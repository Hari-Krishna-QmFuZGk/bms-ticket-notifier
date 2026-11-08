# Current watch: Ramayana Telugu at Prasads PCX

Confirmed preferences: Saturday 14 November 2026; Prasads Multiplex Hyderabad; any PCX-labelled screen; show starts 13:00–23:00 IST inclusive; check every ten minutes; alert once per newly bookable session.

The user supplied ET00523814. Live browser verification showed it is Telugu 4DX 3D. Selecting Telugu / All on the official page produced reference ET00518312 and the v5 all-format query. Prasads' Telugu 3D section contains event ET00523155 with explicit PCX Screen labels. The checker uses the verified all-format reference and a PCX filter, rather than monitoring the 4DX-only event.

GitHub Variables are configured:

```text
BMS_URL=https://in.bookmyshow.com/movies/hyderabad/ramayana/buytickets/ET00518312/20261114
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

The generated booking link adds etCodes=*, language=telugu, and refEventCode=ET00518312 so it preserves all Telugu formats.

On 8 November, local v5 API access returned HTTP 200. The response explicitly marked 14 November date-disabled and fell back to today's shows with a date-changed toast. The checker treats this as date_not_open and never alerts from the fallback date. This is a point-in-time observation, not a guarantee of future availability.

GitHub-hosted access still returns HTTP 403: access denied by website. No CAPTCHA, cookies, proxies, or browser impersonation are used. Monitoring remains paused pending an execution-environment decision.

All three Resend secret names are present. The one-time requested test succeeded with provider acceptance: https://github.com/Hari-Krishna-QmFuZGk/bms-ticket-notifier/actions/runs/42441173951 . Inbox receipt remains user-confirmed.

43 tests passed: https://github.com/Hari-Krishna-QmFuZGk/bms-ticket-notifier/actions/runs/42441301774
Final cloud access diagnostic: https://github.com/Hari-Krishna-QmFuZGk/bms-ticket-notifier/actions/runs/42441298638
