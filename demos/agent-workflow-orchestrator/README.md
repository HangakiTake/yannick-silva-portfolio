# Lead workflow orchestrator

Brightfield Solar is a fictional installer. This runs a short lead-to-kickoff workflow on a mock CRM, a mock calendar and a mock outbox. The systems are SQLite files. Nothing is on the network, and nothing leaves the machine until someone approves that exact draft.

```
cd demos/agent-workflow-orchestrator
python3 -m pip install -r requirements.txt
python3 -m pytest -q
python3 -m src.cli run --inbox data/leads.json --state state
```

That first run prints a JSON summary. On this machine it was:

```
{"crm": 9, "tasks": 4, "events": 8, "drafts": 9, "drafts_queued": 9, "outbox": 0, "exceptions": 1, "approvals": 0, "rejections": 0}
```

Twelve inbox rows become 9 CRM records: 2 rows are exact copies, and 1 is the same person with different capitalisation, spacing and phone punctuation. Four leads are missing a usable site address or monthly kWh, so each gets one internal task. Eight discovery calls are booked. `farid.malik@example.net` is seeded to fail the calendar three times and is handed to Priya Shah. Grace Lee is seeded to fail twice and then get a slot. The sleeps are 0.05s and then 0.10s. One run with that default backoff took 0.464 seconds. The same run with `--backoff 0` took 0.126 seconds.

Drafts stay queued. The outbox stays empty.

```
python3 -m src.cli approve DRAFT_ID --by "Sam Okonkwo" --state state
python3 -m src.cli run --inbox data/leads.json --state state
```

Approving the eight leads who have a booking, then running again, put 8 messages in the outbox and left Farid's draft queued. A further run left those counts unchanged. The tests count writes on that quiet run: 0 new CRM rows, 0 new events, 0 new emails.

```
python3 -m src.cli run --inbox data/leads.json --state state --crash-after 4
```

Exit code 2. On this inbox the fourth new ledger mark is the first lead's calendar booking, before any draft. Run the same command without `--crash-after` and the final records match a clean run.

`--retry-escalated` tries an escalated booking again. The seeded faults stay on unless you also pass `--no-faults`. With both flags, Farid is booked, the exception row is removed, and the draft is rewritten. It is still queued until someone approves the new text.

The idempotency key is `sha256(step + normalised email + sha256 of the canonical payload)`. A step already marked done is skipped. Calendar events, CRM rows and outbox messages also use a stable id, so a crash between the write and the ledger mark does not create a second record.

`src/` is the standard library only. pytest is the test runner. The follow-up text is a template; the draft starts with `[template draft — not a language model]`.
