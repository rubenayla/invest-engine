"""Validated private-company records, independent of public-market tickers."""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
)

NonEmpty = Annotated[str, Field(min_length=1)]
Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
PositiveAmount = Annotated[float, Field(gt=0, allow_inf_nan=False)]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PrivateCompany(Record):
    jurisdiction: NonEmpty
    registration_number: NonEmpty
    legal_name: NonEmpty
    company_type: Literal["startup", "established", "unclassified"] = "unclassified"
    listing_status: Literal["unconfirmed", "confirmed_private", "public"] = "unconfirmed"
    country: NonEmpty
    website: HttpUrl | None = None
    sector: NonEmpty | None = None
    public_visibility: bool = False

    @field_validator("jurisdiction")
    @classmethod
    def canonical_jurisdiction(cls, value: str) -> str:
        return value.upper()


class Observation(Record):
    """One immutable source assertion; conflicting assertions are retained."""

    metric: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]
    value: StrictBool | StrictInt | StrictFloat | StrictStr
    unit: NonEmpty
    currency: Currency | None = None
    period_end: date | None = None
    source_url: HttpUrl
    retrieved_at: datetime
    evidence_type: Literal["reported", "estimated", "verified"]
    public_visibility: bool = False

    @field_validator("value")
    @classmethod
    def valid_value(cls, value):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Observation values must be finite")
        if isinstance(value, str) and not value.strip():
            raise ValueError("Observation text cannot be blank")
        return value

    @field_validator("retrieved_at")
    @classmethod
    def aware_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("retrieved_at must include a timezone")
        return value


class InvestmentOffer(Record):
    """An identified investment offer, not a fundraising announcement."""

    public_visibility: bool = False
    external_id: NonEmpty
    status: Literal["available", "closed", "unknown"] = "unknown"
    security_type: NonEmpty
    currency: Currency
    pre_money_valuation: PositiveAmount | None = None
    minimum_investment: PositiveAmount | None = None
    terms_summary: NonEmpty | None = None
    source_url: HttpUrl


class CompanyBundle(Record):
    company: PrivateCompany
    observations: list[Observation] = Field(default_factory=list)
    offers: list[InvestmentOffer] = Field(default_factory=list)
