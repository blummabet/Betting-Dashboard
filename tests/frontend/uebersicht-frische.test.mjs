// tests/frontend/uebersicht-frische.test.mjs — 30.08.2026
//
// Aus Lucas' Checkup: der Kopf zeigte „Stand 10:56" — die BROWSER-UHR. Über die Daten sagt die
// nichts. Gemessen am selben Vormittag: Betfair 12 Minuten alt, die Cards 5,9 Stunden, die
// Serien 12,1 Stunden. Die Seite behauptete für alles dieselbe Frische, und der Liga-Refresh
// hing seit Stunden — ohne dass irgendetwas darauf hinwies.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const MOD = new URL('../../main-dashboard.js', import.meta.url);

function render(data) {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="mainDashPanel"></div></body>',
    { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve(null) });
  w.eval(readFileSync(MOD, 'utf8'));
  w._mdState.data = Object.assign(
    { liga: null, mls: null, ligaStreaks: null, mlsStreaks: null, betfair: null, whales: null }, data);
  w._renderMainDash();
  return w.document.getElementById('mainDashPanel').innerHTML;
}
const vor = (min) => new Date(Date.now() - min * 60000).toISOString();

test('der Kopf nennt die ÄLTESTE Quelle, nicht die Uhrzeit', () => {
  const html = render({
    betfair: { _meta: { generatedAt: vor(12) }, matches: [] },
    liga: { _meta: { picksUpdatedAt: vor(354) }, groups: {}, picks: {} },
  });
  assert.match(html, /älteste Quelle/);
  assert.match(html, /Cards vor 5,9 h/, 'die Cards sind der trägste Feed — genau der gehört hin');
  assert.doesNotMatch(html, /Stand <b>\d\d:\d\d<\/b>/, 'die Browser-Uhr sagt nichts über die Daten');
});

test('picksUpdatedAt und ein generatedAt auf oberster Ebene werden gelesen', () => {
  // Beides kam vorher nicht durch: _ageMin las nur _meta.generatedAt/updated_at, weshalb für
  // Cards, Money-Map und Konsens NIE ein Alter heraussprang.
  const html = render({
    liga: { _meta: { picksUpdatedAt: vor(200) }, groups: {}, picks: {} },
    moneyMap: { generatedAt: vor(400), rows: [] },
  });
  assert.match(html, /Money-Map vor 6,7 h/);
});

test('alles frisch → keine Warnfarbe, aber weiterhin eine echte Angabe', () => {
  const html = render({ betfair: { _meta: { generatedAt: vor(5) }, matches: [] } });
  assert.match(html, /Betfair vor 5 Min/);
  assert.doesNotMatch(html, /#f2a6a6/, 'unter einer Stunde ist nichts zu warnen');
});

test('ohne jede Zeitangabe fällt der Kopf auf die Uhr zurück statt zu schweigen', () => {
  const html = render({ betfair: { matches: [] } });
  assert.match(html, /Stand <b>\d\d:\d\d<\/b>/);
});

test('die Card-Kachel trägt ihr eigenes Alter', () => {
  const html = render({
    liga: { _meta: { picksUpdatedAt: vor(354) },
      groups: { g: { fixtures: [{ home: 'Bayern', away: 'Dortmund', league: 'Bundesliga', kickoff: new Date(Date.now() + 4 * 3600e3).toISOString(), picks: [
        { market: 'Heimsieg', verdict: 'BET', convictionScore: 8, odds: 1.8 }] }] } }, picks: {} },
  });
  const kachel = html.slice(html.indexOf('Beste Cards'), html.indexOf('Beste Streaks'));
  assert.match(kachel, /Stand vor 5,9 h/);
});

test('ein negativer Edge am Steam-Folger wird erklärt, nicht versteckt', () => {
  const mk = (extra) => ({ _meta: { picksUpdatedAt: vor(10) },
    groups: { g: { fixtures: [{ home: 'Bayern', away: 'Dortmund', league: 'Bundesliga',
      kickoff: new Date(Date.now() + 4 * 3600e3).toISOString(), picks: [Object.assign({ market: 'Heimsieg', verdict: 'BET', convictionScore: 8,
        odds: 1.67, edgePP: -4 }, extra)] }] } }, picks: {} });
  const mitSteam = render({ liga: mk({ source: 'steam', lateEntry: true }) });
  assert.match(mitSteam, /-4pp/, 'die Zahl bleibt sichtbar');
  assert.match(mitSteam, /Steam-Folger, spät/);
  // Ohne Steam wäre ein negativer Edge ein echter Widerspruch — der bleibt nackt stehen.
  const ohne = render({ liga: mk({ source: 'model' }) });
  assert.match(ohne, /-4pp/);
  assert.doesNotMatch(ohne, /Steam-Folger/);
});
