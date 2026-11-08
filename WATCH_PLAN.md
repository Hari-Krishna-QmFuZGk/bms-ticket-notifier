# Current watch: Ramayana Telugu at Prasads PCX

Confirmed on 8 November 2026:

- User-provided event: ET00523814, Ramayana, Telugu.
- Hyderabad; Prasads Multiplex; PCX screen metadata required.
- Saturday 14 November 2026, show starts from 13:00 through 23:00 IST inclusive.
- GitHub Actions every 10 minutes (execution may be delayed by GitHub).

```text
BMS_URL=https://in.bookmyshow.com/movies/hyderabad/ramayana/buytickets/ET00523814/20261114
BMS_CITY=hyderabad
BMS_THEATRE=Prasads
BMS_SCREEN=PCX
BMS_LANGUAGE=telugu
BMS_DATES=20261114
BMS_TIME=13:00-23:00
CHECK_INTERVAL=10
NOTIFY_ONCE=false
STOP_AFTER_FOUND=false
MONITOR_ENABLED=false
```

The supplied URL contained 12 November and a Telugu query parameter. The explicit requested date overrides that URL date; the query is replaced with a response-language guard. No Hindi event identifier is substituted. Screen numbers are never assumed to mean PCX. Missing screen/language metadata is unknown and prevents an alert.

Notify for each newly bookable session once; unchanged sessions do not send repeat alerts. Credentials remain in GitHub Secrets only. The recipient email and Resend account setup are pending.

The local read-only API request on 8 November returned HTTP 403. This does not establish availability or validate the current live response schema. A GitHub runner check is required before activation; keep MONITOR_ENABLED=false while access is blocked.

GitHub runner verification also returned HTTP 403: https://github.com/Hari-Krishna-QmFuZGk/bms-ticket-notifier/actions/runs/42440654665 . All 40 unit tests passed. Monitoring remains off.
