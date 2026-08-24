// tests/frontend/poly-whales-tab.test.mjs — 24.08.2026 (Lucas: „im Polymarket Betting ein neuer Tab
// mit Whales — die Wetten der Top-20 aus der Übersicht"). Zwei Risiken werden hier festgepinnt:
//   1. Der Tab darf NUR zeigen, was man noch spielen kann. Von 17 offenen Positionen der Top-20 waren
//      am 24.08. genau 1 vor Anpfiff — ohne Filter wäre das ein Friedhof aus fertigen Spielen.
//   2. Die Wallet-Auswahl muss dieselbe sein wie im Wallets-Menü (eine Quelle, kein Nachbau).
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const VERDICT = new URL('../../pick-verdict.js', import.meta.url);
const PW      = new URL('../../poly-wallets.js', import.meta.url);
const POLY    = new URL('../../polymarket-tab.js', import.meta.url);

const NOW = new Date().toISOString();

// Markt im Broad-Feed. htk>0 = Anpfiff in der Zukunft (spielbar), htk<0 = laeuft schon.
function market(league, htk, prices, tokens) {
  return { league, sport: null, resolved: null, totalUsd: 100000, capturedAt: NOW,
           hoursToKickoff: htk, shares: prices, prices, ...(tokens ? { tokens } : {}) };
}

// Wallet mit echter P&L → Modus A der Rangliste (n≥8, Ø CLV≥0, Treffer≥45 %, Ø-Einsatz ≥$1.000).
function sharp(pnl, n = 12) {
  return { n, clvSumPP: 12, wins: Math.round(n * 0.6), usd: n * 5000, pnl };
}

