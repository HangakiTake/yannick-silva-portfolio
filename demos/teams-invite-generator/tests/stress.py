"""Messy-input stress run (not part of the sample generator). Prints one line per variant."""
import os, sys, copy
from datetime import time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, os.path.join(ROOT, "src"))
import pandas as pd, invites as I, make_sample as M

base = M.ROWS[0]
V = {
 "duplicate row": [base, base],
 "US date 09/14/2026": [base[:2] + ["09/14/2026"] + base[3:]],
 "ambiguous 03/04/2027 (d/m assumed)": [base[:2] + ["03/04/2027", "30-06-2027"] + base[4:]],
 "festivo year typo 12-10-2062": [base[:7] + ["12-10-2062"] + base[8:]],
 "DST change inside series (25 Oct)": [base],
 "headers with spaces/case": None,
 "attendees on new lines": [base[:8] + ["a@example.com\nb@example.com"] + base[9:]],
 "time as text 9:00 am": [base[:4] + ["9:00 am"] + base[5:]],
 "weekday in English 'Monday'": [base[:6] + ["Monday"] + base[7:]],
 "end date = start date, not a class day": [base[:2] + ["15-09-2026", "15-09-2026"] + base[4:]],
 "teacher name trailing space": [[base[0] + " "] + base[1:]],
}
for name, rows in V.items():
    hdr = M.HDR
    if rows is None:
        rows, hdr = [base], ["  " + h.upper() + " " for h in M.HDR]
    df = pd.DataFrame(rows, columns=hdr)
    mp = {I.norm(t): m for t, m in M.TEACHERS}
    try:
        course = df.rename(columns=I.find_columns(df))
        s, log = I.build(course, mp)
        keys = [x.key for x in s]
        out = "; ".join(f'{l["status"]}: {l.get("reason") or ""} ({l.get("classes",0)} classes)' for l in log)
        if len(keys) != len(set(keys)): out += " | DUPLICATE KEYS"
    except Exception as e:
        out = f"CRASH {type(e).__name__}: {e}"
    print(f"{name:40s} -> {out}")
