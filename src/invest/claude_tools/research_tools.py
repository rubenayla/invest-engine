"""
Claude Desktop tools for stock research and analysis.

These tools enable Claude to perform web-based research and qualitative analysis
that complements the systematic quantitative screening.
"""

import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from invest.data.yahoo import get_financials, get_stock_data  # noqa: E402


def research_stock(
    ticker: str, research_areas: Optional[List[str]] = None, time_horizon: str = "3_months"
) -> Dict[str, Any]:
    """
    Research a specific stock using available data and prompt Claude for web research.

    Args:
        ticker: Stock ticker symbol (e.g., 'AAPL', 'MSFT')
        research_areas: List of areas to focus on. Options:
                       ['competitive_position', 'recent_news', 'management',
                        'industry_trends', 'risks', 'catalysts']
        time_horizon: Time period for analysis ('1_month', '3_months', '6_months', '1_year')

    Returns:
        Dict containing available stock data and research framework for Claude
    """
    if research_areas is None:
        research_areas = ["competitive_position", "recent_news", "risks"]

    try:
        # Get basic stock data
        stock_data = get_stock_data(ticker)
        if not stock_data:
            return {
                "error": f"Could not retrieve data for ticker {ticker}",
                "suggestion": "Please verify the ticker symbol is correct",
            }

        # Get detailed financials if available
        get_financials(ticker)

        # Prepare research framework
        research_framework = {
            "ticker": ticker.upper(),
            "company_name": stock_data.get("longName", "N/A"),
            "basic_info": {
                "sector": stock_data.get("sector", "N/A"),
                "industry": stock_data.get("industry", "N/A"),
                "market_cap": f"${stock_data.get('market_cap', 0) / 1e9:.2f}B"
                if stock_data.get("market_cap")
                else "N/A",
                "current_price": f"${stock_data.get('current_price', 0):.2f}"
                if stock_data.get("current_price")
                else "N/A",
                "employees": stock_data.get("fullTimeEmployees", "N/A"),
                "website": stock_data.get("website", "N/A"),
                "description": stock_data.get("longBusinessSummary", "N/A")[:500] + "..."
                if stock_data.get("longBusinessSummary")
                and len(stock_data.get("longBusinessSummary", "")) > 500
                else stock_data.get("longBusinessSummary", "N/A"),
            },
            "financial_snapshot": {
                "pe_ratio": f"{stock_data.get('trailing_pe', 0):.1f}"
                if stock_data.get("trailing_pe")
                else "N/A",
                "pb_ratio": f"{stock_data.get('price_to_book', 0):.2f}"
                if stock_data.get("price_to_book")
                else "N/A",
                "roe": f"{stock_data.get('return_on_equity', 0):.1%}"
                if stock_data.get("return_on_equity")
                else "N/A",
                "debt_to_equity": f"{stock_data.get('debt_to_equity', 0):.1f}"
                if stock_data.get("debt_to_equity")
                else "N/A",
                "revenue_growth": f"{stock_data.get('revenue_growth', 0):.1%}"
                if stock_data.get("revenue_growth")
                else "N/A",
                "profit_margins": f"{stock_data.get('profit_margins', 0):.1%}"
                if stock_data.get("profit_margins")
                else "N/A",
                "operating_margins": f"{stock_data.get('operating_margins', 0):.1%}"
                if stock_data.get("operating_margins")
                else "N/A",
            },
            "analyst_targets": {
                "target_high": f"${stock_data.get('target_high_price', 0):.2f}"
                if stock_data.get("target_high_price")
                else "N/A",
                "target_mean": f"${stock_data.get('target_mean_price', 0):.2f}"
                if stock_data.get("target_mean_price")
                else "N/A",
                "target_low": f"${stock_data.get('target_low_price', 0):.2f}"
                if stock_data.get("target_low_price")
                else "N/A",
                "recommendation": stock_data.get("recommendation_mean", "N/A"),
            },
            "research_areas_requested": research_areas,
            "time_horizon": time_horizon,
            "claude_research_prompts": _generate_research_prompts(
                ticker, stock_data, research_areas, time_horizon
            ),
        }

        return research_framework

    except Exception as e:
        return {"error": str(e), "message": f"Failed to research {ticker}"}


