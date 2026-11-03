# Pending Hyderabad Ramayana watch

The user requested **Telugu**, at any of these Hyderabad cinemas:

- Allu Cinemas, Kokapet ([cinema website](https://allucinemas.com/)).
- AMB Cinemas, Sarath City Capital Mall, Kondapur ([cinema website](https://www.ambcinemas.in/)).
- Inorbit Mall, Cyberabad ([mall website](https://www.inorbit.in/inorbit-mall-cyberabad)); exact BookMyShow cinema listing/identity remains unverified.

| Date | Allowed show start time (IST) |
| --- | --- |
| Thursday, 5 November 2026 | 16:00–23:59 |
| Friday, 6 November 2026 | 16:00–23:59 |
| Saturday, 7 November 2026 | Anytime |
| Sunday, 8 November 2026 | Anytime |

The dates correspond to the upcoming weekend as of the conversation on 3 November 2026. [Fandango's Ramayana listing](https://www.fandango.com/ramayana-2026-245446/movie-overview) lists a worldwide 5 November release, but does not establish Hyderabad Telugu show availability.

## Language and live-check blocker

The user supplied this reference: [Ramayana — Hindi, ET00451914](https://in.bookmyshow.com/movies/hyderabad/ramayana-hindi/ET00451914).

Both the forwarded title and URL label it **Hindi**, conflicting with the earlier Telugu preference. A direct read of that exact URL returned **HTTP 403** from this environment. Its language selector and any Telugu event identifier could not be inspected. Do not guess a Telugu identifier by editing the slug, and do not configure this Hindi URL as if it were Telugu. A confirmed Telugu BookMyShow URL is needed, or the user must explicitly choose Hindi instead.

## Proposed configuration after language verification

```text
BMS_CITY=hyderabad
BMS_THEATRE=Allu Cinemas,AMB Cinemas,Inorbit
BMS_DATES=20261105,20261106,20261107,20261108
BMS_TIME={"20261105":"evening,night","20261106":"evening,night","20261107":"","20261108":""}
CHECK_INTERVAL=5
MONITOR_ENABLED=false
```

`BMS_URL` is deliberately unresolved. Theatre substrings are provisional until actual BookMyShow inventory can be read; they are name filters, not verified venue IDs. Exact returned names should be checked before activation. No GitHub Variables or Secrets were changed and no live notification or scheduled monitoring was activated for this watch.

The user has not yet selected whether one accepted alert across all cinemas is sufficient (`NOTIFY_ONCE=true`, the default) or whether newly bookable sessions should continue to alert (`NOTIFY_ONCE=false`). Stopping after the first alert likewise remains optional. See README for the three required Resend Secrets and manual dry-run/email-test setup.
