# Incoming request drafts

A small fictional home-services company, Linden Home Services, gets quote, booking, billing and complaint messages. This reads a sample inbox, pulls the request into fields, and saves a reply for a person to check.

Nothing is sent. Mock mode needs no API key.

```
cd demos/ai-request-triage-drafts
pip install -r requirements.txt
PYTHONPATH=src python -m triage run --inbox samples --out out --policy policy/tone_policy.json
PYTHONPATH=src python -m pytest -q tests
```

`--redact` hides names, emails and phones in the review log and in `out/state.json`. The draft files keep the name, because a person still has to answer.

The HTTP endpoint, for Zapier or Power Automate, refuses work until `TRIAGE_WEBHOOK_TOKEN` is set. See `HANDOFF.md`.

```
TRIAGE_POLICY=policy/tone_policy.json TRIAGE_WEBHOOK_TOKEN=choose-a-long-token \
  PYTHONPATH=src python -m triage serve
```

Live mode is off unless you set `TRIAGE_LLM_MODE=live` and either `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`. A key on its own does not call a vendor. Install `requirements-live.txt` first. This environment had neither key, so live mode was not run.

Synthetic data only. Names and addresses use example.com, example.net, example.org or example.fr.
