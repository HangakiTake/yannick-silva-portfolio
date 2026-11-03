"""Review log a person can open. The message body is not a column."""

import csv
import os
from pathlib import Path

from openpyxl import Workbook

COLUMNS = (
    "request_id",
    "source",
    "sender",
    "subject",
    "request_type",
    "urgency",
    "customer_name",
    "company",
    "contact_email",
    "contact_phone",
    "key_dates",
    "amounts",
    "summary",
    "missing_info",
    "confidence",
    "needs_human",
    "flags",
    "draft_path",
    "disposition",
    "attachments",
    "schema_valid",
)


def excel_safe(value) -> str:
    if isinstance(value, list):
        value = "; ".join(str(part) for part in value)
    if isinstance(value, bool):
        value = "yes" if value else "no"
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text


def redact_row(row: dict) -> dict:
    cleaned = dict(row)
    secrets = [
        row.get("customer_name") or "",
        row.get("contact_email") or "",
        row.get("contact_phone") or "",
        row.get("sender") or "",
    ]
    if cleaned.get("customer_name"):
        cleaned["customer_name"] = "[redacted-name]"
    if cleaned.get("contact_email"):
        cleaned["contact_email"] = "[redacted-email]"
    if cleaned.get("sender"):
        cleaned["sender"] = "[redacted-email]"
    if cleaned.get("contact_phone"):
        cleaned["contact_phone"] = "[redacted-phone]"

    def hide(value: str) -> str:
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[redacted]")
        return value

    for key in ("summary", "subject", "company"):
        if isinstance(cleaned.get(key), str):
            cleaned[key] = hide(cleaned[key])
    if isinstance(cleaned.get("missing_info"), list):
        cleaned["missing_info"] = [hide(str(item)) for item in cleaned["missing_info"]]
    return cleaned


def _replace(temporary: Path, final: Path) -> None:
    os.replace(temporary, final)


def write_logs(out: Path, rows: list[dict]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "review_log.csv"
    csv_tmp = out / "review_log.csv.tmp"
    with csv_tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: excel_safe(row.get(column, "")) for column in COLUMNS})
    _replace(csv_tmp, csv_path)
    book = Workbook()
    sheet = book.active
    sheet.title = "Review"
    sheet.append(list(COLUMNS))
    for row in rows:
        sheet.append([excel_safe(row.get(column, "")) for column in COLUMNS])
    xlsx_tmp = out / "review_log.xlsx.tmp"
    book.save(xlsx_tmp)
    _replace(xlsx_tmp, out / "review_log.xlsx")
