#!/usr/bin/env python3
"""
Price target alerts — notify when watchlist stocks enter buy zones.

Reads price targets from PRICE_ALERTS below, checks current prices from the DB,
and prints a Telegram-formatted message for any stock in its buy zone.

Usage:
    uv run python scripts/price_alerts.py              # Check all alerts
    uv run python scripts/price_alerts.py --dry-run    # Preview without recording
    uv run python scripts/price_alerts.py --status     # Show all alerts and current prices

Designed to run daily after data fetch (plug into update_all.py or cron).
stdout is captured by scan_and_notify.sh for Telegram delivery.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from invest.data.db import get_connection


@dataclass
class PriceAlert:
    ticker: str
    buy_below: float  # Upper bound of buy zone
    target_low: float  # Lower bound of buy zone (ideal entry)
    thesis: str  # Why we're watching
    verdict: str  # BUY / WATCH / PASS


# ── Alert definitions ──────────────────────────────────────────────
# Edit this list to add/remove price alerts.
PRICE_ALERTS: list[PriceAlert] = [
    # Starship beneficiaries (2026-04-05 research)
    PriceAlert("RKLB", 45.0, 38.0, "Best pure-play space co, 18/25 quality. Buy on Neutron progress or pullback.", "WATCH"),
    PriceAlert("LIN", 450.0, 425.0, "World-class industrial gas oligopoly, 21/25 quality. Buy at fair value.", "WATCH"),
    PriceAlert("ASTS", 70.0, 55.0, "Biggest Starship beneficiary (massive sats). Buy after Block 2 proof or pullback.", "WATCH"),
    PriceAlert("PL", 22.0, 18.0, "Great earth imaging biz, 1000% run. Buy at sane valuation.", "PASS"),
    PriceAlert("APD", 270.0, 260.0, "Activist turnaround, capex peak behind. Buy on pullback.", "WATCH"),
    PriceAlert("RDW", 7.0, 6.0, "Only public in-space mfg. Buy if margins recover.", "WATCH"),
    PriceAlert("LUNR", 16.0, 14.0, "Lunar landers. Buy after clean landing + Lanteris EBITDA proof.", "PASS"),
]


def get_current_prices(tickers: list[str]) -> dict[str, float | None]:
    """Fetch current prices from the database."""
    conn = get_connection()
    cursor = conn.cursor()
    placeholders = ",".join(["%s"] * len(tickers))
    cursor.execute(
        f"SELECT ticker, current_price FROM current_stock_data WHERE ticker IN ({placeholders})",
        tickers,
    )
    prices = {row[0]: float(row[1]) if row[1] else None for row in cursor.fetchall()}
    conn.close()
    return prices


def check_alerted_today(ticker: str) -> bool:
    """Check if we already sent an alert for this ticker today."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM price_alert_history WHERE ticker = %s AND alert_date = %s",
        (ticker, date.today()),
    )
    exists = cursor.fetchone() is not None
    conn.close()
    return exists


def record_alert(ticker: str, price: float, buy_below: float) -> None:
    """Record that we sent an alert for this ticker today."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO price_alert_history (ticker, alert_date, price_at_alert, buy_below_target)
           VALUES (%s, %s, %s, %s)
           ON CONFLICT (ticker, alert_date) DO NOTHING""",
        (ticker, date.today(), price, buy_below),
    )
    conn.commit()
    conn.close()


def ensure_table() -> None:
    """Create the price_alert_history table if it doesn't exist."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS price_alert_history (
            ticker VARCHAR(20) NOT NULL,
            alert_date DATE NOT NULL,
            price_at_alert NUMERIC(12, 4),
            buy_below_target NUMERIC(12, 4),
            PRIMARY KEY (ticker, alert_date)
        )
    """)
    conn.commit()
    conn.close()


def format_alert(alert: PriceAlert, price: float) -> str:
    """Format a single price alert for Telegram."""
    pct_below = (alert.buy_below - price) / alert.buy_below * 100
    zone = "🎯 TARGET ZONE" if price <= alert.buy_below else "⚠️ APPROACHING"
    ideal = "✅ IDEAL ENTRY" if price <= alert.target_low else ""

    lines = [
        f"🚨 **[{alert.ticker}](https://finance.yahoo.com/quote/{alert.ticker})** — PRICE ALERT",
        "═" * 30,
        f"{zone} {ideal}",
        "",
        f"💰 Current: **${price:.2f}**",
        f"🎯 Buy zone: ${alert.target_low:.0f} – ${alert.buy_below:.0f}",
        f"📉 {pct_below:.1f}% below upper target",
        "",
        f"📝 {alert.thesis}",
        "",
        f"🔎 [Chart](https://finance.yahoo.com/quote/{alert.ticker})",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Price target alerts")
    parser.add_argument("--dry-run", action="store_true", help="Preview without recording")
    parser.add_argument("--status", action="store_true", help="Show all alerts and current prices")
    parser.add_argument("--quiet", action="store_true", help="Only output alert messages")
    args = parser.parse_args()

    ensure_table()

    tickers = [a.ticker for a in PRICE_ALERTS]
    prices = get_current_prices(tickers)

    if args.status:
        print("\n🎯 Price Alert Status")
        print("=" * 70)
        print(f"{'Ticker':<8} {'Price':>8} {'Buy Zone':>14} {'Distance':>10} {'Status':<12}")
        print("-" * 70)
        for alert in PRICE_ALERTS:
            price = prices.get(alert.ticker)
            if price is None:
                print(f"{alert.ticker:<8} {'N/A':>8} ${alert.target_low:.0f}-${alert.buy_below:.0f}     {'NO DATA':>10} {alert.verdict}")
                continue
            if price <= alert.target_low:
                status = "🟢 IDEAL"
                dist = f"-{(alert.target_low - price) / alert.target_low * 100:.1f}%"
            elif price <= alert.buy_below:
                status = "🟡 IN ZONE"
                dist = f"-{(alert.buy_below - price) / alert.buy_below * 100:.1f}%"
            else:
                pct_above = (price - alert.buy_below) / alert.buy_below * 100
                status = "🔴 ABOVE"
                dist = f"+{pct_above:.0f}%"
            print(f"{alert.ticker:<8} ${price:>7.2f} ${alert.target_low:.0f}-${alert.buy_below:.0f}     {dist:>10} {status}")
        return 0

    # Check for alerts
    alerts_triggered = []
    for alert in PRICE_ALERTS:
        price = prices.get(alert.ticker)
        if price is None:
            continue
        if price <= alert.buy_below:
            if not args.dry_run and check_alerted_today(alert.ticker):
                continue  # Already alerted today
            alerts_triggered.append((alert, price))

    if not alerts_triggered:
        if not args.quiet:
            print("No price alerts triggered today.")
        return 0

    # Format and output alerts
    messages = []
    for alert, price in alerts_triggered:
        msg = format_alert(alert, price)
        messages.append(msg)
        if not args.dry_run:
            record_alert(alert.ticker, price, alert.buy_below)

    output = "\n\n".join(messages)
    if args.quiet:
        print(output)
    else:
        print(f"\n🚨 {len(alerts_triggered)} Price Alert(s) Triggered!")
        print("=" * 60)
        print(output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
