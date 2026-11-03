"""Turn a messy description of a week into tasks, questions, and asides.

Nothing is dropped in silence. A clause with a frequency and a duration becomes
a task. A clause that looks like work but is missing either one becomes a
question. One-off facts and chatter are kept on the trace so they can be seen.
"""

from __future__ import annotations

import json
import re
import statistics
from dataclasses import dataclass, field

from .normalize import normalize
from .paths import CONFIG

_FREQ = json.loads((CONFIG / "frequency.json").read_text(encoding="utf-8"))
_WEEKS = float(_FREQ["weeks_per_month"])
_PHRASES: list[tuple[re.Pattern[str], float]] = []
for row in _FREQ["phrases"]:
    if "per_month" in row:
        value = float(row["per_month"])
    else:
        value = float(row["times_per_week"]) * _WEEKS
    _PHRASES.append((re.compile(row["pattern"]), value))

_TOPICS = json.loads((CONFIG / "topics.json").read_text(encoding="utf-8"))
_TOPIC_RES: list[tuple[str, str, re.Pattern[str]]] = []
for topic in _TOPICS:
    joined = "|".join(topic["patterns"])
    _TOPIC_RES.append((topic["id"], topic["summary"], re.compile(joined)))

_MINUTE_RANGE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:-|–|to)\s*(\d+(?:\.\d+)?)\s*(?:min|mins|minutes)\b"
)
_HOURS = re.compile(r"(\d+(?:\.\d+)?)\s*(?:hours?|hrs)\b")
_AN_HOUR = re.compile(r"\ban hour\b")
_HALF = re.compile(r"\bhalf an (?:hour|hr)\b")
_MINS = re.compile(r"(\d+(?:\.\d+)?)\s*(?:min|mins|minutes)\b")
_UNCERTAIN = re.compile(
    r"\b(not sure|no idea|i forget|idk|it varies)\b|payroll is a mess|\bportal\b"
)
_DURATION_ONLY = re.compile(r"^(that|this|it|takes|take)\b")
_VERBS = re.compile(
    r"\b(go through|draft|copy|code|coding|type|check|answer|chase|update|back up|"
    r"backup|reconcile|refresh|match|follow up|decide|move|enter|transcribe|write|"
    r"prepare|set up|look for|review|pull|rename|file|log|onboard|export|text|send)\b"
)
_CUSTOMER = re.compile(
    r"replies|chase|appointment reminder|did you get|proposals?|checklist email|"
    r"client report|invoice wording|invoice description|\bcalls?\b"
)
_TOOLS = [
    ("gmail", re.compile(r"\b(e-?mails?|inbox)\b")),
    ("google_sheets", re.compile(r"google sheet|the sheet|time sheet|cashflow sheet|pricing sheet|spreadsheet")),
    ("xero", re.compile(r"\bxero\b")),
    ("square", re.compile(r"\bsquare\b")),
    ("whatsapp", re.compile(r"\bwhatsapp\b")),
    ("calendar", re.compile(r"\bcalendar\b")),
    ("drive", re.compile(r"\bdrive\b")),
    ("pdf", re.compile(r"\bpdfs?\b")),
    ("phone", re.compile(r"\b(voicemails?|phone)\b")),
]


@dataclass
class ClauseTask:
    topic: str
    summary: str
    frequency: float
    minutes: float
    original: str
    tools: list[str]
    customer_facing: bool


@dataclass
class Question:
    quote: str
    reason: str


@dataclass
class Trace:
    text: str
    disposition: str
    detail: str = ""


@dataclass
class Extraction:
    tasks: list[dict] = field(default_factory=list)
    questions: list[Question] = field(default_factory=list)
    trace: list[Trace] = field(default_factory=list)


def find_topic(norm: str) -> tuple[str, str] | None:
    for topic_id, summary, pattern in _TOPIC_RES:
        if pattern.search(norm):
            return topic_id, summary
    return None


def find_frequency(norm: str) -> float | None:
    for pattern, value in _PHRASES:
        match = pattern.search(norm)
        if not match:
            continue
        prefix = norm[max(0, match.start() - 24) : match.start()]
        if re.search(r"\b(not|never)\b(?:\s+\w+){0,2}\s*$", prefix):
            continue
        return value
    return None


def minute_values(norm: str) -> list[float]:
    values: list[float] = []
    working = _HALF.sub(" ", norm)
    if working != norm:
        values.append(30.0)
    for match in _MINUTE_RANGE.finditer(working):
        values.append((float(match.group(1)) + float(match.group(2))) / 2)
    stripped = _MINUTE_RANGE.sub(" ", working)
    for match in _HOURS.finditer(stripped):
        values.append(float(match.group(1)) * 60)
    stripped = _HOURS.sub(" ", stripped)
    if _AN_HOUR.search(stripped):
        values.append(60.0)
        stripped = _AN_HOUR.sub(" ", stripped)
    for match in _MINS.finditer(stripped):
        values.append(float(match.group(1)))
    return values


def contradictory_duration(norm: str) -> bool:
    values = minute_values(norm)
    return len(values) >= 2 and max(values) >= min(values) * 3


def find_minutes(norm: str) -> float | None:
    if contradictory_duration(norm):
        return None
    values = minute_values(norm)
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return float(statistics.median(values))


def _tools(norm: str) -> list[str]:
    return [name for name, pattern in _TOOLS if pattern.search(norm)]


def _has_minutes(norm: str) -> bool:
    return find_minutes(norm) is not None


