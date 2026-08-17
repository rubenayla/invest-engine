#!/usr/bin/env python3
"""
Live dashboard server.

Serves the valuation dashboard with real-time health monitoring
and the ability to trigger data updates from the browser.

Usage:
    uv run python scripts/dashboard_server.py
    uv run python scripts/dashboard_server.py --port 8050
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse
from starlette.routing import Route

REPO_ROOT = Path(__file__).parent.parent
LOG_PATH = REPO_ROOT / "logs" / "update_server.log"

sys.path.insert(0, str(REPO_ROOT / "src"))

from invest.data.db import get_connection

logger = logging.getLogger("dashboard_server")

_last_activity = time.monotonic()
_server_ref: uvicorn.Server | None = None


def _touch_activity():
    global _last_activity
    _last_activity = time.monotonic()

# ── Update process singleton ─────────────────────────────────────────────

class UpdateManager:
    """Manages a single update subprocess. Prevents concurrent runs."""

    def __init__(self):
        self._lock = threading.Lock()
        self._process: subprocess.Popen | None = None
        self._status = "idle"          # idle | running | completed | failed
        self._started_at: str | None = None
        self._finished_at: str | None = None
        self._error: str | None = None
        self._output_lines: list[str] = []
        self._exit_code: int | None = None
        self._phase: str = ""
        self._thread: threading.Thread | None = None

    @property
    def status_dict(self) -> dict:
        return {
            "status": self._status,
            "started_at": self._started_at,
            "finished_at": self._finished_at,
            "error": self._error,
            "exit_code": self._exit_code,
            "phase": self._phase,
            "tail": self._output_lines[-30:],
        }

    def start(self, universe: str = "sp500", extra_args: list[str] | None = None) -> dict:
        with self._lock:
            if self._status == "running" and self._process and self._process.poll() is None:
                return {"ok": False, "reason": "already_running", **self.status_dict}

            self._status = "running"
            self._started_at = _now_iso()
            self._finished_at = None
            self._error = None
            self._exit_code = None
            self._output_lines = []
            self._phase = "starting"

            cmd = [
                "uv", "run", "python", "scripts/update_all.py",
                "--universe", universe,
                "--skip-dashboard",       # we regenerate via the server
                "--skip-gbm",             # ML models run on Mac, not server
                "--skip-nn",
                "--skip-autoresearch",
                "--skip-classic",
                "--skip-scanner",
            ]
            if extra_args:
                cmd.extend(extra_args)

            self._thread = threading.Thread(target=self._run, args=(cmd,), daemon=True)
            self._thread.start()

            return {"ok": True, **self.status_dict}

    def _run(self, cmd: list[str]):
        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(REPO_ROOT),
            )
            for line in self._process.stdout:
                line = line.rstrip("\n")
                self._output_lines.append(line)
                # Parse phase from "==> Phase name" lines
                if line.startswith("==>"):
                    self._phase = line[4:].strip()

            self._process.wait()
            self._exit_code = self._process.returncode

            if self._exit_code == 0:
                self._status = "completed"
                self._phase = "done"
                # Fresh data landed — rebuild the snapshot so it shows without
                # waiting for the next scheduled refresh.
                try:
                    snapshot_cache.refresh()
                except Exception as exc:
                    logger.error("Post-update snapshot refresh failed: %s", exc)
            else:
                self._status = "failed"
                self._error = f"Process exited with code {self._exit_code}"
        except Exception as exc:
            self._status = "failed"
            self._error = str(exc)
            self._exit_code = -1
        finally:
            self._finished_at = _now_iso()

    def cancel(self) -> dict:
        with self._lock:
            if self._process and self._process.poll() is None:
                self._process.terminate()
                try:
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                self._status = "failed"
                self._error = "Cancelled by user"
                self._finished_at = _now_iso()
                self._exit_code = -2
                return {"ok": True, "reason": "cancelled"}
            return {"ok": False, "reason": "not_running"}


update_manager = UpdateManager()


# ── Alarm checker ────────────────────────────────────────────────────────

def _ensure_alarm_table():
    """Create the price_alarms table if it doesn't exist."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS price_alarms (
            id SERIAL PRIMARY KEY,
            ticker TEXT NOT NULL,
            condition TEXT NOT NULL CHECK(condition IN ('above', 'below')),
            target_price REAL NOT NULL,
            created_at TEXT NOT NULL DEFAULT (TO_CHAR(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')),
            triggered_at TEXT,
            active INTEGER NOT NULL DEFAULT 1
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_price_alarms_active ON price_alarms(active, ticker)")
    conn.commit()
    conn.close()


def _ensure_reminder_table():
    """Create the reminders table if it doesn't exist."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id SERIAL PRIMARY KEY,
            ticker TEXT,
            message TEXT NOT NULL,
            due_date TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (TO_CHAR(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')),
            acknowledged_at TEXT,
            active INTEGER NOT NULL DEFAULT 1
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_reminders_active ON reminders(active, due_date)")
    conn.commit()
    conn.close()


class AlarmChecker:
    """Periodically checks active alarms against current prices."""

    def __init__(self):
        self._thread: threading.Thread | None = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while True:
            try:
                self._check_alarms()
            except Exception as e:
                logger.error("Alarm check failed: %s", e)
            time.sleep(60)

    def _check_alarms(self):
        conn = get_connection(dict_cursor=True)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id, ticker, condition, target_price FROM price_alarms WHERE active = 1"
        )
        alarms = cursor.fetchall()

        if not alarms:
            conn.close()
            return

        tickers = list({r["ticker"] for r in alarms})
        placeholders = ",".join("%s" for _ in tickers)
        cursor.execute(
            f"SELECT ticker, current_price FROM current_stock_data WHERE ticker IN ({placeholders})",
            tickers,
        )
        prices = cursor.fetchall()
        price_map = {r["ticker"]: r["current_price"] for r in prices if r["current_price"]}

        now = _now_iso()
        triggered_ids = []
        for alarm in alarms:
            price = price_map.get(alarm["ticker"])
            if price is None:
                continue
            if alarm["condition"] == "above" and price >= alarm["target_price"]:
                triggered_ids.append(alarm["id"])
            elif alarm["condition"] == "below" and price <= alarm["target_price"]:
                triggered_ids.append(alarm["id"])

        if triggered_ids:
            ph = ",".join("%s" for _ in triggered_ids)
            cursor.execute(
                f"UPDATE price_alarms SET triggered_at = %s, active = 0 WHERE id IN ({ph})",
                [now, *triggered_ids],
            )
            conn.commit()
        conn.close()


alarm_checker = AlarmChecker()


# ── Database health queries ──────────────────────────────────────────────

def get_db_health() -> dict:
    """Query database for freshness and health metrics."""
    conn = get_connection(dict_cursor=True)
    cursor = conn.cursor()
    now = datetime.now(timezone.utc)

    health: dict = {"ok": True, "generated_at": _now_iso()}

    # ── Stock data freshness (use fetch_timestamp, count stale) ──
    try:
        cursor.execute(
            "SELECT COUNT(*) as cnt, MIN(fetch_timestamp) as oldest, MAX(fetch_timestamp) as newest "
            "FROM current_stock_data WHERE current_price IS NOT NULL"
        )
        row = cursor.fetchone()
        cursor.execute(
            "SELECT COUNT(*) as cnt FROM current_stock_data "
            "WHERE current_price IS NOT NULL AND fetch_timestamp < NOW() - INTERVAL '7 days'"
        )
        stale_row = cursor.fetchone()
        # p80 age: 80th percentile fetch_timestamp (ignores the ~20% oldest outliers)
        cursor.execute(
            "SELECT fetch_timestamp FROM current_stock_data "
            "WHERE current_price IS NOT NULL AND fetch_timestamp IS NOT NULL "
            "ORDER BY fetch_timestamp ASC "
            "LIMIT 1 OFFSET (SELECT CAST(COUNT(*) * 0.2 AS INTEGER) "
            "FROM current_stock_data WHERE current_price IS NOT NULL AND fetch_timestamp IS NOT NULL)"
        )
        p80_row = cursor.fetchone()
        health["stock_data"] = {
            "count": row["cnt"],
            "oldest": row["oldest"],
            "newest": row["newest"],
            "age_hours": _hours_ago(row["oldest"], now),
            "newest_age_hours": _hours_ago(row["newest"], now),
            "p80_age_hours": _hours_ago(p80_row["fetch_timestamp"], now) if p80_row else None,
            "stale_count": stale_row["cnt"],
        }
    except Exception as exc:
        health["stock_data"] = {"error": str(exc)}
        conn.rollback()

    # ── Per-model valuation freshness ──
    try:
        cursor.execute(
            "SELECT model_name, COUNT(*) as cnt, "
            "SUM(CASE WHEN suitable THEN 1 ELSE 0 END) as ok_cnt, "
            "SUM(CASE WHEN NOT suitable THEN 1 ELSE 0 END) as fail_cnt, "
            "MIN(timestamp) as oldest, MAX(timestamp) as newest "
            "FROM valuation_results GROUP BY model_name"
        )
        rows = cursor.fetchall()
        models = {}
        for r in rows:
            models[r["model_name"]] = {
                "total": r["cnt"],
                "successful": r["ok_cnt"],
                "failed": r["fail_cnt"],
                "oldest": r["oldest"],
                "newest": r["newest"],
                "age_hours": _hours_ago(r["oldest"], now),
                "newest_age_hours": _hours_ago(r["newest"], now),
            }
        health["models"] = models
    except Exception as exc:
        health["models"] = {"error": str(exc)}
        conn.rollback()

    # ── SEC data freshness (now in main Postgres DB) ──
    sec_tables = {
        "insider": "insider_transactions",
        "activist": "activist_stakes",
        "holdings": "fund_holdings",
    }
    sec_health = {}
    for name, table in sec_tables.items():
        try:
            cursor.execute(f"SELECT COUNT(*) as cnt FROM {table}")
            count = cursor.fetchone()["cnt"]
            sec_health[name] = {"exists": True, "rows": count}
        except Exception as exc:
            sec_health[name] = {"exists": False, "error": str(exc)}
            conn.rollback()
    health["sec_data"] = sec_health

    # ── Database size (PostgreSQL) ──
    try:
        cursor.execute("SELECT pg_database_size('invest')")
        size_bytes = cursor.fetchone()["pg_database_size"]
        health["db_size_mb"] = round(size_bytes / (1024 * 1024), 1)
    except Exception as exc:
        health["db_size_mb"] = None
        conn.rollback()

    # ── Recent errors (last 20 failed valuations) ──
    try:
        cursor.execute(
            "SELECT ticker, model_name, error_message, failure_reason, timestamp "
            "FROM valuation_results WHERE NOT suitable AND error_message IS NOT NULL "
            "ORDER BY timestamp DESC LIMIT 20"
        )
        rows = cursor.fetchall()
        health["recent_errors"] = [dict(r) for r in rows]
    except Exception as exc:
        health["recent_errors"] = {"error": str(exc)}
        conn.rollback()

    conn.close()
    return health


# ── Data snapshot cache ──────────────────────────────────────────────────

# Loading all stocks + valuations + insider/politician signals from the DB
# takes ~1-2s. Doing it on every request made pages take 8-15s. Instead we
# hold one shared snapshot, refreshed by a background thread, so no user
# request ever pays the load cost.
REFRESH_INTERVAL = int(os.environ.get("DASHBOARD_REFRESH_INTERVAL", "300"))  # seconds


class SnapshotCache:
    """Thread-safe holder for the latest loaded stocks_data + health."""

    def __init__(self):
        self._lock = threading.Lock()
        self._refresh_lock = threading.Lock()
        self._stocks_data: dict | None = None
        self._health: dict | None = None
        self._generated_at: str | None = None

    def _load(self):
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        from dashboard import load_stocks_from_database

        stocks_data = load_stocks_from_database()
        health = get_db_health()
        return stocks_data, health

    def refresh(self) -> bool:
        """Rebuild the snapshot. Keeps the previous one on failure.

        Serialized via _refresh_lock so concurrent triggers don't double-load.
        """
        with self._refresh_lock:
            try:
                stocks_data, health = self._load()
            except Exception as exc:
                logger.error("Snapshot refresh failed: %s", exc)
                return False
            with self._lock:
                self._stocks_data = stocks_data
                self._health = health
                self._generated_at = _now_iso()
            return True

    def get(self):
        """Return (stocks_data, health, generated_at), loading synchronously
        on the very first call if the snapshot isn't warm yet."""
        with self._lock:
            warm = self._stocks_data is not None
        if not warm:
            self.refresh()
        with self._lock:
            return (
                self._stocks_data or {},
                self._health or {},
                self._generated_at or _now_iso(),
            )

    def start_background_refresh(self):
        def _run():
            while True:
                time.sleep(REFRESH_INTERVAL)
                self.refresh()

        threading.Thread(target=_run, daemon=True).start()


snapshot_cache = SnapshotCache()


# ── Route handlers ───────────────────────────────────────────────────────

async def index(request: Request) -> HTMLResponse:
    """Serve the dashboard HTML, rendered from the cached data snapshot."""
    _touch_activity()
    from invest.dashboard_components.html_generator import HTMLGenerator

    stocks_data, health, generated_at = snapshot_cache.get()

    generator = HTMLGenerator()
    progress_data = {
        "total_analyzed": len(stocks_data),
        "successful": len(stocks_data),
        "failed": 0,
    }
    metadata = {
        "last_updated": generated_at,
        "server_mode": True,
        "health": health,
        "update_status": update_manager.status_dict,
    }
    html = generator.generate_dashboard_html(stocks_data, progress_data, metadata)
    return HTMLResponse(html, headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})


async def mobile_index(request: Request) -> HTMLResponse:
    """Serve the mobile-optimized card-based dashboard."""
    _touch_activity()
    from invest.dashboard_components.html_generator import HTMLGenerator

    stocks_data, _, _ = snapshot_cache.get()
    generator = HTMLGenerator()
    html = generator.generate_mobile_html(stocks_data)
    return HTMLResponse(html, headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})


