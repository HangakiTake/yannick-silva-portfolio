"""Routing, duplicates, idempotency, attachments, and messy mailbox cases."""

from __future__ import annotations

import json
import shutil
from decimal import Decimal
from pathlib import Path

import pytest

from ap_pipeline.adapters.mail_local import safe_filename, safe_message_id
from ap_pipeline.adapters.qbo_mock import MockQBOClient
from ap_pipeline.reasons import REASON_TEXT
from tests.conftest import FIXTURES, copy_mail, run_demo


def test_corpus_has_thirty_synthetic_invoices(manifest):
    assert len(manifest["invoices"]) == 30
    assert {item["expected_decision"] for item in manifest["invoices"]} == {"processed", "failed", "duplicate"}


def test_seeded_failures_duplicates_and_bills(tmp_path, vendors, jobs, manifest):
    mail_root = copy_mail(tmp_path)
    summary, qbo = run_demo(mail_root, tmp_path, vendors=vendors, jobs=jobs)
    by_id = summary.results_by_id
    assert summary.bills_created == 16
    assert qbo.creates == 16
    for item in manifest["invoices"]:
        record = by_id[item["message_id"]]
        assert record.decision == item["expected_decision"]
        assert record.reasons == item["expected_reasons"]
        if item["expected_decision"] == "processed":
            assert record.bill_id
            bill = next(bill for bill in qbo.bills if bill.id == record.bill_id)
            pdf = (mail_root / "Processed Invoices" / item["message_id"] / "invoice.pdf").read_bytes()
            assert bill.attachment_bytes == pdf
            assert bill.total == Decimal(item["truth"]["total"])
            assert bill.vendor_name == item["truth"]["vendor_name"]
            assert bill.invoice_number == item["truth"]["invoice_number"]
            assert bill.po_number in bill.memo
            assert bill.memo.split(" ", 1)[1]
        else:
            assert record.bill_id is None
            reply = (mail_root / "outbox" / "sent" / f"{item['message_id']}.txt").read_text(encoding="utf-8")
            bullets = [line for line in reply.splitlines() if line.startswith("- ")]
            assert bullets == [f"- {REASON_TEXT[code]}" for code in item["expected_reasons"]]
            assert (mail_root / "Failed Invoices" / item["message_id"]).is_dir()


def test_second_run_and_replay_create_no_bills(tmp_path, vendors, jobs):
    mail_root = copy_mail(tmp_path)
    state = tmp_path / "state.json"
    logs = tmp_path / "logs"
    qbo = MockQBOClient()
    first, _ = run_demo(mail_root, tmp_path, qbo=qbo, vendors=vendors, jobs=jobs, name="first")
    assert first.bills_created == 16
    # Point both runs at the same state file. run_demo uses work/name-state.json.
    # Re-run by calling run_demo with the same name after the inbox is empty,
    # then copy the pristine inbox back.
    second, _ = run_demo(mail_root, tmp_path, qbo=qbo, vendors=vendors, jobs=jobs, name="first")
    assert second.bills_created == 0
    assert second.records == []
    shutil.copytree(FIXTURES / "mail" / "inbox", mail_root / "inbox", dirs_exist_ok=True)
    third, _ = run_demo(mail_root, tmp_path, qbo=qbo, vendors=vendors, jobs=jobs, name="first")
    assert third.bills_created == 0
    assert qbo.creates == 16
    assert {record.decision for record in third.records} == {"already_processed"}
    sent_after = list((mail_root / "outbox" / "sent").glob("*.txt"))
    assert len(sent_after) == 14
    del state, logs


def test_lost_state_still_blocks_a_second_bill(tmp_path, vendors, jobs):
    mail_root = copy_mail(tmp_path)
    qbo = MockQBOClient()
    first, _ = run_demo(mail_root, tmp_path, qbo=qbo, vendors=vendors, jobs=jobs, name="kept")
    assert first.bills_created == 16
    (tmp_path / "kept-state.json").unlink()
    shutil.copytree(FIXTURES / "mail" / "inbox", mail_root / "inbox", dirs_exist_ok=True)
    second, _ = run_demo(mail_root, tmp_path, qbo=qbo, vendors=vendors, jobs=jobs, name="kept")
    assert second.bills_created == 0
    assert qbo.creates == 16
    processed = [record for record in second.records if record.prior_decision == "processed" or record.decision == "duplicate"]
    assert any(record.decision == "duplicate" for record in processed)


