// tests/frontend/poly-paarung-reihenfolge.test.mjs — 20.09.2026 (Übersicht-Check)
//
// 🔴 Auf der Übersicht stand dasselbe Spiel zweimal in entgegengesetzter Reihenfolge:
//   Ebene 3  → „EDward Gaming Youth Team vs Fuego"
//   Liste „Spielbar aus Public-Kandidaten" zwei Blöcke darüber → „Fuego vs EDward Gaming Youth Team"
// Dasselbe bei „SSC Napoli vs ACF Fiorentina" (Slug sea-fio-nap → Fiorentina ist Heim) und
// „AIK vs Halmstads BK" (Slug swe-hal-aik → Halmstads ist Heim).
//
// Ursache: `_pwShortlistScore` sortiert `oc` nach Geld, um `moneyFav` zu bestimmen, und reicht
// DASSELBE sortierte Array an `_pwPlayLabel` weiter. Sechs weitere Aufrufer machen es genauso.
// Weil die empfohlene Seite fast immer die Geld-Mehrheitsseite ist, steht der Pick vorn:
// gemessen im Push-Buch 33 von 33 Zeilen, gegen die echte Marktreihenfolge 11 von 32 gedreht.
//
// Fehlerklasse: eine Reihenfolge, die eine Eigenschaft des MARKTES ist, wird aus einer
// Auswertung abgeleitet. Deshalb prüft dieser Test die Reihenfolge und NICHT den Aufrufer —
// ein Test, der jeden Aufrufer einzeln absichert, zementiert das Duplikat.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';

const ROOT = new URL('../../', import.meta.url);
const JS = readFileSync(new URL('poly-wallets.js', ROOT), 'utf8');

function holen(name) {
  const a = JS.indexOf('function ' + name + '(');
  assert.ok(a > 0, 'Funktion weg: ' + name);
  let tiefe = 0;
  for (let j = JS.indexOf('{', a); j < JS.length; j++) {
    if (JS[j] === '{') tiefe++;
    else if (JS[j] === '}') { tiefe--; if (!tiefe) return JS.slice(a, j + 1); }
  }
  throw new Error('Klammern nicht geschlossen: ' + name);
}

function bau(cache) {
  const quelle = 'let _pwCache=' + JSON.stringify(cache) + ';\n'
    + 'const _PW_NAME_SUFFIX_RX=/-(more-markets|total-corners|exact-score|player-.*)$/;\n'
    + 'const _PW_GEN_RX=/^(over|under|yes|no|draw|tie)$/i;\n'
    + 'const _PW_DRAWP_RX=/^draw\\s*\\(/i;\n'
    + 'const _PW_SCORE_RX=/\\d+\\s*-\\s*\\d+/;\n'
    + holen('_pwRealTeams') + '\n' + holen('_pwMarktReihenfolge') + '\n'
    + holen('_pwNachMarkt') + '\n' + holen('_pwResolveTeams') + '\n'
    + holen('_pwPrettyKey') + '\n' + holen('_pwPlayLabel') + '\n'
    + 'return _pwPlayLabel;';
  return new Function(quelle)();
}

// Die drei echten Fälle vom Board, mit der Outcome-Reihenfolge aus den Artefakten.
const MARKT = {
  broadLive: {
    'sea-fio-nap-2026-09-20': { prices: { 'ACF Fiorentina': 0.1, 'Draw (ACF Fiorentina vs. SSC Napoli)': 0.2, 'SSC Napoli': 0.7 } },
    'lol-fue-edgy-2026-09-20': { prices: { 'Fuego': 0.14, 'EDward Gaming Youth Team': 0.86 } },
    'swe-hal-aik-2026-09-20': { prices: { 'Halmstads BK': 0.2, 'Draw (Halmstads BK vs. AIK)': 0.2, 'AIK': 0.6 } },
  },
  broadLiveNow: {}, moneyBroad: {},
};

test('der Pick vorn dreht die Paarung nicht mehr um', () => {
  const label = bau(MARKT);
  // So kam es aus `_pwShortlistScore`: nach Geld sortiert, Favorit zuerst.
  const geldSortiert = [{ s: 'SSC Napoli' }, { s: 'ACF Fiorentina' }];
  assert.equal(label('sea-fio-nap-2026-09-20', geldSortiert), 'ACF Fiorentina vs SSC Napoli');
  assert.equal(label('lol-fue-edgy-2026-09-20',
    [{ s: 'EDward Gaming Youth Team' }, { s: 'Fuego' }]), 'Fuego vs EDward Gaming Youth Team');
  assert.equal(label('swe-hal-aik-2026-09-20',
    [{ s: 'AIK' }, { s: 'Halmstads BK' }]), 'Halmstads BK vs AIK');
});

test('eine schon richtige Reihenfolge bleibt richtig', () => {
  const label = bau(MARKT);
  assert.equal(label('sea-fio-nap-2026-09-20',
    [{ s: 'ACF Fiorentina' }, { s: 'SSC Napoli' }]), 'ACF Fiorentina vs SSC Napoli');
});

test('beide Flächen zeigen dasselbe Spiel gleich herum', () => {
  const label = bau(MARKT);
  const ebene3 = label('lol-fue-edgy-2026-09-20',
    [{ s: 'EDward Gaming Youth Team' }, { s: 'Fuego' }]);          // nach Geld sortiert
  const liste = label('lol-fue-edgy-2026-09-20',
    [{ s: 'Fuego' }, { s: 'EDward Gaming Youth Team' }]);          // Artefakt-Reihenfolge
  assert.equal(ebene3, liste, 'zwei Flächen, ein Spiel, zwei Reihenfolgen');
});

test('ohne Markt im Cache wird nichts geraten', () => {
  // Raten wäre schlimmer als eine unbekannte Ordnung: eine erfundene Heim/Auswärts-Zuordnung
  // ist nicht als falsch erkennbar.
  const label = bau({ broadLive: {}, broadLiveNow: {}, moneyBroad: {} });
  assert.equal(label('xyz-unbekannt-2026-09-20',
    [{ s: 'B Team' }, { s: 'A Team' }]), 'B Team vs A Team');
});

test('ein Prop erbt die Reihenfolge seines Basis-Events', () => {
  const label = bau(MARKT);
  assert.equal(label('sea-fio-nap-2026-09-20-total-corners',
    [{ s: 'Over' }, { s: 'Under' }]), 'ACF Fiorentina vs SSC Napoli');
});

test('nur wenn BEIDE Namen im Markt stehen wird umgestellt', () => {
  // Sonst entschiede ein Unbekannter die Reihenfolge des Bekannten.
  const label = bau(MARKT);
  // Der Unbekannte steht VORN: ohne die Schranke landete er hinten, weil „nicht im Markt"
  // als „ganz hinten" gerechnet wird — eine Reihenfolge, die ein Unbekannter entscheidet.
  assert.equal(label('sea-fio-nap-2026-09-20',
    [{ s: 'Wer auch immer' }, { s: 'SSC Napoli' }]), 'Wer auch immer vs SSC Napoli');
});
