import json, os, sys
from datetime import date, time
import pandas as pd, pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
import invites as I, make_sample  # noqa: E402

D = lambda s: date.fromisoformat(s)


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    d = tmp_path_factory.mktemp("inv"); p = d / "Cursos_demo.xlsx"; make_sample.make(p)
    course, mapping = I.read_sheet(p)
    series, log = I.build(course, mapping)
    lg = I.write_outputs(series, log, d / "out")
    return {s.row: s for s in series}, {l["row"]: l for l in log}, d / "out", lg


# T1 parsing ---------------------------------------------------------------
@pytest.mark.parametrize("txt,exp", [
    ("lunes y miércoles", [0, 2]), ("Martes y jueves", [1, 3]), ("Viernes", [4]), ("MIERCOLES", [2]),
    ("lunes, miercoles y viernes", [0, 2, 4]), ("L-X", [0, 2]), ("lunes a viernes", [0, 1, 2, 3, 4]),
    ("lun/jue", [0, 3]), ("Monday and Wednesday".replace(" and ", ", "), [0, 2]), ("sábado", [5]), ("martes e jueves", [1, 3]), ("los lunes", [0])])
def test_T1_weekdays(txt, exp):
    assert I.parse_days(txt) == exp


@pytest.mark.parametrize("bad", ["Lunez y martes", "", "viernes a lunes", "every week"])
def test_T1_weekdays_bad(bad):
    with pytest.raises(I.RowError):
        I.parse_days(bad)


@pytest.mark.parametrize("v,exp", [("14-09-2026", D("2026-09-14")), ("14/09/2026", D("2026-09-14")), ("2026-09-14", D("2026-09-14")),
                                   (pd.Timestamp("2026-09-14"), D("2026-09-14")), (46279, D("2026-09-14")), ("14.09.26", D("2026-09-14"))])
def test_T1_dates(v, exp):
    assert I.parse_date(v, "x") == exp


@pytest.mark.parametrize("v,exp", [(time(9), time(9)), ("09:00", time(9)), ("18.30", time(18, 30)), ("20h", time(20)),
                                   ("9", time(9)), ("9:00 am", time(9)), ("6.30 pm", time(18, 30)), ("12pm", time(12)), (0.375, time(9)), ("09:00:00", time(9))])
def test_T1_times(v, exp):
    assert I.parse_time(v, "x") == exp


def test_T1_holidays_and_attendees():
    h = I.parse_holidays("12-10-2026; 08-12-2026\n21-12-2026 a 23-12-2026")
    assert h == {D("2026-10-12"), D("2026-12-08"), D("2026-12-21"), D("2026-12-22"), D("2026-12-23")}
    assert I.parse_attendees("A@example.com, b@example.com; a@example.com") == ["a@example.com", "b@example.com"]
    with pytest.raises(I.RowError):
        I.parse_attendees("ana@@example")


# T2 occurrences vs hand-written calendars ---------------------------------
EXPECTED = {
    2: "2026-09-14 16 21 23 28 30|10-05 07 14 19 21 26 28|11-02 04 09 11 16 18 23 25 30|12-02 07 09 14",
    3: "2026-09-15 17 22 24 29|10-01 06 08 13 15 20 22 27 29|11-03 05 10 12 17 19 24 26|12-01 03 10 15",
    4: "2026-09-18 25|10-02 09 16 23 30|11-06 13 20 27|12-04 11",
    5: "2026-11-30|12-02 04 07 09 11 14 16 18|2027-01-08 11 13 15 18 20 22 25 27 29",
    6: "2026-11-02 03 04 05 09 10 11 12",
}


def expand(spec):
    out, year = [], None
    for part in spec.split("|"):
        toks = part.split()
        head = toks[0].split("-")
        if len(head) == 3:
            year = head[0]; month, first = head[1], head[2]
        else:
            month, first = head
        for dd in [first] + toks[1:]:
            out.append(D(f"{year}-{month}-{dd}"))
    return out


@pytest.mark.parametrize("row", list(EXPECTED))
def test_T2_occurrences_match_hand_calendar(run, row):
    s = run[0][row]
    assert s.occurrences == expand(EXPECTED[row])
    assert all(s.start_date <= d <= s.end_date for d in s.occurrences)


def test_T2_festivos_removed(run):
    s = run[0]
    assert s[2].removed == [D("2026-10-12")]
    assert s[3].removed == [D("2026-12-08")] and s[3].holidays_not_on_class_day == [D("2026-10-12")]
    assert len(s[5].removed) == 8 and D("2026-12-25") in s[5].removed and D("2027-01-06") in s[5].removed
    for x in s.values():
        assert not set(x.removed) & set(x.occurrences)


