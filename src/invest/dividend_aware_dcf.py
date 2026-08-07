"""
Enhanced DCF model with proper dividend policy accounting.

This enhanced DCF model addresses the fundamental flaw in traditional DCF where
dividend vs reinvestment policies are not properly valued. It uses the Dividend
Discount Model (DDM) combined with FCF analysis to properly value companies
based on their capital allocation strategies.

Key Improvements:
1. Separates dividend and growth components of value
2. Uses Free Cash Flow to Equity (FCFE) approach
3. Accounts for payout ratio and reinvestment opportunities
4. Provides separate valuations for dividend vs growth scenarios

Author: Enhanced for proper dividend treatment
"""

from typing import Dict, List, Optional

import numpy as np
import yfinance as yf

from .config.logging_config import (
    get_logger,
    log_data_fetch,
    log_error_with_context,
    log_valuation_result,
)
from .error_handling import create_error_context, handle_valuation_error
from .exceptions import InsufficientDataError, ModelNotSuitableError

logger = get_logger(__name__)


PROJECTION_YEARS = 10


def calculate_enhanced_dcf(
    ticker: str,
    fcf: Optional[float] = None,
    shares: Optional[float] = None,
    cash: Optional[float] = None,
    debt: Optional[float] = None,
    current_price: Optional[float] = None,
    dividend_rate: Optional[float] = None,
    payout_ratio: Optional[float] = None,
    roe: Optional[float] = None,
    growth_rates: Optional[List[float]] = None,
    discount_rate: float = 0.12,
    terminal_growth: float = 0.025,
    projection_years: int = PROJECTION_YEARS,
    use_normalized_fcf: bool = True,
    verbose: bool = True,
) -> Dict:
    """
    Enhanced DCF with proper dividend policy accounting.

    This model values companies by considering both dividend payments and
    reinvestment opportunities, providing a more accurate valuation that
    reflects different capital allocation strategies.

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
    dividend_rate : float, optional
        Annual dividend per share (will be fetched if None)
    payout_ratio : float, optional
        Dividend payout ratio (will be calculated if None)
    roe : float, optional
        Return on equity (will be fetched if None)
    growth_rates : List[float], optional
        Annual growth rates for projection (will be calculated if None)
    discount_rate : float
        Discount rate (cost of equity), default 0.12
    terminal_growth : float
        Terminal growth rate, default 0.025
    projection_years : int
        Number of years to project, default 10
    use_normalized_fcf : bool
        Whether to use normalized FCF from historical data, default True
    verbose : bool
        Whether to print detailed output, default True

    Returns
    -------
    Dict
        Comprehensive valuation results including dividend and growth components
    """
    # Create error context for comprehensive error handling
    create_error_context(ticker=ticker, model="Enhanced DCF", function_name="calculate_enhanced_dcf")

    try:
        stock = yf.Ticker(ticker)

        try:
            info = stock.info
        except Exception as e:
            info = {}
            log_data_fetch(logger, ticker, "market_data", False, error=str(e))
            if verbose:
                print(f"Warning: Unable to retrieve market data for {ticker}: {e}")

        # Fetch missing data
        if fcf is None:
            fcf = info.get("freeCashflow")

            # If FCF not in info, try to get it from cashflow statement (common for financial companies)
            if fcf is None:
                try:
                    cf = stock.cashflow
                    if not cf.empty and 'Free Cash Flow' in cf.index:
                        # Get most recent FCF value
                        fcf_values = cf.loc['Free Cash Flow'].dropna()
                        if not fcf_values.empty:
                            fcf = fcf_values.iloc[0]  # Most recent value
                            if verbose:
                                logger.info(f"Retrieved FCF from cashflow statement for {ticker}: ${fcf:,.0f}")
                except Exception as e:
                    if verbose:
                        logger.warning(f"Could not retrieve FCF from cashflow statement for {ticker}: {e}")

        if shares is None:
            shares = info.get("sharesOutstanding")
        if cash is None:
            cash = info.get("totalCash", 0)
        if debt is None:
            debt = info.get("totalDebt", 0)
        if current_price is None:
            current_price = info.get("currentPrice")
        if dividend_rate is None:
            dividend_rate = info.get("dividendRate", 0)
        if roe is None:
            roe = info.get("returnOnEquity")

        # Validate essential data with better error handling
        missing_data = []
        if fcf is None:
            missing_data.append("fcf")
        if shares is None:
            missing_data.append("shares")
        if current_price is None:
            missing_data.append("current_price")

        if missing_data:
            # For financial companies, try alternative approaches
            sector = info.get("sector", "").lower()
            if "financial" in sector:
                if verbose:
                    logger.warning(f"Enhanced DCF may not be suitable for financial company {ticker} ({sector}). Missing: {missing_data}")
                # Skip enhanced DCF for financials - they need different models
                raise ModelNotSuitableError(
                    "Enhanced DCF",
                    ticker,
                    f"Enhanced DCF not applicable to financial company ({sector}). Use bank-specific valuation models like P/B or RIM instead."
                )
            else:
                raise InsufficientDataError(ticker, missing_data)

        # Calculate payout ratio if not provided
        if payout_ratio is None and dividend_rate and shares:
            total_dividends = dividend_rate * shares
            if fcf > 0:
                payout_ratio = min(total_dividends / fcf, 1.0)  # Cap at 100%
            else:
                payout_ratio = 0.0
        elif payout_ratio is None:
            payout_ratio = 0.0

        # Check for Enhanced DCF model suitability
        if fcf <= 0:
            # Enhanced DCF requires positive FCF for dividend analysis
            raise ModelNotSuitableError(
                "Enhanced DCF",
                ticker,
                f"Negative FCF (${fcf:,.0f}) makes dividend-based valuation inappropriate. Use traditional DCF or other methods."
            )

        # Use normalized FCF if enabled
        base_fcf = _calculate_normalized_fcf(stock, fcf, use_normalized_fcf, verbose, ticker)

        # Calculate dividend and reinvestment metrics
        dividend_metrics = _calculate_dividend_metrics(
            base_fcf, shares, dividend_rate, payout_ratio, roe
        )

        # Determine growth rates based on reinvestment policy
        if growth_rates is None:
            growth_rates = _calculate_sustainable_growth_rates(dividend_metrics, info, projection_years)

        # Project future cash flows and dividends
        projections = _project_dividend_and_growth(
            base_fcf, dividend_metrics, growth_rates, projection_years
        )

        # Calculate present values
        valuation = _calculate_present_values(
            projections, discount_rate, terminal_growth, projection_years, cash, debt, shares
        )

        # Calculate margin of safety
        margin_of_safety = (valuation["fair_value_per_share"] - current_price) / current_price

        # Prepare comprehensive results
        results = {
            "ticker": ticker,
            "fair_value_per_share": valuation["fair_value_per_share"],
            "fair_value": valuation["fair_value_per_share"],  # Add compatibility with dashboard
            "current_price": current_price,
            "margin_of_safety": margin_of_safety,
            # Dividend-specific metrics
            "dividend_component_value": valuation["dividend_pv"] / shares,
            "growth_component_value": valuation["growth_pv"] / shares,
            "dividend_yield": dividend_rate / current_price if current_price > 0 else 0,
            "implied_terminal_yield": valuation.get("terminal_dividend_yield", 0),
            # Capital allocation analysis
            "payout_ratio": payout_ratio,
            "retention_ratio": 1 - payout_ratio,
            "reinvestment_efficiency": dividend_metrics.get("reinvestment_roic", 0),
            "sustainable_growth_rate": dividend_metrics.get("sustainable_growth", 0),
            # Traditional DCF components
            "enterprise_value": valuation["enterprise_value"],
            "terminal_value": valuation["terminal_value"],
            "terminal_value_pv": valuation["terminal_pv"],
            # Scenario analysis
            "high_dividend_scenario": valuation.get("high_dividend_value", 0) / shares,
            "high_growth_scenario": valuation.get("high_growth_value", 0) / shares,
            # Inputs and assumptions
            "inputs": {
                "base_fcf": base_fcf,
                "normalized_fcf_used": use_normalized_fcf,
                "shares": shares,
                "cash": cash,
                "debt": debt,
                "discount_rate": discount_rate,
                "terminal_growth": terminal_growth,
                "growth_rates": growth_rates,
            },
        }

        # Log the enhanced DCF valuation result
        log_valuation_result(
            logger,
            ticker,
            "Enhanced DCF",
            results['fair_value_per_share'],
            margin_of_safety=results['margin_of_safety'],
            dividend_yield=results['dividend_yield'],
            sustainable_growth_rate=results['sustainable_growth_rate']
        )

        if verbose:
            _print_enhanced_dcf_summary(results, ticker)

        return results

    except Exception as e:
        # Handle any unexpected errors with comprehensive error context
        error_info = handle_valuation_error(e, ticker, "Enhanced DCF")

        # Log the error with full context
        log_error_with_context(
            logger,
            error_info.technical_message,
            ticker=ticker,
            model="Enhanced DCF",
            error_id=error_info.error_id,
            user_message=error_info.user_message
        )

        # Re-raise the original exception to maintain existing behavior
        raise


