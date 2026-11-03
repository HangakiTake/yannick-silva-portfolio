// Builds n8n/fleet-compliance.workflow.json. Credentials are referenced by name only; no secrets in the file.
// Approach: n8n schedules and sends; the rule engine runs as a Node script via the Execute Command node, so the
// logic tested by `npm test` is exactly what n8n runs.
'use strict';
const fs = require('fs'), path = require('path');
const node = (name, type, typeVersion, position, parameters, extra = {}) => ({ id: name.toLowerCase().replace(/[^a-z0-9]+/g, '-'), name, type, typeVersion, position, parameters, ...extra });
const DIR = '={{ $env.FLEET_APP_DIR || "/opt/fleet-compliance-assistant" }}';
// The Pack nodes decide SENT / FAILED / DRY_RUN per item from evidence (Twilio sid or SMTP messageId), never from which
// output an item arrived on: the Email node can emit failed items on its success output. Then one Execute Command
// appends the batch (Execute Command runs once per execution, not once per item).
// Send nodes use continueRegularOutput: exactly one output item per input item, in order, so item i of a send
// node is item i of that channel's By channel output (n8n drops paired-item data on error items).
const pack = (srcExpr) => `const clean = s => String(s ?? '').replace(/[^A-Za-z0-9 |:._-]/g, ' ');
const srcs = ${srcExpr};
const out = $input.all();
if (out.length !== srcs.length) throw new Error('result count ' + out.length + ' != sent count ' + srcs.length);
const rows = out.map((it, i) => {
  const src = srcs[i].json, j = it.json;
  const err = j.error && (j.error.message || j.error);
  const result = !src.send ? 'DRY_RUN' : (!err && (j.sid || j.messageId)) ? 'SENT' : 'FAILED';
  return [src.run_date, src.key, src.channel, result, result === 'FAILED' ? (err || 'no delivery id returned') : ''].map(clean).join('~');
});
return [{ json: { batch: rows.join(';;'), count: rows.length } }];`;
const nodes = [
  node('Every day 07:00', 'n8n-nodes-base.scheduleTrigger', 1.2, [0, 0], { rule: { interval: [{ field: 'days', triggerAtHour: 7 }] } }),
  node('Run now (manual)', 'n8n-nodes-base.manualTrigger', 1, [0, 200], {}),
  node('Run compliance checks', 'n8n-nodes-base.executeCommand', 1, [240, 100], { command: '=cd "{{ $env.FLEET_APP_DIR || "/opt/fleet-compliance-assistant" }}" && node src/run.js --json' }),
  node('Split alerts', 'n8n-nodes-base.code', 2, [480, 100], { jsCode:
`const raw = $input.first().json.stdout || '';
let run;
try { run = JSON.parse(raw.trim().split('\\n').pop()); } catch (e) { throw new Error('Compliance run did not return JSON: ' + raw.slice(0, 300)); }
const to = { primary: { email: $env.ALERT_EMAIL_PRIMARY, whatsapp: $env.ALERT_WHATSAPP_PRIMARY }, escalation: { email: $env.ALERT_EMAIL_ESCALATION, whatsapp: $env.ALERT_WHATSAPP_ESCALATION } };
return run.outbox.map(o => ({ json: { ...o, address: (to[o.recipient_role] || {})[o.channel] || '', send: $env.SEND_ENABLED === 'yes' } }));` }),
  node('Sending enabled?', 'n8n-nodes-base.if', 2, [720, 100], { conditions: { options: { caseSensitive: true, typeValidation: 'strict' }, combinator: 'and', conditions: [{ id: 'c1', leftValue: '={{ $json.send }}', rightValue: true, operator: { type: 'boolean', operation: 'true', singleValue: true } }] } }),
  node('By channel', 'n8n-nodes-base.switch', 3, [960, 0], { rules: { values: [
    { conditions: { options: { caseSensitive: true, typeValidation: 'strict' }, combinator: 'and', conditions: [{ leftValue: '={{ $json.channel }}', rightValue: 'whatsapp', operator: { type: 'string', operation: 'equals' } }] }, renameOutput: true, outputKey: 'whatsapp' },
    { conditions: { options: { caseSensitive: true, typeValidation: 'strict' }, combinator: 'and', conditions: [{ leftValue: '={{ $json.channel }}', rightValue: 'email', operator: { type: 'string', operation: 'equals' } }] }, renameOutput: true, outputKey: 'email' }] } }),
  node('WhatsApp (Twilio)', 'n8n-nodes-base.twilio', 1, [1200, -100], { toWhatsapp: true, from: '={{ $env.TWILIO_WHATSAPP_FROM }}', to: '={{ $json.address }}', message: '={{ $json.text }}' }, { credentials: { twilioApi: { id: 'REPLACE_ME', name: 'Twilio account' } }, onError: 'continueRegularOutput' }),
  node('Email (SMTP)', 'n8n-nodes-base.emailSend', 2.1, [1200, 100], { fromEmail: '={{ $env.ALERT_EMAIL_FROM }}', toEmail: '={{ $json.address }}', subject: '={{ $json.level === "reminder" ? "Fleet reminder" : "URGENT fleet alert" }}: {{ $json.text.slice(0, 60) }}', emailFormat: 'text', text: '={{ $json.text }}\n\nOpen the dashboard for details. Reply is not monitored.', options: {} }, { credentials: { smtp: { id: 'REPLACE_ME', name: 'SMTP account' } }, onError: 'continueRegularOutput' }),
  node('Pack WhatsApp results', 'n8n-nodes-base.code', 2, [1440, -100], { jsCode: pack("$('By channel').all(0)") }),
  node('Pack email results', 'n8n-nodes-base.code', 2, [1440, 100], { jsCode: pack("$('By channel').all(1)") }),
  node('Pack DRY_RUN', 'n8n-nodes-base.code', 2, [1440, 300], { jsCode: pack('$input.all()') }),
  node('Write to audit log', 'n8n-nodes-base.executeCommand', 1, [1680, 100], { command: '=cd "{{ $env.FLEET_APP_DIR || "/opt/fleet-compliance-assistant" }}" && node src/log_delivery.js out \'{{ $json.batch }}\'' }),
];
const c = (from, to, outIdx = 0) => [from, to, outIdx];
const links = [c('Every day 07:00', 'Run compliance checks'), c('Run now (manual)', 'Run compliance checks'), c('Run compliance checks', 'Split alerts'), c('Split alerts', 'Sending enabled?'),
  c('Sending enabled?', 'By channel', 0), c('Sending enabled?', 'Pack DRY_RUN', 1), c('By channel', 'WhatsApp (Twilio)', 0), c('By channel', 'Email (SMTP)', 1),
  c('WhatsApp (Twilio)', 'Pack WhatsApp results'), c('Email (SMTP)', 'Pack email results'),
  c('Pack WhatsApp results', 'Write to audit log'), c('Pack email results', 'Write to audit log'), c('Pack DRY_RUN', 'Write to audit log')];
const connections = {};
for (const [f, t, i] of links) { const m = (connections[f] ||= { main: [] }).main; while (m.length <= i) m.push([]); m[i].push({ node: t, type: 'main', index: 0 }); }
const wf = { id: 'FleetDemo0000001', name: 'Fleet compliance assistant (demo)', nodes, connections, settings: { executionOrder: 'v1', timezone: 'Europe/London' }, active: false, pinData: {}, meta: { templateCredsSetupCompleted: false }, tags: [] };
fs.mkdirSync(path.join(__dirname, '../n8n'), { recursive: true });
fs.writeFileSync(path.join(__dirname, '../n8n/fleet-compliance.workflow.json'), JSON.stringify(wf, null, 2) + '\n');
console.log('wrote n8n/fleet-compliance.workflow.json with', nodes.length, 'nodes');
