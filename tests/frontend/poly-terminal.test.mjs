// tests/frontend/poly-terminal.test.mjs — 18.08.2026 (Lucas): 🖥️ Terminal-Reiter im Polymarket-Wallets-Tab.
// Prüft die Verdrahtung: Reiter rendert, KPI-Band liest aus poly_shortlist_track.agg (Public/All-ROI).
// Getrieben über initPolyWallets mit gemocktem fetch (wie poly-wallets-edge.test.mjs).
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const PW = new URL('../../poly-wallets.js', import.meta.url);

function mockFetch(files) {
  return (url) => {
    const u = String(url); let body = null;
    for (const [frag, data] of Object.entries(files)) { if (u.includes(frag)) { body = data; break; } }
    return Promise.resolve({ ok: body != null, json: () => Promise.resolve(body) });
  };
}
async function render(files, view) {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="polyWalletsPanel"></div></body>',
    { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const { window: w } = dom;
  w.fetch = mockFetch(Object.assign({
    'mls-data.json': { groups: {} }, 'mls_poly_prices.json': { prices: {} },
    'mls_poly_wallets.json': { topPositionsAll: [], updatedAt: new Date().toISOString() },
    'mls-odds-history.json': {},
  }, files));
  w.eval(readFileSync(PW, 'utf8'));
  w._pwDsId = 'mls';
  w.initPolyWallets();
  await new Promise(r => setTimeout(r, 20));
  w._pwSetView(view);
  return w.document.getElementById('polyWalletsPanel').innerHTML;
}

const AGG = { updatedAt: new Date().toISOString(), stake: 10, agg: {
  all:    { n: 403, wins: 220, hit: 0.546, roi: -0.071, clvAvg: -0.02, stake: 4030, pnl: -287 },
  public: { n: 119, wins: 82,  hit: 0.689, roi: 0.027,  clvAvg: 0.01,  stake: 1190, pnl: 32 },
  byConv: { '6': { n: 109, hit: 0.596, roi: 0.096, clvAvg: 0.02 },
            '5': { n: 62,  hit: 0.339, roi: -0.356, clvAvg: 0.02 } } } };

test('Terminal-Reiter rendert Board-Kopf + KPI-Band aus shortlist_track.agg', async () => {
  const html = await render({ 'poly_shortlist_track.json': AGG, 'poly_money_broad_live.json': {} }, 'terminal');
  assert.match(html, /Terminal — handelbare Kanten/, 'Board-Kopf da');
  assert.match(html, /ROI Public-Segment/, 'KPI-Label Public');
  assert.match(html, /\+2\.7%/, 'Public-ROI +2.7% aus agg');
  assert.match(html, /-7\.1%/, 'ganze-Shortlist-ROI -7.1% aus agg');
});

test('Terminal-Button steht im View-Umschalter', async () => {
  const html = await render({ 'poly_shortlist_track.json': AGG }, 'money');
  assert.match(html, /🖥️ Terminal/, 'Umschalter enthält Terminal-Button');
});
