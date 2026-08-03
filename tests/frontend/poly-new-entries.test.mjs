// tests/frontend/poly-new-entries.test.mjs — „🆕 Neu"-View (31.07.2026, Lucas: „$33-Einstiege
// wertlos, Politik drin"). Fix: nur echte Sportarten, Größen-Floor $5K, nach Größe sortiert.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const PW = new URL('../../poly-wallets.js', import.meta.url);
function mockFetch(files) {
  return (url) => { const u = String(url); let body = null;
    for (const [frag, data] of Object.entries(files)) if (u.includes(frag)) { body = data; break; }
    return Promise.resolve({ ok: body != null, json: () => Promise.resolve(body) }); };
}
async function renderNew(walletTrack, close) {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="polyWalletsPanel"></div></body>',
    { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const { window: w } = dom;
  w.fetch = mockFetch({
    'mls-data.json': { groups: {} }, 'mls_poly_prices.json': { prices: {} },
    'mls_poly_wallets.json': { topPositionsAll: [{ wallet: '0xabc', usd: 5000, side: 'h', pick: 'H', key: 'H-A', match: 'H vs A' }], updatedAt: new Date().toISOString() },
    'poly_money_broad.json': { n: 5, generatedAt: new Date().toISOString(), byLeague: [1] },
    'poly_money_broad_close.json': close || { x: {} },
    'poly_wallet_track.json': walletTrack,
  });
  w.eval(readFileSync(PW, 'utf8'));
  w._pwDsId = 'mls'; w.initPolyWallets();
  await new Promise(r => setTimeout(r, 30));
  w._pwSetSportFilter('all'); w._pwSetView('new');
  return w.document.getElementById('polyWalletsPanel').innerHTML;
}
const iso = h => new Date(Date.now() - h * 3600000).toISOString();

test('Neu: nur echte Sportarten ≥$5K, nach Größe — kein Dust/Politik', async () => {
  const track = { updatedAt: new Date().toISOString(), scores: {}, open: {
    'k1': { wallet: '0xA', key: 'tennis-sinner-2026', side: 'Sinner', league: 'TENNIS', firstPrice: 0.6, firstTs: iso(2), usd: 30000 },
    'k2': { wallet: '0xB', key: 'greater-election-2026', side: 'No', league: 'GREATER', firstPrice: 0.5, firstTs: iso(3), usd: 50000 },  // Politik → raus
    'k3': { wallet: '0xC', key: 'esports-t1-2026', side: 'T1', league: 'ESPORTS', firstPrice: 0.55, firstTs: iso(1), usd: 33 },          // Dust → raus
    'k4': { wallet: '0xD', key: 'mlb-dodgers-2026', side: 'Dodgers', league: 'MLB', firstPrice: 0.58, firstTs: iso(4), usd: 12000 },
  } };
  const h = await renderNew(track);
  const seg = (h.split('Neue große Einstiege')[1] || '').split('Favorit gekippt')[0];
  assert.match(seg, /Sinner/, 'großer Tennis-Einstieg gelistet');
  assert.match(seg, /Dodgers/, 'großer MLB-Einstieg gelistet');
  assert.doesNotMatch(seg, /greater-election|No</, 'Politik (GREATER) NICHT gelistet');
  assert.doesNotMatch(seg, /esports-t1|\bT1\b/, 'Dust ($33) NICHT gelistet');
  // nach Größe: Sinner ($30K) vor Dodgers ($12K)
  assert.ok(seg.indexOf('Sinner') < seg.indexOf('Dodgers'), 'nach Einsatz sortiert (größte zuerst)');
});

// 03.08.2026 (Lucas: „Neu ist nicht aktuell"): der Feed zeigte $300K-Einstiege auf GESTRIGE Spiele.
// Fix: Anpfiff-Gate — schon angepfiffene/durchgelaufene Spiele (rekonstruierter Anpfiff aus dem
// broadLive-Freeze, >4h nach KO = durch) fliegen raus; kommende bleiben.
test('Neu: durchgelaufene Spiele raus, kommende bleiben (Anpfiff-Gate)', async () => {
  const cap = new Date().toISOString();
  const close = {
    'mlb-over-2026-08-02':  { capturedAt: cap, hoursToKickoff: -8 },   // vor 8h angepfiffen → durch
    'mlb-comng-2026-08-02': { capturedAt: cap, hoursToKickoff: 3 },    // in 3h → noch aktuell
  };
  const track = { updatedAt: new Date().toISOString(), scores: {}, open: {
    a: { wallet: '0xA', key: 'mlb-over-2026-08-02',  side: 'Overside', league: 'MLB', firstPrice: 0.6, firstTs: iso(6), usd: 40000 },
    b: { wallet: '0xB', key: 'mlb-comng-2026-08-02', side: 'Comingside', league: 'MLB', firstPrice: 0.6, firstTs: iso(2), usd: 20000 },
  } };
  const h = await renderNew(track, close);
  const seg = (h.split('Neue große Einstiege')[1] || '').split('Favorit gekippt')[0];
  assert.doesNotMatch(seg, /mlb-over-2026|Overside/, 'durchgelaufenes Spiel ($40K, 8h nach KO) NICHT gelistet');
  assert.match(seg, /mlb-comng-2026|Comingside/, 'kommendes Spiel (in 3h) bleibt gelistet');
});

test('Neu: kein Freeze mehr im broadLive → Datum aus dem Key < heute filtert', async () => {
  const track = { updatedAt: new Date().toISOString(), scores: {}, open: {
    a: { wallet: '0xA', key: 'mlb-yesterday-2000-01-01', side: 'Alt', league: 'MLB', firstPrice: 0.6, firstTs: iso(5), usd: 30000 },
  } };
  const h = await renderNew(track, { z: {} });   // Markt nicht (mehr) im Freeze
  const seg = (h.split('Neue große Einstiege')[1] || '').split('Favorit gekippt')[0];
  assert.doesNotMatch(seg, /mlb-yesterday|Alt</, 'Spiel mit Key-Datum in der Vergangenheit fliegt raus');
});
