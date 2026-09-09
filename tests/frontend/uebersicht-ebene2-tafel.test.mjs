// tests/frontend/uebersicht-ebene2-tafel.test.mjs — 08.09.2026
//
// Lucas: „Ebene 0 hast du heute dazugebaut, da seh ich aber eben nicht den Mehrwert zu Ebene 2."
// Gemessen hatte er recht: 24 von 25 Zeilen der Spielzentrale standen ohnehin in
// `killer.alleBewertet`. Es war dieselbe Frage, zweimal gestellt.
//
// Der eigentliche Fund dahinter: Ebene 2 BEWERTETE 145 Spiele und ZEIGTE 6 — nur die, bei denen
// zusätzlich Geld in Bewegung war. Die anderen 139 standen in der Datei und wurden vom Frontend
// nie gelesen. Deshalb wirkte die Ebene leer, obwohl sie 145 Antworten hatte.
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

function buch(b, punkte, txt, status) {
  return { buch: b, name: b, status: status || (punkte > 0 ? 'ja' : 'nein'),
           punkte: punkte, moeglich: 3, grund: { ok: punkte > 0, text: txt }, tiefe: null, text: txt };
}

function zeile(over) {
  return Object.assign({
    matchId: '1', liga: 'UEFA Champions League', home: 'Real Madrid', away: 'Inter',
    name: 'Real Madrid', seite: 'home', odd: 1.64,
    kickoff: new Date(Date.now() + 5 * 3600e3).toISOString(),
    punkte: 10, moeglich: 13, torOk: false,
    teile: [buch('BF', 3, 'Geld 78% auf der Seite'), buch('POLY', 3, 'Poly-Geld 71% auf derselben Seite'),
            buch('PIN', 2, 'hat dieselbe Seite als Favorit'),
            buch('STAKE', 3, '$7.318 Highroller-Geld auf derselben Seite')],
  }, over || {});
}

const K = (rows) => ({ stufe1: [], stufe2: [], alleBewertet: rows, bilanz: null });

test('die Tafel zeigt die Spitze der bewerteten Spiele — auch ohne Bewegung', () => {
  const w = load();
  const html = w._mdKlTafelTest(K([zeile()]), {});
  assert.match(html, /Real Madrid/);
  assert.match(html, /10\/13/, 'Punkte MIT Nenner — 6 aus 7 ist etwas anderes als 6 aus 13');
});

test('alle vier Bücher stehen als eigene Spalte da', () => {
  const w = load();
  const html = w._mdKlTafelTest(K([zeile()]), {});
  ['Betfair', 'Polymarket', 'Pinnacle', 'Stake'].forEach((b) =>
    assert.match(html, new RegExp(b), 'Spalte fehlt: ' + b));
  assert.match(html, /Highroller-Geld/, 'der Stake-Beleg fehlt');
});

test('ein nicht erhobenes Buch ist eine leere Spalte, kein Nein', () => {
  const w = load();
  const r = zeile({ teile: [buch('BF', 3, 'Geld 78%'), buch('POLY', 0, '', 'unbekannt'),
                            buch('PIN', 2, 'Favorit'), buch('STAKE', 0, '', 'unbekannt')] });
  const html = w._mdKlTafelTest(K([r]), {});
  assert.equal((html.match(/sz-c leer/g) || []).length, 2);
  assert.match(html, /nicht erhoben/);
});

test('schwache Zeilen stehen nicht oben, werden aber gezählt', () => {
  const w = load();
  const schwach = [];
  for (let i = 0; i < 40; i++) schwach.push(zeile({ matchId: 'x' + i, punkte: 3, home: 'Klein' + i }));
  const html = w._mdKlTafelTest(K([zeile()].concat(schwach)), {});
  assert.match(html, /Real Madrid/);
  assert.doesNotMatch(html.split('md-kl-det')[0], /Klein0/, 'eine 3/13 gehört nicht nach oben');
  assert.match(html, /<b>40<\/b> weitere Spiele bewertet/);
  assert.match(html, /Alle 41 bewerteten Spiele ansehen/, 'das Register fehlt');
});

test('die Tafel wird nie zur Wand — höchstens 12 Zeilen oben', () => {
  const w = load();
  const viele = [];
  for (let i = 0; i < 30; i++) viele.push(zeile({ matchId: 'y' + i, home: 'Stark' + i }));
  const oben = w._mdKlTafelTest(K(viele), {}).split('md-kl-det')[0];
  assert.equal((oben.match(/class="sz-r"/g) || []).length, 12);
});

test('angepfiffene Spiele fallen raus', () => {
  const w = load();
  const alt = zeile({ matchId: 'z', home: 'Gelaufen', kickoff: new Date(Date.now() - 2 * 3600e3).toISOString() });
  const html = w._mdKlTafelTest(K([alt]), {});
  assert.doesNotMatch(html, /Gelaufen/);
});

test('kein Spiel über der Schwelle → Ergebnis, nicht Leere', () => {
  const w = load();
  const html = w._mdKlTafelTest(K([zeile({ punkte: 3 })]), {});
  assert.match(html, /Ergebnis, kein Fehler/);
});

test('bewegte Spiele werden in der Tafel markiert', () => {
  const w = load();
  assert.match(w._mdKlTafelTest(K([zeile()]), { '1': 1 }), /Geld bewegt sich/);
  assert.doesNotMatch(w._mdKlTafelTest(K([zeile()]), {}), /Geld bewegt sich/);
});

test('Ebene 0 ist raus und die Sektion ist wieder dreistufig', () => {
  const src = readFileSync(MOD, 'utf8');
  assert.doesNotMatch(src, /_mdZentrale/, 'die Spielzentrale hängt noch drin');
  assert.doesNotMatch(src, /spielzentrale\.json/, 'die Datei wird noch geladen');
  assert.match(src, /_mdFreigabe\(\) \+ _mdKiller\(polyPlays\) \+ _mdJetzt\(polyPlays\)/);
});

