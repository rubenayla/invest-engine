"""
Feature extraction utilities for LSTM/Transformer model.

Extracts temporal and static features from stock data for model training and prediction.
"""

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


class FeatureExtractor:
    """Extracts temporal and static features from stock data."""

    # Sectors for one-hot encoding
    SECTORS = [
        'Technology', 'Healthcare', 'Financial Services', 'Consumer Cyclical',
        'Industrials', 'Communication Services', 'Consumer Defensive',
        'Energy', 'Utilities', 'Real Estate', 'Basic Materials'
    ]

    def __init__(self, num_quarters: int = 4):
        """
        Initialize feature extractor.

        Parameters
        ----------
        num_quarters : int
            Number of historical quarters to extract (default: 4 = 1 year)
        """
        self.num_quarters = num_quarters

    def extract_temporal_features(
        self,
        income_data: List[dict],
        cashflow_data: List[dict],
        balance_sheet_data: List[dict]
    ) -> Optional[np.ndarray]:
        """
        Extract temporal features from quarterly financial statements.

        Parameters
        ----------
        income_data : List[dict]
            List of records from income statement
        cashflow_data : List[dict]
            List of records from cash flow statement
        balance_sheet_data : List[dict]
            List of records from balance sheet

        Returns
        -------
        np.ndarray or None
            Shape: (num_quarters, num_temporal_features)
            Returns None if insufficient data
        """
        # Convert list of dicts to DataFrame format
        income_df = self._records_to_dataframe(income_data)
        cashflow_df = self._records_to_dataframe(cashflow_data)
        balance_df = self._records_to_dataframe(balance_sheet_data)

        if income_df is None:
            return None

        # Get most recent quarters
        date_cols = [col for col in income_df.columns if col != 'index']
        if len(date_cols) < self.num_quarters:
            return None  # Not enough historical data

        # Take most recent quarters
        recent_quarters = date_cols[:self.num_quarters]

        # Extract features for each quarter
        temporal_features = []

        for quarter in recent_quarters:
            quarter_features = self._extract_quarter_features(
                quarter, income_df, cashflow_df, balance_df
            )
            if quarter_features is None:
                return None
            temporal_features.append(quarter_features)

        # Shape: (num_quarters, num_features)
        return np.array(temporal_features)

    def _records_to_dataframe(self, records: List[dict]) -> Optional[pd.DataFrame]:
        """Convert list of records to DataFrame."""
        if not records:
            return None

        df = pd.DataFrame(records)
        if 'index' not in df.columns:
            return None

        df = df.set_index('index')
        return df

    def _extract_quarter_features(
        self,
        quarter: str,
        income_df: pd.DataFrame,
        cashflow_df: Optional[pd.DataFrame],
        balance_df: Optional[pd.DataFrame]
    ) -> Optional[np.ndarray]:
        """
        Extract features for a single quarter.

        Returns
        -------
        np.ndarray or None
            Feature vector for this quarter
        """
        features = []

        # Income statement features (using actual yfinance metric names)
        income_features = [
            'Total Revenue',
            'Operating Revenue',
            'Gross Profit',
            'Operating Income',  # May not exist, will default to 0
            'Net Income Common Stockholders',
            'EBITDA',
            'Basic EPS',
        ]

        for feat in income_features:
            value = self._get_value(income_df, feat, quarter)
            features.append(value)

        # Cash flow features
        if cashflow_df is not None:
            cashflow_features = [
                'Operating Cash Flow',
                'Free Cash Flow',
                'Capital Expenditure',
            ]
            for feat in cashflow_features:
                value = self._get_value(cashflow_df, feat, quarter)
                features.append(value)
        else:
            features.extend([0.0] * 3)

        # Balance sheet features
        if balance_df is not None:
            balance_features = [
                'Total Assets',
                'Total Debt',
                'Cash And Cash Equivalents',
                'Stockholders Equity',
            ]
            for feat in balance_features:
                value = self._get_value(balance_df, feat, quarter)
                features.append(value)
        else:
            features.extend([0.0] * 4)

        # Derived feature: Revenue growth QoQ
        # TODO: Calculate quarter-over-quarter growth
        features.append(0.0)

        return np.array(features)

    def _get_value(
        self,
        df: pd.DataFrame,
        metric: str,
        quarter: str,
        default: float = 0.0
    ) -> float:
        """
        Get value from DataFrame, handling missing data.

        Parameters
        ----------
        df : pd.DataFrame
            Financial statement DataFrame
        metric : str
            Metric name (row index)
        quarter : str
            Quarter column name
        default : float
            Default value if metric not found

        Returns
        -------
        float
            Value or default
        """
        try:
            if metric not in df.index or quarter not in df.columns:
                return default

            value = df.loc[metric, quarter]

            if pd.isna(value):
                return default

            return float(value)
        except (KeyError, ValueError, TypeError):
            return default

    def extract_static_features(self, stock_data: dict) -> Optional[np.ndarray]:
        """
        Extract static features from current stock data.

        Parameters
        ----------
        stock_data : dict
            Stock data from StockDataReader

        Returns
        -------
        np.ndarray or None
            Static feature vector, or None if insufficient data
        """
        info = stock_data.get('info', {})
        financials = stock_data.get('financials', {})

        features = []

        # Valuation ratios
        valuation_fields = [
            'trailingPE', 'forwardPE', 'priceToBook', 'priceToSalesTrailing12Months',
            'enterpriseToRevenue', 'enterpriseToEbitda', 'pegRatio'
        ]
        for field in valuation_fields:
            value = financials.get(field, 0.0) or 0.0
            features.append(float(value))

        # Profitability
        profitability_fields = [
            'returnOnEquity', 'returnOnAssets', 'profitMargins',
            'operatingMargins', 'grossMargins'
        ]
        for field in profitability_fields:
            value = financials.get(field, 0.0) or 0.0
            features.append(float(value))

        # Growth
        growth_fields = [
            'revenueGrowth', 'earningsGrowth', 'earningsQuarterlyGrowth'
        ]
        for field in growth_fields:
            value = financials.get(field, 0.0) or 0.0
            features.append(float(value))

        # Financial health
        health_fields = [
            'debtToEquity', 'currentRatio', 'quickRatio', 'totalCashPerShare'
        ]
        for field in health_fields:
            value = financials.get(field, 0.0) or 0.0
            features.append(float(value))

        # Free cash flow (from info section)
        fcf = info.get('freeCashflow', 0.0) or 0.0
        features.append(float(fcf))

        # Market metrics
        beta = financials.get('beta', 1.0) or 1.0
        features.append(float(beta))

        market_cap = info.get('marketCap', 0.0) or 0.0
        market_cap_log = np.log10(market_cap + 1)  # Log transform, avoid log(0)
        features.append(float(market_cap_log))

        # Sector one-hot encoding
        current_sector = info.get('sector', '')
        for sector in self.SECTORS:
            features.append(1.0 if current_sector == sector else 0.0)

        # Price momentum
        current_price = info.get('currentPrice', 0.0) or 0.0

        price_52w_high = financials.get('fiftyTwoWeekHigh', current_price) or current_price
        price_52w_low = financials.get('fiftyTwoWeekLow', current_price) or current_price

        if price_52w_high > 0:
            high_ratio = current_price / price_52w_high
        else:
            high_ratio = 1.0

        if price_52w_low > 0:
            low_ratio = current_price / price_52w_low
        else:
            low_ratio = 1.0

        features.append(float(high_ratio))
        features.append(float(low_ratio))

        # Price trend (30 day)
        price_trend = stock_data.get('price_data', {}).get('price_trend_30d', 0.0) or 0.0
        features.append(float(price_trend))

        return np.array(features)

    def normalize_features(
        self,
        temporal: np.ndarray,
        static: np.ndarray,
        temporal_stats: Optional[Dict] = None,
        static_stats: Optional[Dict] = None
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Normalize features using robust scaling.

        Uses median and IQR instead of mean and std to handle outliers.

        Parameters
        ----------
        temporal : np.ndarray
            Temporal features, shape: (num_quarters, temporal_features)
        static : np.ndarray
            Static features, shape: (static_features,)
        temporal_stats : dict, optional
            Pre-computed statistics for temporal features
        static_stats : dict, optional
            Pre-computed statistics for static features

        Returns
        -------
        Tuple[np.ndarray, np.ndarray]
            Normalized (temporal, static) features
        """
        # TODO: Implement robust normalization
        # For now, return as-is
        return temporal, static
