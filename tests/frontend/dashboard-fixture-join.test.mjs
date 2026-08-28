// tests/frontend/dashboard-fixture-join.test.mjs — 28.08.2026 (Lucas: „Triple-Konsens ist immer leer")
//
// Der Walker in main-dashboard.js suchte Objekte, die SELBST ein picks-Array tragen. In
// liga-data.json / mls-data.json hängen die Picks aber nicht am Fixture — sie liegen in einer
// eigenen Map unter `picks`, verschlüsselt als `<LIGA>-<Spieltag>-<homeId>-<awayId>`.
// Ergebnis: NULL Fixtures in allen drei Datensätzen. Damit lag nicht nur der Triple-Konsens
// brach, sondern alles auf allFixtures(): beste Cards, Sharp-Moves, „Jetzt", Engine-Kandidaten.
// Die Daten waren die ganze Zeit da — zusammengeführt hat sie niemand.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';

const ROOT = new URL('../../', import.meta.url);
const SRC = readFileSync(new URL('main-dashboard.js', ROOT), 'utf8');

// Funktion per Klammer-Zaehlung aus der Quelle schneiden — robuster als ein Regex, der an
// jedem verschachtelten `}` scheitert.
function load(name) {
  const start = SRC.indexOf('function ' + name + '(data) {');
  assert.ok(start >= 0, name + ' nicht gefunden');
  let i = SRC.indexOf('{', start), tiefe = 0, ende = -1;
  for (let j = i; j < SRC.length; j++) {
    if (SRC[j] === '{') tiefe++;
    else if (SRC[j] === '}') { tiefe--; if (tiefe === 0) { ende = j + 1; break; } }
  }
  assert.ok(ende > 0, name + ': Klammern gehen nicht auf');
  return SRC.slice(start, ende);
}
function build(name, ...deps) {
  // fixtures() ruft _mdJoinPicks — beide im selben Scope auswerten, sonst „is not defined".
  const code = deps.map(load).concat([load(name)]).join('\n');
  return new Function(code + '; return ' + name + ';')();
}
const join = build('_mdJoinPicks');

const DATA = {
  groups: {
    ESP: { fixtures: [
      { home: '529', away: '531', homeName: 'Barcelona', awayName: 'Athletic Club',
        matchday: 1, date: '2026-08-27', kickoff: '2026-08-27T19:00:00+00:00' },
      { home: '1', away: '2', matchday: 1, date: '2026-08-27' },
    ] },
  },
  koFixtures: [{ home: '7', away: '8', matchday: 30, round: 'R16', date: '2026-09-01' }],
  picks: {
    'ESP-1-529-531': [{ market: 'Über 3.5 Tore', verdict: 'ABWÄGEN',
                        consensus: { kind: 'konsens', n: 3, side: 'home' } }],
    'R16-30-7-8': [{ market: 'Heimsieg', verdict: 'BET' }],
  },
};

test('Picks aus der Map landen am Fixture', () => {
  const fx = join(DATA);
  const b = fx.find(f => f.homeName === 'Barcelona');
  assert.equal(b.picks.length, 1);
  assert.equal(b.picks[0].consensus.kind, 'konsens');
});

test('KO-Spiele kommen mit (liegen in koFixtures, nicht in groups)', () => {
  const ko = join(DATA).find(f => f.home === '7');
  assert.equal(ko.picks[0].verdict, 'BET');
});

test('Fixture ohne Picks bleibt drin, aber mit leerem Array', () => {
  const leer = join(DATA).find(f => f.home === '1');
  assert.deepStrictEqual([...leer.picks], []);
});

test('die Rohdaten werden NICHT mutiert', () => {
  // Sonst hängen die Picks nach jedem Refresh erneut dran.
  const kopie = JSON.parse(JSON.stringify(DATA));
  join(kopie);
  assert.equal(kopie.groups.ESP.fixtures[0].picks, undefined);
});

test('Liga-Code landet am Fixture, damit die Zeile beschriftet werden kann', () => {
  const b = join(DATA).find(f => f.homeName === 'Barcelona');
  assert.equal(b.group, 'ESP');
});

test('Müll wirft nicht', () => {
  for (const bad of [null, undefined, {}, 'x', 5, { groups: null }, { groups: { X: null } }]) {
    assert.doesNotThrow(() => join(bad));
  }
  assert.deepStrictEqual([...join({ groups: { X: { fixtures: [null, 'y'] } } })], []);
});

test('der alte Walker bleibt als Fallback stehen', () => {
  // Ältere/andere Formate tragen die Picks doch am Fixture — die dürfen nicht verloren gehen.
  const fixtures = build('fixtures', '_mdJoinPicks');
  const alt = { irgendwo: [{ home: 'A', away: 'B', picks: [{ market: 'X' }] }] };
  assert.equal(fixtures(alt).length, 1);
});

test('Join darf den Fallback nicht verdrängen, wenn er selbst nichts findet', () => {
  // Der erste Anlauf prüfte nur `joined.length`. Bei einem Format mit Picks AM Fixture lieferte
  // der Join Fixtures mit LEEREN Arrays — und verdrängte damit den Walker, der sie gefunden
  // hätte. Fehlende Daten sahen aus wie „nichts da".
  const fixtures = build('fixtures', '_mdJoinPicks');
  const gemischt = {
    groups: { ESP: { fixtures: [{ home: 'A', away: 'B', matchday: 1, picks: [{ market: 'X' }] }] } },
    picks: {},   // Map da, aber leer → Join findet nichts
  };
  const out = fixtures(gemischt);
  assert.equal(out.length, 1, 'der Walker muss einspringen');
  assert.equal(out[0].picks.length, 1);
});
