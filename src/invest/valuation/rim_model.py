"""
RIM (Residual Income Model) implementation under the unified structure.

The Residual Income Model is particularly effective for financial companies
and mature businesses where traditional DCF may not be suitable.
"""

from typing import Any, Dict, Optional

from ..config.constants import VALUATION_DEFAULTS
from ..exceptions import InsufficientDataError, ModelNotSuitableError
from .base import ValuationModel, ValuationResult


class RIMModel(ValuationModel):
    """Residual Income Model for equity valuation."""

    def __init__(self):
        super().__init__('rim')
        self.projection_years = VALUATION_DEFAULTS.RIM_PROJECTION_YEARS

    def is_suitable(self, ticker: str, data: Dict[str, Any]) -> bool:
        """RIM is suitable for companies with stable book values and ROE."""
        try:
            # Check for required financial data
            balance_sheet = data.get('balance_sheet')
            income = data.get('income')

            if balance_sheet is None or balance_sheet.empty:
                self._last_suitability_reason = 'Missing balance sheet data'
                return False
            if income is None or income.empty:
                self._last_suitability_reason = 'Missing income statement data'
                return False

            # Check for positive book equity
            book_equity = self._get_book_equity(data)
            if book_equity is None or book_equity <= 0:
                self._last_suitability_reason = 'Negative or missing book equity'
                return False

            # Check for reasonable ROE
            roe = self._calculate_roe(data)
            if roe is None or roe <= 0 or roe > 1.0:  # ROE > 100% is unrealistic
                self._last_suitability_reason = f'ROE unsuitable ({roe:.1%})' if roe is not None else 'Missing ROE'
                return False

            return True

        except Exception:
            return False

    def _validate_inputs(self, ticker: str, data: Dict[str, Any]) -> None:
        """Validate required RIM inputs."""
        required_fields = ['balance_sheet', 'income', 'info']

        for field in required_fields:
            if field not in data or data[field] is None:
                raise InsufficientDataError(ticker, [field])

        # Validate book equity
        book_equity = self._get_book_equity(data)
        if book_equity is None or book_equity <= 0:
            raise InsufficientDataError(ticker, ['positive_book_equity'])

        # Validate ROE
        roe = self._calculate_roe(data)
        if roe is None or roe <= 0:
            raise InsufficientDataError(ticker, ['positive_roe'])

        # Check for extreme ROE that might indicate data issues
        if roe > 1.0:  # 100%+ ROE is suspicious
            raise ModelNotSuitableError('rim', ticker, f'Extreme ROE ({roe:.1%}) suggests data quality issues')

    def _calculate_valuation(self, ticker: str, data: Dict[str, Any]) -> ValuationResult:
        """Perform RIM calculation."""
        # Extract key inputs
        book_equity = self._get_book_equity(data)
        net_income = self._get_net_income(data)
        roe = self._calculate_roe(data)
        cost_of_equity = self._estimate_cost_of_equity(data)

        # Calculate residual income components
        roe_spread = roe - cost_of_equity

        # Project book values and residual incomes
        projected_book_values = self._project_book_values(
            book_equity, roe, self.projection_years
        )

        projected_residual_incomes = [
            roe_spread * bv for bv in projected_book_values
        ]

        # Calculate present value of residual incomes
        pv_residual_incomes = [
            ri / (1 + cost_of_equity)**i
            for i, ri in enumerate(projected_residual_incomes, 1)
        ]

        # Calculate terminal value (assuming fade to cost of equity)
        terminal_growth = VALUATION_DEFAULTS.TERMINAL_GROWTH_RATE
        terminal_spread = roe_spread * VALUATION_DEFAULTS.ROE_FADE_RATE
        terminal_book_value = projected_book_values[-1] * (1 + terminal_growth)
        terminal_residual_income = terminal_spread * terminal_book_value
        if cost_of_equity <= terminal_growth:
            raise ModelNotSuitableError('rim', ticker, f'Cost of equity ({cost_of_equity:.2%}) <= terminal growth ({terminal_growth:.2%})')
        terminal_value = terminal_residual_income / (cost_of_equity - terminal_growth)
        pv_terminal = terminal_value / (1 + cost_of_equity)**self.projection_years

        # RIM formula: Current Book Value + PV of Future Residual Income
        equity_value = book_equity + sum(pv_residual_incomes) + pv_terminal

        # Calculate per-share value
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
            margin_of_safety=margin_of_safety
        )

        # Add detailed inputs/outputs
        result.inputs = {
            'book_equity': book_equity,
            'net_income': net_income,
            'roe': roe,
            'cost_of_equity': cost_of_equity,
            'roe_spread': roe_spread,
            'projection_years': self.projection_years,
        }

        result.outputs = {
            'projected_book_values': projected_book_values,
            'projected_residual_incomes': projected_residual_incomes,
            'pv_residual_incomes': pv_residual_incomes,
            'terminal_value': terminal_value,
            'pv_terminal': pv_terminal,
            'equity_value': equity_value,
            'shares_outstanding': shares_outstanding,
            'roe_spread': roe_spread,
        }

        return result

    def _get_book_equity(self, data: Dict[str, Any]) -> Optional[float]:
        """Get book value of equity from balance sheet."""
        balance_sheet = data.get('balance_sheet')
        if balance_sheet is None or balance_sheet.empty:
            return None

        # Try different possible field names for stockholders' equity
        equity_fields = [
            'Total Stockholder Equity',
            'Stockholders Equity',
            'Total Equity',
            'Shareholders Equity',
            'Common Stock Equity'
        ]

        for field in equity_fields:
            if field in balance_sheet.index:
                equity = self._get_most_recent_value(balance_sheet.loc[field])
                if equity is not None and equity > 0:
                    return equity

        return None

    def _get_net_income(self, data: Dict[str, Any]) -> Optional[float]:
        """Get net income from income statement."""
        income = data.get('income')
        if income is None or income.empty:
            return None

        # Try different field names
        income_fields = [
            'Net Income',
            'Net Income Common Stockholders',
            'Net Income Continuous Operations'
        ]

        for field in income_fields:
            if field in income.index:
                net_income = self._get_most_recent_value(income.loc[field])
                if net_income is not None:
                    return net_income

        return None

    def _calculate_roe(self, data: Dict[str, Any]) -> Optional[float]:
        """Calculate Return on Equity."""
        net_income = self._get_net_income(data)
        book_equity = self._get_book_equity(data)

        if net_income is None or book_equity is None or book_equity <= 0:
            return None

        return net_income / book_equity

    def _estimate_cost_of_equity(self, data: Dict[str, Any]) -> float:
        """Estimate cost of equity using CAPM."""
        info = data.get('info', {})

        # Get beta
        beta = self._safe_float(info.get('beta'), 1.0)

        # Use default risk-free rate and market premium
        risk_free_rate = VALUATION_DEFAULTS.RISK_FREE_RATE
        market_premium = VALUATION_DEFAULTS.EQUITY_RISK_PREMIUM

        return risk_free_rate + beta * market_premium

    def _project_book_values(self, initial_book_equity: float, roe: float, years: int) -> list:
        """Project future book values assuming retained earnings growth."""
        # Assume some portion of earnings is retained (not paid as dividends)
        retention_ratio = VALUATION_DEFAULTS.RETENTION_RATIO

        projected = []
        book_value = initial_book_equity

        for year in range(years):
            # Book value grows by retained earnings
            retained_earnings = book_value * roe * retention_ratio
            book_value += retained_earnings
            projected.append(book_value)

        return projected

    def _get_shares_outstanding(self, data: Dict[str, Any]) -> float:
        """Get shares outstanding."""
        info = data.get('info', {})
        shares = self._safe_float(info.get('sharesOutstanding'))

        if not shares or shares <= 0:
            shares = self._safe_float(info.get('impliedSharesOutstanding'))

        if not shares or shares <= 0:
            raise InsufficientDataError('unknown_ticker', ['shares_outstanding'])

        return shares

    def _get_current_price(self, data: Dict[str, Any]) -> Optional[float]:
        """Get current stock price."""
        info = data.get('info', {})
        return self._safe_float(info.get('currentPrice'))
