import copy
import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

import main
from config import Config
from monitor import decode_snapshot, run_check, watch_id
from state import StateError, StateStore

ENV = {'BMS_URL': 'https://in.bookmyshow.com/movies/chennai/test/ET00123456',
       'BMS_THEATRE': 'Test Cinema', 'BMS_DATES': '20261120'}
NOW = '2026-11-03T10:00:00+00:00'


def response(status='3', session='S1', date='20261120', venue='Test Cinema'):
    """Synthetic fixture in the upstream parser's schema, NOT a verified live response."""
    return {'data': {
        'topStickyWidgets': [{'type': 'horizontal-block-list', 'data': [
            {'id': date, 'styleId': 'date-selected', 'data': ['Fri', '20', 'Nov']}]}],
        'bottomSheetData': {'format-selector': {'widgets': [
            {'type': 'vertical-text-list', 'data': [{'styleId': 'bottomsheet-subtitle', 'text': 'Test Movie'}]}]}},
        'showtimeWidgets': [{'type': 'groupList', 'data': [{'type': 'venueGroup', 'data': [
            {'type': 'venue-card', 'additionalData': {'venueCode': 'V1', 'venueName': venue}, 'showtimes': [
                {'title': '07:30 PM', 'additionalData': {
                    'sessionId': session, 'showDateCode': date, 'showTimeCode': '1930',
                    'categories': [{'priceDesc': 'Regular', 'curPrice': 250, 'availStatus': status}]}}]}]}]}]}}


class ConfigTests(unittest.TestCase):
    def test_defaults_and_city_override(self):
        c = Config.from_env(ENV)
        self.assertEqual(c.city, 'hyderabad')
        self.assertIn('/hyderabad/', c.url)
        self.assertTrue(c.notify_once)
        self.assertFalse(c.stop_after_found)

    def test_dates_and_time_parsing(self):
        c = Config.from_env(dict(ENV, BMS_DATES='20261121,20261120,20261120', BMS_TIME='Evening, 19:30'))
        self.assertEqual(c.dates, ('20261120', '20261121'))
        self.assertEqual(c.times, 'evening,19:30')

    def test_per_date_time_rules(self):
        dates = '20261105,20261106,20261107,20261108'
        rules = {'20261105': 'Evening, Night', '20261106': 'evening,night',
                 '20261107': '', '20261108': ''}
        c = Config.from_env(dict(ENV, BMS_DATES=dates, BMS_TIME=json.dumps(rules)))
        self.assertEqual(c.time_filter_for('20261105'), 'evening,night')
        self.assertEqual(c.time_filter_for('20261108'), '')
        # Reformatting the same JSON must not create a new watch / duplicate alert.
        reordered = dict(reversed(list(rules.items())))
        other = Config.from_env(dict(ENV, BMS_DATES=dates, BMS_TIME=json.dumps(reordered, indent=2)))
        self.assertEqual(watch_id(c), watch_id(other))

    def test_invalid_per_date_time_rules(self):
        for rules in ('{', '{}', '{"20261120":null}', '{"20261120":"25:00"}',
                      '{"20261121":"evening"}',
                      '{"20261120":"evening","20261120":"night"}'):
            with self.subTest(rules=rules), self.assertRaises(ValueError):
                Config.from_env(dict(ENV, BMS_TIME=rules))

    def test_invalid_config(self):
        for k, v in [('BMS_URL', ''), ('BMS_URL', 'https://evil.example/movies/x/ET00123456'),
                     ('BMS_URL', ENV['BMS_URL'] + '?token=private'),
                     ('BMS_CITY', 'typo'), ('BMS_THEATRE', ''), ('BMS_DATES', '20260230'),
                     ('BMS_DATES', '2026112'), ('BMS_TIME', '25:00'), ('NOTIFY_ONCE', 'yes'),
                     ('STOP_AFTER_FOUND', 'yes'), ('CHECK_INTERVAL', '1')]:
            with self.subTest(k=k, v=v), self.assertRaises(ValueError):
                Config.from_env(dict(ENV, **{k: v}))

    def test_booking_link_respects_explicit_date(self):
        c = Config.from_env(dict(ENV, BMS_URL=ENV['BMS_URL'] + '/20261101'))
        self.assertIn('/buytickets/ET00123456/20261120', c.url)
        self.assertNotIn('20261101', c.url)

    def test_date_from_url(self):
        env = dict(ENV, BMS_URL=ENV['BMS_URL'] + '/20261120', BMS_DATES='')
        self.assertEqual(Config.from_env(env).dates, ('20261120',))
        with self.assertRaises(ValueError):
            Config.from_env(dict(ENV, BMS_DATES=''))


