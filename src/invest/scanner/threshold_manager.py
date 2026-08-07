"""
Dynamic Threshold Manager for Opportunity Scanner

Adjusts the notification threshold to maintain an average of ~1 notification per week.
The scoring formula never changes - only "how good does an opportunity need to be today?"
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Tuple

from invest.data.db import get_connection


@dataclass
class ThresholdState:
    """Current state of the threshold manager."""
    current_threshold: float
    recent_notification_rate: float  # Notifications per week
    days_since_last_notification: int
    best_score_today: Optional[float]
    stocks_above_threshold: int


class ThresholdManager:
    """
    Dynamic threshold management for opportunity notifications.

    Core principle:
    - TARGET_NOTIFICATIONS_PER_WEEK = 1.0
    - MIN_THRESHOLD = 65 (never notify below this - quality floor)
    - MAX_THRESHOLD = 90 (always notify above this - exceptional)
    """

    TARGET_NOTIFICATIONS_PER_WEEK = 1.0
    MIN_THRESHOLD = 65.0
    MAX_THRESHOLD = 90.0

    # Adjustment parameters
    ADJUSTMENT_STEP = 1.0  # How much to adjust per day
    DRY_SPELL_DAYS = 21    # Emergency lower after this many days
    RATE_LOW = 0.5         # Rate below this: lower threshold
    RATE_HIGH = 1.5        # Rate above this: raise threshold

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize threshold manager.

        Parameters
        ----------
        db_path : Path, optional
            Ignored (kept for backward compatibility). Connections come from get_connection().
        """
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """Create scanner tables if they don't exist."""
        conn = get_connection()
        cursor = conn.cursor()

        # Threshold history table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS scanner_threshold_history (
                id SERIAL PRIMARY KEY,
                date TEXT NOT NULL,
                threshold REAL NOT NULL,
                best_score REAL,
                stocks_above INTEGER DEFAULT 0,
                notification_sent INTEGER DEFAULT 0,
                notified_ticker TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date)
            )
        ''')

        # Score history table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS scanner_score_history (
                id SERIAL PRIMARY KEY,
                date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                opportunity_score REAL NOT NULL,
                quality_score REAL,
                value_score REAL,
                growth_score REAL,
                risk_score REAL,
                catalyst_score REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date, ticker)
            )
        ''')

        # Create indexes
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_threshold_date
            ON scanner_threshold_history(date)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_score_date_ticker
            ON scanner_score_history(date, ticker)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_score_opportunity
            ON scanner_score_history(opportunity_score DESC)
        ''')

        conn.commit()
        conn.close()

    def get_current_threshold(self) -> float:
        """
        Get the current notification threshold.

        If no history exists, starts at midpoint between MIN and MAX.
        """
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT threshold FROM scanner_threshold_history
            ORDER BY date DESC LIMIT 1
        ''')
        row = cursor.fetchone()
        conn.close()

        if row:
            return row[0]

        # Default starting threshold (slightly above midpoint)
        return (self.MIN_THRESHOLD + self.MAX_THRESHOLD) / 2 + 2.5  # 80.0

    def get_notification_rate(self, days: int = 28) -> float:
        """
        Calculate recent notification rate (per week).

        Parameters
        ----------
        days : int
            Look-back period in days

        Returns
        -------
        float
            Notifications per week
        """
        conn = get_connection()
        cursor = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        cursor.execute('''
            SELECT COUNT(*) FROM scanner_threshold_history
            WHERE date >= %s AND notification_sent = 1
        ''', (cutoff_date,))

        count = cursor.fetchone()[0]
        conn.close()

        weeks = days / 7
        return count / weeks if weeks > 0 else 0

    def get_days_since_last_notification(self) -> int:
        """Get number of days since last notification was sent."""
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT date FROM scanner_threshold_history
            WHERE notification_sent = 1
            ORDER BY date DESC LIMIT 1
        ''')
        row = cursor.fetchone()
        conn.close()

        if not row:
            return 999  # Never notified

        last_date = datetime.strptime(row[0], '%Y-%m-%d')
        return (datetime.now() - last_date).days

    def calculate_adjusted_threshold(self) -> float:
        """
        Calculate the threshold for today based on recent notification rate.

        Logic:
        - If rate < 0.5/week: lower threshold (dry spell)
        - If rate > 1.5/week: raise threshold (too many)
        - If days since last > 21: emergency lower to MIN
        - Exceptional opportunities (>90) always notify
        """
        current = self.get_current_threshold()
        rate = self.get_notification_rate()
        days_since = self.get_days_since_last_notification()

        # Emergency: long dry spell
        if days_since >= self.DRY_SPELL_DAYS:
            return self.MIN_THRESHOLD

        # Adjust based on rate
        if rate < self.RATE_LOW:
            # Lower threshold (but not below MIN)
            new_threshold = max(self.MIN_THRESHOLD, current - self.ADJUSTMENT_STEP)
        elif rate > self.RATE_HIGH:
            # Raise threshold (but not above MAX)
            new_threshold = min(self.MAX_THRESHOLD, current + self.ADJUSTMENT_STEP)
        else:
            # Rate is in target range, maintain
            new_threshold = current

        return round(new_threshold, 1)

    def should_notify(self, score: float) -> bool:
        """
        Determine if a score should trigger a notification.

        Parameters
        ----------
        score : float
            Opportunity score (0-100)

        Returns
        -------
        bool
            True if should notify
        """
        # Always notify exceptional opportunities
        if score >= self.MAX_THRESHOLD:
            return True

        # Never notify below quality floor
        if score < self.MIN_THRESHOLD:
            return False

        # Compare to current threshold
        threshold = self.calculate_adjusted_threshold()
        return score >= threshold

    def record_daily_scan(
        self,
        date: str,
        threshold: float,
        best_score: Optional[float],
        stocks_above: int,
        notification_sent: bool,
        notified_ticker: Optional[str] = None
    ) -> None:
        """
        Record daily scan results.

        Parameters
        ----------
        date : str
            Date string (YYYY-MM-DD)
        threshold : float
            Threshold used today
        best_score : float, optional
            Highest score seen today
        stocks_above : int
            Number of stocks above threshold
        notification_sent : bool
            Whether a notification was sent
        notified_ticker : str, optional
            Ticker that was notified (if any)
        """
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO scanner_threshold_history
            (date, threshold, best_score, stocks_above, notification_sent, notified_ticker)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (date) DO UPDATE SET
                threshold = EXCLUDED.threshold,
                best_score = EXCLUDED.best_score,
                stocks_above = EXCLUDED.stocks_above,
                notification_sent = EXCLUDED.notification_sent,
                notified_ticker = EXCLUDED.notified_ticker
        ''', (
            date,
            threshold,
            best_score,
            stocks_above,
            1 if notification_sent else 0,
            notified_ticker
        ))

        conn.commit()
        conn.close()

    def record_scores(
        self,
        date: str,
        scores: List[Tuple[str, float, float, float, float, float, float]]
    ) -> None:
        """
        Record all daily scores to history.

        Parameters
        ----------
        date : str
            Date string (YYYY-MM-DD)
        scores : list
            List of (ticker, opportunity, quality, value, growth, risk, catalyst) tuples
        """
        conn = get_connection()
        cursor = conn.cursor()

        for s in scores:
            cursor.execute('''
                INSERT INTO scanner_score_history
                (date, ticker, opportunity_score, quality_score, value_score,
                 growth_score, risk_score, catalyst_score)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (date, ticker) DO UPDATE SET
                    opportunity_score = EXCLUDED.opportunity_score,
                    quality_score = EXCLUDED.quality_score,
                    value_score = EXCLUDED.value_score,
                    growth_score = EXCLUDED.growth_score,
                    risk_score = EXCLUDED.risk_score,
                    catalyst_score = EXCLUDED.catalyst_score
            ''', (date, *s))

        conn.commit()
        conn.close()

    def get_threshold_history(self, days: int = 30) -> List[dict]:
        """
        Get recent threshold history for analysis.

        Parameters
        ----------
        days : int
            Number of days of history

        Returns
        -------
        list
            List of history records
        """
        conn = get_connection(dict_cursor=True)
        cursor = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        cursor.execute('''
            SELECT date, threshold, best_score, stocks_above,
                   notification_sent, notified_ticker
            FROM scanner_threshold_history
            WHERE date >= %s
            ORDER BY date DESC
        ''', (cutoff_date,))

        history = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return history

    def get_state(self) -> ThresholdState:
        """Get current threshold manager state."""
        return ThresholdState(
            current_threshold=self.calculate_adjusted_threshold(),
            recent_notification_rate=self.get_notification_rate(),
            days_since_last_notification=self.get_days_since_last_notification(),
            best_score_today=None,  # Set during scan
            stocks_above_threshold=0  # Set during scan
        )

    def get_top_scores_for_date(self, date: str, limit: int = 10) -> List[dict]:
        """
        Get top scoring stocks for a given date.

        Parameters
        ----------
        date : str
            Date string (YYYY-MM-DD)
        limit : int
            Maximum number of results

        Returns
        -------
        list
            List of score records
        """
        conn = get_connection(dict_cursor=True)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT ticker, opportunity_score, quality_score, value_score,
                   growth_score, risk_score, catalyst_score
            FROM scanner_score_history
            WHERE date = %s
            ORDER BY opportunity_score DESC
            LIMIT %s
        ''', (date, limit))

        scores = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return scores
