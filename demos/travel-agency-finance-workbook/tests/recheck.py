"""Independent recheck: reads ONLY the typed inputs from the workbook, recomputes every
figure in plain Python (no workbook formulas reused), and compares with the values the
spreadsheet engine calculated (LibreOffice headless recalculation of the same file).

Usage: python3 tests/recheck.py <workbook.xlsx> [--base EUR|BAM|USD]
Exit code 0 = every compared figure within tolerance."""
import sys, os, subprocess, tempfile, shutil, atexit, datetime as dt, bisect, json
from collections import defaultdict
import openpyxl

TOL = 0.01
HERE = os.path.dirname(os.path.abspath(__file__))


def recalc(path):
    out = tempfile.mkdtemp(prefix="recalc_"); atexit.register(shutil.rmtree, out, True)
    subprocess.run(["soffice", "--headless", "--calc", "--convert-to", "xlsx:Calc MS Excel 2007 XML", "--outdir", out, path],
                   check=True, capture_output=True, timeout=600)
    return os.path.join(out, os.path.basename(path))


def table_rows(ws, name):
    t = ws.tables[name]; (c1, r1), (c2, r2) = openpyxl.utils.cell.range_boundaries(t.ref)[:2], openpyxl.utils.cell.range_boundaries(t.ref)[2:]
    rows = list(ws.iter_rows(min_row=r1, max_row=r2, min_col=c1, max_col=c2, values_only=True))
    hdr = rows[0]
    return [dict(zip(hdr, r)) for r in rows[1:]]


def d_(x):
    return x.date() if isinstance(x, dt.datetime) else x


