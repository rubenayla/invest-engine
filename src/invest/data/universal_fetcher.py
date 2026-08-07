"""
Universal stock data fetcher that handles any ticker from any exchange.

This module provides a unified interface for fetching stock data regardless of:
- Exchange (NYSE, NASDAQ, TSE, LSE, etc.)
- Country (US, Japan, UK, Germany, etc.)
- Currency (automatically converts if needed)

Ticker formats supported:
- Simple: 'AAPL' (defaults to primary exchange)
- With exchange: 'AAPL:NASDAQ', '7203.T', 'ASML.AS'
- Yahoo format: '7203.T' (Toyota on Tokyo), 'NESN.SW' (Nestle on Swiss)
"""

import logging
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from numbers import Number
from typing import Dict, List, Optional

import yfinance as yf

logger = logging.getLogger(__name__)

# Exchange suffixes for Yahoo Finance
EXCHANGE_SUFFIXES = {
    # US - no suffix needed
    'NYSE': '',
    'NASDAQ': '',
    'AMEX': '',

    # Asia
    'TSE': '.T',      # Tokyo Stock Exchange
    'OSE': '.T',      # Osaka (merged with TSE)
    'HKEX': '.HK',    # Hong Kong
    'SSE': '.SS',     # Shanghai
    'SZSE': '.SZ',    # Shenzhen
    'KRX': '.KS',     # Korea
    'SGX': '.SI',     # Singapore
    'BSE': '.BO',     # Bombay
    'NSE': '.NS',     # India NSE

    # Europe
    'LSE': '.L',      # London
    'XETRA': '.DE',   # Germany
    'PAR': '.PA',     # Paris
    'AMS': '.AS',     # Amsterdam
    'SWX': '.SW',     # Swiss
    'BME': '.MC',     # Madrid
    'MIL': '.MI',     # Milan
    'STO': '.ST',     # Stockholm
    'HEL': '.HE',     # Helsinki
    'CPH': '.CO',     # Copenhagen
    'OSL': '.OL',     # Oslo

    # Other
    'TSX': '.TO',     # Toronto
    'ASX': '.AX',     # Australia
    'NZX': '.NZ',     # New Zealand
    'JSE': '.JO',     # Johannesburg
    'TADAWUL': '.SR', # Saudi Arabia
    'ADX': '.AE',     # Abu Dhabi
    'QSE': '.QA',     # Qatar
}

# Common ticker mappings for different formats
TICKER_ALIASES = {
    # Japanese companies
    '8002': '8002.T',  # Marubeni
    '7203': '7203.T',  # Toyota
    '6758': '6758.T',  # Sony
    '8058': '8058.T',  # Mitsubishi Corp
    '4063': '4063.T',  # Shin-Etsu Chemical

    # European companies
    'ASML': 'ASML.AS',  # ASML (Amsterdam)
    'NESN': 'NESN.SW',  # Nestle (Swiss)
    'SAP': 'SAP.DE',    # SAP (Germany)

    # Special cases
    'BRK.B': 'BRK-B',   # Berkshire Hathaway B
    'BRK.A': 'BRK-A',   # Berkshire Hathaway A
}


