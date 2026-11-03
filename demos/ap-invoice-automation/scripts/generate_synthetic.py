"""Write the 30 synthetic invoices, their mailbox folders, and manifest.json.

Synthetic data only. Re-run from the demo root:

    python scripts/generate_synthetic.py
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from PIL import Image, ImageDraw
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
INBOX = FIXTURES / "mail" / "inbox"

SENDERS = {
    "cedarline": ("Cedarline Supply Co.", "Cedarline Supply Accounts", "ap@cedarline-supply.example"),
    "harbour": ("Harbour Metal Roofing", "Harbour Metal Billing", "billing@harbour-metal.example"),
    "prairie": ("Prairie Fastener Ltd.", "Prairie Fastener Invoices", "invoices@prairie-fastener.example"),
    "lakeside": ("Lakeside Insulation Supply", "Lakeside Accounts", "ar@lakeside-insulation.example"),
    "summit": ("Summit Underlayment Inc.", "Summit Accounts", "accounts@summit-underlayment.example"),
    "northwind": ("Northwind Shingles Inc.", "Northwind Billing", "ap@northwind-shingles.example"),
    "ghost": ("Ghost Vendor LLC", "Ghost Billing", "billing@ghost-vendor.example"),
}

# Truth totals are what scoring compares. Printed text may use another shape.
def _row(
    invoice_id,
    message_id,
    layout,
    vendor,
    invoice_number,
    po,
    date_truth,
    subtotal,
    tax,
    total,
    received_at,
    decision,
    reasons,
    date_print=None,
    po_print=None,
    invoice_print=None,
    total_print=None,
    image_only=False,
):
    return {
        "id": invoice_id,
        "message_id": message_id,
        "layout": layout,
        "vendor": vendor,
        "invoice_number": invoice_number,
        "po": po,
        "date_truth": date_truth,
        "date_print": date_print if date_print is not None else date_truth,
        "subtotal": subtotal,
        "tax": tax,
        "total": total,
        "total_print": total_print,
        "po_print": po_print,
        "invoice_print": invoice_print,
        "received_at": received_at,
        "decision": decision,
        "reasons": reasons,
        "image_only": image_only,
    }


INVOICES = [
    _row("inv-01", "msg-01", "clean", "cedarline", "INV-1001", "PO-2401", "2026-03-01", "1000.00", "50.00", "1050.00", "2026-03-02T15:00:00Z", "processed", []),
    _row("inv-02", "msg-02", "clean", "harbour", "INV-1002", "PO-2402", "2026-03-03", "845.50", "42.28", "887.78", "2026-03-04T15:00:00Z", "processed", []),
    _row("inv-03", "msg-03", "clean", "prairie", "INV-1003", "PO-2408", "2026-03-05", "300.00", "15.00", "315.00", "2026-03-06T15:00:00Z", "processed", []),
    _row("inv-04", "msg-04", "clean", "lakeside", "INV-1004", "PO-2415", "2026-03-07", "2500.00", "125.00", "2625.00", "2026-03-08T15:00:00Z", "processed", []),
    _row("inv-05", "msg-05", "clean", "summit", "INV-1005", "PO-2420", "2026-03-09", "640.00", "32.00", "672.00", "2026-03-10T15:00:00Z", "processed", []),
    _row("inv-06", "msg-06", "messy", "cedarline", "INV-1006", "PO-2422", "2026-03-11", "1480.00", "74.00", "1554.00", "2026-03-12T15:00:00Z", "processed", [], date_print="11 Mar 2026"),
    _row("inv-07", "msg-07", "messy", "harbour", "INV-1007", "PO-2430", "2026-03-13", "99.99", "5.00", "104.99", "2026-03-14T15:00:00Z", "processed", [], date_print="March 13, 2026"),
    _row("inv-08", "msg-08", "multipage", "prairie", "INV-1008", "PO-2433", "2026-03-15", "4100.00", "205.00", "4305.00", "2026-03-16T15:00:00Z", "processed", []),
    _row("inv-09", "msg-09", "multipage", "lakeside", "INV-1009", "PO-2401", "2026-03-17", "750.25", "37.51", "787.76", "2026-03-18T15:00:00Z", "processed", []),
    _row("inv-10", "msg-10", "scan", "summit", "INV-1010", "PO-2402", "2026-03-19", "800.00", "40.00", "840.00", "2026-03-20T15:00:00Z", "processed", [], date_print="March 19, 2026"),
    _row("inv-11", "msg-11", "scan", "cedarline", "INV-1011", "PO-2420", "2026-03-21", "150.00", "7.50", "157.50", "2026-03-22T15:00:00Z", "processed", [], date_print="21 Mar 2026"),
    _row("inv-12", "msg-12", "french", "harbour", "INV-1012", "PO-2408", "2026-03-25", "1320.00", "66.00", "1386.00", "2026-03-26T15:00:00Z", "processed", [], date_print="25 mars 2026"),
    _row("inv-13", "msg-13", "clean", "prairie", "INV-1013", "PO-2415", "2026-04-01", "50.00", "2.50", "52.50", "2026-04-02T15:00:00Z", "processed", []),
    _row("inv-14", "msg-14", "clean", "lakeside", "INV-1014", "PO-2422", "2026-04-03", "99.99", "13.00", "112.99", "2026-04-04T15:00:00Z", "processed", []),
    _row("inv-15", "msg-15", "clean", "summit", "INV-1015", "PO-2430", "2026-04-05", "100.00", "5.00", "105.01", "2026-04-06T15:00:00Z", "processed", []),
    _row("inv-16", "msg-16", "clean", "cedarline", "INV-1016", "PO-2433", "2026-04-20", "1000.00", "50.00", "1050.00", "2026-04-21T15:00:00Z", "processed", []),
    _row("inv-17", "msg-17", "clean", "cedarline", "INV-2001", None, "2026-03-02", "200.00", "10.00", "210.00", "2026-03-03T16:00:00Z", "failed", ["missing_po"]),
    _row("inv-18", "msg-18", "clean", "harbour", "INV-2002", None, "2026-03-04", "210.00", "10.50", "220.50", "2026-03-05T16:00:00Z", "failed", ["missing_po"], po_print="N/A"),
    _row("inv-19", "msg-19", "clean", "northwind", "INV-2003", "PO-2401", "2026-03-06", "220.00", "11.00", "231.00", "2026-03-07T15:00:00Z", "failed", ["unknown_vendor"]),
    _row("inv-20", "msg-20", "clean", "cedarline", "INV-2004", "PO-9999", "2026-03-08", "230.00", "11.50", "241.50", "2026-03-09T15:00:00Z", "failed", ["po_not_on_open_jobs"]),
    _row("inv-21", "msg-21", "clean", "cedarline", "INV-2005", "PO-2440", "2026-03-10", "240.00", "12.00", "252.00", "2026-03-11T15:00:00Z", "failed", ["po_not_open"]),
    _row("inv-22", "msg-22", "clean", "prairie", "INV-2006", "PO-2401", "2026-03-11", "1000.00", "50.00", "1200.00", "2026-03-12T16:00:00Z", "failed", ["total_mismatch"]),
    _row("inv-23", "msg-23", "clean", "lakeside", "INV-2007", "PO-2402", None, "250.00", "12.50", "262.50", "2026-03-13T16:00:00Z", "failed", ["unparseable_date"], date_print="32/13/2026"),
    _row("inv-24", "msg-24", "clean", "summit", None, "PO-2408", "2026-03-18", "260.00", "13.00", "273.00", "2026-03-19T16:00:00Z", "failed", ["missing_invoice_number"]),
    _row("inv-25", "msg-25", "clean", "cedarline", "INV-2008", "PO-2415", "2026-03-20", "270.00", "13.50", None, "2026-03-21T16:00:00Z", "failed", ["missing_total"]),
    _row("inv-26", "msg-26", "clean", "ghost", "INV-2009", None, None, "10.00", "1.00", "11.00", "2026-03-22T16:00:00Z", "failed", ["unknown_vendor", "missing_po", "unparseable_date"], date_print="soon"),
    _row("inv-27", "msg-27", "image", "harbour", "INV-2010", "PO-2420", "2026-03-28", "220.00", "11.00", "231.00", "2026-03-29T15:00:00Z", "failed", ["no_text_layer"], image_only=True),
    _row("inv-28", "msg-28", "clean", "prairie", "INV-2011", "PO-2433", "2026-03-28", "500.00", "25.00", None, "2026-03-29T16:00:00Z", "failed", ["missing_total"], total_print="52S.00"),
    _row("inv-29", "msg-00-resend", "clean", "cedarline", "INV-1001", "PO-2401", "2026-03-01", "1000.00", "50.00", "1050.00", "2026-03-03T15:00:00Z", "duplicate", ["duplicate_invoice_number", "duplicate_amount_within_7_days"], invoice_print="inv-1001"),
    _row("inv-30", "msg-00-amount", "clean", "cedarline", "INV-3001", "PO-2402", "2026-03-04", "1000.00", "50.00", "1050.00", "2026-03-05T15:00:00Z", "duplicate", ["duplicate_amount_within_7_days"]),
]


def main() -> None:
    if INBOX.exists():
        for child in INBOX.iterdir():
            if child.is_dir():
                for item in child.iterdir():
                    item.unlink()
                child.rmdir()
    INBOX.mkdir(parents=True, exist_ok=True)
    manifest_rows = []
    for invoice in INVOICES:
        folder = INBOX / invoice["message_id"]
        folder.mkdir()
        pdf_path = folder / "invoice.pdf"
        if invoice["image_only"]:
            _write_image_pdf(pdf_path, invoice)
        else:
            _write_text_pdf(pdf_path, invoice)
        manifest_rows.append(_manifest_row(invoice))
        (folder / "message.json").write_text(
            json.dumps(_message(invoice), indent=2),
            encoding="utf-8",
        )
    payload = {
        "description": "30 synthetic roofing-supply invoices. No real vendor documents.",
        "invoices": manifest_rows,
    }
    (FIXTURES / "manifest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {len(manifest_rows)} invoices")


def _manifest_row(invoice: dict) -> dict:
    vendor_name, _, _ = SENDERS[invoice["vendor"]]
    return {
        "id": invoice["id"],
        "message_id": invoice["message_id"],
        "layout": invoice["layout"],
        "pdf": f"mail/inbox/{invoice['message_id']}/invoice.pdf",
        "from_email": SENDERS[invoice["vendor"]][2],
        "received_at": invoice["received_at"],
        "text_layer": not invoice["image_only"],
        "truth": {
            "vendor_name": None if invoice["image_only"] else vendor_name,
            "invoice_number": None if invoice["image_only"] else invoice["invoice_number"],
            "po_number": None if invoice["image_only"] else invoice["po"],
            "invoice_date": None if invoice["image_only"] else invoice["date_truth"],
            "subtotal": None if invoice["image_only"] else invoice["subtotal"],
            "tax": None if invoice["image_only"] else invoice["tax"],
            "total": None if invoice["image_only"] else invoice["total"],
            "currency": None if invoice["image_only"] else "CAD",
        },
        "visual_truth": {
            "vendor_name": vendor_name,
            "invoice_number": invoice["invoice_number"],
            "po_number": invoice["po"],
            "invoice_date": invoice["date_truth"],
            "subtotal": invoice["subtotal"],
            "tax": invoice["tax"],
            "total": invoice["total"],
            "currency": "CAD",
        },
        "expected_decision": invoice["decision"],
        "expected_reasons": invoice["reasons"],
    }


def _message(invoice: dict) -> dict:
    _, from_name, from_email = SENDERS[invoice["vendor"]]
    number = invoice["invoice_number"] or "attached"
    return {
        "id": invoice["message_id"],
        "from_name": from_name,
        "from_email": from_email,
        "subject": f"Invoice {number}",
        "received_at": invoice["received_at"],
        "body": "Please see the attached invoice.",
    }


def _write_text_pdf(path: Path, invoice: dict) -> None:
    document = canvas.Canvas(str(path))
    if invoice["layout"] == "multipage":
        _page_one_items(document, invoice)
        document.showPage()
        _draw_lines(document, _multipage_total_lines(invoice), font="Helvetica", size=11)
    elif invoice["layout"] == "messy":
        _draw_lines(document, _messy_lines(invoice), font="Helvetica", size=11)
    elif invoice["layout"] == "scan":
        _draw_lines(document, _scan_lines(invoice), font="Courier", size=11)
    elif invoice["layout"] == "french":
        _draw_lines(document, _french_lines(invoice), font="Helvetica", size=11)
    else:
        _draw_lines(document, _clean_lines(invoice), font="Helvetica", size=11)
    document.save()


def _write_image_pdf(path: Path, invoice: dict) -> None:
    image_path = path.with_suffix(".png")
    image = Image.new("RGB", (1700, 2200), "white")
    draw = ImageDraw.Draw(image)
    vendor_name, _, _ = SENDERS[invoice["vendor"]]
    lines = [
        "SCANNED INVOICE",
        f"Vendor: {vendor_name}",
        f"Invoice Number: {invoice['invoice_number']}",
        f"PO Number: {invoice['po']}",
        f"Invoice Date: {invoice['date_truth']}",
        f"Subtotal: {invoice['subtotal']}",
        f"Tax: {invoice['tax']}",
        f"Total: {invoice['total']}",
        "Currency: CAD",
    ]
    y = 80
    for line in lines:
        draw.text((80, y), line, fill="black")
        y += 48
    image.save(image_path)
    document = canvas.Canvas(str(path))
    document.drawImage(str(image_path), 36, 36, width=540, height=700, preserveAspectRatio=True, mask="auto")
    document.save()
    image_path.unlink()


def _draw_lines(document, lines: list[str], *, font: str, size: int) -> None:
    document.setFont(font, 14)
    y = 760
    document.drawString(72, y, lines[0])
    document.setFont(font, size)
    for line in lines[1:]:
        y -= 22
        document.drawString(72, y, line)


def _shown_invoice(invoice: dict) -> str | None:
    if invoice["invoice_number"] is None:
        return None
    return invoice["invoice_print"] or invoice["invoice_number"]


def _shown_po(invoice: dict) -> str | None:
    if invoice["po_print"] is not None:
        return invoice["po_print"]
    return invoice["po"]


def _shown_total(invoice: dict) -> str | None:
    if invoice["total_print"] is not None:
        return invoice["total_print"]
    if invoice["total"] is None:
        return None
    return invoice["total"]


def _clean_lines(invoice: dict) -> list[str]:
    vendor_name, _, _ = SENDERS[invoice["vendor"]]
    rows = ["INVOICE", f"Vendor: {vendor_name}"]
    number = _shown_invoice(invoice)
    if number is not None:
        rows.append(f"Invoice Number: {number}")
    po = _shown_po(invoice)
    if po is not None:
        rows.append(f"PO Number: {po}")
    if invoice["date_print"] is not None:
        rows.append(f"Invoice Date: {invoice['date_print']}")
    rows.append(f"Subtotal: {invoice['subtotal']}")
    rows.append(f"Tax: {invoice['tax']}")
    total = _shown_total(invoice)
    if total is not None:
        rows.append(f"Total: {total}")
    rows.append("Currency: CAD")
    return rows


def _messy_lines(invoice: dict) -> list[str]:
    vendor_name, _, _ = SENDERS[invoice["vendor"]]
    return [
        "INVOICE",
        f"Vendor Name    :   {vendor_name}",
        f"Inv #          :   {_shown_invoice(invoice)}",
        f"P.O. Number    :   {_shown_po(invoice)}",
        f"Date           :   {invoice['date_print']}",
        f"Sub-Total      :   {_money_us(invoice['subtotal'])}",
        f"GST            :   {_money_us(invoice['tax'])}",
        f"Amount Due     :   {_money_us(invoice['total'])}",
        "Currency       :   CAD",
    ]


def _scan_lines(invoice: dict) -> list[str]:
    vendor_name, _, _ = SENDERS[invoice["vendor"]]
    return [
        "*** TEXT LAYER FROM A SCAN ***",
        f"VENDOR..........{vendor_name.upper()}",
        f"INVOICE NO......{_shown_invoice(invoice)}",
        f"P O NUMBER......{_shown_po(invoice)}",
        f"DATE............{invoice['date_print']}",
        f"SUBTOTAL........{_money_us(invoice['subtotal'])}",
        f"TAX.............{_money_us(invoice['tax'])}",
        f"TOTAL...........{_money_us(invoice['total'])}",
        "CURRENCY........CAD",
    ]


def _french_lines(invoice: dict) -> list[str]:
    vendor_name, _, _ = SENDERS[invoice["vendor"]]
    return [
        "FACTURE",
        f"Fournisseur : {vendor_name}",
        f"Numéro de facture : {_shown_invoice(invoice)}",
        f"Bon de commande : {_shown_po(invoice)}",
        f"Date de facture : {invoice['date_print']}",
        f"Sous-total : {_money_fr(invoice['subtotal'])}",
        f"TPS : {_money_fr(invoice['tax'])}",
        f"Total : {_money_fr(invoice['total'])}",
        "Devise : CAD",
    ]


def _page_one_items(document, invoice: dict) -> None:
    vendor_name, _, _ = SENDERS[invoice["vendor"]]
    lines = [
        "INVOICE",
        f"Vendor: {vendor_name}",
        f"Invoice Number: {_shown_invoice(invoice)}",
        f"PO Number: {_shown_po(invoice)}",
        f"Invoice Date: {invoice['date_print']}",
        "Description: Architectural shingles",
        "Quantity: 40",
        "Line amount: 3200.00",
        "Note: the quote total was $99.00",
        "Continued on the next page.",
    ]
    _draw_lines(document, lines, font="Helvetica", size=11)


def _multipage_total_lines(invoice: dict) -> list[str]:
    vendor_name, _, _ = SENDERS[invoice["vendor"]]
    return [
        "INVOICE TOTALS",
        f"Vendor: {vendor_name}",
        f"Invoice Number: {_shown_invoice(invoice)}",
        f"PO Number: {_shown_po(invoice)}",
        f"Invoice Date: {invoice['date_print']}",
        f"Subtotal: {invoice['subtotal']}",
        f"Tax: {invoice['tax']}",
        f"Total: {invoice['total']}",
        "Currency: CAD",
    ]


def _money_us(value: str) -> str:
    return f"${Decimal(value):,.2f}"


def _money_fr(value: str) -> str:
    whole, frac = f"{Decimal(value):.2f}".split(".")
    groups: list[str] = []
    while whole:
        groups.append(whole[-3:])
        whole = whole[:-3]
    return f"{' '.join(reversed(groups))},{frac}"


if __name__ == "__main__":
    main()
