#!/usr/bin/env python3
"""
Train single-horizon LSTM/Transformer model for 1-year stock predictions.

This script:
- Loads historical snapshots from database
- Converts snapshot sequences into LSTM-compatible temporal features
- Trains the model with decade/sector-aware train/val/test splits
- Evaluates model performance across different time periods and sectors

Database Structure:
------------------
- snapshots: Point-in-time fundamental data (PE, margins, growth, etc.) + macro indicators
  - NOTE: current_price field is always NULL (not used, we have price_history)
  - Contains 17,840 snapshots from 150+ stocks (2008-2025)
  - 2,790+ snapshots with populated fundamental ratios from SEC EDGAR data

- price_history: Daily OHLCV data linked to each snapshot
  - 8.5M records with actual historical prices
  - Used to calculate forward returns

- forward_returns: Pre-calculated returns for each snapshot
  - Horizons: 1m, 3m, 6m, 1y, 2y
  - Already computed by create_multi_horizon_cache.py

- assets: Stock symbols and sectors
"""

import argparse
import logging
import sqlite3
import sys
from pathlib import Path
from typing import List, Tuple

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / 'src'))

from invest.valuation.lstm_transformer_model import LSTMTransformerNetwork

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class StockSnapshotDataset(Dataset):
    """Dataset for historical stock snapshots with temporal sequences."""

    def __init__(self, samples: List[Tuple[np.ndarray, np.ndarray, float]]):
        """
        Initialize dataset.

        Parameters
        ----------
        samples : List[Tuple]
            List of (temporal_features, static_features, target_return) tuples
        """
        self.samples = samples

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        temporal, static, target = self.samples[idx]
        return (
            torch.FloatTensor(temporal),
            torch.FloatTensor(static),
            torch.FloatTensor([target])
        )


