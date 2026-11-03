"""Messy-input stress run for the workbook (not part of pytest). Needs soffice. Prints one line per variant."""
import os, subprocess, sys, tempfile
from datetime import date
import openpyxl
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [HERE, os.path.join(os.path.dirname(HERE), "src")]
import build_workbook as B, rubs  # noqa: E402
from test_rubs import row_of, recon_rows, exc_total, errors, excel_cents  # noqa: E402


def cell(sheet, ref, v):
    return lambda wb: wb[sheet].__setitem__(ref, v)


def occ(unit, col, v):
    return lambda wb: wb["Occupancy"].cell(row_of(wb, "Occupancy", unit), col).__setattr__("value", v)


V = {
    "amount typed as text '1,234.50'": cell("Bills", "F3", "1,234.50"),
    "bill date typed as text '18/09/2026'": cell("Bills", "D2", "18/09/2026"),
    "credit (refund) bill -25.00": cell("Bills", "F3", -25.0),
    "zero-amount bill": cell("Bills", "F3", 0),
    "unit ID lower case in Occupancy": occ("P1-01", 1, "p1-01"),
    "unit ID with trailing space": occ("P1-01", 1, "P1-01 "),
    "occupants 2.5": occ("P1-01", 2, 2.5),
    "occupants typed as text '3'": occ("P1-01", 2, "3"),
    "all P1 tenants move out before bill period": lambda wb: [occ(u, 4, date(2026, 9, 1))(wb) for u in ["P1-01", "P1-03", "P1-04"]] + [
        wb["Occupancy"].cell(r, 4).__setattr__("value", date(2026, 9, 1)) for r in range(2, 102) if wb["Occupancy"].cell(r, 1).value == "P1-02"],
    "bill spanning two months (Sep 1 - Oct 31)": lambda wb: (cell("Bills", "D3", date(2026, 9, 1))(wb), cell("Bills", "E3", date(2026, 10, 31))(wb)),
    "amount with 3 decimals 100.005": cell("Bills", "F3", 100.005),
}
tmp = tempfile.mkdtemp(); paths = {}
for i, (name, edit) in enumerate(V.items()):
    p = os.path.join(tmp, f"v{i}.xlsx"); B.build(p)
    wb = openpyxl.load_workbook(p); edit(wb); wb.save(p); paths[name] = p
subprocess.run(["soffice", "--headless", "--calc", "--convert-to", "xlsx:Calc MS Excel 2007 XML", "--outdir", tmp + "/o", *paths.values()],
               check=True, capture_output=True)
for name, p in paths.items():
    wb = openpyxl.load_workbook(tmp + "/o/" + os.path.basename(p), data_only=True)
    ex = {k: v for k, v in exc_total(wb).items() if v and k != "TOTAL issues"}
    bad = [r[0] for r in recon_rows(wb) if r[12] != "OK"]
    try:
        ref, _ = rubs.allocate(*rubs.read_inputs(wb)); xl = excel_cents(wb)
        agree = f"python agrees {sum(ref.get(k) == xl.get(k) for k in set(ref) | set(xl))}/{len(set(ref) | set(xl))}"
    except Exception as e:
        agree = f"python ref crashed: {type(e).__name__}: {e}"
    print(f"{name:45s} -> exceptions {ex or 'none'}; recon not OK {bad or 'none'}; formula errors {len(errors(wb))}; {agree}")