async def feed_index(request: Request) -> HTMLResponse:
    """Serve the doomscroll insights feed."""
    _touch_activity()
    from invest.dashboard_components.html_generator import HTMLGenerator

    stocks_data, _, _ = snapshot_cache.get()

    # Load Polymarket Trump-policy markets if the table exists.
    # DB-down or table-missing is non-fatal — feed renders without that section.
    policy_markets: list = []
    try:
        from invest.data.polymarket_db import get_active_markets
        conn = get_connection()
        try:
            policy_markets = get_active_markets(conn, limit=12, sort_by_24h_move=True)
        finally:
            conn.close()
    except Exception:
        policy_markets = []

    generator = HTMLGenerator()
    notes_dir = os.environ.get("INVEST_NOTES_DIR") or str(REPO_ROOT / "notes" / "companies")
    feed_html = generator.generate_feed_html(
        stocks_data, notes_dir=notes_dir, policy_markets=policy_markets,
    )
    return HTMLResponse(feed_html, headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})


async def api_stocks(request: Request) -> JSONResponse:
    """Return all stock data as JSON for mobile dashboard refresh."""
    _touch_activity()
    stocks_data, _, _ = snapshot_cache.get()

    # Slim down for JSON: keep only what the mobile dashboard needs
    slim = {}
    for ticker, stock in stocks_data.items():
        entry = {
            "ticker": ticker,
            "company_name": stock.get("company_name", ticker),
            "current_price": stock.get("current_price"),
            "valuations": {},
            "insider": stock.get("insider", {}),
        }
        for model, val in stock.get("valuations", {}).items():
            safe_val = {k: v for k, v in val.items() if k != "details"}
            if "details" in val and isinstance(val["details"], dict):
                safe_val["details"] = val["details"]
            entry["valuations"][model] = safe_val
        slim[ticker] = entry

    return JSONResponse(_json_safe(slim), headers={"Cache-Control": "no-store"})


