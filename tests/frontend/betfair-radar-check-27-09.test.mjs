// tests/frontend/betfair-radar-check-27-09.test.mjs — Radar-Check 27.09.2026 (Lucas: „kannst mal
// betfair radar checken, denke da auch eventuell was zu optimieren").
//   1. „▼ Geld → Lithuania", aber das meiste 1X2-Geld lag auf Remis — die Pille las den Preis.
//   2. „Remis @1.54 ▲ +320 % 🚨" bei 1:1 in Minute ~98 — Uhr-Zerfall, kein Alarm.
//   3. Ein Duenn-Markt mit +€2,3K stand VOR +€16,7K in „Größte Zuflüsse (€)".
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const ROOT = new URL('../../', import.meta.url);
const ko = (h) => new Date(Date.now() + h * 3600e3).toISOString();
const ts = (min) => new Date(Date.now() - min * 60e3).toISOString();

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
function m1x2(id, home, away, hw, dr, aw, opts) {
  opts = opts || {};
  return { matchId: id, home, away, league: 'Test League', country: 'GB', kickoff: opts.ko || ko(9),
    liveInfo: opts.live || {}, totalVol: hw + dr + aw,
    markets: { 'Match Odds': { vol: hw + dr + aw, runners: [
      { name: home, odd: opts.oddH || 2.0, vol: hw }, { name: 'The Draw', odd: opts.oddD || 3.5, vol: dr },
      { name: away, odd: 4.0, vol: aw }] } } };
}
function cardOf(html, id) {
  const a = html.indexOf('id="bfg-' + id + '"'); if (a < 0) return '';
  const b = html.indexOf('id="bfg-', a + 5); return html.slice(a, b > a ? b : html.length);
}
const steam = (id) => ({ [id]: [
  { ts: ts(40), mo: { hw: 2.0, dr: 3.5, aw: 4.0 }, totalVol: 1000 },
  { ts: ts(2), mo: { hw: 1.6, dr: 3.5, aw: 4.0 }, totalVol: 2000 }] });

test('1. Preis fällt auf Heim, Geld liegt aufs Remis: die Pille behauptet kein Geld', () => {
  const w = boot([m1x2(1, 'Lithuania', 'Azerbaijan', 1400, 7200, 1400)], steam(1));
  const c = cardOf(w._renderBetfairRadar(), 1);
  assert.doesNotMatch(c, /Geld → Lithuania/);
  assert.match(c, /▼ Lithuania/);
  assert.match(c, /Quote fällt/);
});

test('1. Gegenbeweis: liegt das Geld auf derselben Seite, bleibt „Geld →"', () => {
  const w = boot([m1x2(1, 'Lithuania', 'Azerbaijan', 7200, 1400, 1400)], steam(1));
  assert.match(cardOf(w._renderBetfairRadar(), 1), /Geld → Lithuania/);
});

test('2. Live-Remis bei Gleichstand ist reaktiv, bei Führung und vor Anpfiff nicht', () => {
  const w = boot([]);
  const live = (g1, g2) => ({ liveInfo: { time: 80, goal_v1: g1, goal_v2: g2 }, kickoff: ko(-1.5) });
  const R = w._bfReactive;
  const lv = (g1, g2) => Object.assign({ home: 'A', away: 'B' }, live(g1, g2));
  // isLive braucht die Felder, die das Modul liest — ueber den echten Weg pruefen:
  assert.equal(typeof R, 'function');
  const mEq = lv(1, 1), mLead = lv(1, 0), mPre = { home: 'A', away: 'B', liveInfo: {}, kickoff: ko(3) };
  assert.equal(R(mEq, 'The Draw'), true, 'Remis bei 1:1 live');
  assert.equal(R(mLead, 'The Draw'), false, 'Remis bei 1:0 ist kein Uhr-Zerfall');
  assert.equal(R(mPre, 'The Draw'), false, 'vor Anpfiff nie reaktiv');
  assert.equal(R(mEq, 'A'), false, 'nur das Remis');
});

function flowMatch(id, home, away, prev, curr, opts) {
  const m = m1x2(id, home, away, curr * 0.2, curr * 0.6, curr * 0.2, opts);
  return { m, hist: { [id]: [
    { ts: ts(20), mo: { hw: 2, dr: 1.54, aw: 4 }, totalVol: prev, mkv: { 'Match Odds': prev } },
    { ts: ts(2), mo: { hw: 2, dr: 1.54, aw: 4 }, totalVol: curr, mkv: { 'Match Odds': curr } }] } };
}

test('2. Der Sprung auf ein Live-Remis bei 1:1 bekommt „reaktiv" statt 🚨', () => {
  const f = flowMatch(7, 'Casertana', 'Catania', 4400, 18600, { oddD: 1.54, ko: ko(-1.6), live: { time: 81, goal_v1: 1, goal_v2: 1 } });
  const w = boot([f.m], f.hist);
  const html = w._renderBetfairRadar();
  const i = html.indexOf('Größte Sprünge');
  assert.ok(i > 0, 'Sprung-Liste fehlt');
  const block = html.slice(i, i + 4000);
  assert.match(block, /reaktiv/);
  assert.doesNotMatch(block, /🚨/);
});

