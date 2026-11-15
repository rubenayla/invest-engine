"""Investment Notes Workstation Frontend View.

Renders an interactive, responsive workstation for equity research notes with:
- Collapsible stock universe sidebar with real-time search, filters (All, BUY, WATCH, Notes Only),
  and PJAX seamless navigation.
- Topbar with dashboard navigation, visual companion link, and external toolbars.
- Sticky 5-tab workspace navigation (Thesis & Primer, Financial Statements, Cross-Plotter,
  Technical Analysis, Valuation Models) with keyboard shortcuts (1-5, [, Ctrl+B).
- Interactive multi-year financial statements viewer (Merged, Income, Balance Sheet, Cash Flow).
- Cross-Plotter mixing balance sheet + earnings with dual Y-axes, 5 financial presets,
  and custom line-item picker across all statements.
- Technical analysis with 52-week gauge, volume stats, thesis-break benchmark, and TradingView chart.
- Valuation models comparison, scenario targets visualization, and fair value distribution.
"""

from __future__ import annotations

import html
import json
import os
from pathlib import Path
import re
import urllib.parse


def render_notes_page(
    ticker: str,
    content: str,
    has_visual_report: bool = False,
    notes_catalog: list[dict] | None = None,
) -> str:
    """Render the full interactive investment notes workstation HTML."""
    ticker_clean = ticker.upper()
    meta = _extract_note_meta(ticker_clean, content)
    body_html = _render_markdown_body(content)
    topbar_html = _render_topbar_html(ticker_clean, meta, has_visual_report)
    initial_catalog_json = json.dumps(notes_catalog) if notes_catalog else "null"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{ticker_clean} - Analysis Workstation</title>
  <meta name="color-scheme" content="light dark">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <!-- Chart.js CDN -->
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  <!-- TradingView Widget Script -->
  <script src="https://s3.tradingview.com/tv.js" async></script>
  <style>
{_get_css()}
  </style>
</head>
<body>
  <div id="topProgressBar"></div>
  <div class="app-container" id="appContainer">
    <!-- Collapsible Stocks Sidebar -->
    <aside class="stocks-sidebar" id="stocksSidebar">
      <div class="sidebar-header">
        <div class="sidebar-title-row">
          <div class="sidebar-title-group">
            <span class="sidebar-title">Stock Universe</span>
            <span class="sidebar-count-badge" id="sidebarStockCount">0</span>
          </div>
          <button class="sidebar-toggle-btn" id="sidebarCollapseBtn" title="Collapse Sidebar ([ or Ctrl+B)" aria-label="Collapse Sidebar">
            <svg class="sidebar-toggle-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect width="18" height="18" x="3" y="3" rx="3.5" />
              <path d="M3 6.5A3.5 3.5 0 0 1 6.5 3H9v18H6.5A3.5 3.5 0 0 1 3 17.5V6.5z" fill="currentColor" stroke="none" />
            </svg>
          </button>
        </div>
        <div class="sidebar-search-wrap">
          <input type="text" id="sidebarSearchInput" placeholder="Search ticker or name... (/)" autocomplete="off" spellcheck="false">
          <button id="sidebarSearchClear" class="search-clear-btn" title="Clear search (Esc)" style="display:none;">&times;</button>
        </div>
        <div class="sidebar-filter-pills" id="sidebarFilterPills">
          <button class="filter-pill active" data-filter="all">All</button>
          <button class="filter-pill" data-filter="buy">BUY</button>
          <button class="filter-pill" data-filter="watch">WATCH</button>
          <button class="filter-pill" data-filter="notes">Notes Only</button>
        </div>
      </div>
      <div class="sidebar-stock-list" id="sidebarStockList">
        <div class="sidebar-loading">Loading stock catalog...</div>
      </div>
    </aside>

    <!-- Main Workspace -->
    <main class="main-workspace" id="mainWorkspace">
      <!-- Topbar Header -->
      <div id="topbarContainer">
{topbar_html}
      </div>

      <!-- Sticky Top Navigation Tabs -->
      <nav class="notes-nav-tabs" id="notesNavTabs">
        <button class="nav-tab active" data-tab="thesis"><span class="tab-icon">📝</span> Thesis &amp; Primer <kbd class="tab-kbd">1</kbd></button>
        <button class="nav-tab" data-tab="financials"><span class="tab-icon">📊</span> Financial Statements <kbd class="tab-kbd">2</kbd></button>
        <button class="nav-tab" data-tab="plotter"><span class="tab-icon">📈</span> Cross-Plotter <kbd class="tab-kbd">3</kbd></button>
        <button class="nav-tab" data-tab="technicals"><span class="tab-icon">⚡</span> Technical Analysis <kbd class="tab-kbd">4</kbd></button>
        <button class="nav-tab" data-tab="valuation"><span class="tab-icon">🎯</span> Valuation Models <kbd class="tab-kbd">5</kbd></button>
      </nav>

      <!-- Tab Panels Container -->
      <div class="tab-panels-container">
        <!-- Panel 1: Thesis & Primer -->
        <section class="tab-panel active" id="panel-thesis" data-panel="thesis">
          <div class="markdown-body" id="markdownBody">
{body_html}
          </div>
        </section>

        <!-- Panel 2: Financial Statements -->
        <section class="tab-panel" id="panel-financials" data-panel="financials">
          <div class="financials-view-container">
            <div class="financials-toolbar">
              <div class="view-switch-group" id="stmtViewSwitchGroup">
                <button class="stmt-switch-btn active" data-view="merged">Merged</button>
                <button class="stmt-switch-btn" data-view="income">Income Statement</button>
                <button class="stmt-switch-btn" data-view="balance">Balance Sheet</button>
                <button class="stmt-switch-btn" data-view="cashflow">Cash Flow</button>
              </div>
              <div class="financials-search-box">
                <input type="text" id="stmtFilterInput" placeholder="Filter rows... (e.g. Revenue, EBITDA, Debt)" autocomplete="off">
              </div>
              <div class="financials-units-meta">
                <span id="stmtCurrencyBadge" class="meta-pill">Currency: USD</span>
                <button id="stmtFormatToggle" class="stmt-toggle-btn" title="Toggle humanized (B/M/K) vs exact numbers">Format: B/M/K</button>
              </div>
            </div>
            <div id="financialsContent" class="financials-table-wrap">
              <div class="loading-spinner-wrap"><div class="spinner"></div><span>Loading financial statements...</span></div>
            </div>
          </div>
        </section>

        <!-- Panel 3: Cross-Plotter -->
        <section class="tab-panel" id="panel-plotter" data-panel="plotter">
          <div class="cross-plotter-container">
            <div class="plotter-top-controls">
              <div class="plotter-presets-bar">
                <span class="plotter-section-label">PRESETS:</span>
                <button class="preset-btn active" data-preset="growth-debt">Growth vs Debt</button>
                <button class="preset-btn" data-preset="cash-quality">Cash Quality vs FCF</button>
                <button class="preset-btn" data-preset="capex-cf">CapEx vs Operating CF</button>
                <button class="preset-btn" data-preset="capital-structure">Capital Structure</button>
                <button class="preset-btn" data-preset="margins">Margins</button>
              </div>
              <div class="plotter-actions-bar">
                <button id="plotterClearBtn" class="plotter-btn secondary-btn">Clear All</button>
                <div class="plotter-type-group">
                  <button class="plotter-type-btn active" data-type="line">Line</button>
                  <button class="plotter-type-btn" data-type="bar">Bar</button>
                </div>
              </div>
            </div>

            <div class="plotter-picker-panel">
              <div class="metric-picker-row">
                <div class="picker-input-wrap">
                  <label for="plotterMetricSelect">Add Line Item:</label>
                  <select id="plotterMetricSelect" class="plotter-select">
                    <option value="">-- Choose any metric from statements --</option>
                  </select>
                </div>
                <div class="picker-axis-wrap">
                  <label>Axis:</label>
                  <div class="axis-radio-group">
                    <label><input type="radio" name="plotterAxisChoice" value="left" checked> Left (Y1)</label>
                    <label><input type="radio" name="plotterAxisChoice" value="right"> Right (Y2)</label>
                  </div>
                </div>
                <button id="plotterAddMetricBtn" class="plotter-btn primary-btn">+ Add to Chart</button>
              </div>
              <div class="active-metrics-chips" id="plotterActiveChips"></div>
            </div>

            <div class="plotter-canvas-container" id="plotterCanvasContainer">
              <canvas id="crossPlotterCanvas"></canvas>
            </div>
            <div class="plotter-footer-hint">
              <span>💡 Tip: Combine income, balance sheet, and cash flow line items simultaneously with dual independent Y-axes.</span>
            </div>
          </div>
        </section>

        <!-- Panel 4: Technical Analysis -->
        <section class="tab-panel" id="panel-technicals" data-panel="technicals">
          <div class="technicals-container">
            <div class="technicals-summary-grid">
              <!-- 52W Range Gauge Card -->
              <div class="tech-card gauge-card">
                <div class="tech-card-title">52-Week Price Range</div>
                <div class="range-gauge-wrap">
                  <div class="range-labels">
                    <span class="range-low" id="gaugeLowVal">$0.00</span>
                    <span class="range-cur" id="gaugeCurVal">$0.00</span>
                    <span class="range-high" id="gaugeHighVal">$0.00</span>
                  </div>
                  <div class="range-track">
                    <div class="range-fill" id="gaugeFillBar" style="width: 50%;"></div>
                    <div class="range-thumb" id="gaugeThumb" style="left: 50%;"></div>
                  </div>
                  <div class="range-meta" id="gaugeMetaText">Loading range...</div>
                </div>
              </div>

              <!-- Stats Grid Card -->
              <div class="tech-card stats-card">
                <div class="tech-card-title">Price &amp; Volume Statistics</div>
                <div class="stats-mini-grid">
                  <div class="stat-cell"><span class="stat-lbl">Current Price</span><span class="stat-val" id="statCurPrice">--</span></div>
                  <div class="stat-cell"><span class="stat-lbl">30-Day Trend</span><span class="stat-val" id="statTrend30d">--</span></div>
                  <div class="stat-cell"><span class="stat-lbl">Avg Daily Volume</span><span class="stat-val" id="statAvgVol">--</span></div>
                  <div class="stat-cell"><span class="stat-lbl">Market Cap</span><span class="stat-val" id="statMktCap">--</span></div>
                  <div class="stat-cell"><span class="stat-lbl">Sector</span><span class="stat-val" id="statSector">--</span></div>
                  <div class="stat-cell"><span class="stat-lbl">Industry</span><span class="stat-val" id="statIndustry">--</span></div>
                </div>
              </div>

              <!-- Thesis Break & Entry Benchmark Card -->
              <div class="tech-card benchmark-card">
                <div class="tech-card-title">Strategy &amp; Entry Benchmarks</div>
                <div class="benchmark-list" id="benchmarkList">
                  <div class="benchmark-row">
                    <span class="bm-label">Target Entry Price:</span>
                    <span class="bm-val" id="bmEntryVal">--</span>
                  </div>
                  <div class="benchmark-status" id="bmEntryStatus">--</div>
                  <div class="benchmark-row">
                    <span class="bm-label">Thesis-Break Price:</span>
                    <span class="bm-val" id="bmBreakVal">--</span>
                  </div>
                  <div class="benchmark-status" id="bmBreakStatus">--</div>
                </div>
              </div>
            </div>

            <!-- TradingView Embed Widget Card -->
            <div class="tech-card tradingview-card">
              <div class="tech-card-title-row">
                <span class="tech-card-title">Interactive Technical Chart</span>
                <span class="tech-card-sub" id="tvSymbolLabel">TradingView</span>
              </div>
              <div class="tradingview-container-wrap" id="tvContainerWrap">
                <div id="tradingview_chart_embed" style="height: 520px; width: 100%;"></div>
              </div>
            </div>
          </div>
        </section>

        <!-- Panel 5: Valuation Models -->
        <section class="tab-panel" id="panel-valuation" data-panel="valuation">
          <div class="valuation-container">
            <div class="valuation-banner-grid">
              <div class="val-metric-card">
                <span class="val-metric-lbl">LLM Verdict</span>
                <span class="val-metric-val verdict-badge-large" id="valVerdictBadge">--</span>
                <span class="val-metric-sub" id="valConvictionSub">--</span>
              </div>
              <div class="val-metric-card">
                <span class="val-metric-lbl">Expected Value</span>
                <span class="val-metric-val" id="valEvPct">--</span>
                <span class="val-metric-sub">Probability-Weighted</span>
              </div>
              <div class="val-metric-card">
                <span class="val-metric-lbl">Target / Fair Value</span>
                <span class="val-metric-val" id="valTargetPrice">--</span>
                <span class="val-metric-sub" id="valUpsideSub">--</span>
              </div>
              <div class="val-metric-card">
                <span class="val-metric-lbl">Actionable Entry</span>
                <span class="val-metric-val" id="valEntryPrice">--</span>
                <span class="val-metric-sub" id="valEntrySub">--</span>
              </div>
            </div>

            <div class="tech-card scenario-targets-card">
              <div class="tech-card-title">Scenario Targets &amp; Probabilities</div>
              <div class="scenario-chart-body">
                <div class="scenario-bar-list" id="valScenarioBars">
                  <div class="empty-hint">Loading scenario analysis...</div>
                </div>
              </div>
            </div>

            <div class="tech-card valuation-table-card">
              <div class="tech-card-title">Valuation Models Comparison</div>
              <div class="val-table-wrap" id="valTableWrap">
                <div class="empty-hint">Loading model comparisons...</div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </main>
  </div>

  <script>
    window.__CURRENT_TICKER__ = "{ticker_clean}";
    window.__INITIAL_CATALOG__ = {initial_catalog_json};
{_get_javascript()}
  </script>
