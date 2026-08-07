#!/usr/bin/env python3
"""
Systematic Investment Analysis CLI

Usage:
    python systematic_analysis.py [config_file] [options]
    python systematic_analysis.py --list-configs
    python systematic_analysis.py --create-example

Examples:
    python systematic_analysis.py dashboard/configs/default_analysis.yaml
    python systematic_analysis.py dashboard/configs/aggressive_growth.yaml --output results/
    python systematic_analysis.py --config conservative_value --save-csv
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Add src to path to import our modules
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from invest.analysis.pipeline import AnalysisPipeline
from invest.config.loader import (
    create_example_config,
    get_default_config_path,
    list_available_configs,
    load_analysis_config,
)
from invest.reports.templates import export_to_csv_format, generate_full_report


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Systematic Investment Analysis Framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                    # Use default configuration
  %(prog)s dashboard/configs/aggressive_growth.yaml    # Use specific config
  %(prog)s --list-configs                    # Show available configs
  %(prog)s --create-example my_config.yaml  # Create example config
  %(prog)s --config default --output results/ --save-csv
        """
    )

    parser.add_argument(
        'config_file',
        nargs='?',
        help='Path to analysis configuration file'
    )

    parser.add_argument(
        '--list-configs',
        action='store_true',
        help='List all available configuration files'
    )

    parser.add_argument(
        '--create-example',
        metavar='FILE',
        help='Create an example configuration file'
    )

    parser.add_argument(
        '--output', '-o',
        metavar='DIR',
        help='Output directory for results (default: current directory)'
    )

    parser.add_argument(
        '--save-json',
        action='store_true',
        help='Save results in JSON format'
    )

    parser.add_argument(
        '--save-csv',
        action='store_true',
        help='Save results in CSV format'
    )

    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='Suppress progress output'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Verbose output with detailed logging'
    )

    return parser.parse_args()


def list_configs():
    """List available configuration files."""
    configs = list_available_configs()

    if not configs:
        print("No configuration files found.")
        return

    print("Available configuration files:")
    print("=" * 40)

    for config_path in sorted(configs):
        config_name = config_path.stem
        print(f"• {config_name} ({config_path.name})")

        try:
            config = load_analysis_config(config_path)
            if config.description:
                print(f"  Description: {config.description}")
            print()
        except Exception as e:
            print(f"  Error loading config: {e}")
            print()


def run_analysis(config_file: str, args) -> dict:
    """Run the systematic analysis."""
    # Load configuration
    if config_file:
        config_path = Path(config_file)
        if not config_path.exists():
            # Try in configs directory
            configs_dir = Path(__file__).parent.parent / "dashboard" / "configs"
            config_path = configs_dir / f"{config_file}.yaml"
            if not config_path.exists():
                config_path = configs_dir / config_file
    else:
        config_path = get_default_config_path()

    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    if not args.quiet:
        print(f"Loading configuration: {config_path}")

    config = load_analysis_config(config_path)

    if not args.quiet:
        print(f"Starting analysis: {config.name}")
        if config.description:
            print(f"Description: {config.description}")
        print()

    # Run analysis pipeline
    pipeline = AnalysisPipeline(config)
    results = pipeline.run_analysis()

    return results


def save_results(results: dict, args):
    """Save analysis results in requested formats."""
    output_dir = Path(args.output) if args.output else Path.cwd()
    output_dir.mkdir(parents=True, exist_ok=True)

    config_name = results.get('config', {}).get('name', 'analysis')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    base_filename = f"{config_name}_{timestamp}"

    saved_files = []

    # Always save text report
    report_path = output_dir / f"{base_filename}_report.txt"
    full_report = generate_full_report(results)

    with open(report_path, 'w') as f:
        f.write(full_report)
    saved_files.append(report_path)

    # Save JSON if requested
    if args.save_json:
        json_path = output_dir / f"{base_filename}_data.json"
        with open(json_path, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        saved_files.append(json_path)

    # Save CSV if requested
    if args.save_csv:
        csv_path = output_dir / f"{base_filename}_results.csv"
        csv_data = export_to_csv_format(results)
        with open(csv_path, 'w') as f:
            f.write(csv_data)
        saved_files.append(csv_path)

    return saved_files


def main():
    """Main CLI entry point."""
    args = parse_arguments()

    # Handle special commands
    if args.list_configs:
        list_configs()
        return

    if args.create_example:
        output_path = Path(args.create_example)
        create_example_config(output_path)
        print(f"Example configuration created: {output_path}")
        return

    try:
        # Run analysis
        results = run_analysis(args.config_file, args)

        # Display summary
        if not args.quiet:
            summary = results.get('summary', {})
            print("\nANALYSIS COMPLETE")
            print("=" * 50)
            print(f"Total universe: {results.get('total_universe', 0)} stocks")
            print(f"Passed screening: {results.get('passed_screening', 0)} stocks")
            print(f"Final results: {results.get('final_results', 0)} stocks")

            if summary.get('top_picks'):
                print("\nTop 5 recommendations:")
                for i, pick in enumerate(summary['top_picks'], 1):
                    print(f"{i}. {pick['ticker']} - Score: {pick['composite_score']:.1f} ({pick['sector']})")

        # Save results
        saved_files = save_results(results, args)

        if not args.quiet:
            print("\nResults saved to:")
            for file_path in saved_files:
                print(f"• {file_path}")

    except KeyboardInterrupt:
        print("\nAnalysis interrupted by user.")
        sys.exit(1)

    except Exception as e:
        print(f"Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
