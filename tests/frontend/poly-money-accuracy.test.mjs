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

test('View-Tab „Großes Geld" existiert (25.07.2026: Landing-Tab, umbenannt)', async () => {
  const html = await renderMoney({ n: 0 });
  assert.match(html, /Großes Geld/);
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

// 25.07.2026 (Lucas: „wo liegt das große Geld, alle Sportarten, zum Folgen"). Sektion (b) aus
// poly_money_broad_close.json: kommende Märkte (resolved==null) nach Volumen, mit Geld-Seite.
test('Wo-liegt-Geld: kommende Märkte aller Sportarten mit Geld-Favorit', () => {
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'https://example.com/', runScripts: 'outside-only' });
  const { window: w } = dom;
  w.eval(readFileSync(PW, 'utf8'));
  const live = {
    'mlb-a-b-2026-08-01': { league: 'MLB', totalUsd: 400000, resolved: null, hoursToKickoff: 2,
      shares: { 'Atlanta Braves': 220000, 'San Diego Padres': 180000 },
      prices: { 'Atlanta Braves': 0.54, 'San Diego Padres': 0.46 } },
    'cs2-x-y-2026-08-01': { league: 'ESPORTS', totalUsd: 20000, resolved: null, hoursToKickoff: 1,
      shares: { 'NAVI': 15000, 'FaZe': 5000 }, prices: { 'NAVI': 0.72, 'FaZe': 0.28 } },
    'mlb-old-2026-07-01': { league: 'MLB', totalUsd: 900000, resolved: 'home',  // aufgelöst → NICHT zeigen
      shares: { 'X': 500000, 'Y': 400000 }, prices: { 'X': 0.55, 'Y': 0.45 } },
  };
  const html = w._pwMoneyLive(live);
  assert.match(html, /Atlanta Braves/, 'Team-Name (Geld-Favorit) fehlt');
  assert.match(html, /ESPORTS|🎮/, 'E-Sport muss als eigene Sportart erscheinen');
  assert.ok(!/mlb-old/.test(html), 'aufgelöste Spiele gehören nicht in die „kommend"-Sicht');
});

// 25.07.2026 (Lucas: „Edge vs Pinnacle, alle Sportarten, im Wallets-Tab"). Sektion (a) aus
// poly_cross_sport.json: Poly-% vs Pinnacle-%, Lücke, Konvergenz. Team-Namen aus `event`.
test('Globale Edge (a): rendert Cross-Sport-Lücken mit Konvergenz', () => {
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'https://example.com/', runScripts: 'outside-only' });
  const { window: w } = dom;
  w.eval(readFileSync(PW, 'utf8'));
  const cs = { matched: 40, discrepancies: [
    { sport: 'basketball_nba', event: 'Lakers vs Celtics', outcome: 'Lakers', polyPP: 62, pinnPP: 55, gapPP: 7, richtung: 'Poly zu hoch → faden', convergePP: 3 },
    { sport: 'soccer_mls', event: 'Philadelphia vs Seattle', outcome: 'Heim', polyPP: 40, pinnPP: 48, gapPP: -8, richtung: 'Poly zu niedrig → backen', convergePP: null },
  ] };
  const html = w._pwGlobalEdge(cs);
  assert.match(html, /Lakers vs Celtics/);
  assert.match(html, /🏀/, 'Sport-Icon (Basketball) fehlt');
  assert.match(html, /▼ 3\.0pp/, 'Konvergenz (schließende Lücke) muss markiert sein');
});

test('Globale Edge (a): leer-aber-verglichen ist ehrlich (keine Lücke ≠ keine Daten)', () => {
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'https://example.com/', runScripts: 'outside-only' });
  const { window: w } = dom;
  w.eval(readFileSync(PW, 'utf8'));
  const html = w._pwGlobalEdge({ matched: 30, discrepancies: [] });
  assert.match(html, /keine Lücke/i);
});

