"""Shared typo cleanup. Applied to a working copy; evidence quotes stay original."""

from __future__ import annotations

import re

_TYPOS = [
    (re.compile(r"\bemials\b"), "emails"),
    (re.compile(r"\bgoogel\b"), "google"),
    (re.compile(r"\breciepts\b"), "receipts"),
    (re.compile(r"\breciept\b"), "receipt"),
    (re.compile(r"\binvioce\b"), "invoice"),
    (re.compile(r"\binvioce s\b"), "invoices"),
    (re.compile(r"\bminuts\b"), "minutes"),
    (re.compile(r"\baprox\b"), "approx"),
    (re.compile(r"\bseverl\b"), "several"),
    (re.compile(r"\bcalender\b"), "calendar"),
    (re.compile(r"\bwatsapp\b"), "whatsapp"),
    (re.compile(r"\bthru\b"), "through"),
    (re.compile(r"\breconcil(?!e)"), "reconcile"),
]


def normalize(text: str) -> str:
    out = text.casefold()
    for pattern, repl in _TYPOS:
        out = pattern.sub(repl, out)
    return out
