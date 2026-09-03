// tests/frontend/stake-radar.test.mjs — 03.09.2026
//
// Lucas: „ich würde gerne nur im Dashboard einen Bereich mit den Spielen sehen, mit Schwellen
// die wir definieren, dann rein und wir sammeln das."
//
// Der Tab ist eine Sammelansicht. Für Stake-Einsatzfluss ist im Projekt weder eine
// Trefferquote noch ein CLV gemessen — deshalb sichern diese Tests vor allem, was die
// Fläche NICHT tun darf:
//
//  · Unbekanntes Geld addieren. Eine Wette in einer Währung ohne USD-Kurs darf die
//    Spielsumme nicht als 0 aufblähen und nicht stillschweigend verschwinden.
//  · Sich als belegt ausgeben. Kein „stark/mittel/schwach", keine Ampel, keine Prozentzahl
//    ohne Basis.
//  · Die Auswahl-Schwäche der Quelle verschweigen („Wetten verbergen").
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';

const ROOT = new URL('../../', import.meta.url);
const JS = readFileSync(new URL('stake-radar.js', ROOT), 'utf8');
// Kommentare raus, wo auf ABWESENHEIT geprüft wird: sie benennen absichtlich, was fehlen soll.
const CODE = JS.replace(/^\s*\/\/.*$/gm, '').replace(/\/\*[\s\S]*?\*\//g, '');

// Blockgrenzen an Funktionsnamen, nie an Zeichen-Offsets.
function schneide(vonMarke, bisMarke) {
  const von = JS.indexOf(vonMarke), bis = JS.indexOf(bisMarke);
  assert.ok(von > 0, 'Anker weg: ' + vonMarke);
  assert.ok(bis > von, 'Anker weg: ' + bisMarke);
  return JS.slice(von, bis);
}

// Modul in einer Mini-Umgebung laden (kein DOM nötig für die reinen Rechenteile).
function laden() {
  const sandbox = { window: {}, document: { getElementById: () => null, head: { appendChild() {} }, createElement: () => ({}) }, module: { exports: {} } };
  const fn = new Function('window', 'document', 'module', JS + '\nreturn module.exports;');
  return fn(sandbox.window, sandbox.document, sandbox.module);
}
const API = laden();

const T = (min) => new Date(Date.UTC(2026, 8, 3, 18, min, 0)).toISOString();

// ── Gruppierung ─────────────────────────────────────────────────────────────
test('Wetten desselben Spiels landen in einer Gruppe', () => {
  const g = API._srGruppen([
    { event: 'Stuttgart - Bayern', liga: 'BL', ts: T(0), einsatzUsd: 9000, auswahl: 'Stuttgart', quote: 1.53 },
    { event: 'Stuttgart - Bayern', liga: 'BL', ts: T(2), einsatzUsd: 4000, auswahl: 'Stuttgart', quote: 1.55 },
    { event: 'Milan - Inter', liga: 'SA', ts: T(3), einsatzUsd: 2000, auswahl: 'Inter', quote: 2.10 },
  ]);
  assert.equal(g.length, 2);
  const bl = g.find(x => x.event === 'Stuttgart - Bayern');
  assert.equal(bl.n, 2);
  assert.equal(bl.geldUsd, 13000);
});

test('unbekanntes Geld wird gezaehlt, nicht addiert', () => {
  const [g] = API._srGruppen([
    { event: 'A - B', ts: T(0), einsatzUsd: 5000, auswahl: 'A' },
    { event: 'A - B', ts: T(1), einsatzUsd: null, waehrung: 'btc', auswahl: 'A' },
  ]);
  assert.equal(g.n, 2, 'die unbekannte Wette bleibt in der Gruppe');
  assert.equal(g.geldUsd, 5000, 'sie darf die Summe nicht als 0 mitziehen');
  assert.equal(g.nGeldBekannt, 1);
  assert.equal(g.nGeldUnbekannt, 1, 'und sie muss sichtbar bleiben');
});

test('Seiten sind nach Geld sortiert und tragen die Quotenspanne', () => {
  const [g] = API._srGruppen([
    { event: 'A - B', ts: T(0), einsatzUsd: 1000, auswahl: 'B', quote: 3.0 },
    { event: 'A - B', ts: T(1), einsatzUsd: 9000, auswahl: 'A', quote: 1.50 },
    { event: 'A - B', ts: T(2), einsatzUsd: 2000, auswahl: 'A', quote: 1.58 },
  ]);
  assert.equal(g.seiten[0].name, 'A');
  assert.equal(g.seiten[0].geld, 11000);
  assert.equal(g.seiten[0].qMin, 1.50);
  assert.equal(g.seiten[0].qMax, 1.58);
  assert.equal(g.seiten[1].name, 'B');
});

test('gleiches Team in verschiedenen Ligen ist nicht dasselbe Spiel', () => {
  const g = API._srGruppen([
    { event: 'A - B', liga: 'BL', ts: T(0), einsatzUsd: 1000 },
    { event: 'A - B', liga: 'Pokal', ts: T(1), einsatzUsd: 1000 },
  ]);
  assert.equal(g.length, 2);
});

// ── Dichte: eine Beobachtung, keine Note ────────────────────────────────────
test('Dichte findet die groesste Haeufung, nicht das engste Paar', () => {
  // Ein Ausreisser bei 0, dann vier Wetten in drei Minuten. Eine Rate n/Minuten haette
  // hier ein Zweier-Paar gekuert (2 in 1 Min = 2,0 > 4 in 3 Min = 1,33). Zwei ist keine Haeufung.
  const d = API._srDichte([
    { ts: T(0) }, { ts: T(50) }, { ts: T(51) }, { ts: T(52) }, { ts: T(53) },
  ]);
  assert.ok(d, 'Dichte muss ermittelbar sein');
  assert.equal(d.n, 4, 'die vier eng beieinander liegenden Wetten, n=' + (d && d.n));
  assert.equal(d.min, 3);
});

test('Dichte ignoriert, was weiter als das Dichtefenster auseinander liegt', () => {
  const d = API._srDichte([{ ts: T(0) }, { ts: T(30) }, { ts: T(60) }]);
  assert.equal(d, null, 'drei Wetten im Stundenabstand sind keine Haeufung');
});

test('bei Gleichstand gewinnt das kuerzere Fenster', () => {
  const d = API._srDichte([{ ts: T(0) }, { ts: T(9) }, { ts: T(40) }, { ts: T(41) }]);
  assert.equal(d.n, 2);
  assert.equal(d.min, 1);
});

test('eine einzelne Wette hat keine Dichte', () => {
  assert.equal(API._srDichte([{ ts: T(0) }]), null);
});

test('Wetten ohne Zeitstempel erzeugen keine Phantom-Dichte', () => {
  assert.equal(API._srDichte([{ ts: null }, { ts: undefined }]), null);
});

// ── Geldformat ──────────────────────────────────────────────────────────────
test('unbekanntes Geld wird als Strich gezeigt, nie als $0', () => {
  assert.equal(API._srUsd(null), '—');
  assert.equal(API._srUsd(undefined), '—');
  assert.equal(API._srUsd(NaN), '—');
  assert.equal(API._srUsd(0), '$0');
});

test('grosse Betraege bleiben lesbar', () => {
  assert.equal(API._srUsd(9000), '$9k');
  assert.equal(API._srUsd(1500000), '$1.5M');
  assert.equal(API._srUsd(450), '$450');
});

// ── Was die Flaeche nicht behaupten darf ────────────────────────────────────
test('kein Bewertungsvokabular im Code', () => {
  for (const wort of ['Strong Signal', 'Medium Signal', 'Weak Signal', 'Verdacht', 'fixed match', 'Schiebung']) {
    assert.ok(!CODE.includes(wort), 'unbelegte Bewertung im Code: ' + wort);
  }
});

test('der Kopf sagt, dass nichts gemessen ist', () => {
  const kopf = schneide('function _srRender', 'if (!d)');
  assert.ok(/keine gemessene Trefferquote/.test(kopf), 'die fehlende Messung muss im Kopf stehen');
  assert.ok(/CLV/.test(kopf));
});

test('die Auswahl-Schwaeche der Quelle steht auf der Flaeche', () => {
  assert.ok(/verbergen/.test(JS), '„Wetten verbergen" muss erklaert werden');
  assert.ok(/Auswahl, keine Grundgesamtheit/.test(JS));
  // 03.09.2026, am echten Feed geprueft: `user` ist bei JEDER Wette null. Wer hier spaeter
  // einen Track-Record je Konto plant, muss das auf der Flaeche lesen koennen.
  assert.ok(/anonym/i.test(JS), 'dass der Feed anonym ist, muss dastehen');
  assert.ok(/Track-Record je Spieler/.test(JS) || /Track-Record/.test(JS));
});

test('Kombis zaehlen nicht ins Geld eines einzelnen Spiels', () => {
  const [g] = API._srGruppen([
    { event: 'A - B', eventId: 'f1', ts: T(0), einsatzUsd: 5000, auswahl: 'A' },
    { event: 'A - B', eventId: 'f1', ts: T(1), einsatzUsd: 9000, auswahl: 'A', kombi: true, nBeine: 4 },
  ]);
  assert.equal(g.n, 2, 'die Kombi bleibt sichtbar');
  assert.equal(g.nKombi, 1);
  assert.equal(g.nEinzel, 1);
  assert.equal(g.geldUsd, 5000, 'ihr Einsatz haengt an vier Spielen — er gehoert keinem davon');
  assert.equal(g.seiten.reduce((s, x) => s + x.geld, 0), 5000, 'auch die Seiten bleiben sauber');
});

test('gruppiert wird ueber die Fixture-ID, nicht ueber den Namen', () => {
  const g = API._srGruppen([
    { event: 'A - B', eventId: 'liga', liga: 'BL', ts: T(0), einsatzUsd: 1000 },
    { event: 'A - B', eventId: 'pokal', liga: 'BL', ts: T(1), einsatzUsd: 1000 },
  ]);
  assert.equal(g.length, 2, 'dasselbe Paar in zwei Wettbewerben sind zwei Spiele');
});

test('die Seite traegt Markt UND Auswahl', () => {
  const [g] = API._srGruppen([
    { event: 'A - B', eventId: 'f1', ts: T(0), einsatzUsd: 1000, markt: 'Winner', auswahl: 'A' },
    { event: 'A - B', eventId: 'f1', ts: T(1), einsatzUsd: 1000, markt: 'Total', auswahl: 'Over 2.5' },
  ]);
  assert.equal(g.seiten.length, 2, '"Winner: A" und "Total: Over 2.5" sind nicht dieselbe Seite');
  assert.ok(g.seiten.some(s => s.name === 'Winner: A'));
});

test('ein Feed-Fehler zeigt keine alten Zahlen als aktuell', () => {
  const block = schneide("if (d.status === 'schema_unbekannt'", 'var seit =');
  assert.ok(/Kein Feed/.test(block));
  assert.ok(/return;/.test(block), 'nach der Fehlermeldung darf nicht weitergerendert werden');
});

test('jede Zahl im Kopf nennt ihre Basis', () => {
  const basis = schneide('var basis =', 'var warn =');
  assert.ok(/Sammlung seit/.test(basis));
  assert.ok(/nLedger/.test(basis));
  assert.ok(/nFenster/.test(basis));
});

test('Regler filtern nur die Anzeige, sie schreiben nichts zurueck', () => {
  for (const setter of ['_srSetMin', '_srSetN', '_srSetFenster', '_srSetSport', '_srSetSort']) {
    assert.ok(CODE.includes('window.' + setter), 'Regler fehlt: ' + setter);
  }
  assert.ok(!/fetch\([^)]*POST/i.test(CODE), 'der Tab darf nichts senden');
  assert.ok((CODE.match(/fetch\(/g) || []).length === 1, 'genau ein Lesezugriff, sonst nichts');
});

test('gelesen wird die Sicht, nie das Ledger', () => {
  assert.ok(CODE.includes('stake_highroller.json'));
  assert.ok(!CODE.includes('stake_bet_ledger.json'),
    'das Ledger bleibt auf dem Runner — es gehoert nicht ins Pages-Artefakt');
});

test('alles aus dem Feed wird escaped, bevor es ins HTML geht', () => {
  const karte = schneide('function _srKarte', 'function _srRender');
  for (const feld of ['w.markt', 'w.auswahl', 'g.event', 's.name', 'w.waehrung']) {
    assert.ok(karte.includes('_srEsc(' + feld), 'nicht escaped: ' + feld);
  }
});

test('die Nutzer-Spalte ist weg — der Feed liefert dort nie etwas', () => {
  const karte = schneide('function _srKarte', 'function _srRender');
  assert.ok(!/sr-bu/.test(karte), 'eine Spalte, die immer leer bleibt, ist kein Platzhalter wert');
});
