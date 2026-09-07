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
  // 29.08.2026 (Lucas: „wenn es verbessert, zieh's nach"): Cards + Card-Tracking lasen
  // liga-data.json / mls-data.json relativ, also aus dem Pages-Snapshot — waehrend die
  // Uebersicht dieselben zwei Dateien laengst raw-first holte. Ein Datensatz, zwei Staende,
  // je nach Tab. Das ist schlimmer als ueberall gleich alt: die Tabs widersprachen sich.
  'wm2026-renderer.js',
  'wm2026-tracking.js',
  // 07.09.2026 (Lucas: „na alle tabs klappen nur der nicht"): stake-radar.js. Der neue
  // Spielklasse-Reiter stand leer, die drei Reiter daneben liefen — weil die nur Felder
  // brauchen, die es im alten Artefakt schon gab. Ein NEUES Feld ist im Pages-Snapshot bis
  // zu eine Stunde lang nicht da, und das sieht aus wie ein kaputter Produzent.
  'stake-radar.js',
];

// 07.09.2026 — dritter Fall derselben Klasse, und die Liste oben war der Grund. Sie ist
// handgepflegt: eine neue Datei kommt dazu, niemand traegt sie nach, und der Guard schweigt
// genau fuer die Datei, die neu ist. Ein Guard, den man vergessen kann, ist keiner.
//
// Deshalb wird die Liste jetzt gegen die WIRKLICHKEIT geprueft: welche Dateien laedt das
// Dashboard, und welche davon holen JSON? Jede davon muss entweder raw-zuerst holen oder
// hier unten mit Grund stehen. Dann kostet eine neue Datei eine Entscheidung statt ein
// stilles Vergessen.
const AUSNAHMEN = {
  // Diese fuenf holen bis heute relativ. Das ist ein offener Befund vom 07.09., keine
  // Absicht — sie zeigen bis zu eine Stunde alte Daten. Sie stehen hier namentlich, damit
  // die Zahl nicht waechst, ohne dass es jemand entscheidet.
  'renderer.js': 'offen (07.09.2026): liga-data.json u.a. relativ',
  'ui.js': 'offen (07.09.2026): wm2026-data.json u.a. relativ',
  'pinnacle-poly.js': 'offen (07.09.2026): pinnacle_poly_scan.json relativ',
  'signal-check.js': 'offen (07.09.2026): signal_check.json relativ',
  'results-v2.js': 'offen (07.09.2026): picks_history.json ueber die Pages-URL',
};

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

test('keine Datei des Dashboards holt JSON, ohne dass es jemand entschieden hat', () => {
  // Die Skriptliste steht in season-finish-v2.html; sie ist die Wirklichkeit, nicht die
  // Liste oben. Ein `fetch(...json)` in einer Datei, die weder raw-zuerst holt noch als
  // Ausnahme benannt ist, ist genau der Fall, der am 29.08. und am 07.09. passiert ist.
  const html = src('season-finish-v2.html');
  const liste = html.slice(html.indexOf('var scripts = ['), html.indexOf('for (var i = 0'));
  const dateien = [...liste.matchAll(/"([^"]+\.js)"/g)].map((m) => m[1]);
  assert.ok(dateien.length > 10, 'die Skriptliste im Dashboard wurde nicht gefunden');

  const uebersehen = [];
  for (const f of dateien) {
    let s;
    try { s = src(f); } catch { continue; }
    const holtJson = /fetch\(\s*['"`][^'"`]*\.json/.test(s);
    if (!holtJson) continue;
    if (s.includes(RAW)) continue;
    if (AUSNAHMEN[f]) continue;
    uebersehen.push(f);
  }
  assert.deepEqual(uebersehen, [],
    'holt JSON relativ und steht weder in DATEN_LADER noch in AUSNAHMEN: ' + uebersehen.join(', '));
});

test('die Ausnahmenliste bleibt ehrlich', () => {
  // Eine Ausnahme, die inzwischen raw-zuerst holt, gehoert nach oben — sonst waechst hier
  // eine Liste von Behauptungen, die niemand mehr prueft.
  const falsch = Object.keys(AUSNAHMEN).filter((f) => {
    try { return src(f).includes(RAW); } catch { return true; }
  });
  assert.deepEqual(falsch, [],
    'steht als Ausnahme, holt aber längst raw-zuerst (oder gibt es nicht mehr): ' + falsch.join(', '));
});

test('der Deploy läuft stündlich, nicht mehr alle 15 Minuten', () => {
  // `*/15` lieferte real im Median alle ~1,9 h (8 statt 96 Läufe/Tag) — GitHub drosselt
  // hochfrequente Schedules. Eine stündliche Bitte hält es zuverlässig ein.
  const wf = src('.github/workflows/deploy-pages.yml');
  assert.ok(!/cron:\s*'\*\/15/.test(wf), 'deploy-pages steht wieder auf */15');
  assert.ok(/cron:\s*'\d+ \* \* \* \*'/.test(wf), 'deploy-pages hat keinen stündlichen Cron');
});
