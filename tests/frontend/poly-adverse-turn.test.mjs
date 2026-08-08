// tests/frontend/poly-adverse-turn.test.mjs — 07.08.2026 (Lucas: „wenn der Poly-Preis nach dem Alert
// gegen uns dreht, muss der Tick raus"). Umkehr-Sperre in _pwShortlistScore: faellt die empfohlene Seite
// hart von ihrem Hoch zurueck, wird der Play gewarnt (Badge + Conviction runter) bzw. ganz entfernt (SKIP).
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const PW = new URL('../../poly-wallets.js', import.meta.url);
function load(files) {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="polyWalletsPanel"></div></body>',
    { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const { window } = dom;
  window.fetch = (url) => {
    const name = String(url).split('?')[0].split('/').pop();
    const body = Object.prototype.hasOwnProperty.call(files, name) ? files[name] : null;
    return Promise.resolve({ ok: body != null, json: () => Promise.resolve(body) });
  };
  window.eval(readFileSync(PW, 'utf8'));
  return window;
}

// Wallet-Track mit EINER bewaehrten Wallet, offen auf FAV → Sharp-Signal (zusammen mit Geld-Mehrheit
// ergibt das einen sauberen BET, auf den wir dann die Umkehr legen).
const WT = { scores: { W1: { n: 10, clvSumPP: 20, wins: 7, pnl: 500 } },
  open: [{ key: 'lol-kill', side: 'FAV', usd: 1000, wallet: 'W1' },
         { key: 'lol-warn', side: 'FAV', usd: 1000, wallet: 'W1' },
         { key: 'lol-fav',  side: 'FAV', usd: 1000, wallet: 'W1' }] };
const HIST = {
  'lol-kill': [{ p: { FAV: 0.50, DOG: 0.50 } }, { p: { FAV: 0.75, DOG: 0.25 } }, { p: { FAV: 0.58, DOG: 0.42 } }], // −17pp vom Hoch
  'lol-warn': [{ p: { FAV: 0.50, DOG: 0.50 } }, { p: { FAV: 0.66, DOG: 0.34 } }, { p: { FAV: 0.58, DOG: 0.42 } }], // −8pp
  'lol-fav':  [{ p: { FAV: 0.72, DOG: 0.28 } }, { p: { FAV: 0.88, DOG: 0.12 } }, { p: { FAV: 0.80, DOG: 0.20 } }], // −8pp, aber noch 80% → kein Dreh
};
const mkt = (prFav) => ({ league: 'ESPORTS', totalUsd: 20000,
  shares: { FAV: 7000, DOG: 3000 }, prices: { FAV: prFav, DOG: 1 - prFav } });

async function score(key, prFav) {
  const w = load({ 'poly_money_broad_close.json': {}, 'poly_money_broad_history.json': HIST,
    'poly_wallet_track.json': WT, 'poly_money_broad.json': {}, 'poly_cross_sport.json': {} });
  await new Promise((res) => w._pwEnsurePlaysData(res));
  return w._pwShortlistScore(key, mkt(prFav));
}

test('Detektor _pwAdverseFor: Rueckfall vom Hoch, cur, null bei <2 Snaps', () => {
  const w = load({ 'poly_money_broad_close.json': {}, 'poly_money_broad_history.json': HIST });
  return new Promise((res) => w._pwEnsurePlaysData(res)).then(() => {
    const a = w._pwAdverseFor('lol-kill', 'FAV');
    assert.ok(Math.abs(a.fromPeak - 17) < 0.01);
    assert.ok(Math.abs(a.cur - 0.58) < 1e-9);
    assert.equal(w._pwAdverseFor('nope', 'FAV'), null);
  });
});

test('Starke Umkehr (−17pp) → Play raus (verdict SKIP)', async () => {
  const r = await score('lol-kill', 0.58);
  assert.equal(r.verdict, 'SKIP');
});

test('Moderate Umkehr (−8pp, <70%) → gewarnt: turned + Badge + Conviction runter', async () => {
  const r = await score('lol-warn', 0.58);
  assert.notEqual(r.verdict, 'SKIP');
  assert.equal(r.turned, true);
  assert.ok(/gedreht/.test(r.reasons[0]));
  assert.ok(r.conv <= 7);                    // um 3 abgewertet (Basis waere 10)
  assert.ok((r.signals || []).includes('turned'));
});

test('Favorit dippt (−8pp, aber noch 80%) → KEIN Dreh, normaler Play', async () => {
  const r = await score('lol-fav', 0.80);
  assert.ok(r.verdict === 'BET' || r.verdict === 'FADE');
  assert.ok(!r.turned);
  assert.ok(!/gedreht/.test((r.reasons || []).join(' ')));
});

test('Ohne Historie → keine Sperre (Play unveraendert)', async () => {
  const w = load({ 'poly_money_broad_close.json': {}, 'poly_money_broad_history.json': {},
    'poly_wallet_track.json': WT, 'poly_money_broad.json': {}, 'poly_cross_sport.json': {} });
  await new Promise((res) => w._pwEnsurePlaysData(res));
  const r = w._pwShortlistScore('lol-kill', mkt(0.58));
  assert.ok(r.verdict === 'BET' || r.verdict === 'FADE');
  assert.ok(!r.turned);
});
