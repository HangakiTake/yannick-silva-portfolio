"""Run the inquiry workflow locally. Drafts are saved. Nothing is sent."""

from __future__ import annotations

import json

from .models import InquiryFields
from .paths import CONFIG
from .redact import redact

_PROMPT = json.loads((CONFIG / "prompts.json").read_text(encoding="utf-8"))["inquiry_system"]


class Sheet:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def append(self, row: dict) -> None:
        self.rows.append(row)


class Mailbox:
    """Draft store. There is no send method on purpose."""

    def __init__(self) -> None:
        self.drafts: list[dict] = []

    def save_draft(self, draft: dict) -> dict:
        saved = {**draft, "id": f"draft-{len(self.drafts) + 1}", "status": "draft_awaiting_approval"}
        self.drafts.append(saved)
        return saved


def process_inquiry(email: dict, llm, sheet: Sheet | None = None, mailbox: Mailbox | None = None) -> dict:
    sheet = sheet or Sheet()
    mailbox = mailbox or Mailbox()
    subject = redact(str(email.get("subject", "")))
    body = redact(str(email.get("body", "")))
    sender = redact(f"{email.get('from_name', '')} <{email.get('from_email', '')}>")
    user = f"From: {sender.text}\nSubject: {subject.text}\n\n{body.text}"
    fields = InquiryFields.model_validate(llm.complete({"system": _PROMPT, "user": user}))
    if not fields.awaiting_approval():
        raise RuntimeError("Draft is missing the not-sent line. Refusing to store it.")
    draft = mailbox.save_draft(
        {
            "to": sender.text,
            "subject": fields.draft_subject,
            "body": fields.draft_body,
            "sent": False,
        }
    )
    sheet.append(
        {
            "id": email.get("id"),
            "category": fields.category,
            "urgency": fields.urgency,
            "service": fields.service,
            "sender": sender.text,
            "subject": subject.text,
            "draft_status": draft["status"],
            "sent": False,
        }
    )
    return {
        "id": email.get("id"),
        "status": "draft_awaiting_approval",
        "sent": False,
        "category": fields.category,
        "urgency": fields.urgency,
        "service": fields.service,
        "draft_body": fields.draft_body,
    }


def run_inquiries(emails: list[dict], llm) -> dict:
    sheet, mailbox = Sheet(), Mailbox()
    results = [process_inquiry(email, llm, sheet, mailbox) for email in emails]
    sent = [row for row in sheet.rows if row["sent"]] + [d for d in mailbox.drafts if d.get("sent")]
    return {"results": results, "sheet": sheet, "mailbox": mailbox, "sent": sent}
