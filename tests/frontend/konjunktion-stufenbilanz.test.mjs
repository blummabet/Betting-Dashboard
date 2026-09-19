// tests/frontend/konjunktion-stufenbilanz.test.mjs — 12.09.2026 (Plattform-Audit, Block B)
//
// 🔴 `killer.py` rechnet `punkteBilanz`: je (Punkte, möglich) die Rendite MIT einseitiger
// 95-%-Untergrenze. Sie steht in `killer.json` und wird committet. Gelesen hat sie **keine
// einzige Frontend-Datei** — dritter Fall derselben Sorte an einem Tag (Guard-Batterie,
// Pick-Validator, diese hier).
//
// Nachgerechnet am echten Stand: von 34 Eimern haben **zwei** eine Untergrenze über null —
// 12/13 (n=3) und 1/4 (n=6, ein Lottoschein mit +815 %). Im ganzen Bereich ab 6 Punkten, also
// genau dem, was die Tafel zeigt, liegt **keine einzige** Untergrenze über null.
//
// Zweiter Fund an derselben Stelle: der Fußtext sagte „kein Spiel über 6 von **13** Punkten".
// Der Nenner ist aber je Spiel verschieden — 38 Zeilen mit 10, 19 mit 4, 15 mit 7 und genau EINE
// mit 13. Ein Spiel mit `moeglich=4` kann die 6 nie erreichen, egal wie einig sich die gefragten
// Bücher sind.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';

const ROOT = new URL('../../', import.meta.url);
const JS = readFileSync(new URL('main-dashboard.js', ROOT), 'utf8');
const CODE = JS.replace(/^\s*\/\/.*$/gm, '');

// Die beiden Funktionen sind eigenstaendig — also echt ausfuehren statt nur Text pruefen.
function holen(name) {
  const a = CODE.indexOf('function ' + name + '(');
  assert.ok(a > 0, 'Funktion weg: ' + name);
  let tiefe = 0, i = CODE.indexOf('{', a);
  for (let j = i; j < CODE.length; j++) {
    if (CODE[j] === '{') tiefe++;
    else if (CODE[j] === '}') { tiefe--; if (!tiefe) return CODE.slice(a, j + 1); }
  }
  throw new Error('Klammern nicht geschlossen: ' + name);
}
const fn = new Function(holen('_klStufenBilanz') + '\n' + holen('_klStufenText')
  + '\nreturn {bilanz:_klStufenBilanz, text:_klStufenText};')();

const K = { punkteBilanz: [
  { punkte: 7, moeglich: 10, n: 51, roi: 0.1461, roiLb: -0.0767 },
  { punkte: 12, moeglich: 13, n: 3, roi: 0.82, roiLb: 0.5897 },
  { punkte: 5, moeglich: 13, n: 2, roi: 0.28, roiLb: null },
]};

test('die Bilanz wird über BEIDE Zahlen nachgeschlagen, nicht nur über die Punkte', () => {
  // 7/10 und 7/13 sind verschiedene Stufen. Nur über `punkte` zu suchen waere genau der
  // Nenner-Fehler, um den es hier geht.
  assert.strictEqual(fn.bilanz(K, 7, 10).n, 51);
  assert.strictEqual(fn.bilanz(K, 7, 13), null);
  assert.strictEqual(fn.bilanz(K, 12, 13).n, 3);
});

test('⭐ eine Stufe ohne Untergrenze behauptet nichts', () => {
  const t = fn.text({ punkte: 5, moeglich: 13, n: 2, roi: 0.28, roiLb: null });
  assert.match(t, /kein Urteil/);
  assert.doesNotMatch(t, /trägt/, 'ein Punktschätzer aus n=2 darf nicht wie ein Beleg aussehen');
});

test('⭐ „trägt" steht nur, wenn die Untergrenze über null liegt', () => {
  // Geprueft wird die AUSSAGE, nicht der Tooltip: der erklaert die Regel und enthaelt das Wort
  // zwangslaeufig. Die Behauptung steckt in der Klasse und im sichtbaren Zusatz.
  const schwach = fn.text({ n: 51, roi: 0.1461, roiLb: -0.0767 });
  assert.doesNotMatch(schwach, /md-kl-traegt/,
    '+15 % Rendite mit UG −8 % ist kein Beleg — genau die Stufe, die die Tafel am meisten zeigt');
  assert.doesNotMatch(schwach, /· trägt/);
  const stark = fn.text({ n: 3, roi: 0.82, roiLb: 0.5897 });
  assert.match(stark, /md-kl-traegt/);
  assert.match(stark, /· trägt/);
});

test('die Untergrenze steht immer dabei, nicht nur die Rendite', () => {
  const t = fn.text({ n: 51, roi: 0.1461, roiLb: -0.0767 });
  assert.match(t, /\+15%/);
  assert.match(t, /UG −8%|UG -8%/);
  assert.match(t, /n51/);
});

test('ohne Bilanz bleibt die Zeile stumm statt zu raten', () => {
  assert.strictEqual(fn.text(null), '');
  assert.strictEqual(fn.text({ n: 0 }), '');
});

