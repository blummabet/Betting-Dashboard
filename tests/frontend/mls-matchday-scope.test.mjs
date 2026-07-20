// tests/frontend/mls-matchday-scope.test.mjs
// 20.07.2026 (Lucas Audit): Bei MLS zeigte die Spieltag-Filterleiste „Spieltag 1", obwohl die MLS
// längst bei md 18 steht. Wurzel: die Chips wurden aus ALLEN Fixtures (Top-5 + MLS gemerged)
// abgeleitet — weil die Top-5-Saison 2026/27 noch nicht läuft, war der „nächste" Spieltag = 1, und
// die MLS erbte ihn. Fix: die anstehenden Spieltage NUR aus der aktiven Gruppe ableiten.
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

// Realitätsnah: Top-5 (ENG) hat nur md1, zukunftsdatiert (Saison startet erst); MLS steht bei md18.
const FIXTURES = [
  { groupKey: 'ENG', matchday: 1,  date: '2026-08-15' },
  { groupKey: 'ENG', matchday: 2,  date: '2026-08-22' },
  { groupKey: 'MLS', matchday: 17, date: '2026-07-15' },   // vergangen
  { groupKey: 'MLS', matchday: 18, date: '2026-07-22' },   // anstehend
  { groupKey: 'MLS', matchday: 19, date: '2026-07-26' },
];
const TODAY = '2026-07-20';

test('MLS-Scope: nächster Spieltag ist 18, NICHT 1 (erbt nicht die Top-5-md)', () => {
  const t = hook();
  const up = t.upcomingMdsForScope(FIXTURES, 'MLS', TODAY);
  assert.equal(up[0], 18, 'MLS muss md 18 als nächsten zeigen, nicht die Top-5-md 1');
  assert.ok(!up.includes(1), 'md 1 der Top-5 darf im MLS-Scope nicht auftauchen');
});

test('Top-5-Scope: nächster Spieltag bleibt 1 (Saison startet erst) — korrektes Verhalten', () => {
  const t = hook();
  const up = t.upcomingMdsForScope(FIXTURES, 'ENG', TODAY);
  assert.equal(up[0], 1, 'Bei den Top-5 ist Spieltag 1 korrekt (noch nicht gestartet)');
});

test("'Alle' bleibt bewusst gemischt (kleinster anstehender md über alle Gruppen)", () => {
  const t = hook();
  const up = t.upcomingMdsForScope(FIXTURES, 'all', TODAY);
  assert.equal(up[0], 1, 'Alle-Ansicht mischt weiterhin — kleinster anstehender md');
});

test('Vergangene MLS-Spieltage zählen nicht als anstehend', () => {
  const t = hook();
  const up = t.upcomingMdsForScope(FIXTURES, 'MLS', TODAY);
  assert.ok(!up.includes(17), 'md 17 (15.07., vergangen) darf nicht anstehend sein');
});
