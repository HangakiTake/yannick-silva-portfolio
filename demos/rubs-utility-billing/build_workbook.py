"""Build RUBS_Billing_Demo.xlsx.

Inputs are yellow. Everything else is a formula. The engine on Allocation
implements the same integer-cent rules as rubs.py:

* owner-paid percent comes off the top (half-up, via basis points)
* the pool is split by largest remainder
* tie-break is the bucket key ascending (``unit id|O`` before ``unit id|T``)
* a vacant flag suppresses tenant occupancy
* discounts move cents from the tenant to Owner
"""

from __future__ import annotations

import argparse
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import column_index_from_string, get_column_letter
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.page import PageMargins

from rubs import demo_dataset

HERE = Path(__file__).resolve().parent
DEFAULT_OUT = HERE / "RUBS_Billing_Demo.xlsx"

HEADER_ROW = 4
DATA_START = 5
MAX_PROPERTIES = 8
MAX_UNITS = 30
MAX_OCC = 60
MAX_BILLS = 32
MAX_RULES = 48
ENG_HEADER = 7
ENG_START = 8
ENG_ROWS = MAX_BILLS * MAX_UNITS
ENG_LAST = ENG_START + ENG_ROWS - 1
REPORT_ROWS = 400
EX_DETAIL_START = 40

NAVY = "1F4E79"
TEAL = "0F5C5C"
GOLD = "FFF2CC"
CALC = "EEF2F6"
WHITE = "FFFFFF"
RED = "F8D0C8"
GREEN = "E3F1E6"
LINE = "D0D7DE"
ORANGE = "F4E1C8"

THIN = Border(
    left=Side(style="thin", color=LINE),
    right=Side(style="thin", color=LINE),
    top=Side(style="thin", color=LINE),
    bottom=Side(style="thin", color=LINE),
)
FILL_NAVY = PatternFill("solid", fgColor=NAVY)
FILL_TEAL = PatternFill("solid", fgColor=TEAL)
FILL_GOLD = PatternFill("solid", fgColor=GOLD)
FILL_CALC = PatternFill("solid", fgColor=CALC)
FILL_GREEN = PatternFill("solid", fgColor=GREEN)
FILL_RED = PatternFill("solid", fgColor=RED)
FONT_WHITE = Font(name="Calibri", bold=True, color=WHITE, size=11)
FONT_TITLE = Font(name="Calibri", bold=True, color=NAVY, size=18)
FONT_BODY = Font(name="Calibri", size=11, color="1A1A1A")
FONT_SMALL = Font(name="Calibri", size=10, italic=True, color="4A5560")
FONT_HEADER = Font(name="Calibri", bold=True, color=WHITE, size=10)
WRAP = Alignment(wrap_text=True, vertical="center")
LEFT = Alignment(vertical="center", wrap_text=True)

ENGINE_FIELDS = [
    "scope",
    "bill_id",
    "bill_property",
    "utility",
    "period_start",
    "period_end",
    "period_days",
    "amount_cents",
    "valid",
    "owner_bps",
    "owner_pct_cents",
    "pool_cents",
    "unit_id",
    "unit_property",
    "is_vacant",
    "discount_bps",
    "sqft",
    "excluded",
    "method",
    "partial",
    "vacant_eq",
    "occupant_days",
    "occupied_days",
    "tenant_weight",
    "owner_weight",
    "total_weight",
    "floor_t",
    "floor_o",
    "rem_t",
    "rem_o",
    "rank_t",
    "rank_o",
    "extra_t",
    "extra_o",
    "gross_t",
    "gross_o",
    "discount_cents",
    "tenant_net",
    "unallocated",
    "line_index",
    "key_t",
    "key_o",
    "leftover",
]
ENG_COL = {name: get_column_letter(21 + index) for index, name in enumerate(ENGINE_FIELDS)}


def last_row(count: int) -> int:
    return DATA_START + count - 1


PROP_LAST = last_row(MAX_PROPERTIES)
UNIT_LAST = last_row(MAX_UNITS)
OCC_LAST = last_row(MAX_OCC)
BILL_LAST = last_row(MAX_BILLS)
RULE_LAST = last_row(MAX_RULES)


def ec(name: str) -> str:
    return ENG_COL[name]


def cell(name: str, row: int) -> str:
    return f"{ec(name)}{row}"


def cents_formula(amount: Decimal) -> str:
    cents = int((Decimal(amount) * 100).quantize(Decimal("1")))
    return f"={cents}/100"


def apply_title(ws, text: str) -> None:
    ws["A1"] = text
    ws["A1"].font = FONT_TITLE
    ws.row_dimensions[1].height = 26
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.page_setup.paperSize = ws.PAPERSIZE_TABLOID
    ws.page_margins = PageMargins(0.5, 0.5, 0.6, 0.5, 0.3, 0.3)
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.oddFooter.left.text = "RUBS calculation tool. Not legal advice."
    ws.oddFooter.right.text = "Synthetic data"
    ws.sheet_view.showGridLines = False
    ws.sheet_view.zoomScale = 110


def instruction(ws, text: str) -> None:
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=8)
    ws["A2"] = text
    ws["A2"].font = FONT_SMALL
    ws["A2"].alignment = WRAP
    ws.row_dimensions[2].height = 36


def write_headers(ws, headers: list[str], calculated_from: int | None = None) -> None:
    for index, header in enumerate(headers, start=1):
        cell_obj = ws.cell(HEADER_ROW, index, header)
        calculated = calculated_from is not None and index >= calculated_from
        cell_obj.fill = FILL_TEAL if calculated else FILL_NAVY
        cell_obj.font = FONT_HEADER
        cell_obj.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        cell_obj.border = THIN
    ws.row_dimensions[HEADER_ROW].height = 32
    ws.freeze_panes = "A5"


def paint_inputs(ws, first_calc_col: int, last_col: int, capacity: int, formats: dict[int, str] | None = None) -> None:
    """Yellow through the column before first_calc_col. Gray from there through last_col."""
    formats = formats or {}
    last_col = max(last_col, first_calc_col - 1)
    for row in range(DATA_START, DATA_START + capacity):
        for col in range(1, last_col + 1):
            item = ws.cell(row, col)
            item.border = THIN
            item.font = FONT_BODY
            item.alignment = Alignment(vertical="center")
            item.fill = FILL_CALC if col >= first_calc_col else FILL_GOLD
            if col in formats:
                item.number_format = formats[col]


def widths(ws, sizes: list[float]) -> None:
    for index, size in enumerate(sizes, start=1):
        ws.column_dimensions[get_column_letter(index)].width = size


def add_name(wb: Workbook, name: str, ref: str) -> None:
    wb.defined_names.add(DefinedName(name=name, attr_text=ref))


def list_validation(formula: str, error: str) -> DataValidation:
    rule = DataValidation(type="list", formula1=formula, allow_blank=True, showDropDown=False, showErrorMessage=True, errorStyle="warning")
    rule.error = error
    rule.errorTitle = "Check this entry"
    rule.prompt = error
    rule.showInputMessage = True
    return rule


def overlap_raw(start: str, end: str) -> str:
    out_eff = f'((OccOut="")*{end}+(OccOut<>"")*OccOut)'
    ov_end = f"(({out_eff}<={end})*{out_eff}+({out_eff}>{end})*{end})"
    ov_start = f"((OccIn>={start})*OccIn+(OccIn<{start})*{start})"
    return f"({ov_end}-{ov_start}+1)"


def sumproduct_days(unit: str, start: str, end: str, with_counts: bool) -> str:
    raw = overlap_raw(start, end)
    weight = "OccCount" if with_counts else "(OccCount>0)"
    return f"SUMPRODUCT((OccUnit={unit})*({weight})*(({raw}>0)*({raw})))"


def prior_end_formula(row: int) -> str:
    terms = []
    for other in range(DATA_START, BILL_LAST + 1):
        terms.append(
            f'IF(AND($B${other}=B{row},$C${other}=C{row},$H${other}=1,$F${other}<E{row}),$F${other},0)'
        )
    joined = ",".join(terms)
    return f'IF(H{row}<>1,"",IF(MAX({joined})=0,"",MAX({joined})))'


def slot(row: int, axis: str) -> str:
    if axis == "bill":
        return f"INT((ROW()-{ENG_START})/{MAX_UNITS})+1"
    return f"MOD(ROW()-{ENG_START},{MAX_UNITS})+1"


def better_buckets(row: int, this_rem: str, this_key: str, other_weight: str, other_rem: str, other_key: str) -> str:
    bill = ec("bill_id")
    return (
        f"SUMPRODUCT((${bill}${ENG_START}:${bill}${ENG_LAST}={ec('bill_id')}{row})"
        f"*(${other_weight}${ENG_START}:${other_weight}${ENG_LAST}>0)"
        f"*((${other_rem}${ENG_START}:${other_rem}${ENG_LAST}>{this_rem})"
        f"+((${other_rem}${ENG_START}:${other_rem}${ENG_LAST}={this_rem})"
        f"*(${other_key}${ENG_START}:${other_key}${ENG_LAST}<{this_key}))))"
    )


def rank_formula(row: int, side: str) -> str:
    weight = cell("tenant_weight" if side == "t" else "owner_weight", row)
    rem = cell("rem_t" if side == "t" else "rem_o", row)
    key = cell("key_t" if side == "t" else "key_o", row)
    tenant = better_buckets(row, rem, key, ec("tenant_weight"), ec("rem_t"), ec("key_t"))
    owner = better_buckets(row, rem, key, ec("owner_weight"), ec("rem_o"), ec("key_o"))
    return f"IF({weight}<=0,0,{tenant}+{owner})"


