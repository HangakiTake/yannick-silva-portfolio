"""Runs every test in PLAN_AND_SPECS.md section 3 and writes TEST_REPORT.md + tests/results.json.
Usage: python3 tests/run_tests.py   (needs LibreOffice for recalculation)"""
import os, sys, time, json, zipfile, re, copy, datetime as dt
import openpyxl
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src")); sys.path.insert(0, HERE)
import sample_data as S, build_workbook as W, recheck as R
OUT = os.path.join(HERE, "out"); os.makedirs(OUT, exist_ok=True)
D = dt.date
results = []

def record(tid, name, req, n_pass, n, threshold, detail, passed=None, manual=False):
    passed = (n_pass == n) if passed is None else passed
    results.append(dict(id=tid, test=name, req=req, n_pass=n_pass, n=n, threshold=threshold, detail=detail,
                        result=("MANUAL (pending)" if manual else "PASS" if passed else "FAIL")))
    print(f"{tid} {name}: {n_pass}/{n} -> {results[-1]['result']}  {detail}")

def rows(wb, sheet, table):
    return {r[list(r)[0]]: r for r in R.table_rows(wb[sheet], table) if r[list(r)[0]]}

# ---- shipped sample
sample = os.path.join(ROOT, "TravelAgency_Finance_Workbook.xlsx")
data = S.generate(); cases, aging = S.seeded_cases(data); W.build(sample, data)
W.build(os.path.join(ROOT, "TravelAgency_Finance_Workbook_BLANK.xlsx"), blank=True)
base = R.compare(sample)
wb = base["calc"]; m = base["model"]
bk = rows(wb, "Bookings", "Bookings")
okb = sum(1 for b, r in bk.items() if all(R.close(r[c], m.booking[b][k]) for c, k in [("RevenueBase", "rev"), ("CostBase", "cost"), ("GrossProfit", "gp")])
          and (m.booking[b]["margin"] is None or R.close(r["MarginPct"], m.booking[b]["margin"], 0.0001)))
fit = sum(1 for r in bk.values() if r["Type"] == "FIT"); grp = len(bk) - fit; canc = sum(1 for r in bk.values() if r["Status"] == "Cancelled")
tot = sum(v[1] for v in base["results"].values()); okn = sum(v[0] for v in base["results"].values())
record("T01", "Profitability per booking (revenue, cost, GP, margin in base ccy)", "R01 R02 R07", okb, len(bk), "40/40 match to 0.01",
       f"{len(bk)} bookings ({fit} FIT, {grp} group, {canc} cancelled); whole-workbook recheck {okn}/{tot} figures")

# ---- partial payments: test copy with the overpayment case included
d2 = S.generate(); cases2, _ = S.seeded_cases(d2, include_over=True)
pp = os.path.join(OUT, "cases_with_overpayment.xlsx"); W.build(pp, d2)
c2 = R.compare(pp); wb2 = c2["calc"]; m2 = c2["model"]
inv2, bill2 = rows(wb2, "Invoices", "Invoices"), rows(wb2, "Bills", "Bills")
okc = 0; det = []
for name, ref, exp in cases2:
    got = (inv2.get(ref) or bill2.get(ref))["Balance"]
    if isinstance(exp, tuple):  # hand formula with the rate on the payment date (independent of workbook)
        kind = exp[0]
        if kind == "usd": exp_v = exp[1] - exp[2] / m2.rate("USD", exp[3])
        elif kind == "usdbill": exp_v = exp[1] - exp[2] * m2.rate("USD", exp[3])
        else: exp_v = exp[1] - exp[2] - exp[3] / S.BAM_PEG
    else: exp_v = exp
    ok = R.close(got, exp_v)
    if name.startswith("T3"):
        ok = ok and inv2[ref]["PayStatus"] == "OVERPAID" and "overpaid" in (inv2[ref]["Flag"] or "") and "ISSUE" in str(wb2["Checks"]["B2"].value)
    okc += ok; det.append(f"{name}: {got:.2f} vs {exp_v:.2f} {'ok' if ok else 'X'}")
