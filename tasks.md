# Tasks

## Make the dashboard a private authenticated service
## Investigate why the three invest cron jobs stopped after 2026-09-24

- [ ] The user crontab still contains the 02:30 politician fetch, 04:00 backup, and 05:00 update entries, and the cron service is active/enabled. The 02:30 fetch ran on 2026-09-30, but cron has not invoked the 04:00 backup or 05:00 update since 2026-09-24. Some `current_stock_data` and `valuation_results` rows have 2026-09-29 timestamps, so those writes may come from a separate/manual run; `scanner_score_history` remains dated 2026-09-24. Inspect cron invocation and user-environment errors before rerunning any job.

## Restore the required unauthenticated POST response

- [ ] Keep `invest.rubenayla.xyz` behind authenticated access. The application currently has no authentication and exposes the full live research universe plus write endpoints that start or cancel data refreshes and create or delete price alarms. Bind the application to loopback only and enforce authentication at the proxy before restoring the public tunnel. A public read-only product, if wanted later, must be a separate static export with no account-specific research or writable endpoints.

## Re-run insider snapshot backfill against the investment database

- [ ] Run `ssh -fN -L 5433:localhost:5432 y540-ubuntu`, then `uv run python scripts/backfill_insider_snapshots.py` and `uv run python scripts/dashboard.py`. The investment database is healthy on `y540-ubuntu`; `hetzner-db` reaches the separate Partle database.

## Account for LLM-research freshness in the opportunity ranking

- [ ] Make each ranked opportunity internally consistent: either freeze price, scenario returns and expected value at the research date, or rebase all scenario returns and expected value when the dashboard refreshes the price. Then mark or discount stale research so old and fresh analyses are not compared as if they had equal currency.
