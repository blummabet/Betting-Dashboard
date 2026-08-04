// tests/frontend/main-dashboard-live-badge.test.mjs — 04.08.2026 (Lucas: „Übersicht zeigt kein
// Live-Badge"). isLive() las die Daten-Frische aus _bfState (Radar-Speicher), der auf der Übersicht
// leer ist → jedes Spiel galt als „stale → nicht live" → Badge feuerte nie. Fix: die Übersicht
// reicht ihre eigene _meta.generatedAt als Frische-Override an window._bfIsLive durch.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const RADAR = new URL('../../betfair-radar.js', import.meta.url);
const DASH  = new URL('../../main-dashboard.js', import.meta.url);

function boot() {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="mainDashPanel"></div></body>', { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window; w._bfNoAutoRefresh = true;
  w.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve(null) });
  w.eval(readFileSync(RADAR, 'utf8'));   // echtes window._bfIsLive + window._bfState
  w.eval(readFileSync(DASH, 'utf8'));
  return w;
}
function liveMatch() {
  const ko = new Date(Date.now() - 25 * 60e3).toISOString();   // Anpfiff vor 25 min
  return { matchId: 1, home: 'LiveHeim', away: 'LiveGast', country: 'ES', league: 'La Liga',
    kickoff: ko, liveInfo: { time: 25, finished: false },
    markets: { 'Match Odds': { runners: [{ name: 'LiveHeim', odd: 1.5, vol: 18000 }, { name: 'LiveGast', odd: 5.0, vol: 2000 }] } } };
}
function seed(w, gen) {
  w._mdState.data = { liga: null, mls: null, ligaStreaks: null, mlsStreaks: null,
    betfair: { _meta: { generatedAt: gen }, matches: [ liveMatch() ] },
    whales: null, bfOverview: { generatedAt: gen, steam: [], flow: [] } };
}

test('Übersicht: Live-Spiel bekommt ● LIVE — auch ohne geöffneten Radar-Tab (_bfState leer)', () => {
  const w = boot();
  assert.strictEqual(typeof w._bfIsLive, 'function', 'echtes _bfIsLive geladen');
  assert.ok(!(w._bfState && w._bfState.data), '_bfState.data leer (Bug-Zustand)');
  seed(w, new Date().toISOString());
  w._renderMainDash();
  const h = w.document.getElementById('mainDashPanel').innerHTML;
  assert.match(h, /LiveHeim/, 'Live-Spiel erscheint in einer Kachel');
  assert.match(h, /● LIVE/, 'und trägt das Live-Badge');
});

test('echtes isLive: ohne Override stale (Bug), mit Frische-Override live', () => {
  const w = boot();
  const m = liveMatch();
  assert.strictEqual(w._bfIsLive(m), false, 'ohne Override: Stale-Sperre greift');
  assert.strictEqual(w._bfIsLive(m, 5), true, 'mit Frische-Override: live');
});

test('wirklich alte Daten: auch mit Override kein Badge', () => {
  const w = boot();
  seed(w, new Date(Date.now() - 3 * 3600e3).toISOString());   // 3h > 75 min
  w._renderMainDash();
  const h = w.document.getElementById('mainDashPanel').innerHTML;
  assert.ok(!/● LIVE/.test(h), 'bei alten Daten bleibt das Badge aus');
});
