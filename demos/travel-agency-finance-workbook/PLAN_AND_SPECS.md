# travel-agency-finance-workbook: plan and specs (no build yet)

Status: DRAFT for Yannick's approval. Nothing is built; every number below is a **target**, not a measurement.
Matches Upwork job 2115603361810026804, "Excel Financial Management System for a B2B Travel Agency" (RT Vacations Balkan, Sarajevo; fixed $300 / about €300; expert; posted 29 Oct 2026 01:35 Geneva).
Portfolio build with fictional sample data, not client work. It's shaped like the job so it can be shown as the "example of relevant work" the post asks for, and it reuses the input-spec / exception-flag / closing-check approach from the existing Power Query month-end reconciliation piece.

## 1. Goal and scope
| Item | In scope | Out of scope |
|---|---|---|
| Workbook | One `.xlsx`, Excel 365 / 2021, no macros (so it opens anywhere and nothing gets blocked by security settings) | VBA, Power BI, cloud database |
| Data | Fictional Balkan agency: ~40 bookings (FIT + group), 12 customers (agencies), 15 suppliers, 3 salespeople, 3 months | Any real company's data |
| Currencies | EUR, BAM, USD with a rates table by date; reporting in a chosen base currency | Live FX feeds (noted as an optional extra) |
| Accounting | Management view: revenue, direct cost, gross profit, opex, net operating profit, AR, AP | Statutory bookkeeping, VAT returns, tax filing |

## 2. Requirements
Sources: **JP** = job post, **PS** = professional / common-sense standard.
| ID | Src | Requirement |
|---|---|---|
| R01 | JP | Booking register: FIT/group, travel dates, customer, destination, status |
| R02 | JP | Per-booking revenue, direct cost, gross profit, margin % |
| R03 | JP | Operating expenses and other transactions log |
| R04 | JP | Customer invoices with outstanding balances |
| R05 | JP | Supplier bills with amounts payable |
| R06 | JP | Full and partial payments (in and out), balances and payment dates |
| R07 | JP | EUR / BAM / USD, configurable rates, reporting in a selected base currency |
| R08 | JP | Dashboard: monthly revenue, GP, opex, net operating profit, receivables, payables |
| R09 | JP | Reports by month, destination, customer, salesperson |
| R10 | JP | Data validation, clear input cells, protected formulas, daily-use instructions |
| R11 | JP | Fully editable, owned by the client; sample transactions included |
| R12 | JP | Tested: partial payments, multi-currency, booking profitability |
| R13 | JP | Short handover guide |
| R14 | PS | BAM fixed peg to EUR (1 EUR = 1.95583 BAM) pre-set; USD rate by date |
| R15 | PS | Control checks: invoices tie to bookings, payments never exceed invoice, AR/AP reconcile to the ledgers, flagged on a Checks sheet |
| R16 | PS | Aging buckets for AR and AP (0–30, 31–60, 61–90, 90+) |
| R17 | PS | One row per record, Excel Tables (structured references) so new rows extend formulas automatically |
| R18 | PS | Cancelled bookings excluded from revenue but kept for the record; unique booking / invoice IDs enforced |
| R19 | PS | Performance: stays responsive at 2,000 bookings / 5,000 payments |
| R20 | PS | Clean when cleared: a blank copy with no sample data for go-live |

