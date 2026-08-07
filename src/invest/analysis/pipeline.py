import logging
from typing import Any, Dict, List

from ..config.constants import ANALYSIS_LIMITS
from ..config.schema import AnalysisConfig

# Removed old data fetching modules - now using universal_fetcher for all stocks
from ..data.universal_fetcher import UniversalStockFetcher
from ..dividend_aware_dcf import calculate_enhanced_dcf
from ..screening.growth import screen_growth
from ..screening.quality import screen_quality
from ..screening.risk import apply_cyclical_adjustments, screen_risk
from ..screening.value import screen_value
from ..simple_ratios import calculate_simple_ratios_valuation
from ..standard_dcf import calculate_dcf

# Import the modern valuation system
try:
    from ..valuation.model_registry import ModelRegistry
    from ..valuation.multi_timeframe_models import MultiTimeframeNeuralNetworks
    MODEL_REGISTRY_AVAILABLE = True
except ImportError:
    MODEL_REGISTRY_AVAILABLE = False
    logging.warning("Modern valuation system not available - using legacy models only")

# Set up logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


class AnalysisPipeline:
    """Systematic investment analysis pipeline."""

    def __init__(self, config: AnalysisConfig):
        self.config = config
        self.results = {}

        # Initialize modern valuation system if available
        if MODEL_REGISTRY_AVAILABLE:
            self.model_registry = ModelRegistry()
            self.neural_networks = MultiTimeframeNeuralNetworks()
            logger.info("Modern valuation system initialized")
        else:
            self.model_registry = None
            self.neural_networks = None

    def run_analysis(self) -> Dict[str, Any]:
        """Execute the complete analysis pipeline."""
        logger.info(f"Starting analysis: {self.config.name}")

        # Step 1: Get stock universe
        logger.info("Step 1: Building stock universe...")
        stocks_data = self._get_universe()
        logger.info(f"Universe contains {len(stocks_data)} stocks")

        if not stocks_data:
            logger.error("No stocks found in universe")
            return {"error": "No stocks found in universe"}

        # Step 2: Apply cyclical adjustments if needed
        if self.config.risk.cyclical_adjustment:
            logger.info("Applying cyclical adjustments...")
            stocks_data = apply_cyclical_adjustments(stocks_data, self.config.risk)

        # Step 3: Quality screening
        logger.info("Step 2: Quality assessment...")
        quality_results = screen_quality(stocks_data, self.config.quality)

        # Step 4: Value screening
        logger.info("Step 3: Value assessment...")
        value_results = screen_value(stocks_data, self.config.value)

        # Step 5: Growth screening
        logger.info("Step 4: Growth assessment...")
        growth_results = screen_growth(stocks_data, self.config.growth)

        # Step 6: Risk screening
        logger.info("Step 5: Risk assessment...")
        risk_results = screen_risk(stocks_data, self.config.risk)

        # Step 7: Combine results
        logger.info("Step 6: Combining screening results...")
        combined_results = self._combine_screening_results(
            stocks_data, quality_results, value_results, growth_results, risk_results
        )

        # Step 8: Apply filters and ranking
        logger.info("Step 7: Filtering and ranking...")
        filtered_results = self._apply_filters(combined_results)
        ranked_results = self._rank_results(combined_results)  # Rank ALL results, not just filtered

        # Step 9: Run valuation models on top candidates
        logger.info("Step 8: Running valuation models...")
        final_results = self._run_valuations(ranked_results[: self.config.max_results])

        # Step 10: Generate summary
        summary = self._generate_summary(final_results)

        # Include all analyzed stocks in results
        self.results = {
            "config": self.config.dict(),
            "summary": summary,
            "stocks": final_results,
            "all_stocks": combined_results,  # Include ALL analyzed stocks
            "total_universe": len(stocks_data),
            "passed_screening": len(filtered_results),
            "final_results": len(final_results),
        }

        logger.info(
            f"Analysis complete: {len(final_results)} stocks selected from {len(combined_results)} analyzed"
        )
        return self.results

    def _get_universe(self) -> List[Dict]:
        """Build the stock universe based on configuration."""
        universe_config = self.config.universe

        # Check if we have direct tickers in config (new style)
        if hasattr(self.config, 'tickers') and self.config.tickers:
            tickers = self.config.tickers
        elif universe_config.custom_tickers:
            tickers = universe_config.custom_tickers
        elif (
            hasattr(universe_config, "pre_screening_universe")
            and universe_config.pre_screening_universe == "sp500"
        ):
            # S&P 500 (Full Real List)
            logger.info("Fetching real S&P 500 constituent list...")
            from ..data.index_manager import IndexManager
            im = IndexManager()
            tickers = im.get_index_tickers('sp500')

        elif (
            hasattr(universe_config, "pre_screening_universe")
            and universe_config.pre_screening_universe == "global"
        ):
            # Global (USA, Argentina, India, Japan)
            logger.info("Fetching global constituent list (US, Arg, India, Japan)...")
            from ..data.index_manager import IndexManager
            im = IndexManager()
            tickers = im.get_all_tickers()
        elif hasattr(universe_config, "market"):
            # International market support with predefined lists
            market = universe_config.market
            if market == "japan_buffett":
                # Japanese blue chip companies Buffett might like
                tickers = ["7203.T", "6758.T", "8058.T", "8002.T", "4063.T", "9432.T"]
            elif market == "international_buffett":
                # International value stocks
                tickers = ["ASML.AS", "NESN.SW", "SAP.DE", "MC.PA", "7203.T", "8002.T"]
            else:
                # Default international mix
                tickers = ["ASML.AS", "SAP.DE", "NESN.SW", "7203.T", "0700.HK"]
        elif universe_config.region == "US":
            # Default to S&P 500 sample
            tickers = [
                'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'TSLA', 'META', 'BRK-B',
                'UNH', 'JNJ', 'V', 'WMT', 'XOM', 'LLY', 'JPM', 'PG', 'MA', 'HD',
                'CVX', 'ABBV', 'BAC', 'PFE', 'COST', 'AVGO', 'KO', 'PEP', 'TMO',
                'MRK', 'CSCO', 'ACN', 'LIN', 'DHR', 'ABT', 'VZ', 'ADBE', 'CRM',
                'NFLX', 'NKE', 'TXN', 'DIS', 'WFC', 'INTC', 'PM', 'AMD', 'BMY'
            ]
        else:
            # For non-US, use a smaller sample for now
            tickers = ["ASML", "SAP", "NESN.SW"] if universe_config.region == "EU" else ["TSM"]

        # Optimization: If we need top N by market cap, pre-filter tickers first
        if hasattr(universe_config, "top_n_by_market_cap") and universe_config.top_n_by_market_cap:
            logger.info(
                f"Pre-filtering to top {universe_config.top_n_by_market_cap} stocks by market cap..."
            )

            # Get basic market cap data for sorting (faster than full data)
            # Limit to prevent timeout during market cap fetching
            max_fetch = min(
                len(tickers),
                max(
                    ANALYSIS_LIMITS.MAX_TICKERS_FOR_MARKET_CAP_FETCH,
                    universe_config.top_n_by_market_cap * ANALYSIS_LIMITS.MARKET_CAP_FETCH_MULTIPLIER
                )
            )
            logger.info(f"Fetching market cap data for top {max_fetch} tickers...")

            # Use concurrent fetching for market cap data
            def progress_callback(completed: int, total: int):
                if completed % 25 == 0:
                    logger.info(f"Processed {completed}/{total} tickers for market cap...")

            fetcher = UniversalStockFetcher(convert_currency=True)
            fetcher_results = fetcher.fetch_multiple(tickers[:max_fetch])

            ticker_market_caps = []
            for ticker, stock_data in fetcher_results.items():
                if stock_data and 'marketCap' in stock_data:
                    market_cap = stock_data.get('marketCap', 0)
                    if market_cap and market_cap > 0:
                        ticker_market_caps.append((ticker, market_cap))

            # Sort by market cap and take top N
            ticker_market_caps.sort(key=lambda x: x[1], reverse=True)
            tickers = [
                ticker for ticker, _ in ticker_market_caps[: universe_config.top_n_by_market_cap]
            ]
            logger.info(f"Pre-filtered to {len(tickers)} tickers by market cap")

        # Get full stock data for filtered tickers
        logger.info(f"Fetching full stock data for {len(tickers)} tickers...")

        # Check if we have mixed international tickers
        has_international = any('.' in str(t) or ':' in str(t) for t in tickers)

        stocks_data = []

        if has_international or universe_config.region == "ALL":
            # Use universal fetcher for mixed/international portfolios
            logger.info("Using universal fetcher for mixed international stocks...")
            # from ..data.universal_fetcher import UniversalStockFetcher

            fetcher = UniversalStockFetcher(convert_currency=True)
            fetcher_results = fetcher.fetch_multiple(tickers, max_workers=10)

            for ticker in tickers:
                stock_data = fetcher_results.get(ticker)
                if stock_data:
                    # Check filters and add filter status
                    stock_data["passes_universe_filters"] = self._passes_universe_filters(
                        stock_data, universe_config
                    )
                    stocks_data.append(stock_data)
        else:
            # Use universal fetcher for all stocks (handles both domestic and international)
            logger.info("Using universal fetcher for all stocks...")
            # from ..data.universal_fetcher import UniversalStockFetcher

            fetcher = UniversalStockFetcher(convert_currency=True)
            fetcher_results = fetcher.fetch_multiple(tickers, max_workers=10)

            for ticker in tickers:
                stock_data = fetcher_results.get(ticker)
                if stock_data:
                    # Check filters and add filter status
                    stock_data["passes_universe_filters"] = self._passes_universe_filters(
                        stock_data, universe_config
                    )
                    stocks_data.append(stock_data)

        passed_count = sum(1 for s in stocks_data if s["passes_universe_filters"])
        logger.info(f"Completed fetching data for {len(tickers)} tickers. {passed_count} passed universe filters.")

        return stocks_data

    def _passes_universe_filters(self, stock_data: Dict, universe_config) -> bool:
        """Check if stock passes universe-level filters."""
        market_cap = stock_data.get("market_cap", 0)
        sector = stock_data.get("sector", "")

        # Market cap filters
        passes_filters = True
        filter_reasons = []

        # Market cap filter
        if universe_config.min_market_cap and (
            not market_cap or market_cap < universe_config.min_market_cap * 1e6
        ):
            passes_filters = False
            filter_reasons.append(f"Market cap too low: {market_cap/1e6:.2f}M")

        if (
            universe_config.max_market_cap
            and market_cap
            and market_cap > universe_config.max_market_cap * 1e6
        ):
            passes_filters = False
            filter_reasons.append(f"Market cap too high: {market_cap/1e6:.2f}M")

        # Sector filters
        if universe_config.exclude_sectors and sector in universe_config.exclude_sectors:
            passes_filters = False
            filter_reasons.append(f"Excluded sector: {sector}")

        if universe_config.sectors and sector not in universe_config.sectors:
            passes_filters = False
            filter_reasons.append(f"Not in allowed sectors: {sector}")

        # Detailed logging
        if not passes_filters:
            logger.info(
                f"Filtering out {stock_data.get('ticker', 'Unknown')}: {', '.join(filter_reasons)}"
            )

        return passes_filters

    def _combine_screening_results(
        self,
        stocks_data: List[Dict],
        quality_results: List[Dict],
        value_results: List[Dict],
        growth_results: List[Dict],
        risk_results: List[Dict],
    ) -> List[Dict]:
        """Combine all screening results into unified records."""
        combined = []

        # Create lookup dictionaries
        quality_lookup = {r["ticker"]: r for r in quality_results}
        value_lookup = {r["ticker"]: r for r in value_results}
        growth_lookup = {r["ticker"]: r for r in growth_results}
        risk_lookup = {r["ticker"]: r for r in risk_results}

        for stock in stocks_data:
            ticker = stock.get("ticker", "")

            combined_record = {
                "ticker": ticker,
                "basic_data": stock,
                "quality": quality_lookup.get(ticker, {}),
                "value": value_lookup.get(ticker, {}),
                "growth": growth_lookup.get(ticker, {}),
                "risk": risk_lookup.get(ticker, {}),
            }

            # Calculate composite score
            quality_score = quality_lookup.get(ticker, {}).get("quality_score", 0)
            value_score = value_lookup.get(ticker, {}).get("value_score", 0)
            growth_score = growth_lookup.get(ticker, {}).get("growth_score", 0)
            risk_score = risk_lookup.get(ticker, {}).get(
                "overall_risk_score", 100
            )  # Higher risk = lower score

            # Composite score (weighted average, risk is inverted)
            composite_score = (
                quality_score * 0.3
                + value_score * 0.3
                + growth_score * 0.25
                + (100 - risk_score) * 0.15  # Invert risk score
            )

            combined_record["composite_score"] = composite_score
            combined_record["scores"] = {
                "quality": quality_score,
                "value": value_score,
                "growth": growth_score,
                "risk": risk_score,
                "composite": composite_score,
            }

            combined.append(combined_record)

        return combined

    def _apply_filters(self, combined_results: List[Dict]) -> List[Dict]:
        """Apply minimum score filters and mark pass/fail status."""
        filtered = []

        # Apply minimum thresholds (now from configuration)
        min_quality = ANALYSIS_LIMITS.MIN_QUALITY_SCORE
        min_value = ANALYSIS_LIMITS.MIN_VALUE_SCORE
        min_growth = ANALYSIS_LIMITS.MIN_GROWTH_SCORE
        max_risk = ANALYSIS_LIMITS.MAX_RISK_SCORE
        min_composite = ANALYSIS_LIMITS.MIN_COMPOSITE_SCORE

        for result in combined_results:
            scores = result.get("scores", {})

            # Check if passes filters
            passes_filters = (
                scores.get("quality", 0) >= min_quality
                and scores.get("value", 0) >= min_value
                and scores.get("growth", 0) >= min_growth
                and scores.get("risk", 100) <= max_risk
                and scores.get("composite", 0) >= min_composite
            )

            # Add pass/fail flag to result
            result["passes_filters"] = passes_filters

            if passes_filters:
                filtered.append(result)

        return filtered

    def _rank_results(self, filtered_results: List[Dict]) -> List[Dict]:
        """Rank results based on configuration."""
        sort_key = self.config.sort_by

        if sort_key == "composite_score":
            return sorted(filtered_results, key=lambda x: x.get("composite_score", 0), reverse=True)
        elif sort_key == "quality_score":
            return sorted(
                filtered_results, key=lambda x: x.get("scores", {}).get("quality", 0), reverse=True
            )
        elif sort_key == "value_score":
            return sorted(
                filtered_results, key=lambda x: x.get("scores", {}).get("value", 0), reverse=True
            )
        elif sort_key == "growth_score":
            return sorted(
                filtered_results, key=lambda x: x.get("scores", {}).get("growth", 0), reverse=True
            )
        else:
            # Default to composite score
            return sorted(filtered_results, key=lambda x: x.get("composite_score", 0), reverse=True)

    def _run_valuations(self, top_results: List[Dict]) -> List[Dict]:
        """Run valuation models on top candidates."""
        for result in top_results:
            ticker = result["ticker"]
            stock_data = result["basic_data"]

            try:
                valuations = {}

                # Use modern valuation system if available
                if self.model_registry is not None:
                    # Get the configured models, default to comprehensive analysis for dashboard
                    models_to_run = self.config.valuation.models

                    # For dashboard updates, always include neural networks
                    if hasattr(self.config, 'is_dashboard_update') and self.config.is_dashboard_update:
                        models_to_run = ['dcf', 'dcf_enhanced', 'simple_ratios',
                                       'neural_network_best', 'neural_network_consensus']

                    # Run all requested models using the registry
                    for model_name in models_to_run:
                        try:
                            model = self.model_registry.get_model(model_name)
                            if model and model.is_suitable(ticker, stock_data):
                                # Convert stock_data format for the model
                                model_result = model._calculate_valuation(ticker, stock_data)
                                if model_result:
                                    valuations[model_name] = {
                                        'fair_value': model_result.fair_value,
                                        'current_price': model_result.current_price,
                                        'margin_of_safety': model_result.margin_of_safety,
                                        'confidence': getattr(model_result, 'confidence', 'medium')
                                    }
                        except Exception as e:
                            logger.warning(f"Model {model_name} failed for {ticker}: {e}")
                            continue

                else:
                    # Fallback to legacy models
                    # Run DCF if configured
                    if "dcf" in self.config.valuation.models:
                        dcf_result = self._run_dcf_valuation(stock_data)
                        if dcf_result:
                            valuations["dcf"] = dcf_result

                    # Run Enhanced DCF if configured
                    if "dcf_enhanced" in self.config.valuation.models:
                        enhanced_dcf_result = self._run_enhanced_dcf_valuation(stock_data)
                        if enhanced_dcf_result:
                            valuations["dcf_enhanced"] = enhanced_dcf_result

                    # Run RIM if configured
                    if "rim" in self.config.valuation.models:
                        rim_result = self._run_rim_valuation(stock_data)
                        if rim_result:
                            valuations["rim"] = rim_result

                    # Run Simple Ratios if configured
                    if "simple_ratios" in self.config.valuation.models:
                        ratios_result = self._run_simple_ratios_valuation(stock_data)
                        if ratios_result:
                            valuations["simple_ratios"] = ratios_result

                result["valuations"] = valuations

            except Exception as e:
                logger.warning(f"Valuation failed for {ticker}: {e}")
                result["valuations"] = {}

        return top_results

    def _run_dcf_valuation(self, stock_data: Dict) -> Dict:
        """Run traditional DCF valuation."""
        try:
            ticker = stock_data.get("ticker", "")
            if not ticker:
                return None

            # Use the original DCF function
            dcf_result = calculate_dcf(ticker, verbose=False)

            return {
                "fair_value": dcf_result.get("fair_value_per_share", 0),
                "current_price": dcf_result.get("current_price", 0),
                "upside_downside": dcf_result.get("margin_of_safety", 0),
                "model": "DCF",
                "confidence": "medium",
                "enterprise_value": dcf_result.get("enterprise_value", 0),
            }
        except Exception as e:
            logger.warning(f"DCF valuation failed for {stock_data.get('ticker', 'unknown')}: {e}")
            return None

    def _run_enhanced_dcf_valuation(self, stock_data: Dict) -> Dict:
        """Run enhanced DCF valuation with dividend policy awareness."""
        try:
            ticker = stock_data.get("ticker", "")
            if not ticker:
                return None

            # Use the enhanced DCF function that accounts for dividends
            dcf_result = calculate_enhanced_dcf(ticker, verbose=False)

            return {
                "fair_value": dcf_result.get("fair_value_per_share", 0),
                "current_price": dcf_result.get("current_price", 0),
                "upside_downside": dcf_result.get("margin_of_safety", 0),
                "model": "Enhanced DCF",
                "confidence": "high",  # Higher confidence due to dividend consideration
                "enterprise_value": dcf_result.get("enterprise_value", 0),
                # Enhanced dividend-specific metrics
                "dividend_component_value": dcf_result.get("dividend_component_value", 0),
                "growth_component_value": dcf_result.get("growth_component_value", 0),
                "dividend_yield": dcf_result.get("dividend_yield", 0),
                "payout_ratio": dcf_result.get("payout_ratio", 0),
                "sustainable_growth_rate": dcf_result.get("sustainable_growth_rate", 0),
                "capital_allocation_efficiency": dcf_result.get("reinvestment_efficiency", 0),
            }
        except Exception as e:
            logger.warning(
                f"Enhanced DCF valuation failed for {stock_data.get('ticker', 'unknown')}: {e}"
            )
            return None

    def _run_rim_valuation(self, stock_data: Dict) -> Dict:
        """Run RIM valuation (placeholder implementation)."""
        # This would integrate with your existing RIM model
        current_price = stock_data.get("current_price", 0)
        book_value = stock_data.get("price_to_book", 0)

        if not current_price or not book_value:
            return None

        # Very rough RIM approximation
        fair_value = current_price * 0.95  # Placeholder logic

        return {
            "fair_value": fair_value,
            "current_price": current_price,
            "upside_downside": (fair_value / current_price - 1) if current_price > 0 else 0,
            "model": "RIM",
            "confidence": "medium",
        }

    def _run_simple_ratios_valuation(self, stock_data: Dict) -> Dict:
        """Run simple ratios valuation model."""
        try:
            # Extract valuation config for simple ratios
            valuation_config = {
                "pe_target": self.config.valuation.pe_target,
                "pb_target": self.config.valuation.pb_target,
                "ps_target": self.config.valuation.ps_target,
                "ev_ebitda_target": self.config.valuation.ev_ebitda_target,
                "dividend_yield_target": self.config.valuation.dividend_yield_target,
                "peg_target": self.config.valuation.peg_target,
            }

            # Run simple ratios valuation
            ratios_result = calculate_simple_ratios_valuation(stock_data, valuation_config)

            if ratios_result and ratios_result.get("valuation_price"):
                return {
                    "fair_value": ratios_result["valuation_price"],
                    "current_price": ratios_result["current_price"],
                    "upside_downside": ratios_result.get("upside_potential", 0)
                    / 100,  # Convert percentage to decimal
                    "model": "Simple Ratios",
                    "confidence": ratios_result.get("confidence", "medium"),
                    "composite_score": ratios_result.get("composite_score"),
                    "component_scores": ratios_result.get("component_scores", {}),
                    "sector_adjustments": ratios_result.get("sector_adjustments", {}),
                }
            else:
                return None

        except Exception as e:
            logger.warning(
                f"Simple ratios valuation failed for {stock_data.get('ticker', 'unknown')}: {e}"
            )
            return None

    def _generate_summary(self, final_results: List[Dict]) -> Dict:
        """Generate analysis summary."""
        if not final_results:
            return {
                "top_picks": [],
                "average_scores": {},
                "sector_breakdown": {},
                "key_insights": ["No stocks passed the screening criteria"],
            }

        # Calculate average scores
        avg_quality = sum(r.get("scores", {}).get("quality", 0) for r in final_results) / len(
            final_results
        )
        avg_value = sum(r.get("scores", {}).get("value", 0) for r in final_results) / len(
            final_results
        )
        avg_growth = sum(r.get("scores", {}).get("growth", 0) for r in final_results) / len(
            final_results
        )
        avg_risk = sum(r.get("scores", {}).get("risk", 0) for r in final_results) / len(
            final_results
        )

        # Sector breakdown
        sectors = {}
        for result in final_results:
            sector = result.get("basic_data", {}).get("sector", "Unknown")
            sectors[sector] = sectors.get(sector, 0) + 1

        # Count total and filtered stocks available in results
        # total_analyzed = self.results.get('total_universe', len(final_results))  # Reserved for future use

        # Top picks (top 5)
        top_picks = [
            {
                "ticker": r["ticker"],
                "composite_score": r.get("composite_score", 0),
                "sector": r.get("basic_data", {}).get("sector", "Unknown"),
            }
            for r in final_results[:5]
        ]

        return {
            "top_picks": top_picks,
            "average_scores": {
                "quality": round(avg_quality, 1),
                "value": round(avg_value, 1),
                "growth": round(avg_growth, 1),
                "risk": round(avg_risk, 1),
            },
            "sector_breakdown": sectors,
            "key_insights": [
                f"Found {len(final_results)} stocks meeting criteria",
                f"Average composite score: {sum(r.get('composite_score', 0) for r in final_results) / len(final_results):.1f}",
                f"Most represented sector: {max(sectors.items(), key=lambda x: x[1])[0] if sectors else 'None'}",
            ],
        }
