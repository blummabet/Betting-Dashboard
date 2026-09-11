// tests/frontend/stake-radar-zeit-anteil.test.mjs — 11.09.2026
//
// Lucas, drei Fragen an einem Stück:
//   1) „was heisst der rote Punkt und die min daneben? ist das vergangen?"
//   2) „da is vieles alt mmn und sollten wir da ja eher auch anzeigen wieviel Geld und
//      wieviel % das sind vom Markt"
//   3) „sagen uns die anderen Auswertungen in den anderen Tabs etwas aus?"
//
// Alle drei sind Fragen an eine ANZEIGE, nicht an die Daten — und eine Anzeige, bei der der
// Leser raten muss, ist der Befund. Diese Tests halten die Antworten fest.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';

const ROOT = new URL('../../', import.meta.url);
const JS = readFileSync(new URL('stake-radar.js', ROOT), 'utf8');

function laden() {
  const box = { window: {}, document: { getElementById: () => null, head: { appendChild() {} }, createElement: () => ({}) }, module: { exports: {} } };
  const fn = new Function('window', 'document', 'module', JS + '\nreturn module.exports;');
  return fn(box.window, box.document, box.module);
}
const API = laden();
const roh = (h) => String(h).replace(/<[^>]+>/g, '');
const vor = (min) => ({ anpfiff: new Date(Date.now() + min * 60000).toISOString() });
const seit = (min) => ({ anpfiff: new Date(Date.now() - min * 60000).toISOString() });

// ── 1) Der rote Punkt ──────────────────────────────────────────────────────────────────────
test('vor Anpfiff steht, dass es noch dauert — nicht bloß eine nackte Zahl', () => {
  const t = roh(API._srAnpfiffText(vor(95)));
  assert.match(t, /in 1 h 35 min/);
});

test('der rote Punkt sagt jetzt „läuft" und nennt die Uhr, nicht eine Spielminute', () => {
  // Der Kern der Frage: „63. Min" behauptet eine Spielminute. Gemessen ist die Wanduhr seit
  // Anpfiff — die Halbzeitpause zählt mit, und bei Cricket gibt es gar keine Minuten.
  const h = API._srAnpfiffText(seit(63));
  assert.match(roh(h), /läuft/);
  assert.match(roh(h), /seit 1 h 03 min/);
  assert.doesNotMatch(roh(h), /63\. Min/, 'die Spielminuten-Lesart darf nicht zurückkommen');
  assert.match(h, /WANDUHR/, 'der Tooltip muss sagen, was gemessen wird');
});

test('ein Spiel von vor sechs Stunden steht nicht mehr rot da', () => {
  // Lucas' eigentliche Frage war „ist das vergangen?" — die alte Anzeige hat sie nicht
  // beantwortet, sondern erzeugt.
  const h = API._srAnpfiffText(seit(380));
  assert.match(roh(h), /angepfiffen vor 6 h 20 min/);
  assert.doesNotMatch(roh(h), /läuft/);
  assert.doesNotMatch(h, /sr-live/, 'rot heißt läuft — das wäre hier eine Behauptung');
  assert.match(h, /sr-vorbei/);
});

test('behauptet trotzdem nirgends, das Spiel sei beendet', () => {
  // Der Feed meldet kein Spielende. „Beendet" wäre erfunden — „nicht mehr läuft" ist belegt.
  const h = API._srAnpfiffText(seit(600));
  assert.doesNotMatch(roh(h), /beendet|zu Ende|abgepfiffen/i);
});

test('ohne Anpfiff steht nichts — kein Platzhalter, keine 0. Min', () => {
  // 🔴 Hier steckte ein echter Fehler: `new Date(null)` ist der 01.01.1970, kein Invalid Date.
  // Eine Zeile ohne Anpfiff kam als „angepfiffen vor 496.981 h" heraus — vorher als
  // „🔴 29818860. Min", also derselbe Fehler, nur besser getarnt. Epoch 0 ist ein GUELTIGES
  // Datum und besteht jede null-Pruefung, die man dagegen stellt.
  assert.strictEqual(API._srAnpfiffText({}), '');
  assert.strictEqual(API._srAnpfiffText({ anpfiff: null }), '');
  assert.strictEqual(API._srAnpfiffText({ anpfiff: '' }), '');
  assert.strictEqual(API._srBisAnpfiff({ anpfiff: null }), null,
    'null darf nicht zu 1970 werden');
});

test('die Grenze zwischen läuft und vorbei liegt genau dort, wo sie steht', () => {
  assert.match(roh(API._srAnpfiffText(seit(150))), /läuft/);
  assert.match(roh(API._srAnpfiffText(seit(151))), /angepfiffen vor/);
});

test('_srDauerText schreibt Minuten zweistellig, damit 1 h 03 nicht wie 1 h 30 aussieht', () => {
  assert.strictEqual(API._srDauerText(63), '1 h 03 min');
  assert.strictEqual(API._srDauerText(90), '1 h 30 min');
  assert.strictEqual(API._srDauerText(45), '45 min');
});

// ── 2) Altlasten und Anteil ────────────────────────────────────────────────────────────────
test('das Board zeigt standardmäßig nur, was noch spielbar ist', () => {
  // Gemessen am 11.09.: von 47 Gruppen lagen 37 über 30 Min im Spiel, 17 davon über sechs
  // Stunden. Ein Board, dessen Standardansicht zu 79 % aus gelaufenen Spielen besteht, ist
  // ein Archiv. Der Regler war da — er stand falsch herum.
  assert.strictEqual(API._srNurSpielbar(), true);
});

