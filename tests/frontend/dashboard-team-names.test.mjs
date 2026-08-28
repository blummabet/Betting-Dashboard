// tests/frontend/dashboard-team-names.test.mjs — 28.08.2026
// Lucas: „der triple konsens ist befüllt / aber da passt noch was nicht mit den team namen"
//
// Im Panel stand „45 v 52 · Ausw." statt „Everton v Crystal Palace". Ursache: in
// liga-data.json / mls-data.json ist fx.home die TEAM-ID als String ("45"), der Klarname liegt
// daneben in fx.homeName. Die Anzeige rief team(f.home) — und team() bekommt nur die ID und
// gibt sie mangels Besserem unverändert zurück. Im WM-Datensatz existiert homeName gar nicht:
// dort ist fx.home ein Kürzel ("MEX"), dessen Name in groups[*].teams steht.
//
// Reihenfolge, die fxTeam jetzt einhält: Name-Feld → ID→Name-Map des Datensatzes → Rohwert.
// Der Rohwert bleibt als letzte Stufe erhalten: lieber „45" anzeigen als „?" oder gar nichts.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';

const ROOT = new URL('../../', import.meta.url);
const SRC = readFileSync(new URL('main-dashboard.js', ROOT), 'utf8');

function load(name) {
  const start = SRC.indexOf('function ' + name + '(');
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
  const basis = ['team', 'fxTeam', '_mdLearnTeamNames', '_mdJoinPicks']
    .filter((n) => n !== name && !deps.includes(n));
  const code = 'var _MD_TEAM_NAMES = {};\n'
    + basis.concat(deps).map(load).concat([load(name)]).join('\n')
    + '; return { ' + [name, 'fxTeam', '_mdLearnTeamNames'].join(', ') + ' };';
  return new Function(code)();
}

// ── Stufe 1: das Name-Feld gewinnt ───────────────────────────────────────────
test('homeName/awayName werden bevorzugt', () => {
  const { fxTeam } = build('fxTeam');
  const fx = { home: '45', away: '52', homeName: 'Everton', awayName: 'Crystal Palace' };
  assert.equal(fxTeam(fx, 'home'), 'Everton');
  assert.equal(fxTeam(fx, 'away'), 'Crystal Palace');
});

test('genau der Fall aus dem Panel: nackte IDs kommen nicht mehr durch', () => {
  const { fxTeam, _mdLearnTeamNames } = build('fxTeam');
  _mdLearnTeamNames({ groups: { ENG: { teams: [
    { id: 45, name: 'Everton' }, { id: 52, name: 'Crystal Palace' },
  ] } } });
  const fx = { home: '45', away: '52' };            // wie im Rohdatensatz: nur IDs
  assert.equal(fxTeam(fx, 'home'), 'Everton');
  assert.equal(fxTeam(fx, 'away'), 'Crystal Palace');
});

// ── Stufe 2: die ID→Name-Map aus dem Datensatz ───────────────────────────────
test('WM-Kürzel werden über groups[*].teams aufgelöst', () => {
  const { fxTeam, _mdLearnTeamNames } = build('fxTeam');
  _mdLearnTeamNames({ groups: { A: { teams: [{ id: 'MEX', name: 'Mexiko' }, { id: 'ZAF', name: 'Südafrika' }] } } });
  assert.equal(fxTeam({ home: 'MEX', away: 'ZAF' }, 'home'), 'Mexiko');
  assert.equal(fxTeam({ home: 'MEX', away: 'ZAF' }, 'away'), 'Südafrika');
});

test('numerische IDs im Datensatz matchen auf String-IDs im Fixture', () => {
  // liga-data.json fuehrt teams[].id als Zahl, fixtures[].home als String — das muss halten.
  const { fxTeam, _mdLearnTeamNames } = build('fxTeam');
  _mdLearnTeamNames({ groups: { ITA: { teams: [{ id: 496, name: 'Juventus' }] } } });
  assert.equal(fxTeam({ home: '496', away: '523' }, 'home'), 'Juventus');
});

