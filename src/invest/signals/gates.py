"""
Signal gate registry — measured-alpha metadata per trade-signal source.

The /feed dashboard shows two card categories:
  - NARRATIVE cards (intro, thesis, bull/bear, numbers, verdict) — sourced
    from the user's own notes/companies/*.md analyses. NOT gated here.
  - TRADE-SIGNAL cards (Congress signal, Insider signal) — derived from
    external data, with implicit alpha claims. Gated by this module.

Default policy is DROP UNBACKTESTED. A signal source has to clear the
alpha bar (entry in SIGNAL_GATES with passes=True) before it surfaces.
Surviving signals carry an inline alpha + caveat annotation on the card.

The accompanying human-readable ledger lives at
notes/research/signal_inventory.md — keep it in sync with this dict so we
remember what's curated vs not.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class GateResult:
    """One row of measured-alpha metadata for a trade-signal source."""

    passes: bool
    alpha: float            # annualised, signed (e.g. 0.142 for +14.2%)
    horizon: str            # the horizon the alpha was measured at, e.g. "365d"
    p_value: float          # two-sided t-test p-value vs control
    n_nominal: int          # raw observation count
    n_effective: int        # post-clustering / independence-adjusted n
    caveat: str             # one-line caveat shown inline on the card
    last_backtested_at: str # ISO date the metadata was last refreshed


# Tuple key shape: (source, name, kind).
# - source: signal family ("politician", future: "insider", "activist", ...)
# - name:   politician full-name as stored in politician_trades.politician_name,
#           or a regime label for non-per-name signals.
# - kind:   transaction direction for politicians ('P'/'S'), or None.
SIGNAL_GATES: Dict[Tuple[str, str, Optional[str]], GateResult] = {
    # See notes/research/politician_backtest_2026.md for derivation.
    # Tuberville sells: +14.2% annualised alpha at 365d, hit rate 75.5%,
    # p<0.001 vs House control. Trade clustering reduces effective n
    # from 216 to ~20, so headline t-stat is optimistic.
    ('politician', 'Tuberville, Tommy', 'S'): GateResult(
        passes=True,
        alpha=0.142,
        horizon='365d',
        p_value=0.001,
        n_nominal=216,
        n_effective=20,
        caveat='trade clustering reduces effective n',
        last_backtested_at='2026-04-30',
    ),
    # Tuberville buys: -9.2% annualised alpha at 365d, but the
    # statistically robust window is 180d (n=118, p=0.003, alpha -13.3%).
    # Reported here at 180d horizon. Faded, not amplified.
    ('politician', 'Tuberville, Tommy', 'P'): GateResult(
        passes=False,
        alpha=-0.133,
        horizon='180d',
        p_value=0.003,
        n_nominal=118,
        n_effective=10,
        caveat='underperforms SPY post-disclosure',
        last_backtested_at='2026-04-30',
    ),
    # See notes/research/pelosi_backtest_2026.md for derivation.
    # Pelosi buys: +13.7% annualised alpha at 365d, hit rate 62.5%
    # (cluster level 75%), p=0.004 vs House control. n_nominal=16 is
    # small; cluster count 12. Survives leave-2-out robustness check
    # but heavily exposed to bull-market regime (megacap-tech
    # concentration). Provisional pass; revisit in 12mo.
    ('politician', 'Pelosi, Nancy', 'P'): GateResult(
        passes=True,
        alpha=0.137,
        horizon='365d',
        p_value=0.004,
        n_nominal=16,
        n_effective=12,
        caveat='small sample; bull-market regime; megacap-tech concentration',
        last_backtested_at='2026-05-10',
    ),
    # Pelosi sells: -18.9% annualised alpha at 365d, p=0.023, hit
    # rate 22% (cluster 12%). Significant underperformance — she
    # sells names that subsequently beat SPY. Faded, not amplified.
    ('politician', 'Pelosi, Nancy', 'S'): GateResult(
        passes=False,
        alpha=-0.189,
        horizon='365d',
        p_value=0.023,
        n_nominal=9,
        n_effective=8,
        caveat='underperforms SPY post-disclosure (significantly negative)',
        last_backtested_at='2026-05-10',
    ),
    # See notes/research/gottheimer_backtest_2026.md for derivation.
    # Gottheimer: no significant alpha vs House control at any horizon
    # × direction. n large (105 P / 166 S, 90 / 115 clusters) so this
    # is a confident reject, not "haven't measured." Set passes=False
    # to document the negative result. Best p across all combos is
    # 0.148 (sells 90d); 365d alphas track control closely.
    ('politician', 'Gottheimer, Josh', 'P'): GateResult(
        passes=False,
        alpha=-0.072,
        horizon='365d',
        p_value=0.826,
        n_nominal=59,
        n_effective=54,
        caveat='no significant alpha vs control across horizons',
        last_backtested_at='2026-05-10',
    ),
    ('politician', 'Gottheimer, Josh', 'S'): GateResult(
        passes=False,
        alpha=0.079,
        horizon='365d',
        p_value=0.385,
        n_nominal=83,
        n_effective=70,
        caveat='no significant alpha vs control across horizons',
        last_backtested_at='2026-05-10',
    ),
    # Crenshaw, Daniel: only n=6 trades in DB (House Clerk PTRs since
    # 2021 backfill). Same fate as Vance — sample too small for any
    # inference. Documented as fail rather than left UNGATED.
    ('politician', 'Crenshaw, Daniel', 'P'): GateResult(
        passes=False,
        alpha=0.0,
        horizon='365d',
        p_value=1.0,
        n_nominal=6,
        n_effective=6,
        caveat='n too small for inference (6 total trades)',
        last_backtested_at='2026-05-10',
    ),
    ('politician', 'Crenshaw, Daniel', 'S'): GateResult(
        passes=False,
        alpha=0.0,
        horizon='365d',
        p_value=1.0,
        n_nominal=6,
        n_effective=6,
        caveat='n too small for inference (6 total trades)',
        last_backtested_at='2026-05-10',
    ),
    # Other politicians and signal sources: no entry here -> evaluate()
    # returns None -> the gate filter drops the post.
}


def evaluate(
    source: str,
    name: str,
    kind: Optional[str] = None,
) -> Optional[GateResult]:
    """Look up gate metadata for a trade signal.

    Returns the GateResult if the (source, name, kind) tuple has a
    curated entry, else None. Callers should treat None as "drop" under
    the default strict-gate policy.
    """
    return SIGNAL_GATES.get((source, name, kind))


def confidence_tier(gate: GateResult) -> str:
    """Return a star rating ('★★★' / '★★' / '★' / '') for a gate.

    Combines p-value with effective n so a tiny-but-significant result
    doesn't get the same display weight as a robust one. Tiers:
      ★★★ Strong:   p < 0.01 AND n_effective >= 20
      ★★  Moderate: p < 0.05 AND n_effective >= 10
      ★   Weak:     anything else that still passes
    Empty string for non-passing gates (they aren't rendered anyway).
    """
    if not gate.passes:
        return ''
    if gate.p_value < 0.01 and gate.n_effective >= 20:
        return '★★★'
    if gate.p_value < 0.05 and gate.n_effective >= 10:
        return '★★'
    return '★'


def annualised_alpha(gate: GateResult) -> float:
    """Compound the registered horizon alpha to one year (decimal return).

    `gate.alpha` is the mean log-alpha at `gate.horizon` (e.g. '365d').
    Returns simple-return annualised, suitable for a "+13.7% / yr" pill.
    """
    horizon_days = int(gate.horizon.rstrip('d'))
    return math.expm1(gate.alpha * 365.0 / horizon_days)


def freshness(gate: GateResult, today: Optional[date] = None) -> Tuple[str, str]:
    """Return (label, severity) for the last_backtested_at date.

    severity ∈ {'fresh', 'aging', 'stale'} — the dashboard maps these
    to colours. Boundaries are 12 / 24 months; gates older than 24
    months should be flagged as needing re-validation.
    """
    today = today or date.today()
    backtest = date.fromisoformat(gate.last_backtested_at)
    age_days = (today - backtest).days
    label = f'as of {gate.last_backtested_at[:7]}'
    if age_days < 365:
        return label, 'fresh'
    if age_days < 730:
        return label, 'aging'
    return label, 'stale'


def apply_signal_gates(posts):
    """Filter trade-signal posts by the gate registry.

    Posts with type='signal' must carry signal_source / signal_name /
    signal_kind keys. The gate is looked up; passing posts get the
    GateResult attached as post['gate'] for inline rendering. Failing or
    ungated posts are dropped.

    Posts of any other type (intro, thesis, bull, bear, numbers, verdict)
    pass through untouched — the gate is for external alpha claims, not
    for the user's own narrative analyses.
    """
    out = []
    for post in posts:
        if post.get("type") != "signal":
            out.append(post)
            continue
        result = evaluate(
            post.get("signal_source", ""),
            post.get("signal_name", ""),
            post.get("signal_kind"),
        )
        if result is None or not result.passes:
            continue
        post = dict(post)
        post["gate"] = result
        out.append(post)
    return out
