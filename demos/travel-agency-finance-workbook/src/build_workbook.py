"""Builds the travel agency finance workbook (no macros). Usage: python3 src/build_workbook.py"""
import sys, os, datetime as dt
from openpyxl import Workbook
from openpyxl.worksheet.table import Table, TableStyleInfo, TableColumn, TableFormula
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.styles import Font, PatternFill, Alignment, Protection, Border, Side
from openpyxl.formatting.rule import FormulaRule, CellIsRule
from openpyxl.chart import BarChart, Reference
from openpyxl.workbook.properties import CalcProperties
sys.path.insert(0, os.path.dirname(__file__))
import sample_data as S

INPUT = PatternFill("solid", fgColor="FFF8E1")   # pale yellow = type here
CALC = PatternFill("solid", fgColor="ECEFF1")    # grey = formula, locked
HEAD = PatternFill("solid", fgColor="1F3A5F")
BOLD = Font(bold=True); WH = Font(bold=True, color="FFFFFF")
UNLOCK = Protection(locked=False); LOCK = Protection(locked=True)
NUM = '#,##0.00'; DATE = 'yyyy-mm-dd'

def RATE(c, d):
    return (f'_xlfn.SWITCH({c},"EUR",1,"BAM",BAMPeg,"USD",'
            f'_xlfn.XLOOKUP({d},Rates[Date],Rates[USD_per_EUR],NA(),-1),NA())')

def ref(t, c): return f"{t}[[#This Row],[{c}]]"


def add_table(ws, name, inputs, calcs, rows, fmts=None, widths=None, row0=1):
    """inputs: list of col names; calcs: list of (col, formula). rows: list of input value lists."""
    if name != "Rates":  # blank rows stay blank instead of showing #N/A
        k0 = ref(name, inputs[0])
        calcs = [(c, f if c == "Flag" else f'IF({k0}="","",{f})') for c, f in calcs]
    cols = inputs + [c for c, _ in calcs]
    for j, c in enumerate(cols, 1):
        x = ws.cell(row0, j, c); x.font = WH; x.fill = HEAD; x.alignment = Alignment(wrap_text=True)
    n = max(1, len(rows))
    for i in range(n):
        r = row0 + 1 + i
        vals = rows[i] if rows else [None] * len(inputs)
        for j, v in enumerate(vals, 1):
            x = ws.cell(r, j, v); x.fill = INPUT; x.protection = UNLOCK
        for k, (c, f) in enumerate(calcs):
            x = ws.cell(r, len(inputs) + 1 + k, "=" + f); x.fill = CALC; x.protection = LOCK
    for j, c in enumerate(cols, 1):
        fm = (fmts or {}).get(c)
        if fm:
            for i in range(n): ws.cell(row0 + 1 + i, j).number_format = fm
        ws.column_dimensions[ws.cell(row0, j).column_letter].width = (widths or {}).get(c, max(11, len(c) + 2))
    last = ws.cell(row0 + n, len(cols)).coordinate
    t = Table(displayName=name, ref=f"A{row0}:{last}")
    t.tableStyleInfo = TableStyleInfo(name="TableStyleLight9", showRowStripes=True)
    calcmap = dict(calcs)
    for j, c in enumerate(cols, 1):  # calculated columns -> new rows auto-fill in Excel
        tc = TableColumn(id=j, name=c)
        if c in calcmap: tc.calculatedColumnFormula = TableFormula(attr_text=calcmap[c])
        t.tableColumns.append(tc)
    ws.add_table(t); ws.freeze_panes = ws.cell(row0 + 1, 2)
    return n


def dv(ws, sqref, **kw):
    d = DataValidation(allow_blank=True, showErrorMessage=True, errorStyle="stop", **kw); d.add(sqref); ws.add_data_validation(d)


