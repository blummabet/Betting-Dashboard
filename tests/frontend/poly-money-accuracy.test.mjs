// tests/frontend/poly-money-accuracy.test.mjs
// 19.07.2026 — Wallets-Tab „Liegt das Geld richtig?": empirischer Test, ob das Poly-Geld schärfer
// ist als der Preis. Eigener View-Tab neben dem Edge-Board.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const PW = new URL('../../poly-wallets.js', import.meta.url);

const baseWallets = { topPositionsAll: [{ wallet: '0xa', usd: 5000, side: 'home',
  pick: 'Heim', key: 'H-A', match: 'H vs A' }], updatedAt: new Date().toISOString() };

function mockFetch(files) {
  return (url) => {
    const u = String(url);
    let body = null;
    for (const [frag, data] of Object.entries(files)) if (u.includes(frag)) { body = data; break; }
    return Promise.resolve({ ok: body != null, json: () => Promise.resolve(body) });
  };
}

async function renderMoney(acc, broad) {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="polyWalletsPanel"></div></body>',
    { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const { window: w } = dom;
  w.fetch = mockFetch({
    'mls-data.json': { groups: {} }, 'mls_poly_prices.json': { prices: {} },
    'mls_poly_wallets.json': baseWallets, 'mls-odds-history.json': {},
    'mls_poly_money_accuracy.json': acc,
    'poly_money_broad.json': broad || { n: 0 },
  });
  w.eval(readFileSync(PW, 'utf8'));
  w._pwDsId = 'mls';
  w.initPolyWallets();
  await new Promise(r => setTimeout(r, 20));
  w._pwSetView('money');                       // in den Geld-View schalten
  return w.document.getElementById('polyWalletsPanel').innerHTML;
}

test('View-Tab „Liegt das Geld richtig?" existiert', async () => {
  const html = await renderMoney({ n: 0 });
  assert.match(html, /Liegt das Geld richtig/);
});

test('Geld schärfer: grünes Urteil + Brier-Vergleich + Trefferquoten', async () => {
  const html = await renderMoney({
    n: 40, moneyHitRate: 0.62, priceHitRate: 0.55, brierMoney: 0.42, brierPrice: 0.51,
    verdict: 'geld_schaerfer', disagree: { n: 10, moneyWon: 7, priceWon: 3 },
    rows: [{ key: 'LA-SEA', winner: 'home', moneyFav: 'home', priceFav: 'away',
             moneyOK: true, priceOK: false, totalUsd: 50000 }],
  });
  assert.match(html, /Das Geld ist schärfer als der Preis/);
  assert.match(html, /62%/); assert.match(html, /55%/);
  assert.match(html, /0\.420/); assert.match(html, /0\.510/, 'Brier-Preis-Wert fehlt');
  assert.match(html, /Geld gewann/); assert.match(html, /LA-SEA/);
});

test('Preis besser: rotes Urteil (dummes Geld)', async () => {
  const html = await renderMoney({ n: 30, moneyHitRate: 0.4, priceHitRate: 0.55,
    brierMoney: 0.6, brierPrice: 0.5, verdict: 'preis_besser', disagree: { n: 5, moneyWon: 1, priceWon: 4 }, rows: [] });
  assert.match(html, /Der Preis ist besser als das Geld/);
});

test('zu wenig Daten: ehrlicher Sammel-Zustand statt Fantasiezahl', async () => {
  const html = await renderMoney({ n: 0 });
  assert.match(html, /Sammelt noch/);
  assert.doesNotMatch(html, /schärfer als der Preis/);
});

test('Alle Poly-Ligen: Liga-Breakdown mit Geld-Vorteil + min-Quote-Hinweis', async () => {
  const html = await renderMoney({ n: 0 }, {
    n: 120, minVolUsd: 7500, minOdds: 1.35, byLeague: [
      { league: 'NBA', n: 40, moneyHitRate: 0.62, brierMoney: 0.42, brierPrice: 0.50, verdict: 'geld_schaerfer' },
      { league: 'EPL', n: 25, moneyHitRate: 0.50, brierMoney: 0.55, brierPrice: 0.52, verdict: 'preis_besser' },
    ],
  });
  assert.match(html, /Alle Poly-Ligen/);
  assert.match(html, /NBA/); assert.match(html, /EPL/);
  assert.match(html, /Mindest-Quote 1\.35/, 'triviale-Favoriten-Filter muss erklärt sein');
});

test('Alle Poly-Ligen: leerer Zustand ist ein ehrlicher Sammel-Hinweis', async () => {
  const html = await renderMoney({ n: 0 }, { n: 0 });
  assert.match(html, /sammelt am Mac-Runner/);
});

test('Alle Poly-Ligen: nach Kategorie geordnet inkl. E-Sport + Highlight-Kacheln', async () => {
  const html = await renderMoney({ n: 0 }, {
    n: 200, minVolUsd: 7500, minOdds: 1.35, byLeague: [
      { league: 'NBA', n: 40, moneyHitRate: 0.62, brierMoney: 0.42, brierPrice: 0.50, verdict: 'geld_schaerfer' },
      { league: 'EPL', n: 25, moneyHitRate: 0.50, brierMoney: 0.55, brierPrice: 0.52, verdict: 'preis_besser' },
      { league: 'CS2', n: 30, moneyHitRate: 0.58, brierMoney: 0.45, brierPrice: 0.48, verdict: 'geld_schaerfer' },
    ],
  });
  assert.match(html, /🎮 E-Sport/, 'E-Sport-Kategorie muss erscheinen');
  assert.match(html, /🇺🇸 US-Sport/);
  assert.match(html, /⚽ Fußball/);
  assert.match(html, /Masse am schärfsten/, 'Highlight-Gimmick fehlt');
  assert.match(html, /Ø Geld-Vorteil/, 'Kategorie-Subtotal fehlt');
});
