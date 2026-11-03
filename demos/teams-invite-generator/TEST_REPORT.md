# Test report — Teams invite generator

Run: 2026-11-03 08:14 (Europe/Zurich), Python 3.13.5, pandas 3.0.6.
Command: `python -m pytest -q tests` → **55 passed, 0 failed**.

| Spec | What is checked | Tests | Result |
|---|---|---|---|
| T1 parsing | 12 weekday spellings, 4 bad ones rejected, 6 date formats, 10 time formats, holiday list + range, attendee dedupe, bad email | 33 | pass |
| T2 occurrences | 5 sample rows vs hand-written class calendars (92 classes in total); festivos removed; none outside the dates | 6 | pass |
| T3 errors | 7 seeded bad rows logged with the right reason; missing column fails loudly; duplicate row flagged; ambiguous dd/mm date warned; festivo year typo rejected | 11 | pass |
| T4 Graph payload | weekly recurrence, daysOfWeek, range, Europe/Madrid, teamsForBusiness, cancel list; series starts on the first class day; a festivo before the first class is not sent as a cancel | 3 | pass |
| T5 idempotency | same key on rerun, time change keeps key and changes payload, keys unique | 1 | pass |
| T6 log | one log row per non-blank input row; 4 Ready + 1 Phase 2 + 7 Error = 12; Occurrences sheet rows = classes | 1 | pass |

Hand-written calendars (T2): A2+ Mon/Wed 14 Sep–14 Dec = 26 classes (12 Oct removed); B2 Tue/Thu 15 Sep–15 Dec = 26 (8 Dec removed; 12 Oct is a Monday, noted); C1 Fridays 16 Sep–16 Dec = 13 (first class 18 Sep); Business English Mon/Wed/Fri 30 Nov–29 Jan = 19 (8 removed, 21 Dec–6 Jan); Intensivo Mon–Thu 2–13 Nov = 8.

Also run locally (not published): the client's own 3-row sample file → 3 Ready, 66 classes, 1 festivo removed, with no mailbox check (no mapping sheet in that file).

Not tested: anything live against Microsoft Graph or Power Automate (no tenant).
