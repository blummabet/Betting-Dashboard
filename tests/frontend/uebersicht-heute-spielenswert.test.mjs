// tests/frontend/uebersicht-heute-spielenswert.test.mjs — 07.09.2026
//
// Lucas: „diese hundertfünfzig oder hundertsechzig im Paper-Trading — ist das jetzt nicht das,
// was in der Übersicht steht?"
//
// Nein, und ich hatte die beiden diese Session über selbst gleichgesetzt. Es waren zwei Mengen
// aus derselben Engine, gemessen an 570 abgerechneten spielbaren Plays:
//
//     der Topf, aus dem die Kachel wählte   n=570   63,3 % Treffer   +6,85 EUR    ROI +0,1 %
//     die Public-Kandidaten (durchs Tor)    n=167   70,7 %          +107,22 EUR  ROI +6,4 %
//
// Die Kachel SORTIERTE (Top 3 nach Score), das Tor FILTERT. Der Gewinn kommt vom Filtern.
// Seit dem 07.09. zieht die Kachel aus derselben Quelle wie das Papier-Depot und der Trades-Push.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';

const JS = readFileSync(new URL('../../main-dashboard.js', import.meta.url), 'utf8');
const CODE = JS.replace(/^\s*\/\/.*$/gm, '');

test('die Kachel zieht aus dem Public-Tor, nicht aus dem ganzen Topf', () => {
  assert.match(CODE, /_pwPublicTopPlays\(\)/,
    'ohne diese Quelle zeigt die Kachel wieder die ungefilterte Menge');
  assert.doesNotMatch(CODE, /plays = _pwTopPlays\(3, null, false\)/,
    'die alte Top-3-Sortierung darf nicht zurückkommen');
});

test('sie zeigt weiterhin höchstens drei', () => {
  const i = CODE.indexOf('_pwPublicTopPlays()');
  assert.ok(i > 0);
  assert.match(CODE.slice(i, i + 120), /\.slice\(0, 3\)/,
    'die Kachel ist eine Kachel, keine Liste');
});

test('das Etikett behauptet nicht mehr „alle Plays"', () => {
  // Ein Untertitel, der dem Inhalt widerspricht, ist in diesem Repo die häufigste Fehlerklasse.
  const i = CODE.indexOf("'Heute spielenswert'");
  assert.ok(i > 0, 'Kachel nicht gefunden');
  const zeile = CODE.slice(i, i + 260);
  assert.doesNotMatch(zeile, /'alle Plays'/);
  assert.match(zeile, /durchs Public-Tor/);
});

test('der Leer-Fall nennt die echte Bedingung', () => {
  // „Keine klaren Plays" wäre nach der Umstellung irreführend: es kommt nichts durch das TOR,
  // nicht „es gibt nichts".
  assert.match(CODE, /Gerade kommt nichts durch das Tor/);
});

test('eine Quelle für alle drei Flächen', () => {
  // Kachel, Papier-Depot und Trades-Push müssen dieselbe Menge meinen — sonst heißt in drei
  // Wochen wieder dasselbe Wort drei verschiedene Dinge.
  const emit = readFileSync(new URL('../../scripts/emit_shortlist.mjs', import.meta.url), 'utf8');
  assert.match(emit, /_pwPublicTopPlays\(\)/, 'der Emitter muss dieselbe Funktion nutzen');
  const push = readFileSync(new URL('../../push_shortlist_trades.py', import.meta.url), 'utf8');
  assert.match(push, /p\.get\("public"\)/, 'der Trades-Push muss am selben Flag hängen');
});
