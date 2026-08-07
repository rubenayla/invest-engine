"""
REIT (Real Estate Investment Trust) Valuation Model

REITs require specialized valuation approaches because they:
- Distribute most income as dividends (90%+ payout requirement)
- Focus on Funds From Operations (FFO) rather than net income
- Have different depreciation and capital expenditure patterns
- Are valued based on dividend yield and NAV (Net Asset Value)
"""

import logging
from typing import Any, Dict, Optional

from ...config.constants import VALUATION_DEFAULTS
from ...exceptions import InsufficientDataError
from ..base import ValuationModel, ValuationResult

logger = logging.getLogger(__name__)


class REITModel(ValuationModel):
    """
    Specialized valuation model for Real Estate Investment Trusts (REITs).

    This model uses REIT-specific metrics like:
    - Funds From Operations (FFO)
    - Adjusted Funds From Operations (AFFO)
    - Net Asset Value (NAV)
    - Dividend yield analysis
    """

    def __init__(self):
        super().__init__('reit')

    def is_suitable(self, ticker: str, data: Dict[str, Any]) -> bool:
        """Check if company is a REIT suitable for this model."""
        try:
            info = data.get('info', {})

            # Check if it's classified as a REIT
            sector = info.get('sector', '').lower()
            industry = info.get('industry', '').lower()

            # Look for REIT indicators
            is_reit = (
                'reit' in industry or
                'real estate' in sector or
                'real estate investment trust' in (info.get('longBusinessSummary', '').lower()) or
                'reit' in (info.get('longName', '').lower())
            )

            if not is_reit:
                return False

            # REITs should have high dividend yields and payout ratios
            dividend_yield = info.get('dividendYield')
            payout_ratio = info.get('payoutRatio')

            if dividend_yield and dividend_yield > 0.03:  # >3% dividend yield
                return True

            if payout_ratio and payout_ratio > 0.6:  # >60% payout ratio
                return True

            return True  # If classified as REIT, assume suitable

        except Exception:
            return False

    def _validate_inputs(self, ticker: str, data: Dict[str, Any]) -> None:
        """Validate REIT-specific input data."""
        info = data.get('info', {})

        if not info:
            raise InsufficientDataError(ticker, ['info'])

        # Check for dividend data
        dividend_yield = info.get('dividendYield')
        if not dividend_yield or dividend_yield <= 0:
            raise InsufficientDataError(ticker, ['dividendYield'])

    def _calculate_valuation(self, ticker: str, data: Dict[str, Any]) -> ValuationResult:
        """Calculate REIT valuation using multiple approaches."""
        info = data.get('info', {})

        # Extract REIT-specific metrics
        current_price = self._safe_float(info.get('currentPrice'))
        dividend_yield = self._safe_float(info.get('dividendYield'))
        dividend_rate = self._safe_float(info.get('dividendRate'))
        payout_ratio = self._safe_float(info.get('payoutRatio'))
        shares_outstanding = self._get_shares_outstanding(data, ticker)

        # Calculate FFO-based valuation
        ffo_valuation = self._calculate_ffo_valuation(data, ticker)

        # Calculate dividend discount model valuation
        ddm_valuation = self._calculate_dividend_discount_valuation(data)

        # Calculate NAV-based valuation (simplified)
        nav_valuation = self._calculate_nav_valuation(data, ticker)

        # Weighted average of different approaches
        valuations = []
        weights = []
        valuation_details = {}

        if ffo_valuation:
            valuations.append(ffo_valuation)
            weights.append(0.4)  # 40% weight to FFO
            valuation_details['ffo_based'] = ffo_valuation

        if ddm_valuation:
            valuations.append(ddm_valuation)
            weights.append(0.35)  # 35% weight to dividend model
            valuation_details['dividend_based'] = ddm_valuation

        if nav_valuation:
            valuations.append(nav_valuation)
            weights.append(0.25)  # 25% weight to NAV
            valuation_details['nav_based'] = nav_valuation

        if not valuations:
            raise InsufficientDataError(ticker, ['valuation_methods'])

        # Calculate weighted average
        if len(weights) != len(valuations):
            weights = [1.0 / len(valuations)] * len(valuations)  # Equal weights

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
            'shares_outstanding': shares_outstanding,
        }

        result.outputs = {
            'individual_valuations': valuation_details,
            'valuation_methods_used': len(valuations),
            'average_fair_value': fair_value,
        }

        return result

    def _calculate_ffo_valuation(self, data: Dict[str, Any], ticker: str = "UNKNOWN") -> Optional[float]:
        """Calculate valuation based on Funds From Operations (FFO)."""
        try:
            # Try to estimate FFO from available data
            # FFO = Net Income + Depreciation - Gains on Sales of Property

            financials = data.get('income')
            if financials is None or financials.empty:
                return None

            # Get most recent net income
            net_income = self._get_most_recent_value(
                financials.loc['Net Income'] if 'Net Income' in financials.index else None
            )

            # Estimate depreciation (simplified - in practice would need cash flow statement)
            # For REITs, depreciation is typically significant
            estimated_depreciation = abs(net_income) * 0.3 if net_income else 0  # Rough estimate

            # Simplified FFO calculation
            estimated_ffo = (net_income or 0) + estimated_depreciation

            if estimated_ffo <= 0:
                return None

            # Apply REIT-specific FFO multiple (typically 12-20x)
            ffo_multiple = 15.0  # Conservative middle ground
            shares_outstanding = self._get_shares_outstanding(data, ticker)

            ffo_per_share = estimated_ffo / shares_outstanding
            return ffo_per_share * ffo_multiple

        except Exception as e:
            logger.debug(f"FFO valuation failed: {e}")
            return None

    def _calculate_dividend_discount_valuation(self, data: Dict[str, Any]) -> Optional[float]:
        """Calculate valuation using dividend discount model."""
        try:
            info = data.get('info', {})

            dividend_rate = self._safe_float(info.get('dividendRate'))
            if not dividend_rate or dividend_rate <= 0:
                return None

            # Estimate dividend growth rate (conservative for REITs)
            dividend_growth = 0.02  # 2% annual growth assumption

            # Required rate of return for REITs (typically higher than bonds due to risk)
            required_return = VALUATION_DEFAULTS.RISK_FREE_RATE + 0.04  # Risk-free + 4% premium

            if required_return <= dividend_growth:
                return None  # Avoid negative/infinite valuations

            # Dividend discount model: V = D1 / (r - g)
            next_year_dividend = dividend_rate * (1 + dividend_growth)
            return next_year_dividend / (required_return - dividend_growth)

        except Exception as e:
            logger.debug(f"Dividend discount valuation failed: {e}")
            return None

    def _calculate_nav_valuation(self, data: Dict[str, Any], ticker: str = "UNKNOWN") -> Optional[float]:
        """Calculate Net Asset Value based valuation."""
        try:
            balance_sheet = data.get('balance_sheet')
            if balance_sheet is None or balance_sheet.empty:
                return None

            # Get book value (simplified NAV proxy)
            book_value = self._get_most_recent_value(
                balance_sheet.loc['Total Stockholder Equity'] if 'Total Stockholder Equity' in balance_sheet.index else None
            )

            if not book_value or book_value <= 0:
                return None

            shares_outstanding = self._get_shares_outstanding(data, ticker)
            book_value_per_share = book_value / shares_outstanding

            # REITs often trade at premium/discount to book value
            # Apply a conservative premium for quality REITs
            nav_multiple = 1.1  # 10% premium to book value

            return book_value_per_share * nav_multiple

        except Exception as e:
            logger.debug(f"NAV valuation failed: {e}")
            return None

    def _get_shares_outstanding(self, data: Dict[str, Any], ticker: str = "UNKNOWN") -> float:
        """Get shares outstanding."""
        info = data.get('info', {})
        shares = self._safe_float(info.get('sharesOutstanding'))

        if not shares or shares <= 0:
            shares = self._safe_float(info.get('impliedSharesOutstanding'))

        if not shares or shares <= 0:
            raise InsufficientDataError(ticker or 'UNKNOWN', ['sharesOutstanding'])

        return shares

    def _determine_confidence(self, num_methods: int, dividend_yield: Optional[float],
                            payout_ratio: Optional[float]) -> str:
        """Determine confidence level based on data quality and consistency."""
        if num_methods >= 3:
            base_confidence = 'high'
        elif num_methods >= 2:
            base_confidence = 'medium'
        else:
            base_confidence = 'low'

        # Adjust based on REIT-specific factors
        if dividend_yield and dividend_yield > 0.05:  # >5% yield indicates mature REIT
            if base_confidence == 'medium':
                return 'high'

        if payout_ratio and 0.7 <= payout_ratio <= 0.95:  # Healthy payout ratio
            if base_confidence == 'low':
                return 'medium'

        return base_confidence
