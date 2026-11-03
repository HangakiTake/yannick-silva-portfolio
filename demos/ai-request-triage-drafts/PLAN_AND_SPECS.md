# ai-request-triage-drafts: plan and specs

Matches Upwork job 2117604263222640994, "Set Up Simple AI Workflow Automation" (US client wants one AI-powered workflow that processes incoming requests, organises the information into a summary, prepares a draft response for human review, is tested on sample requests, and comes with a brief handoff guide; asks which tools are recommended and what subscriptions or costs are needed). Portfolio build on synthetic data, not client work. Every number below is a target until measured.

## 1. What the demo is
An "incoming request to reviewed draft reply" workflow for a fictional small services business, built so it can be wired into Zapier or Power Automate:
1. **Intake.** Reads incoming requests from a sample inbox export (EML/JSON files and a web-form CSV): sender, subject, body, attachments listed by name. Handles forwarded threads, signatures, quoted replies, HTML-only bodies, non-English requests (FR/PT/ES) and empty or spam-like messages.
2. **Organise.** One LLM call with a strict JSON schema extracts: request type (quote, support, booking, billing, complaint, other), urgency, customer name, company, contact details, key dates/amounts, a 2–3 line summary, missing info to ask for, and a confidence score. Low confidence or unknown type routes to "needs human".
3. **Draft.** Writes a reply draft in the business's tone from a short tone/policy file (prices, opening hours, what we never promise). Drafts are saved as drafts only (a drafts folder / CSV / Gmail-or-Outlook-style draft JSON), never sent. Drafts never invent prices, dates or commitments that are not in the policy file; they ask for missing info instead.
4. **Review log.** Every request gets a row in a review log (CSV/XLSX): summary, fields, draft path, confidence, flags, so a person can approve or edit.
5. **Handoff guide.** A one-page HANDOFF.md: how to connect it to Zapier (Webhooks by Zapier / Code step calling the script or a small HTTP endpoint) or Power Automate (HTTP action), which accounts and API keys are needed, expected monthly costs per 100/1,000 requests with dated price assumptions, and how to change the tone file.

## 2. Requirements
JP = job post, PS = professional standard.
| ID | Src | Requirement |
|---|---|---|
| R01 | JP | Processes incoming requests from realistic sources (email export, form CSV) |
| R02 | JP | Organises information: structured fields plus a short summary per request |
| R03 | JP | Generates a draft response for review, never auto-sends |
| R04 | JP | Tested with sample requests; results reported |
| R05 | JP | Brief handoff guide, including recommended tools and required subscriptions/costs |
| R06 | PS | Strict JSON schema validation on LLM output; invalid output retried once then flagged, never silently accepted |
| R07 | PS | Drafts contain no invented facts: prices, dates and commitments only from the policy file (checked by a test) |
| R08 | PS | Low-confidence, angry/complaint, legal or payment-dispute requests flagged "needs human" |
| R09 | PS | PII handled carefully: no request content in logs beyond the review log; redaction option for the log |
| R10 | PS | Runs fully offline in a deterministic mock-LLM mode; live mode (OpenAI or Anthropic) only when an API key env var is set |
| R11 | PS | Idempotent: re-running on the same inbox does not duplicate drafts or log rows |
| R12 | PS | No secrets in the repo; synthetic data only |

## 3. Tests and pass thresholds
| Test | Pass threshold |
|---|---|
| Sample set: at least 40 synthetic requests, at least 15 deliberately messy (threads, signatures, HTML-only, other languages, empty, spam), hand-labelled gold fields written before building | Gold labels committed before the extractor |
| Request type classification vs gold (mock mode deterministic, plus live if a key is available) | ≥90% correct; every miss listed in TEST_REPORT |
| Field extraction (name, contact, dates, amounts) vs gold | ≥90% field-level accuracy; 0 fabricated values (a field not in the request must be empty) |
| Schema validation | 100% of malformed LLM outputs (fuzzed) rejected or retried, 0 accepted |
| Draft fact check | 0 drafts containing a price, date or commitment not in the request or policy file (automated check) |
| Needs-human routing | 100% of complaint/legal/payment-dispute and low-confidence gold cases flagged |
| Never-send guarantee | No code path sends mail; test asserts drafts only |
| Idempotency | Second run on same inbox produces 0 new rows/drafts |
| Live mode (optional) | If a key is available, report accuracy on the same 40 requests; otherwise reported as "not run" |

Then the realism-gate review (skeptical buyer, messy inputs) and ponytail review until no must-fix or should-fix items remain.

## 4. Stack and why
- **Python 3.11**: email/CSV parsing and the pipeline; Yannick's working language.
- **Pydantic**: JSON schema for extracted fields and validation of LLM output.
- **OpenAI or Anthropic SDK behind one small adapter**: the client asked for tool recommendations; showing either model works keeps it vendor-neutral.
- **FastAPI (single endpoint)**: lets Zapier Webhooks or Power Automate's HTTP action call the workflow, matching "works with my existing tools".
- **openpyxl/CSV**: review log a non-technical person can open.
- **pytest + GitHub Actions**: tests above in mock mode.
- **Zapier / Power Automate**: documented in the handoff guide as the glue (not required to run the demo).

## 5. Build time
About 6–9 hours of agent build time, plus review cycles.

## 6. Accounts needed
None to build and merge. Mock mode runs without keys. Optional live-mode numbers need an OPENAI_API_KEY or ANTHROPIC_API_KEY (report live mode as not run if absent). Zapier/Power Automate are documented, not required.

## 7. Portfolio page
Project page under projects/ matching the existing ones: who it's for (a small business drowning in incoming requests that wants draft replies ready for a quick human check) and the use case, real test numbers from TEST_REPORT, honest caveats (synthetic requests, mock-mode figures, live mode not run unless it was, Zapier/Power Automate wiring documented but not demoed live).
