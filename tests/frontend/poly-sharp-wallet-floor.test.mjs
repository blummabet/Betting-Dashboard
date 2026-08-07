// tests/frontend/poly-sharp-wallet-floor.test.mjs — 07.08.2026 (Lucas: „diese Wetten mit 2-6 Dollar
// was soll das … muss viel akkurater und schärfer sein"). Die „scharfe Wallet" darf nur zählen, wenn
// BEIDE Achsen stimmen (Treffer>=50% UND CLV>=0 UND PnL>0) und genug Historie da ist. Prüft das
// geteilte Prädikat _pwIsSharpScore anhand der zwei realen 10/10-FADE-Fehlfälle.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const PW = new URL('../../poly-wallets.js', import.meta.url);
function load() {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="polyWalletsPanel"></div></body>',
    { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const { window } = dom;
  window.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  window.eval(readFileSync(PW, 'utf8'));
  return window;
}

test('Hook _pwIsSharpScore ist da', () => {
  assert.equal(typeof load()._pwIsSharpScore, 'function');
});
test('BASEMENT-Fall: 30% Treffer raus (auch mit +CLV)', () => {
  assert.equal(load()._pwIsSharpScore({ n: 10, hit: 0.3, avgClv: 0.8, pnl: 0 }), false);
});
test('Giant-Pandas-Fall: negativer CLV raus (auch mit 58% Treffer + PnL)', () => {
  assert.equal(load()._pwIsSharpScore({ n: 12, hit: 0.58, avgClv: -2.38, pnl: 15798 }), false);
});
test('echte Sharp-Wallet zählt (Team WE 83% · +CLV · +PnL)', () => {
  assert.equal(load()._pwIsSharpScore({ n: 23, hit: 0.83, avgClv: 0.5, pnl: 34000 }), true);
});
test('zu wenig Historie raus (n<4)', () => {
  assert.equal(load()._pwIsSharpScore({ n: 3, hit: 0.9, avgClv: 1, pnl: 100 }), false);
});
test('PnL=0 reicht nicht (muss >0 sein)', () => {
  assert.equal(load()._pwIsSharpScore({ n: 8, hit: 0.7, avgClv: 0.5, pnl: 0 }), false);
});
test('genau an der Schwelle zählt (hit .5, clv 0, pnl 1)', () => {
  assert.equal(load()._pwIsSharpScore({ n: 4, hit: 0.5, avgClv: 0, pnl: 1 }), true);
});
