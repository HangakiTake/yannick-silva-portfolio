"""Run the inbox once. A second run reuses the same drafts and does not call the model again."""

import fcntl
import hashlib
import json
import logging
import os
import re
from pathlib import Path

from triage.draft import build_draft
from triage.extract import refresh_copy, safety_flags
from triage.factcheck import draft_violations
from triage.intake import load_inbox
from triage.llm import build_llm, complete_valid, render_prompt
from triage.policy import load_policy
from triage.reviewlog import redact_row, write_logs
from triage.schema import LOW_CONFIDENCE, Extraction
from triage.textutil import find_amounts, find_dates, phone_grounded

logger = logging.getLogger("triage")
STATE_VERSION = 1


def _safe_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", value)[:80]
    return cleaned or "request"


def _policy_fingerprint(policy) -> str:
    blob = json.dumps(policy.raw, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _digest(request, redact: bool, policy) -> str:
    payload = json.dumps(
        {
            "version": STATE_VERSION,
            "redact": redact,
            "policy": _policy_fingerprint(policy),
            "id": request.id,
            "subject": request.subject,
            "body": request.body_text,
            "from": request.sender_email,
            "from_name": request.sender_name,
            "reply": request.reply_email,
            "reply_name": request.reply_name,
            "phone": request.supplied_phone,
            "company": request.supplied_company,
            "preferred": request.preferred_date,
            "attachments": request.attachments,
            "truncated": request.truncated,
            "parse_error": request.parse_error,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _ground(extraction: Extraction, request) -> tuple[dict, bool]:
    data = extraction.model_dump()
    folded = request.search_text.casefold()
    dropped = False
    if data["customer_name"]:
        wanted = re.sub(r"\s+", " ", data["customer_name"]).strip()
        pattern = re.escape(wanted).replace("\\ ", r"\s+")
        if not re.search(pattern, request.search_text, flags=re.I):
            data["customer_name"] = ""
            dropped = True
    if data["company"] and data["company"].casefold() not in folded:
        data["company"] = ""
        dropped = True
    if data["contact_email"] and data["contact_email"].casefold() not in folded:
        data["contact_email"] = ""
        dropped = True
    if data["contact_phone"] and not phone_grounded(data["contact_phone"], request.search_text):
        data["contact_phone"] = ""
        dropped = True
    found = find_dates("\n".join((request.body_text, request.subject, request.preferred_date)))
    by_iso = {}
    for hit in found:
        by_iso.setdefault(hit["iso"], hit["phrase"])
    kept_dates, kept_phrases = [], []
    for iso in data["key_dates"]:
        if iso in by_iso:
            kept_dates.append(iso)
            kept_phrases.append(by_iso[iso])
        else:
            dropped = True
    data["key_dates"] = kept_dates
    data["date_phrases"] = kept_phrases
    allowed_amounts = set(find_amounts(f"{request.subject}\n{request.body_text}"))
    if "spam" in data["flags"]:
        allowed_amounts = set()
    kept_amounts = []
    for amount in data["amounts"]:
        if amount in allowed_amounts:
            kept_amounts.append(amount)
        else:
            dropped = True
    data["amounts"] = kept_amounts
    if any(hit["ambiguous"] for hit in found) and "ambiguous_date" not in data["flags"]:
        data["flags"].append("ambiguous_date")
    if dropped:
        data["confidence"] = min(data["confidence"], 0.5)
    return data, dropped


def _overlay(data: dict, request) -> dict:
    flags = set(data["flags"])
    flags |= safety_flags(f"{request.subject}\n{request.body_text}")
    if request.truncated:
        flags.add("truncated")
    if "legal" in flags or "angry" in flags:
        data["request_type"] = "complaint"
    elif "payment_dispute" in flags and data["request_type"] != "complaint":
        data["request_type"] = "billing"
    if "spam" in flags or "empty" in flags:
        data["request_type"] = "other"
        data["amounts"] = []
        data["confidence"] = min(float(data["confidence"]), 0.22 if "spam" in flags else 0.10)
    if request.parse_error:
        flags.add("empty")
        data["request_type"] = "other"
    if float(data["confidence"]) < LOW_CONFIDENCE:
        flags.add("low_confidence")
    data["flags"] = sorted(flags)
    return data


def _needs_human(data: dict, dropped: bool) -> bool:
    if data["request_type"] in {"complaint", "other"}:
        return True
    if data["urgency"] == "high":
        return True
    if dropped:
        return True
    force = {
        "legal", "payment_dispute", "angry", "spam", "empty", "low_confidence",
        "ambiguous_date", "truncated", "schema_invalid",
    }
    return bool(set(data["flags"]) & force)


def _blank_row(request) -> dict:
    return {
        "request_id": request.id,
        "source": request.source,
        "sender": request.sender_email,
        "subject": request.subject,
        "request_type": "other",
        "urgency": "normal",
        "customer_name": "",
        "company": "",
        "contact_email": "",
        "contact_phone": "",
        "key_dates": [],
        "date_phrases": [],
        "amounts": [],
        "summary": "The message could not be read automatically.\nA person needs to open it.\nNo fields were kept.",
        "missing_info": ["a readable message"],
        "confidence": 0.0,
        "needs_human": True,
        "flags": ["low_confidence", "schema_invalid"],
        "disposition": "draft",
        "schema_valid": False,
        "attachments": list(request.attachments),
    }


def _row_from_data(request, data: dict, dropped: bool, schema_valid: bool) -> dict:
    return {
        "request_id": request.id,
        "source": request.source,
        "sender": request.sender_email,
        "subject": request.subject,
        "request_type": data["request_type"],
        "urgency": data["urgency"],
        "customer_name": data["customer_name"],
        "company": data["company"],
        "contact_email": data["contact_email"],
        "contact_phone": data["contact_phone"],
        "key_dates": list(data["key_dates"]),
        "date_phrases": list(data["date_phrases"]),
        "amounts": list(data["amounts"]),
        "summary": data["summary"],
        "missing_info": list(data["missing_info"]),
        "confidence": float(data["confidence"]),
        "needs_human": _needs_human(data, dropped),
        "flags": list(data["flags"]),
        "disposition": "draft",
        "schema_valid": schema_valid,
        "attachments": list(request.attachments),
    }


def _write_draft(out: Path, request, row: dict, policy) -> None:
    drafts = out / "drafts"
    drafts.mkdir(parents=True, exist_ok=True)
    path = drafts / f"{_safe_id(request.id)}.json"
    subject = " ".join(request.subject.split()) or "your request"
    body = build_draft(request, row, policy)
    problems = draft_violations(body, request.search_text, policy, row["request_type"])
    if problems:
        row["needs_human"] = True
        body = "Hello,"
        body += (
            f"\n\nThank you for writing to {policy.business_name}.\n"
            "We could not tell what you need from this message.\n\n"
            + "\n".join(policy.allowed_commitments)
            + "\n\n"
            + "\n".join(policy.signature_lines)
        )
        logger.info("draft fact check failed id=%s count=%s", request.id, len(problems))
    payload = {
        "disposition": "draft",
        "sent": False,
        "to": request.sender_email,
        "subject": f"Re: {subject}",
        "body": body,
    }
    _atomic_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    row["draft_path"] = str(path)


def process_one(request, policy, llm, out: Path) -> dict:
    if getattr(llm, "policy", None) is None:
        llm.policy = policy
    extraction = complete_valid(llm, render_prompt(request))
    if extraction is None:
        row = _blank_row(request)
    else:
        data, dropped = _ground(extraction, request)
        data = _overlay(data, request)
        data = refresh_copy(data, request, policy)
        row = _row_from_data(request, data, dropped, True)
    if request.force_human:
        row["needs_human"] = True
    _write_draft(Path(out), request, row, policy)
    logger.info(
        "processed id=%s type=%s needs_human=%s",
        row["request_id"],
        row["request_type"],
        row["needs_human"],
    )
    return row


def _atomic_text(path: Path, text: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def _load_state(path: Path) -> dict:
    if not path.is_file():
        return {"version": STATE_VERSION, "items": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"version": STATE_VERSION, "items": {}}
    if data.get("version") != STATE_VERSION:
        return {"version": STATE_VERSION, "items": {}}
    data.setdefault("items", {})
    return data


def run_inbox(inbox: Path, out: Path, policy_path: Path, *, redact: bool = False, llm=None) -> list[dict]:
    policy = load_policy(policy_path)
    if llm is None:
        llm = build_llm()
    llm.policy = policy
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    lock_path = out / ".lock"
    with lock_path.open("a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            return _run_locked(Path(inbox), out, policy, llm, redact)
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _remember(request, out: Path, policy, llm, redact: bool, state: dict) -> dict:
    digest = _digest(request, redact, policy)
    cached = state["items"].get(request.id)
    draft_path = out / "drafts" / f"{_safe_id(request.id)}.json"
    if cached and cached.get("digest") == digest and draft_path.is_file():
        return cached["row"]
    row = process_one(request, policy, llm, out)
    stored = redact_row(row) if redact else row
    state["items"][request.id] = {"digest": digest, "row": stored}
    return stored


def _flush(out: Path, state: dict) -> None:
    rows = sorted((item["row"] for item in state["items"].values()), key=lambda row: row["request_id"])
    _atomic_text(out / "state.json", json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    write_logs(out, rows)


def record_one(request, out: Path, policy_path: Path, *, redact: bool = False, llm=None) -> dict:
    """One webhook request. A repeat of the same message does not add a row or call the model again."""
    policy = load_policy(policy_path)
    if llm is None:
        llm = build_llm()
    llm.policy = policy
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    with (out / ".lock").open("a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            state = _load_state(out / "state.json")
            row = _remember(request, out, policy, llm, redact, state)
            _flush(out, state)
            return row
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _run_locked(inbox: Path, out: Path, policy, llm, redact: bool) -> list[dict]:
    state = _load_state(out / "state.json")
    rows = []
    seen = set()
    for request in load_inbox(inbox):
        rows.append(_remember(request, out, policy, llm, redact, state))
        seen.add(request.id)
    for key, item in list(state["items"].items()):
        if item["row"].get("source") == "webhook":
            continue
        if key not in seen:
            del state["items"][key]
    rows.sort(key=lambda row: row["request_id"])
    _flush(out, state)
    return rows
