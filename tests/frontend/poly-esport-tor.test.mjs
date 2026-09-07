// tests/frontend/poly-esport-tor.test.mjs — 07.09.2026
//
// Lucas: „was meinst du bei E-Sport? was würdest du da ändern?"
//
// Gemessen an 621 abgerechneten Plays, getrennt nach dem, was das Public-Tor DURCHLÄSST und was
// es ABWEIST — und zwar nur innerhalb E-Sport:
//
//     E-Sport, das durchkommt       n= 69   Treffer 78,3 %   Break-even 73,2 %   +5,1 pp
//     E-Sport, das abgewiesen wird  n=100   Treffer 71,0 %   Break-even 66,0 %   +5,0 pp
//
// Zwei disjunkte Gruppen, exakt derselbe Vorsprung. Die Wallet-Bedingung trennt bei E-Sport
// nichts — sie kostet nur Volumen. Rückgerechnet hätte die Regel 89 Plays mehr gebracht:
// 75,3 % Treffer, +113,01 EUR, ROI +12,7 %, Untergrenze +1,0 %.
//
// Diese Datei hält fest, dass die Lockerung GENAU dort greift und nirgends sonst. Ein Tor, das
// versehentlich auch Fußball durchlässt, wäre teurer als eines, das zu streng ist.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const PW = new URL('../../poly-wallets.js', import.meta.url);
const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'https://example.com/', runScripts: 'outside-only' });
dom.window.eval(readFileSync(PW, 'utf8'));
const W = dom.window;

const SHARP = { n: 10, hit: 0.70, grade: 2 };
const basis = (o) => ({ conv: 6, moneyPct: 0.70, ...o });

test('E-Sport kommt ohne Wallet-Nachweis durch — ab der Preisschwelle', () => {
  assert.strictEqual(W._pwTermIsPublic(basis({ league: 'CS2 Blast', price: 0.62 })), true);
  assert.strictEqual(W._pwTermIsPublic(basis({ league: 'CS2 Blast', price: 0.55 })), true,
    'die Schwelle ist einschließend gemeint');
});

test('Außenseiter unter der Schwelle bleiben draußen', () => {
  // 40,5 % Treffer gegen 46,9 % Break-even — in JEDER Kategorie Gift.
  assert.strictEqual(W._pwTermIsPublic(basis({ league: 'CS2 Blast', price: 0.48 })), false);
});

test('die Lockerung gilt NUR für E-Sport', () => {
  assert.strictEqual(W._pwTermIsPublic(basis({ league: 'EPL', price: 0.62 })), false,
    'Fußball ohne Wallet-Nachweis darf nicht durchrutschen');
  assert.strictEqual(W._pwTermIsPublic(basis({ league: 'ATP Wien', price: 0.62 })), false);
  assert.strictEqual(W._pwTermIsPublic(basis({ league: 'MLB', price: 0.62 })), false);
});

test('mit Wallet-Nachweis bleibt alles wie vorher', () => {
  assert.strictEqual(W._pwTermIsPublic(basis({ league: 'EPL', price: 0.62, sharp: SHARP })), true);
});

test('die übrigen Bedingungen gelten für E-Sport unverändert weiter', () => {
  // Gelockert wurde die WALLET-Bedingung, nicht das Tor. Conviction und Geld-Mehrheit bleiben.
  assert.strictEqual(W._pwTermIsPublic({ conv: 2, moneyPct: 0.70, league: 'CS2 Blast', price: 0.62 }), false);
  assert.strictEqual(W._pwTermIsPublic({ conv: 6, moneyPct: 0.40, league: 'CS2 Blast', price: 0.62 }), false);
});

test('ohne Preis wird nichts behauptet', () => {
  // Fehlende Information ist keine Erlaubnis — ein Play ohne Preis darf nicht durch die
  // Lockerung rutschen, nur weil er E-Sport ist.
  assert.strictEqual(W._pwTermIsPublic(basis({ league: 'CS2 Blast' })), false);
  assert.strictEqual(W._pwTermIsPublic(basis({ league: 'CS2 Blast', price: null })), false);
  assert.strictEqual(W._pwTermIsPublic(basis({ league: 'CS2 Blast', price: 'x' })), false);
});

test('gesperrte Kategorien bleiben gesperrt', () => {
  // US-Sport und Kampfsport laufen über _pwBetBlocked, nicht über dieses Tor — die Sperre
  // darf von der Lockerung nicht berührt werden. (48 abgerechnete US-Sport-Plays: 37,5 %
  // Treffer gegen 59,3 % Break-even. Sie werden mitgeschrieben, nie gespielt.)
  assert.strictEqual(W._pwBetBlocked({ league: 'MLB' }), true);
  assert.strictEqual(W._pwBetBlocked({ league: 'UFC' }), true);
  assert.strictEqual(W._pwBetBlocked({ league: 'CS2 Blast' }), false);
});

test('die Kontrollgruppe misst weiter das, was sie messen soll', () => {
  // `_pwTermIsPublicOhneWallet` ist die Schattengruppe: Public-Rest erfüllt, Wallet NICHT.
  // Sie muss unabhängig von der E-Sport-Lockerung bleiben, sonst misst sie ab heute etwas
  // anderes als gestern und die Reihe bricht.
  assert.strictEqual(W._pwTermIsPublicOhneWallet(basis({ league: 'CS2 Blast', price: 0.62 })), true,
    'ein E-Sport-Play ohne Wallet gehört weiterhin in die Kontrollgruppe');
  assert.strictEqual(W._pwTermIsPublicOhneWallet(basis({ league: 'EPL', price: 0.62, sharp: SHARP })), false);
});

test('die Schwelle steht als benannte Konstante, nicht im Ausdruck', () => {
  const src = readFileSync(PW, 'utf8');
  assert.match(src, /const PW_ESPORT_FREI_AB_PREIS = 0\.55;/,
    'eine gesetzte Schwelle muss auffindbar sein — sie ist angepasst, nicht gemessen');
  assert.match(src, /ANGEPASST, nicht gefunden/,
    'und sie muss als solche beschriftet sein');
});
