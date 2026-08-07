"""
Screening-based investment strategy for backtesting.
"""

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class ScreeningStrategy:
    """
    Investment strategy based on the screening system.
    Selects stocks based on quality, value, growth, and risk metrics.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize strategy with configuration.

        Parameters
        ----------
        config : Dict[str, Any], optional
            Strategy configuration including:
            - quality_weight: Weight for quality score (default 0.30)
            - value_weight: Weight for value score (default 0.30)
            - growth_weight: Weight for growth score (default 0.25)
            - risk_weight: Weight for risk score (default 0.15)
            - min_score: Minimum composite score to include (default 0.5)
            - max_positions: Maximum number of positions (default 10)
        """
        self.config = config or {}

        # Scoring weights
        self.quality_weight = self.config.get('quality_weight', 0.30)
        self.value_weight = self.config.get('value_weight', 0.30)
        self.growth_weight = self.config.get('growth_weight', 0.25)
        self.risk_weight = self.config.get('risk_weight', 0.15)

        # Selection criteria
        self.min_score = self.config.get('min_score', 0.5)
        self.max_positions = self.config.get('max_positions', 10)

        # Thresholds for screening
        self.thresholds = {
            'min_roe': self.config.get('min_roe', 0.10),
            'max_debt_equity': self.config.get('max_debt_equity', 2.0),
            'min_current_ratio': self.config.get('min_current_ratio', 1.0),
            'max_pe': self.config.get('max_pe', 30.0),
            'max_pb': self.config.get('max_pb', 5.0),
            'min_revenue_growth': self.config.get('min_revenue_growth', 0.0),
            'max_beta': self.config.get('max_beta', 1.5)
        }

    def generate_signals(self, market_data: Dict[str, Any],
                         current_portfolio: Dict[str, float],
                         date: pd.Timestamp) -> Dict[str, float]:
        """
        Generate target portfolio weights based on screening.

        Parameters
        ----------
        market_data : Dict[str, Any]
            Point-in-time market data including prices and fundamentals
        current_portfolio : Dict[str, float]
            Current portfolio holdings
        date : pd.Timestamp
            Current date

        Returns
        -------
        Dict[str, float]
            Target weights for each ticker
        """
        logger.info(f"Generating signals for {date}")

        # Extract metrics
        metrics = market_data.get('financial_metrics', {})
        current_prices = market_data.get('current_prices', {})

        if not metrics or not current_prices:
            logger.warning("No data available, maintaining current portfolio")
            return current_portfolio

        # Score each stock
        scores = {}
        for ticker in metrics.keys():
            if ticker not in current_prices:
                continue

            ticker_metrics = metrics[ticker]

            # Calculate component scores
            quality_score = self._calculate_quality_score(ticker_metrics)
            value_score = self._calculate_value_score(ticker_metrics)
            growth_score = self._calculate_growth_score(ticker_metrics)
            risk_score = self._calculate_risk_score(ticker_metrics)

            # Calculate composite score
            if all(s is not None for s in [quality_score, value_score, growth_score, risk_score]):
                composite_score = (
                    quality_score * self.quality_weight +
                    value_score * self.value_weight +
                    growth_score * self.growth_weight +
                    risk_score * self.risk_weight
                )

                scores[ticker] = {
                    'composite': composite_score,
                    'quality': quality_score,
                    'value': value_score,
                    'growth': growth_score,
                    'risk': risk_score
                }

        # Select top stocks
        selected_stocks = self._select_stocks(scores)

        # Generate target weights
        target_weights = self._calculate_weights(selected_stocks, scores)

        logger.info(f"Selected {len(target_weights)} stocks with total weight {sum(target_weights.values()):.2%}")

        return target_weights

    def _calculate_quality_score(self, metrics: Dict[str, Any]) -> Optional[float]:
        """Calculate quality score (0-1)."""
        score_components = []

        # ROE score
        roe = metrics.get('roe')
        if roe is not None:
            roe_score = min(1.0, max(0.0, roe / 0.30))  # 30% ROE = perfect score
            score_components.append(roe_score)

        # ROA score
        roa = metrics.get('roa')
        if roa is not None:
            roa_score = min(1.0, max(0.0, roa / 0.15))  # 15% ROA = perfect score
            score_components.append(roa_score)

        # Debt/Equity score (inverted)
        debt_equity = metrics.get('debt_to_equity')
        if debt_equity is not None:
            de_score = max(0.0, 1.0 - debt_equity / 2.0)  # 0 D/E = 1, 2+ D/E = 0
            score_components.append(de_score)

        # Current ratio score
        current_ratio = metrics.get('current_ratio')
        if current_ratio is not None:
            cr_score = min(1.0, max(0.0, (current_ratio - 0.5) / 2.0))  # 2.5+ = perfect
            score_components.append(cr_score)

        # Operating margin score
        op_margin = metrics.get('operating_margin')
        if op_margin is not None:
            margin_score = min(1.0, max(0.0, op_margin / 0.25))  # 25% margin = perfect
            score_components.append(margin_score)

        return np.mean(score_components) if score_components else None

    def _calculate_value_score(self, metrics: Dict[str, Any]) -> Optional[float]:
        """Calculate value score (0-1)."""
        score_components = []

        # P/E score (inverted)
        pe = metrics.get('pe_ratio')
        if pe is not None and pe > 0:
            pe_score = max(0.0, 1.0 - (pe - 10) / 20)  # PE 10 = 1, PE 30+ = 0
            score_components.append(pe_score)

        # P/B score (inverted)
        pb = metrics.get('pb_ratio')
        if pb is not None and pb > 0:
            pb_score = max(0.0, 1.0 - (pb - 1) / 4)  # PB 1 = 1, PB 5+ = 0
            score_components.append(pb_score)

        # P/S score (inverted)
        ps = metrics.get('ps_ratio')
        if ps is not None and ps > 0:
            ps_score = max(0.0, 1.0 - (ps - 1) / 4)  # PS 1 = 1, PS 5+ = 0
            score_components.append(ps_score)

        # Dividend yield score
        div_yield = metrics.get('dividend_yield')
        if div_yield is not None:
            yield_score = min(1.0, div_yield / 0.04)  # 4% yield = perfect
            score_components.append(yield_score)

        return np.mean(score_components) if score_components else None

    def _calculate_growth_score(self, metrics: Dict[str, Any]) -> Optional[float]:
        """Calculate growth score (0-1)."""
        score_components = []

        # Revenue growth score
        rev_growth = metrics.get('revenue_growth')
        if rev_growth is not None:
            rev_score = min(1.0, max(0.0, rev_growth / 0.20))  # 20% growth = perfect
            score_components.append(rev_score)

        # Earnings growth score
        earn_growth = metrics.get('earnings_growth')
        if earn_growth is not None:
            earn_score = min(1.0, max(0.0, earn_growth / 0.20))  # 20% growth = perfect
            score_components.append(earn_score)

        # Momentum scores (recent returns)
        for period, weight in [('return_1m', 0.1), ('return_3m', 0.2),
                                ('return_6m', 0.3), ('return_1y', 0.4)]:
            ret = metrics.get(period)
            if ret is not None:
                # Normalize returns to 0-1 scale
                ret_score = min(1.0, max(0.0, (ret + 10) / 40))  # -10% to +30% mapped to 0-1
                score_components.append(ret_score * weight)

        return np.mean(score_components) if score_components else None

    def _calculate_risk_score(self, metrics: Dict[str, Any]) -> Optional[float]:
        """Calculate risk score (0-1, lower risk = higher score)."""
        score_components = []

        # Beta score (inverted)
        beta = metrics.get('beta')
        if beta is not None:
            beta_score = max(0.0, 1.0 - abs(beta - 1.0))  # Beta = 1 is perfect
            score_components.append(beta_score)

        # Volatility score (inverted)
        volatility = metrics.get('volatility')
        if volatility is not None:
            vol_score = max(0.0, 1.0 - volatility / 50)  # 0% vol = 1, 50%+ vol = 0
            score_components.append(vol_score)

        # Debt/Equity score (inverted) - also part of risk
        debt_equity = metrics.get('debt_to_equity')
        if debt_equity is not None:
            de_score = max(0.0, 1.0 - debt_equity / 3.0)  # 0 D/E = 1, 3+ D/E = 0
            score_components.append(de_score)

        return np.mean(score_components) if score_components else None

    def _select_stocks(self, scores: Dict[str, Dict[str, float]]) -> List[str]:
        """Select stocks that pass screening criteria."""
        selected = []

        # Sort by composite score
        sorted_stocks = sorted(
            scores.items(),
            key=lambda x: x[1]['composite'],
            reverse=True
        )

        for ticker, score_data in sorted_stocks:
            # Check minimum score threshold
            if score_data['composite'] < self.min_score:
                continue

            selected.append(ticker)

            # Limit number of positions
            if len(selected) >= self.max_positions:
                break

        return selected

    def _calculate_weights(self, selected_stocks: List[str],
                           scores: Dict[str, Dict[str, float]]) -> Dict[str, float]:
        """Calculate portfolio weights for selected stocks."""
        if not selected_stocks:
            return {}

        # Get scores for selected stocks
        selected_scores = {
            ticker: scores[ticker]['composite']
            for ticker in selected_stocks
        }

        # Calculate weights proportional to scores
        total_score = sum(selected_scores.values())

        if total_score == 0:
            # Equal weight if all scores are zero
            weight = 0.95 / len(selected_stocks)  # Keep 5% cash
            return {ticker: weight for ticker in selected_stocks}

        # Score-weighted allocation
        weights = {}
        for ticker, score in selected_scores.items():
            weight = (score / total_score) * 0.95  # Keep 5% cash

            # Apply position size limits
            weight = max(0.01, min(0.20, weight))  # 1% min, 20% max
            weights[ticker] = weight

        # Normalize weights to ensure they sum to target
        total_weight = sum(weights.values())
        if total_weight > 0.95:
            factor = 0.95 / total_weight
            weights = {k: v * factor for k, v in weights.items()}

        return weights
