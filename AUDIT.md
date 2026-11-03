# Initial repository audit

Inspected upstream commit `5f9782d` (`chore: update bms_state.json [skip ci]`) on 2026-11-03 before implementation: README, all of `main.py`, `pyproject.toml`, `uv.lock`, `.python-version`, `.gitignore`, tracked state, and the sole Actions workflow. There was no AGENTS.md in the checkout.

| Area | Existing behavior | Required changes |
| --- | --- | --- |
| API | `requests` GET to the existing `/api/movies-data/v4/showtimes-by-event/primary-dynamic` endpoint, 15s timeout, movie ET identifier in request | Retain endpoint; bounded transient retries; distinguish blocked/invalid/error responses from unavailability |
| Movie/city | URL extracts ET identifier and city; region map includes Hyderabad | Explicit city variable defaulting to Hyderabad; reject unknown cities instead of fabricating region codes; require a real configured movie |
| Dates | Dates from env/URL; otherwise default API date | Validate one or more explicit dates; do not accept missing show dates through the date filter |
| Theatre/time | Case-insensitive comma-separated theatre substrings; four time periods | Reuse filters; validate configuration; add exact HH:MM preferences |
| Availability | Per-category statuses mapped from 0–3; compares dates/new categories/sold-out transitions | Alert only on known bookable sessions; do not alert for a new sold-out listing or unrecognized status |
| First run | Saves a baseline without alerting | Alert immediately if matching tickets are already available |
| Notifications | Existing HTML/plaintext Resend integration | Reuse formatting; include dates and booking link; require provider ID; sanitize errors; add test mode |
| Duplicate history | Compares last observations; saves before sending | Separate observations from accepted notifications; checkpoint pending payload before send; retry safely with idempotency key |
| State | `bms_state.json` committed to code branch; invalid JSON silently becomes empty | Versioned schema, atomic writes, valid backup recovery, fail closed if unrecoverable; isolate Git state branch |
| Workflow | `*/10` cron (README claimed 30 minutes), manual dispatch, Ubuntu, Python 3.14/uv, job `contents: write` | Five-minute cron; opt-in activation; cross-ref concurrency; cached dependencies; manual dry-run/test modes; dedicated state branch |
| Tests | No test files/configuration | Add mocked unit tests and local bare-remote Git integration tests |
| Documentation | Short README, incorrect sender advice, typo assigning TO twice | Full setup, Resend restrictions, state/recovery, cost, schedule limitations, and deployment handoff |

Baseline test discovery: `python -m unittest discover -v` reported **0 tests / NO TESTS RAN**. The upstream dependency set installed successfully using `uv sync --frozen` with a writable uv cache and managed Python directory.

Validation of external assumptions: the existing BookMyShow endpoint returned **HTTP 403** from this environment. That is neither a successful live availability check nor proof of sold-out tickets. Current official GitHub billing/scheduling and Resend pricing/idempotency/sender documentation were consulted; links and relevant limits are in README.md. No replacement endpoint was invented.
