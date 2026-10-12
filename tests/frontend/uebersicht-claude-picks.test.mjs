// 12.10.2026 (Lucas: „das mit dir und den Picks ist mir wichtiger … auf Dashboard einbauen").
// Die Sektion zeigt, was claude_picks_buch.json sagt — Urteil und CLV kommen vom Produzenten.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const MOD = new URL('../../main-dashboard.js', import.meta.url);
function load() {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="mainDashPanel"></div></body>',
    { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve(null) });
  w.eval(readFileSync(MOD, 'utf8'));
  return w;
}
const BUCH = {
  bilanz: { n: 2, abgerechnet: 1, gewonnen: 1, verloren: 0, push: 0, roi: 125, nClv: 1,
            clvSchnittPP: 1.4, clvPositivPct: 100, urteil: 'sammelt (Urteil ab 30 Picks mit Schlusskurs)' },
  zeilen: [
    { spiel: 'Coventry – Newcastle', liga: 'EPL', anpfiff: '2026-10-12T19:00:00Z', auswahl: 'Newcastle',
      kurs: 2.19, grund: 'Pinnacle <läuft>', status: 'offen' },
    { spiel: 'Oviedo – Eibar', liga: 'Segunda', anpfiff: '2026-10-12T16:30:00Z', auswahl: 'Eibar (DNB)',
      kurs: 2.25, status: 'abgerechnet', ergebnis: 'win', clvPP: 1.4, ft: [0, 1] },
  ],
};

test('offene Picks mit Grund, abgerechnete mit CLV, Urteil vom Produzenten', () => {
  const w = load();
  w._mdState.data = { claude: BUCH };
  const h = w._mdClaudePicksTest();
  assert.match(h, /Claudes Picks/);
  assert.match(h, /Coventry – Newcastle/);
  assert.match(h, /@2\.19/);
  assert.match(h, /Pinnacle &lt;läuft&gt;/, 'Grund wird escaped');
  assert.match(h, /✅ \+1\.4 pp/);
  assert.match(h, /sammelt \(Urteil ab 30 Picks/);
});

test('ohne Buch keine leere Sektion', () => {
  const w = load();
  w._mdState.data = { claude: null };
  assert.strictEqual(w._mdClaudePicksTest(), '');
});
