// Pure rule engine: no network, no file access. The same code runs in the CLI and inside the n8n Code node.
'use strict';
const CONFIG_DEFAULTS = {
  dueSoonDays: 30,               // inside this window an item is DUE_SOON
  ladder: [30, 14, 7, 1],        // reminder rungs, days before the deadline
  insuranceVerifyWindowDays: 30, // a manual MID/askMID check older than this shows UNVERIFIED
  escalateAfterDays: 2,          // unacknowledged urgent issue goes to the second contact after this
  pendingSignatureDays: 0,       // any envelope not completed is flagged (0 = flag immediately)
  docusignLookbackDays: 365,     // live DocuSign: list envelope changes since this many days ago
  requiredDocuments: ['V5C logbook', 'Insurance certificate', 'Hire agreement'], // each vehicle needs a "present" row for each
};
const PRESENT = ['yes', 'y', 'true', '1'];
// Registrations are compared ignoring case and spaces: "za03dvk" and "ZA03 DVK" are the same vehicle.
const canonReg = r => String(r || '').toUpperCase().replace(/\s+/g, '');
const sameReg = (a, b) => canonReg(a) === canonReg(b);
const RED = ['OVERDUE', 'CHECK_FAILED', 'ACTION_REQUIRED'];
const AMBER = ['DUE_SOON', 'UNVERIFIED', 'ATTENTION', 'MISSING', 'PENDING'];

const dayNum = s => Math.floor(Date.UTC(+s.slice(0, 4), +s.slice(5, 7) - 1, +s.slice(8, 10)) / 86400000);
const daysBetween = (from, to) => dayNum(to) - dayNum(from);
const isDate = s => typeof s === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(s) && !isNaN(dayNum(s));

function byDate(due, today, cfg) {
  if (!isDate(due)) return { status: 'CHECK_FAILED', due: null, daysLeft: null, detail: `missing or invalid date "${due ?? ''}"` };
  const d = daysBetween(today, due);
  return { status: d < 0 ? 'OVERDUE' : d <= cfg.dueSoonDays ? 'DUE_SOON' : 'OK', due, daysLeft: d };
}

// DVLA VES -> tax item
function taxItem(dvla, today, cfg) {
  if (!dvla.ok) return { status: 'CHECK_FAILED', due: null, daysLeft: null, detail: `DVLA: ${dvla.error}`, source: 'DVLA VES' };
  const b = dvla.body;
  if (b.taxStatus === 'SORN') return { status: 'ACTION_REQUIRED', due: null, daysLeft: null, detail: 'SORN declared: must not be used or hired on public roads', source: 'DVLA VES' };
  if (b.taxStatus === 'Untaxed') return { ...byDate(b.taxDueDate, today, cfg), status: 'OVERDUE', detail: 'DVLA says Untaxed', source: 'DVLA VES' };
  if (b.taxStatus !== 'Taxed') return { status: 'ATTENTION', due: b.taxDueDate || null, daysLeft: null, detail: `DVLA tax status "${b.taxStatus}"`, source: 'DVLA VES' };
  return { ...byDate(b.taxDueDate, today, cfg), source: 'DVLA VES' };
}

// DVSA MOT History (primary) cross-checked against DVLA motExpiryDate
function motItem(dvsa, dvla, today, cfg) {
  if (!dvsa.ok) return { status: 'CHECK_FAILED', due: null, daysLeft: null, detail: `DVSA: ${dvsa.error}`, source: 'DVSA MOT History' };
  const b = dvsa.body, tests = (b.motTests || []).slice().sort((a, c) => (c.completedDate || '').localeCompare(a.completedDate || ''));
  if (!tests.length) return { ...byDate(b.motTestDueDate, today, cfg), detail: 'No MOT yet (new vehicle): first test due', source: 'DVSA MOT History' };
  const lastPass = tests.find(t => t.testResult === 'PASSED');
  const item = { ...byDate(lastPass && lastPass.expiryDate, today, cfg), source: 'DVSA MOT History' };
  const latest = tests[0];
  if (latest.testResult === 'FAILED') {
    const dangerous = (latest.defects || []).some(d => d.dangerous || d.type === 'DANGEROUS');
    return { ...item, status: dangerous ? 'ACTION_REQUIRED' : (RED.includes(item.status) ? item.status : 'ATTENTION'),
      detail: `Latest MOT test FAILED on ${latest.completedDate.slice(0, 10)}${dangerous ? ' with a DANGEROUS defect: do not hire' : ''}` };
  }
  if (dvla.ok && dvla.body.motExpiryDate && item.due && dvla.body.motExpiryDate !== item.due && item.status === 'OK')
    return { ...item, status: 'ATTENTION', detail: `DVLA MOT expiry ${dvla.body.motExpiryDate} differs from DVSA ${item.due}; check manually` };
  return item;
}

