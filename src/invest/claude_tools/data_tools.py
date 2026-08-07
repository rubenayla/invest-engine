"""
Claude Desktop tools for stock data retrieval and analysis.

These tools provide Claude with easy access to financial data and metrics
for individual stocks or groups of stocks.
"""

import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from invest.data.yahoo import get_financials, get_stock_data  # noqa: E402


def get_stock_data_detailed(ticker: str) -> Dict[str, Any]:
    """
    Get comprehensive stock data for a single ticker.

    Args:
        ticker: Stock ticker symbol (e.g., 'AAPL', 'MSFT')

    Returns:
        Dict containing detailed stock information formatted for analysis
    """
    try:
        # Get basic stock data
        stock_data = get_stock_data(ticker)
        if not stock_data:
            return {
                "error": f"Could not retrieve data for ticker {ticker}",
                "suggestion": "Please verify the ticker symbol is correct",
            }

        # Get detailed financials
        financials = get_financials(ticker)

        # Format the data for easy analysis
        detailed_data = {
            "ticker": ticker.upper(),
            "last_updated": datetime.now().isoformat(),
            "company_info": {
                "name": stock_data.get("longName", "N/A"),
                "sector": stock_data.get("sector", "N/A"),
                "industry": stock_data.get("industry", "N/A"),
                "description": stock_data.get("longBusinessSummary", "N/A"),
                "website": stock_data.get("website", "N/A"),
                "employees": stock_data.get("fullTimeEmployees", "N/A"),
                "country": stock_data.get("country", "N/A"),
                "exchange": stock_data.get("exchange", "N/A"),
            },
            "price_info": {
                "current_price": stock_data.get("current_price", 0),
                "currency": stock_data.get("currency", "USD"),
                "market_cap": stock_data.get("market_cap", 0),
                "market_cap_formatted": f"${stock_data.get('market_cap', 0) / 1e9:.2f}B"
                if stock_data.get("market_cap")
                else "N/A",
                "enterprise_value": stock_data.get("enterprise_value", 0),
                "shares_outstanding": stock_data.get("shares_outstanding", 0),
                "52_week_high": stock_data.get("fifty_two_week_high", 0),
                "52_week_low": stock_data.get("fifty_two_week_low", 0),
            },
            "valuation_metrics": {
                "pe_ratio_trailing": stock_data.get("trailing_pe", 0),
                "pe_ratio_forward": stock_data.get("forward_pe", 0),
                "pb_ratio": stock_data.get("price_to_book", 0),
                "ps_ratio": stock_data.get("price_to_sales", 0),
                "ev_to_ebitda": stock_data.get("ev_to_ebitda", 0),
                "ev_to_revenue": stock_data.get("ev_to_revenue", 0),
                "peg_ratio": stock_data.get("peg_ratio", 0),
            },
            "profitability_metrics": {
                "profit_margins": stock_data.get("profit_margins", 0),
                "operating_margins": stock_data.get("operating_margins", 0),
                "gross_margins": stock_data.get("gross_margins", 0),
                "return_on_equity": stock_data.get("return_on_equity", 0),
                "return_on_assets": stock_data.get("return_on_assets", 0),
                "ebitda_margins": stock_data.get("ebitda_margins", 0),
            },
            "financial_health": {
                "debt_to_equity": stock_data.get("debt_to_equity", 0),
                "current_ratio": stock_data.get("current_ratio", 0),
                "quick_ratio": stock_data.get("quick_ratio", 0),
                "total_cash": stock_data.get("total_cash", 0),
                "total_debt": stock_data.get("total_debt", 0),
                "free_cash_flow": stock_data.get("free_cash_flow", 0),
            },
            "growth_metrics": {
                "revenue_growth": stock_data.get("revenue_growth", 0),
                "earnings_growth": stock_data.get("earnings_growth", 0),
                "revenue_per_share": stock_data.get("revenue_per_share", 0),
                "earnings_per_share": stock_data.get("earnings_per_share", 0),
            },
            "dividend_info": {
                "dividend_yield": stock_data.get("dividend_yield", 0),
                "dividend_rate": stock_data.get("dividend_rate", 0),
                "payout_ratio": stock_data.get("payout_ratio", 0),
                "ex_dividend_date": stock_data.get("ex_dividend_date", "N/A"),
            },
            "analyst_info": {
                "target_high_price": stock_data.get("target_high_price", 0),
                "target_mean_price": stock_data.get("target_mean_price", 0),
                "target_low_price": stock_data.get("target_low_price", 0),
                "recommendation_mean": stock_data.get("recommendation_mean", 0),
                "number_of_analyst_opinions": stock_data.get("number_of_analyst_opinions", 0),
            },
        }

        # Add financial statements if available
        if financials:
            detailed_data["has_financial_statements"] = True
            detailed_data[
                "financial_statements_note"
            ] = "Detailed financial statements available via get_financials() tool"
        else:
            detailed_data["has_financial_statements"] = False

        # Add calculated metrics
        detailed_data["calculated_metrics"] = _calculate_additional_metrics(stock_data)

        return detailed_data

    except Exception as e:
        return {"error": str(e), "message": f"Failed to retrieve detailed data for {ticker}"}


