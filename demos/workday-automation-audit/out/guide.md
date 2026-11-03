# Run and change it yourself

Fictional solo bookkeeper. This guide is for the top-ranked task: **Draft replies to new inquiry emails** (inquiry_replies).

The workflow file is `n8n/inquiry-draft-reply.workflow.json`. Import it with the n8n menu: Workflows, Import from file. It arrives **inactive**, and the send node arrives **disabled**. The Python runner (`python -m workday_audit inquiries`) does the same job with a fake mailbox and never sends.

## What each node does


### 1. Run one email now

Start here while you are testing. Paste one email in the next node with the pin data, or use the Gmail trigger.

Type: `n8n-nodes-base.manualTrigger`.

### 2. New inquiry email

Fires when a new email arrives. The raw email is in this node's output. Turn off saving execution data if the inbox is sensitive.

Type: `n8n-nodes-base.gmailTrigger`.

### 3. Redact personal data

Replaces names, emails, phones, amounts and street addresses with placeholders before Claude sees the text. Same rules as config/redaction.json.

Type: `n8n-nodes-base.code`.

### 4. Claude classify and draft

Calls Claude with the redacted email and the system prompt. The API key lives in the n8n credential named 'Anthropic API' (header x-api-key). It is not in this file. Edit the prompt in the JSON body, or rebuild this file after editing config/prompts.json.

Type: `n8n-nodes-base.httpRequest`.

### 5. Map fields

Reads the JSON fields Claude returned: category, urgency, service, draft subject and draft body. Stops if the draft does not say it has not been sent. Later nodes read these fields by name, so a sheet response cannot wipe them.

Type: `n8n-nodes-base.code`.

### 6. Add lead row

Appends one row to the Leads tab: category, urgency, service, draft status, sent=false. Set LEADS_SHEET_ID in the n8n environment. Create those five column headers in row 1 before the first run.

Type: `n8n-nodes-base.googleSheets`.

### 7. Save draft reply

Saves a Gmail draft with the subject and body from Map fields. It does not send.

Type: `n8n-nodes-base.gmail`.

### 8. Human approval

Pauses until a person opens the approval link. Leave this node in the path. That is the approval switch, on.

Type: `n8n-nodes-base.wait`.

### 9. Approved?

True only when the approval link was confirmed. The false branch stops at 'Leave as draft'.

Type: `n8n-nodes-base.if`.

### 10. Leave as draft

Approval was not given. The draft stays in Gmail. Nothing is sent.

Type: `n8n-nodes-base.noOp`.

### 11. Send reply

Sends the reply. This node ships disabled. It is only reachable after Human approval and only on the true branch of Approved?. Enable it only after you have used the draft path for a while.

Type: `n8n-nodes-base.gmail`.


## Where to edit the prompt

Edit config/prompts.json key inquiry_system. The same text is copied into the n8n node 'Claude classify and draft' when the workflow file is rebuilt. In n8n, open that node and change the system text in the JSON body.

The prompt text in the workflow starts with: "You classify one redacted email for a solo bookkeeper and draft a reply that a h"

## Approval, on or off

**On (how it ships).** `Save draft reply` connects to `Human approval`, which connects to `Approved?`. Only the true branch reaches `Send reply`, and that node is disabled. Leave it this way. A customer-facing reply waits until a person opens the approval link.

**Off.** Do not do this until you have watched a week of drafts. To turn the gate off you would connect `Save draft reply` straight to `Send reply` and enable `Send reply`. The false branch `Leave as draft` would no longer be in the path. The Python runner still cannot send: it has no send method.

## What it costs per month

Figures dated **2026-11-03**. Euros and dollars are shown separately. They are not added together.

- n8n Cloud Starter, billed monthly: **€24**. Billed annually it is listed at €20 a month. 80 runs is inside the 2500 execution allowance.
- Claude claude-haiku-5-5: **$0.0212**. That is 80 inquiries × (900 input tokens × $0.1 + 350 output tokens × $0.5) / 1,000,000. The price is the short-prompt rate, for prompts under 100,000 tokens.
- Gmail and Google Sheets: $0 and $0 on top of the Google account you already pay for.

Assumption: 80 is about 4 new inquiry emails each weekday. 900 input tokens and 350 output tokens are one short email and one short draft, not a long thread. Recheck both against a real week before buying anything.


- n8n Cloud Starter (2026-11-03): https://n8n.io/pricing/ — The public pricing page lists Starter at 24 euros a month billed monthly, or 20 euros a month billed annually, including 2,500 workflow executions. Prices are in euros. Recheck on the day you subscribe.

- Claude Haiku 5.5 (2026-11-03): https://platform.claude.com/docs/en/about-claude/pricing — List price for prompts up to 100,000 tokens: 0.10 US dollars per million input tokens and 0.50 US dollars per million output tokens. A short inquiry is far under 100,000 tokens, so the higher long-prompt rate does not apply.


Self-hosting n8n has no licence fee. You would pay for the machine instead of the €24. A cloud n8n keeps execution data on n8n's side. The Gmail trigger has already received the raw email by then. If the inbox is sensitive, turn off saving execution data in n8n, or run n8n on your own machine. The placeholder map from the Python runner stays in the file you choose. Do not commit that file on a real job.

## What this does not do

It does not send the reply. It does not file the tax return. It does not decide which client to call. Those are on the shortlist as "don't automate", with the reason next to them.