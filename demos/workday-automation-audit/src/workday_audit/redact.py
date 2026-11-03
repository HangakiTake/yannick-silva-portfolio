"""Replace personal data with placeholders before any text is sent to a model.

Rules live in config/redaction.json. The same rules are emitted as JavaScript
for the n8n Code node, so the workflow does not carry a second hand-written copy.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .paths import CONFIG

_CONFIG = json.loads((CONFIG / "redaction.json").read_text(encoding="utf-8"))
STOP = {w.casefold() for w in _CONFIG["stoplist"]}
PATTERNS: dict[str, list[re.Pattern[str]]] = {
    kind: [re.compile(p) for p in pats] for kind, pats in _CONFIG["patterns"].items()
}
NAME_PAIR = re.compile(_CONFIG["name_pair"])
KIND_ORDER = ["email", "phone", "amount", "address", "name_title", "name_greeting", "name_pair"]
PRIORITY = {kind: i for i, kind in enumerate(KIND_ORDER)}


@dataclass
class Span:
    start: int
    end: int
    kind: str

    @property
    def length(self) -> int:
        return self.end - self.start


@dataclass
class Redaction:
    text: str
    mapping: dict[str, str]
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def _name_kind(kind: str) -> str:
    if kind.startswith("name"):
        return "name"
    return kind


def _pair_ok(text: str, start: int, end: int) -> bool:
    words = re.findall(r"[A-Za-z][A-Za-z'\-]*", text[start:end])
    if len(words) < 2:
        return False
    return all(w.casefold() not in STOP for w in words)


def find_spans(text: str) -> list[Span]:
    found: list[Span] = []
    for kind, regs in PATTERNS.items():
        for reg in regs:
            for match in reg.finditer(text):
                if match.end() > match.start():
                    found.append(Span(match.start(), match.end(), kind))
    for match in NAME_PAIR.finditer(text):
        if _pair_ok(text, match.start(), match.end()):
            found.append(Span(match.start(), match.end(), "name_pair"))
    found.sort(key=lambda s: (PRIORITY.get(s.kind, 9), -s.length, s.start))
    taken: list[Span] = []
    for span in found:
        if any(not (span.end <= prev.start or span.start >= prev.end) for prev in taken):
            continue
        taken.append(span)
    taken.sort(key=lambda s: s.start)
    return taken


def redact(text: str) -> Redaction:
    spans = find_spans(text)
    parts: list[str] = []
    mapping: dict[str, str] = {}
    counts: dict[str, int] = {}
    cursor = 0
    for span in spans:
        parts.append(text[cursor:span.start])
        kind = _name_kind(span.kind)
        counts[kind] = counts.get(kind, 0) + 1
        token = f"[{kind.upper()}_{counts[kind]}]"
        mapping[token] = text[span.start:span.end]
        parts.append(token)
        cursor = span.end
    parts.append(text[cursor:])
    return Redaction("".join(parts), mapping, counts)


def restore(text: str, mapping: dict[str, str]) -> str:
    for token in sorted(mapping, key=len, reverse=True):
        text = text.replace(token, mapping[token])
    return text


def javascript_redactor() -> str:
    """JavaScript port driven by the same pattern list and stoplist."""
    payload = {
        "stoplist": sorted(STOP),
        "patterns": {kind: [p.pattern for p in regs] for kind, regs in PATTERNS.items()},
        "namePair": NAME_PAIR.pattern,
        "order": KIND_ORDER,
    }
    return (
        "function redact(text) {\n"
        "  const cfg = "
        + json.dumps(payload)
        + ";\n"
        + _JS_BODY
    )


_JS_BODY = r"""
  const priority = {};
  cfg.order.forEach((k, i) => { priority[k] = i; });
  const stop = new Set(cfg.stoplist);
  function collect(reSrc, kind, spans) {
    const re = new RegExp(reSrc, 'g');
    let m;
    while ((m = re.exec(text)) !== null) {
      if (m[0].length === 0) { re.lastIndex++; continue; }
      spans.push({ start: m.index, end: m.index + m[0].length, kind });
    }
  }
  const spans = [];
  Object.keys(cfg.patterns).forEach(kind => {
    cfg.patterns[kind].forEach(src => collect(src, kind, spans));
  });
  collect(cfg.namePair, 'name_pair', spans);
  const kept = [];
  spans.filter(s => {
    if (s.kind !== 'name_pair') return true;
    const words = (text.slice(s.start, s.end).match(/[A-Za-z][A-Za-z'\-]*/g) || []);
    return words.length >= 2 && words.every(w => !stop.has(w.toLowerCase()));
  }).sort((a, b) => (priority[a.kind] - priority[b.kind]) || ((b.end - b.start) - (a.end - a.start)) || (a.start - b.start))
    .forEach(span => {
      if (kept.some(prev => !(span.end <= prev.start || span.start >= prev.end))) return;
      kept.push(span);
    });
  kept.sort((a, b) => a.start - b.start);
  let out = '';
  let cursor = 0;
  const mapping = {};
  const counts = {};
  kept.forEach(span => {
    out += text.slice(cursor, span.start);
    const kind = span.kind.startsWith('name') ? 'name' : span.kind;
    counts[kind] = (counts[kind] || 0) + 1;
    const token = '[' + kind.toUpperCase() + '_' + counts[kind] + ']';
    mapping[token] = text.slice(span.start, span.end);
    out += token;
    cursor = span.end;
  });
  out += text.slice(cursor);
  return { text: out, mapping, counts };
}
"""