def engine_formulas(row: int) -> dict[str, str]:
    bill_i = slot(row, "bill")
    unit_i = slot(row, "unit")
    formulas = {
        "bill_id": f'IF(INDEX(BillID,{bill_i})="","",INDEX(BillID,{bill_i}))',
        "bill_property": f'IF({cell("bill_id", row)}="","",INDEX(BillProp,{bill_i}))',
        "utility": f'IF({cell("bill_id", row)}="","",INDEX(BillUtil,{bill_i}))',
        "period_start": f'IF({cell("bill_id", row)}="","",INDEX(BillStart,{bill_i}))',
        "period_end": f'IF({cell("bill_id", row)}="","",INDEX(BillEnd,{bill_i}))',
        "period_days": (
            f'IF(OR({cell("period_start", row)}="",{cell("period_end", row)}="",'
            f'{cell("period_end", row)}<{cell("period_start", row)}),"",'
            f'{cell("period_end", row)}-{cell("period_start", row)}+1)'
        ),
        "amount_cents": f'IF({cell("bill_id", row)}="","",ROUND(INDEX(BillAmt,{bill_i})*100,0))',
        "valid": f'IF({cell("bill_id", row)}="","",INDEX(BillValid,{bill_i}))',
        "unit_id": f'IF(INDEX(UnitID,{unit_i})="","",INDEX(UnitID,{unit_i}))',
        "unit_property": f'IF({cell("unit_id", row)}="","",INDEX(UnitProp,{unit_i}))',
        "is_vacant": f'IF({cell("unit_id", row)}="","",INDEX(UnitVac,{unit_i}))',
        "discount_bps": (
            f'IF(OR({cell("unit_id", row)}="",INDEX(UnitDisc,{unit_i})<0,INDEX(UnitDisc,{unit_i})>100),"",'
            f"ROUND(INDEX(UnitDisc,{unit_i})*100,0))"
        ),
        "sqft": (
            f'IF({cell("unit_id", row)}="","",IF(INDEX(UnitSqft,{unit_i})="",0,INDEX(UnitSqft,{unit_i})))'
        ),
        "excluded": (
            f'IF(OR({cell("unit_id", row)}="",{cell("utility", row)}="",INDEX(UnitExcl,{unit_i})=""),0,'
            f'IF(ISNUMBER(SEARCH(","&{cell("utility", row)}&",",","&SUBSTITUTE(INDEX(UnitExcl,{unit_i})," ","")&",")),1,0))'
        ),
        "method": (
            f'IF({cell("bill_property", row)}="","",'
            f'IFERROR(INDEX(RuleMethod,MATCH({cell("bill_property", row)}&"|"&{cell("utility", row)},RuleKey,0)),""))'
        ),
        "partial": (
            f'IF({cell("method", row)}="","",'
            f'IFERROR(INDEX(RulePartial,MATCH({cell("bill_property", row)}&"|"&{cell("utility", row)},RuleKey,0)),""))'
        ),
        "vacant_eq": (
            f'IF({cell("method", row)}="","",'
            f'IFERROR(INDEX(RuleEquiv,MATCH({cell("bill_property", row)}&"|"&{cell("utility", row)},RuleKey,0)),0))'
        ),
        "owner_bps": (
            f'IF(OR({cell("method", row)}="",{cell("valid", row)}<>1),"",'
            f'ROUND(INDEX(RuleOwner,MATCH({cell("bill_property", row)}&"|"&{cell("utility", row)},RuleKey,0))*100,0))'
        ),
        "scope": (
            f'IF(AND({cell("bill_id", row)}<>"",{cell("unit_id", row)}<>"",'
            f'{cell("bill_property", row)}={cell("unit_property", row)}),"Y","")'
        ),
        "occupant_days": (
            f'IF(OR({cell("scope", row)}<>"Y",{cell("is_vacant", row)}="Y",'
            f'{cell("period_start", row)}="",{cell("period_end", row)}=""),0,'
            f'{sumproduct_days(cell("unit_id", row), cell("period_start", row), cell("period_end", row), True)})'
        ),
        "occupied_days": (
            f'IF(OR({cell("scope", row)}<>"Y",{cell("is_vacant", row)}="Y",'
            f'{cell("period_start", row)}="",{cell("period_end", row)}=""),0,'
            f'MIN({cell("period_days", row)},'
            f'{sumproduct_days(cell("unit_id", row), cell("period_start", row), cell("period_end", row), False)}))'
        ),
        "tenant_weight": (
            f'IF(OR({cell("scope", row)}<>"Y",{cell("valid", row)}<>1,{cell("excluded", row)}=1,{cell("method", row)}=""),0,'
            f'IF({cell("method", row)}="occupant_days",IF({cell("is_vacant", row)}="Y",0,{cell("occupant_days", row)}),'
            f'IF({cell("method", row)}="per_unit",{cell("occupied_days", row)},'
            f'IF({cell("method", row)}="square_footage",IF({cell("sqft", row)}<=0,0,{cell("sqft", row)}*{cell("occupied_days", row)}),0))))'
        ),
        "owner_weight": (
            f'IF(OR({cell("scope", row)}<>"Y",{cell("valid", row)}<>1,{cell("excluded", row)}=1,'
            f'{cell("method", row)}="",{cell("partial", row)}<>"owner"),0,'
            f'IF({cell("method", row)}="occupant_days",{cell("vacant_eq", row)}*({cell("period_days", row)}-{cell("occupied_days", row)}),'
            f'IF({cell("method", row)}="per_unit",{cell("period_days", row)}-{cell("occupied_days", row)},'
            f'IF({cell("method", row)}="square_footage",IF({cell("sqft", row)}<=0,0,{cell("sqft", row)}*({cell("period_days", row)}-{cell("occupied_days", row)})),0))))'
        ),
        "total_weight": (
            f'IF({cell("bill_id", row)}="","",'
            f'SUMIF(${ec("bill_id")}${ENG_START}:${ec("bill_id")}${ENG_LAST},{cell("bill_id", row)},'
            f'${ec("tenant_weight")}${ENG_START}:${ec("tenant_weight")}${ENG_LAST})+'
            f'SUMIF(${ec("bill_id")}${ENG_START}:${ec("bill_id")}${ENG_LAST},{cell("bill_id", row)},'
            f'${ec("owner_weight")}${ENG_START}:${ec("owner_weight")}${ENG_LAST}))'
        ),
        "pool_cents": (
            f'IF(OR({cell("bill_id", row)}="",{cell("valid", row)}<>1,{cell("method", row)}=""),0,'
            f'{cell("amount_cents", row)}-QUOTIENT({cell("amount_cents", row)}*IF({cell("owner_bps", row)}="",0,{cell("owner_bps", row)})+5000,10000))'
        ),
        "owner_pct_cents": (
            f'IF(OR(MOD(ROW()-{ENG_START},{MAX_UNITS})<>0,{cell("method", row)}="",{cell("valid", row)}<>1),0,'
            f'QUOTIENT({cell("amount_cents", row)}*{cell("owner_bps", row)}+5000,10000))'
        ),
        "floor_t": (
            f'IF(OR({cell("tenant_weight", row)}<=0,{cell("total_weight", row)}="",{cell("total_weight", row)}<=0),0,'
            f'QUOTIENT({cell("pool_cents", row)}*{cell("tenant_weight", row)},{cell("total_weight", row)}))'
        ),
        "floor_o": (
            f'IF(OR({cell("owner_weight", row)}<=0,{cell("total_weight", row)}="",{cell("total_weight", row)}<=0),0,'
            f'QUOTIENT({cell("pool_cents", row)}*{cell("owner_weight", row)},{cell("total_weight", row)}))'
        ),
        "rem_t": (
            f'IF({cell("tenant_weight", row)}<=0,0,'
            f'MOD({cell("pool_cents", row)}*{cell("tenant_weight", row)},{cell("total_weight", row)}))'
        ),
        "rem_o": (
            f'IF({cell("owner_weight", row)}<=0,0,'
            f'MOD({cell("pool_cents", row)}*{cell("owner_weight", row)},{cell("total_weight", row)}))'
        ),
        "key_t": f'IF({cell("tenant_weight", row)}<=0,"",{cell("unit_id", row)}&"|T")',
        "key_o": f'IF({cell("owner_weight", row)}<=0,"",{cell("unit_id", row)}&"|O")',
        "leftover": (
            f'IF(OR({cell("bill_id", row)}="",{cell("valid", row)}<>1),0,'
            f'{cell("pool_cents", row)}'
            f'-SUMIF(${ec("bill_id")}${ENG_START}:${ec("bill_id")}${ENG_LAST},{cell("bill_id", row)},${ec("floor_t")}${ENG_START}:${ec("floor_t")}${ENG_LAST})'
            f'-SUMIF(${ec("bill_id")}${ENG_START}:${ec("bill_id")}${ENG_LAST},{cell("bill_id", row)},${ec("floor_o")}${ENG_START}:${ec("floor_o")}${ENG_LAST}))'
        ),
        "rank_t": rank_formula(row, "t"),
        "rank_o": rank_formula(row, "o"),
        "extra_t": f'IF(AND({cell("tenant_weight", row)}>0,{cell("rank_t", row)}<{cell("leftover", row)}),1,0)',
        "extra_o": f'IF(AND({cell("owner_weight", row)}>0,{cell("rank_o", row)}<{cell("leftover", row)}),1,0)',
        "gross_t": f'{cell("floor_t", row)}+{cell("extra_t", row)}',
        "gross_o": f'{cell("floor_o", row)}+{cell("extra_o", row)}',
        "discount_cents": (
            f'IF(OR({cell("gross_t", row)}<=0,{cell("discount_bps", row)}=""),0,'
            f'QUOTIENT({cell("gross_t", row)}*{cell("discount_bps", row)}+5000,10000))'
        ),
        "tenant_net": f'{cell("gross_t", row)}-{cell("discount_cents", row)}',
        "unallocated": (
            f'IF(MOD(ROW()-{ENG_START},{MAX_UNITS})<>0,0,'
            f'IF(AND({cell("valid", row)}=1,{cell("method", row)}="",{cell("amount_cents", row)}>0),{cell("amount_cents", row)},'
            f'IF(AND({cell("valid", row)}=1,{cell("pool_cents", row)}>0,{cell("total_weight", row)}=0),{cell("pool_cents", row)},0)))'
        ),
    }
    if row == ENG_START:
        formulas["line_index"] = f'IF({cell("scope", row)}="Y",1,0)'
    else:
        formulas["line_index"] = (
            f'IF({cell("scope", row)}="Y",{cell("line_index", row - 1)}+1,{cell("line_index", row - 1)})'
        )
    return formulas


