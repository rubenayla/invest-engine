"""
Tests for the update pipeline.

Covers two outages:
1. Bare 'uv' in subprocess calls breaks in cron's minimal PATH (2.5 weeks of silent failure)
2. NaN/Infinity in financial JSON rejected by Postgres (data fetched but not stored)
"""

import json
import math
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = REPO_ROOT / 'scripts'
sys.path.insert(0, str(SCRIPTS_DIR))

ORCHESTRATOR_SCRIPTS = [
    'update_all.py',
    'run_all_predictions.py',
]


class TestNoHardcodedUv:
    """Scripts must use sys.executable, not bare 'uv', to spawn Python subprocesses."""

    @pytest.mark.parametrize('script_name', ORCHESTRATOR_SCRIPTS)
    def test_no_bare_uv_in_subprocess_calls(self, script_name):
        script_path = SCRIPTS_DIR / script_name
        assert script_path.exists(), f'{script_name} not found'

        violations = []
        for i, line in enumerate(script_path.read_text().splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            if re.search(r"""['"]uv['"],\s*['"]run['"],\s*['"]python['"]""", stripped):
                violations.append((i, stripped))

        if violations:
            details = '\n'.join(f'  line {n}: {text}' for n, text in violations)
            pytest.fail(
                f"{script_name} uses ['uv', 'run', 'python', ...] in subprocess calls. "
                f"This breaks in cron/SSH where uv isn't on PATH.\n"
                f"Use sys.executable instead:\n{details}"
            )


class TestCleanJson:
    """json.dumps produces NaN/Infinity tokens that Postgres rejects as invalid JSON."""

    @pytest.fixture
    def clean_json(self):
        from data_fetcher import _clean_json
        return _clean_json

    def test_nan_replaced_with_null(self, clean_json):
        data = [{'revenue': 1000, 'earnings': float('nan')}]
        result = json.loads(clean_json(data))
        assert result[0]['earnings'] is None

    def test_infinity_replaced_with_null(self, clean_json):
        data = [{'ratio': float('inf')}]
        result = json.loads(clean_json(data))
        assert result[0]['ratio'] is None

    def test_negative_infinity_replaced_with_null(self, clean_json):
        data = [{'ratio': float('-inf')}]
        result = json.loads(clean_json(data))
        assert result[0]['ratio'] is None

    def test_normal_values_preserved(self, clean_json):
        data = [{'revenue': 1000.5, 'name': 'AAPL', 'count': 0}]
        result = json.loads(clean_json(data))
        assert result == data

    def test_nested_nan(self, clean_json):
        data = [{'a': {'b': float('nan')}}]
        result = json.loads(clean_json(data))
        assert result[0]['a']['b'] is None

    def test_output_is_valid_json(self, clean_json):
        """The whole point — Postgres must accept this as valid JSON."""
        data = [{'x': float('nan'), 'y': float('inf'), 'z': 42}]
        result = clean_json(data)
        # json.loads would raise ValueError if invalid
        parsed = json.loads(result)
        assert parsed[0]['z'] == 42

    def test_empty_list(self, clean_json):
        assert clean_json([]) == '[]'