</body>
</html>
"""


def _extract_note_meta(ticker: str, content: str) -> dict:
    """Extract company name, external links, and key metadata from markdown."""
    m_title = re.search(r"^#\s+([^\n(]+)", content, re.MULTILINE)
    company_name = m_title.group(1).strip() if m_title else ticker

    m_web = re.search(r"\[(?:Official\s+)?Website\]\((https?://[^\)]+)\)", content, re.IGNORECASE)
    website_url = m_web.group(1) if m_web else None

    m_ir = re.search(r"\[(?:Investor\s+Relations|IR|Shareholder)\s*[^\]]*\]\((https?://[^\)]+)\)", content, re.IGNORECASE)
    ir_url = m_ir.group(1) if m_ir else None

    # TIKR URL extraction
    m_tikr = re.search(r"\[TIKR\]\((https?://app\.tikr\.com/[^\)]+)\)", content, re.IGNORECASE)
    if m_tikr and "cid=" in m_tikr.group(1):
        tikr_url = m_tikr.group(1)
    else:
        tikr_url = _resolve_tikr_cached(ticker, company_name)

    if not ir_url:
        m_ir_auto = re.search(r"(https?://(?:investor|ir)\.[a-zA-Z0-9.-]+[a-zA-Z0-9/_-]*)", content)
        if m_ir_auto:
            ir_url = m_ir_auto.group(1).rstrip(".,;)")

    encoded_name = urllib.parse.quote_plus(company_name)
    encoded_ticker = urllib.parse.quote_plus(ticker)

    if not website_url:
        website_url = f"https://www.google.com/search?q={encoded_name}+official+website"
        web_label = "🌐 Search Website"
    else:
        web_label = "🌐 Website"

    if not ir_url:
        ir_url = f"https://www.google.com/search?q={encoded_name}+investor+relations"
        ir_label = "📑 Search IR"
    else:
        ir_label = "📑 Investor Relations"

    if ticker.endswith(".MC"):
        clean_t = ticker.replace(".MC", "")
        filings_url = f"https://www.cnmv.es/portal/Consultas/DerechosVoto/Buscador.aspx?q={clean_t}"
        filings_label = "🏛️ CNMV Filings"
    elif ticker.endswith(".T"):
        filings_url = f"https://www.google.com/search?q={ticker}+EDINET+filings"
        filings_label = "🏛️ EDINET Filings"
    elif "." not in ticker or ticker.endswith(".US"):
        clean_t = ticker.replace(".US", "")
        filings_url = f"https://www.sec.gov/edgar/searchedgar/companysearch?companyName={clean_t}"
        filings_label = "🏛️ SEC Filings"
    else:
        filings_url = f"https://www.google.com/search?q={encoded_ticker}+{encoded_name}+financial+filings"
        filings_label = "🏛️ Filings"

    return {
        "company_name": company_name,
        "website_url": website_url,
        "web_label": web_label,
        "ir_url": ir_url,
        "ir_label": ir_label,
        "tikr_url": tikr_url,
        "filings_url": filings_url,
        "filings_label": filings_label,
    }


def _resolve_tikr_cached(ticker: str, company_name: str = "") -> str:
    """Resolve TIKR URL from data/tikr_cache.json if available, otherwise direct ticker URL."""
    cache_file = Path(__file__).resolve().parent.parent / "data" / "tikr_cache.json"
    if cache_file.is_file():
        try:
            c = json.loads(cache_file.read_text(encoding="utf-8"))
            if ticker in c:
                return c[ticker]
        except Exception:
            pass
    return f"https://app.tikr.com/stock/about?ticker={ticker}"


def _render_topbar_html(ticker: str, meta: dict, has_visual_report: bool) -> str:
    """Build the company header action toolbar."""
    visual_btn = ""
    if has_visual_report:
        visual_btn = (
            f'<a class="nav-btn highlight-btn" href="/api/notes/{ticker}/visual" '
            f'target="_blank" rel="noopener">🎨 Visual Companion</a>'
        )

    return (
        f'<header class="workspace-topbar" id="workspaceTopbar">'
        f'<div class="toolbar-left">'
        f'<button class="nav-btn sidebar-toggle-btn" id="sidebarOpenBtn" title="Toggle Sidebar ([ or Ctrl+B)" aria-label="Toggle Sidebar">'
        f'<svg class="sidebar-toggle-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        f'<rect width="18" height="18" x="3" y="3" rx="3.5" />'
        f'<path d="M3 6.5A3.5 3.5 0 0 1 6.5 3H9v18H6.5A3.5 3.5 0 0 1 3 17.5V6.5z" fill="currentColor" stroke="none" />'
        f'</svg>'
        f'</button>'
        f"<a class='nav-btn back-btn' href='/'>← Dashboard</a>"
        f'{visual_btn}'
        f'</div>'
        f'<div class="toolbar-right">'
        f'<a class="nav-btn" href="{meta["website_url"]}" target="_blank" rel="noopener">{meta["web_label"]}</a>'
        f'<a class="nav-btn" href="{meta["ir_url"]}" target="_blank" rel="noopener">{meta["ir_label"]}</a>'
        f'<a class="nav-btn" href="{meta["tikr_url"]}" target="_blank" rel="noopener">📈 TIKR</a>'
        f'<a class="nav-btn" href="https://finance.yahoo.com/quote/{ticker}" target="_blank" rel="noopener">📊 Yahoo Finance</a>'
        f'<a class="nav-btn" href="https://www.google.com/finance/quote/{ticker}" target="_blank" rel="noopener">🔍 Google Finance</a>'
        f'<a class="nav-btn" href="https://www.tradingview.com/symbols/{ticker}/" target="_blank" rel="noopener">📉 TradingView</a>'
        f'<a class="nav-btn" href="{meta["filings_url"]}" target="_blank" rel="noopener">{meta["filings_label"]}</a>'
        f'</div>'
        f'</header>'
    )


def _render_markdown_body(content: str) -> str:
    """Render markdown to HTML using python-markdown or formatted pre-fallback."""
    try:
        import markdown

        return markdown.markdown(content, extensions=["tables", "fenced_code"])
    except ImportError:
        escaped = html.escape(content)
        return f"<pre style='white-space:pre-wrap;'>{escaped}</pre>"


def _get_css() -> str:
    """Return complete CSS stylesheet for the notes workstation."""
    return """
:root {
  color-scheme: light dark;
  --background:#fff;
  --foreground:#1f2328;
  --heading:#0969da;
  --border:#d0d7de;
  --surface:#f6f8fa;
  --surface-hover:#eaeef2;
  --strong:#24292f;
  --accent:#0969da;
  --accent-light:rgba(9, 105, 218, 0.12);
  --success:#2da44e;
  --success-bg:rgba(45, 164, 78, 0.15);
  --warning:#bf8700;
  --warning-bg:rgba(191, 135, 0, 0.15);
  --danger:#cf222e;
  --danger-bg:rgba(207, 34, 46, 0.15);
  --sidebar-width:320px;
}

@media (prefers-color-scheme: dark) {
  :root {
    --background:#0d1117;
    --foreground:#e0e6ed;
    --heading:#58a6ff;
    --border:#30363d;
    --surface:#161b22;
    --surface-hover:#21262d;
    --strong:#f0f6fc;
    --accent:#58a6ff;
    --accent-light:rgba(88, 166, 255, 0.15);
    --success:#3fb950;
    --success-bg:rgba(63, 185, 80, 0.18);
    --warning:#d29922;
    --warning-bg:rgba(210, 153, 34, 0.18);
    --danger:#f85149;
    --danger-bg:rgba(248, 81, 73, 0.18);
  }
}

* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: var(--background);
  color: var(--foreground);
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  font-size: 16px;
  line-height: 1.6;
  min-height: 100vh;
  overflow-x: hidden;
}

/* PJAX Loading Bar */
#topProgressBar {
  position: fixed;
  top: 0;
  left: 0;
  height: 3px;
  width: 0%;
  background: var(--heading);
  z-index: 99999;
  transition: width 0.2s ease, opacity 0.3s ease;
  pointer-events: none;
}

/* App Layout */
.app-container {
  display: flex;
  min-height: 100vh;
  width: 100vw;
  transition: all 0.25s ease;
}

/* Stocks Sidebar */
.stocks-sidebar {
  width: var(--sidebar-width);
  min-width: var(--sidebar-width);
  max-width: var(--sidebar-width);
  background: var(--surface);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  height: 100vh;
  position: sticky;
  top: 0;
  z-index: 50;
  transition: margin-left 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.app-container.sidebar-collapsed .stocks-sidebar {
  margin-left: calc(-1 * var(--sidebar-width));
}

.sidebar-header {
  padding: 16px 14px 10px;
  border-bottom: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 10px;
  background: var(--surface);
}

.sidebar-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.sidebar-title-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.sidebar-title {
  font-size: 14px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--heading);
}

.sidebar-count-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 1px 7px;
  border-radius: 10px;
  background: var(--accent-light);
  color: var(--heading);
  border: 1px solid rgba(88, 166, 255, 0.25);
}

.sidebar-toggle-btn {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--heading);
  cursor: pointer;
  padding: 5px;
  width: 32px;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s ease;
  flex-shrink: 0;
}
.sidebar-toggle-btn:hover {
  background: var(--surface-hover);
  border-color: var(--heading);
  color: var(--accent);
}
.sidebar-toggle-icon {
  display: block;
  flex-shrink: 0;
}

/* Avoid duplicate toggle buttons: hide topbar open button when sidebar is open */
.app-container:not(.sidebar-collapsed) #sidebarOpenBtn {
  display: none !important;
}
.app-container.sidebar-collapsed #sidebarOpenBtn {
  display: inline-flex !important;
}

.sidebar-search-wrap {
  position: relative;
  display: flex;
  align-items: center;
}

.sidebar-search-wrap input {
  width: 100%;
  padding: 7px 28px 7px 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--background);
  color: var(--foreground);
  font-size: 13px;
  outline: none;
  transition: border-color 0.15s;
}
.sidebar-search-wrap input:focus {
  border-color: var(--heading);
  box-shadow: 0 0 0 2px var(--accent-light);
}

.search-clear-btn {
  position: absolute;
  right: 8px;
  background: transparent;
  border: none;
  color: var(--foreground);
  opacity: 0.6;
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
}
.search-clear-btn:hover { opacity: 1; color: var(--danger); }

.sidebar-filter-pills {
  display: flex;
  gap: 4px;
}

.filter-pill {
  flex: 1;
  padding: 4px 6px;
  font-size: 11px;
  font-weight: 600;
  border-radius: 5px;
  border: 1px solid var(--border);
  background: var(--background);
  color: var(--foreground);
  cursor: pointer;
  text-align: center;
  transition: all 0.15s;
}
.filter-pill:hover {
  background: var(--surface-hover);
  border-color: var(--heading);
}
.filter-pill.active {
  background: var(--heading);
  border-color: var(--heading);
  color: #fff;
}

