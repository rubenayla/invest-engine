#!/usr/bin/env python
"""
Asynchronous Data Fetcher Service

This service fetches stock data independently from analysis.
Data is cached locally for offline analysis.

Usage:
    uv run python scripts/data_fetcher.py --universe sp500 --max-stocks 1000
"""

import argparse
import asyncio
import json
import logging
import math
import os

# Import currency converter (dynamically since it's in scripts/)
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from pathlib import Path as PathLib
from typing import Dict, List, Optional, Set

import yfinance as yf

# Ensure src/ is on sys.path for invest.data.db imports
_src_dir = str(PathLib(__file__).parent.parent / 'src')
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

if str(PathLib(__file__).parent) not in sys.path:
    sys.path.insert(0, str(PathLib(__file__).parent))
from currency_converter import convert_financial_statements_to_usd, convert_financials_to_usd

from invest.data.db import get_connection

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def _clean_json(obj) -> str:
    """Serialize to JSON, replacing NaN/Infinity with null (Postgres rejects them)."""
    def _sanitize(v):
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return None
        if isinstance(v, dict):
            return {k: _sanitize(val) for k, val in v.items()}
        if isinstance(v, list):
            return [_sanitize(item) for item in v]
        return v
    return json.dumps(_sanitize(obj))


class StockDataCache:
    """Manages local stock data cache"""

    def __init__(self, cache_dir: str = 'data/stock_cache'):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.index_file = self.cache_dir / 'cache_index.json'
        self.load_index()

    def load_index(self):
        """Load cache index tracking what data we have"""
        if self.index_file.exists():
            with open(self.index_file, 'r') as f:
                self.index = json.load(f)
        else:
            self.index = {
                'stocks': {},
                'last_updated': datetime.now().isoformat(),
                'version': '1.0'
            }

    def save_index(self):
        """Save cache index atomically to prevent corruption"""
        self.index['last_updated'] = datetime.now().isoformat()

        # Write to temporary file first, then atomic rename
        temp_file = self.index_file.with_suffix('.tmp')
        try:
            with open(temp_file, 'w') as f:
                json.dump(self.index, f, indent=2)
            # Atomic rename prevents corruption from concurrent writes
            os.rename(temp_file, self.index_file)
        except Exception as e:
            # Clean up temp file if write failed
            if temp_file.exists():
                temp_file.unlink()
            raise e

    def get_update_order(self, tickers: List[str]) -> List[str]:
        """Get tickers in update order: broken/empty first, then oldest to newest"""
        empty_stocks = []
        broken_stocks = []
        cached_stocks = []

        for ticker in tickers:
            if ticker not in self.index['stocks']:
                empty_stocks.append(ticker)
            else:
                # Check if file is corrupted/empty (< 500 bytes)
                cache_file = self.cache_dir / f'{ticker}.json'
                if cache_file.exists() and cache_file.stat().st_size < 500:
                    broken_stocks.append(ticker)
                else:
                    cached_stocks.append(ticker)

        # Sort cached stocks by age (oldest first)
        cached_stocks.sort(key=lambda t: self.index['stocks'][t]['last_updated'])

        # Priority: 1) Empty (not in index), 2) Broken (< 500 bytes), 3) Oldest to newest
        return empty_stocks + broken_stocks + cached_stocks

    def get_cached_data(self, ticker: str) -> Optional[Dict]:
        """Get cached data for a ticker"""
        cache_file = self.cache_dir / f'{ticker}.json'
        if cache_file.exists():
            with open(cache_file, 'r') as f:
                return json.load(f)
        return None

    def save_to_sqlite_lite(self, ticker: str, data: Dict):
        """Save only price/metric fields to PostgreSQL, preserving existing financial statements."""
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()

            info = data.get('info', {})
            financials = data.get('financials', {})
            price_data = data.get('price_data', {})

            # Check if ticker already exists
            cursor.execute(
                'SELECT 1 FROM current_stock_data WHERE ticker = %s', (ticker,)
            )
            exists = cursor.fetchone()

            if exists:
                # UPDATE only price-related columns, keep financial statements intact
                cursor.execute('''
                    UPDATE current_stock_data SET
                        current_price = %s, market_cap = %s,
                        sector = COALESCE(%s, sector), industry = COALESCE(%s, industry),
                        long_name = COALESCE(%s, long_name), short_name = COALESCE(%s, short_name),
                        currency = COALESCE(%s, currency), financial_currency = COALESCE(%s, financial_currency),
                        exchange = COALESCE(%s, exchange), country = COALESCE(%s, country),
                        trailing_pe = %s, forward_pe = %s, price_to_book = %s,
                        return_on_equity = %s, debt_to_equity = %s, current_ratio = %s,
                        revenue_growth = %s, earnings_growth = %s,
                        operating_margins = %s, profit_margins = %s,
                        total_revenue = %s, total_cash = %s, total_debt = %s, shares_outstanding = %s,
                        trailing_eps = %s, book_value = %s, revenue_per_share = %s, price_to_sales_ttm = %s,
                        price_52w_high = %s, price_52w_low = %s, avg_volume = %s, price_trend_30d = %s,
                        fetch_timestamp = %s, last_updated = %s
                    WHERE ticker = %s
                ''', (
                    info.get('currentPrice'), info.get('marketCap'),
                    info.get('sector'), info.get('industry'),
                    info.get('longName'), info.get('shortName'),
                    info.get('currency'), info.get('financialCurrency'),
                    info.get('exchange'), info.get('country'),
                    financials.get('trailingPE'), financials.get('forwardPE'), financials.get('priceToBook'),
                    financials.get('returnOnEquity'), financials.get('debtToEquity'), financials.get('currentRatio'),
                    financials.get('revenueGrowth'), financials.get('earningsGrowth'),
                    financials.get('operatingMargins'), financials.get('profitMargins'),
                    financials.get('totalRevenue'), financials.get('totalCash'),
                    financials.get('totalDebt'), financials.get('sharesOutstanding'),
                    financials.get('trailingEps'), financials.get('bookValue'),
                    financials.get('revenuePerShare'), financials.get('priceToSalesTrailing12Months'),
                    price_data.get('price_52w_high'), price_data.get('price_52w_low'),
                    price_data.get('avg_volume'), price_data.get('price_trend_30d'),
                    data.get('fetch_timestamp', datetime.now().isoformat()),
                    datetime.now().isoformat(),
                    ticker,
                ))
            else:
                # New ticker — full insert (no statements to preserve)
                self._insert_full_row(cursor, ticker, data)

            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            logger.warning(f'{ticker}: Failed to save lite data to PostgreSQL: {e}')
        finally:
            if conn:
                conn.close()

    def _insert_full_row(self, cursor, ticker: str, data: Dict):
        """Insert a complete row into current_stock_data (upsert)."""
        info = data.get('info', {})
        financials = data.get('financials', {})
        price_data = data.get('price_data', {})

        cursor.execute('''
            INSERT INTO current_stock_data (
                ticker,
                current_price, market_cap, sector, industry, long_name, short_name,
                currency, financial_currency, exchange, country,
                trailing_pe, forward_pe, price_to_book, return_on_equity, debt_to_equity,
                current_ratio, revenue_growth, earnings_growth, operating_margins, profit_margins,
                total_revenue, total_cash, total_debt, shares_outstanding,
                trailing_eps, book_value, revenue_per_share, price_to_sales_ttm,
                price_52w_high, price_52w_low, avg_volume, price_trend_30d,
                cashflow_json, balance_sheet_json, income_json,
                fetch_timestamp, last_updated,
                exchange_rate_used, original_currency
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s
            )
            ON CONFLICT (ticker) DO UPDATE SET
                current_price = EXCLUDED.current_price,
                market_cap = EXCLUDED.market_cap,
                sector = EXCLUDED.sector,
                industry = EXCLUDED.industry,
                long_name = EXCLUDED.long_name,
                short_name = EXCLUDED.short_name,
                currency = EXCLUDED.currency,
                financial_currency = EXCLUDED.financial_currency,
                exchange = EXCLUDED.exchange,
                country = EXCLUDED.country,
                trailing_pe = EXCLUDED.trailing_pe,
                forward_pe = EXCLUDED.forward_pe,
                price_to_book = EXCLUDED.price_to_book,
                return_on_equity = EXCLUDED.return_on_equity,
                debt_to_equity = EXCLUDED.debt_to_equity,
                current_ratio = EXCLUDED.current_ratio,
                revenue_growth = EXCLUDED.revenue_growth,
                earnings_growth = EXCLUDED.earnings_growth,
                operating_margins = EXCLUDED.operating_margins,
                profit_margins = EXCLUDED.profit_margins,
                total_revenue = EXCLUDED.total_revenue,
                total_cash = EXCLUDED.total_cash,
                total_debt = EXCLUDED.total_debt,
                shares_outstanding = EXCLUDED.shares_outstanding,
                trailing_eps = EXCLUDED.trailing_eps,
                book_value = EXCLUDED.book_value,
                revenue_per_share = EXCLUDED.revenue_per_share,
                price_to_sales_ttm = EXCLUDED.price_to_sales_ttm,
                price_52w_high = EXCLUDED.price_52w_high,
                price_52w_low = EXCLUDED.price_52w_low,
                avg_volume = EXCLUDED.avg_volume,
                price_trend_30d = EXCLUDED.price_trend_30d,
                cashflow_json = EXCLUDED.cashflow_json,
                balance_sheet_json = EXCLUDED.balance_sheet_json,
                income_json = EXCLUDED.income_json,
                fetch_timestamp = EXCLUDED.fetch_timestamp,
                last_updated = EXCLUDED.last_updated,
                exchange_rate_used = EXCLUDED.exchange_rate_used,
                original_currency = EXCLUDED.original_currency
        ''', (
            ticker,
            info.get('currentPrice'), info.get('marketCap'), info.get('sector'),
            info.get('industry'), info.get('longName'), info.get('shortName'),
            info.get('currency'), info.get('financialCurrency'), info.get('exchange'), info.get('country'),
            financials.get('trailingPE'), financials.get('forwardPE'), financials.get('priceToBook'),
            financials.get('returnOnEquity'), financials.get('debtToEquity'), financials.get('currentRatio'),
            financials.get('revenueGrowth'), financials.get('earningsGrowth'), financials.get('operatingMargins'),
            financials.get('profitMargins'), financials.get('totalRevenue'), financials.get('totalCash'),
            financials.get('totalDebt'), financials.get('sharesOutstanding'), financials.get('trailingEps'),
            financials.get('bookValue'), financials.get('revenuePerShare'), financials.get('priceToSalesTrailing12Months'),
            price_data.get('price_52w_high'), price_data.get('price_52w_low'),
            price_data.get('avg_volume'), price_data.get('price_trend_30d'),
            _clean_json(data.get('cashflow', [])),
            _clean_json(data.get('balance_sheet', [])),
            _clean_json(data.get('income', [])),
            data.get('fetch_timestamp', datetime.now().isoformat()),
            datetime.now().isoformat(),
            financials.get('_exchange_rate_used'),
            financials.get('_original_currency')
        ))

    def save_to_sqlite(self, ticker: str, data: Dict):
        """Save stock data to PostgreSQL database"""
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()

            self._insert_full_row(cursor, ticker, data)

            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            logger.warning(f'{ticker}: Failed to save to PostgreSQL: {e}')
        finally:
            if conn:
                conn.close()

    def save_stock_data(self, ticker: str, data: Dict):
        """Save stock data to both JSON cache and PostgreSQL database"""
        # VALIDATION: Check if data is valid before saving
        if 'error' in data:
            logger.error(f'{ticker}: Skipping save - data fetch failed: {data.get("error")}')
            return

        # Check for minimum required fields
        info = data.get('info', {})
        if not info:
            logger.error(f'{ticker}: Skipping save - empty info dict')
            return
        if not info.get('currentPrice'):
            # Don't skip — currentPrice may be missing in fresh fetch for some
            # stocks (e.g., ADRs, delisted). Let the save proceed so other valid
            # fields (sector, financials, etc.) are still cached.
            logger.warning(f'{ticker}: currentPrice is missing — saving anyway')

        # Check if we have at least some data (not all None/empty)
        has_sector = info.get('sector') is not None
        has_market_cap = info.get('marketCap') is not None
        has_minimal_data = has_sector or has_market_cap

        if not has_minimal_data:
            logger.error(f'{ticker}: Skipping save - insufficient data (no sector, no market cap)')
            return

        logger.info(f'{ticker}: Data validation passed - saving to cache and database')

        cache_file = self.cache_dir / f'{ticker}.json'
        temp_file = cache_file.with_suffix('.tmp')

        # Add metadata
        data['_cache_metadata'] = {
            'ticker': ticker,
            'cached_at': datetime.now().isoformat(),
            'data_source': 'yfinance'
        }

        # Save to PostgreSQL first (source of truth)
        self.save_to_sqlite(ticker, data)

        # Save to JSON (best-effort backup). If this fails, SQLite still has
        # the data so we log a warning instead of raising.
        try:
            with open(temp_file, 'w') as f:
                json.dump(data, f, indent=2)
            os.rename(temp_file, cache_file)
        except Exception as e:
            logger.warning(f'{ticker}: PostgreSQL write succeeded but JSON write failed: {e}')
            if temp_file.exists():
                temp_file.unlink()

        # Update index
        self.index['stocks'][ticker] = {
            'last_updated': datetime.now().isoformat(),
            'file_size': cache_file.stat().st_size if cache_file.exists() else 0,
            'has_financials': 'financials' in data,
            'has_info': 'info' in data,
            'has_cashflow': 'cashflow' in data,
            'has_balance_sheet': 'balance_sheet' in data,
            'has_income': 'income' in data
        }
        self.save_index()

    def get_cached_tickers(self) -> Set[str]:
        """Get all tickers we have cached data for"""
        return set(self.index['stocks'].keys())


