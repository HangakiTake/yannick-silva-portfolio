"""Run: pytest -q tests  (needs LibreOffice 'soffice' on PATH)."""
import os, random, subprocess, sys, tempfile, time, shutil
from datetime import date, timedelta
import openpyxl, pytest

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
import build_workbook as B, rubs, sample_data as S  # noqa: E402

TMP = tempfile.mkdtemp(prefix="rubs_")
VARIANTS = {}  # name -> path of the edited (unrecalculated) workbook
TIMES = {}


def variant(name, edit=None, blank=False):
    path = os.path.join(TMP, name + ".xlsx")
    B.build(path, blank=blank)
    if edit:
        wb = openpyxl.load_workbook(path); edit(wb); wb.save(path)
    VARIANTS[name] = path


def set_(sheet, cell, val):
    return lambda wb: wb[sheet].__setitem__(cell, val)


def row_of(wb, sheet, key):
    for r in range(2, wb[sheet].max_row + 1):
        if wb[sheet].cell(r, 1).value == key:
            return r


def occ_set(unit, col, val):
    def e(wb):
        wb["Occupancy"].cell(row_of(wb, "Occupancy", unit), col, val)
    return e


# ---------- variants
variant("base")
variant("blank", blank=True)
variant("more_people", occ_set("P1-01", 2, 5))
variant("lower_case_keys", lambda wb: [wb["Bills"].__setitem__("C2", "water"), wb["Occupancy"].__setitem__("A2", wb["Occupancy"]["A2"].value.lower()),
                                       wb["Settings_Units"].__setitem__("F5", "y")])
variant("owner_pct", lambda wb: wb["Rules"].__setitem__("E4", 0.30))  # P1 Trash 15% -> 30%


def november(wb):
    ws = wb["Bills"]
    amounts = [398.10, 301.22, 145.00, 260.48, 802.17, 640.00, 260.00, 611.93, 1222.40, 990.03, 390.00, 1010.55, 120.00]
    for r in range(2, 15):
        ws.cell(r, 1, ws.cell(r, 1).value.replace("B-", "N-"))
        s = date(2026, 10, 18) if r == 2 else date(2026, 11, 1)
        e = date(2026, 11, 17) if r == 2 else date(2026, 11, 30)
        ws.cell(r, 4, s); ws.cell(r, 5, e); ws.cell(r, 6, amounts[r - 2])
    o = wb["Occupancy"]; n = len(S.OCCUPANCY) + 2
    o.cell(row_of(wb, "Occupancy", "P1-04"), 4, date(2026, 11, 14))   # P1-04 moves out 14 Nov...
    o.cell(n, 1, "P1-04"); o.cell(n, 2, 1); o.cell(n, 3, date(2026, 11, 20))  # ...one new tenant from 20 Nov
variant("november", november)

PAIRS = [("B-101", "P1-02"), ("B-103", "P1-03"), ("B-204", "P2-08"), ("B-304", "P3-07"), ("B-305", "P3-10"), ("B-201", "P2-05")]
for k, (b, u) in enumerate(PAIRS):
    variant(f"manual_{k}", lambda wb, b=b, u=u: (wb["Manual_Check"].__setitem__("B3", b), wb["Manual_Check"].__setitem__("B4", u)))

