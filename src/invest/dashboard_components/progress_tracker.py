"""
ProgressTracker - Tracks and manages dashboard update progress.

This component is responsible for:
- Tracking progress of valuation updates across stocks and models
- Providing progress information for UI updates
- Managing completion statistics and timing
- Generating progress summaries and status reports
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ProgressState:
    """Data class to hold progress state information."""
    completed_tasks: int = 0
    total_tasks: int = 0
    status: str = "idle"  # idle, running, completed, error
    current_ticker: str = ""
    current_model: str = ""
    stocks_completed: int = 0
    total_stocks: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    errors: List[str] = field(default_factory=list)


class ProgressTracker:
    """Tracks progress of dashboard updates and provides status information."""

    def __init__(self):
        """Initialize the progress tracker."""
        self.state = ProgressState()
        self.stock_progress = {}  # ticker -> {models_attempted, models_completed}
        self.model_progress = {}  # model -> {stocks_attempted, stocks_completed}

    def initialize_progress(self, tickers: List[str], models: List[str]):
        """
        Initialize progress tracking for a new update cycle.

        Parameters
        ----------
        tickers : List[str]
            List of stock tickers to analyze
        models : List[str]
            List of valuation models to run
        """
        self.state = ProgressState(
            total_tasks=len(tickers) * len(models),
            total_stocks=len(tickers),
            status="running",
            start_time=datetime.now()
        )

        # Initialize per-stock progress
        self.stock_progress = {
            ticker: {"models_attempted": 0, "models_completed": 0, "status": "pending"}
            for ticker in tickers
        }

        # Initialize per-model progress
        self.model_progress = {
            model: {"stocks_attempted": 0, "stocks_completed": 0}
            for model in models
        }

        logger.info(f"Progress initialized: {len(tickers)} stocks × {len(models)} models = {self.state.total_tasks} tasks")

    def start_task(self, ticker: str, model: str):
        """Mark the start of a valuation task."""
        self.state.current_ticker = ticker
        self.state.current_model = model

        # Update stock progress
        if ticker in self.stock_progress:
            self.stock_progress[ticker]["models_attempted"] += 1
            if self.stock_progress[ticker]["status"] == "pending":
                self.stock_progress[ticker]["status"] = "in_progress"

        # Update model progress
        if model in self.model_progress:
            self.model_progress[model]["stocks_attempted"] += 1

        logger.debug(f"Started task: {ticker} {model}")

    def complete_task(self, ticker: str, model: str, success: bool = True, error_message: str = None):
        """Mark the completion of a valuation task."""
        self.state.completed_tasks += 1

        # Update stock progress
        if ticker in self.stock_progress:
            if success:
                self.stock_progress[ticker]["models_completed"] += 1

            # Check if all models for this stock are done
            models_attempted = self.stock_progress[ticker]["models_attempted"]
            total_models = len(self.model_progress)

            if models_attempted >= total_models:
                self.stock_progress[ticker]["status"] = "completed"
                self.state.stocks_completed += 1

        # Update model progress
        if model in self.model_progress and success:
            self.model_progress[model]["stocks_completed"] += 1

        # Track errors
        if not success and error_message:
            self.state.errors.append(f"{ticker} {model}: {error_message}")

        # Check if all tasks are complete
        if self.state.completed_tasks >= self.state.total_tasks:
            self.finish_progress()

        logger.debug(f"Completed task: {ticker} {model} (success={success})")

    def finish_progress(self):
        """Mark the progress as finished."""
        self.state.status = "completed"
        self.state.end_time = datetime.now()
        self.state.current_ticker = ""
        self.state.current_model = ""

        logger.info(f"Progress completed: {self.state.completed_tasks}/{self.state.total_tasks} tasks")

    def set_error_state(self, error_message: str):
        """Set the progress state to error."""
        self.state.status = "error"
        self.state.end_time = datetime.now()
        self.state.errors.append(f"Global error: {error_message}")

        logger.error(f"Progress error: {error_message}")

    def get_progress_info(self) -> Dict:
        """Get current progress information for UI display."""
        # Calculate elapsed time
        elapsed_seconds = 0
        if self.state.start_time:
            end_time = self.state.end_time or datetime.now()
            elapsed_seconds = (end_time - self.state.start_time).total_seconds()

        # Calculate completion percentage
        completion_pct = 0
        if self.state.total_tasks > 0:
            completion_pct = (self.state.completed_tasks / self.state.total_tasks) * 100

        # Calculate estimated time remaining
        eta_seconds = 0
        if self.state.completed_tasks > 0 and self.state.status == "running":
            avg_time_per_task = elapsed_seconds / self.state.completed_tasks
            remaining_tasks = self.state.total_tasks - self.state.completed_tasks
            eta_seconds = avg_time_per_task * remaining_tasks

        return {
            "status": self.state.status,
            "completed_tasks": self.state.completed_tasks,
            "total_tasks": self.state.total_tasks,
            "completion_percentage": round(completion_pct, 1),
            "current_ticker": self.state.current_ticker,
            "current_model": self.state.current_model,
            "stocks_completed": self.state.stocks_completed,
            "total_stocks": self.state.total_stocks,
            "elapsed_seconds": int(elapsed_seconds),
            "eta_seconds": int(eta_seconds),
            "error_count": len(self.state.errors),
            "latest_errors": self.state.errors[-5:],  # Last 5 errors
        }

    def get_stock_progress(self, ticker: str) -> Dict:
        """Get progress information for a specific stock."""
        return self.stock_progress.get(ticker, {})

    def get_model_progress(self, model: str) -> Dict:
        """Get progress information for a specific model."""
        return self.model_progress.get(model, {})

    def get_detailed_progress(self) -> Dict:
        """Get detailed progress information including per-stock and per-model stats."""
        return {
            "overall": self.get_progress_info(),
            "by_stock": self.stock_progress.copy(),
            "by_model": self.model_progress.copy(),
        }

    def generate_progress_summary(self) -> str:
        """Generate a human-readable progress summary."""
        info = self.get_progress_info()

        if info["status"] == "idle":
            return "Dashboard update not started"

        if info["status"] == "running":
            return (
                f"Progress: {info['completion_percentage']:.1f}% "
                f"({info['completed_tasks']}/{info['total_tasks']} tasks) • "
                f"Current: {info['current_ticker']} {info['current_model']} • "
                f"ETA: {info['eta_seconds']//60}m {info['eta_seconds']%60}s"
            )

        if info["status"] == "completed":
            return (
                f"Completed: {info['completed_tasks']} tasks in "
                f"{info['elapsed_seconds']//60}m {info['elapsed_seconds']%60}s"
            )

        if info["status"] == "error":
            return f"Failed with {info['error_count']} errors after {info['elapsed_seconds']//60}m {info['elapsed_seconds']%60}s"

        return f"Status: {info['status']}"

    def reset(self):
        """Reset progress tracker to initial state."""
        self.state = ProgressState()
        self.stock_progress.clear()
        self.model_progress.clear()

        logger.info("Progress tracker reset")

    def is_complete(self) -> bool:
        """Check if progress is complete."""
        return self.state.status in ["completed", "error"]

    def is_running(self) -> bool:
        """Check if progress is currently running."""
        return self.state.status == "running"
