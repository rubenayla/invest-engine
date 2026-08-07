"""
Growth-Adjusted DCF Model implementation.

This model separates maintenance CapEx from growth CapEx, treating growth investments
as value-creating assets rather than simple costs. This approach is particularly
valuable for reinvestment-heavy companies like Amazon, Tesla, and Netflix.

Key Innovation:
- Normalized FCF = Operating CF - Maintenance CapEx only
- Growth CapEx is valued separately based on expected ROIC
- Prevents traditional DCF bias against growth companies
"""

from typing import Any, Dict, Optional

import numpy as np

from ..config.constants import VALUATION_DEFAULTS
from ..exceptions import InsufficientDataError, ModelNotSuitableError
from .base import ValuationResult
from .dcf_model import DCFModel


class GrowthAdjustedDCFModel(DCFModel):
    """Growth-Adjusted DCF that separates maintenance from growth CapEx."""

    def __init__(self):
        super().__init__()
        self.name = 'growth_dcf'
        self.projection_years = VALUATION_DEFAULTS.DCF_PROJECTION_YEARS

        # Industry maintenance CapEx benchmarks (as % of revenue)
        self.industry_maintenance_rates = {
            'utilities': 0.035,          # 3.5% - infrastructure maintenance
            'energy': 0.040,             # 4.0% - pipeline/refinery maintenance
            'industrials': 0.025,        # 2.5% - equipment replacement
            'materials': 0.030,          # 3.0% - mining/processing equipment
            'consumer discretionary': 0.020,  # 2.0% - retail/automotive
            'consumer staples': 0.015,   # 1.5% - food/beverage facilities
            'health care': 0.020,        # 2.0% - pharmaceutical/medical
            'financials': 0.010,         # 1.0% - offices/IT infrastructure
            'information technology': 0.015,  # 1.5% - servers/offices
            'communication services': 0.020,  # 2.0% - network infrastructure
            'real estate': 0.025,        # 2.5% - property maintenance
            'default': 0.020            # 2.0% - conservative default
        }

    def is_suitable(self, ticker: str, data: Dict[str, Any]) -> bool:
        """Growth-Adjusted DCF is suitable for companies with significant CapEx and positive ROIC."""
        try:
            # Must have basic DCF requirements
            if not super().is_suitable(ticker, data):
                return False

            # Check for significant CapEx (>2% of revenue suggests capital intensity)
            capex_intensity = self._calculate_capex_intensity(data)
            if capex_intensity is None or capex_intensity < 0.02:
                return False

            # Check for positive historical ROIC
            roic = self._calculate_roic(data)
            if roic is None or roic <= 0:
                return False

            # Check if ROIC > WACC (value-creating investments)
            wacc = self._estimate_wacc(data)
            if roic <= wacc:
                return False

            return True

        except Exception:
            return False

    def _validate_inputs(self, ticker: str, data: Dict[str, Any]) -> None:
        """Validate inputs specific to Growth-Adjusted DCF."""
        super()._validate_inputs(ticker, data)

        # Validate CapEx intensity
        capex_intensity = self._calculate_capex_intensity(data)
        if capex_intensity is None or capex_intensity < 0.02:
            raise ModelNotSuitableError('growth_dcf', ticker, f'Low CapEx intensity ({capex_intensity:.1%}) - traditional DCF may be sufficient')

        # Validate ROIC
        roic = self._calculate_roic(data)
        if roic is None or roic <= 0:
            raise InsufficientDataError(ticker, ['roic_calculation_data'])

        # Validate value creation (ROIC > WACC)
        wacc = self._estimate_wacc(data)
        if roic <= wacc:
            raise ModelNotSuitableError('growth_dcf', ticker, f'ROIC ({roic:.1%}) <= WACC ({wacc:.1%}) - growth may not create value')

    def _calculate_valuation(self, ticker: str, data: Dict[str, Any]) -> ValuationResult:
        """Perform Growth-Adjusted DCF calculation."""

        # Step 1: Separate maintenance vs growth CapEx
        capex_breakdown = self._separate_maintenance_growth_capex(data)
        maintenance_capex = capex_breakdown['maintenance_capex']
        growth_capex = capex_breakdown['growth_capex']
        total_capex = capex_breakdown['total_capex']

        # Step 2: Calculate normalized FCF (only subtract maintenance CapEx)
        operating_cf = self._get_operating_cash_flow(data)
        normalized_fcf = operating_cf - maintenance_capex

        if normalized_fcf <= 0:
            raise ModelNotSuitableError('growth_dcf', ticker, f'Negative normalized FCF ({normalized_fcf:,.0f}) - cannot produce meaningful DCF valuation')

        # Step 3: Project normalized FCF growth
        # Use terminal growth for the base business — above-terminal growth
        # comes entirely from _value_growth_investments to avoid double-counting
        wacc = self._estimate_wacc(data)
        terminal_growth = VALUATION_DEFAULTS.TERMINAL_GROWTH_RATE

        projected_normalized_fcfs = self._project_cash_flows(normalized_fcf, terminal_growth, self.projection_years)

        # Step 4: Value the base business (from normalized FCF)
        if wacc <= terminal_growth:
            raise ModelNotSuitableError('growth_dcf', ticker, f'WACC ({wacc:.2%}) <= terminal growth ({terminal_growth:.2%})')
        terminal_normalized_fcf = projected_normalized_fcfs[-1] * (1 + terminal_growth)
        terminal_value_base = terminal_normalized_fcf / (wacc - terminal_growth)

        pv_normalized_fcfs = [fcf / (1 + wacc)**i for i, fcf in enumerate(projected_normalized_fcfs, 1)]
        pv_terminal_base = terminal_value_base / (1 + wacc)**self.projection_years

        base_business_value = sum(pv_normalized_fcfs) + pv_terminal_base

        # Step 5: Value growth investments separately
        growth_investment_value = self._value_growth_investments(growth_capex, data)

        # Step 6: Total enterprise value
        enterprise_value = base_business_value + growth_investment_value

        # Step 7: Convert to equity value and per-share
        equity_value = self._convert_to_equity_value(enterprise_value, data)
        shares_outstanding = self._get_shares_outstanding(data)
        fair_value_per_share = equity_value / shares_outstanding

        # Calculate margin of safety
        current_price = self._get_current_price(data)
        margin_of_safety = None
        if current_price and current_price > 0:
            margin_of_safety = (fair_value_per_share - current_price) / current_price

        # Create result
        result = ValuationResult(
            ticker=ticker,
            model=self.name,
            fair_value=fair_value_per_share,
            current_price=current_price,
            margin_of_safety=margin_of_safety,
            enterprise_value=enterprise_value
        )

        # Add detailed inputs/outputs for transparency
        result.inputs = {
            'operating_cash_flow': operating_cf,
            'total_capex': total_capex,
            'maintenance_capex': maintenance_capex,
            'growth_capex': growth_capex,
            'normalized_fcf': normalized_fcf,
            'roic': self._calculate_roic(data),
            'wacc': wacc,
            'terminal_growth': terminal_growth,
            'capex_intensity': self._calculate_capex_intensity(data),
        }

        result.outputs = {
            'projected_normalized_fcfs': projected_normalized_fcfs,
            'pv_normalized_fcfs': pv_normalized_fcfs,
            'base_business_value': base_business_value,
            'growth_investment_value': growth_investment_value,
            'terminal_value_base': terminal_value_base,
            'pv_terminal_base': pv_terminal_base,
            'equity_value': equity_value,
            'shares_outstanding': shares_outstanding,
            'maintenance_capex_methods': capex_breakdown['estimation_methods'],
        }

        return result

    def _separate_maintenance_growth_capex(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Separate total CapEx into maintenance and growth components.
        Uses multiple estimation methods for robustness.
        """
        total_capex = abs(self._get_total_capex(data))  # Make positive

        # Method 1: Depreciation proxy
        depreciation = self._get_depreciation(data)
        depreciation_estimate = depreciation if depreciation else total_capex * 0.5

        # Method 2: Industry benchmark
        revenue = self._get_revenue(data)
        sector = self._get_sector(data)
        industry_rate = self.industry_maintenance_rates.get(sector.lower(),
                                                          self.industry_maintenance_rates['default'])
        industry_estimate = revenue * industry_rate if revenue else total_capex * 0.5

        # Method 3: Historical minimum approach
        historical_estimate = self._estimate_historical_minimum_capex(data)
        if historical_estimate is None:
            historical_estimate = total_capex * 0.3

        # Method 4: Revenue-based conservative estimate
        conservative_estimate = revenue * 0.015 if revenue else total_capex * 0.4  # 1.5% of revenue

        # Use the maximum of all estimates (conservative approach)
        estimates = [depreciation_estimate, industry_estimate, historical_estimate, conservative_estimate]
        maintenance_capex = max([e for e in estimates if e is not None and e > 0])

        # Ensure maintenance CapEx doesn't exceed total CapEx
        maintenance_capex = min(maintenance_capex, total_capex * 0.8)  # Cap at 80% of total

        growth_capex = total_capex - maintenance_capex

        return {
            'total_capex': total_capex,
            'maintenance_capex': maintenance_capex,
            'growth_capex': growth_capex,
            'estimation_methods': {
                'depreciation_estimate': depreciation_estimate,
                'industry_estimate': industry_estimate,
                'historical_estimate': historical_estimate,
                'conservative_estimate': conservative_estimate,
                'method_used': 'maximum_of_estimates'
            }
        }

    def _get_total_capex(self, data: Dict[str, Any]) -> float:
        """Get total capital expenditures."""
        cashflow = data.get('cashflow')
        if cashflow is None or cashflow.empty:
            return 0

        # Try different possible field names for CapEx
        capex_fields = ['Capital Expenditure', 'Capital Expenditures', 'Purchase Of PPE', 'Net PPE Purchase And Sale']

        for field in capex_fields:
            if field in cashflow.index:
                capex = self._get_most_recent_value(cashflow.loc[field])
                if capex is not None:
                    return abs(capex)  # Make positive

        return 0

    def _get_operating_cash_flow(self, data: Dict[str, Any]) -> float:
        """Get operating cash flow."""
        cashflow = data.get('cashflow')
        if cashflow is None or cashflow.empty:
            return 0

        # Try different possible field names for operating cash flow
        ocf_fields = [
            'Operating Cash Flow',
            'Cash Flow From Continuing Operating Activities',
            'Total Cash From Operating Activities'
        ]

        for field in ocf_fields:
            if field in cashflow.index:
                ocf = self._get_most_recent_value(cashflow.loc[field])
                if ocf is not None:
                    return ocf

        return 0

    def _get_depreciation(self, data: Dict[str, Any]) -> Optional[float]:
        """Get depreciation expense."""
        cashflow = data.get('cashflow')
        if cashflow is None or cashflow.empty:
            return None

        # Try different possible field names
        depreciation_fields = [
            'Depreciation And Amortization',
            'Depreciation Amortization Depletion',
            'Depreciation',
            'Depreciation & Amortization'
        ]

        for field in depreciation_fields:
            if field in cashflow.index:
                depreciation = self._get_most_recent_value(cashflow.loc[field])
                if depreciation and depreciation > 0:
                    return abs(depreciation)  # Make positive

        return None

    def _get_revenue(self, data: Dict[str, Any]) -> Optional[float]:
        """Get total revenue."""
        income = data.get('income')
        if income is None or income.empty:
            return None

        revenue_fields = ['Total Revenue', 'Revenue']

        for field in revenue_fields:
            if field in income.index:
                revenue = self._get_most_recent_value(income.loc[field])
                if revenue and revenue > 0:
                    return revenue

        return None

    def _get_sector(self, data: Dict[str, Any]) -> str:
        """Get company sector."""
        info = data.get('info', {})
        sector = info.get('sector', '')
        return sector if sector else 'default'

    def _estimate_historical_minimum_capex(self, data: Dict[str, Any]) -> Optional[float]:
        """Estimate maintenance CapEx using historical minimum approach."""
        cashflow = data.get('cashflow')
        income = data.get('income')

        if cashflow is None or cashflow.empty or income is None or income.empty:
            return None

        try:
            # Get historical CapEx and revenue
            if 'Capital Expenditures' not in cashflow.index or 'Total Revenue' not in income.index:
                return None

            capex_series = cashflow.loc['Capital Expenditures'].dropna()
            revenue_series = income.loc['Total Revenue'].dropna()

            if len(capex_series) < 3 or len(revenue_series) < 3:
                return None

            # Calculate CapEx/Revenue ratios
            capex_ratios = []
            for i in range(min(len(capex_series), len(revenue_series), 5)):  # Last 5 years max
                if revenue_series.iloc[i] > 0:
                    ratio = abs(capex_series.iloc[i]) / revenue_series.iloc[i]
                    capex_ratios.append(ratio)

            if not capex_ratios:
                return None

            # Use 25th percentile as proxy for maintenance (companies cut growth first)
            min_ratio = np.percentile(capex_ratios, 25)
            current_revenue = revenue_series.iloc[0]

            return current_revenue * min_ratio

        except Exception:
            return None

    def _value_growth_investments(self, growth_capex: float, data: Dict[str, Any]) -> float:
        """Value growth CapEx based on expected ROIC."""
        if growth_capex <= 0:
            return 0

        # Get historical ROIC
        roic = self._calculate_roic(data)
        if roic is None or roic <= 0:
            return 0

        # Be conservative - use 80% of historical ROIC for growth investments
        conservative_roic = roic * 0.8

        # Calculate annual returns from growth investment
        annual_returns = growth_capex * conservative_roic

        # Present value of perpetual returns from this investment
        wacc = self._estimate_wacc(data)
        terminal_growth = VALUATION_DEFAULTS.TERMINAL_GROWTH_RATE

        # Use Gordon growth model for returns from growth investment
        if wacc <= terminal_growth:
            return 0
        pv_growth_returns = annual_returns / (wacc - terminal_growth)

        return pv_growth_returns

    def _calculate_roic(self, data: Dict[str, Any]) -> Optional[float]:
        """
        Calculate Return on Invested Capital.
        ROIC = NOPAT / Invested Capital
        """
        try:
            # Get operating income (EBIT)
            income = data.get('income')
            if income is None or income.empty:
                return None

            operating_income = None
            income_fields = ['Operating Income', 'EBIT']

            for field in income_fields:
                if field in income.index:
                    operating_income = self._get_most_recent_value(income.loc[field])
                    if operating_income:
                        break

            if not operating_income or operating_income <= 0:
                return None

            # Estimate tax rate
            info = data.get('info', {})
            effective_tax_rate = self._safe_float(info.get('effectiveActualTaxRate'), 0.25)  # Default 25%

            # Calculate NOPAT
            nopat = operating_income * (1 - effective_tax_rate)

            # Calculate invested capital (simplified approach)
            balance_sheet = data.get('balance_sheet')
            if balance_sheet is None or balance_sheet.empty:
                return None

            # Total Assets - Cash - Non-interest bearing liabilities (simplified)
            total_assets = self._get_most_recent_value(
                balance_sheet.loc['Total Assets'] if 'Total Assets' in balance_sheet.index else None
            )

            cash = self._get_most_recent_value(
                balance_sheet.loc['Cash And Cash Equivalents'] if 'Cash And Cash Equivalents' in balance_sheet.index else None,
                default=0
            )

            if not total_assets:
                return None

            # Simplified invested capital = Total Assets - Cash
            invested_capital = total_assets - cash

            if invested_capital <= 0:
                return None

            roic = nopat / invested_capital

            # Sanity check - ROIC should be positive
            if roic < 0:
                return None

            # Cap at 100% for computation — asset-light businesses can legitimately
            # exceed 100% ROIC but unbounded values distort the DCF
            roic = min(roic, 1.0)

            return roic

        except Exception:
            return None

    def _calculate_capex_intensity(self, data: Dict[str, Any]) -> Optional[float]:
        """Calculate CapEx as percentage of revenue."""
        total_capex = self._get_total_capex(data)
        revenue = self._get_revenue(data)

        if total_capex and revenue and revenue > 0:
            return total_capex / revenue

        return None
