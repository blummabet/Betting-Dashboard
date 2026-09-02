// tests/frontend/poly-split-und-bewegung.test.mjs — 02.09.2026
//
// Lucas: „kannst du mal die inhalte hier checken bei 'Großes Geld' und 'Bewegung' ob das
// vernünftig implementiert oder man da mehr rausholen kann".
//
// Konnte man. Beide Flächen behaupteten Dinge, die ihre Daten nicht trugen:
//
//  · Geld-Split: bei zwei Ausgängen ist der Geld-Anteil rechnerisch der Preis (gemessen an
//    1.262 Märkten: Abweichung Median 0,0pp); bei drei Ausgängen holte /holders genau EINE Seite
//    je Ausgang, ohne mitzuschreiben, ob das alle waren — der „Favorit" konnte dort eine
//    abgeschnittene Liste sein (Osasuna 44,5¢ $745.597 gegen Getafe 22,5¢ $13.006).
//  · Bewegung: gemessen wurde gegen den ältesten Snapshot (Fenster 0,1h bis 29,2h, trotzdem
//    gegeneinander sortiert), und „Steam vs dreht" las EINEN Tick — 65% davon waren exakt 0,00pp.
//
// Diese Tests sichern, dass die Oberfläche jetzt sagt, was sie weiß, und schweigt, wo sie nichts weiß.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';

const ROOT = new URL('../../', import.meta.url);
const JS = readFileSync(new URL('poly-wallets.js', ROOT), 'utf8');
// Kommentare raus, wo wir auf ABWESENHEIT von Code prüfen: die Kommentare beschreiben
// absichtlich, was früher dastand, und würden sonst gegen den eigenen Test anschlagen.
const CODE = JS.replace(/^\s*\/\/.*$/gm, '');

// Blockgrenzen an Funktionsnamen, nie an Zeichen-Offsets.
function schneide(vonMarke, bisMarke) {
  const von = JS.indexOf(vonMarke), bis = JS.indexOf(bisMarke);
  assert.ok(von > 0, 'Anker weg: ' + vonMarke);
  assert.ok(bis > von, 'Anker weg: ' + bisMarke);
  return JS.slice(von, bis);
}

function ladeSplit() {
  const g = {};
  // eslint-disable-next-line no-new-func
  new Function('exp', schneide('const PW_SPLIT_ARTEN', 'function _pwNormStage')
    + '\nexp.guete=_pwSplitGuete; exp.seite=_pwGeldSeite; exp.ARTEN=PW_SPLIT_ARTEN;'
    + '\nfunction _pwEsc(s){return String(s);}')(g);
  return g;
}

function ladeBewegung() {
  const g = {};
  // eslint-disable-next-line no-new-func
  new Function('exp', schneide('const PW_MOVE_FENSTER_H', 'function _pwMomentum')
    + '\nexp.steigung=_pwTrendSteigung; exp.schwanz=_pwTrendSchwanz;'
    + '\nexp.FENSTER=PW_MOVE_FENSTER_H; exp.MINPP=PW_MOVE_MIN_PP; exp.TRENDN=PW_MOVE_TREND_N;')(g);
  return g;
}

const S = ladeSplit();
const B = ladeBewegung();

// ── Geld-Split ───────────────────────────────────────────────────────────────
test('zwei Ausgänge werden als Preis-Echo erkannt, nicht als Mehrheit', () => {
  assert.strictEqual(S.guete({ shares: { A: 60, B: 40 }, totalUsd: 100 }).art, 'preis_echo');
});

test('drei Ausgänge mit abgeschnittener Halter-Liste sind nicht belastbar', () => {
  const g = S.guete({ shares: { O: 745597, D: 13100, G: 13006 }, totalUsd: 1796655,
                      splitGuete: { art: 'abgeschnitten', trunc: true } });
  assert.strictEqual(g.art, 'abgeschnitten');
});

test('drei Ausgänge ohne Vollständigkeits-Angabe sind „unbekannt", nie belastbar', () => {
  // Der Kern: das Backend-Feld fehlt (Alt-Bestand). Die Client-Notrechnung darf daraus KEIN
  // „belastbar" machen — sie kann die Vollständigkeit gar nicht kennen.
  assert.strictEqual(S.guete({ shares: { A: 60, B: 20, C: 5 }, totalUsd: 100 }).art, 'unbekannt');
});

test('drei Ausgänge mit vollständiger Halter-Liste sind belastbar', () => {
  assert.strictEqual(S.guete({ shares: { A: 60, B: 20, C: 5 }, totalUsd: 100,
                               splitGuete: { art: 'belastbar', trunc: false } }).art, 'belastbar');
});

