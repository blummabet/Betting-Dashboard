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
  // Rendering-Tests gegen stabile Schwellen pinnen (produktive Betfair-Schwellen sind Config):
  if (w._bfTHR) { w._bfTHR.top = { FT: 10000, HT: 5000 }; w._bfTHR.intl = { FT: 3000, HT: 1000 }; w._bfTHR.rest = { FT: 5000, HT: 1500 }; }
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
  assert.match(html, /Größte Zuflüsse/);
  assert.match(html, /Größte Sprünge/);
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

test('Trefferquoten: Umschalter „nach Team" zeigt Team×Markt', () => {
  const { w } = boot();
  w._bfState.view = 'record';
  w._bfState.track = {
    generatedAt: iso(0), n: 48,
    byLeagueMarket: { 'Ecuador Serie A|Match Odds': { n: 40, wins: 27, hitRate: 0.68, roi: 0.14, nConc: 25, hitRateConc: 0.72, roiConc: 0.2, nInflow: 0, hitRateInflow: null, roiInflow: null } },
    byTeamMarket: { 'LDU Quito|Match Odds': { n: 22, wins: 15, hitRate: 0.68, roi: 0.12, nConc: 14, hitRateConc: 0.71, roiConc: 0.18, nInflow: 0, hitRateInflow: null, roiInflow: null } },
  };
  let html = w._renderBetfairRadar();
  assert.match(html, /nach Liga/); assert.match(html, /nach Team/);
  assert.match(html, /Ecuador Serie A/); assert.doesNotMatch(html, /LDU Quito/);
  w._bfSetTrackBy('team');
  html = w.document.getElementById('betfairRadarPanel').innerHTML;
  assert.match(html, /Team×Markt/); assert.match(html, /LDU Quito/);
  assert.doesNotMatch(html, /Ecuador Serie A/);
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


test('Markt-Filter: nur Spiele mit Geld auf dem gewählten Markt', () => {
  const { w } = boot();
  w._bfState.market = 'Match Odds';
  const html = w._renderBetfairRadar();
  assert.match(html, /Kairat Almaty/);                      // hat Match Odds
  assert.ok(!/Atletico Madrid/.test(html), 'Atletico (nur O/U 2.5) ohne Match Odds ausgefiltert');
});

test('Markt-Filter fokussiert die komprimierte Karte auf den gewählten Markt', () => {
  const { w } = boot();
  w._bfState.market = 'First Half Goals 0.5';               // sonst zeigt Kairat komprimiert 1X2 (Top-Geld)
  const html = w._renderBetfairRadar();
  const cardStart = html.indexOf('id="bfg-1"');            // die Karte selbst (nicht die Hotspot-Leiste oben)
  const seg = html.slice(cardStart, cardStart + 2600);
  assert.match(seg, /Kairat Almaty/);
  assert.match(seg, /HT Ü0\.5/, 'komprimierte Karte zeigt den gefilterten HT-Markt statt 1X2');
  assert.ok(!/1X2 → /.test(seg), 'komprimiert nicht mehr 1X2 (Top-Geld), sondern der gefilterte HT-Markt');
});

test('Markt-Dropdown listet nur Märkte mit Geld', () => {
  const { html } = render();
  assert.match(html, /Alle Märkte/);
  assert.match(html, /_bfSetMarket/);
});

test('Nur-Live-Filter: nur laufende Spiele', () => {
  const { w, prices } = boot();
  prices.matches.find(m => m.home === 'Kairat Almaty').liveInfo = { time: "55'" };  // live setzen
  w._bfState.onlyLive = true;
  const html = w._renderBetfairRadar();
  assert.match(html, /Kairat Almaty/);
  assert.ok(!/Gornik Zabrze/.test(html), 'nicht-live Spiel ausgefiltert');
});

test('Nur-Live-Toggle ist in der Leiste', () => {
  const { html } = render();
  assert.match(html, /Nur Live/);
  assert.match(html, /_bfToggleLive/);
});


/* ── Kohärenz-Engine (v5-Port) ─────────────────────────────────────────── */
function ouLadder(over, vol){                     // {n:pOver} → Ü/U-Märkte ohne Vig
  const mk={};
  for(const n in over){ const p=over[n];
    mk['Over/Under '+n+' Goals']={ vol:(vol||8000), runners:[
      { name:'Over '+n+' Goals',  odd:+(1/p).toFixed(3),     vol:(vol||8000)/2 },
      { name:'Under '+n+' Goals', odd:+(1/(1-p)).toFixed(3), vol:(vol||8000)/2 }]};
  }
  return mk;
}
function cohBoot(match){
  const dom = new JSDOM('<!DOCTYPE html><body><div id="betfairRadarPanel"></div></body>',{url:'https://x.com/',runScripts:'outside-only'});
  const w = dom.window; w._bfNoAutoRefresh = true;
  w.eval(readFileSync(new URL('betfair-radar.js', ROOT),'utf8'));
  w._bfState.data = { _meta:{ generatedAt: iso(0) }, matches:[match] };
  w._bfState.hist = {}; w._bfState._cohCache = {}; w._bfState._mixBase = null;
  return w;
}

test('fitLambda rekonstruiert λ aus einer sauberen Ü/U-Leiter', () => {
  const m = { matchId:99, home:'Alpha', away:'Beta', league:'Test', country:'International', kickoff:ko(9), liveInfo:{}, totalVol:60000,
    mo:{ hw:2.4, dr:3.4, aw:3.0, fair:{ home:0.40, draw:0.28, away:0.32 } },
    markets: ouLadder({0.5:0.9093, 1.5:0.6916, 2.5:0.4303, 3.5:0.2213}) };
  const w = cohBoot(m);
  const co = w._bfCoherence(m);
  assert.ok(co.fit, 'λ gefittet');
  assert.ok(co.fit.l >= 2.2 && co.fit.l <= 2.6, 'λ ≈ 2.4, war '+co.fit.l);
  assert.equal(co.checks.filter(c=>c.hard).length, 0, 'saubere Leiter → keine harten Widersprüche');
});

test('Kohärenz: harte Leiter-Monotonie-Verletzung wird erkannt', () => {
  const m = { matchId:99, home:'Alpha', away:'Beta', league:'Test', country:'International', kickoff:ko(9), liveInfo:{}, totalVol:60000,
    mo:{ hw:2.4, dr:3.4, aw:3.0, fair:{ home:0.40, draw:0.28, away:0.32 } },
    markets: ouLadder({0.5:0.60, 1.5:0.75, 2.5:0.40}) };   // Ü1.5 > Ü0.5 = unmöglich
  const co = cohBoot(m)._bfCoherence(m);
  const hard = co.checks.filter(c=>c.hard && c.k==='Leiter-Monotonie');
  assert.ok(hard.length >= 1, 'harte Monotonie-Verletzung gefunden');
});

test('Kohärenz: Draw-no-Bet-Widerspruch zu 1X2 (hart)', () => {
  const mk = ouLadder({0.5:0.9093, 1.5:0.6916, 2.5:0.4303, 3.5:0.2213});
  mk['Draw no Bet'] = { vol:6000, runners:[{ name:'Alpha', odd:2.5, vol:3000 }, { name:'Beta', odd:1.667, vol:3000 }] }; // DNB-Heim ≈ 40%
  const m = { matchId:99, home:'Alpha', away:'Beta', league:'Test', country:'International', kickoff:ko(9), liveInfo:{}, totalVol:60000,
    mo:{ hw:2.0, dr:3.6, aw:3.4, fair:{ home:0.50, draw:0.20, away:0.30 } },  // impliziert DNB-Heim 0.5/0.8=62.5%
    markets: mk };
  const co = cohBoot(m)._bfCoherence(m);
  const dnb = co.checks.filter(c=>c.k==='Draw no Bet');
  assert.ok(dnb.length===1 && dnb[0].hard, 'DNB-Widerspruch als hart erkannt');
  assert.ok(Math.abs(dnb[0].dev) > 15, 'große Abweichung, war '+dnb[0].dev);
});

test('cohFlow klassifiziert steam / absorb / air', () => {
  const base = { matchId:99, home:'Alpha', away:'Beta', league:'Test', country:'International', kickoff:ko(9), liveInfo:{}, totalVol:2000, markets:{} };
  const w = cohBoot(base);
  const t0=iso(-2*3600e3), t1=iso(0);
  w._bfState.hist = { '99':[ {ts:t0,totalVol:1000,mo:{hw:2.0,dr:3.5,aw:4.0}}, {ts:t1,totalVol:1500,mo:{hw:1.6,dr:3.5,aw:4.0}} ] };
  assert.equal(w._bfCohFlow(base).kind, 'steam', 'Preis+Geld = steam');
  w._bfState.hist = { '99':[ {ts:t0,totalVol:1000,mo:{hw:2.00,dr:3.5,aw:4.0}}, {ts:t1,totalVol:1700,mo:{hw:1.99,dr:3.5,aw:4.0}} ] };
  assert.equal(w._bfCohFlow(base).kind, 'absorb', 'Geld ohne Preis = absorb');
  w._bfState.hist = { '99':[ {ts:t0,totalVol:1000,mo:{hw:2.0,dr:3.5,aw:4.0}}, {ts:t1,totalVol:1050,mo:{hw:1.6,dr:3.5,aw:4.0}} ] };
  assert.equal(w._bfCohFlow(base).kind, 'air', 'Preis ohne Geld = air');
});

test('Drawer öffnet, zeigt Kohärenz-Sektionen und schließt wieder', () => {
  const m = { matchId:77, home:'Alpha', away:'Beta', league:'Test', country:'International', kickoff:ko(9), liveInfo:{}, totalVol:60000,
    mo:{ hw:2.4, dr:3.4, aw:3.0, fair:{ home:0.40, draw:0.28, away:0.32 } },
    markets: ouLadder({0.5:0.9093, 1.5:0.6916, 2.5:0.4303, 3.5:0.2213}) };
  const w = cohBoot(m);
  w._bfDrawer(77);
  const dr = w.document.getElementById('bfdDrawer');
  assert.ok(dr && dr.classList.contains('on'), 'Drawer offen');
  const html = w.document.getElementById('bfdIn').innerHTML;
  assert.match(html, /Konsens-Kurve/);
  assert.match(html, /Kohärenz-Prüfung/);
  assert.match(html, /Geld je Markt/);
  w._bfCloseDrawer();
  assert.ok(!dr.classList.contains('on'), 'Drawer geschlossen');
});

test('Card zeigt den Kohärenz-Deep-Dive-Button', () => {
  const { html } = render();
  assert.match(html, /Kohärenz-Deep-Dive/);
  assert.match(html, /_bfDrawer\(/);
});


/* ── Robuster Live-Status (Fix „war live, dann wieder pre") ─────────────────── */
function liveMatch(id, kickoffH, liveInfo){
  return { matchId:id, home:'Leverkusen', away:'Genk', league:'Friendly Matches', country:'International',
    kickoff:ko(kickoffH), liveInfo:liveInfo||{}, totalVol:160000,
    markets:{ 'Match Odds': { vol:39000, runners:[
      { name:'Leverkusen', odd:1.5, vol:32800 }, { name:'The Draw', odd:4.0, vol:3200 }, { name:'Genk', odd:6.0, vol:3000 }] } } };
}

test('Live: Anpfiff vorbei ohne Betwatch-Uhr zählt trotzdem als live', () => {
  const { w } = boot();
  assert.equal(w._bfIsLive(liveMatch(501, -0.5, {})), true, 'angepfiffen + kein finished → live');
});

test('Live: beendet gewinnt immer', () => {
  const { w } = boot();
  assert.equal(w._bfIsLive(liveMatch(502, -0.5, { finished: true, time: "80'" })), false);
});

test('Live: lange nach Anpfiff (> 2,5h) → nicht mehr live', () => {
  const { w } = boot();
  assert.equal(w._bfIsLive(liveMatch(503, -5, {})), false);
});

test('Live: längst beendetes Spiel (Anpfiff > 2,5h her) ist NICHT live — auch mit Rest-Uhr', () => {
  const { w } = boot();
  // Betwatch sendet noch eine Uhr (90'), aber Anpfiff war vor 3h → harter Cut, nicht live
  assert.equal(w._bfIsLive(liveMatch(504, -3, { time: 90 })), false);
});

test('Live: Betwatch-Uhr vorhanden → live (auch wenn Anpfiff-Zeit noch Zukunft behauptet)', () => {
  const { w } = boot();
  assert.equal(w._bfIsLive(liveMatch(505, 1, { time: "12'" })), true);
});

test('Live-Pill rendert sauber „LIVE" (kein null, keine Minute)', () => {
  const { w, prices } = boot();
  prices.matches[0].kickoff = ko(-0.5); prices.matches[0].liveInfo = {};   // angepfiffen, keine Uhr
  const html = w._renderBetfairRadar();
  assert.match(html, /LIVE/);
  assert.doesNotMatch(html, /LIVE\s*null/);
  assert.doesNotMatch(html, /null'/);
});


test('Card-Kopf zeigt den größten Markt, nicht die Summe aller Märkte', () => {
  const { w } = boot();
  const html = w._renderBetfairRadar();
  assert.match(html, /größter Markt/, 'Label „größter Markt" statt „gematchtes Geld"');
  const i = html.indexOf('id="bfg-1"'); const seg = html.slice(i, i + 2600);   // Kairat-Card
  assert.match(seg, /€17\.5K/, 'Kopf = Match Odds (größter Markt)');
  assert.doesNotMatch(seg, /€19\.6K/, 'NICHT die Summe aller Märkte');
});


test('Card-Kopf folgt dem Markt-Filter (gefilterter Markt statt größtem)', () => {
  const { w } = boot();
  w._bfState.market = 'First Half Goals 0.5';   // Kairat: HT Ü0.5 €2.1K statt Match Odds €17.5K
  const html = w._renderBetfairRadar();
  const i = html.indexOf('id="bfg-1"'); const seg = html.slice(i, i + 2600);
  assert.match(seg, /€2\.1K/, 'Kopf = gefilterter Markt (HT Ü0.5)');
  assert.doesNotMatch(seg, /€17\.5K/, 'nicht mehr der größte Markt (Match Odds)');
  assert.match(seg, /HT Ü0\.5/, 'Label = gefilterter Markt');
});


test('Steam-pp ist implied-prob-basiert & begrenzt (kein 16279pp bei Live-Drift)', () => {
  const { w } = boot();
  // Favorit driftet live raus (hw 1.01 → 165), Gegenseite kommt rein (aw 30 → 1.05)
  w._bfState.hist = { '601': [ { mo: { hw: 1.01, dr: 20, aw: 30 } }, { mo: { hw: 165, dr: 5, aw: 1.05 } } ] };
  const mv = w._bfMoveOf({ matchId: 601 });
  assert.ok(mv, 'Move erkannt');
  assert.ok(Math.abs(mv.pp) <= 100, 'pp begrenzt (implied-prob), war ' + mv.pp);
  assert.ok(Math.abs(mv.pp) > 50, 'großer, aber realistischer Move');
});


test('×-Norm: überverhältnismäßig viel Geld wird erkannt & markiert (Stage-Median)', () => {
  const { w } = boot();
  const mk = (v) => ({ 'Match Odds': { runners: [ { name: 'H', vol: v * 0.6, odd: 2.0 }, { name: 'A', vol: v * 0.4, odd: 2.2 } ] } });
  const mm = (id, v) => ({ matchId: id, home: 'H' + id, away: 'A' + id, league: 'Testliga', country: 'AT', kickoff: '2031-01-01T20:00:00Z', liveInfo: {}, markets: mk(v) });
  // 5 normale (~10K) + 1 großes (40K) Spiel, alle weit vor Anpfiff (Stage p0)
  w._bfState.data = { matches: [ mm(1, 10000), mm(2, 10000), mm(3, 10000), mm(4, 10000), mm(5, 10000), mm(6, 40000) ] };
  w._bfState._normBase = null; w._bfState._cohCache = {};
  assert.strictEqual(w._bfStageOf(w._bfState.data.matches[0]), 'p0', 'weit vor Anpfiff = p0');
  const rBig = w._bfNormRatio(w._bfState.data.matches[5]);
  const rNorm = w._bfNormRatio(w._bfState.data.matches[0]);
  assert.ok(rBig >= 3.5 && rBig <= 4.5, 'großes Spiel ~4× Median, war ' + rBig);
  assert.ok(rNorm >= 0.9 && rNorm <= 1.1, 'normales Spiel ~1× Median, war ' + rNorm);
  const html = w._renderBetfairRadar();
  assert.match(html, /bfb-norm/, '×-Norm-Badge wird gerendert');
  assert.match(html, /bfb-over2/, 'starkes Über-Norm-Spiel rot umrandet');
});

test('×-Norm: zu wenige Vergleichsspiele → kein Ratio (Median instabil)', () => {
  const { w } = boot();
  const mk = (v) => ({ 'Match Odds': { runners: [ { name: 'H', vol: v, odd: 2.0 } ] } });
  const mm = (id, v) => ({ matchId: id, home: 'H' + id, away: 'A' + id, league: 'L', country: 'AT', kickoff: '2031-01-01T20:00:00Z', liveInfo: {}, markets: mk(v) });
  w._bfState.data = { matches: [ mm(1, 10000), mm(2, 90000) ] };   // nur 2 Spiele in der Stage
  w._bfState._normBase = null; w._bfState._cohCache = {};
  assert.strictEqual(w._bfNormRatio(w._bfState.data.matches[1]), null, 'unter NORM_MIN_PEERS → null');
});
