from typing import Dict, Optional

from ..config.schema import GrowthThresholds


def calculate_historical_cagr(data: Dict, years: int = 5) -> Optional[float]:
    """Estimate sustainable revenue growth rate.

    Uses the trailing revenue growth with a mean-reversion haircut.
    Not a true multi-year CAGR — requires historical data for that.
    """
    revenue_growth = data.get("revenue_growth", 0)
    if not revenue_growth:
        return None

    # Haircut for mean reversion — current YoY growth overstates long-run trend
    return revenue_growth * 0.85


def calculate_fcf_growth(data: Dict) -> Optional[float]:
    """Calculate free cash flow growth (approximation)."""
    # Without historical FCF data, use earnings growth as proxy
    earnings_growth = data.get("earnings_growth", 0)
    if not earnings_growth:
        return None

    # FCF growth often more volatile than earnings growth
    return earnings_growth * 0.9


def calculate_book_value_growth(data: Dict) -> Optional[float]:
    """Calculate book value growth (approximation).

    Book value growth ≈ ROE * retention ratio.
    Uses actual payout ratio from data when available.
    """
    roe = data.get("return_on_equity", 0)
    if not roe or roe <= 0:
        return None

    # Use actual payout ratio if available, else default 40%
    payout_ratio = data.get("payoutRatio")
    if payout_ratio and isinstance(payout_ratio, (int, float)) and 0 <= payout_ratio <= 1:
        retention = 1 - payout_ratio
    else:
        retention = 0.6

    return roe * retention


def assess_growth(data: Dict, thresholds: GrowthThresholds) -> Dict:
    """Assess growth metrics for a single stock."""
    results = {
        "ticker": data.get("ticker", "N/A"),
        "growth_score": 0,
        "growth_flags": [],
        "growth_metrics": {},
    }

    # Get/calculate growth metrics
    revenue_growth = data.get("revenue_growth", 0) or 0
    earnings_growth = data.get("earnings_growth", 0) or 0
    fcf_growth = calculate_fcf_growth(data) or 0
    book_value_growth = calculate_book_value_growth(data) or 0
    historical_cagr = calculate_historical_cagr(data) or 0

    results["growth_metrics"] = {
        "revenue_growth": revenue_growth,
        "earnings_growth": earnings_growth,
        "fcf_growth": fcf_growth,
        "book_value_growth": book_value_growth,
        "historical_cagr": historical_cagr,
    }

    # Score each growth metric
    score = 0
    max_score = 0

    # Revenue growth scoring
    if thresholds.min_revenue_growth is not None:
        max_score += 1
        if revenue_growth >= thresholds.min_revenue_growth:
            score += 1
            # Bonus for exceptional revenue growth
            if revenue_growth > thresholds.min_revenue_growth * 2:
                score += 0.5
        else:
            results["growth_flags"].append(
                f"Revenue growth {revenue_growth:.1%} below threshold {thresholds.min_revenue_growth:.1%}"
            )

    # Earnings growth scoring
    if thresholds.min_earnings_growth is not None:
        max_score += 1
        if earnings_growth >= thresholds.min_earnings_growth:
            score += 1
            # Bonus for exceptional earnings growth
            if earnings_growth > thresholds.min_earnings_growth * 2:
                score += 0.5
        else:
            results["growth_flags"].append(
                f"Earnings growth {earnings_growth:.1%} below threshold {thresholds.min_earnings_growth:.1%}"
            )

    # FCF growth scoring
    if thresholds.min_fcf_growth is not None and fcf_growth:
        max_score += 1
        if fcf_growth >= thresholds.min_fcf_growth:
            score += 1
            if fcf_growth > thresholds.min_fcf_growth * 2:
                score += 0.5
        else:
            results["growth_flags"].append(
                f"FCF growth {fcf_growth:.1%} below threshold {thresholds.min_fcf_growth:.1%}"
            )

    # Book value growth scoring
    if thresholds.min_book_value_growth is not None and book_value_growth:
        max_score += 1
        if book_value_growth >= thresholds.min_book_value_growth:
            score += 1
            if book_value_growth > thresholds.min_book_value_growth * 1.5:
                score += 0.5
        else:
            results["growth_flags"].append(
                f"Book value growth {book_value_growth:.1%} below threshold {thresholds.min_book_value_growth:.1%}"
            )

    # Calculate final growth score (0-100 scale, accounting for bonuses)
    if max_score > 0:
        raw_score = min(score, max_score * 1.5)  # Cap bonuses
        results["growth_score"] = (raw_score / max_score) * 100
        results["growth_score"] = min(100, results["growth_score"])
    else:
        results["growth_score"] = 0

    # Add growth quality assessment
    results["growth_quality"] = assess_growth_quality(data, results["growth_metrics"])

    return results


def assess_growth_quality(data: Dict, growth_metrics: Dict) -> str:
    """Assess the quality/sustainability of growth."""
    revenue_growth = growth_metrics.get("revenue_growth", 0)
    earnings_growth = growth_metrics.get("earnings_growth", 0)

    # Check if earnings growth outpaces revenue growth (margin expansion)
    if earnings_growth > revenue_growth * 1.2:
        return "margin_expanding"
    elif earnings_growth < revenue_growth * 0.8:
        return "margin_contracting"
    else:
        return "stable_margins"


def screen_growth(stocks_data: list[Dict], thresholds: GrowthThresholds) -> list[Dict]:
    """Screen multiple stocks for growth criteria."""
    results = []

    for stock_data in stocks_data:
        growth_result = assess_growth(stock_data, thresholds)
        results.append(growth_result)

    return results


def apply_growth_filters(
    stocks_data: list[Dict], thresholds: GrowthThresholds, min_growth_score: float = 50.0
) -> list[Dict]:
    """Filter stocks that meet minimum growth requirements."""
    growth_results = screen_growth(stocks_data, thresholds)

    filtered = [result for result in growth_results if result["growth_score"] >= min_growth_score]

    return filtered


def rank_by_growth(stocks_data: list[Dict], thresholds: GrowthThresholds) -> list[Dict]:
    """Rank stocks by growth score (highest first)."""
    growth_results = screen_growth(stocks_data, thresholds)

    return sorted(growth_results, key=lambda x: x["growth_score"], reverse=True)


def identify_growth_at_reasonable_price(
    stocks_data: list[Dict], growth_thresholds: GrowthThresholds, max_pe_to_growth: float = 1.5
) -> list[Dict]:
    """Identify GARP (Growth At Reasonable Price) opportunities."""
    growth_results = screen_growth(stocks_data, growth_thresholds)

    garp_candidates = []

    for result in growth_results:
        # Get the original stock data to check valuation
        ticker = result["ticker"]
        stock_data = next((s for s in stocks_data if s.get("ticker") == ticker), None)

        if not stock_data:
            continue

        pe = stock_data.get("trailing_pe", 0)
        earnings_growth = result["growth_metrics"].get("earnings_growth", 0)

        if pe > 0 and earnings_growth > 0:
            # Calculate PEG ratio (P/E to Growth)
            peg_ratio = pe / (earnings_growth * 100)  # Convert growth to percentage

            if peg_ratio <= max_pe_to_growth and result["growth_score"] >= 60:
                result["peg_ratio"] = peg_ratio
                result["garp_candidate"] = True
                garp_candidates.append(result)
            else:
                result["peg_ratio"] = peg_ratio
                result["garp_candidate"] = False

    return garp_candidates
