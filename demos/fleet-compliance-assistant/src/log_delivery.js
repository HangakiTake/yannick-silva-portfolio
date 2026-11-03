// Called by n8n after a batch of send attempts: appends delivery results to the audit log (no recipient address, no message body).
// Usage: node src/log_delivery.js <outDir> '<run_date>~<key>~<channel>~<SENT|FAILED|DRY_RUN>~<error>;;...'
'use strict';
const fs = require('fs'), path = require('path');
const { toCsv } = require('./io');
const [outDir, batch = ''] = process.argv.slice(2);
if (!outDir) { console.error("usage: log_delivery.js <outDir> '<run_date>~<key>~<channel>~<SENT|FAILED|DRY_RUN>~<error>;;...'"); process.exit(2); }
const H = ['logged_at', 'run_date', 'mode', 'registration', 'check', 'result', 'due', 'detail', 'source', 'message_key', 'channel', 'recipient_role'];
const now = new Date().toISOString();
const rows = batch.split(';;').filter(Boolean).map(r => { const [run_date, key = '', channel, res, error = ''] = r.split('~');
  const result = ['SENT', 'FAILED', 'DRY_RUN'].includes(res) ? res : 'UNKNOWN';
  return { logged_at: now, run_date, mode: process.env.FLEET_MODE || 'mock', registration: key.split('|')[0], check: key.split('|')[1], result: 'DELIVERY_' + result, detail: error.slice(0, 200), message_key: key, channel }; });
fs.appendFileSync(path.join(outDir, 'audit_log.csv'), toCsv(rows, H));
console.log(`logged ${rows.length} delivery results`);