class TokenBucketRateLimiter:
    """Thread-safe token bucket rate limiter for Yahoo Finance."""

    def __init__(self, rate: float = 2.0, burst: int = 3):
        self.rate = rate
        self.burst = burst
        self._tokens = float(burst)
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """Block until a token is available."""
        while True:
            with self._lock:
                now = time.monotonic()
                elapsed = now - self._last_refill
                self._tokens = min(self.burst, self._tokens + elapsed * self.rate)
                self._last_refill = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
            time.sleep(0.05)


class AsyncStockDataFetcher:
    """Fetches stock data using thread pool (simplified)"""

    def __init__(self, max_workers: int = 10, lite: bool = False):
        self.cache = StockDataCache()
        self.max_workers = max_workers
        self.rate_limiter = TokenBucketRateLimiter(rate=2.0, burst=3)
        self.lite = lite

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    def fetch_stock_data_sync(self, ticker: str) -> Dict:
        """Fetch fresh data for a single stock — single attempt, no in-loop retry.

        Retries are handled at the pass level by fetch_multiple_stocks so a
        worker never sleeps idle on one ticker. On failure, returns an error
        dict; the caller decides whether to retry the ticker on a later pass.
        """
        try:
            logger.info(f"Fetching fresh data for {ticker}")

            # Fetch from yfinance
            self.rate_limiter.acquire()
            stock = yf.Ticker(ticker)

            # Get comprehensive data
            data = {
                'ticker': ticker,
                'info': {},
                'financials': {},
                'price_data': {},
                'fetch_timestamp': datetime.now().isoformat()
            }

            # Fetch stock info (required for everything else)
            self.rate_limiter.acquire()
            info = stock.info

            # Validate that info has real data — yfinance silently returns an
            # empty/partial dict on both rate-limit and 404 (delisted/wrong
            # suffix). currentPrice is the bare minimum.
            if not info or not info.get('currentPrice'):
                raise RuntimeError(
                    f"{ticker}: yfinance returned empty info (rate-limited or delisted)"
                )

            # Basic info (most important)
            data['info'] = {
                'currentPrice': info.get('currentPrice'),
                'marketCap': info.get('marketCap'),
                'sector': info.get('sector'),
                'industry': info.get('industry'),
                'longName': info.get('longName'),
                'shortName': info.get('shortName'),
                'symbol': info.get('symbol'),
                'currency': info.get('currency'),
                'financialCurrency': info.get('financialCurrency'),  # Added: explicit financial reporting currency
                'exchange': info.get('exchange'),
                'country': info.get('country')
            }

            # Key financial metrics
            try:
                # Calculate debt-to-equity ourselves - yfinance returns it as percentage (92.867)
                # but we store ratios as ratios (0.929), not percentages
                debt_to_equity = None
                total_debt = info.get('totalDebt')
                book_value = info.get('bookValue')
                shares_outstanding = info.get('sharesOutstanding')

                if total_debt and book_value and shares_outstanding and book_value > 0:
                    total_equity = book_value * shares_outstanding
                    if total_equity > 0:
                        debt_to_equity = total_debt / total_equity

                data['financials'] = {
                    'trailingPE': info.get('trailingPE'),
                    'forwardPE': info.get('forwardPE'),
                    'priceToBook': info.get('priceToBook'),
                    'returnOnEquity': info.get('returnOnEquity'),
                    'debtToEquity': debt_to_equity,  # Use calculated ratio, not yfinance's percentage
                    'currentRatio': info.get('currentRatio'),
                    'revenueGrowth': info.get('revenueGrowth'),
                    'earningsGrowth': info.get('earningsGrowth'),
                    'operatingMargins': info.get('operatingMargins'),
                    'profitMargins': info.get('profitMargins'),
                    'totalRevenue': info.get('totalRevenue'),
                    'totalCash': info.get('totalCash'),
                    'totalDebt': info.get('totalDebt'),
                    'sharesOutstanding': info.get('sharesOutstanding'),
                    # Per-share metrics needed by Simple Ratios model
                    'trailingEps': info.get('trailingEps'),
                    'bookValue': info.get('bookValue'),
                    'revenuePerShare': info.get('revenuePerShare'),
                    'priceToSalesTrailing12Months': info.get('priceToSalesTrailing12Months'),
                }

                # Convert foreign currency financials to USD
                data['financials'] = convert_financials_to_usd(data['info'], data['financials'])

            except Exception as e:
                logger.warning(f"Could not fetch financials for {ticker}: {e}")

            # Recent price data (for charts/trends)
            try:
                from datetime import timedelta
                self.rate_limiter.acquire()
                hist = stock.history(period='1y')
                if not hist.empty:
                    # Use calendar-day cutoff, not bar index, to handle
                    # holidays / missing trading days correctly.
                    cutoff_30d = hist.index[-1] - timedelta(days=30)
                    hist_30d = hist[hist.index >= cutoff_30d]
                    if len(hist_30d) >= 2:
                        trend_30d = float((hist_30d['Close'].iloc[-1] / hist_30d['Close'].iloc[0] - 1) * 100)
                    else:
                        trend_30d = None
                    data['price_data'] = {
                        'current_price': float(hist['Close'].iloc[-1]),
                        'price_52w_high': float(hist['High'].max()),
                        'price_52w_low': float(hist['Low'].min()),
                        'avg_volume': int(hist['Volume'].mean()),
                        'price_trend_30d': trend_30d,
                    }
            except Exception as e:
                logger.warning(f"Could not fetch price data for {ticker}: {e}")

            # Raw financial statements (for DCF/RIM valuation models)
            # Skipped in lite mode — statements change quarterly, not daily.
            if not self.lite:
                # NOTE: These raw statements are stored WITHOUT currency conversion.
                # For ADRs reporting in non-USD (e.g., JPY, EUR), values are in the
                # original financialCurrency. We store the currency alongside so
                # downstream consumers can detect and handle this. Automatic
                # conversion is too risky here — see convert_financial_statements_to_usd
                # below for the converted path.
                try:
                    import pandas as pd

                    # Store financialCurrency so JSON consumers know the unit
                    financial_currency = info.get('financialCurrency')
                    if financial_currency:
                        data['financial_statements_currency'] = financial_currency

                    # Cash flow statement
                    self.rate_limiter.acquire()
                    cashflow = stock.cashflow
                    if cashflow is not None and not cashflow.empty:
                        df = cashflow.reset_index()
                        df.columns = df.columns.astype(str)
                        for col in df.columns:
                            if pd.api.types.is_datetime64_any_dtype(df[col]):
                                df[col] = df[col].astype(str)
                        data['cashflow'] = df.to_dict(orient='records')

                    # Balance sheet
                    self.rate_limiter.acquire()
                    balance_sheet = stock.balance_sheet
                    if balance_sheet is not None and not balance_sheet.empty:
                        df = balance_sheet.reset_index()
                        df.columns = df.columns.astype(str)
                        for col in df.columns:
                            if pd.api.types.is_datetime64_any_dtype(df[col]):
                                df[col] = df[col].astype(str)
                        data['balance_sheet'] = df.to_dict(orient='records')

                    # Income statement
                    self.rate_limiter.acquire()
                    income_stmt = stock.income_stmt
                    if income_stmt is not None and not income_stmt.empty:
                        df = income_stmt.reset_index()
                        df.columns = df.columns.astype(str)
                        for col in df.columns:
                            if pd.api.types.is_datetime64_any_dtype(df[col]):
                                df[col] = df[col].astype(str)
                        data['income'] = df.to_dict(orient='records')

                    logger.info(f"Fetched financial statements for {ticker}")
                except Exception as e:
                    logger.warning(f"Could not fetch financial statements for {ticker}: {e}")

                # Convert financial statements if currency conversion was applied
                if data['financials'].get('_currency_converted'):
                    financial_currency = data['financials'].get('_original_currency')
                    exchange_rate = data['financials'].get('_exchange_rate_used')
                    if financial_currency and exchange_rate:
                        data = convert_financial_statements_to_usd(data, financial_currency, exchange_rate)

            # Cache the data (lite mode preserves existing financial statements in DB)
            if self.lite:
                self.cache.save_to_sqlite_lite(ticker, data)
                self.cache.index['stocks'][ticker] = {
                    'last_updated': datetime.now().isoformat(),
                    'file_size': self.cache.index.get('stocks', {}).get(ticker, {}).get('file_size', 0),
                    'has_financials': True,
                    'has_info': True,
                    'has_cashflow': self.cache.index.get('stocks', {}).get(ticker, {}).get('has_cashflow', False),
                    'has_balance_sheet': self.cache.index.get('stocks', {}).get(ticker, {}).get('has_balance_sheet', False),
                    'has_income': self.cache.index.get('stocks', {}).get(ticker, {}).get('has_income', False),
                }
                self.cache.save_index()
            else:
                self.cache.save_stock_data(ticker, data)

            return data

        except Exception as e:
            logger.warning(f"{ticker}: fetch failed: {e}")
            return {
                'ticker': ticker,
                'error': str(e),
                'fetch_timestamp': datetime.now().isoformat()
            }

    async def fetch_multiple_stocks(
        self,
        tickers: List[str],
        max_concurrent: int = 10,
        max_passes: int = 3,
    ) -> Dict[str, Dict]:
        """Fetch data for many stocks with pass-based retries.

        One worker = one ticker per attempt, no in-loop sleep. After each
        pass we retry just the tickers that failed, up to ``max_passes``
        passes. Whatever still fails after the last pass is left in the
        results with its error — those are the genuine failures.
        """
        results: Dict[str, Dict] = {}
        remaining = list(tickers)
        total = len(tickers)

        for pass_num in range(1, max_passes + 1):
            if not remaining:
                break

            logger.info(
                f"Pass {pass_num}/{max_passes}: fetching {len(remaining)} ticker(s)"
            )

            failed_this_pass: List[str] = []

            with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
                future_to_ticker = {
                    executor.submit(self.fetch_stock_data_sync, ticker): ticker
                    for ticker in remaining
                }

                completed = 0
                for future in as_completed(future_to_ticker):
                    ticker = future_to_ticker[future]
                    try:
                        data = future.result(timeout=120)
                    except Exception as e:
                        data = {
                            'ticker': ticker,
                            'error': str(e),
                            'fetch_timestamp': datetime.now().isoformat(),
                        }

                    if 'error' in data:
                        failed_this_pass.append(ticker)
                    else:
                        results[ticker] = data

                    completed += 1
                    done_total = len(results) + (
                        len(failed_this_pass) if pass_num == max_passes else 0
                    )
                    if completed % 10 == 0 or completed == len(future_to_ticker):
                        logger.info(
                            f"Pass {pass_num}: {completed}/{len(future_to_ticker)} "
                            f"(succeeded so far: {len(results)}/{total})"
                        )

                    # Keep last-seen error for the final report
                    if 'error' in data:
                        results[ticker] = data

            remaining = failed_this_pass
            if remaining:
                logger.info(
                    f"Pass {pass_num}/{max_passes} done. "
                    f"{len(remaining)} ticker(s) failed: {remaining[:10]}"
                    + (' ...' if len(remaining) > 10 else '')
                )

        if remaining:
            logger.error(
                f"Giving up on {len(remaining)} ticker(s) after {max_passes} passes: "
                f"{remaining[:20]}" + (' ...' if len(remaining) > 20 else '')
            )

        return results


