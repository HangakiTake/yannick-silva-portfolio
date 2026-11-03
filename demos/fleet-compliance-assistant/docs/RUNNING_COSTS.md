# Running costs (prices checked 2026-10-28)

Prices change; re-check every line before quoting. Volume basis: in the 40-day simulation of this 25-vehicle demo fleet the system queued 82 alerts, about 62 a month (82 × 30 ÷ 40), each sent on both email and WhatsApp. A real fleet's count depends on how many things are actually due.

| Item | Price | Monthly at demo volume | Source (checked 2026-10-28) |
|---|---|---|---|
| n8n self-hosted Community edition | Free licence, no execution limit | £0 + server | https://docs.n8n.io/choose-how-to-use-n8n (checked 2026-10-28) |
| Small VPS for self-hosted n8n | e.g. DreamHost VPS $8.99/mo for 3 months, then $15.99/mo (one example) | about £7-13 | https://www.dreamhost.com/blog/n8n-self-hosted/ (checked 2026-10-28) |
| or n8n Cloud Starter instead of a VPS | €20/mo billed annually, 2,500 executions (one run a day = about 30) | €20 | https://n8n.io/pricing/ (checked 2026-10-28) |
| Twilio WhatsApp platform fee | $0.005 per message | about $0.31 a month at 62 messages | https://www.twilio.com/en-us/whatsapp/pricing (checked 2026-10-28) |
| Meta WhatsApp utility template fee, UK | £0.0159 per delivered message from 1 Oct 2026 (third-party summary; confirm on Meta's rate card) | about £0.99 a month at 62 messages | https://everymessage.com/insights/whatsapp-message-types-and-pricing/ (checked 2026-10-28) |
| DVLA Vehicle Enquiry Service API | Free (new registrations closed as of today) | £0 | https://developer-portal.driver-vehicle-licensing.api.gov.uk/apis/vehicle-enquiry-service/vehicle-enquiry-service-description.html (checked 2026-10-28) |
| DVSA MOT History API | Free, registration up to 5 working days | £0 | https://documentation.history.mot.api.gov.uk/mot-history-api/register (checked 2026-10-28) |
| Email alerts | Client's existing mailbox via SMTP | £0 | https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.sendemail/ (checked 2026-10-28) |
| DocuSign API | Uses the client's existing DocuSign plan; API access needs an app that passes go-live review. Plan-dependent, so confirm with the client | £0 extra expected, unconfirmed | https://developers.docusign.com/platform/go-live/ (checked 2026-10-28) |

Not included: optional LLM daily summary (not built in this demo), SMS (optional, not built), VAT, currency conversion, and any MIB commercial MID access (priced on application).
