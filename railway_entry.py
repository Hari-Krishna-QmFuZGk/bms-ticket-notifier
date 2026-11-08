"""One cron invocation, with a durable volume and automatic watch expiry."""
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from config import Config, boolean
from monitor import cli


def run(env=None, today=None):
    env = os.environ if env is None else env
    mode = env.get('BMS_RUN_MODE', 'dry-run').strip()
    if mode not in ('dry-run', 'check', 'test-notification'):
        raise ValueError('BMS_RUN_MODE must be dry-run, check, or test-notification')
    if mode == 'test-notification':
        return cli(['--test-notification'])
    if mode == 'check' and not boolean(env, 'MONITOR_ENABLED', False):
        print('Monitoring paused; no requests or email.')
        return 0
    config = Config.from_env(env)
    today = today or datetime.now(ZoneInfo('Asia/Kolkata')).strftime('%Y%m%d')
    if max(config.dates) < today:
        print('Watch dates have passed; no requests or email. Remove the cron schedule to stop launches.')
        return 0
    mount = env.get('RAILWAY_VOLUME_MOUNT_PATH', '')
    if mount != '/data' or not Path(mount).is_dir() or not os.path.ismount(mount):
        raise ValueError('Attach the persistent Railway volume at /data before running the checker')
    args = ['--state-file', '/data/bms_state.json']
    if mode == 'dry-run':
        args.append('--dry-run')
    result = cli(args)
    if mode == 'check' and result == 0:
        print('Check completed; persistent state checkpoint is on /data.')
    return result


if __name__ == '__main__':
    try:
        sys.exit(run())
    except (ValueError, OSError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(1)
