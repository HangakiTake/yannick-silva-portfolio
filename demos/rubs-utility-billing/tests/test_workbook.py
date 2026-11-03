"""Workbook tests. LibreOffice recalculates the formulas; rubs.py is the reference."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import load_workbook

from build_workbook import (
    BILL_LAST,
    DATA_START,
    ENG_COL,
    ENG_LAST,
    ENG_START,
    build,
)
from libreoffice_recalc import LibreOfficeSession
from rubs import Bill, Dataset, Occupancy, Rule, allocate_dataset, demo_dataset

REQUIRED_SHEETS = [
    "README",
    "Settings_Properties",
    "Settings_Units",
    "Occupancy",
    "Bills",
    "Rules",
    "Allocation",
    "Unit_Statements",
    "Property_Summary",
    "Reconciliation",
    "Manual_Check",
    "Exceptions",
]


@pytest.fixture(scope="module")
def lo():
    session = LibreOfficeSession(port=2055)
    session.start()
    yield session
    session.stop()


@pytest.fixture(scope="module")
def workbook(tmp_path_factory):
    path = tmp_path_factory.mktemp("rubs") / "RUBS_Billing_Demo.xlsx"
    build(path)
    return path


def _engine_rows(document):
    sheet = document.Sheets.getByName("Allocation")
    columns = {}
    for field in (
        "scope",
        "bill_id",
        "unit_id",
        "occupant_days",
        "occupied_days",
        "tenant_weight",
        "owner_weight",
        "gross_t",
        "gross_o",
        "discount_cents",
        "tenant_net",
    ):
        letter = ENG_COL[field]
        columns[field] = sheet.getCellRangeByName(f"{letter}{ENG_START}:{letter}{ENG_LAST}").getDataArray()
    rows = []
    count = len(columns["scope"])
    for index in range(count):
        rows.append({field: columns[field][index][0] for field in columns})
    return rows


def _cents(value) -> int:
    if value in ("", None):
        return 0
    return int(round(float(value)))


def assert_engine_matches(document, data: Dataset) -> Allocation:
    result = allocate_dataset(data)
    expected = {
        (bill.bill_id, line.unit_id): line
        for bill in result.bills
        if bill.included
        for line in bill.lines
    }
    seen = set()
    for row in _engine_rows(document):
        if row["scope"] != "Y":
            continue
        key = (row["bill_id"], row["unit_id"])
        line = expected.get(key)
        if line is None:
            assert _cents(row["tenant_net"]) == 0
            assert _cents(row["gross_o"]) == 0
            continue
        seen.add(key)
        assert _cents(row["occupant_days"]) == line.occupant_days
        assert _cents(row["occupied_days"]) == line.occupied_days
        assert _cents(row["tenant_weight"]) == line.tenant_weight
        assert _cents(row["owner_weight"]) == line.owner_weight
        assert _cents(row["gross_t"]) == line.tenant_gross_cents
        assert _cents(row["gross_o"]) == line.owner_gross_cents
        assert _cents(row["discount_cents"]) == line.discount_cents
        assert _cents(row["tenant_net"]) == line.tenant_net_cents
    assert seen == set(expected)
    return result


def test_workbook_has_the_required_sheets_and_live_formulas(workbook):
    book = load_workbook(workbook)
    assert book.sheetnames == REQUIRED_SHEETS
    engine = book["Allocation"][f"{ENG_COL['tenant_net']}{ENG_START}"].value
    assert isinstance(engine, str) and engine.startswith("=")
    manual = book["Manual_Check"]["D22"].value
    assert isinstance(manual, str) and manual.startswith("=")
    assert "not legal advice" in book["README"]["A3"].value.lower()
    assert "synthetic" in book["README"]["A4"].value.lower()
    text = " ".join(book["README"].cell(row, 1).value or "" for row in range(3, 14)).lower()
    assert "state" in text
    assert "not legal advice" in text


def test_libreoffice_recalculation_matches_python_to_the_cent(workbook, lo):
    document = lo.open(workbook)
    try:
        assert_engine_matches(document, demo_dataset())
        recon = document.Sheets.getByName("Reconciliation")
        rows = recon.getCellRangeByName(f"A{DATA_START}:J{BILL_LAST}").getDataArray()
        included = [bill for bill in allocate_dataset(demo_dataset()).bills if bill.included]
        seen = set()
        for bill_id, _prop, _util, _start, _end, _amount, status, _tenant, _owner, diff in rows:
            if not bill_id:
                continue
            if status == "Excluded":
                assert bill_id == "CS-E-CREDIT"
                continue
            assert status in {"Tied", "Tied with exceptions"}
            assert abs(float(diff)) < 0.001
            seen.add(bill_id)
        assert seen == {bill.bill_id for bill in included}
        summary = document.Sheets.getByName("Property_Summary")
        differences = summary.getCellRangeByName("A5:H12").getDataArray()
        for prop, *_rest, difference in differences:
            if prop:
                assert abs(float(difference)) < 0.001
    finally:
        document.close(False)


def test_manual_check_matches_every_included_bill(workbook, lo):
    document = lo.open(workbook)
    try:
        manual = document.Sheets.getByName("Manual_Check")
        result = allocate_dataset(demo_dataset())
        for bill in result.bills:
            if not bill.included:
                continue
            sample = next(line for line in bill.lines if line.tenant_weight or line.owner_weight) if any(
                line.tenant_weight or line.owner_weight for line in bill.lines
            ) else bill.lines[0]
            manual.getCellRangeByName("B4").setString(bill.bill_id)
            manual.getCellRangeByName("B5").setString(sample.unit_id)
            document.calculateAll()
            assert abs(float(manual.getCellRangeByName("D25").getValue())) < 0.001
            due = float(manual.getCellRangeByName("D22").getValue())
            assert _cents(round(due * 100)) == sample.tenant_net_cents
            block = manual.getCellRangeByName("A28:W57").getDataArray()
            nets = {row[0]: _cents(row[22]) for row in block if row[0]}
            for line in bill.lines:
                assert nets[line.unit_id] == line.tenant_net_cents
    finally:
        document.close(False)


def test_exceptions_sheet_flags_the_seeded_errors(workbook, lo):
    document = lo.open(workbook)
    try:
        sheet = document.Sheets.getByName("Exceptions")
        assert sheet.getCellRangeByName("B3").getValue() == 3
        messages = []
        for row in sheet.getCellRangeByName("G40:G209").getDataArray():
            if row[0]:
                messages.append(str(row[0]))
        blob = " ".join(messages)
        top = " ".join(str(value) for row in sheet.getCellRangeByName("A8:G12").getDataArray() for value in row)
        assert '""' not in top
        assert "Negative bill amount on CS-E-CREDIT" in blob
        assert "marked vacant" in blob
        assert "HC-03" in blob
        assert "2026-02-27" in blob
        assert "2026-02-28" in blob
        assert all(not text.startswith("#") for text in messages)
    finally:
        document.close(False)


def test_changing_inputs_changes_results_without_formula_edits(tmp_path, lo):
    path = tmp_path / "edited.xlsx"
    build(path)
    book = load_workbook(path)
    formula = book["Allocation"][f"{ENG_COL['tenant_net']}{ENG_START}"].value
    occupancy = book["Occupancy"]
    found_occ = False
    for row in range(DATA_START, DATA_START + 60):
        if occupancy.cell(row, 1).value == "HC-01-RES":
            occupancy.cell(row, 3).value = 5
            found_occ = True
            break
    rules = book["Rules"]
    found_rule = False
    for row in range(DATA_START, DATA_START + 48):
        if rules.cell(row, 1).value == "HC" and rules.cell(row, 2).value == "trash":
            rules.cell(row, 4).value = 40
            found_rule = True
            break
    bills = book["Bills"]
    for row in range(DATA_START, DATA_START + 32):
        if bills.cell(row, 1).value == "HC-W-2026-03":
            bills.cell(row, 4).value = 100
            break
    assert found_occ and found_rule
    book.save(path)
    reread = load_workbook(path)
    assert reread["Allocation"][f"{ENG_COL['tenant_net']}{ENG_START}"].value == formula

    original = allocate_dataset(demo_dataset())
    original_net = next(
        line.tenant_net_cents
        for bill in original.bills
        if bill.bill_id == "HC-W-2026-03"
        for line in bill.lines
        if line.unit_id == "HC-01"
    )
    data = demo_dataset()
    occupancy_rows = []
    for record in data.occupancy:
        if record.occupancy_id == "HC-01-RES":
            occupancy_rows.append(Occupancy(record.occupancy_id, record.unit_id, 5, record.move_in, record.move_out, record.notes))
        else:
            occupancy_rows.append(record)
    rule_rows = []
    for rule in data.rules:
        if rule.property_id == "HC" and rule.utility == "trash":
            rule_rows.append(Rule(rule.property_id, rule.utility, rule.method, Decimal("40"), rule.partial_vacancy, rule.vacant_equivalent, rule.notes))
        else:
            rule_rows.append(rule)
    bill_rows = []
    for bill in data.bills:
        if bill.bill_id == "HC-W-2026-03":
            bill_rows.append(Bill(bill.bill_id, bill.property_id, bill.utility, Decimal("100.00"), bill.period_start, bill.period_end, bill.notes))
        else:
            bill_rows.append(bill)
    edited = Dataset(data.properties, data.units, occupancy_rows, bill_rows, rule_rows)
    document = lo.open(path)
    try:
        assert_engine_matches(document, edited)
        edited_result = allocate_dataset(edited)
        edited_net = next(
            line.tenant_net_cents
            for bill in edited_result.bills
            if bill.bill_id == "HC-W-2026-03"
            for line in bill.lines
            if line.unit_id == "HC-01"
        )
        assert edited_net != original_net
        trash_before = next(bill.owner_cents for bill in original.bills if bill.bill_id == "HC-T-2026-03")
        trash_after = next(bill.owner_cents for bill in edited_result.bills if bill.bill_id == "HC-T-2026-03")
        assert trash_after > trash_before
    finally:
        document.close(False)


def test_overlapping_occupancy_is_flagged_in_the_workbook(tmp_path, lo):
    path = tmp_path / "overlap.xlsx"
    build(path)
    book = load_workbook(path)
    occupancy = book["Occupancy"]
    for row in range(DATA_START, DATA_START + 60):
        if occupancy.cell(row, 1).value == "MT-02-B":
            occupancy.cell(row, 4).value = date(2026, 3, 10)
            break
    else:
        raise AssertionError("MT-02-B was not in the occupancy sheet")
    book.save(path)
    document = lo.open(path)
    try:
        messages = [
            str(row[0])
            for row in document.Sheets.getByName("Exceptions").getCellRangeByName("G40:G209").getDataArray()
            if row[0]
        ]
        assert any("Overlapping occupancy on MT-02" in message for message in messages)
    finally:
        document.close(False)


def test_checked_in_workbook_matches_the_builder(tmp_path):
    fresh = tmp_path / "fresh.xlsx"
    build(fresh)
    committed = Path(__file__).resolve().parents[1] / "RUBS_Billing_Demo.xlsx"
    built = load_workbook(fresh)
    saved = load_workbook(committed)
    assert saved.sheetnames == built.sheetnames
    assert saved["Allocation"][f"{ENG_COL['tenant_net']}8"].value == built["Allocation"][f"{ENG_COL['tenant_net']}8"].value
    assert saved["Bills"]["D5"].value == built["Bills"]["D5"].value
    assert saved["Exceptions"]["G40"].value == built["Exceptions"]["G40"].value


def test_readme_file_states_the_limits():
    text = Path(__file__).resolve().parents[1].joinpath("README.md").read_text(encoding="utf-8").lower()
    assert "synthetic" in text
    assert "not legal advice" in text
    assert "state" in text
    assert "libreoffice" in text
