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
  // 03.09.2026: zwei Lesezugriffe, seit das Terminal die Auswertung mitlaedt. Was zaehlt,
  // ist NUR-lesen — und dass nichts anderes gelesen wird als diese beiden Dateien.
  const gelesen = [...CODE.matchAll(/fetch\('([^']+)'/g)].map(m => m[1].split('?')[0]);
  assert.deepEqual(gelesen.sort(), ['stake_auswertung.json', 'stake_highroller.json']);
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

// ── Schwellen (03.09.2026, Lucas: „die gehören mal etwas höher") ────────────
test('die Anzeige startet bei $5.000, nicht bei $1.000', () => {
  // Im ersten echten Ledger lagen 68 von 93 Wetten über $1.000 — das ist keine Auswahl.
  // Gesammelt wird weiter alles; das hier ist nur der Startwert der Anzeige.
  assert.ok(/var SR_MIN_USD = 5000;/.test(JS));
  assert.ok(/SR_STAKE_LIMITS = \[1000, 2500, 5000, 10000, 25000\]/.test(JS),
    'die Regler-Stufen müssen mitgewachsen sein');
});

test('die Regler können wieder runter — eine Schwelle ist kein Filter der Sammlung', () => {
  const von = JS.indexOf('SR_STAKE_LIMITS');
  const zeile = JS.slice(von, JS.indexOf('\n', von));
  assert.ok(zeile.includes('1000'), 'die niedrigste Stufe bleibt erreichbar');
});

test('ein umgerechneter Betrag sagt, dass er umgerechnet ist', () => {
  // 27% der ersten 93 Wetten liefen in eth/sol/btc/cad/try/ltc/xrp/aed. Die zählen jetzt
  // mit — aber ein Kurswert ist kein gemessener Dollarbetrag und wird als solcher markiert.
  const karte = schneide('function _srKarte', 'function _srRender');
  assert.ok(/usdGrund/.test(karte), 'die Herkunft des Betrags muss geprüft werden');
  assert.ok(/sr-um/.test(karte), 'und sichtbar markiert sein');
});

test('der Kursstand steht im Kopf', () => {
  const basis = schneide('var basis =', 'var warn =');
  assert.ok(/kurse/.test(basis), 'auch ein umgerechneter Wert nennt seine Basis');
});

// ── Terminal (03.09.2026, Lucas: „kannst ja gleich so ein Terminal bauen") ───
test('vier Ansichten, und die Weiche kennt alle', () => {
  for (const t of ['spiele', 'auffaellig', 'bilanz', 'norm']) {
    assert.ok(CODE.includes("'" + t + "'"), 'Reiter fehlt: ' + t);
  }
  assert.ok(/window\._srTab/.test(CODE), 'der Reiter-Wechsel muss aufrufbar sein');
});

test('ohne n gibt es gar keinen Prozentwert', () => {
  assert.ok(!API._srBasis({ n: 0 }).includes('%'));
  assert.ok(!API._srRendite({ beinN: 0 }).includes('%'));
});

// 04.09.2026 — der wichtigste Fund des Tages, und er betraf diesen Code:
// `belegt` hing an „Trefferquote ueber 50%". Bei Wetten mit unterschiedlichen Quoten sagt das
// NICHTS. Gemessen an 950 abgerechneten Beinen: 63,9% Treffer bei Ø-Quote 1,72 — und trotzdem
// ROI −6,8%. Wer bei 1,20 setzt, braucht 83% zum Nullpunkt.
test('die Trefferquote urteilt nicht mehr', () => {
  const s = API._srBasis({ n: 950, quote: 0.639, oQuote: 1.72 });
  assert.ok(s.includes('63.9%'), 'sie wird weiter gezeigt');
  assert.ok(!/>trägt</.test(s), 'aber sie entscheidet nichts');
  assert.ok(s.includes('1.72'), 'und nennt die Durchschnittsquote, ohne die sie bedeutungslos ist');
});

test('das Urteil haengt an der Rendite-Untergrenze', () => {
  const verlust = API._srRendite({ beinN: 950, beinRoi: -0.068, beinRoiUg: -0.115, belegt: false });
  assert.ok(verlust.includes('-6.8%'));
  assert.ok(!/>trägt</.test(verlust), 'eine negative Untergrenze bekommt kein Abzeichen');

  const traegt = API._srRendite({ beinN: 400, beinRoi: 0.09, beinRoiUg: 0.02, belegt: true });
  assert.ok(traegt.includes('+9.0%'));
  assert.ok(/>trägt</.test(traegt), 'eine positive Untergrenze bekommt eines');
  assert.ok(traegt.includes('sr-ok'));
});

test('unter der Mindestzahl gibt es kein Urteil, auch bei gutem Punktwert', () => {
  const d = API._srRendite({ beinN: 8, beinRoi: 0.5, beinRoiUg: null, belegt: false });
  assert.ok(d.includes('kein Urteil'));
  assert.ok(!/>trägt</.test(d), '+50% auf n=8 ist kein Beleg');
});

test('die Flaeche warnt, dass eine hohe Trefferquote nichts Gutes heisst', () => {
  const block = schneide('function _srBilanz', 'function _srKpi');
  assert.ok(/kein gutes Zeichen/.test(block));
  assert.ok(/83/.test(block), 'das Gegenbeispiel (1,20 braucht 83%) muss dastehen');
});

test('jede Quote nennt ihr n', () => {
  assert.ok(API._srBasis({ n: 42, quote: 0.5, ug: null }).includes('n42'));
});

test('Prozente ohne Wert sind ein Strich, keine 0', () => {
  assert.equal(API._srPct(null), '—');
  assert.equal(API._srPct(undefined), '—');
  assert.equal(API._srPct(NaN), '—');
  assert.equal(API._srPct(0), '0.0%');
});

test('fehlt die Auswertung, steht das da statt einer leeren Tabelle', () => {
  const block = schneide('if (SR_TAB !== ', 'window.initStakeRadar');
  assert.ok(/nicht lesbar/.test(block));
  assert.ok(/nichts gefunden/.test(block), 'der Unterschied muss benannt sein');
});

test('die Bilanz erklaert, warum sie Beine zaehlt und nicht Wetten', () => {
  const block = schneide('function _srBilanz', 'function _srKpi');
  assert.ok(/Beine/.test(block) && /Einzelwetten/.test(block));
  assert.ok(/[Aa]nnullierte/.test(block), 'auch, was mit annullierten Beinen passiert');
});

test('die Norm-Ansicht trennt gelernt von zu duenn', () => {
  const block = schneide('function _srNorm', '  // ── Render');
  assert.ok(/gelernt/.test(block));
  assert.ok(/ohne Norm/.test(block));
  assert.ok(/etwas anderes als/.test(block),
    'nichts wissen ist nicht dasselbe wie ein gemessenes Nein — das muss dastehen');
});

// ── Gesperrte Sportarten (03.09.2026, Lucas: „Ganze US-Sport brauch ich aktuell mal nicht") ──
test('US-Sport wird als solcher erkannt — ueber Slug und ueber Liganamen', () => {
  assert.equal(API._srKat({ kat: 'US-Sport' }), 'US-Sport');
  assert.equal(API._srKat({ sport: 'baseball', liga: 'MLB' }), 'US-Sport');
  assert.equal(API._srKat({ sport: 'american-football', liga: 'NFL' }), 'US-Sport');
  assert.equal(API._srKat({ sport: null, liga: 'NBA Summer League' }), 'US-Sport');
  assert.equal(API._srKat({ sport: null, liga: 'NHL Preseason' }), 'US-Sport');
  // 03.09.2026: die Liga hiess 'NCAA, Regular' — ein Muster mit Leerzeichen statt
  // Wortgrenzen lief daran vorbei, und american-football fehlte im Rueckfall ganz.
  assert.equal(API._srKat({ sport: null, liga: 'NCAA, Regular' }), 'US-Sport');
  assert.equal(API._srKat({ sport: 'american-football', liga: 'NCAA, Regular' }), 'US-Sport');
  assert.equal(API._srKat({ sport: null, liga: 'NFL - Preseason' }), 'US-Sport');
});

test('das Rueckfall-Muster steht in Terminal und Uebersicht gleich', () => {
  // Zwei Flaechen, dasselbe Urteil — sonst zeigt die eine, was die andere sperrt.
  // Verglichen wird der Mustertext selbst, nicht ein nachgebautes Regex: ein Test, der die
  // Regel noch einmal formuliert, prueft nur sich selbst.
  const uebersicht = readFileSync(new URL('main-dashboard.js', ROOT), 'utf8');
  const holen = (src) => {
    const i = src.indexOf("return 'US-Sport';");
    assert.ok(i > 0, 'US-Sport-Zweig nicht gefunden');
    const zeile = src.slice(src.lastIndexOf('\n', i), i);
    const m = zeile.match(/\/(.+)\/\.test/);
    assert.ok(m, 'kein Muster in der Zeile: ' + zeile.trim());
    return m[1];
  };
  assert.equal(holen(JS), holen(uebersicht),
    'Terminal und Uebersicht muessen dieselben Sportarten sperren');
  assert.ok(holen(JS).includes('american'), 'american football muss drin sein');
  assert.ok(holen(JS).includes('ncaa'), 'ncaa muss drin sein');
});

test('Fussball und Tennis bleiben unangetastet', () => {
  assert.equal(API._srKat({ sport: 'soccer', liga: 'La Liga' }), 'Fußball');
  assert.equal(API._srKat({ sport: 'soccer', liga: 'MLS' }), 'Fußball');
  // Ohne Slug fiel MLS erst auf 'Sonstige' — gefunden vom Python-Zwilling dieses Tests.
  assert.equal(API._srKat({ sport: null, liga: 'MLS' }), 'Fußball');
  assert.equal(API._srKat({ sport: 'tennis', liga: 'US Open Men Singles' }), 'Tennis');
});

test('das gestempelte Feld schlaegt die Rueckfall-Erkennung', () => {
  assert.equal(API._srKat({ kat: 'Fußball', sport: 'baseball' }), 'Fußball');
});

test('die Sperrliste wird nicht zweimal definiert', () => {
  // Sie kommt aus stake_highroller.json (dort GESPERRT in stake_highroller_fetch.py).
  // Der Rueckfall im Frontend darf nur greifen, wenn die Datei sie nicht mitschickt.
  assert.ok(/function _srGesperrt/.test(CODE));
  assert.ok(/d\.gesperrt && d\.gesperrt\.length/.test(CODE),
    'die Datei hat Vorrang vor der eingebauten Liste');
});

test('der Filter ist nicht still — er zaehlt, was er weglaesst', () => {
  const block = schneide('var jetzt = Date.now()', 'var gruppen =');
  assert.ok(/nGesperrt\+\+/.test(block), 'weggelassene Wetten muessen gezaehlt werden');
  const anzeige = schneide('var treffer =', 'var koerper =');
  assert.ok(/ausgeblendet/.test(anzeige), 'und die Zahl muss auf der Flaeche stehen');
});

test('gesperrte Sportarten verschwinden nicht aus der Bilanz, nur aus dem Urteil', () => {
  const block = schneide('function _srGesperrteSchubladen', 'function _srKpi');
  assert.ok(/mitgeschrieben, nicht mitgez/.test(block));
  assert.ok(/gesperrteSchubladen/.test(block));
});

test('der Sport-Regler bietet gesperrte Sportarten gar nicht erst an', () => {
  const block = schneide('function _srSports', 'window._srSetMin');
  assert.ok(/sperr\.indexOf/.test(block));
});

// ── Terminal, zweiter Ausbau (03.09.2026, Lucas: „gleich wirklich top funktionell") ──
test('umkaempft: grosses Geld auf zwei Seiten ist kein einheitlicher Fluss', () => {
  const einig = { geldUsd: 10000, seiten: [{ geld: 9000 }, { geld: 1000 }] };
  const strittig = { geldUsd: 10000, seiten: [{ geld: 6000 }, { geld: 4000 }] };
  assert.equal(API._srUmkaempft(einig), false, '10 % auf der Gegenseite ist Rauschen');
  assert.equal(API._srUmkaempft(strittig), true, '40 % dagegen ist Uneinigkeit');
});

test('ein Spiel mit nur einer Seite ist nie umkaempft', () => {
  assert.equal(API._srUmkaempft({ geldUsd: 5000, seiten: [{ geld: 5000 }] }), false);
  assert.equal(API._srUmkaempft({ geldUsd: 0, seiten: [] }), false);
});

test('Anpfiff: Minuten davor positiv, danach negativ', () => {
  const inEinerStunde = new Date(Date.now() + 3600000).toISOString();
  const vorEinerStunde = new Date(Date.now() - 3600000).toISOString();
  assert.ok(Math.abs(API._srBisAnpfiff({ anpfiff: inEinerStunde }) - 60) <= 1);
  assert.ok(Math.abs(API._srBisAnpfiff({ anpfiff: vorEinerStunde }) + 60) <= 1);
  assert.equal(API._srBisAnpfiff({}), null, 'ohne Anpfiff wird nichts behauptet');
});

test('der Norm-Faktor nimmt den groessten EINZELNEN Einsatz, nicht die Summe', () => {
  // Zehn Wetten a $2.000 sind ein normaler Abend, EINE ueber $30.000 ist das Ereignis.
  const block = schneide('function _srNormFaktor', 'function _srUmkaempft');
  assert.ok(/groesster/.test(block));
  assert.ok(!/geldUsd/.test(block), 'die Spielsumme waere hier das falsche Mass');
  assert.ok(/basis !== 'gelernt'/.test(block), 'ohne gelernte Norm gibt es keinen Faktor');
});

test('Kombis zaehlen auch beim Norm-Faktor nicht', () => {
  const block = schneide('function _srNormFaktor', 'function _srUmkaempft');
  assert.ok(/!w\.kombi/.test(block));
});

test('der Spielbar-Filter laesst 30 Minuten Live zu und sagt, was er weglaesst', () => {
  const block = schneide('if (SR_NUR_SPIELBAR)', 'gruppen.sort');
  assert.ok(/m > -30/.test(block));
  assert.ok(/zu weit im Spiel/.test(CODE), 'die weggelassenen muessen gezaehlt werden');
});

test('nach × Norm laesst sich sortieren', () => {
  assert.ok(/SR_SORT === 'norm'/.test(CODE));
  assert.ok(/'× Norm'/.test(CODE));
});

test('eine Sammel-Luecke steht auf der Flaeche, nicht nur im JSON', () => {
  const basis = schneide('var basis =', 'var warn =');
  assert.ok(/Lücke/.test(basis));
  assert.ok(/nicht gesehen/.test(basis), 'und sie muss erklaert sein');
});

test('Karten lassen sich aufklappen, ohne dass die Seite neu laedt', () => {
  assert.ok(/window\._srAufklappen/.test(CODE));
  assert.ok(/SR_OFFEN\[g\.key\]/.test(CODE));
});

// ── Quotenschwelle (03.09.2026, Lucas: „@1,03 und 1,2 ist schon relativ low") ──
test('der Quotenregler startet bei 1,35 — dem Boden, den das Projekt schon hat', () => {
  assert.ok(/var SR_MIN_QUOTE = 1\.35;/.test(JS));
  assert.ok(/SR_QUOTEN = \[1\.0, 1\.20, 1\.35, 1\.60, 2\.00\]/.test(JS),
    'und „alle" muss erreichbar bleiben');
});

test('eine Wette OHNE Quote wird nicht weggefiltert', () => {
  // Unbekannt ist nicht dasselbe wie niedrig — dieselbe Regel wie beim USD-Wert.
  const block = schneide('var sperr = _srGesperrt()', 'var gruppen =');
  assert.ok(/w\.quote != null && w\.quote < SR_MIN_QUOTE/.test(block),
    'ohne Quote darf der Filter nicht greifen');
});

test('der Quotenfilter zaehlt, was er weglaesst', () => {
  const block = schneide('var sperr = _srGesperrt()', 'var gruppen =');
  assert.ok(/nQuote\+\+/.test(block));
  const anzeige = schneide('var treffer =', 'var koerper =');
  assert.ok(/unter Quote/.test(anzeige));
});

test('der Regler blendet aus, er urteilt nicht — und sagt das', () => {
  assert.ok(/blendet aus, er urteilt nicht/.test(JS),
    'ob niedrige Quoten schlechter informiert sind, ist NICHT gemessen');
});

test('möglicher Gewinn steht neben dem Einsatz und laesst sich sortieren', () => {
  assert.ok(/SR_SORT === 'gewinn'/.test(CODE));
  assert.ok(/'zu gewinnen'/.test(CODE), 'als Sortier-Option');
  const gruppen = schneide('function _srGruppen', 'function _srCtrl');
  assert.ok(/g\.gewinnUsd =/.test(gruppen));
  assert.ok(/w\.quote - 1/.test(gruppen), 'alte Zeilen ohne gewinnUsd muessen nachgerechnet werden');
});

test('die Bilanz nennt fuer den ROI die ABGERECHNETEN Wetten, nicht alle', () => {
  // Zwei Grundgesamtheiten: einsatzUsd/gewinnUsd sind alle Einzelwetten, der ROI rechnet
  // nur auf den abgerechneten. Eine Rendite neben der falschen Zahl waere irrefuehrend.
  const block = schneide('function _srBilanz', 'function _srKpi');
  assert.ok(/abgerechnetN/.test(block));
  assert.ok(/abgerechnet</.test(block));
});
