"""Paths and JSON config used by the rest of the kit."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def scoring_config() -> dict:
    return load_json(ROOT / "config" / "scoring.json")


@lru_cache(maxsize=1)
def price_config() -> dict:
    return load_json(ROOT / "config" / "openai_prices.json")


@lru_cache(maxsize=1)
def refund_policy() -> dict:
    return load_json(ROOT / "config" / "refund_policy.json")


@lru_cache(maxsize=1)
def tool_schema() -> dict:
    return load_json(ROOT / "shared" / "tools.schema.json")
