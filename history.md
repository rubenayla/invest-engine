
## 2026-08-16 — Thesis change: MP WATCH→BUY (conviction MEDIUM→MEDIUM)
**Believed (prior variant perception):** Market was focused on 2028 magnet scale, but we were waiting for evidence of Stage 2 execution (heavy rare earths) or a pullback to .
**Happened:** Q2 2026 revenue jumped 89% YoY on record NdPr production (840 mt). First commercial gadolinium oxide supply announced. GM magnet shipments on track for Q4.
**Lesson (transferable):** When a capital-intensive manufacturing buildout proves its intermediate stage (Stage 2 separation), the multiple re-rates before the final stage (Stage 3 magnets) is fully online, because execution risk drops materially.
**Surviving edge / re-upgrade triggers:** The Q4 2026 magnet shipments are the next catalyst. Thesis breaks if magnet yields/specs fail.

## 2026-08-18 — Insider snapshot backfill implementation

Added `scripts/backfill_insider_snapshots.py`, which reconstructs one as-of-date insider signal for each ticker and open-market Form 4 transaction date. It writes to the dedicated `insider_signal_history` table so the backfill does not invent mandatory valuation scores in `scanner_score_history`. The dashboard API reads this table and retains a fallback to scanner-captured snapshots.

The configured PostgreSQL tunnel at `127.0.0.1:5433` accepted connections to `postgres`, but the configured `invest` database did not exist. The live backfill and dashboard regeneration remain pending until that database is restored or the connection file is corrected.

## 2026-08-19 — Database location clarified

The missing `invest` database was a tunnel-target error, not data loss. `hetzner-db` reaches the Hetzner Partle server, whose PostgreSQL cluster contains `partle` but not `invest`. The investment database is on `y540-ubuntu` at PostgreSQL `localhost:5432`; it is online and contains 422 MB, 109,085 insider transactions, and 120,497 scanner score-history rows as of this check. The correct local tunnel is `ssh -fN -L 5433:localhost:5432 y540-ubuntu`.

Root cause of the wrong diagnosis: the real `hetzner-db` alias was copied from the separate Partle workflow, where it is used to reach Partle's PostgreSQL server. The invest repository already names `y540-ubuntu` as its tunnel alias in `scripts/update_all.py:27` (commit `f5bf756`). The two projects share a machine and port convention, but not the database host.

## 2026-08-19 — Investment dashboard deployment gap

The invest repository's `.github/workflows/ci.yml` contains only a test job. It does not pull code or restart the dashboard on `y540-ubuntu`. The running dashboard server there was started on 2026-08-17 from commit `7e292f3`, while `origin/main` had advanced to `d2e0237`. Partle auto-deploys through its separate `.github/workflows/deploy.yml` and `scripts/ship.sh`; that deployment mechanism is not shared with invest.

## 2026-08-21 — Candidates for deeper insider-signal research

The live dashboard screen ranked TSM, ASGN, SPG, VITL, and GEHC among the strongest current insider-buying signals by cluster score. TSM had the highest cluster score (21), but its net-buy percentage was negative and its valuation models disagreed sharply, so it needs verification rather than automatic promotion. ASGN had a strong all-buy signal but the latest activity was 114 days old. GEHC had eight buys, no sells, and about $6.4 million of dollar conviction, while its valuation models also disagreed; GE HealthCare's Q2 2026 release reported 5.7% revenue growth, 11.1% organic orders growth, a $23.9 billion backlog, reaffirmed 2026 guidance, and a CFO transition. Sources: https://investor.tsmc.com/english/quarterly-results/2026/q2 and https://investor.gehealthcare.com/news-releases/news-release-details/ge-healthcare-reports-second-quarter-2026-financial-results.

## 2026-08-21 — Independent four-company research run

Four workers researched TSM, GEHC, ASGN, and SPG independently. Each wrote only its company folder under `~/vault/finance/notes/companies/{TICKER}/` and saved its ticker-specific `llm_deep_analysis` database row. The coordinator committed the outputs after the workers finished; shared watchlists, task boards, and history were unchanged. The research skill now requires this commit boundary because separate file paths do not make concurrent git-index operations safe.

## 2026-08-21 — Main-push deployment verified

The GitHub Actions deployment job was already present and functional, but the workflow ignored root Markdown-only pushes. It now runs for every push to `main`, passes the expected commit SHA to the remote deploy script, and verifies that y540 checked out that exact revision before regenerating and restarting the dashboard. Commit `d6783f8` deployed successfully; the service health endpoint returned `{"ok":true}`.