def _calculate_normalized_fcf(stock, fcf: float, use_normalized: bool, verbose: bool, ticker: str = "UNKNOWN") -> float:
    """Calculate normalized FCF from historical data if requested."""
    if not use_normalized:
        return fcf

    try:
        cf_df = stock.cashflow
        if not cf_df.empty:
            if "Free Cash Flow" in cf_df.index:
                normalized = cf_df.loc["Free Cash Flow"].mean()
            else:
                operating_cf = cf_df.loc["Total Cash From Operating Activities"]
                capex = cf_df.loc["Capital Expenditures"]
                normalized = (operating_cf - capex).mean()

            if not np.isnan(normalized) and normalized != 0:
                if verbose:
                    print(f"Using normalized FCF: ${normalized:,.0f} vs TTM: ${fcf:,.0f}")
                return normalized
    except Exception as e:
        logger.warning(
            f"Could not calculate normalized FCF for {ticker}",
            extra={"ticker": ticker, "error": str(e), "fallback_fcf": fcf}
        )
        if verbose:
            print(f"Could not calculate normalized FCF: {e}")

    return fcf


def _calculate_dividend_metrics(
    fcf: float, shares: float, dividend_rate: float, payout_ratio: float, roe: Optional[float]
) -> Dict:
    """Calculate comprehensive dividend and reinvestment metrics."""
    metrics = {}

    # Basic dividend metrics
    total_dividends = dividend_rate * shares if dividend_rate else 0
    reinvested_fcf = fcf - total_dividends

    metrics["total_dividends"] = total_dividends
    metrics["reinvested_fcf"] = reinvested_fcf
    metrics["dividend_per_share"] = dividend_rate
    metrics["payout_ratio"] = payout_ratio
    metrics["retention_ratio"] = 1 - payout_ratio

    # Sustainable growth calculation
    # Growth = ROE × Retention Ratio (for equity-financed growth)
    if roe and roe > 0:
        sustainable_growth = roe * (1 - payout_ratio)
        metrics["sustainable_growth"] = min(sustainable_growth, 0.25)  # Cap at 25%

        # Use a more conservative reinvestment ROIC estimate
        # High ROE companies often can't sustain those returns on incremental capital
        if reinvested_fcf > 0:
            # Cap reinvestment returns at a reasonable level (15-20% for excellent companies)
            conservative_roic = min(roe * 0.15, 0.20)  # 15% of ROE, capped at 20%
            metrics["reinvestment_roic"] = conservative_roic
        else:
            metrics["reinvestment_roic"] = 0
    else:
        # Fallback calculation based on FCF efficiency
        if reinvested_fcf > 0 and fcf > 0:
            # Assume reinvestment generates returns at cost of capital
            metrics["sustainable_growth"] = min(reinvested_fcf / fcf * 0.12, 0.15)
            metrics["reinvestment_roic"] = 0.12
        else:
            metrics["sustainable_growth"] = 0.02  # Minimal growth
            metrics["reinvestment_roic"] = 0.02

    return metrics


