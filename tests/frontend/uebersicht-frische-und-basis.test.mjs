// tests/frontend/uebersicht-frische-und-basis.test.mjs — 03.09.2026
//
// Lucas: „Mal bitte kleinen Checkup der Übersicht auf inhalt, logik, fehler, verbesserungen".
// Zwei der drei Befunde stecken hier:
//
//  1. Oben stand „älteste Quelle Serien vor 64 Min", während dieselbe Seite unten „letzte
//     Erfassung vor 2 h" meldete. `_mdQuellenAlter` prüfte 8 von 13 geladenen Datensätzen, und
//     der Polymarket-LIVE-Feed hat gar kein Feld in `_md.data` — er kommt über
//     `_pwCache.broadLiveNow`. Der Kommentar in `_head()` verspricht ausdrücklich das Gegenteil.
//  2. Die Puls-Kachel zeigte „n30" neben „78% Treffer 21–6" — einer Quote auf 27. `n` ist die
//     Fenstergröße, `winPct` rechnet auf wins+losses; Picks mit einem Ergebnis, das weder WIN
//     noch LOSS ist, fielen aus der Quote und blieben im angezeigten n.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';

const ROOT = new URL('../../', import.meta.url);
const JS = readFileSync(new URL('main-dashboard.js', ROOT), 'utf8');
// Beim Prüfen auf ABWESENHEIT nur echten Code ansehen: die Kommentare beschreiben absichtlich,
// was früher dastand.
const CODE = JS.replace(/^\s*\/\/.*$/gm, '');

function schneide(von, bis) {
  const a = JS.indexOf(von), b = JS.indexOf(bis);
  assert.ok(a > 0, 'Anker weg: ' + von);
  assert.ok(b > a, 'Anker weg: ' + bis);
  return JS.slice(a, b);
}

// ── 1. Frische ───────────────────────────────────────────────────────────────
test('die Frische-Liste kennt alle geladenen Datensätze', () => {
  // Die Ladezeile ist die Wahrheit darüber, was es gibt.
  const laden = (JS.split('\n').find(z => z.includes('_md.data = {')) || '').replace(/\s/g, '');
  const felder = [...laden.matchAll(/([a-zA-Z]+):a\[\d+\]/g)].map(m => m[1]);
  assert.ok(felder.length >= 12, 'Ladezeile nicht erkannt: ' + felder.length);
  const block = schneide('function _mdQuellenAlter', 'function _ageTxt');
  const fehlen = felder.filter(f => !new RegExp('d\\.' + f + '\\b').test(block));
  assert.deepStrictEqual(fehlen, [], 'Diese Quellen zählen nicht in die älteste Quelle mit: '
    + fehlen.join(', '));
});

test('der Poly-LIVE-Feed zählt mit, obwohl er kein Feld in _md.data hat', () => {
  const block = schneide('function _mdQuellenAlter', 'function _ageTxt');
  assert.match(block, /_pwLiveStaleMin/,
    'Genau der Feed, der sich unten selbst als 2 h alt meldet, fehlt oben wieder');
});

test('eine Quelle ohne lesbaren Zeitstempel gibt sich nicht als frisch aus', () => {
  const g = {};
  // eslint-disable-next-line no-new-func
  new Function('exp', schneide('function _ageMin', 'function _ageTxt') + '\nexp.f=_ageMin;')(g);
  for (const leer of [null, undefined, {}, { _meta: {} }, { generatedAt: 'kaputt' }]) {
    assert.strictEqual(g.f(leer), null, 'erfindet ein Alter für ' + JSON.stringify(leer));
  }
});

test('der Kopf wird nachgezogen, wenn der Live-Feed später landet', () => {
  // Ohne das bliebe die älteste Quelle auf dem Stand VOR dem Laden stehen — wieder zu optimistisch.
  assert.match(CODE, /function _mdRefreshAsof/, 'kein Nachziehen des Kopfes');
  assert.match(CODE, /id="md-asof"/, 'der Kopf hat keinen Anker zum Nachziehen');
  const füllen = schneide('function _mdFillLive', 'function _mdMoneyMapWide');
  assert.match(füllen, /_mdRefreshAsof\(\)/, 'nach dem Laden wird der Kopf nicht aktualisiert');
});

// ── 2. Jede Zahl trägt ihre Basis ────────────────────────────────────────────
test('die Puls-Kachel setzt kein n über eine Quote, die auf weniger rechnet', () => {
  const block = schneide('🎯 Cards<b>n', '_spark(d.series)');
  assert.match(block, /nGraded/, 'die gewertete Stichprobe steht nicht dabei');
  assert.match(block, /nClv/, 'die CLV-Stichprobe steht nicht dabei');
});

test('stimmen alle Basen überein, wird nichts Zusätzliches angezeigt', () => {
  // Die Zusätze sind an `!==` gekoppelt — sonst stünde bei sauberen Daten dreimal dieselbe Zahl.
  const block = schneide('🎯 Cards<b>n', '_spark(d.series)');
  assert.match(block, /d\.nGraded !== d\.n/);
  assert.match(block, /d\.nClv !== d\.n/);
});

// ── 3. Die Money-Map-Kachel behauptet nicht mehr drei Bücher für alle ────────
// 03.09.2026 (Lucas: „Was fehlt dann noch von Poly bei dem Betis - Real Madrid Beispiel?"):
// die Kachel schrieb „7 Konsens · BF × Poly × Pinn". Bei Betis–Real Madrid bestand die dritte
// Quelle aus $74 Umsatz und einem Preis, der 21pp neben dem Anker lag. Die Zeile selbst schreibt
// das korrekt mit (`polyGeld:false`, `nSources:2`) — die Kachel las es nur nie.
test('die Money-Map-Kachel zählt echte Drei-Bücher-Zeilen, nicht Verdikte', () => {
  // Auf CODE (ohne Kommentare) prüfen: der Kommentar zitiert absichtlich die alte Behauptung.
  const von = CODE.indexOf('var kon = mmRows.filter'), bis = CODE.indexOf("A.flow, 'moneymap')");
  assert.ok(von > 0 && bis > von, 'Anker weg');
  const block = CODE.slice(von, bis);
  assert.match(block, /nSources \|\| 0\) >= 3/, 'die Kachel prüft die echten Quellen nicht');
  assert.match(block, /polyGeld === false/, 'die Kachel kennt die Zeilen ohne Poly-Geld nicht');
  assert.ok(!/BF × Poly × Pinn/.test(block),
    'die pauschale Drei-Bücher-Behauptung ist zurück');
});

test('die Karte benennt einen Preis, der dem Anker widerspricht', () => {
  const MM = readFileSync(new URL('money-map.js', ROOT), 'utf8');
  assert.match(MM, /polyPreisWeit/, 'die Karte kennt die Abweichung nicht');
  assert.match(MM, /polyPreisAbwPP/, 'die Abweichung wird nicht beziffert');
  // Der Preis verschwindet NICHT — er bleibt sichtbar, nur ohne den Anschein von Zustimmung.
  assert.match(MM, /Preis \(dünn\)/, 'der normale Dünn-Preis-Fall ist weggefallen');
});
