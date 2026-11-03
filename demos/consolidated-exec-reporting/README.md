# Consolidated Executive Reporting (Excel + Power Query) — portfolio demo

One Excel workbook that collects monthly sales exports from two regional Excel files (PL and DACH),
CRM accounts and deals (CSV) and a targets file, then refreshes a one-page executive dashboard.
Every number on the dashboard ties back to its source rows, and anything that can't be loaded cleanly is
listed on an Exceptions sheet instead of being dropped silently.

All data is synthetic, for the fictional company "Kestrel Industrial Supplies".

## What's in the workbook (`ExecReporting.xlsx`)
| Sheet | Purpose |
|---|---|
| Dashboard | Revenue vs target, attainment, open and weighted pipeline, win rate, monthly trend, regions, stages, top 10 customers, 2 charts |
| Checks | A banner (**ALL CHECKS PASS** / **CHECK FAILED - do not publish**), a per-file reconciliation (rows read = loaded + excluded, EUR likewise) and the schema check |
| Exceptions | One row per problem: file, row, key, issue, detail, raw value and the action to take |
| Parameters | `InputFolder`, FX rates, stage probabilities, the country→region map and the header aliases. Business users edit this sheet, not the queries |
| Input_Spec | The required columns per source (also in `INPUT_SPEC.md`) |
| Queries | The Power Query M for each query, in the order to create them |
| Data_* | The loaded tables that the dashboard formulas read |

## One-time setup in desktop Excel 365 (about 15 minutes)
The xlsx is generated on Linux, so the queries are shipped as M text (`powerquery/*.m`, also on the Queries sheet)
and the Data_* sheets hold a snapshot of what the queries return for `data/base`.
1. Copy the `data` folder to e.g. `C:\ExecReporting\data\`. Set **Parameters!B3** (`InputFolder`) to the folder with a trailing `\`, e.g. `C:\ExecReporting\data\base\`.
2. Data → Get Data → From Other Sources → Blank Query. Open the Advanced Editor and paste the M from `powerquery/01_pInputFolder.m`. Name the query exactly as in its first line (`// Name: pInputFolder`). Repeat for every file in numeric order, starting with the four `00_tbl_*` queries (they read the tables on Parameters).
3. Files 00–05 and 11: Close & Load To → **Only Create Connection**.
4. Files 10, 12–17: first clear the snapshot range on the target sheet, then Close & Load To → Table → **Existing worksheet** at the cell in the file header (e.g. `Data_Sales!A1`, `Exceptions!A4`, `Checks!A4`, `Checks!T4`, `Dashboard!N5`).
5. Data → Refresh All. Checks!A2 should say **ALL CHECKS PASS** the live tie-out (Checks!N15:R17) should show 3 × OK, and on `data\base\` the Python reference block (Checks!N5:R10) should show 6 × OK.
6. Privacy level prompt: choose "Ignore privacy levels" for this file (all sources are local files).

## Monthly use (about 2 minutes)
1. Drop the new month's files into `sales_pl\` and `sales_dach\` (keep the file naming `sales_pl_YYYY-MM.xlsx`) and replace the CRM CSVs.
2. Data → Refresh All.
3. Read Checks!A2. If it says CHECK FAILED, open Exceptions, fix the file named there, refresh again. Don't send the dashboard until it passes.
4. Work through the Exceptions list (warnings such as unmatched customers don't block publishing but should be cleared over time).

## Rules the pipeline applies
- **Amounts** are converted to EUR with the rates on Parameters, rounded half-up to cents per row.
- **Excluded rows** (shown on Exceptions, not counted): blank invoice number, duplicate invoice number (the first one is kept), unreadable date, unreadable or ambiguous amount (`1,234` / `1.234` could mean either), missing or unknown currency, a date outside the file's month, a deal with an unknown stage.
- **Warnings** (counted but listed): customer not found in CRM or matching several accounts (revenue shows as "(unmatched)"), a deal pointing to an unknown account, duplicate CRM accounts, a country missing from tbl_Region (revenue goes to region "Other").
- **Rejected files**: a file whose required column can't be found (even through the alias list) is skipped as a whole and the banner turns red. A target row that can't be read is excluded and also turns the banner red, because a missing target would inflate attainment. Missing data is never silently replaced by zero.
- **The banner** checks: every file passed the layout check, every file reconciles (row and EUR diff 0), the dashboard revenue, pipeline and target totals equal the Recon totals, and no BAD_TARGET rows exist.
- **Customer matching**: CRM account id first (DACH files carry it); otherwise the normalised name (case, spaces and punctuation ignored) plus country. *Deviation from the plan: the plan said name first, then id. Id-first is safer because names change and ids don't.* There is no fuzzy matching, so a variant like "Mueller" vs "Müller" is listed as unmatched rather than guessed.

## Verifying without Excel
`scripts/pipeline.py` mirrors the M logic in Python, so the rules can be tested on Linux.
```
python3 scripts/generate_data.py     # synthetic data + answer key (seed 7)
python3 scripts/build_workbook.py    # ExecReporting.xlsx with snapshot data and formulas
python3 -m pytest tests -q -s        # requirement tests (needs pandas, openpyxl, pytest; LibreOffice for the formula checks)
python3 scripts/stress_test.py       # realism stress cases
```
Results: `docs/TEST_RESULTS.md`. What still has to be checked in real Excel: `docs/EXCEL_VERIFICATION.md`.

## Other docs
`INPUT_SPEC.md` (with `templates/`), `CHANGE_MANAGEMENT.md`, `HANDOVER.md`, `docs/TEST_SCRIPT.md`, `docs/realism-review.md`, `docs/ponytail-review-*.md`, `TIME_LOG.md`.

## Licence
Code: PolyForm Noncommercial 1.0.0. Docs and workbook: CC BY-NC 4.0. See `LICENSE`. Copyright Yannick Silva.
