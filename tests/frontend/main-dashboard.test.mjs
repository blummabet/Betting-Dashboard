// tests/frontend/main-dashboard.test.mjs — MAIN-Dashboard „Übersicht" (29.07.2026)
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const MOD = new URL('../../main-dashboard.js', import.meta.url);
function load() {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="mainDashPanel"></div></body>', { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve(null) });
  w.eval(readFileSync(MOD, 'utf8'));
  return w;
}
// 30.08.2026: die Fixtures brauchen jetzt einen Anpfiff. Vorher zeigten „Beste Cards" und
// „Pinnacle-Steam" auch Spiele, die seit Tagen gespielt waren (FC Cincinnati: 179 Stunden her);
// die Filter sind fail-closed — ohne Zeitangabe wird nicht geraten.
function seed(w) {
  w._mdState.data = {
    liga: { groups: { g: { fixtures: [
      { home: 'Bayern', away: 'Dortmund', league: 'Bundesliga', kickoff: new Date(Date.now() + 4 * 3600e3).toISOString(), picks: [
        { market: 'Heimsieg', verdict: 'BET', convictionScore: 8, edgePP: 5, odds: 1.8, source: 'steam', steamMovePP: 4.2 } ] } ] } } },
    mls: null,
    ligaStreaks: { streaks: [ { team: 'Bournemouth', market: 'Ungeschlagen', length: 15, continuation: { state: 'intakt', ratePct: 100 }, leagueName: 'Premier League' } ] },
    mlsStreaks: null,
    betfair: { matches: [ { home: 'Kairat', away: 'Omonia', markets: { 'Match Odds': { runners: [
      { name: 'Kairat', odd: 1.5, vol: 12000 }, { name: 'Omonia', odd: 3.0, vol: 1000 } ] } } } ] },
    whales: { m1: { league: 'NBA', totalUsd: 12000, hoursToKickoff: 3, whales: [ { wallet: '0x', side: 'Lakers', usd: 12000 } ] } },  // >= $10K-Whale-Schwelle
  };
}

test('Dashboard rendert alle Kacheln', () => {
  const w = load(); seed(w);
  w._renderMainDash();
  const html = w.document.getElementById('mainDashPanel').innerHTML;
  assert.match(html, /Übersicht/);
  assert.match(html, /Beste Cards/);   assert.match(html, /Bayern/);
  assert.match(html, /Beste Streaks/); assert.match(html, /Bournemouth/);
  assert.match(html, /Betfair-Kohle/); assert.match(html, /Kairat/);
  assert.match(html, /Poly Whale-Bets/); assert.match(html, /Lakers/);
  assert.match(html, /Pinnacle-Steam/);   // umbenannt von Sharp-Radar   assert.match(html, /\+4\.2pp/);
});

test('Kachel-Überschriften führen per showView in den vollen Bereich', () => {
  const w = load(); seed(w);
  w._renderMainDash();
  const html = w.document.getElementById('mainDashPanel').innerHTML;
  assert.match(html, /showView\('national-cards'\)/);
  assert.match(html, /showView\('betfair'\)/);
  assert.match(html, /showView\('polywallets'\)/);
  assert.match(html, /showView\('sharp'\)/);
});

test('leere Daten → freundliche Leer-Hinweise, kein Crash', () => {
  const w = load();
  w._mdState.data = { liga: null, mls: null, ligaStreaks: null, mlsStreaks: null, betfair: null, whales: null };
  w._renderMainDash();
  const html = w.document.getElementById('mainDashPanel').innerHTML;
  assert.match(html, /Beste Cards/);
  assert.match(html, /Keine|nichts|Kein/i);
});


// 30.08.2026 (Lucas: „was aber dann mit dem tripple konsens? ist das nicht teils redundant?"):
// Der Hero ist raus. Der Test dreht sich mit um: er hielt fest, DASS das Panel rendert — jetzt
// hält er fest, dass es nicht wiederkommt. Begründung im Kopf von main-dashboard.js: die Spalte
// „Einig" sortierte nach der kleinsten Spanne und wählte damit die Spiele mit fertigem Preis;
// 91 von 139 Zeilen waren NOBET; und der Ausreißer war praktisch immer „Soft", was steam_lag
// in den Cards schon abdeckt. Die Auswahl nach GELD statt nach Preis macht „Mehrfach gedeckt".
test('der Triple-Konsens-Hero ist entfernt und kommt nicht durch die Hintertür zurück', () => {
  const w = load();
  w._mdState.data = {
    liga: { groups: { g: { fixtures: [
      { home:'Bayern', away:'Dortmund', league:'Bundesliga', kickoff: new Date(Date.now() + 4 * 3600e3).toISOString(), picks:[
        { market:'Heimsieg', verdict:'BET', consensus:{ side:'home', n:4, spreadPP:3.0, medianPP:58, kind:'konsens',
          sources:{pinnacle:0.58,betfair:0.585,poly:0.60,soft:0.575}, outlier:null, outlierGapPP:2.0 } } ] } ] } } },
    mls:null, ligaStreaks:null, mlsStreaks:null, betfair:null, whales:null,
  };
  w._renderMainDash();
  const html = w.document.getElementById('mainDashPanel').innerHTML;
  assert.doesNotMatch(html, /Triple-Konsens/);
  assert.doesNotMatch(html, /md-agree|md-arow|md-hero/, 'auch das Markup muss weg sein');
  assert.doesNotMatch(html, /4\/4 einig|schert aus/);
  // Die Card selbst bleibt sichtbar — entfernt wurde die Konsens-Anzeige, nicht der Pick.
  assert.match(html, /Bayern/);
});


