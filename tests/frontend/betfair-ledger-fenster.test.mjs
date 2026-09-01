// tests/frontend/betfair-ledger-fenster.test.mjs — 01.09.2026
//
// Lucas: „aja und kann es sein dass da schon ewig 8000 steht … bild mir ein sollte mehr sein."
//
// Konnte es, und es war schlimmer als ein Anzeigefehler. RESULTS_KEEP deckelte den Ledger auf 8000
// Zeilen; bei ~1.300 Abrechnungen am Tag hielt er damit SECHS Tage. Die Kachel „Signale 8000" las
// sich wie eine Gesamthistorie und war ein rollendes Fenster — und weil jeder Liga×Markt-Bucket
// dadurch bei n≈24 endete, entschied das Lern-Board (ab n=15 dreht es Card-Signale um) dauerhaft
// auf einer Wochenstichprobe.
//
// Der Deckel steht jetzt auf 40.000. Diese Tests sichern die andere Hälfte: dass die Oberfläche
// eine gedeckelte Zahl nie wieder als „alles" ausgibt.
//  1. Neben der Signal-Zahl steht immer, wie viele Tage sie abdeckt.
//  2. Fehlt die Fenster-Angabe, wird NICHTS erfunden — lieber gar keine Angabe als eine falsche.
//  3. Das Lern-Board beziffert seinen eigenen Ausschnitt (wirkende von allen Kombinationen) und
//     sagt es, wenn der Display-Cap wirkende Zeilen verschluckt.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';

const ROOT = new URL('../../', import.meta.url);
const JS = readFileSync(new URL('betfair-radar.js', ROOT), 'utf8');

const C = { ink: '#e6edf3', mut: '#8b949e', dim: '#6e7681', bd: '#30363d', card: '#0d1117',
            back: '#3fb950', lay: '#f85149', gold: '#ffb80c', purp: '#a371f7' };

// Blockgrenzen an Funktionsnamen, nicht an Zeichen-Offsets (das ist am 31.08. dreimal gebrochen).
function schneide(vonMarke, bisMarke) {
  const von = JS.indexOf(vonMarke), bis = JS.indexOf(bisMarke);
  assert.ok(von > 0, 'Anker weg: ' + vonMarke);
  assert.ok(bis > von, 'Anker weg: ' + bisMarke);
  return JS.slice(von, bis);
}

function ladeFenster() {
  const g = {};
  // eslint-disable-next-line no-new-func
  new Function('exp', 'C', schneide('function _fensterTxt', 'function trackHeadline')
    + '\nexp.f=_fensterTxt;')(g, C);
  return g.f;
}
const fensterTxt = ladeFenster();

test('die Fensterdauer wird aus dem Aggregat gelesen, nicht geschätzt', () => {
  const s = fensterTxt({ fenster: { n: 8000, tage: 5.9, von: '2026-08-26T17:55:59+00:00', bis: '2026-09-01T15:55:41+00:00' } });
  assert.match(s, /5\.9 Tage/, 'die Dauer fehlt: ' + s);
  assert.match(s, /26\.08/, 'der Beginn fehlt: ' + s);
});

test('ohne Fenster-Angabe wird nichts erfunden', () => {
  // Ein Aggregat aus der Zeit vor dem 01.09. trägt kein `fenster`. Dann darf dort NICHTS stehen —
  // eine geratene Dauer wäre schlimmer als die alte, stumme 8000.
  for (const t of [null, {}, { fenster: null }, { fenster: {} }, { fenster: { tage: null } },
                   { fenster: { tage: 'sechs' } }]) {
    assert.strictEqual(fensterTxt(t), '', 'erfindet etwas bei ' + JSON.stringify(t));
  }
});

test('lange Fenster werden ohne Nachkommastelle gezeigt, kurze mit', () => {
  assert.match(fensterTxt({ fenster: { tage: 42.3, von: '2026-07-01T00:00:00+00:00', bis: '2026-08-12T00:00:00+00:00' } }), /^42 Tage/);
  assert.match(fensterTxt({ fenster: { tage: 5.9, von: '2026-08-26T00:00:00+00:00', bis: '2026-09-01T00:00:00+00:00' } }), /^5\.9 Tage/);
});

test('die Signal-Kachel trägt die Fensterdauer', () => {
  // Ohne diese Kopplung steht die Zahl wieder nackt da und liest sich als Gesamthistorie.
  const block = schneide("kpi('Signale'", "kpi('Trefferquote'");
  assert.match(block, /_fensterTxt\(t\)/, 'die Signal-Kachel nennt das Fenster nicht mehr');
});

