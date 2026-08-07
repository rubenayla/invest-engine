#!/usr/bin/env python3
"""
Update stock data, run model predictions, and generate the dashboard.

Usage:
    uv run python scripts/update_all.py
    uv run python scripts/update_all.py --universe sp500
    uv run python scripts/update_all.py --skip-fetch --skip-nn
"""

from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / 'src'))

from invest.config.logging_config import setup_logging


def ensure_db_tunnel(host: str = 'localhost', port: int = 5433, ssh_alias: str = 'hetzner-db') -> None:
    """Open SSH tunnel to Hetzner Postgres if port 5433 is not already reachable.

    The Mac connects to the production Postgres via an SSH tunnel; without it,
    every model script crashes with "Connection refused". Idempotent: no-op if
    the port is already up (existing tunnel or running locally).
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(2)
        try:
            s.connect((host, port))
            return
        except (socket.timeout, ConnectionRefusedError, OSError):
            pass

    print(f'==> Opening SSH tunnel to {ssh_alias} on localhost:{port}')
    result = subprocess.run(
        ['ssh', '-fN', '-L', f'{port}:localhost:5432', ssh_alias],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f'   ssh tunnel failed: {result.stderr.strip()}', file=sys.stderr)
        sys.exit(1)


def run_cmd(cmd: List[str], label: str) -> None:
    """Run a command and print timing info."""
    print(f'\n==> {label}')
    start = time.time()
    subprocess.run(cmd, check=True)
    elapsed = time.time() - start
    print(f'==> Done in {elapsed:.1f}s')


def ensure_dashboard_data() -> bool:
    """Create dashboard_data.json if it does not exist."""
    data_path = REPO_ROOT / 'dashboard' / 'dashboard_data.json'
    if data_path.exists():
        return True

    sys.path.insert(0, str(REPO_ROOT / 'src'))
    try:
        from invest.dashboard_components.data_manager import DataManager
        from invest.data.stock_data_reader import StockDataReader
    except Exception as exc:
        print(f'Could not import dashboard helpers: {exc}')
        return False

    reader = StockDataReader()
    tickers = reader.get_all_tickers()
    if not tickers:
        print('No tickers found in current_stock_data; skipping NN update.')
        return False

    manager = DataManager(output_dir=str(REPO_ROOT / 'dashboard'))
    manager.initialize_stocks(tickers)
    manager.save_data()
    print(f'Created {data_path} with {len(tickers)} stocks')
    return True


def run_gbm_predictions() -> None:
    """Run all GBM prediction variants."""
    variants = [
        ('standard', '1y'),
        ('standard', '3y'),
        ('lite', '1y'),
        ('lite', '3y'),
        ('opportunistic', '1y'),
        ('opportunistic', '3y'),
    ]
    for variant, horizon in variants:
        run_cmd(
            [
                sys.executable,'scripts/run_gbm_predictions.py',
                '--variant', variant,
                '--horizon', horizon,
            ],
            f'GBM {variant} {horizon}',
        )


def main() -> int:
    setup_logging(log_file_path="logs/update_all.log")
    ensure_db_tunnel()

    parser = argparse.ArgumentParser(
        description='Update data, run predictions, and regenerate the dashboard',
    )
    parser.add_argument('--universe', default='all', help='Universe for data fetcher (default: all)')
    parser.add_argument('--max-concurrent', type=int, default=10, help='Max concurrent fetches')
    parser.add_argument('--skip-fetch', action='store_true', help='Skip data fetching step')
    parser.add_argument('--skip-gbm', action='store_true', help='Skip GBM predictions')
    parser.add_argument('--skip-nn', action='store_true', help='Skip NN predictions')
    parser.add_argument('--skip-autoresearch', action='store_true', help='Skip autoresearch predictions')
    parser.add_argument('--skip-classic', action='store_true', help='Skip classic valuations')
    parser.add_argument('--skip-dashboard', action='store_true', help='Skip dashboard generation')
    parser.add_argument('--skip-insider', action='store_true', help='Skip insider data fetching')
    parser.add_argument('--skip-activist', action='store_true', help='Skip activist stakes (13D/13G)')
    parser.add_argument('--skip-holdings', action='store_true', help='Skip institutional holdings (13F)')
    parser.add_argument('--skip-edinet', action='store_true', help='Skip EDINET Japan data')
    parser.add_argument('--skip-politician', action='store_true', help='Skip House PTR politician trades')
    parser.add_argument('--skip-truthsocial', action='store_true', help='Skip Truth Social Trump-post fetch')
    parser.add_argument('--skip-polymarket-policy', action='store_true',
                        help='Skip Polymarket Trump-policy market poll')
    parser.add_argument('--skip-scanner', action='store_true', help='Skip opportunity scanner')
    parser.add_argument('--lite-fetch', action='store_true',
                        help='Lite mode: fetch prices+metrics only (no statements/insider/activist/holdings/edinet)')
    args = parser.parse_args()

    # Lite mode implies skipping heavy data sources
    if args.lite_fetch:
        args.skip_insider = True
        args.skip_activist = True
        args.skip_holdings = True
        args.skip_edinet = True
        args.skip_politician = True
        args.skip_truthsocial = True
        args.skip_polymarket_policy = True

    if not args.skip_fetch:
        fetch_cmd = [
            sys.executable,'scripts/data_fetcher.py',
            '--universe', args.universe,
            '--max-concurrent', str(args.max_concurrent),
        ]
        if args.lite_fetch:
            fetch_cmd.append('--lite')
        run_cmd(fetch_cmd, f'Fetching data ({args.universe}){"  [LITE]" if args.lite_fetch else ""}')

    # --- Phase 1b: Insider data (reads SEC EDGAR, writes insider_transactions) ---
    if not args.skip_insider:
        run_cmd(
            [sys.executable,'scripts/fetch_insider_data.py'],
            'Fetching insider data (SEC Form 4)',
        )

    # --- Phase 1c: Activist stakes (SEC 13D/13G) ---
    if not args.skip_activist:
        run_cmd(
            [sys.executable,'scripts/fetch_activist_data.py'],
            'Fetching activist stakes (SEC 13D/13G)',
        )

    # --- Phase 1d: Institutional holdings (SEC 13F) ---
    if not args.skip_holdings:
        run_cmd(
            [sys.executable,'scripts/fetch_holdings_data.py'],
            'Fetching institutional holdings (SEC 13F)',
        )

    # --- Phase 1e: EDINET Japan (if API key set) ---
    if not args.skip_edinet:
        import os
        if os.environ.get('EDINET_API_KEY'):
            run_cmd(
                [sys.executable,'scripts/fetch_edinet_data.py'],
                'Fetching EDINET Japan large shareholding reports',
            )
        else:
            print('\n==> Skipping EDINET (EDINET_API_KEY not set)')

    # --- Phase 1f: House PTR politician trades ---
    if not args.skip_politician:
        from datetime import datetime
        year = datetime.utcnow().year
        run_cmd(
            [sys.executable, 'scripts/fetch_politician_data.py',
             '--years', str(year - 1), str(year)],
            'Fetching House PTR politician trades',
        )

    # --- Phase 1g: Truth Social Trump posts (real-time signal) ---
    if not args.skip_truthsocial:
        run_cmd(
            [sys.executable, 'scripts/fetch_truth_social.py'],
            'Fetching Truth Social posts',
        )

    # --- Phase 1h: Polymarket Trump-policy markets ---
    # Cheap (one HTTP call per page, no heavy parsing) — safe to run frequently.
    # Postgres-down is non-fatal inside the script, so it won't block update_all.
    if not args.skip_polymarket_policy:
        run_cmd(
            [sys.executable, 'scripts/fetch_polymarket_policy.py'],
            'Fetching Polymarket Trump-policy markets',
        )

    # --- Phase 2: Valuations (independent of each other) ---
    # GBM reads fundamental_history + price_history; classic reads current_stock_data.
    # Both write to valuation_results. Order between them doesn't matter.
    if not args.skip_gbm:
        run_gbm_predictions()

    # NN disabled: near-zero test correlation (2026-02-21)
    # if not args.skip_nn:
    #     if ensure_dashboard_data():
    #         run_cmd(
    #             [sys.executable,'scripts/run_multi_horizon_predictions.py'],
    #             'Neural network predictions (multi-horizon)',
    #         )

    if not args.skip_autoresearch:
        run_cmd(
            [sys.executable,'scripts/run_autoresearch_predictions.py'],
            'AutoResearch predictions (5-model ensemble)',
        )

    if not args.skip_classic:
        run_cmd(
            [sys.executable,'scripts/run_classic_valuations.py'],
            'Classic valuations',
        )

    # --- Phase 3: Consumers (independent of each other, need Phase 2 done) ---
    # Dashboard renders valuation_results into HTML.
    # Scanner reads valuation_results for its value_score component.
    # Neither depends on the other; order between them doesn't matter.
    if not args.skip_dashboard:
        run_cmd(
            [sys.executable,'scripts/dashboard.py'],
            'Dashboard generation',
        )

    if not args.skip_scanner:
        run_cmd(
            [sys.executable,'scripts/run_opportunity_scan.py'],
            'Opportunity scanner',
        )

        run_cmd(
            [sys.executable,'scripts/price_alerts.py'],
            'Price target alerts',
        )

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