// Insurance: there is no automated MID feed in this system, so it is never shown as "verified" by the system.
function insuranceItem(v, today, cfg) {
  const exp = byDate(v.insurance_expiry, today, cfg);
  const mid = isDate(v.insurance_verified_on) && daysBetween(v.insurance_verified_on, today) <= cfg.insuranceVerifyWindowDays && daysBetween(v.insurance_verified_on, today) >= 0
    ? `Manually checked ${v.insurance_verified_on} (${v.insurance_verified_source || 'source not recorded'})`
    : 'UNVERIFIED: no automated MID check; do a manual askMID / insurer check';
  if (exp.status === 'OVERDUE' || exp.status === 'CHECK_FAILED') return { ...exp, mid, source: 'Register (policy dates)' };
  if (mid.startsWith('UNVERIFIED')) return { ...exp, status: 'UNVERIFIED', mid, detail: 'Insurance not verified in the last ' + cfg.insuranceVerifyWindowDays + ' days', source: 'Register (policy dates)' };
  return { ...exp, mid, source: 'Register (policy dates)' };
}

function evaluateVehicle(v, ctx) {
  const { today, cfg, dvla, dvsa, docs, envelopes } = ctx;
  const items = {
    tax: taxItem(dvla, today, cfg),
    mot: motItem(dvsa, dvla, today, cfg),
    insurance: insuranceItem(v, today, cfg),
    service: { ...byDate(v.service_due, today, cfg), source: 'Register' },
  };
  // Every required document must have a row marked present; a vehicle with no rows is MISSING, not OK.
  const mine = docs.filter(d => sameReg(d.registration, v.registration));
  const has = doc => mine.some(d => d.document.toLowerCase() === doc.toLowerCase() && PRESENT.includes(String(d.present).trim().toLowerCase()));
  const extra = mine.filter(d => !PRESENT.includes(String(d.present).trim().toLowerCase())).map(d => d.document);
  const missing = [...new Set([...cfg.requiredDocuments.filter(doc => !has(doc)), ...extra])];
  items.documents = missing.length ? { status: 'MISSING', due: null, daysLeft: null, detail: 'Missing: ' + missing.join(', '), source: 'Documents list' } : { status: 'OK', source: 'Documents list' };
  if (v.docusign_envelope_id) {
    if (!envelopes.ok) items.agreement = { status: 'CHECK_FAILED', detail: `DocuSign: ${envelopes.error}`, source: 'DocuSign' };
    else {
      const e = envelopes.body.envelopes.find(x => x.envelopeId === v.docusign_envelope_id);
      if (!e) items.agreement = { status: 'CHECK_FAILED', detail: 'Envelope not found in DocuSign response', source: 'DocuSign' };
      else if (e.status === 'completed') items.agreement = { status: 'OK', detail: 'Signed ' + (e.completedDateTime || '').slice(0, 10), source: 'DocuSign' };
      else if (['declined', 'voided'].includes(e.status)) items.agreement = { status: 'ACTION_REQUIRED', detail: `Agreement ${e.status}`, source: 'DocuSign' };
      else {
        const age = daysBetween(e.sentDateTime.slice(0, 10), today);
        items.agreement = { status: age >= cfg.pendingSignatureDays ? 'PENDING' : 'OK', detail: `Unsigned (${e.status}) for ${age} day(s)`, source: 'DocuSign' };
      }
    }
  }
  const sts = Object.values(items).map(i => i.status);
  const light = sts.some(s => RED.includes(s)) ? 'red' : sts.some(s => AMBER.includes(s)) ? 'amber' : 'green';
  const next = Object.entries(items).filter(([, i]) => i.due && i.daysLeft != null).sort((a, b) => a[1].daysLeft - b[1].daysLeft)[0];
  const actions = Object.entries(items).filter(([, i]) => i.status !== 'OK').map(([k, i]) => `${k}: ${i.status}${i.detail ? ' (' + i.detail + ')' : i.due ? ' (' + i.due + ')' : ''}`);
  return { registration: v.registration, make: v.make, model: v.model, light, items, next: next ? { check: next[0], due: next[1].due, daysLeft: next[1].daysLeft } : null, actions };
}