// 25.07.2026 (Lucas: „Ligen oben weg, statt dessen Sport-Filter zum Suchen"). Kategorie-Mapping
// robust aus Liga-Label ODER Sport-Key; Filter-Leiste nur bei ≥2 Kategorien.
test('Sport-Filter: Kategorien aus Liga-Label und Sport-Key', () => {
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'https://example.com/', runScripts: 'outside-only' });
  const { window: w } = dom;
  w.eval(readFileSync(PW, 'utf8'));
  assert.equal(w._pwSportCategory('MLB'), 'US-Sport');
  assert.equal(w._pwSportCategory('basketball_nba'), 'US-Sport');
  assert.equal(w._pwSportCategory('soccer_mls'), 'Fußball');
  assert.equal(w._pwSportCategory('ESPORTS'), 'E-Sport');
  assert.equal(w._pwSportCategory('boxing'), 'Kampfsport');
  const bar = w._pwSportFilterBar(new Set(['US-Sport', 'E-Sport', 'Fußball']));
  assert.match(bar, /_pwSetSportFilter\('all'\)/, 'Alle-Chip fehlt');
  assert.match(bar, /🎮 E-Sport/);
  assert.equal(w._pwSportFilterBar(new Set(['US-Sport'])), '', 'eine Kategorie → kein Filter');
});

// 25.07.2026 (Lucas: „was setzen einzelne Wale, alle Sportarten"). Sektion (c): größte Einzel-
// Wallets aus den `whales` je Markt, mit Wallet- + Markt-Link.
test('Globale Wale (c): größte Einzel-Wallets mit Links', () => {
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'https://example.com/', runScripts: 'outside-only' });
  const { window: w } = dom;
  w.eval(readFileSync(PW, 'utf8'));
  const live = { 'mlb-a-b': { league: 'MLB', resolved: null, totalUsd: 400000, shares: { Braves: 1, Padres: 1 },
    whales: [{ wallet: '0xWHALE', side: 'Braves', usd: 50000 }] } };
  const h = w._pwGlobalWhales(live);
  assert.match(h, /profile\/0xWHALE/, 'Wallet-Link fehlt');
  assert.match(h, /event\/mlb-a-b/, 'Markt-Link fehlt');
  assert.match(h, /Braves/, 'Seite fehlt');
});

// 25.07.2026 (Lucas ① Momentum): „was bewegt sich gerade" — stärkster Poly-Preis-Move je Markt,
// Steam (zieht weiter) vs Reversal (dreht), aus der globalen Preis-Zeitreihe.
test('Momentum (①): stärkster Move je Markt, Steam vs Reversal, nach Größe sortiert', () => {
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'https://example.com/', runScripts: 'outside-only' });
  const { window: w } = dom;
  w.eval(readFileSync(PW, 'utf8'));
  const t = (min) => new Date(Date.UTC(2026, 6, 24, 12, min)).toISOString();
  const hist = {
    'mlb-a-b': [
      { ts: t(0),  p: { Braves: 0.50, Padres: 0.50 }, v: 200000, htk: 3,   league: 'MLB' },
      { ts: t(30), p: { Braves: 0.54, Padres: 0.46 }, v: 210000, htk: 2.5, league: 'MLB' },
      { ts: t(60), p: { Braves: 0.58, Padres: 0.42 }, v: 220000, htk: 2,   league: 'MLB' }],   // +8pp, letzter Schritt zieht weiter → Steam
    'atp-x-y': [
      { ts: t(0),  p: { Alcaraz: 0.60 }, v: 80000, htk: 4,   league: 'TENNIS' },
      { ts: t(30), p: { Alcaraz: 0.66 }, v: 85000, htk: 3.5, league: 'TENNIS' },
      { ts: t(60), p: { Alcaraz: 0.63 }, v: 86000, htk: 3,   league: 'TENNIS' }],              // +3pp gesamt, letzter Schritt runter → dreht
    'flat-x': [
      { ts: t(0),  p: { A: 0.50 },    v: 90000, league: 'MLB' },
      { ts: t(30), p: { A: 0.5005 },  v: 90000, league: 'MLB' }],                              // <1pp → Rauschen, raus
  };
  const h = w._pwMomentum(hist);
  assert.match(h, /Was sich gerade bewegt/);
  assert.match(h, /Braves/); assert.match(h, /\+8\.0pp/); assert.match(h, /▲ Steam/);
  assert.match(h, /▼ dreht/, 'Tennis-Reversal muss als „dreht" markiert sein');
  assert.ok(!/flat-x/.test(h), 'unter 1pp Bewegung = Rauschen, raus');
  assert.ok(h.indexOf('Braves') < h.indexOf('Alcaraz'), 'nach |Move| sortiert (8pp vor 3pp)');
});

