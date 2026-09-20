// tests/frontend/betfair-tafel-profit.test.mjs — 20.09.2026
//
// Lucas: „Ich will immer roi oder Profit, diese UG sagt mir nichts."
//
// Befund: der Profit stand in KEINER Zelle der Betfair-Tafel. Sie zeigte Liga, Markt, Spiele,
// Trefferquote, ROI, Konzentration, Zufluss — also genau die eine Zahl nicht, die er will.
//
// Warum die Spalte mehr ist als eine Bequemlichkeit, gemessen am Bestand vom 20.09.:
//   · Spitzenzeile „Swedish Allsvenskan · HT · +87 %"  =  +19,2 Einheiten aus 22 Spielen
//   · alle 609 Eimer mit n>=20 zusammen                =  -239,1 Einheiten (ROI -1,2 %)
//   · Nullmodell (jede Zeile mit ihrer eigenen Quote gewürfelt, KEINE Kante): der Zufall bringt
//     im Median 16 Zeilen über +40 % hervor und eine Spitze von +73 %. Beobachtet: 11 und +87 %.
//   · nachgespielt: Top 10 der ersten Septemberhälfte dort +100,1 Einheiten, danach -26,3.
//
// Fehlerklasse: ein Prozentsatz ohne seinen Nenner. 22 Spiele sehen aus wie ein Befund.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';

const ROOT = new URL('../../', import.meta.url);
const JS = readFileSync(new URL('betfair-radar.js', ROOT), 'utf8');
const PY = readFileSync(new URL('betfair_track_record.py', ROOT), 'utf8');

test('die Tafel hat eine Profit-Spalte', () => {
  const kopf = JS.slice(JS.indexOf('var head2 ='), JS.indexOf('var head2 =') + 400);
  assert.ok(kopf.includes("th('P/L', 1)"), 'keine P/L-Spalte im Tabellenkopf');
  assert.ok(kopf.indexOf("th('ROI', 1)") < kopf.indexOf("th('P/L', 1)"),
    'P/L gehört neben den ROI, nicht ans Ende');
});

test('der Profit kommt vom Produzenten, nicht aus roi*n', () => {
  // Sonst stünde dieselbe Rechnung zweimal im Repo — und die Fläche könnte von der
  // Bilanz abweichen, ohne dass es jemand merkt.
  assert.ok(PY.includes('"pl": round(b["roiSum"], 1)'), 'der Produzent schreibt `pl` nicht');
  const zelle = JS.slice(JS.indexOf("td(v.pl != null"), JS.indexOf("td(v.pl != null") + 200);
  assert.ok(zelle.includes('v.pl'), 'die Zelle liest `pl` nicht');
  assert.ok(!/v\.roi\s*\*\s*v\.n/.test(JS), 'das Frontend rechnet den Profit nach');
});

test('ein fehlendes Feld rendert als Lücke, nicht als Null', () => {
  // Rollout-Lücke: der Code wirkt erst, wenn der Produzent neu gelaufen ist. Ein Lauf lang
  // „—" ist ehrlich; eine 0.0 wäre eine Behauptung.
  const zelle = JS.slice(JS.indexOf("td(v.pl != null"), JS.indexOf("td(v.pl != null") + 200);
  assert.ok(zelle.includes("'—'"), 'fehlendes `pl` rendert nicht als —');
  assert.ok(!/v\.pl\s*\|\|\s*0/.test(JS), 'fehlendes `pl` wird zu 0 gemacht');
});

test('der Kopf nennt den gemessenen Rauschboden', () => {
  // Ohne diesen Satz ist eine nach ROI sortierte Liste eine Bestenliste des Zufalls, und sie
  // sieht genauso aus wie eine echte. Die Zahlen sind gemessen, nicht geschätzt.
  const t = JS;
  for (const zahl of ['16 Zeilen über +40 % ROI', '+73', '+87', '26,3', '19,2']) {
    assert.ok(t.includes(zahl), 'Rauschboden-Zahl fehlt: ' + zahl);
  }
});

test('die Sortierung bleibt der ROI', () => {
  // Lucas' ausdrückliche Wahl. Der Text erklärt die Liste, er stellt sie nicht um.
  const sort = JS.slice(JS.indexOf('var all = Object.keys(src)'), JS.indexOf('var total = all.length'));
  assert.ok(/b\.v\.roi \|\| -9\) - \(a\.v\.roi \|\| -9\)/.test(sort), 'nicht mehr nach ROI sortiert');
});