def build(path: Path = DEFAULT_OUT) -> Path:
    data = demo_dataset()
    wb = Workbook()
    readme = wb.active
    readme.title = "README"
    properties = wb.create_sheet("Settings_Properties")
    units = wb.create_sheet("Settings_Units")
    occupancy = wb.create_sheet("Occupancy")
    bills = wb.create_sheet("Bills")
    rules = wb.create_sheet("Rules")
    allocation = wb.create_sheet("Allocation")
    statements = wb.create_sheet("Unit_Statements")
    summary = wb.create_sheet("Property_Summary")
    reconciliation = wb.create_sheet("Reconciliation")
    manual = wb.create_sheet("Manual_Check")
    exceptions = wb.create_sheet("Exceptions")

    _names(wb)
    _readme(readme)
    _properties(properties, data)
    _units(units, data)
    _occupancy(occupancy, data)
    _bills(bills, data)
    _rules(rules, data)
    _allocation(allocation)
    _statements(statements)
    _summary(summary)
    _reconciliation(reconciliation)
    _manual(manual)
    _exceptions(exceptions)

    readme.sheet_view.tabSelected = True
    wb.active = readme
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def _names(wb: Workbook) -> None:
    spans = {
        "PropID": f"Settings_Properties!$A${DATA_START}:$A${PROP_LAST}",
        "PropName": f"Settings_Properties!$B${DATA_START}:$B${PROP_LAST}",
        "UnitID": f"Settings_Units!$A${DATA_START}:$A${UNIT_LAST}",
        "UnitProp": f"Settings_Units!$B${DATA_START}:$B${UNIT_LAST}",
        "UnitVac": f"Settings_Units!$C${DATA_START}:$C${UNIT_LAST}",
        "UnitDisc": f"Settings_Units!$D${DATA_START}:$D${UNIT_LAST}",
        "UnitSqft": f"Settings_Units!$E${DATA_START}:$E${UNIT_LAST}",
        "UnitExcl": f"Settings_Units!$F${DATA_START}:$F${UNIT_LAST}",
        "OccID": f"Occupancy!$A${DATA_START}:$A${OCC_LAST}",
        "OccUnit": f"Occupancy!$B${DATA_START}:$B${OCC_LAST}",
        "OccCount": f"Occupancy!$C${DATA_START}:$C${OCC_LAST}",
        "OccIn": f"Occupancy!$D${DATA_START}:$D${OCC_LAST}",
        "OccOut": f"Occupancy!$E${DATA_START}:$E${OCC_LAST}",
        "OccOutEff": f"Occupancy!$G${DATA_START}:$G${OCC_LAST}",
        "OccOverlap": f"Occupancy!$H${DATA_START}:$H${OCC_LAST}",
        "BillID": f"Bills!$A${DATA_START}:$A${BILL_LAST}",
        "BillProp": f"Bills!$B${DATA_START}:$B${BILL_LAST}",
        "BillUtil": f"Bills!$C${DATA_START}:$C${BILL_LAST}",
        "BillAmt": f"Bills!$D${DATA_START}:$D${BILL_LAST}",
        "BillStart": f"Bills!$E${DATA_START}:$E${BILL_LAST}",
        "BillEnd": f"Bills!$F${DATA_START}:$F${BILL_LAST}",
        "BillValid": f"Bills!$H${DATA_START}:$H${BILL_LAST}",
        "BillPrior": f"Bills!$I${DATA_START}:$I${BILL_LAST}",
        "BillOverlap": f"Bills!$J${DATA_START}:$J${BILL_LAST}",
        "RuleProp": f"Rules!$A${DATA_START}:$A${RULE_LAST}",
        "RuleUtil": f"Rules!$B${DATA_START}:$B${RULE_LAST}",
        "RuleMethod": f"Rules!$C${DATA_START}:$C${RULE_LAST}",
        "RuleOwner": f"Rules!$D${DATA_START}:$D${RULE_LAST}",
        "RulePartial": f"Rules!$E${DATA_START}:$E${RULE_LAST}",
        "RuleEquiv": f"Rules!$F${DATA_START}:$F${RULE_LAST}",
        "RuleKey": f"Rules!$H${DATA_START}:$H${RULE_LAST}",
        "UtilityList": "Rules!$AA$5:$AA$20",
        "MethodList": "Rules!$AB$5:$AB$8",
        "YesNoList": "Rules!$AC$5:$AC$6",
        "PartialList": "Rules!$AD$5:$AD$6",
    }
    for name, ref in spans.items():
        add_name(wb, name, ref)
    for field, letter in ENG_COL.items():
        add_name(wb, f"Eng_{field}", f"Allocation!${letter}${ENG_START}:${letter}${ENG_LAST}")


def _readme(ws) -> None:
    apply_title(ws, "RUBS utility billing demo")
    ws.sheet_properties.tabColor = "C4A35A"
    paragraphs = [
        "This workbook allocates water, sewer, trash, gas, and other utility bills to units. It is a calculation tool for a property manager who wants to see the formulas. It is not a billing service and it is not legal advice.",
        "The properties, residents, and bills are synthetic. They are not a real community and they are not tied to a real jurisdiction. RUBS (ratio utility billing) rules vary by US state and by local law. Some places restrict which utilities can be allocated, cap fees, require submetering, or prescribe the factor. Confirm the rule before this pattern is used on a live building.",
        "How to run a month: edit the yellow cells only. Add or change bills, occupancy dates, discounts, exclusions, and rules. Do not edit gray cells or the Allocation engine. Filter Allocation column scope to Y to read unit lines. Reconciliation should show a difference of $0.00 on every bill that was allocated. Exceptions lists anything the checks caught.",
        "Allocation order, same in the workbook and in rubs.py: (1) drop a bill with a negative amount or a backwards period and list it on Exceptions; (2) convert the amount to cents; (3) take the owner-paid percent off the top; (4) split the remaining pool by weight using largest remainder so the cents sum exactly; (5) take a unit discount from that unit's tenant share and give those cents to Owner; (6) if nobody has weight, the whole pool goes to Owner and Exceptions says so.",
        "Weights. occupant_days uses occupants times inclusive days in the service period. per_unit uses occupied days, and if partial vacancy is owner the vacant days in that unit's month go to Owner. square_footage uses square feet times occupied days. A unit marked vacant contributes no tenant weight even if an occupancy row exists; that conflict is flagged. A utility named in Excluded utilities is left out of the denominator. Days are inclusive: 1 March through 31 March is 31 days, and a move-in on 16 March counts 16 days.",
        "Rounding. Largest remainder on integer cents. If two buckets have the same remainder, the lower key wins. The key is the unit id plus |O for the owner (vacancy) bucket or |T for the tenant bucket, so |O is ahead of |T when the unit id is the same. Percentages are entered as points: 15 means 15%, not 0.15. Sample bill amounts are stored as cents/100 so the demo file is exact; type a normal dollar amount over them for a new month.",
        "Capacity without editing formulas: 8 properties, 30 units, 60 occupancy rows, 32 bills, 48 rules. The readable Allocation list shows the first 400 in-scope lines. Reconciliation, Unit_Statements, and Property_Summary sum the full engine (32 bills x 30 units), so a line past the readable list is still in the totals. Overlapping occupancy rows are flagged. Until they are fixed, per-unit and square-footage day counts add the overlapping stints and cap them at the length of the period, which can overstate occupied days. Occupant-day weights add the overlapping people too.",
        "Sample mess, on purpose: Harbor Court has 4 units, Maple Terrace 8, Cedar Station 12. HC-02 moves in on 16 March. HC-03 is vacant but has an occupancy row. HC-04 has a 10% discount and no gas. Harbor Court trash is 15% owner-paid, then split per occupied day with vacant days to Owner. Maple Terrace gas uses square footage. Cedar Station has common-area electric. HC water has a February bill that ends on 26 February, so 27-28 February are a gap. CS-E-CREDIT is a negative amount and is not allocated.",
        "What was checked: rubs.py is an independent cent-level implementation. pytest covers reconciliation to the cent, partial months, vacancies, exclusions, discounts, owner percent, largest remainder, and the seeded exceptions. A second test opens this file in LibreOffice, recalculates the formulas, and compares every in-scope line to rubs.py. Manual_Check is a separate formula block; its difference cell should be $0.00. Changing an occupant count or an owner percent changes the results without a formula edit.",
        "What was not checked: Excel 365, Excel for Mac, or Excel Online specifically (recalculation was LibreOffice). No legal review. No tenant portal, late fees, taxes, payment application, meter reads, common-area subtraction before the ratio, mid-period rate changes, or billing periods that are not one contiguous date range. Overlapping occupancy is detected, not silently repaired. Credits are not allocated; a negative amount is stopped and listed. This file does not submit bills to residents.",
    ]
    for index, paragraph in enumerate(paragraphs):
        row = 3 + index
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=8)
        ws.cell(row, 1, paragraph).font = FONT_BODY
        ws.cell(row, 1).alignment = WRAP
        ws.row_dimensions[row].height = 48 if index < 2 else 62
    widths(ws, [28, 18, 18, 18, 18, 18, 18, 18])
    ws.row_dimensions[3].height = 48
    ws.page_setup.orientation = "portrait"
    ws.page_setup.fitToWidth = 1
    ws.print_title_rows = "1:1"
    ws.oddHeader.left.text = "Yannick Silva — portfolio demo"


