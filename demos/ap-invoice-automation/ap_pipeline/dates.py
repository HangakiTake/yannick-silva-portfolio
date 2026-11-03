"""Invoice date parsing. Numeric dates are day/month/year (Canada)."""

from __future__ import annotations

import re
from datetime import date, datetime

from ap_pipeline.textnorm import collapse_space, is_blank_token, strip_accents

_MONTHS = {
    "jan": 1,
    "january": 1,
    "janvier": 1,
    "feb": 2,
    "february": 2,
    "fev": 2,
    "fevrier": 2,
    "mar": 3,
    "march": 3,
    "mars": 3,
    "apr": 4,
    "april": 4,
    "avr": 4,
    "avril": 4,
    "may": 5,
    "mai": 5,
    "jun": 6,
    "june": 6,
    "juin": 6,
    "jul": 7,
    "july": 7,
    "juillet": 7,
    "juil": 7,
    "aug": 8,
    "august": 8,
    "aout": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "septembre": 9,
    "oct": 10,
    "october": 10,
    "octobre": 10,
    "nov": 11,
    "november": 11,
    "novembre": 11,
    "dec": 12,
    "december": 12,
    "decembre": 12,
}


def parse_received_at(value: str) -> datetime:
    text = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError(f"received_at must include a timezone: {value}")
    return parsed


def parse_invoice_date(raw: str | None) -> date | None:
    if raw is None or is_blank_token(raw):
        return None
    text = collapse_space(strip_accents(raw)).casefold().rstrip(".")
    iso = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text)
    if iso:
        return _safe(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
    iso_slash = re.fullmatch(r"(\d{4})/(\d{2})/(\d{2})", text)
    if iso_slash:
        return _safe(int(iso_slash.group(1)), int(iso_slash.group(2)), int(iso_slash.group(3)))
    numeric = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", text)
    if numeric:
        # Day first. 04/05/2026 is 4 May 2026, not 5 April.
        return _safe(int(numeric.group(3)), int(numeric.group(2)), int(numeric.group(1)))
    day_month = re.fullmatch(r"(\d{1,2})[ ]([a-z]+)[ ](\d{4})", text)
    if day_month:
        month = _MONTHS.get(day_month.group(2))
        if month is None:
            return None
        return _safe(int(day_month.group(3)), month, int(day_month.group(1)))
    month_day = re.fullmatch(r"([a-z]+)[ ](\d{1,2}),?[ ](\d{4})", text)
    if month_day:
        month = _MONTHS.get(month_day.group(1))
        if month is None:
            return None
        return _safe(int(month_day.group(3)), month, int(month_day.group(2)))
    dashed = re.fullmatch(r"(\d{1,2})-([a-z]+)-(\d{4})", text)
    if dashed:
        month = _MONTHS.get(dashed.group(2))
        if month is None:
            return None
        return _safe(int(dashed.group(3)), month, int(dashed.group(1)))
    return None


def _safe(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None
