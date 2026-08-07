#!/usr/bin/env python3
"""
Run classic valuation models (DCF, RIM, etc.) on all stocks in database.

This script:
- Gets stock list from current_stock_data table (database is ONLY source)
- Loads stock data from PostgreSQL database
- Runs classic valuation models (DCF, Enhanced DCF, RIM, Simple Ratios, etc.)
- Saves predictions to valuation_results table
"""

import json
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / 'src'))

from invest.data.db import get_connection
from invest.data.stock_data_reader import StockDataReader
from invest.valuation.base import ModelNotSuitableError
from invest.valuation.model_registry import ModelRegistry

# Models to run (excluding sector-specific and ensemble models for now)
# Format: (registry_name, db_name)
# NOTE: db_name must match what html_generator.py expects!
MODELS_TO_RUN = [
    ('dcf', 'dcf'),
    ('dcf_enhanced', 'dcf_enhanced'),  # HTML expects 'dcf_enhanced'
    ('rim', 'rim'),
    ('simple_ratios', 'simple_ratios'),
    ('growth_dcf', 'growth_dcf'),
    ('multi_stage_dcf', 'multi_stage_dcf'),
]


CONFIDENCE_MAP = {'very_high': 0.95, 'high': 0.85, 'medium': 0.70, 'low': 0.50, 'very_low': 0.30}


def save_to_database(conn, ticker: str, model_name: str, result: dict):
    """Save valuation result to valuation_results table."""

    cursor = conn.cursor()

    if result.get('suitable'):
        # Successful valuation
        details_json = json.dumps(result.get('details', {}))

        cursor.execute('''
            INSERT INTO valuation_results (
                ticker, model_name, fair_value, current_price,
                margin_of_safety, upside_pct, suitable,
                confidence, details_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (ticker, model_name) DO UPDATE SET
                fair_value = EXCLUDED.fair_value,
                current_price = EXCLUDED.current_price,
                margin_of_safety = EXCLUDED.margin_of_safety,
                upside_pct = EXCLUDED.upside_pct,
                suitable = EXCLUDED.suitable,
                confidence = EXCLUDED.confidence,
                details_json = EXCLUDED.details_json,
                timestamp = NOW()
        ''', (
            ticker,
            model_name,
            result['fair_value'],
            result['current_price'],
            result['margin_of_safety'],
            result['upside'],
            True,
            CONFIDENCE_MAP.get(result.get('confidence', 'medium'), 0.70),
            details_json
        ))
    else:
        # Failed valuation
        cursor.execute('''
            INSERT INTO valuation_results (
                ticker, model_name, suitable, error_message, failure_reason
            ) VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (ticker, model_name) DO UPDATE SET
                suitable = EXCLUDED.suitable,
                error_message = EXCLUDED.error_message,
                failure_reason = EXCLUDED.failure_reason,
                fair_value = NULL,
                current_price = NULL,
                margin_of_safety = NULL,
                upside_pct = NULL,
                confidence = NULL,
                details_json = NULL,
                timestamp = NOW()
        ''', (
            ticker,
            model_name,
            False,
            result.get('error', 'Unknown error'),
            result.get('reason', 'Unknown reason')
        ))

    conn.commit()


def load_stock_data(ticker: str, reader: StockDataReader) -> Optional[dict]:
    """
    Load stock data from database and convert to model-compatible format.

    Converts JSON-stored financial statements back to pandas DataFrames
    that valuation models expect.
    """
    cache_data = reader.get_stock_data(ticker)
    if not cache_data:
        return None

    # Convert JSON financial statements back to DataFrames
    # Models expect: {info: dict, cashflow: DataFrame, balance_sheet: DataFrame, income: DataFrame}
    # StockDataReader already merges financials into info, so just use it directly
    stock_data = {
        'info': cache_data.get('info', {}),
        'market_data': reader.get_market_inputs(
            ticker=ticker,
            min_price_points=252,
            max_price_age_days=30,
            max_rate_age_days=30,
        ),
    }

    # Convert cashflow from list of records to DataFrame
    # yfinance format: rows=metrics (Free Cash Flow, etc), columns=dates (timestamps)
    if 'cashflow' in cache_data and cache_data['cashflow']:
        try:
            df = pd.DataFrame(cache_data['cashflow'])
            # Set the metric name column as index
            if 'index' in df.columns:
                df = df.set_index('index')
            # No transpose needed - orient=records already has correct orientation
            stock_data['cashflow'] = df
        except Exception as e:
            print(f'Warning: Could not convert cashflow for {ticker}: {e}')

    # Convert balance_sheet from list of records to DataFrame
    if 'balance_sheet' in cache_data and cache_data['balance_sheet']:
        try:
            df = pd.DataFrame(cache_data['balance_sheet'])
            if 'index' in df.columns:
                df = df.set_index('index')
            stock_data['balance_sheet'] = df
        except Exception as e:
            print(f'Warning: Could not convert balance_sheet for {ticker}: {e}')

    # Convert income statement from list of records to DataFrame
    if 'income' in cache_data and cache_data['income']:
        try:
            df = pd.DataFrame(cache_data['income'])
            if 'index' in df.columns:
                df = df.set_index('index')
            stock_data['income'] = df
        except Exception as e:
            print(f'Warning: Could not convert income for {ticker}: {e}')

    return stock_data


