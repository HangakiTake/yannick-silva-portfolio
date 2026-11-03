# Code review 1 (ponytail-review), 2026-10-28

Scope: whole repo at this point (src/, scripts/build_n8n.js, tests/). Assumed load: one small UK hire firm, 25–500 vehicles, one run a day.

What this change does: A daily Node.js run reads the vehicle register, looks up tax (DVLA), MOT (DVSA) and hire agreements (DocuSign) through a mock/live switch, gives each item a status, plans de-duplicated reminders and escalations, and writes an outbox, an append-only audit log and a dashboard. n8n schedules it and does the sending.

## Must fix

1. **Live DocuSign lookup only sees today's changes — src/run.js:29, src/adapters.js (docusign)**
   - What this is: the DocuSign "list envelope status changes" call returns envelopes whose status changed on or after `from_date`.
   - Problem: the run passes `from_date = today`. In live mode, an agreement sent last week and not touched since is not in the response, so every such vehicle shows "Envelope not found" (CHECK FAILED) and an urgent alert goes out. Mock mode hides this because the fixture holds every envelope.
   - Fix: pass `today − cfg.docusignLookbackDays` (default 365) and note pagination as a limit.
   - If we skip it: on day one of going live every hire agreement goes red and staff learn to ignore the alerts.

## Should fix

2. **Old acknowledgement silences future escalations — src/engine.js planMessages `acked`**
   - What this is: an acknowledgement row says "a person has seen this issue".
   - Problem: it matches on registration + check only. If ZA03 tax was acknowledged on 2026-11-03, the next time ZA03's tax goes overdue (2027) that old row still counts, so the escalation never fires.
   - Fix: count an acknowledgement only if `acknowledged_on` is on or after the day this urgent issue started (`urgentOn[k]`).
   - If we skip it: the second-contact safety net quietly stops working for repeat offenders.

## Nice to have

3. **`--json` reports mode from env, not the adapter — src/run.js CLI.** Use `adapters.mode`. Harmless today because both default to mock.
4. **state.sent grows forever — src/engine.js.** About 2 keys per vehicle per month; 500 vehicles × 5 years is roughly 60k short strings. Fine at this load; prune keys whose due date is over a year old if it ever matters.

Verdict: fix 1 and 2 first.
Not checked: live API behaviour (no accounts), n8n UI rendering of the workflow (import and CLI execute only).

## Outcome
1, 2 and 3 fixed with unit tests (`live DocuSign is asked for a year of changes`, `acknowledgement from an earlier occurrence does not stop escalation`). 4 left as is (named limit, fine at the stated load).
