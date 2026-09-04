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
    // C: kein Pinnacle-Anker -> muss gemutet werden ('kein Anker')
    { matchId: 'C', home: 'Epsilon', away: 'Zeta', league: 'Klein Liga', live: true,
      kickoff: iso(-10 * 60e3), moneySide: 'home', moneyName: 'Epsilon', moneyOdd: 1.05,
      moneyDir: 'in', totVol: 5000, pinn: null, verdict: 'no_anchor', poly: null },
    // D: Anker da, aber historisch schwacher CLV-Bucket -> muss gemutet werden ('Bucket')
    { matchId: 'D', home: 'Eta', away: 'Theta', league: 'Schwach Liga', live: false,
      kickoff: iso(120 * 60e3), moneySide: 'home', moneyName: 'Eta', moneyOdd: 1.60,
      moneyDir: 'in', totVol: 30000, pinn: { home: 0.66, draw: 0.2, away: 0.14, fav: 'home' },
      verdict: 'konsens', pinnMovePP: 0.5, poly: { sharePct: 60, odd: 1.6, vol: 20000 } },
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
  w._bfState.track = { n: 500, byLeagueMarket: { 'Schwach Liga|Match Odds': { n: 44, roi: -0.12, roiUg: -0.12, urteil: 'verliert', hitRate: 0.30 } } };
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

test('Auto-Mute (P1): kein-Anker & schwacher Bucket werden gemutet, nach unten sortiert, ausblendbar', () => {
  const w = boot();
  const board = panel(w);
  assert.match(board, /Nicht handelbar \(gemutet\)/, 'Trenn-Zeile für gemutete Reihen');
  assert.match(board, /🔇 kein Anker/, 'no-anchor-Zeile trägt kein-Anker-Tag');
  assert.match(board, /🔇 Bucket UG -12% ROI/, 'schwacher-Bucket-Zeile trägt Bucket-Tag');
  // gemutete Zeilen (C/D) stehen unter den handelbaren (Alpha/Gamma)
  assert.ok(board.indexOf('Alpha') < board.indexOf('Epsilon'), 'handelbar vor kein-Anker');
  assert.ok(board.indexOf('Gamma') < board.indexOf('Eta'), 'handelbar vor schwachem Bucket');
  // Toggle blendet gemutete komplett aus
  w._bfTermMute(true);
  const hidden = panel(w);
  assert.ok(!/Epsilon/.test(hidden) && !/Eta/.test(hidden), 'gemutete Zeilen ausgeblendet');
  assert.match(hidden, /Alpha/, 'handelbare bleiben sichtbar');
  w._bfTermMute(false);
  assert.match(panel(w), /Epsilon/, 'Toggle zeigt gemutete wieder');
});

// 🔴 04.09.2026 (Lucas: „mach ma mal Betfair-Check"). Das Mute lief auf dem Punktschätzer:
// `b.n>=10 && b.roi<=-0.05`. An dem Tag standen die fünf Ligen des Boards bei n = 9 bis 14 —
// Premier League −11,1 % auf n=10 nahm neun Zeilen vom Board, darunter die drei überzeugtesten
// (Man City 93, PSG 100, Arsenal 85). Bundesliga blieb bei −5,6 % nur deshalb stehen, weil n=9
// statt 10 war: ein einziger abgerechneter Play entschied über eine ganze Liga.
//
// Rauschprobe über die echten 1.652 Match-Odds-Plays: dieselben Stichprobengrößen zufällig aus
// einem gemeinsamen Topf gezogen ergeben in 91 % der Läufe eine mindestens so große Spanne
// zwischen bester und schlechtester Liga. Der Bucket sortierte Rauschen.
test('ein Bucket ohne Untergrenze mutet nicht — nichts zu wissen ist kein Grund wegzublenden', () => {
  const w = boot();
  w._bfState.track.byLeagueMarket['Schwach Liga|Match Odds'] = { n: 12, roi: -0.12, hitRate: 0.30 };
  w._bfSetView('terminal');
  const board = panel(w);
  assert.ok(!/🔇 Bucket/.test(board), '−12 % auf n=12 ist ein Punktschätzer, kein Grund zu muten');
  assert.match(board, /kein Urteil · n12/, 'stattdessen steht dran, dass nichts gemessen ist');
  assert.ok(!/🟢|🔴/.test(board.slice(board.indexOf('Eta'), board.indexOf('Eta') + 900)),
    'und keine Ampelfarbe, die einen Befund behauptet');
});

test('Konsens-View bleibt unbeschädigt (additiv)', () => {
  const w = boot();
  w._bfSetView('consensus');
  const h = panel(w);
  assert.ok(!/🖥️ Terminal — handelbare Kanten/.test(h), 'Konsens rendert nicht das Terminal-Board');
  assert.doesNotThrow(() => w._bfSetView('live'));
});

