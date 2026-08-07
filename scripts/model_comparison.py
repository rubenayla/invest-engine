#!/usr/bin/env python3
"""
Compare neural network model against existing DCF models.

Tests prediction accuracy and portfolio performance across different models.
"""

import sys
import warnings
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.invest.valuation.model_registry import ModelRegistry
from src.invest.valuation.neural_network_model import NeuralNetworkValuationModel

# Suppress warnings for cleaner output
warnings.filterwarnings('ignore')


def get_test_stocks() -> List[str]:
    """Get a diverse set of test stocks."""
    return [
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA',  # Tech
        'JPM', 'BAC', 'WFC', 'GS', 'C',           # Finance
        'JNJ', 'PFE', 'ABBV', 'MRK', 'UNH',      # Healthcare
        'XOM', 'CVX', 'COP', 'EOG', 'SLB',       # Energy
        'WMT', 'HD', 'PG', 'KO', 'PEP'           # Consumer
    ]


def calculate_actual_return(ticker: str, months_back: int = 12) -> float:
    """Calculate the actual return over the past N months."""
    try:
        from datetime import timedelta

        import yfinance as yf

        end_date = datetime.now()
        start_date = end_date - timedelta(days=months_back * 30)

        stock = yf.Ticker(ticker)
        hist = stock.history(start=start_date, end=end_date)

        if len(hist) < 30:
            return None

        # Use 30-day averages like in training
        start_prices = hist['Close'].iloc[:30]
        end_prices = hist['Close'].iloc[-30:]

        if len(start_prices) < 10 or len(end_prices) < 10:
            return None

        start_price = start_prices.mean()
        end_price = end_prices.mean()

        return (end_price - start_price) / start_price

    except Exception as e:
        print(f'Error calculating return for {ticker}: {e}')
        return None


def evaluate_model_predictions(model_name: str, model, test_stocks: List[str]) -> Dict[str, float]:
    """Evaluate a model's prediction accuracy."""
    predictions = []
    actuals = []
    successful_predictions = 0

    print(f'\nEvaluating {model_name}...')

    for ticker in test_stocks:
        try:
            # Get actual return
            actual_return = calculate_actual_return(ticker, months_back=12)
            if actual_return is None:
                continue

            # Get model prediction
            result = model.value_company(ticker, verbose=False)

            if not result or not result.fair_value or not result.current_price:
                continue

            # Convert to predicted return
            predicted_return = (result.fair_value - result.current_price) / result.current_price

            predictions.append(predicted_return)
            actuals.append(actual_return)
            successful_predictions += 1

            print(f'  {ticker:5}: Predicted {predicted_return:+.1%}, Actual {actual_return:+.1%}')

        except Exception as e:
            print(f'  {ticker:5}: Error - {e}')
            continue

    if len(predictions) < 5:
        print(f'  Insufficient predictions for {model_name}')
        return {}

    # Calculate metrics
    predictions = np.array(predictions)
    actuals = np.array(actuals)

    mae = np.mean(np.abs(predictions - actuals))
    rmse = np.sqrt(np.mean((predictions - actuals) ** 2))
    correlation = np.corrcoef(predictions, actuals)[0, 1]

    # Hit rate (directional accuracy)
    correct_direction = np.sum(np.sign(predictions) == np.sign(actuals))
    hit_rate = correct_direction / len(predictions)

    # Mean predicted vs actual returns
    mean_predicted = np.mean(predictions)
    mean_actual = np.mean(actuals)

    metrics = {
        'successful_predictions': successful_predictions,
        'mae': mae,
        'rmse': rmse,
        'correlation': correlation,
        'hit_rate': hit_rate,
        'mean_predicted_return': mean_predicted,
        'mean_actual_return': mean_actual,
        'prediction_bias': mean_predicted - mean_actual
    }

    print(f'  Results: MAE={mae:.3f}, Correlation={correlation:.3f}, Hit Rate={hit_rate:.1%}')

    return metrics


def simulate_portfolio_performance(model_name: str, model, test_stocks: List[str]) -> Dict[str, float]:
    """Simulate portfolio performance using model predictions."""
    print(f'\nSimulating portfolio for {model_name}...')

    stock_predictions = []

    for ticker in test_stocks:
        try:
            result = model.value_company(ticker, verbose=False)

            if not result or not result.fair_value or not result.current_price:
                continue

            margin_of_safety = result.margin_of_safety
            predicted_return = (result.fair_value - result.current_price) / result.current_price
            actual_return = calculate_actual_return(ticker, months_back=12)

            if actual_return is None:
                continue

            stock_predictions.append({
                'ticker': ticker,
                'predicted_return': predicted_return,
                'actual_return': actual_return,
                'margin_of_safety': margin_of_safety
            })

        except Exception:
            continue

    if len(stock_predictions) < 10:
        print('  Insufficient data for portfolio simulation')
        return {}

    # Create portfolio strategies
    df = pd.DataFrame(stock_predictions)

    # Strategy 1: Top 10 by predicted return
    top10_predicted = df.nlargest(10, 'predicted_return')['actual_return']

    # Strategy 2: Top 10 by margin of safety
    top10_mos = df.nlargest(10, 'margin_of_safety')['actual_return']

    # Strategy 3: Equal weight all stocks
    equal_weight = df['actual_return']

    # Calculate portfolio metrics
    strategies = {
        'top10_predicted': top10_predicted,
        'top10_margin_of_safety': top10_mos,
        'equal_weight': equal_weight
    }

    portfolio_metrics = {}

    for strategy_name, returns in strategies.items():
        if len(returns) == 0:
            continue

        portfolio_return = returns.mean()
        portfolio_volatility = returns.std()
        sharpe_ratio = portfolio_return / portfolio_volatility if portfolio_volatility > 0 else 0

        portfolio_metrics[f'{strategy_name}_return'] = portfolio_return
        portfolio_metrics[f'{strategy_name}_volatility'] = portfolio_volatility
        portfolio_metrics[f'{strategy_name}_sharpe'] = sharpe_ratio

    print(f'  Portfolio returns: Top10={portfolio_metrics.get("top10_predicted_return", 0):.1%}, '
          f'EqualWeight={portfolio_metrics.get("equal_weight_return", 0):.1%}')

    return portfolio_metrics


