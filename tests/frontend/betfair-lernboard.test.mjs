// tests/frontend/betfair-lernboard.test.mjs — 29.08.2026
//
// Lucas: „im Betfair-Radar sieht man alle Ligen — dort wissen wir dann auch, was trägt und was
// nicht. Ich will schon wissen, wo viel Geld reinfließt, aber auch: in dieser Liga ist das zwar
// okay, aber nicht gewinnbringend."
//
// Der Mechanismus dafür existiert seit dem 29.07. in sharp_signals/betfair_money.py: der
// Liga×Markt-Track moduliert die confidence des Card-Signals und DREHT ES UM, wo dem Geld zu
// folgen historisch verliert. Sichtbar war davon nichts — die Konsequenz stand als Textfragment
// in der Evidence-Zeile eines Picks. Man sah die Zahl, aber nicht, was sie anrichtet.
//
// Zwei Dinge sichern diese Tests:
//  1. Die Schwellen im Radar müssen die aus betfair_money.py sein. Laufen sie auseinander, zeigt
//     die Oberfläche „trägt", während das Signal fadet — schlimmer als gar keine Anzeige.
//  2. Die Aussage darf nie an der Farbe allein hängen (grün/rot: ΔE 2,2 für Deutan).
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';

const ROOT = new URL('../../', import.meta.url);
const JS = readFileSync(new URL('betfair-radar.js', ROOT), 'utf8');
const PY = readFileSync(new URL('sharp_signals/betfair_money.py', ROOT), 'utf8');

function ladeWirkung() {
  const von = JS.indexOf('var BF_TR_MIN_N');
  const bis = JS.indexOf('  // Kleine Confidence-Chip');
  assert.ok(von > 0 && bis > von, 'der Wirkungs-Block im Radar ist weg');
  const g = {};
  // eslint-disable-next-line no-new-func
  new Function('exp', 'C', JS.slice(von, bis)
    + '\nexp.f=bfTrackWirkung; exp.minN=BF_TR_MIN_N; exp.fade=BF_TR_FADE; exp.boost=BF_TR_BOOST;')(
    g, { dim: '#6e7681', mut: '#8b949e', back: '#3fb950', lay: '#f85149' });
  return g;
}
const W = ladeWirkung();

test('die Schwellen im Radar sind die aus betfair_money.py', () => {
  const n = /^MIN_TR_N\s*=\s*(\d+)/m.exec(PY);
  const f = /^TR_FADE_ROI\s*=\s*(-?[\d.]+)/m.exec(PY);
  const b = /^TR_BOOST_ROI\s*=\s*(-?[\d.]+)/m.exec(PY);
  assert.ok(n && f && b, 'Schwellen in betfair_money.py nicht gefunden');
  assert.strictEqual(W.minN, Number(n[1]), 'Mindest-Stichprobe läuft auseinander');
  assert.strictEqual(W.fade, Number(f[1]), 'Fade-Schwelle läuft auseinander');
  assert.strictEqual(W.boost, Number(b[1]), 'Boost-Schwelle läuft auseinander');
});

// 04.09.2026 (Lucas: „mach ma mal Betfair-Check"): die Aussage hing am PUNKTSCHÄTZER. Gemessen
// haben die Liga×Markt-Buckets Median n=5; von 1.641 tragen 3 überhaupt eine Rendite-Untergrenze,
// und davon keiner eine positive. Trotzdem galten 52 als „trägt" und 57 als „verliert". Seither
// entscheidet roiUg — und ohne Untergrenze sagt der Chip „sammelt", nicht „unauffällig".
test('jede Bandbreite bekommt ihre eigene Aussage', () => {
  assert.strictEqual(W.f({ n: 40, roi: 0.12, roiUg: 0.04 }).art, 'boost');
  assert.strictEqual(W.f({ n: 40, roi: -0.18, roiUg: -0.15 }).art, 'fade');
  assert.strictEqual(W.f({ n: 40, roi: 0.12, roiUg: 0.0 }).art, 'neutral');
  assert.strictEqual(W.f({ n: 7, roi: 0.5 }).art, 'sammelt', 'ohne Untergrenze wirkt nichts, egal wie gut');
  assert.strictEqual(W.f(null), null);
  assert.strictEqual(W.f({ n: 30 }), null, 'ohne ROI keine Aussage');
});

test('ein glänzender ROI ohne Untergrenze bewegt gar nichts', () => {
  // Der reale Fall: Serie A stand mit +52,1% auf n=10 als „🟢 80%" auf dem Board.
  assert.strictEqual(W.f({ n: 10, roi: 0.521 }).art, 'sammelt');
  assert.strictEqual(W.f({ n: 10, roi: -0.211 }).art, 'sammelt', 'und in die andere Richtung genauso');
});

test('genau an den Schwellen kippt es — nicht daneben', () => {
  assert.strictEqual(W.f({ n: 40, roi: 1, roiUg: W.boost }).art, 'neutral',
    'die Boost-Schwelle muss ÜBERSCHRITTEN sein — genau null ist kein Beleg');
  assert.strictEqual(W.f({ n: 40, roi: 1, roiUg: W.boost + 0.01 }).art, 'boost');
  assert.strictEqual(W.f({ n: 40, roi: -1, roiUg: W.fade }).art, 'fade', 'die Fade-Schwelle zählt mit');
});

test('die Aussage steht in Worten da, nicht nur in Farbe', () => {
  // Grün/Rot ist für Rot-Grün-Blinde praktisch ununterscheidbar. Wer die Farben nicht trennen
  // kann, muss die Zeile trotzdem lesen können.
  assert.match(W.f({ n: 40, roi: 0.12, roiUg: 0.04 }).txt, /trägt/);
  assert.match(W.f({ n: 40, roi: -0.18, roiUg: -0.15 }).txt, /verliert/);
  assert.match(W.f({ n: 40, roi: 0.12, roiUg: 0.04 }).sub, /verstärkt/);
  assert.match(W.f({ n: 40, roi: -0.18, roiUg: -0.15 }).sub, /fadet/);
});

test('unter der Schwelle zeigt der Chip den Fortschritt statt gar nichts', () => {
  // Vorher war der Chip unter n=12 komplett weg — „noch keine Daten" sah aus wie
  // „nie hingeschaut". Jetzt steht der Zähler da.
  const s = W.f({ n: 6, roi: 0.3 });
  assert.strictEqual(s.art, 'sammelt');
  assert.strictEqual(s.sub, 'n6/' + W.minN);
});

test('das Board zeichnet beide Entscheidungslinien in den Balken', () => {
  const von = JS.indexOf('function renderBfLernBoard');
  const fn = JS.slice(von, JS.indexOf('function renderTrackBoard'));
  assert.match(fn, /mark\(BF_TR_FADE/, 'die Fade-Linie fehlt im Balken');
  assert.match(fn, /mark\(BF_TR_BOOST/, 'die Boost-Linie fehlt im Balken');
  assert.match(fn, /left:50%;border-radius:0 4px 4px 0/, 'positiver Balken wächst nicht nach rechts');
  assert.match(fn, /right:50%;border-radius:4px 0 0 4px/, 'negativer Balken wächst nicht nach links');
});

test('das Board sagt auch im leeren Zustand, worauf es wartet', () => {
  const von = JS.indexOf('function renderBfLernBoard');
  const fn = JS.slice(von, JS.indexOf('function renderTrackBoard'));
  assert.match(fn, /noch nichts aktiv/);
  assert.match(fn, /abgerechneten Spiele erreicht/, 'der Leer-Zustand nennt die fehlende Bedingung nicht');
});
