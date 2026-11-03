"""Data records passed between the pipeline and its adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class Attachment:
    filename: str
    content: bytes
    content_type: str = "application/pdf"


@dataclass(frozen=True)
class EmailMessage:
    id: str
    from_name: str
    from_email: str
    subject: str
    received_at: datetime
    body: str
    attachments: tuple[Attachment, ...] = ()


@dataclass
class InvoiceFields:
    vendor_name: str | None = None
    invoice_number: str | None = None
    po_number: str | None = None
    invoice_date: str | None = None
    subtotal: Decimal | None = None
    tax: Decimal | None = None
    total: Decimal | None = None
    currency: str | None = None
    no_text_layer: bool = False
    unreadable: bool = False


@dataclass(frozen=True)
class Vendor:
    id: str
    name: str
    aliases: tuple[str, ...] = ()
    email_domains: tuple[str, ...] = ()


@dataclass(frozen=True)
class OpenJob:
    po_number: str
    job_name: str
    status: str
    qbo_customer_id: str | None = None


@dataclass(frozen=True)
class BillDraft:
    vendor_name: str
    vendor_id: str
    invoice_number: str
    txn_date: str
    total: Decimal
    po_number: str
    memo: str
    line_description: str
    currency: str = "CAD"
    qbo_customer_id: str | None = None
    expense_account_id: str = "80"


@dataclass
class Bill:
    id: str
    vendor_name: str
    vendor_id: str
    invoice_number: str
    txn_date: str
    total: Decimal
    po_number: str
    memo: str
    currency: str = "CAD"
    attachment_id: str | None = None
    attachment_filename: str | None = None
    attachment_sha256: str | None = None
    attachment_bytes: bytes | None = None


@dataclass
class RunRecord:
    message_id: str
    from_email: str
    subject: str
    decision: str
    reasons: list[str] = field(default_factory=list)
    bill_id: str | None = None
    vendor_name: str | None = None
    invoice_number: str | None = None
    total: str | None = None
    prior_decision: str | None = None


@dataclass
class RunSummary:
    records: list[RunRecord]
    bills_created: int
    extractor: str
    qbo: str
    mail: str

    @property
    def results_by_id(self) -> dict[str, RunRecord]:
        return {record.message_id: record for record in self.records}
