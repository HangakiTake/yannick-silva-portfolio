# RUBS utility billing workbook

A ratio-utility-billing workbook for several properties. Water, sewer, trash, gas, and any other utility are split to units with formulas a property manager can read. `rubs.py` is a separate cent-level check of the same rules.

The properties, stays, and bills are **synthetic**. They are not a real community.

## What you get

- `RUBS_Billing_Demo.xlsx` — the workbook. Yellow cells are inputs. Gray cells are formulas.
- `rubs.py` — the reference allocator and the synthetic dataset.
- `build_workbook.py` — rebuilds the workbook from that dataset.
- `tests/` — pytest, including a LibreOffice recalc of the workbook.

## How a bill is split

1. A negative amount, or a period that runs backwards or is longer than 366 days, is not allocated. It is listed on Exceptions.
2. The amount is converted to cents.
3. The owner-paid percent is taken off the top. Enter **15** for 15%, not 0.15.
4. The rest is split by weight. Odd cents use largest remainder. If two buckets tie, the lower key wins (`HC-01` before `HC-02`; within one unit the `|O` vacancy bucket is ahead of `|T`).
5. A unit discount is taken from that unit's tenant share and added to Owner. Enter **10** for 10%.
6. If nobody has weight, the remaining pool goes to Owner and Exceptions says so.

Weights:

- `occupant_days` — occupants times inclusive days inside the service period. A vacant unit does not get a tenant share. Days with nobody home are absorbed by the other units unless you set partial vacancy to `owner` and a vacant equivalent.
- `per_unit` — one weight per occupied day. With partial vacancy `owner`, the vacant days in that unit go to Owner.
- `square_footage` — square feet times occupied days.

Days are inclusive. 1 March through 31 March is 31 days. A move-in on 16 March counts 16 days. A blank move-out means the household is still there. A unit marked vacant is not billed as occupied, even if an occupancy row exists; that conflict is flagged.

Sample bill amounts are stored as cents/100 so this file is exact. Type a normal dollar amount over them for a new month.

## The sample

Harbor Court has 4 units, Maple Terrace 8, Cedar Station 12.

- HC-02 moves in on 16 March.
- HC-03 is vacant and also has an occupancy row, which is flagged and ignored for the charge.
- HC-04 has a 10% discount and is excluded from gas.
- Harbor Court trash is 15% owner-paid, then split per occupied day, with vacant days to Owner.
- Maple Terrace gas uses square footage. MT-02 has a move-out on 12 March and a move-in on 20 March.
- Cedar Station has an extra electric bill, split by occupant-days. It is not a common-area deduction.
- Harbor Court water has a February bill that ends on 26 February, so 27–28 February show up as a gap.
- `CS-E-CREDIT` is a negative amount and is not allocated.

## Running it

From this folder, with Python 3.11+ and LibreOffice Calc:

```bash
pip install -r requirements.txt
python build_workbook.py
python rubs.py reconcile
python rubs.py explain HC-W-2026-03 HC-04
pytest
```

`pytest` needs LibreOffice on the path (`soffice`). The workbook tests load the file headlessly, recalculate, and compare every in-scope line to `rubs.py`.

Capacity without editing a formula: 8 properties, 30 units, 60 occupancy rows, 32 bills, 48 rules. The readable list on Allocation shows the first 400 in-scope lines. Reconciliation and the statements sum the whole engine, so a line past that list is still in the totals.

## Caveats

RUBS rules vary by US state and by local law. Some places limit which utilities can be billed this way, cap fees, require submetering, or prescribe the factor. **This is a calculation tool, not legal advice**, and the sample is not a real jurisdiction.

Overlapping occupancy rows are flagged, not repaired. Until the dates are fixed, per-unit and square-footage day counts add the overlapping stays and cap them at the length of the period, so a partial overlap can overstate occupied days. Occupant-day weights add the overlapping people as well.

A credit or a negative bill is stopped and listed. It is not spread.

## What was tested, and what was not

Tested in `pytest`:

- Reconciliation to the cent for every included bill (tenant charges + owner share = the bill).
- Partial-month move-ins and move-outs, vacancies, excluded utilities, discounts, owner percent, square footage, and largest-remainder ties.
- The three seeded problems: negative bill, occupancy on a vacant unit, and the February service-period gap.
- LibreOffice recalculation of the workbook against `rubs.py`, including Manual_Check for every included bill.
- Changing occupants, the owner percent, and a typed bill amount, with no formula edit. The new results still match `rubs.py`.

Not tested:

- Excel 365, Excel for Mac, or Excel Online specifically. Recalculation was LibreOffice.
- Any legal review, tenant portal, late fee, tax, payment, meter read, or common-area subtraction before the ratio.
- Rate changes inside one service period, or a bill that is not one contiguous date range.
- Repairing overlapping occupancy. The sheet only flags it.
- Allocating credits. A negative amount is rejected.
