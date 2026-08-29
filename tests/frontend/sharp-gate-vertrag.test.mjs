// tests/frontend/sharp-gate-vertrag.test.mjs — 29.08.2026 (Lucas: „prinzipiell checken, welche
// Wallets wir tracken, welche in den Push kommen, ob Schwellen sinnvoll sind").
//
// Es gab vier Definitionen von „scharf": _pwIsSharpScore (Dashboard/Shortlist/Push), _is_smart
// (Whale-Karten), eine handkopierte Klammer in poly_live_watch.py und tote Konstanten in
// poly_money_broad.py. Zwei davon lebten — und behandelten fehlende Daten genau gegenlaeufig:
// das sendende Gate liess unbekannten P&L durch, das anzeigende warf ihn raus. Gemessen am
// 29.08.: 42 gegen 16 Wallets bei 15 Schnittmenge.
//
// Jetzt ist sharp_gate.py die Definition und _pwIsSharpScore ihr Spiegel. Geteilten Code gibt es
// ueber die Sprachgrenze nicht — diesen Test gibt es. Er liest DIESELBE Fixture wie
// tests/test_sharp_gate.py. Laufen beide gruen, sagen Seite und Push dasselbe.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';

const ROOT  = new URL('../../', import.meta.url);
const SRC   = readFileSync(new URL('poly-wallets.js', ROOT), 'utf8');
const CASES = JSON.parse(readFileSync(new URL('tests/fixtures/sharp_gate_cases.json', ROOT), 'utf8')).cases;
const PY    = readFileSync(new URL('sharp_gate.py', ROOT), 'utf8');

// Nur die Gate-Funktionen aus der Datei ziehen — kein DOM, kein Cache, keine Fetches noetig.
function ladeGate() {
  const von = SRC.indexOf('const PW_SHARP_MIN_N=');
  const bis = SRC.indexOf('const PW_MONEY_MAJ');
  assert.ok(von > 0 && bis > von, 'Gate-Block in poly-wallets.js nicht gefunden');
  const g = {};
  // eslint-disable-next-line no-new-func
  new Function('exp', SRC.slice(von, bis)
    + '\nexp.isSharp=_pwIsSharpScore; exp.wilson=_pwWilsonLb; exp.minN=PW_SHARP_MIN_N; exp.z=PW_SHARP_Z;')(g);
  return g;
}
const G = ladeGate();

// Die Fixture spricht die rohe Tracker-Form; das Frontend bekommt die abgeleitete.
function alsFrontendScore(s) {
  const n = s.n || 0;
  return {
    n, wins: s.wins || 0,
    hit: n ? (s.wins || 0) / n : 0,
    avgClv: n ? (s.clvSumPP || 0) / n : 0,
    pnl: typeof s.pnl === 'number' ? s.pnl : 0,
    pnlKnown: typeof s.pnl === 'number',
  };
}

for (const c of CASES) {
  test(`Vertrag: ${c.name}`, () => {
    assert.strictEqual(G.isSharp(alsFrontendScore(c.score)), c.sharp, c.warum);
  });
}

test('JS und Python teilen dieselben Konstanten', () => {
  const pyN = /^SHARP_MIN_N = int\(os\.environ\.get\("SHARP_MIN_N"\) or (\d+)\)/m.exec(PY);
  const pyZ = /^SHARP_Z = float\(os\.environ\.get\("SHARP_Z"\) or ([\d.]+)\)/m.exec(PY);
  assert.ok(pyN && pyZ, 'Konstanten in sharp_gate.py nicht gefunden');
  assert.strictEqual(G.minN, Number(pyN[1]), 'n-Schwelle laeuft auseinander');
  assert.strictEqual(G.z, Number(pyZ[1]), 'z-Wert laeuft auseinander');
});

test('Wilson: gleiche Quote, mehr Stichprobe -> hoehere Untergrenze', () => {
  assert.ok(G.wilson(5, 9) < 0.5, '5/9 darf den Muenzwurf nicht schlagen');
  assert.ok(G.wilson(500, 900) > 0.5, '500/900 muss ihn schlagen');
  assert.strictEqual(G.wilson(0, 0), 0);
});

test('P&L kann nur ausschliessen, nie beweisen', () => {
  // Der Konviktions-Scorer hatte einen +0,5-Bonus fuer pnl>0. P&L ist die Poly-Gesamtbilanz ueber
  // alle Maerkte (Wahlen, Krypto) -- die Trefferquote misst nur unsere beobachteten Positionen.
  const scorer = SRC.slice(SRC.indexOf('let w=1.8;'), SRC.indexOf('let w=1.8;') + 200);
  assert.ok(!/sh\.pnl\s*>\s*0/.test(scorer),
    'der P&L-Bonus im Konviktions-Gewicht ist zurueck — das vermischt zwei verschiedene Welten');
});
