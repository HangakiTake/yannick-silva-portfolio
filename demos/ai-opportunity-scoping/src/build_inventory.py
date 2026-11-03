"""Write the messy inventory workbook and CSV from data/catalog.json."""

from __future__ import annotations

import csv
import json

from openpyxl import Workbook

from src.paths import ROOT


def load_catalog() -> dict:
    return json.loads((ROOT / "data" / "catalog.json").read_text(encoding="utf-8"))


def build(catalog: dict | None = None) -> tuple[object, object]:
    catalog = catalog or load_catalog()
    xlsx_path = ROOT / "data" / "pebblecart_inventory.xlsx"
    csv_path = ROOT / "data" / "pebblecart_inventory.csv"
    book = Workbook()
    cover = book.active
    cover.title = "Cover"
    cover["A1"] = "This sheet is a cover. The inventory is on the next sheet."
    sheet = book.create_sheet("Inventory")
    sheet.append([catalog["title"]])
    sheet.append([""] * len(catalog["headers"]))
    sheet.append(catalog["headers"])
    for row in catalog["rows"]:
        values = [
            row["process"],
            row["team"],
            row["volume"],
            row["minutes"],
            row["error"],
            row["sources"],
            row["notes"],
            row["owner"],
        ]
        sheet.append(["" if value is None else str(value) for value in values])
        for cell in sheet[sheet.max_row]:
            cell.number_format = "@"
    book.save(xlsx_path)

    width = len(catalog["headers"])
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([catalog["title"]] + [""] * (width - 1))
        writer.writerow([""] * width)
        writer.writerow(catalog["headers"])
        for row in catalog["rows"]:
            writer.writerow(
                [
                    row["process"],
                    row["team"],
                    row["volume"],
                    row["minutes"],
                    row["error"],
                    row["sources"],
                    row["notes"],
                    row["owner"],
                ]
            )
    return xlsx_path, csv_path


if __name__ == "__main__":
    print(build())
