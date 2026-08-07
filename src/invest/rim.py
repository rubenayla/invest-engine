"""
Residual Income Model (RIM) - Excellent for financial companies and mature businesses.

The Residual Income Model values companies based on their ability to generate returns
above their cost of equity capital. This model is particularly effective for:
- Financial companies (banks, insurance) where DCF is problematic
- Mature companies with stable ROE
- Companies with significant book value assets

RIM Formula:
Value = Current Book Value + Present Value of Future Residual Income

Where Residual Income = (ROE - Cost of Equity) × Book Value

This model is based on the insight that a company's value comes from its ability
to earn returns above what investors require, applied to the capital employed.
"""

from typing import Dict, List, Optional

import yfinance as yf

from .config.constants import VALUATION_DEFAULTS
from .config.logging_config import (
    get_logger,
    log_data_fetch,
    log_error_with_context,
    log_valuation_result,
)
from .error_handling import create_error_context, handle_valuation_error
from .exceptions import InsufficientDataError, ModelNotSuitableError

logger = get_logger(__name__)

PROJECTION_YEARS = VALUATION_DEFAULTS.RIM_PROJECTION_YEARS


def rim_valuation(
    book_equity: float,
    net_income: float,
    cost_of_equity: float,
    n_years: int = 10,
    growth_rate: float = 0.0,
) -> float:
    """
    Basic Residual Income Model (RIM) valuation using net income directly.

    Parameters
    ----------
    book_equity : float
        Current book equity ($).
    net_income : float
        Current net income ($), assumed constant or growing.
    cost_of_equity : float
        Required return on equity (as decimal).
    n_years : int
        Forecast horizon.
    growth_rate : float
        Perpetual residual income growth after forecast.

    Returns
    -------
    float
        Estimated intrinsic value of the company.
    """
    assert cost_of_equity > growth_rate, "Growth rate must be < cost of equity"

    equity = book_equity
    residual_income = 0.0

    for t in range(1, n_years + 1):
        equity_charge = equity * cost_of_equity
        ri = net_income - equity_charge
        residual_income += ri / (1 + cost_of_equity) ** t
        equity += net_income  # assume all earnings are reinvested

    terminal_ri = (net_income - equity * cost_of_equity) / (cost_of_equity - growth_rate)
    residual_income += terminal_ri / (1 + cost_of_equity) ** (n_years + 1)

    return book_equity + residual_income


