#!/bin/bash
set -e

echo "🔄 Updating all model predictions..."
echo ""

echo "📊 Running GBM models..."
uv run python scripts/run_gbm_predictions.py --variant standard --horizon 1y
uv run python scripts/run_gbm_predictions.py --variant standard --horizon 3y
uv run python scripts/run_gbm_predictions.py --variant lite --horizon 1y
uv run python scripts/run_gbm_predictions.py --variant lite --horizon 3y
uv run python scripts/run_gbm_predictions.py --variant opportunistic --horizon 1y
uv run python scripts/run_gbm_predictions.py --variant opportunistic --horizon 3y

# NN disabled: near-zero test correlation (2026-02-21)
# echo ""
# echo "🧠 Running neural network models..."
# uv run python scripts/run_multi_horizon_predictions.py

echo ""
echo "💰 Running classic valuation models..."
uv run python scripts/run_classic_valuations.py

echo ""
echo "📈 Generating dashboard..."
uv run python scripts/dashboard.py

echo ""
echo "✅ All predictions updated, dashboard generated at dashboard/valuation_dashboard.html"
