#!/usr/bin/env python3
"""
Fetch US House Periodic Transaction Reports (PTRs) and store in DB.

Usage:
    uv run python scripts/fetch_politician_data.py
    uv run python scripts/fetch_politician_data.py --years 2025 2026
    uv run python scripts/fetch_politician_data.py --years 2026 --max-docs 50
    uv run python scripts/fetch_politician_data.py --force-refresh
"""

from __future__ import annotations

import argparse
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / 'src'))

from invest.config.logging_config import setup_logging
from invest.data.db import get_connection
from invest.data.politician_db import (
    ensure_schema,
    get_known_doc_ids,
    insert_trades,
    log_doc,
)
from invest.data.politician_fetcher import (
    PtrIndexEntry,
    TokenBucketRateLimiter,
    fetch_and_parse_ptr_pdf,
    fetch_ptr_index,
)

logger = logging.getLogger(__name__)


def process_doc(
    entry: PtrIndexEntry,
    rate_limiter: TokenBucketRateLimiter,
) -> dict:
    """Fetch + parse one PTR PDF, insert rows, log it. Returns summary."""
    conn = get_connection()
    try:
        ensure_schema(conn)
        trades = fetch_and_parse_ptr_pdf(entry, rate_limiter)
        inserted = 0
        if trades:
            inserted = insert_trades(conn, trades)
        log_doc(
            conn, entry.doc_id, entry.politician_name, 'House',
            entry.year, len(trades), status='ok',
        )
        return {'doc_id': entry.doc_id, 'trades': len(trades), 'inserted': inserted}
    except Exception as exc:
        logger.warning('Failed doc %s: %s', entry.doc_id, exc)
        try:
            log_doc(
                conn, entry.doc_id, entry.politician_name, 'House',
                entry.year, 0, status=f'error: {exc}',
            )
        except Exception:
            pass
        return {'doc_id': entry.doc_id, 'error': str(exc)}
    finally:
        conn.close()


def main() -> int:
    setup_logging(log_file_path='logs/fetch_politician_data.log')

    parser = argparse.ArgumentParser(description='Fetch House PTR data')
    parser.add_argument(
        '--years',
        type=int,
        nargs='+',
        default=[datetime.utcnow().year],
        help='Years to fetch (default: current year)',
    )
    parser.add_argument('--max-docs', type=int, default=None,
                        help='Cap number of new docs processed (debug)')
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--force-refresh', action='store_true',
                        help='Re-process docs already in fetch log')
    args = parser.parse_args()

    rate_limiter = TokenBucketRateLimiter(rate=4.0, burst=4)

    # Load known doc_ids once across all years
    bootstrap_conn = get_connection()
    ensure_schema(bootstrap_conn)
    known = set() if args.force_refresh else get_known_doc_ids(bootstrap_conn)
    bootstrap_conn.close()

    pending: list[PtrIndexEntry] = []
    for year in args.years:
        logger.info('Fetching index for %d ...', year)
        try:
            entries = fetch_ptr_index(year, rate_limiter)
        except Exception as exc:
            logger.error('Failed index for %d: %s', year, exc)
            continue
        new_entries = [e for e in entries if e.doc_id not in known]
        logger.info('Year %d: %d entries, %d new', year, len(entries), len(new_entries))
        pending.extend(new_entries)

    if args.max_docs:
        pending = pending[:args.max_docs]

    if not pending:
        logger.info('No new PTRs to process.')
        return 0

    logger.info('Processing %d PTR PDFs with %d workers ...', len(pending), args.workers)
    total_trades = 0
    total_inserted = 0
    errors = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(process_doc, e, rate_limiter): e for e in pending}
        for fut in as_completed(futures):
            result = fut.result()
            if 'error' in result:
                errors += 1
            else:
                total_trades += result['trades']
                total_inserted += result['inserted']

    logger.info(
        'Done. %d docs, %d trades parsed, %d inserted, %d errors.',
        len(pending), total_trades, total_inserted, errors,
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())
