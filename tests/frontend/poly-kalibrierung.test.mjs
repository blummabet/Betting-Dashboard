// tests/frontend/poly-kalibrierung.test.mjs — 29.08.2026
//
// Lucas: „sollte man das ähnlich der Cards mit lernen und neu gewichten?"
//
// Antwort war: die Hälfte davon läuft schon (_pwCalibConv, 21.08.) — nur an drei Stellen falsch.
//
//  1. Sie lief gar nicht dort, wo es zählt. `poly_shortlist_track.json` fehlte im schlanken
//     Loader (_pwEnsurePlaysData), der die Übersichts-Kachel UND scripts/emit_shortlist.mjs
//     bedient — also Papier-Depot und Telegram-Push. _pwComboFor() gab null zurück, die
//     Kalibrierung stieg stumm aus. Sichtbar war sie nur im Wallets-Tab, wo der große Loader
//     den Track mitlädt. Derselbe Play trug damit auf zwei Flächen zwei verschiedene Zahlen.
//
//  2. `bf` fehlte im Kalibrier-Kern — ausgerechnet das beste Signal im Track (+26,4 % ROI über
//     n=41). Der Eimer „money" (n=33, +21,1 %) war in Wahrheit money+bf; `money` allein kommt
//     gewichtsmäßig gar nicht über die Schwelle von 3. Der Lerner schrieb den Erfolg dem
//     falschen Signal zu.
//
//  3. Kein Engine-Stempel. Alle 500 abgerechneten Plays stammen aus der alten Gewichtung.
//     Jetzt zählen Alt-Plays halb: der ROI-Schätzer bleibt, das Vertrauen (conf = n/(n+25))
//     sinkt — und der Alt-Anteil verwässert sich von selbst, weil seine n eingefroren ist.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const ROOT = new URL('../../', import.meta.url);
const SRC  = readFileSync(new URL('poly-wallets.js', ROOT), 'utf8');

// 29.08.2026: die Engine-Version wird aus der QUELLE gelesen, nicht eingetippt. Beim ersten
// echten Versionssprung (Säulen-Neugewichtung, '2026-08-29' -> '2026-08-29b') sind diese Tests
// gekippt — nicht weil etwas kaputt war, sondern weil der Stempel genau seinen Job gemacht hat.
const EV = /const PW_ENGINE_VERSION='([^']+)'/.exec(SRC)[1];

const TRACK = (evs) => ({
  agg: { all: { roi: 0 } },
  settled: evs.map((ev, i) => ({
    key: 'k' + i, side: 'A', result: 'win', stake: 10, pnl: 3,
    signals: ['money', 'bf'], ev,
  })),
});

