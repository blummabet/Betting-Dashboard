// tests/frontend/poly-sharp-ranking.test.mjs — 🥇 Schärfste-Wallets-Rangliste (31.07.2026, Lucas).
// Rankt bewertete Wallets nach Kombi-Score (CLV + Treffer, konfidenz-gewichtet), gated ab n≥5,
// zeigt die aktuelle Position. Beantwortet „wem folgen", nicht „wer setzt am meisten".
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

const TRACK = {
  updatedAt: new Date().toISOString(),
  scores: {
    '0xAAA': { n: 30, clvSumPP: 90, wins: 21, usd: 8000 },  // Ø CLV +3, 70% → Top
    '0xBBB': { n: 6, clvSumPP: 30, wins: 3, usd: 2000 },    // Ø CLV +5 aber n klein → geschrumpft
    '0xCCC': { n: 3, clvSumPP: 30, wins: 3, usd: 9000 },    // n<5 → NICHT gelistet
    '0xDDD': { n: 12, clvSumPP: -24, wins: 3, usd: 4000 },  // Ø CLV -2, 25% → negativ, unten
  },
  open: { '0xAAA|k1|Bayern Munich': { wallet: '0xAAA', key: 'k1', side: 'Bayern Munich', league: 'SOCCER', usd: 1200 } },
};

test('Rangliste: sortiert nach Kombi-Score, n<5 ausgeschlossen', async () => {
  const h = await renderWhales(TRACK);
  assert.match(h, /Schärfste Wallets — Rangliste/, 'Sektion da');
  assert.doesNotMatch(h, /0xCCC/, 'Wallet mit n<5 ist NICHT gelistet');
  const rank = h.split('Schärfste Wallets')[1].split('Größte Whales')[0];
  const iA = rank.indexOf('0xAAA'), iB = rank.indexOf('0xBBB'), iD = rank.indexOf('0xDDD');
  assert.ok(iA > -1 && iB > -1 && iD > -1, 'alle drei bewährten gelistet');
  assert.ok(iA < iB && iB < iD, 'Reihenfolge nach Score: AAA > BBB > DDD');
  assert.match(rank, /🥇/, 'Medaille für Platz 1');
});

test('Rangliste: zeigt die aktuelle Position („setzt gerade auf")', async () => {
  const h = await renderWhales(TRACK);
  const rank = h.split('Schärfste Wallets')[1].split('Größte Whales')[0];
  assert.match(rank, /setzt gerade auf/, 'Spalte da');
  assert.match(rank, /Bayern Munich/, 'aktuelle Position von 0xAAA');
  assert.match(rank, /keine offene Position/, 'Wallets ohne offene Position markiert');
});

test('Rangliste: leerer Track-Record → freundlicher Hinweis statt Crash', async () => {
  const h = await renderWhales({ updatedAt: new Date().toISOString(), scores: {}, open: {} });
  assert.match(h, /Schärfste Wallets/, 'Sektion da');
  assert.match(h, /Noch keine Wallet mit genug Historie/, 'Leer-Hinweis');
});
