"""Load the approved vendor list and the open-job list."""

from __future__ import annotations

import json
from pathlib import Path

from ap_pipeline.models import OpenJob, Vendor
from ap_pipeline.textnorm import po_key, vendor_key


def load_vendors(path: Path) -> list[Vendor]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    vendors: list[Vendor] = []
    for row in payload["vendors"]:
        vendors.append(
            Vendor(
                id=row["id"],
                name=row["name"],
                aliases=tuple(row.get("aliases", [])),
                email_domains=tuple(domain.casefold() for domain in row.get("email_domains", [])),
            )
        )
    return vendors


def load_open_jobs(path: Path) -> list[OpenJob]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        OpenJob(
            po_number=row["po_number"],
            job_name=row["job_name"],
            status=row["status"],
            qbo_customer_id=row.get("qbo_customer_id"),
        )
        for row in payload["jobs"]
    ]


class VendorDirectory:
    def __init__(self, vendors: list[Vendor]) -> None:
        self._by_key: dict[str, Vendor] = {}
        for vendor in vendors:
            for name in (vendor.name, *vendor.aliases):
                self._by_key[vendor_key(name)] = vendor

    def resolve(self, extracted_name: str | None) -> Vendor | None:
        if extracted_name is None:
            return None
        return self._by_key.get(vendor_key(extracted_name))


class JobDirectory:
    def __init__(self, jobs: list[OpenJob]) -> None:
        self._by_po: dict[str, OpenJob] = {}
        for job in jobs:
            key = po_key(job.po_number)
            if key is None:
                raise ValueError(f"Job file has a blank PO: {job.job_name}")
            self._by_po[key] = job

    def get(self, po_number: str | None) -> OpenJob | None:
        key = None if po_number is None else po_key(po_number)
        if key is None:
            return None
        return self._by_po.get(key)
