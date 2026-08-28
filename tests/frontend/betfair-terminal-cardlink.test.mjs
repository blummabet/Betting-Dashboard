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
    { matchId: 'D', home: 'Jota', away: 'Kappa', league: 'Test Liga', live: false,
      kickoff: iso(180 * 60e3), moneySide: 'home', moneyName: 'Jota', moneyOdd: 1.7,
      moneyDir: 'in', totVol: 30000, pinn: { home: 0.60, draw: 0.22, away: 0.18, fav: 'home' },
      verdict: 'konsens', pinnMovePP: 0.3, poly: null },
  ] };
}
const LINKS = { links: {
  // sc = convictionScore aus liga-data.json, Skala 0-10 (NICHT 0-1).
  A: { market: 'Heimsieg', odds: 1.62, sc: 8, icon: '🏠', verdict: 'BET',
       sides: ['home'], moneySide: 'home', agree: true, nPicks: 2, matchedBy: 'exakt' },
  B: { market: 'Heimsieg', odds: 2.10, sc: 6, icon: '🏠', verdict: 'ABWÄGEN',
       sides: ['home'], moneySide: 'away', agree: false, nPicks: 1, matchedBy: 'bruecke' },
  // 28.08.2026: Tor-Picks werden gegen den Boersen-Tormarkt geprueft statt uebergangen.
  C: { market: 'Über 3.5 Tore', odds: 1.50, sc: 6, icon: '⚽', verdict: 'ABWÄGEN',
       sides: [], moneySide: 'home', agree: true, nPicks: 1, matchedBy: 'exakt',
       achse: 'tor', torMarkt: 'Over/Under 3.5 Goals', torSeite: 'Over',
       torEur: 7039, torSharePct: 87 },
  D: { market: 'Unter 2.5 Tore', odds: 2.10, sc: 5, icon: '🛡', verdict: 'ABWÄGEN',
       sides: [], moneySide: 'home', agree: true, nPicks: 1, matchedBy: 'exakt',
       achse: 'tor', torMarkt: 'Over/Under 2.5 Goals', torSeite: 'Under',
       torEur: 40, torSharePct: 90 },
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
  assert.match(h, /Konviktion 8\/10/, 'Konviktion auf der 0-10-Skala, nicht als Prozent');
  assert.doesNotMatch(h, /Konviktion \d00%/, 'sc*100 waere „Konviktion 800%" gewesen');
});

test('Zustimmung und Widerspruch sind unterscheidbar', () => {
  const h = panel(boot(LINKS));
  assert.match(h, /Geld auf unserer Seite/, 'Zustimmung wird benannt');
  assert.match(h, /Geld steht gegen unsere Card/, 'Widerspruch wird benannt');
});

test('Tor-Pick wird gegen den Boersen-Tormarkt beurteilt, nicht uebergangen', () => {
  const h = panel(boot(LINKS));
  assert.match(h, /Über 3\.5 Tore/, 'der Tor-Pick wird angezeigt');
  assert.match(h, /Over\/Under 3\.5 Goals Over: 87%/, 'die Basis des Urteils steht dran');
});

test('duenner Tormarkt wird als duenn gekennzeichnet', () => {
  // 87 % von 7.039 EUR ist eine andere Aussage als 90 % von 40 EUR.
  const h = panel(boot(LINKS));
  assert.match(h, /\(dünn\)/, 'der 40-EUR-Markt wird als duenn markiert');
  const idxDuenn = h.indexOf('(dünn)');
  const idxUeber = h.indexOf('Über 3.5 Tore');
  assert.ok(idxDuenn > idxUeber, 'der dicke 7k-Markt bekommt KEIN duenn-Label');
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
