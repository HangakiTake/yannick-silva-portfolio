# Test report — incoming request drafts

Run: 3 Nov 2026, Python 3.12.3, pydantic 2.14.2, fastapi 0.162.0, openpyxl 3.1.5, pytest 9.2.0.
Command: `python -m pytest -q tests` → **24 passed, 0 failed**. One warning, from the installed Starlette TestClient (`httpx` vs `httpx2`). It does not fail a test.
This machine has no Python 3.11, so the GitHub Action (which asks for 3.11) was not executed here. `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` were unset. Live mode: **not run**.

The labelled set is 47 synthetic messages (19 email files, 12 JSON exports, 16 web-form rows). 29 are marked messy in `gold/labels.json` (threads, signatures, HTML-only, French, Portuguese, Spanish, empty, spam, a legal threat, a payment dispute). The labels were committed before the extractor.

| Check | What was measured | Result |
|---|---|---|
| Request type vs gold | 47 / 47 | 100%. Misses: none |
| Fields vs gold | customer name, email, phone, dates, amounts: 235 / 235 | 100%. Misses: none. Gold-empty fields left empty: 0 filled |
| Needs a person | 16 / 16 gold cases (complaint, legal, payment dispute, angry, empty, spam, unknown type, high urgency) | 100%. Low-confidence flags on the run: 5, matching the 5 gold low-confidence rows |
| Schema | 12 malformed model replies, each sent twice | 12 / 12 rejected, 0 accepted. A bad reply followed by a valid one was accepted on the retry |
| Draft fact check | all 47 drafts | 0 prices, dates or promises outside the request or `policy/tone_policy.json` |
| Never send | import scan of `src/` plus the suite's network block | no mail library, no send call. Draft JSON has `sent: false` |
| Idempotency | second run of the same 47 | 0 new rows, 0 new draft files, model call count unchanged |
| Load | 300 plain quote emails, mock mode, this machine | 0.431 seconds, then a second run still 300 drafts |
| Webhook | token missing, token wrong, valid quote, 200,001-character body, bad JSON | 401, 401, draft with the $129 policy price, 413, 422 |

Extra cases outside the 47, also in the suite: a short "FYI" wrapping the business's own $249 quote does not become a customer quote; `USD 150` is kept as `$150`; a curly apostrophe in "I'm Erin O'Brien" is read; a model summary that says "refund" is replaced from the grounded fields.

Prompt size on the 47 (system + user): 943–1,165 characters, median 1,059. Mock JSON: 343–437 characters, median 387. Used only for the cost estimate in `HANDOFF.md`.