SEEDED = {  # name: (edit, sheet, expected issue text)
    "neg_amount": (set_("Bills", "F3", -10), "negative amount"),
    "missing_amount": (set_("Bills", "F3", None), "missing field"),
    "end_before_start": (set_("Bills", "E3", date(2026, 9, 1)), "period end before start"),
    "unknown_prop_bill": (set_("Bills", "B3", "P9"), "unknown property"),
    "text_amount": (set_("Bills", "F3", "1,234.50"), "text instead of a number or date"),
    "text_bill_date": (set_("Bills", "D2", "18/09/2026"), "text instead of a number or date"),
    "text_move_date": (occ_set("P3-10", 3, "16/10/2026"), "text instead of a date"),
    "dup_bill": (set_("Bills", "A3", "B-101"), "duplicate bill ID"),
    "bad_service": (set_("Bills", "C3", "Electric"), "invalid service"),
    "period_gap": (lambda wb: [wb["Bills"].__setitem__(c, v) for c, v in
                               [("A15", "B-102b"), ("B15", "P1"), ("C15", "Sewer"), ("D15", date(2026, 11, 5)), ("E15", date(2026, 11, 30)), ("F15", 10)]], "gap or overlap"),
    "no_billable": (lambda wb: [wb["Settings_Units"].__setitem__(f"J{r}", "Y") for r in range(14, 26)], "no billable units"),
    "unknown_unit": (occ_set("P1-01", 1, "P1-99"), "unknown unit"),
    "zero_occupants": (occ_set("P1-01", 2, 0), "occupants missing"),
    "moveout_before_in": (lambda wb: [occ_set("P3-10", 4, date(2026, 10, 1))(wb)], "move-out before move-in"),
    "overlap_occ": (lambda wb: [wb["Occupancy"].__setitem__(c, v) for c, v in [("A30", "P1-01"), ("B30", 1), ("C30", date(2026, 10, 5))]], "overlapping occupancy"),
    "vacant_with_occ": (lambda wb: [wb["Occupancy"].__setitem__(c, v) for c, v in [("A30", "P2-08"), ("B30", 2)]], "occupancy on unit marked vacant"),
    "bad_discount": (set_("Settings_Units", "D2", 1.5), "discount outside"),
    "bad_method": (set_("Rules", "C2", "Meters"), "invalid method"),
    "bad_owner_pct": (set_("Rules", "E2", 1.2), "owner % outside"),
    "over_capacity": (set_("Bills", f"A{B.MAXB + 2}", "B-999"), "rows below capacity"),
    "dup_rule": (lambda wb: [wb["Rules"].__setitem__(c, v) for c, v in [("A20", "P1"), ("B20", "Water"), ("C20", "Equal")]], "duplicate rule"),
}
for n, (e, _) in SEEDED.items():
    variant("seed_" + n, e)


