// tests/frontend/uebersicht-freigabe-spiele.test.mjs — 08.09.2026
//
// Lucas: „also es wird nur das geschickt, aber nicht welche Spiele — na dann brauch ich das eher
// nicht. Interessant wäre ja, welche Spiele für die freigegebenen Schubladen in Frage kämen.
// Das müsste man im Board sehen und halt ne Push dafür."
//
// Der Einwand trifft den Kern: „Liga · ABWÄGEN ist freigegeben" ist eine Aussage über 91
// abgerechnete Plays von gestern. Handeln kann man erst mit den offenen Picks, die heute unter
// dieselbe Definition fallen.
//
// Was hier festgehalten wird, sind vor allem die drei verschiedenen Arten von „nichts":
//   · nicht auflösbar — wir haben für diesen Schnitt gar keine Liste (Betfair-Aggregate)
//   · leer, aber alles läuft schon — zu spät
//   · leer und nichts läuft — warten
// Als leere Liste sehen alle drei gleich aus und heißen etwas völlig anderes.
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

const KO = new Date(Date.now() + 60 * 3600e3).toISOString();
const play = (over) => Object.assign({
  id: 'ENG-1-42-1346|Über 2.5 Tore', spiel: 'Venezia v Fiorentina',
  auswahl: 'Über 2.5 Tore', quote: 1.78, anpfiff: KO,
}, over || {});

const block = (over) => Object.assign({
  schublade: 'Liga · ABWÄGEN', strom: 'cards', roiLb: 0.0076,
  clvUrteil: 'negativ belegt', aufloesbar: true, laufend: 0, n: 1, plays: [play()],
}, over || {});

function ebene1(w, spiele) {
  w._mdState.data = {
    freigabe: {
      regeln: { minN: 30 }, zusammenfassung: { schubladen: 1, freigegeben: 1 },
      freigegeben: [{ schublade: 'Liga · ABWÄGEN', strom: 'cards', n: 91, status: 'freigegeben',
                      roi: 0.152, roiLb: 0.0076, pl: 13.8, clv: -1.52, clvUrteil: 'negativ belegt' }],
      kandidaten: [], alle: [], stroeme: [], spiele: spiele,
    },
  };
  w._renderMainDash();
  return w.document.querySelectorAll('section.md-sp .md-eb')[0].innerHTML;
}

test('die offenen Spiele einer freigegebenen Schublade stehen im Board', () => {
  const html = ebene1(load(), [block()]);
  assert.match(html, /Spielbar aus/);
  assert.match(html, /Venezia v Fiorentina/);
  assert.match(html, /Über 2\.5 Tore/);
  assert.match(html, /@1\.78/);
});

test('„nicht auflösbar" ist NICHT „keine Spiele"', () => {
  // Der teure Fehler: für Betfair gibt es gar keine Liste offener Zeilen. Eine „0" dort liest
  // sich als „heute nichts dabei" — und das wäre eine Aussage über den Spielplan, die wir
  // nicht haben.
  const html = ebene1(load(), [block({
    schublade: 'Half Time', strom: 'betfair', aufloesbar: false, n: 0, plays: [],
    grund: 'für diesen Schnitt gibt es keine Liste offener Plays — die Schublade rechnet auf Aggregaten',
  })]);
  assert.match(html, /keine Liste offener Plays/);
  assert.doesNotMatch(html, /kein offenes Spiel in diesem Schnitt/);
});

test('„alle laufen schon" heißt zu spät — nicht „nichts dabei"', () => {
  const html = ebene1(load(), [block({ n: 0, plays: [], laufend: 4 })]);
  assert.match(html, /4 Kandidaten sind bereits angepfiffen/);
  assert.doesNotMatch(html, /kein offenes Spiel in diesem Schnitt/);
});

test('leer und nichts läuft heißt warten', () => {
  const html = ebene1(load(), [block({ n: 0, plays: [], laufend: 0 })]);
  assert.match(html, /kein offenes Spiel in diesem Schnitt/);
  assert.doesNotMatch(html, /angepfiffen/);
});

test('lange Listen werden gedeckelt und der Rest gezählt', () => {
  const viele = [];
  for (let i = 0; i < 31; i++) viele.push(play({ id: 'p' + i, spiel: 'Spiel ' + i }));
  const html = ebene1(load(), [block({ n: 31, plays: viele })]);
  assert.match(html, /21 weitere in diesem Schnitt/);
  assert.doesNotMatch(html, /Spiel 25/, 'sonst ist die Ebene 31 Zeilen lang');
});

test('ohne Spiele-Block erscheint gar nichts — kein leerer Rahmen', () => {
  assert.doesNotMatch(ebene1(load(), []), /Spielbar aus/);
});

test('der Anpfiff steht dran — eine Liste ohne Zeit ist nicht handelbar', () => {
  const html = ebene1(load(), [block()]);
  assert.match(html, /\d{2}\.\d{2}\.|\d{2}:\d{2}/);
});
