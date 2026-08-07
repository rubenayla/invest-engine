#!/usr/bin/env python3
"""
Run all backtest strategies and generate comparison report.
"""

import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Backtest configurations to run
BACKTEST_CONFIGS = [
    {
        'name': 'SPY Benchmark',
        'config': 'models/backtesting/configs/spy_benchmark.yaml',
        'description': 'Buy-and-hold S&P 500 (baseline)'
    },
    {
        'name': 'GBM Top Decile 1y',
        'config': 'models/backtesting/configs/gbm_top_decile_1y.yaml',
        'description': 'Full GBM 1y model, top 10%, equal weight'
    },
    {
        'name': 'GBM Lite Top Quintile',
        'config': 'models/backtesting/configs/gbm_lite_top_quintile.yaml',
        'description': 'Lite GBM 1y model, top 20%, equal weight'
    },
    {
        'name': 'GBM Opportunistic 3y',
        'config': 'models/backtesting/configs/gbm_opportunistic_3y.yaml',
        'description': 'Opportunistic 3y model (Rank IC 0.64), prediction-weighted'
    },
    {
        'name': 'GBM Risk-Managed',
        'config': 'models/backtesting/configs/gbm_risk_managed.yaml',
        'description': 'Lite GBM with inverse volatility weighting, monthly rebal'
    },
]


def run_backtest(config_path: str) -> dict:
    """
    Run a single backtest.

    Parameters
    ----------
    config_path : str
        Path to YAML config file

    Returns
    -------
    dict
        Backtest results summary
    """
    logger.info(f'Running backtest: {config_path}')

    cmd = [
        'uv', 'run', 'python',
        'models/backtesting/run_backtest.py',
        config_path,
        '--output-dir', 'models/backtesting/reports'
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            cwd=Path(__file__).parent.parent  # repo root
        )

        logger.info(f'✅ Completed: {config_path}')
        return {'status': 'success', 'output': result.stdout}

    except subprocess.CalledProcessError as e:
        logger.error(f'❌ Failed: {config_path}')
        logger.error(f'Error: {e.stderr}')
        return {'status': 'failed', 'error': str(e)}


def parse_backtest_results(report_dir: Path) -> pd.DataFrame:
    """
    Parse backtest results from CSV files.

    Parameters
    ----------
    report_dir : Path
        Directory containing backtest report CSV files

    Returns
    -------
    pd.DataFrame
        Summary of all backtest results
    """
    results = []

    # Find all summary CSV files
    summary_files = sorted(report_dir.glob('*_summary.csv'))

    for file in summary_files:
        try:
            # Read summary data
            pd.read_csv(file)

            # Extract strategy name from filename
            strategy_name = file.stem.replace('_summary', '').replace('_' + file.stem.split('_')[-1], '')

            # Get key metrics (assuming standard format)
            # You'll need to adjust this based on actual CSV format
            results.append({
                'Strategy': strategy_name,
                'File': file.name,
            })

        except Exception as e:
            logger.warning(f'Could not parse {file}: {e}')

    return pd.DataFrame(results)


def generate_comparison_report(results: pd.DataFrame) -> str:
    """
    Generate markdown comparison report.

    Parameters
    ----------
    results : pd.DataFrame
        Combined backtest results

    Returns
    -------
    str
        Markdown report
    """
    report = f"""# Backtest Comparison Report

**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Period**: 2010-01-01 to 2024-12-31 (14 years)
**Initial Capital**: $100,000

---

## Strategies Tested

"""

    for _, config in enumerate(BACKTEST_CONFIGS):
        report += f"**{config['name']}**: {config['description']}\n\n"

    report += f"""
---

## Results Summary

{results.to_markdown(index=False)}

---

## Interpretation

### Best Total Return
Look for highest final value and CAGR

### Best Risk-Adjusted Return
Look for highest Sharpe ratio (returns per unit of risk)

### Best Downside Protection
Look for smallest max drawdown

### Most Consistent
Look for highest percentage of positive years

---

## Next Steps

1. Review detailed reports in `models/backtesting/reports/`
2. Analyze portfolio composition over time
3. Check transaction costs and turnover
4. Validate assumptions and data quality

"""

    return report


def main():
    """Run all backtests and generate comparison."""

    logger.info('='*60)
    logger.info('BACKTEST COMPARISON RUNNER')
    logger.info('='*60)

    repo_root = Path(__file__).parent.parent

    # Check if model files exist
    models_to_check = [
        repo_root / 'models' / 'neural_network' / 'training' / 'gbm_model_1y.txt',
        repo_root / 'models' / 'neural_network' / 'training' / 'gbm_lite_model_1y.txt',
        repo_root / 'models' / 'neural_network' / 'training' / 'gbm_opportunistic_model_3y.txt',
    ]

    missing_models = [m for m in models_to_check if not m.exists()]
    if missing_models:
        logger.error('❌ Missing GBM model files:')
        for model in missing_models:
            logger.error(f'   - {model}')
        logger.error('\nPlease train models first or check paths.')
        sys.exit(1)

    logger.info('✅ All required model files found')
    logger.info(f'\nRunning {len(BACKTEST_CONFIGS)} backtests...\n')

    # Run all backtests
    for i, config in enumerate(BACKTEST_CONFIGS, 1):
        logger.info(f'[{i}/{len(BACKTEST_CONFIGS)}] {config["name"]}')
        result = run_backtest(config['config'])

        if result['status'] == 'failed':
            logger.error('Backtest failed. Check logs above.')
            # Continue with other backtests even if one fails
            continue

        print()  # Blank line between runs

    # Parse results
    logger.info('\n' + '='*60)
    logger.info('PARSING RESULTS')
    logger.info('='*60)

    report_dir = repo_root / 'models' / 'backtesting' / 'reports'
    results_df = parse_backtest_results(report_dir)

    logger.info(f'\nFound {len(results_df)} result files')

    # Generate comparison report
    report = generate_comparison_report(results_df)

    # Save report
    report_path = report_dir / f'comparison_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.md'
    report_path.write_text(report)

    logger.info(f'\n✅ Comparison report saved to: {report_path}')

    # Print summary
    print('\n' + '='*60)
    print('BACKTEST COMPARISON COMPLETE')
    print('='*60)
    print(f'\nResults saved in: {report_dir}')
    print(f'Comparison report: {report_path}')
    print('\nReview the reports to see which strategy performed best!')


if __name__ == '__main__':
    main()
