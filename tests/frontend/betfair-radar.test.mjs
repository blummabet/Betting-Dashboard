// tests/frontend/betfair-radar.test.mjs — Betfair Radar v2 Rendering (29.07.2026, Lucas-Redesign).
// Prüft: zwei Sektionen (Top5+MLS / Rest), € statt £, Flaggen, nur Märkte mit Geld,
// ausgebautes Info-Band, Live-Pill nur bei frischen Daten, Tab-/Liga-Filter.
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
  w._bfState.data = JSON.parse(readFileSync(new URL('betfair_prices.json', ROOT), 'utf8'));
  w._bfState.hist = JSON.parse(readFileSync(new URL('betfair_history.json', ROOT), 'utf8'));
  w._bfState.loading = false;
  w._bfState.league = 'all';
  w._bfState.tab = 'both';
  return w;
}
function render() { const w = boot(); return { w, html: w._renderBetfairRadar() }; }

test('Kopf + ausgebautes Info-Band', () => {
  const { html } = render();
  assert.match(html, /Betfair/);
  assert.match(html, /Radar/);
  assert.match(html, /Geld gematcht gesamt/, 'Info-Tile Gesamtvolumen');
  assert.match(html, /Top 5 \+ MLS/, 'Info-Tile Top5/MLS');
  assert.match(html, /meiste HT-Action/, 'Info-Tile HT-Action');
});

test('Zwei Sektionen: Top5+MLS und Rest', () => {
  const { html } = render();
  assert.match(html, /⭐ Top 5 \+ MLS/, 'Sektion Top5/MLS');
  assert.match(html, /Rest — alle anderen Ligen/, 'Sektion Rest');
  // Top-Sektion (Untertitel €10k FT) steht vor Rest-Sektion (Untertitel €1,5k HT)
  assert.ok(html.indexOf('€10k FT') > -1 && html.indexOf('€1,5k HT') > -1, 'beide Sektions-Untertitel da');
  assert.ok(html.indexOf('€10k FT') < html.indexOf('€1,5k HT'), 'Top-Sektion vor Rest-Sektion');
});

test('Beträge in € — keine £-Beträge (nur Fußnote)', () => {
  const { html } = render();
  assert.match(html, /€/, 'Euro-Zeichen da');
  assert.ok(!/£\s*[0-9]/.test(html), 'kein £-Betrag');
  assert.strictEqual((html.match(/£/g) || []).length, 1, '£ nur in der Umrechnungs-Fußnote');
});

test('Flagge vor der Paarung', () => {
  const { html } = render();
  assert.match(html, /\u{1F1E9}\u{1F1EA}/u, 'DE-Flagge (Regional Indicators)');
  assert.match(html, /\u{1F1FA}\u{1F1F8}/u, 'US-Flagge');
});

test('Nur Märkte mit Geld — kein leerer Markt-Chip', () => {
  const { html } = render();
  // Jeju United (kleinste Liquidität): BTTS liegt unter dem €-Floor → kein BTTS-Chip in seiner Karte.
  const i = html.indexOf('Jeju United');
  assert.ok(i > -1, 'Jeju gerendert');
  const block = html.slice(i, i + 2600);
  assert.ok(!/BTTS/.test(block), 'BTTS-Chip unter Floor ausgeblendet');
});

test('Richtung aus History (gebackt/gelayt)', () => {
  const { html } = render();
  assert.match(html, /gebackt|gelayt/, 'Richtungs-Pill aus Preisbewegung');
  assert.match(html, /▼|▲/, 'Richtungs-Pfeil');
});

test('Live-Pill nur bei frischen Daten', () => {
  const { html } = render();
  assert.match(html, /LIVE 38/, 'frisches Live-Spiel zeigt Minute');
});

test('Stale-Guard: alte Daten → kein Fake-Live, Banner', () => {
  const w = boot();
  // generatedAt weit in die Vergangenheit → isLive muss unterdrücken
  w._bfState.data._meta.generatedAt = new Date(Date.now() - 26 * 3.6e6).toISOString();
  const html = w._renderBetfairRadar();
  assert.ok(!/LIVE 38/.test(html), 'kein Live bei veralteten Daten');
  assert.match(html, /alt/, 'Stale-Banner sichtbar');
});

test('Tab-Filter: nur Top / nur Rest', () => {
  const w = boot();
  w._bfState.tab = 'top';
  const top = w._renderBetfairRadar();
  assert.match(top, /Bayern Munich/);
  assert.ok(!/Rest — alle anderen Ligen/.test(top), 'Rest-Sektion aus');
  assert.ok(!/€10k FT/.test(top) === false, 'Top-Sektion-Untertitel da im Top-Tab');
  w._bfState.tab = 'rest';
  const rest = w._renderBetfairRadar();
  assert.match(rest, /Levski Sofia/);
  // Top-Sektion-Header (Untertitel €10k FT) darf im Rest-Tab nicht erscheinen (Tab-Button zählt nicht).
  assert.ok(!/€10k FT/.test(rest), 'Top-Sektion aus');
});

test('Liga-Dropdown filtert', () => {
  const w = boot();
  w._bfState.league = 'German Bundesliga';
  const html = w._renderBetfairRadar();
  assert.match(html, /Bayern Munich/);
  assert.ok(!/Levski Sofia/.test(html), 'andere Ligen raus');
  assert.match(html, /Alle Ligen/, 'Dropdown-Option da');
});