def _properties(ws, data) -> None:
    apply_title(ws, "Properties")
    ws.sheet_properties.tabColor = NAVY
    instruction(ws, "Yellow cells are inputs. Add a property in the next blank row. Do not insert columns. These names are fictional.")
    headers = ["Property ID", "Property name", "Address", "City", "Notes"]
    write_headers(ws, headers)
    for index, prop in enumerate(data.properties):
        values = [prop.property_id, prop.name, prop.address, prop.city, prop.notes]
        for col, value in enumerate(values, start=1):
            ws.cell(DATA_START + index, col, value)
    paint_inputs(ws, first_calc_col=6, last_col=5, capacity=MAX_PROPERTIES)
    widths(ws, [16, 22, 28, 18, 42])
    ws.auto_filter.ref = f"A{HEADER_ROW}:E{PROP_LAST}"


def _units(ws, data) -> None:
    apply_title(ws, "Units")
    ws.sheet_properties.tabColor = NAVY
    instruction(ws, "Yellow cells are inputs. Vacant is Y or N. Discount is points: enter 10 for 10%. Excluded utilities are comma-separated names, for example gas. The vacant flag wins over any occupancy row.")
    headers = ["Unit ID", "Property ID", "Vacant (Y/N)", "Discount % (10 = 10%)", "Square feet", "Excluded utilities", "Notes"]
    write_headers(ws, headers)
    for index, unit in enumerate(data.units):
        row = DATA_START + index
        ws.cell(row, 1, unit.unit_id)
        ws.cell(row, 2, unit.property_id)
        ws.cell(row, 3, "Y" if unit.is_vacant else "N")
        ws.cell(row, 4, float(unit.discount_points))
        if unit.sqft is not None:
            ws.cell(row, 5, unit.sqft)
        if unit.exclude_utilities:
            ws.cell(row, 6, ", ".join(unit.exclude_utilities))
        if unit.notes:
            ws.cell(row, 7, unit.notes)
    paint_inputs(ws, first_calc_col=8, last_col=7, capacity=MAX_UNITS, formats={4: '0.00"%"', 5: "#,##0"})
    widths(ws, [14, 14, 16, 24, 14, 24, 55])
    ws.auto_filter.ref = f"A{HEADER_ROW}:G{UNIT_LAST}"
    yes_no = list_validation("=YesNoList", "Enter Y or N.")
    props = list_validation("=PropID", "Use a property id from Settings_Properties.")
    ws.add_data_validation(yes_no)
    ws.add_data_validation(props)
    yes_no.add(f"C{DATA_START}:C{UNIT_LAST}")
    props.add(f"B{DATA_START}:B{UNIT_LAST}")


def _occupancy(ws, data) -> None:
    apply_title(ws, "Occupancy")
    ws.sheet_properties.tabColor = NAVY
    instruction(ws, "One row per stay. Leave move-out blank if the household is still there. Dates are inclusive. Overlapping stays on the same unit are flagged; fix them before relying on per-unit or square-footage charges.")
    headers = ["Occupancy ID", "Unit ID", "Occupants", "Move in", "Move out", "Notes", "Move-out used (calculated)", "Overlap count (calculated)"]
    write_headers(ws, headers, calculated_from=7)
    for index, record in enumerate(data.occupancy):
        row = DATA_START + index
        ws.cell(row, 1, record.occupancy_id)
        ws.cell(row, 2, record.unit_id)
        ws.cell(row, 3, record.occupants)
        ws.cell(row, 4, record.move_in)
        if record.move_out is not None:
            ws.cell(row, 5, record.move_out)
        if record.notes:
            ws.cell(row, 6, record.notes)
    for row in range(DATA_START, OCC_LAST + 1):
        ws.cell(row, 7, f'=IF(A{row}="","",IF(E{row}="",DATE(2099,12,31),E{row}))')
        ws.cell(row, 8, f'=IF(A{row}="","",COUNTIFS($B${DATA_START}:$B${OCC_LAST},B{row},$D${DATA_START}:$D${OCC_LAST},"<="&G{row},$G${DATA_START}:$G${OCC_LAST},">="&D{row}))')
        ws.cell(row, 7).number_format = "YYYY-MM-DD"
        ws.cell(row, 4).number_format = "YYYY-MM-DD"
        ws.cell(row, 5).number_format = "YYYY-MM-DD"
    paint_inputs(ws, first_calc_col=7, last_col=8, capacity=MAX_OCC, formats={4: "YYYY-MM-DD", 5: "YYYY-MM-DD"})
    widths(ws, [18, 14, 12, 16, 16, 55, 28, 26])
    ws.auto_filter.ref = f"A{HEADER_ROW}:H{OCC_LAST}"
    units = list_validation("=UnitID", "Use a unit id from Settings_Units.")
    ws.add_data_validation(units)
    units.add(f"B{DATA_START}:B{OCC_LAST}")


def _bills(ws, data) -> None:
    apply_title(ws, "Bills")
    ws.sheet_properties.tabColor = NAVY
    instruction(ws, "One row per property, utility, and service period. Sample amounts are cents/100 so the file is exact; type a normal dollar amount over them. A negative amount is flagged and not allocated. Gray columns are checks.")
    headers = [
        "Bill ID",
        "Property ID",
        "Utility",
        "Amount",
        "Period start",
        "Period end",
        "Notes",
        "Valid (calculated)",
        "Prior period end (calculated)",
        "Overlapping bills (calculated)",
    ]
    write_headers(ws, headers, calculated_from=8)
    for index, bill in enumerate(data.bills):
        row = DATA_START + index
        ws.cell(row, 1, bill.bill_id)
        ws.cell(row, 2, bill.property_id)
        ws.cell(row, 3, bill.utility)
        ws.cell(row, 4, cents_formula(bill.amount))
        ws.cell(row, 5, bill.period_start)
        ws.cell(row, 6, bill.period_end)
        if bill.notes:
            ws.cell(row, 7, bill.notes)
    for row in range(DATA_START, BILL_LAST + 1):
        ws.cell(
            row,
            8,
            f'=IF(AND(A{row}<>"",D{row}<>"",D{row}>=0,E{row}<>"",F{row}<>"",F{row}>=E{row},F{row}-E{row}+1<=366),1,0)',
        )
        ws.cell(row, 9, f"={prior_end_formula(row)}")
        ws.cell(
            row,
            10,
            f'=IF(H{row}<>1,"",COUNTIFS($B${DATA_START}:$B${BILL_LAST},B{row},$C${DATA_START}:$C${BILL_LAST},C{row},$E${DATA_START}:$E${BILL_LAST},"<="&F{row},$F${DATA_START}:$F${BILL_LAST},">="&E{row},$H${DATA_START}:$H${BILL_LAST},1))',
        )
        for col in (4,):
            ws.cell(row, col).number_format = '"$"#,##0.00'
        ws.cell(row, 5).number_format = "YYYY-MM-DD"
        ws.cell(row, 6).number_format = "YYYY-MM-DD"
        ws.cell(row, 9).number_format = "YYYY-MM-DD"
    paint_inputs(ws, first_calc_col=8, last_col=10, capacity=MAX_BILLS, formats={4: '"$"#,##0.00', 5: "YYYY-MM-DD", 6: "YYYY-MM-DD"})
    widths(ws, [18, 14, 14, 14, 16, 16, 70, 20, 28, 26])
    ws.auto_filter.ref = f"A{HEADER_ROW}:J{BILL_LAST}"
    utility = list_validation("=UtilityList", "Pick a utility, or add its name to the list on Rules (column AA).")
    props = list_validation("=PropID", "Use a property id from Settings_Properties.")
    ws.add_data_validation(utility)
    ws.add_data_validation(props)
    utility.add(f"C{DATA_START}:C{BILL_LAST}")
    props.add(f"B{DATA_START}:B{BILL_LAST}")


