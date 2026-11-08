# Railway deployment status — 8 November 2026

## Verified access test

The user approved the one-time test deployment. Railway Singapore (asia-southeast1-eqsg3a) returned HTTP 200 and valid Ramayana date metadata. November 14 was explicitly date-disabled at test time. No notifications or state writes occurred.

Project: d80b94c2-0dfc-46dd-beff-21d924f2ac08
Environment: 15e25f51-dcfd-4127-93b6-f0e5727b99a0
Probe service: e7498465-7d69-4c46-b93d-2563cf4e4066
Probe deployment: 6faafce5-aacb-4ca8-a8b4-afd4180792b0
Probe has no schedule and restart policy NEVER.

## Prepared scheduled checker (not yet deployed)

Service: ticket-checker (38f693cf-5428-41e4-ac85-ae12562bba36)
Source: Hari-Krishna-QmFuZGk/bms-ticket-notifier, codex/cloud-monitor, pinned to 2e4df34c94aa8d52111c91eff661b316e7909361
Schedule: */10 * * * *
Region: Singapore
Limit: 256 MB RAM, 1 vCPU
Volume: ticket-checker-state (0eb262bc-3e7a-4cd4-83de-d77965a0c4cd), 512 MB at /data
Start: /app/.venv/bin/python railway_entry.py

The container uses the existing Python checker and locked dependencies. It exits after each check, retains alert history on the mounted volume, refuses ephemeral state storage, and skips API/email work once all watch dates have passed in IST. Cron launches remain until the schedule is removed. No public domain or web server is configured.

The watch Variables and RESEND_FROM_EMAIL are saved. User must add RESEND_API_KEY and RESEND_TO_EMAIL directly to ticket-checker Variables; GitHub secrets cannot be read back. At last inspection these two were absent. Do not infer readiness from the successful GitHub email test alone.

Source/settings/volume are staged in patch 3346801e-779a-4408-b5cd-6fa6a825caf7. Inspect current staged changes and secret names, then obtain explicit confirmation for deployment of the recurring monitor. The preceding approval was for the one-time access test.

Validation: all 47 unit tests passed, Docker image built, Asia/Kolkata timezone resolved, and paused container startup exited successfully in CI run 42442564229.

After deployment, verify runtime API access from the Python container, the /data checkpoint, a second invocation reusing state, and one scheduled execution. A deployment status alone is insufficient. Check Resend from Railway separately if needed; the prior GitHub test was accepted, inbox receipt remains unconfirmed.
