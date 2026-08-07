#!/usr/bin/env python3
"""
Migrate stock data from JSON cache to SQLite database.

This script reads the existing training_data_cache_multi_horizon.json
and migrates all records to the new SQLite database structure.
"""

import json
import sqlite3
import sys
from pathlib import Path
from typing import Dict

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.invest.valuation.neural_network_model import FeatureEngineer


def migrate_data(
    json_path: str = 'training_data_cache_multi_horizon.json',
    db_path: str = 'stock_data.db'
):
    """Migrate all data from JSON to SQLite."""

    print('🚀 Starting migration from JSON to SQLite')
    print('='*60)

    # Load JSON data
    print(f'\n📂 Loading JSON cache: {json_path}')
    with open(json_path) as f:
        data = json.load(f)

    records = data['samples']
    print(f'   Found {len(records)} records')

    # Connect to database
    print(f'\n💾 Connecting to database: {db_path}')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Enable foreign keys
    cursor.execute('PRAGMA foreign_keys = ON')

    # Track statistics
    stats = {
        'tickers_added': 0,
        'snapshots_added': 0,
        'returns_added': 0,
        'errors': 0
    }

    # Group records by ticker
    print('\n📊 Grouping records by ticker...')
    ticker_records: Dict[str, list] = {}
    for record in records:
        ticker = record['ticker']
        if ticker not in ticker_records:
            ticker_records[ticker] = []
        ticker_records[ticker].append(record)

    print(f'   Found {len(ticker_records)} unique tickers')

    # Initialize feature engineer
    print('\n🔧 Initializing feature engineer...')
    feature_engineer = FeatureEngineer()

    # Migrate each ticker
    print('\n🔄 Migrating data...')
    for i, (ticker, ticker_data) in enumerate(ticker_records.items(), 1):
        try:
            # Insert or get asset
            cursor.execute(
                'SELECT id FROM assets WHERE symbol = ?',
                (ticker,)
            )
            result = cursor.fetchone()

            if result:
                asset_id = result[0]
            else:
                # Get asset info from first record
                first_record = ticker_data[0]
                info = first_record['data'].get('info', {})

                cursor.execute('''
                    INSERT INTO assets (symbol, asset_type, name, sector, industry)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    ticker,
                    'stock',  # Default to stock for now
                    info.get('longName') or info.get('shortName'),
                    info.get('sector'),
                    info.get('industry')
                ))
                asset_id = cursor.lastrowid
                stats['tickers_added'] += 1

            # Insert snapshots for this ticker
            for record in ticker_data:
                # Extract features using FeatureEngineer
                data = record['data']
                features = feature_engineer.extract_features(data)
                forward_returns = record['forward_returns']

                # Get snapshot date from history (last date in the data)
                history = data.get('history')
                if history and 'index' in history and len(history['index']) > 0:
                    # history['index'] is a list of date strings
                    snapshot_date = history['index'][-1][:10]  # Take first 10 chars (YYYY-MM-DD)
                else:
                    # Skip if no history data
                    continue

                # Insert snapshot
                cursor.execute('''
                    INSERT INTO snapshots (
                        asset_id, snapshot_date,
                        current_price, volume, market_cap, shares_outstanding,
                        pe_ratio, pb_ratio, ps_ratio, peg_ratio,
                        price_to_book, price_to_sales, enterprise_to_revenue, enterprise_to_ebitda,
                        profit_margins, operating_margins, gross_margins, ebitda_margins,
                        return_on_assets, return_on_equity,
                        revenue_growth, earnings_growth, earnings_quarterly_growth, revenue_per_share,
                        total_cash, total_debt, debt_to_equity, current_ratio, quick_ratio,
                        operating_cashflow, free_cashflow,
                        trailing_eps, forward_eps, book_value,
                        dividend_rate, dividend_yield, payout_ratio,
                        price_change_pct, volatility, beta,
                        fifty_day_average, two_hundred_day_average,
                        fifty_two_week_high, fifty_two_week_low,
                        vix, treasury_10y, dollar_index, oil_price, gold_price
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    asset_id, snapshot_date,
                    features.get('current_price'), features.get('volume'),
                    features.get('market_cap'), features.get('shares_outstanding'),
                    features.get('pe_ratio'), features.get('pb_ratio'),
                    features.get('ps_ratio'), features.get('peg_ratio'),
                    features.get('price_to_book'), features.get('price_to_sales'),
                    features.get('enterprise_to_revenue'), features.get('enterprise_to_ebitda'),
                    features.get('profit_margins'), features.get('operating_margins'),
                    features.get('gross_margins'), features.get('ebitda_margins'),
                    features.get('return_on_assets'), features.get('return_on_equity'),
                    features.get('revenue_growth'), features.get('earnings_growth'),
                    features.get('earnings_quarterly_growth'), features.get('revenue_per_share'),
                    features.get('total_cash'), features.get('total_debt'),
                    features.get('debt_to_equity'), features.get('current_ratio'),
                    features.get('quick_ratio'), features.get('operating_cashflow'),
                    features.get('free_cashflow'), features.get('trailing_eps'),
                    features.get('forward_eps'), features.get('book_value'),
                    features.get('dividend_rate'), features.get('dividend_yield'),
                    features.get('payout_ratio'), features.get('price_change_pct'),
                    features.get('volatility'), features.get('beta'),
                    features.get('fifty_day_average'), features.get('two_hundred_day_average'),
                    features.get('fifty_two_week_high'), features.get('fifty_two_week_low'),
                    features.get('vix'), features.get('treasury_10y'),
                    features.get('dollar_index'), features.get('oil_price'),
                    features.get('gold_price')
                ))
                snapshot_id = cursor.lastrowid
                stats['snapshots_added'] += 1

                # Insert full price history (ALL the raw data)
                if history and 'index' in history:
                    for idx, date_str in enumerate(history['index']):
                        date = date_str[:10]  # YYYY-MM-DD

                        # Get values from history arrays
                        open_val = history['Open'][idx] if 'Open' in history else None
                        high_val = history['High'][idx] if 'High' in history else None
                        low_val = history['Low'][idx] if 'Low' in history else None
                        close_val = history['Close'][idx] if 'Close' in history else None
                        volume_val = history['Volume'][idx] if 'Volume' in history else None
                        dividends_val = history.get('Dividends', [None] * len(history['index']))[idx]
                        splits_val = history.get('Stock Splits', [None] * len(history['index']))[idx]

                        cursor.execute('''
                            INSERT INTO price_history
                            (snapshot_id, date, open, high, low, close, volume, dividends, stock_splits)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (snapshot_id, date, open_val, high_val, low_val, close_val,
                              volume_val, dividends_val, splits_val))
                        stats['returns_added'] += 1  # Reuse counter for tracking

                # Insert complete company info as JSON
                info = data.get('info', {})
                if info:
                    cursor.execute('''
                        INSERT INTO company_info (asset_id, snapshot_id, info_json)
                        VALUES (?, ?, ?)
                    ''', (asset_id, snapshot_id, json.dumps(info)))

                # Insert forward returns
                for horizon, return_pct in forward_returns.items():
                    cursor.execute('''
                        INSERT INTO forward_returns (snapshot_id, horizon, return_pct)
                        VALUES (?, ?, ?)
                    ''', (snapshot_id, horizon, return_pct))
                    stats['returns_added'] += 1

            # Progress indicator
            if i % 10 == 0:
                print(f'   [{i}/{len(ticker_records)}] Processed {ticker}...')

        except Exception as e:
            print(f'   ❌ Error processing {ticker}: {e}')
            stats['errors'] += 1
            continue

    # Commit all changes
    print('\n💾 Committing changes...')
    conn.commit()

    # Verify migration
    print('\n✅ Migration complete!')
    print('='*60)
    print('📊 Statistics:')
    print(f'   Tickers added: {stats["tickers_added"]}')
    print(f'   Snapshots added: {stats["snapshots_added"]}')
    print(f'   Returns added: {stats["returns_added"]}')
    print(f'   Errors: {stats["errors"]}')

    # Query to verify
    cursor.execute('SELECT COUNT(*) FROM assets')
    asset_count = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM snapshots')
    snapshot_count = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM forward_returns')
    return_count = cursor.fetchone()[0]

    print('\n📊 Database contents:')
    print(f'   Assets: {asset_count}')
    print(f'   Snapshots: {snapshot_count}')
    print(f'   Forward returns: {return_count}')

    conn.close()
    print(f'\n✅ Database ready: {db_path}')


if __name__ == '__main__':
    script_dir = Path(__file__).parent
    json_path = script_dir / 'training_data_cache_multi_horizon.json'
    db_path = script_dir / 'stock_data.db'

    migrate_data(str(json_path), str(db_path))
