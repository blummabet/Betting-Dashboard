// tests/frontend/betfair-radar.test.mjs — Betfair Radar v4 (29.07.2026, Lucas-Feedback #3).
// WICHTIG: nutzt eine INLINE-Fixture, NICHT die Live-betfair_prices.json — sonst brechen die Tests,
// sobald der echte Fetcher andere Zahlen schreibt (genau das ist am 29.07. passiert).
// Prüft: EU-Flagge für UEFA / 🌍 sonst · € (kein £) · Karten eingeklappt mit komprimiertem
// Top-Markt · Klick klappt alle Märkte auf · Hotspots mit konkretem Ausgang · drei Ebenen
// (Top/Intl/Rest) · Geld-Verteilung · Stale-Guard · Tab-Filter.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const ROOT = new URL('../../', import.meta.url);

function iso(msFromNow = 0) { return new Date(Date.now() + msFromNow).toISOString(); }
function ko(hours) { return iso(hours * 3600e3); }

// Kontrollierte Fixture (Beträge in €). Deckt UEFA + Friendly + CAF, Verteilung, HT-Markt, Direction.
function fixture() {
  return {
    _meta: { generatedAt: iso(0), n: 4, live: 0, currency: 'EUR', source: 'test-fixture' },
    matches: [
      { matchId: 1, home: 'Kairat Almaty', away: 'Omonia', league: 'UEFA Champions League Qualifiers',
        country: 'International', kickoff: ko(9), liveInfo: {}, totalVol: 19569,
        markets: {
          'Match Odds': { vol: 17469, runners: [
            { name: 'Kairat Almaty', odd: 2.32, vol: 13009 },
            { name: 'The Draw', odd: 3.5, vol: 2952 },
            { name: 'Omonia', odd: 3.65, vol: 1508 }] },
          'First Half Goals 0.5': { vol: 2100, runners: [
            { name: 'Over 0.5 Goals', odd: 1.3, vol: 1260 },
            { name: 'Under 0.5 Goals', odd: 3.6, vol: 840 }] },
        } },
      { matchId: 4, home: 'Gornik Zabrze', away: 'Fenerbahce', league: 'UEFA Champions League Qualifiers',
        country: 'International', kickoff: ko(9), liveInfo: {}, totalVol: 10808,
        markets: {
          'Match Odds': { vol: 9408, runners: [
            { name: 'Gornik Zabrze', odd: 7.0, vol: 1393 },
            { name: 'The Draw', odd: 4.5, vol: 1268 },
            { name: 'Fenerbahce', odd: 1.57, vol: 6747 }] },   // 6747/9408 = 72 % (Auswärts dominant)
          'First Half Goals 0.5': { vol: 1400, runners: [
            { name: 'Over 0.5 Goals', odd: 1.28, vol: 900 },
            { name: 'Under 0.5 Goals', odd: 3.8, vol: 500 }] },
        } },
      { matchId: 7, home: 'Atletico Madrid', away: 'Getafe', league: 'Elite Friendlies',
        country: 'International', kickoff: ko(9), liveInfo: {}, totalVol: 14707,
        markets: {
          'Over/Under 2.5 Goals': { vol: 14707, runners: [
            { name: 'Under 2.5 Goals', odd: 2.08, vol: 13965 },
            { name: 'Over 2.5 Goals', odd: 1.92, vol: 742 }] },
        } },
      { matchId: 9, home: 'Cameroon (W)', away: 'Mali (W)', league: 'CAF Ladies Africa Nations Cup',
        country: 'International', kickoff: ko(12), liveInfo: {}, totalVol: 4055,
        markets: {
          'Over/Under 2.5 Goals': { vol: 4055, runners: [
            { name: 'Under 2.5 Goals', odd: 1.74, vol: 3933 },
            { name: 'Over 2.5 Goals', odd: 2.36, vol: 122 }] },
        } },
    ],
  };
}
function histFixture() {
  return {
    '4': [{ ts: iso(-2 * 3600e3), mo: { hw: 6.5, dr: 4.4, aw: 1.72, vol: 6000 } },
          { ts: iso(0), mo: { hw: 7.0, dr: 4.5, aw: 1.57, vol: 9408 } }],  // Auswärts verkürzt → gebackt
    _meta: { updatedAt: iso(0) },
  };
}

