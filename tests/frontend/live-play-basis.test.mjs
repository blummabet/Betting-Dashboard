// tests/frontend/live-play-basis.test.mjs — 03.09.2026
//
// Lucas: „🔥 Heute spielenswert … 8/10 · BET · Hapoel Tel Aviv vs Beitar 🔴 LIVE → Hapoel @48¢ ·
// großes Geld (74%) → $22K · Steam läuft rein (+6.0pp)" — gepusht um 19:28. Da stand es 3:0 und
// das Spiel lief in der 92. Minute. „Die 48 Cent gab es ewig zuvor, aber da kam nie ne Push."
//
// Die Zahlen in diesem Test sind nicht erfunden. Sie stehen so in den Dateien:
//
//   poly_money_broad_close.json  isr-hta-bei-2026-09-03
//     capturedAt 17:27:50, hoursToKickoff 0.09  → fünf Minuten VOR Anpfiff
//     prices  {Hapoel 0.475, Draw 0.275, Beitar 0.265}      → die 48¢ aus dem Push
//     shares  {3507.9, 1049.1, 199.0} = 73,7% auf Hapoel    → die 74% aus dem Push
//     totalUsd 22251                                        → die $22K aus dem Push
//
//   poly_money_broad_live.json   isr-hta-bei-2026-09-03
//     prices  {Hapoel 0.5, Draw 0.5, Beitar 0.5}            → Summe 1,5 bei drei Ausgängen
//
// Der Push trug also durchweg VORSPIEL-Zahlen und klebte ein „🔴 LIVE" davor. Und der
// Live-Schnappschuss, den niemand gefragt hat, hatte gar keinen Preis: drei sich ausschließende
// Ausgänge auf exakt 0,500 sind ein leeres Orderbuch, dessen Mittelwert zurückfällt — im
// Live-File betraf das an dem Tag 21 von 62 Märkten (34%), im Close-File 4 von 2002 (0,2%).
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const ROOT = new URL('../../', import.meta.url);
const JS = readFileSync(new URL('poly-wallets.js', ROOT), 'utf8');

function fenster() {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="polyWalletsPanel"></div></body>',
    { url: 'https://test.local/', runScripts: 'outside-only', pretendToBeVisual: true });
  dom.window.fetch = () => Promise.resolve({ ok: false, json: () => Promise.resolve(null) });
  dom.window.eval(JS);
  return dom.window;
}
const W = fenster();

// ── Ein Preis muss ein Preis sein ───────────────────────────────────────────
test('drei Ausgänge auf exakt 0,500 sind kein Preis, sondern ein leeres Buch', () => {
  assert.equal(W._pwPreisBrauchbar({ a: 0.5, b: 0.5, c: 0.5 }), false);
});

test('auch bei ZWEI Ausgängen — dort summiert 0,5/0,5 sauber auf 1,0', () => {
  // Die Summenprüfung allein würde das durchwinken. Genau deshalb braucht es beide Regeln:
  // 21 der 34% betroffenen Live-Märkte an dem Tag waren Zwei-Wege-Märkte (MLB, Tennis, eSport).
  assert.equal(W._pwPreisBrauchbar({ a: 0.5, b: 0.5 }), false);
});

test('ein echter Drei-Weg-Preis geht durch', () => {
  assert.equal(W._pwPreisBrauchbar({ Hapoel: 0.475, Draw: 0.275, Beitar: 0.265 }), true);
});

test('Preise, die sich nicht auf 1 summieren, sind unbrauchbar', () => {
  assert.equal(W._pwPreisBrauchbar({ a: 0.9, b: 0.9 }), false);
  assert.equal(W._pwPreisBrauchbar({ a: 0.2, b: 0.2, c: 0.2 }), false);
});

test('ein einzelner Preis ist keine Verteilung', () => {
  assert.equal(W._pwPreisBrauchbar({ a: 0.6 }), false);
  assert.equal(W._pwPreisBrauchbar({}), false);
  assert.equal(W._pwPreisBrauchbar(null), false);
});

test('nicht-numerische Werte zählen nicht als Preis', () => {
  assert.equal(W._pwPreisBrauchbar({ a: '0.4', b: '0.6' }), false);
});

// ── Live wird mit Live-Zahlen bewertet ──────────────────────────────────────
const CLOSE = {
  capturedAt: '2026-09-03T17:27:50.262817+00:00',
  hoursToKickoff: 0.09, league: 'SOCCER', sport: 'Fußball', totalUsd: 22251,
  prices: { 'Hapoel Tel Aviv FC': 0.475, 'Draw': 0.275, 'Beitar Jerusalem FC': 0.265 },
  shares: { 'Hapoel Tel Aviv FC': 3507.95, 'Draw': 1049.13, 'Beitar Jerusalem FC': 198.97 },
};
const LIVE = {
  capturedAt: '2026-09-03T19:19:00.000000+00:00',
  hoursToKickoff: -1.86, league: 'SOCCER', sport: 'Fußball', totalUsd: 22251,
  prices: { 'Hapoel Tel Aviv FC': 0.5, 'Draw': 0.5, 'Beitar Jerusalem FC': 0.5 },
  shares: { 'Hapoel Tel Aviv FC': 3692.58, 'Draw': 1907.50, 'Beitar Jerusalem FC': 375.41 },
};

test('der Merge nimmt Preis, Geld und Volumen aus dem laufenden Spiel', () => {
  const m = W._pwLiveMerge(CLOSE, LIVE);
  assert.deepEqual(m.prices, LIVE.prices, 'der Preis kommt aus dem Live-Satz');
  assert.deepEqual(m.shares, LIVE.shares, 'das Geld auch');
  assert.equal(m.preisQuelle, 'live');
});

