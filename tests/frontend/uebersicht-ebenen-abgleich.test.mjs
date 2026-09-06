// tests/frontend/uebersicht-ebenen-abgleich.test.mjs — 06.09.2026
//
// Lucas: „die 2 Elemente müssen einfach simpel zeigen warum damit ich schnell weiß. Und wenn in
// beiden Elemente selbe Team dann ja eindeutiger."
//
// Ich hatte ihm vorher gesagt, die Flächen überschnitten sich nicht, und daraus „ein Marker
// würde nie feuern" geschlossen. Er hat mich mit seinem eigenen Board widerlegt:
//
//     Ebene 2:  „Remo v Flamengo → Flamengo"
//     Ebene 3:  „CR Flamengo vs Clube do Remo → CR Flamengo"
//
// Gemessen nach dem Fix (06.09., 18:00 UTC): 2 von 3 Konsens-Zeilen stehen mit DERSELBEN Seite
// auch in der Poly-Shortlist. Der Marker hätte sehr wohl gefeuert — er konnte nur nicht, weil
// der gemeinsame Schlüssel (`polyKey`) im Produzenten weggeworfen wurde.
//
// Zwei Dinge hält diese Datei fest:
//   1. der Abgleich läuft über den EXAKTEN Marktschlüssel, nicht über geratene Namensformen
//   2. er ist in BEIDE Richtungen sichtbar — und „gleiches Spiel" ist nicht „gleiche Seite"
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';

const ROOT = new URL('../../', import.meta.url);
const JS = readFileSync(new URL('main-dashboard.js', ROOT), 'utf8');
const CODE = JS.replace(/^\s*\/\/.*$/gm, '');

test('der Abgleich läuft über den Marktschlüssel des Produzenten', () => {
  assert.ok(/m\['pk:' \+ z\.polyKey\]/.test(CODE),
    'ohne polyKey-Index gibt es keinen gemeinsamen Bezeichner zwischen den Ebenen');
  assert.ok(/_klk\['pk:' \+ o\.pk\]/.test(CODE),
    'Ebene 3 fragt den Index nicht ab');
  assert.ok(/pk: r\.key \|\| null/.test(CODE),
    'die Poly-Zeile reicht ihren eigenen Schlüssel nicht weiter');
});

test('das Frontend rät keine Namensformen mehr', () => {
  // Der erste Anlauf zerlegte „CR Flamengo vs Clube do Remo" im Renderer und verglich Teile
  // gegen „Remo"/„Flamengo" — Produzenten-Logik im Frontend (Bug-Klasse 2), und für genau
  // dieses Paar hätte sie AUCH nicht getroffen.
  assert.ok(!/teamsAusLabel/.test(CODE),
    'Label-Zerlegung ist zurück — der Schlüssel gehört vom Produzenten, nicht aus dem Text');
});

test('beide Richtungen tragen den Marker', () => {
  assert.ok(/function _klNachPolyKey/.test(CODE), 'die Gegenrichtung fehlt');
  assert.ok(/auch Ebene 2/.test(CODE), 'Ebene 3 sagt nicht, dass die Zeile oben steht');
  assert.ok(/auch Ebene 3/.test(CODE), 'Ebene 2 sagt nicht, dass die Zeile unten steht');
  // Auf die AUFRUFSTELLE prüfen, nicht auf den Funktionskopf: `function _mdKiller(polyPlays)`
  // matcht sonst mit, und der Test bliebe grün, während der Aufruf die Plays nicht mehr
  // durchreicht. (Genau das ist beim Gegenbeweis passiert.)
  assert.ok(/_mdFreigabe\(\) \+ _mdKiller\(polyPlays\)/.test(CODE),
    'Ebene 2 bekommt die Plays nicht — dann kann sie den Abgleich gar nicht kennen');
});

test('„gleiches Spiel" wird nicht als „gleiche Seite" ausgegeben', () => {
  // Der Unterschied ist die ganze Aussage: dieselbe Seite ist eine Bestätigung, die
  // Gegenseite ein Widerspruch. Beides als ein blaues 🔒 zu zeigen wäre die alte
  // Krankheit — ein Satz, der mehr behauptet als die Daten hergeben.
  assert.ok(/deckSeite = \(_z2\.polySide === o\.polySide\) \? 'gleich' : 'anders'/.test(CODE),
    'die Seiten werden nicht verglichen');
  assert.ok(/Ebene 2 dagegen/.test(CODE) && /Ebene 3 dagegen/.test(CODE),
    'der Widerspruchsfall hat keine eigene Anzeige — er ist der wichtigere von beiden');
  assert.ok(/gleiche Seite/.test(CODE), 'der bestätigte Fall ist nicht als solcher benannt');
});

test('ohne beide Seitennamen wird nichts behauptet', () => {
  // Fehlende Information ist keine Erlaubnis: ein Altbestand ohne `polySide` darf nicht
  // stillschweigend als „gleiche Seite" durchgehen.
  assert.ok(/o\.deckSeite = null;/.test(CODE), 'der Unbekannt-Zustand fehlt');
  assert.ok(/if \(o\.gedeckt && o\.pk && o\.polySide\)/.test(CODE),
    'die Seitenprüfung läuft ohne Vorbedingung — dann erfindet sie ein Urteil');
});