class UniversalStockFetcher:
    """Fetches stock data from any exchange worldwide."""

    def __init__(self, convert_currency: bool = True, target_currency: str = 'USD'):
        """
        Initialize the universal fetcher.

        Args:
            convert_currency: Whether to convert all prices to target currency
            target_currency: Target currency for conversion (default: USD)
        """
        self.convert_currency = convert_currency
        self.target_currency = target_currency
        self._exchange_rates = {}

    def parse_ticker(self, ticker_input: str) -> str:
        """
        Parse various ticker formats into Yahoo Finance format.

        Examples:
            'AAPL' -> 'AAPL'
            'AAPL:NASDAQ' -> 'AAPL'
            '7203:TSE' -> '7203.T'
            'ASML:AMS' -> 'ASML.AS'
            '8002' -> '8002.T' (assumes Japanese if 4 digits)
        """
        # Check if it's in our alias map
        if ticker_input in TICKER_ALIASES:
            return TICKER_ALIASES[ticker_input]

        # Handle exchange-specified format (TICKER:EXCHANGE)
        if ':' in ticker_input:
            ticker, exchange = ticker_input.split(':', 1)
            exchange = exchange.upper()
            if exchange in EXCHANGE_SUFFIXES:
                suffix = EXCHANGE_SUFFIXES[exchange]
                return f'{ticker}{suffix}' if suffix else ticker
            else:
                logger.warning(f'Unknown exchange {exchange}, using ticker as-is')
                return ticker

        # Auto-detect Japanese stocks (4-digit numbers)
        if ticker_input.isdigit() and len(ticker_input) == 4:
            return f'{ticker_input}.T'

        # Return as-is (might already be in Yahoo format or US stock)
        return ticker_input

    def fetch_stock(self, ticker_input: str) -> Optional[Dict]:
        """
        Fetch data for a single stock from any exchange.

        Args:
            ticker_input: Ticker in any supported format

        Returns:
            Dictionary with normalized stock data
        """
        yahoo_ticker = self.parse_ticker(ticker_input)

        try:
            stock = yf.Ticker(yahoo_ticker)
            info = stock.info

            if not info or 'symbol' not in info:
                logger.warning(f'No data found for {ticker_input} (tried {yahoo_ticker})')
                return None

            # Normalize the data
            normalized = self._normalize_data(info, ticker_input)

            # Add exchange info
            normalized['original_ticker'] = ticker_input
            normalized['yahoo_ticker'] = yahoo_ticker
            normalized['exchange'] = info.get('exchange', 'Unknown')
            normalized['currency'] = info.get('currency', 'USD')
            normalized['country'] = info.get('country', 'Unknown')

            # Convert currency if requested
            if self.convert_currency and normalized['currency'] != self.target_currency:
                normalized = self._convert_prices(normalized)

            return normalized

        except Exception as e:
            logger.error(f'Error fetching {ticker_input}: {e}')
            return None

    def fetch_multiple(self, tickers: List[str], max_workers: int = 10) -> Dict[str, Optional[Dict]]:
        """
        Fetch data for multiple stocks concurrently.

        Args:
            tickers: List of tickers in any supported format
            max_workers: Maximum concurrent threads

        Returns:
            Dictionary mapping original ticker -> stock data
        """
        results = {}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_ticker = {
                executor.submit(self.fetch_stock, ticker): ticker
                for ticker in tickers
            }

            for future in as_completed(future_to_ticker):
                ticker = future_to_ticker[future]
                try:
                    data = future.result()
                    results[ticker] = data
                except Exception as e:
                    logger.error(f'Error fetching {ticker}: {e}')
                    results[ticker] = None

        return results

    def _normalize_data(self, info: Dict, original_ticker: str) -> Dict:
        """Normalize yfinance data to consistent field names."""
        # Start with all original data
        normalized = dict(info)

        # Add normalized field names
        normalized.update({
            'ticker': original_ticker,
            'sector': info.get('sector'),
            'industry': info.get('industry'),
            'market_cap': info.get('marketCap'),
            'enterprise_value': info.get('enterpriseValue'),
            'current_price': info.get('currentPrice') or info.get('regularMarketPrice'),
            'trailing_pe': info.get('trailingPE'),
            'forward_pe': info.get('forwardPE'),
            'price_to_book': info.get('priceToBook'),
            'ev_to_ebitda': info.get('enterpriseToEbitda'),
            'ev_to_revenue': info.get('enterpriseToRevenue'),
            'return_on_equity': info.get('returnOnEquity'),
            'return_on_assets': info.get('returnOnAssets'),
            'debt_to_equity': self._calc_debt_to_equity(info),
            'current_ratio': info.get('currentRatio'),
            'revenue_growth': info.get('revenueGrowth'),
            'earnings_growth': info.get('earningsGrowth'),
            'free_cash_flow': info.get('freeCashflow'),
            'shares_outstanding': info.get('sharesOutstanding'),
            'trailing_eps': info.get('trailingEps'),
            'dividend_yield': info.get('dividendYield'),
            'beta': info.get('beta'),
            'revenue': info.get('totalRevenue'),
            'net_income': info.get('netIncomeToCommon'),
            'ebitda': info.get('ebitda'),
            'total_debt': info.get('totalDebt'),
            'total_cash': info.get('totalCash'),
        })

        return normalized

    @staticmethod
    def _calc_debt_to_equity(info: Dict) -> Optional[float]:
        """Calculate D/E as a ratio from raw fields.

        yfinance returns debtToEquity as a percentage (e.g. 150 meaning 1.5x).
        We recompute it from totalDebt / (bookValue * sharesOutstanding) so the
        value is stored as a proper ratio, consistent with data_fetcher.py.
        """
        total_debt = info.get('totalDebt')
        book_value = info.get('bookValue')
        shares = info.get('sharesOutstanding')
        if total_debt and book_value and shares and book_value > 0:
            total_equity = book_value * shares
            if total_equity > 0:
                return total_debt / total_equity
        return None

    def _convert_prices(self, data: Dict) -> Dict:
        """Convert price fields to target currency."""
        source_currency = data.get('currency')
        data['original_currency'] = source_currency

        if not source_currency:
            data['currency'] = self.target_currency
            data['exchange_rate'] = 1.0
            data['converted_to'] = self.target_currency
            return data

        if source_currency == self.target_currency:
            data['exchange_rate'] = 1.0
            data['converted_to'] = self.target_currency
            data['currency'] = self.target_currency
            if 'financialCurrency' in data:
                data.setdefault('financialCurrency_original', data['financialCurrency'])
                data['financialCurrency'] = self.target_currency
            return data

        # Get exchange rate
        if source_currency not in self._exchange_rates:
            rate_ticker = f'{source_currency}{self.target_currency}=X'
            try:
                rate_data = yf.Ticker(rate_ticker).info
                rate = rate_data.get('regularMarketPrice', 1.0)
                self._exchange_rates[source_currency] = rate
            except Exception:
                logger.warning(f'Could not get exchange rate for {source_currency} to {self.target_currency}')
                self._exchange_rates[source_currency] = 1.0

        rate = self._exchange_rates[source_currency]

        def _convert_field(field_name: str) -> None:
            """Convert a numeric field in-place while preserving the original value."""
            value = data.get(field_name)
            if value is None or isinstance(value, bool) or not isinstance(value, Number):
                return
            original_key = f'{field_name}_original'
            if original_key not in data:
                data[original_key] = value
            try:
                numeric_value = float(value)
            except (TypeError, ValueError):
                return
            if math.isnan(numeric_value) or math.isinf(numeric_value):
                return
            converted_value = numeric_value * rate
            data[field_name] = converted_value
            data[f'{field_name}_{self.target_currency.lower()}'] = converted_value

        # Convert price fields
        price_fields = [
            'current_price', 'currentPrice', 'regularMarketPrice',
            'target_mean_price', 'targetMeanPrice',
            'target_high_price', 'targetHighPrice',
            'target_low_price', 'targetLowPrice',
            'fifty_two_week_high', 'fiftyTwoWeekHigh',
            'fifty_two_week_low', 'fiftyTwoWeekLow',
            'fifty_day_average', 'fiftyDayAverage',
            'two_hundred_day_average', 'twoHundredDayAverage',
            'book_value', 'bookValue',
            'trailing_eps', 'trailingEps',
            'forward_eps', 'forwardEps',
            'previousClose', 'open', 'dayHigh', 'dayLow'
        ]

        for field in price_fields:
            _convert_field(field)

        # Convert value fields
        value_fields = [
            'market_cap', 'marketCap',
            'enterprise_value', 'enterpriseValue',
            'revenue', 'totalRevenue',
            'ebitda',
            'net_income', 'netIncomeToCommon',
            'free_cash_flow', 'freeCashflow',
            'total_cash', 'totalCash',
            'total_debt', 'totalDebt',
            'total_assets', 'totalAssets',
            'total_liabilities', 'totalLiab'
        ]

        for field in value_fields:
            _convert_field(field)

        data['currency'] = self.target_currency
        if 'financialCurrency' in data:
            data.setdefault('financialCurrency_original', data['financialCurrency'])
            data['financialCurrency'] = self.target_currency

        data['exchange_rate'] = rate
        data['converted_to'] = self.target_currency

        return data


def compare_international_stocks(tickers: List[str], metrics: List[str] = None) -> Dict:
    """
    Compare stocks from different exchanges on common metrics.

    Args:
        tickers: List of tickers (can be from different exchanges)
        metrics: Specific metrics to compare (default: key valuation metrics)

    Returns:
        Comparison dictionary with normalized data
    """
    if metrics is None:
        metrics = [
            'current_price', 'market_cap', 'trailing_pe', 'price_to_book',
            'return_on_equity', 'debt_to_equity', 'revenue_growth',
            'dividend_yield', 'ev_to_ebitda'
        ]

    fetcher = UniversalStockFetcher(convert_currency=True)
    data = fetcher.fetch_multiple(tickers)

    comparison = {}
    for ticker, stock_data in data.items():
        if stock_data:
            comparison[ticker] = {
                'name': stock_data.get('longName', ticker),
                'exchange': stock_data.get('exchange'),
                'currency': stock_data.get('currency'),
                'country': stock_data.get('country'),
                'sector': stock_data.get('sector'),
                'metrics': {
                    metric: stock_data.get(metric) or stock_data.get(f'{metric}_usd')
                    for metric in metrics
                }
            }

    return comparison
