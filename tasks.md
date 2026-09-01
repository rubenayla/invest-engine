# Tasks

## Re-run insider snapshot backfill against the investment database

- [ ] Run `ssh -fN -L 5433:localhost:5432 y540-ubuntu`, then `uv run python scripts/backfill_insider_snapshots.py` and `uv run python scripts/dashboard.py`. The investment database is healthy on `y540-ubuntu`; `hetzner-db` reaches the separate Partle database.

## Make the LLM ranking describe what it measures

- [ ] Rename or redesign the dashboard's LLM sort. It currently displays company quality but ranks only verdict, entry-price state, expected value divided by bear-case loss, and conviction. Decide whether this is an opportunity ranking or a research-quality ranking, label it accordingly, and include freshness so old thesis scores do not compare as if current.
