// tests/frontend/betfair-radar.test.mjs — Betfair Radar v3 (29.07.2026, Lucas-Feedback #2).
// Prüft: Hotspot-Leiste, Datumsauswahl+Filter, Geld-Verteilung (Segment-Balken €+%),
// heißester Markt offen / Rest per Klick, CL/EL-Quali im Top-Bucket, Pfeil-Legende,
// € statt £, Stale-Guard, Tab-Filter.
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
  w._bfState.league = 'all'; w._bfState.tab = 'both'; w._bfState.date = 'all';
  w._bfState.open = {}; w._bfState.seeded = false;
  return { w, prices };
}
function render() { const { w, prices } = boot(); return { w, prices, html: w._renderBetfairRadar() }; }

test('Kopf + Info-Band inkl. UEFA-Kachel', () => {
  const { html } = render();
  assert.match(html, /Betfair/);
  assert.match(html, /Geld gematcht gesamt/);
  assert.match(html, /Top 5 \+ MLS \+ UEFA/);
  assert.match(html, /meiste HT-Action/);
});

test('Hotspot-Leiste zeigt heißeste Einzelmärkte', () => {
  const { html } = render();
  assert.match(html, /Meistes Geld gerade/);
  assert.match(html, /springt zum Spiel/);
});

test('Datumsauswahl vorhanden (Heute/Morgen)', () => {
  const { html } = render();
  assert.match(html, /📅 Datum/);
  assert.match(html, /Heute/);
  assert.match(html, /Morgen/);
});

test('Datumsfilter blendet andere Tage aus', () => {
  const { w, prices } = boot();
  const arsenal = prices.matches.find(m => m.home === 'Arsenal');
  const tomKey = new Date(Date.parse(arsenal.kickoff)).toLocaleDateString('en-CA');
  w._bfState.date = tomKey;
  const html = w._renderBetfairRadar();
  assert.match(html, /Arsenal/, 'Spiel des gewählten Tages sichtbar');
  assert.ok(!/Bayern Munich/.test(html), 'anderer Tag ausgeblendet');
});

test('Geld-Verteilung: Segment-Balken + % je Ausgang', () => {
  const { html } = render();
  // im geöffneten (heißesten) Markt stehen Prozent-Werte je Ausgang
  assert.match(html, /[0-9]{1,3}%<\/span>/, 'Prozent je Ausgang');
  // ein dominanter Anteil ist sichtbar (Bayern-Favorit)
  const bi = html.indexOf('Bayern Munich');
  assert.match(html.slice(bi, bi + 4000), /[5-9][0-9]%/, 'dominanter Geld-Anteil');
});

test('Heißester Markt offen (▾), weitere zu (▸)', () => {
  const { html } = render();
  assert.match(html, /▾/, 'mind. ein Markt aufgeklappt');
  assert.match(html, /▸/, 'weitere Märkte eingeklappt');
});

test('Klick klappt Markt auf/zu (Toggle)', () => {
  const { w, prices } = boot();
  const before = w._renderBetfairRadar();
  const bay = prices.matches.find(m => m.home === 'Bayern Munich');
  w._bfToggle(bay.matchId + '|Over/Under 2.5 Goals');   // zweiten Markt aufklappen
  const panel = w.document.getElementById('betfairRadarPanel');
  const after = panel.innerHTML;
  assert.notStrictEqual(before, after, 'Ausgabe ändert sich beim Toggle');
  // nach dem Aufklappen erscheint die Über/Unter-Verteilung von Bayern
  assert.match(after, /Ü 2\.5|Über|Ü2\.5/);
});

test('CL/EL-Quali zählt zum Top-Bucket', () => {
  const { html } = render();
  assert.match(html, /Dinamo Zagreb/);
  assert.match(html, /UEFA Champions League Qualifying/);
  assert.ok(html.indexOf('Dinamo Zagreb') < html.indexOf('Rest — alle anderen Ligen'),
    'CL-Quali steht in der Top-Sektion, nicht im Rest');
});

test('Pfeil-Legende erklärt Back/Lay', () => {
  const { html } = render();
  assert.match(html, /Quote fällt/);
  assert.match(html, /Quote steigt/);
  assert.match(html, /Back/);
  assert.match(html, /Lay/);
});

test('Beträge in € — keine £-Beträge (nur Fußnote)', () => {
  const { html } = render();
  assert.match(html, /€/);
  assert.ok(!/£\s*[0-9]/.test(html));
  assert.strictEqual((html.match(/£/g) || []).length, 1);
});

test('Stale-Guard: alte Daten → kein Fake-Live', () => {
  const { w } = boot();
  w._bfState.data._meta.generatedAt = new Date(Date.now() - 26 * 3.6e6).toISOString();
  const html = w._renderBetfairRadar();
  assert.ok(!/LIVE 38/.test(html), 'kein Live bei veralteten Daten');
  assert.match(html, /alt/, 'Stale-Banner');
});

test('Tab-Filter: nur Top / nur Rest', () => {
  const { w } = boot();
  w._bfState.tab = 'top';
  const top = w._renderBetfairRadar();
  assert.match(top, /Bayern Munich/);
  assert.ok(!/Rest — alle anderen Ligen/.test(top));
  w._bfState.tab = 'rest';
  const rest = w._renderBetfairRadar();
  assert.match(rest, /Levski Sofia/);
  assert.ok(!/€10k FT/.test(rest), 'Top-Sektion-Untertitel weg');
});
