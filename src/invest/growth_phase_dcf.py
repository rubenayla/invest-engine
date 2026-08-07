"""
Multi-Stage DCF Model with Realistic Growth Phases

This model addresses the limitation of traditional single-stage DCF models that assume
linear growth decline. Instead, it models company growth in three realistic phases:

Phase 1: High Growth (Years 1-5) - Companies with competitive advantages
Phase 2: Transition (Years 6-10) - Market maturation and increased competition
Phase 3: Terminal Stable (Years 11+) - Mature steady-state growth

The model automatically adjusts phase durations and growth rates based on:
- Company size (market cap)
- Industry maturity
- Historical growth patterns
- Competitive position indicators

Author: Multi-stage growth modeling
"""

from typing import Dict, Optional

import yfinance as yf

from .config.constants import VALUATION_DEFAULTS
from .config.logging_config import get_logger, log_data_fetch, log_valuation_result
from .error_handling import create_error_context
from .exceptions import InsufficientDataError, ModelNotSuitableError

logger = get_logger(__name__)

def calculate_multi_stage_dcf(
    ticker: str,
    fcf: Optional[float] = None,
    shares: Optional[float] = None,
    cash: Optional[float] = None,
    debt: Optional[float] = None,
    current_price: Optional[float] = None,
    high_growth_years: int = VALUATION_DEFAULTS.MULTI_STAGE_HIGH_GROWTH_YEARS,
    transition_years: int = VALUATION_DEFAULTS.MULTI_STAGE_TRANSITION_YEARS,
    discount_rate: float = VALUATION_DEFAULTS.DCF_DISCOUNT_RATE,
    terminal_growth: float = VALUATION_DEFAULTS.DCF_TERMINAL_GROWTH,
    verbose: bool = True,
) -> Dict:
    """
    Calculate multi-stage DCF with realistic growth phases.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol
    fcf : float, optional
        Free cash flow (will be fetched if None)
    shares : float, optional
        Shares outstanding (will be fetched if None)
    cash : float, optional
        Total cash and equivalents (will be fetched if None)
    debt : float, optional
        Total debt (will be fetched if None)
    current_price : float, optional
        Current stock price (will be fetched if None)
    high_growth_years : int
        Duration of high growth phase, default 5
    transition_years : int
        Duration of transition phase, default 5
    discount_rate : float
        Discount rate (cost of equity), default 0.12
    terminal_growth : float
        Terminal growth rate, default 0.025
    verbose : bool
        Whether to print detailed output, default True

    Returns
    -------
    Dict
        Comprehensive multi-stage DCF valuation results
    """
    # Create error context for comprehensive error handling
    create_error_context(ticker=ticker, model="Multi-Stage DCF", function_name="calculate_multi_stage_dcf")

    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        log_data_fetch(logger, ticker, "market_data", True)
    except Exception as e:
        info = {}
        log_data_fetch(logger, ticker, "market_data", False, error=str(e))
        if verbose:
            logger.warning(f"Unable to retrieve market data for {ticker}: {e}")

    # Fetch missing data
    if fcf is None:
        fcf = info.get("freeCashflow")
        # Try cashflow statement fallback for financial companies
        if fcf is None:
            try:
                cf = stock.cashflow
                if not cf.empty and 'Free Cash Flow' in cf.index:
                    fcf_values = cf.loc['Free Cash Flow'].dropna()
                    if not fcf_values.empty:
                        fcf = fcf_values.iloc[0]
            except Exception:
                pass

    if shares is None:
        shares = info.get("sharesOutstanding")
    if cash is None:
        cash = info.get("totalCash", 0)
    if debt is None:
        debt = info.get("totalDebt", 0)
    if current_price is None:
        current_price = info.get("currentPrice")

    # Validate essential data
    missing_data = []
    if fcf is None:
        missing_data.append("fcf")
    if shares is None:
        missing_data.append("shares")
    if current_price is None:
        missing_data.append("current_price")

    if missing_data:
        raise InsufficientDataError(ticker, missing_data)

    # Check for Multi-Stage DCF model suitability
    if fcf <= 0:
        # Multi-stage DCF is inappropriate for companies with negative FCF
        sector = info.get('sector', '').lower()
        industry = info.get('industry', '').lower()

        # Exception for early-stage biotech (they often have negative FCF but high potential)
        is_early_biotech = (
            'biotechnology' in industry or
            ('healthcare' in sector and any(keyword in industry for keyword in ['drug', 'biotech', 'pharmaceutical']))
        )

        if not is_early_biotech:
            raise ModelNotSuitableError(
                "Multi-Stage DCF",
                ticker,
                f"Negative FCF (${fcf:,.0f}) makes multi-stage growth projections unrealistic. Use single-stage DCF or other valuation methods."
            )
        else:
            logger.warning(
                f"Multi-Stage DCF applied to biotech with negative FCF: {ticker}",
                extra={"ticker": ticker, "fcf": fcf, "reason": "biotech_exception"}
            )

    # Analyze company characteristics to determine growth phases
    company_profile = _analyze_company_profile(info, stock, verbose)

    # Determine phase-specific growth rates
    growth_phases = _determine_growth_phases(
        company_profile, high_growth_years, transition_years, terminal_growth
    )

    # Project multi-stage cash flows
    projections = _project_multi_stage_cashflows(fcf, growth_phases)

    # Calculate present values for each phase
    valuation = _calculate_multi_stage_present_values(
        projections, growth_phases, discount_rate, cash, debt, shares
    )

    # Calculate margin of safety
    margin_of_safety = (valuation["fair_value_per_share"] - current_price) / current_price

    # Prepare comprehensive results
    results = {
        "ticker": ticker,
        "fair_value_per_share": valuation["fair_value_per_share"],
        "fair_value": valuation["fair_value_per_share"],  # Dashboard compatibility
        "current_price": current_price,
        "margin_of_safety": margin_of_safety,

        # Phase-specific valuations
        "high_growth_value": valuation["high_growth_pv"] / shares,
        "transition_value": valuation["transition_pv"] / shares,
        "terminal_value_per_share": valuation["terminal_pv"] / shares,

        # Growth phase details
        "high_growth_rate": growth_phases["high_growth_rate"],
        "transition_start_rate": growth_phases["transition_rates"][0] if growth_phases["transition_rates"] else 0,
        "transition_end_rate": growth_phases["transition_rates"][-1] if growth_phases["transition_rates"] else 0,
        "terminal_growth_rate": terminal_growth,

        # Company profile insights
        "company_stage": company_profile["stage"],
        "market_cap_category": company_profile["market_cap_category"],
        "industry_maturity": company_profile["industry_maturity"],
        "competitive_strength": company_profile["competitive_strength"],

        # Traditional DCF components
        "enterprise_value": valuation["enterprise_value"],
        "terminal_value": valuation["terminal_value"],

        # Inputs and assumptions
        "inputs": {
            "base_fcf": fcf,
            "shares": shares,
            "cash": cash,
            "debt": debt,
            "discount_rate": discount_rate,
            "high_growth_years": high_growth_years,
            "transition_years": transition_years,
            "total_projection_years": high_growth_years + transition_years,
        },
    }

    # Log the multi-stage DCF valuation result
    log_valuation_result(
        logger,
        ticker,
        "Multi-Stage DCF",
        results['fair_value_per_share'],
        margin_of_safety=results['margin_of_safety'],
        high_growth_rate=results['high_growth_rate'],
        terminal_growth_rate=results['terminal_growth_rate'],
        company_stage=company_profile['stage']
    )

    if verbose:
        _print_multi_stage_dcf_summary(results, ticker, growth_phases, company_profile)

    return results



