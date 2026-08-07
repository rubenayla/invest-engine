#!/usr/bin/env python3
"""
Comprehensive Neural Network Training System
============================================

A robust training system for neural network valuation models that:
- Collects and caches 20 years of historical stock data (2004-2024)
- Implements incremental data collection for efficiency
- Uses smart sampling across diverse time periods and stocks
- Monitors training progress with early stopping
- Saves best model checkpoints automatically
- Provides detailed training metrics and correlations
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import yfinance as yf

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.invest.valuation.neural_network_model import NeuralNetworkValuationModel

# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class TrainingConfig:
    """Configuration for comprehensive neural network training.

    Attributes:
        start_year: Beginning year for historical data collection
        end_year: Ending year for historical data collection
        target_samples: Number of training samples to collect
        validation_split: Fraction of data for validation (0.0 to 1.0)
        test_split: Fraction of data for testing (0.0 to 1.0)
        batch_size: Number of samples per training batch
        initial_epochs: Epochs per training batch
        patience: Epochs without improvement before early stopping
        min_improvement: Minimum loss improvement to reset patience
        max_total_epochs: Maximum total epochs across all batches
        cache_file: Path to cache file for training data
        use_cache: Whether to use cached data if available
    """
    # Data collection parameters
    start_year: int = 2004
    end_year: int = 2024
    target_samples: int = 10000

    # Data split ratios
    validation_split: float = 0.2
    test_split: float = 0.1

    # Training parameters
    batch_size: int = 64
    initial_epochs: int = 25
    patience: int = 50
    min_improvement: float = 0.001
    max_total_epochs: int = 300

    # Cache configuration
    cache_file: str = 'models/neural_network/training/training_data_cache.json'
    use_cache: bool = True

    # Sampling parameters
    forward_return_months: int = 24  # 2-year forward returns
    min_trading_days: int = 730  # Minimum 2 years of trading history
    sample_generation_multiplier: int = 2  # Generate 2x samples for filtering


@dataclass
class TrainingProgress:
    """Track training progress for monitoring and early stopping.

    Attributes:
        epoch: Current epoch number
        train_loss: Training loss for this epoch
        val_loss: Validation loss for this epoch
        val_mae: Validation mean absolute error
        correlation: Correlation between predictions and actuals
        best_val_loss: Best validation loss so far
        epochs_without_improvement: Consecutive epochs without improvement
        should_stop: Whether training should stop
    """
    epoch: int
    train_loss: float
    val_loss: float
    val_mae: float
    correlation: float
    best_val_loss: float
    epochs_without_improvement: int
    should_stop: bool = False


# ============================================================================
# CONSTANTS
# ============================================================================

# Large-cap stocks with long trading history
LARGE_CAP_UNIVERSE = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'BRK-B',
    'JPM', 'JNJ', 'V', 'PG', 'UNH', 'HD', 'DIS', 'MA', 'PYPL', 'BAC',
    'ADBE', 'CRM', 'NFLX', 'XOM', 'PFE', 'CVX', 'ABBV', 'TMO', 'COST',
    'AVGO', 'PEP', 'WMT', 'ABT', 'MRK', 'NKE', 'ACN', 'LLY', 'ORCL',
    'DHR', 'VZ', 'QCOM', 'TXN', 'MDT', 'NEE', 'LIN', 'BMY', 'PM',
    'HON', 'T', 'UNP', 'LOW', 'IBM', 'AMD', 'INTC', 'GS', 'SPGI'
]

# Mid-cap and historically stable stocks
ADDITIONAL_UNIVERSE = [
    'CAT', 'MMM', 'AXP', 'WBA', 'GE', 'F', 'GM', 'KO', 'MCD', 'SBUX',
    'CMG', 'GILD', 'AMGN', 'BKNG', 'COP', 'SLB', 'HAL', 'MDLZ', 'MNST',
    'ZTS', 'MU', 'AMAT', 'ADI', 'KLAC', 'MRVL', 'FTNT', 'PANW', 'NOW'
]

# Complete training universe
TRAINING_UNIVERSE = LARGE_CAP_UNIVERSE + ADDITIONAL_UNIVERSE


# ============================================================================
# LOGGING SETUP
# ============================================================================

def setup_logging(log_file: str = 'models/neural_network/training/logs/comprehensive_training.log') -> logging.Logger:
    """Setup logging configuration with file and console output.

    Args:
        log_file: Path to log file

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)

    # Clear any existing handlers
    logger.handlers.clear()

    # Create formatters
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # File handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