def calculate_rim(
    ticker: str,
    book_value_per_share: Optional[float] = None,
    roe: Optional[float] = None,
    current_price: Optional[float] = None,
    cost_of_equity: float = VALUATION_DEFAULTS.RIM_COST_OF_EQUITY,
    roe_decay_rate: float = VALUATION_DEFAULTS.RIM_ROE_DECAY_RATE,
    terminal_roe: Optional[float] = None,
    projection_years: int = PROJECTION_YEARS,
    use_sector_adjustment: bool = True,
    verbose: bool = True,
) -> Dict:
    """
    Calculate Residual Income Model (RIM) valuation.

    Perfect for financial companies and asset-heavy businesses where book value
    is a meaningful measure of invested capital and ROE is relatively stable.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol
    book_value_per_share : float, optional
        Current book value per share (fetched if not provided)
    roe : float, optional
        Return on Equity as decimal (fetched if not provided)
    current_price : float, optional
        Current market price per share (fetched if not provided)
    cost_of_equity : float
        Required return on equity (WACC for equity), default 12%
    roe_decay_rate : float
        Rate at which ROE reverts to cost of equity, default 5% per year
    terminal_roe : float, optional
        Long-term sustainable ROE (defaults to cost of equity)
    projection_years : int
        Number of years to project residual income, default 10
    use_sector_adjustment : bool
        Whether to adjust cost of equity based on sector, default True
    verbose : bool
        Whether to print detailed analysis, default True

    Returns
    -------
    Dict
        RIM valuation results including fair value, margin of safety, and components
    """
    # Create error context for comprehensive error handling
    create_error_context(ticker=ticker, model="RIM", function_name="calculate_rim")

    try:
        stock = yf.Ticker(ticker)

        try:
            info = stock.info
            log_data_fetch(logger, ticker, "market_data", True)
        except Exception as e:
            info = {}
            log_data_fetch(logger, ticker, "market_data", False, error=str(e))

        # Fetch missing data
        if book_value_per_share is None:
            book_value_per_share = info.get('bookValue')

        if roe is None:
            roe = info.get('returnOnEquity')

        if current_price is None:
            current_price = info.get('currentPrice') or info.get('regularMarketPrice')

        # Validate essential data
        missing_data = []
        if book_value_per_share is None or book_value_per_share <= 0:
            missing_data.append("book_value_per_share")
        if roe is None:
            missing_data.append("roe")
        if current_price is None or current_price <= 0:
            missing_data.append("current_price")

        if missing_data:
            raise InsufficientDataError(ticker, missing_data)

        # Sector-based cost of equity adjustments
        sector = info.get('sector', '').lower()
        adjusted_cost_of_equity = cost_of_equity

        if use_sector_adjustment:
            sector_adjustments = {
            'financial': -0.01,      # Banks often have lower risk due to regulation
            'utilities': -0.02,      # Regulated utilities, lower risk
            'consumer staples': -0.01,  # Stable demand
            'real estate': -0.005,   # REITs, stable income
            'technology': +0.02,     # Higher growth, higher risk
            'biotechnology': +0.04,  # High risk, high uncertainty
            'energy': +0.01,         # Commodity risk
        }

        for sector_key, adjustment in sector_adjustments.items():
            if sector_key in sector:
                adjusted_cost_of_equity += adjustment
                logger.info(
                    f"Applied sector adjustment for {sector}",
                    extra={
                        "ticker": ticker,
                        "sector": sector,
                        "adjustment": adjustment,
                        "adjusted_cost_of_equity": adjusted_cost_of_equity
                    }
                )
                break

        # Check for RIM model suitability
        sector = info.get('sector', '').lower()

        # RIM is less suitable for:
        if book_value_per_share <= 0:
            raise ModelNotSuitableError(
            "RIM",
            ticker,
            f"Negative or zero book value (${book_value_per_share:.2f}). Book value must be positive for RIM."
        )

        if roe <= 0:
            raise ModelNotSuitableError(
            "RIM",
            ticker,
            f"Negative or zero ROE ({roe:.1%}). Companies with negative ROE cannot generate residual income."
        )

        # Warning for asset-light businesses (but don't fail)
        if 'software' in sector or 'technology' in sector:
            logger.warning(
            f"RIM may be less reliable for asset-light {sector} companies",
            extra={"ticker": ticker, "sector": sector, "reason": "intangible_heavy_business"}
        )

        # Calculate sustainable ROE first (before projections)
            sustainable_roe = _estimate_sustainable_roe(info, roe)

        # Set terminal ROE (long-term sustainable level)
        if terminal_roe is None:
            terminal_roe = adjusted_cost_of_equity  # Long-run, ROE converges to cost of equity

        # Use sustainable ROE for projections instead of current ROE
        # This prevents extreme current ROE from distorting the entire valuation
        normalized_initial_roe = min(sustainable_roe, roe) if sustainable_roe < roe else roe

        if normalized_initial_roe != roe:
            logger.warning(
            f"Using normalized ROE for {ticker}",
            extra={
                "ticker": ticker,
                "original_roe": roe,
                "normalized_roe": normalized_initial_roe,
                "reason": "extreme_roe_adjustment"
            }
        )
        if verbose:
            print(f"⚠️  Using normalized ROE {normalized_initial_roe:.1%} instead of current {roe:.1%} for projections")

        # Calculate residual income projections
            projections = _project_residual_income(
        book_value_per_share=book_value_per_share,
        initial_roe=normalized_initial_roe,
        cost_of_equity=adjusted_cost_of_equity,
        terminal_roe=terminal_roe,
        roe_decay_rate=roe_decay_rate,
        projection_years=projection_years
        )

        # Calculate present value of residual income
            pv_residual_income = _calculate_present_value(
        projections['residual_income'],
        adjusted_cost_of_equity,
        projection_years
        )

        # Calculate terminal value (assume no residual income growth beyond terminal year)
        terminal_residual_income = projections['residual_income'][-1]
        terminal_value = terminal_residual_income / adjusted_cost_of_equity  # Perpetuity
        pv_terminal_value = terminal_value / ((1 + adjusted_cost_of_equity) ** projection_years)

        # Fair value = Current Book Value + PV of all future residual income
        fair_value_per_share = book_value_per_share + pv_residual_income + pv_terminal_value

        # Calculate margin of safety
        margin_of_safety = (fair_value_per_share - current_price) / current_price

        # Additional analysis
        current_residual_income = (roe - adjusted_cost_of_equity) * book_value_per_share

        # Quality metrics
        roe_spread = roe - adjusted_cost_of_equity
        # sustainable_roe already calculated above

        results = {
        'ticker': ticker,
        'current_price': current_price,
        'fair_value': fair_value_per_share,
        'fair_value_per_share': fair_value_per_share,  # Compatibility
        'margin_of_safety': margin_of_safety,

        # Core RIM components
        'book_value_per_share': book_value_per_share,
        'current_roe': roe,
        'cost_of_equity': adjusted_cost_of_equity,
        'terminal_roe': terminal_roe,
        'roe_spread': roe_spread,  # ROE - Cost of Equity

        # Valuation breakdown
        'book_value_component': book_value_per_share,
        'pv_residual_income': pv_residual_income,
        'pv_terminal_value': pv_terminal_value,
        'current_residual_income': current_residual_income,

        # Quality indicators
        'sustainable_roe': sustainable_roe,
        'roe_quality_score': _calculate_roe_quality_score(info, roe),
        'asset_quality_score': _calculate_asset_quality_score(info),

        # Model assumptions
        'inputs': {
            'projection_years': projection_years,
            'roe_decay_rate': roe_decay_rate,
            'sector': sector,
            'sector_adjustment_applied': adjusted_cost_of_equity != cost_of_equity,
        },

        # Projections for analysis
        'projections': projections,
        }

        # Log the valuation result
        log_valuation_result(
        logger,
        ticker,
        "RIM",
        fair_value_per_share,
        margin_of_safety=margin_of_safety,
        roe_spread=roe_spread,
        sustainable_roe=sustainable_roe
        )

        if verbose:
            _print_rim_analysis(results, ticker)

        return results

    except Exception as e:
        # Handle any unexpected errors with comprehensive error context
        error_info = handle_valuation_error(e, ticker, "RIM")

        # Log the error with full context
        log_error_with_context(
            logger,
            error_info.technical_message,
            ticker=ticker,
            model="RIM",
            error_id=error_info.error_id,
            user_message=error_info.user_message
        )

        # Re-raise the original exception to maintain existing behavior
        raise