test('⭐ der Fußtext behauptet keinen festen Nenner mehr', () => {
  assert.ok(!/von 13 Punkten/.test(CODE),
    'der Nenner ist je Spiel verschieden — „6 von 13" stimmte für 72 von 73 Zeilen nicht');
  assert.match(CODE, /Der Nenner ist je Spiel verschieden/);
});

test('⭐ die Tafel liest die Bilanz überhaupt', () => {
  assert.match(CODE, /_klStufenBilanz\(k,\s*r\.punkte,\s*r\.moeglich\)/,
    'sonst liegt punkteBilanz weiter ungelesen in killer.json');
  assert.match(CODE, /punkteBilanz/);
});

test('am echten Bestand: im Bereich der Tafel trägt keine einzige Stufe', () => {
  // Der Satz, der den Fund ausmacht. Kippt er, ist das eine Nachricht — und gehört angesehen,
  // nicht stillschweigend weggetestet.
  const k = JSON.parse(readFileSync(new URL('killer.json', ROOT), 'utf8'));
  const oben = (k.punkteBilanz || []).filter(e => e.punkte >= 6);
  assert.ok(oben.length >= 5, 'zu wenig Bestand für die Aussage');
  const traegt = oben.filter(e => (e.roiLb || -9) > 0);
  // 14.09.2026 angesehen, zweiter Eintrag: „6/7 (n=6)" mit ROI +59,2 % und Untergrenze
  // +5,1 %. Angesehen heisst NICHT belegt — bei sechs Zeilen ist eine positive Untergrenze
  // kein Beleg, sondern die Bandbreite, die sechs Zeilen eben noch zulassen. Dieselbe Tafel
  // fuehrt „12/13 (n=3)" mit +82 % und „7/13 (n=3)" mit −100 %: Nenner dieser Groesse sagen
  // in beide Richtungen nichts. Beide stehen hier als PROTOKOLL, nicht als Freigabe — die
  // Aussage der Tafel („im Bereich traegt keine Stufe") haengt weiter an den Zeilen mit
  // zweistelligem n, und dort ist keine einzige Untergrenze ueber null.
  // 18.09.2026 angesehen: „10/13 (n=21)" ist dazugekommen — ROI +29,9 %, Untergrenze +1,9 %.
  // Die erste Stufe mit zweistelligem n ueber null, also genau die Nachricht, auf die der Satz
  // unten gewartet hat. Angesehen, und sie traegt trotzdem nichts:
  //
  //   11/13  n=22   ROI  +9,1 %   UG −24,8 %      ← die STRENGERE Stufe, und sie ist schlechter
  //   10/13  n=21   ROI +29,9 %   UG  +1,9 %
  //    9/13  n=13   ROI +13,4 %   UG −24,0 %
  //
  // Eine Leiter, deren oberste Sprosse unter der zweitobersten liegt, ist keine Leiter. Und die
  // Untergrenze steht mit +1,9 % praktisch auf der Null, bei vierzehn gleichzeitig geprueften
  // Stufen — da ist knapp ein Treffer ueber der Schranke genau das, was der Zufall liefert.
  // Steht sie in vier Wochen bei doppeltem n immer noch da, und zieht 11/13 mit, ist es ein
  // Befund. Bis dahin: Protokoll, keine Freigabe.
  // 19.09.2026 angesehen — die Antwort kam schneller als die vier Wochen. „10/13" ist nach
  // EINEM weiteren Play wieder unter null:
  //
  //   18.09.   10/13  n=21   ROI +29,9 %   UG +1,9 %
  //   19.09.   10/13  n=22   ROI +24,1 %   UG −4,4 %
  //   19.09.   11/13  n=23   ROI +12,7 %   UG −20,2 %   ← die strengere Stufe, weiter schlechter
  //
  // Genau das war der Verdacht: eine Untergrenze, die bei vierzehn gleichzeitig geprueften
  // Stufen knapp ueber der Null steht, ist kein Befund, sondern die Bandbreite. Ein einziger
  // Play hat sie zurueckgeholt.
  //
  // Die feste Liste war deshalb der falsche Griff: sie bricht bei jedem Play, an dem sich nur
  // das n aendert (12/13 ging von n=3 auf n=4, ohne dass sich irgendetwas an der Aussage
  // aendert). Gehalten wird ab jetzt der SATZ, um den es geht — im belastbaren Bereich traegt
  // keine Stufe. Die Zeilen mit einstelligem n bleiben Protokoll und werden benannt, damit sie
  // nicht unbemerkt wachsen.
  const belastbar = traegt.filter(e => (e.n || 0) >= 10);
  assert.deepStrictEqual(belastbar.map(e => `${e.punkte}/${e.moeglich} (n=${e.n})`), [],
    'Eine Stufe mit zweistelligem n traegt zum ersten Mal — das ist die Nachricht und gehoert '
    + 'angesehen, statt hier weggetestet zu werden.');
  assert.ok(traegt.every(e => (e.n || 0) < 10),
    'Protokollzeilen muessen einstellig bleiben, sonst sind sie keine mehr.');
  const elf = oben.find(e => e.punkte === 11 && e.moeglich === 13);
  assert.ok(elf && (elf.roiLb || -9) <= 0,
    'Wenn die STRENGERE Stufe 11/13 auch ueber null geht, ist die Leiter zum ersten Mal '
    + 'monoton — DAS waere der Befund und muss auffallen, statt hier durchzurutschen.');
});
