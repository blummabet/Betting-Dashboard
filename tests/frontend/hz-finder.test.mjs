// tests/frontend/hz-finder.test.mjs — Money Map → Reiter ⏸️ HZ 0:0 (04.10.2026). Reine Anzeige von
// hz_finder.json: Bilanz-Tabelle + Fund-Karten, Urteil kommt vom Erzeuger.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

function load() {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="moneyMapPanel"></div></body>', { runScripts: 'outside-only' });
  dom.window.fetch = () => Promise.resolve({ ok: false, json: () => Promise.resolve(null) });
  dom.window.eval(readFileSync(new URL('../../raw-json.js', import.meta.url), 'utf8'));
  dom.window.eval(readFileSync(new URL('../../money-map.js', import.meta.url), 'utf8'));
  return dom.window;
}

const D = {
  regel: { mindestN: 100 },
  bericht: {
    'tore/over05': { gruppe: 'tore', wette: 'over05', text: 'Over 0.5 (Tor in 2. HZ)', n: 12, trefferPct: 83.3, erwartetPct: 76.9, roi: 4.1, ug: null, og: null, urteil: 'sammelt' },
    'tore/over15': { gruppe: 'tore', wette: 'over15', text: 'Over 1.5 (2+ Tore)', n: 0, urteil: 'sammelt' },
    'heim/heim': { gruppe: 'heim', wette: 'heim', text: 'Heimsieg', n: 0, urteil: 'sammelt' },
  },
  zuletzt: [
    { home: 'Ararat <b>', away: 'Noah', league: 'Armenian Premier League', phase: 'HZ', gruppen: ['tore'], vor: { over25: 1.62 },
      quoten: { over05: 1.32, over15: 2.3, heim: 1.9 }, status: 'abgerechnet', ft: [1, 0],
      wetten: { over05: { win: true }, over15: { win: false } },
      serie: { heim: { form: 'SSU', over25: 2, n: 3, toreSchnitt: 3.3 }, gast: null }, gebuchtAt: '2026-10-04T15:00:00Z' },
  ],
};

test('Bilanz zeigt Treffer gegen die Pausenquote und das Urteil des Erzeugers', () => {
  const h = load()._mmHzHtml(D);
  assert.match(h, /Over 0\.5 \(Tor in 2\. HZ\)/);
  assert.match(h, /83\.3 %/);
  assert.match(h, /76\.9 %/);
  assert.match(h, /sammelt/);
});

test('Karte: Pausenquoten, Serie, Ergebnis — und Namen escaped', () => {
  const h = load()._mmHzHtml(D);
  assert.match(h, /Over 0\.5 <b>1\.32<\/b>/);
  assert.match(h, /Over 2\.5 erwartet @1\.62/);
  assert.match(h, /SSU · O2\.5 2\/3/);
  assert.match(h, /noch keine Spiele im Archiv/);
  assert.match(h, /O0\.5 ✓/);
  assert.match(h, /O1\.5 ✗/);
  assert.ok(!h.includes('Ararat <b>'), 'Teamname muss escaped sein');
});

test('leer: sagt, dass nichts da ist, statt leer zu bleiben', () => {
  const h = load()._mmHzHtml({ bericht: {}, zuletzt: [] });
  assert.match(h, /kein HZ-0:0-Fund/);
});

test('Karte zeigt Live-Statistik und die rückwirkende Serie aus API-Football', () => {
  const e = { ...D.zuletzt[0], apif: { statistik: { heim: { aufsTor: 5, schuesse: 12, ballbesitz: 64, xg: 1.1 }, gast: { aufsTor: 1, schuesse: 4, ballbesitz: 36, xg: 0.2 } },
    serie: { heim: { form: 'SUN', over25: 2, n: 8, toreSchnitt: 3.1, torIn2hz: 7, nHz: 8 } } } };
  const h = load()._mmHzHtml({ ...D, zuletzt: [e] });
  assert.match(h, /1\. HZ: aufs Tor 5–1 · Schüsse 12–4 · Ballbesitz 64–36 % · xG 1\.10–0\.20/);
  assert.match(h, /Tor in 2\. HZ 7\/8/);
});

// 09.10.2026 (Lucas lässt Nationalteams aus): je Wette zwei Unterzeilen aus dem Erzeuger.
test('Bilanz zeigt Vereine und Nationalteams getrennt — nur wenn es Fälle gibt', () => {
  const b = JSON.parse(JSON.stringify(D));
  b.bericht['tore/over15'] = { gruppe: 'tore', wette: 'over15', text: 'Over 1.5 (2+ Tore)', n: 45,
    trefferPct: 62.2, erwartetPct: 51.1, roi: 20.5, ug: -3.5, og: 44.4, urteil: 'sammelt',
    vereine: { n: 31, trefferPct: 64.5, erwartetPct: 51.3, roi: 25.9, ug: -2.1, og: 53.9 },
    nationalteams: { n: 14, trefferPct: 57.1, erwartetPct: 50.5, roi: 8.5, ug: null, og: null } };
  const h = load()._mmHzHtml(b);
  assert.match(h, /↳ nur Vereine<\/td><td class="mm-cn">31<\/td>/);
  assert.match(h, /↳ nur Nationalteams<\/td><td class="mm-cn">14<\/td>/);
  assert.match(h, /\+25\.9 %/);
  // over05 im Fixture hat keine Aufteilung (alter Stand) → keine leeren Unterzeilen
  assert.strictEqual((h.match(/↳ nur Vereine/g) || []).length, 1);
});
