#!/usr/bin/env python3
"""
Run all prediction models at once and generate dashboard.

This script orchestrates the complete prediction pipeline:
1. GBM models (6 variants)
2. Classic valuation models
3. Dashboard generation

Usage:
    uv run python scripts/run_all_predictions.py
    uv run python scripts/run_all_predictions.py --models gbm
    uv run python scripts/run_all_predictions.py --skip-dashboard
"""

import argparse
import subprocess
import sys
import time
from datetime import datetime


class Colors:
    """Terminal colors for output."""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def print_header(msg: str):
    """Print a header message."""
    print(f'\n{Colors.BOLD}{Colors.HEADER}{msg}{Colors.ENDC}')


def print_info(msg: str):
    """Print an info message."""
    print(f'{Colors.CYAN}ℹ {msg}{Colors.ENDC}')


def print_success(msg: str):
    """Print a success message."""
    print(f'{Colors.GREEN}✓ {msg}{Colors.ENDC}')


def print_error(msg: str):
    """Print an error message."""
    print(f'{Colors.RED}✗ {msg}{Colors.ENDC}')


def print_warning(msg: str):
    """Print a warning message."""
    print(f'{Colors.YELLOW}⚠ {msg}{Colors.ENDC}')


def run_command(cmd: list[str], description: str) -> tuple[bool, float]:
    """
    Run a command and return success status and execution time.

    Parameters
    ----------
    cmd : list[str]
        Command to run
    description : str
        Human-readable description

    Returns
    -------
    tuple[bool, float]
        (success, elapsed_seconds)
    """
    print_info(f'Running: {description}')
    start = time.time()

    try:
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True
        )
        elapsed = time.time() - start
        print_success(f'{description} completed in {elapsed:.1f}s')
        return True, elapsed
    except subprocess.CalledProcessError as e:
        elapsed = time.time() - start
        print_error(f'{description} failed after {elapsed:.1f}s')
        if e.stderr:
            print(f'  Error: {e.stderr[:200]}')
        return False, elapsed


def run_gbm_models() -> dict:
    """Run all GBM model variants."""
    print_header('📊 Running GBM Models')

    variants = [
        ('standard', '1y'),
        ('standard', '3y'),
        ('lite', '1y'),
        ('lite', '3y'),
        ('opportunistic', '1y'),
        ('opportunistic', '3y'),
    ]

    results = {}
    total_time = 0

    for variant, horizon in variants:
        cmd = [
            sys.executable,'scripts/run_gbm_predictions.py',
            '--variant', variant,
            '--horizon', horizon
        ]
        description = f'GBM {variant} {horizon}'
        success, elapsed = run_command(cmd, description)
        results[f'gbm_{variant}_{horizon}'] = success
        total_time += elapsed

    print_info(f'Total GBM time: {total_time:.1f}s')
    return results


def run_classic_models() -> dict:
    """Run classic valuation models."""
    print_header('💰 Running Classic Valuation Models')

    cmd = [sys.executable,'scripts/run_classic_valuations.py']
    success, elapsed = run_command(cmd, 'Classic valuations (DCF, RIM, etc.)')

    return {'classic': success}


def generate_dashboard() -> dict:
    """Generate dashboard."""
    print_header('📈 Generating Dashboard')

    cmd = [sys.executable,'scripts/dashboard.py']
    success, elapsed = run_command(cmd, 'Dashboard generation')

    return {'dashboard': success}


def print_summary(results: dict, total_time: float):
    """Print execution summary."""
    print_header('Summary')

    successful = sum(1 for v in results.values() if v)
    failed = sum(1 for v in results.values() if not v)

    print(f'\n{"="*60}')
    print(f'Total time: {total_time:.1f}s ({total_time/60:.1f} minutes)')
    print(f'Successful: {successful}')
    print(f'Failed: {failed}')
    print(f'{"="*60}\n')

    if failed > 0:
        print_warning('Failed tasks:')
        for name, success in results.items():
            if not success:
                print(f'  - {name}')
        print()

    if successful == len(results):
        print_success('All predictions completed successfully!')
        print_info('Dashboard available at: dashboard/valuation_dashboard.html')
    else:
        print_error(f'{failed} task(s) failed')


def main():
    """Run all prediction models."""
    parser = argparse.ArgumentParser(
        description='Run all prediction models and generate dashboard',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                           # Run everything
  %(prog)s --models gbm              # Run only GBM models
  %(prog)s --skip-dashboard          # Skip dashboard generation
  %(prog)s --models classic          # Run only classic valuations
        """
    )
    parser.add_argument(
        '--models',
        help='Comma-separated list of model types (gbm,classic)',
        default='gbm,classic'
    )
    parser.add_argument(
        '--skip-dashboard',
        action='store_true',
        help='Skip dashboard generation'
    )
    args = parser.parse_args()

    start_time = time.time()
    all_results = {}

    print_header(f'🚀 Running All Predictions - {datetime.now():%Y-%m-%d %H:%M:%S}')

    # Parse which models to run
    model_types = [m.strip() for m in args.models.split(',')]

    # Run models
    if 'gbm' in model_types:
        all_results.update(run_gbm_models())

    if 'classic' in model_types:
        all_results.update(run_classic_models())

    # Generate dashboard
    if not args.skip_dashboard:
        all_results.update(generate_dashboard())

    # Print summary
    total_time = time.time() - start_time
    print_summary(all_results, total_time)

    # Exit with error code if any failed
    if any(not success for success in all_results.values()):
        sys.exit(1)


if __name__ == '__main__':
    main()
