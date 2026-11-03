# Workday automation audit

A portfolio demo on synthetic data. One fictional solo bookkeeper describes a week. The kit suggests what to automate, keeps the notes private, and hands back an n8n workflow plus a short guide. It is not a company-wide process inventory.

## Requirements

| ID | Requirement |
|---|---|
| R01 | From a person's description of their day, suggest what can be automated, with reasons |
| R02 | A working, importable automation for the top pick, plus a plain guide |
| R03 | Redaction before any model call, local placeholder map, redaction report |
| R04 | n8n or Make for app steps, Claude for text, a spreadsheet when that is enough, each with a reason |
| R05 | Messy input (ranges, approximations, typos, duplicates). Unparseable lines go to the questions list. Nothing labelled is dropped |
| R06 | Scoring formula documented, weights in config, every score traceable to the extracted fields |
| R07 | Human approval on anything a customer would receive. The runner never sends |
| R08 | Cost from a dated config |
| R09 | Mock mode by default. Live Claude only if ANTHROPIC_API_KEY is set |
| R10 | No secrets. Synthetic data only |

## Pass thresholds

| Check | Threshold |
|---|---|
| Task extraction, at least 3 weeks, at least 45 mentions, at least 15 messy, against hand labels | At least 90% of tasks found. Frequency and minutes inside the labelled range for at least 90% of those. The rest on the questions list. No silent drops |
| Redaction, at least 60 planted items | At least 98% removed. No email or phone left in the model payload. The map restores the text exactly |
| Tool pick, at least 30 tasks | At least 80% match the hand labels. Every miss explained |
| Scoring | Same input, same order. Changing a weight changes the order as the config example says |
| n8n JSON | Parses. Every connection names a real node. No credential values. Approval before any send node |
| Runner, at least 30 fake inquiries | 100% end as drafts awaiting approval, none sent. At least 95% category and fields match the labels |
| Guide | Generated. Covers each node, where to edit the prompt, and the monthly cost with its assumptions |
| Live mode | If a key is present, report accuracy on the same inquiries. If not, say it was not run |

## Stack

Python 3.11, pandas, Pydantic, an n8n workflow JSON file, the Anthropic SDK behind a deterministic mock, regex redaction, Jinja2, pytest. Mock mode needs no accounts.
