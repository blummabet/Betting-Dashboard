// tests/frontend/poly-smartmoney.test.mjs
// 19.07.2026 — Dashboard-Ausbau: die bisher KOMPLETT ungenutzte {ds}_poly_smartmoney.json wird
// jetzt geladen und als „Smart-Money-Konzentration" gerendert (Geld-Split, Halter-Breite,
// Whale-Konzentration, Fluss) + Deep-Link auf Polymarket.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const PW = new URL('../../poly-wallets.js', import.meta.url);

function win() {
  const dom = new JSDOM('<!DOCTYPE html><body></body>',
    { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const { window: w } = dom;
  w.eval(readFileSync(PW, 'utf8'));
  return w;
}

const smart = { matches: { 'ESP-ARG': {
  home: 'Spanien', away: 'Argentinien', totalUsd: 1417268, hoursToKickoff: 12.6,
  outcomes: {
    home: { usd: 463608, share: 0.327, topHolderShare: 0.525, holders: 200, netFlowUsd: 17592 },
    draw: { usd: 183406, share: 0.129, topHolderShare: 0.78, holders: 200 },
    away: { usd: 770254, share: 0.543, topHolderShare: 0.771, holders: 200 } } } } };
const prices = { prices: { 'ESP-ARG': { slug: 'fifwc-esp-arg-2026-07-19' } } };

test('Smart-Money-Konzentration rendert Split, Halter, Konzentration', () => {
  const html = win()._pwSmartConcentration(smart, prices, {});
  assert.match(html, /Smart-Money-Konzentration/);
  assert.match(html, /Spanien – Argentinien/);
  assert.match(html, /Geld-Split/);
});

test('hohe Whale-Konzentration wird als weiches Signal markiert', () => {
  const html = win()._pwSmartConcentration(smart, prices, {});
  assert.match(html, /⚠️ 78%/, 'topHolderShare ≥ 70% muss als Warnung erscheinen');
});

test('Deep-Link auf den Polymarket-Markt (slug)', () => {
  const html = win()._pwSmartConcentration(smart, prices, {});
  assert.match(html, /polymarket\.com\/event\/fifwc-esp-arg-2026-07-19/);
});

test('leere/dünne Smart-Money-Daten → keine Sektion (kein leerer Kasten)', () => {
  const w = win();
  assert.equal(w._pwSmartConcentration(null, prices, {}), '');
  assert.equal(w._pwSmartConcentration({ matches: { X: { totalUsd: 100, outcomes: {} } } }, prices, {}), '');
});

test('Deep-Link-Helfer robust bei fehlendem slug', () => {
  assert.equal(win()._pwPolyLink(null), '');
});

// O/U-Leiter komplett (19.07.2026): poly_o15/o35 waren ungenutzt → jetzt im Edge-Board.
test('Edge-Board: O/U 1.5 + 2.5 + 3.5 mit Pinnacle-Fair (WM-Stil)', () => {
  const w = win();
  const prices = { prices: { 'H-A': { homeName: 'H', awayName: 'A', homeId: 'h', awayId: 'a',
    hw: 0.5, dr: 0.3, aw: 0.3, vol: 50000,
    poly_o15: 0.7, poly_u15: 0.3, poly_o25: 0.45, poly_u25: 0.55, poly_o35: 0.2, poly_u35: 0.8 } } };
  const odds = { 'H-A': { hw: 2.0, dr: 3.5, aw: 3.5,
    o15: 1.3, u15: 3.5, o25: 1.9, u25: 1.9, o35: 3.6, u35: 1.28 } };
  const mkts = new Set(w._pwBuildEdges(prices, odds).map(e => e.mkt));
  assert.ok(mkts.has('ou15') && mkts.has('ou') && mkts.has('ou35'), 'O/U-Leiter unvollständig');
});

test('Edge-Board: ohne Pinnacle-Totals fällt O/U auf Softbook zurück (ᴾ-Tag)', () => {
  const w = win();
  const prices = { prices: { 'H-A': { homeName: 'H', awayName: 'A', homeId: 'h', awayId: 'a',
    hw: 0.5, dr: 0.3, aw: 0.3, vol: 50000, poly_o25: 0.45, poly_u25: 0.55 } } };
  const odds = { 'H-A': { hw: 2.0, dr: 3.5, aw: 3.5, public_o25: 1.9, public_u25: 1.9 } };
  const ou = w._pwBuildEdges(prices, odds).find(e => e.mkt === 'ou' && e.side === 'over');
  assert.ok(ou && /ᴾ/.test(ou.ticket), 'Softbook-Fair muss als ᴾ markiert sein');
  assert.equal(ou.fairSrc, 'public');
});
