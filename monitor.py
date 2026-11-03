"""One check per invocation; independent availability and notification outcomes."""
import argparse
import copy
import fcntl
import hashlib
import json
import sys
import uuid
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

from config import Config
from main import (CatInfo, ShowInfo, REGION_MAP, fetch_bms, filter_shows,
                  parse_dates, parse_movie_info, parse_shows, send_email)
from state import GitStateStore, StateError, StateStore, validate_show


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def watch_id(config):
    return hashlib.sha256(json.dumps(asdict(config), sort_keys=True).encode()).hexdigest()


def decode_snapshot(data, config, date):
    """Only a recognizable inventory or an explicitly disabled date proves unavailability."""
    try:
        body = data['data']
        if not isinstance(body['topStickyWidgets'], list) or not isinstance(body['showtimeWidgets'], list):
            raise ValueError('Missing widget lists')
        dates = parse_dates(data)
        movie = parse_movie_info(data)
        if not isinstance(movie['name'], str) or not movie['name'] or movie['name'] == 'Unknown Movie':
            raise ValueError('Movie not found or movie metadata schema changed')
        shows = parse_shows(data)
        if any(d.date_code == date and d.status == 'NOT_OPEN' for d in dates):
            return movie, [], 'date_not_open'
        matching = filter_shows(shows, config.theatre, '', '')
        if not matching:
            raise ValueError('Theatre not listed; bookings may not be open, or check theatre name')
        for s in matching:
            validate_show(asdict(s))
            if (not s.venue_code or not s.session_id or not s.date_code
                    or not s.time or not s.time_code or not s.categories):
                raise ValueError('Show identity, date, time, or categories missing')
            if any(c.status not in ('0', '1', '2', '3') for c in s.categories):
                raise ValueError('Unknown category availability status')
            tc = str(s.time_code)
            if not tc.isdigit() or not 0 <= int(tc) < 2400 or int(tc) % 100 >= 60:
                raise ValueError('Invalid show time')
        if not any(s.date_code == date for s in matching):
            raise ValueError('Requested date not returned; availability unknown')
        filtered = filter_shows(matching, config.theatre, config.times, date)
        return movie, filtered, 'matching_shows' if filtered else 'no_preferred_showtimes'
    except (KeyError, TypeError, AttributeError, ValueError, IndexError) as exc:
        # Do not log raw response values; messages below contain only our diagnostics.
        if isinstance(exc, ValueError):
            reason = str(exc)
        else:
            reason = 'BookMyShow response format changed'
        raise RuntimeError(reason) from None


def available_shows(shows):
    return {f'{s.venue_code}|{s.session_id}|{s.date_code}|{s.time_code}': asdict(s)
            for s in shows if any(c.status in ('1', '2', '3') for c in s.categories)}


def restore_show(raw):
    values = dict(raw)
    values['categories'] = [CatInfo(**c) for c in values['categories']]
    return ShowInfo(**values)


def deliver_pending(state, watch, store, config, sender, now):
    pending = watch.get('pending')
    if pending is None:
        return True
    try:
        age = datetime.fromisoformat(now) - datetime.fromisoformat(pending['created_at'])
        # Resend only retains keys for 24 hours. A crash/timeout may have sent mail.
        if age < timedelta(0):
            raise RuntimeError('Pending timestamp is in the future; check state and runner clock')
        if age >= timedelta(hours=23, minutes=55):
            raise RuntimeError('Pending alert is near/past Resend 24h idempotency limit; review Resend logs before manual recovery')
        email_id = sender(pending['subject'],
                          [f"Availability observed at {pending['created_at']} (UTC); check current availability before booking."],
                          [restore_show(s) for s in pending['shows']], pending['movie'],
                          pending['url'], pending['key'])
        if not isinstance(email_id, str) or not email_id:
            raise RuntimeError('Notification provider did not confirm acceptance')
    except (RuntimeError, ValueError, TypeError, KeyError) as exc:
        message = str(exc) if isinstance(exc, RuntimeError) else 'Invalid pending notification state'
        watch['last_error'] = message
        print(f'NOTIFICATION ERROR: {message}')
        store.save(state)
        return False
    watch['notified'] = sorted(set(watch['notified']) | set(pending['keys']))
    watch['last_notification'] = {'accepted_at': now, 'provider_id': email_id}
    watch['pending'] = None
    watch['last_error'] = None
    watch['stopped'] = config.stop_after_found
    store.save(state)
    return True


