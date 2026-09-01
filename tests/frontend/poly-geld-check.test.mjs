// tests/frontend/poly-geld-check.test.mjs — 01.09.2026
//
// Lucas: „kannst du da auch mal checken" (Reiter 💰 Großes Geld). Zwei Befunde:
//
//  1. Die Kachel „🏆 Masse weiß am meisten" stand GRÜN auf MLB — während dieselbe Ansicht MLB in
//     der Tabelle darunter als „🔴 Preis besser" führte. Ursache: der Vorfilter `|edge| >= 0.01`
//     sortiert nach BETRAG, nicht nach VORZEICHEN. Sind alle übrigen Ligen negativ (heute 12 von
//     12, beste −0,027), ist `s[0]` der am wenigsten schlechte Verlierer — gekrönt als Sieger.
//  2. Die Tabelle „zum Folgen" listet 30 Märkte, während für KEINE Liga „🟢 Geld schärfer" gilt.
//     Das Urteil stand nur im Rückblick weiter unten, nicht an der Zeile, an der man handelt.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const SRC = readFileSync(new URL('../../poly-wallets.js', import.meta.url), 'utf8');
function laden(cache) {
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve(null) });
  w.eval(SRC);
  w._pwCache = cache || {};
  return w;
}
const liga = (league, n, bm, bp, hit) => ({ league, n, brierMoney: bm, brierPrice: bp,
  moneyHitRate: hit, verdict: bm < bp - 0.01 ? 'geld_schaerfer' : bm > bp + 0.01 ? 'preis_besser' : 'gleichauf' });

test('kein Sieger, solange die beste Liga unter null liegt', () => {
  // Genau der gemeldete Fall: alle negativ, „bester" ist −0,027.
  const broad = { n: 100, byLeague: [liga('MLB', 50, 0.4938, 0.4665, 0.58),
                                     liga('EPL', 54, 0.7323, 0.6427, 0.37),
                                     liga('MLS', 69, 0.80, 0.68, 0.42)] };
  const w = laden({ moneyBroad: broad });
  const h = w._pwMoneyBroad(broad);
  assert.match(h, /keine Liga/, 'das Fehlen eines Siegers wird ausgesprochen');
  assert.doesNotMatch(h, /#3fb95014/, 'keine grüne Sieger-Kachel');
  assert.match(h, /Am nächsten dran: MLB/, 'aber der Beste wird benannt');
  assert.match(h, /Masse liegt am öftesten daneben/, 'die Verlierer-Kachel bleibt');
});

test('ist eine Liga wirklich schärfer, bekommt sie die grüne Kachel', () => {
  const broad = { n: 100, byLeague: [liga('ESPORTS', 136, 0.40, 0.47, 0.62),
                                     liga('EPL', 54, 0.7323, 0.6427, 0.37)] };
  const w = laden({ moneyBroad: broad });
  const h = w._pwMoneyBroad(broad);
  assert.doesNotMatch(h, /keine Liga/);
  assert.match(h, /#3fb95014/, 'grüne Sieger-Kachel erscheint');
  assert.match(h, /ESPORTS/);
});

test('die Kachel nennt das Maß, nach dem sie ausgewählt hat', () => {
  // Vorher stand dort nur die Trefferquote (58%) — ausgewählt wurde aber nach Brier-Vorsprung.
  // Zwei verschiedene Maße in einer Kachel, ohne dass eines davon benannt war.
  const broad = { n: 100, byLeague: [liga('ESPORTS', 136, 0.40, 0.47, 0.62),
                                     liga('EPL', 54, 0.7323, 0.6427, 0.37)] };
  const h = laden({ moneyBroad: broad })._pwMoneyBroad(broad);
  assert.match(h, /Vorsprung [+-]0\.\d{3}/, 'der Vorsprung steht dabei');
  assert.match(h, /Geld trifft \d+%/, 'und die Trefferquote auch');
});

test('jede Zeile der Folgen-Tabelle trägt das Urteil ihrer Liga', () => {
  const w = laden({
    moneyBroad: { n: 10, byLeague: [liga('EPL', 54, 0.7323, 0.6427, 0.37),
                                    liga('ESPORTS', 136, 0.40, 0.47, 0.62)] },
    broadLive: {
      'a-epl': { league: 'EPL', totalUsd: 50000, hoursToKickoff: 2,
                 shares: { 'Arsenal': 30000, 'Chelsea': 20000 }, prices: { 'Arsenal': 0.6, 'Chelsea': 0.4 } },
      'b-es': { league: 'ESPORTS', totalUsd: 40000, hoursToKickoff: 3,
                shares: { 'HOTU': 26000, 'Color': 14000 }, prices: { 'HOTU': 0.65, 'Color': 0.35 } },
      'c-neu': { league: 'CRICKET', totalUsd: 30000, hoursToKickoff: 4,
                 shares: { 'X': 20000, 'Y': 10000 }, prices: { 'X': 0.66, 'Y': 0.34 } },
    },
  });
  const h = w._pwMoneyLive(w._pwCache.broadLive);
  assert.match(h, /🔴 faden/, 'die rote Liga wird an der Zeile als „faden" markiert');
  assert.match(h, /🟢 folgen/, 'die grüne als „folgen"');
  // Liga ohne Rückblick: „?" — kein Freibrief.
  assert.match(h, /kein Rückblick vor/, 'ohne Historie kein Urteil, aber auch kein Schweigen');
});