def get_universe_tickers(universe: str) -> List[str]:
    """Get ticker list for a universe using dynamic index manager."""
    import sys
    from pathlib import Path

    # Add project root to path for imports
    project_root = Path(__file__).parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from scripts.index_manager import IndexManager

    try:
        # Initialize the index manager
        index_manager = IndexManager()

        # Curated fallback universes - small lists for specific themes
        universe_configs = {
            'japan': [
                '7203.T', '6098.T', '4063.T', '4502.T', '9984.T', '9432.T', '8316.T',
                '6758.T', '7267.T', '6861.T', '6954.T', '6920.T', '6752.T', '4543.T',
                '8002.T', '8058.T', '8031.T', '8001.T', '8053.T',  # Sogo shosha
            ],
            'spain': [
                'SAN.MC', 'BBVA.MC', 'CABK.MC', 'SAB.MC', 'BKT.MC', 'MAP.MC',
                'IBE.MC', 'ELE.MC', 'ENG.MC', 'RED.MC', 'REE.MC', 'NTGY.MC',
                'REP.MC', 'TEF.MC', 'ITX.MC', 'ACS.MC', 'FER.MC', 'FCC.MC',
                'ACX.MC', 'ANA.MC', 'AENA.MC', 'IAG.MC', 'MEL.MC', 'GRF.MC',
                'IDR.MC', 'COL.MC', 'CLNX.MC', 'ALM.MC', 'AMS.MC', 'SGRE.MC',
                'VIS.MC', 'MRL.MC', 'ROVI.MC', 'SLR.MC'
            ],
            'europe': [
                # France
                'MC.PA', 'OR.PA', 'SAN.PA', 'TTE.PA', 'AI.PA', 'SU.PA', 'BNP.PA',
                'RMS.PA', 'CS.PA', 'DG.PA', 'SAF.PA', 'EL.PA', 'DSY.PA', 'CA.PA',
                'ORA.PA', 'EN.PA', 'VIE.PA', 'SGO.PA', 'KER.PA', 'STLAM.PA',
                # Germany
                'SAP.DE', 'SIE.DE', 'AIR.DE', 'ALV.DE', 'BAS.DE', 'MBG.DE', 'VOW3.DE',
                'BMW.DE', 'DTE.DE', 'EOAN.DE', 'MUV2.DE', 'ADS.DE', 'DB1.DE', 'IFX.DE',
                'SHL.DE', 'BNR.DE',
                # Netherlands
                'ASML.AS', 'PHIA.AS', 'INGA.AS', 'ABN.AS', 'AD.AS', 'HEIA.AS',
                # Italy
                'ENI.MI', 'ISP.MI', 'ENEL.MI', 'G.MI', 'STM.MI',
                # Spain
                'SAN.MC', 'BBVA.MC', 'IBE.MC', 'ITX.MC',
                # Belgium
                'ABI.BR'
            ],
            'growth': [
                'TSLA', 'SHOP', 'ROKU', 'ZM', 'SNOW', 'PLTR', 'RBLX', 'U', 'DDOG', 'CRWD'
            ],
            'tech': [
                'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'ORCL', 'CRM', 'ADBE', 'INTC',
                'AMD', 'QCOM', 'CSCO', 'IBM', 'NOW', 'INTU', 'TXN', 'MU', 'AMAT', 'LRCX'
            ],
        }

        source_desc = 'from dynamic index manager'

        # Map universe names to index manager methods
        if universe == 'sp500':
            tickers = index_manager.get_index_tickers('sp500')
        elif universe == 'sp1500':
            sp500 = index_manager.get_index_tickers('sp500')
            sp400 = index_manager.get_index_tickers('sp400')
            sp600 = index_manager.get_index_tickers('sp600')
            tickers = list(dict.fromkeys(sp500 + sp400 + sp600))
            source_desc = f"S&P 1500 (500={len(sp500)}, 400={len(sp400)}, 600={len(sp600)})"
        elif universe == 'international':
            # Combine multiple international indices
            tickers = []
            tickers.extend(index_manager.get_index_tickers('ftse100'))
            # Add more indices as they become available
            tickers = list(dict.fromkeys(tickers))  # Remove duplicates
        elif universe == 'all':
            # Get all known tickers + cached registry + curated lists + everything already tracked in DB
            index_tickers = index_manager.get_all_tickers()
            cached_tickers = list(index_manager.companies['companies'].keys())
            curated_tickers = [t for lst in universe_configs.values() for t in lst]
            db_tickers = []
            try:
                with get_connection() as _conn:
                    with _conn.cursor() as _cur:
                        _cur.execute('SELECT ticker FROM current_stock_data')
                        db_tickers = [row[0] for row in _cur.fetchall()]
            except Exception as _e:
                logger.warning(f'Could not load DB tickers for universe=all: {_e}')
            tickers = list(dict.fromkeys(index_tickers + cached_tickers + curated_tickers + db_tickers))
            source_desc = (
                f"indices={len(index_tickers)}, cached={len(cached_tickers)}, "
                f"curated={len(curated_tickers)}, db={len(db_tickers)}"
            )
        elif universe == 'cached':
            # Return all companies in our registry
            tickers = list(index_manager.companies['companies'].keys())
        else:
            # Fallback universes - small curated lists for specific themes
            tickers = universe_configs.get(universe, [])

        # Log the result
        logger.info(f"Universe '{universe}': {len(tickers)} tickers ({source_desc})")

        return tickers

    except Exception as e:
        logger.error(f"Failed to get dynamic tickers for {universe}: {e}")

        # Fallback to legacy sp500_tickers.json for S&P 500
        if universe == 'sp500':
            try:
                import json
                with open('sp500_tickers.json', 'r') as f:
                    fallback_tickers = json.load(f)
                logger.info(f"Fallback: loaded {len(fallback_tickers)} S&P 500 tickers from file")
                return fallback_tickers
            except Exception:
                pass

        # Final fallback - minimal set
        fallback_tickers = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'ORCL', 'CRM', 'ADBE']
        logger.warning(f"Using minimal fallback: {len(fallback_tickers)} tickers")
        return fallback_tickers


