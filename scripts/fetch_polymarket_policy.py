#!/usr/bin/env python3
"""
Fetch Polymarket Trump-policy markets, upsert into Postgres, emit alerts.

Usage:
    uv run python scripts/fetch_polymarket_policy.py
    uv run python scripts/fetch_polymarket_policy.py --min-volume 5000
    uv run python scripts/fetch_polymarket_policy.py --max-pages 8

The script:
  1. Calls Polymarket gamma-api for active markets (paginated).
  2. Filters to Trump-policy themes via keyword/category rules.
  3. Upserts into trump_policy_markets, snapshots prices into history.
  4. Computes 24h pp deltas; pushes >10pp moves into policy_alerts.

Designed to be run hourly via cron / wired into update_all.py. Postgres
being down is non-fatal — we exit 0 with a warning so the rest of the
update pipeline keeps going.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / 'src'))
sys.path.insert(0, str(REPO_ROOT / 'scripts'))

from invest.config.logging_config import setup_logging
from invest.data.db import get_connection
from invest.data.polymarket_db import (
    compute_and_record_alerts,
    delete_stale_markets,
    ensure_schema,
    upsert_markets,
)
from polymarket_lookup import fetch_trump_policy_markets

logger = logging.getLogger(__name__)


def main() -> int:
    setup_logging(log_file_path='logs/fetch_polymarket_policy.log')

    parser = argparse.ArgumentParser(description='Fetch Polymarket Trump-policy markets')
    parser.add_argument('--min-volume', type=float, default=0,
                        help='Filter out markets below this lifetime volume USD')
    parser.add_argument('--max-pages', type=int, default=6,
                        help='Max gamma-api pages to fetch (500 each)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Fetch + classify but do not write to DB')
    args = parser.parse_args()

    logger.info('Fetching Trump-policy markets from Polymarket gamma-api ...')
    try:
        markets = fetch_trump_policy_markets(
            max_pages=args.max_pages,
            min_volume_total=args.min_volume,
        )
    except Exception as exc:
        logger.error('Polymarket fetch failed: %s', exc)
        return 0  # non-fatal — don't break update_all

    logger.info('Fetched %d Trump-policy markets', len(markets))
    if not markets:
        logger.warning('No markets returned — API may have changed shape')
        return 0

    if args.dry_run:
        for m in markets[:10]:
            logger.info('  [%s] %s | yes=%.2f vol24h=%.0f',
                        m['category'], m['question'][:80],
                        m.get('yes_price') or 0, m.get('volume_24h') or 0)
        return 0

    try:
        conn = get_connection()
    except Exception as exc:
        logger.warning('Postgres unavailable, exiting cleanly: %s', exc)
        return 0

    try:
        ensure_schema(conn)
        upserted = upsert_markets(conn, markets)
        kept_ids = [m['market_id'] for m in markets]
        deleted = delete_stale_markets(conn, kept_ids)
        alerts = compute_and_record_alerts(conn, markets)
        logger.info('Upserted %d markets, deleted %d stale, emitted %d alerts',
                    upserted, deleted, len(alerts))
        for a in alerts:
            logger.info('  ALERT: %+.1fpp %s', a['delta_pp'], a['question'][:80])
    finally:
        conn.close()

    return 0


if __name__ == '__main__':
    sys.exit(main())
