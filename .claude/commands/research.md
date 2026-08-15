# research TICKER — Deep dive on one company

Full investment research: news, variant perception, financials, scenarios, verdict.
Saves to `~/vault/finance/notes/companies/TICKER.md` and `valuation_results` DB (model: `llm_deep_analysis`).

---

## STEP 1: Refresh Stock Data

**Before starting research, update the stock's price and fundamental data in the database.**

```bash
uv run python -c "
import sys; sys.path.insert(0, '.')
from scripts.data_fetcher import AsyncStockDataFetcher, StockDataCache
fetcher = AsyncStockDataFetcher()
data = fetcher.fetch_stock_data_sync('{TICKER}')
if data and data.get('info', {}).get('currentPrice'):
    cache = StockDataCache()
    cache.save_stock_data('{TICKER}', data)
    print(f'Updated {data[\"info\"].get(\"longName\", \"{TICKER}\")}: \${data[\"info\"][\"currentPrice\"]}')
else:
    print('Warning: could not fetch data, proceeding with existing DB data')
"
```

If this fails (SSL error, rate limit), proceed anyway — the analysis can use existing DB data + live yfinance queries in STEP 8.

---

## Understand the Business & Situation — STEPS 2-5 (primer first, then primary sources, then narrative)

**This step comes FIRST. Before touching any numbers, understand what the business actually does, what's happening with it, and how the news fits — from the company itself, not from reporters.**

### STEP 2: Business Primer (Plain English)

Before any earnings reading, before any ratios, write a plain-English primer of the company as if explaining it to a smart friend who has never heard of it. **This is non-optional and must be written for every research run, even for well-known names.** Numbers without this context are noise.

Structure it as **five** short paragraphs (no jargon, no acronyms without spelling them out the first time):

1. **Core business today** — what they actually sell, who pays them, how they make money. Concrete examples of products/services and customers. If revenue is split between segments, name the biggest 2-3 and explain each.

2. **Why customers choose them (the value proposition)** — what specific problem does the product solve, and why does the customer pick it over the next-best alternative? Compare directly to the alternatives ("open surgery vs robotic", "Postgres vs Oracle DB", "cash vs credit card", "Word vs Google Docs"). Describe the *concrete improvement* the customer gets in terms a non-customer would understand: "incisions go from 20 cm to 1 cm, recovery from 6 weeks to 2", "query 10× faster at 1/3 the compute cost", "tracks 200 metrics the legacy system can't see". If the product is technical, explain what it *does* mechanically — wristed instruments inside the body, motion-scaling, tremor filtering, etc. — not just that it's "premium" or "better." A reader should finish this paragraph and understand why a rational customer would pay for the product instead of the cheaper/older alternative.

3. **Where they want to grow** — the explicit strategic bets management is making. New products, new geographies, new customer types, M&A direction. What does success look like in 3-5 years?

4. **What could go wrong (the business risks, not the stock risks)** — competitive threats, structural industry shifts, customer concentration, execution risks on the growth bets, regulatory or technology disruption. These are the things that would damage the *business*, separate from valuation.

5. **How to think about it vs. peers/category** — one or two sentences situating the company. *This* is where investor-shorthand belongs ("razor-and-blade compounder", "infrastructure vs data SaaS", "growth challenger eating share") — but only as a label for everything you just explained above, not as a substitute for explaining.

**Rule 1 — Explain the product, don't label it.** Phrases like "razor-and-blade installed-base compounder", "high-quality compounder", "asset-light SaaS", "moat", "platform business" are *investor labels* that summarize a business after you already understand it. They do **not** explain it. In paragraphs 1–2, describe the actual product, the actual customer behavior, and the actual reason the product wins, in terms a smart non-investor friend would understand. Save the labels for paragraph 5.

**Rule 2 — Value proposition is mandatory.** If a reader cannot answer **both** "what does this company DO" *and* "why would a customer pick this over the alternative" in one sentence each after reading the primer, it failed. Rewrite. Most failure modes are skipping the *why customers buy* part — describing the product's features without explaining the concrete benefit that drives adoption.

This primer goes at the **top** of the output file under a `## Business Primer` heading, before Situation Summary.

