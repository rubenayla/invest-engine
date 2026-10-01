# Tasks

## Repair the update queue failure and cron status reporting

- [ ] Remove or repair the malformed pending LLM-verdict queue entry that makes `scripts/save_llm_verdict.py --flush-queue` raise `JSONDecodeError`, then rerun the lite update and verify fresh database timestamps and row counts. Update `/home/rubenayla/invest_cron.sh` so a failed `update_all.py` run is not logged as `exit 0` and does not look successful to this monitor.

## Make the dashboard a private authenticated service
## Investigate why the three invest cron jobs stopped after 2026-09-24

- [ ] The user crontab still contains the 02:30 politician fetch, 04:00 backup, and 05:00 update entries, and the cron service is active/enabled. The politician fetch ran on 2026-10-01 but logged a DNS failure; the 04:00 backup ran on 2026-09-30 and produced a 56 MB dump; and the 05:00 update ran on 2026-09-30 but failed while flushing the pending LLM verdict queue on invalid JSON. The update wrapper incorrectly logged exit 0 after the traceback. Database writes remain stale (`current_stock_data` and `valuation_results` at 2026-09-29; `scanner_score_history` at 2026-09-24). Confirm and repair the malformed queue entry and the update wrapper's exit-status handling before rerunning the scheduled update.
- [ ] On 2026-10-01 cron invoked all three jobs. The politician fetch logged a DNS resolution error but then reported no new PTRs without a reliable exit status; the backup completed and wrote a 58M dump; the update failed in `save_llm_verdict.py --flush-queue` before its data-writing stages, while `invest_cron.sh` still logged exit 0. `current_stock_data` and `scanner_score_history` remain frozen at 2026-09-29 and 2026-09-24 respectively.

## Restore the required unauthenticated POST response

- [ ] Keep `invest.rubenayla.xyz` behind authenticated access. The application currently has no authentication and exposes the full live research universe plus write endpoints that start or cancel data refreshes and create or delete price alarms. Bind the application to loopback only and enforce authentication at the proxy before restoring the public tunnel. A public read-only product, if wanted later, must be a separate static export with no account-specific research or writable endpoints.

## Re-run insider snapshot backfill against the investment database

- [ ] Run `ssh -fN -L 5433:localhost:5432 y540-ubuntu`, then `uv run python scripts/backfill_insider_snapshots.py` and `uv run python scripts/dashboard.py`. The investment database is healthy on `y540-ubuntu`; `hetzner-db` reaches the separate Partle database.

## Account for LLM-research freshness in the opportunity ranking

- [ ] Make each ranked opportunity internally consistent: either freeze price, scenario returns and expected value at the research date, or rebase all scenario returns and expected value when the dashboard refreshes the price. Then mark or discount stale research so old and fresh analyses are not compared as if they had equal currency.
