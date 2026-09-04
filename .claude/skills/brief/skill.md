---
name: brief
description: Portfolio intelligence briefing — sell signals, buy opportunities, actionable brief. Use when user says "brief", "morning brief", "what should I do", "any sells", "opportunities", or "check portfolio".
argument-hint: "[--skip-update] [--sells-only] [--buys-only]"
---

# Analyze — Portfolio Intelligence Brief

Runs the full analysis pipeline: data freshness check, dashboard, portfolio risk scan, watchlist opportunity ranking, and actionable recommendations.

**Output style**: High density, no fluff. Lead with actions. Concise tables. No disclaimers mid-text (one at the end is fine).

## Phase 1: Data & Dashboard

1. **Check data freshness** by querying the database:
   ```bash
   uv run python -c "
   import sqlite3, sys
   from datetime import datetime, timezone
   sys.path.insert(0, 'src')
   conn = sqlite3.connect('data/stock_data.db')
   # Most recent valuation timestamp
   row = conn.execute('SELECT MAX(timestamp) FROM valuation_results').fetchone()
   newest = row[0] if row else None
   if newest:
       from datetime import datetime
       ts = datetime.fromisoformat(newest)
       age_h = (datetime.now(timezone.utc) - ts.replace(tzinfo=timezone.utc)).total_seconds() / 3600
       print(f'NEWEST_VALUATION={newest}')
       print(f'AGE_HOURS={age_h:.1f}')
       print(f'STALE={\"yes\" if age_h > 24 else \"no\"}')
   else:
       print('STALE=yes')
   conn.close()
   "
   ```

