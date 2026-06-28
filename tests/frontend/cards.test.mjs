// tests/frontend/cards.test.mjs — Render-Tests für die Cards (wm2026-renderer.js, IIFE).
// Nutzt den Test-Hook window.__wmCardTest. Prüft: gemeinsames Signal-Grid (inkl. neuer Liga-Signale)
// + dass die KO-Card genauso reich rendert wie eine normale Card (Pick + Signale + Form).
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const WM_RENDERER = new URL('../../wm2026-renderer.js', import.meta.url);

function loadCards() {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="intlCardsPanel"></div></body>', {
    url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true,
  });
  const { window } = dom;
  window.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  window.eval(readFileSync(WM_RENDERER, 'utf8'));
  return window;
}

test('Card-Test-Hook ist exportiert', () => {
  const w = loadCards();
  assert.ok(w.__wmCardTest, '__wmCardTest fehlt');
  assert.equal(typeof w.__wmCardTest.engineSignalGridHtml, 'function');
  assert.equal(typeof w.__wmCardTest.buildKoCard, 'function');
});

test('Signal-Grid rendert neue Liga-Signale mit Label + Begründung', () => {
  const t = loadCards().__wmCardTest;
  const html = t.engineSignalGridHtml({
    signalAdjustmentPP: 1.5,
    signals: [
      { name: 'league_pressure', score: 1.2, evidence: 'Titelrennen — beide brauchen Punkte' },
      { name: 'fixture_congestion', score: -0.8, evidence: 'Heim müde (3 Tage Pause)' },
      { name: 'topscorer_momentum', score: 0.6, evidence: 'Top-Torjäger in Form' },
    ],
  });
  assert.match(html, /Liga-Druck/);
  assert.match(html, /Erschöpfung/);
  assert.match(html, /Top-Torjäger/);
  assert.match(html, /Titelrennen/);          // Begründung sichtbar
  assert.match(html, /Engine-Signale/);
});

test('KO-Card ist reich: Pick + Conviction + Signal-Grid + Form', () => {
  const w = loadCards();
  const t = w.__wmCardTest;
  t.setWmData({ form: {
    CIV: { last5: ['W', 'W', 'D', 'W', 'L'], avgScored: 1.8 },
    NOR: { last5: ['L', 'W', 'W', 'D', 'W'], avgScored: 1.5 },
  } });
  const fx = {
    home: 'CIV', away: 'NOR', date: '2026-06-30', kickoff: '2026-06-30T17:00:00Z',
    isKO: true, result: null,
    koData: { round: 'R32', roundLabel: 'Sechzehntelfinale', matchNo: 78,
              bothResolved: true, home: 'CIV', away: 'NOR' },
  };
  const home = { name: 'Elfenbeinküste', flag: '🇨🇮', elo: 1700 };
  const away = { name: 'Norwegen', flag: '🇳🇴', elo: 1720 };
  const picks = [{
    market: 'Doppelte Chance — 1X', verdict: 'ABWÄGEN', odds: 1.41, convictionScore: 5,
    signalAdjustmentPP: 1.0,
    signals: [{ name: 'league_pressure', score: 1.0, evidence: 'Druck' },
              { name: 'form_trend', score: 0.5, evidence: 'Heimform' }],
  }];
  const html = t.buildKoCard(fx, home, away, {}, picks, null, '2026-06-27');
  assert.match(html, /Doppelte Chance/, 'Pick-Markt muss erscheinen');
  assert.match(html, /Vorsichtiger Pick/, 'ABWÄGEN-Label');
  assert.match(html, /Warum\?/, 'Warum-Button muss da sein');
  assert.match(html, /Engine-Signale/, 'Signal-Grid muss da sein');
  assert.match(html, /Form letzten 5/, 'Form-Block muss da sein');
  assert.match(html, /Elfenbeinküste/);
});
