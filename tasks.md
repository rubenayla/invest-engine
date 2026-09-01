# Tasks

## Re-run insider snapshot backfill against the investment database

- [ ] Run `ssh -fN -L 5433:localhost:5432 y540-ubuntu`, then `uv run python scripts/backfill_insider_snapshots.py` and `uv run python scripts/dashboard.py`. The investment database is healthy on `y540-ubuntu`; `hetzner-db` reaches the separate Partle database.

## Account for LLM-research freshness in the opportunity ranking

- [ ] Mark or discount stale research so an old expected-value estimate is not compared with a fresh one as if both described the current buying opportunity.
