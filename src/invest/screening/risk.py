from typing import Dict

from ..config.schema import RiskThresholds


def calculate_financial_risk(data: Dict) -> Dict:
    """Calculate financial risk metrics."""
    debt_equity = data.get("debt_to_equity", 0) or 0
    current_ratio = data.get("current_ratio", 0) or 0
    sector = data.get('sector', '')

    # Financial risk score (0-100, lower is less risky)
    financial_risk = 0

    # Financials (banks, insurance) naturally carry high D/E (10-15x);
    # penalising them on the same scale as industrials double-counts risk
    # already captured by the cyclical-sector penalty in business_risk.
    financial_sectors = ['Financials']

    if sector in financial_sectors:
        # Sector-appropriate D/E thresholds for financials
        if debt_equity > 20.0:
            financial_risk += 40
        elif debt_equity > 15.0:
            financial_risk += 25
        elif debt_equity > 10.0:
            financial_risk += 10
    else:
        # Debt risk (debt_equity is a ratio, e.g. 0.93 = 93%)
        if debt_equity > 1.0:  # Very high debt
            financial_risk += 40
        elif debt_equity > 0.5:  # High debt
            financial_risk += 25
        elif debt_equity > 0.25:  # Moderate debt
            financial_risk += 10

    # Liquidity risk
    if current_ratio < 0.8:  # Poor liquidity
        financial_risk += 30
    elif current_ratio < 1.2:  # Below comfortable liquidity
        financial_risk += 15
    elif current_ratio < 1.5:  # Adequate liquidity
        financial_risk += 5

    # Sector-appropriate debt risk labels
    if sector in financial_sectors:
        debt_risk_level = (
            'high' if debt_equity > 15.0
            else 'moderate' if debt_equity > 10.0
            else 'low'
        )
    else:
        debt_risk_level = (
            'high' if debt_equity > 0.5
            else 'moderate' if debt_equity > 0.25
            else 'low'
        )

    return {
        "financial_risk_score": min(100, financial_risk),
        "debt_risk_level": debt_risk_level,
        "liquidity_risk_level": "high"
        if current_ratio < 1.0
        else "moderate"
        if current_ratio < 1.5
        else "low",
    }


def calculate_market_risk(data: Dict) -> Dict:
    """Calculate market risk metrics."""
    # Beta (market risk) - not always available in basic Yahoo data
    # For now, estimate based on sector and size

    sector = data.get("sector", "")
    market_cap = data.get("market_cap", 0) or 0

    # Use actual beta from data if available (yfinance provides it)
    actual_beta = data.get("beta")
    if actual_beta and isinstance(actual_beta, (int, float)) and actual_beta > 0:
        estimated_beta = actual_beta
    else:
        # Fall back to sector-based estimate
        sector_betas = {
            "Technology": 1.3,
            "Consumer Discretionary": 1.2,
            "Financials": 1.4,
            "Healthcare": 1.0,
            "Energy": 1.5,
            "Materials": 1.3,
            "Industrials": 1.1,
            "Consumer Staples": 0.7,
            "Utilities": 0.6,
            "Real Estate": 0.9,
            "Communication Services": 1.2,
        }

        estimated_beta = sector_betas.get(sector, 1.0)

        # Adjust for size (smaller companies typically more volatile)
        if market_cap > 0:
            if market_cap < 2e9:  # Small cap
                estimated_beta *= 1.2
            elif market_cap > 200e9:  # Large cap
                estimated_beta *= 0.9

    return {
        "estimated_beta": estimated_beta,
        "market_risk_level": "high"
        if estimated_beta > 1.5
        else "moderate"
        if estimated_beta > 1.2
        else "low",
    }


