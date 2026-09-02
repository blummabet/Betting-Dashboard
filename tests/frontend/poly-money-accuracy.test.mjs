// 29.08.2026 (Sharp-Gate vereinheitlicht): die 0xSHARP-Fixtures standen auf n=6 mit 4/6.
// Das war unter dem alten Gate „scharf" (roh 67%) und ist es unter dem neuen nicht mehr —
// bei n=6 beweist keine Quote etwas (Wilson-Untergrenze 30%). Diese Tests pruefen Drilldown,
// Sharp-Spalte und Ranking, nicht die Kalibrierung -> Fixture auf eine belegte Wallet (28/40).
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

async function renderMoney(acc, broad, filter) {
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
  // 25.07.: der MLS-Rückblick (money-accuracy) erscheint nur unter ⚽ Fußball; byLeague bleibt global.
  if (filter) w._pwSetSportFilter(filter);
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
  }, undefined, 'Fußball');
  assert.match(html, /Das Geld ist schärfer als der Preis/);
  assert.match(html, /62%/); assert.match(html, /55%/);        // Trefferquoten als Klartext-KPI
  assert.doesNotMatch(html, /Brier/, 'Brier-Jargon muss raus (20.07.2026, Lucas: klar lesbar)');
  assert.doesNotMatch(html, /Kalibrierung/);
  assert.match(html, /Geld gewann/); assert.match(html, /LA-SEA/);
});

test('Preis besser: rotes Urteil (dummes Geld)', async () => {
  const html = await renderMoney({ n: 30, moneyHitRate: 0.4, priceHitRate: 0.55,
    brierMoney: 0.6, brierPrice: 0.5, verdict: 'preis_besser', disagree: { n: 5, moneyWon: 1, priceWon: 4 }, rows: [] }, undefined, 'Fußball');
  assert.match(html, /Der Preis ist besser als das Geld/);
});

test('zu wenig Daten: ehrlicher Sammel-Zustand statt Fantasiezahl', async () => {
  const html = await renderMoney({ n: 0 }, undefined, 'Fußball');
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

// 25.07.2026 (Lucas 🔎): Whale-Drilldown — Klick auf Wallet → Track-Record + alle Positionen.
test('🔎 Wallet-Chip trägt 🔎 mit Drilldown-Aufruf', () => {
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'https://example.com/', runScripts: 'outside-only' });
  const { window: w } = dom;
  w.eval(readFileSync(PW, 'utf8'));
  const chip = w._pwWalletChip('0xABCDEF1234567890');
  assert.match(chip, /🔎/);
  assert.match(chip, /_pwWhaleDrill\('0xABCDEF1234567890'\)/);
  assert.match(chip, /profile\/0xABCDEF1234567890/, 'Profil-Link bleibt erhalten');
});

