// tests/frontend/uebersicht-serien-buch.test.mjs — 09.09.2026
//
// Lucas: „der Preis ist da egal um ehrlich zu sein — die Frage ist einfach: wurde Serie erfüllt
// ja oder nein. Das dann etwas simpler, aber das braucht es oder?"
//
// Ja. Und der Fund davor: `build_recap` rechnete genau das seit August jeden Tag aus, postete es
// und warf es weg — 50 bewachte Serien, 0 Ergebnisse. Jetzt gibt es ein Buch.
//
// Was hier festgehalten wird, ist die eine Regel, an der die Zahl hängt: die Trefferquote ALLEIN
// sagt nichts. „71 % erfüllt" ist gut oder schlecht, je nachdem, was ohne jede Serie zu erwarten
// war — und das Urteil darüber fällt der Produzent, nicht das Frontend.
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

const serie = {
  team: 'Parma', market: 'Unter 2,5 Tore', type: 'under25', length: 10, venue: 'all',
  leagueName: 'Serie A', league: 'ITA', basis: 'prior', preN: 5, ratePct: 80,
  continuation: { state: 'intakt', ratePct: 80, label: 'x' },
  seltenheit: { basis: 'eigen', ratePct: 80, preN: 5, einsZu: 9, erwartet: 340.16,
                familie: 3168, bandPct: [44, 95], einsZuBand: [2, 4097],
                erwartetBand: [0.77, 1979.08], urteil: 'erwartbar', grund: 'im Feld erwartbar' },
};

function render(rec) {
  const w = load();
  w._mdState.data = { ligaStreaks: { streaks: [serie] }, mlsStreaks: null, ligaStreakRec: rec };
  w._renderMainDash();
  return w.document.body.innerHTML;
}

test('das Buch steht unter den Serien und nennt sein Urteil', () => {
  const html = render({ bilanz: { n: 200, treffer: 160, unaufloesbar: 0, quotePct: 80,
    erwartetPct: 60, ugPct: 75.3, ogPct: 84.2, urteil: 'traegt sich selbst',
    grund: 'erfuellt in 80.0 % (Untergrenze 75.3 %) gegen 60.0 % Erwartung' } });
  assert.match(html, /Serien-Buch/);
  assert.match(html, /trägt sich selbst/);
  assert.match(html, /Untergrenze 75\.3/);
});

test('ohne Buch-Datei erscheint gar nichts — kein leerer Rahmen', () => {
  assert.doesNotMatch(render(null), /Serien-Buch/);
});

test('ein leeres Buch sagt, dass es erst beginnt — nicht „nichts gemessen"', () => {
  const html = render({ zeilen: [], bilanz: { n: 0, treffer: 0, unaufloesbar: 0,
    urteil: 'sammelt', grund: '0 von 30 abgerechneten Serien' } });
  assert.match(html, /noch keine abgerechnete Serie/);
});

test('nicht abrechenbare Serien bleiben im Nenner sichtbar', () => {
  // Ecken und Karten stehen nicht im Endstand. Verschwänden sie still, sähe das Buch
  // vollständiger aus, als es ist.
  const html = render({ bilanz: { n: 40, treffer: 30, unaufloesbar: 7, quotePct: 75,
    erwartetPct: 60, ugPct: 62.5, ogPct: 84.6, urteil: 'traegt sich selbst', grund: 'x' } });
  assert.match(html, /7 nicht abrechenbar/);
});

test('das Frontend fällt kein eigenes Urteil — es liest das des Produzenten', () => {
  // Eine Quote über der Erwartung, aber mit Untergrenze darunter: der Produzent sagt „kein
  // Unterschied". Rechnete das Frontend selbst, stünde hier „trägt sich selbst".
  const html = render({ bilanz: { n: 35, treffer: 25, unaufloesbar: 0, quotePct: 71.4,
    erwartetPct: 60, ugPct: 57.7, ogPct: 82.1, urteil: 'kein Unterschied',
    grund: 'erfuellt in 71.4 % (57.7..82.1 %) — die Erwartung von 60.0 % liegt im Band' } });
  assert.match(html, /kein Unterschied/);
  assert.doesNotMatch(html, /trägt sich selbst/);
});
