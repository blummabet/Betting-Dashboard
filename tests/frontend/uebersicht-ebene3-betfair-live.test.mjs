// tests/frontend/uebersicht-ebene3-betfair-live.test.mjs — 27.09.2026
//
// Lucas: „laufende Betfair-Spiele aus Ebene 3 … können drin bleiben, es muss halt ein
// Live-Badge haben." Vorher: der Steam-Block setzte gar kein `live`, der Geld-Block nur den
// Feed-Status. Ein Betfair-Spiel mit Anpfiff vor 10 Minuten stand als „⏱ 0m" — sah aus wie
// „gleich", war aber schon am Laufen.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const MOD = new URL('../../main-dashboard.js', import.meta.url);

function load() {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="mainDashPanel"></div></body>',
    { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve(null) });
  w.eval(readFileSync(MOD, 'utf8'));
  return w;
}
const iso = (minVonJetzt) => new Date(Date.now() + minVonJetzt * 60000).toISOString();
const steam = (min) => ({ matchId: 'm1', home: 'Lorenskog', away: 'Skeid', league: 'Norway 2',
  kickoff: iso(min), pp: 11.1, odd: 2.72, sideName: 'Skeid' });
const flow = (min) => ({ matchId: 'm2', home: 'Casertana', away: 'Catania', league: 'Serie C',
  kickoff: iso(min), deltaEur: 9000, nowEur: 20000, odd: 2.1, sideName: 'Catania', dir: 'in',
  market: 'Match Odds' });

function ebene3(w, bf) {
  w._mdState.data = { killer: {}, bfOverview: bf };
  return w._mdJetztTest([]);
}

test('Steam-Zeile nach Anpfiff trägt das Live-Badge', () => {
  const html = ebene3(load(), { steam: [steam(-10)], flow: [] });
  assert.match(html, /Lorenskog/);
  assert.match(html, /● LIVE/, 'laufendes Betfair-Spiel ohne Live-Badge');
  assert.doesNotMatch(html, /⏱ 0m/, '„0m" behauptet, das Spiel beginne gleich');
});

test('Geld-Zeile nach Anpfiff trägt das Live-Badge, auch ohne Feed-Status', () => {
  const html = ebene3(load(), { steam: [], flow: [flow(-5)] });
  assert.match(html, /Casertana/);
  assert.match(html, /● LIVE/);
});

test('Gegenbeweis: vor Anpfiff kein Live-Badge', () => {
  const html = ebene3(load(), { steam: [steam(45)], flow: [flow(90)] });
  assert.match(html, /Lorenskog/);
  assert.doesNotMatch(html, /● LIVE/);
});
