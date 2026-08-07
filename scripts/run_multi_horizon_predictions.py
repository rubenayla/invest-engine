#!/usr/bin/env python3
"""
Run multi-horizon neural network predictions on all stocks in dashboard_data.json.

The model predicts forward **excess returns** vs SPY. Fair values are derived
by adding assumed market returns per horizon to the predicted excess return.
"""

import json
import sys
from pathlib import Path

import numpy as np
import torch
from sklearn.preprocessing import RobustScaler

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / 'src'))

from invest.valuation.multi_horizon_nn import MultiHorizonValuationModel
from invest.valuation.db_utils import get_db_connection, save_nn_prediction
from invest.valuation.neural_network_model import FeatureEngineer

# Long-run market return assumptions per horizon (~10% annualised)
MARKET_RETURN = {
    '1m': 0.008,   # 0.8%
    '3m': 0.025,   # 2.5%
    '6m': 0.05,    # 5%
    '1y': 0.10,    # 10%
    '2y': 0.21,    # 21%
}


def _build_scaler(checkpoint: dict) -> RobustScaler:
    """Reconstruct a fitted RobustScaler from checkpoint data."""
    scaler = RobustScaler()
    state = checkpoint['scaler_state']
    scaler.center_ = np.array(state['center_'])
    scaler.scale_ = np.array(state['scale_'])
    # RobustScaler also needs n_features_in_ for validation
    scaler.n_features_in_ = len(state['center_'])
    return scaler


def load_stock_cache(ticker: str, stock_cache_dir: Path) -> dict:
    """Load stock data from SQLite database (or fallback to JSON cache)."""
    # Try SQLite first
    try:
        from invest.data.stock_data_reader import StockDataReader

        reader = StockDataReader()
        stock_data = reader.get_stock_data(ticker)

        if stock_data:
            # Transform to format expected by FeatureEngineer
            return {
                'info': stock_data.get('info', {}),
                'financials': stock_data.get('financials', {}),
                'history': stock_data.get('price_data', {}),
                'cashflow': stock_data.get('cashflow', []),
                'balance_sheet': stock_data.get('balance_sheet', []),
                'income': stock_data.get('income', []),
            }
    except Exception:
        pass  # Silently fall back to JSON

    # Fallback to JSON cache
    cache_file = stock_cache_dir / f'{ticker}.json'
    if not cache_file.exists():
        return None

    with open(cache_file) as f:
        cache_data = json.load(f)

    stock_data = {
        'info': cache_data.get('info', {}),
        'financials': cache_data.get('financials', {}),
        'history': cache_data.get('price_data', {}),
    }

    return stock_data