### STEP 3 (MANDATORY): Read the Primary Source

If the company reported earnings in the last 90 days, you MUST fetch and read the actual materials before writing anything:
1. **Earnings press release** from `investor.<company>.com` (or IR equivalent) — WebFetch this page.
2. **Earnings call transcript or prepared remarks** — look for "Q&A" and "prepared remarks."
3. Latest **10-Q or 10-K** segment disclosures if available (geographic + product segment revenue breakdowns).

From these primary sources, extract and write down:
- **Every quantified headwind** management disclosed (basis points, dollar amounts, percentage impacts). List them ranked by size.
- **Segment and geographic revenue breakdowns** and which specific segments/regions moved.
- **Margin commentary** — gross margin, operating margin changes YoY and QoQ, with the reasons management gave.
- **Customer concentration** — any large customer losses, renewals pushed, or federal/government exposure.
- **Guidance changes** — what was raised, what was cut, what was held. Decompose by segment if disclosed.

**RULE: If you cannot fetch the IR page (tool failure, paywall), explicitly say so in the output and flag the analysis as "news-summary-only" with LOWER confidence.**

### STEP 4: Map the News Narrative

Now use web search to find:
1. **Recent news** (last 30–90 days): earnings surprises, guidance changes, management turnover, M&A, lawsuits, regulatory actions, activist investors.
2. **The market narrative**: What does Wall Street currently believe about this stock? Is it a "consensus long" or contrarian?
3. **Sector context**: How is the industry doing? Tariffs, regulation, interest rate sensitivity, competitive shifts?
4. **Upcoming events**: Next earnings date, FDA decisions, contract renewals, product launches, analyst days — anything dateable in the next 6 months.

### STEP 5: Cross-Check (MANDATORY)

Compare what management disclosed vs. what the news is leading with:
- Does the news headline risk match the **largest** headwind management disclosed, or a smaller one?
- If there's a mismatch (e.g. news says "Iran war" but CFO cited federal shutdown as the bigger issue), your analysis must reflect management's size ordering, not the media's framing.
- Write down at least one risk that is **NOT in the news headlines but is in the primary source**. If you cannot find one, your STEP 3 reading was too shallow — go back and reread.

**Output a 3-5 sentence "Situation Summary"** — what's the story right now, as told by the company itself, with the news narrative as context.

---

## STEP 6: Variant Perception (THE MOST IMPORTANT STEP)

Before doing any valuation, answer Steinhardt's 4 questions:

1. **The Idea**: What is the specific investment opportunity?
2. **The Consensus View**: What does the market currently believe? (Check analyst ratings, short interest, institutional ownership, recent price action)
3. **Your Variant Perception**: Where specifically does your view differ from consensus, and WHY? What do you see that the market doesn't?
4. **The Trigger Event**: What specific, dateable catalyst will force the market to re-rate?

**If you cannot articulate a variant perception, there is no edge. Say so honestly.**

Reverse-engineer what the current price implies about future earnings/growth. Compare that to what you think will actually happen. The gap IS the opportunity.

---

## STEP 7: Gather Model Data (Database)

Query the PostgreSQL database for ALL valuation models (use `invest.data.db.get_connection()`):

```sql
SELECT model_name, fair_value, current_price, upside_pct, confidence, timestamp
FROM valuation_results
WHERE ticker = '{TICKER}'
ORDER BY upside_pct DESC;
```

Record: which models are bullish vs bearish. Note extreme divergences (>50pp spread).
**CRITICAL: Check `timestamp` for each model.** If a model is >7 days old, compare its `current_price` to today's live price. If they diverge >5%, the model's upside % is INVALID — recalculate using the model's fair_value vs today's price, and note the discrepancy in the output.
Known biases: DCF overvalues cyclicals at peak earnings, RIM undervalues asset-light companies. GBM and autoresearch are most reliable for return predictions.

---

## STEP 8: Pull Live Financials (yfinance)

