// tests/frontend/uebersicht-bftrack.test.mjs — 29.08.2026
//
// Lucas: „das müsste man ja auf der Übersicht auch anpassen — mit dem Element haben wir ja quasi
// schon mal was Ähnliches begonnen." Gemeint ist „Top-Wetten jetzt", das Cards, Poly, Betfair und
// Money-Map in einer Liste zusammenführt.
//
// Das Problem war unsichtbar: die Poly-Zeilen bekommen ihren Rang aus der Conviction und ziehen
// deshalb bei jeder Neugewichtung automatisch mit. Die Betfair-Zeilen hingen an festen
// Konstanten (42 + pp bzw. 46 + €) — und hatten obendrein einen BEDINGUNGSLOS reservierten
// Platz. Eine Betfair-Zeile kam also auch dann in die Top-Wetten, wenn ihr Liga×Markt-Eimer
// historisch nie etwas getragen hat.
//
// Jetzt greift derselbe Track, der in den Cards das Signal verstärkt oder umdreht. In den Cards
// wird ein verlierender Eimer GEFADET; auf der Übersicht gibt es nichts umzudrehen — eine Zeile
// in „Top-Wetten jetzt" ist eine Empfehlung. Also fliegt sie raus statt gedreht zu werden.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';

const ROOT = new URL('../../', import.meta.url);
const MD = readFileSync(new URL('main-dashboard.js', ROOT), 'utf8');
const RADAR = readFileSync(new URL('betfair-radar.js', ROOT), 'utf8');
const PY = readFileSync(new URL('sharp_signals/betfair_money.py', ROOT), 'utf8');

test('die Schwellen stehen an drei Stellen — und überall gleich', () => {
  // betfair_money.py (entscheidet), betfair-radar.js (zeigt), main-dashboard.js (rankt).
  // Laufen sie auseinander, empfiehlt die Übersicht, was das Signal gerade fadet.
  const py = {
    n: Number(/^MIN_TR_N\s*=\s*(\d+)/m.exec(PY)[1]),
    fade: Number(/^TR_FADE_ROI\s*=\s*(-?[\d.]+)/m.exec(PY)[1]),
    boost: Number(/^TR_BOOST_ROI\s*=\s*(-?[\d.]+)/m.exec(PY)[1]),
  };
  const md = /var MD_BFTR_MIN_N = (\d+), MD_BFTR_FADE = (-?[\d.]+), MD_BFTR_BOOST = (-?[\d.]+)/.exec(MD);
  assert.ok(md, 'die Schwellen in main-dashboard.js sind weg');
  assert.deepStrictEqual([Number(md[1]), Number(md[2]), Number(md[3])], [py.n, py.fade, py.boost],
    'Übersicht und Card-Signal rechnen mit verschiedenen Schwellen');
  const rd = {
    n: Number(/var BF_TR_MIN_N = (\d+)/.exec(RADAR)[1]),
    fade: Number(/var BF_TR_FADE\s*=\s*(-?[\d.]+)/.exec(RADAR)[1]),
    boost: Number(/var BF_TR_BOOST = (-?[\d.]+)/.exec(RADAR)[1]),
  };
  assert.deepStrictEqual([rd.n, rd.fade, rd.boost], [py.n, py.fade, py.boost],
    'Radar und Card-Signal rechnen mit verschiedenen Schwellen');
});

function trackFn() {
  const von = MD.indexOf('var MD_BFTR_MIN_N');
  const bis = MD.indexOf('// ⚡ Sharpe Bewegungen');
  const g = {};
  // eslint-disable-next-line no-new-func
  new Function('exp', '_md', MD.slice(von, bis) + '\nexp.f=_mdBfTrack;')(
    g, { data: { bfTrack: { byLeagueMarket: {
      'EPL|Match Odds': { n: 40, roi: 0.12, roiUg: 0.03 },
      'EPL|Both teams to Score?': { n: 40, roi: -0.22, roiUg: -0.16 },
      'EPL|Over/Under 2.5 Goals': { n: 40, roi: 0.08, roiUg: 0.0 },
      'Kleinkram|Match Odds': { n: 6, roi: 0.9 },
      // 04.09.2026: n groß genug für die alte Schwelle, aber ohne Untergrenze — der reale Fall.
      'Schoener Schein|Match Odds': { n: 20, roi: 0.42 },
    } } } });
  return g.f;
}

