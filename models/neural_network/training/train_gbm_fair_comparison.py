#!/usr/bin/env python3
"""
Fair comparison: Train full GBM only on stocks with >=12 quarters.
"""
import sqlite3
from pathlib import Path

from train_gbm_stock_ranker import GBMStockRanker

# Get stocks with sufficient history
db_path = Path('../../data/stock_data.db')
conn = sqlite3.connect(db_path)

query = '''
SELECT DISTINCT a.symbol
FROM assets a
JOIN snapshots s ON a.id = s.asset_id
WHERE s.vix IS NOT NULL
GROUP BY a.symbol
HAVING COUNT(*) >= 12
'''
cursor = conn.cursor()
cursor.execute(query)
eligible_stocks = {row[0] for row in cursor.fetchall()}
conn.close()

print(f'Stocks with ≥12 quarters: {len(eligible_stocks)}')

# Train full GBM on complete data only
trainer = GBMStockRanker(target_horizon='1y', model_type='lightgbm')
df = trainer.load_data()

# Filter to only eligible stocks
df_filtered = df[df['ticker'].isin(eligible_stocks)]
print(f'Total samples: {len(df)} → Filtered: {len(df_filtered)} ({len(df_filtered)/len(df)*100:.1f}%)')

# Engineer features
df_filtered = trainer.engineer_features(df_filtered)

# Prepare training data
df_filtered, numeric_features, categorical_features = trainer.prepare_training_data(df_filtered)

# Train
trainer.train(df_filtered, numeric_features, categorical_features)

# Evaluate
metrics = trainer.evaluate(df_filtered, numeric_features, categorical_features)

print('\n' + '='*60)
print('FULL GBM (≥12 quarters only) - Fair Comparison')
print('='*60)
print(f'Samples: {len(df_filtered)}')
print(f'Rank IC: {metrics["rank_ic"]:.4f}')
print(f'Decile Spread: {metrics["decile_spread"]:.4f}')
print('='*60)
