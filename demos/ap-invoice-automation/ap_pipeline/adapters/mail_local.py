"""Read and file invoices from a local directory. This is the tested mail adapter."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from ap_pipeline.dates import parse_received_at
from ap_pipeline.models import Attachment, EmailMessage

_SAFE_ID = re.compile(r"[A-Za-z0-9._-]{1,80}")
PROCESSED_FOLDER = "Processed Invoices"
FAILED_FOLDER = "Failed Invoices"


class LocalFolderMailSource:
    name = "local"

    def __init__(self, root: Path) -> None:
        self.root = root
        self.inbox = root / "inbox"
        self.processed = root / PROCESSED_FOLDER
        self.failed = root / FAILED_FOLDER
        self.sent = root / "outbox" / "sent"
        self.drafts = root / "outbox" / "drafts"
        self.read_errors: list[tuple[str, Exception]] = []

    def list_messages(self) -> list[EmailMessage]:
        self.read_errors = []
        if not self.inbox.exists():
            return []
        messages: list[EmailMessage] = []
        for folder in sorted(path for path in self.inbox.iterdir() if path.is_dir()):
            try:
                resolved = folder.resolve()
                resolved.relative_to(self.inbox.resolve())
                messages.append(_read_message(folder))
            except Exception as exc:  # noqa: BLE001 — one bad folder must not drop the rest
                self.read_errors.append((folder.name, exc))
        return messages

    def move(self, message_id: str, destination: str) -> None:
        safe = safe_message_id(message_id)
        source = self.inbox / safe
        if not source.exists():
            return
        if destination == "processed":
            target_root = self.processed
        elif destination == "failed":
            target_root = self.failed
        else:
            raise ValueError(f"Unknown mail destination {destination}")
        target_root.mkdir(parents=True, exist_ok=True)
        target = target_root / safe
        if target.exists():
            shutil.rmtree(source)
            return
        shutil.move(str(source), str(target))

    def deliver_reply(self, message: EmailMessage, subject: str, body: str, *, dry_run: bool) -> Path:
        bucket = self.drafts if dry_run else self.sent
        bucket.mkdir(parents=True, exist_ok=True)
        path = bucket / f"{safe_message_id(message.id)}.txt"
        path.write_text(
            f"To: {message.from_name} <{message.from_email}>\nSubject: {subject}\n\n{body}",
            encoding="utf-8",
        )
        return path


def safe_message_id(message_id: str) -> str:
    if _SAFE_ID.fullmatch(message_id) is None or message_id in {".", ".."}:
        raise ValueError(f"Unsafe message id: {message_id!r}")
    return message_id


def safe_filename(filename: str) -> str:
    base = Path(filename).name
    if base in {"", ".", ".."}:
        base = "invoice.pdf"
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", base)
    if not cleaned.lower().endswith(".pdf"):
        cleaned += ".pdf"
    return cleaned


def _read_message(folder: Path) -> EmailMessage:
    payload = json.loads((folder / "message.json").read_text(encoding="utf-8"))
    attachments = []
    for path in sorted(folder.iterdir()):
        if path.is_file() and path.suffix.lower() == ".pdf":
            attachments.append(
                Attachment(filename=path.name, content=path.read_bytes(), content_type="application/pdf")
            )
    message_id = payload["id"]
    safe_message_id(message_id)
    if folder.name != message_id:
        raise ValueError(f"Folder {folder.name} does not match message id {message_id}")
    return EmailMessage(
        id=message_id,
        from_name=payload.get("from_name", ""),
        from_email=payload["from_email"],
        subject=payload.get("subject", ""),
        received_at=parse_received_at(payload["received_at"]),
        body=payload.get("body", ""),
        attachments=tuple(attachments),
    )
