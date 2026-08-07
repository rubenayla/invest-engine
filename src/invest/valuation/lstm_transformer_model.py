"""
Single-horizon LSTM/Transformer hybrid model for 1-year stock predictions.

This model combines:
- LSTM for temporal patterns in quarterly financial data
- Transformer attention for feature importance
- MC Dropout for confidence estimation
- Single output: 1-year expected return

Architecture:
    Temporal features (8 quarters) → LSTM(256)
    Static features → Dense(128)
    Concat → Transformer Encoder → Dense layers → 1-year return
    MC Dropout → Confidence intervals
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn

from invest.valuation.feature_extraction import FeatureExtractor


@dataclass
class PredictionResult:
    """Result from model prediction with confidence intervals."""

    ticker: str
    expected_return: float  # 1-year expected return (e.g., 0.15 = 15%)
    confidence_lower: float  # Lower bound of 95% confidence interval
    confidence_upper: float  # Upper bound of 95% confidence interval
    confidence_std: float  # Standard deviation from MC Dropout
    current_price: float
    fair_value: float
    margin_of_safety: float


class LSTMTransformerNetwork(nn.Module):
    """
    Hybrid LSTM/Transformer architecture for stock prediction.

    Processes temporal and static features separately, then combines them
    for final prediction using transformer attention.
    """

    def __init__(
        self,
        temporal_features: int = 15,  # Revenue, earnings, margins, etc.
        static_features: int = 36,  # Ratios, sector, market cap, etc.
        lstm_hidden: int = 256,
        transformer_heads: int = 8,
        dropout_rate: float = 0.3,
        num_quarters: int = 4
    ):
        """
        Initialize hybrid model.

        Parameters
        ----------
        temporal_features : int
            Number of features that vary over time (per quarter)
        static_features : int
            Number of static features (current snapshot)
        lstm_hidden : int
            Hidden dimension for LSTM
        transformer_heads : int
            Number of attention heads in transformer
        dropout_rate : float
            Dropout rate for MC Dropout confidence estimation
        num_quarters : int
            Number of historical quarters to use
        """
        super().__init__()

        self.temporal_features = temporal_features
        self.static_features = static_features
        self.lstm_hidden = lstm_hidden
        self.dropout_rate = dropout_rate

        # Temporal branch: LSTM for time-series patterns
        self.lstm = nn.LSTM(
            input_size=temporal_features,
            hidden_size=lstm_hidden,
            num_layers=2,
            batch_first=True,
            dropout=dropout_rate
        )

        # Static branch: Dense layers for snapshot features
        self.static_network = nn.Sequential(
            nn.Linear(static_features, 128),
            nn.ReLU(),
            nn.BatchNorm1d(128),
            nn.Dropout(dropout_rate),
            nn.Linear(128, 128),
            nn.ReLU(),
            nn.BatchNorm1d(128),
            nn.Dropout(dropout_rate)
        )

        # Combine temporal and static
        combined_dim = lstm_hidden + 128

        # Transformer encoder for attention
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=combined_dim,
            nhead=transformer_heads,
            dim_feedforward=512,
            dropout=dropout_rate,
            batch_first=True
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=2)

        # Final prediction head
        self.prediction_head = nn.Sequential(
            nn.Linear(combined_dim, 128),
            nn.ReLU(),
            nn.BatchNorm1d(128),
            nn.Dropout(dropout_rate),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.BatchNorm1d(64),
            nn.Dropout(dropout_rate),
            nn.Linear(64, 1)  # Single output: 1-year return
        )

    def forward(self, temporal: torch.Tensor, static: torch.Tensor) -> torch.Tensor:
        """
        Forward pass.

        Parameters
        ----------
        temporal : torch.Tensor
            Shape: (batch, num_quarters, temporal_features)
        static : torch.Tensor
            Shape: (batch, static_features)

        Returns
        -------
        torch.Tensor
            Predicted 1-year returns, shape: (batch, 1)
        """
        # Process temporal features with LSTM
        lstm_out, (h_n, c_n) = self.lstm(temporal)
        # Use last hidden state
        temporal_features = h_n[-1]  # Shape: (batch, lstm_hidden)

        # Process static features
        static_features = self.static_network(static)  # Shape: (batch, 128)

        # Combine features
        combined = torch.cat([temporal_features, static_features], dim=1)
        # Shape: (batch, lstm_hidden + 128)

        # Add sequence dimension for transformer
        combined = combined.unsqueeze(1)  # Shape: (batch, 1, combined_dim)

        # Transformer attention
        transformer_out = self.transformer(combined)
        transformer_out = transformer_out.squeeze(1)  # Shape: (batch, combined_dim)

        # Final prediction
        prediction = self.prediction_head(transformer_out)

        return prediction


class SingleHorizonModel:
    """
    Wrapper for LSTM/Transformer model with training and MC Dropout prediction.
    """

    def __init__(self, feature_dim_temporal: int = 15, feature_dim_static: int = 36):
        """Initialize the single-horizon model."""
        self.model = LSTMTransformerNetwork(
            temporal_features=feature_dim_temporal,
            static_features=feature_dim_static
        )

        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.model.to(self.device)

        # Feature extractor
        self.feature_extractor = FeatureExtractor(num_quarters=4)

        # Feature names (for reference)
        self.temporal_feature_names = self._get_temporal_features()
        self.static_feature_names = self._get_static_features()

    def _get_temporal_features(self) -> List[str]:
        """
        Define features that vary over time (quarterly).

        Returns
        -------
        List[str]
            Feature names to extract from quarterly financial statements
        """
        return [
            # Income statement
            'Total Revenue',
            'Operating Revenue',
            'Gross Profit',
            'Operating Income',
            'Net Income',
            'EBITDA',
            'Basic EPS',

            # Cash flow
            'Operating Cash Flow',
            'Free Cash Flow',
            'Capital Expenditure',

            # Balance sheet
            'Total Assets',
            'Total Debt',
            'Cash And Cash Equivalents',
            'Stockholders Equity',

            # Derived metrics
            'Revenue Growth QoQ',  # Calculated from revenue
        ]

    def _get_static_features(self) -> List[str]:
        """
        Define static features (current snapshot).

        Returns
        -------
        List[str]
            Feature names to extract from current data
        """
        return [
            # Valuation ratios
            'trailingPE', 'forwardPE', 'priceToBook', 'priceToSalesTrailing12Months',
            'enterpriseToRevenue', 'enterpriseToEbitda', 'pegRatio',

            # Profitability
            'returnOnEquity', 'returnOnAssets', 'profitMargins', 'operatingMargins',
            'grossMargins',

            # Growth
            'revenueGrowth', 'earningsGrowth', 'earningsQuarterlyGrowth',

            # Financial health
            'debtToEquity', 'currentRatio', 'quickRatio', 'totalCashPerShare',
            'freeCashflow',

            # Market metrics
            'beta', 'marketCap_log',  # Log-transformed for normalization

            # Sector encoding (one-hot or embedding)
            'sector_Technology', 'sector_Healthcare', 'sector_Financial Services',
            'sector_Consumer Cyclical', 'sector_Industrials', 'sector_Communication Services',
            'sector_Consumer Defensive', 'sector_Energy', 'sector_Utilities',
            'sector_Real Estate', 'sector_Basic Materials',

            # Price momentum
            'price_52w_high_ratio',  # current_price / 52w_high
            'price_52w_low_ratio',  # current_price / 52w_low
            'price_trend_30d',
        ]

    def predict_with_confidence(
        self,
        ticker: str,
        stock_data: dict,
        n_samples: int = 100
    ) -> Optional[PredictionResult]:
        """
        Make prediction with MC Dropout confidence estimation.

        Runs the model multiple times with dropout enabled to estimate
        prediction uncertainty.

        Parameters
        ----------
        ticker : str
            Stock ticker symbol
        stock_data : dict
            Stock data from StockDataReader
        n_samples : int
            Number of MC Dropout samples (default: 100)

        Returns
        -------
        PredictionResult or None
            Prediction with confidence intervals, or None if insufficient data
        """
        # Extract features
        temporal_features, static_features = self._extract_features(stock_data)

        if temporal_features is None or static_features is None:
            return None

        # Convert to tensors
        temporal_tensor = torch.FloatTensor(temporal_features).unsqueeze(0).to(self.device)
        static_tensor = torch.FloatTensor(static_features).unsqueeze(0).to(self.device)

        # MC Dropout: run model multiple times with dropout enabled
        # Note: We keep dropout active but disable batch normalization
        predictions = []

        # Enable dropout for MC sampling
        for module in self.model.modules():
            if isinstance(module, nn.Dropout):
                module.train()
            elif isinstance(module, nn.BatchNorm1d):
                module.eval()  # Keep BatchNorm in eval mode

        with torch.no_grad():
            for _ in range(n_samples):
                pred = self.model(temporal_tensor, static_tensor)
                predictions.append(pred.cpu().numpy()[0, 0])

        # Calculate statistics
        predictions = np.array(predictions)
        mean_return = float(np.mean(predictions))
        std_return = float(np.std(predictions))

        # 95% confidence interval (2 standard deviations)
        lower_bound = float(mean_return - 2 * std_return)
        upper_bound = float(mean_return + 2 * std_return)

        # Calculate fair value
        current_price = stock_data.get('info', {}).get('currentPrice', 0)
        fair_value = current_price * (1 + mean_return)
        margin_of_safety = ((fair_value - current_price) / current_price) if current_price > 0 else 0

        return PredictionResult(
            ticker=ticker,
            expected_return=mean_return,
            confidence_lower=lower_bound,
            confidence_upper=upper_bound,
            confidence_std=std_return,
            current_price=current_price,
            fair_value=fair_value,
            margin_of_safety=margin_of_safety
        )

    def _extract_features(
        self,
        stock_data: dict
    ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """
        Extract temporal and static features from stock data.

        Parameters
        ----------
        stock_data : dict
            Stock data from StockDataReader

        Returns
        -------
        Tuple[np.ndarray, np.ndarray] or (None, None)
            (temporal_features, static_features) or (None, None) if insufficient data
            temporal_features shape: (num_quarters, temporal_features)
            static_features shape: (static_features,)
        """
        # Extract temporal features from quarterly statements
        income_data = stock_data.get('income', [])
        cashflow_data = stock_data.get('cashflow', [])
        balance_sheet_data = stock_data.get('balance_sheet', [])

        temporal_features = self.feature_extractor.extract_temporal_features(
            income_data, cashflow_data, balance_sheet_data
        )

        # Extract static features from current snapshot
        static_features = self.feature_extractor.extract_static_features(stock_data)

        if temporal_features is None or static_features is None:
            return None, None

        return temporal_features, static_features
