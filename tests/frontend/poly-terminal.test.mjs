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
  assert.match(html, /🖥️ Terminal — Kanten/, 'Board-Kopf (Kanten-Linse) da');
  assert.match(html, /handelbare Kanten/, 'Kanten-Note vorhanden');
  assert.match(html, /💰 Geld/, 'Geld-Linse im Umschalter');
  assert.match(html, /📈 Bewegung/, 'Bewegung-Linse im Umschalter');
  assert.match(html, /ROI Public-Segment/, 'KPI-Label Public (nur Kanten-Linse)');
  assert.match(html, /\+2\.7%/, 'Public-ROI +2.7% aus agg');
  assert.match(html, /-7\.1%/, 'ganze-Shortlist-ROI -7.1% aus agg');
});

test('Terminal-Button steht im View-Umschalter', async () => {
  const html = await render({ 'poly_shortlist_track.json': AGG }, 'money');
  assert.match(html, /🖥️ Terminal/, 'Umschalter enthält Terminal-Button');
});

// 18.08.2026 (Lucas: „dass auch in Geld/Bewegung ein laufendes Spiel den frischen Live-Preis zeigt"):
// Geld-Linse muss fuer ein IN-PLAY-Spiel die frische Live-Poly (broadLiveNow) statt der eingefrorenen
// Close-Quote nehmen. Relative Zeitstempel, damit der Test nicht mit der Zeit „gone" wird.
test('Geld-Linse nimmt bei laufendem Spiel die frische Live-Poly statt der Close-Freeze', async () => {
  const iso = (minAgo) => new Date(Date.now() - minAgo * 60000).toISOString();
  const K = 'ucl-alpbet-live';
  const close = { [K]: { prices: { Alpha: 0.40, Beta: 0.60 }, shares: { Alpha: 40000, Beta: 60000 },
    league: 'UEFA Champions League', totalUsd: 200000, hoursToKickoff: -0.4, kickoff: iso(25), capturedAt: iso(23) } };
  const live = { [K]: { prices: { Alpha: 0.25, Beta: 0.75 }, shares: { Alpha: 25000, Beta: 75000 },
    league: 'UEFA Champions League', totalUsd: 260000, kickoff: iso(25), capturedAt: iso(6) } };
  const dom = new JSDOM('<!DOCTYPE html><body><div id="polyWalletsPanel"></div></body>',
    { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window;
  w.fetch = mockFetch({ 'mls-data.json': { groups: {} }, 'mls_poly_prices.json': { prices: {} },
    'mls_poly_wallets.json': { topPositionsAll: [], updatedAt: new Date().toISOString() }, 'mls-odds-history.json': {},
    'poly_shortlist_track.json': AGG, 'poly_money_broad_close.json': close, 'poly_money_broad_live.json': live });
  w.eval(readFileSync(PW, 'utf8'));
  w._pwDsId = 'mls'; w.initPolyWallets();
  await new Promise(r => setTimeout(r, 25));
  w._pwSetView('terminal'); w._pwTermSetLens('geld');
  const html = w.document.getElementById('polyWalletsPanel').innerHTML;
  assert.match(html, /\$260K/, 'frisches Live-Volumen ($260K) sichtbar');
  assert.ok(!/\$200K/.test(html), 'eingefrorenes Close-Volumen ($200K) NICHT');
  assert.match(html, /75¢/, 'Live-Preis 75¢ sichtbar');
  assert.ok(!/60¢/.test(html), 'Close-Preis 60¢ NICHT');
});
