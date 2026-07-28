// tests/frontend/betfair-radar.test.mjs — Betfair Radar Rendering (28.07.2026, Lucas).
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const ROOT = new URL('../../', import.meta.url);
function render() {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="betfairRadarPanel"></div></body>',
    { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.eval(readFileSync(new URL('betfair-radar.js', ROOT), 'utf8'));
  w._bfState.data = JSON.parse(readFileSync(new URL('betfair_prices.json', ROOT), 'utf8'));
  w._bfState.hist = JSON.parse(readFileSync(new URL('betfair_history.json', ROOT), 'utf8'));
  w._bfState.loading = false;
  return { w, html: w._renderBetfairRadar() };
}

test('KPI-Band + Volumen + Spiele rendern', () => {
  const { html } = render();
  assert.match(html, /Betfair-Geld gematcht/);
  assert.match(html, /Top-Liga nach Geld/);
  assert.match(html, /Bayern Munich/);
  assert.match(html, /£/, 'Volumen in £');
});

test('Markt-Filterchips inkl. HT-Märkte da', () => {
  const { html } = render();
  assert.match(html, /Alle Märkte/);
  for (const m of ['1X2', 'Ü\\/U 2.5', 'Ü\\/U 3.5', 'BTTS', 'HT 1X2', 'HT Ü0.5', 'HT Ü1.5'])
    assert.match(html, new RegExp(m), 'Markt-Chip fehlt: ' + m);
});

test('Geld-Richtung aus History (gebackt/gelayt)', () => {
  const { html } = render();
  assert.match(html, /gebackt|gelayt/, 'Richtungsbadge aus Preisbewegung');
});

test('Markt-Filter reduziert Spalten', () => {
  const { w } = render();
  w._bfState.market = 'First Half Goals 0.5';
  const h2 = w._renderBetfairRadar();
  assert.match(h2, /HT Ü0.5/);
  assert.ok(!/Correct Score/.test(h2));
});
