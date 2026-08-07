"""
ETF valuation module.

Provides valuation metrics specific to ETFs including NAV analysis,
premium/discount calculations, and expense ratio impact.
"""

from typing import Dict, List, Optional

import numpy as np
import yfinance as yf


def calculate_etf_valuation(
    ticker: str,
    current_price: Optional[float] = None,
    nav: Optional[float] = None,
    expense_ratio: Optional[float] = None,
    holding_period_years: float = 5,
    expected_return: float = 0.08,
    verbose: bool = True,
) -> Dict:
    """
    Calculate ETF valuation metrics.

    Unlike stocks which use DCF, ETFs are valued based on:
    - NAV premium/discount
    - Expense ratio impact over time
    - Historical tracking performance
    - Relative valuation vs peers

    Parameters
    ----------
    ticker : str
        ETF ticker symbol
    current_price : float, optional
        Current market price (fetched if not provided)
    nav : float, optional
        Net Asset Value per share (fetched if not provided)
    expense_ratio : float, optional
        Annual expense ratio (fetched if not provided)
    holding_period_years : float
        Expected holding period for cost analysis
    expected_return : float
        Expected annual return for cost impact calculation
    verbose : bool
        Whether to print analysis details

    Returns
    -------
    Dict
        Valuation metrics including premium/discount, cost impact, fair value
    """
    # Fetch ETF data
    etf = yf.Ticker(ticker)
    info = etf.info

    # Get basic data
    if current_price is None:
        current_price = info.get("regularMarketPrice") or info.get("currentPrice")
    if nav is None:
        nav = info.get("navPrice")
    if expense_ratio is None:
        expense_ratio = info.get("annualReportExpenseRatio", 0)

    # Validate required data
    if current_price is None:
        raise ValueError(f"Could not fetch current price for {ticker}")

    # Calculate premium/discount to NAV
    if nav and nav > 0:
        premium_discount = ((current_price - nav) / nav) * 100
        premium_discount_dollar = current_price - nav
    else:
        # If NAV not available, assume trading at fair value
        nav = current_price
        premium_discount = 0
        premium_discount_dollar = 0

    # Calculate expense ratio impact over holding period
    # This shows how much the expense ratio will cost in dollar terms
    expense_cost_per_share = current_price * (1 - (1 - expense_ratio) ** holding_period_years)

    # Calculate the drag on returns
    gross_value = current_price * (1 + expected_return) ** holding_period_years
    net_value = (
        current_price * ((1 + expected_return) * (1 - expense_ratio)) ** holding_period_years
    )
    return_drag = gross_value - net_value
    return_drag_pct = (return_drag / gross_value) * 100 if gross_value > 0 else 0

    # Get historical performance metrics
    history = etf.history(period="5y")
    if not history.empty:
        # Calculate tracking volatility (standard deviation of daily returns)
        daily_returns = history["Close"].pct_change().dropna()
        volatility = daily_returns.std() * np.sqrt(252) * 100  # Annualized

        # Calculate average daily volume
        avg_volume = history["Volume"].mean()

        # Calculate bid-ask spread estimate (using high-low as proxy)
        avg_spread = ((history["High"] - history["Low"]) / history["Close"]).mean() * 100
    else:
        volatility = None
        avg_volume = None
        avg_spread = None

    # Adjust for reasonable premium/discount based on ETF type
    etf_category = info.get("category", "").lower()

    # Some ETFs typically trade at premiums (e.g., popular, liquid ETFs)
    # Others at discounts (e.g., international, less liquid)
    typical_premium = 0  # Default: should trade at NAV

    if "international" in etf_category or "emerging" in etf_category:
        typical_premium = -0.5  # Often trade at slight discount
    elif "bond" in etf_category or "treasury" in etf_category:
        typical_premium = 0.1  # Often trade at slight premium

    adjusted_fair_value = nav * (1 + typical_premium / 100) if nav else current_price

    # Calculate upside/downside
    upside_downside = (
        ((adjusted_fair_value - current_price) / current_price) * 100 if current_price > 0 else 0
    )

    # Scoring components for ETF attractiveness
    scores = {}

    # Premium/Discount Score (lower premium is better)
    if abs(premium_discount) < 0.1:
        scores["nav_score"] = 100
    elif abs(premium_discount) < 0.5:
        scores["nav_score"] = 80
    elif abs(premium_discount) < 1.0:
        scores["nav_score"] = 60
    elif abs(premium_discount) < 2.0:
        scores["nav_score"] = 40
    else:
        scores["nav_score"] = 20

    # Expense Ratio Score (lower is better)
    if expense_ratio < 0.001:  # Less than 0.1%
        scores["expense_score"] = 100
    elif expense_ratio < 0.002:  # Less than 0.2%
        scores["expense_score"] = 90
    elif expense_ratio < 0.005:  # Less than 0.5%
        scores["expense_score"] = 70
    elif expense_ratio < 0.01:  # Less than 1%
        scores["expense_score"] = 50
    else:
        scores["expense_score"] = 30

    # Liquidity Score (based on volume)
    if avg_volume and avg_volume > 10_000_000:
        scores["liquidity_score"] = 100
    elif avg_volume and avg_volume > 1_000_000:
        scores["liquidity_score"] = 80
    elif avg_volume and avg_volume > 100_000:
        scores["liquidity_score"] = 60
    else:
        scores["liquidity_score"] = 40

    # Overall composite score
    composite_score = (
        scores["nav_score"] * 0.4 + scores["expense_score"] * 0.4 + scores["liquidity_score"] * 0.2
    )

    # Build results
    results = {
        "ticker": ticker,
        "name": info.get("longName", ticker),
        "current_price": current_price,
        "nav": nav,
        "fair_value": adjusted_fair_value,
        "upside_downside": upside_downside,
        "premium_discount": premium_discount,
        "premium_discount_dollar": premium_discount_dollar,
        "expense_ratio": expense_ratio * 100,  # Convert to percentage
        "expense_cost_per_share": expense_cost_per_share,
        "return_drag": return_drag,
        "return_drag_pct": return_drag_pct,
        "volatility": volatility,
        "avg_volume": avg_volume,
        "avg_spread": avg_spread,
        "scores": scores,
        "composite_score": composite_score,
        "category": info.get("category", "Unknown"),
        "total_assets": info.get("totalAssets", 0),
        "yield": info.get("yield", 0) * 100 if info.get("yield") else 0,
    }

    if verbose:
        _print_etf_valuation(results)

    return results


