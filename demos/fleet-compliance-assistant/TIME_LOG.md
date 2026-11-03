# Time log

All times are Europe/Zurich, 2026-10-28. The times come from the build box clock: start was recorded when work began, and finish when the final report was written.

| | Estimate (PLAN_AND_SPECS.md §5) | Actual |
|---|---|---|
| Total | 8–10 h (written as hours for a person) | **about 16 min of agent wall-clock time, 14:26 to about 14:42** |

## Why these numbers can't be compared directly

- The estimate assumed a person building in the n8n UI, step by step. This build was done by an AI agent working in code, with n8n running locally. The actual time is machine time, not a person's hours, so it is **not evidence that a person could do this in 16 minutes**.
- What isn't counted: Yannick's own time to review and test the demo (allow 30–45 min, see the report), and the go-live work that needs real accounts (API registration waits of up to 5 working days for DVSA, and DVLA registration is currently closed).
- What ran over or changed against the plan: the n8n delivery-logging design was reworked three times (a single Execute Command runs once per execution; the Email node puts failures on its success output; paired-item data is lost on error items). The stress test and the code reviews found five more real bugs, all fixed and re-tested.

## Lesson for future estimates

For agent-built demos, quote the client in **human** hours for the real build, which is the original 8–10 h, plus go-live time per account. Track agent wall-clock time separately, as a check on how hard the demo was to make, not as a price.
