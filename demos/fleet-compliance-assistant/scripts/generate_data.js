// Writes the synthetic register, documents, envelopes, acks, API fixtures and the hand-written answer key.
// All data is fictional. Registrations use a "ZA" prefix (Z is not issued as a first letter in GB current-format plates).
'use strict';
const fs = require('fs'), path = require('path');
const ROOT = path.join(__dirname, '..');
const DAY0 = '2026-11-02';
const add = (d, n) => { const t = new Date(d + 'T00:00:00Z'); t.setUTCDate(t.getUTCDate() + n); return t.toISOString().slice(0, 10); };
const MAKES = [['FORD','TRANSIT CUSTOM'],['VAUXHALL','VIVARO'],['TOYOTA','COROLLA'],['VOLKSWAGEN','CRAFTER'],['KIA','NIRO']];

// Scenario table. Offsets are days from DAY0. Expected day-0 statuses are written by hand (not computed by the engine).
// cols: n, tax, mot, insExp, insVerifiedAgeDays (null = never), service, special, expected {tax, mot, insurance, service}
const S = [
 [1, 200,180,150,5,90,null,            'OK','OK','OK','OK'],
 [2, 25,200,150,5,90,null,             'DUE_SOON','OK','OK','OK'],
 [3, -3,200,150,5,90,'untaxed',        'OVERDUE','OK','OK','OK'],
 [4, 200,12,150,5,90,null,             'OK','DUE_SOON','OK','OK'],
 [5, 200,-5,150,5,90,'motexpired',     'OK','OVERDUE','OK','OK'],
 [6, 200,200,20,5,90,null,             'OK','OK','DUE_SOON','OK'],
 [7, 200,200,-2,5,90,null,             'OK','OK','OVERDUE','OK'],
 [8, 200,200,-10,40,90,null,           'OK','OK','OVERDUE','OK'],
 [9, 200,200,150,null,90,null,         'OK','OK','UNVERIFIED','OK'],
 [10,200,200,150,45,90,null,           'OK','OK','UNVERIFIED','OK'],
 [11,200,200,150,31,90,null,           'OK','OK','UNVERIFIED','OK'],
 [12,200,200,150,30,90,null,           'OK','OK','OK','OK'],
 [13,200,200,150,5,8,null,             'OK','OK','OK','DUE_SOON'],
 [14,200,200,150,5,-1,null,            'OK','OK','OK','OVERDUE'],
 [15,30,200,150,5,90,null,             'DUE_SOON','OK','OK','OK'],
 [16,31,200,150,5,90,null,             'OK','OK','OK','OK'],
 [17,0,200,150,5,90,null,              'DUE_SOON','OK','OK','OK'],
 [18,200,200,150,5,90,'notfound',      'CHECK_FAILED','CHECK_FAILED','OK','OK'],
 [19,200,200,150,5,90,'dvlatimeout',   'CHECK_FAILED','OK','OK','OK'],
 [20,200,200,150,5,90,'dvsa500',       'OK','CHECK_FAILED','OK','OK'],
 [21,-40,200,150,5,90,'sorn',          'ACTION_REQUIRED','OK','OK','OK'],
 [22,200,300,150,5,90,'newvehicle',    'OK','OK','OK','OK'],
 [23,200,60,150,5,90,'mismatch',       'OK','ATTENTION','OK','OK'],
 [24,200,40,150,5,90,'latestfailed',   'OK','ACTION_REQUIRED','OK','OK'],
 [25,200,200,1,5,90,null,              'OK','OK','DUE_SOON','OK'],
];
const reg = n => `ZA${String(n).padStart(2,'0')} ${String.fromCharCode(65+(n%26))}${String.fromCharCode(65+((n*7)%26))}K`;
const wjson = (p, o) => fs.writeFileSync(path.join(ROOT, p), JSON.stringify(o, null, 2) + '\n');
const csv = rows => rows.map(r => r.map(v => v == null ? '' : /[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g,'""')}"` : v).join(',')).join('\n') + '\n';

const reg_rows = [['registration','make','model','insurance_expiry','insurance_verified_on','insurance_verified_source','service_due','docusign_envelope_id','notes']];
const key = [['registration','tax','mot','insurance','service','docs','agreement']];
const docs = [['registration','document','present']];
const DOCS = ['V5C logbook','Insurance certificate','Hire agreement'];
const MISSING = { 3: 'Insurance certificate', 10: 'Hire agreement', 25: 'V5C logbook' };
const ENV = { 1: ['completed', -20], 2: ['completed', -9], 6: ['sent', -5], 13: ['delivered', -2] };
const envelopes = [];
for (const [n, tax, mot, ins, insAge, svc, sp, eTax, eMot, eIns, eSvc] of S) {
  const r = reg(n), vrm = r.replace(' ', ''), [make, model] = MAKES[n % 5];
  const envId = ENV[n] ? `0a1b2c3d-0000-4000-8000-0000000000${String(n).padStart(2,'0')}` : '';
  reg_rows.push([r, make, model, add(DAY0, ins), insAge == null ? '' : add(DAY0, -insAge), insAge == null ? '' : 'askMID manual check (staff)', add(DAY0, svc), envId, '']);
  for (const d of DOCS) docs.push([r, d, MISSING[n] === d ? 'no' : 'yes']);
  let agreement = 'NONE';
  if (ENV[n]) {
    const [st, sentAgo] = ENV[n];
    envelopes.push({ envelopeId: envId, status: st, emailSubject: `Hire agreement - ${r}`, sentDateTime: add(DAY0, sentAgo) + 'T09:12:44.0000000Z',
      statusChangedDateTime: add(DAY0, sentAgo + (st === 'completed' ? 1 : 0)) + 'T10:01:02.0000000Z', ...(st === 'completed' ? { completedDateTime: add(DAY0, sentAgo + 1) + 'T10:01:02.0000000Z' } : {}) });
    agreement = st === 'completed' ? 'SIGNED' : 'PENDING';
  }
  key.push([r, eTax, eMot, eIns, eSvc, MISSING[n] ? 'MISSING' : 'OK', agreement]);

  // DVLA Vehicle Enquiry Service response (documented schema: POST /vehicle-enquiry/v1/vehicles)
  let dvla;
  if (sp === 'notfound') dvla = { __http: 404, body: { errors: [{ status: '404', code: '404', title: 'Vehicle Not Found', detail: 'Record for vehicle not found' }] } };
  else if (sp === 'dvlatimeout') dvla = { __timeout: true };
  else {
    const motExp = sp === 'mismatch' ? add(DAY0, mot + 30) : add(DAY0, mot);
    dvla = { __http: 200, body: { registrationNumber: vrm, make, colour: 'WHITE', fuelType: 'DIESEL', yearOfManufacture: 2021, engineCapacity: 1995,
      taxStatus: sp === 'untaxed' ? 'Untaxed' : sp === 'sorn' ? 'SORN' : 'Taxed', ...(sp === 'sorn' ? {} : { taxDueDate: add(DAY0, tax) }),
      motStatus: sp === 'newvehicle' ? 'No details held by DVLA' : mot < 0 ? 'Not valid' : 'Valid', ...(sp === 'newvehicle' ? {} : { motExpiryDate: motExp }),
      co2Emissions: 199, markedForExport: false, typeApproval: 'N1', dateOfLastV5CIssued: '2025-03-14', monthOfFirstRegistration: '2021-03' } };
  }
  wjson(`fixtures/dvla/${vrm}.json`, dvla);

  // DVSA MOT History API response (documented schema: GET /v1/trade/vehicles/registration/{registration})
  let dvsa;
  if (sp === 'notfound') dvsa = { __http: 404, body: { errorCode: 'MOTH-NP-01', errorMessage: `No data found for the provided registration ${vrm}`, requestId: 'mock-req-18' } };
  else if (sp === 'dvsa500') dvsa = { __http: 500, body: { errorCode: 'MOTH-IS-01', errorMessage: 'Internal server error', requestId: 'mock-req-20' } };
  else if (sp === 'newvehicle') dvsa = { __http: 200, body: { registration: vrm, make, model, firstUsedDate: '2025-12-29', fuelType: 'Diesel', primaryColour: 'White', registrationDate: '2025-12-29', manufactureDate: '2025-12-29', motTestDueDate: add(DAY0, mot), hasOutstandingRecall: 'Unknown' } };
  else {
    const tests = [{ completedDate: add(DAY0, mot - 365) + 'T11:20:31.000Z', testResult: 'PASSED', expiryDate: add(DAY0, mot), odometerValue: '48211', odometerUnit: 'MI', odometerResultType: 'READ', motTestNumber: String(500000000000 + n), dataSource: 'DVSA', defects: [] }];
    if (sp === 'latestfailed') tests.unshift({ completedDate: add(DAY0, -3) + 'T09:02:10.000Z', testResult: 'FAILED', odometerValue: '61007', odometerUnit: 'MI', odometerResultType: 'READ', motTestNumber: String(600000000000 + n), dataSource: 'DVSA', defects: [{ text: 'Nearside Front Tyre tread depth below requirements of 1.6mm (5.2.3 (e))', type: 'DANGEROUS', dangerous: true }] });
    dvsa = { __http: 200, body: { registration: vrm, make, model, firstUsedDate: '2021-03-01', fuelType: 'Diesel', primaryColour: 'White', registrationDate: '2021-03-01', manufactureDate: '2021-03-01', engineSize: '1995', hasOutstandingRecall: 'No', motTests: tests } };
  }
  wjson(`fixtures/dvsa/${vrm}.json`, dvsa);
}
// DocuSign eSignature REST v2.1 listStatusChanges response
wjson('fixtures/docusign/envelopes.json', { __http: 200, body: { resultSetSize: String(envelopes.length), startPosition: '0', endPosition: String(envelopes.length - 1), totalSetSize: String(envelopes.length), envelopes } });
fs.writeFileSync(path.join(ROOT, 'data/register.csv'), csv(reg_rows));
fs.writeFileSync(path.join(ROOT, 'data/documents.csv'), csv(docs));
fs.writeFileSync(path.join(ROOT, 'data/answer_key_day0.csv'), csv(key));
// Acknowledgements: staff acknowledge every day-0 red issue on day 1 EXCEPT three (tax ZA03, mot ZA05, service ZA14) which must escalate.
const acks = [['registration','check','acknowledged_on','by_role']];
for (const r of key.slice(1)) for (const [i, c] of ['tax','mot','insurance','service'].entries()) {
  const st = r[i + 1];
  if (['OVERDUE','CHECK_FAILED','ACTION_REQUIRED'].includes(st) && !['ZA03:tax','ZA05:mot','ZA14:service'].includes(r[0].slice(0,4) + ':' + c)) acks.push([r[0], c, add(DAY0, 1), 'fleet_manager']);
}
fs.writeFileSync(path.join(ROOT, 'data/acknowledgements.csv'), csv(acks));
console.log(`wrote ${S.length} vehicles, ${envelopes.length} envelopes, ${acks.length - 1} acks`);
