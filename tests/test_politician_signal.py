"""
Tests for politician trade signal weighting.

Covers the (politician, transaction_type) keyed weight dict introduced
after the Tuberville PTR backtest (notes/research/politician_backtest_2026.md):
Tuberville buys had −9% alpha @180d, sells had +14% alpha @365d. The dict
must let us fade buys and amplify sells independently of other politicians.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from invest.data.politician_db import (
    DEFAULT_POLITICIAN_WEIGHT,
    HIGH_SIGNAL_POLITICIANS,
    _politician_weight,
    compute_politician_signal,
)


# ---------------------------------------------------------------------------
# Direct weight-lookup unit tests
# ---------------------------------------------------------------------------


def test_tuberville_buy_is_faded():
    """Tuberville buys backtested to −9% alpha — weight must be < 1.0."""
    assert _politician_weight('Tuberville, Tommy', 'P') == 0.3


def test_tuberville_sell_is_amplified():
    """Tuberville sells backtested to +14% alpha — weight must be > 2.0."""
    assert _politician_weight('Tuberville, Tommy', 'S') == 3.5


def test_pelosi_buy_and_sell_both_uniform():
    """Pelosi has not been direction-split yet — both sides keep the old 3.0."""
    assert _politician_weight('Pelosi, Nancy', 'P') == 3.0
    assert _politician_weight('Pelosi, Nancy', 'S') == 3.0


def test_unknown_politician_buy_uses_default():
    assert _politician_weight('Nobody, Random', 'P') == DEFAULT_POLITICIAN_WEIGHT


def test_unknown_politician_sell_uses_default():
    assert _politician_weight('Nobody, Random', 'S') == DEFAULT_POLITICIAN_WEIGHT


def test_missing_tx_type_returns_default():
    """Defensive: empty/None transaction_type should not raise, just default."""
    assert _politician_weight('Tuberville, Tommy', None) == DEFAULT_POLITICIAN_WEIGHT
    assert _politician_weight('Tuberville, Tommy', '') == DEFAULT_POLITICIAN_WEIGHT


def test_lowercase_tx_type_is_normalized():
    """transaction_type input may not be canonical case — handle 'p'/'s'."""
    assert _politician_weight('Tuberville, Tommy', 'p') == 0.3
    assert _politician_weight('Tuberville, Tommy', 's') == 3.5


def test_partial_sale_code_resolves_to_sell():
    """Some PTR feeds use 'S (partial)' — the leading 'S' must still match."""
    assert _politician_weight('Tuberville, Tommy', 'S (partial)') == 3.5


def test_dict_is_keyed_on_tuples():
    """Regression guard against accidentally reverting to name-only keys."""
    for key in HIGH_SIGNAL_POLITICIANS:
        assert isinstance(key, tuple), f'expected tuple key, got {type(key)}: {key!r}'
        assert len(key) == 2
        name, code = key
        assert isinstance(name, str) and name
        assert code in {'P', 'S'}, f'unexpected tx_type code in dict: {code!r}'


# ---------------------------------------------------------------------------
# compute_politician_signal integration (DB stubbed, no live Postgres)
# ---------------------------------------------------------------------------


def _stub_conn(rows):
    """Build a fake psycopg2 connection that returns ``rows`` from any SELECT.

    The first SELECT inside compute_politician_signal is a 1-row probe
    (`SELECT 1 FROM politician_trades LIMIT 1`); we satisfy that by always
    returning a non-empty ``fetchone`` until the second cursor's ``fetchall``
    returns the actual ``rows``.
    """
    probe_cursor = MagicMock()
    probe_cursor.execute.return_value = None
    probe_cursor.fetchone.return_value = (1,)

    data_cursor = MagicMock()
    data_cursor.execute.return_value = None
    data_cursor.fetchall.return_value = rows

    conn = MagicMock()
    # First .cursor(...) call hits the probe, second hits the data query.
    conn.cursor.side_effect = [probe_cursor, data_cursor]
    return conn


def test_compute_signal_tuberville_buy_zeroed_by_gate_fail():
    """Tuberville BUYS are gate-FAIL; the catalyst score must drop to zero
    despite the 0.3 manual weight in HIGH_SIGNAL_POLITICIANS."""
    rows = [
        # name, tx_type, tx_date, amt_min, amt_max
        ('Tuberville, Tommy', 'P', '2026-04-01', 1_001, 15_000),  # size_factor 0.5
    ]
    conn = _stub_conn(rows)
    out = compute_politician_signal(conn, 'AAPL')
    assert out['has_data'] is True
    assert out['buy_count'] == 1
    assert out['sell_count'] == 0
    # gate-FAIL → weight collapses to 0 regardless of the manual weight
    assert out['weighted_score'] == pytest.approx(0.0)


def test_compute_signal_tuberville_sell_uses_amplified_weight():
    """A single Tuberville sale subtracts 3.5 * size_factor from the score
    (gate-PASS keeps the manual weight)."""
    rows = [
        ('Tuberville, Tommy', 'S', '2026-04-01', 1_001, 15_000),  # size_factor 0.5
    ]
    conn = _stub_conn(rows)
    out = compute_politician_signal(conn, 'AAPL')
    assert out['has_data'] is True
    assert out['buy_count'] == 0
    assert out['sell_count'] == 1
    # weighted_score is *subtracted* on sells: -3.5 * 0.5 = -1.75
    assert out['weighted_score'] == pytest.approx(-1.75)


def test_compute_signal_pelosi_buy_passes_sell_zeroed():
    """Pelosi BUYS are gate-PASS (keep weight 3.0), Pelosi SELLS are
    gate-FAIL (zero contribution). The manual weight is symmetric across
    directions; the gate breaks the symmetry."""
    buy_rows = [('Pelosi, Nancy', 'P', '2026-04-01', 1_001, 15_000)]
    sell_rows = [('Pelosi, Nancy', 'S', '2026-04-01', 1_001, 15_000)]
    buy_score = compute_politician_signal(_stub_conn(buy_rows), 'AAPL')['weighted_score']
    sell_score = compute_politician_signal(_stub_conn(sell_rows), 'AAPL')['weighted_score']
    # 3.0 manual weight × 0.5 size_factor on the buy side
    assert buy_score == pytest.approx(1.5)
    # FAIL → zero
    assert sell_score == pytest.approx(0.0)


def test_compute_signal_unbacktested_politician_uses_default_weight():
    """A politician with no entry in SIGNAL_GATES should still contribute at
    DEFAULT_POLITICIAN_WEIGHT — the gate filters known-bad signals, it
    doesn't punish unmeasured ones."""
    rows = [('Schumer, Chuck', 'P', '2026-04-01', 1_001, 15_000)]
    conn = _stub_conn(rows)
    out = compute_politician_signal(conn, 'AAPL')
    assert out['has_data'] is True
    # DEFAULT_POLITICIAN_WEIGHT = 1.0, size_factor = 0.5
    assert out['weighted_score'] == pytest.approx(0.5)
