#!/usr/bin/env python3
"""Reconstruct daily insider signal snapshots from stored Form 4 transactions.

The backfill creates one snapshot for each date on which a ticker has an
open-market Form 4 transaction. It computes the signal using only transactions
known on that date, so later filings cannot leak into an earlier snapshot.

Usage:
    uv run python scripts/backfill_insider_snapshots.py
    uv run python scripts/backfill_insider_snapshots.py --lookback-days 180
    uv run python scripts/backfill_insider_snapshots.py --tickers AAPL,MSFT
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from invest.data.db import get_connection
from invest.data.insider_db import (
    _aggregate_insider_rows,
    _trends_from_aggregates,
    ensure_schema,
)
from invest.scanner.scoring_engine import ScoringEngine


def build_daily_snapshots(
    rows: Iterable[tuple],
    lookback_days: int = 180,
) -> list[dict[str, Any]]:
    """Build as-of-date insider snapshots from transaction rows.

    Each input row is ``(ticker, transaction_type, shares, price,
    transaction_date, reporter_name, is_open_market)``. Only open-market
    purchases and sales contribute to a snapshot.
    """
    by_ticker: dict[str, list[tuple]] = defaultdict(list)
    for ticker, tx_type, shares, price, tx_date, reporter, is_open_market in rows:
        if is_open_market and tx_type in {"P", "S"}:
            by_ticker[ticker].append((tx_type, shares, price, tx_date, reporter, is_open_market))

    engine = ScoringEngine()
    snapshots: list[dict[str, Any]] = []
    for ticker, ticker_rows in by_ticker.items():
        ticker_rows.sort(key=lambda row: row[3])
        dates = sorted({row[3] for row in ticker_rows})
        for date_str in dates:
            as_of = datetime.strptime(date_str, "%Y-%m-%d")
            cutoff = (as_of - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
            recent = [row for row in ticker_rows if cutoff <= row[3] <= date_str]
            if not recent:
                continue

            signal = _aggregate_insider_rows(recent, now=as_of)
            recent_sells = sum(row[0] == "S" for row in recent)
            recent_buys = sum(row[0] == "P" for row in recent)
            prior = [row for row in ticker_rows if row[3] < cutoff]
            sell_trend, buy_trend = _trends_from_aggregates(
                ticker_rows[0][3], len(ticker_rows),
                recent_sells, recent_buys,
                sum(row[0] == "S" for row in prior),
                sum(row[0] == "P" for row in prior),
                lookback_days, as_of,
            )
            signal["sell_trend"] = sell_trend
            signal["buy_trend"] = buy_trend
            _, details = engine.score_catalyst({"insider": signal})
            insider = details["insider"]
            snapshots.append({
                "date": date_str,
                "ticker": ticker,
                "insider_score": insider["score"],
                "buy_count": signal["buy_count"],
                "sell_count": signal["sell_count"],
                "net_buy_pct": signal["net_buy_pct"],
                "sell_trend": sell_trend,
                "buy_trend": buy_trend,
                "cluster_score": signal["cluster_score"],
                "dollar_conviction": signal["dollar_conviction"],
            })
    return sorted(snapshots, key=lambda row: (row["ticker"], row["date"]))


def backfill(tickers: set[str] | None = None, lookback_days: int = 180) -> int:
    """Read Form 4 rows and upsert reconstructed snapshots."""
    conn = get_connection()
    try:
        ensure_schema(conn)
        cur = conn.cursor()
        cur.execute("""
            SELECT ticker, transaction_type, shares, price_per_share,
                   transaction_date, reporter_name, is_open_market
            FROM insider_transactions
            WHERE is_open_market = 1
            ORDER BY ticker, transaction_date
        """)
        rows = cur.fetchall()
        if tickers:
            rows = [row for row in rows if row[0] in tickers]
        snapshots = build_daily_snapshots(rows, lookback_days)
        for snapshot in snapshots:
            cur.execute("""
                INSERT INTO insider_signal_history
                    (date, ticker, insider_score, buy_count, sell_count,
                     net_buy_pct, sell_trend, buy_trend, cluster_score,
                     dollar_conviction)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (date, ticker) DO UPDATE SET
                    insider_score = EXCLUDED.insider_score,
                    buy_count = EXCLUDED.buy_count,
                    sell_count = EXCLUDED.sell_count,
                    net_buy_pct = EXCLUDED.net_buy_pct,
                    sell_trend = EXCLUDED.sell_trend,
                    buy_trend = EXCLUDED.buy_trend,
                    cluster_score = EXCLUDED.cluster_score,
                    dollar_conviction = EXCLUDED.dollar_conviction
            """, tuple(snapshot[field] for field in (
                "date", "ticker", "insider_score", "buy_count", "sell_count",
                "net_buy_pct", "sell_trend", "buy_trend", "cluster_score",
                "dollar_conviction",
            )))
        conn.commit()
        return len(snapshots)
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", help="Comma-separated ticker subset")
    parser.add_argument("--lookback-days", type=int, default=180)
    args = parser.parse_args()
    tickers = {ticker.strip().upper() for ticker in args.tickers.split(",")} if args.tickers else None
    count = backfill(tickers=tickers, lookback_days=args.lookback_days)
    print(f"Upserted {count} insider signal snapshots")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
