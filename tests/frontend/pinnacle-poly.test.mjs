// tests/frontend/pinnacle-poly.test.mjs — 04.08.2026 (Lucas): „Pinnacle × Poly"-Sheet.
// Kernlogik: Round-Trip-Backtest (Einstieg bei Pinnacle-Move + Poly-Lag, Ausstieg bei Konvergenz).
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const MOD = new URL('../../pinnacle-poly.js', import.meta.url);
function boot(data) {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="pinnPolyPanel"></div></body>', { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve(data) });
  w.eval(readFileSync(MOD, 'utf8'));
  return w;
}
const ts = (m) => new Date(Date.UTC(2026, 7, 4, 12, m, 0)).toISOString();

test('Backtest: Pinnacle-Move + Poly-Lag → konvergierter Trip mit Gewinn', () => {
  const w = boot(null);
  const snaps = [
    { ts: ts(0),  pinn: [0.45, 0.30, 0.25], poly: [0.44, 0.30, 0.26] },
    { ts: ts(30), pinn: [0.52, 0.28, 0.20], poly: [0.44, 0.30, 0.26] },   // Pinnacle +7pp Heim, Poly lagt → Einstieg
    { ts: ts(60), pinn: [0.52, 0.28, 0.20], poly: [0.515, 0.28, 0.205] }, // Poly konvergiert → Ausstieg
  ];
  const home = w._ppBacktest(snaps).filter(t => t.o === 0);
  assert.strictEqual(home.length, 1);
  assert.ok(home[0].converged);
  assert.ok(home[0].realized > 6 && home[0].realized < 9, 'Gewinn ~+7.5pp: ' + home[0].realized);
  assert.strictEqual(home[0].mins, 30);
});

test('Backtest: kein Pinnacle-Move → kein Trip (nur statische Edge zählt nicht)', () => {
  const w = boot(null);
  const snaps = [
    { ts: ts(0),  pinn: [0.50, 0.30, 0.20], poly: [0.40, 0.30, 0.30] },
    { ts: ts(30), pinn: [0.50, 0.30, 0.20], poly: [0.41, 0.30, 0.29] },
  ];
  assert.strictEqual(w._ppBacktest(snaps).length, 0);
});

test('Backtest: offener Trip (nie konvergiert) wird markiert', () => {
  const w = boot(null);
  const snaps = [
    { ts: ts(0),  pinn: [0.45, 0.30, 0.25], poly: [0.44, 0.30, 0.26] },
    { ts: ts(30), pinn: [0.55, 0.25, 0.20], poly: [0.44, 0.30, 0.26] },   // Einstieg, bleibt offen
    { ts: ts(60), pinn: [0.55, 0.25, 0.20], poly: [0.46, 0.29, 0.25] },
  ];
  const t = w._ppBacktest(snaps).filter(x => x.o === 0);
  assert.strictEqual(t.length, 1);
  assert.strictEqual(t[0].converged, false);
});

test('Render: Sheet zeigt Liga + aufklappbar die Spiele', async () => {
  const data = { _meta: { generatedAt: ts(60), leaguesActive: 1 }, games: {
    'Champions League|Ajax|PSV|2026-08-04': { league: 'Champions League', home: 'Ajax', away: 'PSV', kickoff: ts(120),
      snaps: [
        { ts: ts(0),  pinn: [0.45, 0.30, 0.25], poly: [0.44, 0.30, 0.26] },
        { ts: ts(30), pinn: [0.52, 0.28, 0.20], poly: [0.44, 0.30, 0.26] },
        { ts: ts(60), pinn: [0.52, 0.28, 0.20], poly: [0.515, 0.28, 0.205] },
      ] } } };
  const w = boot(data);
  w.initPinnPoly();
  await new Promise(r => setTimeout(r, 30));
  let h = w.document.getElementById('pinnPolyPanel').innerHTML;
  assert.match(h, /Pinnacle × Poly/, 'Titel');
  assert.match(h, /Champions League/, 'Liga-Zeile');
  assert.match(h, /Trips/, 'Backtest-Summary');
  w._ppToggle('Champions League');
  h = w.document.getElementById('pinnPolyPanel').innerHTML;
  assert.match(h, /Ajax/, 'Spiel nach Aufklappen sichtbar');
});
