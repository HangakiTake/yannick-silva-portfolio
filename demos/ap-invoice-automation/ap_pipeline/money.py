"""Parse invoice amounts into Decimal. Floats are not used for money."""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation

_TWO_PLACES = Decimal("0.01")


def parse_money(raw: str | None) -> Decimal | None:
    """Parse a single amount.

    Supports `$1,554.00`, `1 320,00`, and `1.320,00`. Returns None when the
    text is not one unambiguous amount with at most two decimal places.
    """
    if raw is None:
        return None
    text = raw.strip().replace("\u00a0", " ")
    if not text:
        return None
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1].strip()
    # Currency codes are removed before the letter check so "1050.00 USD"
    # still parses, while "10O0.00" and "52S.00" do not.
    text = re.sub(r"(?i)\b(?:CAD|USD|EUR|GBP)\b", "", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Zs")
    text = text.replace("'", "").replace("’", "")
    text = text.replace("$", "").replace("€", "").replace("£", "")
    if re.search(r"[A-Za-z]", text):
        # A letter inside the amount (10O0.00, 52S.00) is not a number we will pay.
        return None
    text = text.removeprefix("+")
    if text.startswith("-"):
        negative = True
        text = text[1:]
    if not text or not re.fullmatch(r"\d[\d.,]*", text):
        return None
    normalized = _normalize_separators(text)
    if normalized is None:
        return None
    try:
        value = Decimal(normalized)
    except InvalidOperation:
        return None
    if value.as_tuple().exponent < -2:
        return None
    value = value.quantize(_TWO_PLACES)
    return -value if negative else value


def _normalize_separators(text: str) -> str | None:
    has_comma = "," in text
    has_dot = "." in text
    if has_comma and has_dot:
        if text.rfind(",") > text.rfind("."):
            return text.replace(".", "").replace(",", ".")
        return text.replace(",", "")
    if has_comma:
        parts = text.split(",")
        if len(parts) == 2 and len(parts[1]) == 2:
            return f"{parts[0]}.{parts[1]}"
        if all(len(part) == 3 for part in parts[1:]):
            return "".join(parts)
        return None
    if has_dot:
        parts = text.split(".")
        if len(parts) == 2 and 1 <= len(parts[1]) <= 2:
            return text
        if len(parts) > 2 and all(len(part) == 3 for part in parts[1:]):
            return "".join(parts)
        return None
    return text


def money_to_json_number(value: Decimal) -> str:
    """Canonical JSON number with two decimal places, without binary float drift."""
    return format(value.quantize(_TWO_PLACES), "f")
