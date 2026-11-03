"""Realism stress test: damage a copy of data/base in ways the generator never produced, run the
pipeline, and record whether each case is handled correctly, fails loudly, or fails silently."""
import csv, shutil, sys, tempfile
from pathlib import Path
from openpyxl import load_workbook
sys.path.insert(0, str(Path(__file__).parent)); import pipeline as p
BASE = Path(__file__).resolve().parents[1] / "data" / "base"
ref = p.kpis(p.run(BASE))

def xl(d, name, fn):
    f = d / name; wb = load_workbook(f); fn(wb.active); wb.save(f)

def hdr_col(ws, label):
    for row in ws.iter_rows(min_row=1, max_row=10):
        for c in row:
            if c.value == label: return c.row, c.column
CASES = []
def case(title):
    def deco(fn): CASES.append((title, fn)); return fn
    return deco

@case("US-format text amount '1,234.56' in PL file")
def _(d):
    def f(ws): r, c = hdr_col(ws, "Kwota netto"); ws.cell(r + 1, c).value = "1,234.56"
    xl(d, "sales_pl/sales_pl_2026-08.xlsx", f)
@case("Ambiguous text amount '1,234' in DACH file")
def _(d):
    def f(ws): r, c = hdr_col(ws, "Net Amount"); ws.cell(r + 1, c).value = "1,234"
    xl(d, "sales_dach/sales_dach_2026-08.xlsx", f)
@case("Date stored as Excel serial number (46250)")
def _(d):
    def f(ws): r, c = hdr_col(ws, "Data sprzedazy"); ws.cell(r + 2, c).value = 46250; ws.cell(r + 2, c).number_format = "General"
    xl(d, "sales_pl/sales_pl_2026-08.xlsx", f)
@case("Credit note (negative amount)")
def _(d):
    def f(ws): r, c = hdr_col(ws, "Kwota netto"); ws.cell(r + 3, c).value = -800
    xl(d, "sales_pl/sales_pl_2026-08.xlsx", f)
@case("Header pushed below row 10 (12 junk rows)")
def _(d):
    def f(ws): ws.insert_rows(1, 12)
    xl(d, "sales_dach/sales_dach_2026-09.xlsx", f)
@case("Same invoice number in PL and DACH files")
def _(d):
    src = load_workbook(d / "sales_pl/sales_pl_2026-09.xlsx").active; r, c = hdr_col(src, "Nr faktury"); inv = src.cell(r + 1, c).value
    def f(ws): r2, c2 = hdr_col(ws, "Invoice No"); ws.cell(r2 + 1, c2).value = inv
    xl(d, "sales_dach/sales_dach_2026-09.xlsx", f)
@case("Excel lock file ~$sales_pl_2026-09.xlsx left in folder")
def _(d): (d / "sales_pl" / "~$sales_pl_2026-09.xlsx").write_bytes(b"\x00lock")
@case("Unrelated file 'notes.txt' dropped in folder")
def _(d): (d / "sales_pl" / "notes.txt").write_text("call Anna re: targets")
@case("CRM deals exported with ';' delimiter (Excel PL/DE locale)")
def _(d):
    rows = list(csv.reader(open(d / "crm" / "crm_deals.csv", encoding="utf-8-sig")))
    with open(d / "crm" / "crm_deals.csv", "w", newline="", encoding="utf-8") as fh: csv.writer(fh, delimiter=";").writerows(rows)
@case("Customer name with trailing spaces and different case")
def _(d):
    def f(ws): r, c = hdr_col(ws, "Klient"); ws.cell(r + 1, c).value = "  " + str(ws.cell(r + 1, c).value).upper() + "   "
    xl(d, "sales_pl/sales_pl_2026-09.xlsx", f)
@case("Deal with unknown stage 'On hold'")
def _(d):
    rows = list(csv.reader(open(d / "crm" / "crm_deals.csv", encoding="utf-8-sig"))); i = rows[0].index("stage"); rows[1][i] = "On hold"
    with open(d / "crm" / "crm_deals.csv", "w", newline="", encoding="utf-8") as fh: csv.writer(fh).writerows(rows)

@case("DACH export without the Cust ID column")
def _(d):
    def f(ws): r, c = hdr_col(ws, "Cust ID"); ws.delete_cols(c)
    xl(d, "sales_dach/sales_dach_2026-08.xlsx", f)
@case("Blank invoice number on two rows")
def _(d):
    def f(ws):
        r, c = hdr_col(ws, "Nr faktury"); ws.cell(r + 1, c).value = None; ws.cell(r + 2, c).value = "  "
    xl(d, "sales_pl/sales_pl_2026-07.xlsx", f)
@case("Sale to a country not in the region map (HU)")
def _(d):
    def f(ws): r, c = hdr_col(ws, "Country"); ws.cell(r + 1, c).value = "HU"
    xl(d, "sales_dach/sales_dach_2026-07.xlsx", f)
@case("Target row with 'tbd' instead of a number")
def _(d):
    rows = list(csv.reader(open(d / "targets.csv", encoding="utf-8-sig"))); rows[1][2] = "tbd"
    with open(d / "targets.csv", "w", newline="", encoding="utf-8") as fh: csv.writer(fh).writerows(rows)


def main():
    out = ["| # | Stress case | Result | Revenue Δ vs base (EUR) | New exception types |", "|---|---|---|---|---|"]
    base_types = {e["issue"] for e in p.run(BASE)["exceptions"]}
    base_counts = {}
    for e in p.run(BASE)["exceptions"]: base_counts[e["issue"]] = base_counts.get(e["issue"], 0) + 1
    for i, (title, fn) in enumerate(CASES, 1):
        d = Path(tempfile.mkdtemp()) / "in"; shutil.copytree(BASE, d); fn(d)
        try:
            o = p.run(d); k = p.kpis(o); cnt = {}
            for e in o["exceptions"]: cnt[e["issue"]] = cnt.get(e["issue"], 0) + 1
            diff = {t: cnt.get(t, 0) - base_counts.get(t, 0) for t in set(cnt) | set(base_counts) if cnt.get(t, 0) != base_counts.get(t, 0)}
            res = "ran"; dv = f"{k['revenue_eur'] - ref['revenue_eur']:,.2f}"
            det = ", ".join(f"{t} {v:+d}" for t, v in sorted(diff.items())) or "none"
            if k["target_eur"] != ref["target_eur"]: det += f"; target Δ {k['target_eur'] - ref['target_eur']:,.2f}"
            if any(r["row_diff"] or r["eur_diff"] for r in o["recon"]): det += "; RECON DIFF"
            if k["weighted_pipeline_eur"] != ref["weighted_pipeline_eur"]: det += f"; weighted pipeline Δ {k['weighted_pipeline_eur'] - ref['weighted_pipeline_eur']:,.2f}"
        except Exception as ex:
            res, dv, det = f"STOPPED: {type(ex).__name__}: {str(ex)[:70]}", "-", "-"
        out.append(f"| {i} | {title} | {res} | {dv} | {det} |")
    print("\n".join(out))
if __name__ == "__main__": main()
