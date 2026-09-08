// tests/frontend/poly-datensatz-banner.test.mjs — 08.09.2026
//
// Lucas: „schau dir die ganzen Whales an … ob das alles wirklich sauber umgesetzt ist."
//
// Zwei Datensätze im Poly-Menü zeigen ohne ein Wort etwas anderes, als der Reiter verspricht:
//   · 🏆 WM 2026 — `wm_poly_wallets.json` trägt den Stempel 19.07.2026, also 50 Tage alt.
//   · 🎮 E-Sport — der Tab lädt drei Dateien (Abrechnung, Wallet-Ledger, Geld-Genauigkeit),
//     die für diesen Datensatz gar nicht produziert werden. Die Abschnitte bleiben leer.
//
// Ein leerer Abschnitt und ein nie gebauter Abschnitt sehen gleich aus — dieser Unterschied
// muss dastehen, sonst sucht man den Fehler bei sich.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const PW = new URL('../../poly-wallets.js', import.meta.url);

function load() {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="polyWalletsPanel"></div></body>',
    { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve(null) });
  w.eval(readFileSync(PW, 'utf8'));
  return w;
}

function cache(w, over) {
  w._pwTestSetCache(Object.assign({
    prices: { generatedAt: new Date().toISOString() },
    wallets: { updatedAt: new Date().toISOString() },
    settlement: {}, ledger: {}, moneyAcc: {},
  }, over || {}));
}

test('frischer, vollständiger Datensatz → kein Banner', () => {
  const w = load(); cache(w);
  assert.equal(w._pwQuellenBanner(), '');
});

test('50 Tage alter Datensatz sagt sein Alter — in Tagen, nicht in Stunden', () => {
  const w = load();
  const alt = new Date(Date.now() - 50 * 24 * 3600e3).toISOString();
  cache(w, { prices: { generatedAt: alt }, wallets: { updatedAt: alt } });
  const h = w._pwQuellenBanner();
  assert.match(h, /vor 50 Tagen/);
  assert.match(h, /pw-dswarn-err/, 'ab zwei Tagen ist das kein Hinweis mehr, sondern ein Befund');
});

test('fehlende Dateien werden als NIE GEBAUT benannt, nicht als leer', () => {
  const w = load();
  cache(w, { settlement: null, ledger: null, moneyAcc: null });
  const h = w._pwQuellenBanner();
  assert.match(h, /Abrechnung/); assert.match(h, /Wallet-Ledger/); assert.match(h, /Geld-Genauigkeit/);
  assert.match(h, /nie gebaut/, 'der Unterschied zu „gerade nichts da" fehlt');
});

test('kein Zeitstempel behauptet kein Alter', () => {
  const w = load();
  cache(w, { prices: {}, wallets: {} });
  assert.equal(w._pwQuellenBanner(), '', 'ohne Stempel wird nichts geraten');
});

test('das Banner hängt an den Datensatz-Reitern, nicht an einer Ansicht', () => {
  const src = readFileSync(PW, 'utf8');
  assert.match(src, /_pwDatasetTabs\(\)[\s\S]{0,400}_pwQuellenBanner\(\)/,
    'sonst sieht man es nur in einem der zehn Views');
});
