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
import { readFileSync, readdirSync } from 'node:fs';

const ROOT = new URL('../../', import.meta.url);
const RAW = 'raw.githubusercontent.com/blummabet/Betting-Dashboard/main';

// Dateien, die Daten-JSONs laden und deshalb raw-zuerst holen müssen.
const DATEN_LADER = [
  'raw-json.js',
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
  // 07.09.2026, gefunden vom breiteren Guard unten (nicht von einem Blick): money-map.js holte
  // money_map.json relativ, waehrend die Uebersicht dieselbe Datei raw-zuerst hat. tiktok-studio.js
  // ebenso fuer Config/Pools.
  'money-map.js',
  'tiktok-studio.js',
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
// 07.09.2026 — die fuenf offenen Faelle (renderer, ui, pinnacle-poly, signal-check,
// results-v2) sind erledigt, und zwar nicht per Copy-Paste: sie holen jetzt ueber
// `rawJson()` aus raw-json.js. Damit ist die Reihenfolge EINMAL geschrieben statt
// dreizehnmal abgeschrieben — das war die eigentliche Bug-Klasse. Die Liste bleibt
// leer stehen: sie ist der Ort, an dem eine bewusste Ausnahme mit Grund steht,
// und ein leerer Ort ist die ehrlichste Meldung, die er machen kann.
const AUSNAHMEN = {};

// Wer nicht selbst raw kennt, muss den gemeinsamen Helfer benutzen. Beides zaehlt als
// „holt raw-zuerst"; alles andere ist ein Fund.
const HELFER = 'raw-json.js';
const nutztHelfer = (s) => /\brawJson\s*\(|\brawFirstUrls\s*\(/.test(s);
const holtRawZuerst = (s) => s.includes(RAW) || nutztHelfer(s);

function src(f) {
  return readFileSync(new URL(f, ROOT), 'utf8');
}

// Der Helfer selbst: er ist die einzige Stelle, an der die Reihenfolge steht, also wird
// er als einziger auf beides geprueft.
test('raw-json.js holt raw-zuerst und faellt auf den Snapshot zurueck', () => {
  const s = src(HELFER);
  assert.ok(s.includes(RAW), 'raw-json.js kennt die raw-Basis nicht');
  const fenster = s.slice(s.indexOf(RAW), s.indexOf(RAW) + 1600);
  assert.ok(/catch\s*[({]/.test(fenster),
    'raw-json.js faengt einen raw-Fehlschlag nicht ab — kein Rueckfall auf den Snapshot');
});

test('raw-json.js wird vor allen anderen Skripten geladen', () => {
  // Sonst ist `rawJson` beim ersten Aufruf undefined — und der Fehler sieht aus wie
  // „Daten fehlen", nicht wie „Skript-Reihenfolge".
  const html = src('season-finish-v2.html');
  const liste = html.slice(html.indexOf('var scripts = ['), html.indexOf('for (var i = 0'));
  const dateien = [...liste.matchAll(/"([^"]+\.js)"/g)].map((m) => m[1]);
  assert.equal(dateien[0], HELFER, `raw-json.js steht nicht an erster Stelle (sondern: ${dateien[0]})`);
});

for (const f of DATEN_LADER) {
  test(`${f} holt primär von raw/main`, () => {
    assert.ok(holtRawZuerst(src(f)),
      `${f} kennt weder die raw-Basis noch rawJson() — seine Daten hängen dann am Pages-Deploy (stündlich)`);
  });

  test(`${f} hat den Snapshot als Rückfall`, () => {
    if (nutztHelfer(src(f)) && !src(f).includes(RAW)) return;   // Rückfall steckt in raw-json.js
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
    // 07.09.2026 breiter als vorher: frueher wurde nur ein Literal direkt im fetch()
    // erkannt. results-v2.js holt seine URLs aus einer Liste (`fetch(url)`) und waere so
    // nie aufgefallen — genau die Datei, die den Befund ausgeloest hat.
    const holtJson = /fetch\(/.test(s) && /\.json\b/.test(s);
    if (!holtJson) continue;
    if (holtRawZuerst(s)) continue;
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
    try { return holtRawZuerst(src(f)); } catch { return true; }
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

test('kein jsdom-Harness testet eine Umgebung ohne raw-json.js', () => {
  // 07.09.2026: die Umstellung auf rawJson() hat zwoelf Render-Tests rot gemacht — zu Recht.
  // Sie luden renderer.js in ein DOM, in dem es window.rawJson nicht gab, also eine Umgebung,
  // die es im Browser nicht gibt. Der Fix ist billig (eine eval-Zeile mehr); ihn zu VERGESSEN
  // ist der teure Teil, weil der naechste rote Test wie ein Produktfehler aussieht.
  const dir = new URL('./', import.meta.url);
  const dateien = readdirSync(dir).filter((f) => f.endsWith('.test.mjs'));
  const fehlt = [];
  for (const f of dateien) {
    const s = readFileSync(new URL(f, dir), 'utf8');
    // Welche Dashboard-Dateien evaluiert dieser Harness?
    const evals = [...s.matchAll(/\.\.\/\.\.\/([\w.-]+\.js)/g)].map((m) => m[1]);
    const brauchtHelfer = evals.some((d) => {
      if (d === HELFER) return false;
      try { return nutztHelfer(src(d)); } catch { return false; }
    });
    if (brauchtHelfer && !s.includes(HELFER)) fehlt.push(f);
  }
  assert.deepEqual(fehlt, [],
    'laedt eine Datei, die rawJson() benutzt, ohne raw-json.js zu laden: ' + fehlt.join(', '));
});
