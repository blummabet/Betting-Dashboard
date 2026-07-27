// tests/frontend/poly-betting-filter.test.mjs
//
// 18.07.2026 — Was landet im manuellen Wett-Interface (Polymarket Betting)?
//
// Vorgeschichte: der Tab filterte hart auf `verdict === 'BET'`. Bei dünnen Märkten (MLS)
// entstehen aber oft ausschließlich ABWÄGEN-Picks — der Tab war leer, obwohl Picks da waren,
// und es sah nach einem Bug aus. Die Gegenrichtung („alles durchlassen") ist genauso falsch:
// dann stehen schwach begründete Picks im Wett-Interface, als wären sie Empfehlungen.
//
// Lucas' Regel: „kann bei BET bleiben und ABWÄGEN mit hoher Conviction".
// Diese Tests halten genau diese Grenze fest — beide Richtungen.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const POLY = new URL('../../polymarket-tab.js', import.meta.url);

// `const` auf Top-Level landet beim eval NICHT auf window — Schwelle aus der Quelle lesen.
const MIN_CONV = Number(
  readFileSync(POLY, 'utf8').match(/WM_POLY_ABWAEGEN_MIN_CONV\s*=\s*(\d+)/)[1]);

function loadPoly(wmPicks) {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="polymarketPanel"></div></body>', {
    url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true,
  });
  const { window } = dom;
  window.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  window.localStorage.clear();
  window.WM2026_PICKS_FOR_POLY = wmPicks || [];
  window.eval(readFileSync(POLY, 'utf8'));
  return window;
}

const pick = (over) => ({
  pickKey: 'X', home: 'Inter Miami', away: 'Orlando City',
  date: '2026-07-23', market: 'Heimsieg', odds: 2.1, modelOdds: 1.9,
  verdict: 'BET', convictionScore: 8, edgePP: 4, ...over,
});

test('BET kommt immer durch — auch mit niedriger Conviction', () => {
  const w = loadPoly();
  assert.equal(w._polyPickEligible('BET', 2), true);
  assert.equal(w._polyPickEligible('BET', null), true);
});

test('ABWÄGEN nur ab hoher Conviction', () => {
  const w = loadPoly();
  const min = MIN_CONV;
  assert.ok(min >= 5, 'Schwelle zu niedrig — praktisch jedes ABWÄGEN käme durch');
  assert.equal(w._polyPickEligible('ABWÄGEN', min), true, 'Schwelle selbst muss zählen');
  assert.equal(w._polyPickEligible('ABWÄGEN', min + 1), true);
  assert.equal(w._polyPickEligible('ABWÄGEN', min - 1), false, 'schwaches ABWÄGEN durchgelassen');
  assert.equal(w._polyPickEligible('ABWÄGEN', 3), false);
});

// Der eigentliche Fallstrick: eine Schwelle, die NIE erreicht wird, sieht aus wie ein Filter,
// verhält sich aber wie das alte BET-only — der Tab bliebe leer und niemand merkt warum.
// Über alle bisher gestempelten Picks liegt das ABWÄGEN-Maximum bei 5.
test('Schwelle ist erreichbar — kein getarntes BET-only', () => {
  // 27.07.2026: früher „Maximum real: 5" — überholt. MLS-ABWÄGEN erreicht real bis 7
  // (Conviction ist vom Verdict entkoppelt). Schwelle 6 lässt die starken ABWÄGEN (6–7) durch.
  assert.ok(MIN_CONV <= 7,
    `Conviction ${MIN_CONV} über dem real erreichbaren ABWÄGEN-Maximum (~7) → Filter wäre ein No-Op`);
});

test('ABWÄGEN ohne Conviction-Score bleibt draußen (kein stiller Durchrutscher)', () => {
  const w = loadPoly();
  assert.equal(w._polyPickEligible('ABWÄGEN', null), false);
  assert.equal(w._polyPickEligible('ABWÄGEN', undefined), false);
});

test('NOBET/SKIP/BEOBACHTEN sind nie wettbar', () => {
  const w = loadPoly();
  for (const v of ['NOBET', 'SKIP', 'BEOBACHTEN', '', null]) {
    assert.equal(w._polyPickEligible(v, 10), false, `${v} wurde wettbar`);
  }
});

