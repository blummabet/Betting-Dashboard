// tests/frontend/cards-liga-kontext.test.mjs — 04.09.2026
//
// Lucas: „es wird mal wieder Zeit für einen Cards-Check."
//
// Auf den Liga-Cards stand als BEGRÜNDUNG eines Picks:
//
//     ❌ Beide ausgeschieden — Friendly-Charakter, beide ohne Druck.   (Ipswich–Liverpool, ST 3)
//     Real Betis braucht zwingend Sieg + Schützenhilfe, Real Madrid bereits sicher.  (La Liga ST 4)
//     🔥 Aufstiegs-Druck                                               (PSG–Monaco, Ligue 1 ST 3)
//
// An Spieltag 3 einer Liga ist niemand ausgeschieden und niemand sicher. Die Ursache ist eine
// WM-Gruppenregel auf einer Liga-Tabelle: `hSafe = pos <= 2`, `hOut = pos > 3`. In einer
// Vierergruppe heißt das „durch" und „raus" — in `standings['ESP']` stehen aber 20 Teams
// (ENG 20, GER 18). Damit war ab Platz 4 jeder „ausgeschieden" und auf Platz 1–2 jeder „sicher".
//
// Das ist nicht kosmetisch: der Satz steht im „Warum?" und stützte bei Ipswich–Liverpool einen
// Über-2.5-Pick mit „beide ohne Druck".
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';

const JS = readFileSync(new URL('../../wm2026-renderer.js', import.meta.url), 'utf8');

// Den Wächter isoliert laden — er ist rein und hängt an nichts.
function guard() {
  const von = JS.indexOf('  const _GRUPPE_MAX = 4;');
  const bis = JS.indexOf('function _deriveAngle');
  assert.ok(von > 0 && bis > von, 'der Gruppentabellen-Wächter fehlt');
  const g = {};
  // eslint-disable-next-line no-new-func
  new Function('exp', JS.slice(von, bis) + '\nexp.f=_istGruppentabelle; exp.max=_GRUPPE_MAX;')(g);
  return g;
}
const G = guard();

test('eine WM-Vierergruppe ist eine Gruppentabelle', () => {
  assert.strictEqual(G.max, 4, 'eine WM-Gruppe hat vier Teams');
  assert.strictEqual(G.f([1, 2, 3, 4].map(p => ({ team: 'T' + p }))), true);
  assert.strictEqual(G.f([{ team: 'A' }, { team: 'B' }, { team: 'C' }]), true);
});

test('eine Liga-Tabelle ist keine — das ist der ganze Fehler', () => {
  const laLiga = Array.from({ length: 20 }, (_, i) => ({ team: String(i) }));
  const bundesliga = Array.from({ length: 18 }, (_, i) => ({ team: String(i) }));
  assert.strictEqual(G.f(laLiga), false, '20 Teams sind keine Gruppe');
  assert.strictEqual(G.f(bundesliga), false, '18 Teams auch nicht');
});

test('nichts vorhanden heißt auch nicht Gruppe', () => {
  assert.strictEqual(G.f(null), false);
  assert.strictEqual(G.f([]), false);
  assert.strictEqual(G.f(undefined), false);
});

// ── Die drei Stellen, die es benutzen müssen ────────────────────────────────
test('die Kopfzeilen-Kategorie fragt den Wächter', () => {
  assert.match(JS, /\} else if \(_istGruppentabelle\(standing\) && fx\.matchday >= 3\) \{/);
});

test('der Begründungstext fragt den Wächter', () => {
  assert.match(JS, /\} else if \(fx\.matchday >= 3 && _istGruppentabelle\(standing\)\) \{/);
});

test('das Szenario fragt den Wächter', () => {
  assert.match(JS, /if \(_istGruppentabelle\(standing\)\) \{\s*\n\s*return _standingScenario/);
});

test('die alte ungeschützte Form ist überall weg', () => {
  assert.ok(!/else if \(standing && standing\.length && fx\.matchday >= 3\)/.test(JS));
  assert.ok(!/else if \(fx\.matchday >= 3 && standing && standing\.length\)/.test(JS));
  assert.ok(!/if \(standing && standing\.length > 0\) \{\s*\n\s*return _standingScenario/.test(JS));
});

// ── Serien: die richtige Hälfte ─────────────────────────────────────────────
// Werder Bremen (Heim) v RB Leipzig (Auswärts) trug beide Zeilen falschherum:
//   RB Leipzig · Ungeschlagen HEIM 6×          → Leipzig spielt hier auswärts
//   Werder Bremen · Über 9,5 Ecken AUSWÄRTS 5× → Werder spielt hier daheim
// In den Daten hat Werder ausschließlich Auswärts-Serien, Leipzig fast nur Heim-Serien.
function streakPicker() {
  const von = JS.indexOf('  function _streaksForTeam(');
  const bis = JS.indexOf('  function _matchStreaksHtml(');
  assert.ok(von > 0 && bis > von);
  const g = {};
  // eslint-disable-next-line no-new-func
  new Function('exp', JS.slice(von, bis) + '\nexp.f=_streaksForTeam;')(g);
  return g.f;
}

test('eine Serie aus der anderen Hälfte kommt nicht in „Serien in diesem Spiel"', () => {
  const f = streakPicker();
  const werder = [{ teamId: '162', type: 'corners_over', venue: 'A', length: 5 }];
  assert.deepStrictEqual(f(werder, '162', 'H'), [], 'Werder spielt daheim — die Auswärts-Serie sagt nichts');
  const leipzig = [{ teamId: '173', type: 'unbeaten', venue: 'H', length: 6 }];
  assert.deepStrictEqual(f(leipzig, '173', 'A'), [], 'Leipzig spielt auswärts — die Heim-Serie sagt nichts');
});

test('die passende Hälfte und die Gesamt-Serie bleiben', () => {
  const f = streakPicker();
  const list = [
    { teamId: '1', type: 'unbeaten', venue: 'H', length: 6 },
    { teamId: '1', type: 'scores', venue: 'all', length: 3 },
    { teamId: '1', type: 'corners_over', venue: 'A', length: 9 },
  ];
  const out = f(list, '1', 'H').map(s => s.type).sort();
  assert.deepStrictEqual(out, ['scores', 'unbeaten'], 'die lange Auswärts-Serie fliegt trotz Länge raus');
});

test('die venue-passende schlägt die Gesamt-Serie beim selben Typ', () => {
  const f = streakPicker();
  const list = [
    { teamId: '1', type: 'unbeaten', venue: 'all', length: 9 },
    { teamId: '1', type: 'unbeaten', venue: 'H', length: 3 },
  ];
  assert.strictEqual(f(list, '1', 'H')[0].venue, 'H', 'die Heim-Serie ist die für ein Heimspiel passende');
});
