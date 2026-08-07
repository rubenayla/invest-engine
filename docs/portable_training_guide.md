# Portable Training Setup Guide

## Overview

Train neural network models on powerful machines and use them on your daily driver Mac. This guide covers setup, training, and model transfer.

---

## Quick Start

### On Your Mac (Daily Driver)

```bash
# 1. Clone the repo (already done)
git clone https://github.com/yourusername/invest.git
cd invest

# 2. Install dependencies
uv sync

# 3. Package the code for transfer
./scripts/package_for_training.sh
```

This creates `invest_training_package.tar.gz` ready to transfer.

### On Your Training Machine (Linux/Windows)

```bash
# 1. Extract the package
tar -xzf invest_training_package.tar.gz
cd invest

# 2. Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh  # Linux/Mac
# OR
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"  # Windows

# 3. Install dependencies
uv sync --all-groups

# 4. Run training
uv run python models/neural_network/training/comprehensive_neural_training.py

# 5. Package trained models
tar -czf trained_models.tar.gz *.pt
```

### Back to Your Mac

```bash
# 1. Transfer trained models
scp user@training-machine:invest/trained_models.tar.gz .

# 2. Extract models
tar -xzf trained_models.tar.gz

# 3. Use the models
uv run python -c "
from pathlib import Path
from src.invest.valuation.neural_network_model import NeuralNetworkValuationModel

model = NeuralNetworkValuationModel(
    time_horizon='2year',
    model_path=Path('trained_nn_2year_comprehensive.pt')
)
print('Model loaded successfully!')
"
```

---

## Detailed Setup

### System Requirements

**Minimum (for inference on Mac):**
- 4GB RAM
- Any modern CPU
- 500MB disk space

**Recommended (for training):**
- 16GB+ RAM
- NVIDIA GPU with 8GB+ VRAM (optional but 10-100x faster)
- 10GB disk space for data caching

### Installing on Different Systems

#### Ubuntu/Debian Linux

```bash
# Install system dependencies
sudo apt update
sudo apt install -y python3.11 python3-pip git

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Add to PATH
echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

# Clone and setup
git clone https://github.com/yourusername/invest.git
cd invest
uv sync --all-groups
```

#### Windows

```powershell
# Install Python 3.11 from python.org first

# Install uv
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Clone and setup
git clone https://github.com/yourusername/invest.git
cd invest
uv sync --all-groups
```

#### Docker (Platform-Independent)

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install uv
RUN pip install uv

# Copy project
COPY . .

# Install dependencies
RUN uv sync --all-groups

# Run training
CMD ["uv", "run", "python", "models/neural_network/training/comprehensive_neural_training.py"]
```

Build and run:
```bash
docker build -t invest-trainer .
docker run -v $(pwd):/app invest-trainer
```

---

## Training Configuration

### Config File Approach

Create `training_config.yaml`:

```yaml
# Training period
start_year: 2015  # More recent = better data quality
end_year: 2024

# Dataset size
target_samples: 10000  # More = better (but slower)

# Model architecture (advanced)
hidden_dims: [512, 256, 128, 64]
dropout_rate: 0.3

# Training hyperparameters
initial_epochs: 50
max_total_epochs: 300
patience: 15  # Early stopping
learning_rate: 0.001

# Hardware settings
batch_size: 128  # Increase for GPU
use_gpu: true
```

Load in training script:
```python
import yaml

with open('training_config.yaml') as f:
    config = yaml.safe_load(f)

# Use config values...
```

### Environment Variables

For quick tweaks:

```bash
# Set training parameters
export TRAIN_START_YEAR=2015
export TRAIN_SAMPLES=10000
export TRAIN_EPOCHS=100

