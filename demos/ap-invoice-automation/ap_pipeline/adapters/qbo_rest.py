"""QuickBooks Online REST client.

UNTESTED: no sandbox company is configured, so these calls have never been
executed against Intuit. Payload builders are unit-tested with a fake HTTP
session. Do not treat a green test run as a live QuickBooks certification.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote, urlsplit

from ap_pipeline.errors import CredentialsNotConfigured, PipelineError, ProductionGuardError
from ap_pipeline.models import Bill, BillDraft
from ap_pipeline.money import money_to_json_number

LIVE_API_TESTED = False
UNTESTED_NOTICE = (
    "UNTESTED: QuickBooks Online REST has not been called against an Intuit sandbox. "
    "Request payloads are unit-tested with a fake HTTP session only."
)
TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
SANDBOX_BASE = "https://sandbox-quickbooks.api.intuit.com"
MINOR_VERSION = "75"
_QUERY_SAFE = re.compile(r"[A-Za-z0-9 .,&()/.+-]+$")


_SANDBOX_HOST = "sandbox-quickbooks.api.intuit.com"
_PRODUCTION_HOST = "quickbooks.api.intuit.com"


def assert_sandbox_or_explicit_production(base_url: str, *, allow_production: bool = False) -> str:
    """Allow the sandbox host, or production only when the caller opts in.

    Userinfo, a trailing dot, and an explicit port still count as production.
    Any other host is refused so a mistyped base URL cannot receive the token.
    """
    parsed = urlsplit(base_url.strip())
    if parsed.scheme not in {"https"} or not parsed.hostname:
        raise ProductionGuardError(f"QuickBooks base URL must be https with a host: {base_url}")
    if parsed.username or parsed.password:
        raise ProductionGuardError("Refusing a QuickBooks base URL that contains userinfo")
    host = parsed.hostname.rstrip(".").lower()
    if host == _SANDBOX_HOST and parsed.port in {None, 443}:
        return f"https://{_SANDBOX_HOST}"
    if host == _PRODUCTION_HOST and parsed.port in {None, 443}:
        if not allow_production:
            raise ProductionGuardError(
                "Refusing production QuickBooks host quickbooks.api.intuit.com. "
                "Use the sandbox host, or set QBO_ALLOW_PRODUCTION=yes if you intend to create real bills."
            )
        return f"https://{_PRODUCTION_HOST}"
    raise ProductionGuardError(
        f"Refusing QuickBooks base URL host {host!r}. "
        f"The only host this demo calls without QBO_ALLOW_PRODUCTION=yes is {_SANDBOX_HOST}."
    )


def build_bill_payload(draft: BillDraft, qbo_vendor_id: str) -> dict:
    detail: dict = {"AccountRef": {"value": draft.expense_account_id}}
    if draft.qbo_customer_id:
        detail["CustomerRef"] = {"value": draft.qbo_customer_id}
    return {
        "VendorRef": {"value": qbo_vendor_id, "name": draft.vendor_name},
        "TxnDate": draft.txn_date,
        "DocNumber": draft.invoice_number,
        "PrivateNote": draft.memo,
        "CurrencyRef": {"value": draft.currency},
        "Line": [
            {
                "DetailType": "AccountBasedExpenseLineDetail",
                "Amount": draft.total,
                "Description": draft.line_description,
                "AccountBasedExpenseLineDetail": detail,
            }
        ],
    }


def dumps_qbo(payload: dict) -> str:
    """JSON with Decimal amounts written as two-decimal numbers, not binary floats."""
    encoded = json.dumps(payload, default=_encode_decimal, separators=(",", ":"))
    return re.sub(r'"@@DEC:(-?\d+\.\d{2})@@"', r"\1", encoded)


def build_upload_parts(bill_id: str, filename: str, content: bytes) -> tuple[bytes, str]:
    filename = _attachment_filename(filename)
    boundary = "----ap-" + uuid.uuid4().hex
    while boundary.encode("ascii") in content:
        boundary = "----ap-" + uuid.uuid4().hex
    metadata = {
        "AttachableRef": [{"EntityRef": {"type": "Bill", "value": str(bill_id)}}],
        "FileName": filename,
        "ContentType": "application/pdf",
    }
    meta = json.dumps(metadata).encode("utf-8")
    chunks = [
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="file_metadata_0"; filename="attachment.json"\r\n',
        b"Content-Type: application/json; charset=UTF-8\r\n\r\n",
        meta,
        b"\r\n",
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="file_content_0"; filename="{filename}"\r\n'.encode(),
        b"Content-Type: application/pdf\r\n\r\n",
        content,
        b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ]
    body = b"".join(chunks)
    return body, f"multipart/form-data; boundary={boundary}"


def _encode_decimal(value: object) -> str:
    if isinstance(value, Decimal):
        return f"@@DEC:{money_to_json_number(value)}@@"
    raise TypeError(f"Cannot encode {type(value).__name__}")


def _attachment_filename(filename: str) -> str:
    base = Path(filename).name
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", base)
    if cleaned in {"", ".", ".."}:
        return "invoice.pdf"
    if not cleaned.lower().endswith(".pdf"):
        cleaned += ".pdf"
    return cleaned


def _query_literal(value: str) -> str:
    if not value or _QUERY_SAFE.fullmatch(value) is None:
        raise PipelineError(f"Refusing to put this value in a QuickBooks query: {value!r}")
    return value


class QboRestClient:
    """Live client. `LIVE_API_TESTED` stays false until a sandbox run exists."""

    name = "rest"
    live_tested = LIVE_API_TESTED

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        realm_id: str,
        expense_account_id: str,
        base_url: str = SANDBOX_BASE,
        session=None,
        token_cache: Path | None = None,
        allow_production: bool = False,
    ) -> None:
        missing = [
            name
            for name, value in {
                "QBO_CLIENT_ID": client_id,
                "QBO_CLIENT_SECRET": client_secret,
                "QBO_REFRESH_TOKEN": refresh_token,
                "QBO_REALM_ID": realm_id,
                "QBO_EXPENSE_ACCOUNT_ID": expense_account_id,
            }.items()
            if not value
        ]
        if missing:
            raise CredentialsNotConfigured(
                "QuickBooks REST adapter is missing " + ", ".join(missing) + ". " + UNTESTED_NOTICE
            )
        self.base_url = assert_sandbox_or_explicit_production(base_url, allow_production=allow_production)
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.realm_id = realm_id
        self.expense_account_id = expense_account_id
        self.token_cache = token_cache
        self._session = session if session is not None else _default_session()
        self._access_token: str | None = None
        self._token_deadline = 0.0
        if token_cache is not None and token_cache.is_file():
            cached = token_cache.read_text(encoding="utf-8").strip()
            if cached:
                self.refresh_token = cached

    def load_ledger(self, bills: list[Bill]) -> None:
        """The live company is the ledger. Local bills are not copied into QuickBooks."""
        del bills

    def find_bills(self, vendor_name: str | None = None) -> list[Bill]:
        since = (date.today() - timedelta(days=400)).isoformat()
        rows = self._query_bills(since)
        bills = [_bill_from_qbo(row) for row in rows]
        if vendor_name is None:
            return bills
        from ap_pipeline.textnorm import vendor_key

        wanted = vendor_key(vendor_name)
        return [bill for bill in bills if vendor_key(bill.vendor_name) == wanted]

    def create_bill(self, draft: BillDraft) -> Bill:
        vendor_id = self._vendor_id(draft.vendor_name)
        payload = build_bill_payload(draft, vendor_id)
        created = self._post_json(f"/v3/company/{self.realm_id}/bill", dumps_qbo(payload))
        bill = created.get("Bill", created)
        return Bill(
            id=str(bill["Id"]),
            vendor_name=draft.vendor_name,
            vendor_id=vendor_id,
            invoice_number=draft.invoice_number,
            txn_date=draft.txn_date,
            total=draft.total,
            po_number=draft.po_number,
            memo=draft.memo,
            currency=draft.currency,
        )

    def attach_pdf(self, bill_id: str, filename: str, content: bytes) -> str:
        body, content_type = build_upload_parts(bill_id, filename, content)
        url = f"{self.base_url}/v3/company/{self.realm_id}/upload?minorversion={MINOR_VERSION}"
        response = self._session.post(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {self._token()}",
                "Accept": "application/json",
                "Content-Type": content_type,
            },
            timeout=60,
        )
        if response.status_code >= 400:
            raise PipelineError(f"QuickBooks attachment upload failed with HTTP {response.status_code}")
        payload = response.json()
        attachable = payload.get("AttachableResponse", [{}])
        first = attachable[0] if attachable else {}
        ref = first.get("Attachable", first)
        if "Id" not in ref:
            raise PipelineError("QuickBooks attachment upload returned no Attachable Id")
        return str(ref["Id"])

    def _vendor_id(self, display_name: str) -> str:
        safe = _query_literal(display_name)
        query = f"select * from Vendor where DisplayName = '{safe}'"
        rows = self._query(query).get("QueryResponse", {}).get("Vendor", [])
        if isinstance(rows, dict):
            rows = [rows]
        if not rows:
            raise PipelineError(
                f"No QuickBooks vendor named {display_name!r}. Create the vendor in the sandbox "
                "with the same display name before running the live adapter."
            )
        return str(rows[0]["Id"])

    def _query_bills(self, since: str) -> list[dict]:
        collected: list[dict] = []
        start = 1
        while len(collected) < 1000:
            query = (
                "select * from Bill where TxnDate >= "
                f"'{since}' startposition {start} maxresults 200"
            )
            rows = self._query(query).get("QueryResponse", {}).get("Bill", [])
            if isinstance(rows, dict):
                rows = [rows]
            if not rows:
                break
            collected.extend(rows)
            if len(rows) < 200:
                break
            start += 200
        return collected

    def _query(self, statement: str) -> dict:
        url = (
            f"{self.base_url}/v3/company/{self.realm_id}/query"
            f"?query={quote(statement)}&minorversion={MINOR_VERSION}"
        )
        response = self._session.get(
            url,
            headers={"Authorization": f"Bearer {self._token()}", "Accept": "application/json"},
            timeout=60,
        )
        if response.status_code >= 400:
            raise PipelineError(f"QuickBooks query failed with HTTP {response.status_code}")
        return response.json()

    def _post_json(self, path: str, body: str) -> dict:
        url = f"{self.base_url}{path}?minorversion={MINOR_VERSION}"
        response = self._session.post(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {self._token()}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=60,
        )
        if response.status_code >= 400:
            raise PipelineError(f"QuickBooks create bill failed with HTTP {response.status_code}")
        return response.json()

    def _token(self) -> str:
        if self._access_token and time.monotonic() < self._token_deadline:
            return self._access_token
        self._access_token = None
        response = self._session.post(
            TOKEN_URL,
            data={"grant_type": "refresh_token", "refresh_token": self.refresh_token},
            auth=(self.client_id, self.client_secret),
            timeout=60,
        )
        if response.status_code != 200:
            raise PipelineError(f"QBO token refresh failed with HTTP {response.status_code}")
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise PipelineError("QBO token refresh returned no access_token")
        rotated = payload.get("refresh_token")
        if rotated and self.token_cache is not None:
            _write_secret(self.token_cache, rotated)
            self.refresh_token = rotated
        expires_in = int(payload.get("expires_in") or 3600)
        self._token_deadline = time.monotonic() + max(30, expires_in - 120)
        self._access_token = token
        return token


def _bill_from_qbo(row: dict) -> Bill:
    vendor_ref = row.get("VendorRef") or {}
    note = row.get("PrivateNote") or ""
    po_number = note.split(" ", 1)[0] if note.startswith("PO-") else ""
    total = Decimal(str(row.get("TotalAmt", "0"))).quantize(Decimal("0.01"))
    return Bill(
        id=str(row.get("Id", "")),
        vendor_name=str(vendor_ref.get("name", "")),
        vendor_id=str(vendor_ref.get("value", "")),
        invoice_number=str(row.get("DocNumber", "")),
        txn_date=str(row.get("TxnDate", "")),
        total=total,
        po_number=po_number,
        memo=note,
        currency=str((row.get("CurrencyRef") or {}).get("value", "CAD")),
    )


def _write_secret(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, value.encode("utf-8"))
    finally:
        os.close(fd)


def _default_session():
    import requests

    return requests.Session()
