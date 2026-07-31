// tests/frontend/poly-sharp-ranking.test.mjs — 🥇 Schärfste-Wallets-Rangliste (31.07.2026, Lucas).
// Zwei Modi: (A) echte Poly-P&L (scores[w].pnl) → nach Gewinn ranken; (B) Interim ohne P&L →
// CLV-Kombi-Score, hart gegated (n≥12) + klar als „kein Gewinn/Verlust" gelabelt. Grund: ein
// −800K-Wallet stand mit n=9 auf #1, weil CLV nur Timing auf wenigen getrackten Wetten misst.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const PW = new URL('../../poly-wallets.js', import.meta.url);
const baseWallets = { topPositionsAll: [{ wallet: '0xabc', usd: 5000, side: 'home', pick: 'Heim', key: 'H-A', match: 'H vs A' }], updatedAt: new Date().toISOString() };
function mockFetch(files) {
  return (url) => { const u = String(url); let body = null;
    for (const [frag, data] of Object.entries(files)) if (u.includes(frag)) { body = data; break; }
    return Promise.resolve({ ok: body != null, json: () => Promise.resolve(body) }); };
}
async function renderWhales(walletTrack) {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="polyWalletsPanel"></div></body>',
    { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const { window: w } = dom;
  w.fetch = mockFetch({
    'mls-data.json': { groups: {} }, 'mls_poly_prices.json': { prices: {} },
    'mls_poly_wallets.json': baseWallets, 'mls-odds-history.json': {},
    'poly_wallet_track.json': walletTrack,
  });
  w.eval(readFileSync(PW, 'utf8'));
  w._pwDsId = 'mls';
  w.initPolyWallets();
  await new Promise(r => setTimeout(r, 30));
  w._pwSetSportFilter('all');
  w._pwSetView('whales');
  return w.document.getElementById('polyWalletsPanel').innerHTML;
}
const rankSlice = h => h.split('Schärfste Wallets')[1].split('Größte Whales')[0];

// ── (B) Interim CLV-Modus ────────────────────────────────────────────────────
const CLV_TRACK = {
  updatedAt: new Date().toISOString(),
  scores: {
    '0xAAA': { n: 30, clvSumPP: 90, wins: 21, usd: 8000 },  // top
    '0xBBB': { n: 15, clvSumPP: 30, wins: 9, usd: 6000 },   // mitte
    '0xCCC': { n: 9,  clvSumPP: 84, wins: 5, usd: 15000 },  // n<12 → NICHT gelistet (der „−800K"-Fall)
    '0xDDD': { n: 12, clvSumPP: -24, wins: 3, usd: 4000 },  // negativ, unten
  },
  open: { '0xAAA|k1|Bayern Munich': { wallet: '0xAAA', key: 'k1', side: 'Bayern Munich', league: 'SOCCER', usd: 1200 } },
};

test('Interim (CLV): hart gegated ab n≥12, kleine-Stichprobe-Wallet fliegt raus', async () => {
  const h = await renderWhales(CLV_TRACK);
  const rank = rankSlice(h);
  assert.doesNotMatch(rank, /0xCCC/, 'n=9-Wallet (der Verlierer-Fall) ist NICHT gelistet');
  const iA = rank.indexOf('0xAAA'), iB = rank.indexOf('0xBBB'), iD = rank.indexOf('0xDDD');
  assert.ok(iA > -1 && iB > -1 && iD > -1 && iA < iB && iB < iD, 'Reihenfolge nach Score');
});

test('Interim (CLV): trägt den ehrlichen „kein Gewinn"-Warnhinweis', async () => {
  const h = await renderWhales(CLV_TRACK);
  const rank = rankSlice(h);
  assert.match(rank, /Vorläufig/, 'Warn-Label');
  assert.match(rank, /misst Timing \(CLV\), nicht Gewinn/, 'CLV≠Gewinn klargestellt');
  assert.match(rank, /tief im Minus/, 'warnt vor Verlierer-Wallets oben');
  assert.match(rank, /CLV-Score/, 'Spalte heißt CLV-Score, nicht „Score"');
});

// ── (A) Echte Poly-P&L-Modus ─────────────────────────────────────────────────
const PNL_TRACK = {
  updatedAt: new Date().toISOString(),
  scores: {
    '0xP1': { n: 10, clvSumPP: 20, wins: 6, usd: 9000, pnl: 50000 },     // +50K → #1
    '0xP2': { n: 10, clvSumPP: 90, wins: 6, usd: 9000, pnl: -800000 },   // −800K → trotz Top-CLV UNTEN
    '0xP3': { n: 20, clvSumPP: 10, wins: 12, usd: 5000, pnl: 12000 },    // +12K → mitte
    '0xP4': { n: 5,  clvSumPP: 40, wins: 4, usd: 3000, pnl: 99999 },     // n<8 → NICHT gelistet
  },
  open: {},
};

test('P&L-Modus: rankt nach echter Bilanz — −800K-Wallet trotz Top-CLV ganz unten', async () => {
  const h = await renderWhales(PNL_TRACK);
  const rank = rankSlice(h);
  assert.match(rank, /Poly-P&/, 'P&L-Spalte da');
  assert.match(rank, /echter Poly-Gesamt-Bilanz/, 'Label auf echte Bilanz');
  const i1 = rank.indexOf('0xP1'), i2 = rank.indexOf('0xP2'), i3 = rank.indexOf('0xP3');
  assert.ok(i1 < i3 && i3 < i2, 'Reihenfolge nach P&L: +50K > +12K > −800K');
  assert.match(rank, /−\$800K/, 'Verlust negativ dargestellt');
  assert.doesNotMatch(rank, /0xP4/, 'n<8 im P&L-Modus ausgeschlossen');
});

test('leerer Track-Record → freundlicher Hinweis statt Crash', async () => {
  const h = await renderWhales({ updatedAt: new Date().toISOString(), scores: {}, open: {} });
  assert.match(h, /Schärfste Wallets/);
  assert.match(h, /Noch keine bewerteten Wallets/);
});
