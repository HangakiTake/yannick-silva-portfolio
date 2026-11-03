'use strict';
const h = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const COLS = ['tax', 'mot', 'insurance', 'service', 'documents', 'agreement'];
const cls = s => ['OVERDUE', 'CHECK_FAILED', 'ACTION_REQUIRED'].includes(s) ? 'r' : s === 'OK' ? 'g' : s ? 'a' : 'n';
const label = s => s === 'CHECK_FAILED' ? 'CHECK FAILED' : (s || 'n/a').replace('_', ' ');
function cell(i) {
  if (!i) return '<td class="n">n/a</td>';
  const sub = i.mid ? `<div class="sub">MID: ${h(i.mid)}</div>` : '';
  return `<td class="${cls(i.status)}" title="${h(i.detail || '')}"><b>${h(label(i.status))}</b>${i.due ? `<div class="sub">${h(i.due)}${i.daysLeft != null ? ` (${i.daysLeft}d)` : ''}</div>` : ''}${i.detail && i.status !== 'OK' ? `<div class="sub">${h(i.detail)}</div>` : ''}${sub}</td>`;
}
function renderDashboard(results, { today, mode }) {
  const order = { red: 0, amber: 1, green: 2 }, rs = results.slice().sort((a, b) => order[a.light] - order[b.light] || a.registration.localeCompare(b.registration));
  const n = l => results.filter(r => r.light === l).length;
  const failed = results.filter(r => Object.values(r.items).some(i => i.status === 'CHECK_FAILED'));
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Fleet compliance ${h(today)}</title><style>
body{font:13px system-ui,Arial,sans-serif;margin:16px;color:#1d1d1f}h1{font-size:20px;margin:0 0 4px}.meta{color:#555;margin-bottom:10px}
.k{display:inline-block;padding:6px 12px;border-radius:6px;margin-right:6px;font-weight:600}.kr{background:#fde2e1;color:#8a1c14}.ka{background:#fff1cc;color:#7a5200}.kg{background:#dff5e1;color:#185c25}
.banner{background:#8a1c14;color:#fff;padding:8px 12px;border-radius:6px;margin:10px 0;font-weight:600}
table{border-collapse:collapse;width:100%}th,td{border:1px solid #ddd;padding:5px 6px;vertical-align:top;text-align:left}th{background:#f3f3f3;position:sticky;top:0}
td.r{background:#fde2e1}td.a{background:#fff6dd}td.g{background:#eef9ef}td.n{color:#999}.sub{font-size:11px;color:#444}
.dot{display:inline-block;width:12px;height:12px;border-radius:50%;margin-right:6px;vertical-align:-1px}.dot.red{background:#d93025}.dot.amber{background:#f2a600}.dot.green{background:#1e8e3e}
.demo{background:#eef3ff;border:1px solid #c5d3f5;padding:6px 10px;border-radius:6px;margin-bottom:8px}ul{margin:0;padding-left:16px}</style></head><body>
<div class="demo">DEMO with synthetic vehicles. Data mode: <b>${h(mode)}</b>${mode === 'mock' ? ' (recorded API responses, not live DVLA/DVSA/DocuSign)' : ''}. Insurance is never auto-verified: MID status is "UNVERIFIED" unless a person recorded a manual check.</div>
<h1>Fleet compliance status</h1><div class="meta">Run date ${h(today)} &middot; ${results.length} vehicles</div>
<span class="k kr">${n('red')} need action now</span><span class="k ka">${n('amber')} due soon / check</span><span class="k kg">${n('green')} all clear</span>
${failed.length ? `<div class="banner">CHECK FAILED for ${failed.length} vehicle(s): ${failed.map(r => h(r.registration)).join(', ')}. Status for these checks is unknown, not OK.</div>` : ''}
<table><thead><tr><th>Vehicle</th>${COLS.map(c => `<th>${c === 'mot' ? 'MOT' : c[0].toUpperCase() + c.slice(1)}</th>`).join('')}<th>Next deadline</th><th>Open actions</th></tr></thead><tbody>
${rs.map(r => `<tr><td><span class="dot ${r.light}" aria-label="${r.light}"></span><b>${h(r.registration)}</b><div class="sub">${h(r.make)} ${h(r.model)}</div></td>${COLS.map(c => cell(r.items[c])).join('')}<td>${r.next ? `${h(r.next.check)}<div class="sub">${h(r.next.due)} (${r.next.daysLeft}d)</div>` : '-'}</td><td>${r.actions.length ? `<ul>${r.actions.map(x => `<li>${h(x)}</li>`).join('')}</ul>` : 'None'}</td></tr>`).join('\n')}
</tbody></table></body></html>`;
}
module.exports = { renderDashboard };