def run_valuation(registry: ModelRegistry, registry_name: str, ticker: str, stock_data: dict) -> Optional[dict]:
    """
    Run a single valuation model on a stock.

    Parameters
    ----------
    registry : ModelRegistry
        Shared model registry instance
    registry_name : str
        Model name as used in the ModelRegistry
    ticker : str
        Stock ticker
    stock_data : dict
        Stock data from cache

    Returns
    -------
    dict
        Valuation result or error information
    """

    try:
        # Get model instance
        model = registry.get_model(registry_name)

        # Check if model is suitable for this stock
        if not model.is_suitable(ticker, stock_data):
            reason = 'Data requirements not met'
            if hasattr(model, 'get_suitability_reason'):
                model_reason = model.get_suitability_reason()
                if model_reason:
                    reason = model_reason
            raise ModelNotSuitableError(registry_name, ticker, reason)

        # Validate inputs
        model._validate_inputs(ticker, stock_data)

        # Run valuation
        result = model._calculate_valuation(ticker, stock_data)

        # Format result for dashboard
        details = {}
        if hasattr(result, 'inputs'):
            details.update(result.inputs)
        if hasattr(result, 'outputs'):
            details.update(result.outputs)

        return {
            'fair_value': float(result.fair_value),
            'current_price': float(result.current_price),
            'margin_of_safety': float(result.margin_of_safety),
            'upside': float(((result.fair_value / result.current_price) - 1) * 100) if result.current_price > 0 else 0,
            'suitable': True,
            'confidence': result.confidence,
            'details': details
        }

    except ModelNotSuitableError as e:
        return {
            'suitable': False,
            'error': str(e),
            'reason': e.reason if hasattr(e, 'reason') else 'Model not suitable for this stock'
        }

    except Exception as e:
        return {
            'suitable': False,
            'error': str(e),
            'reason': f'Unexpected error: {type(e).__name__}'
        }


def main():
    """Run classic valuations on all stocks in database."""

    print('🚀 Running Classic Valuation Models')
    print('=' * 60)
    print(f'Models: {", ".join(db_name for _, db_name in MODELS_TO_RUN)}')
    print('=' * 60)

    # Initialize stock data reader
    print('\n📦 Initializing stock data reader...')
    reader = StockDataReader()

    # Get list of tickers from database
    print('\n📂 Loading tickers from database...')
    registry = ModelRegistry()
    conn = get_connection()
    try:
        query = 'SELECT DISTINCT ticker FROM current_stock_data WHERE current_price IS NOT NULL'
        cursor = conn.cursor()
        cursor.execute(query)
        tickers = [row[0] for row in cursor.fetchall()]
        print(f'   Found {len(tickers)} tickers with price data')

        # Statistics
        stats = {db_name: {'success': 0, 'unsuitable': 0, 'error': 0, 'cache_miss': 0} for _, db_name in MODELS_TO_RUN}

        # Run valuations on each stock
        print('\n🔄 Running valuations...')

        for i, ticker in enumerate(tickers):
            # Load stock data from database
            stock_data = load_stock_data(ticker, reader)

            if not stock_data:
                # Save "no data" failure for all models
                for _, db_name in MODELS_TO_RUN:
                    stats[db_name]['cache_miss'] += 1
                    error_result = {
                        'suitable': False,
                        'error': 'Stock data not found in database',
                        'reason': 'Missing stock data'
                    }
                    save_to_database(conn, ticker, db_name, error_result)
                continue

            # Run each model
            for registry_name, db_name in MODELS_TO_RUN:
                try:
                    result = run_valuation(registry, registry_name, ticker, stock_data)

                    # Save to database
                    save_to_database(conn, ticker, db_name, result)

                    if result.get('suitable', False):
                        stats[db_name]['success'] += 1
                    else:
                        if 'error' in result:
                            stats[db_name]['error'] += 1
                        else:
                            stats[db_name]['unsuitable'] += 1

                except Exception as e:
                    conn.rollback()
                    print(f'   [{i+1}/{len(tickers)}] {ticker} - {db_name}: Unexpected error - {str(e)}')
                    error_result = {
                        'suitable': False,
                        'error': str(e),
                        'reason': f'Unexpected error: {type(e).__name__}'
                    }
                    try:
                        save_to_database(conn, ticker, db_name, error_result)
                    except Exception:
                        conn.rollback()
                    stats[db_name]['error'] += 1

            # Progress update
            if (i + 1) % 50 == 0:
                print(f'   [{i+1}/{len(tickers)}] Processed {ticker}...')
    finally:
        conn.close()

    # Summary
    print('\n✅ Classic valuations complete!')
    print('=' * 60)
    print('📊 Results by model:')
    print()

    for _, db_name in MODELS_TO_RUN:
        model_stats = stats[db_name]
        total = sum(model_stats.values())
        print(f'{db_name:20} - Success: {model_stats["success"]:3} | '
              f'Unsuitable: {model_stats["unsuitable"]:3} | '
              f'Errors: {model_stats["error"]:3} | '
              f'Cache miss: {model_stats["cache_miss"]:3} | '
              f'Total: {total:3}')

    print()
    print(f'Total stocks processed: {len(tickers)}')
    print('💾 Saved to database: valuation_results table')
    print('💡 Run dashboard.py to update the dashboard HTML')

    return 0


if __name__ == '__main__':
    sys.exit(main())
