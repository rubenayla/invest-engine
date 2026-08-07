"""
Standard DCF - Single-Stage Discounted Cash Flow Valuation

This is the classic DCF model using a single growth rate assumption. Best for:
- Mature companies with stable cash flows
- Simple valuations where growth uncertainty is low
- Quick analysis when you need a baseline valuation

Key Features:
- Normalizes FCF from historical data to smooth out one-time events
- Single discount rate (WACC) throughout projection period
- Terminal value with constant growth rate
- Handles missing market data gracefully

Variables:
    enterprise_value     : Present value of projected FCFs + terminal value
    estimated_market_cap : Enterprise value - net debt
    fair_value_per_share : Market cap / shares outstanding

Best Used For: Large caps, utilities, mature industrials
"""

import yfinance as yf

from .config.constants import VALUATION_DEFAULTS
from .config.logging_config import (
    get_logger,
    log_data_fetch,
    log_error_with_context,
)
from .error_handling import create_error_context, handle_valuation_error
from .exceptions import InsufficientDataError, ModelNotSuitableError

logger = get_logger(__name__)

PROJECTION_YEARS = VALUATION_DEFAULTS.DCF_PROJECTION_YEARS


def project_fcfs(initial_fcf: float, growth_rates: list[float]) -> list[float]:
    """
    Projects free cash flows over the projection horizon.

    Parameters:
        initial_fcf (float): The base free cash flow.
        growth_rates (list[float]): Annual growth rates for each projection year.

    Returns:
        list[float]: Projected FCF values for each year.
    """
    fcfs = []
    fcf = initial_fcf
    for g in growth_rates:
        fcf *= 1 + g
        fcfs.append(fcf)
    return fcfs


def discounted_sum(values: list[float], rate: float) -> float:
    """
    Computes the present value (NPV) of a series of future values.

    Parameters:
        values (list[float]): Future cash flows.
        rate (float): Annual discount rate.

    Returns:
        float: Sum of discounted cash flows.
    """
    return sum(v / (1 + rate) ** (i + 1) for i, v in enumerate(values))