def build(path, data=None, base="EUR", blank=False, extra=None):
    data = data or S.generate()
    if blank:
        data = dict(bookings=[], invoices=[], bills=[], payments=[], expenses=[])
    wb = Workbook(); wb.calculation = CalcProperties(fullCalcOnLoad=True)
    dash = wb.active; dash.title = "Dashboard"
    sheets = {n: wb.create_sheet(n) for n in ["Instructions", "Settings", "Rates", "Customers", "Suppliers", "Lists",
                                             "Bookings", "Invoices", "Bills", "Payments", "Expenses", "Reports", "Checks"]}
    # ---------- Settings
    st = sheets["Settings"]
    st["A1"] = "Settings"; st["A1"].font = Font(bold=True, size=14)
    items = [("Base (reporting) currency", base, "BaseCcy", None), ("As-of date (aging, AR/AP)", S.ASOF, "AsOf", DATE),
             ("First month on dashboard", S.FIRST_MONTH, "FirstMonth", DATE), ("BAM per EUR (fixed peg)", S.BAM_PEG, "BAMPeg", '0.00000'),
             ("Tolerance for checks", 0.01, "Tol", '0.00')]
    for i, (lab, v, nm, fm) in enumerate(items, 3):
        st.cell(i, 1, lab).font = BOLD; c = st.cell(i, 2, v); c.fill = INPUT; c.protection = UNLOCK
        if fm: c.number_format = fm
        wb.defined_names[nm] = DefinedName(nm, attr_text=f"Settings!$B${i}")
    st["C3"] = "Choose EUR, BAM or USD. Every report converts at the rate on each transaction date."
    st["C6"] = "Central Bank of BiH currency board rate. Change only if the peg changes."
    st["C4"] = "Open balances and aging are measured on this date (converted at this date's rate)."
    dv(st, "B3", type="list", formula1='"EUR,BAM,USD"')
    st.column_dimensions["A"].width = 30; st.column_dimensions["B"].width = 14; st.column_dimensions["C"].width = 80
    st.protection.sheet = True
    # ---------- Rates
    rs = sheets["Rates"]
    rr = [[d, v] for d, v in S.rates()]
    add_table(rs, "Rates", ["Date", "USD_per_EUR"], [("BAM_per_EUR", "BAMPeg")], rr, {"Date": DATE, "USD_per_EUR": '0.0000', "BAM_per_EUR": '0.00000'})
    rs["E1"] = "One row per rate date (e.g. weekly). A transaction uses the latest rate on or before its date. EUR is always 1."
    dv(rs, "B2:B5000", type="decimal", operator="greaterThan", formula1="0")
    # ---------- master data
    add_table(sheets["Customers"], "Customers", ["CustID", "Name", "Country", "TermsDays"], [], [list(c) for c in S.CUSTOMERS], widths={"Name": 36})
    add_table(sheets["Suppliers"], "Suppliers", ["SuppID", "Name", "Type", "Country"], [], [list(s) for s in S.SUPPLIERS], widths={"Name": 36})
    ls = sheets["Lists"]
    add_table(ls, "Salespeople", ["Salesperson"], [], [[s] for s in S.SALES], widths={"Salesperson": 18})
    for i, d in enumerate(["Destination"] + S.DESTS, 1): ls.cell(i, 3, d)
    for i in range(2, len(S.DESTS) + 2): ls.cell(i, 3).fill = INPUT
    t = Table(displayName="Destinations", ref=f"C1:C{len(S.DESTS)+1}"); t.tableStyleInfo = TableStyleInfo(name="TableStyleLight9"); ls.add_table(t)
    ls.column_dimensions["C"].width = 18
    for nm, rng in [("CustList", "Customers[CustID]"), ("SuppList", "Suppliers[SuppID]"), ("SalesList", "Salespeople[Salesperson]"),
                    ("DestList", "Destinations[Destination]")]:
        wb.defined_names[nm] = DefinedName(nm, attr_text=rng)
    # ---------- Bookings
    B = "Bookings"; r_ = lambda c: ref(B, c)
    bcalc = [
        ("RateSell", RATE(r_("SellCcy"), r_("StartDate"))),
        ("SellEUR", f'{r_("SellPrice")}/{r_("RateSell")}'),
        ("RevenueBase", f'IF({r_("Status")}="Cancelled",0,{r_("SellEUR")}*{RATE("BaseCcy", r_("StartDate"))})'),
        ("CostBase", f'IF({r_("Status")}="Cancelled",0,SUMIFS(Bills[CostBase],Bills[BookingID],{r_("BookingID")}))'),
        ("GrossProfit", f'{r_("RevenueBase")}-{r_("CostBase")}'),
        ("MarginPct", f'IF({r_("RevenueBase")}=0,"",{r_("GrossProfit")}/{r_("RevenueBase")})'),
        ("Month", f'IF(ISNUMBER({r_("StartDate")}),DATE(YEAR({r_("StartDate")}),MONTH({r_("StartDate")}),1),"")'),
        ("InvoicedBase", f'SUMIFS(Invoices[AmountBase],Invoices[BookingID],{r_("BookingID")})'),
        ("Flag", f'IF({r_("BookingID")}="","",_xlfn.TEXTJOIN("; ",TRUE,'
                 f'IF(COUNTIF(Bookings[BookingID],{r_("BookingID")})>1,"duplicate ID",""),'
                 f'IF(COUNTIF(CustList,{r_("Customer")})=0,"unknown customer",""),'
                 f'IF(AND(ISNUMBER({r_("StartDate")}),ISNUMBER({r_("EndDate")})),IF({r_("EndDate")}<{r_("StartDate")},"end before start",""),"date not a date"),'
                 f'IF(ISNUMBER({r_("SellPrice")}),"","price not a number"),'
                 f'IF(ISNA({r_("RateSell")}),"bad currency or no rate",""),'
                 f'IF(AND({r_("Status")}<>"Cancelled",COUNTIF(Invoices[BookingID],{r_("BookingID")})=0),"not invoiced",""),'
                 f'IFERROR(IF(AND({r_("Status")}<>"Cancelled",ABS({r_("InvoicedBase")}-{r_("RevenueBase")})>1),"invoices differ from price",""),"cannot compute")))'),
    ]
    bin_ = ["BookingID", "Type", "Customer", "Destination", "Salesperson", "BookingDate", "StartDate", "EndDate", "Pax", "Status", "SellCcy", "SellPrice"]
    bf = {c: DATE for c in ["BookingDate", "StartDate", "EndDate", "Month"]}
    bf.update({c: NUM for c in ["SellPrice", "SellEUR", "RevenueBase", "CostBase", "GrossProfit", "InvoicedBase"]}); bf["MarginPct"] = '0.0%'; bf["RateSell"] = '0.0000'; bf["Month"] = 'mmm yyyy'
    rows = [list(b) for b in data["bookings"]] + [list(x) for x in (extra or {}).get("bookings", [])]
    add_table(sheets[B], B, bin_, bcalc, rows, bf, {"Flag": 40})
    # ---------- Bills (direct costs + payables)
    L = "Bills"; r_ = lambda c: ref(L, c)
    lcalc = [
        ("Rate", RATE(r_("Ccy"), r_("BillDate"))),
        ("CostBase", f'{r_("Amount")}/{r_("Rate")}*{RATE("BaseCcy", r_("BillDate"))}'),
        ("Paid", f'SUMIFS(Payments[AmtInRefCcy],Payments[Ref],{r_("BillID")})'),
        ("Balance", f'{r_("Amount")}-{r_("Paid")}'),
        ("BalanceBase", f'{r_("Balance")}/{RATE(r_("Ccy"), "AsOf")}*{RATE("BaseCcy", "AsOf")}'),
        ("AmountBaseAsOf", f'{r_("Amount")}/{RATE(r_("Ccy"), "AsOf")}*{RATE("BaseCcy", "AsOf")}'),
        ("AgeDays", f'AsOf-{r_("BillDate")}'),
        ("Bucket", f'IF(ABS({r_("Balance")})<0.005,"Paid",IF({r_("AgeDays")}<=30,"0-30",IF({r_("AgeDays")}<=60,"31-60",IF({r_("AgeDays")}<=90,"61-90","90+"))))'),
        ("Flag", f'IF({r_("BillID")}="","",_xlfn.TEXTJOIN("; ",TRUE,'
                 f'IF(COUNTIF(Bills[BillID],{r_("BillID")})>1,"duplicate ID",""),'
                 f'IF(COUNTIF(SuppList,{r_("Supplier")})=0,"unknown supplier",""),'
                 f'IF(COUNTIF(Bookings[BookingID],{r_("BookingID")})=0,"unknown booking",""),'
                 f'IF(ISNUMBER({r_("Amount")}),"","amount not a number"),'
                 f'IF(ISNUMBER({r_("BillDate")}),"","date not a date"),'
                 f'IF(ISNA({r_("Rate")}),"bad currency or no rate",""),'
                 f'IFERROR(IF({r_("Balance")}<-0.005,"overpaid",""),"cannot compute")))'),
    ]
    lf = {c: DATE for c in ["BillDate", "DueDate"]}; lf.update({c: NUM for c in ["Amount", "CostBase", "Paid", "Balance", "BalanceBase", "AmountBaseAsOf"]}); lf["Rate"] = '0.0000'
    rows = [list(b) for b in data["bills"]] + [list(x) for x in (extra or {}).get("bills", [])]
    add_table(sheets[L], L, ["BillID", "Supplier", "BookingID", "BillDate", "DueDate", "Service", "Ccy", "Amount"], lcalc, rows, lf, {"Flag": 40})
    # ---------- Invoices
    I = "Invoices"; r_ = lambda c: ref(I, c)
    icalc = [
        ("Customer", f'_xlfn.XLOOKUP({r_("BookingID")},Bookings[BookingID],Bookings[Customer],"?")'),
        ("Rate", RATE(r_("Ccy"), r_("InvDate"))),
        ("AmountBase", f'{r_("Amount")}/{RATE(r_("Ccy"), "_xlfn.XLOOKUP(" + r_("BookingID") + ",Bookings[BookingID],Bookings[StartDate])")}*{RATE("BaseCcy", "_xlfn.XLOOKUP(" + r_("BookingID") + ",Bookings[BookingID],Bookings[StartDate])")}'),
        ("Paid", f'SUMIFS(Payments[AmtInRefCcy],Payments[Ref],{r_("InvoiceID")})'),
        ("Balance", f'{r_("Amount")}-{r_("Paid")}'),
        ("BalanceBase", f'{r_("Balance")}/{RATE(r_("Ccy"), "AsOf")}*{RATE("BaseCcy", "AsOf")}'),
        ("AmountBaseAsOf", f'{r_("Amount")}/{RATE(r_("Ccy"), "AsOf")}*{RATE("BaseCcy", "AsOf")}'),
        ("AgeDays", f'AsOf-{r_("InvDate")}'),
        ("Bucket", f'IF(ABS({r_("Balance")})<0.005,"Paid",IF({r_("AgeDays")}<=30,"0-30",IF({r_("AgeDays")}<=60,"31-60",IF({r_("AgeDays")}<=90,"61-90","90+"))))'),
        ("PayStatus", f'IF({r_("Balance")}<-0.005,"OVERPAID",IF(ABS({r_("Balance")})<0.005,"Paid",IF({r_("Paid")}>0,"Part-paid","Open")))'),
        ("Flag", f'IF({r_("InvoiceID")}="","",_xlfn.TEXTJOIN("; ",TRUE,'
                 f'IF(COUNTIF(Invoices[InvoiceID],{r_("InvoiceID")})>1,"duplicate ID",""),'
                 f'IF(COUNTIF(Bookings[BookingID],{r_("BookingID")})=0,"unknown booking",'
                 f'IF(_xlfn.XLOOKUP({r_("BookingID")},Bookings[BookingID],Bookings[Status])="Cancelled","booking cancelled","")),'
                 f'IF(ISNUMBER({r_("Amount")}),"","amount not a number"),'
                 f'IF(ISNUMBER({r_("InvDate")}),"","date not a date"),'
                 f'IF(ISNA({r_("Rate")}),"bad currency or no rate",""),'
                 f'IFERROR(IF({r_("Balance")}<-0.005,"overpaid",""),"cannot compute")))'),
    ]
    inf = {c: DATE for c in ["InvDate", "DueDate"]}; inf.update({c: NUM for c in ["Amount", "AmountBase", "Paid", "Balance", "BalanceBase", "AmountBaseAsOf"]}); inf["Rate"] = '0.0000'
    rows = [list(b) for b in data["invoices"]] + [list(x) for x in (extra or {}).get("invoices", [])]
    add_table(sheets[I], I, ["InvoiceID", "BookingID", "InvDate", "DueDate", "Ccy", "Amount"], icalc, rows, inf, {"Flag": 40, "Customer": 10})
    # ---------- Payments (in and out, any number of partials; negative = refund)
    P = "Payments"; r_ = lambda c: ref(P, c)
    rc = f'IF({r_("Direction")}="In",_xlfn.XLOOKUP({r_("Ref")},Invoices[InvoiceID],Invoices[Ccy],"?"),_xlfn.XLOOKUP({r_("Ref")},Bills[BillID],Bills[Ccy],"?"))'
    pcalc = [
        ("RefCcy", rc),
        ("AmtInRefCcy", f'IFERROR({r_("Amount")}/{RATE(r_("Ccy"), r_("PayDate"))}*{RATE(r_("RefCcy"), r_("PayDate"))},0)'),
        ("AmtBaseAsOf", f'IFERROR({r_("AmtInRefCcy")}/{RATE(r_("RefCcy"), "AsOf")}*{RATE("BaseCcy", "AsOf")},0)'),
        ("Flag", f'IF({r_("PayID")}="","",_xlfn.TEXTJOIN("; ",TRUE,'
                 f'IF(COUNTIF(Payments[PayID],{r_("PayID")})>1,"duplicate ID",""),'
                 f'IF({r_("RefCcy")}="?","unknown invoice/bill",""),'
                 f'IF(ISNUMBER({r_("Amount")}),"","amount not a number"),'
                 f'IF(ISNUMBER({r_("PayDate")}),"","date not a date"),'
                 f'IF(ISNA({RATE(r_("Ccy"), r_("PayDate"))}),"bad currency or no rate","")))'),
    ]
    pf = {"PayDate": DATE, "Amount": NUM, "AmtInRefCcy": NUM, "AmtBaseAsOf": NUM}
    rows = [list(b) for b in data["payments"]] + [list(x) for x in (extra or {}).get("payments", [])]
    add_table(sheets[P], P, ["PayID", "PayDate", "Direction", "Ref", "Ccy", "Amount", "Method", "Note"], pcalc, rows, pf, {"Flag": 34, "Note": 24})
    # ---------- Expenses
    E = "Expenses"; r_ = lambda c: ref(E, c)
    ecalc = [("Base", f'{r_("Amount")}/{RATE(r_("Ccy"), r_("ExpDate"))}*{RATE("BaseCcy", r_("ExpDate"))}'),
             ("Month", f'IF(ISNUMBER({r_("ExpDate")}),DATE(YEAR({r_("ExpDate")}),MONTH({r_("ExpDate")}),1),"")'),
             ("Flag", f'IF({r_("ExpID")}="","",_xlfn.TEXTJOIN("; ",TRUE,IF(COUNTIF(Expenses[ExpID],{r_("ExpID")})>1,"duplicate ID",""),'
                      f'IF(ISNUMBER({r_("Amount")}),"","amount not a number"),IF(ISNUMBER({r_("ExpDate")}),"","date not a date")))')]
    rows = [list(b) for b in data["expenses"]] + [list(x) for x in (extra or {}).get("expenses", [])]
    add_table(sheets[E], E, ["ExpID", "ExpDate", "Category", "Description", "Ccy", "Amount"], ecalc, rows, {"ExpDate": DATE, "Amount": NUM, "Base": NUM, "Month": 'mmm yyyy'}, {"Description": 24, "Flag": 30})
    # ---------- data validation on ledgers (Excel blocks bad typed entries; Flag column catches pasted ones)
    ccy = '"EUR,BAM,USD"'
    bk = sheets[B]
    dv(bk, "A2:A20000", type="custom", formula1="COUNTIF($A:$A,A2)=1", error="Booking ID already used")
    dv(bk, "B2:B20000", type="list", formula1='"FIT,Group"'); dv(bk, "C2:C20000", type="list", formula1="=CustList")
    dv(bk, "D2:D20000", type="list", formula1="=DestList"); dv(bk, "E2:E20000", type="list", formula1="=SalesList")
    dv(bk, "F2:G20000", type="date", operator="greaterThan", formula1="DATE(2000,1,1)")
    dv(bk, "H2:H20000", type="custom", formula1="AND(ISNUMBER(H2),H2>=G2)", error="End date must be a date on or after the start date")
    dv(bk, "I2:I20000", type="whole", operator="greaterThan", formula1="0")
    dv(bk, "J2:J20000", type="list", formula1='"Confirmed,Completed,Cancelled"'); dv(bk, "K2:K20000", type="list", formula1=ccy)
    dv(bk, "L2:L20000", type="decimal", operator="greaterThanOrEqual", formula1="0")
    iv = sheets[I]
    dv(iv, "A2:A20000", type="custom", formula1="COUNTIF($A:$A,A2)=1", error="Invoice ID already used")
    dv(iv, "B2:B20000", type="custom", formula1="COUNTIF(Bookings!$A:$A,B2)>0", error="Unknown booking ID")
    dv(iv, "C2:D20000", type="date", operator="greaterThan", formula1="DATE(2000,1,1)"); dv(iv, "E2:E20000", type="list", formula1=ccy)
    dv(iv, "F2:F20000", type="decimal", operator="greaterThan", formula1="0")
    bl = sheets[L]
    dv(bl, "A2:A20000", type="custom", formula1="COUNTIF($A:$A,A2)=1", error="Bill ID already used")
    dv(bl, "B2:B20000", type="list", formula1="=SuppList"); dv(bl, "C2:C20000", type="custom", formula1="COUNTIF(Bookings!$A:$A,C2)>0", error="Unknown booking ID")
    dv(bl, "D2:E20000", type="date", operator="greaterThan", formula1="DATE(2000,1,1)"); dv(bl, "G2:G20000", type="list", formula1=ccy)
    dv(bl, "H2:H20000", type="decimal", operator="greaterThan", formula1="0")
    py = sheets[P]
    dv(py, "A2:A50000", type="custom", formula1="COUNTIF($A:$A,A2)=1", error="Payment ID already used")
    dv(py, "B2:B50000", type="date", operator="greaterThan", formula1="DATE(2000,1,1)"); dv(py, "C2:C50000", type="list", formula1='"In,Out"')
    dv(py, "E2:E50000", type="list", formula1=ccy); dv(py, "F2:F50000", type="decimal", operator="notEqual", formula1="0")
    ex = sheets[E]
    dv(ex, "B2:B20000", type="date", operator="greaterThan", formula1="DATE(2000,1,1)"); dv(ex, "E2:E20000", type="list", formula1=ccy)
    dv(ex, "F2:F20000", type="decimal", operator="greaterThan", formula1="0")
    red = PatternFill("solid", fgColor="FFCDD2")
    for ws, col in [(bk, "U"), (bl, "Q"), (iv, "Q"), (py, "L"), (ex, "I")]:
        ws.conditional_formatting.add(f"{col}2:{col}50000", FormulaRule(formula=[f'LEN({col}2)>0'], fill=red))
    # ---------- Dashboard
    d = dash
    d["A1"] = "Travel agency finance dashboard (fictional sample data)"; d["A1"].font = Font(bold=True, size=16, color="1F3A5F")
    d["A2"] = '="Reporting currency: "&BaseCcy&"   |   As of "&TEXT(AsOf,"yyyy-mm-dd")&"   |   Checks: "&Checks!B2'
    hdr = ["Month", "Revenue", "Direct cost", "Gross profit", "GP %", "Opex", "Net op. profit", "Receivables (month end)", "Payables (month end)", "Bookings"]
    for j, h in enumerate(hdr, 1):
        c = d.cell(4, j, h); c.font = WH; c.fill = HEAD; c.alignment = Alignment(wrap_text=True, horizontal="center")
    for i in range(12):
        r = 5 + i; m = f"$A{r}"; eom = f"EOMONTH({m},0)"
        d[f"A{r}"] = f"=EDATE(FirstMonth,{i})"; d[f"A{r}"].number_format = "mmm yyyy"
        d[f"B{r}"] = f"=SUMIFS(Bookings[RevenueBase],Bookings[Month],{m})"
        d[f"C{r}"] = f"=SUMIFS(Bookings[CostBase],Bookings[Month],{m})"
        d[f"D{r}"] = f"=B{r}-C{r}"; d[f"E{r}"] = f'=IF(B{r}=0,"",D{r}/B{r})'; d[f"E{r}"].number_format = '0.0%'
        d[f"F{r}"] = f"=SUMIFS(Expenses[Base],Expenses[Month],{m})"; d[f"G{r}"] = f"=D{r}-F{r}"
        d[f"H{r}"] = (f'=SUMIFS(Invoices[AmountBaseAsOf],Invoices[InvDate],"<="&{eom})'
                      f'-SUMIFS(Payments[AmtBaseAsOf],Payments[Direction],"In",Payments[PayDate],"<="&{eom})')
        d[f"I{r}"] = (f'=SUMIFS(Bills[AmountBaseAsOf],Bills[BillDate],"<="&{eom})'
                      f'-SUMIFS(Payments[AmtBaseAsOf],Payments[Direction],"Out",Payments[PayDate],"<="&{eom})')
        d[f"J{r}"] = f'=COUNTIFS(Bookings[Month],{m},Bookings[Status],"<>Cancelled")'
        for col in "BCDEFGHIJ":  # months after the as-of date stay blank
            v = d[f"{col}{r}"].value; d[f"{col}{r}"] = f'=IF({m}>AsOf,"",{v[1:]})'
        for col in "BCDFGHI": d[f"{col}{r}"].number_format = NUM
    d["A17"] = "Total"; d["A17"].font = BOLD
    for col in "BCDFGJ":
        d[f"{col}17"] = f"=SUM({col}5:{col}16)"; d[f"{col}17"].font = BOLD; d[f"{col}17"].number_format = NUM if col != "J" else "0"
    d["E17"] = '=IF(B17=0,"",D17/B17)'; d["E17"].number_format = '0.0%'
    d["A19"] = "Open now (as-of date)"; d["A19"].font = BOLD
    kp = [("Receivables (AR)", "=SUM(Invoices[BalanceBase])"), ("Payables (AP)", "=SUM(Bills[BalanceBase])"),
          ("Overdue receivables (past due date)", '=SUMIFS(Invoices[BalanceBase],Invoices[DueDate],"<"&AsOf,Invoices[BalanceBase],">0")'),
          ("Overdue payables (past due date)", '=SUMIFS(Bills[BalanceBase],Bills[DueDate],"<"&AsOf,Bills[BalanceBase],">0")'),
          ("Cancelled bookings (kept, excluded)", '=COUNTIF(Bookings[Status],"Cancelled")'),
          ("Rows flagged for review", "=Checks!B26")]
    for i, (k, f) in enumerate(kp, 20):
        d[f"A{i}"] = k; d[f"B{i}"] = f; d[f"B{i}"].number_format = NUM if i < 24 else "0"
    d["A27"] = "Totals cover the 12 months from 'First month' (Settings) up to the as-of date.\nChecks must read ALL OK before trusting the numbers."
    d["A27"].font = Font(italic=True, color="666666")
    for col, w in zip("ABCDEFGHIJ", [30, 13, 13, 13, 8, 12, 14, 15, 15, 9]): d.column_dimensions[col].width = w
    d.row_dimensions[4].height = 32
    ch = BarChart(); ch.type = "col"; ch.title = "Revenue, gross profit and net operating profit by month"; ch.height = 7.0; ch.width = 17; ch.legend.position = "b"
    ch.add_data(Reference(d, min_col=2, min_row=4, max_row=16), titles_from_data=True)
    ch.add_data(Reference(d, min_col=4, min_row=4, max_row=16), titles_from_data=True)
    ch.add_data(Reference(d, min_col=7, min_row=4, max_row=16), titles_from_data=True)
    ch.set_categories(Reference(d, min_col=1, min_row=5, max_row=16)); d.add_chart(ch, "D19")
    d.conditional_formatting.add("A2", FormulaRule(formula=['ISNUMBER(SEARCH("ISSUE",A2))'], font=Font(bold=True, color="C62828")))
    d.protection.sheet = True
    d.page_setup.orientation = "landscape"; d.page_setup.fitToWidth = 1; d.page_setup.fitToHeight = 1; d.sheet_properties.pageSetUpPr.fitToPage = True
    d.print_area = "A1:J34"; d.page_setup.scale = 62
    # ---------- Reports (formula reports; ties checked on Checks)
    rp = sheets["Reports"]
    rp["A1"] = '="Reports in "&BaseCcy&" (confirmed + completed bookings; cancelled excluded)"'; rp["A1"].font = Font(bold=True, size=13)
    def block(col0, title, key_formula, key_col, n, label_formula=None):
        c0 = col0
        hd = [title, "Bookings", "Revenue", "Gross profit", "Margin"]
        for j, h in enumerate(hd):
            x = rp.cell(3, c0 + j, h); x.font = WH; x.fill = HEAD
        for i in range(n):
            r = 4 + i; k = rp.cell(r, c0).coordinate
            rp.cell(r, c0, key_formula(i))
            rp.cell(r, c0 + 1, f'=IF({k}="","",COUNTIFS(Bookings[{key_col}],{k},Bookings[Status],"<>Cancelled"))')
            rp.cell(r, c0 + 2, f'=IF({k}="","",SUMIFS(Bookings[RevenueBase],Bookings[{key_col}],{k}))').number_format = NUM
            rp.cell(r, c0 + 3, f'=IF({k}="","",SUMIFS(Bookings[GrossProfit],Bookings[{key_col}],{k}))').number_format = NUM
            rv, gp = rp.cell(r, c0 + 2).coordinate, rp.cell(r, c0 + 3).coordinate
            rp.cell(r, c0 + 4, f'=IF(N({rv})=0,"",{gp}/{rv})').number_format = '0.0%'
        r = 4 + n; rp.cell(r, c0, "Total").font = BOLD
        for j in (1, 2, 3):
            L_ = rp.cell(4, c0 + j).column_letter; x = rp.cell(r, c0 + j, f"=SUM({L_}4:{L_}{r-1})"); x.font = BOLD; x.number_format = NUM if j > 1 else "0"
        for j, w in enumerate([22, 9, 13, 13, 8]): rp.column_dimensions[rp.cell(1, c0 + j).column_letter].width = w
        return rp.cell(r, c0 + 2).coordinate
    tot = {}
    tot["month"] = block(1, "Month", lambda i: f"=Dashboard!A{5+i}", "Month", 12)
    for i in range(12): rp.cell(4 + i, 1).number_format = "mmm yyyy"
    tot["dest"] = block(7, "Destination", lambda i: f'=IFERROR(INDEX(Destinations[Destination],{i+1}),"")', "Destination", 20)
    tot["cust"] = block(13, "Customer ID", lambda i: f'=IFERROR(INDEX(Customers[CustID],{i+1}),"")', "Customer", 40)
    tot["sales"] = block(19, "Salesperson", lambda i: f'=IFERROR(INDEX(Salespeople[Salesperson],{i+1}),"")', "Salesperson", 15)
    # aging
    rp["Y3"] = "Aging (open balance, base ccy)"; rp["Y3"].font = WH; rp["Y3"].fill = HEAD; rp["Z3"] = "Receivables"; rp["AA3"] = "Payables"
    for c in ("Z3", "AA3"): rp[c].font = WH; rp[c].fill = HEAD
    for i, bk_ in enumerate(["0-30", "31-60", "61-90", "90+"], 4):
        rp[f"Y{i}"] = bk_
        rp[f"Z{i}"] = f'=SUMIFS(Invoices[BalanceBase],Invoices[Bucket],Y{i})'; rp[f"AA{i}"] = f'=SUMIFS(Bills[BalanceBase],Bills[Bucket],Y{i})'
        rp[f"Z{i}"].number_format = rp[f"AA{i}"].number_format = NUM
    rp["Y8"] = "Total"; rp["Z8"] = "=SUM(Z4:Z7)"; rp["AA8"] = "=SUM(AA4:AA7)"; rp["Z8"].number_format = rp["AA8"].number_format = NUM
    rp["Y9"] = "Aging counts days since invoice/bill date to the as-of date. Paid items are excluded."
    rp.column_dimensions["Y"].width = 26; rp.column_dimensions["Z"].width = 14; rp.column_dimensions["AA"].width = 14
    rp.protection.sheet = True
    # ---------- Checks
    ck = sheets["Checks"]
    ck["A1"] = "Control checks"; ck["A1"].font = Font(bold=True, size=14)
    ck["A2"] = "Overall"; ck["A2"].font = BOLD
    checks = [
        ("Dashboard revenue = bookings ledger (months shown)", "=Dashboard!B17", '=SUMIFS(Bookings[RevenueBase],Bookings[Month],">="&FirstMonth,Bookings[Month],"<"&EDATE(FirstMonth,12))'),
        ("Dashboard direct cost = bookings ledger", "=Dashboard!C17", '=SUMIFS(Bookings[CostBase],Bookings[Month],">="&FirstMonth,Bookings[Month],"<"&EDATE(FirstMonth,12))'),
        ("Dashboard opex = expenses ledger", "=Dashboard!F17", '=SUMIFS(Expenses[Base],Expenses[Month],">="&FirstMonth,Expenses[Month],"<"&EDATE(FirstMonth,12))'),
        ("Report by month = dashboard revenue", f"=Reports!{tot['month']}", "=Dashboard!B17"),
        ("Report by destination = all revenue", f"=Reports!{tot['dest']}", "=SUM(Bookings[RevenueBase])"),
        ("Report by customer = all revenue", f"=Reports!{tot['cust']}", "=SUM(Bookings[RevenueBase])"),
        ("Report by salesperson = all revenue", f"=Reports!{tot['sales']}", "=SUM(Bookings[RevenueBase])"),
        ("AR: invoice balances = invoiced - received", "=SUM(Invoices[BalanceBase])", '=SUM(Invoices[AmountBaseAsOf])-SUMIFS(Payments[AmtBaseAsOf],Payments[Direction],"In")'),
        ("AP: bill balances = billed - paid", "=SUM(Bills[BalanceBase])", '=SUM(Bills[AmountBaseAsOf])-SUMIFS(Payments[AmtBaseAsOf],Payments[Direction],"Out")'),
        ("AR aging total = AR", "=Reports!Z8", "=SUMIFS(Invoices[BalanceBase],Invoices[Bucket],\"<>Paid\")"),
        ("AP aging total = AP", "=Reports!AA8", "=SUMIFS(Bills[BalanceBase],Bills[Bucket],\"<>Paid\")"),
    ]
    for j, h in enumerate(["Check", "Value", "Should equal / limit", "Result"], 1):
        c = ck.cell(4, j, h); c.font = WH; c.fill = HEAD
    r = 5
    for lab, a, b in checks:
        ck[f"A{r}"] = lab; ck[f"B{r}"] = a; ck[f"C{r}"] = b; ck[f"D{r}"] = f'=IF(ISERROR(B{r}-C{r}),"ISSUE",IF(ABS(B{r}-C{r})<=Tol,"OK","ISSUE"))'
        ck[f"B{r}"].number_format = ck[f"C{r}"].number_format = NUM; r += 1
    counts = [
        ("Overpaid invoices (payments exceed invoice)", '=COUNTIF(Invoices[PayStatus],"OVERPAID")'),
        ("Overpaid supplier bills", '=COUNTIF(Bills[Balance],"<-0.005")'),
        ("Flagged bookings", '=COUNTIF(Bookings[Flag],"?*")'), ("Flagged invoices", '=COUNTIF(Invoices[Flag],"?*")'),
        ("Flagged bills", '=COUNTIF(Bills[Flag],"?*")'), ("Flagged payments", '=COUNTIF(Payments[Flag],"?*")'),
        ("Flagged expenses", '=COUNTIF(Expenses[Flag],"?*")'),
        ("Formula errors in ledgers", "=SUMPRODUCT(--ISERROR(Bookings[GrossProfit]))+SUMPRODUCT(--ISERROR(Invoices[Balance]))+SUMPRODUCT(--ISERROR(Bills[Balance]))+SUMPRODUCT(--ISERROR(Expenses[Base]))+SUMPRODUCT(--ISERROR(Bookings[RevenueBase]))+SUMPRODUCT(--ISERROR(Invoices[BalanceBase]))+SUMPRODUCT(--ISERROR(Bills[BalanceBase]))"),
    ]
    first_count = r
    for lab, f in counts:
        ck[f"A{r}"] = lab; ck[f"B{r}"] = f; ck[f"C{r}"] = 0; ck[f"D{r}"] = f'=IF(ISERROR(B{r}),"ISSUE",IF(B{r}=0,"OK","ISSUE"))'; r += 1
    assert r - 1 <= 24
    ck["A26"] = "Rows flagged (total)"; ck["B26"] = f"=SUM(B{first_count+2}:B{first_count+6})+B{first_count}+B{first_count+1}"
    ck["B2"] = f'=IF(COUNTIF(D5:D{r-1},"OK")={r-5},"ALL OK",COUNTIF(D5:D{r-1},"ISSUE")&" ISSUE(S)")'
    ck["A28"] = "If a count is not 0, filter that sheet's Flag column (non-blank) to see which rows and why."
    ck.conditional_formatting.add(f"D5:D{r-1}", CellIsRule(operator="equal", formula=['"ISSUE"'], fill=red))
    ck.conditional_formatting.add(f"D5:D{r-1}", CellIsRule(operator="equal", formula=['"OK"'], fill=PatternFill("solid", fgColor="C8E6C9")))
    ck.column_dimensions["A"].width = 50; ck.column_dimensions["B"].width = 16; ck.column_dimensions["C"].width = 18; ck.column_dimensions["D"].width = 10
    ck.protection.sheet = True
    # ---------- Instructions
    ins = sheets["Instructions"]
    lines = open(os.path.join(os.path.dirname(__file__), "instructions.txt"), encoding="utf-8").read().splitlines()
    for i, l in enumerate(lines, 1):
        c = ins.cell(i, 1, l)
        if l.startswith("#"): c.value = l.lstrip("# "); c.font = Font(bold=True, size=13 if l.startswith("# ") else 11)
    ins.column_dimensions["A"].width = 120; ins.protection.sheet = True
    for ws in wb.worksheets:
        ws.sheet_view.zoomScale = 90
    wb.save(path)
    return data


if __name__ == "__main__":
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data = S.generate(); S.seeded_cases(data)
    build(os.path.join(here, "TravelAgency_Finance_Workbook.xlsx"), data)
    build(os.path.join(here, "TravelAgency_Finance_Workbook_BLANK.xlsx"), blank=True)
    print("built")
