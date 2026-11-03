// One daily run: read register -> look up DVLA/DVSA/DocuSign -> evaluate -> plan messages -> write outbox, audit log, dashboard.
// Usage: node src/run.js [--today YYYY-MM-DD] [--data data] [--out out]
'use strict';
const fs = require('fs'), path = require('path');
const { CONFIG_DEFAULTS, evaluateVehicle, planMessages, isDate, canonReg } = require('./engine');
const { makeAdapters } = require('./adapters');
const { readCsv, toCsv } = require('./io');
const { renderDashboard } = require('./dashboard');

const REQUIRED = ['registration', 'make', 'model', 'insurance_expiry', 'insurance_verified_on', 'insurance_verified_source', 'service_due', 'docusign_envelope_id'];
const AUDIT_HEADER = ['logged_at', 'run_date', 'mode', 'registration', 'check', 'result', 'due', 'detail', 'source', 'message_key', 'channel', 'recipient_role'];

function loadInputs(dataDir) {
  const reg = readCsv(path.join(dataDir, 'register.csv'));
  const miss = REQUIRED.filter(c => !(reg[0] && c in reg[0]));
  if (miss.length) throw new Error('register.csv is missing columns: ' + miss.join(', '));
  const seen = new Set(), dupes = [];
  for (const v of reg) { v.registration = v.registration.toUpperCase().replace(/\s+/g, ' ').trim(); const c = canonReg(v.registration); if (seen.has(c)) dupes.push(c); seen.add(c); }
  const opt = f => fs.existsSync(path.join(dataDir, f)) ? readCsv(path.join(dataDir, f)) : [];
  return { register: reg, dupes, docs: opt('documents.csv'), acks: opt('acknowledgements.csv'), config: fs.existsSync(path.join(dataDir, 'config.json')) ? JSON.parse(fs.readFileSync(path.join(dataDir, 'config.json'), 'utf8')) : {} };
}

async function runOnce({ today, dataDir, outDir, adapters, nowIso = new Date().toISOString() }) {
  if (!isDate(today)) throw new Error('today must be YYYY-MM-DD');
  const inp = loadInputs(dataDir), cfg = { ...CONFIG_DEFAULTS, ...(inp.config.rules || {}) };
  fs.mkdirSync(outDir, { recursive: true });
  const statePath = path.join(outDir, 'state.json');
  const state = fs.existsSync(statePath) ? JSON.parse(fs.readFileSync(statePath, 'utf8')) : {};
  const from = new Date(Date.parse(today + 'T00:00:00Z') - cfg.docusignLookbackDays * 86400000).toISOString().slice(0, 10);
  const envelopes = await adapters.docusign(from);
  const results = [];
  for (const v of inp.register) {
    let r;
    try {
      const [dvla, dvsa] = await Promise.all([adapters.dvla(v.registration), adapters.dvsa(v.registration)]);
      r = evaluateVehicle(v, { today, cfg, dvla, dvsa, docs: inp.docs, envelopes });
    } catch (e) { // one bad row must not stop the others
      r = { registration: v.registration, make: v.make, model: v.model, light: 'red', next: null, items: { run: { status: 'CHECK_FAILED', detail: 'internal error: ' + e.message } }, actions: ['run: CHECK_FAILED (internal error)'] };
    }
    if (inp.dupes.includes(canonReg(v.registration))) { r.items.register = { status: 'ATTENTION', detail: 'registration appears more than once in register.csv' }; r.light = r.light === 'green' ? 'amber' : r.light; r.actions.push('register: duplicate row'); }
    results.push(r);
  }
  const plan = planMessages(results, today, cfg, state, inp.acks);
  const channels = inp.config.channels || ['email', 'whatsapp'];
  const outbox = plan.messages.flatMap(m => channels.map(ch => ({ run_date: today, channel: ch, recipient_role: m.to, level: m.level, key: m.key, text: m.text })));
  const audit = [];
  for (const r of results) for (const [check, i] of Object.entries(r.items))
    audit.push({ logged_at: nowIso, run_date: today, mode: adapters.mode, registration: r.registration, check, result: i.status, due: i.due || '', detail: i.detail || '', source: i.source || '' });
  for (const o of outbox) audit.push({ logged_at: nowIso, run_date: today, mode: adapters.mode, registration: o.key.split('|')[0], check: o.key.split('|')[1], result: 'MESSAGE_QUEUED:' + o.level, message_key: o.key, channel: o.channel, recipient_role: o.recipient_role });

  // append-only audit log and outbox; state written last so a crash re-sends rather than silently drops
  const auditPath = path.join(outDir, 'audit_log.csv');
  if (!fs.existsSync(auditPath)) fs.writeFileSync(auditPath, AUDIT_HEADER.join(',') + '\n');
  fs.appendFileSync(auditPath, toCsv(audit, AUDIT_HEADER));
  fs.appendFileSync(path.join(outDir, 'outbox.jsonl'), outbox.map(o => JSON.stringify(o)).join('\n') + (outbox.length ? '\n' : ''));
  fs.writeFileSync(path.join(outDir, 'status.json'), JSON.stringify({ run_date: today, mode: adapters.mode, results }, null, 2));
  fs.writeFileSync(path.join(outDir, 'dashboard.html'), renderDashboard(results, { today, mode: adapters.mode }));
  fs.writeFileSync(statePath, JSON.stringify(plan.state));
  return { mode: adapters.mode, results, messages: plan.messages, outbox, audit };
}

if (require.main === module) {
  const a = process.argv.slice(2), arg = (k, d) => { const i = a.indexOf(k); return i >= 0 ? a[i + 1] : d; };
  const root = path.join(__dirname, '..');
  const today = arg('--today', new Date().toLocaleDateString('en-CA', { timeZone: 'Europe/London' }));
  runOnce({ today, dataDir: path.resolve(root, arg('--data', 'data')), outDir: path.resolve(root, arg('--out', 'out')), adapters: makeAdapters() })
    .then(r => { if (a.includes('--json')) return console.log(JSON.stringify({ run_date: today, mode: r.mode, red: r.results.filter(x => x.light === 'red').length, outbox: r.outbox })); const c = l => r.results.filter(x => x.light === l).length; console.log(`${today} [${r.mode}] ${r.results.length} vehicles: ${c('red')} red, ${c('amber')} amber, ${c('green')} green; ${r.messages.length} new alerts queued`); })
    .catch(e => { console.error('RUN FAILED: ' + e.message); process.exit(1); });
}
module.exports = { runOnce, loadInputs };
