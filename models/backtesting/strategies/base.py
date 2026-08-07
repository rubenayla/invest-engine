"""
Base strategy interface for investment strategies.
"""

from typing import Any, Dict, Optional, Protocol

import pandas as pd


class Strategy(Protocol):
    """
    Protocol defining the interface that all investment strategies must implement.

    This ensures compatibility with the backtesting engine while allowing
    flexibility in implementation details.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """
        Initialize strategy with configuration.

        Parameters
        ----------
        config : Dict[str, Any], optional
            Strategy-specific configuration parameters
        """
        ...

    def generate_signals(self, market_data: Dict[str, Any],
                         current_portfolio: Dict[str, float],
                         date: pd.Timestamp) -> Dict[str, float]:
        """
        Generate target portfolio weights based on strategy logic.

        Parameters
        ----------
        market_data : Dict[str, Any]
            Point-in-time market data including:
            - current_prices: Dict[str, float] - Current stock prices
            - financial_metrics: Dict[str, Dict] - Financial data per stock

        current_portfolio : Dict[str, float]
            Current portfolio holdings as {ticker: weight}

        date : pd.Timestamp
            Current date in the backtest

        Returns
        -------
        Dict[str, float]
            Target portfolio weights as {ticker: weight}
            Weights should sum to <= 1.0 (remainder is cash)
        """
        ...
