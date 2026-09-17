// tests/frontend/wallet-tor-vergleich.test.mjs — 17.09.2026
//
// Lucas, zur Kontrollgruppen-Kachel: „schaut ok aus oder?"
//
// Sah ok aus und war es nicht. Die Kachel entschied am Vorzeichen der Differenz zweier ROIs
// („Das Wallet-Tor trägt nicht: ohne Wallet-Nachweis +1,5 pp höher") und schrieb im selben
// Absatz, dass ein Unterschied zwischen zwei Punktschätzern selbst nur einer ist. Dazu kam die
// verunreinigte Kontrolle: 12 der 124 Kontroll-Plays waren gesendet worden (E-Sport-Ausnahme),
// 11 davon gewonnen — bereinigt dreht das Vorzeichen.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const PW = new URL('../../poly-wallets.js', import.meta.url);
const RAWJSON = new URL('../../raw-json.js', import.meta.url);
function win() {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="polyWalletsPanel"></div></body>',
    { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  w.eval(readFileSync(RAWJSON, 'utf8'));
  w.eval(readFileSync(PW, 'utf8'));
  return w;
}
const MIT = { n: 204, roi: 0.0578, roiUg: -0.0239 };
const OHNE = { n: 112, roi: 0.0453, roiUg: -0.0790 };
function cache(w, walletTor) {
  w._pwTestSetCache({ shortlistTrack: { agg: { public: MIT, publicOhneWallet: OHNE, walletTor } } });
}

test('das Urteil kommt aus dem Band, nicht aus dem Vorzeichen', () => {
  const w = win();
  cache(w, { diffPP: 1.25, lo: -13.33, hi: 16.23, urteil: 'nicht entschieden' });
  const h = w._pwWalletGateVergleich(MIT, OHNE);
  assert.match(h, /nicht entschieden/);
  assert.match(h, /90-%-Band \[-13\.33, \+16\.23\] pp/);
  assert.ok(!/trägt<\/b>:/.test(h), 'ein Band um die Null ist kein „trägt"');
});

test('ein Band ganz über null darf „trägt" sagen', () => {
  const w = win();
  cache(w, { diffPP: 6.0, lo: 1.2, hi: 11.0, urteil: 'traegt' });
  assert.match(w._pwWalletGateVergleich(MIT, OHNE), /Das Wallet-Tor <b>trägt<\/b>/);
});

test('und ein Band ganz unter null „trägt nicht"', () => {
  const w = win();
  cache(w, { diffPP: -6.0, lo: -11.0, hi: -1.2, urteil: 'traegt nicht' });
  assert.match(w._pwWalletGateVergleich(MIT, OHNE), /trägt <b>nicht<\/b>/);
});

test('ohne Band aus dem Produzenten wird kein Urteil erfunden', () => {
  const w = win();
  w._pwTestSetCache({ shortlistTrack: { agg: { public: MIT, publicOhneWallet: OHNE } } });
  const h = w._pwWalletGateVergleich(MIT, OHNE);
  assert.match(h, /ohne Band ist das kein Urteil/);
  assert.ok(!/trägt/.test(h));
});

test('die Kachel sagt, dass die Kontrolle nur Nicht-Gesendete enthält', () => {
  // Genau die Behauptung, die am 17.09. für 12 von 124 Plays falsch war.
  const w = win();
  cache(w, { diffPP: 1.25, lo: -13.33, hi: 16.23, urteil: 'nicht entschieden' });
  assert.match(w._pwWalletGateVergleich(MIT, OHNE), /NICHT gesendet/);
});

test('eine zu dünne Kontrollgruppe bleibt eine Sammelmeldung', () => {
  const w = win();
  cache(w, { diffPP: null, lo: null, hi: null, urteil: 'zu duenn' });
  assert.match(w._pwWalletGateVergleich(MIT, { n: 8, roi: 0.1 }), /sammelt noch/);
});
