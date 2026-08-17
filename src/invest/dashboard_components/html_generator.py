"""
HTMLGenerator - Generates dashboard HTML templates and content.

This component is responsible for:
- Generating complete HTML dashboard templates
- Formatting stock data for display
- Creating progress indicators and status displays
- Providing responsive and interactive UI elements
"""

import html
import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


class HTMLGenerator:
    """Generates HTML content for the investment dashboard."""

    def __init__(self, output_dir: str = "dashboard"):
        """Initialize the HTML generator."""
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.html_file = self.output_dir / "valuation_dashboard.html"

    def generate_dashboard_html(self, stocks_data: Dict, progress_data: Dict, metadata: Dict = None) -> str:
        """
        Generate complete HTML dashboard.

        Parameters
        ----------
        stocks_data : Dict
            Dictionary of stock data keyed by ticker
        progress_data : Dict
            Progress tracking information
        metadata : Dict, optional
            Additional metadata for the dashboard

        Returns
        -------
        str
            Complete HTML content
        """
        last_updated = metadata.get("last_updated", "Never") if metadata else "Never"
        server_mode = metadata.get("server_mode", False) if metadata else False

        # Generate main content sections
        summary_html = self._generate_summary_section(stocks_data)
        table_html = self._generate_stock_table(stocks_data)
        health_html = self._generate_health_panel(metadata) if server_mode else ""
        health_json = json.dumps(metadata.get("health", {}), default=str) if metadata else "{}"
        update_status_json = json.dumps(metadata.get("update_status", {}), default=str) if metadata else "{}"

        # Create complete HTML document
        html_content = f"""<!-- Start server: uv run python scripts/dashboard_server.py -->
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Investment Valuation Dashboard</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&family=Geist+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        {self._get_css_styles()}
    </style>
</head>
<body>
    <div class="container">
        <header class="dashboard-header">
            <h1>Investment Valuation Dashboard</h1>
            <div class="header-row">
                <div class="last-updated">Page rendered: <span id="lastUpdated">{last_updated}</span></div>
                <div class="header-actions">
                    <a id="liveServerLink" href="/" class="btn btn-update" style="{'display:none' if server_mode else ''}">Live Server</a>
                    <a href="/feed" class="btn btn-docs">Feed</a>
                    <a href="https://rubenayla.github.io/invest/models/" target="_blank" rel="noopener noreferrer" class="btn btn-docs">Model Docs</a>
                    <button onclick="exportToCSV()" class="btn btn-export">Export CSV</button>
                    <button onclick="openReminderModal()" class="btn btn-update">Reminders</button>
                </div>
            </div>
        </header>

        <!-- Notification Bar -->
        <div id="notificationBar" class="notification-bar" style="display:none;">
          <div class="notification-bar-header">
            <span class="notification-bar-title">&#128276; Notifications</span>
            <button onclick="dismissAllNotifications()" class="btn" style="padding:2px 10px; font-size:12px;">Clear all</button>
          </div>
          <div id="notificationList" class="notification-list"></div>
        </div>

        {health_html}

        <div class="controls">
            <div class="controls-left">
                <div class="universe-selector">
                    <label for="universe">Universe:</label>
                    <select id="universe">
                        <option value="all_universes">All Universes Combined</option>
                        <option value="nyse">NYSE</option>
                        <option value="sp500" selected>S&P 500</option>
                        <option value="russell2000">Russell 2000</option>
                        <option value="global_mix">Global Mix</option>
                        <option value="small_cap_focus">Small Cap</option>
                        <option value="japan_major">Japan Major</option>
                        <option value="uk_ftse">UK FTSE 100</option>
                        <option value="custom">Custom Tickers</option>
                    </select>
                    <input type="text" id="customTickers" placeholder="AAPL,MSFT,GOOGL..." style="display:none;">
                </div>
            </div>
            <div class="controls-right">
                <div id="updateStatus" class="update-status"></div>
                <button id="updateButton" onclick="triggerUpdate()" class="btn btn-update" title="Full refresh: prices, financials, statements, insider trades, activist stakes, institutional holdings. Data only — ML models run locally on Mac.">Update Data</button>
                <button id="liteUpdateButton" onclick="triggerUpdate(true)" class="btn btn-lite-update" title="Fast refresh: prices &amp; key metrics only. Preserves existing financial statements.">Lite Update</button>
                <button id="cancelButton" onclick="cancelUpdate()" class="btn btn-cancel" style="display:none;">Cancel</button>
            </div>
        </div>

        <div id="updateLog" class="update-log" style="display:none;">
            <div class="update-log-header">
                <span id="updatePhase">Starting...</span>
                <button onclick="toggleLog()" class="btn-toggle-log">Toggle Log</button>
            </div>
            <pre id="updateLogContent" class="update-log-content"></pre>
        </div>

        {summary_html}

        <div class="stock-analysis">
            <h2>Stock Analysis Results</h2>
            {table_html}
        </div>

    </div>

    <!-- Alarm Modal -->
    <div id="alarmModal" class="modal-overlay" style="display:none;" onclick="if(event.target===this)closeAlarmModal()">
      <div class="modal-content">
        <h3>Price Alarm: <span id="alarmTicker"></span></h3>
        <p class="modal-price">Current price: <span id="alarmCurrentPrice"></span></p>
        <div class="modal-form">
          <select id="alarmCondition">
            <option value="below">Below</option>
            <option value="above">Above</option>
          </select>
          <input type="number" id="alarmTargetPrice" step="0.01" placeholder="Target price">
          <button onclick="createAlarm()" class="btn btn-update">Set Alarm</button>
        </div>
        <div id="alarmList" class="alarm-list"></div>
        <button onclick="closeAlarmModal()" class="btn" style="margin-top:12px;">Close</button>
      </div>
    </div>

    <!-- Insider Chart Modal -->
    <div id="insiderModal" class="modal-overlay" style="display:none;" onclick="if(event.target===this)closeInsiderModal()">
      <div class="modal-content" style="min-width:520px; max-width:620px;">
        <h3 style="margin:0 0 4px;">Insider Activity: <span id="insiderModalTicker"></span></h3>
        <p id="insiderModalSubtitle" style="color:#738091; font-size:13px; margin:0 0 12px; font-family:Geist Mono,monospace;"></p>
        <div id="insiderChartContainer" style="width:100%; overflow-x:auto;"></div>
        <button onclick="closeInsiderModal()" class="btn" style="margin-top:16px;">Close</button>
      </div>
    </div>

    <!-- Reminder Modal -->
    <div id="reminderModal" class="modal-overlay" style="display:none;" onclick="if(event.target===this)closeReminderModal()">
      <div class="modal-content" style="min-width:420px; max-width:520px;">
        <h3>Reminders</h3>
        <div class="modal-form" style="flex-direction:column; gap:10px;">
          <input type="text" id="reminderTicker" placeholder="Ticker (optional)" style="width:120px;">
          <textarea id="reminderMessage" placeholder="Reminder message..." rows="2" style="width:100%; background:var(--bg-card,#161b22); color:var(--text-primary,#e0e6ed); border:1px solid var(--border,#2a3040); border-radius:4px; padding:8px; font-family:inherit; font-size:14px; resize:vertical;"></textarea>
          <div style="display:flex; gap:10px; align-items:center;">
            <input type="date" id="reminderDueDate" style="flex:1;">
            <button onclick="createReminder()" class="btn btn-update">Add Reminder</button>
          </div>
        </div>
        <div id="reminderList" style="margin-top:16px; max-height:300px; overflow-y:auto;"></div>
        <button onclick="closeReminderModal()" class="btn" style="margin-top:12px;">Close</button>
      </div>
    </div>

    <!-- Toast container for alarm notifications -->
    <div id="toastContainer" class="toast-container"></div>

    <!-- Alarm panel toggle (fixed button) -->
    <button id="alarmPanelToggle" class="alarm-panel-toggle" onclick="toggleAlarmPanel()" title="View all alarms" style="display:none;">&#128276; <span id="activeAlarmCount">0</span></button>

    <!-- Alarm list sidebar -->
    <div id="alarmPanel" class="alarm-panel" style="display:none;">
      <div class="alarm-panel-header">
        <h3>Price Alarms</h3>
        <button onclick="toggleAlarmPanel()" class="btn" style="padding:4px 10px;">X</button>
      </div>
      <div id="alarmPanelList" class="alarm-panel-list"></div>
    </div>

    <script>
        const SERVER_MODE = {'true' if server_mode else 'false'};
        const INITIAL_HEALTH = {health_json};
        const INITIAL_UPDATE_STATUS = {update_status_json};
        {self._get_javascript()}
    </script>
</body>
</html>"""

        return html_content

    def _generate_progress_section(self, progress_data: Dict) -> str:
        """Generate the progress section HTML."""
        status = progress_data.get("status", "idle")
        completed = progress_data.get("completed_tasks", 0)
        total = progress_data.get("total_tasks", 0)
        completion_pct = progress_data.get("completion_percentage", 0)
        current_ticker = progress_data.get("current_ticker", "")
        current_model = progress_data.get("current_model", "")

        if status == "idle":
            return '''
            <div class="progress-section" style="display: none;" id="progressSection">
                <div class="progress-bar">
                    <div class="progress-fill" style="width: 0%"></div>
                </div>
                <div class="progress-text">Ready to update</div>
            </div>'''

        progress_text = f"{completed}/{total} tasks ({completion_pct:.1f}%)"
        if current_ticker and current_model:
            progress_text += f" • Current: {current_ticker} {current_model}"

        return f'''
        <div class="progress-section" id="progressSection">
            <div class="progress-bar">
                <div class="progress-fill" style="width: {completion_pct}%"></div>
            </div>
            <div class="progress-text" id="progressText">{progress_text}</div>
        </div>'''

    def _generate_health_panel(self, metadata: Dict) -> str:
        """Generate the database health status panel."""
        health = metadata.get("health", {})
        if not health or not health.get("ok"):
            return '<div class="health-panel health-error">Database not found or inaccessible</div>'

        stock_data = health.get("stock_data", {})
        models = health.get("models", {})
        sec = health.get("sec_data", {})
        db_size = health.get("db_size_mb", 0)

        # Models staleness
        max_model_age = 0
        display_models = [
            "autoresearch", "gbm_opportunistic_1y", "gbm_opportunistic_3y",
            "gbm_1y", "gbm_3y", "dcf", "rim",
        ]
        for m in display_models:
            info = models.get(m, {})
            age = info.get("age_hours")
            if age is not None and age > max_model_age:
                max_model_age = age

        # Raw data (yfinance prices/fundamentals) staleness
        # Use p80 age (80th percentile) for prices to ignore stale scanner outliers
        price_age = stock_data.get("p80_age_hours") or stock_data.get("age_hours") or 0
        stale_count = stock_data.get("stale_count", 0)

        def _staleness(age_hours: float, source: str, stale_outliers: int = 0) -> tuple[str, str]:
            """Return (css_class, label) for a freshness indicator."""
            if age_hours > 168:
                return "stale-critical", f"Most {source} over {age_hours / 24:.0f}d old"
            if age_hours > 48:
                return "stale-warning", f"Some {source} up to {age_hours / 24:.0f}d old"
            if age_hours > 24:
                return "stale-mild", f"{source.capitalize()} up to {age_hours:.0f}h old"
            if stale_outliers:
                return "stale-fresh", f"{source.capitalize()} fresh ({stale_outliers} stale outliers)"
            return "stale-fresh", f"{source.capitalize()} fresh"

        overall_cls, overall_label = _staleness(max_model_age, "models")
        raw_cls, raw_label = _staleness(price_age, "raw data", stale_count)

        # Build model chips
        model_chips = []
        for m in display_models:
            info = models.get(m, {})
            age_h = info.get("age_hours")
            ok = info.get("successful", 0)
            fail = info.get("failed", 0)
            label = m.replace("_", " ").replace("gbm ", "GBM ").replace("autoresearch", "AutoRes")
            if age_h is None:
                chip_cls = "chip-missing"
                age_str = "no data"
            elif age_h > 168:
                chip_cls = "chip-critical"
                age_str = f"{age_h / 24:.0f}d"
            elif age_h > 48:
                chip_cls = "chip-warning"
                age_str = f"{age_h / 24:.0f}d"
            else:
                chip_cls = "chip-ok"
                age_str = f"{age_h:.0f}h" if age_h >= 1 else "<1h"
            fail_str = f" | {fail} err" if fail else ""
            model_chips.append(
                f'<span class="health-chip {chip_cls}" title="{m}: {ok} ok, {fail} failed, age {age_str}">'
                f'{label} <small>{age_str}{fail_str}</small></span>'
            )

        # SEC chips
        sec_chips = []
        for name, info in sec.items():
            if info.get("exists"):
                age_h = info.get("age_hours", 0)
                rows = info.get("rows", 0)
                if age_h > 168:
                    chip_cls = "chip-critical"
                elif age_h > 48:
                    chip_cls = "chip-warning"
                else:
                    chip_cls = "chip-ok"
                age_str = f"{age_h / 24:.0f}d" if age_h > 24 else f"{age_h:.0f}h"
                sec_chips.append(
                    f'<span class="health-chip {chip_cls}" title="{name}: {rows} rows, {age_str} old">'
                    f'{name.title()} <small>{age_str}</small></span>'
                )
            else:
                sec_chips.append(f'<span class="health-chip chip-missing">{name.title()} <small>missing</small></span>')

        stock_count = stock_data.get("count", 0)

        return f'''
        <div class="health-panel" id="healthPanel">
            <div class="health-header">
                <div class="health-overall-group">
                    <div class="health-overall {overall_cls}" title="Age of newest result among displayed valuation models">
                        <span class="health-dot"></span>
                        {overall_label}
                    </div>
                    <div class="health-overall {raw_cls}" title="Age of yfinance raw data (p80 of stock_data.timestamp)">
                        <span class="health-dot"></span>
                        {raw_label}
                    </div>
                </div>
                <div class="health-meta">
                    {stock_count} stocks | {db_size} MB
                </div>
            </div>
            <div class="health-details" id="healthDetails">
                <div class="health-row">
                    <span class="health-label">Models</span>
                    <div class="health-chips">{''.join(model_chips)}</div>
                </div>
                <div class="health-row">
                    <span class="health-label">SEC Data</span>
                    <div class="health-chips">{''.join(sec_chips)}</div>
                </div>
                <div class="health-row" style="margin-top:6px; font-size:0.82em; color:#738091;">
                    Update buttons fetch data only. To refresh ML models, run on Mac:
                    <code style="background:#161b22; padding:1px 5px; border-radius:3px; font-size:0.95em;">ssh -N hetzner-db & uv run python scripts/update_all.py --skip-fetch</code>
                </div>
            </div>
        </div>'''

    def _generate_summary_section(self, stocks_data: Dict) -> str:
        """Generate the analysis summary section."""
        total_stocks = len(stocks_data)

        # Count stocks that have at least one successful valuation
        analyzed_stocks = 0
        for s in stocks_data.values():
            for v in s.get("valuations", {}).values():
                if isinstance(v, dict) and v.get("fair_value"):
                    analyzed_stocks += 1
                    break

        # Count only dashboard-visible models
        display_models = [
            "autoresearch", "gbm_opportunistic_1y", "gbm_opportunistic_3y",
            "gbm_1y", "gbm_3y", "dcf", "rim",
        ]
        model_counts = {}
        for stock in stocks_data.values():
            for model in stock.get("valuations", {}):
                if model in display_models:
                    v = stock["valuations"][model]
                    if isinstance(v, dict) and v.get("fair_value"):
                        model_counts[model] = model_counts.get(model, 0) + 1

        summary_items = []
        summary_items.append(f"<div class='summary-item'><strong>{total_stocks}</strong><br>Total Stocks</div>")
        summary_items.append(f"<div class='summary-item'><strong>{analyzed_stocks}</strong><br>Analyzed</div>")

        name_map = {
            "autoresearch": "AutoRes", "gbm_opportunistic_1y": "GBM Opp 1y",
            "gbm_opportunistic_3y": "GBM Opp 3y", "gbm_1y": "GBM 1y",
            "gbm_3y": "GBM 3y", "dcf": "DCF", "rim": "RIM",
        }
        for model in display_models:
            count = model_counts.get(model, 0)
            model_name = name_map.get(model, model)
            summary_items.append(f"<div class='summary-item'><strong>{count}</strong><br>{model_name}</div>")

        return f'''
        <div class="analysis-summary">
            <h2>📊 Analysis Summary</h2>
            <div class="summary-grid">
                {''.join(summary_items)}
            </div>
        </div>'''

    def _generate_stock_table(self, stocks_data: Dict) -> str:
        """Generate the stock analysis table."""
        if not stocks_data:
            return '<p class="no-data">No stock data available. Click "Update Data" to start analysis.</p>'

        # Sort stocks by status and performance
        sorted_stocks = self._sort_stocks_for_display(stocks_data)

        # Generate table rows
        table_rows = []
        for ticker, stock_data in sorted_stocks:
            row_html = self._generate_stock_row(ticker, stock_data)
            table_rows.append(row_html)

        return f'''
        <div class="table-search-bar" style="display:flex; align-items:center; gap:8px; padding:6px 4px;">
            <input type="text" id="tableSearch" placeholder="Filter rows: ticker, company, signals, sector..." oninput="filterTableRows()" style="flex:1; max-width:520px; padding:6px 10px; background:var(--bg-base); color:var(--text-primary); border:1px solid var(--border-subtle); border-radius:4px; font-family:Geist Mono,monospace; font-size:13px;" />
            <span id="tableSearchCount" style="color:var(--text-muted); font-size:12px; font-family:Geist Mono,monospace;"></span>
        </div>
        <div class="table-container">
            <table class="stock-table results-table" id="stockTable">
                <thead>
                    <tr>
                        <th title="Rank in current sort order">#</th>
                        <th title="Stock ticker symbol">Stock</th>
                        <th title="Current market price per share">Price</th>
                        <th title="Analysis completion status">Status</th>
                        <th title="AutoResearch - 5-model ensemble peak 2y return prediction (Spearman 0.54)">AutoRes</th>
                        <th class="sort-asc" title="LLM Deep Analysis - AI research verdict with news, variant perception, and scenario analysis. Default sort: BUY &gt; WATCH &gt; PASS, then price at/below entry, then EV vs bear-case loss weighted by conviction">LLM</th>
                        <th title="Signals: insider buys/sells, activist stakes, institutional holders">Signals</th>
                        <th title="Opportunistic GBM 1-year - Peak return prediction within 2 years">GBM Opp 1y</th>
                        <th title="Opportunistic GBM 3-year - Peak return prediction within 3 years">GBM Opp 3y</th>
                        <th title="Gradient Boosted Machine 1-year return prediction">GBM 1y</th>
                        <th title="Gradient Boosted Machine 3-year return prediction">GBM 3y</th>
                        <th title="Discounted Cash Flow - Values future cash flows discounted to present value">DCF</th>
                        <th title="Residual Income Model - Values excess returns above cost of equity based on book value">RIM</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(table_rows)}
                </tbody>
            </table>
        </div>'''

    def _generate_stock_row(self, ticker: str, stock_data: Dict) -> str:
        """Generate a single stock table row."""
        current_price = stock_data.get("current_price", 0)
        
        currency_code = stock_data.get("currency", "USD")
        symbols = {'EUR': '€', 'USD': '$', 'GBP': '£', 'JPY': '¥', 'CHF': 'Fr.', 'CAD': 'CA$', 'AUD': 'A$'}
        self.current_currency_sym = symbols.get(currency_code, '$')
        
        valuations = stock_data.get("valuations", {})
        fetch_ts = stock_data.get("fetch_timestamp", "")
        from datetime import datetime, timezone

        def _format_age(ts_value):
            if not ts_value:
                return 'never', '#e76a6e'
            try:
                ts = ts_value if isinstance(ts_value, datetime) else datetime.fromisoformat(str(ts_value))
                age_h = (datetime.now(timezone.utc) - ts.replace(tzinfo=timezone.utc)).total_seconds() / 3600
                if age_h < 24:
                    label = f'{age_h:.0f}h ago'
                elif age_h < 720:
                    label = f'{age_h / 24:.0f}d ago'
                else:
                    label = f'{age_h / 720:.0f}mo ago'
                color = '#e76a6e' if age_h > 168 else '#738091'  # Red if >7 days
                return label, color
            except Exception:
                return '?', '#738091'

        updated_str, updated_color = _format_age(fetch_ts)

        # Latest model timestamp across all valuations
        model_ts_latest = None
        for v in valuations.values():
            if not isinstance(v, dict):
                continue
            t = v.get('timestamp')
            if not t:
                continue
            try:
                t_dt = t if isinstance(t, datetime) else datetime.fromisoformat(str(t))
            except (ValueError, TypeError):
                continue
            if model_ts_latest is None or t_dt > model_ts_latest:
                model_ts_latest = t_dt
        models_str, models_color = _format_age(model_ts_latest)
        company_name = html.escape(stock_data.get("company_name", ticker))

        # Create meaningful status based on what actually worked
        working_models = []
        failed_models = []

        model_names = {
            "autoresearch": "AutoRes",
            "gbm_opportunistic_1y": "GBM-Opp1y",
            "gbm_opportunistic_3y": "GBM-Opp3y",
            "gbm_1y": "GBM1y",
            "gbm_3y": "GBM3y",
            "dcf": "DCF",
            "rim": "RIM",
            "llm_deep_analysis": "LLM",
        }

        for model_key, result in valuations.items():
            # Skip non-dict values like current_price
            if not isinstance(result, dict):
                continue
            model_name = model_names.get(model_key, model_key.upper())
            if result and result.get("fair_value"):
                working_models.append(model_name)
            else:
                failed_models.append(model_name)

        # Create better status
        if working_models:
            if len(working_models) >= 3:
                new_status = "completed"
                new_message = f"✅ Working: {', '.join(working_models[:3])}{'...' if len(working_models) > 3 else ''}"
            else:
                new_status = "partial"
                new_message = f"⚠️ Working: {', '.join(working_models)} | Failed: {', '.join(failed_models[:2])}"
        else:
            new_status = "failed"
            new_message = f"❌ All models failed or unsuitable for {ticker}"

        # Format status
        status_html = self._format_status_cell(new_status, new_message)

        # Format valuation columns
        autoresearch_html = self._format_valuation_cell(valuations.get("autoresearch", {}), current_price, show_confidence=True)
        gbm_opp_1y_html = self._format_valuation_cell(valuations.get("gbm_opportunistic_1y", {}), current_price, show_confidence=True)
        gbm_opp_3y_html = self._format_valuation_cell(valuations.get("gbm_opportunistic_3y", {}), current_price, show_confidence=True)
        gbm_1y_html = self._format_valuation_cell(valuations.get("gbm_1y", {}), current_price, show_confidence=True)
        gbm_3y_html = self._format_valuation_cell(valuations.get("gbm_3y", {}), current_price, show_confidence=True)
        dcf_html = self._format_valuation_cell(valuations.get("dcf", {}), current_price)
        rim_html = self._format_valuation_cell(valuations.get("rim", {}), current_price)
        llm_html = self._format_llm_cell(valuations.get("llm_deep_analysis", {}), current_price, ticker)

        # Format combined signals column
        signals_html = self._format_signals_cell(
            stock_data.get("insider", {}),
            stock_data.get("activist", {}),
            stock_data.get("japan_stakes", {}),
            stock_data.get("holdings", {}),
            ticker,
            politician=stock_data.get("politician", {}),
        )


        return f'''
        <tr class="stock-row {new_status}">
            <td class="rank-cell"></td>
            <td class="ticker-cell"><span class="ticker-trigger" data-ticker="{ticker}" data-price="{current_price or 0}" onclick="toggleKebab(event, this)" title="{company_name}">{ticker} &#8942;</span><a class="notes-link" href="/api/notes/{ticker}" onclick="openNotes('{ticker}'); return false;">&#128196; Notes</a><div class="kebab-menu"><div class="kebab-label">{company_name}</div><div class="kebab-label" style="color:{updated_color}; padding-top:0;">Data: {updated_str}</div><div class="kebab-label" style="color:{models_color}; padding-top:0;">Models: {models_str}</div><div class="kebab-sep"></div><a class="kebab-item" href="#" onclick="openNotes('{ticker}'); return false;">&#128196; Analysis notes</a><div class="kebab-item" onclick="openAlarmModal('{ticker}', {current_price or 0}); closeAllKebabs();">&#128276; Price alarm</div><a class="kebab-item" href="https://finance.yahoo.com/quote/{ticker}" target="_blank" rel="noopener">&#128200; Yahoo Finance</a></div></td>
            <td>{self._safe_format(current_price, prefix="$")}</td>
            <td>{status_html}</td>
            <td>{autoresearch_html}</td>
            <td>{llm_html}</td>
            <td>{signals_html}</td>
            <td>{gbm_opp_1y_html}</td>
            <td>{gbm_opp_3y_html}</td>
            <td>{gbm_1y_html}</td>
            <td>{gbm_3y_html}</td>
            <td>{dcf_html}</td>
            <td>{rim_html}</td>
        </tr>'''

    def _format_status_cell(self, status: str, message: str) -> str:
        """Format the status cell with icon and tooltip."""
        status_icons = {
            "completed": "✅",
            "partial": "⚠️",
            "failed": "❌",
            "analyzing": "🔄",
            "pending": "⏳",
            "data_missing": "❌",
            "rate_limited": "🚫",
            "model_failed": "⚠️",
        }

        icon = status_icons.get(status, "❓")

        # Custom display names for better readability
        display_names = {
            "completed": "Complete",
            "partial": "Partial",
            "failed": "Failed",
            "analyzing": "Running",
            "pending": "Pending"
        }

        display_name = display_names.get(status, status.replace("_", " ").title())

        return f'<span title="{html.escape(message)}">{icon} {display_name}</span>'

    def _format_valuation_cell(self, valuation: Dict, current_price: float = None, show_confidence: bool = False) -> str:
        """Format a valuation cell with fair value, margin, and ratio."""
        if valuation.get("failed", False):
            reason = valuation.get("failure_reason", "Model failed")
            reason = reason[:30] + "..." if len(reason) > 30 else reason
            return f'<span title="{html.escape(reason)}">❌</span>'

        fair_value = valuation.get("fair_value")
        margin = valuation.get("margin_of_safety")

        if fair_value is None or fair_value == 0:
            # Show error message in tooltip if available
            error_msg = valuation.get("error_message") or valuation.get("error", "No valuation available")
            return f'<span title="{html.escape(str(error_msg))}">-</span>'

        fair_value_str = self._safe_format(fair_value, prefix="$")
        margin_str = self._safe_percent(margin)

        # Calculate ratio if current price is available
        ratio_str = ""
        if current_price and current_price > 0:
            ratio = fair_value / current_price
            ratio_str = f'<div class="ratio">{ratio:.2f}x</div>'

        # Color code the margin
        margin_class = self._get_margin_class(margin)

        confidence_badge = ''
        if show_confidence:
            conf = valuation.get('confidence')
            conf_value = None
            if isinstance(conf, (int, float)):
                conf_value = conf
            elif isinstance(conf, str):
                conf_lower = conf.lower()
                mapping = {'high': 0.9, 'medium': 0.5, 'low': 0.2}
                conf_value = mapping.get(conf_lower, None)
            if conf_value is None:
                details = valuation.get('details', {})
                percentile = details.get('ranking_percentile')
                if isinstance(percentile, (int, float)):
                    percentile = percentile / 100 if percentile > 1 else percentile
                    conf_value = max(percentile, 1 - percentile)
            if conf_value is not None:
                conf_value = min(max(conf_value, 0.0), 1.0)
                conf_label = f'{conf_value * 100:.1f}%'
                # color: high green, medium yellow, low red
                if conf_value >= 0.75:
                    conf_style = 'background: rgba(50,164,103,0.15); color: #72ca9b'
                elif conf_value >= 0.4:
                    conf_style = 'background: rgba(209,152,11,0.15); color: #f0b726'
                else:
                    conf_style = 'background: rgba(205,66,70,0.12); color: #e76a6e'
                confidence_badge = f'<div class="confidence-badge" style="{conf_style}; font-size: 12px; padding: 3px 7px; border-radius: 3px; margin-top: 2px; font-weight: 500; font-family: Geist Mono, monospace;">{conf_label}</div>'

        age_badge = self._format_age_badge(valuation.get('timestamp'))

        return f'''
        <div class="valuation-cell">
            <div class="fair-value">{fair_value_str}</div>
            <div class="margin {margin_class}">{margin_str}</div>
            {ratio_str}
            {confidence_badge}
            {age_badge}
        </div>'''

    def _format_age_badge(self, timestamp_str) -> str:
        """Format a small age badge showing how old a model prediction is."""
        if not timestamp_str:
            return ''
        try:
            if isinstance(timestamp_str, str):
                ts = datetime.fromisoformat(timestamp_str)
            else:
                ts = timestamp_str
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            age_hours = (now - ts).total_seconds() / 3600
            if age_hours < 24:
                label = f'{int(age_hours)}h'
            else:
                label = f'{int(age_hours / 24)}d'
            if age_hours > 168:  # > 7 days
                style = 'color: #e76a6e'
            elif age_hours > 72:  # > 3 days
                style = 'color: #f0b726'
            else:
                style = 'color: #6b7280'
            return f'<div style="{style}; font-size: 10px; margin-top: 1px; font-family: Geist Mono, monospace;" title="Model ran {label} ago">{label}</div>'
        except (ValueError, TypeError):
            return ''

    @staticmethod
    def llm_entry_actionable(valuation: Dict, current_price: float = None):
        """True when the current price is at or below the LLM entry price,
        False when above it, None when either number is missing."""
        details = (valuation or {}).get("details", {}) or {}
        try:
            entry = float(details.get("entry_price"))
            price = float(current_price)
        except (TypeError, ValueError):
            return None
        if entry <= 0 or price <= 0:
            return None
        return price <= entry

    @staticmethod
    def llm_risk_adjusted_score(valuation: Dict, current_price: float = None):
        """Sort key for the LLM column (higher = better idea to act on now).

        verdict tier (BUY 100 / WATCH 0 / PASS -100)
        + 50 if the price is at or below the entry price (a BUY that already ran
          past its entry is a wait, not a buy)
        + reward/risk: EV% / |bear-case loss%| (bear clamped to at least 10% so a
          near-zero bear case cannot dominate; ratio capped at 10) x conviction weight.
        Returns None when there is no LLM analysis.
        """
        if not valuation or not valuation.get("fair_value"):
            return None
        details = valuation.get("details", {}) or {}
        verdict = details.get("verdict", "?")
        ev_pct = details.get("expected_value_pct", 0) or 0
        conviction = details.get("conviction", "?")
        scenarios = details.get("scenarios", {}) or {}
        bear_return = None
        for name, s in scenarios.items():
            if isinstance(s, dict) and 'bear' in name.lower():
                bear_return = s.get('return_pct')
        conviction_weight = {"HIGH": 1.9, "MEDIUM-HIGH": 1.6, "MEDIUM": 1.3, "LOW": 1.0}.get(
            str(conviction).upper(), 1.3
        )
        if bear_return is not None and bear_return < 0:
            raw_score = min(ev_pct / max(abs(bear_return), 10.0), 10.0) * conviction_weight
        else:
            raw_score = ev_pct * conviction_weight / 100 if ev_pct else 0
        verdict_tier = {"BUY": 100, "WATCH": 0, "PASS": -100}.get(verdict, -50)
        actionable_bonus = 50 if HTMLGenerator.llm_entry_actionable(valuation, current_price) else 0
        return verdict_tier + actionable_bonus + raw_score

    def _format_llm_cell(self, valuation: Dict, current_price: float = None, ticker: str = "") -> str:
        """Format LLM deep analysis cell showing verdict, EV%, and entry price. Clickable to open analysis notes."""
        if not valuation or not valuation.get("fair_value"):
            return '<span title="No LLM analysis available">-</span>'

        details = valuation.get("details", {})
        verdict = details.get("verdict", "?")
        ev_pct = details.get("expected_value_pct", 0)
        entry_price = details.get("entry_price", "?")
        quality = details.get("quality_score", "?")
        conviction = details.get("conviction", "?")
        variant = details.get("variant_perception", "")
        scenarios = details.get("scenarios", {})

        # Build tooltip
        tooltip_parts = [f"Conviction: {conviction}"]
        tooltip_parts.append(f"Quality: {quality}/25")
        tooltip_parts.append(f"Entry: ${entry_price}")
        if variant:
            tooltip_parts.append(f"Edge: {variant[:80]}")
        for name, s in scenarios.items():
            if isinstance(s, dict):
                tooltip_parts.append(f"{name.title()}: {s.get('prob', 0):.0%} → {s.get('return_pct', 0):+.0f}%")
        tooltip = " | ".join(tooltip_parts)

        # Verdict badge color
        if verdict == "BUY":
            badge_bg = "rgba(50,164,103,0.2)"
            badge_color = "#72ca9b"
        elif verdict == "PASS":
            badge_bg = "rgba(205,66,70,0.15)"
            badge_color = "#e76a6e"
        else:  # WATCH
            badge_bg = "rgba(209,152,11,0.15)"
            badge_color = "#f0b726"

        # EV% color
        ev_class = "margin-excellent" if ev_pct > 15 else "margin-good" if ev_pct > 5 else "margin-neutral" if ev_pct > -5 else "margin-poor"

        risk_adj_score = self.llm_risk_adjusted_score(valuation, current_price)
        actionable = self.llm_entry_actionable(valuation, current_price)
        if actionable is True:
            entry_note = ' <span style="color:#72ca9b;" title="Price at or below entry">&#10003;</span>'
        elif actionable is False:
            entry_note = ' <span style="color:#738091;" title="Price above entry">&#8593;</span>'
        else:
            entry_note = ''

        return f'''
        <a href="#" onclick="openNotes('{ticker}'); return false;" rel="noopener" style="text-decoration:none; display:block;" title="{html.escape(tooltip)}">
        <div class="valuation-cell" data-sort-value="{risk_adj_score:.4f}" style="cursor:pointer;">
            <div style="background:{badge_bg}; color:{badge_color}; font-weight:700; font-size:13px; padding:2px 8px; border-radius:3px; display:inline-block; font-family:var(--font-mono);">{verdict}</div>
            <div class="margin {ev_class}" style="margin-top:3px;">{ev_pct:+.0f}%</div>
            <div class="ratio">entry ${entry_price}{entry_note}</div>
            {self._format_age_badge(valuation.get('timestamp'))}
        </div>
        </a>'''

    def _format_nn_cell(self, valuation: Dict, current_price: float = None) -> str:
        """Format neural network valuation cell with confidence indicator."""
        if not valuation or not valuation.get('suitable'):
            reason = valuation.get('error', 'No prediction') if valuation else 'No data'
            reason = reason[:30] + '...' if len(reason) > 30 else reason
            return f'<span title="{html.escape(reason)}">-</span>'

        fair_value = valuation.get('fair_value')
        margin = valuation.get('margin_of_safety')

        if fair_value is None or fair_value == 0:
            return '-'

        # Get details for tooltip
        details = valuation.get('details', {})
        conf_std = details.get('confidence_std', 0)
        conf_lower = details.get('confidence_lower_95', 0)
        conf_upper = details.get('confidence_upper_95', 0)

        fair_value_str = self._safe_format(fair_value, prefix='$')
        margin_str = self._safe_percent(margin)

        # Confidence badge - show std as percentage instead of categorical label
        # Color based on std thresholds: <5% = green, <15% = yellow, >=15% = red
        if conf_std < 0.05:
            conf_style = 'background: rgba(50,164,103,0.15); color: #72ca9b'
        elif conf_std < 0.15:
            conf_style = 'background: rgba(209,152,11,0.15); color: #f0b726'
        else:
            conf_style = 'background: rgba(205,66,70,0.12); color: #e76a6e'

        conf_label = f'σ={conf_std:.1%}'  # Show actual std percentage

        # Tooltip with detailed confidence info
        tooltip = f'Uncertainty (Std): {conf_std:.1%} | 95% CI: [{conf_lower:.1f}%, {conf_upper:.1f}%]'

        # Calculate ratio if current price is available
        ratio_str = ''
        if current_price and current_price > 0:
            ratio = fair_value / current_price
            ratio_str = f'<div class="ratio">{ratio:.2f}x</div>'

        # Color code the margin
        margin_class = self._get_margin_class(margin)

        return f'''
        <div class="valuation-cell" title="{tooltip}">
            <div class="fair-value">{fair_value_str}</div>
            <div class="margin {margin_class}">{margin_str}</div>
            {ratio_str}
            <div class="confidence-badge" style="{conf_style}; font-size: 12px; padding: 3px 7px; border-radius: 3px; margin-top: 2px; font-weight: 500; font-family: Geist Mono, monospace;">{conf_label}</div>
        </div>'''

    def _format_multi_horizon_cells(self, nn_valuation: Dict, current_price: float) -> Tuple[str, str, str, str, str]:
        """Format multi-horizon NN predictions into 5 separate cells (1m, 3m, 6m, 1y, 2y)."""
        if not nn_valuation or not nn_valuation.get('suitable'):
            empty = '-'
            return empty, empty, empty, empty, empty

        details = nn_valuation.get('details', {})
        predictions = details.get('predictions', {})
        fair_values = details.get('fair_values', {})
        confidence_scores = details.get('confidence_scores', {})

        horizons = [
            ('1m', '1-month'),
            ('3m', '3-month'),
            ('6m', '6-month'),
            ('1y', '1-year'),
            ('2y', '2-year')
        ]

        cells = []
        for horizon_key, horizon_label in horizons:
            prediction = predictions.get(horizon_key)
            fair_value = fair_values.get(horizon_key)
            confidence = confidence_scores.get(horizon_key, 0)

            if prediction is None or fair_value is None:
                cells.append('-')
                continue

            # Calculate margin of safety
            margin = (fair_value - current_price) / current_price if current_price > 0 else 0

            # Format values
            pred_str = f'{prediction:.2f}%'
            fv_str = self._safe_format(fair_value, prefix='$')
            margin_str = self._safe_percent(margin)
            conf_str = f'{confidence * 100:.1f}%'

            # Color code the margin
            margin_class = self._get_margin_class(margin)

            # Create tooltip with all details
            tooltip = f'{horizon_label}: Return {pred_str}, FV {fv_str}, Margin {margin_str}, Confidence {conf_str}'

            cells.append(f'''
            <div class="nn-cell" title="{tooltip}">
                <div class="prediction">{pred_str}</div>
                <div class="margin {margin_class}">{margin_str}</div>
            </div>''')

        return tuple(cells)

    def _format_consensus_cell(self, valuations: Dict, current_price: float) -> str:
        """Format the consensus cell with log-return weighted valuation."""
        from ..valuation.consensus import compute_consensus_from_dicts

        consensus = compute_consensus_from_dicts(valuations, current_price)
        if consensus is None:
            return "-"

        avg_fair_value = consensus.fair_value
        avg_margin = consensus.margin_of_safety
        avg_ratio = avg_fair_value / current_price if current_price > 0 else 0

        avg_fair_value_str = self._safe_format(avg_fair_value, prefix="$")
        avg_margin_str = self._safe_percent(avg_margin)
        avg_ratio_str = f"{avg_ratio:.2f}x" if avg_ratio > 0 else "-"
        margin_class = self._get_margin_class(avg_margin)

        # Confidence badge based on consensus confidence label
        conf_label = consensus.confidence
        if conf_label == 'high':
            conf_style = 'background: rgba(50,164,103,0.15); color: #72ca9b'
        elif conf_label == 'medium':
            conf_style = 'background: rgba(209,152,11,0.15); color: #f0b726'
        else:
            conf_style = 'background: rgba(205,66,70,0.12); color: #e76a6e'
        confidence_badge = f'<div class="confidence-badge" style="{conf_style}; font-size: 12px; padding: 3px 7px; border-radius: 3px; margin-top: 2px; font-weight: 500; font-family: Geist Mono, monospace;">{conf_label.title()}</div>'

        return f'''
        <div class="consensus-cell">
            <div class="fair-value"><strong>{avg_fair_value_str}</strong></div>
            <div class="margin {margin_class}"><strong>{avg_margin_str}</strong></div>
            <div class="ratio"><strong>{avg_ratio_str}</strong></div>
            {confidence_badge}
            <div class="model-count">({consensus.num_models} models)</div>
        </div>'''

    def _format_insider_cell(self, insider: Dict) -> str:
        """Format insider activity cell with trend indicators.

        Shows counts + trend vs historical baseline, e.g.:
        '3B/12S ↓40%' = 12 sells but 40% below normal (bullish)
        """
        if not insider or not insider.get('has_data'):
            return '<span style="color: #5f6b7c;">-</span>'

        buy_count = insider.get('buy_count', 0)
        sell_count = insider.get('sell_count', 0)
        dollars = insider.get('dollar_conviction', 0.0)
        sell_trend = insider.get('sell_trend')
        buy_trend = insider.get('buy_trend')

        parts = []
        if buy_count > 0:
            parts.append(f"{buy_count}B")
        if sell_count > 0:
            parts.append(f"{sell_count}S")

        activity = "/".join(parts) if parts else "-"

        # Dollar formatting
        if dollars >= 1_000_000:
            dollar_str = f"${dollars / 1_000_000:.1f}M"
        elif dollars >= 1_000:
            dollar_str = f"${dollars / 1_000:.0f}K"
        elif dollars > 0:
            dollar_str = f"${dollars:.0f}"
        else:
            dollar_str = ""

        # Trend annotation: show how current activity compares to historical norm
        trend_str = ""
        if sell_trend is not None and sell_count > 0:
            pct_change = int((sell_trend - 1.0) * 100)
            if pct_change <= -20:
                trend_str = f" S↓{abs(pct_change)}%"  # selling below normal (bullish)
            elif pct_change >= 20:
                trend_str = f" S↑{pct_change}%"  # selling above normal (bearish)
        if buy_trend is not None and buy_count > 0:
            pct_change = int((buy_trend - 1.0) * 100)
            if pct_change >= 50:
                trend_str += f" B↑{pct_change}%"  # buying above normal (bullish)
            elif pct_change <= -50:
                trend_str += f" B↓{abs(pct_change)}%"  # buying below normal (bearish)

        # Color logic: factor in sell trend
        # Low selling relative to normal is bullish even if sell_count > buy_count
        if buy_count > sell_count:
            color = "#34d399"
            bg = "rgba(50,164,103,0.15)"
        elif sell_count > buy_count:
            if sell_trend is not None and sell_trend < 0.7:
                # Selling well below normal — muted, not alarming
                color = "#a0aec0"
                bg = "rgba(160,174,192,0.10)"
            else:
                color = "#e76a6e"
                bg = "rgba(205,66,70,0.12)"
        else:
            color = "#738091"
            bg = "rgba(255,255,255,0.06)"

        text = f"{activity}"
        if dollar_str:
            text += f" {dollar_str}"
        if trend_str:
            text += trend_str

        return f'<span style="color: {color}; background: {bg}; padding: 1px 5px; border-radius: 2px; font-size: 13px; font-weight: 500; font-family: Geist Mono, monospace;">{text}</span>'

    def _format_activist_cell(self, activist: Dict, japan: Dict, ticker: str) -> str:
        """Format activist/passive stakes cell. Shows Japan stakes for .T tickers."""
        parts = []

        # SEC 13D/13G
        if activist and activist.get('has_data'):
            activist_count = activist.get('activist_count', 0)
            passive_count = activist.get('passive_count', 0)
            max_pct = activist.get('max_stake_pct')
            name = activist.get('recent_activist_name', '')

            if activist_count > 0:
                pct_str = f" {max_pct:.1f}%" if max_pct else ""
                name_str = f" ({name[:15]})" if name else ""
                parts.append(f"{activist_count}\u00d713D{name_str}{pct_str}")
            if passive_count > 0:
                parts.append(f"{passive_count}\u00d713G")

        # Japan large shareholding (for .T tickers)
        if japan and japan.get('has_data') and ticker.endswith('.T'):
            count = japan.get('holder_count', 0)
            max_pct = japan.get('max_stake_pct')
            name = japan.get('recent_holder_name', '')
            pct_str = f" {max_pct:.1f}%" if max_pct else ""
            name_str = f" ({name[:12]})" if name else ""
            parts.append(f"{count}JP{name_str}{pct_str}")

        if not parts:
            return '<span style="color: #5f6b7c;">\u2014</span>'

        text = " | ".join(parts)

        # Color: activist = amber (high signal), passive = blue
        has_activist = activist and activist.get('activist_count', 0) > 0
        if has_activist:
            color = "#f0b726"
            bg = "rgba(209,152,11,0.15)"
        else:
            color = "#8abbff"
            bg = "rgba(76,144,240,0.12)"

        return f'<span style="color: {color}; background: {bg}; padding: 1px 5px; border-radius: 2px; font-size: 13px; font-weight: 500; font-family: Geist Mono, monospace;">{text}</span>'

    def _format_smart_money_cell(self, holdings: Dict) -> str:
        """Format smart money institutional holdings cell."""
        if not holdings or not holdings.get('has_data'):
            return '<span style="color: #5f6b7c;">\u2014</span>'

        holders_count = holdings.get('smart_money_holders', 0)
        value = holdings.get('total_smart_money_value_usd', 0)
        new_positions = holdings.get('new_positions', [])
        notable = holdings.get('notable_holders', [])

        parts = []

        # Show notable holder names (abbreviated)
        if notable:
            abbrevs = []
            for name in notable[:3]:
                # Abbreviate to first word or initials
                words = name.split()
                if len(words) == 1:
                    abbrevs.append(words[0][:3].upper())
                else:
                    abbrevs.append("".join(w[0] for w in words[:3]).upper())
            parts.append(", ".join(abbrevs))

        # New positions
        if new_positions:
            parts.append(f"+{len(new_positions)} new")

        # Value
        if value >= 1_000_000_000:
            parts.append(f"${value / 1_000_000_000:.1f}B")
        elif value >= 1_000_000:
            parts.append(f"${value / 1_000_000:.0f}M")

        if not parts:
            parts.append(f"{holders_count} funds")

        text = " ".join(parts)

        # Color based on holder count
        if holders_count >= 3:
            color = "#34d399"
            bg = "rgba(50,164,103,0.15)"
        elif holders_count >= 1:
            color = "#8abbff"
            bg = "rgba(76,144,240,0.12)"
        else:
            color = "#738091"
            bg = "rgba(255,255,255,0.06)"

        return f'<span style="color: {color}; background: {bg}; padding: 1px 5px; border-radius: 2px; font-size: 13px; font-weight: 500; font-family: Geist Mono, monospace;">{text}</span>'

    def _format_signals_cell(self, insider: Dict, activist: Dict, japan: Dict,
                              holdings: Dict, ticker: str,
                              politician: Dict | None = None) -> str:
        """Format combined signals cell with readable tags."""
        tags = []  # (color, label, clickable_ticker_or_None)

        # Insider buys/sells (clickable → opens chart)
        if insider and insider.get('has_data'):
            buy_count = insider.get('buy_count', 0)
            sell_count = insider.get('sell_count', 0)
            dollars = insider.get('dollar_conviction', 0.0)
            sell_trend = insider.get('sell_trend')

            if dollars >= 1_000_000:
                dollar_str = f" ${dollars / 1_000_000:.1f}M"
            elif dollars >= 1_000:
                dollar_str = f" ${dollars / 1_000:.0f}K"
            elif dollars > 0:
                dollar_str = f" ${dollars:.0f}"
            else:
                dollar_str = ""

            # Sell trend annotation
            trend_hint = ""
            if sell_trend is not None and sell_count > 0:
                pct = int((sell_trend - 1.0) * 100)
                if pct <= -20:
                    trend_hint = f" ({abs(pct)}% below avg)"
                elif pct >= 20:
                    trend_hint = f" ({pct}% above avg)"

            if buy_count > 0:
                label = f"{buy_count} insider buy{'s' if buy_count > 1 else ''}{dollar_str}"
                tags.append(('green', label, ticker))
            if sell_count > 0:
                label = f"{sell_count} insider sell{'s' if sell_count > 1 else ''}{trend_hint}"
                sell_color = 'grey' if (sell_trend is not None and sell_trend < 0.7) else 'red'
                tags.append((sell_color, label, ticker))

        # Activist stakes (13D = activist, 13G = passive)
        if activist and activist.get('has_data'):
            activist_count = activist.get('activist_count', 0)
            passive_count = activist.get('passive_count', 0)
            max_pct = activist.get('max_stake_pct')
            name = activist.get('recent_activist_name', '')

            if activist_count > 0:
                pct_str = f" {max_pct:.0f}%" if max_pct else ""
                name_str = f" {name[:15]}" if name else ""
                tags.append(('orange', f"activist stake{pct_str}{name_str}", None))
            if passive_count > 0:
                tags.append(('blue', f"{passive_count} passive stake{'s' if passive_count > 1 else ''}", None))

        # Japan large shareholding
        if japan and japan.get('has_data') and ticker.endswith('.T'):
            count = japan.get('holder_count', 0)
            name = japan.get('recent_holder_name', '')
            if count > 0:
                name_str = f" {name[:12]}" if name else ""
                tags.append(('blue', f"JP stake{name_str}", None))

        # Smart money
        if holdings and holdings.get('has_data'):
            notable = holdings.get('notable_holders', [])
            new_positions = holdings.get('new_positions', [])
            holders_count = holdings.get('smart_money_holders', 0)

            if new_positions:
                tags.append(('green', f"{len(new_positions)} new fund position{'s' if len(new_positions) > 1 else ''}", None))
            elif notable:
                names = ", ".join(n.split()[0][:10] for n in notable[:2])
                tags.append(('blue', f"held by {names}", None))
            elif holders_count > 0:
                tags.append(('blue', f"{holders_count} fund{'s' if holders_count > 1 else ''}", None))

        # Congressional/politician trades (House PTRs)
        if politician and politician.get('has_data'):
            from invest.signals.gates import (
                annualised_alpha,
                confidence_tier,
                evaluate,
            )
            buys = politician.get('buy_count', 0)
            sells = politician.get('sell_count', 0)
            score = politician.get('weighted_score', 0.0)
            top = politician.get('top_politicians', [])
            top_raw = ''
            top_name = ''
            if top:
                top_raw = top[0].get('name', '')
                last = top_raw.split(',')[0].strip() if ',' in top_raw else top_raw.split()[-1]
                top_name = f' · {last[:10]}'

            def _gate_annotation(direction: str) -> str:
                """Append ★/★★/★★★ + annualised α if (top politician, direction) gate-passes."""
                if not top_raw:
                    return ''
                g = evaluate('politician', top_raw, direction)
                if g is None or not g.passes:
                    return ''
                ann = annualised_alpha(g)
                sign = '+' if ann >= 0 else ''
                return f' {confidence_tier(g)} {sign}{ann * 100:.1f}%/yr'

            if buys > 0 and score > 0:
                tags.append((
                    'green',
                    f"{buys} congress buy{'s' if buys > 1 else ''}{top_name}{_gate_annotation('P')}",
                    None,
                ))
            if sells > 0 and score < 0:
                tags.append((
                    'red',
                    f"{sells} congress sell{'s' if sells > 1 else ''}{top_name}{_gate_annotation('S')}",
                    None,
                ))

        if not tags:
            return '<span style="color: #5f6b7c;">\u2014</span>'

        styles = {
            'green': 'color: #72ca9b; background: rgba(50,164,103,0.15);',
            'red': 'color: #f87171; background: rgba(205,66,70,0.12);',
            'grey': 'color: #a0aec0; background: rgba(160,174,192,0.10);',
            'orange': 'color: #fbbf24; background: rgba(209,152,11,0.15);',
            'blue': 'color: #60a5fa; background: rgba(76,144,240,0.12);',
        }

        html_parts = []
        for color, label, click_ticker in tags:
            style = styles.get(color, styles['blue'])
            click_attr = f' onclick="openInsiderChart(\'{click_ticker}\')" style="{style} padding: 1px 5px; border-radius: 2px; font-size: 12px; font-weight: 500; display: inline-block; margin: 2px 0; font-family: Geist Mono, monospace; cursor: pointer;"' if click_ticker else f' style="{style} padding: 1px 5px; border-radius: 2px; font-size: 12px; font-weight: 500; display: inline-block; margin: 2px 0; font-family: Geist Mono, monospace;"'
            html_parts.append(f'<span{click_attr}>{label}</span>')

        return "<br>".join(html_parts)

    def _sort_stocks_for_display(self, stocks_data: Dict) -> List[Tuple[str, Dict]]:
        """Default table order = the LLM column, the same order a click on that
        header gives: rows with an LLM verdict first, best risk-adjusted score
        first; rows without one after, by status and then best model margin."""
        def get_sort_key(stock_item):
            ticker, stock_data = stock_item
            status = stock_data.get("status", "pending")
            valuations = stock_data.get("valuations", {})
            llm_score = self.llm_risk_adjusted_score(
                valuations.get("llm_deep_analysis", {}), stock_data.get("current_price")
            )
            has_llm = 0 if llm_score is not None else 1

            # Status priority (lower = higher priority)
            status_priority = {
                "completed": 1,
                "analyzing": 2,
                "pending": 3,
                "data_missing": 4,
                "rate_limited": 5,
                "model_failed": 6,
            }.get(status, 7)

            # Best margin of safety for secondary sort
            margins = []
            for key, val in valuations.items():
                # Skip non-dict values like current_price
                if not isinstance(val, dict):
                    continue
                if not val.get("failed", False):
                    margin = val.get("margin_of_safety")
                    if margin is not None:
                        margins.append(margin)

            best_margin = max(margins) if margins else -999

            return (has_llm, -(llm_score or 0), status_priority, -best_margin)

        return sorted(stocks_data.items(), key=get_sort_key)

    def _get_margin_class(self, margin: float) -> str:
        """Get CSS class for margin color coding."""
        if margin is None:
            return ""
        elif margin > 0.3:
            return "margin-excellent"
        elif margin > 0.15:
            return "margin-good"
        elif margin > -0.15:
            return "margin-neutral"
        else:
            return "margin-poor"

    def _safe_format(self, value: Any, format_str: str = ".2f", placeholder: str = "-", prefix: str = "") -> str:
        """Safely format a numeric value."""
        cur_sym = getattr(self, 'current_currency_sym', '$')
        if prefix == "$":
            prefix = cur_sym
        try:
            if value is None:
                return placeholder
            formatted = f"{float(value):{format_str}}"
            return f"{prefix}{formatted}"
        except (ValueError, TypeError):
            return placeholder

    def _safe_percent(self, value: Any, placeholder: str = "-") -> str:
        """Safely format a percentage value."""
        try:
            if value is None:
                return placeholder
            return f"{float(value) * 100:+.1f}%"
        except (ValueError, TypeError):
            return placeholder

    def save_html(self, html_content: str):
        """Save HTML content to file."""
        try:
            with open(self.html_file, "w", encoding="utf-8") as f:
                f.write(html_content)
            logger.info(f"Dashboard HTML saved to {self.html_file}")
        except Exception as e:
            logger.error(f"Failed to save HTML: {e}")

    # ── Mobile Dashboard ────────────────────────────────────────────────

    def generate_mobile_html(self, stocks_data: Dict) -> str:
        """Generate a mobile-optimized card-based dashboard."""
        import json as _json

        # Prepare serializable stock data for embedding
        safe_data = {}
        for ticker, stock in stocks_data.items():
            entry = {
                'ticker': ticker,
                'company_name': stock.get('company_name', ticker),
                'sector': stock.get('sector', ''),
                'current_price': stock.get('current_price'),
                'valuations': {},
                'insider': stock.get('insider', {}),
            }
            for model, val in stock.get('valuations', {}).items():
                safe_val = {k: v for k, v in val.items() if k != 'details'}
                if 'details' in val and isinstance(val['details'], dict):
                    safe_val['details'] = val['details']
                entry['valuations'][model] = safe_val
            safe_data[ticker] = entry

        data_json = _json.dumps(safe_data, default=str)

        return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="theme-color" content="#111418">
