// Data sources behind one switch: FLEET_MODE=mock (recorded responses in fixtures/) or live (real APIs, keys from env).
// Message sending is NOT done here: the CLI only writes an outbox. Real sending happens in n8n (Twilio + email nodes)
// and only when SEND_ENABLED=yes. This file never sends WhatsApp, SMS or email.
'use strict';
const fs = require('fs'), path = require('path');
const FIX = path.join(__dirname, '..', 'fixtures');
const TIMEOUT_MS = 10000;
const vrm = r => String(r).toUpperCase().replace(/\s+/g, '');

function fromFixture(file) {
  if (!fs.existsSync(file)) return { ok: false, error: 'no recorded response for this registration' };
  const f = JSON.parse(fs.readFileSync(file, 'utf8'));
  if (f.__timeout) return { ok: false, error: `timeout after ${TIMEOUT_MS / 1000}s` };
  if (f.__http !== 200) return { ok: false, error: httpError(f.__http, f.body) };
  return { ok: true, body: f.body };
}
function httpError(code, body) {
  const e = body && ((body.errors && body.errors[0] && (body.errors[0].title + ': ' + body.errors[0].detail)) || body.errorMessage || body.message);
  return `HTTP ${code}${e ? ' ' + e : ''}`;
}
async function getJson(url, opts) {
  try {
    const res = await fetch(url, { ...opts, signal: AbortSignal.timeout(TIMEOUT_MS) });
    const body = await res.json().catch(() => null);
    return res.status === 200 ? { ok: true, body } : { ok: false, error: httpError(res.status, body) };
  } catch (e) { return { ok: false, error: e.name === 'TimeoutError' ? `timeout after ${TIMEOUT_MS / 1000}s` : 'network error: ' + e.message }; }
}
function need(env, names) {
  const miss = names.filter(n => !env[n]);
  if (miss.length) throw new Error('FLEET_MODE=live needs these environment variables: ' + miss.join(', '));
}

function makeAdapters(env = process.env) {
  const mode = env.FLEET_MODE || 'mock';
  if (mode === 'mock') return {
    mode,
    dvla: async r => fromFixture(path.join(FIX, 'dvla', vrm(r) + '.json')),
    dvsa: async r => fromFixture(path.join(FIX, 'dvsa', vrm(r) + '.json')),
    docusign: async () => fromFixture(path.join(FIX, 'docusign', 'envelopes.json')),
  };
  if (mode !== 'live') throw new Error(`FLEET_MODE must be "mock" or "live", got "${mode}"`);
  need(env, ['DVLA_API_KEY', 'DVSA_CLIENT_ID', 'DVSA_CLIENT_SECRET', 'DVSA_TENANT_ID', 'DVSA_API_KEY', 'DOCUSIGN_BASE_URI', 'DOCUSIGN_ACCOUNT_ID', 'DOCUSIGN_ACCESS_TOKEN']);
  let dvsaToken = null;
  async function token() {
    if (dvsaToken) return dvsaToken;
    const r = await getJson(`https://login.microsoftonline.com/${env.DVSA_TENANT_ID}/oauth2/v2.0/token`, { method: 'POST',
      headers: { 'content-type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ grant_type: 'client_credentials', client_id: env.DVSA_CLIENT_ID, client_secret: env.DVSA_CLIENT_SECRET, scope: env.DVSA_SCOPE || 'https://tapi.dvsa.gov.uk/.default' }) });
    if (!r.ok) return null;
    return (dvsaToken = r.body.access_token);
  }
  return {
    mode,
    dvla: r => getJson(env.DVLA_URL || 'https://driver-vehicle-licensing.api.gov.uk/vehicle-enquiry/v1/vehicles', {
      method: 'POST', headers: { 'x-api-key': env.DVLA_API_KEY, 'content-type': 'application/json' }, body: JSON.stringify({ registrationNumber: vrm(r) }) }),
    dvsa: async r => {
      const t = await token();
      if (!t) return { ok: false, error: 'DVSA token request failed (check client id/secret/tenant)' };
      return getJson(`https://history.mot.api.gov.uk/v1/trade/vehicles/registration/${encodeURIComponent(vrm(r))}`, { headers: { Authorization: 'Bearer ' + t, 'X-API-Key': env.DVSA_API_KEY } });
    },
    docusign: async (fromDate) => getJson(`${env.DOCUSIGN_BASE_URI}/restapi/v2.1/accounts/${env.DOCUSIGN_ACCOUNT_ID}/envelopes?from_date=${fromDate}`, { headers: { Authorization: 'Bearer ' + env.DOCUSIGN_ACCESS_TOKEN } }),
  };
}
module.exports = { makeAdapters, vrm };
