#!/usr/bin/env python3
"""
Create SQLite database for stock market data.

This script creates the database schema for storing historical stock data,
macroeconomic indicators, and forward returns across multiple time horizons.
"""

import sqlite3
from pathlib import Path


def create_database(db_path: str = 'stock_data.db'):
    """Create the SQLite database with the complete schema."""

    # Connect to database (creates if doesn't exist)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Enable foreign keys
    cursor.execute('PRAGMA foreign_keys = ON')

    # Create assets table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL UNIQUE,
            asset_type TEXT NOT NULL,
            name TEXT,
            sector TEXT,
            industry TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Create snapshots table with all 47 features
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id INTEGER NOT NULL,
            snapshot_date DATE NOT NULL,

            -- Price and volume
            current_price REAL,
            volume REAL,
            market_cap REAL,
            shares_outstanding REAL,

            -- Valuation ratios
            pe_ratio REAL,
            pb_ratio REAL,
            ps_ratio REAL,
            peg_ratio REAL,
            price_to_book REAL,
            price_to_sales REAL,
            enterprise_to_revenue REAL,
            enterprise_to_ebitda REAL,

            -- Profitability metrics
            profit_margins REAL,
            operating_margins REAL,
            gross_margins REAL,
            ebitda_margins REAL,
            return_on_assets REAL,
            return_on_equity REAL,

            -- Growth metrics
            revenue_growth REAL,
            earnings_growth REAL,
            earnings_quarterly_growth REAL,
            revenue_per_share REAL,

            -- Financial health
            total_cash REAL,
            total_debt REAL,
            debt_to_equity REAL,
            current_ratio REAL,
            quick_ratio REAL,

            -- Cash flow
            operating_cashflow REAL,
            free_cashflow REAL,

            -- Per share metrics
            trailing_eps REAL,
            forward_eps REAL,
            book_value REAL,

            -- Dividends
            dividend_rate REAL,
            dividend_yield REAL,
            payout_ratio REAL,

            -- Price history (60 days)
            price_change_pct REAL,
            volatility REAL,
            beta REAL,
            fifty_day_average REAL,
            two_hundred_day_average REAL,
            fifty_two_week_high REAL,
            fifty_two_week_low REAL,

            -- Macroeconomic features (shared across all assets on same date)
            vix REAL,
            treasury_10y REAL,
            dollar_index REAL,
            oil_price REAL,
            gold_price REAL,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (asset_id) REFERENCES assets(id),
            UNIQUE(asset_id, snapshot_date)
        )
    ''')

    # Create forward_returns table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS forward_returns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id INTEGER NOT NULL,
            horizon TEXT NOT NULL,
            return_pct REAL,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (snapshot_id) REFERENCES snapshots(id),
            UNIQUE(snapshot_id, horizon)
        )
    ''')

    # Create price_history table for storing full historical price data
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id INTEGER NOT NULL,
            date DATE NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL,
            dividends REAL,
            stock_splits REAL,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (snapshot_id) REFERENCES snapshots(id),
            UNIQUE(snapshot_id, date)
        )
    ''')

    # Create company_info table for storing complete yfinance metadata
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS company_info (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id INTEGER NOT NULL,
            snapshot_id INTEGER NOT NULL,

            -- Store full yfinance info dict as JSON
            info_json TEXT NOT NULL,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (asset_id) REFERENCES assets(id),
            FOREIGN KEY (snapshot_id) REFERENCES snapshots(id),
            UNIQUE(snapshot_id)
        )
    ''')

    # Create indexes for performance
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_assets_symbol ON assets(symbol)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_assets_type ON assets(asset_type)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_snapshots_asset_date ON snapshots(asset_id, snapshot_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_forward_returns_snapshot ON forward_returns(snapshot_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_price_history_snapshot ON price_history(snapshot_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_price_history_date ON price_history(snapshot_id, date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_company_info_asset ON company_info(asset_id)')

    # Commit and close
    conn.commit()
    conn.close()

    print(f'✅ Database created: {db_path}')
    print('   Tables: assets, snapshots, forward_returns, price_history, company_info')
    print('   Indexes: 7 performance indexes created')
    return db_path


if __name__ == '__main__':
    db_path = Path(__file__).parent / 'stock_data.db'
    create_database(str(db_path))
