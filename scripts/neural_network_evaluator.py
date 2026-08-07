#!/usr/bin/env python3
'''
Neural Network Model Evaluator
==============================

Comprehensive evaluation system with:
- Proper train/test/validation splits across decades
- Sector-based stratification
- Confidence metrics (prediction intervals, calibration)
- Comparison with other valuation models
- Error analysis and edge case detection
'''

import asyncio
import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from scipy import stats

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import yfinance as yf

from src.invest.valuation.model_registry import ModelRegistry
from src.invest.valuation.neural_network_model import NeuralNetworkValuationModel

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class EvaluationConfig:
    '''Configuration for comprehensive evaluation.'''
    # Time periods for evaluation
    train_start: str = '2004-01-01'
    train_end: str = '2019-12-31'  # 16 years training
    val_start: str = '2020-01-01'
    val_end: str = '2021-12-31'    # 2 years validation
    test_start: str = '2022-01-01'
    test_end: str = '2024-12-31'   # 3 years test

    # Prediction horizons to test
    horizons: List[str] = None

    # Confidence interval levels
    confidence_levels: List[float] = None

    def __post_init__(self):
        if self.horizons is None:
            self.horizons = ['1month', '3month', '1year']
        if self.confidence_levels is None:
            self.confidence_levels = [0.68, 0.95]  # 1σ and 2σ


@dataclass
class PredictionResult:
    '''Single prediction result with actual outcome.'''
    ticker: str
    sector: str
    prediction_date: datetime
    horizon: str

    # Neural network prediction
    nn_score: float
    nn_fair_value: float
    nn_confidence: str

    # Other model predictions (for comparison)
    dcf_fair_value: Optional[float] = None
    graham_fair_value: Optional[float] = None
    ratios_fair_value: Optional[float] = None

    # Actual outcome
    actual_price: float = None
    actual_return: float = None

    # Metadata
    current_price: float = None
    market_cap: float = None
    pe_ratio: float = None


@dataclass
class ModelEvaluation:
    '''Comprehensive model evaluation results.'''
    # Overall metrics
    mae: float
    rmse: float
    mape: float
    r_squared: float
    correlation: float

    # Confidence metrics
    calibration_score: float  # How well confidence matches accuracy
    prediction_interval_coverage: Dict[float, float]  # Coverage at each CI level

    # Comparison with other models
    vs_dcf_improvement: float
    vs_graham_improvement: float
    vs_ratios_improvement: float

    # Sector-wise performance
    sector_performance: Dict[str, Dict[str, float]]

    # Time-based performance
    decade_performance: Dict[str, Dict[str, float]]

    # Edge cases and outliers
    large_errors: List[PredictionResult]  # Top 10 worst predictions
    model_disagreements: List[PredictionResult]  # Where NN differs most from others

    # Confidence analysis
    confidence_accuracy: Dict[str, float]  # Accuracy by confidence level


