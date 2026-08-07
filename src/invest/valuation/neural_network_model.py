"""
Neural Network Valuation Model.

This module implements a neural network-based valuation model that learns
from historical market data to predict company valuations. It uses engineered
features from fundamental data and can target different time horizons.
"""

import logging
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.preprocessing import RobustScaler

from ..exceptions import InsufficientDataError, ValuationError
from .base import ValuationModel, ValuationResult

# Suppress sklearn warnings
warnings.filterwarnings('ignore', category=UserWarning)

logger = logging.getLogger(__name__)


class NeuralNetworkArchitecture(nn.Module):
    """
    Neural network architecture for stock valuation.

    Features a deep architecture with dropout for regularization
    and batch normalization for stable training.
    """

    def __init__(self, input_dim: int, hidden_dims: List[int] = None,
                 dropout_rate: float = 0.3, output_type: str = 'score'):
        """
        Initialize the neural network.

        Parameters
        ----------
        input_dim : int
            Number of input features
        hidden_dims : List[int]
            List of hidden layer dimensions
        dropout_rate : float
            Dropout rate for regularization
        output_type : str
            Type of output ('score' for 0-100, 'return' for expected return)
        """
        super().__init__()

        if hidden_dims is None:
            hidden_dims = [256, 128, 64, 32]

        self.output_type = output_type

        # Build the network layers
        layers = []
        prev_dim = input_dim

        for hidden_dim in hidden_dims:
            layers.extend([
                nn.Linear(prev_dim, hidden_dim),
                nn.BatchNorm1d(hidden_dim),
                nn.ReLU(),
                nn.Dropout(dropout_rate)
            ])
            prev_dim = hidden_dim

        # Output layer
        layers.append(nn.Linear(prev_dim, 1))

        # Add sigmoid for score output (0-100 range)
        if output_type == 'score':
            layers.append(nn.Sigmoid())

        self.network = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass through the network."""
        output = self.network(x)

        # Scale to 0-100 for score output
        if self.output_type == 'score':
            output = output * 100

        return output


class FeatureEngineer:
    """
    Feature engineering for neural network input.

    Transforms raw financial data into normalized features suitable
    for neural network training.
    """

    def __init__(self):
        """Initialize the feature engineer."""
        self.scaler = RobustScaler()
        self.feature_names = []
        self.is_fitted = False

    def extract_features(self, data: Dict[str, Any]) -> Dict[str, float]:
        """
        Extract engineered features from raw financial data.

        Parameters
        ----------
        data : Dict[str, Any]
            Raw financial data from yfinance

        Returns
        -------
        Dict[str, float]
            Dictionary of engineered features
        """
        features = {}

        # Standardize financials to dictionary format
        # This handles variability between offline cache (dict) and live yfinance (DataFrame)
        financials = self._convert_to_dict(data.get('income'))

        # Merge info and financials
        info = {**data.get('info', {}), **financials}

        # Valuation Ratios
        features['pe_ratio'] = self._safe_ratio(
            info.get('currentPrice'),
            info.get('trailingEps')
        )
        features['forward_pe'] = self._safe_ratio(
            info.get('currentPrice'),
            info.get('forwardEps')
        )
        # features['peg_ratio'] = info.get('pegRatio', 0.0) or 0.0  # REMOVED: 100% zeros in cache
        features['price_to_book'] = info.get('priceToBook', 0.0) or 0.0
        features['price_to_sales'] = self._safe_ratio(
            info.get('marketCap'),
            info.get('totalRevenue')
        )
        features['ev_to_ebitda'] = self._safe_ratio(
            info.get('enterpriseValue'),
            info.get('ebitda')
        )
        features['ev_to_revenue'] = self._safe_ratio(
            info.get('enterpriseValue'),
            info.get('totalRevenue')
        )

        # Profitability Metrics
        features['profit_margin'] = info.get('profitMargins', 0.0) or 0.0
        features['operating_margin'] = info.get('operatingMargins', 0.0) or 0.0
        features['roe'] = info.get('returnOnEquity', 0.0) or 0.0
        features['roa'] = info.get('returnOnAssets', 0.0) or 0.0
        # features['roic'] = self._calculate_roic(info)  # REMOVED: 100% zeros in cache
        features['gross_margin'] = info.get('grossMargins', 0.0) or 0.0

        # Growth Metrics
        features['revenue_growth'] = info.get('revenueGrowth', 0.0) or 0.0
        features['earnings_growth'] = info.get('earningsGrowth', 0.0) or 0.0
        # features['revenue_growth_3y'] = self._safe_float(
        #     info.get('revenueQuarterlyGrowth', 0.0)
        # )  # REMOVED: 100% zeros in cache

        # Financial Health
        features['current_ratio'] = info.get('currentRatio', 0.0) or 0.0
        features['quick_ratio'] = info.get('quickRatio', 0.0) or 0.0
        features['debt_to_equity'] = info.get('debtToEquity', 0.0) or 0.0
        features['interest_coverage'] = self._calculate_interest_coverage(info)
        features['free_cash_flow_yield'] = self._safe_ratio(
            info.get('freeCashflow'),
            info.get('marketCap')
        )

        # Market Metrics
        features['beta'] = info.get('beta', 1.0) or 1.0
        features['market_cap_log'] = np.log(max(info.get('marketCap') or 1e6, 1))
        features['avg_volume_log'] = np.log(max(info.get('averageVolume') or 1e3, 1))
        features['dividend_yield'] = info.get('dividendYield', 0.0) or 0.0
        features['payout_ratio'] = info.get('payoutRatio', 0.0) or 0.0

        # Momentum Indicators
        features['52w_high_ratio'] = self._safe_ratio(
            info.get('currentPrice'),
            info.get('fiftyTwoWeekHigh')
        )
        features['52w_low_ratio'] = self._safe_ratio(
            info.get('currentPrice'),
            info.get('fiftyTwoWeekLow')
        )
        features['50d_ma_ratio'] = self._safe_ratio(
            info.get('currentPrice'),
            info.get('fiftyDayAverage')
        )
        features['200d_ma_ratio'] = self._safe_ratio(
            info.get('currentPrice'),
            info.get('twoHundredDayAverage')
        )

        # Get macro data early for new features
        macro = data.get('macro', {})

        # NEW: Time-series momentum features
        history = data.get('history', None)
        if history is not None and (hasattr(history, 'empty') and not history.empty or len(history) > 0):
            features.update(self._extract_time_series_features(history, info))

        # NEW: Relative performance features
        features.update(self._extract_relative_features(info, macro))

        # NEW: Technical indicators
        if history is not None and (hasattr(history, 'empty') and not history.empty or len(history) > 0):
            features.update(self._extract_technical_indicators(history))

        # Analyst Sentiment (if available)
        features['analyst_count'] = info.get('numberOfAnalystOpinions', 0) or 0
        features['target_mean_ratio'] = self._safe_ratio(
            info.get('targetMeanPrice'),
            info.get('currentPrice')
        )
        features['recommendation_score'] = self._encode_recommendation(
            info.get('recommendationKey', 'none')
        )

        # Sector encoding (simplified - could use one-hot encoding)
        features['sector_code'] = self._encode_sector(info.get('sector', 'Unknown'))
        features['industry_code'] = hash(info.get('industry', 'Unknown')) % 100

        # Macroeconomic features from yfinance (real data)
        if macro:
            features['vix'] = macro.get('vix', 20.0) / 100.0  # Normalize VIX
            features['treasury_10y'] = macro.get('treasury_10y', 3.0) / 10.0  # Normalize 10Y yield
            features['dollar_index'] = (macro.get('dollar_index', 100.0) - 100.0) / 20.0  # Normalize DXY around 100
            features['oil_price'] = macro.get('oil_price', 70.0) / 100.0  # Normalize oil price
            features['gold_price'] = macro.get('gold_price', 1800.0) / 2000.0  # Normalize gold price

        return features

    def _convert_to_dict(self, data: Any) -> Dict[str, Any]:
        """
        Convert input data (Dict or DataFrame) to a dictionary predictably.

        - If Dict: Return as is.
        - If DataFrame: Return the most recent column (first column) as dict.
        - If None/Other: Return empty dict.
        """
        if data is None:
            return {}

        if isinstance(data, dict):
            return data

        # Handle DataFrame without triggering ambiguity error
        # Check for DataFrame-like attributes
        if hasattr(data, 'to_dict') and hasattr(data, 'iloc'):
            try:
                if hasattr(data, 'empty') and data.empty:
                    return {}
                # Take the most recent data (first column usually in yfinance)
                return data.iloc[:, 0].to_dict()
            except Exception:
                return {}

        return {}

    def _safe_ratio(self, numerator: Any, denominator: Any,
                   default: float = 0.0) -> float:
        """Calculate ratio safely handling None and zero values."""
        try:
            num = float(numerator) if numerator is not None else 0.0
            den = float(denominator) if denominator is not None else 0.0

            if den == 0:
                return default

            ratio = num / den

            # Cap extreme ratios
            if ratio > 100:
                return 100.0
            elif ratio < -100:
                return -100.0

            return ratio
        except (TypeError, ValueError):
            return default

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        """Safely convert value to float."""
        try:
            if value is None:
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    def _calculate_roic(self, info: Dict[str, Any]) -> float:
        """Calculate Return on Invested Capital."""
        ebit = info.get('ebit', 0)
        tax_rate = 0.25  # Assume 25% if not available
        total_assets = info.get('totalAssets', 0)
        current_liab = info.get('totalCurrentLiabilities', 0)
        cash = info.get('totalCash', 0)

        if not ebit or not total_assets:
            return 0.0

        nopat = ebit * (1 - tax_rate)
        invested_capital = total_assets - current_liab - cash

        if invested_capital <= 0:
            return 0.0

        return (nopat / invested_capital) * 100

    def _calculate_interest_coverage(self, info: Dict[str, Any]) -> float:
        """Calculate interest coverage ratio."""
        ebit = info.get('ebit', 0)
        interest_expense = info.get('interestExpense', 0)

        if not interest_expense or interest_expense == 0:
            return 10.0  # High coverage if no interest expense

        return min(ebit / abs(interest_expense), 10.0)

    def _encode_recommendation(self, rec_key: str) -> float:
        """Encode analyst recommendation to numeric value."""
        encoding = {
            'strong_buy': 5.0,
            'buy': 4.0,
            'hold': 3.0,
            'sell': 2.0,
            'strong_sell': 1.0,
            'none': 3.0
        }
        return encoding.get(rec_key.lower().replace('-', '_'), 3.0)

    def _encode_sector(self, sector: str) -> float:
        """Simple sector encoding (could be improved with one-hot)."""
        sectors = {
            'Technology': 1.0,
            'Healthcare': 2.0,
            'Financial Services': 3.0,
            'Consumer Cyclical': 4.0,
            'Communication Services': 5.0,
            'Consumer Defensive': 6.0,
            'Industrials': 7.0,
            'Energy': 8.0,
            'Utilities': 9.0,
            'Real Estate': 10.0,
            'Basic Materials': 11.0,
            'Unknown': 0.0
        }
        return sectors.get(sector, 0.0)

    def _extract_time_series_features(self, history: Any, info: Dict[str, Any]) -> Dict[str, float]:
        """Extract time-series momentum and volatility features."""
        # Default values in case of any issues
        default_features = {}
        for period in ['1m', '3m', '6m', '1y']:
            default_features[f'return_{period}'] = 0.0
            default_features[f'volatility_{period}'] = 20.0
        default_features['momentum_score'] = 0.0

        # Convert dict to DataFrame if needed (for cached data)
        if isinstance(history, dict):
            try:
                history = pd.DataFrame(history)
            except Exception:
                return default_features

        # Guard clauses - return defaults early if data is invalid
        if not hasattr(history, 'empty') or history.empty:
            return default_features

        close_prices = history['Close'] if 'Close' in history else history.get('close', [])
        if len(close_prices) == 0:
            return default_features

        try:
            # CRITICAL: Use the last price in history, NOT info['currentPrice']
            # info['currentPrice'] is from when cache was created (2024),
            # but history contains historical prices from various dates
            current_price = close_prices.iloc[-1] if hasattr(close_prices, 'iloc') else close_prices[-1]

            # Calculate returns for different periods
            periods = {
                '1m': 21,   # ~1 month
                '3m': 63,   # ~3 months
                '6m': 126,  # ~6 months
                '1y': 252   # ~1 year
            }

            features = {}
            for period_name, days in periods.items():
                if len(close_prices) > days:
                    old_price = close_prices.iloc[-days] if hasattr(close_prices, 'iloc') else close_prices[-days]
                    features[f'return_{period_name}'] = (current_price / old_price - 1) * 100

                    # Calculate volatility for this period
                    period_prices = close_prices.iloc[-days:] if hasattr(close_prices, 'iloc') else close_prices[-days:]
                    returns = period_prices.pct_change().dropna() if hasattr(period_prices, 'pct_change') else np.diff(period_prices) / period_prices[:-1]
                    features[f'volatility_{period_name}'] = np.std(returns) * np.sqrt(252) * 100
                else:
                    features[f'return_{period_name}'] = 0.0
                    features[f'volatility_{period_name}'] = 20.0  # Default volatility

            # Momentum score (weighted average of returns)
            weights = [0.4, 0.3, 0.2, 0.1]  # Recent returns weighted more
            momentum_score = 0
            for i, period in enumerate(['1m', '3m', '6m', '1y']):
                if f'return_{period}' in features:
                    momentum_score += weights[i] * features[f'return_{period}']
            features['momentum_score'] = momentum_score

            return features

        except Exception:
            return default_features

    def _extract_relative_features(self, info: Dict[str, Any], macro: Dict[str, Any]) -> Dict[str, float]:
        """Extract relative performance vs sector and market."""
        features = {}

        # REMOVED: All macro-dependent features since we have no real macro data
        # Would need real sector/market data to make these meaningful

        # Only keep features we can calculate from stock data alone
        # Market cap size (log scale)
        market_cap = info.get('marketCap', 1e9)
        features['market_cap_log'] = np.log(market_cap)

        # Volume relative to average
        volume = info.get('volume', 1e6)
        avg_volume = info.get('averageVolume', 1e6)
        features['volume_vs_avg'] = self._safe_ratio(volume, avg_volume, 1.0)

        return features

    def _extract_technical_indicators(self, history: Any) -> Dict[str, float]:
        """Extract technical indicators like RSI, MACD, Bollinger Bands."""
        features = {}

        try:
            if hasattr(history, 'empty') and not history.empty:
                close_prices = history['Close'] if 'Close' in history else history.get('close', [])

                if len(close_prices) >= 14:
                    # RSI (Relative Strength Index)
                    delta = close_prices.diff() if hasattr(close_prices, 'diff') else np.diff(close_prices, prepend=close_prices[0])
                    gains = delta.where(delta > 0, 0) if hasattr(delta, 'where') else np.where(delta > 0, delta, 0)
                    losses = -delta.where(delta < 0, 0) if hasattr(delta, 'where') else -np.where(delta < 0, delta, 0)

                    avg_gain = gains.rolling(14).mean() if hasattr(gains, 'rolling') else np.convolve(gains, np.ones(14)/14, mode='valid')[-1]
                    avg_loss = losses.rolling(14).mean() if hasattr(losses, 'rolling') else np.convolve(losses, np.ones(14)/14, mode='valid')[-1]

                    if hasattr(avg_gain, 'iloc'):
                        avg_gain = avg_gain.iloc[-1]
                        avg_loss = avg_loss.iloc[-1]

                    rs = avg_gain / avg_loss if avg_loss != 0 else 100
                    features['rsi'] = 100 - (100 / (1 + rs))

                    # MACD
                    if len(close_prices) >= 26:
                        ema_12 = close_prices.ewm(span=12).mean() if hasattr(close_prices, 'ewm') else close_prices[-12:].mean()
                        ema_26 = close_prices.ewm(span=26).mean() if hasattr(close_prices, 'ewm') else close_prices[-26:].mean()

                        if hasattr(ema_12, 'iloc'):
                            ema_12 = ema_12.iloc[-1]
                            ema_26 = ema_26.iloc[-1]

                        features['macd'] = ema_12 - ema_26
                        features['macd_normalized'] = features['macd'] / close_prices.iloc[-1] if hasattr(close_prices, 'iloc') else features['macd'] / close_prices[-1]
                    else:
                        features['macd'] = 0.0
                        features['macd_normalized'] = 0.0

                    # Bollinger Bands position
                    if len(close_prices) >= 20:
                        sma_20 = close_prices.rolling(20).mean() if hasattr(close_prices, 'rolling') else np.mean(close_prices[-20:])
                        std_20 = close_prices.rolling(20).std() if hasattr(close_prices, 'rolling') else np.std(close_prices[-20:])

                        if hasattr(sma_20, 'iloc'):
                            sma_20 = sma_20.iloc[-1]
                            std_20 = std_20.iloc[-1]

                        current = close_prices.iloc[-1] if hasattr(close_prices, 'iloc') else close_prices[-1]
                        upper_band = sma_20 + 2 * std_20
                        lower_band = sma_20 - 2 * std_20

                        # Position within bands (-1 to 1)
                        band_width = upper_band - lower_band
                        features['bollinger_position'] = (current - lower_band) / band_width if band_width > 0 else 0.5
                        features['bollinger_width'] = band_width / sma_20 if sma_20 > 0 else 0.2
                    else:
                        features['bollinger_position'] = 0.5
                        features['bollinger_width'] = 0.2
                else:
                    # Default values if not enough data
                    features['rsi'] = 50.0
                    features['macd'] = 0.0
                    features['macd_normalized'] = 0.0
                    features['bollinger_position'] = 0.5
                    features['bollinger_width'] = 0.2

        except Exception:
            # If technical extraction fails, use defaults
            features['rsi'] = 50.0
            features['macd'] = 0.0
            features['macd_normalized'] = 0.0
            features['bollinger_position'] = 0.5
            features['bollinger_width'] = 0.2

        return features

    def fit_transform(self, features_list: List[Dict[str, float]]) -> np.ndarray:
        """
        Fit the scaler and transform features.

        Parameters
        ----------
        features_list : List[Dict[str, float]]
            List of feature dictionaries

        Returns
        -------
        np.ndarray
            Scaled feature array
        """
        # Convert to DataFrame for easier handling
        df = pd.DataFrame(features_list)

        # Store feature names
        self.feature_names = list(df.columns)

        # Replace inf and -inf with NaN, then fill with 0
        df = df.replace([np.inf, -np.inf], np.nan).fillna(0)

        # Fit and transform
        scaled_features = self.scaler.fit_transform(df)
        self.is_fitted = True

        return scaled_features

    def transform(self, features: Dict[str, float]) -> np.ndarray:
        """
        Transform features using fitted scaler.

        Parameters
        ----------
        features : Dict[str, float]
            Feature dictionary

        Returns
        -------
        np.ndarray
            Scaled feature array
        """
        if not self.is_fitted:
            raise ValueError('FeatureEngineer must be fitted before transform')

        # Ensure consistent feature ordering
        feature_array = np.array([features.get(name, 0.0) for name in self.feature_names])

        # Handle inf and nan
        feature_array = np.nan_to_num(feature_array, nan=0.0, posinf=100.0, neginf=-100.0)

        # Transform
        return self.scaler.transform(feature_array.reshape(1, -1))


class NeuralNetworkValuationModel(ValuationModel):
    """
    Neural network-based valuation model.

    This model uses a deep neural network trained on historical market data
    to predict company valuations. It incorporates extensive feature engineering
    and can target different time horizons.
    """

    def __init__(self, time_horizon: str = '1year', model_path: Optional[Path] = None):
        """
        Initialize the neural network valuation model.

        Parameters
        ----------
        time_horizon : str
            Target time horizon ('1month', '1year', '5year')
        model_path : Optional[Path]
            Path to pre-trained model weights
        """
        super().__init__('neural_network')

        self.time_horizon = time_horizon

        # Resolve default model path if not provided
        if model_path is None:
            # Try to find model in standard locations
            # Path(__file__) is .../src/invest/valuation/neural_network_model.py
            # Parent x4 is project root
            project_root = Path(__file__).parent.parent.parent.parent
            default_model_dir = project_root / 'neural_network' / 'models'

            # Map horizon to filename
            horizon_map = {
                '1month': 'trained_nn_1month.pt',
                '3month': 'trained_nn_3month.pt',
                '6month': 'trained_nn_6month.pt',
                '1year': 'trained_nn_2year.pt',  # Fallback to 2year
                '18month': 'trained_nn_18month.pt',
                '2year': 'trained_nn_2year.pt',
                '3year': 'trained_nn_2year.pt',  # Fallback
                '5year': 'trained_nn_2year.pt',  # Fallback
            }

            filename = horizon_map.get(time_horizon, 'trained_nn_2year.pt')
            candidate_path = default_model_dir / filename

            if candidate_path.exists():
                model_path = candidate_path
                self.logger.info(f"Auto-resolved model path: {model_path}")

        self.model_path = model_path

        # Initialize components
        self.feature_engineer = FeatureEngineer()
        self.model = None
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

        # Load pre-trained model if provided
        if model_path and model_path.exists():
            self.load_model(model_path)
        else:
            # Initialize untrained model (will need training)
            self._initialize_model()

    def _initialize_model(self):
        """Initialize an untrained model with default architecture."""
        # Default feature count (will be updated when fitted)
        input_dim = 40  # Approximate number of features

        self.model = NeuralNetworkArchitecture(
            input_dim=input_dim,
            hidden_dims=[256, 128, 64, 32],
            dropout_rate=0.3,
            output_type='score'
        ).to(self.device)

    def is_suitable(self, ticker: str, data: Dict[str, Any]) -> bool:
        """
        Check if this model is suitable for the given company.

        Neural network model is generally applicable to all companies
        with sufficient fundamental data.

        Parameters
        ----------
        ticker : str
            Stock ticker symbol
        data : Dict[str, Any]
            Company financial data

        Returns
        -------
        bool
            True if model is suitable
        """
        info = data.get('info', {})

        # Check for minimum required data
        required_fields = [
            'currentPrice', 'marketCap', 'totalRevenue',
            'trailingEps', 'enterpriseValue'
        ]

        for field in required_fields:
            if not info.get(field):
                return False

        # Check for positive market cap
        market_cap = self._safe_float(info.get('marketCap'))
        if market_cap <= 0:
            return False

        return True

    def _validate_inputs(self, ticker: str, data: Dict[str, Any]) -> None:
        """
        Validate that required input data is available.

        Parameters
        ----------
        ticker : str
            Stock ticker symbol
        data : Dict[str, Any]
            Company financial data

        Raises
        ------
        InsufficientDataError
            If required data is missing
        """
        info = data.get('info', {})

        # Essential fields for feature engineering
        essential_fields = [
            'currentPrice', 'marketCap', 'enterpriseValue',
            'totalRevenue', 'trailingEps'
        ]

        missing_fields = []
        for field in essential_fields:
            if not info.get(field):
                missing_fields.append(field)

        if missing_fields:
            raise InsufficientDataError(ticker, missing_fields)

        # Warn about optional but useful fields
        optional_fields = [
            'returnOnEquity', 'debtToEquity', 'freeCashflow',
            'revenueGrowth', 'targetMeanPrice'
        ]

        missing_optional = []
        for field in optional_fields:
            if not info.get(field):
                missing_optional.append(field)

        if missing_optional and len(missing_optional) > len(optional_fields) / 2:
            self.logger.warning(
                f'Missing {len(missing_optional)} optional fields for {ticker}. '
                f'Prediction accuracy may be reduced.'
            )

    def _calculate_valuation(self, ticker: str, data: Dict[str, Any]) -> ValuationResult:
        """
        Perform neural network valuation.

        Parameters
        ----------
        ticker : str
            Stock ticker symbol
        data : Dict[str, Any]
            Company financial data

        Returns
        -------
        ValuationResult
            The valuation result
        """
        info = data.get('info', {})

        # Extract features
        features = self.feature_engineer.extract_features(data)

        # Check if model is trained
        if not self.feature_engineer.is_fitted:
            raise ValuationError(
                f"Neural network model not trained/loaded for {ticker}. "
                "Ensure a valid model weights file (.pt) is available."
            )

        # Transform features for model input
        feature_array = self.feature_engineer.transform(features)
        feature_tensor = torch.FloatTensor(feature_array).to(self.device)

        # Get model prediction with uncertainty estimation
        self.model.eval()
        with torch.no_grad():
            # Get base prediction
            score = self.model(feature_tensor).cpu().numpy()[0, 0]

            # Calculate uncertainty based on multiple factors
            uncertainty = self._estimate_uncertainty(features, score)
            confidence = self._score_to_confidence(uncertainty)

        # Convert score to fair value estimate
        current_price = self._safe_float(info.get('currentPrice'))

        # Score 50 = fair value, >50 = undervalued, <50 = overvalued
        # Each point roughly represents 2% deviation from fair value
        # Explicitly cast score to float to avoid numpy types leaking into results
        score_val = float(score)
        fair_value_multiplier = 1 + (score_val - 50) * 0.02
        fair_value = float(current_price * fair_value_multiplier)

        # Calculate margin of safety
        if current_price and current_price != 0:
            margin_of_safety = float(((fair_value - current_price) / current_price) * 100)
        else:
            margin_of_safety = 0.0

        return ValuationResult(
            ticker=ticker,
            model=self.name,
            fair_value=fair_value,
            current_price=current_price,
            margin_of_safety=margin_of_safety,
            confidence=confidence,
            inputs={
                'feature_count': len(features),
                'model_score': float(score),
                'uncertainty': float(uncertainty),
                'time_horizon': self.time_horizon
            },
            outputs={
                'score': float(score),
                'fair_value_multiplier': float(fair_value_multiplier),
                'top_features': self._get_top_features(features)
            },
            warnings=self._generate_warnings(features, score)
        )


    def _estimate_uncertainty(self, features: Dict[str, float], score: float) -> float:
        '''
        Estimate prediction uncertainty based on multiple factors.

        Returns uncertainty score (0-20+), where:
        - 0-5: High confidence
        - 5-10: Medium confidence
        - 10+: Low confidence
        '''
        uncertainty = 0.0

        # Factor 1: Data completeness (0-5 points)
        # Count how many optional fields are missing
        optional_fields = [
            'roe', 'roic', 'free_cash_flow_yield', 'peg_ratio',
            'target_mean_ratio', 'analyst_count', 'debt_to_equity'
        ]
        missing_count = sum(1 for f in optional_fields if features.get(f, 0) == 0)
        uncertainty += (missing_count / len(optional_fields)) * 5

        # Factor 2: Extreme values (0-5 points)
        # High uncertainty if key ratios are extreme
        if features.get('pe_ratio', 0) > 100 or features.get('pe_ratio', 0) < 0:
            uncertainty += 2
        if features.get('debt_to_equity', 0) > 5:
            uncertainty += 1.5
        if features.get('profit_margin', 0) < -0.5:
            uncertainty += 1.5

        # Factor 3: Sector volatility (0-3 points)
        # Some sectors are harder to predict
        volatile_sectors = [1.0, 8.0, 4.0]  # Tech, Energy, Consumer Cyclical
        if features.get('sector_code', 0) in volatile_sectors:
            uncertainty += 2

        # Factor 4: Market cap (0-2 points)
        # Smaller caps are harder to predict
        market_cap_log = features.get('market_cap_log', 20)
        if market_cap_log < 18:  # Below ~$100M
            uncertainty += 2
        elif market_cap_log < 20:  # Below ~$500M
            uncertainty += 1

        # Factor 5: Model confidence in prediction (0-5 points)
        # Extreme scores (very bullish/bearish) may be less reliable
        if score > 80 or score < 20:
            uncertainty += 3
        elif score > 70 or score < 30:
            uncertainty += 1.5

        # Factor 6: Analyst coverage (0-2 points)
        # Low analyst coverage increases uncertainty
        if features.get('analyst_count', 0) < 5:
            uncertainty += 2
        elif features.get('analyst_count', 0) < 10:
            uncertainty += 1

        # Cap uncertainty at reasonable maximum
        return min(uncertainty, 20.0)

    def _score_to_confidence(self, uncertainty: float) -> str:
        '''Convert uncertainty to confidence level.'''
        if uncertainty < 5:
            return 'high'
        elif uncertainty < 10:
            return 'medium'
        else:
            return 'low'

    def _get_top_features(self, features: Dict[str, float], n: int = 5) -> Dict[str, float]:
        """Get the top n most influential features."""
        # For now, return key valuation metrics
        # In production, would use SHAP values or similar
        key_features = [
            'pe_ratio', 'peg_ratio', 'roe', 'profit_margin',
            'debt_to_equity', 'revenue_growth', '52w_high_ratio'
        ]

        return {k: features.get(k, 0) for k in key_features[:n]}

    def _generate_warnings(self, features: Dict[str, float], score: float) -> List[str]:
        """Generate warnings based on feature values and score."""
        warnings = []

        # Check for extreme values
        if features.get('pe_ratio', 0) > 50:
            warnings.append('Very high P/E ratio - possible overvaluation')

        if features.get('debt_to_equity', 0) > 3:
            warnings.append('High debt levels - increased financial risk')

        if features.get('profit_margin', 0) < 0:
            warnings.append('Negative profit margins')

        # Score-based warnings
        if score > 80:
            warnings.append('Strong buy signal - verify with fundamental analysis')
        elif score < 20:
            warnings.append('Strong sell signal - verify with fundamental analysis')

        return warnings

    def train_model(self, training_data: List[Tuple[str, Dict[str, Any], float]],
                   validation_split: float = 0.2, epochs: int = 100) -> Dict[str, float]:
        """
        Train the neural network model on historical data.

        Parameters
        ----------
        training_data : List[Tuple[str, Dict[str, Any], float]]
            List of (ticker, data, target_return) tuples
        validation_split : float
            Fraction of data to use for validation
        epochs : int
            Number of training epochs

        Returns
        -------
        Dict[str, float]
            Training metrics (loss, accuracy, etc.)
        """
        if not training_data:
            raise ValueError('No training data provided')

        self.logger.info(f'Training model on {len(training_data)} samples')

        # Extract features and targets
        features_list = []
        targets = []

        for ticker, data, target in training_data:
            try:
                features = self.feature_engineer.extract_features(data)
                features_list.append(features)

                # Convert return to score (0-100)
                # -50% return = 0, 0% = 50, +50% = 100
                score = 50 + (target * 100)
                score = max(0, min(100, score))
                targets.append(score)

            except Exception as e:
                self.logger.warning(f'Failed to extract features for {ticker}: {e}')
                continue

        if len(features_list) < 10:
            raise ValueError('Insufficient valid training samples')

        # Fit scaler and transform features
        X = self.feature_engineer.fit_transform(features_list)
        y = np.array(targets)

        # Update model input dimension
        input_dim = X.shape[1]
        self.model = NeuralNetworkArchitecture(
            input_dim=input_dim,
            hidden_dims=[256, 128, 64, 32],
            dropout_rate=0.3,
            output_type='score'
        ).to(self.device)

        # Prepare data for PyTorch
        X_tensor = torch.FloatTensor(X).to(self.device)
        y_tensor = torch.FloatTensor(y.reshape(-1, 1)).to(self.device)

        # Train/validation split
        split_idx = int(len(X) * (1 - validation_split))
        X_train, X_val = X_tensor[:split_idx], X_tensor[split_idx:]
        y_train, y_val = y_tensor[:split_idx], y_tensor[split_idx:]

        # Training setup
        optimizer = optim.Adam(self.model.parameters(), lr=0.001)
        criterion = nn.MSELoss()

        # Create DataLoader for mini-batch training
        from torch.utils.data import DataLoader, TensorDataset

        batch_size = 32  # Standard batch size for neural networks
        train_dataset = TensorDataset(X_train, y_train)
        train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)

        # Training loop
        train_losses = []
        val_losses = []

        for epoch in range(epochs):
            # Training phase
            self.model.train()
            epoch_train_losses = []

            # Mini-batch training
            for batch_X, batch_y in train_loader:
                optimizer.zero_grad()

                batch_pred = self.model(batch_X)
                batch_loss = criterion(batch_pred, batch_y)

                batch_loss.backward()
                optimizer.step()

                epoch_train_losses.append(batch_loss.item())

            # Calculate average training loss for the epoch
            avg_train_loss = np.mean(epoch_train_losses)
            train_losses.append(avg_train_loss)

            # Validation phase
            self.model.eval()
            with torch.no_grad():
                val_pred = self.model(X_val)
                val_loss = criterion(val_pred, y_val)
                val_losses.append(val_loss.item())

            if (epoch + 1) % 10 == 0:
                self.logger.info(
                    f'Epoch {epoch + 1}/{epochs} - '
                    f'Train Loss: {avg_train_loss:.4f}, Val Loss: {val_loss.item():.4f}'
                )

        # Calculate final metrics
        self.model.eval()
        with torch.no_grad():
            final_train_pred = self.model(X_train).cpu().numpy()
            final_val_pred = self.model(X_val).cpu().numpy()

        train_mae = np.mean(np.abs(final_train_pred.flatten() - y_train.cpu().numpy().flatten()))
        val_mae = np.mean(np.abs(final_val_pred.flatten() - y_val.cpu().numpy().flatten()))

        metrics = {
            'final_train_loss': train_losses[-1],
            'final_val_loss': val_losses[-1],
            'train_mae': train_mae,
            'val_mae': val_mae,
            'epochs_trained': epochs
        }

        self.logger.info(f'Training completed. Validation MAE: {val_mae:.2f}')

        return metrics

    def save_model(self, path: Path) -> None:
        """Save the trained model to disk."""
        if not self.model:
            raise ValueError('No model to save')

        path.parent.mkdir(parents=True, exist_ok=True)

        checkpoint = {
            'model_state': self.model.state_dict(),
            'feature_names': self.feature_engineer.feature_names,
            'scaler_params': {
                'center_': self.feature_engineer.scaler.center_.tolist(),
                'scale_': self.feature_engineer.scaler.scale_.tolist()
            },
            'time_horizon': self.time_horizon
        }

        torch.save(checkpoint, path)
        self.logger.info(f'Model saved to {path}')

    def load_model(self, path: Path) -> None:
        """Load a trained model from disk."""
        if not path.exists():
            raise FileNotFoundError(f'Model file not found: {path}')

        checkpoint = torch.load(path, map_location=self.device)

        # Restore feature engineer
        self.feature_engineer.feature_names = checkpoint['feature_names']
        self.feature_engineer.scaler.center_ = np.array(checkpoint['scaler_params']['center_'])
        self.feature_engineer.scaler.scale_ = np.array(checkpoint['scaler_params']['scale_'])
        self.feature_engineer.is_fitted = True

        # Restore model
        input_dim = len(self.feature_engineer.feature_names)
        self.model = NeuralNetworkArchitecture(
            input_dim=input_dim,
            hidden_dims=[256, 128, 64, 32],
            dropout_rate=0.3,
            output_type='score'
        ).to(self.device)

        self.model.load_state_dict(checkpoint['model_state'])
        self.time_horizon = checkpoint.get('time_horizon', '1year')

        self.logger.info(f'Model loaded from {path}')
