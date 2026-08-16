// tests/frontend/poly-smartmoney.test.mjs
// 19.07.2026 — Dashboard-Ausbau: die bisher KOMPLETT ungenutzte {ds}_poly_smartmoney.json wird
// jetzt geladen und als „Smart-Money-Konzentration" gerendert (Geld-Split, Halter-Breite,
// Whale-Konzentration, Fluss) + Deep-Link auf Polymarket.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const PW = new URL('../../poly-wallets.js', import.meta.url);

function win() {
  const dom = new JSDOM('<!DOCTYPE html><body></body>',
    { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const { window: w } = dom;
  w.eval(readFileSync(PW, 'utf8'));
  return w;
}

const smart = { matches: { 'ESP-ARG': {
  home: 'Spanien', away: 'Argentinien', totalUsd: 1417268, hoursToKickoff: 12.6,
  outcomes: {
    home: { usd: 463608, share: 0.327, topHolderShare: 0.525, holders: 200, netFlowUsd: 17592 },
    draw: { usd: 183406, share: 0.129, topHolderShare: 0.78, holders: 200 },
    away: { usd: 770254, share: 0.543, topHolderShare: 0.771, holders: 200 } } } } };
const prices = { prices: { 'ESP-ARG': { slug: 'fifwc-esp-arg-2026-07-19' } } };

test('Smart-Money-Konzentration rendert Split, Halter, Konzentration', () => {
  const html = win()._pwSmartConcentration(smart, prices, {});
  assert.match(html, /Smart-Money-Konzentration/);
  assert.match(html, /Spanien – Argentinien/);
  assert.match(html, /Geld liegt auf/);   // 25.07.2026: Spaltenkopf in Klartext (war „Geld-Split")
});

test('hohe Whale-Konzentration wird als weiches Signal markiert', () => {
  const html = win()._pwSmartConcentration(smart, prices, {});
  assert.match(html, /⚠️ 78%/, 'topHolderShare ≥ 70% muss als Warnung erscheinen');
});

test('Deep-Link auf den Polymarket-Markt (slug)', () => {
  const html = win()._pwSmartConcentration(smart, prices, {});
  assert.match(html, /polymarket\.com\/event\/fifwc-esp-arg-2026-07-19/);
});

test('leere/dünne Smart-Money-Daten → keine Sektion (kein leerer Kasten)', () => {
  const w = win();
  assert.equal(w._pwSmartConcentration(null, prices, {}), '');
  assert.equal(w._pwSmartConcentration({ matches: { X: { totalUsd: 100, outcomes: {} } } }, prices, {}), '');
});

test('Deep-Link-Helfer robust bei fehlendem slug', () => {
  assert.equal(win()._pwPolyLink(null), '');
});

// O/U-Leiter komplett (19.07.2026): poly_o15/o35 waren ungenutzt → jetzt im Edge-Board.
test('Edge-Board: O/U 1.5 + 2.5 + 3.5 mit Pinnacle-Fair (WM-Stil)', () => {
  const w = win();
  const prices = { prices: { 'H-A': { homeName: 'H', awayName: 'A', homeId: 'h', awayId: 'a',
    hw: 0.5, dr: 0.3, aw: 0.3, vol: 50000,
    poly_o15: 0.7, poly_u15: 0.3, poly_o25: 0.45, poly_u25: 0.55, poly_o35: 0.2, poly_u35: 0.8 } } };
  const odds = { 'H-A': { hw: 2.0, dr: 3.5, aw: 3.5,
    o15: 1.3, u15: 3.5, o25: 1.9, u25: 1.9, o35: 3.6, u35: 1.28 } };
  const mkts = new Set(w._pwBuildEdges(prices, odds).map(e => e.mkt));
  assert.ok(mkts.has('ou15') && mkts.has('ou') && mkts.has('ou35'), 'O/U-Leiter unvollständig');
});

test('Edge-Board: ohne Pinnacle-Totals fällt O/U auf Softbook zurück (ᴾ-Tag)', () => {
  const w = win();
  const prices = { prices: { 'H-A': { homeName: 'H', awayName: 'A', homeId: 'h', awayId: 'a',
    hw: 0.5, dr: 0.3, aw: 0.3, vol: 50000, poly_o25: 0.45, poly_u25: 0.55 } } };
  const odds = { 'H-A': { hw: 2.0, dr: 3.5, aw: 3.5, public_o25: 1.9, public_u25: 1.9 } };
  const ou = w._pwBuildEdges(prices, odds).find(e => e.mkt === 'ou' && e.side === 'over');
  assert.ok(ou && /ᴾ/.test(ou.ticket), 'Softbook-Fair muss als ᴾ markiert sein');
  assert.equal(ou.fairSrc, 'public');
});

// Unter-Reiter (19.07.2026, Lucas: „besser aufteilen") — jede Ansicht zeigt nur ihr Thema.
import { JSDOM as _JSDOM } from 'jsdom';
async function renderView(view, filter) {
  const files = {
    'mls-data.json': { groups: {} },
    'mls_poly_prices.json': { prices: { 'H-A': { homeName: 'H', awayName: 'A', hw: 0.5, dr: 0.3, aw: 0.3, vol: 50000 } } },
    'mls_poly_wallets.json': { topPositionsAll: [{ wallet: '0xa', usd: 5000, side: 'home', pick: 'H', key: 'H-A', match: 'H – A' }],
      bigTradesAll: [{ wallet: '0xb', side: 'home', pick: 'H', usd: 9000, price: 0.5, action: 'BUY', ts: new Date().toISOString(), match: 'H – A', key: 'H-A' }],
      clustersAll: [], updatedAt: new Date().toISOString() },
    'mls-odds-history.json': {},
    'mls_poly_smartmoney.json': { matches: { 'H-A': { home: 'H', away: 'A', totalUsd: 50000, hoursToKickoff: 5,
      outcomes: { home: { usd: 30000, share: 0.6, topHolderShare: 0.55, holders: 40 }, away: { usd: 20000, share: 0.4, topHolderShare: 0.8, holders: 30 } } } } },
    'mls_poly_wallet_ledger.json': { updatedAt: new Date().toISOString(), positions: {
      a: { wallet: '0xd', usd: 8000, pick: 'H', firstAvgPrice: 0.42, avgPrice: 0.5 },
      b: { wallet: '0xe', usd: 3000, pick: 'A', firstAvgPrice: 0.6 },
      c: { wallet: '0xf', usd: 2000, pick: 'X', firstAvgPrice: 0.5 } } },
  };
  const dom = new _JSDOM('<!DOCTYPE html><body><div id="polyWalletsPanel"></div></body>',
    { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window;
  w.fetch = (url) => { const u = String(url); let b = null; for (const [f, d] of Object.entries(files)) if (u.includes(f)) { b = d; break; } return Promise.resolve({ ok: b != null, json: () => Promise.resolve(b) }); };
  w.eval(readFileSync(PW, 'utf8'));
  w.initPolyWallets();
  await new Promise(r => setTimeout(r, 30));
  if (filter) w._pwSetSportFilter(filter);   // 25.07.2026: Datensatz-Boards nur unter passendem Sport-Filter
  w._pwSetView(view);
  return w.document.getElementById('polyWalletsPanel').innerHTML;
}

// 25.07.2026 (Lucas): Smart-Money-Tab entfernt — die MLS-Konzentration lebt jetzt im Whales-Tab,
// aber NUR unter dem ⚽ Fußball-Filter (Datensatz-Detail). Default „Alle" bleibt rein global.
test('Whales unter ⚽ Fußball zeigt die Datensatz-Smart-Money-Konzentration', async () => {
  const html = await renderView('whales', 'Fußball');
  assert.match(html, /Smart-Money-Konzentration/);
});

test('Reiter Whales: Leaderboard, aber keine Smart-Money-Konzentration', async () => {
  const html = await renderView('whales');
  assert.match(html, /🏦 Größte Whales/);   // 25.07.2026: globaler Leaderboard (MLS-Board entfernt, war doppelt)
  assert.doesNotMatch(html, /Smart-Money-Konzentration/);
});

test('Reiter Chancen (Default): weder Konzentration noch Leaderboard (die sind eigene Reiter)', async () => {
  const html = await renderView('edge');
  assert.doesNotMatch(html, /Smart-Money-Konzentration/);
  assert.doesNotMatch(html, /Whale-Leaderboard/);
});

test('Unter-Reiter existieren (Smart-Money-Tab 25.07. entfernt)', async () => {
  const html = await renderView('edge');
  for (const t of ['🔥 Heute wetten', '💰 Großes Geld', '📈 Bewegung', '🆕 Neu', '🎯 Chancen', '🐋 Whales']) assert.match(html, new RegExp(t));
  assert.doesNotMatch(html, /💡 Smart-Money/, 'Smart-Money-Tab wurde entfernt');
});

// 26.07.2026 (Lucas: „No vs Yes als Spielname ist sinnlos"). _pwEventLabel: Team-Namen wenn echt,
// sonst lesbarer Name aus dem Slug statt der generischen Ja/Nein-Ausgänge.
test('_pwEventLabel: echte Team-Namen bleiben „A vs B"', () => {
  const html = win()._pwEventLabel('x', ['Inter Miami CF', 'CF Montréal'], 'MLS');
  assert.match(html, /Inter Miami CF/);
  assert.match(html, /CF Montréal/);
  assert.match(html, /vs/);
});

test('_pwEventLabel: Ja/Nein-Markt → Name aus Slug, kein „No vs Yes"', () => {
  const w = win();
  assert.equal(w._pwEventLabel('mls-mim-mia-2026-07-25', ['No', 'Yes'], 'MLS'), 'MIM MIA');
  assert.equal(w._pwEventLabel('ucl-agf-lep-2026-07-21-exact-score', ['Yes', 'No'], 'UCL'),
               'AGF LEP Exact Score');
  const out = w._pwEventLabel('mlb-pit-nyy-2026-07-20-player-props', ['No', 'Yes'], 'MLB');
  assert.doesNotMatch(out, /No|Yes/);
  assert.match(out, /PIT NYY/);
});

// 27.07.2026 (Lucas: „was kommt oder live — fertige Spiele raus"): das Momentum-Board darf keine
// Spiele mehr zeigen, deren Anpfiff klar vorbei ist (Walkover/Alt-Spiele hingen bis 4 Tage).
test('_pwMomentum: fertige Spiele (Anpfiff >4h vorbei) raus, Zukunft/live bleibt', () => {
  const w = win();
  const hrsAgo = h => new Date(Date.now() - h * 3.6e6).toISOString();
  const hist = {
    'future-match': [
      { ts: hrsAgo(2),   p: { 'TeamZukunft': 0.40, 'GegnerZ': 0.60 }, v: 50000, htk: 4, league: 'soccer' },
      { ts: hrsAgo(0.1), p: { 'TeamZukunft': 0.55, 'GegnerZ': 0.45 }, v: 50000, htk: 2, league: 'soccer' },
    ],
    'past-match': [
      { ts: hrsAgo(8), p: { 'TeamVorbei': 0.40, 'GegnerV': 0.60 }, v: 50000, htk: 1, league: 'soccer' },
      { ts: hrsAgo(6), p: { 'TeamVorbei': 0.55, 'GegnerV': 0.45 }, v: 50000, htk: 0, league: 'soccer' },
    ],
  };
  const html = w._pwMomentum(hist);
  assert.match(html, /TeamZukunft/, 'kommendes/laufendes Spiel muss bleiben');
  assert.doesNotMatch(html, /TeamVorbei/, 'fertiges Spiel (Anpfiff >4h vorbei) darf NICHT erscheinen');
});