# Run training
uv run python models/neural_network/training/comprehensive_neural_training.py
```

---

## Model Management

### Model Files Explained

```
invest/
├── *.pt                                    # Trained models (PyTorch format)
│   ├── trained_nn_2year_comprehensive.pt   # Full model (225KB)
│   └── best_comprehensive_nn_*.pt          # Best checkpoint
│
├── comprehensive_training.log              # Training log
└── evaluation_results/                     # Evaluation outputs
    ├── neural_network_evaluation_report.txt
    └── evaluation_results.json
```

**Model file contents:**
- Neural network weights (most of the file)
- Feature scaler parameters (for normalization)
- Feature names (for consistency)
- Metadata (time horizon, training date)

### Transferring Models

**Method 1: Direct File Copy**
```bash
# On training machine
scp *.pt USER@HOST:/path/to/invest/

# On Mac
cd /path/to/invest
ls -lh *.pt
```

**Method 2: Git LFS (for version control)**
```bash
# Setup (one-time)
git lfs install
git lfs track "*.pt"

# On training machine
git add *.pt
git commit -m "Add trained models"
git push

# On Mac
git pull
```

**Method 3: Cloud Storage**
```bash
# Upload to S3/GCS/Azure
aws s3 cp trained_nn_2year_comprehensive.pt s3://my-bucket/models/

# Download on Mac
aws s3 cp s3://my-bucket/models/trained_nn_2year_comprehensive.pt .
```

### Model Versioning

Best practice - include metadata in filename:

```
trained_nn_{horizon}_{date}_{samples}_{mae}.pt

Examples:
trained_nn_2year_20241005_4620samples_25.78mae.pt
trained_nn_1year_20241006_8000samples_18.45mae.pt
```

Script to rename:
```python
import shutil
from datetime import datetime

old_name = 'trained_nn_2year_comprehensive.pt'
new_name = f'trained_nn_2year_{datetime.now():%Y%m%d}_4620samples_25.78mae.pt'
shutil.copy(old_name, new_name)
```

---

## GPU Training

### CUDA Setup (NVIDIA GPUs)

```bash
# Check GPU
nvidia-smi

# Install CUDA-enabled PyTorch
uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# Verify
uv run python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"
```

### Performance Comparison

| Hardware | Training Time (5000 samples) | Cost |
|----------|------------------------------|------|
| M1 Mac (CPU) | ~45 min | $0 (you own it) |
| Intel i7 (CPU) | ~60 min | $0 |
| NVIDIA RTX 3080 | ~5 min | ~$2/hr cloud |
| NVIDIA A100 | ~2 min | ~$4/hr cloud |

### Cloud Training Options

**AWS EC2:**
```bash
# p3.2xlarge (V100 GPU) - $3.06/hour
aws ec2 run-instances \
    --image-id ami-0abcdef1234567890 \
    --instance-type p3.2xlarge \
    --key-name my-key

# SSH and train
ssh -i my-key.pem ubuntu@<instance-ip>
```

**Google Colab (Free tier):**
```python
# Upload invest_training_package.tar.gz to Colab
!tar -xzf invest_training_package.tar.gz
!pip install uv
!uv sync
!uv run python models/neural_network/training/comprehensive_neural_training.py

# Download model
from google.colab import files
files.download('trained_nn_2year_comprehensive.pt')
```

**Vast.ai (Cheap GPUs):**
- Rent GPUs from $0.10-0.50/hour
- SSH access, full control
- Good for experiments

---

## Advanced Topics

### Distributed Training (Multiple GPUs)

```python
import torch.nn as nn
import torch.distributed as dist

# Wrap model
model = nn.DataParallel(model, device_ids=[0, 1, 2, 3])

# Training loop automatically uses all GPUs
```

### Hyperparameter Tuning

Use Ray Tune for automated search:

```python
from ray import tune

def train_model(config):
    model = NeuralNetworkValuationModel()
    metrics = model.train_model(
        data,
        epochs=config['epochs'],
        # ... other params
    )
    return metrics['val_mae']