class ParserTests(unittest.TestCase):
    def setUp(self):
        self.config = Config.from_env(ENV)

    def test_pcx_telugu_time_boundaries(self):
        config = Config.from_env(dict(ENV, BMS_TIME='13:00-23:00',
                                     BMS_SCREEN='PCX', BMS_LANGUAGE='Telugu', CHECK_INTERVAL='10'))
        for time, expected in [('1259', False), ('1300', True), ('1930', True),
                               ('2300', True), ('2301', False)]:
            data = response()
            data['data']['topStickyWidgets'].append({'type': 'horizontal-text-list', 'data': [
                {'leftText': {'data': [{'components': [{'text': 'Telugu • 2D'}]}]}}]})
            show = data['data']['showtimeWidgets'][0]['data'][0]['data'][0]['showtimes'][0]
            show['screenAttr'] = 'PCX Dolby Atmos'
            show['additionalData']['showTimeCode'] = time
            with self.subTest(time=time):
                self.assertEqual(bool(decode_snapshot(data, config, '20261120')[1]), expected)
        show['additionalData']['showTimeCode'] = '1930'
        for label in ['2D', 'NonPCX']:
            show['screenAttr'] = label
            self.assertEqual(decode_snapshot(data, config, '20261120')[1], [])
        show['screenAttr'] = ''
        with self.assertRaisesRegex(RuntimeError, 'Screen metadata missing'):
            decode_snapshot(data, config, '20261120')
        show['screenAttr'] = 'PCX'
        data['data']['topStickyWidgets'].pop()
        with self.assertRaisesRegex(RuntimeError, 'language not confirmed'):
            decode_snapshot(data, config, '20261120')

    def test_invalid_time_ranges(self):
        for value in ['23:00-13:00', '13:00-24:00', '13:60-23:00', '13:00-']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                Config.from_env(dict(ENV, BMS_TIME=value))

    def test_parse_and_filter(self):
        movie, shows, _ = decode_snapshot(response(), self.config, '20261120')
        self.assertEqual(movie['name'], 'Test Movie')
        self.assertEqual(len(shows), 1)
        self.assertEqual(main.filter_shows(shows, 'other', '', ''), [])
        self.assertEqual(main.filter_shows(shows, 'test', 'morning', ''), [])
        self.assertEqual(len(main.filter_shows(shows, 'TEST', '19:30', '20261120')), 1)
        self.assertEqual(main.filter_shows(shows, '', '', '20261121'), [])
        shows[0].date_code = ''
        self.assertEqual(main.filter_shows(shows, '', '', '20261120'), [])

    def test_thursday_friday_from_four_and_weekends_anytime(self):
        rules = {'20261105': 'evening,night', '20261106': 'evening,night',
                 '20261107': '', '20261108': ''}
        c = Config.from_env(dict(ENV, BMS_DATES=','.join(rules), BMS_TIME=json.dumps(rules)))
        for date in rules:
            for time in ('0030', '0900', '1559', '1600', '2359'):
                data = response(date=date)
                show = data['data']['showtimeWidgets'][0]['data'][0]['data'][0]['showtimes'][0]
                show['additionalData']['showTimeCode'] = time
                _, shows, _ = decode_snapshot(data, c, date)
                expected = date in ('20261107', '20261108') or int(time) >= 1600
                with self.subTest(date=date, time=time):
                    self.assertEqual(bool(shows), expected)

    def test_unknown_responses(self):
        for data in ({}, {'data': {}}, response(status='9'), response(date='20261121'),
                     response(venue='Other Cinema')):
            with self.subTest(data=data), self.assertRaises(RuntimeError):
                decode_snapshot(data, self.config, '20261120')

    def test_missing_identity_never_unavailable(self):
        for field in ('sessionId', 'showDateCode', 'categories', 'showTimeCode'):
            data = response()
            del data['data']['showtimeWidgets'][0]['data'][0]['data'][0]['showtimes'][0]['additionalData'][field]
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                decode_snapshot(data, self.config, '20261120')

    def test_disabled_date_is_known_unavailable(self):
        data = response()
        data['data']['topStickyWidgets'][0]['data'][0]['styleId'] = 'date-disabled'
        data['data']['showtimeWidgets'] = []
        _, shows, reason = decode_snapshot(data, self.config, '20261120')
        self.assertEqual(shows, [])
        self.assertEqual(reason, 'date_not_open')


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = StateStore(Path(self.temp.name) / 'state.json')
        self.config = Config.from_env(dict(ENV, NOTIFY_ONCE='false'))
        self.sender = Mock(return_value='email-accepted')

    def run_check(self, data=None, **kwargs):
        return run_check(kwargs.pop('config', self.config), self.store,
                         fetch=kwargs.pop('fetch', Mock(return_value=data if data is not None else response())),
                         sender=self.sender, now=kwargs.pop('now', NOW), **kwargs)

    def watch(self):
        return self.store.load()['watches'][watch_id(self.config)]

    def test_movie_city_date_passed_to_fetch(self):
        fetch = Mock(return_value=response())
        self.run_check(fetch=fetch)
        fetch.assert_called_once_with('ET00123456', '20261120', *main.REGION_MAP['hyderabad'])

    def test_existing_state_unchanged_by_dry_run(self):
        self.run_check()
        before = self.store.path.read_bytes(), self.store.backup.read_bytes()
        self.sender.reset_mock()
        self.run_check(response(session='S2'), dry_run=True)
        self.assertEqual(before, (self.store.path.read_bytes(), self.store.backup.read_bytes()))
        self.sender.assert_not_called()

    def test_first_run_and_unchanged(self):
        self.assertEqual(self.run_check(), 0)
        self.assertEqual(self.sender.call_count, 1)
        self.assertTrue(self.watch()['notified'])
        self.run_check()
        self.assertEqual(self.sender.call_count, 1)
        self.assertIsNone(self.watch()['pending'])

    def test_sold_out_then_available_and_status_changes(self):
        self.run_check(response('0'))
        self.sender.assert_not_called()
        self.run_check(response('1'))
        self.run_check(response('2'))
        self.run_check(response('3'))
        self.assertEqual(self.sender.call_count, 1)

    def test_new_showtime_and_notify_once(self):
        self.run_check()
        self.run_check(response(session='S2'))
        self.assertEqual(self.sender.call_count, 2)
        self.config = replace(self.config, notify_once=True)
        self.run_check()
        self.run_check(response(session='S3'))
        self.assertEqual(self.sender.call_count, 3)

    def test_failure_retry_uses_exact_payload_and_key(self):
        self.sender.side_effect = RuntimeError('Resend HTTP 401; email acceptance unconfirmed')
        self.assertEqual(self.run_check(), 1)
        self.assertFalse(self.watch()['notified'])
        self.assertEqual(self.watch()['records']['20261120']['result'], 'available')
        first = self.sender.call_args
        self.sender.side_effect = None
        self.assertEqual(self.run_check(now='2026-11-03T10:05:00+00:00'), 0)
        self.assertEqual(first, self.sender.call_args)
        self.assertTrue(self.watch()['notified'])

    def test_expired_pending_requires_manual_review(self):
        self.sender.side_effect = RuntimeError('timeout')
        self.run_check()
        self.sender.reset_mock()
        self.run_check(now='2026-11-04T11:00:00+00:00')
        self.sender.assert_not_called()
        self.assertIn('idempotency limit', self.watch()['last_error'])

    def test_checkpoint_failure_prevents_sending(self):
        with patch.object(self.store, 'save', side_effect=StateError('push failed')):
            with self.assertRaises(StateError):
                self.run_check()
        self.sender.assert_not_called()

    def test_crash_after_send_retries_same_key(self):
        save = self.store.save
        def crash(state):
            if state['watches'][watch_id(self.config)].get('last_notification'):
                raise StateError('crash')
            save(state)
        with patch.object(self.store, 'save', side_effect=crash), self.assertRaises(StateError):
            self.run_check()
        first = self.sender.call_args
        self.assertIsNotNone(self.watch()['pending'])
        self.run_check(now='2026-11-03T10:05:00+00:00')
        self.assertEqual(first, self.sender.call_args)

    def test_api_error_preserves_previous_availability(self):
        self.run_check()
        old = self.watch()['records']['20261120']
        self.assertEqual(self.run_check(fetch=Mock(side_effect=RuntimeError('HTTP 403'))), 1)
        record = self.watch()['records']['20261120']
        self.assertEqual(record['available'], old['available'])
        self.assertEqual(record['last_success'], NOW)
        self.assertEqual(record['result'], 'unknown')
        self.assertEqual(self.sender.call_count, 1)

    def test_partial_date_failure_does_not_clear_valid_date(self):
        self.config = replace(self.config, dates=('20261120', '20261121'))
        self.run_check(fetch=Mock(side_effect=[response(), response(date='20261121')]))
        self.assertEqual(self.run_check(fetch=Mock(side_effect=[response(), RuntimeError('timeout')])), 1)
        self.assertTrue(self.watch()['records']['20261121']['available'])
        self.assertEqual(self.watch()['records']['20261121']['result'], 'unknown')

    def test_dry_run_no_writes_or_send(self):
        self.assertEqual(self.run_check(dry_run=True), 0)
        self.assertFalse(self.store.path.exists())
        self.sender.assert_not_called()

    def test_stops_only_after_accepted_alert(self):
        self.config = replace(self.config, stop_after_found=True)
        self.sender.side_effect = RuntimeError('timeout')
        self.run_check()
        self.assertFalse(self.watch()['stopped'])
        self.sender.side_effect = None
        self.run_check()
        self.assertTrue(self.watch()['stopped'])
        fetch = Mock(side_effect=AssertionError('must not fetch after stop'))
        self.run_check(fetch=fetch)
        fetch.assert_not_called()

    def test_changed_target_gets_separate_state(self):
        self.run_check()
        self.run_check(config=replace(self.config, theatre='Test'))
        self.assertEqual(self.sender.call_count, 2)
        self.assertEqual(len(self.store.load()['watches']), 2)

    def test_state_roundtrip_and_corruption_backup(self):
        self.run_check()
        expected = copy.deepcopy(self.watch()['notified'])
        self.run_check(now='2026-11-03T10:05:00+00:00')
        self.store.path.write_text('broken')
        recovered = StateStore(self.store.path).load()
        self.assertEqual(recovered['watches'][watch_id(self.config)]['notified'], expected)
        self.store.backup.write_text('{"version":2,"watches":{"bad":{}}}')
        with self.assertRaises(StateError):
            StateStore(self.store.path).load()


