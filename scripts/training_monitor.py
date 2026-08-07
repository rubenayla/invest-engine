#!/usr/bin/env python3
"""
Training Progress Monitor
========================

Simple script to monitor training progress in real-time by parsing logs
and showing training metrics in a clean format.
"""

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt


def monitor_training_logs(log_file: Path = Path('comprehensive_training.log')):
    """Monitor training logs and display progress."""

    if not log_file.exists():
        print(f'❌ Log file not found: {log_file}')
        print('Start training first: uv run python models/neural_network/training/comprehensive_neural_training.py')
        return

    print('🔍 Monitoring Neural Network Training Progress')
    print('=' * 60)
    print(f'Log file: {log_file}')
    print('Press Ctrl+C to stop monitoring\n')

    last_position = 0

    try:
        while True:
            # Read new log entries
            with open(log_file, 'r') as f:
                f.seek(last_position)
                new_lines = f.readlines()
                last_position = f.tell()

            # Process new lines
            for line in new_lines:
                line = line.strip()

                # Look for progress reports
                if 'Progress Report - Epoch' in line:
                    try:
                        # Extract epoch number
                        epoch_part = line.split('Epoch ')[1]
                        current_epoch = int(epoch_part.split('/')[0])
                        print(f'\n📊 Epoch {current_epoch}')
                    except Exception:
                        pass

                elif 'Train Loss:' in line:
                    try:
                        train_loss = float(line.split('Train Loss: ')[1])
                        print(f'   🔸 Train Loss: {train_loss:.4f}')
                    except Exception:
                        pass

                elif 'Val Loss:' in line:
                    try:
                        val_loss = float(line.split('Val Loss: ')[1])
                        print(f'   🔹 Val Loss: {val_loss:.4f}')
                    except Exception:
                        pass

                elif 'Correlation:' in line:
                    try:
                        correlation = float(line.split('Correlation: ')[1])
                        print(f'   🎯 Correlation: {correlation:.3f}')

                        if correlation > 0.5:
                            print('      🔥 Excellent correlation!')
                        elif correlation > 0.3:
                            print('      📈 Good correlation')
                        elif correlation > 0.1:
                            print('      ⚠️ Weak correlation')
                    except Exception:
                        pass

                elif '✅ Improvement found' in line:
                    print('   ✅ Model improved - saved checkpoint')

                elif '⚠️  No significant improvement' in line:
                    print('   ⚠️ No improvement this batch')

                elif '🛑 Early stopping triggered' in line:
                    print('\n🛑 EARLY STOPPING - Training Complete!')
                    print('Model has converged or stopped improving.')
                    return

                elif 'Training Complete!' in line:
                    print('\n🎉 TRAINING COMPLETED SUCCESSFULLY!')
                    return

                elif 'Training interrupted' in line:
                    print('\n🛑 Training was interrupted by user')
                    return

            # Sleep before checking again
            time.sleep(2)

    except KeyboardInterrupt:
        print('\n👋 Monitoring stopped')


def plot_training_results(results_file: Path = None):
    """Plot training results from JSON file."""

    if results_file is None:
        # Find the most recent results file
        results_files = list(Path('.').glob('comprehensive_training_results_*.json'))
        if not results_files:
            print('❌ No training results files found')
            return

        results_file = max(results_files, key=lambda p: p.stat().st_mtime)

    print(f'📊 Plotting results from: {results_file}')

    try:
        with open(results_file, 'r') as f:
            results = json.load(f)

        history = results.get('training_history', [])
        if not history:
            print('❌ No training history found in results')
            return

        # Extract data
        epochs = [h['epoch'] for h in history]
        train_losses = [h['train_loss'] for h in history]
        val_losses = [h['val_loss'] for h in history]
        correlations = [h['correlation'] for h in history]

        # Create plots
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 10))
        fig.suptitle('Neural Network Training Results', fontsize=16)

        # Training and validation loss
        ax1.plot(epochs, train_losses, 'b-', label='Train Loss', alpha=0.7)
        ax1.plot(epochs, val_losses, 'r-', label='Validation Loss', alpha=0.7)
        ax1.set_xlabel('Epoch')
        ax1.set_ylabel('Loss')
        ax1.set_title('Training Progress')
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        # Correlation over time
        ax2.plot(epochs, correlations, 'g-', linewidth=2)
        ax2.set_xlabel('Epoch')
        ax2.set_ylabel('Correlation')
        ax2.set_title('Model Correlation with Actual Returns')
        ax2.grid(True, alpha=0.3)
        ax2.axhline(y=0.3, color='orange', linestyle='--', alpha=0.7, label='Good (0.3)')
        ax2.axhline(y=0.5, color='red', linestyle='--', alpha=0.7, label='Excellent (0.5)')
        ax2.legend()

        # Loss difference (overfitting indicator)
        loss_diff = [v - t for v, t in zip(val_losses, train_losses)]
        ax3.plot(epochs, loss_diff, 'purple', linewidth=2)
        ax3.set_xlabel('Epoch')
        ax3.set_ylabel('Val Loss - Train Loss')
        ax3.set_title('Overfitting Indicator')
        ax3.grid(True, alpha=0.3)
        ax3.axhline(y=0, color='black', linestyle='-', alpha=0.3)

        # Summary statistics
        ax4.axis('off')
        summary_text = f"""
Training Summary:
━━━━━━━━━━━━━━━━
Total Epochs: {results.get('total_epochs', 'N/A')}
Best Val Loss: {results.get('best_val_loss', 0):.4f}
Final Correlation: {correlations[-1]:.3f}
Test Correlation: {results.get('test_correlation', 0):.3f}
Early Stopped: {results.get('early_stopped', False)}

Model Performance:
{'🔥 Excellent' if results.get('test_correlation', 0) > 0.4 else '📈 Good' if results.get('test_correlation', 0) > 0.2 else '⚠️ Needs Improvement'}

Best Model: {Path(results.get('best_model_path', '')).name if results.get('best_model_path') else 'N/A'}
"""
        ax4.text(0.1, 0.9, summary_text, transform=ax4.transAxes,
                fontsize=12, verticalalignment='top', fontfamily='monospace')

        plt.tight_layout()

        # Save plot
        plot_path = f'training_results_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png'
        plt.savefig(plot_path, dpi=300, bbox_inches='tight')
        print(f'📊 Plot saved: {plot_path}')

        plt.show()

    except Exception as e:
        print(f'❌ Error plotting results: {e}')


def main():
    """Main monitor function."""
    parser = argparse.ArgumentParser(description='Monitor neural network training')
    parser.add_argument('--plot', action='store_true', help='Plot training results from JSON file')
    parser.add_argument('--results', type=Path, help='Path to results JSON file')
    parser.add_argument('--log', type=Path, default=Path('comprehensive_training.log'),
                       help='Path to log file')

    args = parser.parse_args()

    if args.plot:
        plot_training_results(args.results)
    else:
        monitor_training_logs(args.log)


if __name__ == '__main__':
    main()
