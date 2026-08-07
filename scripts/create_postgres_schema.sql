-- PostgreSQL schema for the invest database
-- Translated from SQLite schema in data/stock_data.db

-- ── Core tables ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS assets (
    id SERIAL PRIMARY KEY,
    symbol TEXT NOT NULL UNIQUE,
    asset_type TEXT NOT NULL,
    name TEXT,
    sector TEXT,
    industry TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS current_stock_data (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL UNIQUE,

    -- Basic info
    current_price DOUBLE PRECISION,
    market_cap DOUBLE PRECISION,
    sector TEXT,
    industry TEXT,
    long_name TEXT,
    short_name TEXT,
    currency TEXT,
    exchange TEXT,
    country TEXT,

    -- Financial metrics
    trailing_pe DOUBLE PRECISION,
    forward_pe DOUBLE PRECISION,
    price_to_book DOUBLE PRECISION,
    return_on_equity DOUBLE PRECISION,
    debt_to_equity DOUBLE PRECISION,
    current_ratio DOUBLE PRECISION,
    revenue_growth DOUBLE PRECISION,
    earnings_growth DOUBLE PRECISION,
    operating_margins DOUBLE PRECISION,
    profit_margins DOUBLE PRECISION,
    total_revenue DOUBLE PRECISION,
    total_cash DOUBLE PRECISION,
    total_debt DOUBLE PRECISION,
    shares_outstanding DOUBLE PRECISION,
    trailing_eps DOUBLE PRECISION,
    book_value DOUBLE PRECISION,
    revenue_per_share DOUBLE PRECISION,
    price_to_sales_ttm DOUBLE PRECISION,

    -- Price data
    price_52w_high DOUBLE PRECISION,
    price_52w_low DOUBLE PRECISION,
    avg_volume BIGINT,
    price_trend_30d DOUBLE PRECISION,

    -- Raw JSON storage
    cashflow_json JSONB,
    balance_sheet_json JSONB,
    income_json JSONB,

    -- Metadata
    fetch_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    financial_currency TEXT,
    exchange_rate_used DOUBLE PRECISION,
    original_currency TEXT
);

CREATE TABLE IF NOT EXISTS fundamental_history (
    id SERIAL PRIMARY KEY,
    asset_id INTEGER NOT NULL REFERENCES assets(id),
    snapshot_date DATE NOT NULL,

    volume DOUBLE PRECISION,
    market_cap DOUBLE PRECISION,
    shares_outstanding DOUBLE PRECISION,

    -- Valuation ratios
    pe_ratio DOUBLE PRECISION,
    pb_ratio DOUBLE PRECISION,
    ps_ratio DOUBLE PRECISION,
    peg_ratio DOUBLE PRECISION,
    price_to_book DOUBLE PRECISION,
    price_to_sales DOUBLE PRECISION,
    enterprise_to_revenue DOUBLE PRECISION,
    enterprise_to_ebitda DOUBLE PRECISION,

    -- Profitability metrics
    profit_margins DOUBLE PRECISION,
    operating_margins DOUBLE PRECISION,
    gross_margins DOUBLE PRECISION,
    ebitda_margins DOUBLE PRECISION,
    return_on_assets DOUBLE PRECISION,
    return_on_equity DOUBLE PRECISION,

    -- Growth metrics
    revenue_growth DOUBLE PRECISION,
    earnings_growth DOUBLE PRECISION,
    earnings_quarterly_growth DOUBLE PRECISION,
    revenue_per_share DOUBLE PRECISION,

    -- Financial health
    total_cash DOUBLE PRECISION,
    total_debt DOUBLE PRECISION,
    debt_to_equity DOUBLE PRECISION,
    current_ratio DOUBLE PRECISION,
    quick_ratio DOUBLE PRECISION,

    -- Cash flow
    operating_cashflow DOUBLE PRECISION,
    free_cashflow DOUBLE PRECISION,

    -- Per-share metrics
    trailing_eps DOUBLE PRECISION,
    forward_eps DOUBLE PRECISION,
    book_value DOUBLE PRECISION,

    -- Dividends
    dividend_rate DOUBLE PRECISION,
    dividend_yield DOUBLE PRECISION,
    payout_ratio DOUBLE PRECISION,

    -- Price changes
    price_change_pct DOUBLE PRECISION,
    volatility DOUBLE PRECISION,
    beta DOUBLE PRECISION,

    -- Moving averages
    fifty_day_average DOUBLE PRECISION,
    two_hundred_day_average DOUBLE PRECISION,
    fifty_two_week_high DOUBLE PRECISION,
    fifty_two_week_low DOUBLE PRECISION,

    -- Macro indicators
    vix DOUBLE PRECISION,
    treasury_10y DOUBLE PRECISION,
    dollar_index DOUBLE PRECISION,
    oil_price DOUBLE PRECISION,
    gold_price DOUBLE PRECISION,
    realistic_return_1y DOUBLE PRECISION,
    realistic_return_3y DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS price_history (
    ticker TEXT NOT NULL,
    date DATE NOT NULL,
    open DOUBLE PRECISION,
    high DOUBLE PRECISION,
    low DOUBLE PRECISION,
    close DOUBLE PRECISION,
    volume DOUBLE PRECISION,
    dividends DOUBLE PRECISION,
    stock_splits DOUBLE PRECISION,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS valuation_results (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    model_name TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fair_value DOUBLE PRECISION,
    current_price DOUBLE PRECISION,
    margin_of_safety DOUBLE PRECISION,
    upside_pct DOUBLE PRECISION,
    suitable BOOLEAN NOT NULL,
    error_message TEXT,
    failure_reason TEXT,
    details_json JSONB,
    confidence DOUBLE PRECISION,
    UNIQUE(ticker, model_name)
);

-- ── Forward returns / company info / models ─────────────────────────────

CREATE TABLE IF NOT EXISTS forward_returns (
    id SERIAL PRIMARY KEY,
    snapshot_id INTEGER NOT NULL,
    horizon TEXT NOT NULL,
    return_pct DOUBLE PRECISION,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(snapshot_id, horizon)
);

CREATE TABLE IF NOT EXISTS company_info (
    id SERIAL PRIMARY KEY,
    asset_id INTEGER NOT NULL REFERENCES assets(id),
    snapshot_id INTEGER NOT NULL,
    info_json JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(snapshot_id)
);

CREATE TABLE IF NOT EXISTS models (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    model_type TEXT NOT NULL,
    version TEXT,
    description TEXT,
    model_path TEXT,
    feature_dim INTEGER,
    trained_date TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ── Scanner ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS scanner_threshold_history (
    id SERIAL PRIMARY KEY,
    date TEXT NOT NULL UNIQUE,
    threshold DOUBLE PRECISION NOT NULL,
    best_score DOUBLE PRECISION,
    stocks_above INTEGER DEFAULT 0,
    notification_sent INTEGER DEFAULT 0,
    notified_ticker TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scanner_score_history (
    id SERIAL PRIMARY KEY,
    date TEXT NOT NULL,
    ticker TEXT NOT NULL,
    opportunity_score DOUBLE PRECISION NOT NULL,
    quality_score DOUBLE PRECISION,
    value_score DOUBLE PRECISION,
    growth_score DOUBLE PRECISION,
    risk_score DOUBLE PRECISION,
    catalyst_score DOUBLE PRECISION,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, ticker)
);

-- ── Macro rates ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS macro_rates (
    rate_name TEXT NOT NULL,
    date DATE NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    source TEXT,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (rate_name, date)
);

-- ── SEC data ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS insider_transactions (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    cik TEXT NOT NULL,
    accession_number TEXT NOT NULL,
    filing_date TEXT NOT NULL,
    transaction_date TEXT NOT NULL,
    reporter_name TEXT NOT NULL,
    reporter_title TEXT,
    transaction_type TEXT NOT NULL,
    shares DOUBLE PRECISION NOT NULL,
    price_per_share DOUBLE PRECISION,
    shares_owned_after DOUBLE PRECISION,
    is_open_market INTEGER DEFAULT 0,
    UNIQUE(accession_number, reporter_name, transaction_date, shares)
);

CREATE TABLE IF NOT EXISTS insider_fetch_log (
    ticker TEXT PRIMARY KEY,
    cik TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    form4_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'ok'
);

CREATE TABLE IF NOT EXISTS activist_stakes (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    cik TEXT NOT NULL,
    accession_number TEXT NOT NULL,
    filing_date TEXT NOT NULL,
    holder_name TEXT NOT NULL,
    form_type TEXT NOT NULL,
    shares_held DOUBLE PRECISION,
    percent_of_class DOUBLE PRECISION,
    purpose_text TEXT,
    is_activist INTEGER DEFAULT 0,
    UNIQUE(accession_number, holder_name)
);

CREATE TABLE IF NOT EXISTS activist_fetch_log (
    ticker TEXT PRIMARY KEY,
    cik TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    filing_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'ok'
);

CREATE TABLE IF NOT EXISTS fund_holdings (
    id SERIAL PRIMARY KEY,
    fund_name TEXT NOT NULL,
    fund_cik TEXT NOT NULL,
    filing_date TEXT NOT NULL,
    quarter TEXT NOT NULL,
    cusip TEXT NOT NULL,
    ticker TEXT,
    issuer_name TEXT,
    shares DOUBLE PRECISION,
    value_usd DOUBLE PRECISION,
    UNIQUE(fund_cik, filing_date, cusip)
);

CREATE TABLE IF NOT EXISTS holdings_fetch_log (
    fund_cik TEXT PRIMARY KEY,
    fund_name TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    filing_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'ok'
);

-- ── Japan (EDINET) ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS japan_large_stakes (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    filing_date TEXT NOT NULL,
    holder_name TEXT NOT NULL,
    shares_held DOUBLE PRECISION,
    percent_of_class DOUBLE PRECISION,
    purpose_text TEXT,
    report_type TEXT,
    UNIQUE(doc_id, holder_name)
);

CREATE TABLE IF NOT EXISTS edinet_fetch_log (
    ticker TEXT PRIMARY KEY,
    fetched_at TEXT NOT NULL,
    filing_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'ok'
);

-- ── Price alarms ────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS price_alarms (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    condition TEXT NOT NULL CHECK(condition IN ('above', 'below')),
    target_price DOUBLE PRECISION NOT NULL,
    created_at TEXT NOT NULL DEFAULT (TO_CHAR(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')),
    triggered_at TEXT,
    active INTEGER NOT NULL DEFAULT 1
);

-- ── Indexes ─────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_assets_symbol ON assets(symbol);
CREATE INDEX IF NOT EXISTS idx_assets_type ON assets(asset_type);
CREATE INDEX IF NOT EXISTS idx_forward_returns_snapshot ON forward_returns(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_company_info_asset ON company_info(asset_id);
CREATE INDEX IF NOT EXISTS idx_current_ticker ON current_stock_data(ticker);
CREATE INDEX IF NOT EXISTS idx_current_updated ON current_stock_data(last_updated);
CREATE INDEX IF NOT EXISTS idx_current_sector ON current_stock_data(sector);
CREATE INDEX IF NOT EXISTS idx_snapshots_asset_date ON fundamental_history(asset_id, snapshot_date);
CREATE INDEX IF NOT EXISTS idx_snapshots_date ON fundamental_history(snapshot_date);
CREATE INDEX IF NOT EXISTS idx_price_ticker_date ON price_history(ticker, date);
CREATE INDEX IF NOT EXISTS idx_valuation_ticker ON valuation_results(ticker);
CREATE INDEX IF NOT EXISTS idx_valuation_model ON valuation_results(model_name);
CREATE INDEX IF NOT EXISTS idx_valuation_suitable ON valuation_results(suitable);
CREATE INDEX IF NOT EXISTS idx_valuation_timestamp ON valuation_results(timestamp);
CREATE INDEX IF NOT EXISTS idx_valuation_ticker_model ON valuation_results(ticker, model_name);
CREATE INDEX IF NOT EXISTS idx_valuation_upside ON valuation_results(upside_pct DESC);
CREATE INDEX IF NOT EXISTS idx_threshold_date ON scanner_threshold_history(date);
CREATE INDEX IF NOT EXISTS idx_score_date_ticker ON scanner_score_history(date, ticker);
CREATE INDEX IF NOT EXISTS idx_score_opportunity ON scanner_score_history(opportunity_score DESC);
CREATE INDEX IF NOT EXISTS idx_macro_rates_rate_date ON macro_rates(rate_name, date DESC);
CREATE INDEX IF NOT EXISTS idx_insider_ticker ON insider_transactions(ticker);
CREATE INDEX IF NOT EXISTS idx_insider_ticker_date ON insider_transactions(ticker, transaction_date);
CREATE INDEX IF NOT EXISTS idx_activist_ticker ON activist_stakes(ticker);
CREATE INDEX IF NOT EXISTS idx_activist_ticker_date ON activist_stakes(ticker, filing_date);
CREATE INDEX IF NOT EXISTS idx_holdings_ticker ON fund_holdings(ticker);
CREATE INDEX IF NOT EXISTS idx_holdings_fund_quarter ON fund_holdings(fund_cik, quarter);
CREATE INDEX IF NOT EXISTS idx_holdings_quarter ON fund_holdings(quarter);
CREATE INDEX IF NOT EXISTS idx_price_alarms_active ON price_alarms(active, ticker);
