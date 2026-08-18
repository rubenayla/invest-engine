"""Tests for reconstructing insider signal history without look-ahead bias."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from backfill_insider_snapshots import build_daily_snapshots


def test_snapshots_are_as_of_each_transaction_date():
    rows = [
        ("ACME", "P", 10.0, 100.0, "2026-01-01", "Alice", 1),
        ("ACME", "S", 5.0, 110.0, "2026-01-02", "Bob", 1),
        ("ACME", "P", 20.0, 120.0, "2026-01-03", "Carol", 1),
    ]

    snapshots = build_daily_snapshots(rows)

    assert [row["date"] for row in snapshots] == [
        "2026-01-01", "2026-01-02", "2026-01-03"
    ]
    assert snapshots[0]["buy_count"] == 1
    assert snapshots[0]["sell_count"] == 0
    assert snapshots[1]["buy_count"] == 1
    assert snapshots[1]["sell_count"] == 1
    assert snapshots[2]["buy_count"] == 2
    assert snapshots[2]["sell_count"] == 1


def test_backfill_ignores_non_open_market_form_four_rows():
    rows = [
        ("ACME", "M", 10.0, 100.0, "2026-01-01", "Alice", 0),
        ("ACME", "P", 10.0, 100.0, "2026-01-02", "Alice", 1),
    ]

    snapshots = build_daily_snapshots(rows)

    assert len(snapshots) == 1
    assert snapshots[0]["date"] == "2026-01-02"
