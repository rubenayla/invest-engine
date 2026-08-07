#!/usr/bin/env python
"""
Offline Analysis Engine

Runs investment analysis on cached stock data without network calls.
Fast, reliable, and can process large numbers of stocks.

Usage:
    uv run python scripts/offline_analyzer.py --universe sp500 --update-dashboard
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.data_fetcher import StockDataCache
from src.invest.dashboard_components.valuation_engine import ValuationEngine
from src.invest.valuation.model_registry import get_available_models

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OfflineValuationEngine:
    """Performs valuation analysis on cached stock data"""

    def __init__(self, cache_dir: str = 'data/stock_cache'):
        self.cache = StockDataCache(cache_dir)
        self.valuation_engine = ValuationEngine()
        self.available_models = get_available_models()

    def calculate_composite_score(self, stock_data: Dict) -> float:
        """Calculate composite investment score from cached data"""
        try:
            info = stock_data.get('info', {})
            financials = stock_data.get('financials', {})

            # Value Score (0-40 points)
            value_score = 0
            pe_ratio = financials.get('trailingPE')
            pb_ratio = financials.get('priceToBook')

            if pe_ratio and pe_ratio > 0:
                if pe_ratio < 15: value_score += 15
                elif pe_ratio < 25: value_score += 10
                elif pe_ratio < 35: value_score += 5

            if pb_ratio and pb_ratio > 0:
                if pb_ratio < 1.5: value_score += 15
                elif pb_ratio < 3.0: value_score += 10
                elif pb_ratio < 5.0: value_score += 5

            # Add dividend yield consideration
            market_cap = info.get('marketCap')
            if market_cap and market_cap > 1e9:  # Large cap bonus
                value_score += 10

            # Quality Score (0-35 points)
            quality_score = 0
            roe = financials.get('returnOnEquity')
            debt_equity = financials.get('debtToEquity')
            current_ratio = financials.get('currentRatio')
            margins = financials.get('operatingMargins')

            if roe and roe > 0.15: quality_score += 10
            elif roe and roe > 0.10: quality_score += 5

            if debt_equity and debt_equity < 0.5: quality_score += 10
            elif debt_equity and debt_equity < 1.0: quality_score += 5

            if current_ratio and current_ratio > 1.5: quality_score += 10
            elif current_ratio and current_ratio > 1.0: quality_score += 5

            if margins and margins > 0.20: quality_score += 5

            # Growth Score (0-25 points)
            growth_score = 0
            revenue_growth = financials.get('revenueGrowth')
            earnings_growth = financials.get('earningsGrowth')

            if revenue_growth and revenue_growth > 0.15: growth_score += 15
            elif revenue_growth and revenue_growth > 0.05: growth_score += 10
            elif revenue_growth and revenue_growth > 0: growth_score += 5

            if earnings_growth and earnings_growth > 0.15: growth_score += 10
            elif earnings_growth and earnings_growth > 0: growth_score += 5

            total_score = min(100, value_score + quality_score + growth_score)

            return total_score

        except Exception as e:
            logger.warning(f"Error calculating score for {stock_data.get('ticker', 'unknown')}: {e}")
            return 50.0  # Default neutral score

    def calculate_dcf_estimate(self, stock_data: Dict) -> Dict:
        """Simple DCF calculation from cached data"""
        try:
            info = stock_data.get('info', {})
            financials = stock_data.get('financials', {})
            price_data = stock_data.get('price_data', {})

            current_price = price_data.get('current_price') or info.get('currentPrice') or 0

            # Simple DCF based on available metrics
            revenue = financials.get('totalRevenue')
            margin = financials.get('profitMargins') or 0.1
            shares = financials.get('sharesOutstanding')
            growth_rate = financials.get('revenueGrowth') or 0.05

            if not all([revenue, shares]) or any(x <= 0 for x in [revenue, shares]):
                return {
                    'fair_value': current_price * 1.1,  # Small premium as default
                    'current_price': current_price,
                    'margin_of_safety': 0.1,
                    'confidence': 'low',
                    'method': 'fallback_estimate'
                }

            # Simple 5-year DCF
            annual_earnings = revenue * margin
            terminal_multiple = 15  # Conservative P/E for terminal value
            discount_rate = 0.10

            # Project 5 years of cash flows
            total_pv = 0
            for year in range(1, 6):
                future_earnings = annual_earnings * ((1 + growth_rate) ** year)
                pv = future_earnings / ((1 + discount_rate) ** year)
                total_pv += pv

            # Terminal value
            terminal_earnings = annual_earnings * ((1 + growth_rate) ** 5)
            terminal_value = terminal_earnings * terminal_multiple
            terminal_pv = terminal_value / ((1 + discount_rate) ** 5)

            enterprise_value = total_pv + terminal_pv
            fair_value_per_share = enterprise_value / shares

            margin_of_safety = (fair_value_per_share - current_price) / fair_value_per_share if fair_value_per_share > 0 else 0

            # Confidence based on data quality
            confidence = 'medium'
            if not financials.get('totalRevenue') or not financials.get('sharesOutstanding'):
                confidence = 'low'
            elif margin > 0.15 and growth_rate > 0.10:
                confidence = 'high'

            return {
                'fair_value': fair_value_per_share,
                'current_price': current_price,
                'margin_of_safety': margin_of_safety,
                'confidence': confidence,
                'method': 'simple_dcf',
                'assumptions': {
                    'growth_rate': growth_rate,
                    'discount_rate': discount_rate,
                    'terminal_multiple': terminal_multiple,
                    'profit_margin': margin
                }
            }

        except Exception as e:
            logger.warning(f"DCF calculation failed for {stock_data.get('ticker', 'unknown')}: {e}")
            current_price = stock_data.get('price_data', {}).get('current_price', 0)
            return {
                'fair_value': current_price,
                'current_price': current_price,
                'margin_of_safety': 0,
                'confidence': 'low',
                'method': 'error_fallback'
            }

    def analyze_stock(self, ticker: str, stock_data: Dict) -> Dict:
        """Analyze a single stock with cached data using comprehensive valuation models"""
        try:
            info = stock_data.get('info', {})
            financials = stock_data.get('financials', {})
            price_data = stock_data.get('price_data', {})

            # Basic info extraction
            analysis = {
                'ticker': ticker,
                'status': 'completed',
                'status_message': 'Analysis completed successfully',
                'current_price': price_data.get('current_price') or info.get('currentPrice') or 0,
                'company_name': info.get('longName') or info.get('shortName') or ticker,
                'sector': info.get('sector') or 'Unknown',
                'industry': info.get('industry') or 'Unknown',
                'market_cap': info.get('marketCap') or 0,
                'exchange': info.get('exchange') or 'Unknown',
                'currency': info.get('currency') or 'USD',
                'country': info.get('country') or 'Unknown'
            }

            # Calculate scores
            composite_score = self.calculate_composite_score(stock_data)
            analysis['composite_score'] = composite_score

            # Break down scores (simplified for now)
            analysis['value_score'] = min(40, composite_score * 0.4)
            analysis['quality_score'] = min(35, composite_score * 0.35)
            analysis['growth_score'] = min(25, composite_score * 0.25)

            # Financial metrics
            analysis['financial_metrics'] = {
                'trailing_pe': financials.get('trailingPE'),
                'forward_pe': financials.get('forwardPE'),
                'price_to_book': financials.get('priceToBook'),
                'return_on_equity': financials.get('returnOnEquity'),
                'debt_to_equity': financials.get('debtToEquity'),
                'current_ratio': financials.get('currentRatio'),
                'operating_margins': financials.get('operatingMargins'),
                'profit_margins': financials.get('profitMargins'),
                'revenue_growth': financials.get('revenueGrowth'),
                'earnings_growth': financials.get('earningsGrowth')
            }

            # Price metrics
            analysis['price_metrics'] = {
                'price_52w_high': price_data.get('price_52w_high'),
                'price_52w_low': price_data.get('price_52w_low'),
                'avg_volume': price_data.get('avg_volume'),
                'price_trend_30d': price_data.get('price_trend_30d')
            }

            # Run ALL Available Valuation Models
            current_price = analysis['current_price']
            analysis['valuations'] = {'current_price': current_price}

            logger.debug(f"Running {len(self.available_models)} valuation models for {ticker}")

            # Run each valuation model using the comprehensive engine
            for model_name in self.available_models:
                try:
                    logger.debug(f"Running {model_name} model for {ticker}")
                    valuation_result = self.valuation_engine.run_valuation(ticker, model_name, timeout=30)

                    if valuation_result:
                        analysis['valuations'][model_name] = valuation_result
                        logger.debug(f"✅ {model_name} completed for {ticker}")
                    else:
                        analysis['valuations'][model_name] = {
                            'error': 'Model returned None',
                            'fair_value': None,
                            'confidence': 'low'
                        }
                        logger.debug(f"❌ {model_name} returned None for {ticker}")

                except Exception as e:
                    analysis['valuations'][model_name] = {
                        'error': str(e),
                        'fair_value': None,
                        'confidence': 'low'
                    }
                    logger.debug(f"❌ {model_name} failed for {ticker}: {e}")

            # Calculate summary statistics from all models
            successful_models = 0
            total_expected_value = 0
            model_count = 0

            for model_name, result in analysis['valuations'].items():
                if model_name == 'current_price':
                    continue

                if isinstance(result, dict) and result.get('fair_value') and not result.get('error'):
                    successful_models += 1
                    fair_value = result.get('fair_value', 0)
                    if fair_value and fair_value > 0:
                        total_expected_value += fair_value
                        model_count += 1

            # Add ensemble statistics
            analysis['valuation_summary'] = {
                'successful_models': successful_models,
                'total_models': len(self.available_models),
                'average_expected_value': total_expected_value / model_count if model_count > 0 else current_price,
                'current_price': current_price
            }

            if model_count > 0:
                analysis['valuation_summary']['expected_vs_market_ratio'] = (total_expected_value / model_count) / current_price if current_price > 0 else 1.0
            else:
                analysis['valuation_summary']['expected_vs_market_ratio'] = 1.0

            # Analysis timestamp
            analysis['analysis_timestamp'] = datetime.now().isoformat()
            analysis['data_source_timestamp'] = stock_data.get('_cache_metadata', {}).get('cached_at')

            logger.info(f"✅ Analyzed {ticker}: {successful_models}/{len(self.available_models)} models successful")
            return analysis

        except Exception as e:
            logger.error(f"Analysis failed for {ticker}: {e}")
            return {
                'ticker': ticker,
                'status': 'failed',
                'status_message': f'Analysis failed: {str(e)}',
                'error': str(e),
                'analysis_timestamp': datetime.now().isoformat()
            }

    def analyze_multiple_stocks(self, tickers: List[str]) -> Dict[str, Dict]:
        """Analyze multiple stocks from cache"""

        results = {}
        cached_tickers = self.cache.get_cached_tickers()
        available_tickers = [t for t in tickers if t in cached_tickers]

        logger.info(f"Analyzing {len(available_tickers)} stocks with cached data")

        for i, ticker in enumerate(available_tickers, 1):
            try:
                stock_data = self.cache.get_cached_data(ticker)
                if not stock_data:
                    logger.warning(f"No cached data found for {ticker}")
                    continue

                analysis = self.analyze_stock(ticker, stock_data)
                results[ticker] = analysis

                if i % 50 == 0:
                    logger.info(f"Analyzed {i}/{len(available_tickers)} stocks")

            except Exception as e:
                logger.error(f"Failed to analyze {ticker}: {e}")
                results[ticker] = {
                    'ticker': ticker,
                    'status': 'failed',
                    'error': str(e)
                }

        logger.info(f"Analysis complete: {len(results)} stocks processed")
        return results


class DashboardIntegration:
    """Integrates offline analysis with dashboard"""

    def __init__(self, dashboard_dir: str = 'dashboard'):
        self.dashboard_dir = Path(dashboard_dir)
        self.dashboard_dir.mkdir(exist_ok=True)

    def update_dashboard_data(self, analysis_results: Dict[str, Dict]):
        """Update dashboard with analysis results"""
        dashboard_data = {
            'last_updated': datetime.now().isoformat(),
            'analysis_method': 'offline_cached',
            'total_stocks': len(analysis_results),
            'successful_analyses': sum(1 for r in analysis_results.values() if r.get('status') == 'completed'),
            'stocks': analysis_results
        }

        # Save dashboard data
        dashboard_file = self.dashboard_dir / 'dashboard_data.json'
        with open(dashboard_file, 'w') as f:
            json.dump(dashboard_data, f, indent=2)

        logger.info(f"Dashboard data updated: {dashboard_file}")

        # Create summary report
        successful = dashboard_data['successful_analyses']
        total = dashboard_data['total_stocks']
        avg_score = 0

        if successful > 0:
            scores = [r.get('composite_score', 0) for r in analysis_results.values() if r.get('status') == 'completed']
            avg_score = sum(scores) / len(scores) if scores else 0

        summary = {
            'timestamp': datetime.now().isoformat(),
            'total_stocks_analyzed': total,
            'successful_analyses': successful,
            'failed_analyses': total - successful,
            'average_composite_score': avg_score,
            'top_10_stocks': self.get_top_stocks(analysis_results, 10),
            'analysis_method': 'offline_cached_data'
        }

        summary_file = self.dashboard_dir / f'analysis_summary_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)

        logger.info(f"Analysis summary: {summary_file}")
        return summary

    def get_top_stocks(self, analysis_results: Dict[str, Dict], limit: int = 10) -> List[Dict]:
        """Get top N stocks by composite score"""
        completed_stocks = [
            stock for stock in analysis_results.values()
            if stock.get('status') == 'completed' and stock.get('composite_score', 0) > 0
        ]

        # Sort by composite score
        sorted_stocks = sorted(
            completed_stocks,
            key=lambda x: x.get('composite_score', 0),
            reverse=True
        )

        return sorted_stocks[:limit]


async def main():
    """Main offline analysis routine"""
    parser = argparse.ArgumentParser(description='Run offline investment analysis on cached data')
    parser.add_argument('--universe', default='sp500', help='Stock universe to analyze')
    parser.add_argument('--update-dashboard', action='store_true', help='Update dashboard with results')
    parser.add_argument('--cache-dir', default='data/stock_cache', help='Cache directory location')

    args = parser.parse_args()

    # Initialize analyzer
    analyzer = OfflineValuationEngine(args.cache_dir)

    # Get available cached tickers
    available_tickers = list(analyzer.cache.get_cached_tickers())
    logger.info(f"Found {len(available_tickers)} stocks in cache")

    if not available_tickers:
        logger.error("No cached stock data found. Run data_fetcher.py first!")
        return

    # Determine which tickers to analyze
    if args.universe == 'cached':
        target_tickers = available_tickers
    else:
        # Import the universe function from data_fetcher
        from scripts.data_fetcher import get_universe_tickers
        universe_tickers = get_universe_tickers(args.universe)
        target_tickers = [t for t in universe_tickers if t in available_tickers]

        logger.info(f"Target universe: {len(universe_tickers)} stocks, {len(target_tickers)} available in cache")


    if not target_tickers:
        logger.error(f"No stocks available for analysis in {args.universe} universe")
        return

    # Run analysis
    logger.info(f"Starting offline analysis of {len(target_tickers)} stocks")
    start_time = time.time()

    results = analyzer.analyze_multiple_stocks(target_tickers)

    elapsed = time.time() - start_time
    logger.info(f"Analysis completed in {elapsed:.2f} seconds ({elapsed/len(results):.3f} sec/stock)")

    # Update dashboard if requested
    if args.update_dashboard:
        dashboard = DashboardIntegration()
        summary = dashboard.update_dashboard_data(results)

        logger.info(f"""
Dashboard Update Summary:
  - Total stocks: {summary['total_stocks_analyzed']}
  - Successful: {summary['successful_analyses']}
  - Failed: {summary['failed_analyses']}
  - Average score: {summary['average_composite_score']:.1f}
  - Top stock: {summary['top_10_stocks'][0]['ticker'] if summary['top_10_stocks'] else 'None'} ({summary['top_10_stocks'][0].get('composite_score', 0):.1f})
        """)

    # Save raw results
    results_file = Path(f'offline_analysis_results_{args.universe}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)

    logger.info(f"Raw results saved: {results_file}")


if __name__ == '__main__':
    asyncio.run(main())