test('🔎 Drilldown-Overlay: Track-Record + offene Positionen der Wallet', async () => {
  const files = {
    'mls-data.json': { groups: {} }, 'mls_poly_prices.json': { prices: {} },
    'mls_poly_wallets.json': { topPositionsAll: [], matches: {}, updatedAt: new Date().toISOString() },
    'poly_money_broad.json': { n: 0 },
    'poly_wallet_track.json': { scores: { '0xSHARP': { n: 40, clvSumPP: 120, wins: 28, pnl: 500 } }, open: {
      '0xSHARP|mlb-a-b|Braves': { wallet: '0xSHARP', key: 'mlb-a-b', side: 'Braves', league: 'MLB', firstPrice: 0.42, usd: 30000 },
      '0xSHARP|atp-x-y|Alcaraz': { wallet: '0xSHARP', key: 'atp-x-y', side: 'Alcaraz', league: 'TENNIS', firstPrice: 0.6, usd: 12000 },
      '0xOTHER|nba-c-d|Lakers': { wallet: '0xOTHER', key: 'nba-c-d', side: 'Lakers', league: 'NBA', firstPrice: 0.5, usd: 5000 } } },
  };
  const dom = new JSDOM('<!DOCTYPE html><body><div id="polyWalletsPanel"></div></body>',
    { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window;
  w.fetch = (url) => { const u = String(url); let b = null; for (const [f, d] of Object.entries(files)) if (u.includes(f)) { b = d; break; } return Promise.resolve({ ok: b != null, json: () => Promise.resolve(b) }); };
  w.eval(readFileSync(PW, 'utf8'));
  w.initPolyWallets();
  await new Promise(r => setTimeout(r, 30));
  w._pwWhaleDrill('0xSHARP');
  const ov = w.document.getElementById('pwDrillOverlay');
  assert.ok(ov, 'Overlay muss erscheinen');
  const html = ov.innerHTML;
  assert.match(html, /\+3\.0pp Ø CLV/); assert.match(html, /🔥 scharf/);
  assert.match(html, /Braves/); assert.match(html, /Alcaraz/);   // beide Positionen
  assert.ok(!/Lakers/.test(html), 'fremde Wallet-Position darf nicht auftauchen');
  w._pwWhaleDrillClose();
  assert.ok(!w.document.getElementById('pwDrillOverlay'), 'Schließen entfernt das Overlay');
});

// 25.07.2026 (Lucas 🆕): Was-ist-neu-Feed — neue Einstiege (24h) + Favoriten-Flips.
test('🆕 Neue Einstiege: nur letzte 24h', () => {
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'https://example.com/', runScripts: 'outside-only' });
  const { window: w } = dom;
  w.eval(readFileSync(PW, 'utf8'));
  const now = Date.now();
  const track = { open: {
    'a|k1|A': { wallet: '0xa', key: 'k1', side: 'A', league: 'MLB', firstPrice: 0.4, usd: 9000, firstTs: new Date(now - 2 * 3.6e6).toISOString() },
    'b|k2|B': { wallet: '0xb', key: 'k2', side: 'B', league: 'MLB', firstPrice: 0.5, usd: 5000, firstTs: new Date(now - 72 * 3.6e6).toISOString() },
  } };
  const e = w._pwNewEntries(track, 24);
  assert.equal(e.length, 1); assert.equal(e[0].key, 'k1');
});

test('🔀 Flips: führende Seite gewechselt wird erkannt, stabile nicht', () => {
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'https://example.com/', runScripts: 'outside-only' });
  const { window: w } = dom;
  w.eval(readFileSync(PW, 'utf8'));
  // 02.09.2026: relativ zu jetzt. _pwFlips misst seit dem Audit über dasselbe feste Fenster wie
  // die Bewegung — vorher war die Basis arr[0], und „der Favorit ist gekippt" über 29 Stunden ist
  // keine Neuigkeit, sondern die halbe Vorgeschichte des Marktes.
  const t = (m) => new Date(Date.now() - (120 - m) * 60000).toISOString();
  const hist = {
    'k': [{ ts: t(0), p: { A: 0.6, B: 0.4 }, league: 'MLB' }, { ts: t(60), p: { A: 0.45, B: 0.55 }, league: 'MLB' }],
    'stable': [{ ts: t(0), p: { A: 0.6, B: 0.4 }, league: 'MLB' }, { ts: t(60), p: { A: 0.62, B: 0.38 }, league: 'MLB' }],
    // ausserhalb des Fensters: gekippt, aber nicht mehr „gerade passiert"
    'alt': [{ ts: new Date(Date.now() - 30 * 3600e3).toISOString(), p: { A: 0.7, B: 0.3 }, league: 'MLB' },
            { ts: new Date(Date.now() - 29 * 3600e3).toISOString(), p: { A: 0.3, B: 0.7 }, league: 'MLB' }],
  };
  const f = w._pwFlips(hist);
  assert.equal(f.length, 1, 'nur der frische Flip'); assert.equal(f[0].from, 'A'); assert.equal(f[0].to, 'B');
  assert.equal(f[0].key, 'k');
});