def _rules(ws, data) -> None:
    apply_title(ws, "Rules")
    ws.sheet_properties.tabColor = NAVY
    instruction(ws, "One rule per property and utility. Method is occupant_days, per_unit, or square_footage. Owner-paid % is points: 15 means 15% off the top. Partial vacancy owner sends vacant days to Owner; absorb leaves them out of the denominator. Vacant equivalent is used only by occupant_days when partial vacancy is owner (1 means one phantom occupant on vacant days).")
    headers = [
        "Property ID",
        "Utility",
        "Method",
        "Owner-paid % (15 = 15%)",
        "Partial vacancy",
        "Vacant equivalent",
        "Notes",
        "Rule key (calculated)",
    ]
    write_headers(ws, headers, calculated_from=8)
    for index, rule in enumerate(data.rules):
        row = DATA_START + index
        ws.cell(row, 1, rule.property_id)
        ws.cell(row, 2, rule.utility)
        ws.cell(row, 3, rule.method)
        ws.cell(row, 4, float(rule.owner_paid_points))
        ws.cell(row, 5, rule.partial_vacancy)
        ws.cell(row, 6, rule.vacant_equivalent)
        if rule.notes:
            ws.cell(row, 7, rule.notes)
    for row in range(DATA_START, RULE_LAST + 1):
        ws.cell(row, 8, f'=IF(A{row}="","",A{row}&"|"&B{row})')
    paint_inputs(ws, first_calc_col=8, last_col=8, capacity=MAX_RULES, formats={4: '0.00"%"'})
    widths(ws, [16, 14, 20, 26, 18, 20, 78, 22])
    ws.auto_filter.ref = f"A{HEADER_ROW}:H{RULE_LAST}"
    lists = {
        "AA": ["water", "sewer", "trash", "gas", "electric", "other"],
        "AB": ["occupant_days", "per_unit", "square_footage"],
        "AC": ["Y", "N"],
        "AD": ["absorb", "owner"],
    }
    labels = {"AA": "Utility list", "AB": "Method list", "AC": "Yes / No", "AD": "Partial vacancy"}
    for column, values in lists.items():
        ws[f"{column}4"] = labels[column]
        ws[f"{column}4"].font = FONT_HEADER
        ws[f"{column}4"].fill = FILL_TEAL
        for index, value in enumerate(values):
            ws[f"{column}{5 + index}"] = value
            ws[f"{column}{5 + index}"].fill = FILL_GOLD
    ws["AA11"] = "Add a utility name in the yellow cells below if you bill something else."
    ws["AA11"].font = FONT_SMALL
    for row in range(12, 21):
        ws.cell(row, 27).fill = FILL_GOLD
    methods = list_validation("=MethodList", "Use occupant_days, per_unit, or square_footage.")
    partials = list_validation("=PartialList", "Use absorb or owner.")
    utilities = list_validation("=UtilityList", "Pick a utility or add it in column AA.")
    props = list_validation("=PropID", "Use a property id from Settings_Properties.")
    for rule in (methods, partials, utilities, props):
        ws.add_data_validation(rule)
    methods.add(f"C{DATA_START}:C{RULE_LAST}")
    partials.add(f"E{DATA_START}:E{RULE_LAST}")
    utilities.add(f"B{DATA_START}:B{RULE_LAST}")
    props.add(f"A{DATA_START}:A{RULE_LAST}")
    ws.column_dimensions["AA"].width = 28
    ws.column_dimensions["AB"].width = 20
    ws.column_dimensions["AC"].width = 14
    ws.column_dimensions["AD"].width = 18


def _allocation(ws) -> None:
    apply_title(ws, "Allocation")
    ws.sheet_properties.tabColor = "5B7C4A"
    instruction(ws, "Readable lines are on the left (first 400 in-scope unit lines). The engine on the right is formulas — do not edit it. Filter scope to Y, or just read this list. Totals on Reconciliation include every engine row, including any line past this list.")
    report_headers = [
        "Property",
        "Unit",
        "Utility",
        "Period start",
        "Period end",
        "Bill amount",
        "Occupant-days",
        "Tenant gross",
        "Discount",
        "Amount due",
        "Owner on unit",
        "Bill ID",
        "scope",
    ]
    for index, header in enumerate(report_headers, start=1):
        item = ws.cell(ENG_HEADER, index, header)
        item.fill = FILL_NAVY
        item.font = FONT_HEADER
        item.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
    pulls = {
        1: "bill_property",
        2: "unit_id",
        3: "utility",
        4: "period_start",
        5: "period_end",
        6: "amount_cents",
        7: "occupant_days",
        8: "gross_t",
        9: "discount_cents",
        10: "tenant_net",
        11: "owner_plus_discount",
        12: "bill_id",
        13: "scope",
    }
    money_cols = {6, 8, 9, 10, 11}
    date_cols = {4, 5}
    for row in range(ENG_START, ENG_START + REPORT_ROWS):
        nth = row - ENG_HEADER
        match = f"MATCH({nth},Eng_line_index,0)"
        for col, field in pulls.items():
            if field == "owner_plus_discount":
                formula = (
                    f'IFERROR((INDEX(Eng_gross_o,{match})+INDEX(Eng_discount_cents,{match}))/100,"")'
                )
            elif field in {"amount_cents", "gross_t", "discount_cents", "tenant_net"}:
                formula = f'IFERROR(INDEX(Eng_{field},{match})/100,"")'
            else:
                formula = f'IFERROR(INDEX(Eng_{field},{match}),"")'
            item = ws.cell(row, col, f"={formula}")
            item.font = FONT_BODY
            item.border = THIN
            if col in money_cols:
                item.number_format = '"$"#,##0.00'
            elif col in date_cols:
                item.number_format = "YYYY-MM-DD"
    for index, field in enumerate(ENGINE_FIELDS, start=21):
        header = ws.cell(ENG_HEADER, index, field)
        header.fill = FILL_TEAL
        header.font = FONT_HEADER
        header.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center", textRotation=90)
    ws.row_dimensions[ENG_HEADER].height = 36
    ws.freeze_panes = "A8"
    ws.auto_filter.ref = f"A{ENG_HEADER}:M{ENG_START + REPORT_ROWS - 1}"
    for row in range(ENG_START, ENG_LAST + 1):
        formulas = engine_formulas(row)
        for field, formula in formulas.items():
            column = column_index_from_string(ENG_COL[field])
            item = ws.cell(row, column, f"={formula}")
            item.font = Font(name="Calibri", size=9, color="4A5560")
            item.fill = FILL_CALC
        for field in ("amount_cents", "owner_pct_cents", "pool_cents", "gross_t", "gross_o", "discount_cents", "tenant_net", "unallocated"):
            ws.cell(row, column_index_from_string(ENG_COL[field])).number_format = "#,##0"
    widths(ws, [14, 12, 12, 14, 14, 14, 16, 14, 12, 14, 16, 16, 10])
    ws.column_dimensions["T"].width = 3
    for letter in ENG_COL.values():
        ws.column_dimensions[letter].width = 14
    ws.auto_filter.ref = f"A{ENG_HEADER}:M{ENG_START + REPORT_ROWS - 1}"
    ws.sheet_view.zoomScale = 110
    ws.oddHeader.center.text = "In-scope allocation lines"


def _statements(ws) -> None:
    apply_title(ws, "Unit statements")
    ws.sheet_properties.tabColor = "5B7C4A"
    instruction(ws, "One row per unit slot. Amounts sum every allocated bill in the engine, including lines past the readable Allocation list. Other is any utility that is not water, sewer, trash, gas, or electric. Filter to the unit you are billing.")
    headers = [
        "Unit ID",
        "Property",
        "Vacant",
        "Amount due",
        "Water",
        "Sewer",
        "Trash",
        "Gas",
        "Electric",
        "Other",
        "Discounts",
        "Owner on unit",
    ]
    write_headers(ws, headers)
    for index in range(MAX_UNITS):
        row = DATA_START + index
        ws.cell(row, 1, f'=IF(INDEX(UnitID,{index + 1})="","",INDEX(UnitID,{index + 1}))')
        ws.cell(row, 2, f'=IF(A{row}="","",INDEX(UnitProp,{index + 1}))')
        ws.cell(row, 3, f'=IF(A{row}="","",INDEX(UnitVac,{index + 1}))')
        ws.cell(row, 4, f'=IF(A{row}="","",SUMIF(Eng_unit_id,A{row},Eng_tenant_net)/100)')
        for col, utility in enumerate(["water", "sewer", "trash", "gas", "electric"], start=5):
            ws.cell(
                row,
                col,
                f'=IF(A{row}="","",SUMIFS(Eng_tenant_net,Eng_unit_id,A{row},Eng_utility,"{utility}")/100)',
            )
        ws.cell(row, 10, f'=IF(A{row}="","",D{row}-E{row}-F{row}-G{row}-H{row}-I{row})')
        ws.cell(row, 11, f'=IF(A{row}="","",SUMIF(Eng_unit_id,A{row},Eng_discount_cents)/100)')
        ws.cell(
            row,
            12,
            f'=IF(A{row}="","",(SUMIF(Eng_unit_id,A{row},Eng_gross_o)+SUMIF(Eng_unit_id,A{row},Eng_discount_cents))/100)',
        )
        for col in range(4, 13):
            ws.cell(row, col).number_format = '"$"#,##0.00'
            ws.cell(row, col).font = FONT_BODY
            ws.cell(row, col).fill = FILL_CALC
            ws.cell(row, col).border = THIN
        for col in range(1, 4):
            ws.cell(row, col).font = FONT_BODY
            ws.cell(row, col).fill = FILL_CALC
            ws.cell(row, col).border = THIN
    widths(ws, [14, 14, 12, 16, 14, 14, 14, 14, 14, 14, 14, 18])
    ws.auto_filter.ref = f"A{HEADER_ROW}:L{UNIT_LAST}"
    ws.conditional_formatting.add(f"D{DATA_START}:D{UNIT_LAST}", CellIsRule(operator="greaterThan", formula=["0"], fill=FILL_GREEN))