def _print_etf_valuation(results: Dict) -> None:
    """Print ETF valuation analysis in a formatted way."""
    print(f"\n{'='*60}")
    print(f"ETF VALUATION ANALYSIS: {results['ticker']}")
    print(f"{'='*60}")
    print(f"Name: {results['name']}")
    print(f"Category: {results['category']}")

    print(f"\n{'='*60}")
    print("VALUATION METRICS")
    print(f"{'='*60}")
    print(f"Current Price:           ${results['current_price']:.2f}")
    print(f"Net Asset Value (NAV):   ${results['nav']:.2f}")
    print(
        f"Premium/Discount to NAV: {results['premium_discount']:+.2f}% (${results['premium_discount_dollar']:+.2f})"
    )
    print(f"Fair Value:              ${results['fair_value']:.2f}")
    print(f"Upside/Downside:         {results['upside_downside']:+.2f}%")

    print(f"\n{'='*60}")
    print("COST ANALYSIS")
    print(f"{'='*60}")
    print(f"Expense Ratio:           {results['expense_ratio']:.2f}%")
    print(f"5-Year Cost per Share:   ${results['expense_cost_per_share']:.2f}")
    print(
        f"Return Drag (5 years):   ${results['return_drag']:.2f} ({results['return_drag_pct']:.1f}%)"
    )

    print(f"\n{'='*60}")
    print("TRADING METRICS")
    print(f"{'='*60}")
    if results["volatility"]:
        print(f"Volatility (Annual):     {results['volatility']:.1f}%")
    if results["avg_volume"]:
        print(f"Avg Daily Volume:        {results['avg_volume']:,.0f}")
    if results["avg_spread"]:
        print(f"Avg Spread (High-Low):   {results['avg_spread']:.3f}%")
    if results["yield"] > 0:
        print(f"Distribution Yield:      {results['yield']:.2f}%")

    print(f"\n{'='*60}")
    print("SCORING")
    print(f"{'='*60}")
    print(f"NAV Score:               {results['scores']['nav_score']:.0f}/100")
    print(f"Expense Score:           {results['scores']['expense_score']:.0f}/100")
    print(f"Liquidity Score:         {results['scores']['liquidity_score']:.0f}/100")
    print(f"COMPOSITE SCORE:         {results['composite_score']:.0f}/100")

    # Investment recommendation
    print(f"\n{'='*60}")
    print("RECOMMENDATION")
    print(f"{'='*60}")

    if results["composite_score"] >= 80:
        recommendation = "STRONG BUY - Excellent ETF with low costs and good liquidity"
    elif results["composite_score"] >= 70:
        recommendation = "BUY - Good ETF with reasonable costs"
    elif results["composite_score"] >= 60:
        recommendation = "HOLD - Average ETF, consider alternatives"
    elif results["composite_score"] >= 50:
        recommendation = "WEAK HOLD - Below average, look for better options"
    else:
        recommendation = "AVOID - Poor metrics, high costs or low liquidity"

    print(recommendation)

    if abs(results["premium_discount"]) > 1:
        if results["premium_discount"] > 0:
            print("⚠️  Warning: Trading at significant premium to NAV")
        else:
            print("✓  Opportunity: Trading at discount to NAV")

    if results["expense_ratio"] > 0.5:
        print("⚠️  Warning: High expense ratio will erode returns")

    print(f"{'='*60}\n")


