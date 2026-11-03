# Make.com scenario — UNTESTED

This document mirrors the Python pipeline in `ap_pipeline`. The JSON file next to it, `ap-invoice-automation.blueprint.json`, is a hand-written blueprint. **It has not been imported into Make.com and it has not been run.** Module keys (`microsoft-email:*`, `quickbooks:createBill`, `http:ActionSendData`) are placeholders. After import, open every module, confirm the app picked the right action, and connect your own Microsoft 365, OpenAI or Anthropic, and QuickBooks Online sandbox accounts. Expect to fix mapping. Do not turn scheduling on until a sandbox bill looks right.

The scenario is sequential on purpose. A later invoice in the same run must be able to see a bill created earlier in that run, or the duplicate check is late.

## What the scenario has to do

1. **Watch the mailbox.** Microsoft 365 Email, new messages in Inbox that have attachments.
2. **Count PDF attachments.** Exactly one PDF continues. Zero PDFs, or more than one, is a failure.
3. **Read the PDF text.** Make's PDF parser, then a structured model call (OpenAI json_schema or Anthropic tool use) with the fields `vendor_name`, `invoice_number`, `po_number`, `invoice_date`, `subtotal`, `tax`, `total`, `currency`. The model must return null for a missing field. It must not add subtotal and tax to invent a total.
4. **Validate in Make, not in the model.**
   - Vendor display name is on an approved list (a Make data store or a Google Sheet is enough for the pilot).
   - PO number is on the open-job list, and the job status is open.
   - Invoice date parses. Numeric dates are day/month/year.
   - Date is not more than a year before receipt and not more than 7 days after receipt.
   - Subtotal, tax, and total are all present. Tax may be 0.00. Total must be greater than zero.
   - Subtotal + tax equals total within 0.01.
   - Currency is CAD. A missing currency is treated as CAD. USD is a failure.
   - Invoice number is 1–21 characters from `A–Z`, `0–9`, `.`, `/`, `-`.
5. **Duplicate check before any bill.**
   - Same vendor and the same invoice number as a bill already in QuickBooks: stop.
   - Same vendor, same total, invoice dates within 7 days (inclusive): stop, even if the invoice number is new.
6. **Pass.** Create the QuickBooks bill in the **sandbox** company. One expense line for the invoice total (QuickBooks computes `TotalAmt` from lines). `DocNumber` is the invoice number. `PrivateNote` is `PO-xxxx` plus the job name. Then upload the original PDF with the multipart attachment call (`file_metadata_0` and `file_content_0`) linked to that Bill. Move the email to a mailbox folder named `Processed Invoices`.
7. **Fail or duplicate.** Send the templated reply. Each bullet is one failed check, in the same words the Python `REASON_TEXT` table uses, and no extra bullets. Move the email to `Failed Invoices`. While you are testing, create a **draft** instead of sending.
8. **Run it twice.** The second run must not create another bill for the same message. Store the message id in a Make data store when the bill is created, and also rely on the duplicate query so a lost store record still cannot create a second bill.

## Sandbox setup before the first live run

- QuickBooks Online sandbox company, with each approved vendor created under the **same display name** as `fixtures/vendors.json`.
- An expense account id. The Python default `80` is only a placeholder.
- Optional later: a QuickBooks customer id per job, mapped from `fixtures/open_jobs.json`, if you want job costing on the line.
- Microsoft 365 mailbox with two folders: `Processed Invoices` and `Failed Invoices`.
- Model API key. The blueprint does not contain one.

The blueprint's `{{4.ok}}` filter is a placeholder. The JSON does **not** compute the arithmetic check, the open-PO check, or the duplicate check. Those have to be built as Make filters or data-store lookups before the scenario is allowed to create a bill. The reply text in the JSON is shorter than the Python template on purpose: use `ap_pipeline/reasons.py` as the wording source.

## What this scenario does not prove

No Make run has been executed. A successful import is not a test. The Python suite is the tested path, and it uses a local folder, a rules extractor, and an in-memory QuickBooks client. LLM field accuracy is **not measured**.
