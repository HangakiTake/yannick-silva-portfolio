# Ponytail review, round 1

Scope: scripts/, powerquery/, the workbook formulas, tests/.

## Must fix
1. **The banner would fail every month after the first.** Checks!A2 included the Python reference block (N5:R10), which holds hard-coded base figures. After a real refresh in Excel, it would show DIFF and CHECK FAILED forever. *Fixed:* banner uses a live tie-out (N15:R17: dashboard revenue/pipeline/targets vs the Recon query); the reference block is labelled "reference only". Test `test_r8_banner_survives_new_month`.
2. **tbl_FX, tbl_Stages, tbl_Region, tbl_Aliases were used in M but no query defined them.** Every refresh would fail with "name not recognised". *Fixed:* `00_tbl_*.m`, listed first on the Queries sheet. A static test checks every referenced query exists and is created earlier.
3. **US-format text amount `1,234.56` was read as 1.23456.** Silent wrong number. *Fixed* in Python and M (last mark is the decimal mark; `1,234`/`1.234` flagged as ambiguous). 19 parsing tests.

## Should fix
4. Semicolon CSVs (PL/DE Excel exports) crashed the run. *Fixed:* delimiter detection in both.
5. DACH Cust ID was documented as optional but treated as required. *Fixed* in both.
6. Blank invoice numbers were reported as duplicates. *Fixed:* MISSING_INVOICE_NO.
7. Countries missing from tbl_Region went to "Other", which the dashboard didn't show, so the region rows didn't sum to the total. *Fixed:* UNKNOWN_COUNTRY warning + "Other" row.
8. Unreadable target rows crashed the Python run (and in M would become null targets). *Fixed:* BAD_TARGET, excluded, banner red.
9. CSV `source_row` in Python was counted after blank rows were dropped, so it differed from the M row numbers. *Fixed.*
10. Future months showed revenue 0 and "0%" on the Dashboard. *Fixed:* blank.
11. The Queries sheet didn't contain the M, though the README said it did. *Fixed.* config.py docstring referred to a non-existent test file. *Fixed.*
12. The R7 independent recompute used a different rounding rule (1-cent false alarm). *Fixed* in the test, and the Excel-side risk is documented.

## Nice to have (not done)
- fnReadSalesFile numbers rows assuming the used range starts at row 1. Only `source_row` on Exceptions would be off, not the figures.
- Fuzzy or alias-table customer matching (would lift R5 above 98%).
- Windows-1250 CSV support.

Verdict: **Not ready** → fixes applied; see round 2.
