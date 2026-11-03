# Input specification

Folder layout under `InputFolder`:
```
crm\crm_accounts.csv
crm\crm_deals.csv
sales_pl\sales_pl_YYYY-MM.xlsx      one file per month
sales_dach\sales_dach_YYYY-MM.xlsx  one file per month
targets.csv
```
Empty templates with one example row are in `templates/`. Other files in the sales folders (notes, Excel `~$` lock files) are ignored.

## General rules
- **CSV**: UTF-8 (with or without BOM). Comma or semicolon delimiter (detected from the header line). Blank lines are ignored.
- **Excel**: the first sheet is read. The header row can be anywhere in rows 1–10; title rows and blank rows above or inside the data are skipped.
- **Dates**: a real Excel date cell, or text `DD.MM.YYYY` or `YYYY-MM-DD`. Anything else (e.g. `06/03/2026`, `TBC`, a date number in a General-format cell) is listed as BAD_DATE.
- **Amounts**: a number cell, or text with a comma or point as the decimal mark (`1234,56`, `1 234,56`, `1.234,56`, `1,234.56`). `1,234` and `1.234` are ambiguous and listed as BAD_AMOUNT. No currency symbols in the amount cell. Credit notes are negative amounts.
- **Currency**: ISO code, one of the codes on Parameters → tbl_FX (EUR, PLN, CHF, CZK). Add a row there to accept a new currency.
- **Headers**: matched case-insensitively. Alternative names are on Parameters → tbl_Aliases; add a row there when a source renames a column.

## sales_pl_YYYY-MM.xlsx (PL ERP export)
| Column | Type | Required | Notes / aliases |
|---|---|---|---|
| Nr faktury | text | yes | invoice number, unique across all files; blank = MISSING_INVOICE_NO. Aliases: Numer faktury, Invoice No |
| Data sprzedazy | date | yes | must fall in the file's month. Alias: Data sprzedaży, Data |
| Klient | text | yes | customer name as in CRM. Alias: Kontrahent |
| Kraj | text (ISO-2) | yes | PL, DE, AT, CH, CZ |
| Kwota netto | amount | yes | net, before VAT. Aliases: Kwota netto (PLN), Netto |
| Waluta | text (ISO) | yes | |

## sales_dach_YYYY-MM.xlsx (DACH ERP export)
| Column | Type | Required | Notes / aliases |
|---|---|---|---|
| Invoice No | text | yes | Aliases: Rechnungsnr, Invoice |
| Cust ID | text | no | CRM account id; used first for matching. Aliases: Kundennr, Customer ID |
| Customer | text | yes | Alias: Kunde |
| Country | text (ISO-2) | yes | Alias: Land |
| Invoice Date | date | yes | Alias: Rechnungsdatum |
| Net Amount | amount | yes | Aliases: Netto, Amount (net) |
| Currency | text (ISO) | yes | Alias: Währung |

## crm_accounts.csv
`account_id` (text, unique), `account_name` (text), `country` (ISO-2), `owner` (text).

## crm_deals.csv
`deal_id` (text), `account_id` (text, should exist in accounts), `stage` (Lead, Qualified, Proposal, Negotiation, Won, Lost — see tbl_Stages; any other stage is listed as BAD_STAGE and left out of the pipeline), `amount` (amount), `currency`, `expected_close` (date), `owner`.

## targets.csv
`month` (YYYY-MM-01), `region` (PL, DACH, CEE), `target_eur` (amount, EUR). An unreadable row is BAD_TARGET and turns the banner red.
