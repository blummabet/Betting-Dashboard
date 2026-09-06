// tests/frontend/uebersicht-signal-bilanz.test.mjs — 06.09.2026
//
// Lucas: „auf der Übersicht hast auch mal was eingebaut, das sollte man nicht vergessen" —
// und beim Hinsehen stand in der BILANZ-Kachel genau die Krankheit, die wir am selben Tag aus
// dem Lern-Loop entfernt haben:
//
//     edge = Win%dafür − Win%dagegen
//
// Eine Trefferquote ohne die Quoten ist keine Zahl (Bug-Klasse 6). Dazu ein Rückfall auf
// „dafür vs. Ø", wenn die Gegen-Seite dünn war — derselbe Populations-Sockel-Fehler, den die
// Signal-Bilanz an dem Tag zweimal korrigiert hat.
//
// Was das anrichtete (gleiche Picks, gleicher Tag, Tafel vs. gemessene Bilanz):
//
//     Form-Rating    Tafel +53 %  →  kein Urteil (ΔCLV −0,28)
//     xG-Stärke      Tafel +27 %  →  kein Urteil
//     Betfair-Geld   Tafel  +1 %  →  TRÄGT BEI (ΔCLV +2,71, UG +1,16)
//     Torjäger       Tafel −13 %  →  trägt bei
//
// Die Reihenfolge war nahezu invertiert: das beste Signal stand fast unten.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';

const ROOT = new URL('../../', import.meta.url);
const JS = readFileSync(new URL('main-dashboard.js', ROOT), 'utf8');
// Kommentare beschreiben absichtlich, was früher dastand — beim Prüfen auf Abwesenheit
// nur echten Code ansehen.
const CODE = JS.replace(/^\s*\/\/.*$/gm, '');

function block(von, bis) {
  const a = CODE.indexOf(von), b = CODE.indexOf(bis, a + 1);
  assert.ok(a > 0, 'Anker weg: ' + von);
  assert.ok(b > a, 'Anker weg: ' + bis);
  return CODE.slice(a, b);
}

const BOARD = () => block('var strength=function(r){', '🟢 trägt belegt bei');

test('die Zahl rechts kommt aus der gemessenen Bilanz, nicht aus Win-Quoten', () => {
  const b = BOARD();
  assert.ok(/r\.clvDiff/.test(b), 'strength() liest nicht clvDiff');
  assert.ok(!/r\.edge\b/.test(b),
    'r.edge (Win%dafür − Win%dagegen) ist wieder im Spiel — das ist keine Zahl');
});

test('der Rückfall auf „dafür vs. Ø" ist weg', () => {
  const b = BOARD();
  assert.ok(!/suppWinPct\s*-\s*base/.test(b),
    'Vergleich gegen den Hausschnitt zurück: derselbe Sockel-Fehler wie in der ersten Bilanz');
  assert.ok(!/viaBase/.test(b), 'die ⌀-Kennzeichnung ist zurück');
});

test('ohne belegtes Urteil steht kein Punktschätzer da', () => {
  const b = BOARD();
  assert.ok(/kein Urteil/.test(b), 'die Zeile sagt nicht mehr, wenn nichts belegt ist');
  assert.ok(/unbelegt/.test(b),
    'eine gemessene Zahl ohne Beleg muss als unbelegt gekennzeichnet sein');
});

test('Markt und Geld dürfen sich widersprechen, ohne dass daraus ein Urteil wird', () => {
  const b = BOARD();
  assert.ok(/gemischt/.test(b),
    'chance_creation ist im CLV positiv und beim Geld negativ — das darf nicht als '
    + '„trägt bei" durchgehen');
  assert.ok(/ausgangUrteil/.test(b), 'das Geld-Urteil wird gar nicht gelesen');
});

test('die Ampel folgt dem Urteil, nicht einer Prozent-Schwelle', () => {
  const b = BOARD();
  assert.ok(!/s>=10\b/.test(b) && !/s<=-12\b/.test(b),
    'die alten Prozent-Schwellen (>=10 / <=-12) entscheiden wieder die Farbe');
  assert.ok(/urteil\(r\)/.test(b), 'tier() fragt nicht nach dem Urteil');
});

test('die Legende nennt die Win-Quoten Beschreibung und kein Urteil', () => {
  // Anker auf den TEXT, nicht auf die CSS-Klasse: `.sb-legend{...}` steht weiter oben in
  // den Styles und wuerde den falschen Ausschnitt liefern.
  const leg = block('🟢 trägt belegt bei', '</div>');
  assert.ok(!/Edge \(dafür−gegen\)/.test(leg), 'die Legende nennt es wieder „Edge"');
  assert.ok(/Beschreibung, kein Urteil/.test(leg),
    'die Legende muss sagen, dass die Win-Quoten nichts beurteilen');
  assert.ok(/95%-Grenze|95%-Grenze die Null/.test(leg),
    'die Legende nennt die Grenze nicht, ab der ein Urteil gilt');
});

test('Belegtes steht oben, Unbelegtes wandert ans Ende', () => {
  const b = BOARD();
  assert.ok(/urteil\(x\)===.kein Urteil./.test(b) || /rx!==ry/.test(b),
    'die Sortierung stellt Unbelegtes nicht hinten an');
});
