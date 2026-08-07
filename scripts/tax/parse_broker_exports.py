"""
Parse Revolut + IBKR broker exports into per-year Spanish tax summaries.

Input:  ~/vault/paperwork/taxes/YYYY/raw/*.{csv,pdf}
Output: ~/vault/paperwork/taxes/YYYY/processed/{trades,gains,dividends}.csv
        ~/vault/paperwork/taxes/YYYY/processed/summary.json

Computes FIFO cost basis in EUR using ECB reference rates on each transaction date.
Flags whether net realized gains exceed the €1,000 IRPF filing threshold.

Usage:
    uv run python scripts/tax/parse_broker_exports.py 2025
    uv run python scripts/tax/parse_broker_exports.py --all

Status: SKELETON. Parsers for Revolut/IBKR formats are stubbed until we see real exports.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from dataclasses import dataclass, asdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

PAPERWORK_TAXES = Path.home() / "repos" / "vault" / "paperwork" / "taxes"
FILING_THRESHOLD_EUR = Decimal("1000")


@dataclass
class Trade:
    date: date
    broker: str
    ticker: str
    action: str  # "BUY" or "SELL"
    quantity: Decimal
    price_native: Decimal
    currency: str
    fees_native: Decimal
    fx_rate_eur: Decimal  # ECB reference on trade date, native_per_eur
    price_eur: Decimal
    fees_eur: Decimal
    total_eur: Decimal  # quantity * price_eur (+ fees for buys, - fees for sells)


@dataclass
class RealizedGain:
    sell_date: date
    buy_date: date
    ticker: str
    broker: str
    quantity: Decimal
    proceeds_eur: Decimal
    cost_basis_eur: Decimal
    gain_eur: Decimal
    holding_days: int


@dataclass
class Dividend:
    date: date
    broker: str
    ticker: str
    gross_native: Decimal
    withheld_native: Decimal
    currency: str
    fx_rate_eur: Decimal
    gross_eur: Decimal
    withheld_eur: Decimal


def load_ecb_rates() -> dict[date, dict[str, Decimal]]:
    """Load ECB reference rates. TODO: fetch once, cache locally, fill weekends with prior trading day."""
    # Placeholder — will implement with frankfurter.app or ECB SDMX API
    return {}


def parse_revolut(raw_dir: Path) -> list[Trade]:
    """Parse Revolut trading CSV/PDF into Trade records.
    TODO: implement once we see real export format.
    Expected columns in Revolut trading CSV: Date, Ticker, Type, Quantity, Price per share, Total Amount, Currency, FX Rate, Fees.
    """
    trades: list[Trade] = []
    for f in raw_dir.glob("revolut*.csv"):
        print(f"  [stub] would parse {f.name}")
    for f in raw_dir.glob("revolut*.pdf"):
        print(f"  [stub] would extract from {f.name} (PDF parser needed)")
    return trades


def parse_ibkr(raw_dir: Path) -> list[Trade]:
    """Parse IBKR Activity Statement CSV into Trade records.
    TODO: implement once we see real export format.
    IBKR CSV has multi-section format: Trades, Dividends, Withholding Tax, Fees sections per asset class.
    """
    trades: list[Trade] = []
    for f in raw_dir.glob("ibkr*.csv"):
        print(f"  [stub] would parse {f.name}")
    return trades


def compute_fifo_gains(trades: list[Trade]) -> list[RealizedGain]:
    """Apply FIFO cost basis matching per (broker, ticker) lot.
    Spanish tax requires FIFO — cannot choose which lots to sell."""
    lots: dict[tuple[str, str], deque[tuple[Trade, Decimal]]] = {}
    gains: list[RealizedGain] = []

    for t in sorted(trades, key=lambda x: x.date):
        key = (t.broker, t.ticker)
        if t.action == "BUY":
            lots.setdefault(key, deque()).append((t, t.quantity))
        elif t.action == "SELL":
            remaining = t.quantity
            while remaining > 0 and lots.get(key):
                buy_trade, lot_qty = lots[key][0]
                matched = min(remaining, lot_qty)
                cost_basis = matched * buy_trade.price_eur + (
                    buy_trade.fees_eur * matched / buy_trade.quantity
                )
                proceeds = matched * t.price_eur - (
                    t.fees_eur * matched / t.quantity
                )
                gains.append(
                    RealizedGain(
                        sell_date=t.date,
                        buy_date=buy_trade.date,
                        ticker=t.ticker,
                        broker=t.broker,
                        quantity=matched,
                        proceeds_eur=proceeds,
                        cost_basis_eur=cost_basis,
                        gain_eur=proceeds - cost_basis,
                        holding_days=(t.date - buy_trade.date).days,
                    )
                )
                remaining -= matched
                if matched == lot_qty:
                    lots[key].popleft()
                else:
                    lots[key][0] = (buy_trade, lot_qty - matched)
            if remaining > 0:
                print(f"  WARN: sell on {t.date} for {t.ticker} {t.broker} has no matching buy lots ({remaining} unmatched)")
    return gains


def summarize_year(year: int, gains: list[RealizedGain], dividends: list[Dividend]) -> dict:
    year_gains = [g for g in gains if g.sell_date.year == year]
    year_divs = [d for d in dividends if d.date.year == year]
    total_gain = sum((g.gain_eur for g in year_gains), Decimal(0))
    total_div_gross = sum((d.gross_eur for d in year_divs), Decimal(0))
    total_div_withheld = sum((d.withheld_eur for d in year_divs), Decimal(0))
    return {
        "year": year,
        "realized_gain_eur": float(total_gain),
        "dividends_gross_eur": float(total_div_gross),
        "dividends_withheld_eur": float(total_div_withheld),
        "num_sells": len(year_gains),
        "crosses_1000_threshold": total_gain > FILING_THRESHOLD_EUR,
        "filing_required": total_gain > FILING_THRESHOLD_EUR or total_div_gross > Decimal("1600"),
    }


def process_year(year: int) -> None:
    year_dir = PAPERWORK_TAXES / str(year)
    raw = year_dir / "raw"
    processed = year_dir / "processed"
    processed.mkdir(exist_ok=True)

    if not raw.exists() or not any(raw.iterdir()):
        print(f"{year}: no raw files, skipping")
        return

    print(f"Processing {year}...")
    trades = parse_revolut(raw) + parse_ibkr(raw)
    if not trades:
        print(f"{year}: no trades parsed (parsers are stubs — add real broker exports and implement parsers)")
        return

    gains = compute_fifo_gains(trades)
    dividends: list[Dividend] = []  # TODO: extract from broker statements
    summary = summarize_year(year, gains, dividends)

    (processed / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(f"  → {processed}/summary.json")
    print(f"  realized_gain: €{summary['realized_gain_eur']:.2f}")
    print(f"  filing_required: {summary['filing_required']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("year", nargs="?", type=int, help="Fiscal year to process")
    parser.add_argument("--all", action="store_true", help="Process all years with raw files")
    args = parser.parse_args()

    if args.all:
        years = sorted(int(p.name) for p in PAPERWORK_TAXES.iterdir() if p.is_dir() and p.name.isdigit())
        for y in years:
            process_year(y)
    elif args.year:
        process_year(args.year)
    else:
        parser.print_help()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
