"""Unit and integration tests for notes_view.py workstation frontend."""

import json
from pathlib import Path
import pytest
from starlette.testclient import TestClient

import sys
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from notes_view import render_notes_page, _extract_note_meta
import dashboard_server


def test_render_notes_page_structure():
    """Verify all workstation panels, sidebar, tabs, and controls are rendered."""
    ticker = "TEST"
    content = (
        "# Test Company (TEST)\n\n"
        "**Sector:** Technology | **Industry:** Software\n\n"
        "## Business Primer\n\nGreat business.\n\n"
        "## Valuation Models\n\n"
        "| Model | Fair Value |\n|---|---|\n| DCF | $15.00 |\n\n"
        "## Verdict\n\n**BUY** — High conviction\n"
    )
    html = render_notes_page(ticker, content, has_visual_report=False)

    # Core document structure
    assert "<!DOCTYPE html>" in html
    assert "<title>TEST - Analysis Workstation</title>" in html
    assert "color-scheme: light dark" in html
    assert "@media (prefers-color-scheme: dark)" in html
    assert "--background:#fff" in html
    assert "--background:#0d1117" in html

    # Sidebar components
    assert 'id="stocksSidebar"' in html
    assert 'id="sidebarStockCount"' in html
    assert 'id="sidebarCollapseBtn"' in html
    assert 'id="sidebarSearchInput"' in html
    assert 'id="sidebarSearchClear"' in html
    assert 'data-filter="all"' in html
    assert 'data-filter="buy"' in html
    assert 'data-filter="watch"' in html
    assert 'data-filter="notes"' in html
    assert 'id="sidebarStockList"' in html

    # Main Workspace & Topbar
    assert 'id="mainWorkspace"' in html
    assert 'id="workspaceTopbar"' in html
    assert 'id="sidebarOpenBtn"' in html
    assert "href='/'" in html
    assert "Dashboard" in html
    assert "TIKR" in html
    assert "Yahoo Finance" in html
    assert "Google Finance" in html
    assert "TradingView" in html
    assert "Filings" in html

    # 5-Tab Bar
    assert 'id="notesNavTabs"' in html
    assert 'data-tab="thesis"' in html
    assert 'data-tab="financials"' in html
    assert 'data-tab="plotter"' in html
    assert 'data-tab="technicals"' in html
    assert 'data-tab="valuation"' in html

    # 5 Tab Panels
    assert 'id="panel-thesis"' in html
    assert 'id="markdownBody"' in html
    assert "Great business." in html
    assert "<td>DCF</td>" in html
    assert "<td>$15.00</td>" in html

    assert 'id="panel-financials"' in html
    assert 'data-view="merged"' in html
    assert 'data-view="income"' in html
    assert 'data-view="balance"' in html
    assert 'data-view="cashflow"' in html
    assert 'id="stmtFilterInput"' in html

    assert 'id="panel-plotter"' in html
    assert 'id="crossPlotterCanvas"' in html
    assert 'data-preset="growth-debt"' in html
    assert 'data-preset="cash-quality"' in html
    assert 'data-preset="capex-cf"' in html
    assert 'data-preset="capital-structure"' in html
    assert 'data-preset="margins"' in html
    assert 'id="plotterMetricSelect"' in html
    assert 'id="plotterAddMetricBtn"' in html

    assert 'id="panel-technicals"' in html
    assert 'id="gaugeFillBar"' in html
    assert 'id="statCurPrice"' in html
    assert 'id="benchmarkList"' in html
    assert 'id="tradingview_chart_embed"' in html

    assert 'id="panel-valuation"' in html
    assert 'id="valVerdictBadge"' in html
    assert 'id="valEvPct"' in html
    assert 'id="valTargetPrice"' in html
    assert 'id="valScenarioBars"' in html
    assert 'id="valTableWrap"' in html


def test_render_notes_page_visual_companion():
    """Verify Visual Companion button appears when has_visual_report is True."""
    ticker = "VIS"
    content = "# Visual Corp (VIS)\n\nSome note."
    html_with = render_notes_page(ticker, content, has_visual_report=True)
    assert "/api/notes/VIS/visual" in html_with
    assert "Visual Companion" in html_with

    html_without = render_notes_page(ticker, content, has_visual_report=False)
    assert "/api/notes/VIS/visual" not in html_without


def test_render_notes_page_catalog_embedding():
    """Verify notes_catalog is embedded into window.__INITIAL_CATALOG__ when provided."""
    mock_catalog = [
        {"ticker": "AAA", "company_name": "Triple A", "verdict": "BUY", "current_price": 50.0},
        {"ticker": "BBB", "company_name": "Triple B", "verdict": "WATCH", "current_price": 20.0},
    ]
    html = render_notes_page("AAA", "# AAA\n", notes_catalog=mock_catalog)
    assert "window.__INITIAL_CATALOG__ = [" in html
    assert '"Triple A"' in html
    assert '"Triple B"' in html


def test_extract_note_meta():
    """Verify extraction of external links and company metadata."""
    content = (
        "# Snowflake Inc. (SNOW)\n\n"
        "[Official Website](https://www.snowflake.com)\n"
        "[Investor Relations](https://investors.snowflake.com)\n"
        "[TIKR](https://app.tikr.com/stock/about?cid=12345&tid=67890)\n"
    )
    meta = _extract_note_meta("SNOW", content)
    assert meta["company_name"] == "Snowflake Inc."
    assert meta["website_url"] == "https://www.snowflake.com"
    assert meta["ir_url"] == "https://investors.snowflake.com"
    assert "cid=12345" in meta["tikr_url"]
    assert "sec.gov" in meta["filings_url"]

    # Test Spanish exchange
    meta_mc = _extract_note_meta("REP.MC", "# Repsol (REP.MC)")
    assert "cnmv.es" in meta_mc["filings_url"]

    # Test Japanese exchange
    meta_t = _extract_note_meta("6758.T", "# Sony (6758.T)")
    assert "EDINET" in meta_t["filings_label"]


def test_dashboard_server_serves_workstation(tmp_path, monkeypatch):
    """Integration test: /api/notes/{ticker} serves workstation HTML via dashboard_server."""
    (tmp_path / "ACME.md").write_text("# ACME Corp (ACME)\n\nWorkstation test.\n", encoding="utf-8")
    monkeypatch.setattr(dashboard_server, "NOTES_DIR", tmp_path)

    client = TestClient(dashboard_server.app)
    res = client.get("/api/notes/ACME")
    assert res.status_code == 200
    assert "ACME - Analysis Workstation" in res.text
    assert 'id="stocksSidebar"' in res.text
    assert 'id="mainWorkspace"' in res.text
    assert 'id="notesNavTabs"' in res.text
    assert "Workstation test." in res.text
