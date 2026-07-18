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
  assert.ok(MIN_CONV <= 5,
    `Conviction ${MIN_CONV} erreicht kein ABWÄGEN (Maximum real: 5) → Filter ist ein No-Op`);
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
