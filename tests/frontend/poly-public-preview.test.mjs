// tests/frontend/poly-public-preview.test.mjs — 01.08.2026 (Lucas):
// (#69) Sharp-Signal nach Wallet-Qualität gewichten: bewiesene Wallet mit hoher Trefferquote +
//   positiver Lifetime-P&L hebt die Conviction; die „Warum"-Zeile zeigt den Record.
// (#70) Public-Kandidat „Top-Play" — hart gegatet (Conv≥9 + Wallet n≥8 & ≥55% + Geld-Mehrheit ≥60%).
// (#71) Public-Kandidat „Whale-Watch" — Public-Schwelle (untracked ≥$100K / tracked ≥$25K) auf open.
// Alle drei sind NUR Vorschau/Analyse — es wird nichts gesendet.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const PW = new URL('../../poly-wallets.js', import.meta.url);

function boot(files) {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="polyWalletsPanel"></div></body>',
    { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window;
  w.fetch = (url) => { const u = String(url); let b = null;
    for (const [f, d] of Object.entries(files)) if (u.includes(f)) { b = d; break; }
    return Promise.resolve({ ok: b != null, json: () => Promise.resolve(b) }); };
  w.eval(readFileSync(PW, 'utf8'));
  return w;
}

// broadLive-Markt (poly_money_broad_close.json): frischer Anpfiff, keine Resolution.
function market(league, shares, prices, totalUsd) {
  return { league, resolved: null, totalUsd, shares, prices,
    hoursToKickoff: 3, capturedAt: new Date().toISOString() };
}

const BROAD = {
  // MLB: 65% Geld auf Braves, Preis auch Braves-Favorit → BET Braves. Scharfe Wallet auf Braves.
  'mlb-braves-padres': market('MLB',
    { 'Atlanta Braves': 65000, 'San Diego Padres': 35000 },
    { 'Atlanta Braves': 0.62, 'San Diego Padres': 0.38 }, 100000),
  // NBA: nur Whale-Kandidat (untracked $120K), kein Shortlist-Signal nötig
  'nba-lakers-celtics': market('NBA',
    { 'Lakers': 55000, 'Celtics': 45000 },
    { 'Lakers': 0.55, 'Celtics': 0.45 }, 100000),
};

const TRACK = {
  updatedAt: new Date().toISOString(),
  scores: {
    // bewiesen scharf: n10, 70% Treffer, +CLV, +$150K lifetime
    '0xSHARP': { n: 10, clvSumPP: 20, wins: 7, usd: 40000, pnl: 150000 },
  },
  open: [
    { wallet: '0xSHARP', key: 'mlb-braves-padres', side: 'Atlanta Braves', league: 'MLB',
      usd: 40000, entryPrice: 0.55, lastPrice: 0.62 },
    // untracked Whale auf NBA: $120K, Preis 55¢ → Public-Whale-Kandidat
    { wallet: '0xWHALE', key: 'nba-lakers-celtics', side: 'Lakers', league: 'NBA',
      usd: 120000, entryPrice: 0.50, lastPrice: 0.55 },
    // untracked, aber unter Schwelle ($40K) → NICHT
    { wallet: '0xSMALL', key: 'nba-lakers-celtics', side: 'Celtics', league: 'NBA',
      usd: 40000, entryPrice: 0.45, lastPrice: 0.45 },
  ],
};

function withData(fn) {
  const w = boot({
    'mls-data.json': { groups: {} }, 'mls_poly_prices.json': { prices: {} },
    'mls_poly_wallets.json': { topPositionsAll: [], matches: {}, updatedAt: new Date().toISOString() },
    'poly_money_broad_close.json': BROAD,
    'poly_money_broad_history.json': {},
    'poly_money_broad.json': { n: 100, byLeague: [{ league: 'MLB', verdict: 'neutral' }] },
    'poly_wallet_track.json': TRACK,
    'poly_cross_sport.json': { discrepancies: [] },
  });
  // Lexischen _pwCache über den schlanken Loader füllen (wie die Übersicht-Box es tut).
  return new Promise((resolve) => { w._pwEnsurePlaysData(() => resolve(fn(w))); });
}

test('#69 Sharp-Qualität: bewiesene Wallet hebt Conviction + Warum zeigt Record', async () => {
  await withData((w) => {
    const info = w._pwSharpInfoForKey('mlb-braves-padres');
    assert.ok(info, 'Sharp-Info für den Key vorhanden');
    assert.strictEqual(info.side, 'Atlanta Braves');
    assert.strictEqual(info.n, 10);
    assert.strictEqual(info.wins, 7);
    assert.ok(Math.abs(info.hit - 0.7) < 1e-9, 'Trefferquote 70%');
    assert.ok(info.pnl > 0, 'positive Lifetime-P&L');

    const r = w._pwShortlistScore('mlb-braves-padres', BROAD['mlb-braves-padres']);
    assert.strictEqual(r.verdict, 'BET');
    assert.strictEqual(r.side, 'Atlanta Braves');
    // Geld 1 (65%) + Sharp 4 (Basis2,5 +0,5@≥60 +0,5@≥70 +0,5 P&L>0) → conv = round(4+5) = 9
    assert.ok(r.conv >= 9, 'Conviction ≥9 durch Qualitäts-Sharp, war: ' + r.conv);
    assert.ok(r.reasons.some(x => /scharfe Wallet \(7\/10, 70% · \+\$150K\)/.test(x)),
      'Warum zeigt den Wallet-Record: ' + JSON.stringify(r.reasons));
    assert.ok(r.sharp && r.sharp.n === 10, 'Sharp-Record am Play angehängt');
  });
});

test('#70 Public Top-Play: erfüllt harte Gates → Kandidat', async () => {
  await withData((w) => {
    const tops = w._pwPublicTopPlays();
    assert.ok(tops.length >= 1, 'mindestens ein Top-Play-Kandidat');
    const t = tops[0];
    assert.strictEqual(t.side, 'Atlanta Braves');
    assert.ok(t.conv >= 9 && t.moneyPct >= 0.60 && t.sharp.n >= 8 && t.sharp.hit >= 0.55,
      'alle Gates erfüllt');
  });
});

test('#70 Public Top-Play: schwache Wallet fällt raus', async () => {
  const track2 = JSON.parse(JSON.stringify(TRACK));
  track2.scores['0xSHARP'] = { n: 5, clvSumPP: 5, wins: 2, usd: 40000, pnl: -10000 }; // n<8, hit40%, P&L neg
  const w = boot({
    'mls-data.json': { groups: {} }, 'mls_poly_prices.json': { prices: {} },
    'mls_poly_wallets.json': { topPositionsAll: [], matches: {}, updatedAt: new Date().toISOString() },
    'poly_money_broad_close.json': BROAD, 'poly_money_broad_history.json': {},
    'poly_money_broad.json': { n: 100, byLeague: [] },
    'poly_wallet_track.json': track2, 'poly_cross_sport.json': { discrepancies: [] },
  });
  await new Promise((res) => w._pwEnsurePlaysData(res));
  assert.strictEqual(w._pwPublicTopPlays().length, 0, 'n<8 & schwach → kein Public-Top-Play');
});

test('#71 Whale-Public: nur Positionen über der Schwelle + Sport + Preis 3–97¢', async () => {
  await withData((w) => {
    const c = w._pwWhalePublicCandidates();
    const lakers = c.find(x => x.side === 'Lakers');
    assert.ok(lakers, 'untracked $120K Lakers-Whale ist Kandidat');
    assert.strictEqual(lakers.tracked, false);
    assert.ok(!c.some(x => x.side === 'Celtics'), 'untracked $40K unter $100K-Schwelle → raus');
  });
});

test('#71 Whale-Public: tracked-Schwelle greift bei $25K', async () => {
  const track3 = JSON.parse(JSON.stringify(TRACK));
  // 0xWHALE jetzt getrackt mit n8 → Schwelle $25K statt $100K; setze eine $30K-Position dazu
  track3.scores['0xMID'] = { n: 8, clvSumPP: 8, wins: 5, usd: 30000, pnl: 5000 };
  track3.open.push({ wallet: '0xMID', key: 'nba-lakers-celtics', side: 'Celtics', league: 'NBA',
    usd: 30000, entryPrice: 0.45, lastPrice: 0.45 });
  const w = boot({
    'mls-data.json': { groups: {} }, 'mls_poly_prices.json': { prices: {} },
    'mls_poly_wallets.json': { topPositionsAll: [], matches: {}, updatedAt: new Date().toISOString() },
    'poly_money_broad_close.json': BROAD, 'poly_money_broad_history.json': {},
    'poly_money_broad.json': { n: 100, byLeague: [] },
    'poly_wallet_track.json': track3, 'poly_cross_sport.json': { discrepancies: [] },
  });
  await new Promise((res) => w._pwEnsurePlaysData(res));
  const c = w._pwWhalePublicCandidates();
  const mid = c.find(x => x.side === 'Celtics');
  assert.ok(mid && mid.tracked, 'getrackte $30K-Position ist Kandidat (Schwelle $25K)');
});
