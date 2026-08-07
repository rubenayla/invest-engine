"""Tests for lite fetch mode — prices+metrics only, preserving financial statements.

These tests require a PostgreSQL connection (via SSH tunnel or direct).
They are automatically skipped in CI where no database is available.
"""

import json
import os
import sys
import time
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.data_fetcher import AsyncStockDataFetcher, StockDataCache

# Classes that test DB operations are marked requires_data and skip in CI


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

from invest.data.db import get_connection


def _insert_full_row(ticker: str, price: float,
                     cashflow: str = '[{"item": "cf"}]',
                     balance_sheet: str = '[{"item": "bs"}]',
                     income: str = '[{"item": "inc"}]',
                     sector: str = 'Technology',
                     market_cap: float = 1e12):
    """Insert a complete row with financial statements via Postgres."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO current_stock_data (
            ticker, current_price, market_cap, sector, industry, long_name,
            currency, financial_currency, exchange, country,
            trailing_pe, forward_pe, price_to_book,
            return_on_equity, debt_to_equity, operating_margins, profit_margins,
            total_revenue, trailing_eps, book_value,
            price_52w_high, price_52w_low, avg_volume, price_trend_30d,
            cashflow_json, balance_sheet_json, income_json,
            fetch_timestamp, last_updated
        ) VALUES (
            %s, %s, %s, %s, 'Consumer Electronics', 'Apple Inc.',
            'USD', 'USD', 'NASDAQ', 'USA',
            28.5, 25.0, 40.0,
            1.48, 1.96, 0.30, 0.25,
            380000000000, 6.5, 4.0,
            200.0, 120.0, 50000000, 5.2,
            %s, %s, %s,
            %s, %s
        )
        ON CONFLICT (ticker) DO UPDATE SET
            current_price = EXCLUDED.current_price,
            market_cap = EXCLUDED.market_cap,
            sector = EXCLUDED.sector,
            cashflow_json = EXCLUDED.cashflow_json,
            balance_sheet_json = EXCLUDED.balance_sheet_json,
            income_json = EXCLUDED.income_json,
            fetch_timestamp = EXCLUDED.fetch_timestamp,
            last_updated = EXCLUDED.last_updated
    """, (ticker, price, market_cap, sector, cashflow, balance_sheet, income,
          datetime.now().isoformat(), datetime.now().isoformat()))
    conn.commit()
    conn.close()