test('Ebene 2 wird nach dem Poly-Nachladen mitgetauscht', () => {
  // Die Plays kommen async. Wird nur der untere Kasten neu gebaut, trägt genau EINE der
  // beiden Flächen den Marker — der Zustand, den Lucas beanstandet hat.
  assert.ok(/id="mdKillerBox"/.test(CODE), 'Ebene 2 hat keinen eigenen Anker');
  assert.ok(/getElementById\('mdKillerBox'\)/.test(CODE), '_mdFillJetzt tauscht Ebene 2 nicht');
});

test('der Abgleich feuert gegen den echten Bestand', () => {
  // Kein Fixture: killer.json × poly_shortlist_track.json. Solange killer.json noch vom
  // Lauf VOR dem Fix stammt, fehlt polyKey — das ist die Rollout-Lücke und wird als solche
  // gemeldet, nicht als bestandener Test.
  let k, sl;
  try {
    k = JSON.parse(readFileSync(new URL('killer.json', ROOT), 'utf8'));
    sl = JSON.parse(readFileSync(new URL('poly_shortlist_track.json', ROOT), 'utf8'));
  } catch (e) { return; }
  const rows = [].concat(k.stufe1 || [], k.stufe2 || []);
  if (!rows.length) return;
  const mitKey = rows.filter((r) => r.polyKey);
  if (!mitKey.length) {
    assert.ok(!Object.prototype.hasOwnProperty.call(rows[0], 'polyKey'),
      'killer.json kennt polyKey, aber keine einzige Zeile trägt einen — dann joint nichts');
    return;   // Rollout-Lücke: killer.json ist älter als der Fix
  }
  const offen = sl.open || {};
  const nachKey = {};
  Object.keys(offen).forEach((kk) => { (nachKey[offen[kk].key] = nachKey[offen[kk].key] || []).push(offen[kk]); });
  const treffer = mitKey.filter((r) => nachKey[r.polyKey]);
  const gleicheSeite = treffer.filter((r) => (nachKey[r.polyKey] || []).some((p) => p.side === r.polySide));
  assert.ok(treffer.length >= gleicheSeite.length);
  assert.ok(gleicheSeite.length === 0 || gleicheSeite.every((r) => r.polySide),
    'eine Zeile gilt als „gleiche Seite", ohne selbst eine Seite zu tragen');
});

// ── „warum" (Lucas: „müssen einfach simpel zeigen warum damit ich schnell weiß") ─────────
test('jede Zeile beider Ebenen trägt eine Warum-Zeile', () => {
  assert.ok(/<i>warum:<\/i>/.test(CODE), 'die Warum-Zeile fehlt');
  assert.ok((CODE.match(/<i>warum:<\/i>/g) || []).length >= 2,
    'nur eine der beiden Ebenen erklärt sich — dann bleibt die andere ein Rätsel');
  assert.ok(/function \(o\) \{ return _jzWarum/.test(CODE) || /_jzWarum\(x\)/.test(CODE));
});

test('die Warum-Zeile zitiert, sie formuliert nicht neu', () => {
  // Ebene 2 nimmt `punkte.teile[].grund.text` aus killer.json; Ebene 3 nimmt `reasons` aus
  // der Poly-Zeile. Beides steht fertig im Artefakt. Würde das Frontend hier eigene Sätze
  // aus Schwellen bauen, wäre es die alte Krankheit: Produzenten-Logik im Renderer, die
  // beim nächsten Schwellenwechsel still falsch wird.
  assert.ok(/t\.punkte > 0 && t\.grund && t\.grund\.text/.test(CODE),
    'Ebene 2 baut ihre Begründung nicht aus dem Artefakt');
  assert.ok(/\(o\.poly && o\.poly\.reasons\) \|\| \[\]/.test(CODE),
    'Ebene 3 zitiert die Poly-Begründung nicht');
});

test('nur Bücher, die auch Punkte gegeben haben, dürfen als Grund gelten', () => {
  // Sonst stünde „Pinnacle hat dieselbe Seite als Favorit" unter einer Zeile, in der
  // Pinnacle gar nicht zugestimmt hat — ein Satz, der die Zahl daneben widerlegt.
  const src = CODE.slice(CODE.indexOf('warum: (pk.teile'), CODE.indexOf('warum: (pk.teile') + 400);
  assert.ok(/t\.punkte > 0/.test(src));
});

test('ohne Begründung steht keine leere Zeile da', () => {
  assert.ok(/pkt && pkt\.warum && pkt\.warum\.length/.test(CODE),
    'eine leere Warum-Zeile wäre eine Behauptung über nichts');
});

test('die beiden Köpfe sagen, was sie voneinander unterscheidet', () => {
  assert.ok(/gleichzeitig<\/b> auf derselben Seite \(UND\)/.test(CODE),
    'Ebene 2 sagt nicht, dass sie eine Konjunktion ist');
  assert.ok(/eine Quelle genügt, kein UND/.test(CODE),
    'Ebene 3 sagt nicht, dass sie eine Disjunktion ist');
});
