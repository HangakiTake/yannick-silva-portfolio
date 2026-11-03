| # | Stress case | Result | Revenue Δ vs base (EUR) | New exception types |
|---|---|---|---|---|
| 1 | US-format text amount '1,234.56' in PL file | ran | -2,031.87 | none |
| 2 | Ambiguous text amount '1,234' in DACH file | ran | -2,183.71 | BAD_AMOUNT +1 |
| 3 | Date stored as Excel serial number (46250) | ran | -4,330.34 | BAD_DATE +1 |
| 4 | Credit note (negative amount) | ran | -5,249.74 | none |
| 5 | Header pushed below row 10 (12 junk rows) | ran | -110,183.56 | FILE_REJECTED +1; RECON DIFF |
| 6 | Same invoice number in PL and DACH files | ran | -5,897.08 | DUPLICATE_INVOICE +1 |
| 7 | Excel lock file ~$sales_pl_2026-09.xlsx left in folder | ran | 0.00 | none |
| 8 | Unrelated file 'notes.txt' dropped in folder | ran | 0.00 | none |
| 9 | CRM deals exported with ';' delimiter (Excel PL/DE locale) | ran | 0.00 | none |
| 10 | Customer name with trailing spaces and different case | ran | 0.00 | none |
| 11 | Deal with unknown stage 'On hold' | ran | 0.00 | BAD_STAGE +1 |
| 12 | DACH export without the Cust ID column | ran | 0.00 | none |
| 13 | Blank invoice number on two rows | ran | -9,918.16 | MISSING_INVOICE_NO +2 |
| 14 | Sale to a country not in the region map (HU) | ran | 0.00 | UNKNOWN_COUNTRY +1 |
| 15 | Target row with 'tbd' instead of a number | ran | 0.00 | BAD_TARGET +1; target Δ -128,000.00 |
