# RUBS utility billing workbook (demo)

This is an Excel workbook that splits each property's water, sewer, trash, gas and other bills across its units. It uses RUBS (ratio utility billing), splitting by occupant-days, square feet or equally. Every rule is in an input table, so a new month needs no formula edits.

Open `RUBS_Billing_Demo.xlsx` (sample data) or `RUBS_Billing_BLANK.xlsx` (empty inputs).

## How it works
1. **Owner-paid share.** The owner-paid % of each bill comes off the top.
2. **Weights.** The rest is split by weight:
   - occupant-days (people × days in the bill period), or
   - square feet × occupied days, or
   - equal × occupied days.

   Move-ins and move-outs inside the period are pro-rated by day.
3. **Vacant days.** These carry a "vacant weight" (0 or 1 per rule). With weight 1, a vacant unit's share goes to the owner. With 0, that share is spread over the tenants.
4. **Unit discount.** It reduces the unit's charge, and the owner pays the difference.
5. **Excluded services.** A service can be excluded per unit (for example, no gas).
6. **Rounding.** It is done in cents with the largest-remainder method, so unit charges plus the owner share equal the bill exactly. Ties go by remainder (6 decimals), then by unit order.

## Sheets
- **Inputs (yellow cells):** Settings_Properties, Settings_Units, Occupancy, Bills, Rules.
- **Results:** Allocation, Unit_Statements, Property_Summary, Reconciliation.
- **Manual_Check:** works out any one bill and unit from scratch, separately from Allocation, and says MATCH or DIFFERENT.
- **Exceptions:** counts every input problem. These include negative amounts, missing fields, text where a number or date belongs, period gaps or overlaps, unknown units or properties, overlapping occupancy, occupancy on a unit marked vacant, duplicates, bad rule values, rows typed below the capacity, and any formula error.

Capacity: 10 properties, 40 units, 100 occupancy rows, 30 bills a month, 60 rules.

## Rebuild and test
```
pip install openpyxl pytest            # plus LibreOffice (soffice) on PATH
python src/build_workbook.py RUBS_Billing_Demo.xlsx
python src/build_workbook.py RUBS_Billing_BLANK.xlsx --blank
python -m pytest -q tests              # 87 tests, about 1 minute
python tests/stress.py                 # messy-input stress run
```
`src/rubs.py` is a separate Python version of the same maths, using exact fractions. The tests check the workbook against it cent by cent.

## Limits
- **Bills that are not spread.** A bill is only allocated when its amount and dates are numbers, the amount is not negative, the property and service are known and its rule is usable (valid method, owner % and vacant weight between 0 and 1, no duplicate rule; a blank % counts as 0). Otherwise it is flagged, charges nobody and stays out of the Property_Summary totals.
- **Credits.** A credit or refund on a bill (a negative amount) is therefore flagged and not split. Enter it as a reduced amount instead.
- **Move-in dates.** A blank move-in means the tenant was there before the period, so it counts from the period start. A move date typed as text is flagged and that row counts no days.
- **Rule changes.** One rule per property and service applies to the whole period. A rule change in the middle of a period is not supported.
- **Testing.** Formulas were recalculated with LibreOffice. They use only standard functions (MAXIFS needs Excel 2019 or 365), but the file has not been opened in Microsoft Excel during testing.
- **Legal.** RUBS rules differ by US state and city (disclosure, caps, admin fees). This is a calculation tool, not legal advice.

Synthetic data only.
