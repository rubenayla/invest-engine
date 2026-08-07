#!/usr/bin/env python3
"""
Fetch SEC 13F institutional holdings for curated "smart money" funds.

Iterates over funds (not tickers). ~20 funds x 4 quarters x 2 requests = ~160 requests.

Usage:
    uv run python scripts/fetch_holdings_data.py
    uv run python scripts/fetch_holdings_data.py --force-refresh
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
from invest.data.insider_fetcher import TokenBucketRateLimiter
from invest.data.holdings_fetcher import (
    fetch_holdings_for_fund,
    load_cusip_map,
    load_smart_money_funds,
)
from invest.data.holdings_db import (
    ensure_schema,
    get_known_accessions,
    insert_holdings,
    log_fetch,
)

logger = logging.getLogger(__name__)


def fetch_one_fund(
    fund: dict,
    rate_limiter: TokenBucketRateLimiter,
    force_refresh: bool,
    cusip_map: dict,
) -> dict:
    """Fetch holdings for a single fund. Returns summary dict."""
    fund_name = fund["name"]
    fund_cik = fund["cik"]

    conn = get_connection()
    try:
        ensure_schema(conn)

        # Use filing_date as dedup key (not accession)
        known = set() if force_refresh else get_known_accessions(conn, fund_cik)

        holdings = fetch_holdings_for_fund(
            fund_name, fund_cik,
            rate_limiter=rate_limiter,
            known_accessions=known,
            cusip_map=cusip_map,
        )

        inserted = 0
        if holdings:
            inserted = insert_holdings(conn, holdings)

        log_fetch(conn, fund_cik, fund_name, filing_count=len(holdings), status="ok")
        return {"fund": fund_name, "holdings": len(holdings), "inserted": inserted}
    except Exception as exc:
        logger.warning("Failed %s: %s", fund_name, exc)
        try:
            log_fetch(conn, fund_cik, fund_name, filing_count=0, status=f"error: {exc}")
        except Exception:
            pass
        return {"fund": fund_name, "error": str(exc)}
    finally:
        conn.close()


def main() -> int:
    setup_logging(log_file_path="logs/fetch_holdings_data.log")

    parser = argparse.ArgumentParser(description="Fetch SEC 13F institutional holdings")
    parser.add_argument("--force-refresh", action="store_true",
                        help="Re-fetch even if filings are already known")
    parser.add_argument("--max-workers", type=int, default=4,
                        help="Max concurrent fund fetches (default: 4)")
    args = parser.parse_args()

    funds = load_smart_money_funds()
    if not funds:
        logger.error("No funds found in smart_money_funds.json")
        return 1

    cusip_map = load_cusip_map()
    logger.info("Loaded %d CUSIP->ticker mappings", len(cusip_map))

    logger.info("Fetching holdings for %d funds", len(funds))

    rate_limiter = TokenBucketRateLimiter(rate=8.0, burst=8)
    start_time = time.time()
    results = []

    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        future_to_fund = {
            executor.submit(
                fetch_one_fund, fund, rate_limiter, args.force_refresh, cusip_map
            ): fund["name"]
            for fund in funds
        }

        for future in as_completed(future_to_fund):
            fund_name = future_to_fund[future]
            try:
                result = future.result(timeout=300)
                results.append(result)
                status = f"{result.get('holdings', 0)} holdings" if "error" not in result else f"ERROR: {result['error']}"
                logger.info("  %s: %s", fund_name, status)
            except Exception as exc:
                logger.error("Unexpected error for %s: %s", fund_name, exc)
                results.append({"fund": fund_name, "error": str(exc)})

    elapsed = time.time() - start_time
    successful = sum(1 for r in results if "error" not in r)
    total_holdings = sum(r.get("holdings", 0) for r in results)
    failed = len(results) - successful

    logger.info(
        "Holdings fetch complete: %d/%d funds successful, "
        "%d total holdings, %d failed, %.1fs elapsed",
        successful, len(results), total_holdings, failed, elapsed,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
