// tests/frontend/uebersicht-freigabe.test.mjs — 01.09.2026
//
// Lucas: „ja bitte und wo bauen wir das im Frontend ein?" — das Freigabe-Register hatte bis dahin
// gar keine Oberfläche: freigabe.json wurde nur vom Killer-Badge gelesen. Jetzt steht es direkt
// nach dem Puls, VOR „Mehrfach gedeckt", weil es die Meta-Antwort über allen Sektionen darunter
// ist: darf ich hiervon überhaupt etwas blind spielen?
//
// Geprüft werden die drei Stellen, an denen so eine Sektion typischerweise lügt:
//   · sie behauptet „nichts freigegeben", obwohl sie es gar nicht wissen kann (Datei fehlt),
//   · sie zeigt den Punktschätzer ohne Untergrenze,
//   · sie verschweigt, dass die Datenbasis aus einer älteren Engine stammt.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const MOD = new URL('../../main-dashboard.js', import.meta.url);

function render(freigabe) {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="mainDashPanel"></div></body>',
    { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve(null) });
  w.eval(readFileSync(MOD, 'utf8'));
  w._mdState.data = {
    liga: null, mls: null, ligaStreaks: null, mlsStreaks: null, betfair: null, whales: null,
    killer: null, freigabe,
  };
  w._renderMainDash();
  const html = w.document.getElementById('mainDashPanel').innerHTML;
  const von = html.indexOf('Blind spielbar');
  assert.ok(von > 0, 'Freigabe-Sektion wird gar nicht gerendert');
  return html.slice(Math.max(0, von - 300), von + 3200);
}

const schublade = (over = {}) => ({
  schublade: 'Conviction 9', strom: 'poly', n: 12, status: 'kandidat',
  grund: '12 von 30 Plays — noch 18', roi: 0.163, roiLb: -0.021,
  clv: 0.75, clvLb: 0.23, fehltN: 18, alterTage: 1.2, ...over,
});
const reg = (over = {}) => ({
  generatedAt: new Date().toISOString(), engine: '2026-09-01', engineGefiltert: true,
  regeln: { minN: 30, z: 1.645, text: 'freigegeben = n>=30 UND ROI-Untergrenze>0 …' },
  freigegeben: [], kandidaten: [schublade()], alle: [schublade()],
  zusammenfassung: { schubladen: 38, freigegeben: 0, kandidaten: 1, ruhend: 0, naechsteFreigabe: 18 },
  ...over,
});

test('leeres Register sagt „nichts freigegeben" — und dass das ein Ergebnis ist', () => {
  const h = render(reg());
  assert.match(h, /nichts freigegeben/);
  assert.match(h, /nächste in 18 Plays/);
  assert.match(h, /Ergebnis, kein Fehler/, 'leer muss als Aussage erklärt werden, nicht als Panne');
});

test('fehlende Datei meldet ❔ UNBEKANNT — niemals „nichts freigegeben"', () => {
  // Der Unterschied, an dem dieses Projekt schon mehrfach Wochen verloren hat:
  // nicht wissen ist nicht dasselbe wie wissen, dass nichts da ist.
  const h = render(null);
  assert.match(h, /unbekannt/i);
  // Gemeint ist: die Sektion darf es nicht BEHAUPTEN. Der Satz, der die beiden Fälle
  // gegeneinander stellt, muss die Phrase zitieren dürfen — sonst erklärt er nichts.
  // Also wird getrennt geprüft: was im Badge steht, und was der Fließtext behauptet.
  // nur bis zum Ende DIESER Sektion — dahinter beginnt „Mehrfach gedeckt" mit eigenem Badge.
  const ab = h.indexOf('Blind spielbar');
  const bis = h.indexOf('</section>', ab);
  const sekt = h.slice(ab, bis > 0 ? bis : h.length);
  const badges = [...sekt.matchAll(/class="md-kl-st"[^>]*>([\s\S]*?)<\/span>/g)].map(m => m[1].trim());
  assert.deepEqual(badges, ['❔ unbekannt'], 'ohne Datei darf im Badge nur „unbekannt" stehen');
  const behauptung = h.replace(/nicht dasselbe wie [„"»]?nichts freigegeben/g, '');
  assert.ok(!/nichts freigegeben/.test(behauptung), 'ohne Datei darf die Sektion nichts behaupten');
  assert.match(h, /nicht dasselbe wie/, 'der Unterschied gehört ausgesprochen');
});

test('jede Zeile zeigt die Untergrenze neben dem Wert', () => {
  const h = render(reg());
  assert.match(h, /ROI \+16%/);
  assert.match(h, /\(UG −?-?2%\)/, 'ohne Untergrenze ist der ROI eine Behauptung');
});

test('freigegebene Schublade wird grün und mit Haken gezeigt', () => {
  const frei = schublade({ status: 'freigegeben', n: 34, roi: 0.21, roiLb: 0.04, grund: 'ROI und CLV belegt' });
  const h = render(reg({ freigegeben: [frei], alle: [frei], kandidaten: [],
    zusammenfassung: { schubladen: 38, freigegeben: 1, kandidaten: 0, ruhend: 0, naechsteFreigabe: null } }));
  assert.match(h, /1 freigegeben/);
  assert.match(h, /34\/30/, 'die Stichprobe muss an der Zeile stehen');
});

test('Alt-Plays aus einer früheren Engine werden ausgewiesen, nicht verschwiegen', () => {
  const h = render(reg({ kandidaten: [schublade({ n: 0, nAlt: 12, roiAlt: 0.163 })],
                         alle: [schublade({ n: 0, nAlt: 12, roiAlt: 0.163 })] }));
  assert.match(h, /12 alt/, 'die Alt-Stichprobe gehört sichtbar an die Zeile');
  assert.match(h, /Engine <b>2026-09-01<\/b>/);
  assert.match(h, /zählen nicht für eine Freigabe/);
});

test('ohne Engine-Filter sagt die Sektion das offen', () => {
  const h = render(reg({ engineGefiltert: false, engine: null }));
  assert.match(h, /Ohne Engine-Filter/);
});

test('alte Datei ohne Filter-Auskunft meldet ❔ statt etwas zu behaupten', () => {
  const alt = reg(); delete alt.engineGefiltert;
  assert.match(render(alt), /sagt die Datei nicht/);
});

test('das Register steht VOR „Mehrfach gedeckt"', () => {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="mainDashPanel"></div></body>',
    { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve(null) });
  w.eval(readFileSync(MOD, 'utf8'));
  w._mdState.data = { liga: null, mls: null, ligaStreaks: null, mlsStreaks: null, betfair: null,
    whales: null, killer: { stufe1: [], stufe2: [], bilanz: null }, freigabe: reg() };
  w._renderMainDash();
  const html = w.document.getElementById('mainDashPanel').innerHTML;
  assert.ok(html.indexOf('Blind spielbar') < html.indexOf('Mehrfach gedeckt'),
    'die Meta-Antwort muss vor den Empfehlungen stehen, nicht danach');
});
