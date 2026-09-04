// tests/frontend/cards-engine-netto.test.mjs — 04.09.2026
//
// Lucas: „ja räum das bitte noch auf."
//
// Auf der Elche-Card standen sechs Kacheln und GAR KEIN Netto:
//
//   Verletzungen −6.8 · Form-Trend +2.1 · H2H −1.0 · xG +1.3 · Chancen +1.1 · Frische +1.6
//
// Drei Dinge liefen zusammen:
//   1. Das Netto war versteckt, weil |+0.17| < 0.5 als „nicht nennenswert" galt — damit fehlte
//      der einzige Anker, und die Kacheln wirkten wie das ganze Ergebnis.
//   2. Die Kacheln summieren nicht auf das Netto (−0.44 vs +0.17) und sollen es auch nicht:
//      combined_score_pp ist ein nach Konfidenz und Gewicht gemittelter Wert. Beides ist
//      richtig, nebeneinander ohne Erklärung sieht es nach Rechenfehler aus.
//   3. slice(0,6) schnitt in Registry-Reihenfolge ab, ohne Hinweis. Auf Elche fiel
//      move_following +1.2 heraus — nicht weil es klein war, sondern weil es hinten stand.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';

const JS = readFileSync(new URL('../../wm2026-renderer.js', import.meta.url), 'utf8');

function grid() {
  const von = JS.indexOf('  function _engineSignalGridHtml(');
  const bis = JS.indexOf('  // Spiel „vergangen/gespielt"?');
  assert.ok(von > 0 && bis > von, '_engineSignalGridHtml nicht gefunden');
  const META = { injury: ['🩹', 'Verletzungen'], form_trend: ['📈', 'Form-Trend'],
                 h2h_pattern: ['⚔️', 'H2H'], xg_strength: ['🥅', 'xG-Stärke'],
                 chance_creation: ['🎨', 'Chancen'], freshness_leg: ['💨', 'Frische'],
                 move_following: ['•', 'move following'] };
  const g = {};
  // eslint-disable-next-line no-new-func
  new Function('exp', '_SIG_META', JS.slice(von, bis) + '\nexp.f=_engineSignalGridHtml;')(g, META);
  return g.f;
}
const F = grid();

// Die echte Elche-Card (liga-data.json, ESP-4-797-548, „Über 2.5 Tore").
const ELCHE = {
  signalAdjustmentPP: 0.17,
  signals: [
    { name: 'injury', score: -6.75, evidence: 'Offense-Ausfälle' },
    { name: 'form_trend', score: 2.13, evidence: 'Form' },
    { name: 'h2h_pattern', score: -1.00, evidence: 'H2H' },
    { name: 'xg_strength', score: 1.31, evidence: 'xG' },
    { name: 'chance_creation', score: 1.12, evidence: 'Chancen' },
    { name: 'freshness_leg', score: 1.55, evidence: 'Frische' },
    { name: 'move_following', score: 1.20, evidence: 'Move' },
  ],
};

test('ein Netto nahe null wird trotzdem gezeigt — es ist der einzige Anker', () => {
  const h = F(ELCHE);
  assert.match(h, /\+0\.2pp Netto/, 'das Netto fehlte auf der echten Card komplett');
});

test('das Netto sagt dazu, dass es kein Summenwert ist', () => {
  const h = F(ELCHE);
  assert.match(h, /Ø gew\./, 'ohne Kennzeichnung liest man es als Summe der Kacheln');
  assert.match(h, /KEINE Summe der Kacheln/, 'die Erklärung gehört in den Titel');
  assert.match(h, /-0\.4pp/, 'und nennt, was die Kacheln tatsächlich ergäben');
});

test('abgeschnittene Signale werden ausgewiesen statt verschwiegen', () => {
  const h = F(ELCHE);
  assert.match(h, /\+1 weiteres Signal/, 'das siebte Signal fiel vorher spurlos raus');
  assert.match(h, /zählen mit, aber nicht abgebildet/);
});

test('das abgeschnittene Signal steht mit Namen und Wert im Titel', () => {
  // „+1 weitere" wäre sonst selbst wieder eine Lücke.
  assert.match(F(ELCHE), /title="[^"]*H2H -1\.0pp/);
});

test('die stärksten Signale stehen vorn, nicht die erstbesten', () => {
  const h = F(ELCHE);
  const pos = (n) => h.indexOf(n);
  assert.ok(pos('Verletzungen') < pos('Chancen'), '−6.8 trägt das Ergebnis, +1.1 nicht');
  // move_following (+1.2) schlägt h2h_pattern (−1.0) im Betrag → h2h ist der Abgeschnittene.
  assert.ok(pos('move following') > 0, 'das vorher abgeschnittene Signal ist jetzt sichtbar');
});

test('sechs oder weniger Signale bekommen keine Rest-Zeile', () => {
  const sechs = { signalAdjustmentPP: 1.4, signals: ELCHE.signals.slice(0, 6) };
  assert.ok(!/weitere/.test(F(sechs)));
});

test('ohne Signale bleibt der Block ganz weg', () => {
  assert.strictEqual(F({ signals: [] }), '');
  assert.strictEqual(F({}), '');
});

test('ohne Netto-Wert wird keines erfunden', () => {
  const h = F({ signals: ELCHE.signals.slice(0, 3) });
  assert.ok(!/Netto/.test(h), 'fehlendes Netto ist nicht 0');
});
