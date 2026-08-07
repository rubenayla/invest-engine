"""
Scoring Engine for Opportunity Scanner

Uses continuous scoring functions (sigmoid-like curves) instead of pass/fail checklists.
A stock with P/E=19 isn't discarded - it just scores slightly lower than P/E=17.
"""

import logging
import math
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List

from ..data.stock_data_reader import StockDataReader
from ..valuation.db_utils import get_db_connection, get_latest_predictions

logger = logging.getLogger(__name__)


@dataclass
class OpportunityScore:
    """Complete opportunity score for a stock."""
    ticker: str
    company_name: str
    opportunity_score: float  # 0-100 composite
    quality_score: float      # 0-100
    value_score: float        # 0-100
    growth_score: float       # 0-100
    risk_score: float         # 0-100 (higher = less risky)
    catalyst_score: float     # 0-100

    # Key metrics for display
    current_price: float = 0.0
    dcf_fair_value: Optional[float] = None
    rim_fair_value: Optional[float] = None
    ensemble_fair_value: Optional[float] = None

    # Supporting data
    key_metrics: Dict[str, Any] = field(default_factory=dict)
    component_details: Dict[str, Any] = field(default_factory=dict)


class ScoringEngine:
    """
    Continuous scoring engine for stock opportunities.

    Core principle: Use smooth curves instead of binary thresholds.
    """

    # Default component weights (sum to 1.0)
    DEFAULT_WEIGHTS = {
        'quality': 0.25,
        'value': 0.30,
        'growth': 0.20,
        'risk': 0.10,
        'catalyst': 0.15,
    }

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        """
        Initialize scoring engine with optional custom weights.

        Parameters
        ----------
        weights : dict, optional
            Custom weights for each component. Must sum to 1.0.
        """
        self.weights = weights or self.DEFAULT_WEIGHTS
        self._validate_weights()
        self.reader = StockDataReader()

    def _validate_weights(self) -> None:
        """Ensure weights sum to 1.0."""
        total = sum(self.weights.values())
        if not 0.99 <= total <= 1.01:
            raise ValueError(f"Weights must sum to 1.0, got {total}")

    @staticmethod
    def normalize(
        value: float,
        min_val: float,
        target: float,
        max_val: float,
        inverse: bool = False
    ) -> float:
        """
        Normalize a value to 0-100 using a smooth sigmoid-like curve.

        Parameters
        ----------
        value : float
            The raw value to normalize
        min_val : float
            Below this: 0-20 points
        target : float
            At target: ~70 points (good)
        max_val : float
            At max: ~100 points (exceptional)
        inverse : bool
            If True, lower values are better (e.g., P/E ratio)

        Returns
        -------
        float
            Score from 0 to 100
        """
        if value is None or math.isnan(value):
            return 50.0  # Neutral score for missing data

        if inverse:
            # Flip value and target so lower-is-better maps to higher scores
            value = min_val + max_val - value
            target = min_val + max_val - target

        if value <= min_val:
            # Below minimum: 0-20 points (linear)
            return max(0, 20 * (value / min_val)) if min_val > 0 else 0

        if value >= max_val:
            # Above maximum: cap at 100
            return 100.0

        if value <= target:
            # Between min and target: 20-70 points (smooth curve)
            progress = (value - min_val) / (target - min_val)
            # Use smoothstep for smoother transition
            smooth = progress * progress * (3 - 2 * progress)
            return 20 + smooth * 50

        # Between target and max: 70-100 points (smooth curve)
        progress = (value - target) / (max_val - target)
        smooth = progress * progress * (3 - 2 * progress)
        return 70 + smooth * 30

    def score_quality(self, data: Dict[str, Any]) -> tuple[float, Dict[str, Any]]:
        """
        Score business quality metrics.

        Sources: ROE, ROIC, current ratio, debt/equity, margins
        """
        details = {}
        scores = []

        # ROE: 5% min, 15% target, 30% exceptional
        roe = data.get('financials', {}).get('returnOnEquity')
        if roe is not None:
            roe_score = self.normalize(roe * 100, 5, 15, 30)
            scores.append(roe_score)
            details['roe'] = {'value': roe * 100, 'score': roe_score}

        # Current Ratio: 0.8 min, 1.5 target, 3.0 max
        current_ratio = data.get('financials', {}).get('currentRatio')
        if current_ratio is not None:
            cr_score = self.normalize(current_ratio, 0.8, 1.5, 3.0)
            scores.append(cr_score)
            details['current_ratio'] = {'value': current_ratio, 'score': cr_score}

        # Debt/Equity: 2.0 max, 0.5 target, 0 ideal (inverse)
        debt_equity = data.get('financials', {}).get('debtToEquity')
        if debt_equity is not None:
            de_score = self.normalize(debt_equity, 0, 0.5, 2.0, inverse=True)
            scores.append(de_score)
            details['debt_equity'] = {'value': debt_equity, 'score': de_score}

        # Operating Margins: 0% min, 15% target, 40% exceptional
        op_margin = data.get('financials', {}).get('operatingMargins')
        if op_margin is not None:
            om_score = self.normalize(op_margin * 100, 0, 15, 40)
            scores.append(om_score)
            details['operating_margin'] = {'value': op_margin * 100, 'score': om_score}

        # Profit Margins: 0% min, 10% target, 30% exceptional
        profit_margin = data.get('financials', {}).get('profitMargins')
        if profit_margin is not None:
            pm_score = self.normalize(profit_margin * 100, 0, 10, 30)
            scores.append(pm_score)
            details['profit_margin'] = {'value': profit_margin * 100, 'score': pm_score}

        # Accrual-based earnings quality: lower accruals = more cash-backed earnings
        accrual_score, accrual_details = self._score_accrual_quality(data)
        if accrual_score is not None:
            scores.append(accrual_score)
            details['accrual_quality'] = accrual_details

        final_score = sum(scores) / len(scores) if scores else 50.0
        return final_score, details

    def _score_accrual_quality(
        self, data: Dict[str, Any]
    ) -> tuple[Optional[float], Dict[str, Any]]:
        """
        Score earnings quality via accrual ratio.

        Accruals = (Net Income - Operating Cash Flow) / Total Assets

        High accruals → earnings driven by accounting, not cash (Enron-style).
        Low/negative accruals → earnings backed by real cash flows.
        """
        import json

        # Extract multi-year income data
        income_raw = data.get('income') or data.get('income_json')
        cashflow_raw = data.get('cashflow')
        balance_sheet_raw = data.get('balance_sheet')

        if not (income_raw and cashflow_raw and balance_sheet_raw):
            return None, {'status': 'insufficient_data'}

        def parse_json(raw):
            if isinstance(raw, str):
                return json.loads(raw)
            return raw

        try:
            income_data = parse_json(income_raw)
            cashflow_data = parse_json(cashflow_raw)
            bs_data = parse_json(balance_sheet_raw)
        except (json.JSONDecodeError, TypeError):
            return None, {'status': 'parse_error'}

        def get_most_recent(rows, metric_names):
            """Get most recent value for a metric from list-of-dicts format."""
            for row in rows:
                if isinstance(row, dict) and row.get('index') in metric_names:
                    dates = sorted(
                        [k for k in row.keys() if k != 'index'], reverse=True
                    )
                    for d in dates:
                        val = row.get(d)
                        if val is not None and not (isinstance(val, float) and val != val):
                            return float(val)
            return None

        net_income = get_most_recent(
            income_data, ['Net Income', 'Net Income Common Stockholders']
        )
        operating_cf = get_most_recent(
            cashflow_data, ['Operating Cash Flow', 'Cash Flow From Continuing Operating Activities']
        )
        total_assets = get_most_recent(
            bs_data, ['Total Assets']
        )

        if net_income is None or operating_cf is None or total_assets is None:
            return None, {'status': 'missing_fields'}

        if total_assets <= 0:
            return None, {'status': 'invalid_total_assets'}

        accruals = (net_income - operating_cf) / total_assets

        # Score: accruals 0.10 (10%) = poor, 0.03 = good, -0.05 = excellent
        # Using inverse normalization: lower accruals → higher score
        accrual_pct = accruals * 100
        accrual_score = self.normalize(accrual_pct, -5, 3, 10, inverse=True)

        details = {
            'accrual_ratio': round(accruals, 4),
            'accrual_pct': round(accrual_pct, 2),
            'score': round(accrual_score, 1),
            'net_income': net_income,
            'operating_cashflow': operating_cf,
            'total_assets': total_assets,
            'quality': 'high' if accruals < 0.03 else 'moderate' if accruals < 0.07 else 'low',
        }

        return accrual_score, details

    def score_value(
        self,
        data: Dict[str, Any],
        valuations: Dict[str, Any]
    ) -> tuple[float, Dict[str, Any]]:
        """
        Score valuation attractiveness.

        Sources: P/E, P/B, EV/EBITDA + DCF/RIM/Ensemble upside
        """
        details = {}
        scores = []

        # P/E Ratio: 30 max, 15 target, 8 exceptional (inverse - lower is better)
        pe = data.get('financials', {}).get('trailingPE')
        try:
            pe = float(pe) if pe is not None else None
        except (ValueError, TypeError):
            pe = None
        if pe is not None and pe > 0:
            pe_score = self.normalize(pe, 8, 15, 30, inverse=True)
            scores.append(pe_score)
            details['pe'] = {'value': pe, 'score': pe_score}

        # P/B Ratio: 5 max, 2.5 target, 1 exceptional (inverse)
        pb = data.get('financials', {}).get('priceToBook')
        try:
            pb = float(pb) if pb is not None else None
        except (ValueError, TypeError):
            pb = None
        if pb is not None and pb > 0:
            pb_score = self.normalize(pb, 1, 2.5, 5, inverse=True)
            scores.append(pb_score)
            details['pb'] = {'value': pb, 'score': pb_score}

        # Model upside via unified consensus (heavier weight)
        from ..valuation.consensus import compute_consensus_from_dicts

        current_price = data.get('info', {}).get('currentPrice') or data.get('price_data', {}).get('current_price')
        consensus = compute_consensus_from_dicts(valuations, current_price) if current_price else None

        if consensus is not None:
            consensus_upside = consensus.margin_of_safety * 100  # as percentage
            upside_score = self.normalize(consensus_upside, -20, 20, 50)
            details['consensus_upside'] = {'value': consensus_upside, 'score': upside_score}
            ratio_avg = sum(scores) / len(scores) if scores else 50.0
            final_score = ratio_avg * 0.5 + upside_score * 0.5
        else:
            final_score = sum(scores) / len(scores) if scores else 50.0

        return final_score, details

    def score_risk(self, data: Dict[str, Any]) -> tuple[float, Dict[str, Any]]:
        """
        Score risk level (higher score = LOWER risk = better).

        Sources: Beta, volatility, financial leverage
        """
        details = {}
        scores = []

        # Debt/Equity as risk indicator: 2 max (risky), 0.5 target, 0 ideal
        debt_equity = data.get('financials', {}).get('debtToEquity')
        try:
            debt_equity = float(debt_equity) if debt_equity is not None else None
        except (ValueError, TypeError):
            debt_equity = None
        if debt_equity is not None:
            # Inverse: lower debt = higher score (less risky)
            de_risk_score = self.normalize(debt_equity, 0, 0.5, 2.0, inverse=True)
            scores.append(de_risk_score)
            details['debt_equity_risk'] = {'value': debt_equity, 'score': de_risk_score}

        # Current ratio as liquidity safety: 0.5 min (risky), 1.5 target, 3.0 safe
        current_ratio = data.get('financials', {}).get('currentRatio')
        try:
            current_ratio = float(current_ratio) if current_ratio is not None else None
        except (ValueError, TypeError):
            current_ratio = None
        if current_ratio is not None:
            cr_score = self.normalize(current_ratio, 0.5, 1.5, 3.0)
            scores.append(cr_score)
            details['liquidity'] = {'value': current_ratio, 'score': cr_score}

        # Sector-based risk adjustment
        sector = data.get('info', {}).get('sector', '')
        sector_risk = {
            'Consumer Staples': 80,
            'Utilities': 75,
            'Healthcare': 70,
            'Communication Services': 60,
            'Industrials': 55,
            'Consumer Discretionary': 50,
            'Technology': 50,
            'Materials': 45,
            'Financials': 45,
            'Energy': 40,
            'Real Estate': 55,
        }
        sector_score = sector_risk.get(sector, 50)
        scores.append(sector_score)
        details['sector_stability'] = {'value': sector, 'score': sector_score}

        final_score = sum(scores) / len(scores) if scores else 50.0
        return final_score, details

    def score_catalyst(self, data: Dict[str, Any]) -> tuple[float, Dict[str, Any]]:
        """
        Score timing/momentum signals.

        Sources: 52w-high discount, RSI proxy, momentum signals
        """
        details = {}
        scores = []

        # 52-week high discount: more discount = better buying opportunity
        current_price = data.get('info', {}).get('currentPrice') or data.get('price_data', {}).get('current_price')
        price_52w_high = data.get('price_data', {}).get('price_52w_high')

        if current_price and price_52w_high and price_52w_high > 0:
            discount = (price_52w_high - current_price) / price_52w_high * 100
            # Discount: 0% min (at high), 15% target, 40% exceptional
            discount_score = self.normalize(discount, 0, 15, 40)
            scores.append(discount_score)
            details['52w_discount'] = {'value': discount, 'score': discount_score}

        # 52-week low buffer: distance from 52w low (safety)
        price_52w_low = data.get('price_data', {}).get('price_52w_low')
        if current_price and price_52w_low and price_52w_low > 0:
            buffer = (current_price - price_52w_low) / price_52w_low * 100
            # Buffer: 0% min, 30% target, 80% max (not catching falling knife)
            buffer_score = self.normalize(buffer, 0, 30, 80)
            scores.append(buffer_score * 0.5)  # Lower weight
            details['52w_low_buffer'] = {'value': buffer, 'score': buffer_score}

        # 30-day trend as momentum proxy
        price_trend = data.get('price_data', {}).get('price_trend_30d')
        if price_trend is not None:
            # Slight negative to neutral is ideal for buying
            # -5% to +5% is target zone
            trend_pct = price_trend * 100
            if -5 <= trend_pct <= 5:
                trend_score = 70  # Consolidation = good
            elif trend_pct < -15:
                trend_score = 40  # Falling knife risk
            elif trend_pct > 15:
                trend_score = 50  # Already moved
            else:
                trend_score = 60  # Moderate movement
            scores.append(trend_score)
            details['momentum'] = {'value': trend_pct, 'score': trend_score}

        # Insider activity sub-signal
        insider = data.get('insider', {})
        if insider.get('has_data'):
            insider_score, insider_details = self._score_insider_activity(insider)
            scores.append(insider_score)
            details['insider'] = insider_details

        # Activist activity sub-signal (13D/13G)
        activist = data.get('activist', {})
        if activist.get('has_data'):
            activist_score, activist_details = self._score_activist_activity(activist)
            scores.append(activist_score)
            details['activist'] = activist_details

        # Smart money holdings sub-signal (13F)
        holdings = data.get('holdings', {})
        if holdings.get('has_data'):
            holdings_score, holdings_details = self._score_smart_money(holdings)
            scores.append(holdings_score)
            details['smart_money'] = holdings_details

        # Japan large shareholding (same scoring as activist for .T tickers)
        japan = data.get('japan_stakes', {})
        if japan.get('has_data'):
            japan_score, japan_details = self._score_japan_stakes(japan)
            scores.append(japan_score)
            details['japan_stakes'] = japan_details

        final_score = sum(scores) / len(scores) if scores else 50.0
        return final_score, details

    def _score_insider_activity(self, insider: Dict[str, Any]) -> tuple[float, Dict[str, Any]]:
        """
        Score insider buying/selling activity.

        Signals: net_buy_pct, cluster_score, recency_days, dollar_conviction.
        Capped at 25 if only sells exist.
        """
        details: Dict[str, Any] = {}
        scores = []

        buy_count = insider.get('buy_count', 0)
        sell_count = insider.get('sell_count', 0)

        # Net buy %: -100% (all sells) to +100% (all buys)
        net_buy_pct = insider.get('net_buy_pct', 0.0)
        net_score = self.normalize(net_buy_pct, -2.0, 0.2, 1.0)
        # Remap to 0-100 range: normalize returns 0-100 via the smoothstep
        # -2% -> ~0-20, +0.2% -> 70, +1% -> 100
        scores.append(net_score)
        details['net_buy_pct'] = {'value': net_buy_pct, 'score': net_score}

        # Cluster score: distinct insiders buying in 30-day window
        cluster = insider.get('cluster_score', 0)
        cluster_score = self.normalize(cluster, 0, 2, 4)
        scores.append(cluster_score)
        details['cluster'] = {'value': cluster, 'score': cluster_score}

        # Recency: days since last purchase (lower is better -> inverse)
        recency = insider.get('recency_days')
        if recency is not None:
            recency_score = self.normalize(recency, 0, 60, 180, inverse=True)
            scores.append(recency_score)
            details['recency'] = {'value': recency, 'score': recency_score}

        # Dollar conviction: total USD of open-market buys
        dollars = insider.get('dollar_conviction', 0.0)
        dollar_score = self.normalize(dollars, 0, 1_000_000, 5_000_000)
        scores.append(dollar_score)
        details['dollar_conviction'] = {'value': dollars, 'score': dollar_score}

        # Sell trend: selling below historical norm is bullish
        sell_trend = insider.get('sell_trend')
        if sell_trend is not None and sell_count > 0:
            # sell_trend 0.5 = half normal selling → score ~80
            # sell_trend 1.0 = normal → score ~50
            # sell_trend 2.0 = double normal → score ~20
            sell_trend_score = self.normalize(sell_trend, 0.0, 0.7, 1.5, inverse=True)
            scores.append(sell_trend_score)
            details['sell_trend'] = {'value': sell_trend, 'score': sell_trend_score}

        final = sum(scores) / len(scores) if scores else 50.0

        # Cap at 25 if only sells exist (no buys) AND selling is at/above normal
        if buy_count == 0 and sell_count > 0:
            if sell_trend is None or sell_trend >= 0.7:
                final = min(final, 25.0)
            else:
                # Selling well below normal — still mildly bearish but not capped as hard
                final = min(final, 45.0)

        details['buy_count'] = buy_count
        details['sell_count'] = sell_count
        return final, details

    def _score_activist_activity(self, activist: Dict[str, Any]) -> tuple[float, Dict[str, Any]]:
        """
        Score activist/passive large-stake activity (13D/13G).

        13D (activist) filings are high-signal: often push for changes.
        13G (passive) 5%+ holders indicate institutional confidence.
        """
        details: Dict[str, Any] = {}
        scores = []

        activist_count = activist.get('activist_count', 0)
        passive_count = activist.get('passive_count', 0)
        max_stake = activist.get('max_stake_pct')
        total_holders = activist.get('total_holders_5pct', 0)

        # Activist (13D) presence is high signal
        activist_score = self.normalize(activist_count, 0, 1, 3)
        scores.append(activist_score * 1.5)  # Weight activist more heavily
        details['activist_count'] = {'value': activist_count, 'score': activist_score}

        # Passive (13G) 5%+ holders indicate confidence
        passive_score = self.normalize(passive_count, 0, 2, 5)
        scores.append(passive_score)
        details['passive_count'] = {'value': passive_count, 'score': passive_score}

        # Max stake percentage: higher = more conviction
        if max_stake is not None:
            stake_score = self.normalize(max_stake, 5, 10, 25)
            scores.append(stake_score)
            details['max_stake_pct'] = {'value': max_stake, 'score': stake_score}

        # Total distinct 5%+ holders
        holder_score = self.normalize(total_holders, 0, 2, 5)
        scores.append(holder_score)
        details['total_holders'] = {'value': total_holders, 'score': holder_score}

        final = sum(scores) / len(scores) if scores else 50.0
        details['recent_activist'] = activist.get('recent_activist_name')
        return final, details

    def _score_smart_money(self, holdings: Dict[str, Any]) -> tuple[float, Dict[str, Any]]:
        """
        Score smart money institutional holdings (13F).

        Signals: number of smart money holders, new positions, exits,
        quarter-over-quarter changes.
        """
        details: Dict[str, Any] = {}
        scores = []

        holders_count = holdings.get('smart_money_holders', 0)
        quarter_change = holdings.get('quarter_change')
        new_positions = holdings.get('new_positions', [])
        exited = holdings.get('exited_positions', [])

        # Number of smart money funds holding this stock
        holder_score = self.normalize(holders_count, 0, 3, 10)
        scores.append(holder_score)
        details['holder_count'] = {'value': holders_count, 'score': holder_score}

        # New positions this quarter (high signal)
        new_score = self.normalize(len(new_positions), 0, 1, 3)
        scores.append(new_score * 1.3)  # Bonus for new buys
        details['new_positions'] = {'value': len(new_positions), 'score': new_score}

        # Exits this quarter (negative signal)
        if exited:
            exit_penalty = self.normalize(len(exited), 0, 1, 3, inverse=True)
            scores.append(exit_penalty)
            details['exited'] = {'value': len(exited), 'score': exit_penalty}

        # Quarter-over-quarter share change
        if quarter_change is not None and quarter_change != 0:
            # Positive change = accumulation
            if quarter_change > 0:
                qoq_score = 70.0  # Accumulation is positive
            else:
                qoq_score = 30.0  # Distribution is negative
            scores.append(qoq_score)
            details['quarter_change'] = {'value': quarter_change, 'score': qoq_score}

        final = sum(scores) / len(scores) if scores else 50.0
        details['notable_holders'] = holdings.get('notable_holders', [])
        return final, details

    def _score_japan_stakes(self, japan: Dict[str, Any]) -> tuple[float, Dict[str, Any]]:
        """Score Japan large shareholding reports (EDINET)."""
        details: Dict[str, Any] = {}
        scores = []

        holder_count = japan.get('holder_count', 0)
        max_pct = japan.get('max_stake_pct')
        total_reports = japan.get('total_reports', 0)

        holder_score = self.normalize(holder_count, 0, 2, 5)
        scores.append(holder_score)
        details['holder_count'] = {'value': holder_count, 'score': holder_score}

        if max_pct is not None:
            stake_score = self.normalize(max_pct, 5, 10, 25)
            scores.append(stake_score)
            details['max_stake_pct'] = {'value': max_pct, 'score': stake_score}

        report_score = self.normalize(total_reports, 0, 2, 6)
        scores.append(report_score)
        details['total_reports'] = {'value': total_reports, 'score': report_score}

        final = sum(scores) / len(scores) if scores else 50.0
        details['recent_holder'] = japan.get('recent_holder_name')
        return final, details

    def score_stock(self, ticker: str, conn=None) -> Optional[OpportunityScore]:
        """
        Calculate complete opportunity score for a stock.

        Parameters
        ----------
        ticker : str
            Stock ticker symbol
        conn : optional
            An open DB connection to reuse for this ticker's reads. If None, a
            fresh connection is opened and closed here. Passing one shared
            connection (see ``score_universe``) avoids ~7 connection handshakes
            per ticker, which otherwise stalls a full scan over the SSH tunnel.

        Returns
        -------
        OpportunityScore or None if data not available
        """
        own_conn = conn is None
        if own_conn:
            conn = get_db_connection()

        # Load stock data (reuse conn for the row + all sub-signal lookups)
        data = self.reader.get_stock_data(ticker, conn=conn)
        if not data:
            if own_conn:
                conn.close()
            return None

        # Get valuation predictions
        valuations = get_latest_predictions(conn, ticker)
        if own_conn:
            conn.close()

        # Calculate component scores
        quality_score, quality_details = self.score_quality(data)
        value_score, value_details = self.score_value(data, valuations)
        growth_score, growth_details = self.score_growth(data)
        risk_score, risk_details = self.score_risk(data)
        catalyst_score, catalyst_details = self.score_catalyst(data)

        # Calculate weighted composite score
        opportunity_score = (
            quality_score * self.weights['quality'] +
            value_score * self.weights['value'] +
            growth_score * self.weights['growth'] +
            risk_score * self.weights['risk'] +
            catalyst_score * self.weights['catalyst']
        )

        # Extract key metrics for display
        info = data.get('info', {})
        financials = data.get('financials', {})

        key_metrics = {
            'pe': financials.get('trailingPE'),
            'pb': financials.get('priceToBook'),
            'roe': (financials.get('returnOnEquity') or 0) * 100,
            'debt_equity': financials.get('debtToEquity'),
            'current_ratio': financials.get('currentRatio'),
            'revenue_growth': (financials.get('revenueGrowth') or 0) * 100,
            'earnings_growth': (financials.get('earningsGrowth') or 0) * 100,
            'sector': info.get('sector'),
        }

        # Get fair values from valuations
        dcf_fv = None
        rim_fv = None
        ensemble_fv = None

        for model, pred in valuations.items():
            if pred.get('suitable'):
                if 'dcf' in model.lower() and dcf_fv is None:
                    dcf_fv = pred.get('fair_value')
                elif 'rim' in model.lower() and rim_fv is None:
                    rim_fv = pred.get('fair_value')
                elif 'ensemble' in model.lower():
                    ensemble_fv = pred.get('fair_value')

        return OpportunityScore(
            ticker=ticker,
            company_name=info.get('longName') or info.get('shortName') or ticker,
            opportunity_score=round(opportunity_score, 1),
            quality_score=round(quality_score, 1),
            value_score=round(value_score, 1),
            growth_score=round(growth_score, 1),
            risk_score=round(risk_score, 1),
            catalyst_score=round(catalyst_score, 1),
            current_price=info.get('currentPrice') or data.get('price_data', {}).get('current_price') or 0,
            dcf_fair_value=dcf_fv,
            rim_fair_value=rim_fv,
            ensemble_fair_value=ensemble_fv,
            key_metrics=key_metrics,
            component_details={
                'quality': quality_details,
                'value': value_details,
                'growth': growth_details,
                'risk': risk_details,
                'catalyst': catalyst_details,
            }
        )

    def score_universe(self, tickers: List[str]) -> List[OpportunityScore]:
        """
        Score all stocks in a universe.

        Parameters
        ----------
        tickers : list
            List of ticker symbols

        Returns
        -------
        list
            Sorted list of OpportunityScore objects (highest first)
        """
        scores = []
        # One shared connection for the whole universe instead of ~7 per ticker.
        # autocommit=True keeps every read in its own statement, so a failure on
        # one ticker can't poison the connection for the rest and no long-lived
        # transaction is held open across the scan.
        conn = get_db_connection()
        conn.autocommit = True
        try:
            for ticker in tickers:
                try:
                    score = self.score_stock(ticker, conn=conn)
                except Exception as e:
                    logger.warning(f"Scoring failed for {ticker}: {e}")
                    continue
                if score:
                    scores.append(score)
        finally:
            conn.close()

        # Sort by opportunity score (highest first)
        scores.sort(key=lambda x: x.opportunity_score, reverse=True)
        return scores
    def score_growth(self, data: Dict[str, Any]) -> tuple[float, Dict[str, Any]]:
        """
        Score growth potential.

        Sources: 3-Year CAGR (Revenue/Earnings) if available.
        Returns 0.0 total growth score if data is insufficient or invalid, forcing the scanner to fail the stock.
        """
        details = {}
        scores = []
        valid_growth_data = False

        financials = data.get('financials', {})
        income_json = data.get('income') or data.get('income_json')
        
        # Helper to calculate CAGR
        def calculate_cagr(start_val, end_val, years):
            if start_val is None or end_val is None or start_val <= 0 or end_val <= 0 or years <= 0:
                return None
            return (end_val / start_val) ** (1 / years) - 1

        # 1. Revenue Growth (CAGR Priority)
        rev_cagr = None
        
        if income_json:
            import json
            try:
                if isinstance(income_json, str):
                    income_data = json.loads(income_json)
                else:
                    income_data = income_json
                
                rev_row = next((row for row in income_data if row.get("index") in ["Total Revenue", "Operating Revenue"]), None)
                if rev_row:
                    dates = sorted([k for k in rev_row.keys() if k != "index"], reverse=True)
                    if len(dates) >= 4:
                        latest_rev = rev_row[dates[0]]
                        past_rev = rev_row[dates[3]]
                        rev_cagr = calculate_cagr(past_rev, latest_rev, 3)
            except Exception:
                pass

        if rev_cagr is not None:
            rg_score = self.normalize(rev_cagr * 100, 0, 10, 25)
            scores.append(rg_score)
            details['revenue_growth_metric'] = 'CAGR_3Y'
            details['revenue_growth'] = {'value': rev_cagr * 100, 'score': rg_score}
            valid_growth_data = True
        else:
            # Explicitly mark as missing
            details['revenue_growth_metric'] = 'MISSING'
            details['revenue_growth'] = None

        # 2. Earnings Growth (CAGR Priority)
        earn_cagr = None
        if income_json:
            import json
            try:
                if isinstance(income_json, str):
                    income_data = json.loads(income_json)
                else:
                    income_data = income_json
                
                ni_row = next((row for row in income_data if row.get("index") in ["Net Income", "Net Income Common Stockholders"]), None)
                if ni_row:
                    dates = sorted([k for k in ni_row.keys() if k != "index"], reverse=True)
                    if len(dates) >= 4:
                        latest_ni = ni_row[dates[0]]
                        past_ni = ni_row[dates[3]]
                        if past_ni > 0:
                            earn_cagr = calculate_cagr(past_ni, latest_ni, 3)
                        elif latest_ni > 0:
                            earn_cagr = 0.5 
                        else:
                            earn_cagr = -0.1 
            except Exception:
                pass

        if earn_cagr is not None:
            eg_score = self.normalize(earn_cagr * 100, 0, 12, 30)
            scores.append(eg_score)
            details['earnings_growth_metric'] = 'CAGR_3Y'
            details['earnings_growth'] = {'value': earn_cagr * 100, 'score': eg_score}
            valid_growth_data = True
        else:
            details['earnings_growth_metric'] = 'MISSING'
            details['earnings_growth'] = None

        # 3. Price Momentum (unchanged)
        price_trend = data.get('price_data', {}).get('price_trend_30d')
        if price_trend is not None:
            pt_score = self.normalize(price_trend * 100, -10, 5, 15)
            scores.append(pt_score * 0.5)
            details['price_trend_30d'] = {'value': price_trend * 100, 'score': pt_score}

        # If we have NO valid fundamental growth data (Revenue or Earnings), return 0.0 (Fail)
        # Force a failing grade so it never passes the threshold.
        if not valid_growth_data:
             return 0.0, details

        final_score = sum(scores) / len(scores) if scores else 0.0
        return final_score, details