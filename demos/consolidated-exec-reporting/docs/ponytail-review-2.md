# Ponytail review, round 2 (after the round 1 fixes)

Re-read: 00_tbl_*, 02 (Amount, Csv), 03 (optional columns), 05 (MISSING_INVOICE_NO), 06/13 (targets), 15, 16, build_workbook banner and live tie-out, pipeline.py, the new tests.

## Must fix
None.

## Should fix
None. Checked specifically:
- The banner includes BAD_TARGET; a LibreOffice test proves a bad target row turns it red (`test_bad_target_turns_banner_red`).
- Python and M agree on the new rules: same issue names, same order, Cust ID optional in both, delimiter detection in both.
- Query creation order on the Queries sheet matches the dependencies (static test).
- Exceptions!D is the issue column the banner counts.

## Nice to have (left open, documented)
- Row numbers in fnReadSalesFile assume the used range starts at row 1.
- `Text.Trim` on a null cell in the 00_tbl_* queries: should return null in M, but this is unverified (EXCEL_VERIFICATION item 2 would show it).
- Fuzzy matching, Windows-1250 CSVs.

Verdict: **Ready for Excel verification.** Nothing here has been run in Excel.
