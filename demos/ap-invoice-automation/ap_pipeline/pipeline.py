"""Orchestrate extract → validate → bill or reply. Adapters are injected."""

from __future__ import annotations

import re
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from ap_pipeline.adapters.mail_local import safe_filename
from ap_pipeline.errors import PipelineError
from ap_pipeline.models import BillDraft, InvoiceFields, RunRecord, RunSummary
from ap_pipeline.money import money_to_json_number
from ap_pipeline.reasons import order_reasons
from ap_pipeline.reply import render_reply
from ap_pipeline.runlog import RunLog
from ap_pipeline.state import StateStore
from ap_pipeline.textnorm import invoice_key, vendor_key
from ap_pipeline.validator import validate_invoice

_BUSINESS_ZONE = ZoneInfo("America/Toronto")

_DUPLICATES = {"duplicate_invoice_number", "duplicate_amount_within_7_days"}


@dataclass
class PipelineConfig:
    company_name: str = "Northline Roofing"
    dry_run: bool = False
    expense_account_id: str = "80"
    extractor_name: str = "rules"
    qbo_name: str = "mock"
    mail_name: str = "local"


def run_pipeline(
    *,
    mail,
    extractor,
    qbo,
    vendors,
    jobs,
    state: StateStore,
    run_log: RunLog,
    config: PipelineConfig | None = None,
) -> RunSummary:
    settings = config or PipelineConfig()
    qbo.load_ledger(state.bills)
    records: list[RunRecord] = []
    created = 0
    messages = sorted(mail.list_messages(), key=lambda item: (item.received_at, item.id))
    for message_id, exc in getattr(mail, "read_errors", []):
        records.append(
            RunRecord(
                message_id=message_id,
                from_email="",
                subject="",
                decision="error",
                reasons=[_safe_error(exc)],
            )
        )
    for message in messages:
        try:
            record, new_bills = _handle_message(
                message,
                mail=mail,
                extractor=extractor,
                qbo=qbo,
                vendors=vendors,
                jobs=jobs,
                state=state,
                config=settings,
            )
        except Exception as exc:  # noqa: BLE001 — one bad message must not abort the batch
            record = RunRecord(
                message_id=message.id,
                from_email=message.from_email,
                subject=message.subject,
                decision="error",
                reasons=[_safe_error(exc)],
            )
            new_bills = 0
        records.append(record)
        created += new_bills
    summary = RunSummary(
        records=records,
        bills_created=created,
        extractor=settings.extractor_name,
        qbo=settings.qbo_name,
        mail=settings.mail_name,
    )
    run_log.write(summary)
    return summary


