# Realism gate review: would a skeptical Polish CFO/controller buy this?

Reviewer stance: a group controller at a mid-size PL/DACH distributor. They've seen "automated dashboards" that broke on the second month.

| # | Gate | Verdict | Evidence / gap |
|---|---|---|---|
| 1 | Inputs look like real exports | **Pass** | Polish ERP headers, DD.MM.YYYY, decimal comma, merged title rows, a BOM CSV, a header renamed by IT, German DACH headers, PLN/EUR/CHF/CZK. Gap: no Windows-1250 CSV and no real Comarch/Symfonia/SAP layout |
| 2 | Messy data handled, not hidden | **Pass** | 15/15 seeded issues listed, 0 false alarms; ambiguous `1,234` refused rather than guessed; FILE_REJECTED turns the banner red |
| 3 | Numbers tie out and you can prove it | **Pass** | Per-file rows and EUR reconcile to 0 on Checks; the KPI tie-out block; independent recompute equal to the cent (Excel itself not yet run) |
| 4 | Survives month 2 | **Pass (logic)** | Oct drops in with no edits; aliases and FX are on Parameters. Refresh in Excel not timed |
| 5 | Honest about limits | **Pass** | R5 96.9% reported as missed with the cause; untested items listed; no fuzzy matching claimed |
| 6 | An executive can read it in 30 s | **Pass (unverified)** | One page: KPIs, month trend, regions, stages, top 10, status line. R6 test not yet run with a person |
| 7 | Handover-ready | **Pass** | INPUT_SPEC + templates, CHANGE_MANAGEMENT, HANDOVER, setup steps |
| 8 | Runs in the buyer's real environment | **Fail until verified** | Power Query M has never been executed; one-time setup means pasting 19 queries by hand |

## Stress test (inputs the generator never produced; `scripts/stress_test.py`)
| Case | Outcome |
|---|---|
| US-format text amount `1,234.56` | Parsed correctly (after a fix: it was being read as 1.23456 → **silent error found and fixed**) |
| Ambiguous `1,234` | BAD_AMOUNT, excluded, listed (after the fix) |
| Date as a number in a General-format cell | BAD_DATE, listed (loud; not auto-converted) |
| Credit note (negative amount) | Loaded as negative revenue |
| Header pushed below row 10 | FILE_REJECTED, banner red |
| Same invoice number in PL and DACH | DUPLICATE_INVOICE, second one excluded |
| Excel `~$` lock file / stray notes.txt | Ignored |
| CRM CSV with `;` delimiter | Crashed at first → **fixed** with delimiter detection (Python and M) |
| Name with extra spaces and upper case | Matched |
| Unknown deal stage "On hold" | BAD_STAGE, excluded from pipeline, listed |
| DACH export without the Cust ID column | Was rejected as a missing column → **fixed**: Cust ID is optional, matching falls back to name (0 new exceptions) |
| Blank invoice numbers | Were reported as DUPLICATE_INVOICE → **fixed**: MISSING_INVOICE_NO |
| Country not in the region map (HU) | Was silently put in "Other", missing from the region table → **fixed**: UNKNOWN_COUNTRY warning + "Other" row on the Dashboard |
| Target row "tbd" | Was crashing the run → **fixed**: BAD_TARGET, excluded, banner red (attainment would be inflated) |

Six real defects were found by the stress test and fixed: the US-format amount, the semicolon CSV, the optional Cust ID, blank invoice numbers, unmapped countries and bad target rows. Full table: `docs/stress_results.md`.

## Shipping verdict
**Ship as a portfolio demo after Excel verification (gate 8).** Don't present it as tested in Excel until the 10 points in EXCEL_VERIFICATION.md have been done. In the proposal, say plainly that matching is exact plus Cust ID (96.9% on the demo set, misses listed) and that fuzzy matching is an option.
