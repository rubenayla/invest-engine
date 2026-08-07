"""
Claude Desktop tools for portfolio construction and analysis.

These tools help Claude build and analyze investment portfolios based on
systematic screening results and additional constraints.
"""

import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from invest.data.yahoo import get_stock_data  # noqa: E402


def build_portfolio(
    candidate_stocks: List[str],
    portfolio_constraints: Optional[Dict] = None,
    optimization_objective: str = "balanced",
    max_positions: int = 10,
) -> Dict[str, Any]:
    """
    Build an optimized portfolio from candidate stocks.

    Args:
        candidate_stocks: List of ticker symbols to consider
        portfolio_constraints: Dict with constraints like max_single_position,
                              sector_limits, min_yield, etc.
        optimization_objective: 'balanced', 'growth', 'value', 'income', 'low_risk'
        max_positions: Maximum number of positions in portfolio

    Returns:
        Dict containing optimized portfolio allocation and analysis
    """
    if portfolio_constraints is None:
        portfolio_constraints = {
            "max_single_position": 0.15,  # 15% max per stock
            "min_position": 0.03,  # 3% minimum per stock
            "max_sector_allocation": 0.30,  # 30% max per sector
            "target_dividend_yield": None,  # No specific yield target
        }

    try:
        # Get data for all candidate stocks
        stock_data_dict = {}
        for ticker in candidate_stocks:
            stock_data = get_stock_data(ticker)
            if stock_data:
                stock_data_dict[ticker.upper()] = stock_data

        if not stock_data_dict:
            return {"error": "No valid stock data found for candidates"}

        # Score stocks based on optimization objective
        scored_stocks = _score_stocks_for_portfolio(stock_data_dict, optimization_objective)

        # Apply portfolio constraints and build allocation
        portfolio_allocation = _optimize_portfolio_allocation(
            scored_stocks, portfolio_constraints, max_positions
        )

        # Calculate portfolio metrics
        portfolio_metrics = _calculate_portfolio_metrics(portfolio_allocation, stock_data_dict)

        # Generate portfolio analysis
        portfolio_analysis = {
            "portfolio_objective": optimization_objective,
            "creation_date": datetime.now().isoformat(),
            "total_positions": len(portfolio_allocation),
            "allocation": portfolio_allocation,
            "portfolio_metrics": portfolio_metrics,
            "constraints_applied": portfolio_constraints,
            "risk_analysis": _analyze_portfolio_risk(portfolio_allocation, stock_data_dict),
            "sector_diversification": _analyze_sector_diversification(
                portfolio_allocation, stock_data_dict
            ),
            "rebalancing_suggestions": _generate_rebalancing_suggestions(
                portfolio_allocation, stock_data_dict
            ),
        }

        return portfolio_analysis

    except Exception as e:
        return {
            "error": str(e),
            "message": f"Failed to build portfolio from {len(candidate_stocks)} candidates",
        }


