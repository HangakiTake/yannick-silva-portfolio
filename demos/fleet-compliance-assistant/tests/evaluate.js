// Runs the plan's acceptance tests (R1-R13) and writes tests/RESULTS.md. Real measured numbers only.
'use strict';
const fs = require('fs'), path = require('path'), os = require('os'), { execFileSync } = require('child_process');
const ROOT = path.join(__dirname, '..');
const { runOnce } = require('../src/run');
const { makeAdapters } = require('../src/adapters');
const { readCsv } = require('../src/io');
const { CONFIG_DEFAULTS, daysBetween } = require('../src/engine');
const DAY0 = '2026-11-02', DAYS = 40;
const add = (d, n) => { const t = new Date(d + 'T00:00:00Z'); t.setUTCDate(t.getUTCDate() + n); return t.toISOString().slice(0, 10); };
const rows = [];
const rec = (id, req, measured, threshold, pass, note = '') => rows.push({ id, req, measured, threshold, verdict: pass === null ? 'NOT RUN' : pass ? 'PASS' : 'MISSED', note });
const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), 'fleet-'));

(async () => {
  const adapters = makeAdapters({ FLEET_MODE: 'mock' });
  // ---------- 40-day simulation ----------
  const out = tmp(), days = [];
  for (let i = 0; i < DAYS; i++) days.push(await runOnce({ today: add(DAY0, i), dataDir: path.join(ROOT, 'data'), outDir: out, adapters, nowIso: add(DAY0, i) + 'T06:00:00Z' }));
  const d0 = days[0];

  // R1: day-0 statuses vs hand-written answer key
  const key = readCsv(path.join(ROOT, 'data/answer_key_day0.csv'));
  let ok = 0, tot = 0; const wrong = [];
  const map = { SIGNED: 'OK', NONE: undefined };
  for (const k of key) {
    const r = d0.results.find(x => x.registration === k.registration);
    for (const c of ['tax', 'mot', 'insurance', 'service', 'documents', 'agreement']) {
      const exp = c === 'agreement' ? (k.agreement in map ? map[k.agreement] : k.agreement) : k[c === 'documents' ? 'docs' : c];
      const got = r.items[c] && r.items[c].status;
      tot++; if (got === exp) ok++; else wrong.push(`${k.registration} ${c}: expected ${exp} got ${got}`);
    }
  }
  rec('R1', 'Track MOT, tax, insurance, service, documents, agreement per vehicle', `${ok}/${tot} statuses match the answer key (${(100 * ok / tot).toFixed(1)}%)`, '100%', ok === tot, wrong.join('; '));

  // R2: every lookup returns or is logged as failed; 0 silent passes
  let lookups = 0, failed = 0, silent = 0;
  for (const r of d0.results) for (const [c, src] of [['tax', 'dvla'], ['mot', 'dvsa']]) {
    lookups++; const res = await adapters[src](r.registration);
    if (!res.ok) { failed++; const logged = d0.audit.some(a => a.registration === r.registration && a.check === c && a.result === 'CHECK_FAILED'); if (r.items[c].status !== 'CHECK_FAILED' || !logged) silent++; }
  }
  rec('R2', 'Official tax and MOT status from DVLA/DVSA (recorded responses)', `${lookups} lookups, ${failed} failed, all ${failed} shown as CHECK FAILED and logged; ${silent} silent passes`, '0 silent passes', silent === 0, 'Run against recorded responses in the documented API formats, not the live APIs (no keys yet).');

  // R3: insurance unverified/expired
  const seeded = ['ZA07', 'ZA08', 'ZA09', 'ZA10', 'ZA11'];
  const flagged = seeded.filter(p => { const i = d0.results.find(r => r.registration.startsWith(p)).items.insurance; return ['UNVERIFIED', 'OVERDUE'].includes(i.status); });
  const neverVerified = d0.results.every(r => !/verified/i.test(r.items.insurance.mid) || /UNVERIFIED|Manually checked/.test(r.items.insurance.mid));
  const readme = fs.readFileSync(path.join(ROOT, 'README.md'), 'utf8');
  rec('R3', 'Insurance (MID) flagged when it cannot be verified automatically', `${flagged.length}/5 seeded cases flagged; system never labels insurance as auto-verified: ${neverVerified}; README limitation present: ${/askMID/.test(readme) && /MID/.test(readme)}`, '5/5 + README limitation', flagged.length === 5 && neverVerified && /askMID/.test(readme));

  // R4: reminder ladder, each rung exactly once, 0 duplicates over 40 days
  const all = days.flatMap(d => d.messages);
  const dup = all.length - new Set(all.map(m => m.key)).size;
  // Independent expectation: walk the calendar per dated item and list the rungs a person would expect.
  const expected = new Set();
  for (let i = 0; i < DAYS; i++) for (const r of days[i].results) for (const [c, it] of Object.entries(r.items)) {
    if (it.status !== 'DUE_SOON') continue;
    const left = daysBetween(add(DAY0, i), it.due);
    const rung = [1, 7, 14, 30].find(x => left <= x);
    expected.add(`${r.registration}|${c}|${it.due}|R${rung}`);
  }
  const sentR = new Set(all.filter(m => m.level === 'reminder').map(m => m.key));
  const missingR = [...expected].filter(k => !sentR.has(k)), extraR = [...sentR].filter(k => !expected.has(k));
  rec('R4', 'Advance reminders on a 30/14/7/1-day ladder (40 simulated days)', `${sentR.size} reminders sent, ${expected.size} expected; ${missingR.length} missing, ${extraR.length} unexpected, ${dup} duplicates`, 'each rung once, 0 duplicates', missingR.length === 0 && extraR.length === 0 && dup === 0, [...missingR, ...extraR].slice(0, 5).join('; '));

  // R5: escalation for exactly the 3 unacknowledged issues, after 2 days, to the escalation contact; still open at day 39
  const esc = all.filter(m => m.level === 'escalation');
  const escDays = days.map((d, i) => d.messages.filter(m => m.level === 'escalation').map(m => `${m.registration.slice(0, 4)}:${m.check}@${i}`)).flat();
  // Day-0 issues: only the 3 seeded unacknowledged ones may escalate (all others were acknowledged on day 1).
  // Issues that first turn red later are never acknowledged in the simulation, so each must escalate exactly 2 days later.
  const firstRed = new Map();
  days.forEach((d, i) => d.results.forEach(r => Object.entries(r.items).forEach(([c, it]) => {
    const k = `${r.registration.slice(0, 4)}:${c}`;
    if (['OVERDUE', 'CHECK_FAILED', 'ACTION_REQUIRED'].includes(it.status) && !firstRed.has(k)) firstRed.set(k, i);
  })));
  const want = ['ZA03:tax@2', 'ZA05:mot@2', 'ZA14:service@2'];
  for (const [k, f] of firstRed) if (f > 0 && f + 2 < DAYS) want.push(`${k}@${f + 2}`);
  want.sort();
  const last = days[DAYS - 1].results, stillOpen = ['ZA03', 'ZA05', 'ZA14'].every(p => last.find(r => r.registration.startsWith(p)).light === 'red');
  const escToRole = esc.every(m => m.to === 'escalation');
  rec('R5', 'Urgent alerts escalate to a second contact if unacknowledged', `escalations: ${escDays.join(', ') || 'none'}; all to escalation contact: ${escToRole}; issues still open on day 39: ${stillOpen}`, 'day 0: exactly the 3 seeded unacknowledged issues; later issues: each once, 2 days after turning red; to escalation contact', JSON.stringify([...escDays].sort()) === JSON.stringify(want) && escToRole && stillOpen);

  // R6: both channels
  const outbox = fs.readFileSync(path.join(out, 'outbox.jsonl'), 'utf8').trim().split('\n').map(JSON.parse);
  const both = all.every(m => ['email', 'whatsapp'].every(ch => outbox.some(o => o.key === m.key && o.channel === ch)));
  rec('R6', 'Email + WhatsApp alerts delivered; failures logged', `${all.length} alerts queued, each on email and WhatsApp: ${both}. Live delivery NOT tested`, '100% delivered on both channels', null, 'No Twilio or mailbox set up and real sending is forbidden in this build. Queued-to-both-channels passes; delivery itself is untested.');

  // R7: DocuSign pending + missing docs
  const ag = Object.fromEntries(d0.results.filter(r => r.items.agreement).map(r => [r.registration.slice(0, 4), r.items.agreement.status]));
  const miss = d0.results.filter(r => r.items.documents.status === 'MISSING').map(r => r.registration.slice(0, 4)).sort();
  const r7 = ag.ZA06 === 'PENDING' && ag.ZA13 === 'PENDING' && ag.ZA01 === 'OK' && ag.ZA02 === 'OK' && JSON.stringify(miss) === '["ZA03","ZA10","ZA25"]';
  rec('R7', 'Unsigned DocuSign agreements and missing documents flagged', `pending flagged ${['ZA06', 'ZA13'].filter(p => ag[p] === 'PENDING').length}/2, signed cleared ${['ZA01', 'ZA02'].filter(p => ag[p] === 'OK').length}/2, missing docs flagged ${miss.length}/3 (${miss.join(', ')})`, '2/2, 2/2, 3/3', r7, 'Recorded DocuSign listStatusChanges response, not the sandbox (no account yet).');

  // R8: forced failures: unknown reg (404), timeout, server error (500), bad key (403 on everything), DocuSign down, broken register date
  const failOut = tmp();
  const badKey = { mode: 'mock', dvla: async () => ({ ok: false, error: 'HTTP 403 Forbidden: invalid API key' }), dvsa: async () => ({ ok: false, error: 'HTTP 401 Unauthorized' }), docusign: async () => ({ ok: false, error: 'HTTP 401 USER_AUTHENTICATION_FAILED' }) };
  const bk = await runOnce({ today: DAY0, dataDir: path.join(ROOT, 'data'), outDir: failOut, adapters: badKey });
  const html = fs.readFileSync(path.join(failOut, 'dashboard.html'), 'utf8');
  const bkAll = bk.results.every(r => r.items.tax.status === 'CHECK_FAILED' && r.items.mot.status === 'CHECK_FAILED' && (!r.items.agreement || r.items.agreement.status === 'CHECK_FAILED'));
  const bkAlerts = bk.results.every(r => bk.messages.some(m => m.registration === r.registration && /CHECK FAILED/.test(m.text)));
  const brokenDir = tmp(); for (const f of fs.readdirSync(path.join(ROOT, 'data'))) fs.copyFileSync(path.join(ROOT, 'data', f), path.join(brokenDir, f));
  const regTxt = fs.readFileSync(path.join(brokenDir, 'register.csv'), 'utf8').split('\n'); regTxt[1] = regTxt[1].replace(/2027-01-31/, '31/01/27'); fs.writeFileSync(path.join(brokenDir, 'register.csv'), regTxt.join('\n'));
  const br = await runOnce({ today: DAY0, dataDir: brokenDir, outDir: tmp(), adapters });
  const brokenFlagged = br.results[0].items.service.status === 'CHECK_FAILED' && br.messages.some(m => m.registration === br.results[0].registration && m.check === 'service' && /CHECK FAILED/.test(m.text));
  const d0Fails = ['ZA18:tax', 'ZA18:mot', 'ZA19:tax', 'ZA20:mot'].every(x => { const [p, c] = x.split(':'); return d0.messages.some(m => m.registration.startsWith(p) && m.check === c && /CHECK FAILED/.test(m.text)); });
  rec('R8', 'Failed checks clearly flagged, never hidden', `404/timeout/500 cases alerted in run 1: ${d0Fails}; bad keys: ${bk.results.length}/25 vehicles CHECK FAILED with alert: ${bkAll && bkAlerts}; dashboard banner: ${/CHECK FAILED for 25 vehicle/.test(html)}; bad date in register flagged: ${brokenFlagged}`, 'every failure shows CHECK FAILED + alert in the same run', d0Fails && bkAll && bkAlerts && /CHECK FAILED for 25 vehicle/.test(html) && brokenFlagged);

  // R9: audit log completeness
  const log = readCsv(path.join(out, 'audit_log.csv'));
  const expChecks = days.reduce((s, d) => s + d.results.reduce((a, r) => a + Object.keys(r.items).length, 0), 0);
  const logChecks = log.filter(l => !l.result.startsWith('MESSAGE_QUEUED')).length, logMsgs = log.filter(l => l.result.startsWith('MESSAGE_QUEUED')).length;
  rec('R9', 'Record of every check and reminder', `checks logged ${logChecks}/${expChecks}; messages logged ${logMsgs}/${outbox.length}`, '100% of both', logChecks === expChecks && logMsgs === outbox.length);

  // R10: dashboard (human test not run)
  rec('R10', 'Simple per-vehicle dashboard', 'Dashboard built (out/dashboard.html, docs/dashboard.png). Non-technical reviewer test NOT run', '5/5 questions correct in under 2 minutes', null, 'Needs a person. The 5 questions and answers are in docs/REVIEWER_QUESTIONS.md.');

  // R11: data protection
  const scanFiles = execFileSync('git', ['ls-files', '--others', '--cached', '--exclude-standard'], { cwd: ROOT, encoding: 'utf8' }).split('\n').filter(f => f && !f.startsWith('out/') && !f.endsWith('.png'));
  const secretRe = /(sk-[A-Za-z0-9]{20,}|AC[0-9a-f]{32}|SK[0-9a-f]{32}|eyJ[A-Za-z0-9_-]{20,}\.|-----BEGIN [A-Z ]*PRIVATE KEY|x-api-key"\s*:\s*"[A-Za-z0-9]{20,})/;
  const secretHits = scanFiles.filter(f => secretRe.test(fs.readFileSync(path.join(ROOT, f), 'utf8')));
  const piiRe = /@|\+?\d{10,}/;
  const piiMsgs = outbox.filter(o => piiRe.test(o.text)).length, piiLog = log.filter(l => piiRe.test(Object.values(l).join(' ').replace(/\d{4}-\d{2}-\d{2}T[\d:.]+Z/g, ''))).length;
  const wf = fs.readFileSync(path.join(ROOT, 'n8n/fleet-compliance.workflow.json'), 'utf8');
  rec('R11', 'Protect customer data', `secrets found in ${secretHits.length} of ${scanFiles.length} repo files (incl. n8n workflow JSON); messages with emails/phone numbers: ${piiMsgs}/${outbox.length}; audit rows with them: ${piiLog}/${log.length}; workflow JSON references credentials by name only: ${!/"password"|"apiKey"\s*:\s*"[^{=]/.test(wf)}`, '0 secrets, reg + task only in messages', secretHits.length === 0 && piiMsgs === 0 && piiLog === 0, 'Automated scan only; the review checklist in docs/HANDOVER.md still needs a human tick.');

  // R12: fresh-copy setup
  const fresh = tmp(); execFileSync('cp', ['-r', ...['src', 'data', 'fixtures', 'scripts', 'package.json'].map(x => path.join(ROOT, x)), fresh]);
  let r12 = false, r12msg = '';
  try { r12msg = execFileSync('npm', ['run', '--silent', 'demo', '--', '--today', DAY0], { cwd: fresh, encoding: 'utf8' }).trim(); r12 = /25 vehicles/.test(r12msg) && fs.existsSync(path.join(fresh, 'out/dashboard.html')); } catch (e) { r12msg = e.message; }
  const n8nRes = fs.existsSync(path.join(ROOT, 'tests/n8n_import_result.txt')) ? fs.readFileSync(path.join(ROOT, 'tests/n8n_import_result.txt'), 'utf8').trim() : 'n8n import not run';
  rec('R12', 'Someone else can set it up', `README quick start in a clean copy: ${r12 ? 'green run' : 'FAILED'} ("${r12msg}"); n8n: ${n8nRes.split('\n').filter(l => /^(import|execute)/.test(l)).join(' / ')}. Fresh human reader NOT tested`, 'a fresh reader gets a green run without help', null, 'Automated clean-copy run passes; the human part (Yannick following the README) is the real test.');

  // R13: cost sheet sources
  const cost = fs.readFileSync(path.join(ROOT, 'docs/RUNNING_COSTS.md'), 'utf8');
  const lines = cost.split('\n').filter(l => /^\| (?!Item|---)/.test(l));
  const cited = lines.filter(l => /https?:\/\//.test(l) && /2026-10-28/.test(l));
  rec('R13', 'Running cost stated honestly', `${cited.length}/${lines.length} cost lines cite a source page and date`, 'every line cites source + date', lines.length > 0 && cited.length === lines.length);

  const md = ['# Test results vs thresholds', '', `Generated by \`npm test\` on ${new Date().toISOString().slice(0, 10)}. Data: 25 synthetic vehicles, recorded API responses, simulated run dates ${DAY0} to ${add(DAY0, DAYS - 1)} (${DAYS} daily runs).`, '', '| # | Requirement | Measured | Threshold | Verdict | Note |', '|---|---|---|---|---|---|',
    ...rows.map(r => `| ${r.id} | ${r.req} | ${r.measured.replace(/\|/g, '/')} | ${r.threshold} | **${r.verdict}** | ${r.note.replace(/\|/g, '/')} |`), '',
    `Summary: ${rows.filter(r => r.verdict === 'PASS').length} pass, ${rows.filter(r => r.verdict === 'MISSED').length} missed, ${rows.filter(r => r.verdict === 'NOT RUN').length} not run (need live accounts or a person).`, ''];
  fs.writeFileSync(path.join(ROOT, 'tests/RESULTS.md'), md.join('\n'));
  for (const r of rows) console.log(`${r.id} ${r.verdict.padEnd(8)} ${r.measured}${r.note && r.verdict !== 'PASS' ? '  [' + r.note + ']' : ''}`);
  process.exitCode = rows.some(r => r.verdict === 'MISSED') ? 1 : 0;
})().catch(e => { console.error(e); process.exit(1); });
