// tests/frontend/cockpit-unbelegt.test.mjs — 21.09.2026
//
// 🔴 Lucas, 01:04 UTC: „Das kam. Aber auf poly wurde nicht gesetzt." Die Toluca-Zeile stand mit
// `result: LOSS, pnl: -5.00` im Buch; das Wallet hatte sich sieben Stunden nicht bewegt. Zwei
// solche Zeilen, zusammen 10 $ — die angezeigte Bilanz war um diesen Betrag schlechter als die
// Wirklichkeit.
//
// Das Urteil faellt dort, wo die Zahl entsteht (`wallet_abgleich.entbuchen` schreibt
// `bilanz: false`). Diese Flaeche hat es nur zu LESEN — sie darf die Regel nicht ein zweites
// Mal nachbauen. Geprueft wird hier also nur: faellt so eine Zeile aus Zaehler UND Nenner, und
// wird sie trotzdem genannt?
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const SRC = readFileSync(new URL('../../polymarket-tab.js', import.meta.url), 'utf8');
const RAW = readFileSync(new URL('../../raw-json.js', import.meta.url), 'utf8');

function laden() {
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: false });
  w.eval(RAW);
  w.eval(SRC);
  return w;
}

const gewonnen = { result: 'WIN', status: 'won', stake: 5, pnl: 3.93, resolvedAt: '2026-09-20T10:00:00Z' };
const verloren = { result: 'LOSS', status: 'lost', stake: 5, pnl: -5, resolvedAt: '2026-09-20T11:00:00Z' };
const unbelegt = { result: 'UNBELEGT', status: 'unbelegt', stake: 5, pnl: 0, bilanz: false,
                   pnlGebucht: -5, resolvedAt: '2026-09-21T01:04:00Z' };

test('eine unbelegte Zeile faellt aus dem Zaehler', () => {
  const w = laden();
  const b = w._ptBilanz([gewonnen, verloren, unbelegt]);
  assert.equal(Math.round(b.pnl * 100) / 100, -1.07);   // 3.93 - 5, NICHT -6.07
});

test('… und aus dem Nenner', () => {
  // Ein Einsatz, der nie floss, verwaessert auch die Rendite nicht.
  const w = laden();
  assert.equal(w._ptBilanz([gewonnen, verloren, unbelegt]).stake, 10);
});

test('sie zaehlt weder als Sieg noch als Niederlage noch als Void', () => {
  const w = laden();
  const b = w._ptBilanz([gewonnen, verloren, unbelegt]);
  assert.equal(b.w, 1);
  assert.equal(b.l, 1);
  assert.equal(b.v, 0);
});

test('aber sie wird gezaehlt und genannt', () => {
  // ⭐ Wer sie stumm wegwirft, verliert den Vorfall: in drei Wochen weiss niemand mehr, dass es
  // ihn gab. Eine Luecke, die sich selbst erledigt, hinterlaesst sonst keine Statistik.
  const w = laden();
  const b = w._ptBilanz([gewonnen, verloren, unbelegt]);
  assert.equal(b.u, 1);
  assert.equal(b.n, 2, 'n ist die Zahl, auf der die Rendite rechnet');
  assert.equal(b.nAlle, 3, 'nAlle ist, was dastand');
});

test('ohne solche Zeilen aendert sich nichts', () => {
  // Die Gegenprobe: eine Regel, die immer zieht, waere hier genauso gruen.
  const w = laden();
  const b = w._ptBilanz([gewonnen, verloren]);
  assert.equal(Math.round(b.pnl * 100) / 100, -1.07);
  assert.equal(b.stake, 10);
  assert.equal(b.u, 0);
  assert.equal(b.n, 2);
});

test('`bilanz: true` oder fehlend zaehlt normal — nur das ausdrueckliche false zieht', () => {
  const w = laden();
  assert.equal(w._ptBilanz([{ ...verloren, bilanz: true }]).pnl, -5);
  assert.equal(w._ptBilanz([{ ...verloren, bilanz: undefined }]).pnl, -5);
  assert.equal(w._ptBilanz([{ ...verloren, bilanz: 0 }]).pnl, -5, '0 ist nicht false');
});

test('eine entbuchte Zeile ist terminal, also nicht wieder offen', () => {
  // Die Falle beim Bauen: ein neuer Status, den die Terminal-Liste nicht kennt, macht die Zeile
  // wieder „offen" — und sie belegt den Exposure-Deckel, obwohl nie Geld floss.
  const w = laden();
  assert.equal(w._ptIstOffen(unbelegt), false);
  assert.equal(w._ptIstOffen({ status: 'unbelegt', stake: 5 }), false,
    'der Status allein muss reichen');
});

test('sie steht in der abgerechneten Liste, nicht bei den offenen', () => {
  const w = laden();
  const s = w._ptAbgerechnet([gewonnen, unbelegt, { status: 'placed', stake: 5 }]);
  assert.equal(s.length, 2);
});
