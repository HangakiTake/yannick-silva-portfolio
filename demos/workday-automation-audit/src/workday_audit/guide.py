"""One-page guide for the top pick, rendered from the workflow and the cost config."""

from __future__ import annotations

import json

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .cost import monthly_cost
from .paths import CONFIG, TEMPLATES
from .workflow import build_workflow

_PROMPT = json.loads((CONFIG / "prompts.json").read_text(encoding="utf-8"))


def render_guide(top: dict, kind: str = "html") -> str:
    workflow = build_workflow()
    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("guide.html.j2" if kind == "html" else "guide.md.j2")
    return template.render(
        top=top,
        nodes=workflow["nodes"],
        prompt_help=_PROMPT["where_to_edit"],
        prompt_start=_PROMPT["inquiry_system"][:80],
        cost=monthly_cost(),
    )
