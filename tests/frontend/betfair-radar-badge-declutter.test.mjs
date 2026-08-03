// tests/frontend/betfair-radar-badge-declutter.test.mjs — 03.08.2026 (Lucas: „zu viele Badges,
// live irreführend"). Die KARTE trägt nur noch Steam + Geld→ und NUR vor Anpfiff; live sind beide
// weg (Spielstand ≠ Wettsignal). Der Kohärenz-Kram lebt im Deep-Dive (full=true). LIVE bleibt oben.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const ROOT = new URL('../../', import.meta.url);
const ko = (h) => new Date(Date.now() + h * 3600e3).toISOString();

function boot(matches, hist) {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="betfairRadarPanel"></div></body>', { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window; w._bfNoAutoRefresh = true;
  w.eval(readFileSync(new URL('betfair-radar.js', ROOT), 'utf8'));
  w._bfState.data = { _meta: { generatedAt: new Date().toISOString(), n: matches.length, live: 0, currency: 'EUR', source: 'test' }, matches };
  w._bfState.hist = hist || {}; w._bfState.loading = false;
  if (w._bfTHR) { w._bfTHR.top = { FT: 1000, HT: 500 }; w._bfTHR.intl = { FT: 1000, HT: 500 }; w._bfTHR.rest = { FT: 1000, HT: 500 }; }
  w._bfState.league = 'all'; w._bfState.tab = 'all'; w._bfState.date = 'all'; w._bfState.cardOpen = {};
  return w;
}
function m1x2(id, home, away, hw, dr, aw, oddH, opts) {
  opts = opts || {};
  return { matchId: id, home, away, league: 'Test League', country: 'GB', kickoff: opts.ko || ko(9),
    liveInfo: opts.live || {}, totalVol: hw + dr + aw,
    markets: { 'Match Odds': { vol: hw + dr + aw, runners: [
      { name: home, odd: oddH, vol: hw }, { name: 'The Draw', odd: 3.5, vol: dr }, { name: away, odd: 4.0, vol: aw }] } } };
}
// Steam: Heim-Quote zieht 2.0→1.6, Volumen verdoppelt → moveOf + cohFlow(steam) feuern
function steamHist(id) {
  const t0 = new Date(Date.now() - 40 * 60e3).toISOString(), t1 = new Date(Date.now() - 2 * 60e3).toISOString();
  return { [id]: [
    { ts: t0, mo: { hw: 2.0, dr: 3.5, aw: 4.0, vol: 1000 }, totalVol: 1000 },
    { ts: t1, mo: { hw: 1.6, dr: 3.5, aw: 4.0, vol: 2000 }, totalVol: 2000 },
  ] };
}
function cardOf(html, id) {
  const a = html.indexOf('id="bfg-' + id + '"'); if (a < 0) return '';
  const b = html.indexOf('id="bfg-', a + 5); return html.slice(a, b > a ? b : html.length);
}

test('Pre-Match-Karte zeigt Steam + Geld→', () => {
  const w = boot([m1x2(1, 'Alpha', 'Beta', 7200, 1400, 1400, 2.0, { ko: ko(9) })], steamHist(1));
  const c = cardOf(w._renderBetfairRadar(), 1);
  assert.match(c, /↯ Steam/, 'Steam auf der Karte');
  assert.match(c, /Geld → Alpha/, 'Geld-Richtung auf der Karte');
});

test('Live-Karte: Geld→ UND Steam weg (Spielstand ≠ Wettsignal), LIVE bleibt', () => {
  const w = boot([m1x2(1, 'Alpha', 'Beta', 7200, 1400, 1400, 2.0, { live: { time: 30, finished: false }, ko: ko(-0.3) })], steamHist(1));
  const c = cardOf(w._renderBetfairRadar(), 1);
  assert.ok(!/Geld → Alpha/.test(c), 'kein Geld→ auf der Live-Karte');
  assert.ok(!/↯ Steam/.test(c), 'kein Steam auf der Live-Karte');
  assert.match(c, /LIVE/, 'LIVE-Badge bleibt');
});

test('Kohärenz-Chips (Modell-Lücken/harte Abweichung) NICHT auf der Karte', () => {
  // (mit reinen Match-Odds entstehen ohnehin keine — der Test sichert, dass die Karte sie nie zeigt)
  const w = boot([m1x2(1, 'Alpha', 'Beta', 7200, 1400, 1400, 2.0, { ko: ko(9) })], steamHist(1));
  const c = cardOf(w._renderBetfairRadar(), 1);
  assert.ok(!/Modell-Lücke/.test(c), 'keine Modell-Lücken-Chips auf der Karte');
  assert.ok(!/harte Abweichung/.test(c), 'keine harte-Abweichung-Chips auf der Karte');
  assert.ok(!/über Norm/.test(c), 'kein Markt×über-Norm auf der Karte');
});

test('Deep-Dive zeigt die volle Pill-Reihe (Steam sichtbar, auch live)', () => {
  const w = boot([m1x2(1, 'Alpha', 'Beta', 7200, 1400, 1400, 2.0, { live: { time: 30, finished: false }, ko: ko(-0.3) })], steamHist(1));
  w._renderBetfairRadar();
  w._bfDrawer('1');
  const drawer = w.document.getElementById('bfdIn').innerHTML;
  assert.match(drawer, /↯ Steam/, 'Steam im Deep-Dive sichtbar');
  assert.match(drawer, /● LIVE/, 'LIVE im Deep-Dive-Header');
});

test('Mobile Safe-Area-CSS für den Deep-Dive-Schließen-Button ist injiziert', () => {
  const w = boot([m1x2(1, 'Alpha', 'Beta', 7200, 1400, 1400, 2.0)], {});
  w._renderBetfairRadar();
  const css = [...w.document.querySelectorAll('style')].map(s => s.textContent).join('');
  assert.match(css, /\.bfd-close\{[^}]*safe-area-inset-top/, 'bfd-close bekommt Safe-Area-Top');
  assert.match(css, /\.bfd-hd\{[^}]*safe-area-inset-top/, 'bfd-hd bekommt Safe-Area-Top');
});
