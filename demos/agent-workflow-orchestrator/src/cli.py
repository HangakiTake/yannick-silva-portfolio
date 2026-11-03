"""Run the workflow, or record a person's approval. Nothing is sent until approve."""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path

from src.auditlog import AuditLog
from src.mailer import approve
from src.pipeline import run
from src.store import Store


def summarise(store: Store) -> dict:
    drafts = store.list_drafts()
    return {
        "crm": len(store.list_crm()),
        "tasks": len(store.list_tasks()),
        "events": len(store.list_events()),
        "drafts": len(drafts),
        "drafts_queued": sum(1 for row in drafts if row["status"] == "queued"),
        "outbox": len(store.list_outbox()),
        "exceptions": len(store.list_exceptions()),
        "approvals": len(store.list_approvals()),
        "rejections": len(store.list_rejections()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Brightfield Solar lead workflow (offline mocks)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_parser = sub.add_parser("run", help="run the six steps against the mock systems")
    run_parser.add_argument("--inbox", required=True)
    run_parser.add_argument("--state", required=True)
    run_parser.add_argument("--crash-after", type=int, default=None)
    run_parser.add_argument("--retry-escalated", action="store_true")
    run_parser.add_argument(
        "--no-faults",
        action="store_true",
        help="do not seed the calendar failures (use after an escalated lead should be booked)",
    )
    run_parser.add_argument("--backoff", type=float, default=0.05)

    approve_parser = sub.add_parser("approve", help="approve one draft so a later run may send it")
    approve_parser.add_argument("draft_id")
    approve_parser.add_argument("--by", required=True)
    approve_parser.add_argument("--state", required=True)

    args = parser.parse_args(argv)
    state = Path(args.state)
    # A run can read approvals. Only `approve` can write them.
    if args.cmd == "approve":
        store = Store(state / "orchestrator.sqlite", approvals_mode="rw")
    else:
        store = Store(state / "orchestrator.sqlite", approvals_mode="ro")
    audit = AuditLog(state / "audit.jsonl", run_id=uuid.uuid4().hex)
    try:
        if args.cmd == "approve":
            try:
                saved = approve(store, args.draft_id, args.by, audit)
            except ValueError as exc:
                print(str(exc), file=sys.stderr)
                return 1
            print(json.dumps({"draft_id": saved["draft_id"], "by": saved["by_name"]}))
            return 0
        run(
            args.inbox,
            store,
            audit,
            crash_after=args.crash_after,
            retry_escalated=args.retry_escalated,
            sleep=time.sleep,
            base_delay=args.backoff,
            failures={} if args.no_faults else None,
        )
        print(json.dumps(summarise(store)))
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
