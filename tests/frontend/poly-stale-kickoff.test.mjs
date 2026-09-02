// tests/frontend/poly-stale-kickoff.test.mjs
// 28.07.2026 — Boyer/Tomic-Bug: hoursToKickoff in der Broad-Close-Datei ist auf den Freeze-Zeitpunkt
// (capturedAt) eingefroren. Läuft ein Spiel (Walkover, nie resolved) und der Runner steht, zeigt es
// ewig „<1h" und feuert weiter Verdikte in „Heute wetten" / „Chancen" / „Großes Geld".
// Fix: echten Rest bis Anpfiff aus capturedAt rekonstruieren (_pwRealHtk) + fertige Spiele filtern.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const PW = new URL('../../poly-wallets.js', import.meta.url);
function win() {
  const dom = new JSDOM('<!DOCTYPE html><body></body>',
    { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const { window: w } = dom;
  w.eval(readFileSync(PW, 'utf8'));
  return w;
}
const H = 3.6e6;
const iso = (msAgo) => new Date(Date.now() - msAgo).toISOString();

test('_pwRealHtk rekonstruiert echten Rest bis Anpfiff aus capturedAt', () => {
  const w = win();
  const stale = { hoursToKickoff: 0.97, capturedAt: iso(25 * H) }; // vor 25h eingefroren
  const fresh = { hoursToKickoff: 2, capturedAt: iso(0) };
  assert.ok(w._pwRealHtk(stale) < -20, 'stale muss stark negativ sein');
  assert.ok(Math.abs(w._pwRealHtk(fresh) - 2) < 0.1, 'fresh ≈ 2h');
  assert.equal(w._pwKoStale(stale), true);
  assert.equal(w._pwKoStale(fresh), false);
  assert.equal(w._pwRealHtk({ hoursToKickoff: 5 }), 5, 'ohne capturedAt → roher Wert');
  assert.equal(w._pwRealHtk({}), null, 'ohne htk → null');
});

// Preis-Move +10pp auf Seite A, Steigung zieht weiter → Steam ▲ (liefert das Shortlist-Signal)
// 02.09.2026 (Lucas-Audit): die Snapshots brauchen jetzt `ts`. _pwMoveFor misst seit dem Audit
// über ein festes 6h-Fenster statt gegen den ältesten Punkt und liest die Richtung aus der
// Steigung über mindestens vier Punkte — nicht mehr aus einem einzelnen Tick. Ein Snapshot ohne
// Zeitstempel fällt damit aus dem Fenster, und das ist richtig so: ohne Zeit kein Tempo.
const steamHist = () => [0.40, 0.44, 0.47, 0.50].map((a, i) => ({
  ts: new Date(Date.now() - (180 - i * 45) * 60000).toISOString(),
  p: { A: a, B: 1 - a },
}));
const mkt = (capMsAgo, htk) => ({
  league: 'TENNIS', shares: { A: 60000, B: 40000 }, prices: { A: 0.5, B: 0.5 },
  totalUsd: 133000, hoursToKickoff: htk, capturedAt: iso(capMsAgo),
});

test('_pwShortlist blendet fertige (stale-kickoff) Spiele aus, frische bleiben', () => {
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window;
  const cache = { broadHist: { 'atp-fresh-x': steamHist(), 'atp-stale-boyer': steamHist() }, moneyBroad: {} };
  // _pwCache ist ein top-level `let` — nur eine Zuweisung IM SELBEN eval wie die Datei trifft die
  // lexikalische Bindung (ein zweiter eval-Aufruf liefe in eigenem Scope → _pwMoveFor bliebe blind).
  w.eval(readFileSync(PW, 'utf8') + '\n_pwCache = ' + JSON.stringify(cache) + ';');
  const live = {
    'atp-fresh-x': mkt(0, 2),           // frisch, Anpfiff in 2h
    'atp-stale-boyer': mkt(25 * H, 0.97), // vor 25h eingefroren → Spiel längst durch
  };
  const html = w._pwShortlist(live);
  assert.ok(html.includes('atp-fresh-x'), 'frischer Markt muss in der Shortlist stehen (Kontroll-Signal)');
  assert.ok(!html.includes('atp-stale-boyer'), 'stale-kickoff-Markt darf NICHT erscheinen');
});

test('_pwShortlist zeigt Einstiegspreis-Spalte + hebt staerksten Play hervor', () => {
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window;
  const cache = { broadHist: { 'atp-fresh-x': steamHist() }, moneyBroad: {} };
  w.eval(readFileSync(PW, 'utf8') + '\n_pwCache = ' + JSON.stringify(cache) + ';');
  const html = w._pwShortlist({ 'atp-fresh-x': mkt(0, 2) });   // Preis A=0.5 -> 50c, einziger Play -> Top
  assert.match(html, /<th>Einstieg<\/th>/, 'Einstieg-Spalte im Kopf');
  assert.match(html, /50¢/, 'Einstiegspreis der empfohlenen Seite');
  assert.match(html, /⭐/, 'staerkster Play markiert');
});

test('_pwMoneyLive filtert stale-kickoff ebenfalls raus', () => {
  const w = win();
  const live = {
    'atp-fresh-y': mkt(0, 3),
    'atp-stale-tomic': mkt(30 * H, 0.5),
  };
  const html = w._pwMoneyLive(live);
  assert.ok(html.includes('atp-fresh-y'), 'frischer Markt bleibt in Großes Geld');
  assert.ok(!html.includes('atp-stale-tomic'), 'stale-kickoff-Markt raus aus Großes Geld');
});
