#!/usr/bin/env python3
"""
Parallel Architecture Experiments
==================================

Run multiple neural network architectures in parallel using the same cached data.
This script modifies the NeuralNetworkArchitecture to test different configurations.
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Get architecture config from environment variable
arch_name = os.environ.get('ARCH_NAME', 'default')
hidden_dims_str = os.environ.get('HIDDEN_DIMS', '256,128,64,32')
hidden_dims = [int(x) for x in hidden_dims_str.split(',')]

print(f"Starting training with architecture: {arch_name}")
print(f"Hidden dimensions: {hidden_dims}")

# Monkey-patch the default hidden_dims in NeuralNetworkArchitecture
from src.invest.valuation import neural_network_model

original_init = neural_network_model.NeuralNetworkArchitecture.__init__

def patched_init(self, input_dim, hidden_dims=None, dropout_rate=0.3, output_type='score'):
    if hidden_dims is None:
        # Use configured architecture from environment
        hidden_dims = [int(x) for x in os.environ.get('HIDDEN_DIMS', '256,128,64,32').split(',')]
    original_init(self, input_dim, hidden_dims, dropout_rate, output_type)

neural_network_model.NeuralNetworkArchitecture.__init__ = patched_init

# Now run the comprehensive training
import asyncio

from neural_network.training.comprehensive_neural_training import main

if __name__ == '__main__':
    asyncio.run(main())
