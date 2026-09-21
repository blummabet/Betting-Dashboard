// tests/frontend/status-ruhend.test.mjs — 21.09.2026
//
// 🔴 Lucas: „Der WM Mist, ist vorbei. Interessiert niemand." Der Readiness-Report der WM war
// 1529 Stunden alt — 64 Tage — und leuchtete auf der Statusseite ROT, mit drei Befunden vom
// 19. Juli. Ein Datensatz, der seit zwei Monaten nichts mehr liefert, ist nicht kaputt: er
// ruht. Rot heisst „etwas ist schiefgegangen"; hier ist nichts schiefgegangen, hier ist ein
// Turnier vorbei.
//
// Fehlerklasse: ein abgeschlossener Zustand, der als Störung gerendert wird.
//
// Die Unterscheidung gibt es im Haus schon — `freigabe.py` kennt `status: "ruht"` für
// Schubladen, deren letzter Play zu lange her ist. Dieselbe Regel, andere Fläche.
//
// Der Test führt die Einstufung aus, statt im Quelltext nach Wörtern zu suchen: ein
// Grep-Test wäre grün, sobald das Wort irgendwo steht.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';

const SRC = readFileSync(new URL('../../status-checks.js', import.meta.url), 'utf8');

const RUHEND_H = (() => {
  const m = SRC.match(/const _ST_RUHEND_H\s*=\s*([^;]+);/);
  assert.ok(m, '_ST_RUHEND_H fehlt');
  return Function('return (' + m[1] + ')')();
})();

// Die echte Funktion aus dem Quelltext holen und AUSFUEHREN — kein Grep. `_stAgo` wird
// eingespeist, weil es fuer diese Frage nichts entscheidet.
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

const einstufen = (() => {
  const quelle = holen('_stFeedStufe') + '\nreturn _stFeedStufe;';
  return Function('_ST_RUHEND_H', '_stAgo', quelle)(RUHEND_H, () => 'vor X');
})();

const FEED = { warnH: 8, errH: 24 };

test('die Schwelle steht bei 14 Tagen', () => {
  assert.equal(RUHEND_H, 14 * 24);
});

test('der echte Fall: 1529 h alt ruht, statt rot zu sein', () => {
  const r = einstufen(1529, FEED, 'x');
  assert.equal(r.val, 'ruht');
  assert.notEqual(r.col, '#f85149', 'ein abgeschlossenes Turnier ist keine Störung');
  assert.match(r.sub, /64 Tagen/);
});

test('ein echter Ausfall bleibt rot', () => {
  // 30 h: über errH (24), aber weit unter der Ruhend-Schwelle — genau der Fall, für den
  // die rote Farbe da ist.
  const r = einstufen(30, FEED, 'x');
  assert.equal(r.col, '#f85149');
  assert.notEqual(r.val, 'ruht');
});

test('knapp unter der Schwelle ist noch ein Ausfall', () => {
  const r = einstufen(14 * 24 - 1, FEED, 'x');
  assert.notEqual(r.val, 'ruht', 'die Grenze darf nicht schon vorher greifen');
  assert.equal(r.col, '#f85149');
});

test('ein frischer Feed bleibt grün', () => {
  const r = einstufen(2, FEED, 'x');
  assert.equal(r.col, '#3fb950');
});

test('ohne Zeitstempel wird weder rot noch ruhend behauptet', () => {
  const r = einstufen(null, FEED, null);
  assert.equal(r.val, '—');
});