def compare_etfs(tickers: List[str], verbose: bool = True) -> Dict:
    """
    Compare multiple ETFs side by side.

    Parameters
    ----------
    tickers : List[str]
        List of ETF tickers to compare
    verbose : bool
        Whether to print comparison table

    Returns
    -------
    Dict
        Comparison data for all ETFs
    """
    results = {}

    for ticker in tickers:
        try:
            results[ticker] = calculate_etf_valuation(ticker, verbose=False)
        except Exception as e:
            print(f"Error analyzing {ticker}: {e}")
            continue

    if verbose and results:
        _print_etf_comparison(results)

    return results


def _print_etf_comparison(results: Dict) -> None:
    """Print ETF comparison table."""
    print(f"\n{'='*100}")
    print("ETF COMPARISON")
    print(f"{'='*100}")

    # Header
    print(
        f"{'Ticker':<8} {'Expense':<8} {'Prem/Disc':<10} {'Volume':<12} {'Score':<7} {'Category':<20}"
    )
    print(f"{'-'*8} {'-'*8} {'-'*10} {'-'*12} {'-'*7} {'-'*20}")

    # Sort by composite score
    sorted_etfs = sorted(results.items(), key=lambda x: x[1]["composite_score"], reverse=True)

    for ticker, data in sorted_etfs:
        expense = f"{data['expense_ratio']:.2f}%"
        prem_disc = f"{data['premium_discount']:+.2f}%"
        volume = f"{data['avg_volume']/1e6:.1f}M" if data["avg_volume"] else "N/A"
        score = f"{data['composite_score']:.0f}"
        category = data["category"][:20]

        print(f"{ticker:<8} {expense:<8} {prem_disc:<10} {volume:<12} {score:<7} {category:<20}")

    print(f"{'='*100}\n")
