#!/usr/bin/env python
"""
Run backtesting on investment strategies.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import logging
from datetime import datetime
from pathlib import Path

import yaml

from backtesting.core.engine import Backtester
from backtesting.strategies.etf_portfolio import ETFPortfolioStrategy
from backtesting.strategies.gbm_ranking import GBMRankingStrategy
from backtesting.strategies.market_cap import MarketCapStrategy
from backtesting.strategies.pipeline_strategy import PipelineStrategy
from backtesting.strategies.screening import ScreeningStrategy

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config(config_path: str) -> dict:
    """Load configuration from YAML file."""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description='Run investment strategy backtest')
    parser.add_argument(
        'config',
        help='Path to backtest configuration file'
    )
    parser.add_argument(
        '--output-dir',
        default='models/backtesting/reports',
        help='Directory for output reports'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Load configuration
    logger.info(f"Loading configuration from {args.config}")
    config = load_config(args.config)

    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Initialize backtester
    logger.info("Initializing backtester")
    backtester = Backtester(config)

    # Initialize strategy
    strategy_config = config.get('strategy', {})
    strategy_type = config.get('strategy_type', 'screening')

    if strategy_type == 'gbm_ranking':
        strategy = GBMRankingStrategy(strategy_config)
        logger.info(f"Using GBM ranking strategy: {strategy_config.get('model_path')}")
    elif strategy_type == 'pipeline':
        strategy = PipelineStrategy(strategy_config)
        logger.info("Using real analysis pipeline strategy")
    elif strategy_type == 'market_cap':
        strategy = MarketCapStrategy(strategy_config)
        logger.info("Using market cap weighted strategy")
    elif strategy_type == 'etf_portfolio':
        strategy = ETFPortfolioStrategy(strategy_config)
        logger.info(f"Using ETF portfolio strategy: {strategy_config.get('strategy_type', 'core_satellite')}")
    else:
        strategy = ScreeningStrategy(strategy_config)
        logger.info("Using basic screening strategy")

    # Run backtest
    logger.info(f"Running backtest from {config['start_date']} to {config['end_date']}")
    results = backtester.run(strategy)

    # Generate output files
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    base_name = f"{config.get('name', 'backtest')}_{timestamp}"

    # Save summary
    summary_path = output_dir / f"{base_name}_summary.csv"
    results.to_csv(str(summary_path))
    logger.info(f"Summary saved to {summary_path}")

    # Print results
    print("\n" + "="*60)
    print("BACKTEST RESULTS")
    print("="*60)

    summary = results.get_summary()

    print(f"\nPeriod: {config['start_date']} to {config['end_date']}")
    print(f"Initial Capital: ${summary['initial_capital']:,.2f}")
    print(f"Final Value: ${summary['final_value']:,.2f}")
    print("\nPerformance Metrics:")
    print(f"  Total Return: {summary['total_return']:.2f}%")
    print(f"  Annualized Return: {summary['annualized_return']:.2f}%")
    print(f"  Sharpe Ratio: {summary['sharpe_ratio']:.2f}")
    print(f"  Max Drawdown: {summary['max_drawdown']:.2f}%")
    print(f"  Win Rate: {summary['win_rate']:.2f}%")
    print("\nTrading Activity:")
    print(f"  Number of Trades: {summary['number_of_trades']}")
    print(f"  Portfolio Turnover: {summary['portfolio_turnover']:.2f}")

    # Compare to benchmark if available
    if 'benchmark_return' in results.metrics:
        print(f"\nBenchmark Comparison ({config.get('benchmark', 'SPY')}):")

        # Convert pandas Series to scalar if needed
        def safe_format(value):
            if hasattr(value, 'item'):
                return value.item()
            elif hasattr(value, 'iloc') and len(value) > 0:
                return float(value.iloc[-1])  # Get last value
            else:
                return float(value) if value is not None else 0

        benchmark_return = safe_format(results.metrics['benchmark_return'])
        alpha = safe_format(results.metrics.get('alpha', 0))
        beta = safe_format(results.metrics.get('beta', 0))
        info_ratio = safe_format(results.metrics.get('information_ratio', 0))

        print(f"  Benchmark Return: {benchmark_return:.2f}%")
        print(f"  Alpha: {alpha:.2f}%")
        print(f"  Beta: {beta:.2f}")
        print(f"  Information Ratio: {info_ratio:.2f}")

    print("\n" + "="*60)

    return results


if __name__ == '__main__':
    try:
        results = main()
    except KeyboardInterrupt:
        logger.info("Backtest interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Backtest failed: {e}", exc_info=True)
        sys.exit(1)
