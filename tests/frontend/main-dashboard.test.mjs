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
function seed(w) {
  w._mdState.data = {
    liga: { groups: { g: { fixtures: [
      { home: 'Bayern', away: 'Dortmund', league: 'Bundesliga', picks: [
        { market: 'Heimsieg', verdict: 'BET', convictionScore: 8, edgePP: 5, odds: 1.8, source: 'steam', steamMovePP: 4.2 } ] } ] } } },
    mls: null,
    ligaStreaks: { streaks: [ { team: 'Bournemouth', market: 'Ungeschlagen', length: 15, continuation: { state: 'intakt', ratePct: 100 }, leagueName: 'Premier League' } ] },
    mlsStreaks: null,
    betfair: { matches: [ { home: 'Kairat', away: 'Omonia', markets: { 'Match Odds': { runners: [
      { name: 'Kairat', odd: 1.5, vol: 12000 }, { name: 'Omonia', odd: 3.0, vol: 1000 } ] } } } ] },
    whales: { m1: { league: 'NBA', totalUsd: 12000, hoursToKickoff: 3, whales: [ { wallet: '0x', side: 'Lakers', usd: 12000 } ] } },  // >= $10K-Whale-Schwelle
  };
}

test('Dashboard rendert alle Kacheln + Triple-Hero', () => {
  const w = load(); seed(w);
  w._renderMainDash();
  const html = w.document.getElementById('mainDashPanel').innerHTML;
  assert.match(html, /Übersicht/);
  assert.match(html, /Triple-Konsens/);
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


test('Triple-Hero zeigt Konsens (einig) und Divergenz (Ausreißer)', () => {
  const w = load();
  w._mdState.data = {
    liga: { groups: { g: { fixtures: [
      { home:'Bayern', away:'Dortmund', league:'Bundesliga', picks:[
        { market:'Heimsieg', verdict:'BET', consensus:{ side:'home', n:4, spreadPP:3.0, medianPP:58, kind:'konsens',
          sources:{pinnacle:0.58,betfair:0.585,poly:0.60,soft:0.575}, outlier:null, outlierGapPP:2.0 } } ] },
      { home:'Leipzig', away:'Koeln', league:'Bundesliga', picks:[
        { market:'Auswärtssieg', verdict:'ABWÄGEN', consensus:{ side:'away', n:4, spreadPP:14, medianPP:40, kind:'divergenz',
          sources:{pinnacle:0.40,betfair:0.41,poly:0.28,soft:0.42}, outlier:'poly', outlierGapPP:12 } } ] } ] } } },
    mls:null, ligaStreaks:null, mlsStreaks:null, betfair:null, whales:null,
  };
  w._renderMainDash();
  const html = w.document.getElementById('mainDashPanel').innerHTML;
  assert.match(html, /Triple-Konsens/);
  assert.match(html, /Einig/);           assert.match(html, /4\/4 einig/);   assert.match(html, /Bayern/);
  assert.match(html, /Ausreißer/);       assert.match(html, /Poly schert aus/); assert.match(html, /Leipzig/);
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
    scores: { '0xSHARP': { n: 10, clvSumPP: 20, wins: 7, usd: 40000, pnl: 150000 } },
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
  assert.match(html, /sendet nicht/);        // Vorschau-Hinweis je Kachel
  assert.match(html, /Top-Play/);            // eigene Kachel (Reihe 4)
  assert.match(html, /Volumen über Norm/);         // eigene Kachel (Reihe 4)
  assert.match(html, /Atlanta Braves/, 'Top-Play-Kandidat sichtbar');
});
