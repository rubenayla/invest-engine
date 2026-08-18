
## 2026-08-16 — Thesis change: MP WATCH→BUY (conviction MEDIUM→MEDIUM)
**Believed (prior variant perception):** Market was focused on 2028 magnet scale, but we were waiting for evidence of Stage 2 execution (heavy rare earths) or a pullback to .
**Happened:** Q2 2026 revenue jumped 89% YoY on record NdPr production (840 mt). First commercial gadolinium oxide supply announced. GM magnet shipments on track for Q4.
**Lesson (transferable):** When a capital-intensive manufacturing buildout proves its intermediate stage (Stage 2 separation), the multiple re-rates before the final stage (Stage 3 magnets) is fully online, because execution risk drops materially.
**Surviving edge / re-upgrade triggers:** The Q4 2026 magnet shipments are the next catalyst. Thesis breaks if magnet yields/specs fail.

## 2026-08-18 — Insider snapshot backfill implementation

Added `scripts/backfill_insider_snapshots.py`, which reconstructs one as-of-date insider signal for each ticker and open-market Form 4 transaction date. It writes to the dedicated `insider_signal_history` table so the backfill does not invent mandatory valuation scores in `scanner_score_history`. The dashboard API reads this table and retains a fallback to scanner-captured snapshots.

The configured PostgreSQL tunnel at `127.0.0.1:5433` accepted connections to `postgres`, but the configured `invest` database did not exist. The live backfill and dashboard regeneration remain pending until that database is restored or the connection file is corrected.
