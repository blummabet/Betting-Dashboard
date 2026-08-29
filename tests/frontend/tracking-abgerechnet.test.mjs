// tests/frontend/tracking-abgerechnet.test.mjs — 29.08.2026
//
// Lucas: „Im Tracking der Cards seh ich die abgerechneten nicht. Hätte ich gerne per Klick."
//
// Zwei getrennte Befunde dahinter:
//
//  1. Der Endstand fehlte komplett. _buildPicksTable las fx.scoreHome/fx.scoreAway — Felder,
//     die es in liga-data.json, mls-data.json und wm2026-data.json NICHT gibt. Der Stand liegt
//     unter fx.result = {status, home_score, away_score, stats}. Ergebnis: jede abgerechnete
//     Zeile trug einen grünen Haken, aber niemand konnte sehen wie das Spiel ausging.
//     Gemessen am echten Datensatz: 0 von 44 abgerechneten Liga-Spielen zeigten einen Stand.
//     K.O.-Zeilen bauen ihr fx-Objekt selbst zusammen und liessen result einfach weg.
//
//  2. Die Klappzeile sagte nur „N ausgewertete Picks". Ob es gut oder schlecht lief, stand
//     erst NACH dem Aufklappen da. Jetzt trägt die Zeile die Bilanz: Treffer, Fehlschläge, P&L.
//
// Zusätzlich: die NOBET-Liste (im echten Liga-Datensatz 174 Zeilen) stand dauerhaft offen.
// Gleiche Behandlung wie die abgerechneten Picks — eingeklappt, Inhalt auf Klick.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';

const ROOT = new URL('../../', import.meta.url);
const SRC  = readFileSync(new URL('wm2026-tracking.js', ROOT), 'utf8');

// ── Mini-Datensatz im Format von liga-data.json ────────────────────────────
const DATA = {
  groups: {
    ENG: {
      name: 'Premier League',
      teams: [{ id: '1', name: 'Heim FC' }, { id: '2', name: 'Gast FC' }],
      fixtures: [
        {                                   // abgerechnet, mit Stand + xG
          matchday: 1, home: '1', away: '2', date: '2020-01-01', time: '15:30',
          result: { status: 'FT', home_score: 3, away_score: 1, stats: { xgHome: 2.4, xgAway: 0.7 } },
        },
        {                                   // offen
          matchday: 2, home: '2', away: '1', date: '2099-01-01', time: '15:30',
        },
      ],
    },
  },
  koFixtures: [{                            // K.O.: baut sein fx selbst → result muss mit
    round: 'F', home: '1', away: '2', date: '2020-02-01', kickoff: '2020-02-01T20:00:00Z',
    bothResolved: true,
    result: { status: 'FT', home_score: 0, away_score: 2, stats: { homeXg: 0.3, awayXg: 1.9 } },
  }],
  picks: {
    'ENG-1-1-2': [{ market: 'Heimsieg',   verdict: 'BET',     odds: 2.0, result: 'WIN',  stake: 10 },
                  { market: 'Over 2.5',   verdict: 'ABWÄGEN', odds: 1.8, result: 'LOSS', stake: 5 },
                  { market: 'BTTS',       verdict: 'NOBET',   odds: 1.9, nobetReason: 'Edge gekippt' }],
    'ENG-2-2-1': [{ market: 'Auswärtssieg', verdict: 'BET',   odds: 2.5, result: null,  stake: 10 }],
    'KO-F-1-2':  [{ market: 'Auswärtssieg', verdict: 'BET',   odds: 3.0, result: 'WIN', stake: 10 }],
  },
};

const LOG = [];   // jede angefragte URL, in Reihenfolge

function render() {
  let html = '';
  LOG.length = 0;
  const panel = { get innerHTML() { return html; }, set innerHTML(v) { html = v; }, style: {} };
  const g = {
    document: { getElementById: id => (id === 'trackingV2Panel' ? panel : null), querySelectorAll: () => [] },
    // raw/main antwortet in diesem Test NICHT — damit laeuft jeder Testlauf ueber den
    // Rueckfall auf den Pages-Snapshot. Genau der Weg, der offline und bei raw-Stoerung greift.
    fetch: async (u) => {
      LOG.push(String(u));
      return String(u).startsWith('liga-data.json')
        ? { ok: true, json: async () => JSON.parse(JSON.stringify(DATA)) }
        : { ok: false, json: async () => null };
    },
  };
  const prev = {};
  for (const k of Object.keys(g)) { prev[k] = globalThis[k]; globalThis[k] = g[k]; }
  globalThis.window = globalThis;
  // eslint-disable-next-line no-eval
  (0, eval)(SRC);
  return window.initNationalTracking().then(() => {
    for (const k of Object.keys(g)) globalThis[k] = prev[k];
    return html;
  });
}

