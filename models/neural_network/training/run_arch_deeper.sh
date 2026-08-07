#!/bin/bash
# Train deeper network: 5 layers [256, 256, 128, 128, 64]
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
export PATH=$HOME/.local/bin:$PATH
export ARCH_NAME="deeper_5layer"
export HIDDEN_DIMS="256,256,128,128,64"
uv run python neural_network/training/parallel_architecture_experiments.py > training_deeper.log 2>&1
