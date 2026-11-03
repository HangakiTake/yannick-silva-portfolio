"""Build RUBS_Billing_Demo.xlsx. Usage: python src/build_workbook.py [out.xlsx] [--blank]"""
import sys
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.formatting.rule import FormulaRule
from openpyxl.utils import get_column_letter as L

sys.path.insert(0, __import__("os").path.dirname(__file__))
import sample_data as S

MAXP, MAXU, MAXO, MAXB, MAXR = 10, 40, 100, 30, 60
SERVICES = ["Water", "Sewer", "Trash", "Gas", "Other"]
METHODS = ["Occupants", "SqFt", "Equal"]
HDR = Font(bold=True, color="FFFFFF"); HFILL = PatternFill("solid", fgColor="305496")
INPUT = PatternFill("solid", fgColor="FFF2CC"); BAD = PatternFill("solid", fgColor="F8CBAD")


def header(ws, cols, widths=None):
    for i, c in enumerate(cols, 1):
        cell = ws.cell(1, i, c); cell.font = HDR; cell.fill = HFILL
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws.column_dimensions[L(i)].width = (widths or {}).get(i, 13)
    ws.freeze_panes = "A2"


def shade(ws, ncols, nrows):
    for r in range(2, nrows + 2):
        for c in range(1, ncols + 1):
            ws.cell(r, c).fill = INPUT


def dv_list(ws, items, rng):
    dv = DataValidation(type="list", formula1='"' + ",".join(items) + '"', allow_blank=True)
    ws.add_data_validation(dv); dv.add(rng)


def flag_issue(ws, col, nrows):
    ws.conditional_formatting.add(f"{col}2:{col}{nrows+1}", FormulaRule(formula=[f'LEN({col}2)>0'], fill=BAD))


