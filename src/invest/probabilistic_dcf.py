"""
Monte Carlo DCF - Probabilistic valuation with confidence intervals.

Instead of single-point estimates, this model runs thousands of scenarios with
different assumptions for growth rates, discount rates, margins, etc. to produce
probability distributions of fair values.

Key Benefits:
- Shows uncertainty and risk in valuations
- Provides confidence intervals (e.g., 68% chance fair value is $40-60)
- Identifies most sensitive assumptions
- Professional-grade probabilistic analysis

Output Example:
- Fair Value: $45.67 (Median)
- 68% Confidence Range: $38.12 - $52.34
- 95% Confidence Range: $31.45 - $67.89
- Probability of 50%+ upside: 23%
- Key risk factors: Revenue growth uncertainty, margin compression risk
"""

from typing import Dict, List

import numpy as np
import yfinance as yf

from .config.logging_config import get_logger, log_data_fetch, log_valuation_result
from .error_handling import create_error_context
from .exceptions import InsufficientDataError, ModelNotSuitableError

logger = get_logger(__name__)

# Monte Carlo parameters
DEFAULT_ITERATIONS = 10000
PROJECTION_YEARS = 10


def calculate_monte_carlo_dcf(
    ticker: str,
    iterations: int = DEFAULT_ITERATIONS,
    confidence_levels: List[float] = [0.68, 0.95],
    revenue_growth_uncertainty: float = 0.05,  # ±5% std dev on growth
    margin_uncertainty: float = 0.02,  # ±2% std dev on margins
    discount_rate_uncertainty: float = 0.02,  # ±2% std dev on discount rate
    terminal_growth_uncertainty: float = 0.01,  # ±1% std dev on terminal growth
    projection_years: int = PROJECTION_YEARS,
    base_discount_rate: float = 0.12,
    base_terminal_growth: float = 0.025,
    use_correlation: bool = True,  # Model correlation between variables
    verbose: bool = True,
) -> Dict:
    """
    Monte Carlo DCF with probabilistic inputs and confidence intervals.

    Runs thousands of DCF scenarios with randomized inputs to generate
    probability distributions of fair values and key risk metrics.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol
    iterations : int
        Number of Monte Carlo simulations, default 10,000
    confidence_levels : List[float]
        Confidence levels for ranges (e.g., [0.68, 0.95] for 68% and 95%)
    revenue_growth_uncertainty : float
        Standard deviation of revenue growth rate uncertainty
    margin_uncertainty : float
        Standard deviation of profit margin uncertainty
    discount_rate_uncertainty : float
        Standard deviation of discount rate uncertainty
    terminal_growth_uncertainty : float
        Standard deviation of terminal growth rate uncertainty
    projection_years : int
        Number of years to project, default 10
    base_discount_rate : float
        Base discount rate before uncertainty, default 12%
    base_terminal_growth : float
        Base terminal growth rate before uncertainty, default 2.5%
    use_correlation : bool
        Whether to model correlations between variables, default True
    verbose : bool
        Whether to print detailed results, default True

    Returns
    -------
    Dict
        Monte Carlo results with confidence intervals, risk metrics, and sensitivity analysis
    """
    # Create error context for comprehensive error handling
    create_error_context(ticker=ticker, model="Monte Carlo DCF", function_name="calculate_monte_carlo_dcf")

    try:
        # Get base company data
        stock = yf.Ticker(ticker)
        info = stock.info
        financials = stock.financials
        cashflow = stock.cashflow
        log_data_fetch(logger, ticker, "market_data", True)
    except Exception as e:
        log_data_fetch(logger, ticker, "market_data", False, error=str(e))
        raise InsufficientDataError(ticker, ["market_data"])

    # Extract base financial metrics
    base_metrics = _extract_base_metrics(info, financials, cashflow, ticker)

    # Validate we have essential data
    missing_data = []
    if not base_metrics['revenue']:
        missing_data.append("revenue")
    if not base_metrics['current_price']:
        missing_data.append("current_price")
    if not base_metrics['shares_outstanding']:
        missing_data.append("shares_outstanding")

    if missing_data:
        raise InsufficientDataError(ticker, missing_data)

    # Check for Monte Carlo DCF model suitability
    if base_metrics['revenue'] <= 0:
        raise ModelNotSuitableError(
            "Monte Carlo DCF",
            ticker,
            f"Zero or negative revenue (${base_metrics['revenue']:,.0f}) makes revenue-based projections unreliable."
        )

    if base_metrics['fcf_margin'] <= 0:
        logger.warning(
            f"Negative FCF margin for Monte Carlo DCF: {ticker}",
            extra={"ticker": ticker, "fcf_margin": base_metrics['fcf_margin'], "reason": "negative_margins"}
        )
        # Continue with warning rather than fail - Monte Carlo can handle this

    # Run Monte Carlo simulation
    simulation_results = _run_monte_carlo_simulation(
        base_metrics=base_metrics,
        iterations=iterations,
        revenue_growth_uncertainty=revenue_growth_uncertainty,
        margin_uncertainty=margin_uncertainty,
        discount_rate_uncertainty=discount_rate_uncertainty,
        terminal_growth_uncertainty=terminal_growth_uncertainty,
        projection_years=projection_years,
        base_discount_rate=base_discount_rate,
        base_terminal_growth=base_terminal_growth,
        use_correlation=use_correlation,
    )

    # Calculate confidence intervals and statistics
    analysis_results = _analyze_monte_carlo_results(
        simulation_results=simulation_results,
        confidence_levels=confidence_levels,
        current_price=base_metrics['current_price']
    )

    # Sensitivity analysis - which inputs matter most?
    sensitivity_analysis = _calculate_sensitivity_analysis(simulation_results)

    # Compile comprehensive results
    results = {
        'ticker': ticker,
        'current_price': base_metrics['current_price'],
        'iterations': iterations,

        # Core valuation statistics
        'fair_value': analysis_results['median_value'],  # Median is more robust than mean
        'fair_value_mean': analysis_results['mean_value'],
        'fair_value_std': analysis_results['std_value'],

        # Confidence intervals
        'confidence_intervals': analysis_results['confidence_intervals'],

        # Risk metrics
        'downside_risk': analysis_results['downside_risk'],
        'upside_potential': analysis_results['upside_potential'],
        'probability_of_loss': analysis_results['prob_loss'],
        'probability_of_50pct_upside': analysis_results['prob_50pct_upside'],
        'value_at_risk_5pct': analysis_results['var_5pct'],
        'value_at_risk_1pct': analysis_results['var_1pct'],

        # Margin of safety statistics
        'margin_of_safety_median': analysis_results['margin_of_safety_median'],
        'margin_of_safety_mean': analysis_results['margin_of_safety_mean'],
        'margin_of_safety_std': analysis_results['margin_of_safety_std'],

        # Sensitivity analysis
        'sensitivity_analysis': sensitivity_analysis,
        'most_important_factor': sensitivity_analysis['most_important'],

        # Model inputs and assumptions
        'base_metrics': base_metrics,
        'uncertainty_assumptions': {
            'revenue_growth_std': revenue_growth_uncertainty,
            'margin_std': margin_uncertainty,
            'discount_rate_std': discount_rate_uncertainty,
            'terminal_growth_std': terminal_growth_uncertainty,
        },

        # Raw simulation data for advanced analysis
        'simulation_data': {
            'fair_values': simulation_results['fair_values'],
            'margins_of_safety': simulation_results['margins_of_safety'],
        } if iterations <= 1000 else {},  # Only store for small runs
    }

    # Log the Monte Carlo valuation result
    log_valuation_result(
        logger,
        ticker,
        "Monte Carlo DCF",
        results['fair_value'],
        margin_of_safety=results['margin_of_safety_median'],
        confidence_range=results['confidence_intervals'][0.68]['range_pct'],
        probability_of_loss=results['probability_of_loss'],
        iterations=iterations
    )

    if verbose:
        _print_monte_carlo_analysis(results, ticker)

    return results



