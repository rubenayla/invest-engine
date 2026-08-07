"""
Main Opportunity Scanner Orchestration

Coordinates:
1. Scoring all stocks in universe
2. Dynamic threshold management
3. Recording history
4. Generating notifications
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from ..data.stock_data_reader import StockDataReader
from .scoring_engine import ScoringEngine, OpportunityScore
from .threshold_manager import ThresholdManager
from .telegram_notifier import TelegramNotifier


logger = logging.getLogger(__name__)


@dataclass
class ScanResult:
    """Result of a daily scan."""
    date: str
    threshold_used: float
    stocks_scanned: int
    stocks_above_threshold: int
    best_opportunity: Optional[OpportunityScore]
    notification_sent: bool
    notification_message: Optional[str]
    top_10_scores: List[OpportunityScore]


class OpportunityScanner:
    """
    Daily opportunity scanning system.

    Workflow:
    1. Load stock universe
    2. Score all stocks using ScoringEngine
    3. Get dynamic threshold from ThresholdManager
    4. Identify opportunities above threshold
    5. Record all scores and threshold to history
    6. Generate notification for best opportunity (if any)
    """

    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        db_path: Optional[Path] = None
    ):
        """
        Initialize the opportunity scanner.

        Parameters
        ----------
        weights : dict, optional
            Custom component weights for scoring
        db_path : Path, optional
            Path to SQLite database
        """
        self.scoring_engine = ScoringEngine(weights=weights)
        self.threshold_manager = ThresholdManager(db_path=db_path)
        self.notifier = TelegramNotifier()
        self.reader = StockDataReader(db_path=db_path)

    def scan(
        self,
        tickers: Optional[List[str]] = None,
        date: Optional[str] = None,
        dry_run: bool = False
    ) -> ScanResult:
        """
        Run the daily opportunity scan.

        Parameters
        ----------
        tickers : list, optional
            List of tickers to scan. If None, scans all in database.
        date : str, optional
            Date string (YYYY-MM-DD). Defaults to today.
        dry_run : bool
            If True, don't record to database or send notifications

        Returns
        -------
        ScanResult
            Complete scan results
        """
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')

        # Get universe
        if tickers is None:
            tickers = self.reader.get_all_tickers()

        logger.info(f"Scanning {len(tickers)} stocks for {date}")

        # Score all stocks
        all_scores = self.scoring_engine.score_universe(tickers)
        logger.info(f"Scored {len(all_scores)} stocks successfully")

        # Get dynamic threshold
        threshold = self.threshold_manager.calculate_adjusted_threshold()
        logger.info(f"Current threshold: {threshold}")

        # Find opportunities above threshold
        above_threshold = [s for s in all_scores if s.opportunity_score >= threshold]
        exceptional = [s for s in all_scores if s.opportunity_score >= self.threshold_manager.MAX_THRESHOLD]

        # Best opportunity
        best = all_scores[0] if all_scores else None
        best_score = best.opportunity_score if best else None

        # Determine if we should notify (for all stocks above threshold)
        notification_sent = False
        notification_message = None

        if above_threshold and self.threshold_manager.should_notify(above_threshold[0].opportunity_score):
            messages = []
            for stock in above_threshold[:5]:  # Cap at top 5 to avoid spam
                is_exceptional = stock.opportunity_score >= self.threshold_manager.MAX_THRESHOLD
                messages.append(self.notifier.format_notification(
                    stock, threshold, is_exceptional
                ))
            notification_message = '\n---\n'.join(messages)
            notification_sent = True
            tickers_str = ', '.join(s.ticker for s in above_threshold[:5])
            logger.info(f"Notification triggered for {tickers_str}")

        # Record to database (unless dry run)
        if not dry_run:
            # Record scores
            score_tuples = [
                (
                    s.ticker,
                    s.opportunity_score,
                    s.quality_score,
                    s.value_score,
                    s.growth_score,
                    s.risk_score,
                    s.catalyst_score
                )
                for s in all_scores
            ]
            self.threshold_manager.record_scores(date, score_tuples)

            # Record threshold and result
            self.threshold_manager.record_daily_scan(
                date=date,
                threshold=threshold,
                best_score=best_score,
                stocks_above=len(above_threshold),
                notification_sent=notification_sent,
                notified_ticker=best.ticker if notification_sent else None
            )

        # Prepare result
        return ScanResult(
            date=date,
            threshold_used=threshold,
            stocks_scanned=len(tickers),
            stocks_above_threshold=len(above_threshold),
            best_opportunity=best,
            notification_sent=notification_sent,
            notification_message=notification_message,
            top_10_scores=all_scores[:10]
        )

    def get_status(self) -> Dict[str, Any]:
        """
        Get current scanner status for monitoring.

        Returns
        -------
        dict
            Status information
        """
        state = self.threshold_manager.get_state()
        recent_history = self.threshold_manager.get_threshold_history(days=7)

        return {
            'current_threshold': state.current_threshold,
            'notification_rate_per_week': state.recent_notification_rate,
            'days_since_last_notification': state.days_since_last_notification,
            'min_threshold': self.threshold_manager.MIN_THRESHOLD,
            'max_threshold': self.threshold_manager.MAX_THRESHOLD,
            'target_rate': self.threshold_manager.TARGET_NOTIFICATIONS_PER_WEEK,
            'recent_history': recent_history,
        }

    def preview_top_opportunities(
        self,
        tickers: Optional[List[str]] = None,
        limit: int = 10
    ) -> List[OpportunityScore]:
        """
        Preview top opportunities without recording.

        Parameters
        ----------
        tickers : list, optional
            Tickers to scan
        limit : int
            Number of top opportunities to return

        Returns
        -------
        list
            Top OpportunityScore objects
        """
        if tickers is None:
            tickers = self.reader.get_all_tickers()

        scores = self.scoring_engine.score_universe(tickers)
        return scores[:limit]

    def backtest_threshold(
        self,
        start_date: str,
        end_date: str
    ) -> Dict[str, Any]:
        """
        Analyze threshold behavior over a date range.

        Note: This requires historical score data to be present.

        Parameters
        ----------
        start_date : str
            Start date (YYYY-MM-DD)
        end_date : str
            End date (YYYY-MM-DD)

        Returns
        -------
        dict
            Backtest analysis results
        """
        history = self.threshold_manager.get_threshold_history(days=365)

        # Filter to date range
        history = [
            h for h in history
            if start_date <= h['date'] <= end_date
        ]

        if not history:
            return {'error': 'No history data in date range'}

        notifications = sum(1 for h in history if h['notification_sent'])
        thresholds = [h['threshold'] for h in history]
        best_scores = [h['best_score'] for h in history if h['best_score']]

        days = len(history)
        weeks = days / 7

        return {
            'date_range': f"{start_date} to {end_date}",
            'days_analyzed': days,
            'total_notifications': notifications,
            'notifications_per_week': notifications / weeks if weeks > 0 else 0,
            'avg_threshold': sum(thresholds) / len(thresholds) if thresholds else 0,
            'min_threshold': min(thresholds) if thresholds else 0,
            'max_threshold': max(thresholds) if thresholds else 0,
            'avg_best_score': sum(best_scores) / len(best_scores) if best_scores else 0,
            'max_best_score': max(best_scores) if best_scores else 0,
        }

    def generate_weekly_report(self) -> str:
        """
        Generate a weekly summary report.

        Returns
        -------
        str
            Formatted weekly report
        """
        history = self.threshold_manager.get_threshold_history(days=7)

        notifications = sum(1 for h in history if h['notification_sent'])
        thresholds = [h['threshold'] for h in history]
        avg_threshold = sum(thresholds) / len(thresholds) if thresholds else 0
        current_threshold = self.threshold_manager.calculate_adjusted_threshold()

        # Get top scores from the week
        top_scores = []
        for h in history:
            if h['best_score'] and h['notified_ticker']:
                top_scores.append((h['notified_ticker'], h['best_score']))

        # Sort by score
        top_scores.sort(key=lambda x: x[1], reverse=True)

        return self.notifier.format_weekly_summary(
            notifications_sent=notifications,
            top_scores=top_scores,
            avg_threshold=avg_threshold,
            current_threshold=current_threshold
        )
