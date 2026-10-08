"""Source semantics, invalid input and safe research-file creation."""

import csv
import io
import json
import zipfile
from datetime import datetime, timezone

import pytest

from invest.private_companies.cli import main, read_bundles, write_dossier
from invest.private_companies.models import CompanyBundle
from invest.private_companies.sources import parse_form_d


def archive(*, fund=False, primary="YES", amount="25", duplicate=False):
    tables = {
        "FORMDSUBMISSION.tsv": [
            dict(ACCESSIONNUMBER="000001-26-000001", FILING_DATE="01-OCT-2026", TESTORLIVE="LIVE")
        ],
        "ISSUERS.tsv": [
            dict(
                ACCESSIONNUMBER="000001-26-000001",
                CIK="0000123",
                ENTITYNAME="Fictional Research Candidate",
                IS_PRIMARYISSUER_FLAG=primary,
                JURISDICTIONOFINC="DELAWARE",
            )
        ],
        "OFFERING.tsv": [
            dict(
                ACCESSIONNUMBER="000001-26-000001",
                INDUSTRYGROUPTYPE="Pooled Investment Fund" if fund else "Other Technology",
                ISPOOLEDINVESTMENTFUNDTYPE="",
                TOTALAMOUNTSOLD=amount,
                TOTALOFFERINGAMOUNT="Indefinite",
            )
        ],
    }
    if duplicate:
        for rows in tables.values():
            row = dict(rows[0], ACCESSIONNUMBER="000001-26-000002")
            if "FILING_DATE" in row:
                row["FILING_DATE"] = "02-OCT-2026"
            rows.append(row)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as z:
        for name, rows in tables.items():
            text = io.StringIO()
            writer = csv.DictWriter(text, fieldnames=list(rows[0]), delimiter="\t")
            writer.writeheader()
            writer.writerows(rows)
            z.writestr("2026Q4_d/" + name, text.getvalue())
    return output.getvalue()


def test_form_d_is_unclassified_candidate_not_offer():
    bundle = parse_form_d(archive(), retrieved_at=datetime(2026, 10, 8, tzinfo=timezone.utc))[0]
    assert bundle.company.registration_number == "123"
    assert bundle.company.company_type == "unclassified"
    assert bundle.company.listing_status == "unconfirmed"
    assert bundle.company.public_visibility is False
    assert bundle.offers == []
    assert {item.metric for item in bundle.observations} == {
        "form_d_amount_sold",
        "form_d_filing_date",
    }
    assert all(not item.public_visibility for item in bundle.observations)
    assert "revenue" not in {item.metric for item in bundle.observations}


@pytest.mark.parametrize("kwargs", [{"fund": True}, {"primary": "NO"}])
def test_excludes_funds_and_secondary_issuers(kwargs):
    assert parse_form_d(archive(**kwargs)) == []


def test_keeps_latest_filing_per_cik_and_unknown_amount_not_zero():
    bundle = parse_form_d(archive(amount="Indefinite", duplicate=True))[0]
    assert len(bundle.observations) == 1
    assert bundle.observations[0].value == "2026-10-02"


@pytest.mark.parametrize("limit", [0, -1, 100001])
def test_invalid_collection_limit(limit):
    with pytest.raises(ValueError):
        parse_form_d(archive(), limit=limit)


def test_missing_archive_tables_rejected():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as z:
        z.writestr("unrelated.txt", "data")
    with pytest.raises(ValueError, match="FORMDSUBMISSION"):
        parse_form_d(output.getvalue())


def test_collect_stages_and_refuses_overwrite(tmp_path):
    source = tmp_path / "source.zip"
    source.write_bytes(archive())
    output = tmp_path / "candidates.json"
    args = ["collect-form-d", "--archive", str(source), "--output", str(output)]
    assert main(args) == 0
    bundles = read_bundles(output)
    assert len(bundles) == 1
    assert main(args) == 2
    assert len(read_bundles(output)) == 1


def test_whole_input_validated_before_writes(tmp_path, monkeypatch):
    bundle = parse_form_d(archive())[0].model_dump(mode="json")
    bad = dict(bundle, unexpected="private text")
    source = tmp_path / "input.json"
    source.write_text(json.dumps([bundle, bad]))
    calls = []
    monkeypatch.setattr(
        "invest.private_companies.cli.ingest_bundle", lambda bundle: calls.append(bundle)
    )
    assert main(["import-json", str(source)]) == 2
    assert calls == []


def test_dossier_never_overwrites_research(tmp_path):
    bundle = parse_form_d(archive())[0]
    path = write_dossier(bundle, tmp_path)
    assert "Fictional Research Candidate" in path.read_text()
    assert "Not assessed." in path.read_text()
    path.write_text("Analyst research retained")
    with pytest.raises(FileExistsError):
        write_dossier(bundle, tmp_path)
    assert path.read_text() == "Analyst research retained"


def test_json_input_shape_invalid(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("42")
    with pytest.raises(ValueError):
        read_bundles(path)


def test_corrupt_archive_returns_error_without_traceback(tmp_path, capsys):
    archive_path = tmp_path / "corrupt.zip"
    archive_path.write_bytes(b"not a ZIP")
    assert (
        main(
            [
                "collect-form-d",
                "--archive",
                str(archive_path),
                "--output",
                str(tmp_path / "unused.json"),
            ]
        )
        == 2
    )
    assert "BadZipFile" in capsys.readouterr().err
    assert not (tmp_path / "unused.json").exists()
