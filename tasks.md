# Tasks

## Re-run insider snapshot backfill against the investment database

- [ ] Run `ssh -fN -L 5433:localhost:5432 y540-ubuntu`, then `uv run python scripts/backfill_insider_snapshots.py` and `uv run python scripts/dashboard.py`. The investment database is healthy on `y540-ubuntu`; `hetzner-db` reaches the separate Partle database.

## Deploy investment dashboard code to y540

- [ ] Add a GitHub Actions deployment job for `main` that updates `/home/rubenayla/repos/invest-engine` on `y540-ubuntu` and restarts the user dashboard server after checks pass. The current invest workflow only tests; Partle has a separate SSH-based deployment workflow.
