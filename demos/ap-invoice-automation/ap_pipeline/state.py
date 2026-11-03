"""Atomic JSON state: one record per email, plus the bill ledger used for duplicates."""

from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path

from ap_pipeline.errors import PipelineError
from ap_pipeline.models import Bill


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock_file = self._acquire_lock(path)
        self.messages: dict[str, dict] = {}
        self.bills: list[Bill] = []
        if path.exists():
            self._load(json.loads(path.read_text(encoding="utf-8")))

    def close(self) -> None:
        lock = getattr(self, "_lock_file", None)
        self._lock_file = None
        if not lock:
            return
        fd, lock_path, owned = lock
        if owned:
            os.close(fd)
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:  # noqa: BLE001 — destructor must not raise
            return

    def get_message(self, message_id: str) -> dict | None:
        found = self.messages.get(message_id)
        return None if found is None else dict(found)

    def upsert_message(self, message_id: str, **fields: object) -> None:
        current = dict(self.messages.get(message_id, {}))
        current.update(fields)
        self.messages[message_id] = current
        self.save()

    def add_bill(self, bill: Bill) -> None:
        if any(existing.id == bill.id for existing in self.bills):
            return
        self.bills.append(_without_bytes(bill))
        self.save()

    def mark_attachment(self, bill_id: str, attachment_id: str, sha256: str, filename: str) -> None:
        for bill in self.bills:
            if bill.id == bill_id:
                bill.attachment_id = attachment_id
                bill.attachment_sha256 = sha256
                bill.attachment_filename = filename
                break
        message = self._message_for_bill(bill_id)
        if message is not None:
            message["attachment_id"] = attachment_id
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "messages": self.messages,
            "bills": [_bill_to_json(bill) for bill in self.bills],
        }
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(self.path)

    @staticmethod
    def _acquire_lock(path: Path) -> tuple[int, Path, bool] | None:
        """One process at a time. A second store in this process reuses the lock.

        A lock whose pid is no longer running is removed. A live other pid refuses
        the run so two overlapping processes cannot both create a bill.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = path.with_name(path.name + ".lock")
        for _ in range(2):
            try:
                fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
            except FileExistsError:
                holder = _lock_holder(lock_path)
                if holder == os.getpid():
                    return None
                if holder is not None and _pid_alive(holder):
                    raise PipelineError(
                        f"Another run is already using {path}. Refusing to start a second one."
                    )
                try:
                    lock_path.unlink()
                except FileNotFoundError:
                    pass
                continue
            os.write(fd, str(os.getpid()).encode("ascii"))
            return fd, lock_path, True
        raise PipelineError(f"Could not lock {path}")

    def _load(self, payload: dict) -> None:
        self.messages = dict(payload.get("messages", {}))
        self.bills = [_bill_from_json(row) for row in payload.get("bills", [])]

    def _message_for_bill(self, bill_id: str) -> dict | None:
        for message in self.messages.values():
            if message.get("bill_id") == bill_id:
                return message
        return None


def _lock_holder(lock_path: Path) -> int | None:
    try:
        return int(lock_path.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        return None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _without_bytes(bill: Bill) -> Bill:
    return Bill(
        id=bill.id,
        vendor_name=bill.vendor_name,
        vendor_id=bill.vendor_id,
        invoice_number=bill.invoice_number,
        txn_date=bill.txn_date,
        total=bill.total,
        po_number=bill.po_number,
        memo=bill.memo,
        currency=bill.currency,
        attachment_id=bill.attachment_id,
        attachment_filename=bill.attachment_filename,
        attachment_sha256=bill.attachment_sha256,
        attachment_bytes=None,
    )


def _bill_to_json(bill: Bill) -> dict:
    return {
        "id": bill.id,
        "vendor_name": bill.vendor_name,
        "vendor_id": bill.vendor_id,
        "invoice_number": bill.invoice_number,
        "txn_date": bill.txn_date,
        "total": format(bill.total, "f"),
        "po_number": bill.po_number,
        "memo": bill.memo,
        "currency": bill.currency,
        "attachment_id": bill.attachment_id,
        "attachment_filename": bill.attachment_filename,
        "attachment_sha256": bill.attachment_sha256,
    }


def _bill_from_json(row: dict) -> Bill:
    return Bill(
        id=row["id"],
        vendor_name=row["vendor_name"],
        vendor_id=row["vendor_id"],
        invoice_number=row["invoice_number"],
        txn_date=row["txn_date"],
        total=Decimal(row["total"]),
        po_number=row["po_number"],
        memo=row["memo"],
        currency=row.get("currency", "CAD"),
        attachment_id=row.get("attachment_id"),
        attachment_filename=row.get("attachment_filename"),
        attachment_sha256=row.get("attachment_sha256"),
    )
