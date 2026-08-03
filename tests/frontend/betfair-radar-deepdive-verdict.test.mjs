// tests/frontend/betfair-radar-deepdive-verdict.test.mjs — 03.08.2026 (Lucas): der Kohärenz-Deep-Dive
// führt jetzt mit einem VERDIKT (Synthese statt nur Diagnose): härteste Fehlbepreisung → Back/Lay-
// Richtung, oder „nichts Handelbares"; live keine Value-Aussage. Konsens-Kurve wandert ans Ende.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const ROOT = new URL('../../', import.meta.url);
const ko = (h) => new Date(Date.now() + h * 3600e3).toISOString();

function bootRadar() {
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window; w._bfNoAutoRefresh = true;
  w.eval(readFileSync(new URL('betfair-radar.js', ROOT), 'utf8'));
  w._bfState.data = { _meta: { generatedAt: new Date().toISOString() }, matches: [] };
  return w;
}
const PRE = { kickoff: ko(9), liveInfo: {} };
const LIVE = { kickoff: ko(-0.3), liveInfo: { time: 30, finished: false } };
const hard = (dev, w, vol) => ({ k: 'Draw no Bet', mkt: 'DNB Heim', market: 0.62 + (dev / 100), model: 0.62, dev, w, vol });

test('Live → Verdikt warnt, keine Value-Aussage', () => {
  const w = bootRadar();
  const v = w._bfVerdict({ hard: [hard(-6, 0.5, 5000)], s: 55 }, LIVE);
  assert.match(v, /Live — mit Vorsicht/);
  assert.match(v, /kein verlässliches Value-Signal/);
});

test('Pre-Match ohne harte Abweichung → „Nichts klar Handelbares"', () => {
  const w = bootRadar();
  assert.match(w._bfVerdict({ hard: [], s: 20, fl: null }, PRE), /Nichts klar Handelbares/);
});

test('Harte Abweichung nur auf dünnem Markt (w<0.35) → nicht handelbar', () => {
  const w = bootRadar();
  assert.match(w._bfVerdict({ hard: [hard(-6, 0.2, 1000)], s: 40 }, PRE), /Nichts klar Handelbares/);
});

test('Unterbewertet → Back, überbewertet → Lay', () => {
  const w = bootRadar();
  const under = w._bfVerdict({ hard: [hard(-6, 0.5, 5000)], s: 55 }, PRE);
  assert.match(under, /Handelbar/); assert.match(under, /unterbewertet/); assert.match(under, /Back DNB Heim/);
  const over = w._bfVerdict({ hard: [hard(6, 0.5, 5000)], s: 55 }, PRE);
  assert.match(over, /überbewertet/); assert.match(over, /Lay DNB Heim/);
});

test('Leiter-Monotonie → als reiner Widerspruch benannt', () => {
  const w = bootRadar();
  const v = w._bfVerdict({ hard: [{ k: 'Leiter-Monotonie', mkt: 'O1.5 > O1.0', market: 0.7, model: 0.66, dev: 4, w: 0.5, vol: 5000 }], s: 55 }, PRE);
  assert.match(v, /Widerspruch/);
});

test('mehrere harte Abweichungen → Zusatzhinweis auf die Tabelle', () => {
  const w = bootRadar();
  const v = w._bfVerdict({ hard: [hard(-6, 0.5, 5000), hard(-4, 0.5, 4000)], s: 60 }, PRE);
  assert.match(v, /1 weitere harte Abweichung/);
});

test('Reihenfolge im Deep-Dive: Verdikt oben, Konsens-Kurve ganz unten', () => {
  const w = bootRadar();
  const m = { matchId: 1, home: 'Alpha', away: 'Beta', league: 'Test', country: 'GB', kickoff: ko(9), liveInfo: {},
    totalVol: 10000, markets: { 'Match Odds': { vol: 10000, runners: [
      { name: 'Alpha', odd: 2.0, vol: 7000 }, { name: 'The Draw', odd: 3.5, vol: 1500 }, { name: 'Beta', odd: 4.0, vol: 1500 }] } } };
  w._bfState.data = { _meta: { generatedAt: new Date().toISOString() }, matches: [m] };
  const h = w._bfDrawerHTML(m);
  const iVerdict = Math.max(h.indexOf('Nichts klar Handelbares'), h.indexOf('Handelbar'));
  const iGeld = h.indexOf('Geld je Markt');
  const iCurve = Math.max(h.indexOf('Konsens-Kurve'), h.indexOf('Kurve nicht rekonstruierbar'));
  assert.ok(iVerdict >= 0 && iGeld >= 0 && iCurve >= 0, 'alle Abschnitte vorhanden');
  assert.ok(iVerdict < iGeld, 'Verdikt steht vor „Geld je Markt"');
  assert.ok(iGeld < iCurve, 'Konsens-Kurve steht nach „Geld je Markt" (ganz unten)');
});