<title>Invest</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600;9..40,700&family=Geist+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>{self._get_mobile_css()}</style>
</head>
<body>
<div id="pullIndicator">
  <svg class="pull-spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M12 2v6m0-6L9 5m3-3l3 3"/></svg>
  <span class="pull-text">Pull to refresh</span>
</div>

<header id="toolbar">
  <div class="toolbar-top">
    <h1 class="toolbar-title">Invest</h1>
    <div class="toolbar-meta">
      <span id="stockCount">0</span> stocks
      <span class="sep">&middot;</span>
      <span id="refreshAge">now</span>
    </div>
  </div>
  <div class="pill-row" id="sortRow">
    <button class="pill active" data-sort="autores">AutoRes</button>
    <button class="pill" data-sort="gbm">GBM 3y</button>
    <button class="pill" data-sort="ev">LLM Score</button>
    <button class="pill" data-sort="price">Price</button>
    <button class="pill" data-sort="az">A-Z</button>
  </div>
  <div class="pill-row" id="filterRow">
    <button class="pill filter active" data-filter="all">All</button>
    <button class="pill filter" data-filter="buy" style="--pill-accent:#72ca9b">BUY</button>
    <button class="pill filter" data-filter="watch" style="--pill-accent:#f0b726">WATCH</button>
    <button class="pill filter" data-filter="insider" style="--pill-accent:#ec9a3c">Insider</button>
  </div>
