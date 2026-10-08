// 🔴 07.10.2026 (Übersicht-Check): „🐋 Poly Whale-Bets · Cleveland Guardians vs Chicago White Sox
// · MLB" — zweimal, $58,1K und $37,2K. US-Sport ist seit dem 27.09. auf Polymarket UND Stake
// gesperrt. Die Stake-Kachel hielt sich daran, die vier Poly-Kacheln nicht.
// Fehlerklasse: eine Sperre, die je Fläche nachgebaut wird — die vergessene zeigt das Gesperrte.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const MOD = new URL('../../main-dashboard.js', import.meta.url);

function load() {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="mainDashPanel"></div></body>',
    { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve(null) });
  w.eval(readFileSync(MOD, 'utf8'));
  // die eine Quelle aus poly-wallets.js
  w.PW_BLOCKED_BET_CATS = ['US-Sport', 'Kampfsport', 'Cricket'];
  w._pwSportCategory = (lg, sp) => sp || (/mlb|nba|nfl/i.test(String(lg)) ? 'US-Sport' : 'Fußball');
  w._pwEnsurePlaysData = (cb) => cb && cb();
  return w;
}
const cap = () => new Date().toISOString();

function seed(w) {
  w._pwOverNormTop = () => [
    { key: 'mlb-cle-cws-2026-10-07', league: 'MLB', sport: 'US-Sport', name: 'Guardians vs White Sox',
      fav: 'White Sox', favPct: 70, usd: 300000, ratio: 6.0 },
    { key: 'cs2-spi-m80-2026-10-07', league: 'CS2', sport: 'E-Sport', name: 'Spirit vs M80',
      fav: 'Spirit', favPct: 86, usd: 319000, ratio: 4.5 },
  ];
  w._mdState.data = {
    liga: null, mls: null, ligaStreaks: null, mlsStreaks: null, betfair: { matches: [] }, pulse: null,
    whales: {
      'mlb-cle-cws-2026-10-07': { league: 'MLB', sport: 'US-Sport', capturedAt: cap(), hoursToKickoff: 0.5,
                                  whales: [{ wallet: '0xA', side: 'Chicago White Sox', usd: 58100 }] },
      'cs2-spi-m80-2026-10-07': { league: 'CS2', sport: 'E-Sport', capturedAt: cap(), hoursToKickoff: 0.5,
                                  whales: [{ wallet: '0xB', side: 'Spirit', usd: 42900 }] },
    },
  };
}

test('Poly Whale-Bets: gesperrte Sportart raus, E-Sport bleibt', () => {
  const w = load(); seed(w);
  w._renderMainDash();
  const h = w.document.getElementById('mainDashPanel').innerHTML;
  const seg = (h.split('Poly Whale-Bets')[1] || '').split('md-cell-whale')[0];
  assert.ok(!/White Sox|mlb-cle-cws/.test(seg), 'MLB steht nicht in der Kachel');
  assert.match(seg, /Spirit/, 'E-Sport bleibt');
});

test('Volumen über Norm: gesperrte Sportart raus', () => {
  const w = load(); seed(w);
  w._renderMainDash();
  const h = w.document.getElementById('md-cell-whale').innerHTML;
  assert.ok(!/Guardians/.test(h), 'MLB steht nicht in Volumen über Norm');
  assert.match(h, /Spirit vs M80/);
});

test('die Liste kommt aus poly-wallets.js, nicht aus der Kopie', () => {
  const w = load(); seed(w);
  w.PW_BLOCKED_BET_CATS = ['E-Sport'];          // Lucas legt die Sperre um → die Kachel folgt
  w._renderMainDash();
  const h = w.document.getElementById('mainDashPanel').innerHTML;
  const seg = (h.split('Poly Whale-Bets')[1] || '').split('md-cell-whale')[0];
  assert.match(seg, /White Sox/);
  assert.ok(!/Spirit/.test(seg));
});

test('Live-Kacheln laufen durch dieselbe Sperre', () => {
  const src = readFileSync(MOD, 'utf8');
  assert.match(src, /_mdOhneGesperrte\(_pwLiveTopWhales\(/);
  assert.match(src, /_mdOhneGesperrte\(_pwLiveTopInflow\(/);
});
