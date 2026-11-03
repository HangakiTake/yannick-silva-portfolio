'use strict';
// Messy-input stress test (realism gate step 2). Each case mutates a copy of the demo data the way a real
// office spreadsheet goes wrong, runs one day, and records whether the problem is visible on the vehicle.
// Pass = the vehicle is not green and the problem is named; Fail = silent pass, dropped row, or crash.
const fs = require('fs'), os = require('os'), path = require('path');
const { runOnce } = require('../src/run');
const { makeAdapters } = require('../src/adapters');
const ROOT = path.join(__dirname, '..');
const lines = f => fs.readFileSync(path.join(ROOT, 'data', f), 'utf8').split('\n');
const cases = [
  ['UK-format date in register (01/04/2027)', d => d['register.csv'] = d['register.csv'].replace(/^(ZA01 BHK,[^,]*,[^,]*,)2027-04-01/m, '$101/04/2027'), r => r('ZA01 BHK', 'insurance')],
  ['Blank service date', d => d['register.csv'] = d['register.csv'].replace(/^(ZA02 COK(?:,[^,\n]*){5}),2027-01-31/m, '$1,'), r => r('ZA02 COK', 'service')],
  ['Duplicate row, one written without the space (ZA04ECK)', d => d['register.csv'] += d['register.csv'].split('\n').find(l => l.startsWith('ZA04 ECK')).replace('ZA04 ECK', 'ZA04ECK') + '\n', r => r('ZA04 ECK', 'register') || r('ZA04ECK', 'register')],
  ['Lower-case, extra spaces in register (" za15  pbk")', d => d['register.csv'] = d['register.csv'].replace(/^ZA15 PBK/m, ' za15  pbk'), r => r('ZA15 PBK', 'tax', ['DUE_SOON'])],
  ['Missing document row typed lower-case without space (za03dvk)', d => d['documents.csv'] = d['documents.csv'].replace(/^ZA03 DVK,Insurance certificate/m, 'za03dvk,Insurance certificate'), r => r('ZA03 DVK', 'documents')],
  ['Vehicle with no document rows at all (ZA16)', d => d['documents.csv'] = d['documents.csv'].split('\n').filter(l => !l.startsWith('ZA16 QIK')).join('\n'), r => r('ZA16 QIK', 'documents')],
  ['Envelope ID not in DocuSign', d => d['register.csv'] = d['register.csv'].replace('0a1b2c3d-0000-4000-8000-000000000001', 'ffffffff-0000-4000-8000-00000000dead'), r => r('ZA01 BHK', 'agreement')],
  ['UTF-8 BOM + CRLF line endings (Excel export)', d => d['register.csv'] = '\uFEFF' + d['register.csv'].replace(/\n/g, '\r\n'), r => r('ZA05 FJK', 'mot', ['OVERDUE'])],
  ['Blank registration row', d => d['register.csv'] += ',FORD,TRANSIT,2027-04-01,2026-10-28,askMID manual check (staff),2027-01-31,,\n', r => r('', 'register') || r('', 'tax')],
  ['"present" typed as Y / TRUE', d => d['documents.csv'] = d['documents.csv'].replace(/^(ZA17 RPK,V5C logbook,)yes/m, '$1Y').replace(/^(ZA17 RPK,Hire agreement,)yes/m, '$1TRUE'), r => r('ZA17 RPK', 'documents', ['OK'])],
  ['Formula in a register cell (=HYPERLINK...)', d => d['register.csv'] = d['register.csv'].replace(/^(ZA19 TDK(?:,[^,\n]*){8}),$/m, '$1,=HYPERLINK("http://x")'), (r, out) => !/^=|,=/m.test(fs.readFileSync(path.join(out, 'audit_log.csv'), 'utf8'))],
];
(async () => {
  const rows = [];
  for (const [name, mutate, check] of cases) {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'stress-')), data = path.join(dir, 'data'), out = path.join(dir, 'out');
    fs.cpSync(path.join(ROOT, 'data'), data, { recursive: true });
    const d = {}; for (const f of ['register.csv', 'documents.csv']) d[f] = fs.readFileSync(path.join(data, f), 'utf8');
    mutate(d); for (const f in d) fs.writeFileSync(path.join(data, f), d[f]);
    let res, outcome;
    try {
      res = await runOnce({ today: '2026-11-02', dataDir: data, outDir: out, adapters: makeAdapters({ FLEET_MODE: 'mock' }) });
      const flagged = (reg, check, okStatuses = []) => { const v = res.results.find(x => x.registration === reg); if (!v) return false; const it = v.items[check] || v.items.run; return it ? (okStatuses.length ? okStatuses.includes(it.status) : it.status !== 'OK') : false; };
      outcome = check(flagged, out) ? 'PASS' : 'FAIL';
    } catch (e) { outcome = 'CRASH: ' + e.message; }
    rows.push(`| ${name} | ${outcome} |`);
  }
  const md = `| Messy input | Result |\n|---|---|\n${rows.join('\n')}\n`;
  fs.writeFileSync(path.join(__dirname, 'STRESS_RESULTS.md'), `# Stress test (run ${new Date().toISOString().slice(0, 16)}Z, day 2026-11-02, mock data)\n\n${md}`);
  console.log(md);
  process.exitCode = rows.some(r => !/\| PASS \|$/.test(r)) ? 1 : 0;
})();