test('3. „Größte Zuflüsse (€)" ist nach Euro sortiert, dünne Märkte stehen darunter', () => {
  const big = flowMatch(1, 'Norway', 'Portugal', 272000, 288700);          // +16,7K
  const thin = flowMatch(2, 'Valladolid', 'Cordoba', 2700, 5000);           // +2,3K = 46 % des Marktes
  const w = boot([big.m, thin.m], Object.assign({}, big.hist, thin.hist));
  const html = w._renderBetfairRadar();
  const eur = html.indexOf('Größte Zuflüsse'), duenn = html.indexOf('Dünne Märkte');
  assert.ok(eur > 0 && duenn > eur, 'eigene Liste für dünne Märkte, unter der Euro-Liste');
  const eurBlock = html.slice(eur, html.indexOf('Größte Sprünge') > eur ? html.indexOf('Größte Sprünge') : duenn);
  assert.match(eurBlock, /Norway/);
  assert.doesNotMatch(eurBlock, /Valladolid/, 'der Dünn-Markt steht nicht mehr in der Euro-Liste');
  assert.match(html.slice(duenn, duenn + 3000), /Valladolid/);
});

function chip(ageMin) {
  const w = boot([m1x2(1, 'A', 'B', 7200, 1400, 1400)]);
  w._bfState.data._meta.generatedAt = new Date(Date.now() - ageMin * 60e3).toISOString();
  return w._renderBetfairRadar();
}

test('4. 17 Minuten alt ist der normale Takt (Lauf + Deploy), kein „überfällig"', () => {
  const h = chip(17);
  assert.doesNotMatch(h, /überfällig/);
  assert.match(h, /nächster gleich/);
});

test('4. Gegenbeweis: fehlt wirklich ein Lauf, steht es da', () => {
  assert.match(chip(35), /überfällig/);
  assert.match(chip(90), /Fetcher hängt/);
});

test('5. Keine Top-5-Spiele: keine „€0 · 0 Spiele"-Kachel; mit Spiel ist sie da', () => {
  assert.doesNotMatch(chip(3), /Top 5 \+ MLS<\/div>\s*<div[^>]*>0 Spiele/);
  const w = boot([m1x2(1, 'A', 'B', 7200, 1400, 1400)]);
  assert.doesNotMatch(w._renderBetfairRadar(), />0 Spiele</);
});

test('6. „sammelt nX/30" steht je Liga nur auf der ersten Karte, Urteile auf jeder', () => {
  const ms = [1, 2, 3].map((i) => Object.assign(m1x2(i, 'H' + i, 'G' + i, 7200, 1400, 1400), { league: 'UEFA Nations League' }));
  const w = boot(ms);
  w._bfState.track = { byLeagueMarket: { 'UEFA Nations League|Match Odds': { n: 26, roi: 0.05, hitRate: 0.5 } } };
  const html = w._renderBetfairRadar();
  const karten = [1, 2, 3].map((i) => cardOf(html, i));
  assert.equal(karten.filter((c) => /n26\/30/.test(c)).length, 1, 'genau einmal pro Liga');
  // Gegenbeweis: ein Urteil steht auf jeder Karte
  const w2 = boot(ms);
  w2._bfState.track = { byLeagueMarket: { 'UEFA Nations League|Match Odds': { n: 60, roi: -0.3, hitRate: 0.3, urteil: 'verliert' } } };
  const h2 = w2._renderBetfairRadar();
  assert.equal([1, 2, 3].map((i) => cardOf(h2, i)).filter((c) => /verliert belegt/.test(c)).length, 3);
});

test('7. Deep-Dive sitzt kompakt in der Karte, keine eigene Fusszeile mehr', () => {
  const w = boot([m1x2(1, 'A', 'B', 7200, 1400, 1400)]);
  const c = cardOf(w._renderBetfairRadar(), 1);
  assert.match(c, /🔬 Deep-Dive/);
  assert.match(c, /_bfDrawer\('1'\)/, 'Knopf öffnet weiter den Drawer');
  assert.doesNotMatch(c, /justify-content:flex-end">\s*<button[^>]*_bfDrawer/, 'keine Fusszeile nur für den Knopf');
});

test('8. Die Balkenfarben sind erklärt, in der Reihenfolge des Feeds (Heim · Remis · Auswärts)', () => {
  const h = boot([m1x2(1, 'A', 'B', 7200, 1400, 1400)])._renderBetfairRadar();
  const i = h.indexOf('So liest du den Radar');
  const leg = h.slice(i, i + 3000);
  assert.ok(leg.indexOf('Heim') < leg.indexOf('Remis') && leg.indexOf('Remis') < leg.indexOf('Auswärts'));
});

test('9. Handy: Zeilen brechen um, Ansichts-Leiste bricht um (keine 464 px auf 390)', () => {
  const w = boot([m1x2(1, 'A', 'B', 7200, 1400, 1400)]);
  w._renderBetfairRadar();
  const css = w.document.getElementById('bfb-css').textContent;
  assert.match(css, /@media\(max-width:560px\)\{\.bfb-row\{grid-template-columns:minmax\(0,1fr\) auto/);
  assert.match(css, /\.bfv-tabs\{display:flex !important;flex-wrap:wrap/);
  assert.match(w._renderBetfairRadar(), /class="bfv-tabs"/);
});
