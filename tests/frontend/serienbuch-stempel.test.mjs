// tests/frontend/serienbuch-stempel.test.mjs — 20.09.2026 (Übersicht-Check)
//
// 🔴 Der Serien-Block zieht aus ZWEI Büchern (Liga und MLS) und stempelte sich mit
// `_ageStr(_md.data.ligaStreaks)` — also mit EINEM davon. Gemessen an dem Tag: Liga 6,0 h,
// MLS 22,0 h. Der Block sah 16 Stunden frischer aus, als er war. Gleichzeitig sagte der
// Seitenkopf korrekt „älteste Quelle Serien-Buch vor 21,2 h": zwei Zahlen über derselben
// Fläche, von denen eine die andere widerlegt.
//
// Fehlerklasse: eine zusammenfassende Überschrift über einer Zahl, die nur aus einem Teil
// stammt. Eine Fläche aus mehreren Quellen ist so alt wie ihre ÄLTESTE.
//
// Der Test führt die Regel aus statt den Quelltext zu durchsuchen — die Lehre aus
// `_bfSagtWas`: ein Test, der Buchstaben prüft, meldet Umbauten und keine Fehler.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';

const SRC = readFileSync(new URL('../../main-dashboard.js', import.meta.url), 'utf8');

function holen(name) {
  const a = SRC.indexOf('function ' + name + '(');
  assert.ok(a > 0, 'Funktion weg: ' + name);
  let tiefe = 0;
  for (let j = SRC.indexOf('{', a); j < SRC.length; j++) {
    if (SRC[j] === '{') tiefe++;
    else if (SRC[j] === '}') { tiefe--; if (!tiefe) return SRC.slice(a, j + 1); }
  }
  throw new Error('Klammern nicht geschlossen: ' + name);
}

// Die Regel isoliert: _ageMin und esc werden hereingereicht, alles andere ist echter Quelltext.
function bau() {
  const quelle = holen('_ageTxt') + '\n' + holen('_ageStrAelteste') + '\nreturn _ageStrAelteste;';
  return new Function('_ageMin', 'esc', quelle)(
    o => (o && o.__min != null) ? o.__min : null,
    s => String(s));
}

const alt = m => ({ __min: m });

test('der Stempel nimmt die ÄLTESTE Quelle, nicht die erste', () => {
  const f = bau();
  // Genau der gemessene Fall: Liga 6,0 h (360 Min), MLS 22,0 h (1320 Min).
  const html = f([alt(360), alt(1320)], ['Liga', 'MLS-Buch']);
  assert.match(html, /22,0 h/, 'der Block ist so alt wie sein ältester Teil');
  assert.ok(!/6,0 h/.test(html), 'der jüngere Teil darf den Stempel nicht stellen');
});

test('er sagt auch, WELCHE Quelle die älteste ist', () => {
  // Sonst sieht man die Zahl und weiß nicht, wo man nachsehen muss.
  const f = bau();
  assert.match(f([alt(360), alt(1320)], ['Liga', 'MLS-Buch']), /MLS-Buch/);
});

test('die Reihenfolge der Quellen ändert nichts', () => {
  const f = bau();
  const a = f([alt(1320), alt(360)], ['MLS-Buch', 'Liga']);
  const b = f([alt(360), alt(1320)], ['Liga', 'MLS-Buch']);
  assert.match(a, /22,0 h/);
  assert.match(b, /22,0 h/);
});

test('eine fehlende Quelle zieht den Stempel nicht auf null', () => {
  // „nicht gemessen" ist nicht „gerade frisch" — die Klasse, die hier ohnehin überall lauert.
  const f = bau();
  assert.match(f([null, alt(1320), {}], ['a', 'MLS-Buch', 'c']), /22,0 h/);
});

test('ohne jede lesbare Quelle steht gar kein Stempel', () => {
  const f = bau();
  assert.equal(f([null, {}], ['a', 'b']), '');
  assert.equal(f([], []), '');
  assert.equal(f(null), '');
});

test('die Farbe folgt dem Alter der ältesten Quelle', () => {
  const f = bau();
  assert.match(f([alt(5), alt(1320)], ['a', 'b']), /#f2a6a6/, 'alt muss rot sein');
  assert.match(f([alt(5), alt(20)], ['a', 'b']), /--gold/);
  assert.match(f([alt(5), alt(9)], ['a', 'b']), /--mi3/);
});

test('der Serien-Block benutzt die Regel und nicht mehr den Einzel-Stempel', () => {
  // Hier ist eine Quelltext-Prüfung richtig: geprüft wird die VERDRAHTUNG, nicht das Verhalten.
  // Die AUFRUFSTELLE suchen, nicht die Definition: `function _mdStreakBuch() {` enthaelt
  // `_mdStreakBuch()` als Teilstring, und der Funktionsrumpf liest selbst `mlsStreakRec` —
  // ein Schnitt ab der Definition waere gruen, egal was die Aufrufstelle uebergibt.
  const i = SRC.indexOf("join('') + _mdStreakBuch()");
  const j = SRC.indexOf('Keine langen Serien', i);
  assert.ok(i > 0 && j > i);
  const block = SRC.slice(i, j);
  assert.match(block, /_ageStrAelteste\(/, 'der Block muss die Regel benutzen');
  assert.ok(!/_ageStr\(_md\.data\.ligaStreaks\)/.test(block),
    'der Einzel-Stempel war der Fehler');
  assert.match(block, /mlsStreakRec/, 'das MLS-Buch muss unter den Quellen stehen');
});
