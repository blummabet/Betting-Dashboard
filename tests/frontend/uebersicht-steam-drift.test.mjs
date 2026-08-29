// tests/frontend/uebersicht-steam-drift.test.mjs — 29.08.2026
//
// Aus Lucas' Dump der „Top-Wetten jetzt" stand auf Platz 3:
//   „Sao Paulo @2.60 · −5,4pp · Quote driftet → Geld auf Gegenseite"
// Eine Empfehlung auf die Seite, die das Geld gerade VERLÄSST. Ursache: der Steam-Block prüfte
// den BETRAG der Bewegung (Math.abs(pp)), und der reservierte Betfair-Platz tat es noch einmal.
// Für den Frisches-Geld-Block hat Lucas dieselbe Frage am 16.08. entschieden: `dir === 'out'`
// fliegt raus. Dieser Test hält beide Blöcke auf derselben Regel.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const MOD = new URL('../../main-dashboard.js', import.meta.url);

function render(steam) {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="mainDashPanel"></div></body>',
    { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve(null) });
  w.eval(readFileSync(MOD, 'utf8'));
  w._mdState.data = {
    liga: null, mls: null, ligaStreaks: null, mlsStreaks: null, betfair: null, whales: null,
    bfOverview: { steam, flow: [] },
  };
  w._renderMainDash();
  // NUR die Empfehlungs-Sektion. Die beschreibende Kachel „Betfair-Steam" darunter zeigt die
  // driftende Zeile weiterhin — und soll das auch: dort ist sie Information, hier wäre sie Rat.
  return w.document.getElementById('mdJetztBox').outerHTML;
}

const ko = () => new Date(Date.now() + 3 * 3600e3).toISOString();
const row = (home, pp) => ({
  matchId: 'm' + home, home, away: 'Gegner ' + home, league: 'English Premier League',
  kickoff: ko(), pp, odd: 2.6, sideName: home,
});

test('eine wegdriftende Quote wird nicht als Top-Wette empfohlen', () => {
  const html = render([row('Sao Paulo', -5.4), row('Arsenal', 4.0)]);
  assert.match(html, /Arsenal/, 'die mitziehende Quote gehört rein');
  assert.doesNotMatch(html, /Sao Paulo/,
    'die verlassene Seite darf nicht als Top-Wette auftauchen — das Geld liegt gegenüber');
});

test('driftet ALLES, bleibt der reservierte Betfair-Platz leer statt falsch belegt', () => {
  // Vorher hat `Math.abs(pp) >= 3` genau hier zugeschlagen: kein einziger Back-Rückhalt da,
  // trotzdem eine Betfair-Zeile in den Top-Wetten — weil der Betrag groß genug war.
  const html = render([row('Sao Paulo', -5.4), row('Fluminense', -6.1)]);
  assert.doesNotMatch(html, /Sao Paulo|Fluminense/);
  assert.match(html, /kein spielbares Signal|Top-Wetten jetzt/);
});

test('die Regel steht im Code, nicht nur im Ergebnis', () => {
  const src = readFileSync(MOD, 'utf8');
  const jetzt = src.slice(src.indexOf('function _mdJetzt'), src.indexOf('function _mdFillJetzt'));
  assert.doesNotMatch(jetzt, /Math\.abs\(\+x\.pp/,
    'der Betrag von pp darf nirgends mehr über eine Empfehlung entscheiden');
});
