"""Payoff minus a fraction of effort. See docs/scoring.md."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pandas as pd

from src.inventory import ParsedRow
from src.paths import scoring_config
from src.phrases import first_phrase, phrase_groups, scrub
from src.units import q


@dataclass
class ScoredRow:
    source_row: int
    process: str
    team: str
    notes: str
    sources: list[str]
    sources_raw: str
    monthly_volume: Decimal
    minutes_per_item: Decimal
    error_rate: Decimal | None
    error_missing: bool
    monthly_hours: Decimal
    hours_score: Decimal
    error_score: Decimal
    payoff: Decimal
    n_sources: int
    source_score: Decimal
    effort_tag: Decimal
    effort_reason: str
    effort: Decimal
    net: Decimal
    weights: dict


def effort_tag(process: str, notes: str, cfg: dict | None = None) -> tuple[Decimal, str]:
    cfg = cfg or scoring_config()
    groups = phrase_groups()
    original = f"{process} {notes}".lower()
    cleaned = scrub(original)
    judgment = first_phrase(cleaned, groups["judgment"])
    structured = first_phrase(original, groups["structured"])
    if judgment:
        return Decimal(cfg["effort_high"]), f"judgment:{judgment}"
    if structured:
        return Decimal(cfg["effort_low"]), f"structured:{structured}"
    return Decimal(cfg["effort_mid"]), "neither"


def net_of(payoff: Decimal, effort: Decimal, w_effort: object) -> Decimal:
    return q(Decimal(payoff) - Decimal(str(w_effort)) * Decimal(effort))


def score_row(row: ParsedRow, cfg: dict | None = None, tag: tuple[Decimal, str] | None = None) -> ScoredRow:
    cfg = cfg or scoring_config()
    volume = Decimal(row.monthly_volume)
    minutes = Decimal(row.minutes_per_item)
    monthly_hours = q(volume * minutes / Decimal(60))
    hours_score = q(min(monthly_hours / Decimal(str(cfg["hours_cap"])), Decimal(1)) * 100)
    if row.error_rate is None:
        used_error = Decimal(str(cfg["missing_error_rate_as"]))
        error_missing = True
    else:
        used_error = Decimal(row.error_rate)
        error_missing = row.error_missing
    error_score = q(min(used_error / Decimal(str(cfg["error_cap"])), Decimal(1)) * 100)
    payoff = q(Decimal(str(cfg["w_hours"])) * hours_score + Decimal(str(cfg["w_error"])) * error_score)
    n_sources = len(row.sources)
    source_score = q(min(Decimal(n_sources) / Decimal(str(cfg["source_cap"])), Decimal(1)) * 100)
    if tag is None:
        tag_value, tag_reason = effort_tag(row.process, row.notes, cfg)
    else:
        tag_value, tag_reason = tag
    effort = q(Decimal(str(cfg["w_sources"])) * source_score + Decimal(str(cfg["w_unstructured"])) * tag_value)
    net = net_of(payoff, effort, cfg["w_effort"])
    return ScoredRow(
        source_row=row.source_row,
        process=row.process,
        team=row.team,
        notes=row.notes,
        sources=list(row.sources),
        sources_raw=row.sources_raw,
        monthly_volume=volume,
        minutes_per_item=minutes,
        error_rate=None if row.error_rate is None else Decimal(row.error_rate),
        error_missing=error_missing,
        monthly_hours=monthly_hours,
        hours_score=hours_score,
        error_score=error_score,
        payoff=payoff,
        n_sources=n_sources,
        source_score=source_score,
        effort_tag=tag_value,
        effort_reason=tag_reason,
        effort=effort,
        net=net,
        weights={
            "w_hours": cfg["w_hours"],
            "w_error": cfg["w_error"],
            "w_sources": cfg["w_sources"],
            "w_unstructured": cfg["w_unstructured"],
            "w_effort": cfg["w_effort"],
        },
    )


def rank_rows(rows: list[ScoredRow]) -> list[ScoredRow]:
    """Sort in Python so Decimal order stays exact, and check pandas agrees."""
    ordered = sorted(rows, key=lambda row: (-row.net, -row.payoff, row.process))
    if rows:
        frame = pd.DataFrame(
            {
                "process": [row.process for row in rows],
                "net": [float(row.net) for row in rows],
                "payoff": [float(row.payoff) for row in rows],
            }
        )
        pandas_order = frame.sort_values(
            ["net", "payoff", "process"], ascending=[False, False, True], kind="mergesort"
        )["process"].tolist()
        if pandas_order != [row.process for row in ordered]:
            raise RuntimeError("pandas rank and decimal rank disagreed")
    return ordered