function boot() {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="betfairRadarPanel"></div></body>',
    { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w._bfNoAutoRefresh = true;   // Auto-Refresh-Timer in Tests aus (sonst hängt die Event-Loop)
  w.eval(readFileSync(new URL('betfair-radar.js', ROOT), 'utf8'));
  const prices = fixture();
  w._bfState.data = prices;
  w._bfState.hist = histFixture();
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
  assert.match(html, /→ (Fenerbahce|Kairat Almaty|U 2\.5|Ü 2\.5)/);
});

test('Drei Ebenen — International/UEFA-Sektion + Tier-Logik', () => {
  const { w, html } = render();
  assert.match(html, /International \/ UEFA/);
  assert.strictEqual(w._bfTier({ league: 'UEFA Champions League Qualifiers', country: 'International' }), 'intl');
  assert.strictEqual(w._bfTier({ league: 'German Bundesliga', country: 'DE' }), 'top');
  assert.strictEqual(w._bfTier({ league: 'Bulgarian First League', country: 'BG' }), 'rest');
  // KEINE Fehl-Einordnung in Top5 (Regex war zu locker): Land-qualifiziert + keine Freundschafts-Turniere
  assert.strictEqual(w._bfTier({ league: 'Brazilian Serie A', country: 'BR' }), 'rest', 'Brasilien ≠ Top5');
  assert.strictEqual(w._bfTier({ league: 'Bhutan Premier League', country: 'BT' }), 'rest', 'Bhutan ≠ Top5');
  assert.strictEqual(w._bfTier({ league: 'English Premier League Summer Series', country: 'GB' }), 'rest', 'Sommer-Friendly ≠ Top5');
  assert.strictEqual(w._bfTier({ league: 'Italian Serie A', country: 'IT' }), 'top');
  assert.strictEqual(w._bfTier({ league: 'USA MLS', country: 'US' }), 'top');
});

