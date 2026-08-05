// tests/frontend/poly-track-record.test.mjs — 02.08.2026 (Lucas): der neue Poly-Tab „📊 Track-Record"
// rendert das Paper-Track-Record der „Heute wetten"-Shortlist: KPIs (Alle + Public), Conviction-Tabelle,
// offene + abgerechnete Plays, ehrliche „sendet/setzt nichts"-Notiz. Reiner Render-Test (jsdom).
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const PW = new URL('../../poly-wallets.js', import.meta.url);

function boot(track) {
  const files = {
    'mls_poly_wallets.json': { topPositionsAll: [], matches: {}, updatedAt: new Date().toISOString() },
    'poly_shortlist_track.json': track,
  };
  const dom = new JSDOM('<!DOCTYPE html><body><div id="polyWalletsPanel"></div></body>',
    { url: 'https://x/', runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window;
  w.fetch = (u) => { u = String(u); let b = null; for (const [f, d] of Object.entries(files)) if (u.includes(f)) { b = d; break; } return Promise.resolve({ ok: b != null, json: () => Promise.resolve(b) }); };
  w.eval(readFileSync(PW, 'utf8'));
  return w;
}

const TRACK = {
  updatedAt: '2026-08-02T06:30:00Z', stake: 10,
  open: { 'k1|Team A': { key: 'k1', side: 'Team A', verdict: 'BET', conv: 9, league: 'MLB', entryPrice: 0.62, public: true } },
  settled: [
    { key: 'mlb-a-b', side: 'Team A', verdict: 'BET', conv: 9, league: 'MLB', entryPrice: 0.62, closePrice: 0.68, result: 'win', pnl: 6.13, clvPP: 6, stake: 10, public: true },
    { key: 'nba-c-d', side: 'Club Y', verdict: 'FADE', conv: 7, league: 'NBA', entryPrice: 0.40, closePrice: 0.35, result: 'loss', pnl: -10, clvPP: -5, stake: 10, public: false },
  ],
  agg: {
    all: { n: 2, wins: 1, hit: 0.5, pnl: -3.87, stake: 20, roi: -0.1935, clvAvg: 0.5 },
    public: { n: 1, wins: 1, hit: 1, pnl: 6.13, stake: 10, roi: 0.613, clvAvg: 6 },
    byConv: { '9': { n: 1, wins: 1, hit: 1, pnl: 6.13, stake: 10, roi: 0.613, clvAvg: 6 },
              '7': { n: 1, wins: 0, hit: 0, pnl: -10, stake: 10, roi: -1, clvAvg: -5 } },
    byVerdict: {},
    bySignal: { sharp: { n: 2, wins: 2, hit: 1, pnl: 12, stake: 20, roi: 0.6, clvAvg: 3 },
                steam: { n: 1, wins: 0, hit: 0, pnl: -10, stake: 10, roi: -1, clvAvg: -2 } },
  },
};

test('Track-Tab ist in der Reiterleiste', async () => {
  const w = boot(TRACK); w.initPolyWallets();
  await new Promise(r => setTimeout(r, 40));
  const html = w.document.getElementById('polyWalletsPanel').innerHTML;
  assert.match(html, /_pwSetView\('track'\)/);
  assert.match(html, /📊 Track-Record/);
});

test('Track-View rendert KPIs, Conviction-Tabelle, offene + abgerechnete Plays', async () => {
  const w = boot(TRACK); w.initPolyWallets();
  await new Promise(r => setTimeout(r, 40));
  w._pwSetView('track');
  const html = w.document.getElementById('polyWalletsPanel').innerHTML;
  assert.match(html, /Ganze Shortlist/);
  assert.match(html, /Public-Kandidaten/);
  assert.match(html, /Nach Conviction/);
  assert.match(html, /9\/10/); assert.match(html, /7\/10/);
  assert.match(html, /\+61\.3%/, 'Public-ROI dargestellt');           // public roi 0.613
  assert.match(html, /1 offene Plays|offene Plays/);
  assert.match(html, /Letzte abgerechnete/);
  assert.match(html, /Es wird nichts gesetzt/, 'ehrliche Paper-Notiz');
});

test('Leerer Track → freundlicher „sammelt noch"-Hinweis, kein Crash', async () => {
  const w = boot({ open: {}, settled: [], agg: { all: { n: 0 }, public: { n: 0 }, byConv: {} } });
  w.initPolyWallets();
  await new Promise(r => setTimeout(r, 40));
  w._pwSetView('track');
  const html = w.document.getElementById('polyWalletsPanel').innerHTML;
  assert.match(html, /Track-Record/);
  assert.match(html, /Noch keine Daten|sammelt/i);
});


test('Signal-Attribution: Tabelle je Ausloeser-Signal (Treffer/ROI/CLV)', async () => {
  const w = boot(TRACK); w.initPolyWallets();
  await new Promise(r => setTimeout(r, 40));
  w._pwSetView('track');
  const html = w.document.getElementById('polyWalletsPanel').innerHTML;
  assert.match(html, /Welches Signal trägt die Kante/);
  assert.match(html, /Scharfe Wallet/);
  assert.match(html, /Steam/);
  assert.match(html, /\+60%/, 'Sharp-ROI 0.6 dargestellt');
});