test('🆕 Feed rendert Einstiege (🔥 scharf) + Favoriten-Flips', async () => {
  const now = Date.now();
  const files = {
    'mls-data.json': { groups: {} }, 'mls_poly_prices.json': { prices: {} },
    'mls_poly_wallets.json': { topPositionsAll: [], matches: {}, updatedAt: new Date().toISOString() },
    'poly_money_broad.json': { n: 0 },
    'poly_wallet_track.json': { open: { 's|k1|A': { wallet: '0xSHARP', key: 'k1', side: 'A', league: 'MLB', firstPrice: 0.4, usd: 9000, firstTs: new Date(now - 3 * 3.6e6).toISOString() } }, scores: { '0xSHARP': { n: 40, clvSumPP: 120, wins: 28 } } },
    // 02.09.2026: relativ zu jetzt — _pwFlips schaut nur noch ins feste Fenster.
    'poly_money_broad_history.json': { 'k2': [{ ts: new Date(now - 2 * 3.6e6).toISOString(), p: { X: 0.6, Y: 0.4 }, league: 'NBA' }, { ts: new Date(now - 1 * 3.6e6).toISOString(), p: { X: 0.4, Y: 0.6 }, league: 'NBA' }] },
  };
  const dom = new JSDOM('<!DOCTYPE html><body><div id="polyWalletsPanel"></div></body>',
    { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window;
  w.fetch = (url) => { const u = String(url); let b = null; for (const [f, d] of Object.entries(files)) if (u.includes(f)) { b = d; break; } return Promise.resolve({ ok: b != null, json: () => Promise.resolve(b) }); };
  w.eval(readFileSync(PW, 'utf8'));
  w.initPolyWallets();
  await new Promise(r => setTimeout(r, 30));
  w._pwSetView('new');
  const html = w.document.getElementById('polyWalletsPanel').innerHTML;
  assert.match(html, /Neue große Einstiege/); assert.match(html, /🔥/, 'scharfe Wallet markiert');
  assert.match(html, /Favorit gekippt/);
});

// 25.07.2026 (Lucas ③): Heute-wetten-Shortlist — edge-fokussiert (echte Signale, keine bloßen
// Favoriten), BET (mit Geld) vs FADE (dagegen), Conviction 0–10. Landing-View.
test('③ Shortlist: Edge (Geld schlägt Preis) → BET mit Conviction; reiner Favorit → SKIP', async () => {
  const files = {
    'mls-data.json': { groups: {} }, 'mls_poly_prices.json': { prices: {} },
    'mls_poly_wallets.json': { topPositionsAll: [], matches: {}, updatedAt: new Date().toISOString() },
    'poly_money_broad_close.json': {
      // Geld auf Braves (70%), Preis-Favorit aber Padres → uneinig; Liga „geld_schaerfer" → BET Braves
      'mlb-a-b': { league: 'MLB', resolved: null, totalUsd: 100000,
        shares: { 'Atlanta Braves': 70000, 'San Diego Padres': 30000 },
        prices: { 'Atlanta Braves': 0.45, 'San Diego Padres': 0.55 } },
      // reiner Favorit, Geld & Preis einig → kein Edge → SKIP (darf NICHT auftauchen)
      'nba-c-d': { league: 'NBA', resolved: null, totalUsd: 100000,
        shares: { 'Lakers': 80000, 'Celtics': 20000 }, prices: { 'Lakers': 0.80, 'Celtics': 0.20 } },
    },
    // 29.08.2026 (Säulen-Neugewichtung): das Liga-Urteil braucht jetzt eine Stichprobe. „Geld ist
    // in dieser Liga schärfer" aus fünf Spielen ist eine Behauptung, keine Erkenntnis — deshalb
    // wiegt ein belegtes Urteil (n>=PW_GVP_MIN_N) 1,5 und ein unbelegtes 1,0. Die Fixture trägt
    // ihr n jetzt mit, so wie die echten byLeague-Einträge auch.
    'poly_money_broad.json': { n: 100, byLeague: [{ league: 'MLB', verdict: 'geld_schaerfer', n: 24 }] },
  };
  const dom = new JSDOM('<!DOCTYPE html><body><div id="polyWalletsPanel"></div></body>',
    { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window;
  w.fetch = (url) => { const u = String(url); let b = null; for (const [f, d] of Object.entries(files)) if (u.includes(f)) { b = d; break; } return Promise.resolve({ ok: b != null, json: () => Promise.resolve(b) }); };
  w.eval(readFileSync(PW, 'utf8'));
  w.initPolyWallets();
  await new Promise(r => setTimeout(r, 30));
  w._pwSetView('bet');                        // 🔥 Heute wetten (Landung bleibt vorerst 'money')
  const html = w.document.getElementById('polyWalletsPanel').innerHTML;
  assert.match(html, /Heute wetten/);
  assert.match(html, /BET/); assert.match(html, /Atlanta Braves/);
  // 29.08.2026 (Säulen-Neugewichtung): war 6/10, ist 5/10. Rechnung: Basis 2 + Geld 1,5 (@70%)
  // + belegtes Liga-Urteil 1,5 (vorher 2,0) = 5. Der Test prüft, dass eine echte Kante als BET
  // erscheint und ein reiner Favorit nicht — nicht die Kalibrierung der Gewichte.
  assert.match(html, /5\/10/, 'Conviction = 2 + Geld 1,5 + geld_schaerfer 1,5 = 5');
  assert.ok(!/Lakers/.test(html), 'reiner Favorit ohne Edge darf nicht in der Shortlist stehen');
});

test('③ Shortlist leer → „kein Signal ist auch ein Ergebnis" (nicht wetten)', () => {
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'https://example.com/', runScripts: 'outside-only' });
  const { window: w } = dom;
  w.eval(readFileSync(PW, 'utf8'));
  assert.match(w._pwShortlist({}), /Kein Signal ist auch ein Ergebnis/);
});

// 25.07.2026 (Lucas ① Momentum): „was bewegt sich gerade" — stärkster Poly-Preis-Move je Markt,
// Steam (zieht weiter) vs Reversal (dreht), aus der globalen Preis-Zeitreihe.
test('Momentum (①): Tempo statt Gesamt-Move, Trend statt Ein-Tick, „zu kurz" wenn zu kurz', () => {
  // 02.09.2026, Lucas-Audit. Dieser Test trug den alten Vertrag: Basis war der ÄLTESTE Snapshot
  // (Fenster 0,1h–29,2h, trotzdem gegeneinander sortiert), und „Steam vs dreht" kam aus EINEM
  // Tick — gemessen waren 65% dieser Ticks exakt 0,00pp. Jetzt: festes 6h-Fenster, Sortierung
  // nach pp/h, Richtung aus der Steigung über den jüngeren Teil, und unter vier Punkten sagt
  // die Spalte „zu kurz" statt zu raten.
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'https://example.com/', runScripts: 'outside-only' });
  const { window: w } = dom;
  w.eval(readFileSync(PW, 'utf8'));
  const _base = Date.now() - 120 * 60000;
  const t = (min) => new Date(_base + min * 60000).toISOString();
  const hist = {
    'mlb-a-b': [   // stetig hoch, +8pp über 2h → Steam
      { ts: t(0),   p: { Braves: 0.50, Padres: 0.50 }, v: 200000, htk: 4,   league: 'MLB' },
      { ts: t(40),  p: { Braves: 0.52, Padres: 0.48 }, v: 205000, htk: 3.3, league: 'MLB' },
      { ts: t(80),  p: { Braves: 0.55, Padres: 0.45 }, v: 210000, htk: 2.6, league: 'MLB' },
      { ts: t(120), p: { Braves: 0.58, Padres: 0.42 }, v: 220000, htk: 2,   league: 'MLB' }],
    'atp-x-y': [   // hoch, dann zurück: Gesamt +4pp, Schwanz fällt → dreht
      { ts: t(0),   p: { Alcaraz: 0.50 }, v: 80000, htk: 5,   league: 'TENNIS' },
      { ts: t(40),  p: { Alcaraz: 0.60 }, v: 82000, htk: 4.3, league: 'TENNIS' },
      { ts: t(80),  p: { Alcaraz: 0.58 }, v: 85000, htk: 3.6, league: 'TENNIS' },
      { ts: t(120), p: { Alcaraz: 0.54 }, v: 86000, htk: 3,   league: 'TENNIS' }],
    'kurz-x': [    // nur zwei Punkte, aber deutlicher Move → Zeile bleibt, Richtung nicht
      { ts: t(60),  p: { A: 0.40 }, v: 90000, htk: 3, league: 'MLB' },
      { ts: t(120), p: { A: 0.47 }, v: 90000, htk: 2, league: 'MLB' }],
    'flat-x': [    // unter der Rauschkante → raus
      { ts: t(60),  p: { A: 0.50 },   v: 90000, htk: 3, league: 'MLB' },
      { ts: t(120), p: { A: 0.505 },  v: 90000, htk: 2, league: 'MLB' }],
    'alt-x': [     // ausserhalb des 6h-Fensters → raus, KEIN Rückfall auf arr[0]
      { ts: new Date(Date.now() - 30 * 3600e3).toISOString(), p: { A: 0.10 }, v: 99000, htk: 26, league: 'MLB' },
      { ts: new Date(Date.now() - 29 * 3600e3).toISOString(), p: { A: 0.60 }, v: 99000, htk: 25, league: 'MLB' }],
  };
  const h = w._pwMomentum(hist);
  assert.match(h, /Was sich gerade bewegt/);
  assert.match(h, /Braves/);
  assert.match(h, /\+8\.0pp/, 'der Gesamt-Move steht weiter da');
  assert.match(h, /▲ Steam/, 'stetiger Anstieg über vier Punkte = Steam');
  assert.match(h, /▼ dreht/, 'Anstieg mit fallendem Schwanz = dreht');
  assert.match(h, /zu kurz/, 'zwei Punkte tragen keine Richtung');
  assert.ok(!/flat-x/.test(h), 'unter der Rauschkante = raus');
  assert.ok(!/alt-x/.test(h), 'ausserhalb des Fensters darf NICHT über arr[0] zurückkommen');
  assert.ok(h.indexOf('Braves') < h.indexOf('Alcaraz'), 'nach Tempo sortiert (4 pp/h vor 2 pp/h)');
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

// 25.07.2026 (Lucas ②): Sharp-Wallet — CLV/Treffer-Spalte + 🔥 für bewiesen-scharfe Wallets.
test('② Sharp-Spalte: bewiesene Wallet zeigt CLV + 🔥, dünne zeigt „sammelt"', async () => {
  const files = {
    'mls-data.json': { groups: {} }, 'mls_poly_prices.json': { prices: {} },
    'mls_poly_wallets.json': { topPositionsAll: [], matches: {}, updatedAt: new Date().toISOString() },
    'poly_money_broad_close.json': {
      'mlb-a-b': { league: 'MLB', resolved: null, totalUsd: 400000, shares: { A: 1, B: 1 },
        whales: [{ wallet: '0xSHARP', side: 'A', usd: 50000 }, { wallet: '0xNEW', side: 'B', usd: 9000 }] } },
    'poly_wallet_track.json': { scores: { '0xSHARP': { n: 40, clvSumPP: 120, wins: 28 }, '0xNEW': { n: 1, clvSumPP: 0.5, wins: 0 } } },
    'poly_money_broad.json': { n: 0 },
  };
  const dom = new JSDOM('<!DOCTYPE html><body><div id="polyWalletsPanel"></div></body>',
    { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window;
  w.fetch = (url) => { const u = String(url); let b = null; for (const [f, d] of Object.entries(files)) if (u.includes(f)) { b = d; break; } return Promise.resolve({ ok: b != null, json: () => Promise.resolve(b) }); };
  w.eval(readFileSync(PW, 'utf8'));
  w.initPolyWallets();
  await new Promise(r => setTimeout(r, 30));
  w._pwSetView('whales');
  const html = w.document.getElementById('polyWalletsPanel').innerHTML;
  assert.match(html, /Schärfe \(CLV/);
  assert.match(html, /🔥/, 'bewiesen-scharfe Wallet (n≥4, CLV>0) muss 🔥 bekommen');
  assert.match(html, /\+3\.0pp/, 'Ø CLV = 18/6 = 3.0pp');
  assert.match(html, /sammelt/, 'dünne Wallet (n<4) zeigt „sammelt" statt Fantasiewert');
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
  w._pwSetView('xsport');   // 28.07.2026: die globale Cross-Sport-Edge (a) hat jetzt den eigenen Tab
  let html = w.document.getElementById('polyWalletsPanel').innerHTML;
  assert.match(html, /Wo Poly falscher liegt als Pinnacle/, '(a) fehlt im Tab Poly vs Sharp trotz globaler Daten');
  w._pwSetView('whales');
  html = w.document.getElementById('polyWalletsPanel').innerHTML;
  assert.match(html, /Was einzelne Wale setzen/, '(c) fehlt in Whales trotz globaler Daten');
});