analysis = tune.run(
    train_model,
    config={
        'epochs': tune.choice([50, 100, 200]),
        'learning_rate': tune.loguniform(1e-4, 1e-2),
        'dropout': tune.uniform(0.1, 0.5)
    },
    num_samples=20
)
```

### Continuous Training

Keep model fresh with new data:

```bash
# Cron job (daily at 2 AM)
0 2 * * * cd ~/invest && uv run python scripts/incremental_training.py
```

---

## Troubleshooting

### "Module not found" errors

```bash
# Make sure you're using uv run
uv run python script.py  # ✓ Correct
python script.py         # ✗ Wrong (uses system Python)
```

### "Out of memory" on GPU

```python
# Reduce batch size
config.batch_size = 32  # Instead of 128

# Or use gradient accumulation
for i in range(4):  # Accumulate 4 batches
    loss = model(batch) / 4
    loss.backward()
optimizer.step()
```

### Models don't transfer between platforms

PyTorch models are generally portable, but:

```python
# Save with map_location
torch.save(model.state_dict(), 'model.pt')

# Load on any device
model.load_state_dict(torch.load('model.pt', map_location='cpu'))
```

### Training is too slow

**Profile the code:**
```python
import cProfile
cProfile.run('train_model()', 'training_profile.txt')

# Analyze
python -m pstats training_profile.txt
```

**Common bottlenecks:**
1. Data loading (use multiprocessing)
2. Feature engineering (vectorize with NumPy)
3. Network requests (cache aggressively)

---

## Best Practices

### 1. Version Everything

```
models/
├── v1_2024-10-05/
│   ├── trained_nn_2year.pt
│   ├── config.yaml
│   ├── training.log
│   └── eval_results.json
└── v2_2024-10-12/
    └── ...
```

### 2. Document Training Runs

Create `training_metadata.json`:
```json
{
  "version": "v2",
  "date": "2024-10-12",
  "machine": "AWS p3.2xlarge",
  "duration_hours": 0.3,
  "config": {
    "start_year": 2015,
    "samples": 10000,
    "epochs": 150
  },
  "metrics": {
    "val_mae": 18.45,
    "test_correlation": 0.35
  },
  "git_commit": "a1b2c3d"
}
```

### 3. Test Before Deploying

```bash
# Quick sanity check
uv run python -c "
from pathlib import Path
from src.invest.valuation.neural_network_model import NeuralNetworkValuationModel

model = NeuralNetworkValuationModel(model_path=Path('new_model.pt'))
# Test on known stock
result = model.calculate_fair_value('AAPL', test_data)
assert result.fair_value > 0, 'Model broken!'
print('✓ Model works')
"
```

### 4. Automate the Workflow

`scripts/train_and_deploy.sh`:
```bash
#!/bin/bash
set -e

# Train
uv run python models/neural_network/training/comprehensive_neural_training.py

# Evaluate
uv run python scripts/neural_network_evaluator.py

# Test
uv run pytest tests/test_neural_network_model.py

# Package
tar -czf models_$(date +%Y%m%d).tar.gz *.pt

echo "✓ Training complete! Transfer models_$(date +%Y%m%d).tar.gz to your Mac"
```

---

## Summary

**Workflow:**
1. **Develop on Mac**: Code, test, iterate
2. **Train on powerful machine**: Use GPU for speed
3. **Transfer models**: Simple file copy
4. **Use on Mac**: Inference is lightweight

**Key files to transfer:**
- `*.pt` - Trained models (essential)
- `comprehensive_training.log` - Training details (optional)
- `evaluation_results/*` - Performance metrics (recommended)

**Next steps:**
- Set up your training machine
- Run improved training (2015-2024 data)
- Compare old vs new model performance
- Deploy best model to production

Need help? Check:
- Training logs: `comprehensive_training.log`
- Test results: `uv run pytest -v`
- Model registry: `src/invest/valuation/model_registry.py`