test('Stammdaten bleiben aus dem Close-Satz, der Live-Scan führt sie nicht immer mit', () => {
  const m = W._pwLiveMerge(CLOSE, { prices: { a: 0.4, b: 0.6 } });
  assert.equal(m.league, 'SOCCER');
  assert.equal(m.sport, 'Fußball');
  assert.equal(m.capturedAt, CLOSE.capturedAt, 'der Anpfiff-Stempel darf nicht wandern');
});

test('der Merge fasst den Close-Satz nicht an', () => {
  const kopie = JSON.parse(JSON.stringify(CLOSE));
  W._pwLiveMerge(CLOSE, LIVE);
  assert.deepEqual(CLOSE, kopie);
});

test('genau dieser Fall fliegt jetzt raus', () => {
  // Der Live-Satz ist das, was ein Live-Play bewerten müsste — und er hat keinen Preis.
  const m = W._pwLiveMerge(CLOSE, LIVE);
  assert.equal(W._pwPreisBrauchbar(m.prices), false,
    'mit den Zahlen aus dem laufenden Spiel ist das kein Play, sondern ein leeres Buch');
  // Und mit den Vorspiel-Zahlen sah alles gesund aus — das ist der Fehler, den wir zumachen.
  assert.equal(W._pwPreisBrauchbar(CLOSE.prices), true);
  assert.equal(Math.round(CLOSE.prices['Hapoel Tel Aviv FC'] * 100), 48,
    'die 48¢ aus der Nachricht stammen aus dem Close-Satz, fünf Minuten vor Anpfiff');
  const geld = CLOSE.shares['Hapoel Tel Aviv FC'] /
    Object.values(CLOSE.shares).reduce((a, b) => a + b, 0);
  assert.equal(Math.round(geld * 100), 74, 'und die 74% ebenfalls');
  // Zum Vergleich: dieselbe Rechnung auf dem Live-Satz ergibt 62%, nicht 74. Die Nachricht
  // zeigte also nachweislich die Vorspiel-Zahl, nicht die laufende.
  const geldLive = LIVE.shares['Hapoel Tel Aviv FC'] /
    Object.values(LIVE.shares).reduce((a, b) => a + b, 0);
  assert.equal(Math.round(geldLive * 100), 62);
});

// ── Spielbarkeit nach Anpfiff ───────────────────────────────────────────────
function nachAnpfiff(stundenSeitAnpfiff, sport) {
  // capturedAt = jetzt, hoursToKickoff negativ → _pwRealHtk liefert genau diesen Wert
  return { capturedAt: new Date().toISOString(), hoursToKickoff: -stundenSeitAnpfiff,
           league: sport === 'Fußball' ? 'SOCCER' : 'ATP', sport };
}

test('Fußball: die 92. Minute ist kein Play mehr', () => {
  assert.equal(W._pwLiveZuSpaet(nachAnpfiff(1.55, 'Fußball')), true);
});

test('Fußball: die erste Stunde bleibt spielbar', () => {
  assert.equal(W._pwLiveZuSpaet(nachAnpfiff(0.9, 'Fußball')), false);
});

test('Fußball: die Grenze liegt bei 75 Minuten', () => {
  assert.equal(W._pwLiveZuSpaet(nachAnpfiff(1.2, 'Fußball')), false);
  assert.equal(W._pwLiveZuSpaet(nachAnpfiff(1.3, 'Fußball')), true);
});

test('Tennis darf länger laufen — ein Fünfsatzer ist nicht entschieden, nur lang', () => {
  assert.equal(W._pwLiveZuSpaet(nachAnpfiff(1.55, 'Tennis')), false);
  assert.equal(W._pwLiveZuSpaet(nachAnpfiff(2.5, 'Tennis')), true);
});

test('ohne Anpfiff-Angabe wird nichts weggeworfen', () => {
  assert.equal(W._pwLiveZuSpaet({ league: 'SOCCER', sport: 'Fußball' }), false);
});

test('Spielbarkeit und Markt-Echtheit sind zwei verschiedene Fragen', () => {
  // 03.09.2026: sie wurden verwechselt. PW_STALE_AFTER_KO_H_FOOTBALL = 2,5h beantwortet
  // „ist dieser Markt noch echt?" — in der 92. Minute liegt man da komfortabel drunter.
  const m = nachAnpfiff(1.55, 'Fußball');
  assert.equal(W._pwKoStale(m), false, 'der Markt gilt weiter als echt');
  assert.equal(W._pwLiveZuSpaet(m), true, 'spielbar ist er trotzdem nicht mehr');
});

// ── Der Pfad selbst ─────────────────────────────────────────────────────────
const CODE = JS.replace(/^\s*\/\/.*$/gm, '');

test('_pwTopPlays bewertet live nicht mehr den Close-Satz', () => {
  const von = CODE.indexOf('function _pwTopPlays');
  const bis = CODE.indexOf('function _pwPublicMinConv');
  assert.ok(von > 0 && bis > von, 'Anker weg');
  const block = CODE.slice(von, bis);
  assert.ok(/_pwLiveMerge\(m,\s*_lnm\)/.test(block), 'der Live-Satz muss in die Bewertung');
  assert.ok(/_pwShortlistScore\(k,\s*_mBewert\)/.test(block),
    'gescort wird der gemergte Satz, nicht mehr roh der Close-Satz');
  assert.ok(/_pwPreisBrauchbar/.test(block));
  assert.ok(/_pwLiveZuSpaet/.test(block));
});

test('jeder Play sagt, woher sein Preis stammt', () => {
  const von = CODE.indexOf('function _pwTopPlays');
  const block = CODE.slice(von, CODE.indexOf('function _pwPublicMinConv'));
  assert.ok(/preisQuelle\s*=/.test(block),
    'eine Zahl muss ihre Basis nennen — auch diese');
});
