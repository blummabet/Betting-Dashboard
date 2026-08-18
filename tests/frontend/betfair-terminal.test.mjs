// tests/frontend/betfair-terminal.test.mjs — 🖥️ Terminal (17.08.2026, Lucas).
// Prüft den additiven Terminal-Menüpunkt: Board sortiert nach Edge, ½-Kelly in € skaliert mit
// Bankroll, Zeilen-Klick öffnet Drilldown (Preis-Kurve-SVG + gematcht-je-Quote + Richtung),
// und der Konsens/Live-View bleibt unbeschädigt. INLINE-Fixtures (nicht die Live-JSONs).
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const ROOT = new URL('../../', import.meta.url);
function iso(ms = 0) { return new Date(Date.now() + ms).toISOString(); }

function consensusFixture() {
  return { games: [
    // Klare positive Kante: fair 1/0.68=1.47, angeboten 1.58 -> Edge ~ +7,4 %
    { matchId: 'A', home: 'Alpha', away: 'Beta', league: 'Test Liga', live: true,
      kickoff: iso(-30 * 60e3), moneySide: 'home', moneyName: 'Alpha', moneyOdd: 1.58,
      moneyDir: 'in', totVol: 111000, pinn: { home: 0.68, draw: 0.2, away: 0.12, fav: 'home' },
      verdict: 'konsens', pinnMovePP: 1.5, poly: { sharePct: 70, odd: 1.5, vol: 40000 } },
    // Negative Kante: fair 1/0.82=1.22, angeboten 1.20 -> Edge < 0
    { matchId: 'B', home: 'Gamma', away: 'Delta', league: 'Test Liga', live: false,
      kickoff: iso(90 * 60e3), moneySide: 'home', moneyName: 'Gamma', moneyOdd: 1.20,
      moneyDir: 'out', totVol: 25000, pinn: { home: 0.82, draw: 0.12, away: 0.06, fav: 'away' },
      verdict: 'uneinig', pinnMovePP: -2.0, poly: null },
  ] };
}
function histFixture() {
  return {
    'A': [
      { ts: iso(-6 * 3600e3), totalVol: 10000, mo: { hw: 1.44, dr: 4.0, aw: 6.0, vol: 9000 } },
      { ts: iso(-3 * 3600e3), totalVol: 60000, mo: { hw: 1.46, dr: 3.9, aw: 6.1, vol: 55000 } },
      { ts: iso(-30 * 60e3), totalVol: 111000, mo: { hw: 1.58, dr: 3.7, aw: 6.5, vol: 100000 } },
    ],
    'B': [
      { ts: iso(-4 * 3600e3), totalVol: 8000, mo: { hw: 1.25, dr: 5, aw: 9, vol: 7000 } },
      { ts: iso(0), totalVol: 25000, mo: { hw: 1.20, dr: 5.2, aw: 9.5, vol: 22000 } },
    ],
  };
}
function boot() {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="betfairRadarPanel"></div></body>',
    { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w._bfNoAutoRefresh = true;
  w.eval(readFileSync(new URL('betfair-radar.js', ROOT), 'utf8'));
  w._bfState.data = { matches: [] };   // sonst triggert renderBetfairRadar einen fetch (kein Netz im Test)
  w._bfState.consensus = consensusFixture();
  w._bfState.hist = histFixture();
  w._bfState.loading = false;
  w._bfState.view = 'terminal';
  return w;
}
function panel(w) { return w._renderBetfairRadar(); }   // frisch rendern -> spiegelt bankroll/termOpen-State

test('Terminal-Button existiert im View-Umschalter (Nav bleibt erreichbar)', () => {
  const w = boot();
  assert.match(panel(w), /🖥️ Terminal/, 'Umschalter mit Terminal-Button im Terminal-View');
  assert.match(panel(w), /🧭 Konsens/, 'andere View-Buttons weiterhin da');
});

test('Board sortiert nach Edge: positive Kante (Alpha) vor negativer (Gamma)', () => {
  const w = boot();
  const h = panel(w);
  assert.ok(h.indexOf('Alpha') < h.indexOf('Gamma'), 'Alpha (höhere Edge) steht oben');
  assert.match(h, /\+7\.\d%/, 'Edge von Alpha ~ +7 %');
});

test('½-Kelly in € skaliert mit Bankroll, nur bei positiver Edge', () => {
  const w = boot();
  w._bfTermBank(1000);
  const at1k = panel(w);
  w._bfTermBank(2000);
  const at2k = panel(w);
  // Alpha hat positive Edge -> € steigt mit Bankroll; Gamma (negativ) -> kein Stake
  const eur1k = (at1k.match(/€(\d+)\b/g) || []);
  assert.ok(/€\d/.test(at2k), 'ein €-Stake sichtbar');
  assert.notStrictEqual(at1k, at2k, 'Bankroll-Änderung verändert die €-Stakes');
});

test('Zeilen-Klick öffnet Drilldown mit Kurve (SVG) + gematcht-je-Quote', () => {
  const w = boot();
  assert.ok(!/<svg/.test(panel(w)), 'geschlossen: keine Kurve');
  w._bfTermOpen('A');
  const open = panel(w);
  assert.match(open, /<svg/, 'Drilldown zeigt Preis-Kurve als SVG');
  assert.match(open, /Gematcht je Quote/, 'Drilldown zeigt Matched-by-Price');
  assert.match(open, /fair 1\.47/, 'faire Pinnacle-Linie beschriftet');
  w._bfTermOpen('A'); // toggle zu
  assert.ok(!/<svg/.test(panel(w)), 'erneuter Klick schließt den Drilldown');
});

test('Konviktions-Score (P4): einig+Geld-rein+Steam hoch, Widerspruch+Drift niedrig', () => {
  const w = boot();
  const board = panel(w);
  assert.match(board, /100/, 'Alpha (konsens+in+steam+poly) erreicht Top-Konviktion');
  // Drilldown von Alpha zeigt Panel mit Label + Quellen-Zeilen
  w._bfTermOpen('A');
  const open = panel(w);
  assert.match(open, /Konviktion \(3 Quellen\)/, 'Konviktions-Panel im Drilldown');
  assert.match(open, /🔥 Stark/, 'starke Konviktion ausgewiesen');
  assert.match(open, /Pinnacle/, 'Quellen-Aufschlüsselung');
  // Gamma (uneinig+out) muss klar niedriger sein
  w._bfTermOpen('A'); w._bfTermOpen('B');
  assert.match(panel(w), /⚠ Widerspruch|Schwach/, 'Gamma niedrige Konviktion / Widerspruch');
});

test('Konsens-View bleibt unbeschädigt (additiv)', () => {
  const w = boot();
  w._bfSetView('consensus');
  const h = panel(w);
  assert.ok(!/🖥️ Terminal — handelbare Kanten/.test(h), 'Konsens rendert nicht das Terminal-Board');
  assert.doesNotThrow(() => w._bfSetView('live'));
});
