"""Independent Python reference for the RUBS allocation (exact fractions, no workbook formulas).

allocate(units, occupancy, bills, rules) -> {(bill_id, unit_id): cents}, {bill_id: owner_cents}
"""
from datetime import date, datetime
from fractions import Fraction as F
import math


def _round(x):
    """Round half away from zero, like Excel ROUND."""
    return int(math.copysign(math.floor(abs(x) + F(1, 2)), x))

SERVICES = ["Water", "Sewer", "Trash", "Gas", "Other"]
FAR_PAST, FAR_FUTURE = date(1900, 1, 1), date(9999, 12, 31)


def _d(x):
    return x.date() if isinstance(x, datetime) else x


def _overlap(a1, a2, b1, b2):
    return max(0, (min(a2, b2) - max(a1, b1)).days + 1)


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _isdate(x):
    return isinstance(x, (date, datetime))


def _spread(b, rule, props):
    """props: Settings_Properties IDs, or None to skip that check. A bill is spread only if its inputs and its rule are usable (same test as Bills!H in the workbook)."""
    method, vw, pct = rule
    return ((props is None or b["prop"] in props) and b["service"] in SERVICES and _isdate(b["start"]) and _isdate(b["end"])
            and _d(b["end"]) >= _d(b["start"]) and _num(b["amount"]) and b["amount"] >= 0
            and method in ("Occupants", "SqFt", "Equal") and _num(vw) and 0 <= vw <= 1 and _num(pct) and 0 <= pct <= 1)


def allocate(units, occupancy, bills, rules, known_props=None):
    """units: list of dicts id, prop, sqft, discount, excluded(set)
    occupancy: list of dicts unit, occupants, move_in, move_out (None allowed)
    bills: list of dicts id, prop, service, start, end, amount
    rules: dict (prop, service) -> (method, vacant_weight, owner_pct)"""
    charges, owner = {}, {}
    for b in bills:
        method, vw, pct = rules.get((b["prop"], b["service"]), ("Occupants", 0, 0))
        if not _spread(b, (method, vw, pct), known_props):
            continue  # not allocated: no unit charges, no owner line
        start, end = _d(b["start"]), _d(b["end"])
        amt_c = _round(F(str(b["amount"])) * 100)
        owner_paid_c = _round(F(str(b["amount"])) * F(str(pct)) * 100)
        pool = F(amt_c - owner_paid_c, 100)
        pdays = (end - start).days + 1
        ws = []  # (unit, tenant_w, vacant_w)
        for u in units:
            if u["prop"] != b["prop"] or b["service"] in u["excluded"] or pdays <= 0 or b["service"] not in SERVICES:
                continue
            # a text move date is flagged in the workbook and the row counts no days
            rows = [o for o in occupancy if o["unit"] == u["id"]
                    and all(v is None or _isdate(v) for v in (o["move_in"], o["move_out"]))]
            ov = lambda o: _overlap(_d(o["move_in"]) or FAR_PAST, _d(o["move_out"]) or FAR_FUTURE, start, end)
            people_days = sum(o["occupants"] * ov(o) for o in rows)
            occ_days = min(pdays, sum(ov(o) for o in rows if o["occupants"] > 0))
            base = F(str(u["sqft"])) if method == "SqFt" else 1
            tw = people_days if method == "Occupants" else base * occ_days
            vwt = F(str(vw)) * base * (pdays - occ_days)
            ws.append((u, F(tw), F(vwt)))
        total = sum(t + v for _, t, v in ws)
        raw = [(u, pool * 100 * t / total * (1 - F(str(u["discount"]))) if total else F(0)) for u, t, _ in ws]
        target = _round(sum(r for _, r in raw))
        floors = [(u, r, r.numerator // r.denominator) for u, r in raw]
        short = target - sum(f for *_, f in floors)
        # ties: remainder rounded to 6 decimals (same as the workbook's column AB), then unit order
        order = sorted(range(len(floors)), key=lambda k: (-round(floors[k][1] - floors[k][2], 6), k))
        bump = set(order[:short])
        tenant = 0
        for k, (u, r, f) in enumerate(floors):
            c = f + (1 if k in bump else 0)
            charges[(b["id"], u["id"])] = c
            tenant += c
        owner[b["id"]] = amt_c - tenant
    return charges, owner


def read_inputs(wb):
    """Read the typed input cells of a workbook (openpyxl, data_only).

    Text keys are matched case-insensitively, like Excel's COUNTIF/SUMIFS, by mapping them to the Settings spelling."""
    fold = lambda v: v.upper() if isinstance(v, str) else v
    units = []
    for r in wb["Settings_Units"].iter_rows(min_row=2, max_col=10, values_only=True):
        if r[0]:
            units.append(dict(id=r[0], prop=r[1], sqft=r[2] or 0, discount=r[3] or 0,
                              excluded={s for s, f in zip(SERVICES, r[5:10]) if fold(f) == "Y"}))
    uid = {fold(u["id"]): u["id"] for u in units}
    pid = {fold(u["prop"]): u["prop"] for u in units}
    sid = {s.upper(): s for s in SERVICES}
    occ = [dict(unit=uid.get(fold(r[0]), r[0]), occupants=r[1] or 0, move_in=r[2], move_out=r[3])
           for r in wb["Occupancy"].iter_rows(min_row=2, max_col=4, values_only=True) if r[0]]
    bills = [dict(id=r[0], prop=pid.get(fold(r[1]), r[1]), service=sid.get(fold(r[2]), r[2]), start=r[3], end=r[4], amount=r[5])
             for r in wb["Bills"].iter_rows(min_row=2, max_col=6, values_only=True) if r[0]]
    rules = {(pid.get(fold(r[0]), r[0]), sid.get(fold(r[1]), r[1])): (r[2], r[3] or 0, r[4] or 0)
             for r in wb["Rules"].iter_rows(min_row=2, max_col=5, values_only=True) if r[0]}
    return units, occ, bills, rules
