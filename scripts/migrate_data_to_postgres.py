#!/usr/bin/env python3
"""
One-time migration: SQLite → PostgreSQL.

Reads all tables from data/stock_data.db and copies them into the configured
PostgreSQL database. Database configuration follows README.md.

Usage:
    uv run python scripts/migrate_data_to_postgres.py
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import sys
import time
from pathlib import Path

import psycopg2
import psycopg2.extras

REPO_ROOT = Path(__file__).parent.parent
SQLITE_DB = REPO_ROOT / 'data' / 'stock_data.db'

# Tables to migrate, in dependency order
TABLES = [
    'assets',
    'current_stock_data',
    'fundamental_history',
    'price_history',
    'valuation_results',
    'forward_returns',
    'company_info',
    'models',
    'scanner_threshold_history',
    'scanner_score_history',
    'macro_rates',
    'insider_transactions',
    'insider_fetch_log',
    'activist_stakes',
    'activist_fetch_log',
    'fund_holdings',
    'holdings_fetch_log',
    'japan_large_stakes',
    'edinet_fetch_log',
    'price_alarms',
]

# Columns that are JSONB in Postgres but TEXT in SQLite
JSONB_COLUMNS = {
    'current_stock_data': {'cashflow_json', 'balance_sheet_json', 'income_json'},
    'valuation_results': {'details_json'},
    'company_info': {'info_json'},
}


def get_sqlite_columns(sqlite_conn: sqlite3.Connection, table: str) -> list[str]:
    """Get column names for a SQLite table."""
    cursor = sqlite_conn.execute(f'PRAGMA table_info("{table}")')
    return [row[1] for row in cursor.fetchall()]


def get_postgres_columns(pg_conn, table: str) -> list[str]:
    """Get column names for a Postgres table."""
    cursor = pg_conn.cursor()
    cursor.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = %s AND table_schema = 'public' ORDER BY ordinal_position",
        (table,),
    )
    return [row[0] for row in cursor.fetchall()]


def migrate_table(sqlite_conn: sqlite3.Connection, pg_conn, table: str) -> int:
    """Migrate a single table. Returns row count."""
    sqlite_cols = get_sqlite_columns(sqlite_conn, table)
    pg_cols = get_postgres_columns(pg_conn, table)

    # Only migrate columns that exist in both
    common_cols = [c for c in sqlite_cols if c in pg_cols]
    if not common_cols:
        print(f'  SKIP {table}: no common columns')
        return 0

    jsonb_cols = JSONB_COLUMNS.get(table, set())

    # Detect boolean and numeric columns in Postgres
    cursor = pg_conn.cursor()
    cursor.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_name = %s",
        (table,),
    )
    col_types = {row[0]: row[1] for row in cursor.fetchall()}
    bool_cols = {c for c, t in col_types.items() if t == 'boolean'}
    numeric_cols = {c for c, t in col_types.items() if t in ('double precision', 'integer', 'bigint', 'numeric')}

    # Read all rows from SQLite
    col_list = ', '.join(f'"{c}"' for c in common_cols)
    rows = sqlite_conn.execute(f'SELECT {col_list} FROM "{table}"').fetchall()

    if not rows:
        print(f'  {table}: 0 rows (empty)')
        return 0

    # Prepare for Postgres insert
    cursor = pg_conn.cursor()
    pg_col_list = ', '.join(f'"{c}"' for c in common_cols)
    placeholders = ', '.join(['%s'] * len(common_cols))

    # Build insert SQL — skip conflicts on tables with unique constraints
    insert_sql = f'INSERT INTO "{table}" ({pg_col_list}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'

    # Process rows in batches
    batch_size = 1000
    total = 0

    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        converted_batch = []

        for row in batch:
            converted_row = []
            for col_name, value in zip(common_cols, row):
                if col_name in jsonb_cols and isinstance(value, str):
                    try:
                        # Replace NaN/Infinity tokens that SQLite allows but Postgres rejects
                        cleaned = re.sub(r'\bNaN\b', 'null', value)
                        cleaned = re.sub(r'\bInfinity\b', 'null', cleaned)
                        cleaned = re.sub(r'\b-Infinity\b', 'null', cleaned)
                        parsed = json.loads(cleaned)
                        converted_row.append(json.dumps(parsed))
                    except (json.JSONDecodeError, TypeError):
                        converted_row.append(value)
                elif col_name in jsonb_cols and value is None:
                    converted_row.append(None)
                elif col_name in bool_cols and isinstance(value, int):
                    converted_row.append(bool(value))
                elif col_name in numeric_cols and isinstance(value, str):
                    # Text in a numeric column (e.g. "high" in confidence) → None
                    try:
                        converted_row.append(float(value))
                    except (ValueError, TypeError):
                        converted_row.append(None)
                elif isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
                    converted_row.append(None)
                else:
                    converted_row.append(value)
            converted_batch.append(tuple(converted_row))

        psycopg2.extras.execute_batch(cursor, insert_sql, converted_batch, page_size=500)
        total += len(batch)

    pg_conn.commit()

    # Fix sequences for SERIAL columns
    if 'id' in common_cols:
        cursor.execute(
            f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
            f"COALESCE((SELECT MAX(id) FROM \"{table}\"), 1))"
        )
        pg_conn.commit()

    return total


def main():
    if not SQLITE_DB.exists():
        print(f'ERROR: SQLite database not found at {SQLITE_DB}')
        sys.exit(1)

    # Connect to SQLite
    sqlite_conn = sqlite3.connect(str(SQLITE_DB))

    # Get list of tables in SQLite
    sqlite_tables = {
        row[0]
        for row in sqlite_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence'"
        ).fetchall()
    }

    # Connect to Postgres
    sys.path.insert(0, str(REPO_ROOT / 'src'))
    from invest.data.db import get_db_url
    pg_conn = psycopg2.connect(get_db_url())

    print(f'SQLite: {SQLITE_DB} ({SQLITE_DB.stat().st_size / 1024 / 1024:.1f} MB)')
    pg_display = get_db_url().split('@')[1] if '@' in get_db_url() else get_db_url()
    print(f'Postgres: {pg_display}')
    print()

    start = time.time()
    total_rows = 0

    for table in TABLES:
        if table not in sqlite_tables:
            print(f'  SKIP {table}: not in SQLite')
            continue

        t0 = time.time()
        count = migrate_table(sqlite_conn, pg_conn, table)
        elapsed = time.time() - t0
        total_rows += count
        print(f'  {table}: {count:,} rows ({elapsed:.1f}s)')

    # Check for tables we might have missed
    migrated = set(TABLES)
    missed = sqlite_tables - migrated
    if missed:
        print(f'\n  WARNING: tables in SQLite but not in migration list: {missed}')

    elapsed_total = time.time() - start
    print(f'\nDone: {total_rows:,} total rows in {elapsed_total:.1f}s')

    sqlite_conn.close()
    pg_conn.close()


if __name__ == '__main__':
    main()
