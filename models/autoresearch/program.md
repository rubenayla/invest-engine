# autoresearch — stock return prediction

Autonomous AI research loop for building the best model to predict
approximate maximum expected returns in a 2-year forward window.

## Setup

1. **Agree on a run tag** with the user (e.g. `mar15`). Branch: `models/autoresearch/<tag>`.
2. **Create the branch**: `git checkout -b models/autoresearch/<tag>` from current HEAD.
3. **Read the in-scope files**:
   - `models/autoresearch/evaluate.py` — fixed harness: data loading, target computation, scoring. **Do not modify.**
   - `models/autoresearch/train.py` — the file you modify. Model, features, training loop.
4. **Run baseline**: `cd autoresearch && uv run python train.py > run.log 2>&1`
5. **Initialize results.tsv** with the header + baseline result.
6. **Confirm and go.**

## The data

- **Source**: SQLite database at `data/stock_data.db`.
- **Fundamentals**: ~20K quarterly snapshots (2006–2025), 712 tickers, ~50 financial metrics each.
- **Prices**: daily OHLCV for 791 tickers (2004–2026).
- **Target**: `peak_return_2y` = `max(close[t:t+504 trading days]) / close[t] - 1`.
  This is the approximate maximum return you could achieve buying at snapshot date
  and selling at the best point within 2 years.
- **Train**: snapshots before 2022-01-01. **Test**: snapshots 2022-01-01 to 2024-01-01.
- Price features (momentum, volatility, distance from highs/lows) are pre-computed.

## What you CAN do

- Modify `models/autoresearch/train.py` — **this is the only file you edit.** Everything is fair game:
  - Model choice (LightGBM, CatBoost, neural nets, ensembles, linear models, anything)
  - Feature engineering (lags, rolling stats, cross-sectional ranks, interactions, embeddings)
  - Hyperparameter tuning
  - Training strategy (cross-validation, sample weighting, target transforms)
  - Use any dependency in `pyproject.toml`: lightgbm, catboost, scikit-learn, torch, scipy, numpy, pandas

## What you CANNOT do

- Modify `evaluate.py`. It contains the fixed data split, target computation, and scoring.
- Install new packages beyond what's in `pyproject.toml`.
- Use future-looking information (no features computed from data after snapshot_date).
- Hardcode test set answers or overfit to the specific test period.

## The metric

**Spearman rank correlation** between predicted and actual peak 2-year returns.
Higher is better. A perfect ranker scores 1.0. Random is ~0.0.

Secondary metrics (for diagnostics, not optimization):
- `decile_spread`: top-decile actual mean − bottom-decile actual mean
- `top_decile_mean`: mean actual peak return of stocks you'd rank highest
- `hit_rate_top_q`: % of top-quintile picks that beat median

**The goal: get the highest Spearman correlation.** Everything else is diagnostic.

## Time budget

Training + prediction must complete within **120 seconds**. Data loading time is excluded
from this budget (it's ~30-60s of I/O). If a run exceeds 120s of model time, it's a failure.

## Output format

The script prints a summary:

```
---
spearman:         0.234567
decile_spread:    0.4321
top_decile_mean:  0.8765
hit_rate_top_q:   0.6543
n_scored:         1234
training_seconds: 45.2
```

Extract the key metric: `grep "^spearman:" run.log`

## Logging results

Log to `results.tsv` (tab-separated). Header + 5 columns:

```
commit	spearman	training_s	status	description
```

1. git commit hash (short, 7 chars)
2. spearman correlation (e.g. 0.234567) — use 0.000000 for crashes
3. training seconds (e.g. 45.2) — use 0.0 for crashes
4. status: `keep`, `discard`, or `crash`
5. short text description of what this experiment tried

Do NOT commit results.tsv — leave it untracked.

## The experiment loop

LOOP FOREVER:

1. Look at the git state and results so far.
2. Think of a hypothesis — what change might improve Spearman correlation?
3. Modify `models/autoresearch/train.py` with the idea.
4. `git commit` the change.
5. Run: `cd /Users/rubenayla/repos/invest/autoresearch && uv run python train.py > run.log 2>&1`
6. Extract: `grep "^spearman:\|^training_seconds:" run.log`
7. If grep is empty → crash. Run `tail -n 50 run.log`, attempt fix or move on.
8. Log to results.tsv.
9. If spearman **improved** → keep commit, advance branch.
10. If spearman **same or worse** → `git reset --hard HEAD~1` (discard).

## Research directions to explore

These are suggestions — you're free to try anything:

- **Feature engineering**: lag features (QoQ, YoY changes), rolling stats, cross-sectional percentile ranks, sector-relative metrics, interaction terms
- **Target transforms**: log(1 + return), rank-based targets, winsorized targets
- **Model architectures**: CatBoost, XGBoost-style, neural nets (tabular), ensemble stacking
- **Sample weighting**: weight recent samples higher, or weight by inverse sector frequency
- **Sector/industry encoding**: target encoding, leave-one-out encoding, embeddings
- **Multi-task learning**: predict both level and rank simultaneously
- **Outlier handling**: winsorize extreme targets, robust loss functions (Huber, quantile)
- **Temporal features**: time-since-IPO, market regime indicators, VIX interactions

## Constraints

- **Simplicity criterion**: if two approaches give similar Spearman, prefer the simpler one.
- **No overfitting**: the test set is out-of-sample (2022-2023). If your training metric is great but test Spearman drops, you're overfitting.
- **NEVER STOP**: do not ask the human to continue. Run experiments indefinitely until interrupted.
