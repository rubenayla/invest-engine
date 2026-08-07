"""
Stock Data Reader

Provides unified interface to read stock data from PostgreSQL database.
"""

import json
import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from psycopg2.extras import RealDictCursor

from .db import get_connection

logger = logging.getLogger(__name__)


class StockDataReader:
    """Read stock data from PostgreSQL database."""

    def __init__(self, db_path=None):
        """Initialize reader. db_path is accepted for backward compatibility but ignored."""
        pass

    def _conn(self, dict_cursor=False):
        return get_connection(dict_cursor=dict_cursor)

    def get_stock_data(self, ticker: str, conn=None) -> Optional[Dict[str, Any]]:
        """Get stock data for a single ticker.

        If ``conn`` is provided the caller owns its lifecycle and it is reused
        for the main row *and* every sub-signal lookup, instead of opening a
        fresh connection per call. Scoring a whole universe otherwise opens ~7
        connections per ticker, which stalls over a slow (SSH-tunnelled) link.
        The connection must be tuple-default (the sub-signal helpers expect
        tuple rows); the main row is read with an explicit dict cursor.
        """
        own = conn is None
        if own:
            conn = self._conn()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute('SELECT * FROM current_stock_data WHERE ticker = %s', (ticker,))
        row = cursor.fetchone()
        cursor.close()

        if not row:
            if own:
                conn.close()
            return None

        # JSONB columns come back as Python objects (no json.loads needed)
        cashflow_data = row['cashflow_json'] if row['cashflow_json'] else []
        balance_sheet_data = row['balance_sheet_json'] if row['balance_sheet_json'] else []
        income_data = row['income_json'] if row['income_json'] else []

        # Extract most recent cash flow values for valuation models
        free_cashflow = None
        operating_cashflow = None
        if cashflow_data and isinstance(cashflow_data, list):
            for item in cashflow_data:
                if isinstance(item, dict) and 'index' in item:
                    dates = [k for k in item.keys() if k != 'index']
                    if dates:
                        recent_date = dates[0]
                        value = item.get(recent_date)
                        if item['index'] == 'Free Cash Flow' and value and not (isinstance(value, float) and value != value):
                            free_cashflow = value
                        elif item['index'] == 'Operating Cash Flow' and value and not (isinstance(value, float) and value != value):
                            operating_cashflow = value

        data = {
            'ticker': row['ticker'],
            'info': {
                'currentPrice': row['current_price'],
                'marketCap': row['market_cap'],
                'sector': row['sector'],
                'industry': row['industry'],
                'longName': row['long_name'],
                'shortName': row['short_name'],
                'currency': row['currency'],
                'financialCurrency': row.get('financial_currency') or 'USD',
                'exchange': row['exchange'],
                'country': row['country'],
                'sharesOutstanding': row['shares_outstanding'],
                'totalRevenue': row['total_revenue'],
                'totalCash': row['total_cash'],
                'totalDebt': row['total_debt'],
                'trailingEps': row['trailing_eps'],
                'bookValue': row['book_value'],
                'revenuePerShare': row['revenue_per_share'],
                'freeCashflow': free_cashflow,
                'operatingCashflow': operating_cashflow,
            },
            'financials': {
                'trailingPE': row['trailing_pe'],
                'forwardPE': row['forward_pe'],
                'priceToBook': row['price_to_book'],
                'returnOnEquity': row['return_on_equity'],
                'debtToEquity': row['debt_to_equity'],
                'currentRatio': row['current_ratio'],
                'revenueGrowth': row['revenue_growth'],
                'earningsGrowth': row['earnings_growth'],
                'operatingMargins': row['operating_margins'],
                'profitMargins': row['profit_margins'],
                'totalRevenue': row['total_revenue'],
                'totalCash': row['total_cash'],
                'totalDebt': row['total_debt'],
                'sharesOutstanding': row['shares_outstanding'],
                'trailingEps': row['trailing_eps'],
                'bookValue': row['book_value'],
                'revenuePerShare': row['revenue_per_share'],
                'priceToSalesTrailing12Months': row['price_to_sales_ttm'],
                '_exchange_rate_used': row.get('exchange_rate_used'),
                '_original_currency': row.get('original_currency'),
            },
            'price_data': {
                'current_price': row['current_price'],
                'price_52w_high': row['price_52w_high'],
                'price_52w_low': row['price_52w_low'],
                'avg_volume': row['avg_volume'],
                'price_trend_30d': row['price_trend_30d'],
            },
            'cashflow': cashflow_data,
            'balance_sheet': balance_sheet_data,
            'income': income_data,
            'fetch_timestamp': row['fetch_timestamp'],
            'insider': self.get_insider_signal(ticker, conn=conn),
            'activist': self.get_activist_signal(ticker, conn=conn),
            'holdings': self.get_holdings_signal(ticker, conn=conn),
            'japan_stakes': self.get_japan_signal(ticker, conn=conn),
            'politician': self.get_politician_signal(ticker, conn=conn),
        }

        if own:
            conn.close()
        return data

    def get_all_tickers(self) -> List[str]:
        """Get list of all tickers in the database."""
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute('SELECT ticker FROM current_stock_data ORDER BY ticker')
        tickers = [row[0] for row in cursor.fetchall()]
        conn.close()
        return tickers

    def get_tickers_with_gate_pass_politician_trade(
        self,
        lookback_days: int = 180,
        direction: str = 'P',
    ) -> List[str]:
        """Tickers that received at least one gate-PASS politician trade recently.

        Joins ``politician_trades`` with the ticker universe in
        ``current_stock_data`` and consults
        ``src/invest/signals/gates.py:SIGNAL_GATES`` to keep only trades
        whose (politician, direction) entry has ``passes=True``. Today
        that means Pelosi BUYS and Tuberville SELLS — but the function
        is direction-parameterized so callers can request either side.

        Parameters
        ----------
        lookback_days : int
            Look back this many days from today for the trade date.
        direction : str
            ``'P'`` for purchases (default) or ``'S'`` for sales.

        Returns
        -------
        Sorted list of distinct tickers, all guaranteed to be in the
        scanner's working universe (``current_stock_data``).
        """
        from datetime import datetime, timedelta

        from invest.signals.gates import SIGNAL_GATES

        passing_names = sorted({
            name for (source, name, kind), gate in SIGNAL_GATES.items()
            if source == 'politician' and kind == direction and gate.passes
        })
        if not passing_names:
            return []

        cutoff = (datetime.utcnow() - timedelta(days=lookback_days)).strftime('%Y-%m-%d')
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT DISTINCT pt.ticker
            FROM politician_trades pt
            JOIN current_stock_data csd ON csd.ticker = pt.ticker
            WHERE pt.transaction_type = %s
              AND pt.transaction_date >= %s
              AND pt.politician_name = ANY(%s)
            ORDER BY pt.ticker
            """,
            (direction, cutoff, passing_names),
        )
        tickers = [row[0] for row in cursor.fetchall()]
        conn.close()
        return tickers

    def get_stocks_by_sector(self, sector: str) -> List[str]:
        """Get all tickers in a specific sector."""
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT ticker FROM current_stock_data WHERE sector = %s ORDER BY ticker',
            (sector,),
        )
        tickers = [row[0] for row in cursor.fetchall()]
        conn.close()
        return tickers

    def get_stock_count(self) -> int:
        """Get total number of stocks in database."""
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM current_stock_data')
        count = cursor.fetchone()[0]
        conn.close()
        return count

    def get_fundamental_history(self, ticker: str, metric: str) -> Optional[Dict[str, float]]:
        """Extract historical values for a fundamental metric from JSON data."""
        conn = self._conn()
        cursor = conn.cursor()

        cursor.execute(
            'SELECT income_json, cashflow_json, balance_sheet_json '
            'FROM current_stock_data WHERE ticker = %s',
            (ticker,),
        )

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        # JSONB comes back as Python objects already
        income_data, cashflow_data, balance_sheet_data = row
        data_sources = [
            income_data if income_data else [],
            cashflow_data if cashflow_data else [],
            balance_sheet_data if balance_sheet_data else [],
        ]

        metric_lower = metric.lower()

        def _extract_history(item: dict) -> Optional[Dict[str, float]]:
            history = {}
            for key, value in item.items():
                if key == 'index':
                    continue
                year = key[:4] if len(key) >= 4 else key
                if value is not None and not (isinstance(value, float) and value != value):
                    history[year] = value
            if history:
                return dict(sorted(history.items(), reverse=True))
            return None

        # Pass 1: exact match
        for data_list in data_sources:
            if not isinstance(data_list, list):
                continue
            for item in data_list:
                if not isinstance(item, dict) or 'index' not in item:
                    continue
                if item['index'].lower() == metric_lower:
                    result = _extract_history(item)
                    if result:
                        return result

        # Pass 2: partial match
        for data_list in data_sources:
            if not isinstance(data_list, list):
                continue
            for item in data_list:
                if not isinstance(item, dict) or 'index' not in item:
                    continue
                item_name = item['index'].lower()
                if metric_lower in item_name or item_name in metric_lower:
                    result = _extract_history(item)
                    if result:
                        return result

        return None

    def get_earnings_trend(self, ticker: str) -> Optional[Dict[str, float]]:
        """Get historical net income trend for a stock."""
        return self.get_fundamental_history(ticker, 'Net Income')

    def get_revenue_trend(self, ticker: str) -> Optional[Dict[str, float]]:
        """Get historical revenue trend for a stock."""
        return self.get_fundamental_history(ticker, 'Total Revenue')

    def get_cashflow_trend(self, ticker: str) -> Optional[Dict[str, float]]:
        """Get historical free cash flow trend for a stock."""
        return self.get_fundamental_history(ticker, 'Free Cash Flow')

    def get_recent_price_closes(self, ticker: str, limit: int = 600) -> Dict[str, Any]:
        """Get most recent close prices for a ticker."""
        empty = {'closes': [], 'dates': [], 'last_date': None, 'price_points': 0}
        try:
            conn = self._conn(dict_cursor=True)
            cursor = conn.cursor()
            cursor.execute(
                'SELECT date, close FROM price_history '
                'WHERE ticker = %s AND close IS NOT NULL '
                'ORDER BY date DESC LIMIT %s',
                (ticker, limit),
            )
            rows = cursor.fetchall()
            conn.close()
        except Exception:
            logger.warning('price_history query failed for %s — returning empty result', ticker)
            return empty

        if not rows:
            return {'closes': [], 'dates': [], 'last_date': None, 'price_points': 0}

        rows = list(reversed(rows))
        closes = [float(row['close']) for row in rows if row['close'] is not None]
        dates_list = []
        for row in rows:
            if row['close'] is not None:
                d = row['date']
                dates_list.append(d.isoformat() if isinstance(d, date) else str(d))
        last_date = dates_list[-1] if dates_list else None

        return {
            'closes': closes,
            'dates': dates_list,
            'last_date': last_date,
            'price_points': len(closes),
        }

    def get_latest_macro_rate(self, rate_name: str = 'risk_free_rate') -> Optional[Dict[str, Any]]:
        """Get the most recent macro rate from `macro_rates`."""
        conn = self._conn(dict_cursor=True)
        cursor = conn.cursor()

        try:
            cursor.execute(
                'SELECT rate_name, date, value, source, fetched_at '
                'FROM macro_rates WHERE rate_name = %s '
                'ORDER BY date DESC LIMIT 1',
                (rate_name,),
            )
            row = cursor.fetchone()
        except Exception:
            conn.close()
            return None

        conn.close()

        if not row:
            return None

        d = row['date']
        return {
            'rate_name': row['rate_name'],
            'date': d.isoformat() if isinstance(d, date) else str(d),
            'value': float(row['value']) if row['value'] is not None else None,
            'source': row['source'],
            'fetched_at': row['fetched_at'],
        }

    def get_market_inputs(
        self,
        ticker: str,
        min_price_points: int = 252,
        max_price_age_days: int = 30,
        max_rate_age_days: int = 30,
    ) -> Dict[str, Any]:
        """Get robust market inputs for structural valuation models."""
        prices = self.get_recent_price_closes(ticker, limit=max(min_price_points + 50, 600))
        closes = prices.get('closes', [])
        last_price_date = prices.get('last_date')
        price_age_days = None
        price_is_fresh = False

        if last_price_date:
            try:
                last_dt = datetime.strptime(last_price_date, '%Y-%m-%d')
                price_age_days = (datetime.now() - last_dt).days
                price_is_fresh = price_age_days <= max_price_age_days
            except ValueError:
                price_age_days = None
                price_is_fresh = False

        macro = self.get_latest_macro_rate('risk_free_rate')
        risk_free_rate = None
        rate_source = 'default_config'
        rate_date = None
        rate_age_days = None
        rate_is_fresh = False

        if macro and isinstance(macro.get('value'), float):
            risk_free_rate = float(macro['value'])
            rate_source = str(macro.get('source') or 'macro_rates')
            rate_date = macro.get('date')

            if rate_date:
                try:
                    rate_dt = datetime.strptime(rate_date, '%Y-%m-%d')
                    rate_age_days = (datetime.now() - rate_dt).days
                    rate_is_fresh = rate_age_days <= max_rate_age_days
                except ValueError:
                    rate_age_days = None
                    rate_is_fresh = False

        return {
            'closes': closes,
            'price_points': len(closes),
            'price_last_date': last_price_date,
            'price_age_days': price_age_days,
            'price_is_fresh': price_is_fresh,
            'min_price_points': min_price_points,
            'risk_free_rate': risk_free_rate,
            'rate_source': rate_source,
            'rate_date': rate_date,
            'rate_age_days': rate_age_days,
            'rate_is_fresh': rate_is_fresh,
        }

    def get_insider_signal(self, ticker: str, conn=None) -> Dict[str, Any]:
        """Get insider activity signal for a ticker.

        If ``conn`` is provided it is reused (caller owns its lifecycle);
        otherwise a fresh connection is opened and closed here.
        """
        no_data = {'has_data': False}
        try:
            from .insider_db import compute_insider_signal
            own = conn is None
            if own:
                conn = self._conn()
            try:
                return compute_insider_signal(conn, ticker)
            finally:
                if own:
                    conn.close()
        except Exception:
            return no_data

    def get_activist_signal(self, ticker: str, conn=None) -> Dict[str, Any]:
        """Get activist/passive large-stake signal (13D/13G) for a ticker.

        If ``conn`` is provided it is reused (caller owns its lifecycle).
        """
        no_data = {'has_data': False}
        try:
            from .activist_db import compute_activist_signal
            own = conn is None
            if own:
                conn = self._conn()
            try:
                return compute_activist_signal(conn, ticker)
            finally:
                if own:
                    conn.close()
        except Exception:
            return no_data

    def get_holdings_signal(self, ticker: str, conn=None) -> Dict[str, Any]:
        """Get smart money institutional holdings signal (13F) for a ticker.

        If ``conn`` is provided it is reused (caller owns its lifecycle).
        """
        no_data = {'has_data': False}
        try:
            from .holdings_db import compute_holdings_signal
            own = conn is None
            if own:
                conn = self._conn()
            try:
                return compute_holdings_signal(conn, ticker)
            finally:
                if own:
                    conn.close()
        except Exception:
            return no_data

    def get_japan_signal(self, ticker: str, conn=None) -> Dict[str, Any]:
        """Get Japan large shareholding signal (EDINET) for a ticker.

        If ``conn`` is provided it is reused (caller owns its lifecycle).
        """
        no_data = {'has_data': False}
        try:
            from .edinet_db import compute_japan_signal
            own = conn is None
            if own:
                conn = self._conn()
            try:
                return compute_japan_signal(conn, ticker)
            finally:
                if own:
                    conn.close()
        except Exception:
            return no_data

    def get_politician_signal(self, ticker: str, conn=None) -> Dict[str, Any]:
        """Get House PTR politician-trade signal for a ticker.

        If ``conn`` is provided it is reused (caller owns its lifecycle).
        """
        no_data = {'has_data': False}
        try:
            from .politician_db import compute_politician_signal
            own = conn is None
            if own:
                conn = self._conn()
            try:
                return compute_politician_signal(conn, ticker)
            finally:
                if own:
                    conn.close()
        except Exception:
            return no_data
