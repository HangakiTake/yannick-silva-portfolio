# Handoff

Linden Home Services is fictional. The workflow reads a request, writes a draft, and stops. A person sends the reply from their own mailbox.

## Run it here

```
pip install -r requirements.txt
PYTHONPATH=src python -m triage run --inbox samples --out out --policy policy/tone_policy.json
```

`out/review_log.csv` and `out/review_log.xlsx` have one row per request. `out/drafts/` holds the replies (`sent` is false). Running the same inbox again adds no rows and no drafts.

Edit `policy/tone_policy.json` to change the business name, hours, the three prices, the two sentences the draft is allowed to promise, and the signature. A price is quoted only when the customer asked for that service and the request is a quote. The file is the only price list.

## Zapier

1. Run this app where Zapier can reach it (`python -m triage serve`). Set `TRIAGE_POLICY` and `TRIAGE_WEBHOOK_TOKEN`. Without the token, `POST /triage` returns 401.
2. Zap: email trigger (Gmail or Outlook "new email"), then Webhooks by Zapier → POST.
3. URL `https://YOUR-HOST/triage`. Header `Authorization: Bearer YOUR-TOKEN`.
4. JSON body: `sender`, `subject`, `body`, `attachments` (list of file names). The response has `disposition: "draft"` and `sent: false`.
5. Next Zapier step: create a Gmail or Outlook **draft**, or a row in a Sheet. Do not use "send email".

Accounts: a Zapier account, and the mailbox Zapier already uses. No model key while `TRIAGE_LLM_MODE` stays `mock`.

Zapier prices read from https://zapier.com/pricing on 3 Nov 2026: Free includes 100 tasks/month. Professional at 750 tasks is $19.99/month billed annually, or $29.99 month to month. One webhook action per request is about one task, so 100 requests sit on the free allowance and 1,000 do not fit the 750-task tier. The next tier's price was not copied here; check that page before buying. Triggers were treated as not counting. Recount the steps in the real Zap.

## Power Automate

1. Same app and the same token.
2. Flow: "When a new email arrives", then HTTP (POST) to `/triage` with the bearer token, then "Create a draft" in Outlook. Do not use "Send an email".
3. The HTTP action to your own URL is a premium connector, so a Microsoft 365-only flow is not enough.

Microsoft's pricing page on 3 Nov 2026 (https://www.microsoft.com/en-us/power-platform/products/power-automate/pricing) showed Power Automate Process at $150 per bot per month, paid yearly, and Hosted Process at $215. The Premium per-user price was not in the page text that could be read. Confirm it at checkout.

## Model cost, if you turn live mode on

Mock mode is the default and costs nothing. Live mode: `TRIAGE_LLM_MODE=live` plus `OPENAI_API_KEY` (default model `gpt-4o-mini`) or `ANTHROPIC_API_KEY` (default `claude-haiku-5-5`). `pip install -r requirements-live.txt`. One call per new request. A repeat of the same inbox does not call again.

On the 47 sample messages the prompt (system + user) was 943 to 1,165 characters, median 1,059. The mock JSON reply was 343 to 437 characters, median 387. Dividing by 4 gives a rough token count, not a vendor tokenizer: about 265 input tokens and 97 output tokens at the median. Live mode was not run, so this is not a bill.

Prices read on 3 Nov 2026:

| | Input / 1M | Output / 1M | About 100 requests | About 1,000 |
|---|---|---|---|---|
| gpt-4o-mini | $0.15 | $0.60 | $0.0098 | $0.098 |
| Claude Haiku 5.5 (prompt under 100k tokens) | $0.10 | $0.50 | $0.0075 | $0.075 |

Sources: https://developers.openai.com/api/docs/pricing and https://platform.claude.com/docs/en/about-claude/pricing. The arithmetic is `100 * (265/1e6*input_price + 97/1e6*output_price)`. A real bill moves with the tokenizer, the prompt, and any price change. Hosting the small app was not priced.

## Before real customer mail

- Put the token only in the host's environment, not in the repo.
- Keep the app off the public internet, or put it behind the token and a body-size limit (the app rejects bodies over 200,000 characters).
- Drafts and the review log contain the customer's name and address. Decide who can open `out/` and how long you keep it. That decision is not built in.
- Read `policy/tone_policy.json` with the owner before go-live. The draft will not promise a refund, a same-day visit, or a price that is not in that file.