def calculate_dcf(
    ticker: str,
    fcf: float = None,
    shares: float = None,
    cash: float = None,
    debt: float = None,
    current_price: float = None,
    growth_rates: list[float] = None,
    discount_rate: float = VALUATION_DEFAULTS.DCF_DISCOUNT_RATE,
    terminal_growth: float = VALUATION_DEFAULTS.DCF_TERMINAL_GROWTH,
    projection_years: int = PROJECTION_YEARS,
    use_normalized_fcf: bool = True,
    verbose: bool = True,
) -> dict:
    """
    Calculate the DCF-based valuation for a given ticker.

    Data is fetched from yfinance. In auto mode, the function computes a normalized free
    cash flow (FCF) from historical cash flow data to avoid distortions from one-off events.
    If market data is not available (e.g., a dummy ticker), a warning is issued and provided
    manual inputs are used.

    Parameters:
        ticker (str): Stock ticker.
        fcf (float, optional): TTM free cash flow. If None, it is taken from market data.
        shares (float, optional): Shares outstanding.
        cash (float, optional): Total cash & equivalents.
        debt (float, optional): Total debt.
        current_price (float, optional): Current market price.
        growth_rates (list[float], optional): Annual projection growth rates. If None, defaults are inferred.
        discount_rate (float, optional): The discount rate (WACC). Defaults to 0.12.
        terminal_growth (float, optional): Terminal (perpetual) growth rate. Defaults to 0.02.
        projection_years (int, optional): Number of years to project FCF. Defaults to 10.
        use_normalized_fcf (bool, optional): Whether to compute normalized FCF from historical data.
        verbose (bool, optional): Whether to print valuation details.

    Returns:
        dict: A dictionary with valuation details including:
              - fair_value_per_share: The estimated fair share price.
              - enterprise_value: The DCF-estimated total enterprise value.
              - estimated_market_cap: enterprise_value - debt + cash.
              - Other inputs and intermediate values.
    """
    # Create error context for comprehensive error handling
    create_error_context(ticker=ticker, model="DCF", function_name="calculate_dcf")

    try:
        stock = yf.Ticker(ticker)

        try:
            info = stock.info
            log_data_fetch(logger, ticker, "market_data", True)
        except Exception as e:
            info = {}
            log_data_fetch(logger, ticker, "market_data", False, error=str(e))
            if verbose:
                logger.warning(
                    f"Unable to retrieve market data for {ticker}, using manual inputs",
                    extra={"ticker": ticker, "error": str(e)}
                )

        # Autofill inputs from stock.info if missing:
        if fcf is None:
            fcf = info.get("freeCashflow")
        if shares is None:
            shares = info.get("sharesOutstanding")
        if cash is None:
            cash = info.get("totalCash", 0)
        if debt is None:
            debt = info.get("totalDebt", 0)
        if current_price is None:
            current_price = info.get("currentPrice")

        # When market data is not available, you must supply fcf, shares, and current_price manually.
        if (not info) and any(x is None for x in [fcf, shares, current_price]):
            missing_fields = []
            if fcf is None: missing_fields.append("fcf")
            if shares is None: missing_fields.append("shares")
            if current_price is None: missing_fields.append("current_price")
            raise InsufficientDataError(ticker, missing_fields)

        # Use normalized FCF if enabled.
        if use_normalized_fcf:
            try:
                cf_df = stock.cashflow
                if not cf_df.empty:
                    if "Free Cash Flow" in cf_df.index:
                        norm_fcf = cf_df.loc["Free Cash Flow"].mean()
                    else:
                        norm_fcf = (
                            cf_df.loc["Total Cash From Operating Activities"]
                            - cf_df.loc["Capital Expenditures"]
                        ).mean()
                else:
                    # If cashflow data is unavailable, fallback to provided fcf.
                    norm_fcf = fcf
            except Exception as e:
                norm_fcf = fcf
                if verbose:
                    logger.warning(
                        f"Could not compute normalized FCF for {ticker}, using TTM FCF",
                        extra={"ticker": ticker, "error": str(e), "fallback_fcf": fcf}
                    )
        else:
            norm_fcf = fcf

        base_fcf = norm_fcf

        if any(x is None for x in [base_fcf, shares, current_price]):
            missing_fields = []
            if base_fcf is None: missing_fields.append("fcf")
            if shares is None: missing_fields.append("shares")
            if current_price is None: missing_fields.append("current_price")
            raise InsufficientDataError(ticker, missing_fields)

        # Check for inappropriate DCF application (biotech/pharma with negative FCF)
        sector = info.get('sector', '').lower()
        industry = info.get('industry', '').lower()

        is_biotech_pharma = (
            'biotechnology' in industry or
            'pharmaceutical' in industry or
            'biotech' in industry or
            ('healthcare' in sector and any(keyword in industry for keyword in ['drug', 'medicine', 'therapeutic']))
        )

        if is_biotech_pharma and base_fcf < 0:
            # DCF is inappropriate for pre-profitability biotech companies
            raise ModelNotSuitableError(
                "DCF",
                ticker,
                f"Biotech/pharma company with negative FCF (${base_fcf:,.0f}). Use pipeline-based valuation methods instead."
            )

        if base_fcf < 0 and abs(base_fcf) > info.get('totalCash', 0):
            # Very negative FCF that exceeds cash reserves suggests unsustainable model
            years_of_cash = info.get('totalCash', 0) / abs(base_fcf) if base_fcf < 0 else float('inf')
            if years_of_cash < 2:
                raise ModelNotSuitableError(
                    "DCF",
                    ticker,
                    f"Severe negative FCF (${base_fcf:,.0f}) with limited cash runway ({years_of_cash:.1f} years). Company may face financial distress."
                )

        # If growth rates are not provided, infer from revenueGrowth or default to 5%.
        if growth_rates is None:
            inferred_growth = info.get("revenueGrowth", 0.05)
            if inferred_growth < 0:
                inferred_growth = 0.00
            growth_rates = [inferred_growth * (1 - 0.1 * i) for i in range(projection_years)]

        # Project FCFs over the projection period.
        fcfs = project_fcfs(base_fcf, growth_rates)

        # Terminal Value: Using the Gordon Growth Model.
        TV = fcfs[-1] * (1 + terminal_growth) / (discount_rate - terminal_growth)
        tv_pv = TV / ((1 + discount_rate) ** projection_years)

        # NPV of projected FCFs (years 1 to projection_years).
        npv_fcf = discounted_sum(fcfs, discount_rate)

        # Enterprise value from DCF.
        enterprise_value = npv_fcf + tv_pv

        # Estimated market cap from our valuation.
        estimated_market_cap = enterprise_value - debt + cash

        # Fair value per share.
        fair_value_per_share = estimated_market_cap / shares

        # Calculate margin of safety (always, not just when verbose)
        margin = (fair_value_per_share - current_price) / current_price if current_price > 0 else 0

        if verbose:
            logger.info(
                f"DCF valuation completed for {ticker}",
                extra={
                    "ticker": ticker,
                    "current_price": current_price,
                    "fair_value_per_share": fair_value_per_share,
                    "margin_of_safety": margin,
                    "estimated_market_cap": estimated_market_cap,
                    "normalized_fcf": base_fcf,
                    "growth_rates": growth_rates
                }
            )
            # Still print summary for user when verbose=True
            print(f"\nDCF Valuation for {ticker}")
            print("-" * 40)
            print(f"Current Price:        ${current_price:,.2f}")
            print(f"Estimated Market Cap: ${estimated_market_cap:,.2f}")
            print(f"Fair Value per Share: ${fair_value_per_share:,.2f}")
            print(f"Margin of Safety:      {margin * 100:.1f}%")
            print(f"Normalized FCF:       ${base_fcf:,.0f}")
            print("Growth Rates:         " + ", ".join(f"{g:.1%}" for g in growth_rates))

        return {
            "ticker": ticker,
            "fair_value_per_share": fair_value_per_share,
            "current_price": current_price,
            "margin_of_safety": margin,
            "fcf_projection": fcfs,
            "TV": TV,
            "tv_pv": tv_pv,
            "npv_fcf": npv_fcf,
            "enterprise_value": enterprise_value,
            "estimated_market_cap": estimated_market_cap,
            "discount_rate": discount_rate,
            "growth_rates": growth_rates,
            "inputs": {
                "normalized_fcf": base_fcf,
                "shares": shares,
                "cash": cash,
                "debt": debt,
            },
        }

    except Exception as e:
        # Handle any unexpected errors with comprehensive error context
        error_info = handle_valuation_error(e, ticker, "DCF")

        # Log the error with full context
        log_error_with_context(
            logger,
            error_info.technical_message,
            **{
                "ticker": ticker,
                "model": "DCF",
                "error_id": error_info.error_id,
                "user_message": error_info.user_message
            }
        )

        # Re-raise the original exception to maintain existing behavior
        raise