def _handle_message(message, *, mail, extractor, qbo, vendors, jobs, state, config) -> tuple[RunRecord, int]:
    prior = state.get_message(message.id)
    if prior and prior.get("phase") in {"completed", "replying"}:
        _refile(mail, message.id, prior.get("decision"))
        if prior.get("phase") == "replying":
            state.upsert_message(message.id, phase="completed")
        return (
            RunRecord(
                message_id=message.id,
                from_email=message.from_email,
                subject=message.subject,
                decision="already_processed",
                bill_id=prior.get("bill_id") or None,
                prior_decision=prior.get("decision"),
                vendor_name=prior.get("vendor_name") or None,
                invoice_number=prior.get("invoice_number") or None,
                total=prior.get("total") or None,
            ),
            0,
        )
    if prior and prior.get("phase") == "creating" and not prior.get("bill_id"):
        match = _matching_bill(qbo, prior.get("vendor_name"), prior.get("invoice_number"), state)
        if match is not None:
            state.add_bill(match)
            state.upsert_message(message.id, phase="in_progress", bill_id=match.id, decision="processed")
            refreshed = state.get_message(message.id) or prior
            return _resume_attachment(message, mail=mail, qbo=qbo, state=state, prior=refreshed)
    if prior and prior.get("bill_id"):
        return _resume_attachment(message, mail=mail, qbo=qbo, state=state, prior=prior)

    pdfs = [item for item in message.attachments if item.filename.lower().endswith(".pdf")]
    if len(pdfs) == 0:
        return _reject(message, ["missing_pdf"], mail=mail, state=state, config=config, fields=None)
    if len(pdfs) > 1:
        return _reject(
            message,
            ["multiple_pdf_attachments"],
            mail=mail,
            state=state,
            config=config,
            fields=None,
        )

    fields = extractor.extract(pdfs[0].content)
    received_on = message.received_at.astimezone(_BUSINESS_ZONE).date()
    outcome = validate_invoice(
        fields,
        vendors=vendors,
        jobs=jobs,
        ledger=_combined_ledger(state, qbo),
        received_on=received_on,
    )
    reasons = list(outcome.reasons)
    if _sender_mismatch(message.from_email, fields.vendor_name, vendors):
        reasons = order_reasons([*reasons, "sender_not_vendor"])
    if reasons:
        return _reject(
            message,
            reasons,
            mail=mail,
            state=state,
            config=config,
            fields=fields,
            invoice_number=outcome.invoice_number or fields.invoice_number,
        )
    if config.dry_run:
        return (
            RunRecord(
                message_id=message.id,
                from_email=message.from_email,
                subject=message.subject,
                decision="would_process",
                vendor_name=outcome.vendor_name,
                invoice_number=outcome.invoice_number,
                total=None if fields.total is None else money_to_json_number(fields.total),
            ),
            0,
        )

    if not (
        outcome.vendor_id
        and outcome.vendor_name
        and outcome.po_number
        and outcome.job_name
        and outcome.invoice_number
        and outcome.txn_date
        and fields.total is not None
        and fields.subtotal is not None
        and fields.tax is not None
    ):
        raise PipelineError("Invoice passed validation without the fields required to create a bill")
    memo = f"{outcome.po_number} {outcome.job_name}"
    description = (
        f"Subtotal {money_to_json_number(fields.subtotal)} "
        f"tax {money_to_json_number(fields.tax)}. {memo}"
    )
    draft = BillDraft(
        vendor_name=outcome.vendor_name,
        vendor_id=outcome.vendor_id,
        invoice_number=outcome.invoice_number,
        txn_date=outcome.txn_date,
        total=fields.total,
        po_number=outcome.po_number,
        memo=memo,
        line_description=description,
        currency="CAD",
        qbo_customer_id=outcome.qbo_customer_id,
        expense_account_id=config.expense_account_id,
    )
    # Record the intent before the create call. If the bill lands in QuickBooks
    # and this process dies before the bill id is saved, the next run attaches
    # that bill instead of creating another one.
    state.upsert_message(
        message.id,
        phase="creating",
        decision="processed",
        reasons=[],
        vendor_name=outcome.vendor_name,
        invoice_number=outcome.invoice_number,
        total=money_to_json_number(fields.total),
    )
    bill = qbo.create_bill(draft)
    state.add_bill(bill)
    state.upsert_message(
        message.id,
        phase="in_progress",
        decision="processed",
        bill_id=bill.id,
        reasons=[],
        vendor_name=bill.vendor_name,
        invoice_number=bill.invoice_number,
        total=money_to_json_number(bill.total),
    )
    try:
        attachment_id = qbo.attach_pdf(bill.id, safe_filename(pdfs[0].filename), pdfs[0].content)
    except Exception as exc:  # noqa: BLE001 — keep the bill and retry the upload next run
        return (
            RunRecord(
                message_id=message.id,
                from_email=message.from_email,
                subject=message.subject,
                decision="error",
                reasons=[_safe_error(exc)],
                bill_id=bill.id,
                vendor_name=bill.vendor_name,
                invoice_number=bill.invoice_number,
                total=money_to_json_number(bill.total),
            ),
            1,
        )
    state.mark_attachment(bill.id, attachment_id, bill.attachment_sha256 or "", safe_filename(pdfs[0].filename))
    state.upsert_message(
        message.id,
        phase="completed",
        decision="processed",
        bill_id=bill.id,
        attachment_id=attachment_id,
        reasons=[],
        vendor_name=bill.vendor_name,
        invoice_number=bill.invoice_number,
        total=money_to_json_number(bill.total),
    )
    mail.move(message.id, "processed")
    return (
        RunRecord(
            message_id=message.id,
            from_email=message.from_email,
            subject=message.subject,
            decision="processed",
            bill_id=bill.id,
            vendor_name=bill.vendor_name,
            invoice_number=bill.invoice_number,
            total=money_to_json_number(bill.total),
        ),
        1,
    )


def _resume_attachment(message, *, mail, qbo, state, prior) -> tuple[RunRecord, int]:
    pdfs = [item for item in message.attachments if item.filename.lower().endswith(".pdf")]
    if len(pdfs) != 1:
        return (
            RunRecord(
                message_id=message.id,
                from_email=message.from_email,
                subject=message.subject,
                decision="error",
                reasons=["attachment_retry_needs_one_pdf"],
                bill_id=prior.get("bill_id"),
            ),
            0,
        )
    try:
        attachment_id = qbo.attach_pdf(prior["bill_id"], safe_filename(pdfs[0].filename), pdfs[0].content)
    except Exception as exc:  # noqa: BLE001 — report the existing bill id instead of hiding it
        return (
            RunRecord(
                message_id=message.id,
                from_email=message.from_email,
                subject=message.subject,
                decision="error",
                reasons=[_safe_error(exc)],
                bill_id=prior.get("bill_id"),
                vendor_name=prior.get("vendor_name") or None,
                invoice_number=prior.get("invoice_number") or None,
                total=prior.get("total") or None,
            ),
            0,
        )
    bill = _find_bill(qbo, prior["bill_id"])
    digest = "" if bill is None else (bill.attachment_sha256 or "")
    state.mark_attachment(prior["bill_id"], attachment_id, digest, safe_filename(pdfs[0].filename))
    state.upsert_message(
        message.id,
        phase="completed",
        decision="processed",
        bill_id=prior["bill_id"],
        attachment_id=attachment_id,
    )
    mail.move(message.id, "processed")
    return (
        RunRecord(
            message_id=message.id,
            from_email=message.from_email,
            subject=message.subject,
            decision="processed",
            bill_id=prior["bill_id"],
            vendor_name=prior.get("vendor_name") or None,
            invoice_number=prior.get("invoice_number") or None,
            total=prior.get("total") or None,
        ),
        0,
    )