async def main():
    """Main data fetching routine"""
    parser = argparse.ArgumentParser(description='Fetch stock data asynchronously')
    parser.add_argument('--universe', default='sp500', help='Stock universe to fetch')
    parser.add_argument('--max-concurrent', type=int, default=10, help='Max concurrent requests')
    parser.add_argument('--lite', action='store_true', help='Lite mode: prices + metrics only, skip financial statements')

    args = parser.parse_args()

    # Get ticker list
    tickers = get_universe_tickers(args.universe)
    logger.info(f"Planning to fetch data for {len(tickers)} stocks from {args.universe} universe")

    # Get update order: empty stocks first, then oldest to newest
    cache = StockDataCache()
    tickers = cache.get_update_order(tickers)

    logger.info(f"Will update {len(tickers)} stocks in optimal order (empty first, then oldest to newest)")

    # Fetch data
    start_time = time.time()

    if args.lite:
        logger.info("LITE MODE: skipping financial statements (cashflow, balance sheet, income)")

    async with AsyncStockDataFetcher(max_workers=args.max_concurrent, lite=args.lite) as fetcher:
        results = await fetcher.fetch_multiple_stocks(tickers, args.max_concurrent)

    # Report results
    successful = sum(1 for r in results.values() if 'error' not in r)
    failed = len(results) - successful
    elapsed = time.time() - start_time

    logger.info(f"""
Data fetching complete:
  - Total stocks: {len(results)}
  - Successful: {successful}
  - Failed: {failed}
  - Time elapsed: {elapsed:.1f} seconds
  - Average: {elapsed/len(results):.2f} sec/stock" if results else "  - Average: N/A (no results)"
  - Cache location: {fetcher.cache.cache_dir}
    """)

    # Save summary report
    summary = {
        'universe': args.universe,
        'total_requested': len(tickers),
        'successful_fetches': successful,
        'failed_fetches': failed,
        'time_elapsed': elapsed,
        'fetch_timestamp': datetime.now().isoformat(),
        'failed_tickers': [ticker for ticker, data in results.items() if 'error' in data]
    }

    logs_dir = Path(__file__).resolve().parent.parent / 'logs'
    logs_dir.mkdir(exist_ok=True)
    summary_file = logs_dir / f'data_fetch_summary_{args.universe}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)

    logger.info(f"Summary saved to: {summary_file}")


if __name__ == '__main__':
    asyncio.run(main())
