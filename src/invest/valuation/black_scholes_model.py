"""
Black-Scholes-Merton structural equity valuation model.

This model treats equity as a call option on firm assets (Merton framework):
    Equity = Call(Assets, Debt, r, sigma_asset, T)

Robustness features:
- Requires sufficiently deep and fresh price history for volatility estimation
- Uses a dated risk-free rate from database macro table when available
- Falls back to configured default risk-free rate with confidence penalty
- Emits detailed diagnostics and data freshness metadata in outputs
"""

from __future__ import annotations

import math
import statistics
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ..config.constants import VALUATION_DEFAULTS
from ..exceptions import InsufficientDataError
from ..data.stock_data_reader import StockDataReader
from .base import ValuationModel, ValuationResult


class BlackScholesModel(ValuationModel):
    """
    Structural Black-Scholes-Merton equity valuation model.

    Parameters
    ----------
    horizon_years : float
        Option horizon in years.
    min_price_points : int
        Minimum number of close prices required to estimate volatility.
    max_price_age_days : int
        Maximum allowed age (days) of the latest price-history point.
    max_rate_age_days : int
        Maximum allowed age (days) of the latest macro risk-free rate.
    """

    def __init__(
        self,
        horizon_years: float = 1.0,
        min_price_points: int = 252,
        max_price_age_days: int = 30,
        max_rate_age_days: int = 30,
    ):
        super().__init__('black_scholes')
        self.horizon_years = horizon_years
        self.min_price_points = min_price_points
        self.max_price_age_days = max_price_age_days
        self.max_rate_age_days = max_rate_age_days
        self._last_suitability_reason = ''
        self._reader: Optional[StockDataReader] = None

    def get_suitability_reason(self) -> str:
        """
        Get the latest suitability reason.

        Returns
        -------
        str
            Empty when suitable, otherwise reason for unsuitability.
        """
        return self._last_suitability_reason

    def is_suitable(self, ticker: str, data: Dict[str, Any]) -> bool:
        """
        Check model suitability using robust data quality gates.

        Parameters
        ----------
        ticker : str
            Stock ticker symbol.
        data : Dict[str, Any]
            Stock data dictionary.

        Returns
        -------
        bool
            True if suitable, False otherwise.
        """
        self._last_suitability_reason = ''
        info = data.get('info', {})

        current_price = self._safe_float(self._get_info_value(info, ['currentPrice', 'current_price']))
        shares = self._safe_float(self._get_info_value(info, ['sharesOutstanding', 'shares_outstanding']))
        market_cap = self._safe_float(self._get_info_value(info, ['marketCap', 'market_cap']))
        total_debt = self._safe_float(self._get_info_value(info, ['totalDebt', 'total_debt']))

        if current_price <= 0:
            self._last_suitability_reason = 'Missing or invalid current price'
            return False
        if shares <= 0:
            self._last_suitability_reason = 'Missing or invalid shares outstanding'
            return False
        if market_cap <= 0:
            # Fallback to price * shares if market cap missing
            market_cap = current_price * shares
        if market_cap <= 0:
            self._last_suitability_reason = 'Missing or invalid market capitalization'
            return False
        if total_debt <= 0:
            self._last_suitability_reason = 'Missing or invalid total debt for structural strike value'
            return False

        market_data = self._resolve_market_data(ticker, data)
        price_points = market_data.get('price_points', 0)
        price_is_fresh = bool(market_data.get('price_is_fresh', False))

        if price_points < self.min_price_points:
            self._last_suitability_reason = (
                f'Insufficient price history for volatility ({price_points} < {self.min_price_points})'
            )
            return False
        if not price_is_fresh:
            age_days = market_data.get('price_age_days')
            self._last_suitability_reason = (
                f'Stale price history ({age_days} days old; max {self.max_price_age_days})'
            )
            return False

        return True

    def _validate_inputs(self, ticker: str, data: Dict[str, Any]) -> None:
        """
        Validate required inputs.

        Parameters
        ----------
        ticker : str
            Stock ticker symbol.
        data : Dict[str, Any]
            Stock data dictionary.

        Raises
        ------
        InsufficientDataError
            If required fields are missing.
        """
        info = data.get('info', {})
        missing: List[str] = []

        if self._safe_float(self._get_info_value(info, ['currentPrice', 'current_price'])) <= 0:
            missing.append('currentPrice')
        if self._safe_float(self._get_info_value(info, ['sharesOutstanding', 'shares_outstanding'])) <= 0:
            missing.append('sharesOutstanding')
        if self._safe_float(self._get_info_value(info, ['totalDebt', 'total_debt'])) <= 0:
            missing.append('totalDebt')

        market_data = self._resolve_market_data(ticker, data)
        if market_data.get('price_points', 0) < self.min_price_points:
            missing.append('price_history')

        if missing:
            raise InsufficientDataError(ticker, missing)

    def _calculate_valuation(self, ticker: str, data: Dict[str, Any]) -> ValuationResult:
        """
        Calculate per-share fair value using the Merton framework.

        Parameters
        ----------
        ticker : str
            Stock ticker symbol.
        data : Dict[str, Any]
            Stock data dictionary.

        Returns
        -------
        ValuationResult
            Model valuation output.
        """
        info = data.get('info', {})
        current_price = self._safe_float(self._get_info_value(info, ['currentPrice', 'current_price']))
        shares = self._safe_float(self._get_info_value(info, ['sharesOutstanding', 'shares_outstanding']))
        market_cap = self._safe_float(self._get_info_value(info, ['marketCap', 'market_cap']))
        total_debt = self._safe_float(self._get_info_value(info, ['totalDebt', 'total_debt']))
        total_cash = self._safe_float(self._get_info_value(info, ['totalCash', 'total_cash']))
        book_value = self._safe_float(self._get_info_value(info, ['bookValue', 'book_value']))

        if market_cap <= 0:
            market_cap = current_price * shares

        market_data = self._resolve_market_data(ticker, data)
        closes = market_data.get('closes', [])
        sigma_equity = self._annualized_volatility(closes)
        risk_free_rate = self._resolve_risk_free_rate(market_data)

        # Debt is the strike in structural option view of equity.
        strike_debt = max(total_debt, 1.0)
        maturity = self.horizon_years

        asset_value_source, asset_value_fundamental = self._estimate_fundamental_asset_value(
            data=data,
            market_cap=market_cap,
            total_debt=total_debt,
            total_cash=total_cash,
            book_value=book_value,
            shares=shares,
        )

        calibrated_asset_value, calibrated_asset_vol, iterations, converged = self._calibrate_assets(
            equity_value=market_cap,
            equity_vol=sigma_equity,
            debt_value=strike_debt,
            risk_free_rate=risk_free_rate,
            maturity=maturity,
        )

        fair_equity_value = self._black_scholes_call(
            asset_value_fundamental,
            strike_debt,
            risk_free_rate,
            calibrated_asset_vol,
            maturity,
        )
        fair_value_per_share = fair_equity_value / shares if shares > 0 else 0.0
        margin_of_safety = ((fair_value_per_share - current_price) / current_price) if current_price > 0 else None
        pd_market = self._default_probability(
            calibrated_asset_value,
            strike_debt,
            risk_free_rate,
            calibrated_asset_vol,
            maturity,
        )
        pd_fundamental = self._default_probability(
            asset_value_fundamental,
            strike_debt,
            risk_free_rate,
            calibrated_asset_vol,
            maturity,
        )

        confidence_score = self._compute_confidence(
            market_data=market_data,
            sigma_equity=sigma_equity,
            converged=converged,
            asset_value_source=asset_value_source,
        )
        confidence = self._score_to_label(confidence_score)

        result = ValuationResult(
            ticker=ticker,
            model=self.name,
            fair_value=fair_value_per_share,
            current_price=current_price,
            margin_of_safety=margin_of_safety,
            enterprise_value=asset_value_fundamental,
            confidence=confidence,
        )

        result.inputs = {
            'horizon_years': maturity,
            'risk_free_rate': risk_free_rate,
            'equity_volatility': sigma_equity,
            'market_cap': market_cap,
            'total_debt': total_debt,
            'total_cash': total_cash,
            'shares_outstanding': shares,
            'asset_value_source': asset_value_source,
            'fundamental_asset_value': asset_value_fundamental,
        }
        result.outputs = {
            'equity_value_fair': fair_equity_value,
            'calibrated_asset_value_market': calibrated_asset_value,
            'calibrated_asset_volatility': calibrated_asset_vol,
            'calibration_iterations': iterations,
            'calibration_converged': converged,
            'default_probability_market_based': pd_market,
            'default_probability_fundamental_based': pd_fundamental,
            'confidence_score': confidence_score,
            'data_quality': {
                'price_points': market_data.get('price_points'),
                'price_last_date': market_data.get('price_last_date'),
                'price_age_days': market_data.get('price_age_days'),
                'price_is_fresh': market_data.get('price_is_fresh'),
                'rate_source': market_data.get('rate_source'),
                'rate_date': market_data.get('rate_date'),
                'rate_age_days': market_data.get('rate_age_days'),
                'rate_is_fresh': market_data.get('rate_is_fresh'),
            },
        }

        if asset_value_source == 'market_cap_plus_debt_minus_cash':
            result.warnings.append(
                'Fundamental asset value derived from market cap (circular); '
                'no accounting-based total assets available'
            )
        if not converged:
            result.warnings.append('Asset calibration did not fully converge; valuation confidence reduced')
        if not market_data.get('rate_is_fresh', False):
            result.warnings.append('Risk-free rate fallback used due to stale or missing macro rate')

        return result

    def _get_reader(self) -> StockDataReader:
        """Get lazy-initialized stock data reader."""
        if self._reader is None:
            self._reader = StockDataReader()
        return self._reader

    def _resolve_market_data(self, ticker: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resolve market data from provided payload or database.

        Parameters
        ----------
        ticker : str
            Stock ticker symbol.
        data : Dict[str, Any]
            Stock data dictionary.

        Returns
        -------
        Dict[str, Any]
            Resolved market data fields.
        """
        preloaded = data.get('market_data')
        if isinstance(preloaded, dict):
            return preloaded

        reader = self._get_reader()
        return reader.get_market_inputs(
            ticker=ticker,
            min_price_points=self.min_price_points,
            max_price_age_days=self.max_price_age_days,
            max_rate_age_days=self.max_rate_age_days,
        )

    def _resolve_risk_free_rate(self, market_data: Dict[str, Any]) -> float:
        """
        Resolve risk-free rate with robust fallback.

        Parameters
        ----------
        market_data : Dict[str, Any]
            Market data dictionary.

        Returns
        -------
        float
            Risk-free rate in decimal units.
        """
        risk_free_rate = market_data.get('risk_free_rate')
        if isinstance(risk_free_rate, (float, int)) and math.isfinite(float(risk_free_rate)):
            rate = float(risk_free_rate)
            if 0 <= rate < 1:
                return rate

        return float(VALUATION_DEFAULTS.RISK_FREE_RATE)

    def _annualized_volatility(self, closes: List[float]) -> float:
        """
        Compute annualized equity volatility from close prices.

        Parameters
        ----------
        closes : List[float]
            Ordered close prices.

        Returns
        -------
        float
            Annualized volatility (decimal).
        """
        valid_closes = [float(c) for c in closes if isinstance(c, (float, int)) and c > 0]
        if len(valid_closes) < 30:
            return 0.0

        log_returns: List[float] = []
        for prev, curr in zip(valid_closes[:-1], valid_closes[1:]):
            if prev > 0 and curr > 0:
                log_returns.append(math.log(curr / prev))

        if len(log_returns) < 30:
            return 0.0

        daily_vol = statistics.stdev(log_returns)
        return max(daily_vol * math.sqrt(252), 0.0001)

    def _estimate_fundamental_asset_value(
        self,
        data: Dict[str, Any],
        market_cap: float,
        total_debt: float,
        total_cash: float,
        book_value: float,
        shares: float,
    ) -> Tuple[str, float]:
        """
        Estimate firm asset value from fundamental (non-market) fields.

        Uses a priority chain of increasingly less ideal sources:
        1. Balance-sheet total assets (best -- accounting-based, independent of
           market price).
        2. info-dict totalAssets snapshot (same accounting basis, less granular).
        3. Book equity + debt (accounting-based reconstruction).
        4. Market-cap-derived EV (CIRCULAR -- see warning below).

        Parameters
        ----------
        data : Dict[str, Any]
            Stock data dictionary.
        market_cap : float
            Market capitalization.
        total_debt : float
            Total debt.
        total_cash : float
            Total cash.
        book_value : float
            Book value per share.
        shares : float
            Shares outstanding.

        Returns
        -------
        Tuple[str, float]
            (source_label, estimated_asset_value)
        """
        # --- Priority 1: balance-sheet DataFrame total assets ----------------
        balance_sheet = data.get('balance_sheet')
        if balance_sheet is not None and hasattr(balance_sheet, 'index'):
            candidates = ['Total Assets', 'Total Asset', 'Total Assets As Reported']
            for name in candidates:
                if name in balance_sheet.index:
                    try:
                        series = balance_sheet.loc[name]
                        asset_value = self._get_most_recent_value(series, default=None)
                        if asset_value and float(asset_value) > 0:
                            return 'balance_sheet_total_assets', float(asset_value)
                    except Exception:
                        pass

        # --- Priority 2: info-dict totalAssets snapshot ----------------------
        info = data.get('info', {})
        info_total_assets = self._safe_float(
            self._get_info_value(info, ['totalAssets', 'total_assets'])
        )
        if info_total_assets > 0:
            return 'info_total_assets', info_total_assets

        # --- Priority 3: book equity + debt ----------------------------------
        if book_value > 0 and shares > 0:
            return 'book_equity_plus_debt', max((book_value * shares) + total_debt, 1.0)

        # --- Priority 4 (CIRCULAR): market-cap-derived EV --------------------
        # BUG #17 -- Known limitation: using market_cap to derive asset value
        # makes the Merton output partially circular because the "fundamental"
        # fair value then reflects current market pricing.  This fallback is
        # kept only when no accounting-based asset figure is available.  A
        # proper fix would require an independent asset-value source (e.g.
        # DCF-derived EV).  The confidence score is penalised when this path
        # is taken (see _compute_confidence).
        return 'market_cap_plus_debt_minus_cash', max(market_cap + total_debt - total_cash, 1.0)

    def _calibrate_assets(
        self,
        equity_value: float,
        equity_vol: float,
        debt_value: float,
        risk_free_rate: float,
        maturity: float,
    ) -> Tuple[float, float, int, bool]:
        """
        Calibrate asset value and asset volatility to market equity.

        Parameters
        ----------
        equity_value : float
            Observed market equity value.
        equity_vol : float
            Observed annualized equity volatility.
        debt_value : float
            Debt strike value.
        risk_free_rate : float
            Risk-free rate.
        maturity : float
            Maturity in years.

        Returns
        -------
        Tuple[float, float, int, bool]
            (asset_value, asset_volatility, iterations, converged)
        """
        equity_value = max(equity_value, 1.0)
        debt_value = max(debt_value, 1.0)
        equity_vol = min(max(equity_vol, 0.05), 3.0)

        sigma_asset = min(max(equity_vol * equity_value / (equity_value + debt_value), 0.05), 1.5)
        asset_value = equity_value + debt_value
        converged = False
        max_iter = 100

        for i in range(max_iter):
            asset_value = self._solve_asset_value(
                target_equity=equity_value,
                debt_value=debt_value,
                risk_free_rate=risk_free_rate,
                asset_vol=sigma_asset,
                maturity=maturity,
            )

            d1, _ = self._d1_d2(asset_value, debt_value, risk_free_rate, sigma_asset, maturity)
            nd1 = self._norm_cdf(d1)
            denom = max(asset_value * max(nd1, 1e-6), 1e-6)
            sigma_new = min(max(equity_vol * equity_value / denom, 0.01), 3.0)

            if abs(sigma_new - sigma_asset) < 1e-5:
                sigma_asset = sigma_new
                converged = True
                return asset_value, sigma_asset, i + 1, converged

            sigma_asset = 0.5 * sigma_asset + 0.5 * sigma_new

        return asset_value, sigma_asset, max_iter, converged

    def _solve_asset_value(
        self,
        target_equity: float,
        debt_value: float,
        risk_free_rate: float,
        asset_vol: float,
        maturity: float,
    ) -> float:
        """
        Solve for asset value by bisection given equity target.

        Parameters
        ----------
        target_equity : float
            Target equity value.
        debt_value : float
            Debt strike value.
        risk_free_rate : float
            Risk-free rate.
        asset_vol : float
            Asset volatility.
        maturity : float
            Maturity in years.

        Returns
        -------
        float
            Solved asset value.
        """
        low = 1e-6
        high = max(target_equity + debt_value * 4.0, debt_value * 2.0)

        while self._black_scholes_call(high, debt_value, risk_free_rate, asset_vol, maturity) < target_equity:
            high *= 2.0
            if high > 1e16:
                break

        for _ in range(120):
            mid = 0.5 * (low + high)
            equity_mid = self._black_scholes_call(mid, debt_value, risk_free_rate, asset_vol, maturity)
            if equity_mid > target_equity:
                high = mid
            else:
                low = mid

        return 0.5 * (low + high)

    def _default_probability(
        self,
        asset_value: float,
        debt_value: float,
        risk_free_rate: float,
        asset_vol: float,
        maturity: float,
    ) -> float:
        """
        Compute risk-neutral default probability.

        Parameters
        ----------
        asset_value : float
            Asset value.
        debt_value : float
            Debt strike.
        risk_free_rate : float
            Risk-free rate.
        asset_vol : float
            Asset volatility.
        maturity : float
            Maturity in years.

        Returns
        -------
        float
            Risk-neutral default probability.
        """
        _, d2 = self._d1_d2(asset_value, debt_value, risk_free_rate, asset_vol, maturity)
        return self._norm_cdf(-d2)

    def _black_scholes_call(
        self,
        asset_value: float,
        debt_value: float,
        risk_free_rate: float,
        asset_vol: float,
        maturity: float,
    ) -> float:
        """
        Price call option under Black-Scholes.

        Parameters
        ----------
        asset_value : float
            Spot asset value.
        debt_value : float
            Strike (debt) value.
        risk_free_rate : float
            Risk-free rate.
        asset_vol : float
            Asset volatility.
        maturity : float
            Time to maturity in years.

        Returns
        -------
        float
            Call option value.
        """
        d1, d2 = self._d1_d2(asset_value, debt_value, risk_free_rate, asset_vol, maturity)
        return asset_value * self._norm_cdf(d1) - debt_value * math.exp(-risk_free_rate * maturity) * self._norm_cdf(d2)

    def _d1_d2(
        self,
        asset_value: float,
        debt_value: float,
        risk_free_rate: float,
        asset_vol: float,
        maturity: float,
    ) -> Tuple[float, float]:
        """
        Compute d1 and d2 terms.

        Parameters
        ----------
        asset_value : float
            Spot asset value.
        debt_value : float
            Strike (debt) value.
        risk_free_rate : float
            Risk-free rate.
        asset_vol : float
            Asset volatility.
        maturity : float
            Time to maturity in years.

        Returns
        -------
        Tuple[float, float]
            d1 and d2.
        """
        asset_value = max(asset_value, 1e-12)
        debt_value = max(debt_value, 1e-12)
        asset_vol = max(asset_vol, 1e-8)
        maturity = max(maturity, 1e-8)
        vol_term = asset_vol * math.sqrt(maturity)
        d1 = (math.log(asset_value / debt_value) + (risk_free_rate + 0.5 * asset_vol**2) * maturity) / vol_term
        d2 = d1 - vol_term
        return d1, d2

    def _norm_cdf(self, value: float) -> float:
        """
        Standard normal CDF.

        Parameters
        ----------
        value : float
            Input value.

        Returns
        -------
        float
            Standard normal CDF at value.
        """
        return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))

    def _compute_confidence(
        self,
        market_data: Dict[str, Any],
        sigma_equity: float,
        converged: bool,
        asset_value_source: str,
    ) -> float:
        """
        Compute confidence score in [0, 1].

        Parameters
        ----------
        market_data : Dict[str, Any]
            Market data quality fields.
        sigma_equity : float
            Annualized equity volatility.
        converged : bool
            Whether asset calibration converged.
        asset_value_source : str
            Source used for fundamental asset estimate.

        Returns
        -------
        float
            Confidence score.
        """
        score = 0.7

        # Fresh and sufficiently deep price history.
        if market_data.get('price_is_fresh'):
            score += 0.1
        else:
            score -= 0.2

        if int(market_data.get('price_points', 0)) >= 504:
            score += 0.05

        # Rate freshness and provenance.
        if market_data.get('rate_is_fresh'):
            score += 0.05
        elif market_data.get('rate_source') == 'default_config':
            score -= 0.1

        # Calibration and volatility sanity.
        if converged:
            score += 0.05
        else:
            score -= 0.1

        if sigma_equity <= 0.01 or sigma_equity >= 2.0:
            score -= 0.1

        # Better confidence when using actual balance-sheet assets.
        if asset_value_source in ('balance_sheet_total_assets', 'info_total_assets'):
            score += 0.05
        elif asset_value_source == 'market_cap_plus_debt_minus_cash':
            # Circular: market-derived EV used as "fundamental" asset value.
            score -= 0.05

        return min(max(score, 0.0), 1.0)

    def _score_to_label(self, score: float) -> str:
        """
        Map confidence score to textual level.

        Parameters
        ----------
        score : float
            Confidence score.

        Returns
        -------
        str
            `high`, `medium`, or `low`.
        """
        if score >= 0.75:
            return 'high'
        if score >= 0.45:
            return 'medium'
        return 'low'

    def _get_info_value(self, info: Dict[str, Any], keys: List[str]) -> Any:
        """
        Get first present value from candidate keys.

        Parameters
        ----------
        info : Dict[str, Any]
            Info dictionary.
        keys : List[str]
            Candidate key names.

        Returns
        -------
        Any
            First found value or None.
        """
        for key in keys:
            if key in info and info[key] is not None:
                return info[key]
        return None
