---
name: update
description: Refresh prices, run all ML models, regenerate dashboard, start live server. Use when user says "update", "refresh data", "fetch prices", or "update database".
disable-model-invocation: false
argument-hint: "[--universe sp500] [--skip-fetch] [--skip-insider] [--skip-gbm] [--skip-autoresearch] [--skip-classic] [--skip-scanner]"
allowed-tools: Bash
---

# update_db — Refresh prices, run models, launch dashboard

Fetch latest stock data, run all ML models, regenerate dashboard, start live server.

## Steps

1. **Start the dashboard server** (if not already running):
   ```bash
   lsof -ti:8050 >/dev/null 2>&1 || (uv run python scripts/dashboard_server.py --port 8050 &)
   sleep 2
   open http://127.0.0.1:8050
   ```
   Tell the user: **Dashboard is live at http://localhost:8050**

2. **Run the full update pipeline**. Pass through any arguments the user provided (universe, skip flags):
   ```bash
   uv run python scripts/update_all.py $ARGUMENTS
   ```
   This runs (in order, unless skipped):
   - Data fetching from yfinance
   - Insider signals (SEC Form 4 via EDGAR)
   - GBM predictions (6 variants)
   - AutoResearch predictions (5-model ensemble)
   - Classic valuations (DCF, RIM, ratios, etc.)
   - Dashboard HTML regeneration
   - Opportunity scanner

   The default universe is `sp500`. Common alternatives: `international`, `japan`, `tech`, `growth`, `europe`, `spain`, `all`, `cached`.

3. **Refresh ALL stale stocks in the database** (catches everything the universe missed):
   ```bash
   uv run python -c "
   import yfinance as yf, sqlite3
   from datetime import datetime, timezone

   db = sqlite3.connect('data/stock_data.db')

   # Find all stocks with stale prices (>24h old)
   rows = db.execute('''
       SELECT ticker, fetch_timestamp FROM current_stock_data
       WHERE current_price IS NOT NULL
       AND (fetch_timestamp IS NULL OR fetch_timestamp < datetime('now', '-1 day'))
       ORDER BY fetch_timestamp ASC
   ''').fetchall()
   print(f'Found {len(rows)} stale stocks to refresh')

   updated = 0
   errors = 0
   for ticker, ts in rows:
       try:
           t = yf.Ticker(ticker)
           price = t.info.get('currentPrice') or t.info.get('regularMarketPrice')
           if price:
               db.execute('UPDATE current_stock_data SET current_price = ?, fetch_timestamp = ? WHERE ticker = ?',
                          (price, datetime.now().isoformat(), ticker))
               db.execute('UPDATE valuation_results SET current_price = ? WHERE ticker = ?', (price, ticker))
               updated += 1
               if updated % 20 == 0:
                   print(f'  ... {updated}/{len(rows)} updated')
                   db.commit()
       except Exception as e:
           errors += 1
           if errors <= 5:
               print(f'  {ticker}: error - {e}')
   db.commit()
   db.close()
   print(f'Done: {updated} refreshed, {errors} errors, out of {len(rows)} stale')
   "
   ```

4. **Report completion** — summarize what ran, how long it took, and remind the user the dashboard is at http://localhost:8050

## Important

- Always use `uv run python` for all commands
- Run the dashboard server FIRST so the user gets the link immediately
- The update pipeline can take 10-20 minutes for a full run; keep the user informed of progress
- If the dashboard server is already running on port 8050, skip starting it again and just run the update pipeline
- If the user only says `/update_db` with no arguments, default to `--universe sp500`
- The user can also trigger updates from the browser UI — the dashboard server has an /api/update endpoint
