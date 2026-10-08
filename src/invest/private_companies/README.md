# Private-company research

A separate research pipeline for startups and established private businesses, sharing the existing PostgreSQL database. Public-market tables and ticker identities are unchanged. Company identity, historical evidence and actual investment offers are separate records.

## Workflow

Run commands from the repository root with `uv run`. Database commands use the existing `DB_URL` or `~/.invest_db_url` configuration. No additional database is required.

```bash
uv run private-companies init-db

# Download and stage a small batch from an official US Securities and Exchange Commission (SEC) quarterly archive.
# Set SEC_USER_AGENT to a descriptive application name and your contact address.
uv run private-companies collect-form-d --year 2026 --quarter 3 \
  --limit 50 --output /tmp/private-company-candidates.json

# Review the staged JSON, then import it. All records default to private.
uv run private-companies import-json /tmp/private-company-candidates.json
uv run private-companies list --type startup
uv run private-companies list --type established

# Create narrative dossiers in the private vault, without overwriting existing notes.
uv run private-companies dossier /tmp/private-company-candidates.json
```

`collect-form-d --archive /path/to/archive.zip` reads an existing official archive without another download. Collection does not require a database. Output files must be new paths; the commands refuse to overwrite them. An import validates the full file before writing, then commits each company bundle atomically. If a database error interrupts a batch, completed bundles remain committed and the command reports their count. Re-importing is safe.

The collector excludes disclosed pooled investment funds, keeps the latest filing per issuer within the archive, and uses SEC Central Index Key (CIK) identifiers under the `US-SEC` identity namespace. This is not a local incorporation registration number. A filing does not prove private listing status, company maturity, investor eligibility or investment availability. Collected candidates therefore start as `unclassified` and `unconfirmed`, with no investment offer. Filed offering amounts and amounts sold are fundraising disclosures, never revenue or company valuation. Their `period_end` is the filing date, not a financial year-end. This source is US securities-filing coverage, not a complete international company universe.

## Reviewing and enriching records

Input is one JSON company bundle or a list of bundles. A bundle has `company`, `observations` and `offers`. The validated field definitions are in [models.py](models.py). Unknown fields, blank required values, invalid web URLs, malformed three-letter currency codes, non-finite numeric observations and non-positive investment amounts are rejected.

Classify reviewed companies as `startup` or `established`; retain `unclassified` when evidence is insufficient. Set `listing_status` to `confirmed_private` only after checking it. Public-listed issuers are excluded from the private-company directory. An unclassified/unconfirmed source import preserves an existing reviewed classification, and missing website/sector values preserve existing values. Non-empty incoming values update the company record.

Each observation carries its source URL, retrieval timestamp, reporting period, unit, currency where applicable, and evidence type (`reported`, `estimated`, or `verified`). Verification is an analyst assertion; ingestion never promotes a filed claim to verified. Distinct conflicting assertions remain separate. Re-fetching the same assertion preserves the first retrieval timestamp and does not create duplicates. Visibility may be changed independently of the historical assertion.

Stage-specific checklist metric names:

| Startups | Established businesses |
| --- | --- |
| `customer_retention` | `revenue` |
| `revenue` | `operating_cash_flow` |
| `gross_margin` | `debt` |
| `cash_runway_months` | `customer_concentration` |
| `funding_needs` | `owner_dependence` |
| `dilution` | |

These are evidence-coverage checklists, not automatic business-quality scores or recommendations. Documented evidence still requires review; missing evidence stays unknown. Contradictions are flagged within the same period, unit and currency. Evidence confidence remains unassessed until an analyst evaluates sources. Different stages are not forced into a shared ranking.

Offers have their own external identifier, status, security type, currency, optional valuation and minimum investment, source and terms summary. Availability is shown only for an offer marked available with a minimum investment and terms summary. Eligibility and current availability must still be checked; there is no automatic execution or purchase recommendation. Closing an offer requires an explicit update.

## Public dashboard and private research

The dashboard server exposes `/private-companies` and `/api/private-companies`, with all/startup/established/unclassified views and search. Both desktop and mobile stock dashboards link to the directory.

The existing server is public. Companies, observations and offers default to `public_visibility: false`. Public screening uses only explicitly public evidence and offers, and the public response publishes only directory metadata and checklist states. It never serves dossier contents, raw financial observations or offer terms. Re-importing a record with visibility false revokes its public visibility; do not assume a source refresh preserves approval. No public records are pre-seeded.

Private narrative research belongs in `~/vault/finance/notes/private-companies/`, with an override through `INVEST_PRIVATE_NOTES_DIR`. Database records own structured facts; Markdown owns business assessments, terms analysis, risks and questions. Keep downloaded evidence beside the dossier that uses it. Nothing in the dossier folder is automatically published.

## Verification

```bash
uv run pytest tests/test_private_companies.py tests/test_private_sources_cli.py \
  tests/test_private_dashboard.py --no-cov
```

The real PostgreSQL integration test runs only when `PRIVATE_COMPANIES_TEST_DB_URL` points to a disposable database. It checks idempotent ingestion, retained contradictory facts, rollback and public/private filtering. Never point that test at production.

Source documentation: [SEC Form D datasets](https://www.sec.gov/data-research/sec-markets-data/form-d-data-sets). Future country-specific or licensed collectors can produce the same validated bundle format; they are not implemented by this module.
