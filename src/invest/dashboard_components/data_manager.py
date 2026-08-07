"""
DataManager - Handles data persistence, loading, and caching for the dashboard.

This component is responsible for:
- Loading and saving dashboard data to JSON files
- Managing stock data structures and initialization
- Providing data access methods for other components
- Handling data validation and cleanup
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class DataManager:
    """Manages dashboard data persistence and access."""

    def __init__(self, output_dir: str = "dashboard"):
        """
        Initialize the data manager.

        Parameters
        ----------
        output_dir : str
            Directory for dashboard files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

        self.data_file = self.output_dir / "dashboard_data.json"
        self.backup_file = self.output_dir / "dashboard_data_backup.json"

        # Load existing data or initialize empty structure
        self.data = self._load_existing_data()

    def _load_existing_data(self) -> Dict:
        """Load existing dashboard data from file."""
        if self.data_file.exists():
            try:
                with open(self.data_file, "r") as f:
                    data = json.load(f)

                # Validate data structure
                if self._validate_data_structure(data):
                    logger.info(f"Loaded existing data for {len(data.get('stocks', {}))} stocks")
                    return data
                else:
                    logger.warning("Existing data structure invalid, initializing fresh")

            except Exception as e:
                logger.warning(f"Could not load existing data: {e}")
                # Try backup file
                if self.backup_file.exists():
                    try:
                        with open(self.backup_file, "r") as f:
                            data = json.load(f)
                        if self._validate_data_structure(data):
                            logger.info("Loaded data from backup file")
                            return data
                    except Exception as backup_e:
                        logger.error(f"Backup file also corrupted: {backup_e}")

        # Return fresh data structure
        return self._create_empty_data_structure()

    def _validate_data_structure(self, data: Dict) -> bool:
        """Validate that data has the expected structure."""
        try:
            required_keys = ['stocks', 'model_status']
            return all(key in data for key in required_keys)
        except Exception:
            return False

    def _create_empty_data_structure(self) -> Dict:
        """Create empty data structure with proper schema."""
        return {
            "last_updated": None,
            "update_started": None,
            "stocks": {},
            "model_status": {
                "dcf": "not_run",
                "dcf_enhanced": "not_run",
                "simple_ratios": "not_run",
                "rim": "not_run",
                "multi_stage_dcf": "not_run",
            },
            "progress": {
                "completed": 0,
                "total": 0,
                "status": "idle",
                "current_ticker": "",
                "stocks_completed": 0,
                "total_stocks": 0,
            },
            "engine_stats": {},
        }

    def initialize_stocks(self, tickers: List[str]):
        """Initialize stock data structures for the given tickers."""
        for ticker in tickers:
            if ticker not in self.data["stocks"]:
                self.data["stocks"][ticker] = self._create_stock_structure(ticker)
            else:
                # Ensure existing stock has complete structure
                self._ensure_stock_structure(ticker)

                # Reset status for existing stocks
                stock = self.data["stocks"][ticker]
                stock["status"] = "pending"
                stock["status_message"] = "Waiting to be analyzed"
                stock["models_attempted"] = 0
                stock["models_completed"] = 0

        logger.info(f"Initialized {len(tickers)} stocks")

    def _create_stock_structure(self, ticker: str) -> Dict:
        """Create the data structure for a single stock."""
        return {
            "ticker": ticker,
            "status": "pending",
            "status_message": "Waiting to be analyzed",
            "current_price": None,
            "valuations": {},
            "models_attempted": 0,
            "models_completed": 0,
            "last_attempt": None,
            "errors": {},
            "analysis_summary": {
                "total_models": 0,
                "successful_models": 0,
                "average_fair_value": None,
                "valuation_range": None,
                "consensus_rating": None,
            },
        }

    def _ensure_stock_structure(self, ticker: str) -> Dict:
        """Ensure stock has complete structure with all required fields."""
        stock = self.data["stocks"][ticker]

        # Check and add missing required fields
        required_fields = {
            "ticker": ticker,
            "status": "pending",
            "status_message": "Waiting to be analyzed",
            "current_price": None,
            "valuations": {},
            "models_attempted": 0,
            "models_completed": 0,
            "last_attempt": None,
            "errors": {},
            "analysis_summary": {
                "total_models": 0,
                "successful_models": 0,
                "average_fair_value": None,
                "valuation_range": None,
                "consensus_rating": None,
            }
        }

        for field, default_value in required_fields.items():
            if field not in stock:
                logger.warning(f"Stock {ticker} missing field '{field}', adding default")
                stock[field] = default_value

        # Ensure analysis_summary has all required subfields
        if isinstance(stock.get("analysis_summary"), dict):
            summary_fields = {
                "total_models": 0,
                "successful_models": 0,
                "average_fair_value": None,
                "valuation_range": None,
                "consensus_rating": None,
            }
            for field, default_value in summary_fields.items():
                if field not in stock["analysis_summary"]:
                    stock["analysis_summary"][field] = default_value

        return stock

    def update_stock_data(self, ticker: str, model: str, result: Optional[Dict]):
        """Update stock data with valuation result."""
        if ticker not in self.data["stocks"]:
            self.data["stocks"][ticker] = self._create_stock_structure(ticker)

        # Ensure complete stock structure (defensive programming)
        stock = self._ensure_stock_structure(ticker)
        stock["models_attempted"] += 1
        stock["last_attempt"] = datetime.now().isoformat()

        if result:
            # Store the valuation result
            stock["valuations"][model] = result
            stock["models_completed"] += 1

            # Update current price if available
            if "current_price" in result and result["current_price"]:
                stock["current_price"] = result["current_price"]

            # Update analysis summary
            self._update_analysis_summary(ticker)

            logger.debug(f"Updated stock data: {ticker} {model}")
        else:
            # Store error information
            stock["errors"][model] = {
                "timestamp": datetime.now().isoformat(),
                "message": "Valuation failed"
            }

    def _update_analysis_summary(self, ticker: str):
        """Update analysis summary for a stock."""
        stock = self.data["stocks"][ticker]

        # Ensure stock structure is complete (defensive programming)
        if "analysis_summary" not in stock:
            logger.warning(f"Stock {ticker} missing analysis_summary field, reinitializing structure")
            stock["analysis_summary"] = {
                "total_models": 0,
                "successful_models": 0,
                "average_fair_value": None,
                "valuation_range": None,
                "consensus_rating": None,
            }

        valuations = stock.get("valuations", {})

        if not valuations:
            return

        # Calculate summary statistics
        fair_values = []
        for model, result in valuations.items():
            if not isinstance(result, dict):
                continue
            fair_value = result.get("fair_value")
            if fair_value and isinstance(fair_value, (int, float)):
                fair_values.append(fair_value)

        summary = stock["analysis_summary"]
        summary["total_models"] = len(valuations)
        summary["successful_models"] = len(fair_values)

        if fair_values:
            # Valuation range is descriptive — keep min/max/spread
            summary["valuation_range"] = {
                "min": min(fair_values),
                "max": max(fair_values),
                "spread": max(fair_values) - min(fair_values)
            }

            # Use unified consensus for average fair value and rating
            current_price = stock.get("current_price")
            if current_price and current_price > 0:
                from ..valuation.consensus import (
                    compute_consensus_from_dicts,
                    consensus_margin_to_rating,
                )

                consensus = compute_consensus_from_dicts(valuations, current_price)
                if consensus:
                    summary["average_fair_value"] = consensus.fair_value
                    summary["consensus_rating"] = consensus_margin_to_rating(consensus.margin_of_safety)
                else:
                    summary["average_fair_value"] = sum(fair_values) / len(fair_values)
            else:
                summary["average_fair_value"] = sum(fair_values) / len(fair_values)

    def update_stock_status(self, ticker: str, status: str, message: str):
        """Update stock status and message."""
        if ticker in self.data["stocks"]:
            # Ensure complete stock structure (defensive programming)
            stock = self._ensure_stock_structure(ticker)
            stock["status"] = status
            stock["status_message"] = message
            stock["last_attempt"] = datetime.now().isoformat()

    def get_stock_data(self, ticker: str) -> Optional[Dict]:
        """Get data for a specific stock."""
        return self.data["stocks"].get(ticker)

    def get_all_stocks(self) -> Dict[str, Dict]:
        """Get data for all stocks."""
        return self.data["stocks"]

    def get_progress_data(self) -> Dict:
        """Get current progress information."""
        return self.data.get("progress", {})

    def update_progress(self, progress_data: Dict):
        """Update progress information."""
        self.data["progress"].update(progress_data)

    def save_data(self):
        """Save data to file with backup."""
        try:
            # Create backup of existing file
            if self.data_file.exists():
                self.data_file.rename(self.backup_file)

            # Update timestamp
            self.data["last_updated"] = datetime.now().isoformat()

            # Save new data
            with open(self.data_file, "w") as f:
                json.dump(self.data, f, indent=2)

            logger.debug("Dashboard data saved successfully")

        except Exception as e:
            logger.error(f"Failed to save dashboard data: {e}")
            # Restore backup if save failed
            if self.backup_file.exists():
                self.backup_file.rename(self.data_file)

    def cleanup_old_data(self):
        """Clean up old stock data to prevent file from growing too large."""
        # No cleanup - keep all data without limits
        logger.info(f"Data cleanup disabled - keeping all {len(self.data['stocks'])} stocks")

    def get_data_summary(self) -> Dict:
        """Get summary statistics about the data."""
        stocks = self.data["stocks"]

        total_stocks = len(stocks)
        completed_stocks = len([s for s in stocks.values() if s["models_completed"] > 0])

        model_counts = {}
        for stock in stocks.values():
            for model in stock.get("valuations", {}):
                model_counts[model] = model_counts.get(model, 0) + 1

        return {
            "total_stocks": total_stocks,
            "completed_stocks": completed_stocks,
            "completion_rate": completed_stocks / total_stocks if total_stocks > 0 else 0,
            "model_counts": model_counts,
            "last_updated": self.data.get("last_updated"),
            "data_file_size": self.data_file.stat().st_size if self.data_file.exists() else 0,
        }
