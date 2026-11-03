"""Money, dates, and the rules extractor on text and on synthetic PDFs."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from ap_pipeline.adapters.extract_rules import RulesExtractor, parse_invoice_text
from ap_pipeline.dates import parse_invoice_date
from ap_pipeline.money import parse_money
from tests.conftest import FIXTURES


def test_parse_money_us_french_and_garbled_token():
    assert parse_money("$1,554.00") == Decimal("1554.00")
    assert parse_money("1 320,00") == Decimal("1320.00")
    assert parse_money("1.320,00") == Decimal("1320.00")
    assert parse_money("52S.00") is None
    assert parse_money("10O0.00") is None
    assert parse_money("1\u202f320,00") == Decimal("1320.00")
    assert parse_money("1'320,00") == Decimal("1320.00")
    assert parse_money("1050.00 USD") == Decimal("1050.00")
    assert parse_money("see attached") is None
    assert parse_money("105.010") is None


def test_numeric_dates_are_day_month_year():
    assert parse_invoice_date("04/05/2026") == date(2026, 5, 4)
    assert parse_invoice_date("25 mars 2026") == date(2026, 3, 25)
    assert parse_invoice_date("11 Mar 2026") == date(2026, 3, 11)
    assert parse_invoice_date("March 13, 2026") == date(2026, 3, 13)
    assert parse_invoice_date("32/13/2026") is None
    assert parse_invoice_date("soon") is None
    assert parse_invoice_date("2026-02-31") is None


def test_total_due_is_a_total_and_usd_on_the_amount_line_is_not_cad():
    fields = parse_invoice_text(
        "Vendor: Cedarline Supply Co.\nInvoice Number: INV-1\nPO Number: PO-2401\n"
        "Invoice Date: 2026-03-01\nSubtotal: 1000.00\nGST: 50.00\nTotal Due: 1,050.00 USD\n"
    )
    assert fields.total == Decimal("1050.00")
    assert fields.currency == "USD"
    ignored = parse_invoice_text(
        "Subtotal: 100.00\nTotal before tax: 100.00\nGST: 5.00\nTax rate: 5%\nTotal: 105.00\n"
    )
    assert ignored.tax == Decimal("5.00")
    assert ignored.total == Decimal("105.00")


def test_repeated_tax_label_uses_the_last_value_and_tps_tvq_sum():
    replaced = parse_invoice_text("Vendor: A\nGST: 1.00\nGST: 5.00\n")
    assert replaced.tax == Decimal("5.00")
    combined = parse_invoice_text("Vendor: A\nTPS: 5.00\nTVQ: 9.98\n")
    assert combined.tax == Decimal("14.98")


def test_missing_total_is_not_invented():
    fields = parse_invoice_text(
        "Vendor: Cedarline Supply Co.\nInvoice Number: INV-1\nPO Number: PO-2401\n"
        "Invoice Date: 2026-03-01\nSubtotal: 10.00\nTax: 0.50\nCurrency: CAD\n"
    )
    assert fields.total is None
    assert fields.subtotal == Decimal("10.00")


def test_rules_extractor_reads_clean_messy_scan_french_and_multipage():
    extractor = RulesExtractor()
    expected = {
        "msg-01": ("Cedarline Supply Co.", "INV-1001", "PO-2401", date(2026, 3, 1), Decimal("1050.00")),
        "msg-06": ("Cedarline Supply Co.", "INV-1006", "PO-2422", date(2026, 3, 11), Decimal("1554.00")),
        "msg-10": ("Summit Underlayment Inc.", "INV-1010", "PO-2402", date(2026, 3, 19), Decimal("840.00")),
        "msg-12": ("Harbour Metal Roofing", "INV-1012", "PO-2408", date(2026, 3, 25), Decimal("1386.00")),
        "msg-08": ("Prairie Fastener Ltd.", "INV-1008", "PO-2433", date(2026, 3, 15), Decimal("4305.00")),
    }
    for message_id, (vendor, number, po, invoice_date, total) in expected.items():
        fields = extractor.extract((FIXTURES / "mail" / "inbox" / message_id / "invoice.pdf").read_bytes())
        assert fields.vendor_name is not None
        assert vendor.casefold() in fields.vendor_name.casefold()
        assert fields.invoice_number == number
        assert fields.po_number == po
        assert parse_invoice_date(fields.invoice_date) == invoice_date
        assert fields.total == total


def test_multipage_ignores_the_quote_decoy():
    fields = RulesExtractor().extract(
        (FIXTURES / "mail" / "inbox" / "msg-08" / "invoice.pdf").read_bytes()
    )
    assert fields.total == Decimal("4305.00")
    assert fields.total != Decimal("99.00")


def test_image_only_pdf_has_no_text_layer_and_garbled_total_parses_as_printed():
    image = RulesExtractor().extract((FIXTURES / "mail" / "inbox" / "msg-27" / "invoice.pdf").read_bytes())
    assert image.no_text_layer is True
    assert image.vendor_name is None
    garbled = RulesExtractor().extract((FIXTURES / "mail" / "inbox" / "msg-28" / "invoice.pdf").read_bytes())
    assert garbled.total is None
    assert garbled.subtotal == Decimal("500.00")