def _project_residual_income(
    book_value_per_share: float,
    initial_roe: float,
    cost_of_equity: float,
    terminal_roe: float,
    roe_decay_rate: float,
    projection_years: int
) -> Dict:
    """Project future book value and residual income."""

    book_values = [book_value_per_share]
    roes = [initial_roe]
    residual_incomes = []

    for year in range(projection_years):
        # Current year calculations
        current_bv = book_values[-1]
        current_roe = roes[-1]

        # Calculate residual income
        residual_income = (current_roe - cost_of_equity) * current_bv
        residual_incomes.append(residual_income)

        # Project next year's book value (assumes all earnings retained - conservative)
        # BV grows by: ROE * BV (assuming no dividends, conservative assumption)
        retention_rate = 0.7  # Assume 70% retention for most companies
        next_bv = current_bv * (1 + current_roe * retention_rate)
        book_values.append(next_bv)

        # ROE mean reversion toward terminal ROE
        next_roe = current_roe + (terminal_roe - current_roe) * roe_decay_rate
        roes.append(next_roe)

    return {
        'book_values': book_values[:-1],  # Remove last (unused) value
        'roes': roes[:-1],
        'residual_income': residual_incomes,
    }


def _calculate_present_value(residual_incomes: List[float], discount_rate: float, years: int) -> float:
    """Calculate present value of projected residual incomes."""
    pv = 0
    for year, ri in enumerate(residual_incomes, 1):
        pv += ri / ((1 + discount_rate) ** year)
    return pv


