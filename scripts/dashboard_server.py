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
import math
import os
import re
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
try:
    from invest.private_companies.dashboard import add_navigation, public_company, render_directory
except ImportError:
    add_navigation = public_company = render_directory = None

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
        self._catalog_cache: list[dict] | None = None
        self._catalog_stocks_id: int | None = None
        self._catalog_notes_dir: str | None = None

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
                self._catalog_cache = None
            return True

    def invalidate_notes_catalog(self):
        with self._lock:
            self._catalog_cache = None

    def get_notes_catalog(self) -> list[dict]:
        with self._lock:
            if (
                self._catalog_cache is not None
                and self._catalog_stocks_id == id(self._stocks_data)
                and self._catalog_notes_dir == str(NOTES_DIR)
            ):
                return self._catalog_cache

        stocks_data, _, _ = self.get()
        catalog = _build_notes_catalog(stocks_data)
        with self._lock:
            self._catalog_cache = catalog
            self._catalog_stocks_id = id(self._stocks_data)
            self._catalog_notes_dir = str(NOTES_DIR)
            return self._catalog_cache

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
    html = add_navigation(generator.generate_dashboard_html(stocks_data, progress_data, metadata))
    return HTMLResponse(html, headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})


async def mobile_index(request: Request) -> HTMLResponse:
    """Serve the mobile-optimized card-based dashboard."""
    _touch_activity()
    from invest.dashboard_components.html_generator import HTMLGenerator

    stocks_data, _, _ = snapshot_cache.get()
    generator = HTMLGenerator()
    html = add_navigation(generator.generate_mobile_html(stocks_data), mobile=True)
    return HTMLResponse(html, headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})


def _load_private_companies() -> tuple[list[dict], str]:
    """Read only explicitly publishable records; never expose raw DB errors."""
    from psycopg2.errors import UndefinedTable

    from invest.private_companies.repository import list_companies

    try:
        records = list_companies(public_only=True)
        companies = [projected for record in records
                     if (projected := public_company(record)) is not None]
        return companies, "ready"
    except UndefinedTable:
        return [], "not_initialized"
    except Exception:
        # Database exceptions may contain credentials or private record values.
        logger.warning("Private-company directory database unavailable")
        return [], "unavailable"


async def private_companies_index(request: Request) -> HTMLResponse:
    _touch_activity()
    companies, state = _load_private_companies()
    company_type = request.query_params.get("type", "all")
    if company_type not in {"all", "startup", "established", "unclassified"}:
        return PlainTextResponse("Unknown opportunity type", status_code=400)
    html = render_directory(companies, state=state, company_type=company_type,
                            query=request.query_params.get("q", ""))
    return HTMLResponse(html, status_code=503 if state == "unavailable" else 200,
                        headers={"Cache-Control": "no-store"})


async def api_private_companies(request: Request) -> JSONResponse:
    _touch_activity()
    companies, state = _load_private_companies()
    return JSONResponse({"status": state, "companies": companies},
                        status_code=503 if state == "unavailable" else 200,
                        headers={"Cache-Control": "no-store"})


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


# ── Insider history API ──────────────────────────────────────────────────


