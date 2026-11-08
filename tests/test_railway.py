import unittest
from unittest.mock import patch

from railway_entry import run
from tests.test_monitor import ENV


class RailwayTests(unittest.TestCase):
    def test_paused_and_expired_never_check(self):
        with patch('railway_entry.cli') as cli:
            self.assertEqual(run({'BMS_RUN_MODE': 'check'}), 0)
            self.assertEqual(run(dict(ENV, BMS_RUN_MODE='check', MONITOR_ENABLED='true'), today='20261121'), 0)
            cli.assert_not_called()

    def test_missing_volume_refuses_ephemeral_state(self):
        with patch('railway_entry.cli') as cli, self.assertRaisesRegex(ValueError, 'persistent Railway volume'):
            run(dict(ENV), today='20261120')
        cli.assert_not_called()

    def test_mounted_volume_and_modes(self):
        env = dict(ENV, RAILWAY_VOLUME_MOUNT_PATH='/data', MONITOR_ENABLED='true')
        with patch('railway_entry.Path.is_dir', return_value=True), patch('railway_entry.os.path.ismount', return_value=True), patch('railway_entry.cli', return_value=0) as cli:
            self.assertEqual(run(env, today='20261120'), 0)
            cli.assert_called_with(['--state-file', '/data/bms_state.json', '--dry-run'])
            self.assertEqual(run(dict(env, BMS_RUN_MODE='check'), today='20261120'), 0)
            cli.assert_called_with(['--state-file', '/data/bms_state.json'])

    def test_email_mode_is_explicit_and_config_independent(self):
        with patch('railway_entry.cli', return_value=0) as cli:
            self.assertEqual(run({'BMS_RUN_MODE': 'test-notification'}), 0)
            cli.assert_called_once_with(['--test-notification'])
        with self.assertRaises(ValueError):
            run({'BMS_RUN_MODE': 'unexpected'})
