# Code review 2 (ponytail-review), 2026-10-28

Scope: fixes from review 1, plus a second pass over src/engine.js planMessages, the n8n Pack nodes, src/dashboard.js. Same load assumption.

What this change does: DocuSign now looks back 365 days; acknowledgements count only for the current occurrence of an issue; the CLI reports the adapter's mode.

## Should fix

1. **A problem that clears and comes back is never alerted again — src/engine.js planMessages**
   - What this is: `state.sent` remembers which alert keys went out so nothing is sent twice. Urgent keys for a CHECK FAILED have an empty due date, e.g. `ZA19 TDK|tax||CHECK_FAILED`.
   - Problem: ZA19's DVLA lookup times out today (alert sent), works tomorrow, times out again next month. Same key, already in `sent`, so no urgent alert; and `urgentOn` still holds the old date, so the escalation key may also already be used. The third time it is completely silent. Same for UNVERIFIED / MISSING actions.
   - Fix: at the end of each run, forget urgent/action keys (and their escalation) for issues that are no longer true. Keep reminder keys, which carry the due date.
   - If we skip it: intermittent API failures, the most likely real-world fault, go quiet after the first time.

Checked and fine: dashboard escapes every value (`h()`); Pack nodes throw on a count mismatch, so a lost item fails the n8n execution visibly; secrets only via env / n8n credentials.

Verdict: fix 1 first.

## Outcome
Fixed, with unit test `an issue that clears and comes back alerts again`. Trade-off (accepted): an issue that flaps daily re-alerts on each return, which is noisy rather than silent.
