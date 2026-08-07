"""
Data requirements documentation for valuation models.

This module provides a centralized definition of what data fields each
valuation model requires, making it easier to:
1. Mock data for tests
2. Validate data completeness before running models
3. Document API contracts clearly
"""

from dataclasses import dataclass
from typing import Dict, List, Set


@dataclass
class FieldRequirement:
    """Describes data field requirements for a model."""

    # Fields that must be present and non-null
    required: List[str]

    # At least one of these fields must be present
    required_one_of: List[str]

    # Optional fields that enhance the model if available
    optional: List[str]

    # Description of what the model does and when to use it
    description: str

    def get_all_possible_fields(self) -> Set[str]:
        """Get all fields this model might use."""
        return set(self.required + self.required_one_of + self.optional)

    def validate_data(self, data: Dict) -> tuple[bool, str]:
        """
        Validate if data meets requirements.

        Returns:
            (is_valid, error_message)
        """
        info = data.get('info', {})

        # Check required fields
        for field in self.required:
            if field not in info or info[field] is None:
                return False, f"Missing required field: {field}"

        # Check at least one of required_one_of
        if self.required_one_of:
            has_one = any(
                field in info and info[field] is not None
                for field in self.required_one_of
            )
            if not has_one:
                return False, f"Need at least one of: {', '.join(self.required_one_of)}"

        return True, ""


