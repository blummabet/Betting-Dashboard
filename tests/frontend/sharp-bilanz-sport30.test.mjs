// 🔴 10.10.2026 (Übersicht-Check): „Arsenal FC · 🔎 vielversprechende Wallets (noch nicht belegt)
// (4 Wallets, zusammen 72/101, 71% · -$48K)". Die -$48K waren Polymarkets Lebensbilanz über
// Wahlen, Krypto, alles — seit 29.08. ausdrücklich KEIN Beleg. Das Gate urteilt nach dem
// 30-Tage-Sport-Profit; derselbe Satz Wallets stand dort bei +$42,8K (eine allein -$42,3K
// Lebenszeit, +$39,9K Sport). Ein Satz neben einer Zahl, die das Gegenteil sagt.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const SRC = readFileSync(new URL('../../poly-wallets.js', import.meta.url), 'utf8');
const KEY = 'epl-ars-lee-2026-10-10';
// Die vier echten Wallets vom 10.10. (n, wins, Lebensbilanz, 30-T-Sport)
const W = [
  ['0xa', 38, 28, -42278, 39943.61], ['0xb', 23, 18, -515, 274.48],
  ['0xc', 21, 14, -2020, 2545.13], ['0xd', 19, 12, -3072, 21.69],
];
function laden() {
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve(null) });
  w.eval(SRC);
  const scores = {}, open = [];
  for (const [id, n, wins, pnl, g] of W) {
    scores[id] = { n, wins, clvSumPP: 0, pnl, fenster30: { gewinn: g, nGeld: n } };
    open.push({ key: KEY, wallet: id, side: 'Arsenal FC', usd: 1000 });
  }
  w.eval('_pwCache = ' + JSON.stringify({ walletTrack: { scores, open } }) + ';');
  return w;
}

test('die Seite trägt den 30-Tage-Sport-Profit, nach dem das Gate urteilt', () => {
  const w = laden();
  const sh = w._pwSharpInfoForKey(KEY);
  assert.ok(sh, 'Wallets erkannt');
  assert.ok(Math.abs(sh.sport30 - 42784.91) < 0.01, 'Summe der gemessenen 30-T-Sport-Profite');
  assert.ok(sh.pnl < 0, 'die Lebensbilanz bleibt intern erhalten');
});

test('der Satz zeigt den Sport-Profit, nicht die Lebensbilanz', () => {
  assert.match(SRC, /'30 T Sport '/);
  assert.doesNotMatch(SRC, /const pnlTxt=\(sh\.pnl>=0/, 'die Lebensbilanz steht nicht mehr im Grund');
});
