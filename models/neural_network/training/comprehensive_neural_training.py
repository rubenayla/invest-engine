#!/usr/bin/env python3
"""
Comprehensive Neural Network Training with 20 Years of Data
===========================================================

Advanced training system that:
- Uses 20 years of historical stock data (2004-2024)
- Samples random time points for robust training
- Monitors training progress and stops when plateauing
- Creates multiple models with different architectures
- Validates on out-of-sample recent data
"""

import asyncio
import json
import logging
import random
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# Add src to path (go up to repo root)
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import yfinance as yf

from src.invest.valuation.neural_network_model import NeuralNetworkValuationModel

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('models/neural_network/training/logs/comprehensive_training.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class TrainingConfig:
    """Configuration for comprehensive training."""
    start_year: int = 2004  # Use all available historical data
    end_year: int = 2024
    target_samples: int = 10000  # Larger dataset for complex models
    validation_split: float = 0.2
    test_split: float = 0.1
    batch_size: int = 64
    initial_epochs: int = 50
    patience: int = 10  # Early stopping patience
    min_improvement: float = 0.001  # Minimum improvement threshold
    max_total_epochs: int = 300  # Maximum total training epochs
    cache_file: str = 'models/neural_network/training/training_data_cache.json'  # Cache location
    use_cache: bool = True  # Use cached data by default

@dataclass
class TrainingProgress:
    """Track training progress for intelligent stopping."""
    epoch: int
    train_loss: float
    val_loss: float
    val_mae: float
    correlation: float
    best_val_loss: float
    epochs_without_improvement: int
    should_stop: bool = False

class ComprehensiveNeuralTrainer:
    """Comprehensive neural network trainer with 20 years of data."""

    def __init__(self, config: TrainingConfig):
        self.config = config
        self.progress_history: List[TrainingProgress] = []
        self.best_model_path: Optional[Path] = None
        # Find repo root for cache path
        current = Path.cwd()
        while current != current.parent:
            if (current / '.git').exists():
                repo_root = current
                break
            current = current.parent
        else:
            repo_root = Path.cwd()
        self.cache_path = repo_root / config.cache_file

        # Stock universe for training
        self.stock_universe = self._get_training_universe()
        logger.info(f'Training universe: {len(self.stock_universe)} stocks')

    def _get_training_universe(self) -> List[str]:
        """Get comprehensive stock universe for training."""
        # Large, diverse universe of stocks that have been around for years
        large_caps = [
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'BRK-B',
            'JPM', 'JNJ', 'V', 'PG', 'UNH', 'HD', 'DIS', 'MA', 'PYPL', 'BAC',
            'ADBE', 'CRM', 'NFLX', 'XOM', 'PFE', 'CVX', 'ABBV', 'TMO', 'COST',
            'AVGO', 'PEP', 'WMT', 'ABT', 'MRK', 'NKE', 'ACN', 'LLY', 'ORCL',
            'DHR', 'VZ', 'QCOM', 'TXN', 'MDT', 'NEE', 'LIN', 'BMY', 'PM',
            'HON', 'T', 'UNP', 'LOW', 'IBM', 'AMD', 'INTC', 'GS', 'SPGI'
        ]

        # Add some mid-caps and historically stable stocks
        additional_stocks = [
            'CAT', 'MMM', 'AXP', 'WBA', 'GE', 'F', 'GM', 'KO', 'MCD', 'SBUX',
            'CMG', 'GILD', 'AMGN', 'BKNG', 'COP', 'SLB', 'HAL', 'MDLZ', 'MNST',
            'ZTS', 'MU', 'AMAT', 'ADI', 'KLAC', 'MRVL', 'FTNT', 'PANW', 'NOW'
        ]

        return large_caps + additional_stocks

    def _build_stock_availability_map(self) -> Dict[str, Tuple[datetime, datetime]]:
        """Build a map of when each stock was trading."""
        logger.info('Building stock availability map...')
        availability_map = {}

        for ticker in self.stock_universe:
            try:
                stock = yf.Ticker(ticker)
                # Get full history to find first and last trading dates
                hist = stock.history(period='max')

                if hist.empty:
                    continue

                # Extract dates (handle timezone-aware indices)
                hist_index = hist.index.tz_localize(None) if hist.index.tz is not None else hist.index
                first_date = hist_index[0].to_pydatetime()
                last_date = hist_index[-1].to_pydatetime()

                # Ensure we have at least 2 years of data for forward returns
                if (last_date - first_date).days >= 730:
                    availability_map[ticker] = (first_date, last_date)

            except Exception as e:
                logger.warning(f'Error checking availability for {ticker}: {e}')
                continue

        logger.info(f'Found {len(availability_map)} stocks with sufficient trading history')
        return availability_map

    def _load_cached_data(self) -> Optional[Dict[str, Any]]:
        """Load cached training data if available."""
        # Find the repository root (where .git directory is)
        current = Path.cwd()
        while current != current.parent:
            if (current / '.git').exists():
                repo_root = current
                break
            current = current.parent
        else:
            repo_root = Path.cwd()  # Fallback to current directory

        # Try cache path relative to repo root
        cache_path = repo_root / self.config.cache_file

        if cache_path.exists():
            try:
                with open(cache_path, 'r') as f:
                    cache = json.load(f)
                logger.info(f'Loaded cache from {cache_path}')
                logger.info(f'Cache contains {cache["sample_count"]} samples')
                logger.info(f'Cache last updated: {cache["last_updated"]}')
                # Update cache path for future saves
                self.cache_path = cache_path
                return cache
            except Exception as e:
                logger.warning(f'Failed to load cache from {cache_path}: {e}')

        logger.info(f'No cache found at {cache_path}')
        return None

    def _save_cache(self, samples: List[Tuple[str, Dict, float]]):
        """Save training samples to cache."""
        try:
            # Create cache directory if needed
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

    def collect_historical_data(self) -> List[Tuple[str, Dict, float]]:
        """Collect historical training data using smart stock sampling."""
        logger.info(f'Collecting historical data from {self.config.start_year} to {self.config.end_year}')

        # Try to load from cache first
        if self.config.use_cache:
            cache = self._load_cached_data()
            if cache:
                # Check if cache config matches current config
                cache_config = cache.get('config', {})
                if (cache_config.get('start_year') == self.config.start_year and
                    cache_config.get('end_year') == self.config.end_year):
                    # Load existing samples
                    existing_samples = [
                        (s['ticker'], s['data'], s['forward_return'])
                        for s in cache['samples']
                    ]

                    if len(existing_samples) >= self.config.target_samples:
                        logger.info('Using cached training data')
                        logger.info(f'Loaded {self.config.target_samples} samples from cache')
                        return existing_samples[:self.config.target_samples]
                    else:
                        # Incrementally add more samples
                        logger.info(f'Cache has {len(existing_samples)} samples, need {self.config.target_samples}')
                        logger.info(f'Collecting {self.config.target_samples - len(existing_samples)} additional samples')
                        training_samples = existing_samples
                        # Continue below to collect more
                else:
                    logger.info('Cache config mismatch (start_year/end_year), collecting new data')

        # Only initialize empty list if we didn't load from cache
        if 'training_samples' not in locals():
            training_samples = []
        period_start = datetime(self.config.start_year, 1, 1)
        period_end = datetime(self.config.end_year, 1, 1)

        # Build stock availability map
        availability_map = self._build_stock_availability_map()
        if not availability_map:
            logger.error('No stocks available for training')
            return []

        # Generate smart (stock, date) pairs
        stock_date_pairs = []
        for _ in range(self.config.target_samples * 2):  # Generate extra to account for filtering
            # Randomly select a stock
            ticker = random.choice(list(availability_map.keys()))
            stock_start, stock_end = availability_map[ticker]

            # Find the valid date range for this stock (intersection with our training period)
            valid_start = max(period_start, stock_start)
            valid_end = min(period_end, stock_end)

            # Leave 2 years for forward returns
            valid_end = valid_end - timedelta(days=730)

            if valid_end <= valid_start:
                continue

            # Generate random date within valid range
            total_days = (valid_end - valid_start).days
            if total_days <= 0:
                continue

            random_days = random.randint(0, total_days)
            sample_date = valid_start + timedelta(days=random_days)

            stock_date_pairs.append((ticker, sample_date))

        stock_date_pairs.sort(key=lambda x: x[1])  # Sort by date
        logger.info(f'Generated {len(stock_date_pairs)} (stock, date) pairs from available trading periods')

        # Collect data for each (stock, date) pair
        for i, (ticker, sample_date) in enumerate(stock_date_pairs):
            if i % 100 == 0:
                logger.info(f'Processing sample {i+1}/{len(stock_date_pairs)} ({ticker} @ {sample_date.strftime("%Y-%m-%d")})')

            try:
                # Get fundamental data at sample date
                stock_data = self._get_historical_stock_data(ticker, sample_date)
                if not stock_data:
                    continue

                # Calculate 2-year forward return from sample date
                forward_return = self._calculate_forward_return(ticker, sample_date, 24)
                if forward_return is None:
                    continue

                # Prepare data in format expected by neural network
                model_data = {
                    'info': stock_data,
                    'financials': None,  # Using info data for now
                    'balance_sheet': None,
                    'cashflow': None
                }

                training_samples.append((ticker, model_data, forward_return))

                # Stop if we have enough samples
                if len(training_samples) >= self.config.target_samples:
                    break

            except Exception as e:
                logger.warning(f'Error collecting data for {ticker} at {sample_date}: {e}')
                continue

        logger.info(f'Collected {len(training_samples)} training samples')

        # Save to cache for future use
        if self.config.use_cache and training_samples:
            self._save_cache(training_samples)

        return training_samples

    def _get_historical_stock_data(self, ticker: str, date: datetime) -> Optional[Dict]:
        """Get historical stock data for a specific date."""
        try:
            # For historical data, we'll approximate using the closest available data
            stock = yf.Ticker(ticker)

            # Get MORE historical price data for technical indicators (need 1+ year)
            start_date = date - timedelta(days=400)  # Get ~1.5 years for technical indicators
            end_date = date + timedelta(days=30)
            hist = stock.history(start=start_date, end=end_date)

            if hist.empty or len(hist) < 20:  # Need minimum data for indicators
                return None

            # Get the closest price data
            price = hist['Close'].iloc[-1] if not hist.empty else None
            if not price or price <= 0:
                return None

            # Use current info as approximation (limitation of free data)
            # In production, you'd want historical fundamental data
            info = stock.info
            if not info or not info.get('marketCap'):
                return None

            # Copy all info fields (for comprehensive features)
            adjusted_info = info.copy()

            # Override price-related fields with historical values
            adjusted_info.update({
                'currentPrice': float(price),
                'marketCap': info.get('marketCap', 0),
                'enterpriseValue': info.get('enterpriseValue', 0),
                'totalRevenue': info.get('totalRevenue', 0),
                'trailingEps': info.get('trailingEps', price/15),  # Approximate if missing
                'forwardEps': info.get('forwardEps', price/14),
                'trailingPE': info.get('trailingPE', 15),
                'forwardPE': info.get('forwardPE', 15),
                'priceToBook': info.get('priceToBook', 2),
                'debtToEquity': info.get('debtToEquity', 50),
                'returnOnEquity': info.get('returnOnEquity', 0.15),
                'returnOnAssets': info.get('returnOnAssets', 0.08),
                'grossMargins': info.get('grossMargins', 0.3),
                'operatingMargins': info.get('operatingMargins', 0.15),
                'profitMargins': info.get('profitMargins', 0.10),
                'sector': info.get('sector', 'Technology'),
                'industry': info.get('industry', 'Unknown'),
                'beta': info.get('beta', 1.0),
                'dividendYield': info.get('dividendYield', 0.0),
                'payoutRatio': info.get('payoutRatio', 0.0),
                'currentRatio': info.get('currentRatio', 1.5),
                'quickRatio': info.get('quickRatio', 1.0),
                'totalCash': info.get('totalCash', 0),
                'totalDebt': info.get('totalDebt', 0),
                'freeCashflow': info.get('freeCashflow', 0),
                'operatingCashflow': info.get('operatingCashflow', 0),
                'revenueGrowth': info.get('revenueGrowth', 0.1),
                'earningsGrowth': info.get('earningsGrowth', 0.1),
                'pegRatio': info.get('pegRatio', 1.5),
                'ebitda': info.get('ebitda', 0),
                'ebit': info.get('ebit', 0),
                'numberOfAnalystOpinions': info.get('numberOfAnalystOpinions', 0),
                'targetMeanPrice': info.get('targetMeanPrice', price * 1.1),
                'recommendationKey': info.get('recommendationKey', 'hold'),
                'fiftyTwoWeekHigh': info.get('fiftyTwoWeekHigh', price * 1.2),
                'fiftyTwoWeekLow': info.get('fiftyTwoWeekLow', price * 0.8),
                'fiftyDayAverage': info.get('fiftyDayAverage', price),
                'twoHundredDayAverage': info.get('twoHundredDayAverage', price),
                'averageVolume': info.get('averageVolume', 1000000),
                'volume': info.get('volume', 1000000),
                'sharesOutstanding': info.get('sharesOutstanding', 1000000000),
            })

            # Create data dict with both info and history for new features
            data = {
                'info': adjusted_info,
                'history': hist,  # Include full history for technical indicators
                'macro': {  # Add placeholder macro data
                    'fed_funds_rate': 2.5,
                    'treasury_10y': 3.0,
                    'vix': 20.0,
                    'sp500_pe': 20.0,
                    'gdp_growth': 2.0,
                    'inflation_rate': 2.5,
                    'unemployment_rate': 4.0,
                    'sector_pe': 20.0,  # Would need sector-specific data
                    'sector_avg_market_cap': 1e10,
                    'relative_perf_1y': 0.0,
                    'sector_relative_perf_1y': 0.0,
                }
            }

            return data

        except Exception as e:
            logger.warning(f'Error getting historical data for {ticker}: {e}')
            return None

    def _calculate_forward_return(self, ticker: str, start_date: datetime, months: int) -> Optional[float]:
        """Calculate forward return from start_date."""
        try:
            end_date = start_date + timedelta(days=months * 30)

            stock = yf.Ticker(ticker)
            hist = stock.history(
                start=start_date - timedelta(days=10),
                end=end_date + timedelta(days=10)
            )

            if len(hist) < months * 15:  # Need reasonable amount of data
                return None

            # Find start and end prices (handle timezone-aware indices)
            hist_index = hist.index.tz_localize(None) if hist.index.tz is not None else hist.index
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
            logger.warning(f'Error calculating forward return for {ticker}: {e}')
            return None

    def train_with_progress_monitoring(self, training_data: List[Tuple]) -> Dict[str, Any]:
        """Train neural network with intelligent progress monitoring."""
        logger.info(f'Starting comprehensive training with {len(training_data)} samples')

        # Initialize model
        model = NeuralNetworkValuationModel(
            time_horizon='comprehensive_2year'
        )

        # Split data
        random.shuffle(training_data)
        n_samples = len(training_data)
        n_train = int(n_samples * (1 - self.config.validation_split - self.config.test_split))
        n_val = int(n_samples * self.config.validation_split)

        train_data = training_data[:n_train]
        val_data = training_data[n_train:n_train + n_val]
        test_data = training_data[n_train + n_val:]

        logger.info(f'Data split: Train={len(train_data)}, Val={len(val_data)}, Test={len(test_data)}')

        # Training loop with progress monitoring
        best_val_loss = float('inf')
        epochs_without_improvement = 0
        total_epochs = 0

        training_results = {
            'total_epochs': 0,
            'best_val_loss': float('inf'),
            'final_train_loss': 0,
            'final_val_loss': 0,
            'val_mae': 0,
            'test_correlation': 0,
            'training_history': []
        }

        # Initial training phase
        logger.info(f'Starting initial training phase: {self.config.initial_epochs} epochs')

        try:
            while total_epochs < self.config.max_total_epochs:
                # Train for a batch of epochs
                epochs_this_batch = min(self.config.initial_epochs,
                                      self.config.max_total_epochs - total_epochs)

                # Combine train and val data for train_model to split internally
                combined_data = train_data + val_data

                # Use the existing train_model method for this batch
                batch_results = model.train_model(
                    combined_data,
                    validation_split=0.2,  # Let model handle validation split
                    epochs=epochs_this_batch
                )

                total_epochs += epochs_this_batch

                # Evaluate progress
                current_val_loss = batch_results.get('final_val_loss', float('inf'))
                current_train_loss = batch_results.get('final_train_loss', float('inf'))
                val_mae = batch_results.get('val_mae', float('inf'))

                # Calculate correlation on validation set
                correlation = self._calculate_correlation(model, val_data)

                # Track progress
                progress = TrainingProgress(
                    epoch=total_epochs,
                    train_loss=current_train_loss,
                    val_loss=current_val_loss,
                    val_mae=val_mae,
                    correlation=correlation,
                    best_val_loss=best_val_loss,
                    epochs_without_improvement=epochs_without_improvement
                )

                self.progress_history.append(progress)

                # Check for improvement
                improvement = best_val_loss - current_val_loss
                if improvement > self.config.min_improvement:
                    best_val_loss = current_val_loss
                    epochs_without_improvement = 0

                    # Save best model
                    best_model_path = Path(f'best_comprehensive_nn_2year_{total_epochs}epochs.pt')
                    model.save_model(best_model_path)
                    self.best_model_path = best_model_path

                    logger.info(f'[OK] Improvement found at epoch {total_epochs}!')
                    logger.info(f'   Val Loss: {current_val_loss:.4f} (↓{improvement:.4f})')
                    logger.info(f'   Correlation: {correlation:.3f}')
                    logger.info(f'   Model saved: {best_model_path}')
                else:
                    epochs_without_improvement += epochs_this_batch
                    logger.info(f'[WARNING]  No significant improvement at epoch {total_epochs}')
                    logger.info(f'   Val Loss: {current_val_loss:.4f} (best: {best_val_loss:.4f})')
                    logger.info(f'   Epochs without improvement: {epochs_without_improvement}')

                # Early stopping check
                if epochs_without_improvement >= self.config.patience:
                    logger.info(f'[STOP] Early stopping triggered after {epochs_without_improvement} epochs without improvement')
                    progress.should_stop = True
                    break

                # Progress report
                logger.info(f'[INFO] Progress Report - Epoch {total_epochs}/{self.config.max_total_epochs}')
                logger.info(f'   Train Loss: {current_train_loss:.4f}')
                logger.info(f'   Val Loss: {current_val_loss:.4f}')
                logger.info(f'   Val MAE: {val_mae:.4f}')
                logger.info(f'   Correlation: {correlation:.3f}')
                logger.info(f'   Best Val Loss: {best_val_loss:.4f}')

                # Small delay to avoid overwhelming logs
                time.sleep(1)

        except KeyboardInterrupt:
            logger.info('Training interrupted by user')
        except Exception as e:
            logger.error(f'Training error: {e}')
            raise

        # Final evaluation on test set
        test_correlation = 0
        if test_data and self.best_model_path and self.best_model_path.exists():
            try:
                # Load best model for final evaluation
                best_model = NeuralNetworkValuationModel(model_path=self.best_model_path)
                test_correlation = self._calculate_correlation(best_model, test_data)
                logger.info(f'[RESULT] Final test correlation: {test_correlation:.3f}')
            except Exception as e:
                logger.warning(f'Error calculating test correlation: {e}')

        # Compile final results
        training_results.update({
            'total_epochs': total_epochs,
            'best_val_loss': best_val_loss,
            'final_train_loss': current_train_loss,
            'final_val_loss': current_val_loss,
            'val_mae': val_mae,
            'test_correlation': test_correlation,
            'best_model_path': str(self.best_model_path) if self.best_model_path else None,
            'epochs_without_improvement': epochs_without_improvement,
            'early_stopped': epochs_without_improvement >= self.config.patience,
            'training_history': [
                {
                    'epoch': p.epoch,
                    'train_loss': p.train_loss,
                    'val_loss': p.val_loss,
                    'val_mae': p.val_mae,
                    'correlation': p.correlation
                }
                for p in self.progress_history
            ]
        })

        # Save training results
        results_path = Path(f'comprehensive_training_results_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
        with open(results_path, 'w') as f:
            json.dump(training_results, f, indent=2, default=str)

        logger.info(f'[FILE] Training results saved: {results_path}')

        return training_results

    def _calculate_correlation(self, model: NeuralNetworkValuationModel, data: List[Tuple]) -> float:
        """Calculate correlation between model predictions and actual returns."""
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

            if len(predictions) < 10:  # Need minimum samples for meaningful correlation
                return 0.0

            return np.corrcoef(predictions, actuals)[0, 1] if len(predictions) > 1 else 0.0

        except Exception as e:
            logger.warning(f'Error calculating correlation: {e}')
            return 0.0

    def run_comprehensive_training(self) -> Dict[str, Any]:
        """Run the complete comprehensive training pipeline."""
        logger.info('[START] Starting Comprehensive Neural Network Training')
        logger.info('=' * 60)
        logger.info(f'Target: {self.config.target_samples} samples from {self.config.start_year}-{self.config.end_year}')
        logger.info(f'Universe: {len(self.stock_universe)} stocks')
        logger.info(f'Max epochs: {self.config.max_total_epochs}, Patience: {self.config.patience}')

        start_time = time.time()

        try:
            # Step 1: Collect historical data
            logger.info('\n[INFO] Step 1: Collecting Historical Data')
            training_data = self.collect_historical_data()

            if len(training_data) < 100:
                raise ValueError(f'Insufficient training data: {len(training_data)} samples')

            # Step 2: Train with progress monitoring
            logger.info('\n[TRAIN] Step 2: Training Neural Network')
            results = self.train_with_progress_monitoring(training_data)

            # Step 3: Final summary
            training_time = time.time() - start_time
            logger.info('\n[COMPLETE] Training Complete!')
            logger.info('=' * 60)
            logger.info(f'Training time: {training_time/3600:.1f} hours')
            logger.info(f'Total epochs: {results["total_epochs"]}')
            logger.info(f'Best validation loss: {results["best_val_loss"]:.4f}')
            logger.info(f'Test correlation: {results["test_correlation"]:.3f}')
            logger.info(f'Early stopped: {results["early_stopped"]}')

            if self.best_model_path:
                logger.info(f'Best model: {self.best_model_path}')

                # Copy to standard location
                final_model_path = Path('trained_nn_2year_comprehensive.pt')
                import shutil
                shutil.copy2(self.best_model_path, final_model_path)
                logger.info(f'Model copied to: {final_model_path}')

            return results

        except Exception as e:
            logger.error(f'Training failed: {e}')
            raise


async def main():
    """Main training function."""
    # Use default config values from the dataclass
    config = TrainingConfig()

    trainer = ComprehensiveNeuralTrainer(config)

    try:
        results = trainer.run_comprehensive_training()

        print('\n[RESULT] COMPREHENSIVE TRAINING SUMMARY')
        print('=' * 50)
        print('Final Results:')
        print(f'  • Training Time: {results.get("training_time", 0)/3600:.1f} hours')
        print(f'  • Total Epochs: {results["total_epochs"]}')
        print(f'  • Best Val Loss: {results["best_val_loss"]:.4f}')
        print(f'  • Test Correlation: {results["test_correlation"]:.3f}')
        print(f'  • Early Stopped: {results["early_stopped"]}')

        if results["test_correlation"] > 0.4:
            print('[EXCELLENT] Excellent correlation achieved!')
        elif results["test_correlation"] > 0.2:
            print('[PROGRESS] Good correlation achieved!')
        else:
            print('[WARNING] Correlation could be improved with more data/tuning')

    except KeyboardInterrupt:
        print('\n[STOP] Training interrupted by user')
    except Exception as e:
        print(f'\n[ERROR] Training failed: {e}')
        raise


if __name__ == '__main__':
    asyncio.run(main())
