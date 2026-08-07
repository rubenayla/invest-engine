"""Show recent insider transactions for a ticker via Finnhub.

Usage: uv run python scripts/finnhub_insiders.py TICKER [--all] [--days N]

Defaults to open-market buys (P) and sales (S) only — these are the codes that
carry signal. Grants, option exercises, gifts, and tax withholdings are noise
unless --all is passed.

Requires FINNHUB_API_KEY in .env (or environment).
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

ENV_PATH = Path(__file__).resolve().parent.parent / '.env'
if ENV_PATH.exists():
    for line in ENV_PATH.read_text().splitlines():
        if line.strip() and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip())

API_KEY = os.environ.get('FINNHUB_API_KEY')
if not API_KEY:
    sys.exit('FINNHUB_API_KEY not set (add to .env)')

# Form 4 codes worth surfacing. Open-market P/S are the real signal.
SIGNAL_CODES = {'P', 'S'}
CODE_NAMES = {
    'P': 'open-market purchase',
    'S': 'open-market sale',
    'A': 'grant/award',
    'M': 'option exercise',
    'F': 'tax withholding',
    'G': 'gift',
    'D': 'disposition',
}


def fetch(ticker: str) -> list[dict]:
    r = requests.get(
        'https://finnhub.io/api/v1/stock/insider-transactions',
        params={'symbol': ticker, 'token': API_KEY},
        timeout=15,
    )
    r.raise_for_status()
    return r.json().get('data', []) or []


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('ticker')
    p.add_argument('--all', action='store_true', help='Include grants, options, gifts (noisy)')
    p.add_argument('--days', type=int, default=365, help='Lookback window (default 365)')
    args = p.parse_args()

    rows = fetch(args.ticker.upper())
    if not rows:
        print(f'No insider transactions returned for {args.ticker}.')
        return

    cutoff = date.today() - timedelta(days=args.days)
    filtered = []
    for row in rows:
        try:
            tdate = datetime.strptime(row['transactionDate'], '%Y-%m-%d').date()
        except (KeyError, TypeError, ValueError):
            continue
        if tdate < cutoff:
            continue
        if not args.all and row.get('transactionCode') not in SIGNAL_CODES:
            continue
        filtered.append((tdate, row))

    if not filtered:
        scope = 'open-market trades' if not args.all else 'transactions'
        print(f'No {scope} for {args.ticker} in the last {args.days} days.')
        print('Tip: re-run with --all to include grants/options/gifts.')
        return

    filtered.sort(key=lambda t: t[0], reverse=True)

    # Rolling net (signal codes only, dollar-weighted)
    buckets = {'30d': 0.0, '90d': 0.0, '365d': 0.0}
    insider_net = defaultdict(float)
    today = date.today()
    for tdate, row in filtered:
        if row.get('transactionCode') not in SIGNAL_CODES:
            continue
        price = row.get('transactionPrice') or 0
        if not price:
            continue
        dollars = row['change'] * price  # change is signed: P positive, S negative
        age = (today - tdate).days
        if age <= 30:
            buckets['30d'] += dollars
        if age <= 90:
            buckets['90d'] += dollars
        if age <= 365:
            buckets['365d'] += dollars
        insider_net[row['name']] += dollars

    print(f'\n=== {args.ticker.upper()} insider activity (last {args.days}d) ===')
    print(f'Rolling net $ (open-market P/S only):')
    for k, v in buckets.items():
        sign = '+' if v >= 0 else ''
        print(f'  {k:>5}: {sign}${v:,.0f}')

    buyers = sorted([(n, v) for n, v in insider_net.items() if v > 0], key=lambda x: -x[1])
    sellers = sorted([(n, v) for n, v in insider_net.items() if v < 0], key=lambda x: x[1])
    if buyers:
        print('\nNet buyers:')
        for n, v in buyers[:5]:
            print(f'  +${v:>12,.0f}  {n}')
    if sellers:
        print('\nNet sellers:')
        for n, v in sellers[:5]:
            print(f'  ${v:>13,.0f}  {n}')

    print(f'\nRecent transactions ({len(filtered)} shown):')
    print(f'  {"date":<11} {"code":<5} {"shares":>10} {"price":>9}  insider')
    for tdate, row in filtered[:25]:
        code = row.get('transactionCode', '?')
        shares = row.get('change', 0)
        price = row.get('transactionPrice') or 0
        print(f'  {tdate.isoformat():<11} {code:<5} {shares:>10,} {price:>9.2f}  {row.get("name", "?")}')


if __name__ == '__main__':
    main()
