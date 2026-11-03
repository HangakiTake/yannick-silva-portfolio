# Change management note

**Who is affected:** the fleet manager (gets reminders and owns acknowledgements), a second contact (gets escalations), and whoever updates the register and documents list.

**What changes for them**
- Tax and MOT dates stop being typed in. They come from DVLA and DVSA, and a failed lookup is shown as CHECK FAILED, not hidden.
- Insurance still needs a person. The system asks for a manual askMID or insurer check every 30 days and records who did it. It will never say "insured" on its own.
- Acknowledging an urgent alert means adding one line to `acknowledgements.csv` (or the matching sheet tab). That stops escalation but not the alert: the item stays red until it is actually fixed.
- Reminders arrive at 30, 14, 7 and 1 days before each deadline, once each.

**Rollout (suggested, 3 weeks)**
1. Week 1, shadow mode: live lookups on, `SEND_ENABLED=no`. Compare the dashboard with the current spreadsheet every day and log any difference.
2. Week 2, email only to the fleet manager. Tune `dueSoonDays` and the ladder if it is too noisy.
3. Week 3: add WhatsApp and the escalation contact. The old spreadsheet reminders can be retired once a full week passes with no differences.

**Risks and mitigations**
| Risk | Mitigation |
|---|---|
| Alert fatigue | Ladder sends each step once; tune in week 2; only red items escalate |
| False comfort from green | Green requires every check to succeed; failed lookups are red; insurance can't go green without a recent manual check |
| Register quality (wrong date format, duplicates) | Bad dates show CHECK FAILED; duplicates flagged; input spec in docs/INPUT_SPEC.md |
| API outage or key expiry | Shows CHECK FAILED on the dashboard and in alerts the same day |
| Staff leave | Escalation contact plus role-based (not person-based) recipients |

**Rollback:** deactivate the n8n workflow. The register and the audit log stay as they are, so nothing is lost.

**Training:** a 30-minute handover (script in HANDOVER.md) and the 5-question dashboard check (REVIEWER_QUESTIONS.md).