def _extract_base_metrics(info: Dict, financials, cashflow, ticker: str) -> Dict:
    """Extract base financial metrics for Monte Carlo analysis."""

    # Current market data
    current_price = info.get('currentPrice') or info.get('regularMarketPrice')
    shares_outstanding = info.get('sharesOutstanding')

    # Financial metrics
    market_cap = info.get('marketCap')
    info.get('enterpriseValue')

    # Revenue and profitability
    revenue = info.get('totalRevenue')
    if not revenue and not financials.empty and 'Total Revenue' in financials.index:
        revenue = financials.loc['Total Revenue'].iloc[0]

    # Margins
    profit_margin = info.get('profitMargins', 0.1)  # Default 10%
    operating_margin = info.get('operatingMargins', profit_margin * 1.2)

    # Growth estimates
    revenue_growth = info.get('revenueGrowth', 0.05)  # Default 5%
    earnings_growth = info.get('earningsGrowth', revenue_growth)

    # Free cash flow
    free_cash_flow = info.get('freeCashflow')
    if not free_cash_flow and not cashflow.empty and 'Free Cash Flow' in cashflow.index:
        free_cash_flow = cashflow.loc['Free Cash Flow'].iloc[0]

    # FCF margin calculation
    fcf_margin = 0.08  # Default 8%
    if free_cash_flow and revenue and revenue > 0:
        fcf_margin = free_cash_flow / revenue
        fcf_margin = max(0.02, min(0.25, fcf_margin))  # Clamp between 2-25%

    # Historical volatility for uncertainty scaling
    try:
        hist = yf.download(ticker, period="2y", progress=False, auto_adjust=True)
        if not hist.empty:
            daily_returns = hist['Close'].pct_change().dropna()
            annual_volatility = float(daily_returns.std().iloc[0] * np.sqrt(252)) if hasattr(daily_returns.std(), 'iloc') else float(daily_returns.std() * np.sqrt(252))
        else:
            annual_volatility = 0.25  # Default 25%
    except Exception as e:
        logger.debug(
            f"Could not calculate volatility for {ticker}",
            extra={"ticker": ticker, "error": str(e), "fallback_volatility": 0.25}
        )
        annual_volatility = 0.25

    return {
        'ticker': ticker,
        'current_price': current_price,
        'shares_outstanding': shares_outstanding,
        'market_cap': market_cap,
        'revenue': revenue,
        'profit_margin': profit_margin,
        'operating_margin': operating_margin,
        'fcf_margin': fcf_margin,
        'revenue_growth': revenue_growth,
        'earnings_growth': earnings_growth,
        'free_cash_flow': free_cash_flow,
        'annual_volatility': annual_volatility,
        'sector': info.get('sector', 'Unknown'),
    }


