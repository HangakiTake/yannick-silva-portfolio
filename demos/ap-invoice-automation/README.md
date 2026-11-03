# Accounts-payable invoice automation

Portfolio demo for a Canadian roofing contractor. A mailbox message with one PDF invoice is read, checked, and either turned into a QuickBooks Online bill or answered with a short reply that says exactly what is wrong. The company name in the sample data, Northline Roofing, is fictional. The invoices are synthetic.

The flow that is actually tested is offline:

| Piece | What the tests run | Live service |
| --- | --- | --- |
| Mail | `LocalFolderMailSource` reads `fixtures/mail` | Microsoft Graph adapter is **UNTESTED** |
| Extraction | Rules extractor (labels, French labels, last page wins) | OpenAI / Anthropic adapter is **UNTESTED**. LLM-path accuracy is **not measured** |
| Validation | Deterministic checks after extraction | Same code would run in front of a live model |
| Bills | In-memory QuickBooks client | QuickBooks Online REST adapter is **UNTESTED** |
| Make.com | Hand-written blueprint and step-by-step doc | **UNTESTED**. Not imported, not run |

Rules-path field accuracy on the 30 synthetic invoices is **145/150**. The five misses are the one image-only scan (`inv-27`): pdfplumber cannot read a page that has no text layer. Every other vendor, invoice number, PO, date, and total in the set matched. That number comes from `python -m ap_pipeline.cli eval`. It is not an LLM score.

## What a passing invoice does

1. Exactly one PDF.
2. The PDF has a text layer. A scan without selectable text is failed with `no_text_layer`. The model is not asked to guess.
3. Vendor matches the approved list after case and punctuation are folded.
4. PO matches an **open** job. A closed job and an unknown PO are different failures.
5. Invoice number, subtotal, tax, and total are present. A missing total is not filled in from the other two lines. Tax may be `0.00`. Total must be greater than zero. Credit notes are out of scope.
6. Subtotal + tax equals total within **$0.01**.
7. The date parses. Numeric dates are **day/month/year**. The date is not more than a year before the email arrived, and not more than 7 days after it.
8. Currency is CAD. If the invoice does not name a currency, the pipeline assumes CAD. USD is rejected.
9. Duplicate check, before any bill is created:
   - same vendor and same invoice number, ignoring case and spaces
   - same vendor and same total, with invoice dates within 7 days inclusive, even when the invoice number is new
10. The bill's amount is the invoice total (QuickBooks derives the transaction total from lines). The private note is the PO and the job name. The original PDF bytes are attached.
11. The email is moved to `Processed Invoices`.

A failure or a duplicate is moved to `Failed Invoices`. The reply is a fixed template: one bullet per reason, no extras. `--dry-run` writes that reply under `outbox/drafts` and does **not** create a bill, move the email, or mark the message done. A later run without `--dry-run` can still process it. The sender's domain must be listed on the vendor when `email_domains` is set. A letter inside an amount (`10O0.00`, `52S.00`) is rejected instead of being rewritten into a smaller number. `USD` on the amount line is not treated as CAD. Received dates are read in `America/Toronto`.

## Idempotency

Each message id is stored when handling finishes. A second run creates **0** new bills. Replaying the same files is logged as `already_processed` and does not send a second reply.

If the attachment upload fails after the bill exists, the message stays in the inbox and the state row stays `in_progress`. The next run attaches the PDF and does not create another bill.

If the state file is deleted but the QuickBooks client still has the bills, a replay is blocked as a duplicate instead of creating a second bill. On the real adapter that depends on a query of recent bills (capped at 1000 bills in the last 400 days). That query has not been run against Intuit.

A corrected invoice has to arrive as a new message. The same message id is not processed again after it was filed. If the process dies after the reply is written and before that fact is saved, the next run can send the reply once more. A bill is not created on that path. Once the reply is recorded, a later run only files the message. Two processes cannot hold the same state file; the second run stops. The QuickBooks query used by the untested REST client is still capped, and the local state ledger is included so a bill this demo already recorded is not created again just because it fell outside that query.

## Run the tests

```bash
cd demos/ap-invoice-automation
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Regenerate the synthetic PDFs with `python scripts/generate_synthetic.py` after you change the corpus. They are generated fixtures, not vendor documents.

Run the mock demo without touching the committed fixtures:

```bash
rm -rf /tmp/ap-demo && mkdir -p /tmp/ap-demo
cp -a fixtures/mail/. /tmp/ap-demo/
python -m ap_pipeline.cli run \
  --mail-root /tmp/ap-demo \
  --state /tmp/ap-demo/state.json \
  --log-dir /tmp/ap-demo/logs
python -m ap_pipeline.cli eval \
  --manifest fixtures/manifest.json \
  --out-dir /tmp/ap-demo/eval
```

The eval command writes `rules_accuracy.json` and `llm_accuracy.json`. With no API key, the LLM file says status `not_measured` and `accuracy` is null.

## Honest limits

- Same vendor, same total, within 7 days is blocked even when both invoices are legitimate. That is the control from the spec. A person has to release it.
- The pipeline does not check that tax is 5% or 13%. Provinces differ. It only checks that the printed numbers add up.
- Vendor matching is normalized text, not a fuzzy match. A shortened trade name fails closed until it is added as an alias in `fixtures/vendors.json`.
- QuickBooks line items are one expense line for the invoice total, not one line per product. Job costing via `CustomerRef` is supported in the payload only when `qbo_customer_id` is set on the job. The sample jobs leave it null.
- The live QuickBooks client looks up the vendor by **display name**. The sandbox vendor must be spelled like the master file. Local ids such as `v-cedarline` are never sent as QuickBooks ids.
- The default expense account id `80` is a placeholder. Set `QBO_EXPENSE_ACCOUNT_ID` to an account that exists in the sandbox.
- Production QuickBooks (`quickbooks.api.intuit.com`) is refused unless `QBO_ALLOW_PRODUCTION=yes`.
- Graph mail uses application permissions (`Mail.ReadWrite`) and client credentials. Delegated sign-in is not implemented. A tenant admin has to consent. This path is **UNTESTED**.
- The LLM adapter sends text, not page images. It will not read the image-only invoice. It is **UNTESTED**, and this repo does not call it during `pytest` or during `eval`.
- Make.com steps are in `make/MAKE_SCENARIO.md`. The blueprint is **UNTESTED**.

## Accounts required before this can run live

Do not merge a live configuration until these exist. The owner has to create them; none are in this repo.

1. **Intuit Developer** account and a **QuickBooks Online sandbox** company (free). Create the vendors with the display names in `fixtures/vendors.json`, and note the expense account id.
2. **Make.com** account (free tier is enough to import and try the scenario). The blueprint has never been imported.
3. **OpenAI or Anthropic API key**, if the extractor should be a model rather than the rules parser. LLM accuracy is not measured until that key exists and someone deliberately runs an eval. This demo will not invent a percentage.
4. **Optional: a Microsoft 365 developer tenant** and a test mailbox, if the trigger should be Graph rather than a local folder. The Graph adapter is untested until that mailbox exists.

Until those exist, the only path this repository certifies is the mock one: local folder, rules extractor, in-memory bills.
