// tests/frontend/betfair-radar-declutter.test.mjs — 02.08.2026 (Lucas): Radar-Entrümpelung.
// (1) Keine rote Live-Umrandung mehr — Rot nur im ● LIVE-Badge. (2) ×Norm-Badge Gold→Orange
// statt Rot. (3) Oberer Block „Wo das Geld liegt" nur mit klarer Mehrheit (Führung ≥60%),
// Fast-Gleichstände (die nur ein großes liquides Spiel sind) fliegen raus.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const ROOT = new URL('../../', import.meta.url);
function ko(h) { return new Date(Date.now() + h * 3600e3).toISOString(); }

function boot(matches) {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="betfairRadarPanel"></div></body>', { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window; w._bfNoAutoRefresh = true;
  w.eval(readFileSync(new URL('betfair-radar.js', ROOT), 'utf8'));
  w._bfState.data = { _meta: { generatedAt: new Date().toISOString(), n: matches.length, live: 0, currency: 'EUR', source: 'test' }, matches };
  w._bfState.hist = {}; w._bfState.loading = false;
  if (w._bfTHR) { w._bfTHR.top = { FT: 1000, HT: 500 }; w._bfTHR.intl = { FT: 1000, HT: 500 }; w._bfTHR.rest = { FT: 1000, HT: 500 }; }
  w._bfState.league = 'all'; w._bfState.tab = 'all'; w._bfState.date = 'all'; w._bfState.cardOpen = {};
  return w;
}
// 1X2-Match; Lead-Runner = home (so lässt sich „→ home" im Hotspot suchen).
function m1x2(id, home, away, hw, dr, aw, oddH, opts) {
  opts = opts || {};
  return { matchId: id, home, away, league: 'Test League', country: 'GB', kickoff: opts.ko || ko(9),
    liveInfo: opts.live || {}, totalVol: hw + dr + aw,
    markets: { 'Match Odds': { vol: hw + dr + aw, runners: [
      { name: home, odd: oddH, vol: hw }, { name: 'The Draw', odd: 3.5, vol: dr }, { name: away, odd: 4.0, vol: aw }] } } };
}
function hotspotBlock(html) {
  const a = html.indexOf('größte Einzel-Ausgänge');
  const b = html.indexOf('💸');   // Frisches-Geld-Block folgt direkt danach
  return html.slice(a, b > a ? b : html.length);
}

test('Coinflip-Filter: Führung < 60% fliegt aus dem oberen Block, ≥60% bleibt', () => {
  const w = boot([
    m1x2(1, 'DominantFC', 'X', 7200, 1400, 1400, 2.0),   // 72% → bleibt
    m1x2(2, 'EvenFC', 'Y', 5200, 2400, 2400, 2.0),       // 52% → raus (genug € & Quote, nur Split zu knapp)
  ]);
  const block = hotspotBlock(w._renderBetfairRadar());
  assert.match(block, /DominantFC/, 'klare Mehrheit bleibt');
  assert.ok(!/EvenFC/.test(block), 'Fast-Gleichstand (52%) ist NICHT im Hotspot-Block');
});

test('Keine rote Live-Umrandung mehr — aber ● LIVE-Badge bleibt', () => {
  const w = boot([m1x2(1, 'LiveFC', 'Z', 7200, 1400, 1400, 2.0, { live: { time: 30, finished: false }, ko: ko(-0.2) })]);
  const html = w._renderBetfairRadar();
  assert.ok(!/bfb-row bfb-live/.test(html), 'die Zeile trägt KEINE bfb-live-Umrandung mehr');
  assert.match(html, /● LIVE/, 'das LIVE-Badge ist weiterhin da');
});

test('×Norm-Badge ist orange (#f0883e), nicht rot', () => {
  const peers = [];
  for (let i = 0; i < 4; i++) peers.push(m1x2(10 + i, 'Peer' + i, 'P', 2000, 500, 500, 2.0));   // je €3000
  const big = m1x2(20, 'BigFC', 'B', 8000, 500, 500, 1.5);                                       // €9000 → 3.0× Median
  const w = boot([...peers, big]);
  const ratio = w._bfNormRatio(w._bfState.data.matches.find(m => m.home === 'BigFC'));
  assert.ok(ratio >= 2.6, 'Norm-Ratio (' + ratio + ') liegt in der hohen Stufe');
  const html = w._renderBetfairRadar();
  assert.match(html, /color:#f0883e;border-color:#f0883e[^>]*>×[\d.]+ Norm/, '×Norm-Badge trägt Orange');
  assert.ok(!/color:#f85149;border-color:#f85149[^>]*>×[\d.]+ Norm/.test(html), 'kein rotes ×Norm-Badge mehr');
});

test('Regression: dominante Fixture-Spiele (72–97%) bleiben sichtbar', () => {
  const w = boot([
    m1x2(1, 'FavHome', 'A', 7500, 1300, 1200, 1.6),   // 75%
    m1x2(2, 'BigFav', 'B', 9100, 500, 400, 1.4),      // 91%
  ]);
  const block = hotspotBlock(w._renderBetfairRadar());
  assert.match(block, /FavHome/); assert.match(block, /BigFav/);
});
