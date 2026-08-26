// tests/frontend/betfair-terminal-cardlink.test.mjs — „unsere Card sagt X, und das Geld?"
// 26.08.2026 (Lucas): Das Terminal zeigte in der Pick-Spalte immer die GELD-Seite von Betfair,
// nie unseren eigenen Pick — man sah also nicht, ob die Boerse mit uns oder gegen uns steht.
// Der Link kommt fertig aus betfair_card_link.py; hier nur die Darstellung.
// WICHTIG (Leitplanke): Information, KEIN zweites Urteil — das Terminal stuft nie etwas herab.
// INLINE-Fixtures, nie die Live-JSONs.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const ROOT = new URL('../../', import.meta.url);
function iso(ms = 0) { return new Date(Date.now() + ms).toISOString(); }

function games() {
  return { games: [
    { matchId: 'A', home: 'Alpha', away: 'Beta', league: 'Test Liga', live: false,
      kickoff: iso(90 * 60e3), moneySide: 'home', moneyName: 'Alpha', moneyOdd: 1.58,
      moneyDir: 'in', totVol: 111000, pinn: { home: 0.68, draw: 0.2, away: 0.12, fav: 'home' },
      verdict: 'konsens', pinnMovePP: 1.5, poly: null },
    { matchId: 'B', home: 'Gamma', away: 'Delta', league: 'Test Liga', live: false,
      kickoff: iso(120 * 60e3), moneySide: 'away', moneyName: 'Delta', moneyOdd: 2.4,
      moneyDir: 'in', totVol: 60000, pinn: { home: 0.40, draw: 0.26, away: 0.34, fav: 'home' },
      verdict: 'konsens', pinnMovePP: 0.4, poly: null },
    { matchId: 'C', home: 'Epsilon', away: 'Zeta', league: 'Test Liga', live: false,
      kickoff: iso(150 * 60e3), moneySide: 'home', moneyName: 'Epsilon', moneyOdd: 1.9,
      moneyDir: 'in', totVol: 40000, pinn: { home: 0.55, draw: 0.25, away: 0.20, fav: 'home' },
      verdict: 'konsens', pinnMovePP: 0.2, poly: null },
  ] };
}
const LINKS = { links: {
  A: { market: 'Heimsieg', marketKey: 'homeWin', odds: 1.62, sc: 0.81, icon: '🏠',
       sides: ['home'], moneySide: 'home', agree: true, nPicks: 2, matchedBy: 'exakt' },
  B: { market: 'Heimsieg', marketKey: 'homeWin', odds: 2.10, sc: 0.63, icon: '🏠',
       sides: ['home'], moneySide: 'away', agree: false, nPicks: 1, matchedBy: 'bruecke' },
  C: { market: 'Über 2.5 Tore', marketKey: 'over25', odds: 1.85, sc: 0.7, icon: '⚽',
       sides: [], moneySide: 'home', agree: null, nPicks: 1, matchedBy: 'exakt' },
} };

function boot(cardLink) {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="betfairRadarPanel"></div></body>',
    { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w._bfNoAutoRefresh = true;
  w.eval(readFileSync(new URL('betfair-radar.js', ROOT), 'utf8'));
  w._bfState.data = { matches: [] };
  w._bfState.consensus = games();
  w._bfState.hist = {};
  w._bfState.track = null;
  w._bfState.cardLink = cardLink;
  w._bfState.loading = false;
  w._bfState.view = 'terminal';
  return w;
}
const panel = (w) => w._renderBetfairRadar();

test('Spalte „Unsere Card" existiert und die Geld-Seite bleibt getrennt sichtbar', () => {
  const h = panel(boot(LINKS));
  assert.match(h, /Unsere Card/, 'neue Spalte im Kopf');
  assert.match(h, /Geld-Seite/, 'die Boersen-Seite ist jetzt klar als solche beschriftet');
});

test('Unser Pick steht in der Zeile — nicht nur der Betfair-Runner', () => {
  const h = panel(boot(LINKS));
  assert.match(h, /Heimsieg/, 'unser Pick-Name erscheint');
  assert.match(h, /@1\.62/, 'unsere Quote, nicht die Boersenquote');
  assert.match(h, /Konviktion 81%/, 'Konviktion der Card');
});

test('Zustimmung und Widerspruch sind unterscheidbar', () => {
  const h = panel(boot(LINKS));
  assert.match(h, /Geld auf unserer Seite/, 'Zustimmung wird benannt');
  assert.match(h, /Geld steht gegen unsere Card/, 'Widerspruch wird benannt');
});

test('Andere Achse bekommt KEIN Urteil (Tore sind nicht mit 1X2 vergleichbar)', () => {
  const h = panel(boot(LINKS));
  assert.match(h, /Über 2\.5 Tore/, 'der Tor-Pick wird trotzdem angezeigt');
  assert.match(h, /nicht vergleichbar/, 'aber ausdruecklich ohne Zustimmung/Widerspruch');
});

test('Ohne Card-Link bleibt das Terminal heil und sagt es ehrlich', () => {
  for (const empty of [null, {}, { links: {} }]) {
    const h = panel(boot(empty));
    assert.match(h, /keine Card/, 'ehrliche Leermeldung statt stiller Luecke');
    assert.match(h, /Alpha/, 'die Boersen-Zeile steht weiterhin');
    assert.doesNotMatch(h, /undefined/, 'kein undefined im Markup');
  }
});

test('Das Terminal faellt kein eigenes Urteil — es blendet keine Zeile aus und mutet nicht', () => {
  const mit = panel(boot(LINKS));
  const ohne = panel(boot(null));
  for (const t of ['Alpha', 'Gamma', 'Epsilon']) {
    assert.ok(mit.includes(t) && ohne.includes(t), t + ' ist in beiden Faellen sichtbar');
  }
  // Widerspruch (Gamma) darf die Zeile NICHT abwerten oder verstecken
  assert.ok(mit.indexOf('Gamma') > 0, 'die widersprochene Zeile bleibt im Board');
});

test('Tabelle bleibt strukturell heil (colspan zieht mit der neuen Spalte mit)', () => {
  const w = boot(LINKS);
  w._bfTermOpen('A');
  const h = panel(w);
  assert.doesNotMatch(h, /colspan="8"/, 'kein veralteter colspan nach dem Spalten-Zuwachs');
  assert.match(h, /colspan="9"/, 'Drilldown spannt ueber alle Spalten');
});

test('Kaputter Link-Eintrag wirft nicht', () => {
  const h = panel(boot({ links: { A: null, B: 'kaputt', C: { market: null, odds: null } } }));
  assert.match(h, /Alpha/, 'Board rendert weiter');
  assert.doesNotMatch(h, /undefined/, 'kein undefined im Markup');
});
