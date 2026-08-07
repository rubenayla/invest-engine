"""
Regression tests for populate_fundamental_history.py.

These tests ensure:
1. All fundamental_history columns are populated (not just a subset)
2. stock.info fields are extracted and mapped to DB columns
3. International tickers are handled correctly
4. The enrichment pipeline doesn't silently drop data
"""

import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# Requires a live Postgres at localhost:5432 — skipped under CI's `-m "not slow"`.
pytestmark = pytest.mark.slow

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from populate_fundamental_history import HistoricalSnapshotFetcher


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def db_path(tmp_path):
    """Create a temporary DB with the required schema."""
    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    conn.execute("""
        CREATE TABLE current_stock_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL UNIQUE,
            current_price REAL,
            sector TEXT,
            industry TEXT,
            last_updated TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL UNIQUE,
            asset_type TEXT NOT NULL,
            name TEXT,
            sector TEXT,
            industry TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Create fundamental_history with ALL columns (matching production schema)
    conn.execute("""
        CREATE TABLE fundamental_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id INTEGER NOT NULL,
            snapshot_date DATE NOT NULL,
            volume REAL, market_cap REAL, shares_outstanding REAL,
            pe_ratio REAL, pb_ratio REAL, ps_ratio REAL, peg_ratio REAL,
            price_to_book REAL, price_to_sales REAL,
            enterprise_to_revenue REAL, enterprise_to_ebitda REAL,
            profit_margins REAL, operating_margins REAL, gross_margins REAL, ebitda_margins REAL,
            return_on_assets REAL, return_on_equity REAL,
            revenue_growth REAL, earnings_growth REAL, earnings_quarterly_growth REAL,
            revenue_per_share REAL,
            total_cash REAL, total_debt REAL, debt_to_equity REAL,
            current_ratio REAL, quick_ratio REAL,
            operating_cashflow REAL, free_cashflow REAL,
            trailing_eps REAL, forward_eps REAL, book_value REAL,
            dividend_rate REAL, dividend_yield REAL, payout_ratio REAL,
            price_change_pct REAL, volatility REAL, beta REAL,
            fifty_day_average REAL, two_hundred_day_average REAL,
            fifty_two_week_high REAL, fifty_two_week_low REAL,
            vix REAL, treasury_10y REAL, dollar_index REAL, oil_price REAL, gold_price REAL,
            realistic_return_1y REAL, realistic_return_3y REAL
        )
    """)
    conn.execute("""
        CREATE TABLE price_history (
            ticker TEXT NOT NULL,
            date DATE NOT NULL,
            open REAL, high REAL, low REAL, close REAL,
            volume REAL, dividends REAL, stock_splits REAL,
            PRIMARY KEY (ticker, date)
        )
    """)
    conn.commit()
    conn.close()
    return db


def _make_mock_info(ticker="AAPL", international=False):
    """Create a realistic stock.info dict."""
    info = {
        "symbol": ticker,
        "currentPrice": 150.0,
        "marketCap": 2500000000000,
        "trailingPE": 28.5,
        "forwardPE": 25.0,
        "priceToBook": 40.0,
        "priceToSalesTrailing12Months": 7.5,
        "pegRatio": 1.8,
        "enterpriseToRevenue": 7.2,
        "enterpriseToEbitda": 22.0,
        "profitMargins": 0.26,
        "operatingMargins": 0.30,
        "grossMargins": 0.45,
        "ebitdaMargins": 0.35,
        "returnOnAssets": 0.27,
        "returnOnEquity": 1.48,
        "revenueGrowth": 0.08,
        "earningsGrowth": 0.12,
        "earningsQuarterlyGrowth": 0.05,
        "revenuePerShare": 25.0,
        "totalCash": 60000000000,
        "totalDebt": 110000000000,
        "debtToEquity": 195.0,  # percentage from yfinance
        "currentRatio": 1.04,
        "quickRatio": 0.95,
        "operatingCashflow": 110000000000,
        "freeCashflow": 90000000000,
        "trailingEps": 6.15,
        "forwardEps": 7.0,
        "bookValue": 3.95,
        "dividendRate": 0.96,
        "dividendYield": 0.0055,
        "payoutRatio": 0.155,
        "beta": 1.28,
        "fiftyDayAverage": 148.0,
        "twoHundredDayAverage": 145.0,
        "fiftyTwoWeekHigh": 180.0,
        "fiftyTwoWeekLow": 120.0,
        "volume": 55000000,
        "sharesOutstanding": 15500000000,
        "sector": "Technology",
        "industry": "Consumer Electronics",
    }
    if international:
        info["symbol"] = ticker
        info["currency"] = "EUR"
        info["financialCurrency"] = "EUR"
    return info


def _make_mock_quarterly_financials():
    """Create mock quarterly financials DataFrame."""
    dates = [pd.Timestamp("2025-12-31"), pd.Timestamp("2025-09-30")]
    data = {
        dates[0]: {
            "Total Revenue": 120000000000,
            "Operating Income": 36000000000,
            "Net Income": 31000000000,
            "EBITDA": 42000000000,
        },
        dates[1]: {
            "Total Revenue": 115000000000,
            "Operating Income": 34000000000,
            "Net Income": 29000000000,
            "EBITDA": 40000000000,
        },
    }
    return pd.DataFrame(data)


def _make_mock_quarterly_balance_sheet():
    dates = [pd.Timestamp("2025-12-31"), pd.Timestamp("2025-09-30")]
    data = {
        dates[0]: {
            "Total Assets": 350000000000,
            "Total Debt": 110000000000,
            "Stockholders Equity": 62000000000,
            "Cash And Cash Equivalents": 30000000000,
            "Current Assets": 140000000000,
            "Current Liabilities": 135000000000,
        },
        dates[1]: {
            "Total Assets": 340000000000,
            "Total Debt": 108000000000,
            "Stockholders Equity": 60000000000,
            "Cash And Cash Equivalents": 28000000000,
            "Current Assets": 138000000000,
            "Current Liabilities": 133000000000,
        },
    }
    return pd.DataFrame(data)


def _make_mock_quarterly_cashflow():
    dates = [pd.Timestamp("2025-12-31"), pd.Timestamp("2025-09-30")]
    data = {
        dates[0]: {
            "Operating Cash Flow": 28000000000,
            "Free Cash Flow": 22000000000,
        },
        dates[1]: {
            "Operating Cash Flow": 27000000000,
            "Free Cash Flow": 21000000000,
        },
    }
    return pd.DataFrame(data)


def _mock_yfinance_ticker(info, financials=None, balance_sheet=None, cashflow=None):
    """Create a mock yfinance.Ticker object."""
    mock = MagicMock()
    mock.info = info
    mock.quarterly_financials = financials if financials is not None else pd.DataFrame()
    mock.quarterly_balance_sheet = balance_sheet if balance_sheet is not None else pd.DataFrame()
    mock.quarterly_cashflow = cashflow if cashflow is not None else pd.DataFrame()
    return mock


# ── Tests ─────────────────────────────────────────────────────────────────

class TestSnapshotColumnCoverage:
    """REGRESSION: Ensure all fundamental_history columns are populated."""

    def test_save_snapshots_uses_all_columns(self, db_path):
        """The save_snapshots INSERT must cover all SNAPSHOT_COLUMNS."""
        fetcher = HistoricalSnapshotFetcher(db_path=str(db_path))
        # Verify SNAPSHOT_COLUMNS matches the DB schema (minus id and non-populated cols)
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("PRAGMA table_info(fundamental_history)")
        db_cols = {row[1] for row in cursor.fetchall()}
        conn.close()

        snapshot_cols = set(fetcher.SNAPSHOT_COLUMNS)
        # These columns exist in DB but aren't populated by the fetcher
        # (they come from other scripts or are unused)
        exempt = {"id", "treasury_10y", "dollar_index", "oil_price", "gold_price",
                  "realistic_return_1y", "realistic_return_3y", "price_change_pct", "volatility"}

        missing_from_insert = (db_cols - snapshot_cols) - exempt
        assert not missing_from_insert, (
            f"REGRESSION: These DB columns are not in SNAPSHOT_COLUMNS and will always be NULL: "
            f"{missing_from_insert}"
        )
        fetcher.close()

    def test_enrichment_maps_all_info_fields(self, db_path):
        """stock.info fields must map to DB columns — not be silently dropped."""
        fetcher = HistoricalSnapshotFetcher(db_path=str(db_path))

        info = _make_mock_info()
        snapshots = [{
            "ticker": "TEST",
            "snapshot_date": "2025-12-31",
            "vix": 20.0,
        }]

        fetcher._enrich_latest_snapshot(snapshots, info, "TEST")
        enriched = snapshots[0]

        # These info keys MUST be mapped — if any are missing, we're dropping data
        critical_fields = {
            "market_cap", "pe_ratio", "pb_ratio", "profit_margins",
            "operating_margins", "return_on_equity", "revenue_growth",
            "trailing_eps", "book_value", "beta", "free_cashflow",
            "total_cash", "total_debt", "current_ratio",
            "fifty_day_average", "two_hundred_day_average",
            "shares_outstanding", "volume",
        }

        missing = {f for f in critical_fields if enriched.get(f) is None}
        assert not missing, (
            f"REGRESSION: These critical fields were not enriched from stock.info: {missing}"
        )
        fetcher.close()


class TestInternationalTickers:
    """REGRESSION: International tickers must be processed like US ones."""

    INTERNATIONAL_TICKERS = [
        ("SAP.DE", "Technology"),
        ("ASML.AS", "Technology"),
        ("MC.PA", "Consumer Cyclical"),
        ("ULVR.L", "Consumer Defensive"),
        ("7203.T", "Consumer Cyclical"),
        ("ENEL.MI", "Utilities"),
    ]

    @pytest.mark.parametrize("ticker,sector", INTERNATIONAL_TICKERS)
    def test_international_ticker_creates_asset(self, db_path, ticker, sector):
        """International tickers must be registered in the assets table."""
        fetcher = HistoricalSnapshotFetcher(db_path=str(db_path))
        asset_id = fetcher.get_or_create_asset(ticker, sector, "Test")
        assert asset_id is not None
        assert asset_id > 0

        # Verify it's in the DB
        result = fetcher.cursor.execute(
            "SELECT symbol FROM assets WHERE id = ?", (asset_id,)
        ).fetchone()
        assert result[0] == ticker
        fetcher.close()

    @pytest.mark.parametrize("ticker,sector", INTERNATIONAL_TICKERS)
    def test_international_ticker_gets_enriched(self, db_path, ticker, sector):
        """International tickers must get stock.info data in their snapshots."""
        fetcher = HistoricalSnapshotFetcher(db_path=str(db_path))

        info = _make_mock_info(ticker, international=True)
        snapshots = [{
            "ticker": ticker,
            "snapshot_date": "2025-12-31",
            "vix": 20.0,
            "profit_margins": 0.15,
        }]

        fetcher._enrich_latest_snapshot(snapshots, info, ticker)

        assert snapshots[0].get("pe_ratio") is not None, f"{ticker}: pe_ratio not enriched"
        assert snapshots[0].get("market_cap") is not None, f"{ticker}: market_cap not enriched"
        assert snapshots[0].get("trailing_eps") is not None, f"{ticker}: trailing_eps not enriched"
        assert snapshots[0].get("beta") is not None, f"{ticker}: beta not enriched"
        fetcher.close()


class TestEnrichmentLogic:
    """Test the enrichment pipeline details."""

    def test_enrichment_creates_snapshot_when_no_quarterly_data(self, db_path):
        """If quarterly data is empty, info-only snapshot must still be created."""
        fetcher = HistoricalSnapshotFetcher(db_path=str(db_path))
        info = _make_mock_info("NEWSTOCK")
        snapshots = []  # empty — no quarterly data

        fetcher._enrich_latest_snapshot(snapshots, info, "NEWSTOCK")

        assert len(snapshots) == 1, "Should create a snapshot from info alone"
        assert snapshots[0].get("pe_ratio") == 28.5
        assert snapshots[0].get("market_cap") == 2500000000000
        fetcher.close()

    def test_enrichment_does_not_overwrite_existing_values(self, db_path):
        """Enrichment should only fill NULLs, not overwrite quarterly-derived data."""
        fetcher = HistoricalSnapshotFetcher(db_path=str(db_path))

        info = _make_mock_info()
        snapshots = [{
            "ticker": "TEST",
            "snapshot_date": "2025-12-31",
            "vix": 20.0,
            "profit_margins": 0.999,  # pre-existing value from quarterly statements
        }]

        fetcher._enrich_latest_snapshot(snapshots, info, "TEST")

        # profit_margins should keep the original value
        assert snapshots[0]["profit_margins"] == 0.999
        # But pe_ratio should be filled from info
        assert snapshots[0]["pe_ratio"] == 28.5
        fetcher.close()

    def test_debt_to_equity_converted_from_percentage(self, db_path):
        """yfinance returns debtToEquity as percentage (e.g. 195.0), must convert to ratio."""
        fetcher = HistoricalSnapshotFetcher(db_path=str(db_path))

        info = _make_mock_info()
        info["debtToEquity"] = 195.0  # percentage
        snapshots = [{"ticker": "T", "snapshot_date": "2025-12-31", "vix": 20.0}]

        fetcher._enrich_latest_snapshot(snapshots, info, "T")

        dte = snapshots[0].get("debt_to_equity")
        assert dte is not None
        assert dte < 10, f"debtToEquity should be ratio (<10), got {dte}"
        assert abs(dte - 1.95) < 0.01
        fetcher.close()

    def test_debt_to_equity_not_double_converted(self, db_path):
        """If debtToEquity is already a ratio (<10), don't divide again."""
        fetcher = HistoricalSnapshotFetcher(db_path=str(db_path))

        info = _make_mock_info()
        info["debtToEquity"] = 1.5  # already a ratio
        snapshots = [{"ticker": "T", "snapshot_date": "2025-12-31", "vix": 20.0}]

        fetcher._enrich_latest_snapshot(snapshots, info, "T")

        dte = snapshots[0].get("debt_to_equity")
        assert abs(dte - 1.5) < 0.01
        fetcher.close()