record("T02", "Partial payments (10 scripted cases)", "R06 R12 R15", okc, len(cases2), "10/10; overpayment flagged",
       "; ".join(det))

# ---- multi-currency: rebuild with each base currency and recheck everything
mc = 0; det = []; revs = {}
for b in ["EUR", "BAM", "USD"]:
    p = os.path.join(OUT, f"base_{b}.xlsx"); W.build(p, data, base=b); c = R.compare(p)
    t = sum(v[1] for v in c["results"].values()); o = sum(v[0] for v in c["results"].values())
    revs[b] = c["calc"]["Dashboard"]["B17"].value
    ok = o == t and c["checks_overall"] == "ALL OK"; mc += ok; det.append(f"{b}: {o}/{t} figures, Checks {c['checks_overall']}, revenue {revs[b]:,.2f}")
peg_ok = R.close(revs["BAM"], revs["EUR"] * S.BAM_PEG)
record("T03", "Multi-currency base switch EUR/BAM/USD", "R07 R14", mc, 3, "3/3 within 0.01", "; ".join(det) + f"; BAM total = EUR x 1.95583: {peg_ok}",
       passed=(mc == 3 and peg_ok))

# ---- dashboard ties + reports
ck = wb["Checks"]; lines = [(ck[f"A{r}"].value, ck[f"D{r}"].value) for r in range(5, 24) if ck[f"A{r}"].value]
okk = sum(1 for _, v in lines if v == "OK")
record("T04", "Dashboard and ledgers tie (Checks sheet)", "R08 R15", okk, len(lines), "All checks OK", f"Checks!B2 = {ck['B2'].value}")
rep = [l for l in lines if l[0].startswith("Report by")]
dr = base["results"]["dashboard"]; rr = base["results"]["reports"]
record("T05", "Reports by month, destination, customer, salesperson tie to totals", "R09", sum(1 for _, v in rep if v == "OK"), 4, "4/4 tie",
       f"plus Python recheck of every report row {rr[0]}/{rr[1]} and dashboard cells {dr[0]}/{dr[1]}")

# ---- aging seeds
inv1, bill1 = rows(wb, "Invoices", "Invoices"), rows(wb, "Bills", "Bills")
oka = sum(1 for ref, b in aging if (inv1.get(ref) or bill1.get(ref))["Bucket"] == b)
record("T06", "Aging buckets (12 seeded invoices/bills)", "R16", oka, len(aging), "12/12 right bucket",
       f"all {base['results']['aging'][0]}/{base['results']['aging'][1]} items match the Python bucket")

# ---- validation: 8 bad inputs pasted in (bypassing Excel's typing validation) must be flagged
bad = dict(
    bookings=[["B-2001", "FIT", "C99", "Mostar", "Amra K.", D(2026, 9, 1), D(2026, 9, 10), D(2026, 9, 12), 2, "Confirmed", "EUR", 800],
              ["B-2002", "FIT", "C01", "Mostar", "Amra K.", D(2026, 9, 1), D(2026, 9, 10), D(2026, 9, 12), 2, "Confirmed", "EUR", "1.200,00"],
              ["B-2003", "FIT", "C01", "Mostar", "Amra K.", D(2026, 9, 1), D(2026, 9, 10), D(2026, 9, 8), 2, "Confirmed", "EUR", 800],
              ["B-1001", "FIT", "C01", "Mostar", "Amra K.", D(2026, 9, 1), D(2026, 9, 10), D(2026, 9, 12), 2, "Confirmed", "EUR", 800],
              ["B-2005", "FIT", "C01", "Mostar", "Amra K.", D(2026, 9, 1), D(2026, 9, 10), D(2026, 9, 12), 2, "Confirmed", "GBP", 800],
              ["B-2006", "FIT", "C01", "Mostar", "Amra K.", D(2026, 9, 1), "15.09.2026", D(2026, 9, 18), 2, "Confirmed", "EUR", 800]],
    payments=[["PAY-X1", D(2026, 9, 5), "In", "INV-9999", "EUR", 100, "Bank transfer", "bad ref"]],
    invoices=[["INV-X1", "B-9999", D(2026, 9, 5), D(2026, 10, 5), "EUR", 100]])
