// tests/frontend/mls-event-page-slug.test.mjs
// 19.07.2026 (Lucas: „MLS-Event-Pages komplett leer") — die Match-Page-JSONs heißen mls-{id}-…
// (generate_wm_match_pages schreibt mit dem DATENSATZ-Prefix). MLS rendert unter _mode='liga',
// also baute das Frontend `liga-…` → 404 → leere Seite. Der Slug-Prefix muss pro Fixture aus der
// Gruppe kommen: 'MLS' → mls-, Top-5 → liga-, WM → wm-.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const WM_RENDERER = new URL('../../wm2026-renderer.js', import.meta.url);

function hook() {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="intlCardsPanel"></div></body>',
    { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const { window } = dom;
  window.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  window.eval(readFileSync(WM_RENDERER, 'utf8'));
  return window.__wmCardTest;
}

test('MLS-Fixture bekommt mls-Prefix (nicht liga-)', () => {
  const t = hook();
  t.setMode('liga');   // MLS + Top-5 rendern beide im Liga-Modus
  assert.equal(t.mpPrefix({ groupKey: 'MLS', home: '20787', away: '18310' }), 'mls',
    'MLS-Event-Page-Slug muss mls- sein, sonst 404 → leere Seite');
});

test('Top-5-Fixture bleibt liga-', () => {
  const t = hook();
  t.setMode('liga');
  assert.equal(t.mpPrefix({ groupKey: 'ENG', home: '116', away: '108' }), 'liga');
});

test('WM-Fixture bleibt wm-', () => {
  const t = hook();
  t.setMode('wm');
  assert.equal(t.mpPrefix({ groupKey: 'A', home: 'GER', away: 'BRA' }), 'wm');
});

test('Fallback ohne groupKey bricht Top-5 nicht (bleibt liga-)', () => {
  const t = hook();
  t.setMode('liga');
  assert.equal(t.mpPrefix({ home: '116', away: '108' }), 'liga');
});
