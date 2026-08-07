#!/usr/bin/env python3
"""
Compare model performance with and without macro features.
"""

import json
import logging
from pathlib import Path

import numpy as np

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def analyze_cache(cache_path):
    """Analyze cache statistics."""
    with open(cache_path, 'r') as f:
        cache = json.load(f)

    samples = cache['samples']

    # Check for macro data
    has_macro = False
    macro_features = set()

    if samples and 'macro' in samples[0]['data'] and samples[0]['data']['macro']:
        has_macro = True
        macro_features = set(samples[0]['data']['macro'].keys())

    # Analyze return statistics
    returns_stats = {}
    for horizon in ['1m', '3m', '6m', '1y', '2y']:
        returns = [s['forward_returns'][horizon] * 100 for s in samples]
        returns_stats[horizon] = {
            'mean': np.mean(returns),
            'std': np.std(returns),
            'min': np.min(returns),
            'max': np.max(returns)
        }

    return {
        'sample_count': len(samples),
        'has_macro': has_macro,
        'macro_features': list(macro_features),
        'returns_stats': returns_stats
    }

def compare_training_logs(log_files):
    """Compare training results from log files."""
    results = {}

    for name, log_file in log_files.items():
        if not Path(log_file).exists():
            logger.warning(f'{log_file} not found')
            continue

        with open(log_file, 'r') as f:
            lines = f.readlines()

        # Extract test results
        test_results = {}
        for line in lines:
            if 'MAE=' in line and 'RMSE=' in line and 'Corr=' in line:
                # Parse line like: "1m : MAE=6.02%, RMSE=8.19%, Corr=-0.051"
                parts = line.split(':')
                if len(parts) >= 2:
                    horizon = parts[0].strip().split()[-1]
                    metrics = parts[1].strip()

                    # Extract metrics
                    mae = float(metrics.split('MAE=')[1].split('%')[0])
                    rmse = float(metrics.split('RMSE=')[1].split('%')[0])
                    corr = float(metrics.split('Corr=')[1].strip())

                    test_results[horizon] = {
                        'mae': mae,
                        'rmse': rmse,
                        'corr': corr
                    }

        # Extract feature count
        feature_count = None
        for line in lines:
            if 'Feature dimension:' in line:
                feature_count = int(line.split('Feature dimension:')[1].strip())
                break

        results[name] = {
            'feature_count': feature_count,
            'test_results': test_results
        }

    return results

def main():
    logger.info('='*60)
    logger.info('Comparing Model Performance: With vs Without Macro Features')
    logger.info('='*60)

    # Analyze caches
    logger.info('\n📊 Cache Analysis:')
    logger.info('-'*40)

    # Current cache (with macro)
    if Path('training_data_cache_multi_horizon.json').exists():
        current_cache = analyze_cache('training_data_cache_multi_horizon.json')
        logger.info('Current cache:')
        logger.info(f'  Samples: {current_cache["sample_count"]}')
        logger.info(f'  Has macro: {current_cache["has_macro"]}')
        if current_cache['has_macro']:
            logger.info(f'  Macro features: {current_cache["macro_features"]}')

    # Compare training results
    logger.info('\n📈 Training Results Comparison:')
    logger.info('-'*40)

    log_files = {
        'Without Macro (previous)': 'training_no_placeholders.log',
        'With Time Series Features': 'training_with_ts_features.log',
        'With Real Macro': 'training_with_real_macro.log'
    }

    results = compare_training_logs(log_files)

    # Display comparison table
    if results:
        horizons = ['1m', '3m', '6m', '1y', '2y']

        for horizon in horizons:
            logger.info(f'\n{horizon} Horizon:')
            logger.info('  Model                    | Features | MAE     | RMSE    | Corr')
            logger.info('  -------------------------|----------|---------|---------|-------')

            for name, data in results.items():
                if horizon in data.get('test_results', {}):
                    metrics = data['test_results'][horizon]
                    logger.info(f'  {name:24s} | {data.get("feature_count", "?"):^8} | '
                               f'{metrics["mae"]:6.2f}% | {metrics["rmse"]:6.2f}% | '
                               f'{metrics["corr"]:+.3f}')

        # Calculate improvements
        logger.info('\n🎯 Performance Summary:')
        logger.info('-'*40)

        if 'Without Macro (previous)' in results and 'With Real Macro' in results:
            base = results['Without Macro (previous)']['test_results']
            improved = results['With Real Macro']['test_results']

            improvements = []
            for horizon in horizons:
                if horizon in base and horizon in improved:
                    # Lower MAE/RMSE is better, higher correlation is better
                    mae_improvement = (base[horizon]['mae'] - improved[horizon]['mae']) / base[horizon]['mae'] * 100
                    rmse_improvement = (base[horizon]['rmse'] - improved[horizon]['rmse']) / base[horizon]['rmse'] * 100
                    corr_improvement = improved[horizon]['corr'] - base[horizon]['corr']

                    improvements.append({
                        'horizon': horizon,
                        'mae_imp': mae_improvement,
                        'rmse_imp': rmse_improvement,
                        'corr_imp': corr_improvement
                    })

            if improvements:
                logger.info('Improvements (With Macro vs Without):')
                for imp in improvements:
                    logger.info(f'  {imp["horizon"]:3s}: MAE {imp["mae_imp"]:+.1f}%, '
                               f'RMSE {imp["rmse_imp"]:+.1f}%, '
                               f'Corr {imp["corr_imp"]:+.3f}')

                avg_mae_imp = np.mean([imp['mae_imp'] for imp in improvements])
                avg_rmse_imp = np.mean([imp['rmse_imp'] for imp in improvements])
                avg_corr_imp = np.mean([imp['corr_imp'] for imp in improvements])

                logger.info(f'\n  Average: MAE {avg_mae_imp:+.1f}%, '
                           f'RMSE {avg_rmse_imp:+.1f}%, '
                           f'Corr {avg_corr_imp:+.3f}')

if __name__ == '__main__':
    main()