def test_attachment_failure_retries_without_a_second_bill(tmp_path, vendors, jobs):
    mail_root = _one_message(tmp_path, "msg-01")
    inner = MockQBOClient()

    class AttachFailsOnce:
        def __init__(self):
            self.attach_calls = 0

        def load_ledger(self, bills):
            inner.load_ledger(bills)

        def find_bills(self, vendor_name=None):
            return inner.find_bills(vendor_name)

        def create_bill(self, draft):
            return inner.create_bill(draft)

        def attach_pdf(self, bill_id, filename, content):
            self.attach_calls += 1
            if self.attach_calls == 1:
                raise RuntimeError("upload failed")
            return inner.attach_pdf(bill_id, filename, content)

    wrapper = AttachFailsOnce()
    first, _ = run_demo(mail_root, tmp_path, qbo=wrapper, vendors=vendors, jobs=jobs, name="retry")
    assert first.bills_created == 1
    assert first.records[0].decision == "error"
    assert (mail_root / "inbox" / "msg-01").is_dir()
    second, _ = run_demo(mail_root, tmp_path, qbo=wrapper, vendors=vendors, jobs=jobs, name="retry")
    assert second.bills_created == 0
    assert inner.creates == 1
    assert second.records[0].decision == "processed"
    assert inner.bills[0].attachment_bytes is not None
    assert (mail_root / "Processed Invoices" / "msg-01").is_dir()


def test_dry_run_does_not_create_a_bill_or_file_a_valid_invoice(tmp_path, vendors, jobs):
    mail_root = _one_message(tmp_path, "msg-01")
    summary, qbo = run_demo(mail_root, tmp_path, vendors=vendors, jobs=jobs, dry_run=True, name="drypass")
    assert summary.records[0].decision == "would_process"
    assert summary.bills_created == 0
    assert qbo.creates == 0
    assert (mail_root / "inbox" / "msg-01").is_dir()
    assert not (mail_root / "Processed Invoices").exists()


def test_dry_run_drafts_the_reply_and_still_files_the_email(tmp_path, vendors, jobs):
    mail_root = _one_message(tmp_path, "msg-17")
    summary, qbo = run_demo(mail_root, tmp_path, vendors=vendors, jobs=jobs, dry_run=True, name="dry")
    assert summary.records[0].decision == "would_fail"
    assert summary.records[0].reasons == ["missing_po"]
    assert qbo.creates == 0
    assert (mail_root / "outbox" / "drafts" / "msg-17.txt").is_file()
    assert not (mail_root / "outbox" / "sent").exists()
    assert (mail_root / "inbox" / "msg-17").is_dir()
    assert not (mail_root / "Failed Invoices").exists()


def test_run_log_has_decision_reasons_and_bill_id(tmp_path, vendors, jobs):
    mail_root = copy_mail(tmp_path)
    summary, _ = run_demo(mail_root, tmp_path, vendors=vendors, jobs=jobs, name="logged")
    log_dir = tmp_path / "logged-logs"
    payload = json.loads(next(log_dir.glob("run-*.json")).read_text(encoding="utf-8"))
    assert payload["live_apis"] == "not_used"
    assert payload["bills_created"] == summary.bills_created
    failed = next(row for row in payload["records"] if row["message_id"] == "msg-17")
    assert failed["decision"] == "failed"
    assert failed["reasons"] == ["missing_po"]
    assert failed["bill_id"] == ""
    passed = next(row for row in payload["records"] if row["message_id"] == "msg-01")
    assert passed["bill_id"].startswith("mock-bill-")
    csv_text = next(log_dir.glob("run-*.csv")).read_text(encoding="utf-8")
    assert "decision,reasons,bill_id" in csv_text.replace(" ", "")


def test_no_pdf_and_two_pdfs_do_not_create_bills(tmp_path, vendors, jobs):
    mail_root = tmp_path / "mail"
    inbox = mail_root / "inbox"
    _write(inbox / "msg-none", [])
    pdf = (FIXTURES / "mail" / "inbox" / "msg-01" / "invoice.pdf").read_bytes()
    _write(inbox / "msg-two", [("a.pdf", pdf), ("b.pdf", pdf)])
    summary, qbo = run_demo(mail_root, tmp_path, vendors=vendors, jobs=jobs, name="shapes")
    by_id = summary.results_by_id
    assert by_id["msg-none"].reasons == ["missing_pdf"]
    assert by_id["msg-two"].reasons == ["multiple_pdf_attachments"]
    assert qbo.creates == 0


def test_unreadable_pdf_is_failed_closed(tmp_path, vendors, jobs):
    mail_root = tmp_path / "mail"
    _write(mail_root / "inbox" / "msg-bad", [("invoice.pdf", b"this is not a pdf")])
    summary, qbo = run_demo(mail_root, tmp_path, vendors=vendors, jobs=jobs, name="badpdf")
    assert summary.records[0].reasons == ["unreadable_pdf"]
    assert qbo.creates == 0


