"""Transactional PostgreSQL persistence for private-company research."""

from __future__ import annotations

import hashlib
import json
from contextlib import closing
from pathlib import Path

from psycopg2.extras import Json

from invest.data.db import get_connection

from .models import CompanyBundle, InvestmentOffer, Observation, PrivateCompany
from .screening import screen_company


def initialize_schema() -> None:
    schema = Path(__file__).resolve().parents[3] / "scripts/create_private_companies_schema.sql"
    with closing(get_connection()) as connection, connection:
        with connection.cursor() as cursor:
            cursor.execute(schema.read_text())


def _fact_hash(observation: Observation) -> str:
    # Re-fetching the same fact must not create another historical assertion.
    fact = observation.model_dump(mode="json", exclude={"retrieved_at", "public_visibility"})
    return hashlib.sha256(json.dumps(fact, sort_keys=True).encode()).hexdigest()


def ingest_bundle(bundle: CompanyBundle) -> int:
    """Upsert identity/offers and append distinct facts in one atomic transaction.

    Unclassified/unconfirmed imports preserve existing classification. Missing
    website/sector values preserve existing metadata. Incoming visibility is
    authoritative, including revocation; fact values and first retrieval times
    remain immutable when the same assertion is imported again.
    """
    if not isinstance(bundle, CompanyBundle):
        bundle = CompanyBundle.model_validate(bundle)
    company = bundle.company.model_dump(mode="json")
    with closing(get_connection()) as connection, connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO private_companies
                   (jurisdiction, registration_number, legal_name, company_type, listing_status, country,
                    website, sector, public_visibility)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (jurisdiction, registration_number) DO UPDATE SET
                     legal_name=EXCLUDED.legal_name,
                     company_type=CASE WHEN EXCLUDED.company_type = 'unclassified'
                       THEN private_companies.company_type ELSE EXCLUDED.company_type END,
                     listing_status=CASE WHEN EXCLUDED.listing_status = 'unconfirmed'
                       THEN private_companies.listing_status ELSE EXCLUDED.listing_status END,
                     country=EXCLUDED.country, website=COALESCE(EXCLUDED.website, private_companies.website),
                     sector=COALESCE(EXCLUDED.sector, private_companies.sector),
                     public_visibility=EXCLUDED.public_visibility, updated_at=CURRENT_TIMESTAMP
                   RETURNING id""",
                tuple(
                    company[key]
                    for key in (
                        "jurisdiction",
                        "registration_number",
                        "legal_name",
                        "company_type",
                        "listing_status",
                        "country",
                        "website",
                        "sector",
                        "public_visibility",
                    )
                ),
            )
            company_id = cursor.fetchone()[0]
            for item in bundle.observations:
                cursor.execute(
                    """INSERT INTO private_company_observations
                       (company_id,fact_hash,metric,value,unit,currency,period_end,public_visibility,
                        source_url,retrieved_at,evidence_type)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (company_id,fact_hash) DO UPDATE SET
                         public_visibility=EXCLUDED.public_visibility""",
                    (
                        company_id,
                        _fact_hash(item),
                        item.metric,
                        Json(item.value),
                        item.unit,
                        item.currency,
                        item.period_end,
                        item.public_visibility,
                        str(item.source_url),
                        item.retrieved_at,
                        item.evidence_type,
                    ),
                )
            for item in bundle.offers:
                cursor.execute(
                    """INSERT INTO private_company_offers
                       (company_id,external_id,status,security_type,currency,pre_money_valuation,public_visibility,
                        minimum_investment,terms_summary,source_url)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (company_id,external_id) DO UPDATE SET
                         status=EXCLUDED.status, public_visibility=EXCLUDED.public_visibility, security_type=EXCLUDED.security_type,
                         currency=EXCLUDED.currency, pre_money_valuation=EXCLUDED.pre_money_valuation,
                         minimum_investment=EXCLUDED.minimum_investment,
                         terms_summary=EXCLUDED.terms_summary, source_url=EXCLUDED.source_url,
                         updated_at=CURRENT_TIMESTAMP""",
                    (
                        company_id,
                        item.external_id,
                        item.status,
                        item.security_type,
                        item.currency,
                        item.pre_money_valuation,
                        item.public_visibility,
                        item.minimum_investment,
                        item.terms_summary,
                        str(item.source_url),
                    ),
                )
    return company_id


def list_companies(public_only: bool = True) -> list[dict]:
    """Return JSON-ready dossiers; public exports omit all private company records."""
    with closing(get_connection(dict_cursor=True)) as connection, connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM private_companies WHERE (%s = FALSE OR public_visibility = TRUE) AND listing_status <> 'public' "
                "ORDER BY legal_name, id",
                (public_only,),
            )
            companies = cursor.fetchall()
            if not companies:
                return []
            ids = [row["id"] for row in companies]
            cursor.execute(
                "SELECT * FROM private_company_observations WHERE company_id = ANY(%s) AND (%s = FALSE OR public_visibility = TRUE) ORDER BY id",
                (ids, public_only),
            )
            observations = cursor.fetchall()
            cursor.execute(
                "SELECT * FROM private_company_offers WHERE company_id = ANY(%s) AND (%s = FALSE OR public_visibility = TRUE) ORDER BY id",
                (ids, public_only),
            )
            offers = cursor.fetchall()
    result = []
    for row in companies:
        company = PrivateCompany.model_validate(
            {key: row[key] for key in PrivateCompany.model_fields}
        )
        bundle = CompanyBundle(
            company=company,
            observations=[
                Observation.model_validate({key: item[key] for key in Observation.model_fields})
                for item in observations
                if item["company_id"] == row["id"]
            ],
            offers=[
                InvestmentOffer.model_validate(
                    {key: item[key] for key in InvestmentOffer.model_fields}
                )
                for item in offers
                if item["company_id"] == row["id"]
            ],
        )
        result.append(
            {
                "id": row["id"],
                **company.model_dump(mode="json"),
                "observations": [item.model_dump(mode="json") for item in bundle.observations],
                "offers": [item.model_dump(mode="json") for item in bundle.offers],
                "screening": screen_company(bundle),
            }
        )
    return result
