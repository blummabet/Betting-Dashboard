// tests/frontend/pw-track-je-sportart.test.mjs — Track-Record je Block nach Sportart (04.10.2026,
// Lucas: „die Sportarten auch anzeigen darunter — dann sieht man die Stats besser").
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const ROOT = new URL('../../', import.meta.url);
function fenster() {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="polyWalletsPanel"></div></body>',
    { url: 'https://test.local/', runScripts: 'outside-only' });
  dom.window.fetch = () => Promise.resolve({ ok: false, json: () => Promise.resolve(null) });
  dom.window.eval(readFileSync(new URL('raw-json.js', ROOT), 'utf8'));
  dom.window.eval(readFileSync(new URL('poly-wallets.js', ROOT), 'utf8'));
  return dom.window;
}
const W = fenster();

test('Chips je Sportart mit ROI und Untergrenze, unter 30 „sammelt"', () => {
  const h = W._pwCatChips({
    'E-Sport': { n: 445, roi: 0.081, roiUg: 0.033 },
    'Fußball': { n: 12, roi: -0.05, roiUg: -0.4 },
    'Leer': { n: 0 },
  });
  assert.match(h, /E-Sport/);
  assert.match(h, /\+8\.1%/);
  assert.match(h, /UG \+3\.3%/);
  assert.match(h, /Fußball[\s\S]*sammelt/);
  assert.ok(!h.includes('Leer'), 'Sportart ohne Plays wird nicht gezeigt');
});

test('ohne Daten keine leere Zeile', () => {
  assert.equal(W._pwCatChips({}), '');
  assert.equal(W._pwCatChips(undefined), '');
});

test('Track-Record zeigt die Chips unter Bespielbar, Public und Kontrolle', () => {
  const agg = { bettable: { n: 10 }, public: { n: 5 }, publicOhneWallet: { n: 3 },
    bettableByCat: { Tennis: { n: 10, roi: 0.02 } }, publicByCat: { 'E-Sport': { n: 5, roi: -0.1 } },
    publicOhneWalletByCat: { 'Fußball': { n: 3, roi: 0.3 } }, byConv: {} };
  const h = W._pwTrackRecord({ agg, settled: [{ key: 'x' }], open: {} });
  assert.equal((h.match(/Je Sportart:/g) || []).length, 3);
});