def _summary(ws) -> None:
    apply_title(ws, "Property summary")
    ws.sheet_properties.tabColor = "5B7C4A"
    instruction(ws, "Valid bills are non-negative, with a real period of at most 366 days. Tenant charges plus the owner share should equal those bills. The owner share includes the percent off the top, vacant-day shares, discounts, and any pool that had no eligible weight. The utility columns are the tenant portion only.")
    headers = [
        "Property ID",
        "Property name",
        "Units",
        "Vacant units",
        "Valid bills",
        "Tenant charges",
        "Owner share",
        "Difference",
        "Tenant water",
        "Tenant sewer",
        "Tenant trash",
        "Tenant gas",
        "Tenant electric",
    ]
    write_headers(ws, headers)
    for index in range(MAX_PROPERTIES):
        row = DATA_START + index
        ws.cell(row, 1, f'=IF(INDEX(PropID,{index + 1})="","",INDEX(PropID,{index + 1}))')
        ws.cell(row, 2, f'=IF(A{row}="","",INDEX(PropName,{index + 1}))')
        ws.cell(row, 3, f'=IF(A{row}="","",COUNTIF(UnitProp,A{row}))')
        ws.cell(row, 4, f'=IF(A{row}="","",COUNTIFS(UnitProp,A{row},UnitVac,"Y"))')
        ws.cell(row, 5, f'=IF(A{row}="","",SUMIFS(BillAmt,BillProp,A{row},BillValid,1))')
        ws.cell(row, 6, f'=IF(A{row}="","",SUMIF(Eng_bill_property,A{row},Eng_tenant_net)/100)')
        ws.cell(
            row,
            7,
            f'=IF(A{row}="","",(SUMIF(Eng_bill_property,A{row},Eng_owner_pct_cents)+SUMIF(Eng_bill_property,A{row},Eng_gross_o)+SUMIF(Eng_bill_property,A{row},Eng_discount_cents)+SUMIF(Eng_bill_property,A{row},Eng_unallocated))/100)',
        )
        ws.cell(row, 8, f'=IF(A{row}="","",E{row}-F{row}-G{row})')
        for col, utility in enumerate(["water", "sewer", "trash", "gas", "electric"], start=9):
            ws.cell(
                row,
                col,
                f'=IF(A{row}="","",SUMIFS(Eng_tenant_net,Eng_bill_property,A{row},Eng_utility,"{utility}")/100)',
            )
        for col in range(1, 14):
            item = ws.cell(row, col)
            item.font = FONT_BODY
            item.fill = FILL_CALC
            item.border = THIN
            if col >= 5:
                item.number_format = '"$"#,##0.00'
    widths(ws, [14, 20, 12, 14, 16, 16, 16, 14, 14, 14, 14, 14, 14])
    ws.auto_filter.ref = f"A{HEADER_ROW}:M{PROP_LAST}"
    ws.conditional_formatting.add(
        f"H{DATA_START}:H{PROP_LAST}",
        CellIsRule(operator="notEqual", formula=["0"], fill=FILL_RED),
    )


def _reconciliation(ws) -> None:
    apply_title(ws, "Reconciliation")
    ws.sheet_properties.tabColor = "5B7C4A"
    instruction(ws, "Every allocated bill should show a difference of $0.00. Excluded means the bill failed a hard check (negative amount or a bad period) and was not spread. Tied with exceptions means the cents match and Exceptions has a warning on that bill id. A property-level warning, such as occupancy on a vacant unit, stays on Exceptions even when these rows say Tied.")
    headers = [
        "Bill ID",
        "Property",
        "Utility",
        "Period start",
        "Period end",
        "Amount",
        "Status",
        "Tenant charges",
        "Owner share",
        "Difference",
        "Notes",
    ]
    write_headers(ws, headers)
    ex_last = EX_DETAIL_START + MAX_BILLS + MAX_UNITS + MAX_OCC + MAX_RULES - 1
    for index in range(MAX_BILLS):
        row = DATA_START + index
        ws.cell(row, 1, f'=IF(INDEX(BillID,{index + 1})="","",INDEX(BillID,{index + 1}))')
        ws.cell(row, 2, f'=IF(A{row}="","",INDEX(BillProp,{index + 1}))')
        ws.cell(row, 3, f'=IF(A{row}="","",INDEX(BillUtil,{index + 1}))')
        ws.cell(row, 4, f'=IF(A{row}="","",INDEX(BillStart,{index + 1}))')
        ws.cell(row, 5, f'=IF(A{row}="","",INDEX(BillEnd,{index + 1}))')
        ws.cell(row, 6, f'=IF(A{row}="","",INDEX(BillAmt,{index + 1}))')
        ws.cell(row, 8, f'=IF(A{row}="","",SUMIF(Eng_bill_id,A{row},Eng_tenant_net)/100)')
        ws.cell(
            row,
            9,
            f'=IF(A{row}="","",(SUMIF(Eng_bill_id,A{row},Eng_owner_pct_cents)+SUMIF(Eng_bill_id,A{row},Eng_gross_o)+SUMIF(Eng_bill_id,A{row},Eng_discount_cents)+SUMIF(Eng_bill_id,A{row},Eng_unallocated))/100)',
        )
        ws.cell(row, 10, f'=IF(OR(A{row}="",INDEX(BillValid,{index + 1})<>1),"",F{row}-H{row}-I{row})')
        ws.cell(
            row,
            7,
            (
                f'=IF(A{row}="","",IF(INDEX(BillValid,{index + 1})<>1,"Excluded",'
                f'IF(ABS(J{row})>0.001,"Break",'
                f'IF(SUMPRODUCT((Exceptions!$F${EX_DETAIL_START}:$F${ex_last}=A{row})*(Exceptions!$G${EX_DETAIL_START}:$G${ex_last}<>""))>0,'
                f'"Tied with exceptions","Tied"))))'
            ),
        )
        ws.cell(row, 11, f'=IF(A{row}="","",INDEX(Bills!G${DATA_START}:G${BILL_LAST},{index + 1}))')
        for col in range(1, 12):
            item = ws.cell(row, col)
            item.font = FONT_BODY
            item.fill = FILL_CALC
            item.border = THIN
        for col in (6, 8, 9, 10):
            ws.cell(row, col).number_format = '"$"#,##0.00'
        for col in (4, 5):
            ws.cell(row, col).number_format = "YYYY-MM-DD"
    widths(ws, [18, 14, 14, 16, 16, 14, 24, 16, 16, 14, 70])
    ws.auto_filter.ref = f"A{HEADER_ROW}:K{BILL_LAST}"
    ws.conditional_formatting.add(f"G{DATA_START}:G{BILL_LAST}", FormulaRule(formula=[f'LEFT(G{DATA_START},5)="Break"'], fill=FILL_RED))
    ws.conditional_formatting.add(f"J{DATA_START}:J{BILL_LAST}", CellIsRule(operator="notEqual", formula=["0"], fill=FILL_RED))
    ws.conditional_formatting.add(f"G{DATA_START}:G{BILL_LAST}", FormulaRule(formula=[f'G{DATA_START}="Tied"'], fill=FILL_GREEN))


