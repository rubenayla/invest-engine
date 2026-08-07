#!/usr/bin/env python3
"""Backtest one politician's PTRs vs House control, Tuberville-style.

Mirrors the methodology in notes/research/politician_backtest_2026.md
(forward log returns over {30,90,180,365}d horizons, alpha vs SPY,
direction-split P/S, Welch t-test vs House control). Adds a
cluster-aggregated descriptive pass for low-n politicians whose
trades come in same-day batches (e.g. Pelosi).

Usage:
    DB_URL=postgresql://invest:YOUR_DB_PASSWORD@localhost:5433/invest \
    uv run python scripts/backtest_politician.py \
        --name "Pelosi, Nancy" \
        --out notes/research/pelosi_backtest_2026.md
"""

from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / 'src'))

from invest.data.db import get_connection

HORIZONS = [30, 90, 180, 365]
CONTROL_START = '2023-01-01'
GAP_DAYS = 7  # max forward search for a trading day


@dataclass
class Trade:
    ticker: str
    politician: str
    tx_date: date
    direction: str  # 'P' or 'S'


def load_trades(conn, name: Optional[str], control: bool) -> List[Trade]:
    """If name is set, load that politician's trades. If control=True,
    load all *other* House trades since CONTROL_START.
    """
    cur = conn.cursor()
    if control:
        cur.execute(
            """
            SELECT ticker, politician_name, transaction_date, transaction_type
            FROM politician_trades
            WHERE transaction_type IN ('P','S')
              AND transaction_date >= %s
              AND politician_name <> %s
            """,
            (CONTROL_START, name),
        )
    else:
        cur.execute(
            """
            SELECT ticker, politician_name, transaction_date, transaction_type
            FROM politician_trades
            WHERE transaction_type IN ('P','S')
              AND politician_name = %s
            """,
            (name,),
        )
    out = []
    for ticker, pol, tx, tt in cur.fetchall():
        try:
            d = date.fromisoformat(tx)
        except (TypeError, ValueError):
            continue
        if not ticker or len(ticker) > 10:
            continue
        out.append(Trade(ticker.upper(), pol, d, tt))
    return out


def load_prices(conn, tickers: List[str]) -> Dict[str, Dict[date, float]]:
    """Returns {ticker: {date: close}}."""
    if not tickers:
        return {}
    cur = conn.cursor()
    cur.execute(
        "SELECT ticker, date, close FROM price_history WHERE ticker = ANY(%s)",
        (list(set(tickers)),),
    )
    out: Dict[str, Dict[date, float]] = defaultdict(dict)
    for t, d, c in cur.fetchall():
        if c is not None and c > 0:
            out[t][d] = float(c)
    return out


def next_trading_close(
    prices: Dict[date, float],
    target: date,
    gap_days: int = GAP_DAYS,
) -> Optional[Tuple[date, float]]:
    """First available close on or after `target` (within gap_days)."""
    for i in range(gap_days + 1):
        d = target + timedelta(days=i)
        if d in prices:
            return d, prices[d]
    return None


def alpha_for_trade(
    trade: Trade,
    stock_prices: Dict[date, float],
    spy_prices: Dict[date, float],
    horizon: int,
    spy_max_date: date,
) -> Optional[float]:
    """Return signed alpha (log-space) for a trade-horizon, or None."""
    if trade.tx_date + timedelta(days=horizon) > spy_max_date:
        return None
    p0 = next_trading_close(stock_prices, trade.tx_date)
    p1 = next_trading_close(stock_prices, trade.tx_date + timedelta(days=horizon))
    s0 = next_trading_close(spy_prices, trade.tx_date)
    s1 = next_trading_close(spy_prices, trade.tx_date + timedelta(days=horizon))
    if not (p0 and p1 and s0 and s1):
        return None
    stock_ret = math.log(p1[1] / p0[1])
    spy_ret = math.log(s1[1] / s0[1])
    if trade.direction == 'P':
        return stock_ret - spy_ret
    else:
        return spy_ret - stock_ret


def annualise(alpha: float, horizon: int) -> float:
    """Compound a horizon-period log alpha to 365d, return decimal."""
    return math.expm1(alpha * 365.0 / horizon)


