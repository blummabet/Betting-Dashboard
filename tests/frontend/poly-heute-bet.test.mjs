// tests/frontend/poly-heute-bet.test.mjs
// 21.08.2026 (Lucas): „Heute"-Bet direkt auslösen wo möglich. Kernrisiko = die Seite↔Pick-Markt-
// Zuordnung (_heuteSideMatches) — falsches Mapping = falsche Geld-Wette. Diese Tests pinnen sie fest.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const VERDICT = new URL('../../pick-verdict.js', import.meta.url);
const POLY    = new URL('../../polymarket-tab.js', import.meta.url);

function loadPoly() {
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const { window } = dom;
  window.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  window.localStorage.clear();
  window.eval(readFileSync(VERDICT, 'utf8'));
  window.eval(readFileSync(POLY, 'utf8'));
  return window;
}

test('_heuteSideMatches: Heimsieg <-> Heim-Team', () => {
  const w = loadPoly();
  const p = { market:'Heimsieg', home:'Real Betis', away:'Real Sociedad' };
  assert.equal(w._heuteSideMatches('real betis', p), true);
  assert.equal(w._heuteSideMatches('betis', p), true);
  assert.equal(w._heuteSideMatches('real sociedad', p), false);
});

test('_heuteSideMatches: Auswaertssieg / Unentschieden', () => {
  const w = loadPoly();
  const p = { market:'Auswärtssieg', home:'Arsenal', away:'Coventry City' };
  assert.equal(w._heuteSideMatches('coventry city', p), true);
  assert.equal(w._heuteSideMatches('coventry', p), true);
  const d = { market:'Unentschieden', home:'A', away:'B' };
  assert.equal(w._heuteSideMatches('draw', d), true);
  assert.equal(w._heuteSideMatches('the draw', d), true);
  assert.equal(w._heuteSideMatches('arsenal', d), false);
});

test('_heuteSideMatches: Over/Under/BTTS', () => {
  const w = loadPoly();
  assert.equal(w._heuteSideMatches('over 2.5', { market:'Over 2.5 Tore', home:'A', away:'B' }), true);
  assert.equal(w._heuteSideMatches('under 2.5', { market:'Over 2.5 Tore', home:'A', away:'B' }), false);
  assert.equal(w._heuteSideMatches('under 2.5', { market:'Under 2.5 Tore', home:'A', away:'B' }), true);
  assert.equal(w._heuteSideMatches('yes', { market:'Beide Teams treffen', home:'A', away:'B' }), true);
});

test('_polyHeuteBetOrder: ohne Preis-Cache faellt es auf die Token-Order zurueck', () => {
  // 24.08.2026: Frueher gab es hier null (= Link). Der Card-Pick-Weg braucht den Preis-Cache, der
  // Direktweg nicht — polyKey+side reichen, den Rest loest der Runner ueber den Slug auf.
  const w = loadPoly();
  const r = { key:'some-slug', side:'Real Betis', price:0.6, conv:8 };
  const o = w._polyHeuteBetOrder(r, [{ home:'Real Betis', away:'Real Sociedad', market:'Heimsieg', odds:2.0 }]);
  assert.ok(o && o.polyKey === 'some-slug' && o.side === 'Real Betis');
});

test('_polyHeuteBetOrder: null nur ohne Key/Seite — sonst immer eine Order', () => {
  const w = loadPoly();
  assert.ok(w._polyHeuteBetOrder({ key:'x', side:'y' }, []), 'Key+Seite reichen');
  assert.equal(w._polyHeuteBetOrder({ key:'x' }, []), null, 'ohne Seite keine Order');
  assert.equal(w._polyHeuteBetOrder({ side:'y' }, []), null, 'ohne Key keine Order');
  assert.equal(w._polyHeuteBetOrder(null, []), null);
});

// ── 24.08.2026 (Lucas: „kriegen wir hin, dass ich von dort gleich die Wette auslöse?") ──────────
// Der Card-Pick-Umweg deckte real ~7% der Plays ab. Jetzt trägt der Play die CLOB-Token-ID selbst,
// damit ist JEDE Sportart direkt setzbar — ausser den im Papier-Track negativen (US-Sport/Kampf).

