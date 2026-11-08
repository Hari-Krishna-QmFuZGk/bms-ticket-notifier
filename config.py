"""Validated configuration; no credentials or network side effects at import time."""
import os
import re
import json
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse

from main import REGION_MAP, TIME_PERIODS, parse_bms_url


def boolean(env, name, default):
    value = env.get(name, str(default)).strip().lower()
    if not value:
        return default
    if value not in ('true', 'false', '1', '0'):
        raise ValueError(f'{name} must be true or false')
    return value in ('true', '1')


def time_preferences(raw, dates):
    """Keep the original comma list, or require an explicit rule for every date."""
    def normalize(value):
        if not isinstance(value, str):
            raise ValueError('Each BMS_TIME rule must be a string; use empty string for anytime')
        result = ','.join(p.strip().lower() for p in value.split(',') if p.strip())
        for period in result.split(',') if result else []:
            clock = r'(?:[01]\d|2[0-3]):[0-5]\d'
            if re.fullmatch(f'{clock}-{clock}', period):
                start, end = period.split('-')
                if start > end:
                    raise ValueError('BMS_TIME ranges must start before they end')
            elif period not in TIME_PERIODS and not re.fullmatch(clock, period):
                raise ValueError('BMS_TIME requires a period, HH:MM or inclusive HH:MM-HH:MM range')
        return result

    if not raw.strip().startswith('{'):
        return normalize(raw)

    def unique_rules(pairs):
        rules = {}
        for date, value in pairs:
            if date in rules:
                raise ValueError('BMS_TIME contains a duplicate date rule')
            rules[date] = value
        return rules

    try:
        rules = json.loads(raw, object_pairs_hook=unique_rules)
    except json.JSONDecodeError:
        raise ValueError('BMS_TIME date rules must be a valid JSON object') from None
    if set(rules) != set(dates):
        raise ValueError('BMS_TIME JSON must contain exactly the target dates; use empty strings for anytime')
    return json.dumps({date: normalize(value) for date, value in rules.items()}, sort_keys=True)


@dataclass(frozen=True)
class Config:
    url: str
    event: str
    city: str
    theatre: str
    dates: tuple[str, ...]
    times: str
    notify_once: bool
    stop_after_found: bool
    screen: str = ''
    language: str = ''

    def time_filter_for(self, date):
        if self.times.startswith('{'):
            return json.loads(self.times)[date]
        return self.times

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        url = env.get('BMS_URL', '').strip()
        parsed = parse_bms_url(url)
        u = urlparse(url)
        if (u.scheme != 'https' or u.netloc != 'in.bookmyshow.com'
                or not parsed['event_code'] or u.query or u.fragment):
            raise ValueError('BMS_URL must be an HTTPS in.bookmyshow.com movie URL with ET identifier (no query/fragment)')
        city = env.get('BMS_CITY', '').strip().lower() or 'hyderabad'
        if city not in REGION_MAP:
            raise ValueError('BMS_CITY is unsupported; choose a city in REGION_MAP')
        theatre = env.get('BMS_THEATRE', '').strip()
        if not theatre or not any(t.strip() for t in theatre.split(',')):
            raise ValueError('BMS_THEATRE is required (comma-separated name substrings)')
        raw_dates = env.get('BMS_DATES', '').strip() or parsed['date_code'] or ''
        dates = tuple(sorted(set(d.strip() for d in raw_dates.split(',') if d.strip())))
        if not dates:
            raise ValueError('Set BMS_DATES or include a target date in BMS_URL')
        for d in dates:
            if not re.fullmatch(r'\d{8}', d):
                raise ValueError('BMS_DATES must contain YYYYMMDD dates')
            datetime.strptime(d, '%Y%m%d')
        times = time_preferences(env.get('BMS_TIME', ''), dates)
        if env.get('CHECK_INTERVAL', '').strip() not in ('', '10'):
            raise ValueError('CHECK_INTERVAL must be 10; edit workflow cron to change scheduling')
        # Rewrite a city embedded in the supplied URL to match the explicit/default city.
        parts = u.path.split('/')
        if 'movies' not in parts or parts.index('movies') + 2 >= len(parts):
            raise ValueError('BMS_URL must be a movie page URL')
        parts[parts.index('movies') + 1] = REGION_MAP[city][1]
        if 'buytickets' not in parts:
            parts.insert(parts.index(parsed['event_code']), 'buytickets')
        # Explicit BMS_DATES must also override a stale date embedded in the link.
        parts = [part for part in parts if not re.fullmatch(r'\d{8}', part)]
        if len(dates) == 1:
            parts = [part for part in parts if part] + [dates[0]]
            parts.insert(0, '')
        url = 'https://in.bookmyshow.com' + '/'.join(parts)
        return cls(url, parsed['event_code'], city, theatre, dates, times,
                   boolean(env, 'NOTIFY_ONCE', True), boolean(env, 'STOP_AFTER_FOUND', False),
                   env.get('BMS_SCREEN', '').strip().lower(),
                   env.get('BMS_LANGUAGE', '').strip().lower())