// 18.08.2026 (Lucas: „im Terminal nur 1X2, kein Over/Under — im Drilldown die anderen Märkte auch
// zeigen"): der Drilldown verknüpft per matchId mit betfair_prices.json und listet O/U/BTTS/…
// nach Matched-Volumen, mit führender Seite + Gegenquote. Reines Betfair-Geld, kein Edge-Anker.
test('Drilldown zeigt „Andere Märkte" (Über/Unter) aus betfair_prices je matchId', () => {
  const w = boot();
  // prices-Match zu Consensus-Game 'A' mit O/U-Markt bestücken
  w._bfState.data = { matches: [
    { matchId: 'A', home: 'Alpha', away: 'Beta',
      markets: {
        'Match Odds': { runners: [
          { name: 'Alpha', odd: 1.58, vol: 100000 }, { name: 'The Draw', odd: 3.7, vol: 8000 }, { name: 'Beta', odd: 6.5, vol: 6000 } ] },
        'Over/Under 2.5 Goals': { runners: [
          { name: 'Under 2.5 Goals', odd: 1.80, vol: 14000 }, { name: 'Over 2.5 Goals', odd: 2.10, vol: 9000 } ] },
        'Both teams to Score?': { runners: [
          { name: 'Yes', odd: 1.90, vol: 5000 }, { name: 'No', odd: 1.95, vol: 3000 } ] },
      } },
  ] };
  const closed = panel(w);
  assert.ok(!/Andere Märkte/.test(closed), 'geschlossen: kein Andere-Märkte-Block');
  w._bfTermOpen('A');
  const open = panel(w);
  assert.match(open, /Andere Märkte/, 'Drilldown zeigt Andere-Märkte-Block');
  assert.match(open, /Ü\/U 2\.5/, 'Über/Unter-2.5-Zeile da (gekürztes Label)');
  assert.match(open, /BTTS/, 'BTTS-Zeile da');
  assert.ok(!/Match Odds/.test(open.split('Andere Märkte')[1] || ''), 'Match Odds NICHT im Andere-Märkte-Block (ist ja die Hauptzeile)');
});

// 18.08.2026 (Lucas: „an Pinnacle-Totals andocken wäre geil"): O/U-Edge im Drilldown = faire
// Pinnacle-O/U-% (aus g.pinnTotals, de-viggt) × Betfair-Quote − 1. Plus Phasen-Mismatch-Schutz:
// weicht Betfairs eigene implied stark von Pinnacle ab (live vs pre-match), wird die Edge unterdrückt.
test('Drilldown zeigt O/U-Edge vs Pinnacle + unterdrückt Phasen-Mismatch', () => {
  const w = boot();
  w._bfState.data = { matches: [
    { matchId: 'A', home: 'Alpha', away: 'Beta',
      markets: {
        'Match Odds': { runners: [ { name: 'Alpha', odd: 1.58, vol: 100000 }, { name: 'The Draw', odd: 3.7, vol: 8000 }, { name: 'Beta', odd: 6.5, vol: 6000 } ] },
        // 2.5: Pinnacle overFair 0.55, Betfair Over@1.88 -> +3.4% Über (echte kleine Kante)
        'Over/Under 2.5 Goals': { runners: [ { name: 'Over 2.5 Goals', odd: 1.88, vol: 9000 }, { name: 'Under 2.5 Goals', odd: 2.14, vol: 6000 } ] },
        // 1.5: Betfair implied Over ~0.95 (Over@1.02/Under@20), Pinnacle overFair 0.60 -> Gap>0.25 -> Mismatch -> unterdrückt
        'Over/Under 1.5 Goals': { runners: [ { name: 'Over 1.5 Goals', odd: 1.02, vol: 4000 }, { name: 'Under 1.5 Goals', odd: 20.0, vol: 300 } ] },
        // BTTS: kein Pinnacle-Total -> kein Edge
        'Both teams to Score?': { runners: [ { name: 'Yes', odd: 1.90, vol: 5000 }, { name: 'No', odd: 1.95, vol: 3000 } ] },
      } },
  ] };
  // Pinnacle-Totals ans Consensus-Spiel A hängen (kommt real aus betfair_consensus.py)
  w._bfState.consensus.games = w._bfState.consensus.games.map(g =>
    g.matchId === 'A' ? { ...g, pinnTotals: { '2.5': { overFair: 0.55, underFair: 0.45 }, '1.5': { overFair: 0.60, underFair: 0.40 } } } : g);
  w._bfTermOpen('A');
  const open = panel(w);
  assert.match(open, /Edge vs Pinnacle/, 'Edge-Spalte im Andere-Märkte-Block');
  assert.match(open, /\+3\.4%/, 'Ü/U 2.5 zeigt +3,4% Edge');
  assert.match(open, /O\/U-Kante/, 'Header-Badge zählt die Kante ≥ +2%');
  // genau EINE grün markierte Value-Zeile (2.5) — die 1.5-Zeile ist Phasen-Mismatch -> unterdrückt
  const greens = (open.match(/border-left:2px solid #2ee08a/g) || []).length;
  assert.strictEqual(greens, 1, 'nur die echte Kante ist grün, Mismatch-Zeile nicht');
});
