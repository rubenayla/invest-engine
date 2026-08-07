#!/usr/bin/env python3
"""
Train multi-horizon model with real macro data.
"""

import json
import logging
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.model_selection import train_test_split
from torch.utils.data import DataLoader, TensorDataset

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.invest.valuation.neural_network_model import FeatureEngineer, MultiHorizonNeuralNetwork

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def train_multi_horizon_model():
    """Train model with real macro features."""

    logger.info('='*60)
    logger.info('Training Multi-Horizon Model with Macro Features')
    logger.info('='*60)

    # Load cache
    cache_path = Path(__file__).parent / 'training_data_cache_multi_horizon.json'
    logger.info(f'Loading cache from {cache_path}')

    with open(cache_path, 'r') as f:
        cache = json.load(f)

    samples = cache['samples']
    logger.info(f'Loaded {len(samples)} samples from cache')

    # Check if we have macro data
    first_sample = samples[0]
    if 'macro' in first_sample['data'] and first_sample['data']['macro']:
        macro_keys = list(first_sample['data']['macro'].keys())
        logger.info(f'Macro features available: {macro_keys}')
    else:
        logger.warning('No macro data found in cache!')

    # Extract features
    feature_engineer = FeatureEngineer()
    X_list = []
    y_dict = {horizon: [] for horizon in ['1m', '3m', '6m', '1y', '2y']}

    logger.info('Extracting features...')
    for i, sample in enumerate(samples):
        if i % 500 == 0:
            logger.info(f'Processing sample {i}/{len(samples)}')

        features = feature_engineer.extract_features(sample['data'])
        X_list.append(list(features.values()))

        for horizon in y_dict.keys():
            y_dict[horizon].append(sample['forward_returns'][horizon])

    # Convert to arrays
    X = np.array(X_list)
    y = {k: np.array(v) for k, v in y_dict.items()}

    logger.info(f'Feature dimension: {X.shape[1]}')
    logger.info(f'Feature names (first 10): {list(features.keys())[:10]}')

    # Check if macro features are present
    feature_names = list(features.keys())
    macro_features = [f for f in feature_names if any(m in f for m in ['vix', 'treasury', 'dollar', 'oil', 'gold'])]
    if macro_features:
        logger.info(f'Macro features in model: {macro_features}')

    # Split data
    X_train, X_temp, y_train, y_temp = train_test_split(
        X, [y[h] for h in y.keys()], test_size=0.3, random_state=42
    )
    X_val, X_test, y_val, y_test = train_test_split(
        X_temp, y_temp, test_size=0.5, random_state=42
    )

    # Reconstruct y dicts
    horizons = ['1m', '3m', '6m', '1y', '2y']
    y_train = {h: y_train[i] for i, h in enumerate(horizons)}
    y_val = {h: y_val[i] for i, h in enumerate(horizons)}
    y_test = {h: y_test[i] for i, h in enumerate(horizons)}

    logger.info(f'Data split: Train={len(X_train)}, Val={len(X_val)}, Test={len(X_test)}')

    # Fit scaler and transform
    feature_engineer.fit_transform(X_train)
    X_train_scaled = feature_engineer.transform(X_train)
    X_val_scaled = feature_engineer.transform(X_val)
    X_test_scaled = feature_engineer.transform(X_test)

    # Create model
    input_dim = X_train_scaled.shape[1]
    model = MultiHorizonNeuralNetwork(
        input_dim=input_dim,
        hidden_dims=[256, 128, 64, 32],
        horizons=horizons,
        dropout_rate=0.3
    )

    # Training setup
    optimizer = optim.Adam(model.parameters(), lr=0.001)

    # Create DataLoaders
    train_dataset = TensorDataset(
        torch.FloatTensor(X_train_scaled),
        *[torch.FloatTensor(y_train[h]) for h in horizons]
    )
    val_dataset = TensorDataset(
        torch.FloatTensor(X_val_scaled),
        *[torch.FloatTensor(y_val[h]) for h in horizons]
    )

    train_loader = DataLoader(train_dataset, batch_size=64, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=64, shuffle=False)

    # Training loop
    logger.info('\nStarting training...')
    best_val_loss = float('inf')
    patience = 20
    patience_counter = 0

    for epoch in range(200):
        # Training
        model.train()
        train_loss = 0
        for batch in train_loader:
            X_batch = batch[0]
            y_batch = {h: batch[i+1] for i, h in enumerate(horizons)}

            optimizer.zero_grad()
            predictions = model(X_batch)

            loss = sum(
                nn.MSELoss()(predictions[h], y_batch[h])
                for h in horizons
            )

            loss.backward()
            optimizer.step()
            train_loss += loss.item()

        # Validation
        model.eval()
        val_loss = 0
        with torch.no_grad():
            for batch in val_loader:
                X_batch = batch[0]
                y_batch = {h: batch[i+1] for i, h in enumerate(horizons)}

                predictions = model(X_batch)
                loss = sum(
                    nn.MSELoss()(predictions[h], y_batch[h])
                    for h in horizons
                )
                val_loss += loss.item()

        avg_train_loss = train_loss / len(train_loader)
        avg_val_loss = val_loss / len(val_loader)

        if (epoch + 1) % 10 == 0:
            logger.info(f'Epoch {epoch+1}: Train Loss={avg_train_loss:.4f}, Val Loss={avg_val_loss:.4f}')

        # Early stopping
        if avg_val_loss < best_val_loss:
            best_val_loss = avg_val_loss
            patience_counter = 0
            # Save best model
            torch.save({
                'model_state_dict': model.state_dict(),
                'feature_engineer': feature_engineer,
                'input_dim': input_dim,
                'horizons': horizons
            }, 'multi_horizon_model_with_macro.pt')
        else:
            patience_counter += 1
            if patience_counter >= patience:
                logger.info(f'Early stopping at epoch {epoch+1}')
                break

    # Load best model
    checkpoint = torch.load('multi_horizon_model_with_macro.pt')
    model.load_state_dict(checkpoint['model_state_dict'])

    # Evaluate on test set
    logger.info('\n' + '='*60)
    logger.info('Evaluating on Test Set')
    logger.info('='*60)

    model.eval()
    X_test_tensor = torch.FloatTensor(X_test_scaled)

    with torch.no_grad():
        predictions = model(X_test_tensor)

    for horizon in horizons:
        pred = predictions[horizon].numpy()
        actual = y_test[horizon]

        mae = np.mean(np.abs(pred - actual))
        rmse = np.sqrt(np.mean((pred - actual) ** 2))
        corr = np.corrcoef(pred.flatten(), actual.flatten())[0, 1]

        logger.info(f'{horizon:3s}: MAE={mae*100:.2f}%, RMSE={rmse*100:.2f}%, Corr={corr:.3f}')

    logger.info('\n✅ Training complete with macro features!')


if __name__ == '__main__':
    train_multi_horizon_model()
