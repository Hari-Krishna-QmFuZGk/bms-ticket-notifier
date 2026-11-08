# BookMyShow Ticket Notifier

A cloud monitor that runs once per GitHub Actions invocation, checks a movie's showtimes at selected cinemas/dates, sends an availability email through Resend, and exits. It never purchases tickets. The cron requests a run every ten minutes; GitHub can delay or drop scheduled jobs.

**Current status (8 November 2026): local v5 access works; GitHub-hosted access is denied.** The configured Telugu watch uses the current v5 all-format endpoint and its section/seat-widget schema. A local request returned HTTP 200 and explicitly marked 14 November not open. The GitHub runner returned HTTP 403 with an access-denied page. Resend accepted the requested test notification. All 43 tests pass. Monitoring remains off until an execution environment with working access is selected. The legacy v4 path is retained for configurations without BMS_LANGUAGE and is not live-verified.

## Prerequisites and fork

- A GitHub account and preferably a **public** fork, with standard GitHub-hosted Linux runners.
- A free Resend account and a permitted sender/recipient pair.
- A BookMyShow movie URL, the cinema name as BookMyShow lists it, and target dates.
- For local development: Python 3.14+ and [uv](https://docs.astral.sh/uv/). Actions installs them automatically. `requests` is the only direct runtime dependency.

Use GitHub's **Fork** button on [the original repository](https://github.com/shray-narang/bms-ticket-notifier), then apply/merge the implementation branch in your fork. Alternatively, with the GitHub CLI:

```bash
gh repo fork shray-narang/bms-ticket-notifier --clone
cd bms-ticket-notifier
```

Enable workflows under your fork's **Actions** tab if prompted. Scheduled checks are gated off until you set `MONITOR_ENABLED=true`; you can test manually first. No default-branch pushes or activation are required to review a pull request.

## GitHub Variables

Go to **Settings → Secrets and variables → Actions → Variables**. All dates and times are local cinema time (IST for these cities); state timestamps are UTC.

| Variable | Value / behavior |
| --- | --- |
| `BMS_URL` | **Required.** HTTPS movie URL on `in.bookmyshow.com` containing its `ET…` movie identifier. Details or `buytickets` URLs work. Strip query strings/fragments. |
| `BMS_CITY` | Default `hyderabad`. Explicitly overrides the city in the URL, including the booking link. |
| `BMS_THEATRE` | **Required.** Case-insensitive name substring; comma-separated substrings are ORed. Use a specific full name to avoid matching other cinemas. |
| `BMS_DATES` | **Required unless the URL contains a date.** Comma-separated `YYYYMMDD`, e.g. `20261120,20261121`. No implicit today's-date fallback. |
| `BMS_SCREEN` | Optional exact label token in show screen metadata, e.g. `PCX`. Missing metadata is unknown, never assumed PCX. |
| `BMS_LANGUAGE` | Optional required language token in movie metadata, e.g. `telugu`. Missing or mismatched metadata fails closed. |
| `BMS_TIME` | Optional comma-separated periods and/or exact `HH:MM` or inclusive ranges `HH:MM-HH:MM`: `evening,19:30`. Empty means all showtimes. For different preferences by date, use the JSON object described below. |
| `CHECK_INTERVAL` | Optional `10` (minutes). Documents/validates the fixed schedule; changing this variable does **not** rewrite cron. |
| `NOTIFY_ONCE` | Default `true`: one accepted availability alert for this configuration. `false`: alert for each newly bookable session, once per session. |
| `STOP_AFTER_FOUND` | Default `false`. `true` persists a stopped flag after the first accepted availability email; subsequent invocations skip BookMyShow requests. |
| `MONITOR_ENABLED` | Default off. Set exactly `true` to allow scheduled checks. Manual runs work while this is off. |

Periods are morning 06:00–11:59, afternoon 12:00–15:59, evening 16:00–18:59, night 19:00–23:59. Exact times use 24-hour format. Filters are ORed. Supported cities reuse the upstream region map: Hyderabad, Chennai, Mumbai, Delhi/NCR, Bengaluru/Bangalore, Kolkata, Pune, Kochi. Unknown cities are rejected rather than guessed. An absent theatre or date is **unknown**, because absence alone cannot establish sold-out or unopened bookings. An explicitly disabled target date is unavailable.

Different time preferences by date use the existing `BMS_TIME` Variable as a JSON object. It must include **every target date exactly once**; use an empty string for anytime. For example, Thursday/Friday **4 PM onward** and Saturday/Sunday anytime for 5–8 November 2026:

```json
{"20261105":"evening,night","20261106":"evening,night","20261107":"","20261108":""}
```

`evening,night` includes starts at 16:00 through 23:59 IST. The JSON object is canonicalized so changing whitespace or key order does not reset duplicate history. Existing plain `BMS_TIME=evening,night` still applies to every date. Do not substitute a Hindi event identifier when monitoring Telugu; verify the actual Telugu movie/booking URL first. See [WATCH_PLAN.md](WATCH_PLAN.md) for this user's pending Hyderabad watch.

Example configuration (replace the movie, cinema, and dates):

```bash
REPO=YOUR_GITHUB_LOGIN/bms-ticket-notifier
gh variable set BMS_URL --repo "$REPO" --body 'https://in.bookmyshow.com/movies/hyderabad/REPLACE-MOVIE/ET00123456'
gh variable set BMS_CITY --repo "$REPO" --body 'hyderabad'
gh variable set BMS_THEATRE --repo "$REPO" --body 'REPLACE with cinema name'
gh variable set BMS_DATES --repo "$REPO" --body '20261120,20261121'
gh variable set BMS_TIME --repo "$REPO" --body 'evening,night'
gh variable set CHECK_INTERVAL --repo "$REPO" --body '10'
gh variable set NOTIFY_ONCE --repo "$REPO" --body 'true'
gh variable set STOP_AFTER_FOUND --repo "$REPO" --body 'false'
gh variable set MONITOR_ENABLED --repo "$REPO" --body 'false'
```

## Resend credentials and test email

Create an API key at [Resend API Keys](https://resend.com/api-keys), with sending access for the intended domain. Store all three values under **Actions → Secrets**, never as Variables or in source:

| Secret | Purpose |
| --- | --- |
| `RESEND_API_KEY` | Resend sending API key |
| `RESEND_FROM_EMAIL` | Sender address authorized by Resend |
| `RESEND_TO_EMAIL` | One recipient address |

For a zero-cost personal test, `onboarding@resend.dev` can send **only to the email address associated with your Resend account**. It is not an unrestricted sending domain. For other recipients, verify a domain you already own at [Resend Domains](https://resend.com/domains), add the DNS records Resend requests, wait for verification, and use an address at that domain. Buying a new domain would add cost and is unnecessary for personal testing.

These commands prompt for secrets without putting them in shell history:

```bash
gh secret set RESEND_API_KEY --repo "$REPO"
gh secret set RESEND_FROM_EMAIL --repo "$REPO"
gh secret set RESEND_TO_EMAIL --repo "$REPO"
```

Use **Actions → BMS Ticket Checker → Run workflow → mode: test-notification**. This sends one test email, without checking BookMyShow or writing monitoring state. Confirm both the inbox (including spam) and Resend's email logs. A returned Resend email ID means provider acceptance, not guaranteed inbox delivery. The GitHub workflow requires a successful HTTP response and a nonempty email ID before marking an availability alert notified.

## Manual checks and activation

1. Run **mode: dry-run** first. It reads persisted state and checks the API, but sends no email and makes no remote state commits. Check every target date in the logs. A missing state branch is normal before the first real check.
2. Run **mode: test-notification** and verify the recipient receives it.
3. Run **mode: check** for one real check. If tickets are already bookable, the **first run alerts immediately**. Otherwise state records the result.
4. After inspecting the results, opt into scheduled monitoring:

```bash
gh workflow run bms-checker.yml --repo "$REPO" -f mode=dry-run
gh workflow run bms-checker.yml --repo "$REPO" -f mode=test-notification
# Sends availability mail and persists state:
gh workflow run bms-checker.yml --repo "$REPO" -f mode=check
# Explicit activation, only after the checks above:
gh variable set MONITOR_ENABLED --repo "$REPO" --body 'true'
```

The workflow must exist on the default branch for schedules. It uses `*/10 * * * *`, standard `ubuntu-latest`, a ten-minute job timeout, locked dependencies with uv's cache, and no daemon or sleep loop. The runner exits after each check. GitHub concurrency serializes manual/scheduled invocations across refs, with `cancel-in-progress: false`. GitHub can replace older pending runs, delay jobs, or drop runs under load; missed checks are not replayed. Public scheduled workflows may be disabled after 60 days without repository activity. There is no ten-minute execution guarantee or alert-delivery SLA.

## State and duplicate prevention

Actions stores `bms_state.json` and one previous valid backup on a separate **`bms-state` branch**; it never commits state to your code branch. No database, paid storage, or PAT is needed. The job grants only `contents: write` to its scoped `GITHUB_TOKEN`. Repository rules must allow that token to create/update `bms-state`; do not remove protections from your default branch. No workflow uses `pull_request_target` or sends secrets to PR jobs.

Each configuration has a separate hashed watch containing the movie URL/identifier, city, theatre filters, dates, and time preferences. Per-date records contain theatre/session identities, detected shows, current known bookable sessions, the last successful check time, and errors. Notification history and any pending payload are stored separately. No credentials or recipient/sender addresses are written to state. **Public state exposes your movie/cinema preferences and dates.**

- Category codes `1`, `2`, `3` are bookable; `0` is sold out, preserving the upstream mapping. Unknown codes fail closed. An empty/malformed response or a block never clears prior valid observations.
- An alert is triggered by a previously unnotified bookable **session**, identified by venue, session, date, and time. Price/category fullness changes do not trigger duplicate mail. With `NOTIFY_ONCE=false`, newly listed or previously sold-out unnotified sessions can alert. A previously alerted session reopening does not alert again.
- The complete pending payload and stable Resend idempotency key are pushed **before sending**. Acceptance and notification history are pushed afterward. A failed pre-send push prevents mail. A rejected/failed/ambiguous email remains pending for retry on the next check; errors never mark it delivered.
- Pending emails retry the original observation, even if current availability has since changed; the email includes its UTC observation timestamp. Recheck BookMyShow before booking.
- Resend retains idempotency keys for 24 hours. An unresolved pending alert older than 23h55m stops automatic retry and fails visibly, preventing an ambiguous repeat outside that guarantee. Keep sender/recipient credentials unchanged while a payload is pending (Resend rejects changed payloads for the same key).
- Reads use the last valid backup if the current JSON is corrupt. If both are corrupt/unsupported, the run fails without overwriting either. Missing state starts a new watch; deleting all state necessarily loses duplicate history. The old unversioned upstream JSON cannot prove email delivery and must not be reused as notification history.
- Local atomic writes and a process lock protect local runs. Cloud writes are fast-forward-only: unexpected competing pushes fail instead of overwriting remote state. Do not run a second workflow or a local writer against the same branch.

Successful checks normally commit once per run to retain their actual timestamp, plus pre-send/post-acceptance checkpoints when alerting. Identical saves make no commits; stopped checks make no state writes. At ten-minute intervals, timestamp history can mean about 8,640 small commits per 30 days on the isolated branch. Caches can be evicted and are immutable per key; artifacts expire and need download/permission/retention logic. Neither is used as authoritative state. Only dependency packages are cached.

To verify persistence and inspect logs:

```bash
gh run list --repo "$REPO" --workflow bms-checker.yml --limit 10
gh run view RUN_ID --repo "$REPO" --log
gh api "repos/$REPO/contents/bms_state.json?ref=bms-state" --jq .sha
# In a clone:
git fetch origin bms-state
git show FETCH_HEAD:bms_state.json
```

Run a second unchanged check: the notification history should remain unchanged and there should be no second email. The last successful timestamp should advance. A failed date keeps its old observations and timestamp, with `result: unknown` and `last_error` set.

## Stop or resume monitoring

```bash
gh variable set MONITOR_ENABLED --repo "$REPO" --body 'false'
# Optional: disables all runs, including manual dispatch, until re-enabled:
gh workflow disable bms-checker.yml --repo "$REPO"
```

An already-running check may complete; cancel it in Actions if needed. `STOP_AFTER_FOUND=true` stops API polling automatically after an accepted alert; cron jobs still start briefly and exit. Set `MONITOR_ENABLED=false` to skip scheduled jobs entirely, or disable the workflow to stop cron dispatch. No `actions: write` permission is needed for this behavior.

Any change to the watch configuration (including notify/stop policy) creates a new watch and may alert again. To resume the exact stopped watch, pause monitoring, edit its `stopped` field to `false` on `bms-state`, and decide whether to retain `notified`. Retain it to suppress old sessions; clear it only if you deliberately want another alert. Never reset history merely to resolve a transient HTTP/email error.

## Local development

```bash
uv sync --frozen --no-dev
cp .env.example .env
# Edit .env to replace sample movie, theatre, dates and credential placeholders.
set -a
. ./.env
set +a
uv run --no-sync main.py --dry-run
uv run --no-sync main.py --test-notification
uv run --no-sync main.py
uv run --no-sync python -m unittest discover -v
```

Local runs use `bms_state.json` and `bms_state.previous.json` in the current directory. `.env` and backups are ignored. Keep local runtime state out of code commits. `--state-file /tmp/my-bms-state.json` selects a different local file. `--git-state` is intended for the Actions job: it creates a local worktree and can push checkpoints. Dry runs may create a local lock/worktree but never change persistent state or send mail. Test notification needs only the three Resend secrets, not movie configuration.

## Costs (official documentation checked 2026-11-03)

**Target: ₹0/month** using a public repository, standard GitHub-hosted runners, and Resend's free allowance. No continuously running local machine is needed. This is conditional on provider terms and continued free-tier eligibility.

- [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions): standard GitHub-hosted runners in public repositories are free. Larger runners are billed, including in public repos; this workflow does not use them.
- [Current included usage](https://docs.github.com/en/billing/reference/product-usage-included) lists GitHub Free with **$12/month of eligible compute usage**. Private-repository compute consumes the owner's allowance, shared with other work. Do not assume old minute allowances or unlimited private runs.
- [Runner pricing](https://docs.github.com/en/billing/reference/actions-runner-pricing) lists standard Linux 2-core at **$0.006/minute**, with each job rounded up to a whole minute. 144 requested runs/day is 4,320 in 30 days or 4,464 in 31 days. Even at one billed minute per check, a private repo uses roughly $25.92–$26.78 of compute before allowance (about **$13.92–$14.78 beyond a $12 allowance**, if otherwise unused). Two-minute jobs cost more. Actual runs depend on scheduling; prices can change.
- [Resend pricing](https://resend.com/pricing): free transactional tier currently includes **3,000 emails/month, limited to 100/day**. Checks without a new alert do not call Resend. Keep the account on the free plan; this repository does not enable paid overages or upgrade a plan. Test emails count toward limits.
- No artifacts are uploaded. Package caching is an optimization, not a requirement for correctness. Review your own Actions/cache storage usage and billing settings; do not opt into paid capacity for this monitor.

See also [GitHub schedule limitations](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule), [Resend idempotency](https://resend.com/docs/dashboard/emails/idempotency-keys), and [resend.dev sender restrictions](https://resend.com/docs/knowledge-base/403-error-resend-dev-domain).

## Troubleshooting and recovery

| Symptom | Meaning / action |
| --- | --- |
| BookMyShow HTTP 403/401/429 | Unknown availability. Blocking/authentication/rate limits are not sold out. Do not bypass them. Pause scheduled monitoring and review whether permitted API access is available. |
| Timeout or HTTP 5xx | At most three attempts per date, with 1s/2s backoff and connection/read timeouts. Failed dates retain valid state; inspect the next run. Other HTTP errors are not retried in the same check. |
| Movie not found/schema changed | Confirm the ET identifier and current booking URL. The undocumented API or widget fields may have changed; capture a sanitized permitted response for parser maintenance. Mock fixtures cannot establish live support. |
| Theatre not listed / requested date not returned | Check exact cinema name/city/date. Future dates or not-yet-listed theatres remain unknown; the checker refuses to infer a negative. |
| `unavailable (date_not_open)` | Target date explicitly disabled in a recognizable response. No availability email. |
| `unavailable (matching_shows)` | Matching sessions exist, all categories are sold out. |
| No preferred showtimes | Valid inventory/date, but no sessions match your time filters. Broaden `BMS_TIME` if needed. |
| Missing/invalid config | Fix Variables; blank booleans use defaults. Unsupported cities, malformed dates/times, absent URL/theatre, and non-10 intervals fail before requests. |
| Resend HTTP 401/403 | Check API key permissions, verified sender, and resend.dev recipient restriction. No secrets/provider bodies are printed. Pending alert is retained. |
| Resend accepted but inbox empty | Inspect Resend delivery/bounce logs, recipient and spam folder. Provider acceptance cannot prove inbox delivery. |
| Resend HTTP 429/5xx, timeout, or missing email ID | Pending payload is retried with its stable key next run. No history is marked delivered without an email ID. |
| Pending alert near/past 24h limit or HTTP 409 | Pause monitoring; check Resend logs for whether the original payload was accepted. If accepted, update `notified` with `pending.keys`, record the provider ID, clear `pending`, and set `stopped` if desired. If definitely unsent, deliberately clear `pending` to let a fresh sequence/key be generated. Do not blindly reset state after an ambiguous timeout. |
| Corrupt state | Backup recovery logs a warning. If both files fail, pause and restore a known-good file from `bms-state` Git history. If you explicitly choose a fresh start, replace it with `{"version":2,"watches":{}}`; that can produce another first-run alert. |
| Git push/state branch error | Check Actions write permissions, branch rules, network, or another writer. Remote errors do not count as a missing branch. No force pushes are attempted; a failed durable pre-send checkpoint prevents mail. |
| Schedule never runs | Ensure workflow is on default branch, Actions is enabled, and `MONITOR_ENABLED` is exactly `true`. GitHub may delay/drop scheduled events or disable inactive schedules. |

Resend accepted one user-requested test email on 8 November 2026; inbox receipt is not independently verified. The corrected Telugu all-format reference and current PCX watch are recorded in WATCH_PLAN.md. See [AUDIT.md](AUDIT.md) for the initial repository findings and [HANDOFF.md](HANDOFF.md) for validation and deployment status.
