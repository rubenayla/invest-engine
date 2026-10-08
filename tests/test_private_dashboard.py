"""Public directory filtering, privacy and rendering regression tests."""

import sys
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from invest.private_companies.dashboard import public_company, render_directory, safe_url

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import dashboard_server


def record(**overrides):
    return {
        "id": 1,
        "legal_name": "<script>alert(1)</script>",
        "company_type": "startup",
        "country": "ES",
        "public_visibility": True,
        "website": "javascript:alert(1)",
        "dossier_path": "/private/notes.md",
        "observations": [{"value": "private financials"}],
        **overrides,
    }


@pytest.mark.parametrize("visibility", [False, None, "true", 1])
def test_public_records_require_explicit_boolean_opt_in(visibility):
    assert public_company(record(public_visibility=visibility)) is None


def test_public_projection_excludes_dossiers_and_private_observations():
    result = public_company(record())
    assert "dossier_path" not in result
    assert "observations" not in result
    assert result["website"] == ""


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "data:text/html,hi",
        "//example.com",
        "https://user:pass@example.com",
        "http://[invalid",
    ],
)
def test_unsafe_website_links_are_rejected(url):
    assert safe_url(url) == ""


def test_page_escapes_imported_text_and_query():
    html = render_directory([public_company(record())], query="")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "javascript:" not in html
    assert "/private/notes.md" not in html
    assert "&quot;" in render_directory([], query='" autofocus')


def test_type_and_search_filters_keep_both_opportunity_types():
    companies = [
        public_company(record(legal_name="Startup ES")),
        public_company(
            record(id=2, legal_name="Established UK", company_type="established", country="UK")
        ),
    ]
    html = render_directory(companies, company_type="established", query="uk")
    assert "Established UK" in html
    assert "Startup ES" not in html
    assert "Startups" in html and "Established businesses" in html
    assert "No companies match" in render_directory(companies, query="missing")


def test_empty_page_and_error_states_are_honest():
    assert "explicitly approved" in render_directory([])
    assert "not initialized" in render_directory([], state="not_initialized")
    assert "unavailable" in render_directory([], state="unavailable")


def test_routes_share_safe_projection(monkeypatch):
    monkeypatch.setattr(
        dashboard_server, "_load_private_companies", lambda: ([public_company(record())], "ready")
    )
    with TestClient(dashboard_server.app) as client:
        response = client.get("/api/private-companies")
        assert response.status_code == 200
        assert response.json()["companies"][0]["legal_name"] == "<script>alert(1)</script>"
        assert "dossier" not in response.text and "private financials" not in response.text
        assert client.get("/private-companies").status_code == 200
        assert client.post("/api/private-companies").status_code == 405


@pytest.mark.parametrize("state", ["not_initialized", "unavailable"])
def test_routes_show_actionable_database_failures(monkeypatch, state):
    monkeypatch.setattr(dashboard_server, "_load_private_companies", lambda: ([], state))
    with TestClient(dashboard_server.app) as client:
        response = client.get("/api/private-companies")
        assert response.json()["status"] == state
        assert response.status_code == (503 if state == "unavailable" else 200)
        page = client.get("/private-companies")
        assert page.status_code == response.status_code
        assert ("not initialized" if state == "not_initialized" else "unavailable") in page.text


def test_loader_filters_private_and_public_listed_records(monkeypatch):
    from invest.private_companies import repository

    calls = []

    def load(*, public_only):
        calls.append(public_only)
        return [
            record(),
            record(legal_name="Secret", public_visibility=False),
            record(legal_name="Listed", listing_status="public"),
        ]

    monkeypatch.setattr(repository, "list_companies", load)
    records, state = dashboard_server._load_private_companies()
    assert state == "ready"
    assert calls == [True]
    assert len(records) == 1


@pytest.mark.parametrize("missing", [False, True])
def test_loader_sanitizes_database_errors(monkeypatch, missing):
    from psycopg2.errors import UndefinedTable

    from invest.private_companies import repository

    def fail(**kwargs):
        error = UndefinedTable if missing else RuntimeError
        raise error("postgresql://secret:password@private-host/private-notes")

    monkeypatch.setattr(repository, "list_companies", fail)
    records, state = dashboard_server._load_private_companies()
    assert records == []
    assert state == ("not_initialized" if missing else "unavailable")


def test_projection_uses_backend_screening_contract():
    company = public_company(
        record(
            screening={
                "criteria": [
                    {
                        "metric": "revenue",
                        "label": "Revenue history",
                        "status": "documented",
                        "assessment": "Private conclusion",
                    }
                ],
                "evidence_summary": {"confidence": "unassessed"},
                "investment_availability": "available",
            }
        )
    )
    assert company["screening"]["investment_status"] == "available"
    assert company["screening"]["checks"] == [
        {"criterion": "Revenue history", "status": "documented"}
    ]
    assert "Private conclusion" not in str(company)
    html = render_directory([company])
    assert "Revenue history: documented" in html
    assert "Private listing status unconfirmed" in html
