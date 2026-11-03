# Pebblecart — where AI is worth it

Synthetic company. Generated 2026-11-03. This is a decision note, not a live bill and not a production system.

## Ranked shortlist

Processes we would actually build, highest net score first. "Don't automate" rows are listed later and are not in this shortlist.

| Rank | Process | Team | Hours / month | Payoff | Effort | Net | Architecture | OpenAI USD / month |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Customer support queue: order status, refunds and tickets | Support | 666.6667 | 94.0000 | 81.0000 | 73.7500 | llm_agent | 12.7500 |
| 2 | Billing email triage and correction | Finance | 7500.0000 | 88.0000 | 71.0000 | 70.2500 | llm_agent | 15.3000 |
| 3 | Reconcile Stripe payouts to the bank | Finance | 1800.0000 | 76.0000 | 35.0000 | 67.2500 | rules | 0.0000 |
| 4 | Weekend warehouse cycle count | Warehouse | 1825.0001 | 70.0000 | 25.0000 | 63.7500 | rules | 0.0000 |
| 5 | Churn risk score for Plus subscribers | Product | 266.6667 | 76.6667 | 53.0000 | 63.4167 | classic_ml | 0.0000 |
| 6 | Answer product questions from the help center | Support | 291.6667 | 78.0417 | 71.0000 | 60.2917 | rag | 5.6650 |
| 7 | Warehouse pick confirmation | Warehouse | 300.0000 | 56.1000 | 25.0000 | 49.8500 | rules | 0.0000 |
| 8 | SKU demand forecast | Warehouse | 133.3333 | 53.3333 | 43.0000 | 42.5833 | classic_ml | 0.0000 |


30 processes were scored. 14 inventory rows were exceptions and were not scored. None were dropped.


- Weekend warehouse cycle count: Error rate was blank and was counted as 0 for the score.


## Recommended architecture


### Customer support queue: order status, refunds and tickets

- Architecture: **llm_agent** (rule `action`)
- Why: The work includes a customer reply or a record change (look up the order).
- Systems: Shopify, Helpdesk, Policy PDF
- Human in the loop: A person handles anything the policy or the tool check refuses.
- Main risk: The model can pick the wrong tool or invent a fact. Arguments are checked, and a refund the policy does not allow is not executed. A person takes the escalation. Order text would be sent to OpenAI.

### Billing email triage and correction

- Architecture: **llm_agent** (rule `action`)
- Why: The work includes a customer reply or a record change (reply to the customer).
- Systems: NetSuite, Helpdesk
- Human in the loop: A person handles anything the policy or the tool check refuses.
- Main risk: The model can pick the wrong tool or invent a fact. Arguments are checked, and a refund the policy does not allow is not executed. A person takes the escalation. Order text would be sent to OpenAI.

### Reconcile Stripe payouts to the bank

- Architecture: **rules** (rule `rules`)
- Why: The steps are fixed (tie to the cent). A workflow can do this without a model.
- Systems: Stripe, Bank CSV
- Human in the loop: A person handles the cases the rules do not cover.
- Main risk: A case that was never written down falls through to a person. Rules do not invent facts. Someone has to own that queue.

### Weekend warehouse cycle count

- Architecture: **rules** (rule `rules`)
- Why: The steps are fixed (always the same). A workflow can do this without a model.
- Systems: WMS
- Human in the loop: A person handles the cases the rules do not cover.
- Main risk: A case that was never written down falls through to a person. Rules do not invent facts. Someone has to own that queue.

### Churn risk score for Plus subscribers

- Architecture: **classic_ml** (rule `ml`)
- Why: This is a score or a class (predict), and there is history to learn from.
- Systems: Warehouse, Stripe
- Human in the loop: A person reviews the scores for the first month.
- Main risk: Bad labels teach the wrong score, and scores drift. A person should review the first month. This is not a refund bot.

### Answer product questions from the help center

