// tests/frontend/poly-terminal-konvergenz.test.mjs — 16.09.2026
//
// Lucas, zu drei offenen Trades ~5 % im Minus: „Die wurden getriggert, weil Pinnacle bewegt und
// Poly scheinbar nicht. Können wir rückwirkend auslesen, ob Poly überhaupt zu unseren Gunsten
// anpasst, wenn sowas passiert? Weil eventuell machen die das nie und ist nur unsere Theorie."
//
// Die Annahme trägt jeden dieser Trades. Gemessen wird sie in `poly_konvergenz.py`; hier steht
// nur, dass die Fläche das Urteil des Produzenten ZEIGT — in beide Richtungen, und ohne die
// Schwelle nachzubauen.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const PW = new URL('../../poly-wallets.js', import.meta.url);
const RAWJSON = new URL('../../raw-json.js', import.meta.url);

function win() {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="polyWalletsPanel"></div></body>',
    { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  w.eval(readFileSync(RAWJSON, 'utf8'));
  w.eval(readFileSync(PW, 'utf8'));
  return w;
}
const ROW = { key: 'k1', match: 'A vs B', side: 'Heim', conv: 8, reasons: [],
              price: 0.55, vol: 120000, htk: 3, league: 'Serie A' };
const MARKT = { totalUsd: 120000, league: 'Serie A', prices: { Heim: 0.55 },
                shares: { Heim: 0.7 }, whales: [] };

function konv(over) {
  return Object.assign({
    dataset: 'liga', schwellePP: 4.0, nettoPP: 3.37, belegt: true, urteil: 'zieht nach',
    grund: 'Poly laeuft bis zum Anpfiff +4.87 pp mit',
    arme: { dafuer: { n: 171, spiele: 105, polyPP: 4.87, polyUgPP: 3.84, gegenUnsPct: 36.0 } },
  }, over || {});
}

test('der belegte Fall steht als Argument DAFÜR, mit Untergrenze und Spielzahl', () => {
  const w = win();
  w._pwTestSetCache({ broadLive: { k1: MARKT }, konv: konv() });
  const html = w._pwTermUrteil(ROW);
  assert.match(html, /Poly zieht der Pinnacle-Kante nach/);
  assert.match(html, /\+4\.9pp mit/, 'die Bewegung selbst fehlt');
  assert.match(html, /Untergrenze \+3\.8pp/, 'ohne Schranke ist es ein Punktschätzer');
  assert.match(html, /105 Spiele/, 'die Basis gehört an die Zahl');
});

test('dass jeder dritte Trade trotzdem gegen uns läuft, steht daneben', () => {
  // Genau Lucas' Ausgangslage: drei offene Positionen im Minus. Ein Schnitt von +4,9pp ohne
  // diese Zahl liest sich wie ein Versprechen.
  const w = win();
  w._pwTestSetCache({ broadLive: { k1: MARKT }, konv: konv() });
  assert.match(w._pwTermUrteil(ROW), /36% laufen trotzdem gegen uns/);
});

test('der halbe Spread wird abgezogen — brutto ist keine Geldaussage', () => {
  const w = win();
  w._pwTestSetCache({ broadLive: { k1: MARKT }, konv: konv() });
  assert.match(w._pwTermUrteil(ROW), /netto nach halbem Spread \+3\.4pp/);
});

test('ein NICHT belegter Befund ist ein Gegenargument, kein Schweigen', () => {
  // Die Fläche darf die Annahme nicht nur dann erwähnen, wenn sie ihr passt.
  const w = win();
  w._pwTestSetCache({ broadLive: { k1: MARKT }, konv: konv({
    belegt: false, urteil: 'Kontrolle unsauber',
    grund: 'die Kontrollgruppe bewegt sich um +0.61 pp — gemessen wird dann ein Drift der Reihe' }) });
  const html = w._pwTermUrteil(ROW);
  assert.match(html, /NICHT belegt/);
  assert.match(html, /Kontrollgruppe/, 'der Grund des Produzenten gehört dazu');
  assert.ok(!/Poly zieht der Pinnacle-Kante nach/.test(html));
});

test('ohne Artefakt wird nichts behauptet', () => {
  const w = win();
  w._pwTestSetCache({ broadLive: { k1: MARKT } });
  const html = w._pwTermUrteil(ROW);
  assert.ok(!/Pinnacle-Kante nach/.test(html));
  assert.ok(!/NICHT belegt/.test(html));
});

test('ohne Spiele im Arm wird nichts gezeigt', () => {
  const w = win();
  w._pwTestSetCache({ broadLive: { k1: MARKT },
    konv: konv({ arme: { dafuer: { n: 0, spiele: 0, polyPP: null, polyUgPP: null } } }) });
  assert.ok(!/Pinnacle-Kante/.test(w._pwTermUrteil(ROW)));
});

test('die Fläche baut die Schwelle nicht nach, sie liest sie', () => {
  const w = win();
  w._pwTestSetCache({ broadLive: { k1: MARKT }, konv: konv({ schwellePP: 6.5 }) });
  assert.match(w._pwTermUrteil(ROW), /Kante ab 6\.5pp/);
});
