from pathlib import Path
from typing import Dict

import yaml

from .schema import AnalysisConfig, SectorBenchmarks


def load_analysis_config(config_path: str | Path) -> AnalysisConfig:
    """Load analysis configuration from YAML file."""
    config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path, "r") as f:
        config_data = yaml.safe_load(f)

    return AnalysisConfig(**config_data)


def load_sector_benchmarks(benchmarks_path: str | Path) -> Dict[str, SectorBenchmarks]:
    """Load sector-specific benchmarks from YAML file."""
    benchmarks_path = Path(benchmarks_path)

    if not benchmarks_path.exists():
        return {}  # Return empty dict if no benchmarks file

    with open(benchmarks_path, "r") as f:
        benchmarks_data = yaml.safe_load(f)

    benchmarks = {}
    for sector_name, sector_data in benchmarks_data.items():
        benchmarks[sector_name] = SectorBenchmarks(sector=sector_name, **sector_data)

    return benchmarks


def get_default_config_path() -> Path:
    """Get path to default configuration file."""
    # Look for configs directory relative to this file
    current_dir = Path(__file__).parent
    project_root = current_dir.parent.parent.parent  # Go up to project root
    configs_dir = project_root / "dashboard" / "configs"

    return configs_dir / "default_analysis.yaml"


def list_available_configs() -> list[Path]:
    """List all available configuration files."""
    current_dir = Path(__file__).parent
    project_root = current_dir.parent.parent.parent
    configs_dir = project_root / "dashboard" / "configs"

    if not configs_dir.exists():
        return []

    return list(configs_dir.glob("*.yaml"))


def create_example_config(output_path: str | Path) -> None:
    """Create an example configuration file."""
    example_config = {
        "name": "example_analysis",
        "description": "Example configuration showing all available options",
        "universe": {
            "region": "US",
            "min_market_cap": 1000,
            "max_market_cap": None,
            "sectors": None,
            "exclude_sectors": ["Utilities"],
            "custom_tickers": None,
        },
        "quality": {
            "min_roic": 0.12,
            "min_roe": 0.15,
            "min_current_ratio": 1.2,
            "max_debt_equity": 0.6,
            "min_interest_coverage": 3.0,
        },
        "value": {
            "max_pe": 25,
            "max_pb": 3.5,
            "max_ev_ebitda": 15,
            "max_ev_ebit": 12,
            "max_p_fcf": 20,
        },
        "growth": {
            "min_revenue_growth": 0.05,
            "min_earnings_growth": 0.10,
            "min_fcf_growth": 0.05,
            "min_book_value_growth": 0.08,
        },
        "risk": {
            "max_beta": 1.5,
            "min_liquidity_ratio": 1.0,
            "max_concentration_risk": 0.3,
            "cyclical_adjustment": True,
        },
        "valuation": {
            "models": ["dcf", "rim"],
            "scenarios": ["bear", "base", "bull"],
            "dcf_years": 10,
            "terminal_growth_rate": 0.025,
            "risk_free_rate": None,
            "rim_years": 10,
            "required_return": None,
        },
        "max_results": 50,
        "sort_by": "composite_score",
        "generate_reports": True,
        "save_data": True,
    }

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        yaml.dump(example_config, f, default_flow_style=False, indent=2)
