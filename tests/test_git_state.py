"""Integration tests against local bare Git remotes; no GitHub or email calls."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from state import GitStateStore, StateError, empty_state


def git(cwd, *args):
    return subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


class GitStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.remote = self.root / 'origin.git'
        git(self.root, 'init', '--bare', str(self.remote))
        seed = self.clone('seed')
        git(seed, 'config', 'user.name', 'Test')
        git(seed, 'config', 'user.email', 'test@example.com')
        (seed / 'code.txt').write_text('code must not change')
        git(seed, 'add', 'code.txt')
        git(seed, 'commit', '-m', 'seed')
        git(seed, 'push', 'origin', 'HEAD')
        self.code_head = git(seed, 'rev-parse', 'HEAD')

    def clone(self, name):
        path = self.root / name
        git(self.root, 'clone', str(self.remote), str(path))
        return path

    def test_persistence_from_fresh_runner_and_no_code_commits(self):
        first = GitStateStore(self.clone('first'))
        state = first.load()
        first.save(state)
        code = git(first.repo, 'rev-parse', 'HEAD')
        self.assertEqual(code, self.code_head)
        second = GitStateStore(self.clone('second'))
        self.assertEqual(second.load(), state)
        head = git(second.worktree, 'rev-parse', 'HEAD')
        second.save(state)
        self.assertEqual(git(second.worktree, 'rev-parse', 'HEAD'), head)
        # A subsequent timestamp checkpoint creates a recoverable backup.
        state['watches']['test'] = {'records': {}, 'notified': [], 'sequence': 0,
                                    'stopped': False, 'pending': None, 'last_error': 'timeout'}
        second.save(state)
        third = GitStateStore(self.clone('third'))
        self.assertEqual(third.load(), state)
        self.assertTrue(third.backup.exists())

    def test_stale_writer_cannot_overwrite_remote(self):
        seed = GitStateStore(self.clone('initial'))
        seed.save(empty_state())
        first = GitStateStore(self.clone('a'))
        second = GitStateStore(self.clone('b'))
        a = first.load()
        b = second.load()
        a['watches']['a'] = {'records': {}, 'notified': [], 'sequence': 0, 'stopped': False}
        b['watches']['b'] = {'records': {}, 'notified': [], 'sequence': 0, 'stopped': False}
        first.save(a)
        with self.assertRaises(StateError):
            second.save(b)
        final = GitStateStore(self.clone('final'))
        self.assertEqual(final.load(), a)

    def test_read_only_does_not_create_remote_branch(self):
        store = GitStateStore(self.clone('dry'))
        self.assertEqual(store.load(), empty_state())
        self.assertEqual(git(self.root, '--git-dir', str(self.remote), 'branch', '--list', 'bms-state'), '')
