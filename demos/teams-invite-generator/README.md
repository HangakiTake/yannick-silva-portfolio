# Teams invite generator (dry-run demo)

This turns a course sheet (one row per course) into recurring Microsoft Teams meeting series in each teacher's calendar. Holidays are removed, attendees are invited, and every row is logged.

**This demo is offline.** It reads the sheet, works out every class date, and writes out:
- `dry_run.xlsx`, with Log, Series and Occurrences sheets
- `graph_payloads.json`, the exact Microsoft Graph requests a live run would send.

No invite is sent. A live run needs the client's Microsoft 365 tenant. See `docs/POWER_AUTOMATE_FLOW.md`.

```
pip install pandas openpyxl xlrd pytest
python src/make_sample.py samples/Cursos_demo.xlsx   # synthetic sheet in the client's column layout
python src/invites.py samples/Cursos_demo.xlsx out/  # dry run
python -m pytest -q tests                            # 55 tests
python tests/stress.py                               # messy-input stress run
```

## What it accepts
- **Weekdays:**
  - Spanish, with or without accents ("lunes y miércoles", "Martes y jueves")
  - lists ("lunes, miercoles y viernes", "L-X", "lun/jue") and ranges ("lunes a jueves")
  - English names.
- **Dates and times:**
  - dd-mm-yyyy (with `-`, `/` or `.`), real Excel dates, Excel serial numbers.
  - Times written as 9, 09:00, 18.30, 20h or 6.30 pm.
- **Holidays:** several dates per cell, plus ranges ("21-12-2026 a 06-01-2027").
- **Teacher mailboxes:** a `Profesores` sheet maps each teacher name to a mailbox. An unmapped teacher is an Error. The tool never guesses a mailbox.

Each bad row is logged as Error with a reason. The other rows still go through.

## Limits
- Dates are read day first, the Spanish order. A US-style date with a day above 12 is an Error. Text like 03/04/2027, which could mean either, is read as 3 April and flagged "check ... read as day/month" in the Log.
- A holiday outside the course dates is ignored, with a log note. One more than a year outside is an Error, because it is probably a mistyped year.
- Google Meet rows are marked "Phase 2" and nothing is built for them.
- The Power Automate flow is a design. It has not been run.

Synthetic data only. Teacher names and addresses are made up (example.com).