.sidebar-stock-list {
  flex: 1;
  overflow-y: auto;
  padding: 6px 8px 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.sidebar-loading, .sidebar-empty {
  padding: 24px 14px;
  text-align: center;
  font-size: 13px;
  color: var(--foreground);
  opacity: 0.6;
}

.stock-card-item {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 8px 10px;
  border-radius: 6px;
  border: 1px solid transparent;
  background: var(--background);
  cursor: pointer;
  text-decoration: none;
  color: inherit;
  transition: all 0.12s ease;
}
.stock-card-item:hover {
  background: var(--surface-hover);
  border-color: var(--border);
}
.stock-card-item.active {
  background: var(--accent-light);
  border-color: var(--heading);
}

.stock-card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.stock-card-ticker {
  font-size: 13px;
  font-weight: 700;
  color: var(--strong);
}
.stock-card-item.active .stock-card-ticker {
  color: var(--heading);
}

.stock-card-badges {
  display: flex;
  align-items: center;
  gap: 4px;
}

.badge-mini {
  font-size: 10px;
  font-weight: 700;
  padding: 1px 5px;
  border-radius: 4px;
  line-height: 1.2;
}
.badge-buy { background: var(--success-bg); color: var(--success); border: 1px solid rgba(45, 164, 78, 0.3); }
.badge-watch { background: var(--warning-bg); color: var(--warning); border: 1px solid rgba(191, 135, 0, 0.3); }
.badge-pass { background: rgba(127,127,127,0.15); color: var(--foreground); opacity: 0.7; }
.badge-actionable { background: rgba(255, 193, 7, 0.25); color: #d97706; border: 1px solid #d97706; font-weight: 800; }
.badge-note { font-size: 11px; opacity: 0.8; }
.badge-visual { font-size: 11px; opacity: 0.8; }

.stock-card-mid {
  font-size: 12px;
  color: var(--foreground);
  opacity: 0.8;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.stock-card-bot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 11px;
  opacity: 0.75;
}

/* Main Workspace */
.main-workspace {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

/* Topbar Header Toolbar */
.workspace-topbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 12px 28px;
  background: var(--background);
  border-bottom: 1px solid var(--border);
}

.toolbar-left, .toolbar-right {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.nav-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 6px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--heading);
  text-decoration: none;
  font-size: 13px;
  font-weight: 500;
  line-height: 1.2;
  background: var(--surface);
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}
.nav-btn:hover {
  background: var(--accent-light);
  border-color: var(--heading);
  color: var(--heading);
}
.nav-btn.back-btn { font-weight: 600; }
.nav-btn.highlight-btn { background: var(--heading); color: #fff; border-color: var(--heading); }
.nav-btn.highlight-btn:hover { opacity: 0.9; color: #fff; }

/* Sticky Tabs Bar */
.notes-nav-tabs {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 0 28px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  z-index: 39;
  overflow-x: auto;
}

.nav-tab {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 12px 18px;
  font-size: 14px;
  font-weight: 600;
  color: var(--foreground);
  opacity: 0.75;
  background: transparent;
  border: none;
  border-bottom: 3px solid transparent;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.15s ease;
}
.nav-tab:hover {
  opacity: 1;
  color: var(--heading);
  background: rgba(88, 166, 255, 0.05);
}
.nav-tab.active {
  opacity: 1;
  color: var(--heading);
  border-bottom-color: var(--heading);
  background: rgba(88, 166, 255, 0.08);
}

.tab-kbd {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 3px;
  background: rgba(127,127,127,0.2);
  color: var(--foreground);
  margin-left: 4px;
}

/* Tab Panels Container */
.tab-panels-container {
  flex: 1;
  padding: 32px 36px;
  max-width: 1240px;
  width: 100%;
  margin: 0 auto;
}

.tab-panel {
  display: none;
  animation: fadeIn 0.15s ease;
}
.tab-panel.active { display: block; }

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: translateY(0); }
}

/* Markdown Qualitative Body (Thesis & Primer) */
.markdown-body {
  font-size: 18px;
  line-height: 1.75;
}
.markdown-body h1 {
  color: var(--heading);
  font-size: 2.2em;
  margin-top: 0.8em;
  margin-bottom: 0.5em;
  font-weight: 700;
  border-bottom: 1px solid var(--border);
  padding-bottom: 0.3em;
}
.markdown-body h2 {
  color: var(--heading);
  font-size: 1.6em;
  margin-top: 1.4em;
  margin-bottom: 0.5em;
  font-weight: 600;
  border-bottom: 1px solid rgba(127,127,127,0.15);
  padding-bottom: 0.2em;
}
.markdown-body h3 {
  color: var(--heading);
  font-size: 1.25em;
  margin-top: 1.2em;
  margin-bottom: 0.4em;
  font-weight: 600;
}
.markdown-body p { margin-bottom: 0.9em; }
.markdown-body ul, .markdown-body ol { margin-bottom: 1em; padding-left: 1.5em; }
.markdown-body li { margin-bottom: 0.35em; }
.markdown-body strong { color: var(--strong); }
.markdown-body a { color: var(--heading); text-decoration: none; }
.markdown-body a:hover { text-decoration: underline; }
.markdown-body code {
  background: var(--surface);
  padding: 2px 7px;
  border-radius: 4px;
  font-size: 0.88em;
  border: 1px solid var(--border);
}
.markdown-body pre {
  background: var(--surface);
  padding: 16px;
  border-radius: 8px;
  overflow-x: auto;
  font-size: 0.88em;
  border: 1px solid var(--border);
  margin-bottom: 1.2em;
}
.markdown-body table {
  border-collapse: collapse;
  width: 100%;
  font-size: 0.95em;
  margin: 1.4em 0;
}
.markdown-body th, .markdown-body td {
  border: 1px solid var(--border);
  padding: 10px 14px;
  text-align: left;
}
.markdown-body th {
  background: var(--surface);
  font-weight: 600;
  color: var(--strong);
}
.markdown-body tr:hover { background: rgba(88, 166, 255, 0.04); }

/* In-page TIKR Interactive Chart Engine Styles */
.tikr-chart-widget {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 22px 26px 18px;
  margin: 32px 0 24px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.05);
  font-family: system-ui, -apple-system, sans-serif;
  transition: all 0.2s ease;
}
.tikr-chart-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 14px;
}
.tikr-title-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.tikr-metric-name {
  font-size: 1.25em;
  font-weight: 700;
  color: var(--heading);
  display: flex;
  align-items: center;
  gap: 10px;
}
.tikr-meta-badges {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.tikr-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 9px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
}
.tikr-badge-val {
  background: rgba(88, 166, 255, 0.15);
  color: var(--heading);
  border: 1px solid rgba(88, 166, 255, 0.3);
}
.tikr-badge-growth {
  background: rgba(46, 160, 67, 0.15);
  color: #2ea043;
  border: 1px solid rgba(46, 160, 67, 0.3);
}
.tikr-badge-neg {
  background: rgba(248, 81, 73, 0.15);
  color: #f85149;
  border: 1px solid rgba(248, 81, 73, 0.3);
}
.tikr-controls {
  display: flex;
  align-items: center;
  gap: 8px;
}
.tikr-btn-group {
  display: inline-flex;
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
}
.tikr-btn {
  padding: 6px 12px;
  font-size: 12px;
  font-weight: 600;
  border: none;
  background: var(--background);
  color: var(--foreground);
  cursor: pointer;
  transition: all 0.15s;
}
.tikr-btn:not(:last-child) { border-right: 1px solid var(--border); }
.tikr-btn:hover { background: var(--surface); color: var(--heading); }
.tikr-btn.active { background: var(--heading); color: #fff; }
.tikr-toggle-btn {
  padding: 6px 12px;
  font-size: 12px;
  font-weight: 600;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--background);
  color: var(--foreground);
  cursor: pointer;
  transition: all 0.15s;
}
.tikr-toggle-btn:hover { border-color: var(--heading); }
.tikr-toggle-btn.active {
  background: rgba(130, 80, 223, 0.18);
  border-color: #8250df;
  color: #8250df;
}
.tikr-pills-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-bottom: 14px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border);
}
.tikr-pill-label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-weight: 600;
  color: var(--foreground);
  opacity: 0.6;
  margin-right: 4px;
}
.tikr-pill {
  padding: 4px 10px;
  font-size: 12px;
  font-weight: 500;
  border-radius: 14px;
  border: 1px solid var(--border);
  background: var(--background);
  color: var(--foreground);
  cursor: pointer;
  transition: all 0.15s;
}
.tikr-pill:hover { border-color: var(--heading); color: var(--heading); }
.tikr-pill.active {
  background: var(--heading);
  border-color: var(--heading);
  color: #fff;
  font-weight: 600;
}
.tikr-canvas-container {
  position: relative;
  height: 290px;
  width: 100%;
}
.tikr-footer-hint {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 10px;
  font-size: 12px;
  color: var(--foreground);
  opacity: 0.7;
}
tr.tikr-clickable-row {
  cursor: pointer;
  transition: background 0.12s, border-left 0.12s;
}
tr.tikr-clickable-row:hover td {
  background: rgba(88, 166, 255, 0.08) !important;
}
tr.tikr-clickable-row.active-row td {
  background: rgba(88, 166, 255, 0.14) !important;
  font-weight: 600;
}
tr.tikr-clickable-row.active-row td:first-child {
  border-left: 4px solid var(--heading) !important;
  color: var(--heading);
}
.tikr-row-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 8px;
  background: var(--heading);
  opacity: 0;
  transition: opacity 0.15s;
}
tr.tikr-clickable-row:hover .tikr-row-dot { opacity: 0.5; }
tr.tikr-clickable-row.active-row .tikr-row-dot { opacity: 1; }

/* Scenario Target Visualization */
.scenario-chart-widget {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 22px 26px;
  margin: 28px 0;
  box-shadow: 0 4px 16px rgba(0,0,0,0.04);
}
.scenario-chart-title {
  font-size: 1.15em;
  font-weight: 700;
  color: var(--heading);
  margin-bottom: 6px;
}
.scenario-chart-sub {
  font-size: 0.85em;
  color: var(--foreground);
  opacity: 0.75;
  margin-bottom: 18px;
}
.scenario-bar-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.scenario-bar-row {
  display: flex;
  align-items: center;
  gap: 14px;
}
.scenario-bar-name {
  width: 140px;
  font-size: 13px;
  font-weight: 600;
  color: var(--strong);
}
.scenario-bar-track-wrap {
  flex: 1;
  position: relative;
  height: 28px;
  background: rgba(127,127,127,0.12);
  border-radius: 6px;
  overflow: hidden;
  display: flex;
  align-items: center;
}
.scenario-bar-fill {
  height: 100%;
  border-radius: 6px;
  display: flex;
  align-items: center;
  padding: 0 10px;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
  white-space: nowrap;
}
.scenario-bar-meta {
  width: 130px;
  text-align: right;
  font-size: 13px;
  font-weight: 600;
}

/* Financial Statements Panel */
.financials-view-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.financials-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 18px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
}

.view-switch-group {
  display: inline-flex;
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
}

.stmt-switch-btn {
  padding: 7px 14px;
  font-size: 13px;
  font-weight: 600;
  background: var(--background);
  color: var(--foreground);
  border: none;
  cursor: pointer;
  transition: all 0.15s;
}
.stmt-switch-btn:not(:last-child) { border-right: 1px solid var(--border); }
.stmt-switch-btn:hover { background: var(--surface-hover); color: var(--heading); }
.stmt-switch-btn.active { background: var(--heading); color: #fff; }

.financials-search-box input {
  padding: 6px 12px;
  font-size: 13px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--background);
  color: var(--foreground);
  width: 260px;
  outline: none;
}
.financials-search-box input:focus { border-color: var(--heading); }

.financials-units-meta {
  display: flex;
  align-items: center;
  gap: 10px;
}

.meta-pill {
  font-size: 12px;
  font-weight: 600;
  padding: 4px 8px;
  background: var(--accent-light);
  color: var(--heading);
  border-radius: 4px;
  border: 1px solid rgba(88, 166, 255, 0.2);
}

.stmt-toggle-btn {
  padding: 5px 10px;
  font-size: 12px;
  font-weight: 600;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--background);
  color: var(--foreground);
  cursor: pointer;
}
.stmt-toggle-btn:hover { border-color: var(--heading); color: var(--heading); }

.financials-table-wrap {
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
}

.financials-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.financials-table th, .financials-table td {
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  text-align: right;
  white-space: nowrap;
}
.financials-table th:first-child, .financials-table td:first-child {
  text-align: left;
  font-weight: 600;
  min-width: 240px;
  position: sticky;
  left: 0;
  background: var(--surface);
  z-index: 2;
  border-right: 1px solid var(--border);
}
.financials-table th {
  background: var(--surface-hover);
  color: var(--strong);
  font-weight: 700;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.financials-table tr:hover td {
  background: rgba(88, 166, 255, 0.08);
  cursor: pointer;
}
.financials-table tr.section-header-row td {
  background: rgba(127,127,127,0.12);
  font-weight: 700;
  color: var(--heading);
  text-align: left;
  font-size: 13px;
  letter-spacing: 0.05em;
  padding: 10px 12px;
}
.row-plot-hint {
  font-size: 10px;
  opacity: 0.5;
  margin-left: 6px;
}

/* Cross-Plotter Panel */
.cross-plotter-container {
  display: flex;
  flex-direction: column;
  gap: 18px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 24px;
}

.plotter-top-controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--border);
}

.plotter-presets-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.plotter-section-label {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.05em;
  color: var(--foreground);
  opacity: 0.6;
  margin-right: 4px;
}

.preset-btn {
  padding: 5px 12px;
  font-size: 12px;
  font-weight: 600;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--background);
  color: var(--foreground);
  cursor: pointer;
  transition: all 0.15s;
}
.preset-btn:hover { border-color: var(--heading); color: var(--heading); }
.preset-btn.active {
  background: var(--heading);
  border-color: var(--heading);
  color: #fff;
}

