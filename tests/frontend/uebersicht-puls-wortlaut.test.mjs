// tests/frontend/uebersicht-puls-wortlaut.test.mjs — 15.09.2026 (Lucas-Uebersicht-Check)
//
// Zwei Funde in EINER Kachelzeile des Puls, beide derselben Klasse: ein Wort bzw. eine Zahl,
// die etwas anderes benennt als das, was danebensteht.
//
// 1) „🎯 Cards n30 · 27 gew." stand direkt neben „63 % Treffer 17–10". `nGraded` ist die Zahl
//    der ABGERECHNETEN Picks (wins+losses), nicht der gewonnenen — aber „gew." liest sich als
//    „gewonnen", und 17 Siege daneben machen die Verwechslung teuer. Der Fix vom 03.09. hatte
//    die richtige Zahl und das falsche Wort.
// 2) „💷 Betfair n25876" stand auf DEMSELBEN Board neben „25.985 Plays" im Register. Dieselbe
//    Grundmenge, zwei Alter: `dashboard_pulse.json` kopiert den Aggregat-Block aus
//    `betfair_track_record.json` und wird 3–4×/Tag gebaut, die Quelle alle ~15 Min. Die
//    Uebersicht laedt die Quelle selbst — also liest die Kachel dort.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const MOD = new URL('../../main-dashboard.js', import.meta.url);
function load() {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="mainDashPanel"></div></body>', { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve(null) });
  w.eval(readFileSync(MOD, 'utf8'));
  return w;
}
const PULSE = {
  _meta: { generatedAt: new Date().toISOString() },
  n: 30, nClv: 17, nGraded: 27, wins: 17, losses: 10, winPct: 63.0,
  avgClvPP: -2.5, pctBeatClose: 35,
  betfair: { n: 25876, hitPct: 52.7, roiPct: -0.7 },
};
function seed(w, extra) {
  w._mdState.data = Object.assign({
    liga: null, mls: null, ligaStreaks: null, mlsStreaks: null, betfair: null, whales: null,
    pulse: JSON.parse(JSON.stringify(PULSE)), bfOverview: null, moneyMap: null,
  }, extra || {});
}

test('die Cards-Kachel nennt 27 abgerechnet, nicht „gew." neben 17 Siegen', () => {
  const w = load(); seed(w); w._renderMainDash();
  const h = w.document.getElementById('mainDashPanel').innerHTML;
  assert.match(h, /27 abgerechnet/);
  assert.ok(!/27 gew\./.test(h), 'Abkuerzung „gew." neben einer Trefferzahl — genau der Fund vom 15.09.');
  assert.match(h, /Treffer 17–10/);
});

test('die Betfair-Kachel liest das Track-Record, nicht die aeltere Kopie im Puls', () => {
  const w = load();
  seed(w, { bfTrack: { generatedAt: new Date().toISOString(),
                       global: { n: 25985, hitRate: 0.5264, roi: -0.008 } } });
  w._renderMainDash();
  const h = w.document.getElementById('mainDashPanel').innerHTML;
  assert.match(h, /n25985/);
  assert.ok(!/n25876/.test(h), 'die Kachel zeigt die 2 h alte Kopie, waehrend die Quelle geladen ist');
  assert.match(h, /52\.6%/);
});

test('ohne Track-Record bleibt der Puls-Block der Rueckfall — keine leere Kachel', () => {
  const w = load(); seed(w); w._renderMainDash();
  const h = w.document.getElementById('mainDashPanel').innerHTML;
  assert.match(h, /n25876/);
});
