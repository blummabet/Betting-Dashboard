// tests/frontend/messungen-panel.test.mjs — 15.09.2026
//
// Lucas: „wo sehen wir den Outcome dieser Messungen? Damit wir in 2 Wochen wissen, dass wir das
// heute gemacht haben?" — die Flaeche, die das beantwortet. Die teuerste Fehlbedienung waere ein
// Balken, der Fortschritt behauptet, wo gar nichts zaehlt.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const SRC = readFileSync(new URL('../../messungen.js', import.meta.url), 'utf8');
const RAW = readFileSync(new URL('../../raw-json.js', import.meta.url), 'utf8');
const UI  = readFileSync(new URL('../../ui.js', import.meta.url), 'utf8');
const HTML = readFileSync(new URL('../../season-finish-v2.html', import.meta.url), 'utf8');

function laden(daten) {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="messungenPanel"></div></body>',
    { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: false });
  w.eval(RAW);          // rawJson() ist die einzige Stelle, an der die Hol-Reihenfolge steht
  w.eval(SRC);
  if (daten !== undefined) w._msSetDataTest(daten);
  w._msRenderTest();
  return { w, html: () => w.document.getElementById('messungenPanel').innerHTML };
}

const m = (o = {}) => Object.assign({
  id: 'x', titel: 'Zahlt ein frueherer Einstieg?', frage: 'ROI nach Anpfiff-Abstand',
  warum: 'CLV ist negativ', gestartet: '2026-09-15', faellig: '2026-09-29',
  quelle: 'track.json', standN: 14, mindestN: 60, fortschritt: 14 / 60,
  zustand: 'sammelt', stand: '14 von 60 Beobachtungen', tageBisFaellig: 14,
}, o);

test('fehlende Datei sagt das als Satz, nicht als leere Flaeche', () => {
  const { html } = laden(null);
  assert.match(html(), /noch nie geschrieben/);
  assert.match(html(), /messungen\.json/);
});

test('jeder Zustand traegt sein Wort, nicht nur seine Farbe', () => {
  // Gruen/Rot hat fuer Rot-Gruen-Blinde zu wenig Abstand — ohne Wort waere die Tafel unlesbar.
  for (const [z, wort] of [['ueberfaellig', 'ÜBERFÄLLIG'], ['faellig', 'ENTSCHEIDUNG FÄLLIG'],
                           ['wartet auf Einbau', 'ZÄHLT NOCH NICHT'], ['bereit', 'MENGE ERREICHT'],
                           ['sammelt', 'SAMMELT'], ['entschieden', 'ENTSCHIEDEN'],
                           ['quelle unlesbar', 'QUELLE UNLESBAR']]) {
    const { html } = laden({ messungen: [m({ zustand: z })], nHandlung: 0, nOffen: 1 });
    assert.match(html(), new RegExp(wort), `${z} ohne Wort`);
  }
});

test('ohne Zaehlbares gibt es KEINEN Balken', () => {
  // Die wichtigste Regel dieser Flaeche: „0 von 60" in Gruen saehe aus wie „faengt gerade an".
  const { html } = laden({ messungen: [m({ fortschritt: null, standN: null, mindestN: null,
                                           zustand: 'wartet auf Einbau' })], nHandlung: 1 });
  assert.doesNotMatch(html(), /Beobachtungen \(/, 'ein Balken wurde gezeichnet, obwohl nichts zaehlt');
  assert.match(html(), /ZÄHLT NOCH NICHT/);
});

test('mit Zaehlbarem steht der Balken samt Zahlen da', () => {
  const { html } = laden({ messungen: [m()], nHandlung: 0, nOffen: 1 });
  assert.match(html(), /14 von 60 Beobachtungen \(23 %\)/);
});

test('ein ueberfaelliger Eintrag sagt, dass die Frage nicht beantwortet ist', () => {
  const { html } = laden({ messungen: [m({
    zustand: 'ueberfaellig', tageBisFaellig: -3,
    stand: 'Termin erreicht, aber nur 14 von 60 Beobachtungen — die Frage ist NICHT beantwortet',
  })], nHandlung: 1, nOffen: 1 });
  assert.match(html(), /NICHT beantwortet/);
  assert.match(html(), /seit 3 Tagen offen/);
});

test('die Bilanzzeile zaehlt den Handlungsbedarf', () => {
  assert.match(laden({ messungen: [m()], nHandlung: 2, nOffen: 3 }).html(), /2 von 1 brauchen/);
  assert.match(laden({ messungen: [m()], nHandlung: 0, nOffen: 3 }).html(), /alle sammeln planmäßig/);
});

test('leeres Register ist kein Fehler', () => {
  assert.match(laden({ messungen: [], nHandlung: 0 }).html(), /Keine Einträge/);
});

test('Text aus dem Register wird escaped', () => {
  const { html } = laden({ messungen: [m({ titel: '<img src=x onerror=alert(1)>' })], nHandlung: 0 });
  assert.doesNotMatch(html(), /<img/);
  assert.match(html(), /&lt;img/);
});

test('Termin-Text nennt heute, morgen und die Vergangenheit getrennt', () => {
  const { w } = laden(undefined);
  assert.match(w._msTerminTest({ tageBisFaellig: 0 }), /heute/);
  assert.match(w._msTerminTest({ tageBisFaellig: 1, faellig: '2026-09-16' }), /morgen/);
  assert.match(w._msTerminTest({ tageBisFaellig: -2, faellig: '2026-09-13' }), /seit 2 Tagen/);
  assert.match(w._msTerminTest({}), /kein Termin/);
});

test('die Ansicht ist verdrahtet: Panel, Menue, Skript, Callback', () => {
  // ⭐ Gegenprobe an der Nahtstelle. Ohne sie waere das Buch gebaut und unerreichbar —
  // und Lucas' Frage („dann sehe ich es im Menue") waere genau NICHT beantwortet.
  assert.match(HTML, /id="messungenPanel"/, 'kein Panel im HTML');
  // Beide Wege getrennt pruefen: Desktop-Dropdown UND Mobile-Sheet. Faellt einer weg, ist die
  // Flaeche fuer die Haelfte der Geraete unerreichbar — und der andere deckt den Ausfall zu.
  assert.match(HTML, /showView\('messungen'\);closeTopMore\(\)/, 'kein Eintrag im Desktop-Menue');
  assert.match(HTML, /showView\('messungen'\);toggleMoreSheet\(\)/, 'kein Eintrag im Mobile-Sheet');
  assert.match(HTML, /"messungen\.js"/, 'Skript nicht eingebunden');
  assert.match(UI, /'messungenPanel'/, 'Panel nicht in der Panel-Liste');
  assert.match(UI, /'messungen':\s*'messungenPanel'/, 'keine View-Zuordnung');
  assert.match(UI, /MORE_SECS[^\n]*'messungen'/, 'Menue-Eintrag wird nicht aktiv markiert');
  assert.match(UI, /view === 'messungen'[\s\S]{0,80}initMessungen\(\)/, 'kein Lade-Callback');
  assert.match(SRC, /rawJson\('messungen\.json'\)/, 'holt nicht raw-zuerst ueber rawJson()');
});