```python
import yfinance as yf
t = yf.Ticker('{TICKER}')

# Income statement (3-5 year trend)
print(t.income_stmt.loc[['Total Revenue', 'Net Income', 'EBITDA', 'Operating Income']])

# Balance sheet
print(t.balance_sheet.loc[['Total Assets', 'Total Debt', 'Stockholders Equity', 'Cash And Cash Equivalents']])

# Cash flow
print(t.cashflow.loc[['Operating Cash Flow', 'Free Cash Flow', 'Capital Expenditure']])

# Key ratios
info = t.info
for k in ['trailingPE', 'forwardPE', 'priceToBook', 'priceToSalesTrailing12Months',
           'debtToEquity', 'returnOnEquity', 'returnOnAssets', 'profitMargins',
           'operatingMargins', 'grossMargins', 'dividendYield', 'payoutRatio',
           'beta', 'marketCap', 'enterpriseValue', 'currentRatio', 'quickRatio',
           'revenueGrowth', 'earningsGrowth', 'sector', 'industry',
           'shortPercentOfFloat', 'heldPercentInsiders', 'heldPercentInstitutions',
           'targetMeanPrice', 'targetLowPrice', 'targetHighPrice', 'numberOfAnalystOpinions',
           'recommendationKey']:
    print(f"{k}: {info.get(k, 'N/A')}")
```

**THE IRON RULE**: Before claiming any trend ("declining revenue", "improving margins"), verify with the actual data. Check 3-5 year trends.

Calculate: Revenue CAGR (3yr), Earnings CAGR (3yr), FCF yield (FCF/market cap), Net debt/EBITDA.

---

## STEP 9: Business Quality Assessment

Score each dimension 1-5 with specific evidence:

| Dimension | What to assess |
|-----------|---------------|
| **Moat (1-5)** | Pricing power, switching costs, network effects, scale advantages, brand. Is it DURABLE? |
| **Management (1-5)** | Capital allocation track record (ROIC vs WACC), M&A history, insider buying/selling, forecasting accuracy, transparency in bad times (Fisher point #14) |
| **Profitability (1-5)** | Margins vs peers, ROE sustainability, capital intensity, margin trajectory |
| **Balance Sheet (1-5)** | Leverage appropriate for industry, interest coverage, debt maturity profile, cash generation vs obligations |
| **Growth Runway (1-5)** | TAM expansion, new products/markets, organic vs acquired growth, law of large numbers risk |

**Total: X/25** — Below 15 is a yellow flag. Below 10 is a red flag.

---

## STEP 10: Inflection Point Check

Is this company at or near a fundamental inflection? The best investments come at turning points. Check for:

- **Turnaround**: Recovering from setbacks with identifiable, correctable causes?
- **Hidden segment growth**: Fast-growing product/segment masked by larger flat business?
- **Demand breakthrough**: New distribution, geographic expansion, regulatory approval?
- **Profitability inflection**: Crossing into strong profitability as operating leverage kicks in?
- **Corporate event**: Spin-off, activist involvement, new management with a clear plan?

**Timing principle**: Don't try to buy absolute bottoms. Look for OBSERVABLE EVIDENCE that the inflection has begun. Enter after initial recovery starts — you trade some upside for dramatically reduced value-trap risk.

If no inflection is evident, the stock needs to be cheap enough on a static basis to justify buying into a "more of the same" scenario.

---

## STEP 11: Scenario Table (TIED TO REAL EVENTS)

Each scenario must be driven by specific, identifiable conditions — not generic "things go well/badly."

For each scenario, decompose the return into **earnings growth** + **multiple change**:

| Scenario | Prob | Earnings Driver | Multiple Driver | Target | Return |
|----------|------|----------------|-----------------|--------|--------|
| **Bull** | X% | {specific: revenue acceleration from X, margin expansion from Y} | {re-rating because Z} | $X | +X% |
| **Base** | X% | {specific: continuation of current trends} | {stable multiple} | $X | +X% |
| **Bear** | X% | {specific: what goes wrong — loss of customer, margin compression from X} | {de-rating because Y} | $X | -X% |

**Expected value** = sum(probability x return)

**Thesis quality check**: If your upside depends entirely on multiple expansion (not earnings growth), the thesis is LOW QUALITY. Flag it.

**Pre-mortem**: What specific condition would break your thesis entirely? Define the "I was wrong" signal upfront.

---

## STEP 12: Setup & Timing Assessment

Even a great company is a bad buy at the wrong price/time. Check:

| Factor | Check | Status |
|--------|-------|--------|
| **Crowdedness** | Is it a consensus hedge fund long? (Check top holders) | Crowded / Uncrowded |
| **Short interest** | High = squeeze potential but also consensus negative | X% |
| **Technical position** | RSI, distance from 52w high/low, relative performance vs sector | Oversold / Neutral / Overbought |
| **Catalyst proximity** | Is there a dateable catalyst in 0-6 months? | Yes (date) / No |
| **Recent price action** | Has it already run 10%+ ahead of the catalyst? | |

**Favor buying now when**: uncrowded, near-term catalyst, observable inflection evidence, stock hasn't run yet.
**Favor waiting when**: crowded, catalyst is 6+ months out, technically overbought, already appreciated significantly.

---

## STEP 13: Final Verdict

| Criterion | Assessment |
|-----------|-----------|
| **Variant Perception?** | Clear / Weak / None — what do you see that the market doesn't? |
| **Undervalued?** | Model consensus direction and magnitude |
| **Quality?** | Business quality score (X/25) |
| **Inflection?** | Is there an identifiable turning point? |
| **Catalyst?** | Specific dateable event within 6 months? |
| **Risk/Reward?** | Expected value from scenario table |
| **Setup?** | Entry timing favorable? |
| **Conviction** | HIGH / MEDIUM / LOW |

**Final verdict**: BUY / WATCH / PASS — with clear rationale

**If BUY**: At what price? Full position or scale in? What's the thesis-break signal?
**If WATCH**: What would change your mind? What price/event triggers a BUY?
**If PASS**: Why? Is it permanently uninvestable or just wrong timing?

### Public-vs-private content rule (MANDATORY)

The file you save under `~/vault/finance/notes/companies/{TICKER}.md` lives in the **public**
invest repo. It must contain ONLY generic research that anyone could write,
NOT decisions tied to the user's personal portfolio.

**Belongs in the public file** (write these freely):
- Scenarios, quality scores, valuations, model EVs, BUY/WATCH/PASS verdict
- Generic conditional language: "Existing holders: trim 30-50%", "Would
  upgrade to BUY at $X", "If already long: consider trimming"
- Watchlist-style entry/exit prices that anyone could act on

**Does NOT belong in the shared research file** (keep it in your private notes — see below):
- Specific cash amounts of your own position, or its weight in your portfolio
- Specific share counts you hold
- Your cost basis or the dates you bought
- Profit and loss figures, realised or unrealised
- "Position Context" or "Personal Position" sections describing what the
  user owns

If the verdict naturally references personal context (e.g. you'd like to
say "given your existing 16% position, don't add"), write a SEPARATE
decision note at `$INVEST_PRIVATE_NOTES/positions/{TICKER}.md` with the
personal-decision content, and keep the public file generic. Do not let
the two leak into each other.

---

## STEP 14: Per-ticker forecast track record (MANDATORY — comes before the overwrite in STEP 15)

Every name you form a real, actionable view on keeps a `~/vault/finance/notes/companies/{TICKER}/history.md` — an append-only **forecast track record** (oldest first, newest appended at the end). This is the standard, not an opt-in. Its purpose is calibration: record what we predicted, what actually happened, and what the gap says about how *we* forecast — so we stop being wrong the same way twice. `SQM/history.md` is the reference shape.

**Do this before the OVERWRITE in STEP 15**, because the prior call is the thing you are grading:

1. **Capture the prior call.** From the existing `{TICKER}.md` / `{TICKER}/thesis.md`, read the prior verdict, conviction, scenario targets, and the explicit "Thesis breaks if…" / upgrade-trigger lines.
2. **Promote to folder layout if still flat:** `git mv ~/vault/finance/notes/companies/{TICKER}.md ~/vault/finance/notes/companies/{TICKER}/thesis.md`, then create `history.md`. (Skip if already a folder.)
3. **Append a reconciliation entry** using this shape:

```markdown
## YYYY-MM-DD — Reconciliation: {one-line what changed}. ${price}

**What actually happened.** {The facts since the prior call — earnings prints, realized vs. predicted numbers, catalysts hit/missed, price move with dates.}

**Scorecard.** Fundamental call: {right/wrong, how decisively}. Near-term stock call: {right/wrong}. Net: {one line}.

**Self-pattern (the reason this file exists).** {What the hit/miss reveals about *our* process — not just "we were wrong." Is this a repeat of an earlier error family? What should we weigh differently for names like this? Make it transferable.}

**Current expectation (to reconcile next time).** {The new call, restated as a falsifiable prediction with dated/numeric triggers and thesis-break lines — so the next entry has something concrete to grade.}
```

If this is the **first** entry for a brand-new name (no prior call to grade), still create the file and log the initial call: the verdict, the falsifiable triggers, and a "Current expectation (to reconcile next time)" block. The grading starts next run.

**Only skip this step** when the run is a routine refresh that left the verdict, conviction, and triggers unchanged AND nothing material happened since the last entry. When in doubt, append — a slightly noisy track record beats a lost data point on our own calibration.

---

## STEP 15: Write the Note (output format)

**Save to `~/vault/finance/notes/companies/{TICKER}.md`** — this is the SINGLE source of truth for each company's analysis.
If the file already exists, STEP 14 has already captured and graded the prior call, so now OVERWRITE the thesis with the new analysis (the old version is in git history).
If the ticker has supplementary files, they live in `~/vault/finance/notes/companies/{TICKER}/` (subdirectory) — don't touch those except `history.md`, which STEP 14 appends to.

Template:

```markdown
# {Company Name} ({TICKER})

**Sector:** {sector} | **Industry:** {industry}
**Price:** ${price} ({YYYY-MM-DD}) | **Market Cap:** ${cap}
**Analysis Date:** {YYYY-MM-DD}

## Business Primer

**What they do today.** {Plain-English description of the core business — what they sell, who pays them, how revenue is split across the biggest segments. Concrete products and customers. No jargon, spell out acronyms on first use.}

**Why customers choose them (the value proposition).** {What concrete problem does the product solve, compared to the next-best alternative? Describe the actual mechanism — what the product *does* that makes the customer prefer it. E.g., "open surgery → 20cm incision and 6-week recovery; da Vinci → 1cm incisions, 3D vision with 10× magnification, wristed instruments that can suture inside the body, 1-week recovery." Avoid investor-shorthand here ("moat", "compounder", "high-quality") — say what the product actually does that makes customers pay.}

**Where they want to grow.** {The explicit strategic bets — new products, new geographies, new customer types, M&A direction. What success looks like in 3-5 years.}

**What could go wrong (business risks).** {Competitive threats, structural industry shifts, customer concentration, execution risks on the growth bets, regulatory or tech disruption. The things that damage the *business*, separate from valuation.}

**How to think about it.** {One or two sentences situating the company in its category — "infrastructure vs. data SaaS riding on infrastructure", "legacy incumbent in a turnaround vs. growth challenger eating share", etc. Frames everything that follows.}

## Situation Summary
{3-5 sentences: what's happening with this company RIGHT NOW. Recent news, narrative, sector dynamics.}

## Variant Perception
- **Consensus view:** {what the market believes}
- **Our view:** {where we differ and why}
- **Trigger:** {what event forces re-rating}

## Financial Snapshot

| Metric | Value | 3yr Trend |
|--------|-------|-----------|
| Revenue | $XB | {CAGR}% |
| Net Income | $XB | {CAGR}% |
| FCF | $XB | {trend} |
| ROE | X% | {trend} |
| D/E | X | {trend} |
| FCF Yield | X% | |

## Valuation Models

| Model | Fair Value | Upside | Confidence | Run Date |
|-------|-----------|--------|------------|----------|
| ... | ... | ... | ... | YYYY-MM-DD |

*Models older than 7 days may use stale prices — compare model's current_price to today's price before trusting upside %.*

**Model consensus:** {summary — which models agree/disagree and why}

## Business Quality (X/25)

| Dimension | Score | Notes |
|-----------|-------|-------|
| Moat | /5 | {specific evidence} |
| Management | /5 | {capital allocation, insider activity, transparency} |
| Profitability | /5 | {margins vs peers, trajectory} |
| Balance Sheet | /5 | {leverage, coverage, trajectory} |
| Growth | /5 | {runway, organic vs acquired} |

## Inflection Point
{Is there one? What evidence? Or is this a static value play?}

## Bull Case
{3-5 bullets — specific, not generic}

## Bear Case
{3-5 bullets — what actually kills the thesis.
**At least one bullet must be a risk the company disclosed but news headlines under-covered** (from the STEP 3 primary-source reading). If every bear bullet matches the top news narrative, the research is shallow and the verdict should be downgraded or delayed.}

## Scenario Table

| Scenario | Prob | Earnings Driver | Multiple Driver | Target | Return |
|----------|------|----------------|-----------------|--------|--------|
| Bull | X% | {specific} | {specific} | $X | +X% |
| Base | X% | {specific} | {specific} | $X | +X% |
| Bear | X% | {specific} | {specific} | $X | -X% |

**Expected value: +X%**
**Thesis breaks if:** {specific condition}

## Setup & Timing

| Factor | Status |
|--------|--------|
| Crowdedness | |
| Short interest | |
| Technical position | |
| Next catalyst | {date} |
| Recent price action | |

## Verdict

**{BUY / WATCH / PASS}** — Conviction: {HIGH/MEDIUM/LOW}

{2-3 sentence rationale linking variant perception, quality, catalyst, and setup}

**If BUY:** Entry at $X, scale-in plan (generic — no personal share counts), thesis-break at $X
**If WATCH:** Would upgrade on {specific condition}

<!-- Do NOT add a "Position Context" / "Personal Position" / "My Holding"
     section here. The public file is generic research only. Personal
     position size, cost basis, P&L, and share counts go to
     $INVEST_PRIVATE_NOTES/positions/{TICKER}.md (or are tracked in
     portfolio.md / notes/transactions/). See the Public-vs-private
     content rule in STEP 13 above. -->
```

---

## STEP 16: Save to Database

After writing the .md file, save the verdict to `valuation_results` (model
`llm_deep_analysis`). The dashboard's LLM column reads only this row, and its
default order ranks by it, so a note without this row is invisible there.

```bash
uv run python scripts/save_llm_verdict.py {TICKER} --price {CURRENT_PRICE} \
    --verdict {BUY/WATCH/PASS} --conviction {HIGH/MEDIUM-HIGH/MEDIUM/LOW} \
    --ev {EXPECTED_VALUE_PCT} --quality {QUALITY_SCORE_OUT_OF_25} \
    --entry {ENTRY_PRICE} --thesis-break {THESIS_BREAK_PRICE} \
    --bull {BULL_PROB}:{BULL_TARGET}:{BULL_RETURN_PCT} \
    --base {BASE_PROB}:{BASE_TARGET}:{BASE_RETURN_PCT} \
    --bear {BEAR_PROB}:{BEAR_TARGET}:{BEAR_RETURN_PCT} \
    --variant "{ONE_LINE_VARIANT_PERCEPTION}"
```

Probabilities are 0-1 (0.25 for 25%). Add `--dry-run` to see the row first. The DB
is on y540; on the Mac the script needs the tunnel on localhost:5433
(`ssh -fN -L 5433:localhost:5432 y540-ubuntu`). If the tunnel cannot be opened, add
the exact command to `~/vault/finance/invest-analysis/tasks.md` so the row gets
written when y540 is back — the note alone is not enough.

**This step is MANDATORY.** Every deep analysis must be persisted to the database so the dashboard and other tools can access it.

---

## STEP 17: Sync the Watchlist (MANDATORY if the ticker is on it)

`~/vault/finance/notes/portfolio/watchlist.md` is a curated summary that goes stale the moment a deep analysis changes a verdict. After saving the note + DB row, check whether `{TICKER}` already has a line in the watchlist:

```bash
grep -n "companies/{TICKER}.md" ~/vault/finance/notes/portfolio/watchlist.md
```

- **If a line exists**, update it in place to match the new verdict, conviction, quality score, EV %, and entry/thesis-break prices from this run. Preserve the thesis hook prose; only refresh the data fields and the verdict label. If the verdict flipped (e.g. WATCH→BUY), append a short `*(was WATCH on YYYY-MM-DD — upgraded.)*` note so the change is visible.
- **If no line exists** but the verdict is BUY or a notable WATCH, add a line in the appropriate section.
- Bump the file-level `Last updated YYYY-MM-DD` stamp at the top whenever you touch it.

The watchlist must never contradict the company note. A BUY in `~/vault/finance/notes/companies/{TICKER}.md` that still reads WATCH on the watchlist is a bug.

---

## STEP 18: Queue whatever this run says to look at next (MANDATORY if the analysis names one)

Deep analysis routinely surfaces a *different* name worth researching — a cheaper peer, a better structural expression of the same idea, a supplier or counterparty that captures more of the economics. Put it in the **`## Next to research`** section at the top of `~/vault/finance/notes/portfolio/watchlist.md`, in this run, as a bullet containing:

- **Ticker, company name, and the date it was queued**, plus what queued it (this run, and the thesis file if one applies).
- **Why it beats or complements the name just analysed** — the specific comparison, with figures.
- **The headline numbers** that make it interesting: price, market cap, the yield or multiple that matters for its category, distance from 52-week high.
- **What to settle before any position** — the two or three open questions whoever picks it up must answer first.
- **Any data caveat** the next run would otherwise trip on (broken yfinance fields, structures that make headline ratios meaningless, pre-merger or pre-spin statements).

Record no verdict, EV or quality score here — those appear when `/research` has actually been run on the name and it graduates to a normal watchlist line.

The reason this is a step rather than a habit: a "worth looking at next" left in a thesis file, in repo-root `history.md`, or in chat is invisible to the person choosing what to work on. The top of the watchlist is where that decision gets made.

---

## STEP 19: Repo-root history.md — cross-cutting insights (when the lesson generalizes beyond this one ticker)

Where STEP 14 is the per-name track record, repo-root `history.md` is the cross-ticker learning corpus. Append a dated entry whenever this run produced a takeaway a future session would want regardless of the ticker — that includes **first looks at notable names**, **thesis changes**, and **transferable insights** (sector dynamics, valuation methods, market mechanics). It already holds all three kinds; keep it that way.

**Log when any of these is true:**
- **Thesis change** — verdict flips (BUY ↔ WATCH ↔ PASS), conviction moves a full step, or a prior "Thesis breaks if…" signal actually triggered.
- **First look** — a name not previously covered, where the analysis surfaced a transferable lesson (how to value the category, a structural trap, a mispricing pattern) — not just "here's another BUY."
- **Insight** — anything cross-cutting you learned this run that generalizes beyond the one ticker.

**The only thing NOT worth logging:** a routine refresh that leaves the call unchanged AND taught you nothing new. Skipping those keeps the file a learning log, not a changelog. When in doubt, err toward logging — a slightly noisy history beats a lost lesson. The **Lesson** line is always the point: make it transferable to other names.

**Append to the end of repo-root `history.md`** (newest last). Use one of these title conventions so entries pull with a simple grep:

```markdown
## YYYY-MM-DD — Thesis change: {TICKER} {OLD_VERDICT}→{NEW_VERDICT} (conviction {OLD}→{NEW})
## YYYY-MM-DD — First look: {TICKER} ({Name}) — {VERDICT}/{CONVICTION}, {one-line hook}
## YYYY-MM-DD — Insight: {topic} (surfaced via {TICKER})
```

For a thesis change, use this body (it's the highest-value shape):

```markdown
**Believed (prior variant perception):** {what the old thesis bet on, and the trigger it was waiting for}
**Happened:** {what actually occurred — the facts that forced the change}
**Lesson (transferable):** {the generalizable takeaway — what to weigh differently next time, not just "we were wrong"}
**Surviving edge / re-upgrade triggers:** {what, if anything, still holds; what would flip the call back}
```

For first looks and insights, a tighter **Found/decided** + **Lesson (transferable)** + **Re-engage triggers** is fine. This is the same file used for all cross-cutting investigations; no separate file.
