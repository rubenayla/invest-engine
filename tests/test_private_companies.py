"""Private-company validation, evidence handling and persistence boundaries."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from invest.private_companies import (
    CompanyBundle,
    InvestmentOffer,
    Observation,
    PrivateCompany,
    repository,
    screen_company,
)


def company(**changes):
    return PrivateCompany(
        **(
            dict(
                jurisdiction="gb",
                registration_number="00123456",
                legal_name="Example Ltd",
                country="GB",
            )
            | changes
        )
    )


def observation(**changes):
    data = dict(
        metric="revenue",
        value=100,
        unit="money",
        currency="GBP",
        period_end="2025-12-31",
        source_url="https://example.org/accounts",
        retrieved_at=datetime(2026, 10, 8, tzinfo=timezone.utc),
        evidence_type="reported",
    )
    return Observation(**(data | changes))


def offer(**changes):
    data = dict(
        external_id="round-1",
        security_type="ordinary_shares",
        currency="GBP",
        source_url="https://example.org/offer",
    )
    return InvestmentOffer(**(data | changes))


@pytest.mark.parametrize(
    "changes",
    [
        {"value": float("nan")},
        {"value": float("inf")},
        {"value": " "},
        {"source_url": "file:///etc/passwd"},
        {"currency": "gbp"},
        {"retrieved_at": datetime(2026, 1, 1)},
        {"metric": "Revenue!"},
    ],
)
def test_observation_rejects_invalid_input(changes):
    with pytest.raises(ValidationError):
        observation(**changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"minimum_investment": 0},
        {"pre_money_valuation": -1},
        {"minimum_investment": float("inf")},
        {"pre_money_valuation": float("nan")},
        {"external_id": " "},
        {"status": "fundraising"},
    ],
)
def test_offer_rejects_invalid_input(changes):
    with pytest.raises(ValidationError):
        offer(**changes)


def test_defaults_keep_research_private_and_classification_explicit():
    record = company()
    assert record.registration_number == "00123456"
    assert record.jurisdiction == "GB"
    assert record.company_type == "unclassified"
    assert record.listing_status == "unconfirmed"
    assert not record.public_visibility
    assert not observation().public_visibility
    assert not offer().public_visibility
    assert (
        screen_company(CompanyBundle(company=record))["business_assessment"]
        == "classification_required"
    )


def test_type_specific_checklists_do_not_equate_coverage_with_quality():
    startup = screen_company(CompanyBundle(company=company(company_type="startup")))
    established = screen_company(CompanyBundle(company=company(company_type="established")))
    assert all(item["status"] == "unknown" for item in startup["criteria"])
    assert "cash_runway_months" in {item["metric"] for item in startup["criteria"]}
    assert "owner_dependence" in {item["metric"] for item in established["criteria"]}
    assert startup["business_assessment"] == "unassessed"
    assert startup["investment_availability"] == "unknown"
    assert "score" not in startup


def test_conflicting_same_period_assertions_remain_visible():
    bundle = CompanyBundle(
        company=company(company_type="startup"),
        observations=[
            observation(value=100),
            observation(value=200),
            observation(value=300, period_end="2024-12-31"),
        ],
    )
    screened = screen_company(bundle)
    revenue = next(item for item in screened["criteria"] if item["metric"] == "revenue")
    assert revenue["status"] == "conflicting"
    assert screened["evidence_summary"]["reported"] == 3
    assert screened["business_assessment"] == "unassessed"


def test_historical_changes_are_not_conflicts_and_estimates_not_verified():
    bundle = CompanyBundle(
        company=company(company_type="established"),
        observations=[
            observation(),
            observation(value=90, period_end="2024-12-31", evidence_type="estimated"),
        ],
    )
    screened = screen_company(bundle)
    assert screened["criteria"][0]["status"] == "documented"
    assert screened["evidence_summary"]["verified"] == 0
    assert screened["evidence_summary"]["estimated"] == 1


def test_fundraising_information_and_partial_offers_do_not_prove_access():
    bundle = CompanyBundle(company=company(), observations=[observation(metric="funding_raised")])
    assert screen_company(bundle)["investment_availability"] == "unknown"
    bundle.offers = [offer(status="available")]
    assert screen_company(bundle)["investment_availability"] == "unknown"
    bundle.offers = [
        offer(
            status="available",
            minimum_investment=1000,
            terms_summary="Ordinary shares; transfer restricted",
        )
    ]
    assert screen_company(bundle)["investment_availability"] == "available"
    bundle.offers = [offer(status="closed")]
    assert screen_company(bundle)["investment_availability"] == "closed"


def test_fact_hash_deduplicates_refetch_but_retains_revised_assertion():
    first = observation()
    later = observation(retrieved_at=datetime(2026, 10, 9, tzinfo=timezone.utc))
    assert repository._fact_hash(first) == repository._fact_hash(later)
    assert repository._fact_hash(first) == repository._fact_hash(
        observation(public_visibility=True)
    )
    assert repository._fact_hash(first) != repository._fact_hash(observation(value=101))


def database(monkeypatch):
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    monkeypatch.setattr(repository, "get_connection", lambda **kwargs: connection)
    return connection, cursor


def test_bundle_writes_are_one_transaction_and_close_connection(monkeypatch):
    connection, cursor = database(monkeypatch)
    cursor.fetchone.return_value = (42,)
    bundle = CompanyBundle(company=company(), observations=[observation()], offers=[offer()])
    assert repository.ingest_bundle(bundle) == 42
    assert cursor.execute.call_count == 3
    assert (
        "public_visibility=EXCLUDED.public_visibility" in cursor.execute.call_args_list[1].args[0]
    )
    assert (
        "ON CONFLICT (company_id,external_id) DO UPDATE" in cursor.execute.call_args_list[2].args[0]
    )
    for query in cursor.execute.call_args_list:
        assert query.args[0].count("%s") == len(query.args[1])
    connection.__exit__.assert_called_once_with(None, None, None)
    connection.close.assert_called_once()


def test_ingestion_failure_exits_transaction_with_error(monkeypatch):
    connection, cursor = database(monkeypatch)
    cursor.fetchone.return_value = (42,)
    cursor.execute.side_effect = [None, RuntimeError("write failed")]
    with pytest.raises(RuntimeError, match="write failed"):
        repository.ingest_bundle(CompanyBundle(company=company(), observations=[observation()]))
    assert connection.__exit__.call_args.args[0] is RuntimeError
    connection.close.assert_called_once()


def test_public_reads_filter_children_before_screening(monkeypatch):
    _, cursor = database(monkeypatch)
    row = {"id": 42, **company(public_visibility=True).model_dump(mode="json")}
    cursor.fetchall.side_effect = [[row], [], []]
    result = repository.list_companies()
    assert result[0]["observations"] == []
    assert result[0]["screening"]["investment_availability"] == "unknown"
    for call in cursor.execute.call_args_list:
        assert "public_visibility = TRUE" in call.args[0]
        assert True in call.args[1]
    assert "listing_status <> 'public'" in cursor.execute.call_args_list[0].args[0]


@pytest.mark.integration
def test_real_postgres_idempotence_rollback_and_public_boundaries(monkeypatch):
    """Run only against an explicitly provided disposable PostgreSQL database."""
    import os
    from uuid import uuid4

    from invest.data.db import get_connection, get_db_url

    test_url = os.environ.get("PRIVATE_COMPANIES_TEST_DB_URL")
    if not test_url:
        pytest.skip("Set PRIVATE_COMPANIES_TEST_DB_URL to a disposable PostgreSQL database")
    monkeypatch.setenv("DB_URL", test_url)
    get_db_url.cache_clear()
    repository.initialize_schema()
    number = "test-" + uuid4().hex
    failed_number = "rollback-" + uuid4().hex
    public_company = company(
        registration_number=number,
        company_type="startup",
        listing_status="confirmed_private",
        public_visibility=True,
    )
    bundle = CompanyBundle(
        company=public_company,
        observations=[
            observation(public_visibility=True),
            observation(value=200),
        ],
        offers=[
            offer(status="available", minimum_investment=100, terms_summary="Private offer terms")
        ],
    )
    try:
        first = repository.ingest_bundle(bundle)
        assert repository.ingest_bundle(bundle) == first
        private = next(
            row for row in repository.list_companies(public_only=False) if row["id"] == first
        )
        assert len(private["observations"]) == 2
        assert len(private["offers"]) == 1
        assert private["screening"]["criteria"][1]["status"] == "conflicting"
        assert private["screening"]["investment_availability"] == "available"
        public = next(row for row in repository.list_companies() if row["id"] == first)
        assert len(public["observations"]) == 1
        assert public["offers"] == []
        assert public["screening"]["criteria"][1]["status"] == "documented"
        assert public["screening"]["investment_availability"] == "unknown"
        updated = bundle.model_copy(
            update={
                "company": public_company.model_copy(
                    update={
                        "company_type": "unclassified",
                        "listing_status": "unconfirmed",
                    }
                )
            }
        )
        repository.ingest_bundle(updated)
        saved = next(row for row in repository.list_companies(False) if row["id"] == first)
        assert saved["company_type"] == "startup"
        assert saved["listing_status"] == "confirmed_private"
        repository.ingest_bundle(
            CompanyBundle(company=public_company, observations=[observation()])
        )
        revoked = next(row for row in repository.list_companies() if row["id"] == first)
        assert revoked["observations"] == []
        assert revoked["screening"]["evidence_summary"]["observation_count"] == 0
        invalid = CompanyBundle(
            company=company(registration_number=failed_number),
            offers=[offer().model_copy(update={"status": "invalid"})],
        )
        with pytest.raises(Exception, match="check constraint"):
            repository.ingest_bundle(invalid)
        with get_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM private_companies WHERE registration_number=%s",
                (failed_number,),
            )
            assert cursor.fetchone()[0] == 0
    finally:
        with get_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM private_companies WHERE registration_number = ANY(%s)",
                ([number, failed_number],),
            )
            ids = [row[0] for row in cursor.fetchall()]
            for table in (
                "private_company_observations",
                "private_company_offers",
                "private_companies",
            ):
                key = "id" if table == "private_companies" else "company_id"
                cursor.execute(f"DELETE FROM {table} WHERE {key} = ANY(%s)", (ids,))
        get_db_url.cache_clear()


def test_equivalent_numeric_assertions_are_not_conflicts():
    bundle = CompanyBundle(
        company=company(company_type="startup"),
        observations=[observation(value=100), observation(value=100.0)],
    )
    result = screen_company(bundle)
    assert (
        next(item for item in result["criteria"] if item["metric"] == "revenue")["status"]
        == "documented"
    )