class SingleHorizonTrainer:
    """Trainer for single-horizon model."""

    def __init__(self, db_path: str = '../../data/stock_data.db', target_horizon: str = '1y'):
        self.db_path = Path(__file__).parent / db_path
        self.model = None
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.target_horizon = target_horizon

    def load_training_data(
        self,
        min_samples_per_stock: int = 4,
        target_horizon: str = '1y'
    ) -> Tuple[List, List, List]:
        """
        Load and prepare training data from database.

        Parameters
        ----------
        min_samples_per_stock : int
            Minimum number of historical snapshots per stock to use as sequence
        target_horizon : str
            Target prediction horizon (default: '1y')

        Returns
        -------
        Tuple[List, List, List]
            (train_samples, val_samples, test_samples)
        """
        logger.info(f'Loading data from {self.db_path}')

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Load snapshots with macro indicators AND fundamental features
        # Use ALL available real data: price history + macro + fundamentals
        cursor.execute('''
            SELECT
                a.symbol,
                a.sector,
                s.snapshot_date,
                s.vix,
                s.treasury_10y,
                s.dollar_index,
                s.oil_price,
                s.gold_price,
                s.pe_ratio,
                s.pb_ratio,
                s.ps_ratio,
                s.profit_margins,
                s.operating_margins,
                s.return_on_equity,
                s.revenue_growth,
                s.earnings_growth,
                s.debt_to_equity,
                s.current_ratio,
                s.trailing_eps,
                s.book_value,
                s.free_cashflow,
                s.operating_cashflow,
                s.market_cap,
                s.id
            FROM snapshots s
            JOIN assets a ON s.asset_id = a.id
            WHERE s.vix IS NOT NULL  -- Filter: require macro data
            ORDER BY a.symbol, s.snapshot_date
        ''')

        rows = cursor.fetchall()

        # Group by stock symbol
        stock_data = {}
        for row in rows:
            symbol = row[0]
            if symbol not in stock_data:
                stock_data[symbol] = []
            stock_data[symbol].append(row)

        logger.info(f'Loaded data for {len(stock_data)} stocks')

        # Create samples from sequences
        samples = []

        for symbol, snapshots in stock_data.items():
            if len(snapshots) < min_samples_per_stock:
                continue

            sector = snapshots[0][1]

            # Create sliding windows
            for i in range(len(snapshots) - min_samples_per_stock):
                # Use past N snapshots as temporal sequence
                sequence = snapshots[i:i + min_samples_per_stock]
                snapshot_id = sequence[-1][-1]  # ID of most recent snapshot

                # Get forward return for target horizon
                cursor.execute('''
                    SELECT return_pct
                    FROM forward_returns
                    WHERE snapshot_id = ? AND horizon = ?
                ''', (snapshot_id, target_horizon))

                result = cursor.fetchone()
                if not result or result[0] is None:
                    continue

                # Database already stores as decimal (2.05 = 205% gain)
                forward_return = float(result[0])

                # Get price history for this snapshot to extract temporal features
                cursor.execute('''
                    SELECT date, close, volume
                    FROM price_history
                    WHERE snapshot_id = ?
                    ORDER BY date
                ''', (snapshot_id,))
                price_history = cursor.fetchall()

                if len(price_history) < 60:  # Need at least 60 days of price history
                    continue

                # Extract temporal features (from price history + sequence of macro indicators)
                temporal_features = self._extract_temporal_from_sequence(sequence, price_history)

                # Extract static features (most recent snapshot with macro indicators)
                static_features = self._extract_static_from_snapshot(sequence[-1], sector)

                if temporal_features is not None and static_features is not None:
                    # Add metadata for stratified splitting
                    sample = {
                        'temporal': temporal_features,
                        'static': static_features,
                        'target': forward_return,
                        'symbol': symbol,
                        'sector': sector,
                        'date': sequence[-1][2],  # snapshot_date
                    }
                    samples.append(sample)

        logger.info(f'Created {len(samples)} training samples')

        # Stratified split by decade and sector
        train_samples, val_samples, test_samples = self._stratified_split(samples)

        logger.info(f'Train: {len(train_samples)}, Val: {len(val_samples)}, Test: {len(test_samples)}')

        conn.close()
        return train_samples, val_samples, test_samples

    def _extract_temporal_from_sequence(self, sequence: List, price_history: List) -> np.ndarray:
        """
        Extract temporal features from price history, macro indicators, and fundamentals.

        Uses ONLY real historical data:
        - Price momentum and volatility (from price_history)
        - Macro indicators (VIX, rates, commodities) from snapshots
        - Fundamental ratios (PE, PB, margins, ROE, debt, cash flows) from snapshots

        Parameters
        ----------
        sequence : List
            List of snapshot rows with macro indicators and fundamental data
        price_history : List
            Price history tuples (date, close, volume)

        Returns
        -------
        np.ndarray
            Shape: (num_snapshots, 17) - 4 price + 5 macro + 8 fundamental features
        """
        # Calculate price-based features from last 60 days
        recent_prices = [p[1] for p in price_history[-60:]]  # Last 60 closes
        recent_volumes = [p[2] for p in price_history[-60:]]  # Last 60 volumes

        if len(recent_prices) < 60:
            return None

        # Price momentum features (calculated from real price data)
        returns_1m = (recent_prices[-1] - recent_prices[-21]) / recent_prices[-21] if len(recent_prices) >= 21 else 0.0
        returns_3m = (recent_prices[-1] - recent_prices[0]) / recent_prices[0]
        volatility = np.std(np.diff(recent_prices) / recent_prices[:-1])

        # Volume trend
        vol_avg = np.mean(recent_volumes)
        vol_recent = np.mean(recent_volumes[-5:])
        volume_trend = (vol_recent - vol_avg) / vol_avg if vol_avg > 0 else 0.0

        # Temporal sequence from macro indicators + fundamental features (each snapshot in sequence)
        temporal_features = []
        for snapshot in sequence:
            # Indices: symbol(0), sector(1), date(2), vix(3), treasury(4), dollar(5), oil(6), gold(7),
            # pe_ratio(8), pb_ratio(9), ps_ratio(10), profit_margins(11), operating_margins(12),
            # return_on_equity(13), revenue_growth(14), earnings_growth(15), debt_to_equity(16),
            # current_ratio(17), trailing_eps(18), book_value(19), free_cashflow(20),
            # operating_cashflow(21), market_cap(22), id(23)

            # Calculate cash flow yields for temporal features
            market_cap = snapshot[22] if snapshot[22] is not None and snapshot[22] > 0 else 1e9
            fcf = snapshot[20] if snapshot[20] is not None else 0.0
            ocf = snapshot[21] if snapshot[21] is not None else 0.0
            fcf_yield = fcf / market_cap
            ocf_yield = ocf / market_cap

            features = [
                # Price-based features (4)
                returns_1m,
                returns_3m,
                volatility,
                volume_trend,
                # Macro indicators (5)
                snapshot[3] if snapshot[3] is not None else 20.0,  # VIX
                snapshot[4] if snapshot[4] is not None else 3.0,  # Treasury 10Y
                snapshot[5] if snapshot[5] is not None else 100.0,  # Dollar Index
                snapshot[6] if snapshot[6] is not None else 70.0,  # Oil price
                snapshot[7] if snapshot[7] is not None else 1800.0,  # Gold price
                # Fundamental features (8) - showing evolution over time
                min(max(snapshot[8] if snapshot[8] is not None else 20.0, -50.0), 100.0),  # PE ratio
                min(max(snapshot[9] if snapshot[9] is not None else 3.0, 0.0), 20.0),  # PB ratio
                snapshot[11] if snapshot[11] is not None else 0.10,  # Profit margins
                snapshot[12] if snapshot[12] is not None else 0.15,  # Operating margins
                snapshot[13] if snapshot[13] is not None else 0.10,  # ROE
                min(max(snapshot[16] if snapshot[16] is not None else 0.5, 0.0), 5.0),  # Debt-to-equity
                fcf_yield,  # Free cash flow yield
                ocf_yield,  # Operating cash flow yield
            ]
            temporal_features.append(features)

        return np.array(temporal_features)

    def _extract_static_from_snapshot(self, snapshot, sector: str) -> np.ndarray:
        """
        Extract static features from most recent snapshot.

        Uses ALL available real data:
        - Macro indicators (VIX, Treasury, Dollar Index, Oil, Gold)
        - Fundamental ratios (PE, PB, PS, ROE, margins, etc.)
        - Sector (categorical)

        Parameters
        ----------
        snapshot : tuple
            Most recent snapshot row - see load_training_data() for full field list
        sector : str
            Company sector

        Returns
        -------
        np.ndarray
            Static feature vector
        """
        features = []

        # Indices: symbol(0), sector(1), date(2), vix(3), treasury(4), dollar(5), oil(6), gold(7),
        # pe_ratio(8), pb_ratio(9), ps_ratio(10), profit_margins(11), operating_margins(12),
        # return_on_equity(13), revenue_growth(14), earnings_growth(15), debt_to_equity(16),
        # current_ratio(17), trailing_eps(18), book_value(19), free_cashflow(20),
        # operating_cashflow(21), market_cap(22), id(23)

        # Macro indicators (5 features)
        features.extend([
            snapshot[3] if snapshot[3] is not None else 20.0,  # VIX
            snapshot[4] if snapshot[4] is not None else 3.0,  # Treasury 10Y
            snapshot[5] if snapshot[5] is not None else 100.0,  # Dollar Index
            snapshot[6] if snapshot[6] is not None else 70.0,  # Oil price
            snapshot[7] if snapshot[7] is not None else 1800.0,  # Gold price
        ])

        # Fundamental features (14 features)
        # Valuation ratios (capped to reasonable ranges to handle outliers)
        pe_ratio = snapshot[8] if snapshot[8] is not None else 20.0
        features.append(min(max(pe_ratio, -50.0), 100.0))  # PE ratio (clipped)

        pb_ratio = snapshot[9] if snapshot[9] is not None else 3.0
        features.append(min(max(pb_ratio, 0.0), 20.0))  # PB ratio (clipped)

        ps_ratio = snapshot[10] if snapshot[10] is not None else 2.0
        features.append(min(max(ps_ratio, 0.0), 20.0))  # PS ratio (clipped)

        # Profitability metrics (as decimals, e.g. 0.15 = 15%)
        features.append(snapshot[11] if snapshot[11] is not None else 0.10)  # Profit margins
        features.append(snapshot[12] if snapshot[12] is not None else 0.15)  # Operating margins
        features.append(snapshot[13] if snapshot[13] is not None else 0.10)  # ROE

        # Growth metrics (as decimals, e.g. 0.10 = 10% growth)
        revenue_growth = snapshot[14] if snapshot[14] is not None else 0.05
        features.append(min(max(revenue_growth, -0.5), 2.0))  # Revenue growth (clipped)

        earnings_growth = snapshot[15] if snapshot[15] is not None else 0.05
        features.append(min(max(earnings_growth, -1.0), 3.0))  # Earnings growth (clipped)

        # Financial health
        debt_to_equity = snapshot[16] if snapshot[16] is not None else 0.5
        features.append(min(max(debt_to_equity, 0.0), 5.0))  # Debt-to-equity (clipped)

        features.append(snapshot[17] if snapshot[17] is not None else 1.5)  # Current ratio

        # Per-share metrics (normalized by price from price_history)
        # Note: For now using raw values, could normalize later if needed
        features.append(snapshot[18] if snapshot[18] is not None else 0.0)  # Trailing EPS
        features.append(snapshot[19] if snapshot[19] is not None else 0.0)  # Book value

        # Cash flow metrics (normalized by market cap)
        market_cap = snapshot[22] if snapshot[22] is not None and snapshot[22] > 0 else 1e9

        free_cashflow = snapshot[20] if snapshot[20] is not None else 0.0
        features.append(free_cashflow / market_cap)  # FCF yield

        operating_cashflow = snapshot[21] if snapshot[21] is not None else 0.0
        features.append(operating_cashflow / market_cap)  # OCF yield

        # Sector one-hot encoding (11 features)
        sectors = [
            'Technology', 'Healthcare', 'Financial Services', 'Consumer Cyclical',
            'Industrials', 'Communication Services', 'Consumer Defensive',
            'Energy', 'Utilities', 'Real Estate', 'Basic Materials'
        ]
        for s in sectors:
            features.append(1.0 if sector == s else 0.0)

        return np.array(features)

    def _stratified_split(
        self,
        samples: List[dict],
        train_end_year: int = 2020,
        val_year: int = 2021,
        test_year: int = 2022
    ) -> Tuple[List, List, List]:
        """
        Split data chronologically to prevent data leakage.

        Parameters
        ----------
        samples : List[dict]
            All samples with metadata
        train_end_year : int
            Last year to include in training (default: 2020)
        val_year : int
            Year to use for validation (default: 2021)
        test_year : int
            Year to use for testing (default: 2022)

        Returns
        -------
        Tuple[List, List, List]
            (train, val, test) samples as list of (temporal, static, target) tuples
        """
        train_samples = []
        val_samples = []
        test_samples = []

        for sample in samples:
            year = int(sample['date'][:4])

            if year <= train_end_year:
                train_samples.append(sample)
            elif year == val_year:
                val_samples.append(sample)
            elif year == test_year:
                test_samples.append(sample)
            # Samples after test_year are ignored (no forward returns yet)

        def to_tuples(sample_list):
            return [(s['temporal'], s['static'], s['target']) for s in sample_list]

        return to_tuples(train_samples), to_tuples(val_samples), to_tuples(test_samples)

    def train(
        self,
        train_samples: List,
        val_samples: List,
        epochs: int = 100,
        batch_size: int = 32,
        learning_rate: float = 0.001
    ):
        """
        Train the model.

        Parameters
        ----------
        train_samples : List
            Training samples
        val_samples : List
            Validation samples
        epochs : int
            Number of training epochs
        batch_size : int
            Batch size
        learning_rate : float
            Learning rate
        """
        logger.info('Initializing model...')

        # Determine feature dimensions from first sample
        # Temporal: 17 features (4 price + 5 macro + 8 fundamental over time)
        # Static: 30 features (5 macro + 14 fundamental + 11 sector one-hot)
        temporal_dim = train_samples[0][0].shape[1]
        static_dim = train_samples[0][1].shape[0]

        logger.info(f'Feature dimensions: temporal={temporal_dim}, static={static_dim}')
        logger.info('Expected: temporal=17 (4 price + 5 macro + 8 fundamental), static=30 (5 macro + 14 fundamental + 11 sectors)')

        self.model = LSTMTransformerNetwork(
            temporal_features=temporal_dim,
            static_features=static_dim
        ).to(self.device)

        # Create data loaders
        train_dataset = StockSnapshotDataset(train_samples)
        val_dataset = StockSnapshotDataset(val_samples)

        train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, drop_last=True)
        val_loader = DataLoader(val_dataset, batch_size=batch_size, drop_last=True)

        # Loss and optimizer
        criterion = nn.HuberLoss()  # Robust to outliers
        optimizer = torch.optim.Adam(self.model.parameters(), lr=learning_rate, weight_decay=1e-5)

        # Training loop
        best_val_loss = float('inf')
        patience = 10
        patience_counter = 0

        for epoch in range(epochs):
            # Train
            self.model.train()
            train_loss = 0.0

            for temporal, static, target in train_loader:
                temporal = temporal.to(self.device)
                static = static.to(self.device)
                target = target.to(self.device)

                optimizer.zero_grad()
                output = self.model(temporal, static)
                loss = criterion(output, target)
                loss.backward()
                optimizer.step()

                train_loss += loss.item()

            train_loss /= len(train_loader)

            # Validate
            self.model.eval()
            val_loss = 0.0

            with torch.no_grad():
                for temporal, static, target in val_loader:
                    temporal = temporal.to(self.device)
                    static = static.to(self.device)
                    target = target.to(self.device)

                    output = self.model(temporal, static)
                    loss = criterion(output, target)
                    val_loss += loss.item()

            val_loss /= len(val_loader)

            logger.info(f'Epoch {epoch+1}/{epochs} - Train Loss: {train_loss:.4f}, Val Loss: {val_loss:.4f}')

            # Early stopping
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                patience_counter = 0
                # Save best model with horizon-specific name
                self.save_model()
            else:
                patience_counter += 1
                if patience_counter >= patience:
                    logger.info(f'Early stopping at epoch {epoch+1}')
                    break

    def save_model(self):
        """Save model weights with horizon-specific filename."""
        filename = f'best_model_{self.target_horizon}.pt'
        save_path = Path(__file__).parent / filename
        torch.save(self.model.state_dict(), save_path)
        logger.info(f'Model saved to {save_path}')


def main():
    parser = argparse.ArgumentParser(description='Train single-horizon model')
    parser.add_argument('--epochs', type=int, default=100, help='Number of epochs')
    parser.add_argument('--batch-size', type=int, default=32, help='Batch size')
    parser.add_argument('--learning-rate', type=float, default=0.001, help='Learning rate')
    parser.add_argument('--target-horizon', type=str, default='1y',
                        help='Target prediction horizon (1m, 3m, 6m, 1y, 2y, 3y)')
    args = parser.parse_args()

    trainer = SingleHorizonTrainer(target_horizon=args.target_horizon)

    # Load data
    train_samples, val_samples, test_samples = trainer.load_training_data(
        target_horizon=args.target_horizon
    )

    # Train
    trainer.train(
        train_samples,
        val_samples,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate
    )

    logger.info(f'Training complete for {args.target_horizon} horizon!')


if __name__ == '__main__':
    main()
