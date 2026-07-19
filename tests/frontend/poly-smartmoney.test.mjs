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