expect = [("Bookings", "B-2001", "unknown customer"), ("Bookings", "B-2002", "price not a number"), ("Bookings", "B-2003", "end before start"),
          ("Bookings", "B-1001", "duplicate ID"), ("Bookings", "B-2005", "bad currency"), ("Bookings", "B-2006", "date not a date"),
          ("Payments", "PAY-X1", "unknown invoice/bill"), ("Invoices", "INV-X1", "unknown booking")]
vp = os.path.join(OUT, "bad_inputs.xlsx"); W.build(vp, data, extra=bad); vwb = openpyxl.load_workbook(R.recalc(vp), data_only=True)
okv = 0; det = []
for sh, idv, txt in expect:
    flags = [r["Flag"] for r in R.table_rows(vwb[sh], sh) if r[list(r)[0]] == idv]
    hit = any(txt in str(f or "") for f in flags); okv += hit; det.append(f"{idv}->{'flagged' if hit else 'MISSED'} ({txt})")
src = openpyxl.load_workbook(sample); ndv = sum(len(src[s].data_validations.dataValidation) for s in ["Bookings", "Invoices", "Bills", "Payments", "Expenses", "Settings"])
record("T07", "Validation: 8 bad inputs flagged", "R10 R18", okv, 8, "8/8 rejected or flagged",
       "; ".join(det) + f"; Checks then reads '{vwb['Checks']['B2'].value}'; {ndv} typing rules (lists, dates, unique IDs, end>=start) also block these when typed in Excel")

# ---- protection (structure check; Excel click-test is manual)
prot = {s: src[s].protection.sheet for s in src.sheetnames}
want = ["Dashboard", "Reports", "Checks", "Settings", "Instructions"]
lock_ok = 0; lock_n = 0
for sh, tn in [("Bookings", "Bookings"), ("Invoices", "Invoices"), ("Bills", "Bills"), ("Payments", "Payments"), ("Expenses", "Expenses")]:
    ws = src[sh]
    for cell in ws[2]:
        if cell.value is None: continue
        lock_n += 1; isf = isinstance(cell.value, str) and cell.value.startswith("=")
        lock_ok += (cell.protection.locked == isf)
record("T08", "Protection: formulas locked, inputs unlocked, report sheets protected (no password)", "R10 R11",
       sum(prot[s] for s in want) + lock_ok, len(want) + lock_n, "Manual check pass",
       f"protected: {', '.join(s for s in want if prot[s])}; ledger cells with correct lock state {lock_ok}/{lock_n}; data sheets left unprotected so tables can grow (Excel limit)",
       passed=None, manual=True)

# ---- extensibility: 5 new bookings + invoices + payments typed below the tables
xb = [[f"B-30{i}", "FIT", "C02", "Ohrid", "Dino H.", D(2026, 9, 1), D(2026, 10, 5 + i), D(2026, 10, 9 + i), 2, "Confirmed", "EUR", 1000 + i] for i in range(5)]
xi = [[f"INV-80{i}", f"B-30{i}", D(2026, 9, 2), D(2026, 10, 2), "EUR", 1000 + i] for i in range(5)]
xp = [[f"PAY-80{i}", D(2026, 9, 20), "In", f"INV-80{i}", "EUR", 400, "Bank transfer", "new row"] for i in range(5)]
xpth = os.path.join(OUT, "extended.xlsx"); W.build(xpth, data, extra=dict(bookings=xb, invoices=xi, payments=xp)); ce = R.compare(xpth)
t = sum(v[1] for v in ce["results"].values()); o = sum(v[0] for v in ce["results"].values())
oct_delta = ce["calc"]["Dashboard"]["B7"].value - wb["Dashboard"]["B7"].value
ar_delta = ce["calc"]["Dashboard"]["B20"].value - wb["Dashboard"]["B20"].value
with zipfile.ZipFile(sample) as z:
    xml = "".join(z.read(n).decode() for n in z.namelist() if n.startswith("xl/tables/"))
