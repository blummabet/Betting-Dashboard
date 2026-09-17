// tests/frontend/stake-radar-luecken.test.mjs — 17.09.2026
//
// Lucas schickt einen Post aus einem fremden Stake-Radar: kasachische Pervaya Liga,
// FK Arys – Aktobe Reserve, „6 bets / 5 bets in 3 min", Einsätze zwischen $1.273 und $6.500.
// „Sowas findest du nicht? Gab's nicht in unserem Feed?"
//
// Gab es nicht: null Zeilen aus Kasachstan in 20.000 gesammelten Wetten. Die Fläche sagte
// trotzdem „Abruf deckt 37 min" und las sich gesund — das ist der LETZTE Lauf. Die Bilanz über
// alle Läufe sagte: in 138 von 369 Abrufen entstand eine Lücke, 855,8 Minuten blind seit dem
// 13.09. Eine Momentaufnahme stand dort, wo eine Bilanz hingehört.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';

const ROOT = new URL('../../', import.meta.url);
const JS = readFileSync(new URL('stake-radar.js', ROOT), 'utf8');
function laden() {
  const sandbox = { window: {}, document: { getElementById: () => null, head: { appendChild() {} }, createElement: () => ({}) }, module: { exports: {} } };
  const fn = new Function('window', 'document', 'module', JS + '\nreturn module.exports;');
  return fn(sandbox.window, sandbox.document, sandbox.module);
}
const API = laden();
const BILANZ = { laeufe: 369, seit: '2026-09-13T13:40:22.341666Z', mitLuecke: 138,
                 minutenBlind: 855.8, laengsteMin: 24.3, anteilMitLueckePct: 37.4 };

test('die Bilanz nennt Anteil und blinde Minuten', () => {
  const h = API._srLueckenBilanz(BILANZ);
  assert.match(h, /37 % der Abrufe mit Lücke/);
  assert.match(h, /856 min blind/);
});

test('sie nennt auch die längste Einzellücke und die Zahl der Läufe', () => {
  // Ohne die beiden ist „37 %" eine Zahl ohne Basis.
  const h = API._srLueckenBilanz(BILANZ);
  assert.match(h, /369 Abrufe/);
  assert.match(h, /24\.3 min/);
});

test('ab einem Viertel der Läufe wird es eine Warnung, nicht graue Deko', () => {
  assert.match(API._srLueckenBilanz(BILANZ), /sr-warnz/);
  assert.match(API._srLueckenBilanz(Object.assign({}, BILANZ, { anteilMitLueckePct: 4 })), /sr-mut/);
});

test('ohne gezählte Läufe wird nichts behauptet', () => {
  // „0 % Lücke" wäre eine Aussage über eine Messung, die es nicht gibt.
  assert.equal(API._srLueckenBilanz(null), '');
  assert.equal(API._srLueckenBilanz({}), '');
  assert.equal(API._srLueckenBilanz({ laeufe: 0, mitLuecke: 0 }), '');
});

test('fehlt der fertige Anteil, wird er aus den Läufen gerechnet', () => {
  const h = API._srLueckenBilanz({ laeufe: 100, mitLuecke: 40, minutenBlind: 200, laengsteMin: 9 });
  assert.match(h, /40 % der Abrufe mit Lücke/);
});

test('die Statuszeile ruft die Bilanz auch wirklich auf', () => {
  // Der Rollout-Teil: eine Funktion, die stimmt und nirgends haengt, ist Dekoration.
  const von = JS.indexOf('Stakes Deckel liegt bei 50');
  const bis = JS.indexOf('sr-warn">Der Feed ist');
  assert.ok(von > 0 && bis > von, 'Anker im Statusblock weg');
  assert.match(JS.slice(von, bis), /_srLueckenBilanz\(d\.luecken\)/);
});