// 01.08.2026 (Lucas): Public-Kandidaten-Vorschau-Boxen in der Übersicht — laden poly-wallets.js
// in dasselbe Window, damit _pwPublicTopPlays / _pwWhalePublicCandidates da sind. Sendet nichts.
const PWMOD = new URL('../../poly-wallets.js', import.meta.url);
function loadBoth(files) {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="mainDashPanel"></div></body>', { url: 'https://x.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window;
  w.fetch = (url) => { const u = String(url); let b = null;
    for (const [f, d] of Object.entries(files)) if (u.includes(f)) { b = d; break; }
    return Promise.resolve({ ok: b != null, json: () => Promise.resolve(b) }); };
  w.eval(readFileSync(PWMOD, 'utf8'));   // poly-Globals zuerst
  w.eval(readFileSync(MOD, 'utf8'));     // dann Übersicht
  return w;
}
const iso = new Date().toISOString();
const PREV_FILES = {
  'poly_money_broad_close.json': {
    'mlb-braves-padres': { league: 'MLB', resolved: null, totalUsd: 100000, hoursToKickoff: 3, capturedAt: iso,
      shares: { 'Atlanta Braves': 65000, 'San Diego Padres': 35000 }, prices: { 'Atlanta Braves': 0.62, 'San Diego Padres': 0.38 } },
    'nba-lakers-celtics': { league: 'NBA', resolved: null, totalUsd: 100000, hoursToKickoff: 3, capturedAt: iso,
      shares: { 'Lakers': 55000, 'Celtics': 45000 }, prices: { 'Lakers': 0.55, 'Celtics': 0.45 } },
  },
  'poly_money_broad_history.json': {},
  'poly_money_broad.json': { n: 100, byLeague: [] },
  'poly_wallet_track.json': { updatedAt: iso,
    // 29.08.2026 (Wallet-Neugewichtung): n10 traegt seit heute bewusst keinen Public-Kandidaten mehr
    // (Konfidenzfaktor 0,5). Diese Box prueft das Rendern, nicht die Stichprobe -> belegte Wallet.
    scores: { '0xSHARP': { n: 60, clvSumPP: 120, wins: 42, usd: 40000, pnl: 150000 } },
    open: [
      { wallet: '0xSHARP', key: 'mlb-braves-padres', side: 'Atlanta Braves', league: 'MLB', usd: 40000, entryPrice: 0.55, lastPrice: 0.62 },
      { wallet: '0xWHALE', key: 'nba-lakers-celtics', side: 'Lakers', league: 'NBA', usd: 120000, entryPrice: 0.50, lastPrice: 0.55 },
    ] },
  'poly_cross_sport.json': { discrepancies: [] },
};

test('Übersicht: Public-Kandidaten-Vorschau-Boxen rendern (sendet nicht)', async () => {
  const w = loadBoth(PREV_FILES);
  w._mdState.data = { liga: null, mls: null, ligaStreaks: null, mlsStreaks: null, betfair: null, whales: null };
  await new Promise((res) => w._pwEnsurePlaysData(res));   // lexischen Cache vorfüllen → Box-Fill ist synchron
  w._renderMainDash();
  await new Promise(r => setTimeout(r, 40));
  const html = w.document.getElementById('mainDashPanel').innerHTML;
  // 07.09.2026: die Kachel „🎯 Top-Play" ist weg. Sie war am 01.08. als Experiment angelegt
  // („🧪 Vorschau — sendet nicht · ein paar Tage beobachten") und rendert `_pwPublicTopPlays()`.
  // Seit dem 07.09. zieht „Heute spielenswert" aus derselben Funktion (gemessen: der vorherige,
  // ungefilterte Topf +0,1 % ROI über 570 Plays gegen +6,4 % über 167). Zwei Kacheln, ein
  // Inhalt — also eine weg. Der Kandidat muss deshalb JETZT oben stehen.
  // Auf die KACHEL prüfen, nicht auf den Namen: der KPI-Balken trägt weiterhin die Zeile
  // „Top-Plays offen", und ein /Top-Play/ über das ganze HTML würde die treffen. Genau die
  // Sorte Unschärfe, die heute schon dreimal einen Test hat anschlagen lassen, obwohl nichts
  // kaputt war.
  assert.doesNotMatch(html, /md-tile-t">Top-Play</, 'die doppelte Kachel ist raus');
  assert.match(html, /md-tile-t">Heute spielenswert</);
  assert.match(html, /md-tile-t">Volumen über Norm</);   // eigene Kachel, unverändert
});
