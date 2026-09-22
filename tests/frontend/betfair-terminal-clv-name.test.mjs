// tests/frontend/betfair-terminal-clv-name.test.mjs — 22.09.2026
//
// 🔴 Lucas: „Kannst du den ganzen Betfair-Radar auch checken, ob wir da CLV so implementiert
// haben, dass es irgendwas blockt oder so? Auch das Betfair-Terminal."
//
// Ergebnis der Prüfung: im Terminal blockt der CLV nichts. Das Auto-Mute („🔇 Nicht handelbar")
// läuft seit dem 04.09.2026 auf der RENDITE-Untergrenze `roiUg` — davor hatte es auf einem
// Punktschätzer gemutet und dabei Man City, PSG und Arsenal vom Board geblendet.
//
// Die Spalte hieß trotzdem weiter „CLV-Bucket". Das ist die teuerste Sorte falscher
// Beschriftung: sie behauptet genau das, was Lucas abgestellt haben will, obwohl der Code es
// nicht tut. Fehlerklasse: **eine Beschriftung, die etwas anderes verspricht als die Zahl
// darunter** — dieselbe, die am 01.09. im Poly-Terminal eine Spalte „CLV-Bucket" nannte, die
// den ROI zeigte.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';

const JS = readFileSync(new URL('../../betfair-radar.js', import.meta.url), 'utf8');
const ohneKommentar = JS.split('\n').filter(z => !z.trim().startsWith('//')).join('\n');

test('⭐ das Terminal-Mute entscheidet auf der Rendite, nicht auf dem CLV', () => {
  const fn = ohneKommentar.slice(ohneKommentar.indexOf('function _tMute'),
                                ohneKommentar.indexOf('var _TSK'));
  assert.ok(/roiUg/.test(fn), '_tMute liest die Rendite-Untergrenze nicht mehr');
  assert.ok(!/clv/i.test(fn),
    '_tMute fragt wieder den CLV — Lucas, 22.09.2026: „es darf kein Kriterium sein, dass '
    + 'irgendwas gekickt wird"');
});

test('⭐ keine Spalte verspricht CLV und zeigt Rendite', () => {
  assert.ok(!/th\('CLV-Bucket'\)/.test(ohneKommentar),
    'die Spaltenüberschrift heißt wieder „CLV-Bucket" und zeigt eine Rendite-Untergrenze');
  assert.ok(/th\('Liga-Bilanz'\)/.test(ohneKommentar), 'die Spalte fehlt ganz');
});

test('die Legende sagt, dass hier KEIN CLV urteilt', () => {
  assert.match(JS, /Liga-Bilanz = hist\. Rendite je Liga[^<]*KEIN CLV/);
});

test('der CLV bleibt als Kennzahl sichtbar — entfernt ist das Kriterium, nicht die Zahl', () => {
  assert.match(JS, /CLV vs Betfair-Close/);
  assert.match(JS, /CLV vs Pinnacle/);
});

test('⭐ im ganzen Radar entscheidet kein CLV über Sichtbarkeit', () => {
  // Die Eigenschaft über die ganze Datei, nicht über eine Stelle: jede Zeile, die einen
  // CLV-Wert in einer Bedingung benutzt, muss eine Anzeige sein (Farbe, Text) — kein Filter.
  const treffer = ohneKommentar.split('\n')
    .map((z, i) => [i + 1, z])
    .filter(([, z]) => /clv/i.test(z))
    .filter(([, z]) => /\.filter\(|continue|return (false|null)|&& *!|\|\| *!/.test(z));
  assert.deepStrictEqual(treffer, [],
    'CLV steht wieder in einer Auswahl-Bedingung:\n' + treffer.map(t => t.join(': ')).join('\n'));
});