- Architecture: **rag** (rule `rag`)
- Why: The answer is already in a document (help center). Retrieve it, and let a person send it.
- Systems: Help center, Policy PDFs
- Human in the loop: A person reviews the answer before it is sent out.
- Main risk: The right passage can be missing or out of date. A person should review anything that is sent out. The documents would be sent to the API.

### Warehouse pick confirmation

- Architecture: **rules** (rule `rules`)
- Why: The steps are fixed (always the same). A workflow can do this without a model.
- Systems: WMS
- Human in the loop: A person handles the cases the rules do not cover.
- Main risk: A case that was never written down falls through to a person. Rules do not invent facts. Someone has to own that queue.

### SKU demand forecast

- Architecture: **classic_ml** (rule `ml`)
- Why: This is a score or a class (forecast), and there is history to learn from.
- Systems: Shopify
- Human in the loop: A person reviews the scores for the first month.
- Main risk: Bad labels teach the wrong score, and scores drift. A person should review the first month. This is not a refund bot.


## Integration plan

The first build talks to the shop's order API (lookup, refund policy, refund, ticket, escalation). The other systems below are named in the inventory. They are not connected in this demo.


- **Customer support queue: order status, refunds and tickets** (llm_agent): Shopify, Helpdesk, Policy PDF

- **Billing email triage and correction** (llm_agent): NetSuite, Helpdesk

- **Reconcile Stripe payouts to the bank** (rules): Stripe, Bank CSV

- **Weekend warehouse cycle count** (rules): WMS

- **Churn risk score for Plus subscribers** (classic_ml): Warehouse, Stripe

- **Answer product questions from the help center** (rag): Help center, Policy PDFs

- **Warehouse pick confirmation** (rules): WMS

- **SKU demand forecast** (classic_ml): Shopify


## Cost and risk

Prices are from `config/openai_prices.json`, checked 2026-11-03. Source: https://developers.openai.com/api/docs/pricing. Standard published prices. Cache discounts are not applied, so the figure is the full input price. gpt-4.1-mini is on the deprecation list (shutdown 2027-01-14), so the estimate uses gpt-5-mini. Checked 2026-11-03.

Model for agent and RAG calls: `gpt-5-mini` at $0.25 per million input tokens and $2.0 per million output tokens. Embedding `text-embedding-3-small` at $0.02 per million. Cache discounts are not applied.

Token assumptions per item: agent 7000 in / 400 out (Three tool rounds. Schemas and tool results are sent again each round. Cache not assumed.). RAG 5000 in / 500 out plus 800 embedding tokens (One question plus retrieved excerpts. The embedding line is the query only. Building the index is not in the monthly figure.). Rules, classic ML and "don't automate" are $0 in this table. Classic ML training cost is not included.

| Process | Architecture | OpenAI USD / month | Main risk | Human in the loop |
| --- | --- | --- | --- | --- |
| Customer support queue: order status, refunds and tickets | llm_agent | 12.7500 | The model can pick the wrong tool or invent a fact. Arguments are checked, and a refund the policy does not allow is not executed. A person takes the escalation. Order text would be sent to OpenAI. | A person handles anything the policy or the tool check refuses. |
| Billing email triage and correction | llm_agent | 15.3000 | The model can pick the wrong tool or invent a fact. Arguments are checked, and a refund the policy does not allow is not executed. A person takes the escalation. Order text would be sent to OpenAI. | A person handles anything the policy or the tool check refuses. |
| Reconcile Stripe payouts to the bank | rules | 0.0000 | A case that was never written down falls through to a person. Rules do not invent facts. Someone has to own that queue. | A person handles the cases the rules do not cover. |
| Weekend warehouse cycle count | rules | 0.0000 | A case that was never written down falls through to a person. Rules do not invent facts. Someone has to own that queue. | A person handles the cases the rules do not cover. |
| Churn risk score for Plus subscribers | classic_ml | 0.0000 | Bad labels teach the wrong score, and scores drift. A person should review the first month. This is not a refund bot. | A person reviews the scores for the first month. |
| Answer product questions from the help center | rag | 5.6650 | The right passage can be missing or out of date. A person should review anything that is sent out. The documents would be sent to the API. | A person reviews the answer before it is sent out. |
| Warehouse pick confirmation | rules | 0.0000 | A case that was never written down falls through to a person. Rules do not invent facts. Someone has to own that queue. | A person handles the cases the rules do not cover. |
| SKU demand forecast | classic_ml | 0.0000 | Bad labels teach the wrong score, and scores drift. A person should review the first month. This is not a refund bot. | A person reviews the scores for the first month. |


