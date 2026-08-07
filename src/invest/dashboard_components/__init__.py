"""
Dashboard Components - Modular components for the investment dashboard.

This package provides modular components that break down the monolithic dashboard
into maintainable, testable, and reusable parts.

Components:
- ValuationEngine: Handles valuation model execution and coordination
- DataManager: Handles data persistence, loading, and caching
- ProgressTracker: Tracks and manages dashboard update progress
- HTMLGenerator: Generates dashboard HTML templates and content
- StockPrioritizer: Handles stock analysis prioritization logic
- ValuationDashboard: Orchestrates all components (main interface)
"""

from .dashboard import ValuationDashboard
from .data_manager import DataManager
from .html_generator import HTMLGenerator
from .progress_tracker import ProgressTracker
from .stock_prioritizer import StockPrioritizer
from .valuation_engine import ValuationEngine

__all__ = [
    'ValuationEngine',
    'DataManager',
    'ProgressTracker',
    'HTMLGenerator',
    'StockPrioritizer',
    'ValuationDashboard',
]
