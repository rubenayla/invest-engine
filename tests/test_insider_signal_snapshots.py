"""Regression tests for persisted daily insider signal snapshots."""

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))

import dashboard_server

from invest.dashboard_components.html_generator import HTMLGenerator
from invest.scanner.scoring_engine import ScoringEngine
from invest.scanner.threshold_manager import ThresholdManager


class _RecordingCursor:
    def __init__(self):
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((query, params))


class _RecordingConnection:
    def __init__(self):
        self.cursor_instance = _RecordingCursor()
        self.committed = False
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


def test_insider_score_is_available_for_the_daily_snapshot():
    engine = ScoringEngine()

    _, details = engine.score_catalyst({
        'insider': {
            'has_data': True,
            'net_buy_pct': 25.0,
            'cluster_score': 2,
            'recency_days': 10,
            'dollar_conviction': 1_500_000,
            'buy_count': 3,
            'sell_count': 1,
            'sell_trend': 0.5,
        },
    })

    assert details['insider']['score'] > 0


def test_record_scores_upserts_all_insider_snapshot_fields(monkeypatch):
    connection = _RecordingConnection()
    monkeypatch.setattr('invest.scanner.threshold_manager.get_connection', lambda: connection)
    manager = object.__new__(ThresholdManager)

    manager.record_scores('2026-08-18', [
        ('ACME', 80.0, 70.0, 75.0, 65.0, 60.0, 85.0, {
            'score': 77.5,
            'buy_count': 4,
            'sell_count': 1,
            'net_buy_pct': 30.5,
            'sell_trend': 0.6,
            'buy_trend': 1.4,
            'cluster_score': 3,
            'dollar_conviction': 2_500_000.0,
        }),
    ])

    query, params = connection.cursor_instance.calls[0]
    assert 'insider_dollar_conviction' in query
    assert 'insider_score = EXCLUDED.insider_score' in query
    assert params == (
        '2026-08-18', 'ACME', 80.0, 70.0, 75.0, 65.0, 60.0, 85.0,
        77.5, 4, 1, 30.5, 0.6, 1.4, 3, 2_500_000.0,
    )
    assert connection.committed and connection.closed


class _HistoryCursor:
    def __init__(self):
        self.query_count = 0

    def execute(self, query, params=None):
        self.query_count += 1

    def fetchall(self):
        return [
            [('2026-08', 'P', 2, 8000.0)],
            [],
            [('2026-08-18', 72.5, 2, 1, 33.3, 0.5, 1.2, 2, 8000.0)],
        ][self.query_count - 1]


class _HistoryConnection:
    def __init__(self):
        self.cursor_instance = _HistoryCursor()
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def rollback(self):
        pass

    def close(self):
        self.closed = True


def test_insider_history_api_returns_transaction_and_signal_history(monkeypatch):
    connection = _HistoryConnection()
    monkeypatch.setattr(dashboard_server, 'get_connection', lambda: connection)
    request = SimpleNamespace(path_params={'ticker': 'acme'})

    response = asyncio.run(dashboard_server.api_insider_history(request))
    body = json.loads(response.body)

    assert body['ticker'] == 'ACME'
    assert body['months'][0]['buys'] == 2
    assert body['snapshots'] == [{
        'date': '2026-08-18', 'insider_score': 72.5, 'buy_count': 2,
        'sell_count': 1, 'net_buy_pct': 33.3, 'sell_trend': 0.5,
        'buy_trend': 1.2, 'cluster_score': 2, 'dollar_conviction': 8000.0,
    }]
    assert connection.closed


def test_dashboard_renders_signal_history_and_gross_transaction_labels(tmp_path):
    dashboard = HTMLGenerator(output_dir=tmp_path)
    output = dashboard.generate_dashboard_html({}, {}, {'server_mode': True})

    assert 'renderInsiderSignalHistory' in output
    assert 'Insider score' in output
    assert 'Dollar conviction' in output
    assert '>Gross buys</text>' in output
    assert '>Gross sells</text>' in output
