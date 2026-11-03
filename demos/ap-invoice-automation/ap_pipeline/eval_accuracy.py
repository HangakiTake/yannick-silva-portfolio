"""Score the rules extractor. The LLM path is reported as not measured without a live eval."""

from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path

from ap_pipeline.adapters.extract_rules import RulesExtractor
from ap_pipeline.dates import parse_invoice_date
from ap_pipeline.textnorm import invoice_key, is_blank_token, po_key, vendor_key

SCORE_FIELDS = ("vendor_name", "invoice_number", "po_number", "invoice_date", "total")

LLM_NOT_MEASURED = (
    "No OPENAI_API_KEY or ANTHROPIC_API_KEY is set. LLM-path accuracy was not measured."
)
LLM_KEY_PRESENT_NOT_RUN = (
    "An API key is present, but the live LLM eval was not run. LLM-path accuracy was not measured."
)


def score_rules(manifest: dict, fixture_root: Path) -> dict:
    extractor = RulesExtractor()
    correct = 0
    total = 0
    misses: list[dict] = []
    for item in manifest["invoices"]:
        pdf_bytes = (fixture_root / item["pdf"]).read_bytes()
        extracted = extractor.extract(pdf_bytes)
        # Image-only invoices are scored against the page a person can see.
        # Text invoices are scored against the text layer, including a broken
        # total token as the characters that were printed.
        reference = item["visual_truth"] if not item["text_layer"] else item["truth"]
        for field in SCORE_FIELDS:
            total += 1
            if _matches(field, extracted, reference):
                correct += 1
            else:
                misses.append(
                    {
                        "id": item["id"],
                        "field": field,
                        "expected": reference.get(field),
                        "extracted": _extracted_value(field, extracted),
                    }
                )
    return {
        "path": "rules",
        "status": "measured",
        "correct": correct,
        "total": total,
        "accuracy": correct / total if total else 0,
        "misses": misses,
        "scoring": (
            "vendor, invoice number, and PO are compared after normalization. "
            "Dates are compared as parsed calendar dates. Totals are compared as "
            "decimal amounts of what the text layer says. An image-only PDF is "
            "scored against the visual invoice, so a missing text layer counts as misses."
        ),
    }


def llm_accuracy_report() -> dict:
    has_key = bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY"))
    return {
        "path": "llm",
        "status": "not_measured",
        "accuracy": None,
        "reason": LLM_KEY_PRESENT_NOT_RUN if has_key else LLM_NOT_MEASURED,
    }


def write_reports(manifest_path: Path, out_dir: Path) -> tuple[dict, dict]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rules = score_rules(manifest, manifest_path.parent)
    llm = llm_accuracy_report()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "rules_accuracy.json").write_text(json.dumps(rules, indent=2), encoding="utf-8")
    (out_dir / "llm_accuracy.json").write_text(json.dumps(llm, indent=2), encoding="utf-8")
    return rules, llm


def _matches(field: str, extracted, truth: dict) -> bool:
    expected = truth.get(field)
    if field == "vendor_name":
        if expected is None:
            return is_blank_token(extracted.vendor_name)
        if is_blank_token(extracted.vendor_name):
            return False
        return vendor_key(extracted.vendor_name) == vendor_key(str(expected))
    if field == "invoice_number":
        if expected is None:
            return is_blank_token(extracted.invoice_number)
        if is_blank_token(extracted.invoice_number):
            return False
        return invoice_key(extracted.invoice_number) == invoice_key(str(expected))
    if field == "po_number":
        if expected is None:
            return po_key(extracted.po_number or "") is None
        return po_key(extracted.po_number or "") == po_key(str(expected))
    if field == "invoice_date":
        expected_date = None if expected is None else parse_invoice_date(str(expected))
        actual = parse_invoice_date(extracted.invoice_date)
        if expected_date is None:
            return actual is None
        return actual == expected_date
    if field == "total":
        if expected is None:
            return extracted.total is None
        if extracted.total is None:
            return False
        return extracted.total == Decimal(str(expected))
    raise KeyError(field)


def _extracted_value(field: str, extracted) -> str | None:
    value = getattr(extracted, field)
    if value is None:
        return None
    return str(value)
