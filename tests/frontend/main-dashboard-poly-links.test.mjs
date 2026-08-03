// tests/frontend/main-dashboard-poly-links.test.mjs — 02.08.2026 (Lucas): die Poly-Kacheln der
// Übersicht (Poly Whale-Bets, Top-Play, Whale-Watch, Heute spielenswert) verlinken das Match aufs
// jeweilige Polymarket-Event — genau wie im Wallet-Reiter (polymarket.com/event/<slug>).
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const MOD = new URL('../../main-dashboard.js', import.meta.url);

function load() {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="mainDashPanel"></div></body>', { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve(null) });
  w.eval(readFileSync(MOD, 'utf8'));
  return w;
}
function seed(w) {
  w._pwSportIcon = () => '⚾';
  w._pwEnsurePlaysData = (cb) => cb && cb();
  w._pwTopPlays = () => [{ key: 'nba-lal-bos-2026-07-25', match: 'Lakers vs Celtics', side: 'Lakers', verdict: 'BET', conv: 9, reasons: ['Steam'], htk: 3, league: 'NBA' }];
  w._pwPublicTopPlays = () => [{ key: 'atp-alc-sin-2026-07-25', match: 'Alcaraz vs Sinner', side: 'Alcaraz', verdict: 'BET', conv: 10, moneyPct: 0.7, sharp: { n: 12, wins: 8, hit: 0.66 }, htk: 1, league: 'ATP' }];
  w._pwWhalePublicCandidates = () => [{ wallet: '0xdead', key: 'lol-t1-geng-2026-07-25', side: 'T1', league: 'LoL', usd: 150000, price: 0.6, tracked: true, n: 20, hit: 0.7 }];
  w._mdState.data = {
    liga: null, mls: null, ligaStreaks: null, mlsStreaks: null, betfair: { matches: [] }, pulse: null,
    // poly_money_broad_close.json-Form: Top-Level-Key IST der Event-Slug
    whales: { 'mlb-cws-tor-2026-07-19': { league: 'MLB', hoursToKickoff: 2, whales: [{ wallet: '0xabc', side: 'Toronto', usd: 120000 }] } },
  };
}

test('alle vier Poly-Kacheln verlinken aufs jeweilige polymarket.com/event/<slug>', () => {
  const w = load(); seed(w);
  w._renderMainDash();
  const h = w.document.getElementById('mainDashPanel').innerHTML;
  // Poly Whale-Bets (aus dem close-Sidecar), Heute spielenswert, Top-Play, Whale-Watch
  assert.match(h, /href="https:\/\/polymarket\.com\/event\/mlb-cws-tor-2026-07-19"/, 'Whale-Bets → Event');
  assert.match(h, /href="https:\/\/polymarket\.com\/event\/nba-lal-bos-2026-07-25"/, 'Heute spielenswert → Event');
  assert.match(h, /href="https:\/\/polymarket\.com\/event\/atp-alc-sin-2026-07-25"/, 'Top-Play → Event');
  assert.match(h, /href="https:\/\/polymarket\.com\/event\/lol-t1-geng-2026-07-25"/, 'Whale-Watch → Event');
  // neuer Tab + noopener wie im Wallet-Reiter, plus ↗-Cue
  assert.match(h, /target="_blank" rel="noopener" class="md-polylink"/);
  assert.match(h, /md-ext">↗/);
});

test('ohne Slug bleibt die Zeile unverlinkt (kein leeres <a>)', () => {
  const w = load(); seed(w);
  // Slug entfernen → Text muss ohne Anchor durchlaufen
  w._pwTopPlays = () => [{ match: 'NoSlug FC vs X', side: 'NoSlug FC', verdict: 'BET', conv: 9, reasons: [], htk: 3, league: 'NBA' }];
  w._renderMainDash();
  const h = w.document.getElementById('mainDashPanel').innerHTML;
  assert.match(h, /NoSlug FC/, 'Text ist da');
  assert.ok(!/event\/undefined/.test(h), 'kein event/undefined-Link');
  assert.ok(!/href="https:\/\/polymarket\.com\/event\/"/.test(h), 'kein leerer Event-Link');
})
// 03.08.2026 (Lucas: „Spiele waren in der Nacht — unnötig in der Übersicht"): die Poly-Whale-Bets-
// Kachel filtert jetzt schon angepfiffene/aufgelöste Spiele (rekonstruierter Anpfiff aus capturedAt+
// hoursToKickoff, >4h danach = durch) — wie der Wallet-Reiter. Gleiche Quelle, gleiche Gate.
function seedWhales(w, whales) {
  w._mdState.data = {
    liga: null, mls: null, ligaStreaks: null, mlsStreaks: null, betfair: { matches: [] }, pulse: null,
    whales,
  };
}
const capNow = () => new Date().toISOString();

test('Poly Whale-Bets: MLB-Nachtspiel (>4h nach Anpfiff) raus, kommendes bleibt', () => {
  const w = load();
  seedWhales(w, {
    'mlb-bos-lad-2026-08-02': { league: 'MLB', country: 'US', capturedAt: capNow(), hoursToKickoff: -8,
                               whales: [{ wallet: '0xA', side: 'Boston Red Sox', usd: 302000 }] },   // durch
    'atp-live-2026-08-03':    { league: 'TENNIS', country: 'US', capturedAt: capNow(), hoursToKickoff: 2,
                               whales: [{ wallet: '0xB', side: 'Alcaraz', usd: 9000 }] },             // in 2h
  });
  w._renderMainDash();
  const h = w.document.getElementById('mainDashPanel').innerHTML;
  const seg = (h.split('Poly Whale-Bets')[1] || '').split('id="md-cell-top"')[0];
  assert.ok(!/mlb-bos-lad|Red Sox/.test(seg), 'durchgelaufenes MLB-Nachtspiel NICHT in der Kachel');
  assert.match(seg, /atp-live-2026-08-03|Alcaraz/, 'kommendes Spiel bleibt');
});

test('Poly Whale-Bets: aufgelöster Markt (resolved) raus', () => {
  const w = load();
  seedWhales(w, {
    'mlb-res-2026-08-02': { league: 'MLB', capturedAt: capNow(), hoursToKickoff: 1, resolved: 'X',
                            whales: [{ wallet: '0xA', side: 'ResSide', usd: 80000 }] },
    'atp-ok-2026-08-03':  { league: 'TENNIS', capturedAt: capNow(), hoursToKickoff: 2,
                            whales: [{ wallet: '0xB', side: 'OkSide', usd: 9000 }] },
  });
  w._renderMainDash();
  const h = w.document.getElementById('mainDashPanel').innerHTML;
  const seg = (h.split('Poly Whale-Bets')[1] || '').split('id="md-cell-top"')[0];
  assert.ok(!/ResSide/.test(seg), 'aufgelöster Markt NICHT in der Kachel');
  assert.match(seg, /OkSide/, 'offener Markt bleibt');
});
