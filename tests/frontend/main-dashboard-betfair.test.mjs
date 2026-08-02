// tests/frontend/main-dashboard-betfair.test.mjs — 02.08.2026 (Lucas): drei neue Betfair-Kacheln
// in der Übersicht (erster Menüpunkt). Steam + Frisches Geld aus dem Sidecar, Fehlbepreisung
// client-seitig über die Radar-Engine (window._bfCoherence). Reiner Render-Test (jsdom).
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

function seed(w, extra) {
  w._mdState.data = Object.assign({
    liga: null, mls: null, ligaStreaks: null, mlsStreaks: null,
    betfair: { matches: [
      { matchId: 1, home: 'Genk', away: 'Twente', country: 'BE', league: 'Jupiler',
        markets: { 'Match Odds': { runners: [{ name: 'Genk', odd: 2.4, vol: 9000 }, { name: 'Twente', odd: 3.0, vol: 1000 }] } } },
      { matchId: 2, home: 'Ruhig', away: 'Spiel', country: 'DE', league: 'X',
        markets: { 'Match Odds': { runners: [{ name: 'Ruhig', odd: 2.0, vol: 500 }, { name: 'Spiel', odd: 2.0, vol: 500 }] } } },
    ] },
    whales: null,
    bfOverview: {
      generatedAt: new Date().toISOString(),
      steam: [{ matchId: 1, home: 'Genk', away: 'Twente', country: 'BE', league: 'Jupiler', side: 'hw', sideName: 'Genk', pp: -8.8, odd: 2.4 }],
      flow: [{ matchId: 3, home: 'Brondby', away: 'Viborg', country: 'DK', league: 'Superliga', deltaEur: 61989, nowEur: 161989, market: 'Match Odds', sideName: 'Brondby', odd: 2.2 }],
    },
  }, extra || {});
}

test('Steam- und Frisches-Geld-Kachel rendern aus dem Sidecar', () => {
  const w = load(); seed(w);
  w._renderMainDash();
  const h = w.document.getElementById('mainDashPanel').innerHTML;
  assert.match(h, /Betfair-Steam/); assert.match(h, /Genk/); assert.match(h, /-8\.8pp/); assert.match(h, /Quote steigt/);
  assert.match(h, /Frisches Geld/); assert.match(h, /Brondby/); assert.match(h, /€61\.?9?K|€62K/);
});

test('Fehlbepreisung ohne Radar-Engine → freundlicher Ladehinweis, kein Crash', () => {
  const w = load(); seed(w);
  w._renderMainDash();
  const h = w.document.getElementById('mainDashPanel').innerHTML;
  assert.match(h, /Größte Fehlbepreisung/);
  assert.match(h, /Radar-Engine lädt/);
});

test('Fehlbepreisung mit (gestubbter) Radar-Engine → ⚠ N + Spiel, nur vor Anpfiff', () => {
  const w = load(); seed(w);
  w._bfIsLive = () => false;
  w._bfCoherence = (m) => m.home === 'Genk'
    ? { checks: [{ k: 'Draw no Bet', mkt: 'DNB Genk', dev: 6.0, hard: true, w: 1 },
                 { k: 'BTTS', mkt: 'Beide treffen', dev: 3.2, hard: true, w: 1 }] }
    : { checks: [] };
  w._renderMainDash();
  const h = w.document.getElementById('mainDashPanel').innerHTML;
  assert.match(h, /Größte Fehlbepreisung/);
  assert.match(h, /md-wdot/, 'Warn-Flag-Form (Symbol + Zähler)');   // ⚠ im Symbol, Zahl separat
  assert.match(h, /Draw no Bet/, 'stärkste Abweichung zuerst');
  assert.match(h, /Genk/);
});

test('leerer Sidecar → freundliche „sammelt"-Hinweise, kein Crash', () => {
  const w = load(); seed(w, { bfOverview: { steam: [], flow: [] } });
  w._renderMainDash();
  const h = w.document.getElementById('mainDashPanel').innerHTML;
  assert.match(h, /Betfair-Steam/); assert.match(h, /Frisches Geld/);
  assert.match(h, /sammelt/i);
});

test('Betfair HT: Halbzeit-Markt-Geld (HT O/U) wird als eigene Kachel gezeigt', () => {
  const w = load();
  w._mdState.data = {
    liga: null, mls: null, ligaStreaks: null, mlsStreaks: null, whales: null, bfOverview: { steam: [], flow: [] },
    betfair: { matches: [
      { matchId: 5, home: 'Sturm', away: 'Rapid', country: 'AT', league: 'Bundesliga',
        markets: { 'First Half Goals 0.5': { runners: [
          { name: 'Under 0.5 Goals', odd: 3.6, vol: 8000 }, { name: 'Over 0.5 Goals', odd: 1.3, vol: 2000 } ] } } },
    ] },
  };
  w._renderMainDash();
  const h = w.document.getElementById('mainDashPanel').innerHTML;
  assert.match(h, /Betfair HT/, 'eigene HT-Kachel');
  assert.match(h, /HT O\/U 0\.5/, 'HT-Markt-Label');
  assert.match(h, /Sturm/);
});

test('Betfair HT: unter der HT-Schwelle (< 1K) -> freundlicher Leer-Hinweis', () => {
  const w = load();
  w._mdState.data = {
    liga: null, mls: null, ligaStreaks: null, mlsStreaks: null, whales: null, bfOverview: { steam: [], flow: [] },
    betfair: { matches: [
      { matchId: 6, home: 'Klein', away: 'Winzig', country: 'AT', league: 'X',
        markets: { 'First Half Goals 0.5': { runners: [
          { name: 'Under 0.5 Goals', odd: 3.6, vol: 400 }, { name: 'Over 0.5 Goals', odd: 1.3, vol: 200 } ] } } },
    ] },
  };
  w._renderMainDash();
  const h = w.document.getElementById('mainDashPanel').innerHTML;
  assert.match(h, /Betfair HT/);
  assert.match(h, /Kein nennenswertes HT-Geld/);
});
