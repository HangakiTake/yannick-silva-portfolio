"""Normalization helpers shared by extraction, validation, and scoring."""

from __future__ import annotations

import re
import unicodedata

_MISSING_TOKENS = {
    "",
    "n/a",
    "na",
    "none",
    "null",
    "tbd",
    "-",
    "—",
    "–",
    ".",
}


def strip_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def collapse_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_label(value: str) -> str:
    text = strip_accents(value).casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return collapse_space(text)


def is_blank_token(value: str | None) -> bool:
    if value is None:
        return True
    return collapse_space(value).casefold() in _MISSING_TOKENS


def clean_text(value: str | None) -> str | None:
    if value is None or is_blank_token(value):
        return None
    return collapse_space(value)


def vendor_key(value: str) -> str:
    text = strip_accents(value).casefold().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return collapse_space(text)


def invoice_key(value: str) -> str:
    return re.sub(r"\s+", "", value).upper()


def po_key(value: str) -> str | None:
    if is_blank_token(value):
        return None
    compact = re.sub(r"[^A-Za-z0-9]", "", value).upper()
    if not compact:
        return None
    match = re.fullmatch(r"(?:PO)?(\d+)", compact)
    if match:
        return f"PO-{match.group(1)}"
    return compact