async def api_health(request: Request) -> JSONResponse:
    """Return database health/freshness data (from the cached snapshot)."""
    _, health, _ = snapshot_cache.get()
    return JSONResponse(_json_safe(health))


async def api_update_start(request: Request) -> JSONResponse:
    """Start an update process."""
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    universe = body.get("universe", "all")
    extra_args = body.get("extra_args", [])
    if body.get("lite", False) and "--lite-fetch" not in extra_args:
        extra_args.append("--lite-fetch")
    result = update_manager.start(universe=universe, extra_args=extra_args)
    return JSONResponse(result)


async def api_update_status(request: Request) -> JSONResponse:
    """Return current update status."""
    return JSONResponse(update_manager.status_dict)


async def api_update_cancel(request: Request) -> JSONResponse:
    """Cancel a running update."""
    return JSONResponse(update_manager.cancel())


# ── Alarm API ────────────────────────────────────────────────────────────

async def api_alarm_create(request: Request) -> JSONResponse:
    """Create a new price alarm."""
    body = await request.json()
    ticker = body.get("ticker", "").upper().strip()
    condition = body.get("condition")
    target_price = body.get("target_price")

    if not ticker or condition not in ("above", "below") or not isinstance(target_price, (int, float)):
        return JSONResponse({"ok": False, "error": "Invalid parameters"}, status_code=400)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO price_alarms (ticker, condition, target_price) VALUES (%s, %s, %s) RETURNING id",
        (ticker, condition, target_price),
    )
    alarm_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    return JSONResponse({"ok": True, "id": alarm_id})


