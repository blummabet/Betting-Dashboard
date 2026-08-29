// tests/frontend/poly-sharp-wallet-floor.test.mjs
//
// 07.08.2026 (Lucas: „diese Wetten mit 2-6 Dollar was soll das … muss viel akkurater und schärfer
// sein"). Ursprünglich: die „scharfe Wallet" zählt nur, wenn beide Achsen stimmen.
//
// 29.08.2026 (Lucas: „prinzipiell checken, ob Schwellen sinnvoll sind") — die Regel dahinter hat
// sich geändert, und zwar an genau der Stelle, an der sie am meisten geschadet hat:
//
//   vorher   n>=4 · rohe Quote >=55% (oder >=50% mit CLV>=1pp) · CLV>=0 · P&L>0 ZWINGEND
//   jetzt    n>=8 · Wilson-Untergrenze der Quote >50% · CLV>=0 · P&L nur als AUSSCHLUSS
//
// Warum: eine rohe Quote ignoriert die Stichprobe. 5/9 sind 55,6% und beweisen nichts — die
// Wilson-Untergrenze liegt bei 30%. Von 42 Wallets, die das alte Gate „scharf" nannte, bestanden
// 27 diesen Test nicht; eine davon hatte $729 Lebensbilanz und CLV +0,03pp. Umgekehrt flogen 318
// Wallets nur deshalb raus, weil ihr P&L nie abgefragt wurde (Abdeckung: 13%) — nicht, weil sie
// schlecht waren. Damit entschied das Fetch-Budget, wer „bewiesen" ist.
//
// Die Definition wohnt jetzt in sharp_gate.py; sharp-gate-vertrag.test.mjs hält beide Seiten
// zusammen. Diese Datei prüft die Fälle, die Lucas real gemeldet hat.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const PW = new URL('../../poly-wallets.js', import.meta.url);
function load() {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="polyWalletsPanel"></div></body>',
    { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const { window } = dom;
  window.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  window.eval(readFileSync(PW, 'utf8'));
  return window;
}
// Die Aufrufer reichen teils {hit}, teils {wins} durch — Helfer baut beides konsistent.
const sc = (n, wins, avgClv, pnl) => ({
  n, wins, hit: n ? wins / n : 0, avgClv,
  pnl: pnl == null ? 0 : pnl, pnlKnown: pnl != null,
});

test('Hook _pwIsSharpScore ist da', () => {
  assert.equal(typeof load()._pwIsSharpScore, 'function');
});

test('BASEMENT-Fall: 30% Treffer raus (auch mit +CLV)', () => {
  assert.equal(load()._pwIsSharpScore(sc(10, 3, 0.8, 0)), false);
});

test('Giant-Pandas-Fall: negativer CLV raus (auch mit 58% Treffer + PnL)', () => {
  assert.equal(load()._pwIsSharpScore(sc(12, 7, -2.38, 15798)), false);
});

test('echte Sharp-Wallet zählt (Team WE 83% über n=23 · +CLV · +PnL)', () => {
  assert.equal(load()._pwIsSharpScore(sc(23, 19, 0.5, 34000)), true);
});

test('zu wenig Historie raus (n<8)', () => {
  assert.equal(load()._pwIsSharpScore(sc(7, 7, 1, 100)), false);
});

// ── Der Kern der Umstellung: die Stichprobe entscheidet mit ─────────────────────────────────
test('52% zählt NICHT — auch nicht mit deutlicher CLV (vorher zählte es)', () => {
  // Alte Regel: „marginaler Treffer (0,50–0,55) zählt bei Ø CLV >= 1pp." Das war ein Schlupfloch:
  // 52% über n=52 ist ein Münzwurf (Wilson 40%), und eine CLV von 1,4pp macht daraus keinen Beweis
  // für Trefferstärke. Wer eine Kante über CLV hat, soll sie über CLV zeigen — nicht als „scharfe
  // Trefferquote" durchrutschen.
  assert.equal(load()._pwIsSharpScore(sc(52, 27, 1.4, 495000)), false);
});

test('60% bei n=20 zählt NICHT — 12/20 ist Zufall im Rahmen', () => {
  // Alte Regel: „klar über Münzwurf (>=55%) zählt auch mit knapper CLV." 12/20 hat eine
  // Wilson-Untergrenze von 41,7%. Genau solche Wallets trugen Konviktion auf der Übersicht.
  assert.equal(load()._pwIsSharpScore(sc(20, 12, 0.2, 5000)), false);
});

test('dieselben 60% über n=100 zählen sehr wohl', () => {
  // Gleiche Quote, belastbare Stichprobe -> Wilson 52,4%. Genau der Unterschied, den die rohe
  // Quote nicht sehen konnte.
  assert.equal(load()._pwIsSharpScore(sc(100, 60, 0.2, 5000)), true);
});

// ── P&L: Ausschluss, kein Beweis ───────────────────────────────────────────────────────────
test('P&L = 0 ist kein Ausschluss mehr (0 ist kein Verlust)', () => {
  assert.equal(load()._pwIsSharpScore(sc(40, 28, 0.5, 0)), true);
});

test('P&L unbekannt schließt nicht aus — 87% der Wallets haben keinen', () => {
  assert.equal(load()._pwIsSharpScore(sc(40, 28, 0.5, null)), true);
});

test('bestätigter Verlierer bleibt draußen (88% Treffer bei −$7 Mio)', () => {
  assert.equal(load()._pwIsSharpScore(sc(40, 35, 1.0, -7000000)), false);
});