def build(path, blank=False):
    wb = Workbook()
    rd = wb.active; rd.title = "README"
    lines = [
        "RUBS utility billing workbook (demo, fictional data)",
        "",
        "Monthly routine - you only type in the yellow cells, never in formulas:",
        "1. Bills: clear last month's rows and enter each utility bill (property, service, service period, amount).",
        "2. Occupancy: record move-ins/move-outs (dates) and occupant counts. Blank move-in = before the period, blank move-out = still living there.",
        "3. Settings_Units / Rules only when something changes (new unit, discount, owner-paid %, allocation method).",
        "4. Check Exceptions (must show 0 issues) and Reconciliation (every row OK).",
        "5. Send Unit_Statements; Property_Summary shows what the owner absorbs.",
        "",
        "How a bill is split:",
        "- Owner-paid % comes off the top (Rules).",
        "- The rest is shared over units of that property that use the service, by the Rule's method:",
        "  Occupants = occupant-days in the service period; SqFt = sq ft x occupied days; Equal = occupied days.",
        "- Vacant days carry 'Vacant weight' (0 = vacant share is spread over occupied units; 1 = a vacant unit counts like 1 occupant / its sq ft, and that share is charged to the owner).",
        "- A unit discount reduces the tenant charge; the discount is charged to the owner.",
        "- Charges are rounded to the cent with the largest-remainder method, so unit charges + owner line = bill, to the cent.",
        "",
        f"Capacity: {MAXP} properties, {MAXU} units, {MAXO} occupancy rows, {MAXB} bills, {MAXR} rules per run.",
        "Manual_Check recomputes any single unit's charge from the raw inputs with separate formulas.",
        "RUBS rules vary by US state and city (disclosure, admin fees, caps). This is a calculation tool, not legal advice.",
    ]
    for i, t in enumerate(lines, 1):
        rd.cell(i, 1, t)
    rd["A1"].font = Font(bold=True, size=14); rd.column_dimensions["A"].width = 130

    # ---- Settings_Properties
    sp = wb.create_sheet("Settings_Properties"); header(sp, ["PropID", "Name"], {2: 30}); shade(sp, 2, MAXP)
    if not blank:
        for r, p in enumerate(S.PROPERTIES, 2):
            sp.cell(r, 1, p[0]); sp.cell(r, 2, p[1])

    # ---- Settings_Units  (K = Issue)
    su = wb.create_sheet("Settings_Units")
    header(su, ["UnitID", "PropID", "SqFt", "Discount %", "Marked vacant (Y/N)"] + [f"No {s} (Y)" for s in SERVICES] + ["Issue"], {11: 40})
    shade(su, 10, MAXU)
    dv_list(su, ["Y", "N"], f"E2:J{MAXU+1}")
    dvd = DataValidation(type="decimal", operator="between", formula1="0", formula2="1", allow_blank=True)
    su.add_data_validation(dvd); dvd.add(f"D2:D{MAXU+1}")
    if not blank:
        for r, u in enumerate(S.UNITS, 2):
            su.cell(r, 1, u[0]); su.cell(r, 2, u[1]); su.cell(r, 3, u[2]); su.cell(r, 4, u[3]); su.cell(r, 5, u[4])
            for k, s in enumerate(SERVICES):
                su.cell(r, 6 + k, "Y" if s in u[5] else "N")
    for r in range(2, MAXU + 2):
        su.cell(r, 4).number_format = "0%"
        su.cell(r, 11, (f'=IF(A{r}="","",TRIM('
                        f'IF(COUNTIF(Settings_Properties!$A$2:$A${MAXP+1},B{r})=0,"unknown property; ","")'
                        f'&IF(COUNTIF($A$2:$A${MAXU+1},A{r})>1,"duplicate unit; ","")'
                        f'&IF(OR(N(D{r})<0,N(D{r})>1),"discount outside 0-100%; ","")'
                        f'&IF(AND(E{r}="Y",COUNTIF(Occupancy!$A$2:$A${MAXO+1},A{r})>0),"occupancy on unit marked vacant; ","")))'))
    flag_issue(su, "K", MAXU)

    # ---- Occupancy  E EffIn F EffOut G Issue H Occ#
    oc = wb.create_sheet("Occupancy")
    header(oc, ["UnitID", "Occupants", "Move-in (blank = before period)", "Move-out (blank = still there)", "Eff. in", "Eff. out", "Issue", "Occ #"], {3: 16, 4: 16, 7: 40})
    shade(oc, 4, MAXO)
    if not blank:
        for r, o in enumerate(S.OCCUPANCY, 2):
            for c, v in enumerate(o, 1):
                if v is not None:
                    oc.cell(r, c, v)
    for r in range(2, MAXO + 2):
        oc.cell(r, 3).number_format = oc.cell(r, 4).number_format = "yyyy-mm-dd"
        oc.cell(r, 5, f'=IF(C{r}="",1,C{r})'); oc.cell(r, 6, f'=IF(D{r}="",2958465,D{r})')
        oc.cell(r, 8, f"=N(B{r})")
        oc.cell(r, 7, (f'=IF(A{r}="","",TRIM('
                       f'IF(COUNTIF(Settings_Units!$A$2:$A${MAXU+1},A{r})=0,"unknown unit; ","")'
                       f'&IF(N(B{r})<=0,"occupants missing or not positive; ","")'
                       f'&IF(OR(AND(C{r}<>"",NOT(ISNUMBER(C{r}))),AND(D{r}<>"",NOT(ISNUMBER(D{r})))),"text instead of a date; ","")'
                       f'&IF(F{r}<E{r},"move-out before move-in; ","")'
                       f'&IF(COUNTIFS($A$2:$A${MAXO+1},A{r},$E$2:$E${MAXO+1},"<="&F{r},$F$2:$F${MAXO+1},">="&E{r})>1,"overlapping occupancy rows; ","")))'))
    for c in "EFH":
        oc.column_dimensions[c].hidden = True
    flag_issue(oc, "G", MAXO)

    # ---- Bills  G Issue
    bl = wb.create_sheet("Bills")
    header(bl, ["BillID", "PropID", "Service", "Period start", "Period end", "Amount ($)", "Issue"], {7: 45})
    shade(bl, 6, MAXB)
    dv_list(bl, SERVICES, f"C2:C{MAXB+1}")
    if not blank:
        for r, b in enumerate(S.BILLS, 2):
            for c, v in enumerate(b, 1):
                bl.cell(r, c, v)
    for r in range(2, MAXB + 2):
        bl.cell(r, 4).number_format = bl.cell(r, 5).number_format = "yyyy-mm-dd"
        bl.cell(r, 6).number_format = "#,##0.00"
        prev = f'_xlfn.MAXIFS($E$2:$E${MAXB+1},$B$2:$B${MAXB+1},B{r},$C$2:$C${MAXB+1},C{r},$D$2:$D${MAXB+1},"<"&D{r})'
        bl.cell(r, 7, (f'=IF(A{r}="","",TRIM('
                       f'IF(OR(B{r}="",C{r}="",D{r}="",E{r}="",F{r}=""),"missing field; ","")'
                       f'&IF(OR(AND(D{r}<>"",NOT(ISNUMBER(D{r}))),AND(E{r}<>"",NOT(ISNUMBER(E{r}))),AND(F{r}<>"",NOT(ISNUMBER(F{r})))),"text instead of a number or date; ","")'
                       f'&IF(N(F{r})<0,"negative amount; ","")'
                       f'&IF(N(E{r})<N(D{r}),"period end before start; ","")'
                       f'&IF(COUNTIF(Settings_Properties!$A$2:$A${MAXP+1},B{r})=0,"unknown property; ","")'
                       f'&IF(COUNTIF($A$2:$A${MAXB+1},A{r})>1,"duplicate bill ID; ","")'
                       f'&IF(ISNA(MATCH(C{r},{{"Water","Sewer","Trash","Gas","Other"}},0)),"invalid service; ","")'
                       f'&IF(COUNTIFS(Rules!$A$2:$A${MAXR+1},B{r},Rules!$B$2:$B${MAXR+1},C{r})=0,"no rule (default Occupants, 0% owner); ","")'
                       f'&IF(AND({prev}>0,N(D{r})<>{prev}+1),"gap or overlap with previous period; ","")'
                       f'&IF(AND(N(F{r})<>0,SUMIFS(Allocation!$X:$X,Allocation!$A:$A,ROW()-1,Allocation!$B:$B,1)=0),"no billable units, all to owner; ","")))'))
    flag_issue(bl, "G", MAXB)

    # ---- Rules
    ru = wb.create_sheet("Rules")
    header(ru, ["PropID", "Service", "Method", "Vacant weight (0 or 1)", "Owner-paid %", "Key", "Issue"], {7: 40})
    shade(ru, 5, MAXR)
    dv_list(ru, SERVICES, f"B2:B{MAXR+1}"); dv_list(ru, METHODS, f"C2:C{MAXR+1}")
    if not blank:
        for r, x in enumerate(S.RULES, 2):
            for c, v in enumerate(x, 1):
                ru.cell(r, c, v)
    for r in range(2, MAXR + 2):
        ru.cell(r, 5).number_format = "0%"
        ru.cell(r, 6, f'=A{r}&"|"&B{r}')
        ru.cell(r, 7, (f'=IF(A{r}="","",TRIM('
                       f'IF(ISNA(MATCH(C{r},{{"Occupants","SqFt","Equal"}},0)),"invalid method; ","")'
                       f'&IF(OR(N(E{r})<0,N(E{r})>1),"owner % outside 0-100%; ","")'
                       f'&IF(OR(N(D{r})<0,N(D{r})>1),"vacant weight outside 0-1; ","")'
                       f'&IF(COUNTIF($F$2:$F${MAXR+1},F{r})>1,"duplicate rule; ","")))'))
    ru.column_dimensions["F"].hidden = True
    flag_issue(ru, "G", MAXR)

    # ---- Allocation (one row per bill slot x unit slot)
    al = wb.create_sheet("Allocation")
    cols = ["Bill #", "Unit #", "BillID", "PropID", "Service", "Start", "End", "Amount", "UnitID", "Unit prop",
            "Applies", "Key", "Method", "Vacant wt", "Owner %", "Base", "Occupant-days", "Occupied days", "Period days",
            "Vacant days", "Tenant weight", "Vacant weight", "Discount", "Total weight", "Pool", "Raw cents",
            "Floor", "Remainder", "Target cents", "Short", "Rank", "Cents", "Charge $"]
    header(al, cols)
    OA, OE, OF, OH = (f"Occupancy!${c}$2:${c}${MAXO+1}" for c in "AEFH")
    for i in range(1, MAXB + 1):
        b = i + 1
        top = 2 + (i - 1) * MAXU; bot = top + MAXU - 1
        blk = lambda c: f"${c}${top}:${c}${bot}"
        for j in range(1, MAXU + 1):
            r = top + j - 1; u = j + 1
            mn = f"({OF}-({OF}>G{r})*({OF}-G{r}))"
            mx = f"({OE}+(F{r}>{OE})*(F{r}-{OE}))"
            ov = f"(({mn}-{mx}+1)*(({mn}-{mx}+1)>0))"
            f = {
                "A": i, "B": j,
                "C": f'=IF(Bills!$A${b}="","",Bills!$A${b})', "D": f'=Bills!$B${b}&""', "E": f'=Bills!$C${b}&""',
                "F": f"=N(Bills!$D${b})", "G": f"=N(Bills!$E${b})", "H": f"=N(Bills!$F${b})",
                "I": f'=Settings_Units!$A${u}&""', "J": f'=Settings_Units!$B${u}&""',
                "K": (f'=IF(AND(C{r}<>"",I{r}<>"",J{r}=D{r},G{r}>=F{r},'
                      f'IFERROR(INDEX(Settings_Units!$F${u}:$J${u},MATCH(E{r},{{"Water","Sewer","Trash","Gas","Other"}},0)),"Y")<>"Y"),1,0)'),
                "L": f'=D{r}&"|"&E{r}',
                "M": f'=IFERROR(INDEX(Rules!$C$2:$C${MAXR+1},MATCH(L{r},Rules!$F$2:$F${MAXR+1},0))&"","Occupants")',
                "N": f'=IFERROR(N(INDEX(Rules!$D$2:$D${MAXR+1},MATCH(L{r},Rules!$F$2:$F${MAXR+1},0))),0)',
                "O": f'=IFERROR(N(INDEX(Rules!$E$2:$E${MAXR+1},MATCH(L{r},Rules!$F$2:$F${MAXR+1},0))),0)',
                "P": f'=IF(M{r}="SqFt",N(Settings_Units!$C${u}),1)',
                "Q": f"=IF(K{r}=1,SUMPRODUCT(({OA}=I{r})*{OH}*{ov}),0)",
                "R": f"=IF(K{r}=1,MIN(S{r},SUMPRODUCT(({OA}=I{r})*({OH}>0)*{ov})),0)",
                "S": f"=IF(K{r}=1,G{r}-F{r}+1,0)",
                "T": f"=MAX(0,S{r}-R{r})",
                "U": f'=IF(K{r}=1,IF(M{r}="Occupants",Q{r},P{r}*R{r}),0)',
                "V": f"=IF(K{r}=1,N{r}*P{r}*T{r},0)",
                "W": f"=N(Settings_Units!$D${u})",
                "X": f"=SUM({blk('U')})+SUM({blk('V')})",
                "Y": f"=H{r}-ROUND(H{r}*O{r},2)",
                "Z": f"=IF(AND(K{r}=1,X{r}>0),Y{r}*100*U{r}/X{r}*(1-W{r}),0)",
                "AA": f"=INT(Z{r})",
                "AB": f"=IF(K{r}=1,ROUND(Z{r}-AA{r},6),-1)",
                "AC": f"=ROUND(SUM({blk('Z')}),0)",
                "AD": f"=AC{r}-SUM({blk('AA')})",
                "AE": f"=IF(K{r}=1,SUMPRODUCT(({blk('AB')}>AB{r})+({blk('AB')}=AB{r})*({blk('B')}<B{r}))+1,999)",
                "AF": f"=AA{r}+IF(AE{r}<=AD{r},1,0)",
                "AG": f"=AF{r}/100",
            }
            for c, v in f.items():
                al[f"{c}{r}"] = v
    al.sheet_state = "visible"

    # ---- Unit_Statements
    us = wb.create_sheet("Unit_Statements")
    header(us, ["UnitID", "PropID"] + SERVICES + ["Total $"])
    AG, AI, AE_ = "Allocation!$AG:$AG", "Allocation!$I:$I", "Allocation!$E:$E"
    for j in range(1, MAXU + 1):
        r = j + 1
        us.cell(r, 1, f'=IF(Settings_Units!A{r}="","",Settings_Units!A{r})')
        us.cell(r, 2, f'=IF(Settings_Units!B{r}="","",Settings_Units!B{r})')
        for k, s in enumerate(SERVICES):
            c = us.cell(r, 3 + k, f'=IF($A{r}="","",SUMIFS({AG},{AI},$A{r},{AE_},"{s}"))'); c.number_format = "#,##0.00"
        us.cell(r, 8, f'=IF(A{r}="","",SUM(C{r}:G{r}))').number_format = "#,##0.00"

    # ---- Property_Summary (property x service)
    ps = wb.create_sheet("Property_Summary")
    header(ps, ["PropID", "Service", "Billed $", "Charged to tenants $", "Owner pays $", "Owner %"])
    r = 2
    for p in range(1, MAXP + 1):
        for s in SERVICES:
            ps.cell(r, 1, f'=IF(Settings_Properties!$A${p+1}="","",Settings_Properties!$A${p+1})'); ps.cell(r, 2, s)
            ps.cell(r, 3, f'=IF(A{r}="","",SUMIFS(Bills!$F:$F,Bills!$B:$B,A{r},Bills!$C:$C,B{r}))')
            ps.cell(r, 4, f'=IF(A{r}="","",SUMIFS(Allocation!$AG:$AG,Allocation!$D:$D,A{r},Allocation!$E:$E,B{r}))')
            ps.cell(r, 5, f'=IF(A{r}="","",C{r}-D{r})')
            ps.cell(r, 6, f'=IF(OR(A{r}="",N(C{r})=0),"",E{r}/C{r})').number_format = "0.0%"
            for c in (3, 4, 5):
                ps.cell(r, c).number_format = "#,##0.00"
            r += 1
    ps.cell(r + 1, 2, "TOTAL").font = Font(bold=True)
    for c in (3, 4, 5):
        ps.cell(r + 1, c, f"=SUM({L(c)}2:{L(c)}{r-1})").number_format = "#,##0.00"

    # ---- Reconciliation (per bill)
    rc = wb.create_sheet("Reconciliation")
    header(rc, ["BillID", "PropID", "Service", "Billed $", "Owner-paid % share", "Vacancy share", "Discounts",
                "Rounding", "Owner total", "Tenant total", "Tenants+owner", "Difference", "Status"])
    for i in range(1, MAXB + 1):
        r = i + 1; top = 2 + (i - 1) * MAXU; bot = top + MAXU - 1
        A = lambda c: f"Allocation!${c}${top}:${c}${bot}"
        rc.cell(r, 1, f'=IF(Bills!A{r}="","",Bills!A{r})'); rc.cell(r, 2, f'=IF(A{r}="","",Bills!B{r})'); rc.cell(r, 3, f'=IF(A{r}="","",Bills!C{r})')
        rc.cell(r, 4, f'=IF(A{r}="","",N(Bills!F{r}))')
        rc.cell(r, 5, f'=IF(A{r}="","",ROUND(D{r}*Allocation!O{top},2))')
        rc.cell(r, 6, f'=IF(A{r}="","",IF(Allocation!X{top}>0,Allocation!Y{top}*SUM({A("V")})/Allocation!X{top},Allocation!Y{top}))')
        rc.cell(r, 7, f'=IF(A{r}="","",IF(Allocation!X{top}>0,Allocation!Y{top}*SUMPRODUCT({A("U")},{A("W")})/Allocation!X{top},0))')
        rc.cell(r, 10, f'=IF(A{r}="","",SUM({A("AF")})/100)')
        rc.cell(r, 8, f'=IF(A{r}="","",D{r}-E{r}-F{r}-G{r}-J{r})')
        rc.cell(r, 9, f'=IF(A{r}="","",E{r}+F{r}+G{r}+H{r})')
        rc.cell(r, 11, f'=IF(A{r}="","",I{r}+J{r})')
        rc.cell(r, 12, f'=IF(A{r}="","",ROUND(D{r}-K{r},2))')
        rc.cell(r, 13, (f'=IF(A{r}="","",IF(AND(L{r}=0,ABS(H{r})<0.005,SUM({A("AF")})=Allocation!AC{top},'
                        f'J{r}>=0,I{r}>=-0.005,Bills!G{r}=""),"OK","CHECK"))'))
        for c in range(4, 13):
            rc.cell(r, c).number_format = "#,##0.00"
    t = MAXB + 3
    rc.cell(t, 1, "All bills"); rc.cell(t, 4, f"=SUM(D2:D{MAXB+1})"); rc.cell(t, 10, f"=SUM(J2:J{MAXB+1})")
    rc.cell(t, 9, f"=SUM(I2:I{MAXB+1})")
    rc.cell(t + 1, 1, "Unit statements total"); rc.cell(t + 1, 10, f"=SUM(Unit_Statements!H2:H{MAXU+1})")
    rc.cell(t + 2, 1, "Statements tie to allocation")
    rc.cell(t + 2, 13, f'=IF(ROUND(J{t}-J{t+1},2)=0,"OK","CHECK")')
    rc.cell(t + 3, 1, "Bills not OK"); rc.cell(t + 3, 13, f'=COUNTIF(M2:M{MAXB+1},"CHECK")')
    for c in range(1, 14):
        rc.cell(t, c).font = Font(bold=True)

    # ---- Manual_Check (independent recomputation from raw inputs)
    mc = wb.create_sheet("Manual_Check")
    mc.column_dimensions["A"].width = 34; mc.column_dimensions["B"].width = 16
    mc["A1"] = "Manual check calculator - pick a bill and a unit (yellow). Uses its own formulas on the raw inputs."; mc["A1"].font = Font(bold=True)
    labels = ["Bill ID", "Unit ID", "Property", "Service", "Period start", "Period end", "Period days", "Amount",
              "Method", "Vacant weight", "Owner-paid %", "Pool after owner %", "Unit applies (1/0)", "Unit weight",
              "Total weight (all units, incl. vacant)", "Unit discount", "Exact share (unrounded)",
              "Rounded to cent", "Allocation sheet charge", "Difference", "Result"]
    for k, t_ in enumerate(labels, 3):
        mc.cell(k, 1, t_)
    mc["B3"].fill = mc["B4"].fill = INPUT
    if not blank:
        mc["B3"] = "B-201"; mc["B4"] = "P2-05"
    BR = lambda c: f"Bills!${c}$2:${c}${MAXB+1}"
    mc["B5"] = f'=IFERROR(INDEX({BR("B")},MATCH(B3,{BR("A")},0)),"")'
    mc["B6"] = f'=IFERROR(INDEX({BR("C")},MATCH(B3,{BR("A")},0)),"")'
    mc["B7"] = f'=IFERROR(INDEX({BR("D")},MATCH(B3,{BR("A")},0)),0)'
    mc["B8"] = f'=IFERROR(INDEX({BR("E")},MATCH(B3,{BR("A")},0)),0)'
    mc["B7"].number_format = mc["B8"].number_format = "yyyy-mm-dd"
    mc["B9"] = "=B8-B7+1"
    mc["B10"] = f'=IFERROR(INDEX({BR("F")},MATCH(B3,{BR("A")},0)),0)'
    RR = lambda c: f"Rules!${c}$2:${c}${MAXR+1}"
    rule = f'MATCH(1,INDEX(({RR("A")}=B5)*({RR("B")}=B6),0),0)'
    mc["B11"] = f'=IFERROR(INDEX({RR("C")},{rule}),"Occupants")'
    mc["B12"] = f'=IFERROR(N(INDEX({RR("D")},{rule})),0)'
    mc["B13"] = f'=IFERROR(N(INDEX({RR("E")},{rule})),0)'
    mc["B14"] = "=B10-ROUND(B10*B13,2)"
    # per-unit working table starting row 30
    mc["A28"] = "Working: every unit slot for this bill"; mc["A28"].font = Font(bold=True)
    wh = ["UnitID", "In property", "Excluded", "Applies", "Base", "Occupant-days", "Occupied days", "Vacant days", "Tenant wt", "Vacant wt", "Discount"]
    for k, h in enumerate(wh, 1):
        mc.cell(29, k, h).font = Font(bold=True)
    svc_col = '{"Water","Sewer","Trash","Gas","Other"}'
    for j in range(1, MAXU + 1):
        r = 29 + j; u = j + 1
        days = (f"SUMPRODUCT(({OA}=A{r})*({{w}})*((MIN_END-MAX_START+1)>0)*(MIN_END-MAX_START+1))")
        me = f"IF({OF}<$B$8,{OF},$B$8)"; ms = f"IF({OE}>$B$7,{OE},$B$7)"
        mc.cell(r, 1, f"=Settings_Units!A{u}&\"\"")
        mc.cell(r, 2, f'=IF(AND(A{r}<>"",Settings_Units!B{u}=$B$5),1,0)')
        mc.cell(r, 3, f'=IFERROR(INDEX(Settings_Units!F{u}:J{u},MATCH($B$6,{svc_col},0)),"Y")')
        mc.cell(r, 4, f'=IF(AND(B{r}=1,C{r}<>"Y",$B$9>0),1,0)')
        mc.cell(r, 5, f'=IF($B$11="SqFt",N(Settings_Units!C{u}),1)')
        mc.cell(r, 6, "=IF(D%d=1,SUMPRODUCT((%s=A%d)*%s*((%s-%s+1)>0)*(%s-%s+1)),0)" % (r, OA, r, OH, me, ms, me, ms))
        mc.cell(r, 7, "=IF(D%d=1,MIN($B$9,SUMPRODUCT((%s=A%d)*(%s>0)*((%s-%s+1)>0)*(%s-%s+1))),0)" % (r, OA, r, OH, me, ms, me, ms))
        mc.cell(r, 8, f"=IF(D{r}=1,$B$9-G{r},0)")
        mc.cell(r, 9, f'=IF(D{r}=1,IF($B$11="Occupants",F{r},E{r}*G{r}),0)')
        mc.cell(r, 10, f"=IF(D{r}=1,$B$12*E{r}*H{r},0)")
        mc.cell(r, 11, f"=N(Settings_Units!D{u})")
    W1, WL = 30, 29 + MAXU
    mc["B15"] = f'=IFERROR(INDEX(D{W1}:D{WL},MATCH(B4,A{W1}:A{WL},0)),0)'
    mc["B16"] = f'=IFERROR(INDEX(I{W1}:I{WL},MATCH(B4,A{W1}:A{WL},0)),0)'
    mc["B17"] = f"=SUM(I{W1}:J{WL})"
    mc["B18"] = f'=IFERROR(INDEX(K{W1}:K{WL},MATCH(B4,A{W1}:A{WL},0)),0)'
    mc["B19"] = "=IF(B17>0,B14*B16/B17*(1-B18),0)"
    mc["B20"] = "=ROUND(B19,2)"
    mc["B21"] = (f'=SUMIFS(Allocation!$AG:$AG,Allocation!$C:$C,B3,Allocation!$I:$I,B4)')
    mc["B22"] = "=ROUND(B21-B19,4)"
    mc["B23"] = '=IF(ABS(B22)<0.01,"MATCH (within 1 cent rounding)","DIFFERENT - investigate")'
    for c in ("B10", "B14", "B19", "B20", "B21"):
        mc[c].number_format = "#,##0.0000" if c == "B19" else "#,##0.00"
    mc["B13"].number_format = mc["B18"].number_format = "0%"

    # ---- Exceptions
    ex = wb.create_sheet("Exceptions")
    header(ex, ["Sheet", "Check", "Rows flagged"], {2: 45})
    checks = [("Bills", "G", MAXB, x) for x in ["missing field", "negative amount", "period end before start", "unknown property",
                                                 "duplicate bill ID", "invalid service", "text instead of a number or date", "no rule", "gap or overlap", "no billable units"]]
    checks += [("Occupancy", "G", MAXO, x) for x in ["unknown unit", "occupants missing", "move-out before move-in", "overlapping occupancy", "text instead of a date"]]
    checks += [("Settings_Units", "K", MAXU, x) for x in ["unknown property", "duplicate unit", "discount outside", "occupancy on unit marked vacant"]]
    checks += [("Rules", "G", MAXR, x) for x in ["invalid method", "owner % outside", "vacant weight outside", "duplicate rule"]]
    for k, (sh, col, n, txt) in enumerate(checks, 2):
        ex.cell(k, 1, sh); ex.cell(k, 2, txt)
        ex.cell(k, 3, f'=SUMPRODUCT(--ISNUMBER(SEARCH("{txt}",{sh}!${col}$2:${col}${n+1})))')
    k = len(checks) + 2
    ex.cell(k, 1, "All"); ex.cell(k, 2, "formula error in an Issue column")
    ex.cell(k, 3, "=" + "+".join(f"SUMPRODUCT(--ISERROR({sh}!${c}$2:${c}${n+1}))" for sh, c, n in
                                 [("Bills", "G", MAXB), ("Occupancy", "G", MAXO), ("Settings_Units", "K", MAXU), ("Rules", "G", MAXR)]))
    k += 1
    ex.cell(k, 1, "All"); ex.cell(k, 2, "rows below capacity (ignored)")
    ex.cell(k, 3, "=" + "+".join(f"COUNTA({sh}!A{n+2}:A5000)" for sh, n in
                                 [("Bills", MAXB), ("Occupancy", MAXO), ("Settings_Units", MAXU), ("Rules", MAXR), ("Settings_Properties", MAXP)]))
    tot = len(checks) + 5
    ex.cell(tot, 2, "TOTAL issues").font = Font(bold=True); ex.cell(tot, 3, f"=SUM(C2:C{tot-2})")
    ex.cell(tot + 1, 2, "Reconciliation rows not OK"); ex.cell(tot + 1, 3, f"=Reconciliation!M{MAXB+6}")
    wb.move_sheet("Exceptions", offset=-(len(wb.sheetnames) - 2))
    wb.save(path)


if __name__ == "__main__":
    out = next((a for a in sys.argv[1:] if not a.startswith("--")), "RUBS_Billing_Demo.xlsx")
    build(out, blank="--blank" in sys.argv)
    print("wrote", out)
