// tests/frontend/uebersicht-ebene3-stake.test.mjs — Stake als vierter Indikator (08.09.2026)
//
// Lucas: „Stake in Ebene 3, aber genauso dargestellt wie diese anderen Indikatoren mit dem
// Balken." Ebene 3 ist die einzige Fläche, die auch Tennis und E-Sport zeigt — genau die
// Sportarten, in denen Stake eine große Highroller-Sektion hat und wir sonst gar keine zweite
// Quelle haben.
//
// Was hier festgehalten wird, ist weniger das Aussehen als die Ehrlichkeit der Zelle:
//   1. Der Renderer JOINT NICHT. Er schlägt in einem fertigen Wörterbuch nach (killer.stakePoly).
//      Ein Namensvergleich hier wäre Produzenten-Logik an der falschen Stelle.
//   2. „nicht erhoben" und „kein Geld auf diesem Spiel" sind zwei verschiedene Nichts.
//   3. Gleiche Seite und andere Seite dürfen nie gleich aussehen.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const MOD = new URL('../../main-dashboard.js', import.meta.url);

function load() {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="mainDashPanel"></div></body>',
    { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve(null) });
  w.eval(readFileSync(MOD, 'utf8'));
  return w;
}

const play = (over) => Object.assign({
  key: 'atp-tiafoe-michels-2026-09-08', match: 'Tiafoe vs Michelsen', side: 'Frances Tiafoe',
  league: 'TENNIS', sport: 'Tennis', verdict: 'BET', conv: 8, htk: 3,
  moneyPct: 0.62, vol: 40000,
}, over || {});

function ebene3(w, plays, stakePoly) {
  w._mdState.data = { killer: stakePoly === undefined ? {} : { stakePoly: stakePoly } };
  return w._mdJetztTest(plays);
}

const STAKE = {
  'atp-tiafoe-michels-2026-09-08': {
    usd: 7427, n: 4, seite: 'Frances Tiafoe', seiteUsd: 6404,
    event: 'Frances Tiafoe - Alex Michelsen', liga: 'US Open Men Singles',
  },
};

test('Stake steht als eigener Balken-Indikator neben den anderen', () => {
  const html = ebene3(load(), [play()], STAKE);
  assert.match(html, /Stake-Geld/, 'die Zelle fehlt ganz');
  assert.match(html, /md-sig-bar/, 'ohne Balken ist es nicht „wie die anderen Indikatoren"');
  assert.match(html, /\$7\.4K|\$7427/, 'die Summe fehlt');
  assert.match(html, /4 Wetten/);
});

test('gleiche Seite wird als solche benannt — nicht nur als Geldbetrag', () => {
  const html = ebene3(load(), [play({ side: 'Frances Tiafoe' })], STAKE);
  assert.match(html, /gleiche Seite/);
});

test('andere Seite ist eine Warnung, keine Bestätigung', () => {
  // Der teure Fehler wäre, Stake-Geld auf der GEGENSEITE als Rückenwind zu lesen.
  const html = ebene3(load(), [play({ side: 'Alex Michelsen' })], STAKE);
  assert.match(html, /andere Seite/);
  assert.doesNotMatch(html, /gleiche Seite/);
});

test('„nicht erhoben" und „kein Geld auf dem Spiel" sind zwei verschiedene Nichts', () => {
  const ohneIndex = ebene3(load(), [play()], undefined);
  assert.match(ohneIndex, /nicht erhoben/,
    'ohne Index haben wir gar nicht gefragt — das ist keine Aussage über das Spiel');
  const leererIndex = ebene3(load(), [play()], {});
  assert.match(leererIndex, /kein Highroller-Geld/,
    'mit Index und ohne Treffer haben wir gefragt und nichts gefunden');
  assert.doesNotMatch(leererIndex, /nicht erhoben/);
});

test('Geld ohne vergleichbare Seite wird sichtbar, stimmt aber nicht mit ab', () => {
  // Nur Satzsieger- oder Über/Unter-Wetten: das Geld existiert, eine Spielseite nicht.
  const html = ebene3(load(), [play()], {
    'atp-tiafoe-michels-2026-09-08': { usd: 5000, n: 2, seite: null, seiteUsd: 0,
      event: 'A - B', liga: 'X' },
  });
  assert.match(html, /Geld ohne vergleichbare Seite/);
  assert.doesNotMatch(html, /gleiche Seite|andere Seite/);
});

test('„-more-markets" ist dasselbe Spiel — der Basisschlüssel entscheidet', () => {
  const html = ebene3(load(), [play({ key: 'atp-tiafoe-michels-2026-09-08-more-markets' })], STAKE);
  assert.match(html, /\$7\.4K|\$7427/,
    'sonst verliert genau die Hälfte der Poly-Zeilen ihren Stake-Bezug');
});

test('der Renderer joint NICHT selbst — er schlägt nur nach', () => {
  // Gegenbeweis gegen die naheliegende Abkürzung „vergleich halt die Namen im Frontend".
  // Ein Eintrag unter einem fremden Schlüssel darf nicht über den Namen gefunden werden.
  const html = ebene3(load(), [play()], {
    'irgendein-anderer-schluessel': { usd: 99999, n: 9, seite: 'Frances Tiafoe',
      seiteUsd: 99999, event: 'Frances Tiafoe - Alex Michelsen', liga: 'US Open' },
  });
  assert.doesNotMatch(html, /\$100K|99999/,
    'ein Namens-Join im Renderer wäre Produzenten-Logik an der falschen Stelle');
  assert.match(html, /kein Highroller-Geld/);
});

test('Betfair-Zeilen bekommen keine Stake-Zelle — der Index kennt nur Poly-Schlüssel', () => {
  const w = load();
  w._mdState.data = {
    killer: { stakePoly: STAKE },
    bfOverview: { steam: [{ matchId: 'm1', home: 'Arsenal', away: 'Chelsea',
      league: 'English Premier League', kickoff: new Date(Date.now() + 3 * 3600e3).toISOString(),
      pp: 4.0, odd: 2.6, sideName: 'Arsenal' }], flow: [] },
  };
  const html = w._mdJetztTest([]);
  assert.match(html, /Arsenal/);
  assert.doesNotMatch(html, /Stake-Geld/,
    'eine Stake-Zelle an einer Betfair-Zeile wäre eine Behauptung ohne Schlüssel dahinter');
});
