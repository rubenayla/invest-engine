from typing import Dict, Optional

from ..config.schema import ValueThresholds


def calculate_ev_ebit(data: Dict) -> Optional[float]:
    """Calculate EV/EBIT ratio from data if available, else None."""
    # Only return a value if we have real EV/EBIT data (not a proxy)
    return data.get("ev_to_ebit")


def calculate_p_fcf(data: Dict) -> Optional[float]:
    """Calculate Price/Free Cash Flow ratio from data if available, else None."""
    # Only return a value if we have real P/FCF data (not a proxy)
    price = data.get("current_price") or data.get("currentPrice")
    fcf_per_share = data.get("fcf_per_share")
    if price and fcf_per_share and fcf_per_share > 0:
        return price / fcf_per_share
    return None


def assess_value(data: Dict, thresholds: ValueThresholds) -> Dict:
    """Assess value metrics for a single stock."""
    results = {
        "ticker": data.get("ticker", "N/A"),
        "value_score": 0,
        "value_flags": [],
        "value_metrics": {},
    }

    # Get/calculate value metrics
    pe = data.get("trailing_pe", 0) or 0
    pb = data.get("price_to_book", 0) or 0
    ev_ebitda = data.get("ev_to_ebitda", 0) or 0
    ev_ebit = calculate_ev_ebit(data) or 0
    p_fcf = calculate_p_fcf(data) or 0

    results["value_metrics"] = {
        "pe_ratio": pe,
        "pb_ratio": pb,
        "ev_ebitda": ev_ebitda,
        "ev_ebit": ev_ebit,
        "p_fcf": p_fcf,
    }

    # Score each value metric (lower ratios = higher scores)
    score = 0
    max_score = 0

    # P/E scoring (lower is better)
    if thresholds.max_pe is not None and pe > 0:
        max_score += 1
        if pe <= thresholds.max_pe:
            score += 1
            # Bonus for very attractive P/E
            if pe < thresholds.max_pe * 0.6:
                score += 0.5
        else:
            results["value_flags"].append(f"P/E {pe:.1f} above threshold {thresholds.max_pe:.1f}")

    # P/B scoring (lower is better)
    if thresholds.max_pb is not None and pb > 0:
        max_score += 1
        if pb <= thresholds.max_pb:
            score += 1
            # Bonus for very attractive P/B
            if pb < thresholds.max_pb * 0.7:
                score += 0.5
        else:
            results["value_flags"].append(f"P/B {pb:.2f} above threshold {thresholds.max_pb:.2f}")

    # EV/EBITDA scoring (lower is better)
    if thresholds.max_ev_ebitda is not None and ev_ebitda > 0:
        max_score += 1
        if ev_ebitda <= thresholds.max_ev_ebitda:
            score += 1
            if ev_ebitda < thresholds.max_ev_ebitda * 0.7:
                score += 0.5
        else:
            results["value_flags"].append(
                f"EV/EBITDA {ev_ebitda:.1f} above threshold {thresholds.max_ev_ebitda:.1f}"
            )

    # EV/EBIT scoring (lower is better)
    if thresholds.max_ev_ebit is not None and ev_ebit and ev_ebit > 0:
        max_score += 1
        if ev_ebit <= thresholds.max_ev_ebit:
            score += 1
            if ev_ebit < thresholds.max_ev_ebit * 0.7:
                score += 0.5
        else:
            results["value_flags"].append(
                f"EV/EBIT {ev_ebit:.1f} above threshold {thresholds.max_ev_ebit:.1f}"
            )

    # P/FCF scoring (lower is better)
    if thresholds.max_p_fcf is not None and p_fcf and p_fcf > 0:
        max_score += 1
        if p_fcf <= thresholds.max_p_fcf:
            score += 1
            if p_fcf < thresholds.max_p_fcf * 0.7:
                score += 0.5
        else:
            results["value_flags"].append(
                f"P/FCF {p_fcf:.1f} above threshold {thresholds.max_p_fcf:.1f}"
            )

    # Calculate final value score (0-100 scale, accounting for bonuses)
    if max_score > 0:
        # Cap the score at max_score * 1.5 to account for bonuses
        raw_score = min(score, max_score * 1.5)
        results["value_score"] = (raw_score / max_score) * 100
        results["value_score"] = min(100, results["value_score"])  # Cap at 100
    else:
        results["value_score"] = 0

    return results


def screen_value(stocks_data: list[Dict], thresholds: ValueThresholds) -> list[Dict]:
    """Screen multiple stocks for value criteria."""
    results = []

    for stock_data in stocks_data:
        value_result = assess_value(stock_data, thresholds)
        results.append(value_result)

    return results


def apply_value_filters(
    stocks_data: list[Dict], thresholds: ValueThresholds, min_value_score: float = 50.0
) -> list[Dict]:
    """Filter stocks that meet minimum value requirements."""
    value_results = screen_value(stocks_data, thresholds)

    # Filter by minimum value score
    filtered = [result for result in value_results if result["value_score"] >= min_value_score]

    return filtered


def rank_by_value(stocks_data: list[Dict], thresholds: ValueThresholds) -> list[Dict]:
    """Rank stocks by value score (highest first)."""
    value_results = screen_value(stocks_data, thresholds)

    return sorted(value_results, key=lambda x: x["value_score"], reverse=True)


def identify_deep_value(stocks_data: list[Dict], thresholds: ValueThresholds) -> list[Dict]:
    """Identify potential deep value opportunities."""
    value_results = screen_value(stocks_data, thresholds)

    # Deep value criteria: high value score + multiple attractive ratios
    deep_value = []

    for result in value_results:
        if result["value_score"] >= 80:  # High value score
            metrics = result["value_metrics"]
            attractive_ratios = 0

            # Count how many ratios are in attractive territory
            if (
                thresholds.max_pe
                and metrics["pe_ratio"] > 0
                and metrics["pe_ratio"] < thresholds.max_pe * 0.6
            ):
                attractive_ratios += 1
            if (
                thresholds.max_pb
                and metrics["pb_ratio"] > 0
                and metrics["pb_ratio"] < thresholds.max_pb * 0.7
            ):
                attractive_ratios += 1
            if (
                thresholds.max_ev_ebitda
                and metrics["ev_ebitda"] > 0
                and metrics["ev_ebitda"] < thresholds.max_ev_ebitda * 0.7
            ):
                attractive_ratios += 1

            # Require at least 2 attractive ratios for deep value classification
            if attractive_ratios >= 2:
                result["deep_value"] = True
                deep_value.append(result)
            else:
                result["deep_value"] = False

    return deep_value