function boot(files) {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="polyWalletsPanel"></div></body>',
    { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window;
  const geholt = [];
  w.fetch = (url) => {
    const name = String(url).split('?')[0].split('/').pop();
    geholt.push(name);
    const b = files[name];
    return Promise.resolve({ ok: b != null, json: () => Promise.resolve(b) });
  };
  w.eval(SRC);
  w.__geholt = geholt;
  return w;
}

test('der schlanke Loader holt den Shortlist-Track — sonst lernt die Übersicht nie', async () => {
  const w = boot({});
  await new Promise((res) => w._pwEnsurePlaysData(res));
  assert.ok(w.__geholt.includes('poly_shortlist_track.json'),
    'poly_shortlist_track.json fehlt wieder im schlanken Loader — die Kalibrierung steigt dann '
    + 'stumm aus, und zwar genau in Übersicht, Papier-Depot und Push. Geholt wurde: '
    + w.__geholt.join(', '));
});

test('bf ist im Kalibrier-Kern — money+bf wird nicht mehr als money verbucht', async () => {
  const w = boot({ 'poly_shortlist_track.json': TRACK([EV, EV]) });
  await new Promise((res) => w._pwEnsurePlaysData(res));
  const agg = w._pwComboStatsAll();
  assert.ok(agg, 'Combo-Statistik ist leer');
  assert.ok(agg['bf+money'], 'der Eimer heisst nicht bf+money: ' + Object.keys(agg).join(', '));
  assert.ok(!agg['money'], 'money+bf laeuft immer noch als reines money');
});

test('Alt-Plays zählen halb, aktuelle voll', async () => {
  const w = boot({ 'poly_shortlist_track.json': TRACK([EV, null, 'irgendwas-altes']) });
  await new Promise((res) => w._pwEnsurePlaysData(res));
  const a = w._pwComboStatsAll()['bf+money'];
  assert.strictEqual(a.nRoh, 3, 'die rohe Anzahl muss ehrlich bleiben');
  assert.strictEqual(a.nAlt, 2, 'zwei Plays stammen aus einer aelteren Engine');
  assert.strictEqual(a.n, 1 + 0.5 + 0.5, 'gewichtete Anzahl: 1 aktuell + 2 alte à 0,5');
});

test('das Alt-Gewicht senkt das Vertrauen, nicht die ROI-Schätzung', async () => {
  const nur_alt  = boot({ 'poly_shortlist_track.json': TRACK([null, null, null, null]) });
  const nur_neu  = boot({ 'poly_shortlist_track.json': TRACK(Array(4).fill(EV)) });
  await new Promise((res) => nur_alt._pwEnsurePlaysData(res));
  await new Promise((res) => nur_neu._pwEnsurePlaysData(res));
  const a = nur_alt._pwComboStatsAll()['bf+money'];
  const b = nur_neu._pwComboStatsAll()['bf+money'];
  assert.ok(Math.abs(a.roi - b.roi) < 1e-9, 'gleicher ROI — die Halbierung kuerzt sich raus');
  assert.ok(a.n < b.n, 'aber weniger gewichtete Stichprobe -> conf = n/(n+25) faellt');
});

test('jeder Play trägt den Engine-Stempel — sonst kommt er nie im Track an', () => {
  // Datum plus optionaler Buchstabe: mehrere Gewichtungs-Wechsel an einem Tag brauchen
  // unterscheidbare Stempel ('2026-08-29', '2026-08-29b', …).
  assert.match(SRC, /const PW_ENGINE_VERSION='\d{4}-\d{2}-\d{2}[a-z]?'/, 'Engine-Version fehlt');
  assert.match(SRC, /ev:PW_ENGINE_VERSION/, '_pwShortlistScore gibt den Stempel nicht mit');
  const emit = readFileSync(new URL('scripts/emit_shortlist.mjs', ROOT), 'utf8');
  assert.match(emit, /ev: p\.ev \|\| null/, 'emit_shortlist reicht den Stempel nicht durch');
});

// ── Das Lern-Board (29.08.2026, Lucas: „das ist sehr wichtig, es optisch cool darzustellen") ──
// Bis dahin war die Kalibrierung eine Blackbox: sie verschob Conviction um bis zu drei Stufen und
// die einzige Spur war eine Zeile im „Warum". Das Board zeigt je Signal-Mix, was das Papier-Depot
// wirklich hergab. Form: divergierender Balken ab einer Mittellinie (= Basis-ROI der Shortlist),
// weil die Frage Polaritaet ist — ueber oder unter dem Schnitt — nicht Groesse.

const BOARD_TRACK = {
  agg: { all: { roi: -0.015 } },   // Schnitt der Shortlist = die Mittellinie
  settled: [
    // Mix mit NEGATIVEM ROI, der trotzdem UEBER dem Schnitt liegt. Genau hier ging die erste
    // Fassung schief: sie haengte den Pfeil an den ROI, also stand bei -0,5% ein ↑ — als waere
    // der Mix profitabel. Der Pfeil gehoert zum Abstand (das zeigt der Balken), die Zahl ist der ROI.
    ...Array.from({ length: 10 }, (_, i) => ({
      key: 'a' + i, result: 'win', stake: 100, pnl: -0.5, signals: ['money'], ev: '2026-08-29' })),
    // Klar unter dem Schnitt, genug Stichprobe -> muss abwerten
    ...Array.from({ length: 20 }, (_, i) => ({
      key: 'b' + i, result: 'loss', stake: 100, pnl: -40, signals: ['steam'], ev: '2026-08-29' })),
    // Zu duenn -> darf gar nichts anpassen
    ...Array.from({ length: 3 }, (_, i) => ({
      key: 'c' + i, result: 'win', stake: 100, pnl: 60, signals: ['pinn'], ev: '2026-08-29' })),
  ],
};

async function board() {
  const w = boot({ 'poly_shortlist_track.json': BOARD_TRACK });
  await new Promise((res) => w._pwEnsurePlaysData(res));
  return { w, html: w._pwCalibBoard() };
}

test('Lern-Board rendert je Signal-Mix eine Zeile mit lesbaren Namen', async () => {
  const { html } = await board();
  assert.match(html, /Lern-Board/);
  assert.match(html, /💰 Geld-Mehrheit/, 'Signal-Namen statt roher Tags');
  assert.match(html, /📈 Steam/);
  assert.strictEqual((html.match(/class="pw-cal-row(?! pw-cal-legend)/g) || []).length, 3,
    'je Signal-Mix genau eine Datenzeile (die Skala-Zeile zaehlt nicht mit)');
  assert.match(html, /pw-cal-legend/, 'die Skala-Zeile fehlt');
});

test('der Pfeil hängt am Abstand zum Schnitt, nicht am ROI', async () => {
  const { html } = await board();
  // money: ROI -0,5% (negativ!) aber 1,0pp UEBER dem Schnitt von -1,5%
  assert.match(html, /<b>−0\.5%<\/b>/, 'der ROI wird mit seinem eigenen Vorzeichen gezeigt');
  assert.match(html, /↑ 1\.0pp<i>über Schnitt/,
    'der Abstand trägt den Pfeil — sonst stünde bei negativem ROI ein ↑ und läse sich als Gewinn');
});

test('Balken wächst aus der Mittellinie — links schlechter, rechts besser', async () => {
  const { html } = await board();
  assert.match(html, /class="pw-cal-mid"/, 'die Mittellinie fehlt');
  assert.match(html, /left:50%;border-radius:0 4px 4px 0/, 'positiver Balken wächst nach rechts');
  assert.match(html, /right:50%;border-radius:4px 0 0 4px/, 'negativer Balken wächst nach links');
});

test('unter acht gewichteten Plays wird nichts angepasst — und das steht da', async () => {
  const { html } = await board();
  assert.match(html, /sammelt · n&lt;8/, 'dünne Mixe müssen als solche markiert sein');
  assert.match(html, /↓ −\d Stufen?/, 'der klar schlechte Mix muss abgewertet werden');
});

test('Farbe trägt die Aussage nie allein (grün/rot ist für Deutan ununterscheidbar)', async () => {
  // Validator: #3fb950 ↔ #f85149 haben deutan ΔE 2,2. Wer die zwei nicht trennen kann, muss die
  // Zeile trotzdem lesen können -> Richtung ab der Mittellinie, Vorzeichen UND ein ↑/↓.
  const { html } = await board();
  for (const zeichen of ['↑', '↓', 'über Schnitt', 'unter Schnitt']) {
    assert.ok(html.includes(zeichen), `sekundäre Kodierung fehlt: ${zeichen}`);
  }
});