test('getWmPolyPicks wendet die Regel echt an (nicht nur der Helper)', () => {
  const w = loadPoly([
    pick({ verdict: 'BET', convictionScore: 4, market: 'Heimsieg' }),
    pick({ verdict: 'ABWÄGEN', convictionScore: 9, market: 'Auswärtssieg' }),
    pick({ verdict: 'ABWÄGEN', convictionScore: 3, market: 'Unentschieden' }),
  ]);
  const märkte = w.getWmPolyPicks('').map(p => p.market).sort();
  assert.deepEqual(märkte, ['Auswärtssieg', 'Heimsieg'],
    'Filter greift im Extraktor nicht — schwaches ABWÄGEN kam durch oder BET fehlte');
});

test('leerer Datumsfilter zeigt alle Tage (Default des Tabs)', () => {
  const w = loadPoly([
    pick({ date: '2026-07-23', market: 'Heimsieg' }),
    pick({ date: '2026-08-02', market: 'Auswärtssieg' }),
  ]);
  assert.equal(w.getWmPolyPicks('').length, 2, "'' muss ALLE Tage zeigen");
  assert.equal(w.getWmPolyPicks(null).length, 2, 'null muss ALLE Tage zeigen');
  assert.equal(w.getWmPolyPicks('23.07.2026').length, 1, 'Tagesfilter filtert nicht mehr');
});

test('Tages-Chips: „Alle" + ein Chip je Tag, mit Pick-Zähler', () => {
  const w = loadPoly([pick({ date: '2026-07-23' })]);
  const html = w._renderPolyDateChips('');
  assert.ok(html.includes('id="polyDateChips"'), 'Chip-Container fehlt (polyChangeDate findet ihn nicht)');
  assert.ok(html.includes(">Alle"), '„Alle"-Chip fehlt');
  assert.ok(html.includes("polyChangeDate('')"), '„Alle" setzt den Filter nicht zurück');
  assert.ok(html.includes('data-polydate="23.07.2026"'), 'Tages-Chip für 23.07. fehlt');
});

// 25.07.2026 (Lucas: „Betting-Tab startet erst 31.7, aber dieses WE ist MLS-Runde"). MLS fehlte in
// POLY_LEAGUES → MLS-Fixtures fielen aus den Datums-Chips. Regression-Guard: MLS-Datum muss rein,
// eine Nicht-Poly-Liga bleibt draußen. Datum weit in der Zukunft, damit es unabhängig vom CI-Datum
// den „ab heute"-Filter passiert.
test('MLS-Fixtures fließen in die Datums-Chips (POLY_LEAGUES enthält MLS)', () => {
  const w = loadPoly();
  w.LEAGUES = {
    MLS: { fixtures: [{ date: '25.07.2099', home: 1614, away: 9568 }] },
    BRA: { fixtures: [{ date: '26.07.2099', home: 1, away: 2 }] },   // nicht in POLY_LEAGUES
  };
  const dates = w._getAvailableDates();
  assert.ok(dates.includes('25.07.2099'), 'MLS-Datum fehlt in den Chips — MLS nicht in POLY_LEAGUES?');
  assert.ok(!dates.includes('26.07.2099'), 'Nicht-Poly-Liga (BRA) darf nicht auftauchen');
});

// 25.07.2026 (Lucas: „seh nichts im Betting-Tab") — MLS/Liga-Picks aus NATIONAL_PICKS_FOR_POLY
// laufen jetzt durch dieselbe Eligibilitäts-Schwelle wie WM. Schwelle bleibt (Lucas' Wahl):
// starkes ABWÄGEN erscheint, schwaches nicht.
test('MLS-Picks aus NATIONAL_PICKS_FOR_POLY: nur ab Conviction-Schwelle', () => {
  const w = loadPoly();
  w.NATIONAL_PICKS_FOR_POLY = [
    { league: 'MLS', home: 'Inter Miami', away: 'Orlando', homeId: 1, awayId: 2, date: '2099-07-25',
      market: 'Heimsieg', odds: 1.9, modelOdds: 1.8, verdict: 'ABWÄGEN', convictionScore: MIN_CONV + 1, edgePP: 3 },
    { league: 'MLS', home: 'CF Montreal', away: 'Chicago', homeId: 3, awayId: 4, date: '2099-07-25',
      market: 'Auswärtssieg', odds: 3.0, modelOdds: 2.8, verdict: 'ABWÄGEN', convictionScore: 2, edgePP: 1 },
  ];
  const picks = w.getMlsLigaPolyPicks('');
  const teams = picks.map(p => p.home);
  assert.deepEqual(teams, ['Inter Miami'], 'nur das starke ABWÄGEN (≥Schwelle) darf erscheinen');
  assert.equal(picks[0].league, 'MLS');
  assert.equal(picks[0].leagueFlag, '🇺🇸');
});

