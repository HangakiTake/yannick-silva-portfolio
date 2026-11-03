"""Strict schema for one extraction. Invalid model output never becomes a row."""

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

REQUEST_TYPES = ("quote", "support", "booking", "billing", "complaint", "other")
URGENCIES = ("low", "normal", "high")
FLAGS = (
    "legal",
    "payment_dispute",
    "angry",
    "spam",
    "empty",
    "low_confidence",
    "ambiguous_date",
    "truncated",
    "schema_invalid",
)

LOW_CONFIDENCE = 0.60


class SchemaError(ValueError):
    pass


class Extraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_type: Literal["quote", "support", "booking", "billing", "complaint", "other"]
    urgency: Literal["low", "normal", "high"]
    customer_name: str = ""
    company: str = ""
    contact_email: str = ""
    contact_phone: str = ""
    key_dates: list[str] = Field(default_factory=list)
    date_phrases: list[str] = Field(default_factory=list)
    amounts: list[str] = Field(default_factory=list)
    summary: str
    missing_info: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    flags: list[
        Literal[
            "legal",
            "payment_dispute",
            "angry",
            "spam",
            "empty",
            "low_confidence",
            "ambiguous_date",
            "truncated",
            "schema_invalid",
        ]
    ] = Field(default_factory=list)


def parse_extraction(raw: str) -> Extraction:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SchemaError("invalid_json") from exc
    if not isinstance(data, dict):
        raise SchemaError("not_object")
    try:
        return Extraction.model_validate(data)
    except ValidationError as exc:
        raise SchemaError("schema_mismatch") from exc
