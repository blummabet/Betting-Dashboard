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
    + '\nexp.isSharp=_pwIsSharpScore; exp.wilson=_pwWilsonLb; exp.minN=PW_SHARP_MIN_N; exp.z=PW_SHARP_Z;'
    + '\nexp.grade=_pwSharpGrade; exp.floor=PW_SHARP_GRADE_FLOOR;')(g);
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


// ── Der Regler (01.09.2026) ──────────────────────────────────────────────────
// Gemessen: das binaere Gate liess eine Wallet mit 60% aus 65 Plays (Wilson-UG 49,8%) genauso
// aussen vor wie eine mit 30% aus 8 — und diese Bande lieferte out of sample den besten CLV
// (+0,94pp, n=136). Der Regler behebt die Form. Beide Sprachen muessen denselben Grad rechnen,
// sonst zeigt die Seite eine andere Conviction als der Tracker abrechnet.

test('Regler: JS trifft denselben Grad wie die Fixture', () => {
  for (const c of CASES) {
    if (typeof c.grade !== 'number') continue;
    const g = G.grade(alsFrontendScore(c.score));
    assert.ok(Math.abs(g - c.grade) < 0.005,
      `${c.name}: JS ${g.toFixed(3)} vs erwartet ${c.grade} — ${c.warum}`);
  }
});

test('Regler: voller Grad und das strenge Gate fallen zusammen', () => {
  for (const c of CASES) {
    assert.strictEqual(G.isSharp(alsFrontendScore(c.score)), G.grade(alsFrontendScore(c.score)) >= 1,
      `${c.name}: Schalter und Regler sind uneinig`);
  }
});

test('Regler: JS und Python teilen den Boden', () => {
  const pyFloor = /^GRADE_FLOOR_LB = float\(os\.environ\.get\("SHARP_GRADE_FLOOR"\) or ([\d.]+)\)/m.exec(PY);
  assert.ok(pyFloor, 'GRADE_FLOOR_LB in sharp_gate.py nicht gefunden');
  assert.strictEqual(G.floor, Number(pyFloor[1]), 'der Boden der Rampe laeuft auseinander');
});

test('Der Beleggrad haengt wirklich im Konviktions-Gewicht', () => {
  // Sonst ist der Regler eingebaut und feuert nie — die Bauform, die uns schon mehrfach
  // Wochen gekostet hat (Fix da, Wirkung null).
  const von = SRC.indexOf('let w=1.8;');
  const scorer = SRC.slice(von, von + 2000);
  assert.ok(/w\s*\*=\s*_gr/.test(scorer),
    'das Konviktions-Gewicht multipliziert den Beleggrad nicht mehr');
  assert.ok(/vielversprechende Wallet/.test(scorer),
    'die Begruendungs-Zeile unterscheidet belegt und vielversprechend nicht mehr');
});

test('Das Etikett ist strenger als das Gewicht — sonst verwaessern die Eimer', () => {
  // Gewicht darf fein abgestuft sein; der TAG bildet die Eimer, in denen _pwCalibConv und das
  // Freigabe-Register rechnen. Liefe jeder 0,1-Beitrag als 'sharp' mit, stuende ein Play mit
  // 0,23 Gewicht im selben Eimer wie eines mit 2,8 — der Eimer misst dann nichts mehr.
  const von = SRC.indexOf('let w=1.8;');
  const scorer = SRC.slice(von, von + 2000);
  assert.ok(/_gr>=PW_SHARP_TAG_MIN_GRADE\?'sharp':null/.test(scorer.replace(/\s+/g, '')),
    'der Tag haengt nicht mehr an einer eigenen Schwelle');
  const m = /const PW_SHARP_TAG_MIN_GRADE=([\d.]+)/.exec(SRC);
  assert.ok(m, 'PW_SHARP_TAG_MIN_GRADE fehlt');
  const tagMin = Number(m[1]);
  assert.ok(tagMin > G.floor && tagMin <= 1,
    `Tag-Schwelle ${tagMin} muss ueber dem Rampen-Boden ${G.floor} und hoechstens 1 liegen`);
});
