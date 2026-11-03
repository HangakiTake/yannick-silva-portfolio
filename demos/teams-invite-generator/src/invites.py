"""Offline dry run: course sheet -> recurring Teams/Meet series, holidays removed, log.

python src/invites.py samples/Cursos_demo.xlsx out/  -> out/dry_run.xlsx + out/graph_payloads.json
Nothing is sent anywhere.
"""
import hashlib, json, re, sys, unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
import pandas as pd

TZ = "Europe/Madrid"
WEEKDAYS = {  # Spanish (and English) name -> python weekday
    "lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "domingo": 6,
    "lun": 0, "mar": 1, "mie": 2, "jue": 3, "vie": 4, "sab": 5, "dom": 6,
    "l": 0, "m": 1, "x": 2, "j": 3, "v": 4, "s": 5, "d": 6,
}
GRAPH_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
WEEKDAYS.update({d: i for i, d in enumerate(GRAPH_DAYS)})
WEEKDAYS.update({d[:3]: i for i, d in enumerate(GRAPH_DAYS)})
COLS = {  # canonical -> accepted header spellings (normalised)
    "teacher": ["profesor/a", "profesor", "profesora", "teacher"],
    "title": ["titulo", "title", "curso"],
    "start_date": ["fecha inicio curso", "fecha inicio", "start date"],
    "end_date": ["fecha fin curso", "fecha fin", "end date"],
    "start_time": ["hora inicio", "hora de inicio", "start time"],
    "end_time": ["hora de fin", "hora fin", "end time"],
    "days": ["periodico", "periodicidad", "dias", "days"],
    "holidays": ["festivos", "holidays"],
    "attendees": ["asistentes", "attendees"],
    "platform": ["plataforma", "platform"],
    "text": ["texto", "text", "body"],
}
EMAIL = re.compile(r"^[A-Za-z0-9._%+'-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
DEFAULT_TEXT = "Link for your class. Questions? Reply to this invite."


def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", s).strip()


class RowError(ValueError):
    pass


def blank(v):
    return v is None or (isinstance(v, float) and pd.isna(v)) or (isinstance(v, str) and not v.strip()) or v is pd.NaT


def parse_date(v, what):
    if blank(v):
        raise RowError(f"{what} missing")
    if isinstance(v, pd.Timestamp):
        return v.date()
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, (int, float)):  # Excel serial
        if 20000 < v < 80000:
            return date(1899, 12, 30) + timedelta(days=int(v))
        raise RowError(f"{what} not a date: {v}")
    s = str(v).strip()
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%Y-%m-%d", "%d-%m-%y", "%d/%m/%y", "%d.%m.%y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    raise RowError(f"{what} not a date: {s!r}")


def ambiguous_date(v):
    """True for text like 03/04/2027 where day and month could be swapped."""
    m = re.fullmatch(r"\s*(\d{1,2})[-/.](\d{1,2})[-/.]\d{2,4}\s*", str(v)) if isinstance(v, str) else None
    return bool(m) and int(m.group(1)) <= 12 and int(m.group(2)) <= 12 and m.group(1) != m.group(2)


