# Ponytail review, 2026-11-03

Read for: correct, safe, tested, lean. Scope is the scoping kit, the fake API, the Python agent, the Node client, and the decision note.

## Must fix

None.

## Should fix

None. Checked after the fixes below:

1. A failed order lookup used to escalate as "order not found". It now stops and changes nothing, in Python and in the Node client.
2. The judgment word "write" inflated the effort of "write the quantity" on a checklist. Removed from the rubric. Architecture for that row stays `rules`.
3. A blank error rate was a silent zero on the decision note. The note now says the zero is a stand-in.
4. The security-questionnaire row (net -4.1500) is no longer listed as phase-3 work. It waits.
5. The in-process HTTP client matches the installed httpx. The async-only ASGI transport was not used. Tests call FastAPI's test client. The Node test starts uvicorn.
6. Out-of-policy refunds are refused in the planner and again in the API. A direct `issue_refund` of $120 does not create a row. 13 of 13 scripted cases escalate. 28 of 28 bad arguments are rejected before any HTTP call.
7. Prices and token counts live in `config/openai_prices.json`. The $12.75 support figure is asserted from that arithmetic.
8. 17 Python tests and 3 Node tests passed on 2026-11-03. Live mode was not called.

## Nice to have (left open)

1. The tool log is append-only. A real deployment needs a retention rule.
2. The Node mock planner is a second copy of the Python one. The tool schema is shared. The planner is not, on purpose, so the Node example is a real client and not a shell around Python.
3. `src/live.py` matches the installed SDK (`chat.completions.create` still takes `tools` and `temperature`, openai 3.42.1) and was not executed.

## Verdict

**Ready as a portfolio demo.** The refund gate holds without a model. Nothing here has been run against a live OpenAI account.