def _analyze_company_profile(info: Dict, stock, verbose: bool) -> Dict:
    """Analyze company characteristics to determine appropriate growth modeling."""
    profile = {
        "market_cap_category": "unknown",
        "stage": "mature",
        "industry_maturity": "mature",
        "competitive_strength": "moderate",
        "historical_growth": 0.05,
        "revenue_growth_5y": 0.05,
        "profitability_trend": "stable",
    }

    # Market cap analysis
    market_cap = info.get("marketCap", 0)
    if market_cap > 200e9:  # $200B+
        profile["market_cap_category"] = "mega_cap"
        profile["stage"] = "mature"
    elif market_cap > 10e9:  # $10B-200B
        profile["market_cap_category"] = "large_cap"
        profile["stage"] = "growth_to_mature"
    elif market_cap > 2e9:   # $2B-10B
        profile["market_cap_category"] = "mid_cap"
        profile["stage"] = "growth"
    else:  # <$2B
        profile["market_cap_category"] = "small_cap"
        profile["stage"] = "early_growth"

    # Industry analysis
    sector = info.get("sector", "").lower()
    industry = info.get("industry", "").lower()

    # Tech and growth sectors
    if any(keyword in sector for keyword in ["technology", "communication", "biotechnology"]):
        if any(keyword in industry for keyword in ["software", "internet", "cloud", "ai", "biotech"]):
            profile["industry_maturity"] = "emerging"
        else:
            profile["industry_maturity"] = "growth"
    # Traditional sectors
    elif any(keyword in sector for keyword in ["utilities", "real estate", "consumer staples"]):
        profile["industry_maturity"] = "mature"
    else:
        profile["industry_maturity"] = "growth"

    # Competitive strength indicators
    roe = info.get("returnOnEquity", 0)
    profit_margin = info.get("profitMargins", 0)

    if roe and profit_margin:
        if roe > 0.20 and profit_margin > 0.15:
            profile["competitive_strength"] = "strong"
        elif roe > 0.15 and profit_margin > 0.10:
            profile["competitive_strength"] = "moderate"
        else:
            profile["competitive_strength"] = "weak"

    # Historical growth analysis
    try:
        revenue_growth = info.get("revenueGrowth")
        info.get("earningsGrowth")

        if revenue_growth:
            profile["revenue_growth_5y"] = min(max(revenue_growth, -0.20), 0.50)  # Cap between -20% and 50%

        # Historical FCF growth from financials
        cf = stock.cashflow
        if not cf.empty and "Free Cash Flow" in cf.index:
            fcf_series = cf.loc["Free Cash Flow"].dropna()
            if len(fcf_series) >= 3:
                # Calculate CAGR over available years
                years = len(fcf_series) - 1
                if fcf_series.iloc[0] > 0 and fcf_series.iloc[-1] > 0:
                    cagr = (fcf_series.iloc[-1] / fcf_series.iloc[0]) ** (1/years) - 1
                    profile["historical_growth"] = min(max(cagr, -0.15), 0.40)  # Cap between -15% and 40%
    except Exception as e:
        if verbose:
            logger.debug(f"Could not analyze historical growth for {info.get('symbol', 'unknown')}: {e}")

    return profile