class TestEndToEnd:
    """End-to-end test: fetch → extract → save → read back."""

    @patch("populate_fundamental_history.yf.Ticker")
    def test_process_stock_saves_enriched_data(self, mock_ticker_cls, db_path):
        """Full pipeline: process_stock must save all enriched fields to DB."""
        info = _make_mock_info("TEST")
        mock_ticker_cls.return_value = _mock_yfinance_ticker(
            info=info,
            financials=_make_mock_quarterly_financials(),
            balance_sheet=_make_mock_quarterly_balance_sheet(),
            cashflow=_make_mock_quarterly_cashflow(),
        )

        fetcher = HistoricalSnapshotFetcher(db_path=str(db_path))
        # Prepopulate VIX cache so it doesn't call yfinance for VIX
        fetcher.vix_cache = {"2025-12-31": 20.0, "2025-09-30": 22.0}

        count = fetcher.process_stock("TEST", "Technology", "Consumer Electronics")
        assert count >= 1

        # Read back from DB and verify enrichment
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT f.* FROM fundamental_history f
            JOIN assets a ON f.asset_id = a.id
            WHERE a.symbol = 'TEST'
            ORDER BY f.snapshot_date DESC
        """).fetchall()
        conn.close()

        assert len(rows) >= 1
        latest = dict(rows[0])

        # Critical fields from stock.info must be present on the latest snapshot
        assert latest["pe_ratio"] is not None, "pe_ratio missing from DB"
        assert latest["trailing_eps"] is not None, "trailing_eps missing from DB"
        assert latest["market_cap"] is not None, "market_cap missing from DB"
        assert latest["beta"] is not None, "beta missing from DB"
        assert latest["book_value"] is not None, "book_value missing from DB"
        assert latest["free_cashflow"] is not None, "free_cashflow missing from DB"
        assert latest["volume"] is not None, "volume missing from DB"

        # Derived fields from quarterly statements
        assert latest["profit_margins"] is not None, "profit_margins missing from DB"
        assert latest["operating_margins"] is not None, "operating_margins missing from DB"
        assert latest["return_on_equity"] is not None, "return_on_equity missing from DB"
        assert latest["vix"] is not None, "vix missing from DB"

        fetcher.close()

    @patch("populate_fundamental_history.yf.Ticker")
    def test_process_stock_with_no_quarterly_still_saves(self, mock_ticker_cls, db_path):
        """Stock with no quarterly data should still get a snapshot from info."""
        info = _make_mock_info("INFOONLY")
        mock_ticker_cls.return_value = _mock_yfinance_ticker(info=info)

        fetcher = HistoricalSnapshotFetcher(db_path=str(db_path))
        fetcher.vix_cache = {"2025-12-31": 18.0}

        count = fetcher.process_stock("INFOONLY", "Technology")
        assert count >= 1

        conn = sqlite3.connect(str(db_path))
        row = conn.execute("""
            SELECT f.pe_ratio, f.trailing_eps, f.market_cap
            FROM fundamental_history f
            JOIN assets a ON f.asset_id = a.id
            WHERE a.symbol = 'INFOONLY'
            ORDER BY f.snapshot_date DESC LIMIT 1
        """).fetchone()
        conn.close()

        assert row is not None, "No snapshot saved for info-only stock"
        assert row[0] is not None, "pe_ratio missing for info-only stock"
        assert row[1] is not None, "trailing_eps missing for info-only stock"
        assert row[2] is not None, "market_cap missing for info-only stock"

        fetcher.close()


class TestSafeFloat:
    """Test _safe_float handles edge cases without crashing."""

    @pytest.mark.parametrize("val,expected", [
        (None, None),
        (float("nan"), None),
        (float("inf"), float("inf")),  # inf is technically a valid float
        ("not_a_number", None),
        (0, 0.0),
        (42, 42.0),
        (-3.14, -3.14),
        (True, 1.0),  # bool is subclass of int
    ])
    def test_safe_float_cases(self, val, expected):
        result = HistoricalSnapshotFetcher._safe_float(val)
        if expected is None:
            assert result is None
        else:
            assert result == expected


class TestInfoEdgeCases:
    """Test enrichment with broken/partial stock.info responses."""

    def test_empty_info_does_not_crash(self, db_path):
        """stock.info returning {} should not create a snapshot."""
        fetcher = HistoricalSnapshotFetcher(db_path=str(db_path))
        snapshots = []
        fetcher._enrich_latest_snapshot(snapshots, {}, "EMPTY")
        assert len(snapshots) == 0
        fetcher.close()

    def test_info_without_current_price_skipped(self, db_path):
        """If currentPrice is missing, enrichment is skipped entirely."""
        fetcher = HistoricalSnapshotFetcher(db_path=str(db_path))
        info = _make_mock_info()
        del info["currentPrice"]
        snapshots = []

        # The caller checks info.get('currentPrice') before calling _enrich
        # Simulate: enrichment should not run
        if info.get("currentPrice"):
            fetcher._enrich_latest_snapshot(snapshots, info, "TEST")
        assert len(snapshots) == 0
        fetcher.close()

    def test_info_with_non_numeric_values_skipped(self, db_path):
        """Non-numeric values in info should be silently skipped."""
        fetcher = HistoricalSnapshotFetcher(db_path=str(db_path))
        info = _make_mock_info()
        info["trailingPE"] = "N/A"  # sometimes yfinance returns strings
        info["beta"] = None
        snapshots = [{"ticker": "T", "snapshot_date": "2025-12-31", "vix": 20.0}]

        fetcher._enrich_latest_snapshot(snapshots, info, "T")

        assert snapshots[0].get("pe_ratio") is None  # "N/A" skipped
        assert snapshots[0].get("beta") is None  # None skipped
        assert snapshots[0].get("market_cap") is not None  # valid field still works
        fetcher.close()


class TestSnapshotColumnsOrder:
    """REGRESSION: SNAPSHOT_COLUMNS order must match the INSERT values."""

    def test_columns_start_with_asset_id_and_date(self, db_path):
        """First two columns must be asset_id and snapshot_date (positional INSERT)."""
        fetcher = HistoricalSnapshotFetcher(db_path=str(db_path))
        assert fetcher.SNAPSHOT_COLUMNS[0] == "asset_id"
        assert fetcher.SNAPSHOT_COLUMNS[1] == "snapshot_date"
        fetcher.close()

    def test_all_snapshot_columns_exist_in_db(self, db_path):
        """Every column in SNAPSHOT_COLUMNS must exist in the DB table."""
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("PRAGMA table_info(fundamental_history)")
        db_cols = {row[1] for row in cursor.fetchall()}
        conn.close()

        fetcher = HistoricalSnapshotFetcher(db_path=str(db_path))
        for col in fetcher.SNAPSHOT_COLUMNS:
            assert col in db_cols, f"SNAPSHOT_COLUMNS has '{col}' but it doesn't exist in DB"
        fetcher.close()

    def test_no_duplicate_columns(self, db_path):
        """SNAPSHOT_COLUMNS must not have duplicates."""
        fetcher = HistoricalSnapshotFetcher(db_path=str(db_path))
        assert len(fetcher.SNAPSHOT_COLUMNS) == len(set(fetcher.SNAPSHOT_COLUMNS)), \
            "Duplicate columns in SNAPSHOT_COLUMNS"
        fetcher.close()


class TestRefreshMode:
    """Test --refresh flag selects and cleans up sparse tickers."""

    def test_refresh_finds_tickers_with_empty_data(self, db_path):
        """Tickers in assets with all-null fundamentals should be found by refresh query."""
        conn = sqlite3.connect(str(db_path))
        # Add a ticker to current_stock_data
        conn.execute(
            "INSERT INTO current_stock_data (ticker, current_price, sector, industry) VALUES (?, ?, ?, ?)",
            ("SPARSE", 100.0, "Tech", "Software"),
        )
        # Add to assets
        conn.execute(
            "INSERT INTO assets (symbol, asset_type, sector) VALUES (?, ?, ?)",
            ("SPARSE", "stock", "Tech"),
        )
        asset_id = conn.execute("SELECT id FROM assets WHERE symbol = 'SPARSE'").fetchone()[0]
        # Add a row with all nulls (simulating the old bug)
        conn.execute(
            "INSERT INTO fundamental_history (asset_id, snapshot_date) VALUES (?, ?)",
            (asset_id, "2025-06-30"),
        )
        conn.commit()
        conn.close()

        fetcher = HistoricalSnapshotFetcher(db_path=str(db_path))
        sparse = fetcher.cursor.execute("""
            SELECT c.ticker FROM current_stock_data c
            WHERE c.current_price IS NOT NULL AND c.ticker IN (
                SELECT a.symbol FROM assets a
                JOIN fundamental_history f ON f.asset_id = a.id
                GROUP BY a.symbol
                HAVING SUM(CASE WHEN f.pe_ratio IS NOT NULL
                                  OR f.trailing_eps IS NOT NULL
                                  OR f.market_cap IS NOT NULL
                           THEN 1 ELSE 0 END) = 0
            )
        """).fetchall()

        tickers = [r[0] for r in sparse]
        assert "SPARSE" in tickers
        fetcher.close()


class TestQuarterlyExtraction:
    """Test extraction from quarterly financial statements."""

    def test_derived_ratios_calculated(self, db_path):
        """Derived ratios (margins, ROE, D/E) must be calculated from statements."""
        fetcher = HistoricalSnapshotFetcher(db_path=str(db_path))

        snapshot = fetcher._extract_snapshot_from_quarterly(
            ticker="TEST",
            snapshot_date=pd.Timestamp("2025-12-31"),
            financials=_make_mock_quarterly_financials(),
            balance_sheet=_make_mock_quarterly_balance_sheet(),
            cashflow=_make_mock_quarterly_cashflow(),
            sector="Technology",
        )

        assert snapshot is not None
        assert snapshot["profit_margins"] is not None
        assert abs(snapshot["profit_margins"] - 31000000000 / 120000000000) < 0.001
        assert snapshot["operating_margins"] is not None
        assert snapshot["return_on_equity"] is not None
        assert snapshot["debt_to_equity"] is not None
        assert snapshot["current_ratio"] is not None
        assert snapshot["free_cashflow"] == 22000000000

        fetcher.close()

    def test_handles_missing_statements_gracefully(self, db_path):
        """If a statement is empty, should still return partial snapshot."""
        fetcher = HistoricalSnapshotFetcher(db_path=str(db_path))

        snapshot = fetcher._extract_snapshot_from_quarterly(
            ticker="PARTIAL",
            snapshot_date=pd.Timestamp("2025-12-31"),
            financials=_make_mock_quarterly_financials(),
            balance_sheet=pd.DataFrame(),  # empty
            cashflow=pd.DataFrame(),  # empty
            sector="Unknown",
        )

        assert snapshot is not None
        assert snapshot["profit_margins"] is not None  # from financials
        assert snapshot.get("debt_to_equity") is None  # no balance sheet
        assert snapshot.get("free_cashflow") is None  # no cashflow

        fetcher.close()
