// tests/frontend/poly-wallet-stille.test.mjs — 01.09.2026
//
// Lucas: „die Whales Wallets ändern sich eh, sobald eine bessere erscheint, oder?"
// Ja — aber die Rangliste sortiert nach LEBENSZEIT-P&L, nicht nach Aktivität: 15 der Top-20 hatten
// keine offene Position, und ob sie seit zwei Tagen oder zwei Monaten still sind, war nicht
// feststellbar. Seit 01.09. schreibt poly_money_broad.py `lastTs` mit.
//
// Geprüft wird die Stelle, an der so eine Anzeige typischerweise lügt: sie macht aus einer
// FEHLENDEN Angabe eine gute Nachricht.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

function laden() {
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve(null) });
  w.eval(readFileSync(new URL('../../poly-wallets.js', import.meta.url), 'utf8'));
  return w;
}
const tag = (vorTagen) => new Date(Date.now() - vorTagen * 86400000).toISOString().slice(0, 10);

test('ohne Zeitstempel steht „—", niemals „frisch"', () => {
  const w = laden();
  const h = w._pwStilleZelle({ lastTs: null, avgClv: 1, recent: null });
  assert.match(h, /—/);
  assert.doesNotMatch(h, /heute|gestern/, 'eine fehlende Angabe ist keine Aktivität');
  assert.match(h, /01\.09\.2026/, 'und sie sagt, warum sie fehlt');
  assert.equal(w._pwStilleTage(null), null);
  assert.equal(w._pwStilleTage('quatsch'), null, 'unlesbar → unbekannt, nicht 0');
});

test('die Stille wird in Tagen gezählt und eingefärbt', () => {
  const w = laden();
  assert.equal(w._pwStilleTage(tag(20)), 20);
  assert.match(w._pwStilleZelle({ lastTs: tag(0), avgClv: 1 }), /heute/);
  assert.match(w._pwStilleZelle({ lastTs: tag(1), avgClv: 1 }), /gestern/);
  assert.match(w._pwStilleZelle({ lastTs: tag(20), avgClv: 1 }), /20d/);
  // frisch grün, mittel gold, lange still grau — die Farbe trägt dieselbe Aussage wie die Zahl
  assert.match(w._pwStilleZelle({ lastTs: tag(1), avgClv: 1 }), /#3fb950/);
  assert.match(w._pwStilleZelle({ lastTs: tag(30), avgClv: 1 }), /#8b949e/);
});

test('das Fenster vergleicht zuletzt gegen Lebenszeit — und schweigt, wenn es zu dünn ist', () => {
  const w = laden();
  const rec = (n, clv) => Array.from({ length: n }, () => [tag(1), clv, 1]);
  // unter 5 Auflösungen: keine Aussage
  assert.doesNotMatch(w._pwStilleZelle({ lastTs: tag(1), avgClv: 2, recent: rec(4, 0) }), /[▲▼]/);
  // zuletzt schlechter als über die ganze Historie → ▼
  assert.match(w._pwStilleZelle({ lastTs: tag(1), avgClv: 2.0, recent: rec(6, 0.1) }), /▼/);
  // zuletzt besser → ▲
  assert.match(w._pwStilleZelle({ lastTs: tag(1), avgClv: -1.0, recent: rec(6, 0.5) }), /▲/);
});

test('die Rangliste reicht lastTs und recent überhaupt durch', () => {
  // Sonst wäre die Anzeige gebaut, könnte aber nie feuern ([[project_betfair_norm_league_basis]]).
  const w = laden();
  const scores = { '0xa': { n: 40, wins: 24, clvSumPP: 40, usd: 400000, pnl: 1000,
                            lastTs: tag(3), recent: [[tag(3), 1.0, 1]] } };
  const [r] = w._pwRankRowsPnl(scores);
  assert.ok(r, 'Wallet muss in der Rangliste landen');
  assert.equal(r.lastTs, tag(3));
  assert.equal(r.recent.length, 1);
  const [c] = w._pwRankRowsClv(scores);
  assert.equal(c.lastTs, tag(3), 'auch die CLV-Rangliste trägt den Stempel');
});

test('beide Tabellen haben die Spalte', () => {
  const SRC = readFileSync(new URL('../../poly-wallets.js', import.meta.url), 'utf8');
  // Aufruf-Stellen zaehlen, nicht die Definition mit — sonst zaehlt `function _pwStilleZelle(r){` mit.
  assert.equal((SRC.match(/\+ _pwStilleZelle\(r\) \+/g) || []).length, 2, 'P&L- und CLV-Rangliste');
  assert.equal((SRC.match(/>zuletzt<\/th>/g) || []).length, 2, 'und beide Spaltenköpfe');
});