def _split_and(sentence: str) -> list[str]:
    """Split only when each side is its own task. '10 minutes and 3 hours' stays one clause."""
    parts = re.split(r"\s+and\s+", sentence, flags=re.IGNORECASE)
    if len(parts) < 2:
        return [sentence]
    if not all(_has_minutes(normalize(part)) for part in parts):
        return [sentence]

    def own_task(part: str) -> bool:
        norm = normalize(part)
        return find_topic(norm) is not None or _VERBS.search(norm) is not None

    if all(own_task(part) for part in parts):
        return [part.strip() for part in parts if part.strip()]
    return [sentence]


def _clauses(text: str) -> list[str]:
    clauses: list[str] = []
    for line in text.splitlines():
        raw = re.sub(r"^[-*•]\s*", "", line.strip())
        if not raw:
            continue
        pieces = re.split(r"(?<=[.!])\s+", raw)
        for piece in pieces:
            piece = piece.strip()
            if piece:
                clauses.extend(_split_and(piece))
    merged: list[str] = []
    for clause in clauses:
        norm = normalize(clause)
        if merged and _DURATION_ONLY.match(norm) and _has_minutes(norm) and not find_topic(norm):
            merged[-1] = merged[-1].rstrip() + " " + clause
        else:
            merged.append(clause)
    out: list[str] = []
    index = 0
    while index < len(merged):
        norm = normalize(merged[index])
        header = (
            find_topic(norm) is not None
            and not _has_minutes(norm)
            and len(merged[index].split()) <= 8
        )
        if header and index + 1 < len(merged) and _has_minutes(normalize(merged[index + 1])):
            out.append(merged[index].rstrip() + " " + merged[index + 1])
            index += 2
        else:
            out.append(merged[index])
            index += 1
    return out


def _slug(norm: str) -> str:
    words = re.findall(r"[a-z0-9]{3,}", norm)
    stop = {"the", "and", "for", "with", "about", "every", "once", "that", "this", "into", "from"}
    kept = [w for w in words if w not in stop][:4]
    return "unlisted-" + ("-".join(kept) or "task")


def extract(text: str) -> Extraction:
    result = Extraction()
    pending: list[ClauseTask] = []
    for clause in _clauses(text):
        norm = normalize(clause)
        topic = find_topic(norm)
        frequency = find_frequency(norm)
        minutes = find_minutes(norm)
        uncertain = _UNCERTAIN.search(norm) is not None
        looks_like_work = topic is not None or _VERBS.search(norm) is not None
        if contradictory_duration(norm):
            result.questions.append(Question(clause, "Two durations are too far apart, so neither one is used."))
            result.trace.append(Trace(clause, "question", "contradictory-duration"))
            continue
        if uncertain and (frequency is None or minutes is None):
            result.questions.append(Question(clause, "Frequency or duration is not stated, so it is not scored."))
            result.trace.append(Trace(clause, "question", "uncertain"))
            continue
        if minutes is None and frequency is not None:
            result.questions.append(Question(clause, "No duration I can use. A range or a single number is needed."))
            result.trace.append(Trace(clause, "question", "no-minutes"))
            continue
        if frequency is None and minutes is not None:
            result.questions.append(Question(clause, "No repeat rate I can use. It is not scored."))
            result.trace.append(Trace(clause, "question", "no-frequency"))
            continue
        if minutes is None and frequency is None and looks_like_work:
            if len(clause.split()) < 5:
                result.trace.append(Trace(clause, "chatter", "short"))
            else:
                result.questions.append(Question(clause, "This looks like work, but there is no repeat rate or duration."))
                result.trace.append(Trace(clause, "question", "incomplete"))
            continue
        if frequency is not None and minutes is not None:
            # A frequency and a duration is enough. Unknown topics stay provisional.
            if topic:
                topic_id, summary = topic
                provisional = False
            else:
                topic_id, summary = _slug(norm), clause.strip()
                provisional = True
            pending.append(
                ClauseTask(
                    topic=topic_id,
                    summary=summary,
                    frequency=frequency,
                    minutes=minutes,
                    original=clause,
                    tools=_tools(norm),
                    customer_facing=_CUSTOMER.search(norm) is not None,
                )
            )
            if provisional:
                result.questions.append(
                    Question(clause, "Not on the usual bookkeeping list. Confirm the name before you build anything.")
                )
                result.trace.append(Trace(clause, "task", "provisional"))
            else:
                result.trace.append(Trace(clause, "task", topic_id))
            continue
        if re.search(r"@|[$£€]|\b\d{3}[-.)]\d{3}", clause):
            result.trace.append(Trace(clause, "aside", "personal-fact"))
        else:
            result.trace.append(Trace(clause, "chatter", ""))
    grouped: dict[str, list[ClauseTask]] = {}
    order: list[str] = []
    for item in pending:
        if item.topic not in grouped:
            grouped[item.topic] = []
            order.append(item.topic)
        grouped[item.topic].append(item)
    for topic_id in order:
        items = grouped[topic_id]
        frequencies = [item.frequency for item in items]
        minutes = [item.minutes for item in items]
        tools: list[str] = []
        for item in items:
            for tool in item.tools:
                if tool not in tools:
                    tools.append(tool)
        result.tasks.append(
            {
                "id": topic_id,
                "summary": items[0].summary,
                "frequency_per_month": float(statistics.median(frequencies)),
                "minutes_per_run": float(statistics.median(minutes)),
                "tools": tools,
                "customer_facing": any(item.customer_facing for item in items),
                "evidence": [item.original for item in items],
                "provisional": topic_id.startswith("unlisted-"),
            }
        )
    return result