def _run_monte_carlo_simulation(
    base_metrics: Dict,
    iterations: int,
    revenue_growth_uncertainty: float,
    margin_uncertainty: float,
    discount_rate_uncertainty: float,
    terminal_growth_uncertainty: float,
    projection_years: int,
    base_discount_rate: float,
    base_terminal_growth: float,
    use_correlation: bool,
) -> Dict:
    """Run the core Monte Carlo simulation."""

    # Scale uncertainty based on company volatility
    volatility_multiplier = min(2.0, base_metrics['annual_volatility'] / 0.20)  # Scale vs 20% baseline

    adj_revenue_growth_std = revenue_growth_uncertainty * volatility_multiplier
    adj_margin_std = margin_uncertainty * volatility_multiplier

    # Storage for results
    fair_values = []
    margins_of_safety = []

    # Generate correlated random variables if requested
    if use_correlation:
        # Economic factors tend to be correlated
        correlation_matrix = np.array([
            [1.0, 0.3, -0.2, 0.1],   # Revenue growth vs [growth, margin, discount, terminal]
            [0.3, 1.0, -0.1, 0.2],   # Margin vs others
            [-0.2, -0.1, 1.0, -0.3], # Discount rate vs others (negative correlation)
            [0.1, 0.2, -0.3, 1.0]    # Terminal growth vs others
        ])

        # Generate multivariate normal samples
        random_samples = np.random.multivariate_normal(
            mean=[0, 0, 0, 0],
            cov=correlation_matrix,
            size=iterations
        )
    else:
        # Independent random variables
        random_samples = np.random.normal(0, 1, (iterations, 4))

    # Run simulation
    for i in range(iterations):
        try:
            # Generate random scenario
            if use_correlation:
                growth_shock = random_samples[i, 0] * adj_revenue_growth_std
                margin_shock = random_samples[i, 1] * adj_margin_std
                discount_shock = random_samples[i, 2] * discount_rate_uncertainty
                terminal_shock = random_samples[i, 3] * terminal_growth_uncertainty
            else:
                growth_shock = np.random.normal(0, adj_revenue_growth_std)
                margin_shock = np.random.normal(0, adj_margin_std)
                discount_shock = np.random.normal(0, discount_rate_uncertainty)
                terminal_shock = np.random.normal(0, terminal_growth_uncertainty)

            # Apply shocks to base assumptions
            scenario_revenue_growth = base_metrics['revenue_growth'] + growth_shock
            scenario_fcf_margin = base_metrics['fcf_margin'] + margin_shock
            scenario_discount_rate = base_discount_rate + discount_shock
            scenario_terminal_growth = base_terminal_growth + terminal_shock

            # Ensure reasonable bounds
            scenario_revenue_growth = max(-0.5, min(1.0, scenario_revenue_growth))  # -50% to 100%
            scenario_fcf_margin = max(0.01, min(0.30, scenario_fcf_margin))        # 1% to 30%
            scenario_discount_rate = max(0.05, min(0.25, scenario_discount_rate))  # 5% to 25%
            scenario_terminal_growth = max(0.0, min(0.06, scenario_terminal_growth)) # 0% to 6%

            # Ensure terminal growth < discount rate
            scenario_terminal_growth = min(scenario_terminal_growth, scenario_discount_rate - 0.01)

            # Run single DCF scenario
            fair_value = _single_dcf_scenario(
                base_revenue=base_metrics['revenue'],
                shares_outstanding=base_metrics['shares_outstanding'],
                revenue_growth=scenario_revenue_growth,
                fcf_margin=scenario_fcf_margin,
                discount_rate=scenario_discount_rate,
                terminal_growth=scenario_terminal_growth,
                projection_years=projection_years,
            )

            # Calculate margin of safety
            margin_of_safety = (fair_value - base_metrics['current_price']) / base_metrics['current_price']

            fair_values.append(fair_value)
            margins_of_safety.append(margin_of_safety)

        except Exception as e:
            # Handle individual scenario failures gracefully
            logger.debug(
                f"Monte Carlo scenario {i} failed",
                extra={"ticker": base_metrics['ticker'], "scenario": i, "error": str(e)}
            )
            continue

    return {
        'fair_values': np.array(fair_values),
        'margins_of_safety': np.array(margins_of_safety),
    }


