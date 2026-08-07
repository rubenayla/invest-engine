#!/usr/bin/env python3
"""
Test runner script for the investment analysis framework.

This script runs the complete test suite and provides detailed output
about test results, coverage, and performance.
"""

import subprocess
import sys
import time
from pathlib import Path


def run_command(cmd, description):
    """Run a command and return success status."""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print('='*60)

    start_time = time.time()
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        duration = time.time() - start_time

        print(f"✅ SUCCESS ({duration:.2f}s): {description}")
        if result.stdout.strip():
            print("Output:")
            print(result.stdout)
        return True

    except subprocess.CalledProcessError as e:
        duration = time.time() - start_time
        print(f"❌ FAILED ({duration:.2f}s): {description}")
        print(f"Exit code: {e.returncode}")
        if e.stdout.strip():
            print("STDOUT:")
            print(e.stdout)
        if e.stderr.strip():
            print("STDERR:")
            print(e.stderr)
        return False


def main():
    """Run the complete test suite."""
    print("🧪 Investment Analysis Framework - Test Suite")
    print("=" * 60)

    # Change to project root directory
    project_root = Path(__file__).parent.parent
    original_dir = Path.cwd()

    try:
        os.chdir(project_root)

        total_tests = 0
        passed_tests = 0

        # Test categories to run
        test_categories = [
            {
                'name': 'Linting with Ruff',
                'cmd': ['uv', 'run', 'ruff', 'check', 'src', 'tests'],
                'required': True
            },
            {
                'name': 'Code Formatting Check',
                'cmd': ['uv', 'run', 'ruff', 'format', '--check', 'src', 'tests'],
                'required': True
            },
            {
                'name': 'Data Provider Tests',
                'cmd': ['uv', 'run', 'pytest', 'tests/test_data_providers.py', '-v'],
                'required': True
            },
            {
                'name': 'Valuation Model Tests',
                'cmd': ['uv', 'run', 'pytest', 'tests/test_valuation.py', '-v'],
                'required': True
            },
            {
                'name': 'International Market Tests',
                'cmd': ['uv', 'run', 'pytest', 'tests/test_international_markets.py', '-v'],
                'required': True
            },
            {
                'name': 'Systematic Analysis Tests',
                'cmd': ['uv', 'run', 'pytest', 'tests/test_systematic_analysis.py', '-v'],
                'required': True
            },
            {
                'name': 'End-to-End Workflow Tests',
                'cmd': ['uv', 'run', 'pytest', 'tests/test_end_to_end.py', '-v'],
                'required': True
            },
            {
                'name': 'Complete Test Suite with Coverage',
                'cmd': ['uv', 'run', 'pytest', '--cov=src/invest', '--cov-report=term-missing', '--cov-report=html', '-v'],
                'required': False
            },
            {
                'name': 'Configuration Validation',
                'cmd': ['uv', 'run', 'python', '-c', 'import yaml; [yaml.safe_load(open(f)) for f in Path("configs").glob("*.yaml")]'],
                'required': True
            },
            {
                'name': 'Documentation Build Test',
                'cmd': ['uv', 'run', 'mkdocs', 'build', '--strict'],
                'required': False
            }
        ]

        # Run all test categories
        for test_category in test_categories:
            total_tests += 1

            success = run_command(test_category['cmd'], test_category['name'])

            if success:
                passed_tests += 1
            elif test_category['required']:
                print(f"\n❌ Required test failed: {test_category['name']}")
                print("Stopping test execution due to critical failure.")
                break

        # Print summary
        print(f"\n{'='*60}")
        print("🏁 TEST SUMMARY")
        print('='*60)
        print(f"Total test categories: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {total_tests - passed_tests}")
        print(f"Success rate: {(passed_tests/total_tests)*100:.1f}%")

        if passed_tests == total_tests:
            print("\n🎉 ALL TESTS PASSED! 🎉")
            print("The investment analysis framework is working correctly.")
            return 0
        else:
            print(f"\n❌ {total_tests - passed_tests} TEST(S) FAILED")
            print("Please fix the failing tests before proceeding.")
            return 1

    except KeyboardInterrupt:
        print("\n\n⚠️  Test execution interrupted by user")
        return 1

    except Exception as e:
        print(f"\n\n💥 Unexpected error during test execution: {e}")
        return 1

    finally:
        os.chdir(original_dir)


if __name__ == "__main__":
    import os
    sys.exit(main())
