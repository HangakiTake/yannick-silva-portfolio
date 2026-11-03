# Realism gate review (buyer: agency finance manager, burned by Excel templates)

| # | Area | Result | Evidence or gap |
|---|---|---|---|
| 1 | Data realism | FAIL (portfolio) | Generated, fictional data only. The messy inputs tested were 8 bad entries (T07), an overpayment, a refund, FX partials, cancellations and duplicate IDs. Not tested: a real agency export or locale decimal commas. |
| 2 | Grounding | N/A to PASS | No extraction is involved. Every figure traces to a typed row, and the Flag columns name the faulty row. |
| 3 | Evaluation | PASS | The expected values are recomputed independently in Python from the inputs: 706/706 figures, 12 tests with denominators, and the T10 fail is reported. |
| 4 | Failure modes | PASS | Checks sheet with 19 checks. Overpayment and duplicate IDs are flagged, and running balances are reconciled. |
| 5 | Integration | PARTIAL | The workbook is the system of record. There is no accounting or ERP link and no live FX feed (stated). |
| 6 | Security | PARTIAL | Protection without a password, by design, so the client owns the file. There is no audit log, which Excel can't enforce. |
| 7 | Cost and latency | FAIL (stated) | Recalculation takes 11.9 s at 2,000 bookings in LibreOffice, against a target of 3 s or less. Not timed in Excel. |
| 8 | Honest claims | PASS | README lists each fail and partial beside its claim and labels the data as fictional. |

Ship rule (portfolio): section 8 passes and the fails are listed, so it can ship.

## Fixes
- **Should-fix, done:** the sample overdue share was 89%, which looked unrealistic. Payment behaviour was reworked; the share is still high and is stated in the README caveats.
- **Should-fix, done:** the chart legend was cropped. It now sits at the bottom.
- **Later:** time the scale test in desktop Excel, and run the T12 handover test with a real person.
