"""
Opportunity Scanner Module

A daily scanning system that:
1. Scores opportunities using continuous functions (not rigid checklists)
2. Dynamically adjusts notification thresholds to average ~1/week
3. Keeps evaluation objective - only the notification threshold changes
4. Integrates with OpenClaw for scheduling and Telegram notifications
"""

from .scoring_engine import ScoringEngine, OpportunityScore
from .threshold_manager import ThresholdManager
from .opportunity_scanner import OpportunityScanner
from .telegram_notifier import TelegramNotifier

__all__ = [
    'ScoringEngine',
    'OpportunityScore',
    'ThresholdManager',
    'OpportunityScanner',
    'TelegramNotifier',
]
