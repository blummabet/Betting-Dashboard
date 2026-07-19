// tests/frontend/poly-frontend-visibility.test.mjs
// 19.07.2026 — Die Backend-Sachen im Frontend sichtbar machen (Lucas: „kann ich mir das anschauen?"):
//   (1) CLV-Spalte im Bayesian-Gewichte-Panel (Sharp Radar) — zeigt, welche Signale aus CLV lernen.
//   (2) Maker-Register im Trading-Cockpit — ruhende Limit-Orders + Eskalations-Hinweis.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const RENDERER = new URL('../../renderer.js', import.meta.url);
const POLYTAB  = new URL('../../polymarket-tab.js', import.meta.url);

function win(src) {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="mainContent"></div></body>',
    { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const { window: w } = dom;
  w.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  w.eval(readFileSync(src, 'utf8'));
  return w;
}

test('Bayesian-Panel: CLV-Spalte erscheint, wenn ein Signal aus CLV gelernt hat', () => {
  const w = win(RENDERER);
  w.LEAGUES = {};
  w._sharpSetDataset('liga');
  w.LIGA_SIGNAL_WEIGHTS = {
    lead_lag_bias: { weight: 1.2, n_observations: 12, n_clv: 6, wins_when_triggered: 7 },
    form_trend:    { weight: 1.0, n_observations: 12, n_clv: 0, wins_when_triggered: 6 },
  };
  const html = w._renderBayesianWeights();
  assert.match(html, />CLV</, 'CLV-Spaltenkopf fehlt');
  assert.match(html, /\+6/, 'CLV-Zähler des Sharp-Money-Signals fehlt');
  assert.match(html, /<b>CLV-Spalte:<\/b>/, 'Erklär-Fußnote fehlt');
});

test('Bayesian-Panel: ohne CLV-Daten keine Fußnote (aber Spalte bleibt konsistent)', () => {
  const w = win(RENDERER);
  w.LEAGUES = {};
  w._sharpSetDataset('liga');
  w.LIGA_SIGNAL_WEIGHTS = { form_trend: { weight: 1.0, n_observations: 5, n_clv: 0 } };
  const html = w._renderBayesianWeights();
  assert.doesNotMatch(html, /<b>CLV-Spalte:<\/b>/, 'Fußnote ohne CLV-Daten gezeigt');
});

test('Trading-Cockpit: Maker-Register erklärt sich im Leerzustand', () => {
  const w = win(POLYTAB);
  const html = w._ptRestingBlock([]);
  assert.match(html, /Maker-Orders/);
  assert.match(html, /maker_enabled/, 'Leerzustand erklärt den Maker-Modus nicht');
  assert.doesNotMatch(html, /<table/, 'leere Tabelle statt Erklärung');
});

test('Trading-Cockpit: ruhende Order wird gelistet, Eskalations-Fenster markiert', () => {
  const w = win(POLYTAB);
  const soon = new Date(Date.now() + 3600000).toISOString();   // 1h → im 1.5h-Fenster
  const later = new Date(Date.now() + 6 * 3600000).toISOString();
  const html = w._ptRestingBlock([
    { matchKey: 'LA-SEA', market: 'Heimsieg', price: 0.49, kickoff: soon, status: 'resting' },
    { matchKey: 'NY-ATL', market: 'Über 2.5', price: 0.55, kickoff: later, status: 'resting' },
  ]);
  assert.match(html, /LA-SEA/);
  assert.match(html, /49¢/);
  assert.match(html, /2 im Buch/);
  assert.match(html, /⚠️/, 'Order kurz vor Anpfiff muss markiert sein (Eskalation steht an)');
});

test('Trading-Cockpit: Markout-Verdict (trägt Making?) erscheint als Tor für maker_enabled', () => {
  const w = win(POLYTAB);
  const html = w._ptRestingBlock([], {
    mls: { verdict: 'traegt_nicht', netMakerPP: -0.8 },
    wm:  { verdict: 'traegt', netMakerPP: 1.0 },
  });
  assert.match(html, /Kann Making funktionieren/);
  assert.match(html, /MLS: trägt NICHT/, 'toxischer Markout muss klar rot benannt sein');
  assert.match(html, /erst scharfschalten, wenn das dauerhaft/, 'Gate-Hinweis fehlt');
});

test('Trading-Cockpit: ohne Markout-Daten keine Verdict-Zeile', () => {
  const w = win(POLYTAB);
  assert.doesNotMatch(w._ptRestingBlock([], {}), /Kann Making funktionieren/);
});