class NetworkTests(unittest.TestCase):
    @patch('main.requests.get')
    def test_blocks_not_retried(self, get):
        get.return_value.status_code = 403
        with self.assertRaisesRegex(RuntimeError, '403'):
            main.fetch_bms('ET00123456', '20261120', *main.REGION_MAP['hyderabad'])
        self.assertEqual(get.call_count, 1)

    @patch('time.sleep')
    @patch('main.requests.get')
    def test_timeouts_and_transient_errors_bounded(self, get, sleep):
        get.side_effect = main.requests.Timeout('secret text should not be logged')
        with self.assertRaisesRegex(RuntimeError, 'after 3 attempts'):
            main.fetch_bms('ET00123456', '20261120', *main.REGION_MAP['hyderabad'])
        self.assertEqual(get.call_count, 3)
        self.assertEqual(sleep.call_count, 2)
        get.reset_mock(side_effect=True)
        get.return_value.status_code = 503
        with self.assertRaisesRegex(RuntimeError, '503'):
            main.fetch_bms('ET00123456', '20261120', *main.REGION_MAP['hyderabad'])
        self.assertEqual(get.call_count, 3)

    @patch('main.requests.get')
    def test_empty_invalid_and_changed_json(self, get):
        get.return_value.status_code = 200
        for data in (None, [], {}, {'data': None}):
            get.return_value.json.return_value = data
            with self.subTest(data=data), self.assertRaises(RuntimeError):
                main.fetch_bms('ET00123456', '', *main.REGION_MAP['hyderabad'])
        get.return_value.json.side_effect = ValueError()
        with self.assertRaisesRegex(RuntimeError, 'invalid JSON'):
            main.fetch_bms('ET00123456', '', *main.REGION_MAP['hyderabad'])

    @patch.dict(os.environ, {'RESEND_API_KEY': 'secret', 'RESEND_TO_EMAIL': 'to@example.com', 'RESEND_FROM_EMAIL': 'from@example.com'})
    @patch('main.requests.post')
    def test_email_acceptance_and_details(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = {'id': 'accepted'}
        shows = main.parse_shows(response())
        self.assertEqual(main.send_email('Tickets', ['new show'], shows, {'name': 'Movie', 'observed_at': NOW}, ENV['BMS_URL'], 'stable-key'), 'accepted')
        payload = post.call_args.kwargs['json']
        for text in ('Movie', 'Test Cinema', '20261120', '07:30 PM', ENV['BMS_URL']):
            self.assertIn(text, payload['html'])
        self.assertEqual(post.call_args.kwargs['headers']['Idempotency-Key'], 'stable-key')
        post.return_value.json.return_value = {}
        with self.assertRaisesRegex(RuntimeError, 'missing email id'):
            main.send_email('Tickets', [], [], {}, ENV['BMS_URL'], 'stable-key')
        post.return_value.status_code = 401
        post.return_value.text = 'secret'
        with self.assertRaisesRegex(RuntimeError, 'Resend HTTP 401'):
            main.send_email('Tickets', [], [], {}, ENV['BMS_URL'], 'stable-key')

    @patch.dict(os.environ, {'RESEND_API_KEY': '', 'RESEND_TO_EMAIL': '', 'RESEND_FROM_EMAIL': ''})
    def test_missing_credentials_fail(self):
        with self.assertRaisesRegex(RuntimeError, 'all three'):
            main.send_email('Test', [], [], {}, ENV['BMS_URL'], 'key')


class CliTests(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    @patch('monitor.send_email', return_value='test-id')
    def test_test_email_does_not_require_movie_or_load_state(self, sender):
        from monitor import cli
        with patch('monitor.StateStore', side_effect=AssertionError('must not open state')):
            self.assertEqual(cli(['--test-notification']), 0)
        sender.assert_called_once()

    def test_local_lock_rejects_overlapping_check(self):
        import fcntl
        from monitor import cli
        with tempfile.TemporaryDirectory() as directory:
            old_cwd = os.getcwd()
            try:
                os.chdir(directory)
                with open('.bms-monitor.lock', 'a') as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    with patch.dict(os.environ, ENV), patch('monitor.run_check') as check:
                        self.assertEqual(cli(['--dry-run']), 1)
                        check.assert_not_called()
            finally:
                os.chdir(old_cwd)

    @patch.dict(os.environ, {'RESEND_API_KEY': 'secret', 'RESEND_TO_EMAIL': 'to@example.com', 'RESEND_FROM_EMAIL': 'from@example.com'})
    @patch('main.requests.post')
    def test_email_transport_failure_does_not_log_provider_exception(self, post):
        post.side_effect = main.requests.Timeout('secret reflected by provider')
        with self.assertRaisesRegex(RuntimeError, '^Resend request failed; email acceptance unconfirmed$'):
            main.send_email('Test', [], [], {}, ENV['BMS_URL'], 'key')