def analyze_portfolio_risk(
    portfolio_tickers: List[str],
    portfolio_weights: Optional[List[float]] = None,
    risk_factors: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Analyze risk characteristics of a portfolio.

    Args:
        portfolio_tickers: List of tickers in the portfolio
        portfolio_weights: List of weights (if None, assumes equal weighting)
        risk_factors: Risk factors to analyze ['sector', 'size', 'geography', 'style']

    Returns:
        Dict containing comprehensive risk analysis
    """
    if portfolio_weights is None:
        portfolio_weights = [1.0 / len(portfolio_tickers)] * len(portfolio_tickers)

    if risk_factors is None:
        risk_factors = ["sector", "size", "style", "financial_health"]

    try:
        # Get data for all portfolio stocks
        portfolio_data = {}
        for ticker in portfolio_tickers:
            stock_data = get_stock_data(ticker)
            if stock_data:
                portfolio_data[ticker.upper()] = stock_data

        risk_analysis = {
            "portfolio_tickers": [t.upper() for t in portfolio_tickers],
            "portfolio_weights": portfolio_weights,
            "analysis_date": datetime.now().isoformat(),
            "risk_factors_analyzed": risk_factors,
        }

        if "sector" in risk_factors:
            risk_analysis["sector_risk"] = _analyze_sector_concentration(
                portfolio_data, portfolio_weights
            )

        if "size" in risk_factors:
            risk_analysis["size_risk"] = _analyze_size_concentration(
                portfolio_data, portfolio_weights
            )

        if "style" in risk_factors:
            risk_analysis["style_risk"] = _analyze_style_concentration(
                portfolio_data, portfolio_weights
            )

        if "financial_health" in risk_factors:
            risk_analysis["financial_health_risk"] = _analyze_financial_health_risk(
                portfolio_data, portfolio_weights
            )

        # Overall risk assessment
        risk_analysis["overall_risk_assessment"] = _assess_overall_portfolio_risk(risk_analysis)

        return risk_analysis

    except Exception as e:
        return {
            "error": str(e),
            "message": f"Failed to analyze portfolio risk for {len(portfolio_tickers)} positions",
        }


def optimize_allocation(
    current_portfolio: Dict[str, float],
    target_allocation: Dict[str, float],
    optimization_constraints: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    Optimize portfolio allocation to move from current to target weights.

    Args:
        current_portfolio: Dict of {ticker: current_weight}
        target_allocation: Dict of {ticker: target_weight}
        optimization_constraints: Trading constraints (min_trade_size, max_turnover, etc.)

    Returns:
        Dict containing rebalancing recommendations
    """
    if optimization_constraints is None:
        optimization_constraints = {
            "min_trade_size": 0.01,  # 1% minimum trade
            "max_turnover": 0.50,  # 50% max turnover
            "transaction_cost": 0.001,  # 0.1% transaction cost estimate
        }

    try:
        rebalancing_plan = {
            "current_portfolio": current_portfolio,
            "target_allocation": target_allocation,
            "optimization_date": datetime.now().isoformat(),
            "constraints": optimization_constraints,
            "trades_required": [],
            "total_turnover": 0,
            "estimated_transaction_costs": 0,
        }

        # Calculate required trades
        all_tickers = set(list(current_portfolio.keys()) + list(target_allocation.keys()))

        for ticker in all_tickers:
            current_weight = current_portfolio.get(ticker, 0)
            target_weight = target_allocation.get(ticker, 0)
            trade_size = target_weight - current_weight

            if abs(trade_size) >= optimization_constraints["min_trade_size"]:
                trade_action = "BUY" if trade_size > 0 else "SELL"

                rebalancing_plan["trades_required"].append(
                    {
                        "ticker": ticker,
                        "action": trade_action,
                        "current_weight": f"{current_weight:.2%}",
                        "target_weight": f"{target_weight:.2%}",
                        "trade_size": f"{abs(trade_size):.2%}",
                        "priority": _calculate_trade_priority(
                            trade_size, current_weight, target_weight
                        ),
                    }
                )

                rebalancing_plan["total_turnover"] += abs(trade_size)

        # Sort trades by priority
        rebalancing_plan["trades_required"].sort(key=lambda x: x["priority"], reverse=True)

        # Calculate transaction costs
        rebalancing_plan["estimated_transaction_costs"] = (
            rebalancing_plan["total_turnover"] * optimization_constraints["transaction_cost"]
        )

        # Check if turnover exceeds constraints
        if rebalancing_plan["total_turnover"] > optimization_constraints["max_turnover"]:
            rebalancing_plan[
                "warning"
            ] = f"Total turnover {rebalancing_plan['total_turnover']:.1%} exceeds constraint {optimization_constraints['max_turnover']:.1%}"

            # Suggest reducing trades
            rebalancing_plan["suggested_modifications"] = _suggest_turnover_reduction(
                rebalancing_plan["trades_required"], optimization_constraints["max_turnover"]
            )

        return rebalancing_plan

    except Exception as e:
        return {"error": str(e), "message": "Failed to optimize portfolio allocation"}


def generate_portfolio_report(
    portfolio_data: Dict[str, Any], include_sections: Optional[List[str]] = None
) -> str:
    """
    Generate a comprehensive portfolio report.

    Args:
        portfolio_data: Portfolio data from build_portfolio() or similar
        include_sections: Sections to include ['summary', 'allocation', 'risk', 'recommendations']

    Returns:
        Formatted string report
    """
    if include_sections is None:
        include_sections = ["summary", "allocation", "risk", "recommendations"]

    try:
        report = f"""
PORTFOLIO ANALYSIS REPORT
{'='*50}
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}
Objective: {portfolio_data.get('portfolio_objective', 'Not specified')}

"""

        if "summary" in include_sections:
            report += _generate_portfolio_summary_section(portfolio_data)

        if "allocation" in include_sections:
            report += _generate_allocation_section(portfolio_data)

        if "risk" in include_sections:
            report += _generate_risk_section(portfolio_data)

        if "recommendations" in include_sections:
            report += _generate_recommendations_section(portfolio_data)

        report += f"\n{'='*50}\nGenerated by Claude Desktop Investment Tools\n"

        return report

    except Exception as e:
        return f"Error generating portfolio report: {str(e)}"


# Helper functions
def _score_stocks_for_portfolio(stock_data_dict: Dict, objective: str) -> List[Dict]:
    """Score stocks based on portfolio objective."""
    scored_stocks = []

    for ticker, data in stock_data_dict.items():
        score = 0
        metrics = {}

        # Base metrics
        pe_ratio = data.get("trailing_pe", 0)
        roe = data.get("return_on_equity", 0)
        revenue_growth = data.get("revenue_growth", 0)
        debt_ratio = data.get("debt_to_equity", 0)
        dividend_yield = data.get("dividend_yield", 0)
        market_cap = data.get("market_cap", 0)

        if objective == "value":
            # Favor low valuations, stable companies
            if pe_ratio and pe_ratio > 0 and pe_ratio < 20:
                score += 2
            elif pe_ratio and pe_ratio < 15:
                score += 3

            if roe and roe > 0.12:
                score += 2

            if debt_ratio < 50:
                score += 1

        elif objective == "growth":
            # Favor high growth, even at premium valuations
            if revenue_growth > 0.15:
                score += 3
            elif revenue_growth > 0.10:
                score += 2

            if roe and roe > 0.15:
                score += 2

            # Don't penalize high P/E as much for growth stocks
            if pe_ratio and pe_ratio > 0:
                score += 1

        elif objective == "income":
            # Favor dividend-paying stocks
            if dividend_yield > 0.03:
                score += 3
            elif dividend_yield > 0.02:
                score += 2

            if debt_ratio < 60:  # Need stable companies for dividends
                score += 2

        elif objective == "low_risk":
            # Favor large, stable, low-debt companies
            if market_cap > 50e9:  # Large cap
                score += 2
            elif market_cap > 20e9:  # Mid cap
                score += 1

            if debt_ratio < 30:
                score += 3
            elif debt_ratio < 50:
                score += 1

            if roe and 0.10 < roe < 0.25:  # Stable profitability
                score += 2

        else:  # balanced
            # Balanced approach
            if pe_ratio and 10 < pe_ratio < 25:
                score += 2
            if roe and roe > 0.12:
                score += 2
            if revenue_growth > 0.05:
                score += 1
            if debt_ratio < 60:
                score += 1
            if dividend_yield > 0.01:
                score += 1

        scored_stocks.append({"ticker": ticker, "score": score, "data": data, "metrics": metrics})

    return sorted(scored_stocks, key=lambda x: x["score"], reverse=True)


def _optimize_portfolio_allocation(
    scored_stocks: List[Dict], constraints: Dict, max_positions: int
) -> Dict[str, float]:
    """Create optimized portfolio allocation."""
    allocation = {}

    # Select top stocks up to max_positions
    selected_stocks = scored_stocks[:max_positions]

    if not selected_stocks:
        return allocation

    # Simple equal-weighted approach with constraints
    base_weight = 1.0 / len(selected_stocks)
    max_weight = constraints.get("max_single_position", 0.20)
    min_weight = constraints.get("min_position", 0.05)

    # Adjust weights based on scores
    total_score = sum(stock["score"] for stock in selected_stocks)

    for stock in selected_stocks:
        if total_score > 0:
            score_weight = stock["score"] / total_score
            # Blend equal weight with score weight
            weight = (base_weight * 0.6) + (score_weight * 0.4)
        else:
            weight = base_weight

        # Apply constraints
        weight = max(min_weight, min(max_weight, weight))
        allocation[stock["ticker"]] = weight

    # Normalize to sum to 1.0
    total_weight = sum(allocation.values())
    if total_weight > 0:
        for ticker in allocation:
            allocation[ticker] /= total_weight

    return allocation


def _calculate_portfolio_metrics(allocation: Dict[str, float], stock_data_dict: Dict) -> Dict:
    """Calculate portfolio-level metrics."""
    if not allocation:
        return {}

    weighted_pe = 0
    weighted_roe = 0
    weighted_yield = 0
    weighted_growth = 0
    total_market_cap = 0

    for ticker, weight in allocation.items():
        data = stock_data_dict.get(ticker, {})

        pe = data.get("trailing_pe", 0)
        if pe and pe > 0:
            weighted_pe += pe * weight

        roe = data.get("return_on_equity", 0)
        if roe:
            weighted_roe += roe * weight

        dividend_yield = data.get("dividend_yield", 0)
        if dividend_yield:
            weighted_yield += dividend_yield * weight

        growth = data.get("revenue_growth", 0)
        if growth:
            weighted_growth += growth * weight

        market_cap = data.get("market_cap", 0)
        if market_cap:
            total_market_cap += market_cap * weight

    return {
        "weighted_pe_ratio": weighted_pe,
        "weighted_roe": weighted_roe,
        "weighted_dividend_yield": weighted_yield,
        "weighted_revenue_growth": weighted_growth,
        "weighted_avg_market_cap_b": total_market_cap / 1e9,
        "number_of_positions": len(allocation),
    }


def _analyze_portfolio_risk(allocation: Dict[str, float], stock_data_dict: Dict) -> Dict:
    """Analyze portfolio risk factors."""
    risk_analysis = {
        "concentration_risk": "Low"
        if len(allocation) >= 10
        else "Medium"
        if len(allocation) >= 5
        else "High",
        "largest_position": max(allocation.values()) if allocation else 0,
        "top_3_concentration": sum(sorted(allocation.values(), reverse=True)[:3])
        if len(allocation) >= 3
        else sum(allocation.values()),
    }

    return risk_analysis


def _analyze_sector_diversification(allocation: Dict[str, float], stock_data_dict: Dict) -> Dict:
    """Analyze sector diversification."""
    sector_allocation = {}

    for ticker, weight in allocation.items():
        sector = stock_data_dict.get(ticker, {}).get("sector", "Unknown")
        sector_allocation[sector] = sector_allocation.get(sector, 0) + weight

    return {
        "sectors_represented": len(sector_allocation),
        "sector_allocation": {k: f"{v:.1%}" for k, v in sector_allocation.items()},
        "largest_sector_weight": max(sector_allocation.values()) if sector_allocation else 0,
        "diversification_score": "High"
        if len(sector_allocation) >= 5
        else "Medium"
        if len(sector_allocation) >= 3
        else "Low",
    }


def _generate_rebalancing_suggestions(
    allocation: Dict[str, float], stock_data_dict: Dict
) -> List[str]:
    """Generate rebalancing suggestions."""
    suggestions = []

    # Check for concentration
    if max(allocation.values()) > 0.20:
        largest_position = max(allocation.items(), key=lambda x: x[1])
        suggestions.append(
            f"Consider reducing {largest_position[0]} position ({largest_position[1]:.1%}) - exceeds 20% allocation"
        )

    # Check sector concentration
    sector_weights = {}
    for ticker, weight in allocation.items():
        sector = stock_data_dict.get(ticker, {}).get("sector", "Unknown")
        sector_weights[sector] = sector_weights.get(sector, 0) + weight

    for sector, weight in sector_weights.items():
        if weight > 0.35:
            suggestions.append(
                f"High concentration in {sector} sector ({weight:.1%}) - consider diversification"
            )

    return suggestions


def _analyze_sector_concentration(portfolio_data: Dict, weights: List[float]) -> Dict:
    """Analyze sector concentration risk."""
    sector_weights = {}

    for i, (ticker, data) in enumerate(portfolio_data.items()):
        if i < len(weights):
            sector = data.get("sector", "Unknown")
            sector_weights[sector] = sector_weights.get(sector, 0) + weights[i]

    max_sector_weight = max(sector_weights.values()) if sector_weights else 0

    return {
        "sector_weights": {k: f"{v:.1%}" for k, v in sector_weights.items()},
        "max_sector_weight": f"{max_sector_weight:.1%}",
        "concentration_level": "High"
        if max_sector_weight > 0.4
        else "Medium"
        if max_sector_weight > 0.25
        else "Low",
    }


def _analyze_size_concentration(portfolio_data: Dict, weights: List[float]) -> Dict:
    """Analyze market cap concentration."""
    weighted_market_cap = 0
    large_cap_weight = 0  # >$10B
    mid_cap_weight = 0  # $2B-$10B
    small_cap_weight = 0  # <$2B

    for i, (ticker, data) in enumerate(portfolio_data.items()):
        if i < len(weights):
            market_cap = data.get("market_cap", 0)
            weight = weights[i]

            if market_cap:
                weighted_market_cap += market_cap * weight

                if market_cap > 10e9:
                    large_cap_weight += weight
                elif market_cap > 2e9:
                    mid_cap_weight += weight
                else:
                    small_cap_weight += weight

    return {
        "weighted_avg_market_cap_b": f"${weighted_market_cap / 1e9:.1f}B",
        "large_cap_allocation": f"{large_cap_weight:.1%}",
        "mid_cap_allocation": f"{mid_cap_weight:.1%}",
        "small_cap_allocation": f"{small_cap_weight:.1%}",
        "size_diversification": "High"
        if min(large_cap_weight, mid_cap_weight + small_cap_weight) > 0.2
        else "Low",
    }


def _analyze_style_concentration(portfolio_data: Dict, weights: List[float]) -> Dict:
    """Analyze value vs growth style concentration."""
    value_weight = 0
    growth_weight = 0

    for i, (ticker, data) in enumerate(portfolio_data.items()):
        if i < len(weights):
            pe_ratio = data.get("trailing_pe", 0)
            revenue_growth = data.get("revenue_growth", 0)
            weight = weights[i]

            # Simple style classification
            if pe_ratio and pe_ratio < 15:
                value_weight += weight
            elif revenue_growth and revenue_growth > 0.15:
                growth_weight += weight

    return {
        "value_tilt": f"{value_weight:.1%}",
        "growth_tilt": f"{growth_weight:.1%}",
        "style_balance": "Balanced"
        if abs(value_weight - growth_weight) < 0.3
        else "Value-tilted"
        if value_weight > growth_weight
        else "Growth-tilted",
    }


def _analyze_financial_health_risk(portfolio_data: Dict, weights: List[float]) -> Dict:
    """Analyze financial health risk."""
    high_debt_weight = 0
    low_profitability_weight = 0

    for i, (ticker, data) in enumerate(portfolio_data.items()):
        if i < len(weights):
            debt_ratio = data.get("debt_to_equity", 0)
            roe = data.get("return_on_equity", 0)
            weight = weights[i]

            if debt_ratio > 75:  # High debt
                high_debt_weight += weight

            if roe and roe < 0.08:  # Low profitability
                low_profitability_weight += weight

    return {
        "high_debt_exposure": f"{high_debt_weight:.1%}",
        "low_profitability_exposure": f"{low_profitability_weight:.1%}",
        "financial_health_score": "Strong"
        if high_debt_weight < 0.2 and low_profitability_weight < 0.1
        else "Moderate",
    }


def _assess_overall_portfolio_risk(risk_analysis: Dict) -> Dict:
    """Assess overall portfolio risk level."""
    risk_factors = []

    if risk_analysis.get("sector_risk", {}).get("concentration_level") == "High":
        risk_factors.append("High sector concentration")

    if risk_analysis.get("size_risk", {}).get("size_diversification") == "Low":
        risk_factors.append("Poor size diversification")

    if risk_analysis.get("financial_health_risk", {}).get("financial_health_score") != "Strong":
        risk_factors.append("Financial health concerns")

    overall_risk = (
        "High" if len(risk_factors) >= 2 else "Medium" if len(risk_factors) == 1 else "Low"
    )

    return {
        "overall_risk_level": overall_risk,
        "risk_factors": risk_factors,
        "recommendation": "Consider diversification improvements"
        if overall_risk != "Low"
        else "Well-diversified portfolio",
    }


def _calculate_trade_priority(
    trade_size: float, current_weight: float, target_weight: float
) -> float:
    """Calculate priority for rebalancing trades."""
    # Larger deviations get higher priority
    deviation = abs(trade_size)

    # Trades to establish new positions get high priority
    if current_weight == 0 and target_weight > 0:
        return deviation * 2

    # Trades to exit positions get high priority
    if current_weight > 0 and target_weight == 0:
        return deviation * 1.5

    return deviation


def _suggest_turnover_reduction(trades: List[Dict], max_turnover: float) -> List[str]:
    """Suggest ways to reduce portfolio turnover."""
    suggestions = []

    # Find smallest trades that could be eliminated
    small_trades = [
        trade for trade in trades if float(trade["trade_size"].rstrip("%")) / 100 < 0.05
    ]

    if small_trades:
        suggestions.append(f"Consider eliminating {len(small_trades)} small trades (<5% each)")

    # Suggest focusing on largest deviations
    suggestions.append("Focus on largest position deviations first")
    suggestions.append("Consider phased rebalancing over multiple periods")

    return suggestions


def _generate_portfolio_summary_section(portfolio_data: Dict) -> str:
    """Generate portfolio summary section."""
    metrics = portfolio_data.get("portfolio_metrics", {})

    return f"""
PORTFOLIO SUMMARY
-----------------
Total Positions: {metrics.get('number_of_positions', 0)}
Weighted P/E Ratio: {metrics.get('weighted_pe_ratio', 0):.1f}
Weighted ROE: {metrics.get('weighted_roe', 0):.1%}
Weighted Dividend Yield: {metrics.get('weighted_dividend_yield', 0):.2%}
Weighted Revenue Growth: {metrics.get('weighted_revenue_growth', 0):.1%}
Average Market Cap: ${metrics.get('weighted_avg_market_cap_b', 0):.1f}B

"""


def _generate_allocation_section(portfolio_data: Dict) -> str:
    """Generate allocation section."""
    allocation = portfolio_data.get("allocation", {})

    section = """
PORTFOLIO ALLOCATION
--------------------
"""

    for ticker, weight in sorted(allocation.items(), key=lambda x: x[1], reverse=True):
        section += f"{ticker}: {weight:.1%}\n"

    return section + "\n"


def _generate_risk_section(portfolio_data: Dict) -> str:
    """Generate risk analysis section."""
    risk_data = portfolio_data.get("risk_analysis", {})
    sector_data = portfolio_data.get("sector_diversification", {})

    return f"""
RISK ANALYSIS
-------------
Concentration Risk: {risk_data.get('concentration_risk', 'N/A')}
Largest Position: {risk_data.get('largest_position', 0):.1%}
Top 3 Concentration: {risk_data.get('top_3_concentration', 0):.1%}

Sector Diversification: {sector_data.get('diversification_score', 'N/A')}
Sectors Represented: {sector_data.get('sectors_represented', 0)}

"""


def _generate_recommendations_section(portfolio_data: Dict) -> str:
    """Generate recommendations section."""
    suggestions = portfolio_data.get("rebalancing_suggestions", [])

    section = """
RECOMMENDATIONS
---------------
"""

    if suggestions:
        for suggestion in suggestions:
            section += f"• {suggestion}\n"
    else:
        section += "• Portfolio appears well-balanced\n"

    return section + "\n"
