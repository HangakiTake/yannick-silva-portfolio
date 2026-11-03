# Demo plan and specs: fleet compliance assistant (UK vehicle rental)

Status: DRAFT, waiting for Yannick's approval. Nothing is built yet.
Source job: [AI Automation Assistant](https://www.upwork.com/jobs/~022115432223314149061) (id 2115432223314149061, K.A Rentals Ltd, UK, hourly, no rate given, posted 28 Oct 2026 14:15 Europe/Zurich).

## 1. What the client asked for (their words)
- "Build an AI assistant that monitors my fleet and automatically reminds me of upcoming tasks and compliance deadlines."
- Uses Fleetworks, DocuSign, Excel spreadsheets and reminders; wants them "connected wherever possible".
- Monitor MID insured ("green") status "using an authorised method where available"; flag missing/unverified.
- Track MOT, road tax, insurance renewals, servicing and other compliance dates.
- Advance reminders and urgent alerts via WhatsApp, email or SMS.
- Flag missing documents, unsigned DocuSign agreements, overdue tasks.
- Simple dashboard per vehicle: status, upcoming deadlines, outstanding actions.
- Escalate unresolved issues; keep a record of checks and reminders.
- Deliverables: working tested system, setup instructions, handover session; protect customer data; clearly flag failed checks.
- Proposal must cover: examples, approach, integration limitations, delivery time, setup cost, running costs.

## 2. The demo in one line
An n8n workflow that reads a fleet register (Excel/Google Sheet, 25 fictional vehicles), checks tax and MOT status against the official DVLA and DVSA APIs, tracks insurance/service/document dates, chases unsigned agreements (DocuSign sandbox), sends tiered reminders and escalations by email and WhatsApp, logs every check, and shows a one-page status dashboard. All vehicle and customer data is synthetic; only test-safe registration numbers are used.

## 3. Requirements and how each is tested

| # | Requirement | Source | How it is tested | Pass threshold |
|---|---|---|---|---|
| R1 | Track MOT, tax, insurance, service and other dates per vehicle | Post | Register with 25 vehicles and an answer key of due dates and statuses | 100% of statuses (OK / due soon / overdue) match the answer key |
| R2 | Official tax and MOT status, not typed-in guesses | Post ("authorised method") + business standard | DVLA Vehicle Enquiry API and DVSA MOT History API called for each test reg; results compared to the APIs' own test responses | Every lookup returns or is logged as failed; 0 silent passes |
| R3 | Insurance (MID) status flagged when it can't be verified automatically | Post | No automated MID feed in the demo; each vehicle has an "insurance verified on" date and source; anything older than the set window shows "unverified" | All 5 seeded unverified/expired cases flagged; integration limitation written in README |
| R4 | Advance reminders on a ladder (e.g. 30/14/7/1 days) | Post | Run the workflow with a mocked "today" across 40 days | Each seeded deadline gets each reminder exactly once; 0 duplicates |
| R5 | Urgent alerts and escalation if unresolved | Post | Leave 3 seeded issues unacknowledged | Escalation sent after the set delay to the second contact; issue stays open until marked done |
| R6 | Multi-channel: email plus WhatsApp (SMS optional) | Post | Send to test inbox and WhatsApp sandbox number | 100% of test alerts delivered on both channels; delivery failures logged |
| R7 | Unsigned DocuSign agreements and missing documents flagged | Post | DocuSign developer sandbox with 4 envelopes (2 signed, 2 pending); register with 3 missing docs | All 2 pending and 3 missing items flagged; signed ones cleared |
| R8 | Failed checks clearly flagged, never hidden | Post | Force API errors (bad key, timeout, unknown reg) | Each failure shows "CHECK FAILED" on the dashboard and in an alert within one run |
| R9 | Record of checks and reminders | Post | Audit log sheet: timestamp, vehicle, check, result, message sent | 100% of checks and messages from the 40-day run present in the log |
| R10 | Simple dashboard per vehicle | Post | One page: traffic-light status, next deadline, open actions; a non-technical reviewer answers 5 set questions | 5/5 correct in under 2 minutes |
| R11 | Protect customer data | Post + UK GDPR common sense | Secrets in n8n credentials only, no customer data in messages beyond reg + task, log has no personal data | Review checklist passes; 0 secrets in exported workflow JSON |
| R12 | Someone else can set it up | Post (setup instructions, handover) | README + 5-minute handover video script; fresh reader imports the workflow | Reader gets a green run without help |
| R13 | Running cost stated honestly | Post | Cost sheet built from the providers' current price pages on build day | Every line cites its source page and date |

## 4. Stack and why
- **n8n**: the client named Make/Zapier/n8n; n8n has DocuSign, Google Sheets, email, Twilio and HTTP nodes and can be self-hosted, which keeps customer data under his control and running cost low.
- **Excel / Google Sheets register**: he already runs on spreadsheets, so the register stays where he works.
- **DVLA Vehicle Enquiry Service API + DVSA MOT History API**: official government sources for tax and MOT status, which is the "authorised method" for those two checks.
- **DocuSign developer sandbox**: free, same API as production, so envelope status checks are real.
- **Twilio (WhatsApp sandbox / SMS) + email**: the standard way to send WhatsApp and SMS from an automation.
- **Small LLM step (optional)**: writes the daily plain-English summary ("3 things need you today"); all checks stay rule-based so nothing is guessed.
- **Dashboard**: a Sheets status tab (or Looker Studio page) so it opens on his phone without a new app.

## 5. Build steps and time (about 8–10 hours)
1. Synthetic fleet register, customers, documents, answer key, seeded issues: 1.5 h
2. n8n: daily schedule, register read, DVLA/DVSA lookups, date logic, status calc: 2.5 h
3. DocuSign sandbox envelopes + status check; missing-docs check: 1 h
4. Reminder ladder, escalation, email + WhatsApp, audit log: 2 h
5. Dashboard tab, failure flags, 40-day mocked-date test run and checks (R1–R13): 1.5 h
6. README, cost sheet, screenshots, realism-gate review: 1 h

## 6. Accounts or keys Yannick must set up
- **DVLA Vehicle Enquiry Service API key** (free, apply on the DVLA developer portal; can take a few days).
- **DVSA MOT History API access** (free, register on the DVSA site; also can take a few days).
- **DocuSign developer (sandbox) account** (free).
- **Twilio account** for the WhatsApp sandbox / SMS (free trial credit).
- **n8n**: either n8n Cloud trial or I self-host it on my box (no account needed for self-host).
- A test Gmail/Google Sheet is fine; no customer data involved.
- If the API keys are slow to arrive, the demo runs on recorded sample responses first and switches to live keys later.

## 7. Integration limitations (for the proposal and README)
- MID: no free bulk API; askMID is single-vehicle. Fleet-level checks need an authorised commercial route (MIB) or the insurer's own fleet portal. Demo flags "unverified" rather than scraping. Verify current MIB options before quoting.
- Fleetworks: depends on whether his plan offers an API or scheduled export; fallback is a scheduled export into the register.
- Running costs to be quoted from current price pages (n8n, Twilio per-message) on build day, not from memory.

## 8. Portfolio packaging
- Upwork portfolio item: screenshots of the dashboard, an alert on WhatsApp/email, the audit log, and the n8n canvas; short write-up with the test results table.
- Repo kept private; "walkthrough on request" in proposals. Only quote figures from the final README.
