#!/usr/bin/env python3
"""
Save (or refresh) a company note's verdict as the `llm_deep_analysis` row in
`valuation_results`, so the dashboard's LLM column shows it and ranks by it.

The dashboard reads verdicts from the database, not from the markdown notes.
Every time a note under `~/vault/finance/notes/companies/` gets a verdict
(first analysis, refresh, chollo scan re-check), run this with the note's numbers.

Usage:
    uv run python scripts/save_llm_verdict.py NRG --price 119.75 --verdict BUY \
        --conviction HIGH --ev 30 --quality 16 --entry 120 --thesis-break 95 \
        --bull 0.25:190:59 --base 0.5:155:29 --bear 0.25:117:-3 \
        --variant "Market sells the Q2 EPS miss; BYOP turns NRG into contracted AI infrastructure"

    --bull/--base/--bear take PROB:TARGET:RETURN_PCT (prob 0-1; use 0 if the note
    gives no probability). Add --dry-run to print the row without touching the DB.

The DB lives on y540 (see `.agents/deployment.md`); on the Mac the script needs the
SSH tunnel on localhost:5433 (`scripts/update_all.py` opens it, or
`ssh -fN -L 5433:localhost:5432 y540-ubuntu`).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

CONVICTIONS = ["HIGH", "MEDIUM-HIGH", "MEDIUM", "LOW"]
CONFIDENCE = {"HIGH": 0.9, "MEDIUM-HIGH": 0.8, "MEDIUM": 0.7, "LOW": 0.5}


def parse_scenario(text: str) -> dict:
    parts = text.split(":")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError(f"scenario must be PROB:TARGET:RETURN_PCT, got {text!r}")
    prob, target, ret = (float(p) for p in parts)
    if prob > 1:  # tolerate "25" for 25%
        prob = prob / 100
    return {"prob": prob, "target": target, "return_pct": ret}


def build_row(a: argparse.Namespace) -> tuple:
    fair_value = a.price * (1 + a.ev / 100)
    details = {
        "verdict": a.verdict,
        "conviction": a.conviction,
        "quality_score": a.quality,
        "expected_value_pct": a.ev,
        "entry_price": a.entry,
        "thesis_break_price": a.thesis_break,
        "variant_perception": a.variant or "",
        "scenarios": {"bull": a.bull, "base": a.base, "bear": a.bear},
    }
    return (
        a.ticker,
        datetime.now().isoformat(),
        fair_value,
        a.price,
        a.ev,
        a.verdict == "BUY",
        CONFIDENCE[a.conviction],
        json.dumps(details),
    )


SQL = """INSERT INTO valuation_results
    (ticker, model_name, timestamp, fair_value, current_price, upside_pct, suitable, confidence, details_json)
    VALUES (%s, 'llm_deep_analysis', %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (ticker, model_name) DO UPDATE SET
    timestamp=EXCLUDED.timestamp, fair_value=EXCLUDED.fair_value, current_price=EXCLUDED.current_price,
    upside_pct=EXCLUDED.upside_pct, suitable=EXCLUDED.suitable, confidence=EXCLUDED.confidence,
    details_json=EXCLUDED.details_json"""


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("ticker", help="ticker exactly as the note filename, e.g. NRG, 8001.T, KER.PA")
    p.add_argument("--price", type=float, required=True, help="price the analysis used")
    p.add_argument("--verdict", choices=["BUY", "WATCH", "PASS"], required=True)
    p.add_argument("--conviction", choices=CONVICTIONS, required=True)
    p.add_argument("--ev", type=float, required=True, help="expected value in %% (30 for +30%%)")
    p.add_argument("--quality", type=float, required=True, help="quality score, out of 25")
    p.add_argument("--entry", type=float, required=True, help="recommended entry price")
    p.add_argument("--thesis-break", type=float, default=None, help="price where the thesis is wrong")
    p.add_argument("--bull", type=parse_scenario, required=True, help="PROB:TARGET:RETURN_PCT")
    p.add_argument("--base", type=parse_scenario, required=True, help="PROB:TARGET:RETURN_PCT")
    p.add_argument("--bear", type=parse_scenario, required=True, help="PROB:TARGET:RETURN_PCT")
    p.add_argument("--variant", default="", help="one-line variant perception")
    p.add_argument("--dry-run", action="store_true", help="print the row, do not write")
    a = p.parse_args(argv)

    row = build_row(a)
    if a.dry_run:
        print(json.dumps({"ticker": row[0], "fair_value": row[2], "current_price": row[3],
                          "upside_pct": row[4], "suitable": row[5], "confidence": row[6],
                          "details": json.loads(row[7])}, indent=2))
        return 0

    from invest.data.db import get_connection

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(SQL, row)
        conn.commit()
    finally:
        conn.close()
    print(f"Saved {a.ticker} llm_deep_analysis: verdict={a.verdict}, EV={a.ev:+.0f}%, "
          f"conviction={a.conviction}, entry={a.entry}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
