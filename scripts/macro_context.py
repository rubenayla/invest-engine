#!/usr/bin/env python3
"""
Macro context snapshot — answers "is this a good time to deploy capital?"

Pulls live equity / volatility / rate / safe-haven prices from yfinance and
Fed-pricing probabilities from Polymarket into a single readable report. Use
when deciding whether to deploy cash now or wait for a pullback.

Usage:
    uv run python scripts/macro_context.py
    uv run python scripts/macro_context.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import yfinance as yf

# Reuse the existing Polymarket lookup (same scripts/ dir).
sys.path.insert(0, str(Path(__file__).parent))
from polymarket_lookup import search_markets  # noqa: E402


TICKERS = {
    "equities": {
        "^GSPC": "S&P 500",
        "^NDX": "NASDAQ 100",
        "^RUT": "Russell 2000 (small cap)",
    },
    "volatility": {
        "^VIX": "VIX (fear index)",
    },
    "rates": {
        "^TNX": "10Y Treasury yield",
        "^IRX": "13W T-Bill yield",
    },
    "safe_havens": {
        "GLD": "Gold (GLD)",
        "TLT": "Long bonds (TLT)",
    },
}


def vix_regime(vix: float) -> tuple[str, str]:
    """Return (label, description) for a VIX level."""
    if vix >= 40:
        return "PANIC", "historically best forward 12mo returns"
    if vix >= 30:
        return "FEAR", "fear premium present, strong deploy zone"
    if vix >= 25:
        return "CAUTION", "some worry priced in, tranche in"
    if vix >= 20:
        return "NORMAL", "standard volatility"
    if vix >= 15:
        return "CALM", "bull-market regime"
    if vix >= 12:
        return "LOW", "low fear, options cheap"
    return "COMPLACENCY", "historically precedes selloffs"


def fetch_prices() -> dict:
    """Pull 1y of price data for each ticker and compute summary stats."""
    out: dict = {}
    for category, tickers in TICKERS.items():
        out[category] = {}
        for sym, name in tickers.items():
            try:
                hist = yf.Ticker(sym).history(period="1y")
                if hist.empty:
                    out[category][sym] = {"name": name, "error": "no data"}
                    continue
                cur = float(hist["Close"].iloc[-1])
                high = float(hist["Close"].max())
                low = float(hist["Close"].min())
                start = float(hist["Close"].iloc[0])
                out[category][sym] = {
                    "name": name,
                    "current": round(cur, 2),
                    "high_1y": round(high, 2),
                    "low_1y": round(low, 2),
                    "pct_off_high": round((cur / high - 1) * 100, 1),
                    "pct_1y_return": round((cur / start - 1) * 100, 1),
                }
            except Exception as e:
                out[category][sym] = {"name": name, "error": str(e)}
    return out


def fetch_fed_pricing() -> dict:
    """Pull liquid Fed-rate markets from Polymarket."""
    try:
        markets = search_markets("fed", limit=30, min_liquidity=50_000)
        relevant = [
            m for m in markets
            if any(k in m["question"].lower() for k in
                   ["rate cut", "interest rate", "fed decrease", "fed increase",
                    "no change", "rate cuts happen"])
        ]
        return {"markets": relevant[:6]}
    except Exception as e:
        return {"error": str(e), "markets": []}


def composite_signal(prices: dict, vix: float) -> dict:
    """
    Score the buy environment. Negative = wait, positive = deploy.
    Each axis contributes independently; reasons explain the score.
    """
    score = 0
    reasons: list[str] = []

    # VIX axis
    vix_label, _ = vix_regime(vix)
    if vix >= 30:
        score += 3
        reasons.append(f"VIX {vix:.1f} ({vix_label}) → strong deploy")
    elif vix >= 25:
        score += 2
        reasons.append(f"VIX {vix:.1f} ({vix_label}) → tranche in")
    elif vix >= 20:
        reasons.append(f"VIX {vix:.1f} ({vix_label}) → neutral")
    elif vix < 15:
        score -= 1
        reasons.append(f"VIX {vix:.1f} ({vix_label}) → no urgency, FOMO risk")

    # S&P drawdown axis
    spx = prices.get("equities", {}).get("^GSPC", {})
    spx_dd = spx.get("pct_off_high")
    if spx_dd is not None:
        if spx_dd <= -15:
            score += 3
            reasons.append(f"S&P {spx_dd}% off 1y high → bear-market entry")
        elif spx_dd <= -10:
            score += 2
            reasons.append(f"S&P {spx_dd}% off 1y high → correction territory")
        elif spx_dd <= -5:
            score += 1
            reasons.append(f"S&P {spx_dd}% off 1y high → minor pullback")
        elif spx_dd >= -3:
            score -= 1
            reasons.append(f"S&P {spx_dd}% off 1y high → near peak, limited entry")

    # S&P YoY momentum — extreme runs revert (long-term avg ≈ 10%)
    spx_1y = spx.get("pct_1y_return")
    if spx_1y is not None:
        if spx_1y >= 30:
            score -= 2
            reasons.append(f"S&P +{spx_1y}% YoY (3× historical avg) → strong mean-reversion risk")
        elif spx_1y >= 20:
            score -= 1
            reasons.append(f"S&P +{spx_1y}% YoY (2× historical avg) → elevated, FOMO zone")
        elif spx_1y <= -10:
            score += 1
            reasons.append(f"S&P {spx_1y}% YoY → already painful, future returns skew higher")

    # Small-cap divergence (canary)
    rut_dd = prices.get("equities", {}).get("^RUT", {}).get("pct_off_high")
    if rut_dd is not None and spx_dd is not None:
        if rut_dd <= -15 and spx_dd > -10:
            score += 1
            reasons.append(
                f"Russell 2000 {rut_dd}% off high while S&P holds → divergence"
            )

    # Gold rip = hedging beneath surface
    gold_1y = prices.get("safe_havens", {}).get("GLD", {}).get("pct_1y_return")
    if gold_1y is not None and gold_1y >= 30:
        reasons.append(
            f"Gold +{gold_1y}% YoY → hedging behavior beneath calm surface"
        )

    if score >= 4:
        verdict = "DEPLOY AGGRESSIVELY"
    elif score >= 2:
        verdict = "DEPLOY / TRANCHE IN"
    elif score >= 0:
        verdict = "NEUTRAL — average in normally"
    elif score >= -2:
        verdict = "CAUTIOUS — keep dry powder"
    else:
        verdict = "WAIT — elevated FOMO risk"

    return {"score": score, "verdict": verdict, "reasons": reasons}


def _fmt_num(v: float, width: int = 10) -> str:
    return f"{v:>{width},.2f}"


def print_report(prices: dict, fed: dict, composite: dict, vix: float) -> None:
    print()
    print("=" * 76)
    print(f"  MACRO CONTEXT  —  {datetime.now():%Y-%m-%d %H:%M}")
    print("=" * 76)

    print("\n  EQUITIES")
    for d in prices.get("equities", {}).values():
        if "error" in d:
            print(f"    {d['name']:30s}  ERROR: {d['error']}")
            continue
        print(f"    {d['name']:30s} {_fmt_num(d['current'])}   "
              f"off high: {d['pct_off_high']:>+6.1f}%   "
              f"1y: {d['pct_1y_return']:>+6.1f}%")

    print("\n  VOLATILITY")
    if vix:
        label, desc = vix_regime(vix)
        print(f"    VIX = {vix:.2f}   →   {label}: {desc}")

    print("\n  RATES")
    for d in prices.get("rates", {}).values():
        if "error" in d:
            continue
        print(f"    {d['name']:30s}  {d['current']:>6.2f}%   "
              f"1y change: {d['pct_1y_return']:>+6.1f}%")

    print("\n  SAFE HAVENS")
    for d in prices.get("safe_havens", {}).values():
        if "error" in d:
            continue
        print(f"    {d['name']:30s} {_fmt_num(d['current'])}   "
              f"off high: {d['pct_off_high']:>+6.1f}%   "
              f"1y: {d['pct_1y_return']:>+6.1f}%")

    print("\n  FED PRICING (Polymarket, liquidity ≥ $50K)")
    if fed.get("error"):
        print(f"    error: {fed['error']}")
    elif not fed.get("markets"):
        print("    no liquid Fed markets found")
    else:
        for m in fed["markets"]:
            probs = " | ".join(f"{k}: {v}%" for k, v in m["probabilities"].items())
            print(f"    {m['question'][:62]}")
            print(f"      {probs}")

    print("\n" + "=" * 76)
    print(f"  VERDICT: {composite['verdict']}   (score: {composite['score']:+d})")
    print("=" * 76)
    for r in composite["reasons"]:
        print(f"    • {r}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    prices = fetch_prices()
    vix = prices.get("volatility", {}).get("^VIX", {}).get("current", 0.0)
    fed = fetch_fed_pricing()
    composite = composite_signal(prices, vix)

    if args.json:
        json.dump(
            {"prices": prices, "vix": vix, "fed": fed, "composite": composite},
            sys.stdout,
            indent=2,
            default=str,
        )
        print()
    else:
        print_report(prices, fed, composite, vix)


if __name__ == "__main__":
    main()
