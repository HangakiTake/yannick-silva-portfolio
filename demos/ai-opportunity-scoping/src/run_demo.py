"""Build the sample inventory and write the decision note."""

from __future__ import annotations

import json

from src.build_inventory import build
from src.decision import write_decision
from src.paths import ROOT
from src.pipeline import scope_path


def main() -> None:
    xlsx, _csv = build()
    scoped = scope_path(xlsx)
    gold = json.loads((ROOT / "data" / "gold_architecture.json").read_text(encoding="utf-8"))
    gaps = []
    for label in gold["labels"]:
        got = scoped.recommendations[label["process"]].pattern
        if got != label["pattern"]:
            gaps.append(
                {
                    "process": label["process"],
                    "pattern": label["pattern"],
                    "rubric_will_say": got,
                    "why_it_differs": label.get("why_it_differs", ""),
                }
            )
    md_path, html_path = write_decision(xlsx, ROOT / "out", gaps)
    top = scoped.ranked[0]
    print(f"top: {top.process} ({scoped.recommendations[top.process].pattern}, net {top.net})")
    print(md_path)
    print(html_path)


if __name__ == "__main__":
    main()
