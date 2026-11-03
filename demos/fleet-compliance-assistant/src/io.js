'use strict';
const fs = require('fs');
// Minimal RFC 4180 CSV reader/writer (quoted fields, commas, newlines in quotes).
function parseCsv(text) {
  const rows = []; let row = [], f = '', q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) { if (c === '"') { if (text[i + 1] === '"') { f += '"'; i++; } else q = false; } else f += c; }
    else if (c === '"') q = true;
    else if (c === ',') { row.push(f); f = ''; }
    else if (c === '\n' || c === '\r') { if (c === '\r' && text[i + 1] === '\n') i++; row.push(f); rows.push(row); row = []; f = ''; }
    else f += c;
  }
  if (f !== '' || row.length) { row.push(f); rows.push(row); }
  const [h, ...rest] = rows.filter(r => r.some(x => x !== ''));
  return rest.map(r => Object.fromEntries(h.map((k, i) => [k.trim(), (r[i] ?? '').trim()])));
}
const readCsv = p => parseCsv(fs.readFileSync(p, 'utf8').replace(/^\uFEFF/, ''));
const esc = v => { v = v == null ? '' : String(v); if (/^[=+\-@\t\r]/.test(v)) v = "'" + v; return /[",\n\r]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v; };
const toCsv = (rows, header) => rows.map(r => header.map(h => esc(r[h])).join(',')).join('\n') + (rows.length ? '\n' : '');
module.exports = { parseCsv, readCsv, toCsv };
