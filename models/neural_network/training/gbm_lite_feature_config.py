"""
GBM Lite Feature Configuration - Maximum compatibility with limited history.

This is an ultra-lightweight version optimized for maximum stock coverage:
- NO lag periods (removes need for historical quarters)
- NO rolling windows (removes need for time series)
- NO YoY changes (removes need for year-ago data)
- Only QoQ changes (requires just 2 quarters)
- Focus on current snapshot features

This should work for ANY stock with at least 2 quarters of data.
"""

# Same fundamental features as full GBM
FUNDAMENTAL_FEATURES = [
    # Profitability
    'profit_margins',
    'operating_margins',
    'gross_margins',

    # Returns
    'return_on_equity',
    'return_on_assets',

    # Growth
    'revenue_growth',
    'earnings_growth',

    # Balance Sheet Strength
    'current_ratio',
    'quick_ratio',
    'debt_to_equity',

    # Valuation Multiples
    'pe_ratio',
    'pb_ratio',
    'ps_ratio',
    'enterprise_to_ebitda',
    'enterprise_to_revenue',

    # Dividends
    'dividend_yield',
    'payout_ratio',

    # Company Characteristics
    'market_cap',  # Will be log-transformed
    'beta',
]

# Market regime features
MARKET_FEATURES = [
    'vix',
    'treasury_10y',
]

# Price-based momentum features (computed from price_history)
PRICE_FEATURES = [
    'returns_1m',
    'returns_3m',
    'returns_6m',
    'returns_1y',
    'volatility',
    'volume_trend',
]

# Absolute fundamental metrics (for computing yields)
CASHFLOW_FEATURES = [
    'free_cashflow',
    'operating_cashflow',
    'trailing_eps',
    'book_value',
]

# All base features to engineer
BASE_FEATURES = FUNDAMENTAL_FEATURES + MARKET_FEATURES + PRICE_FEATURES

# ULTRA-LITE CONFIGURATION: Maximum compatibility
LAG_PERIODS = []  # No lags - use only current values
ROLLING_WINDOWS = []  # No rolling stats - avoid time series requirements
ROLLING_STATS = []  # No stats needed

# Minimum quarters needed for this configuration
MIN_QUARTERS_REQUIRED = 2  # Only need current + 1 prior for QoQ changes

# Categorical features
CATEGORICAL_FEATURES = ['sector']


def get_all_feature_names():
    """
    Get complete list of all feature names after engineering.

    Returns
    -------
    list
        List of all feature column names in order
    """
    features = []

    # Base features (current snapshot only)
    features.extend(BASE_FEATURES)

    # Computed yields (created from cashflow features)
    features.extend(['fcf_yield', 'ocf_yield', 'earnings_yield'])

    # Log-transformed market cap
    features.append('log_market_cap')

    # Engineered features for each base feature
    for feat in BASE_FEATURES:
        # Lags: NONE (removed for compatibility)

        # Changes: Only QoQ (requires 2 quarters total)
        features.append(f'{feat}_qoq')
        # NO YoY - would require 5 quarters

        # Rolling statistics: NONE (removed for compatibility)

        # Missingness flag
        features.append(f'{feat}_missing')

    # Categorical
    features.extend(CATEGORICAL_FEATURES)

    return features


def get_snapshot_query_columns():
    """
    Get SQL columns needed from snapshots table.

    Returns
    -------
    list
        List of column names to query
    """
    return (
        ['ticker', 'snapshot_date', 'snapshot_id', 'sector'] +
        FUNDAMENTAL_FEATURES +
        MARKET_FEATURES +
        CASHFLOW_FEATURES
    )


def get_min_quarters_required():
    """
    Get minimum quarters needed for GBM Lite.

    Returns
    -------
    int
        Minimum number of quarters required
    """
    # Ultra-minimal requirements:
    # - Current quarter (1)
    # - Previous quarter for QoQ change (1)
    # Total: 2 quarters
    return MIN_QUARTERS_REQUIRED
