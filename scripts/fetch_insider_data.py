#!/usr/bin/env python3
"""
Fetch SEC Form 4 insider transaction data for all tickers with CIK mappings.

Usage:
    uv run python scripts/fetch_insider_data.py
    uv run python scripts/fetch_insider_data.py --tickers AAPL,MSFT,JPM
    uv run python scripts/fetch_insider_data.py --lookback-days 365 --force-refresh
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from invest.config.logging_config import setup_logging
from invest.data.db import get_connection
from invest.data.insider_fetcher import (
    TokenBucketRateLimiter,
    fetch_insider_data_for_ticker,
    load_cik_map,
)
from invest.data.insider_db import (
    ensure_schema,
    get_known_accessions,
    insert_transactions,
    log_fetch,
)

logger = logging.getLogger(__name__)


def fetch_one_ticker(
    ticker: str,
    cik: str,
    rate_limiter: TokenBucketRateLimiter,
    since_date: str,
    force_refresh: bool,
) -> dict:
    """Fetch insider data for a single ticker. Returns summary dict."""
    conn = get_connection()
    try:
        ensure_schema(conn)
        known = set() if force_refresh else get_known_accessions(conn, ticker)

        txns = fetch_insider_data_for_ticker(
            ticker, cik,
            rate_limiter=rate_limiter,
            since_date=since_date,
            known_accessions=known,
        )

        inserted = 0
        if txns:
            inserted = insert_transactions(conn, txns)

        log_fetch(conn, ticker, cik, form4_count=len(txns), status="ok")
        return {"ticker": ticker, "transactions": len(txns), "inserted": inserted}
    except Exception as exc:
        logger.warning("Failed %s: %s", ticker, exc)
        try:
            log_fetch(conn, ticker, cik, form4_count=0, status=f"error: {exc}")
        except Exception:
            pass
        return {"ticker": ticker, "error": str(exc)}
    finally:
        conn.close()


def main() -> int:
    setup_logging(log_file_path="logs/fetch_insider_data.log")

    parser = argparse.ArgumentParser(description="Fetch SEC Form 4 insider data")
    parser.add_argument("--tickers", help="Comma-separated tickers (default: all with CIK)")
    parser.add_argument("--lookback-days", type=int, default=730,
                        help="How far back to look for filings (default: 730)")
    parser.add_argument("--force-refresh", action="store_true",
                        help="Re-fetch even if accessions are already known")
    parser.add_argument("--max-workers", type=int, default=4,
                        help="Max concurrent ticker fetches (default: 4)")
    args = parser.parse_args()

    cik_map = load_cik_map()
    if not cik_map:
        logger.error("No CIK mappings found. Cannot fetch insider data.")
        return 1

    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",")]
        # Filter to those with CIK mappings
        ticker_cik = {t: cik_map[t] for t in tickers if t in cik_map}
        missing = [t for t in tickers if t not in cik_map]
        if missing:
            logger.warning("No CIK mapping for: %s", ", ".join(missing))
    else:
        # Scope to tickers in our DB universe (not the entire SEC CIK map)
        from invest.data.stock_data_reader import StockDataReader
        try:
            universe = set(StockDataReader().get_all_tickers())
            ticker_cik = {t: cik_map[t] for t in universe if t in cik_map}
            logger.info("Scoped to %d tickers in DB universe (of %d in CIK map)",
                        len(ticker_cik), len(cik_map))
        except Exception:
            ticker_cik = cik_map

    logger.info("Fetching insider data for %d tickers (lookback=%d days)",
                len(ticker_cik), args.lookback_days)

    from datetime import datetime, timedelta
    since_date = (datetime.utcnow() - timedelta(days=args.lookback_days)).strftime("%Y-%m-%d")

    rate_limiter = TokenBucketRateLimiter(rate=8.0, burst=8)
    start_time = time.time()
    results = []

    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        future_to_ticker = {
            executor.submit(
                fetch_one_ticker, ticker, cik, rate_limiter, since_date, args.force_refresh
            ): ticker
            for ticker, cik in ticker_cik.items()
        }

        for i, future in enumerate(as_completed(future_to_ticker), 1):
            ticker = future_to_ticker[future]
            try:
                result = future.result(timeout=300)
                results.append(result)
            except Exception as exc:
                logger.error("Unexpected error for %s: %s", ticker, exc)
                results.append({"ticker": ticker, "error": str(exc)})

            if i % 25 == 0 or i == len(future_to_ticker):
                elapsed = time.time() - start_time
                logger.info("Progress: %d/%d tickers (%.1fs elapsed)",
                            i, len(future_to_ticker), elapsed)

    elapsed = time.time() - start_time
    successful = sum(1 for r in results if "error" not in r)
    total_txns = sum(r.get("transactions", 0) for r in results)
    failed = len(results) - successful

    logger.info(
        "Insider data fetch complete: %d/%d tickers successful, "
        "%d total transactions, %d failed, %.1fs elapsed",
        successful, len(results), total_txns, failed, elapsed
    )

    if failed > 0:
        failed_tickers = [r["ticker"] for r in results if "error" in r]
        logger.info("Failed tickers: %s", ", ".join(failed_tickers[:20]))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
