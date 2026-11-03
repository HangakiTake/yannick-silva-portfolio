# Handover

## 1. Install (self-hosted n8n on a small Linux server)
1. Install Node.js 18+ and n8n (`npm i -g n8n`, or the official Docker image with Node available to the Execute Command node).
2. Copy this folder to `/opt/fleet-compliance-assistant` (or set `FLEET_APP_DIR`).
3. Copy `.env.example` to `.env`, then load it into n8n's environment. Keep `FLEET_MODE=mock` and `SEND_ENABLED=no` at first.
4. In n8n: Workflows > Import from file > `n8n/fleet-compliance.workflow.json`.
5. Create credentials named **Twilio account** and **SMTP account**, and select them on the two send nodes.
6. Click "Run now (manual)". Expect: every alert logged as `DELIVERY_DRY_RUN` in `out/audit_log.csv`, and `out/dashboard.html` refreshed.
7. Activate the workflow (daily 07:00 UK time).

Note: the Execute Command node must be allowed. It is on by default in n8n 1.x, but n8n 2.x disables it, so it must be re-enabled through `NODES_EXCLUDE`. Check your version.

## 2. Go live, one source at a time
| Step | Do | Check |
|---|---|---|
| DVSA | Put the DVSA keys in `.env`, set `FLEET_MODE=live` | MOT column matches the DVSA website for 3 vehicles |
| DVLA | Add `DVLA_API_KEY` (once registration reopens) | Tax column matches gov.uk "check vehicle tax" for 3 vehicles |
| DocuSign | Create an integration key, JWT grant, and put the access token in `.env` | Pending and signed agreements match DocuSign |
| Sending | `SEND_ENABLED=yes`, WhatsApp sandbox first | Audit log shows DELIVERY_SENT for both channels |

Live mode needs **all** DVLA, DVSA and DocuSign variables. It stops and names any missing ones rather than mixing live and recorded data.

DocuSign access tokens expire after about an hour. For unattended runs, swap the static token for n8n's DocuSign OAuth2 credential or a JWT refresh step. That isn't built in this demo.

## 3. Daily operation
- Dashboard: `out/dashboard.html` (red first).
- To acknowledge an urgent item, add a row to `data/acknowledgements.csv`.
- Fix the data (renew tax, book the MOT, record a manual insurance check) and the item clears on the next run.

## 4. Data protection checklist (tick before go-live)
- [ ] `.env` is not in git or backups shared outside the company
- [ ] Recipients set only in n8n environment/credentials
- [ ] Messages contain registration + task only (verified by `npm test`, R11)
- [ ] Audit log stores roles, not phone numbers or emails
- [ ] Server disk encrypted; access limited to named staff
- [ ] Retention agreed for `out/audit_log.csv` (suggest 6 years to match typical record-keeping, client to confirm)

## 5. Handover session script (30 min)
1. (5 min) Dashboard tour using the 5 reviewer questions.
2. (5 min) A reminder, an urgent alert and an escalation, traced in the audit log.
3. (10 min) Update the register: a new vehicle, a manual insurance check, an acknowledgement. Run it and watch it change.
4. (5 min) What CHECK FAILED and UNVERIFIED mean and what to do.
5. (5 min) Where the keys live, how to turn sending off, rollback.

## 6. Known limits
See README "Integration limits". There is no MID automation, no Fleetworks connection, no SMS and no LLM summary in this demo.

Open go-live tasks found in the realism review (docs/realism-review.md):
- DocuSign: the adapter reads one page of envelope status changes. A fleet with more than 100 envelopes changing in the look-back window needs pagination (`start_position`) added before go-live.
- A delivery is logged as SENT only when Twilio returns a message `sid` or SMTP returns a `messageId`; anything else is FAILED. Check the first live send shows DELIVERY_SENT rows before you rely on it.
