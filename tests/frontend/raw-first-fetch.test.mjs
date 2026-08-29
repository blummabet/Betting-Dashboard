// tests/frontend/raw-first-fetch.test.mjs — 29.08.2026
//
// Lucas: „auf der Seite ist nichts" / „weder in Übersicht noch im Polymarket-Wallets".
//
// Die Seite holt ihre Daten auf zwei Wegen, und das war der ganze Ärger eines halben Tages:
//
//   main-dashboard.js · betfair-radar.js · polymarket-tab.js
//       → raw.githubusercontent.com/main   commit-frisch, alle ~14 Min
//   status-checks.js · poly-wallets.js
//       → relativer Pfad                   Pages-Snapshot, real ~8 Republishes/Tag
//
// Folge: die Feed-Frische meldete „vor 8,6 Std", während dieselben Dateien in der Übersicht
// daneben live waren. Das Diagnose-Panel war das Älteste auf der Seite und hat die Suche einen
// halben Tag in die falsche Richtung geschickt — erst Richtung Daten, dann Richtung Deploy,
// bis am Ende nur die Messung falsch war.
//
// Seit dem Deploy-Wechsel auf stündlich (statt der real nie eingehaltenen 15 Minuten) ist die
// Reihenfolge nicht mehr Geschmackssache: wer relativ holt, zeigt bis zu eine Stunde alte Daten.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';

const ROOT = new URL('../../', import.meta.url);
const RAW = 'raw.githubusercontent.com/blummabet/Betting-Dashboard/main';

// Dateien, die Daten-JSONs laden und deshalb raw-zuerst holen müssen.
const DATEN_LADER = [
  'main-dashboard.js',
  'betfair-radar.js',
  'polymarket-tab.js',
  'status-checks.js',
  'poly-wallets.js',
];

function src(f) {
  return readFileSync(new URL(f, ROOT), 'utf8');
}

for (const f of DATEN_LADER) {
  test(`${f} holt primär von raw/main`, () => {
    assert.ok(src(f).includes(RAW),
      `${f} kennt die raw-Basis nicht — seine Daten hängen dann am Pages-Deploy (stündlich)`);
  });

  test(`${f} hat den Snapshot als Rückfall`, () => {
    // Ohne Rückfall wäre eine raw-Störung ein Totalausfall statt einer Verzögerung.
    // `catch {}` (ohne Bindung) zählt genauso wie `catch (e)` — polymarket-tab.js nutzt die
    // kurze Form, und der erste Anlauf dieses Tests hat sie faelschlich als fehlend gemeldet.
    const s = src(f);
    const fenster = s.slice(s.indexOf(RAW), s.indexOf(RAW) + 900);
    assert.ok(/catch\s*[({]/.test(fenster),
      `${f} fängt einen raw-Fehlschlag nicht ab — kein Rückfall auf den Snapshot`);
  });
}

test('status-checks meldet eine Datei erst als unlesbar, wenn BEIDE Wege scheitern', () => {
  // Sonst hätte jede raw-Störung das halbe Dashboard als kaputt gemeldet — ein Fehlalarm,
  // der genau so schädlich ist wie die verschwiegene Stille davor.
  const s = src('status-checks.js');
  const fn = s.slice(s.indexOf('async function _stGet'), s.indexOf('let _stRunning'));
  // Die raw-Basis steht als Konstante ueber der Funktion; im Rumpf steht ihr Name.
  const rawPos = fn.indexOf('_ST_RAW_BASE');
  const meldePos = fn.indexOf('_stUnloadable.push');
  assert.ok(rawPos >= 0, '_stGet benutzt die raw-Basis gar nicht');
  assert.ok(meldePos > rawPos,
    'die Unlesbar-Meldung steht vor dem raw-Versuch — jede raw-Stoerung waere ein Fehlalarm');
});

test('der Deploy läuft stündlich, nicht mehr alle 15 Minuten', () => {
  // `*/15` lieferte real im Median alle ~1,9 h (8 statt 96 Läufe/Tag) — GitHub drosselt
  // hochfrequente Schedules. Eine stündliche Bitte hält es zuverlässig ein.
  const wf = src('.github/workflows/deploy-pages.yml');
  assert.ok(!/cron:\s*'\*\/15/.test(wf), 'deploy-pages steht wieder auf */15');
  assert.ok(/cron:\s*'\d+ \* \* \* \*'/.test(wf), 'deploy-pages hat keinen stündlichen Cron');
});
