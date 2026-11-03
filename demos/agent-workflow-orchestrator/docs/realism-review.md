# Realism-gate review: lead workflow orchestrator

Reviewer: an ops lead who has had an agent create two CRM records for one person, book two calls in one slot, and email a customer something nobody approved. The questions were: what happens with duplicate and half-empty leads, what happens when the calendar fails, and can a draft leave the building on its own?

## What was tried

The 12-row inbox, then rows written to poke the edges. Each line is a pytest case that passed with the suite (`22 passed in 1.73s`).

| Input | Result |
|---|---|
| Exact copy of Amira Hassan, and an exact copy of Chiara Vogel | One CRM row each. The second pass is an audit skip |
| Ben Okoye again as ` BEN.OKOYE@Example.com ` with a spaced name and a punctuated phone | One CRM row, phone `4155550177`, name `Ben Okoye` |
| Same email later, with phone blank, address `TBD`, kWh `n/a` | Usable phone, address and kWh kept |
| Same email later, kWh `about 900` then `900` | CRM becomes `900`. The task is removed |
| Blank address, `TBD`, `see attached`, `about 900`, `n/a`, `0` | One task listing the unusable fields. `1,150` and `640 kWh` and a JSON number `640` are kept |
| `Ada <ADA@example.com>` | Stored as `ada@example.com` |
| `not-an-email` | One rejection row, read back, `verified: true`. A second run does not add another |
| Name `Robert'); DROP TABLE crm;--` | Stored as the name. The `crm` table is still there |
| Grace Lee, seeded 503s | Attempts 1 and 2 sleep 0.05s then 0.10s. Attempt 3 books one slot |
| Farid Malik, seeded 503 on every try | Three attempts, no event, one exception for Priya Shah. The next run does not hit the calendar again |
| `--retry-escalated --no-faults` after Farid | One event, exception removed, draft rewritten with the slot, still queued |
| Full run, then the same run again | 0 new CRM writes, 0 new tasks, 0 new events, 0 new emails. Outbox still empty |
| Approve the eight booked drafts, run, run again | Outbox 8, then 0 further emails. Farid stays queued |
| Send with no approval, with someone else's approval, with the wrong body hash, or after the body is edited | `ApprovalRequired`. Outbox unchanged. Draft stays queued |
| Approver name of spaces | Rejected. No approval row |
| Crash after ledger marks 1, 4, 7, 15, 30, 45, and past the end | Resume matches a clean run |
| Crash after the calendar insert, before the ledger mark | One event, same slot, after resume |
| Change the lead's name after the note was sent | Outbox text unchanged. One exception: the lead changed and needs a new approval |
| A store opened the way `run` opens approvals | `save_approval` raises, and an INSERT on that connection raises |

## Findings

1. **Fixed.** A run could open the approval file writable, so the same program that sends could also approve. `run` now opens `approvals.sqlite` read-only. Only `approve` writes it.
2. **Fixed.** `Ada <ADA@example.com>` was dropped as a bad email. The address inside the brackets is the one that is stored.
3. **Fixed.** A second row could have blanked a phone or an address we already had. A usable value is kept. A later usable value still wins, which is how `about 900` becomes `900`.
4. **Fixed.** A draft approved, then edited, would have been a different sentence under an old approval. The send checks the body hash and refuses.
5. **Fixed.** Changing a lead after the note was sent rewrote nothing visible except the CRM. The sent text stays. One exception names Priya Shah.
6. **Fixed.** A rejected email was logged `verified: false` after the row was stored. The audit follows the read-back.
7. **Open, by design.** The calendar faults are seeded for two addresses so a retry and an escalation can be seen. They are not a measurement of a real calendar. `--no-faults` is how an operator says the outage is over. `--retry-escalated` alone tries again and, with the seed still on, fails again and leaves the one exception.
8. **Open, by design.** The follow-up is a template. The first line of the draft says so. No model is called.
9. **Open.** The approval file is local. The run's connection cannot insert a row. A person who can write that file on disk can. There is no second user and no retention rule for the audit log, which stores the email address.

## Are the headline numbers planted?

The 9 CRM records are the distinct emails in `data/leads.json` after normalisation, and the tests compute that from the file. The 8 events are those 9 minus the one seeded permanent failure. The 4 tasks are the leads whose address or kWh is unusable under the rules in `src/normalize.py`. The outbox stays at 0 until `approve` is run. A guessed "10 unique records" would be wrong for this file: 12 rows, 3 of them repeats, 9 people.

## Score sheet

| # | Item | Result | Why |
|---|---|---|---|
| 1 | Data realism | **Fail** | 12 synthetic leads written for this demo. No export from a CRM. |
| 2 | Grounding | Pass | The draft uses the lead's name, the booked slot, and the names of missing fields. It does not fill in a kWh figure. The banner says the text is a template. |
| 3 | Evaluation | **Fail** | The checks and the inbox were written together. There is no held-out real export. |
| 4 | Failure modes / human check | Pass | Duplicates, placeholders, retries, escalation, crash resume, and a send that refuses without a matching approval are all tested. Unapproved drafts stay queued. |
| 5 | Integration | **Fail** | CRM, calendar and outbox are tables in SQLite. No vendor account is connected. |
| 6 | Security | **Fail** | No secrets and no network calls. The run cannot write an approval. The file is still on a local disk the same user can edit, and the audit log keeps the email. |
| 7 | Cost and latency | Pass | No model call and no invoice. One default run: 0.464 seconds, of which the seeded sleeps are 0.30 seconds. With `--backoff 0`: 0.126 seconds. The suite: 1.73 seconds. |
| 8 | Honest claims | Pass | The project page states the synthetic inbox, the mock systems, the template, the seeded faults, and that nothing is sent until a person approves that draft. |

**Ship as a portfolio demo:** yes. The fails are the missing real inbox, the missing vendor accounts, and the local approval file.

**Ready for a live CRM:** no.