test('abgerechnete Picks stecken in einer aufklappbaren <details>-Klappe', async () => {
  const html = await render();
  assert.match(html, /<details class="wm-trk-resolved"/);
  const sum = html.slice(html.indexOf('<details class="wm-trk-resolved"'));
  const kopf = sum.slice(0, sum.indexOf('</summary>')).replace(/<[^>]+>/g, ' ');
  assert.match(kopf, /3 abgerechnete Picks/, 'Anzahl gehört in die Klappzeile');
  assert.match(kopf, /aufklappen/, 'Klapp-Hinweis fehlt');
});

test('die Klappzeile trägt die Bilanz — ohne dass man sie öffnen muss', async () => {
  const html = await render();
  const sum = html.slice(html.indexOf('<details class="wm-trk-resolved"'));
  const kopf = sum.slice(0, sum.indexOf('</summary>')).replace(/<[^>]+>/g, ' ');
  assert.match(kopf, /2 gewonnen/);
  assert.match(kopf, /1 verloren/);
  // 2×WIN @2.0/€10 und @3.0/€10 = +10 +20 ; 1×LOSS €5 → +€25.00
  assert.match(kopf, /\+€25\.00/, 'P&L der abgerechneten Picks fehlt in der Klappzeile');
});

test('Endstand kommt aus fx.result.home_score/away_score (nicht aus fx.scoreHome)', async () => {
  const html = await render();
  assert.ok(!/scoreHome/.test(SRC.split('function _fxScore')[1].split('function ')[1] || ''),
    'ausserhalb von _fxScore darf scoreHome nicht mehr direkt gelesen werden');
  assert.match(html, /wm-trk-score">3 : 1/, 'Gruppenspiel-Endstand fehlt');
  assert.match(html, /wm-trk-score">0 : 2/, 'K.O.-Endstand fehlt (fx.result wurde nicht mitgereicht)');
});

test('xG steht unter dem Stand — beide Feldnamen (xgHome/homeXg)', async () => {
  const html = await render();
  assert.match(html, /xG 2\.40 : 0\.70/, 'Gruppenspiel-xG (xgHome/xgAway)');
  assert.match(html, /xG 0\.30 : 1\.90/, 'K.O.-xG (homeXg/awayXg)');
});

test('offene Picks bleiben ohne Klick sichtbar', async () => {
  const html = await render();
  const vorKlappe = html.slice(0, html.indexOf('<details class="wm-trk-resolved"'));
  assert.match(vorKlappe, /Auswärtssieg/, 'der offene Pick muss oberhalb der Klappe stehen');
});

test('NOBET-Liste ist eingeklappt statt dauerhaft offen', async () => {
  const html = await render();
  assert.match(html, /<details class="wm-trk-nobet"/);
  const nb = html.slice(html.indexOf('<details class="wm-trk-nobet"'));
  assert.match(nb.slice(0, nb.indexOf('</summary>')).replace(/<[^>]+>/g, ' '), /1 Kein Bet/);
});

test('die Daten kommen raw-zuerst, der Snapshot ist nur der Rückfall', async () => {
  await render();
  const liga = LOG.filter(u => u.includes('liga-data.json'));
  assert.ok(liga.length >= 2, 'es gab keinen zweiten Anlauf — kein Rückfall vorhanden');
  assert.match(liga[0], /^https:\/\/raw\.githubusercontent\.com\//,
    'der erste Anlauf ging nicht an raw/main — dann hängt das Tracking wieder am stündlichen Pages-Deploy');
  assert.match(liga[1], /^liga-data\.json/,
    'der zweite Anlauf ist nicht der relative Snapshot-Pfad');
});

test('scheitern beide Wege, sagt die Fehlermeldung das auch', async () => {
  // Vorher stand da „HTTP 404" — was nach kaputter Datei aussieht, obwohl in Wahrheit
  // zwei verschiedene Wege gescheitert sind. Die Meldung soll beide nennen.
  const stelle = SRC.indexOf('war weder ueber raw/main noch im Pages-Snapshot lesbar');
  assert.ok(stelle > 0, 'die Fehlermeldung nennt die zwei Wege nicht');
});
