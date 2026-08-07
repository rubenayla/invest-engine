"""
Simple ratio-based valuation model.

This implements a traditional value investing approach using fundamental ratios
without complex cash flow projections. Sometimes the simplest approaches work best!
"""

import logging
from typing import Any, Dict, Optional

import numpy as np

logger = logging.getLogger(__name__)


class SimpleRatiosModel:
    """
    Simple ratio-based valuation model using traditional value metrics.

    This model assigns intrinsic value based on ratio comparisons to:
    - Historical averages
    - Sector medians
    - Market benchmarks

    The approach is inspired by Benjamin Graham's methods and assumes
    that ratios reverting to historical means provides valuation guidance.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the simple ratios valuation model.

        Parameters
        ----------
        config : Dict[str, Any], optional
            Configuration including ratio targets and weights
        """
        self.config = config or {}

        # Ratio weights for composite score
        self.pe_weight = self.config.get("pe_weight", 0.25)
        self.pb_weight = self.config.get("pb_weight", 0.20)
        self.ps_weight = self.config.get("ps_weight", 0.15)
        self.ev_ebitda_weight = self.config.get("ev_ebitda_weight", 0.20)
        self.dividend_yield_weight = self.config.get("dividend_yield_weight", 0.10)
        self.peg_weight = self.config.get("peg_weight", 0.10)

        # Target ratios (market "fair value" benchmarks)
        self.target_ratios = {
            "pe_target": self.config.get("pe_target", 15.0),  # S&P 500 historical average
            "pb_target": self.config.get("pb_target", 2.5),  # Reasonable book value multiple
            "ps_target": self.config.get("ps_target", 2.0),  # Conservative sales multiple
            "ev_ebitda_target": self.config.get("ev_ebitda_target", 12.0),  # EBITDA multiple
            "dividend_yield_target": self.config.get("dividend_yield_target", 0.03),  # 3% yield
            "peg_target": self.config.get("peg_target", 1.0),  # PEG = 1 is "fair value"
        }

        # Sector adjustments (some sectors naturally trade at different multiples)
        self.sector_adjustments = {
            "Technology": {"pe_adj": 1.5, "pb_adj": 1.3, "ps_adj": 1.8},
            "Healthcare": {"pe_adj": 1.2, "pb_adj": 1.1, "ps_adj": 1.3},
            "Utilities": {"pe_adj": 0.8, "pb_adj": 0.9, "ps_adj": 0.7},
            "Energy": {"pe_adj": 0.7, "pb_adj": 0.8, "ps_adj": 0.6},
            "Financials": {"pe_adj": 0.6, "pb_adj": 1.2, "ps_adj": 0.4},
            "Real Estate": {"pe_adj": 0.8, "pb_adj": 0.9, "ps_adj": 0.8},
            "Consumer Staples": {"pe_adj": 0.9, "pb_adj": 1.0, "ps_adj": 0.8},
            "Industrials": {"pe_adj": 1.0, "pb_adj": 1.0, "ps_adj": 1.0},
            "Materials": {"pe_adj": 0.8, "pb_adj": 0.9, "ps_adj": 0.7},
            "Consumer Discretionary": {"pe_adj": 1.1, "pb_adj": 1.1, "ps_adj": 1.2},
            "Communication Services": {"pe_adj": 1.3, "pb_adj": 1.2, "ps_adj": 1.5},
        }

    def calculate_valuation(self, stock_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate simple ratio-based valuation.

        Parameters
        ----------
        stock_data : Dict[str, Any]
            Stock fundamental and market data

        Returns
        -------
        Dict[str, Any]
            Valuation results including intrinsic value and component scores
        """
        ticker = stock_data.get("ticker", "Unknown")
        current_price = stock_data.get("current_price", 0)
        sector = stock_data.get("sector", "Unknown")

        logger.debug(f"Calculating simple ratios valuation for {ticker}")

        try:
            # Get current ratios
            current_ratios = self._extract_ratios(stock_data)

            if not current_ratios:
                return {
                    "model": "simple_ratios",
                    "ticker": ticker,
                    "valuation_price": None,
                    "current_price": current_price,
                    "upside_potential": None,
                    "confidence": "low",
                    "error": "Insufficient ratio data",
                }

            # Calculate sector-adjusted targets
            adjusted_targets = self._get_sector_adjusted_targets(sector)

            # Calculate component scores
            component_scores = self._calculate_component_scores(current_ratios, adjusted_targets)

            # Calculate composite valuation score
            composite_score = self._calculate_composite_score(component_scores)

            # Estimate intrinsic value based on ratio attractiveness
            intrinsic_value = self._estimate_intrinsic_value(
                current_price, current_ratios, adjusted_targets, composite_score
            )

            # Calculate upside potential
            upside_potential = (
                ((intrinsic_value / current_price) - 1) * 100 if current_price > 0 else None
            )

            # Determine confidence level
            confidence = self._assess_confidence(component_scores, current_ratios)

            return {
                "model": "simple_ratios",
                "ticker": ticker,
                "valuation_price": intrinsic_value,
                "current_price": current_price,
                "upside_potential": upside_potential,
                "confidence": confidence,
                "composite_score": composite_score,
                "component_scores": component_scores,
                "current_ratios": current_ratios,
                "target_ratios": adjusted_targets,
                "sector_adjustments": self.sector_adjustments.get(sector, {}),
            }

        except Exception as e:
            logger.error(f"Error calculating simple ratios valuation for {ticker}: {e}")
            return {
                "model": "simple_ratios",
                "ticker": ticker,
                "valuation_price": None,
                "current_price": current_price,
                "upside_potential": None,
                "confidence": "low",
                "error": str(e),
            }

    def _extract_ratios(self, stock_data: Dict[str, Any]) -> Dict[str, float]:
        """Extract relevant ratios from stock data."""
        ratios = {}

        # P/E ratio
        pe = stock_data.get("pe_ratio")
        if pe and pe > 0:
            ratios["pe"] = pe

        # P/B ratio
        pb = stock_data.get("pb_ratio")
        if pb and pb > 0:
            ratios["pb"] = pb

        # P/S ratio
        ps = stock_data.get("ps_ratio")
        if ps and ps > 0:
            ratios["ps"] = ps

        # EV/EBITDA
        ev_ebitda = stock_data.get("ev_ebitda")
        if ev_ebitda and ev_ebitda > 0:
            ratios["ev_ebitda"] = ev_ebitda

        # Dividend yield
        div_yield = stock_data.get("dividend_yield")
        if div_yield and div_yield >= 0:
            ratios["dividend_yield"] = div_yield

        # PEG ratio
        peg = stock_data.get("peg_ratio")
        if peg and peg > 0:
            ratios["peg"] = peg

        return ratios

    def _get_sector_adjusted_targets(self, sector: str) -> Dict[str, float]:
        """Get sector-adjusted target ratios."""
        base_targets = self.target_ratios.copy()

        # Apply sector adjustments
        sector_adj = self.sector_adjustments.get(sector, {})

        adjusted_targets = {}
        for ratio, base_value in base_targets.items():
            ratio_key = ratio.replace("_target", "")
            adjustment_key = f"{ratio_key}_adj"

            if adjustment_key in sector_adj:
                adjusted_targets[ratio] = base_value * sector_adj[adjustment_key]
            else:
                adjusted_targets[ratio] = base_value

        return adjusted_targets

    def _calculate_component_scores(
        self, current_ratios: Dict[str, float], targets: Dict[str, float]
    ) -> Dict[str, float]:
        """Calculate individual component scores (0-100, higher is better value)."""
        scores = {}

        # P/E score (lower P/E is better)
        if "pe" in current_ratios:
            pe_target = targets["pe_target"]
            current_pe = current_ratios["pe"]
            # Score = 100 when PE = target/2, 50 when PE = target, 0 when PE = target*2
            pe_score = max(0, min(100, 100 * (2 - current_pe / pe_target)))
            scores["pe_score"] = pe_score

        # P/B score (lower P/B is better)
        if "pb" in current_ratios:
            pb_target = targets["pb_target"]
            current_pb = current_ratios["pb"]
            pb_score = max(0, min(100, 100 * (2 - current_pb / pb_target)))
            scores["pb_score"] = pb_score

        # P/S score (lower P/S is better)
        if "ps" in current_ratios:
            ps_target = targets["ps_target"]
            current_ps = current_ratios["ps"]
            ps_score = max(0, min(100, 100 * (2 - current_ps / ps_target)))
            scores["ps_score"] = ps_score

        # EV/EBITDA score (lower is better)
        if "ev_ebitda" in current_ratios:
            ebitda_target = targets["ev_ebitda_target"]
            current_ebitda = current_ratios["ev_ebitda"]
            ebitda_score = max(0, min(100, 100 * (2 - current_ebitda / ebitda_target)))
            scores["ev_ebitda_score"] = ebitda_score

        # Dividend yield score (higher yield is better, up to a point)
        if "dividend_yield" in current_ratios:
            yield_target = targets["dividend_yield_target"]
            current_yield = current_ratios["dividend_yield"]
            # Optimal yield is 1.5x target, diminishing returns after that
            optimal_yield = yield_target * 1.5
            if current_yield <= optimal_yield:
                yield_score = (current_yield / optimal_yield) * 100
            else:
                # Diminishing returns for very high yields (could signal distress)
                yield_score = 100 - min(50, (current_yield - optimal_yield) * 1000)
            scores["dividend_yield_score"] = max(0, yield_score)

        # PEG score (closer to 1.0 is better)
        if "peg" in current_ratios:
            peg_target = targets["peg_target"]
            current_peg = current_ratios["peg"]
            # Perfect score at PEG = 1, declining as it moves away
            peg_deviation = abs(current_peg - peg_target)
            peg_score = max(0, 100 - (peg_deviation * 50))  # 50% penalty per point away from 1.0
            scores["peg_score"] = peg_score

        return scores

    def _calculate_composite_score(self, component_scores: Dict[str, float]) -> float:
        """Calculate weighted composite score."""
        weighted_sum = 0
        total_weight = 0

        # Apply weights to available scores
        weight_mapping = {
            "pe_score": self.pe_weight,
            "pb_score": self.pb_weight,
            "ps_score": self.ps_weight,
            "ev_ebitda_score": self.ev_ebitda_weight,
            "dividend_yield_score": self.dividend_yield_weight,
            "peg_score": self.peg_weight,
        }

        for score_name, score_value in component_scores.items():
            weight = weight_mapping.get(score_name, 0)
            if weight > 0:
                weighted_sum += score_value * weight
                total_weight += weight

        # Normalize by actual total weight used
        if total_weight > 0:
            return weighted_sum / total_weight
        else:
            return 50  # Neutral score if no components available

    def _estimate_intrinsic_value(
        self,
        current_price: float,
        current_ratios: Dict[str, float],
        targets: Dict[str, float],
        composite_score: float,
    ) -> float:
        """Estimate intrinsic value based on ratio attractiveness."""

        # Base intrinsic value on how current ratios compare to targets
        value_multiplier = 1.0

        # P/E based adjustment
        if "pe" in current_ratios:
            pe_ratio = targets["pe_target"] / current_ratios["pe"]
            value_multiplier *= pe_ratio**0.3  # 30% weight

        # P/B based adjustment
        if "pb" in current_ratios:
            pb_ratio = targets["pb_target"] / current_ratios["pb"]
            value_multiplier *= pb_ratio**0.2  # 20% weight

        # P/S based adjustment
        if "ps" in current_ratios:
            ps_ratio = targets["ps_target"] / current_ratios["ps"]
            value_multiplier *= ps_ratio**0.15  # 15% weight

        # EV/EBITDA based adjustment
        if "ev_ebitda" in current_ratios:
            ebitda_ratio = targets["ev_ebitda_target"] / current_ratios["ev_ebitda"]
            value_multiplier *= ebitda_ratio**0.2  # 20% weight

        # Apply composite score adjustment (remaining weight)
        score_multiplier = 0.5 + (composite_score / 100)  # 0.5 to 1.5 multiplier
        value_multiplier *= score_multiplier**0.15  # 15% weight

        # Cap extreme adjustments (no more than 3x up or 0.33x down)
        value_multiplier = max(0.33, min(3.0, value_multiplier))

        return current_price * value_multiplier

    def _assess_confidence(
        self, component_scores: Dict[str, float], current_ratios: Dict[str, float]
    ) -> str:
        """Assess confidence in the valuation."""

        # Count available metrics
        available_metrics = len(component_scores)

        # Calculate score consistency (lower variance = higher confidence)
        if len(component_scores) > 1:
            scores = list(component_scores.values())
            score_std = np.std(scores)
        else:
            score_std = 50  # High uncertainty with only one metric

        # Check for extreme ratios (could indicate data issues)
        extreme_ratios = 0
        for ratio_name, ratio_value in current_ratios.items():
            if ratio_name == "pe" and (ratio_value > 100 or ratio_value < 5):
                extreme_ratios += 1
            elif ratio_name == "pb" and (ratio_value > 20 or ratio_value < 0.1):
                extreme_ratios += 1
            elif ratio_name == "ps" and (ratio_value > 50 or ratio_value < 0.1):
                extreme_ratios += 1

        # Determine confidence
        if available_metrics >= 4 and score_std < 20 and extreme_ratios == 0:
            return "high"
        elif available_metrics >= 3 and score_std < 30 and extreme_ratios <= 1:
            return "medium"
        else:
            return "low"


def calculate_simple_ratios_valuation(
    stock_data: Dict[str, Any], config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Convenience function to calculate simple ratios valuation.

    Parameters
    ----------
    stock_data : Dict[str, Any]
        Stock data including ratios and market information
    config : Dict[str, Any], optional
        Model configuration

    Returns
    -------
    Dict[str, Any]
        Valuation results
    """
    model = SimpleRatiosModel(config)
    return model.calculate_valuation(stock_data)
