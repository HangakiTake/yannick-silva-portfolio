"""Build ExecReporting.xlsx: Parameters tables Power Query reads, a snapshot of
the query outputs (from pipeline.py on data/base), and formula-driven
Dashboard and Checks sheets. See README for the one-time query setup."""
import datetime as dt, sys
from pathlib import Path
from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.formatting.rule import FormulaRule
sys.path.insert(0, str(Path(__file__).parent))
import pipeline as pl
from config import FX_TO_EUR, STAGE_PROB, OPEN_STAGES, REGION, PL_ALIASES, DACH_ALIASES

ROOT = Path(__file__).resolve().parents[1]
EUR, PCT, DATE = '#,##0;[Red]-#,##0', '0.0%', 'yyyy-mm-dd'
H = Font(bold=True, color="FFFFFF"); HF = PatternFill("solid", fgColor="1F3864")
T = Font(bold=True, size=16, color="1F3864")
SALES_COLS = ["invoice_no", "source_file", "source_row", "invoice_date", "month_start", "customer_id", "customer_name",
              "country", "region", "amount", "currency", "amount_eur", "match_method"]
PIPE_COLS = ["deal_id", "account_id", "account_name", "country", "region", "stage", "amount", "currency",
             "amount_eur", "probability", "weighted_eur", "expected_close", "owner"]
RECON_COLS = ["source_file", "source", "rows_read", "rows_loaded", "rows_excluded", "eur_source", "eur_loaded",
              "eur_excluded", "row_diff", "eur_diff"]
EXC_COLS = ["source_file", "source_row", "record_key", "issue", "detail", "amount_raw", "action"]
SCHEMA_COLS = ["file", "status", "missing_columns", "unmapped_columns", "rows_read"]
KPI_ROWS = [("Revenue to date (EUR)", "revenue_eur", EUR), ("Target to date (EUR)", "target_eur", EUR),
            ("Attainment", "attainment", PCT), ("Open pipeline (EUR)", "open_pipeline_eur", EUR),
            ("Weighted pipeline (EUR)", "weighted_pipeline_eur", EUR), ("Win rate (deals)", "win_rate", PCT)]
STAGES_ARR = "{" + ",".join(f'"{s}"' for s in OPEN_STAGES) + "}"


def header(ws, row, col, names):
    for j, n in enumerate(names):
        c = ws.cell(row, col + j, n); c.font = H; c.fill = HF


def dump(ws, row, col, cols, records, fmts=None):
    header(ws, row, col, cols)
    for i, r in enumerate(records, start=row + 1):
        for j, k in enumerate(cols):
            c = ws.cell(i, col + j, r.get(k))
            if fmts and k in fmts: c.number_format = fmts[k]


def add_table(ws, name, ref):
    t = Table(displayName=name, ref=ref); t.tableStyleInfo = TableStyleInfo(name="TableStyleLight9", showRowStripes=True)
    ws.add_table(t)