async def api_alarm_list(request: Request) -> JSONResponse:
    """List alarms, optionally filtered by ticker."""
    ticker = request.query_params.get("ticker")
    conn = get_connection(dict_cursor=True)
    cursor = conn.cursor()
    if ticker:
        cursor.execute(
            "SELECT * FROM price_alarms WHERE ticker = %s ORDER BY active DESC, created_at DESC",
            (ticker.upper(),),
        )
    else:
        cursor.execute(
            "SELECT * FROM price_alarms ORDER BY active DESC, created_at DESC"
        )
    rows = cursor.fetchall()
    conn.close()
    return JSONResponse(_json_safe({"ok": True, "alarms": [dict(r) for r in rows]}))


async def api_alarm_delete(request: Request) -> JSONResponse:
    """Delete an alarm by id."""
    alarm_id = request.path_params["alarm_id"]
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM price_alarms WHERE id = %s", (alarm_id,))
    conn.commit()
    conn.close()
    return JSONResponse({"ok": True})


async def api_alarm_triggered(request: Request) -> JSONResponse:
    """Return alarms triggered since a given timestamp."""
    since = request.query_params.get("since")
    conn = get_connection(dict_cursor=True)
    cursor = conn.cursor()
    if since:
        cursor.execute(
            "SELECT * FROM price_alarms WHERE triggered_at IS NOT NULL AND triggered_at > %s "
            "ORDER BY triggered_at DESC",
            (since,),
        )
    else:
        cursor.execute(
            "SELECT * FROM price_alarms WHERE triggered_at IS NOT NULL AND active = 0 "
            "ORDER BY triggered_at DESC LIMIT 20"
        )
    rows = cursor.fetchall()
    conn.close()
    return JSONResponse(_json_safe({"ok": True, "triggered": [dict(r) for r in rows]}))