def _estimate_sustainable_roe(info: Dict, current_roe: float) -> float:
    """Estimate long-term sustainable ROE based on fundamentals."""
    # Use DuPont analysis: ROE = (Net Margin) × (Asset Turnover) × (Equity Multiplier)

    profit_margin = info.get('profitMargins', 0)
    asset_turnover = info.get('assetTurnover', 1)  # Revenue / Total Assets
    equity_multiplier = info.get('debtToEquity', 0)

    if equity_multiplier:
        equity_multiplier = 1 + equity_multiplier  # Convert to assets/equity ratio
    else:
        equity_multiplier = 1.5  # Conservative default

    # Conservative sustainable ROE with extreme ROE protection
    if profit_margin and asset_turnover:
        sustainable_roe = profit_margin * asset_turnover * equity_multiplier
        # Cap at reasonable levels and don't exceed current ROE significantly
        sustainable_roe = min(sustainable_roe, current_roe * 1.1, 0.25)  # Max 25%
        sustainable_roe = max(sustainable_roe, 0.05)  # Min 5%
    else:
        # Fallback: conservative estimate based on current ROE
        sustainable_roe = min(current_roe * 0.8, 0.15)  # 80% of current, max 15%

    # Special handling for extreme ROE cases (>50%)
    if current_roe > 0.50:  # More than 50% ROE is likely unsustainable
        # Use industry/sector median ROE as reality check
        sector = info.get('sector', '')
        if 'consumer' in sector.lower():
            sector_median_roe = 0.15  # Consumer companies typically 10-20% ROE
        elif 'financial' in sector.lower():
            sector_median_roe = 0.12  # Financial companies 10-15%
        else:
            sector_median_roe = 0.12  # General default

        # For extreme ROE, bias toward sector median
        extreme_adjustment = min(current_roe * 0.3, sector_median_roe * 1.5)
        sustainable_roe = min(sustainable_roe, extreme_adjustment)

        # Absolute cap: no sustainable ROE above configured maximum
        sustainable_roe = min(sustainable_roe, VALUATION_DEFAULTS.RIM_MAX_SUSTAINABLE_ROE)

    return sustainable_roe


def _calculate_roe_quality_score(info: Dict, roe: float) -> float:
    """Score ROE quality based on its components and stability."""
    score = 50  # Base score

    # High ROE is good, but extremely high might be unsustainable
    if 0.12 <= roe <= 0.25:  # Sweet spot: 12-25%
        score += 20
    elif 0.08 <= roe < 0.12:  # Decent: 8-12%
        score += 10
    elif roe > 0.25:  # Very high - might be unsustainable
        score += 5
    elif roe < 0.05:  # Too low
        score -= 20

    # Debt levels (lower is better for ROE quality)
    debt_to_equity = info.get('debtToEquity', 1)
    if debt_to_equity < 0.3:  # Low debt
        score += 10
    elif debt_to_equity > 2:  # High debt - ROE might be leveraged
        score -= 15

    # Profit margins (higher is better)
    profit_margin = info.get('profitMargins', 0)
    if profit_margin > 0.15:  # High margins
        score += 10
    elif profit_margin < 0.05:  # Low margins
        score -= 10

    return max(0, min(100, score))


def _calculate_asset_quality_score(info: Dict) -> float:
    """Score asset quality for book value reliability."""
    score = 50  # Base score

    # Current ratio (liquidity)
    current_ratio = info.get('currentRatio', 1)
    if current_ratio > 2:
        score += 15
    elif current_ratio > 1.2:
        score += 10
    elif current_ratio < 1:
        score -= 20

    # Asset turnover (efficiency)
    asset_turnover = info.get('totalRevenue', 0) / info.get('totalAssets', 1) if info.get('totalAssets') else 0
    if asset_turnover > 1:  # Efficient asset use
        score += 10
    elif asset_turnover < 0.5:  # Inefficient
        score -= 10

    # Tangible assets (more reliable than intangibles)
    # This is harder to get from yfinance, so we use sector as proxy
    sector = info.get('sector', '').lower()
    if 'financial' in sector or 'real estate' in sector:
        score += 5  # Financial assets are fairly valued
    elif 'technology' in sector:
        score -= 5  # More intangible assets

    return max(0, min(100, score))


