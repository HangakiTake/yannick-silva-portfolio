# Realism-gate review: Teams invite generator

**Reviewer persona:** the operations coordinator at a language school. She schedules about 40 courses a term and has already had a "calendar bot" double-book 200 students. She does not care about visuals. Her questions are: will it create duplicate or wrong invites, and what happens when a teacher types the sheet badly?

## Findings, by severity
1. **High, fixed.** A duplicated row produced two series with the same key, which in a live run means double invites. It is now logged as an Error ("duplicate of row N"). A regression test was added.
2. **High, open and stated.** Nothing has been run against Microsoft Graph. The payload shape follows the Graph v1.0 docs but has not been accepted by a real tenant. This is labelled as a dry run on every page.
3. **Medium, fixed (mitigated).** Ambiguous text dates like 03/04/2027 are still read day-first, but the Log now flags "check Fecha inicio: read as day/month". Dates stored as real Excel dates are not ambiguous.
4. **Medium, fixed.** A holiday more than a year outside the course (e.g. 12-10-2062) is now an Error. One just outside the dates is ignored, with a note.
5. **Medium, fixed.** "9:00 am" and English weekday names were rejected. They are now parsed.
6. **Low, by design.** Changing a start date or title creates a new series key. The flow design says the old series has to be cancelled by hand.

## Stress test (independent of the sample generator: `tests/stress.py` and the client's own file)
| Input | Result | Verdict |
|---|---|---|
| Client's real 3-row Cursos.xls (local only, not published) | 3 Ready, 66 classes, 1 festivo removed | OK |
| Duplicate row | 2nd row Error "duplicate of row 2" | OK (after fix) |
| US date 09/14/2026 | Error "not a date" | OK |
| Ambiguous 03/04/2027 | Read as 3 Apr, Ready, with a "check … day/month" note | OK (after fix; still needs a human look) |
| Festivo year typo 2062 | Error "year typo?" | OK (after fix) |
| Course spanning DST change 25 Oct | 26 classes; times sent with Europe/Madrid | OK (Graph not exercised) |
| Headers in caps with spaces | Columns found | OK |
| Attendees on new lines | Parsed | OK |
| "9:00 am" | Parsed (after fix) | OK |
| "Monday" | Parsed (after fix) | OK |
| Same start and end date, not a class day | Error "no class dates" | OK |
| Teacher name with trailing space | Mapped | OK |
| Missing Festivos column | Run stops with "sheet is missing columns: festivos" | OK |

## Planted numbers?
The 55 tests run on a sample I wrote myself. The occurrence lists were written by hand from a calendar, before the code was run on them. The client's file was the only independent input, and it has 3 rows. The denominators are stated in TEST_REPORT.md.

## Score sheet (Pass or Fail, never averaged)
| # | Item | Result | Evidence or reason |
|---|---|---|---|
| 1 | Data realism | **Fail** | Independent data is the client's 3-row file. Everything else is synthetic or variants. No term-sized real sheet. |
| 2 | Grounding | Pass | Every series links back to its sheet row number. The Log shows the reason, first/last class and removed count per row. |
| 3 | Evaluation | Pass (for a dry run) | Hand-written expected calendars fixed before the run. 55 tests with denominators. Regressions kept. No live hold-out. |
| 4 | Failure modes / human-in-the-loop | Pass | Errors isolated per row. Duplicate check. Approval step before anything is sent (design). |
| 5 | Integration | **Fail** | Not connected to Graph or Power Automate. The system of record (InviteLog) and idempotency are designed, not built. |
| 6 | Security | **Fail** | Permission scope and an application access policy are described. Nothing is enforced, because no tenant exists. |
| 7 | Cost and latency | **Fail** | Not measured live. The dry run takes under 1 s for 12 rows; that is the only number. |
| 8 | Honest claims | Pass | Every page says "dry run, needs your Microsoft 365 tenant". Limits are listed next to the claims. |

**Ship decision:** OK as a portfolio demo. Section 8 passes, and the fails (1, 5, 6, 7) are listed on the project page. Not ready for live client use.

## Fix list
- **Quick wins (done):** duplicate-row Error; am/pm times; English weekdays; ambiguous-date warning; holiday year-typo Error.
- **Bigger upgrades:**
  - Build the flow in a test tenant and record the Graph responses.