def _calculate_sustainable_growth_rates(
    dividend_metrics: Dict, info: Dict, projection_years: int
) -> List[float]:
    """Calculate growth rates based on reinvestment policy."""
    sustainable_growth = dividend_metrics.get("sustainable_growth", 0.05)

    # Start with sustainable growth and gradually decline
    growth_rates = []
    for i in range(projection_years):
        # Decline growth over time as opportunities diminish
        decline_factor = 1 - (i * 0.05)  # 5% decline per year
        year_growth = sustainable_growth * decline_factor

        # Floor at 2% (inflation baseline)
        year_growth = max(year_growth, 0.02)
        growth_rates.append(year_growth)

    return growth_rates


def _project_dividend_and_growth(
    base_fcf: float, dividend_metrics: Dict, growth_rates: List[float], projection_years: int
) -> Dict:
    """Project future dividends and cash flows based on capital allocation."""
    projections = {
        "fcf_projections": [],
        "dividend_projections": [],
        "reinvestment_projections": [],
        "years": list(range(1, projection_years + 1)),
    }

    current_fcf = base_fcf
    current_dividend_per_share = dividend_metrics["dividend_per_share"]
    payout_ratio = dividend_metrics["payout_ratio"]

    for i, growth_rate in enumerate(growth_rates):
        # Grow FCF
        current_fcf *= 1 + growth_rate
        projections["fcf_projections"].append(current_fcf)

        # Calculate dividends based on payout ratio
        total_dividends = current_fcf * payout_ratio
        projections["dividend_projections"].append(total_dividends)

        # Calculate reinvestment
        reinvestment = current_fcf * (1 - payout_ratio)
        projections["reinvestment_projections"].append(reinvestment)

        # Grow dividend per share (assuming constant share count)
        current_dividend_per_share *= 1 + growth_rate * payout_ratio

    projections["final_dividend_per_share"] = current_dividend_per_share

    return projections


