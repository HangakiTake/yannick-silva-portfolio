"""Stable validation codes and the vendor-facing sentences for each."""

from __future__ import annotations

REASON_ORDER: tuple[str, ...] = (
    "missing_pdf",
    "multiple_pdf_attachments",
    "unreadable_pdf",
    "no_text_layer",
    "missing_vendor",
    "unknown_vendor",
    "sender_not_vendor",
    "missing_invoice_number",
    "invoice_number_invalid",
    "missing_po",
    "po_not_on_open_jobs",
    "po_not_open",
    "unparseable_date",
    "date_out_of_range",
    "missing_subtotal",
    "missing_tax",
    "missing_total",
    "non_positive_total",
    "total_mismatch",
    "unsupported_currency",
    "duplicate_invoice_number",
    "duplicate_amount_within_7_days",
)

REASON_TEXT: dict[str, str] = {
    "missing_pdf": "The email has no PDF attachment.",
    "multiple_pdf_attachments": "The email has more than one PDF attachment. Send one invoice PDF per email.",
    "unreadable_pdf": "The PDF could not be read. Please send a standard PDF invoice.",
    "no_text_layer": "The PDF has no text layer, so it looks like a scan we cannot read. Please send a PDF with selectable text.",
    "missing_vendor": "The vendor name is missing.",
    "unknown_vendor": "The vendor is not on our approved vendor list.",
    "sender_not_vendor": "The email sender is not a domain we have on file for this vendor.",
    "missing_invoice_number": "The invoice number is missing.",
    "invoice_number_invalid": "The invoice number contains characters we cannot store, or it is longer than 21 characters.",
    "missing_po": "A job or PO number is missing.",
    "po_not_on_open_jobs": "The PO number does not match an open job.",
    "po_not_open": "The PO number is for a job that is not open.",
    "unparseable_date": "The invoice date is missing or not a valid date.",
    "date_out_of_range": "The invoice date is more than a year before we received the email, or more than 7 days after it.",
    "missing_subtotal": "The subtotal is missing.",
    "missing_tax": "The tax amount is missing. If no tax applies, print a tax line of 0.00.",
    "missing_total": "The invoice total is missing.",
    "non_positive_total": "The invoice total must be greater than zero. Credit notes are not entered by this automation.",
    "total_mismatch": "The total does not equal the subtotal plus tax within $0.01.",
    "unsupported_currency": "The invoice currency is not CAD.",
    "duplicate_invoice_number": "We already have this vendor and invoice number on file.",
    "duplicate_amount_within_7_days": "An invoice from this vendor with the same total is dated within 7 days of this one.",
}


def order_reasons(reasons: list[str]) -> list[str]:
    rank = {code: index for index, code in enumerate(REASON_ORDER)}
    unknown = [code for code in reasons if code not in rank]
    if unknown:
        raise KeyError(f"Unknown reason codes: {unknown}")
    return sorted(set(reasons), key=rank.__getitem__)
