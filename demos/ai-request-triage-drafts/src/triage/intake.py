"""Read an inbox of EML files, JSON exports and a web-form CSV."""

import csv
import email.policy
import json
import re
from dataclasses import dataclass, field
from email.utils import parseaddr
from pathlib import Path

from triage.textutil import customer_text, html_to_text

_ADDRESS = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

MAX_BODY = 50_000


@dataclass
class Request:
    id: str
    source: str
    sender_name: str = ""
    sender_email: str = ""
    reply_name: str = ""
    reply_email: str = ""
    subject: str = ""
    body_text: str = ""
    preferred_date: str = ""
    supplied_phone: str = ""
    supplied_company: str = ""
    attachments: list[str] = field(default_factory=list)
    truncated: bool = False
    parse_error: str = ""
    force_human: bool = False

    @property
    def search_text(self) -> str:
        return "\n".join(
            (
                self.body_text,
                self.subject,
                self.preferred_date,
                self.sender_name,
                self.sender_email,
                self.reply_name,
                self.reply_email,
                self.supplied_phone,
                self.supplied_company,
                " ".join(self.attachments),
            )
        )


def _address(value: str) -> tuple[str, str]:
    name, address = parseaddr(value or "")
    return " ".join(name.split()), address.strip().casefold()


def _decode_part(part) -> str:
    try:
        content = part.get_content()
    except (KeyError, LookupError, UnicodeError, ValueError):
        content = None
    if isinstance(content, str):
        return content
    payload = part.get_payload(decode=True) or b""
    charset = part.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")


def _bodies(message) -> tuple[str, list[str]]:
    plain: list[str] = []
    html_parts: list[str] = []
    attachments: list[str] = []
    unclosed = False
    parts = message.walk() if message.is_multipart() else [message]
    for part in parts:
        filename = part.get_filename()
        if filename:
            attachments.append(filename)
        if part.get_content_disposition() == "attachment":
            continue
        if part.get_content_maintype() == "multipart":
            continue
        content = _decode_part(part)
        kind = part.get_content_type()
        if kind == "text/html":
            html_parts.append(content)
        elif kind == "text/plain":
            plain.append(content)
    text = "\n".join(part for part in plain if part.strip())
    stub = sum(character.isalnum() for character in text) < 40 and bool(
        re.search(r"view this|in your browser|in html", text, re.I)
    )
    if html_parts and (not text.strip() or stub):
        converted = []
        for part in html_parts:
            visible, hidden_open = html_to_text(part)
            converted.append(visible)
            unclosed = unclosed or hidden_open
        text = "\n".join(converted)
    return text, attachments, unclosed


def _limit(text: str) -> tuple[str, bool]:
    if len(text) <= MAX_BODY:
        return text, False
    return text[:MAX_BODY], True


def load_eml(path: Path, source: str) -> Request:
    message = email.message_from_bytes(path.read_bytes(), policy=email.policy.default)
    sender_name, sender_email = _address(str(message.get("from", "")))
    reply_name, reply_email = _address(str(message.get("reply-to", "")))
    raw, attachments, unclosed = _bodies(message)
    raw, truncated = _limit(raw)
    own = []
    for header in ("to", "cc", "delivered-to"):
        for value in message.get_all(header, []):
            own.extend(_ADDRESS.findall(str(value)))
    return Request(
        id=path.stem,
        source=source,
        sender_name=sender_name,
        sender_email=sender_email,
        reply_name=reply_name,
        reply_email=reply_email,
        subject=str(message.get("subject", "") or ""),
        body_text=customer_text(raw, own),
        attachments=attachments,
        truncated=truncated,
        force_human=unclosed,
    )


def _from_mapping(data: dict, source: str, fallback_id: str) -> Request:
    raw = data.get("body_text") or ""
    unclosed = False
    if not str(raw).strip() and data.get("body_html"):
        raw, unclosed = html_to_text(data.get("body_html") or "")
    raw, truncated = _limit(str(raw))
    attachments = [str(name) for name in data.get("attachments") or [] if str(name).strip()]
    return Request(
        id=str(data.get("id") or fallback_id),
        source=source,
        sender_name=" ".join(str(data.get("from_name") or "").split()),
        sender_email=str(data.get("from_email") or "").strip().casefold(),
        reply_name=" ".join(str(data.get("reply_to_name") or "").split()),
        reply_email=str(data.get("reply_to_email") or "").strip().casefold(),
        subject=str(data.get("subject") or ""),
        body_text=customer_text(raw),
        supplied_phone=str(data.get("phone") or ""),
        supplied_company=str(data.get("company") or ""),
        attachments=attachments,
        truncated=truncated,
        force_human=unclosed,
    )


def load_json(path: Path, source: str) -> list[Request]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return [Request(id=path.stem, source=source, parse_error="invalid_json")]
    rows = data if isinstance(data, list) else [data]
    loaded = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            loaded.append(Request(id=f"{path.stem}-{index}", source=source, parse_error="invalid_json"))
            continue
        loaded.append(_from_mapping(row, source, path.stem if len(rows) == 1 else f"{path.stem}-{index}"))
    return loaded


def load_csv(path: Path, source: str) -> list[Request]:
    loaded = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for index, row in enumerate(csv.DictReader(handle)):
            message = row.get("message") or ""
            attachment = (row.get("attachment") or "").strip()
            loaded.append(
                Request(
                    id=(row.get("id") or f"{path.stem}-{index}").strip(),
                    source=source,
                    sender_name=" ".join((row.get("full_name") or "").split()),
                    sender_email=(row.get("email") or "").strip().casefold(),
                    subject="",
                    body_text=customer_text(message),
                    preferred_date=(row.get("preferred_date") or "").strip(),
                    supplied_phone=(row.get("phone") or "").strip(),
                    supplied_company=(row.get("company") or "").strip(),
                    attachments=[attachment] if attachment else [],
                )
            )
    return loaded


def load_inbox(inbox: Path) -> list[Request]:
    root = Path(inbox).resolve()
    requests: list[Request] = []
    paths = sorted(path for path in root.rglob("*") if path.is_file() and not path.is_symlink())
    for path in paths:
        if not path.resolve().is_relative_to(root):
            continue
        source = str(path.relative_to(root))
        suffix = path.suffix.casefold()
        if suffix == ".eml":
            requests.append(load_eml(path, source))
        elif suffix == ".json":
            requests.extend(load_json(path, source))
        elif suffix == ".csv":
            requests.extend(load_csv(path, source))
    return requests
