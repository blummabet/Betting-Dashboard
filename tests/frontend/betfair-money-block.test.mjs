// tests/frontend/betfair-money-block.test.mjs — 💷 Betfair-Geld-Verteilungsblock (wm2026-renderer.js).
// Prüft den Card-Block, der die GELD-VERTEILUNG aus dem betfair_money-Signal rendert: Haltung
// (stützt/warnt/dünn), Verteilungsbalken (Geld-Anteil vs. fairer Marker), €-Volumen, Track-Record.
// Nutzt den Test-Hook window.__wmCardTest.betfairMoneyBlock.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const WM_RENDERER = new URL('../../wm2026-renderer.js', import.meta.url);
function load() {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="intlCardsPanel"></div></body>', {
    url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true,
  });
  const { window } = dom;
  window.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  window.eval(readFileSync(WM_RENDERER, 'utf8'));
  return window.__wmCardTest;
}
const sig = (score, md) => ({ signals: [{ name: 'betfair_money', score, metadata: md }] });

test('Hook ist exportiert', () => {
  assert.equal(typeof load().betfairMoneyBlock, 'function');
});

test('stützt: Geld über fair, solider Track → grün + ✅ + €k + Verteilung', () => {
  const h = load().betfairMoneyBlock(sig(2.4, {
    market: 'Match Odds', token: 'H', money_share: 0.68, fair_share: 0.44,
    edge_pp: 24, total_eur: 31000, track_roi: 0.12, track_n: 23,
  }));
  assert.match(h, /Betfair-Geld stützt Heim/);
  assert.match(h, /68%/);                    // Geld-Anteil
  assert.match(h, /fair 44%/);               // fairer Anteil
  assert.match(h, /€31k/);                   // Volumen
  assert.match(h, /✅ Liga×Markt solide/);
  assert.match(h, /ROI \+12%/);
  assert.match(h, /n23/);
  assert.match(h, /cc-betfair/);             // eigene CSS-Identität
  assert.match(h, /cc-bf-fair/);             // fair-Marker vorhanden
  assert.match(h, /#3fb950/);                // grün
});

test('gefadet: Geld auf Pick, aber Track verliert → rot + ⚠️ fadet + „warnt trotz Geld"', () => {
  const h = load().betfairMoneyBlock(sig(-2.4, {
    market: 'Over/Under 2.5 Goals', token: 'OVER', money_share: 0.71, fair_share: 0.52,
    edge_pp: 19, total_eur: 18000, track_roi: -0.14, track_n: 19,
  }));
  assert.match(h, /warnt trotz Geld auf Über/);
  assert.match(h, /⚠️ Liga×Markt fadet/);
  assert.match(h, /ROI -14%/);
  assert.match(h, /#f85149/);                // rot
  assert.doesNotMatch(h, /stützt/);
});

test('dünn: weniger Geld als fair (Geld gegen Pick) → gelb, kein Track-Badge', () => {
  const h = load().betfairMoneyBlock(sig(-1.6, {
    market: 'Match Odds', token: 'A', money_share: 0.30, fair_share: 0.44, edge_pp: -14, total_eur: 12000,
  }));
  assert.match(h, /dünn auf Auswärts/);
  assert.match(h, /30%/);
  assert.match(h, /fair 44%/);
  assert.match(h, /#e3b341/);                // gelb
  assert.doesNotMatch(h, /Liga×Markt/);      // Track < n15 bzw. fehlt → kein Badge
});

test('Track unter n15 → kein Track-Badge (noch nicht belastbar)', () => {
  const h = load().betfairMoneyBlock(sig(2.0, {
    token: 'YES', money_share: 0.66, fair_share: 0.45, edge_pp: 21, total_eur: 9000,
    track_roi: 0.40, track_n: 8,
  }));
  assert.match(h, /BTTS Ja/);
  assert.doesNotMatch(h, /Liga×Markt/);
});

test('kein betfair_money-Signal → leerer String', () => {
  assert.equal(load().betfairMoneyBlock({ signals: [{ name: 'form_trend', score: 1 }] }), '');
});

test('betfair_money ohne metadata → leerer String (kein Fehlsignal)', () => {
  assert.equal(load().betfairMoneyBlock({ signals: [{ name: 'betfair_money', score: 1 }] }), '');
  assert.equal(load().betfairMoneyBlock({}), '');
  assert.equal(load().betfairMoneyBlock(null), '');
});

test('_SIG_META: Engine-Signal-Grid zeigt Betfair-Geld-Label', () => {
  const html = load().engineSignalGridHtml({
    signalAdjustmentPP: 2.4,
    signals: [{ name: 'betfair_money', score: 2.4, evidence: '💷 Betfair-Geld stützt Heim: 68% auf €31k' }],
  });
  assert.match(html, /Betfair-Geld/);
  assert.match(html, /💷/);
});