</header>

<main id="cardContainer"></main>

<div id="emptyState" style="display:none">
  <div class="empty-icon">&#x1f50d;</div>
  <div class="empty-text">No stocks match this filter</div>
</div>

<script>
const INITIAL_DATA = {data_json};
{self._get_mobile_javascript()}
</script>
</body>
</html>'''

    def _get_mobile_css(self) -> str:
        return """
:root {
    --bg-base: #111418;
    --bg-panel: #1c2127;
    --bg-elevated: #252a31;
    --bg-hover: #2f343c;
    --border: rgba(255,255,255,0.12);
    --border-subtle: rgba(255,255,255,0.06);
    --text-primary: #f6f7f9;
    --text-secondary: #abb3bf;
    --text-muted: #738091;
    --accent: #4c90f0;
    --accent-bright: #8abbff;
    --green: #32a467;
    --green-bright: #72ca9b;
    --green-dim: rgba(50,164,103,0.15);
    --red: #cd4246;
    --red-bright: #e76a6e;
    --red-dim: rgba(205,66,70,0.12);
    --gold: #d1980b;
    --gold-dim: rgba(209,152,11,0.15);
    --orange: #ec9a3c;
    --orange-dim: rgba(236,154,60,0.12);
    --font-body: 'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    --font-mono: 'Geist Mono', 'SF Mono', ui-monospace, monospace;
}

* { margin:0; padding:0; box-sizing:border-box; -webkit-tap-highlight-color:transparent; }

html {
    overscroll-behavior-y: contain;
}

body {
    font-family: var(--font-body);
    background: var(--bg-base);
    color: var(--text-primary);
    -webkit-font-smoothing: antialiased;
    min-height: 100dvh;
    padding-top: env(safe-area-inset-top);
}

/* ── Pull to refresh ── */
#pullIndicator {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 12px;
    color: var(--text-muted);
    font-size: 13px;
    font-family: var(--font-mono);
    transform: translateY(-100%);
    transition: transform 0.3s cubic-bezier(0.22, 1, 0.36, 1), opacity 0.3s;
    opacity: 0;
    z-index: 200;
    pointer-events: none;
}
#pullIndicator.visible { opacity: 1; }
#pullIndicator.refreshing .pull-spinner { animation: spin 0.8s linear infinite; }
#pullIndicator.refreshing .pull-text::after { content: '...'; }
.pull-spinner { width: 16px; height: 16px; transition: transform 0.2s; }
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Toolbar ── */
#toolbar {
    position: sticky;
    top: 0;
    z-index: 100;
    background: var(--bg-base);
    padding: 12px 16px 8px;
    border-bottom: 1px solid var(--border);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
}
.toolbar-top {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 10px;
}
.toolbar-title {
    font-size: 20px;
    font-weight: 700;
    letter-spacing: -0.02em;
    background: linear-gradient(135deg, var(--accent-bright), var(--accent));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}
.toolbar-meta {
    font-size: 12px;
    font-family: var(--font-mono);
    color: var(--text-muted);
}
.toolbar-meta .sep { margin: 0 4px; opacity: 0.4; }

/* ── Pills ── */
.pill-row {
    display: flex;
    gap: 6px;
    overflow-x: auto;
    scrollbar-width: none;
    -webkit-overflow-scrolling: touch;
    padding-bottom: 8px;
    margin: 0 -16px;
    padding-left: 16px;
    padding-right: 16px;
}
.pill-row::-webkit-scrollbar { display: none; }
.pill {
    flex-shrink: 0;
    padding: 5px 14px;
    border-radius: 20px;
    font-size: 13px;
    font-weight: 600;
    font-family: var(--font-body);
    background: var(--bg-elevated);
    color: var(--text-muted);
    border: 1px solid var(--border-subtle);
    cursor: pointer;
    transition: all 0.15s ease;
    white-space: nowrap;
}
.pill:active { transform: scale(0.95); }
.pill.active {
    background: var(--accent);
    color: #fff;
    border-color: var(--accent);
    box-shadow: 0 2px 12px rgba(76,144,240,0.25);
}
.pill.filter.active {
    background: var(--pill-accent, var(--accent));
    border-color: var(--pill-accent, var(--accent));
    box-shadow: 0 2px 12px rgba(76,144,240,0.2);
}

/* ── Cards ── */
#cardContainer {
    padding: 8px 12px 80px;
    display: flex;
    flex-direction: column;
    gap: 6px;
}

.stock-card {
    background: var(--bg-panel);
    border: 1px solid var(--border-subtle);
    border-radius: 10px;
    padding: 12px 14px;
    display: grid;
    grid-template-columns: 1fr auto;
    grid-template-rows: auto auto;
    gap: 4px 10px;
    cursor: pointer;
    transition: transform 0.12s ease, border-color 0.2s;
    will-change: transform;
}
.stock-card:active {
    transform: scale(0.985);
    border-color: var(--accent);
}

.card-left { grid-column: 1; grid-row: 1; min-width: 0; }
.card-right { grid-column: 2; grid-row: 1; text-align: right; display:flex; flex-direction:column; align-items:flex-end; gap:2px; }
.card-bottom { grid-column: 1 / -1; grid-row: 2; display: flex; flex-wrap: wrap; gap: 5px; align-items: center; margin-top: 2px; }

.card-ticker {
    font-family: var(--font-mono);
    font-weight: 700;
    font-size: 15px;
    letter-spacing: 0.02em;
    color: var(--text-primary);
}
.card-name {
    font-size: 12px;
    color: var(--text-muted);
    margin-left: 8px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 160px;
    display: inline-block;
    vertical-align: middle;
}
.card-price {
    font-family: var(--font-mono);
    font-weight: 600;
    font-size: 15px;
    color: var(--text-primary);
}

/* ── Tags & Badges ── */
.verdict-pill {
    display: inline-block;
    padding: 2px 9px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 700;
    font-family: var(--font-mono);
    letter-spacing: 0.04em;
}
.verdict-buy { background: var(--green-dim); color: var(--green-bright); }
.verdict-pass { background: var(--red-dim); color: var(--red-bright); }
.verdict-watch { background: var(--gold-dim); color: var(--gold); }

.metric-tag {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
    font-family: var(--font-mono);
}
.tag-upside-pos { background: var(--green-dim); color: var(--green-bright); }
.tag-upside-neg { background: var(--red-dim); color: var(--red-bright); }
.tag-ev-pos { background: rgba(76,144,240,0.12); color: var(--accent-bright); }
.tag-ev-neg { background: var(--red-dim); color: var(--red-bright); }
.tag-ev-neutral { background: var(--bg-elevated); color: var(--text-muted); }
.tag-insider-buy { background: var(--green-dim); color: var(--green-bright); }
.tag-insider-sell { background: var(--red-dim); color: var(--red-bright); }
.tag-insider-sell-normal { background: var(--bg-elevated); color: var(--text-muted); }
.tag-activist { background: var(--orange-dim); color: var(--orange); }
.tag-fund { background: rgba(76,144,240,0.10); color: var(--accent-bright); }

/* ── Empty state ── */
#emptyState {
    text-align: center;
    padding: 60px 20px;
    color: var(--text-muted);
}
.empty-icon { font-size: 40px; margin-bottom: 12px; opacity: 0.5; }
.empty-text { font-size: 15px; }

/* ── Animations ── */
@keyframes cardIn {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
}
.stock-card {
    animation: cardIn 0.25s ease both;
}
"""

    def _get_mobile_javascript(self) -> str:
        return """
let STOCKS = INITIAL_DATA;
let currentSort = 'autores';
let currentFilter = 'all';
let lastRefresh = Date.now();

// ── Trusted models only (matches Kelly sizer) ──
const TRUSTED_GBM = ['gbm_3y', 'gbm_opportunistic_3y'];

// ── Data helpers ──

function getLLM(s) { return s.valuations?.llm_deep_analysis?.details || null; }
function getVerdict(s) { const l = getLLM(s); return l?.verdict || null; }
function getEV(s) { const l = getLLM(s); return l?.expected_value_pct ?? null; }
function getRiskAdjScore(s) {
    const l = getLLM(s);
    if (!l) return null;
    const ev = l.expected_value_pct ?? 0;
    const scenarios = l.scenarios || {};
    let bearReturn = null;
    for (const [name, sc] of Object.entries(scenarios)) {
        if (name.toLowerCase().includes('bear') && sc?.return_pct != null) bearReturn = sc.return_pct;
    }
    const convMap = {'HIGH': 1.9, 'MEDIUM-HIGH': 1.6, 'MEDIUM': 1.3, 'LOW': 1.0};
    const cw = convMap[(l.conviction || '').toUpperCase()] || 1.3;
    if (bearReturn != null && bearReturn < 0) return (ev / Math.abs(bearReturn)) * cw;
    return ev * cw / 100;
}

function getAutoRes(s) {
    const v = s.valuations?.autoresearch;
    if (!v?.suitable || v.upside == null) return null;
    return v.upside;
}

function getGBM3y(s) {
    // Prefer gbm_opportunistic_3y, fall back to gbm_3y
    for (const m of TRUSTED_GBM) {
        const v = s.valuations?.[m];
        if (v?.suitable && v.upside != null) return v.upside;
    }
    return null;
}

function hasInsiderBuys(s) { return (s.insider?.buy_count || 0) > 0; }

function fmtPct(v) {
    const pct = (v * 100).toFixed(0);
    return (v > 0 ? '+' : '') + pct + '%';
}

// ── Rendering ──

function cardHTML(s, i) {
    const price = s.current_price != null ? '$' + Number(s.current_price).toFixed(2) : '-';
    const verdict = getVerdict(s);
    const ev = getEV(s);
    const autores = getAutoRes(s);
    const gbm = getGBM3y(s);
    const ins = s.insider || {};
    const name = (s.company_name || '').substring(0, 28);

    let tags = [];

    // Verdict (LLM)
    if (verdict) {
        const cls = verdict === 'BUY' ? 'verdict-buy' : verdict === 'PASS' ? 'verdict-pass' : 'verdict-watch';
        tags.push('<span class="verdict-pill ' + cls + '">' + verdict + '</span>');
    }

    // EV% (from LLM)
    if (ev != null) {
        const cls = ev > 5 ? 'tag-ev-pos' : ev < -5 ? 'tag-ev-neg' : 'tag-ev-neutral';
        tags.push('<span class="metric-tag ' + cls + '">' + (ev > 0 ? '+' : '') + ev.toFixed(0) + '% EV</span>');
    }

    // AutoResearch upside
    if (autores != null) {
        const cls = autores > 0 ? 'tag-upside-pos' : 'tag-upside-neg';
        tags.push('<span class="metric-tag ' + cls + '">' + fmtPct(autores) + ' AR</span>');
    }

    // GBM 3y upside
    if (gbm != null) {
        const cls = gbm > 0 ? 'tag-upside-pos' : 'tag-upside-neg';
        tags.push('<span class="metric-tag ' + cls + '">' + fmtPct(gbm) + ' GBM</span>');
    }

    // Insider signals
    if (ins.has_data) {
        const bc = ins.buy_count || 0;
        const sc = ins.sell_count || 0;
        const dollars = ins.dollar_conviction || 0;
        let dollarStr = '';
        if (dollars >= 1e6) dollarStr = ' $' + (dollars/1e6).toFixed(1) + 'M';
        else if (dollars >= 1e3) dollarStr = ' $' + (dollars/1e3).toFixed(0) + 'K';

        if (bc > 0) tags.push('<span class="metric-tag tag-insider-buy">' + bc + ' buy' + (bc>1?'s':'') + dollarStr + '</span>');
        if (sc > 0) {
            const sellTrend = ins.sell_trend;
            const cls = (sellTrend != null && sellTrend < 0.7) ? 'tag-insider-sell-normal' : 'tag-insider-sell';
            tags.push('<span class="metric-tag ' + cls + '">' + sc + ' sell' + (sc>1?'s':'') + '</span>');
        }
    }

    return '<div class="stock-card" style="animation-delay:' + Math.min(i * 0.02, 0.5) + 's" onclick="openNotes(\\'' + s.ticker + '\\')">' +
        '<div class="card-left"><span class="card-ticker">' + s.ticker + '</span><span class="card-name">' + escapeHtml(name) + '</span></div>' +
        '<div class="card-right"><span class="card-price">' + price + '</span></div>' +
        '<div class="card-bottom">' + tags.join('') + '</div>' +
    '</div>';
}

function escapeHtml(t) {
    return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function renderCards() {
    let arr = Object.values(STOCKS);

    // Filter
    if (currentFilter === 'buy') arr = arr.filter(s => getVerdict(s) === 'BUY');
    else if (currentFilter === 'watch') arr = arr.filter(s => getVerdict(s) === 'WATCH');
    else if (currentFilter === 'insider') arr = arr.filter(s => hasInsiderBuys(s));

    // Sort — each pill sorts by a specific model's upside
    const sortFn = {
        autores: (a,b) => (getAutoRes(b) ?? -999) - (getAutoRes(a) ?? -999),
        gbm: (a,b) => (getGBM3y(b) ?? -999) - (getGBM3y(a) ?? -999),
        ev: (a,b) => (getRiskAdjScore(b) ?? -999) - (getRiskAdjScore(a) ?? -999),
        price: (a,b) => (b.current_price ?? 0) - (a.current_price ?? 0),
        az: (a,b) => a.ticker.localeCompare(b.ticker),
    };
    arr.sort(sortFn[currentSort] || sortFn.autores);

    const container = document.getElementById('cardContainer');
    const empty = document.getElementById('emptyState');

    if (arr.length === 0) {
        container.innerHTML = '';
        empty.style.display = 'block';
    } else {
        empty.style.display = 'none';
        container.innerHTML = arr.map((s, i) => cardHTML(s, i)).join('');
    }

    document.getElementById('stockCount').textContent = arr.length;
}

function openNotes(ticker) {
    window.location.href = '/api/notes/' + ticker;
}

// ── Pill interaction ──

document.getElementById('sortRow').addEventListener('click', e => {
    const pill = e.target.closest('.pill');
    if (!pill || pill.classList.contains('filter')) return;
    document.querySelectorAll('#sortRow .pill').forEach(p => p.classList.remove('active'));
    pill.classList.add('active');
    currentSort = pill.dataset.sort;
    renderCards();
});

document.getElementById('filterRow').addEventListener('click', e => {
    const pill = e.target.closest('.pill');
    if (!pill) return;
    document.querySelectorAll('#filterRow .pill').forEach(p => p.classList.remove('active'));
    pill.classList.add('active');
    currentFilter = pill.dataset.filter;
    renderCards();
});

// ── Refresh ──

async function refreshData() {
    const ind = document.getElementById('pullIndicator');
    ind.classList.add('refreshing');
    ind.querySelector('.pull-text').textContent = 'Refreshing';
    try {
        const resp = await fetch('/api/stocks');
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        STOCKS = await resp.json();
        renderCards();
        lastRefresh = Date.now();
        updateAge();
    } catch(e) {
        console.error('Refresh failed:', e);
    }
    setTimeout(() => {
        ind.style.transform = 'translateY(-100%)';
        ind.classList.remove('visible', 'refreshing');
        ind.querySelector('.pull-text').textContent = 'Pull to refresh';
    }, 400);
}

// ── Refresh age display ──

function updateAge() {
    const secs = Math.floor((Date.now() - lastRefresh) / 1000);
    let txt;
    if (secs < 5) txt = 'now';
    else if (secs < 60) txt = secs + 's ago';
    else if (secs < 3600) txt = Math.floor(secs/60) + 'm ago';
    else txt = Math.floor(secs/3600) + 'h ago';
    document.getElementById('refreshAge').textContent = txt;
}
setInterval(updateAge, 5000);

// ── Page Visibility API: auto-refresh when returning ──

document.addEventListener('visibilitychange', () => {
    if (!document.hidden && (Date.now() - lastRefresh > 60000)) {
        const ind = document.getElementById('pullIndicator');
        ind.style.transform = 'translateY(0)';
        ind.classList.add('visible');
        refreshData();
    }
});

// ── Pull-to-refresh gesture ──

let touchStartY = 0;
let pulling = false;
let pullDy = 0;

document.addEventListener('touchstart', e => {
    if (window.scrollY <= 0) {
        touchStartY = e.touches[0].clientY;
        pulling = true;
        pullDy = 0;
    }
}, { passive: true });

document.addEventListener('touchmove', e => {
    if (!pulling) return;
    pullDy = e.touches[0].clientY - touchStartY;
    if (pullDy > 0 && pullDy < 160) {
        const ind = document.getElementById('pullIndicator');
        const progress = Math.min(pullDy / 80, 1);
        ind.style.transform = 'translateY(' + (pullDy * 0.5 - 40) + 'px)';
        ind.classList.toggle('visible', progress > 0.2);
        ind.querySelector('.pull-spinner').style.transform = 'rotate(' + (pullDy * 2) + 'deg)';
        if (progress >= 1) {
            ind.querySelector('.pull-text').textContent = 'Release to refresh';
        } else {
            ind.querySelector('.pull-text').textContent = 'Pull to refresh';
        }
    }
}, { passive: true });

document.addEventListener('touchend', () => {
    if (!pulling) return;
    pulling = false;
    if (pullDy >= 80) {
        const ind = document.getElementById('pullIndicator');
        ind.style.transform = 'translateY(0)';
        refreshData();
    } else {
        const ind = document.getElementById('pullIndicator');
        ind.style.transform = 'translateY(-100%)';
        ind.classList.remove('visible');
    }
}, { passive: true });

// ── Init ──

renderCards();
"""

    def _get_css_styles(self) -> str:
        """Get CSS styles — Palantir Gotham Tactical (Blueprint dark + cinematic)."""
        return """
        :root {
            /* Palantir Blueprint dark palette */
            --bg-base: #111418;
            --bg-panel: #1c2127;
            --bg-elevated: #252a31;
            --bg-hover: #2f343c;
            --bg-row-alt: rgba(76,144,240,0.03);
            --border: rgba(255,255,255,0.15);
            --border-subtle: rgba(255,255,255,0.08);
            --border-glow: rgba(76,144,240,0.3);
            --text-primary: #f6f7f9;
            --text-secondary: #abb3bf;
            --text-muted: #738091;
            --accent: #4c90f0;
            --accent-bright: #8abbff;
            --accent-dim: rgba(76,144,240,0.15);
            --gold: #d1980b;
            --gold-dim: rgba(209,152,11,0.15);
            --green: #32a467;
            --green-bright: #72ca9b;
            --green-dim: rgba(50,164,103,0.15);
            --red: #cd4246;
            --red-bright: #e76a6e;
            --red-dim: rgba(205,66,70,0.12);
            --orange: #ec9a3c;
            --orange-dim: rgba(236,154,60,0.12);
            --font-body: 'DM Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            --font-mono: 'Geist Mono', 'SF Mono', ui-monospace, monospace;
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: var(--font-body);
            font-size: 15px;
            line-height: 1.5;
            color: var(--text-primary);
            background: var(--bg-base);
            min-height: 100vh;
            -webkit-font-smoothing: antialiased;
        }

        .container {
            width: 100%;
            margin: 0;
            padding: 16px 20px;
            min-height: 100vh;
        }

        /* ── Header ── */
        .dashboard-header {
            margin-bottom: 12px;
            padding: 20px 24px;
            background: var(--bg-panel);
            border: 1px solid var(--border-subtle);
            border-top: 2px solid var(--accent);
            border-radius: 4px;
        }

        .dashboard-header h1 {
            color: var(--text-primary);
            font-size: 1.5em;
            font-weight: 700;
            letter-spacing: 2px;
            text-transform: uppercase;
            font-family: var(--font-mono);
        }

        .header-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: 6px;
        }

        .last-updated {
            color: var(--text-muted);
            font-size: 13px;
            font-family: var(--font-mono);
        }

        .header-actions { display: flex; gap: 10px; }

        /* ── Buttons ── */
        .btn {
            border: 1px solid var(--border-subtle);
            padding: 8px 18px;
            border-radius: 4px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            transition: all 0.2s ease;
            font-family: var(--font-body);
            background: var(--bg-elevated);
            color: var(--text-secondary);
        }
        .btn:hover { background: var(--bg-hover); border-color: var(--accent); color: var(--accent-bright); }
        .btn-docs { }
        .btn-export { }
        .btn-update {
            background: var(--accent);
            color: #fff;
            border-color: var(--accent);
            font-weight: 700;
        }
        .btn-update:hover { background: var(--accent-bright); border-color: var(--accent-bright); color: #111; }
        .btn-update:disabled { opacity: 0.4; cursor: not-allowed; }
        .btn-lite-update {
            background: transparent;
            color: var(--accent);
            border-color: var(--accent);
            font-weight: 600;
            font-size: 0.82em;
        }
        .btn-lite-update:hover { background: var(--accent); color: #fff; }
        .btn-lite-update:disabled { opacity: 0.4; cursor: not-allowed; }
        .btn-cancel { background: var(--red-dim); color: var(--red-bright); border-color: rgba(205,66,70,0.3); }
        .btn-cancel:hover { background: var(--red); color: #fff; }
        .btn-toggle-log {
            background: var(--bg-elevated); border: 1px solid var(--border-subtle); padding: 4px 12px;
            border-radius: 4px; font-size: 12px; cursor: pointer; color: var(--text-muted);
            font-family: var(--font-body);
        }

        /* ── Health Panel ── */
        .health-panel {
            margin-bottom: 12px;
            padding: 16px 24px;
            background: var(--bg-panel);
            border: 1px solid var(--border-subtle);
            border-radius: 4px;
        }
        .health-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .health-overall-group {
            display: flex; flex-wrap: wrap; align-items: center;
            gap: 6px 18px;
        }
        .health-overall {
            display: flex; align-items: center; gap: 10px;
            font-weight: 600; font-size: 15px;
            font-family: var(--font-body);
        }
        .health-dot {
            width: 12px; height: 12px; border-radius: 50%;
            display: inline-block; flex-shrink: 0;
        }
        .stale-fresh .health-dot { background: var(--green); box-shadow: 0 0 8px rgba(50,164,103,0.5); }
        .stale-fresh { color: var(--green-bright); }
        .stale-mild .health-dot { background: var(--orange); box-shadow: 0 0 8px rgba(236,154,60,0.5); }
        .stale-mild { color: var(--orange); }
        .stale-warning .health-dot { background: var(--red); box-shadow: 0 0 8px rgba(205,66,70,0.5); }
        .stale-warning { color: var(--red-bright); }
        .stale-critical .health-dot { background: var(--red); animation: pulse 1.5s infinite; box-shadow: 0 0 12px rgba(205,66,70,0.7); }
        .stale-critical { color: var(--red-bright); }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.3; }
        }
        .health-meta {
            color: var(--text-muted); font-size: 14px;
            font-family: var(--font-mono);
        }
        .health-details { margin-top: 10px; }
        .health-row {
            display: flex; align-items: center; gap: 12px;
            margin-bottom: 6px;
        }
        .health-label {
            font-size: 13px; font-weight: 600; color: var(--text-muted);
            min-width: 70px; text-transform: uppercase; letter-spacing: 0.8px;
            font-family: var(--font-mono);
        }
        .health-chips { display: flex; flex-wrap: wrap; gap: 6px; }
        .health-chip {
            font-size: 13px; padding: 4px 12px; border-radius: 4px;
            font-weight: 500; white-space: nowrap;
            font-family: var(--font-mono);
        }
        .health-chip small { font-weight: 400; opacity: 0.7; margin-left: 4px; }
        .chip-ok { background: var(--green-dim); color: var(--green-bright); }
        .chip-warning { background: var(--orange-dim); color: var(--orange); }
        .chip-critical { background: var(--red-dim); color: var(--red-bright); }
        .chip-missing { background: rgba(255,255,255,0.06); color: var(--text-muted); }
        .health-error {
            color: var(--red-bright); font-weight: 600; text-align: center;
            padding: 20px; background: var(--red-dim); border-radius: 4px;
        }

        /* ── Controls ── */
        .controls {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
            padding: 14px 24px;
            background: var(--bg-panel);
            border: 1px solid var(--border-subtle);
            border-radius: 4px;
        }
        .controls-left, .controls-right { display: flex; align-items: center; gap: 12px; }

        .universe-selector label {
            color: var(--text-muted); font-size: 14px;
            text-transform: uppercase; letter-spacing: 0.8px;
            font-family: var(--font-mono); font-weight: 600;
        }
        .universe-selector select, .universe-selector input {
            padding: 8px 14px;
            border: 1px solid var(--border-subtle);
            border-radius: 4px;
            font-size: 15px;
            margin-left: 8px;
            background: var(--bg-elevated);
            color: var(--text-primary);
            font-family: var(--font-body);
            outline: none;
        }
        .universe-selector select:focus, .universe-selector input:focus {
            border-color: var(--accent);
            box-shadow: 0 0 0 2px var(--accent-dim);
        }
        .universe-selector select option { background: var(--bg-elevated); color: var(--text-primary); }

        .update-status {
            font-size: 13px; font-weight: 600; padding: 6px 14px;
            border-radius: 4px; display: none;
            font-family: var(--font-mono);
        }
        .update-status.running { display: inline-block; background: var(--accent-dim); color: var(--accent-bright); }
        .update-status.completed { display: inline-block; background: var(--green-dim); color: var(--green-bright); }
        .update-status.failed { display: inline-block; background: var(--red-dim); color: var(--red-bright); }

        /* ── Update Log ── */
        .update-log {
            margin-bottom: 12px;
            background: var(--bg-base);
            border: 1px solid var(--border-subtle);
            border-radius: 4px;
            overflow: hidden;
        }
        .update-log-header {
            display: flex; justify-content: space-between; align-items: center;
            padding: 10px 20px;
            background: var(--bg-panel);
            border-bottom: 1px solid var(--border-subtle);
            color: var(--text-secondary);
            font-size: 14px; font-weight: 600;
        }
        .update-log-content {
            padding: 12px 20px;
            color: var(--text-muted);
            font-size: 13px;
            max-height: 200px;
            overflow-y: auto;
            margin: 0;
            font-family: var(--font-mono);
            line-height: 1.7;
        }

        /* ── Summary ── */
        .analysis-summary {
            margin-bottom: 12px;
            padding: 18px 24px;
            background: var(--bg-panel);
            border: 1px solid var(--border-subtle);
            border-radius: 4px;
        }
        .analysis-summary h2 {
            font-size: 14px; color: var(--text-muted);
            text-transform: uppercase; letter-spacing: 1.5px;
            font-family: var(--font-mono); font-weight: 600;
            margin-bottom: 12px;
        }

        .summary-grid {
            display: flex;
            flex-wrap: wrap;
            gap: 1px;
            background: var(--border-subtle);
            border-radius: 4px;
            overflow: hidden;
        }

        .summary-item {
            text-align: center;
            padding: 14px 18px;
            background: var(--bg-base);
            font-size: 14px;
            color: var(--text-secondary);
            flex: 1;
            min-width: 90px;
        }
        .summary-item strong {
            display: block;
            font-size: 24px;
            font-weight: 700;
            color: var(--text-primary);
            font-family: var(--font-mono);
            line-height: 1.3;
        }

        .stock-analysis { margin-bottom: 16px; }
        .stock-analysis h2 {
            font-size: 14px; margin-bottom: 10px; color: var(--text-muted);
            text-transform: uppercase; letter-spacing: 1.5px; font-weight: 600;
            font-family: var(--font-mono);
        }

        /* ── Table ── */
        .table-container {
            overflow-x: auto;
            overflow-y: auto;
            height: calc(100vh - 300px);
            min-height: 200px;
            background: var(--bg-base);
            border: 1px solid var(--border-subtle);
            border-radius: 4px;
        }

        .stock-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 15px;
        }

        .stock-table th {
            position: sticky;
            top: 0;
            z-index: 10;
            background: var(--bg-panel);
            color: var(--text-muted);
            padding: 14px 12px;
            text-align: left;
            cursor: pointer;
            user-select: none;
            font-weight: 600;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            border-bottom: 2px solid var(--border-glow);
            font-family: var(--font-mono);
            transition: color 0.15s;
            white-space: nowrap;
        }

        .stock-table th:hover { color: var(--accent-bright); }

        .stock-table th.sort-asc::after { content: ' \\25B2'; font-size: 10px; color: var(--accent); }
        .stock-table th.sort-desc::after { content: ' \\25BC'; font-size: 10px; color: var(--accent); }

        .stock-table td {
            padding: 10px 12px;
            border-bottom: 1px solid var(--border-subtle);
            font-family: var(--font-mono);
            font-size: 14px;
        }

        .stock-table td:first-child {
            font-weight: 700;
            font-size: 15px;
        }
        .ticker-link {
            color: var(--accent-bright);
            text-decoration: none;
            font-weight: 700;
        }
        .ticker-link:hover { text-decoration: underline; }
        .ticker-trigger {
            color: var(--accent-bright);
            font-weight: 700;
            cursor: pointer;
            padding: 4px 6px;
            border-radius: 4px;
            transition: background 0.12s;
            user-select: none;
        }
        .ticker-trigger:hover { background: var(--bg-hover, rgba(76,144,240,0.12)); }
        .notes-link {
            display: block; width: fit-content; margin: 5px 0 0 6px; padding: 2px 6px;
            color: var(--accent-bright); background: var(--accent-dim);
            border: 1px solid var(--border-subtle); border-radius: 4px;
            font-size: 11px; font-weight: 600; text-decoration: none;
        }
        .notes-link:hover { background: var(--bg-hover); border-color: var(--border-glow); }

        .stock-row { transition: background 0.1s; }
        .stock-row:nth-child(even) { background: var(--bg-row-alt); }
        .stock-row:hover { background: rgba(76,144,240,0.08); }
        .stock-row.completed { }
        .stock-row.analyzing { background: rgba(76,144,240,0.05); }

        .valuation-cell { text-align: center; }
        .fair-value {
            font-weight: 600; margin-bottom: 2px;
            color: var(--text-primary);
            font-family: var(--font-mono);
            font-size: 15px;
        }
        .margin {
            font-size: 13px; padding: 2px 7px; border-radius: 3px;
            font-weight: 600;
            font-family: var(--font-mono);
            display: inline-block;
        }
        .ratio {
            font-size: 12px; color: var(--text-muted); font-weight: 400;
            margin-top: 1px; font-family: var(--font-mono);
        }

        .margin-excellent { background: var(--green-dim); color: var(--green-bright); }
        .margin-good { background: var(--gold-dim); color: var(--gold); }
        .margin-neutral { background: rgba(255,255,255,0.05); color: var(--text-muted); }
        .margin-poor { background: var(--red-dim); color: var(--red-bright); }

        .consensus-cell {
            text-align: center;
            border-left: 2px solid var(--border-glow);
            padding-left: 10px;
        }
        .model-count { font-size: 12px; color: var(--text-muted); margin-top: 2px; }

        .no-data {
            text-align: center;
            padding: 60px;
            color: var(--text-muted);
            font-size: 16px;
        }

        /* ── Scrollbar ── */
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: var(--bg-base); }
        ::-webkit-scrollbar-thumb { background: var(--bg-hover); border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: var(--text-muted); }

        /* ── Selection ── */
        ::selection { background: rgba(76,144,240,0.3); color: var(--text-primary); }

        @media (max-width: 768px) {
            .container { padding: 6px; }

            /* ── Header: hide title, keep buttons ── */
            .dashboard-header { padding: 6px 12px; margin-bottom: 4px; }
            .dashboard-header h1 { display: none; }
            .last-updated { display: none; }
            .header-row { flex-direction: row; gap: 6px; align-items: center; }
            .header-actions { flex-wrap: wrap; gap: 6px; }
            .btn { padding: 5px 10px; font-size: 11px; }

            /* ── Health panel: collapsed by default on mobile ── */
            .health-panel { padding: 8px 12px; margin-bottom: 6px; }
            .health-header { flex-direction: row; gap: 8px; align-items: center; cursor: pointer; }
            .health-details { display: none; margin-top: 6px; }
            .health-panel.expanded .health-details { display: block; }
            .health-header::after {
                content: '\\25BC'; font-size: 10px; color: var(--text-muted);
                transition: transform 0.2s; margin-left: auto;
            }
            .health-panel.expanded .health-header::after { transform: rotate(180deg); }
            .health-row { flex-direction: column; align-items: flex-start; gap: 4px; }
            .health-chips { gap: 3px; }
            .health-chip { font-size: 10px; padding: 2px 6px; }
            .health-meta { font-size: 11px; }

            /* ── Controls: compact row ── */
            .controls { flex-direction: column; gap: 4px; padding: 6px 12px; margin-bottom: 4px; }
            .controls-left, .controls-right { flex-wrap: wrap; width: 100%; }
            .controls-right { justify-content: flex-start; }

            /* ── Summary: collapsed by default on mobile ── */
            .analysis-summary { padding: 4px 12px; margin-bottom: 4px; cursor: pointer; }
            .analysis-summary h2::after {
                content: '\\25BC'; font-size: 10px; color: var(--text-muted);
                margin-left: 8px; transition: transform 0.2s;
            }
            .summary-grid { display: none; }
            .analysis-summary.expanded .summary-grid { display: flex; flex-wrap: wrap; gap: 4px; }
            .analysis-summary.expanded h2::after { transform: rotate(180deg); }
            .summary-item { min-width: auto; padding: 4px 8px; flex: 1 1 70px; }
            .summary-item h3 { font-size: 16px; }
            .summary-item p { font-size: 9px; }

            /* ── Table: the main event ── */
            .table-container {
                height: calc(100dvh - 60px);
                min-height: 400px;
                -webkit-overflow-scrolling: touch;
                border-radius: 0;
                border-left: none;
                border-right: none;
            }
            .stock-table { font-size: 12px; }
            .stock-table th { padding: 10px 8px; font-size: 10px; }
            .stock-table td { padding: 8px 6px; font-size: 12px; }

            /* Hide rank column on mobile */
            .rank-cell,
            .stock-table th:first-child { display: none; }

            /* Sticky Stock column (2nd col = first visible) */
            .ticker-cell {
                position: sticky;
                left: 0;
                z-index: 5;
                background: var(--bg-panel);
                box-shadow: 2px 0 6px rgba(0,0,0,0.4);
            }
            /* Header Stock th: sticky both top AND left, above everything */
            .stock-table th:nth-child(2) {
                position: sticky;
                left: 0;
                z-index: 30;
                background: var(--bg-panel);
                box-shadow: 2px 0 6px rgba(0,0,0,0.4);
            }
            /* Keep bg consistent on alternating/hovered rows */
            .stock-row:nth-child(even) .ticker-cell {
                background: color-mix(in srgb, var(--bg-panel) 97%, var(--accent) 3%);
            }
            .stock-row:hover .ticker-cell {
                background: color-mix(in srgb, var(--bg-panel) 92%, var(--accent) 8%);
            }

            /* ── Kebab menu: larger touch targets ── */
            .kebab-item { padding: 11px 12px; font-size: 14px; }
            .kebab-menu { min-width: 220px; }
            .kebab-label { font-size: 12px; padding: 8px 12px; }

            /* ── Modal: full-width ── */
            .modal-content { width: 95vw; max-width: none; margin: 10px; }

            /* ── Alarm panel: bottom sheet ── */
            .alarm-panel { width: 100vw; right: 0; bottom: 0; max-height: 50vh; border-radius: 12px 12px 0 0; }

            /* ── Update log ── */
            .update-log-panel { font-size: 11px; }
        }

        /* ── Kebab Menu (Linear/shadcn pattern) ── */
        .rank-cell { color: var(--text-dim, #738091); font-size: 0.8em; text-align: right; padding-right: 4px; min-width: 28px; }
        .ticker-cell { position: relative; white-space: nowrap; }
        .ticker-trigger.has-alarm { text-shadow: 0 0 8px var(--accent-bright); }
        .kebab-menu {
            display: none; position: absolute; left: 0;
            background: #1e2433; border: 1px solid rgba(255,255,255,0.08);
            border-radius: 8px; min-width: 200px; z-index: 500;
            box-shadow: 0 8px 24px rgba(0,0,0,0.6); padding: 4px;
        }
        .kebab-menu.open { display: block; }
        /* Section label — metadata, non-interactive */
        .kebab-label {
            padding: 6px 10px; font-size: 11px; font-weight: 500;
            color: rgba(255,255,255,0.4);
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
            max-width: 240px; cursor: default; user-select: none;
        }
        /* Separator between metadata and actions */
        .kebab-sep {
            height: 1px; background: rgba(255,255,255,0.08);
            margin: 4px -4px;
        }
        /* Action item — interactive */
        .kebab-item {
            display: block; padding: 7px 10px; color: rgba(255,255,255,0.88);
            text-decoration: none; font-size: 13px; cursor: pointer;
            font-family: var(--font-main, system-ui); font-weight: 400;
            white-space: nowrap; border: none; background: none; width: 100%;
            text-align: left; border-radius: 4px;
        }
        .kebab-item:hover { background: rgba(255,255,255,0.08); }

        /* ── Alarm Bell (kept for modal) ── */
        .alarm-bell {
            cursor: pointer; font-size: 13px; opacity: 0.25;
            transition: opacity 0.15s; margin-left: 3px;
            vertical-align: middle;
        }
        .alarm-bell:hover { opacity: 0.9; }
        .alarm-bell.has-alarm { opacity: 0.85; filter: saturate(2) brightness(1.4); }

        /* ── Modal ── */
        .modal-overlay {
            position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
            background: rgba(0,0,0,0.6); z-index: 1000;
            display: flex; align-items: center; justify-content: center;
        }
        .modal-content {
            background: var(--bg-panel, #1a1f2e); border: 1px solid var(--border, #2a3040);
            border-radius: 8px; padding: 28px 32px; min-width: 380px; max-width: 500px;
        }
        .modal-content h3 { font-size: 18px; margin: 0 0 8px; color: var(--text-primary, #e0e6ed); }
        .modal-price { color: var(--text-muted, #738091); font-family: var(--font-mono, monospace); font-size: 14px; margin: 0 0 16px; }
        .modal-form { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 16px; }
        .modal-form select, .modal-form input {
            padding: 8px 12px; border: 1px solid var(--border, #2a3040);
            border-radius: 4px; background: var(--bg-elevated, #0d1117); color: var(--text-primary, #e0e6ed);
            font-size: 14px; font-family: var(--font-mono, monospace);
        }
        .modal-form input { width: 120px; }

        /* ── Alarm List (in modal) ── */
        .alarm-list { max-height: 200px; overflow-y: auto; }
        .alarm-item {
            display: flex; justify-content: space-between; align-items: center;
            padding: 8px 12px; border-bottom: 1px solid var(--border, #2a3040);
            font-size: 13px; font-family: var(--font-mono, monospace);
        }
        .alarm-item .alarm-info { color: var(--text-secondary, #9ba8b9); }
        .alarm-item .alarm-triggered { color: #3fb950; font-size: 12px; }
        .alarm-item .alarm-delete { cursor: pointer; color: #f85149; opacity: 0.6; font-size: 15px; }
        .alarm-item .alarm-delete:hover { opacity: 1; }

        /* ── Toast ── */
        .toast-container {
            position: fixed; top: 20px; right: 20px; z-index: 2000;
            display: flex; flex-direction: column; gap: 8px; pointer-events: none;
        }
        .toast {
            pointer-events: auto;
            background: var(--bg-panel, #1a1f2e); border: 1px solid #d4a017;
            border-left: 4px solid #d4a017; border-radius: 4px;
            padding: 14px 20px; min-width: 300px; max-width: 420px;
            font-size: 14px; color: var(--text-primary, #e0e6ed);
            animation: toastIn 0.3s ease, toastOut 0.5s ease 9.5s forwards;
            box-shadow: 0 4px 20px rgba(0,0,0,0.4);
        }
        .toast .toast-title { font-weight: 700; color: #d4a017; margin-bottom: 4px; }
        .toast .toast-body { color: var(--text-secondary, #9ba8b9); font-family: var(--font-mono, monospace); font-size: 13px; }
        @keyframes toastIn { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
        @keyframes toastOut { to { opacity: 0; transform: translateY(-10px); } }

        /* ── Notification Bar ── */
        .notification-bar {
            background: var(--bg-panel, #1a1f2e); border: 1px solid #d4a017;
            border-left: 4px solid #d4a017; border-radius: 8px;
            margin-bottom: 16px; overflow: hidden;
        }
        .notification-bar-header {
            display: flex; justify-content: space-between; align-items: center;
            padding: 10px 16px; border-bottom: 1px solid rgba(212,160,23,0.2);
        }
        .notification-bar-title { font-weight: 700; color: #d4a017; font-size: 14px; }
        .notification-list { max-height: 200px; overflow-y: auto; }
        .notification-item {
            display: flex; align-items: center; gap: 10px;
            padding: 8px 16px; border-bottom: 1px solid var(--border, #2a3040);
            font-size: 13px; color: var(--text-primary, #e0e6ed);
        }
        .notification-item:last-child { border-bottom: none; }
        .notification-item .notif-icon { font-size: 16px; flex-shrink: 0; }
        .notification-item .notif-text { flex: 1; }
        .notification-item .notif-ticker { color: #58a6ff; font-weight: 600; font-family: var(--font-mono, monospace); }
        .notification-item .notif-dismiss {
            background: none; border: none; color: var(--text-secondary, #9ba8b9);
            cursor: pointer; font-size: 16px; padding: 2px 6px; border-radius: 4px;
        }
        .notification-item .notif-dismiss:hover { background: rgba(255,255,255,0.1); color: #f87171; }

        /* ── Alarm Panel (sidebar) ── */
        .alarm-panel-toggle {
            position: fixed; bottom: 20px; right: 20px; z-index: 900;
            background: var(--bg-panel, #1a1f2e); border: 1px solid var(--border, #2a3040);
            border-radius: 50%; width: 48px; height: 48px;
            cursor: pointer; font-size: 18px; color: #d4a017;
            display: flex; align-items: center; justify-content: center; gap: 2px;
            box-shadow: 0 2px 12px rgba(0,0,0,0.3);
        }
        .alarm-panel-toggle span {
            font-size: 11px; font-weight: 700; font-family: var(--font-mono, monospace);
            color: var(--text-secondary, #9ba8b9);
        }
        .alarm-panel {
            position: fixed; top: 0; right: 0; width: 380px; height: 100vh;
            background: var(--bg-panel, #1a1f2e); border-left: 1px solid var(--border, #2a3040);
            z-index: 950; overflow-y: auto; box-shadow: -4px 0 20px rgba(0,0,0,0.3);
        }
        .alarm-panel-header {
            display: flex; justify-content: space-between; align-items: center;
            padding: 20px 24px; border-bottom: 1px solid var(--border, #2a3040);
        }
        .alarm-panel-header h3 { font-size: 16px; color: var(--text-primary, #e0e6ed); margin: 0; }
        .alarm-panel-list { padding: 12px; }"""

    def _get_javascript(self) -> str:
        """Get JavaScript for dashboard interactivity."""
        return """
        let pollTimer = null;
        let logExpanded = true;

        function openNotes(ticker) {
            if (SERVER_MODE) {
                window.location.href = '/api/notes/' + ticker;
            } else {
                window.location.href = '../notes/companies/' + ticker + '.md';
            }
        }

        // ── Init ──
        document.addEventListener('DOMContentLoaded', function() {
            // Table sorting
            const table = document.getElementById('stockTable');
            if (table) {
                table.querySelectorAll('th').forEach((header, i) => {
                    header.addEventListener('click', () => sortTableByColumn(i));
                });
            }

            updateRankNumbers();

            // Mobile: collapsible health panel and summary
            if (window.innerWidth <= 768) {
                const hp = document.getElementById('healthPanel');
                if (hp) {
                    hp.querySelector('.health-header').addEventListener('click', () => hp.classList.toggle('expanded'));
                }
                document.querySelectorAll('.analysis-summary').forEach(el => {
                    el.addEventListener('click', e => {
                        if (e.target.closest('.summary-item')) return;
                        el.classList.toggle('expanded');
                    });
                });
            }

            // Universe selector
            document.getElementById('universe').addEventListener('change', function() {
                const ci = document.getElementById('customTickers');
                ci.style.display = this.value === 'custom' ? 'inline-block' : 'none';
            });

            // If server mode, show server controls and start polling
            if (SERVER_MODE) {
                applyUpdateStatus(INITIAL_UPDATE_STATUS);
                if (INITIAL_UPDATE_STATUS.status === 'running') {
                    startPolling();
                }
            }
        });

        // ── Update control ──
        function triggerUpdate(lite) {
            if (!SERVER_MODE) { alert('Server not running. Start with: uv run python scripts/dashboard_server.py'); return; }

            const universe = document.getElementById('universe').value;
            const btn = document.getElementById('updateButton');
            const liteBtn = document.getElementById('liteUpdateButton');
            btn.disabled = true;
            liteBtn.disabled = true;
            btn.textContent = lite ? 'Lite...' : 'Starting...';

            fetch('/api/update', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ universe, lite: !!lite })
            })
            .then(r => r.json())
            .then(data => {
                if (data.ok) {
                    startPolling();
                } else if (data.reason === 'already_running') {
                    startPolling();  // just attach to existing run
                } else {
                    btn.disabled = false;
                    liteBtn.disabled = false;
                    btn.textContent = 'Update Data';
                    alert('Failed to start: ' + (data.reason || 'unknown'));
                }
            })
            .catch(err => {
                btn.disabled = false;
                liteBtn.disabled = false;
                btn.textContent = 'Update Data';
                console.error('Update trigger failed:', err);
            });
        }

        function cancelUpdate() {
            fetch('/api/update/cancel', { method: 'POST' })
            .then(r => r.json())
            .then(data => {
                if (data.ok) stopPolling();
            });
        }

        function startPolling() {
            if (pollTimer) return;
            pollTimer = setInterval(pollStatus, 2000);
            pollStatus();  // immediate first poll
        }

        function stopPolling() {
            if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
        }

        function pollStatus() {
            fetch('/api/update/status')
            .then(r => r.json())
            .then(data => {
                applyUpdateStatus(data);
                if (data.status !== 'running') {
                    stopPolling();
                    // Reload page to get fresh data after completion
                    if (data.status === 'completed') {
                        setTimeout(() => location.reload(), 1000);
                    }
                }
            })
            .catch(err => console.error('Poll failed:', err));
        }

        function applyUpdateStatus(s) {
            const btn = document.getElementById('updateButton');
            const liteBtn = document.getElementById('liteUpdateButton');
            const cancelBtn = document.getElementById('cancelButton');
            const statusEl = document.getElementById('updateStatus');
            const logEl = document.getElementById('updateLog');
            const phaseEl = document.getElementById('updatePhase');
            const logContent = document.getElementById('updateLogContent');

            // Reset classes
            statusEl.className = 'update-status';

            if (s.status === 'running') {
                btn.disabled = true;
                liteBtn.disabled = true;
                btn.textContent = 'Updating...';
                cancelBtn.style.display = 'inline-flex';
                statusEl.className = 'update-status running';
                statusEl.textContent = s.phase || 'Running...';
                logEl.style.display = 'block';
                phaseEl.textContent = s.phase || 'Processing...';
                if (s.tail && s.tail.length) {
                    logContent.textContent = s.tail.join('\\n');
                    logContent.scrollTop = logContent.scrollHeight;
                }
            } else if (s.status === 'completed') {
                btn.disabled = false;
                liteBtn.disabled = false;
                btn.textContent = 'Update Data';
                cancelBtn.style.display = 'none';
                statusEl.className = 'update-status completed';
                statusEl.textContent = 'Completed ' + formatTimeAgo(s.finished_at);
                logEl.style.display = 'none';
            } else if (s.status === 'failed') {
                btn.disabled = false;
                liteBtn.disabled = false;
                btn.textContent = 'Update Data';
                cancelBtn.style.display = 'none';
                statusEl.className = 'update-status failed';
                statusEl.textContent = 'Failed: ' + (s.error || 'unknown error');
                logEl.style.display = 'block';
                phaseEl.textContent = 'FAILED - ' + (s.error || '');
                if (s.tail && s.tail.length) {
                    logContent.textContent = s.tail.join('\\n');
                    logContent.scrollTop = logContent.scrollHeight;
                }
            } else {
                // idle
                btn.disabled = false;
                liteBtn.disabled = false;
                btn.textContent = 'Update Data';
                cancelBtn.style.display = 'none';
                logEl.style.display = 'none';
            }
        }

        function toggleLog() {
            const content = document.getElementById('updateLogContent');
            logExpanded = !logExpanded;
            content.style.display = logExpanded ? 'block' : 'none';
        }

        function formatTimeAgo(iso) {
            if (!iso) return '';
            const diff = (Date.now() - new Date(iso).getTime()) / 1000;
            if (diff < 60) return 'just now';
            if (diff < 3600) return Math.floor(diff/60) + 'm ago';
            if (diff < 86400) return Math.floor(diff/3600) + 'h ago';
            return Math.floor(diff/86400) + 'd ago';
        }

        // ── Table sorting ──
        function sortTableByColumn(columnIndex) {
            const table = document.getElementById('stockTable');
            const tbody = table.querySelector('tbody');
            const rows = Array.from(tbody.querySelectorAll('tr'));

            const header = table.querySelectorAll('th')[columnIndex];
            const isAscending = !header.classList.contains('sort-asc');

            table.querySelectorAll('th').forEach(h => h.classList.remove('sort-asc', 'sort-desc'));
            header.classList.add(isAscending ? 'sort-asc' : 'sort-desc');

            rows.sort((rowA, rowB) => {
                const cellA = rowA.cells[columnIndex];
                const cellB = rowB.cells[columnIndex];
                if (!cellA || !cellB) return 0;

                let textA = cellA.textContent.trim();
                let textB = cellB.textContent.trim();

                const isEmptyA = textA === '-' || textA === 'N/A' || textA === '' || textA === '\\u2014';
                const isEmptyB = textB === '-' || textB === 'N/A' || textB === '' || textB === '\\u2014';
                if (isEmptyA && isEmptyB) return 0;
                if (isEmptyA) return 1;
                if (isEmptyB) return -1;

                // Check for data-sort-value (used by LLM column for risk-adjusted score)
                const sortValA = cellA.querySelector('[data-sort-value]');
                const sortValB = cellB.querySelector('[data-sort-value]');
                const ratioA = cellA.querySelector('.ratio');
                const ratioB = cellB.querySelector('.ratio');
                const marginA = cellA.querySelector('.margin');
                const marginB = cellB.querySelector('.margin');

                let comparison = 0;
                if (sortValA && sortValB) {
                    const sA = parseFloat(sortValA.dataset.sortValue);
                    const sB = parseFloat(sortValB.dataset.sortValue);
                    if (!isNaN(sA) && !isNaN(sB)) comparison = sB - sA;
                } else if (ratioA && ratioB) {
                    const rA = parseFloat(ratioA.textContent.replace(/[x]/g, ''));
                    const rB = parseFloat(ratioB.textContent.replace(/[x]/g, ''));
                    if (!isNaN(rA) && !isNaN(rB)) comparison = rB - rA;
                    else {
                        const pA = parseFloat(marginA?.textContent.replace(/[%+]/g, '') || '0');
                        const pB = parseFloat(marginB?.textContent.replace(/[%+]/g, '') || '0');
                        comparison = pB - pA;
                    }
                } else if (marginA && marginB) {
                    const pA = parseFloat(marginA.textContent.replace(/[%+]/g, ''));
                    const pB = parseFloat(marginB.textContent.replace(/[%+]/g, ''));
                    comparison = pB - pA;
                } else if (marginA || marginB) {
                    comparison = marginA ? -1 : 1;
                } else {
                    const nA = parseFloat(textA.replace(/[$,%]/g, ''));
                    const nB = parseFloat(textB.replace(/[$,%]/g, ''));
                    if (!isNaN(nA) && !isNaN(nB)) comparison = nB - nA;
                    else comparison = textA.localeCompare(textB);
                }
                return isAscending ? comparison : -comparison;
            });
            rows.forEach(row => tbody.appendChild(row));
            updateRankNumbers();
        }

        function updateRankNumbers() {
            const tbody = document.getElementById('stockTable')?.querySelector('tbody');
            if (!tbody) return;
            let rank = 1;
            tbody.querySelectorAll('tr').forEach(row => {
                if (row.style.display !== 'none') {
                    const cell = row.querySelector('.rank-cell');
                    if (cell) cell.textContent = rank++;
                }
            });
        }

        // ── Free-text row filter (above the table) ──
        // Splits the query on whitespace; row must contain ALL tokens
        // (case-insensitive, anywhere in row text). Updates a count badge
        // and re-numbers ranks. Cleared input restores all rows.
        function filterTableRows() {
            const input = document.getElementById('tableSearch');
            const tbody = document.getElementById('stockTable')?.querySelector('tbody');
            const counter = document.getElementById('tableSearchCount');
            if (!input || !tbody) return;
            const query = input.value.trim().toLowerCase();
            const tokens = query ? query.split(/\\s+/) : [];
            let visible = 0;
            const rows = tbody.querySelectorAll('tr');
            rows.forEach(row => {
                if (!tokens.length) {
                    row.style.display = '';
                    visible++;
                    return;
                }
                const text = row.textContent.toLowerCase();
                const match = tokens.every(t => text.includes(t));
                row.style.display = match ? '' : 'none';
                if (match) visible++;
            });
            if (counter) {
                counter.textContent = tokens.length
                    ? `${visible} / ${rows.length} rows`
                    : '';
            }
            updateRankNumbers();
        }

        // ── Export CSV ──
        function exportToCSV() {
            const table = document.getElementById('stockTable');
            if (!table) return;

            const rows = [];
            const headers = [];
            table.querySelectorAll('thead th').forEach(th => {
                headers.push(th.textContent.trim().replace(/[\\u2191\\u2193]/g, ''));
            });
            rows.push(headers);

            table.querySelectorAll('tbody tr').forEach(tr => {
                if (tr.style.display !== 'none') {
                    const row = [];
                    tr.querySelectorAll('td').forEach(td => {
                        let text = td.textContent.trim().replace(/\\s+/g, ' ');
                        if (text.includes(',') || text.includes('"') || text.includes('\\n')) {
                            text = '"' + text.replace(/"/g, '""') + '"';
                        }
                        row.push(text);
                    });
                    rows.push(row);
                }
            });

            const csv = rows.map(r => r.join(',')).join('\\n');
            const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
            const link = document.createElement('a');
            link.href = URL.createObjectURL(blob);
            link.download = `dashboard_export_${new Date().toISOString().split('T')[0]}.csv`;
            link.style.visibility = 'hidden';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        }

        // ── Kebab Menu ──
        function closeAllKebabs() {
            document.querySelectorAll('.kebab-menu.open').forEach(m => m.classList.remove('open'));
        }
        function toggleKebab(event, trigger) {
            event.stopPropagation();
            const menu = trigger.parentElement.querySelector('.kebab-menu');
            const wasOpen = menu.classList.contains('open');
            closeAllKebabs();
            if (!wasOpen) {
                const rect = trigger.getBoundingClientRect();
                const td = trigger.parentElement;
                const tdRect = td.getBoundingClientRect();
                menu.style.top = (rect.bottom - tdRect.top) + 'px';
                menu.classList.add('open');
            }
        }
        document.addEventListener('click', closeAllKebabs);

        // ── Price Alarms ──
        let _lastTriggeredCheck = new Date().toISOString();

        function openAlarmModal(ticker, currentPrice) {
            document.getElementById('alarmTicker').textContent = ticker;
            document.getElementById('alarmCurrentPrice').textContent = '$' + (currentPrice || 0).toFixed(2);
            document.getElementById('alarmTargetPrice').value = (currentPrice || 0).toFixed(2);
            document.getElementById('alarmModal').style.display = 'flex';
            document.getElementById('alarmModal').dataset.ticker = ticker;
            loadAlarmsForTicker(ticker);
        }

        function closeAlarmModal() {
            document.getElementById('alarmModal').style.display = 'none';
        }

        function createAlarm() {
            const ticker = document.getElementById('alarmModal').dataset.ticker;
            const condition = document.getElementById('alarmCondition').value;
            const targetPrice = parseFloat(document.getElementById('alarmTargetPrice').value);
            if (!ticker || isNaN(targetPrice) || targetPrice <= 0) { alert('Invalid target price'); return; }

            fetch('/api/alarms', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ ticker, condition, target_price: targetPrice })
            })
            .then(r => r.json())
            .then(data => {
                if (data.ok) {
                    loadAlarmsForTicker(ticker);
                    refreshAlarmBadge();
                } else {
                    alert('Failed: ' + (data.error || 'unknown'));
                }
            });
        }

        function loadAlarmsForTicker(ticker) {
            fetch('/api/alarms?ticker=' + encodeURIComponent(ticker))
            .then(r => r.json())
            .then(data => {
                const list = document.getElementById('alarmList');
                if (!data.alarms || data.alarms.length === 0) {
                    list.innerHTML = '<p style="color:var(--text-muted,#738091);font-size:13px;margin:8px 0 0;">No alarms set.</p>';
                    return;
                }
                list.innerHTML = data.alarms.map(a => {
                    const status = a.triggered_at
                        ? '<span class="alarm-triggered">Triggered ' + formatTimeAgo(a.triggered_at) + '</span>'
                        : '<span style="color:#58a6ff">Active</span>';
                    return '<div class="alarm-item">' +
                        '<span class="alarm-info">' + a.condition + ' $' + Number(a.target_price).toFixed(2) + ' ' + status + '</span>' +
                        '<span class="alarm-delete" onclick="deleteAlarm(' + a.id + ',\\'' + ticker + '\\')" title="Delete">&#10005;</span>' +
                        '</div>';
                }).join('');
            });
        }

        function deleteAlarm(id, ticker) {
            fetch('/api/alarms/' + id, { method: 'DELETE' })
            .then(r => r.json())
            .then(data => {
                if (data.ok) {
                    if (ticker) loadAlarmsForTicker(ticker);
                    refreshAlarmBadge();
                    loadAlarmPanel();
                }
            });
        }

        function toggleAlarmPanel() {
            const panel = document.getElementById('alarmPanel');
            panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
            if (panel.style.display === 'block') loadAlarmPanel();
        }

        function loadAlarmPanel() {
            fetch('/api/alarms')
            .then(r => r.json())
            .then(data => {
                const list = document.getElementById('alarmPanelList');
                if (!data.alarms || data.alarms.length === 0) {
                    list.innerHTML = '<p style="color:var(--text-muted,#738091);padding:20px;text-align:center;">No alarms configured.</p>';
                    return;
                }
                list.innerHTML = data.alarms.map(a => {
                    const status = a.triggered_at
                        ? '<span class="alarm-triggered">Triggered ' + formatTimeAgo(a.triggered_at) + '</span>'
                        : '<span style="color:#58a6ff">Active</span>';
                    return '<div class="alarm-item">' +
                        '<span class="alarm-info"><strong>' + a.ticker + '</strong> ' + a.condition + ' $' + Number(a.target_price).toFixed(2) + ' ' + status + '</span>' +
                        '<span class="alarm-delete" onclick="deleteAlarm(' + a.id + ')" title="Delete">&#10005;</span>' +
                        '</div>';
                }).join('');
            });
        }

        function refreshAlarmBadge() {
            if (!SERVER_MODE) return;
            fetch('/api/alarms')
            .then(r => r.json())
            .then(data => {
                const active = (data.alarms || []).filter(a => a.active).length;
                document.getElementById('activeAlarmCount').textContent = active;
                const toggle = document.getElementById('alarmPanelToggle');
                toggle.style.display = active > 0 || (data.alarms && data.alarms.length > 0) ? 'flex' : 'none';
                // Highlight bell icons for tickers with active alarms
                const activeTickers = new Set((data.alarms || []).filter(a => a.active).map(a => a.ticker));
                document.querySelectorAll('.ticker-trigger').forEach(el => {
                    el.classList.toggle('has-alarm', activeTickers.has(el.dataset.ticker));
                });
            })
            .catch(() => {});
        }

        function checkTriggeredAlarms() {
            if (!SERVER_MODE) return;
            fetch('/api/alarms/triggered?since=' + encodeURIComponent(_lastTriggeredCheck))
            .then(r => r.json())
            .then(data => {
                _lastTriggeredCheck = new Date().toISOString();
                if (data.triggered && data.triggered.length > 0) {
                    data.triggered.forEach(a => {
                        const container = document.getElementById('toastContainer');
                        const toast = document.createElement('div');
                        toast.className = 'toast';
                        toast.innerHTML = '<div class="toast-title">&#128276; ' + a.ticker + ' Alarm</div>' +
                            '<div class="toast-body">Price went ' + a.condition + ' $' + Number(a.target_price).toFixed(2) + '</div>';
                        container.appendChild(toast);
                        setTimeout(() => toast.remove(), 10000);
                    });
                    refreshAlarmBadge();
                }
            })
            .catch(() => {});
        }

        // Init alarms on page load.
        if (SERVER_MODE) {
            refreshAlarmBadge();
            setInterval(checkTriggeredAlarms, 30000);
        }

        // ── Notification Bar ────────────────────────────────────────────
        let _dismissedAlarmIds = new Set();  // session-only dismissals for alarms

        function refreshNotificationBar() {
            if (!SERVER_MODE) return;
            const sevenDaysAgo = new Date(Date.now() - 7*86400000).toISOString();
            Promise.all([
                fetch('/api/alarms/triggered?since=' + encodeURIComponent(sevenDaysAgo)).then(r => r.json()),
                fetch('/api/reminders/due').then(r => r.json())
            ]).then(([alarmData, reminderData]) => {
                const items = [];
                (alarmData.triggered || []).forEach(a => {
                    if (_dismissedAlarmIds.has(a.id)) return;
                    items.push({
                        type: 'alarm', id: a.id,
                        icon: '&#128276;',
                        html: '<span class="notif-ticker">' + a.ticker + '</span> price went ' +
                              a.condition + ' $' + Number(a.target_price).toFixed(2),
                        date: a.triggered_at
                    });
                });
                (reminderData.reminders || []).forEach(r => {
                    items.push({
                        type: 'reminder', id: r.id,
                        icon: '&#128197;',
                        html: (r.ticker ? '<span class="notif-ticker">' + r.ticker + '</span> ' : '') +
                              r.message + ' <span style="color:#738091; font-size:11px;">(due ' + r.due_date + ')</span>',
                        date: r.due_date
                    });
                });
                const bar = document.getElementById('notificationBar');
                const list = document.getElementById('notificationList');
                if (items.length === 0) {
                    bar.style.display = 'none';
                    return;
                }
                bar.style.display = 'block';
                list.innerHTML = items.map(it => {
                    const q = String.fromCharCode(39);
                    return '<div class="notification-item">' +
                    '<span class="notif-icon">' + it.icon + '</span>' +
                    '<span class="notif-text">' + it.html + '</span>' +
                    '<button class="notif-dismiss" onclick="dismissNotification(' + q + it.type + q + ',' + it.id + ')" title="Dismiss">&times;</button>' +
                    '</div>';
                }).join('');
            }).catch(() => {});
        }

        function dismissNotification(type, id) {
            if (type === 'alarm') {
                _dismissedAlarmIds.add(id);
                refreshNotificationBar();
            } else if (type === 'reminder') {
                fetch('/api/reminders/' + id + '/acknowledge', { method: 'POST' })
                    .then(() => refreshNotificationBar())
                    .catch(() => {});
            }
        }

        function dismissAllNotifications() {
            // Dismiss all visible notifications
            const items = document.querySelectorAll('.notification-item');
            const promises = [];
            items.forEach(item => {
                const btn = item.querySelector('.notif-dismiss');
                if (btn) {
                    const onclick = btn.getAttribute('onclick');
                    const match = onclick.match(/dismissNotification\('(\w+)',(\d+)\)/);
                    if (match) {
                        const [, type, id] = match;
                        if (type === 'alarm') {
                            _dismissedAlarmIds.add(Number(id));
                        } else if (type === 'reminder') {
                            promises.push(fetch('/api/reminders/' + id + '/acknowledge', { method: 'POST' }));
                        }
                    }
                }
            });
            if (promises.length > 0) {
                Promise.all(promises).then(() => refreshNotificationBar());
            } else {
                refreshNotificationBar();
            }
        }

        // ── Reminder Modal ──────────────────────────────────────────────
        function openReminderModal() {
            document.getElementById('reminderModal').style.display = 'flex';
            document.getElementById('reminderTicker').value = '';
            document.getElementById('reminderMessage').value = '';
            document.getElementById('reminderDueDate').value = '';
            loadReminderList();
        }
        function closeReminderModal() {
            document.getElementById('reminderModal').style.display = 'none';
        }
        function createReminder() {
            const ticker = document.getElementById('reminderTicker').value.trim();
            const message = document.getElementById('reminderMessage').value.trim();
            const due_date = document.getElementById('reminderDueDate').value;
            if (!message || !due_date) { alert('Message and due date are required'); return; }
            fetch('/api/reminders', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ ticker: ticker || null, message, due_date })
            })
            .then(r => r.json())
            .then(data => {
                if (data.ok) {
                    document.getElementById('reminderMessage').value = '';
                    loadReminderList();
                    refreshNotificationBar();
                } else {
                    alert(data.error || 'Failed to create reminder');
                }
            })
            .catch(() => alert('Failed to create reminder'));
        }
        function loadReminderList() {
            fetch('/api/reminders')
            .then(r => r.json())
            .then(data => {
                const list = document.getElementById('reminderList');
                const reminders = data.reminders || [];
                if (reminders.length === 0) {
                    list.innerHTML = '<p style="color:#738091; font-size:13px;">No reminders yet.</p>';
                    return;
                }
                list.innerHTML = reminders.map(r => {
                    const status = r.active ? (r.due_date <= new Date().toISOString().slice(0,10) ? '&#128308;' : '&#9898;') : '&#9989;';
                    return '<div style="display:flex; align-items:center; gap:8px; padding:6px 0; border-bottom:1px solid var(--border,#2a3040); font-size:13px;">' +
                        '<span>' + status + '</span>' +
                        '<span style="flex:1; color:var(--text-primary,#e0e6ed);">' +
                            (r.ticker ? '<span style="color:#58a6ff; font-weight:600;">' + r.ticker + '</span> ' : '') +
                            r.message + ' <span style="color:#738091;">(' + r.due_date + ')</span>' +
                        '</span>' +
                        '<button onclick="deleteReminder(' + r.id + ')" style="background:none; border:none; color:#f87171; cursor:pointer; font-size:14px;" title="Delete">&times;</button>' +
                    '</div>';
                }).join('');
            })
            .catch(() => {});
        }
        function deleteReminder(id) {
            fetch('/api/reminders/' + id, { method: 'DELETE' })
                .then(() => { loadReminderList(); refreshNotificationBar(); })
                .catch(() => {});
        }

        // Init notifications on page load
        // Same reason as the alarm badge above: this fetches /api/alarms/triggered
        // and /api/reminders/due, both private.
        if (SERVER_MODE) {
            refreshNotificationBar();
            setInterval(refreshNotificationBar, 60000);
        }

        // ── Insider Chart Modal ─────────────────────────────────────────
        function openInsiderChart(ticker) {
            document.getElementById('insiderModalTicker').textContent = ticker;
            document.getElementById('insiderModal').style.display = 'flex';
            document.getElementById('insiderChartContainer').innerHTML =
                '<p style="color:#738091; font-size:13px;">Loading...</p>';
            document.getElementById('insiderModalSubtitle').textContent = '';

            fetch('/api/insider/' + ticker)
                .then(r => r.json())
                .then(data => {
                    if (!data.months || data.months.length === 0) {
                        document.getElementById('insiderChartContainer').innerHTML =
                            '<p style="color:#738091;">No insider transaction data available.</p>';
                        return;
                    }
                    renderInsiderCharts(data.months, ticker);
                })
                .catch(() => {
                    document.getElementById('insiderChartContainer').innerHTML =
                        '<p style="color:#f87171;">Failed to load data.</p>';
                });
        }

        function closeInsiderModal() {
            document.getElementById('insiderModal').style.display = 'none';
        }

        function fmtDollar(v) {
            if (v >= 1e9) return '$' + (v / 1e9).toFixed(1) + 'B';
            if (v >= 1e6) return '$' + (v / 1e6).toFixed(1) + 'M';
            if (v >= 1e3) return '$' + (v / 1e3).toFixed(0) + 'K';
            return '$' + v;
        }

        function renderInsiderCharts(months, ticker) {
            const n = months.length;
            if (n === 0) return;
            const recent = months[n - 1];
            const hasComp = months.some(m => m.comp_sells > 0);
            let subtitle = months[0].month + ' to ' + recent.month + ' \u2022 Open-market transactions only';
            if (hasComp) subtitle += ' \u2022 Faded = compensation sells (option exercise + tax withholding)';
            document.getElementById('insiderModalSubtitle').textContent = subtitle;

            const container = document.getElementById('insiderChartContainer');
            container.innerHTML = renderDualBarChart(months);
        }

        function renderDualBarChart(months) {
            // Stacked bars: buys up (green), sells down split into discretionary (red) + compensation (faded)
            // Left pair = transaction count, Right pair = $ volume
            const W = 540, H = 240, padL = 36, padR = 52, padT = 24, padB = 42;
            const chartW = W - padL - padR;
            const chartH = H - padT - padB;
            const n = months.length;

            // Max values for scaling (buys go up, sells go down — not netted)
            const maxBuyCount = Math.max(1, ...months.map(m => m.buys));
            const maxSellCount = Math.max(1, ...months.map(m => m.sells));
            const maxCount = Math.max(maxBuyCount, maxSellCount);
            const maxBuyVol = Math.max(1, ...months.map(m => m.buy_vol || 0));
            const maxSellVol = Math.max(1, ...months.map(m => m.sell_vol || 0));
            const maxVol = Math.max(maxBuyVol, maxSellVol);

            const barGroupW = Math.min(50, chartW / n);
            const barW = Math.max(4, (barGroupW - 6) / 2);
            const totalW = barGroupW * n;
            const fullW = Math.max(W, totalW + padL + padR);
            const midY = padT + chartH / 2;
            const halfH = chartH / 2;

            let svg = '<svg width="' + fullW + '" height="' + H + '" xmlns="http://www.w3.org/2000/svg">';

            // Legend
            const hasComp = months.some(m => (m.comp_sells || 0) > 0);
            const legY = 10;
            svg += '<rect x="' + padL + '" y="' + (legY-4) + '" width="8" height="8" fill="#34d399" rx="1"/>';
            svg += '<text x="' + (padL+11) + '" y="' + (legY+4) + '" fill="#738091" font-size="9" font-family="Geist Mono,monospace">Buys</text>';
            svg += '<rect x="' + (padL+42) + '" y="' + (legY-4) + '" width="8" height="8" fill="#e76a6e" rx="1"/>';
            svg += '<text x="' + (padL+53) + '" y="' + (legY+4) + '" fill="#738091" font-size="9" font-family="Geist Mono,monospace">Sells</text>';
            if (hasComp) {
                svg += '<rect x="' + (padL+88) + '" y="' + (legY-4) + '" width="8" height="8" fill="#e76a6e" rx="1" opacity="0.3"/>';
                svg += '<text x="' + (padL+99) + '" y="' + (legY+4) + '" fill="#738091" font-size="9" font-family="Geist Mono,monospace">Comp (vesting)</text>';
            }

            // Grid lines
            const steps = 2;
            for (let i = 1; i <= steps; i++) {
                const frac = i / steps;
                const yUp = midY - halfH * frac;
                svg += '<line x1="' + padL + '" y1="' + yUp + '" x2="' + (padL + Math.max(chartW, totalW)) +
                       '" y2="' + yUp + '" stroke="#2a3040" stroke-width="1"/>';
                svg += '<text x="' + (padL - 4) + '" y="' + (yUp + 4) +
                       '" fill="#738091" font-size="9" text-anchor="end" font-family="Geist Mono,monospace">' + Math.round(maxCount * frac) + '</text>';
                svg += '<text x="' + (padL + Math.max(chartW, totalW) + 4) + '" y="' + (yUp + 4) +
                       '" fill="#738091" font-size="9" font-family="Geist Mono,monospace">' + fmtDollar(maxVol * frac) + '</text>';
                const yDn = midY + halfH * frac;
                svg += '<line x1="' + padL + '" y1="' + yDn + '" x2="' + (padL + Math.max(chartW, totalW)) +
                       '" y2="' + yDn + '" stroke="#2a3040" stroke-width="1"/>';
                svg += '<text x="' + (padL - 4) + '" y="' + (yDn + 4) +
                       '" fill="#738091" font-size="9" text-anchor="end" font-family="Geist Mono,monospace">' + Math.round(maxCount * frac) + '</text>';
                svg += '<text x="' + (padL + Math.max(chartW, totalW) + 4) + '" y="' + (yDn + 4) +
                       '" fill="#738091" font-size="9" font-family="Geist Mono,monospace">' + fmtDollar(maxVol * frac) + '</text>';
            }

            // Zero axis
            svg += '<line x1="' + padL + '" y1="' + midY + '" x2="' + (padL + Math.max(chartW, totalW)) +
                   '" y2="' + midY + '" stroke="#4a5568" stroke-width="1.5"/>';

            // Bars — stacked: buys go UP, sells go DOWN with comp portion faded
            months.forEach((m, i) => {
                const x = padL + i * barGroupW + 3;
                const compSells = m.comp_sells || 0;
                const discSells = m.sells - compSells;
                const compVol = m.comp_sell_vol || 0;
                const discVol = (m.sell_vol || 0) - compVol;

                // COUNT bars (left)
                // Buys (green, going up)
                if (m.buys > 0) {
                    const h = m.buys / maxCount * halfH;
                    svg += '<rect x="' + x + '" y="' + (midY - h) + '" width="' + barW + '" height="' + h +
                           '" fill="#34d399" rx="1.5" opacity="0.9"/>';
                }
                // Discretionary sells (solid red, going down)
                if (discSells > 0) {
                    const h = discSells / maxCount * halfH;
                    svg += '<rect x="' + x + '" y="' + midY + '" width="' + barW + '" height="' + h +
                           '" fill="#e76a6e" rx="1.5" opacity="0.9"/>';
                    // Compensation sells stacked below (faded red)
                    if (compSells > 0) {
                        const ch = compSells / maxCount * halfH;
                        svg += '<rect x="' + x + '" y="' + (midY + h) + '" width="' + barW + '" height="' + ch +
                               '" fill="#e76a6e" rx="1.5" opacity="0.3"/>';
                    }
                } else if (compSells > 0) {
                    // Only compensation sells, no discretionary
                    const ch = compSells / maxCount * halfH;
                    svg += '<rect x="' + x + '" y="' + midY + '" width="' + barW + '" height="' + ch +
                           '" fill="#e76a6e" rx="1.5" opacity="0.3"/>';
                }

                // VOLUME bars (right)
                if ((m.buy_vol || 0) > 0) {
                    const h = m.buy_vol / maxVol * halfH;
                    svg += '<rect x="' + (x + barW + 2) + '" y="' + (midY - h) + '" width="' + barW + '" height="' + h +
                           '" fill="#63e2c6" rx="1.5" opacity="0.7"/>';
                }
                if (discVol > 0) {
                    const h = discVol / maxVol * halfH;
                    svg += '<rect x="' + (x + barW + 2) + '" y="' + midY + '" width="' + barW + '" height="' + h +
                           '" fill="#f0a0a0" rx="1.5" opacity="0.7"/>';
                    if (compVol > 0) {
                        const ch = compVol / maxVol * halfH;
                        svg += '<rect x="' + (x + barW + 2) + '" y="' + (midY + h) + '" width="' + barW + '" height="' + ch +
                               '" fill="#f0a0a0" rx="1.5" opacity="0.25"/>';
                    }
                } else if (compVol > 0) {
                    const ch = compVol / maxVol * halfH;
                    svg += '<rect x="' + (x + barW + 2) + '" y="' + midY + '" width="' + barW + '" height="' + ch +
                           '" fill="#f0a0a0" rx="1.5" opacity="0.25"/>';
                }

                // X-axis labels
                const showLabel = n <= 14 || i % 2 === 0 || i === n - 1;
                if (showLabel) {
                    const parts = m.month.split('-');
                    const lbl = parts[1] + '/' + parts[0].slice(2);
                    svg += '<text x="' + (x + barW) + '" y="' + (H - padB + 14) +
                           '" fill="#738091" font-size="9" text-anchor="middle" font-family="Geist Mono,monospace"' +
                           ' transform="rotate(-35,' + (x + barW) + ',' + (H - padB + 14) + ')">' + lbl + '</text>';
                }
            });

            // Legend
            svg += '<rect x="' + padL + '" y="' + (H - 14) + '" width="8" height="8" fill="#34d399" rx="1"/>';
            svg += '<text x="' + (padL + 11) + '" y="' + (H - 7) + '" fill="#a0aec0" font-size="9" font-family="Geist Mono,monospace">Net count</text>';
            svg += '<rect x="' + (padL + 80) + '" y="' + (H - 14) + '" width="8" height="8" fill="#63e2c6" rx="1" opacity="0.7"/>';
            svg += '<text x="' + (padL + 91) + '" y="' + (H - 7) + '" fill="#a0aec0" font-size="9" font-family="Geist Mono,monospace">Net $ volume</text>';
            svg += '<text x="' + (padL + Math.max(chartW, totalW) + 4) + '" y="' + (midY + 4) +
                   '" fill="#738091" font-size="9" font-family="Geist Mono,monospace">$0</text>';

            // Axis labels
            svg += '<text x="' + (padL - 4) + '" y="12" fill="#738091" font-size="9" text-anchor="end" font-family="Geist Mono,monospace" opacity="0.6"># txns</text>';
            svg += '<text x="' + (padL + Math.max(chartW, totalW) + 4) + '" y="12" fill="#738091" font-size="9" font-family="Geist Mono,monospace" opacity="0.6">$ vol</text>';

            svg += '</svg>';
            return svg;
        }"""

    # ── Doomscroll Insights Feed ─────────────────────────────────────────

    def generate_feed_html(self, stocks_data: Dict, notes_dir: str = None,
                           policy_markets: List[Dict] = None) -> str:
        """Generate the doomscroll insights feed — bite-sized investing posts.

        Parameters
        ----------
        stocks_data : Dict
            Per-ticker valuations and metadata (existing pipeline).
        notes_dir : str
            Path to notes/companies markdown directory.
        policy_markets : List[Dict]
            Optional list of Polymarket Trump-policy markets with deltas.
            Rendered as a separate top section.
        """
        import re
        if notes_dir is None:
            notes_dir = str(Path(__file__).parent.parent.parent.parent / "notes" / "companies")
        posts = self._generate_feed_posts(stocks_data, notes_dir)
        cards_html = self._render_feed_with_sections(posts)
        policy_html = self._render_policy_markets(policy_markets) if policy_markets else ""
        cards_html = policy_html + cards_html

        # Real-time Trump signal cards (fetched fresh on each render so
        # newly-arrived posts surface within seconds of the next page load).
        # Defensive: any DB or import error returns an empty string so the
        # feed never breaks if Postgres / the truthsocial table is down.
        known_tickers = set(stocks_data.keys()) if stocks_data else set()
        trump_html = self._render_trump_signal_cards(known_tickers)
        if trump_html:
            cards_html = trump_html + cards_html

        return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="theme-color" content="#111418">
<title>Feed</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600;9..40,700&family=Geist+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root {{
    --bg: #111418; --panel: #1c2127; --elevated: #252a31;
    --border: rgba(255,255,255,0.08); --border-hover: rgba(255,255,255,0.15);
    --t1: #f6f7f9; --t2: #abb3bf; --t3: #738091;
    --blue: #4c90f0; --green: #72ca9b; --red: #e76a6e; --gold: #f0b726; --cyan: #63e2c6;
    --green-bg: rgba(50,164,103,0.12); --red-bg: rgba(205,66,70,0.10);
    --gold-bg: rgba(209,152,11,0.10); --blue-bg: rgba(76,144,240,0.10);
    --cyan-bg: rgba(99,226,198,0.08);
    --sans: 'DM Sans', -apple-system, sans-serif;
    --mono: 'Geist Mono', monospace;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background: var(--bg); color: var(--t1); font-family: var(--sans); -webkit-font-smoothing: antialiased; }}
.feed {{ max-width: 620px; margin: 0 auto; padding: 20px 16px 100px; }}
.feed-nav {{ display: flex; justify-content: space-between; align-items: center; padding: 10px 0 20px; }}
.feed-nav h1 {{ font-size: 22px; font-weight: 700; }}
.feed-nav a {{ color: var(--t3); text-decoration: none; font: 500 14px var(--mono); }}
.feed-nav a:hover {{ color: var(--blue); }}

/* Thread container */
.thread {{ background: var(--panel); border: 1px solid var(--border); border-radius: 14px;
           padding: 22px 24px 14px; margin-bottom: 14px; transition: border-color 0.2s, box-shadow 0.2s;
           border-left: 3px solid var(--thread-heat, var(--border)); position: relative;
           overflow: hidden; }}
.thread::before {{ content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 60px;
                   background: linear-gradient(90deg, var(--thread-glow, transparent), transparent);
                   pointer-events: none; opacity: 0.5; }}
.thread:hover {{ border-color: var(--border-hover); box-shadow: 0 4px 20px rgba(0,0,0,0.3); }}
.thread:hover::before {{ opacity: 0.8; }}
.thread-head {{ display: flex; align-items: center; gap: 10px; margin-bottom: 0; cursor: pointer; user-select: none; }}
.thread.open .thread-head {{ margin-bottom: 16px; }}
.thread-ticker {{ font: 700 22px var(--mono); color: var(--t1); }}
.thread-name {{ font-size: 14px; color: var(--t3); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.thread-ev {{ font: 700 18px var(--mono); display: none; }}
.thread-ev.pos {{ color: var(--green); }}
.thread-ev.neg {{ color: var(--red); }}
.thread-chevron {{ color: var(--t3); font-size: 18px; transition: transform 0.25s ease; flex-shrink: 0; margin-left: auto; }}
.thread.open .thread-chevron {{ transform: rotate(180deg); }}
.thread-body {{ display: none; }}
.thread.open .thread-body {{ display: block; }}
.thread-more {{ display: block; text-align: right; font: 500 13px var(--mono); color: var(--blue);
                text-decoration: none; padding: 8px 0 4px; border-top: 1px solid var(--border); margin-top: 8px; }}
.thread-more:hover {{ color: var(--t1); }}

/* Collapsed layout — two-column: text left, big EV% spark right */
.thread-collapsed {{ display: flex; gap: 16px; margin-top: 10px; }}
.thread.open .thread-collapsed {{ display: none; }}
.thread-left {{ flex: 1; min-width: 0; }}

/* Preview text — hook + tease pattern */
.thread-hook {{ font-size: 14.5px; line-height: 1.45; color: var(--t1); font-weight: 600;
               display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }}
.thread-tease {{ font-size: 13px; line-height: 1.5; color: var(--t3); margin-top: 4px;
                display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }}
.thread-post-count {{ font: 500 11px var(--mono); color: var(--t3); margin-top: 6px;
                     display: flex; align-items: center; gap: 5px; }}
.thread-post-count::before {{ content: ''; display: inline-block; width: 4px; height: 4px;
                             border-radius: 50%; background: var(--blue); opacity: 0.7; }}
/* Legacy compat */
.thread-preview {{ font-size: 14px; line-height: 1.55; color: var(--t2);
                   display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }}

/* Big EV spark — the dopamine hit */
.thread-spark {{ display: flex; flex-direction: column; align-items: center; justify-content: center;
                 flex-shrink: 0; min-width: 80px; padding: 8px 12px; border-radius: 10px;
                 background: var(--spark-bg, var(--elevated)); position: relative; overflow: hidden;
                 border: 1px solid var(--spark-border, var(--border)); }}
.thread-spark::before {{ content: ''; position: absolute; inset: 0;
                         background: radial-gradient(circle at center, var(--spark-glow, transparent), transparent 70%);
                         opacity: 0.8; pointer-events: none; }}
.spark-val {{ font: 800 28px var(--mono); letter-spacing: -1px; position: relative; z-index: 1; }}
.spark-val.pos {{ color: var(--green); }}
.spark-val.neg {{ color: var(--red); }}
.spark-label {{ font: 500 10px var(--mono); color: var(--t3); text-transform: uppercase; letter-spacing: 0.5px;
                margin-top: 2px; position: relative; z-index: 1; }}
.thread.featured .spark-val {{ font-size: 34px; }}
.thread.featured .thread-spark {{ min-width: 96px; padding: 10px 16px; }}

/* Inline heat bar — visual conviction meter next to EV% */
.thread-heat-bar {{ display: flex; align-items: center; gap: 6px; margin-left: 2px; }}
.heat-track {{ width: 48px; height: 6px; background: var(--elevated); border-radius: 3px; overflow: hidden; flex-shrink: 0; }}
.heat-fill {{ height: 100%; border-radius: 3px; transition: width 0.4s ease; }}
.heat-fill.heat-green {{ background: linear-gradient(90deg, rgba(114,202,155,0.7), var(--green)); }}
.heat-fill.heat-red {{ background: linear-gradient(90deg, rgba(231,106,110,0.7), var(--red)); }}

/* Price vs Entry — deal-hunting indicator */
.thread-entry-gauge {{ display: flex; align-items: center; gap: 8px; margin-top: 10px; }}
.entry-label {{ font: 500 10px var(--mono); color: var(--t3); text-transform: uppercase; letter-spacing: 0.5px; white-space: nowrap; }}
.entry-bar-wrap {{ flex: 1; position: relative; height: 16px; display: flex; align-items: center; }}
.entry-bar-track {{ width: 100%; height: 4px; background: var(--elevated); border-radius: 2px; position: relative; }}
.entry-bar-marker {{ position: absolute; top: 50%; width: 1px; height: 12px; background: var(--t3);
                     transform: translateY(-50%); opacity: 0.5; }}
.entry-bar-fill {{ position: absolute; left: 0; top: 0; height: 100%; border-radius: 2px; }}
.entry-bar-fill.at-discount {{ background: linear-gradient(90deg, rgba(114,202,155,0.4), var(--green)); }}
.entry-bar-fill.at-premium {{ background: linear-gradient(90deg, rgba(231,106,110,0.4), var(--red)); }}
.entry-delta {{ font: 700 12px var(--mono); white-space: nowrap; }}
.entry-delta.discount {{ color: var(--green); }}
.entry-delta.premium {{ color: var(--red); }}

/* Key metric pills shown in collapsed state */
.thread-metrics {{ display: flex; gap: 6px; margin-top: 8px; flex-wrap: wrap; }}
/* thread-metrics hidden via .thread-collapsed parent */
.thread-metric {{ font: 600 11px var(--mono); padding: 3px 8px; border-radius: 4px; background: var(--elevated); color: var(--t2); }}
.thread-metric .mv {{ font-weight: 700; }}
.thread-metric .mv.pos {{ color: var(--green); }}
.thread-metric .mv.neg {{ color: var(--red); }}
.thread-metric .mv.gold {{ color: var(--gold); }}

/* Featured top picks — visual hierarchy */
.thread.featured {{
    background: linear-gradient(135deg, rgba(50,164,103,0.06) 0%, var(--panel) 40%, rgba(76,144,240,0.04) 100%);
    border: 1px solid rgba(114,202,155,0.18);
    border-left: 4px solid rgba(114,202,155,0.9);
    box-shadow: 0 0 24px rgba(50,164,103,0.08), inset 0 1px 0 rgba(255,255,255,0.03);
    padding: 26px 28px 16px;
    margin-bottom: 18px;
}}
.thread.featured .thread-ticker {{ font-size: 26px; }}
.thread.featured .thread-ev {{ font-size: 24px; }}
.thread.featured .thread-preview {{ font-size: 15px; -webkit-line-clamp: 3; color: var(--t2); }}
.thread.featured .thread-head {{ gap: 12px; }}

/* Rank badge for top picks */
.thread-rank {{ display: inline-flex; align-items: center; justify-content: center;
                width: 22px; height: 22px; border-radius: 50%; font: 700 11px var(--mono);
                background: rgba(114,202,155,0.15); color: var(--green); flex-shrink: 0; }}
.thread:not(.featured) .thread-rank {{ display: none; }}

/* Thread post (connected timeline) */
.tp {{ display: flex; gap: 14px; position: relative; padding-bottom: 16px; }}
.tp::before {{ content: ''; position: absolute; left: 5px; top: 14px; bottom: 0; width: 1px; background: var(--border); }}
.tp.tp-last::before {{ display: none; }}
.tp-dot {{ width: 11px; height: 11px; border-radius: 50%; flex-shrink: 0; margin-top: 3px;
           background: var(--t3); border: 2px solid var(--panel); }}
.tp-dot.tag-verdict {{ background: var(--green); }}
.tp-dot.tag-thesis  {{ background: var(--blue); }}
.tp-dot.tag-bull    {{ background: var(--green); }}
.tp-dot.tag-bear    {{ background: var(--red); }}
.tp-dot.tag-numbers {{ background: var(--cyan); }}
.tp-dot.tag-signal  {{ background: var(--gold); }}
.tp-dot.tag-intro   {{ background: var(--t3); }}
.tp-content {{ flex: 1; min-width: 0; }}
.tp-tag {{ font: 700 10px/1 var(--mono); padding: 2px 7px; border-radius: 3px; text-transform: uppercase;
           letter-spacing: 0.5px; display: inline-block; margin-bottom: 6px; }}

.post-tag {{ font: 700 11px/1 var(--mono); padding: 4px 9px; border-radius: 4px; text-transform: uppercase; letter-spacing: 0.5px; flex-shrink: 0; }}
.tag-thesis  {{ background: var(--blue-bg);  color: var(--blue); }}
.tag-bull    {{ background: var(--green-bg); color: var(--green); }}
.tag-bear    {{ background: var(--red-bg);   color: var(--red); }}
.tag-numbers {{ background: var(--cyan-bg);  color: var(--cyan); }}
.tag-signal  {{ background: var(--gold-bg);  color: var(--gold); }}
.tag-verdict {{ background: var(--green-bg); color: var(--green); }}
.tag-intro   {{ background: rgba(171,179,191,0.08); color: var(--t3); }}

/* Hero stat — big prominent number */
.post-hero {{ display: flex; align-items: baseline; gap: 8px; margin-bottom: 8px; }}
.hero-val {{ font: 700 28px var(--mono); }}
.hero-val.pos {{ color: var(--green); }}
.hero-val.neg {{ color: var(--red); }}
.hero-label {{ font: 500 13px var(--mono); color: var(--t3); }}

/* Featured card — top picks get visual prominence */
.post.featured {{
    background: linear-gradient(135deg, rgba(50,164,103,0.08) 0%, var(--panel) 50%, rgba(76,144,240,0.06) 100%);
    border: 1px solid rgba(114,202,155,0.20);
    border-left: 4px solid var(--green);
    padding: 24px 26px;
}}
.post.featured .post-ticker {{ font-size: 22px; }}
.post.featured .hero-val {{ font-size: 36px; }}
.post.featured .post-body {{ font-size: 16px; }}

/* Confidence bar — visual quality indicator */
.conf-bar {{ display: flex; align-items: center; gap: 8px; margin-top: 14px; }}
.conf-track {{ flex: 1; height: 4px; background: var(--elevated); border-radius: 2px; overflow: hidden; }}
.conf-fill {{ height: 100%; border-radius: 2px; transition: width 0.3s; }}
.conf-fill.high {{ background: var(--green); }}
.conf-fill.mid {{ background: var(--gold); }}
.conf-fill.low {{ background: var(--red); }}
.conf-label {{ font: 500 11px var(--mono); color: var(--t3); white-space: nowrap; }}

.post-body {{ font-size: 15px; line-height: 1.6; color: var(--t2); }}
.post-body b, .post-body strong {{ color: var(--t1); font-weight: 600; }}
.post-body .hl {{ color: var(--t1); font-family: var(--mono); font-weight: 600; }}

.pills {{ display: flex; flex-wrap: wrap; gap: 7px; margin-top: 12px; }}
.pill {{ font: 500 12px var(--mono); padding: 4px 10px; border-radius: 6px;
         background: var(--elevated); color: var(--t2); }}
.pill .v {{ color: var(--t1); font-weight: 600; }}
.pill .pos {{ color: var(--green); font-weight: 600; }}
.pill .neg {{ color: var(--red); font-weight: 600; }}

.section-sep {{ display: flex; align-items: center; gap: 12px; padding: 22px 0 10px; }}
.section-sep span {{ font: 700 12px var(--mono); text-transform: uppercase; letter-spacing: 2px; color: var(--t3); white-space: nowrap; }}
.section-sep::after {{ content: ''; flex: 1; height: 1px; background: var(--border); }}
</style>
</head>
<body>
<div class="feed">
    <div class="feed-nav">
        <h1>Feed</h1>
        <a href="/">Dashboard</a>
    </div>
    {cards_html}
</div>
<script>
document.querySelectorAll('.thread-head').forEach(h => {{
    h.addEventListener('click', () => {{
        h.closest('.thread').classList.toggle('open');
    }});
}});
// Only #1 pick auto-expands; rest stay collapsed for doomscroll density
</script>
</body>
</html>'''

    def _parse_md_sections(self, filepath: str) -> Dict[str, str]:
        """Parse a company .md file into section name -> content dict."""
        import re
        try:
            text = Path(filepath).read_text(encoding="utf-8")
        except (FileNotFoundError, OSError):
            return {}
        sections = {}
        current = None
        lines = []
        for line in text.split("\n"):
            m = re.match(r"^##\s+(.+)", line)
            if m:
                if current:
                    sections[current] = "\n".join(lines).strip()
                current = m.group(1).strip()
                lines = []
            elif current:
                lines.append(line)
        if current:
            sections[current] = "\n".join(lines).strip()
        # Also grab the header line (# Title)
        header_match = re.match(r"^#\s+(.+)", text.split("\n")[0]) if text else None
        if header_match:
            # Get sector/industry from the ** lines
            for line in text.split("\n")[1:6]:
                if line.startswith("**Sector"):
                    sections["_header"] = line
                    break
        return sections

    def _first_sentences(self, text: str, n: int = 3, max_chars: int = 400) -> str:
        """Extract first n sentences from text, cleaning markdown. Keeps it punchy."""
        import re
        # Remove markdown links, bold markers, pipe tables, bullet prefixes
        clean = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        clean = re.sub(r'\*\*([^*]+)\*\*', r'\1', clean)
        clean = re.sub(r'\*([^*]+)\*', r'\1', clean)  # italic *text*
        clean = re.sub(r'\|[^\n]+\|', '', clean)
        clean = re.sub(r'^[-*]\s+', '', clean, flags=re.MULTILINE)
        clean = re.sub(r'\n+', ' ', clean).strip()
        clean = re.sub(r'\s+', ' ', clean)
        # Split on sentence boundaries
        parts = re.split(r'(?<=[.!?])\s+', clean)
        result = " ".join(parts[:n]).strip()
        # Truncate if still too long
        if len(result) > max_chars:
            result = result[:max_chars].rsplit(' ', 1)[0] + "\u2026"
        return result if result else clean[:max_chars]

    def _bullet_items(self, text: str, n: int = 3) -> List[str]:
        """Extract first n bullet points from markdown text."""
        import re
        items = []
        for line in text.split("\n"):
            m = re.match(r'^[-*]\s+(.+)', line)
            if m:
                # Clean markdown formatting
                item = re.sub(r'\*\*([^*]+)\*\*', r'\1', m.group(1))
                item = re.sub(r'\*([^*]+)\*', r'\1', item)  # italic *text*
                items.append(item.strip())
                if len(items) >= n:
                    break
        return items

    def _num(self, val: str, positive: bool = True) -> str:
        """Wrap a number in styled span."""
        cls = "pos" if positive else "neg"
        return f'<span class="num {cls}">{html.escape(val)}</span>'

    def _generate_feed_posts(self, stocks_data: Dict, notes_dir: str) -> List[Dict]:
        """Generate bite-sized feed posts from stock data + .md analysis files."""
        posts = []
        notes_path = Path(notes_dir)

        for ticker, stock in stocks_data.items():
            name = stock.get("company_name", ticker)
            price = stock.get("current_price")
            valuations = stock.get("valuations", {})
            insider = stock.get("insider", {})
            llm = valuations.get("llm_deep_analysis", {})
            llm_details = llm.get("details", {})
            verdict = llm_details.get("verdict")
            ev_pct = llm_details.get("expected_value_pct")
            quality = llm_details.get("quality_score")
            entry_price = llm_details.get("entry_price")

            # Only include stocks with rich .md analysis files
            md_file = notes_path / f"{ticker}.md"
            sections = self._parse_md_sections(str(md_file))
            if not sections:
                continue  # Skip stocks without .md — no rich content for the feed

            # --- INTRO: What the company does ---
            # Try Business Quality moat line first (describes the actual business),
            # fall back to Situation Summary if not available
            intro = ""
            bq = ""
            for key in sections:
                if key.startswith("Business Quality"):
                    bq = sections[key]
                    break
            for line in bq.split("\n"):
                if "Moat" in line and "|" in line:
                    parts = line.split("|")
                    if len(parts) >= 4:
                        moat_desc = parts[3].strip()
                        if moat_desc:
                            intro = self._first_sentences(moat_desc, 3, 400)
                    break
            if not intro:
                situation = sections.get("Situation Summary", "")
                if situation:
                    intro = self._first_sentences(situation, 3, 400)
            if intro:
                pills = []
                if price:
                    pills.append(("Price", f"${price:.2f}", ""))
                if ev_pct:
                    pills.append(("EV", f"{ev_pct:+.0f}%", "pos" if ev_pct > 0 else "neg"))
                if quality:
                    q_str = str(quality)
                    pills.append(("Quality", q_str if "/25" in q_str else f"{q_str}/25", ""))
                posts.append({
                    "priority": 200 if verdict == "BUY" else 100 if verdict == "WATCH" else 50,
                    "type": "intro", "tag": "What they do",
                    "ticker": ticker, "name": name,
                    "body": intro, "pills": pills,
                })

            # --- THESIS: Why it's interesting (variant perception) ---
            variant_section = sections.get("Variant Perception", "")
            if variant_section:
                # Extract "Our view" specifically
                our_view = ""
                for line in variant_section.split("\n"):
                    if "Our view" in line or "our view" in line:
                        our_view = line.lstrip("- ").replace("**Our view:**", "").replace("**Our view:** ", "").strip()
                        break
                if our_view:
                    thesis = self._first_sentences(our_view, 3, 400)
                    posts.append({
                        "priority": 190 if verdict == "BUY" else 90,
                        "type": "thesis", "tag": "The Edge",
                        "ticker": ticker, "name": name,
                        "body": thesis, "pills": [],
                    })

            # --- BULL CASE ---
            bull = sections.get("Bull Case", "")
            if bull:
                items = self._bullet_items(bull, 2)
                if items:
                    # Ensure each item ends with a period
                    items = [i.rstrip(".") + "." for i in items]
                    posts.append({
                        "priority": 180 if verdict == "BUY" else 80,
                        "type": "bull", "tag": "Bull case",
                        "ticker": ticker, "name": name,
                        "body": " ".join(items), "pills": [],
                    })

            # --- BEAR CASE / RISKS ---
            bear = sections.get("Bear Case", "")
            if bear:
                items = self._bullet_items(bear, 2)
                if items:
                    items = [i.rstrip(".") + "." for i in items]
                    posts.append({
                        "priority": 170 if verdict == "BUY" else 75,
                        "type": "bear", "tag": "Key risk",
                        "ticker": ticker, "name": name,
                        "body": " ".join(items), "pills": [],
                    })

            # --- KEY NUMBERS ---
            financials = sections.get("Financial Snapshot", "")
            if financials and price:
                # Extract interesting numbers from the table
                pills = []
                if price:
                    pills.append(("Price", f"${price:.2f}", ""))
                if ev_pct:
                    pills.append(("EV", f"{ev_pct:+.0f}%", "pos" if ev_pct > 0 else "neg"))
                if entry_price:
                    pills.append(("Entry", f"${entry_price}", ""))
                observations = ""
                for line in financials.split("\n"):
                    if line.startswith("- ") or line.startswith("* "):
                        observations = line.lstrip("-* ").strip()
                        break
                if observations:
                    posts.append({
                        "priority": 160 if verdict == "BUY" else 70,
                        "type": "numbers", "tag": "By the numbers",
                        "ticker": ticker, "name": name,
                        "body": observations, "pills": pills,
                    })

            # --- POLITICIAN SIGNAL (House PTRs — gated per (politician, direction)) ---
            # Emit one post per (politician, direction) pair that has at least
            # one trade. The boundary filter _apply_signal_gates() drops any
            # post without a curated entry in src/invest/signals/gates.py, so
            # unbacktested politicians vanish here. See notes/research/
            # signal_inventory.md for current gate status.
            politician = stock.get("politician", {})
            if politician.get("has_data"):
                for entry in politician.get("top_politicians", []):
                    raw_name = entry.get("name", "")
                    if not raw_name:
                        continue
                    display_name = raw_name.split(",")[0].strip() if "," in raw_name else raw_name
                    weight = entry.get("weight", 1.0)
                    for direction in ("P", "S"):
                        count = entry.get("buys" if direction == "P" else "sells", 0)
                        if count <= 0:
                            continue
                        action = "purchase" if direction == "P" else "sale"
                        body = (
                            f"{display_name} disclosed {count} {action}"
                            f"{'s' if count > 1 else ''} of {ticker} in the last 6 months "
                            "(House PTR). Disclosure lag up to 45d — treat as a "
                            "watchlist trigger, not a timing signal."
                        )
                        hero_label = "purchases" if direction == "P" else "sales"
                        hero = (str(count), hero_label, "pos" if direction == "P" else "neg")
                        priority_base = 175 if direction == "P" else 180
                        posts.append({
                            "priority": priority_base + min(weight * 5, 25),
                            "type": "signal", "tag": "Congress signal",
                            "ticker": ticker, "name": name,
                            "hero": hero, "body": body, "pills": [],
                            "signal_source": "politician",
                            "signal_name": raw_name,
                            "signal_kind": direction,
                        })

            # --- INSIDER SIGNAL (top 10 by dollar volume, show dollar amount as hero) ---
            buy_count = insider.get("buy_count", 0)
            dollars = insider.get("dollar_conviction", 0)
            if buy_count >= 2 and dollars >= 100_000:
                dollar_str = f"${dollars / 1_000_000:.1f}M" if dollars >= 1_000_000 else f"${dollars / 1_000:.0f}K"
                body = f"{buy_count} open-market purchases over the past 6 months."
                if insider.get("sell_trend") and insider["sell_trend"] < 0.8:
                    body += f" Meanwhile, selling is just {insider['sell_trend']:.0%} of its historical average."
                elif insider.get("sell_trend") and insider["sell_trend"] > 1.5:
                    body += f" But selling is {insider['sell_trend']:.0%} of normal \u2014 mixed signal."
                hero = (dollar_str, "insider buying", "pos")
                posts.append({
                    "priority": 190 + min(dollars / 100_000, 50),  # rank by dollar conviction
                    "type": "signal", "tag": "Insider signal",
                    "ticker": ticker, "name": name,
                    "hero": hero, "body": body, "pills": [],
                    "signal_source": "insider",
                    "signal_name": "cluster_buy",
                    "signal_kind": None,
                })

            # --- VERDICT ---
            verdict_section = sections.get("Verdict", "")
            if verdict_section and verdict:
                # Skip the first line if it's the verdict label
                lines = verdict_section.split("\n")
                text_start = 1 if lines and lines[0].startswith("**") else 0
                verdict_text = self._first_sentences("\n".join(lines[text_start:]), 3, 400)
                pills = []
                if entry_price:
                    pills.append(("Entry", f"${entry_price}", ""))
                if quality:
                    q_str = str(quality)
                    pills.append(("Quality", q_str if "/25" in q_str else f"{q_str}/25", ""))
                hero = None
                if ev_pct:
                    hero = (f"{ev_pct:+.0f}%", "expected value", "pos" if ev_pct > 0 else "neg")
                posts.append({
                    "priority": 210 if verdict == "BUY" else 95 if verdict == "WATCH" else 30,
                    "type": "verdict", "tag": verdict,
                    "ticker": ticker, "name": name,
                    "hero": hero, "body": verdict_text, "pills": pills,
                })

        # Apply the alpha gate to trade-signal posts. Anything without a
        # curated entry in src/invest/signals/gates.py is dropped here;
        # surviving posts carry post['gate'] for inline annotation.
        from invest.signals.gates import apply_signal_gates
        posts = apply_signal_gates(posts)

        # Cap signals to top 10 by priority (avoid 30+ insider cards)
        signal_posts = [p for p in posts if p["type"] == "signal"]
        signal_posts.sort(key=lambda p: p["priority"], reverse=True)
        signal_cut = set(id(p) for p in signal_posts[10:])
        posts = [p for p in posts if id(p) not in signal_cut]

        # Sort by priority, then interleave by ticker to avoid clustering
        posts.sort(key=lambda p: p["priority"], reverse=True)

        # Interleave: avoid showing 5 posts about the same ticker in a row
        result = []
        seen_recent: dict = {}  # ticker -> count of posts in last N
        remaining = list(posts)
        while remaining:
            placed = False
            for i, post in enumerate(remaining):
                t = post["ticker"]
                recent_count = seen_recent.get(t, 0)
                if recent_count < 2 or len(remaining) <= 5:
                    result.append(post)
                    remaining.pop(i)
                    # Update recent tracking
                    seen_recent[t] = recent_count + 1
                    # Decay: reduce counts for all tickers
                    if len(result) % 3 == 0:
                        seen_recent = {k: max(0, v - 1) for k, v in seen_recent.items()}
                    placed = True
                    break
            if not placed:
                # Fallback: just append the next one
                result.append(remaining.pop(0))

        return result

    def _render_trump_signal_cards(
        self,
        known_tickers: set,
        lookback_hours: int = 48,
        limit: int = 10,
    ) -> str:
        """
        Render Trump (Truth Social) signal cards for the top of the feed.

        Returns empty string on any failure (DB down, table missing, import
        error) so the rest of the feed always renders.

        Each card shows:
        - timestamp (relative + absolute)
        - post text (truncated to ~280 chars)
        - extracted entity tags: tickers (linked if in our universe),
          sectors, countries
        """
        try:
            from invest.data.db import get_connection
            from invest.data.truth_social_db import get_recent_posts
        except Exception:
            return ""

        try:
            conn = get_connection()
        except Exception:
            return ""

        try:
            posts = get_recent_posts(
                conn,
                lookback_hours=lookback_hours,
                limit=limit,
                require_signal=True,
            )
        except Exception:
            posts = []
        finally:
            try:
                conn.close()
            except Exception:
                pass

        if not posts:
            return ""

        from datetime import datetime, timezone

        def _relative_time(iso_ts: str) -> str:
            try:
                if iso_ts.endswith('Z'):
                    iso_ts = iso_ts[:-1] + '+00:00'
                dt = datetime.fromisoformat(iso_ts)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                delta = datetime.now(timezone.utc) - dt
                hours = delta.total_seconds() / 3600
                if hours < 1:
                    minutes = max(1, int(delta.total_seconds() / 60))
                    return f"{minutes}m ago"
                if hours < 24:
                    return f"{int(hours)}h ago"
                return f"{int(hours / 24)}d ago"
            except (ValueError, TypeError):
                return iso_ts

        parts: List[str] = []
        parts.append(
            '<div class="section-sep"><span>Trump signal</span></div>'
        )

        for post in posts:
            text = post.get('text', '') or ''
            display_text = text if len(text) <= 280 else text[:277].rstrip() + '…'
            tickers = post.get('extracted_tickers', []) or []
            sectors = post.get('extracted_sectors', []) or []
            countries = post.get('extracted_countries', []) or []
            posted_at = post.get('posted_at', '')
            rel_time = _relative_time(posted_at) if posted_at else ''

            tag_parts: List[str] = []
            for t in tickers:
                in_universe = t in known_tickers
                cls = 'tag-numbers' if in_universe else 'tag-intro'
                tag_parts.append(
                    f'<span class="post-tag {cls}">${html.escape(t)}</span>'
                )
            for s in sectors:
                tag_parts.append(
                    f'<span class="post-tag tag-thesis">{html.escape(s)}</span>'
                )
            for c in countries:
                tag_parts.append(
                    f'<span class="post-tag tag-bear">{html.escape(c)}</span>'
                )

            tags_html = ''
            if tag_parts:
                tags_html = (
                    '<div style="display:flex; gap:6px; flex-wrap:wrap; margin-top:10px;">'
                    + ''.join(tag_parts) + '</div>'
                )

            parts.append(f'''<div class="thread" style="--thread-heat: rgba(240,183,38,0.6); --thread-glow: rgba(240,183,38,0.10);">
    <div class="thread-head" style="cursor:default;">
        <span class="post-tag tag-signal">TRUMP</span>
        <span class="thread-name" style="flex:1;">Truth Social &middot; {html.escape(rel_time)}</span>
    </div>
    <div style="margin-top:10px;">
        <div style="font-size:14.5px; line-height:1.5; color:var(--t1);">{html.escape(display_text)}</div>
        {tags_html}
    </div>
</div>''')

        return '\n'.join(parts) + '\n'

    def _render_feed_with_sections(self, posts: List[Dict]) -> str:
        """Render posts grouped as company threads — each company is a mini-story."""
        from collections import OrderedDict

        # Group posts by ticker
        by_ticker: dict = OrderedDict()
        for p in posts:
            t = p["ticker"]
            if t not in by_ticker:
                by_ticker[t] = []
            by_ticker[t].append(p)

        # Sort tickers: verdict tier first (BUY > WATCH > PASS > none), then EV% within tier
        verdict_rank = {"BUY": 3, "WATCH": 2, "PASS": 1}

        def ticker_sort_key(ticker):
            posts_for_t = by_ticker[ticker]
            tier = 0
            ev = 0
            for p in posts_for_t:
                if p["type"] == "verdict":
                    tier = verdict_rank.get(p.get("tag", ""), 0)
                    if p.get("hero"):
                        try:
                            ev = float(p["hero"][0].replace("%", "").replace("+", ""))
                        except (ValueError, TypeError):
                            pass
                    break
            return (tier, ev)

        sorted_tickers = sorted(by_ticker.keys(), key=ticker_sort_key, reverse=True)

        # Order posts within each thread: verdict → intro → thesis → numbers → bull → bear → signal
        type_order = {"verdict": 0, "intro": 1, "thesis": 2, "numbers": 3, "bull": 4, "bear": 5, "signal": 6}

        parts = []
        max_threads = 20  # Cap total threads
        featured_count = 3  # Top N picks get visual prominence

        for i, ticker in enumerate(sorted_tickers[:max_threads]):
            thread_posts = sorted(by_ticker[ticker], key=lambda p: type_order.get(p["type"], 99))
            name = thread_posts[0]["name"]
            # Get verdict tag if any
            verdict_tag = ""
            for p in thread_posts:
                if p["type"] == "verdict":
                    verdict_tag = p.get("tag", "")
                    break

            tag_cls = {"BUY": "tag-verdict", "WATCH": "tag-numbers", "PASS": "tag-bear"}.get(verdict_tag, "tag-intro")

            # Get EV% for the header
            ev_html = ""
            ev_numeric = 0
            for p in thread_posts:
                if p["type"] == "verdict" and p.get("hero"):
                    val, label, cls = p["hero"]
                    ev_html = f'<span class="thread-ev {cls}">{val}</span>'
                    try:
                        ev_numeric = float(val.replace("%", "").replace("+", ""))
                    except (ValueError, TypeError):
                        pass
                    break

            # Heat style — left border color intensity maps to upside magnitude
            # Also set spark background/glow CSS vars
            if ev_numeric > 0:
                # Map 0-50% to low-high intensity green glow
                intensity = min(ev_numeric / 50.0, 1.0)
                alpha_border = 0.3 + intensity * 0.7  # 0.3 to 1.0
                alpha_glow = intensity * 0.15  # 0 to 0.15
                spark_bg_alpha = 0.10 + intensity * 0.14  # visible green tint
                spark_glow_alpha = 0.25 + intensity * 0.35
                spark_border_alpha = 0.15 + intensity * 0.25
                heat_style = (f'style="--thread-heat: rgba(114,202,155,{alpha_border:.2f}); '
                              f'--thread-glow: rgba(50,164,103,{alpha_glow:.2f}); '
                              f'--spark-bg: rgba(50,164,103,{spark_bg_alpha:.2f}); '
                              f'--spark-glow: rgba(114,202,155,{spark_glow_alpha:.2f}); '
                              f'--spark-border: rgba(114,202,155,{spark_border_alpha:.2f});"')
            elif ev_numeric < 0:
                intensity = min(abs(ev_numeric) / 30.0, 1.0)
                alpha_border = 0.3 + intensity * 0.7
                alpha_glow = intensity * 0.12
                spark_bg_alpha = 0.10 + intensity * 0.14
                spark_glow_alpha = 0.25 + intensity * 0.35
                spark_border_alpha = 0.15 + intensity * 0.25
                heat_style = (f'style="--thread-heat: rgba(231,106,110,{alpha_border:.2f}); '
                              f'--thread-glow: rgba(205,66,70,{alpha_glow:.2f}); '
                              f'--spark-bg: rgba(205,66,70,{spark_bg_alpha:.2f}); '
                              f'--spark-glow: rgba(231,106,110,{spark_glow_alpha:.2f}); '
                              f'--spark-border: rgba(231,106,110,{spark_border_alpha:.2f});"')
            else:
                heat_style = ''

            # Get preview: hook (thesis/edge) + tease (verdict)
            # Thesis text is the variant perception — inherently curiosity-inducing
            # ("The market is mispricing X because...") vs verdict which is dry summary.
            # Use thesis as hook to drive clicks, verdict as supporting tease.
            import re as _re
            preview_hook = ""
            preview_tease = ""
            verdict_text = ""
            thesis_text = ""
            for p in thread_posts:
                if p["type"] == "verdict" and p.get("body") and not verdict_text:
                    verdict_text = _re.sub(r'<[^>]+>', '', p["body"])
                if p["type"] == "thesis" and p.get("body") and not thesis_text:
                    thesis_text = _re.sub(r'<[^>]+>', '', p["body"])
            if thesis_text:
                # Thesis as hook — strip generic "The market is..." openings
                # to surface the unique insight immediately (otherwise every
                # collapsed card looks identical at a glance).
                hook_text = thesis_text.strip()
                # Strip common boilerplate prefixes that kill scannability
                for prefix in [
                    "The market is over-",      # -> "penalizing..."
                    "The market is under",       # -> "estimating..."
                    "The market is ",            # -> "pricing X as if..."
                    "The consensus is ",         # -> "directionally correct but..."
                ]:
                    if hook_text.startswith(prefix):
                        remainder = hook_text[len(prefix):]
                        # Capitalize the first letter after stripping
                        hook_text = remainder[0].upper() + remainder[1:] if remainder else hook_text
                        break
                sent_split = _re.split(r'(?<=[.!?])\s+', hook_text, maxsplit=1)
                preview_hook = sent_split[0].strip()
                # If first sentence is too long for 2-line clamp, cut at a
                # natural clause boundary (colon, semicolon, em-dash, or
                # comma before a conjunction) so the collapsed card reads as
                # a complete thought, not a broken fragment.
                if len(preview_hook) > 100:
                    # Try clause-level breaks first (strongest pause points)
                    best_cut = -1
                    for delim_pat in [
                        r'[.:;]\s',           # colon/semicolon/period + space
                        r'\s[—–]\s',          # em/en-dash surrounded by spaces
                        r',\s+(?:but|and|while|which|where|so|yet)\s',  # comma before conjunction
                    ]:
                        for m in _re.finditer(delim_pat, preview_hook):
                            pos = m.start() + 1  # include the delimiter char
                            if 40 <= pos <= 120:
                                best_cut = pos
                        if best_cut > 0:
                            break
                    if best_cut > 0:
                        preview_hook = preview_hook[:best_cut].rstrip(' ,')
                        # Add ellipsis only if we actually cut content
                        if best_cut < len(sent_split[0].strip()):
                            preview_hook += "\u2026"
                    elif len(preview_hook) > 130:
                        preview_hook = preview_hook[:127].rstrip() + "\u2026"
                # Verdict first sentence as tease — the "what" after the "why"
                # Problem: verdict S1 is almost always boilerplate like
                # "TICKER is a high-quality X trading at Y" — every card
                # looks identical at a glance. Skip to S2 when S1 is generic.
                if verdict_text:
                    v_split = _re.split(r'(?<=[.!?])\s+', verdict_text, maxsplit=2)
                    s1 = v_split[0].strip()
                    s2 = v_split[1].strip() if len(v_split) > 1 else ""
                    # Detect boilerplate openers: "[Name] is/offers/at..."
                    is_boilerplate = bool(_re.match(
                        r'^.{1,40}\s+(?:is|offers|at)\s+(?:a\s+)?'
                        r'(?:high-quality|rare|dominant|best-in-class|mediocre|'
                        r'genuinely|compelling|generational|quality)',
                        s1, _re.IGNORECASE
                    ))
                    if is_boilerplate and s2:
                        preview_tease = s2
                    else:
                        preview_tease = s1

                    # Detect when tease paraphrases the hook (kills info density).
                    # Compare significant words — if >40% overlap, prefer S2 or skip.
                    _stop = {'the','a','an','is','are','was','were','be','been','being',
                             'that','this','it','its','of','in','to','for','on','at',
                             'by','with','and','or','but','not','from','as','has','have',
                             'had','will','would','could','should','may','might','can',
                             'do','does','did','than','so','if','then','into','about'}
                    def _sig_words(t):
                        return set(w.lower().strip('.,;:!?"\'-()') for w in t.split()
                                   if len(w) > 2) - _stop
                    hook_words = _sig_words(preview_hook)
                    tease_words = _sig_words(preview_tease)
                    if hook_words and tease_words:
                        overlap = len(hook_words & tease_words) / min(len(hook_words), len(tease_words))
                        if overlap > 0.4:
                            # Current tease overlaps hook — try the next sentence
                            s3 = v_split[2].strip() if len(v_split) > 2 else ""
                            if not s3:
                                # v_split was capped at maxsplit=2; split further
                                remainder = _re.split(r'(?<=[.!?])\s+', verdict_text)
                                # Find first sentence that doesn't overlap with hook
                                for candidate in remainder[1:]:
                                    cand_words = _sig_words(candidate.strip())
                                    if cand_words and hook_words:
                                        cand_overlap = len(hook_words & cand_words) / min(len(hook_words), len(cand_words))
                                        if cand_overlap <= 0.4:
                                            s3 = candidate.strip()
                                            break
                            if s3:
                                preview_tease = s3
                            # else keep current tease — better than nothing
                    if len(preview_tease) > 200:
                        preview_tease = preview_tease[:197].rstrip() + "..."
            elif verdict_text:
                # No thesis — fall back to verdict as hook
                sent_split = _re.split(r'(?<=[.!?])\s+', verdict_text, maxsplit=1)
                preview_hook = sent_split[0].strip()
                if len(sent_split) > 1:
                    rest = sent_split[1].strip()
                    preview_tease = rest[:200].rstrip() + ("..." if len(rest) > 200 else "")

            is_featured = i < featured_count and verdict_tag == "BUY"
            # All threads start collapsed — maximizes above-the-fold density
            # so users see 3-4 spark numbers at once (slot machine effect).
            # Featured cards are visually prominent but collapsed for scan speed.
            thread_cls = "thread featured" if is_featured else "thread"
            rank_html = f'<span class="thread-rank">{i + 1}</span>' if is_featured else ''

            # Build heat bar HTML
            heat_bar_html = ""
            if ev_numeric != 0:
                fill_pct = min(abs(ev_numeric) / 50.0 * 100, 100)
                heat_cls = "heat-green" if ev_numeric > 0 else "heat-red"
                heat_bar_html = f'<span class="thread-heat-bar"><span class="heat-track"><span class="heat-fill {heat_cls}" style="width:{fill_pct:.0f}%"></span></span></span>'

            # Build key metrics for collapsed state
            metrics_html = ""
            metric_parts = []
            seen_labels = set()
            for p in thread_posts:
                if p["type"] == "verdict" and p.get("pills"):
                    for label, val, cls in p["pills"]:
                        if label in seen_labels:
                            continue
                        seen_labels.add(label)
                        mv_cls = "pos" if cls == "pos" else ("neg" if cls == "neg" else "gold" if "Quality" in label else "")
                        metric_parts.append(f'<span class="thread-metric">{label} <span class="mv {mv_cls}">{val}</span></span>')
                    break
            # Also grab Entry from numbers post if not already present
            for p in thread_posts:
                if p["type"] == "numbers" and p.get("pills"):
                    for label, val, cls in p["pills"]:
                        if label == "Entry" and label not in seen_labels:
                            seen_labels.add(label)
                            metric_parts.append(f'<span class="thread-metric">{label} <span class="mv">{val}</span></span>')
                    break
            if metric_parts:
                metrics_html = '<div class="thread-metrics">' + "".join(metric_parts[:4]) + '</div>'

            # Build price-vs-entry gauge for collapsed state
            entry_gauge_html = ""
            current_price = None
            entry_price_val = None
            # Extract price from intro/numbers pills, entry from verdict/numbers pills
            for p in thread_posts:
                for label, val, cls in (p.get("pills") or []):
                    if label == "Price":
                        try:
                            current_price = float(val.replace("$", "").replace(",", ""))
                        except (ValueError, TypeError):
                            pass
                    if label == "Entry":
                        try:
                            entry_price_val = float(val.replace("$", "").replace(",", ""))
                        except (ValueError, TypeError):
                            pass
            if current_price and entry_price_val and entry_price_val > 0:
                pct_diff = (current_price - entry_price_val) / entry_price_val * 100
                if pct_diff <= 0:
                    # At or below entry — green, showing discount
                    delta_str = f"{pct_diff:.1f}%"
                    delta_cls = "discount"
                    fill_cls = "at-discount"
                    # Bar fills from right to left — how deep the discount is
                    # 0% discount = 50% fill (at entry), -20% = 30%, capped
                    fill_pct = max(10, min(50 + pct_diff, 50))
                    marker_pos = 50  # entry point marker always at midpoint
                else:
                    # Above entry — red, showing premium
                    delta_str = f"+{pct_diff:.1f}%"
                    delta_cls = "premium"
                    fill_cls = "at-premium"
                    fill_pct = min(50 + pct_diff, 90)
                    marker_pos = 50
                entry_gauge_html = f'''<div class="thread-entry-gauge">
                    <span class="entry-label">vs entry</span>
                    <div class="entry-bar-wrap">
                        <div class="entry-bar-track">
                            <div class="entry-bar-fill {fill_cls}" style="width:{fill_pct:.0f}%"></div>
                            <div class="entry-bar-marker" style="left:{marker_pos}%"></div>
                        </div>
                    </div>
                    <span class="entry-delta {delta_cls}">{delta_str}</span>
                </div>'''

            # Build spark HTML — big EV% number on the right
            spark_html = ""
            if ev_numeric != 0:
                ev_val_str = f"{ev_numeric:+.0f}%"
                spark_cls = "pos" if ev_numeric > 0 else "neg"
                spark_html = f'''<div class="thread-spark">
                    <span class="spark-val {spark_cls}">{ev_val_str}</span>
                    <span class="spark-label">upside</span>
                </div>'''

            # Thread header
            parts.append(f'''<div class="{thread_cls}" {heat_style}>
    <div class="thread-head">
        {rank_html}
        <span class="thread-ticker">{ticker}</span>
        {ev_html}
        {heat_bar_html}
        {f'<span class="post-tag {tag_cls}">{verdict_tag}</span>' if verdict_tag else ''}
        <span class="thread-name">{html.escape(name)}</span>
        <span class="thread-chevron">&#9662;</span>
    </div>
    <div class="thread-collapsed">
        <div class="thread-left">
            {f'<div class="thread-hook">{html.escape(preview_hook)}</div>' if preview_hook else ''}
            {f'<div class="thread-tease">{html.escape(preview_tease)}</div>' if preview_tease else ''}
            {metrics_html}
            {entry_gauge_html}
            {f'<div class="thread-post-count">{len(thread_posts)} insights inside</div>' if len(thread_posts) > 2 else ''}
        </div>
        {spark_html}
    </div>
    <div class="thread-body">''')

            # Thread posts (connected by line)
            for j, p in enumerate(thread_posts):
                is_last = (j == len(thread_posts) - 1)
                parts.append(self._render_thread_post(p, is_last=is_last))

            # Thread footer — link to full analysis
            parts.append(f'''    <a href="/api/notes/{ticker}" class="thread-more">Read full analysis &rarr;</a>
    </div>
</div>''')

        return "\n".join(parts)

    def _render_thread_post(self, post: Dict, is_last: bool = False) -> str:
        """Render a single post within a company thread."""
        ptype = post["type"]
        tag_class = f"tag-{ptype}"
        line_class = "" if not is_last else "tp-last"

        hero_html = ""
        if post.get("hero"):
            val, label, cls = post["hero"]
            hero_html = f'<div class="post-hero"><span class="hero-val {cls}">{val}</span><span class="hero-label">{label}</span></div>'

        pills_html = ""
        if post.get("pills"):
            pill_parts = []
            for label, val, cls in post["pills"]:
                pill_parts.append(f'<span class="pill">{label} <span class="v {cls}">{val}</span></span>')
            pills_html = '<div class="pills">' + "".join(pill_parts) + '</div>'

        # Inline alpha annotation for gated trade signals — shows the
        # measured edge so the user can size and trust appropriately.
        # Tier (★/★★/★★★) collapses p-value + n_effective into a glance-
        # readable confidence; annualised α is more interpretable than
        # a horizon-specific log alpha; freshness flags stale gates.
        gate_html = ""
        gate = post.get("gate")
        if gate is not None:
            from invest.signals.gates import (
                annualised_alpha,
                confidence_tier,
                freshness,
            )
            ann = annualised_alpha(gate)
            sign = "+" if ann >= 0 else ""
            tier = confidence_tier(gate)
            fresh_label, fresh_sev = freshness(gate)
            fresh_color = {
                'fresh': 'var(--text-muted)',
                'aging': '#c98a00',
                'stale': '#c0392b',
            }[fresh_sev]
            parts = [
                f"{tier} {sign}{ann * 100:.1f}% / yr".strip(),
                f"n={gate.n_nominal} (eff {gate.n_effective}) · {gate.horizon}",
                f'<span style="color:{fresh_color}">{fresh_label}</span>',
            ]
            if gate.caveat:
                parts.append(html.escape(gate.caveat))
            gate_text = " · ".join(parts)
            gate_html = (
                f'<div style="color:var(--text-muted);font-size:12px;'
                f'margin-top:4px;">{gate_text}</div>'
            )

        return f'''    <div class="tp {line_class}">
        <div class="tp-dot {tag_class}"></div>
        <div class="tp-content">
            <span class="tp-tag {tag_class}">{html.escape(post["tag"])}</span>
            {hero_html}
            <div class="post-body">{post["body"]}</div>
            {gate_html}
            {pills_html}
        </div>
    </div>'''

    def _render_policy_markets(self, markets: List[Dict]) -> str:
        """Render the Trump-policy market section at the top of the feed.

        Each card shows: question, current YES price, 24h delta in pp
        (color-coded), 24h volume, close date. Sorted by |Δ24h| upstream.
        """
        if not markets:
            return ""

        category_labels = {
            'tariffs': 'Tariffs',
            'fed_actions': 'Fed actions',
            'executive_orders': 'Executive orders',
            'cabinet_appointments': 'Cabinet picks',
            'legislation': 'Legislation',
            'china': 'China',
            'energy_oil': 'Energy / oil',
            'crypto': 'Crypto policy',
            'immigration': 'Immigration',
            'foreign_policy': 'Foreign policy',
        }

        parts = ['''<div class="section-sep"><span>Trump policy markets</span></div>''']
        for m in markets[:12]:  # cap to keep section scannable
            q = m.get('question') or ''
            cat = m.get('category') or 'other'
            cat_label = category_labels.get(cat, cat.replace('_', ' ').title())
            yes = m.get('current_yes_price')
            yes_str = f"{yes*100:.0f}%" if yes is not None else "?"
            delta_pp = m.get('delta_pp')
            delta_cls = m.get('delta_class') or ''
            if delta_pp is None:
                delta_str = "—"
                delta_cls = ''
            elif delta_pp > 0:
                delta_str = f"+{delta_pp:.1f}pp"
            else:
                delta_str = f"{delta_pp:.1f}pp"

            v24 = m.get('volume_24h') or 0
            if v24 >= 1e6:
                v24_str = f"${v24/1e6:.1f}M"
            elif v24 >= 1e3:
                v24_str = f"${v24/1e3:.0f}K"
            else:
                v24_str = f"${v24:.0f}"

            close_dt = m.get('close_date')
            close_str = close_dt.strftime('%b %d') if close_dt else '—'
            url = m.get('url') or ''
            link_open = f'<a href="{html.escape(url)}" target="_blank" rel="noopener" style="color:inherit;text-decoration:none;">' if url else ''
            link_close = '</a>' if url else ''

            # Sentiment border via existing thread heat vars
            if delta_pp is not None and abs(delta_pp) >= 5:
                if delta_pp > 0:
                    intensity = min(delta_pp / 30.0, 1.0)
                    heat_style = (f'style="--thread-heat: rgba(114,202,155,{0.3 + intensity*0.7:.2f}); '
                                  f'--thread-glow: rgba(50,164,103,{intensity*0.15:.2f});"')
                else:
                    intensity = min(abs(delta_pp) / 30.0, 1.0)
                    heat_style = (f'style="--thread-heat: rgba(231,106,110,{0.3 + intensity*0.7:.2f}); '
                                  f'--thread-glow: rgba(205,66,70,{intensity*0.12:.2f});"')
            else:
                heat_style = ''

            parts.append(f'''<div class="thread" {heat_style}>
    {link_open}<div class="thread-head" style="cursor:default;">
        <span class="post-tag tag-signal">{html.escape(cat_label)}</span>
        <span class="thread-name" style="flex:1;white-space:normal;font-size:14px;color:var(--t1);font-weight:600;">{html.escape(q)}</span>
    </div>
    <div class="thread-collapsed">
        <div class="thread-left">
            <div class="thread-metrics">
                <span class="thread-metric">YES <span class="mv">{yes_str}</span></span>
                <span class="thread-metric">24h <span class="mv {delta_cls}">{delta_str}</span></span>
                <span class="thread-metric">Vol <span class="mv">{v24_str}</span></span>
                <span class="thread-metric">Closes <span class="mv">{close_str}</span></span>
            </div>
        </div>
        <div class="thread-spark">
            <span class="spark-val {delta_cls}">{delta_str}</span>
            <span class="spark-label">24h</span>
        </div>
    </div>{link_close}
</div>''')

        return "\n".join(parts) + "\n"
