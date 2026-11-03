"""Microsoft Graph mail adapter.

UNTESTED: this has not been run against a Microsoft 365 tenant. Endpoint
construction is unit-tested with a fake session. Application permissions
(Mail.ReadWrite) and an admin-consented app registration are required.
Delegated interactive sign-in is not implemented.
"""

from __future__ import annotations

import base64
from urllib.parse import quote

from ap_pipeline.adapters.mail_local import FAILED_FOLDER, PROCESSED_FOLDER
from ap_pipeline.dates import parse_received_at
from ap_pipeline.errors import CredentialsNotConfigured, PipelineError
from ap_pipeline.models import Attachment, EmailMessage

LIVE_API_TESTED = False
UNTESTED_NOTICE = (
    "UNTESTED: Microsoft Graph has not been called with real tenant credentials. "
    "Endpoint construction is unit-tested with a fake session only."
)
GRAPH_ROOT = "https://graph.microsoft.com/v1.0"


class GraphMailSource:
    name = "graph"
    live_tested = LIVE_API_TESTED

    def __init__(
        self,
        *,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        mailbox: str,
        session=None,
    ) -> None:
        missing = [
            name
            for name, value in {
                "GRAPH_TENANT_ID": tenant_id,
                "GRAPH_CLIENT_ID": client_id,
                "GRAPH_CLIENT_SECRET": client_secret,
                "GRAPH_MAILBOX": mailbox,
            }.items()
            if not value
        ]
        if missing:
            raise CredentialsNotConfigured(
                "Microsoft Graph adapter is missing " + ", ".join(missing) + ". " + UNTESTED_NOTICE
            )
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.mailbox = mailbox
        self._session = session if session is not None else _default_session()
        self._access_token: str | None = None
        self._folder_ids: dict[str, str] = {}

    def list_messages(self) -> list[EmailMessage]:
        rows = self._paged(
            self._user("mailFolders/inbox/messages"),
            params={
                "$filter": "hasAttachments eq true",
                "$select": "id,subject,from,receivedDateTime,bodyPreview",
                "$top": "50",
            },
        )
        payload = {"value": rows}
        messages: list[EmailMessage] = []
        for row in payload.get("value", []):
            attachments = self._pdf_attachments(row["id"])
            sender = ((row.get("from") or {}).get("emailAddress") or {})
            messages.append(
                EmailMessage(
                    id=row["id"],
                    from_name=sender.get("name", ""),
                    from_email=sender.get("address", ""),
                    subject=row.get("subject", ""),
                    received_at=parse_received_at(row["receivedDateTime"]),
                    body=row.get("bodyPreview", ""),
                    attachments=tuple(attachments),
                )
            )
        return messages

    def move(self, message_id: str, destination: str) -> None:
        folder_name = PROCESSED_FOLDER if destination == "processed" else FAILED_FOLDER
        if destination not in {"processed", "failed"}:
            raise ValueError(f"Unknown mail destination {destination}")
        folder_id = self._ensure_folder(folder_name)
        self._post(self._message(message_id, "move"), {"destinationId": folder_id})

    def deliver_reply(self, message: EmailMessage, subject: str, body: str, *, dry_run: bool) -> str:
        # Graph reply keeps the thread subject. The template subject is repeated
        # in the body so the vendor still sees it. dry_run creates a draft and
        # does not call the send endpoint.
        action = "createReply" if dry_run else "reply"
        comment = f"Subject: {subject}\n\n{body}"
        self._post(self._message(message.id, action), {"comment": comment})
        return action

    def _pdf_attachments(self, message_id: str) -> list[Attachment]:
        payload = self._get(self._message(message_id, "attachments"))
        found: list[Attachment] = []
        for row in payload.get("value", []):
            name = row.get("name", "invoice.pdf")
            content_type = row.get("contentType", "")
            if not (name.lower().endswith(".pdf") or content_type == "application/pdf"):
                continue
            encoded = row.get("contentBytes")
            if not encoded and row.get("id"):
                detail = self._get(self._message(message_id, f"attachments/{quote(str(row['id']), safe='')}"))
                encoded = detail.get("contentBytes")
            if not encoded:
                continue
            found.append(
                Attachment(
                    filename=name,
                    content=base64.b64decode(encoded),
                    content_type=content_type or "application/pdf",
                )
            )
        return found

    def _ensure_folder(self, display_name: str) -> str:
        cached = self._folder_ids.get(display_name)
        if cached:
            return cached
        escaped = display_name.replace("'", "''")
        listed = self._get(
            self._user("mailFolders"),
            params={"$filter": f"displayName eq '{escaped}'"},
        )
        values = listed.get("value", [])
        if values:
            folder_id = values[0]["id"]
        else:
            created = self._post(self._user("mailFolders"), {"displayName": display_name})
            folder_id = created["id"]
        self._folder_ids[display_name] = folder_id
        return folder_id

    def _user(self, suffix: str) -> str:
        return f"/users/{quote(self.mailbox, safe='')}/{suffix}"

    def _message(self, message_id: str, suffix: str) -> str:
        return self._user(f"messages/{quote(message_id, safe='')}/{suffix}")

    def _paged(self, path: str, params: dict | None = None) -> list:
        rows: list = []
        url = GRAPH_ROOT + path
        query = params
        for _ in range(10):
            response = self._session.request(
                "GET",
                url,
                params=query,
                headers=self._headers(),
                timeout=60,
            )
            payload = self._json(response, "Graph GET")
            rows.extend(payload.get("value", []))
            url = payload.get("@odata.nextLink")
            query = None
            if not url:
                break
        return rows

    def _get(self, path: str, params: dict | None = None) -> dict:
        response = self._session.request(
            "GET",
            GRAPH_ROOT + path,
            params=params,
            headers=self._headers(),
            timeout=60,
        )
        return self._json(response, "Graph GET")

    def _post(self, path: str, payload: dict) -> dict:
        response = self._session.request(
            "POST",
            GRAPH_ROOT + path,
            json=payload,
            headers=self._headers(),
            timeout=60,
        )
        if response.status_code == 202:
            return {}
        return self._json(response, "Graph POST")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token()}", "Accept": "application/json"}

    def _token(self) -> str:
        if self._access_token:
            return self._access_token
        url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        response = self._session.request(
            "POST",
            url,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "https://graph.microsoft.com/.default",
                "grant_type": "client_credentials",
            },
            timeout=60,
        )
        payload = self._json(response, "Graph token")
        token = payload.get("access_token")
        if not token:
            raise PipelineError("Graph token response did not include access_token")
        self._access_token = token
        return token

    @staticmethod
    def _json(response, action: str) -> dict:
        if getattr(response, "status_code", 500) >= 400:
            raise PipelineError(f"{action} failed with HTTP {response.status_code}")
        if not getattr(response, "content", b""):
            return {}
        return response.json()


def _default_session():
    import requests

    return requests.Session()


def reply_action(dry_run: bool) -> str:
    """Which Graph action a reply uses. Exposed for the unit test."""
    return "createReply" if dry_run else "reply"
