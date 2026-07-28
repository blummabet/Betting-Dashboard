// tests/frontend/poly-xsport-tab.test.mjs
// 28.07.2026 (Lucas: "eigenen tab machen") - Cross-Sport-Edge (Poly vs Pinnacle) bekommt einen
// eigenen, prominenten Tab statt unter "Chancen" versteckt zu sein.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const PW = new URL('../../poly-wallets.js', import.meta.url);
function win() {
  const w = new JSDOM('<!DOCTYPE html><body></body>',
    { url: 'https://x.com/', runScripts: 'outside-only' }).window;
  w.eval(readFileSync(PW, 'utf8'));
  return w;
}

test('eigener Tab "Poly vs Sharp" steht in der Tab-Leiste', () => {
  const html = win()._pwViewTabs();
  assert.match(html, /Poly vs Sharp/);
  assert.match(html, /_pwSetView\('xsport'\)/);
});

test('xsport hat eine Intro-Box', () => {
  const intro = win()._pwViewIntro('xsport');
  assert.match(intro, /Poly vs Sharp/);
});

test('_pwGlobalEdge rendert die Cross-Sport-Edge weiterhin', () => {
  const cs = { matched: 5, discrepancies: [
    { id: 'soccer_mls|a-b|hw', sport: 'soccer_mls', event: 'A vs B', outcome: 'Heim',
      polyPP: 50, pinnPP: 40, gapPP: 10, vol: 100000, richtung: 'Poly zu hoch faden', convergePP: 2.5 } ] };
  const html = win()._pwGlobalEdge(cs);
  assert.match(html, /A vs B/);
  assert.match(html, /Konvergenz/);
});
