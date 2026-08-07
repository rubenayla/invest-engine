"""
Multi-timeframe Neural Network Models.

Provides access to neural network models trained for different time horizons,
allowing users to select the appropriate model based on their investment timeline.
"""

import logging
from pathlib import Path
from typing import Dict, Optional

from .base import ValuationResult
from .neural_network_model import NeuralNetworkValuationModel

logger = logging.getLogger(__name__)


class MultiTimeframeNeuralNetworks:
    """Manager for multiple neural network models across different time horizons."""

    AVAILABLE_TIMEFRAMES = {
        '1month': {
            'model_path': 'trained_nn_1month.pt',
            'description': '1-month prediction horizon - captures short-term market movements',
            'months': 1,
            'best_for': 'Trading, short-term opportunities'
        },
        '3month': {
            'model_path': 'trained_nn_3month.pt',
            'description': '3-month prediction horizon - quarterly performance cycles',
            'months': 3,
            'best_for': 'Quarterly trading, earnings cycles'
        },
        '6month': {
            'model_path': 'trained_nn_6month.pt',
            'description': '6-month prediction horizon - medium-term trends',
            'months': 6,
            'best_for': 'Swing trading, sector rotation'
        },
        '1year': {
            'model_path': 'trained_nn_1year.pt',
            'description': '1-year prediction horizon - annual fundamental changes',
            'months': 12,
            'best_for': 'Value investing, fundamental analysis'
        },
        '18month': {
            'model_path': 'trained_nn_18month.pt',
            'description': '18-month prediction horizon - business cycle effects',
            'months': 18,
            'best_for': 'Economic cycle investing'
        },
        '2year': {
            'model_path': 'trained_nn_2year.pt',
            'description': '2-year prediction horizon - longer-term value realization',
            'months': 24,
            'best_for': 'Long-term value investing, BEST CORRELATION (0.518)'
        },
        '3year': {
            'model_path': 'trained_nn_3year.pt',
            'description': '3-year prediction horizon - structural business changes',
            'months': 36,
            'best_for': 'Buy-and-hold investing'
        }
    }

    def __init__(self, models_directory: Path = None):
        """
        Initialize multi-timeframe neural networks.

        Parameters
        ----------
        models_directory : Path, optional
            Directory containing trained model files
        """
        self.models_directory = models_directory or Path.cwd()
        self._loaded_models = {}

    def get_available_timeframes(self) -> Dict[str, Dict]:
        """Get information about available timeframes."""
        available = {}

        for timeframe, info in self.AVAILABLE_TIMEFRAMES.items():
            model_path = self.models_directory / info['model_path']

            available[timeframe] = {
                **info,
                'available': model_path.exists(),
                'full_path': str(model_path)
            }

        return available

    def get_model(self, timeframe: str) -> Optional[NeuralNetworkValuationModel]:
        """
        Get neural network model for specific timeframe.

        Parameters
        ----------
        timeframe : str
            Timeframe identifier ('1month', '1year', etc.)

        Returns
        -------
        Optional[NeuralNetworkValuationModel]
            Loaded model or None if not available
        """
        if timeframe not in self.AVAILABLE_TIMEFRAMES:
            logger.error(f'Unknown timeframe: {timeframe}. Available: {list(self.AVAILABLE_TIMEFRAMES.keys())}')
            return None

        # Use cached model if already loaded
        if timeframe in self._loaded_models:
            return self._loaded_models[timeframe]

        # Load model from disk
        model_path = self.models_directory / self.AVAILABLE_TIMEFRAMES[timeframe]['model_path']

        if not model_path.exists():
            logger.warning(f'Model file not found: {model_path}')
            return None

        try:
            model = NeuralNetworkValuationModel(
                time_horizon=timeframe,
                model_path=model_path
            )
            self._loaded_models[timeframe] = model
            logger.info(f'Loaded {timeframe} neural network model')
            return model

        except Exception as e:
            logger.error(f'Failed to load {timeframe} model: {e}')
            return None

    def value_company_all_timeframes(self, ticker: str) -> Dict[str, Optional[ValuationResult]]:
        """
        Value a company using all available timeframe models.

        Parameters
        ----------
        ticker : str
            Stock ticker symbol

        Returns
        -------
        Dict[str, Optional[ValuationResult]]
            Results for each timeframe
        """
        results = {}

        for timeframe in self.AVAILABLE_TIMEFRAMES.keys():
            model = self.get_model(timeframe)

            if model:
                try:
                    result = model.value_company(ticker, verbose=False)
                    results[timeframe] = result
                except Exception as e:
                    logger.warning(f'Valuation failed for {ticker} {timeframe}: {e}')
                    results[timeframe] = None
            else:
                results[timeframe] = None

        return results

    def get_consensus_valuation(self, ticker: str,
                               weights: Dict[str, float] = None) -> Optional[ValuationResult]:
        """
        Get consensus valuation across multiple timeframes.

        Parameters
        ----------
        ticker : str
            Stock ticker symbol
        weights : Dict[str, float], optional
            Weights for each timeframe. If None, uses correlation-based weighting.

        Returns
        -------
        Optional[ValuationResult]
            Consensus valuation result
        """
        results = self.value_company_all_timeframes(ticker)

        # Filter valid results
        valid_results = {tf: result for tf, result in results.items()
                        if result and result.fair_value}

        if not valid_results:
            return None

        # Use correlation-based weights if not provided
        if weights is None:
            weights = self._get_correlation_weights()

        # Extract current_price from first valid result
        current_price = None
        for result in valid_results.values():
            if result.current_price:
                current_price = result.current_price
                break

        if not current_price:
            return None

        # Use unified log-return consensus with correlation weights as confidence
        from .consensus import ModelInput, compute_consensus

        model_inputs = []
        for tf, result in valid_results.items():
            corr_weight = weights.get(tf, 0)
            if corr_weight > 0:
                model_inputs.append(ModelInput(
                    model_name=f'neural_network_{tf}',
                    fair_value=result.fair_value,
                    confidence=corr_weight,  # correlation weight acts as confidence
                ))

        if not model_inputs:
            return None

        consensus = compute_consensus(model_inputs, current_price)
        if consensus is None:
            return None

        # Create consensus result (margin_of_safety as percentage for NN convention)
        consensus_result = ValuationResult(
            ticker=ticker,
            model='neural_network_consensus',
            fair_value=consensus.fair_value,
            current_price=current_price,
            margin_of_safety=consensus.margin_of_safety * 100,
            inputs={
                'timeframes_used': list(valid_results.keys()),
                'weights': {tf: weights.get(tf, 0) for tf in valid_results.keys()},
                'individual_fair_values': {tf: result.fair_value for tf, result in valid_results.items()}
            },
            outputs={
                'consensus_method': 'log_return_weighted',
                'timeframes_count': len(valid_results),
                'consensus_model_weights': consensus.model_weights,
            }
        )

        return consensus_result

    def _get_correlation_weights(self) -> Dict[str, float]:
        """Get weights based on historical correlation performance."""
        # Based on multi-timeframe analysis results
        correlation_weights = {
            '1month': 0.05,   # Correlation: 0.050
            '3month': 0.25,   # Correlation: 0.250
            '6month': 0.16,   # Correlation: 0.157
            '1year': 0.01,    # Correlation: 0.011
            '18month': 0.0,   # Correlation: -0.061 (negative)
            '2year': 0.52,    # Correlation: 0.518 (best)
            '3year': 0.33     # Correlation: 0.328
        }

        # Normalize weights
        total = sum(correlation_weights.values())
        return {tf: weight / total for tf, weight in correlation_weights.items()}

    def get_performance_summary(self) -> Dict[str, Dict]:
        """Get performance summary for all timeframes."""
        # Performance data from multi-timeframe analysis
        performance_data = {
            '1month': {'correlation': 0.050, 'hit_rate': 0.75, 'mae': 0.011, 'val_mae': 1.912},
            '3month': {'correlation': 0.250, 'hit_rate': 0.50, 'mae': 0.092, 'val_mae': 5.972},
            '6month': {'correlation': 0.157, 'hit_rate': 0.00, 'mae': 0.438, 'val_mae': 14.577},
            '1year': {'correlation': 0.011, 'hit_rate': 1.00, 'mae': 0.145, 'val_mae': 20.076},
            '18month': {'correlation': -0.061, 'hit_rate': 0.75, 'mae': 0.521, 'val_mae': 28.642},
            '2year': {'correlation': 0.518, 'hit_rate': 1.00, 'mae': 0.873, 'val_mae': 26.243},
            '3year': {'correlation': 0.328, 'hit_rate': 1.00, 'mae': 3.693, 'val_mae': 22.002}
        }

        summary = {}
        for timeframe, info in self.AVAILABLE_TIMEFRAMES.items():
            perf = performance_data.get(timeframe, {})

            summary[timeframe] = {
                **info,
                **perf,
                'rank_by_correlation': self._rank_by_metric(performance_data, 'correlation', timeframe),
                'recommended': timeframe == '2year'  # Best correlation
            }

        return summary

    def _rank_by_metric(self, data: Dict, metric: str, timeframe: str) -> int:
        """Rank timeframe by specific metric."""
        values = [(tf, d.get(metric, 0)) for tf, d in data.items()]
        values.sort(key=lambda x: x[1], reverse=True)

        for i, (tf, _) in enumerate(values):
            if tf == timeframe:
                return i + 1
        return len(values)


# Convenience functions for easy access
def get_best_timeframe_model() -> Optional[NeuralNetworkValuationModel]:
    """Get the best performing neural network model (2-year horizon)."""
    manager = MultiTimeframeNeuralNetworks()
    return manager.get_model('2year')


def value_with_best_model(ticker: str) -> Optional[ValuationResult]:
    """Value stock with best performing neural network model."""
    model = get_best_timeframe_model()
    if model:
        return model.value_company(ticker)
    return None


def get_consensus_prediction(ticker: str) -> Optional[ValuationResult]:
    """Get consensus prediction across all timeframes."""
    manager = MultiTimeframeNeuralNetworks()
    return manager.get_consensus_valuation(ticker)
