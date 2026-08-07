#!/usr/bin/env python3
"""
Migrate stock data from JSON files to SQLite database.

Reads all JSON cache files and populates the current_stock_data table.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

# Get project root
project_root = Path(__file__).parent.parent
cache_dir = project_root / 'data' / 'stock_cache'
db_path = project_root / 'neural_network' / 'training' / 'stock_data.db'


def migrate_stock_data():
    """Migrate all JSON cache files to SQLite."""

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get all JSON files
    json_files = list(cache_dir.glob('*.json'))
    print(f'Found {len(json_files)} JSON cache files')

    success_count = 0
    error_count = 0
    errors = []

    for json_file in json_files:
        try:
            # Skip cache_index.json
            if json_file.name == 'cache_index.json':
                continue

            with open(json_file) as f:
                data = json.load(f)

            ticker = data.get('ticker')
            if not ticker:
                ticker = json_file.stem

            info = data.get('info', {})
            financials = data.get('financials', {})
            price_data = data.get('price_data', {})

            # Prepare data for insertion
            cursor.execute('''
                INSERT OR REPLACE INTO current_stock_data (
                    ticker,
                    current_price, market_cap, sector, industry, long_name, short_name,
                    currency, exchange, country,
                    trailing_pe, forward_pe, price_to_book, return_on_equity, debt_to_equity,
                    current_ratio, revenue_growth, earnings_growth, operating_margins, profit_margins,
                    total_revenue, total_cash, total_debt, shares_outstanding,
                    trailing_eps, book_value, revenue_per_share, price_to_sales_ttm,
                    price_52w_high, price_52w_low, avg_volume, price_trend_30d,
                    cashflow_json, balance_sheet_json, income_json,
                    fetch_timestamp, last_updated
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?
                )
            ''', (
                ticker,
                # Basic info
                info.get('currentPrice'),
                info.get('marketCap'),
                info.get('sector'),
                info.get('industry'),
                info.get('longName'),
                info.get('shortName'),
                info.get('currency'),
                info.get('exchange'),
                info.get('country'),
                # Financial metrics
                financials.get('trailingPE'),
                financials.get('forwardPE'),
                financials.get('priceToBook'),
                financials.get('returnOnEquity'),
                financials.get('debtToEquity'),
                financials.get('currentRatio'),
                financials.get('revenueGrowth'),
                financials.get('earningsGrowth'),
                financials.get('operatingMargins'),
                financials.get('profitMargins'),
                financials.get('totalRevenue'),
                financials.get('totalCash'),
                financials.get('totalDebt'),
                financials.get('sharesOutstanding'),
                financials.get('trailingEps'),
                financials.get('bookValue'),
                financials.get('revenuePerShare'),
                financials.get('priceToSalesTrailing12Months'),
                # Price data
                price_data.get('price_52w_high'),
                price_data.get('price_52w_low'),
                price_data.get('avg_volume'),
                price_data.get('price_trend_30d'),
                # Raw JSON
                json.dumps(data.get('cashflow', [])),
                json.dumps(data.get('balance_sheet', [])),
                json.dumps(data.get('income', [])),
                # Metadata
                data.get('fetch_timestamp', datetime.now().isoformat()),
                datetime.now().isoformat()
            ))

            success_count += 1

            if success_count % 50 == 0:
                print(f'  Migrated {success_count}/{len(json_files)}...')
                conn.commit()

        except Exception as e:
            error_count += 1
            errors.append((json_file.name, str(e)))

    conn.commit()
    conn.close()

    print('\n✅ Migration complete!')
    print(f'  Successful: {success_count}')
    print(f'  Errors: {error_count}')

    if errors:
        print('\nErrors:')
        for filename, error in errors[:10]:  # Show first 10 errors
            print(f'  {filename}: {error}')


if __name__ == '__main__':
    migrate_stock_data()
