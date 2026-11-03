# Realism gate review: Fleet Compliance Assistant (demo)

Reviewed 2026-10-28. Reviewer role-played: **the compliance lead at a UK van and car hire firm** who has been burned before by a "compliance bot" that showed green while a van was out on hire with no tax. They don't care about visuals. Their questions: *Can it ever say OK when it doesn't know? Does it cover every van? Will my staff ignore it?*

## Verdict

**Ships as a portfolio demo: yes.** Section 8 (honest claims) passes, and every failed item is listed below and in the README limits.
**Ready for real client data: no.** Sections 2, 3 and 6 each have open items: there's no live API run, no held-out data, and no data-retention policy. This is expected for a demo running on recorded responses.

## Findings, most severe first

1. **(Fixed) Documents could pass silently.** If a vehicle had no rows in documents.csv, or its row was typed `za03dvk`, it showed documents **OK**. That is a silent pass of exactly the kind the buyer fears. Fix: each vehicle now needs a "present" row for every required document (set in config); missing rows mean MISSING; registrations are matched ignoring case and spaces. Kept as stress cases 5 and 6 and as a unit test.
2. **(Fixed) Duplicate rows like `ZA04ECK` vs `ZA04 ECK` were not caught.** Duplicates are now detected on the canonical registration.
3. **(Fixed, found in n8n testing) False "SENT".** With no SMTP credential, the n8n Email node put its failed items on the *success* output, so 24 email alerts were logged as SENT. SENT now requires delivery evidence (a Twilio `sid` or SMTP `messageId`); without it the alert is FAILED. Re-test: 0 SENT, 48 FAILED (tests/n8n_import_result.txt).
4. **(Open, by design) Insurance can't be auto-verified.** There is no MID API for a small hire firm, so the system can only remind staff to check askMID and record the date. It never shows insurance as verified on its own. This is a business limit, not a bug, and it's stated in the README.
5. **(Open) There has been no live run against DVLA, DVSA or DocuSign.** All lookups are recorded responses built to the documented formats. Field drift in the real APIs (for example DVSA's `motTestDueDate` or new error codes) is untested. DVLA VES registration is currently closed, which may block going live.
6. **(Open) Data is synthetic only.** No public, licence-clean fleet register was available. The answer key was written by hand before the run, but it was written by the same person who wrote the generator, so the score is self-graded. The messy-input stress test (below) is the independent check.
7. **(Open) No retention or residency policy yet.** The audit log grows forever, and if n8n Cloud is used, data is held in the EU (Frankfurt). The client needs to decide on both.

## Stress test: messy inputs (`node tests/stress.js`, day 2026-11-02)

These are inputs the generator never produced. Each one is applied to a copy of the data. **Pass** means the problem is visible on the vehicle and the vehicle isn't green.

Before fixes:

| Messy input | Result |
|---|---|
| UK-format date in register (01/04/2027) | PASS |
| Blank service date | PASS |
| Duplicate row, one written without the space (ZA04ECK) | FAIL |
| Lower-case, extra spaces in register (" za15  pbk") | PASS |
| Missing document row typed lower-case without space (za03dvk) | FAIL |
| Vehicle with no document rows at all (ZA16) | FAIL |
| Envelope ID not in DocuSign | PASS |
| UTF-8 BOM + CRLF line endings (Excel export) | PASS |
| Blank registration row | PASS |
| "present" typed as Y / TRUE | FAIL |
| Formula in a register cell (=HYPERLINK...) | PASS |

After fixes (also run by `npm test`):

| Messy input | Result |
|---|---|
| UK-format date in register (01/04/2027) | PASS |
| Blank service date | PASS |
| Duplicate row, one written without the space (ZA04ECK) | PASS |
| Lower-case, extra spaces in register (" za15  pbk") | PASS |
| Missing document row typed lower-case without space (za03dvk) | PASS |
| Vehicle with no document rows at all (ZA16) | PASS |
| Envelope ID not in DocuSign | PASS |
| UTF-8 BOM + CRLF line endings (Excel export) | PASS |
| Blank registration row | PASS |
| "present" typed as Y / TRUE | PASS |
| Formula in a register cell (=HYPERLINK...) | PASS |

Not covered: scanned or PDF documents, which are out of scope because the system reads a register, not documents. Also not covered: a real DVLA response for a Northern Ireland plate, and DocuSign pagination beyond 100 envelopes (not implemented; listed in HANDOVER as a go-live task).

## Are the headline numbers planted?

Partly, and we say so. R1 is 150/150 statuses on 25 synthetic vehicles, checked against a key written before the run. The denominator is stated. The scenarios were chosen by the builder, which is why the stress table and the "NOT RUN" rows exist. Nothing claims real-world accuracy.

## Score sheet (Pass/Fail; no averaging)

| # | Section | Result | Evidence |
|---|---|---|---|
| 1 | Data realism | **Fail** | Fixtures follow the official DVLA, DVSA and DocuSign response shapes and can be re-run (`npm run generate`), and there are 11 messy variants. But no independent real data was used. |
| 2 | Grounding | **Pass** for this domain | Every status shows its source (DVLA, DVSA, register, DocuSign, documents list) and the detail, for example "DVLA: HTTP 404". Unknown always means CHECK FAILED and never OK. There are no ML or LLM fields to calibrate. |
| 3 | Evaluation | **Fail** | Labels were fixed before the run, with denominators. Failures are kept as regression fixtures (stress, unit and ZA18–ZA24). There is no held-out set and no live API run. |
| 4 | Failure modes / HITL | **Pass** | Errors are isolated per row (R8). A 25/25 bad-key run shows all CHECK FAILED. Duplicates are flagged. Escalation needs a person to acknowledge with a role. Delivery FAILED is logged and never SENT. |
| 5 | Integration | **Pass** | The register CSV is the system of record (named in INPUT_SPEC). Alerts are idempotent through reminder keys in state.json, and R4 shows 0 duplicates. Intake is the office's existing spreadsheet. |
| 6 | Security | **Fail** | No secrets in the repo (R11 scan across 82 files). Credentials are held in n8n by name only. Messages contain only the registration and task. Retention and residency are undecided, and roles are not enforced in the demo. |
| 7 | Cost and latency | **Pass** | About 62 alerts a month for 25 vans, roughly $0.31 Twilio plus £0.99 Meta (docs/RUNNING_COSTS.md, sources dated). Mock-mode run for 25 vehicles: p50 107 ms, p95 121 ms over 20 runs. Live latency is unknown (10 s timeout per call). Hold rate: 10 red and 11 amber on day 0 of the demo fleet, which works out to a few minutes of staff time a day. |
| 8 | Honest claims | **Pass** | A DEMO banner appears on the dashboard. The README limits sit next to the claims. R6, R10 and R12 are marked NOT RUN with reasons. Every number names its dataset, date and denominator. |

## Fix list

**Quick wins (done):** documents required-set, registration normalisation, duplicate detection, n8n SENT-needs-evidence, stress test in `npm test`.

**Bigger upgrades (need the client or accounts):**
1. One live run with real DVLA and DVSA keys on 5 real vehicles, comparing results with gov.uk "check vehicle tax" and "check MOT history".
2. Send the first week's real alerts in DRY_RUN and have the fleet manager confirm them.
3. Set a retention policy and an access list.
4. Add DocuSign pagination.
5. Run the reviewer test (R10) with a staff member.
