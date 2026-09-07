// tests/frontend/stake-ueber-norm.test.mjs — 07.09.2026
//
// Backlog: „Die 🚩 Auffällig-Ansicht ehrlich beschriften. Ihre Prämisse ist gemessen
// invertiert" + „Achse umstellen auf live × Einsatzgröße statt auffällig ja/nein".
//
// Der Fehler war nicht eine falsche Zahl, sondern eine Fläche, die mit ihrem NAMEN etwas
// behauptet, was die Daten daneben widerlegen. Solche Fehler wachsen nach: jemand tippt den
// richtigen Satz hinein, hundert Abrechnungen später stimmt er nicht mehr, und niemand merkt
// es, weil ein getippter Satz nicht rot wird. Deshalb prüfen diese Tests vor allem, dass das
// Urteil GERECHNET und nicht geschrieben ist.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
const ROOT = new URL('../../', import.meta.url);
const JS = readFileSync(new URL('stake-radar.js', ROOT), 'utf8');

// Modul in einer Mini-Umgebung laden — wie in stake-radar.test.mjs, kein DOM noetig.
function laden() {
  const sandbox = { window: {}, document: { getElementById: () => null, head: { appendChild() {} }, createElement: () => ({}) }, module: { exports: {} } };
  const fn = new Function('window', 'document', 'module', JS + '\nreturn module.exports;');
  return fn(sandbox.window, sandbox.document, sandbox.module);
}
const API = laden();

function block(von, bis) {
  const a = JS.indexOf(von), b = JS.indexOf(bis);
  assert.ok(a > 0, 'Anker weg: ' + von);
  assert.ok(b > a, 'Anker weg: ' + bis);
  return JS.slice(a, b);
}
const ANSICHT = block('var _SR_NP_ZEILEN', 'function _srBilanz()');
const CODE = ANSICHT.replace(/^\s*\/\/.*$/gm, '');   // Kommentare benennen absichtlich das Verbotene

// ── Der Name ────────────────────────────────────────────────────────────────
test('der Reiter behauptet nicht mehr, was er nicht belegen kann', () => {
  assert.ok(!/'🚩 Auffällig'/.test(JS),
    'der Reiter heisst wieder „Auffällig" — der Name allein ist die unbelegte Behauptung');
  assert.match(JS, /\['auffaellig', '📏 Über der Norm'\]/,
    'der Reiter beschreibt nicht, was er zeigt (Einsätze über der Norm ihrer Liga)');
  // Der Schluessel bleibt, sonst brechen Artefakt-Verweise und Verlinkungen.
  assert.match(JS, /SR_TAB === 'auffaellig' \? _srAuffaellig\(\)/, 'Tab wird nicht gerendert');
});

// ── Das Urteil ──────────────────────────────────────────────────────────────
test('das Urteil wird gelesen, nicht getippt', () => {
  assert.match(CODE, /u\.praemisse/, 'die Prämisse wird nicht aus dem Artefakt gelesen');
  assert.match(CODE, /normPhase/, 'der Block aus stake_analyse.py wird nicht benutzt');
  // Keine festen Prozentzahlen im Urteilstext: die veralten still.
  const saetze = CODE.match(/'[^']*%[^']*'/g) || [];
  const feste = saetze.filter((t) => /\d+[.,]\d+\s*%/.test(t));
  assert.deepEqual(feste, [],
    'eine feste Prozentzahl steht im Text — sie veraltet mit der nächsten Abrechnung: ' + feste.join(' | '));
});

test('alle drei Ausgänge sind formuliert — auch der, den wir gerade nicht haben', () => {
  for (const fall of ['gestuetzt', 'widerlegt']) {
    assert.ok(CODE.includes("'" + fall + "'"), `der Fall ${fall} fehlt`);
  }
  assert.match(ANSICHT, /weder belegt noch widerlegt/,
    'der offene Fall fehlt — und der ist bei dieser Datenmenge der häufigste');
});

test('fehlender Block sagt das, statt eine leere Fläche zu zeigen', () => {
  assert.match(ANSICHT, /normPhase.*fehlt|fehlt.*normPhase/s,
    'ohne den Block müsste dastehen, dass der Erzeuger noch nicht dran war');
});