def parse_time(v, what):
    if blank(v):
        raise RowError(f"{what} missing")
    if isinstance(v, datetime):
        return v.time().replace(second=0, microsecond=0)
    if isinstance(v, time):
        return v.replace(second=0, microsecond=0)
    if isinstance(v, float) and 0 <= v < 1:  # Excel fraction of a day
        m = round(v * 1440)
        return time(m // 60, m % 60)
    s = norm(v).replace(" ", "")
    ampm = re.search(r"(am|pm)$", s)
    s = re.sub(r"(am|pm)$", "", s).replace("h", ":").replace(".", ":")
    m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?(?::\d{2})?:?", s)
    hh = int(m.group(1)) if m else 99
    if ampm:
        hh = hh % 12 + (12 if ampm.group(1) == "pm" else 0) if 1 <= hh <= 12 else 99
    if not m or hh > 23 or int(m.group(2) or 0) > 59:
        raise RowError(f"{what} not a time: {v!r}")
    return time(hh, int(m.group(2) or 0))


def parse_days(v):
    if blank(v):
        raise RowError("Periodico (weekdays) missing")
    s = norm(v)
    s = re.sub(r"\b(de|los|todos)\b", " ", s)
    out = set()
    rng = re.fullmatch(r"(\w+)\s+(?:a|al|hasta)\s+(\w+)", s.strip())  # "lunes a viernes"; "L-X" is a list, not a range
    if rng and rng.group(1) in WEEKDAYS and rng.group(2) in WEEKDAYS:
        a, b = WEEKDAYS[rng.group(1)], WEEKDAYS[rng.group(2)]
        if a > b:
            raise RowError(f"weekday range backwards: {v!r}")
        return list(range(a, b + 1))
    for tok in re.split(r"[\s,;/+&-]+|\by\b|\be\b", s):
        tok = tok.strip(". ")
        if not tok:
            continue
        if tok not in WEEKDAYS:
            raise RowError(f"unknown weekday {tok!r} in {v!r}")
        out.add(WEEKDAYS[tok])
    if not out:
        raise RowError(f"no weekdays in {v!r}")
    return sorted(out)


def parse_holidays(v):
    if blank(v):
        return set()
    if isinstance(v, (datetime, date, pd.Timestamp, int, float)):
        return {parse_date(v, "Festivo")}
    days = set()
    for part in re.split(r"[;\n,]+", str(v)):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r"(.+?)\s+(?:a|al|-|hasta)\s+(.+)", part)
        if m:
            a, b = parse_date(m.group(1), "Festivo"), parse_date(m.group(2), "Festivo")
            if b < a:
                raise RowError(f"festivo range backwards: {part!r}")
            days |= {a + timedelta(d) for d in range((b - a).days + 1)}
        else:
            days.add(parse_date(part, "Festivo"))
    return days


def parse_attendees(v):
    if blank(v):
        return []
    emails = [e.strip().strip("<>").lower() for e in re.split(r"[;,\s]+", str(v)) if e.strip()]
    bad = [e for e in emails if not EMAIL.match(e)]
    if bad:
        raise RowError(f"bad attendee email: {', '.join(bad)}")
    return list(dict.fromkeys(emails))


def parse_platform(v):
    s = norm(v) if not blank(v) else ""
    if s in ("teams", "microsoft teams", "ms teams"):
        return "Teams"
    if s in ("meet", "google meet", "gmeet", "google"):
        return "Google Meet"
    raise RowError(f"unknown platform {v!r} (expected Teams or Google Meet)")


@dataclass
class Series:
    row: int
    teacher: str
    mailbox: str
    title: str
    platform: str
    start_date: date
    end_date: date
    start_time: time
    end_time: time
    weekdays: list
    attendees: list
    body: str
    occurrences: list = field(default_factory=list)
    removed: list = field(default_factory=list)
    holidays_not_on_class_day: list = field(default_factory=list)

    @property
    def key(self):
        raw = f"{norm(self.teacher)}|{norm(self.title)}|{self.start_date.isoformat()}"
        return hashlib.sha1(raw.encode()).hexdigest()[:12]

    def graph_payload(self):
        """Body for POST /users/{mailbox}/events (Microsoft Graph v1.0)."""
        first = self.occurrences[0] if self.occurrences else self.start_date
        p = {
            "subject": self.title,
            "body": {"contentType": "text", "content": self.body},
            "start": {"dateTime": f"{first.isoformat()}T{self.start_time:%H:%M}:00", "timeZone": TZ},
            "end": {"dateTime": f"{first.isoformat()}T{self.end_time:%H:%M}:00", "timeZone": TZ},
            "recurrence": {
                "pattern": {"type": "weekly", "interval": 1, "daysOfWeek": [GRAPH_DAYS[d] for d in self.weekdays],
                            "firstDayOfWeek": "monday"},
                "range": {"type": "endDate", "startDate": first.isoformat(), "endDate": self.end_date.isoformat(),
                          "recurrenceTimeZone": TZ},
            },
            "attendees": [{"emailAddress": {"address": a}, "type": "required"} for a in self.attendees],
            "transactionId": self.key,
        }
        if self.platform == "Teams":
            p["isOnlineMeeting"] = True
            p["onlineMeetingProvider"] = "teamsForBusiness"
        return {"key": self.key, "mailbox": self.mailbox, "create_event": p,
                # a festivo before the first class is never part of the series, so there is nothing to cancel
                "cancel_occurrences": [d.isoformat() for d in self.removed if d > first]}


