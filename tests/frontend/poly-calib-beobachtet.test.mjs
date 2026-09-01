// tests/frontend/poly-calib-beobachtet.test.mjs — 01.09.2026
//
// Lucas: „schau dir das mal an, ob der Lerneffekt dort eh greift."
// Gemessen (scripts/calib_walkforward.py): er greift — 32% aller Plays wurden angefasst — aber er
// trägt nicht. Über sechs Startpunkte schlugen die ABGESTUFTEN Plays jedes Mal die hochgestuften.
// Deshalb steht `PW_CALIB_AKTIV` auf false: der Lerner beobachtet, bewegt aber keine Conviction.
//
// Diese Tests halten die drei Eigenschaften fest, die beim nächsten Anfassen als Erstes kippen:
//   · der Schalter existiert überhaupt und steht auf false,
//   · solange er false ist, wird conv NICHT verändert und KEIN calib-Tag vergeben
//     (sonst sickert er über die Signal-Eimer ins Papier-Depot und ins Public-Gate zurück),
//   · die Beobachtung geht trotzdem nicht verloren.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';

const SRC = readFileSync(new URL('../../poly-wallets.js', import.meta.url), 'utf8');

// Die Funktion isoliert ausführen — sie hängt nur an _pwComboFor und _pwComboBaselineRoi.
function calib({ n = 60, roi = 0.5, base = -0.024, conv = 7 } = {}) {
  const von = SRC.indexOf('const PW_CALIB_AKTIV');
  const bis = SRC.indexOf('function _pwBfEur');
  assert.ok(von > 0 && bis > von, 'Kalibrier-Block nicht gefunden');
  const code = SRC.slice(von, bis)
    + '\n;globalThis.__calib=_pwCalibConv;';
  const f = new Function('_pwComboFor', '_pwComboBaselineRoi', code + '\nreturn globalThis.__calib;');
  const fn = f(() => (n ? { n, roi, nRoh: n, nAlt: 0 } : null), () => base);
  return fn(['money', 'bf'], conv);
}

test('der Schalter existiert und steht auf AUS', () => {
  assert.match(SRC, /const PW_CALIB_AKTIV\s*=\s*false/,
    'nach dem Walk-Forward-Befund darf der Lerner die Conviction nicht bewegen');
});

test('ein starker Eimer verschiebt die Conviction NICHT mehr', () => {
  // n=60 bei +50% ROI gegen −2,4% Basis: das war der Fall, der +2 Stufen gab.
  const r = calib({ n: 60, roi: 0.5 });
  assert.equal(r.conv, 7, 'conv bleibt, was die Engine gerechnet hat');
  assert.equal(r.tag, null, 'kein calib+ — sonst landet es in den Signal-Eimern');
  assert.equal(r.reason, null);
});

test('ein schwacher Eimer stuft ebenfalls nicht mehr ab', () => {
  const r = calib({ n: 87, roi: -0.081 });
  assert.equal(r.conv, 7);
  assert.equal(r.tag, null);
});

test('die Beobachtung bleibt trotzdem erhalten', () => {
  // Abschalten heißt nicht wegwerfen: das Lern-Board soll weiter zeigen, was der Lerner DÄCHTE.
  const r = calib({ n: 60, roi: 0.5 });
  assert.ok(r.hinweis && /Signal-Mix real/.test(r.hinweis), 'der Hinweis wird mitgegeben');
  assert.equal(r.wuerde, 9, 'und was er getan hätte, steht als „wuerde" daneben');
});

test('zu dünne Eimer bleiben stumm — auch als Beobachtung', () => {
  const r = calib({ n: 5, roi: 0.9 });
  assert.equal(r.conv, 7);
  assert.equal(r.hinweis, undefined, 'unter n=8 wird gar nichts behauptet');
});

test('der Wiedereinschalt-Pfad ist im Quelltext dokumentiert', () => {
  // Ein Schalter ohne Bedingung wird irgendwann aus Bauchgefühl umgelegt.
  assert.match(SRC, /calib_walkforward\.py/,
    'der Quelltext muss sagen, WELCHER Test vor dem Wiedereinschalten laufen muss');
});
