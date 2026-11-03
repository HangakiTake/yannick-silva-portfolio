'use strict';
const test = require('node:test'), assert = require('node:assert');
const { evaluateVehicle, planMessages, CONFIG_DEFAULTS: cfg } = require('../src/engine');
const { parseCsv, toCsv } = require('../src/io');
const ok = body => ({ ok: true, body });
const base = { registration: 'ZA99 TST', make: 'X', model: 'Y', insurance_expiry: '2027-06-01', insurance_verified_on: '2026-11-01', insurance_verified_source: 'askMID', service_due: '2027-06-01', docusign_envelope_id: '' };
const dvla = (o = {}) => ok({ taxStatus: 'Taxed', taxDueDate: '2027-06-01', motStatus: 'Valid', motExpiryDate: '2027-06-01', ...o });
const dvsa = (tests) => ok({ motTests: tests || [{ completedDate: '2026-06-01T10:00:00.000Z', testResult: 'PASSED', expiryDate: '2027-06-01' }] });
const ev = (v = {}, c = {}) => evaluateVehicle({ ...base, ...v }, { today: '2026-11-02', cfg, dvla: dvla(), dvsa: dvsa(), docs: cfg.requiredDocuments.map(document => ({ registration: 'za99tst', document, present: 'yes' })), envelopes: ok({ envelopes: [] }), ...c });

test('due today is DUE_SOON, yesterday is OVERDUE, day 31 is OK', () => {
  assert.equal(ev({ service_due: '2026-11-02' }).items.service.status, 'DUE_SOON');
  assert.equal(ev({ service_due: '2026-11-01' }).items.service.status, 'OVERDUE');
  assert.equal(ev({ service_due: '2026-12-03' }).items.service.status, 'OK');
});
test('blank or UK-format date is CHECK_FAILED, never OK', () => {
  assert.equal(ev({ service_due: '' }).items.service.status, 'CHECK_FAILED');
  assert.equal(ev({ service_due: '01/12/2026' }).items.service.status, 'CHECK_FAILED');
});
test('insurance: verified-on in the future does not count as verified', () => {
  assert.equal(ev({ insurance_verified_on: '2026-12-01' }).items.insurance.status, 'UNVERIFIED');
});
test('MOT uses the latest PASS even when tests are unsorted; non-dangerous failure is ATTENTION', () => {
  const r = ev({}, { dvsa: dvsa([{ completedDate: '2025-01-01T00:00:00Z', testResult: 'PASSED', expiryDate: '2026-01-01' }, { completedDate: '2026-10-30T00:00:00Z', testResult: 'FAILED', defects: [{ type: 'MAJOR' }] }, { completedDate: '2026-06-01T00:00:00Z', testResult: 'PASSED', expiryDate: '2027-06-01' }]) });
  assert.equal(r.items.mot.due, '2027-06-01'); assert.equal(r.items.mot.status, 'ATTENTION');
});
test('DocuSign declined is ACTION_REQUIRED; unknown envelope is CHECK_FAILED', () => {
  const env = ok({ envelopes: [{ envelopeId: 'e1', status: 'declined', sentDateTime: '2026-10-01T00:00:00Z' }] });
  assert.equal(ev({ docusign_envelope_id: 'e1' }, { envelopes: env }).items.agreement.status, 'ACTION_REQUIRED');
  assert.equal(ev({ docusign_envelope_id: 'nope' }, { envelopes: env }).items.agreement.status, 'CHECK_FAILED');
});
test('ladder: first seen at 10 days sends the 14-day rung once, then 7 and 1; never twice', () => {
  let state = {}; const keys = [];
  for (const [today, due] of [['2026-11-02', '2026-11-12'], ['2026-11-03', '2026-11-12'], ['2026-11-05', '2026-11-12'], ['2026-11-11', '2026-11-12'], ['2026-11-11', '2026-11-12']]) {
    const r = evaluateVehicle({ ...base, service_due: due }, { today, cfg, dvla: dvla(), dvsa: dvsa(), docs: cfg.requiredDocuments.map(document => ({ registration: 'za99tst', document, present: 'yes' })), envelopes: ok({ envelopes: [] }) });
    const p = planMessages([r], today, cfg, state, []); state = p.state; keys.push(...p.messages.map(m => m.key.split('|').pop()));
  }
  assert.deepEqual(keys, ['R14', 'R7', 'R1']);
});
test('a moved deadline restarts the ladder', () => {
  let state = {};
  const run = (due) => { const r = ev({ service_due: due }); const p = planMessages([r], '2026-11-02', cfg, state, []); state = p.state; return p.messages.length; };
  assert.equal(run('2026-11-20'), 1); assert.equal(run('2026-11-20'), 0); assert.equal(run('2026-11-25'), 1);
});
test('CSV: quotes, commas and formula injection', () => {
  assert.deepEqual(parseCsv('a,b\n"x, y","He said ""hi"""\n'), [{ a: 'x, y', b: 'He said "hi"' }]);
  assert.equal(toCsv([{ a: '=HYPERLINK("x")' }], ['a']).trim(), `"'=HYPERLINK(""x"")"`);
});

test('documents: no rows = MISSING; reg matched ignoring case/spaces; Y counts as present', () => {
  assert.equal(ev({}, { docs: [] }).items.documents.status, 'MISSING');
  assert.equal(ev().items.documents.status, 'OK');
  const docs = cfg.requiredDocuments.map(document => ({ registration: 'ZA99 TST', document, present: 'Y' }));
  docs[0].present = 'no';
  assert.match(ev({}, { docs }).items.documents.detail, /V5C/);
});

test('acknowledgement from an earlier occurrence does not stop escalation', () => {
  const r = [ev({ service_due: '2026-10-20' })];
  const acks = [{ registration: 'ZA99 TST', check: 'service', acknowledged_on: '2026-01-05' }];
  const st = { urgentOn: { 'ZA99 TST|service|2026-10-20|OVERDUE': '2026-10-31' } };
  assert.ok(planMessages(r, '2026-11-02', cfg, st, acks).messages.some(m => m.level === 'escalation'));
  acks.push({ registration: 'ZA99 TST', check: 'service', acknowledged_on: '2026-11-01' });
  assert.ok(!planMessages(r, '2026-11-02', cfg, st, acks).messages.some(m => m.level === 'escalation'));
});
test('live DocuSign is asked for a year of changes, not just today', async () => {
  const fs = require('fs'), os = require('os'), path = require('path'); const { runOnce } = require('../src/run');
  let asked; const adapters = { mode: 'test', dvla: async () => dvla(), dvsa: async () => dvsa(), docusign: async f => { asked = f; return ok({ envelopes: [] }); } };
  await runOnce({ today: '2026-11-02', dataDir: path.join(__dirname, '../data'), outDir: fs.mkdtempSync(path.join(os.tmpdir(), 'u-')), adapters });
  assert.equal(asked, '2025-11-02');
});

test('an issue that clears and comes back alerts again', () => {
  const bad = [ev({ service_due: '' })], good = [ev()];
  let st = planMessages(bad, '2026-11-02', cfg, {}, []).state;
  st = planMessages(good, '2026-11-03', cfg, st, []).state;
  const again = planMessages(bad, '2026-12-01', cfg, st, []).messages;
  assert.deepEqual(again.map(m => m.level), ['urgent']);
});
