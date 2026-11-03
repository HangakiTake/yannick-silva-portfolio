"""Monthly cost from config/costs.json. Currencies are not mixed into one total."""

from __future__ import annotations

import json

from .paths import CONFIG


def load_costs() -> dict:
    return json.loads((CONFIG / "costs.json").read_text(encoding="utf-8"))


def monthly_cost(config: dict | None = None) -> dict:
    cfg = config or load_costs()
    assumptions = cfg["assumptions"]
    prices = cfg["prices"]
    inquiries = float(assumptions["inquiries_per_month"])
    claude = inquiries * (
        float(assumptions["avg_input_tokens"]) * float(prices["claude_input_usd_per_mtok"])
        + float(assumptions["avg_output_tokens"]) * float(prices["claude_output_usd_per_mtok"])
    ) / 1_000_000
    return {
        "as_of": cfg["as_of"],
        "model": prices["claude_model"],
        "inquiries_per_month": int(inquiries),
        "n8n_eur": prices["n8n_cloud_starter_eur_billed_monthly"],
        "n8n_eur_if_billed_annually": prices["n8n_cloud_starter_eur_billed_annually_per_month"],
        "starter_executions": prices["n8n_starter_executions_per_month"],
        "claude_usd": round(claude, 4),
        "gmail_usd": prices["gmail_usd"],
        "sheets_usd": prices["google_sheets_usd"],
        "assumptions": assumptions,
        "sources": cfg["sources"],
        "input_tokens": assumptions["avg_input_tokens"],
        "output_tokens": assumptions["avg_output_tokens"],
        "input_price": prices["claude_input_usd_per_mtok"],
        "output_price": prices["claude_output_usd_per_mtok"],
    }
