# Test report: RUBS utility billing workbook

- **Run:** 2026-11-03 (Europe/Zurich).
- **Software:** Python 3.13.5, openpyxl 3.1.5, LibreOffice 25.2.3.2.
- **Command:** `python -m pytest -q tests`. **Result: 56 passed, 0 failed** (about 60 s, mostly LibreOffice recalculating 34 workbook variants).

| Spec | What is checked | Tests | Result |
|---|---|---|---|
| T1 Reconciliation | Every bill: tenant charges + owner share = billed amount, to the cent. "Statements tie to allocation" is OK. Run on 6 clean data sets: base, more occupants, higher owner %, a November month, a full-capacity random file (40 units × 30 bills), lower-case keys. | 6 | pass |
| T2 Workbook = Python | Every (bill, unit) charge in cents matches the separate Python version (exact fractions) on the same 6 data sets. Unit_Statements and Property_Summary match too. | 7 | pass |
| T3 Manual_Check | 6 chosen bill/unit pairs (discount, vacant unit, excluded gas, move-in, move-out/move-in) show MATCH and equal the Allocation charge. | 6 | pass |
| T4 Inputs only | More occupants shifts cost to that unit. A higher owner % moves cost to the owner. A new month entered in the input tables recalculates with no formula edits. | 3 | pass |
| T5 Exceptions | Clean data sets show 0 issues. Each of 21 seeded errors is flagged by its own check. | 22 | pass |
| Other | No formula errors in 7 workbooks (including the blank copy). The blank copy is empty. Full-capacity recalculation time. 3 hand-worked examples for the Python version. | 12 | pass |

## Sample month (synthetic, `RUBS_Billing_Demo.xlsx`)
- **Data:** 3 properties, 24 units, 13 bills.
- **Reconciliation:** 13 of 13 bills OK.
- **Totals:** $6,794.73 billed = $6,427.52 charged to tenants + $367.21 owner.
- **Cross-checks:** 0 formula errors. Python agrees on 106 of 106 bill/unit charges.
- **Manual_Check example:** B-201 / P2-05 gives exact $89.938…, rounded $89.94. The Allocation figure is $89.94, so it shows MATCH.

## Speed
LibreOffice headless opens, recalculates and saves one workbook in about 1.0–1.1 s on the build box. That was measured for the sample file and a full-capacity file. Microsoft Excel was not timed.

## Messy-input stress run (`tests/stress.py`, output in `docs/stress_output.txt`)
11 variants. See `docs/realism-review.md`.

## Not tested
- Opening in Microsoft Excel: only LibreOffice was used.
- Real utility bills or a real rent roll.
