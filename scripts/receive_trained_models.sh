#!/bin/bash
# Receive and deploy trained models from Windows machine

set -e

echo "🔄 Model Transfer & Deployment Script"
echo ""
echo "Choose transfer method:"
echo "  1) HTTP download (Windows uploads to this Mac)"
echo "  2) SCP pull from Windows"
echo "  3) Manual (already have the file)"
echo ""
read -p "Selection (1-3): " method

case $method in
    1)
        echo ""
        echo "Starting HTTP server on port 8000..."
        echo "Run this on Windows:"
        echo ""
        echo "  \$date = Get-Date -Format 'yyyyMMdd'"
        echo "  Invoke-WebRequest -Method POST -InFile trained_models_\$date.tar.gz -Uri http://192.168.1.139:8000/upload"
        echo ""
        echo "Waiting for upload..."

        # Simple Python upload server
        python3 << 'PYEOF'
from http.server import HTTPServer, BaseHTTPRequestHandler
import os

class UploadHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/upload':
            content_length = int(self.headers['Content-Length'])
            file_data = self.rfile.read(content_length)

            filename = 'trained_models_received.tar.gz'
            with open(filename, 'wb') as f:
                f.write(file_data)

            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'Upload successful!')

            print(f"\n✅ Received {filename} ({len(file_data)} bytes)")
            print("Shutting down server...")
            raise KeyboardInterrupt
        else:
            self.send_response(404)
            self.end_headers()

try:
    server = HTTPServer(('0.0.0.0', 8000), UploadHandler)
    server.serve_forever()
except KeyboardInterrupt:
    pass
PYEOF

        MODELS_FILE="trained_models_received.tar.gz"
        ;;

    2)
        echo ""
        read -p "Enter date of models (YYYYMMDD, e.g., $(date +%Y%m%d)): " date
        MODELS_FILE="trained_models_${date}.tar.gz"

        echo "Downloading from Windows..."
        scp ruben@192.168.1.117:~/invest_training_package/trained_models_${date}.tar.gz .
        ;;

    3)
        echo ""
        read -p "Enter path to models file: " MODELS_FILE

        if [ ! -f "$MODELS_FILE" ]; then
            echo "❌ File not found: $MODELS_FILE"
            exit 1
        fi
        ;;

    *)
        echo "❌ Invalid selection"
        exit 1
        ;;
esac

# Extract models
echo ""
echo "📦 Extracting models..."
tar -xzf "$MODELS_FILE"

# Backup old models
if ls *.pt 1> /dev/null 2>&1; then
    BACKUP_DIR="models_backup_$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$BACKUP_DIR"
    echo "📁 Backing up old models to $BACKUP_DIR/"
    mv *.pt "$BACKUP_DIR/" 2>/dev/null || true
fi

# List new models
echo ""
echo "✅ New models deployed:"
ls -lh *.pt | awk '{print "   " $9, "(" $5 ")"}'

echo ""
echo "📊 Training log summary:"
if [ -f comprehensive_training.log ]; then
    echo ""
    tail -20 comprehensive_training.log | grep -E "(Collected|Epoch|MAE|correlation|Final)" || echo "   (log format differs - check comprehensive_training.log)"
fi

echo ""
echo "🧪 Testing model loading..."
uv run python -c "
from pathlib import Path
from src.invest.valuation.neural_network_model import NeuralNetworkValuationModel

model_file = list(Path('.').glob('trained_nn_*_comprehensive.pt'))[0]
model = NeuralNetworkValuationModel(
    time_horizon='2year',
    model_path=model_file
)
print(f'✅ Model {model_file.name} loads successfully!')
"

echo ""
echo "✨ Deployment complete!"
echo ""
echo "Next steps:"
echo "  1. Compare with old model: uv run python scripts/model_comparison.py"
echo "  2. Evaluate performance: uv run python scripts/neural_network_evaluator.py"
echo "  3. Update model registry if better: Edit src/invest/valuation/model_registry.py"