class ModelDataRequirements:
    """Central registry of data requirements for all valuation models."""

    SIMPLE_RATIOS = FieldRequirement(
        required=['currentPrice'],
        required_one_of=['trailingEps', 'bookValue', 'revenuePerShare'],
        optional=['totalCash', 'sharesOutstanding', 'sector', 'beta'],
        description="Uses P/E, P/B, P/S ratios for quick valuation. Best for mature companies with stable earnings."
    )

    DCF = FieldRequirement(
        required=['currentPrice', 'sharesOutstanding'],
        required_one_of=['freeCashflow', 'operatingCashFlow'],
        optional=['revenueGrowth', 'beta', 'totalDebt', 'totalCash', 'sector'],
        description="Discounted Cash Flow model. Best for companies with positive and predictable cash flows."
    )

    DCF_ENHANCED = FieldRequirement(
        required=['currentPrice', 'sharesOutstanding'],
        required_one_of=['freeCashflow', 'operatingCashFlow'],
        optional=[
            'revenueGrowth', 'earningsGrowth', 'beta', 'totalDebt',
            'totalCash', 'sector', 'profitMargins', 'returnOnEquity'
        ],
        description="Enhanced DCF with multiple scenarios and sensitivity analysis."
    )

    GROWTH_DCF = FieldRequirement(
        required=['currentPrice', 'sharesOutstanding', 'revenueGrowth'],
        required_one_of=['freeCashflow', 'operatingCashFlow'],
        optional=[
            'earningsGrowth', 'beta', 'totalDebt', 'totalCash',
            'sector', 'researchAndDevelopment', 'sellingGeneralAdministrative'
        ],
        description="DCF variant optimized for high-growth companies. Handles negative current cash flows."
    )

    RIM = FieldRequirement(
        required=['currentPrice', 'bookValue', 'sharesOutstanding'],
        required_one_of=['returnOnEquity', 'netIncome'],
        optional=['dividendYield', 'payoutRatio', 'beta', 'sector'],
        description="Residual Income Model. Best for financial companies and firms with significant book value."
    )

    ENSEMBLE = FieldRequirement(
        required=['currentPrice', 'sharesOutstanding'],
        required_one_of=[],  # Ensemble will run whatever models work
        optional=[
            'trailingEps', 'bookValue', 'revenuePerShare', 'freeCashflow',
            'operatingCashFlow', 'returnOnEquity', 'netIncome', 'revenueGrowth',
            'beta', 'totalDebt', 'totalCash', 'sector'
        ],
        description="Combines multiple models and weights results. More fields enable more models."
    )

    # Sector-specific models
    TECH_MODEL = FieldRequirement(
        required=['currentPrice', 'sharesOutstanding', 'revenue'],
        required_one_of=['researchAndDevelopment', 'sellingGeneralAdministrative'],
        optional=[
            'revenueGrowth', 'grossMargins', 'subscriptionRevenue',
            'recurringRevenue', 'customerAcquisitionCost', 'lifetimeValue',
            'marketTam', 'beta', 'sector'
        ],
        description="Specialized for tech companies, values R&D and growth potential."
    )

    BANK_MODEL = FieldRequirement(
        required=['currentPrice', 'bookValue', 'sharesOutstanding'],
        required_one_of=['netInterestIncome', 'netIncome'],
        optional=[
            'tier1Capital', 'nonPerformingAssets', 'loanLossProvision',
            'netInterestMargin', 'returnOnAssets', 'efficiencyRatio'
        ],
        description="Specialized for banks, focuses on book value and interest margins."
    )

    REIT_MODEL = FieldRequirement(
        required=['currentPrice', 'sharesOutstanding'],
        required_one_of=['fundsFromOperations', 'adjustedFundsFromOperations'],
        optional=[
            'dividendYield', 'debtToEquity', 'occupancyRate',
            'priceToFfo', 'sector'
        ],
        description="Specialized for REITs, uses FFO/AFFO metrics."
    )

    UTILITY_MODEL = FieldRequirement(
        required=['currentPrice', 'sharesOutstanding', 'dividendYield'],
        required_one_of=['netIncome', 'operatingIncome'],
        optional=[
            'regulatedAssetBase', 'allowedRoe', 'capitalExpenditure',
            'debtToEquity', 'interestCoverage', 'payoutRatio'
        ],
        description="Specialized for utilities, focuses on regulated returns and dividends."
    )

    NEURAL_NETWORK = FieldRequirement(
        required=['currentPrice', 'marketCap', 'enterpriseValue', 'totalRevenue'],
        required_one_of=['trailingEps', 'forwardEps'],
        optional=[
            'pegRatio', 'priceToBook', 'ebitda', 'profitMargins', 'operatingMargins',
            'returnOnEquity', 'returnOnAssets', 'revenueGrowth', 'earningsGrowth',
            'currentRatio', 'quickRatio', 'debtToEquity', 'freeCashflow',
            'beta', 'dividendYield', 'payoutRatio', 'fiftyTwoWeekHigh', 'fiftyTwoWeekLow',
            'fiftyDayAverage', 'twoHundredDayAverage', 'targetMeanPrice', 'numberOfAnalystOpinions',
            'recommendationKey', 'sector', 'industry'
        ],
        description="Neural network model using 60+ engineered features for pattern-based valuation."
    )

    @classmethod
    def get_requirements(cls, model_name: str) -> FieldRequirement:
        """
        Get requirements for a specific model.

        Parameters
        ----------
        model_name : str
            Name of the model (e.g., 'simple_ratios', 'dcf')

        Returns
        -------
        FieldRequirement
            The field requirements for the model

        Raises
        ------
        ValueError
            If model_name is not recognized
        """
        model_map = {
            'simple_ratios': cls.SIMPLE_RATIOS,
            'dcf': cls.DCF,
            'dcf_enhanced': cls.DCF_ENHANCED,
            'growth_dcf': cls.GROWTH_DCF,
            'rim': cls.RIM,
            'ensemble': cls.ENSEMBLE,
            'tech_model': cls.TECH_MODEL,
            'bank_model': cls.BANK_MODEL,
            'reit_model': cls.REIT_MODEL,
            'utility_model': cls.UTILITY_MODEL,
            'neural_network': cls.NEURAL_NETWORK,
        }

        if model_name not in model_map:
            raise ValueError(f"Unknown model: {model_name}. Available: {list(model_map.keys())}")

        return model_map[model_name]

    @classmethod
    def get_minimal_mock_data(cls, model_name: str) -> Dict:
        """
        Get minimal mock data that satisfies a model's requirements.

        Useful for testing.

        Parameters
        ----------
        model_name : str
            Name of the model

        Returns
        -------
        Dict
            Minimal data dictionary with required fields
        """
        req = cls.get_requirements(model_name)

        mock_data = {
            'info': {},
            'income': None,
            'balance_sheet': None,
            'cashflow': None,
        }

        # Add all required fields with reasonable defaults
        for field in req.required:
            mock_data['info'][field] = cls._get_default_value(field)

        # Add first of required_one_of
        if req.required_one_of:
            field = req.required_one_of[0]
            mock_data['info'][field] = cls._get_default_value(field)

        # Add a few optional fields for better coverage
        for field in req.optional[:3]:  # Just first 3 optional fields
            mock_data['info'][field] = cls._get_default_value(field)

        return mock_data

    @staticmethod
    def _get_default_value(field: str):
        """Get a reasonable default value for a field."""
        # Price/value fields
        if 'price' in field.lower() or field == 'bookValue':
            return 100.0
        # Ratio fields
        elif 'ratio' in field.lower() or field.endswith('Pe'):
            return 15.0
        # Growth fields
        elif 'growth' in field.lower():
            return 0.1
        # Margin fields
        elif 'margin' in field.lower():
            return 0.2
        # Share fields
        elif 'shares' in field.lower():
            return 1_000_000_000
        # Large dollar amounts
        elif field in ['totalCash', 'totalDebt', 'revenue', 'freeCashflow',
                       'operatingCashFlow', 'netIncome']:
            return 10_000_000_000
        # Percentage fields
        elif field in ['returnOnEquity', 'returnOnAssets', 'beta']:
            return 0.15
        # EPS
        elif field == 'trailingEps':
            return 5.0
        # Revenue per share
        elif field == 'revenuePerShare':
            return 25.0
        # Sector
        elif field == 'sector':
            return 'Technology'
        # Default
        else:
            return 1.0
