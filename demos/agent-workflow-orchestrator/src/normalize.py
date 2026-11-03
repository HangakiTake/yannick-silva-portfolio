"""Canonical lead fields and the idempotency key.

The key is sha256(step + normalised email + sha256 of the canonical payload).
A second run of the same step, person and payload is the same key.
"""

from __future__ import annotations

import hashlib
import json
import re

PLACEHOLDERS = {
    "",
    "n/a",
    "na",
    "tbd",
    "unknown",
    "none",
    "-",
    "?",
    "see attached",
}

_EMAIL = re.compile(r"[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}")
_FIELDS = ("name", "phone", "site_address", "monthly_kwh")


def normalize_email(value: object) -> str:
    text = " ".join(str(value).split()).lower()
    bracketed = re.search(r"<([^<>]+)>", text)
    if bracketed:
        text = bracketed.group(1).strip()
    if not _EMAIL.fullmatch(text):
        raise ValueError("unusable email")
    return text


def usable_kwh(value: object) -> str | None:
    text = " ".join(str(value).split()).lower().replace(",", "")
    if text.endswith("kwh"):
        text = text[:-3].strip()
    if not re.fullmatch(r"\d+(?:\.\d+)?", text):
        return None
    number = float(text)
    if number <= 0:
        return None
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def usable_address(value: object) -> bool:
    text = " ".join(str(value).split())
    if text.lower() in PLACEHOLDERS:
        return False
    has_digit = any(char.isdigit() for char in text)
    has_letter = any(char.isalpha() for char in text)
    return has_digit and has_letter and len(text) >= 8


def canonicalize(raw: dict) -> dict:
    kwh_raw = " ".join(str(raw.get("monthly_kwh", "")).split())
    kwh = usable_kwh(kwh_raw)
    return {
        "name": " ".join(str(raw.get("name", "")).split()),
        "email": normalize_email(raw.get("email", "")),
        "phone": re.sub(r"\D", "", str(raw.get("phone", ""))),
        "site_address": " ".join(str(raw.get("site_address", "")).split()),
        "monthly_kwh": kwh if kwh is not None else kwh_raw,
    }


def missing_fields(lead: dict) -> list[str]:
    missing = []
    if not usable_address(lead.get("site_address", "")):
        missing.append("site_address")
    if usable_kwh(lead.get("monthly_kwh", "")) is None:
        missing.append("monthly_kwh")
    return missing


def _usable(field: str, value: str) -> bool:
    if field == "site_address":
        return usable_address(value)
    if field == "monthly_kwh":
        return usable_kwh(value) is not None
    if field == "phone":
        return len(value) >= 10
    return bool(value)


def merge(existing: dict | None, incoming: dict) -> dict:
    """Keep a usable value when a later row would blank it out.

    A later usable value replaces an older one, including a better monthly kWh
    after a first row that only said "about 900".
    """
    if existing is None:
        return dict(incoming)
    merged = {"email": incoming["email"]}
    for field in _FIELDS:
        old = existing[field]
        new = incoming[field]
        if field == "monthly_kwh" and usable_kwh(new) is not None:
            new = usable_kwh(new) or new
        if _usable(field, new) and (not _usable(field, old) or new != old):
            merged[field] = new
        else:
            merged[field] = old
    return merged


def payload_hash(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def idempotency_key(step: str, entity_id: str, payload: dict) -> str:
    material = f"{step}|{normalize_email(entity_id)}|{payload_hash(payload)}"
    return hashlib.sha256(material.encode()).hexdigest()


def same_lead(row: dict | None, expected: dict) -> bool:
    if row is None:
        return False
    return all(row[field] == expected[field] for field in ("email", *_FIELDS))
