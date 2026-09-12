// tests/frontend/bayes-hitrate.test.mjs — 12.09.2026 (Plattform-Audit)
//
// 🔴 Der Fund: das Bayesian-Panel rechnete `wins_when_triggered / n_observations`. Das sind zwei
// verschiedene Grundgesamtheiten — `n_observations` zählt NUR die Live-Ergebnisse (`n_live`),
// `wins`/`losses` dagegen Live + Backtest-Prior + CLV-Strom (update_signal_weights.py:426-433).
//
// Der Beweis stand auf der Seite und hat zwei Wochen niemanden gestört: MLS `fixture_congestion`
// zeigte **131 %**. Eine Trefferquote über 100 % gibt es nicht — das ist kein Rundungsfehler,
// sondern der Beleg, dass Zähler und Nenner nicht zusammengehören. Betroffen: 7 von 18 Liga- und
// 8 von 21 MLS-Signalen, jedes davon nach OBEN (Liga xG 85 statt 59,1 · Liga Smart-Money 64 statt
// 46,9 · MLS Travel 90 statt 51,7 · WM Opener-Move 52 statt 37,8). Mehrere Signale unter Münzwurf
// leuchteten wegen der festen 55-%-Schwelle grün.
//
// Die Tests laufen bewusst gegen die ECHTEN Gewichtsdateien: eine Unmöglichkeit wie >100 % kann
// man nur an echten Zahlen finden, und genau daran hätte es auffallen müssen.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const ROOT = new URL('../../', import.meta.url);
const JS = readFileSync(new URL('renderer.js', ROOT), 'utf8');
const lade = (f) => JSON.parse(readFileSync(new URL(f, ROOT), 'utf8'));

// Nur die Funktion selbst, und ohne Kommentare: ein Kommentar, der den Fehler BESCHREIBT, ist
// nicht der Fehler. Und die zweite Hit-Rate-Tabelle (CLV-Familien) rechnet wins/n aus DERSELBEN
// Grundgesamtheit — die darf hier nicht mit angeklagt werden.
const BLOCK = (() => {
  const ab = JS.indexOf('function _renderBayesianWeights(');
  const bis = JS.indexOf('\nfunction ', ab + 10);
  return JS.slice(ab, bis > 0 ? bis : JS.length).replace(/^\s*\/\/.*$/gm, '');
})();

const DATEIEN = {
  intl: ['SIGNAL_WEIGHTS', 'signal_weights.json'],
  liga: ['LIGA_SIGNAL_WEIGHTS', 'liga_signal_weights.json'],
  mls: ['MLS_SIGNAL_WEIGHTS', 'mls_signal_weights.json'],
};

function panel(ds) {
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: false, json: () => Promise.resolve(null) });
  w.eval(JS);
  for (const [global, datei] of Object.values(DATEIEN)) w[global] = lade(datei);
  // `_sharpDataset` ist ein `let` im Modul-Scope, also NICHT über window setzbar — der einzige
  // Weg ist der echte Umschalter. Sein Re-Render braucht DOM, den es hier nicht gibt; der
  // Datensatz steht zu dem Zeitpunkt aber schon.
  try { w._sharpSetDataset(ds); } catch (e) { /* Render ohne DOM — egal, ds ist gesetzt */ }
  return w._renderBayesianWeights();
}

const prozente = (html) => [...html.matchAll(/>(-?\d+)%<\/span>/g)].map(m => Number(m[1]));

for (const ds of Object.keys(DATEIEN)) {
  test(`[${ds}] keine Trefferquote über 100 % — der Beweis, dass Zähler und Nenner zusammengehören`, () => {
    const werte = prozente(panel(ds));
    assert.ok(werte.length > 0, 'das Panel zeigt gar keine Trefferquoten mehr');
    const kaputt = werte.filter(v => v > 100 || v < 0);
    assert.deepStrictEqual(kaputt, [],
      `unmögliche Trefferquote(n): ${kaputt.join(', ')} — Zähler und Nenner stammen wieder aus `
    + `verschiedenen Grundgesamtheiten`);
  });

  test(`[${ds}] die gezeigte Zahl ist wins/(wins+losses), nachgerechnet an jeder Zeile`, () => {
    const html = panel(ds);
    const gew = lade(DATEIEN[ds][1]);
    let geprueft = 0;
    for (const [name, w] of Object.entries(gew)) {
      if (!w || typeof w !== 'object') continue;
      const wins = w.wins_when_triggered || 0, losses = w.losses_when_triggered || 0;
      if (wins + losses <= 0) continue;
      const soll = Math.round((wins / (wins + losses)) * 100);
      // Der Tooltip trägt die Zusammensetzung — daran ist die Zeile eindeutig zu erkennen.
      const treffer = html.match(
        new RegExp(`title="${wins.toFixed(1)} von ${(wins + losses).toFixed(1)}[^"]*"[^>]*>(-?\\d+)%`));
      if (!treffer) continue;     // Signal steht in dieser Ansicht nicht auf der Liste
      assert.strictEqual(Number(treffer[1]), soll, `${name}: gezeigt ${treffer[1]}%, richtig ${soll}%`);
      geprueft++;
    }
    assert.ok(geprueft >= 5, `nur ${geprueft} Zeilen nachgerechnet — der Abgleich greift nicht mehr`);
  });
}

test('⭐ Fehlerklasse: nirgends wird wieder wins durch n_observations geteilt', () => {
  // Der eigentliche Wächter. Die Tests oben prüfen den Zustand von heute; dieser prüft die Form,
  // und die kann auch ein Signal betreffen, das es noch gar nicht gibt.
  const stellen = [...BLOCK.matchAll(/wins[^;\n]{0,80}\/[^;\n]{0,40}n_observations|n_observations[^;\n]{0,80}\/[^;\n]{0,40}wins/g)];
  assert.deepStrictEqual(stellen.map(m => m[0]), [],
    'wins_when_triggered zählt Live + Prior + CLV, n_observations nur Live. Ein Quotient aus '
  + 'beiden ist keine Trefferquote, sondern eine Zahl ohne Grundgesamtheit.');
});

test('⭐ die Farbe hängt am Nullpunkt des Signals, nicht an festen 55 %', () => {
  assert.ok(!/hitRate >= 55/.test(BLOCK),
    'Eine feste Schwelle lässt Signale grün leuchten, die unter ihrem eigenen Nullpunkt liegen — '
  + 'genau das war bei Liga Smart-Money (46,9 % bei Nullpunkt ~52 %) der Fall.');
  assert.ok(/hitRate >= neutral/.test(BLOCK), 'der Nullpunkt (w.neutral) wird nicht mehr benutzt');
});

test('Gegenprobe: ohne neutral wird gar nicht eingefärbt statt falsch', () => {
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: false, json: () => Promise.resolve(null) });
  w.eval(JS);
  w.LIGA_SIGNAL_WEIGHTS = { xg_strength: { weight: 1.2, n_observations: 10, wins_when_triggered: 9,
                                           losses_when_triggered: 1 } };   // kein `neutral`
  w._sharpDataset = 'liga';
  const html = w._renderBayesianWeights();
  assert.match(html, />90%</, 'die Zahl selbst muss trotzdem stimmen');
  assert.ok(!/#3fb950;font-weight:700;">90%/.test(html),
    'ohne bekannten Nullpunkt darf 90 % nicht grün behaupten, gut zu sein');
});
