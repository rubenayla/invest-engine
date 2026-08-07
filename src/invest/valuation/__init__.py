"""
Unified Valuation Models Package

This package provides a consolidated structure for all valuation models,
offering a common interface and consistent error handling across different
valuation approaches.
"""

from .base import ValuationModel, ValuationResult
from .dcf_model import DCFModel, EnhancedDCFModel, MultiStageDCFModel
from .model_registry import ModelRegistry
from .ratios_model import SimpleRatiosModel
from .rim_model import RIMModel

# Export the main interfaces
__all__ = [
    'ValuationModel',
    'ValuationResult',
    'DCFModel',
    'EnhancedDCFModel',
    'MultiStageDCFModel',
    'RIMModel',
    'SimpleRatiosModel',
    'ModelRegistry',
]
