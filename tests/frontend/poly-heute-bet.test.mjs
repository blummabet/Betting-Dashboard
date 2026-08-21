// tests/frontend/poly-heute-bet.test.mjs
// 21.08.2026 (Lucas): „Heute"-Bet direkt auslösen wo möglich. Kernrisiko = die Seite↔Pick-Markt-
// Zuordnung (_heuteSideMatches) — falsches Mapping = falsche Geld-Wette. Diese Tests pinnen sie fest.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const VERDICT = new URL('../../pick-verdict.js', import.meta.url);
const POLY    = new URL('../../polymarket-tab.js', import.meta.url);

function loadPoly() {
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const { window } = dom;
  window.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  window.localStorage.clear();
  window.eval(readFileSync(VERDICT, 'utf8'));
  window.eval(readFileSync(POLY, 'utf8'));
  return window;
}

test('_heuteSideMatches: Heimsieg <-> Heim-Team', () => {
  const w = loadPoly();
  const p = { market:'Heimsieg', home:'Real Betis', away:'Real Sociedad' };
  assert.equal(w._heuteSideMatches('real betis', p), true);
  assert.equal(w._heuteSideMatches('betis', p), true);
  assert.equal(w._heuteSideMatches('real sociedad', p), false);
});

test('_heuteSideMatches: Auswaertssieg / Unentschieden', () => {
  const w = loadPoly();
  const p = { market:'Auswärtssieg', home:'Arsenal', away:'Coventry City' };
  assert.equal(w._heuteSideMatches('coventry city', p), true);
  assert.equal(w._heuteSideMatches('coventry', p), true);
  const d = { market:'Unentschieden', home:'A', away:'B' };
  assert.equal(w._heuteSideMatches('draw', d), true);
  assert.equal(w._heuteSideMatches('the draw', d), true);
  assert.equal(w._heuteSideMatches('arsenal', d), false);
});

test('_heuteSideMatches: Over/Under/BTTS', () => {
  const w = loadPoly();
  assert.equal(w._heuteSideMatches('over 2.5', { market:'Over 2.5 Tore', home:'A', away:'B' }), true);
  assert.equal(w._heuteSideMatches('under 2.5', { market:'Over 2.5 Tore', home:'A', away:'B' }), false);
  assert.equal(w._heuteSideMatches('under 2.5', { market:'Under 2.5 Tore', home:'A', away:'B' }), true);
  assert.equal(w._heuteSideMatches('yes', { market:'Beide Teams treffen', home:'A', away:'B' }), true);
});

test('_polyHeuteBetOrder: ohne geladenen Preis-Cache -> null (Link-Fallback)', () => {
  const w = loadPoly();
  const r = { key:'some-slug', side:'Real Betis', price:0.6, conv:8 };
  assert.equal(w._polyHeuteBetOrder(r, [{ home:'Real Betis', away:'Real Sociedad', market:'Heimsieg', odds:2.0 }]), null);
});

test('_polyHeuteBetOrder: keine Picks -> null', () => {
  const w = loadPoly();
  assert.equal(w._polyHeuteBetOrder({ key:'x', side:'y' }, []), null);
});