class Model:
    def __init__(self, src):
        wb = openpyxl.load_workbook(src)  # formulas, not values: only typed inputs are used
        st = wb["Settings"]
        self.base, self.asof, self.first, self.peg = st["B3"].value, d_(st["B4"].value), d_(st["B5"].value), st["B6"].value
        g = lambda sh, t: table_rows(wb[sh], t)
        rates = sorted((d_(r["Date"]), r["USD_per_EUR"]) for r in g("Rates", "Rates") if r["Date"])
        self.rd = [r[0] for r in rates]; self.rv = [r[1] for r in rates]
        keep = lambda rows, k: [r for r in rows if r.get(k)]
        self.bk = keep(g("Bookings", "Bookings"), "BookingID"); self.inv = keep(g("Invoices", "Invoices"), "InvoiceID")
        self.bills = keep(g("Bills", "Bills"), "BillID"); self.pay = keep(g("Payments", "Payments"), "PayID")
        self.exp = keep(g("Expenses", "Expenses"), "ExpID")
        self.compute()

    def rate(self, ccy, d):
        if ccy == "EUR": return 1.0
        if ccy == "BAM": return self.peg
        if ccy == "USD":
            i = bisect.bisect_right(self.rd, d_(d)) - 1
            if i < 0: raise ValueError("no rate")
            return self.rv[i]
        raise ValueError("bad ccy")

    def conv(self, amt, frm, to, d):
        return amt / self.rate(frm, d) * self.rate(to, d)

    def compute(self):
        B = self.base; A = self.asof
        start = {b["BookingID"]: d_(b["StartDate"]) for b in self.bk}
        status = {b["BookingID"]: b["Status"] for b in self.bk}
        self.bill_cost = defaultdict(float)
        for x in self.bills: self.bill_cost[x["BookingID"]] += self.conv(x["Amount"], x["Ccy"], B, x["BillDate"])
        refccy = {i["InvoiceID"]: i["Ccy"] for i in self.inv}; refccy.update({b["BillID"]: b["Ccy"] for b in self.bills})
        self.paid = defaultdict(float); self.pay_asof = {"In": [], "Out": []}
        for p in self.pay:
            rc = refccy.get(p["Ref"])
            if rc is None: continue
            amt = self.conv(p["Amount"], p["Ccy"], rc, p["PayDate"])
            self.paid[p["Ref"]] += amt
            self.pay_asof[p["Direction"]].append((d_(p["PayDate"]), self.conv(amt, rc, B, A)))
        self.booking = {}
        for b in self.bk:
            canc = b["Status"] == "Cancelled"
            rev = 0.0 if canc else self.conv(b["SellPrice"], b["SellCcy"], B, b["StartDate"])
            cost = 0.0 if canc else self.bill_cost[b["BookingID"]]
            self.booking[b["BookingID"]] = dict(rev=rev, cost=cost, gp=rev - cost, margin=(rev - cost) / rev if rev else None,
                                                month=start[b["BookingID"]].replace(day=1), b=b)
        bucket = lambda bal, age: "Paid" if abs(bal) < 0.005 else "0-30" if age <= 30 else "31-60" if age <= 60 else "61-90" if age <= 90 else "90+"
        self.invc = {}
        for i in self.inv:
            bal = i["Amount"] - self.paid[i["InvoiceID"]]
            self.invc[i["InvoiceID"]] = dict(bal=bal, bal_base=self.conv(bal, i["Ccy"], B, A), due=d_(i["DueDate"]), amt_asof=self.conv(i["Amount"], i["Ccy"], B, A),
                                             bucket=bucket(bal, (A - d_(i["InvDate"])).days), date=d_(i["InvDate"]),
                                             amt_base=self.conv(i["Amount"], i["Ccy"], B, start[i["BookingID"]]))
        self.billc = {}
        for x in self.bills:
            bal = x["Amount"] - self.paid[x["BillID"]]
            self.billc[x["BillID"]] = dict(bal=bal, bal_base=self.conv(bal, x["Ccy"], B, A), due=d_(x["DueDate"]), amt_asof=self.conv(x["Amount"], x["Ccy"], B, A),
                                           bucket=bucket(bal, (A - d_(x["BillDate"])).days), date=d_(x["BillDate"]))
        self.opex = defaultdict(float)
        for e in self.exp: self.opex[d_(e["ExpDate"]).replace(day=1)] += self.conv(e["Amount"], e["Ccy"], B, e["ExpDate"])
        # dashboard months
        self.months = []
        y, m = self.first.year, self.first.month
        for k in range(12):
            mm = dt.date(y + (m - 1 + k) // 12, (m - 1 + k) % 12 + 1, 1)
            nxt = dt.date(mm.year + mm.month // 12, mm.month % 12 + 1, 1); eom = nxt - dt.timedelta(days=1)
            rev = sum(v["rev"] for v in self.booking.values() if v["month"] == mm)
            cost = sum(v["cost"] for v in self.booking.values() if v["month"] == mm)
            ar = sum(v["amt_asof"] for v in self.invc.values() if v["date"] <= eom) - sum(a for d, a in self.pay_asof["In"] if d <= eom)
            ap = sum(v["amt_asof"] for v in self.billc.values() if v["date"] <= eom) - sum(a for d, a in self.pay_asof["Out"] if d <= eom)
            n = sum(1 for v in self.booking.values() if v["month"] == mm and v["b"]["Status"] != "Cancelled")
            self.months.append(dict(month=mm, rev=rev, cost=cost, gp=rev - cost, opex=self.opex[mm], nop=rev - cost - self.opex[mm], ar=ar, ap=ap, n=n))
        self.group = {}
        for key, col in [("dest", "Destination"), ("cust", "Customer"), ("sales", "Salesperson")]:
            g = defaultdict(lambda: [0, 0.0, 0.0])
            for v in self.booking.values():
                k = v["b"][col]; g[k][1] += v["rev"]; g[k][2] += v["gp"]
                if v["b"]["Status"] != "Cancelled": g[k][0] += 1
            self.group[key] = dict(g)


def close(a, b, tol=TOL):
    try: return abs(float(a or 0) - float(b or 0)) <= tol
    except (TypeError, ValueError): return False


def compare(src, calc_path=None):
    m = Model(src); calc_path = calc_path or recalc(src)
    wb = openpyxl.load_workbook(calc_path, data_only=True)
    res = defaultdict(lambda: [0, 0]); bad = []
    def chk(group, label, got, exp):
        ok = close(got, exp); res[group][0] += ok; res[group][1] += 1
        if not ok: bad.append((group, label, got, exp))
    for r in table_rows(wb["Bookings"], "Bookings"):
        if not r["BookingID"]: continue
        e = m.booking[r["BookingID"]]
        chk("booking_profit", r["BookingID"] + " rev", r["RevenueBase"], e["rev"]); chk("booking_profit", r["BookingID"] + " cost", r["CostBase"], e["cost"])
        chk("booking_profit", r["BookingID"] + " gp", r["GrossProfit"], e["gp"])
        if e["margin"] is not None: chk("booking_profit", r["BookingID"] + " margin", r["MarginPct"], e["margin"])
    for r in table_rows(wb["Invoices"], "Invoices"):
        if not r["InvoiceID"]: continue
        e = m.invc[r["InvoiceID"]]
        chk("invoices", r["InvoiceID"] + " bal", r["Balance"], e["bal"]); chk("invoices", r["InvoiceID"] + " balbase", r["BalanceBase"], e["bal_base"])
        res["aging"][1] += 1; res["aging"][0] += r["Bucket"] == e["bucket"]
        if r["Bucket"] != e["bucket"]: bad.append(("aging", r["InvoiceID"], r["Bucket"], e["bucket"]))
    for r in table_rows(wb["Bills"], "Bills"):
        if not r["BillID"]: continue
        e = m.billc[r["BillID"]]
        chk("bills", r["BillID"] + " bal", r["Balance"], e["bal"]); chk("bills", r["BillID"] + " balbase", r["BalanceBase"], e["bal_base"])
        res["aging"][1] += 1; res["aging"][0] += r["Bucket"] == e["bucket"]
    d = wb["Dashboard"]
    for i, mm in enumerate(m.months):
        r = 5 + i
        for col, k in zip("BCDFGHIJ", ["rev", "cost", "gp", "opex", "nop", "ar", "ap", "n"]):
            if mm["month"] > m.asof:  # future months are left blank on purpose
                got = d[f"{col}{r}"].value; ok = got in (None, ""); res["dashboard"][0] += ok; res["dashboard"][1] += 1
                if not ok: bad.append(("dashboard", f"{mm['month']:%Y-%m} {k} should be blank", got, ""))
            else:
                chk("dashboard", f"{mm['month']:%Y-%m} {k}", d[f"{col}{r}"].value, mm[k])
    chk("dashboard", "AR now", d["B20"].value, sum(v["bal_base"] for v in m.invc.values()))
    chk("dashboard", "AP now", d["B21"].value, sum(v["bal_base"] for v in m.billc.values()))
    od = lambda c: sum(v["bal_base"] for v in c.values() if v["due"] < m.asof and v["bal_base"] > 0)
    chk("dashboard", "AR overdue", d["B22"].value, od(m.invc)); chk("dashboard", "AP overdue", d["B23"].value, od(m.billc))
    chk("dashboard", "cancelled", d["B24"].value, sum(1 for b in m.bk if b["Status"] == "Cancelled"))
    rp = wb["Reports"]
    for key, c0, n in [("dest", 7, 20), ("cust", 13, 40), ("sales", 19, 15)]:
        for i in range(n):
            k = rp.cell(4 + i, c0).value
            if not k: continue
            e = m.group[key].get(k, [0, 0.0, 0.0])
            chk("reports", f"{key}:{k} n", rp.cell(4 + i, c0 + 1).value, e[0]); chk("reports", f"{key}:{k} rev", rp.cell(4 + i, c0 + 2).value, e[1])
            chk("reports", f"{key}:{k} gp", rp.cell(4 + i, c0 + 3).value, e[2])
        tot = rp.cell(4 + n, c0 + 2).value
        chk("reports", f"{key} total", tot, sum(v["rev"] for v in m.booking.values()))
    ck = wb["Checks"]
    overall = ck["B2"].value
    return dict(model=m, calc=wb, results={k: tuple(v) for k, v in res.items()}, mismatches=bad, checks_overall=overall, calc_path=calc_path)


if __name__ == "__main__":
    out = compare(sys.argv[1])
    tot = sum(v[1] for v in out["results"].values()); okn = sum(v[0] for v in out["results"].values())
    for k, v in out["results"].items(): print(f"{k:16s} {v[0]}/{v[1]}")
    print(f"TOTAL {okn}/{tot} figures match within {TOL}; Checks sheet: {out['checks_overall']}")
    for b in out["mismatches"][:20]: print("MISMATCH", b)
    sys.exit(0 if okn == tot else 1)
