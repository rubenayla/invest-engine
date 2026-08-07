"""
Base classes for the unified valuation model structure.

This module defines the common interfaces and data structures that all
valuation models must implement for consistency and interoperability.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..exceptions import InsufficientDataError, ModelNotSuitableError, ValuationError
from .model_requirements import FieldRequirement, ModelDataRequirements

logger = logging.getLogger(__name__)


@dataclass
class ValuationResult:
    """
    Standardized result structure for all valuation models.

    This ensures consistent output format across different valuation approaches
    and makes it easier to compare results and generate reports.
    """
    ticker: str
    model: str
    fair_value: Optional[float] = None
    current_price: Optional[float] = None
    margin_of_safety: Optional[float] = None
    enterprise_value: Optional[float] = None

    # Model-specific data
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)

    # Metadata
    calculated_at: datetime = field(default_factory=datetime.now)
    confidence: Optional[str] = None  # 'high', 'medium', 'low'
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format for JSON serialization."""
        return {
            'ticker': self.ticker,
            'model': self.model,
            'fair_value_per_share': self.fair_value,
            'fair_value': self.fair_value,  # For backward compatibility
            'current_price': self.current_price,
            'margin_of_safety': self.margin_of_safety,
            'enterprise_value': self.enterprise_value,
            'inputs': self.inputs,
            'outputs': self.outputs,
            'calculated_at': self.calculated_at.isoformat(),
            'confidence': self.confidence,
            'warnings': self.warnings,
        }

    def is_valid(self) -> bool:
        """Check if the valuation result is valid and complete."""
        return (
            self.ticker is not None and
            self.model is not None and
            self.fair_value is not None and
            self.fair_value > 0
        )