# ── Reminder API ─────────────────────────────────────────────────────

async def api_reminder_create(request: Request) -> JSONResponse:
    """Create a new reminder."""
    body = await request.json()
    ticker = (body.get("ticker") or "").upper().strip() or None
    message = (body.get("message") or "").strip()
    due_date = (body.get("due_date") or "").strip()

    if not message or not due_date:
        return JSONResponse({"ok": False, "error": "message and due_date required"}, status_code=400)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO reminders (ticker, message, due_date) VALUES (%s, %s, %s) RETURNING id",
        (ticker, message, due_date),
    )
    reminder_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    return JSONResponse({"ok": True, "id": reminder_id})


async def api_reminder_list(request: Request) -> JSONResponse:
    """List reminders, optionally filtered by ticker."""
    ticker = request.query_params.get("ticker")
    conn = get_connection(dict_cursor=True)
    cursor = conn.cursor()
    if ticker:
        cursor.execute(
            "SELECT * FROM reminders WHERE ticker = %s ORDER BY active DESC, due_date ASC",
            (ticker.upper(),),
        )
    else:
        cursor.execute("SELECT * FROM reminders ORDER BY active DESC, due_date ASC")
    rows = cursor.fetchall()
    conn.close()
    return JSONResponse(_json_safe({"ok": True, "reminders": [dict(r) for r in rows]}))


