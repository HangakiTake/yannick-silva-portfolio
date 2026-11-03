"""Rules-only invoice extractor.

The last labelled value on the last page wins, except tax: the latest value of
each distinct tax label is kept and those labels are summed. A repeated GST
line on page 2 replaces page 1; a TPS line plus a TVQ line are added.

This extractor does not infer a missing total from subtotal plus tax.
"""

from __future__ import annotations

import re

from ap_pipeline.adapters.pdf_text import extract_pdf_text
from ap_pipeline.models import InvoiceFields
from ap_pipeline.money import parse_money
from ap_pipeline.textnorm import clean_text, normalize_label

_INVOICE_LABELS = {
    "invoice number",
    "invoice no",
    "invoice",
    "inv",
    "inv no",
    "numero de facture",
    "no de facture",
    "facture no",
    "facture",
}
_PO_LABELS = {
    "po",
    "po number",
    "po no",
    "p o",
    "p o number",
    "purchase order",
    "bon de commande",
}
_DATE_LABELS = {"invoice date", "date", "date de facture"}
_VENDOR_LABELS = {"vendor", "vendor name", "fournisseur"}
_SUBTOTAL_HINTS = ("subtotal", "sub total", "sous total")
_TOTAL_EXACT = {
    "total",
    "grand total",
    "amount due",
    "balance due",
    "total due",
    "invoice total",
    "montant du",
    "total du",
}
_CURRENCY_CODES = ("CAD", "USD", "EUR", "GBP")


class RulesExtractor:
    """Offline extractor. Field accuracy is measured separately from any LLM path."""

    name = "rules"

    def extract(self, pdf_bytes: bytes) -> InvoiceFields:
        try:
            text = extract_pdf_text(pdf_bytes)
        except Exception:  # noqa: BLE001 — pdf libraries raise many types for a bad file
            return InvoiceFields(unreadable=True)
        if not text.strip():
            return InvoiceFields(no_text_layer=True)
        return parse_invoice_text(text)


def parse_invoice_text(text: str) -> InvoiceFields:
    fields = InvoiceFields()
    tax_by_label: dict[str, object] = {}
    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        parsed = _split_labelled(raw_line)
        if parsed is None:
            continue
        label, value = parsed
        kind = _classify(label)
        if kind == "vendor":
            fields.vendor_name = clean_text(value)
        elif kind == "invoice_number":
            fields.invoice_number = clean_text(value)
        elif kind == "po":
            fields.po_number = clean_text(value)
        elif kind == "date":
            fields.invoice_date = clean_text(value)
        elif kind == "subtotal":
            _note_currency(fields, value)
            fields.subtotal = parse_money(value)
        elif kind == "total":
            _note_currency(fields, value)
            fields.total = parse_money(value)
        elif kind == "tax":
            _note_currency(fields, value)
            tax_by_label[label] = parse_money(value)
        elif kind == "currency":
            token = clean_text(value)
            _note_currency(fields, token or "")
    if tax_by_label:
        parsed = [amount for amount in tax_by_label.values() if amount is not None]
        # A label that is not an amount (for example "Tax rate: 5%") does not
        # wipe a real GST/TPS line on the same invoice.
        if parsed:
            total_tax = parsed[0]
            for amount in parsed[1:]:
                total_tax += amount
            fields.tax = total_tax
        else:
            fields.tax = None
    return fields


def _note_currency(fields: InvoiceFields, value: str) -> None:
    found = [code for code in _CURRENCY_CODES if re.search(rf"\b{code}\b", value, flags=re.IGNORECASE)]
    if not found:
        return
    if len(set(found)) > 1 or (fields.currency and fields.currency not in found):
        fields.currency = "CONFLICT"
        return
    fields.currency = found[0]


def _split_labelled(raw_line: str) -> tuple[str, str] | None:
    line = raw_line.replace("\u00a0", " ").strip()
    if not line:
        return None
    line = re.sub(r"\.{2,}", ":", line)
    if ":" not in line:
        return None
    label, value = line.split(":", 1)
    normalized = normalize_label(label)
    if not normalized:
        return None
    return normalized, value.strip()


def _classify(label: str) -> str | None:
    if "before tax" in label or "excluding tax" in label or "hors taxe" in label:
        return "subtotal" if "sub" in label else None
    if any(hint in label for hint in _SUBTOTAL_HINTS):
        return "subtotal"
    if label in _TOTAL_EXACT or label.endswith((" total", " total due")):
        return "total"
    if "total" in label and "tax" not in label:
        return "total"
    if label in _VENDOR_LABELS:
        return "vendor"
    if label in _INVOICE_LABELS or label.startswith(("invoice number", "numero de facture")):
        return "invoice_number"
    if label in _PO_LABELS or label.startswith(("bon de commande", "purchase order")):
        return "po"
    if label in _DATE_LABELS:
        return "date"
    tax_tokens = ("tax", "gst", "hst", "pst", "tps", "tvq", "qst", "vat")
    if any(token in label.split() or label.startswith(token) for token in tax_tokens):
        return "tax"
    if label in {"currency", "devise"}:
        return "currency"
    return None