logger = setup_logging()


# ============================================================================
# DATA COLLECTION
# ============================================================================

class DataCollector:
    """Handles historical stock data collection with caching support."""

    def __init__(self, config: TrainingConfig):
        """Initialize data collector.

        Args:
            config: Training configuration
        """
        self.config = config
        self.cache_path = Path(config.cache_file)
        self.stock_universe = TRAINING_UNIVERSE
        self._availability_map: Optional[Dict[str, Tuple[datetime, datetime]]] = None

    def collect_training_data(self) -> List[Tuple[str, Dict, float]]:
        """Collect training data with cache support.

        Returns:
            List of (ticker, data_dict, forward_return) tuples
        """
        logger.info(f'Collecting historical data from {self.config.start_year} to {self.config.end_year}')

        # Try loading from cache
        if self.config.use_cache:
            cached_data = self._load_and_validate_cache()
            if cached_data is not None:
                return cached_data

        # Collect new data
        samples = self._collect_new_samples([])

        # Save to cache
        if self.config.use_cache and samples:
            self._save_cache(samples)

        return samples

    def _load_and_validate_cache(self) -> Optional[List[Tuple[str, Dict, float]]]:
        """Load cached data if valid and sufficient.

        Returns:
            Cached samples if valid, None otherwise
        """
        if not self.cache_path.exists():
            return None

        try:
            with open(self.cache_path, 'r') as f:
                cache = json.load(f)

            logger.info(f'Loaded cache from {self.cache_path}')
            logger.info(f'Cache contains {cache["sample_count"]} samples')
            logger.info(f'Cache last updated: {cache["last_updated"]}')

            # Validate cache config
            cache_config = cache.get('config', {})
            if not self._is_cache_compatible(cache_config):
                logger.info('[WARNING]  Cache config mismatch, collecting new data')
                return None

            # Convert cache to training format
            samples = [
                (s['ticker'], s['data'], s['forward_return'])
                for s in cache['samples']
            ]

            # Check if we need more samples
            if len(samples) >= self.config.target_samples:
                logger.info('[OK] Using cached training data')
                logger.info(f'Loaded {self.config.target_samples} samples from cache')
                return samples[:self.config.target_samples]

            # Need incremental collection
            logger.info(f'[PROGRESS] Cache has {len(samples)} samples, need {self.config.target_samples}')
            logger.info(f'Collecting {self.config.target_samples - len(samples)} additional samples')

            # Collect additional samples
            additional_samples = self._collect_new_samples(samples)
            return additional_samples

        except Exception as e:
            logger.warning(f'Failed to load cache: {e}')
            return None

    def _is_cache_compatible(self, cache_config: Dict) -> bool:
        """Check if cached data is compatible with current config.

        Args:
            cache_config: Configuration from cache file

        Returns:
            True if compatible, False otherwise
        """
        return (
            cache_config.get('start_year') == self.config.start_year and
            cache_config.get('end_year') == self.config.end_year
        )

    def _save_cache(self, samples: List[Tuple[str, Dict, float]]) -> None:
        """Save training samples to cache file.

        Args:
            samples: Training samples to cache
        """
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)

            cache = {
                'last_updated': datetime.now().isoformat(),
                'sample_count': len(samples),
                'config': {
                    'start_year': self.config.start_year,
                    'end_year': self.config.end_year,
                    'target_samples': self.config.target_samples
                },
                'samples': [
                    {
                        'ticker': ticker,
                        'data': data,
                        'forward_return': forward_return
                    }
                    for ticker, data, forward_return in samples
                ]
            }

            with open(self.cache_path, 'w') as f:
                json.dump(cache, f, indent=2)

            logger.info(f'Saved {len(samples)} samples to cache: {self.cache_path}')

        except Exception as e:
            logger.warning(f'Failed to save cache: {e}')

    def _collect_new_samples(
        self,
        existing_samples: List[Tuple[str, Dict, float]]
    ) -> List[Tuple[str, Dict, float]]:
        """Collect new training samples.

        Args:
            existing_samples: Already collected samples to extend

        Returns:
            Combined list of existing and new samples
        """
        samples = list(existing_samples)
        needed_samples = self.config.target_samples - len(samples)

        if needed_samples <= 0:
            return samples[:self.config.target_samples]

        # Build availability map
        if self._availability_map is None:
            self._availability_map = self._build_stock_availability_map()

        if not self._availability_map:
            logger.error('No stocks available for training')
            return samples

        # Generate sample pairs
        stock_date_pairs = self._generate_sample_pairs(
            needed_samples * self.config.sample_generation_multiplier
        )

        logger.info(f'Generated {len(stock_date_pairs)} (stock, date) pairs from available trading periods')

        # Collect data for each pair
        for i, (ticker, sample_date) in enumerate(stock_date_pairs):
            if i % 100 == 0:
                logger.info(
                    f'Processing sample {i+1}/{len(stock_date_pairs)} '
                    f'({ticker} @ {sample_date.strftime("%Y-%m-%d")})'
                )

            # Collect sample data
            sample = self._collect_single_sample(ticker, sample_date)
            if sample:
                samples.append(sample)

            # Stop if we have enough
            if len(samples) >= self.config.target_samples:
                break

        logger.info(f'Collected {len(samples)} total training samples')
        return samples

    def _build_stock_availability_map(self) -> Dict[str, Tuple[datetime, datetime]]:
        """Build map of stock trading date ranges.

        Returns:
            Dictionary mapping ticker to (first_date, last_date) tuples
        """
        logger.info('Building stock availability map...')
        availability_map = {}

        for ticker in self.stock_universe:
            try:
                stock = yf.Ticker(ticker)
                hist = stock.history(period='max')

                if hist.empty:
                    continue

                # Extract date range
                hist_index = hist.index
                if hist_index.tz is not None:
                    hist_index = hist_index.tz_localize(None)

                first_date = hist_index[0].to_pydatetime()
                last_date = hist_index[-1].to_pydatetime()

                # Check minimum trading history
                if (last_date - first_date).days >= self.config.min_trading_days:
                    availability_map[ticker] = (first_date, last_date)

            except Exception as e:
                logger.debug(f'Error checking availability for {ticker}: {e}')
                continue

        logger.info(f'Found {len(availability_map)} stocks with sufficient trading history')
        return availability_map

    def _generate_sample_pairs(self, count: int) -> List[Tuple[str, datetime]]:
        """Generate random (stock, date) pairs for sampling.

        Args:
            count: Number of pairs to generate

        Returns:
            List of (ticker, date) tuples
        """
        pairs = []
        period_start = datetime(self.config.start_year, 1, 1)
        period_end = datetime(self.config.end_year, 1, 1)

        for _ in range(count):
            # Random stock selection
            ticker = random.choice(list(self._availability_map.keys()))
            stock_start, stock_end = self._availability_map[ticker]

            # Find valid date range
            valid_start = max(period_start, stock_start)
            valid_end = min(period_end, stock_end)

            # Leave room for forward returns
            forward_days = self.config.forward_return_months * 30
            valid_end = valid_end - timedelta(days=forward_days)

            if valid_end <= valid_start:
                continue

            # Generate random date
            total_days = (valid_end - valid_start).days
            if total_days <= 0:
                continue

            random_days = random.randint(0, total_days)
            sample_date = valid_start + timedelta(days=random_days)

            pairs.append((ticker, sample_date))

        # Sort by date for better cache locality
        pairs.sort(key=lambda x: x[1])
        return pairs

    def _collect_single_sample(
        self,
        ticker: str,
        sample_date: datetime
    ) -> Optional[Tuple[str, Dict, float]]:
        """Collect data for a single training sample.

        Args:
            ticker: Stock ticker symbol
            sample_date: Date to sample from

        Returns:
            (ticker, data_dict, forward_return) tuple or None if failed
        """
        try:
            # Get stock data
            stock_data = self._get_historical_stock_data(ticker, sample_date)
            if not stock_data:
                return None

            # Calculate forward return
            forward_return = self._calculate_forward_return(
                ticker,
                sample_date,
                self.config.forward_return_months
            )
            if forward_return is None:
                return None

            # Format for model
            model_data = {
                'info': stock_data,
                'financials': None,
                'balance_sheet': None,
                'cashflow': None
            }

            return (ticker, model_data, forward_return)

        except Exception as e:
            logger.debug(f'Error collecting sample for {ticker} at {sample_date}: {e}')
            return None

    def _get_historical_stock_data(
        self,
        ticker: str,
        date: datetime
    ) -> Optional[Dict[str, Any]]:
        """Get historical stock data for a specific date.

        Args:
            ticker: Stock ticker symbol
            date: Date to get data for

        Returns:
            Dictionary of stock data or None if unavailable
        """
        try:
            stock = yf.Ticker(ticker)

            # Get price around the target date
            start_date = date - timedelta(days=10)
            end_date = date + timedelta(days=30)
            hist = stock.history(start=start_date, end=end_date)

            if hist.empty:
                return None

            # Get closest price
            price = hist['Close'].iloc[-1] if not hist.empty else None
            if not price or price <= 0:
                return None

            # Get fundamental data (using current as approximation)
            info = stock.info
            if not info or not info.get('marketCap'):
                return None

            # Prepare data dictionary
            stock_data = {
                'currentPrice': float(price),
                'marketCap': info.get('marketCap', 0),
                'enterpriseValue': info.get('enterpriseValue', 0),
                'totalRevenue': info.get('totalRevenue', 0),
                'trailingPE': info.get('trailingPE', 15),
                'forwardPE': info.get('forwardPE', 15),
                'priceToBook': info.get('priceToBook', 2),
                'debtToEquity': info.get('debtToEquity', 50),
                'returnOnEquity': info.get('returnOnEquity', 0.15),
                'grossMargins': info.get('grossMargins', 0.3),
                'operatingMargins': info.get('operatingMargins', 0.15),
                'sector': info.get('sector', 'Technology'),
                'industry': info.get('industry', 'Unknown')
            }

            return stock_data

        except Exception as e:
            logger.debug(f'Error getting historical data for {ticker}: {e}')
            return None

    def _calculate_forward_return(
        self,
        ticker: str,
        start_date: datetime,
        months: int
    ) -> Optional[float]:
        """Calculate forward return from start date.

        Args:
            ticker: Stock ticker symbol
            start_date: Starting date for return calculation
            months: Number of months forward

        Returns:
            Forward return as decimal (e.g., 0.10 for 10%) or None
        """
        try:
            end_date = start_date + timedelta(days=months * 30)

            stock = yf.Ticker(ticker)
            hist = stock.history(
                start=start_date - timedelta(days=10),
                end=end_date + timedelta(days=10)
            )

            # Need sufficient data points
            if len(hist) < months * 15:
                return None

            # Handle timezone-aware indices
            hist_index = hist.index
            if hist_index.tz is not None:
                hist_index = hist_index.tz_localize(None)

            # Find start and end prices
            start_prices = hist[hist_index >= start_date]['Close']
            end_prices = hist[hist_index >= end_date]['Close']

            if len(start_prices) == 0 or len(end_prices) == 0:
                return None

            start_price = start_prices.iloc[0]
            end_price = end_prices.iloc[0]

            if start_price <= 0:
                return None

            return (end_price - start_price) / start_price

        except Exception as e:
            logger.debug(f'Error calculating forward return for {ticker}: {e}')
            return None


