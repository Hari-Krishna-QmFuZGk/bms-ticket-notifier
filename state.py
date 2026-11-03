"""Atomic local storage and fast-forward-only persistence on an isolated Git branch."""
import json
import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path


class StateError(RuntimeError):
    pass


def empty_state():
    return {'version': 2, 'watches': {}}


def validate_show(show):
    if not isinstance(show, dict):
        raise ValueError('Invalid stored show')
    for key in ('venue_code', 'venue_name', 'session_id', 'date_code', 'time', 'time_code', 'screen_attr'):
        if not isinstance(show.get(key), str) or (key != 'screen_attr' and not show[key]):
            raise ValueError('Invalid show identity or display fields')
    categories = show.get('categories')
    if not isinstance(categories, list) or not categories:
        raise ValueError('Invalid show categories')
    for cat in categories:
        if (not isinstance(cat, dict) or not isinstance(cat.get('name'), str)
                or not isinstance(cat.get('price'), (str, int, float))
                or cat.get('status') not in ('0', '1', '2', '3')):
            raise ValueError('Invalid show category fields')


def validate(state):
    if not isinstance(state, dict) or state.get('version') != 2 or not isinstance(state.get('watches'), dict):
        raise ValueError('Unsupported state schema')
    for watch in state['watches'].values():
        if not isinstance(watch, dict) or not isinstance(watch.get('records'), dict):
            raise ValueError('Invalid watch records')
        if not isinstance(watch.get('notified'), list) or not all(isinstance(k, str) for k in watch['notified']):
            raise ValueError('Invalid notification history')
        if not isinstance(watch.get('sequence'), int) or not isinstance(watch.get('stopped'), bool):
            raise ValueError('Invalid watch metadata')
        for record in watch['records'].values():
            if not isinstance(record, dict) or not isinstance(record.get('available'), dict):
                raise ValueError('Invalid availability record')
            for show in record['available'].values():
                validate_show(show)
        pending = watch.get('pending')
        if pending is not None:
            if (not isinstance(pending, dict) or not isinstance(pending.get('shows'), list)
                    or not isinstance(pending.get('keys'), list)
                    or not all(isinstance(pending.get(k), str) for k in ('key', 'created_at', 'subject', 'url'))
                    or not isinstance(pending.get('movie'), dict)):
                raise ValueError('Invalid pending notification')
            if (not pending['shows'] or not pending['keys']
                    or not all(isinstance(k, str) for k in pending['keys'])
                    or not isinstance(pending['movie'].get('name'), str)
                    or pending['movie'].get('observed_at') != pending['created_at']):
                raise ValueError('Invalid pending notification payload')
            created = datetime.fromisoformat(pending['created_at'])
            if created.tzinfo is None:
                raise ValueError('Pending timestamp must include timezone')
            for show in pending['shows']:
                validate_show(show)
    return state


class StateStore:
    def __init__(self, path='bms_state.json'):
        self.path = Path(path)
        self.backup = self.path.with_suffix('.previous.json')
        self.valid_bytes = None

    def load(self):
        if not self.path.exists() and not self.backup.exists():
            return empty_state()
        for path in (self.path, self.backup):
            try:
                raw = path.read_bytes()
                state = validate(json.loads(raw))
                self.valid_bytes = raw
                if path == self.backup:
                    print('WARNING: recovered state from last valid backup')
                return state
            except (OSError, ValueError, TypeError):
                pass
        raise StateError('State is corrupted or legacy. Restore a valid backup or explicitly reset it; refusing to lose notification history.')

    @staticmethod
    def _atomic(path, raw):
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.state-')
        try:
            with os.fdopen(fd, 'wb') as f:
                f.write(raw)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def save(self, state):
        validate(state)
        raw = (json.dumps(state, sort_keys=True, indent=2) + '\n').encode()
        if raw == self.valid_bytes:
            return
        if self.valid_bytes is not None:
            self._atomic(self.backup, self.valid_bytes)
        self._atomic(self.path, raw)
        self.valid_bytes = raw


class GitStateStore(StateStore):
    """One writer under Actions concurrency. Reject remote changes; never force push."""
    branch = 'bms-state'

    def __init__(self, repo='.'):
        self.repo = Path(repo).resolve()
        self.worktree = self.repo / '.monitor-state'
        result = self.git('ls-remote', '--exit-code', '--heads', 'origin', f'refs/heads/{self.branch}', check=False)
        if result.returncode == 0:
            self.git('fetch', '--no-tags', 'origin', f'refs/heads/{self.branch}')
            self.git('worktree', 'add', '--detach', str(self.worktree), 'FETCH_HEAD')
        elif result.returncode == 2:  # Confirmed missing ref, not an authentication/network error.
            self.git('worktree', 'add', '--detach', str(self.worktree), 'HEAD')
            self.git('switch', '--orphan', self.branch, cwd=self.worktree)
        else:
            raise StateError('Cannot inspect remote state branch; refusing a fresh state')
        self.git('config', 'user.name', 'github-actions[bot]')
        self.git('config', 'user.email', 'github-actions[bot]@users.noreply.github.com')
        super().__init__(self.worktree / 'bms_state.json')

    def git(self, *args, cwd=None, check=True):
        try:
            result = subprocess.run(['git', *args], cwd=cwd or self.repo, capture_output=True, text=True, timeout=45)
        except (OSError, subprocess.TimeoutExpired):
            raise StateError('Git state command failed or timed out') from None
        if check and result.returncode:
            # Avoid echoing remote URLs, headers, or provider messages into logs.
            raise StateError('Git state operation failed; inspect branch permissions/network. No force push attempted.')
        return result

    def save(self, state):
        super().save(state)
        paths = ['bms_state.json'] + (['bms_state.previous.json'] if self.backup.exists() else [])
        self.git('add', '--', *paths, cwd=self.worktree)
        diff = self.git('diff', '--cached', '--quiet', cwd=self.worktree, check=False)
        if diff.returncode == 0:
            return
        if diff.returncode != 1:
            raise StateError('Cannot inspect state changes')
        self.git('commit', '-m', 'chore: checkpoint monitor state [skip ci]', cwd=self.worktree)
        self.git('push', 'origin', f'HEAD:refs/heads/{self.branch}', cwd=self.worktree)
