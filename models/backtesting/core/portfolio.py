"""
Portfolio management for backtesting.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List

import pandas as pd

from .type_utils import validate_price_dict

logger = logging.getLogger(__name__)


@dataclass
class Trade:
    """Represents a single trade."""
    date: pd.Timestamp
    ticker: str
    action: str  # 'buy' or 'sell'
    shares: float
    price: float
    value: float
    commission: float
    slippage_cost: float

    @property
    def total_cost(self) -> float:
        """Total cost including commission and slippage."""
        return self.value + self.commission + self.slippage_cost


class Portfolio:
    """Portfolio manager for backtesting."""

    def __init__(self, initial_capital: float) -> None:
        """Initialize portfolio with starting capital."""
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.holdings: Dict[str, float] = {}  # {ticker: shares}
        self.cost_basis: Dict[str, float] = {}  # {ticker: average_cost_per_share}
        self.trade_history: List[Trade] = []

    def get_holdings(self) -> Dict[str, float]:
        """Get current holdings."""
        return self.holdings.copy()

    def get_value(self, current_prices: Dict[str, float]) -> float:
        """
        Calculate total portfolio value.

        Parameters
        ----------
        current_prices : Dict[str, float]
            Current prices for all holdings (must be Python floats, not pandas objects)

        Returns
        -------
        float
            Total portfolio value (cash + holdings) as Python float
        """
        # Validate and convert prices to ensure they're Python floats
        validated_prices = validate_price_dict(current_prices)

        holdings_value = sum(
            shares * validated_prices.get(ticker, 0.0)
            for ticker, shares in self.holdings.items()
        )
        # Ensure we return a Python float, not a pandas scalar
        return float(self.cash + holdings_value)

    def get_weights(self, current_prices: Dict[str, float]) -> Dict[str, float]:
        """Get current portfolio weights."""
        total_value = self.get_value(current_prices)

        if total_value == 0:
            return {}

        weights = {}
        for ticker, shares in self.holdings.items():
            position_value = shares * current_prices.get(ticker, 0)
            weights[ticker] = position_value / total_value

        weights['cash'] = self.cash / total_value
        return weights

    def rebalance(self, target_weights: Dict[str, float],
                  current_prices: Dict[str, float],
                  transaction_cost: float = 0.001,
                  slippage: float = 0.001,
                  date: pd.Timestamp = None) -> List[Trade]:
        """
        Rebalance portfolio to target weights.

        Parameters
        ----------
        target_weights : Dict[str, float]
            Target weights for each ticker (should sum to <= 1.0)
        current_prices : Dict[str, float]
            Current prices for all tickers
        transaction_cost : float
            Transaction cost as percentage (e.g., 0.001 = 0.1%)
        slippage : float
            Slippage as percentage
        date : pd.Timestamp
            Date of rebalancing

        Returns
        -------
        List[Trade]
            List of executed trades
        """
        trades = []
        total_value = self.get_value(current_prices)

        # Calculate target positions
        target_positions = {}
        for ticker, weight in target_weights.items():
            target_value = total_value * weight
            target_shares = target_value / current_prices[ticker]
            target_positions[ticker] = target_shares

        # Sell positions not in target or that need reduction
        for ticker in list(self.holdings.keys()):
            current_shares = self.holdings[ticker]
            target_shares = target_positions.get(ticker, 0)

            if current_shares > target_shares:
                shares_to_sell = current_shares - target_shares
                trade = self._execute_sell(
                    ticker=ticker,
                    shares=shares_to_sell,
                    price=current_prices[ticker],
                    transaction_cost=transaction_cost,
                    slippage=slippage,
                    date=date
                )
                trades.append(trade)

        # Buy new positions or increase existing ones
        for ticker, target_shares in target_positions.items():
            current_shares = self.holdings.get(ticker, 0)

            if target_shares > current_shares:
                shares_to_buy = target_shares - current_shares

                # Check if we have enough cash
                required_cash = shares_to_buy * current_prices[ticker] * (1 + transaction_cost + slippage)

                if required_cash <= self.cash:
                    trade = self._execute_buy(
                        ticker=ticker,
                        shares=shares_to_buy,
                        price=current_prices[ticker],
                        transaction_cost=transaction_cost,
                        slippage=slippage,
                        date=date
                    )
                    trades.append(trade)
                else:
                    logger.warning(f"Insufficient cash to buy {shares_to_buy} shares of {ticker}")

        self.trade_history.extend(trades)
        return trades

    def _execute_buy(self, ticker: str, shares: float, price: float,
                     transaction_cost: float, slippage: float,
                     date: pd.Timestamp) -> Trade:
        """Execute a buy trade."""
        # Apply slippage (pay slightly more)
        execution_price = price * (1 + slippage)
        value = shares * execution_price
        commission = value * transaction_cost
        slippage_cost = shares * price * slippage

        # Update portfolio
        self.cash -= (value + commission)

        if ticker in self.holdings:
            # Update average cost basis
            old_shares = self.holdings[ticker]
            old_cost = self.cost_basis[ticker] * old_shares
            new_cost = old_cost + value
            self.holdings[ticker] += shares
            self.cost_basis[ticker] = new_cost / self.holdings[ticker]
        else:
            self.holdings[ticker] = shares
            self.cost_basis[ticker] = execution_price

        return Trade(
            date=date,
            ticker=ticker,
            action='buy',
            shares=shares,
            price=execution_price,
            value=value,
            commission=commission,
            slippage_cost=slippage_cost
        )

    def _execute_sell(self, ticker: str, shares: float, price: float,
                      transaction_cost: float, slippage: float,
                      date: pd.Timestamp) -> Trade:
        """Execute a sell trade."""
        # Apply slippage (receive slightly less)
        execution_price = price * (1 - slippage)
        value = shares * execution_price
        commission = value * transaction_cost
        slippage_cost = shares * price * slippage

        # Update portfolio
        self.cash += (value - commission)
        self.holdings[ticker] -= shares

        # Remove ticker if position is closed
        if self.holdings[ticker] < 0.001:  # Essentially zero
            del self.holdings[ticker]
            if ticker in self.cost_basis:
                del self.cost_basis[ticker]

        return Trade(
            date=date,
            ticker=ticker,
            action='sell',
            shares=shares,
            price=execution_price,
            value=value,
            commission=commission,
            slippage_cost=slippage_cost
        )

    def get_realized_pnl(self) -> float:
        """Calculate realized P&L from closed positions."""
        realized_pnl = 0

        # Group trades by ticker
        trades_by_ticker = {}
        for trade in self.trade_history:
            if trade.ticker not in trades_by_ticker:
                trades_by_ticker[trade.ticker] = []
            trades_by_ticker[trade.ticker].append(trade)

        # Calculate P&L for each ticker
        for ticker, trades in trades_by_ticker.items():
            buy_cost = sum(t.total_cost for t in trades if t.action == 'buy')
            sell_proceeds = sum(t.value - t.commission for t in trades if t.action == 'sell')

            # Only count fully closed positions
            if ticker not in self.holdings:
                realized_pnl += (sell_proceeds - buy_cost)

        return realized_pnl

    def get_unrealized_pnl(self, current_prices: Dict[str, float]) -> float:
        """Calculate unrealized P&L for open positions."""
        unrealized_pnl = 0

        for ticker, shares in self.holdings.items():
            current_value = shares * current_prices.get(ticker, 0)
            cost_basis_value = shares * self.cost_basis.get(ticker, 0)
            unrealized_pnl += (current_value - cost_basis_value)

        return unrealized_pnl
