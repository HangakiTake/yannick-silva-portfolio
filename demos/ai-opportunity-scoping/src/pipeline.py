"""Inventory in, ranked recommendations and costs out."""

from __future__ import annotations

from dataclasses import dataclass

from src.costs import monthly_openai_usd
from src.inventory import Inventory, load_inventory
from src.paths import price_config
from src.recommend import recommend
from src.scoring import rank_rows, score_row


@dataclass
class Scoped:
    inventory: Inventory
    ranked: list
    recommendations: dict
    costs: dict


def scope_path(path) -> Scoped:
    inventory = load_inventory(path)
    scored = [score_row(row) for row in inventory.parsed]
    ranked = rank_rows(scored)
    recommendations = {row.process: recommend(row) for row in ranked}
    prices = price_config()
    costs = {}
    for row in ranked:
        pattern = recommendations[row.process].pattern
        amount, why, profile = monthly_openai_usd(row.monthly_volume, pattern, prices)
        costs[row.process] = {"usd": amount, "why": why, "profile": profile, "pattern": pattern}
    return Scoped(inventory, ranked, recommendations, costs)


def build_shortlist(scoped: Scoped, limit: int = 8) -> list:
    chosen = []
    for row in scoped.ranked:
        if scoped.recommendations[row.process].pattern == "dont_automate":
            continue
        chosen.append(row)
        if len(chosen) == limit:
            break
    return chosen
