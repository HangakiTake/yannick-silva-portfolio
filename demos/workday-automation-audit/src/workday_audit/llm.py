"""Classify a redacted inquiry. Mock mode is deterministic and needs no key.

Live mode calls Claude only when ANTHROPIC_API_KEY is set. With no key the
result is not_run. This module does not redact; the runner does that first.
"""

from __future__ import annotations

import json
import os
import re

from .normalize import normalize

_CATEGORIES = [
    ("spam", re.compile(r"unsubscribe|seo service|guest post|buy backlinks|limited time offer")),
    ("payment_notice", re.compile(r"payment has been sent|payment sent|remittance|\bach\b|wire sent|paid the invoice|transferred")),
    ("document_request", re.compile(r"receipt|resend|p&l|p and l|w-9|w9|send me the|statement copy|profit and loss")),
    ("invoice_status", re.compile(r"invoice|overdue|unpaid")),
    ("scheduling", re.compile(r"\bmeet\b|schedule|are you free|hop on a call")),
    ("new_lead", re.compile(r"quote|how much|bookkeeping|take on|proposal|your services|monthly books")),
]
_URGENCY = re.compile(r"\basap\b|(?<!not )(?<!nothing )\burgent\b|\btoday\b|\beod\b|right away|as soon as")
_SERVICE = [
    ("payroll", re.compile(r"\bpayroll\b")),
    ("catch_up", re.compile(r"catch[- ]up|behind on|clean-?up|backlog")),
    ("bookkeeping", re.compile(r"bookkeeping|\bbooks\b|monthly")),
]


def classify_text(text: str) -> dict:
    norm = normalize(text)
    category = "other"
    for name, pattern in _CATEGORIES:
        if pattern.search(norm):
            category = name
            break
    urgency = "high" if _URGENCY.search(norm) else "normal"
    service = "general"
    for name, pattern in _SERVICE:
        if pattern.search(norm):
            service = name
            break
    draft_body = (
        "DRAFT — not sent. A person must approve this before it goes to the customer.\n"
        f"Thanks for the note. I have it down as {category.replace('_', ' ')} "
        f"({service}, {urgency}). I will reply once I have read it."
    )
    return {
        "category": category,
        "urgency": urgency,
        "service": service,
        "draft_subject": f"Re: {category.replace('_', ' ')}",
        "draft_body": draft_body,
    }


class MockLLM:
    """Deterministic stand-in. It only sees the payload it is given."""

    name = "mock"

    def __init__(self) -> None:
        self.payloads: list[dict] = []

    def complete(self, payload: dict) -> dict:
        self.payloads.append(payload)
        return classify_text(payload.get("user", ""))


class AnthropicLLM:
    name = "anthropic"

    def __init__(self, client, model: str) -> None:
        self.client = client
        self.model = model
        self.payloads: list[dict] = []

    def complete(self, payload: dict) -> dict:
        self.payloads.append({"system": payload.get("system", ""), "user": payload.get("user", "")})
        message = self.client.messages.create(
            model=self.model,
            max_tokens=800,
            system=payload.get("system", ""),
            messages=[{"role": "user", "content": payload.get("user", "")}],
        )
        raw = "".join(getattr(block, "text", "") for block in message.content)
        start, end = raw.find("{"), raw.rfind("}")
        data = json.loads(raw[start : end + 1]) if start >= 0 else {}
        base = classify_text(payload.get("user", ""))
        for key in ("category", "urgency", "service", "draft_subject", "draft_body"):
            if data.get(key):
                base[key] = data[key]
        if "not sent" not in base["draft_body"].lower():
            base["draft_body"] = "DRAFT — not sent. A person must approve this.\n" + base["draft_body"]
        return base


def make_llm(mode: str = "mock"):
    """Return (llm, status). Live without a key returns (None, 'not_run')."""
    if mode == "live":
        key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not key:
            return None, "not_run"
        import anthropic

        model = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-5-5")
        return AnthropicLLM(anthropic.Anthropic(api_key=key), model), "live"
    return MockLLM(), "mock"
