# Tasks

## Re-run insider snapshot backfill against the investment database

- [ ] Run `ssh -fN -L 5433:localhost:5432 y540-ubuntu`, then `uv run python scripts/backfill_insider_snapshots.py` and `uv run python scripts/dashboard.py`. The investment database is healthy on `y540-ubuntu`; `hetzner-db` reaches the separate Partle database.

## Account for LLM-research freshness in the opportunity ranking

- [ ] Make each ranked opportunity internally consistent: either freeze price, scenario returns and expected value at the research date, or rebase all scenario returns and expected value when the dashboard refreshes the price. Then mark or discount stale research so old and fresh analyses are not compared as if they had equal currency.
