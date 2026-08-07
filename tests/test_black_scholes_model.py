import math
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from invest.config.constants import VALUATION_DEFAULTS  # noqa: E402
from invest.valuation.black_scholes_model import BlackScholesModel  # noqa: E402


def _sample_data(rate_available: bool = True, stale_prices: bool = False) -> dict:
    closes = [100.0 + (0.15 * i) + (2.5 * math.sin(i / 9.0)) for i in range(320)]
    today = datetime.now().strftime('%Y-%m-%d')
    old_date = '2025-01-01'

    market_data = {
        'closes': closes,
        'price_points': len(closes),
        'price_last_date': old_date if stale_prices else today,
        'price_age_days': 200 if stale_prices else 0,
        'price_is_fresh': not stale_prices,
        'risk_free_rate': 0.045 if rate_available else None,
        'rate_source': 'macro_rates' if rate_available else 'default_config',
        'rate_date': today if rate_available else None,
        'rate_age_days': 0 if rate_available else None,
        'rate_is_fresh': bool(rate_available),
    }

    return {
        'info': {
            'currentPrice': 100.0,
            'sharesOutstanding': 1_000_000.0,
            'marketCap': 100_000_000.0,
            'totalDebt': 45_000_000.0,
            'totalCash': 8_000_000.0,
            'bookValue': 70.0,
        },
        'balance_sheet': pd.DataFrame(
            {
                '2025-12-31': [180_000_000.0, 45_000_000.0],
            },
            index=['Total Assets', 'Total Debt'],
        ),
        'market_data': market_data,
    }


def test_black_scholes_model_calculates_positive_fair_value() -> None:
    model = BlackScholesModel()
    data = _sample_data(rate_available=True, stale_prices=False)

    assert model.is_suitable('TEST', data)
    model._validate_inputs('TEST', data)
    result = model._calculate_valuation('TEST', data)

    assert result.fair_value is not None
    assert result.fair_value > 0
    assert result.current_price == 100.0
    assert result.outputs['data_quality']['price_is_fresh'] is True
    assert result.inputs['asset_value_source'] == 'balance_sheet_total_assets'


def test_black_scholes_model_rejects_stale_price_history() -> None:
    model = BlackScholesModel(max_price_age_days=30)
    data = _sample_data(rate_available=True, stale_prices=True)

    assert not model.is_suitable('TEST', data)
    assert 'Stale price history' in model.get_suitability_reason()


def test_black_scholes_model_uses_default_rate_when_missing() -> None:
    model = BlackScholesModel()
    data = _sample_data(rate_available=False, stale_prices=False)

    assert model.is_suitable('TEST', data)
    result = model._calculate_valuation('TEST', data)

    assert result.inputs['risk_free_rate'] == VALUATION_DEFAULTS.RISK_FREE_RATE
    assert any('Risk-free rate fallback used' in w for w in result.warnings)
