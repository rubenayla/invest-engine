#!/bin/bash
# Package the invest repo for training on another machine

set -e

echo "📦 Packaging invest repository for remote training..."
echo ""

# Create temporary directory
TEMP_DIR=$(mktemp -d)
PKG_NAME="invest_training_package"
PKG_DIR="$TEMP_DIR/$PKG_NAME"

mkdir -p "$PKG_DIR"

# Copy essential files
echo "Copying source code..."
cp -r src "$PKG_DIR/"
cp -r scripts "$PKG_DIR/"
cp -r tests "$PKG_DIR/"
cp -r configs "$PKG_DIR/" 2>/dev/null || true

# Copy configuration files
echo "Copying configuration..."
cp pyproject.toml "$PKG_DIR/"
cp uv.lock "$PKG_DIR/" 2>/dev/null || true
cp README.md "$PKG_DIR/" 2>/dev/null || true
cp AGENTS.md "$PKG_DIR/" 2>/dev/null || true

# Copy docs
echo "Copying documentation..."
mkdir -p "$PKG_DIR/docs"
cp docs/portable_training_guide.md "$PKG_DIR/docs/" 2>/dev/null || true
cp docs/neural_network_evaluation_guide.md "$PKG_DIR/docs/" 2>/dev/null || true

# Create setup instructions
cat > "$PKG_DIR/TRAINING_SETUP.md" << 'EOF'
# Quick Training Setup

## 1. Install Dependencies

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh  # Linux/Mac
# OR
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"  # Windows

# Install project dependencies
uv sync --all-groups
```

## 2. Run Training

```bash
# Default training (2015-2024, 5000 samples)
uv run python models/neural_network/training/comprehensive_neural_training.py

# Monitor progress
tail -f comprehensive_training.log
```

## 3. Package Models

```bash
# Create archive of trained models
tar -czf trained_models_$(date +%Y%m%d).tar.gz *.pt comprehensive_training.log

# Transfer back to your Mac
# scp trained_models_*.tar.gz user@mac-ip:~/repos/invest/
```

## Hardware Requirements

- **Minimum**: 8GB RAM, any CPU (training will be slow)
- **Recommended**: 16GB RAM, NVIDIA GPU with 8GB+ VRAM
- **Optimal**: 32GB RAM, NVIDIA RTX 3080+ or A100

## Troubleshooting

**"Module not found"**
- Make sure you use `uv run` prefix
- Run `uv sync --all-groups` again

**Out of memory**
- Reduce target_samples in models/neural_network/training/comprehensive_neural_training.py
- Or increase system RAM/swap

**Training too slow**
- Use a machine with GPU
- Reduce target_samples temporarily
- Check CPU/GPU usage with `htop` or `nvidia-smi`

For full documentation, see: `docs/portable_training_guide.md`
EOF

# Create README
cat > "$PKG_DIR/README.md" << EOF
# Invest Neural Network Training Package

This package contains everything needed to train neural network valuation models.

## Quick Start

1. **Install dependencies**: \`uv sync --all-groups\`
2. **Run training**: \`uv run python models/neural_network/training/comprehensive_neural_training.py\`
3. **Package models**: \`tar -czf trained_models.tar.gz *.pt\`

See **TRAINING_SETUP.md** for detailed instructions.

## What's Included

- \`src/\` - Source code for valuation models
- \`scripts/\` - Training and evaluation scripts
- \`tests/\` - Test suite
- \`pyproject.toml\` - Project dependencies
- \`docs/\` - Documentation

## Training Output

After training completes, you'll have:
- \`*.pt\` files - Trained models (transfer these back)
- \`comprehensive_training.log\` - Training details
- \`evaluation_results/\` - Performance metrics (optional)

## Support

- Training guide: \`docs/portable_training_guide.md\`
- Evaluation guide: \`docs/neural_network_evaluation_guide.md\`
- Project instructions: \`CLAUDE.md\`

Package created: $(date)
EOF

# Create .gitignore for training output
cat > "$PKG_DIR/.gitignore" << EOF
# Training outputs
*.pt
*.pth
*.log
evaluation_results/
__pycache__/
.pytest_cache/
*.pyc

# Data cache
.cache/
data/

# IDE
.vscode/
.idea/
*.swp
EOF

# Create archive
cd "$TEMP_DIR"
echo "Creating archive..."
tar -czf "$PKG_NAME.tar.gz" "$PKG_NAME"

# Move to original directory
ORIGINAL_DIR=$(pwd -P)
cd - > /dev/null
mv "$TEMP_DIR/$PKG_NAME.tar.gz" .

# Cleanup
rm -rf "$TEMP_DIR"

# Show results
echo ""
echo "✅ Package created successfully!"
echo ""
echo "📦 File: $PKG_NAME.tar.gz"
echo "📏 Size: $(du -h "$PKG_NAME.tar.gz" | cut -f1)"
echo ""
echo "Next steps:"
echo "  1. Transfer to training machine:"
echo "     scp $PKG_NAME.tar.gz user@training-machine:~/"
echo ""
echo "  2. On training machine:"
echo "     tar -xzf $PKG_NAME.tar.gz"
echo "     cd $PKG_NAME"
echo "     cat TRAINING_SETUP.md"
echo ""
