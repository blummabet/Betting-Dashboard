// tests/frontend/poly-wallet-kickoff-gate.test.mjs — 03.08.2026 (Lucas: „schon vorbei, steht aber
// noch als aktuell"). Audit-Fix: die Poly-Wallet-Views filtern schon angepfiffene/aufgelöste Spiele
// raus. Hier: _pwGlobalWhales (einzelne Wale), _pwGlobalWhaleLeaderboard, _pwFlips (Favorit gekippt).
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const PW = new URL('../../poly-wallets.js', import.meta.url);
function boot() {
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.eval(readFileSync(PW, 'utf8'));
  w._pwCache = { walletTrack: { scores: {} }, broadLive: {} };
  return w;
}
const capNow = () => new Date().toISOString();
// Markt-Objekt wie im broadLive-Freeze: capturedAt jetzt, htk steuert „schon durch" vs „kommt".
function mkt(htk, side, usd, resolved) {
  return {
    league: 'MLB', capturedAt: capNow(), hoursToKickoff: htk, resolved: resolved == null ? null : resolved,
    shares: { [side]: usd, Other: 100 }, prices: { [side]: 0.6, Other: 0.4 }, totalUsd: usd + 100,
    whales: [{ wallet: '0xW', side, usd }],
  };
}

test('_pwGlobalWhales: fertiges Spiel (>4h nach Anpfiff) raus, kommendes bleibt', () => {
  const w = boot();
  w._tl = {
    'mlb-done-2026-08-02': mkt(-8, 'DoneSide', 300000, null),   // vor 8h angepfiffen → durch
    'mlb-soon-2026-08-02': mkt(3, 'SoonSide', 9000, null),      // in 3h → kommt
  };
  const h = w.eval('_pwGlobalWhales(_tl)');
  assert.ok(!/mlb-done-2026|DoneSide/.test(h), 'durchgelaufener Wale-Markt NICHT gelistet');
  assert.match(h, /mlb-soon-2026|SoonSide/, 'kommender Wale-Markt bleibt');
});

test('_pwGlobalWhales: bereits aufgelöster Markt (resolved) raus', () => {
  const w = boot();
  w._tl = {
    'mlb-res-2026-08-02':  mkt(2, 'ResSide', 50000, 'ResSide'),   // resolved gesetzt
    'mlb-open-2026-08-02': mkt(2, 'OpenSide', 8000, null),
  };
  const h = w.eval('_pwGlobalWhales(_tl)');
  assert.ok(!/mlb-res-2026|ResSide/.test(h), 'aufgelöster Markt NICHT gelistet');
  assert.match(h, /mlb-open-2026|OpenSide/, 'offener Markt bleibt');
});

test('_pwGlobalWhaleLeaderboard: Einsätze fertiger Spiele zählen nicht mehr mit', () => {
  const w = boot();
  w._tl = { 'mlb-done-2026-08-02': mkt(-9, 'DoneSide', 300000, null) };  // nur ein durchgelaufener Markt
  const h = w.eval('_pwGlobalWhaleLeaderboard(_tl)');
  // keine Wallet-Zeile → „Noch keine Wale erfasst"-Hinweis statt der $300K-Position
  assert.ok(!/DoneSide/.test(h), 'kein Eintrag aus fertigem Spiel im Leaderboard');
});

test('_pwFlips: Favorit-Flip auf fertigem Spiel wird nicht als „neu" gezeigt', () => {
  const w = boot();
  // 02.09.2026: 5h statt exakt 6h — _pwFlips schaut seit dem Audit in ein 6h-Fenster, und
  // ein Zeitstempel genau auf der Kante fällt je nach Millisekunde mal rein, mal raus.
  const t0 = new Date(Date.now() - 5 * 3600e3).toISOString();
  const tN = new Date(Date.now() - 30 * 60e3).toISOString();
  w._th = {
    'mlb-doneflip-2026-08-02': [   // Führung A→B, aber Anpfiff war vor ~8h (tN + htk -8)
      { p: { A: 0.6, B: 0.4 }, league: 'MLB', ts: t0, htk: -5.5, v: 5000 },
      { p: { A: 0.4, B: 0.6 }, league: 'MLB', ts: tN, htk: -8, v: 6000 },
    ],
    'mlb-liveflip-2026-08-02': [   // Führung A→B, Anpfiff in ~2h
      { p: { A: 0.6, B: 0.4 }, league: 'MLB', ts: t0, htk: 4, v: 5000 },
      { p: { A: 0.4, B: 0.6 }, league: 'MLB', ts: tN, htk: 2, v: 6000 },
    ],
  };
  const flips = w.eval('_pwFlips(_th)');
  const keys = flips.map(f => f.key);
  assert.ok(!keys.includes('mlb-doneflip-2026-08-02'), 'Flip auf fertigem Spiel raus');
  assert.ok(keys.includes('mlb-liveflip-2026-08-02'), 'Flip auf kommendem Spiel bleibt');
});
