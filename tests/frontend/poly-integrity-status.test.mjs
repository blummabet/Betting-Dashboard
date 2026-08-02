// tests/frontend/poly-integrity-status.test.mjs — 02.08.2026 (Lucas' Skepsis: „wird noch mehr
// falsch sein, nur wir merkens nicht"). Die Poly-Seite bekam eine Ausgabe-Integritäts-Batterie
// (poly_data_integrity.py → poly_status.json). Dieser Test prüft, dass die Status-Seite sie unter
// „🐋 Polymarket" rendert: eigene Karte, 🔴/🟡/✅-Zeilen, Fehler zuerst, und dass ein stiller Bug
// (error-Check) die Kopf-Ampel ganz oben auf Rot zieht — nicht nur unten versteckt.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const SC = new URL('../../status-checks.js', import.meta.url);
function load(files) {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="statusPanel" style="display:block"></div></body>',
    { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window;
  w.fetch = (u) => {
    const f = String(u).split('?')[0];
    const body = Object.prototype.hasOwnProperty.call(files, f) ? files[f] : null;
    return Promise.resolve({ ok: body != null, json: () => Promise.resolve(body) });
  };
  w.eval(readFileSync(SC, 'utf8'));
  return w;
}
const now = () => new Date().toISOString();
const hoursAgo = (h) => new Date(Date.now() - h * 3600000).toISOString();

const STATUS_MIXED = {
  generatedAt: now(),
  nFail: 2,
  checks: [
    { id: 'close_feed_fresh', label: 'Close-Feed frisch', severity: 'error', ok: true, nFail: 0, failures: [], note: 'frisches Geld' },
    { id: 'shortlist_tracker_writes', label: 'Shortlist-Paper-Tracker schreibt', severity: 'error', ok: false, nFail: 1,
      failures: ['Tracker 4.6 h alt, Scan-Feed nur 1.6 h → Emitter liefert seit 2.9 h nichts (still tot?)'], note: 'Emitter kann still ausfallen.' },
    { id: 'proven_wallets_profitable', label: "'Bewiesene' Wallets wirklich profitabel", severity: 'warn', ok: false, nFail: 2,
      failures: ["18/48 'bewiesene' Wallets netto-NEGATIV (38%)", '   0x84cf… n=16 Treffer 62% P&L $-7,497,400'], note: 'Trefferquote trügt.' },
  ],
};

const FRESH_FEEDS = {
  'poly_money_broad.json': { generatedAt: now(), n: 138, byLeague: [1, 2, 3] },
  'poly_money_broad_close.json': { a: { capturedAt: now() } },
  'poly_cross_sport.json': { generatedAt: now(), discrepancies: [] },
  'poly_wallet_track.json': { updatedAt: now(), scores: { w1: {} }, open: [] },
  'poly_trader_data.json': { candidates: [] },
};

test('_stChecksHtml: leere Batterie → freundlicher „noch nicht erzeugt"-Hinweis', () => {
  const w = load({});
  assert.match(w._stChecksHtml([], 'poly_status.json noch nicht erzeugt'), /noch nicht erzeugt/);
  assert.match(w._stChecksHtml(null), /Noch keine Integritäts-Checks/);
});

test('_stChecksHtml: Fehler zuerst, Zeilen + Detail-Failures rendern', () => {
  const w = load({});
  const h = w._stChecksHtml(STATUS_MIXED.checks);
  // error-Check (nicht ok) muss vor dem ok-Check stehen
  assert.ok(h.indexOf('Shortlist-Paper-Tracker') < h.indexOf('Close-Feed frisch'), 'Fehler zuerst sortiert');
  assert.match(h, /still tot/, 'Failure-Text im Detail');
  assert.match(h, /🔴/); assert.match(h, /🟡/); assert.match(h, /🟢|sauber/);
  assert.match(h, /Details zeigen \(1\)/);
});

test('Poly-View: Integritäts-Karte wird gerendert', async () => {
  const w = load({ ...FRESH_FEEDS, 'poly_status.json': STATUS_MIXED });
  await w._stRenderPolyStatus();
  const h = w.document.getElementById('st_dynamic').innerHTML;
  assert.match(h, /Daten-Integrität/, 'eigene Integritäts-Karte');
  assert.match(h, /Shortlist-Paper-Tracker schreibt/);
  assert.match(h, /Integritäts-Report/, 'auch als Feed-Frische-Eintrag');
});

test('Poly-View: error-Check zieht die Kopf-Ampel auf Rot (stiller Bug ganz oben)', async () => {
  const w = load({ ...FRESH_FEEDS, 'poly_status.json': STATUS_MIXED });
  await w._stRenderPolyStatus();
  const h = w.document.getElementById('st_dynamic').innerHTML;
  assert.match(h, /Integritäts-Fehler/, 'Kopf-Banner meldet den Integritätsfehler');
  assert.doesNotMatch(h, /Polymarket frisch/, 'nicht mehr als „frisch" markiert trotz frischer Feeds');
});

test('Poly-View: nur Warnungen bei frischen Feeds → gelbe Ampel, kein Rot', async () => {
  const warnOnly = { generatedAt: now(), nFail: 1, checks: [
    { id: 'resolutions_match_open_keys', label: 'Auflösungen matchen unsere Keys', severity: 'warn', ok: false, nFail: 1,
      failures: ['ESPORTS: nur 93/222 aufgelöst (42%)'], note: 'Slug-Mismatch' },
  ] };
  const w = load({ ...FRESH_FEEDS, 'poly_status.json': warnOnly });
  await w._stRenderPolyStatus();
  const h = w.document.getElementById('st_dynamic').innerHTML;
  assert.match(h, /Integritäts-Warnung/, 'gelbe Kopf-Warnung');
  assert.doesNotMatch(h, /Integritäts-Fehler/, 'kein Rot bei reinen Warnungen');
});
