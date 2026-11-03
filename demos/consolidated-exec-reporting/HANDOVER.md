# Handover (one page)

**What it is.** A workbook that consolidates PL and DACH sales exports, CRM accounts/deals and targets into one EUR dashboard, with a reconciliation and an exceptions list.

**Owner's monthly routine (2 minutes + exception fixing).** Drop files → Refresh All → read the Checks banner → fix or accept Exceptions → send the Dashboard.

**What can go wrong and what you'll see.**
| Symptom | Likely cause | Fix |
|---|---|---|
| Banner CHECK FAILED, Exceptions shows FILE_REJECTED | A column was renamed or the header moved below row 10 | Add the new header to tbl_Aliases, or fix the file |
| Refresh error "file not found" | InputFolder wrong or missing trailing `\` | Fix Parameters!B3 |
| Revenue in "(unmatched)" grows | New customers not yet in CRM, or name spelt differently | Create the account in CRM or correct the name; add the Cust ID in DACH files |
| BAD_AMOUNT on many rows | Export switched number format (e.g. `1,234`) | Re-export with numbers as numbers, not text |
| Numbers differ from ERP by a cent | Rounding per row vs per total | Expected; the rule is per-row half-up to cents |

**Where things are.** Queries: `powerquery/` (and the Queries sheet). Rules: README "Rules". Inputs: `INPUT_SPEC.md`. Changes: `CHANGE_MANAGEMENT.md`.

**Not covered.** Fuzzy name matching, VAT, intercompany eliminations, live CRM API connection (the demo uses CSV exports), automatic scheduling (refresh is manual or via Power Automate, not built here).
