"""Collect research candidates from official SEC Form D quarterly archives.

A notice is neither proof of private listing status nor an accessible investment.
No offer or startup classification is inferred from a filing.
"""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import requests

from .models import CompanyBundle, Observation, PrivateCompany

SEC_ARCHIVE = (
    "https://www.sec.gov/files/datastandardsinnovation/data/form-d-data-sets/{year}q{quarter}_d.zip"
)
US_JURISDICTIONS = set(
    "ALABAMA ALASKA ARIZONA ARKANSAS CALIFORNIA COLORADO CONNECTICUT DELAWARE FLORIDA GEORGIA HAWAII IDAHO ILLINOIS INDIANA IOWA KANSAS KENTUCKY LOUISIANA MAINE MARYLAND MASSACHUSETTS MICHIGAN MINNESOTA MISSISSIPPI MISSOURI MONTANA NEBRASKA NEVADA OHIO OKLAHOMA OREGON PENNSYLVANIA TENNESSEE TEXAS UTAH VERMONT VIRGINIA WASHINGTON WISCONSIN WYOMING".split()
) | {
    "NEW HAMPSHIRE",
    "NEW JERSEY",
    "NEW MEXICO",
    "NEW YORK",
    "NORTH CAROLINA",
    "NORTH DAKOTA",
    "RHODE ISLAND",
    "SOUTH CAROLINA",
    "SOUTH DAKOTA",
    "WEST VIRGINIA",
    "DISTRICT OF COLUMBIA",
}
MAX_ARCHIVE_BYTES = 50_000_000
MAX_EXPANDED_BYTES = 250_000_000


def download_form_d(year: int, quarter: int, user_agent: str) -> bytes:
    """Download one bounded archive; require a caller-supplied SEC contact identity."""
    if not 2008 <= year <= datetime.now(timezone.utc).year or quarter not in (1, 2, 3, 4):
        raise ValueError("Use a year from 2008 through the current year and quarter 1–4")
    if not user_agent.strip():
        raise ValueError("SEC requests require a descriptive user agent with contact information")
    with requests.get(
        SEC_ARCHIVE.format(year=year, quarter=quarter),
        headers={"User-Agent": user_agent},
        timeout=(10, 60),
        stream=True,
    ) as response:
        response.raise_for_status()
        chunks, size = [], 0
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > MAX_ARCHIVE_BYTES:
                raise ValueError("SEC archive exceeds download size limit")
            chunks.append(chunk)
    return b"".join(chunks)


def parse_form_d(
    archive: bytes, *, limit: int = 50, retrieved_at: datetime | None = None
) -> list[CompanyBundle]:
    """Keep latest filing per issuer, excluding disclosed pooled investment funds."""
    if not 1 <= limit <= 100_000:
        raise ValueError("limit must be between 1 and 100000")
    if len(archive) > MAX_ARCHIVE_BYTES:
        raise ValueError("Archive exceeds size limit")
    fetched = retrieved_at or datetime.now(timezone.utc)
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        if sum(info.file_size for info in z.infolist()) > MAX_EXPANDED_BYTES:
            raise ValueError("Expanded archive exceeds size limit")

        def rows(suffix, required):
            matches = [n for n in z.namelist() if n.split("/")[-1].upper() == suffix.upper()]
            if len(matches) != 1:
                raise ValueError(f"Archive must contain exactly one {suffix}")
            reader = csv.DictReader(
                io.StringIO(z.read(matches[0]).decode("utf-8-sig")), delimiter="\t"
            )
            missing = set(required) - set(reader.fieldnames or [])
            if missing:
                raise ValueError(
                    f"{suffix} is missing required fields: {', '.join(sorted(missing))}"
                )
            return list(reader)

        submissions = {
            r["ACCESSIONNUMBER"]: r
            for r in rows("FORMDSUBMISSION.tsv", ("ACCESSIONNUMBER", "FILING_DATE"))
        }
        offerings = {
            r["ACCESSIONNUMBER"]: r
            for r in rows("OFFERING.tsv", ("ACCESSIONNUMBER", "INDUSTRYGROUPTYPE"))
        }
        issuers = rows(
            "ISSUERS.tsv", ("ACCESSIONNUMBER", "CIK", "ENTITYNAME", "IS_PRIMARYISSUER_FLAG")
        )
    latest = {}
    for issuer in issuers:
        accession = issuer.get("ACCESSIONNUMBER", "").strip()
        filing, offering = submissions.get(accession), offerings.get(accession)
        cik = issuer.get("CIK", "").strip()
        if not filing or not offering or not cik.isdigit():
            continue
        if issuer.get("IS_PRIMARYISSUER_FLAG", "").strip().upper() not in ("YES", "TRUE", "Y", "1"):
            continue
        if filing.get("TESTORLIVE", "LIVE").strip().upper() != "LIVE":
            continue
        if offering.get(
            "INDUSTRYGROUPTYPE", ""
        ).strip() == "Pooled Investment Fund" or offering.get(
            "ISPOOLEDINVESTMENTFUNDTYPE", ""
        ).strip().upper() in ("TRUE", "YES", "1"):
            continue
        if not issuer.get("ENTITYNAME", "").strip():
            continue
        filing_date = datetime.strptime(filing["FILING_DATE"].strip(), "%d-%b-%Y").date()
        key = str(int(cik))
        if key not in latest or (filing_date, accession) > latest[key][0]:
            latest[key] = ((filing_date, accession), issuer, offering)
    result = []
    for cik, ((filing_date, accession), issuer, offering) in sorted(
        latest.items(), key=lambda pair: pair[1][0], reverse=True
    )[:limit]:
        source = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/{accession}-index.html"
        jurisdiction = issuer.get("JURISDICTIONOFINC", "").strip()
        company = PrivateCompany(
            jurisdiction="US-SEC",
            registration_number=cik,
            legal_name=issuer["ENTITYNAME"],
            country="US" if jurisdiction.upper() in US_JURISDICTIONS else jurisdiction or "Unknown",
            sector=offering.get("INDUSTRYGROUPTYPE", "").strip() or None,
        )
        observations = []
        for field, metric in [
            ("TOTALAMOUNTSOLD", "form_d_amount_sold"),
            ("TOTALOFFERINGAMOUNT", "form_d_offering_amount"),
        ]:
            raw = offering.get(field, "").strip()
            try:
                value = float(raw)
            except ValueError:
                continue
            if value < 0:
                continue
            observations.append(
                Observation(
                    metric=metric,
                    value=value,
                    unit="currency",
                    currency="USD",
                    period_end=filing_date,
                    source_url=source,
                    retrieved_at=fetched,
                    evidence_type="reported",
                )
            )
        observations.append(
            Observation(
                metric="form_d_filing_date",
                value=filing_date.isoformat(),
                unit="date",
                period_end=filing_date,
                source_url=source,
                retrieved_at=fetched,
                evidence_type="reported",
            )
        )
        result.append(CompanyBundle(company=company, observations=observations))
    return result


def read_archive(path: Path) -> bytes:
    if path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("Archive exceeds size limit")
    return path.read_bytes()