def welch_t(a: List[float], b: List[float]) -> Tuple[float, float, int]:
    """Welch's two-sample t-test, normal approx for df>30. (t, p, df)."""
    if len(a) < 2 or len(b) < 2:
        return 0.0, 1.0, 0
    ma, mb = mean(a), mean(b)
    va = pstdev(a) ** 2 * len(a) / (len(a) - 1)
    vb = pstdev(b) ** 2 * len(b) / (len(b) - 1)
    se = math.sqrt(va / len(a) + vb / len(b))
    if se == 0:
        return 0.0, 1.0, 0
    t = (ma - mb) / se
    num = (va / len(a) + vb / len(b)) ** 2
    den = (va / len(a)) ** 2 / (len(a) - 1) + (vb / len(b)) ** 2 / (len(b) - 1)
    df = num / den if den > 0 else 0
    # two-sided p via normal approx (df > 30 typically)
    z = abs(t)
    p = math.erfc(z / math.sqrt(2))
    return t, p, int(df)


def hit_rate(alphas: List[float]) -> float:
    if not alphas:
        return 0.0
    return sum(1 for a in alphas if a > 0) / len(alphas)


def cluster_count(trades: List[Trade]) -> int:
    """Distinct (date, direction) pairs."""
    return len({(t.tx_date, t.direction) for t in trades})


def compute_alphas(
    trades: List[Trade],
    prices: Dict[str, Dict[date, float]],
    spy: Dict[date, float],
    spy_max: date,
) -> Dict[int, List[Tuple[Trade, float]]]:
    """Return {horizon: [(trade, alpha), ...]}."""
    out = {h: [] for h in HORIZONS}
    for t in trades:
        sp = prices.get(t.ticker)
        if not sp:
            continue
        for h in HORIZONS:
            a = alpha_for_trade(t, sp, spy, h, spy_max)
            if a is not None:
                out[h].append((t, a))
    return out


def fmt_pct(x: float) -> str:
    return f'{x * 100:+.1f}%'


def fmt_p(p: float) -> str:
    if p < 0.001:
        return '<0.001'
    return f'{p:.3f}'