test('_collectAllPolyPicks bündelt WM + MLS + Club (MLS nicht mehr verloren)', () => {
  const w = loadPoly([pick({ verdict: 'BET', market: 'Heimsieg', home: 'Brasilien', away: 'Peru' })]);
  w.NATIONAL_PICKS_FOR_POLY = [
    { league: 'MLS', home: 'LA Galaxy', away: 'Austin', homeId: 5, awayId: 6, date: '2099-08-01',
      market: 'Heimsieg', odds: 1.8, modelOdds: 1.7, verdict: 'BET', convictionScore: 7, edgePP: 4 },
  ];
  const all = w._collectAllPolyPicks('');
  assert.ok(all.some(p => p.home === 'LA Galaxy'), 'MLS-Pick fehlt in der Sammelstelle');
  assert.ok(all.some(p => p.home === 'Brasilien'), 'WM-Pick fehlt in der Sammelstelle');
});

// 27.07.2026 (Lucas: „Bet-Vorschlag ohne Card-Pick / alte Datums-Chips"): der Club-Builder
// (_loadNationalPolyPicksAsync) listete Picks für schon gespielte Spiele — der Kickoff-Filter
// fehlte dort (nur _extractWmPicksForDate hatte ihn).
test('_wmKickoffPassed: Vergangenheit vorbei, Zukunft offen', () => {
  const w = loadPoly();
  assert.equal(w._wmKickoffPassed({ date: '2020-01-01' }), true);
  assert.equal(w._wmKickoffPassed({ date: '2999-01-01' }), false);
  assert.equal(w._wmKickoffPassed({ kickoff: '2020-01-01T00:00:00Z' }), true);
});

test('Club-Builder listet vergangene Spiele NICHT als Wette', async () => {
  const w = loadPoly();
  const data = { groups: { MLS: { fixtures: [
    { home: 'A', away: 'B', homeName: 'Team A', awayName: 'Team B', date: '2020-01-01' },  // vergangen
    { home: 'C', away: 'D', homeName: 'Team C', awayName: 'Team D', date: '2999-01-01' },  // Zukunft
  ] } }, picks: {
    'MLS-1-A-B': [{ verdict: 'BET', market: 'Heimsieg', convictionScore: 8 }],
    'MLS-1-C-D': [{ verdict: 'BET', market: 'Heimsieg', convictionScore: 8 }],
  } };
  w.fetch = (u) => Promise.resolve({ ok: String(u).includes('mls-data'), json: () => Promise.resolve(data) });
  await w._loadNationalPolyPicksAsync();
  const teams = (w.NATIONAL_PICKS_FOR_POLY || []).map(p => p.home);
  assert.ok(teams.includes('Team C'), 'Zukunftsspiel muss gelistet sein');
  assert.ok(!teams.includes('Team A'), 'vergangenes Spiel darf NICHT als Wette erscheinen');
});

// 27.07.2026 (Lucas): im Betting-Tab klar sichtbar machen, ob ein Pick BET oder ABWÄGEN ist.
test('_verdictTag zeigt BET / ABWÄGEN (echter Verdict, Fallback conf)', () => {
  const w = loadPoly();
  assert.match(w._verdictTag({ verdict: 'BET' }), /BET/);
  assert.match(w._verdictTag({ verdict: 'ABWÄGEN' }), /ABWÄGEN/);
  assert.match(w._verdictTag({ conf: 'high' }), /BET/);         // Fallback wenn verdict fehlt
  assert.match(w._verdictTag({ conf: 'medium' }), /ABWÄGEN/);
  assert.equal(w._verdictTag({ conf: 'low' }), '');
});

test('ABWÄGEN-Schwelle steht auf 6 (gute Conviction)', () => {
  const w = loadPoly();
  assert.equal(w._polyPickEligible('ABWÄGEN', 6), true);
  assert.equal(w._polyPickEligible('ABWÄGEN', 5), false);
  assert.equal(w._polyPickEligible('BET', 2), true);
});
