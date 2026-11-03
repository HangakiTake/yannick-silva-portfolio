# Power Automate flow design (live version)

Status: design only. Not built or run. It needs a Microsoft 365 work or school tenant, which this demo does not have.

## Shape
1. **Trigger.** "When a file is created or modified" in a SharePoint library called `Cursos`. A manual "Run now" button flow is also provided for reruns.
2. **Dry run.** An Azure Function (or Power Automate's own "Run script" action) runs `invites.py` logic on the file and writes `dry_run.xlsx` beside it. A coordinator approves it in Teams with the "Start and wait for an approval" action. Nothing is created before approval.
3. **For each Ready series** (concurrency set to 1 so the log order is stable):
   - Look up `key` in a SharePoint list called `InviteLog`, with the columns Key, Mailbox, EventId, PayloadHash, Status and LastRun.
   - **Not found:** `POST https://graph.microsoft.com/v1.0/users/{mailbox}/events` with `create_event`. Save the returned `id`.
   - **Found, same PayloadHash:** skip and log "unchanged".
   - **Found, different hash:** `PATCH /users/{mailbox}/events/{EventId}` with the changed fields.
   - **For each date in `cancel_occurrences`:** `GET /users/{mailbox}/events/{EventId}/instances?startDateTime=...&endDateTime=...` for that day, then `POST /events/{instanceId}/cancel` with a short comment ("Festivo").
4. **Rows with Error or Phase 2 status** are written to `InviteLog` with their reason. Nothing is sent for them.
5. **Write-back.** A summary (created, updated, unchanged, errors) is posted to the coordinator, and the Log sheet is attached.

## Why each piece
- **`transactionId`** (the series key) stops a retried POST from creating a second event. The `InviteLog` list is what makes a rerun days later update the series instead of duplicating it. `transactionId` alone does not do that.
- **The key is the teacher + title + start date.** Changing the time, days, festivos or attendees updates the series. Changing the start date or the title creates a new series, and the old one has to be cancelled by hand. This is listed in the log.
- **Times are sent with `timeZone: Europe/Madrid`,** so the 25 Oct 2026 clock change does not move a 09:00 class.
- **Holidays are cancelled per instance.** Graph has no "exclude dates" field on a recurrence.

## Accounts and permissions needed
- A Microsoft 365 tenant with an Exchange Online mailbox for each teacher (or a shared organiser mailbox).
- One of:
  - Power Automate with the premium "HTTP with Microsoft Entra ID" connector, or
  - an Entra app registration with the **Calendars.ReadWrite** application permission and admin consent. An application access policy should limit it to the teachers' mailboxes.
- A SharePoint site for the `Cursos` library and the `InviteLog` list.
- **Phase 2 (Google Meet):** a Google Workspace domain with a service account and domain-wide delegation for `calendar.events`, using `conferenceData.createRequest` with `hangoutsMeet`.

## Not designed yet
- Deleting a whole series when its row is removed from the sheet. This should go through a manual "cancel" column rather than happen automatically.
- Teams meeting options such as lobby and recording.
