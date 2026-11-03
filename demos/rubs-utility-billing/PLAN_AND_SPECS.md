# RUBS utility billing workbook demo — plan and specs

Job: Upwork 2117450530616786983 "Utilities Billing Automation Services" (applied 2026-11-03).

## Requirements (from the post)
1. Multiple properties, each with different units, occupants and utility services.
2. Proportional allocation of each utility bill to units, primarily by occupant count, with configurable rules.
3. Exceptions: vacant units, varying occupancy, discounts, owner-paid percentage, services not applicable to some units.
4. Bill entry for water, sewer, trash, gas (+ other) with amounts and service periods.
5. Reports: per-unit breakdown, property summary, reconciliation (allocated = billed).
6. Independent manual calculator to verify any unit's charge.
7. Monthly updates without editing formulas; all variables editable in input tables.

## Professional standards added
- Partial-month occupancy pro-rated by days within the service period (move-ins/outs).
- Rounding: allocate in cents with largest-remainder so unit totals sum exactly to the tenant-billable amount.
- Owner-paid share and vacant-unit shares go to an "Owner" line, never silently dropped.
- Input validation (data validation lists, negative/blank checks) and an Exceptions sheet listing any rule violation.
- Note in README: RUBS rules vary by US state/local law; demo is a calculation tool, not legal advice.

## Deliverable
- `RUBS_Billing_Demo.xlsx` built with openpyxl: sheets Settings_Properties, Settings_Units, Occupancy, Bills, Rules, Allocation (formulas), Unit_Statements, Property_Summary, Reconciliation, Manual_Check, Exceptions, README.
- Python reference implementation `rubs.py` (pure function) used to generate expected values and tests.
- Synthetic messy data: 3 properties, 4/8/12 units, a vacancy, a mid-month move-in, a unit excluded from gas, a 10% discount, 15% owner-paid trash.

## Tests and pass thresholds
- T1 Reconciliation: for every property and utility, sum(unit charges) + owner share = bill amount, exact to $0.00 (100% of cases).
- T2 Excel formulas (recalculated via LibreOffice headless) match `rubs.py` to $0.01 for every unit (100%).
- T3 Manual_Check reproduces any chosen unit's charge exactly.
- T4 Changing an input (occupant count, owner %) changes outputs with no formula edits (scripted check).
- T5 Exceptions sheet flags: negative bill, occupancy on a unit marked vacant, service period gaps (all seeded errors caught).
- T6 pytest suite green; ≥ 15 tests.

## Stack and why
- Excel (openpyxl) because the client lives in Excel and wants formulas he can see and own.
- Python reference + pytest to prove the maths independently of the workbook.
- LibreOffice headless to recalculate and read back formula results in CI.

## Build time
About 6–8 hours.

## Accounts Yannick needs
None. Can merge into the portfolio once reviews pass.