test('das Backend-Urteil hat Vorrang vor der Client-Rechnung', () => {
  const m = { shares: { A: 60, B: 40 }, totalUsd: 100, splitGuete: { art: 'belastbar', abdeckung: 0.9 } };
  assert.strictEqual(S.guete(m).art, 'belastbar');
});

test('das Volumen entscheidet NICHT über die Güte', () => {
  // Die Kernkorrektur: `totalUsd` ist gehandeltes Volumen, nicht offene Position. Ein umsatz-
  // starker Markt darf allein deswegen nicht schlechter dastehen.
  for (const tot of [0, null, undefined, -3, 1e9]) {
    assert.strictEqual(S.guete({ shares: { A: 6, B: 2, C: 1 }, totalUsd: tot }).art, 'unbekannt',
      'totalUsd=' + tot);
  }
});

test('bei einem Zwei-Wege-Markt steht der Preis da, nicht ein Prozentsatz als Signal', () => {
  const html = S.seite({ shares: { A: 60, B: 40 }, totalUsd: 100 }, 'Alcaraz', 60, '60¢', false);
  assert.match(html, /= Preis/, 'kennzeichnet das Preis-Echo nicht: ' + html);
  assert.ok(!/60%/.test(html), 'gibt den Anteil weiter als eigene Aussage aus: ' + html);
});

test('bei abgeschnittener Liste wird KEINE Seite behauptet', () => {
  const html = S.seite({ shares: { O: 96, D: 2, G: 2 }, totalUsd: 1000,
                         splitGuete: { art: 'abgeschnitten', trunc: true } }, 'Osasuna', 96, '45¢', false);
  assert.match(html, /unvollständig/, html);
  assert.ok(!/Osasuna/.test(html), 'nennt trotzdem eine Seite: ' + html);
});

test('bei ungeprüftem Split wird KEINE Seite behauptet', () => {
  const html = S.seite({ shares: { O: 96, D: 2, G: 2 }, totalUsd: 1000 }, 'Osasuna', 96, '45¢', false);
  assert.match(html, /ungeprüft/, html);
  assert.ok(!/Osasuna/.test(html), 'nennt trotzdem eine Seite: ' + html);
});

test('bei belastbarem Split steht die Seite ganz normal da', () => {
  const html = S.seite({ shares: { H: 60, D: 20, A: 5 }, totalUsd: 100,
                         splitGuete: { art: 'belastbar', trunc: false } }, 'Bayern', 70, '65¢', false);
  assert.match(html, /Bayern/);
  assert.match(html, /70%/);
});

test('ohne Aufteilung wird nichts behauptet', () => {
  assert.match(S.seite({ shares: {}, totalUsd: 100 }, '—', 0, null, false), /keine Seiten-Aufteilung/);
});

// ── Rückblick ────────────────────────────────────────────────────────────────
test('ein unbekanntes Liga-Verdikt wird nicht als „neutral" ausgegeben', () => {
  // Hier stand `V[u.v] || V.gleichauf` — „zu wenig Daten" wurde damit zu ⚪ neutral,
  // also zu einer Aussage, wo keine ist.
  const von = CODE.indexOf('const _urteilChip='), bis = CODE.indexOf('function _pwShortlist');
  const block = CODE.slice(von, bis);
  assert.ok(von > 0 && bis > von, 'Anker weg');
  assert.ok(!/\|\|\s*V\.gleichauf/.test(block), 'der stille Rückfall auf „gleichauf" ist zurück');
  assert.match(block, /kein Urteil/, 'sagt nicht, dass kein Urteil vorliegt');
});

test('der Rückblick beziffert, wovon er lebt', () => {
  const block = schneide('const gueteZeile', 'const zuDuenn');
  assert.match(block, /belastbar/);
  assert.match(block, /preis_echo/);
  assert.match(block, /abgeschnitten/);
  assert.match(block, /unbekannt/);
});

// ── Bewegung ─────────────────────────────────────────────────────────────────
test('die Steigung braucht mindestens drei Punkte, sonst gibt es keine', () => {
  assert.strictEqual(B.steigung([[0, 10], [1, 12]]), null);
  assert.strictEqual(B.steigung([[0, 10], [1, 12], [2, 14]]), 2);
});

test('ein Sprung am Anfang kippt die Richtung nicht mehr', () => {
  // [10,30,25,22]: Gesamt-Move +12, über ALLE Punkte wäre die Steigung +3,1 („zieht weiter"),
  // obwohl der Preis seit dem Sprung nur fällt. Auf dem Schwanz kommt −4 heraus.
  const p = [[0, 10], [1, 30], [2, 25], [3, 22]];
  assert.ok(B.steigung(p) > 0, 'Vorbedingung: über alles wäre es positiv');
  assert.ok(B.steigung(B.schwanz(p)) < 0, 'der Schwanz muss die Umkehr sehen');
});