async def api_reminder_due(request: Request) -> JSONResponse:
    """Return active reminders where due_date <= today."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    conn = get_connection(dict_cursor=True)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM reminders WHERE active = 1 AND due_date <= %s ORDER BY due_date ASC",
        (today,),
    )
    rows = cursor.fetchall()
    conn.close()
    return JSONResponse(_json_safe({"ok": True, "reminders": [dict(r) for r in rows]}))


async def api_reminder_acknowledge(request: Request) -> JSONResponse:
    """Acknowledge (dismiss) a reminder."""
    reminder_id = request.path_params["reminder_id"]
    now = _now_iso()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE reminders SET acknowledged_at = %s, active = 0 WHERE id = %s",
        (now, reminder_id),
    )
    conn.commit()
    conn.close()
    return JSONResponse({"ok": True})


async def api_reminder_delete(request: Request) -> JSONResponse:
    """Permanently delete a reminder."""
    reminder_id = request.path_params["reminder_id"]
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM reminders WHERE id = %s", (reminder_id,))
    conn.commit()
    conn.close()
    return JSONResponse({"ok": True})


# ── Insider history API ──────────────────────────────────────────────────


async def api_insider_history(request: Request) -> JSONResponse:
    """Return monthly insider buy/sell counts for a ticker (SVG chart data).

    Distinguishes compensation sells (same-day option exercise + sell by same
    person) from discretionary open-market sells.
    """
    ticker = request.path_params["ticker"].upper()
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # Get open-market transactions
        cursor.execute("""
            SELECT SUBSTRING(transaction_date FROM 1 FOR 7) AS month,
                   transaction_type,
                   COUNT(*) AS cnt,
                   COALESCE(SUM(ABS(shares) * price_per_share), 0) AS volume
            FROM insider_transactions
            WHERE ticker = %s AND is_open_market = 1
            GROUP BY month, transaction_type
            ORDER BY month
        """, (ticker,))
        rows = cursor.fetchall()

        # Find compensation sells: sells by people who also exercised options
        # on the same day (M + S pair = vesting + tax withholding sell)
        cursor.execute("""
            SELECT SUBSTRING(s.transaction_date FROM 1 FOR 7) AS month,
                   COUNT(*) AS cnt,
                   COALESCE(SUM(ABS(s.shares) * s.price_per_share), 0) AS volume
            FROM insider_transactions s
            WHERE s.ticker = %s AND s.transaction_type = 'S' AND s.is_open_market = 1
              AND EXISTS (
                  SELECT 1 FROM insider_transactions m
                  WHERE m.ticker = s.ticker
                    AND m.reporter_name = s.reporter_name
                    AND m.transaction_date = s.transaction_date
                    AND m.transaction_type = 'M'
              )
            GROUP BY month
            ORDER BY month
        """, (ticker,))
        comp_rows = cursor.fetchall()
    except Exception:
        conn.rollback()
        return JSONResponse({"ok": True, "ticker": ticker, "months": []})
    finally:
        conn.close()

    # Build compensation sell lookup: month → (count, volume)
    comp_map: dict[str, tuple[int, float]] = {}
    for month, cnt, volume in comp_rows:
        comp_map[month] = (cnt, round(float(volume)))

    # Build month → {buys, sells, buy_vol, sell_vol, comp_sells, comp_sell_vol} map
    month_map: dict[str, dict] = {}
    for month, tx_type, cnt, volume in rows:
        if month not in month_map:
            month_map[month] = {"month": month, "buys": 0, "sells": 0,
                                "buy_vol": 0, "sell_vol": 0,
                                "comp_sells": 0, "comp_sell_vol": 0}
        if tx_type == "P":
            month_map[month]["buys"] = cnt
            month_map[month]["buy_vol"] = round(float(volume))
        elif tx_type == "S":
            month_map[month]["sells"] = cnt
            month_map[month]["sell_vol"] = round(float(volume))
            # Tag compensation portion
            if month in comp_map:
                month_map[month]["comp_sells"] = comp_map[month][0]
                month_map[month]["comp_sell_vol"] = comp_map[month][1]

    return JSONResponse({
        "ok": True,
        "ticker": ticker,
        "months": list(month_map.values()),
    })


# ── Notes (company .md files) ────────────────────────────────────────────

# Company analysis notes. Defaults to the corpus shipped with the repo; point
# INVEST_NOTES_DIR at your own directory to keep your notes separate from it.
NOTES_DIR = Path(os.environ.get("INVEST_NOTES_DIR") or REPO_ROOT / "notes" / "companies")


async def api_notes(request: Request):
    """Serve a company analysis .md file as rendered HTML."""
    import re

    ticker = request.path_params["ticker"].upper()
    # Sanitize: only allow alphanumeric, dots, hyphens (for tickers like BTC-USD, 4578.T)
    if not re.match(r"^[A-Z0-9._-]+$", ticker):
        return PlainTextResponse("Invalid ticker", status_code=400)

    # Folder layout takes priority (TICKER/thesis.md), then flat (TICKER.md).
    folder_path = NOTES_DIR / ticker / "thesis.md"
    flat_path = NOTES_DIR / f"{ticker}.md"
    if folder_path.is_file():
        md_path = folder_path
    elif flat_path.is_file():
        md_path = flat_path
    else:
        return HTMLResponse(
            f"<html><head><meta name='color-scheme' content='light dark'><style>"
            f":root {{ color-scheme: light dark; }}"
            f"body {{ background:#fff; color:#1f2328; font-family:system-ui;padding:40px; }}"
            f"@media (prefers-color-scheme: dark) {{ body {{ background:#0d1117; color:#e0e6ed; }} }}"
            f"</style></head><body>"
            f"<h2>No analysis notes for {ticker}</h2>"
            f"<p style='color:#738091;'>Create <code>notes/companies/{ticker}.md</code> "
            f"or <code>notes/companies/{ticker}/thesis.md</code> to add notes.</p>"
            f"</body></html>",
            status_code=404,
        )

    content = md_path.read_text(encoding="utf-8")
    # Simple markdown-to-HTML: use Python markdown if available, else serve raw
    try:
        import markdown

        body = markdown.markdown(content, extensions=["tables", "fenced_code"])
    except ImportError:
        body = f"<pre style='white-space:pre-wrap;'>{content}</pre>"

    html = (
        f"<html><head><title>{ticker} - Analysis</title>"
        f"<meta name='color-scheme' content='light dark'>"
        f"<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<style>"
        f":root {{ color-scheme: light dark; --background:#fff; --foreground:#1f2328; "
        f"--heading:#0969da; --border:#d0d7de; --surface:#f6f8fa; --strong:#24292f; }}"
        f"@media (prefers-color-scheme: dark) {{ :root {{ --background:#0d1117; --foreground:#e0e6ed; "
        f"--heading:#58a6ff; --border:#30363d; --surface:#161b22; --strong:#f0f6fc; }} }}"
        f"body {{ background:var(--background); color:var(--foreground); font-family:system-ui,-apple-system,sans-serif; "
        f"font-size:20px; padding:56px 80px; max-width:1060px; margin:0 auto; line-height:1.8; }}"
        f"h1 {{ color:var(--heading); font-size:2.4em; margin-top:1.6em; margin-bottom:0.6em; font-weight:700; "
        f"border-bottom:1px solid var(--border); padding-bottom:0.3em; }}"
        f"h2 {{ color:var(--heading); font-size:1.7em; margin-top:1.5em; margin-bottom:0.5em; font-weight:600; }}"
        f"h3 {{ color:var(--heading); font-size:1.3em; margin-top:1.3em; margin-bottom:0.4em; font-weight:600; }}"
        f"p {{ margin-bottom:0.9em; }}"
        f"ul,ol {{ margin-bottom:1em; padding-left:1.5em; }} li {{ margin-bottom:0.35em; }}"
        f"strong {{ color:var(--strong); }}"
        f"a {{ color:var(--heading); }}"
        f"code {{ background:var(--surface); padding:2px 7px; border-radius:4px; font-size:0.88em; }}"
        f"pre {{ background:var(--surface); padding:18px; border-radius:8px; overflow-x:auto; font-size:0.88em; }}"
        f"table {{ border-collapse:collapse; width:100%; font-size:1em; margin:1.2em 0; }} "
        f"th,td {{ border:1px solid var(--border); padding:12px 16px; text-align:left; }}"
        f"th {{ background:var(--surface); font-weight:600; color:var(--strong); }}"
        f"tr:hover {{ background:rgba(88,166,255,0.04); }}"
        f"@media(max-width:700px){{ body {{ padding:24px 18px; font-size:18px; }} }}"
        f".back-link {{ display:inline-block; margin-bottom:24px; padding:8px 12px; border:1px solid var(--border); border-radius:6px; color:var(--heading); text-decoration:none; font-size:14px; line-height:1.2; }}"
        f".back-link:hover {{ background:var(--surface); }}"
        f"</style></head><body><a class='back-link' href='/'>← Back to dashboard</a>{body}</body></html>"
    )
    return HTMLResponse(html)


# ── Helpers ──────────────────────────────────────────────────────────────

def _json_safe(obj):
    """Recursively convert datetime/date objects to ISO strings for JSON serialization."""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, datetime):
        return obj.isoformat(timespec="seconds")
    if hasattr(obj, 'isoformat'):
        return obj.isoformat()
    return obj


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _hours_ago(timestamp_str: str | None, now: datetime) -> float | None:
    if not timestamp_str:
        return None
    try:
        if isinstance(timestamp_str, datetime):
            ts = timestamp_str
        else:
            ts = datetime.fromisoformat(timestamp_str)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return round((now - ts).total_seconds() / 3600, 1)
    except (ValueError, TypeError):
        return None


# ── App ──────────────────────────────────────────────────────────────────

app = Starlette(
    routes=[
        Route("/", index),
        Route("/m", mobile_index),
        Route("/feed", feed_index),
        Route("/api/stocks", api_stocks),
        Route("/api/health", api_health),
        Route("/api/update", api_update_start, methods=["POST"]),
        Route("/api/update/status", api_update_status),
        Route("/api/update/cancel", api_update_cancel, methods=["POST"]),
        Route("/api/alarms", api_alarm_create, methods=["POST"]),
        Route("/api/alarms", api_alarm_list),
        Route("/api/alarms/triggered", api_alarm_triggered),
        Route("/api/alarms/{alarm_id:int}", api_alarm_delete, methods=["DELETE"]),
        Route("/api/reminders", api_reminder_create, methods=["POST"]),
        Route("/api/reminders", api_reminder_list),
        Route("/api/reminders/due", api_reminder_due),
        Route("/api/reminders/{reminder_id:int}/acknowledge", api_reminder_acknowledge, methods=["POST"]),
        Route("/api/reminders/{reminder_id:int}", api_reminder_delete, methods=["DELETE"]),
        Route("/api/insider/{ticker}", api_insider_history),
        Route("/api/notes/{ticker}", api_notes),
    ],
)


def main():
    parser = argparse.ArgumentParser(description="Live investment dashboard server")
    parser.add_argument("--port", type=int, default=8050, help="Port (default: 8050)")
    parser.add_argument("--host", default="::", help="Host (default: :: — IPv6, also accepts IPv4 on most systems)")
    parser.add_argument("--no-auto-shutdown", action="store_true", help="(ignored, kept for systemd compat)")
    args = parser.parse_args()

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    display_host = "[::1]" if args.host == "::" else ("127.0.0.1" if args.host == "0.0.0.0" else args.host)
    print(f"\n  Dashboard server starting at http://{display_host}:{args.port}")
    print(f"  Database: PostgreSQL (invest)\n")

    # Ensure alarm table exists
    _ensure_alarm_table()
    _ensure_reminder_table()

    # Start alarm checker (polls every 60s)
    alarm_checker.start()

    # Warm the data snapshot before serving so the first request is fast,
    # then keep it fresh in the background.
    print("  Warming data snapshot...")
    snapshot_cache.refresh()
    snapshot_cache.start_background_refresh()
    print(f"  Snapshot warm; refreshing every {REFRESH_INTERVAL}s\n")

    global _server_ref
    config = uvicorn.Config(app, host=args.host, port=args.port, log_level="info")
    server = uvicorn.Server(config)
    _server_ref = server
    server.run()


if __name__ == "__main__":
    main()
