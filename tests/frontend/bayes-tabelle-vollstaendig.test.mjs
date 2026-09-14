// tests/frontend/bayes-tabelle-vollstaendig.test.mjs
//
// 14.09.2026 (Lucas: „wo seh ich eigentlich, wie die Signale werken, wie sie sich anpassen und
// lernen?"). Die Antwort war zwei Flächen — und eine davon zeigte nur einen Teil.
//
// Der Bayesian-Lern-Status baute seine Zeilen aus zwei handgepflegten Listen im Renderer.
// Gemessen am echten Bestand fehlten Liga 190 von 820 Beobachtungen (23 %) und MLS 374 von
// 668 (56 %) — darunter das größte MLS-Signal überhaupt. Die Kopfzeile behauptete derweil
// „verteilt über ALLE Signale".
//
// Diese Tests halten fest: die Zeilen kommen aus der DATEI, nicht aus einer Liste.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';

const CODE = readFileSync(new URL('../../renderer.js', import.meta.url), 'utf8');
const BLOCK = CODE.slice(CODE.indexOf('function _renderBayesianWeights'),
                         CODE.indexOf('// ── CLV-Bilanz'));

test('⭐ die Signal-Zeilen kommen aus den Gewichten, nicht aus einer Liste', () => {
  assert.match(BLOCK, /const signalNames = Object\.keys\(weights\)/,
    'eine Aufzählung vergisst das nächste Signal — und niemand merkt es');
  assert.ok(!/const signalNames = _isLiga \? \[/.test(BLOCK),
    'die alten handgepflegten Listen dürfen nicht zurückkommen');
});

test('kein Signal fällt heraus, auch ein unbekanntes nicht', () => {
  const m = BLOCK.match(/const signalNames = Object\.keys\(weights\)([\s\S]*?);\n/);
  assert.ok(m, 'signalNames-Ausdruck nicht gefunden');
  const bauen = new Function('weights', `
    const _ignorieren = new Set(["_meta"]);
    const signalNames = Object.keys(weights)${m[1]};
    return signalNames;`);
  const w = {
    _meta: { description: 'x' },
    form_trend: { n_observations: 111 },
    mls_travel: { n_observations: 39 },          // stand in KEINER der beiden alten Listen
    voellig_neues_signal: { n_observations: 7 }, // das nächste, das dazukommt
  };
  const namen = bauen(w);
  assert.deepStrictEqual(namen, ['form_trend', 'mls_travel', 'voellig_neues_signal'],
    'nach Beobachtungen sortiert, _meta raus, nichts verschluckt');
});

test('ein Signal ohne Label verschwindet nicht, es zeigt seinen Rohnamen', () => {
  assert.match(BLOCK, /labels\[name\] \|\| name/,
    'ein unschöner Name ist besser als ein blinder Fleck');
});

test('⭐ die Kopfzeile behauptet nicht mehr „alle", sondern nennt die Zahl', () => {
  assert.ok(!/Beobachtungen verteilt über alle Signale/.test(BLOCK),
    'die Behauptung war falsch, solange die Tabelle aus einer Liste kam');
  assert.match(BLOCK, /\$\{signalNames\.length\} Signale/);
});

test('die Summe zählt genau die Zeilen, die auch gezeigt werden', () => {
  // Sonst steht in der Kopfzeile eine andere Grundgesamtheit als in der Tabelle — genau der
  // Unterschied 630/820, den Lucas erwischt hat.
  assert.match(BLOCK, /const totalN = signalNames\.reduce/);
});
