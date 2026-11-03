# Architecture rubric

Hand labels in `data/gold_architecture.json` were assigned from this rubric on 2026-11-03, before `src/recommend.py` existed. The recommender implements this page. One label disagrees on purpose: the blog-tag row. The reason is in the gold file and in TEST_REPORT.

Patterns:

- `rules` — the steps are the same every time. No model.
- `llm_agent` — someone writes in, and the reply depends on looking up or changing a record through tools.
- `rag` — the answer is a passage in a document the company already has. A person still sends it.
- `classic_ml` — the job is a score or a class, and there is history to learn from. Not a chatbot.
- `dont_automate` — a person should keep it.

## How a row is read

Text is the process name plus the notes, lowercased. These negations are removed before judgment words and agent words are searched, so "no customer" is not read as a customer and "no judgment" is not read as judgment. The original text is still used for the don't-automate list, the rules list, and the RAG list, because those lists include the negations on purpose ("no judgment", "do not automate").

Scrub list: `no customer`, `not a customer`, `no reply`, `no judgment`, `no judgement`, `no language`.

A phrase matches when it occurs in the text. A stem such as `negotiat` matches negotiate and negotiation. Matching does not care what letter follows the phrase, but a letter must not sit immediately before it.

## Order, first match wins

1. **Don't automate** if the original text has any don't-phrase below.
2. **Agent** if the original text has an action phrase below (a real reply or a record change). This beats the ML rule, so "classify the email and reply to the customer" stays an agent.
3. **Don't automate** if monthly hours are under 5 and monthly volume is under 30. The work is too small to wire up.
4. **Classic ML** if the original text has an ML phrase, and either the volume is at least 200 or the text has a history phrase (`labelled`, `labeled`, `historical labels`, `win/loss`). Skip this step when step 2 already matched.
5. **Rules** if the original text has a rules phrase.
6. **RAG** if the original text has a RAG phrase.
7. **Agent** if the scrubbed text has a channel word (`customer`, `in chat`, `reply`, `transcript`) and a tool word (`look up`, `refund`, `pause`, `ticket`, `crm`).
8. **RAG** again if a RAG phrase is present (already covered by step 6; kept so the fallback story is in one place).
9. **Agent** if the scrubbed text still has a channel word.
10. **Rules** if volume is at least 100 and minutes per item are 5 or less (short, repeated, and nobody described a judgment).
11. **Don't automate.** The steps are not written down clearly enough.

## Phrase lists

A test reads this fence. One phrase per line. Do not reword a line without re-reading the gold labels.

```phrases
dont: board pack
dont: keep human
dont: one-off
dont: executive
dont: salary
dont: negotiat
dont: brand creative
dont: legal advice
dont: do not automate
action: reply to the customer
action: look up the invoice
action: look up the order
action: look up the subscription
action: issue the refund
action: update the crm
ml: predict
ml: forecast
ml: propensity
ml: churn
ml: lead scor
ml: fraud
ml: anomaly
ml: classify
ml: classification
ml: labelled
ml: labeled
ml: win/loss
ml: historical labels
rules: deterministic
rules: always the same
rules: checklist
rules: fixed ladder
rules: no judgment
rules: no judgement
rules: no language
rules: tie to the cent
rules: standardise
rules: standardize
rules: exact email match
rules: three-way
rules: match the
rules: validate
rag: policy pdf
rag: handbook
rag: sop
rag: wiki
rag: help center
rag: help centre
rag: contract
rag: quote the
rag: pdf
scrub: no customer
scrub: not a customer
scrub: no reply
scrub: no judgment
scrub: no judgement
scrub: no language
channel: customer
channel: in chat
channel: reply
channel: transcript
toolword: look up
toolword: refund
toolword: pause
toolword: ticket
toolword: crm
judgment: customer
judgment: in chat
judgment: judgment
judgment: judgement
judgment: tone
judgment: draft
judgment: negotiat
judgment: creative
judgment: reply
judgment: question
judgment: transcript
structured: deterministic
structured: always the same
structured: checklist
structured: fixed ladder
structured: no judgment
structured: no judgement
structured: no language
structured: tie to the cent
structured: exact email match
structured: validate
```

## Known disagreement

"Tag blog posts from past tags" is labelled `classic_ml` because two years of tags are a labelled set. The rubric does not treat "tagged" as a history phrase, and the volume is 20, which is under 200. Step 11 says don't automate. That miss is recorded in the gold file. It is not relabelled to hide it.

## Risks, told with the recommendation

- rules: a case that was never written down falls through. Someone owns that queue. No model, no hallucination.
- llm_agent: the model can pick the wrong tool. Arguments are checked, and a refund the policy does not allow is not executed. A person takes the escalation. Order text would be sent to OpenAI.
- rag: the passage can be missing or out of date. A person reviews anything that is sent out. The documents would be sent to the API.
- classic_ml: bad labels teach the wrong score, and scores drift. A person reviews the first month. This pattern is not a refund bot.
- dont_automate: the hours stay with the team. That is the recommendation, not a blank cell.