## 3. Test, measurement and evaluation plan
Test sheet `Tests` inside a copy of the workbook plus a Python reference (`openpyxl` + `pandas`) that recomputes every figure independently from the raw tables.
| Test | Method | Pass threshold | Req |
|---|---|---|---|
| Profitability | Python recomputes revenue, cost, GP, margin per booking in base currency | 40/40 bookings match to 0.01 | R02, R07 |
| Partial payments | 10 scripted cases: 1 payment, 3 partials, overpayment attempt, payment in a different currency, refund | 10/10 balances correct; overpayment blocked or flagged | R06, R12, R15 |
| Multi-currency | Switch base currency EUR to BAM to USD; totals equal Python within 0.01 | 3/3 | R07, R14 |
| Dashboard ties | Every dashboard number equals its ledger total (Checks sheet) | All checks show OK | R08, R15 |
| Reports | Pivot / SUMIFS by month, destination, customer, salesperson sum to the dashboard totals | 4/4 tie | R09 |
| Aging | 12 seeded invoices/bills in known buckets | 12/12 in the right bucket | R16 |
| Validation | Try 8 bad inputs (unknown customer, text in amount, end date before start, duplicate ID, bad currency, etc.) | 8/8 rejected or flagged | R10, R18 |
| Protection | Formula cells locked, input cells unlocked, sheet protection without password by default (client sets one) | Manual check pass | R10, R11 |
| Extensibility | Add 5 bookings + payments by typing in the next row | All formulas, reports and dashboard update with no edits | R17 |
| Scale | Fill 2,000 bookings / 5,000 payments with generated data | Recalc ≤ 3 s on a normal laptop | R19 |
| Blank copy | Clear-data copy opens with zero errors (#REF!, #N/A, #DIV/0!) | 0 errors | R20 |
| Handover | Someone other than the builder (Yannick) records a booking, invoice, partial payment and supplier bill using only the guide | 4/4 tasks done unaided | R13 |
- Reporting: `TEST_REPORT.md` with each test, n, pass/fail and screenshots of the Checks sheet. Missed thresholds are reported as missed. Run the realism-gate-review skill (messy inputs: mixed date formats, booking paid in 2 currencies, supplier bill in USD for a EUR booking) and a ponytail review before Yannick tests.

## 4. Stack and why
| Part | Choice | Why |
|---|---|---|
| Workbook | Excel Tables + SUMIFS / XLOOKUP / LET, data validation lists | The client asked for Excel, editable, no black box; works without macros |
| FX | Rates table (date, currency, rate to EUR) + lookup of the rate on or before the transaction date | Configurable, auditable, handles BAM peg |
| Reports | PivotTables on the ledgers + formula dashboard with a base-currency selector | Pivots for ad-hoc slicing, formulas for a stable dashboard |
| Build / test | Python (`openpyxl`, `pandas`) to generate sample data and independently verify every total | Proves the numbers instead of eyeballing them |
| Guide | 2-page PDF + an Instructions sheet in the workbook | Daily-use help sits where they work |

## 5. Build steps and time
| # | Step | Est. |
|---|---|---|
| 1 | Data model: Settings, Rates, Customers, Suppliers, Bookings, Booking costs, Invoices, Bills, Payments, Expenses | 1 h |
| 2 | Formulas: profitability, balances, FX conversion, aging, IDs | 2 h |
| 3 | Dashboard + reports + base-currency switch | 1.5 h |
| 4 | Validation, protection, Instructions sheet, Checks sheet | 1 h |
| 5 | Sample data generator + Python verifier + tests | 1.5 h |
| 6 | Guide PDF, blank copy, screenshots, realism gate and review | 1 h |
| | **Total** | **≈ 8 h** |

## 6. Accounts and keys Yannick sets up
None required. Excel on his machine (or free Excel for the web) to test the file. Optional: a GitHub repo `travel-agency-finance-workbook` if he wants it beside the other demos.

## 7. Portfolio packaging
- The workbook (sample data) + blank copy, 3 dashboard screenshots, and `TEST_REPORT.md`.
- A one-page case study PDF for `/workspace/proposals/attachments/` ("Travel agency finance workbook: bookings to dashboard, multi-currency, tested"), labelled portfolio build with fictional data.
- Reusable later for other Excel finance-system posts (tour operators, event agencies, small B2B services).

## 8. Risks and open questions
| Risk / question | Mitigation / ask |
|---|---|
| Budget $300 fixed vs full scope (about 8 h for the demo, more for client tweaks) | The demo does most of the work up front; bid $300 for a first version and name extras (live FX, custom invoice printout) as a later milestone |
| Client: first job post, 0 hires, payment method **not verified** | Don't start until the milestone is funded; mention in internal notes only |
| 15–20 proposals already | Demo is the differentiator; quick build (≈ 8 h) |
| Post asks "have you built these for travel agencies?" | Answer truthfully: point to the demo built for this case + the reconciliation work; never claim a past travel client |
| **Open:** build now (recommended, ≈ 8 h) or skip because of the unverified client? | Yannick to choose |