def calculate_business_risk(data: Dict) -> Dict:
    """Calculate business/operational risk."""
    sector = data.get("sector", "")
    roe = data.get("return_on_equity", 0) or 0
    revenue_growth = data.get("revenue_growth", 0) or 0

    # Cyclical sectors have higher business risk
    cyclical_sectors = [
        "Energy",
        "Materials",
        "Industrials",
        "Consumer Discretionary",
        "Financials",
    ]

    defensive_sectors = ["Consumer Staples", "Utilities", "Healthcare"]

    business_risk = 0

    if sector in cyclical_sectors:
        business_risk += 30
    elif sector in defensive_sectors:
        business_risk += 10
    else:
        business_risk += 20

    # Profitability stability (lower ROE = higher risk)
    if roe < 0.05:  # Very low profitability
        business_risk += 25
    elif roe < 0.10:  # Low profitability
        business_risk += 15
    elif roe < 0.15:  # Moderate profitability
        business_risk += 5

    # Revenue volatility (using growth as proxy)
    if abs(revenue_growth) > 0.30:  # Very volatile
        business_risk += 20
    elif abs(revenue_growth) > 0.15:  # Moderately volatile
        business_risk += 10

    return {
        "business_risk_score": min(100, business_risk),
        "sector_risk_level": "high"
        if sector in cyclical_sectors
        else "low"
        if sector in defensive_sectors
        else "moderate",
        "cyclical": sector in cyclical_sectors,
    }


def assess_risk(data: Dict, thresholds: RiskThresholds) -> Dict:
    """Comprehensive risk assessment for a single stock."""
    results = {
        "ticker": data.get("ticker", "N/A"),
        "overall_risk_score": 0,  # 0-100, higher is riskier
        "risk_flags": [],
        "risk_metrics": {},
    }

    # Calculate different types of risk
    financial_risk = calculate_financial_risk(data)
    market_risk = calculate_market_risk(data)
    business_risk = calculate_business_risk(data)

    results["risk_metrics"].update({**financial_risk, **market_risk, **business_risk})

    # Apply threshold checks
    estimated_beta = market_risk["estimated_beta"]
    current_ratio = data.get("current_ratio", 0) or 0

    # Beta check
    if thresholds.max_beta is not None:
        if estimated_beta > thresholds.max_beta:
            results["risk_flags"].append(
                f"Beta {estimated_beta:.2f} above threshold {thresholds.max_beta:.2f}"
            )

    # Liquidity check
    if thresholds.min_liquidity_ratio is not None:
        if current_ratio < thresholds.min_liquidity_ratio:
            results["risk_flags"].append(
                f"Liquidity ratio {current_ratio:.2f} below threshold {thresholds.min_liquidity_ratio:.2f}"
            )

    # Calculate overall risk score (weighted average)
    financial_weight = 0.4
    market_weight = 0.3
    business_weight = 0.3

    overall_risk = (
        financial_risk["financial_risk_score"] * financial_weight
        + (estimated_beta - 1.0) * 50 * market_weight  # Normalize beta to 0-100 scale
        + business_risk["business_risk_score"] * business_weight
    )

    results["overall_risk_score"] = max(0, min(100, overall_risk))

    # Risk level classification
    if results["overall_risk_score"] > 70:
        results["risk_level"] = "high"
    elif results["overall_risk_score"] > 40:
        results["risk_level"] = "moderate"
    else:
        results["risk_level"] = "low"

    return results


def screen_risk(stocks_data: list[Dict], thresholds: RiskThresholds) -> list[Dict]:
    """Screen multiple stocks for risk criteria."""
    results = []

    for stock_data in stocks_data:
        risk_result = assess_risk(stock_data, thresholds)
        results.append(risk_result)

    return results


def apply_risk_filters(
    stocks_data: list[Dict], thresholds: RiskThresholds, max_risk_score: float = 60.0
) -> list[Dict]:
    """Filter stocks that meet maximum risk requirements."""
    risk_results = screen_risk(stocks_data, thresholds)

    filtered = [result for result in risk_results if result["overall_risk_score"] <= max_risk_score]

    return filtered


def rank_by_risk(
    stocks_data: list[Dict], thresholds: RiskThresholds, ascending: bool = True
) -> list[Dict]:
    """Rank stocks by risk score (lowest first by default)."""
    risk_results = screen_risk(stocks_data, thresholds)

    return sorted(risk_results, key=lambda x: x["overall_risk_score"], reverse=not ascending)


def apply_cyclical_adjustments(stocks_data: list[Dict], thresholds: RiskThresholds) -> list[Dict]:
    """Apply adjustments for cyclical stocks if enabled."""
    if not thresholds.cyclical_adjustment:
        return stocks_data

    adjusted_data = []

    for stock_data in stocks_data:
        adjusted = stock_data.copy()
        sector = stock_data.get("sector", "")

        # Mark cyclical sectors for downstream consumers
        adjusted['is_cyclical'] = sector in [
            'Energy', 'Materials', 'Industrials', 'Consumer Discretionary',
        ]

        adjusted_data.append(adjusted)

    return adjusted_data
