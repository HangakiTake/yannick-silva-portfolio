"""Deterministic validation, including the duplicate window."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from ap_pipeline.models import Bill, InvoiceFields
from ap_pipeline.reply import render_reply
from ap_pipeline.validator import validate_invoice

RECEIVED = date(2026, 3, 2)


def _fields(**overrides) -> InvoiceFields:
    values = {
        "vendor_name": "Cedarline Supply Co.",
        "invoice_number": "INV-9001",
        "po_number": "PO-2401",
        "invoice_date": "2026-03-01",
        "subtotal": Decimal("100.00"),
        "tax": Decimal("5.00"),
        "total": Decimal("105.00"),
        "currency": "CAD",
    }
    values.update(overrides)
    return InvoiceFields(**values)


def _bill(**overrides) -> Bill:
    values = {
        "id": "mock-bill-0001",
        "vendor_name": "Cedarline Supply Co.",
        "vendor_id": "v-cedarline",
        "invoice_number": "INV-1001",
        "txn_date": "2026-03-01",
        "total": Decimal("1050.00"),
        "po_number": "PO-2401",
        "memo": "PO-2401 Maple Street re-roof",
    }
    values.update(overrides)
    return Bill(**values)


def _reasons(fields, vendors, jobs, ledger=None, received=RECEIVED):
    return validate_invoice(
        fields,
        vendors=vendors,
        jobs=jobs,
        ledger=ledger or [],
        received_on=received,
    ).reasons


def test_valid_invoice_has_no_reasons(vendors, jobs):
    outcome = validate_invoice(
        _fields(),
        vendors=vendors,
        jobs=jobs,
        ledger=[],
        received_on=RECEIVED,
    )
    assert outcome.reasons == []
    assert outcome.vendor_name == "Cedarline Supply Co."
    assert outcome.job_name == "Maple Street re-roof"
    assert outcome.po_number == "PO-2401"


def test_total_within_one_cent_passes_and_two_cents_fails(vendors, jobs):
    assert _reasons(_fields(total=Decimal("105.01")), vendors, jobs) == []
    assert _reasons(_fields(total=Decimal("105.02")), vendors, jobs) == ["total_mismatch"]


def test_zero_tax_is_allowed_and_missing_tax_is_not(vendors, jobs):
    assert _reasons(_fields(subtotal=Decimal("40.00"), tax=Decimal("0.00"), total=Decimal("40.00")), vendors, jobs) == []
    assert "missing_tax" in _reasons(_fields(tax=None), vendors, jobs)


def test_missing_total_is_not_accepted(vendors, jobs):
    assert _reasons(_fields(total=None), vendors, jobs) == ["missing_total"]


def test_zero_and_negative_totals_are_rejected(vendors, jobs):
    assert "non_positive_total" in _reasons(_fields(subtotal=Decimal("0.00"), tax=Decimal("0.00"), total=Decimal("0.00")), vendors, jobs)
    assert "non_positive_total" in _reasons(
        _fields(subtotal=Decimal("-10.00"), tax=Decimal("0.00"), total=Decimal("-10.00")),
        vendors,
        jobs,
    )


def test_vendor_po_and_date_failures(vendors, jobs):
    assert _reasons(_fields(vendor_name=None), vendors, jobs) == ["missing_vendor"]
    assert _reasons(_fields(vendor_name="N/A"), vendors, jobs) == ["missing_vendor"]
    assert _reasons(_fields(vendor_name="Northwind Shingles Inc."), vendors, jobs) == ["unknown_vendor"]
    assert _reasons(_fields(vendor_name="CEDARLINE SUPPLY CO."), vendors, jobs) == []
    assert _reasons(_fields(po_number=None), vendors, jobs) == ["missing_po"]
    assert _reasons(_fields(po_number="N/A"), vendors, jobs) == ["missing_po"]
    assert _reasons(_fields(po_number="PO-9999"), vendors, jobs) == ["po_not_on_open_jobs"]
    assert _reasons(_fields(po_number="po 2401"), vendors, jobs) == []
    assert _reasons(_fields(po_number="PO-2440"), vendors, jobs) == ["po_not_open"]
    assert _reasons(_fields(invoice_date="soon"), vendors, jobs) == ["unparseable_date"]
    assert _reasons(_fields(invoice_date="2024-01-01"), vendors, jobs) == ["date_out_of_range"]
    assert _reasons(_fields(invoice_date="2026-03-20"), vendors, jobs, received=RECEIVED) == ["date_out_of_range"]


def test_usd_is_rejected_and_missing_currency_is_cad(vendors, jobs):
    assert _reasons(_fields(currency="USD"), vendors, jobs) == ["unsupported_currency"]
    assert _reasons(_fields(currency=None), vendors, jobs) == []


def test_invoice_number_length_and_characters(vendors, jobs):
    assert _reasons(_fields(invoice_number="INV-1001 "), vendors, jobs) == []
    assert "invoice_number_invalid" in _reasons(_fields(invoice_number="INV " + ("A" * 25)), vendors, jobs)
    assert _reasons(_fields(invoice_number=None), vendors, jobs) == ["missing_invoice_number"]


def test_several_reasons_stay_in_stable_order(vendors, jobs):
    reasons = _reasons(
        _fields(vendor_name="Ghost Vendor LLC", po_number=None, invoice_date="soon"),
        vendors,
        jobs,
    )
    assert reasons == ["unknown_vendor", "missing_po", "unparseable_date"]


def test_duplicate_invoice_number_ignores_case_and_spaces(vendors, jobs):
    reasons = _reasons(
        _fields(invoice_number=" inv-1001 "),
        vendors,
        jobs,
        ledger=[_bill()],
    )
    assert "duplicate_invoice_number" in reasons
    assert "duplicate_amount_within_7_days" not in reasons


def test_same_total_window_is_inclusive_on_day_7(vendors, jobs):
    inside = _reasons(
        _fields(invoice_number="INV-1", invoice_date="2026-03-08", subtotal=Decimal("1000.00"), tax=Decimal("50.00"), total=Decimal("1050.00")),
        vendors,
        jobs,
        ledger=[_bill()],
    )
    outside = _reasons(
        _fields(invoice_number="INV-2", invoice_date="2026-03-09", subtotal=Decimal("1000.00"), tax=Decimal("50.00"), total=Decimal("1050.00")),
        vendors,
        jobs,
        ledger=[_bill()],
    )
    other_vendor = _reasons(
        _fields(
            vendor_name="Harbour Metal Roofing",
            invoice_number="INV-3",
            invoice_date="2026-03-01",
            subtotal=Decimal("1000.00"),
            tax=Decimal("50.00"),
            total=Decimal("1050.00"),
        ),
        vendors,
        jobs,
        ledger=[_bill()],
    )
    assert inside == ["duplicate_amount_within_7_days"]
    assert outside == []
    assert other_vendor == []


def test_reply_lists_exactly_the_reason_sentences():
    subject, body = render_reply(
        ["missing_po", "total_mismatch"],
        invoice_number="INV-2006",
        company_name="Northline Roofing",
    )
    assert subject == "Invoice INV-2006 needs a correction"
    bullets = [line for line in body.splitlines() if line.startswith("- ")]
    assert bullets == [
        "- A job or PO number is missing.",
        "- The total does not equal the subtotal plus tax within $0.01.",
    ]
    assert "approved vendor" not in body
