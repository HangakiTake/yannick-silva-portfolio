"""Append-only JSONL audit log. One object per line."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class AuditLog:
    def __init__(self, path: Path | str, run_id: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id
        self.path.touch(exist_ok=True)

    def record(self, **fields):
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            **fields,
        }
        if row.get("verified") is None:
            row.pop("verified", None)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def read(self) -> list[dict]:
        lines = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                lines.append(json.loads(line))
        return lines