class ValuationModel(ABC):
    """
    Abstract base class for all valuation models.

    This ensures consistent interface across different valuation approaches
    and provides common functionality like error handling and validation.
    """

    def __init__(self, name: str):
        """
        Initialize the valuation model.

        Parameters
        ----------
        name : str
            Name of the valuation model (e.g., 'dcf', 'rim')
        """
        self.name = name
        self.logger = logging.getLogger(f'{__name__}.{name}')
        self._last_suitability_reason = ''

    def get_suitability_reason(self) -> str:
        """Return the reason why is_suitable() last returned False."""
        return self._last_suitability_reason

    @abstractmethod
    def is_suitable(self, ticker: str, data: Dict[str, Any]) -> bool:
        """
        Check if this model is suitable for valuing the given company.

        Parameters
        ----------
        ticker : str
            Stock ticker symbol
        data : Dict[str, Any]
            Company financial data

        Returns
        -------
        bool
            True if model is suitable, False otherwise
        """
        pass

    @abstractmethod
    def _validate_inputs(self, ticker: str, data: Dict[str, Any]) -> None:
        """
        Validate that all required input data is available and reasonable.

        Parameters
        ----------
        ticker : str
            Stock ticker symbol
        data : Dict[str, Any]
            Company financial data

        Raises
        ------
        InsufficientDataError
            If required data is missing or invalid
        """
        pass

    @abstractmethod
    def _calculate_valuation(self, ticker: str, data: Dict[str, Any]) -> ValuationResult:
        """
        Perform the actual valuation calculation.

        Parameters
        ----------
        ticker : str
            Stock ticker symbol
        data : Dict[str, Any]
            Company financial data

        Returns
        -------
        ValuationResult
            The valuation result
        """
        pass

    def value_company(self, ticker: str, verbose: bool = False) -> ValuationResult:
        """
        Main entry point for company valuation.

        This method orchestrates the entire valuation process:
        1. Fetch required data
        2. Check model suitability
        3. Validate inputs
        4. Perform calculation
        5. Return standardized result

        Parameters
        ----------
        ticker : str
            Stock ticker symbol
        verbose : bool
            Whether to enable verbose logging

        Returns
        -------
        ValuationResult
            The valuation result

        Raises
        ------
        ModelNotSuitableError
            If this model is not appropriate for this company
        InsufficientDataError
            If required data is not available
        ValuationError
            If calculation fails
        """
        try:
            # Fetch company data
            data = self._fetch_data(ticker)

            # Check if model is suitable
            if not self.is_suitable(ticker, data):
                raise ModelNotSuitableError(self.name, ticker, 'Model not suitable for this company')

            # Validate inputs
            self._validate_inputs(ticker, data)

            # Perform calculation
            result = self._calculate_valuation(ticker, data)

            # Log result if verbose
            if verbose:
                self.logger.info(f'{self.name} valuation completed for {ticker}: ${result.fair_value:.2f}')

            return result

        except (ModelNotSuitableError, InsufficientDataError):
            raise
        except Exception as e:
            raise ValuationError(f'{self.name} valuation failed for {ticker}: {str(e)}') from e

    def _fetch_data(self, ticker: str) -> Dict[str, Any]:
        """
        Fetch required data for the valuation with caching.

        This implementation uses cached data fetching to improve performance
        and reduce API calls to external data providers.

        Parameters
        ----------
        ticker : str
            Stock ticker symbol

        Returns
        -------
        Dict[str, Any]
            Company data dictionary
        """
        from ..caching.cache_decorators import cached_api_call

        # Define cached data fetching functions
        @cached_api_call(data_type='stock_info', ttl=24*3600)  # 24 hours
        def fetch_stock_info(ticker: str):
            import yfinance as yf
            stock = yf.Ticker(ticker)
            return stock.info

        @cached_api_call(data_type='financials', ttl=6*3600)  # 6 hours
        def fetch_financials(ticker: str):
            import yfinance as yf
            stock = yf.Ticker(ticker)
            return stock.financials

        @cached_api_call(data_type='financials', ttl=6*3600)  # 6 hours
        def fetch_balance_sheet(ticker: str):
            import yfinance as yf
            stock = yf.Ticker(ticker)
            return stock.balance_sheet

        @cached_api_call(data_type='financials', ttl=6*3600)  # 6 hours
        def fetch_cashflow(ticker: str):
            import yfinance as yf
            stock = yf.Ticker(ticker)
            return stock.cashflow

        try:
            # Fetch all data with caching
            info = fetch_stock_info(ticker)
            financials = fetch_financials(ticker)
            balance_sheet = fetch_balance_sheet(ticker)
            cashflow = fetch_cashflow(ticker)

            return {
                'info': info,
                'income': financials,
                'balance_sheet': balance_sheet,
                'cashflow': cashflow,
                'ticker': ticker,
            }

        except Exception as e:
            raise InsufficientDataError(ticker, ['data_fetch_failed']) from e

    def _safe_get(self, data: Dict, key: str, default: Any = None) -> Any:
        """Safely get value from data dictionary with fallback."""
        return data.get(key, default)

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        """Safely convert value to float."""
        try:
            if value is None:
                return default
            return float(value)
        except (ValueError, TypeError):
            return default

    def _get_most_recent_value(self, series, default=None):
        """Get the most recent non-null value from a pandas series."""
        if series is None or series.empty:
            return default

        # Try to get the first valid value (most recent)
        valid_values = series.dropna()
        if valid_values.empty:
            return default

        return valid_values.iloc[0]

    def get_required_fields(self) -> FieldRequirement:
        """
        Get the data field requirements for this model.

        Returns
        -------
        FieldRequirement
            Object describing required, optional, and conditional fields

        Raises
        ------
        ValueError
            If this model is not documented in ModelDataRequirements
        """
        return ModelDataRequirements.get_requirements(self.name)

    def validate_data_completeness(self, data: Dict[str, Any]) -> tuple[bool, str]:
        """
        Validate if the provided data meets this model's requirements.

        This provides a more detailed check than is_suitable(), specifically
        focused on data completeness rather than business logic suitability.

        Parameters
        ----------
        data : Dict[str, Any]
            Company financial data

        Returns
        -------
        tuple[bool, str]
            (is_valid, error_message) - error_message is empty if valid
        """
        try:
            requirements = self.get_required_fields()
            return requirements.validate_data(data)
        except ValueError as e:
            return False, f"Model {self.name} not found in requirements registry: {e}"

    @classmethod
    def get_minimal_mock_data(cls, model_name: str) -> Dict[str, Any]:
        """
        Get minimal mock data for testing this model.

        Parameters
        ----------
        model_name : str
            Name of the model (e.g., 'simple_ratios', 'dcf')

        Returns
        -------
        Dict[str, Any]
            Minimal data dictionary that satisfies the model's requirements
        """
        return ModelDataRequirements.get_minimal_mock_data(model_name)