function boot(files) {
  const dom = new JSDOM('<!DOCTYPE html><body></body>',
    { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window;
  w.fetch = (url) => { const u = String(url); let b = null;
    for (const [f, d] of Object.entries(files)) if (u.includes(f)) { b = d; break; }
    return Promise.resolve({ ok: b != null, json: () => Promise.resolve(b) }); };
  w.eval(readFileSync(VERDICT, 'utf8'));
  w.eval(readFileSync(PW, 'utf8'));
  w.eval(readFileSync(POLY, 'utf8'));
  return w;
}

function withData(broad, track, fn) {
  const w = boot({
    'mls-data.json': { groups: {} }, 'mls_poly_prices.json': { prices: {} },
    'mls_poly_wallets.json': { topPositionsAll: [], matches: {}, updatedAt: NOW },
    'poly_money_broad_close.json': broad,
    'poly_money_broad_live.json': {},
    'poly_money_broad_history.json': {}, 'poly_money_broad.json': { n: 100, byLeague: [] },
    'poly_wallet_track.json': track, 'poly_cross_sport.json': { discrepancies: [] },
  });
  return new Promise((resolve) => { w._pwEnsurePlaysData(() => resolve(fn(w))); });
}

const BROAD = {
  'cs2-g1-leo2':  market('ESPORTS',  1.7, { 'Leo Team': 0.325, 'GenOne': 0.675 }, { 'Leo Team': 'TOK1' }),
  'atp-a-b':      market('ATP',      3.0, { 'Spieler A': 0.55, 'Spieler B': 0.45 }),
  'cs2-laeuft':   market('ESPORTS', -1.2, { 'Team X': 0.60, 'Team Y': 0.40 }),
};

const TRACK = {
  updatedAt: NOW,
  scores: { '0xA': sharp(5000000), '0xB': sharp(2000000), '0xC': sharp(900000) },
  open: [
    // Konsens: ZWEI Top-Wallets auf derselben Seite, Anpfiff in der Zukunft
    { wallet: '0xA', key: 'cs2-g1-leo2', side: 'Leo Team', league: 'ESPORTS', usd: 2000, entryPrice: 0.30 },
    { wallet: '0xB', key: 'cs2-g1-leo2', side: 'Leo Team', league: 'ESPORTS', usd: 500,  entryPrice: 0.34 },
    // Einzelnes Wallet, ebenfalls spielbar
    { wallet: '0xC', key: 'atp-a-b',     side: 'Spieler A', league: 'ATP',    usd: 8000, entryPrice: 0.50 },
    // laeuft schon → darf NICHT auftauchen
    { wallet: '0xA', key: 'cs2-laeuft',  side: 'Team X',    league: 'ESPORTS', usd: 9000, entryPrice: 0.55 },
    // gar nicht im Feed (Ledger haengt) → darf NICHT auftauchen
    { wallet: '0xB', key: 'lol-weg-2026-08-01', side: 'Irgendwer', league: 'ESPORTS', usd: 7000, entryPrice: 0.6 },
  ],
};

test('Whales: nur noch spielbare Positionen (laufend + nicht-im-Feed fliegen raus)', async () => {
  await withData(BROAD, TRACK, (w) => {
    const keys = w._pwWhalePlays().map(p => p.key);
    assert.deepStrictEqual([...keys].sort(), ['atp-a-b', 'cs2-g1-leo2']);
    assert.ok(!keys.includes('cs2-laeuft'), 'laufendes Spiel raus');
    assert.ok(!keys.includes('lol-weg-2026-08-01'), 'nicht mehr im Feed raus');
  });
});

test('Whales: Konsens wird aggregiert und sortiert nach vorn', async () => {
  await withData(BROAD, TRACK, (w) => {
    const plays = w._pwWhalePlays();
    assert.strictEqual(plays[0].key, 'cs2-g1-leo2', 'Konsens zuerst');
    assert.strictEqual(plays[0].n, 2, 'zwei Top-Wallets auf derselben Seite');
    assert.strictEqual(plays[0].usd, 2500, 'Whale-Geld summiert');
    assert.strictEqual(plays[1].n, 1);
  });
});

test('Whales: „Einstieg → jetzt" ist USD-gewichtet', async () => {
  await withData(BROAD, TRACK, (w) => {
    const p = w._pwWhalePlays()[0];
    // (0.30×2000 + 0.34×500) / 2500 = 0.308 → Markt 0.325 = +1,7pp gegen uns
    assert.ok(Math.abs(p.entryAvg - 0.308) < 1e-9, 'gewichteter Ø-Einstieg: ' + p.entryAvg);
    assert.strictEqual(p.driftPP, 1.7);
  });
});

test('Whales: Match-Label ist Klartext (kein HTML im escapten Text)', async () => {
  await withData(BROAD, TRACK, (w) => {
    const p = w._pwWhalePlays()[0];
    assert.ok(!/[<>]/.test(String(p.match)), 'kein Markup im Label: ' + p.match);
    const html = w._renderPolyWhales([p]);
    assert.ok(!html.includes('&lt;span'), 'kein escapter span sichtbar');
  });
});

test('Whales: Setzen auch ohne Token — Link NUR noch bei gesperrter Sportart', async () => {
  // 24.08.2026: Vorher fiel ein tokenloser Play stumm auf einen Link zurück und war damit von einer
  // bewusst gesperrten Sportart nicht zu unterscheiden. Jetzt ist der Link ein eindeutiges Signal.
  await withData(BROAD, TRACK, (w) => {
    const [mitToken, ohneToken] = w._pwWhalePlays();
    assert.strictEqual(mitToken.token, 'TOK1');
    assert.strictEqual(ohneToken.token, null);
    assert.ok(w._renderPolyWhales([mitToken]).includes('🟣 Setzen'), 'mit Token setzbar');
    assert.ok(w._renderPolyWhales([ohneToken]).includes('🟣 Setzen'), 'ohne Token ebenfalls setzbar');
    const gesperrt = { ...mitToken, league: 'MLB', sport: null };
    const html = w._renderPolyWhales([gesperrt]);
    assert.ok(html.includes('🟣 Öffnen'), 'gesperrte Sportart bleibt Link');
    assert.match(html, /bewusst nicht setzbar/, 'und sagt im Tooltip warum');
  });
});

test('Whales: dieselbe Wallet-Auswahl wie die Rangliste im Wallets-Menü', async () => {
  await withData(BROAD, TRACK, (w) => {
    // Arrays kommen aus dem jsdom-Realm -> in ein Host-Array spreaden, sonst schlaegt
    // deepStrictEqual trotz gleicher Struktur fehl (nicht referenzgleiche Prototypen).
    const rank = [...w.eval('_pwRankRows()')].map(r => r.wallet);
    assert.deepStrictEqual(rank, ['0xA', '0xB', '0xC'], 'nach P&L sortiert');
    // Eine Wallet, die den Schärfe-Floor reißt, darf weder in der Rangliste noch im Tab auftauchen.
    const track2 = JSON.parse(JSON.stringify(TRACK));
    track2.scores['0xD'] = { n: 20, clvSumPP: -40, wins: 4, usd: 100000, pnl: 99999999 };  // CLV<0, Treffer 20%
    track2.open.push({ wallet: '0xD', key: 'atp-a-b', side: 'Spieler B', league: 'ATP', usd: 5000, entryPrice: 0.4 });
    return withData(BROAD, track2, (w2) => {
      assert.ok(![...w2.eval('_pwRankRows()')].some(r => r.wallet === '0xD'), 'Verlierer nicht in der Rangliste');
      assert.ok(!w2._pwWhalePlays().some(p => p.side === 'Spieler B'), 'und damit auch nicht im Tab');
    });
  });
});

test('Whales: Sub-Tab erscheint in der Leiste', async () => {
  await withData(BROAD, TRACK, (w) => {
    assert.ok(w._polySubtabBar().includes('🐋 Whales'));
  });
});

test('Whales: ohne qualifizierte Wallets kein Absturz', async () => {
  await withData(BROAD, { updatedAt: NOW, scores: {}, open: [] }, (w) => {
    assert.strictEqual(w._pwWhalePlays().length, 0);
    assert.ok(w._renderPolyWhales([]).includes('🐋 Whales'));
  });
});
