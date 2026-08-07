"""
Technology Sector Valuation Model

Technology companies require specialized approaches because they:
- Have high growth rates and scaling potential
- Often trade at high revenue multiples
- May lack traditional profitability metrics (especially growth-stage)
- Have intangible assets and R&D investments
- Show network effects and platform dynamics
"""

import logging
from typing import Any, Dict, Optional

from ...exceptions import InsufficientDataError
from ..base import ValuationModel, ValuationResult

logger = logging.getLogger(__name__)


class TechModel(ValuationModel):
    """
    Specialized valuation model for technology companies.

    This model emphasizes:
    - Revenue growth and scalability
    - Forward-looking multiples
    - Platform value and network effects
    - R&D investment efficiency
    - Market opportunity sizing
    """

    def __init__(self):
        super().__init__('tech')

    def is_suitable(self, ticker: str, data: Dict[str, Any]) -> bool:
        """Check if company is a tech company suitable for this model."""
        try:
            info = data.get('info', {})

            sector = info.get('sector', '').lower()
            industry = info.get('industry', '').lower()

            # Technology sector indicators
            tech_keywords = [
                'technology', 'software', 'internet', 'semiconductor', 'hardware',
                'computer', 'electronic', 'telecommunications', 'communication services',
                'social media', 'cloud', 'cybersecurity', 'artificial intelligence'
            ]

            is_tech = any(keyword in sector or keyword in industry for keyword in tech_keywords)

            if not is_tech:
                return False

            # Tech companies often have high growth rates
            revenue_growth = info.get('revenueGrowth')
            earnings_growth = info.get('earningsGrowth')

            if revenue_growth and revenue_growth > 0.15:  # >15% revenue growth
                return True

            if earnings_growth and earnings_growth > 0.20:  # >20% earnings growth
                return True

            # Check for high revenue multiples (typical for tech)
            ps_ratio = info.get('priceToSalesTrailing12Months')
            if ps_ratio and ps_ratio > 5.0:  # High P/S ratio
                return True

            return is_tech  # Default to sector classification

        except Exception:
            return False

    def _validate_inputs(self, ticker: str, data: Dict[str, Any]) -> None:
        """Validate tech-specific input data."""
        info = data.get('info', {})

        if not info:
            raise InsufficientDataError(ticker, ['info'])

        # Tech stocks need revenue data
        revenue_per_share = info.get('revenuePerShare')
        if not revenue_per_share or revenue_per_share <= 0:
            # Try alternative revenue metric
            total_revenue = info.get('totalRevenue')
            shares_outstanding = info.get('sharesOutstanding')
            if not (total_revenue and shares_outstanding and total_revenue > 0 and shares_outstanding > 0):
                raise InsufficientDataError(ticker, ['revenuePerShare', 'totalRevenue', 'sharesOutstanding'])

    def _calculate_valuation(self, ticker: str, data: Dict[str, Any]) -> ValuationResult:
        """Calculate tech company valuation using growth-focused approaches."""
        info = data.get('info', {})

        # Extract tech-relevant metrics
        current_price = self._safe_float(info.get('currentPrice'))
        revenue_per_share = self._safe_float(info.get('revenuePerShare'))
        revenue_growth = self._safe_float(info.get('revenueGrowth'))
        earnings_growth = self._safe_float(info.get('earningsGrowth'))
        forward_pe = self._safe_float(info.get('forwardPE'))
        ps_ratio = self._safe_float(info.get('priceToSalesTrailing12Months'))

        # Calculate different tech-focused valuations
        growth_adjusted_valuation = self._calculate_growth_adjusted_valuation(data)
        revenue_multiple_valuation = self._calculate_revenue_multiple_valuation(data)
        forward_earnings_valuation = self._calculate_forward_earnings_valuation(data)
        dcf_growth_valuation = self._calculate_tech_dcf_valuation(data)

        # Weight valuations based on company maturity and profitability
        valuations = []
        weights = []
        valuation_details = {}

        if growth_adjusted_valuation:
            valuations.append(growth_adjusted_valuation)
            weights.append(0.3)  # 30% weight to growth-adjusted
            valuation_details['growth_adjusted'] = growth_adjusted_valuation

        if revenue_multiple_valuation:
            valuations.append(revenue_multiple_valuation)
            weights.append(0.25)  # 25% weight to revenue multiple
            valuation_details['revenue_multiple'] = revenue_multiple_valuation

        if forward_earnings_valuation:
            valuations.append(forward_earnings_valuation)
            weights.append(0.25)  # 25% weight to forward earnings
            valuation_details['forward_earnings'] = forward_earnings_valuation

        if dcf_growth_valuation:
            valuations.append(dcf_growth_valuation)
            weights.append(0.2)  # 20% weight to DCF
            valuation_details['dcf_growth'] = dcf_growth_valuation

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
        confidence = self._determine_confidence(len(valuations), revenue_growth, earnings_growth)

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
            'revenue_per_share': revenue_per_share,
            'revenue_growth': revenue_growth,
            'earnings_growth': earnings_growth,
            'forward_pe': forward_pe,
            'ps_ratio': ps_ratio,
        }

        result.outputs = {
            'individual_valuations': valuation_details,
            'valuation_methods_used': len(valuations),
            'average_fair_value': fair_value,
        }

        return result

    def _calculate_growth_adjusted_valuation(self, data: Dict[str, Any]) -> Optional[float]:
        """Calculate PEG-style growth-adjusted valuation."""
        try:
            info = data.get('info', {})

            forward_pe = self._safe_float(info.get('forwardPE'))
            earnings_growth = self._safe_float(info.get('earningsGrowth'))
            forward_eps = self._safe_float(info.get('forwardEps'))

            if not forward_pe or not earnings_growth or not forward_eps:
                return None

            if earnings_growth <= 0:
                return None

            # PEG ratio: P/E / Growth Rate
            forward_pe / (earnings_growth * 100)  # Convert to percentage

            # Adjust target PEG based on tech growth quality
            if earnings_growth > 0.50:  # >50% growth
                target_peg = 2.0  # Premium for hypergrowth
            elif earnings_growth > 0.25:  # >25% growth
                target_peg = 1.5  # Moderate premium
            else:
                target_peg = 1.0  # Fair value PEG

            target_pe = target_peg * (earnings_growth * 100)
            return forward_eps * target_pe

        except Exception as e:
            logger.debug(f"Growth-adjusted valuation failed: {e}")
            return None

    def _calculate_revenue_multiple_valuation(self, data: Dict[str, Any]) -> Optional[float]:
        """Calculate valuation based on revenue multiples."""
        try:
            info = data.get('info', {})

            revenue_per_share = self._safe_float(info.get('revenuePerShare'))
            revenue_growth = self._safe_float(info.get('revenueGrowth'))

            if not revenue_per_share or revenue_per_share <= 0:
                return None

            # Base revenue multiple for tech companies
            base_multiple = 6.0

            # Adjust based on growth rate
            if revenue_growth:
                if revenue_growth > 0.40:  # >40% growth
                    revenue_multiple = base_multiple * 3.0
                elif revenue_growth > 0.25:  # >25% growth
                    revenue_multiple = base_multiple * 2.0
                elif revenue_growth > 0.15:  # >15% growth
                    revenue_multiple = base_multiple * 1.5
                elif revenue_growth > 0.05:  # >5% growth
                    revenue_multiple = base_multiple * 1.0
                else:  # Low/negative growth
                    revenue_multiple = base_multiple * 0.5
            else:
                revenue_multiple = base_multiple

            # Adjust for profitability if available
            gross_margin = info.get('grossMargins')
            if gross_margin:
                if gross_margin > 0.7:  # >70% gross margin
                    revenue_multiple *= 1.3
                elif gross_margin > 0.5:  # >50% gross margin
                    revenue_multiple *= 1.1
                elif gross_margin < 0.3:  # <30% gross margin
                    revenue_multiple *= 0.8

            return revenue_per_share * revenue_multiple

        except Exception as e:
            logger.debug(f"Revenue multiple valuation failed: {e}")
            return None

    def _calculate_forward_earnings_valuation(self, data: Dict[str, Any]) -> Optional[float]:
        """Calculate valuation based on forward earnings."""
        try:
            info = data.get('info', {})

            forward_eps = self._safe_float(info.get('forwardEps'))
            if not forward_eps or forward_eps <= 0:
                return None

            # Tech-appropriate P/E multiple
            earnings_growth = self._safe_float(info.get('earningsGrowth'))

            if earnings_growth and earnings_growth > 0.30:  # >30% earnings growth
                pe_multiple = 35.0
            elif earnings_growth and earnings_growth > 0.20:  # >20% growth
                pe_multiple = 25.0
            elif earnings_growth and earnings_growth > 0.10:  # >10% growth
                pe_multiple = 20.0
            else:
                pe_multiple = 15.0  # Mature tech multiple

            return forward_eps * pe_multiple

        except Exception as e:
            logger.debug(f"Forward earnings valuation failed: {e}")
            return None

    def _calculate_tech_dcf_valuation(self, data: Dict[str, Any]) -> Optional[float]:
        """Calculate simplified DCF with high growth assumptions."""
        try:
            info = data.get('info', {})

            # Get cash flow data
            free_cashflow = self._safe_float(info.get('freeCashflow'))
            if not free_cashflow or free_cashflow <= 0:
                # Estimate from revenue and margins
                total_revenue = self._safe_float(info.get('totalRevenue'))
                if not total_revenue:
                    return None

                # Assume 20% eventual free cash flow margin for mature tech
                estimated_fcf = total_revenue * 0.20
                if estimated_fcf <= 0:
                    return None
                free_cashflow = estimated_fcf

            shares_outstanding = self._safe_float(info.get('sharesOutstanding'))
            if not shares_outstanding or shares_outstanding <= 0:
                return None

            fcf_per_share = free_cashflow / shares_outstanding

            # High-growth DCF parameters
            high_growth_rate = 0.25  # 25% growth for first 5 years
            moderate_growth_rate = 0.10  # 10% growth for next 5 years
            terminal_growth_rate = 0.03  # 3% perpetual growth
            discount_rate = 0.12  # 12% discount rate for tech

            # Project cash flows
            years_high_growth = 5
            years_moderate_growth = 5

            # High growth phase
            pv_high_growth = 0
            current_fcf = fcf_per_share
            for year in range(1, years_high_growth + 1):
                current_fcf *= (1 + high_growth_rate)
                pv_high_growth += current_fcf / (1 + discount_rate) ** year

            # Moderate growth phase
            pv_moderate_growth = 0
            for year in range(years_high_growth + 1, years_high_growth + years_moderate_growth + 1):
                current_fcf *= (1 + moderate_growth_rate)
                pv_moderate_growth += current_fcf / (1 + discount_rate) ** year

            # Terminal value
            terminal_fcf = current_fcf * (1 + terminal_growth_rate)
            terminal_value = terminal_fcf / (discount_rate - terminal_growth_rate)
            pv_terminal = terminal_value / (1 + discount_rate) ** (years_high_growth + years_moderate_growth)

            return pv_high_growth + pv_moderate_growth + pv_terminal

        except Exception as e:
            logger.debug(f"Tech DCF valuation failed: {e}")
            return None

    def _determine_confidence(self, num_methods: int, revenue_growth: Optional[float],
                            earnings_growth: Optional[float]) -> str:
        """Determine confidence based on growth metrics and data availability."""
        if num_methods >= 3:
            base_confidence = 'high'
        elif num_methods >= 2:
            base_confidence = 'medium'
        else:
            base_confidence = 'low'

        # Adjust for growth visibility
        if revenue_growth and earnings_growth:
            if revenue_growth > 0.20 and earnings_growth > 0.25:  # Strong consistent growth
                if base_confidence == 'medium':
                    return 'high'
            elif revenue_growth < 0.05 or earnings_growth < 0:  # Weak growth
                if base_confidence == 'high':
                    return 'medium'
                elif base_confidence == 'medium':
                    return 'low'

        return base_confidence