test('die Überschrift sagt „rollendes Fenster" statt „über alle"', () => {
  const block = schneide('War die Kohle erfolgreich?', '\n      + kpis');
  assert.match(block, /rollendes Fenster/, 'die Überschrift verspricht wieder Vollständigkeit');
  assert.doesNotMatch(block, /Gesamt-Bilanz über alle/, '„über alle" ist genau die falsche Zusage');
});

// ── Lern-Board: der Ausschnitt muss sich selbst beziffern ────────────────────────────────────
function ladeLernBoard() {
  const bf = {};                       // mutierbar — die Tests setzen bf.track vor jedem Aufruf
  const g = {};
  const quelle = schneide('var BF_LB_HALF', 'function renderTrackBoard');
  // eslint-disable-next-line no-new-func
  new Function('exp', 'C', 'MK_ID', 'esc', '_roiTxt', 'bfTrackWirkung', 'BF_TR_MIN_N',
               'BF_TR_FADE', 'BF_TR_BOOST', '_bf',
    quelle + '\nexp.f=renderBfLernBoard;')(
    g, C, { 'Match Odds': { label: 'Sieger' } }, (s) => String(s),
    (r) => (r == null ? '—' : (r >= 0 ? '+' : '') + Math.round(r * 100) + '%'),
    (v) => (!v || !v.n || typeof v.roi !== 'number') ? null
      : v.n < 15 ? { art: 'sammelt', txt: '⏳ sammelt', sub: 'n' + v.n + '/15', col: C.dim }
      : v.roi <= -0.10 ? { art: 'fade', txt: '⚠️ verliert hier', sub: 'Card fadet', col: C.lay }
      : v.roi >= 0.05 ? { art: 'boost', txt: '✅ trägt', sub: 'Card verstärkt', col: C.back }
      : { art: 'neutral', txt: '➖ neutral', sub: 'ohne Wirkung', col: C.mut },
    15, -0.10, 0.05, bf);
  return { render: g.f, bf: bf };
}
const LB = ladeLernBoard();

function track(nWirkend, nSammelnd) {
  const b = {};
  for (let i = 0; i < nWirkend; i++) b['Liga ' + i + '|Match Odds'] = { n: 20, roi: 0.12 };
  for (let i = 0; i < nSammelnd; i++) b['Klein ' + i + '|Match Odds'] = { n: 4, roi: 0.5 };
  return { byLeagueMarket: b };
}

function board(nWirkend, nSammelnd) {
  LB.bf.track = track(nWirkend, nSammelnd);
  return LB.render();
}

test('das Lern-Board beziffert, wie klein sein Ausschnitt ist', () => {
  // Das war Lucas' Frage: oben ein paar Ligen, unten alle. Der Grund (n≥15) stand da, die
  // Größenordnung nicht — gemessen am 01.09.: 60 von 1418 Kombinationen, 12 von 212 Ligen.
  const h = board(3, 97);
  assert.match(h, /3 von 100/, 'der Ausschnitt wird nicht beziffert: ' + h.slice(0, 600));
  assert.match(h, /Tabelle unten zeigt alle/, 'der Verweis auf die vollständige Tabelle fehlt');
});

test('verschluckt der Display-Cap wirkende Zeilen, wird das gesagt', () => {
  // 30 wirkende Kombinationen, Cap 24 → 6 sind unsichtbar. Vorher stand dort nur „Top 24 nach
  // Stichprobe", was wie eine Sortierung klingt, nicht wie ein Verlust.
  const h = board(30, 0);
  assert.match(h, /NICHT sichtbar/, 'der Cap verschweigt sechs wirkende Zeilen: ' + h.slice(-600));
  assert.match(h, /6 weitere/, 'die Zahl der verschluckten Zeilen fehlt');
});

test('greift der Cap nicht, wird kein Verlust behauptet', () => {
  const h = board(5, 0);
  assert.doesNotMatch(h, /NICHT sichtbar/, 'behauptet einen Verlust, den es nicht gibt');
  assert.match(h, /Alle 5 wirkenden/, 'sagt nicht, dass alles gezeigt wird');
});

test('wirkt noch nichts, sagt das Board das statt leer zu bleiben', () => {
  assert.match(board(0, 40), /noch nichts aktiv/, 'ein leeres Board ohne Erklärung ist keine Aussage');
});