test('Map wird über mehrere Datensätze hinweg gesammelt', () => {
  const { fxTeam, _mdLearnTeamNames } = build('fxTeam');
  _mdLearnTeamNames({ groups: { ENG: { teams: [{ id: 45, name: 'Everton' }] } } });
  _mdLearnTeamNames({ groups: { MLS: { teams: [{ id: 1598, name: 'Austin FC' }] } } });
  assert.equal(fxTeam({ home: '45' }, 'home'), 'Everton');
  assert.equal(fxTeam({ home: '1598' }, 'home'), 'Austin FC');
});

// ── Stufe 3: Rohwert statt Loch ──────────────────────────────────────────────
test('unbekannte ID bleibt sichtbar statt zu „?" zu werden', () => {
  const { fxTeam } = build('fxTeam');
  assert.equal(fxTeam({ home: '99999' }, 'home'), '99999');
});

test('leeres Fixture kippt nicht um', () => {
  const { fxTeam } = build('fxTeam');
  assert.equal(fxTeam(null, 'home'), '?');
  assert.equal(fxTeam({}, 'home'), '?');
});

test('leerer Name-String faellt auf die Map zurueck, nicht auf ""', () => {
  const { fxTeam, _mdLearnTeamNames } = build('fxTeam');
  _mdLearnTeamNames({ groups: { X: { teams: [{ id: '7', name: 'Bayern' }] } } });
  assert.equal(fxTeam({ home: '7', homeName: '' }, 'home'), 'Bayern');
});

// ── Der Join schreibt die Namen mit ──────────────────────────────────────────
test('_mdJoinPicks fuellt homeName/awayName aus groups[*].teams', () => {
  const { _mdJoinPicks } = build('_mdJoinPicks');
  const out = _mdJoinPicks({
    groups: { ENG: {
      teams: [{ id: 45, name: 'Everton' }, { id: 52, name: 'Crystal Palace' }],
      fixtures: [{ home: '45', away: '52', matchday: 3 }],
    } },
    picks: { 'ENG-3-45-52': [{ market: 'Heimsieg', consensus: { kind: 'konsens' } }] },
  });
  assert.equal(out.length, 1);
  assert.equal(out[0].homeName, 'Everton');
  assert.equal(out[0].awayName, 'Crystal Palace');
  assert.equal(out[0].picks.length, 1, 'der Pick muss weiterhin ankommen');
});

test('_mdJoinPicks laesst vorhandene Namen unangetastet', () => {
  const { _mdJoinPicks } = build('_mdJoinPicks');
  const out = _mdJoinPicks({
    groups: { ESP: {
      teams: [{ id: 529, name: 'FALSCH' }],
      fixtures: [{ home: '529', away: '531', homeName: 'Barcelona', awayName: 'Athletic Club', matchday: 1 }],
    } },
    picks: {},
  });
  assert.equal(out[0].homeName, 'Barcelona');
});

test('koFixtures bekommen auch Namen', () => {
  const { _mdJoinPicks } = build('_mdJoinPicks');
  const out = _mdJoinPicks({
    groups: { A: { teams: [{ id: 'MEX', name: 'Mexiko' }, { id: 'ZAF', name: 'Südafrika' }] } },
    koFixtures: [{ home: 'MEX', away: 'ZAF', matchday: 30, round: 'R16' }],
    picks: {},
  });
  const ko = out.find((f) => f.home === 'MEX');
  assert.ok(ko, 'KO-Fixture fehlt');
  assert.equal(ko.homeName, 'Mexiko');
  assert.equal(ko.awayName, 'Südafrika');
});

// ── Regression: keine Anzeigestelle darf zurueckfallen ───────────────────────
test('die Team-Zeilen im Dashboard rufen fxTeam, nicht team(f.home)', () => {
  const treffer = SRC.match(/team\(f\.home\)/g) || [];
  assert.equal(treffer.length, 0,
    'noch ' + treffer.length + 'x team(f.home) — diese Stellen zeigen wieder rohe IDs');
});
