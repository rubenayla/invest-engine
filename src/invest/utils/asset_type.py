"""
Asset type detection utilities.

Detects whether a ticker represents a stock, ETF, or other security type.
"""

from functools import lru_cache
from typing import Any, Dict, Optional

import yfinance as yf


@lru_cache(maxsize=128)
def get_asset_type(ticker: str) -> str:
    """
    Determine the asset type of a ticker.

    Parameters
    ----------
    ticker : str
        The ticker symbol to check

    Returns
    -------
    str
        'ETF', 'EQUITY', or 'UNKNOWN'
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        # Check quoteType field
        quote_type = info.get("quoteType", "").upper()
        if quote_type == "ETF":
            return "ETF"
        elif quote_type in ["EQUITY", "STOCK"]:
            return "EQUITY"

        # Fallback checks for ETFs
        # ETFs often have these characteristics
        if info.get("fundFamily") or info.get("fundInceptionDate"):
            return "ETF"

        # Check for typical ETF names
        long_name = info.get("longName", "").upper()
        if any(etf_indicator in long_name for etf_indicator in ["ETF", "FUND", "TRUST", "INDEX"]):
            return "ETF"

        # Check for typical stock characteristics
        if info.get("sector") or info.get("industry"):
            return "EQUITY"

        # Default to equity if we have basic stock data
        if info.get("marketCap") and info.get("sharesOutstanding"):
            return "EQUITY"

        return "UNKNOWN"

    except Exception:
        return "UNKNOWN"


def is_etf(ticker: str) -> bool:
    """
    Check if a ticker is an ETF.

    Parameters
    ----------
    ticker : str
        The ticker symbol to check

    Returns
    -------
    bool
        True if the ticker is an ETF, False otherwise
    """
    return get_asset_type(ticker) == "ETF"


def is_equity(ticker: str) -> bool:
    """
    Check if a ticker is a stock/equity.

    Parameters
    ----------
    ticker : str
        The ticker symbol to check

    Returns
    -------
    bool
        True if the ticker is an equity, False otherwise
    """
    return get_asset_type(ticker) == "EQUITY"


def get_etf_info(ticker: str) -> Optional[Dict[str, Any]]:
    """
    Get ETF-specific information.

    Parameters
    ----------
    ticker : str
        The ETF ticker symbol

    Returns
    -------
    Dict[str, Any] or None
        Dictionary with ETF information or None if not an ETF
    """
    if not is_etf(ticker):
        return None

    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        return {
            "ticker": ticker,
            "name": info.get("longName", ""),
            "expense_ratio": info.get("annualReportExpenseRatio", 0),
            "total_assets": info.get("totalAssets", 0),
            "nav": info.get("navPrice", 0),
            "category": info.get("category", ""),
            "fund_family": info.get("fundFamily", ""),
            "inception_date": info.get("fundInceptionDate", ""),
            "yield": info.get("yield", 0),
            "ytd_return": info.get("ytdReturn", 0),
            "three_year_return": info.get("threeYearAverageReturn", 0),
            "five_year_return": info.get("fiveYearAverageReturn", 0),
        }
    except Exception:
        return None


# Common ETF tickers for quick reference (cached)
COMMON_ETFS = {
    "SPY",
    "QQQ",
    "IWM",
    "VTI",
    "VOO",
    "DIA",
    "EFA",
    "EEM",
    "VEA",
    "VWO",
    "AGG",
    "BND",
    "TLT",
    "IEF",
    "LQD",
    "HYG",
    "JNK",
    "EMB",
    "GLD",
    "SLV",
    "USO",
    "GDX",
    "XLE",
    "XLF",
    "XLK",
    "XLV",
    "XLI",
    "XLY",
    "VNQ",
    "REET",
    "IYR",
    "XLRE",
    "ARKK",
    "ARKG",
    "ARKQ",
    "ARKW",
    "ARKF",
    "VIG",
    "VYM",
    "DVY",
    "SDY",
    "NOBL",
    "SCHD",
    "JEPI",
    "JEPQ",
    "XYLD",
    "QYLD",
}


def is_common_etf(ticker: str) -> bool:
    """
    Quick check if ticker is a commonly known ETF.

    Parameters
    ----------
    ticker : str
        The ticker symbol to check

    Returns
    -------
    bool
        True if ticker is in the common ETF list
    """
    return ticker.upper() in COMMON_ETFS
