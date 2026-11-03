"""SQLite ledger and the mock CRM, task list, calendar and outbox."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def _sid(prefix: str, material: str) -> str:
    return prefix + hashlib.sha256(material.encode()).hexdigest()[:16]


def _row(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def _open_approvals(path: Path, mode: str) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        setup = sqlite3.connect(path)
        setup.executescript(_APPROVALS)
        setup.commit()
        setup.close()
    if mode == "ro":
        conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(path)
        conn.executescript(_APPROVALS)
        conn.commit()
    conn.row_factory = sqlite3.Row
    return conn


_APPROVALS = """
CREATE TABLE IF NOT EXISTS approvals (
    draft_id TEXT PRIMARY KEY,
    by_name TEXT NOT NULL,
    body_sha256 TEXT NOT NULL,
    approved_at TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path: Path | str, *, approvals_mode: str = "rw"):
        if approvals_mode not in {"rw", "ro"}:
            raise ValueError("approvals_mode must be rw or ro")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.approvals_mode = approvals_mode
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self._init()
        self.approval_conn = _open_approvals(self.path.with_name("approvals.sqlite"), approvals_mode)

    def _init(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS ledger (
                key TEXT PRIMARY KEY,
                step TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                status TEXT NOT NULL,
                detail TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS accepted (
                email TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                site_address TEXT NOT NULL,
                monthly_kwh TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS crm (
                email TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                site_address TEXT NOT NULL,
                monthly_kwh TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                missing TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                slot TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS drafts (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                body TEXT NOT NULL,
                body_sha256 TEXT NOT NULL,
                status TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS outbox (
                id TEXT PRIMARY KEY,
                draft_id TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL,
                body TEXT NOT NULL,
                body_sha256 TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS exceptions (
                id TEXT PRIMARY KEY,
                step TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                owner TEXT NOT NULL,
                reason TEXT NOT NULL,
                UNIQUE(step, entity_id)
            );
            CREATE TABLE IF NOT EXISTS rejections (
                raw_email TEXT PRIMARY KEY,
                reason TEXT NOT NULL
            );
            """
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
        self.approval_conn.close()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def ledger_status(self, key: str) -> str | None:
        row = self.conn.execute("SELECT status FROM ledger WHERE key = ?", (key,)).fetchone()
        return None if row is None else row["status"]

    def mark_ledger(self, key: str, step: str, entity_id: str, status: str, detail: str) -> None:
        self.conn.execute(
            """
            INSERT INTO ledger (key, step, entity_id, status, detail, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                status = excluded.status,
                detail = excluded.detail,
                updated_at = excluded.updated_at
            """,
            (key, step, entity_id, status, detail, self._now()),
        )
        self.conn.commit()

    def _write_person(self, table: str, lead: dict, current: dict | None) -> bool:
        fields = ("name", "phone", "site_address", "monthly_kwh")
        if current and all(current[field] == lead[field] for field in fields):
            return False
        values = (lead["email"], lead["name"], lead["phone"], lead["site_address"], lead["monthly_kwh"])
        if table == "accepted":
            self.conn.execute(
                """
                INSERT INTO accepted (email, name, phone, site_address, monthly_kwh)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(email) DO UPDATE SET
                    name = excluded.name,
                    phone = excluded.phone,
                    site_address = excluded.site_address,
                    monthly_kwh = excluded.monthly_kwh
                """,
                values,
            )
        elif table == "crm":
            self.conn.execute(
                """
                INSERT INTO crm (email, name, phone, site_address, monthly_kwh)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(email) DO UPDATE SET
                    name = excluded.name,
                    phone = excluded.phone,
                    site_address = excluded.site_address,
                    monthly_kwh = excluded.monthly_kwh
                """,
                values,
            )
        else:
            raise ValueError(table)
        self.conn.commit()
        return True

    def upsert_accepted(self, lead: dict) -> bool:
        return self._write_person("accepted", lead, self.get_accepted(lead["email"]))

    def get_accepted(self, email: str) -> dict | None:
        return _row(self.conn.execute("SELECT * FROM accepted WHERE email = ?", (email,)).fetchone())

    def upsert_crm(self, lead: dict) -> bool:
        return self._write_person("crm", lead, self.get_crm(lead["email"]))

    def get_crm(self, email: str) -> dict | None:
        return _row(self.conn.execute("SELECT * FROM crm WHERE email = ?", (email,)).fetchone())

    def list_crm(self) -> list[dict]:
        return [_row(row) for row in self.conn.execute("SELECT * FROM crm ORDER BY email")]

    def get_task(self, email: str) -> dict | None:
        return _row(self.conn.execute("SELECT * FROM tasks WHERE email = ?", (email,)).fetchone())

    def upsert_task(self, email: str, missing: list[str]) -> bool:
        payload = json.dumps(missing, separators=(",", ":"))
        existing = self.get_task(email)
        if existing and existing["missing"] == payload:
            return False
        task_id = existing["id"] if existing else _sid("tsk_", email)
        self.conn.execute(
            """
            INSERT INTO tasks (id, email, missing) VALUES (?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET missing = excluded.missing
            """,
            (task_id, email, payload),
        )
        self.conn.commit()
        return True

    def delete_task(self, email: str) -> bool:
        if self.get_task(email) is None:
            return False
        self.conn.execute("DELETE FROM tasks WHERE email = ?", (email,))
        self.conn.commit()
        return True

    def list_tasks(self) -> list[dict]:
        return [_row(row) for row in self.conn.execute("SELECT * FROM tasks ORDER BY email")]

    def used_slots(self) -> set[str]:
        return {row["slot"] for row in self.conn.execute("SELECT slot FROM events")}

    def get_event(self, email: str) -> dict | None:
        return _row(self.conn.execute("SELECT * FROM events WHERE email = ?", (email,)).fetchone())

    def insert_event(self, email: str, slot: str) -> tuple[dict, bool]:
        existing = self.get_event(email)
        if existing:
            return existing, False
        self.conn.execute(
            "INSERT INTO events (id, email, slot) VALUES (?, ?, ?)",
            (_sid("evt_", email), email, slot),
        )
        self.conn.commit()
        return self.get_event(email), True

    def list_events(self) -> list[dict]:
        return [_row(row) for row in self.conn.execute("SELECT * FROM events ORDER BY slot")]

    def get_draft(self, draft_id: str) -> dict | None:
        return _row(self.conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone())

    def get_draft_by_email(self, email: str) -> dict | None:
        return _row(self.conn.execute("SELECT * FROM drafts WHERE email = ?", (email,)).fetchone())

    def upsert_draft(self, email: str, body: str, body_sha256: str) -> bool:
        existing = self.get_draft_by_email(email)
        if existing and existing["body"] == body:
            return False
        if existing and existing["status"] == "sent":
            return False
        draft_id = existing["id"] if existing else _sid("dft_", email)
        self.conn.execute(
            """
            INSERT INTO drafts (id, email, body, body_sha256, status)
            VALUES (?, ?, ?, ?, 'queued')
            ON CONFLICT(email) DO UPDATE SET
                body = excluded.body,
                body_sha256 = excluded.body_sha256,
                status = 'queued'
            """,
            (draft_id, email, body, body_sha256),
        )
        self.conn.commit()
        return True

    def mark_draft_sent(self, draft_id: str) -> None:
        self.conn.execute("UPDATE drafts SET status = 'sent' WHERE id = ?", (draft_id,))
        self.conn.commit()

    def list_drafts(self) -> list[dict]:
        return [_row(row) for row in self.conn.execute("SELECT * FROM drafts ORDER BY email")]

    def save_approval(self, draft_id: str, by_name: str, body_sha256: str) -> dict:
        if self.approvals_mode != "rw":
            raise PermissionError("a workflow run cannot grant approvals")
        name = str(by_name).strip()
        if not name:
            raise ValueError("approver name required")
        self.approval_conn.execute(
            """
            INSERT INTO approvals (draft_id, by_name, body_sha256, approved_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(draft_id) DO UPDATE SET
                by_name = excluded.by_name,
                body_sha256 = excluded.body_sha256,
                approved_at = excluded.approved_at
            """,
            (draft_id, name, body_sha256, self._now()),
        )
        self.approval_conn.commit()
        return self.get_approval(draft_id)

    def get_approval(self, draft_id: str) -> dict | None:
        return _row(
            self.approval_conn.execute(
                "SELECT * FROM approvals WHERE draft_id = ?", (draft_id,)
            ).fetchone()
        )

    def list_approvals(self) -> list[dict]:
        rows = self.approval_conn.execute("SELECT * FROM approvals ORDER BY draft_id")
        return [row for row in (_row(item) for item in rows) if row is not None]

    def reject(self, raw_email: str, reason: str) -> bool:
        existing = self.conn.execute(
            "SELECT 1 FROM rejections WHERE raw_email = ?", (raw_email,)
        ).fetchone()
        if existing:
            return False
        self.conn.execute(
            "INSERT INTO rejections (raw_email, reason) VALUES (?, ?)",
            (raw_email, reason),
        )
        self.conn.commit()
        return True

    def get_rejection(self, raw_email: str) -> dict | None:
        return _row(
            self.conn.execute(
                "SELECT * FROM rejections WHERE raw_email = ?", (raw_email,)
            ).fetchone()
        )

    def list_rejections(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM rejections ORDER BY raw_email")
        return [row for row in (_row(item) for item in rows) if row is not None]

    def get_outbox(self, outbox_id: str) -> dict | None:
        return _row(self.conn.execute("SELECT * FROM outbox WHERE id = ?", (outbox_id,)).fetchone())

    def get_outbox_by_draft(self, draft_id: str) -> dict | None:
        return _row(
            self.conn.execute("SELECT * FROM outbox WHERE draft_id = ?", (draft_id,)).fetchone()
        )

    def insert_outbox(self, draft: dict) -> dict:
        outbox_id = _sid("msg_", draft["id"])
        self.conn.execute(
            """
            INSERT INTO outbox (id, draft_id, email, body, body_sha256)
            VALUES (?, ?, ?, ?, ?)
            """,
            (outbox_id, draft["id"], draft["email"], draft["body"], draft["body_sha256"]),
        )
        self.conn.commit()
        return self.get_outbox(outbox_id)

    def list_outbox(self) -> list[dict]:
        return [_row(row) for row in self.conn.execute("SELECT * FROM outbox ORDER BY email")]

    def add_exception(self, step: str, entity_id: str, owner: str, reason: str) -> bool:
        existing = self.conn.execute(
            "SELECT id FROM exceptions WHERE step = ? AND entity_id = ?",
            (step, entity_id),
        ).fetchone()
        if existing:
            return False
        self.conn.execute(
            """
            INSERT INTO exceptions (id, step, entity_id, owner, reason)
            VALUES (?, ?, ?, ?, ?)
            """,
            (_sid("exc_", f"{step}|{entity_id}"), step, entity_id, owner, reason),
        )
        self.conn.commit()
        return True

    def delete_exception(self, step: str, entity_id: str) -> None:
        self.conn.execute(
            "DELETE FROM exceptions WHERE step = ? AND entity_id = ?",
            (step, entity_id),
        )
        self.conn.commit()

    def list_exceptions(self) -> list[dict]:
        return [_row(row) for row in self.conn.execute("SELECT * FROM exceptions ORDER BY entity_id")]
