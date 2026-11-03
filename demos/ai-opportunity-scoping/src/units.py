"""Normalise messy time, volume and error-rate cells.

Rules are the ones named in data/gold_units.json. A blank cell is "missing".
Anything else we cannot read is a bad_* code. Callers turn that into an
exception row. Nothing is coerced to zero.
"""

from __future__ import annotations

import re
from decimal import Decimal, ROUND_HALF_UP

PLACES = Decimal("0.0001")
NUM = r"\d+(?:[.,]\d+)?"
WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}
_DAY = Decimal(365) / Decimal(12)
_WEEK = Decimal(52) / Decimal(12)
_YEAR = Decimal(1) / Decimal(12)
FACTORS = {
    "day": _DAY,
    "daily": _DAY,
    "week": _WEEK,
    "weekly": _WEEK,
    "wk": _WEEK,
    "month": Decimal(1),
    "monthly": Decimal(1),
    "mo": Decimal(1),
    "year": _YEAR,
    "yearly": _YEAR,
}


def q(value: Decimal | int | str) -> Decimal:
    return Decimal(value).quantize(PLACES, rounding=ROUND_HALF_UP)


def _approx(text: str) -> str:
    lowered = text.strip().lower()
    for word in ("approximately", "approx.", "approx", "about", "around", "roughly", "~"):
        lowered = lowered.replace(word, " ")
    return re.sub(r"\s+", " ", lowered).strip()


def _number(token: str) -> Decimal:
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", token):
        return Decimal(token.replace(".", ""))
    if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", token):
        return Decimal(token.replace(",", ""))
    if re.fullmatch(r"\d+,\d+", token):
        return Decimal(token.replace(",", "."))
    if re.fullmatch(r"\d+(\.\d+)?", token):
        return Decimal(token)
    raise ValueError(token)


def _leading_number(text: str) -> tuple[str, str] | None:
    for pattern in (
        r"\d{1,3}(?:\.\d{3})+",
        r"\d{1,3}(?:,\d{3})+(?:\.\d+)?",
        r"\d+(?:[.,]\d+)?",
    ):
        match = re.match(pattern, text)
        if match:
            return match.group(0), text[match.end() :]
    return None


def parse_minutes(raw: object) -> tuple[Decimal | None, str | None]:
    if raw is None or str(raw).strip() == "":
        return None, "missing"
    original = str(raw).strip()
    if original.startswith("=") or original.startswith("-"):
        return None, "bad_minutes"
    text = _approx(original)
    if re.search(r"\d\s*-\s*\d", text):
        return None, "bad_minutes"
    if re.search(r"/(week|wk|day|month|mo|year)\b|per\s+(week|day|month|year)|weekly", text):
        return None, "bad_minutes"
    if re.fullmatch(r"half(?:\s+an)?\s+hours?", text):
        return q(30), None
    fraction = re.fullmatch(r"(\d+)\s*/\s*(\d+)\s+hours?", text)
    if fraction:
        denominator = Decimal(fraction.group(2))
        if denominator == 0:
            return None, "bad_minutes"
        return q(Decimal(fraction.group(1)) / denominator * 60), None
    word = re.fullmatch(r"([a-z]+)\s+hours?", text)
    if word:
        if word.group(1) not in WORDS:
            return None, "bad_minutes"
        return q(WORDS[word.group(1)] * 60), None
    clock = re.fullmatch(r"(\d+):(\d{2})(?::(\d{2}))?", text)
    if clock:
        minutes = Decimal(clock.group(2))
        seconds = Decimal(clock.group(3) or 0)
        if minutes >= 60 or seconds >= 60:
            return None, "bad_minutes"
        return q(Decimal(clock.group(1)) * 60 + minutes + seconds / Decimal(60)), None
    hours = re.fullmatch(
        rf"({NUM})\s*(?:h|hr|hrs|hour|hours)\s*(?:({NUM})\s*(?:m|min|mins|minute|minutes))?$",
        text,
    )
    if hours:
        total = _number(hours.group(1)) * 60
        if hours.group(2):
            total += _number(hours.group(2))
        if total < 0:
            return None, "bad_minutes"
        return q(total), None
    mins = re.fullmatch(rf"({NUM})\s*(?:m|min|mins|minute|minutes)$", text)
    if mins:
        value = _number(mins.group(1))
        if value < 0:
            return None, "bad_minutes"
        return q(value), None
    bare = re.fullmatch(rf"({NUM})$", text)
    if bare:
        value = _number(bare.group(1))
        if value < 0:
            return None, "bad_minutes"
        return q(value), None
    return None, "bad_minutes"


def parse_volume(raw: object) -> tuple[Decimal | None, str | None]:
    if raw is None or str(raw).strip() == "":
        return None, "missing"
    original = str(raw).strip()
    if original.startswith("=") or original.startswith("-"):
        return None, "bad_volume"
    text = _approx(original)
    if re.search(r"\d\s*-\s*\d", text):
        return None, "bad_volume"
    found = _leading_number(text)
    if not found:
        return None, "bad_volume"
    token, rest = found
    try:
        number = _number(token)
    except ValueError:
        return None, "bad_volume"
    rest = rest.strip()
    if re.match(r"k(?:/|\s|$)", rest):
        number *= 1000
        rest = rest[1:].strip()
    if re.search(r"\b(h|hr|hrs|hour|hours|min|mins|minute|minutes)\b", rest) or rest in {"h", "hr", "m", "min"}:
        return None, "bad_volume"
    if rest == "":
        factor = Decimal(1)
    else:
        match = re.fullmatch(
            r"(?:a|per|/)?\s*(weeks?|weekly|wk|days?|daily|months?|monthly|mo|years?|yearly)",
            rest,
        )
        if not match:
            return None, "bad_volume"
        unit = match.group(1)
        if unit.endswith("s") and unit not in FACTORS:
            unit = unit[:-1]
        factor = FACTORS[unit]
    if number < 0:
        return None, "bad_volume"
    return q(number * factor), None


def parse_error_rate(raw: object) -> tuple[Decimal | None, str | None]:
    if raw is None or str(raw).strip() == "":
        return None, "missing"
    original = str(raw).strip()
    if original.startswith("="):
        return None, "bad_error"
    text = _approx(original)
    if text in {"none", "zero", "nil"}:
        return q(0), None
    percent = bool(re.search(r"%|percent|pct", text))
    numeric = re.sub(r"%|percent|pct", " ", text)
    numeric = re.sub(r"\s+", " ", numeric).strip()
    if not re.fullmatch(NUM, numeric):
        return None, "bad_error"
    try:
        number = _number(numeric)
    except ValueError:
        return None, "bad_error"
    if number < 0:
        return None, "bad_error"
    if percent:
        if number > 100:
            return None, "bad_error"
        return q(number / Decimal(100)), None
    if number <= 1:
        return q(number), None
    if number <= 100:
        return q(number / Decimal(100)), None
    return None, "bad_error"
