# Workday automation audit

A fictional solo bookkeeper, Mara Ellison, describes a normal week in plain text. This kit turns that into a ranked list of recurring tasks, picks a tool for each one, and builds an importable n8n workflow for the top task. Personal details are replaced with placeholders before any text is handed to a model. The Python runner saves drafts and never sends them.

This is one person's week. It is not a company process inventory.

## Run it

```bash
pip install -r requirements.txt
python -m pytest -q tests
python -m workday_audit audit data/weeks/week_a.txt --out out/week-a
python -m workday_audit inquiries data/inquiries.json --out out/inquiries
python -m workday_audit workflow --out n8n/inquiry-draft-reply.workflow.json
python -m workday_audit guide data/weeks/week_a.txt --out out/guide
```

No API key, no n8n account, and no mailbox. Mock mode is the default. Live Claude runs only if `ANTHROPIC_API_KEY` is set; otherwise that path reports `not_run`.

The three week notes together:

```bash
cat data/weeks/week_a.txt data/weeks/week_b.txt data/weeks/week_c.txt > /tmp/weeks.txt
python -m workday_audit audit /tmp/weeks.txt --out out
python -m workday_audit guide /tmp/weeks.txt --out out
```

## What it does

1. **Tasks.** Each clause with a repeat rate and a duration becomes a task. A clause that looks like work but is missing either one goes on the questions list. Repeating a sentence does not multiply the monthly hours.
2. **Redaction.** Emails, phone numbers, money amounts, street addresses, titled names, greetings, and two-word names are replaced from `config/redaction.json`. The placeholder map can restore the original text. The map is not written into the shortlist page.
3. **Tool.** First matching rule in `src/workday_audit/recommend.py` wins: don't automate (tax, sign-off, a judgment call, or who to phone), n8n (several steps or a customer-facing message), Make (two apps, nothing sent), Claude (reading or drafting text), or a spreadsheet formula. Customer-facing automations require approval.
4. **Score.** From `config/scoring.json`:

   `score = w_hours * (frequency_per_month * minutes_per_run / 60 * capture[tool]) - w_effort * effort - w_risk * risk`

   Default weights are hours 10, effort 1, risk 0.5. The same notes always rank the same way. The worked example in `config/scoring.json` shows a higher effort weight putting the low-effort task first.
5. **Top pick.** New inquiry emails: redact, Claude classifies and drafts, a row is added to a sheet, a Gmail draft is saved. A human approval step sits in front of a send node that ships disabled. The Python runner has no send method.

Repeat rates use 52/12 weeks per month. A weekday habit is 5 times a week. "A couple" is 2 and "a few" or "several" is 3. "Mon-Fri" counts as a weekday habit. "Not a weekly task" does not. "Every other Friday" is left as a question rather than guessed as weekly. "2 hrs" is 120 minutes. Two durations that are a factor of three or more apart ("10 minutes and 3 hours") are a question, not an average.

## Limits

- The person, the week notes, and the inbox are invented.
- Redaction is rules. A bare first name with no title and no greeting ("Sam called") is not removed. Two-word names, "Dear Sam", and "Dr Sam Cho" are.
- The n8n file was checked for structure only: it parses, every connection names a real node, credentials are names with empty ids, and the send node is disabled behind approval. It has not been imported into a running n8n.
- n8n's Gmail trigger has already received the raw email. Turn off saved executions if the inbox is sensitive, or run n8n on your own machine. Cloud Starter is priced below; self-hosting has no licence fee and you pay for the computer instead.
- Prices are dated assumptions in `config/costs.json` (checked 2026-11-03). Recheck them before spending money. Euros and dollars are not added into one total.
- Claude was not called. There is no API key in this repo. Category figures are the deterministic mock.

Synthetic data only.