def find_columns(df):
    hdr = {norm(c): c for c in df.columns}
    out, missing = {}, []
    for k, names in COLS.items():
        hit = next((hdr[n] for n in names if n in hdr), None)
        if hit is None and k != "text":
            missing.append(names[0])
        out[k] = hit
    if missing:
        raise ValueError(f"sheet is missing columns: {', '.join(missing)}")
    return out


def read_sheet(path):
    xl = pd.read_excel(path, sheet_name=None, dtype=object)
    names = list(xl)
    course = xl[names[0]]
    mapping = {}
    for n in names[1:]:
        if norm(n) in ("profesores", "teachers", "buzones", "mailboxes"):
            m = xl[n]
            for _, r in m.iterrows():
                if not blank(r.iloc[0]) and not blank(r.iloc[1]):
                    mapping[norm(r.iloc[0])] = str(r.iloc[1]).strip().lower()
    return course, mapping


def build(course, mapping, require_mailbox=True):
    cols = find_columns(course)
    series, log, seen = [], [], {}
    for i, r in course.iterrows():
        rownum = i + 2
        g = lambda k: r[cols[k]] if cols[k] is not None else None
        if all(blank(g(k)) for k in COLS if cols[k] is not None):
            continue  # empty row
        teacher, title = g("teacher"), g("title")
        entry = {"row": rownum, "teacher": "" if blank(teacher) else str(teacher).strip(),
                 "title": "" if blank(title) else str(title).strip()}
        try:
            if blank(teacher):
                raise RowError("Profesor/a missing")
            if blank(title):
                raise RowError("Titulo missing")
            mailbox = mapping.get(norm(teacher))
            if not mailbox:
                if require_mailbox:
                    raise RowError(f"no mailbox mapped for teacher {str(teacher).strip()!r} (Profesores sheet)")
                mailbox = ""
            elif not EMAIL.match(mailbox):
                raise RowError(f"bad teacher mailbox {mailbox!r}")
            sd, ed = parse_date(g("start_date"), "Fecha inicio"), parse_date(g("end_date"), "Fecha fin")
            if ed < sd:
                raise RowError("Fecha fin before Fecha inicio")
            if (ed - sd).days > 400:
                raise RowError("course longer than 400 days, check the dates")
            st, et = parse_time(g("start_time"), "Hora inicio"), parse_time(g("end_time"), "Hora de fin")
            if et <= st:
                raise RowError("Hora de fin not after Hora inicio")
            days = parse_days(g("days"))
            hols = parse_holidays(g("holidays"))
            att = parse_attendees(g("attendees"))
            plat = parse_platform(g("platform"))
            body = DEFAULT_TEXT if blank(g("text")) else re.sub(r"[ \t]+", " ", str(g("text"))).strip()
            s = Series(rownum, entry["teacher"], mailbox, entry["title"], plat, sd, ed, st, et, days, att, body)
            d = sd
            while d <= ed:
                if d.weekday() in days:
                    (s.removed if d in hols else s.occurrences).append(d)
                d += timedelta(1)
            s.holidays_not_on_class_day = sorted(h for h in hols if sd <= h <= ed and h.weekday() not in days)
            if not s.occurrences:
                raise RowError("no class dates between Fecha inicio and Fecha fin (after festivos)")
            status = "Ready" if plat == "Teams" else "Phase 2 (Google Meet, not created)"
            notes = []
            if not att:
                notes.append("no attendees")
            if s.holidays_not_on_class_day:
                h = s.holidays_not_on_class_day
                notes.append("festivos not on a class day: " + (", ".join(x.isoformat() for x in h) if len(h) <= 3 else f"{len(h)} days"))
            far = [h for h in hols if (sd - h).days > 365 or (h - ed).days > 365]
            if far:
                raise RowError("festivo more than a year outside the course (year typo?): " + ", ".join(h.isoformat() for h in far))
            amb = [n for n, k in (("Fecha inicio", "start_date"), ("Fecha fin", "end_date")) if ambiguous_date(g(k))]
            if amb:
                notes.append(f"check {' and '.join(amb)}: read as day/month")
            out_of_range = sorted(h for h in hols if not sd <= h <= ed)
            if out_of_range:
                notes.append("festivos outside course dates ignored: " + ", ".join(h.isoformat() for h in out_of_range))
            if s.key in seen:
                raise RowError(f"duplicate of row {seen[s.key]} (same teacher, title and start date)")
            seen[s.key] = rownum
            series.append(s)
            log.append({**entry, "status": status, "reason": "; ".join(notes), "key": s.key, "mailbox": mailbox,
                        "platform": plat, "classes": len(s.occurrences), "removed": len(s.removed),
                        "first": s.occurrences[0].isoformat(), "last": s.occurrences[-1].isoformat(), "attendees": len(att)})
        except RowError as e:
            log.append({**entry, "status": "Error", "reason": str(e), "key": "", "mailbox": "", "platform": "",
                        "classes": 0, "removed": 0, "first": "", "last": "", "attendees": 0})
    return series, log


