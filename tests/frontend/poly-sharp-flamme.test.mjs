// tests/frontend/poly-sharp-flamme.test.mjs — 12.09.2026 (Plattform-Audit, Block B)
//
// 🔴 Die Rangliste „🥇 Schärfste Wallets" hat zwei Modi. Im CLV-Modus wurde am 13.08.2026 die
// Regel eingebaut, dass 🔥 nur bei bestandenem Sharp-Gate erscheint („🔥 nur bei echtem
// Sharp-Gate", steht so im Code). Im P&L-Modus — dem AKTIVEN, sobald Wallets eine P&L haben —
// wurde sie nie eingebaut: dort hing die Flamme an `r.pnl > 0`.
//
// Gemessen an den 20 angezeigten Zeilen: **17 trugen 🔥, 3 bestehen das Gate.** 14 Flammen ohne
// Beleg, und zwar auf dem Screen, der beantworten soll, wem man folgen sollte. Der Abschnitt sagt
// in seiner eigenen Kopfzeile, dass die Poly-P&L **null** Information über die Kante trägt
// (Median-CLV der Top-20 = Median aller Qualifizierten, r=0,06) — sie ist plattformweit, also
// Wahlen und Krypto, nicht Sport.
//
// Fehlerklasse: **eine Regel, die an zwei Stellen steht, wird an einer repariert.** Deshalb prüft
// dieser Test nicht nur das Ergebnis, sondern dass BEIDE Modi dieselbe Funktion benutzen.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const ROOT = new URL('../../', import.meta.url);
const JS = readFileSync(new URL('poly-wallets.js', ROOT), 'utf8');

function fenster(cache) {
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: false, json: () => Promise.resolve(null) });
  w.eval(JS);
  w._pwCache = cache || {};
  return w;
}

// Eine Wallet, die viel Geld verdient hat und trotzdem nichts beweist: n unter der Schwelle.
const REICH_ABER_UNBELEGT = {
  pnl: 900000, pnlKnown: true, n: 3, wins: 2, hit: 0.667, avgClv: 0.4, usd: 50000,
  lastTs: new Date().toISOString(),
};
// Und eine, die das Gate wirklich besteht.
const BELEGT = {
  pnl: 12000, pnlKnown: true, n: 40, wins: 26, hit: 0.65, avgClv: 1.2, usd: 80000,
  lastTs: new Date().toISOString(),
};

test('⭐ Geld allein gibt keine Flamme mehr', () => {
  const w = fenster();
  assert.strictEqual(w._pwIsSharpScore(REICH_ABER_UNBELEGT), false,
    'n=3 kann nichts belegen, egal wie hoch die P&L ist');
  assert.strictEqual(w._pwIsSharpScore(BELEGT), true);
});

test('die n-Schwelle des Gates ist scharf — 7 perfekte Wetten reichen nicht, 8 schon', () => {
  // Ohne diesen Fall bliebe „n-Schwelle entfernt" eine gruene Mutation: bei kleinem n scheitert
  // ohnehin meist die Wilson-Untergrenze, die Schwelle selbst waere also ungeprueft.
  const w = fenster();
  const perfekt = (n) => ({ n, wins: n, hit: 1, avgClv: 1 });
  assert.strictEqual(w._pwIsSharpScore(perfekt(7)), false,
    '7 von 7 ist ein Punktschaetzer, kein Beleg');
  assert.strictEqual(w._pwIsSharpScore(perfekt(8)), true);
});

test('⭐ beide Modi benutzen DIESELBE Regel', () => {
  // Der eigentliche Wächter. Ein Ergebnis-Test hätte den Fehler nicht gefunden: der CLV-Modus
  // war ja korrekt, nur der andere nicht — und der läuft nur, wenn P&L da ist.
  // Ohne Kommentare: ein Kommentar, der den Fehler BESCHREIBT, ist nicht der Fehler. (Beim
  // Schreiben dieses Tests genau hineingelaufen — die Erklaerung oben enthaelt die alte Zeile.)
  const ohneKommentar = (t) => t.replace(/^\s*\/\/.*$/gm, '');
  const pnlBlock = ohneKommentar(
    JS.slice(JS.indexOf('function _pwRankByPnl'), JS.indexOf('function _pwRankByClv')));
  const clvBlock = ohneKommentar(JS.slice(JS.indexOf('function _pwRankByClv')).slice(0, 4000));
  for (const [name, block] of [['P&L-Modus', pnlBlock], ['CLV-Modus', clvBlock]]) {
    assert.ok(/_pwIsSharpScore\(/.test(block), `${name} fragt das Sharp-Gate nicht`);
    assert.ok(!/pnl\s*>\s*0\s*\?\s*'🔥/.test(block),
      `${name} hängt die Flamme wieder an die P&L`);
  }
});

test('am echten Bestand: deutlich weniger Flammen als Zeilen', () => {
  const track = JSON.parse(readFileSync(new URL('poly_wallet_track.json', ROOT), 'utf8'));
  const w = fenster({ walletTrack: track });
  const rows = w._pwRankRowsPnl(track.scores);
  if (!rows.length) return;                     // ohne Bestand nichts zu prüfen
  const flammen = rows.filter(r => w._pwIsSharpScore(r)).length;
  const nachGeld = rows.filter(r => r.pnl > 0).length;
  assert.ok(flammen <= nachGeld,
    'das Gate darf nie MEHR Wallets auszeichnen als die alte Geld-Regel');
  assert.ok(flammen < rows.length,
    'wenn jede angezeigte Zeile eine Flamme trägt, sagt die Flamme nichts mehr');
});

test('die Legende verspricht genau das, was die Flamme jetzt bedeutet', () => {
  assert.match(JS, /🔥 = bewiesen scharf/,
    'die Legende ist weg — dann weiß niemand mehr, was die Flamme behauptet');
});
