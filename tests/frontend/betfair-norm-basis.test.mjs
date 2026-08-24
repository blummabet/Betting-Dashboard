// tests/frontend/betfair-norm-basis.test.mjs — 24.08.2026 (Lucas: „bei Premier League und Serie A
// steht das ×N Norm immer noch so extrem").
//
// Der Regressionsfall: die Liga-Stufe vom 22.08. war da, lief aber ins Leere. Jede Stufe verlangt
// 4 Vergleichsspiele aus dem AKTUELLEN Schnappschuss — die hat eine Liga dort fast nie. Also fiel
// alles auf den globalen Pool durch (voll Mini-Ligen, Median ~€11K) und Fulham–Chelsea bekam ×82,
// obwohl es gemessen an echten EPL-Spielen bei ×0.6 liegt. Diese Tests halten fest: gelernte Basis
// zuerst, kein globaler Fallback, und ohne Basis gar kein Badge.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const RADAR = new URL('../../betfair-radar.js', import.meta.url);
const H = 3.6e6;

function mk(league, vol, kickInH = 1) {
  return {
    matchId: league + '-' + vol + '-' + kickInH, home: 'A', away: 'B', league,
    kickoff: new Date(Date.now() + kickInH * H).toISOString(), liveInfo: {},
    markets: { 'Match Odds': { runners: [{ name: 'A', odd: 2, vol }] } },
  };
}
function load(matches, lnorm) {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="betfairRadarPanel"></div></body>',
    { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const { window } = dom;
  window._bfNoAutoRefresh = true;
  window.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  window.eval(readFileSync(RADAR, 'utf8'));
  window._bfState.data = { matches };
  window._bfState.lnorm = lnorm || null;
  window._bfState._normBase = null;
  return window;
}
// Der Pool, der den Schaden anrichtete: viele kleine Ligen, eine grosse mit nur einem Spiel.
const EPL = mk('English Premier League', 900000);
const MINI = [];
for (let i = 0; i < 12; i++) MINI.push(mk('Slovenian U19', 10000 + i * 100));
const LEARNED = { byLeagueStage: { 'English Premier League|p1': { med: 1254554, n: 9 } } };

test('Hooks da', () => {
  const w = load([EPL], LEARNED);
  assert.equal(typeof w._bfNormBasis, 'function');
  assert.equal(typeof w._bfNormRatio, 'function');
});

test('Regression: EPL-Spiel wird NICHT mehr am Mini-Liga-Pool gemessen', () => {
  // Ohne gelernte Basis und ohne EPL-Peers gibt es schlicht keine Aussage — statt ×80.
  const w = load([EPL, ...MINI], null);
  assert.strictEqual(w._bfNormBasis(EPL), null, 'keine Basis fuer eine Liga mit einem Spiel');
  assert.strictEqual(w._bfNormRatio(EPL), null);
  assert.strictEqual(w._bfNormBadge(EPL), '', 'und damit auch kein Badge');
});

test('Gelernte Liga-Basis schlaegt alles andere und liefert die ehrliche Zahl', () => {
  const w = load([EPL, ...MINI], LEARNED);
  const b = w._bfNormBasis(EPL);
  assert.strictEqual(b.src, 'gelernt');
  assert.strictEqual(b.med, 1254554);
  assert.strictEqual(b.n, 9);
  const r = w._bfNormRatio(EPL);
  assert.ok(r > 0.6 && r < 0.8, 'unter der Liga-Norm statt ×80, ist: ' + r);
});

test('Phase zaehlt mit: dieselbe Liga, andere Phase = keine Basis', () => {
  // EPL-Live-Geld ist ein Vielfaches des Vor-Anpfiff-Geldes — l1 gegen p1 zu messen waere derselbe
  // Fehler eine Etage tiefer.
  const w = load([EPL], { byLeagueStage: { 'English Premier League|l2': { med: 5321657, n: 9 } } });
  assert.strictEqual(w._bfNormBasis(EPL), null);
});

test('Duenne gelernte Basis (n<4) zaehlt nicht', () => {
  const w = load([EPL], { byLeagueStage: { 'English Premier League|p1': { med: 1254554, n: 3 } } });
  assert.strictEqual(w._bfNormBasis(EPL), null);
});

test('Heutiger Schnappschuss bleibt Notnagel fuer Ligen ohne Historie', () => {
  const many = [];
  for (let i = 0; i < 6; i++) many.push(mk('Slovenian U19', 10000));
  const gross = mk('Slovenian U19', 40000);
  const w = load([gross, ...many], null);
  const b = w._bfNormBasis(gross);
  assert.strictEqual(b.src, 'heute');
  assert.strictEqual(w._bfNormRatio(gross), 4);
});

test('Kleckerspiele bekommen nie eine Basis', () => {
  const winzig = mk('English Premier League', 2000);
  const w = load([winzig], LEARNED);
  assert.strictEqual(w._bfNormBasis(winzig), null, 'unter NORM_MIN_EUR');
});

test('Badge nennt die Basis im Tooltip — und bleibt ohne Basis leer', () => {
  const gross = mk('English Premier League', 3000000);
  const w = load([gross], LEARNED);
  const html = w._bfNormBadge(gross);
  assert.match(html, /×2\.4 Norm/);
  assert.match(html, /gelernter Median dieser Liga in dieser Spielphase/);
  assert.match(html, /aus 9 Spielen/, 'Stichprobengroesse steht dran');
  assert.strictEqual(w._bfNormBadge(mk('Unbekannte Liga', 900000)), '', 'ohne Basis kein Badge');
});

test('Unter der Auffaellig-Schwelle kein Badge, obwohl Basis da ist', () => {
  const w = load([EPL], LEARNED);
  assert.strictEqual(w._bfNormBadge(EPL), '', '×0.7 ist normal, nicht auffaellig');
});

test('Ohne _bf.lnorm faellt nichts um', () => {
  const w = load([EPL], undefined);
  assert.doesNotThrow(() => w._bfNormBasis(EPL));
  assert.doesNotThrow(() => w._bfNormBadge(EPL));
});
