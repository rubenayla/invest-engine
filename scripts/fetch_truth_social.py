#!/usr/bin/env python3
"""
Fetch Donald Trump's Truth Social posts and store in DB.

Polls the public Mastodon-compatible API at truthsocial.com, runs
regex+dictionary NER over post text, and upserts into truth_social_posts.

Usage:
    uv run python scripts/fetch_truth_social.py
    uv run python scripts/fetch_truth_social.py --limit 40
    uv run python scripts/fetch_truth_social.py --watch          # poll forever
    uv run python scripts/fetch_truth_social.py --interval 60    # custom poll cadence

Designed to be safe to run on a cron / loop alongside the other phase-1
fetchers in update_all.py.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / 'src'))

from invest.config.logging_config import setup_logging
from invest.data.truth_social_db import (
    ensure_schema,
    get_universe_company_names,
    upsert_posts,
)
from invest.data.truth_social_fetcher import (
    POLL_INTERVAL_SECONDS,
    fetch_and_parse,
)

logger = logging.getLogger(__name__)


def run_once(limit: int = 40) -> int:
    """Single fetch+upsert cycle. Returns rows written, -1 on DB error."""
    try:
        from invest.data.db import get_connection
        conn = get_connection()
    except Exception as exc:
        # DB down — log and exit clean (caller is the pipeline orchestrator)
        logger.warning('DB unavailable, skipping Truth Social fetch: %s', exc)
        return -1

    try:
        ensure_schema(conn)
        alias_dict = get_universe_company_names(conn)
        rows = fetch_and_parse(alias_dict=alias_dict, limit=limit)
        if not rows:
            logger.info('No Truth Social posts returned (rate limit or quiet day).')
            return 0
        written = upsert_posts(conn, rows)
        logger.info(
            'Truth Social: %d statuses fetched, %d upserted.',
            len(rows), written,
        )
        return written
    finally:
        try:
            conn.close()
        except Exception:
            pass


def main() -> int:
    setup_logging(log_file_path='logs/fetch_truth_social.log')

    parser = argparse.ArgumentParser(description='Fetch Donald Trump Truth Social posts')
    parser.add_argument('--limit', type=int, default=40,
                        help='Number of statuses to request per fetch (max 40)')
    parser.add_argument('--watch', action='store_true',
                        help='Poll continuously instead of single fetch')
    parser.add_argument('--interval', type=int, default=POLL_INTERVAL_SECONDS,
                        help=f'Seconds between polls in --watch mode (default {POLL_INTERVAL_SECONDS})')
    args = parser.parse_args()

    if not args.watch:
        result = run_once(limit=args.limit)
        return 0 if result >= 0 else 0  # never crash the pipeline

    interval = max(args.interval, 30)  # don't hammer the API
    logger.info('Watching Truth Social, interval=%ds', interval)
    while True:
        try:
            run_once(limit=args.limit)
        except KeyboardInterrupt:
            logger.info('Interrupted, exiting.')
            return 0
        except Exception as exc:
            logger.warning('Watch loop error (continuing): %s', exc)
        time.sleep(interval)


if __name__ == '__main__':
    sys.exit(main())
