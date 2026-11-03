# AI opportunity scoping

This reads a messy process inventory for **Pebblecart**, a fictional home-goods shop, scores each process for payoff against effort, recommends an architecture, and writes a short decision note. The top recommendation is the support queue. The prototype is a function-calling support agent: look up an order, check the refund policy, issue a refund only when the policy allows it, or hand the case to a person.

Nothing here is a real company. No OpenAI key is required.

```
pip install -r requirements.txt
python -m src.run_demo          # writes out/decision.md and out/decision.html
python -m pytest -q             # 17 tests, mock mode
cd node && npm ci && npm test   # the TypeScript client against the fake API
```

Python 3.11 or newer. The numbers in `TEST_REPORT.md` were measured with Python 3.12.3. GitHub Actions runs the same tests on Python 3.11.

## What you get

- A ranked list, with every term of the score written down in `docs/scoring.md`. Weights are in `config/scoring.json`.
- One architecture per process: rules (no model), a function-calling agent, retrieval over the company's own documents, a classic model, or "don't automate". The rules are `docs/architecture_rubric.md`.
- A monthly OpenAI estimate from `config/openai_prices.json` (prices checked 2026-11-03). Rules and classic models are $0 in that estimate. Classic-model training cost is not included.
- `out/decision.md` and `out/decision.html`: the shortlist, the architecture, the systems to connect, the cost and risk table, and a phased build.
- The support agent in Python (`src/agent.py`) and a thin TypeScript client (`node/src/client.ts`). Both use `shared/tools.schema.json`. The fake shop API is FastAPI (`src/api.py`).

## Mock mode and live mode

Mock mode is the default. A deterministic planner chooses the tool. It is not a language model. It is there so the tool schema, the argument checks, the refund gate and the tests run with no key.

Live mode runs only when `OPENAI_API_KEY` is set (`src/live.py`, model `gpt-5-mini` from the price file). It was not run for the numbers in the test report.

## Refund gate

The agent can call `issue_refund`. The API runs the policy again and returns 409, without creating a refund, when the order is outside the window, the item is final-sale or digital, the amount is over the $75 cap, or the amount is over what the customer paid. The planner is supposed to escalate those cases itself. The API is the backstop. The demo clock is frozen on 2026-11-03 so the sample orders stay inside the windows. A real shop would use today's date.

## Limits

- The inventory and the orders are synthetic.
- The 29-of-30 architecture score is against labels written from the rubric in this repo, not against a second person's labels. The miss (blog tags) is kept on purpose and explained in the decision note.
- A blank error rate is scored as 0 and the decision note says so.
- The Node client plans the same kind of call in mock mode. It does not write the Python tool log. The Python agent does, and that log does not store the customer email.
- The fake API has no login. It is a local demo.