def render_report(
    name: str,
    pel_p: List[Trade],
    pel_s: List[Trade],
    ctrl_p: List[Trade],
    ctrl_s: List[Trade],
    pel_a: Dict[int, List[Tuple[Trade, float]]],
    ctrl_a: Dict[int, List[Tuple[Trade, float]]],
    spy_max: date,
) -> str:
    today = date.today().isoformat()
    lines: List[str] = []
    lines.append(f'# Politician PTR Backtest: {name}')
    lines.append('')
    lines.append(f'**Date:** {today}')
    lines.append(
        '**Methodology source:** mirrors '
        '`notes/research/politician_backtest_2026.md`. See that doc for '
        'forward-return convention, alpha sign, and Welch t-test details.'
    )
    lines.append('')

    # Sample sizes
    lines.append('## Sample sizes')
    lines.append('')
    lines.append(f'**{name} raw trades:** {len(pel_p)} P, {len(pel_s)} S')
    lines.append(
        f'**Cluster count (distinct (date, direction)):** '
        f'{cluster_count(pel_p)} P-clusters, {cluster_count(pel_s)} S-clusters'
    )
    lines.append('')
    lines.append(
        f'**Control (House, excl {name}, since {CONTROL_START}):** '
        f'{len(ctrl_p)} P, {len(ctrl_s)} S'
    )
    lines.append('')
    lines.append('| Subset | 30d | 90d | 180d | 365d |')
    lines.append('|---|---:|---:|---:|---:|')
    for label, alphas in [
        (f'{name} buys', {h: [a for (t, a) in pel_a[h] if t.direction == 'P'] for h in HORIZONS}),
        (f'{name} sells', {h: [a for (t, a) in pel_a[h] if t.direction == 'S'] for h in HORIZONS}),
        ('Control buys', {h: [a for (t, a) in ctrl_a[h] if t.direction == 'P'] for h in HORIZONS}),
        ('Control sells', {h: [a for (t, a) in ctrl_a[h] if t.direction == 'S'] for h in HORIZONS}),
    ]:
        lines.append(f'| {label} | ' + ' | '.join(str(len(alphas[h])) for h in HORIZONS) + ' |')
    lines.append('')
    lines.append(f'SPY price coverage ends {spy_max.isoformat()}; horizons crossing that date are dropped.')
    lines.append('')

    # Rigorous tables — buys
    lines.append(f'## Rigorous: {name} BUYS vs Control BUYS')
    lines.append('')
    lines.append('| Horizon | n | n_eff | Hit % | Mean α | Median α | σ_α | Annualised α | Ctrl mean α | t | p |')
    lines.append('|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|')
    for h in HORIZONS:
        a = [v for (t, v) in pel_a[h] if t.direction == 'P']
        ca = [v for (t, v) in ctrl_a[h] if t.direction == 'P']
        if not a:
            continue
        clusters = len({t.tx_date for (t, v) in pel_a[h] if t.direction == 'P'})
        t_stat, p_val, _ = welch_t(a, ca)
        sig = pstdev(a) if len(a) > 1 else 0.0
        lines.append(
            f'| {h}d | {len(a)} | {clusters} | {hit_rate(a) * 100:.1f}% | '
            f'{fmt_pct(mean(a))} | {fmt_pct(median(a))} | {sig:.3f} | '
            f'{fmt_pct(annualise(mean(a), h))} | {fmt_pct(mean(ca)) if ca else "n/a"} | '
            f'{t_stat:+.2f} | {fmt_p(p_val)} |'
        )
    lines.append('')

    # Rigorous tables — sells
    lines.append(f'## Rigorous: {name} SELLS vs Control SELLS')
    lines.append('')
    lines.append('| Horizon | n | n_eff | Hit % | Mean α | Median α | σ_α | Annualised α | Ctrl mean α | t | p |')
    lines.append('|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|')
    for h in HORIZONS:
        a = [v for (t, v) in pel_a[h] if t.direction == 'S']
        ca = [v for (t, v) in ctrl_a[h] if t.direction == 'S']
        if not a:
            continue
        clusters = len({t.tx_date for (t, v) in pel_a[h] if t.direction == 'S'})
        t_stat, p_val, _ = welch_t(a, ca)
        sig = pstdev(a) if len(a) > 1 else 0.0
        lines.append(
            f'| {h}d | {len(a)} | {clusters} | {hit_rate(a) * 100:.1f}% | '
            f'{fmt_pct(mean(a))} | {fmt_pct(median(a))} | {sig:.3f} | '
            f'{fmt_pct(annualise(mean(a), h))} | {fmt_pct(mean(ca)) if ca else "n/a"} | '
            f'{t_stat:+.2f} | {fmt_p(p_val)} |'
        )
    lines.append('')

    # Cluster-descriptive pass
    lines.append(f'## Descriptive: cluster-level batting average ({name})')
    lines.append('')
    lines.append(
        'Group same-day same-direction trades into one cluster. Cluster α = '
        'equal-weight mean across tickers. Hit = cluster α > 0. **No t-test** — '
        'cluster count is too low for inference; this section is descriptive.'
    )
    lines.append('')
    for direction, label in (('P', 'Buy'), ('S', 'Sell')):
        lines.append(f'### {label} clusters')
        lines.append('')
        lines.append('| Date | Tickers | n trades | Mean α @ 30d | @ 90d | @ 180d | @ 365d |')
        lines.append('|---|---|---:|---:|---:|---:|---:|')
        cluster_alphas: Dict[int, List[float]] = {h: [] for h in HORIZONS}
        # gather (date -> {h: [alphas]}, tickers)
        per_date: Dict[date, Dict[str, List]] = defaultdict(lambda: {'tickers': [], 'h': {h: [] for h in HORIZONS}})
        for h in HORIZONS:
            for (t, a) in pel_a[h]:
                if t.direction != direction:
                    continue
                per_date[t.tx_date]['h'][h].append(a)
                if t.ticker not in per_date[t.tx_date]['tickers']:
                    per_date[t.tx_date]['tickers'].append(t.ticker)
        for d in sorted(per_date.keys()):
            entry = per_date[d]
            row = [d.isoformat(), ','.join(entry['tickers']), str(max(len(entry['h'][h]) for h in HORIZONS))]
            for h in HORIZONS:
                vs = entry['h'][h]
                if vs:
                    m = mean(vs)
                    row.append(fmt_pct(m))
                    cluster_alphas[h].append(m)
                else:
                    row.append('—')
            lines.append('| ' + ' | '.join(row) + ' |')
        lines.append('')
        lines.append('**Cluster batting average**')
        lines.append('')
        lines.append('| Horizon | Clusters | Hit % | Mean cluster α | Annualised |')
        lines.append('|---|---:|---:|---:|---:|')
        for h in HORIZONS:
            cs = cluster_alphas[h]
            if cs:
                lines.append(
                    f'| {h}d | {len(cs)} | {hit_rate(cs) * 100:.1f}% | '
                    f'{fmt_pct(mean(cs))} | {fmt_pct(annualise(mean(cs), h))} |'
                )
        lines.append('')

    # Caveats (templated; user adds context manually if needed)
    lines.append('## Caveats')
    lines.append('')
    lines.append(
        '1. **Trade clustering.** Same-day batches reduce effective n. '
        'Cluster-aware n shown above; rigorous t-test still uses raw n and '
        'will be optimistic.'
    )
    lines.append(
        '2. **Bull-market conditioning.** 2023-2025 was a megacap-tech rally. '
        'Concentrated buys in NVDA/GOOGL/AMZN/AVGO/VST will look smart in '
        'this regime regardless of edge. Out-of-sample test is a future '
        'bear/sideways tape.'
    )
    lines.append(
        '3. **Joint-account / spouse trading.** Most rows are filed under '
        'SP (spouse) ownership. Cannot separate "Senator/Rep edge channeled '
        'via joint account" from "spouse independent decisions" from the data.'
    )
    lines.append(
        '4. **Reporting lag.** PTRs filed up to 45 days after the trade. '
        'Tradable alpha for someone reading the disclosure is meaningfully '
        'smaller than measured (especially at 30d horizon).'
    )
    lines.append(
        '5. **Options vs equity.** `[OP]` flag in `asset_description` denotes '
        'options trades; the script computes alpha against the underlying '
        'common stock. Long-call P&L is leveraged and asymmetric — a +10% '
        'underlying move is not +10% on the option. Real economic alpha '
        'differs from this proxy.'
    )
    lines.append(
        '6. **Survivorship in `price_history`.** Only ~792 tickers covered. '
        'Trades on missing tickers are silently dropped.'
    )
    lines.append('')

    lines.append('## Recommendation')
    lines.append('')
    lines.append(
        '_(filled in manually after reviewing numbers above — see `gates.py` '
        'and `signal_inventory.md` for the registered decision.)_'
    )
    lines.append('')
    return '\n'.join(lines) + '\n'


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--name', required=True, help='politician_name as stored in DB')
    ap.add_argument('--out', required=True, help='markdown output path')
    args = ap.parse_args()

    conn = get_connection()

    pel = load_trades(conn, args.name, control=False)
    if not pel:
        print(f'No trades found for {args.name!r}', file=sys.stderr)
        return 1
    pel_p = [t for t in pel if t.direction == 'P']
    pel_s = [t for t in pel if t.direction == 'S']

    ctrl = load_trades(conn, args.name, control=True)
    ctrl_p = [t for t in ctrl if t.direction == 'P']
    ctrl_s = [t for t in ctrl if t.direction == 'S']

    tickers = list({t.ticker for t in pel + ctrl} | {'SPY'})
    prices = load_prices(conn, tickers)
    spy = prices.get('SPY', {})
    if not spy:
        print('SPY missing from price_history', file=sys.stderr)
        return 2
    spy_max = max(spy.keys())

    pel_a = compute_alphas(pel, prices, spy, spy_max)
    ctrl_a = compute_alphas(ctrl, prices, spy, spy_max)

    out = render_report(args.name, pel_p, pel_s, ctrl_p, ctrl_s, pel_a, ctrl_a, spy_max)
    Path(args.out).write_text(out)
    print(f'Wrote {args.out}')
    print(
        f'Pelosi: {len(pel_p)} P / {len(pel_s)} S; '
        f'matched 365d alphas: '
        f'{sum(1 for (t, _) in pel_a[365] if t.direction == "P")} P, '
        f'{sum(1 for (t, _) in pel_a[365] if t.direction == "S")} S'
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())
