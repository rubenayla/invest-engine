"""
Custom exception classes for the investment analysis system.

This module defines specific exceptions that provide better error handling
and debugging information than generic Exception catching.
"""

from typing import List, Optional


class InvestmentAnalysisError(Exception):
    """Base exception for all investment analysis errors."""
    pass


class DataProviderError(InvestmentAnalysisError):
    """Base exception for data provider issues."""
    pass


class DataFetchError(DataProviderError):
    """Error occurred while fetching stock data."""

    def __init__(self, ticker: str, message: str, provider: str = "unknown"):
        self.ticker = ticker
        self.provider = provider
        super().__init__(f"Failed to fetch data for {ticker} from {provider}: {message}")


class RateLimitError(DataProviderError):
    """API rate limit has been exceeded."""

    def __init__(self, provider: str, retry_after: Optional[int] = None):
        self.provider = provider
        self.retry_after = retry_after
        message = f"Rate limit exceeded for {provider}"
        if retry_after:
            message += f". Retry after {retry_after} seconds"
        super().__init__(message)


class ValidationError(InvestmentAnalysisError):
    """Input validation failed."""

    def __init__(self, field: str, value: str, reason: str):
        self.field = field
        self.value = value
        self.reason = reason
        super().__init__(f"Validation failed for {field}='{value}': {reason}")


class ValuationError(InvestmentAnalysisError):
    """Base exception for valuation model errors."""
    pass


class ModelNotSuitableError(ValuationError):
    """Valuation model is not suitable for this company type."""

    def __init__(self, model: str, ticker: str, reason: str):
        self.model = model
        self.ticker = ticker
        self.reason = reason
        super().__init__(f"{model} not suitable for {ticker}: {reason}")


class InsufficientDataError(ValuationError):
    """Not enough data available to perform valuation."""

    def __init__(self, ticker: str, missing_fields: List[str]):
        self.ticker = ticker
        self.missing_fields = missing_fields
        super().__init__(f"Insufficient data for {ticker}. Missing: {', '.join(missing_fields)}")


class AnalysisError(InvestmentAnalysisError):
    """Error during analysis pipeline execution."""

    def __init__(self, stage: str, message: str, ticker: Optional[str] = None):
        self.stage = stage
        self.ticker = ticker
        if ticker:
            super().__init__(f"Analysis failed at {stage} for {ticker}: {message}")
        else:
            super().__init__(f"Analysis failed at {stage}: {message}")


class ConfigurationError(InvestmentAnalysisError):
    """Invalid configuration or setup error."""
    pass


class DashboardError(InvestmentAnalysisError):
    """Dashboard-related errors."""
    pass


# Convenience functions for common error scenarios

def raise_ticker_validation_error(ticker: str, reason: str) -> None:
    """Raise a validation error for invalid ticker format."""
    raise ValidationError("ticker", ticker, reason)


def raise_model_not_suitable(model: str, ticker: str, reason: str) -> None:
    """Raise when a valuation model isn't suitable for a company."""
    raise ModelNotSuitableError(model, ticker, reason)


def raise_insufficient_data(ticker: str, missing_fields: List[str]) -> None:
    """Raise when required data is missing for analysis."""
    raise InsufficientDataError(ticker, missing_fields)
