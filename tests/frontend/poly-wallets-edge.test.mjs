// tests/frontend/poly-wallets-edge.test.mjs
// 19.07.2026 — Die neuen Poly-Edge-Sektionen im Wallets-Tab: Auflösungs-Lücken, interne
// Fehlbepreisung, Whale-Einstiegsqualität. Prüft, dass sie aus den Detektor-Dateien wirklich
// rendern — und NICHT erscheinen, wenn keine Daten da sind (sonst leere Deko-Kästen).
//
// Getrieben über initPolyWallets mit gemocktem fetch (nicht _pwCache direkt — das ist `let`,
// hängt nicht am window und lässt sich von außen nicht setzen).
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const PW = new URL('../../poly-wallets.js', import.meta.url);

const baseWallets = { topPositionsAll: [{ wallet: '0xabc', usd: 5000, side: 'home',
  pick: 'Heim', key: 'H-A', match: 'H vs A' }], updatedAt: new Date().toISOString() };

// Liefert je nach Dateiname (im URL) den passenden JSON-Body zurück.
function mockFetch(files) {
  return (url) => {
    const u = String(url);
    let body = null;
    for (const [frag, data] of Object.entries(files)) {
      if (u.includes(frag)) { body = data; break; }
    }
    return Promise.resolve({ ok: body != null, json: () => Promise.resolve(body) });
  };
}

async function render(files, view) {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="polyWalletsPanel"></div></body>',
    { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const { window: w } = dom;
  w.fetch = mockFetch(Object.assign({
    'mls-data.json': { groups: {} },
    'mls_poly_prices.json': { prices: {} },
    'mls_poly_wallets.json': baseWallets,
    'mls-odds-history.json': {},
  }, files));
  w.eval(readFileSync(PW, 'utf8'));
  w._pwDsId = 'mls';               // MLS = Einstieg (hat Poly)
  w.initPolyWallets();
  await new Promise(r => setTimeout(r, 20));   // Promise.all auflösen lassen
  if (view) w._pwSetView(view);    // 19.07.: Sektionen auf Unter-Reiter verteilt
  return w.document.getElementById('polyWalletsPanel').innerHTML;
}

test('Auflösungs-Lücke rendert aus settlement-Datei', async () => {
  const html = await render({ 'mls_poly_settlement.json': { gaps: [
    { match: 'LA vs SEA', markt: '1X2', endstand: '2:0', gewinnerPreis: 0.94, gapPP: 6, vol: 12000 }] } });
  assert.match(html, /Auflösungs-Lücken/);
  assert.match(html, /LA vs SEA/);
  assert.match(html, /\+6\.0pp/);
});

test('interne Fehlbepreisung rendert aus coherence-Datei', async () => {
  const html = await render({ 'mls_poly_coherence.json': { arbCount: 1, findings: [
    { match: 'Chicago vs Vancouver', markt: '1X2', typ: 'underround', summe: 0.88, edgePP: 12 }] } });
  assert.match(html, /Poly-interne Fehlbepreisung/);
  assert.match(html, /Chicago vs Vancouver/);
  assert.match(html, /Arbitrage/);
});

test('Whale-Einstiegsqualität rendert aus dem Ledger (firstAvgPrice)', async () => {
  const html = await render({ 'mls_poly_wallet_ledger.json': { updatedAt: new Date().toISOString(),
    positions: {
      a: { wallet: '0xdef', usd: 8000, pick: 'Über 2.5', firstAvgPrice: 0.42 },
      b: { wallet: '0xghi', usd: 3000, pick: 'Heim', firstAvgPrice: 0.60 },
      c: { wallet: '0xjkl', usd: 2000, pick: 'BTTS', firstAvgPrice: 0.50 } } } }, 'whales');
  assert.match(html, /Whale-Einstiegsqualität/);
  assert.match(html, /42¢/, 'Einstiegspreis muss erscheinen');
});

test('keine Detektor-Daten → KEINE leeren Sektionen', async () => {
  const html = await render({});
  assert.doesNotMatch(html, /Auflösungs-Lücken/, 'leere Settlement-Sektion darf nicht rendern');
  assert.doesNotMatch(html, /Poly-interne Fehlbepreisung/, 'leere Kohärenz-Sektion darf nicht rendern');
  assert.doesNotMatch(html, /Whale-Einstiegsqualität/, 'leere Ledger-Sektion darf nicht rendern');
});

test('Ledger mit < 3 Positionen wird unterdrückt (zu dünn)', async () => {
  const html = await render({ 'mls_poly_wallet_ledger.json': { positions: {
    a: { wallet: '0xa', usd: 8000, firstAvgPrice: 0.42 } } } });
  assert.doesNotMatch(html, /Whale-Einstiegsqualität/);
});
