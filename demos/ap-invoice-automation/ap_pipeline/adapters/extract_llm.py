"""LLM invoice extractor (OpenAI or Anthropic structured output).

UNTESTED: accuracy has not been measured. This module returns fields only.
The deterministic validator still decides whether a bill is created.
No network call is made when the PDF has no text layer.
"""

from __future__ import annotations

import json
from decimal import Decimal

from ap_pipeline.adapters.pdf_text import extract_pdf_text
from ap_pipeline.errors import CredentialsNotConfigured, PipelineError
from ap_pipeline.models import InvoiceFields
from ap_pipeline.money import parse_money

LIVE_API_TESTED = False
UNTESTED_NOTICE = (
    "UNTESTED: the LLM extractor has not been run against OpenAI or Anthropic. "
    "LLM-path field accuracy is not measured until a key is available and an eval is requested."
)

INVOICE_JSON_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "vendor_name": {"type": ["string", "null"]},
        "invoice_number": {"type": ["string", "null"]},
        "po_number": {"type": ["string", "null"]},
        "invoice_date": {"type": ["string", "null"]},
        "subtotal": {"type": ["string", "null"]},
        "tax": {"type": ["string", "null"]},
        "total": {"type": ["string", "null"]},
        "currency": {"type": ["string", "null"]},
    },
    "required": [
        "vendor_name",
        "invoice_number",
        "po_number",
        "invoice_date",
        "subtotal",
        "tax",
        "total",
        "currency",
    ],
}

_SYSTEM = (
    "Extract invoice fields from the text. Return only the structured fields. "
    "Use null when a field is not printed. Do not calculate a missing total. "
    "Keep the invoice date as printed. Money values are strings with a decimal point."
)


class LlmExtractor:
    name = "llm"
    live_tested = LIVE_API_TESTED

    def __init__(self, *, provider: str, api_key: str, model: str, session=None) -> None:
        if provider not in {"openai", "anthropic"}:
            raise PipelineError(f"Unknown LLM provider {provider!r}")
        if not api_key:
            raise CredentialsNotConfigured(
                "LLM extractor requires OPENAI_API_KEY or ANTHROPIC_API_KEY. " + UNTESTED_NOTICE
            )
        self.provider = provider
        self.api_key = api_key
        self.model = model
        self._session = session if session is not None else _default_session()
        self.calls = 0

    def extract(self, pdf_bytes: bytes) -> InvoiceFields:
        try:
            text = extract_pdf_text(pdf_bytes)
        except Exception:  # noqa: BLE001 — pdf libraries raise many types for a bad file
            return InvoiceFields(unreadable=True)
        if not text.strip():
            return InvoiceFields(no_text_layer=True)
        self.calls += 1
        payload = self._complete(text)
        return ground_amounts(fields_from_mapping(payload), text)

    def _complete(self, text: str) -> dict:
        if self.provider == "openai":
            return self._openai(text)
        return self._anthropic(text)

    def _openai(self, text: str) -> dict:
        response = self._session.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": text[:20000]},
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "invoice_fields", "strict": True, "schema": INVOICE_JSON_SCHEMA},
                },
            },
            timeout=60,
        )
        if response.status_code >= 400:
            raise PipelineError(f"OpenAI request failed with HTTP {response.status_code}")
        content = response.json()["choices"][0]["message"]["content"]
        return json.loads(content)

    def _anthropic(self, text: str) -> dict:
        response = self._session.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": 1024,
                "system": _SYSTEM,
                "tools": [
                    {
                        "name": "record_invoice_fields",
                        "description": "Record the invoice fields that were printed.",
                        "input_schema": INVOICE_JSON_SCHEMA,
                    }
                ],
                "tool_choice": {"type": "tool", "name": "record_invoice_fields"},
                "messages": [{"role": "user", "content": text[:20000]}],
            },
            timeout=60,
        )
        if response.status_code >= 400:
            raise PipelineError(f"Anthropic request failed with HTTP {response.status_code}")
        for block in response.json().get("content", []):
            if block.get("type") == "tool_use" and block.get("name") == "record_invoice_fields":
                return block["input"]
        raise PipelineError("Anthropic response did not include record_invoice_fields")


def fields_from_mapping(payload: dict) -> InvoiceFields:
    """Parse a model payload with the same money and blank-token rules as the rules extractor."""
    return InvoiceFields(
        vendor_name=_text(payload.get("vendor_name")),
        invoice_number=_text(payload.get("invoice_number")),
        po_number=_text(payload.get("po_number")),
        invoice_date=_text(payload.get("invoice_date")),
        subtotal=_money(payload.get("subtotal")),
        tax=_money(payload.get("tax")),
        total=_money(payload.get("total")),
        currency=_currency(payload.get("currency")),
    )


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _money(value: object) -> Decimal | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"))
    if isinstance(value, int):
        return Decimal(value).quantize(Decimal("0.01"))
    if isinstance(value, float):
        raw = Decimal(str(value))
        rounded = raw.quantize(Decimal("0.01"))
        if abs(raw - rounded) > Decimal("0.0000001"):
            return None
        return rounded
    return parse_money(str(value))


def ground_amounts(fields: InvoiceFields, text: str) -> InvoiceFields:
    """Drop money the model returned that is not printed in the PDF text."""
    compact = _compact_text(text)
    for name in ("subtotal", "tax", "total"):
        amount = getattr(fields, name)
        if amount is not None and format(amount, "f") not in compact:
            setattr(fields, name, None)
    return fields


def _compact_text(text: str) -> str:
    cleaned = text.replace("\u202f", "").replace("\u00a0", "").replace(" ", "").replace(",", "").replace("'", "")
    return cleaned.replace("’", "")


def _currency(value: object) -> str | None:
    text = _text(value)
    return None if text is None else text.upper()


def _default_session():
    import requests

    return requests.Session()
