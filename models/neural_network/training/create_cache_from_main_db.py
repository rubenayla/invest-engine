#!/usr/bin/env python3
"""
Populate the NN training cache from the main database.

Dense monthly sampling: one sample per stock per month (carry-forward
fundamentals) with forward **excess returns** vs SPY.

This produces ~80k+ samples vs ~6k from the old one-per-snapshot approach.
"""

import bisect
import sqlite3
import logging
from collections import defaultdict
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MAIN_DB = Path(__file__).parent.parent.parent / 'data' / 'stock_data.db'
TRAIN_DB = Path(__file__).parent / 'stock_data.db'

# Forward return horizons in trading days
HORIZONS = {'1m': 21, '3m': 63, '6m': 126, '1y': 252, '2y': 504}

# Month-end sample dates: 2006-01 to 2024-01
# (need fundamentals from ~2006 and >=2y forward prices → cutoff ~2024-01)
SAMPLE_START = '2006-01'
SAMPLE_END = '2024-01'

# Fundamental columns to carry forward (everything except id/asset_id/snapshot_date)
FUND_COLS = [
    'volume', 'market_cap', 'shares_outstanding',
    'pe_ratio', 'pb_ratio', 'ps_ratio', 'peg_ratio',
    'price_to_book', 'price_to_sales',
    'enterprise_to_revenue', 'enterprise_to_ebitda',
    'profit_margins', 'operating_margins', 'gross_margins', 'ebitda_margins',
    'return_on_assets', 'return_on_equity',
    'revenue_growth', 'earnings_growth', 'earnings_quarterly_growth', 'revenue_per_share',
    'total_cash', 'total_debt', 'debt_to_equity', 'current_ratio', 'quick_ratio',
    'operating_cashflow', 'free_cashflow',
    'trailing_eps', 'forward_eps', 'book_value',
    'dividend_rate', 'dividend_yield', 'payout_ratio',
    'price_change_pct', 'volatility', 'beta',
    'fifty_day_average', 'two_hundred_day_average',
    'fifty_two_week_high', 'fifty_two_week_low',
    'vix', 'treasury_10y', 'dollar_index', 'oil_price', 'gold_price',
]


def _generate_month_ends() -> list[str]:
    """Generate last-day-of-month date strings from SAMPLE_START to SAMPLE_END."""
    import calendar
    months = []
    year, month = int(SAMPLE_START[:4]), int(SAMPLE_START[5:7])
    end_year, end_month = int(SAMPLE_END[:4]), int(SAMPLE_END[5:7])
    while (year, month) <= (end_year, end_month):
        last_day = calendar.monthrange(year, month)[1]
        months.append(f'{year}-{month:02d}-{last_day:02d}')
        month += 1
        if month > 12:
            month = 1
            year += 1
    return months


def _find_price_idx(dates: list[str], target: str) -> int | None:
    """Find index of closest trading day on or before target date.

    Returns None if no valid date found.
    """
    idx = bisect.bisect_right(dates, target) - 1
    if idx < 0:
        return None
    return idx