async def api_insider_history(request: Request) -> JSONResponse:
    """Return transaction history and daily insider signal snapshots for a ticker.

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

        # Prefer the dedicated reconstructed history. Fall back to scanner rows
        # while older deployments are being migrated.
        snapshot_rows = []
        try:
            cursor.execute("""
                SELECT date, insider_score, insider_buy_count, insider_sell_count,
                       insider_net_buy_pct, insider_sell_trend, insider_buy_trend,
                       insider_cluster_score, insider_dollar_conviction
                FROM insider_signal_history
                WHERE ticker = %s AND insider_score IS NOT NULL
                ORDER BY date
            """, (ticker,))
            snapshot_rows = cursor.fetchall()
        except Exception:
            conn.rollback()
            try:
                cursor.execute("""
                    SELECT date, insider_score, insider_buy_count, insider_sell_count,
                           insider_net_buy_pct, insider_sell_trend, insider_buy_trend,
                           insider_cluster_score, insider_dollar_conviction
                    FROM scanner_score_history
                    WHERE ticker = %s AND insider_score IS NOT NULL
                    ORDER BY date
                """, (ticker,))
                snapshot_rows = cursor.fetchall()
            except Exception:
                conn.rollback()
    except Exception:
        conn.rollback()
        return JSONResponse({"ok": True, "ticker": ticker, "months": [], "snapshots": []})
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

    snapshots = [
        {
            "date": date,
            "insider_score": float(insider_score),
            "buy_count": buy_count or 0,
            "sell_count": sell_count or 0,
            "net_buy_pct": float(net_buy_pct) if net_buy_pct is not None else None,
            "sell_trend": float(sell_trend) if sell_trend is not None else None,
            "buy_trend": float(buy_trend) if buy_trend is not None else None,
            "cluster_score": cluster_score or 0,
            "dollar_conviction": float(dollar_conviction) if dollar_conviction is not None else 0.0,
        }
        for (date, insider_score, buy_count, sell_count, net_buy_pct, sell_trend,
             buy_trend, cluster_score, dollar_conviction) in snapshot_rows
    ]

    return JSONResponse({
        "ok": True,
        "ticker": ticker,
        "months": list(month_map.values()),
        "snapshots": snapshots,
    })


# ── Notes (company .md files) ────────────────────────────────────────────

# Company analysis notes. Defaults to the corpus shipped with the repo; point
# INVEST_NOTES_DIR at your own directory to keep your notes separate from it.
NOTES_DIR = Path(os.environ.get("INVEST_NOTES_DIR") or REPO_ROOT / "notes" / "companies")
STOCK_CACHE_DIR = Path(os.environ.get("INVEST_STOCK_CACHE_DIR") or REPO_ROOT / "data" / "stock_cache")


def _calculate_llm_score(llm_val: dict, current_price: float | None = None) -> tuple[float | None, bool, dict]:
    """Compute risk-adjusted LLM score:
    - Verdict tier: BUY (100) / WATCH (0) / PASS (-100) / None (-200)
    - Entry actionable bonus: +50 if price <= entry_price and entry_price > 0
    - Reward/risk: min(ev_pct / max(abs(bear_return), 10.0), 10.0) * conviction_weight (HIGH: 1.9, MED-HIGH: 1.6, MED: 1.3, LOW: 1.0)
    Returns (score, has_valid_llm, details).
    """
    if not isinstance(llm_val, dict) or not llm_val:
        return None, False, {}

    details = llm_val.get("details", {})
    if isinstance(details, str):
        try:
            details = json.loads(details)
        except (json.JSONDecodeError, TypeError):
            details = {}
    elif not isinstance(details, dict):
        details = {}

    verdict = details.get("verdict") or llm_val.get("verdict")
    verdict_str = str(verdict).strip().upper() if verdict else ""

    if verdict_str == "BUY":
        verdict_tier = 100
        has_valid_llm = True
    elif verdict_str == "WATCH":
        verdict_tier = 0
        has_valid_llm = True
    elif verdict_str == "PASS":
        verdict_tier = -100
        has_valid_llm = True
    else:
        verdict_tier = -200
        has_valid_llm = False

    if not has_valid_llm:
        return None, False, details

    entry_price = details.get("entry_price") or llm_val.get("entry_price")
    actionable_bonus = 0
    try:
        if current_price is not None and entry_price is not None:
            p = float(current_price)
            ep = float(entry_price)
            if ep > 0 and p > 0 and p <= ep:
                actionable_bonus = 50
    except (ValueError, TypeError):
        pass

    ev_pct = details.get("expected_value_pct")
    if ev_pct is None:
        ev_pct = llm_val.get("upside") or llm_val.get("expected_value_pct")
    try:
        ev_val = float(ev_pct) if ev_pct is not None else 0.0
    except (ValueError, TypeError):
        ev_val = 0.0

    scenarios = details.get("scenarios") or llm_val.get("scenarios") or {}
    bear_return = None
    if isinstance(scenarios, dict):
        for s_name, s_val in scenarios.items():
            if "bear" in str(s_name).lower():
                if isinstance(s_val, dict):
                    bear_return = s_val.get("return_pct")
                elif isinstance(s_val, (int, float)):
                    bear_return = float(s_val)
    if bear_return is None and "bear" in details:
        b = details["bear"]
        if isinstance(b, dict):
            bear_return = b.get("return_pct")
        elif isinstance(b, (int, float)):
            bear_return = float(b)

    try:
        if bear_return is not None:
            denom = max(abs(float(bear_return)), 10.0)
        else:
            denom = 10.0
        rr_ratio = min(ev_val / denom, 10.0)
    except (ValueError, TypeError):
        rr_ratio = 0.0

    conviction = details.get("conviction") or llm_val.get("conviction") or ""
    conv_str = str(conviction).strip().upper()
    if "MED" in conv_str and "HIGH" in conv_str:
        conviction_weight = 1.6
    elif "HIGH" in conv_str:
        conviction_weight = 1.9
    elif "MED" in conv_str:
        conviction_weight = 1.3
    elif "LOW" in conv_str:
        conviction_weight = 1.0
    else:
        conviction_weight = 1.0

    reward_risk = rr_ratio * conviction_weight
    score = verdict_tier + actionable_bonus + reward_risk
    return round(score, 2), True, details


def _build_notes_catalog(stocks_data: dict) -> list[dict]:
    catalog = []
    for ticker, stock in stocks_data.items():
        if not isinstance(stock, dict):
            continue

        current_price = stock.get("current_price")
        valuations = stock.get("valuations", {}) if isinstance(stock.get("valuations"), dict) else {}
        llm_val = valuations.get("llm_deep_analysis", {}) if isinstance(valuations, dict) else {}

        score, has_valid_llm, details = _calculate_llm_score(llm_val, current_price)

        # Check note availability against NOTES_DIR
        folder_note = NOTES_DIR / ticker / "thesis.md"
        flat_note = NOTES_DIR / f"{ticker}.md"
        has_note = folder_note.is_file() or flat_note.is_file()
        has_visual = (NOTES_DIR / ticker / "visual-report.html").is_file()

        entry_price = details.get("entry_price") or (llm_val.get("entry_price") if isinstance(llm_val, dict) else None)
        entry_actionable = None
        try:
            if current_price is not None and entry_price is not None:
                p = float(current_price)
                ep = float(entry_price)
                if ep > 0 and p > 0:
                    entry_actionable = p <= ep
        except (ValueError, TypeError):
            pass

        # Best margin of safety across non-failed valuations
        margins = []
        for m_name, m_val in valuations.items():
            if isinstance(m_val, dict) and not m_val.get("failed", False):
                margin = m_val.get("margin_of_safety")
                if margin is not None:
                    try:
                        margins.append(float(margin))
                    except (ValueError, TypeError):
                        pass
        best_margin = max(margins) if margins else None

        item = {
            "ticker": ticker,
            "company_name": stock.get("company_name", ticker),
            "current_price": current_price,
            "currency": stock.get("currency"),
            "sector": stock.get("sector"),
            "industry": stock.get("industry"),
            "country": stock.get("country"),
            "status": stock.get("status", "completed"),
            "has_note": has_note,
            "note_available": has_note,
            "has_visual": has_visual,
            "has_llm": has_valid_llm,
            "verdict": details.get("verdict") or (llm_val.get("verdict") if isinstance(llm_val, dict) else None),
            "conviction": details.get("conviction") or (llm_val.get("conviction") if isinstance(llm_val, dict) else None),
            "expected_value_pct": details.get("expected_value_pct") if details.get("expected_value_pct") is not None else (llm_val.get("upside") if isinstance(llm_val, dict) else None),
            "target_price": (llm_val.get("fair_value") if isinstance(llm_val, dict) else None),
            "fair_value": (llm_val.get("fair_value") if isinstance(llm_val, dict) else None),
            "entry_price": entry_price,
            "thesis_break_price": details.get("thesis_break_price"),
            "quality_score": details.get("quality_score"),
            "entry_actionable": entry_actionable,
            "risk_adjusted_score": score,
            "llm_score": score,
            "best_margin": best_margin,
            "scenarios": details.get("scenarios") or (llm_val.get("scenarios") if isinstance(llm_val, dict) else {}),
            "valuations": valuations,
        }
        catalog.append(item)

    def sort_key(item):
        has_llm_key = 0 if item["has_llm"] else 1
        score_val = item["risk_adjusted_score"] if item["risk_adjusted_score"] is not None else -999999.0
        margin_val = item["best_margin"] if item["best_margin"] is not None else -999.0
        return (has_llm_key, -score_val, -margin_val, item["ticker"])

    catalog.sort(key=sort_key)
    return catalog


async def api_notes_catalog(request: Request) -> JSONResponse:
    """Return a JSON list of all stocks enriched with LLM rating metrics and note availability."""
    _touch_activity()
    catalog = snapshot_cache.get_notes_catalog()
    return JSONResponse(_json_safe(catalog), headers={"Cache-Control": "no-store"})


async def api_notes_ticker_data(request: Request) -> JSONResponse:
    """Return fundamentals, financial statements, and price data from stock_cache."""
    _touch_activity()
    raw_ticker = request.path_params.get("ticker", "").strip()
    if not raw_ticker or not re.match(r"^[A-Za-z0-9._-]+$", raw_ticker):
        return JSONResponse({"error": "Invalid ticker", "ticker": raw_ticker}, status_code=400)

    ticker = raw_ticker.upper()
    cache_file = STOCK_CACHE_DIR / f"{ticker}.json"
    if not cache_file.is_file():
        cache_file = STOCK_CACHE_DIR / f"{raw_ticker}.json"
        if not cache_file.is_file():
            return JSONResponse(
                {
                    "error": f"No cached data found for {ticker}",
                    "ticker": ticker,
                    "info": {},
                    "financials": {},
                    "price_data": {},
                    "financial_statements_currency": None,
                    "income": {},
                    "balance_sheet": {},
                    "cashflow": {},
                },
                status_code=404,
            )

    try:
        content = cache_file.read_text(encoding="utf-8")
        if not content.strip():
            return JSONResponse({"error": f"Empty data for {ticker}", "ticker": ticker}, status_code=404)
        data = json.loads(content)
        if not data or not isinstance(data, dict):
            return JSONResponse({"error": f"Empty data for {ticker}", "ticker": ticker}, status_code=404)
    except Exception as exc:
        logger.warning("Error reading stock cache for %s: %s", ticker, exc)
        return JSONResponse({"error": f"Failed to read cache for {ticker}", "ticker": ticker}, status_code=500)

    payload = {
        "ticker": data.get("ticker", ticker),
        "info": data.get("info", {}),
        "financials": data.get("financials", {}),
        "price_data": data.get("price_data", {}),
        "financial_statements_currency": data.get("financial_statements_currency"),
        "income": data.get("income", {}),
        "balance_sheet": data.get("balance_sheet", {}),
        "cashflow": data.get("cashflow", {}),
    }
    return JSONResponse(_json_safe(payload), headers={"Cache-Control": "no-store"})


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
    has_visual = (NOTES_DIR / ticker / "visual-report.html").is_file()

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
    from notes_view import render_notes_page

    catalog = snapshot_cache._catalog_cache
    html = render_notes_page(ticker, content, has_visual_report=has_visual, notes_catalog=catalog)
    return HTMLResponse(html)


def _build_notes_chart_engine() -> str:
    """Build the client-side interactive TIKR-style table-to-chart engine."""
    return """
