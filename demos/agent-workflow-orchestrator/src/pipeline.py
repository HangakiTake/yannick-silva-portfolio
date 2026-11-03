"""Six steps per lead: intake, CRM, missing-info task, calendar, draft, send."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from src.auditlog import AuditLog
from src.calendar_mock import CalendarFailed, MockCalendar
from src.drafting import render
from src.mailer import ApprovalRequired, VerificationFailed, deliver
from src.normalize import canonicalize, idempotency_key, merge, missing_fields, same_lead
from src.store import Store

OWNER = "Priya Shah"
_SCHEDULE = {"intent": "discovery"}


def run(
    inbox: Path | str,
    store: Store,
    audit: AuditLog,
    *,
    crash_after: int | None = None,
    halt_after_write: str | None = None,
    retry_escalated: bool = False,
    sleep=None,
    base_delay: float = 0.05,
    failures: dict | None = None,
) -> dict:
    if sleep is None:
        import time

        sleep = time.sleep
    rows = json.loads(Path(inbox).read_text(encoding="utf-8"))
    calendar = MockCalendar(store, failures=failures, sleep=sleep, base_delay=base_delay)
    stats = {
        "crm_writes": 0,
        "task_writes": 0,
        "event_writes": 0,
        "email_writes": 0,
        "attempts": calendar.attempts,
    }
    completed = 0

    def note(step: str, key: str, email: str, result: str, verified: bool | None = None) -> None:
        fields = {
            "step": step,
            "key": key,
            "input": email,
            "result": result,
            "actor": "agent",
        }
        if verified is not None:
            fields["verified"] = verified
        audit.record(**fields)

    def checkpoint() -> None:
        nonlocal completed
        completed += 1
        store.conn.commit()
        if crash_after is not None and completed >= crash_after:
            raise SystemExit(2)

    for raw in rows:
        try:
            incoming = canonicalize(raw)
        except ValueError:
            raw_email = str(raw.get("email", ""))
            store.reject(raw_email, "unusable email")
            stored = store.get_rejection(raw_email)
            ok = stored is not None and stored["reason"] == "unusable email"
            note(
                "intake",
                hashlib.sha256(f"reject|{raw_email}".encode()).hexdigest(),
                raw_email,
                "rejected: unusable email",
                ok,
            )
            continue
        email = incoming["email"]
        merged = merge(store.get_accepted(email), incoming)
        _intake(store, note, checkpoint, email, incoming, merged)
        _register(store, stats, note, checkpoint, email, incoming)
        lead = store.get_crm(email) or merged
        _missing(store, stats, note, checkpoint, email, lead)
        _schedule(
            store,
            calendar,
            stats,
            note,
            checkpoint,
            email,
            retry_escalated=retry_escalated,
            halt_after_write=halt_after_write,
        )
        lead = store.get_crm(email) or lead
        _draft(store, note, checkpoint, lead)
        _send(store, stats, note, checkpoint, email)

    store.conn.commit()
    return stats


def _intake(store, note, checkpoint, email, incoming, merged) -> None:
    key = idempotency_key("intake", email, incoming)
    if store.ledger_status(key) == "done":
        note("intake", key, email, "skipped")
        return
    store.upsert_accepted(merged)
    if not same_lead(store.get_accepted(email), merged):
        note("intake", key, email, "read-back mismatch", False)
        return
    store.mark_ledger(key, "intake", email, "done", "accepted")
    note("intake", key, email, "accepted", True)
    checkpoint()


def _register(store, stats, note, checkpoint, email, incoming) -> None:
    key = idempotency_key("register", email, incoming)
    if store.ledger_status(key) == "done":
        note("register", key, email, "skipped")
        return
    merged = merge(store.get_crm(email), incoming)
    wrote = store.upsert_crm(merged)
    if not same_lead(store.get_crm(email), merged):
        note("register", key, email, "read-back mismatch", False)
        return
    store.mark_ledger(key, "register", email, "done", "upserted")
    note("register", key, email, "upserted", True)
    if wrote:
        stats["crm_writes"] += 1
    checkpoint()


def _missing(store, stats, note, checkpoint, email, lead) -> None:
    missing = missing_fields(lead)
    key = idempotency_key("request_missing", email, {"missing": missing})
    if store.ledger_status(key) == "done":
        note("request_missing", key, email, "skipped")
        return
    if missing:
        wrote = store.upsert_task(email, missing)
        read = store.get_task(email)
        ok = read is not None and json.loads(read["missing"]) == missing
        result = "task opened"
        verified = True if ok else False
    else:
        wrote = store.delete_task(email)
        ok = store.get_task(email) is None
        result = "nothing missing" if not wrote else "task closed"
        verified = True if wrote else None
    if not ok:
        note("request_missing", key, email, "read-back mismatch", False)
        return
    store.mark_ledger(key, "request_missing", email, "done", result)
    note("request_missing", key, email, result, verified)
    if wrote:
        stats["task_writes"] += 1
    checkpoint()


def _schedule(store, calendar, stats, note, checkpoint, email, *, retry_escalated, halt_after_write):
    key = idempotency_key("schedule", email, _SCHEDULE)
    status = store.ledger_status(key)
    if status == "done":
        note("schedule", key, email, "skipped")
        return None
    if status == "escalated" and not retry_escalated:
        note("schedule", key, email, "skipped: escalated")
        return None

    def on_attempt(attempt: int, outcome: str) -> None:
        note("schedule", key, email, f"attempt {attempt} {outcome}", False)

    try:
        event, wrote = calendar.book(email, on_attempt)
    except CalendarFailed as exc:
        store.add_exception(
            "schedule",
            email,
            OWNER,
            f"calendar failed after {exc.attempts} attempts: {exc.detail}",
        )
        store.mark_ledger(key, "schedule", email, "escalated", exc.detail)
        note("schedule", key, email, "escalated", False)
        checkpoint()
        return None

    if halt_after_write == "schedule" and wrote:
        store.conn.commit()
        raise SystemExit(2)

    read = store.get_event(email)
    if read is None or read["slot"] != event["slot"] or read["email"] != email:
        note("schedule", key, email, "read-back mismatch", False)
        return None
    store.delete_exception("schedule", email)
    store.mark_ledger(key, "schedule", email, "done", event["slot"])
    note("schedule", key, email, "booked", True)
    if wrote:
        stats["event_writes"] += 1
    checkpoint()
    return event


def _draft(store, note, checkpoint, lead) -> None:
    email = lead["email"]
    event = store.get_event(email)
    missing = missing_fields(lead)
    body = render(lead, event, missing)
    digest = hashlib.sha256(body.encode()).hexdigest()
    key = idempotency_key("draft", email, {"body_sha256": digest})
    if store.ledger_status(key) == "done":
        note("draft", key, email, "skipped")
        return
    existing = store.get_draft_by_email(email)
    if existing and existing["status"] == "sent" and existing["body"] != body:
        store.add_exception(
            "draft",
            email,
            OWNER,
            "sent text kept; the lead changed and needs a new approval",
        )
        store.mark_ledger(key, "draft", email, "done", "kept sent draft")
        note("draft", key, email, "kept sent draft; needs a new approval", False)
        checkpoint()
        return
    store.upsert_draft(email, body, digest)
    read = store.get_draft_by_email(email)
    if read is None or read["body"] != body:
        note("draft", key, email, "read-back mismatch", False)
        return
    store.mark_ledger(key, "draft", email, "done", digest)
    note("draft", key, email, "drafted", True)
    checkpoint()


def _send(store, stats, note, checkpoint, email) -> None:
    draft = store.get_draft_by_email(email)
    if draft is None:
        note("send", "", email, "skipped: no draft")
        return
    key = idempotency_key(
        "send",
        email,
        {"draft_id": draft["id"], "body_sha256": draft["body_sha256"]},
    )
    if store.ledger_status(key) == "done":
        note("send", key, email, "skipped")
        return
    try:
        sent, created = deliver(store, draft["id"])
    except ApprovalRequired as exc:
        note("send", key, email, f"refused: {exc.reason}", False)
        return
    except VerificationFailed:
        note("send", key, email, "read-back mismatch", False)
        return
    read = store.get_outbox(sent["id"])
    if read is None or read["body"] != draft["body"] or read["email"] != email:
        note("send", key, email, "read-back mismatch", False)
        return
    store.mark_ledger(key, "send", email, "done", sent["id"])
    note("send", key, email, "sent", True)
    if created:
        stats["email_writes"] += 1
    checkpoint()