test('Momentum leer → ehrlicher Sammel-Hinweis (füllt sich über Läufe)', () => {
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'https://example.com/', runScripts: 'outside-only' });
  const { window: w } = dom;
  w.eval(readFileSync(PW, 'utf8'));
  assert.match(w._pwMomentum({}), /füllt sich über die nächsten Runner-Läufe/);
  assert.match(w._pwMomentum({ x: [{ ts: '2026-07-24T12:00:00Z', p: { A: 0.5 } }] }), /füllt sich/, '1 Snapshot reicht nicht für Bewegung');
});

// 25.07.2026 (Lucas: „die Whale-Auflistung für ALLE Sportarten, die größten Whales"): aggregiertes
// Leaderboard — je Wallet der GESAMT-Einsatz über mehrere Märkte, nach Größe sortiert.
test('Globaler Whale-Leaderboard: aggregiert je Wallet über alle Märkte/Sportarten', () => {
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'https://example.com/', runScripts: 'outside-only' });
  const { window: w } = dom;
  w.eval(readFileSync(PW, 'utf8'));
  const live = {
    'mlb-a-b': { league: 'MLB', resolved: null, totalUsd: 400000, shares: { Braves: 1, Padres: 1 },
      whales: [{ wallet: '0xSHARP', side: 'Braves', usd: 30000 }, { wallet: '0xSMALL', side: 'Padres', usd: 2000 }] },
    'atp-x-y': { league: 'TENNIS', resolved: null, totalUsd: 90000, shares: { Alcaraz: 1, Sinner: 1 },
      whales: [{ wallet: '0xSHARP', side: 'Alcaraz', usd: 25000 }] },   // 0xSHARP in 2 Märkten → aggregiert
  };
  const h = w._pwGlobalWhaleLeaderboard(live);
  assert.match(h, /Größte Whales — alle Sportarten/);
  assert.match(h, /profile\/0xSHARP/, 'Top-Wallet-Link fehlt');
  assert.match(h, /\$55K/, '0xSHARP muss $30K+$25K = $55K aggregiert zeigen');
  // 0xSHARP (55K, 2 Märkte) muss vor 0xSMALL (2K) stehen
  assert.ok(h.indexOf('0xSHARP') < h.indexOf('0xSMALL'), 'nach Gesamt-Einsatz sortiert');
});

// 25.07.2026 (Lucas: „ich seh a und c gar nicht"): der alte Leer-Riegel (kein Datensatz-Poly)
// blockierte die GLOBALEN Sektionen. Ohne Wallet-Daten, aber MIT globalen Daten müssen a+c rendern.
test('Global rendert auch ohne Datensatz-Poly (a in Chancen, c in Whales)', async () => {
  const files = {
    'mls-data.json': { groups: {} }, 'mls_poly_prices.json': { prices: {} },
    'mls_poly_wallets.json': { topPositionsAll: [], matches: {}, updatedAt: new Date().toISOString() },
    'poly_cross_sport.json': { matched: 40, discrepancies: [
      { sport: 'basketball_nba', event: 'Lakers vs Celtics', outcome: 'Lakers', polyPP: 62, pinnPP: 55, gapPP: 7, richtung: 'Poly zu hoch → faden', convergePP: 3 }] },
    'poly_money_broad_close.json': { 'mlb-a-b': { league: 'MLB', resolved: null, totalUsd: 400000,
      shares: { Braves: 1, Padres: 1 }, whales: [{ wallet: '0xW', side: 'Braves', usd: 50000 }] } },
    'poly_money_broad.json': { n: 0 },
  };
  const dom = new JSDOM('<!DOCTYPE html><body><div id="polyWalletsPanel"></div></body>',
    { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window;
  w.fetch = (url) => { const u = String(url); let b = null; for (const [f, d] of Object.entries(files)) if (u.includes(f)) { b = d; break; } return Promise.resolve({ ok: b != null, json: () => Promise.resolve(b) }); };
  w.eval(readFileSync(PW, 'utf8'));
  w.initPolyWallets();
  await new Promise(r => setTimeout(r, 25));
  w._pwSetView('edge');
  let html = w.document.getElementById('polyWalletsPanel').innerHTML;
  assert.match(html, /Wo Poly falscher liegt als Pinnacle/, '(a) fehlt in Chancen trotz globaler Daten');
  w._pwSetView('whales');
  html = w.document.getElementById('polyWalletsPanel').innerHTML;
  assert.match(html, /Was einzelne Wale setzen/, '(c) fehlt in Whales trotz globaler Daten');
});