def build(data_dir, out_path, input_folder_text):
    out = pl.run(data_dir); k = pl.kpis(out); top = pl.top_customers(out)
    wb = Workbook()

    # ---------- README ----------
    ws = wb.active; ws.title = "README"
    lines = [("Consolidated executive reporting - demo workbook", T),
             ("Fictional company (Kestrel Industrial Supplies). All data is synthetic.", None), ("", None),
             ("Monthly use (after one-time setup):", Font(bold=True)),
             ("1. Drop the new month's files into sales_pl\\ and sales_dach\\; replace the CRM exports in crm\\.", None),
             ("2. Data > Refresh All.", None),
             ("3. Open Checks: the banner must say ALL CHECKS PASS. If not, read the red rows.", None),
             ("4. Open Exceptions: work the list (fix in the source, then refresh).", None),
             ("5. Dashboard is ready for C-level.", None), ("", None),
             ("One-time setup in desktop Excel (Power Query): see README.md 'Setup' - about 15 minutes.", Font(bold=True)),
             ("Until setup is done, the Data_* sheets hold a SNAPSHOT computed by scripts/pipeline.py on data/base.", None),
             (f"Snapshot built {dt.date.today().isoformat()} from {Path(data_dir).name}.", None)]
    for i, (txt, f) in enumerate(lines, 1):
        c = ws.cell(i, 1, txt)
        if f: c.font = f
    ws.column_dimensions["A"].width = 110

    # ---------- Parameters ----------
    p = wb.create_sheet("Parameters")
    p["A1"] = "Parameters (read by Power Query)"; p["A1"].font = T
    p["A3"] = "Input folder"; p["B3"] = input_folder_text; p["A3"].font = Font(bold=True)
    p["C3"] = "Full path to the folder holding crm\\, sales_pl\\, sales_dach\\ and targets.csv"
    wb.defined_names["InputFolder"] = DefinedName("InputFolder", attr_text="Parameters!$B$3")
    p.column_dimensions["A"].width = 16; p.column_dimensions["B"].width = 40
    r = 6; p.cell(r - 1, 1, "FX to EUR (fixed monthly rates; update each month)").font = Font(bold=True)
    dump(p, r, 1, ["currency", "rate_to_eur"], [{"currency": c, "rate_to_eur": v} for c, v in FX_TO_EUR.items()])
    add_table(p, "tbl_FX", f"A{r}:B{r + len(FX_TO_EUR)}")
    p.cell(r - 1, 4, "Stage probabilities").font = Font(bold=True)
    dump(p, r, 4, ["stage", "probability"], [{"stage": s, "probability": v} for s, v in STAGE_PROB.items()])
    add_table(p, "tbl_Stages", f"D{r}:E{r + len(STAGE_PROB)}")
    p.cell(r - 1, 7, "Country to region").font = Font(bold=True)
    dump(p, r, 7, ["country", "region"], [{"country": c, "region": v} for c, v in REGION.items()])
    add_table(p, "tbl_Region", f"G{r}:H{r + len(REGION)}")
    al = [{"layout": lay, "std_column": s, "header": h} for lay, d in (("PL", PL_ALIASES), ("DACH", DACH_ALIASES))
          for s, hs in d.items() for h in hs]
    p.cell(r - 1, 10, "Header aliases (source header -> standard column). Add a row here when a source renames a column.").font = Font(bold=True)
    dump(p, r, 10, ["layout", "std_column", "header"], al)
    add_table(p, "tbl_Aliases", f"J{r}:L{r + len(al)}")
    for col in "JKL": p.column_dimensions[col].width = 20

    # ---------- Data sheets (snapshot) ----------
    d = wb.create_sheet("Data_Sales")
    dump(d, 1, 1, SALES_COLS, out["sales"], {"invoice_date": DATE, "month_start": DATE, "amount": "#,##0.00", "amount_eur": "#,##0.00"})
    d = wb.create_sheet("Data_Pipeline")
    dump(d, 1, 1, PIPE_COLS, out["pipeline"], {"expected_close": DATE, "amount": "#,##0.00", "amount_eur": "#,##0.00", "weighted_eur": "#,##0.00"})
    d = wb.create_sheet("Data_Targets")
    dump(d, 1, 1, ["month_start", "region", "target_eur"], out["targets"], {"month_start": DATE, "target_eur": "#,##0.00"})

    # ---------- Checks ----------
    c = wb.create_sheet("Checks", 1)
    c["A1"] = "Data checks and reconciliation"; c["A1"].font = T
    # Banner: schema, reconciliation, live tie-outs (N15:R17) and missing targets. The Python reference block
    # (N4:R10) is NOT in the banner: it only holds for data/base and would fail every later month.
    c["A2"] = ('=IF(OR(COUNTIF(U5:U200,"FAILED")>0,SUMPRODUCT(ABS(I5:I200))>0,SUMPRODUCT(ABS(J5:J200))>0.004,'
               'COUNTIF(R15:R17,"DIFF")>0,COUNTIF(Exceptions!D5:D2000,"BAD_TARGET")>0),"CHECK FAILED - do not publish","ALL CHECKS PASS")')
    c["A2"].font = Font(bold=True, size=14)
    c.conditional_formatting.add("A2", FormulaRule(formula=['LEFT($A$2,5)="CHECK"'], font=Font(color="C00000", bold=True, size=14)))
    c.conditional_formatting.add("A2", FormulaRule(formula=['LEFT($A$2,3)="ALL"'], font=Font(color="00703C", bold=True, size=14)))
    c["A3"] = "Reconciliation per source (rows_read = rows_loaded + rows_excluded; EUR the same). Query: Recon"
    dump(c, 4, 1, RECON_COLS, out["recon"], {k2: "#,##0.00" for k2 in ("eur_source", "eur_loaded", "eur_excluded", "eur_diff")})
    c["N3"] = "KPI tie-out: Excel formula vs independent Python figure (base data set)"
    header(c, 4, 14, ["kpi", "excel", "python_reference", "difference", "result"])
    for i, (label, key, fmt) in enumerate(KPI_ROWS, start=5):
        c.cell(i, 14, label)
        c.cell(i, 15, f"=Dashboard!B{5 + i - 5}").number_format = fmt
        c.cell(i, 16, k[key]).number_format = fmt
        c.cell(i, 17, f"=O{i}-P{i}")
        c.cell(i, 18, f'=IF(ABS(Q{i})<{0.000001 if fmt == PCT else 0.005},"OK","DIFF")')
    c["N12"] = "Reference only (not in the banner): Python figures for data/base. After refreshing on other data, DIFF here is expected."
    c["N13"] = "Live tie-out (in the banner): dashboard figure vs the Recon query, which totals the sources independently"
    header(c, 14, 14, ["check", "dashboard", "recon", "difference", "result"])
    live = [("Revenue = loaded sales EUR", "=Dashboard!B5", '=SUMIFS(G5:G200,B5:B200,"Excel*")'),
            ("Pipeline EUR = loaded deals EUR", "=SUM(Data_Pipeline!I:I)", '=SUMIFS(G5:G200,A5:A200,"crm_deals.csv")'),
            ("Targets EUR = loaded targets EUR", "=SUM(Data_Targets!C:C)", '=SUMIFS(G5:G200,A5:A200,"targets.csv")')]
    for i, (lab, f1, f2) in enumerate(live, start=15):
        c.cell(i, 14, lab); c.cell(i, 15, f1).number_format = EUR; c.cell(i, 16, f2).number_format = EUR
        c.cell(i, 17, f"=O{i}-P{i}"); c.cell(i, 18, f'=IF(ABS(Q{i})<0.005,"OK","DIFF")')
    c["T3"] = "Source file layout check. Query: SchemaCheck"
    dump(c, 4, 20, SCHEMA_COLS, out["schema"])
    c.conditional_formatting.add("A5:J200", FormulaRule(formula=['OR(AND(ISNUMBER($I5),$I5<>0),AND(ISNUMBER($J5),ABS($J5)>0.004))'],
                                                         fill=PatternFill("solid", fgColor="F8CBAD")))
    c.conditional_formatting.add("T5:X200", FormulaRule(formula=['$U5="FAILED"'], fill=PatternFill("solid", fgColor="F8CBAD")))
    for col, w in (("A", 24), ("N", 26), ("T", 24), ("V", 30), ("W", 30)): c.column_dimensions[col].width = w

    # ---------- Exceptions ----------
    e = wb.create_sheet("Exceptions", 2)
    e["A1"] = "Exceptions - every row that was excluded, or loaded with a warning"; e["A1"].font = T
    e["A2"] = '=COUNTA(D5:D2000)&" open exceptions. Excluded rows are NOT in the dashboard figures."'
    dump(e, 4, 1, EXC_COLS, out["exceptions"])
    issues = ["FILE_REJECTED", "DUPLICATE_INVOICE", "BAD_DATE", "BAD_AMOUNT", "BAD_CURRENCY", "DATE_OUTSIDE_FILE_MONTH",
              "BAD_STAGE", "UNMATCHED_CUSTOMER", "AMBIGUOUS_CUSTOMER", "UNKNOWN_ACCOUNT", "DUPLICATE_ACCOUNT"]
    header(e, 4, 10, ["issue", "count"])
    for i, iss in enumerate(issues, start=5):
        e.cell(i, 10, iss); e.cell(i, 11, f'=COUNTIF($D$5:$D$2000,J{i})')
    for col, w in (("A", 24), ("C", 18), ("D", 24), ("E", 44), ("G", 52), ("J", 26)): e.column_dimensions[col].width = w

    # ---------- Dashboard ----------
    b = wb.create_sheet("Dashboard", 0)
    b["A1"] = "Executive dashboard - Kestrel Industrial Supplies (synthetic demo data)"; b["A1"].font = T
    b["A2"] = '="Data to: "&TEXT(MAX(Data_Sales!E:E),"mmm yyyy")&"   |   Data status: "&Checks!A2&"   |   Open exceptions: "&COUNTA(Exceptions!D5:D2000)'
    b["A2"].font = Font(bold=True)
    b.conditional_formatting.add("A2", FormulaRule(formula=['ISNUMBER(SEARCH("FAILED",$A$2))'], font=Font(color="C00000", bold=True)))
    header(b, 4, 1, ["KPI", "Value"])
    f = {"revenue_eur": "=ROUND(SUM(Data_Sales!L:L),2)",
         "target_eur": '=ROUND(SUMIFS(Data_Targets!C:C,Data_Targets!A:A,"<="&MAX(Data_Sales!E:E)),2)',
         "attainment": "=IF(B6=0,\"\",B5/B6)",
         "open_pipeline_eur": f"=ROUND(SUMPRODUCT(SUMIFS(Data_Pipeline!I:I,Data_Pipeline!F:F,{STAGES_ARR})),2)",
         "weighted_pipeline_eur": f"=ROUND(SUMPRODUCT(SUMIFS(Data_Pipeline!K:K,Data_Pipeline!F:F,{STAGES_ARR})),2)",
         "win_rate": '=IFERROR(COUNTIF(Data_Pipeline!F:F,"Won")/(COUNTIF(Data_Pipeline!F:F,"Won")+COUNTIF(Data_Pipeline!F:F,"Lost")),"")'}
    for i, (label, key, fmt) in enumerate(KPI_ROWS, start=5):
        b.cell(i, 1, label); b.cell(i, 2, f[key]).number_format = fmt; b.cell(i, 2).font = Font(bold=True, size=12)
    # monthly
    header(b, 13, 1, ["Month", "Revenue EUR", "Target EUR", "Attainment"])
    months = sorted({t["month_start"] for t in out["targets"]})
    for i, m in enumerate(months, start=14):
        b.cell(i, 1, m).number_format = "mmm yyyy"
        b.cell(i, 2, f'=IF(A{i}>MAX(Data_Sales!E:E),"",SUMIFS(Data_Sales!L:L,Data_Sales!E:E,A{i}))').number_format = EUR
        b.cell(i, 3, f"=SUMIFS(Data_Targets!C:C,Data_Targets!A:A,A{i})").number_format = EUR
        b.cell(i, 4, f'=IF(OR(B{i}="",C{i}=0),"",B{i}/C{i})').number_format = PCT
    last_m = 13 + len(months)
    b.page_setup.orientation = "landscape"; b.page_setup.fitToWidth = 1; b.page_setup.fitToHeight = 1
    b.sheet_properties.pageSetUpPr.fitToPage = True
    # region
    r0 = last_m + 2
    header(b, r0, 1, ["Region", "Revenue to date", "Target to date", "Attainment"])
    for i, reg in enumerate(["PL", "DACH", "CEE", "Other"], start=r0 + 1):
        b.cell(i, 1, reg)
        b.cell(i, 2, f'=SUMIFS(Data_Sales!L:L,Data_Sales!I:I,A{i})').number_format = EUR
        b.cell(i, 3, f'=SUMIFS(Data_Targets!C:C,Data_Targets!B:B,A{i},Data_Targets!A:A,"<="&MAX(Data_Sales!E:E))').number_format = EUR
        b.cell(i, 4, f'=IF(C{i}=0,"",B{i}/C{i})').number_format = PCT
    # pipeline by stage
    header(b, 4, 7, ["Stage", "Deals", "EUR", "Weighted EUR"])
    for i, s in enumerate(STAGE_PROB, start=5):
        b.cell(i, 7, s)
        b.cell(i, 8, f"=COUNTIF(Data_Pipeline!F:F,G{i})")
        b.cell(i, 9, f"=SUMIFS(Data_Pipeline!I:I,Data_Pipeline!F:F,G{i})").number_format = EUR
        b.cell(i, 10, f"=SUMIFS(Data_Pipeline!K:K,Data_Pipeline!F:F,G{i})").number_format = EUR
    # top 10 (query TopCustomers loads here)
    b["N4"] = "Top 10 customers by revenue to date (query: TopCustomers)"; b["N4"].font = Font(bold=True)
    dump(b, 5, 14, ["rank", "customer", "revenue_eur"], top, {"revenue_eur": EUR})
    for col, w in (("A", 26), ("B", 16), ("C", 16), ("D", 12), ("G", 14), ("I", 14), ("J", 14), ("O", 34), ("P", 14)):
        b.column_dimensions[col].width = w
    ch = BarChart(); ch.title = "Revenue vs target by month (EUR)"; ch.height, ch.width = 7.5, 16
    ch.add_data(Reference(b, min_col=2, max_col=3, min_row=13, max_row=last_m), titles_from_data=True)
    ch.set_categories(Reference(b, min_col=1, min_row=14, max_row=last_m)); b.add_chart(ch, f"F{r0 - 8}")
    ch2 = BarChart(); ch2.type = "bar"; ch2.title = "Pipeline by stage (EUR)"; ch2.height, ch2.width = 7.5, 12
    ch2.add_data(Reference(b, min_col=9, max_col=9, min_row=4, max_row=8), titles_from_data=True)
    ch2.set_categories(Reference(b, min_col=7, min_row=5, max_row=8)); b.add_chart(ch2, "N17")

    # ---------- Input spec + Queries ----------
    s = wb.create_sheet("Input_Spec")
    s["A1"] = "Input spec - see INPUT_SPEC.md for the full version"; s["A1"].font = T
    rows = [("crm\\crm_accounts.csv", "account_id", "text", "required, unique, e.g. ACC-1001"),
            ("crm\\crm_accounts.csv", "account_name", "text", "required"),
            ("crm\\crm_accounts.csv", "country", "text", "ISO 2-letter, must be in tbl_Region"),
            ("crm\\crm_accounts.csv", "owner", "text", "optional"),
            ("crm\\crm_deals.csv", "deal_id", "text", "required"), ("crm\\crm_deals.csv", "account_id", "text", "must exist in accounts"),
            ("crm\\crm_deals.csv", "stage", "text", "one of tbl_Stages"), ("crm\\crm_deals.csv", "amount", "number", "dot decimal, no thousands separator"),
            ("crm\\crm_deals.csv", "currency", "text", "in tbl_FX"), ("crm\\crm_deals.csv", "expected_close", "date", "yyyy-mm-dd"),
            ("crm\\crm_deals.csv", "owner", "text", "optional"),
            ("targets.csv", "month", "date", "first of month, yyyy-mm-dd"), ("targets.csv", "region", "text", "PL / DACH / CEE"),
            ("targets.csv", "target_eur", "number", "EUR, dot decimal")]
    rows += [(f"sales_pl\\sales_pl_YYYY-MM.xlsx", std, "see INPUT_SPEC.md", "accepted headers: " + " | ".join(h)) for std, h in PL_ALIASES.items()]
    rows += [(f"sales_dach\\sales_dach_YYYY-MM.xlsx", std, "see INPUT_SPEC.md", "accepted headers: " + " | ".join(h)) for std, h in DACH_ALIASES.items()]
    dump(s, 3, 1, ["file", "column", "type", "rule"], [dict(zip(["file", "column", "type", "rule"], r)) for r in rows])
    for col, w in (("A", 36), ("B", 16), ("C", 18), ("D", 70)): s.column_dimensions[col].width = w
    q = wb.create_sheet("Queries")
    q["A1"] = "Power Query queries (M code in powerquery\\). Create in this order."; q["A1"].font = T
    qs = [("tbl_FX", "00_tbl_FX.m", "Connection only"), ("tbl_Stages", "00_tbl_Stages.m", "Connection only"),
          ("tbl_Region", "00_tbl_Region.m", "Connection only"), ("tbl_Aliases", "00_tbl_Aliases.m", "Connection only"),
          ("pInputFolder", "01_pInputFolder.m", "Connection only"), ("fnHelpers", "02_fnHelpers.m", "Connection only"),
          ("fnReadSalesFile", "03_fnReadSalesFile.m", "Connection only"), ("qAccounts", "04_qAccounts.m", "Connection only"),
          ("qSalesStage", "05_qSalesStage.m", "Connection only"), ("qTargetsStage", "06_qTargetsStage.m", "Connection only"), ("Sales", "10_Sales.m", "Table: Data_Sales!A1"),
          ("qDealsStage", "11_qDealsStage.m", "Connection only"), ("Pipeline", "12_Pipeline.m", "Table: Data_Pipeline!A1"),
          ("Targets", "13_Targets.m", "Table: Data_Targets!A1"), ("SchemaCheck", "14_SchemaCheck.m", "Table: Checks!T4"),
          ("Exceptions", "15_Exceptions.m", "Table: Exceptions!A4"), ("Recon", "16_Recon.m", "Table: Checks!A4"),
          ("TopCustomers", "17_TopCustomers.m", "Table: Dashboard!N5")]
    qh = ["query name (exact)", "file", "load to", "M code (paste into Advanced Editor)"]
    dump(q, 3, 1, qh, [dict(zip(qh, x + ((ROOT / "powerquery" / x[1]).read_text(encoding="utf-8"),))) for x in qs])
    for col, w in (("A", 22), ("B", 24), ("C", 26), ("D", 120)): q.column_dimensions[col].width = w
    for row in q.iter_rows(min_row=4, min_col=4, max_col=4):
        for c in row: c.alignment = Alignment(wrap_text=True, vertical="top")
    wb.save(out_path)
    return out, k


if __name__ == "__main__":
    o, k = build(ROOT / "data" / "base", ROOT / "ExecReporting.xlsx", "C:\\ExecReporting\\data\\base\\")
    print("built", ROOT / "ExecReporting.xlsx", k)
