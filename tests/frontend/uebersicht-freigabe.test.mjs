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
  // 01.09.2026: das Register ist Ebene 1 der Sektion „Was kann ich spielen?". Zugeschnitten
  // wird per DOM auf genau diese Ebene — nicht per Zeichenabstand (das las beim letzten Umbau
  // die Nachbarsektion mit) und nicht per Überschrift-Text (der darf sich ändern dürfen).
  const n = w.document.querySelector('.md-eb-n.e1');
  assert.ok(n, 'Ebene 1 (Register) wird gar nicht gerendert');
  return n.closest('.md-eb').outerHTML;
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
  const badges = [...h.matchAll(/class="md-eb-st"[^>]*>([\s\S]*?)<\/span>/g)].map(m => m[1].trim());
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

// 01.09.2026 (Lucas: „das wirkt jetzt schon sehr oft quasi redundant"): die drei Fragen stehen
// jetzt als nummerierte Ebenen in EINER Sektion. Die Reihenfolge ist damit nicht mehr Geschmack,
// sondern die Aussage der Sektion — von streng nach breit. Deshalb wird sie hier festgehalten.
test('die drei Ebenen stehen in EINER Sektion, von streng nach breit', () => {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="mainDashPanel"></div></body>',
    { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve(null) });
  w.eval(readFileSync(MOD, 'utf8'));
  w._mdState.data = { liga: null, mls: null, ligaStreaks: null, mlsStreaks: null, betfair: null,
    whales: null, killer: { stufe1: [], stufe2: [], bilanz: null }, freigabe: reg() };
  w._renderMainDash();
  const doc = w.document;
  const sek = [...doc.querySelectorAll('section.md-sp')];
  assert.equal(sek.length, 1, 'genau EINE Sektion — sonst konkurrieren wieder drei Köpfe');
  const nummern = [...sek[0].querySelectorAll('.md-eb-n')].map(x => x.textContent.trim());
  assert.deepEqual(nummern, ['1', '2', '3'], 'Register → Konjunktion → Rangliste, in dieser Folge');
  // Die Klammer muss den Zusammenhang AUSSPRECHEN — ohne sie sehen drei Antworten aus
  // wie dreimal dieselbe Frage. Genau das war Lucas' Eindruck.
  const kopf = sek[0].querySelector('.md-sp-s').textContent;
  assert.match(kopf, /streng/, 'der Kopf muss sagen, wonach die Ebenen geordnet sind');
  assert.match(kopf, /Ebene 1/, 'und wozu die oberste Ebene gut ist');
});

test('jede Ebene sagt, wie sie gebaut ist — Register, Filter, Rangliste', () => {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="mainDashPanel"></div></body>',
    { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve(null) });
  w.eval(readFileSync(MOD, 'utf8'));
  w._mdState.data = { liga: null, mls: null, ligaStreaks: null, mlsStreaks: null, betfair: null,
    whales: null, killer: { stufe1: [], stufe2: [], bilanz: null }, freigabe: reg() };
  w._renderMainDash();
  const pillen = [...w.document.querySelectorAll('section.md-sp .md-mech')].map(x => x.textContent.trim());
  // 01.09.2026: aus „Filter" wurde „Punktestand" — die Ebene sortiert Spiele jetzt nach der Zahl
  // der zustimmenden BÜCHER, statt sie hart auszusortieren. Drei verschiedene Bauarten bleibt der
  // Punkt: Urteil über Schubladen · Gewichtung über Bücher · Sortierung über Einzelsignale.
  assert.deepEqual(pillen, ['Register', 'Punktestand', 'Rangliste'],
    'drei verschiedene Bauarten — genau deshalb sind es drei Ebenen und keine Wiederholung');
});

// 01.09.2026 (Lucas: „brauch das im Desktop die gesamte Breite? reicht es nicht, wenn 3 Kacheln
// nebeneinander stehen?"). Antwort: die EBENEN bleiben untereinander — nebeneinander liest sich als
// gleichrangig, und genau das war der Eindruck, den die Leiter beseitigt hat. Die SPIELE innerhalb
// einer Ebene sind dagegen untereinander gleichrangig und stehen ab 1040px zu zweit.
// Diese beiden Regeln werden hier festgehalten, weil sie beim naechsten Layout-Umbau als Erstes
// aufgeweicht werden.
test('die Ebenen bleiben untereinander, die Spiele duerfen nebeneinander', () => {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="mainDashPanel"></div></body>',
    { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve(null) });
  w.eval(readFileSync(MOD, 'utf8'));
  const ko = new Date(Date.now() + 2 * 3600e3).toISOString();
  const sp = (h) => ({ matchId: h, home: h, away: 'Gegner', league: 'English Premier League',
    kickoff: ko, markt: 'Match Odds', seite: 'home', name: h, odd: 1.8, haltePreis: 1.8,
    anteilPct: 74, stufe: 2, verstaerker: [], rang: 55, aktiv: true,
    gehaltenSeit: new Date().toISOString(), zuletztAktiv: new Date().toISOString() });
  w._mdState.data = { liga: null, mls: null, ligaStreaks: null, mlsStreaks: null, betfair: null,
    whales: null, killer: { stufe1: [], stufe2: [sp('Arsenal'), sp('Chelsea')], bilanz: null },
    freigabe: reg() };
  w._renderMainDash();
  const doc = w.document, sek = doc.querySelector('section.md-sp');
  const css = doc.getElementById('mdash-css').textContent;

  // Die Ebenen selbst bekommen NIE ein Spaltenraster.
  assert.ok(!/\.md-eb\{[^}]*grid-template-columns/.test(css),
    'die Leiter darf nicht in Spalten zerfallen — die Reihenfolge ist die Aussage');
  assert.deepEqual([...sek.querySelectorAll('.md-eb-n')].map(x => x.textContent.trim()),
    ['1', '2', '3'], 'und sie bleibt streng → breit');

  // Die Spiele stehen in einem Container, der erst ab 1040px zweispaltig wird.
  assert.equal(sek.querySelectorAll('.md-kl-paar > .md-kl-row').length, 2,
    'die Spiele liegen im Paar-Container');
  assert.match(css, /@media\(min-width:1040px\)/,
    'zweispaltig erst, wenn das Deckungs-Profil in eine halbe Spalte passt');

  // Und die Zeile hat ein Maass: der Balken darf ROI/CLV nicht an den Rand druecken.
  assert.match(css, /\.md-kl-bz\{max-width:\d+px/, 'die Datenzeile braucht eine Lesebreite');
  assert.ok(!/\.md-kl-bl\{[^}]*flex:1[;}]/.test(css),
    'der Fortschrittsbalken darf den Restplatz nicht mehr fressen');
});