def _manual(ws) -> None:
    apply_title(ws, "Manual check")
    ws.sheet_properties.tabColor = "8C4A2F"
    instruction(ws, "Pick any bill and any unit. The amount due is calculated again in the table below, from the yellow inputs, not by copying Allocation. Difference must be $0.00. Odd cents use largest remainder; the lower unit id wins, and within a unit the |O bucket is ahead of |T.")
    ws["A4"] = "Bill ID"
    ws["B4"] = "HC-W-2026-03"
    ws["A5"] = "Unit ID"
    ws["B5"] = "HC-04"
    for addr in ("A4", "A5"):
        ws[addr].font = FONT_HEADER
        ws[addr].fill = FILL_NAVY
    for addr in ("B4", "B5"):
        ws[addr].fill = FILL_GOLD
        ws[addr].font = Font(name="Calibri", bold=True, size=14, color=NAVY)
        ws[addr].border = THIN
    labels = [
        (4, "Property", f'=IFERROR(INDEX(BillProp,MATCH($B$4,BillID,0)),"")'),
        (5, "Utility", f'=IFERROR(INDEX(BillUtil,MATCH($B$4,BillID,0)),"")'),
        (6, "Period start", f'=IFERROR(INDEX(BillStart,MATCH($B$4,BillID,0)),"")'),
        (7, "Period end", f'=IFERROR(INDEX(BillEnd,MATCH($B$4,BillID,0)),"")'),
        (8, "Days in period", '=IF(OR(D6="",D7=""),"",D7-D6+1)'),
        (9, "Bill amount", f'=IFERROR(INDEX(BillAmt,MATCH($B$4,BillID,0)),"")'),
        (10, "Valid bill", f'=IFERROR(INDEX(BillValid,MATCH($B$4,BillID,0)),0)'),
        (11, "Method", '=IF(D4="","",IFERROR(INDEX(RuleMethod,MATCH(D4&"|"&D5,RuleKey,0)),""))'),
        (12, "Owner-paid %", '=IF(D11="","",IFERROR(INDEX(RuleOwner,MATCH(D4&"|"&D5,RuleKey,0)),""))'),
        (13, "Owner-paid cents off the top", '=IF(OR(D10<>1,D11=""),0,QUOTIENT(ROUND(D9*100,0)*ROUND(D12*100,0)+5000,10000))'),
        (14, "Pool (cents)", '=IF(OR(D10<>1,D11=""),0,ROUND(D9*100,0)-D13)'),
        (15, "All weights", "=SUM(J28:J57)+SUM(K28:K57)"),
        (16, "This unit occupant-days", '=IF($B$5="","",SUMIF($A$28:$A$57,$B$5,$H$28:$H$57))'),
        (17, "This unit occupied days", '=IF($B$5="","",SUMIF($A$28:$A$57,$B$5,$I$28:$I$57))'),
        (18, "This unit tenant weight", '=IF($B$5="","",SUMIF($A$28:$A$57,$B$5,$J$28:$J$57))'),
        (19, "This unit owner weight", '=IF($B$5="","",SUMIF($A$28:$A$57,$B$5,$K$28:$K$57))'),
        (20, "Tenant gross", '=IF($B$5="","",SUMIF($A$28:$A$57,$B$5,$T$28:$T$57)/100)'),
        (21, "Discount", '=IF($B$5="","",SUMIF($A$28:$A$57,$B$5,$V$28:$V$57)/100)'),
        (22, "Amount due", '=IF($B$5="","",SUMIF($A$28:$A$57,$B$5,$W$28:$W$57)/100)'),
        (23, "Owner portion on this unit", '=IF($B$5="","",(SUMIF($A$28:$A$57,$B$5,$U$28:$U$57)+SUMIF($A$28:$A$57,$B$5,$V$28:$V$57))/100)'),
        (24, "Allocation sheet amount due", '=IF(OR($B$4="",$B$5=""),"",SUMIFS(Eng_tenant_net,Eng_bill_id,$B$4,Eng_unit_id,$B$5)/100)'),
        (25, "Difference (must be 0.00)", '=IF(OR($B$4="",$B$5=""),"",D22-D24)'),
    ]
    for row, label, formula in labels:
        ws.cell(row, 3, label).font = FONT_BODY
        ws.cell(row, 3).alignment = Alignment(vertical="center")
        item = ws.cell(row, 4, formula if str(formula).startswith("=") else f"={formula}")
        item.font = Font(name="Calibri", bold=True, size=12, color=NAVY)
        item.fill = FILL_CALC
        item.border = THIN
    for row in (6, 7):
        ws.cell(row, 4).number_format = "YYYY-MM-DD"
    for row in (9, 20, 21, 22, 23, 24, 25):
        ws.cell(row, 4).number_format = '"$"#,##0.00'
    ws["D12"].number_format = '0.00"%"'
    ws["A27"] = "Working table for the selected bill. Weights of units on other properties stay at zero."
    ws["A27"].font = FONT_SMALL
    block_headers = [
        "Unit",
        "Property",
        "On bill",
        "Vacant",
        "Discount bps",
        "Sqft",
        "Excluded",
        "Occupant-days",
        "Occupied days",
        "Tenant weight",
        "Owner weight",
        "Floor T",
        "Floor O",
        "Rem T",
        "Rem O",
        "Rank T",
        "Rank O",
        "Extra T",
        "Extra O",
        "Gross T",
        "Gross O",
        "Discount cents",
        "Net cents",
        "Key T",
        "Key O",
    ]
    for index, header in enumerate(block_headers, start=1):
        item = ws.cell(27, index, header)
        item.fill = FILL_NAVY
        item.font = FONT_HEADER
        item.alignment = Alignment(wrap_text=True, vertical="center")
    ws.row_dimensions[27].height = 30
    for index in range(MAX_UNITS):
        row = 28 + index
        unit_index = index + 1
        ws.cell(row, 1, f'=IF(INDEX(UnitID,{unit_index})="","",INDEX(UnitID,{unit_index}))')
        ws.cell(row, 2, f'=IF(A{row}="","",INDEX(UnitProp,{unit_index}))')
        ws.cell(row, 3, f'=IF(OR($D$4="",A{row}="",B{row}<>$D$4),"","Y")')
        ws.cell(row, 4, f'=IF(A{row}="","",INDEX(UnitVac,{unit_index}))')
        ws.cell(row, 5, f'=IF(OR(A{row}="",INDEX(UnitDisc,{unit_index})<0,INDEX(UnitDisc,{unit_index})>100),"",ROUND(INDEX(UnitDisc,{unit_index})*100,0))')
        ws.cell(row, 6, f'=IF(A{row}="","",IF(INDEX(UnitSqft,{unit_index})="",0,INDEX(UnitSqft,{unit_index})))')
        ws.cell(
            row,
            7,
            f'=IF(OR(A{row}="",$D$5="",INDEX(UnitExcl,{unit_index})=""),0,IF(ISNUMBER(SEARCH(","&$D$5&",",","&SUBSTITUTE(INDEX(UnitExcl,{unit_index})," ","")&",")),1,0))',
        )
        ws.cell(
            row,
            8,
            f'=IF(OR(C{row}<>"Y",D{row}="Y",$D$6="",$D$7=""),0,{sumproduct_days(f"A{row}", "$D$6", "$D$7", True)})',
        )
        ws.cell(
            row,
            9,
            f'=IF(OR(C{row}<>"Y",D{row}="Y",$D$6="",$D$7=""),0,MIN($D$8,{sumproduct_days(f"A{row}", "$D$6", "$D$7", False)}))',
        )
        ws.cell(
            row,
            10,
            f'=IF(OR(C{row}<>"Y",$D$10<>1,G{row}=1,$D$11=""),0,IF($D$11="occupant_days",IF(D{row}="Y",0,H{row}),IF($D$11="per_unit",I{row},IF($D$11="square_footage",IF(F{row}<=0,0,F{row}*I{row}),0))))',
        )
        ws.cell(
            row,
            11,
            (
                f'=IF(OR(C{row}<>"Y",$D$10<>1,G{row}=1,$D$11="",'
                f'IFERROR(INDEX(RulePartial,MATCH($D$4&"|"&$D$5,RuleKey,0)),"")<>"owner"),0,'
                f'IF($D$11="occupant_days",IFERROR(INDEX(RuleEquiv,MATCH($D$4&"|"&$D$5,RuleKey,0)),0)*($D$8-I{row}),'
                f'IF($D$11="per_unit",$D$8-I{row},IF($D$11="square_footage",IF(F{row}<=0,0,F{row}*($D$8-I{row})),0))))'
            ),
        )
        ws.cell(row, 12, f'=IF(OR(J{row}<=0,$D$15=""),0,QUOTIENT($D$14*J{row},$D$15))')
        ws.cell(row, 13, f'=IF(OR(K{row}<=0,$D$15=""),0,QUOTIENT($D$14*K{row},$D$15))')
        ws.cell(row, 14, f'=IF(J{row}<=0,0,MOD($D$14*J{row},$D$15))')
        ws.cell(row, 15, f'=IF(K{row}<=0,0,MOD($D$14*K{row},$D$15))')
        ws.cell(row, 24, f'=IF(J{row}<=0,"",A{row}&"|T")')
        ws.cell(row, 25, f'=IF(K{row}<=0,"",A{row}&"|O")')
        ws.cell(
            row,
            16,
            (
                f'=IF(J{row}<=0,0,SUMPRODUCT(($C$28:$C$57="Y")*($J$28:$J$57>0)*((($N$28:$N$57>N{row})+(($N$28:$N$57=N{row})*($X$28:$X$57<X{row})))))'
                f'+SUMPRODUCT(($C$28:$C$57="Y")*($K$28:$K$57>0)*((($O$28:$O$57>N{row})+(($O$28:$O$57=N{row})*($Y$28:$Y$57<X{row}))))))'
            ),
        )
        ws.cell(
            row,
            17,
            (
                f'=IF(K{row}<=0,0,SUMPRODUCT(($C$28:$C$57="Y")*($J$28:$J$57>0)*((($N$28:$N$57>O{row})+(($N$28:$N$57=O{row})*($X$28:$X$57<Y{row})))))'
                f'+SUMPRODUCT(($C$28:$C$57="Y")*($K$28:$K$57>0)*((($O$28:$O$57>O{row})+(($O$28:$O$57=O{row})*($Y$28:$Y$57<Y{row}))))))'
            ),
        )
        ws.cell(row, 18, f'=IF(AND(J{row}>0,P{row}<$D$14-SUM($L$28:$L$57)-SUM($M$28:$M$57)),1,0)')
        ws.cell(row, 19, f'=IF(AND(K{row}>0,Q{row}<$D$14-SUM($L$28:$L$57)-SUM($M$28:$M$57)),1,0)')
        ws.cell(row, 20, f"=L{row}+R{row}")
        ws.cell(row, 21, f"=M{row}+S{row}")
        ws.cell(row, 22, f'=IF(OR(T{row}<=0,E{row}=""),0,QUOTIENT(T{row}*E{row}+5000,10000))')
        ws.cell(row, 23, f"=T{row}-V{row}")
        for col in range(1, 26):
            item = ws.cell(row, col)
            item.font = Font(name="Calibri", size=9)
            item.fill = FILL_CALC
            item.border = THIN
    ws.conditional_formatting.add("D25", CellIsRule(operator="notEqual", formula=["0"], fill=FILL_RED))
    ws.conditional_formatting.add("D25", CellIsRule(operator="equal", formula=["0"], fill=FILL_GREEN))
    bills = list_validation("=BillID", "Pick a bill id.")
    unit_ids = list_validation("=UnitID", "Pick a unit id.")
    ws.add_data_validation(bills)
    ws.add_data_validation(unit_ids)
    bills.add("B4")
    unit_ids.add("B5")
    widths(ws, [16, 18, 28, 22, 14, 12, 12, 16, 16, 14, 14, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 16, 12, 14, 14])
    ws.freeze_panes = "A28"
    ws.row_dimensions[4].height = 22
    ws.row_dimensions[5].height = 22


