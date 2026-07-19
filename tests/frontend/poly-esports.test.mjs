// tests/frontend/poly-esports.test.mjs
// 19.07.2026 — E-Sport als eigener Wallets-Menüpunkt neben MLS/Liga. „Poly-only" (kein scharfer
// Pinnacle-Anker) → KEIN Edge-vs-Pinnacle-Board, aber volle Smart-Money-/Whale-Sicht.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const PW = new URL('../../poly-wallets.js', import.meta.url);

const files = {
  'esports_poly_prices.json': { prices: { 'cs2-navi-faze': {
    homeName: 'NAVI', awayName: 'FaZe', hw: 0.58, aw: 0.42, vol: 50000, slug: 'cs2-navi-faze' } } },
  'esports_poly_wallets.json': { topPositionsAll: [{ wallet: '0xa', usd: 5000, side: 'home',
    pick: 'NAVI', key: 'cs2-navi-faze', match: 'NAVI – FaZe' }], updatedAt: new Date().toISOString() },
  'esports_poly_smartmoney.json': { matches: { 'cs2-navi-faze': {
    home: 'NAVI', away: 'FaZe', totalUsd: 50000, hoursToKickoff: 5, outcomes: {
      home: { usd: 30000, share: 0.6, topHolderShare: 0.55, holders: 40 },
      away: { usd: 20000, share: 0.4, topHolderShare: 0.80, holders: 30 } } } } },
};

function mockFetch() {
  return (url) => {
    const u = String(url); let b = null;
    for (const [f, d] of Object.entries(files)) if (u.includes(f)) { b = d; break; }
    return Promise.resolve({ ok: b != null, json: () => Promise.resolve(b) });
  };
}

async function renderEsports() {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="polyWalletsPanel"></div></body>',
    { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const { window: w } = dom;
  w.fetch = mockFetch();
  w.eval(readFileSync(PW, 'utf8'));
  w._pwSwitchDataset('esports');               // korrekt umschalten (setzt den Modul-State)
  await new Promise(r => setTimeout(r, 30));
  return w.document.getElementById('polyWalletsPanel').innerHTML;
}

test('E-Sport ist ein eigener Datensatz-Tab', () => {
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { runScripts: 'outside-only' });
  dom.window.eval(readFileSync(PW, 'utf8'));
  assert.match(dom.window._pwDatasetTabs(), /E-Sport/);
});

test('E-Sport rendert Smart-Money statt Pinnacle-Edge-Board', async () => {
  const html = await renderEsports();
  assert.match(html, /Smart-Money-Konzentration/, 'Smart-Money muss erscheinen');
  assert.match(html, /NAVI – FaZe/);
  assert.doesNotMatch(html, /⚡ Edge-Board/, 'ohne scharfen Anker KEIN Pinnacle-Edge-Board');
  assert.match(html, /keine Edge-vs-Pinnacle-Ansicht/, 'Erklärung fehlt, warum kein Edge-Board');
});

test('E-Sport: hohe Whale-Konzentration wird markiert (80%)', async () => {
  const html = await renderEsports();
  assert.match(html, /⚠️ 80%/);
});
