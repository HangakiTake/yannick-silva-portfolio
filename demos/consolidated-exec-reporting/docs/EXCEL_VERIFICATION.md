# What Yannick must verify in desktop Excel 365 (Windows) before showing this

Nothing in the M has been executed. The Python mirror proves the rules, not the M syntax.
1. **Setup**: follow README "One-time setup" on `data\base\`. Every query should save without a syntax error. Note the time it takes.
2. **Refresh All** with no error dialogs; Checks!A2 = ALL CHECKS PASS; Checks!N15:R17 (live tie-out) shows 3 × OK and Checks!N5:R10 shows 6 × OK. The N5:R10 block compares against the Python numbers: revenue 1,466,086.42, target 1,530,900.00, open pipeline 2,311,039.05, weighted 824,668.98, win rate 67.57%.
3. **Exceptions** has 27 rows (DUPLICATE_ACCOUNT 2, UNKNOWN_ACCOUNT 3, DUPLICATE_INVOICE 3, BAD_DATE 2, BAD_AMOUNT 2, BAD_CURRENCY 2, DATE_OUTSIDE_FILE_MONTH 1, UNMATCHED_CUSTOMER 7, AMBIGUOUS_CUSTOMER 5).
4. **Rounding**: if a KPI is off by 0.01, it's the double-vs-decimal half-up difference (TEST_RESULTS.md). Note it; don't patch the tie-out.
5. **Messy set**: set InputFolder to `data\messy\`, refresh. Expect CHECK FAILED with FILE_REJECTED for `sales_dach_2026-06.xlsx`. The PL file with the merged title and the renamed header, the EU text amounts and the BOM CSV should load.
6. **New month**: point InputFolder at `data\next\` (base plus the Oct files), refresh. Oct 2026 should appear on the Dashboard, the banner should stay ALL CHECKS PASS, and N5:R10 will show DIFF (expected: it is the base reference). Time the refresh (R8 target: under 60 s).
7. **CSV blank lines**: confirm `Csv.Document` doesn't produce null rows that skew `source_row` on `data\messy\crm\crm_deals.csv`.
8. **Privacy levels / formula firewall**: if Excel reports "Formula.Firewall", set Data → Get Data → Query Options → Privacy → "Ignore privacy levels" for this workbook, and note it in the README.
9. Take the portfolio screenshots from Excel. `docs/dashboard.png` is a LibreOffice render and its fonts and charts differ.
10. R6 and R10 need a non-technical person (TEST_SCRIPT.md, HANDOVER.md).
