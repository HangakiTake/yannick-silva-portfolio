"""Shortlist page. Evidence and questions are redacted before they are rendered."""

from __future__ import annotations

import json

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .paths import CONFIG, TEMPLATES
from .redact import redact
from .score import DEFAULTS


def render_shortlist(frame, questions, redaction_counts) -> str:
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html"]))
    rows = frame.to_dict(orient="records")
    safe_questions = [
        {"quote": redact(q.quote).text, "reason": q.reason} for q in questions
    ]
    top = rows[0]
    return env.get_template("shortlist.html.j2").render(
        rows=rows,
        questions=safe_questions,
        counts=redaction_counts,
        formula=DEFAULTS["formula"],
        weights=DEFAULTS["weights"],
        top=top,
    )


def load_prompt() -> str:
    return json.loads((CONFIG / "prompts.json").read_text(encoding="utf-8"))["inquiry_system"]
