// tests/frontend/poly-wallet-profit.test.mjs — 22.09.2026
//
// 🔴 Lucas: „Mir ist da wirklich wichtig, dass wir den Profit und den ROI der letzten sieben und
// 30 Tage auch mit tracken. Du weisst ja, mit CLV bin ich jetzt nicht so der grösste Fan. Ich
// will halt immer den Profit haben."
//
// Die Rangliste zeigte CLV-UG, Ø CLV, Treffer, n, Einsatz, Ø/Wette und Polys Lebensbilanz. Die
// einzige Geld-Zahl darin schleppt Wahlen und Krypto mit und sagt über Sport nichts.
//
// Gerechnet wird hier NICHTS: `gewinn`, `einsatz` und `roi` kommen fertig aus poly_money_broad.
// Geprüft wird nur, dass die Fläche sie liest, richtig färbt und ihre Lücken benennt.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const PW = new URL('../../poly-wallets.js', import.meta.url);

function laden() {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="polyWalletsPanel"></div></body>',
    { url: 'https://example.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: false });
  w.eval(readFileSync(PW, 'utf8'));
  return w;
}

const f = (o) => Object.assign({ n: 9, nGeld: 9, gewinn: 7500, einsatz: 5000, roi: 1.5 }, o);

test('der Profit steht in der Zelle, nicht der CLV', () => {
  const h = laden()._pwGeldZelle(f(), '7 Tage');
  assert.match(h, /7\.5K|7500/);
  assert.doesNotMatch(h, /pp/, 'das ist die Geld-Spalte, nicht die CLV-Spalte');
});

test('der ROI steht darunter', () => {
  const h = laden()._pwGeldZelle(f(), '7 Tage');
  assert.match(h, /\+150%/);
});

test('ein Verlust ist rot und negativ', () => {
  const h = laden()._pwGeldZelle(f({ gewinn: -320, roi: -0.064 }), '30 Tage');
  assert.match(h, /#f85149/);
  assert.match(h, /-6%/);
});

test('nicht gemessen ist ein Strich, keine Null', () => {
  // ⭐ Der wichtigste Fall. „0 $ Gewinn" und „wir haben nichts gemessen" sind zwei verschiedene
  // Auskünfte, und die zweite als die erste zu zeigen ist genau die Fehlerklasse, die dieses
  // Repo sonst überall jagt: fehlende Information als harmloser Default.
  for (const x of [null, undefined, {}, { n: 9, nGeld: 0 }]) {
    const h = laden()._pwGeldZelle(x, '7 Tage');
    assert.match(h, /—/);
    assert.doesNotMatch(h, /\$0/);
    assert.match(h, /nicht gemessen, nicht null/);
  }
});

test('eine Teil-Abdeckung steht im Tooltip', () => {
  const h = laden()._pwGeldZelle(f({ n: 30, nGeld: 12 }), '30 Tage');
  assert.match(h, /aus 12 von 30/);
});

test('volle Abdeckung sagt nichts dazu', () => {
  const h = laden()._pwGeldZelle(f({ n: 30, nGeld: 30 }), '30 Tage');
  assert.doesNotMatch(h, /aus 30 von 30/);
});

test('ein Gewinn ohne ROI zeigt trotzdem den Gewinn', () => {
  const h = laden()._pwGeldZelle(f({ roi: null }), '7 Tage');
  assert.match(h, /7\.5K|7500/);
  assert.doesNotMatch(h, /%<\/div>/);
});

test('die Spalten stehen in der Rangliste', () => {
  const src = readFileSync(PW, 'utf8');
  assert.match(src, /Profit 7T/);
  assert.match(src, /Profit 30T/);
  // Und Polys Lebensbilanz bleibt daneben stehen, klar als Kontext beschriftet — sie ersetzt
  // den Sport-Profit nicht und wird von ihm nicht ersetzt.
  assert.match(src, /Wahlen, Krypto inklusive/);
});

test('die Fläche rechnet den Profit nicht selbst', () => {
  // Eine zweite Rechnung neben der ersten ist in diesem Repo schon dreimal auseinandergelaufen.
  const zelle = readFileSync(PW, 'utf8').split('function _pwGeldZelle')[1].split('\nfunction ')[0];
  assert.doesNotMatch(zelle, /lastPrice|entryPrice|\/ *entry/,
    'die Zelle darf nur lesen, was der Produzent gerechnet hat');
});
