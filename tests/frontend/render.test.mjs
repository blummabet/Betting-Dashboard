// tests/frontend/render.test.mjs — echter Render-Harness (jsdom) für renderer.js.
// Lädt den echten Renderer in ein DOM, speist Mock-Daten und prüft die GERENDERTE Ausgabe.
// Fängt Dataset-Awareness-Regressionen (Liga vs WM) + die Datums-Fenster-Logik im Sharp Radar.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const RENDERER = new URL('../../renderer.js', import.meta.url);

function loadRenderer() {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="mainContent"></div></body>', {
    url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true,
  });
  const { window } = dom;
  window.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  window.eval(readFileSync(RENDERER, 'utf8'));
  return window;
}

test('Renderer lädt + exportiert die Render-Funktionen global', () => {
  const w = loadRenderer();
  assert.equal(typeof w._renderBayesianWeights, 'function');
  assert.equal(typeof w._renderLigaCurrentLinesHtml, 'function');
  assert.equal(typeof w._sharpSetDataset, 'function');
});

test('Bayesian-Panel (WM): zeigt WM-Signale aus window.SIGNAL_WEIGHTS', () => {
  const w = loadRenderer();
  w.SIGNAL_WEIGHTS = {
    travel_burden: { weight: 0.94, n_observations: 50, wins_when_triggered: 23 },
    form_trend: { weight: 1.28, n_observations: 48, wins_when_triggered: 31 },
  };
  const html = w._renderBayesianWeights();
  assert.match(html, /Travel-Burden/, 'WM-Panel muss Travel-Burden listen');
  assert.match(html, /Pressure-Index/, 'WM-Panel muss Pressure-Index listen');
});

test('Bayesian-Panel (Liga): nur Liga-Signale, KEINE WM-only-Signale', () => {
  const w = loadRenderer();
  w._sharpSetDataset('liga');               // setzt _sharpDataset='liga' (sync)
  w.LIGA_SIGNAL_WEIGHTS = {
    form_trend: { weight: 1.14, n_observations: 0 },
    league_pressure: { weight: 0.93, n_observations: 0 },
  };
  const html = w._renderBayesianWeights();
  assert.match(html, /Liga-Druck/, 'Liga-Panel muss league_pressure (Liga-Druck) zeigen');
  assert.ok(!/Travel-Burden/.test(html), 'Liga-Panel darf KEIN WM-Travel-Burden zeigen');
  assert.ok(!/Weather\/Hitze/.test(html), 'Liga-Panel darf KEIN WM-Wetter zeigen');
});

test('Liga-Linien: nur nächste ~3 Wochen, ferne Spiele (2027) gefiltert', () => {
  const w = loadRenderer();
  const near = new Date(Date.now() + 3 * 86400000).toISOString().slice(0, 10);
  const data = {
    groups: { ENG: {
      teams: [{ id: '1', name: 'Alpha' }, { id: '2', name: 'Beta' },
              { id: '3', name: 'Gamma' }, { id: '4', name: 'Delta' }],
      fixtures: [
        { home: '1', away: '2', date: near, matchday: 1, result: null },
        { home: '3', away: '4', date: '2027-04-15', matchday: 38, result: null },
      ],
    } },
    odds: { '1-2': { hw: 1.8, dr: 3.5, aw: 4.2 }, '3-4': { hw: 2.0, dr: 3.3, aw: 3.5 } },
  };
  const html = w._renderLigaCurrentLinesHtml(data);
  assert.match(html, /Alpha – Beta/, 'Spiel in 3 Tagen muss erscheinen');
  assert.ok(!/Gamma – Delta/.test(html), 'Spiel im April 2027 muss aus dem 3-Wochen-Fenster fallen');
});
