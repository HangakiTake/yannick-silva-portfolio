"""Rank tasks by hours saved against effort and risk.

score = w_hours * hours_saved - w_effort * effort - w_risk * risk
hours_saved = frequency_per_month * minutes_per_run / 60 * capture[tool]

Weights and capture rates are read from config/scoring.json. The same inputs
always produce the same order. Ties break on the task id.
"""

from __future__ import annotations

import json

import pandas as pd

from .paths import CONFIG

DEFAULTS = json.loads((CONFIG / "scoring.json").read_text(encoding="utf-8"))


def _effort(task: dict, points: dict) -> int:
    effort = int(points["base"])
    if len(task.get("tools") or []) >= 2:
        effort += int(points["extra_tool"])
    if task.get("customer_facing"):
        effort += int(points["customer_facing"])
    if task.get("work_type") in {"text_read", "text_draft", "multi_step"}:
        effort += int(points["text_or_multi"])
    if task.get("work_type") in {"judgment_review", "tax_or_filing"}:
        effort += int(points["judgment_or_tax"])
    return min(int(points["cap"]), effort)


def _risk(task: dict, points: dict) -> int:
    risk = 0
    if task.get("customer_facing"):
        risk += int(points["customer_facing"])
    if task.get("work_type") == "tax_or_filing":
        risk += int(points["tax_or_filing"])
    if task.get("requires_approval"):
        risk += int(points["approval"])
    return min(int(points["cap"]), risk)


def score_components(hours_saved: float, effort: float, risk: float, weights: dict) -> float:
    return (
        float(weights["hours"]) * float(hours_saved)
        - float(weights["effort"]) * float(effort)
        - float(weights["risk"]) * float(risk)
    )


def rank(tasks: list[dict], config: dict | None = None) -> pd.DataFrame:
    cfg = config or DEFAULTS
    weights = cfg["weights"]
    capture = cfg["capture"]
    rows = []
    for task in tasks:
        hours = round(float(task["frequency_per_month"]) * float(task["minutes_per_run"]) / 60.0, 6)
        rate = float(capture[task["tool"]])
        saved = round(hours * rate, 6)
        effort = _effort(task, cfg["effort_points"])
        risk = _risk(task, cfg["risk_points"])
        score = round(score_components(saved, effort, risk, weights), 6)
        rows.append(
            {
                **task,
                "hours_per_month": round(hours, 6),
                "capture": rate,
                "hours_saved": round(saved, 6),
                "effort": effort,
                "risk": risk,
                "w_hours": weights["hours"],
                "w_effort": weights["effort"],
                "w_risk": weights["risk"],
                "score": score,
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(["score", "id"], ascending=[False, True], kind="mergesort").reset_index(drop=True)
