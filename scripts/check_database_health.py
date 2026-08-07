#!/usr/bin/env python3
"""
Database Health Monitor

Checks data quality, coverage, and freshness across all database tables.
Provides actionable warnings when data is missing or stale.
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple


class DatabaseHealthChecker:
    """Monitor database health and data quality."""

    def __init__(self, db_path: str = 'data/stock_data.db'):
        project_root = Path(__file__).parent.parent
        self.db_path = project_root / db_path
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        self.issues = []
        self.warnings = []
        self.info = []

    def check_table_coverage(self) -> Dict[str, int]:
        """Check stock coverage across all tables."""
        coverage = {}

        # Assets table
        coverage['assets'] = self.cursor.execute(
            'SELECT COUNT(DISTINCT symbol) FROM assets'
        ).fetchone()[0]

        # Fundamental history (stocks with time-series data)
        coverage['fundamental_history'] = self.cursor.execute(
            'SELECT COUNT(DISTINCT asset_id) FROM fundamental_history'
        ).fetchone()[0]

        # Current stock data
        coverage['current_stock_data'] = self.cursor.execute(
            'SELECT COUNT(DISTINCT ticker) FROM current_stock_data'
        ).fetchone()[0]

        # Price history
        coverage['price_history'] = self.cursor.execute(
            'SELECT COUNT(DISTINCT ticker) FROM price_history'
        ).fetchone()[0]

        # Valuation results
        coverage['valuation_results'] = self.cursor.execute(
            'SELECT COUNT(DISTINCT ticker) FROM valuation_results'
        ).fetchone()[0]

        macro_exists = self.cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='macro_rates'"
        ).fetchone()
        if macro_exists:
            coverage['macro_rates'] = self.cursor.execute(
                'SELECT COUNT(*) FROM macro_rates'
            ).fetchone()[0]
        else:
            coverage['macro_rates'] = 0

        return coverage

    def check_data_freshness(self) -> Dict[str, Tuple[str, int]]:
        """Check how recent the data is in each table."""
        freshness = {}
        today = datetime.now()

        # Fundamental history
        latest_snapshot = self.cursor.execute(
            'SELECT MAX(snapshot_date) FROM fundamental_history'
        ).fetchone()[0]

        if latest_snapshot:
            snapshot_date = datetime.strptime(latest_snapshot, '%Y-%m-%d')
            days_old = (today - snapshot_date).days
            freshness['fundamental_history'] = (latest_snapshot, days_old)

        # Current stock data
        latest_current = self.cursor.execute(
            'SELECT MAX(last_updated) FROM current_stock_data'
        ).fetchone()[0]

        if latest_current:
            current_date = datetime.fromisoformat(latest_current)
            days_old = (today - current_date).days
            freshness['current_stock_data'] = (latest_current, days_old)

        # Price history
        latest_price = self.cursor.execute(
            'SELECT MAX(date) FROM price_history'
        ).fetchone()[0]

        if latest_price:
            price_date = datetime.strptime(latest_price, '%Y-%m-%d')
            days_old = (today - price_date).days
            freshness['price_history'] = (latest_price, days_old)

        # Valuation results
        latest_valuation = self.cursor.execute(
            'SELECT MAX(timestamp) FROM valuation_results'
        ).fetchone()[0]

        if latest_valuation:
            val_date = datetime.fromisoformat(latest_valuation)
            days_old = (today - val_date).days
            freshness['valuation_results'] = (latest_valuation, days_old)

        macro_exists = self.cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='macro_rates'"
        ).fetchone()
        if macro_exists:
            latest_macro = self.cursor.execute(
                "SELECT MAX(date) FROM macro_rates WHERE rate_name = 'risk_free_rate'"
            ).fetchone()[0]
            if latest_macro:
                macro_date = datetime.strptime(latest_macro, '%Y-%m-%d')
                macro_days_old = (today - macro_date).days
                freshness['macro_rates'] = (latest_macro, macro_days_old)

        return freshness

    def check_coverage_gaps(self) -> Dict[str, List[str]]:
        """Find stocks missing from various tables."""
        gaps = {}

        # Stocks in current_stock_data but NOT in assets (can't use GBM)
        missing_from_assets = self.cursor.execute('''
            SELECT ticker
            FROM current_stock_data
            WHERE ticker NOT IN (SELECT symbol FROM assets)
            ORDER BY ticker
        ''').fetchall()
        gaps['missing_from_assets'] = [t[0] for t in missing_from_assets]

        # Stocks in assets but NOT in current_stock_data (no DCF)
        missing_from_current = self.cursor.execute('''
            SELECT symbol
            FROM assets
            WHERE symbol NOT IN (SELECT ticker FROM current_stock_data)
            ORDER BY symbol
        ''').fetchall()
        gaps['missing_from_current'] = [t[0] for t in missing_from_current]

        # Stocks with assets but no fundamental history (incomplete time-series)
        missing_fundamental_history = self.cursor.execute('''
            SELECT symbol
            FROM assets
            WHERE id NOT IN (SELECT DISTINCT asset_id FROM fundamental_history)
            ORDER BY symbol
        ''').fetchall()
        gaps['missing_fundamental_history'] = [t[0] for t in missing_fundamental_history]

        return gaps

    def check_valuation_coverage(self) -> Dict[str, int]:
        """Check which stocks have which valuation models."""
        model_coverage = {}

        models = ['dcf', 'dcf_enhanced', 'rim', 'simple_ratios', 'gbm_1y', 'gbm_3y']

        for model in models:
            count = self.cursor.execute('''
                SELECT COUNT(DISTINCT ticker)
                FROM valuation_results
                WHERE model_name = ? AND suitable = 1
            ''', (model,)).fetchone()[0]
            model_coverage[model] = count

        return model_coverage

    def analyze_health(self):
        """Run all health checks and generate report."""
        print('🏥 DATABASE HEALTH CHECK')
        print('=' * 80)
        print()

        # 1. Table Coverage
        print('📊 TABLE COVERAGE:')
        coverage = self.check_table_coverage()
        for table, count in coverage.items():
            print(f'  • {table:<25} {count:>4} stocks')
        print()

        # 2. Data Freshness
        print('📅 DATA FRESHNESS:')
        freshness = self.check_data_freshness()
        for table, (date, days) in freshness.items():
            status = '✅' if days <= 7 else '⚠️' if days <= 30 else '❌'
            print(f'  {status} {table:<25} {date[:10]:<12} ({days} days old)')

            if days > 30 and table == 'fundamental_history':
                self.warnings.append(
                    f'Fundamental history is {days} days old - run populate_fundamental_history.py'
                )
            elif days > 7 and table == 'current_stock_data':
                self.warnings.append(
                    f'Current stock data is {days} days old - run data_fetcher.py'
                )
            elif days > 7 and table == 'macro_rates':
                self.warnings.append(
                    f'Macro rates are {days} days old - run update_macro_rates.py'
                )
        print()

        # 3. Coverage Gaps
        print('🔍 COVERAGE GAPS:')
        gaps = self.check_coverage_gaps()

        missing_assets = len(gaps['missing_from_assets'])
        missing_current = len(gaps['missing_from_current'])
        missing_fundamental = len(gaps['missing_fundamental_history'])

        print(f'  • Stocks missing from assets table:        {missing_assets:>3}')
        if missing_assets > 0:
            self.issues.append(
                f'{missing_assets} stocks in current_stock_data but not in assets - GBM models unavailable'
            )
            print(f'    (Examples: {", ".join(gaps["missing_from_assets"][:5])}...)')
            print('    → Run: populate_fundamental_history.py')

        print(f'  • Stocks missing from current_stock_data:  {missing_current:>3}')
        if missing_current > 0:
            self.info.append(
                f'{missing_current} stocks in assets but not in current_stock_data - DCF models may not work'
            )

        print(f'  • Assets without fundamental history:      {missing_fundamental:>3}')
        if missing_fundamental > 0:
            self.warnings.append(
                f'{missing_fundamental} assets registered but have no historical fundamental data'
            )
        print()

        # 4. Valuation Model Coverage
        print('📈 VALUATION MODEL COVERAGE:')
        model_coverage = self.check_valuation_coverage()
        total_stocks = coverage['current_stock_data']

        for model, count in model_coverage.items():
            pct = (count / total_stocks * 100) if total_stocks > 0 else 0
            status = '✅' if pct >= 80 else '⚠️' if pct >= 50 else '❌'
            print(f'  {status} {model:<20} {count:>3}/{total_stocks} stocks ({pct:.0f}%)')

            if pct < 50 and model.startswith('gbm'):
                self.issues.append(
                    f'{model} only covers {pct:.0f}% of stocks - populate snapshots for missing stocks'
                )
        print()

        # 5. Summary
        print('=' * 80)
        if self.issues:
            print('❌ ISSUES FOUND:')
            for i, issue in enumerate(self.issues, 1):
                print(f'  {i}. {issue}')
            print()

        if self.warnings:
            print('⚠️  WARNINGS:')
            for i, warning in enumerate(self.warnings, 1):
                print(f'  {i}. {warning}')
            print()

        if not self.issues and not self.warnings:
            print('✅ DATABASE HEALTH: EXCELLENT')
            print('   All systems operational, data is fresh and complete.')
        elif self.issues:
            print('❌ DATABASE HEALTH: NEEDS ATTENTION')
            print('   Critical issues found - data is incomplete.')
        else:
            print('⚠️  DATABASE HEALTH: ACCEPTABLE')
            print('   Minor issues found - data may be slightly stale.')

        print()
        return len(self.issues) == 0

    def close(self):
        """Close database connection."""
        self.conn.close()


def main():
    """Run database health check."""
    checker = DatabaseHealthChecker()

    try:
        healthy = checker.analyze_health()
        checker.close()
        return 0 if healthy else 1
    except Exception as e:
        print(f'❌ Error during health check: {e}')
        checker.close()
        return 2


if __name__ == '__main__':
    sys.exit(main())
