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

// 🔴 04.09.2026 (Lucas: „geh die verbleibenden Duplikate durch"). Dieser Test stand vorher
// andersherum und hieß „die Schwellen stehen an drei Stellen — und überall gleich". Er hat
// funktioniert (er schlug an, als die Schwellen auf die Untergrenze umgestellt wurden), aber er
// hat drei Kopien SYNCHRON gehalten, statt die Kopien loszuwerden. Und er hat eine vierte
// übersehen: `_tMute` im Terminal fadete bei −0,05, während alle drei „gleichen" bei −0,10
// standen.
//
// Jetzt fällt betfair_track_record.py das Urteil einmal und schreibt es als `urteil` ins
// Artefakt. Der Test sichert die neue Regel: im JS wird gelesen, nicht verglichen.
test('die Schwelle steht an EINER Stelle — im Produzenten', () => {
  const REC = readFileSync(new URL('betfair_track_record.py', ROOT), 'utf8');
  assert.match(REC, /from sharp_signals\.betfair_money import TR_FADE_ROI, TR_BOOST_ROI/,
    'der Produzent holt die Schwellen nicht mehr aus der einen Quelle');
  assert.match(REC, /"urteil": _urteil/, 'der Produzent schreibt sein Urteil nicht ins Artefakt');
  // Und die Schwellen selbst stehen genau einmal, im Signal.
  assert.match(PY, /^TR_FADE_ROI\s*=/m);
  assert.match(PY, /^TR_BOOST_ROI\s*=/m);
});

test('kein Frontend vergleicht roiUg noch selbst mit einer Schwelle', () => {
  for (const [name, src] of [['main-dashboard.js', MD], ['betfair-radar.js', RADAR]]) {
    const code = src.split('\n').filter(z => !z.trim().startsWith('//')).join('\n');
    // Verboten ist der Vergleich mit einer SCHWELLE. `roiUg > 0` als Vorzeichen-Prüfung fürs
    // Format („+3%" vs „-3%") ist keine Entscheidung und bleibt erlaubt.
    const schwelle = code.match(/roiUg\s*(<=|>=|>|<)\s*-?\d*\.\d+/g) || [];
    assert.deepStrictEqual(schwelle, [],
      name + ' vergleicht roiUg wieder mit einer eigenen Schwelle: ' + schwelle.join(', '));
    assert.ok(!/MD_BFTR_FADE|MD_BFTR_BOOST/.test(code),
      name + ': die eigenen Fade/Boost-Konstanten sind zurück');
  }
});

function trackFn() {
  const von = MD.indexOf('  function _mdBfTrack(');
  const bis = MD.indexOf('// ⚡ Sharpe Bewegungen');
  const g = {};
  // eslint-disable-next-line no-new-func
  new Function('exp', '_md', MD.slice(von, bis) + '\nexp.f=_mdBfTrack;')(
    g, { data: { bfTrack: { byLeagueMarket: {
      'EPL|Match Odds': { n: 40, roi: 0.12, roiUg: 0.03, urteil: 'traegt' },
      'EPL|Both teams to Score?': { n: 40, roi: -0.22, roiUg: -0.16, urteil: 'verliert' },
      'EPL|Over/Under 2.5 Goals': { n: 40, roi: 0.08, roiUg: 0.0, urteil: 'neutral' },
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