test('der Track urteilt auf der Übersicht wie im Radar', () => {
  const f = trackFn();
  assert.strictEqual(f('EPL', 'Match Odds').traegt, true);
  assert.strictEqual(f('EPL', 'Both teams to Score?').verliert, true);
  const neutral = f('EPL', 'Over/Under 2.5 Goals');
  assert.ok(!neutral.traegt && !neutral.verliert, 'null ROI ist weder tragend noch verlierend');
  assert.strictEqual(f('Kleinkram', 'Match Odds'), null, 'ohne Untergrenze gibt es kein Urteil');
  assert.strictEqual(f('Gibtsnicht', 'Match Odds'), null);
});

// 04.09.2026 (Lucas: „mach ma mal Betfair-Check"). Die Schwelle war n>=15 auf dem
// Punktschätzer. Gemessen: 1.641 Liga×Markt-Buckets mit Median n=5; 146 erreichten n>=15 und
// davon galten 52 als „trägt" und 57 als „verliert" — während über ALLE Buckets nur drei
// überhaupt eine Rendite-Untergrenze tragen und davon keiner eine positive. 57 Zeilen flogen
// also aus „Top-Wetten jetzt", weil ein Eimer mit im Schnitt fünf Plays das so aussehen ließ.
test('ein schöner ROI ohne Untergrenze ist kein Urteil', () => {
  assert.strictEqual(trackFn()('Schoener Schein', 'Match Odds'), null,
    '+42% auf n=20 darf weder boosten noch ausschließen');
});

test('verlierende Eimer kommen gar nicht erst in die Top-Wetten', () => {
  // Beide Betfair-Quellen müssen den Riegel haben — Steam über Match Odds, Zufluss über den
  // Markt, den der Zufluss-Feed mitliefert.
  const steam = MD.slice(MD.indexOf("var trS = _mdBfTrack"), MD.indexOf("badge: '💷 Steam'"));
  assert.match(steam, /trS && trS\.verliert\) return;/, 'der Steam-Kandidat hat keinen Riegel');
  assert.match(steam, /_mdBfTrack\(x\.league, 'Match Odds'\)/, 'Steam nimmt den falschen Eimer');
  const flow = MD.slice(MD.indexOf("var trF = _mdBfTrack"), MD.indexOf("badge: '💷 Geld'"));
  assert.match(flow, /trF && trF\.verliert\) return;/, 'der Zufluss-Kandidat hat keinen Riegel');
  assert.match(flow, /_mdBfTrack\(x\.league, x\.market\)/, 'Zufluss nimmt den falschen Eimer');
});

test('ein tragender Eimer hebt den Rang, ein unbekannter nicht', () => {
  assert.match(MD, /\+ \(trS && trS\.traegt \? 10 : 0\)/, 'Steam bekommt keinen Bonus für belegte Eimer');
  assert.match(MD, /\+ \(trF && trF\.traegt \? 10 : 0\)/, 'Zufluss bekommt keinen Bonus für belegte Eimer');
});

test('die Zeile zeigt, was der Track sagt — auch wenn er nichts weiß', () => {
  assert.match(MD, /_mdSigCell\('Liga-Track'/, 'die Track-Zelle fehlt in der Signal-Leiste');
  assert.match(MD, /_mdSigMuted\('Liga-Track', 'noch zu wenig Historie'\)/,
    'ohne Historie muss die Zelle das sagen, statt zu verschwinden');
  assert.match(MD, /trägt hier/);
});
