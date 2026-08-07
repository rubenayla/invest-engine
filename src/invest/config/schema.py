from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class Region(str, Enum):
    US = "US"
    EU = "EU"
    JP = "JP"
    ALL = "ALL"  # Mixed international - no restrictions


class QualityThresholds(BaseModel):
    """Quality assessment criteria."""

    min_roic: Optional[float] = None  # Minimum Return on Invested Capital
    min_roe: Optional[float] = None  # Minimum Return on Equity
    min_current_ratio: Optional[float] = None  # Minimum Current Ratio
    max_debt_equity: Optional[float] = None  # Maximum Debt to Equity ratio
    min_interest_coverage: Optional[float] = None  # Minimum Interest Coverage


class ValueThresholds(BaseModel):
    """Value assessment criteria."""

    max_pe: Optional[float] = None  # Maximum P/E ratio
    max_pb: Optional[float] = None  # Maximum P/B ratio
    max_ev_ebitda: Optional[float] = None  # Maximum EV/EBITDA
    max_ev_ebit: Optional[float] = None  # Maximum EV/EBIT
    max_p_fcf: Optional[float] = None  # Maximum P/FCF ratio


class GrowthThresholds(BaseModel):
    """Growth assessment criteria."""

    min_revenue_growth: Optional[float] = None  # Minimum revenue growth rate
    min_earnings_growth: Optional[float] = None  # Minimum earnings growth rate
    min_fcf_growth: Optional[float] = None  # Minimum FCF growth rate
    min_book_value_growth: Optional[float] = None  # Minimum book value growth


class RiskThresholds(BaseModel):
    """Risk assessment criteria."""

    max_beta: Optional[float] = None  # Maximum beta (market risk)
    min_liquidity_ratio: Optional[float] = None  # Minimum liquidity measures
    max_concentration_risk: Optional[float] = None  # Geographic/customer concentration
    cyclical_adjustment: bool = False  # Apply cyclical adjustments


class ValuationConfig(BaseModel):
    """Valuation model configuration."""

    models: List[str] = Field(
        default=["dcf", "rim"]
    )  # Models to run: dcf, dcf_enhanced, rim, simple_ratios
    scenarios: List[str] = Field(default=["base"])  # Scenarios: bear, base, bull

    # DCF specific
    dcf_years: int = 10  # Projection years
    terminal_growth_rate: float = 0.025  # Terminal growth rate
    risk_free_rate: Optional[float] = None  # Override risk-free rate

    # RIM specific
    rim_years: int = 10  # Projection years
    required_return: Optional[float] = None  # Override required return

    # Simple ratios specific
    pe_target: float = 15.0  # Target P/E ratio
    pb_target: float = 2.5  # Target P/B ratio
    ps_target: float = 2.0  # Target P/S ratio
    ev_ebitda_target: float = 12.0  # Target EV/EBITDA
    dividend_yield_target: float = 0.03  # Target dividend yield (3%)
    peg_target: float = 1.0  # Target PEG ratio


class UniverseConfig(BaseModel):
    """Stock universe configuration."""

    region: Region = Region.US
    market: Optional[str] = None  # Market identifier (e.g., "japan_topix30", "japan_buffett")
    min_market_cap: Optional[float] = None  # USD millions
    max_market_cap: Optional[float] = None  # USD millions
    sectors: Optional[List[str]] = None  # Include specific sectors
    exclude_sectors: Optional[List[str]] = None  # Exclude sectors
    custom_tickers: Optional[List[str]] = None  # Custom ticker list
    pre_screening_universe: Optional[str] = None  # e.g., "sp500"
    top_n_by_market_cap: Optional[int] = None  # Get top N by market cap


class AnalysisConfig(BaseModel):
    """Complete analysis configuration."""

    name: str = "default_analysis"
    description: Optional[str] = None

    # Universe selection
    universe: UniverseConfig = UniverseConfig()

    # Screening criteria
    quality: QualityThresholds = QualityThresholds()
    value: ValueThresholds = ValueThresholds()
    growth: GrowthThresholds = GrowthThresholds()
    risk: RiskThresholds = RiskThresholds()

    # Valuation
    valuation: ValuationConfig = ValuationConfig()

    # Output options
    max_results: int = 50
    sort_by: str = "composite_score"  # composite_score, value_score, quality_score
    generate_reports: bool = True
    save_data: bool = True


class SectorBenchmarks(BaseModel):
    """Sector-specific benchmarks and adjustments."""

    sector: str
    typical_pe_range: List[float] = Field(min_items=2, max_items=2)
    typical_roe_range: List[float] = Field(min_items=2, max_items=2)
    typical_roic_range: List[float] = Field(min_items=2, max_items=2)
    cyclicality: str  # "high", "medium", "low"
    capital_intensity: str  # "high", "medium", "low"
    margin_stability: str  # "stable", "variable", "volatile"
