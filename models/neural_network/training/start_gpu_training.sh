#!/bin/bash
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
export PATH=$HOME/.local/bin:$PATH
uv run python neural_network/training/comprehensive_neural_training.py
