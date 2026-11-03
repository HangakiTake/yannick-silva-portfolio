# Lead workflow orchestrator

Fictional company: Brightfield Solar. Offline demo. Python 3 standard library and pytest. No accounts and no network.

## Workflow

The inbox is `data/leads.json` (12 rows).

1. Intake. Normalise the email, the name, the phone and the monthly kWh. Reject a row with no usable email and read that rejection back.
2. Upsert the mock CRM by normalised email. A later empty or placeholder value does not wipe a usable one.
3. If the site address or the monthly kWh is unusable, open one internal task. If a later row makes the field usable, close the task.
4. Book the first free discovery slot. The mock calendar fails Grace Lee twice, then books her. It fails Farid Malik on every attempt, up to 3, then writes one exception for Priya Shah.
5. Write a template draft. The banner says it is not a language model.
6. Send only when `approve DRAFT_ID --by NAME` has recorded that person against the current body hash. Read the outbox row back.

## Rules

- Ledger key: sha256 of `step`, the normalised email, and the sha256 of the canonical JSON payload. Status `done` skips the step. Status `escalated` skips unless `--retry-escalated`.
- Writes use a stable id. A crash after the write and before the ledger mark does not create a second CRM row, event or email.
- `--crash-after N` exits with status 2 after N newly committed ledger marks.
- Every audit line has a timestamp, run id, step, key, input summary, result and actor (`agent`, or the approver's name).
- A write is marked `verified: true` only after a read-back matches.
- `run` opens the approval file read-only. `approve` is the only writer.

## Sample result the tests lock in

9 CRM records, 4 tasks, 8 events, 9 queued drafts, 0 outbox rows, 1 exception. After the eight booked drafts are approved: 8 outbox rows and 1 queued draft. The next run adds 0 CRM rows, 0 events and 0 emails.
