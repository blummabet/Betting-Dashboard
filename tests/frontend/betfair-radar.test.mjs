// tests/frontend/betfair-radar.test.mjs — Betfair Radar v4 (29.07.2026, Lucas-Feedback #3).
// Prüft: EU-Flagge für UEFA / 🌍 sonst · € (kein £) · Karten eingeklappt mit komprimiertem
// Top-Markt · Klick klappt alle Märkte auf · Hotspots mit konkretem Ausgang · drei Ebenen
// (Top/Intl/Rest) · Geld-Verteilung · Stale-Guard · Tab-Filter.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const ROOT = new URL('../../', import.meta.url);
function boot() {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="betfairRadarPanel"></div></body>',
    { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.eval(readFileSync(new URL('betfair-radar.js', ROOT), 'utf8'));
  const prices = JSON.parse(readFileSync(new URL('betfair_prices.json', ROOT), 'utf8'));
  w._bfState.data = prices;
  w._bfState.hist = JSON.parse(readFileSync(new URL('betfair_history.json', ROOT), 'utf8'));
  w._bfState.loading = false;
  w._bfState.league = 'all'; w._bfState.tab = 'all'; w._bfState.date = 'all'; w._bfState.cardOpen = {};
  return { w, prices };
}
function render() { const { w, prices } = boot(); return { w, prices, html: w._renderBetfairRadar() }; }

test('EU-Flagge für UEFA, 🌍 für sonstige internationale', () => {
  const { html } = render();
  assert.match(html, /\u{1F1EA}\u{1F1FA}/u, 'EU-Flagge (UEFA)');
  assert.match(html, /\u{1F30D}/u, 'Globus (CAF/Friendly)');
});

test('Beträge in € — gar kein £ mehr', () => {
  const { html } = render();
  assert.match(html, /€/);
  assert.ok(!/£/.test(html), 'kein Pfund-Zeichen');
});

test('Karten standard eingeklappt, komprimierter Top-Markt', () => {
  const { html } = render();
  assert.match(html, /▸/, 'Chevron eingeklappt');
  assert.match(html, /alle Märkte/, 'Hinweis auf Aufklappen');
  // komprimierte Zeile zeigt den führenden Ausgang mit Prozent
  assert.match(html, /→ /);
});

test('Klick klappt alle Märkte der Karte auf', () => {
  const { w, prices } = boot();
  const kairat = prices.matches.find(m => m.home === 'Kairat Almaty');
  const before = w._renderBetfairRadar();
  assert.ok(!/HT Ü0\.5/.test(before.slice(before.indexOf('Kairat Almaty'), before.indexOf('Kairat Almaty') + 1200)), 'HT-Markt eingeklappt noch nicht offen');
  w._bfCard(kairat.matchId);
  const after = w.document.getElementById('betfairRadarPanel').innerHTML;
  assert.match(after, /HT Ü0\.5/, 'nach Klick sind alle Märkte (inkl. HT) offen');
});

test('Hotspot-Leiste zeigt konkreten Ausgang + %', () => {
  const { html } = render();
  assert.match(html, /größte Einzel-Ausgänge/);
  assert.match(html, /→ (Fenerbahce|Kairat Almaty|Crvena Zvezda|Tottenham|U 2\.5|Ü 2\.5)/);
});

test('Drei Ebenen — International/UEFA-Sektion + Tier-Logik', () => {
  const { w, html } = render();
  assert.match(html, /International \/ UEFA/);
  assert.strictEqual(w._bfTier({ league: 'UEFA Champions League Qualifiers', country: 'International' }), 'intl');
  assert.strictEqual(w._bfTier({ league: 'German Bundesliga', country: 'DE' }), 'top');
  assert.strictEqual(w._bfTier({ league: 'Bulgarian First League', country: 'BG' }), 'rest');
});

test('Geld-Verteilung: Balken + %/€ je Ausgang (aufgeklappt)', () => {
  const { w, prices } = boot();
  const g = prices.matches.find(m => m.home === 'Gornik Zabrze');
  w._bfCard(g.matchId);
  const html = w._renderBetfairRadar();
  const i = html.indexOf('Gornik Zabrze');
  const block = html.slice(i, i + 2500);
  assert.match(block, /Fenerbahce/, 'Auswärts-Runner gelistet');
  assert.match(block, /7[0-9]%|72%/, 'dominanter Auswärts-Anteil (~72%)');
});

test('Tab-Filter: nur International', () => {
  const { w } = boot();
  w._bfState.tab = 'intl';
  const html = w._renderBetfairRadar();
  assert.match(html, /Kairat Almaty/);
  assert.ok(!/⭐ Top 5 \+ MLS<\/h2>/.test(html) || !/German Bundesliga/.test(html));
});

test('Pfeil-Legende erklärt Back/Lay', () => {
  const { html } = render();
  assert.match(html, /Quote fällt/);
  assert.match(html, /Quote steigt/);
  assert.match(html, /Back/);
  assert.match(html, /Lay/);
});

test('alle aufklappen / alle zu', () => {
  const { w } = boot();
  w._bfCards(true);
  const open = w._renderBetfairRadar();
  assert.match(open, /▾/, 'aufgeklappt');
  w._bfCards(false);
  const closed = w._renderBetfairRadar();
  assert.ok((closed.match(/▾/g) || []).length === 0, 'alle zu');
});

test('Stale-Guard: alte Daten → Banner, kein Fake-Live', () => {
  const { w } = boot();
  w._bfState.data._meta.generatedAt = new Date(Date.now() - 26 * 3.6e6).toISOString();
  const html = w._renderBetfairRadar();
  assert.match(html, /alt/);
});