def write_outputs(series, log, outdir):
    import os
    os.makedirs(outdir, exist_ok=True)
    ser = pd.DataFrame([{"key": s.key, "row": s.row, "teacher": s.teacher, "mailbox": s.mailbox, "title": s.title,
                         "platform": s.platform, "weekdays": ", ".join(GRAPH_DAYS[d] for d in s.weekdays),
                         "start": f"{s.start_time:%H:%M}", "end": f"{s.end_time:%H:%M}", "time_zone": TZ,
                         "first_class": s.occurrences[0], "last_class": s.occurrences[-1],
                         "classes": len(s.occurrences), "festivos_removed": ", ".join(d.isoformat() for d in s.removed),
                         "attendees": "; ".join(s.attendees)} for s in series])
    occ = pd.DataFrame([{"key": s.key, "teacher": s.teacher, "title": s.title, "date": d,
                         "weekday": GRAPH_DAYS[d.weekday()], "start": f"{s.start_time:%H:%M}", "end": f"{s.end_time:%H:%M}"}
                        for s in series for d in s.occurrences])
    lg = pd.DataFrame(log, columns=["row", "teacher", "title", "status", "reason", "key", "mailbox", "platform",
                                    "classes", "removed", "first", "last", "attendees"])
    with pd.ExcelWriter(os.path.join(outdir, "dry_run.xlsx")) as w:
        lg.to_excel(w, sheet_name="Log", index=False); ser.to_excel(w, sheet_name="Series", index=False)
        occ.to_excel(w, sheet_name="Occurrences", index=False)
    with open(os.path.join(outdir, "graph_payloads.json"), "w") as f:
        json.dump([s.graph_payload() for s in series if s.platform == "Teams"], f, indent=2, ensure_ascii=False)
    return lg


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit("usage: python src/invites.py COURSES.xls[x] [OUTDIR] [--no-mailbox-check]")
    path, outdir = args[0], args[1] if len(args) > 1 else "out"
    course, mapping = read_sheet(path)
    series, log = build(course, mapping, require_mailbox="--no-mailbox-check" not in argv)
    lg = write_outputs(series, log, outdir)
    print(lg["status"].value_counts().to_string())
    print("classes:", int(lg["classes"].sum()), "festivos removed:", int(lg["removed"].sum()))


if __name__ == "__main__":
    main(sys.argv)
