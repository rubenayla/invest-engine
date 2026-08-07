"""
StockPrioritizer - Handles stock analysis prioritization logic.

This component is responsible for:
- Determining which stocks should be analyzed first
- Prioritizing based on data freshness, completeness, and previous failures
- Providing intelligent ordering to optimize dashboard updates
- Avoiding rate limits by spacing out API-heavy operations
"""

import logging
from datetime import datetime
from enum import Enum
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


class Priority(Enum):
    """Priority levels for stock analysis."""
    NEVER_ANALYZED = 1      # Highest priority - never analyzed
    INCOMPLETE = 2          # High priority - missing models
    FAILED_PREVIOUSLY = 3   # Medium priority - failed before, retry
    STALE_DATA = 4          # Low priority - old but complete data
    COMPLETE_RECENT = 5     # Lowest priority - complete and recent


class StockPrioritizer:
    """Handles prioritization of stocks for analysis."""

    def __init__(self):
        """Initialize the stock prioritizer."""
        self.priority_weights = {
            Priority.NEVER_ANALYZED: 1.0,
            Priority.INCOMPLETE: 2.0,
            Priority.FAILED_PREVIOUSLY: 3.0,
            Priority.STALE_DATA: 4.0,
            Priority.COMPLETE_RECENT: 5.0,
        }

    def prioritize_stocks(self, tickers: List[str], stock_data: Dict[str, Dict]) -> List[str]:
        """
        Prioritize stocks for analysis based on their current state.

        Parameters
        ----------
        tickers : List[str]
            List of stock tickers to prioritize
        stock_data : Dict[str, Dict]
            Current data for each stock

        Returns
        -------
        List[str]
            Prioritized list of tickers
        """
        # Calculate priority score for each stock
        stock_priorities = []
        for ticker in tickers:
            priority, score, reason = self._calculate_priority(ticker, stock_data)
            stock_priorities.append((ticker, priority, score, reason))

        # Sort by priority (lower number = higher priority)
        prioritized = sorted(stock_priorities, key=lambda x: (x[1].value, x[2], x[0]))

        # Log prioritization summary
        self._log_prioritization_summary(prioritized)

        # Return just the ticker symbols in priority order
        return [ticker for ticker, _, _, _ in prioritized]

    def _calculate_priority(self, ticker: str, stock_data: Dict[str, Dict]) -> Tuple[Priority, float, str]:
        """
        Calculate priority for a single stock.

        Returns
        -------
        Tuple[Priority, float, str]
            Priority level, secondary score (for tie-breaking), and reason
        """
        stock = stock_data.get(ticker, {})

        # Priority 1: Never analyzed stocks (no valuations)
        valuations = stock.get("valuations", {})
        if not valuations:
            return Priority.NEVER_ANALYZED, 0.0, "never_analyzed"

        # Priority 2: Incomplete analysis (< 6 models)
        completed_models = len(valuations)
        expected_models = 6  # DCF, Enhanced DCF, Simple Ratios, RIM, Multi-Stage DCF, Black-Scholes

        if completed_models < expected_models:
            # Secondary score: fewer models = higher priority (lower score)
            score = completed_models / expected_models
            return Priority.INCOMPLETE, score, f"incomplete_{completed_models}_{expected_models}"

        # Priority 3: Previously failed stocks
        status = stock.get("status", "pending")
        if status in ["rate_limited", "data_missing", "model_failed", "error"]:
            # Secondary score based on how long ago the failure was
            last_attempt = stock.get("last_attempt")
            if last_attempt:
                try:
                    last_time = datetime.fromisoformat(last_attempt)
                    hours_since_failure = (datetime.now() - last_time).total_seconds() / 3600
                    # More recent failures get lower priority (higher score)
                    score = min(hours_since_failure / 24.0, 1.0)  # Normalize to 0-1 over 24 hours
                    return Priority.FAILED_PREVIOUSLY, score, f"failed_{status}"
                except ValueError:
                    pass

            return Priority.FAILED_PREVIOUSLY, 0.5, f"failed_{status}"

        # Priority 4: Stale data (complete but old)
        last_attempt = stock.get("last_attempt")
        if last_attempt:
            try:
                last_time = datetime.fromisoformat(last_attempt)
                age_hours = (datetime.now() - last_time).total_seconds() / 3600

                # Consider data stale if older than 24 hours
                if age_hours > 24:
                    # Older data gets higher priority (lower score)
                    days_old = age_hours / 24.0
                    score = max(0.0, 1.0 - (days_old / 7.0))  # Priority decreases over a week
                    return Priority.STALE_DATA, score, f"stale_{days_old:.1f}_days"
            except ValueError:
                pass

        # Priority 5: Complete and recent (lowest priority)
        return Priority.COMPLETE_RECENT, 1.0, "complete_recent"

    def _log_prioritization_summary(self, prioritized: List[Tuple]):
        """Log a summary of the prioritization results."""
        priority_counts = {}
        for _, priority, _, _ in prioritized:
            priority_counts[priority] = priority_counts.get(priority, 0) + 1

        logger.info(f"Prioritized {len(prioritized)} stocks:")
        for priority in Priority:
            count = priority_counts.get(priority, 0)
            if count > 0:
                logger.info(f"  {priority.name}: {count} stocks")

    def get_priority_explanation(self, ticker: str, stock_data: Dict[str, Dict]) -> str:
        """Get a human-readable explanation of why a stock has its priority."""
        priority, score, reason = self._calculate_priority(ticker, stock_data)

        explanations = {
            Priority.NEVER_ANALYZED: "Never analyzed - highest priority for first-time analysis",
            Priority.INCOMPLETE: f"Incomplete analysis - missing models (reason: {reason})",
            Priority.FAILED_PREVIOUSLY: f"Previously failed - retry needed (reason: {reason})",
            Priority.STALE_DATA: f"Stale data - needs refresh (reason: {reason})",
            Priority.COMPLETE_RECENT: "Complete and recent - lowest priority",
        }

        return explanations.get(priority, f"Unknown priority: {priority}")

    def should_throttle_analysis(self, completed_count: int, total_count: int) -> bool:
        """
        Determine if analysis should be throttled to avoid rate limits.

        Parameters
        ----------
        completed_count : int
            Number of stocks completed so far
        total_count : int
            Total number of stocks being analyzed

        Returns
        -------
        bool
            True if analysis should be slowed down
        """
        # Throttle if we've done a lot of work in a short time
        completion_rate = completed_count / total_count if total_count > 0 else 0

        # Throttle more aggressively as we progress to avoid hitting rate limits
        if completion_rate > 0.8:  # In final 20%
            return True
        elif completion_rate > 0.6:  # In final 40%
            return completed_count % 3 == 0  # Throttle every 3rd stock
        elif completion_rate > 0.4:  # In middle 40%
            return completed_count % 5 == 0  # Throttle every 5th stock

        return False

    def get_recommended_batch_size(self, total_stocks: int) -> int:
        """
        Get recommended batch size for concurrent processing.

        Parameters
        ----------
        total_stocks : int
            Total number of stocks to analyze

        Returns
        -------
        int
            Recommended number of concurrent workers
        """
        # Conservative approach to avoid rate limits
        if total_stocks > 100:
            return 2  # Very conservative for large batches
        elif total_stocks > 50:
            return 3  # Still conservative
        elif total_stocks > 20:
            return 4  # Moderate
        else:
            return 5  # More aggressive for small batches

    def estimate_completion_time(self, total_stocks: int, avg_time_per_stock: float = 30.0) -> int:
        """
        Estimate total completion time in seconds.

        Parameters
        ----------
        total_stocks : int
            Number of stocks to analyze
        avg_time_per_stock : float
            Average time per stock in seconds

        Returns
        -------
        int
            Estimated completion time in seconds
        """
        batch_size = self.get_recommended_batch_size(total_stocks)

        # Account for batching efficiency
        batches = (total_stocks + batch_size - 1) // batch_size
        time_per_batch = avg_time_per_stock * 5  # 5 models per stock

        # Add overhead for rate limiting and coordination
        overhead_factor = 1.2

        return int(batches * time_per_batch * overhead_factor)
