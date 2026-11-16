"""Strict, versioned input contracts. Monetary inputs are always text."""
import hashlib
import json
import re
from datetime import date, datetime
from decimal import Decimal, localcontext
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DIMENSIONS = (
    "environment", "application", "cube", "scenario", "year", "period", "view",
    "entity", "account", "intercompany", "movement", "data_source", "consolidation", "currency",
)


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value) -> str:
    data = value if isinstance(value, bytes) else canonical(value).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def money(value: str) -> Decimal:
    if not isinstance(value, str) or not re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", value):
        raise ValueError("Amount must be a plain decimal string in units, with no grouping or exponent")
    digits = value.replace("-", "").replace(".", "")
    scale = len(value.split(".")[1]) if "." in value else 0
    if len(digits) > 38 or scale > 18:
        raise ValueError("Unverifiable precision exceeds 38 digits or 18 fractional digits")
    return Decimal(value)


def total(values) -> Decimal:
    with localcontext() as context:
        context.prec = 100
        return sum(values, Decimal("0"))


def decimal_text(value: Decimal) -> str:
    return format(value, "f")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class POV(StrictModel):
    environment: str
    application: str
    cube: str
    scenario: str
    year: str
    period: str
    view: str
    entity: str
    account: str
    intercompany: str
    movement: str
    data_source: str
    consolidation: str
    currency: str
    custom: dict[str, str]

    @field_validator(*DIMENSIONS)
    @classmethod
    def nonempty(cls, value):
        if not value or value != value.strip() or len(value) > 160:
            raise ValueError("Every dimension requires an explicit member")
        return value

    def key(self):
        return canonical(self.model_dump())


class Row(StrictModel):
    record_id: str = Field(min_length=1, max_length=160)
    pov: POV
    amount: str | None
    state: Literal["VALUE", "MISSING", "RESTRICTED"] = "VALUE"
    journal_id: str = ""
    line: int = Field(ge=2)

    @field_validator("amount")
    @classmethod
    def valid_amount(cls, value):
        if value is not None:
            money(value)
        return value


class Manifest(StrictModel):
    version: Literal["1"]
    dataset_id: str = Field(min_length=1, max_length=160)
    side: Literal["GL", "FCCS"]
    source_system: str = Field(min_length=1)
    extracted_at: str
    row_count: int = Field(ge=0, le=100000)
    byte_count: int = Field(ge=0, le=20000000)
    sha256: str = Field(pattern="^[a-f0-9]{64}$")
    complete: bool
    precision_verified: bool
    policy_id: str
    unit: Literal["units"]
    expected_povs: list[POV]
    totals_by_currency: dict[str, str]
    journals: dict[str, int] = Field(default_factory=dict)
    controls: dict = Field(default_factory=dict)

    @field_validator("extracted_at")
    @classmethod
    def timestamp(cls, value):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("Extraction time requires a timezone")
        return value

    @field_validator("totals_by_currency")
    @classmethod
    def valid_totals(cls, value):
        for amount in value.values():
            money(amount)
        return value


class Policy(StrictModel):
    id: str = Field(min_length=1, max_length=64, pattern="^[A-Za-z0-9_.-]+$")
    name: str
    effective_from: str
    effective_to: str
    currency_scales: dict[str, int]
    members: dict[str, list[str]]
    custom_dimensions: list[str]
    account_map: dict[str, str]
    sign_map: dict[str, Literal["1", "-1"]]
    required_controls: list[str]
    exclusions: dict[str, str]
    maximum_age_seconds: int = Field(ge=1)
    formulas: dict[str, list[dict]] = Field(default_factory=dict)

    @field_validator("currency_scales")
    @classmethod
    def scales(cls, value):
        if not value or any(type(v) is not int or not 0 <= v <= 9 for v in value.values()):
            raise ValueError("An explicit minor unit from 0 to 9 is required for each currency")
        return value

    @model_validator(mode="after")
    def complete_policy(self):
        known = {"trial_balance", "journals", "intercompany", "fx", "hierarchy", "consolidation", "prior_period"}
        if set(self.required_controls) - known or set(self.exclusions) - known:
            raise ValueError("Policy references unsupported controls")
        if set(self.required_controls) & set(self.exclusions):
            raise ValueError("A required control cannot also be excluded")
        if not set(DIMENSIONS).issubset(self.members):
            raise ValueError("Policy must inventory every standard dimension")
        if date.fromisoformat(self.effective_to) < date.fromisoformat(self.effective_from):
            raise ValueError("Policy effective dates are reversed")
        return self