def get_financial_metrics(
    ticker: str, metric_categories: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Get specific financial metrics for a stock.

    Args:
        ticker: Stock ticker symbol
        metric_categories: Categories to include. Options:
                          ['valuation', 'profitability', 'growth', 'financial_health', 'efficiency']

    Returns:
        Dict containing requested financial metrics
    """
    if metric_categories is None:
        metric_categories = ["valuation", "profitability", "growth", "financial_health"]

    try:
        stock_data = get_stock_data(ticker)
        if not stock_data:
            return {"error": f"Could not retrieve data for {ticker}"}

        metrics = {
            "ticker": ticker.upper(),
            "company_name": stock_data.get("longName", "N/A"),
            "analysis_date": datetime.now().isoformat(),
        }

        if "valuation" in metric_categories:
            metrics["valuation"] = {
                "pe_ratio": stock_data.get("trailing_pe", 0),
                "pb_ratio": stock_data.get("price_to_book", 0),
                "ps_ratio": stock_data.get("price_to_sales", 0),
                "ev_ebitda": stock_data.get("ev_to_ebitda", 0),
                "peg_ratio": stock_data.get("peg_ratio", 0),
            }

        if "profitability" in metric_categories:
            metrics["profitability"] = {
                "roe": stock_data.get("return_on_equity", 0),
                "roa": stock_data.get("return_on_assets", 0),
                "profit_margin": stock_data.get("profit_margins", 0),
                "operating_margin": stock_data.get("operating_margins", 0),
                "gross_margin": stock_data.get("gross_margins", 0),
            }

        if "growth" in metric_categories:
            metrics["growth"] = {
                "revenue_growth": stock_data.get("revenue_growth", 0),
                "earnings_growth": stock_data.get("earnings_growth", 0),
                "book_value_growth": _calculate_book_value_growth(stock_data),
            }

        if "financial_health" in metric_categories:
            metrics["financial_health"] = {
                "debt_to_equity": stock_data.get("debt_to_equity", 0),
                "current_ratio": stock_data.get("current_ratio", 0),
                "quick_ratio": stock_data.get("quick_ratio", 0),
                "interest_coverage": _calculate_interest_coverage(stock_data),
            }

        if "efficiency" in metric_categories:
            metrics["efficiency"] = {
                "asset_turnover": _calculate_asset_turnover(stock_data),
                "inventory_turnover": stock_data.get("inventory_turnover", 0),
                "receivables_turnover": stock_data.get("receivables_turnover", 0),
            }

        return metrics

    except Exception as e:
        return {"error": str(e), "message": f"Failed to get financial metrics for {ticker}"}


def compare_stocks(
    tickers: List[str], comparison_metrics: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Compare multiple stocks side by side.

    Args:
        tickers: List of stock ticker symbols
        comparison_metrics: Metrics to compare. Options:
                           ['valuation', 'profitability', 'growth', 'size', 'financial_health']

    Returns:
        Dict containing side-by-side comparison of stocks
    """
    if comparison_metrics is None:
        comparison_metrics = ["valuation", "profitability", "growth", "size"]

    try:
        comparison_data = {
            "tickers": [t.upper() for t in tickers],
            "comparison_date": datetime.now().isoformat(),
            "metrics_compared": comparison_metrics,
            "companies": {},
        }

        # Get data for each stock
        for ticker in tickers:
            stock_data = get_stock_data(ticker)
            if stock_data:
                company_data = {
                    "name": stock_data.get("longName", "N/A"),
                    "sector": stock_data.get("sector", "N/A"),
                    "current_price": stock_data.get("current_price", 0),
                }

                if "size" in comparison_metrics:
                    company_data["size"] = {
                        "market_cap_b": stock_data.get("market_cap", 0) / 1e9
                        if stock_data.get("market_cap")
                        else 0,
                        "enterprise_value_b": stock_data.get("enterprise_value", 0) / 1e9
                        if stock_data.get("enterprise_value")
                        else 0,
                        "employees": stock_data.get("fullTimeEmployees", 0),
                    }

                if "valuation" in comparison_metrics:
                    company_data["valuation"] = {
                        "pe_ratio": stock_data.get("trailing_pe", 0),
                        "pb_ratio": stock_data.get("price_to_book", 0),
                        "ps_ratio": stock_data.get("price_to_sales", 0),
                        "ev_ebitda": stock_data.get("ev_to_ebitda", 0),
                    }

                if "profitability" in comparison_metrics:
                    company_data["profitability"] = {
                        "roe": stock_data.get("return_on_equity", 0),
                        "roa": stock_data.get("return_on_assets", 0),
                        "profit_margin": stock_data.get("profit_margins", 0),
                        "operating_margin": stock_data.get("operating_margins", 0),
                    }

                if "growth" in comparison_metrics:
                    company_data["growth"] = {
                        "revenue_growth": stock_data.get("revenue_growth", 0),
                        "earnings_growth": stock_data.get("earnings_growth", 0),
                    }

                if "financial_health" in comparison_metrics:
                    company_data["financial_health"] = {
                        "debt_to_equity": stock_data.get("debt_to_equity", 0),
                        "current_ratio": stock_data.get("current_ratio", 0),
                        "free_cash_flow_b": stock_data.get("free_cash_flow", 0) / 1e9
                        if stock_data.get("free_cash_flow")
                        else 0,
                    }

                comparison_data["companies"][ticker.upper()] = company_data

        # Add comparison insights
        comparison_data["insights"] = _generate_comparison_insights(comparison_data)

        return comparison_data

    except Exception as e:
        return {"error": str(e), "message": f"Failed to compare stocks {', '.join(tickers)}"}


def get_sector_stocks(
    sector: str, min_market_cap: Optional[float] = None, max_results: int = 50
) -> Dict[str, Any]:
    """
    Get stocks from a specific sector with basic metrics.

    Args:
        sector: Sector name (e.g., 'Technology', 'Healthcare')
        min_market_cap: Minimum market cap in billions (optional)
        max_results: Maximum number of stocks to return

    Returns:
        Dict containing stocks from the specified sector
    """
    try:
        # This is a simplified implementation - in practice, you'd want a more comprehensive sector database
        from invest.data.yahoo import get_sp500_sample

        sector_data = {
            "sector": sector,
            "min_market_cap_b": min_market_cap,
            "max_results": max_results,
            "stocks": [],
        }

        # Get sample of stocks and filter by sector
        sample_tickers = get_sp500_sample()
        stocks_found = 0

        for ticker in sample_tickers:
            if stocks_found >= max_results:
                break

            stock_data = get_stock_data(ticker)
            if stock_data and stock_data.get("sector") == sector:
                market_cap_b = (
                    stock_data.get("market_cap", 0) / 1e9 if stock_data.get("market_cap") else 0
                )

                # Apply market cap filter if specified
                if min_market_cap is None or market_cap_b >= min_market_cap:
                    sector_data["stocks"].append(
                        {
                            "ticker": ticker,
                            "name": stock_data.get("longName", "N/A"),
                            "market_cap_b": market_cap_b,
                            "pe_ratio": stock_data.get("trailing_pe", 0),
                            "current_price": stock_data.get("current_price", 0),
                            "revenue_growth": stock_data.get("revenue_growth", 0),
                            "profit_margin": stock_data.get("profit_margins", 0),
                        }
                    )
                    stocks_found += 1

        sector_data["total_found"] = stocks_found
        return sector_data

    except Exception as e:
        return {"error": str(e), "message": f"Failed to get stocks for sector {sector}"}


def analyze_stock_trends(ticker: str, trend_periods: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Analyze trends in key metrics for a stock (using available data).

    Args:
        ticker: Stock ticker symbol
        trend_periods: Time periods to analyze (limited by available data)

    Returns:
        Dict containing trend analysis based on available data
    """
    if trend_periods is None:
        trend_periods = ["current", "target"]

    try:
        stock_data = get_stock_data(ticker)
        if not stock_data:
            return {"error": f"Could not retrieve data for {ticker}"}

        trend_analysis = {
            "ticker": ticker.upper(),
            "company_name": stock_data.get("longName", "N/A"),
            "analysis_note": "Trend analysis limited by available data - for detailed historical trends, additional data sources needed",
            "current_metrics": {
                "price": stock_data.get("current_price", 0),
                "market_cap_b": stock_data.get("market_cap", 0) / 1e9
                if stock_data.get("market_cap")
                else 0,
                "pe_ratio": stock_data.get("trailing_pe", 0),
                "revenue_growth": stock_data.get("revenue_growth", 0),
                "profit_margin": stock_data.get("profit_margins", 0),
            },
            "analyst_expectations": {
                "target_price": stock_data.get("target_mean_price", 0),
                "price_upside_potential": (
                    (stock_data.get("target_mean_price", 0) / stock_data.get("current_price", 1))
                    - 1
                )
                if stock_data.get("current_price")
                else 0,
                "forward_pe": stock_data.get("forward_pe", 0),
                "pe_trend": "improving"
                if (stock_data.get("forward_pe", 0) < stock_data.get("trailing_pe", 0))
                and stock_data.get("forward_pe", 0) > 0
                else "stable",
            },
            "growth_indicators": {
                "revenue_growth_rate": stock_data.get("revenue_growth", 0),
                "earnings_growth_rate": stock_data.get("earnings_growth", 0),
                "growth_quality": "margin_expanding"
                if stock_data.get("earnings_growth", 0) > stock_data.get("revenue_growth", 0)
                else "revenue_led",
            },
        }

        return trend_analysis

    except Exception as e:
        return {"error": str(e), "message": f"Failed to analyze trends for {ticker}"}


# Helper functions
def _calculate_additional_metrics(stock_data: Dict) -> Dict[str, Any]:
    """Calculate additional metrics from available data."""
    metrics = {}

    # ROIC approximation
    roe = stock_data.get("return_on_equity", 0)
    debt_ratio = stock_data.get("debt_to_equity", 0)
    if roe and debt_ratio:
        metrics["roic_estimate"] = roe / (1 + debt_ratio / 100) if debt_ratio > 0 else roe

    # Price to sales growth (simple approximation)
    ps_ratio = stock_data.get("price_to_sales", 0)
    revenue_growth = stock_data.get("revenue_growth", 0)
    if ps_ratio and revenue_growth and revenue_growth > 0:
        metrics["ps_to_growth"] = ps_ratio / (revenue_growth * 100)

    # Enterprise multiple
    ev = stock_data.get("enterprise_value", 0)
    revenue = stock_data.get("total_revenue", 0)
    if ev and revenue and revenue > 0:
        metrics["ev_to_sales"] = ev / revenue

    return metrics


def _calculate_book_value_growth(stock_data: Dict) -> float:
    """Estimate book value growth from ROE and retention ratio."""
    roe = stock_data.get("return_on_equity", 0)
    payout_ratio = stock_data.get("payout_ratio", 0.4)  # Assume 40% if not available

    if roe:
        retention_ratio = 1 - payout_ratio
        return roe * retention_ratio
    return 0


def _calculate_interest_coverage(stock_data: Dict) -> Optional[float]:
    """Estimate interest coverage ratio."""
    # This would require EBIT and interest expense from income statement
    # For now, provide a rough estimate based on debt levels and profitability
    debt_ratio = stock_data.get("debt_to_equity", 0)
    profit_margin = stock_data.get("profit_margins", 0)

    if debt_ratio and profit_margin:
        if debt_ratio < 20:
            return 10.0  # Assume good coverage for low debt companies
        elif debt_ratio < 50:
            return 5.0  # Moderate coverage
        else:
            return 2.0  # Lower coverage for high debt

    return None


def _calculate_asset_turnover(stock_data: Dict) -> Optional[float]:
    """Calculate asset turnover if data is available."""
    total_revenue = stock_data.get("total_revenue", 0)
    total_assets = stock_data.get("total_assets", 0)

    if total_revenue and total_assets and total_assets > 0:
        return total_revenue / total_assets

    return None


def _generate_comparison_insights(comparison_data: Dict) -> List[str]:
    """Generate insights from stock comparison."""
    insights = []
    companies = comparison_data.get("companies", {})

    if not companies:
        return insights

    # Find highest/lowest valuations
    if "valuation" in comparison_data.get("metrics_compared", []):
        pe_ratios = {
            ticker: data.get("valuation", {}).get("pe_ratio", 0)
            for ticker, data in companies.items()
            if data.get("valuation", {}).get("pe_ratio", 0) > 0
        }

        if pe_ratios:
            cheapest = min(pe_ratios.items(), key=lambda x: x[1])
            most_expensive = max(pe_ratios.items(), key=lambda x: x[1])
            insights.append(
                f"Valuation: {cheapest[0]} has lowest P/E at {cheapest[1]:.1f}, {most_expensive[0]} highest at {most_expensive[1]:.1f}"
            )

    # Find highest growth
    if "growth" in comparison_data.get("metrics_compared", []):
        revenue_growth = {
            ticker: data.get("growth", {}).get("revenue_growth", 0)
            for ticker, data in companies.items()
        }

        if revenue_growth:
            fastest_growing = max(revenue_growth.items(), key=lambda x: x[1])
            insights.append(
                f"Growth: {fastest_growing[0]} has highest revenue growth at {fastest_growing[1]:.1%}"
            )

    # Find most profitable
    if "profitability" in comparison_data.get("metrics_compared", []):
        roe_values = {
            ticker: data.get("profitability", {}).get("roe", 0)
            for ticker, data in companies.items()
        }

        if roe_values:
            most_profitable = max(roe_values.items(), key=lambda x: x[1])
            insights.append(
                f"Profitability: {most_profitable[0]} has highest ROE at {most_profitable[1]:.1%}"
            )

    return insights