def run_comparison():
    """Run comprehensive model comparison."""
    print('Neural Network vs Traditional Models Comparison')
    print('=' * 60)

    # Get test stocks
    test_stocks = get_test_stocks()
    print(f'Testing on {len(test_stocks)} stocks across sectors')

    # Initialize models
    registry = ModelRegistry()

    models_to_test = {
        'neural_network': None,  # Will load trained model
        'dcf': registry.get_model('dcf'),
        'simple_ratios': registry.get_model('simple_ratios'),
        'ensemble': registry.get_model('ensemble')
    }

    # Load trained neural network if available
    trained_nn_path = Path('models/neural_network/models/trained_nn_2year.pt')
    if trained_nn_path.exists():
        models_to_test['neural_network'] = NeuralNetworkValuationModel(model_path=trained_nn_path)
        print('✓ Using trained neural network model')
    else:
        # Try registry (which now auto-resolves paths)
        try:
            models_to_test['neural_network'] = registry.get_model('neural_network')
            print('✓ Using neural network model (auto-resolved)')
        except Exception:
            print('⚠ Neural network model could not be loaded (requires training)')
            del models_to_test['neural_network']

    # Run evaluations
    all_results = {}

    print('\n' + '=' * 60)
    print('PREDICTION ACCURACY EVALUATION')
    print('=' * 60)

    for model_name, model in models_to_test.items():
        if model is None:
            continue

        try:
            prediction_metrics = evaluate_model_predictions(model_name, model, test_stocks)
            portfolio_metrics = simulate_portfolio_performance(model_name, model, test_stocks)

            all_results[model_name] = {
                **prediction_metrics,
                **portfolio_metrics
            }

        except Exception as e:
            print(f'Error evaluating {model_name}: {e}')
            continue

    # Summary comparison
    print('\n' + '=' * 60)
    print('SUMMARY COMPARISON')
    print('=' * 60)

    if not all_results:
        print('No successful model evaluations')
        return

    # Create comparison table
    pd.DataFrame(all_results).T

    print('\nPrediction Accuracy:')
    print(f'{"Model":<15} {"MAE":<8} {"Correlation":<12} {"Hit Rate":<10} {"Predictions":<12}')
    print('-' * 60)

    for model_name in all_results:
        metrics = all_results[model_name]
        mae = metrics.get('mae', 0)
        corr = metrics.get('correlation', 0)
        hit_rate = metrics.get('hit_rate', 0)
        count = metrics.get('successful_predictions', 0)

        print(f'{model_name:<15} {mae:<8.3f} {corr:<12.3f} {hit_rate:<10.1%} {count:<12}')

    print('\nPortfolio Performance (Top 10 Strategy):')
    print(f'{"Model":<15} {"Return":<10} {"Volatility":<12} {"Sharpe":<8}')
    print('-' * 50)

    for model_name in all_results:
        metrics = all_results[model_name]
        ret = metrics.get('top10_predicted_return', 0)
        vol = metrics.get('top10_predicted_volatility', 0)
        sharpe = metrics.get('top10_predicted_sharpe', 0)

        print(f'{model_name:<15} {ret:<10.1%} {vol:<12.1%} {sharpe:<8.2f}')

    # Save detailed results
    results_path = Path('model_comparison_results.json')
    import json
    with open(results_path, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)

    print(f'\nDetailed results saved to {results_path}')

    # Determine winner
    print('\n' + '=' * 60)
    print('CONCLUSION')
    print('=' * 60)

    if 'neural_network' in all_results and 'dcf' in all_results:
        nn_mae = all_results['neural_network'].get('mae', float('inf'))
        dcf_mae = all_results['dcf'].get('mae', float('inf'))

        nn_corr = all_results['neural_network'].get('correlation', 0)
        dcf_corr = all_results['dcf'].get('correlation', 0)

        print('Neural Network vs DCF:')
        print(f'  MAE: {nn_mae:.3f} vs {dcf_mae:.3f} {"(NN wins)" if nn_mae < dcf_mae else "(DCF wins)"}')
        print(f'  Correlation: {nn_corr:.3f} vs {dcf_corr:.3f} {"(NN wins)" if nn_corr > dcf_corr else "(DCF wins)"}')

        if nn_mae < dcf_mae and nn_corr > dcf_corr:
            print('\n🎉 Neural Network outperforms DCF on both metrics!')
        elif nn_mae > dcf_mae and nn_corr < dcf_corr:
            print('\n📈 DCF model outperforms Neural Network on both metrics.')
        else:
            print('\n🤝 Mixed results - both models have strengths.')


def main():
    """Main comparison pipeline."""
    run_comparison()


if __name__ == '__main__':
    main()
