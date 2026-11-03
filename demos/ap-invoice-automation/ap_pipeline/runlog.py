"""CSV and JSON run logs. One pair of files per run, plus the records on the summary."""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

from ap_pipeline.models import RunRecord, RunSummary


class RunLog:
    def __init__(self, directory: Path, *, now: datetime | None = None) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%S%fZ")
        self.json_path = directory / f"run-{stamp}.json"
        self.csv_path = directory / f"run-{stamp}.csv"
        self.records: list[RunRecord] = []

    def add(self, record: RunRecord) -> None:
        self.records.append(record)

    def write(self, summary: RunSummary) -> None:
        live = "not_used"
        if summary.extractor != "rules" or summary.qbo != "mock" or summary.mail != "local":
            live = "requested_untested"
        payload = {
            "extractor": summary.extractor,
            "qbo": summary.qbo,
            "mail": summary.mail,
            "bills_created": summary.bills_created,
            "live_apis": live,
            "records": [_record_dict(record) for record in summary.records],
        }
        self.json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        with self.csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "message_id",
                    "from_email",
                    "subject",
                    "decision",
                    "reasons",
                    "bill_id",
                    "vendor_name",
                    "invoice_number",
                    "total",
                    "prior_decision",
                ],
            )
            writer.writeheader()
            for record in summary.records:
                row = _record_dict(record)
                row["reasons"] = "|".join(record.reasons)
                writer.writerow(row)


def _record_dict(record: RunRecord) -> dict:
    return {
        "message_id": record.message_id,
        "from_email": record.from_email,
        "subject": record.subject,
        "decision": record.decision,
        "reasons": list(record.reasons),
        "bill_id": record.bill_id or "",
        "vendor_name": record.vendor_name or "",
        "invoice_number": record.invoice_number or "",
        "total": record.total or "",
        "prior_decision": record.prior_decision or "",
    }