def _print_rim_analysis(results: Dict, ticker: str) -> None:
    """Print formatted RIM analysis."""
    print(f"\n{'='*60}")
    print(f"RESIDUAL INCOME MODEL (RIM) - {ticker}")
    print(f"{'='*60}")

    print("\n📊 VALUATION SUMMARY")
    print(f"Current Price:           ${results['current_price']:>8.2f}")
    print(f"Fair Value per Share:    ${results['fair_value']:>8.2f}")
    print(f"Margin of Safety:        {results['margin_of_safety']:>8.1%}")

    print("\n💰 VALUE COMPONENTS")
    print(f"Book Value per Share:    ${results['book_value_component']:>8.2f}")
    print(f"PV of Residual Income:   ${results['pv_residual_income']:>8.2f}")
    print(f"PV of Terminal Value:    ${results['pv_terminal_value']:>8.2f}")

    print("\n📈 ROE ANALYSIS")
    print(f"Current ROE:             {results['current_roe']:>8.1%}")
    print(f"Cost of Equity:          {results['cost_of_equity']:>8.1%}")
    print(f"ROE Spread:              {results['roe_spread']:>8.1%}")
    print(f"Sustainable ROE:         {results['sustainable_roe']:>8.1%}")
    print(f"Current Residual Income: ${results['current_residual_income']:>8.2f}")

    print("\n⭐ QUALITY SCORES")
    print(f"ROE Quality Score:       {results['roe_quality_score']:>8.0f}/100")
    print(f"Asset Quality Score:     {results['asset_quality_score']:>8.0f}/100")

    print("\n📋 MODEL ASSUMPTIONS")
    print(f"Projection Years:        {results['inputs']['projection_years']:>8}")
    print(f"ROE Decay Rate:          {results['inputs']['roe_decay_rate']:>8.1%}")
    print(f"Sector:                  {results['inputs']['sector'].title()}")
    print(f"Sector Adjustment:       {'Yes' if results['inputs']['sector_adjustment_applied'] else 'No'}")

    # Investment recommendation
    print(f"\n{'='*60}")
    print("RIM INVESTMENT RECOMMENDATION")
    print(f"{'='*60}")

    margin = results['margin_of_safety']
    roe_spread = results['roe_spread']
    roe_quality = results['roe_quality_score']

    if margin > 0.3 and roe_spread > 0.05 and roe_quality > 70:
        recommendation = "STRONG BUY - Excellent ROE with significant discount to fair value"
    elif margin > 0.15 and roe_spread > 0.02 and roe_quality > 60:
        recommendation = "BUY - Good ROE spread with decent margin of safety"
    elif margin > 0 and roe_spread > 0 and roe_quality > 50:
        recommendation = "HOLD - Positive residual income but limited upside"
    elif roe_spread < 0:
        recommendation = "AVOID - Destroying shareholder value (ROE < Cost of Equity)"
    else:
        recommendation = "SELL - Overvalued relative to book value and earning power"

    print(recommendation)

    # Warnings and notes
    if roe_spread < 0.02:
        print("⚠️  Warning: Low ROE spread - company barely beating cost of capital")
    if results['current_roe'] > 0.30:
        print("⚠️  Warning: Very high ROE may not be sustainable")
    if results['asset_quality_score'] < 40:
        print("⚠️  Warning: Low asset quality - book value may not be reliable")

    print(f"{'='*60}\n")


# Compatibility function for dashboard integration
def calculate_residual_income_model(ticker: str, **kwargs) -> Dict:
    """
    Wrapper function for dashboard compatibility.

    This provides the same interface as other valuation models for easy integration.
    """
    return calculate_rim(ticker, **kwargs)