def run_check(config, store, *, dry_run=False, fetch=fetch_bms, sender=send_email, now=None):
    now = now or utcnow()
    state = copy.deepcopy(store.load())
    key = watch_id(config)
    watch = state['watches'].setdefault(key, {
        'config': asdict(config), 'records': {}, 'notified': [], 'sequence': 0,
        'pending': None, 'stopped': False, 'last_error': None,
    })
    if watch['stopped'] and not dry_run:
        print('Monitoring stopped after an accepted availability alert. No BookMyShow requests made.')
        return 0
    # Retry the exact previously checkpointed payload/key, even after a runner crash.
    if watch.get('pending') and not dry_run:
        if not deliver_pending(state, watch, store, config, sender, now):
            return 1
        if watch['stopped']:
            return 0
    region = REGION_MAP[config.city]
    all_available = {}
    movie = None
    failures = []
    for date in config.dates:
        record = watch['records'].setdefault(date, {'available': {}})
        try:
            data = fetch(config.event, date, *region)
            movie, shows, reason = decode_snapshot(data, config, date)
            available = available_shows(shows)
            record.update({'result': 'available' if available else 'unavailable',
                           'reason': reason, 'available': available,
                           'detected': [asdict(s) for s in shows],
                           'last_success': now, 'last_error': None})
            all_available.update(available)
            print(f'{date}: {record["result"]} ({reason}); {len(available)} bookable show(s)')
        except RuntimeError as exc:
            record.update({'result': 'unknown', 'last_error': str(exc)})
            failures.append(f'{date}: {exc}')
            print(f'{date}: unable to determine availability: {exc}')
    watch['last_error'] = '; '.join(failures) or None
    unseen = set(all_available) - set(watch['notified'])
    should_notify = unseen and not (config.notify_once and watch['notified'])
    if should_notify:
        watch['sequence'] += 1
        payload_movie = dict(movie, observed_at=now)
        watch['pending'] = {
            'key': f'bms-{key}-{watch["sequence"]}', 'created_at': now,
            'keys': sorted(unseen), 'shows': [all_available[k] for k in sorted(all_available)],
            'movie': payload_movie, 'subject': f'BMS Alert: {movie["name"]} — tickets available',
            'url': config.url,
        }
    if dry_run:
        print(f'DRY RUN: would notify={bool(should_notify)}; no email or state writes')
        return 1 if failures else 0
    # This durable checkpoint MUST succeed before any network notification.
    store.save(state)
    if should_notify and not deliver_pending(state, watch, store, config, sender, now):
        return 1
    # A successful email must not hide an unknown date result.
    if failures:
        watch['last_error'] = '; '.join(failures)
        store.save(state)
    return 1 if failures else 0


def cli(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='Read-only check; no notifications or state changes')
    parser.add_argument('--test-notification', action='store_true', help='Send one test email, without checking tickets or modifying state')
    parser.add_argument('--git-state', action='store_true', help='Persist checkpoints to origin/bms-state (Actions only)')
    parser.add_argument('--state-file', default='bms_state.json')
    args = parser.parse_args(argv)
    if args.dry_run and args.test_notification:
        parser.error('--dry-run and --test-notification are mutually exclusive')
    try:
        if args.test_notification:
            send_email('BMS notifier: test email', ['Resend test; this is not a ticket availability alert.'],
                       [], {'name': 'Notification test'}, 'https://in.bookmyshow.com/', f'bms-test-{uuid.uuid4()}')
            return 0
        config = Config.from_env()
        # Workflow concurrency serializes cloud runs; flock protects local invocations.
        lock = Path('.bms-monitor.lock')
        with lock.open('a') as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise StateError('Another local check is running') from None
            store = GitStateStore() if args.git_state else StateStore(args.state_file)
            return run_check(config, store, dry_run=args.dry_run)
    except (ValueError, RuntimeError, OSError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
