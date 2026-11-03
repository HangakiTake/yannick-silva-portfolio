"""One HTTP endpoint for Zapier or Power Automate. It saves a draft and does not send it."""

import hashlib
import hmac
import json
import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi import Request as HttpRequest
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from triage.intake import Request
from triage.pipeline import record_one
from triage.textutil import customer_text, html_to_text


class Incoming(BaseModel):
    sender: str = ""
    subject: str = ""
    body: str = ""
    body_html: str = ""
    attachments: list[str] = Field(default_factory=list)
    source_id: str = ""


logger = logging.getLogger("triage")
MAX_WEBHOOK_CHARS = 200_000


def create_app() -> FastAPI:
    app = FastAPI(title="Request triage drafts", version="1.0.0")

    @app.exception_handler(Exception)
    async def unhandled(_request, exc):
        if isinstance(exc, StarletteHTTPException):
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        if isinstance(exc, RequestValidationError):
            return JSONResponse(status_code=422, content={"detail": "invalid request"})
        logger.error("webhook failed: %s", type(exc).__name__)
        return JSONResponse(status_code=500, content={"detail": "request failed"})

    @app.get("/health")
    def health():
        mode = os.environ.get("TRIAGE_LLM_MODE", "mock").strip().casefold()
        return {"status": "ok", "mode": "live" if mode == "live" else "mock"}

    @app.post("/triage")
    def triage(payload: Incoming, http_request: HttpRequest):
        token = os.environ.get("TRIAGE_WEBHOOK_TOKEN", "")
        if not token:
            raise HTTPException(status_code=401, detail="TRIAGE_WEBHOOK_TOKEN is not set")
        expected = f"Bearer {token}"
        received = http_request.headers.get("authorization", "")
        if len(received) != len(expected) or not hmac.compare_digest(received, expected):
            raise HTTPException(status_code=401, detail="unauthorized")
        if len(payload.body) > MAX_WEBHOOK_CHARS or len(payload.body_html) > MAX_WEBHOOK_CHARS:
            raise HTTPException(status_code=413, detail="message too large")
        policy_path = os.environ.get("TRIAGE_POLICY", "")
        if not policy_path:
            raise HTTPException(status_code=500, detail="TRIAGE_POLICY is not set")
        out = Path(os.environ.get("TRIAGE_OUT", "out"))
        text = payload.body
        if not text.strip() and payload.body_html:
            text, unclosed = html_to_text(payload.body_html)
        else:
            unclosed = False
        sender_name, sender_email = _split_sender(payload.sender)
        identity = payload.source_id or hashlib.sha256(
            f"{payload.sender}\n{payload.subject}\n{text}".encode("utf-8")
        ).hexdigest()[:16]
        request = Request(
            id=identity,
            source="webhook",
            sender_name=sender_name,
            sender_email=sender_email,
            subject=payload.subject,
            body_text=customer_text(text),
            attachments=[name for name in payload.attachments if name.strip()],
            truncated=len(text) > 50_000,
            force_human=unclosed,
        )
        if request.truncated:
            request.body_text = request.body_text[:50_000]
        row = record_one(request, out, Path(policy_path))
        draft = json.loads(Path(row["draft_path"]).read_text(encoding="utf-8"))
        return {
            "request_id": row["request_id"],
            "request_type": row["request_type"],
            "needs_human": row["needs_human"],
            "confidence": row["confidence"],
            "flags": row["flags"],
            "disposition": "draft",
            "sent": False,
            "draft": draft,
        }

    return app


def _split_sender(value: str) -> tuple[str, str]:
    from email.utils import parseaddr

    name, address = parseaddr(value or "")
    return " ".join(name.split()), address.strip().casefold()