class NeuralNetworkEvaluator:
    '''Comprehensive neural network evaluation system.'''

    def __init__(self, config: EvaluationConfig):
        self.config = config
        self.registry = ModelRegistry()
        self.results: List[PredictionResult] = []

    def get_stock_universe(self) -> Dict[str, List[str]]:
        '''Get stocks organized by sector for balanced evaluation.'''
        return {
            'Technology': [
                'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'ADBE',
                'CRM', 'INTC', 'AMD', 'ORCL', 'QCOM'
            ],
            'Healthcare': [
                'JNJ', 'UNH', 'PFE', 'ABBV', 'TMO', 'ABT', 'MRK',
                'LLY', 'GILD', 'AMGN'
            ],
            'Financial Services': [
                'JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'AXP', 'BLK'
            ],
            'Consumer Cyclical': [
                'TSLA', 'HD', 'MCD', 'NKE', 'SBUX', 'TGT', 'LOW'
            ],
            'Consumer Defensive': [
                'PG', 'KO', 'PEP', 'WMT', 'COST', 'PM', 'MDLZ'
            ],
            'Energy': [
                'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'PXD'
            ],
            'Industrials': [
                'CAT', 'UNP', 'HON', 'BA', 'GE', 'MMM', 'LMT'
            ],
            'Communication Services': [
                'NFLX', 'DIS', 'CMCSA', 'T', 'VZ', 'TMUS'
            ]
        }

    async def collect_historical_predictions(
        self,
        model: NeuralNetworkValuationModel,
        split: str = 'test'
    ) -> List[PredictionResult]:
        '''
        Collect predictions and actual outcomes for evaluation.

        Parameters
        ----------
        model : NeuralNetworkValuationModel
            Trained model to evaluate
        split : str
            'train', 'val', or 'test'
        '''
        if split == 'train':
            start_date = self.config.train_start
            end_date = self.config.train_end
        elif split == 'val':
            start_date = self.config.val_start
            end_date = self.config.val_end
        else:
            start_date = self.config.test_start
            end_date = self.config.test_end

        stock_universe = self.get_stock_universe()
        results = []

        # Sample prediction dates (quarterly to reduce data load)
        pred_dates = pd.date_range(start_date, end_date, freq='3M')

        for sector, tickers in stock_universe.items():
            for ticker in tickers:
                for pred_date in pred_dates:
                    try:
                        # Get historical data at prediction date
                        hist_data = await self._get_historical_data(ticker, pred_date)
                        if not hist_data:
                            continue

                        # Get NN prediction
                        nn_result = model._calculate_valuation(ticker, hist_data)

                        # Get other model predictions for comparison
                        other_predictions = await self._get_other_model_predictions(
                            ticker, hist_data
                        )

                        # Get actual outcome for each horizon
                        for horizon in self.config.horizons:
                            actual = await self._get_actual_outcome(
                                ticker, pred_date, horizon
                            )

                            if actual:
                                result = PredictionResult(
                                    ticker=ticker,
                                    sector=sector,
                                    prediction_date=pred_date,
                                    horizon=horizon,
                                    nn_score=nn_result.outputs.get('score', 50),
                                    nn_fair_value=nn_result.fair_value,
                                    nn_confidence=nn_result.confidence,
                                    dcf_fair_value=other_predictions.get('dcf'),
                                    graham_fair_value=other_predictions.get('graham'),
                                    ratios_fair_value=other_predictions.get('ratios'),
                                    actual_price=actual['price'],
                                    actual_return=actual['return'],
                                    current_price=nn_result.current_price,
                                    market_cap=hist_data['info'].get('marketCap'),
                                    pe_ratio=hist_data['info'].get('trailingPE')
                                )
                                results.append(result)

                    except Exception as e:
                        logger.warning(f'Failed to evaluate {ticker} at {pred_date}: {e}')
                        continue

        logger.info(f'Collected {len(results)} predictions for {split} set')
        return results

    async def _get_historical_data(
        self,
        ticker: str,
        date: datetime
    ) -> Optional[Dict[str, Any]]:
        '''Get historical financial data as it appeared at a specific date.'''
        try:
            stock = yf.Ticker(ticker)

            # Get price data up to the date
            hist = stock.history(start=date - timedelta(days=365), end=date)
            if hist.empty:
                return None

            # Get fundamentals (yfinance gives current data, so this is approximate)
            info = stock.info

            # Adjust current price to historical price
            info['currentPrice'] = float(hist['Close'].iloc[-1])

            return {'info': info}

        except Exception as e:
            logger.debug(f'Error fetching {ticker} data at {date}: {e}')
            return None

    async def _get_other_model_predictions(
        self,
        ticker: str,
        data: Dict[str, Any]
    ) -> Dict[str, float]:
        '''Get predictions from other models for comparison.'''
        predictions = {}

        for model_name in ['dcf', 'graham', 'simple_ratios']:
            try:
                model = self.registry.get_model(model_name)
                if model.is_suitable(ticker, data):
                    result = model._calculate_valuation(ticker, data)
                    predictions[model_name.replace('_', '')] = result.fair_value
            except Exception as e:
                logger.debug(f'{model_name} failed for {ticker}: {e}')
                continue

        return predictions

    async def _get_actual_outcome(
        self,
        ticker: str,
        pred_date: datetime,
        horizon: str
    ) -> Optional[Dict[str, float]]:
        '''Get actual price outcome after the prediction horizon.'''
        # Calculate future date based on horizon
        days_map = {'1month': 30, '3month': 90, '1year': 365}
        future_date = pred_date + timedelta(days=days_map.get(horizon, 365))

        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(
                start=pred_date,
                end=future_date + timedelta(days=7)
            )

            if len(hist) < 2:
                return None

            initial_price = float(hist['Close'].iloc[0])
            final_price = float(hist['Close'].iloc[-1])
            actual_return = (final_price - initial_price) / initial_price

            return {
                'price': final_price,
                'return': actual_return
            }

        except Exception as e:
            logger.debug(f'Error getting outcome for {ticker}: {e}')
            return None

    def calculate_metrics(
        self,
        results: List[PredictionResult]
    ) -> ModelEvaluation:
        '''Calculate comprehensive evaluation metrics.'''

        if not results:
            raise ValueError('No results to evaluate')

        # Convert to arrays for calculations
        df = pd.DataFrame([vars(r) for r in results])

        # Calculate prediction errors
        df['nn_predicted_return'] = (df['nn_fair_value'] - df['current_price']) / df['current_price']
        df['prediction_error'] = df['actual_return'] - df['nn_predicted_return']
        df['absolute_error'] = df['prediction_error'].abs()
        df['squared_error'] = df['prediction_error'] ** 2
        df['percentage_error'] = (df['absolute_error'] / (df['actual_return'].abs() + 1e-6)) * 100

        # Overall metrics
        mae = df['absolute_error'].mean()
        rmse = np.sqrt(df['squared_error'].mean())
        mape = df['percentage_error'].mean()
        correlation = df['nn_predicted_return'].corr(df['actual_return'])

        # R-squared
        ss_res = df['squared_error'].sum()
        ss_tot = ((df['actual_return'] - df['actual_return'].mean()) ** 2).sum()
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

        # Confidence calibration
        calibration_score = self._calculate_calibration(df)

        # Prediction interval coverage
        pi_coverage = self._calculate_prediction_interval_coverage(df)

        # Model comparison
        vs_dcf = self._compare_models(df, 'dcf_fair_value')
        vs_graham = self._compare_models(df, 'graham_fair_value')
        vs_ratios = self._compare_models(df, 'ratios_fair_value')

        # Sector performance
        sector_perf = {}
        for sector in df['sector'].unique():
            sector_df = df[df['sector'] == sector]
            sector_perf[sector] = {
                'mae': sector_df['absolute_error'].mean(),
                'correlation': sector_df['nn_predicted_return'].corr(sector_df['actual_return']),
                'sample_size': len(sector_df)
            }

        # Decade performance
        df['decade'] = df['prediction_date'].dt.year // 10 * 10
        decade_perf = {}
        for decade in df['decade'].unique():
            decade_df = df[df['decade'] == decade]
            decade_perf[f'{decade}s'] = {
                'mae': decade_df['absolute_error'].mean(),
                'correlation': decade_df['nn_predicted_return'].corr(decade_df['actual_return']),
                'sample_size': len(decade_df)
            }

        # Find worst predictions
        large_errors = df.nlargest(10, 'absolute_error')
        large_error_results = [results[i] for i in large_errors.index]

        # Find model disagreements
        df['model_disagreement'] = 0
        if 'dcf_fair_value' in df.columns:
            df['model_disagreement'] += (df['nn_fair_value'] - df['dcf_fair_value']).abs()
        if 'graham_fair_value' in df.columns:
            df['model_disagreement'] += (df['nn_fair_value'] - df['graham_fair_value']).abs()

        disagreements = df.nlargest(10, 'model_disagreement')
        disagreement_results = [results[i] for i in disagreements.index]

        # Confidence accuracy
        conf_accuracy = {}
        for conf in df['nn_confidence'].unique():
            conf_df = df[df['nn_confidence'] == conf]
            conf_accuracy[conf] = {
                'mae': conf_df['absolute_error'].mean(),
                'count': len(conf_df)
            }

        return ModelEvaluation(
            mae=mae,
            rmse=rmse,
            mape=mape,
            r_squared=r_squared,
            correlation=correlation,
            calibration_score=calibration_score,
            prediction_interval_coverage=pi_coverage,
            vs_dcf_improvement=vs_dcf,
            vs_graham_improvement=vs_graham,
            vs_ratios_improvement=vs_ratios,
            sector_performance=sector_perf,
            decade_performance=decade_perf,
            large_errors=large_error_results,
            model_disagreements=disagreement_results,
            confidence_accuracy=conf_accuracy
        )

    def _calculate_calibration(self, df: pd.DataFrame) -> float:
        '''
        Calculate calibration score: how well confidence matches accuracy.

        Perfect calibration = 1.0
        '''
        confidence_map = {'high': 0.9, 'medium': 0.7, 'low': 0.5}

        if 'nn_confidence' not in df.columns:
            return 0.5

        total_score = 0
        count = 0

        for conf in df['nn_confidence'].unique():
            conf_df = df[df['nn_confidence'] == conf]
            expected_accuracy = confidence_map.get(conf, 0.5)

            # Calculate actual accuracy (within 20% of prediction)
            within_threshold = (conf_df['absolute_error'] < 0.2).mean()

            # Calibration is 1 - |expected - actual|
            calibration = 1 - abs(expected_accuracy - within_threshold)
            total_score += calibration * len(conf_df)
            count += len(conf_df)

        return total_score / count if count > 0 else 0.5

    def _calculate_prediction_interval_coverage(
        self,
        df: pd.DataFrame
    ) -> Dict[float, float]:
        '''Calculate empirical coverage of prediction intervals.'''
        coverage = {}

        for level in self.config.confidence_levels:
            # Use prediction error std to estimate intervals
            std = df['prediction_error'].std()
            z_score = stats.norm.ppf((1 + level) / 2)

            # Count how many actual values fall within interval
            within_interval = (df['prediction_error'].abs() <= z_score * std).mean()
            coverage[level] = within_interval

        return coverage

    def _compare_models(
        self,
        df: pd.DataFrame,
        model_col: str
    ) -> float:
        '''
        Compare NN performance vs another model.

        Returns improvement ratio (positive = NN is better).
        '''
        if model_col not in df.columns:
            return 0.0

        # Filter rows where both models have predictions
        valid = df.dropna(subset=[model_col, 'current_price'])
        if len(valid) == 0:
            return 0.0

        # Calculate other model errors
        valid['other_predicted_return'] = (valid[model_col] - valid['current_price']) / valid['current_price']
        valid['other_error'] = (valid['actual_return'] - valid['other_predicted_return']).abs()

        nn_mae = valid['absolute_error'].mean()
        other_mae = valid['other_error'].mean()

        # Improvement ratio
        if other_mae > 0:
            improvement = (other_mae - nn_mae) / other_mae
            return improvement

        return 0.0

    def generate_report(self, evaluation: ModelEvaluation) -> str:
        '''Generate human-readable evaluation report.'''

        report = []
        report.append('=' * 80)
        report.append('NEURAL NETWORK MODEL EVALUATION REPORT')
        report.append('=' * 80)
        report.append('')

        # Overall performance
        report.append('OVERALL PERFORMANCE')
        report.append('-' * 80)
        report.append(f'  Mean Absolute Error (MAE):     {evaluation.mae:.4f} ({evaluation.mae*100:.2f}%)')
        report.append(f'  Root Mean Squared Error (RMSE): {evaluation.rmse:.4f}')
        report.append(f'  Mean Absolute % Error (MAPE):   {evaluation.mape:.2f}%')
        report.append(f'  R-squared:                      {evaluation.r_squared:.4f}')
        report.append(f'  Correlation:                    {evaluation.correlation:.4f}')
        report.append('')

        # Confidence metrics
        report.append('CONFIDENCE METRICS')
        report.append('-' * 80)
        report.append(f'  Calibration Score:              {evaluation.calibration_score:.4f}')
        report.append('  Prediction Interval Coverage:')
        for level, coverage in evaluation.prediction_interval_coverage.items():
            report.append(f'    {level*100:.0f}% CI: {coverage*100:.1f}% (expected {level*100:.0f}%)')
        report.append('')

        # Model comparison
        report.append('COMPARISON WITH OTHER MODELS')
        report.append('-' * 80)
        report.append(f'  vs DCF Model:        {evaluation.vs_dcf_improvement:+.2%} improvement')
        report.append(f'  vs Graham Model:     {evaluation.vs_graham_improvement:+.2%} improvement')
        report.append(f'  vs Simple Ratios:    {evaluation.vs_ratios_improvement:+.2%} improvement')
        report.append('')

        # Confidence-based accuracy
        report.append('ACCURACY BY CONFIDENCE LEVEL')
        report.append('-' * 80)
        for conf, metrics in evaluation.confidence_accuracy.items():
            report.append(f'  {conf.upper():8s}: MAE={metrics["mae"]:.4f}, n={metrics["count"]}')
        report.append('')

        # Sector performance
        report.append('SECTOR-WISE PERFORMANCE')
        report.append('-' * 80)
        for sector, perf in sorted(evaluation.sector_performance.items()):
            report.append(
                f'  {sector:25s}: MAE={perf["mae"]:.4f}, '
                f'Corr={perf["correlation"]:.3f}, n={perf["sample_size"]}'
            )
        report.append('')

        # Decade performance
        report.append('PERFORMANCE BY DECADE')
        report.append('-' * 80)
        for decade, perf in sorted(evaluation.decade_performance.items()):
            report.append(
                f'  {decade:8s}: MAE={perf["mae"]:.4f}, '
                f'Corr={perf["correlation"]:.3f}, n={perf["sample_size"]}'
            )
        report.append('')

        # Worst predictions
        report.append('TOP 10 WORST PREDICTIONS (cases to investigate)')
        report.append('-' * 80)
        for i, pred in enumerate(evaluation.large_errors[:10], 1):
            error = (pred.nn_fair_value - pred.current_price) / pred.current_price - pred.actual_return
            report.append(
                f'  {i:2d}. {pred.ticker:6s} {pred.sector:20s} '
                f'{pred.prediction_date.strftime("%Y-%m-%d"):12s} '
                f'Error: {error:+.2%}'
            )
        report.append('')

        # Model disagreements
        report.append('TOP 10 MODEL DISAGREEMENTS (NN differs most from other models)')
        report.append('-' * 80)
        for i, pred in enumerate(evaluation.model_disagreements[:10], 1):
            nn_return = (pred.nn_fair_value - pred.current_price) / pred.current_price
            report.append(
                f'  {i:2d}. {pred.ticker:6s} {pred.sector:20s} '
                f'NN: {nn_return:+.2%}, Actual: {pred.actual_return:+.2%}'
            )
        report.append('')

        report.append('=' * 80)

        return '\n'.join(report)