def _reject(message, reasons, *, mail, state, config, fields: InvoiceFields | None, invoice_number=None) -> tuple[RunRecord, int]:
    duplicate = bool(reasons) and set(reasons) <= _DUPLICATES
    if config.dry_run:
        decision = "would_duplicate" if duplicate else "would_fail"
    else:
        decision = "duplicate" if duplicate else "failed"
    number = invoice_number
    if number is None and fields is not None:
        number = fields.invoice_number
    subject, body = render_reply(reasons, invoice_number=number, company_name=config.company_name)
    mail.deliver_reply(message, subject, body, dry_run=config.dry_run)
    if config.dry_run:
        total = None if fields is None or fields.total is None else money_to_json_number(fields.total)
        return (
            RunRecord(
                message_id=message.id,
                from_email=message.from_email,
                subject=message.subject,
                decision=decision,
                reasons=list(reasons),
                vendor_name=None if fields is None else fields.vendor_name,
                invoice_number=number,
                total=total,
            ),
            0,
        )
    state.upsert_message(
        message.id,
        phase="replying",
        decision=decision,
        reasons=list(reasons),
        bill_id=None,
        vendor_name=None if fields is None else fields.vendor_name,
        invoice_number=number,
        total=None if fields is None or fields.total is None else money_to_json_number(fields.total),
    )
    mail.move(message.id, "failed")
    total = None if fields is None or fields.total is None else money_to_json_number(fields.total)
    vendor_name = None if fields is None else fields.vendor_name
    state.upsert_message(
        message.id,
        phase="completed",
        decision=decision,
        reasons=list(reasons),
        bill_id=None,
        vendor_name=vendor_name,
        invoice_number=number,
        total=total,
    )
    return (
        RunRecord(
            message_id=message.id,
            from_email=message.from_email,
            subject=message.subject,
            decision=decision,
            reasons=list(reasons),
            vendor_name=vendor_name,
            invoice_number=number,
            total=total,
        ),
        0,
    )


def _combined_ledger(state, qbo) -> list:
    merged = {}
    for bill in [*state.bills, *qbo.find_bills()]:
        current = merged.get(bill.id)
        if current is None or (not current.vendor_name and bill.vendor_name):
            merged[bill.id] = bill
    return list(merged.values())


def _matching_bill(qbo, vendor_name: str | None, invoice_number: str | None, state=None):
    if not vendor_name or not invoice_number:
        return None
    wanted_vendor = vendor_key(vendor_name)
    wanted_number = invoice_key(invoice_number)
    bills = _combined_ledger(state, qbo) if state is not None else qbo.find_bills()
    unnamed = []
    for bill in bills:
        if invoice_key(bill.invoice_number) != wanted_number:
            continue
        if bill.vendor_name and vendor_key(bill.vendor_name) == wanted_vendor:
            return bill
        if not bill.vendor_name:
            unnamed.append(bill)
    if len(unnamed) == 1:
        return unnamed[0]
    if len(unnamed) > 1:
        raise PipelineError(
            "More than one QuickBooks bill has this invoice number and no vendor name was returned"
        )
    return None


def _sender_mismatch(from_email: str, vendor_name: str | None, vendors) -> bool:
    vendor = vendors.resolve(vendor_name)
    if vendor is None or not vendor.email_domains:
        return False
    if "@" not in from_email:
        return True
    domain = from_email.rsplit("@", 1)[1].casefold().strip()
    return domain not in vendor.email_domains


def _safe_error(exc: Exception) -> str:
    text = re.sub(r"Bearer\s+\S+", "Bearer [redacted]", f"{exc.__class__.__name__}: {exc}")
    return text[:180]


def _refile(mail, message_id: str, decision: str | None) -> None:
    if decision == "processed":
        mail.move(message_id, "processed")
    elif decision in {"failed", "duplicate"}:
        mail.move(message_id, "failed")


def _find_bill(qbo, bill_id: str):
    for bill in qbo.find_bills():
        if bill.id == bill_id:
            return bill
    return None