def _determine_growth_phases(
    profile: Dict, high_growth_years: int, transition_years: int, terminal_growth: float
) -> Dict:
    """Determine realistic growth rates for each phase based on company profile."""

    # Base growth rates by company stage and industry
    base_growth_matrix = {
        ("early_growth", "emerging"): 0.25,
        ("early_growth", "growth"): 0.20,
        ("early_growth", "mature"): 0.15,
        ("growth", "emerging"): 0.20,
        ("growth", "growth"): 0.15,
        ("growth", "mature"): 0.12,
        ("growth_to_mature", "emerging"): 0.15,
        ("growth_to_mature", "growth"): 0.12,
        ("growth_to_mature", "mature"): 0.10,
        ("mature", "emerging"): 0.12,
        ("mature", "growth"): 0.10,
        ("mature", "mature"): 0.08,
    }

    stage = profile["stage"]
    industry_maturity = profile["industry_maturity"]
    base_high_growth = base_growth_matrix.get((stage, industry_maturity), 0.10)

    # Adjust based on competitive strength
    competitive_multipliers = {
        "strong": 1.2,
        "moderate": 1.0,
        "weak": 0.8,
    }
    competitive_adj = competitive_multipliers.get(profile["competitive_strength"], 1.0)

    # Incorporate historical performance
    historical_growth = profile.get("historical_growth", 0.05)
    revenue_growth = profile.get("revenue_growth_5y", 0.05)

    # Blend model-based and historical growth (60% model, 40% historical)
    historical_blend = (historical_growth + revenue_growth) / 2
    high_growth_rate = (0.6 * base_high_growth * competitive_adj + 0.4 * historical_blend)

    # Apply reasonable bounds
    high_growth_rate = min(max(high_growth_rate, 0.02), 0.30)  # Between 2% and 30%

    # Create transition phase with gradual decline to terminal
    transition_rates = []
    if transition_years > 0:
        decline_per_year = (high_growth_rate - terminal_growth) / (transition_years + 1)
        for i in range(transition_years):
            rate = high_growth_rate - (decline_per_year * (i + 1))
            rate = max(rate, terminal_growth)  # Don't go below terminal
            transition_rates.append(rate)

    return {
        "high_growth_rate": high_growth_rate,
        "high_growth_years": high_growth_years,
        "transition_rates": transition_rates,
        "transition_years": transition_years,
        "terminal_growth": terminal_growth,
    }


def _project_multi_stage_cashflows(fcf: float, growth_phases: Dict) -> Dict:
    """Project cash flows through multiple growth phases."""
    projections = {
        "high_growth_fcf": [],
        "transition_fcf": [],
        "all_fcf": [],
        "years": [],
        "growth_rates": [],
    }

    current_fcf = fcf
    year = 0

    # High growth phase
    high_growth_rate = growth_phases["high_growth_rate"]
    for i in range(growth_phases["high_growth_years"]):
        year += 1
        current_fcf *= (1 + high_growth_rate)
        projections["high_growth_fcf"].append(current_fcf)
        projections["all_fcf"].append(current_fcf)
        projections["years"].append(year)
        projections["growth_rates"].append(high_growth_rate)

    # Transition phase
    for i, transition_rate in enumerate(growth_phases["transition_rates"]):
        year += 1
        current_fcf *= (1 + transition_rate)
        projections["transition_fcf"].append(current_fcf)
        projections["all_fcf"].append(current_fcf)
        projections["years"].append(year)
        projections["growth_rates"].append(transition_rate)

    # Terminal FCF (first year of terminal phase)
    terminal_fcf = current_fcf * (1 + growth_phases["terminal_growth"])
    projections["terminal_fcf"] = terminal_fcf
    projections["final_projection_fcf"] = current_fcf

    return projections


