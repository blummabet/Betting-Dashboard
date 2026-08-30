// tests/frontend/uebersicht-anpfiff.test.mjs — 30.08.2026
//
// Aus Lucas' zweitem Checkup. Zwei Kacheln liefen über ALLE Fixtures, ohne den Anpfiff zu prüfen:
//
//   „Beste Cards"      zeigte FC Cincinnati — Anpfiff 179 Stunden her, also seit siebeneinhalb
//                      Tagen gespielt. Beide angezeigten BET-Cards waren vorbei.
//   „Pinnacle-Steam"   zeigte drei von fünf Zeilen auf gespielten Partien, die oberste seit
//                      331 Stunden (14 Tage). Von 299 Steam-Picks im Bestand waren 192 vorbei.
//
// Deshalb standen dort auch dieselben Zahlen wie am Vortag: die Spiele waren durch, die Werte
// konnten sich gar nicht mehr bewegen. Jede andere Kachel filtert nach Zeit — diese zwei nie.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const MOD = new URL('../../main-dashboard.js', import.meta.url);
const vor = (h) => new Date(Date.now() + h * 3600e3).toISOString();

function render(fixtures) {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="mainDashPanel"></div></body>',
    { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve(null) });
  w.eval(readFileSync(MOD, 'utf8'));
  w._mdState.data = { liga: { _meta: { picksUpdatedAt: vor(-0.1) }, groups: { g: { fixtures } } },
    mls: null, ligaStreaks: null, mlsStreaks: null, betfair: null, whales: null };
  w._renderMainDash();
  return w.document.getElementById('mainDashPanel');
}
// Die Kachel per DOM holen, nicht per String-Slice: „Money Map" steht auch in der KPI-Leiste
// darueber, ein indexOf-Fenster erwischt damit den falschen Abschnitt.
function kachel(panel, titel) {
  const t = [...panel.querySelectorAll('.md-tile-t')].find(e => e.textContent.trim() === titel);
  return t ? t.closest('section').innerHTML : '';
}
const fx = (name, h, picks) => ({ home: name, away: 'Gegner', homeName: name, awayName: 'Gegner',
  league: 'Bundesliga', kickoff: vor(h), picks });
const bet = { market: 'Heimsieg', verdict: 'BET', convictionScore: 8, odds: 1.8, edgePP: 4 };
const steam = { market: 'Heimsieg', verdict: 'ABWÄGEN', source: 'steam', steamMovePP: 9.0, odds: 2.1 };

test('eine BET-Card auf einem gespielten Spiel ist keine Empfehlung mehr', () => {
  const k = kachel(render([fx('Gestern', -179, [bet]), fx('Heute', 4, [bet])]), 'Beste Cards');
  assert.match(k, /Heute/);
  assert.doesNotMatch(k, /Gestern/, '179 Stunden nach Anpfiff ist das Historie');
});

test('ein laufendes Spiel bleibt kurz sichtbar', () => {
  // Anpfiff war vor einer Stunde — das Spiel läuft. Es abrupt verschwinden zu lassen wäre
  // genauso irreführend wie es ewig zu zeigen.
  assert.match(kachel(render([fx('Laeuft', -1, [bet])]), 'Beste Cards'), /Laeuft/);
});

test('Pinnacle-Steam zeigt keine gespielten Partien mehr', () => {
  const k = kachel(render([fx('Vorbei', -331, [steam]), fx('Kommt', 6, [steam])]), 'Pinnacle-Steam');
  assert.match(k, /Kommt/);
  assert.doesNotMatch(k, /Vorbei/);
});

test('ein Spiel in ferner Zukunft ist auch keine Empfehlung', () => {
  // Real Sociedad v Celta stand mit Anpfiff in 105 Stunden in der Steam-Kachel.
  const p = render([fx('Naechste Woche', 147, [bet, steam])]);
  assert.doesNotMatch(kachel(p, 'Beste Cards'), /Naechste Woche/);
  assert.doesNotMatch(kachel(p, 'Pinnacle-Steam'), /Naechste Woche/);
});

test('ohne Anpfiff wird nicht geraten', () => {
  const p = render([{ home: 'Ohnezeit', away: 'X', homeName: 'Ohnezeit', awayName: 'X',
    league: 'Bundesliga', picks: [bet] }]);
  assert.doesNotMatch(kachel(p, 'Beste Cards'), /Ohnezeit/,
    'fehlende Zeitangabe ist keine Erlaubnis');
});