test('„—" heißt nicht erhoben, „0" heißt gefragt und stimmt nicht zu', () => {
  // Ohne diesen Unterschied sehen „nicht gefragt" und „sagt nein" gleich aus — und genau
  // dafür wird der Nenner überhaupt mitgeschrieben.
  const w = load();
  const r = zeile({ punkte: 8, moeglich: 13, teile: [
    buch('BF', 0, 'Geld 62% auf der Seite'), buch('POLY', 2, 'Poly-Geld 76%'),
    buch('PIN', 2, 'Favorit'), buch('STAKE', 0, '', 'unbekannt')] });
  const html = w._mdKlTafelTest(K([r]), {});
  assert.match(html, /nicht erhoben/, 'das nicht erhobene Buch fehlt');
  assert.equal((html.match(/sz-c leer/g) || []).length, 1, 'nur Stake ist leer, Betfair nicht');
  assert.match(html, />0</, 'das gefragte Buch ohne Zustimmung muss eine 0 zeigen');
  assert.match(html, /Geld 62%/, 'und trotzdem seinen Grund');
});

// ── 08.09.2026: Geld ins Kästchen, mit Balken ──────────────────────────────────────────
// Lucas: „könnte man das optisch nicht ins Kästchen schreiben, wieviel Kohle oben liegt? Bei
// Betfair, Poly und Stake. Nur +2 und ganz mini so ein %, das sieht man ja nicht gut — unten in
// Ebene 3 ist das mit den Balken optisch besser gelöst."
//
// Der teure Teil ist nicht der Balken, sondern WORAUS er gemacht wird: bei Polymarket ist
// derselbe Anteil manchmal Geld und manchmal ein PREIS. Ein Geldbetrag aus einem Preis wäre eine
// erfundene Zahl an genau der Stelle, auf die Lucas ab jetzt schaut.
function tafelMit(w, teile) {
  return w._mdKlTafelTest(K([zeile({ home: 'PSV', away: 'Shakhtar', name: 'PSV', odd: 1.48,
                                     punkte: 7, moeglich: 10, teile: teile })]), {});
}

const gbuch = (over) => Object.assign({
  buch: 'BF', name: 'Betfair', status: 'ja', punkte: 2, moeglich: 3,
  grund: { ok: true, text: 'Geld 88% auf der Seite' }, tiefe: { ok: false, text: 'x' },
  geld: { anteil: 0.88, betrag: 1840000, gesamt: 2091581, waehrung: 'EUR', quelle: 'geld' },
}, over || {});

test('der Betrag steht als große Zahl im Kästchen, der Anteil als Balken', () => {
  const html = tafelMit(load(), [gbuch()]);
  assert.match(html, /€1\.8M|€1840K|€1\.84M/, 'der Betrag fehlt — genau der war der Wunsch');
  assert.match(html, /sz-bar/, 'ohne Balken ist es wieder nur eine Zahl');
  assert.match(html, /88 % der Seite/);
});

test('die Punkte bleiben sichtbar, aber klein — sie sind die Mechanik, nicht das Ergebnis', () => {
  const html = tafelMit(load(), [gbuch()]);
  assert.match(html, /sz-p/);
  assert.match(html, /\+2/);
});

test('⭐ ein Poly-PREIS bekommt keinen Geldbetrag — der wäre erfunden', () => {
  // 68 % Preis heißt „der Markt hält es für zu 68 % wahrscheinlich", nicht „68 % des Geldes".
  const html = tafelMit(load(), [gbuch({
    buch: 'POLY', name: 'Polymarket',
    grund: { ok: true, text: 'Poly-Preis 68% auf derselben Seite' },
    geld: { anteil: 0.68, betrag: null, gesamt: 1407, waehrung: 'USD', quelle: 'preis' },
  })]);
  assert.match(html, /Preis, kein Geldanteil/);
  assert.match(html, /68 %/);
  assert.match(html, /sz-bar/, 'der Anteil ist gemessen — der Balken stimmt, nur der Betrag fehlt');
});

test('Anteil ohne Betrag wird benannt, nicht geschätzt', () => {
  const html = tafelMit(load(), [gbuch({
    geld: { anteil: 0.88, betrag: null, gesamt: null, waehrung: 'EUR', quelle: 'geld' },
  })]);
  assert.match(html, /Betrag nicht erhoben/);
  assert.doesNotMatch(html, /€0|€NaN/, 'eine fehlende Zahl darf nie als 0 rendern');
});

test('Pinnacle bekommt keinen Balken — ein Preisbuch hat kein Geld auf einer Seite', () => {
  const html = tafelMit(load(), [gbuch({
    buch: 'PIN', name: 'Pinnacle', geld: null,
    grund: { ok: true, text: 'hat dieselbe Seite als Favorit' },
  })]);
  assert.match(html, /dieselbe Seite als Favorit/);
  const zelle = html.split('PIN')[1] || html;
  assert.doesNotMatch(zelle.split('</div>')[0] || '', /sz-bar/,
    'ein leerer Balken sähe aus wie „null Geld"');
});

test('nicht erhoben bleibt nicht erhoben — kein Balken, keine Null', () => {
  const html = tafelMit(load(), [gbuch({
    buch: 'STAKE', name: 'Stake-Highroller', status: 'unbekannt', punkte: 0, moeglich: 0,
    grund: null, tiefe: null, geld: null,
  })]);
  assert.match(html, /nicht erhoben/);
  assert.doesNotMatch(html, /\$0\b/);
});
