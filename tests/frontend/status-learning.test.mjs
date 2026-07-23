// tests/frontend/status-learning.test.mjs — Lern-Abschnitt der Status-Seite (_stRenderLearning).
// 22.07.2026 (Lucas: „sehe ich auf einen Blick, ob/wann zuletzt gelernt wurde?"). Fixiert die
// Ledger-Kopfzeile: N Einträge · letzter Eintrag vor X · Loop grün/wartet — auch im Leer-Fall.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const SC = new URL('../../status-checks.js', import.meta.url);

function load() {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="st_learning"></div></body>',
    { url: 'https://example.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  w.eval(readFileSync(SC, 'utf8'));
  return w;
}

test('Lern-Kopf: leerer Ledger zeigt „0 Einträge" + „Lern-Loop wartet"', () => {
  const w = load();
  w._stRenderLearning({ groups: {} }, { records: [] }, {});
  const html = w.document.getElementById('st_learning').innerHTML;
  assert.match(html, /Ledger: 0 Einträge/, 'Ledger-Zähler fehlt');
  assert.match(html, /Lern-Loop wartet/, 'Wartestatus fehlt');
});

test('Lern-Kopf: gefüllter Ledger zeigt Anzahl, „letzter Eintrag vor" + grünen Loop', () => {
  const w = load();
  const now = new Date().toISOString();
  const ledger = { records: [
    { key: 'a|1', result: 'won', processVerdict: 'JUSTIFIED', resolvedAt: now,
      signals: [{ name: 'form_trend', score: 1 }] },
  ] };
  const weights = { form_trend: {
    weight: 1.2, n_observations: 12, wins_when_triggered: 7, losses_when_triggered: 3, last_updated: now } };
  w._stRenderLearning({ groups: {}, picks: {} }, ledger, weights);
  const html = w.document.getElementById('st_learning').innerHTML;
  assert.match(html, /Ledger: 1 Eintrag\b/, 'Singular-Zähler fehlt');
  assert.match(html, /letzter Eintrag vor/, '„letzter Eintrag vor X" fehlt');
  assert.match(html, /Lern-Loop grün/, 'Grün-Status fehlt (judged>0 + Gewichte frisch)');
});

test('Lern-Kopf: „letzter Eintrag" nimmt das JÜNGSTE resolvedAt', () => {
  const w = load();
  const alt = new Date(Date.now() - 5 * 24 * 3600 * 1000).toISOString();   // vor 5 Tagen
  const neu = new Date(Date.now() - 2 * 3600 * 1000).toISOString();        // vor 2 Std
  const ledger = { records: [
    { key: 'a|1', result: 'won', resolvedAt: alt, signals: [{ name: 'x', score: 1 }] },
    { key: 'b|1', result: 'lost', resolvedAt: neu, signals: [{ name: 'x', score: 1 }] },
  ] };
  w._stRenderLearning({ groups: {} }, ledger, {});
  const html = w.document.getElementById('st_learning').innerHTML;
  assert.match(html, /Ledger: 2 Einträge/);
  assert.match(html, /letzter Eintrag vor 2\.0 Std/, 'muss das jüngste (2 Std), nicht das älteste zeigen');
});
