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
    whales: { m1: { league: 'NBA', totalUsd: 8000, hoursToKickoff: 3, whales: [ { wallet: '0x', side: 'Lakers', usd: 8000 } ] } },
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
  assert.match(html, /Sharp-Radar/);   assert.match(html, /\+4\.2pp/);
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
