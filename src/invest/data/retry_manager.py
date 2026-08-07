"""
Retry manager for handling failed stock data fetches.

This module provides intelligent retry logic for stocks that failed due to
circuit breaker activation, rate limiting, or temporary API issues.
"""

import time
from dataclasses import dataclass
from enum import Enum
from threading import Lock
from typing import Callable, Dict, List, Optional

from ..config.logging_config import get_logger
from .concurrent_fetcher import ConcurrentDataFetcher

logger = get_logger(__name__)


class FailureReason(Enum):
    """Types of failure that can be retried."""
    CIRCUIT_BREAKER_OPEN = "circuit_breaker_open"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    NETWORK_ERROR = "network_error"
    TEMPORARY_API_ERROR = "temporary_api_error"
    PERMANENT_ERROR = "permanent_error"  # Don't retry these


@dataclass
class RetryTask:
    """A stock that needs to be retried."""
    ticker: str
    failure_reason: FailureReason
    failure_time: float
    retry_count: int = 0
    last_retry_time: float = 0.0
    callback: Optional[Callable[[str, Optional[Dict]], None]] = None  # Called when data is available


class RetryManager:
    """Manages retrying failed stock data fetches."""

    def __init__(self, fetcher: ConcurrentDataFetcher):
        self.fetcher = fetcher
        self.retry_queue: Dict[str, RetryTask] = {}
        self.lock = Lock()
        self.max_retries = 3
        self.retry_delays = [30, 120, 300]  # 30s, 2min, 5min

    def register_failure(
        self,
        ticker: str,
        failure_reason: FailureReason,
        callback: Optional[Callable[[str, Optional[Dict]], None]] = None
    ):
        """Register a failed stock for potential retry."""
        if failure_reason == FailureReason.PERMANENT_ERROR:
            logger.info(f"Not queuing {ticker} for retry - permanent error")
            return

        with self.lock:
            if ticker in self.retry_queue:
                # Update existing retry task
                task = self.retry_queue[ticker]
                task.failure_reason = failure_reason
                task.failure_time = time.time()
            else:
                # Create new retry task
                self.retry_queue[ticker] = RetryTask(
                    ticker=ticker,
                    failure_reason=failure_reason,
                    failure_time=time.time(),
                    callback=callback
                )

        logger.info(
            f"Registered {ticker} for retry",
            extra={
                "ticker": ticker,
                "failure_reason": failure_reason.value,
                "queue_size": len(self.retry_queue)
            }
        )

    def process_retries(self) -> Dict[str, Optional[Dict]]:
        """Process all eligible retries and return successful results."""
        with self.lock:
            ready_tasks = self._get_ready_tasks()

        if not ready_tasks:
            return {}

        logger.info(f"Processing {len(ready_tasks)} retry tasks")

        # Attempt to fetch data for ready tasks
        ready_tickers = [task.ticker for task in ready_tasks]
        results = self.fetcher.fetch_multiple_stocks_basic(ready_tickers)

        successful_results = {}

        with self.lock:
            for task in ready_tasks:
                ticker = task.ticker
                data = results.get(ticker)

                if data:
                    # Success! Remove from retry queue and notify callback
                    logger.info(f"Retry successful for {ticker}")
                    successful_results[ticker] = data

                    if task.callback:
                        task.callback(ticker, data)

                    # Remove from retry queue
                    self.retry_queue.pop(ticker, None)

                else:
                    # Still failing - increment retry count
                    task.retry_count += 1
                    task.last_retry_time = time.time()

                    if task.retry_count >= self.max_retries:
                        # Give up after max retries
                        logger.warning(f"Giving up on {ticker} after {task.retry_count} retries")
                        if task.callback:
                            task.callback(ticker, None)  # Notify failure
                        self.retry_queue.pop(ticker, None)
                    else:
                        # Will retry again later
                        next_delay = self.retry_delays[min(task.retry_count - 1, len(self.retry_delays) - 1)]
                        logger.info(
                            f"Retry {task.retry_count}/{self.max_retries} failed for {ticker}, "
                            f"next attempt in {next_delay}s"
                        )

        return successful_results

    def _get_ready_tasks(self) -> List[RetryTask]:
        """Get tasks that are ready for retry."""
        ready_tasks = []
        current_time = time.time()

        for task in self.retry_queue.values():
            if task.retry_count >= self.max_retries:
                continue  # Skip exhausted retries

            # Calculate when this task should be retried
            if task.retry_count == 0:
                # First retry - based on failure type
                if task.failure_reason == FailureReason.CIRCUIT_BREAKER_OPEN:
                    retry_time = task.failure_time + 60  # Wait for circuit breaker recovery
                elif task.failure_reason == FailureReason.RATE_LIMITED:
                    retry_time = task.failure_time + 30  # Wait for rate limit reset
                else:
                    retry_time = task.failure_time + self.retry_delays[0]
            else:
                # Subsequent retries - exponential backoff
                delay = self.retry_delays[min(task.retry_count - 1, len(self.retry_delays) - 1)]
                retry_time = task.last_retry_time + delay

            if current_time >= retry_time:
                ready_tasks.append(task)

        return ready_tasks

    def get_retry_status(self) -> Dict[str, Dict]:
        """Get status of all pending retries."""
        with self.lock:
            status = {}
            current_time = time.time()

            for ticker, task in self.retry_queue.items():
                next_retry_time = self._calculate_next_retry_time(task)
                time_until_retry = max(0, next_retry_time - current_time)

                status[ticker] = {
                    "retry_count": task.retry_count,
                    "max_retries": self.max_retries,
                    "failure_reason": task.failure_reason.value,
                    "time_until_retry": time_until_retry,
                    "will_retry": task.retry_count < self.max_retries
                }

            return status

    def _calculate_next_retry_time(self, task: RetryTask) -> float:
        """Calculate when a task should be retried next."""
        if task.retry_count == 0:
            if task.failure_reason == FailureReason.CIRCUIT_BREAKER_OPEN:
                return task.failure_time + 60
            elif task.failure_reason == FailureReason.RATE_LIMITED:
                return task.failure_time + 30
            else:
                return task.failure_time + self.retry_delays[0]
        else:
            delay = self.retry_delays[min(task.retry_count - 1, len(self.retry_delays) - 1)]
            return task.last_retry_time + delay

    def clear_retries(self, tickers: Optional[List[str]] = None):
        """Clear retry queue for specific tickers or all."""
        with self.lock:
            if tickers:
                for ticker in tickers:
                    self.retry_queue.pop(ticker, None)
                logger.info(f"Cleared retry queue for {len(tickers)} tickers")
            else:
                count = len(self.retry_queue)
                self.retry_queue.clear()
                logger.info(f"Cleared entire retry queue ({count} items)")


def classify_failure_reason(error: Exception) -> FailureReason:
    """Classify an exception to determine if/how it should be retried."""
    error_str = str(error).lower()

    if "circuit breaker" in error_str:
        return FailureReason.CIRCUIT_BREAKER_OPEN
    elif "rate limit" in error_str or "too many requests" in error_str:
        return FailureReason.RATE_LIMITED
    elif "timeout" in error_str or "timed out" in error_str:
        return FailureReason.TIMEOUT
    elif "network" in error_str or "connection" in error_str:
        return FailureReason.NETWORK_ERROR
    elif "invalid ticker" in error_str or "not found" in error_str:
        return FailureReason.PERMANENT_ERROR  # Don't retry invalid tickers
    else:
        return FailureReason.TEMPORARY_API_ERROR
