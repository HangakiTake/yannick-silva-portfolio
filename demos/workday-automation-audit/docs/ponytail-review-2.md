# Ponytail review, round 2

Re-read after the round 1 fixes: extract, redact, recommend, score, runner, workflow builder, guide, and the tests.

## Must fix

None.

## Should fix

None. Checked specifically:

- `Send reply` is disabled, and `Human approval` is an ancestor. The sheet node is not an ancestor of the draft.
- Draft, sheet, and send read `$('Map fields')`.
- 25 tests pass, including the stress cases from round 1 and the JavaScript redactor against the same 65 items.
- Customer-facing tools set `requires_approval`. The runner's mailbox has no send method. A draft that does not say "not sent" is refused.
- The score stored on each row is the formula in `config/scoring.json` applied to that row's hours saved, effort, and risk.
- The rendered shortlist was showing `21.6666666665`. The page now prints the repeat rate to two decimals. The stored score is unchanged.
- The shortlist page does not contain the sample email or the sample phone. The placeholder map is not rendered there.
- No API key in the workflow JSON. Credential objects are a name and an empty id.

## Nice to have (left open)

- "Every other Friday" stays a question.
- A bare first name is not redacted.
- No live n8n import and no live Claude call.

Verdict: nothing further to change for this demo.