.plotter-actions-bar {
  display: flex;
  align-items: center;
  gap: 8px;
}

.plotter-btn {
  padding: 6px 14px;
  font-size: 12px;
  font-weight: 600;
  border-radius: 6px;
  cursor: pointer;
  border: 1px solid var(--border);
  transition: all 0.15s;
}
.plotter-btn.primary-btn { background: var(--heading); color: #fff; border-color: var(--heading); }
.plotter-btn.primary-btn:hover { opacity: 0.9; }
.plotter-btn.secondary-btn { background: var(--background); color: var(--foreground); }
.plotter-btn.secondary-btn:hover { background: var(--surface-hover); border-color: var(--heading); }

.plotter-type-group {
  display: inline-flex;
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
}
.plotter-type-btn {
  padding: 5px 10px;
  font-size: 12px;
  font-weight: 600;
  border: none;
  background: var(--background);
  color: var(--foreground);
  cursor: pointer;
}
.plotter-type-btn:first-child { border-right: 1px solid var(--border); }
.plotter-type-btn.active { background: var(--heading); color: #fff; }

.plotter-picker-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px 16px;
  background: var(--background);
  border: 1px solid var(--border);
  border-radius: 8px;
}

.metric-picker-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 14px;
}

.picker-input-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 260px;
}
.picker-input-wrap label { font-size: 12px; font-weight: 600; }
.plotter-select {
  flex: 1;
  padding: 6px 10px;
  font-size: 13px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--surface);
  color: var(--foreground);
  outline: none;
}

.picker-axis-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  font-weight: 600;
}
.axis-radio-group {
  display: flex;
  align-items: center;
  gap: 10px;
}
.axis-radio-group label {
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
}

.active-metrics-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.metric-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 16px;
  font-size: 12px;
  font-weight: 600;
  background: var(--surface);
  border: 1px solid var(--border);
}
.chip-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
}
.chip-axis-badge {
  font-size: 10px;
  padding: 1px 4px;
  border-radius: 3px;
  background: rgba(127,127,127,0.2);
}
.chip-remove-btn {
  background: transparent;
  border: none;
  color: var(--foreground);
  opacity: 0.6;
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
}
.chip-remove-btn:hover { opacity: 1; color: var(--danger); }

.plotter-canvas-container {
  position: relative;
  height: 380px;
  width: 100%;
}

.plotter-footer-hint {
  font-size: 12px;
  color: var(--foreground);
  opacity: 0.7;
}

/* Technical Analysis Panel */
.technicals-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.technicals-summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 18px;
}

.tech-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.03);
}

.tech-card-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--heading);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 14px;
}

.range-gauge-wrap {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.range-labels {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 600;
}
.range-cur { color: var(--heading); font-size: 15px; font-weight: 700; }

.range-track {
  position: relative;
  height: 10px;
  background: rgba(127,127,127,0.18);
  border-radius: 5px;
  overflow: visible;
}
.range-fill {
  height: 100%;
  background: linear-gradient(90deg, #3fb950, #d29922, #f85149);
  border-radius: 5px;
}
.range-thumb {
  position: absolute;
  top: -4px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--heading);
  border: 2px solid #fff;
  box-shadow: 0 2px 6px rgba(0,0,0,0.3);
  transform: translateX(-50%);
}

.range-meta {
  font-size: 12px;
  color: var(--foreground);
  opacity: 0.8;
  text-align: center;
}

.stats-mini-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}
.stat-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.stat-lbl { font-size: 11px; opacity: 0.7; }
.stat-val { font-size: 14px; font-weight: 600; color: var(--strong); }

.benchmark-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.benchmark-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
}
.bm-label { font-weight: 600; }
.bm-val { font-weight: 700; color: var(--heading); }
.benchmark-status {
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 4px;
  background: var(--background);
  border: 1px solid var(--border);
  margin-bottom: 6px;
}

.tech-card-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.tech-card-sub { font-size: 12px; opacity: 0.6; }

/* Valuation Models Panel */
.valuation-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.valuation-banner-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 16px;
}

.val-metric-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.val-metric-lbl { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; opacity: 0.7; }
.val-metric-val { font-size: 22px; font-weight: 700; color: var(--heading); }
.val-metric-sub { font-size: 12px; opacity: 0.75; }

.verdict-badge-large {
  display: inline-flex;
  align-items: center;
  font-size: 18px;
  font-weight: 800;
  padding: 2px 10px;
  border-radius: 6px;
  width: fit-content;
}
.verdict-BUY { color: var(--success); background: var(--success-bg); border: 1px solid rgba(45,164,78,0.3); }
.verdict-WATCH { color: var(--warning); background: var(--warning-bg); border: 1px solid rgba(191,135,0,0.3); }
.verdict-PASS { color: var(--danger); background: var(--danger-bg); border: 1px solid rgba(207,34,46,0.3); }

.scenario-bar-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 6px;
}
.scenario-bar-row {
  display: flex;
  align-items: center;
  gap: 14px;
}
.scenario-bar-name {
  width: 140px;
  font-size: 13px;
  font-weight: 600;
  color: var(--strong);
}
.scenario-bar-track-wrap {
  flex: 1;
  position: relative;
  height: 28px;
  background: rgba(127,127,127,0.12);
  border-radius: 6px;
  overflow: hidden;
  display: flex;
  align-items: center;
}
.scenario-bar-fill {
  height: 100%;
  border-radius: 6px;
  display: flex;
  align-items: center;
  padding: 0 10px;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
  white-space: nowrap;
}
.scenario-bar-meta {
  width: 130px;
  text-align: right;
  font-size: 13px;
  font-weight: 600;
}

.val-table-wrap table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.val-table-wrap th, .val-table-wrap td {
  border: 1px solid var(--border);
  padding: 10px 14px;
  text-align: left;
}
.val-table-wrap th { background: var(--surface-hover); font-weight: 600; }
.val-table-wrap tr:hover { background: rgba(88, 166, 255, 0.05); }

.empty-hint {
  padding: 20px;
  text-align: center;
  font-size: 13px;
  opacity: 0.6;
}

.loading-spinner-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 40px;
  font-size: 13px;
  color: var(--foreground);
  opacity: 0.7;
}
.spinner {
  width: 20px;
  height: 20px;
  border: 2px solid var(--border);
  border-top-color: var(--heading);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* Fast Tooltips (delay dropped to approx 1/3 of browser native: ~220ms) */
.fast-tooltip-card {
  position: fixed;
  z-index: 100000;
  display: none;
  pointer-events: none;
  max-width: 380px;
  padding: 8px 12px;
  font-family: system-ui, -apple-system, sans-serif;
  font-size: 12px;
  line-height: 1.45;
  color: var(--foreground);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.25);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  opacity: 0;
  transform: translateY(3px);
  transition: opacity 0.1s ease, transform 0.1s ease;
  white-space: normal;
  word-break: break-word;
}
.fast-tooltip-card.visible {
  opacity: 1;
  transform: translateY(0);
}
.fast-tooltip-card .ft-line {
  padding: 2px 0;
}
.fast-tooltip-card .ft-line:not(:last-child) {
  border-bottom: 1px solid var(--border);
}
.fast-tooltip-card .ft-title {
  font-weight: 700;
  color: var(--heading);
  margin-bottom: 2px;
}

/* Responsive adjustments */
@media (max-width: 900px) {
  .stocks-sidebar {
    position: fixed;
    left: 0;
    top: 0;
    bottom: 0;
    box-shadow: 0 0 30px rgba(0,0,0,0.3);
  }
  .app-container.sidebar-collapsed .stocks-sidebar,
  .app-container:not(.sidebar-open) .stocks-sidebar {
    margin-left: calc(-1 * var(--sidebar-width));
  }
  .app-container.sidebar-open .stocks-sidebar {
    margin-left: 0 !important;
  }
  .app-container #sidebarOpenBtn {
    display: inline-flex !important;
  }
  .tab-panels-container { padding: 18px 14px; }
  .markdown-body { font-size: 16px; }
  .workspace-topbar { padding: 10px 14px; }
  .notes-nav-tabs { padding: 0 14px; }
}
"""


def _get_javascript() -> str:
    """Return complete client-side JavaScript workstation engine."""
    return """
