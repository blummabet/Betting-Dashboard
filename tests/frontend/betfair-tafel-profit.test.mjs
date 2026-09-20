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

// ── „sagt was ab" (20.09.2026) ──────────────────────────────────────────────────────────────
// Lucas: „es ist nicht höher, obwohl dort eine höhere grüne Zahl steht. Ach, ich verstehe es
// nicht." Er hat die Tafel richtig gelesen — es fehlte der Maßstab daneben.
//
// Vorgeführt an seinen Daten: dieselben 32.055 Zeilen, Liga-Namen zufällig vertauscht (also ein
// garantiert NICHT vorhandener Liga-Effekt) — die Spitze sah aus wie vorher: +65 %, +63 %,
// +60 % bei 20–34 Spielen. Bei 2254 Eimern mit im Median 11 Spielen muss einer oben stehen.
//
// Die Spalte nennt, wie groß der Vorsprung bei DIESEM n sein müsste. Sie ist keine zweite
// Schwelle neben roiUg, sondern dieselbe in anderer Sprache — nachgewiesen in 2000 von 2000
// Zufallsfällen: roi > sichtbarAb gilt genau dann, wenn roiUg > 0.

test('die Spalte steht in der Tafel und kommt vom Produzenten', () => {
  const kopf = JS.slice(JS.indexOf('var head2 ='), JS.indexOf('var head2 =') + 500);
  assert.ok(kopf.includes("th('sagt was ab', 1)"), 'Spalte fehlt im Kopf');
  assert.ok(PY.includes('def _sichtbar_ab(n, summe, quadratsumme):'), 'Produzent rechnet sie nicht');
  assert.ok(PY.includes('"sichtbarAb"'), 'Produzent schreibt sie nicht ins Artefakt');
  assert.ok(!/Math\.sqrt\(\s*v\.n\s*\)/.test(JS), 'das Frontend rechnet die Schranke selbst nach');
});

// Ausgeführt statt gegrept: ein Test, der nur Zeichenketten sucht, hält jeder Umbenennung
// stand und keiner Logik-Änderung. Genau das ist mir hier zuerst passiert — die Mutation
// „Häkchen immer setzen" ist durchgerutscht, weil der Vergleich noch im Farb-Argument stand.
function zelle() {
  const hol = (name) => {
    const a = JS.indexOf('function ' + name + '(');
    assert.ok(a > 0, 'Funktion weg: ' + name);
    let t = 0;
    for (let j = JS.indexOf('{', a); j < JS.length; j++) {
      if (JS[j] === '{') t++;
      else if (JS[j] === '}') { t--; if (!t) return JS.slice(a, j + 1); }
    }
    throw new Error('Klammern offen: ' + name);
  };
  return new Function("const C={back:'#0f0'};" + hol('_bfSagtWas') + hol('_bfSagtWasTxt')
    + 'return {ok:_bfSagtWas, txt:_bfSagtWasTxt};')();
}

test('das Häkchen kommt nur, wenn der ROI die Schranke schlägt', () => {
  const z = zelle();
  assert.equal(z.ok({ roi: 0.87, sichtbarAb: 0.64 }), true, 'ROI über der Schranke → ✓');
  assert.equal(z.ok({ roi: 0.30, sichtbarAb: 0.64 }), false, 'ROI unter der Schranke → kein ✓');
  assert.equal(z.ok({ roi: 0.64, sichtbarAb: 0.64 }), false, 'gleichauf ist nicht darüber');
  assert.ok(z.txt({ roi: 0.87, sichtbarAb: 0.64 }).includes('✓'));
  assert.ok(!z.txt({ roi: 0.30, sichtbarAb: 0.64 }).includes('✓'));
  assert.ok(z.txt({ roi: 0.87, sichtbarAb: 0.64 }).startsWith('+64%'), 'die Schranke selbst fehlt');
});

test('zu wenig Spiele rendert als Lücke, nicht als Häkchen', () => {
  const z = zelle();
  assert.equal(z.txt({ roi: 5.0, sichtbarAb: null }), '—', 'ohne Schranke keine Zahl');
  assert.equal(z.ok({ roi: 5.0, sichtbarAb: null }), false, 'ohne Schranke kein ✓');
  assert.equal(z.ok({ roi: null, sichtbarAb: 0.4 }), false, 'ohne ROI kein ✓');
});

test('der Fußtext nennt, wie viele Häkchen schon der Zufall bringt', () => {
  // OHNE diesen Satz wäre die Spalte eine neue Falle: 48 Häkchen sehen nach 48 Ligen aus.
  // Die Schranke lässt 5 % durch, bei 1257 messbaren Zeilen sind das ~63 — also MEHR als
  // die 48, die dastehen.
  assert.ok(JS.includes('_nMessbar * 0.05'), 'die Zufallserwartung wird nicht gerechnet');
  assert.ok(JS.includes('heißt ') && JS.includes('nicht „diese Liga trägt"'),
    'das Häkchen wird nicht als das benannt, was es ist');
});

test('gezählt wird über alle Eimer, nicht über die gezeigten 500', () => {
  // Sonst hinge die Zahl am Anzeige-Deckel statt am Bestand.
  const z = JS.slice(JS.indexOf('var _nMessbar'), JS.indexOf('var _nMessbar') + 400);
  assert.ok(z.includes('all.filter'), 'über rows statt über all gezählt');
  assert.ok(!z.includes('rows.filter'), 'über rows statt über all gezählt');
});