# T3 errors isolated --------------------------------------------------------
@pytest.mark.parametrize("row,reason", [(7, "unknown weekday"), (8, "Fecha fin before"), (9, "Hora de fin not after"),
                                        (10, "bad attendee email"), (11, "unknown platform"), (12, "no mailbox mapped"), (13, "Titulo missing")])
def test_T3_bad_rows_logged(run, row, reason):
    l = run[1][row]
    assert l["status"] == "Error" and reason in l["reason"]
    assert row not in run[0]


def test_T3_missing_column_fails_loudly():
    with pytest.raises(ValueError, match="festivos"):
        I.find_columns(pd.DataFrame(columns=[c for c in make_sample.HDR if c != "Festivos"]))


def test_T3_duplicate_row_is_error():
    df = pd.DataFrame([M_ROW, M_ROW], columns=make_sample.HDR)
    s, log = I.build(df, {I.norm(t): m for t, m in make_sample.TEACHERS})
    assert len(s) == 1 and log[1]["status"] == "Error" and "duplicate of row 2" in log[1]["reason"]


M_ROW = make_sample.ROWS[0]


def _one(row):
    s, log = I.build(pd.DataFrame([row], columns=make_sample.HDR), {I.norm(t): m for t, m in make_sample.TEACHERS})
    return log[0]


def test_T3_ambiguous_date_warned():
    l = _one(M_ROW[:2] + ["03/04/2027", "30-06-2027"] + M_ROW[4:])
    assert l["status"] == "Ready" and "check Fecha inicio: read as day/month" in l["reason"] and l["first"] == "2027-04-05"
    assert "check" not in (_one(M_ROW)["reason"] or "")


def test_T3_festivo_year_typo_is_error():
    l = _one(M_ROW[:7] + ["12-10-2062"] + M_ROW[8:])
    assert l["status"] == "Error" and "year typo" in l["reason"]


# T4 Graph payload ----------------------------------------------------------
def test_T4_graph_payload(run):
    p = json.load(open(run[2] / "graph_payloads.json"))
    assert len(p) == 4  # Teams rows only; Meet row is phase 2
    e = next(x for x in p if x["create_event"]["subject"] == "English A2+ Grupo 3")
    ev = e["create_event"]
    assert e["mailbox"] == "profe1@example.com"
    assert ev["recurrence"]["pattern"] == {"type": "weekly", "interval": 1, "daysOfWeek": ["monday", "wednesday"], "firstDayOfWeek": "monday"}
    assert ev["recurrence"]["range"]["startDate"] == "2026-09-14" and ev["recurrence"]["range"]["endDate"] == "2026-12-14"
    assert ev["start"] == {"dateTime": "2026-09-14T09:00:00", "timeZone": "Europe/Madrid"}
    assert ev["isOnlineMeeting"] is True and ev["onlineMeetingProvider"] == "teamsForBusiness"
    assert e["cancel_occurrences"] == ["2026-10-12"]
    assert "  " not in ev["body"]["content"]


def test_T4_first_occurrence_is_first_class_day(run):
    # course starts on a Wednesday but classes are on Fridays -> series must start on the Friday
    assert run[0][4].graph_payload()["create_event"]["start"]["dateTime"].startswith("2026-09-18")


def test_T4_festivo_on_first_class_day_not_cancelled():
    s, _ = I.build(pd.DataFrame([M_ROW[:7] + ["14-09-2026; 12-10-2026"] + M_ROW[8:]], columns=make_sample.HDR),
                   {I.norm(t): m for t, m in make_sample.TEACHERS})
    p = s[0].graph_payload()
    assert p["create_event"]["start"]["dateTime"].startswith("2026-09-16") and p["cancel_occurrences"] == ["2026-10-12"]


# T5 idempotency ------------------------------------------------------------
def test_T5_keys_stable_and_time_change_keeps_key(run):
    s = run[0][2]
    import dataclasses
    t = dataclasses.replace(s, start_time=time(9, 30))
    assert s.key == t.key and s.graph_payload() != t.graph_payload()
    assert len({x.key for x in run[0].values()}) == len(run[0])


# T6 log --------------------------------------------------------------------
def test_T6_log_one_row_per_input_row(run):
    lg = run[3]
    assert len(lg) == len(make_sample.ROWS)  # blank rows skipped, every real row logged
    assert (lg["status"] == "Ready").sum() == 4 and (lg["status"] == "Error").sum() == 7
    assert int(lg["classes"].sum()) == sum(len(s.occurrences) for s in run[0].values())
    xl = pd.ExcelFile(run[2] / "dry_run.xlsx")
    assert xl.sheet_names == ["Log", "Series", "Occurrences"]
    assert len(pd.read_excel(xl, "Occurrences")) == int(lg["classes"].sum())
