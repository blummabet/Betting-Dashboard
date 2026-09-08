// tests/frontend/poly-terminal-ueberzeugung.test.mjs — 07.09.2026
//
// Lucas: „mir hat gefallen, wenn ich geklickt hab, hatte man Zusatz-Infos, schöne Grafik,
// Wallets gelistet. Aber es war halt nichtssagend und ich konnte damit nichts anfangen."
//
// Der Drawer hatte sechs hübsche Kästen und keine Aussage. Sechs Zahlen nebeneinander sind
// keine Überzeugung — die Arbeit, sie zu verrechnen, blieb bei jedem Klick beim Leser.
//
// Diese Tests halten fest, was die Fläche seither leisten MUSS:
//   1. Ein Einsatz steht gegen die eigene Norm der Wallet, nicht nackt.
//   2. Es gibt eine Für-/Gegen-Bilanz, und jede Zeile trägt ihre Basis.
//   3. Was fehlt, steht als „fehlt" da — nicht als stiller Nuller.
//   4. Die Gegenrede wird nicht verschwiegen (auch nicht die über die Quelle selbst).
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const PW = new URL('../../poly-wallets.js', import.meta.url);
const RAWJSON = new URL('../../raw-json.js', import.meta.url);

function win() {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="polyWalletsPanel"></div></body>',
    { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  w.eval(readFileSync(RAWJSON, 'utf8'));
  w.eval(readFileSync(PW, 'utf8'));
  return w;
}

// Der Drawer liest aus dem Modul-Cache; der haengt nicht am window. Deshalb wird er ueber die
// exportierte Testschnittstelle gesetzt (dieselbe, die initPolyWallets fuellt).
function mitCache(w, cache) {
  w._pwTestSetCache(cache);
  return w;
}

const NORM = { generatedAt: '2026-09-07T18:00:00Z', minN: 8,
  wallets: {
    '0xaaa': { n: 41, basis: 'gelernt', median: 2400, p90: 9000, max: 30000 },
    '0xbbb': { n: 12, basis: 'gelernt', median: 500, p90: 900, max: 1500 },
    '0xccc': { n: 3, basis: 'zu duenn', median: null },
  } };

const MARKT = { totalUsd: 120000, league: 'Serie A', sport: 'Fußball',
  prices: { Heim: 0.55, Auswärts: 0.45 }, shares: { Heim: 0.7, Auswärts: 0.3 },
  whales: [ { wallet: '0xaaa', usd: 30000, side: 'Heim' },
            { wallet: '0xbbb', usd: 9000, side: 'Auswärts' },
            { wallet: '0xccc', usd: 5000, side: 'Heim' } ] };

const ROW = { key: 'k1', match: 'A vs B', side: 'Heim', conv: 8, reasons: [],
              price: 0.55, vol: 120000, htk: 3, league: 'Serie A' };

test('der Einsatz steht gegen die eigene Norm der Wallet', () => {
  const w = mitCache(win(), { broadLive: { k1: MARKT }, walletNorm: NORM });
  const html = w._pwTermWhaleTape(ROW);
  assert.match(html, /× eigene Norm/, 'die Spalte fehlt');
  assert.match(html, /×12\.5/, '$30.000 gegen Median $2.400 = ×12,5');
  assert.match(html, /×18/, '$9.000 gegen Median $500 = ×18');
  assert.match(html, /Rekord/, 'ein Einsatz über dem bisherigen Maximum muss auffallen');
});

test('ohne gelernte Norm wird kein Faktor erfunden', () => {
  const w = mitCache(win(), { broadLive: { k1: MARKT }, walletNorm: NORM });
  const html = w._pwTermWhaleTape(ROW);
  // 0xccc hat basis 'zu duenn' -> „neu", kein ×
  assert.match(html, /neu/, 'Wallet ohne Norm muss als „neu" dastehen');
});

test('die Kopfzeile zählt Für und Gegen — mit Basis je Zeile', () => {
  const w = mitCache(win(), { broadLive: { k1: MARKT }, walletNorm: NORM });
  const html = w._pwTermUrteil(ROW);
  assert.match(html, /über eigener Norm auf dieser Seite/);
  assert.match(html, /GEGENSEITE/, 'die Gegenseite darf nicht verschwiegen werden');
  assert.match(html, /Median \$2\.400 über 41 Einsätze/, 'jede Zeile trägt ihre Basis');
});

test('die gemessene Schwäche der Geld-Seite steht als Gegenargument da', () => {
  // Genau der Punkt, an dem das Terminal etwas behauptet, was die Daten nicht stützen: es
  // sortiert nach Geld, und die Messung sagt, die Geld-Verteilung ist schlechter kalibriert.
  //
  // 07.09.2026, eigener Fehler im ersten Anlauf: hier stand der TREFFERQUOTEN-Vergleich
  // („37% gegen 46%"). Das Urteil des Produzenten hängt aber am Brier-Vergleich — und die
  // Preis-Seite ist per Konstruktion der Favorit, trifft also ohnehin öfter. Eine Trefferquote
  // ohne die Quoten ist keine Zahl (Bug-Klasse 6), und sie darf erst recht nicht als Beleg für
  // ein Urteil dastehen, das aus einer anderen Rechnung stammt.
  const w = mitCache(win(), { broadLive: { k1: MARKT }, walletNorm: NORM,
    moneyAcc: { n: 35, moneyHitRate: 0.371, priceHitRate: 0.457, brierMoney: 0.9911,
                brierPrice: 0.6213, verdict: 'preis_besser', urteilMinN: 30 } });
  const html = w._pwTermUrteil(ROW);
  assert.match(html, /schlechter kalibriert als der Preis/);
  assert.match(html, /Brier 0\.99 gegen 0\.62 · n35/, 'das Urteil muss seine eigene Rechnung zeigen');
  assert.match(html, /Treffer 37% vs 46%/, 'die Trefferquote bleibt Beschreibung, nicht Beleg');
});

test('das Gegenteil würde genauso dastehen', () => {
  // Sonst wäre die Fläche nur in eine Richtung ehrlich.
  const w = mitCache(win(), { broadLive: { k1: MARKT }, walletNorm: NORM,
    moneyAcc: { n: 40, moneyHitRate: 0.5, priceHitRate: 0.5, brierMoney: 0.41,
                brierPrice: 0.55, verdict: 'geld_schaerfer', urteilMinN: 30 } });
  assert.match(w._pwTermUrteil(ROW), /besser kalibriert als der Preis/);
});

test('unter der Mindestzahl wird das Verdikt NICHT gezeigt', () => {
  const w = mitCache(win(), { broadLive: { k1: MARKT }, walletNorm: NORM,
    moneyAcc: { n: 12, moneyHitRate: 0.30, priceHitRate: 0.60, verdict: 'preis_besser', urteilMinN: 30 } });
  assert.ok(!/Geld-Seite trifft gemessen schlechter/.test(w._pwTermUrteil(ROW)),
    'n12 unter urteilMinN=30 ist kein Urteil');
});

test('Markout trägt als Argument nur mit Verdikt aus dem Artefakt', () => {
  const w = mitCache(win(), { broadLive: { k1: MARKT }, walletNorm: NORM,
    markout: { verdict: 'traegt', netMakerPP: 1.912, fills: 3758, headlineHorizon: '2.0h' } });
  assert.match(w._pwTermUrteil(ROW), /Markout \+1\.9pp netto über 3\.758 Fills/);
  const w2 = mitCache(win(), { broadLive: { k1: MARKT }, walletNorm: NORM,
    markout: { verdict: 'kein Urteil', netMakerPP: 1.9, fills: 20 } });
  assert.ok(!/Markout/.test(w2._pwTermUrteil(ROW)), 'ohne Verdikt kein Argument');
});

test('was fehlt, steht als Loch in der Begründung da', () => {
  const w = mitCache(win(), { broadLive: { k1: Object.assign({}, MARKT, { whales: [] }) }, walletNorm: NORM });
  const html = w._pwTermUrteil(ROW);
  assert.match(html, /Was fehlt/);
  assert.match(html, /kein Pinnacle-Anker/);
  assert.match(html, /keine Whale-Positionen erfasst/);
});

test('ohne jede Evidenz wird nichts behauptet', () => {
  const w = mitCache(win(), { broadLive: {}, walletNorm: {} });
  const html = w._pwTermUrteil({ key: 'x', side: 'Heim', conv: null, price: null });
  assert.match(html, /Nichts Messbares/);
});

test('die Norm steht schon in der Tabelle, nicht erst im Drawer', () => {
  // Der Grund, überhaupt zu klicken: „×18" sieht man von außen, „$9.000" sagt nichts.
  const w = mitCache(win(), { broadLive: { k1: MARKT }, walletNorm: NORM });
  const zelle = w._pwTermNormZelle(ROW);
  // 0xaaa: $30.000 gegen Median $2.400 = ×12,5 auf UNSERER Seite (0xbbb steht mit ×18 auf der
  // Gegenseite und darf den Wert deshalb nicht bestimmen).
  assert.match(zelle, /×12\.5/, 'stärkster Faktor auf dieser Seite');
  assert.match(zelle, /⟂1/, 'Gegenseite wird mitgezählt');
});

test('ohne gelernte Norm zeigt die Zelle „—", keine Null', () => {
  const w = mitCache(win(), { broadLive: { k1: Object.assign({}, MARKT, { whales: [] }) }, walletNorm: NORM });
  const zelle = w._pwTermNormZelle(ROW);
  assert.match(zelle, /—/);
  assert.ok(!/×/.test(zelle), '„keine Norm bekannt" ist nicht „Einsatz ist normal"');
});

// ── Sortier-Umschalter (07.09.2026) ─────────────────────────────────────────
// Lucas: „macht es Sinn, mit einem Toggle umzustellen?" — ja, aber nicht „Geld gegen Preis":
// nach dem Preis zu sortieren ergibt keine Rangfolge. Die drei Achsen, die etwas heißen, sind
// die Linsen-Ordnung, die Wallet-Anomalie und der Anpfiff.
test('der Umschalter ordnet um, er wählt nicht aus', () => {
  const w = win();
  const JS = readFileSync(PW, 'utf8');
  assert.match(JS, /function _pwTermSortiere/, 'kein Sortier-Umschalter');
  // Die Auswahl passiert vor dem Sortieren — sonst hinge sie an der Sortierung.
  const rowsFn = JS.slice(JS.indexOf('function _pwTermRows'), JS.indexOf('function _pwTermSortiere'));
  assert.match(rowsFn, /_pwTermSortiere\(rows\)\.slice\(0,\s*40\)/,
    'erst sortieren, dann deckeln — und die Auswahl davor');
  assert.ok(typeof w._pwTermSetSort === 'function', 'der Umschalter ist nicht verdrahtet');
});

test('die Bewegungs-Linse ist raus — der Reiter kann es besser', () => {
  // Gemessen mit demselben Stand: Reiter 14 Märkte, Linse 3 — und die drei kamen aus der
  // alten Rechnung (H[0] gegen H[letzter]), die der Reiter am 02.09. abgelegt hat. Auf die
  // Fensterlogik des Reiters umgestellt fand die Linse null. Eine Ansicht, die weniger findet
  // und nichts hinzufügt, ist ein zweiter Wahrheitsstand ohne Gegenwert.
  const JS = readFileSync(PW, 'utf8');
  assert.ok(!/\['kanten','geld','bewegung','live'\]/.test(JS), 'die Linse steht wieder in der Leiste');
  assert.match(JS, /\['kanten','geld','live'\]/, 'die verbliebenen drei Linsen fehlen');
});

test('die Steam-Rechnung bleibt korrekt, falls sie als Spalte zurückkommt', () => {
  const JS = readFileSync(PW, 'utf8');
  const fn = JS.slice(JS.indexOf('function _pwMarketSteam'), JS.indexOf('function _pwMarketRow'));
  assert.match(fn, /PW_MOVE_FENSTER_H/, 'ohne das Fenster des Reiters wäre der alte Fehler zurück');
  assert.match(fn, /tempo:/);
  assert.ok(!/H\[0\]/.test(fn), 'der Rückfall auf den ältesten Snapshot ist zurück');
});

test('ein alter Linsen-Zustand landet nicht auf einer leeren Fläche', () => {
  const w = win();
  w._pwTestSetCache({ broadLive: {}, broadLiveNow: {}, walletNorm: {} });
  w._pwTermSetLens('bewegung');   // z.B. aus einer alten Sitzung
  assert.doesNotThrow(() => w._pwTermRows('geld'));
});

test('laufende Märkte verschwinden nicht mehr — sie werden markiert', () => {
  // 07.09.2026, der Hauptgrund für die leere Fläche: laufende Spiele ohne frischen
  // Live-Snapshot wurden weggeworfen. Gemessen am echten Stand: 31 solcher Märkte, für keinen
  // gab es einen Live-Eintrag — die Linse zeigte 3 Zeilen, der Reiter daneben 31.
  const w = win();
  const jetzt = Date.now();
  const laufend = { totalUsd: 90000, league: 'Serie A', sport: 'Fußball',
    prices: { Heim: 0.6, Auswärts: 0.4 }, shares: { Heim: 0.55, Auswärts: 0.45 }, whales: [],
    hoursToKickoff: 0.2, capturedAt: new Date(jetzt - 2 * 3.6e6).toISOString() };
  w._pwTestSetCache({ broadLive: { k9: laufend }, broadLiveNow: {}, walletNorm: {} });
  const rows = w._pwTermRows('geld');
  assert.equal(rows.length, 1, 'das laufende Spiel darf nicht verschwinden');
  assert.ok(rows[0].r.eingefroren > 1.5 && rows[0].r.eingefroren < 2.5,
    'das Alter des eingefrorenen Preises muss mitkommen');
});

test('ein frischer Live-Snapshot schlägt den eingefrorenen Preis', () => {
  const w = win();
  const jetzt = Date.now();
  const laufend = { totalUsd: 90000, league: 'Serie A', sport: 'Fußball',
    prices: { Heim: 0.6 }, shares: { Heim: 0.55 }, whales: [],
    hoursToKickoff: 0.2, capturedAt: new Date(jetzt - 2 * 3.6e6).toISOString() };
  const frisch = { prices: { Heim: 0.71 }, shares: { Heim: 0.8 }, totalUsd: 95000,
    hoursToKickoff: -0.5, capturedAt: new Date(jetzt - 3 * 60000).toISOString() };
  w._pwTestSetCache({ broadLive: { k9: laufend }, broadLiveNow: { k9: frisch }, walletNorm: {} });
  const rows = w._pwTermRows('geld');
  assert.equal(rows.length, 1);
  assert.equal(rows[0].r.eingefroren, null, 'mit frischem Snapshot gibt es nichts zu markieren');
  assert.equal(Math.round(rows[0].r.price * 100), 71, 'der frische Preis muss gewinnen');
});