// ── Die Achse ───────────────────────────────────────────────────────────────
test('die Achse ist Phase × Einsatzgrösse, nicht auffällig ja/nein', () => {
  assert.match(CODE, /_SR_NP_ZEILEN/, 'keine Phasen-Zeilen');
  for (const z of ['vor', 'live', 'alle']) {
    assert.ok(new RegExp(`'${z}':`).test(CODE), `Zeile ${z} fehlt`);
  }
  assert.match(CODE, /np\.spalten/, 'die Bänder kommen nicht aus dem Artefakt');
  // Wie bei der Spielklasse: keine zweite Schwelle im Renderer.
  assert.ok(!/faktor\s*[<>]=?\s*\d/.test(CODE),
    'im Renderer wird gegen eine eigene Schwelle verglichen — die gibt es dann zweimal');
});

test('die gepoolte Zeile ist als solche erkennbar', () => {
  // Sonst liest sie sich wie eine dritte Phase und wird mitgezählt.
  assert.match(CODE, /sr-pool/, 'die Summenzeile ist optisch nicht abgesetzt');
  assert.match(ANSICHT, /Gepoolt/, 'die Summenzeile sagt nicht, dass sie eine Summe ist');
});

// ── Gerendert ───────────────────────────────────────────────────────────────
const ZELLE = (n, flach, ug, og) => ({
  n, spiele: n, roi: flach, flach, flachUg: ug, flachOg: og,
  belegt: ug != null && ug > 0, belegtGegen: og != null && og < 0,
});

test('eine widerlegte Prämisse steht als Widerlegung da, nicht als Fund', () => {
  const np = {
    spalten: ['<1.5x', '1.5-3x', '3-6x', '6-15x', '>15x'],
    zeilen: ['vor', 'live', 'alle'],
    auffBaender: ['3-6x', '6-15x', '>15x'],
    kreuz: { alle: { '>15x': ZELLE(71, -0.221, -0.4168, -0.0252) } },
    urteil: {
      praemisse: 'widerlegt',
      folgen: [],
      gegen: [{ phase: 'alle', band: '>15x', n: 71, flach: -0.221, flachUg: -0.4168, flachOg: -0.0252 }],
    },
    warum: 'test',
  };
  const html = API._srNpUrteil(np);
  assert.match(html, /keine Empfehlung/, 'die Fläche sagt nicht, dass sie nichts empfiehlt');
  assert.match(html, /nicht<\/b>\s*mitzugehen|nicht<\/b> mitzugehen/,
    'die gemessene Richtung (dagegen) steht nicht da');
  assert.match(html, /-2[.,]5\s*%/, 'die Obergrenze aus dem Artefakt taucht nicht auf');
  assert.match(html, /n71/, 'die Basis (n) fehlt — ohne sie ist die Zahl eine Behauptung');
});

test('ohne Beleg in beide Richtungen wird nichts behauptet', () => {
  const html = API._srNpUrteil({
    spalten: [], auffBaender: ['3-6x'], kreuz: {},
    urteil: { praemisse: 'offen', folgen: [], gegen: [] },
  });
  assert.match(html, /weder belegt noch widerlegt/);
  assert.ok(!/keine Empfehlung.*Gegenteil/s.test(html),
    'der offene Fall übernimmt den Text des widerlegten');
});

test('ein Beleg FÜR die These würde auch dastehen', () => {
  // Sonst wäre die Fläche nur in eine Richtung ehrlich.
  const html = API._srNpUrteil({
    spalten: [], auffBaender: ['>15x'], kreuz: {},
    urteil: {
      praemisse: 'gestuetzt', gegen: [],
      folgen: [{ phase: 'live', band: '>15x', n: 40, flach: 0.2, flachUg: 0.05, flachOg: 0.4 }],
    },
  });
  assert.match(html, /trägt das hier/, 'ein Beleg für die These wird nicht angezeigt');
  assert.match(html, /vorwärts/, 'ohne den Hinweis auf die Vorregistrierung ist es Rückblick');
});
