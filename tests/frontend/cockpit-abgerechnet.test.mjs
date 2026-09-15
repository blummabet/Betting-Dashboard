// tests/frontend/cockpit-abgerechnet.test.mjs — 15.09.2026
//
// Lucas: „abgerechnete positionen sind nicht im cockpit / nur aktive scheinbar / sollten wir
// aendern oder?" — Eine Flaeche, deren ganzer Zweck der Track Record ist, warf die abgerechnete
// Haelfte weg. Dazu hielt sie eine EIGENE Definition von „offen", naemlich genau die, die am
// 14.09. in Python durch poly_offen.ist_offen ersetzt wurde.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const SRC = readFileSync(new URL('../../polymarket-tab.js', import.meta.url), 'utf8');
const RAW = readFileSync(new URL('../../raw-json.js', import.meta.url), 'utf8');
const PY  = readFileSync(new URL('../../poly_offen.py', import.meta.url), 'utf8');

function laden() {
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: false });
  w.eval(RAW);
  w.eval(SRC);
  return w;
}

const bet = (o = {}) => Object.assign({
  match: 'A vs B', side: 'A', market: 'Heimsieg', stake: 5, polyPrice: 0.5,
  placedAt: '2026-09-14T10:00:00+00:00',
}, o);

test('die Offen-Definition ist die von poly_offen.py — Liste fuer Liste', () => {
  // ⭐ Der Pin. Bewegt sich eine Seite, faellt dieser Test, und dann gehoert die ANDERE
  // nachgezogen — nicht der Test angepasst. Dieselbe Bauart wie bei der Whale-Rangliste.
  const w = laden();
  const pyStatus = [...PY.matchAll(/TERMINAL_STATUS = \{([^}]*)\}/g)][0][1]
    .match(/"([^"]+)"/g).map(x => x.replace(/"/g, '')).sort();
  const pyResult = [...PY.matchAll(/TERMINAL_RESULT = \{([^}]*)\}/g)][0][1]
    .match(/"([^"]+)"/g).map(x => x.replace(/"/g, '')).sort();
  const listen = w._ptTerminalListen();
  assert.deepEqual(listen.status.slice().sort(), pyStatus);
  assert.deepEqual(listen.result.slice().sort(), pyResult);
});

test('eine verkaufte Position ohne soldAt gilt NICHT mehr als offen', () => {
  // 🔴 Genau diese Zeile steht real in wm_auto_bets_placed.json: status "sold", kein soldAt,
  // kein result. Der alte Filter zaehlte sie als offen — das sind die $5,50 Phantom-Exposure.
  const w = laden();
  assert.equal(w._ptIstOffen(bet({ status: 'sold' })), false);
  assert.equal(w._ptIstOffen(bet({ status: 'closed_manual' })), false);
  assert.equal(w._ptIstOffen(bet({ status: 'dry-run' })), false);
});

test('fehlende Information gilt als offen, nicht als abgerechnet', () => {
  // Bei einem Risiko-Deckel ist der harmlose Default „blockiert", nicht „frei".
  const w = laden();
  assert.equal(w._ptIstOffen(bet({ status: 'placed' })), true);
  assert.equal(w._ptIstOffen(bet({})), true);
  assert.equal(w._ptIstOffen(null), false);
});

test('abgerechnete Positionen stehen im Block, neueste zuerst', () => {
  const w = laden();
  const html = w._ptSettledBlock([
    bet({ match: 'Alt', status: 'lost', result: 'LOSS', pnl: -5, resolvedAt: '2026-09-10T00:00:00Z' }),
    bet({ match: 'Neu', status: 'won', result: 'WIN', pnl: 3.93, resolvedAt: '2026-09-14T00:00:00Z' }),
    bet({ match: 'Offen', status: 'placed' }),
  ]);
  assert.match(html, /Neu/);
  assert.match(html, /Alt/);
  assert.doesNotMatch(html, /Offen/, 'eine offene Position gehoert nicht in den Abgerechnet-Block');
  assert.ok(html.indexOf('Neu') < html.indexOf('Alt'), 'nicht nach Datum sortiert');
  assert.match(html, /GEWONNEN/);
  assert.match(html, /VERLOREN/);
});

test('die Bilanzzeile nennt Anzahl, Ausgang und realisiertes Geld', () => {
  const w = laden();
  const html = w._ptSettledBlock([
    bet({ status: 'won', result: 'WIN', pnl: 3.93 }),
    bet({ status: 'won', result: 'WIN', pnl: 1.67 }),
    bet({ status: 'lost', result: 'LOSS', pnl: -5 }),
  ]);
  assert.match(html, /3 · 2W\/1L/);
  assert.match(html, /\+\$0\.60/);
});

test('bei kleiner Stichprobe steht KEINE Rendite da', () => {
  // 🔴 Die wichtigste Regel dieses Blocks. „+39 %" aus drei Zeilen ist Dekoration, und diese
  // Flaeche lebt davon, dass man ihren Zahlen glauben kann.
  const w = laden();
  const html = w._ptSettledBlock([bet({ status: 'won', result: 'WIN', pnl: 3.93 })]);
  assert.match(html, /Rendite erst ab 25 Zeilen/);
  assert.doesNotMatch(html, /Rendite [+-]\d/);
});

test('ab genug Zeilen steht die Rendite da — mit Verweis auf die Untergrenze', () => {
  const w = laden();
  const viele = Array.from({ length: 25 }, () => bet({ status: 'won', result: 'WIN', pnl: 1 }));
  const html = w._ptSettledBlock(viele);
  assert.match(html, /Rendite \+20\.0 %/);
  assert.match(html, /Untergrenze siehe/, 'das Urteil gehoert ins Messungen-Buch, nicht hierher');
});

test('fehlender CLV rendert als Strich, nicht als Null', () => {
  // „keine Schluss-Referenz" ist nicht dasselbe wie „flach" — die Lehre vom 07.08.
  const w = laden();
  const ohne = w._ptSettledBlock([bet({ status: 'won', result: 'WIN', pnl: 1 })]);
  assert.doesNotMatch(ohne, /0\.0pp/);
  const mit = w._ptSettledBlock([bet({ status: 'won', result: 'WIN', pnl: 1, clvPP: 12.0, clvVorsprungPP: 26.0 })]);
  assert.match(mit, /\+12\.0pp/);
  assert.match(mit, /\+26\.0 vs Papier/);
});

test('leerer Block ist kein Fehler', () => {
  assert.match(laden()._ptSettledBlock([]), /Noch nichts abgerechnet/);
});

test('beide Quellen sind in der Zeile unterscheidbar', () => {
  const w = laden();
  const html = w._ptSettledBlock([
    bet({ match: 'S', status: 'won', result: 'WIN', pnl: 1, source: 'auto_shortlist' }),
    bet({ match: 'T', status: 'won', result: 'WIN', pnl: 1, source: 'auto' }),
  ]);
  assert.match(html, /🔥/);
  assert.match(html, /🤖/);
});

test('das Cockpit haengt den Block wirklich ein', () => {
  // ⭐ Gegenprobe an der Nahtstelle: sonst waere der Block gebaut und unsichtbar.
  assert.match(SRC, /\$\{_ptSettledBlock\(bets\)\}/, 'der Block wird nirgends gerendert');
  assert.doesNotMatch(SRC, /bets\.filter\(b => !b\.resolved/, 'der alte Offen-Filter lebt noch');
});
