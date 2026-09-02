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
    '0xAAA': { n: 30, clvSumPP: 90, wins: 21, usd: 60000 },  // top (avg $2K/Wette)
    '0xBBB': { n: 15, clvSumPP: 30, wins: 9, usd: 30000 },   // mitte (avg $2K)
    '0xCCC': { n: 9,  clvSumPP: 84, wins: 5, usd: 18000 },  // n<12 → NICHT gelistet (der „−800K"-Fall)
    '0xDDD': { n: 12, clvSumPP: -24, wins: 3, usd: 24000 },  // negativ, unten (avg $2K)
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
    '0xP1': { n: 10, clvSumPP: 20, wins: 6, usd: 20000, pnl: 50000 },     // +50K → #1 (avg $2K)
    '0xP2': { n: 10, clvSumPP: 90, wins: 6, usd: 20000, pnl: -800000 },   // −800K → trotz Top-CLV UNTEN
    '0xP3': { n: 20, clvSumPP: 10, wins: 12, usd: 40000, pnl: 12000 },    // +12K → mitte (avg $2K)
    '0xP4': { n: 5,  clvSumPP: 40, wins: 4, usd: 10000, pnl: 99999 },     // n<8 → NICHT gelistet
  },
  open: {},
};

// 🔄 02.09.2026 — der Vertrag hat sich geaendert, und zwar gemessen. Sortiert wurde nach `pnl`;
// ueber die echten Daten trug das NULL Information ueber die Kante:
//     Median Ø-CLV der Top-20  0,59pp   ==   Median Ø-CLV aller 86 Qualifizierten  0,60pp
//     Korrelation P&L ~ Ø CLV  0,06     |    Korrelation P&L ~ Einsatzgroesse  0,04
// Der Grund: `pnl` ist die PLATTFORMWEITE Lebenszeit-Bilanz (Wahlen, Krypto), nicht unser Sport-
// Track. CLV dagegen persistiert (getrennte Fenster, r=0,78). Sortiert wird jetzt nach der
// CLV-UNTERGRENZE; die P&L bleibt als Kontext-Spalte stehen.
//
// ⚠️ Die Lehre vom 31.07.2026 (ein n=9-Wallet mit Traum-CLV stand auf #1 und war ein grosser
// Verlierer) bleibt gueltig — sie haengt aber am kleinen n, nicht an der P&L. Deshalb prueft der
// zweite Test unten, dass duenne Stichproben weiterhin draussen bleiben, solange nur der
// Schrumpf-Schaetzer verfuegbar ist.
test('rankt nach CLV-Untergrenze, nicht nach Vermoegen', async () => {
  const h = await renderWhales(PNL_TRACK);
  const rank = rankSlice(h);
  assert.match(rank, /CLV-UG/, 'die Untergrenze ist eine eigene Spalte');
  assert.match(rank, /Poly-P&/, 'die P&L bleibt als Kontext sichtbar');
  assert.match(rank, /CLV-Untergrenze/, 'das Label nennt das Rang-Kriterium');
  assert.doesNotMatch(rank, /sortiert nach <b>echter Poly-Gesamt-Bilanz/,
    'die alte Zusage darf nicht stehenbleiben');
  // Das −800K-Wallet taucht nicht mehr auf — nicht wegen seiner Bilanz, sondern weil es mit n=10
  // unter dem strengeren Gate liegt, solange die Streuung fehlt. Genau so soll es sein.
  assert.doesNotMatch(rank, /0xP2/, 'n=10 ohne gemessene Streuung ist noch kein Beleg');
});

test('eine duenne Stichprobe kommt nicht nach oben, auch mit Traum-CLV', async () => {
  // 0xP4: n=5, Ø CLV +8pp. Genau der Fall vom 31.07.2026. Ohne Streuung im Track greift das
  // strengere n-Gate (PW_RANK_MIN_N=12), damit Zufall nicht geadelt wird.
  const rank = rankSlice(await renderWhales(PNL_TRACK));
  assert.doesNotMatch(rank, /0xP4/, 'n=5 gehoert nicht in die Rangliste');
  assert.doesNotMatch(rank, /0xP2/, 'n=10 ohne gemessene Streuung ebenfalls nicht');
});

// ── 4-stellig-Einsatz-Filter (23.08.2026, Lucas: „hundert-Euro-Beträge interessieren nicht") ──
const SIZE_TRACK = {
  updatedAt: new Date().toISOString(),
  scores: {
    '0xBIG':   { n: 20, clvSumPP: 40, wins: 12, usd: 40000, pnl: 30000 },  // Ø $2K/Wette → bleibt
    '0xSMALL': { n: 20, clvSumPP: 40, wins: 12, usd: 6000,  pnl: 30000 },  // Ø $300/Wette → weg (Default)
  },
  open: {},
};

test('Einsatz-Filter: Default blendet <$1.000-Ø-Wallets aus, Toggle „alle" zeigt sie', async () => {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="polyWalletsPanel"></div></body>',
    { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const { window: w } = dom;
  w.fetch = mockFetch({
    'mls-data.json': { groups: {} }, 'mls_poly_prices.json': { prices: {} },
    'mls_poly_wallets.json': baseWallets, 'mls-odds-history.json': {},
    'poly_wallet_track.json': SIZE_TRACK,
  });
  w.eval(readFileSync(PW, 'utf8'));
  w._pwDsId = 'mls'; w.initPolyWallets();
  await new Promise(r => setTimeout(r, 30));
  w._pwSetSportFilter('all'); w._pwSetView('whales');
  let rank = rankSlice(w.document.getElementById('polyWalletsPanel').innerHTML);
  assert.match(rank, /0xBIG/, 'Ø $2K-Wallet bleibt');
  assert.doesNotMatch(rank, /0xSMALL/, 'Ø $300-Wallet ist per Default raus');
  // Toggle auf „alle"
  w._pwSetRankBigOnly(false);
  rank = rankSlice(w.document.getElementById('polyWalletsPanel').innerHTML);
  assert.match(rank, /0xSMALL/, 'nach Toggle „alle" wieder sichtbar');
});

test('leerer Track-Record → freundlicher Hinweis statt Crash', async () => {
  const h = await renderWhales({ updatedAt: new Date().toISOString(), scores: {}, open: {} });
  assert.match(h, /Schärfste Wallets/);
  assert.match(h, /Noch keine bewerteten Wallets/);
});