def main():
    """Run predictions on all stocks in the dashboard."""

    print('Running Multi-Horizon NN predictions on dashboard stocks')
    print('=' * 60)

    # Load dashboard data
    dashboard_data_path = project_root / 'dashboard' / 'dashboard_data.json'
    print(f'\nLoading dashboard data: {dashboard_data_path}')

    with open(dashboard_data_path) as f:
        data = json.load(f)

    stocks = data.get('stocks', {})
    print(f'   Found {len(stocks)} stocks')

    # Stock cache directory
    stock_cache_dir = project_root / 'data' / 'stock_cache'

    # Load model
    model_path = project_root / 'neural_network' / 'models' / 'multi_horizon_model.pt'
    if not model_path.exists():
        raise FileNotFoundError(
            'Multi-horizon model not found. Expected: '
            f'{model_path}'
        )
    print(f'\nLoading model from: {model_path}')

    checkpoint = torch.load(model_path, map_location='cpu', weights_only=False)
    feature_dim = checkpoint['feature_dim']
    feature_names = checkpoint['feature_names']
    is_excess = checkpoint.get('target_type') == 'excess_return'

    # Rebuild fitted scaler from checkpoint
    if 'scaler_state' in checkpoint:
        scaler = _build_scaler(checkpoint)
        print('   Loaded scaler from checkpoint')
    else:
        scaler = None
        print('   WARNING: No scaler in checkpoint — features will be unscaled')

    # Initialize model and load weights
    model = MultiHorizonValuationModel(feature_dim=feature_dim)
    model.model.load_state_dict(checkpoint['model_state_dict'])
    model.model.eval()

    print(f'   Model loaded (feature_dim={feature_dim}, excess_return={is_excess})')

    # Initialize feature engineer (for feature extraction only; scaling done via checkpoint scaler)
    feature_engineer = FeatureEngineer()

    # Connect to database
    print('\nConnecting to database...')
    db_conn = get_db_connection()

    # Run predictions on each stock
    print('\nRunning predictions...')
    success_count = 0
    error_count = 0
    cache_miss_count = 0
    db_save_count = 0

    for i, (ticker, stock) in enumerate(stocks.items()):
        try:
            # Load stock data from cache
            stock_data = load_stock_cache(ticker, stock_cache_dir)

            if not stock_data:
                cache_miss_count += 1
                if 'valuations' not in stock:
                    stock['valuations'] = {}
                stock['valuations']['multi_horizon_nn'] = {
                    'error': 'Stock cache file not found',
                    'suitable': False
                }
                continue

            # Get current price
            current_price = stock_data['info'].get('currentPrice')
            if not current_price:
                current_price = stock_data['info'].get('regularMarketPrice', 100.0)

            # Extract features using FeatureEngineer
            features = feature_engineer.extract_features(stock_data)

            # Convert features dict to numpy array in correct order
            feature_array = np.array([features.get(name, 0.0) for name in feature_names])
            feature_array = np.nan_to_num(feature_array, nan=0.0, posinf=100.0, neginf=-100.0)

            # Apply scaler if available
            if scaler is not None:
                feature_array = scaler.transform(feature_array.reshape(1, -1)).squeeze()

            # Run prediction (raw model forward pass)
            with torch.no_grad():
                x_tensor = torch.FloatTensor(feature_array.reshape(1, -1)).to(model.device)
                raw_preds = model.model(x_tensor)

            # Build prediction results
            predictions = {}  # horizon -> predicted % return
            fair_values = {}  # horizon -> fair value price
            confidence_scores = {}

            for horizon in model.model.horizons:
                pred_pct = float(raw_preds[horizon].cpu().numpy().squeeze())
                predictions[horizon] = pred_pct

                if is_excess:
                    # pred_pct is excess return in %; convert to total return
                    total_return = (pred_pct / 100.0) + MARKET_RETURN.get(horizon, 0.10)
                else:
                    total_return = pred_pct / 100.0

                fair_values[horizon] = current_price * (1 + total_return)

                # Simple confidence: inverse of abs prediction (less extreme = more confident)
                confidence_scores[horizon] = max(0.0, min(1.0, 1.0 - abs(pred_pct) / 100.0))

            # Pick recommended horizon (longest horizon with positive expected return)
            recommended = '2y'
            for h in ['2y', '1y', '6m', '3m', '1m']:
                if predictions[h] > 0:
                    recommended = h
                    break

            overall_score = float(np.mean([predictions[h] for h in ['1y', '2y']]))

            fair_value = fair_values[recommended]
            margin_of_safety = (fair_value - current_price) / current_price if current_price > 0 else 0
            upside_pct = ((fair_value / current_price) - 1) * 100 if current_price > 0 else 0
            confidence = confidence_scores[recommended]

            details = {
                'predictions': predictions,
                'fair_values': fair_values,
                'confidence_scores': confidence_scores,
                'recommended_horizon': recommended,
                'overall_score': overall_score,
                'target_type': 'excess_return' if is_excess else 'absolute',
            }

            result = {
                'fair_value': fair_value,
                'upside': float(upside_pct),
                'margin_of_safety': float(margin_of_safety),
                'suitable': True,
                'details': details
            }

            # Add to stock valuations
            if 'valuations' not in stock:
                stock['valuations'] = {}
            stock['valuations']['multi_horizon_nn'] = result
            stock['current_price'] = float(current_price)

            save_nn_prediction(
                db_conn,
                'multi_horizon_nn',
                ticker,
                fair_value,
                float(current_price),
                float(margin_of_safety),
                float(upside_pct),
                confidence=confidence,
                details=details
            )
            db_save_count += 1

            success_count += 1

            if (i + 1) % 50 == 0:
                print(f'   [{i+1}/{len(stocks)}] Processed {ticker}...')

        except Exception as e:
            import traceback
            if error_count < 3:  # Only print first 3 errors in detail
                print(f'   [{i+1}/{len(stocks)}] {ticker}: Error - {str(e)}')
                traceback.print_exc()
            if 'valuations' not in stock:
                stock['valuations'] = {}
            stock['valuations']['multi_horizon_nn'] = {
                'error': str(e),
                'suitable': False
            }
            error_count += 1

    # Close database connection
    db_conn.close()

    # Save updated data
    print('\nSaving updated dashboard data...')
    with open(dashboard_data_path, 'w') as f:
        json.dump(data, f, indent=2)

    # Summary
    print('\nPredictions complete!')
    print('=' * 60)
    print('Summary:')
    print(f'   Successful predictions: {success_count}')
    print(f'   Saved to database: {db_save_count}')
    print(f'   Cache misses: {cache_miss_count}')
    print(f'   Errors: {error_count}')
    print(f'   Total stocks: {len(stocks)}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
