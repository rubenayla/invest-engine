#!/usr/bin/env python3
"""
Fetch EDINET large shareholding reports for Japanese equities.

Requires EDINET_API_KEY environment variable (free registration at api.edinet-fsa.go.jp).

Usage:
    uv run python scripts/fetch_edinet_data.py
    uv run python scripts/fetch_edinet_data.py --tickers 6758.T,4578.T
    EDINET_API_KEY=xxx uv run python scripts/fetch_edinet_data.py
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from invest.config.logging_config import setup_logging
from invest.data.db import get_connection
from invest.data.edinet_fetcher import (
    fetch_japan_stakes_for_ticker,
    load_edinet_map,
)
from invest.data.edinet_db import (
    ensure_schema,
    insert_stakes,
    log_fetch,
)

logger = logging.getLogger(__name__)


def main() -> int:
    setup_logging(log_file_path="logs/fetch_edinet_data.log")

    parser = argparse.ArgumentParser(description="Fetch EDINET large shareholding reports")
    parser.add_argument("--tickers", help="Comma-separated Japanese tickers (default: all mapped)")
    parser.add_argument("--lookback-days", type=int, default=365,
                        help="How far back to look (default: 365)")
    parser.add_argument("--api-key", help="EDINET API key (or set EDINET_API_KEY env var)")
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("EDINET_API_KEY", "")
    if not api_key:
        logger.error("No EDINET API key. Set EDINET_API_KEY env var or pass --api-key.")
        return 1

    edinet_map = load_edinet_map()
    if not edinet_map:
        logger.error("No ticker-to-EDINET mappings found at data/edinet/ticker_to_edinet.json")
        return 1

    if args.tickers:
        tickers = [t.strip() for t in args.tickers.split(",")]
        ticker_edinet = {t: edinet_map[t] for t in tickers if t in edinet_map}
        missing = [t for t in tickers if t not in edinet_map]
        if missing:
            logger.warning("No EDINET mapping for: %s", ", ".join(missing))
    else:
        ticker_edinet = edinet_map

    logger.info("Fetching EDINET data for %d tickers (lookback=%d days)",
                len(ticker_edinet), args.lookback_days)

    from datetime import datetime, timedelta
    since_date = (datetime.utcnow() - timedelta(days=args.lookback_days)).strftime("%Y-%m-%d")

    conn = get_connection()
    ensure_schema(conn)

    start_time = time.time()
    total_stakes = 0
    successful = 0
    failed = 0

    for ticker, edinet_code in ticker_edinet.items():
        try:
            stakes = fetch_japan_stakes_for_ticker(
                ticker, edinet_code, api_key, since_date,
            )
            if stakes:
                insert_stakes(conn, stakes)
            log_fetch(conn, ticker, edinet_code, doc_count=len(stakes), status="ok")
            total_stakes += len(stakes)
            successful += 1
            logger.info("  %s: %d reports found", ticker, len(stakes))
        except Exception as exc:
            logger.warning("Failed %s: %s", ticker, exc)
            try:
                log_fetch(conn, ticker, edinet_code, doc_count=0, status=f"error: {exc}")
            except Exception:
                pass
            failed += 1

    conn.close()

    elapsed = time.time() - start_time
    logger.info(
        "EDINET fetch complete: %d/%d tickers successful, "
        "%d total reports, %d failed, %.1fs elapsed",
        successful, successful + failed, total_stakes, failed, elapsed,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