async def main():
    '''Run comprehensive evaluation.'''

    config = EvaluationConfig()
    evaluator = NeuralNetworkEvaluator(config)

    # Check if model exists
    model_path = Path('models/neural_network_1year.pth')

    if not model_path.exists():
        logger.error(
            f'No trained model found at {model_path}. '
            'Please train the model first using comprehensive_neural_training.py'
        )
        return

    # Load model
    logger.info(f'Loading model from {model_path}')
    model = NeuralNetworkValuationModel(time_horizon='1year', model_path=model_path)

    # Collect predictions on test set
    logger.info('Collecting predictions on test set...')
    test_results = await evaluator.collect_historical_predictions(model, split='test')

    # Calculate metrics
    logger.info('Calculating evaluation metrics...')
    evaluation = evaluator.calculate_metrics(test_results)

    # Generate and save report
    report = evaluator.generate_report(evaluation)
    print(report)

    # Save detailed results
    output_dir = Path('evaluation_results')
    output_dir.mkdir(exist_ok=True)

    report_path = output_dir / 'neural_network_evaluation_report.txt'
    with open(report_path, 'w') as f:
        f.write(report)

    logger.info(f'Report saved to {report_path}')

    # Save JSON results
    json_path = output_dir / 'evaluation_results.json'
    with open(json_path, 'w') as f:
        json.dump({
            'mae': evaluation.mae,
            'rmse': evaluation.rmse,
            'r_squared': evaluation.r_squared,
            'correlation': evaluation.correlation,
            'calibration_score': evaluation.calibration_score,
            'sector_performance': evaluation.sector_performance,
            'decade_performance': evaluation.decade_performance
        }, f, indent=2)

    logger.info(f'JSON results saved to {json_path}')


if __name__ == '__main__':
    asyncio.run(main())
