from typing import Dict, Optional

from ..config.schema import QualityThresholds


def calculate_roic(data: Dict) -> float:
    """Calculate Return on Invested Capital."""
    # ROIC approximation using available data
    # ROIC = NOPAT / Invested Capital
    # Approximation: ROE adjusted for leverage

    roe = data.get("return_on_equity", 0)
    if not roe or roe <= 0:
        return 0.0

    debt_ratio = data.get("debt_to_equity", 0)
    if debt_ratio and debt_ratio > 0:
        # ROIC proxy: ROE / (1 + D/E) — unlevered return on capital
        roic = roe / (1 + debt_ratio)
    else:
        roic = roe  # If no debt, ROIC ≈ ROE

    return max(0.0, roic)


def calculate_interest_coverage(data: Dict) -> Optional[float]:
    """Calculate interest coverage ratio (EBIT / Interest Expense).

    Returns None when the actual data is unavailable rather than
    fabricating a proxy from unrelated metrics.
    """
    interest_coverage = data.get("interest_coverage")
    if interest_coverage and isinstance(interest_coverage, (int, float)):
        return interest_coverage
    return None


def assess_quality(data: Dict, thresholds: QualityThresholds) -> Dict:
    """Assess quality metrics for a single stock."""
    results = {
        "ticker": data.get("ticker", "N/A"),
        "quality_score": 0,
        "quality_flags": [],
        "quality_metrics": {},
    }

    # Calculate derived metrics
    roic = calculate_roic(data)
    roe = data.get("return_on_equity", 0) or 0
    current_ratio = data.get("current_ratio", 0) or 0
    debt_equity = data.get("debt_to_equity", 0) or 0
    interest_coverage = calculate_interest_coverage(data)

    results["quality_metrics"] = {
        "roic": roic,
        "roe": roe,
        "current_ratio": current_ratio,
        "debt_to_equity": debt_equity,
        "interest_coverage": interest_coverage,
    }

    # Continuous scoring: each component contributes 0.0-1.0, scaled to 0-100
    component_scores = []

    # ROIC scoring — linear from 0 (ROIC<=0) to 1 (ROIC>=threshold)
    if thresholds.min_roic is not None:
        t = thresholds.min_roic
        s = min(1.0, max(0.0, roic / t)) if t > 0 else (1.0 if roic >= t else 0.0)
        component_scores.append(s)
        if roic < t:
            results['quality_flags'].append(
                f'ROIC {roic:.1%} below threshold {t:.1%}'
            )

    # ROE scoring — linear from 0 (ROE<=0) to 1 (ROE>=threshold)
    if thresholds.min_roe is not None:
        t = thresholds.min_roe
        s = min(1.0, max(0.0, roe / t)) if t > 0 else (1.0 if roe >= t else 0.0)
        component_scores.append(s)
        if roe < t:
            results['quality_flags'].append(
                f'ROE {roe:.1%} below threshold {t:.1%}'
            )

    # Current ratio scoring — linear from 0 (ratio<=0) to 1 (ratio>=threshold)
    if thresholds.min_current_ratio is not None:
        t = thresholds.min_current_ratio
        s = min(1.0, max(0.0, current_ratio / t)) if t > 0 else (
            1.0 if current_ratio >= t else 0.0
        )
        component_scores.append(s)
        if current_ratio < t:
            results['quality_flags'].append(
                f'Current ratio {current_ratio:.2f} below threshold {t:.2f}'
            )

    # Debt/equity scoring (inverse — lower is better)
    # Linear from 1 (debt_equity<=0) to 0 (debt_equity>=2*threshold)
    if thresholds.max_debt_equity is not None:
        t = thresholds.max_debt_equity
        upper = 2.0 * t if t > 0 else 1.0
        s = min(1.0, max(0.0, 1.0 - debt_equity / upper)) if upper > 0 else (
            1.0 if debt_equity <= t else 0.0
        )
        component_scores.append(s)
        if debt_equity > t:
            results['quality_flags'].append(
                f'Debt/Equity {debt_equity:.2f} above threshold {t:.2f}'
            )

    # Interest coverage scoring — linear from 0 (coverage<=0) to 1 (coverage>=threshold)
    if thresholds.min_interest_coverage is not None and interest_coverage is not None:
        t = thresholds.min_interest_coverage
        s = min(1.0, max(0.0, interest_coverage / t)) if t > 0 else (
            1.0 if interest_coverage >= t else 0.0
        )
        component_scores.append(s)
        if interest_coverage < t:
            results['quality_flags'].append(
                f'Interest coverage {interest_coverage:.1f} below threshold {t:.1f}'
            )

    # Calculate final quality score (0-100 scale)
    if component_scores:
        results['quality_score'] = (sum(component_scores) / len(component_scores)) * 100
    else:
        results['quality_score'] = 0

    return results


def screen_quality(stocks_data: list[Dict], thresholds: QualityThresholds) -> list[Dict]:
    """Screen multiple stocks for quality criteria."""
    results = []

    for stock_data in stocks_data:
        quality_result = assess_quality(stock_data, thresholds)
        results.append(quality_result)

    return results


def apply_quality_filters(
    stocks_data: list[Dict], thresholds: QualityThresholds, min_quality_score: float = 60.0
) -> list[Dict]:
    """Filter stocks that meet minimum quality requirements."""
    quality_results = screen_quality(stocks_data, thresholds)

    # Filter by minimum quality score
    filtered = [
        result for result in quality_results if result["quality_score"] >= min_quality_score
    ]

    return filtered


def rank_by_quality(stocks_data: list[Dict], thresholds: QualityThresholds) -> list[Dict]:
    """Rank stocks by quality score (highest first)."""
    quality_results = screen_quality(stocks_data, thresholds)

    return sorted(quality_results, key=lambda x: x["quality_score"], reverse=True)