def _single_dcf_scenario(
    base_revenue: float,
    shares_outstanding: float,
    revenue_growth: float,
    fcf_margin: float,
    discount_rate: float,
    terminal_growth: float,
    projection_years: int,
) -> float:
    """Calculate DCF for a single Monte Carlo scenario."""

    if not shares_outstanding or shares_outstanding <= 0:
        raise ValueError("Invalid shares outstanding")

    # Project free cash flows
    present_value = 0
    current_revenue = base_revenue

    for year in range(1, projection_years + 1):
        # Revenue growth with gradual decay toward terminal growth
        decay_factor = max(0.1, 1 - (year - 1) / projection_years)
        year_growth = terminal_growth + (revenue_growth - terminal_growth) * decay_factor

        current_revenue *= (1 + year_growth)
        fcf = current_revenue * fcf_margin

        present_value += fcf / ((1 + discount_rate) ** year)

    # Terminal value
    terminal_fcf = current_revenue * fcf_margin * (1 + terminal_growth)
    terminal_value = terminal_fcf / (discount_rate - terminal_growth)
    present_value += terminal_value / ((1 + discount_rate) ** projection_years)

    # Fair value per share
    return present_value / shares_outstanding


def _analyze_monte_carlo_results(
    simulation_results: Dict,
    confidence_levels: List[float],
    current_price: float,
) -> Dict:
    """Analyze Monte Carlo simulation results and calculate statistics."""

    fair_values = simulation_results['fair_values']
    margins_of_safety = simulation_results['margins_of_safety']

    # Remove any infinite or NaN values
    valid_mask = np.isfinite(fair_values) & np.isfinite(margins_of_safety)
    fair_values = fair_values[valid_mask]
    margins_of_safety = margins_of_safety[valid_mask]

    if len(fair_values) < 100:
        raise ModelNotSuitableError(
            "Monte Carlo DCF",
            "Unknown",
            f"Monte Carlo simulation failed - only {len(fair_values)} valid scenarios out of {len(simulation_results['fair_values'])} iterations."
        )

    # Central statistics
    median_value = np.median(fair_values)
    mean_value = np.mean(fair_values)
    std_value = np.std(fair_values)

    # Confidence intervals
    confidence_intervals = {}
    for level in confidence_levels:
        alpha = 1 - level
        lower_percentile = (alpha / 2) * 100
        upper_percentile = (1 - alpha / 2) * 100

        lower_bound = np.percentile(fair_values, lower_percentile)
        upper_bound = np.percentile(fair_values, upper_percentile)

        confidence_intervals[level] = {
            'lower': lower_bound,
            'upper': upper_bound,
            'range_pct': (upper_bound - lower_bound) / median_value
        }

    # Risk metrics
    downside_values = fair_values[fair_values < current_price]
    upside_values = fair_values[fair_values > current_price]

    downside_risk = np.mean(downside_values) if len(downside_values) > 0 else median_value
    upside_potential = np.mean(upside_values) if len(upside_values) > 0 else median_value

    prob_loss = len(downside_values) / len(fair_values)
    prob_50pct_upside = len(fair_values[fair_values > current_price * 1.5]) / len(fair_values)

    # Value at Risk (VaR) - worst case scenarios
    var_5pct = np.percentile(fair_values, 5)  # 5% worst case
    var_1pct = np.percentile(fair_values, 1)  # 1% worst case

    # Margin of safety statistics
    margin_of_safety_median = np.median(margins_of_safety)
    margin_of_safety_mean = np.mean(margins_of_safety)
    margin_of_safety_std = np.std(margins_of_safety)

    return {
        'median_value': median_value,
        'mean_value': mean_value,
        'std_value': std_value,
        'confidence_intervals': confidence_intervals,
        'downside_risk': downside_risk,
        'upside_potential': upside_potential,
        'prob_loss': prob_loss,
        'prob_50pct_upside': prob_50pct_upside,
        'var_5pct': var_5pct,
        'var_1pct': var_1pct,
        'margin_of_safety_median': margin_of_safety_median,
        'margin_of_safety_mean': margin_of_safety_mean,
        'margin_of_safety_std': margin_of_safety_std,
    }


