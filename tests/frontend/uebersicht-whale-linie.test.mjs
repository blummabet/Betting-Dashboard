// 🔴 10.10.2026 (Übersicht-Check): „🐋 Poly Whale-Bets · Over ↗ → Over · EPL · in 2h · $49.3K".
// Kein Spiel, keine Linie. Im Artefakt: epl-ars-lee-2026-10-10-more-markets, frage „Arsenal FC
// vs. Leeds United FC: O/U 0.5", gekauft zu 0.9586 — eine Parkwette auf ein Tor, die als
// größter Over-Whale des Tages dastand. Fehlende Information rendert als harmloser Default.
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
  w.PW_BLOCKED_BET_CATS = ['US-Sport', 'Kampfsport', 'Cricket'];
  w._pwSportCategory = (lg, sp) => sp || 'Fußball';
  w._pwEnsurePlaysData = (cb) => cb && cb();
  w._pwOverNormTop = () => [];
  return w;
}

test('Whale-Bets: Spiel, Linie und Preis aus dem Artefakt, ohne Poly-Tab-Cache', () => {
  const w = load();
  w._mdState.data = {
    liga: null, mls: null, ligaStreaks: null, mlsStreaks: null, betfair: { matches: [] }, pulse: null,
    whales: {
      'epl-ars-lee-2026-10-10-more-markets': {
        league: 'EPL', sport: 'Fußball', capturedAt: new Date().toISOString(), hoursToKickoff: 2,
        frage: 'Arsenal FC vs. Leeds United FC: O/U 0.5',
        whales: [{ wallet: '0xA', side: 'Over', usd: 49290, avgPrice: 0.9586 }] },
    },
  };
  w._renderMainDash();
  const h = w.document.getElementById('mainDashPanel').innerHTML;
  const seg = (h.split('Poly Whale-Bets')[1] || '').split('md-cell-whale')[0];
  assert.match(seg, /Arsenal FC vs\. Leeds United FC/, 'das Spiel steht da');
  assert.match(seg, /Over 0\.5/, 'die Linie steht da');
  assert.match(seg, /@96¢/, 'der Preis steht da');
});

test('_mdWhaleFrage trennt nur Linien ab, nicht das Spiel', () => {
  const w = load();
  assert.deepStrictEqual({ ...w._mdWhaleFrage('Arsenal FC vs. Leeds United FC: O/U 2.5') },
    { spiel: 'Arsenal FC vs. Leeds United FC', linie: '2.5' });
  const t = w._mdWhaleFrage('Shanghai Rolex Masters: Arthur Fils vs Pavel Kotov');
  assert.strictEqual(t.linie, null);
  assert.match(t.spiel, /Fils vs Pavel Kotov/);
});

test('Volumen über Norm: Over trägt seine Linie', () => {
  const w = load();
  w._pwOverNormTop = () => [{ key: 'epl-ars-lee-2026-10-10-more-markets', league: 'EPL', sport: 'Fußball',
    name: 'Arsenal FC vs Leeds United FC', fav: 'Over', favPct: 95, usd: 85300, ratio: 6.9,
    frage: 'Arsenal FC vs. Leeds United FC: O/U 0.5' }];
  w._mdState.data = { liga: null, mls: null, ligaStreaks: null, mlsStreaks: null, betfair: { matches: [] }, pulse: null, whales: {} };
  w._renderMainDash();
  const h = w.document.getElementById('md-cell-whale').innerHTML;
  assert.match(h, /Geld auf Over 0\.5 95%/);
});
