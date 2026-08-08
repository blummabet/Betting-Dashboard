// tests/frontend/betfair-direction-badge.test.mjs — 08.08.2026 (Lucas: „Back oder Lay?").
// Richtungs-Badge im Radar aus betfair_direction.json: Quote kuerzer -> "Back ✓", driftet -> "driftet".
// Deckt ALLE Maerkte (auch Over/Under/BTTS/HZ, wo die alte 1X2-dirPill nicht greift) und live.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const RADAR = new URL('../../betfair-radar.js', import.meta.url);
function load(dir) {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="betfairRadarPanel"></div></body>',
    { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const { window } = dom;
  window._bfNoAutoRefresh = true;
  window.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  window.eval(readFileSync(RADAR, 'utf8'));
  window._bfState.dir = dir;   // Closure-State (window._bfState = _bf im Modul)
  return window;
}
const M = { matchId: 7, home: 'Atletico', away: 'Getafe' };
const runner = (name) => ({ name, odd: 1.9, vol: 1000 });

test('Hook da', () => { assert.equal(typeof load({})._bfDirBadge, 'function'); });

test('Quote kürzer (in) → Back ✓', () => {
  const w = load({ '7': { 'Over/Under 2.5 Goals': { 'Over 2.5 Goals': { dir: 'in', prev: 2.0, odd: 1.9 } } } });
  const html = w._bfDirBadge(M, 'Over/Under 2.5 Goals', runner('Over 2.5 Goals'));
  assert.match(html, /Back/);
  assert.match(html, /#3fb950/);   // grün
});

test('Quote driftet (out) → driftet, amber', () => {
  const w = load({ '7': { 'Over/Under 2.5 Goals': { 'Over 2.5 Goals': { dir: 'out', prev: 1.9, odd: 2.1 } } } });
  const html = w._bfDirBadge(M, 'Over/Under 2.5 Goals', runner('Over 2.5 Goals'));
  assert.match(html, /driftet/);
  assert.match(html, /#e3b341/);   // amber
});

test('flat oder unbekannt → kein Badge', () => {
  const w = load({ '7': { 'Over/Under 2.5 Goals': { 'Over 2.5 Goals': { dir: 'flat' } } } });
  assert.equal(w._bfDirBadge(M, 'Over/Under 2.5 Goals', runner('Over 2.5 Goals')), '');
  assert.equal(w._bfDirBadge(M, 'Over/Under 2.5 Goals', runner('Under 2.5 Goals')), '');   // kein Eintrag
  assert.equal(w._bfDirBadge(M, 'Over/Under 2.5 Goals', null), '');
});

test('ohne _bf.dir → kein Crash, kein Badge', () => {
  const w = load(undefined);
  assert.equal(w._bfDirBadge(M, 'Match Odds', runner('Atletico')), '');
});
