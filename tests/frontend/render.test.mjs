// tests/frontend/render.test.mjs — echter Render-Harness (jsdom) für renderer.js.
// Lädt den echten Renderer in ein DOM, speist Mock-Daten und prüft die GERENDERTE Ausgabe.
// Fängt Dataset-Awareness-Regressionen (Liga vs WM) + die Datums-Fenster-Logik im Sharp Radar.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const RENDERER = new URL('../../renderer.js', import.meta.url);
const PICK_ENGINE = new URL('../../pick-engine.js', import.meta.url);

function loadRenderer() {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="mainContent"></div></body>', {
    url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true,
  });
  const { window } = dom;
  window.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  window.eval(readFileSync(RENDERER, 'utf8'));
  return window;
}

// Voller Loader: pick-engine.js (computeLineMovement, parseGermanDate …) + renderer.js.
// Nötig für den kompletten renderSharpRadar-Durchlauf (Hero + KPIs).
function loadFull() {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="mainContent"></div></body>', {
    url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true,
  });
  const { window } = dom;
  window.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  window.eval(readFileSync(PICK_ENGINE, 'utf8'));
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

test('CLV-Scoreboard: Ø CLV + %beat + Abdeckung + Markt-Tabelle', () => {
  const w = loadRenderer();
  w.WM_CLV_SUMMARY = {
    overall: { n: 10, avgClvPP: 1.5, pctBeatClose: 60, coverage: { withClosing: 10, resolved: 12, pct: 83.3 } },
    byMarket: { '1X2/DNB': { n: 6, avgClvPP: 2.0, pctBeatClose: 66.7 }, 'Über/Unter': { n: 4, avgClvPP: 0.5, pctBeatClose: 50 } },
    byLeague: { A: { n: 10, avgClvPP: 1.5, pctBeatClose: 60 } },
    byTime: [{ bucket: '1', n: 5, avgClvPP: 1.0, pctBeatClose: 60 }],
  };
  const html = w._renderClvScoreboard();
  assert.match(html, /CLV-Bilanz/, 'Überschrift');
  assert.match(html, /\+1\.5pp/, 'Ø CLV-Kachel');
  assert.match(html, /83%/, 'Closing-Abdeckung %');
  assert.match(html, /Nach Markt/, 'Markt-Tabelle');
  assert.match(html, /Über\/Unter/, 'Markt-Zeile');
});

test('CLV-Scoreboard: keine aufgelösten Picks → freundlicher Hinweis', () => {
  const w = loadRenderer();
  w.WM_CLV_SUMMARY = { overall: { n: 0, coverage: { resolved: 0, withClosing: 0, pct: null } }, byMarket: {}, byLeague: {}, byTime: [] };
  const html = w._renderClvScoreboard();
  assert.match(html, /Noch keine aufgelösten Steam-Picks/);
});

test('Sharp Radar: Mover-Hero (Top-5) + Snapshot-KPI rendern (abgeschaut bei SteamWatch)', () => {
  const w = loadFull();
  w.LEAGUES = {};                                  // Legacy-Liga-Loop leer halten
  const near = new Date(Date.now() + 3 * 86400000).toISOString().slice(0, 10);
  const tsOld = new Date(Date.now() - 2 * 86400000).toISOString();
  const tsNow = new Date().toISOString();          // Snapshot „heute" → live-Zähler
  w.WM2026_DATA = { groups: { A: {
    teams: [{ id: 'civ', name: 'Elfenbeinküste', flag: '🇨🇮' },
            { id: 'nor', name: 'Norwegen', flag: '🇳🇴' }],
    fixtures: [{ home: 'civ', away: 'nor', date: near, time: '17:00', matchday: 1, result: null }],
  } } };
  w.WM2026_ODDS_HISTORY = { 'civ-nor': [
    { ts: tsOld, hw: 4.31, dr: 3.50, aw: 1.90 },
    { ts: tsNow, hw: 3.67, dr: 3.50, aw: 2.08 },   // Heim-Quote fällt → Heim gebackt
  ] };
  w.renderSharpRadar();
  const html = w.document.getElementById('mainContent').innerHTML;
  assert.match(html, /Größte Mover · Top/, 'Mover-Hero-Strip muss erscheinen');
  assert.match(html, /Elfenbeinküste/, 'Hero muss das Top-Mover-Spiel zeigen');
  assert.match(html, /4\.31→/, 'Hero muss Open→Jetzt zeigen');
  assert.match(html, /📸/, 'Snapshot-KPI muss erscheinen');
  assert.match(html, /heute · live/, 'Snapshot-KPI muss heutige Snapshots als live markieren');
});

test('Mover-Hero: Liga-Logos (<img>) werden sauber gestrippt, kein kaputter Link/Attr', () => {
  const w = loadFull();
  w.LEAGUES = {};
  const near = new Date(Date.now() + 3 * 86400000).toISOString().slice(0, 10);
  const tsOld = new Date(Date.now() - 2 * 86400000).toISOString();
  const tsNow = new Date().toISOString();
  // Liga rendert Teamnamen als "<img src=...> Name" (Logo statt Flag) + Mehrwort-Name
  const logo = '<img src="https://media.api-sports.io/football/teams/49.png" style="width:18px">';
  w.WM2026_DATA = { groups: { A: {
    teams: [{ id: 'che', name: 'Chelsea', flag: logo },
            { id: 'cry', name: 'Crystal Palace', flag: logo }],
    fixtures: [{ home: 'che', away: 'cry', date: near, time: '17:00', matchday: 1, result: null }],
  } } };
  w.WM2026_ODDS_HISTORY = { 'che-cry': [
    { ts: tsOld, hw: 2.23, dr: 3.40, aw: 3.10 },
    { ts: tsNow, hw: 2.00, dr: 3.40, aw: 3.50 },
  ] };
  w.renderSharpRadar();
  const html = w.document.getElementById('mainContent').innerHTML;
  assert.match(html, /Chelsea <span[^>]*>vs<\/span> Crystal Palace/, 'Saubere Namen ohne Logo-HTML/Mehrwort-Verstümmelung');
  assert.ok(!/href="[^"]*<img/.test(html), 'KEIN <img> darf in ein href-Attribut lecken');
  assert.ok(!/wm-<img/.test(html), 'Kein kaputter Event-Page-Link aus Logo-HTML');
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