# ============================================================================
# TRAINING
# ============================================================================

class NeuralTrainer:
    """Handles neural network training with progress monitoring."""

    def __init__(self, config: TrainingConfig):
        """Initialize trainer.

        Args:
            config: Training configuration
        """
        self.config = config
        self.progress_history: List[TrainingProgress] = []
        self.best_model_path: Optional[Path] = None

    def train(
        self,
        training_data: List[Tuple[str, Dict, float]]
    ) -> Dict[str, Any]:
        """Train neural network with progress monitoring.

        Args:
            training_data: List of (ticker, data, forward_return) tuples

        Returns:
            Dictionary of training results
        """
        logger.info(f'Starting comprehensive training with {len(training_data)} samples')

        # Initialize model
        model = NeuralNetworkValuationModel(time_horizon='comprehensive_2year')

        # Split data
        train_data, val_data, test_data = self._split_data(training_data)
        logger.info(
            f'Data split: Train={len(train_data)}, '
            f'Val={len(val_data)}, Test={len(test_data)}'
        )

        # Training loop
        results = self._training_loop(model, train_data, val_data)

        # Final test evaluation
        if test_data and self.best_model_path and self.best_model_path.exists():
            results['test_correlation'] = self._evaluate_test_set(test_data)

        # Save results
        self._save_results(results)

        return results

    def _split_data(
        self,
        data: List[Tuple]
    ) -> Tuple[List[Tuple], List[Tuple], List[Tuple]]:
        """Split data into train, validation, and test sets.

        Args:
            data: Full dataset

        Returns:
            Tuple of (train_data, val_data, test_data)
        """
        random.shuffle(data)
        n_samples = len(data)
        n_train = int(n_samples * (1 - self.config.validation_split - self.config.test_split))
        n_val = int(n_samples * self.config.validation_split)

        train_data = data[:n_train]
        val_data = data[n_train:n_train + n_val]
        test_data = data[n_train + n_val:]

        return train_data, val_data, test_data

    def _training_loop(
        self,
        model: NeuralNetworkValuationModel,
        train_data: List[Tuple],
        val_data: List[Tuple]
    ) -> Dict[str, Any]:
        """Main training loop with early stopping.

        Args:
            model: Model to train
            train_data: Training data
            val_data: Validation data

        Returns:
            Training results dictionary
        """
        best_val_loss = float('inf')
        epochs_without_improvement = 0
        total_epochs = 0

        results = {
            'total_epochs': 0,
            'best_val_loss': float('inf'),
            'final_train_loss': 0,
            'final_val_loss': 0,
            'val_mae': 0,
            'test_correlation': 0,
            'training_history': [],
            'early_stopped': False
        }

        logger.info(f'Starting initial training phase: {self.config.initial_epochs} epochs')

        try:
            while total_epochs < self.config.max_total_epochs:
                # Train batch
                batch_results = self._train_batch(
                    model,
                    train_data,
                    val_data,
                    total_epochs
                )

                # Update progress
                total_epochs += batch_results['epochs']
                current_val_loss = batch_results['val_loss']

                # Check improvement
                improvement = best_val_loss - current_val_loss
                if improvement > self.config.min_improvement:
                    best_val_loss = current_val_loss
                    epochs_without_improvement = 0
                    self._save_checkpoint(model, total_epochs)
                    self._log_improvement(total_epochs, current_val_loss, improvement, batch_results)
                else:
                    epochs_without_improvement += batch_results['epochs']
                    self._log_no_improvement(total_epochs, current_val_loss, best_val_loss, epochs_without_improvement)

                # Progress report
                self._log_progress(total_epochs, batch_results, best_val_loss)

                # Update results
                results.update({
                    'total_epochs': total_epochs,
                    'best_val_loss': best_val_loss,
                    'final_train_loss': batch_results['train_loss'],
                    'final_val_loss': batch_results['val_loss'],
                    'val_mae': batch_results['val_mae']
                })

                # Early stopping check
                if epochs_without_improvement >= self.config.patience:
                    logger.info(
                        f'[STOP] Early stopping triggered after {epochs_without_improvement} '
                        f'epochs without improvement'
                    )
                    results['early_stopped'] = True
                    break

                time.sleep(1)  # Prevent log flooding

        except KeyboardInterrupt:
            logger.info('Training interrupted by user')
        except Exception as e:
            logger.error(f'Training error: {e}')
            raise

        return results

    def _train_batch(
        self,
        model: NeuralNetworkValuationModel,
        train_data: List[Tuple],
        val_data: List[Tuple],
        current_epoch: int
    ) -> Dict[str, Any]:
        """Train model for one batch of epochs.

        Args:
            model: Model to train
            train_data: Training data
            val_data: Validation data
            current_epoch: Current total epoch count

        Returns:
            Batch training results
        """
        epochs_this_batch = min(
            self.config.initial_epochs,
            self.config.max_total_epochs - current_epoch
        )

        # Combine data for model's internal split
        combined_data = train_data + val_data

        # Train
        batch_results = model.train_model(
            combined_data,
            validation_split=0.2,
            epochs=epochs_this_batch
        )

        # Calculate correlation
        correlation = self._calculate_correlation(model, val_data)

        return {
            'epochs': epochs_this_batch,
            'train_loss': batch_results.get('final_train_loss', float('inf')),
            'val_loss': batch_results.get('final_val_loss', float('inf')),
            'val_mae': batch_results.get('val_mae', float('inf')),
            'correlation': correlation
        }

    def _save_checkpoint(self, model: NeuralNetworkValuationModel, epoch: int) -> None:
        """Save model checkpoint.

        Args:
            model: Model to save
            epoch: Current epoch number
        """
        checkpoint_path = Path(f'best_comprehensive_nn_2year_{epoch}epochs.pt')
        model.save_model(checkpoint_path)
        self.best_model_path = checkpoint_path

    def _calculate_correlation(
        self,
        model: NeuralNetworkValuationModel,
        data: List[Tuple]
    ) -> float:
        """Calculate correlation between predictions and actuals.

        Args:
            model: Trained model
            data: Validation or test data

        Returns:
            Correlation coefficient
        """
        try:
            predictions = []
            actuals = []

            for ticker, stock_data, actual_return in data:
                try:
                    result = model._calculate_valuation(ticker, stock_data)
                    if result and result.fair_value and result.current_price:
                        predicted_return = (result.fair_value - result.current_price) / result.current_price
                        predictions.append(predicted_return)
                        actuals.append(actual_return)
                except Exception:
                    continue

            if len(predictions) < 10:
                return 0.0

            return np.corrcoef(predictions, actuals)[0, 1] if len(predictions) > 1 else 0.0

        except Exception as e:
            logger.warning(f'Error calculating correlation: {e}')
            return 0.0

    def _evaluate_test_set(self, test_data: List[Tuple]) -> float:
        """Evaluate model on test set.

        Args:
            test_data: Test dataset

        Returns:
            Test correlation
        """
        try:
            best_model = NeuralNetworkValuationModel(model_path=self.best_model_path)
            test_correlation = self._calculate_correlation(best_model, test_data)
            logger.info(f'[RESULT] Final test correlation: {test_correlation:.3f}')
            return test_correlation
        except Exception as e:
            logger.warning(f'Error calculating test correlation: {e}')
            return 0.0

    def _save_results(self, results: Dict[str, Any]) -> None:
        """Save training results to file.

        Args:
            results: Training results dictionary
        """
        results_path = Path(
            f'comprehensive_training_results_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        )

        with open(results_path, 'w') as f:
            json.dump(results, f, indent=2, default=str)

        logger.info(f'[FILE] Training results saved: {results_path}')

    def _log_improvement(
        self,
        epoch: int,
        val_loss: float,
        improvement: float,
        batch_results: Dict
    ) -> None:
        """Log improvement in validation loss."""
        logger.info(f'[OK] Improvement found at epoch {epoch}!')
        logger.info(f'   Val Loss: {val_loss:.4f} (↓{improvement:.4f})')
        logger.info(f'   Correlation: {batch_results["correlation"]:.3f}')
        logger.info(f'   Model saved: {self.best_model_path}')

    def _log_no_improvement(
        self,
        epoch: int,
        val_loss: float,
        best_val_loss: float,
        epochs_without_improvement: int
    ) -> None:
        """Log lack of improvement."""
        logger.info(f'[WARNING]  No significant improvement at epoch {epoch}')
        logger.info(f'   Val Loss: {val_loss:.4f} (best: {best_val_loss:.4f})')
        logger.info(f'   Epochs without improvement: {epochs_without_improvement}')

    def _log_progress(
        self,
        epoch: int,
        batch_results: Dict,
        best_val_loss: float
    ) -> None:
        """Log training progress."""
        logger.info(f'[INFO] Progress Report - Epoch {epoch}/{self.config.max_total_epochs}')
        logger.info(f'   Train Loss: {batch_results["train_loss"]:.4f}')
        logger.info(f'   Val Loss: {batch_results["val_loss"]:.4f}')
        logger.info(f'   Val MAE: {batch_results["val_mae"]:.4f}')
        logger.info(f'   Correlation: {batch_results["correlation"]:.3f}')
        logger.info(f'   Best Val Loss: {best_val_loss:.4f}')


# ============================================================================
# MAIN ORCHESTRATOR
# ============================================================================

class ComprehensiveTrainingOrchestrator:
    """Orchestrates the complete training pipeline."""

    def __init__(self, config: TrainingConfig):
        """Initialize orchestrator.

        Args:
            config: Training configuration
        """
        self.config = config
        self.data_collector = DataCollector(config)
        self.trainer = NeuralTrainer(config)

    def run(self) -> Dict[str, Any]:
        """Run the complete training pipeline.

        Returns:
            Training results dictionary
        """
        self._log_header()
        start_time = time.time()

        try:
            # Collect data
            logger.info('\n[INFO] Step 1: Collecting Historical Data')
            training_data = self.data_collector.collect_training_data()

            if len(training_data) < 100:
                raise ValueError(f'Insufficient training data: {len(training_data)} samples')

            # Train model
            logger.info('\n[TRAIN] Step 2: Training Neural Network')
            results = self.trainer.train(training_data)

            # Finalize
            training_time = time.time() - start_time
            results['training_time'] = training_time

            self._log_summary(results)
            self._copy_best_model()

            return results

        except Exception as e:
            logger.error(f'Training failed: {e}')
            raise

    def _log_header(self) -> None:
        """Log training header information."""
        logger.info('[START] Starting Comprehensive Neural Network Training')
        logger.info('=' * 60)
        logger.info(f'Target: {self.config.target_samples} samples from {self.config.start_year}-{self.config.end_year}')
        logger.info(f'Universe: {len(TRAINING_UNIVERSE)} stocks')
        logger.info(f'Max epochs: {self.config.max_total_epochs}, Patience: {self.config.patience}')

    def _log_summary(self, results: Dict[str, Any]) -> None:
        """Log training summary.

        Args:
            results: Training results
        """
        logger.info('\n[COMPLETE] Training Complete!')
        logger.info('=' * 60)
        logger.info(f'Training time: {results["training_time"]/3600:.1f} hours')
        logger.info(f'Total epochs: {results["total_epochs"]}')
        logger.info(f'Best validation loss: {results["best_val_loss"]:.4f}')
        logger.info(f'Test correlation: {results.get("test_correlation", 0):.3f}')
        logger.info(f'Early stopped: {results.get("early_stopped", False)}')

    def _copy_best_model(self) -> None:
        """Copy best model to standard location."""
        if self.trainer.best_model_path and self.trainer.best_model_path.exists():
            final_path = Path('trained_nn_2year_comprehensive.pt')
            shutil.copy2(self.trainer.best_model_path, final_path)
            logger.info(f'Best model: {self.trainer.best_model_path}')
            logger.info(f'Model copied to: {final_path}')


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

async def main():
    """Main training function."""
    config = TrainingConfig()
    orchestrator = ComprehensiveTrainingOrchestrator(config)

    try:
        results = orchestrator.run()

        # Print summary
        print('\n[RESULT] COMPREHENSIVE TRAINING SUMMARY')
        print('=' * 50)
        print('Final Results:')
        print(f'  • Training Time: {results.get("training_time", 0)/3600:.1f} hours')
        print(f'  • Total Epochs: {results["total_epochs"]}')
        print(f'  • Best Val Loss: {results["best_val_loss"]:.4f}')
        print(f'  • Test Correlation: {results.get("test_correlation", 0):.3f}')
        print(f'  • Early Stopped: {results.get("early_stopped", False)}')

        # Correlation assessment
        test_corr = results.get("test_correlation", 0)
        if test_corr > 0.4:
            print('[EXCELLENT] Excellent correlation achieved!')
        elif test_corr > 0.2:
            print('[PROGRESS] Good correlation achieved!')
        else:
            print('[WARNING]  Correlation could be improved with more data/tuning')

    except KeyboardInterrupt:
        print('\n[STOP] Training interrupted by user')
    except Exception as e:
        print(f'\n[ERROR] Training failed: {e}')
        raise


if __name__ == '__main__':
    asyncio.run(main())
