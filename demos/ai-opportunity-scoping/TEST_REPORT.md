# Test report — AI opportunity scoping

Run: 2026-11-03. Python 3.12.3, pandas 3.1.0, pydantic 2.14.2, FastAPI 0.162.0, openai Python package 3.42.1 (imported by the live-mode module, not called). Node.js 22.23.4, openai npm package 4.104.0 (imported by the client test, not called).

No `OPENAI_API_KEY` was set. Live mode: **not run**.

Commands:

- `python3 -m pytest -q` → **17 passed, 0 failed**
- `cd node && npm test` → **3 passed, 0 failed**

| Check | Measured | Threshold | Result |
| --- | --- | --- | --- |
| Inventory rows accounted for | 44 seen, 30 scored, 14 exceptions, 0 in both lists, 0 missing | 100% parsed or excepted, 0 silent drops, at least 40 rows | pass |
| Deliberately messy rows in that inventory | 20 | at least 10 | pass |
| Unit normalisation vs hand labels | 77 of 77 parseable values | at least 95% | pass (100%) |
| Same input, same ranking | two runs, identical nets and order | identical | pass |
| Weight change | HighHours net 55.0833 above HighError 30.7500 at the default weights; after `w_hours` 0.20 and `w_error` 0.80, HighError 75.7500 is above HighHours 18.4167. Effort-weight example: nets 65.0000 and 57.5000 flip to 69.0000 and 75.5000 when `w_effort` goes from 0.25 to 0.05 | ranking moves as `docs/scoring.md` describes | pass |
| Architecture vs hand labels | 29 of 30 (96.7%) | at least 80%, every miss explained | pass |
| Mock agent conversations | 36 of 36 right tool and valid arguments | at least 30 conversations, at least 95% | pass (100%) |
| Out-of-policy refunds | 13 of 13 escalated, 0 `issue_refund` calls, 0 refund rows created | 100% escalated, 0 executed | pass |
| Forced over-cap refund, bypassing the planner | `issue_refund` of $120 on PBL-1002 returns `not_executed`. $75 on the same order is created. A second refund then returns `not_executed`. Refund count stays 1 | not executed | pass |
| Malformed tool arguments | 28 of 28 rejected, with the field name in the error, 0 HTTP calls | 100% rejected | pass |
| Node client | lookup PBL-1001, in-policy refund of PBL-1001, $120 refund of PBL-1002 not created, bad `order_id` rejected before `fetch` | test passes | pass |
| Decision note | Markdown and HTML include the shortlist, architecture, integration plan, cost and risk table, and phases 1–4 | all of those sections | pass |
| Support-queue cost | $12.7500 per month | 5000 × (7000 × $0.25 + 400 × $2.00) / 1,000,000 | pass |
| Live OpenAI mode | not run | report "not run" when no key | pass |

## The one architecture miss

Hand label for "Tag blog posts from past tags": `classic_ml`, because two years of tags are a labelled set.

The rubric returns `dont_automate`. It does not treat the word "tagged" as a history signal, and 20 posts a month is under the 200 cutoff, so the fallback is "don't automate".

That row was not relabelled. It is in the decision note under "Where the hand labels differ". The other 29 labels match the rubric, including "Billing email triage and correction", where the word "classify" would have suggested a classic model but the reply-and-lookup phrase wins and the label is `llm_agent`.

## What the 17 Python tests are

1. `test_unit_gold_meets_95_percent`
2. `test_inventory_accounts_for_every_row` (xlsx and csv)
3. `test_missing_header_fails_loudly`
4. `test_scoring_is_reproducible_and_weights_flip`
5. `test_architecture_matches_hand_labels`
6. `test_refund_policy_boundaries` (14-day, 15-day, 30-day and 31-day edges included)
7. `test_agent_scripted_conversations`
8. `test_malformed_tool_args_are_rejected`
9. `test_out_of_policy_refund_is_not_executed`
10. `test_tool_schema_matches_models`
11. `test_decision_doc_has_the_required_sections`
12. `test_support_queue_cost_is_the_published_arithmetic`
13. `test_live_mode_is_not_called_without_a_key`
14. `test_repo_has_no_secrets_or_employer_name`
15. `test_semicolon_and_latin1_and_blank_line`
16. `test_same_name_different_team_is_kept_and_duration_is_not_a_count`
17. `test_alias_headers`

## Top of the ranking on this run

1. Customer support queue, `llm_agent`, net 73.7500, estimated OpenAI cost $12.7500 a month.
2. Billing email triage and correction, `llm_agent`, net 70.2500, $15.3000.
3. Reconcile Stripe payouts to the bank, `rules`, net 67.2500, $0.

The prototype is item 1.

## Not measured

Live tool choice with a real model. The code path is `src/live.py`. It refuses to run without `OPENAI_API_KEY`, and that is what the test checks. The installed SDK still has `chat.completions.create` with `tools` and `temperature`. No request was sent.
