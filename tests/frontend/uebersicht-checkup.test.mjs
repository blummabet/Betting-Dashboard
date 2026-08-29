// tests/frontend/uebersicht-checkup.test.mjs — 29.08.2026
//
// Drei Befunde aus dem Übersicht-Checkup. Alle drei haben eines gemeinsam: die Kachel hat
// nicht geschwiegen, sie hat etwas Falsches behauptet — und das ist schlimmer als eine Lücke.
//
//  1. „Beste Cards" schrieb ein hartes '+' vor jede Edge. Heute standen dort drei MLS-Picks mit
//     −1pp, −3pp und −4pp — angezeigt als „+-1pp", „+-3pp", „+-4pp". Wer nur die Kachel liest,
//     sieht drei Picks mit Kante, obwohl alle drei BET-Cards des Tages gegen die Linie stehen.
//
//  2. „Top-Wetten jetzt" setzte bei Betfair-Geld-Zeilen k = now, weil der Zufluss-Feed keinen
//     Anpfiff mitlieferte. Ergebnis: immer „⏱ 0m". Liverpool–Forest stand als „Anpfiff jetzt"
//     in der Liste, während der Poly-Block zwei Zeilen weiter „in 2h" sagte. Jetzt kommt der
//     Anpfiff aus dem Feed; fehlt er, bleibt die Uhr weg.
//
//  3. Die Signal-Zelle „Wallets · 57% · 152 von 266" las sich als „152 von 266 Wallets auf
//     dieser Seite". Es ist die lebenslange Bilanz der scharfen Wallets. Aufgefallen ist es,
//     weil zwei verschiedene Japan-Spiele exakt dieselbe Zahl trugen.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';

const ROOT = new URL('../../', import.meta.url);
const MD  = readFileSync(new URL('main-dashboard.js', ROOT), 'utf8');
const BOV = readFileSync(new URL('build_betfair_overview.py', ROOT), 'utf8');

test('Beste Cards: negative Edge wird nicht als Plus verkauft', () => {
  const zeile = MD.split('\n').find(l => l.includes("edgePP != null") && l.includes("pp'"));
  assert.ok(zeile, 'die Edge-Zeile der Cards-Kachel ist weg');
  assert.ok(!/' · \+' \+ Math\.round/.test(zeile),
    "hart vorangestelltes '+' ist zurück — negative Edge erscheint dann als „+-3pp\"");
  assert.match(zeile, /> 0 \? '\+' : ''/, 'das Vorzeichen hängt nicht mehr am Wert');
});

test('Top-Wetten: Betfair-Geld-Zeilen erfinden keinen Anpfiff mehr', () => {
  const i = MD.indexOf("put({ id: 'bf' + mid(");
  assert.ok(i > 0, 'der Betfair-Zufluss-Kandidat ist weg');
  const block = MD.slice(i, i + 400);
  assert.ok(!/^\s*k: now,/m.test(block), 'k: now ist zurück — jede Zeile zeigt wieder „0m"');
  assert.match(block, /k: x\.kickoff \? Date\.parse/, 'der Anpfiff kommt nicht aus dem Feed');
});

test('Ohne bekannten Anpfiff wird gar keine Uhr gezeigt', () => {
  assert.match(MD, /var min = isFinite\(x\.k\)/, 'NaN/now landet wieder ungeprüft in der Uhr');
  assert.match(MD, /\(ko \? '<span class="md-jz-ko">/, 'der Uhr-Chip ist nicht mehr optional');
});

test('der Zufluss-Feed liefert den Anpfiff mit', () => {
  const i = BOV.indexOf('def flow_list');
  const fn = BOV.slice(i, BOV.indexOf('\ndef ', i + 10));
  assert.match(fn, /"kickoff": m\.get\("kickoff"\)/,
    'flow_list schreibt keinen kickoff — dann hat die Übersicht wieder nichts, woraus sie die Zeit nehmen kann');
});

test('die Wallet-Zelle nennt Wallets und Bilanz getrennt', () => {
  assert.ok(!/sh\.wins \+ ' von ' \+ sh\.n/.test(MD),
    '„152 von 266" ist zurück — das liest jeder als Anzahl Wallets');
  assert.match(MD, /sh\.count/, 'die echte Wallet-Anzahl (sh.count) wird immer noch nicht gezeigt');
  assert.match(MD, /lifetime/, 'nichts sagt, dass n die lebenslange Bilanz ist');
});
