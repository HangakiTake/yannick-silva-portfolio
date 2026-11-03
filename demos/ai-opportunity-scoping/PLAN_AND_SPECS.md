# ai-opportunity-scoping: plan and specs

Matches Upwork job 2117601578217120329, "OpenAI, AI Agents & Business Automation" (a tech company wants an advisor on AI agent development, OpenAI API integration, chatbots and business process automation: architecture, technology selection, API integrations, implementation strategy; "identify the best AI solutions for our business"). Portfolio build on synthetic data, not client work. Every number below is a target until measured.

## 1. What the demo is
An "AI opportunity scoping kit" that does what the proposal promises, end to end, on a fictional mid-size SaaS/e-commerce company:
1. **Process inventory in, ranked shortlist out.** Reads a messy process inventory (CSV/XLSX: process name, team, monthly volume, minutes per item, error rate, data sources, free-text notes) and scores each process for AI/automation payoff vs effort with a transparent, documented formula.
2. **Architecture recommender.** For each candidate, recommends one pattern with a written reason: plain rules/workflow automation (no LLM), LLM function-calling agent, retrieval (RAG) over own documents, classic ML, or "don't automate". Includes estimated monthly OpenAI running cost from token assumptions, and the main risks (data privacy, hallucination, human-in-the-loop need).
3. **Decision doc generator.** Writes a short Markdown/HTML decision document: ranked shortlist, recommended architecture per item, integration plan (which APIs/systems), cost and risk table, and a first-build plan.
4. **Working prototype of the top pick.** A small OpenAI function-calling agent (support/ops assistant: look up an order, check refund policy, open a ticket) against a fake REST API, with a deterministic offline mock LLM mode so tests and the demo run with no API key. Provide the agent in **Python** and a thin **Node.js/TypeScript** client example calling the same tool schema, to show it fits a JS/PHP/Node stack.

## 2. Requirements
JP = job post, PS = professional standard.
| ID | Src | Requirement |
|---|---|---|
| R01 | JP | Ranks business processes by AI/automation value with stated reasons (technology selection) |
| R02 | JP | Recommends an architecture per use case (agent, chatbot/RAG, workflow automation) with why |
| R03 | JP | Shows an OpenAI API integration: function calling with JSON-schema tools hitting a REST API |
| R04 | JP | Implementation strategy: phased build plan in the decision doc |
| R05 | JP | JS/Node example of the same integration (client prefers JS/PHP/React/Node) |
| R06 | PS | Scoring formula documented, weights configurable, every score traceable to input fields |
| R07 | PS | Messy input handled: missing values, mixed units ("2h", "90 min"), duplicate rows, free-text volumes ("~200/week"); rows it can't parse go to an exceptions list, never silently dropped |
| R08 | PS | Agent validates tool arguments, refuses out-of-policy actions (e.g. refund above limit → escalates to human), logs every tool call |
| R09 | PS | Cost estimate shows its token and price assumptions (config file, dated), not hard-coded magic numbers |
| R10 | PS | Runs fully offline in mock mode; real OpenAI mode only with OPENAI_API_KEY set |
| R11 | PS | No secrets in repo; synthetic data only; do not name a real employer |

## 3. Tests and pass thresholds
| Test | Pass threshold |
|---|---|
| Parser on messy inventory (≥40 rows incl. ≥10 deliberately messy) | 100% of rows either parsed correctly or listed as exceptions; 0 silent drops |
| Unit normalisation (time/volume) | ≥95% of messy-but-parseable values normalised correctly vs hand-labelled gold |
| Scoring reproducibility | Same input → identical ranking; changing a weight changes ranking as documented |
| Architecture recommender vs hand-labelled gold (≥25 processes, labelled before building) | ≥80% match on pattern; every mismatch explained in TEST_REPORT |
| Agent tool-calling, mock mode, ≥30 scripted conversations | ≥95% correct tool + valid args; 100% of out-of-policy requests escalated, 0 executed |
| Agent schema validation | 100% of malformed tool args rejected with a clear error |
| Node client example | Runs against the fake API in mock mode, test passes in CI |
| Decision doc | Generated for the sample company; contains shortlist, architecture, cost table, risks, phased plan |
| Optional live mode | If key available, ≥90% correct tool selection on the same 30 conversations; otherwise reported as "not run" (honest caveat) |

## 4. Stack and why
- **Python 3.11 + pandas**: robust messy-table parsing and scoring; Yannick's working language.
- **Pydantic**: tool argument and input validation.
- **OpenAI Python SDK (function calling / tools)**: the client named OpenAI API and AI agents; tools as JSON schema are portable to any language.
- **FastAPI**: the fake company REST API the agent calls (orders, policy, tickets), mirrors a real integration.
- **Node.js (TypeScript, openai npm package)**: thin client proving the same tool schema works in the client's JS/Node stack.
- **Jinja2 → Markdown/HTML**: decision document output.
- **pytest + node test runner**: tests above; GitHub Actions CI in mock mode.

## 5. Accounts needed
None. Mock mode runs without keys. Optional live-mode numbers need an OPENAI_API_KEY (not required to merge; report live mode as not run).