def build_cache():
    logger.info(f'Main DB: {MAIN_DB}')
    logger.info(f'Training DB: {TRAIN_DB}')

    main = sqlite3.connect(str(MAIN_DB))
    main.row_factory = sqlite3.Row

    # --- 1. Create training DB schema (drops old data) ---
    from create_stock_database import create_database
    # Remove old training DB to start fresh
    if TRAIN_DB.exists():
        TRAIN_DB.unlink()
    create_database(str(TRAIN_DB))
    train = sqlite3.connect(str(TRAIN_DB))
    train.execute('PRAGMA journal_mode = WAL')
    train.execute('PRAGMA foreign_keys = ON')

    # --- 2. Copy assets ---
    assets = main.execute('SELECT id, symbol, sector, industry FROM assets').fetchall()
    asset_map = {}  # symbol -> train_id
    symbol_to_main_id = {}
    for a in assets:
        train.execute(
            'INSERT OR IGNORE INTO assets (symbol, asset_type, name, sector, industry) VALUES (?, ?, ?, ?, ?)',
            (a['symbol'], 'stock', None, a['sector'], a['industry'])
        )
        row = train.execute('SELECT id FROM assets WHERE symbol = ?', (a['symbol'],)).fetchone()
        asset_map[a['symbol']] = row[0]
        symbol_to_main_id[a['symbol']] = a['id']
    train.commit()
    logger.info(f'Copied {len(asset_map)} assets')

    # --- 3. Load price history for all tickers + SPY ---
    logger.info('Loading price history...')
    price_rows = main.execute(
        'SELECT ticker, date, close FROM price_history ORDER BY ticker, date'
    ).fetchall()

    price_dates: dict[str, list[str]] = defaultdict(list)
    price_closes: dict[str, list[float]] = defaultdict(list)
    for r in price_rows:
        price_dates[r['ticker']].append(r['date'])
        price_closes[r['ticker']].append(r['close'])

    spy_dates = price_dates.get('SPY', [])
    spy_closes = price_closes.get('SPY', [])
    if not spy_dates:
        raise RuntimeError('SPY price data not found in main DB. Run SPY import first.')
    logger.info(f'Loaded prices for {len(price_dates)} tickers (SPY: {len(spy_dates)} days)')

    # --- 4. Load fundamental_history: build per-ticker sorted snapshot index ---
    logger.info('Loading fundamental snapshots...')
    fund_rows = main.execute(f'''
        SELECT a.symbol, fh.snapshot_date, {", ".join(f"fh.{c}" for c in FUND_COLS)}
        FROM fundamental_history fh
        JOIN assets a ON fh.asset_id = a.id
        ORDER BY a.symbol, fh.snapshot_date
    ''').fetchall()

    # Per-ticker: sorted list of (date, col_values)
    fund_index: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for row in fund_rows:
        sym = row['symbol']
        snap_date = row['snapshot_date']
        vals = {c: row[c] for c in FUND_COLS}
        fund_index[sym].append((snap_date, vals))

    # Pre-extract just dates per ticker for bisect
    fund_dates: dict[str, list[str]] = {
        sym: [s[0] for s in snaps] for sym, snaps in fund_index.items()
    }
    logger.info(f'Loaded fundamentals for {len(fund_index)} tickers')

    # --- 5. Generate monthly samples ---
    month_ends = _generate_month_ends()
    tickers = sorted(fund_index.keys())
    logger.info(f'Generating samples: {len(month_ends)} months x {len(tickers)} tickers')

    inserted = 0
    skipped_no_fund = 0
    skipped_no_price = 0
    skipped_no_spy = 0
    skipped_no_forward = 0

    for mi, month_end in enumerate(month_ends):
        if mi % 12 == 0:
            logger.info(f'  Month {mi+1}/{len(month_ends)} ({month_end}), inserted={inserted}')
            train.commit()

        # SPY price at this month-end
        spy_idx = _find_price_idx(spy_dates, month_end)
        if spy_idx is None:
            skipped_no_spy += len(tickers)
            continue
        spy_price_now = spy_closes[spy_idx]

        # Pre-compute SPY forward prices for each horizon
        spy_forward: dict[str, float | None] = {}
        for horizon_name, days_ahead in HORIZONS.items():
            future_idx = spy_idx + days_ahead
            if future_idx < len(spy_dates):
                spy_forward[horizon_name] = spy_closes[future_idx]
            else:
                spy_forward[horizon_name] = None

        for ticker in tickers:
            # 1. Find most recent fundamental snapshot on or before month_end
            f_dates = fund_dates.get(ticker, [])
            if not f_dates:
                skipped_no_fund += 1
                continue
            f_idx = bisect.bisect_right(f_dates, month_end) - 1
            if f_idx < 0:
                skipped_no_fund += 1
                continue
            _, fund_vals = fund_index[ticker][f_idx]

            # 2. Get stock price at month-end
            s_dates = price_dates.get(ticker, [])
            s_closes = price_closes.get(ticker, [])
            if not s_dates:
                skipped_no_price += 1
                continue
            s_idx = _find_price_idx(s_dates, month_end)
            if s_idx is None:
                skipped_no_price += 1
                continue
            stock_price_now = s_closes[s_idx]
            if stock_price_now is None or stock_price_now <= 0:
                skipped_no_price += 1
                continue

            # 3. Compute forward excess returns for all horizons
            forward_excess = {}
            has_all = True
            for horizon_name, days_ahead in HORIZONS.items():
                # SPY forward
                spy_fwd = spy_forward[horizon_name]
                if spy_fwd is None or spy_fwd <= 0:
                    has_all = False
                    break
                spy_ret = (spy_fwd - spy_price_now) / spy_price_now

                # Stock forward
                future_idx = s_idx + days_ahead
                if future_idx >= len(s_dates):
                    has_all = False
                    break
                stock_fwd = s_closes[future_idx]
                if stock_fwd is None or stock_fwd <= 0:
                    has_all = False
                    break
                stock_ret = (stock_fwd - stock_price_now) / stock_price_now

                forward_excess[horizon_name] = stock_ret - spy_ret

            if not has_all:
                skipped_no_forward += 1
                continue

            # 4. Insert snapshot (use actual stock price, not from fundamental snapshot)
            train_asset_id = asset_map.get(ticker)
            if train_asset_id is None:
                continue

            train.execute('''
                INSERT OR IGNORE INTO snapshots (
                    asset_id, snapshot_date, current_price,
                    volume, market_cap, shares_outstanding,
                    pe_ratio, pb_ratio, ps_ratio, peg_ratio, price_to_book, price_to_sales,
                    enterprise_to_revenue, enterprise_to_ebitda,
                    profit_margins, operating_margins, gross_margins, ebitda_margins,
                    return_on_assets, return_on_equity,
                    revenue_growth, earnings_growth, earnings_quarterly_growth, revenue_per_share,
                    total_cash, total_debt, debt_to_equity, current_ratio, quick_ratio,
                    operating_cashflow, free_cashflow,
                    trailing_eps, forward_eps, book_value,
                    dividend_rate, dividend_yield, payout_ratio,
                    price_change_pct, volatility, beta,
                    fifty_day_average, two_hundred_day_average, fifty_two_week_high, fifty_two_week_low,
                    vix, treasury_10y, dollar_index, oil_price, gold_price
                ) VALUES (
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?, ?, ?, ?,
                    ?, ?,
                    ?, ?, ?, ?,
                    ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?, ?
                )
            ''', (
                train_asset_id, month_end, stock_price_now,
                fund_vals['volume'], fund_vals['market_cap'], fund_vals['shares_outstanding'],
                fund_vals['pe_ratio'], fund_vals['pb_ratio'], fund_vals['ps_ratio'], fund_vals['peg_ratio'],
                fund_vals['price_to_book'], fund_vals['price_to_sales'],
                fund_vals['enterprise_to_revenue'], fund_vals['enterprise_to_ebitda'],
                fund_vals['profit_margins'], fund_vals['operating_margins'],
                fund_vals['gross_margins'], fund_vals['ebitda_margins'],
                fund_vals['return_on_assets'], fund_vals['return_on_equity'],
                fund_vals['revenue_growth'], fund_vals['earnings_growth'],
                fund_vals['earnings_quarterly_growth'], fund_vals['revenue_per_share'],
                fund_vals['total_cash'], fund_vals['total_debt'], fund_vals['debt_to_equity'],
                fund_vals['current_ratio'], fund_vals['quick_ratio'],
                fund_vals['operating_cashflow'], fund_vals['free_cashflow'],
                fund_vals['trailing_eps'], fund_vals['forward_eps'], fund_vals['book_value'],
                fund_vals['dividend_rate'], fund_vals['dividend_yield'], fund_vals['payout_ratio'],
                fund_vals['price_change_pct'], fund_vals['volatility'], fund_vals['beta'],
                fund_vals['fifty_day_average'], fund_vals['two_hundred_day_average'],
                fund_vals['fifty_two_week_high'], fund_vals['fifty_two_week_low'],
                fund_vals['vix'], fund_vals['treasury_10y'], fund_vals['dollar_index'],
                fund_vals['oil_price'], fund_vals['gold_price'],
            ))

            snapshot_id = train.execute(
                'SELECT id FROM snapshots WHERE asset_id = ? AND snapshot_date = ?',
                (train_asset_id, month_end)
            ).fetchone()[0]

            # Insert forward excess returns
            for horizon_name, ret in forward_excess.items():
                train.execute(
                    'INSERT OR IGNORE INTO forward_returns (snapshot_id, horizon, return_pct) VALUES (?, ?, ?)',
                    (snapshot_id, horizon_name, ret)
                )

            inserted += 1

    train.commit()
    main.close()

    # Summary
    total_snapshots = train.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0]
    total_returns = train.execute('SELECT COUNT(*) FROM forward_returns').fetchone()[0]
    date_range = train.execute('SELECT MIN(snapshot_date), MAX(snapshot_date) FROM snapshots').fetchone()

    train.close()

    logger.info('\nDone!')
    logger.info(f'  Snapshots inserted: {total_snapshots}')
    logger.info(f'  Forward returns (excess vs SPY): {total_returns}')
    logger.info(f'  Date range: {date_range[0]} to {date_range[1]}')
    logger.info(f'  Skipped (no fundamentals yet): {skipped_no_fund}')
    logger.info(f'  Skipped (no stock price): {skipped_no_price}')
    logger.info(f'  Skipped (no SPY price): {skipped_no_spy}')
    logger.info(f'  Skipped (insufficient forward data): {skipped_no_forward}')


if __name__ == '__main__':
    build_cache()