def _calculate_multi_stage_present_values(
    projections: Dict,
    growth_phases: Dict,
    discount_rate: float,
    cash: float,
    debt: float,
    shares: float
) -> Dict:
    """Calculate present values for each growth phase."""

    # Present value of high growth phase
    high_growth_pv = sum(
        fcf / (1 + discount_rate) ** (i + 1)
        for i, fcf in enumerate(projections["high_growth_fcf"])
    )

    # Present value of transition phase
    transition_start_year = growth_phases["high_growth_years"] + 1
    transition_pv = sum(
        fcf / (1 + discount_rate) ** (transition_start_year + i)
        for i, fcf in enumerate(projections["transition_fcf"])
    )

    # Terminal value using Gordon Growth Model
    terminal_fcf = projections["terminal_fcf"]
    terminal_value = terminal_fcf / (discount_rate - growth_phases["terminal_growth"])

    # Present value of terminal value
    total_projection_years = growth_phases["high_growth_years"] + growth_phases["transition_years"]
    terminal_pv = terminal_value / (1 + discount_rate) ** total_projection_years

    # Enterprise and equity value
    enterprise_value = high_growth_pv + transition_pv + terminal_pv
    equity_value = enterprise_value - debt + cash

    # Fair value per share
    fair_value_per_share = equity_value / shares

    return {
        "high_growth_pv": high_growth_pv,
        "transition_pv": transition_pv,
        "terminal_pv": terminal_pv,
        "enterprise_value": enterprise_value,
        "equity_value": equity_value,
        "terminal_value": terminal_value,
        "fair_value_per_share": fair_value_per_share,
    }


def _print_multi_stage_dcf_summary(
    results: Dict, ticker: str, growth_phases: Dict, company_profile: Dict
) -> None:
    """Print comprehensive multi-stage DCF analysis."""
    print(f"\n{'='*65}")
    print(f"MULTI-STAGE DCF VALUATION - {ticker}")
    print(f"{'='*65}")

    # Valuation summary
    print("\n📊 VALUATION SUMMARY")
    print(f"Current Price:           ${results['current_price']:>10,.2f}")
    print(f"Fair Value per Share:    ${results['fair_value_per_share']:>10,.2f}")
    print(f"Margin of Safety:        {results['margin_of_safety']:>10.1%}")

    # Value by phase
    print("\n🎯 VALUE BY GROWTH PHASE")
    total_value = results['fair_value_per_share']
    print(f"High Growth Value:       ${results['high_growth_value']:>10,.2f} ({results['high_growth_value']/total_value:.1%})")
    print(f"Transition Value:        ${results['transition_value']:>10,.2f} ({results['transition_value']/total_value:.1%})")
    print(f"Terminal Value:          ${results['terminal_value_per_share']:>10,.2f} ({results['terminal_value_per_share']/total_value:.1%})")

    # Growth phases
    print("\n📈 GROWTH PHASES")
    print(f"High Growth (Yrs 1-{growth_phases['high_growth_years']:<2}):  {results['high_growth_rate']:>10.1%}")
    if growth_phases['transition_years'] > 0:
        start_yr = growth_phases['high_growth_years'] + 1
        end_yr = start_yr + growth_phases['transition_years'] - 1
        print(f"Transition (Yrs {start_yr}-{end_yr}):    {results['transition_start_rate']:>7.1%} → {results['transition_end_rate']:.1%}")
    print(f"Terminal (Yr {growth_phases['high_growth_years'] + growth_phases['transition_years'] + 1}+):          {results['terminal_growth_rate']:>10.1%}")

    # Company profile
    print("\n🏢 COMPANY PROFILE")
    print(f"Stage:                   {company_profile['stage'].replace('_', ' ').title()}")
    print(f"Market Cap:              {company_profile['market_cap_category'].replace('_', ' ').title()}")
    print(f"Industry Maturity:       {company_profile['industry_maturity'].title()}")
    print(f"Competitive Strength:    {company_profile['competitive_strength'].title()}")

    # Key assumptions
    print("\n📋 KEY ASSUMPTIONS")
    print(f"Discount Rate:           {results['inputs']['discount_rate']:>10.1%}")
    print(f"Base FCF:                ${results['inputs']['base_fcf']:>10,.0f}")
    print(f"Total Projection Years:  {results['inputs']['total_projection_years']:>10}")

    print(f"\n{'='*65}")