ncalc = xml.count("<calculatedColumnFormula")
ncalc_exp = 37  # Rates 1 + Bookings 9 + Bills 9 + Invoices 11 + Payments 4 + Expenses 3
ok = o == t and R.close(oct_delta, 5010) and R.close(ar_delta, 5010 - 2000) and ce["checks_overall"] == "ALL OK" and ncalc == ncalc_exp
record("T09", "Extensibility: add 5 bookings + invoices + payments", "R17", int(ok), 1, "Everything updates with no edits",
       f"Oct revenue +{oct_delta:,.2f} (expected +5,010.00), AR +{ar_delta:,.2f} (expected +3,010.00); recheck {o}/{t}; {ncalc}/{ncalc_exp} table calculated-column formulas stored so Excel auto-fills new rows (confirm by typing in Excel)", passed=ok)

# ---- scale
big = S.generate(n_bookings=2000, seed=11, start_id=100001, months=12)
while len(big["payments"]) < 5000:  # top up with small partial payments on open invoices
    i = big["invoices"][len(big["payments"]) % len(big["invoices"])]
    big["payments"].append([f"PAY-T{len(big['payments'])}", min(i[2] + dt.timedelta(days=2), S.ASOF), "In", i[0], i[4], 1.0, "Bank transfer", "scale top-up"])
bp = os.path.join(OUT, "scale_2000.xlsx"); W.build(bp, big)
t0 = time.time(); R.recalc(sample); startup = time.time() - t0
t0 = time.time(); bcalc = R.recalc(bp); secs = time.time() - t0
cb = R.compare(bp, bcalc); t = sum(v[1] for v in cb["results"].values()); o = sum(v[0] for v in cb["results"].values())
record("T10", "Scale: 2,000 bookings / 5,000+ payments", "R19", int(secs <= 3 and o == t), 1, "Recalc <= 3 s",
       f"{len(big['bookings'])} bookings, {len(big['payments'])} payments, {len(big['invoices'])} invoices, {len(big['bills'])} bills; full open+recalc+save in LibreOffice headless {secs:.1f} s on this server (the 40-booking sample takes {startup:.1f} s, so about {secs-startup:.1f} s is calculation); Excel not available here to time; recheck {o}/{t}",
       passed=(secs <= 3 and o == t))

# ---- blank copy
blank = os.path.join(ROOT, "TravelAgency_Finance_Workbook_BLANK.xlsx"); bwb = openpyxl.load_workbook(R.recalc(blank), data_only=True)
errs = [(ws.title, c.coordinate, c.value) for ws in bwb.worksheets for row in ws.iter_rows() for c in row
        if isinstance(c.value, str) and re.match(r"^#(REF!|N/A|DIV/0!|VALUE!|NAME\?|NUM!|NULL!)", c.value)]
nbk = len([r for r in R.table_rows(bwb["Bookings"], "Bookings") if r["BookingID"]])
record("T11", "Blank copy opens with 0 errors", "R20", int(not errs), 1, "0 errors",
       f"{len(errs)} error cells; {nbk} sample bookings left; Checks: {bwb['Checks']['B2'].value}" + (f"; first: {errs[:3]}" if errs else ""), passed=not errs)

record("T12", "Handover: someone else records booking, invoice, partial payment, bill using only the guide", "R13", 0, 4,
       "4/4 tasks unaided", "Not run yet: needs Yannick (or another person) in Excel", manual=True)

json.dump(results, open(os.path.join(HERE, "results.json"), "w"), indent=1, default=str)
L = ["# Test report (generated by tests/run_tests.py)\n", f"Run {dt.date.today()}; recalculated with LibreOffice headless, rechecked by tests/recheck.py from typed inputs only.\n",
     "| Test | Requirements | Result | Score | Threshold | Detail |", "|---|---|---|---|---|---|"]
L += [f"| {t['id']} {t['test']} | {t['req']} | **{t['result']}** | {t['n_pass']}/{t['n']} | {t['threshold']} | {t['detail'].replace('|', '/')} |" for t in results]
open(os.path.join(ROOT, "TEST_REPORT.md"), "w").write("\n".join(L) + "\n")
print("written results.json and TEST_REPORT.md")
