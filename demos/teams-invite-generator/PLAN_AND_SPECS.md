# Teams / Google Meet invite generator — plan and specs

Job: Upwork 2117204485080851480 "Teams and Google meet Invitation generator Agent" (applied 2026-11-02).

## Requirements (from the post and the client's sample file)
R1. Read the course sheet: Profesor/a, Titulo, Fecha inicio curso, Fecha fin curso, Hora inicio, Hora de fin, Periodico (Spanish weekdays, e.g. "lunes y miércoles"), Festivos, Asistentes, Plataforma, Texto.
R2. One recurring meeting series per row in the teacher's calendar, on the listed weekdays, between the start and end dates, at the listed times.
R3. Festivos (holidays) removed from each series.
R4. Attendees invited; Texto used as the invite body.
R5. Plataforma decides Teams or Google Meet (Meet = phase 2).
R6. A log of everything created or skipped.

## Professional standards added
S1. Messy input tolerated: dd-mm-yyyy text dates and real Excel dates, accents/capitals in weekdays ("Miercoles", "Martes y jueves", "lunes, miércoles y viernes", "L-X", "lunes a viernes"), several festivos per cell and date ranges ("21-12-2026 a 06-01-2027"), several attendees separated by ; , or spaces.
S2. Row-level error isolation: a bad row is logged as Error with a reason and never stops other rows.
S3. Time zone explicit (Europe/Madrid) so DST changes (25 Oct 2026) do not shift class times.
S4. Idempotency: each series has a stable key (teacher + title + start date) so a re-run updates rather than duplicates.
S5. Teacher name -> mailbox mapping sheet; unmapped teacher = Error, not a guess.
S6. Dry run first: nothing is sent; output is a workbook (Series, Occurrences, Log) plus the exact Microsoft Graph payloads.

## Deliverables
- `src/invites.py` dry-run engine (pandas/openpyxl; reads .xls and .xlsx).
- `samples/Cursos_demo.xlsx` synthetic file in the client's layout (fictional names, example.com addresses) with messy variants.
- `docs/POWER_AUTOMATE_FLOW.md` flow design (SharePoint trigger, Graph calls, log write-back, permissions).
- Tests (pytest).

## Tests and pass thresholds
- T1 Parsing: every weekday/date/time/festivo/attendee variant in S1 parsed correctly (100%).
- T2 Occurrences: for each sample row, the generated dates equal a hand-written expected list (100%), holidays removed, none outside start..end.
- T3 Errors isolated: each seeded bad row (unknown weekday, end before start, end time before start time, bad email, unknown platform, unmapped teacher, missing field) is logged as Error with the right reason; good rows still produced.
- T4 Graph payload: valid JSON with recurrence pattern weekly, daysOfWeek, range, Europe/Madrid times, isOnlineMeeting/teamsForBusiness for Teams rows.
- T5 Idempotency: same input twice -> same keys; changed time -> same key, payload differs.
- T6 Log sheet: one log row per input row; counts add up.

## Accounts Yannick needs for a live run
A Microsoft 365 work/school tenant with Exchange mailboxes for test teachers, Power Automate (premium HTTP connector or an Entra app with Calendars.ReadWrite), a SharePoint site. Google Workspace for phase 2.