// Work out which messages to send today. state.sent holds keys already sent (dedupe across runs).
function planMessages(results, today, cfg, state, acks) {
  const out = [], sent = new Set(state.sent || []), urgentOn = { ...(state.urgentOn || {}) };
  // An acknowledgement counts only for the current occurrence: dated on/after the issue started and not in the future.
  const acked = (reg, check, since) => acks.some(a => sameReg(a.registration, reg) && a.check === check && isDate(a.acknowledged_on) && daysBetween(a.acknowledged_on, today) >= 0 && daysBetween(since, a.acknowledged_on) >= 0);
  const push = (key, m) => { if (!sent.has(key)) { sent.add(key); out.push({ key, ...m }); } };
  const live = new Set(); // urgent/action keys that are still true today
  for (const r of results) for (const [check, i] of Object.entries(r.items)) {
    const base = `${r.registration}|${check}|${i.due || ''}`;
    if (i.status === 'DUE_SOON') {
      const rung = cfg.ladder.filter(x => i.daysLeft <= x).sort((a, b) => a - b)[0];
      if (rung != null) push(`${base}|R${rung}`, { level: 'reminder', to: 'primary', registration: r.registration, check, text: `${r.registration}: ${check} due ${i.due} (${i.daysLeft} day(s))` });
    } else if (['OVERDUE', 'CHECK_FAILED', 'ACTION_REQUIRED'].includes(i.status)) {
      const k = `${base}|${i.status}`; live.add(k);
      const label = i.status === 'CHECK_FAILED' ? 'CHECK FAILED' : i.status === 'OVERDUE' ? 'OVERDUE' : 'ACTION REQUIRED';
      push(k, { level: 'urgent', to: 'primary', registration: r.registration, check, text: `URGENT ${r.registration}: ${check} ${label}${i.detail ? ' - ' + i.detail : ''}` });
      if (!urgentOn[k]) urgentOn[k] = today;
      if (!acked(r.registration, check, urgentOn[k]) && daysBetween(urgentOn[k], today) >= cfg.escalateAfterDays)
        push(`${k}|ESC`, { level: 'escalation', to: 'escalation', registration: r.registration, check, text: `ESCALATION ${r.registration}: ${check} ${label} unresolved since ${urgentOn[k]} and not acknowledged` });
    } else if (['UNVERIFIED', 'MISSING', 'PENDING', 'ATTENTION'].includes(i.status)) {
      live.add(`${base}|${i.status}`);
      push(`${base}|${i.status}`, { level: 'action', to: 'primary', registration: r.registration, check, text: `${r.registration}: ${check} ${i.status}${i.detail ? ' - ' + i.detail : ''}` });
    }
  }
  // An issue that has cleared is forgotten, so if it comes back (e.g. a lookup fails again next month) it alerts
  // and escalates afresh instead of being treated as already sent. Reminder keys (|R<n>) are kept: they carry the due date.
  for (const key of [...sent]) { const base = key.replace(/\|ESC$/, ''); if (!/\|R\d+$/.test(key) && !live.has(base)) sent.delete(key); }
  for (const k of Object.keys(urgentOn)) if (!live.has(k)) delete urgentOn[k];
  return { messages: out, state: { sent: [...sent], urgentOn } };
}

module.exports = { CONFIG_DEFAULTS, canonReg, evaluateVehicle, planMessages, daysBetween, isDate, RED, AMBER };