test('jede Seite trägt ihren Anteil am beobachteten Geld', () => {
  const g = {
    key: 'k', event: 'A - B', liga: 'Testliga', sport: 'soccer',
    anpfiff: new Date(Date.now() + 60 * 60000).toISOString(),
    n: 2, nEinzel: 2, nGeldBekannt: 2, geldUsd: 10000, gewinnUsd: 0, nKombi: 0,
    nGeldUnbekannt: 0, letzte: new Date().toISOString(), wetten: [],
    seiten: [{ name: 'A', n: 1, geld: 7500, qMin: 1.8, qMax: 1.8 },
             { name: 'B', n: 1, geld: 2500, qMin: 2.1, qMax: 2.1 }]
  };
  const k = API._srKarte(g);
  assert.match(k, /75 %/, 'der Anteil der großen Seite fehlt');
  assert.match(k, /25 %/);
  assert.match(k, /\$8k/i, 'das Geld muss weiter dastehen');
});

test('der Anteil nennt sich NICHT Marktanteil — Stake liefert kein Marktvolumen', () => {
  // Der wichtigste Test der Datei. Lucas hat nach „% vom Markt" gefragt; der Feed ist eine
  // Liste einzelner Highroller-Wetten ohne Orderbuch-Tiefe. Der Nenner ist unsere Stichprobe,
  // und die hat eine Auswahl (nur über der Schwelle, nur öffentliche Konten). Ein Prozentwert,
  // der „Marktanteil" suggeriert, wäre eine erfundene Zahl.
  const g = {
    key: 'k', event: 'A - B', liga: 'L', sport: 'soccer', anpfiff: null,
    n: 1, nEinzel: 1, nGeldBekannt: 1, geldUsd: 5000, gewinnUsd: 0, nKombi: 0,
    nGeldUnbekannt: 0, letzte: new Date().toISOString(), wetten: [],
    seiten: [{ name: 'A', n: 1, geld: 5000, qMin: 1.5, qMax: 1.5 }]
  };
  const k = API._srKarte(g);
  assert.match(k, /beobachteten Großgeld/, 'der Nenner muss benannt sein');
  assert.match(k, /NICHT am Marktvolumen/i);
});

test('ohne Geld auf den Seiten entsteht kein 100-%-Balken aus dem Nichts', () => {
  const g = {
    key: 'k', event: 'A - B', liga: 'L', sport: 'soccer', anpfiff: null,
    n: 1, nEinzel: 1, nGeldBekannt: 0, geldUsd: 0, gewinnUsd: 0, nKombi: 0,
    nGeldUnbekannt: 1, letzte: new Date().toISOString(), wetten: [],
    seiten: [{ name: 'A', n: 1, geld: 0, qMin: null, qMax: null }]
  };
  const k = API._srKarte(g);
  assert.doesNotMatch(k, /100 %/, 'ein Anteil ohne Nenner ist keine Zahl');
});

// ── 3) Sagen die Tabs etwas aus? ───────────────────────────────────────────────────────────
test('die Bilanz sagt oben, wie viele Schubladen überhaupt ein Urteil tragen', () => {
  API._srAus({ schubladen: {
    gesamt: { beinRoi: -0.011, beinRoiUg: -0.019, beinN: 24679 },
    vor_anpfiff: { belegt: true, beinRoi: 0.026, beinRoiUg: 0.015, beinN: 11632 },
    live: { belegt: false, beinRoi: -0.043, beinRoiUg: -0.057, beinN: 13047 },
    live_spaet: { belegt: false, beinRoi: -0.065, beinRoiUg: -0.084, beinN: 6679 }
  } });
  const t = roh(API._srBelegLage());
  assert.match(t, /1 von 3 Schubladen trägt ein Urteil/, 'Singular, und gezählt statt geschrieben');
  assert.match(t, /vor Anpfiff/);
  assert.match(t, /n=11632/);
  assert.match(t, /nicht widerlegt, sondern unbelegt/,
    'der Unterschied ist die ganze Aussage — unbelegt ist kein Gegenbeweis');
});

test('„gesamt" zählt nicht als Schublade — es ist die Grundgesamtheit', () => {
  API._srAus({ schubladen: {
    gesamt: { belegt: true, beinRoi: 0.01, beinRoiUg: 0.005, beinN: 100 },
    live: { belegt: false, beinRoi: -0.04, beinRoiUg: -0.06, beinN: 50 }
  } });
  const t = roh(API._srBelegLage());
  assert.match(t, /0 von 1|Keine der 1/, 'gesamt darf die Bilanz nicht schönen');
});

test('trägt keine Schublade etwas, sagt die Zeile genau das', () => {
  API._srAus({ schubladen: { live: { belegt: false, beinRoi: -0.04, beinRoiUg: -0.06, beinN: 50 } } });
  assert.match(roh(API._srBelegLage()), /Keine der 1 Schubladen/);
});

test('ohne Auswertung entsteht keine leere Behauptung', () => {
  API._srAus(null);
  assert.strictEqual(API._srBelegLage(), '');
  API._srAus({ schubladen: {} });
  assert.strictEqual(API._srBelegLage(), '');
});