2. **If data is >24h old** (and user didn't pass `--skip-update`), run the full update pipeline:
   ```bash
   uv run python scripts/update_all.py --universe sp500
   ```
   This takes 10-20 minutes. Warn the user and keep them informed of progress.
   If data is fresh (<24h), skip and tell the user: "Data is fresh (Xh old), skipping update."

3. **Start dashboard server** (if not already running) and open browser:
   ```bash
   # Check if already running
   lsof -ti:8050 >/dev/null 2>&1 || (uv run python scripts/dashboard_server.py --port 8050 &)
   sleep 2
   open http://127.0.0.1:8050
   ```
   Tell user: "Dashboard live at http://localhost:8050"

## Phase 2: Portfolio Sell-Signal Scan

For each holding in `~/vault/finance/notes/portfolio/portfolio.md`, run parallel subagents to analyze:

**Launch one Agent per holding** (use `subagent_type: "general-purpose"`, run in parallel). Each agent should:

1. Read the company analysis file `~/vault/finance/notes/companies/TICKER.md` for the original thesis
2. Query the database for ALL current model valuations:
   ```bash
   uv run python -c "
   import sqlite3, json
   conn = sqlite3.connect('data/stock_data.db')
   conn.row_factory = sqlite3.Row
   rows = conn.execute('''
       SELECT model_name, fair_value, current_price, upside_pct, confidence, margin_of_safety, timestamp
       FROM valuation_results WHERE ticker = 'TICKER' AND suitable = 1
       ORDER BY model_name
   ''').fetchall()
   for r in rows:
       print(f\"{r['model_name']:25s} FV={r['fair_value']:>10.2f}  Price={r['current_price']:>10.2f}  Upside={r['upside_pct']:>+7.1f}%  Conf={r['confidence'] or 'N/A'}  Age={r['timestamp']}\")
   conn.close()
   "
   ```
3. Check for **sell signals** — return a structured assessment:
   - **Thesis broken?** Compare original thesis catalysts/assumptions vs current data. Flag if key assumptions no longer hold.
   - **Models say overvalued?** If AutoResearch AND majority of GBM models show negative upside, flag it.
   - **Stop-loss hit?** If current price is >25% below purchase price or thesis invalidation price.
   - **Better opportunity?** If the position's model upside (AutoResearch + GBM) is near zero while watchlist stocks show strong upside.
   - **Concentration risk?** If position is >20% of portfolio.

4. Return a **one-paragraph verdict**: HOLD / TRIM / SELL / ADD, with the key reason.

**IMPORTANT**: Trust AutoResearch model most (Spearman 0.54, best calibrated). GBM models are secondary. DCF/RIM are sanity checks only — don't sell just because RIM is bearish (it has known anti-growth bias).

## Phase 3: Watchlist Opportunity Scan

1. **Query top opportunities** from the database — stocks with highest AutoResearch upside that are on the watchlist:
   ```bash
   uv run python -c "
   import sqlite3
   conn = sqlite3.connect('data/stock_data.db')
   # AutoResearch top picks
   rows = conn.execute('''
       SELECT ticker, fair_value, current_price, upside_pct, confidence
       FROM valuation_results
       WHERE model_name = 'autoresearch' AND suitable = 1
       ORDER BY upside_pct DESC
       LIMIT 30
   ''').fetchall()
   for r in rows:
       print(f\"{r[0]:8s} FV={r[1]:>10.2f}  Price={r[2]:>10.2f}  Upside={r[3]:>+7.1f}%  Conf={r[4]}\")
   conn.close()
   "
   ```

2. **Cross-reference with watchlist** (`~/vault/finance/notes/portfolio/watchlist.md`): highlight stocks that appear in both the watchlist AND the top AutoResearch picks.

3. **Check which top picks need fresh LLM analysis.** Query existing analyses:
   ```bash
   uv run python -c "
   import sqlite3
   conn = sqlite3.connect('data/stock_data.db')
   rows = conn.execute('''
       SELECT ticker, timestamp, json_extract(details_json, '$.verdict') as verdict
       FROM valuation_results WHERE model_name = 'llm_deep_analysis'
   ''').fetchall()
   for r in rows:
       print(f'{r[0]:8s} {r[2]:6s} {r[1]}')
   conn.close()
   "
   ```
   Skip tickers that have an LLM analysis less than 7 days old. Also skip speculative/illiquid tickers (market cap < $5B, ADV < 1M).

4. **For the top 5-8 opportunities without fresh analysis**, launch parallel subagents. Each subagent MUST follow the FULL methodology in `.claude/commands/research-company.md` — all 9 steps including web search, variant perception, scenario analysis, and DB write. Pass this prompt to each agent:

   > "You are an investment analyst. Read and follow the FULL methodology in `/path/to/invest/.claude/commands/research-company.md` to produce a deep company analysis for **TICKER**. Follow ALL steps 0-9. Save to `~/vault/finance/notes/companies/TICKER.md`. Today is {DATE}. Be honest and critical."

5. For tickers that already have a fresh LLM analysis, just read the existing `~/vault/finance/notes/companies/TICKER.md` and summarize the verdict.

6. Each stock in the brief should show: **ticker, verdict (BUY/WATCH/PASS), expected value %, entry price, one-line variant perception, next catalyst**.

## Phase 4: The Brief

Present the final output as a single, dense message. Format:

```
## SELL SIGNALS (action required)
| Ticker | Signal | Models Bearish | Action | Reason |
(only if any positions need action — if all clear, say "No sell signals.")

## PORTFOLIO HEALTH
| Ticker | Price | AutoRes Upside | GBM Opp 3y | Thesis Status |
(one row per holding, sorted by concern level)

## TOP OPPORTUNITIES (from watchlist)
| # | Ticker | AutoRes Upside | Models Bullish | Key Signal | Action |
(top 3-5, ranked by conviction)

## SUGGESTED ACTIONS
1. Numbered list of concrete actions: "Sell X shares of TICKER at ~$PRICE" or "Buy $AMOUNT of TICKER"
   Size buys by conviction under the portfolio rules (15% single-name cap, 35% sector cap), not a formula.
```

## Important Rules

- **No fluff.** Every sentence must carry information. No "Let me analyze..." or "Based on my analysis..."
- **Lead with danger.** Sell signals first, always. If something is about to blow up, the user needs to know immediately.
- **Trust AutoResearch > GBM > DCF/RIM.** Don't average them equally. AutoResearch has 0.54 Spearman correlation — it's the best predictor.
- **Read past notes.** Check past company analysis files and transaction journals. The user has context and reasoning there — build on it, don't ignore it.
- **Portfolio context matters.** A 2% position with -10% upside is not urgent. A 20% position with broken thesis IS urgent.
- **Always use `uv run python`** for all commands.
- **Parallel agents.** Launch all holding-analysis agents in parallel, and all opportunity agents in parallel. Don't serialize what can be parallelized.
- **Skip BTC** — no model coverage for crypto. Just note it exists.
