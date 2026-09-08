// tests/frontend/uebersicht-signalbilanz-schwelle.test.mjs — 08.09.2026
//
// Fehlerklasse: fehlende Information rendert als harmloser Default.
// Die Signal-Bilanz las ihre Feuer-Schwelle aus `pulse.signals.minFire`. Das Feld heisst
// `minFire`, liegt aber in `pulse.signalBoard` — demselben Objekt, aus dem die Zeilen kommen.
// `d.signals` ist null, die Kette ergab 0, und mit Schwelle 0 ist keine Zeile duenn: alle 25
// standen ausgeklappt und gleichwertig, darunter fuenf mit n<=2.
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

function board(w, signalBoard) {
  w._mdState.data = { pulse: { signalBoard: signalBoard } };
  return w._mdSignalBoardTest();
}

const DICK = { name: 'betfair_money', fire: 130, supp: 80, opp: 40, suppWinPct: 60, oppWinPct: 50, clvDiff: 2.7, clvUrteil: 'traegt bei' };
const DUENN = { name: 'reverse_line_move', fire: 2, supp: 2, opp: 0, suppWinPct: 100, oppWinPct: null };

test('Schwelle steht in signalBoard — duenne Zeilen wandern in die Sammelzeile', () => {
  const w = load();
  const html = board(w, { n: 500, baseWinPct: 52, minFire: 6, rows: [DICK, DUENN] });
  assert.match(html, /unter n6/, 'Die Sammelzeile muss die tatsaechliche Schwelle nennen');
  assert.doesNotMatch(html, /Umkehr|reverse/i.test('x') ? /$^/ : /sb-nm">[^<]*Umkehr/,
    'die duenne Zeile darf nicht als eigene Zeile stehen');
  assert.match(html, /n130/, 'die dicke Zeile bleibt');
});

test('fehlt die Schwelle wirklich, sagt die Tafel es — statt auf 0 zu fallen', () => {
  const w = load();
  const html = board(w, { n: 500, baseWinPct: 52, rows: [DICK, DUENN] });
  assert.match(html, /keine Feuer-Schwelle/,
    'Ohne Schwelle muss die Tafel das benennen, sonst stehen n2 und n130 gleichwertig da');
  assert.match(html, /n2/, 'die duenne Zeile bleibt sichtbar — sie wird nur nicht mehr stillschweigend gleichgestellt');
});

test('die alte Fehlstelle ist weg — pulse.signals wird nicht mehr gelesen', () => {
  // Kommentarzeilen raus: der Vorfall STEHT im Code dokumentiert und soll dort stehen bleiben.
  const src = readFileSync(MOD, 'utf8').split('\n')
    .filter((z) => !/^\s*(\/\/|\*|\/\*)/.test(z)).join('\n');
  assert.doesNotMatch(src, /d\.signals\s*&&\s*d\.signals\.minFire/,
    'minFire darf nur aus signalBoard kommen — dort liefert der Produzent es');
});
