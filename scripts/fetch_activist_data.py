#!/usr/bin/env python3
"""
Fetch SEC 13D/13G activist and large-stake filings for tickers with CIK mappings.

Usage:
    uv run python scripts/fetch_activist_data.py
    uv run python scripts/fetch_activist_data.py --tickers AAPL,MSFT,JPM
    uv run python scripts/fetch_activist_data.py --lookback-days 365 --force-refresh
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
    load_cik_map,
)
from invest.data.activist_fetcher import fetch_activist_data_for_ticker
from invest.data.activist_db import (
    ensure_schema,
    get_known_accessions,
    insert_stakes,
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
    """Fetch activist data for a single ticker. Returns summary dict."""
    conn = get_connection()
    try:
        ensure_schema(conn)
        known = set() if force_refresh else get_known_accessions(conn, ticker)

        stakes = fetch_activist_data_for_ticker(
            ticker, cik,
            rate_limiter=rate_limiter,
            since_date=since_date,
            known_accessions=known,
        )

        inserted = 0
        if stakes:
            inserted = insert_stakes(conn, stakes)

        log_fetch(conn, ticker, cik, filing_count=len(stakes), status="ok")
        return {"ticker": ticker, "stakes": len(stakes), "inserted": inserted}
    except Exception as exc:
        logger.warning("Failed %s: %s", ticker, exc)
        try:
            log_fetch(conn, ticker, cik, filing_count=0, status=f"error: {exc}")
        except Exception:
            pass
        return {"ticker": ticker, "error": str(exc)}
    finally:
        conn.close()


def main() -> int:
    setup_logging(log_file_path="logs/fetch_activist_data.log")

    parser = argparse.ArgumentParser(description="Fetch SEC 13D/13G activist data")
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
        logger.error("No CIK mappings found. Cannot fetch activist data.")
        return 1

    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",")]
        ticker_cik = {t: cik_map[t] for t in tickers if t in cik_map}
        missing = [t for t in tickers if t not in cik_map]
        if missing:
            logger.warning("No CIK mapping for: %s", ", ".join(missing))
    else:
        ticker_cik = cik_map

    logger.info("Fetching activist data for %d tickers (lookback=%d days)",
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
    total_stakes = sum(r.get("stakes", 0) for r in results)
    failed = len(results) - successful

    logger.info(
        "Activist data fetch complete: %d/%d tickers successful, "
        "%d total stakes, %d failed, %.1fs elapsed",
        successful, len(results), total_stakes, failed, elapsed,
    )

    if failed > 0:
        failed_tickers = [r["ticker"] for r in results if "error" in r]
        logger.info("Failed tickers: %s", ", ".join(failed_tickers[:20]))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