## Phased plan

Phase 0. Clear the 14 exception rows with the team leads (ranges, formulas, missing names, duplicates) before anyone trusts the ranking.

Phase 1. Workflow automation, no model, for the fixed procedures: Reconcile Stripe payouts to the bank; Weekend warehouse cycle count; Warehouse pick confirmation; Three-way match of PO, receipt and invoice; Checkout address validation; Merge duplicate customer records; Return shipping label; Failed-card dunning ladder; 

Phase 2. First AI build: the support agent (Customer support queue: order status, refunds and tickets, net 73.7500). It looks up an order, checks the refund policy, issues a refund only inside the cap, and escalates everything else. The prototype in this repo is that agent, against a fake API, with a mock mode that needs no key.

Phase 3. Retrieval over the documents already named, for: Answer product questions from the help center; Barcode exception SOP lookup; Find the liability clause in a contract; Expense policy questions; New-hire contract questions; 

Phase 4. Classic models only where the history already exists, and only after a person checks the first month: Churn risk score for Plus subscribers; SKU demand forecast; Inbound demo lead scoring; Ticket topic classifier; 


Scored at or below zero, so not in the first build: Security questionnaire first draft (rag, net -4.1500); 


## Leave with the team


- Tag blog posts from past tags: The steps are not clear enough to automate. Leave it with the team until they are written down.

- Monthly close commentary for the board pack: The notes say this stays with a person (board pack).

- Campaign creative brief: The notes say this stays with a person (one-off).

- Settlement negotiation: The notes say this stays with a person (negotiat).

- Weekly social captions: The notes say this stays with a person (brand creative).

- Final salary offer: The notes say this stays with a person (keep human).


## Where the hand labels differ



- **Tag blog posts from past tags**: hand label `classic_ml`, rubric says `dont_automate`. A person sees two years of tags as a labelled set, so the honest label is classic ML. The rubric never treats the word tagged as a history phrase, and 20 posts a month is under the 200 cutoff, so step 11 says don't automate. Left as a known miss rather than relabelled.



## Assumptions

- Scoring weights and caps are in `config/scoring.json`. The formula is `docs/scoring.md`.
- The demo refund clock is frozen on 2026-11-03 so the sample orders stay inside the windows.
- Live OpenAI calls are off unless `OPENAI_API_KEY` is set. The figures above are estimates, not an invoice.
- Customer records in the demo are invented. Emails are example.com.

## Exceptions

| Sheet row | Reasons | Process cell |
| --- | --- | --- |
| 34 | duplicate | Customer support queue: order status, refunds and tickets |
| 35 | duplicate |   customer   support queue: order status, refunds and tickets  |
| 36 | missing_process |  |
| 37 | bad_volume | Ad hoc partner gifts |
| 38 | bad_volume | Exec inbox zero |
| 39 | bad_minutes | Press replies |
| 40 | bad_error | Card testing reviews |
| 41 | bad_volume | Formula leak |
| 42 | blank_row |  |
| 43 | bad_volume | Mystery queue |
| 44 | bad_minutes | Negative time |
| 45 | bad_volume | Pop-up stock check |
| 46 | missing_process |  |
| 47 | bad_volume, bad_minutes | — end of list — |
