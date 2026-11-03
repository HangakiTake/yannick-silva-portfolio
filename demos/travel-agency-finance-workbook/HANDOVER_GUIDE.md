# Handover guide: Travel agency finance workbook

One file, no macros. Grey cells are formulas (locked); white cells are for typing. Work in the tables; new rows extend formulas automatically.

## Daily use
1. **New booking** - Bookings sheet, next empty row: Booking ID (e.g. B-1041), date, customer (from list), salesperson, destination, type FIT/Group, pax, travel dates, selling price and currency. Supplier costs go in Bills with the same Booking ID.
2. **Invoice** - Invoices sheet: Invoice ID, Booking ID, date, due date, amount, currency. Balance and status calculate.
3. **Payment received/made** - Payments sheet: one row per payment, any number of partials. Type "In" against an Invoice ID, "Out" against a Bill ID. Refunds: negative amount.
4. **Supplier bill** - Bills sheet: Bill ID, supplier, Booking ID, dates, amount, currency.
5. **Expenses** - Expenses sheet for rent, salaries, marketing etc. (feeds Opex).
6. **Rates** - add a USD_per_EUR row each week on Rates. BAM is pegged (1.95583) in Settings.

## Month end
- Settings: set **As-of date**; switch **Base currency** (EUR/BAM/USD) if needed.
- Check **Checks!B2 = ALL OK**. Any "ISSUE" or a non-empty Flag column tells you which row to fix.
- Dashboard and Reports (month, destination, customer, salesperson, aging) update themselves.

## Protection
Dashboard, Reports, Checks, Settings, Instructions are protected without password (Review > Unprotect Sheet). Data sheets are left unprotected so tables can grow; their formula cells are locked and grey - don't type over them.

## Going live
Use TravelAgency_Finance_Workbook_BLANK.xlsx: fill Customers, Suppliers, Lists, Rates, set First month and As-of date, then start entering.
