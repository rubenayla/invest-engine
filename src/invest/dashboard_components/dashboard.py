"""
ValuationDashboard - Main orchestrator for the modular dashboard components.

This is the main interface that brings together all the modular components:
- ValuationEngine: Executes valuation models
- DataManager: Handles data persistence
- ProgressTracker: Tracks update progress
- HTMLGenerator: Generates dashboard HTML
- StockPrioritizer: Prioritizes stock analysis

This maintains the same public interface as the original dashboard while
providing better maintainability and testability through modularity.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional

from ..config.constants import ANALYSIS_LIMITS
from .data_manager import DataManager
from .html_generator import HTMLGenerator
from .progress_tracker import ProgressTracker
from .stock_prioritizer import StockPrioritizer
from .valuation_engine import ValuationEngine

logger = logging.getLogger(__name__)


class ValuationDashboard:
    """
    Modular investment dashboard that orchestrates valuation analysis.

    This is the main interface that coordinates all dashboard components
    to provide a comprehensive stock valuation dashboard with real-time updates.
    """

    def __init__(self, output_dir: str = "dashboard"):
        """
        Initialize the modular dashboard.

        Parameters
        ----------
        output_dir : str
            Directory for dashboard output files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

        # Initialize all components
        self.valuation_engine = ValuationEngine()
        self.data_manager = DataManager(output_dir)
        self.progress_tracker = ProgressTracker()
        self.html_generator = HTMLGenerator(output_dir)
        self.stock_prioritizer = StockPrioritizer()

        logger.info(f"Modular dashboard initialized with output directory: {output_dir}")

    def update_dashboard(
        self,
        tickers: List[str],
        timeout_per_stock: int = ANALYSIS_LIMITS.DEFAULT_TIMEOUT_PER_STOCK
    ):
        """
        Update dashboard with latest valuations using modular components.

        Parameters
        ----------
        tickers : List[str]
            Stock tickers to analyze
        timeout_per_stock : int
            Max seconds per stock per model (prevents hanging)
        """
        logger.info(f"Starting modular dashboard update for {len(tickers)} stocks")

        try:
            # Initialize data and progress tracking
            self.data_manager.initialize_stocks(tickers)

            # Get available models and prioritize stocks
            available_models = self.valuation_engine.get_available_models()
            prioritized_tickers = self.stock_prioritizer.prioritize_stocks(
                tickers, self.data_manager.get_all_stocks()
            )

            # Initialize progress tracking
            self.progress_tracker.initialize_progress(prioritized_tickers, available_models)

            # Generate initial HTML
            self._generate_and_save_html()
            print(f"Dashboard available at: {self.html_generator.html_file.absolute()}")

            # Get recommended concurrent workers
            max_workers = self.stock_prioritizer.get_recommended_batch_size(len(tickers))
            logger.info(f"Using {max_workers} concurrent workers for analysis")

            # Execute valuations with controlled concurrency
            self._execute_valuations(
                prioritized_tickers,
                available_models,
                max_workers,
                timeout_per_stock
            )

            # Final cleanup and HTML generation
            self._finalize_dashboard()

        except Exception as e:
            logger.error(f"Dashboard update failed: {e}")
            self.progress_tracker.set_error_state(str(e))
            self._generate_and_save_html()
            raise

    def _execute_valuations(
        self,
        tickers: List[str],
        models: List[str],
        max_workers: int,
        timeout_per_stock: int
    ):
        """Execute valuation tasks using ThreadPoolExecutor."""
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all valuation tasks
            future_to_info = {}

            for ticker in tickers:
                for model in models:
                    future = executor.submit(
                        self._execute_single_valuation,
                        ticker,
                        model,
                        timeout_per_stock
                    )
                    future_to_info[future] = (ticker, model)

            # Process results as they complete
            completed_count = 0
            total_tasks = len(future_to_info)

            for future in as_completed(future_to_info, timeout=timeout_per_stock * len(tickers)):
                ticker, model = future_to_info[future]
                completed_count += 1

                try:
                    # Get the result
                    result = future.result()

                    # Update progress and data
                    success = result is not None
                    self.progress_tracker.complete_task(ticker, model, success)
                    self.data_manager.update_stock_data(ticker, model, result)

                    # Update status
                    if success:
                        logger.debug(f"Completed: {ticker} {model}")
                    else:
                        logger.warning(f"Failed: {ticker} {model}")
                        self.data_manager.update_stock_status(
                            ticker, "model_failed", f"{model} valuation failed"
                        )

                    # Periodic HTML updates and throttling
                    if completed_count % 10 == 0 or self.progress_tracker.is_complete():
                        self._generate_and_save_html()

                        # Check if we should throttle
                        if self.stock_prioritizer.should_throttle_analysis(completed_count, total_tasks):
                            logger.info("Throttling analysis to avoid rate limits")
                            import time
                            time.sleep(2)

                except Exception as e:
                    logger.error(f"Task execution error for {ticker} {model}: {e}")
                    self.progress_tracker.complete_task(ticker, model, False, str(e))
                    self.data_manager.update_stock_status(ticker, "model_failed", str(e))

    def _execute_single_valuation(self, ticker: str, model: str, timeout: int) -> Optional[dict]:
        """Execute a single valuation task."""
        # Notify progress tracker
        self.progress_tracker.start_task(ticker, model)

        # Update stock status
        self.data_manager.update_stock_status(ticker, "analyzing", f"Running {model} model")

        # Execute the valuation
        result = self.valuation_engine.run_valuation(ticker, model, timeout)

        # Update stock status based on result
        if result:
            completed_models = len(self.data_manager.get_stock_data(ticker).get("valuations", {})) + 1
            if completed_models >= len(self.valuation_engine.get_available_models()):
                self.data_manager.update_stock_status(ticker, "completed", "All models completed")

        return result

    def _generate_and_save_html(self):
        """Generate and save the dashboard HTML."""
        try:
            stocks_data = self.data_manager.get_all_stocks()
            progress_data = self.progress_tracker.get_progress_info()
            metadata = {
                "last_updated": self.data_manager.data.get("last_updated"),
                "engine_stats": self.valuation_engine.get_model_statistics(),
            }

            html_content = self.html_generator.generate_dashboard_html(
                stocks_data, progress_data, metadata
            )
            self.html_generator.save_html(html_content)

            # Also save data
            self.data_manager.save_data()

        except Exception as e:
            logger.error(f"Failed to generate HTML: {e}")

    def _finalize_dashboard(self):
        """Finalize the dashboard after all processing is complete."""
        # Mark progress as finished
        self.progress_tracker.finish_progress()

        # Update data manager with engine statistics
        self.data_manager.data["engine_stats"] = self.valuation_engine.get_model_statistics()

        # Final HTML generation
        self._generate_and_save_html()

        # Cleanup old data to prevent files from growing too large
        self.data_manager.cleanup_old_data()

        # Log summary
        data_summary = self.data_manager.get_data_summary()
        engine_stats = self.valuation_engine.get_model_statistics()

        logger.info("Dashboard update completed:")
        logger.info(f"  - Stocks analyzed: {data_summary['completed_stocks']}/{data_summary['total_stocks']}")
        logger.info(f"  - Completion rate: {data_summary['completion_rate']:.1%}")

        for model, stats in engine_stats.items():
            if stats['attempts'] > 0:
                logger.info(f"  - {model}: {stats['successes']}/{stats['attempts']} ({stats['success_rate']:.1%})")

    # Public interface methods for compatibility

    def get_progress_info(self) -> dict:
        """Get current progress information."""
        return self.progress_tracker.get_progress_info()

    def get_stock_data(self, ticker: str) -> Optional[dict]:
        """Get data for a specific stock."""
        return self.data_manager.get_stock_data(ticker)

    def get_all_stocks(self) -> dict:
        """Get data for all stocks."""
        return self.data_manager.get_all_stocks()

    def get_dashboard_summary(self) -> dict:
        """Get comprehensive dashboard summary."""
        return {
            "data_summary": self.data_manager.get_data_summary(),
            "engine_stats": self.valuation_engine.get_model_statistics(),
            "progress_info": self.progress_tracker.get_progress_info(),
        }

    def reset_dashboard(self):
        """Reset the dashboard to initial state."""
        self.progress_tracker.reset()
        self.valuation_engine.reset_statistics()
        # Note: We don't reset data_manager as it contains valuable historical data
        logger.info("Dashboard components reset")


# Convenience function for backward compatibility
def create_dashboard(tickers: List[str] = None) -> str:
    """
    Create a dashboard with the given tickers.

    This function maintains backward compatibility with the original dashboard API.

    Parameters
    ----------
    tickers : List[str], optional
        Stock tickers to analyze

    Returns
    -------
    str
        Path to the generated dashboard HTML file
    """
    if not tickers:
        # Default tickers for demonstration
        tickers = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA']

    dashboard = ValuationDashboard()
    dashboard.update_dashboard(tickers)

    return str(dashboard.html_generator.html_file)
