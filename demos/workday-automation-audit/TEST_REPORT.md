# Test report — workday automation audit

Run: 2026-11-03, Python 3.12.3 locally (CI uses 3.11). pandas and pydantic installed from `requirements.txt`.

Command: `python -m pytest -q tests` → **25 passed, 0 failed** (0.34 s).

`ANTHROPIC_API_KEY` was not set. Every model figure below is the deterministic mock.

| Check | Measured | Threshold | Result |
|---|---|---|---|
| Weeks and mentions | 3 week notes, 53 mentions, 23 marked messy, 30 distinct tasks | ≥3 weeks, ≥45 mentions, ≥15 messy, ≥30 tasks for the tool check | pass |
| Tasks found | 48/48 labelled task mentions matched an extracted task | ≥90% | pass (100%) |
| Frequency and minutes | 48/48 of those inside the hand-labelled range | ≥90% of found | pass (100%) |
| Questions, no silent drops | 5/5 labelled unclear lines are on the questions list and were not turned into tasks. 0 labelled mentions missing from both lists | 100% of the rest, 0 silent drops | pass |
| Redaction | 65/65 planted items removed (16 names, 15 emails, 12 phones, 12 amounts, 10 addresses). Restore equals the original text | ≥98% | pass (100%) |
| Nothing leaked to the model | 0 emails and 0 phone numbers in the mock payloads for the 65-item corpus and for the 32 inquiries | 0 | pass |
| Tool pick | 30/30 match the hand labels. No misses to explain | ≥80% | pass (100%) |
| Scoring | Two runs, same order. Top task `inquiry_replies` (n8n, score 65.01389). The config example swaps order when the effort weight goes from 1 to 5 | identical ranking; documented reorder | pass |
| n8n JSON | 11 nodes. Every connection names a node that exists. Credential objects are name plus an empty id. `Send reply` is disabled and is downstream of `Human approval`. The draft and the send node read `$('Map fields')`, so the sheet step cannot wipe the body | parses, connections, no secrets, approval before send | pass. Not imported into a live n8n |
| Runner | 32/32 inquiries saved as drafts awaiting approval, 0 sent. 32/32 category, urgency, and service match the labels. 8 extra paraphrases in `tests/test_stress.py` also match, 0 sent | 100% drafts, 0 sent, ≥95% fields | pass (100% of 32) |
| Guide | HTML and Markdown list all 11 nodes, the prompt location (`config/prompts.json` and the Claude node), how approval is on, and the cost dated 2026-11-03: €24 n8n Cloud Starter billed monthly (€20 if billed annually) and $0.0212 Claude Haiku 5.5. Currencies are not added together | each node, prompt, cost with assumptions | pass |
| Live Claude | not run | report accuracy or "not run" | not run |

Hand labels are in `data/labels.json`. They were written from the week notes and the decision rules, and the tests read them as the answer key.

Repeat rate used for the ranges: 52/12 weeks per month. Weekday daily = 5 × 52/12 ≈ 21.67. Weekly = 52/12 ≈ 4.33. A couple of times a week = 8.67. A few or several times a week = 13. Twice a month = 2. Yearly = 1/12 ≈ 0.083.

Not tested: a live n8n import, a live Gmail or Google Sheets account, and a live Claude call.