<!-- Chart.js CDN -->
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>

<style>
/* TIKR Interactive Chart Engine */
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
.tikr-btn:not(:last-child) {
  border-right: 1px solid var(--border);
}
.tikr-btn:hover {
  background: var(--surface);
  color: var(--heading);
}
.tikr-btn.active {
  background: var(--heading);
  color: #fff;
}
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
.tikr-toggle-btn:hover {
  border-color: var(--heading);
}
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
.tikr-pill:hover {
  border-color: var(--heading);
  color: var(--heading);
}
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

/* Table Interactive States */
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
tr.tikr-clickable-row:hover .tikr-row-dot {
  opacity: 0.5;
}
tr.tikr-clickable-row.active-row .tikr-row-dot {
  opacity: 1;
}

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
  background: rgba(127,127,127,0.1);
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
  font-weight: 600;
  color: #fff;
  white-space: nowrap;
  transition: width 0.5s cubic-bezier(0.4, 0, 0.2, 1);
}
.scenario-bar-meta {
  width: 120px;
  text-align: right;
  font-size: 13px;
  font-weight: 600;
}
</style>

<script>
(function() {
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

  const PALETTE = [
    { border: '#0969da', bg: 'rgba(9, 105, 218, 0.18)', darkBorder: '#58a6ff', darkBg: 'rgba(88, 166, 255, 0.18)' },
    { border: '#2da44e', bg: 'rgba(45, 164, 78, 0.18)', darkBorder: '#3fb950', darkBg: 'rgba(63, 185, 80, 0.18)' },
    { border: '#8250df', bg: 'rgba(130, 80, 223, 0.18)', darkBorder: '#bc8cff', darkBg: 'rgba(188, 140, 255, 0.18)' },
    { border: '#d97706', bg: 'rgba(217, 119, 6, 0.18)', darkBorder: '#f59e0b', darkBg: 'rgba(245, 158, 11, 0.18)' },
    { border: '#cf222e', bg: 'rgba(207, 34, 46, 0.18)', darkBorder: '#f85149', darkBg: 'rgba(248, 81, 73, 0.18)' }
  ];

  function isDark() {
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  }

  function initTikrTable(table) {
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

    trs.forEach((tr, rowIdx) => {
      const tds = Array.from(tr.querySelectorAll('td'));
      if (tds.length <= Math.max(...timeColIndices)) return;

      const metricCell = tds[0];
      const metricName = metricCell.innerText.replace(/\\*\\*/g, '').trim();
      const values = timeColIndices.map(colIdx => parseValue(tds[colIdx].innerText));
      const validCount = values.filter(v => v !== null).length;

      if (validCount >= 2) {
        parsedRows.push({
          idx: rowIdx,
          tr: tr,
          metricName: metricName,
          values: values,
          summary: tds[tds.length - 1] ? tds[tds.length - 1].innerText.trim() : ''
        });

        tr.classList.add('tikr-clickable-row');
        const dot = document.createElement('span');
        dot.className = 'tikr-row-dot';
        metricCell.prepend(dot);
      }
    });

    if (!parsedRows.length) return;

    // Create Chart Widget Element
    const widget = document.createElement('div');
    widget.className = 'tikr-chart-widget';

    widget.innerHTML = `
      <div class="tikr-chart-header">
        <div class="tikr-title-group">
          <div class="tikr-metric-name">
            <span class="chart-icon">📈</span>
            <span class="title-text">Loading...</span>
          </div>
          <div class="tikr-meta-badges">
            <span class="tikr-badge tikr-badge-val latest-badge">-</span>
            <span class="tikr-badge tikr-badge-growth growth-badge">-</span>
          </div>
        </div>
        <div class="tikr-controls">
          <div class="tikr-btn-group">
            <button class="tikr-btn active btn-area" type="button">Area</button>
            <button class="tikr-btn btn-bar" type="button">Bar</button>
          </div>
          <button class="tikr-toggle-btn btn-compare" type="button">➕ Compare</button>
        </div>
      </div>
      <div class="tikr-pills-row">
        <span class="tikr-pill-label">Quick Jump:</span>
      </div>
      <div class="tikr-canvas-container">
        <canvas class="tikr-canvas"></canvas>
      </div>
      <div class="tikr-footer-hint">
        <span>💡 <b>TIKR Mode:</b> Click any table row to plot it. Shift+click to compare metrics.</span>
        <span class="point-count-label"></span>
      </div>
    `;

    table.parentNode.insertBefore(widget, table);

    // Populate quick jump pills
    const pillsRow = widget.querySelector('.tikr-pills-row');
    const priorityKeywords = ['Revenue', 'EBITDA', 'Net Income', 'Operating Cash Flow', 'Free Cash Flow', 'Net Debt'];
    const quickItems = [];

    priorityKeywords.forEach(kw => {
      const found = parsedRows.find(r => r.metricName.toLowerCase().includes(kw.toLowerCase()));
      if (found && !quickItems.includes(found)) {
        quickItems.push(found);
      }
    });

    quickItems.forEach(item => {
      const pill = document.createElement('button');
      pill.className = 'tikr-pill';
      pill.type = 'button';
      pill.textContent = item.metricName.split('(')[0].trim();
      pill.addEventListener('click', () => {
        selectSingleRow(item);
      });
      pillsRow.appendChild(pill);
    });

    const canvas = widget.querySelector('.tikr-canvas');
    let chartType = 'line';
    let compareMode = false;
    let selectedRows = [parsedRows[0]];

    let chartInstance = null;

    function buildDatasets() {
      const dark = isDark();
      return selectedRows.map((row, idx) => {
        const pal = PALETTE[idx % PALETTE.length];
        const borderColor = dark ? pal.darkBorder : pal.border;
        const bgColor = dark ? pal.darkBg : pal.bg;
        const dataVals = row.values.map(v => v ? v.val : null);

        return {
          label: row.metricName,
          data: dataVals,
          borderColor: borderColor,
          backgroundColor: chartType === 'line' ? bgColor : borderColor,
          fill: chartType === 'line',
          tension: 0.35,
          borderWidth: 2.5,
          pointRadius: 5,
          pointHoverRadius: 7,
          pointBackgroundColor: borderColor,
          borderRadius: 4
        };
      });
    }

    function renderChart() {
      if (!window.Chart) return;
      const dark = isDark();
      const gridColor = dark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.06)';
      const textColor = dark ? '#e0e6ed' : '#1f2328';

      if (chartInstance) {
        chartInstance.destroy();
      }

      const datasets = buildDatasets();
      const firstRow = selectedRows[0];
      const isPercent = firstRow.values.some(v => v && v.isPercent);
      const isMultiple = firstRow.values.some(v => v && v.isMultiple);

      chartInstance = new Chart(canvas, {
        type: chartType,
        data: {
          labels: timeLabels,
          datasets: datasets
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: {
            mode: 'index',
            intersect: false
          },
          plugins: {
            legend: {
              display: selectedRows.length > 1,
              labels: { color: textColor, font: { weight: '600' } }
            },
            tooltip: {
              backgroundColor: dark ? '#161b22' : '#ffffff',
              titleColor: dark ? '#58a6ff' : '#0969da',
              bodyColor: textColor,
              borderColor: dark ? '#30363d' : '#d0d7de',
              borderWidth: 1,
              padding: 10,
              boxPadding: 4,
              callbacks: {
                label: function(ctx) {
                  const r = selectedRows[ctx.datasetIndex];
                  const rawVal = r && r.values[ctx.dataIndex] ? r.values[ctx.dataIndex].raw : ctx.formattedValue;
                  return ' ' + ctx.dataset.label + ': ' + rawVal;
                }
              }
            }
          },
          scales: {
            x: {
              grid: { color: gridColor },
              ticks: { color: textColor, font: { weight: '600' } }
            },
            y: {
              grid: { color: gridColor },
              ticks: {
                color: textColor,
                callback: function(val) {
                  if (isPercent) return val + '%';
                  if (isMultiple) return val + 'x';
                  return val;
                }
              }
            }
          }
        }
      });

      updateHeader();
      updateTableHighlight();
    }

    function updateHeader() {
      const titleEl = widget.querySelector('.title-text');
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

      // Update pills
      widget.querySelectorAll('.tikr-pill').forEach(pill => {
        const match = selectedRows.some(r => r.metricName.toLowerCase().startsWith(pill.textContent.toLowerCase()));
        pill.classList.toggle('active', match);
      });
    }

    function selectSingleRow(row) {
      selectedRows = [row];
      renderChart();
    }

    function toggleRow(row) {
      const idx = selectedRows.indexOf(row);
      if (idx >= 0) {
        if (selectedRows.length > 1) {
          selectedRows.splice(idx, 1);
        }
      } else {
        if (selectedRows.length >= 5) selectedRows.shift();
        selectedRows.push(row);
      }
      renderChart();
    }

    // Attach row clicks
    parsedRows.forEach(r => {
      r.tr.addEventListener('click', (e) => {
        if (compareMode || e.shiftKey || e.metaKey || e.ctrlKey) {
          toggleRow(r);
        } else {
          selectSingleRow(r);
        }
      });
    });

    // Controls
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

    // Initial render
    renderChart();
  }

  function initScenarioChart(table) {
    const ths = Array.from(table.querySelectorAll('th')).map(th => th.innerText.toLowerCase());
    const isScenarioTable = ths.some(h => h.includes('scenario')) && ths.some(h => h.includes('target') || h.includes('return'));
    if (!isScenarioTable) return;

    const targetColIdx = ths.findIndex(h => h.includes('target') || h.includes('fair value'));
    const returnColIdx = ths.findIndex(h => h.includes('return') || h.includes('upside'));
    if (targetColIdx < 0) return;

    const trs = Array.from(table.querySelectorAll('tr')).filter(tr => tr.querySelectorAll('td').length > targetColIdx);
    const scenarios = [];

    trs.forEach(tr => {
      const tds = Array.from(tr.querySelectorAll('td'));
      const name = tds[0].innerText.replace(/\\*\\*/g, '').trim();
      const targetText = tds[targetColIdx].innerText.trim();
      const returnText = returnColIdx >= 0 && tds[returnColIdx] ? tds[returnColIdx].innerText.trim() : '';

      const valMatch = targetText.match(/[$€¥£]?\\s*([0-9]+(?:\\.[0-9]+)?)/);
      if (valMatch) {
        const val = parseFloat(valMatch[1]);
        scenarios.push({
          name: name,
          val: val,
          targetRaw: targetText,
          returnRaw: returnText
        });
      }
    });

    if (scenarios.length < 2) return;

    // Detect current price from page header if possible
    let currentPrice = null;
    const bodyText = document.body.innerText;
    const priceMatch = bodyText.match(/Price:\\*?\\*?\\s*[$€¥£]?([0-9]+(?:\\.[0-9]+)?)/i);
    if (priceMatch) {
      currentPrice = parseFloat(priceMatch[1]);
    }

    const maxVal = Math.max(...scenarios.map(s => s.val), currentPrice || 0) * 1.15;

    const widget = document.createElement('div');
    widget.className = 'scenario-chart-widget';
    widget.innerHTML = `
      <div class="scenario-chart-title">🎯 Valuation Scenario & Target Price Distribution</div>
      <div class="scenario-chart-sub">Visual price target comparison relative to current market price (${currentPrice ? 'Current: €' + currentPrice.toFixed(2) : ''})</div>
      <div class="scenario-bar-list"></div>
    `;

    const list = widget.querySelector('.scenario-bar-list');

    // Add current price benchmark
    if (currentPrice) {
      const pct = (currentPrice / maxVal) * 100;
      const curRow = document.createElement('div');
      curRow.className = 'scenario-bar-row';
      curRow.innerHTML = `
        <div class="scenario-bar-name">📍 Current Price</div>
        <div class="scenario-bar-track-wrap">
          <div class="scenario-bar-fill" style="width: ${pct}%; background: var(--heading); opacity: 0.85;">
            €${currentPrice.toFixed(2)}
          </div>
        </div>
        <div class="scenario-bar-meta">Market Anchor</div>
      `;
      list.appendChild(curRow);
    }

    scenarios.forEach(s => {
      const pct = (s.val / maxVal) * 100;
      let color = '#0969da';
      if (s.name.toLowerCase().includes('bull')) color = '#2ea043';
      else if (s.name.toLowerCase().includes('bear')) color = '#cf222e';
      else if (s.name.toLowerCase().includes('base')) color = '#0969da';

      const row = document.createElement('div');
      row.className = 'scenario-bar-row';
      row.innerHTML = `
        <div class="scenario-bar-name">${s.name} Case</div>
        <div class="scenario-bar-track-wrap">
          <div class="scenario-bar-fill" style="width: ${pct}%; background: ${color};">
            ${s.targetRaw}
          </div>
        </div>
        <div class="scenario-bar-meta" style="color: ${s.returnRaw.includes('-') ? '#cf222e' : '#2ea043'};">
          ${s.returnRaw}
        </div>
      `;
      list.appendChild(row);
    });

    table.parentNode.insertBefore(widget, table);
  }

  function init() {
    const tables = document.querySelectorAll('table');
    tables.forEach(table => {
      initTikrTable(table);
      initScenarioChart(table);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
</script>
"""


_TIKR_CACHE_FILE = REPO_ROOT / "data" / "tikr_cache.json"
_TIKR_CACHE: dict[str, str] = {}



def _resolve_tikr_url(ticker: str, company_name: str = "") -> str:
    """Resolve TIKR URL using Algolia search to find cid and tid, with file-backed caching."""
    global _TIKR_CACHE
    if not _TIKR_CACHE and _TIKR_CACHE_FILE.is_file():
        try:
            import json
            _TIKR_CACHE = json.loads(_TIKR_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            _TIKR_CACHE = {}

    if ticker in _TIKR_CACHE:
        return _TIKR_CACHE[ticker]

    import json
    import urllib.request

    suffix_map = {
        "MC": "BME",
        "T": "TSE",
        "L": "LSE",
        "DE": "XTRA",
        "PA": "ENXTPA",
        "AS": "ENXTAM",
    }
    parts = ticker.split(".")
    clean_t = parts[0]
    expected_exch = suffix_map.get(parts[1].upper()) if len(parts) > 1 else None

    queries = [clean_t]
    if company_name:
        first_word = company_name.split()[0]
        if first_word.lower() not in [clean_t.lower(), "the"]:
            queries.append(first_word)
        queries.append(company_name)

    for q in queries:
        payload = {
            "requests": [{"indexName": "tikr-terminal-v1", "query": q, "params": "hitsPerPage=10"}]
        }
        req = urllib.request.Request(
            "https://tjpay1dyt8-dsn.algolia.net/1/indexes/*/queries?x-algolia-api-key=d88ea2aa3c22293c96736f5ceb5bab4e&x-algolia-application-id=TJPAY1DYT8",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            res = json.loads(urllib.request.urlopen(req, timeout=2.5).read().decode("utf-8"))
            hits = res.get("results", [{}])[0].get("hits", [])
            if expected_exch:
                for h in hits:
                    if h.get("tickersymbol", "").upper() == clean_t.upper() and h.get("exchangesymbol", "").upper() == expected_exch:
                        url = f"https://app.tikr.com/stock/about?cid={h['companyid']}&tid={h['tradingitemid']}"
                        _TIKR_CACHE[ticker] = url
                        _save_tikr_cache()
                        return url
            for h in hits:
                if h.get("tickersymbol", "").upper() == clean_t.upper():
                    url = f"https://app.tikr.com/stock/about?cid={h['companyid']}&tid={h['tradingitemid']}"
                    _TIKR_CACHE[ticker] = url
                    _save_tikr_cache()
                    return url
            if company_name:
                for h in hits:
                    cname = h.get("companyname", "").lower()
                    if company_name.lower() in cname or cname in company_name.lower():
                        url = f"https://app.tikr.com/stock/about?cid={h['companyid']}&tid={h['tradingitemid']}"
                        _TIKR_CACHE[ticker] = url
                        _save_tikr_cache()
                        return url
        except Exception:
            continue

    fallback_url = f"https://app.tikr.com/stock/about?ticker={ticker}"
    _TIKR_CACHE[ticker] = fallback_url
    return fallback_url


def _save_tikr_cache():
    try:
        import json
        _TIKR_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _TIKR_CACHE_FILE.write_text(json.dumps(_TIKR_CACHE, indent=2), encoding="utf-8")
    except Exception:
        pass


def _build_notes_header_html(ticker: str, content: str, has_visual_report: bool = False) -> str:
    """Build a clean action bar with links to external resources for the company."""
    import re
    import urllib.parse

    # 1. Company name from markdown header: "# Company Name (TICKER)"
    m_title = re.search(r"^#\s+([^\n(]+)", content, re.MULTILINE)
    company_name = m_title.group(1).strip() if m_title else ticker

    # 2. Extract official website & investor relations links if present in note
    m_web = re.search(r"\[(?:Official\s+)?Website\]\((https?://[^\)]+)\)", content, re.IGNORECASE)
    website_url = m_web.group(1) if m_web else None

    m_ir = re.search(r"\[(?:Investor\s+Relations|IR|Shareholder)\s*[^\]]*\]\((https?://[^\)]+)\)", content, re.IGNORECASE)
    ir_url = m_ir.group(1) if m_ir else None

    # TIKR URL extraction or dynamic resolution
    m_tikr = re.search(r"\[TIKR\]\((https?://app\.tikr\.com/[^\)]+)\)", content, re.IGNORECASE)
    if m_tikr and "cid=" in m_tikr.group(1):
        tikr_url = m_tikr.group(1)
    else:
        tikr_url = _resolve_tikr_url(ticker, company_name)

    # Secondary heuristic: look for investor.<domain> or ir.<domain> in text
    if not ir_url:
        m_ir_auto = re.search(r"(https?://(?:investor|ir)\.[a-zA-Z0-9.-]+[a-zA-Z0-9/_-]*)", content)
        if m_ir_auto:
            ir_url = m_ir_auto.group(1).rstrip(".,;)")

    # Secondary heuristic for website: check data/stock_cache if present
    if not website_url:
        cache_file = STOCK_CACHE_DIR / f"{ticker}.json"
        if cache_file.is_file():
            try:
                import json
                cdata = json.loads(cache_file.read_text(encoding="utf-8"))
                website_url = cdata.get("info", {}).get("website")
                if not ir_url:
                    ir_url = cdata.get("info", {}).get("irWebsite")
            except Exception:
                pass

    encoded_name = urllib.parse.quote_plus(company_name)
    encoded_ticker = urllib.parse.quote_plus(ticker)

    # Fallbacks if still not found
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

    # Regulatory filings portal
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

    visual_btn = ""
    if has_visual_report:
        visual_btn = f"<a class='nav-btn highlight-btn' href='/api/notes/{ticker}/visual' target='_blank'>🎨 Visual Companion</a>"

    return (
        f"<div class='note-toolbar'>"
        f"<div class='toolbar-left'>"
        f"<a class='nav-btn back-btn' href='/'>← Dashboard</a>"
        f"{visual_btn}"
        f"</div>"
        f"<div class='toolbar-right'>"
        f"<a class='nav-btn' href='{website_url}' target='_blank' rel='noopener'>{web_label}</a>"
        f"<a class='nav-btn' href='{ir_url}' target='_blank' rel='noopener'>{ir_label}</a>"
        f"<a class='nav-btn' href='{tikr_url}' target='_blank' rel='noopener'>📈 TIKR</a>"
        f"<a class='nav-btn' href='https://finance.yahoo.com/quote/{ticker}' target='_blank' rel='noopener'>📊 Yahoo Finance</a>"
        f"<a class='nav-btn' href='https://www.google.com/finance/quote/{ticker}' target='_blank' rel='noopener'>🔍 Google Finance</a>"
        f"<a class='nav-btn' href='https://www.tradingview.com/symbols/{ticker}/' target='_blank' rel='noopener'>📉 TradingView</a>"
        f"<a class='nav-btn' href='{filings_url}' target='_blank' rel='noopener'>{filings_label}</a>"
        f"</div>"
        f"</div>"
    )


async def api_visual_report(request: Request):
    """Serve a company visual-report.html companion file if it exists."""
    import re
    ticker = request.path_params["ticker"].upper()
    if not re.match(r"^[A-Z0-9._-]+$", ticker):
        return PlainTextResponse("Invalid ticker", status_code=400)
    report_path = NOTES_DIR / ticker / "visual-report.html"
    if not report_path.is_file():
        return PlainTextResponse(f"No visual report found for {ticker}", status_code=404)
    return HTMLResponse(report_path.read_text(encoding="utf-8"))


# ── Helpers ──────────────────────────────────────────────────────────────

def _json_safe(obj):
    """Recursively convert datetime/date objects to ISO strings and NaN/Inf to None for JSON serialization."""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
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
        Route("/private-companies", private_companies_index),
        Route("/api/private-companies", api_private_companies),
        Route("/api/stocks", api_stocks),
        Route("/api/health", api_health),
        Route("/api/update", api_update_start, methods=["POST"]),
        Route("/api/update/status", api_update_status),
        Route("/api/update/cancel", api_update_cancel, methods=["POST"]),
        Route("/api/alarms", api_alarm_create, methods=["POST"]),
        Route("/api/alarms", api_alarm_list),
        Route("/api/alarms/triggered", api_alarm_triggered),
        Route("/api/alarms/{alarm_id:int}", api_alarm_delete, methods=["DELETE"]),
        Route("/api/insider/{ticker}", api_insider_history),
        Route("/api/notes/catalog", api_notes_catalog),
        Route("/api/notes/{ticker}/data", api_notes_ticker_data),
        Route("/api/notes/{ticker}", api_notes),
        Route("/api/notes/{ticker}/visual", api_visual_report),
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
    print("  Database: PostgreSQL (invest)\n")

    # Ensure alarm table exists
    _ensure_alarm_table()

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
