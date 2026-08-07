#!/usr/bin/env python3
"""
Comprehensive Model Evaluation Script
======================================

Evaluates the trained LSTM/Transformer model using the historical snapshot database.

Features:
- Test set performance metrics (MAE, RMSE, R², hit rate)
- Decade-by-decade analysis (2006-2010, 2011-2015, 2016-2020, 2021-2022)
- Sector-specific accuracy
- Confidence calibration (MC Dropout)
- Error analysis and visualization
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

from invest.valuation.lstm_transformer_model import LSTMTransformerNetwork


class ModelEvaluator:
    """Evaluates trained neural network model."""

    def __init__(
        self,
        model_path: str = 'best_model.pt',
        db_path: str = '../../data/stock_data.db',
        target_horizon: str = '1y'
    ):
        self.model_path = Path(__file__).parent / model_path
        self.db_path = Path(__file__).parent.parent.parent / 'data' / 'stock_data.db'
        self.target_horizon = target_horizon
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

        print(f'Loading model from {self.model_path}')
        print(f'Using database: {self.db_path}')
        print(f'Target horizon: {target_horizon}')

        # Load model
        self.model = self._load_model()

    def _load_model(self) -> LSTMTransformerNetwork:
        """Load trained model from checkpoint."""
        # Model architecture must match training (updated to use only real data)
        # Temporal: 9 features (4 price-based + 5 macro)
        # Static: 16 features (5 macro + 11 sectors)
        model = LSTMTransformerNetwork(
            temporal_features=9,
            static_features=16,
            lstm_hidden=256,
            transformer_heads=8,
            dropout_rate=0.3
        )

        # Load weights
        state_dict = torch.load(self.model_path, map_location=self.device)
        model.load_state_dict(state_dict)
        model.to(self.device)
        model.eval()

        print('Model loaded successfully (9 temporal, 16 static features)')
        return model

    def load_test_data(self, test_start: str = '2021-01-01') -> pd.DataFrame:
        """
        Load test set from database.

        Parameters
        ----------
        test_start : str
            Start date for test set (default: 2021-01-01)

        Returns
        -------
        pd.DataFrame
            Test samples with features and targets
        """
        print(f'\nLoading test data from {test_start}...')

        conn = sqlite3.connect(self.db_path)

        # Load snapshots with macro indicators only (no fake fundamentals)
        query = '''
            SELECT
                s.id,
                a.symbol,
                a.sector,
                s.snapshot_date,
                s.vix,
                s.treasury_10y,
                s.dollar_index,
                s.oil_price,
                s.gold_price,
                fr.return_pct
            FROM snapshots s
            JOIN assets a ON s.asset_id = a.id
            LEFT JOIN forward_returns fr ON s.id = fr.snapshot_id
            WHERE s.snapshot_date >= ?
                AND fr.horizon = ?
                AND s.vix IS NOT NULL
                AND fr.return_pct IS NOT NULL
            ORDER BY a.symbol, s.snapshot_date
        '''

        df = pd.read_sql_query(query, conn, params=(test_start, self.target_horizon))
        conn.close()

        print(f'Loaded {len(df)} test samples')
        print(f'Date range: {df.snapshot_date.min()} to {df.snapshot_date.max()}')
        print(f'Unique stocks: {df.symbol.nunique()}')
        print(f'Sectors: {df.sector.nunique()}')

        return df

    def prepare_features(self, df: pd.DataFrame, min_sequence_length: int = 4) -> Tuple[List, List, List]:
        """
        Prepare temporal and static features for model input.

        Parameters
        ----------
        df : pd.DataFrame
            Raw data from database
        min_sequence_length : int
            Minimum number of historical snapshots per stock

        Returns
        -------
        Tuple[List, List, List]
            (samples, targets, metadata)
        """
        print('\nPreparing features...')

        samples = []
        targets = []
        metadata = []

        # Connect to database to fetch price history
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Group by stock
        for symbol in df.symbol.unique():
            stock_df = df[df.symbol == symbol].sort_values('snapshot_date')

            if len(stock_df) < min_sequence_length:
                continue

            sector = stock_df.iloc[0].sector

            # Create sliding windows
            for i in range(len(stock_df) - min_sequence_length + 1):
                sequence = stock_df.iloc[i:i + min_sequence_length]
                latest = sequence.iloc[-1]

                # Get price history for latest snapshot
                cursor.execute('''
                    SELECT date, close, volume
                    FROM price_history
                    WHERE snapshot_id = ?
                    ORDER BY date
                ''', (int(latest.id),))
                price_history = cursor.fetchall()

                if len(price_history) < 60:
                    continue

                # Extract temporal features (price history + macro)
                temporal = self._extract_temporal(sequence, price_history)

                # Extract static features (macro indicators + sector)
                static = self._extract_static(latest, sector)

                # Target (forward return - database stores as decimal, where 0.314 = 31.4%)
                target = latest.return_pct

                if temporal is not None and static is not None:
                    samples.append((temporal, static))
                    targets.append(target)
                    metadata.append({
                        'symbol': symbol,
                        'sector': sector,
                        'date': latest.snapshot_date,
                        'year': int(latest.snapshot_date[:4])
                    })

        conn.close()
        print(f'Prepared {len(samples)} samples with sequences')
        return samples, targets, metadata

    def _extract_temporal(self, sequence: pd.DataFrame, price_history: List) -> np.ndarray:
        """
        Extract temporal features from price history and macro indicators.

        Uses ONLY real data (matches train_single_horizon.py).
        """
        # Calculate price-based features from last 60 days
        recent_prices = [p[1] for p in price_history[-60:]]
        recent_volumes = [p[2] for p in price_history[-60:]]

        if len(recent_prices) < 60:
            return None

        # Price momentum
        returns_1m = (recent_prices[-1] - recent_prices[-21]) / recent_prices[-21] if len(recent_prices) >= 21 else 0.0
        returns_3m = (recent_prices[-1] - recent_prices[0]) / recent_prices[0]
        volatility = np.std(np.diff(recent_prices) / recent_prices[:-1])

        # Volume trend
        vol_avg = np.mean(recent_volumes)
        vol_recent = np.mean(recent_volumes[-5:])
        volume_trend = (vol_recent - vol_avg) / vol_avg if vol_avg > 0 else 0.0

        # Temporal sequence from macro indicators
        temporal_features = []
        for _, snapshot in sequence.iterrows():
            features = [
                returns_1m,
                returns_3m,
                volatility,
                volume_trend,
                snapshot.vix if pd.notna(snapshot.vix) else 20.0,
                snapshot.treasury_10y if pd.notna(snapshot.treasury_10y) else 3.0,
                snapshot.dollar_index if pd.notna(snapshot.dollar_index) else 100.0,
                snapshot.oil_price if pd.notna(snapshot.oil_price) else 70.0,
                snapshot.gold_price if pd.notna(snapshot.gold_price) else 1800.0,
            ]
            temporal_features.append(features)

        return np.array(temporal_features)

    def _extract_static(self, snapshot: pd.Series, sector: str) -> np.ndarray:
        """
        Extract static features from macro indicators and sector.

        Uses ONLY real data (matches train_single_horizon.py).
        """
        features = []

        # Macro indicators
        features.extend([
            snapshot.vix if pd.notna(snapshot.vix) else 20.0,
            snapshot.treasury_10y if pd.notna(snapshot.treasury_10y) else 3.0,
            snapshot.dollar_index if pd.notna(snapshot.dollar_index) else 100.0,
            snapshot.oil_price if pd.notna(snapshot.oil_price) else 70.0,
            snapshot.gold_price if pd.notna(snapshot.gold_price) else 1800.0,
        ])

        # Sector one-hot encoding
        sectors = [
            'Technology', 'Healthcare', 'Financial Services', 'Consumer Cyclical',
            'Industrials', 'Communication Services', 'Consumer Defensive',
            'Energy', 'Utilities', 'Real Estate', 'Basic Materials'
        ]
        for s in sectors:
            features.append(1.0 if sector == s else 0.0)

        return np.array(features)

    def evaluate(
        self,
        samples: List[Tuple],
        targets: List[float],
        metadata: List[dict],
        n_mc_samples: int = 100
    ) -> Dict:
        """
        Run evaluation with MC Dropout for confidence estimation.

        Parameters
        ----------
        samples : List[Tuple]
            (temporal, static) feature tuples
        targets : List[float]
            Actual forward returns
        metadata : List[dict]
            Sample metadata
        n_mc_samples : int
            Number of MC Dropout samples for confidence estimation

        Returns
        -------
        Dict
            Evaluation results
        """
        print(f'\nRunning evaluation with {n_mc_samples} MC Dropout samples...')

        predictions = []
        prediction_stds = []

        # Enable dropout for MC sampling
        for module in self.model.modules():
            if isinstance(module, torch.nn.Dropout):
                module.train()
            elif isinstance(module, torch.nn.BatchNorm1d):
                module.eval()

        with torch.no_grad():
            for i, (temporal, static) in enumerate(samples):
                if (i + 1) % 100 == 0:
                    print(f'  Processed {i + 1}/{len(samples)} samples...')

                # Convert to tensors
                temporal_tensor = torch.FloatTensor(temporal).unsqueeze(0).to(self.device)
                static_tensor = torch.FloatTensor(static).unsqueeze(0).to(self.device)

                # MC Dropout: multiple forward passes
                mc_predictions = []
                for _ in range(n_mc_samples):
                    pred = self.model(temporal_tensor, static_tensor)
                    mc_predictions.append(pred.cpu().numpy()[0, 0])

                # Calculate mean and std
                mc_predictions = np.array(mc_predictions)
                predictions.append(float(np.mean(mc_predictions)))
                prediction_stds.append(float(np.std(mc_predictions)))

        predictions = np.array(predictions)
        prediction_stds = np.array(prediction_stds)
        targets = np.array(targets)

        # Calculate metrics
        results = self._calculate_metrics(predictions, targets, prediction_stds, metadata)

        return results

    def _calculate_metrics(
        self,
        predictions: np.ndarray,
        targets: np.ndarray,
        prediction_stds: np.ndarray,
        metadata: List[dict]
    ) -> Dict:
        """Calculate comprehensive evaluation metrics."""
        print('\nCalculating metrics...')

        # Overall metrics
        mae = mean_absolute_error(targets, predictions)
        rmse = np.sqrt(mean_squared_error(targets, predictions))
        r2 = r2_score(targets, predictions)  # Fixed: was comparing targets to targets
        correlation = np.corrcoef(predictions, targets)[0, 1]

        # Hit rate (correct direction)
        correct_direction = ((predictions > 0) == (targets > 0)).mean()

        # Confidence calibration (95% CI coverage)
        lower_bound = predictions - 2 * prediction_stds
        upper_bound = predictions + 2 * prediction_stds
        ci_coverage = ((targets >= lower_bound) & (targets <= upper_bound)).mean()

        # Create results dataframe
        df = pd.DataFrame({
            'prediction': predictions,
            'target': targets,
            'error': predictions - targets,
            'abs_error': np.abs(predictions - targets),
            'std': prediction_stds,
            'symbol': [m['symbol'] for m in metadata],
            'sector': [m['sector'] for m in metadata],
            'year': [m['year'] for m in metadata],
            'date': [m['date'] for m in metadata]
        })

        # Decade-by-decade analysis
        decade_results = {}
        for decade in [2000, 2010, 2020]:
            decade_df = df[(df.year >= decade) & (df.year < decade + 10)]
            if len(decade_df) > 0:
                decade_results[f'{decade}s'] = {
                    'mae': decade_df.abs_error.mean(),
                    'rmse': np.sqrt((decade_df.error ** 2).mean()),
                    'correlation': decade_df[['prediction', 'target']].corr().iloc[0, 1],
                    'hit_rate': ((decade_df.prediction > 0) == (decade_df.target > 0)).mean(),
                    'n_samples': len(decade_df)
                }

        # Sector-specific analysis
        sector_results = {}
        for sector in df.sector.unique():
            sector_df = df[df.sector == sector]
            sector_results[sector] = {
                'mae': sector_df.abs_error.mean(),
                'rmse': np.sqrt((sector_df.error ** 2).mean()),
                'correlation': sector_df[['prediction', 'target']].corr().iloc[0, 1],
                'hit_rate': ((sector_df.prediction > 0) == (sector_df.target > 0)).mean(),
                'n_samples': len(sector_df)
            }

        # Find worst predictions
        worst_predictions = df.nlargest(10, 'abs_error')[['symbol', 'sector', 'date', 'prediction', 'target', 'error']]

        return {
            'overall': {
                'mae': mae,
                'rmse': rmse,
                'r2': r2,
                'correlation': correlation,
                'hit_rate': correct_direction,
                'ci_95_coverage': ci_coverage,
                'n_samples': len(predictions)
            },
            'by_decade': decade_results,
            'by_sector': sector_results,
            'worst_predictions': worst_predictions,
            'full_results': df
        }

    def generate_report(self, results: Dict) -> str:
        """Generate human-readable evaluation report."""
        lines = []
        lines.append('=' * 80)
        lines.append('NEURAL NETWORK MODEL EVALUATION REPORT')
        lines.append('=' * 80)
        lines.append(f'Model: {self.model_path.name}')
        lines.append(f'Target Horizon: {self.target_horizon}')
        lines.append(f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        lines.append('')

        # Overall performance
        overall = results['overall']
        lines.append('OVERALL PERFORMANCE')
        lines.append('-' * 80)
        lines.append(f'  Samples:                    {overall["n_samples"]:,}')
        lines.append(f'  Mean Absolute Error (MAE):  {overall["mae"]:.4f} ({overall["mae"]*100:.2f}%)')
        lines.append(f'  Root Mean Squared Error:    {overall["rmse"]:.4f} ({overall["rmse"]*100:.2f}%)')
        lines.append(f'  R-squared:                  {overall["r2"]:.4f}')
        lines.append(f'  Correlation:                {overall["correlation"]:.4f}')
        lines.append(f'  Hit Rate (direction):       {overall["hit_rate"]:.2%}')
        lines.append(f'  95% CI Coverage:            {overall["ci_95_coverage"]:.2%} (expected 95%)')
        lines.append('')

        # Decade analysis
        lines.append('PERFORMANCE BY DECADE')
        lines.append('-' * 80)
        for decade, metrics in sorted(results['by_decade'].items()):
            lines.append(f'  {decade}:')
            lines.append(f'    MAE:         {metrics["mae"]:.4f} ({metrics["mae"]*100:.2f}%)')
            lines.append(f'    RMSE:        {metrics["rmse"]:.4f}')
            lines.append(f'    Correlation: {metrics["correlation"]:.4f}')
            lines.append(f'    Hit Rate:    {metrics["hit_rate"]:.2%}')
            lines.append(f'    Samples:     {metrics["n_samples"]:,}')
            lines.append('')

        # Sector analysis
        lines.append('PERFORMANCE BY SECTOR')
        lines.append('-' * 80)
        for sector, metrics in sorted(results['by_sector'].items(), key=lambda x: x[1]['mae']):
            lines.append(f'  {sector:25s}: MAE={metrics["mae"]:.4f}, '
                        f'Corr={metrics["correlation"]:.3f}, '
                        f'Hit={metrics["hit_rate"]:.2%}, '
                        f'n={metrics["n_samples"]:,}')
        lines.append('')

        # Worst predictions
        lines.append('TOP 10 WORST PREDICTIONS')
        lines.append('-' * 80)
        for i, row in results['worst_predictions'].iterrows():
            lines.append(f'  {row.symbol:6s} {row.sector:20s} {row.date:12s} | '
                        f'Pred: {row.prediction:+.2%}, Actual: {row.target:+.2%}, '
                        f'Error: {row.error:+.2%}')
        lines.append('')

        lines.append('=' * 80)

        return '\n'.join(lines)


def main():
    """Run comprehensive evaluation."""
    evaluator = ModelEvaluator(
        model_path='best_model.pt',
        target_horizon='1y'
    )

    # Load test data
    df = evaluator.load_test_data(test_start='2021-01-01')

    # Prepare features
    samples, targets, metadata = evaluator.prepare_features(df)

    # Run evaluation
    results = evaluator.evaluate(samples, targets, metadata, n_mc_samples=100)

    # Generate report
    report = evaluator.generate_report(results)
    print('\n' + report)

    # Save results
    output_dir = Path(__file__).parent / 'evaluation_results'
    output_dir.mkdir(exist_ok=True)

    report_path = output_dir / 'evaluation_report.txt'
    with open(report_path, 'w') as f:
        f.write(report)

    print(f'\nReport saved to: {report_path}')

    # Save detailed results
    csv_path = output_dir / 'detailed_results.csv'
    results['full_results'].to_csv(csv_path, index=False)
    print(f'Detailed results saved to: {csv_path}')


if __name__ == '__main__':
    main()