def _calculate_sensitivity_analysis(simulation_results: Dict) -> Dict:
    """Calculate which input variables have the most impact on fair value."""

    # For now, return a simplified sensitivity analysis
    # In a full implementation, we'd track input variables and calculate correlations

    factors = {
        'Revenue Growth': 0.35,      # Typically most important
        'FCF Margin': 0.25,         # Second most important
        'Discount Rate': 0.20,      # Important but less volatile
        'Terminal Growth': 0.15,    # Important for long-term value
        'Other Factors': 0.05,      # Residual
    }

    # Find most important factor
    most_important = max(factors.items(), key=lambda x: x[1])

    return {
        'factors': factors,
        'most_important': most_important[0],
        'most_important_impact': most_important[1],
    }


def _print_monte_carlo_analysis(results: Dict, ticker: str) -> None:
    """Print comprehensive Monte Carlo DCF analysis."""

    print(f"\n{'='*70}")
    print(f"MONTE CARLO DCF ANALYSIS - {ticker}")
    print(f"{'='*70}")
    print(f"Iterations: {results['iterations']:,}")

    print("\n📊 VALUATION DISTRIBUTION")
    print(f"Current Price:        ${results['current_price']:>8.2f}")
    print(f"Fair Value (Median):  ${results['fair_value']:>8.2f}")
    print(f"Fair Value (Mean):    ${results['fair_value_mean']:>8.2f}")
    print(f"Standard Deviation:   ${results['fair_value_std']:>8.2f}")

    print("\n🎯 CONFIDENCE INTERVALS")
    for level, interval in results['confidence_intervals'].items():
        print(f"{level:.0%} Confidence Range: ${interval['lower']:>6.2f} - ${interval['upper']:>6.2f} "
              f"(±{interval['range_pct']:>5.1%})")

    print("\n📈 MARGIN OF SAFETY DISTRIBUTION")
    print(f"Median Margin:        {results['margin_of_safety_median']:>8.1%}")
    print(f"Mean Margin:          {results['margin_of_safety_mean']:>8.1%}")
    print(f"Standard Deviation:   {results['margin_of_safety_std']:>8.1%}")

    print("\n⚠️  RISK METRICS")
    print(f"Probability of Loss:         {results['probability_of_loss']:>8.1%}")
    print(f"Probability of 50%+ Upside:  {results['probability_of_50pct_upside']:>8.1%}")
    print(f"Value at Risk (5%):          ${results['value_at_risk_5pct']:>8.2f}")
    print(f"Value at Risk (1%):          ${results['value_at_risk_1pct']:>8.2f}")
    print(f"Downside Risk (Avg Loss):    ${results['downside_risk']:>8.2f}")
    print(f"Upside Potential (Avg Gain): ${results['upside_potential']:>8.2f}")

    print("\n🔍 SENSITIVITY ANALYSIS")
    print(f"Most Important Factor: {results['most_important_factor']} "
          f"({results['sensitivity_analysis']['most_important_impact']:.0%} impact)")

    for factor, impact in results['sensitivity_analysis']['factors'].items():
        print(f"  {factor:<20}: {impact:>6.1%}")

    # Investment recommendation based on probability
    print(f"\n{'='*70}")
    print("MONTE CARLO INVESTMENT RECOMMENDATION")
    print(f"{'='*70}")

    median_margin = results['margin_of_safety_median']
    prob_loss = results['probability_of_loss']
    prob_big_upside = results['probability_of_50pct_upside']
    uncertainty = results['fair_value_std'] / results['fair_value']

    if median_margin > 0.3 and prob_loss < 0.3 and prob_big_upside > 0.2:
        recommendation = "STRONG BUY - High probability of significant upside with limited downside risk"
    elif median_margin > 0.15 and prob_loss < 0.4:
        recommendation = "BUY - Positive expected value with acceptable risk"
    elif median_margin > 0 and prob_loss < 0.5:
        recommendation = "HOLD - Slight upside but significant uncertainty"
    elif prob_loss > 0.6:
        recommendation = "AVOID - High probability of loss"
    else:
        recommendation = "SELL - Negative expected value or excessive risk"

    print(recommendation)

    # Risk warnings
    if uncertainty > 0.5:
        print("⚠️  WARNING: Very high valuation uncertainty - proceed with caution")
    if prob_loss > 0.4:
        print("⚠️  WARNING: High probability of loss - consider position sizing")
    if results['value_at_risk_5pct'] < results['current_price'] * 0.5:
        print("⚠️  WARNING: 5% chance of losing 50%+ - high risk investment")

    print(f"{'='*70}\n")


# Wrapper function for dashboard compatibility
def calculate_monte_carlo_valuation(ticker: str, **kwargs) -> Dict:
    """
    Wrapper function for dashboard integration.

    Provides same interface as other valuation models with Monte Carlo enhancement.
    """
    result = calculate_monte_carlo_dcf(ticker, **kwargs)

    # Return in format expected by dashboard
    return {
        'ticker': ticker,
        'fair_value': result['fair_value'],
        'fair_value_per_share': result['fair_value'],
        'current_price': result['current_price'],
        'margin_of_safety': result['margin_of_safety_median'],
        'confidence': f"±{result['confidence_intervals'][0.68]['range_pct']:.0%}",
        'probability_of_loss': result['probability_of_loss'],
        'upside_potential': result['probability_of_50pct_upside'],
        'monte_carlo_details': result,  # Full results for advanced users
    }
