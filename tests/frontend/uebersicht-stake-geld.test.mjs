// tests/frontend/uebersicht-stake-geld.test.mjs — Stake-Geld-Kachel der Übersicht (08.09.2026)
//
// Fehlerklasse: eine prominente Kachel zeigt zuverlässig Vergangenheit, ohne es zu sagen.
// Am 08.09. standen dort vier Spiele, die seit 11 bis 15 Stunden angepfiffen waren — sortiert
// nach Geld über ein 24-h-Fenster. Die Kachel war nicht falsch, sie war nutzlos: sie kostete
// jeden Blick, den man auf sie warf, und gab nie eine Handlung zurück.
//
// Drei Sätze werden hier festgehalten:
//   1. Gibt es Spiele vor Anpfiff, steht KEIN gelaufenes Spiel in der Kachel — auch dann nicht,
//      wenn das gelaufene mehr Geld hat (das ist der Gegenbeweis: Geld allein darf die
//      Reihenfolge nicht mehr bestimmen).
//   2. Gibt es keins, ist das Ergebnis ausdrücklich als Rückblick beschriftet.
//   3. Ohne Anpfiff gilt ein Spiel nicht als offen — fehlende Information ist keine Zukunft.
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

const H = 3600e3;
function wette(event, stundenBisAnpfiff, usd, tsStundenHer) {
  return {
    event, liga: 'Serie A', eventId: event,
    ts: new Date(Date.now() - tsStundenHer * H).toISOString(),
    anpfiff: new Date(Date.now() + stundenBisAnpfiff * H).toISOString(),
    einsatzUsd: usd, quote: 2.0, kat: 'Fußball', markt: '1X2', auswahl: 'Heim',
  };
}

function kachel(w, wetten) {
  w._mdState.data = { stake: { wetten: wetten, gesperrt: ['US-Sport'] } };
  return w._mdStakeGeldTest();
}

test('vor Anpfiff schlägt Geld — ein größeres, gelaufenes Spiel steht nicht in der Kachel', () => {
  const w = load();
  const html = kachel(w, [
    wette('Gelaufen Gross', -12, 9000, 13),   // mehr Geld, aber seit 12 h angepfiffen
    wette('Offen Klein', +5, 200, 2),
  ]);
  assert.match(html, /Offen Klein/);
  assert.doesNotMatch(html, /Gelaufen Gross/,
    'Ein seit 12 h laufendes Spiel darf die Kachel nicht belegen, solange eines vor Anpfiff da ist');
  assert.doesNotMatch(html, /Rückblick/, 'Mit offenem Spiel ist das kein Rückblick');
});

test('nur gelaufene Spiele → Kachel sagt selbst, dass sie Rückblick ist', () => {
  const w = load();
  const html = kachel(w, [
    wette('Gelaufen A', -12, 9000, 13),
    wette('Gelaufen B', -3, 400, 4),
  ]);
  assert.match(html, /Gelaufen A/);
  assert.match(html, /Rückblick/,
    'Ohne Spiel vor Anpfiff muss die Kachel den Rückblick benennen, statt ihn als Aktuelles zu zeigen');
});

test('Wette ohne Anpfiff zählt nicht als offen — fehlende Zeit ist keine Zukunft', () => {
  const w = load();
  const ohne = wette('Ohne Anpfiff', 0, 5000, 3); delete ohne.anpfiff;
  const html = kachel(w, [ohne]);
  assert.match(html, /Rückblick/,
    'Ohne Anpfiff ist unbekannt, nicht offen — sonst rutscht jedes zeitlose Spiel nach vorn');
});
