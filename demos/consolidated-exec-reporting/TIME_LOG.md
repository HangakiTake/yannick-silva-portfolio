# Time log: plan vs actual

| Step | Plan | Actual |
|---|---|---|
| 1. Synthetic data + answer key | 1.5 h | about 15 min |
| 2. Power Query M + Python mirror | 2 h | about 15 min |
| 3. Workbook (checks, exceptions, dashboard) | 1 h | (in 4) |
| 4. Tests | 1 h | about 30 min combined for 3–5 |
| 5. Docs (README, spec, templates, change mgmt, handover) | 1 h | (in 4) |
| 6. Realism gate + ponytail loops + fixes | 1.5 h | about 30 min |
| **Total** | **8 h** | **about 1.5 h of agent time** |

How this was measured: rough, from the box clock and `.timelog`. The `.timelog` timestamps aren't reliable: the session was compacted midway, and later entries don't line up with the earlier ones. Read the actual column as an approximation, not a measurement.

The plan's hours assume a person working in desktop Excel. Not yet spent: the one-time setup and verification in Excel (EXCEL_VERIFICATION.md), estimated at **1–2 h for Yannick**, with more if the M needs syntax fixes. Agent time isn't a good predictor of human hours for the same job.
