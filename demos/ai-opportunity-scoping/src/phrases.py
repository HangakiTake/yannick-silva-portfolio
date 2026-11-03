"""Phrase lists live in the architecture rubric so the code cannot drift from it."""

from __future__ import annotations

import re
from functools import lru_cache

from src.paths import ROOT


@lru_cache(maxsize=1)
def phrase_groups() -> dict[str, tuple[str, ...]]:
    text = (ROOT / "docs" / "architecture_rubric.md").read_text(encoding="utf-8")
    fence = re.search(r"```phrases\n(.*?)```", text, re.S)
    if not fence:
        raise RuntimeError("architecture rubric is missing the phrases fence")
    groups: dict[str, list[str]] = {}
    for line in fence.group(1).splitlines():
        line = line.strip()
        if not line or ": " not in line:
            continue
        key, phrase = line.split(": ", 1)
        groups.setdefault(key, []).append(phrase)
    return {key: tuple(values) for key, values in groups.items()}


def has_phrase(text: str, phrase: str) -> bool:
    return re.search(rf"(?<![a-z]){re.escape(phrase)}", text) is not None


def first_phrase(text: str, phrases: tuple[str, ...]) -> str | None:
    for phrase in phrases:
        if has_phrase(text, phrase):
            return phrase
    return None


def scrub(text: str) -> str:
    cleaned = text
    for phrase in sorted(phrase_groups()["scrub"], key=len, reverse=True):
        cleaned = re.sub(rf"(?<![a-z]){re.escape(phrase)}", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()
