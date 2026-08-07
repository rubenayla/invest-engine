#!/usr/bin/env python3
"""
Train multi-horizon neural network model using cached stock data.
"""

import logging
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import torch

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.invest.valuation.multi_horizon_nn import MultiHorizonValuationModel

from src.invest.valuation.neural_network_model import FeatureEngineer

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MultiHorizonTrainer:
    """Train multi-horizon model with cached stock data."""

    def __init__(self, db_path: str = 'stock_data.db'):
        self.db_path = Path(__file__).parent / db_path
        self.feature_engineer = FeatureEngineer()

    def load_cached_data(self) -> List[Tuple]:
        """Load training data from SQLite database."""
        logger.info(f'Loading data from {self.db_path}')

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get summary stats
        cursor.execute('SELECT COUNT(*) FROM snapshots')
        snapshot_count = cursor.fetchone()[0]

        cursor.execute('SELECT MIN(snapshot_date), MAX(snapshot_date) FROM snapshots')
        start_date, end_date = cursor.fetchone()

        logger.info(f'Loaded {snapshot_count} snapshots from database')
        logger.info(f'Data period: {start_date} to {end_date}')
        logger.info('Horizons: [\'1m\', \'3m\', \'6m\', \'1y\', \'2y\']')

        # Load all snapshots with their forward returns
        cursor.execute('''
            SELECT
                a.symbol,
                s.snapshot_date,
                s.current_price, s.volume, s.market_cap, s.shares_outstanding,
                s.pe_ratio, s.pb_ratio, s.ps_ratio, s.peg_ratio,
                s.price_to_book, s.price_to_sales, s.enterprise_to_revenue, s.enterprise_to_ebitda,
                s.profit_margins, s.operating_margins, s.gross_margins, s.ebitda_margins,
                s.return_on_assets, s.return_on_equity,
                s.revenue_growth, s.earnings_growth, s.earnings_quarterly_growth, s.revenue_per_share,
                s.total_cash, s.total_debt, s.debt_to_equity, s.current_ratio, s.quick_ratio,
                s.operating_cashflow, s.free_cashflow,
                s.trailing_eps, s.forward_eps, s.book_value,
                s.dividend_rate, s.dividend_yield, s.payout_ratio,
                s.price_change_pct, s.volatility, s.beta,
                s.fifty_day_average, s.two_hundred_day_average,
                s.fifty_two_week_high, s.fifty_two_week_low,
                s.vix, s.treasury_10y, s.dollar_index, s.oil_price, s.gold_price,
                s.id
            FROM snapshots s
            JOIN assets a ON s.asset_id = a.id
            ORDER BY s.snapshot_date
        ''')

        snapshots = cursor.fetchall()

        # Build samples list
        samples = []
        for row in snapshots:
            ticker = row[0]
            snapshot_id = row[-1]  # Last column is snapshot ID

            # Get forward returns for this snapshot
            cursor.execute('''
                SELECT horizon, return_pct
                FROM forward_returns
                WHERE snapshot_id = ?
            ''', (snapshot_id,))

            forward_returns = {horizon: return_pct for horizon, return_pct in cursor.fetchall()}

            # Build data dict (dummy structure for compatibility with FeatureEngineer)
            # The actual features are already extracted in the database
            {
                'info': {},
                'history': pd.DataFrame(),  # Empty, features already extracted
                'macro': {}
            }

            # Store features directly as dict for easier access
            feature_dict = {
                'current_price': row[2], 'volume': row[3], 'market_cap': row[4], 'shares_outstanding': row[5],
                'pe_ratio': row[6], 'pb_ratio': row[7], 'ps_ratio': row[8], 'peg_ratio': row[9],
                'price_to_book': row[10], 'price_to_sales': row[11], 'enterprise_to_revenue': row[12],
                'enterprise_to_ebitda': row[13], 'profit_margins': row[14], 'operating_margins': row[15],
                'gross_margins': row[16], 'ebitda_margins': row[17], 'return_on_assets': row[18],
                'return_on_equity': row[19], 'revenue_growth': row[20], 'earnings_growth': row[21],
                'earnings_quarterly_growth': row[22], 'revenue_per_share': row[23], 'total_cash': row[24],
                'total_debt': row[25], 'debt_to_equity': row[26], 'current_ratio': row[27], 'quick_ratio': row[28],
                'operating_cashflow': row[29], 'free_cashflow': row[30], 'trailing_eps': row[31],
                'forward_eps': row[32], 'book_value': row[33], 'dividend_rate': row[34], 'dividend_yield': row[35],
                'payout_ratio': row[36], 'price_change_pct': row[37], 'volatility': row[38], 'beta': row[39],
                'fifty_day_average': row[40], 'two_hundred_day_average': row[41], 'fifty_two_week_high': row[42],
                'fifty_two_week_low': row[43], 'vix': row[44], 'treasury_10y': row[45], 'dollar_index': row[46],
                'oil_price': row[47], 'gold_price': row[48]
            }

            samples.append((ticker, feature_dict, forward_returns))

        conn.close()
        return samples

    def prepare_multi_horizon_targets(self, samples: List[Tuple]) -> Tuple:
        """
        Prepare features and REAL multi-horizon targets from database.
        """
        logger.info('Preparing features and multi-horizon targets...')

        X_list = []
        y_dict = {'1m': [], '3m': [], '6m': [], '1y': [], '2y': []}
        valid_samples = []

        for i, (ticker, feature_dict, forward_returns) in enumerate(samples):
            if i % 500 == 0:
                logger.info(f'Processing sample {i}/{len(samples)}')

            try:
                # Features are already extracted in the database
                # Just need to convert dict to the format expected by FeatureEngineer

                # Use REAL forward returns from database (already in percentage)
                for horizon in ['1m', '3m', '6m', '1y', '2y']:
                    y_dict[horizon].append(forward_returns[horizon] * 100)  # Convert to percentage

                X_list.append(feature_dict)
                valid_samples.append((ticker, feature_dict, forward_returns))

            except Exception as e:
                logger.warning(f'Error processing sample {i}: {e}')
                continue

        logger.info(f'Successfully processed {len(X_list)} samples')

        # Fit feature scaler and transform
        X_array = self.feature_engineer.fit_transform(X_list)

        # Convert targets to numpy arrays
        for horizon in y_dict:
            y_dict[horizon] = np.array(y_dict[horizon])

        return X_array, y_dict, valid_samples

    def split_data(self, X: np.ndarray, y: Dict[str, np.ndarray],
                   train_ratio: float = 0.7, val_ratio: float = 0.15):
        """Split data into train/val/test sets using chronological ordering.

        Data is already sorted by snapshot_date from the SQL query, so we
        simply slice by position: oldest → train, middle → val, newest → test.
        This prevents look-ahead bias (training on future data to predict the past).
        """
        n_samples = len(X)
        n_train = int(n_samples * train_ratio)
        n_val = int(n_samples * val_ratio)

        X_train = X[:n_train]
        X_val = X[n_train:n_train + n_val]
        X_test = X[n_train + n_val:]

        y_train = {h: y[h][:n_train] for h in y}
        y_val = {h: y[h][n_train:n_train + n_val] for h in y}
        y_test = {h: y[h][n_train + n_val:] for h in y}

        logger.info(f'Data split (chronological): Train={len(X_train)}, Val={len(X_val)}, Test={len(X_test)}')

        return X_train, X_val, X_test, y_train, y_val, y_test

    def train(self):
        """Main training pipeline."""
        logger.info('='*60)
        logger.info('Starting Multi-Horizon Model Training')
        logger.info('='*60)

        # Load cached data
        samples = self.load_cached_data()

        # Prepare features and targets
        X, y, valid_samples = self.prepare_multi_horizon_targets(samples)

        # Split data
        X_train, X_val, X_test, y_train, y_val, y_test = self.split_data(X, y)

        # Create model
        feature_dim = X_train.shape[1]
        logger.info(f'Feature dimension: {feature_dim}')
        model = MultiHorizonValuationModel(feature_dim=feature_dim)

        # Train model
        logger.info('\nTraining multi-horizon model...')
        history = model.train_model(
            X_train, y_train, X_val, y_val,
            epochs=100,
            batch_size=64,
            learning_rate=0.001
        )

        # Evaluate on test set
        logger.info('\n' + '='*60)
        logger.info('Evaluating on Test Set')
        logger.info('='*60)

        model.model.eval()

        with torch.no_grad():
            X_test_t = torch.FloatTensor(X_test).to(model.device)
            predictions = model.model(X_test_t)

            for horizon in model.model.horizons:
                pred = predictions[horizon].cpu().numpy()
                actual = y_test[horizon]

                # Calculate metrics
                mae = np.mean(np.abs(pred.squeeze() - actual))
                rmse = np.sqrt(np.mean((pred.squeeze() - actual) ** 2))
                correlation = np.corrcoef(pred.squeeze(), actual)[0, 1]

                logger.info(f'{horizon:3s}: MAE={mae:.2f}%, RMSE={rmse:.2f}%, Corr={correlation:.3f}')

        # Save model with date in filename (preserves old models)
        date_str = datetime.now().strftime('%Y%m%d')
        model_dir = Path(__file__).parent
        model_path = model_dir / f'multi_horizon_model_{date_str}.pt'

        checkpoint = {
            'model_state_dict': model.model.state_dict(),
            'feature_dim': feature_dim,
            'feature_names': self.feature_engineer.feature_names,
            'scaler_state': {
                'center_': self.feature_engineer.scaler.center_.tolist(),
                'scale_': self.feature_engineer.scaler.scale_.tolist(),
            },
            'target_type': 'excess_return',  # vs SPY
            'training_history': history,
            'split_method': 'chronological',
            'timestamp': datetime.now().isoformat()
        }
        torch.save(checkpoint, model_path)

        # Back up existing standard model, then overwrite with new one
        standard_path = model_dir.parent / 'models' / 'multi_horizon_model.pt'
        if standard_path.exists():
            backup_path = model_dir / 'old_models' / f'multi_horizon_model_{date_str}_pre.pt'
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(standard_path, backup_path)
            logger.info(f'Backed up previous model to {backup_path}')
        torch.save(checkpoint, standard_path)

        logger.info(f'\nModel saved to {model_path}')

        # Example prediction
        logger.info('\n' + '='*60)
        logger.info('Example Prediction on Test Sample')
        logger.info('='*60)

        test_sample = X_test[0:1]
        prediction = model.predict(test_sample, current_price=100.0)

        logger.info('Predictions for test sample:')
        for horizon in model.model.horizons:
            logger.info(f'  {horizon:3s}: {prediction.predictions[horizon]:+6.2f}% '
                       f'[Confidence: {prediction.confidence_scores[horizon]:.1%}]')
        logger.info(f'Recommended horizon: {prediction.recommended_horizon}')

        return model, history


if __name__ == '__main__':
    # Set random seed for reproducibility
    np.random.seed(42)
    torch.manual_seed(42)

    # Train model
    trainer = MultiHorizonTrainer()
    model, history = trainer.train()

    logger.info('\n✅ Training complete!')
