// tests/frontend/results-stats-scope.test.mjs — Statistik-Umfang (27.08.2026, Lucas)
// „Die Spiele aus den kleinen Ligen im alten System will ich auf keinen Fall drauf haben,
//  das haut uns komplett die Statistik zusammen" + „die Top-5 erst in der neuen Saison".
// Die Liste lebt in stats_scope.json — dieselbe Datei liest der Python-Guard.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';

const ROOT = new URL('../../', import.meta.url);
const SRC = readFileSync(new URL('results-v2.js', ROOT), 'utf8');
const SCOPE = JSON.parse(readFileSync(new URL('stats_scope.json', ROOT), 'utf8')).leagues;

// _v2InScope aus der Quelle ziehen und isoliert ausführen — kein DOM nötig.
function loadInScope() {
  const fn = SRC.match(/function _v2InScope\(league, dateIso, scope\) \{[\s\S]*?\n\}/);
  assert.ok(fn, '_v2InScope nicht gefunden');
  // eslint-disable-next-line no-new-func
  return new Function('_v2Scope', fn[0] + '; return _v2InScope;')(null);
}
const inScope = loadInScope();

test('Top-5 ab Saisonstart zählen', () => {
  assert.equal(inScope('ESP', '2026-08-15', SCOPE), true);
  assert.equal(inScope('ENG', '2026-08-22', SCOPE), true);
});

test('dieselbe Liga vor dem Saisonstart zählt NICHT', () => {
  assert.equal(inScope('ESP', '2026-05-17', SCOPE), false);
  assert.equal(inScope('ITA', '2026-05-24', SCOPE), false);
});

test('die alten Breiten-Ligen zählen nie', () => {
  for (const lg of ['HUN', 'POL', 'CRO', 'SCO', 'AUT', 'SUI', 'TUR', 'NED', 'BEL', 'POR', 'NED2', 'AUT2']) {
    assert.equal(inScope(lg, '2026-08-22', SCOPE), false, lg);
  }
});

test('MLS hat einen eigenen Saisonstart (läuft Februar–Oktober)', () => {
  assert.equal(inScope('MLS', '2026-04-01', SCOPE), true);
  assert.equal(inScope('MLS', '2026-01-10', SCOPE), false);
});

test('unbekannte Liga zählt nicht (fail-closed)', () => {
  assert.equal(inScope('NEUELIGA', '2026-08-22', SCOPE), false);
});

test('ohne geladenen Umfang zählt gar nichts', () => {
  assert.equal(inScope('ESP', '2026-08-22', null), false);
  assert.equal(inScope('ESP', '2026-08-22', undefined), false);
});

test('Müll wirft nicht', () => {
  for (const [lg, d] of [[null, '2026-08-22'], ['ESP', null], ['ESP', 'kaputt'], ['', ''], [5, 7]]) {
    assert.equal(inScope(lg, d, SCOPE), false);
  }
});

test('jede Sammelstelle im Tab filtert — sonst leckt eine davon', () => {
  // Drei Pfade führen Einträge zusammen: localStorage-Vergangenheit, picks_history-Fallback
  // und der „Buffer leer"-Notnagel. Fehlt an einem der Filter, sind die alten Ligen wieder da.
  const treffer = SRC.match(/_v2InScope\(/g) || [];
  assert.ok(treffer.length >= 4, `nur ${treffer.length} Aufrufe — eine Sammelstelle ungefiltert?`);
});

test('fehlender Umfang wird benannt, nicht als „keine Picks" getarnt', () => {
  assert.match(SRC, /_v2ScopeMissing/);
  assert.match(SRC, /stats_scope\.json.*nicht geladen|nicht geladen.*gez/s);
});
