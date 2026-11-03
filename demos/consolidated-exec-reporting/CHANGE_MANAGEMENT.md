# Change management

The aim is that routine changes are made on the **Parameters** sheet by the finance/controlling owner, and only
structural changes need someone who edits Power Query. Every change ends with Refresh All and a green Checks banner.

| Change | Who | Where | How to check it worked |
|---|---|---|---|
| Monthly FX rates | Report owner | Parameters → tbl_FX | Checks banner green; EUR totals move as expected |
| New currency | Report owner | add a row to tbl_FX | BAD_CURRENCY rows for it disappear from Exceptions |
| A source renames a column | Report owner | add the new header to tbl_Aliases | FILE_REJECTED disappears; row counts on Checks match the file |
| New country or region | Report owner | tbl_Region (and targets.csv) | Region table on Dashboard shows it |
| Stage names / probabilities change in CRM | Report owner + sales ops | tbl_Stages | BAD_STAGE rows disappear; weighted pipeline changes |
| New target year | Report owner | targets.csv | Target line on Dashboard covers the new months |
| A new source system (e.g. a third region's ERP) | Power Query editor | copy 03_fnReadSalesFile pattern, add to 05_qSalesStage and 16_Recon | New file rows appear on Checks with diff 0 |
| A new KPI | Power Query editor or Excel author | formula on Dashboard reading Data_* sheets | Add it to the tie-out block on Checks |

## Rules
1. Never type numbers into Data_* sheets. They are overwritten on refresh.
2. Never publish while Checks!A2 says CHECK FAILED.
3. Keep a dated copy of the workbook before changing queries (`ExecReporting_2026-10-28.xlsx`). Keep the previous month's input files.
4. Log each change in the table below (date, who, what, why). One line is enough.
5. Before a structural change goes live, refresh it on last month's files and confirm the figures don't move.

## Change log
| Date | Who | Change | Reason |
|---|---|---|---|
| 2026-10-28 | Yannick Silva | Initial version | — |
