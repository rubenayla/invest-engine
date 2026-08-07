"""
Simple Ratios Model implementation under the unified structure.

This model provides quick valuations based on market multiples and ratios,
useful for initial screening and cross-validation of other models.
"""

from typing import Any, Dict, List, Optional

from ..config.constants import VALUATION_DEFAULTS
from ..exceptions import InsufficientDataError
from .base import ValuationModel, ValuationResult


class SimpleRatiosModel(ValuationModel):
    """
    Simple ratios-based valuation model using market multiples.

    Uses P/E, P/B, P/S ratios for quick valuation. Best for mature companies
    with stable earnings and established market comparables.

    Data Requirements
    -----------------
    Required fields:
        - currentPrice: Current stock price

    Required (at least one):
        - trailingEps: Trailing twelve months earnings per share
        - bookValue: Book value per share
        - revenuePerShare: Revenue per share

    Optional fields (improve accuracy):
        - totalCash: Total cash on balance sheet
        - sharesOutstanding: Shares outstanding
        - sector: Company sector for industry-specific multiples
        - beta: Stock beta for risk adjustment
    """

    def __init__(self):
        super().__init__('simple_ratios')

        # Default industry multiples (would be better to fetch dynamically)
        self.default_multiples = {
            'pe_ratio': VALUATION_DEFAULTS.DEFAULT_PE_MULTIPLE,
            'pb_ratio': VALUATION_DEFAULTS.DEFAULT_PB_MULTIPLE,
            'ps_ratio': VALUATION_DEFAULTS.DEFAULT_PS_MULTIPLE,
            'pcf_ratio': VALUATION_DEFAULTS.DEFAULT_PCF_MULTIPLE,
        }

    def is_suitable(self, ticker: str, data: Dict[str, Any]) -> bool:
        """Ratios model is suitable for most companies with basic financial metrics."""
        try:
            info = data.get('info', {})

            # Need at least basic price and financial data
            current_price = self._safe_float(info.get('currentPrice'))
            if not current_price or current_price <= 0:
                return False

            # Need at least one valuation metric
            metrics_available = [
                self._safe_float(info.get('trailingEps')),
                self._safe_float(info.get('bookValue')),
                self._safe_float(info.get('priceToSalesTrailing12Months')),
            ]

            return any(metric and metric > 0 for metric in metrics_available)

        except Exception:
            return False

    def _validate_inputs(self, ticker: str, data: Dict[str, Any]) -> None:
        """Validate required inputs for ratios model."""
        info = data.get('info', {})

        if not info:
            raise InsufficientDataError(ticker, ['company_info'])

        # Check for current price
        current_price = self._safe_float(info.get('currentPrice'))
        if not current_price or current_price <= 0:
            raise InsufficientDataError(ticker, ['current_price'])

        # Check that we have at least one useful metric
        eps = self._safe_float(info.get('trailingEps'))
        book_value = self._safe_float(info.get('bookValue'))
        revenue_per_share = self._safe_float(info.get('revenuePerShare'))

        if not any([eps and eps > 0, book_value and book_value > 0, revenue_per_share and revenue_per_share > 0]):
            raise InsufficientDataError(ticker, ['valid_financial_metrics'])

    def _calculate_valuation(self, ticker: str, data: Dict[str, Any]) -> ValuationResult:
        """Calculate valuation using multiple ratios and take average."""
        info = data.get('info', {})

        # Extract current metrics
        current_price = self._safe_float(info.get('currentPrice'))
        eps = self._safe_float(info.get('trailingEps'))
        book_value = self._safe_float(info.get('bookValue'))
        revenue_per_share = self._safe_float(info.get('revenuePerShare'))
        cash_per_share = self._calculate_cash_per_share(data)

        # Calculate fair values using different multiples
        valuations = []
        valuation_details = {}

        # P/E based valuation
        if eps and eps > 0:
            pe_multiple = self._get_industry_pe_multiple(info)
            pe_value = eps * pe_multiple
            valuations.append(pe_value)
            valuation_details['pe_valuation'] = {
                'eps': eps,
                'multiple': pe_multiple,
                'fair_value': pe_value
            }

        # P/B based valuation
        if book_value and book_value > 0:
            pb_multiple = self._get_industry_pb_multiple(info)
            pb_value = book_value * pb_multiple
            valuations.append(pb_value)
            valuation_details['pb_valuation'] = {
                'book_value': book_value,
                'multiple': pb_multiple,
                'fair_value': pb_value
            }

        # P/S based valuation
        if revenue_per_share and revenue_per_share > 0:
            ps_multiple = self._get_industry_ps_multiple(info)
            ps_value = revenue_per_share * ps_multiple
            valuations.append(ps_value)
            valuation_details['ps_valuation'] = {
                'revenue_per_share': revenue_per_share,
                'multiple': ps_multiple,
                'fair_value': ps_value
            }

        # P/CF based valuation (if cash flow available)
        if cash_per_share and cash_per_share > 0:
            pcf_multiple = self._get_industry_pcf_multiple(info)
            pcf_value = cash_per_share * pcf_multiple
            valuations.append(pcf_value)
            valuation_details['pcf_valuation'] = {
                'cash_per_share': cash_per_share,
                'multiple': pcf_multiple,
                'fair_value': pcf_value
            }

        if not valuations:
            raise InsufficientDataError(ticker, ['ratio_based_valuations'])

        # Calculate weighted average (equal weights for simplicity)
        fair_value_per_share = sum(valuations) / len(valuations)

        # Calculate margin of safety
        margin_of_safety = None
        if current_price and current_price > 0:
            margin_of_safety = (fair_value_per_share - current_price) / current_price

        # Determine confidence based on number of metrics available
        confidence = self._determine_confidence(len(valuations))

        # Create result
        result = ValuationResult(
            ticker=ticker,
            model=self.name,
            fair_value=fair_value_per_share,
            current_price=current_price,
            margin_of_safety=margin_of_safety,
            confidence=confidence
        )

        # Add detailed inputs/outputs
        result.inputs = {
            'current_price': current_price,
            'eps': eps,
            'book_value': book_value,
            'revenue_per_share': revenue_per_share,
            'cash_per_share': cash_per_share,
        }

        result.outputs = {
            'valuations_calculated': len(valuations),
            'individual_valuations': valuation_details,
            'average_fair_value': fair_value_per_share,
            'valuation_range': {
                'min': min(valuations),
                'max': max(valuations),
                'std_dev': self._calculate_std_dev(valuations)
            }
        }

        return result

    def _calculate_cash_per_share(self, data: Dict[str, Any]) -> Optional[float]:
        """Calculate cash flow per share if data is available."""
        info = data.get('info', {})

        # Try to get operating cash flow per share
        operating_cf_per_share = self._safe_float(info.get('operatingCashflow'))
        shares_outstanding = self._safe_float(info.get('sharesOutstanding'))

        if operating_cf_per_share and shares_outstanding and shares_outstanding > 0:
            return operating_cf_per_share / shares_outstanding

        # Try alternative cash flow metrics
        free_cf_per_share = self._safe_float(info.get('freeCashflow'))
        if free_cf_per_share and shares_outstanding and shares_outstanding > 0:
            return free_cf_per_share / shares_outstanding

        return None

    def _get_industry_pe_multiple(self, info: Dict[str, Any]) -> float:
        """Get appropriate P/E multiple based on industry/growth."""
        # Use industry/sector to adjust multiple (simplified)
        sector = info.get('sector', '')

        base_pe = self.default_multiples['pe_ratio']

        # Sector-based adjustments
        if 'Technology' in sector:
            base_pe *= 1.3  # Higher multiples for tech
        elif 'Utilities' in sector:
            base_pe *= 0.8  # Lower multiples for utilities
        elif 'Financial' in sector:
            base_pe *= 0.9  # Lower multiples for banks

        # Growth adjustment
        growth_rate = self._safe_float(info.get('earningsGrowth'))
        if growth_rate and growth_rate > 0.1:  # 10%+ growth
            base_pe *= min(1.5, 1 + growth_rate)  # Cap at 1.5x
        elif growth_rate and growth_rate < 0:  # Negative growth
            base_pe *= 0.7

        return max(base_pe, 8)  # Minimum reasonable P/E

    def _get_industry_pb_multiple(self, info: Dict[str, Any]) -> float:
        """Get appropriate P/B multiple."""
        sector = info.get('sector', '')

        base_pb = self.default_multiples['pb_ratio']

        if 'Financial' in sector:
            base_pb = 1.0  # Banks typically trade near book value
        elif 'Technology' in sector:
            base_pb *= 2.0  # Higher P/B for asset-light tech
        elif 'Real Estate' in sector:
            base_pb *= 1.2  # Modest premium for REITs

        return base_pb

    def _get_industry_ps_multiple(self, info: Dict[str, Any]) -> float:
        """Get appropriate P/S multiple."""
        sector = info.get('sector', '')

        base_ps = self.default_multiples['ps_ratio']

        if 'Technology' in sector:
            base_ps *= 3.0  # Higher revenue multiples for tech
        elif 'Retail' in sector:
            base_ps *= 0.5  # Lower margins in retail
        elif 'Utilities' in sector:
            base_ps *= 1.5  # Stable revenue streams

        return base_ps

    def _get_industry_pcf_multiple(self, info: Dict[str, Any]) -> float:
        """Get appropriate P/CF multiple."""
        return self.default_multiples['pcf_ratio']

    def _determine_confidence(self, num_metrics: int) -> str:
        """Determine confidence level based on available metrics."""
        if num_metrics >= 3:
            return 'high'
        elif num_metrics >= 2:
            return 'medium'
        else:
            return 'low'

    def _calculate_std_dev(self, values: List[float]) -> float:
        """Calculate standard deviation of valuations."""
        if len(values) < 2:
            return 0.0

        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
        return variance ** 0.5
