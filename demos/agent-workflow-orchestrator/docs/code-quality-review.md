# Code review: lead workflow orchestrator

Reviewed against `PLAN_AND_SPECS.md` and the modules in `src/`. Categories are must-fix, should-fix, and minor. After the fixes below, the must-fix and should-fix lists are empty.

## What holds up

- One pass reads the inbox, upserts the CRM, opens or closes a task, books or escalates, writes a template draft, and sends only through `deliver()`.
- `deliver()` checks that an approval exists, the name is non-blank, and the hash matches the draft. The pipeline does not call `save_approval`. A store opened with `approvals_mode="ro"` uses a read-only SQLite connection.
- The ledger key is sha256 of the step, the normalised email, and the canonical payload hash. CRM rows, events, drafts and outbox rows also have a stable id, so a replay updates the same row.
- A write is committed, read back, and only then marked done. `verified` on the audit line follows that read-back.
- Retries stop at 3. The delays are `base * 2^(attempt-1)`. The tests record 0.05 then 0.10. The permanent failure writes one exception and the next run skips it.
- Parameters are bound in SQL. A name containing a quote and a `DROP TABLE` is stored as text.

## Fixed before this review was closed

1. **Must-fix.** `run` and `approve` shared one writable database, so the sending process could insert its own approval. Approvals are a separate file. `run` opens it read-only. Test: `test_run_cannot_grant_an_approval`.
2. **Should-fix.** An address written as `Name <email>` was rejected. `normalize_email` takes the address inside the brackets.
3. **Should-fix.** A second row with a blank phone or a placeholder address could have wiped a good record. `merge` keeps a usable field. A later usable kWh still replaces `about 900`, and the task is deleted.
4. **Should-fix.** JSON numbers and values like `640 kWh` needed a canonical form. Both become `640`. `0` stays missing.
5. **Should-fix.** Approval was checked at approval time only. `deliver()` compares the hash to the draft it is about to send, including after the body has been edited.
6. **Should-fix.** A sent draft was left in place with no signal when the lead later changed. The sent text stays, and one exception is recorded for Priya Shah. A second run does not add another.
7. **Should-fix.** A rejection was audited `verified: false` after the row was written. The line is now the read-back result, and the key is not empty.
8. **Should-fix.** Person rows were inserted with a table name interpolated into the SQL. Accepted leads and CRM rows now have their own statements.
9. **Should-fix.** Crash recovery was demonstrated at one checkpoint. The suite now resumes after checkpoints 1, 4, 7, 15, 30, 45 and a count past the end, and after a crash between the calendar insert and the ledger mark.
10. **Should-fix.** `--retry-escalated` could only fail again, because the CLI had no way to turn the seeded faults off. `--no-faults` clears them. The test books the escalated lead, removes the exception, and still sends nothing.

## Minor (left as they are)

- The failure counter lives in the process. A crash during Grace's two sleeps runs those failures again next time. The event id is per email, so the successful try still does not double-book.
- Creating the approval file, when it is missing, uses a short writable connection and then reopens it read-only. The run does not insert a row. The same OS user can open the file with their own connection.
- Slots are strings for Tuesday 10 Nov 2026, Pacific wall time, with 12:00 and 12:30 left empty. There is no timezone conversion.
- Tasks are rows. They have no assignee and no ticket system.
- A repeated inbox row writes extra skip and refusal lines in the audit log. It does not write extra CRM rows, events or emails.
- The default backoff is 0.05 seconds so a demo run finishes. A real outage policy would wait longer.
- Ids are 16 hex characters of a sha256. That is plenty for 12 leads and is not a security boundary.
- `--crash-after` counts new ledger marks. On this inbox, 4 is the first lead's booking.
- The draft greeting is plain text in SQLite. The outbox has no mail headers.

## Plan gaps that are stated, not coded around

No live CRM, mailbox or calendar is connected. The template is not a model call. Those are the realism-review fails.
