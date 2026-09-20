// tests/frontend/poly-lernboard-ehrlich.test.mjs — 20.09.2026
//
// 🔴 Lucas, vor dem Lern-Board: „ist das irgendwie aktiv? ist das für die heute spielenswert?
// Was macht das" — er musste fragen, weil die Fläche im Präsens behauptete, was der Schalter
// daneben widerlegt. Wörtlich stand dort „…und <b>verschiebt die Conviction</b> sanft dorthin",
// die Chips lasen sich als „↓ −1 Stufe" und der Fuß sagte „wirkt erst ab acht gewichteten Plays".
// `PW_CALIB_AKTIV` steht seit dem 01.09.2026 auf false: der Lerner rechnet, zeigt, und fasst
// nichts an.
//
// Fehlerklasse: ein Satz behauptet, was der Schalter daneben widerlegt.
//
// Deshalb prüft dieser Test NICHT die drei Sätze einzeln, sondern die Kopplung: was das Board
// sagt, muss zum Stand von `PW_CALIB_AKTIV` passen — in beide Richtungen. Wer den Schalter
// umlegt, ohne den Text mitzunehmen, fällt hier durch; wer den Text zurückbaut, ebenso.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';

const SRC = readFileSync(new URL('../../poly-wallets.js', import.meta.url), 'utf8');

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

// Der echte Stand im Quelltext — der Test hängt nicht an einer zweiten Kopie davon.
const AKTIV_IM_CODE = /const PW_CALIB_AKTIV\s*=\s*true/.test(SRC);

// Zwei Eimer, beide über n=8, einer klar über und einer klar unter dem Schnitt: so entstehen
// Chips mit echten Stufen (+2 / −2), an denen man das „würde" sehen kann.
const EIMER = {
  'money+bf': { n: 60, roi: 0.30, nRoh: 60, nAlt: 0 },
  'steam+pinn': { n: 40, roi: -0.25, nRoh: 40, nAlt: 0 },
};

function board(aktiv) {
  const quelle = 'const _PW_CAL_BAR_W=190;\n'
    + holen('_pwCalMixLabel') + '\n' + holen('_pwCalibBoard') + '\n'
    + 'return _pwCalibBoard;';
  const f = new Function('PW_CALIB_AKTIV', '_PW_SIG_LABEL', '_pwEsc', 'PW_ENGINE_VERSION',
    '_pwComboStatsAll', '_pwComboBaselineRoi', quelle);
  return f(aktiv, { money: 'Money', bf: 'Betfair', steam: 'Steam', pinn: 'Pinnacle' },
    s => String(s), '2026-09-01', () => EIMER, () => -0.02)();
}

// Zwei Lesarten derselben Fläche, aus dem gerenderten HTML gezogen.
const sagtEsPassiert = h => /verschiebt die Conviction/.test(h);
const sagtEsPassiertNicht = h => /greift nicht ein/.test(h) && /Nichts davon wirkt gerade/.test(h);
const chipsMitStufe = h => (h.match(/(?:würde )?[↑↓] [+−]\d Stufen?/g) || []);

test('bei AUS sagt das Board, dass es nichts anfasst', () => {
  const h = board(false);
  assert.ok(sagtEsPassiertNicht(h), 'weder „greift nicht ein" noch „Nichts davon wirkt gerade"');
  assert.ok(!sagtEsPassiert(h), 'der Präsens-Satz „verschiebt die Conviction" darf nicht stehen');
});

test('bei AUS trägt jeder Stufen-Chip ein „würde"', () => {
  const chips = chipsMitStufe(board(false));
  assert.ok(chips.length >= 2, 'die Testdaten müssen Chips mit Stufen erzeugen, nicht nur „sammelt"');
  for (const c of chips) assert.match(c, /^würde /, 'Chip behauptet eine Tat: ' + c);
});

test('bei AN sagt das Board wieder, dass es eingreift', () => {
  const h = board(true);
  assert.ok(sagtEsPassiert(h), 'eingeschaltet muss der Wirkungssatz zurückkommen');
  assert.ok(!/Nichts davon wirkt gerade/.test(h), 'die Abschalt-Warnung darf nicht stehenbleiben');
  for (const c of chipsMitStufe(h)) assert.ok(!/^würde /.test(c), 'eingeschaltet kein Konjunktiv: ' + c);
});

test('der Fuß spricht in derselben Zeitform wie der Schalter', () => {
  assert.match(board(false), /wirkte erst ab acht/,
    'abgeschaltet gehört der Fuß in die Vergangenheit');
  assert.match(board(true), /wirkt erst ab acht/);
});

test('der gelieferte Stand ist mit seinem eigenen Text konsistent', () => {
  // Das ist die eigentliche Fehlerklasse: nicht „der Satz ist falsch", sondern „der Satz und der
  // Schalter driften auseinander". Läuft gegen den echten Wert im Quelltext.
  const h = board(AKTIV_IM_CODE);
  assert.equal(sagtEsPassiert(h), AKTIV_IM_CODE,
    'PW_CALIB_AKTIV=' + AKTIV_IM_CODE + ', das Board sagt das Gegenteil');
  assert.equal(sagtEsPassiertNicht(h), !AKTIV_IM_CODE);
});

test('das Board verschweigt die Messung nicht, nur weil es abgeschaltet ist', () => {
  // Abschalten heißt beobachten. ROI, Abstand und Stichprobe müssen weiter dastehen —
  // sonst wäre der Lerner nicht aus, sondern weg.
  const h = board(false);
  assert.match(h, /\+30\.0%/, 'der gemessene ROI des Eimers fehlt');
  assert.match(h, /32\.0pp/, 'der Abstand zum Schnitt fehlt');
  assert.match(h, /60 Plays/, 'die Stichprobe fehlt');
});

test('der Grund fürs Abschalten steht auf der Fläche, nicht nur im Quelltext', () => {
  // Sonst fragt in vier Wochen wieder jemand „warum ist das aus?" — und legt den Schalter um.
  const h = board(false);
  assert.match(h, /01\.09\.2026/, 'das Datum der Abschaltung');
  assert.match(h, /sechs von sechs/i, 'der Walk-Forward-Befund');
  assert.match(h, /calib_walkforward\.py/, 'die Bedingung fürs Wiedereinschalten');
});
