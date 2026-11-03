# Input spec

All inputs are UTF-8 CSV with a header row. Dates are **YYYY-MM-DD** (ISO). A date in any other format (for example 01/12/2026) shows as CHECK FAILED rather than being guessed. Registrations can include spaces; they are upper-cased and spaces removed before API calls.

## data/register.csv (one row per vehicle; required)
| Column | Required | Example | Notes |
|---|---|---|---|
| registration | yes | AB12 CDE | Unique. A duplicate row is flagged ATTENTION |
| make, model | yes | FORD, TRANSIT CUSTOM | Display only |
| insurance_expiry | yes | 2027-04-01 | Policy end date |
| insurance_verified_on | no | 2026-10-28 | Date a **person** last checked askMID or the insurer. Blank = UNVERIFIED |
| insurance_verified_source | no | askMID manual check (staff) | Who or what was checked |
| service_due | yes | 2027-01-31 | Next service date |
| docusign_envelope_id | no | GUID | The hire agreement envelope. Blank = no agreement tracked |
| notes | no | | Ignored by the rules |

Tax and MOT dates are **not** typed into the register. They come from DVLA and DVSA.

## data/documents.csv
`registration, document, present`. One row per required document per vehicle. Required documents are set in `data/config.json` (`rules.requiredDocuments`, default V5C logbook, Insurance certificate, Hire agreement). present = yes / y / true / 1 counts as present; anything else, or no row at all, is MISSING. Registrations are matched ignoring case and spaces (`za03dvk` = `ZA03 DVK`), here, in the register and in acknowledgements.csv; two register rows that match this way are flagged as duplicates.

## data/acknowledgements.csv
`registration, check, acknowledged_on, by_role` (check is tax, mot, insurance, service, documents, agreement). An acknowledgement stops escalation for that item. It does not close the item: only a clear check does.

## data/config.json
`dueSoonDays`, `ladder` (reminder days), `insuranceVerifyWindowDays`, `escalateAfterDays`, `pendingSignatureDays`, `channels`.

## Environment (.env)
See `.env.example`. Contact addresses live only in n8n's environment. They are never written to the register, messages or audit log.

## Outputs (out/)
| File | Content | Personal data |
|---|---|---|
| status.json | Every item per vehicle | None (registration + dates) |
| dashboard.html | One-page status | None |
| audit_log.csv | Append-only: every check, queued message and delivery result (SENT / FAILED / DRY_RUN) | None: role names, not addresses |
| outbox.jsonl | Messages queued per channel | Registration + task text only |
| state.json | Reminder keys already sent | None |
