// tests/frontend/poly-play-label.test.mjs — 05.08.2026 (Lucas: „bei Yes/No sieht man nicht WELCHES
// Spiel"): generische Ausgaenge (Yes/No, Over/Under, Draw) sagen nichts ueber das Match — dann wird
// das Spiel aus dem Key abgeleitet. Team-Maerkte behalten die Team-Namen.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const PW = new URL('../../poly-wallets.js', import.meta.url);
function load() {
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'https://x/', runScripts: 'outside-only' });
  const w = dom.window; w.eval(readFileSync(PW, 'utf8')); return w;
}

test('Yes/No-Markt: Label kommt aus dem Key, nicht "Yes vs No"', () => {
  const w = load();
  const yn = [{ s: 'No', u: 96 }, { s: 'Yes', u: 4 }];
  assert.equal(w._pwPlayLabel('ucl-sf-kps-2026-07-21', yn), 'ucl sf kps');
  assert.doesNotMatch(w._pwPlayLabel('ucl-sf-kps-2026-07-21', yn), /Yes vs No|No vs Yes/);
});

test('Yes/No mit Untermarkt: Markt-Typ bleibt erhalten', () => {
  const w = load();
  const yn = [{ s: 'Yes', u: 6 }, { s: 'No', u: 94 }];
  assert.equal(w._pwPlayLabel('ucl-sf-kps-2026-07-21-exact-score', yn), 'ucl sf kps · exact score');
});

test('Team-Markt: Team-Namen bleiben (kein Key-Fallback)', () => {
  const w = load();
  const team = [{ s: 'Toronto Blue Jays', u: 60 }, { s: 'Houston Astros', u: 40 }];
  assert.equal(w._pwPlayLabel('mlb-tor-hou-2026-08-05', team), 'Toronto Blue Jays vs Houston Astros');
});

test('Over/Under gilt auch als generisch → Key-Label', () => {
  const w = load();
  const ou = [{ s: 'Over', u: 55 }, { s: 'Under', u: 45 }];
  assert.equal(w._pwPlayLabel('epl-ars-che-2026-08-16', ou), 'epl ars che');
});

test('Prop-Markt (total-corners): Match-Name aus Basis-Event, auch wenn dessen shares leer sind', () => {
  const w = load();
  // Basis-Event traegt die Teamnamen nur in prices (shares leer) — genau der Frosinone/Newcastle-Fall.
  w._pwCache = { broadLive: { 'epl-new-liv-2026-08-23': {
    shares: {},
    prices: { 'Newcastle United FC': 0.42, 'Draw (Newcastle United FC vs. Liverpool FC)': 0.28, 'Liverpool FC': 0.30 }
  } } };
  const ou = [{ s: 'Over', u: 51 }, { s: 'Under', u: 49 }];
  assert.equal(
    w._pwPlayLabel('epl-new-liv-2026-08-23-total-corners', ou),
    'Newcastle United FC vs Liverpool FC'
  );
});

test('Prop-Markt: Teamnamen auch aus moneyBroad-Cache aufloesbar', () => {
  const w = load();
  w._pwCache = { moneyBroad: { 'bra-cor-cor1-2026-08-23': {
    shares: { 'Corinthians': 70, 'Cruzeiro': 30 }
  } } };
  const ou = [{ s: 'Over', u: 60 }, { s: 'Under', u: 40 }];
  assert.equal(
    w._pwPlayLabel('bra-cor-cor1-2026-08-23-total-corners', ou),
    'Corinthians vs Cruzeiro'
  );
});

test('Prop ohne auffindbaren Basis-Event: sauberer Slug-Fallback bleibt', () => {
  const w = load();
  w._pwCache = { broadLive: {} };
  const ou = [{ s: 'Over', u: 55 }, { s: 'Under', u: 45 }];
  assert.equal(
    w._pwPlayLabel('epl-new-liv-2026-08-23-total-corners', ou),
    'epl new liv · total corners'
  );
});