test('bei stetigem Anstieg bleibt der Schwanz positiv', () => {
  const p = [[0, 10], [1, 12], [2, 14], [3, 16], [4, 18]];
  assert.ok(B.steigung(B.schwanz(p)) > 0);
});

test('der Schwanz nimmt nie weniger als drei Punkte, also zwei Intervalle', () => {
  // Drei Punkte sind das Minimum, bei dem eine Gerade mehr sieht als einen einzelnen Schritt.
  // Gemessen war genau das der alte Fehler: „Steam vs dreht" aus EINEM Tick.
  assert.ok(B.schwanz([[0, 1], [1, 2], [2, 3], [3, 4]]).length >= 3);
  assert.ok(B.schwanz([[0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [5, 6]]).length >= 3);
});

test('eine Richtung gibt es erst ab vier Punkten im Fenster', () => {
  // Bei genau drei Punkten IST der Schwanz die ganze Reihe, und die Gerade wird vom ersten
  // Schritt dominiert: [60,66,63] steigt rechnerisch, obwohl der Preis zuletzt fällt.
  assert.strictEqual(B.TRENDN, 4);
  const drei = [[0, 60], [0.5, 66], [1, 63]];
  assert.ok(B.steigung(B.schwanz(drei)) > 0, 'Vorbedingung: über drei Punkte sieht es steigend aus');
  const vier = [[0, 50], [0.5, 60], [1, 58], [1.5, 54]];
  assert.ok(B.steigung(B.schwanz(vier)) < 0, 'ab vier Punkten sieht der Schwanz die Umkehr');
});

test('das Fenster ist fest und die Rauschkante liegt über einem Tick', () => {
  assert.strictEqual(B.FENSTER, 6);
  assert.ok(B.MINPP >= 2, 'unter 2pp sind zwei Ticks des 0,5¢-Rasters');
});

test('der alte Rückfall auf den ältesten Snapshot ist weg', () => {
  // Im GANZEN Tab, nicht nur in der Tabelle: dieselbe Rechnung steckte auch in _pwMoveFor
  // (speist die BET/FADE-Conviction) und in _pwFlips.
  assert.ok(!/base\s*=\s*arr\[0\]/.test(CODE), 'arr[0] als Basis ist irgendwo zurück');
  const block = JS.slice(JS.indexOf('function _pwMomentum(hist)'));
  assert.match(block, /fenster\[0\]/, 'die Basis kommt nicht mehr aus dem Fenster');
  assert.match(block, /tempo/, 'es wird nicht nach Tempo sortiert');
});

test('die Anpfiff-Spalte rechnet die Zeit seit dem Snapshot ab', () => {
  const block = JS.slice(JS.indexOf('function _pwMomentum(hist)'));
  assert.match(block, /htk = latest\.htk - \(jetzt-tsMs\)\/3\.6e6/,
    'htk wird wieder roh aus dem Snapshot übernommen');
});

test('laufende Spiele tragen ein Kennzeichen, dass der Spielstand im Move steckt', () => {
  const block = JS.slice(JS.indexOf('function _pwMomentum(hist)'));
  assert.match(block, /Spielstand drin/);
});

// ── Icons ────────────────────────────────────────────────────────────────────
test('auch die Conviction-Engine misst über das feste Fenster, nicht über einen Tick', () => {
  // _pwMoveFor speist `Steam läuft rein` in der Shortlist — das wog schwerer als die Tabelle.
  const von = CODE.indexOf('function _pwMoveFor(key)'), bis = CODE.indexOf('// 07.08.2026');
  const block = CODE.slice(von, bis > von ? bis : von + 2000);
  assert.match(block, /_pwFensterPunkte\(arr, PW_MOVE_FENSTER_H\)/, 'nutzt das gemeinsame Fenster nicht');
  assert.match(block, /_pwTrendSteigung\(_pwTrendSchwanz/, 'nutzt die gemeinsame Steigung nicht');
  assert.ok(!/step/.test(block), 'die Ein-Tick-Logik ist zurück: ' + block.slice(0, 200));
});

test('das Fenster ist an EINER Stelle definiert', () => {
  const treffer = CODE.match(/function _pwFensterPunkte/g) || [];
  assert.strictEqual(treffer.length, 1, 'mehr als eine Fenster-Definition');
});

test('MLB bekommt kein Basketball-Icon mehr', () => {
  const g = {};
  // eslint-disable-next-line no-new-func
  new Function('exp', schneide('const _PW_LIGA_ICON', 'function _pwSportIcon')
    + '\nexp.I=_PW_LIGA_ICON;')(g);
  assert.strictEqual(g.I.MLB, '⚾');
  assert.strictEqual(g.I.NFL, '🏈');
  assert.strictEqual(g.I.NBA, '🏀');
});
