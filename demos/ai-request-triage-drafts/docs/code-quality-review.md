# Code review: incoming request drafts

Reviewed against the plan in `PLAN_AND_SPECS.md` and against the code in `src/triage/`. Categories below are must-fix, should-fix, and minor. After the fixes in this build, the must-fix and should-fix lists are empty.

## What holds up

- One path reads the inbox, checks model JSON, drops anything not in the request, writes a draft, and appends a review row. Mail is never sent. A scan of `src/` finds no `smtplib`, `imaplib`, or send call, and the tests block `socket.create_connection`.
- Invalid model JSON is retried once and then discarded. A second failure does not keep a partial name or amount. 12 malformed payloads, 0 accepted.
- The same inbox a second time adds 0 rows and 0 drafts, and does not call the model again. A file lock covers the write. Removed inbox files are dropped from `state.json`.
- The webhook returns 401 when `TRIAGE_WEBHOOK_TOKEN` is unset or wrong, 413 over 200,000 characters, and 422 on a body that fails validation. Errors returned to the caller do not include the traceback.
- Application logs record the id, the type, and whether a person is needed. A body marker used in the tests ("Sellwood") does not appear in the log stream or the review log.
- 300 mock emails took 0.431 seconds on this machine. The work is local parsing, not a network call.

## Fixed before this review was closed

1. **Must-fix.** A short forward of the business's own quote was saved as a customer quote, with the business's price in the fields. Forwards whose From address is on To, Cc or Delivered-To are not treated as the new request. Test: `test_forwarded_staff_mail_is_not_a_customer_quote`.
2. **Should-fix.** `--redact` cleaned the CSV and left the addresses in `state.json`. A redacted run stores the redacted row, and the cache key includes the redact flag so a later full run is not stuck with blanks.
3. **Should-fix.** `POST /triage` ran with no token if the variable was empty. It now refuses until the token is set.
4. **Should-fix.** The model summary was stored as written, so a summary could say "refund" or a price the fields did not contain. The saved summary is rebuilt from the grounded fields. Test: `test_model_summary_cannot_add_a_refund`.
5. **Should-fix.** The "at Company" capture included the next sentence ("Northwind Bakery. Please"). The period ends the name.
6. **Should-fix.** The labelling rules count "USD 150" as money and the extractor dropped it. It is now `$150`.
7. **Should-fix.** The draft fact check ran only as a test. Saving a draft now runs the same check and, on a hit, stores a short "a person needs to read this" reply and marks the row for a person.
8. **Should-fix.** Review-log cells that start with `=` are prefixed so a spreadsheet formula in a subject cannot run. Header fields in the model prompt are forced onto one line so a subject cannot break the prompt.

## Second pass

A separate read of the same tree, using inputs the first 23 tests did not send, found more. All of these are fixed and covered by tests:

1. **Must-fix.** "Thanks for the standard home clean last week" was filed as a quote and the draft named $129. A service word is a quote only when the message is also asking for something. "not a deep clean" no longer selects the deep-clean price. "home cleaning" no longer matches the alias "home clean".
2. **Must-fix.** "Can you help me? I need a handyman" was filed as support. A new job wins over a weak help-word. A lockbox reschedule from someone named Price stays support, because the surname is taken out of the text before the word "price" is considered.
3. **Must-fix.** A model could return the name "April Chen" or the phone "3122026503" by gluing words and digits that do appear, separately, in the mail. The full name has to appear as a phrase, and the phone digits have to sit together. A miss here is flagged for a person.
4. **Must-fix.** Editing the price in the tone file and running again kept the old draft. The cache key now includes the tone file. A second run after the change rewrites the draft.
5. **Must-fix.** A hidden HTML block with a nested tag leaked the hidden price into a quote. Hidden regions now close on the matching tag. An unclosed hide is sent to a person and its text is not quoted. A CSS class set to `display:none` is skipped. A plain part that only says "View this email in HTML" is replaced by the HTML part.
6. **Should-fix.** `POST /triage` did not write the review log and called the model again on a retry. It now uses the same lock, log and cache as a folder run. A repeat of the same message stays one row.
7. **Should-fix.** The hours line ignored `opening_hours`. The draft includes that field when it is not already one of the allowed sentences. A banned word such as "refund" fails the fact check even if it is pasted into an allowed sentence, and a display name that contains one of those words is not used as the greeting.

## Minor (left as they are)

- The summary is a fixed three-line template. It will not read like a person wrote it. That is the trade for not letting the summary invent a fact.
- Token costs in the handoff divide characters by 4. That is not the vendor tokenizer.
- The lock is for one machine. Two servers writing the same `out/` directory are not supported.
- pytest prints one Starlette warning about `httpx` versus `httpx2`. The assertion still passes. Switching the test client would be for a later dependency bump.
- "Tomorrow" is not given a date. The labelling rules say only calendar dates count.

## Plan gaps that are stated, not coded around

Live OpenAI / Anthropic was not run (no key). Zapier and Power Automate are in `HANDOFF.md` and were not executed. Those are the realism-review fails, not unfinished functions in `src/`.
