# Realism-gate review: RUBS utility billing workbook

**Reviewer persona:** a property-management bookkeeper who bills about 300 units by RUBS. She has seen spreadsheets where the units add up to a few cents more than the bill, and one where a tenant's move-out was silently ignored. Her questions:
- Does every bill tie out to the cent?
- Does a typo get caught, or does it quietly move money between tenants?

## Findings, by severity
1. **High, fixed.** An amount typed as text ("1,234.50") or a date typed as text ("18/09/2026") was read as 0 with no exception. That bill was split as $0, and the reconciliation still said OK.
   - Both are now flagged: "text instead of a number or date" on Bills, and "text instead of a date" on Occupancy.
   - The bill's reconciliation row now shows not OK.
   - 3 seeded regression tests were added.
2. **Medium, fixed.** Lower-case IDs and service names ("p1-01", "water", "y"). The workbook matched them, because Excel lookups ignore case, but the Python check did not. The two disagreed on 16 of 106 charges.
   - The Python version now matches the same way.
   - A "lower_case_keys" clean data set was added to T1/T2.
3. **Medium, fixed.** Tie-breaking in rounding used exact remainders in Python but 6-decimal remainders in the workbook. They could pick different units in a near-tie. Both now use 6 decimals.
4. **Medium, open and stated.** A unit ID with a trailing space ("P1-01 ") is flagged "unknown unit". Until it is fixed, that unit's occupancy is ignored, so the bill still ties out but the money is split among the other units. The exception shows it.
5. **Medium, open and stated.** Credits and refunds (negative amounts) are flagged and not split. The bookkeeper has to net them into the bill amount.
6. **Low, open.** An amount with 3 decimals (100.005) is rounded to the cent without a warning.
7. **Low, open.** If every tenant has moved out before the bill period, the bill shows "no billable units, all to owner" and the reconciliation shows not OK. That is correct behaviour, but it needs a human decision.

## Stress test (`tests/stress.py`, separate from the sample generator; output in `stress_output.txt`)
| Input | Exceptions | Reconciliation | Python agrees | Verdict |
|---|---|---|---|---|
| Amount typed as text "1,234.50" | text instead of a number or date | B-102 not OK | n/a (input invalid) | OK after fix (was silent $0) |
| Bill date typed as text | text instead of a number or date | B-101 not OK | n/a | OK after fix (was silent) |
| Credit bill −25.00 | negative amount | B-102 not OK | 106/106 | stated limit |
| Zero-amount bill | none | all OK | 106/106 | OK |
| Lower-case unit ID | none | all OK | 106/106 | OK after fix (was 90/106) |
| Unit ID with trailing space | unknown unit | all OK | 106/106 | flagged; money moves until fixed |
| Occupants 2.5 | none | all OK | 106/106 | OK (allowed) |
| Occupants typed as text "3" | occupants missing | all OK | n/a | flagged |
| All P1 tenants gone before period | no billable units (4) | 4 bills not OK | 106/106 | flagged, needs a decision |
| Bill spanning two months | none | all OK | 106/106 | OK |
| Amount 100.005 | none | all OK | 106/106 | weak (silent rounding) |

## Planted numbers?
- **The sample month is my own synthetic data.** The headline "13 of 13 bills OK, 106 of 106 match" uses this pack.
- **Bigger independent checks:**
  - a random full-capacity file (40 units × 30 bills, fixed seed)
  - 3 small examples worked by hand in the Python tests, written before the code
  - the Python version itself, which does not read any workbook formula.
- **Not done:** no real rent roll or utility bills were used.

## Score sheet (Pass or Fail, never averaged)
| # | Item | Result | Evidence or reason |
|---|---|---|---|
| 1 | Data realism | **Fail** | No real bills or rent roll. Synthetic data plus messy variants only. |
| 2 | Grounding | Pass | Every charge traces to its Allocation row (weights, pool, remainder, rank). Manual_Check rebuilds any one charge from the inputs. |
| 3 | Evaluation | Pass | A separate exact-fraction version, 3 hand-worked examples, 21 seeded errors, 6 clean data sets, regressions kept. |
| 4 | Failure modes / human-in-the-loop | Pass | Per-row Issue columns and the Exceptions total. Reconciliation status per bill. Rows typed below capacity and formula errors are counted. |
| 5 | Integration | **Fail** | Manual entry or paste into input tables. No import from a utility portal or property-management system. |
| 6 | Security | Pass (for scope) | A local workbook. No macros, no external links, no personal data in the demo. |
| 7 | Cost and latency | Pass | Recalculation is about 1 s per file at full capacity (LibreOffice). Excel not timed (stated). |
| 8 | Honest claims | Pass | Numbers in TEST_REPORT.md have dataset, date and denominators. The legal note and limits are in the README and on the page. |

**Ship decision:** OK as a portfolio demo. Section 8 passes, and the fails (1, 5) are listed on the project page.

## Fix list
- **Quick wins (done):** text-number and text-date checks; case-insensitive matching in the Python check; matching tie-break.
- **Bigger upgrades:**
  - Support credit lines.
  - Warn on IDs with leading or trailing spaces, and on amounts with more than 2 decimals.
  - Test in Microsoft Excel 365.
  - Run one real month from the client.
