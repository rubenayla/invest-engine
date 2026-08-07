"""
Tests for the trade-signal gate registry and boundary filter.

The /feed dashboard drops trade-signal cards (Congress, Insider, etc.)
that don't have a curated entry in src/invest/signals/gates.py. These
tests pin the contract: known passes survive, known failures and
unbacktested signals are dropped, narrative posts pass through.
"""

from __future__ import annotations

import pytest

import dataclasses
from datetime import date

from invest.signals.gates import (
    GateResult,
    SIGNAL_GATES,
    annualised_alpha,
    apply_signal_gates,
    confidence_tier,
    evaluate,
    freshness,
)


# ---------------------------------------------------------------------------
# Direct evaluate() unit tests
# ---------------------------------------------------------------------------


def test_tuberville_sells_pass_the_gate():
    """Sells beat SPY +14% annualised at 365d in the 2026-04-30 backtest."""
    result = evaluate('politician', 'Tuberville, Tommy', 'S')
    assert result is not None
    assert result.passes is True
    assert result.alpha > 0.10
    assert result.horizon == '365d'
    assert result.p_value < 0.01
    assert result.n_effective < result.n_nominal  # clustering reduces n


def test_tuberville_buys_explicitly_fail_the_gate():
    """Buys underperform SPY by 13% at 180d — recorded as passes=False."""
    result = evaluate('politician', 'Tuberville, Tommy', 'P')
    assert result is not None
    assert result.passes is False
    assert result.alpha < 0


def test_unbacktested_politician_returns_none():
    """Drop-by-default for politicians not yet individually backtested."""
    assert evaluate('politician', 'Random, Nobody', 'P') is None
    assert evaluate('politician', 'Smith, John', 'S') is None
    assert evaluate('politician', 'Schumer, Chuck', 'P') is None


def test_unbacktested_signal_source_returns_none():
    """Insider, activist, 13F have no entries today — all drop."""
    assert evaluate('insider', 'cluster_buy') is None
    assert evaluate('activist', '13D') is None
    assert evaluate('smart_money', '13F') is None


def test_missing_kind_returns_none_when_kind_was_curated():
    """Forgetting to pass the direction shouldn't accidentally pass."""
    assert evaluate('politician', 'Tuberville, Tommy') is None
    assert evaluate('politician', 'Tuberville, Tommy', None) is None


def test_gates_dict_uses_tuple_keys():
    """Regression guard against accidentally reverting to string keys."""
    for key in SIGNAL_GATES:
        assert isinstance(key, tuple), f'expected tuple key, got {type(key)}: {key!r}'
        assert len(key) == 3, f'expected (source, name, kind), got {key!r}'


# ---------------------------------------------------------------------------
# apply_signal_gates() boundary-filter tests
# ---------------------------------------------------------------------------


def _politician_post(name: str, direction: str, ticker: str = 'XYZ') -> dict:
    return {
        'priority': 200, 'type': 'signal', 'tag': 'Congress signal',
        'ticker': ticker, 'name': 'Test Co', 'hero': None, 'body': 'b', 'pills': [],
        'signal_source': 'politician',
        'signal_name': name,
        'signal_kind': direction,
    }


def _insider_post(ticker: str = 'XYZ') -> dict:
    return {
        'priority': 200, 'type': 'signal', 'tag': 'Insider signal',
        'ticker': ticker, 'name': 'Test Co', 'hero': None, 'body': 'b', 'pills': [],
        'signal_source': 'insider',
        'signal_name': 'cluster_buy',
        'signal_kind': None,
    }


def _narrative_post(ptype: str = 'thesis') -> dict:
    return {
        'priority': 100, 'type': ptype, 'tag': ptype.title(),
        'ticker': 'XYZ', 'name': 'Test Co', 'hero': None, 'body': 'b', 'pills': [],
    }


def test_apply_keeps_passing_politician_signal():
    posts = [_politician_post('Tuberville, Tommy', 'S')]
    out = apply_signal_gates(posts)
    assert len(out) == 1
    assert out[0]['gate'] is not None
    assert out[0]['gate'].passes is True


def test_apply_drops_failing_politician_signal():
    posts = [_politician_post('Tuberville, Tommy', 'P')]
    out = apply_signal_gates(posts)
    assert out == []


def test_apply_drops_unbacktested_politician():
    posts = [_politician_post('Schumer, Chuck', 'S')]
    out = apply_signal_gates(posts)
    assert out == []


def test_apply_drops_unbacktested_insider_signal():
    """Strict gate today: no insider entries means all insider posts drop."""
    posts = [_insider_post()]
    out = apply_signal_gates(posts)
    assert out == []


def test_apply_passes_narrative_posts_through_unchanged():
    """Gate is for trade signals only — narrative cards bypass."""
    posts = [_narrative_post('thesis'), _narrative_post('verdict'), _narrative_post('bear')]
    out = apply_signal_gates(posts)
    assert len(out) == 3
    for p in out:
        assert 'gate' not in p


def test_apply_mixed_input_preserves_order_and_filters_correctly():
    posts = [
        _narrative_post('intro'),
        _politician_post('Tuberville, Tommy', 'P'),  # drop
        _politician_post('Tuberville, Tommy', 'S'),  # keep
        _insider_post(),                              # drop
        _narrative_post('verdict'),
    ]
    out = apply_signal_gates(posts)
    assert [p['type'] for p in out] == ['intro', 'signal', 'verdict']
    assert out[1]['signal_name'] == 'Tuberville, Tommy'
    assert out[1]['gate'].passes is True


def test_apply_does_not_mutate_input_posts():
    """Caller-side defensive: incoming posts shouldn't get a 'gate' key."""
    inp = _politician_post('Tuberville, Tommy', 'S')
    apply_signal_gates([inp])
    assert 'gate' not in inp


# ---------------------------------------------------------------------------
# Display helpers — confidence_tier, annualised_alpha, freshness
# ---------------------------------------------------------------------------


def test_confidence_tier_strong_for_low_p_high_n():
    """Tuberville sells: p=0.001, n_eff=20 → strong (★★★)."""
    g = evaluate('politician', 'Tuberville, Tommy', 'S')
    assert confidence_tier(g) == '★★★'


def test_confidence_tier_moderate_for_pelosi_buys():
    """Pelosi buys: p=0.004 (passes <0.01) but n_eff=12 (<20) → ★★."""
    g = evaluate('politician', 'Pelosi, Nancy', 'P')
    assert confidence_tier(g) == '★★'


def test_confidence_tier_empty_for_failing_gate():
    """passes=False entries should never get a star (they don't render)."""
    g = evaluate('politician', 'Tuberville, Tommy', 'P')
    assert confidence_tier(g) == ''


def test_annualised_alpha_compounds_correctly():
    """log α 0.137 at 365d → simple-return ~14.7% / yr."""
    g = evaluate('politician', 'Pelosi, Nancy', 'P')
    ann = annualised_alpha(g)
    assert 0.146 < ann < 0.148


def test_freshness_buckets():
    g = evaluate('politician', 'Tuberville, Tommy', 'S')
    today = date(2026, 5, 10)
    # baseline: backtested 2026-04-30, ~10d ago
    _, sev = freshness(g, today)
    assert sev == 'fresh'
    # aging: 18 months old
    aging = dataclasses.replace(g, last_backtested_at='2024-11-10')
    _, sev = freshness(aging, today)
    assert sev == 'aging'
    # stale: >24 months
    stale = dataclasses.replace(g, last_backtested_at='2023-01-01')
    _, sev = freshness(stale, today)
    assert sev == 'stale'
