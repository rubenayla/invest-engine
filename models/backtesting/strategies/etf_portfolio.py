"""
ETF portfolio investment strategy.

Implements various ETF-based strategies including core-satellite,
risk parity, and sector rotation approaches.
"""

import logging
import os
import sys
from typing import Any, Dict, Optional

import pandas as pd

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../../src'))


logger = logging.getLogger(__name__)


class ETFPortfolioStrategy:
    """
    ETF-based portfolio strategy for backtesting.

    Supports multiple allocation approaches:
    - Core-Satellite: Broad market core with tactical satellite positions
    - Risk Parity: Balance risk across asset classes
    - Momentum: Sector rotation based on recent performance
    - Low Cost: Focus on lowest expense ratio ETFs
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize ETF strategy with configuration.

        Parameters
        ----------
        config : Dict[str, Any], optional
            Strategy configuration including:
            - strategy_type: 'core_satellite', 'risk_parity', 'momentum', 'low_cost'
            - core_allocation: Percentage for core holdings (core_satellite only)
            - max_positions: Maximum number of ETF positions
            - rebalance_threshold: Drift threshold for rebalancing
            - expense_ratio_limit: Maximum acceptable expense ratio
        """
        self.config = config or {}

        # Strategy parameters
        self.strategy_type = self.config.get('strategy_type', 'core_satellite')
        self.max_positions = self.config.get('max_positions', 10)
        self.rebalance_threshold = self.config.get('rebalance_threshold', 0.05)
        self.expense_ratio_limit = self.config.get('expense_ratio_limit', 0.01)  # 1% max

        # Core-satellite specific
        self.core_allocation = self.config.get('core_allocation', 0.60)  # 60% core

        # Define ETF universes by category
        self.etf_universes = {
            'core': ['VTI', 'VOO', 'SPY', 'IVV', 'VT'],  # Broad market
            'international': ['VXUS', 'VEA', 'VWO', 'EFA', 'IEFA'],
            'bonds': ['AGG', 'BND', 'TLT', 'IEF', 'LQD'],
            'sectors': ['XLK', 'XLF', 'XLV', 'XLE', 'XLI', 'XLY', 'XLP', 'XLU', 'XLRE', 'XLB'],
            'commodities': ['GLD', 'SLV', 'USO', 'DBA', 'PDBC'],
            'real_estate': ['VNQ', 'REET', 'IYR', 'XLRE'],
            'growth': ['QQQ', 'VUG', 'IWF', 'ARKK', 'MGK'],
            'value': ['VTV', 'IWD', 'VYM', 'DVY', 'SCHD'],
            'small_cap': ['IWM', 'VB', 'IJR', 'VTWO'],
        }

        # Risk parity target weights (simplified)
        self.risk_parity_weights = {
            'equity': 0.30,
            'bonds': 0.40,
            'commodities': 0.15,
            'real_estate': 0.15
        }

    def generate_signals(self, market_data: Dict[str, Any],
                         current_portfolio: Dict[str, float],
                         date: pd.Timestamp) -> Dict[str, float]:
        """
        Generate target ETF portfolio weights based on selected strategy.

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
            Target weights for each ETF
        """
        logger.info(f'Generating ETF portfolio signals for {date} using {self.strategy_type} strategy')

        # Extract market data
        current_prices = market_data.get('current_prices', {})
        financial_metrics = market_data.get('financial_metrics', {})

        if not current_prices:
            logger.warning('No market data available, maintaining current portfolio')
            return current_portfolio

        # Filter for ETFs only
        etf_prices = {
            ticker: price for ticker, price in current_prices.items()
            if ticker in self._get_available_etfs()
        }

        if not etf_prices:
            logger.warning('No ETF data available')
            return {}

        # Generate weights based on strategy
        if self.strategy_type == 'core_satellite':
            target_weights = self._generate_core_satellite_weights(etf_prices, financial_metrics)
        elif self.strategy_type == 'risk_parity':
            target_weights = self._generate_risk_parity_weights(etf_prices, financial_metrics)
        elif self.strategy_type == 'momentum':
            target_weights = self._generate_momentum_weights(etf_prices, financial_metrics)
        elif self.strategy_type == 'low_cost':
            target_weights = self._generate_low_cost_weights(etf_prices, financial_metrics)
        else:
            logger.error(f'Unknown strategy type: {self.strategy_type}')
            return current_portfolio

        # Check if rebalancing is needed
        if self._should_rebalance(target_weights, current_portfolio):
            logger.info(f'Rebalancing: selected {len(target_weights)} ETFs')
            return target_weights
        else:
            logger.info('No rebalancing needed')
            return current_portfolio

    def _get_available_etfs(self) -> set:
        """Get all ETFs from our universe."""
        all_etfs = set()
        for category_etfs in self.etf_universes.values():
            all_etfs.update(category_etfs)
        return all_etfs

    def _generate_core_satellite_weights(self, etf_prices: Dict[str, float],
                                        financial_metrics: Dict[str, Dict]) -> Dict[str, float]:
        """Generate core-satellite allocation."""
        weights = {}

        # Core allocation (broad market ETFs)
        core_etfs = [etf for etf in self.etf_universes['core'] if etf in etf_prices]
        if core_etfs:
            # Pick the most liquid/largest core ETF (simplified: just use first available)
            core_etf = core_etfs[0]
            weights[core_etf] = self.core_allocation

        # Satellite allocation (tactical positions)
        satellite_allocation = 0.95 - self.core_allocation  # Keep 5% cash
        satellite_candidates = []

        # Look for momentum in sectors
        for etf in self.etf_universes['sectors']:
            if etf in etf_prices and etf in financial_metrics:
                metrics = financial_metrics[etf]
                # Use 3-month return as momentum indicator
                momentum = metrics.get('return_3m', 0)
                if momentum > 0:
                    satellite_candidates.append((etf, momentum))

        # Sort by momentum and select top performers
        satellite_candidates.sort(key=lambda x: x[1], reverse=True)
        num_satellites = min(len(satellite_candidates), self.max_positions - 1)  # -1 for core

        if num_satellites > 0:
            satellite_weight = satellite_allocation / num_satellites
            for etf, _ in satellite_candidates[:num_satellites]:
                weights[etf] = satellite_weight

        return weights

    def _generate_risk_parity_weights(self, etf_prices: Dict[str, float],
                                     financial_metrics: Dict[str, Dict]) -> Dict[str, float]:
        """Generate risk parity allocation across asset classes."""
        weights = {}

        # Select best ETF from each asset class
        selected_etfs = {}

        # Equity
        equity_etfs = [etf for etf in self.etf_universes['core'] if etf in etf_prices]
        if equity_etfs:
            selected_etfs['equity'] = equity_etfs[0]

        # Bonds
        bond_etfs = [etf for etf in self.etf_universes['bonds'] if etf in etf_prices]
        if bond_etfs:
            selected_etfs['bonds'] = bond_etfs[0]

        # Commodities
        commodity_etfs = [etf for etf in self.etf_universes['commodities'] if etf in etf_prices]
        if commodity_etfs:
            selected_etfs['commodities'] = commodity_etfs[0]

        # Real Estate
        reit_etfs = [etf for etf in self.etf_universes['real_estate'] if etf in etf_prices]
        if reit_etfs:
            selected_etfs['real_estate'] = reit_etfs[0]

        # Assign weights based on risk parity targets
        total_weight = 0.95  # Keep 5% cash
        for asset_class, etf in selected_etfs.items():
            target_weight = self.risk_parity_weights.get(asset_class, 0.25)
            weights[etf] = target_weight * total_weight

        return weights

    def _generate_momentum_weights(self, etf_prices: Dict[str, float],
                                  financial_metrics: Dict[str, Dict]) -> Dict[str, float]:
        """Generate momentum-based sector rotation weights."""
        weights = {}
        momentum_scores = []

        # Calculate momentum for all available ETFs
        for etf in etf_prices.keys():
            if etf in financial_metrics:
                metrics = financial_metrics[etf]

                # Composite momentum score
                score = 0
                score += metrics.get('return_1m', 0) * 0.2
                score += metrics.get('return_3m', 0) * 0.3
                score += metrics.get('return_6m', 0) * 0.3
                score += metrics.get('return_1y', 0) * 0.2

                if score > 0:  # Only consider positive momentum
                    momentum_scores.append((etf, score))

        # Sort by momentum and select top ETFs
        momentum_scores.sort(key=lambda x: x[1], reverse=True)
        selected = momentum_scores[:self.max_positions]

        if selected:
            # Equal weight among selected ETFs
            weight = 0.95 / len(selected)  # Keep 5% cash
            for etf, _ in selected:
                weights[etf] = weight

        return weights

    def _generate_low_cost_weights(self, etf_prices: Dict[str, float],
                                  financial_metrics: Dict[str, Dict]) -> Dict[str, float]:
        """Generate portfolio focused on lowest cost ETFs."""
        weights = {}
        etf_costs = []

        # Get expense ratios for all ETFs
        for etf in etf_prices.keys():
            if etf in financial_metrics:
                metrics = financial_metrics[etf]
                expense_ratio = metrics.get('expense_ratio', 1.0)  # Default high if unknown

                # Only consider ETFs below expense limit
                if expense_ratio <= self.expense_ratio_limit:
                    etf_costs.append((etf, expense_ratio))

        # Sort by expense ratio (lowest first)
        etf_costs.sort(key=lambda x: x[1])

        # Diversify across asset classes if possible
        selected_etfs = []
        asset_classes_covered = set()

        for etf, expense in etf_costs:
            # Determine asset class
            asset_class = self._get_etf_asset_class(etf)

            # Add if new asset class or still room for more positions
            if asset_class not in asset_classes_covered or len(selected_etfs) < self.max_positions:
                selected_etfs.append(etf)
                asset_classes_covered.add(asset_class)

                if len(selected_etfs) >= self.max_positions:
                    break

        # Equal weight among selected low-cost ETFs
        if selected_etfs:
            weight = 0.95 / len(selected_etfs)  # Keep 5% cash
            for etf in selected_etfs:
                weights[etf] = weight

        return weights

    def _get_etf_asset_class(self, etf: str) -> str:
        """Determine the asset class of an ETF."""
        for asset_class, etfs in self.etf_universes.items():
            if etf in etfs:
                return asset_class
        return 'unknown'

    def _should_rebalance(self, target_weights: Dict[str, float],
                         current_portfolio: Dict[str, float]) -> bool:
        """Determine if rebalancing is needed."""
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