def analyze_sector(
    sector: str, focus_areas: Optional[List[str]] = None, include_stocks: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Analyze a specific sector with context for investment decisions.

    Args:
        sector: Sector name (e.g., 'Technology', 'Healthcare', 'Energy')
        focus_areas: Areas to analyze. Options:
                    ['cycle_position', 'trends', 'valuations', 'regulations', 'risks']
        include_stocks: Specific stocks in the sector to highlight

    Returns:
        Dict containing sector analysis framework for Claude
    """
    if focus_areas is None:
        focus_areas = ["cycle_position", "trends", "valuations"]

    try:
        # Load sector benchmarks if available
        sector_info = {
            "sector": sector,
            "focus_areas": focus_areas,
            "analysis_date": datetime.now().isoformat(),
            "claude_research_prompts": _generate_sector_research_prompts(sector, focus_areas),
        }

        # Add sector benchmarks if available
        try:
            from invest.analysis.sector_context import SectorContext

            sector_context = SectorContext()
            benchmarks = sector_context.get_sector_context(sector)

            if benchmarks:
                sector_info["benchmarks"] = {
                    "typical_pe_range": benchmarks.typical_pe_range,
                    "typical_roe_range": [f"{r:.1%}" for r in benchmarks.typical_roe_range],
                    "typical_roic_range": [f"{r:.1%}" for r in benchmarks.typical_roic_range],
                    "cyclicality": benchmarks.cyclicality,
                    "capital_intensity": benchmarks.capital_intensity,
                    "margin_stability": benchmarks.margin_stability,
                }
        except Exception:
            sector_info["benchmarks"] = "Not available"

        # Include specific stocks if provided
        if include_stocks:
            sector_info["highlighted_stocks"] = []
            for ticker in include_stocks:
                stock_data = get_stock_data(ticker)
                if stock_data:
                    sector_info["highlighted_stocks"].append(
                        {
                            "ticker": ticker.upper(),
                            "company_name": stock_data.get("longName", "N/A"),
                            "market_cap_b": f"{stock_data.get('market_cap', 0) / 1e9:.2f}"
                            if stock_data.get("market_cap")
                            else "N/A",
                            "pe_ratio": f"{stock_data.get('trailing_pe', 0):.1f}"
                            if stock_data.get("trailing_pe")
                            else "N/A",
                        }
                    )

        return sector_info

    except Exception as e:
        return {"error": str(e), "message": f"Failed to analyze sector {sector}"}


def get_recent_news(
    ticker: str, news_types: Optional[List[str]] = None, days_back: int = 30
) -> Dict[str, Any]:
    """
    Get framework for researching recent news about a stock.

    Args:
        ticker: Stock ticker symbol
        news_types: Types of news to focus on. Options:
                   ['earnings', 'analyst_updates', 'product_launches', 'regulatory', 'partnerships']
        days_back: Number of days to look back for news

    Returns:
        Dict containing news research framework for Claude
    """
    if news_types is None:
        news_types = ["earnings", "analyst_updates", "regulatory"]

    try:
        stock_data = get_stock_data(ticker)
        if not stock_data:
            return {"error": f"Could not find stock data for {ticker}"}

        news_framework = {
            "ticker": ticker.upper(),
            "company_name": stock_data.get("longName", "N/A"),
            "sector": stock_data.get("sector", "N/A"),
            "search_period": f"Last {days_back} days",
            "news_types_requested": news_types,
            "search_terms": _generate_news_search_terms(ticker, stock_data, news_types),
            "claude_search_prompts": _generate_news_search_prompts(
                ticker, stock_data, news_types, days_back
            ),
        }

        return news_framework

    except Exception as e:
        return {
            "error": str(e),
            "message": f"Failed to generate news research framework for {ticker}",
        }


def compare_competitive_position(
    primary_ticker: str, competitor_tickers: List[str], comparison_areas: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Compare competitive positions of multiple stocks in the same sector.

    Args:
        primary_ticker: Main stock to analyze
        competitor_tickers: List of competitor ticker symbols
        comparison_areas: Areas to compare. Options:
                         ['market_share', 'profitability', 'growth', 'valuation', 'strengths_weaknesses']

    Returns:
        Dict containing competitive analysis framework
    """
    if comparison_areas is None:
        comparison_areas = ["market_share", "profitability", "valuation"]

    try:
        # Get data for all companies
        companies = {}
        all_tickers = [primary_ticker] + competitor_tickers

        for ticker in all_tickers:
            stock_data = get_stock_data(ticker)
            if stock_data:
                companies[ticker.upper()] = {
                    "name": stock_data.get("longName", "N/A"),
                    "sector": stock_data.get("sector", "N/A"),
                    "market_cap_b": stock_data.get("market_cap", 0) / 1e9
                    if stock_data.get("market_cap")
                    else 0,
                    "pe_ratio": stock_data.get("trailing_pe", 0),
                    "profit_margins": stock_data.get("profit_margins", 0),
                    "roe": stock_data.get("return_on_equity", 0),
                    "revenue_growth": stock_data.get("revenue_growth", 0),
                    "debt_to_equity": stock_data.get("debt_to_equity", 0),
                }

        competitive_analysis = {
            "primary_company": primary_ticker.upper(),
            "competitors": [t.upper() for t in competitor_tickers],
            "comparison_areas": comparison_areas,
            "company_data": companies,
            "claude_analysis_prompts": _generate_competitive_analysis_prompts(
                primary_ticker, competitor_tickers, companies, comparison_areas
            ),
        }

        return competitive_analysis

    except Exception as e:
        return {
            "error": str(e),
            "message": f"Failed to generate competitive analysis for {primary_ticker}",
        }


def _generate_research_prompts(
    ticker: str, stock_data: Dict, research_areas: List[str], time_horizon: str
) -> List[str]:
    """Generate specific research prompts for Claude to investigate."""
    company_name = stock_data.get("longName", ticker)
    sector = stock_data.get("sector", "the sector")

    prompts = [
        f"Please search for recent information about {company_name} ({ticker}) focusing on the following areas. "
        f"Look for information from the last {time_horizon.replace('_', ' ')}."
    ]

    if "competitive_position" in research_areas:
        prompts.append(
            f"Research {company_name}'s competitive position in {sector}. "
            f"What is their market share? What are their competitive advantages (moats)? "
            f"Who are their main competitors and how do they compare?"
        )

    if "recent_news" in research_areas:
        prompts.append(
            f"Find recent news about {company_name} ({ticker}). Look for: "
            f"earnings reports, product announcements, regulatory changes, "
            f"analyst upgrades/downgrades, partnership announcements."
        )

    if "management" in research_areas:
        prompts.append(
            f"Research {company_name}'s management quality. "
            f"What is the track record of the CEO and key executives? "
            f"Any recent management changes? How do they communicate with shareholders?"
        )

    if "industry_trends" in research_areas:
        prompts.append(
            f"Analyze trends affecting the {sector} sector and {company_name} specifically. "
            f"What are the growth drivers? What are the headwinds? "
            f"Any technological or regulatory changes?"
        )

    if "risks" in research_areas:
        prompts.append(
            f"Identify key risks for {company_name} ({ticker}). "
            f"Consider: regulatory risks, competitive threats, cyclical risks, "
            f"geopolitical risks, operational risks, financial risks."
        )

    if "catalysts" in research_areas:
        prompts.append(
            f"Look for potential catalysts that could drive {company_name}'s stock price. "
            f"Consider: upcoming product launches, regulatory approvals, "
            f"market expansions, cost-cutting initiatives, strategic partnerships."
        )

    return prompts


def _generate_sector_research_prompts(sector: str, focus_areas: List[str]) -> List[str]:
    """Generate sector-specific research prompts for Claude."""
    prompts = [f"Please research the {sector} sector with focus on the following areas:"]

    if "cycle_position" in focus_areas:
        prompts.append(
            f"Where is the {sector} sector in its business cycle? "
            f"Is it early, mid, or late cycle? What are the typical cycle drivers for this sector?"
        )

    if "trends" in focus_areas:
        prompts.append(
            f"What are the key trends affecting the {sector} sector? "
            f"Consider technological trends, demographic trends, regulatory trends."
        )

    if "valuations" in focus_areas:
        prompts.append(
            f"How are {sector} stocks valued currently vs. historical norms? "
            f"Are they expensive, cheap, or fairly valued? What's driving the valuation?"
        )

    if "regulations" in focus_areas:
        prompts.append(
            f"What regulatory changes are affecting or could affect the {sector} sector? "
            f"Any pending legislation, policy changes, or regulatory approvals?"
        )

    if "risks" in focus_areas:
        prompts.append(
            f"What are the major risks facing the {sector} sector? "
            f"Consider both sector-wide and company-specific risks."
        )

    return prompts


def _generate_news_search_terms(ticker: str, stock_data: Dict, news_types: List[str]) -> List[str]:
    """Generate search terms for news research."""
    company_name = stock_data.get("longName", ticker)
    terms = [ticker, company_name]

    if "earnings" in news_types:
        terms.extend([f"{ticker} earnings", f"{company_name} quarterly results"])

    if "analyst_updates" in news_types:
        terms.extend(
            [f"{ticker} analyst", f"{company_name} price target", f"{ticker} upgrade downgrade"]
        )

    if "product_launches" in news_types:
        terms.extend([f"{company_name} product launch", f"{ticker} new product"])

    if "regulatory" in news_types:
        terms.extend([f"{company_name} FDA", f"{ticker} regulation", f"{company_name} approval"])

    if "partnerships" in news_types:
        terms.extend(
            [f"{company_name} partnership", f"{ticker} acquisition", f"{company_name} deal"]
        )

    return terms


def _generate_news_search_prompts(
    ticker: str, stock_data: Dict, news_types: List[str], days_back: int
) -> List[str]:
    """Generate news search prompts for Claude."""
    company_name = stock_data.get("longName", ticker)

    prompts = [
        f"Please search for recent news about {company_name} ({ticker}) from the last {days_back} days. "
        f"Focus on the following types of news:"
    ]

    for news_type in news_types:
        if news_type == "earnings":
            prompts.append(f"- Earnings reports, quarterly results, guidance updates for {ticker}")
        elif news_type == "analyst_updates":
            prompts.append(
                f"- Analyst reports, price target changes, rating upgrades/downgrades for {ticker}"
            )
        elif news_type == "product_launches":
            prompts.append(f"- New product announcements, product launches by {company_name}")
        elif news_type == "regulatory":
            prompts.append(
                f"- Regulatory approvals, compliance issues, policy changes affecting {company_name}"
            )
        elif news_type == "partnerships":
            prompts.append(
                f"- Partnerships, acquisitions, strategic deals involving {company_name}"
            )

    return prompts


def _generate_competitive_analysis_prompts(
    primary_ticker: str, competitors: List[str], company_data: Dict, comparison_areas: List[str]
) -> List[str]:
    """Generate competitive analysis prompts for Claude."""
    primary_name = company_data.get(primary_ticker.upper(), {}).get("name", primary_ticker)
    competitor_names = [company_data.get(t.upper(), {}).get("name", t) for t in competitors]

    prompts = [
        f"Please analyze the competitive position of {primary_name} ({primary_ticker}) "
        f"compared to its main competitors: {', '.join(competitor_names)}. "
        f"Focus on these areas:"
    ]

    if "market_share" in comparison_areas:
        prompts.append(
            f"- Market share analysis: Who has the largest market share? "
            f"Is {primary_name} gaining or losing market share?"
        )

    if "profitability" in comparison_areas:
        prompts.append(
            f"- Profitability comparison: Compare profit margins, ROE, and profitability trends "
            f"between {primary_name} and its competitors."
        )

    if "growth" in comparison_areas:
        prompts.append(
            "- Growth comparison: Which company is growing faster? "
            "Compare revenue growth, earnings growth, and expansion strategies."
        )

    if "valuation" in comparison_areas:
        prompts.append(
            "- Valuation comparison: Compare P/E ratios, P/B ratios, and other valuation metrics. "
            "Which company offers better value?"
        )

    if "strengths_weaknesses" in comparison_areas:
        prompts.append(
            f"- Strengths and weaknesses: What are {primary_name}'s key competitive advantages? "
            f"What are their weaknesses compared to competitors?"
        )

    return prompts
