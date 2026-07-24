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

test('Geld schärfer: grünes Klartext-Urteil + Trefferquoten (kein Brier-Jargon)', async () => {
  const html = await renderMoney({
    n: 40, moneyHitRate: 0.62, priceHitRate: 0.55, brierMoney: 0.42, brierPrice: 0.51,
    verdict: 'geld_schaerfer', disagree: { n: 10, moneyWon: 7, priceWon: 3 },
    rows: [{ key: 'LA-SEA', winner: 'home', moneyFav: 'home', priceFav: 'away',
             moneyOK: true, priceOK: false, totalUsd: 50000 }],
  });
  assert.match(html, /Das Geld ist schärfer als der Preis/);
  assert.match(html, /62%/); assert.match(html, /55%/);        // Trefferquoten als Klartext-KPI
  assert.doesNotMatch(html, /Brier/, 'Brier-Jargon muss raus (20.07.2026, Lucas: klar lesbar)');
  assert.doesNotMatch(html, /Kalibrierung/);
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
  assert.match(html, /Quote ≥ 1\.35/, 'triviale-Favoriten-Filter muss erklärt sein');
  assert.match(html, /Geld-Favorit trifft/, 'Trefferquote-Spalte muss Klartext sein');
  assert.doesNotMatch(html, /Brier/, 'keine Brier-Spalten mehr in der Tabelle');
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
  assert.match(html, /Masse weiß am meisten/, 'Highlight-Kachel (Klartext) fehlt');
  assert.match(html, /Geld schärfer|Preis besser|gleichauf/, 'Klartext-Urteil-Badge fehlt');
});

// 25.07.2026 (Lucas: „können wir das Spiel anzeigen statt der IDs?"). Die Match-Tabelle zeigte den
// rohen Key "homeId-awayId" (2242-1603). _pwMatchLabel löst ihn über die teams-Map auf Namen auf.
test('Match-Label: löst homeId-awayId auf Team-Namen auf', () => {
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'https://example.com/', runScripts: 'outside-only' });
  const { window: w } = dom;
  w.eval(readFileSync(PW, 'utf8'));
  const teams = { '2242': { name: 'FC Cincinnati', flag: '' }, '1603': { name: 'Vancouver Whitecaps', flag: '' } };
  const html = w._pwMatchLabel('2242-1603', teams);
  assert.match(html, /FC Cincinnati/, 'Heim-Team-Name fehlt');
  assert.match(html, /Vancouver Whitecaps/, 'Auswärts-Team-Name fehlt');
  assert.ok(!/2242/.test(html), 'rohe ID darf nicht mehr erscheinen');
});

test('Match-Label: unbekannte ID fällt sicher auf den rohen Key zurück', () => {
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'https://example.com/', runScripts: 'outside-only' });
  const { window: w } = dom;
  w.eval(readFileSync(PW, 'utf8'));
  const html = w._pwMatchLabel('99999-88888', {});
  assert.match(html, /99999-88888/, 'Fallback auf Key fehlt — Zeile würde leer wirken');
});

// 25.07.2026 (Lucas: „alle Zahlen verwirrend, keine Ahnung was ich damit mache"). Jeder Wallets-
// Unter-Reiter bekommt eine Klartext-Box mit „→ Was du damit tust". Regression: alle 4 vorhanden.
test('Wallets: jeder Unter-Reiter hat eine Handlungs-Box', () => {
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'https://example.com/', runScripts: 'outside-only' });
  const { window: w } = dom;
  w.eval(readFileSync(PW, 'utf8'));
  for (const v of ['edge', 'smart', 'whales', 'money']) {
    const h = w._pwViewIntro(v);
    assert.match(h, /Was du damit tust/, `Handlungs-Box fehlt für ${v}`);
  }
  assert.equal(w._pwViewIntro('gibtsnicht'), '', 'unbekannte View → leer');
});
