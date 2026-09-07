// tests/frontend/stake-klasse.test.mjs — 07.09.2026
//
// Lucas: „ne 50k Wette auf Arsenal sagt 0 / Eine 50k Wette auf ein 2-3. Liga Team / Ist
// zumindest jemand der mehr dran glaubt mmn."
//
// Die Ansicht „Spielklasse" darf NICHTS rechnen. Spielklasse, Referenzeinsatz, Schwellen und
// Kreuztabelle kommen fertig aus stake_analyse.py (`randliga`). Eine zweite Schwelle im
// Renderer ist die Klasse, die in diesem Repo schon zweimal auseinandergelaufen ist —
// deshalb prüfen diese Tests vor allem, was NICHT im Code stehen darf.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';

const ROOT = new URL('../../', import.meta.url);
const JS = readFileSync(new URL('stake-radar.js', ROOT), 'utf8');

function block(von, bis) {
  const a = JS.indexOf(von), b = JS.indexOf(bis);
  assert.ok(a > 0, 'Anker weg: ' + von);
  assert.ok(b > a, 'Anker weg: ' + bis);
  return JS.slice(a, b);
}
const KLASSE = block('function _srKlasse()', 'function _srBilanz()');
// Kommentare raus, wo auf Abwesenheit geprüft wird — sie benennen absichtlich das Verbotene.
const CODE = KLASSE.replace(/^\s*\/\/.*$/gm, '');

test('die Ansicht ist verdrahtet', () => {
  assert.match(JS, /\['klasse', '🏟️ Spielklasse'\]/, 'Tab fehlt in der Navigation');
  assert.match(JS, /SR_TAB === 'klasse' \? _srKlasse\(\)/, 'Tab wird nicht gerendert');
});

test('die Schwelle kommt aus dem Artefakt, nicht aus dem Renderer', () => {
  // Keine eigene Zahl neben `abFaktor`: keine 3, keine 6, kein >=-Vergleich auf faktor.
  assert.ok(/r\.abFaktor/.test(CODE), 'die Schwelle wird nicht aus dem Artefakt gelesen');
  assert.ok(!/faktor\s*[<>]=?\s*\d/.test(CODE),
    'im Renderer wird gegen eine eigene Schwelle verglichen — die gibt es dann zweimal');
  assert.ok(!/\bKAND_AB\b|\bTOP_AB\b/.test(CODE), 'Schwellen-Konstante im Frontend nachgebaut');
});

test('die Ebene wird nicht aus dem Ligennamen geraten', () => {
  assert.ok(!/liga.*(match|indexOf|replace|split)\s*\(/i.test(CODE),
    'die Spielklasse wird im Renderer aus dem Namen rekonstruiert statt gelesen');
  assert.ok(/x\.ebene/.test(CODE), 'die gestempelte Ebene wird nicht benutzt');
});

test('fehlender Block sagt das, statt eine leere Tabelle zu zeigen', () => {
  assert.match(KLASSE, /randliga.*fehlt|fehlt.*randliga/s,
    'ohne den Block müsste dastehen, dass er fehlt');
});

test('eine dem Radar unbekannte Ebene fällt nicht aus der Tabelle', () => {
  // 07.09.2026: am Tag nach dem Bau kam „Primera Division Reserve" dazu. Lief die
  // Zeilenauswahl über die Beschriftungsliste im Renderer, wäre jede Ebene, die der
  // Produzent kennt und das Frontend noch nicht, still verschwunden.
  assert.match(CODE, /Object\.keys\(k\)/,
    'die Zeilen kommen aus der Frontend-Liste statt aus dem Artefakt');
  assert.match(CODE, /_SR_KL_EBENE\[e\] \|\|/,
    'ohne Rückfall auf den rohen Schlüssel bleibt eine unbekannte Ebene unsichtbar');
});

test('Ligen ohne Ebene bleiben sichtbar', () => {
  assert.match(CODE, /nOhneEbene/,
    'eine Liga ohne Eintrag muss auffallen, nicht still als Ebene 1 zählen');
});

test('ohne Grenzen steht kein Urteil da', () => {
  const zelle = block('function _srKlZelle(', 'function _srKlasse()');
  assert.match(zelle, /flachUg == null/, 'der Fall „keine Untergrenze" wird nicht behandelt');
  assert.match(zelle, /kein Urteil/, 'unter n=30 muss „kein Urteil" dastehen');
  assert.ok(/z\.belegt/.test(zelle),
    'die Auszeichnung hängt nicht am gestempelten Urteil, sondern an einer eigenen Regel');
});

test('beide Richtungen können ein Urteil tragen', () => {
  // Eine Zelle mit ROI -12 % und Obergrenze unter null sagt etwas: dagegenhalten trägt.
  // Nur mit der Untergrenze bliebe die ganze Ebene-1-Reihe für immer „kein Urteil".
  const zelle = block('function _srKlZelle(', 'function _srKlasse()');
  assert.match(zelle, /flachOg/, 'die Obergrenze wird nicht gelesen');
  assert.match(zelle, /belegtGegen/, 'das Gegen-Urteil aus dem Artefakt wird nicht benutzt');
  // Die Auszeichnung muss AN den gestempelten Flaggen hängen. Ein Test auf „kein `> 0` im
  // Renderer" wäre hier Dekoration gewesen: dasselbe Zeichen steht auch im Vorzeichen der
  // Prozentzahl, der Guard hätte also nicht unterscheiden können, was er verbietet.
  assert.match(zelle, /z\.belegt \|\| z\.belegtGegen/,
    'die Marke hängt nicht an beiden gestempelten Urteilen');
  assert.match(zelle, /z\.belegtGegen \?/, '„dagegen" wird nicht aus dem Artefakt gesetzt');
});

test('die Kandidatenliste filtert den Ausgang nicht weg', () => {
  assert.match(CODE, /ausgang === 'lost'/,
    'auch die Verlierer müssen in der Liste stehen — sonst ist sie ihre eigene Erfolgsmeldung');
});

test('die Herkunft der Referenz steht in der Zeile', () => {
  assert.match(CODE, /refBasis === 'liga'/,
    '„3× der Norm" heißt etwas anderes je nachdem, ob die Norm aus der Liga oder der Ebene kommt');
});
