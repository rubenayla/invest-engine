"""
Investment strategy using the real analysis pipeline for backtesting.
This ensures backtesting uses the same logic as normal analysis.
"""

import logging
import os
import sys
from typing import Any, Dict, List, Optional

import pandas as pd

# Add src to path to import the real analysis pipeline
sys.path.append(os.path.join(os.path.dirname(__file__), '../../src'))

from invest.analysis.pipeline import AnalysisPipeline
from invest.config.schema import (
    AnalysisConfig,
    GrowthThresholds,
    QualityThresholds,
    RiskThresholds,
    UniverseConfig,
    ValuationConfig,
    ValueThresholds,
)

logger = logging.getLogger(__name__)


class PipelineStrategy:
    """
    Investment strategy that uses the real AnalysisPipeline.
    This ensures backtesting tests the exact same logic used in normal analysis.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize strategy with configuration that matches AnalysisConfig.

        Parameters
        ----------
        config : Dict[str, Any], optional
            Strategy configuration including analysis parameters
        """
        self.config = config or {}

        # Strategy parameters
        self.max_positions = self.config.get('max_positions', 15)
        self.min_composite_score = self.config.get('min_composite_score', 50)
        self.rebalance_threshold = self.config.get('rebalance_threshold', 0.05)

        # Create analysis config from backtest config
        self.analysis_config = self._create_analysis_config()

    def _create_analysis_config(self) -> AnalysisConfig:
        """Create AnalysisConfig from backtest configuration."""

        # Universe configuration
        universe_config = UniverseConfig(
            custom_tickers=None,  # Will be set dynamically
            market_cap_min=1e9,   # $1B minimum
            market_cap_max=None,
            sectors=None,
            exclude_sectors=['Real Estate'],  # Often REITs with different metrics
            exclude_countries=None
        )

        # Quality screening thresholds
        quality_config = QualityThresholds(
            min_roe=self.config.get('min_roe', 0.10),
            min_roic=self.config.get('min_roic', 0.12),
            max_debt_equity=self.config.get('max_debt_equity', 2.0),
            min_current_ratio=self.config.get('min_current_ratio', 1.0),
            min_interest_coverage=self.config.get('min_interest_coverage', 3.0)
        )

        # Value screening thresholds
        value_config = ValueThresholds(
            max_pe=self.config.get('max_pe', 25.0),
            max_pb=self.config.get('max_pb', 4.0),
            max_ev_ebitda=self.config.get('max_ev_ebitda', 15.0),
            max_ev_ebit=self.config.get('max_ev_ebit', 20.0),
            max_p_fcf=self.config.get('max_p_fcf', 20.0)
        )

        # Growth screening thresholds
        growth_config = GrowthThresholds(
            min_revenue_growth=self.config.get('min_revenue_growth', 0.0),
            min_earnings_growth=self.config.get('min_earnings_growth', 0.0),
            min_book_value_growth=self.config.get('min_book_value_growth', 0.0),
            min_fcf_growth=self.config.get('min_fcf_growth', 0.0)
        )

        # Risk screening thresholds
        risk_config = RiskThresholds(
            max_beta=self.config.get('max_beta', 1.5),
            min_liquidity_ratio=self.config.get('min_liquidity_ratio', 1.0),
            cyclical_adjustment=False  # Keep consistent for backtesting
        )

        # Valuation configuration
        valuation_models = self.config.get('valuation_models', ['dcf'])
        valuation_config = ValuationConfig(
            models=valuation_models,
            scenarios=["base"],
            dcf_years=10,
            terminal_growth_rate=0.025,
            pe_target=self.config.get('pe_target', 15.0),
            pb_target=self.config.get('pb_target', 2.5),
            ps_target=self.config.get('ps_target', 2.0),
            ev_ebitda_target=self.config.get('ev_ebitda_target', 12.0),
            dividend_yield_target=self.config.get('dividend_yield_target', 0.03),
            peg_target=self.config.get('peg_target', 1.0)
        )

        # Main analysis configuration
        analysis_config = AnalysisConfig(
            name="backtest_analysis",
            universe=universe_config,
            quality=quality_config,
            value=value_config,
            growth=growth_config,
            risk=risk_config,
            valuation=valuation_config,
            max_results=self.max_positions * 2,  # Allow more for selection
            generate_reports=False,
            save_data=False
        )

        return analysis_config

    def generate_signals(self, market_data: Dict[str, Any],
                         current_portfolio: Dict[str, float],
                         date: pd.Timestamp) -> Dict[str, float]:
        """
        Generate target portfolio weights using the real analysis pipeline.

        Parameters
        ----------
        market_data : Dict[str, Any]
            Point-in-time market data including prices and fundamentals
        current_portfolio : Dict[str, float]
            Current portfolio holdings
        date : pd.Timestamp
            Current date

        Returns
        -------
        Dict[str, float]
            Target weights for each ticker
        """
        logger.info(f"Running pipeline analysis for {date}")

        try:
            # Get available tickers from market data
            current_prices = market_data.get('current_prices', {})
            financial_metrics = market_data.get('financial_metrics', {})

            if not current_prices or not financial_metrics:
                logger.warning("No market data available, maintaining current portfolio")
                return current_portfolio

            # Create stock data in the format expected by the pipeline
            stocks_data = self._prepare_stocks_data(current_prices, financial_metrics)

            if not stocks_data:
                logger.warning("No valid stock data prepared, maintaining current portfolio")
                return current_portfolio

            # Update universe config with current tickers
            self.analysis_config.universe.custom_tickers = list(current_prices.keys())

            # Run the real analysis pipeline
            pipeline = AnalysisPipeline(self.analysis_config)

            # Temporarily override the _get_universe method to use our data
            pipeline._get_universe = lambda: stocks_data

            # Run analysis
            results = pipeline.run_analysis()

            # Extract portfolio weights from results
            target_weights = self._extract_portfolio_weights(results, current_prices)

            logger.info(f"Pipeline selected {len(target_weights)} stocks with total weight {sum(target_weights.values()):.2%}")

            return target_weights

        except Exception as e:
            logger.error(f"Error in pipeline analysis: {e}")
            logger.warning("Maintaining current portfolio due to analysis error")
            return current_portfolio

    def _prepare_stocks_data(self, current_prices: Dict[str, float],
                            financial_metrics: Dict[str, Dict]) -> List[Dict]:
        """Convert backtesting data format to pipeline format."""
        stocks_data = []

        for ticker, price in current_prices.items():
            if ticker not in financial_metrics:
                continue

            metrics = financial_metrics[ticker]

            # Convert to format expected by pipeline
            stock_data = {
                'ticker': ticker,
                'current_price': price,
                'market_cap': metrics.get('market_cap'),
                'sector': metrics.get('sector', 'Unknown'),
                'industry': metrics.get('industry', 'Unknown'),

                # Financial ratios
                'pe_ratio': metrics.get('pe_ratio'),
                'pb_ratio': metrics.get('pb_ratio'),
                'ps_ratio': metrics.get('ps_ratio'),
                'debt_to_equity': metrics.get('debt_to_equity'),
                'current_ratio': metrics.get('current_ratio'),
                'roe': metrics.get('roe'),
                'roa': metrics.get('roa'),
                'gross_margin': metrics.get('gross_margin'),
                'operating_margin': metrics.get('operating_margin'),
                'revenue_growth': metrics.get('revenue_growth'),
                'earnings_growth': metrics.get('earnings_growth'),
                'dividend_yield': metrics.get('dividend_yield'),
                'beta': metrics.get('beta'),
                'volatility': metrics.get('volatility'),

                # Price performance
                'return_1m': metrics.get('return_1m'),
                'return_3m': metrics.get('return_3m'),
                'return_6m': metrics.get('return_6m'),
                'return_1y': metrics.get('return_1y'),

                # Technical indicators
                'rsi': metrics.get('rsi'),
                'above_ma50': metrics.get('above_ma50'),
                'above_ma200': metrics.get('above_ma200'),
            }

            stocks_data.append(stock_data)

        return stocks_data

    def _extract_portfolio_weights(self, results: Dict[str, Any],
                                  current_prices: Dict[str, float]) -> Dict[str, float]:
        """Extract portfolio weights from pipeline results."""
        weights = {}

        # Get the top stocks from pipeline results
        stocks = results.get('stocks', [])

        if not stocks:
            logger.warning("No stocks passed pipeline analysis")
            return weights

        # Select top stocks up to max_positions
        selected_stocks = []
        for stock in stocks[:self.max_positions]:
            ticker = stock.get('ticker')
            composite_score = stock.get('composite_score', 0)

            # Apply minimum score filter
            if composite_score >= self.min_composite_score and ticker in current_prices:
                selected_stocks.append((ticker, composite_score))

        if not selected_stocks:
            logger.warning("No stocks passed minimum score threshold")
            return weights

        # Calculate weights based on composite scores
        total_score = sum(score for _, score in selected_stocks)

        if total_score <= 0:
            # Equal weight if all scores are zero/negative
            weight = 0.95 / len(selected_stocks)  # Keep 5% cash
            for ticker, _ in selected_stocks:
                weights[ticker] = weight
        else:
            # Score-weighted allocation
            for ticker, score in selected_stocks:
                weight = (score / total_score) * 0.95  # Keep 5% cash

                # Apply position size limits from backtest config
                min_weight = 0.03  # 3% minimum
                max_weight = 0.15  # 15% maximum
                weight = max(min_weight, min(max_weight, weight))

                weights[ticker] = weight

        # Normalize weights
        total_weight = sum(weights.values())
        if total_weight > 0.95:
            factor = 0.95 / total_weight
            weights = {k: v * factor for k, v in weights.items()}

        return weights
