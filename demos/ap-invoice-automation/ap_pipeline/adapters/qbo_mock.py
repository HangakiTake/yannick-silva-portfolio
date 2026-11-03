"""In-memory QuickBooks client used by tests and the offline demo."""

from __future__ import annotations

import hashlib
import re

from ap_pipeline.models import Bill, BillDraft
from ap_pipeline.textnorm import vendor_key

_BILL_ID = re.compile(r"mock-bill-(\d+)$")


class MockQBOClient:
    """Stores bills in this process. `load_ledger` rebuilds them from the state file."""

    name = "mock"
    live_tested = False

    def __init__(self) -> None:
        self.bills: list[Bill] = []
        self.creates = 0
        self._next = 1

    def load_ledger(self, bills: list[Bill]) -> None:
        """Add ledger bills that this process does not already have.

        A restarted process starts empty and picks up the state file. A process
        whose state file was lost keeps bills already sitting in this client, so
        a replay is still blocked as a duplicate.
        """
        known = {bill.id for bill in self.bills}
        for bill in bills:
            if bill.id in known:
                continue
            self.bills.append(
                Bill(
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
                    attachment_bytes=bill.attachment_bytes,
                )
            )
            known.add(bill.id)
        highest = 0
        for bill in self.bills:
            match = _BILL_ID.fullmatch(bill.id)
            if match:
                highest = max(highest, int(match.group(1)))
        self._next = max(self._next, highest + 1)

    def find_bills(self, vendor_name: str | None = None) -> list[Bill]:
        if vendor_name is None:
            return list(self.bills)
        wanted = vendor_key(vendor_name)
        return [bill for bill in self.bills if vendor_key(bill.vendor_name) == wanted]

    def create_bill(self, draft: BillDraft) -> Bill:
        bill = Bill(
            id=f"mock-bill-{self._next:04d}",
            vendor_name=draft.vendor_name,
            vendor_id=draft.vendor_id,
            invoice_number=draft.invoice_number,
            txn_date=draft.txn_date,
            total=draft.total,
            po_number=draft.po_number,
            memo=draft.memo,
            currency=draft.currency,
        )
        self._next += 1
        self.creates += 1
        self.bills.append(bill)
        return bill

    def attach_pdf(self, bill_id: str, filename: str, content: bytes) -> str:
        bill = self._require(bill_id)
        digest = hashlib.sha256(content).hexdigest()
        attachment_id = f"mock-att-{bill_id.removeprefix('mock-bill-')}"
        bill.attachment_id = attachment_id
        bill.attachment_filename = filename
        bill.attachment_sha256 = digest
        bill.attachment_bytes = content
        return attachment_id

    def _require(self, bill_id: str) -> Bill:
        for bill in self.bills:
            if bill.id == bill_id:
                return bill
        raise KeyError(f"Unknown mock bill {bill_id}")
