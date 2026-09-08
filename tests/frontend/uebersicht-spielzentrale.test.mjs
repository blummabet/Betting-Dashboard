// tests/frontend/uebersicht-spielzentrale.test.mjs — Ebene 0 (08.09.2026)
//
// Lucas: „alle sources zu sehen aber auch Empfehlungen was deckt sich."
//
// Die Ebene liest `spielzentrale.json` und rechnet NICHTS nach — das Urteil entsteht im
// Produzenten. Hier wird festgehalten, dass sie sich daran haelt: ein anderes `urteil` in der
// Datei muss auf dem Board ein anderes Urteil ergeben, ohne dass das Frontend die Quellen
// selbst zaehlt. Und die Restmenge muss dastehen: eine Liste mit drei Zeilen ohne die Zahl
// daneben liest sich wie ein Ausfall und ist eine Messung.
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

function zeile(over) {
  return Object.assign({
    matchId: '1', home: 'Real Madrid', away: 'Inter', league: 'UEFA Champions League',
    kickoff: new Date(Date.now() + 9 * 3600e3).toISOString(), live: false,
    betfair: { seite: 'home', name: 'Real Madrid', anteilPct: 88, eur: 102861, odd: 1.66 },
    poly: { seite: 'home', name: 'Real Madrid CF', anteilPct: 60, usd: 294571, art: 'geld' },
    pinn: { fav: 'home', home: 0.6, draw: 0.21, away: 0.19 },
    stake: { usd: 21362, n: 9, seite: 'home', seiteUsd: 12000 },
    card: null, duenn: false, nGeld: 3, nQuellen: 4,
    urteil: 'einig', seite: 'home', dafuer: ['betfair', 'poly', 'stake'], gegen: [], anker: 'passt',
    text: 'Betfair und Polymarket und Stake-Highroller liegen auf derselben Seite (Heim).',
  }, over || {});
}

function board(w, doc) {
  w._mdState.data = { zentrale: doc };
  return w._mdZentraleTest();
}

test('einige Zeile: alle Quellen stehen als eigene Spalte, das Urteil kommt aus der Datei', () => {
  const w = load();
  const html = board(w, { fensterH: 24, n: 1, zeilen: [zeile()], rest: { einzeln: 77 } });
  assert.match(html, /Real Madrid/);
  ['Betfair', 'Polymarket', 'Stake', 'Pinnacle', 'eigene Card'].forEach((q) =>
    assert.match(html, new RegExp(q), 'Spalte fehlt: ' + q));
  // Geld wird auf der Zentrale gekuerzt (€103K) — die Zeilen sollen scanbar sein, nicht exakt.
  assert.match(html, /€103K/, 'Betfair-Geld fehlt');
  assert.match(html, /\$295K/, 'Poly-Geld fehlt');
  assert.match(html, /Quellen einig/);
  assert.match(html, /liegen auf derselben Seite/, 'der Satz aus der Datei wird nicht gezeigt');
});

test('das Frontend zaehlt nicht selbst — ein anderes Urteil in der Datei schlaegt durch', () => {
  // Dieselben drei Quellen, aber der Produzent sagt „uneinig". Wer im Frontend nachrechnet,
  // wuerde hier weiter „einig" anzeigen.
  const w = load();
  const html = board(w, { fensterH: 24, n: 1, rest: {}, zeilen: [zeile({
    urteil: 'uneinig', dafuer: ['betfair'], gegen: ['poly'], nGeld: 2,
    text: 'Betfair auf Heim, Polymarket dagegen — kein Konsens, sondern eine Divergenz.',
  })] });
  assert.match(html, /uneinig/);
  assert.doesNotMatch(html, /Quellen einig/);
  assert.match(html, /Divergenz/);
});

test('Pinnacle steht als Anker da, nie als Stimme', () => {
  const w = load();
  const html = board(w, { fensterH: 24, n: 1, rest: {}, zeilen: [zeile({ anker: 'dagegen' })] });
  assert.match(html, /anderer Favorit/);
  assert.doesNotMatch(html, /Pinnacle[^<]*einig/);
});

test('ein reiner Poly-Preis wird als Preis beschriftet, nicht als Geld', () => {
  const w = load();
  const html = board(w, { fensterH: 24, n: 1, rest: {}, zeilen: [zeile({
    poly: { seite: 'home', name: 'Real Madrid CF', anteilPct: 60, usd: 597, art: 'preis' },
  })] });
  assert.match(html, /nur Preis/);
  assert.doesNotMatch(html, /\$597/);
});

test('fehlende Quelle ist eine leere Spalte an derselben Stelle — keine verschobene Zeile', () => {
  const w = load();
  const html = board(w, { fensterH: 24, n: 1, rest: {}, zeilen: [zeile({ stake: null, card: null })] });
  const leer = (html.match(/sz-c leer/g) || []).length;
  assert.equal(leer, 2, 'Stake und Card muessen als LEERE Spalten stehen, nicht fehlen');
  assert.match(html, /Stake/);
});

test('die Restmenge steht da — sonst liest sich die kurze Liste wie ein Ausfall', () => {
  const w = load();
  const html = board(w, { fensterH: 24, n: 1, zeilen: [zeile()],
    rest: { einzeln: 77, spaeter: 14, gelaufen: 9 } });
  assert.match(html, /77/, 'die Einzelquellen-Zahl fehlt');
  assert.match(html, /nur eine<\/b> Geldquelle/);
  assert.match(html, /14/); assert.match(html, /9/);
});

test('leere Zentrale sagt Ergebnis, fehlende Datei sagt unbekannt — das ist nicht dasselbe', () => {
  const w = load();
  const leer = board(w, { fensterH: 24, n: 0, zeilen: [], rest: { einzeln: 40 } });
  assert.match(leer, /Ergebnis, kein Fehler/);
  const fehlt = board(w, null);
  assert.match(fehlt, /❔ unbekannt/);
  assert.match(fehlt, /nicht dasselbe wie/);
});

test('duenner Markt wird benannt, nicht versteckt', () => {
  const w = load();
  const html = board(w, { fensterH: 24, n: 1, rest: {}, zeilen: [zeile({
    duenn: true, betfair: { seite: 'home', name: 'Nomme Kalju', anteilPct: 95, eur: 627, odd: 1.1 },
  })] });
  assert.match(html, /dünner Markt/);
  assert.match(html, /95%/);
});

test('Ebene 0 haengt in der Sektion und die Unterzeile erklaert sie', () => {
  const src = readFileSync(MOD, 'utf8');
  assert.match(src, /_mdZentrale\(\) \+ _mdFreigabe\(\)/, 'Ebene 0 steht nicht vor Ebene 1');
  assert.match(src, /Ebene <b>0<\/b> zeigt/, 'die Sektion erklaert Ebene 0 nicht');
  assert.match(src, /jf\('spielzentrale\.json'\)/, 'die Datei wird nicht geladen');
});
