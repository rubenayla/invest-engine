"""Collect, import and inspect private-company research without publishing by default."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import zipfile
from pathlib import Path

import psycopg2
import requests
from pydantic import ValidationError

from .models import CompanyBundle
from .repository import ingest_bundle, initialize_schema, list_companies
from .screening import screen_company
from .sources import download_form_d, parse_form_d, read_archive


def read_bundles(path: Path) -> list[CompanyBundle]:
    data = json.loads(path.read_text())
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        raise ValueError("Input must be a company bundle or a list of bundles")
    # Validate the whole input before the first write.
    return [CompanyBundle.model_validate(item) for item in data]


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Refuse to overwrite retained input or someone else's research.
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def write_dossier(bundle: CompanyBundle, directory: Path) -> Path:
    """Create a private narrative dossier; never overwrite an analyst's work."""
    company = bundle.company
    slug = (
        re.sub(r"[^a-zA-Z0-9_-]+", "-", f"{company.jurisdiction}-{company.registration_number}")
        .strip("-")
        .lower()
    )
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{slug}.md"
    screen = screen_company(bundle)
    sources = sorted(
        {str(item.source_url) for item in bundle.observations}
        | {str(item.source_url) for item in bundle.offers}
    )
    body = f"""# {company.legal_name}

Identity: {company.jurisdiction} / {company.registration_number}.
Company type: {company.company_type}. Listing status: {company.listing_status}.

## Business assessment

Not assessed. Describe the product, customers, competition and reasons the business may succeed or fail.

## Evidence to investigate

"""
    body += (
        "\n".join(f"- {item['label']}: {item['status']}." for item in screen["criteria"])
        or "Classify the company before using a stage-specific checklist."
    )
    body += """

## Investment terms and access

Not assessed. Identify the offered security, valuation, fees, eligibility, shareholder rights, dilution and sale restrictions. A fundraising notice does not establish an accessible investment.

## Risks and unanswered questions

Record material uncertainties and the evidence needed to resolve them.

## Sources

"""
    body += "\n".join(f"- {source}" for source in sources) or "No sources recorded."
    body += "\n"
    with path.open("x") as stream:
        stream.write(body)
    return path


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "init-db", help="Create private-company tables in the configured PostgreSQL database"
    )
    collect = commands.add_parser(
        "collect-form-d", help="Stage SEC candidates as JSON without importing or publishing"
    )
    collect.add_argument("--year", type=int)
    collect.add_argument("--quarter", type=int, choices=range(1, 5))
    collect.add_argument(
        "--archive", type=Path, help="Read a previously downloaded official ZIP instead of fetching"
    )
    collect.add_argument("--user-agent", default=os.environ.get("SEC_USER_AGENT"))
    collect.add_argument("--limit", type=int, default=50)
    collect.add_argument("--output", type=Path, required=True)
    ingest = commands.add_parser("import-json", help="Validate and import reviewed company bundles")
    ingest.add_argument("path", type=Path)
    listing = commands.add_parser("list", help="Export records and evidence checks as JSON")
    listing.add_argument("--public-only", action="store_true")
    listing.add_argument(
        "--type", choices=("all", "startup", "established", "unclassified"), default="all"
    )
    listing.add_argument("--output", type=Path)
    dossier = commands.add_parser(
        "dossier", help="Create a private Markdown dossier from a reviewed input bundle"
    )
    dossier.add_argument("path", type=Path)
    dossier.add_argument(
        "--directory",
        type=Path,
        default=Path(
            os.environ.get(
                "INVEST_PRIVATE_NOTES_DIR",
                str(Path.home() / "vault/finance/notes/private-companies"),
            )
        ),
    )
    return p


def main(argv: list[str] | None = None) -> int:
    p = parser()
    args = p.parse_args(argv)
    try:
        if args.command == "init-db":
            initialize_schema()
            print("Private-company tables initialized.")
        elif args.command == "collect-form-d":
            if args.archive:
                archive = read_archive(args.archive)
            else:
                if args.year is None or args.quarter is None or not args.user_agent:
                    p.error(
                        "Fetching requires --year, --quarter and --user-agent (or SEC_USER_AGENT)"
                    )
                archive = download_form_d(args.year, args.quarter, args.user_agent)
            bundles = parse_form_d(archive, limit=args.limit)
            write_json(args.output, [item.model_dump(mode="json") for item in bundles])
            print(
                f"Staged {len(bundles)} unclassified candidates at {args.output}; listing and investment access are unconfirmed."
            )
        elif args.command == "import-json":
            bundles = read_bundles(args.path)
            completed = 0
            try:
                for bundle in bundles:
                    ingest_bundle(bundle)
                    completed += 1
            except psycopg2.Error:
                print(
                    f"Import stopped after {completed} committed bundles; failing bundle rolled back. Re-run safely after resolving the database error.",
                    file=sys.stderr,
                )
                raise
            print(
                f"Imported {completed} bundles. Public display requires explicit per-record visibility flags."
            )
        elif args.command == "list":
            records = list_companies(public_only=args.public_only)
            records = [
                row for row in records if args.type == "all" or row["company_type"] == args.type
            ]
            if args.output:
                write_json(args.output, records)
                print(f"Exported {len(records)} records to {args.output}.")
            else:
                print(json.dumps(records, indent=2, ensure_ascii=False, allow_nan=False))
        elif args.command == "dossier":
            for bundle in read_bundles(args.path):
                print(write_dossier(bundle, args.directory))
    except ValidationError as exc:
        fields = ", ".join(
            ".".join(map(str, error["loc"])) for error in exc.errors(include_input=False)
        )
        print(f"Invalid input fields: {fields}. No input values printed.", file=sys.stderr)
        return 2
    except psycopg2.Error:
        print(
            "Database operation failed. Check configuration, connectivity and init-db; connection details omitted.",
            file=sys.stderr,
        )
        return 1
    except (ValueError, OSError, zipfile.BadZipFile, requests.RequestException) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    return 0