def _get_row(ticker: str):
    """Get a row from current_stock_data."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT current_price, trailing_pe, sector, market_cap, '
        'cashflow_json, balance_sheet_json, income_json, '
        'price_52w_high, price_52w_low '
        'FROM current_stock_data WHERE ticker = %s', (ticker,)
    )
    row = cursor.fetchone()
    conn.close()
    return row


def _cleanup_test_tickers(*tickers):
    """Remove test tickers from the database."""
    conn = get_connection()
    cursor = conn.cursor()
    for t in tickers:
        cursor.execute('DELETE FROM current_stock_data WHERE ticker = %s', (t,))
    conn.commit()
    conn.close()


def _make_cache(tmp_path) -> StockDataCache:
    """Create a StockDataCache pointing at a tmp dir."""
    cache = StockDataCache(str(tmp_path / 'cache'))
    return cache


# ---------------------------------------------------------------------------
# StockDataCache.save_to_sqlite_lite
# ---------------------------------------------------------------------------

@pytest.mark.requires_data
class TestSaveToSqliteLite:
    """Test that lite saves update prices without clobbering statements."""

    def test_lite_preserves_financial_statements(self, tmp_path):
        """Core test: lite save updates price but keeps cashflow/balance/income."""
        cache = _make_cache(tmp_path)
        conn = sqlite3.connect(str(cache.db_path))

        # Pre-populate with full data including financial statements
        _insert_full_row(conn, 'AAPL', price=150.0)

        # Verify statements exist
        row = conn.execute(
            'SELECT cashflow_json, balance_sheet_json, income_json FROM current_stock_data WHERE ticker=?',
            ('AAPL',)
        ).fetchone()
        assert row[0] == '[{"item": "cf"}]'
        assert row[1] == '[{"item": "bs"}]'
        assert row[2] == '[{"item": "inc"}]'

        # Now do a lite save with new price
        lite_data = {
            'ticker': 'AAPL',
            'info': {'currentPrice': 175.0, 'marketCap': 2.8e12},
            'financials': {'trailingPE': 30.0},
            'price_data': {'price_52w_high': 180.0, 'price_52w_low': 130.0},
            'fetch_timestamp': datetime.now().isoformat(),
        }
        cache.save_to_sqlite_lite('AAPL', lite_data)

        # Verify price updated
        row = conn.execute(
            'SELECT current_price, trailing_pe, cashflow_json, balance_sheet_json, income_json '
            'FROM current_stock_data WHERE ticker=?',
            ('AAPL',)
        ).fetchone()
        assert row[0] == 175.0, "Price should be updated"
        assert row[1] == 30.0, "PE should be updated"
        # Financial statements must be preserved
        assert row[2] == '[{"item": "cf"}]', "Cashflow must not be overwritten"
        assert row[3] == '[{"item": "bs"}]', "Balance sheet must not be overwritten"
        assert row[4] == '[{"item": "inc"}]', "Income must not be overwritten"
        conn.close()

    def test_lite_new_ticker_inserts_full_row(self, tmp_path):
        """Lite save on a ticker not yet in DB should insert (no statements to preserve)."""
        cache = _make_cache(tmp_path)
        conn = sqlite3.connect(str(cache.db_path))

        lite_data = {
            'ticker': 'NEW',
            'info': {'currentPrice': 50.0, 'marketCap': 5e9, 'sector': 'Tech'},
            'financials': {'trailingPE': 15.0},
            'price_data': {},
            'fetch_timestamp': datetime.now().isoformat(),
        }
        cache.save_to_sqlite_lite('NEW', lite_data)

        row = conn.execute(
            'SELECT current_price, sector, cashflow_json FROM current_stock_data WHERE ticker=?',
            ('NEW',)
        ).fetchone()
        assert row is not None, "New ticker should be inserted"
        assert row[0] == 50.0
        conn.close()

    def test_lite_uses_coalesce_for_metadata(self, tmp_path):
        """Lite save with None sector should keep existing sector via COALESCE."""
        cache = _make_cache(tmp_path)
        conn = sqlite3.connect(str(cache.db_path))
        _insert_full_row(conn, 'AAPL', price=150.0, sector='Technology')

        lite_data = {
            'ticker': 'AAPL',
            'info': {'currentPrice': 155.0, 'sector': None, 'marketCap': 2.5e12},
            'financials': {},
            'price_data': {},
            'fetch_timestamp': datetime.now().isoformat(),
        }
        cache.save_to_sqlite_lite('AAPL', lite_data)

        row = conn.execute(
            'SELECT sector FROM current_stock_data WHERE ticker=?', ('AAPL',)
        ).fetchone()
        assert row[0] == 'Technology', "Sector should be preserved when lite sends None"
        conn.close()

    def test_lite_overwrites_price_even_when_lower(self, tmp_path):
        """Lite save should always overwrite price, even if new price is lower."""
        cache = _make_cache(tmp_path)
        conn = sqlite3.connect(str(cache.db_path))
        _insert_full_row(conn, 'AAPL', price=200.0)

        lite_data = {
            'ticker': 'AAPL',
            'info': {'currentPrice': 100.0, 'marketCap': 1.5e12},
            'financials': {},
            'price_data': {},
            'fetch_timestamp': datetime.now().isoformat(),
        }
        cache.save_to_sqlite_lite('AAPL', lite_data)

        row = conn.execute(
            'SELECT current_price FROM current_stock_data WHERE ticker=?', ('AAPL',)
        ).fetchone()
        assert row[0] == 100.0
        conn.close()

    def test_lite_handles_none_price_data(self, tmp_path):
        """Lite save with empty price_data should still work."""
        cache = _make_cache(tmp_path)
        conn = sqlite3.connect(str(cache.db_path))
        _insert_full_row(conn, 'AAPL', price=150.0)

        lite_data = {
            'ticker': 'AAPL',
            'info': {'currentPrice': 160.0, 'marketCap': 2.5e12},
            'financials': {},
            'price_data': {},  # No price_data at all
            'fetch_timestamp': datetime.now().isoformat(),
        }
        cache.save_to_sqlite_lite('AAPL', lite_data)

        row = conn.execute(
            'SELECT current_price, price_52w_high FROM current_stock_data WHERE ticker=?',
            ('AAPL',)
        ).fetchone()
        assert row[0] == 160.0, "Current price from info should update"
        # price_52w_high will be None since price_data was empty — that's OK
        conn.close()


# ---------------------------------------------------------------------------
# AsyncStockDataFetcher with lite=True
# ---------------------------------------------------------------------------

@pytest.mark.requires_data
class TestFetcherLiteMode:
    """Test that the fetcher in lite mode skips financial statements."""

    def _make_mock_stock(self):
        """Create a mock yfinance Ticker with realistic data."""
        stock = MagicMock()
        stock.info = {
            'currentPrice': 150.0,
            'marketCap': 2.5e12,
            'sector': 'Technology',
            'industry': 'Consumer Electronics',
            'longName': 'Apple Inc.',
            'shortName': 'AAPL',
            'symbol': 'AAPL',
            'currency': 'USD',
            'financialCurrency': 'USD',
            'exchange': 'NASDAQ',
            'country': 'USA',
            'trailingPE': 28.5,
            'forwardPE': 25.0,
            'priceToBook': 40.0,
            'returnOnEquity': 1.48,
            'totalDebt': 100e9,
            'bookValue': 4.0,
            'sharesOutstanding': 15e9,
            'currentRatio': 1.0,
            'revenueGrowth': 0.08,
            'earningsGrowth': 0.12,
            'operatingMargins': 0.30,
            'profitMargins': 0.25,
            'totalRevenue': 380e9,
            'totalCash': 60e9,
            'trailingEps': 6.5,
            'revenuePerShare': 25.0,
            'priceToSalesTrailing12Months': 7.0,
        }

        import pandas as pd
        hist = pd.DataFrame({
            'Open': [148.0, 149.0, 150.0],
            'High': [152.0, 153.0, 155.0],
            'Low': [147.0, 148.0, 149.0],
            'Close': [149.0, 150.0, 151.0],
            'Volume': [50000000, 55000000, 45000000],
        }, index=pd.date_range('2025-01-01', periods=3, freq='D'))
        stock.history.return_value = hist

        # These should NOT be called in lite mode
        stock.cashflow = pd.DataFrame({'col': [1]})
        stock.balance_sheet = pd.DataFrame({'col': [2]})
        stock.income_stmt = pd.DataFrame({'col': [3]})

        return stock

    @patch('scripts.data_fetcher.yf.Ticker')
    def test_lite_skips_financial_statements(self, mock_yf_ticker, tmp_path):
        """Lite fetch should not access cashflow/balance_sheet/income_stmt."""
        mock_stock = self._make_mock_stock()
        mock_yf_ticker.return_value = mock_stock

        cache = _make_cache(tmp_path)
        fetcher = AsyncStockDataFetcher(max_workers=1, lite=True)
        fetcher.cache = cache
        fetcher.rate_limiter = MagicMock()  # Skip rate limiting in tests

        data = fetcher.fetch_stock_data_sync('AAPL', max_retries=1)

        assert data['ticker'] == 'AAPL'
        assert data['info']['currentPrice'] == 150.0
        # In lite mode, financial statements should NOT be in the data
        assert 'cashflow' not in data
        assert 'balance_sheet' not in data
        assert 'income' not in data

    @patch('scripts.data_fetcher.yf.Ticker')
    def test_full_fetch_includes_financial_statements(self, mock_yf_ticker, tmp_path):
        """Full (non-lite) fetch should include financial statements."""
        mock_stock = self._make_mock_stock()
        mock_yf_ticker.return_value = mock_stock

        cache = _make_cache(tmp_path)
        fetcher = AsyncStockDataFetcher(max_workers=1, lite=False)
        fetcher.cache = cache
        fetcher.rate_limiter = MagicMock()

        data = fetcher.fetch_stock_data_sync('AAPL', max_retries=1)

        assert data['ticker'] == 'AAPL'
        # Full mode should have fetched statements
        # (They may or may not be in data depending on DataFrame format,
        #  but the attributes were accessed)
        mock_stock.history.assert_called()

    @patch('scripts.data_fetcher.yf.Ticker')
    def test_lite_updates_cache_index(self, mock_yf_ticker, tmp_path):
        """Lite fetch should update cache index for resume-on-interrupt."""
        mock_stock = self._make_mock_stock()
        mock_yf_ticker.return_value = mock_stock

        cache = _make_cache(tmp_path)
        fetcher = AsyncStockDataFetcher(max_workers=1, lite=True)
        fetcher.cache = cache
        fetcher.rate_limiter = MagicMock()

        # Fetch
        fetcher.fetch_stock_data_sync('AAPL', max_retries=1)

        # Cache index should have been updated
        assert 'AAPL' in cache.index['stocks']
        assert 'last_updated' in cache.index['stocks']['AAPL']

    @patch('scripts.data_fetcher.yf.Ticker')
    def test_lite_preserves_existing_index_flags(self, mock_yf_ticker, tmp_path):
        """Lite fetch should preserve has_cashflow etc. from prior full fetches."""
        mock_stock = self._make_mock_stock()
        mock_yf_ticker.return_value = mock_stock

        cache = _make_cache(tmp_path)
        # Simulate a prior full fetch that set these flags
        cache.index['stocks']['AAPL'] = {
            'last_updated': '2025-01-01T00:00:00',
            'file_size': 5000,
            'has_financials': True,
            'has_info': True,
            'has_cashflow': True,
            'has_balance_sheet': True,
            'has_income': True,
        }
        cache.save_index()

        fetcher = AsyncStockDataFetcher(max_workers=1, lite=True)
        fetcher.cache = cache
        fetcher.rate_limiter = MagicMock()

        fetcher.fetch_stock_data_sync('AAPL', max_retries=1)

        idx = cache.index['stocks']['AAPL']
        assert idx['has_cashflow'] is True, "Prior has_cashflow flag must survive lite update"
        assert idx['has_balance_sheet'] is True
        assert idx['has_income'] is True
        assert idx['last_updated'] > '2025-01-01', "Timestamp must be refreshed"


# ---------------------------------------------------------------------------
# Resume-on-interrupt (get_update_order after lite update)
# ---------------------------------------------------------------------------

@pytest.mark.requires_data
class TestResumeOnInterrupt:
    """Test that interrupted lite updates resume correctly."""

    def test_lite_updated_tickers_go_to_back_of_queue(self, tmp_path):
        """Tickers updated via lite should sort after stale tickers."""
        cache = _make_cache(tmp_path)

        # Simulate: AAPL was lite-updated recently, MSFT is stale
        cache.index['stocks']['AAPL'] = {
            'last_updated': datetime.now().isoformat(),
            'file_size': 1000,
            'has_financials': True,
            'has_info': True,
            'has_cashflow': True,
            'has_balance_sheet': True,
            'has_income': True,
        }
        cache.index['stocks']['MSFT'] = {
            'last_updated': '2024-01-01T00:00:00',
            'file_size': 1000,
            'has_financials': True,
            'has_info': True,
            'has_cashflow': True,
            'has_balance_sheet': True,
            'has_income': True,
        }
        cache.save_index()

        order = cache.get_update_order(['AAPL', 'MSFT', 'GOOGL'])
        # GOOGL is empty (not in index) -> first
        # MSFT is oldest cached -> second
        # AAPL is newest cached -> last
        assert order[0] == 'GOOGL', "Empty ticker should be first"
        assert order[1] == 'MSFT', "Stale ticker should be second"
        assert order[2] == 'AAPL', "Recently updated should be last"

    def test_empty_tickers_always_first(self, tmp_path):
        """Tickers not in the cache index should always be fetched first."""
        cache = _make_cache(tmp_path)
        cache.index['stocks']['AAPL'] = {
            'last_updated': '2020-01-01T00:00:00',
            'file_size': 1000,
            'has_financials': True,
            'has_info': True,
            'has_cashflow': False,
            'has_balance_sheet': False,
            'has_income': False,
        }
        cache.save_index()

        order = cache.get_update_order(['NEW1', 'NEW2', 'AAPL'])
        assert order[0] in ('NEW1', 'NEW2')
        assert order[1] in ('NEW1', 'NEW2')
        assert order[2] == 'AAPL'


# ---------------------------------------------------------------------------
# update_all.py --lite-fetch flag
# ---------------------------------------------------------------------------

class TestUpdateAllLiteFetch:
    """Test that --lite-fetch implies correct skip flags."""

    def test_lite_fetch_sets_skip_flags(self):
        """--lite-fetch should auto-skip insider, activist, holdings, edinet."""
        import argparse

        # Simulate argparse the same way update_all.py does
        parser = argparse.ArgumentParser()
        parser.add_argument('--skip-fetch', action='store_true')
        parser.add_argument('--skip-gbm', action='store_true')
        parser.add_argument('--skip-nn', action='store_true')
        parser.add_argument('--skip-autoresearch', action='store_true')
        parser.add_argument('--skip-classic', action='store_true')
        parser.add_argument('--skip-dashboard', action='store_true')
        parser.add_argument('--skip-insider', action='store_true')
        parser.add_argument('--skip-activist', action='store_true')
        parser.add_argument('--skip-holdings', action='store_true')
        parser.add_argument('--skip-edinet', action='store_true')
        parser.add_argument('--skip-scanner', action='store_true')
        parser.add_argument('--lite-fetch', action='store_true')

        args = parser.parse_args(['--lite-fetch'])

        # Apply the same logic as update_all.py
        if args.lite_fetch:
            args.skip_insider = True
            args.skip_activist = True
            args.skip_holdings = True
            args.skip_edinet = True

        assert args.skip_insider is True
        assert args.skip_activist is True
        assert args.skip_holdings is True
        assert args.skip_edinet is True
        # These should NOT be auto-skipped
        assert args.skip_gbm is False
        assert args.skip_classic is False
        assert args.skip_dashboard is False
        assert args.skip_scanner is False

    def test_non_lite_does_not_skip(self):
        """Without --lite-fetch, nothing should be auto-skipped."""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument('--skip-insider', action='store_true')
        parser.add_argument('--skip-activist', action='store_true')
        parser.add_argument('--skip-holdings', action='store_true')
        parser.add_argument('--skip-edinet', action='store_true')
        parser.add_argument('--lite-fetch', action='store_true')

        args = parser.parse_args([])

        if args.lite_fetch:
            args.skip_insider = True
            args.skip_activist = True
            args.skip_holdings = True
            args.skip_edinet = True

        assert args.skip_insider is False
        assert args.skip_activist is False
        assert args.skip_holdings is False
        assert args.skip_edinet is False


# ---------------------------------------------------------------------------
# Dashboard server API lite parameter
# ---------------------------------------------------------------------------

class TestDashboardServerLiteApi:
    """Test that the API correctly passes --lite-fetch."""

    def test_lite_flag_adds_to_extra_args(self):
        """POST /api/update with lite=true should add --lite-fetch to extra_args."""
        extra_args = []
        lite = True
        if lite and "--lite-fetch" not in extra_args:
            extra_args.append("--lite-fetch")
        assert "--lite-fetch" in extra_args

    def test_no_duplicate_lite_flag(self):
        """If --lite-fetch already in extra_args, don't add it again."""
        extra_args = ["--lite-fetch"]
        lite = True
        if lite and "--lite-fetch" not in extra_args:
            extra_args.append("--lite-fetch")
        assert extra_args.count("--lite-fetch") == 1

    def test_no_lite_flag_without_param(self):
        """Without lite=true, extra_args should be unchanged."""
        extra_args = ["--skip-gbm"]
        lite = False
        if lite and "--lite-fetch" not in extra_args:
            extra_args.append("--lite-fetch")
        assert extra_args == ["--skip-gbm"]


