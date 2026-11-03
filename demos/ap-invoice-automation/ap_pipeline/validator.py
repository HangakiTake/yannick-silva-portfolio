"""Deterministic checks applied after extraction. The model does not decide pass/fail."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from ap_pipeline.dates import parse_invoice_date
from ap_pipeline.master_data import JobDirectory, VendorDirectory
from ap_pipeline.models import Bill, InvoiceFields
from ap_pipeline.reasons import order_reasons
from ap_pipeline.textnorm import invoice_key, is_blank_token, po_key, vendor_key

_TOLERANCE = Decimal("0.01")
_INVOICE_NUMBER = re.compile(r"[A-Z0-9][A-Z0-9./-]{0,20}")
_WINDOW = timedelta(days=7)
_MAX_AGE = timedelta(days=365)


@dataclass(frozen=True)
class ValidationOutcome:
    reasons: list[str]
    vendor_id: str | None
    vendor_name: str | None
    po_number: str | None
    job_name: str | None
    qbo_customer_id: str | None
    invoice_number: str | None
    txn_date: str | None


def validate_invoice(
    fields: InvoiceFields,
    *,
    vendors: VendorDirectory,
    jobs: JobDirectory,
    ledger: list[Bill],
    received_on: date,
    duplicate_window_days: int = 7,
) -> ValidationOutcome:
    if fields.unreadable:
        return _outcome(["unreadable_pdf"])
    if fields.no_text_layer:
        return _outcome(["no_text_layer"])

    reasons: list[str] = []
    vendor = None if is_blank_token(fields.vendor_name) else vendors.resolve(fields.vendor_name)
    if is_blank_token(fields.vendor_name):
        reasons.append("missing_vendor")
    elif vendor is None:
        reasons.append("unknown_vendor")

    invoice_number = None if is_blank_token(fields.invoice_number) else _clean_invoice_number(fields.invoice_number)
    if is_blank_token(fields.invoice_number):
        reasons.append("missing_invoice_number")
    elif invoice_number is None:
        reasons.append("invoice_number_invalid")

    job = jobs.get(fields.po_number)
    po_display: str | None = None
    if fields.po_number is None or po_key(fields.po_number) is None:
        reasons.append("missing_po")
    elif job is None:
        reasons.append("po_not_on_open_jobs")
    elif job.status != "open":
        reasons.append("po_not_open")
        po_display = po_key(fields.po_number)
    else:
        po_display = po_key(fields.po_number)

    parsed_date = parse_invoice_date(fields.invoice_date)
    if parsed_date is None:
        reasons.append("unparseable_date")
    else:
        if parsed_date < received_on - _MAX_AGE or parsed_date > received_on + _WINDOW:
            reasons.append("date_out_of_range")

    if fields.subtotal is None:
        reasons.append("missing_subtotal")
    if fields.tax is None:
        reasons.append("missing_tax")
    if fields.total is None:
        reasons.append("missing_total")
    elif fields.total <= 0:
        reasons.append("non_positive_total")

    if (
        fields.subtotal is not None
        and fields.tax is not None
        and fields.total is not None
        and abs((fields.subtotal + fields.tax) - fields.total) > _TOLERANCE
    ):
        reasons.append("total_mismatch")

    currency = (fields.currency or "CAD").upper()
    if currency != "CAD":
        reasons.append("unsupported_currency")

    if vendor is not None and invoice_number is not None and _same_invoice_number(
        ledger, vendor.name, invoice_number
    ):
        reasons.append("duplicate_invoice_number")
    if vendor is not None and fields.total is not None and parsed_date is not None:
        window = timedelta(days=duplicate_window_days)
        if _same_amount_within(ledger, vendor.name, fields.total, parsed_date, window):
            reasons.append("duplicate_amount_within_7_days")

    return ValidationOutcome(
        reasons=order_reasons(reasons),
        vendor_id=None if vendor is None else vendor.id,
        vendor_name=None if vendor is None else vendor.name,
        po_number=po_display,
        job_name=None if job is None or job.status != "open" else job.job_name,
        qbo_customer_id=None if job is None else job.qbo_customer_id,
        invoice_number=invoice_number,
        txn_date=None if parsed_date is None else parsed_date.isoformat(),
    )


def _outcome(reasons: list[str]) -> ValidationOutcome:
    return ValidationOutcome(
        reasons=order_reasons(reasons),
        vendor_id=None,
        vendor_name=None,
        po_number=None,
        job_name=None,
        qbo_customer_id=None,
        invoice_number=None,
        txn_date=None,
    )


def _clean_invoice_number(value: str | None) -> str | None:
    if value is None:
        return None
    key = invoice_key(value)
    if _INVOICE_NUMBER.fullmatch(key) is None:
        return None
    return key


def _same_invoice_number(ledger: list[Bill], vendor_name: str, invoice_number: str) -> bool:
    wanted_vendor = vendor_key(vendor_name)
    wanted_number = invoice_key(invoice_number)
    return any(
        vendor_key(bill.vendor_name) == wanted_vendor and invoice_key(bill.invoice_number) == wanted_number
        for bill in ledger
    )


def _same_amount_within(
    ledger: list[Bill],
    vendor_name: str,
    total: Decimal,
    invoice_date: date,
    window: timedelta,
) -> bool:
    wanted_vendor = vendor_key(vendor_name)
    for bill in ledger:
        if vendor_key(bill.vendor_name) != wanted_vendor:
            continue
        if bill.total != total:
            continue
        prior = parse_invoice_date(bill.txn_date)
        if prior is None:
            continue
        if abs(prior - invoice_date) <= window:
            return True
    return False