def test_bill_created_before_state_saved_is_not_created_again(tmp_path, vendors, jobs):
    from ap_pipeline.models import BillDraft
    from ap_pipeline.state import StateStore

    mail_root = _one_message(tmp_path, "msg-01")
    qbo = MockQBOClient()
    qbo.create_bill(
        BillDraft(
            vendor_name="Cedarline Supply Co.",
            vendor_id="v-cedarline",
            invoice_number="INV-1001",
            txn_date="2026-03-01",
            total=Decimal("1050.00"),
            po_number="PO-2401",
            memo="PO-2401 Maple Street re-roof",
            line_description="already created",
        )
    )
    StateStore(tmp_path / "creating-state.json").upsert_message(
        "msg-01",
        phase="creating",
        decision="processed",
        vendor_name="Cedarline Supply Co.",
        invoice_number="INV-1001",
        total="1050.00",
        reasons=[],
    )
    summary, _ = run_demo(mail_root, tmp_path, qbo=qbo, vendors=vendors, jobs=jobs, name="creating")
    assert qbo.creates == 1
    assert summary.bills_created == 0
    assert summary.records[0].decision == "processed"
    assert summary.records[0].bill_id == "mock-bill-0001"
    assert qbo.bills[0].attachment_bytes is not None
    assert (mail_root / "Processed Invoices" / "msg-01").is_dir()


def test_reply_recorded_as_sent_is_not_sent_again(tmp_path, vendors, jobs):
    mail_root = _one_message(tmp_path, "msg-17")
    from ap_pipeline.state import StateStore

    StateStore(tmp_path / "reply-state.json").upsert_message(
        "msg-17",
        phase="replying",
        decision="failed",
        reasons=["missing_po"],
    )
    summary, qbo = run_demo(mail_root, tmp_path, vendors=vendors, jobs=jobs, name="reply")
    assert summary.bills_created == 0
    assert qbo.creates == 0
    assert summary.records[0].decision == "already_processed"
    assert not (mail_root / "outbox" / "sent").exists()
    assert (mail_root / "Failed Invoices" / "msg-17").is_dir()


def test_sender_domain_must_match_the_vendor(tmp_path, vendors, jobs):
    mail_root = _one_message(tmp_path, "msg-01")
    message = json.loads((mail_root / "inbox" / "msg-01" / "message.json").read_text(encoding="utf-8"))
    message["from_email"] = "ap@evil.example"
    (mail_root / "inbox" / "msg-01" / "message.json").write_text(json.dumps(message), encoding="utf-8")
    summary, qbo = run_demo(mail_root, tmp_path, vendors=vendors, jobs=jobs, name="sender")
    assert summary.records[0].reasons == ["sender_not_vendor"]
    assert qbo.creates == 0


def test_second_process_cannot_lock_the_same_state_file(tmp_path):
    from ap_pipeline.errors import PipelineError
    from ap_pipeline.state import StateStore

    path = tmp_path / "state.json"
    first = StateStore(path)
    try:
        lock = path.with_name(path.name + ".lock")
        lock.write_text("1", encoding="ascii")
        with pytest.raises(PipelineError):
            StateStore(path)
    finally:
        first.close()


def test_message_ids_and_filenames_cannot_escape_the_mail_root():
    assert safe_filename("../etc/passwd.pdf") == "passwd.pdf"
    assert safe_filename("INV 1001.pdf") == "INV_1001.pdf"
    with pytest.raises(ValueError):
        safe_message_id("../escape")


def _one_message(tmp_path: Path, message_id: str) -> Path:
    destination = tmp_path / "mail"
    source = FIXTURES / "mail" / "inbox" / message_id
    target = destination / "inbox" / message_id
    target.mkdir(parents=True)
    shutil.copytree(source, target, dirs_exist_ok=True)
    return destination


def _write(folder: Path, pdfs: list[tuple[str, bytes]]) -> None:
    folder.mkdir(parents=True)
    (folder / "message.json").write_text(
        json.dumps(
            {
                "id": folder.name,
                "from_name": "Cedarline Supply Accounts",
                "from_email": "ap@cedarline-supply.example",
                "subject": "Invoice",
                "received_at": "2026-03-02T15:00:00Z",
                "body": "Please see the attached invoice.",
            }
        ),
        encoding="utf-8",
    )
    for name, content in pdfs:
        (folder / name).write_bytes(content)
