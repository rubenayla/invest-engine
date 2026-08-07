# update — Refresh prices, run models, launch dashboard

Fetch latest prices, run all ML models, regenerate dashboard.

## Modes

- **Full update** (default): Fetches all data including financial statements, insider/activist/holdings data. Use for weekly refreshes.
- **Lite update** (`--lite-fetch` or user says "fast update", "lite update", "just prices"): Fetches only prices + key metrics, skips financial statements and SEC data. ~3-5x faster, much less rate-limiting. Use for daily refreshes.

## Steps

1. **Start the dashboard server** in the background so the user can see progress immediately:
   ```bash
   uv run python scripts/dashboard_server.py &
   ```
   Tell the user: **Dashboard is live at http://localhost:8050**

2. **Run the update pipeline**. Pass through any arguments the user provided (universe, skip flags):
   ```bash
   uv run python scripts/update_all.py $ARGUMENTS
   ```
   For lite mode:
   ```bash
   uv run python scripts/update_all.py --lite-fetch $ARGUMENTS
   ```
   This runs (in order, unless skipped):
   - Data fetching from yfinance (lite: prices+metrics only, no financial statements)
   - Insider data from SEC Form 4 (skipped in lite)
   - Activist stakes from SEC 13D/13G (skipped in lite)
   - Institutional holdings from SEC 13F (skipped in lite)
   - EDINET Japan data (skipped in lite)
   - GBM predictions (6 variants)
   - AutoResearch predictions (5-model ensemble)
   - Classic valuations (DCF, RIM, ratios, etc.)
   - Dashboard HTML regeneration
   - Opportunity scanner

   The default universe is `sp500`. Common alternatives: `international`, `japan`, `tech`, `growth`, `europe`, `spain`, `all`, `cached`.

3. **Report completion** — summarize what ran, how long it took, and remind the user the dashboard is at http://localhost:8050

## Important

- Always use `uv run python` for all commands
- Run the dashboard server FIRST so the user gets the link immediately
- The full update pipeline can take 10-20 minutes; lite mode is typically 3-5 minutes
- If the dashboard server is already running on port 8050, skip starting it again and just run the update pipeline
- If the user only says `/update` with no arguments, default to `--universe sp500` (full mode)
- If the user says "fast update", "lite", "just prices", or "quick update", use `--lite-fetch`
- The user can also trigger updates from the browser UI — the dashboard server has an /api/update endpoint