(function() {
  'use strict';

  let currentTicker = window.__CURRENT_TICKER__ || '';
  let stocksCatalog = window.__INITIAL_CATALOG__ || null;
  let activeFilter = 'all';
  let searchQuery = '';
  let tickerCacheData = {};
  let crossPlotterChart = null;
  let activePlotterMetrics = [];
  let plotterChartType = 'line';
  let isSidebarCollapsed = localStorage.getItem('invest_notes_sidebar_collapsed') === 'true';

  // --- INITIALIZATION ---
  document.addEventListener('DOMContentLoaded', initWorkstation);

  function initWorkstation() {
    setupSidebarToggle();
    setupTabsNavigation();
    setupKeyboardShortcuts();
    setupStatementsControls();
    setupCrossPlotterControls();
    initFastTooltips(220);

    if (stocksCatalog && stocksCatalog.length) {
      renderSidebarList();
    } else {
      fetchCatalog();
    }

    // Load initial ticker data
    if (currentTicker) {
      loadTickerData(currentTicker);
    }

    // Initialize in-page markdown interactive tables
    initMarkdownTables(document.getElementById('markdownBody'));

    // Handle hash on page load
    const hash = (window.location.hash || '').replace('#', '');
    if (['thesis', 'financials', 'plotter', 'technicals', 'valuation'].includes(hash)) {
      switchTab(hash);
    }
  }

  // --- SIDEBAR MANAGEMENT ---
  function setupSidebarToggle() {
    const appContainer = document.getElementById('appContainer');
    const collapseBtn = document.getElementById('sidebarCollapseBtn');
    const openBtn = document.getElementById('sidebarOpenBtn');

    if (isSidebarCollapsed) {
      appContainer.classList.add('sidebar-collapsed');
      appContainer.classList.remove('sidebar-open');
    } else {
      appContainer.classList.remove('sidebar-collapsed');
      appContainer.classList.add('sidebar-open');
    }

    function toggleSidebar() {
      isSidebarCollapsed = !isSidebarCollapsed;
      appContainer.classList.toggle('sidebar-collapsed', isSidebarCollapsed);
      appContainer.classList.toggle('sidebar-open', !isSidebarCollapsed);
      localStorage.setItem('invest_notes_sidebar_collapsed', isSidebarCollapsed ? 'true' : 'false');
    }

    if (collapseBtn) collapseBtn.addEventListener('click', toggleSidebar);
    if (openBtn) openBtn.addEventListener('click', toggleSidebar);

    // Search input
    const searchInput = document.getElementById('sidebarSearchInput');
    const clearBtn = document.getElementById('sidebarSearchClear');

    if (searchInput) {
      searchInput.addEventListener('input', (e) => {
        searchQuery = e.target.value.trim().toLowerCase();
        if (clearBtn) clearBtn.style.display = searchQuery ? 'block' : 'none';
        renderSidebarList();
      });
    }

    if (clearBtn) {
      clearBtn.addEventListener('click', () => {
        if (searchInput) {
          searchInput.value = '';
          searchQuery = '';
          clearBtn.style.display = 'none';
          searchInput.focus();
          renderSidebarList();
        }
      });
    }

    // Filter pills
    const pills = document.querySelectorAll('#sidebarFilterPills .filter-pill');
    pills.forEach(pill => {
      pill.addEventListener('click', () => {
        pills.forEach(p => p.classList.remove('active'));
        pill.classList.add('active');
        activeFilter = pill.getAttribute('data-filter') || 'all';
        renderSidebarList();
      });
    });
  }

  async function fetchCatalog() {
    try {
      const res = await fetch('/api/notes/catalog');
      if (res.ok) {
        stocksCatalog = await res.json();
        renderSidebarList();
      }
    } catch (err) {
      console.warn('Failed to load notes catalog:', err);
    }
  }

  function renderSidebarList() {
    const container = document.getElementById('sidebarStockList');
    const countBadge = document.getElementById('sidebarStockCount');
    if (!container || !stocksCatalog) return;

    let items = stocksCatalog.slice();

    // Filter by pills
    if (activeFilter === 'buy') {
      items = items.filter(s => (s.verdict || '').toUpperCase() === 'BUY');
    } else if (activeFilter === 'watch') {
      items = items.filter(s => (s.verdict || '').toUpperCase() === 'WATCH');
    } else if (activeFilter === 'notes') {
      items = items.filter(s => s.has_note || s.note_available);
    }

    // Filter by search query
    if (searchQuery) {
      items = items.filter(s => {
        const t = (s.ticker || '').toLowerCase();
        const n = (s.company_name || '').toLowerCase();
        return t.includes(searchQuery) || n.includes(searchQuery);
      });
    }

    if (countBadge) {
      countBadge.textContent = items.length;
    }

    if (!items.length) {
      container.innerHTML = '<div class="sidebar-empty">No matching stocks found</div>';
      return;
    }

    let html = '';
    items.forEach(stock => {
      const isAct = stock.ticker === currentTicker;
      const verdict = (stock.verdict || '').toUpperCase();
      let vBadge = '';
      if (verdict === 'BUY') vBadge = '<span class="badge-mini badge-buy">BUY</span>';
      else if (verdict === 'WATCH') vBadge = '<span class="badge-mini badge-watch">WATCH</span>';
      else if (verdict === 'PASS') vBadge = '<span class="badge-mini badge-pass">PASS</span>';

      const entryBadge = stock.entry_actionable ? '<span class="badge-mini badge-actionable" title="Price is at or below recommended entry">⚡ Entry</span>' : '';
      const noteBadge = (stock.has_note || stock.note_available) ? '<span class="badge-mini badge-note" title="Analysis note available">📄</span>' : '';
      const visualBadge = stock.has_visual ? '<span class="badge-mini badge-visual" title="Visual companion available">🎨</span>' : '';

      const priceStr = stock.current_price != null ? '$' + Number(stock.current_price).toFixed(2) : '--';
      let evStr = '';
      if (stock.expected_value_pct != null) {
        const ev = Number(stock.expected_value_pct);
        const col = ev >= 0 ? '#3fb950' : '#f85149';
        evStr = `<span style="color:${col};font-weight:600;">${ev > 0 ? '+' : ''}${ev.toFixed(1)}% EV</span>`;
      } else if (stock.best_margin != null) {
        const m = Number(stock.best_margin) * 100;
        evStr = `<span>${m.toFixed(0)}% margin</span>`;
      }

      // Build rich explanation tooltip (triggers in ~220ms, 1/3rd native hover delay)
      const tipParts = [`${stock.ticker} - ${stock.company_name || stock.ticker}`];
      if (verdict) tipParts.push(`Verdict: ${verdict}`);
      if (stock.conviction) tipParts.push(`Conviction: ${stock.conviction}`);
      if (stock.quality_score) tipParts.push(`Quality: ${stock.quality_score}/25`);
      if (stock.expected_value_pct != null) {
        const ev = Number(stock.expected_value_pct);
        tipParts.push(`Expected Value: ${ev > 0 ? '+' : ''}${ev.toFixed(1)}%`);
      }
      if (stock.target_price || stock.fair_value) {
        const tp = Number(stock.target_price || stock.fair_value);
        tipParts.push(`Target Price: $${tp.toFixed(2)}`);
      }
      if (stock.entry_price) {
        const ep = Number(stock.entry_price);
        tipParts.push(`Entry Price: $${ep.toFixed(2)}${stock.entry_actionable ? ' (Actionable Now)' : ''}`);
      }
      if (stock.best_margin != null) {
        tipParts.push(`Best Margin: ${(Number(stock.best_margin) * 100).toFixed(0)}%`);
      }
      const cardTip = tipParts.join(' | ');

      html += `
        <a class="stock-card-item ${isAct ? 'active' : ''}" data-ticker="${stock.ticker}" data-tooltip="${htmlEscape(cardTip)}" href="/api/notes/${stock.ticker}">
          <div class="stock-card-top">
            <span class="stock-card-ticker">${stock.ticker}</span>
            <div class="stock-card-badges">
              ${entryBadge}
              ${vBadge}
              ${noteBadge}
              ${visualBadge}
            </div>
          </div>
          <div class="stock-card-mid">${stock.company_name || stock.ticker}</div>
          <div class="stock-card-bot">
            <span>${priceStr}</span>
            ${evStr}
          </div>
        </a>
      `;
    });

    container.innerHTML = html;

    // Attach PJAX click handlers
    container.querySelectorAll('.stock-card-item').forEach(card => {
      card.addEventListener('click', (e) => {
        e.preventDefault();
        const t = card.getAttribute('data-ticker');
        if (t && t !== currentTicker) {
          navigateTickerPjax(t);
        }
      });
    });
  }

  // --- PJAX SEAMLESS NAVIGATION ---
  async function navigateTickerPjax(newTicker) {
    const progressBar = document.getElementById('topProgressBar');
    if (progressBar) {
      progressBar.style.width = '30%';
      progressBar.style.opacity = '1';
    }

    try {
      const res = await fetch(`/api/notes/${newTicker}`);
      if (!res.ok) throw new Error('Failed to load note');

      if (progressBar) progressBar.style.width = '70%';

      const htmlText = await res.text();
      const parser = new DOMParser();
      const doc = parser.parseFromString(htmlText, 'text/html');

      // Swap topbar
      const newTopbar = doc.getElementById('workspaceTopbar');
      const curTopbarContainer = document.getElementById('topbarContainer');
      if (newTopbar && curTopbarContainer) {
        curTopbarContainer.innerHTML = '';
        curTopbarContainer.appendChild(newTopbar);
        // Re-bind topbar buttons
        const openBtn = document.getElementById('sidebarOpenBtn');
        if (openBtn) openBtn.addEventListener('click', () => {
          isSidebarCollapsed = !isSidebarCollapsed;
          const app = document.getElementById('appContainer');
          app.classList.toggle('sidebar-collapsed', isSidebarCollapsed);
          app.classList.toggle('sidebar-open', !isSidebarCollapsed);
          localStorage.setItem('invest_notes_sidebar_collapsed', isSidebarCollapsed ? 'true' : 'false');
        });
      }

      // Swap markdown body
      const newBody = doc.getElementById('markdownBody');
      const curBody = document.getElementById('markdownBody');
      if (newBody && curBody) {
        curBody.innerHTML = newBody.innerHTML;
        initMarkdownTables(curBody);
      }

      // Update state
      currentTicker = newTicker;
      window.__CURRENT_TICKER__ = newTicker;
      document.title = `${newTicker} - Analysis Workstation`;
      window.history.pushState({ ticker: newTicker }, '', `/api/notes/${newTicker}`);

      // Update active highlight in sidebar
      document.querySelectorAll('#sidebarStockList .stock-card-item').forEach(c => {
        c.classList.toggle('active', c.getAttribute('data-ticker') === newTicker);
      });

      // Load data for other tabs
      loadTickerData(newTicker);

      // Re-trigger TradingView if on technicals tab
      const activeTabBtn = document.querySelector('#notesNavTabs .nav-tab.active');
      if (activeTabBtn && activeTabBtn.getAttribute('data-tab') === 'technicals') {
        loadTradingView(newTicker);
      }

    } catch (err) {
      console.error('PJAX navigation failed:', err);
      window.location.href = `/api/notes/${newTicker}`;
    } finally {
      if (progressBar) {
        progressBar.style.width = '100%';
        setTimeout(() => {
          progressBar.style.opacity = '0';
          progressBar.style.width = '0%';
        }, 250);
      }
    }
  }

  window.addEventListener('popstate', (e) => {
    if (e.state && e.state.ticker) {
      navigateTickerPjax(e.state.ticker);
    }
  });

  // --- TABS NAVIGATION ---
  function setupTabsNavigation() {
    const tabs = document.querySelectorAll('#notesNavTabs .nav-tab');
    tabs.forEach(tab => {
      tab.addEventListener('click', () => {
        const tabId = tab.getAttribute('data-tab');
        if (tabId) switchTab(tabId);
      });
    });
  }

  function switchTab(tabId) {
    document.querySelectorAll('#notesNavTabs .nav-tab').forEach(t => {
      t.classList.toggle('active', t.getAttribute('data-tab') === tabId);
    });

    document.querySelectorAll('.tab-panels-container .tab-panel').forEach(p => {
      p.classList.toggle('active', p.getAttribute('data-panel') === tabId);
    });

    window.location.hash = tabId;

    if (tabId === 'plotter') {
      setTimeout(() => {
        if (crossPlotterChart) crossPlotterChart.resize();
      }, 50);
    } else if (tabId === 'technicals') {
      loadTradingView(currentTicker);
    }
  }

  function setupKeyboardShortcuts() {
    window.addEventListener('keydown', (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') {
        if (e.key === 'Escape') e.target.blur();
        return;
      }

      // 1 to 5 switch tabs
      if (e.key === '1') switchTab('thesis');
      else if (e.key === '2') switchTab('financials');
      else if (e.key === '3') switchTab('plotter');
      else if (e.key === '4') switchTab('technicals');
      else if (e.key === '5') switchTab('valuation');
      // [ or Ctrl+B toggle sidebar
      else if (e.key === '[' || ((e.ctrlKey || e.metaKey) && (e.key === 'b' || e.key === 'B'))) {
        e.preventDefault();
        const app = document.getElementById('appContainer');
        isSidebarCollapsed = !isSidebarCollapsed;
        app.classList.toggle('sidebar-collapsed', isSidebarCollapsed);
        app.classList.toggle('sidebar-open', !isSidebarCollapsed);
        localStorage.setItem('invest_notes_sidebar_collapsed', isSidebarCollapsed ? 'true' : 'false');
      }
      // / focuses search
      else if (e.key === '/') {
        e.preventDefault();
        const inp = document.getElementById('sidebarSearchInput');
        if (inp) inp.focus();
      }
    });
  }

  // --- FETCH TICKER DATA ---
  async function loadTickerData(ticker) {
    try {
      const res = await fetch(`/api/notes/${ticker}/data`);
      if (res.ok) {
        const data = await res.json();
        tickerCacheData[ticker] = data;
        populateFinancialStatements(data);
        populateCrossPlotter(data);
        populateTechnicals(data);
        populateValuation(data);
      } else {
        showNoDataState();
      }
    } catch (err) {
      console.warn('Could not load ticker data:', err);
      showNoDataState();
    }
  }

  function showNoDataState() {
    const fc = document.getElementById('financialsContent');
    if (fc) fc.innerHTML = '<div class="empty-hint">No financial statements cache available for this ticker.</div>';
    const pc = document.getElementById('plotterCanvasContainer');
    if (pc && !crossPlotterChart) pc.innerHTML = '<div class="empty-hint">No statement metrics available to plot.</div>';
  }

  // --- FINANCIAL STATEMENTS PANEL ---
  let activeStmtView = 'merged';
  let humanizeNumbers = true;
  let stmtFilterText = '';

  function setupStatementsControls() {
    const switchBtns = document.querySelectorAll('#stmtViewSwitchGroup .stmt-switch-btn');
    switchBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        switchBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        activeStmtView = btn.getAttribute('data-view') || 'merged';
        renderStatementsTable();
      });
    });

    const filterInput = document.getElementById('stmtFilterInput');
    if (filterInput) {
      filterInput.addEventListener('input', (e) => {
        stmtFilterText = e.target.value.trim().toLowerCase();
        renderStatementsTable();
      });
    }

    const fmtToggle = document.getElementById('stmtFormatToggle');
    if (fmtToggle) {
      fmtToggle.addEventListener('click', () => {
        humanizeNumbers = !humanizeNumbers;
        fmtToggle.textContent = humanizeNumbers ? 'Format: B/M/K' : 'Format: Exact';
        renderStatementsTable();
      });
    }
  }

  function populateFinancialStatements(data) {
    const curBadge = document.getElementById('stmtCurrencyBadge');
    if (curBadge) {
      curBadge.textContent = `Currency: ${data.financial_statements_currency || 'USD'}`;
    }
    renderStatementsTable();
  }

  function normalizeStatementRows(raw) {
    if (!raw) return [];
    if (Array.isArray(raw)) {
      return raw.map(row => {
        const name = row.index || row.name || 'Metric';
        const vals = {};
        Object.keys(row).forEach(k => {
          if (k !== 'index' && k !== 'name') {
            vals[k] = row[k];
          }
        });
        return { name, values: vals };
      });
    } else if (typeof raw === 'object') {
      return Object.keys(raw).map(name => {
        const val = raw[name];
        if (typeof val === 'object' && val !== null) {
          return { name, values: val };
        } else {
          return { name, values: { 'Latest': val } };
        }
      });
    }
    return [];
  }

  function renderStatementsTable() {
    const container = document.getElementById('financialsContent');
    const data = tickerCacheData[currentTicker];
    if (!container || !data) return;

    const incomeRows = normalizeStatementRows(data.income);
    const balanceRows = normalizeStatementRows(data.balance_sheet);
    const cashflowRows = normalizeStatementRows(data.cashflow);

    let sections = [];
    if (activeStmtView === 'merged') {
      sections = [
        { title: 'Income Statement', rows: incomeRows },
        { title: 'Balance Sheet', rows: balanceRows },
        { title: 'Cash Flow', rows: cashflowRows },
      ];
    } else if (activeStmtView === 'income') {
      sections = [{ title: 'Income Statement', rows: incomeRows }];
    } else if (activeStmtView === 'balance') {
      sections = [{ title: 'Balance Sheet', rows: balanceRows }];
    } else if (activeStmtView === 'cashflow') {
      sections = [{ title: 'Cash Flow', rows: cashflowRows }];
    }

    // Collect all year columns across rows
    const yearSet = new Set();
    sections.forEach(sec => {
      sec.rows.forEach(r => {
        Object.keys(r.values).forEach(y => yearSet.add(y));
      });
    });

    const years = Array.from(yearSet).sort((a, b) => b.localeCompare(a)); // Most recent on left

    if (!years.length) {
      container.innerHTML = '<div class="empty-hint">No financial statements data available.</div>';
      return;
    }

    let tableHtml = '<table class="financials-table"><thead><tr><th>Line Item</th>';
    years.forEach(y => {
      const cleanYear = y.split(' ')[0].split('-')[0];
      tableHtml += `<th>FY ${cleanYear}</th>`;
    });
    tableHtml += '</tr></thead><tbody>';

    sections.forEach(sec => {
      let filteredRows = sec.rows;
      if (stmtFilterText) {
        filteredRows = filteredRows.filter(r => r.name.toLowerCase().includes(stmtFilterText));
      }
      if (!filteredRows.length && stmtFilterText) return;

      if (sections.length > 1) {
        tableHtml += `<tr class="section-header-row"><td colspan="${years.length + 1}">▼ ${sec.title}</td></tr>`;
      }

      filteredRows.forEach(r => {
        tableHtml += `<tr class="stmt-row" data-metric="${r.name}" title="Click to plot in Cross-Plotter">`;
        tableHtml += `<td>${r.name} <span class="row-plot-hint">📈 plot</span></td>`;
        years.forEach(y => {
          const rawV = r.values[y];
          tableHtml += `<td>${formatNumber(rawV, humanizeNumbers)}</td>`;
        });
        tableHtml += '</tr>';
      });
    });

    tableHtml += '</tbody></table>';
    container.innerHTML = tableHtml;

    // Row click -> plot in Cross-Plotter
    container.querySelectorAll('tr.stmt-row').forEach(tr => {
      tr.addEventListener('click', () => {
        const metric = tr.getAttribute('data-metric');
        if (metric) {
          addMetricToPlotter(metric, 'left');
          switchTab('plotter');
        }
      });
    });
  }

  function formatNumber(v, humanize) {
    if (v === null || v === undefined || isNaN(v)) return '--';
    const num = Number(v);
    if (!humanize) return num.toLocaleString();

    const abs = Math.abs(num);
    if (abs >= 1e12) return (num / 1e12).toFixed(2) + 'T';
    if (abs >= 1e9) return (num / 1e9).toFixed(2) + 'B';
    if (abs >= 1e6) return (num / 1e6).toFixed(2) + 'M';
    if (abs >= 1e3) return (num / 1e3).toFixed(1) + 'K';
    return num.toLocaleString();
  }

  // --- CROSS-PLOTTER PANEL ---
  const PALETTE = [
    '#58a6ff', '#3fb950', '#d29922', '#bc8cff', '#f85149',
    '#2da44e', '#0969da', '#f0883e', '#e3b341', '#a371f7'
  ];

  function setupCrossPlotterControls() {
    const presets = document.querySelectorAll('.plotter-presets-bar .preset-btn');
    presets.forEach(p => {
      p.addEventListener('click', () => {
        presets.forEach(btn => btn.classList.remove('active'));
        p.classList.add('active');
        applyPlotterPreset(p.getAttribute('data-preset'));
      });
    });

    const addBtn = document.getElementById('plotterAddMetricBtn');
    if (addBtn) {
      addBtn.addEventListener('click', () => {
        const select = document.getElementById('plotterMetricSelect');
        const axisChoice = document.querySelector('input[name="plotterAxisChoice"]:checked')?.value || 'left';
        if (select && select.value) {
          addMetricToPlotter(select.value, axisChoice);
        }
      });
    }

    const clearBtn = document.getElementById('plotterClearBtn');
    if (clearBtn) {
      clearBtn.addEventListener('click', () => {
        activePlotterMetrics = [];
        renderPlotterChips();
        renderPlotterChart();
      });
    }

    const typeBtns = document.querySelectorAll('.plotter-type-group .plotter-type-btn');
    typeBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        typeBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        plotterChartType = btn.getAttribute('data-type') || 'line';
        renderPlotterChart();
      });
    });
  }

  function populateCrossPlotter(data) {
    const select = document.getElementById('plotterMetricSelect');
    if (!select) return;

    select.innerHTML = '<option value="">-- Choose any metric from statements --</option>';

    const incRows = normalizeStatementRows(data.income);
    const balRows = normalizeStatementRows(data.balance_sheet);
    const cfRows = normalizeStatementRows(data.cashflow);

    function addOptGroup(label, rows) {
      if (!rows.length) return;
      const group = document.createElement('optgroup');
      group.label = label;
      rows.forEach(r => {
        const opt = document.createElement('option');
        opt.value = r.name;
        opt.textContent = r.name;
        group.appendChild(opt);
      });
      select.appendChild(group);
    }

    addOptGroup('Income Statement', incRows);
    addOptGroup('Balance Sheet', balRows);
    addOptGroup('Cash Flow Statement', cfRows);

    // Apply default preset (Growth vs Debt)
    applyPlotterPreset('growth-debt');
  }

  function findRowFuzzy(rows, candidates) {
    for (const c of candidates) {
      const found = rows.find(r => r.name.toLowerCase().includes(c.toLowerCase()));
      if (found) return found;
    }
    return null;
  }

  function applyPlotterPreset(presetName) {
    const data = tickerCacheData[currentTicker];
    if (!data) return;

    const inc = normalizeStatementRows(data.income);
    const bal = normalizeStatementRows(data.balance_sheet);
    const cf = normalizeStatementRows(data.cashflow);

    activePlotterMetrics = [];

    if (presetName === 'growth-debt') {
      const rev = findRowFuzzy(inc, ['Total Revenue', 'Operating Revenue', 'Revenue']);
      const debt = findRowFuzzy(bal, ['Total Debt', 'Long Term Debt', 'Net Debt']);
      if (rev) activePlotterMetrics.push({ name: rev.name, axis: 'left', type: 'line', color: PALETTE[0] });
      if (debt) activePlotterMetrics.push({ name: debt.name, axis: 'right', type: 'bar', color: PALETTE[4] });
    } else if (presetName === 'cash-quality') {
      const ocf = findRowFuzzy(cf, ['Operating Cash Flow', 'Cash Flow From Continuing Operating Activities', 'Cash From Operations']);
      const fcf = findRowFuzzy(cf, ['Free Cash Flow', 'FreeCashFlow']);
      const net = findRowFuzzy(inc, ['Net Income', 'Net Income Common']);
      if (ocf) activePlotterMetrics.push({ name: ocf.name, axis: 'left', type: 'line', color: PALETTE[1] });
      if (fcf) activePlotterMetrics.push({ name: fcf.name, axis: 'left', type: 'line', color: PALETTE[0] });
      if (net) activePlotterMetrics.push({ name: net.name, axis: 'left', type: 'line', color: PALETTE[2] });
    } else if (presetName === 'capex-cf') {
      const ocf = findRowFuzzy(cf, ['Operating Cash Flow', 'Cash From Operations']);
      const capex = findRowFuzzy(cf, ['Capital Expenditure', 'Capital Expenditures', 'Payments For Property']);
      if (ocf) activePlotterMetrics.push({ name: ocf.name, axis: 'left', type: 'line', color: PALETTE[1] });
      if (capex) activePlotterMetrics.push({ name: capex.name, axis: 'right', type: 'bar', color: PALETTE[4] });
    } else if (presetName === 'capital-structure') {
      const assets = findRowFuzzy(bal, ['Total Assets']);
      const liab = findRowFuzzy(bal, ['Total Liabilities', 'Total Liabilities Net']);
      const eq = findRowFuzzy(bal, ['Stockholders Equity', 'Common Stock Equity', 'Total Equity']);
      if (assets) activePlotterMetrics.push({ name: assets.name, axis: 'left', type: 'line', color: PALETTE[0] });
      if (liab) activePlotterMetrics.push({ name: liab.name, axis: 'left', type: 'line', color: PALETTE[4] });
      if (eq) activePlotterMetrics.push({ name: eq.name, axis: 'left', type: 'line', color: PALETTE[1] });
    } else if (presetName === 'margins') {
      const gross = findRowFuzzy(inc, ['Gross Profit']);
      const op = findRowFuzzy(inc, ['Operating Income']);
      const net = findRowFuzzy(inc, ['Net Income']);
      if (gross) activePlotterMetrics.push({ name: gross.name, axis: 'left', type: 'line', color: PALETTE[0] });
      if (op) activePlotterMetrics.push({ name: op.name, axis: 'left', type: 'line', color: PALETTE[1] });
      if (net) activePlotterMetrics.push({ name: net.name, axis: 'left', type: 'line', color: PALETTE[2] });
    }

    renderPlotterChips();
    renderPlotterChart();
  }

  function addMetricToPlotter(metricName, axis) {
    if (activePlotterMetrics.some(m => m.name === metricName)) return;
    const color = PALETTE[activePlotterMetrics.length % PALETTE.length];
    activePlotterMetrics.push({
      name: metricName,
      axis: axis || 'left',
      type: 'line',
      color: color,
    });
    renderPlotterChips();
    renderPlotterChart();
  }

  function renderPlotterChips() {
    const container = document.getElementById('plotterActiveChips');
    if (!container) return;

    if (!activePlotterMetrics.length) {
      container.innerHTML = '<span style="font-size:12px;opacity:0.6;">No metrics plotted. Choose a preset or pick a line item above.</span>';
      return;
    }

    let html = '';
    activePlotterMetrics.forEach((m, idx) => {
      html += `
        <div class="metric-chip">
          <span class="chip-dot" style="background:${m.color}"></span>
          <span>${m.name}</span>
          <span class="chip-axis-badge">${m.axis === 'left' ? 'Y1 Left' : 'Y2 Right'}</span>
          <button class="chip-remove-btn" data-index="${idx}" title="Remove metric">&times;</button>
        </div>
      `;
    });
    container.innerHTML = html;

    container.querySelectorAll('.chip-remove-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const idx = parseInt(btn.getAttribute('data-index'), 10);
        activePlotterMetrics.splice(idx, 1);
        renderPlotterChips();
        renderPlotterChart();
      });
    });
  }

  function renderPlotterChart() {
    const canvas = document.getElementById('crossPlotterCanvas');
    if (!canvas || typeof Chart === 'undefined') return;

    const data = tickerCacheData[currentTicker];
    if (!data) return;

    const inc = normalizeStatementRows(data.income);
    const bal = normalizeStatementRows(data.balance_sheet);
    const cf = normalizeStatementRows(data.cashflow);
    const allRows = inc.concat(bal).concat(cf);

    // Collect dates
    const dateSet = new Set();
    allRows.forEach(r => Object.keys(r.values).forEach(d => dateSet.add(d)));
    const sortedDates = Array.from(dateSet).sort(); // chronological left to right
    const labels = sortedDates.map(d => d.split(' ')[0].split('-')[0]);

    const datasets = [];
    activePlotterMetrics.forEach(m => {
      const row = allRows.find(r => r.name === m.name);
      if (!row) return;

      const series = sortedDates.map(d => {
        const val = row.values[d];
        return (val !== null && val !== undefined && !isNaN(val)) ? Number(val) : null;
      });

      datasets.push({
        label: m.name,
        data: series,
        yAxisID: m.axis === 'right' ? 'y2' : 'y1',
        type: plotterChartType,
        borderColor: m.color,
        backgroundColor: m.color.replace(')', ', 0.15)').replace('rgb', 'rgba').replace('#', 'rgba(') + (m.color.startsWith('#') ? '26' : ''),
        fill: plotterChartType === 'line',
        tension: 0.25,
        borderWidth: 2.5,
        pointRadius: 4,
        pointHoverRadius: 6,
      });
    });

    if (crossPlotterChart) {
      crossPlotterChart.destroy();
    }

    const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const gridColor = isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.06)';
    const textColor = isDark ? '#e0e6ed' : '#1f2328';

    const hasRightAxis = activePlotterMetrics.some(m => m.axis === 'right');

    crossPlotterChart = new Chart(canvas, {
      data: {
        labels: labels,
        datasets: datasets,
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: {
            display: true,
            labels: { color: textColor, font: { weight: 600 } },
          },
          tooltip: {
            callbacks: {
              label: (ctx) => `${ctx.dataset.label}: ${formatNumber(ctx.raw, true)}`,
            },
          },
        },
        scales: {
          x: {
            grid: { color: gridColor },
            ticks: { color: textColor },
          },
          y1: {
            type: 'linear',
            position: 'left',
            grid: { color: gridColor },
            ticks: {
              color: textColor,
              callback: (val) => formatNumber(val, true),
            },
          },
          y2: {
            type: 'linear',
            position: 'right',
            display: hasRightAxis,
            grid: { drawOnChartArea: false },
            ticks: {
              color: textColor,
              callback: (val) => formatNumber(val, true),
            },
          },
        },
      },
    });
  }

  // --- TECHNICAL ANALYSIS PANEL ---
  function populateTechnicals(data) {
    const pData = data.price_data || {};
    const info = data.info || {};

    const cur = pData.current_price != null ? Number(pData.current_price) : null;
    const high = pData.price_52w_high != null ? Number(pData.price_52w_high) : null;
    const low = pData.price_52w_low != null ? Number(pData.price_52w_low) : null;
    const trend = pData.price_trend_30d != null ? Number(pData.price_trend_30d) : null;
    const vol = pData.avg_volume != null ? Number(pData.avg_volume) : null;
    const mktCap = info.marketCap != null ? Number(info.marketCap) : null;

    // 52W Gauge
    if (cur !== null && high !== null && low !== null && high > low) {
      document.getElementById('gaugeLowVal').textContent = '$' + low.toFixed(2);
      document.getElementById('gaugeCurVal').textContent = '$' + cur.toFixed(2);
      document.getElementById('gaugeHighVal').textContent = '$' + high.toFixed(2);

      const pct = Math.max(0, Math.min(100, ((cur - low) / (high - low)) * 100));
      const fillBar = document.getElementById('gaugeFillBar');
      const thumb = document.getElementById('gaugeThumb');
      if (fillBar) fillBar.style.width = pct + '%';
      if (thumb) thumb.style.left = pct + '%';

      document.getElementById('gaugeMetaText').textContent =
        `${pct.toFixed(1)}% of 52-week range (Low: $${low.toFixed(2)} - High: $${high.toFixed(2)})`;
    }

    // Stats Grid
    if (cur !== null) document.getElementById('statCurPrice').textContent = '$' + cur.toFixed(2);
    if (trend !== null) {
      const el = document.getElementById('statTrend30d');
      el.textContent = `${trend >= 0 ? '+' : ''}${trend.toFixed(2)}%`;
      el.style.color = trend >= 0 ? '#3fb950' : '#f85149';
    }
    if (vol !== null) document.getElementById('statAvgVol').textContent = formatNumber(vol, true);
    if (mktCap !== null) document.getElementById('statMktCap').textContent = formatNumber(mktCap, true);
    document.getElementById('statSector').textContent = info.sector || '--';
    document.getElementById('statIndustry').textContent = info.industry || '--';

    // Benchmarks from catalog or details
    const catalogItem = (stocksCatalog || []).find(s => s.ticker === currentTicker);
    const entryPrice = catalogItem ? catalogItem.entry_price : null;
    const breakPrice = catalogItem ? catalogItem.thesis_break_price : null;

    if (entryPrice != null) {
      document.getElementById('bmEntryVal').textContent = '$' + Number(entryPrice).toFixed(2);
      const isAct = cur !== null && cur <= Number(entryPrice);
      const statusEl = document.getElementById('bmEntryStatus');
      statusEl.innerHTML = isAct
        ? '<span style="color:#3fb950;font-weight:700;">🟢 Actionable: Current price is below entry target</span>'
        : '<span style="opacity:0.8;">⏳ Waiting: Price is above recommended entry</span>';
    }

    if (breakPrice != null) {
      document.getElementById('bmBreakVal').textContent = '$' + Number(breakPrice).toFixed(2);
      const statusEl = document.getElementById('bmBreakStatus');
      if (cur !== null && Number(breakPrice) > 0) {
        const buffer = ((cur - Number(breakPrice)) / cur) * 100;
        statusEl.innerHTML = `<span>Thesis-break buffer: <strong>${buffer.toFixed(1)}%</strong> downside</span>`;
      }
    }
  }

  function loadTradingView(symbol) {
    const container = document.getElementById('tradingview_chart_embed');
    const symbolLbl = document.getElementById('tvSymbolLabel');
    if (!container) return;

    let tvSymbol = symbol;
    if (symbol.endsWith('.MC')) tvSymbol = 'BME:' + symbol.replace('.MC', '');
    else if (symbol.endsWith('.T')) tvSymbol = 'TSE:' + symbol.replace('.T', '');
    else if (symbol.endsWith('.TO')) tvSymbol = 'TSX:' + symbol.replace('.TO', '');
    else if (symbol.endsWith('.V')) tvSymbol = 'TSXV:' + symbol.replace('.V', '');

    if (symbolLbl) symbolLbl.textContent = tvSymbol;

    const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const theme = isDark ? 'dark' : 'light';

    container.innerHTML = '';

    if (typeof TradingView !== 'undefined' && TradingView.widget) {
      new TradingView.widget({
        autosize: true,
        symbol: tvSymbol,
        interval: 'D',
        timezone: 'exchange',
        theme: theme,
        style: '1',
        locale: 'en',
        toolbar_bg: isDark ? '#161b22' : '#f6f8fa',
        enable_publishing: false,
        hide_top_toolbar: false,
        allow_symbol_change: true,
        container_id: 'tradingview_chart_embed',
      });
    } else {
      const iframe = document.createElement('iframe');
      iframe.src = `https://s.tradingview.com/widgetembed/?symbol=${encodeURIComponent(tvSymbol)}&interval=D&theme=${theme}&style=1`;
      iframe.style.width = '100%';
      iframe.style.height = '100%';
      iframe.style.border = 'none';
      container.appendChild(iframe);
    }
  }

  // --- VALUATION MODELS PANEL ---
  function populateValuation(data) {
    const catalogItem = (stocksCatalog || []).find(s => s.ticker === currentTicker) || {};

    const verdict = catalogItem.verdict || 'NONE';
    const conviction = catalogItem.conviction || '';
    const evPct = catalogItem.expected_value_pct;
    const targetPrice = catalogItem.target_price || catalogItem.fair_value;
    const entryPrice = catalogItem.entry_price;

    const vBadge = document.getElementById('valVerdictBadge');
    if (vBadge) {
      vBadge.textContent = verdict;
      vBadge.className = `val-metric-val verdict-badge-large verdict-${verdict}`;
    }

    const convSub = document.getElementById('valConvictionSub');
    if (convSub) convSub.textContent = conviction ? `Conviction: ${conviction}` : '--';

    const evEl = document.getElementById('valEvPct');
    if (evEl) {
      if (evPct != null) {
        const ev = Number(evPct);
        evEl.textContent = `${ev >= 0 ? '+' : ''}${ev.toFixed(1)}%`;
        evEl.style.color = ev >= 0 ? '#3fb950' : '#f85149';
      } else {
        evEl.textContent = '--';
      }
    }

    const tpEl = document.getElementById('valTargetPrice');
    if (tpEl) tpEl.textContent = targetPrice != null ? '$' + Number(targetPrice).toFixed(2) : '--';

    const epEl = document.getElementById('valEntryPrice');
    if (epEl) epEl.textContent = entryPrice != null ? '$' + Number(entryPrice).toFixed(2) : '--';

    // Scenarios
    const scenarios = catalogItem.scenarios || {};
    const scContainer = document.getElementById('valScenarioBars');
    if (scContainer) {
      if (typeof scenarios === 'object' && Object.keys(scenarios).length) {
        let scHtml = '';
        Object.keys(scenarios).forEach(name => {
          const sc = scenarios[name];
          const prob = sc.prob || sc.probability || '';
          const ret = sc.return || sc.upside || '';
          const target = sc.target || sc.price || '';
          const isBull = name.toLowerCase().includes('bull');
          const isBear = name.toLowerCase().includes('bear');
          const col = isBull ? '#3fb950' : (isBear ? '#f85149' : '#58a6ff');

          scHtml += `
            <div class="scenario-bar-row">
              <div class="scenario-bar-name">${name.toUpperCase()} (${prob})</div>
              <div class="scenario-bar-track-wrap">
                <div class="scenario-bar-fill" style="width: 100%; background: ${col};">
                  Target: ${target} (${ret})
                </div>
              </div>
              <div class="scenario-bar-meta">${ret}</div>
            </div>
          `;
        });
        scContainer.innerHTML = scHtml;
      } else {
        scContainer.innerHTML = '<div class="empty-hint">No scenario models breakdown available.</div>';
      }
    }

    // Valuations Table
    const vTableWrap = document.getElementById('valTableWrap');
    const valuations = catalogItem.valuations || {};
    if (vTableWrap) {
      if (typeof valuations === 'object' && Object.keys(valuations).length) {
        let tHtml = '<table><thead><tr><th>Model</th><th>Fair Value</th><th>Margin / Upside</th><th>Confidence</th></tr></thead><tbody>';
        Object.keys(valuations).forEach(mName => {
          const m = valuations[mName];
          if (typeof m !== 'object' || m === null) return;
          const fv = m.fair_value != null ? '$' + Number(m.fair_value).toFixed(2) : '--';
          const margin = m.margin_of_safety != null ? (Number(m.margin_of_safety) * 100).toFixed(1) + '%' : (m.upside || '--');
          const conf = m.confidence || '--';
          tHtml += `<tr><td><strong>${mName}</strong></td><td>${fv}</td><td>${margin}</td><td>${conf}</td></tr>`;
        });
        tHtml += '</tbody></table>';
        vTableWrap.innerHTML = tHtml;
      } else {
        vTableWrap.innerHTML = '<div class="empty-hint">No multi-model valuations recorded in catalog.</div>';
      }
    }
  }

  function htmlEscape(str) {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // --- FAST TOOLTIPS (1/3rd native hover delay ~220ms) ---
  function initFastTooltips(delayMs = 220) {
    let tooltipEl = document.getElementById('fast-tooltip-card');
    if (!tooltipEl) {
      tooltipEl = document.createElement('div');
      tooltipEl.id = 'fast-tooltip-card';
      tooltipEl.className = 'fast-tooltip-card';
      document.body.appendChild(tooltipEl);
    }

    let hoverTimer = null;
    let activeTarget = null;
    let isVisible = false;

    function show(target, text, x, y) {
      if (!text || !text.trim()) return;

      if (text.includes(' | ')) {
        const parts = text.split(' | ');
        tooltipEl.innerHTML = parts.map((p, idx) => {
          if (idx === 0 && !p.includes(':')) {
            return `<div class="ft-line ft-title">${htmlEscape(p.trim())}</div>`;
          }
          return `<div class="ft-line">${htmlEscape(p.trim())}</div>`;
        }).join('');
      } else {
        tooltipEl.textContent = text;
      }

      tooltipEl.style.display = 'block';
      const rect = tooltipEl.getBoundingClientRect();
      const pad = 12;
      let left = x + 12;
      let top = y + 16;

      if (left + rect.width > window.innerWidth - pad) {
        left = Math.max(pad, window.innerWidth - rect.width - pad);
      }
      if (top + rect.height > window.innerHeight - pad) {
        top = Math.max(pad, y - rect.height - 8);
      }

      tooltipEl.style.left = left + 'px';
      tooltipEl.style.top = top + 'px';
      tooltipEl.classList.add('visible');
      isVisible = true;
    }

    function hide() {
      clearTimeout(hoverTimer);
      hoverTimer = null;
      activeTarget = null;
      isVisible = false;
      if (tooltipEl) {
        tooltipEl.classList.remove('visible');
        tooltipEl.style.display = 'none';
      }
    }

    document.addEventListener('mouseover', function(e) {
      const el = e.target.closest('[title], [data-tooltip]');
      if (!el) return;

      if (el.hasAttribute('title') && el.getAttribute('title')) {
        el.setAttribute('data-tooltip', el.getAttribute('title'));
        el.removeAttribute('title');
      }

      const text = el.getAttribute('data-tooltip');
      if (!text) return;

      if (activeTarget === el) return;
      activeTarget = el;

      clearTimeout(hoverTimer);
      const currentDelay = isVisible ? 70 : delayMs;
      hoverTimer = setTimeout(() => {
        if (activeTarget === el) {
          show(el, text, e.clientX, e.clientY);
        }
      }, currentDelay);
    }, true);

    document.addEventListener('mouseout', function(e) {
      const el = e.target.closest('[data-tooltip]');
      if (el && el === activeTarget) {
        if (e.relatedTarget && el.contains(e.relatedTarget)) return;
        hide();
      }
    }, true);

    window.addEventListener('scroll', hide, true);
    window.addEventListener('click', hide, true);
  }

  // --- IN-PAGE MARKDOWN TABLES ENHANCER (TIKR & SCENARIOS) ---
  function initMarkdownTables(container) {
    if (!container || typeof Chart === 'undefined') return;

    function parseValue(text) {
      if (!text) return null;
      const clean = text.replace(/<[^>]+>/g, '').trim();
      const m = clean.match(/([+-]?)\\s*[$€¥£]?\\s*([0-9]+(?:,[0-9]+)*(?:\\.[0-9]+)?)\\s*([BMK%xX]?)/i);
      if (!m) return null;
      const sign = m[1] === '-' ? -1 : 1;
      const val = parseFloat(m[2].replace(/,/g, '')) * sign;
      const suffix = (m[3] || '').toUpperCase();
      const isPercent = clean.includes('%');
      const isMultiple = clean.toLowerCase().includes('x');
      const isCurrency = /[$€¥£]/.test(clean);
      return { val, suffix, raw: clean, isPercent, isMultiple, isCurrency };
    }

    const TIKR_PALETTE = [
      { border: '#0969da', bg: 'rgba(9, 105, 218, 0.18)', darkBorder: '#58a6ff', darkBg: 'rgba(88, 166, 255, 0.18)' },
      { border: '#2da44e', bg: 'rgba(45, 164, 78, 0.18)', darkBorder: '#3fb950', darkBg: 'rgba(63, 185, 80, 0.18)' },
      { border: '#8250df', bg: 'rgba(130, 80, 223, 0.18)', darkBorder: '#bc8cff', darkBg: 'rgba(188, 140, 255, 0.18)' },
      { border: '#d97706', bg: 'rgba(217, 119, 6, 0.18)', darkBorder: '#f59e0b', darkBg: 'rgba(245, 158, 11, 0.18)' },
      { border: '#cf222e', bg: 'rgba(207, 34, 46, 0.18)', darkBorder: '#f85149', darkBg: 'rgba(248, 81, 73, 0.18)' }
    ];

    function isDarkTheme() {
      return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    }

    function initTikrTable(table) {
      if (table.getAttribute('data-tikr-initialized')) return;
      const ths = Array.from(table.querySelectorAll('th'));
      if (!ths.length) return;

      const timeColIndices = [];
      const timeLabels = [];

      ths.forEach((th, idx) => {
        if (idx === 0) return;
        const text = th.innerText.trim();
        const isCAGR = /cagr|growth|change|comment/i.test(text);
        const hasTime = /\\b(19\\d\\d|20\\d\\d|Q[1-4]|H[1-2]|FY\\d\\d|LTM|TTM)\\b/i.test(text);
        if (hasTime && !isCAGR) {
          timeColIndices.push(idx);
          let clean = text.replace(/\\(.*?\\)/g, '').trim();
          timeLabels.push(clean || text);
        }
      });

      if (timeColIndices.length < 2) return;

      const trs = Array.from(table.querySelectorAll('tr')).filter(tr => tr.querySelectorAll('td').length > 0);
      const parsedRows = [];

      trs.forEach(tr => {
        const tds = Array.from(tr.querySelectorAll('td'));
        if (tds.length <= Math.max(...timeColIndices)) return;

        const metricName = tds[0].innerText.trim();
        if (!metricName) return;

        const values = timeColIndices.map(colIdx => parseValue(tds[colIdx].innerText));
        const nonNull = values.filter(v => v !== null);
        if (nonNull.length < 2) return;

        let summary = null;
        if (tds.length > Math.max(...timeColIndices) + 1) {
          const lastText = tds[tds.length - 1].innerText.trim();
          if (/cagr|%|trend/i.test(lastText)) summary = lastText;
        }

        tr.classList.add('tikr-clickable-row');
        const dot = document.createElement('span');
        dot.className = 'tikr-row-dot';
        tds[0].insertBefore(dot, tds[0].firstChild);

        parsedRows.push({ tr, metricName, values, summary });
      });

      if (!parsedRows.length) return;
      table.setAttribute('data-tikr-initialized', 'true');

      const widget = document.createElement('div');
      widget.className = 'tikr-chart-widget';
      widget.innerHTML = `
        <div class="tikr-chart-header">
          <div class="tikr-title-group">
            <div class="tikr-metric-name">
              <span class="active-title">Metric Chart</span>
              <div class="tikr-meta-badges">
                <span class="tikr-badge tikr-badge-val latest-badge" style="display:none;"></span>
                <span class="tikr-badge tikr-badge-growth growth-badge" style="display:none;"></span>
              </div>
            </div>
          </div>
          <div class="tikr-controls">
            <button class="tikr-toggle-btn btn-compare">➕ Compare</button>
            <div class="tikr-btn-group">
              <button class="tikr-btn btn-area active">Area</button>
              <button class="tikr-btn btn-bar">Bar</button>
            </div>
          </div>
        </div>
        <div class="tikr-pills-row">
          <span class="tikr-pill-label">Quick:</span>
          ${parsedRows.slice(0, 6).map(r => `<button class="tikr-pill" data-metric="${htmlEscape(r.metricName)}">${htmlEscape(r.metricName.split('(')[0].trim())}</button>`).join('')}
        </div>
        <div class="tikr-canvas-container">
          <canvas></canvas>
        </div>
        <div class="tikr-footer-hint">
          <span>💡 Click any table row to chart it. Click <strong>Compare</strong> to overlay multiple metrics.</span>
          <span class="point-count-label"></span>
        </div>
      `;

      table.parentNode.insertBefore(widget, table);

      const canvas = widget.querySelector('canvas');
      let chartType = 'line';
      let compareMode = false;
      let selectedRows = [parsedRows[0]];
      let chartInstance = null;

      function renderChart() {
        updateBadges();
        updateTableHighlight();

        const dark = isDarkTheme();
        const gridColor = dark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.06)';
        const textColor = dark ? '#e0e6ed' : '#1f2328';

        const datasets = selectedRows.map((row, idx) => {
          const pal = TIKR_PALETTE[idx % TIKR_PALETTE.length];
          const color = dark ? pal.darkBorder : pal.border;
          const bg = dark ? pal.darkBg : pal.bg;
          const dataVals = row.values.map(v => (v ? v.val : null));

          return {
            label: row.metricName,
            data: dataVals,
            type: chartType,
            borderColor: color,
            backgroundColor: chartType === 'line' ? bg : color,
            fill: chartType === 'line',
            tension: 0.25,
            borderWidth: 2.5,
            pointRadius: 4,
            pointHoverRadius: 6,
          };
        });

        if (chartInstance) chartInstance.destroy();

        chartInstance = new Chart(canvas, {
          data: { labels: timeLabels, datasets },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
              legend: { display: selectedRows.length > 1, labels: { color: textColor } },
              tooltip: {
                callbacks: {
                  label: (ctx) => `${ctx.dataset.label}: ${ctx.raw !== null ? ctx.raw.toLocaleString() : '--'}`,
                },
              },
            },
            scales: {
              x: { grid: { color: gridColor }, ticks: { color: textColor } },
              y: { grid: { color: gridColor }, ticks: { color: textColor } },
            },
          },
        });
      }

      function updateBadges() {
        const titleEl = widget.querySelector('.active-title');
        const latestBadge = widget.querySelector('.latest-badge');
        const growthBadge = widget.querySelector('.growth-badge');
        const countLabel = widget.querySelector('.point-count-label');

        if (selectedRows.length === 1) {
          const row = selectedRows[0];
          titleEl.textContent = row.metricName;
          const validVals = row.values.filter(v => v !== null);
          const latest = validVals.length ? validVals[validVals.length - 1] : null;
          latestBadge.textContent = latest ? 'Latest: ' + latest.raw : '';
          latestBadge.style.display = latest ? 'inline-flex' : 'none';

          if (row.summary) {
            growthBadge.textContent = row.summary;
            growthBadge.className = 'tikr-badge ' + (row.summary.includes('-') ? 'tikr-badge-neg' : 'tikr-badge-growth');
            growthBadge.style.display = 'inline-flex';
          } else {
            growthBadge.style.display = 'none';
          }
        } else {
          titleEl.textContent = 'Comparing ' + selectedRows.length + ' Metrics';
          latestBadge.textContent = selectedRows.map(r => r.metricName.split('(')[0].trim()).join(' vs ');
          latestBadge.style.display = 'inline-flex';
          growthBadge.style.display = 'none';
        }

        countLabel.textContent = timeLabels.length + ' periods (' + timeLabels[0] + ' – ' + timeLabels[timeLabels.length - 1] + ')';
      }

      function updateTableHighlight() {
        parsedRows.forEach(r => {
          const isSel = selectedRows.includes(r);
          r.tr.classList.toggle('active-row', isSel);
        });

        widget.querySelectorAll('.tikr-pill').forEach(pill => {
          const match = selectedRows.some(r => r.metricName.toLowerCase().startsWith(pill.textContent.toLowerCase()));
          pill.classList.toggle('active', match);
        });
      }

      parsedRows.forEach(r => {
        r.tr.addEventListener('click', (e) => {
          if (compareMode || e.shiftKey || e.metaKey || e.ctrlKey) {
            const idx = selectedRows.indexOf(r);
            if (idx >= 0 && selectedRows.length > 1) selectedRows.splice(idx, 1);
            else if (idx < 0) {
              if (selectedRows.length >= 5) selectedRows.shift();
              selectedRows.push(r);
            }
          } else {
            selectedRows = [r];
          }
          renderChart();
        });
      });

      widget.querySelectorAll('.tikr-pill').forEach(pill => {
        pill.addEventListener('click', () => {
          const name = pill.getAttribute('data-metric');
          const target = parsedRows.find(r => r.metricName === name);
          if (target) {
            selectedRows = [target];
            renderChart();
          }
        });
      });

      const btnArea = widget.querySelector('.btn-area');
      const btnBar = widget.querySelector('.btn-bar');
      const btnCompare = widget.querySelector('.btn-compare');

      btnArea.addEventListener('click', () => {
        chartType = 'line';
        btnArea.classList.add('active');
        btnBar.classList.remove('active');
        renderChart();
      });

      btnBar.addEventListener('click', () => {
        chartType = 'bar';
        btnBar.classList.add('active');
        btnArea.classList.remove('active');
        renderChart();
      });

      btnCompare.addEventListener('click', () => {
        compareMode = !compareMode;
        btnCompare.classList.toggle('active', compareMode);
        btnCompare.textContent = compareMode ? '✓ Compare (ON)' : '➕ Compare';
      });

      renderChart();
    }

    function initScenarioChart(table) {
      if (table.getAttribute('data-scenario-initialized')) return;
      const ths = Array.from(table.querySelectorAll('th')).map(th => th.innerText.toLowerCase());
      const isScenario = ths.some(h => h.includes('scenario')) && ths.some(h => h.includes('target') || h.includes('return'));
      if (!isScenario) return;

      const trs = Array.from(table.querySelectorAll('tr')).filter(tr => tr.querySelectorAll('td').length > 0);
      const targetIdx = ths.findIndex(h => h.includes('target'));
      const returnIdx = ths.findIndex(h => h.includes('return'));
      const probIdx = ths.findIndex(h => h.includes('prob'));

      const scenarios = [];
      trs.forEach(tr => {
        const tds = Array.from(tr.querySelectorAll('td'));
        if (!tds.length) return;
        const name = tds[0].innerText.trim();
        const target = targetIdx >= 0 && tds[targetIdx] ? tds[targetIdx].innerText.trim() : '';
        const ret = returnIdx >= 0 && tds[returnIdx] ? tds[returnIdx].innerText.trim() : '';
        const prob = probIdx >= 0 && tds[probIdx] ? tds[probIdx].innerText.trim() : '';
        scenarios.push({ name, target, ret, prob });
      });

      if (!scenarios.length) return;
      table.setAttribute('data-scenario-initialized', 'true');

      const widget = document.createElement('div');
      widget.className = 'scenario-chart-widget';
      widget.innerHTML = `
        <div class="scenario-chart-title">Scenario Target Returns</div>
        <div class="scenario-chart-sub">Probability-weighted outlook across defined scenarios</div>
        <div class="scenario-bar-list">
          ${scenarios.map(s => {
            const isBull = s.name.toLowerCase().includes('bull');
            const isBear = s.name.toLowerCase().includes('bear');
            const col = isBull ? '#3fb950' : (isBear ? '#f85149' : '#58a6ff');
            return `
              <div class="scenario-bar-row">
                <div class="scenario-bar-name">${htmlEscape(s.name)} ${s.prob ? `(${htmlEscape(s.prob)})` : ''}</div>
                <div class="scenario-bar-track-wrap">
                  <div class="scenario-bar-fill" style="width: 100%; background: ${col};">
                    ${htmlEscape(s.target)} (${htmlEscape(s.ret)})
                  </div>
                </div>
                <div class="scenario-bar-meta" style="color:${col};">${htmlEscape(s.ret)}</div>
              </div>
            `;
          }).join('')}
        </div>
      `;

      table.parentNode.insertBefore(widget, table);
    }

    const tables = container.querySelectorAll('table');
    tables.forEach(table => {
      initScenarioChart(table);
      initTikrTable(table);
    });
  }

})();
"""
