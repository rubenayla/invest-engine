"""
Bank Valuation Model

Banks require specialized valuation approaches because they:
- Have unique business models (deposits, loans, interest spreads)
- Face regulatory capital requirements
- Use different financial metrics (ROA, ROE, efficiency ratio)
- Have cyclical earnings and credit risk considerations
"""

import logging
from typing import Any, Dict, Optional

from ...config.constants import VALUATION_DEFAULTS
from ...exceptions import InsufficientDataError
from ..base import ValuationModel, ValuationResult

logger = logging.getLogger(__name__)


class BankModel(ValuationModel):
    """
    Specialized valuation model for banks and financial institutions.

    This model uses bank-specific metrics like:
    - Return on Assets (ROA) and Return on Equity (ROE)
    - Net Interest Margin (NIM)
    - Efficiency Ratio
    - Price-to-Book ratio analysis
    - Dividend-based valuation
    """

    def __init__(self):
        super().__init__('bank')

    def is_suitable(self, ticker: str, data: Dict[str, Any]) -> bool:
        """Check if company is a bank suitable for this model."""
        try:
            info = data.get('info', {})

            sector = info.get('sector', '').lower()
            industry = info.get('industry', '').lower()

            # Check for banking/financial indicators
            banking_keywords = [
                'financial services', 'banks', 'banking', 'bank',
                'commercial banking', 'regional banks', 'money center banks',
                'savings & loans', 'credit services'
            ]

            is_bank = any(keyword in sector or keyword in industry for keyword in banking_keywords)

            if not is_bank:
                return False

            # Banks typically have different balance sheet structure
            # Check for banking-specific characteristics
            balance_sheet = data.get('balance_sheet')
            if balance_sheet is not None and not balance_sheet.empty:
                # Look for banking-specific balance sheet items
                has_deposits = any('deposit' in str(idx).lower() for idx in balance_sheet.index)
                has_loans = any('loan' in str(idx).lower() for idx in balance_sheet.index)

                if has_deposits or has_loans:
                    return True

            # Check for bank-typical financial ratios
            info = data.get('info', {})
            book_value = info.get('bookValue')
            if book_value and book_value > 0:
                current_price = info.get('currentPrice')
                if current_price:
                    pb_ratio = current_price / book_value
                    # Banks typically trade at lower P/B ratios
                    if pb_ratio and 0.5 <= pb_ratio <= 3.0:
                        return True

            return is_bank  # Default to sector/industry classification

        except Exception:
            return False

    def _validate_inputs(self, ticker: str, data: Dict[str, Any]) -> None:
        """Validate bank-specific input data."""
        info = data.get('info', {})

        if not info:
            raise InsufficientDataError(ticker, ['info'])

        # Banks need book value for P/B analysis
        book_value = info.get('bookValue')
        if not book_value or book_value <= 0:
            raise InsufficientDataError(ticker, ['bookValue'])

        # Need current price
        current_price = info.get('currentPrice')
        if not current_price or current_price <= 0:
            raise InsufficientDataError(ticker, ['currentPrice'])

    def _calculate_valuation(self, ticker: str, data: Dict[str, Any]) -> ValuationResult:
        """Calculate bank valuation using multiple approaches."""
        info = data.get('info', {})

        # Extract bank-specific metrics
        current_price = self._safe_float(info.get('currentPrice'))
        book_value = self._safe_float(info.get('bookValue'))
        roe = self._safe_float(info.get('returnOnEquity'))
        roa = self._safe_float(info.get('returnOnAssets'))
        dividend_yield = self._safe_float(info.get('dividendYield'))

        # Calculate different valuation approaches
        pb_valuation = self._calculate_pb_valuation(data)
        roe_based_valuation = self._calculate_roe_based_valuation(data)
        dividend_valuation = self._calculate_dividend_valuation(data)

        # Weighted average of approaches
        valuations = []
        weights = []
        valuation_details = {}

        if pb_valuation:
            valuations.append(pb_valuation)
            weights.append(0.4)  # 40% weight to P/B analysis
            valuation_details['pb_based'] = pb_valuation

        if roe_based_valuation:
            valuations.append(roe_based_valuation)
            weights.append(0.35)  # 35% weight to ROE-based
            valuation_details['roe_based'] = roe_based_valuation

        if dividend_valuation:
            valuations.append(dividend_valuation)
            weights.append(0.25)  # 25% weight to dividend model
            valuation_details['dividend_based'] = dividend_valuation

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
        confidence = self._determine_confidence(len(valuations), roe, roa)

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
            'book_value': book_value,
            'roe': roe,
            'roa': roa,
            'dividend_yield': dividend_yield,
        }

        result.outputs = {
            'individual_valuations': valuation_details,
            'valuation_methods_used': len(valuations),
            'average_fair_value': fair_value,
            'current_pb_ratio': current_price / book_value if book_value and book_value > 0 else None,
        }

        return result

    def _calculate_pb_valuation(self, data: Dict[str, Any]) -> Optional[float]:
        """Calculate valuation based on Price-to-Book analysis."""
        try:
            info = data.get('info', {})

            book_value = self._safe_float(info.get('bookValue'))
            if not book_value or book_value <= 0:
                return None

            # Determine appropriate P/B multiple based on bank quality
            roe = self._safe_float(info.get('returnOnEquity'))
            roa = self._safe_float(info.get('returnOnAssets'))

            # Base P/B multiple for banks
            base_pb_multiple = 1.0

            # Adjust based on profitability metrics
            if roe and roe > 0.12:  # >12% ROE indicates good profitability
                base_pb_multiple *= 1.3
            elif roe and roe > 0.08:  # >8% ROE is decent
                base_pb_multiple *= 1.1
            elif roe and roe < 0.05:  # <5% ROE is concerning
                base_pb_multiple *= 0.8

            if roa and roa > 0.01:  # >1% ROA is good for banks
                base_pb_multiple *= 1.1
            elif roa and roa < 0.005:  # <0.5% ROA is poor
                base_pb_multiple *= 0.9

            # Cap the multiple at reasonable levels
            pb_multiple = max(0.5, min(base_pb_multiple, 2.0))

            return book_value * pb_multiple

        except Exception as e:
            logger.debug(f"P/B valuation failed: {e}")
            return None

    def _calculate_roe_based_valuation(self, data: Dict[str, Any]) -> Optional[float]:
        """Calculate valuation based on ROE sustainability model."""
        try:
            info = data.get('info', {})

            book_value = self._safe_float(info.get('bookValue'))
            roe = self._safe_float(info.get('returnOnEquity'))

            if not book_value or not roe or book_value <= 0 or roe <= 0:
                return None

            # Cost of equity for banks (higher than general market due to regulation)
            cost_of_equity = VALUATION_DEFAULTS.RISK_FREE_RATE + 0.08  # Risk-free + 8% premium

            if roe <= cost_of_equity:
                return book_value  # Trade at book value if ROE = cost of equity

            # Simple ROE-based valuation: P/B = ROE / Cost of Equity
            pb_ratio = min(roe / cost_of_equity, 2.5)  # Cap at 2.5x book

            return book_value * pb_ratio

        except Exception as e:
            logger.debug(f"ROE-based valuation failed: {e}")
            return None

    def _calculate_dividend_valuation(self, data: Dict[str, Any]) -> Optional[float]:
        """Calculate valuation using dividend discount model for banks."""
        try:
            info = data.get('info', {})

            dividend_rate = self._safe_float(info.get('dividendRate'))
            self._safe_float(info.get('dividendYield'))

            if not dividend_rate or dividend_rate <= 0:
                return None

            # Estimate dividend growth (conservative for banks due to regulation)
            dividend_growth = 0.03  # 3% annual growth

            # Required return for bank dividends
            required_return = VALUATION_DEFAULTS.RISK_FREE_RATE + 0.06  # Risk-free + 6%

            if required_return <= dividend_growth:
                return None

            # Dividend discount model
            next_year_dividend = dividend_rate * (1 + dividend_growth)
            return next_year_dividend / (required_return - dividend_growth)

        except Exception as e:
            logger.debug(f"Dividend valuation failed: {e}")
            return None

    def _determine_confidence(self, num_methods: int, roe: Optional[float],
                            roa: Optional[float]) -> str:
        """Determine confidence based on data quality and bank metrics."""
        if num_methods >= 3:
            base_confidence = 'high'
        elif num_methods >= 2:
            base_confidence = 'medium'
        else:
            base_confidence = 'low'

        # Adjust based on bank-specific factors
        if roe and roa:
            if roe > 0.10 and roa > 0.008:  # Strong profitability metrics
                if base_confidence == 'medium':
                    return 'high'
            elif roe < 0.05 or roa < 0.003:  # Weak profitability
                if base_confidence == 'high':
                    return 'medium'
                elif base_confidence == 'medium':
                    return 'low'

        return base_confidence
