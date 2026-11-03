# Test report

Command: `python3 -m pytest -q tests` in `demos/agent-workflow-orchestrator`.

```
22 passed in 1.73s
```

Python 3.12.3. pytest 9.2.0. No network. No API key.

## What the tests check

- 12 inbox rows, 9 CRM records. Two rows are byte-for-byte copies. One row matches Ben Okoye only after the email is lowercased and trimmed, the name spacing is collapsed, and the phone is reduced to digits.
- Placeholders become one task each: blank address, `TBD`, `see attached`, `about 900`, `n/a`. `1,150` is stored as `1150`. `0` is treated as missing. Four tasks on the sample inbox.
- A later blank phone, `TBD` address or `n/a` kWh does not replace a usable value. A later real kWh does replace `about 900`, and the task is closed. One CRM row either way.
- A second run of the sample: 0 new CRM writes, 0 new tasks, 0 new events, 0 new emails.
- Approving every draft except Farid's, then running: 8 new outbox rows, 0 new CRM writes, 0 new events. The next run adds 0 emails. Farid's draft stays `queued`.
- `--crash-after 4` stops with one event and no drafts. Resume matches a clean run. The same check at crash points 1, 7, 15, 30, 45 and past the last step also matches.
- A crash after the calendar insert and before the ledger mark still leaves one event for that lead, on the same slot.
- Grace Lee: 3 attempts, sleeps of 0.05s then 0.10s, one event.
- Farid Malik: 3 failures, one exception owned by Priya Shah, no event. The next run does not call the calendar again and does not add a second exception.
- `deliver()` raises `ApprovalRequired` with no approval, with another lead's approval, and when the stored hash is not the draft hash. A blank approver name is rejected. Editing the body after a valid approval blocks the send. The draft stays queued and the outbox stays empty.
- An approved send is read back from the outbox. A second `deliver()` of the same draft does not insert another row.
- Every audit line has a timestamp, run id, step, key, input summary, result and actor. Each CRM row, task, event and draft has a line with `verified: true`. Sends before approval are `refused: no approval` with `verified: false`.
- Clearing the seeded fault and retrying books Farid, drops the exception, and rewrites the queued draft with the slot. `deliver()` still refuses until that new body is approved.
- A sent note is kept when the lead's name changes later. The CRM takes the new name. One exception asks Priya Shah for a new approval. A second run does not add another exception or another outbox row.
- `Ada <ADA@example.com>` is stored as `ada@example.com`. A numeric `640` and `640 kWh` both become `640`. `not-an-email` is one rejection row, read back, with `verified: true`. A second run does not add another rejection. A name that looks like SQL is stored as a name and the `crm` table is still there.
- The idempotency key is sha256 of `step|normalised email|payload hash`.
- The CLI crash, resume, approve and blank-name paths match the library. The approve line in the audit has actor `Sam Okonkwo`.
- `src/pipeline.py` does not call `save_approval`. A store opened the way `run` opens it (`approvals_mode="ro"`) cannot insert an approval; the connection is read-only.
- `src/` does not mention urllib, requests, smtplib, http.client, imaplib or socket.

## CLI on this machine

Default backoff, first run, 0.464 seconds:

```
{"crm": 9, "tasks": 4, "events": 8, "drafts": 9, "drafts_queued": 9, "outbox": 0, "exceptions": 1, "approvals": 0, "rejections": 0}
```

After approving the eight booked leads and running again: outbox 8, drafts_queued 1, exceptions 1. The run after that printed the same counts. With `--backoff 0`, a first run took 0.126 seconds and printed the same first-run counts.