test('Geld-Verteilung: Balken + %/€ je Ausgang (aufgeklappt)', () => {
  const { w, prices } = boot();
  const g = prices.matches.find(m => m.home === 'Gornik Zabrze');
  w._bfCard(g.matchId);
  const html = w._renderBetfairRadar();
  const i = html.indexOf('Gornik Zabrze');
  const block = html.slice(i, i + 2500);
  assert.match(block, /Fenerbahce/, 'Auswärts-Runner gelistet');
  assert.match(block, /72%/, 'dominanter Auswärts-Anteil (6747/9408 = 72%)');
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

test('Frisches Geld: €-Zufluss + % Surge aus mkv-History-Delta', () => {
  const { w } = boot();
  w._bfState.hist = {
    '1': [
      { ts: iso(-15 * 60e3), mkv: { 'Match Odds': 10000, 'First Half Goals 0.5': 1200 } },
      { ts: iso(0), mkv: { 'Match Odds': 15000, 'First Half Goals 0.5': 4800 } },  // +5K bzw. +300%
    ],
  };
  const html = w._renderBetfairRadar();
  assert.match(html, /Frisches Geld/);
  assert.match(html, /Größter €-Zufluss/);
  assert.match(html, /Stärkster Sprung/);
  assert.ok(html.includes('▲ +€5K'), '€-Zufluss Match Odds +€5K');
  assert.match(html, /HT Ü0\.5/);
  assert.ok(html.includes('+300%'), 'Surge +300%');
  assert.match(html, /🚨/, 'großer Sprung markiert');
});

test('Frisches Geld: ohne 2. Snapshot → ehrlicher „sammelt Daten"-Zustand', () => {
  const { w } = boot();
  w._bfState.hist = {};   // keine History → kein Delta
  const html = w._renderBetfairRadar();
  assert.match(html, /Frisches Geld/);
  assert.match(html, /sammelt Daten/);
});

test('View-Toggle Live-Radar / Trefferquoten vorhanden', () => {
  const { html } = render();
  assert.match(html, /🔴 Live-Radar/);
  assert.match(html, /📊 Trefferquoten/);
});

test('Trefferquoten-Board leer → ehrlicher „sammelt Daten"-Zustand', () => {
  const { w } = boot();
  w._bfState.view = 'record';
  w._bfState.track = { n: 0, byLeagueMarket: {} };
  const html = w._renderBetfairRadar();
  assert.match(html, /Sammelt Daten/);
  assert.ok(!/<table/.test(html), 'keine Tabelle ohne Daten');
});

test('Trefferquoten-Board mit Daten: Liga×Markt + Trefferquote + ROI', () => {
  const { w } = boot();
  w._bfState.view = 'record';
  w._bfState.track = {
    generatedAt: iso(0), n: 48,
    byLeagueMarket: {
      'Ecuador Serie A|Half Time': {
        n: 40, wins: 27, hitRate: 0.68, roi: 0.14,
        nConc: 25, hitRateConc: 0.72, roiConc: 0.2, nInflow: 12, hitRateInflow: 0.75, roiInflow: 0.3,
      },
    },
  };
  const html = w._renderBetfairRadar();
  assert.match(html, /<table/);
  assert.match(html, /Ecuador Serie A/);
  assert.match(html, /HT 1X2/);         // Half Time → Label
  assert.match(html, /68%/);            // Trefferquote
  assert.match(html, /\+14%/);          // ROI
  assert.match(html, /72%/);            // Konzentrations-Trefferquote
});

test('Confidence-Badge am Markt in der Liste, wenn Track-Record belastbar', () => {
  const { w } = boot();
  w._bfState.track = {
    n: 30, byLeagueMarket: {
      'UEFA Champions League Qualifiers|Match Odds': {
        n: 30, wins: 18, hitRate: 0.6, roi: 0.1, nConc: 20, hitRateConc: 0.65, roiConc: 0.12, nInflow: 0, hitRateInflow: null, roiInflow: null,
      },
    },
  };
  const html = w._renderBetfairRadar();   // Live-View: Kairat (UEFA, Match Odds) trägt das Badge
  assert.match(html, /🎯/);
  assert.match(html, /🎯 60% · \+10%/);
});


test('_bfRefresh lädt frische Daten nach & behält offene Cards/Filter (Fix „Daten 2h alt")', async () => {
  // Regressions-Guard: der Radar lud früher NUR einmal (_bfLoad-Guard) und pollte nie nach →
  // im offenen Tab wuchs das Daten-Alter unbegrenzt und der Stale-Banner feuerte trotz frischem
  // Server. _bfRefresh muss data/hist/track ersetzen, ohne View/Filter/aufgeklappte Cards zu resetten.
  const dom = new JSDOM('<!DOCTYPE html><body><div id="betfairRadarPanel"></div></body>',
    { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w._bfNoAutoRefresh = true;   // Auto-Refresh-Timer in Tests aus (sonst hängt die Event-Loop)
  w.eval(readFileSync(new URL('betfair-radar.js', ROOT), 'utf8'));

  const oldData = fixture(); oldData._meta.generatedAt = iso(-2 * 3600e3);   // 2h alter Erststand
  w._bfState.data = oldData; w._bfState.hist = histFixture(); w._bfState.loading = false;
  w._bfState.league = 'all'; w._bfState.tab = 'all'; w._bfState.date = 'all';
  w._bfState.cardOpen = { 1: true };                                         // Nutzer hat Karte offen

  const fresh = fixture(); fresh._meta.generatedAt = iso(0);                  // Server liefert frisch
  w.fetch = (u) => Promise.resolve({ ok: true, json: () => Promise.resolve(
    String(u).indexOf('betfair_prices') >= 0 ? fresh :
    String(u).indexOf('betfair_history') >= 0 ? histFixture() : null) });

  await w._bfRefresh();
  assert.equal(w._bfState.data._meta.generatedAt, fresh._meta.generatedAt, 'Daten wurden ersetzt');
  assert.notEqual(w._bfState.data._meta.generatedAt, oldData._meta.generatedAt, 'nicht mehr der alte Stand');
  assert.equal(w._bfState.cardOpen[1], true, 'offene Karte bleibt offen');
  assert.equal(w._bfState.league, 'all', 'Filter bleibt erhalten');
});

test('_bfRefresh no-op wenn Panel unsichtbar (kein unnötiger Fetch)', async () => {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="betfairRadarPanel" style="display:none"></div></body>',
    { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w._bfNoAutoRefresh = true;   // Auto-Refresh-Timer in Tests aus (sonst hängt die Event-Loop)
  w.eval(readFileSync(new URL('betfair-radar.js', ROOT), 'utf8'));
  w._bfState.data = fixture(); w._bfState.loading = false;
  let fetched = false;
  w.fetch = () => { fetched = true; return Promise.resolve({ ok: true, json: () => Promise.resolve(null) }); };
  const r = w._bfRefresh();
  if (r && r.then) await r;
  assert.equal(fetched, false, 'kein Fetch, wenn Radar-Panel ausgeblendet');
});
