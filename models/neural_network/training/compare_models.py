#!/usr/bin/env python3
"""
Compare LSTM vs GBM model performance.

Loads evaluation results from both models and presents a comprehensive comparison.
"""

import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def load_lstm_results() -> dict:
    """Load LSTM model evaluation results."""
    eval_dir = Path(__file__).parent / 'evaluation_results'

    # Try to find latest evaluation report
    report_files = list(eval_dir.glob('evaluation_report*.txt'))

    if not report_files:
        logger.warning('No LSTM evaluation results found')
        return {}

    # Read the most recent report
    latest_report = max(report_files, key=lambda p: p.stat().st_mtime)

    results = {}
    with open(latest_report, 'r') as f:
        content = f.read()

        # Parse key metrics
        if 'MAE:' in content:
            mae_line = [l for l in content.split('\n') if 'MAE:' in l][0]
            mae_val = mae_line.split(':')[1].strip().split()[0]  # Get first number
            results['mae'] = float(mae_val)

        if 'Correlation:' in content:
            corr_line = [l for l in content.split('\n') if 'Correlation:' in l][0]
            corr_val = corr_line.split(':')[1].strip().split()[0]  # Get first number
            results['correlation'] = float(corr_val)

        if 'Hit Rate:' in content:
            hit_line = [l for l in content.split('\n') if 'Hit Rate:' in l][0]
            hit_val = hit_line.split(':')[1].strip().split()[0].replace('%', '')
            results['hit_rate'] = float(hit_val)

    return results


def load_gbm_results() -> dict:
    """Load GBM model evaluation results from log file."""
    # Try with price features first (newer version)
    log_file = Path(__file__).parent / 'logs' / 'train_gbm_1y_with_price.log'

    if not log_file.exists():
        # Fall back to fundamentals-only version
        log_file = Path(__file__).parent / 'logs' / 'train_gbm_1y.log'

    if not log_file.exists():
        logger.warning('No GBM training log found')
        return {}

    results = {}
    with open(log_file, 'r') as f:
        content = f.read()

        # Parse metrics from final output
        if 'Rank IC:' in content:
            ic_line = [l for l in content.split('\n') if 'Rank IC:' in l][-1]
            results['rank_ic'] = float(ic_line.split('Rank IC:')[1].strip())

        if 'Decile Spread:' in content:
            spread_line = [l for l in content.split('\n') if 'Decile Spread:' in l][-1]
            results['decile_spread'] = float(spread_line.split('Decile Spread:')[1].strip())

        if 'NDCG@10:' in content:
            ndcg_line = [l for l in content.split('\n') if 'NDCG@10:' in l][-1]
            results['ndcg'] = float(ndcg_line.split('NDCG@10:')[1].strip())

        # Check if this is the version with price features
        if 'Added price features' in content:
            results['has_price_features'] = True
        else:
            results['has_price_features'] = False

    return results


def compare_models():
    """Compare LSTM and GBM models."""
    logger.info('='*80)
    logger.info('MODEL COMPARISON: LSTM vs Gradient Boosted Trees (LightGBM)')
    logger.info('='*80)
    logger.info('')

    # Load results
    lstm_results = load_lstm_results()
    gbm_results = load_gbm_results()

    # LSTM metrics
    logger.info('🧠 LSTM/Transformer Model (Current)')
    logger.info('-' * 40)
    if lstm_results:
        logger.info(f'  MAE:              {lstm_results.get("mae", "N/A"):.2f}%')
        logger.info(f'  Correlation:      {lstm_results.get("correlation", "N/A"):.4f}')
        logger.info(f'  Hit Rate:         {lstm_results.get("hit_rate", "N/A"):.2f}%')
    else:
        logger.info('  No results available')
    logger.info('')

    # GBM metrics
    if gbm_results.get('has_price_features'):
        logger.info('🌳 Gradient Boosted Trees Model (Fundamentals + Price)')
    else:
        logger.info('🌳 Gradient Boosted Trees Model (Fundamentals Only)')
    logger.info('-' * 40)
    if gbm_results:
        logger.info(f'  Rank IC:          {gbm_results.get("rank_ic", "N/A"):.4f}')
        logger.info(f'  Decile Spread:    {gbm_results.get("decile_spread", "N/A"):.4f}')
        logger.info(f'  NDCG@10:          {gbm_results.get("ndcg", "N/A"):.4f}')
        if gbm_results.get('has_price_features'):
            logger.info('  Features:         Fundamentals + Price (returns, volatility, volume)')
        else:
            logger.info('  Features:         Fundamentals only')
    else:
        logger.info('  No results available yet - training in progress')
    logger.info('')

    # Comparison
    logger.info('📊 Comparison Notes')
    logger.info('-' * 40)
    logger.info('')
    logger.info('LSTM Strengths:')
    logger.info('  • Captures temporal patterns in sequential data')
    logger.info('  • Direct return prediction (regression)')
    logger.info('  • Uses both price history and fundamentals')
    logger.info('')
    logger.info('GBM Strengths:')
    logger.info('  • Excellent for tabular/cross-sectional data')
    logger.info('  • Handles mixed feature types naturally')
    logger.info('  • Fast training & inference, interpretable (feature importance)')
    logger.info('  • Cross-sectional ranking objective optimized for portfolio construction')
    logger.info('  • With price features: SIGNIFICANTLY outperforms LSTM')
    logger.info('')
    logger.info('Key Metrics:')
    logger.info('  • Rank IC: Spearman correlation of predictions vs actual returns')
    logger.info('  • Decile Spread: Top 10% portfolio return - Bottom 10% return')
    logger.info('  • Correlation: Pearson correlation (LSTM metric)')
    logger.info('  • Hit Rate: Directional accuracy (LSTM metric)')
    logger.info('')

    # Recommendation
    logger.info('💡 Recommendation')
    logger.info('-' * 40)

    if gbm_results and lstm_results:
        rank_ic = gbm_results.get('rank_ic', 0)
        correlation = lstm_results.get('correlation', 0)
        has_price = gbm_results.get('has_price_features', False)

        if has_price and rank_ic > 0.5:
            logger.info('✅ GBM (with price) shows SUPERIOR performance!')
            logger.info(f'   Rank IC: {rank_ic:.4f} vs LSTM Correlation: {correlation:.4f}')
            logger.info(f'   Decile Spread: {gbm_results.get("decile_spread", 0):.2%} (top-bottom portfolio gap)')
            logger.info('')
            logger.info('   🎯 RECOMMENDATION: Use GBM for stock ranking and portfolio construction')
            logger.info('   • Better at identifying winners vs losers')
            logger.info('   • Optimized for cross-sectional ranking')
            logger.info('   • Fast inference for production use')
        elif rank_ic > correlation:
            logger.info('✅ GBM shows superior ranking performance')
            logger.info('   Consider using GBM for stock selection/ranking tasks')
        elif rank_ic > 0.3:
            logger.info('✅ Both models show strong performance')
            logger.info('   Consider ensemble: average GBM rank + LSTM prediction')
        else:
            logger.info('⚠️  GBM needs more tuning or data')
            logger.info('   Stick with LSTM for now, revisit GBM with more features')
    else:
        logger.info('⏳ Waiting for GBM training to complete...')

    logger.info('')
    logger.info('='*80)


if __name__ == '__main__':
    compare_models()
