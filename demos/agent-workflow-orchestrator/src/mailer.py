"""Approval gate. deliver() is the only send, and it refuses without a matching approval."""

from __future__ import annotations

from src.auditlog import AuditLog
from src.store import Store


class ApprovalRequired(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class VerificationFailed(Exception):
    pass


def approve(store: Store, draft_id: str, by_name: str, audit: AuditLog) -> dict:
    name = str(by_name).strip()
    if not name:
        raise ValueError("approver name required")
    draft = store.get_draft(draft_id)
    if draft is None:
        raise ValueError("unknown draft")
    saved = store.save_approval(draft_id, name, draft["body_sha256"])
    audit.record(
        step="approve",
        key=draft_id,
        input=draft["email"],
        result="approved",
        actor=name,
        verified=True,
    )
    return saved


def deliver(store: Store, draft_id: str) -> tuple[dict, bool]:
    """Put an approved draft in the outbox and read it back.

    Returns (row, created). created is False when the same message is already there.
    Raises ApprovalRequired when a person has not approved this exact body.
    """
    draft = store.get_draft(draft_id)
    if draft is None:
        raise ApprovalRequired("unknown draft")
    approval = store.get_approval(draft_id)
    if approval is None or not str(approval["by_name"]).strip():
        raise ApprovalRequired("no approval")
    if approval["body_sha256"] != draft["body_sha256"]:
        raise ApprovalRequired("approval does not match draft")

    existing = store.get_outbox_by_draft(draft_id)
    if existing:
        if existing["body"] != draft["body"] or existing["email"] != draft["email"]:
            raise ApprovalRequired("outbox does not match draft")
        read_back = store.get_outbox(existing["id"])
        if read_back is None or read_back["body"] != draft["body"]:
            raise VerificationFailed("outbox read-back failed")
        if draft["status"] != "sent":
            store.mark_draft_sent(draft_id)
        return existing, False

    stored = store.insert_outbox(draft)
    read_back = store.get_outbox(stored["id"])
    if (
        read_back is None
        or read_back["body"] != draft["body"]
        or read_back["email"] != draft["email"]
        or read_back["draft_id"] != draft["id"]
    ):
        raise VerificationFailed("outbox read-back failed")
    store.mark_draft_sent(draft_id)
    return stored, True
