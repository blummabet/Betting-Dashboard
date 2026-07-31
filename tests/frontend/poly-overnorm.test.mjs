// tests/frontend/poly-overnorm.test.mjs — Polymarket ×-Norm (30.07.2026, Lucas).
// Prüft: Gesamt-Volumen- UND Zufluss-Variante, Stage×Sportart-Median, Highlight ab ×1.6/×2.6,
// und dass zu kleine Vergleichsgruppen (<4) KEIN Ratio liefern.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const PW = new URL('../../poly-wallets.js', import.meta.url);
function boot() {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="polyWalletsPanel"></div></body>',
    { url: 'https://x.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window;
  w.eval(readFileSync(PW, 'utf8'));
  return w;
}
// vol = Gesamt-Volumen, inflow = Δ seit letztem Lauf. Kein capturedAt → htk = roh (nicht stale).
function build(spec) {
  const live = {}, hist = {};
  spec.forEach(([id, vol, inflow]) => {
    const k = 'soccer-' + id + '-2026';
    live[k] = { league: 'SOCCER', totalUsd: vol, hoursToKickoff: 10,
      shares: { ['Home' + id]: vol * 0.6, ['Away' + id]: vol * 0.4 }, prices: {} };
    hist[k] = [{ v: vol - inflow, ts: 't1' }, { v: vol, ts: 't2' }];
  });
  return { live, hist };
}

test('×-Norm: großes Spiel über Norm — Gesamt-Volumen & Zufluss, rot markiert', () => {
  const w = boot();
  const { live, hist } = build([
    ['a', 20000, 10000], ['b', 20000, 10000], ['c', 20000, 10000],
    ['d', 20000, 10000], ['e', 20000, 10000], ['big', 120000, 60000],
  ]);
  const html = w._pwOverNorm(live, hist);
  assert.match(html, /×-Norm/, 'Sektion da');
  assert.match(html, /Gesamt-Volumen über Norm/);
  assert.match(html, /Zufluss über Norm/);
  assert.match(html, /×6\.0 Norm/, 'großes Spiel = 6× Median');
  assert.match(html, /pwn-over2/, 'stark → rot umrandet');
  assert.match(html, /Homebig/, 'führende Seite des großen Spiels sichtbar');
});

test('×-Norm: Stage-Buckets korrekt (live / soon / pre)', () => {
  const w = boot();
  assert.strictEqual(w._pwNormStage({ hoursToKickoff: -0.5 }), 'live');
  assert.strictEqual(w._pwNormStage({ hoursToKickoff: 2 }), 'soon');
  assert.strictEqual(w._pwNormStage({ hoursToKickoff: 20 }), 'pre');
});

test('×-Norm: zu wenige Vergleichsspiele → kein Ratio, ruhiger Hinweis', () => {
  const w = boot();
  const { live, hist } = build([['a', 20000, 5000], ['big', 200000, 90000]]);
  const html = w._pwOverNorm(live, hist);
  assert.doesNotMatch(html, /pwn-over2|Norm<\/span>/, 'kein Highlight bei n<4');
  assert.match(html, /im üblichen Rahmen/, 'ruhiger Hinweis statt Fehlalarm');
});

test('×-Norm: Zufluss = Δ der letzten zwei History-Punkte', () => {
  const w = boot();
  assert.strictEqual(w._pwInflow('x', { x: [{ v: 1000 }, { v: 4500 }] }), 3500);
  assert.strictEqual(w._pwInflow('x', { x: [{ v: 1000 }] }), null, '<2 Punkte → null');
});
