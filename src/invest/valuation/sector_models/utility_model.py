"""
Utility Sector Valuation Model

Utility companies require specialized approaches because they:
- Have regulated revenue streams and stable cash flows
- Pay high, stable dividends
- Have large capital expenditure requirements
- Face regulatory approval for rate changes
- Are sensitive to interest rates
- Have predictable, bond-like characteristics
"""

import logging
from typing import Any, Dict, Optional

from ...config.constants import VALUATION_DEFAULTS
from ...exceptions import InsufficientDataError
from ..base import ValuationModel, ValuationResult

logger = logging.getLogger(__name__)


class UtilityModel(ValuationModel):
    """
    Specialized valuation model for utility companies.

    This model emphasizes:
    - Dividend yield and sustainability
    - Regulated return on equity
    - Rate base growth
    - Interest rate sensitivity
    - Stable cash flow patterns
    """

    def __init__(self):
        super().__init__('utility')

    def is_suitable(self, ticker: str, data: Dict[str, Any]) -> bool:
        """Check if company is a utility suitable for this model."""
        try:
            info = data.get('info', {})

            sector = info.get('sector', '').lower()
            industry = info.get('industry', '').lower()

            # Utility sector indicators
            utility_keywords = [
                'utilities', 'utility', 'electric', 'gas', 'water',
                'power', 'energy', 'transmission', 'distribution',
                'renewable energy', 'solar', 'wind'
            ]

            is_utility = any(keyword in sector or keyword in industry for keyword in utility_keywords)

            # Additional checks for utility characteristics
            if is_utility:
                # Utilities typically have high dividend yields
                dividend_yield = info.get('dividendYield')
                if dividend_yield and dividend_yield > 0.03:  # >3% dividend yield
                    return True

                # Utilities have low beta (less volatile than market)
                beta = info.get('beta')
                if beta and beta < 0.8:  # Low volatility
                    return True

                return True  # Trust sector classification

            # Check for utility-like characteristics even if not classified as utility
            dividend_yield = info.get('dividendYield')
            beta = info.get('beta')

            if (dividend_yield and dividend_yield > 0.05 and  # >5% dividend yield
                beta and beta < 0.7):  # Very stable
                return True

            return False

        except Exception:
            return False

    def _validate_inputs(self, ticker: str, data: Dict[str, Any]) -> None:
        """Validate utility-specific input data."""
        info = data.get('info', {})

        if not info:
            raise InsufficientDataError(ticker, ['info'])

        # Utilities should have dividend data
        dividend_yield = info.get('dividendYield')
        if not dividend_yield or dividend_yield <= 0:
            logger.warning(f'Utility {ticker} missing dividend yield - unusual for sector')

    def _calculate_valuation(self, ticker: str, data: Dict[str, Any]) -> ValuationResult:
        """Calculate utility valuation using dividend and stability-focused approaches."""
        info = data.get('info', {})

        # Extract utility-relevant metrics
        current_price = self._safe_float(info.get('currentPrice'))
        dividend_yield = self._safe_float(info.get('dividendYield'))
        dividend_rate = self._safe_float(info.get('dividendRate'))
        payout_ratio = self._safe_float(info.get('payoutRatio'))
        book_value = self._safe_float(info.get('bookValue'))
        roe = self._safe_float(info.get('returnOnEquity'))
        beta = self._safe_float(info.get('beta'))

        # Calculate different utility-focused valuations
        dividend_discount_valuation = self._calculate_dividend_discount_valuation(data)
        regulated_roe_valuation = self._calculate_regulated_roe_valuation(data)
        yield_comparison_valuation = self._calculate_yield_comparison_valuation(data)

        # Weight valuations based on utility characteristics
        valuations = []
        weights = []
        valuation_details = {}

        if dividend_discount_valuation:
            valuations.append(dividend_discount_valuation)
            weights.append(0.5)  # 50% weight to dividend model
            valuation_details['dividend_discount'] = dividend_discount_valuation

        if regulated_roe_valuation:
            valuations.append(regulated_roe_valuation)
            weights.append(0.3)  # 30% weight to ROE model
            valuation_details['regulated_roe'] = regulated_roe_valuation

        if yield_comparison_valuation:
            valuations.append(yield_comparison_valuation)
            weights.append(0.2)  # 20% weight to yield comparison
            valuation_details['yield_comparison'] = yield_comparison_valuation

        if not valuations:
            raise InsufficientDataError(ticker, ['valuation_methods'])

        # Calculate weighted average
        if len(weights) != len(valuations):
            weights = [1.0 / len(valuations)] * len(valuations)

        fair_value = sum(v * w for v, w in zip(valuations, weights)) / sum(weights)

        # Calculate margin of safety
        margin_of_safety = None
        if current_price and current_price > 0:
            margin_of_safety = (fair_value - current_price) / current_price

        # Determine confidence
        confidence = self._determine_confidence(len(valuations), dividend_yield, payout_ratio)

        result = ValuationResult(
            ticker=ticker,
            model=self.name,
            fair_value=fair_value,
            current_price=current_price,
            margin_of_safety=margin_of_safety,
            confidence=confidence
        )

        result.inputs = {
            'current_price': current_price,
            'dividend_yield': dividend_yield,
            'dividend_rate': dividend_rate,
            'payout_ratio': payout_ratio,
            'book_value': book_value,
            'roe': roe,
            'beta': beta,
        }

        result.outputs = {
            'individual_valuations': valuation_details,
            'valuation_methods_used': len(valuations),
            'average_fair_value': fair_value,
            'dividend_sustainability_score': self._calculate_dividend_sustainability_score(data),
        }

        return result

    def _calculate_dividend_discount_valuation(self, data: Dict[str, Any]) -> Optional[float]:
        """Calculate valuation using dividend discount model with utility assumptions."""
        try:
            info = data.get('info', {})

            dividend_rate = self._safe_float(info.get('dividendRate'))
            if not dividend_rate or dividend_rate <= 0:
                return None

            # Utility dividend growth is typically modest and stable
            dividend_growth = 0.025  # 2.5% annual growth assumption

            # Required return for utilities (lower than general market due to stability)
            risk_free_rate = VALUATION_DEFAULTS.RISK_FREE_RATE
            beta = self._safe_float(info.get('beta')) or 0.6  # Default low beta
            market_premium = VALUATION_DEFAULTS.EQUITY_RISK_PREMIUM

            required_return = risk_free_rate + beta * market_premium

            if required_return <= dividend_growth:
                return None

            # Gordon growth model: V = D1 / (r - g)
            next_year_dividend = dividend_rate * (1 + dividend_growth)
            return next_year_dividend / (required_return - dividend_growth)

        except Exception as e:
            logger.debug(f"Dividend discount valuation failed: {e}")
            return None

    def _calculate_regulated_roe_valuation(self, data: Dict[str, Any]) -> Optional[float]:
        """Calculate valuation based on regulated return on equity."""
        try:
            info = data.get('info', {})

            book_value = self._safe_float(info.get('bookValue'))
            roe = self._safe_float(info.get('returnOnEquity'))

            if not book_value or not roe or book_value <= 0:
                return None

            # Utilities typically earn regulated ROE of 9-12%
            # If current ROE is within this range, assume sustainable
            if 0.08 <= roe <= 0.13:  # 8-13% ROE range
                # Fair P/B ratio for utilities with sustainable ROE
                cost_of_equity = VALUATION_DEFAULTS.RISK_FREE_RATE + 0.04  # Risk-free + 4%

                if roe > cost_of_equity:
                    pb_ratio = roe / cost_of_equity
                    pb_ratio = min(pb_ratio, 1.8)  # Cap at 1.8x book
                else:
                    pb_ratio = 1.0  # Trade at book if ROE = cost of equity

                return book_value * pb_ratio

            return None

        except Exception as e:
            logger.debug(f"Regulated ROE valuation failed: {e}")
            return None

    def _calculate_yield_comparison_valuation(self, data: Dict[str, Any]) -> Optional[float]:
        """Calculate valuation based on yield comparison to bonds."""
        try:
            info = data.get('info', {})

            dividend_rate = self._safe_float(info.get('dividendRate'))
            self._safe_float(info.get('dividend_yield'))
            current_price = self._safe_float(info.get('currentPrice'))

            if not dividend_rate or not current_price or dividend_rate <= 0 or current_price <= 0:
                return None

            # Calculate current yield
            current_yield = dividend_rate / current_price

            # Target yield based on bond yields plus premium
            risk_free_rate = VALUATION_DEFAULTS.RISK_FREE_RATE
            target_yield = risk_free_rate + 0.02  # Treasury + 2% premium for equity risk

            # If utility yields significantly more than target, it may be undervalued
            if current_yield > target_yield * 1.2:  # 20% higher yield
                # Price for target yield
                return dividend_rate / target_yield

            # If yield is reasonable, current price is fair
            return current_price

        except Exception as e:
            logger.debug(f"Yield comparison valuation failed: {e}")
            return None

    def _calculate_dividend_sustainability_score(self, data: Dict[str, Any]) -> float:
        """Calculate a score (0-100) for dividend sustainability."""
        try:
            info = data.get('info', {})

            score = 50  # Base score

            # Payout ratio check
            payout_ratio = self._safe_float(info.get('payoutRatio'))
            if payout_ratio:
                if payout_ratio <= 0.7:  # ≤70% payout
                    score += 20
                elif payout_ratio <= 0.8:  # ≤80% payout
                    score += 10
                elif payout_ratio >= 1.0:  # ≥100% payout (unsustainable)
                    score -= 20

            # ROE check
            roe = self._safe_float(info.get('returnOnEquity'))
            if roe:
                if roe >= 0.10:  # ≥10% ROE
                    score += 15
                elif roe >= 0.08:  # ≥8% ROE
                    score += 10
                elif roe <= 0.05:  # ≤5% ROE
                    score -= 15

            # Debt level check (utilities are capital intensive)
            debt_to_equity = self._safe_float(info.get('debtToEquity'))
            if debt_to_equity:
                debt_ratio = debt_to_equity / 100  # Convert percentage
                if debt_ratio <= 0.6:  # ≤60% debt ratio
                    score += 15
                elif debt_ratio <= 0.8:  # ≤80% debt ratio
                    score += 5
                elif debt_ratio >= 1.2:  # ≥120% debt ratio
                    score -= 15

            return max(0, min(100, score))  # Clamp between 0 and 100

        except Exception:
            return 50  # Default neutral score

    def _determine_confidence(self, num_methods: int, dividend_yield: Optional[float],
                            payout_ratio: Optional[float]) -> str:
        """Determine confidence based on utility-specific factors."""
        if num_methods >= 3:
            base_confidence = 'high'
        elif num_methods >= 2:
            base_confidence = 'medium'
        else:
            base_confidence = 'low'

        # Utilities with sustainable dividends are more predictable
        if dividend_yield and payout_ratio:
            if (dividend_yield > 0.04 and  # >4% dividend yield
                0.5 <= payout_ratio <= 0.8):  # Sustainable payout ratio
                if base_confidence == 'medium':
                    return 'high'
                elif base_confidence == 'low':
                    return 'medium'

        return base_confidence
