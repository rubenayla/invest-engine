"""The dashboard and its analysis pages are public.

Personal source notes remain in the vault; this server does not add a second
account or password layer around the rendered analysis pages.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))

from starlette.testclient import TestClient  # noqa: E402

import dashboard_server  # noqa: E402


@pytest.fixture(scope='module')
def client():
    return TestClient(dashboard_server.app, base_url='https://testserver',
                      raise_server_exceptions=False)


class TestPublicDashboard:
    @pytest.mark.parametrize('path', [
        '/', '/m', '/feed', '/api/stocks', '/api/health',
        '/api/notes/CRON', '/api/alarms', '/api/reminders',
        '/api/notes/catalog',
    ])
    def test_reads_have_no_auth_boundary(self, client, path):
        assert client.get(path).status_code != 401

    def test_login_route_is_removed(self, client):
        assert client.post('/api/login', json={'password': 'anything'}).status_code == 404

    def test_notes_follow_browser_color_scheme(self, client, monkeypatch, tmp_path):
        (tmp_path / 'CRON.md').write_text(
            '# Cronos Group\n\n| Metric | Value |\n| --- | --- |\n| Revenue | $146.6M |\n',
            encoding='utf-8',
        )
        monkeypatch.setattr(dashboard_server, 'NOTES_DIR', tmp_path)

        response = client.get('/api/notes/CRON')

        assert response.status_code == 200
        assert "color-scheme: light dark" in response.text
        assert "@media (prefers-color-scheme: dark)" in response.text
        assert "--background:#fff" in response.text
        assert "--background:#0d1117" in response.text
        assert '<table>' in response.text
        assert '<td>Revenue</td>' in response.text
        assert "href='/'" in response.text
        assert 'Dashboard' in response.text


class TestNotesEndpoints:
    def test_notes_catalog_empty_or_default(self, client):
        response = client.get('/api/notes/catalog')
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_notes_catalog_enriched_and_sorted(self, client, monkeypatch, tmp_path):
        notes_dir = tmp_path / "notes"
        notes_dir.mkdir()
        (notes_dir / "BUY_BELOW.md").write_text("# Buy Below\nGreat company", encoding="utf-8")
        watch_dir = notes_dir / "WATCH_STOCK"
        watch_dir.mkdir()
        (watch_dir / "thesis.md").write_text("# Watch Thesis", encoding="utf-8")
        (watch_dir / "visual-report.html").write_text("<h1>Visual</h1>", encoding="utf-8")

        monkeypatch.setattr(dashboard_server, 'NOTES_DIR', notes_dir)

        mock_stocks = {
            "BUY_ABOVE": {
                "company_name": "Buy Above Entry",
                "current_price": 110.0,
                "valuations": {
                    "llm_deep_analysis": {
                        "fair_value": 150.0,
                        "upside": 36.0,
                        "details": {
                            "verdict": "BUY",
                            "expected_value_pct": 36.0,
                            "entry_price": 100.0,
                            "conviction": "HIGH",
                            "scenarios": {"bear": {"return_pct": -20.0}},
                        },
                    },
                },
            },
            "BUY_BELOW": {
                "company_name": "Buy Below Entry",
                "current_price": 95.0,
                "valuations": {
                    "llm_deep_analysis": {
                        "fair_value": 140.0,
                        "upside": 47.0,
                        "details": {
                            "verdict": "BUY",
                            "expected_value_pct": 47.0,
                            "entry_price": 100.0,
                            "conviction": "MEDIUM-HIGH",
                            "scenarios": {"bear": {"return_pct": -15.0}},
                        },
                    },
                },
            },
            "WATCH_STOCK": {
                "company_name": "Watch Stock",
                "current_price": 50.0,
                "valuations": {
                    "llm_deep_analysis": {
                        "fair_value": 55.0,
                        "details": {
                            "verdict": "WATCH",
                            "expected_value_pct": 10.0,
                            "entry_price": 45.0,
                            "conviction": "LOW",
                            "scenarios": {"bear": {"return_pct": -10.0}},
                        },
                    },
                },
            },
            "PASS_STOCK": {
                "company_name": "Pass Stock",
                "current_price": 40.0,
                "valuations": {
                    "llm_deep_analysis": {
                        "fair_value": 30.0,
                        "details": {
                            "verdict": "PASS",
                            "expected_value_pct": -25.0,
                            "entry_price": 20.0,
                            "conviction": "LOW",
                            "scenarios": {"bear": {"return_pct": -30.0}},
                        },
                    },
                },
            },
            "NO_LLM_HIGH_MARGIN": {
                "company_name": "No LLM High Margin",
                "current_price": 10.0,
                "valuations": {
                    "dcf": {"margin_of_safety": 0.50, "fair_value": 20.0},
                },
            },
            "NO_LLM_LOW_MARGIN": {
                "company_name": "No LLM Low Margin",
                "current_price": 10.0,
                "valuations": {
                    "dcf": {"margin_of_safety": 0.10, "fair_value": 11.0},
                },
            },
        }

        monkeypatch.setattr(dashboard_server.snapshot_cache, "_stocks_data", mock_stocks)
        dashboard_server.snapshot_cache.invalidate_notes_catalog()

        response = client.get('/api/notes/catalog')
        assert response.status_code == 200
        catalog = response.json()
        assert isinstance(catalog, list)
        assert len(catalog) == 6

        tickers = [item['ticker'] for item in catalog]
        assert tickers == ["BUY_BELOW", "BUY_ABOVE", "WATCH_STOCK", "PASS_STOCK", "NO_LLM_HIGH_MARGIN", "NO_LLM_LOW_MARGIN"]

        # BUY_BELOW checks
        buy_below = catalog[0]
        assert buy_below["ticker"] == "BUY_BELOW"
        assert buy_below["has_note"] is True
        assert buy_below["note_available"] is True
        assert buy_below["has_visual"] is False
        assert buy_below["entry_actionable"] is True
        assert buy_below["risk_adjusted_score"] > 150
        assert buy_below["verdict"] == "BUY"

        # WATCH_STOCK checks
        watch_stock = catalog[2]
        assert watch_stock["ticker"] == "WATCH_STOCK"
        assert watch_stock["has_note"] is True
        assert watch_stock["has_visual"] is True
        assert watch_stock["verdict"] == "WATCH"

        # BUY_ABOVE checks
        buy_above = catalog[1]
        assert buy_above["has_note"] is False
        assert buy_above["entry_actionable"] is False

    def test_notes_catalog_cache_invalidation(self, client, monkeypatch):
        mock_stocks = {"STOCK_A": {"current_price": 10.0, "valuations": {}}}
        monkeypatch.setattr(dashboard_server.snapshot_cache, "_stocks_data", mock_stocks)
        dashboard_server.snapshot_cache.invalidate_notes_catalog()

        res1 = client.get('/api/notes/catalog').json()
        assert len(res1) == 1
        assert res1[0]["ticker"] == "STOCK_A"

        mock_stocks_2 = {
            "STOCK_A": {"current_price": 10.0, "valuations": {}},
            "STOCK_B": {"current_price": 20.0, "valuations": {}},
        }
        monkeypatch.setattr(dashboard_server.snapshot_cache, "_stocks_data", mock_stocks_2)
        dashboard_server.snapshot_cache.invalidate_notes_catalog()
        res2 = client.get('/api/notes/catalog').json()
        assert len(res2) == 2

    def test_ticker_data_endpoint(self, client, monkeypatch, tmp_path):
        stock_cache_dir = tmp_path / "stock_cache"
        stock_cache_dir.mkdir()
        monkeypatch.setattr(dashboard_server, 'STOCK_CACHE_DIR', stock_cache_dir)

        # 1. Invalid ticker
        assert client.get('/api/notes/INVALID!TICKER/data').status_code == 400
        assert client.get('/api/notes/../../bad/data').status_code in (400, 404)

        # 2. Not found
        res_404 = client.get('/api/notes/NONEXISTENT/data')
        assert res_404.status_code == 404
        assert "ticker" in res_404.json()

        # 3. Valid cached stock with NaNs (like pandas outputs)
        stock_payload = {
            "ticker": "AAPL",
            "info": {"sector": "Technology", "industry": "Consumer Electronics"},
            "financials": {"revenue": 383000000000, "nan_val": float("nan"), "inf_val": float("inf")},
            "price_data": {"close": 180.0},
            "financial_statements_currency": "USD",
            "income": [{"index": "Revenue", "2025": 100.0, "2024": float("nan")}],
            "balance_sheet": {"total_assets": 352000000000},
            "cashflow": {"free_cash_flow": 100000000000},
            "extra_irrelevant_key": "ignored",
        }
        # In json string, write raw NaN or use Python dumps with allow_nan
        (stock_cache_dir / "AAPL.json").write_text(json.dumps(stock_payload, allow_nan=True), encoding="utf-8")

        res_200 = client.get('/api/notes/AAPL/data')
        assert res_200.status_code == 200
        data = res_200.json()
        assert data["financials"]["nan_val"] is None
        assert data["financials"]["inf_val"] is None
        assert data["income"][0]["2024"] is None
        data = res_200.json()
        expected_keys = [
            "ticker", "info", "financials", "price_data",
            "financial_statements_currency", "income", "balance_sheet", "cashflow"
        ]
        for key in expected_keys:
            assert key in data
        assert data["ticker"] == "AAPL"
        assert data["info"]["sector"] == "Technology"
        assert data["financial_statements_currency"] == "USD"

        # 4. Empty cache file returns 404
        (stock_cache_dir / "EMPTY.json").write_text("{}", encoding="utf-8")
        assert client.get('/api/notes/EMPTY/data').status_code == 404
