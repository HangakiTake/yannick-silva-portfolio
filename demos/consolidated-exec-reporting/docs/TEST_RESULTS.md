# Test results (2026-10-28, Linux, Python mirror + LibreOffice recalc)

`python3 -m pytest tests -q -s` → **44 passed, 1 xfailed** (the xfail is a missed threshold, reported as missed).

| Req | Threshold | Result | Status |
|---|---|---|---|
| R1 | Refresh All in Excel works with no errors | Not run: Power Query does not run on Linux | **Untested** — see EXCEL_VERIFICATION.md |
| R2 | All source files and columns mapped | 12/12 files, 13/13 standard columns | Pass |
| R3 | Rows and EUR reconcile per file (diff 0) | 15 sources, row diff 0, EUR diff 0.00 vs an independent pandas recount | Pass |
| R4 | 100% of seeded issues listed, 0 false alarms on clean data | 15/15 seeded; clean set 0 exceptions; base 27 exceptions, 0 not in the answer key | Pass |
| R5 | ≥ 98% of customer rows matched correctly | 284/293 = **96.9%**. 0 wrong matches; all 12 non-matches listed (3 are genuinely new customers) | **MISSED** |
| R6 | Non-technical reviewer answers 5 questions in < 30 s each | Questions and answer key in TEST_SCRIPT.md | **Untested** (needs a person) |
| R7 | Dashboard KPIs equal an independent recompute | 6/6 KPI tie-outs OK after LibreOffice recalc on base and messy sets; independent pandas recompute equal to the cent | Pass (formulas in LibreOffice, not Excel) |
| R8 | New month appears with no edits | Oct 2026: 50 rows added, no code edits. Python run 0.06 s | Pass for logic. Also: a month-2 workbook keeps a green banner (LibreOffice). Excel refresh time **not measured** |
| R9 | Damaged inputs either load correctly or fail loudly | 4/4: 3 load with identical numbers, 1 (renamed amount column) rejected, banner FAILED, revenue drops by exactly that file's EUR 114,866.84 | Pass |
| R10 | Handover: owner can run it from the docs alone | HANDOVER.md written | **Untested** (needs a person) |

Extra: 19 amount/date parsing unit tests, 3 static checks on the M files (names, creation order, bracket balance), and 15 realism stress cases (`docs/stress_results.md`).

## Why R5 is missed
The 9 wrongly unmatched rows are 4 hard spelling variants (legal form written out as "Spółka z o.o." instead of "Sp. z o.o.", plus abbreviations such as "Autom.") and 5 rows where the name matched two CRM accounts because of the seeded duplicate accounts. The matcher deliberately doesn't guess: they land on Exceptions as UNMATCHED/AMBIGUOUS and their revenue shows as "(unmatched)". Reaching 98% would need fuzzy matching or an alias table for customer names. That's a client decision (risk of a wrong match versus manual clearing), not something to switch on silently.

## A cent difference that was found and fixed in the test
The first independent recompute rounded with Python's `round(x + 1e-9, 2)` and differed from the pipeline by EUR 0.01 on the weighted pipeline. The business rule is half-up to cents per row; the test now applies that rule with `Decimal`, and the figures agree. Power Query's `Number.Round(x, 2, RoundingMode.AwayFromZero)` works on binary doubles, so **a 1-cent difference against Excel is possible** and is item 4 in EXCEL_VERIFICATION.md.
