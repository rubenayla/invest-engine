-- Private-company identities, immutable evidence and separately identified offers.
CREATE TABLE IF NOT EXISTS private_companies (
    id BIGSERIAL PRIMARY KEY,
    jurisdiction TEXT NOT NULL,
    registration_number TEXT NOT NULL,
    legal_name TEXT NOT NULL,
    company_type TEXT NOT NULL CHECK (company_type IN ('startup', 'established', 'unclassified')),
    listing_status TEXT NOT NULL DEFAULT 'unconfirmed' CHECK (listing_status IN ('unconfirmed', 'confirmed_private', 'public')),
    country TEXT NOT NULL,
    website TEXT,
    sector TEXT,
    public_visibility BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (jurisdiction, registration_number)
);
CREATE TABLE IF NOT EXISTS private_company_observations (
    id BIGSERIAL PRIMARY KEY,
    company_id BIGINT NOT NULL REFERENCES private_companies(id),
    public_visibility BOOLEAN NOT NULL DEFAULT FALSE,
    fact_hash TEXT NOT NULL,
    metric TEXT NOT NULL,
    value JSONB NOT NULL,
    unit TEXT NOT NULL,
    currency TEXT,
    period_end DATE,
    source_url TEXT NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL,
    evidence_type TEXT NOT NULL CHECK (evidence_type IN ('reported', 'estimated', 'verified')),
    UNIQUE (company_id, fact_hash)
);
CREATE TABLE IF NOT EXISTS private_company_offers (
    id BIGSERIAL PRIMARY KEY,
    company_id BIGINT NOT NULL REFERENCES private_companies(id),
    public_visibility BOOLEAN NOT NULL DEFAULT FALSE,
    external_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('available', 'closed', 'unknown')),
    security_type TEXT NOT NULL,
    currency TEXT NOT NULL,
    pre_money_valuation DOUBLE PRECISION CHECK (pre_money_valuation > 0 AND pre_money_valuation < 'Infinity'::float8),
    minimum_investment DOUBLE PRECISION CHECK (minimum_investment > 0 AND minimum_investment < 'Infinity'::float8),
    terms_summary TEXT,
    source_url TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (company_id, external_id)
);
CREATE INDEX IF NOT EXISTS idx_private_observations_company ON private_company_observations(company_id);
CREATE INDEX IF NOT EXISTS idx_private_offers_company ON private_company_offers(company_id);
