// tests/frontend/betfair-terminal-check-27-09.test.mjs — Terminal-Check 27.09.2026.
//   1. Burgos v Eldense: LIVE + 🔇 gemutet + Konviktion 0 — und „½-Kelly €5". Kein Stake live/gemutet.
//   2. Live-Edge stand gruen (+2,0 %) — dort ist sie ein Zeitversatz, keine Kante.
//   3. „in 25:33" las sich wie eine Uhrzeit.
//   4. „🔇 kein Anker" auch dort, wo das Spiel mit 17 Buechern da war und nur Pinnacle fehlte.
//   5. „keine Card" in jeder Zeile — einmal oben reicht.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const ROOT = new URL('../../', import.meta.url);
const iso = (ms) => new Date(Date.now() + ms).toISOString();
const PINN = { home: 0.68, draw: 0.2, away: 0.12, fav: 'home' };   // fair 1.47 -> @1.58 = +7,4 %

function boot(games, track) {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="betfairRadarPanel"></div></body>', { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window; w._bfNoAutoRefresh = true;
  w.eval(readFileSync(new URL('betfair-radar.js', ROOT), 'utf8'));
  w._bfState.data = { matches: [] }; w._bfState.consensus = { games }; w._bfState.hist = {};
  w._bfState.track = track || { byLeagueMarket: {} }; w._bfState.loading = false; w._bfState.view = 'terminal';
  return w;
}
const g = (o) => Object.assign({ matchId: 'X', home: 'Alpha', away: 'Beta', league: 'L', live: false,
  kickoff: iso(3 * 3600e3), moneySide: 'home', moneyName: 'Alpha', moneyOdd: 1.58, moneyDir: 'in',
  totVol: 50000, pinn: PINN, verdict: 'konsens' }, o);
const row = (html, name) => { const i = html.indexOf('<b>' + name + '</b>'); const a = html.lastIndexOf('<tr', i); return html.slice(a, html.indexOf('</tr>', i)); };
const stakeCol = (r) => { const tds = r.split('<td'); return tds[tds.length - 1]; };

test('1. Gegenbeweis zuerst: vor Anpfiff, nicht gemutet, positive Edge -> Stake', () => {
  const h = boot([g({})])._renderBetfairRadar();
  assert.match(stakeCol(row(h, 'Alpha')), /€\d/);
});

test('1. Live -> kein Stake (Zelle und Drilldown)', () => {
  const w = boot([g({ live: true, kickoff: iso(-40 * 60e3) })]);
  const h = w._renderBetfairRadar();
  assert.doesNotMatch(stakeCol(row(h, 'Alpha')), /€\d/);
  w._bfState.termOpen = 'X';
  assert.match(w._renderBetfairRadar(), /kein Stake[\s\S]{0,300}live — Anker und Quote aus verschiedenen Minuten/);
});

test('1. Gemutet (Bucket-Unterseite) -> kein Stake, auch bei positiver Edge', () => {
  const tr = { byLeagueMarket: { 'L|Match Odds': { n: 45, roi: -0.2, roiUg: -0.37, urteil: 'neutral', fade: true } } };
  const h = boot([g({})], tr)._renderBetfairRadar();
  assert.match(h, /🔇 Bucket-Unterseite/);
  assert.doesNotMatch(stakeCol(row(h, 'Alpha')), /€\d/);
});

test('2. Live-Edge grau mit „~", vor Anpfiff farbig', () => {
  const h = boot([g({ live: true, kickoff: iso(-40 * 60e3) })])._renderBetfairRadar();
  assert.match(row(h, 'Alpha'), /~\+7\.4%/);
  assert.doesNotMatch(boot([g({})])._renderBetfairRadar(), /~\+7\.4%/);
});

test('3. Anpfiff: „in 1h 33m" und ab einem Tag Wochentag + Uhrzeit', () => {
  assert.match(boot([g({ kickoff: iso(93 * 60e3 + 20e3) })])._renderBetfairRadar(), /in 1h 33m/);
  const h = boot([g({ kickoff: iso(25 * 3600e3) })])._renderBetfairRadar();
  assert.match(h, /(So|Mo|Di|Mi|Do|Fr|Sa) \d\d:\d\d/);
  assert.doesNotMatch(h, /in 25:/);
});

test('4. „Pinnacle fehlt (17 andere Bücher da)" statt pauschal „kein Anker"', () => {
  const h = boot([g({ pinn: null, ankerGrund: { grund: 'kein_pinnacle', nSoft: 17 } })])._renderBetfairRadar();
  assert.match(h, /Pinnacle fehlt \(17 andere Bücher da\)/);
  const h2 = boot([g({ pinn: null })])._renderBetfairRadar();
  assert.match(h2, /🔇 kein Anker/, 'ohne Diagnose bleibt der alte Text');
});

test('5. Ohne jede Card: Spalte weg, Hinweis einmal oben', () => {
  const h = boot([g({}), g({ matchId: 'Y', home: 'Gamma', moneyName: 'Gamma' })])._renderBetfairRadar();
  assert.doesNotMatch(h, />Unsere Card</);
  assert.equal((h.match(/keine Card/g) || []).length, 1);
});
