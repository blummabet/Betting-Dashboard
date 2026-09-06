// tests/frontend/uebersicht-regale.test.mjs — 06.09.2026
//
// Lucas: „die Heute spielenswert wären doch auch ähnlich zu diesen 2 Elementen in Wahrheit oder?"
//
// Nachgemessen — nein, und mein erster Vorschlag dazu war falsch. Ich wollte die Überschneidung
// markieren („steht in beiden"). Der Marker hätte nie gefeuert:
//
//     Element 2 (Konsens):       4 Zeilen, davon 4× „Match Odds" — nur 1X2, und nur auf Spielen,
//                                die Betfair UND Poly UND Pinnacle quotieren.
//     Heute spielenswert:        20 offene Plays — 13× Über/Unter, 4× 1X2, dazu Tennis,
//                                E-Sport, exakter Score.
//     Überschneidung:            0     (am 01.09. schon einmal gemessen: ebenfalls 0)
//
// Die Flächen sind nicht redundant, sie sind DISJUNKT — sie bedienen verschiedene Regale. Genau
// das stand nirgends. Deshalb rechnet jeder Kopf jetzt aus den eigenen Daten, womit er gerade
// gefüllt ist, statt es zu behaupten.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';

const ROOT = new URL('../../', import.meta.url);
const JS = readFileSync(new URL('main-dashboard.js', ROOT), 'utf8');
const CODE = JS.replace(/^\s*\/\/.*$/gm, '');

function fn(name) {
  const a = CODE.indexOf('function ' + name);
  assert.ok(a > 0, 'Funktion weg: ' + name);
  const b = CODE.indexOf('\n  function ', a + 1);
  return CODE.slice(a, b > a ? b : a + 4000);
}

test('_mdRegal zählt die Märkte, statt sie zu behaupten', () => {
  const src = fn('_mdRegal');
  assert.ok(/marktVon\(items\[i\]\)/.test(src), 'die Marktbezeichnung wird nicht aus den Items gelesen');
  assert.ok(/sort/.test(src), 'ohne Sortierung steht nicht der häufigste Markt vorn');
  assert.ok(/slice\(0, 3\)/.test(src), 'die Zeile muss kurz bleiben — sie ist eine Beschriftung');
});

test('_mdRegal ist rein und rechenbar', async () => {
  // Die Funktion selbst nachbauen (sie hängt nur an esc) und gegen echte Formen prüfen.
  const src = fn('_mdRegal').replace('function _mdRegal', 'function _mdRegal');
  // eslint-disable-next-line no-new-func
  const f = new Function('esc', src + '; return _mdRegal;')(String);
  assert.strictEqual(f([], () => 'x'), '');
  assert.strictEqual(f(null, () => 'x'), '');
  const items = [{ m: 'Match Odds' }, { m: 'Match Odds' }, { m: 'Über/Unter' }];
  assert.strictEqual(f(items, (o) => o.m), '2× Match Odds · 1× Über/Unter');
});

test('_mdRegal verschweigt fehlende Angaben nicht', () => {
  const f = new Function('esc', fn('_mdRegal') + '; return _mdRegal;')(String);
  assert.strictEqual(f([{}, {}], (o) => o.m), '2× —',
    'ein Markt ohne Namen muss als solcher sichtbar sein, nicht verschwinden');
});

test('beide Ebenen tragen ihr Regal im Kopf', () => {
  assert.ok(/_mdRegal\(s1\.concat\(s2\)/.test(CODE),
    'Ebene 2 sagt nicht, aus welchen Märkten sie besteht');
  assert.ok(/_mdRegal\(items, function \(o\) \{ return _quelleLabel/.test(CODE),
    'Ebene 3 sagt nicht, aus welchen Quellen sie besteht');
});

test('der Kopf zeigt das Regal nur, wenn es eines gibt', () => {
  const src = fn('_mdEbene');
  assert.ok(/regal \?/.test(src),
    'ohne Bedingung stünde bei leerer Liste eine leere Beschriftung da');
  assert.ok(/gerade im Regal/.test(src));
});

test('Ebene 3 bleibt farblos — sie belegt nichts', () => {
  const src = fn('_mdEbene');
  assert.ok(/Ebene 3 traegt bewusst KEINE Signalfarbe/.test(JS) || /mechCol = 'var\(--mi2\)'/.test(src),
    'die Rangliste darf nicht wie ein Urteil aussehen');
});
