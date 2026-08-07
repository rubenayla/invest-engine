#!/usr/bin/env python3
"""
Validate database data quality for neural network training.

Run this manually to check:
- Feature coverage (what % of snapshots have each feature)
- Data completeness by year
- Missing critical fields

Not included in CI/CD since it requires the database.
"""

import sqlite3
import sys
from pathlib import Path


class DataQualityValidator:
    """Validate neural network training data quality."""

    def __init__(self, db_path: str = '../../data/stock_data.db'):
        self.db_path = Path(__file__).parent / db_path
        self.issues = []
        self.warnings = []

    def validate_all(self) -> bool:
        """Run all validation checks. Returns True if data passes quality checks."""
        print('='*80)
        print('DATA QUALITY VALIDATION')
        print('='*80)
        print(f'Database: {self.db_path}\n')

        self._check_database_exists()
        self._check_feature_coverage()
        self._check_coverage_by_year()
        self._check_forward_returns()
        self._check_price_history()

        # Print summary
        print('\n' + '='*80)
        print('VALIDATION SUMMARY')
        print('='*80)

        if self.warnings:
            print(f'\n⚠️  WARNINGS ({len(self.warnings)}):')
            for warning in self.warnings:
                print(f'  - {warning}')

        if self.issues:
            print(f'\n❌ CRITICAL ISSUES ({len(self.issues)}):')
            for issue in self.issues:
                print(f'  - {issue}')
            print('\n🚨 Data quality validation FAILED\n')
            return False
        else:
            print('\n✅ All critical checks passed!')
            if self.warnings:
                print('   (Some warnings - see above)\n')
            else:
                print('   No issues found.\n')
            return True

    def _check_database_exists(self):
        """Check if database file exists."""
        if not self.db_path.exists():
            self.issues.append(f'Database not found at {self.db_path}')
            print('❌ Database file not found\n')
            sys.exit(1)

        size_mb = self.db_path.stat().st_size / (1024 * 1024)
        print(f'✓ Database found ({size_mb:.1f} MB)\n')

    def _check_feature_coverage(self):
        """Check what percentage of snapshots have each critical feature."""
        print('FEATURE COVERAGE')
        print('-'*80)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Critical features for training
        features = {
            'pe_ratio': 'PE Ratio',
            'pb_ratio': 'P/B Ratio',
            'market_cap': 'Market Cap',
            'profit_margins': 'Profit Margins',
            'operating_margins': 'Operating Margins',
            'return_on_equity': 'Return on Equity',
            'revenue_growth': 'Revenue Growth',
            'earnings_growth': 'Earnings Growth',
            'debt_to_equity': 'Debt to Equity',
            'current_ratio': 'Current Ratio',
            'free_cashflow': 'Free Cash Flow',
            'beta': 'Beta'
        }

        cursor.execute('SELECT COUNT(*) FROM snapshots')
        total_snapshots = cursor.fetchone()[0]

        print(f'Total snapshots: {total_snapshots:,}\n')

        for field, name in features.items():
            cursor.execute(f'''
                SELECT COUNT(*)
                FROM snapshots
                WHERE {field} IS NOT NULL
            ''')
            count = cursor.fetchone()[0]
            coverage = (count / total_snapshots * 100) if total_snapshots > 0 else 0

            status = '✓' if coverage > 80 else '⚠️' if coverage > 50 else '❌'
            print(f'{status} {name:25s}: {coverage:5.1f}% ({count:,}/{total_snapshots:,})')

            if coverage < 50:
                self.issues.append(f'{name} coverage too low: {coverage:.1f}%')
            elif coverage < 80:
                self.warnings.append(f'{name} coverage below 80%: {coverage:.1f}%')

        conn.close()
        print()

    def _check_coverage_by_year(self):
        """Check feature coverage by year to detect issues in specific time periods."""
        print('COVERAGE BY YEAR')
        print('-'*80)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT
                strftime('%Y', snapshot_date) as year,
                COUNT(*) as total,
                SUM(CASE WHEN market_cap IS NOT NULL THEN 1 ELSE 0 END) as has_mcap,
                SUM(CASE WHEN profit_margins IS NOT NULL THEN 1 ELSE 0 END) as has_margins,
                SUM(CASE WHEN free_cashflow IS NOT NULL THEN 1 ELSE 0 END) as has_fcf
            FROM snapshots
            GROUP BY year
            ORDER BY year DESC
            LIMIT 5
        ''')

        rows = cursor.fetchall()
        print('Recent years (showing critical fields):')
        print(f'{"Year":<6} {"Snapshots":<10} {"Market Cap":<12} {"Margins":<12} {"FCF":<12}')
        print('-'*60)

        for year, total, has_mcap, has_margins, has_fcf in rows:
            mcap_pct = (has_mcap / total * 100) if total > 0 else 0
            margins_pct = (has_margins / total * 100) if total > 0 else 0
            fcf_pct = (has_fcf / total * 100) if total > 0 else 0

            print(f'{year:<6} {total:<10,} {mcap_pct:>5.1f}%       {margins_pct:>5.1f}%       {fcf_pct:>5.1f}%')

            if year >= '2020' and mcap_pct < 80:
                self.issues.append(f'{year}: Market cap coverage only {mcap_pct:.1f}%')

        conn.close()
        print()

    def _check_forward_returns(self):
        """Check that forward returns are properly calculated."""
        print('FORWARD RETURNS')
        print('-'*80)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Check each horizon
        horizons = ['1m', '3m', '6m', '1y', '2y']

        for horizon in horizons:
            cursor.execute('''
                SELECT COUNT(*), AVG(return_pct), MIN(return_pct), MAX(return_pct)
                FROM forward_returns
                WHERE horizon = ?
            ''', (horizon,))

            count, avg, min_ret, max_ret = cursor.fetchone()

            if count == 0:
                self.issues.append(f'No forward returns for horizon: {horizon}')
                print(f'❌ {horizon}: No data')
            else:
                avg = avg or 0
                min_ret = min_ret or 0
                max_ret = max_ret or 0
                print(f'✓ {horizon}: {count:,} samples, avg={avg*100:+.1f}%, range=[{min_ret*100:.1f}%, {max_ret*100:.1f}%]')

        conn.close()
        print()

    def _check_price_history(self):
        """Check that price history exists for snapshots."""
        print('PRICE HISTORY')
        print('-'*80)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('SELECT COUNT(*) FROM snapshots')
        total_snapshots = cursor.fetchone()[0]

        cursor.execute('''
            SELECT COUNT(DISTINCT snapshot_id)
            FROM price_history
        ''')
        snapshots_with_history = cursor.fetchone()[0]

        coverage = (snapshots_with_history / total_snapshots * 100) if total_snapshots > 0 else 0

        if coverage < 95:
            self.issues.append(f'Price history coverage too low: {coverage:.1f}%')
            print(f'❌ Coverage: {coverage:.1f}% ({snapshots_with_history:,}/{total_snapshots:,})')
        else:
            print(f'✓ Coverage: {coverage:.1f}% ({snapshots_with_history:,}/{total_snapshots:,})')

        cursor.execute('SELECT COUNT(*) FROM price_history')
        total_records = cursor.fetchone()[0]
        print(f'✓ Total price records: {total_records:,}')

        conn.close()
        print()


def main():
    validator = DataQualityValidator()
    passed = validator.validate_all()
    sys.exit(0 if passed else 1)


if __name__ == '__main__':
    main()