def _exceptions(ws) -> None:
    apply_title(ws, "Exceptions")
    ws.sheet_properties.tabColor = "8C2F2F"
    instruction(ws, "Open items are listed first. The rows underneath are the checks themselves, including rows that are currently clear, so a change in the inputs shows up here without editing a formula.")
    ws["A3"] = "Open items"
    ws["B3"] = f'=SUMPRODUCT((G{EX_DETAIL_START}:G{_ex_last()}<>"")*1)'
    ws["A3"].font = FONT_HEADER
    ws["A3"].fill = FILL_NAVY
    ws["B3"].font = Font(name="Calibri", bold=True, size=18, color="8C2F2F")
    ws["B3"].fill = FILL_RED
    headers = ["Source", "Record", "Property", "Unit", "Utility", "Bill ID", "Message", "Issue number"]
    for index, header in enumerate(headers, start=1):
        item = ws.cell(6, index, header)
        item.fill = FILL_NAVY
        item.font = FONT_HEADER
    for slot_index in range(1, 16):
        row = 7 + slot_index
        match = f"MATCH({slot_index},$H${EX_DETAIL_START}:$H${_ex_last()},0)"
        for col, source_col in enumerate(["A", "B", "C", "D", "E", "F", "G"], start=1):
            ws.cell(
                row,
                col,
                f'=IFERROR(INDEX(${source_col}${EX_DETAIL_START}:${source_col}${_ex_last()},{match}),"")',
            )
            ws.cell(row, col).font = FONT_BODY
            ws.cell(row, col).fill = FILL_GOLD
    detail_row = EX_DETAIL_START
    detail_row = _write_bill_checks(ws, detail_row)
    detail_row = _write_unit_checks(ws, detail_row)
    detail_row = _write_occupancy_checks(ws, detail_row)
    detail_row = _write_rule_checks(ws, detail_row)
    first = EX_DETAIL_START
    ws.cell(first, 8, f'=IF(G{first}="",0,1)')
    for row in range(first + 1, detail_row):
        ws.cell(row, 8, f'=IF(G{row}="",H{row - 1},H{row - 1}+1)')
        ws.cell(row, 8).font = Font(name="Calibri", size=9, color="4A5560")
    ws.conditional_formatting.add(
        f"G{EX_DETAIL_START}:G{_ex_last()}",
        FormulaRule(formula=[f'G{EX_DETAIL_START}<>""'], fill=FILL_RED),
    )
    widths(ws, [16, 20, 14, 14, 14, 18, 110, 16])
    ws.freeze_panes = "A7"
    ws.auto_filter.ref = f"A6:G22"


def _ex_last() -> int:
    return EX_DETAIL_START + MAX_BILLS + MAX_UNITS + MAX_OCC + MAX_RULES - 1


def _write_bill_checks(ws, row: int) -> int:
    for index in range(MAX_BILLS):
        source = DATA_START + index
        slot = index * MAX_UNITS + 1
        # Nested IF, not AND, because LibreOffice evaluates every AND argument
        # and a blank prior-end date would turn the whole message into #VALUE!.
        message = (
            f'IF(Bills!A{source}="","",'
            f'IF(NOT(ISNUMBER(Bills!D{source})),"Blank bill amount. ",IF(Bills!D{source}<0,"Negative bill amount on "&Bills!A{source}&"; this row was not allocated. ",""))'
            f'&IF(OR(Bills!E{source}="",Bills!F{source}=""),"Invalid service period. ",IF(Bills!F{source}<Bills!E{source},"Invalid service period. ",IF(Bills!F{source}-Bills!E{source}+1>366,"Service period longer than 366 days. ","")))'
            f'&IF(COUNTIF(BillID,Bills!A{source})>1,"Duplicate bill id. ","")'
            f'&IF(Bills!H{source}<>1,"",IF(COUNTIF(RuleKey,Bills!B{source}&"|"&Bills!C{source})=0,"No allocation rule for this property and utility. The bill was charged to Owner. ",""))'
            f'&IF(Bills!H{source}<>1,"",IF(NOT(ISNUMBER(Bills!I{source})),"",IF(Bills!E{source}>Bills!I{source}+1,"Service period gap from "&TEXT(Bills!I{source}+1,"YYYY-MM-DD")&" through "&TEXT(Bills!E{source}-1,"YYYY-MM-DD")&". ","")))'
            f'&IF(Bills!H{source}<>1,"",IF(NOT(ISNUMBER(Bills!J{source})),"",IF(Bills!J{source}>1,"Service period overlaps another bill for the same utility. Both bills are still allocated. ","")))'
            f'&IF(Bills!H{source}<>1,"",IF(COUNTIF(RuleKey,Bills!B{source}&"|"&Bills!C{source})=0,"",IF(NOT(ISNUMBER(INDEX(Eng_pool_cents,{slot}))),"",IF(INDEX(Eng_pool_cents,{slot})<=0,"",IF(SUMIF(Eng_bill_id,Bills!A{source},Eng_tenant_weight)+SUMIF(Eng_bill_id,Bills!A{source},Eng_owner_weight)=0,"No eligible weight; the tenant pool was assigned to Owner. ","")))))'
            f')'
        )
        _detail_row(
            ws,
            row,
            "Bill",
            f'=IF(Bills!A{source}="","",Bills!A{source})',
            f'=IF(Bills!A{source}="","",Bills!B{source})',
            '=""',
            f'=IF(Bills!A{source}="","",Bills!C{source})',
            f'=IF(Bills!A{source}="","",Bills!A{source})',
            f"={message}",
        )
        row += 1
    return row


def _write_unit_checks(ws, row: int) -> int:
    for index in range(MAX_UNITS):
        source = DATA_START + index
        message = (
            f'IF(Settings_Units!A{source}="","",'
            f'IF(AND(Settings_Units!C{source}="Y",COUNTIFS(OccUnit,Settings_Units!A{source},OccCount,">0")>0),"Occupancy is recorded on "&Settings_Units!A{source}&", which is marked vacant. The vacant flag wins and the unit is not billed as occupied. ","")'
            f'&IF(OR(Settings_Units!D{source}<0,Settings_Units!D{source}>100),"Discount must be between 0 and 100 (enter 10 for 10%). ","")'
            f'&IF(AND(Settings_Units!A{source}<>"",COUNTIF(UnitID,Settings_Units!A{source})>1),"Duplicate unit id. ","")'
            f'&IF(AND(Settings_Units!A{source}<>"",COUNTIF(PropID,Settings_Units!B{source})=0),"Unknown property. ","")'
            f'&IF(AND(Settings_Units!A{source}<>"",OR(Settings_Units!E{source}="",Settings_Units!E{source}<=0),COUNTIFS(RuleProp,Settings_Units!B{source},RuleMethod,"square_footage")>0),"Square footage is blank but a rule for this property uses square footage. ",""))'
        )
        _detail_row(
            ws,
            row,
            "Unit",
            f'=IF(Settings_Units!A{source}="","",Settings_Units!A{source})',
            f'=IF(Settings_Units!A{source}="","",Settings_Units!B{source})',
            f'=IF(Settings_Units!A{source}="","",Settings_Units!A{source})',
            '=""',
            '=""',
            f"={message}",
        )
        row += 1
    return row


def _write_occupancy_checks(ws, row: int) -> int:
    for index in range(MAX_OCC):
        source = DATA_START + index
        message = (
            f'IF(Occupancy!A{source}="","",'
            f'IF(Occupancy!D{source}="","Move-in date is blank. ","")'
            f'&IF(Occupancy!C{source}<0,"Occupant count is negative. ","")'
            f'&IF(AND(Occupancy!E{source}<>"",Occupancy!D{source}<>"",Occupancy!E{source}<Occupancy!D{source}),"Move-out is before move-in. ","")'
            f'&IF(AND(Occupancy!D{source}<>"",Occupancy!H{source}>1),"Overlapping occupancy on "&Occupancy!B{source}&". Per-unit and square-footage day counts can be overstated until the dates are corrected. ","")'
            f'&IF(COUNTIF(UnitID,Occupancy!B{source})=0,"Unknown unit "&Occupancy!B{source}&". ",""))'
        )
        _detail_row(
            ws,
            row,
            "Occupancy",
            f'=IF(Occupancy!A{source}="","",Occupancy!A{source})',
            f'=IF(Occupancy!B{source}="","",IFERROR(INDEX(UnitProp,MATCH(Occupancy!B{source},UnitID,0)),""))',
            f'=IF(Occupancy!A{source}="","",Occupancy!B{source})',
            '=""',
            '=""',
            f"={message}",
        )
        row += 1
    return row


def _write_rule_checks(ws, row: int) -> int:
    for index in range(MAX_RULES):
        source = DATA_START + index
        message = (
            f'IF(Rules!A{source}="","",'
            f'IF(OR(Rules!D{source}<0,Rules!D{source}>100),"Owner-paid percent must be between 0 and 100 (enter 15 for 15%). ","")'
            f'&IF(AND(Rules!C{source}<>"occupant_days",Rules!C{source}<>"per_unit",Rules!C{source}<>"square_footage"),"Unknown allocation method. ","")'
            f'&IF(AND(Rules!E{source}<>"absorb",Rules!E{source}<>"owner"),"Partial vacancy must be absorb or owner. ","")'
            f'&IF(AND(Rules!A{source}<>"",COUNTIF(RuleKey,Rules!H{source})>1),"Duplicate rule for this property and utility. ",""))'
        )
        _detail_row(
            ws,
            row,
            "Rule",
            f'=IF(Rules!A{source}="","",Rules!A{source}&"|"&Rules!B{source})',
            f'=IF(Rules!A{source}="","",Rules!A{source})',
            '=""',
            f'=IF(Rules!A{source}="","",Rules!B{source})',
            '=""',
            f"={message}",
        )
        row += 1
    return row


def _detail_row(ws, row: int, source: str, record: str, prop: str, unit: str, utility: str, bill: str, message: str) -> None:
    ws.cell(row, 1, source).font = FONT_SMALL
    for col, formula in enumerate([record, prop, unit, utility, bill, message], start=2):
        item = ws.cell(row, col, formula if formula.startswith("=") else formula)
        item.font = FONT_BODY
        item.alignment = Alignment(vertical="center", wrap_text=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the RUBS demo workbook.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    path = build(args.out)
    print(path)


if __name__ == "__main__":
    main()
