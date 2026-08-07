#!/usr/bin/env python3
"""
Generate the main valuation dashboard.

This is THE ONLY dashboard script you need to run.

Usage:
    uv run python scripts/dashboard.py

Reads ALL data from PostgreSQL database (single source of truth):
- Stock info from current_stock_data table
- Valuation results from valuation_results table

Output:
    dashboard/valuation_dashboard.html
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / 'src'))

from invest.data.db import get_connection

from invest.dashboard_components.html_generator import HTMLGenerator


def load_stocks_from_database() -> dict:
    """
    Load all stock data and valuations from database.

    Returns
    -------
    dict
        Stock data in format expected by HTMLGenerator:
        {
            'AAPL': {
                'ticker': 'AAPL',
                'company_name': 'Apple Inc.',
                'valuations': {
                    'single_horizon_nn': {...},
                    'dcf': {...},
                    ...
                }
            },
            ...
        }
    """
    conn = get_connection(dict_cursor=True)

    # Get all stocks with current price
    stocks_query = '''
        SELECT ticker, current_price, long_name, short_name, sector, fetch_timestamp
        FROM current_stock_data
        WHERE current_price IS NOT NULL
    '''
    stocks = {}

    cursor = conn.cursor()
    cursor.execute(stocks_query)
    for row in cursor.fetchall():
        ticker = row['ticker']
        stocks[ticker] = {
            'ticker': ticker,
            'company_name': row['long_name'] or row['short_name'] or ticker,
            'sector': row['sector'],
            'current_price': row['current_price'],
            'fetch_timestamp': row['fetch_timestamp'],
            'valuations': {}
        }

    print(f'Loaded {len(stocks)} stocks from current_stock_data')

    # Get all valuation results (including unsuitable ones with error messages)
    valuations_query = '''
        SELECT ticker, model_name, suitable, fair_value, current_price,
               margin_of_safety, upside_pct, confidence, error_message,
               failure_reason, details_json, timestamp
        FROM valuation_results
    '''

    valuation_count = 0
    latest_price_by_ticker = {}
    cursor.execute(valuations_query)
    for row in cursor.fetchall():
        ticker = row['ticker']

        # Skip if ticker not in stocks (shouldn't happen, but defensive)
        if ticker not in stocks:
            continue

        model_name = row['model_name']

        # Parse timestamp for staleness tracking
        model_ts = row['timestamp']
        if isinstance(model_ts, str):
            try:
                model_ts = datetime.fromisoformat(model_ts)
            except (ValueError, TypeError):
                model_ts = None

        if row['suitable']:
            # Successful valuation
            valuation = {
                'suitable': True,
                'fair_value': row['fair_value'],
                'current_price': row['current_price'],
                'margin_of_safety': row['margin_of_safety'],
                'upside': row['upside_pct'],
                'confidence': row['confidence'],
                'timestamp': model_ts.isoformat() if model_ts else None,
            }

            # Parse details JSON if present (JSONB comes back as dict already)
            if row['details_json']:
                details = row['details_json']
                if isinstance(details, str):
                    try:
                        details = json.loads(details)
                    except (json.JSONDecodeError, TypeError):
                        details = {}
                valuation['details'] = details

            stocks[ticker]['valuations'][model_name] = valuation
            valuation_count += 1

            # Track latest price used in valuations for dashboard price column
            if row['current_price'] is not None and row['timestamp'] is not None:
                try:
                    ts = row['timestamp']
                    if isinstance(ts, str):
                        ts = datetime.fromisoformat(ts)
                except (ValueError, TypeError):
                    ts = None

                prev = latest_price_by_ticker.get(ticker)
                if ts is not None:
                    if not prev or ts > prev['timestamp']:
                        latest_price_by_ticker[ticker] = {
                            'price': row['current_price'],
                            'timestamp': ts
                        }
        else:
            # For LLM analysis, load full data even when not "suitable" (WATCH/PASS still have valid analysis)
            if model_name == 'llm_deep_analysis' and row['fair_value'] and row['details_json']:
                valuation = {
                    'suitable': False,
                    'fair_value': row['fair_value'],
                    'current_price': row['current_price'],
                    'upside': row['upside_pct'],
                    'confidence': row['confidence'],
                    'timestamp': model_ts.isoformat() if model_ts else None,
                }
                details = row['details_json']
                if isinstance(details, str):
                    try:
                        details = json.loads(details)
                    except (json.JSONDecodeError, TypeError):
                        details = {}
                valuation['details'] = details
                stocks[ticker]['valuations'][model_name] = valuation
            else:
                # Failed valuation
                stocks[ticker]['valuations'][model_name] = {
                    'suitable': False,
                    'error': row['error_message'],
                    'reason': row['failure_reason'],
                    'timestamp': model_ts.isoformat() if model_ts else None,
                }

    # Override displayed current price with the latest valuation price when available
    for ticker, price_data in latest_price_by_ticker.items():
        stocks[ticker]['current_price'] = price_data['price']

    # Load insider signals (single batched query set instead of N+1 per ticker)
    insider_count = 0
    try:
        from invest.data.insider_db import compute_all_insider_signals, _no_insider_data
        insider_signals = compute_all_insider_signals(conn)
        for ticker in stocks:
            signal = insider_signals.get(ticker) or _no_insider_data()
            stocks[ticker]['insider'] = signal
            if signal.get('has_data'):
                insider_count += 1
    except Exception as exc:
        print(f'  Insider data not available: {exc}')

    # Load politician signals (single batched query instead of N+1 per ticker)
    politician_count = 0
    try:
        from invest.data.politician_db import compute_all_politician_signals, _no_politician_data
        politician_signals = compute_all_politician_signals(conn)
        for ticker in stocks:
            signal = politician_signals.get(ticker) or _no_politician_data()
            stocks[ticker]['politician'] = signal
            if signal.get('has_data'):
                politician_count += 1
    except Exception as exc:
        print(f'  Politician data not available: {exc}')

    conn.close()

    print(f'Loaded {valuation_count} successful valuations, '
          f'{insider_count} insider signals, '
          f'{politician_count} politician signals')

    return stocks


def main():
    """Regenerate dashboard HTML from database."""

    print('🔄 Regenerating dashboard HTML from database...')
    print('=' * 60)

    # Load all data from database (ONLY source)
    print('\n📂 Loading data from database...')
    stocks_data = load_stocks_from_database()

    # Count predictions by model
    model_counts = {}
    for stock in stocks_data.values():
        for model_name, valuation in stock.get('valuations', {}).items():
            if valuation.get('suitable'):
                model_counts[model_name] = model_counts.get(model_name, 0) + 1

    print('\nValuation counts by model:')
    for model_name, count in sorted(model_counts.items()):
        print(f'  {model_name:20s}: {count:3d} successful')

    # Generate HTML
    print('\n🎨 Generating HTML...')
    generator = HTMLGenerator()

    # Create progress_data structure for the HTML generator
    progress_data = {
        'total_analyzed': len(stocks_data),
        'successful': len(stocks_data),
        'failed': 0
    }

    html = generator.generate_dashboard_html(stocks_data, progress_data)

    # Save HTML
    output_path = project_root / 'dashboard' / 'valuation_dashboard.html'
    with open(output_path, 'w') as f:
        f.write(html)

    print(f'\n✅ Dashboard HTML saved: {output_path}')
    print(f'   Total stocks: {len(stocks_data)}')
    print(f'   Total valuations: {sum(model_counts.values())}')
    print('\n💡 Open in browser: file://{}'.format(output_path.absolute()))

    return 0


if __name__ == '__main__':
    sys.exit(main())
