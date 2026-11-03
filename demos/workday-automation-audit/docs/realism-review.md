# Realism-gate review: workday automation audit

Reviewed 2026-11-03. Reviewer role: a solo bookkeeper who already had a "helpful" tool email a client a half-written chase note. She does not care about the page layout. Her questions: will this email my clients, will their names go to a model, and will it invent a task when I was vague?

## Verdict

Ships as a portfolio demo. The honest-claims section passes, and the open limits are the ones named on the project page.

Not ready for a real inbox. The week notes and the 32 inquiries were written for this demo, the model is the mock, and the n8n file has not been imported into a running n8n.

## What the stress pass found, and what changed

These were tried on top of the three labelled weeks. Each one is now a test in `tests/test_stress.py` unless noted.

| Input | Before | After |
|---|---|---|
| "2 hrs" once a week | Dropped. Not a task and not a question | 120 minutes, kept |
| "every morning I read email. takes 20mins." | The "takes 20mins" sentence was not attached, so the task had no duration | 20 minutes, weekday rate |
| "between 10 minutes and 3 hours" | Split on "and" and then dropped both halves | Question. Not averaged |
| "every other friday … 15 min" | Dropped | Question. Not guessed as weekly |
| "Mon-Fri I update the log, 10 min" | Question, no repeat rate | Weekday rate (about 21.7 a month) |
| "not a weekly task" | Scored as weekly, because the word weekly was in the sentence | Not a task |
| "~40/day" next to "about 20 min" | — | 20 minutes, not 40. The 40 is a volume |
| Voice line with a question mark in the middle ("severl times a week? no that's the voicemails") | Split, and the first half was easy to lose | Kept as one voicemail task |
| UK postcode `BS1 4ST` and `Dr. Lena Cho` | Postcode left a fragment; "Dr" was read as a street | Whole address removed; the name is a name |
| Phone written `(503) 555-0148` | Opening parenthesis left in the text | Whole number removed |
| Same inquiry sentence pasted twice | — | One task, frequency not doubled |
| Shopify export and a landlord text in one sentence | — | Two provisional tasks, both also on the questions list |
| 8 paraphrased inquiries ("circling back on the quote", "resend the P&L", "ACH didn't land") | — | Category, urgency, and service match; 0 sent |

## Score sheet (pass or fail, not averaged)

| # | Item | Result | Why |
|---|---|---|---|
| 1 | Data realism | **Fail** | One invented bookkeeper, three invented weeks, 32 invented emails. The answer key was written for those notes. |
| 2 | Grounding | Pass | Every kept task has the sentence it came from. The score row shows frequency, minutes, capture, effort, risk, and the weights. Unclear lines are listed as questions instead of given a number. |
| 3 | Evaluation | Pass for a demo | 25 tests, denominators in TEST_REPORT.md. The messy cases above are regression tests. There is no held-out real week. |
| 4 | Failure modes / a person in the loop | Pass | Customer-facing picks require approval. The runner's mailbox has no send method. 32/32 inquiries are drafts, 0 sent. The n8n send node is disabled and sits after Human approval. A draft without the words "not sent" is refused. |
| 5 | Integration | **Fail** | The workflow JSON was not imported into n8n. Gmail, Sheets, and Claude credentials are names only. Nobody has clicked "execute". |
| 6 | Security | **Fail** | Redaction is rules, measured at 65/65 on the planted list, and a bare first name with no greeting is not covered. On n8n Cloud the Gmail trigger has already stored the raw email in the execution unless saving executions is turned off. There is no retention policy. No secrets are in the repo. |
| 7 | Cost and latency | Pass for the estimate | Cost is computed from `config/costs.json` dated 2026-11-03: €24 a month for n8n Cloud Starter billed monthly, and $0.0212 for Claude Haiku 5.5 at 80 short inquiries. The mock audit of the three weeks finishes in well under a second. Live latency is not measured. |
| 8 | Honest claims | Pass | The page says the person is fictional, the figures are mock-mode, and the n8n file was not run. Live Claude is "not run". |

## Fix list

**Done in this build:** the stress rows above, the draft no longer sitting behind the sheet node (a sheet response would have wiped the reply), and the send node reading the mapped fields by name.

**Left open, and not a code defect to paper over:**

- One real week from a person who did not write the extractor.
- Import the workflow into n8n and run it once on a test mailbox, with sending left disabled.
- A live Claude run on the same 32 inquiries, reported next to the mock numbers.
- Decide whether n8n execution data is saved, and for how long.
