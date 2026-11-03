# Implementation and deployment handoff

Implementation prepared on branch **`codex/cloud-monitor`**, based on upstream `5f9782d`. The user created the public fork at `Hari-Krishna-QmFuZGk/bms-ticket-notifier`, which was verified as a fork of the original repository with default branch `main`. The user approved pushing this feature branch and opening a draft PR against the fork. No default-branch push, merge, real email, or monitoring activation is included.

## Files changed

| Files | Purpose |
| --- | --- |
| `main.py` | Reused upstream API endpoint, region map, data classes, parsers, filters and email template; added bounded errors/retries, correct date filtering, provider acceptance checks and idempotency header |
| `config.py` | Validated URL, movie identifier, Hyderabad/city, cinema, dates, times and notification policies; generated booking link respecting explicit date |
| `monitor.py` | One-shot orchestration; available/unavailable/unknown results; per-date observations; first-run alerts; pending/accepted notification separation; dry-run, test and stop modes |
| `state.py` | Atomic validated JSON, backup recovery, dedicated Git worktree/branch persistence, durable checkpoints before and after email, fast-forward-only pushes |
| `bms_state.json` | Empty version-2 local template; removed unrelated historical upstream observations |
| `.github/workflows/bms-checker.yml` | Five-minute opt-in schedule, manual modes, single-writer concurrency, scoped contents-write token, cached locked dependencies |
| `.github/workflows/tests.yml` | Automated read-only CI for PRs/relevant code pushes; no Resend secrets |
| `tests/__init__.py`, `tests/test_monitor.py`, `tests/test_git_state.py` | Deterministic mocked API/email tests and local Git persistence/race tests |
| `.env.example`, `.gitignore` | Local configuration template and exclusion of credentials/runtime files |
| `pyproject.toml` | Meaningful package description; existing runtime dependencies/Python constraint retained; lockfile unchanged |
| `README.md`, `AUDIT.md`, `HANDOFF.md` | Setup, initial audit, current limits, validation and rollout instructions |

## Decisions

- Keep the existing lightweight API approach and Resend HTTP integration. No Playwright or new runtime dependencies.
- Persist authoritative state on `bms-state`; dependency caches are disposable and artifacts are not used for history. Successful timestamp updates normally require one small commit per check. The code branch stays unchanged.
- Persist notification intent before sending. Resend must return a successful status and email ID before notification history advances. Retries reuse the original observation/key, including after a crash. Fail visibly near the 24-hour provider idempotency limit; manual reconciliation is safer than an ambiguous duplicate.
- Retain last valid per-date observations on errors, with an explicit unknown result. Partial date failures do not erase another date's history.
- `STOP_AFTER_FOUND` stops API polling after provider acceptance. It does not change GitHub workflow activation settings. `MONITOR_ENABLED` separately gates scheduled jobs and defaults off.
- No credentials/addresses in Git state or provider error bodies in logs. Movie/theatre/date preferences are public if the repository is public.

## Validation performed

- Baseline: unittest discovery ran **0 tests**; upstream had no tests.
- Final: `.venv/bin/python -m unittest discover -v` ran **35 tests, all passed**, using Python **3.14.8**.
- Coverage includes configuration/movie request/city/date/theatre/time filters, known availability, disabled date, missing identity/changed schema, first run, unchanged sessions, new sessions, notify-once, retry/failure/crash recovery, expired pending alert, dry-run immutability, stop-after-acceptance, corruption recovery, local locking, durable pre-send failure, local bare-Git remote restoration, no-op commits, read-only branch behavior, and rejection of stale concurrent pushes.
- `actionlint` **v1.7.12** validated both workflows with no findings. Its release archive checksum was checked against published release checksums.
- `uv lock --check --offline` succeeded; existing dependency lock remains valid.
- Python compilation and `git diff --check` succeeded.
- A live **dry run** using the upstream example movie and Hyderabad returned **HTTP 403 / unable to determine**, exit status 1, with no email or state writes. User-specific movie/theatre/dates were not provided. **Live BookMyShow compatibility is not established.**
- Inspected checkout v6's authentication implementation: it supports Git worktree credentials, as used by this state mechanism. GitHub Actions execution itself has not yet been run or verified.
- No live Resend test: credentials were not supplied. Mocked provider acceptance/failure tests passed; inbox delivery remains to be tested.

## Exact configuration

Secrets (all three required for sending):

```text
RESEND_API_KEY
RESEND_FROM_EMAIL
RESEND_TO_EMAIL
```

Variables:

```text
BMS_URL=<actual movie URL>               # required
BMS_CITY=hyderabad                     # default
BMS_THEATRE=<specific cinema name>     # required
BMS_DATES=<YYYYMMDD,YYYYMMDD>           # required unless date is in URL
BMS_TIME=evening,night                  # optional; empty = all
CHECK_INTERVAL=5                       # optional, fixed cron remains authoritative
NOTIFY_ONCE=true                       # default
STOP_AFTER_FOUND=false                 # default
MONITOR_ENABLED=false                  # keep off until explicitly activating
```

## Approval and remaining setup

Verified destination: public fork **`Hari-Krishna-QmFuZGk/bms-ticket-notifier`**, default branch **`main`**, with reported push permission. The user approved publishing only **`codex/cloud-monitor`** and opening a **draft PR against that fork's `main`**. GitHub API fork creation was denied to the integration, so the user created the fork manually.

Merging, pushing to `main`, changing credentials/configuration, and activating monitoring remain outside this approval. Tests may run on the feature-branch push if Actions is enabled; monitoring remains gated off. See the PR for the current publication and CI status.

After review/merge (a separate user-controlled step):

1. Provide the actual movie URL, theatre, dates and optional time preferences.
2. Enable Actions in the fork if needed. Configure the Variables above with `MONITOR_ENABLED=false` and the three Secrets; follow README's interactive `gh secret set` commands so keys stay out of chat/history.
3. Verify Resend sender/recipient restrictions. For personal free testing use `onboarding@resend.dev` and the account owner's email; other recipients require a verified domain.
4. Run workflow mode `dry-run`. If GitHub's runner also receives a block/schema error, pause and investigate permitted access before relying on the monitor.
5. Run mode `test-notification`; verify provider logs and actual inbox delivery.
6. Run mode `check`; verify a `bms-state` branch/checkpoint exists. Run again and verify unchanged availability does not send a duplicate email.
7. Only with explicit approval, set `MONITOR_ENABLED=true`. Watch initial scheduled runs; GitHub does not guarantee five-minute execution.
8. Stop with `MONITOR_ENABLED=false` or disable the workflow. Keep state to preserve notification history.

README contains copy-paste CLI commands, logs/state verification, and pending-alert/corruption recovery instructions.

## Cost and limits

Estimated **₹0/month** on public standard GitHub runners plus Resend's free tier (currently 3,000 emails/month, 100/day), without buying a domain. Current GitHub Free private compute allowance is documented as $12/month; at least one billed minute for each requested five-minute run costs about $51.84–$53.57/month before allowance. A private repository cannot be assumed free. Official source links and calculations appear in README.

Availability can change between polling and opening a link. The undocumented endpoint/schema may change or block cloud IPs. Requests are bounded and conservative; there is no anti-bot evasion, paid proxy, CAPTCHA solving, guaranteed delivery, or automatic ticket purchasing. All runtime state loss necessarily loses duplicate history. Pending notifications older than the provider idempotency window need manual reconciliation.