function loadPolyWithSport(cat) {
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const { window } = dom;
  window.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  window.localStorage.clear();
  // poly-wallets.js wird hier nicht geladen -> Sport-Kategorie stubben (so wie sie real liefert).
  window._pwSportCategory = () => cat;
  window.eval(readFileSync(VERDICT, 'utf8'));
  window.eval(readFileSync(POLY, 'utf8'));
  return window;
}

const PLAY = {
  key: 'atp-alcaraz-sinner-2026-08-24', side: 'Carlos Alcaraz', price: 0.58, conv: 8,
  match: 'Carlos Alcaraz vs Jannik Sinner', league: 'TENNIS', sport: 'Tennis',
  token: '71321045679252212594626385532706912750332728571942532289631379312455583992563',
};

test('_polyHeuteTokenOrder: baut eine vollstaendige Direkt-Order aus dem Play', () => {
  const w = loadPolyWithSport('Tennis');
  const o = w._polyHeuteTokenOrder(PLAY);
  assert.ok(o, 'Order erwartet');
  assert.equal(o.tokenId, PLAY.token);
  assert.equal(o.polyKey, PLAY.key);
  assert.equal(o.side, 'Carlos Alcaraz');
  assert.equal(o.market, 'Carlos Alcaraz');       // der Ausgang IST der Markt
  assert.equal(o.home, 'Carlos Alcaraz');
  assert.equal(o.away, 'Jannik Sinner');
  assert.equal(o.polyPrice, 0.58);
  assert.equal(o.conviction, 8);
  assert.equal(o.edge, null);                     // kein Pinnacle-Anker -> kein erfundener Edge
});

test('_polyHeuteTokenOrder: ohne Token trotzdem eine Order (Placer löst über den Slug auf)', () => {
  // 24.08.2026 (Lucas: „haben nur einen Öffnen-Link"): der Button hing am Token, den poly_money_broad
  // erst ab dem ersten Scan mit dem neuen Code schreibt — dazwischen war JEDER Play tokenlos. Der
  // Token ist jetzt ein Beschleuniger: fehlt er, trägt die Order polyKey+side und der Runner löst auf.
  const w = loadPolyWithSport('Tennis');
  const { token, ...ohne } = PLAY;
  const o = w._polyHeuteTokenOrder(ohne);
  assert.ok(o, 'Order auch ohne Token');
  assert.equal(o.tokenId, null, 'tokenId explizit null, nicht erfunden');
  assert.equal(o.polyKey, PLAY.key);
  assert.equal(o.side, PLAY.side);
});

test('_polyHeuteTokenOrder: US-Sport und Kampfsport bleiben Link', () => {
  // Papier-Track ueber 500 Plays: MLB -28%, NFL -49%, UFC -31% ROI -> kein Direkt-Button.
  assert.equal(loadPolyWithSport('US-Sport')._polyHeuteTokenOrder(PLAY), null);
  assert.equal(loadPolyWithSport('Kampfsport')._polyHeuteTokenOrder(PLAY), null);
  assert.ok(loadPolyWithSport('E-Sport')._polyHeuteTokenOrder(PLAY), 'E-Sport ist bewusst erlaubt');
  assert.ok(loadPolyWithSport('Fußball')._polyHeuteTokenOrder(PLAY), 'Fussball erlaubt');
});

test('_polyHeuteBetOrder: faellt ohne Card-Pick auf die Token-Order zurueck', () => {
  const w = loadPolyWithSport('Tennis');
  const o = w._polyHeuteBetOrder(PLAY, []);       // keine Picks geladen
  assert.ok(o && o.tokenId === PLAY.token, 'Token-Order statt null');
});

test('_polyHeuteTokenOrder: Label ohne "vs" -> home traegt das Label, away leer', () => {
  const w = loadPolyWithSport('E-Sport');
  const o = w._polyHeuteTokenOrder({ ...PLAY, match: 'Winner of Group A' });
  assert.equal(o.home, 'Winner of Group A');
  assert.equal(o.away, '');
});
