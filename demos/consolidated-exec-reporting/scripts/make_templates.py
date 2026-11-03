"""Write empty input templates (headers + one example row) into templates/."""
import csv, datetime as dt
from pathlib import Path
from openpyxl import Workbook
T = Path(__file__).resolve().parents[1] / "templates"; T.mkdir(exist_ok=True)
def c(name, head, ex):
    with open(T / name, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(head); w.writerow(ex)
c("crm_accounts_TEMPLATE.csv", ["account_id", "account_name", "country", "owner"], ["ACC-1001", "Example Metal Sp. z o.o.", "PL", "A. Kowalska"])
c("crm_deals_TEMPLATE.csv", ["deal_id", "account_id", "stage", "amount", "currency", "expected_close", "owner"],
  ["D-5000", "ACC-1001", "Proposal", "12500.00", "PLN", "2026-11-30", "A. Kowalska"])
c("targets_TEMPLATE.csv", ["month", "region", "target_eur"], ["2026-11-01", "PL", "95000.00"])
wb = Workbook(); ws = wb.active; ws.title = "Sprzedaz"
ws.append(["Nr faktury", "Data sprzedazy", "Klient", "Kraj", "Kwota netto", "Waluta"])
ws.append(["FV/202611/00001", dt.date(2026, 11, 3), "Example Metal Sp. z o.o.", "PL", 4300.00, "PLN"]); ws["B2"].number_format = "DD.MM.YYYY"
wb.save(T / "sales_pl_YYYY-MM_TEMPLATE.xlsx")
wb = Workbook(); ws = wb.active; ws.title = "Export"
ws.append(["Kestrel DACH - Umsatz Export YYYY-MM"]); ws.append(["Generated from ERP, do not edit"]); ws.append([])
ws.append(["Invoice No", "Cust ID", "Customer", "Country", "Invoice Date", "Net Amount", "Currency"])
ws.append(["RE/202611/00002", "ACC-1051", "Example Werkzeug GmbH", "DE", dt.date(2026, 11, 4), 1980.00, "EUR"]); ws["E5"].number_format = "DD.MM.YYYY"
wb.save(T / "sales_dach_YYYY-MM_TEMPLATE.xlsx")
print("templates written")