def _calculate_present_values(
    projections: Dict,
    discount_rate: float,
    terminal_growth: float,
    projection_years: int,
    cash: float,
    debt: float,
    shares: float,
) -> Dict:
    """Calculate present values of dividend and growth components."""

    # Present value of projected dividends
    dividend_pv = sum(
        div / (1 + discount_rate) ** (i + 1)
        for i, div in enumerate(projections["dividend_projections"])
    )

    # Present value of projected FCF (for growth component)
    fcf_pv = sum(
        fcf / (1 + discount_rate) ** (i + 1) for i, fcf in enumerate(projections["fcf_projections"])
    )

    # Terminal value using Gordon Growth Model
    final_fcf = projections["fcf_projections"][-1]
    terminal_fcf = final_fcf * (1 + terminal_growth)
    terminal_value = terminal_fcf / (discount_rate - terminal_growth)
    terminal_pv = terminal_value / (1 + discount_rate) ** projection_years

    # Terminal dividend value
    final_dividend = projections["dividend_projections"][-1] * (1 + terminal_growth)
    terminal_dividend_value = final_dividend / (discount_rate - terminal_growth)
    terminal_dividend_pv = terminal_dividend_value / (1 + discount_rate) ** projection_years

    # Enterprise value and equity value
    enterprise_value = fcf_pv + terminal_pv
    equity_value = enterprise_value - debt + cash

    # Separate dividend value component
    total_dividend_value = dividend_pv + terminal_dividend_pv
    growth_value = equity_value - total_dividend_value

    # Fair value per share
    fair_value_per_share = equity_value / shares

    return {
        "dividend_pv": dividend_pv,
        "terminal_dividend_pv": terminal_dividend_pv,
        "total_dividend_value": total_dividend_value,
        "growth_pv": growth_value,
        "enterprise_value": enterprise_value,
        "equity_value": equity_value,
        "terminal_value": terminal_value,
        "terminal_pv": terminal_pv,
        "fair_value_per_share": fair_value_per_share,
        "terminal_dividend_yield": (final_dividend / shares) / fair_value_per_share,
    }


def _print_enhanced_dcf_summary(results: Dict, ticker: str) -> None:
    """Print comprehensive DCF analysis with dividend breakdown."""
    print(f"\n{'='*60}")
    print(f"ENHANCED DCF VALUATION - {ticker}")
    print(f"{'='*60}")

    # Price and valuation summary
    print("\n📊 VALUATION SUMMARY")
    print(f"Current Price:           ${results['current_price']:>10,.2f}")
    print(f"Fair Value per Share:    ${results['fair_value_per_share']:>10,.2f}")
    print(f"Margin of Safety:        {results['margin_of_safety']:>10.1%}")

    # Value component breakdown
    print("\n💰 VALUE COMPONENTS")
    print(
        f"Dividend Component:      ${results['dividend_component_value']:>10,.2f} ({results['dividend_component_value']/results['fair_value_per_share']:.1%})"
    )
    print(
        f"Growth Component:        ${results['growth_component_value']:>10,.2f} ({results['growth_component_value']/results['fair_value_per_share']:.1%})"
    )

    # Dividend analysis
    print("\n💸 DIVIDEND ANALYSIS")
    print(f"Current Dividend Yield:  {results['dividend_yield']:>10.2%}")
    print(f"Payout Ratio:            {results['payout_ratio']:>10.1%}")
    print(f"Retention Ratio:         {results['retention_ratio']:>10.1%}")
    print(f"Implied Terminal Yield:  {results['implied_terminal_yield']:>10.2%}")

    # Capital allocation efficiency
    print("\n🏭 CAPITAL ALLOCATION")
    print(f"Sustainable Growth:      {results['sustainable_growth_rate']:>10.1%}")
    print(f"Reinvestment ROIC:       {results['reinvestment_efficiency']:>10.1%}")

    # Key assumptions
    print("\n📋 KEY ASSUMPTIONS")
    print(f"Discount Rate:           {results['inputs']['discount_rate']:>10.1%}")
    print(f"Terminal Growth:         {results['inputs']['terminal_growth']:>10.1%}")
    print(f"Base FCF:                ${results['inputs']['base_fcf']:>10,.0f}")

    print(f"\n{'='*60}")


# Convenience function for backward compatibility with original DCF
def calculate_dcf_with_dividends(ticker: str, **kwargs) -> Dict:
    """
    Enhanced DCF calculation with dividend policy awareness.

    This is a drop-in replacement for the original calculate_dcf function
    that provides enhanced dividend treatment while maintaining compatibility.
    """
    return calculate_enhanced_dcf(ticker, **kwargs)