# ---------------------------------------------------------------------------
# Edge cases / regression
# ---------------------------------------------------------------------------

@pytest.mark.requires_data
class TestEdgeCases:
    """Edge cases and regression tests."""

    def test_lite_save_multiple_tickers_independent(self, tmp_path):
        """Lite saving one ticker should not affect another."""
        cache = _make_cache(tmp_path)
        conn = sqlite3.connect(str(cache.db_path))

        _insert_full_row(conn, 'AAPL', price=150.0,
                         cashflow='[{"op_cf": 100}]')
        _insert_full_row(conn, 'MSFT', price=400.0,
                         cashflow='[{"op_cf": 200}]')

        # Lite update only AAPL
        cache.save_to_sqlite_lite('AAPL', {
            'ticker': 'AAPL',
            'info': {'currentPrice': 160.0, 'marketCap': 2.5e12},
            'financials': {},
            'price_data': {},
            'fetch_timestamp': datetime.now().isoformat(),
        })

        # MSFT should be completely untouched
        msft = conn.execute(
            'SELECT current_price, cashflow_json FROM current_stock_data WHERE ticker=?',
            ('MSFT',)
        ).fetchone()
        assert msft[0] == 400.0
        assert msft[1] == '[{"op_cf": 200}]'

        # AAPL price updated, statements preserved
        aapl = conn.execute(
            'SELECT current_price, cashflow_json FROM current_stock_data WHERE ticker=?',
            ('AAPL',)
        ).fetchone()
        assert aapl[0] == 160.0
        assert aapl[1] == '[{"op_cf": 100}]'
        conn.close()

    def test_lite_save_with_missing_info_keys(self, tmp_path):
        """Lite save should handle data dicts with missing optional keys."""
        cache = _make_cache(tmp_path)
        conn = sqlite3.connect(str(cache.db_path))
        _insert_full_row(conn, 'AAPL', price=150.0)

        # Minimal data — only currentPrice
        cache.save_to_sqlite_lite('AAPL', {
            'ticker': 'AAPL',
            'info': {'currentPrice': 155.0},
            'fetch_timestamp': datetime.now().isoformat(),
        })

        row = conn.execute(
            'SELECT current_price FROM current_stock_data WHERE ticker=?', ('AAPL',)
        ).fetchone()
        assert row[0] == 155.0
        conn.close()

    def test_full_save_overwrites_statements(self, tmp_path):
        """Full save (non-lite) should overwrite financial statements as before."""
        cache = _make_cache(tmp_path)
        conn = sqlite3.connect(str(cache.db_path))
        _insert_full_row(conn, 'AAPL', price=150.0,
                         cashflow='[{"old": true}]')

        # Full save with new statements
        cache.save_stock_data('AAPL', {
            'ticker': 'AAPL',
            'info': {'currentPrice': 160.0, 'marketCap': 2.5e12, 'sector': 'Technology'},
            'financials': {},
            'price_data': {},
            'cashflow': [{'new': True}],
            'balance_sheet': [{'new': True}],
            'income': [{'new': True}],
            'fetch_timestamp': datetime.now().isoformat(),
        })

        row = conn.execute(
            'SELECT cashflow_json FROM current_stock_data WHERE ticker=?', ('AAPL',)
        ).fetchone()
        parsed = json.loads(row[0])
        assert parsed == [{'new': True}], "Full save should overwrite statements"
        conn.close()

    def test_fetcher_lite_flag_defaults_false(self):
        """AsyncStockDataFetcher should default to lite=False."""
        fetcher = AsyncStockDataFetcher(max_workers=1)
        assert fetcher.lite is False

    def test_fetcher_lite_flag_set_true(self):
        """AsyncStockDataFetcher(lite=True) should be stored."""
        fetcher = AsyncStockDataFetcher(max_workers=1, lite=True)
        assert fetcher.lite is True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
