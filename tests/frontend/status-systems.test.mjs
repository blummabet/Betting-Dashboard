// tests/frontend/status-systems.test.mjs — neue Live-System-Views im Status-Tab (31.07.2026, Lucas).
// Überblick + Betfair + Polymarket rendern aus den echten Feed-Strukturen; Frische-Ampel stimmt.
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

test('Betfair-View: Health, Track-Record & Lernloop rendern (frisch = grün)', async () => {
  const w = load({
    'betfair_prices.json': { _meta: { generatedAt: now(), n: 150, live: 2 } },
    'betfair_track_record.json': { n: 210, byLeagueMarket: { 'a|Match Odds': { n: 25 }, 'b|BTTS': { n: 3 } }, byTeamMarket: { 't|Match Odds': { n: 1 } } },
    'liga_signal_weights.json': { betfair_money: { n_observations: 0, weight: 1 }, betfair_coherence: { n_observations: 0, weight: 1 } },
    'mls_signal_weights.json': { betfair_money: { n_observations: 0, weight: 1 }, betfair_coherence: { n_observations: 0, weight: 1 } },
    'signal_weights.json': { betfair_money: { n_observations: 0, weight: 1 }, betfair_coherence: { n_observations: 0, weight: 1 } },
  });
  await w._stRenderBetfairStatus();
  const h = w.document.getElementById('st_dynamic').innerHTML;
  assert.match(h, /Betfair-Radar frisch/, 'frischer Verdict');
  assert.match(h, /Spiele getrackt/); assert.match(h, />150</);
  assert.match(h, /Liga × Markt/); assert.match(h, /Team × Markt/);
  assert.match(h, /wartet auf resolved Picks/, 'Lernloop-Status (0 Beobachtungen)');
});

test('Betfair-View: veraltete Daten → roter „Mac-Runner"-Alarm', async () => {
  const w = load({ 'betfair_prices.json': { _meta: { generatedAt: hoursAgo(5), n: 40, live: 0 } } });
  await w._stRenderBetfairStatus();
  const h = w.document.getElementById('st_dynamic').innerHTML;
  assert.match(h, /Radar .*h alt/, 'Alter im Verdict');
  assert.match(h, /Mac-Runner/, 'Runner-Hinweis');
});

test('Polymarket-View: Health & Smart-Money-Zähler rendern', async () => {
  const w = load({
    'poly_money_broad.json': { generatedAt: now(), n: 138, byLeague: [1, 2, 3, 4, 5] },
    'poly_money_broad_close.json': { a: {}, b: {}, c: {} },
    'poly_cross_sport.json': { generatedAt: now(), discrepancies: [1, 2] },
    'poly_wallet_track.json': { updatedAt: now(), scores: { w1: {}, w2: {} }, open: [1] },
    'poly_trader_data.json': { candidates: [1, 2, 3] },
  });
  await w._stRenderPolyStatus();
  const h = w.document.getElementById('st_dynamic').innerHTML;
  assert.match(h, /Polymarket frisch/);
  assert.match(h, /Märkte \(Money\)/); assert.match(h, />138</);
  assert.match(h, /Cross-Sport-Edges/); assert.match(h, /Wallets bewertet/); assert.match(h, />2</);
});

test('Poly: 3h alt ist NIE roter Alarm (tagsüber sind Lücken by design)', async () => {
  const w = load({ 'poly_money_broad.json': { generatedAt: hoursAgo(3), n: 100, byLeague: [1] } });
  await w._stRenderPolyStatus();
  const h = w.document.getElementById('st_dynamic').innerHTML;
  assert.doesNotMatch(h, /Auch fürs MLS-Fenster zu alt/, '3h darf nicht rot sein');
});

test('Poly: 30h alt IST rot (auch fürs MLS-Fenster tot)', async () => {
  const w = load({ 'poly_money_broad.json': { generatedAt: hoursAgo(30), n: 100, byLeague: [1] } });
  await w._stRenderPolyStatus();
  const h = w.document.getElementById('st_dynamic').innerHTML;
  assert.match(h, /Auch fürs MLS-Fenster zu alt/, '30h → roter Alarm');
});

test('Überblick: alle Systeme + WM-Archiv-Karte + Feed-Frische', async () => {
  const w = load({
    'betfair_prices.json': { _meta: { generatedAt: now(), n: 150, live: 1 } },
    'poly_money_broad.json': { generatedAt: now(), n: 138, byLeague: [1] },
    'liga-data.json': { _meta: { dataUpdatedAt: hoursAgo(6) } },
    'mls-data.json': { _meta: { dataUpdatedAt: hoursAgo(6) } },
  });
  await w._stRenderOverview();
  const h = w.document.getElementById('st_dynamic').innerHTML;
  assert.match(h, /alle Live-Systeme/);
  for (const s of ['Betfair', 'Polymarket', 'Top-5', 'MLS']) assert.match(h, new RegExp(s));
  assert.match(h, /WM 2026/); assert.match(h, /Archiv/);
  assert.match(h, /Feed-Frische — alle Systeme/);
});

test('View-Switch blendet Legacy-Karten aus und zeigt st_dynamic', async () => {
  const w = load({ 'betfair_prices.json': { _meta: { generatedAt: now(), n: 5, live: 0 } } });
  const panel = w.document.getElementById('statusPanel');
  const legacy = w.document.createElement('div'); legacy.id = 'legacyCard'; panel.appendChild(legacy);
  w._stShowDynamic(true);
  assert.strictEqual(legacy.style.display, 'none', 'Legacy versteckt');
  assert.strictEqual(w.document.getElementById('st_dynamic').style.display, '', 'dynamic sichtbar');
  w._stShowDynamic(false);
  assert.strictEqual(legacy.style.display, '', 'Legacy zurück');
  assert.strictEqual(w.document.getElementById('st_dynamic').style.display, 'none', 'dynamic versteckt');
});
