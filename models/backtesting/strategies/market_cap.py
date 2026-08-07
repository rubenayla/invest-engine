"""
Market cap weighted investment strategy.
Simply buys the biggest stocks by market capitalization.
"""

import logging
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


class MarketCapStrategy:
    """
    Simple strategy that buys the largest stocks by market capitalization.

    This serves as a baseline strategy for comparison - it simply invests
    in the biggest companies, which historically has been a reasonable
    approach due to the quality and stability of large-cap stocks.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize strategy with configuration.

        Parameters
        ----------
        config : Dict[str, Any], optional
            Strategy configuration including:
            - max_positions: Maximum number of stocks to hold (default 10)
            - weighting: 'equal' or 'market_cap' (default 'market_cap')
            - min_market_cap: Minimum market cap filter in billions (default 10)
            - rebalance_threshold: Threshold for rebalancing (default 0.05)
        """
        self.config = config or {}

        # Portfolio parameters
        self.max_positions = self.config.get('max_positions', 10)
        self.weighting = self.config.get('weighting', 'market_cap')
        self.min_market_cap = self.config.get('min_market_cap', 10) * 1e9  # Convert to actual value
        self.rebalance_threshold = self.config.get('rebalance_threshold', 0.05)

        # Track last portfolio for rebalancing decisions
        self.last_portfolio = {}

    def generate_signals(self, market_data: Dict[str, Any],
                         current_portfolio: Dict[str, float],
                         date: pd.Timestamp) -> Dict[str, float]:
        """
        Generate target portfolio weights based on market cap ranking.

        Parameters
        ----------
        market_data : Dict[str, Any]
            Point-in-time market data including prices and metrics
        current_portfolio : Dict[str, float]
            Current portfolio holdings
        date : pd.Timestamp
            Current date

        Returns
        -------
        Dict[str, float]
            Target weights for each ticker
        """
        logger.info(f'Generating market cap signals for {date}')

        # Extract market data
        current_prices = market_data.get('current_prices', {})
        financial_metrics = market_data.get('financial_metrics', {})

        if not current_prices or not financial_metrics:
            logger.warning('No market data available, maintaining current portfolio')
            return current_portfolio

        # Get market caps and filter
        market_caps = {}
        for ticker in current_prices.keys():
            if ticker not in financial_metrics:
                continue

            market_cap = financial_metrics[ticker].get('market_cap')
            if market_cap and market_cap >= self.min_market_cap:
                market_caps[ticker] = market_cap

        if not market_caps:
            logger.warning('No stocks meet market cap criteria')
            return {}

        # Sort by market cap and select top N
        sorted_stocks = sorted(market_caps.items(), key=lambda x: x[1], reverse=True)
        selected_stocks = sorted_stocks[:self.max_positions]

        # Calculate weights based on weighting method
        if self.weighting == 'equal':
            weights = self._calculate_equal_weights(selected_stocks)
        else:  # market_cap weighting
            weights = self._calculate_market_cap_weights(selected_stocks)

        # Check if rebalancing is needed
        if self._should_rebalance(weights, current_portfolio):
            logger.info(f'Rebalancing: selected {len(weights)} stocks')
            self.last_portfolio = weights
            return weights
        else:
            logger.info('No rebalancing needed, maintaining current portfolio')
            return current_portfolio

    def _calculate_equal_weights(self, selected_stocks: List[tuple]) -> Dict[str, float]:
        """Calculate equal weights for selected stocks."""
        if not selected_stocks:
            return {}

        # Equal weight with 5% cash reserve
        weight = 0.95 / len(selected_stocks)
        weights = {ticker: weight for ticker, _ in selected_stocks}

        return weights

    def _calculate_market_cap_weights(self, selected_stocks: List[tuple]) -> Dict[str, float]:
        """Calculate market cap weighted allocation."""
        if not selected_stocks:
            return {}

        # Calculate total market cap
        total_market_cap = sum(market_cap for _, market_cap in selected_stocks)

        # Calculate weights proportional to market cap
        weights = {}
        for ticker, market_cap in selected_stocks:
            # Market cap weight with 5% cash reserve
            weight = (market_cap / total_market_cap) * 0.95

            # Apply position limits
            min_weight = 0.02  # 2% minimum
            max_weight = 0.30  # 30% maximum (for diversification)
            weight = max(min_weight, min(max_weight, weight))

            weights[ticker] = weight

        # Normalize weights to ensure they sum to target
        total_weight = sum(weights.values())
        if total_weight > 0.95:
            factor = 0.95 / total_weight
            weights = {k: v * factor for k, v in weights.items()}

        return weights

    def _should_rebalance(self, target_weights: Dict[str, float],
                         current_portfolio: Dict[str, float]) -> bool:
        """
        Determine if rebalancing is needed based on drift from target.

        This helps reduce transaction costs by only rebalancing when
        the portfolio has drifted significantly from target weights.
        """
        # Always rebalance if portfolio is empty
        if not current_portfolio:
            return True

        # Check if holdings have changed significantly
        current_tickers = set(current_portfolio.keys())
        target_tickers = set(target_weights.keys())

        # Rebalance if the set of holdings changes
        if current_tickers != target_tickers:
            return True

        # Check weight drift
        for ticker in target_tickers:
            current_weight = current_portfolio.get(ticker, 0)
            target_weight = target_weights.get(ticker, 0)

            # Calculate absolute drift
            drift = abs(current_weight - target_weight)

            # Rebalance if any position has drifted beyond threshold
            if drift > self.rebalance_threshold:
                return True

        return False
