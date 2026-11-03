"""Write the decision note as Markdown and HTML."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.paths import ROOT, price_config, refund_policy
from src.pipeline import Scoped, build_shortlist, scope_path


def _env(autoescape: bool) -> Environment:
    return Environment(
        loader=FileSystemLoader(ROOT / "templates"),
        autoescape=select_autoescape(["html"]) if autoescape else False,
    )


def _cell(value: object) -> str:
    return str(value).replace("|", "/").replace("\n", " ")


def render_context(scoped: Scoped, gaps: list[dict]) -> dict:
    prices = price_config()
    shortlist = build_shortlist(scoped)
    rows = []
    for index, row in enumerate(scoped.ranked, start=1):
        rec = scoped.recommendations[row.process]
        cost = scoped.costs[row.process]
        rows.append(
            {
                "rank": index,
                "process": _cell(row.process),
                "team": _cell(row.team),
                "hours": f"{row.monthly_hours}",
                "payoff": f"{row.payoff}",
                "effort": f"{row.effort}",
                "net": f"{row.net}",
                "pattern": rec.pattern,
                "reason": rec.reason,
                "risk": rec.risk,
                "human": rec.human_in_the_loop,
                "usd": f"{cost['usd']}",
                "sources": ", ".join(row.sources) or "none named",
                "rule": rec.rule,
                "worth_building": row.net > 0,
                "error_note": "Error rate was blank and was counted as 0 for the score." if row.error_missing else "",
            }
        )
    by_pattern: dict[str, list] = {}
    for item in rows:
        by_pattern.setdefault(item["pattern"], []).append(item)
    agent_rows = [item for item in rows if item["pattern"] == "llm_agent"]
    return {
        "company": "Pebblecart",
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "rows": rows,
        "shortlist": [item for item in rows if item["process"] in {row.process for row in shortlist}],
        "leave": by_pattern.get("dont_automate", []),
        "rules": [item for item in by_pattern.get("rules", []) if item["worth_building"]],
        "agents": [item for item in agent_rows if item["worth_building"]],
        "rags": [item for item in by_pattern.get("rag", []) if item["worth_building"]],
        "ml": [item for item in by_pattern.get("classic_ml", []) if item["worth_building"]],
        "held": [item for item in rows if item["pattern"] != "dont_automate" and not item["worth_building"]],
        "top_agent": agent_rows[0] if agent_rows else None,
        "exceptions": [
            {"source_row": row.source_row, "reasons": ", ".join(row.reasons), "process": _cell(row.raw.get("process", ""))}
            for row in scoped.inventory.exceptions
        ],
        "gaps": gaps,
        "prices": prices,
        "policy_as_of": refund_policy()["as_of"],
        "parsed_count": len(scoped.inventory.parsed),
        "exception_count": len(scoped.inventory.exceptions),
    }


def write_decision(inventory_path: Path, out_dir: Path, gaps: list[dict] | None = None) -> tuple[Path, Path]:
    scoped = scope_path(inventory_path)
    context = render_context(scoped, gaps or [])
    out_dir.mkdir(parents=True, exist_ok=True)
    markdown = _env(False).get_template("decision.md.j2").render(**context)
    html = _env(True).get_template("decision.html.j2").render(**context)
    md_path = out_dir / "decision.md"
    html_path = out_dir / "decision.html"
    md_path.write_text(markdown, encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")
    return md_path, html_path