def capacity(wb):
    rnd = random.Random(7)
    su, oc, bl, ru = wb["Settings_Units"], wb["Occupancy"], wb["Bills"], wb["Rules"]
    for r in range(2, 42):
        p = ["P1", "P2", "P3"][(r - 2) % 3]; su.cell(r, 1, f"X-{r:02d}"); su.cell(r, 2, p); su.cell(r, 3, rnd.randint(400, 1400))
        su.cell(r, 4, rnd.choice([0, 0, 0, 0.05, 0.1])); su.cell(r, 5, "N")
        for c in range(6, 11):
            su.cell(r, c, "Y" if rnd.random() < 0.1 else "N")
    for row in range(2, 102):  # clear the sample occupancy first (inputs only, A-D)
        for c in range(1, 5):
            oc.cell(row, c).value = None  # cell(r, c, None) does not clear
    r = 2
    for u in range(2, 42):
        cut = date(2026, 10, rnd.randint(2, 28))
        if rnd.random() < 0.1:
            continue  # vacant
        if rnd.random() < 0.5 and r < 100:
            oc.cell(r, 1, f"X-{u:02d}"); oc.cell(r, 2, rnd.randint(1, 5)); oc.cell(r, 3).value = None; oc.cell(r, 4, cut - timedelta(days=1)); r += 1
            oc.cell(r, 1, f"X-{u:02d}"); oc.cell(r, 2, rnd.randint(1, 5)); oc.cell(r, 3, cut); oc.cell(r, 4).value = None; r += 1
        else:
            oc.cell(r, 1, f"X-{u:02d}"); oc.cell(r, 2, rnd.randint(1, 5)); oc.cell(r, 3).value = None; oc.cell(r, 4).value = None; r += 1
    for k in range(30):
        b = k + 2; p = ["P1", "P2", "P3"][k % 3]; s = B.SERVICES[(k // 3) % 5]; m = (k // 15)
        bl.cell(b, 1, f"C-{k:02d}"); bl.cell(b, 2, p); bl.cell(b, 3, s)
        bl.cell(b, 4, date(2026, 9 + m, 1)); bl.cell(b, 5, date(2026, 9 + m, 30) if m == 0 else date(2026, 10, 31))
        bl.cell(b, 6, round(rnd.uniform(50, 3000), 2))
    for k, (p, s) in enumerate([(p, s) for p in ["P1", "P2", "P3"] for s in B.SERVICES]):
        q = k + 2
        ru.cell(q, 1, p); ru.cell(q, 2, s); ru.cell(q, 3, rnd.choice(B.METHODS)); ru.cell(q, 4, rnd.choice([0, 1])); ru.cell(q, 5, rnd.choice([0, 0, 0.1, 0.15]))
variant("capacity", capacity)


@pytest.fixture(scope="session")
def calc():
    out = os.path.join(TMP, "out")
    t = time.time()
    subprocess.run(["soffice", "--headless", "--calc", "--convert-to", "xlsx:Calc MS Excel 2007 XML", "--outdir", out,
                    *VARIANTS.values()], check=True, capture_output=True, timeout=1200)
    TIMES["all"] = time.time() - t
    cache = {}

    def get(name):
        if name not in cache:
            cache[name] = openpyxl.load_workbook(os.path.join(out, name + ".xlsx"), data_only=True)
        return cache[name]
    yield get
    shutil.rmtree(TMP, True)


def excel_cents(wb):
    return {(r[2], r[8]): round(r[31]) for r in wb["Allocation"].iter_rows(min_row=2, values_only=True) if r[2] and r[10] == 1}


def recon_rows(wb):
    return [r for r in wb["Reconciliation"].iter_rows(min_row=2, max_row=B.MAXB + 1, values_only=True) if r[0]]


def errors(wb):
    return [(ws.title, c.coordinate) for ws in wb for row in ws.iter_rows() for c in row
            if isinstance(c.value, str) and c.value.startswith("#")]


def exc_total(wb):
    ws = wb["Exceptions"]
    out = {}
    for r in ws.iter_rows(min_row=2, values_only=True):
        if r[1]:
            out[r[1]] = out.get(r[1], 0) + (r[2] or 0)  # same check text on two sheets is summed
    return out


CLEAN = ["base", "more_people", "owner_pct", "november", "capacity", "lower_case_keys"]


# T1 reconciliation ------------------------------------------------------
@pytest.mark.parametrize("name", CLEAN)
def test_T1_every_bill_reconciles_to_the_cent(calc, name):
    wb = calc(name); rows = recon_rows(wb)
    assert rows
    for r in rows:
        assert r[12] == "OK", r
        assert round(r[9] + r[8] - r[3], 2) == 0
    assert wb["Reconciliation"].cell(B.MAXB + 5, 13).value == "OK"


# T2 workbook == independent Python ---------------------------------------
@pytest.mark.parametrize("name", CLEAN)
def test_T2_excel_matches_python_reference(calc, name):
    wb = calc(name)
    ref, owner = rubs.allocate(*rubs.read_inputs(wb))
    xl = excel_cents(wb)
    assert set(ref) == set(xl)
    assert [k for k in ref if ref[k] != xl[k]] == []
    for r in recon_rows(wb):
        assert round(r[8] * 100) == owner[r[0]]


def test_T2_unit_statements_and_property_summary(calc):
    wb = calc("base"); ref, owner = rubs.allocate(*rubs.read_inputs(wb))
    for r in wb["Unit_Statements"].iter_rows(min_row=2, values_only=True):
        if r[0]:
            assert round(r[7] * 100) == sum(c for (b, u), c in ref.items() if u == r[0])
    bills = {b["id"]: b for b in rubs.read_inputs(wb)[2]}
    for r in wb["Property_Summary"].iter_rows(min_row=2, max_row=1 + B.MAXP * 5, values_only=True):
        if r[0]:
            ids = [i for i, b in bills.items() if b["prop"] == r[0] and b["service"] == r[1]]
            assert round(r[4] * 100) == sum(owner[i] for i in ids)


# T3 manual check ---------------------------------------------------------
@pytest.mark.parametrize("k", range(len(PAIRS)))
def test_T3_manual_check_reproduces_unit(calc, k):
    ws = calc(f"manual_{k}")["Manual_Check"]
    assert ws["B23"].value.startswith("MATCH"), (PAIRS[k], ws["B19"].value, ws["B21"].value)
    assert abs(ws["B20"].value - ws["B21"].value) <= 0.01


# T4 change inputs, no formula edits --------------------------------------
def test_T4_more_occupants_shifts_charges(calc):
    a, b = excel_cents(calc("base")), excel_cents(calc("more_people"))
    assert b[("B-101", "P1-01")] > a[("B-101", "P1-01")]
    assert b[("B-101", "P1-04")] < a[("B-101", "P1-04")]
    assert b[("B-103", "P1-01")] == a[("B-103", "P1-01")]  # trash is Equal split, not by occupants


def test_T4_owner_pct_moves_cost_to_owner(calc):
    a = {r[0]: r for r in recon_rows(calc("base"))}; b = {r[0]: r for r in recon_rows(calc("owner_pct"))}
    assert a["B-103"][4] == 21.75 and b["B-103"][4] == 43.50
    assert b["B-103"][9] < a["B-103"][9]


def test_T4_new_month_without_formula_edits(calc):
    wb = calc("november")
    assert {r[0][:2] for r in recon_rows(wb)} == {"N-"}
    assert exc_total(wb)["TOTAL issues"] == 0


# T5 exceptions -----------------------------------------------------------
def test_T5_clean_data_has_no_exceptions(calc):
    for n in CLEAN + ["blank"]:
        t = exc_total(calc(n))
        assert t["TOTAL issues"] == 0, (n, {k: v for k, v in t.items() if v})


@pytest.mark.parametrize("name", list(SEEDED))
def test_T5_seeded_error_is_flagged(calc, name):
    t = exc_total(calc("seed_" + name))
    hit = [k for k, v in t.items() if k not in ("TOTAL issues", "Reconciliation rows not OK") and v]
    assert any(SEEDED[name][1] in k for k in hit), t
    assert t["TOTAL issues"] >= 1


# Hygiene -----------------------------------------------------------------
@pytest.mark.parametrize("name", CLEAN + ["blank"])
def test_no_formula_errors(calc, name):
    assert errors(calc(name)) == []


def test_blank_copy_is_empty(calc):
    wb = calc("blank")
    assert recon_rows(wb) == [] and wb["Reconciliation"].cell(B.MAXB + 3, 4).value == 0


# Python reference, hand-worked (no workbook) ------------------------------
def test_reference_hand_example():
    # $100 water, 2 units: A 3 people all month, B 1 person all month, 30-day period -> 75 / 25
    u = [dict(id="A", prop="P", sqft=0, discount=0, excluded=set()), dict(id="B", prop="P", sqft=0, discount=0, excluded=set())]
    o = [dict(unit="A", occupants=3, move_in=None, move_out=None), dict(unit="B", occupants=1, move_in=None, move_out=None)]
    b = [dict(id="X", prop="P", service="Water", start=date(2026, 11, 1), end=date(2026, 11, 30), amount=100)]
    ch, ow = rubs.allocate(u, o, b, {})
    assert ch == {("X", "A"): 7500, ("X", "B"): 2500} and ow == {"X": 0}


def test_reference_vacancy_discount_and_rounding():
    # $100, 3 units equal split; C vacant with vacant weight 1 (owner pays), A has 10% discount.
    u = [dict(id=i, prop="P", sqft=0, discount=d, excluded=set()) for i, d in [("A", 0.1), ("B", 0), ("C", 0)]]
    o = [dict(unit="A", occupants=1, move_in=None, move_out=None), dict(unit="B", occupants=1, move_in=None, move_out=None)]
    b = [dict(id="X", prop="P", service="Trash", start=date(2026, 11, 1), end=date(2026, 11, 30), amount=100)]
    ch, ow = rubs.allocate(u, o, b, {("P", "Trash"): ("Equal", 1, 0)})
    # each third = 33.333..; A pays 90% = 30.00, B 33.33; owner = vacancy 33.33 + discount 3.33 + rounding
    assert ch[("X", "A")] == 3000 and ch[("X", "B")] == 3333 and ch[("X", "C")] == 0 and ow["X"] == 3667


def test_reference_excluded_service_and_largest_remainder():
    u = [dict(id=i, prop="P", sqft=0, discount=0, excluded={"Gas"} if i == "C" else set()) for i in "ABCD"]
    o = [dict(unit=i, occupants=1, move_in=None, move_out=None) for i in "ABCD"]
    b = [dict(id="G", prop="P", service="Gas", start=date(2026, 11, 1), end=date(2026, 11, 30), amount=100)]
    ch, ow = rubs.allocate(u, o, b, {})
    assert ch[("G", "A")] + ch[("G", "B")] + ch[("G", "D")] == 10000 and ("G", "C") not in ch
    assert sorted(ch.values()) == [3333, 3333, 3334] and ow["G"] == 0


def test_capacity_recalc_time(calc):
    calc("capacity")
    assert TIMES["all"] < 600  # all variants together; per-file time reported in TEST_REPORT
