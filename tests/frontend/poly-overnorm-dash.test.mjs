// tests/frontend/poly-overnorm-dash.test.mjs — 07.08.2026 (Lucas): „Volumen über Norm" ersetzt
// Whale-Watch auf der Übersicht. _pwOverNormTop liefert die Top-Zeilen (Gesamt-$ ÷ Median gleicher
// Sportart×Phase, ab ×1.6). Cache wird wie im Emitter über _pwEnsurePlaysData + Mock-Fetch gefüllt.
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
const mkt = (usd, favUsd) => ({ league: 'ESPORTS', hoursToKickoff: 2, totalUsd: usd, shares: { FAV: favUsd, DOG: usd - favUsd } });
async function overNorm(broadLive) {
  const w = load({ 'poly_money_broad_close.json': broadLive, 'poly_money_broad_history.json': {} });
  await new Promise((res) => w._pwEnsurePlaysData(res));
  return w._pwOverNormTop(5);
}

test('Hook da', () => { assert.equal(typeof load({})._pwOverNormTop, 'function'); });

test('Markt weit über Norm kommt oben — ratio/fav/usd/url', async () => {
  const rows = await overNorm({
    a: mkt(10000, 6000), b: mkt(12000, 7000), c: mkt(9000, 5000), d: mkt(11000, 6000),
    'lol-x-y-2026-08-07': mkt(200000, 150000),
  });
  assert.ok(rows.length >= 1);
  assert.equal(rows[0].key, 'lol-x-y-2026-08-07');
  assert.ok(rows[0].ratio >= 1.6);
  assert.equal(rows[0].usd, 200000);
  assert.equal(rows[0].favPct, 75);
  assert.ok(String(rows[0].url).includes('polymarket.com/event/lol-x-y-2026-08-07'));
});

test('alles gleich → nichts über Norm (leer)', async () => {
  const same = {}; for (let i = 0; i < 5; i++) same['m' + i] = mkt(10000, 6000);
  assert.equal((await overNorm(same)).length, 0);
});

test('unter Mindestvolumen ($5000) → raus', async () => {
  const small = {}; for (let i = 0; i < 5; i++) small['m' + i] = mkt(1000, 600);
  assert.equal((await overNorm(small)).length, 0);
});
