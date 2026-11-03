"""Monthly OpenAI cost from config/openai_prices.json. No prices live in this file."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from src.paths import price_config

MONEY = Decimal("0.0001")


def monthly_openai_usd(volume: Decimal, pattern: str, prices: dict | None = None) -> tuple[Decimal, str, dict]:
    prices = prices or price_config()
    profile = prices["profiles"][pattern]
    if not profile.get("model"):
        return Decimal("0.0000"), profile["why"], profile
    model = prices["models"][profile["model"]]
    vol = Decimal(volume)
    million = Decimal(1000000)
    incoming = vol * Decimal(profile["input_tokens_per_item"]) * Decimal(str(model["input_usd_per_million"])) / million
    outgoing = vol * Decimal(profile["output_tokens_per_item"]) * Decimal(str(model["output_usd_per_million"])) / million
    embed = Decimal(0)
    if profile.get("embedding_model"):
        embed_price = prices["models"][profile["embedding_model"]]["usd_per_million"]
        embed = vol * Decimal(profile["embedding_tokens_per_item"]) * Decimal(str(embed_price)) / million
    total = (incoming + outgoing + embed).quantize(MONEY, rounding=ROUND_HALF_UP)
    return total, profile["why"], profile
