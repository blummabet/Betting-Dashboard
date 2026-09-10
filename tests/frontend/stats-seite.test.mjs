// tests/frontend/stats-seite.test.mjs — 09.09.2026
//
// Lucas: „schaffen wir eine eigene Stats-Seite? … alles auf Monatsbasis und Wochenbasis auch.
// Schön modern dargestellt, weil brauch das um es zu posten."
//
// Was hier festgehalten wird, ist nicht das Aussehen, sondern die drei Stellen, an denen so
// eine Seite lügt:
//   1. Eine unvollständige Periode sieht aus wie eine schwache.
//   2. Eine fehlende Kennzahl rendert als 0.
//   3. Der Post-Modus ändert Zahlen statt nur die Anzeige.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const SRC = readFileSync(new URL('../../stats.js', import.meta.url), 'utf8');

function laden() {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="statsPanel"></div></body>',
    { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve(null) });
  w.eval(SRC);
  return w;
}

const reihe = (over) => Object.assign({
  periode: '2026-W36', art: 'woche', von: '2026-08-31', bis: '2026-09-06',
  n: 120, treffer: 70, hitPct: 58.3, hitUg: 50.1, roi: 4.2, roiUg: 0.8, pl: 5.1,
  clv: -0.4, mitQuote: 120, mitClv: 90, vollstaendig: true,
}, over || {});

const block = (over) => Object.assign({
  id: 'betfair', label: 'Betfair · alle Signale', emoji: '💷', gruppe: 'Marktdaten',
  abdeckung: { von: '2026-08-26', bis: '2026-09-09' },
  reihen: [reihe(), reihe({ periode: '2026-W37', roi: -4.5, pl: -2.0, vollstaendig: false, grund: 'läuft noch' }),
           reihe({ periode: 'gesamt', art: 'gesamt', n: 17678, roi: -0.5, pl: -87.0 })],
}, over || {});

function seite(w, bloecke) {
  w._stSetDataTest({ generatedAt: '2026-09-09T06:00:00Z', ugMinN: 30, bloecke: bloecke });
  w._stRenderTest();
  return w.document.getElementById('statsPanel').innerHTML;
}

test('Wochen und Monate sind umschaltbar und die Seite zeigt beide', () => {
  const w = laden();
  const b = block({ reihen: block().reihen.concat([
    reihe({ periode: '2026-08', art: 'monat', von: '2026-08-01', bis: '2026-08-31',
            vollstaendig: false, grund: 'die Datenquelle reicht nur bis 2026-08-26 zurück' })]) });
  let h = seite(w, [b]);
  assert.match(h, /KW 36/, 'Wochenansicht ist der Start');
  assert.doesNotMatch(h.split('<tbody>')[1] || '', /Aug 2026/);
  w._stSetMode('monat');
  h = w.document.getElementById('statsPanel').innerHTML;
  assert.match(h, /Aug 2026/);
});

test('⭐ eine unvollständige Periode wird als solche benannt — nicht als schwache gezeigt', () => {
  // Der reale Fall: der Betfair-Ledger reicht nur bis 26.08. zurück. Ein Balken „August" wäre
  // seine letzte Woche und sähe neben dem September aus wie ein schwacher Monat.
  const h = seite(laden(), [block()]);
  assert.match(h, /unvollständig/);
  assert.match(h, /läuft noch/, 'und der Grund steht im Titel der Markierung');
});

test('unvollständige Balken sind auch in der Sparkline unterscheidbar', () => {
  // Farbe allein reicht nicht: grün↔rot hat für Rot-Grün-Blinde ΔE 2,2. Schraffur ist die
  // zweite Kodierung, das Vorzeichen die dritte.
  const w = laden();
  const h = w._stSparkTest(block().reihen, 'roi');
  assert.match(h, /fill="url\(#stHatch\)"/,
    'der unvollständige Balken ist wirklich schraffiert — nicht nur das Muster definiert');
  assert.match(h, /<rect[^>]*fill="#3fb950"/, 'der vollständige Balken ist gefüllt');
  assert.match(h, /<title>[^<]*läuft noch/, 'und sagt im Tooltip, warum er anders aussieht');
});

test('jede Rendite trägt ihr Vorzeichen — Farbe steht hier nie allein', () => {
  const h = seite(laden(), [block()]);
  assert.match(h, /\+4\.2%/);
  assert.match(h, /-4\.5%/);
});

test('⭐ ein Kanal ohne Quoten zeigt keine 0 %, sondern nichts — und sagt warum', () => {
  const ohne = block({
    id: 'shortlist', label: 'Heute spielenswert · Trades',
    reihen: [reihe({ roi: null, roiUg: null, pl: null, hitPct: null, hitUg: null,
                     treffer: null, mitQuote: 0 }),
             reihe({ periode: 'gesamt', art: 'gesamt', roi: null, roiUg: null, pl: null,
                     hitPct: null, hitUg: null, treffer: null, mitQuote: 0 })],
  });
  const h = seite(laden(), [ohne]);
  assert.match(h, /kein Ergebnis-Ledger/);
  assert.doesNotMatch(h, /0\.0%/, 'eine fehlende Kennzahl darf nie als Null rendern');
  assert.match(h, /nicht erhoben/);
});

test('der Post-Modus blendet nur aus — er rechnet nichts anderes', () => {
  const w = laden();
  const vorher = seite(w, [block()]);
  assert.match(vorher, /P\/L/);
  assert.match(vorher, /-87/, 'die Gesamtsumme steht da');
  w._stTogglePost();
  const nachher = w.document.getElementById('statsPanel').innerHTML;
  // Nur der Inhalt, nicht der Kopf: der Tooltip des Schalters ERKLÄRT, dass er P/L ausblendet —
  // dieses Vorkommen ist die Beschriftung, nicht die Zahl.
  const inhalt = nachher.split('</div></div>').slice(1).join('</div></div>');
  assert.doesNotMatch(inhalt, /<th>P\/L<\/th>/, 'die P/L-Spalte ist weg');
  assert.doesNotMatch(inhalt, /-87/, 'und der Betrag auch');
  assert.match(inhalt, /-0\.5%/, 'die Rendite in Prozent bleibt — sie ist keine Betragsangabe');
  assert.match(inhalt, /17\.678/, 'und die Stichprobe auch');
  // Scharf: der Post-Modus nimmt GENAU eine Spalte und GENAU eine Kachel weg. Nähme er mehr,
  // wäre der Screenshot ärmer als nötig; nähme er weniger, wäre er nicht postbar.
  const spalten = (t) => (t.match(/<th>/g) || []).length;
  assert.strictEqual(spalten(vorher) - spalten(nachher), 1, 'genau die P/L-Spalte fällt weg');
  const kacheln = (t) => (t.match(/class="st-k"/g) || []).length;
  assert.strictEqual(kacheln(vorher) - kacheln(nachher), 1, 'genau die P/L-Kachel fällt weg');
});

test('die Untergrenze steht neben jeder Quote — nicht der Punktschätzer allein', () => {
  const h = seite(laden(), [block()]);
  assert.match(h, /UG 50%/);
  assert.match(h, /UG \+0\.8%/);
});

test('ohne Artefakt steht das da — keine Null-Seite', () => {
  const w = laden();
  w._stSetDataTest(null);
  w._stRenderTest();
  const h = w.document.getElementById('statsPanel').innerHTML;
  assert.match(h, /fehlt oder ist nicht lesbar/);
  assert.doesNotMatch(h, /0 Plays/);
});

test('die Blöcke sind nach Gruppen sortiert dargestellt', () => {
  const h = seite(laden(), [block(), block({ id: 'cards', label: 'Cards', gruppe: 'Eigene Engine' })]);
  assert.match(h, /Marktdaten/);
  assert.match(h, /Eigene Engine/);
});

test('das Frontend rechnet keine Vollständigkeit selbst nach', () => {
  // Das Urteil gehört dorthin, wo die Zahl entsteht. Ein Frontend mit eigener Datums-Logik
  // hätte die Regel zweimal — die häufigste Fehlerklasse in diesem Repo.
  assert.ok(!/new Date\(\)/.test(SRC.split('function _stLoad')[0]),
    'kein eigener Zeitvergleich im Render-Pfad');
  assert.match(SRC, /r\.vollstaendig/, 'gelesen wird das Feld des Produzenten');
});

// ── 10.09.2026: die Kopfzeile ─────────────────────────────────────────────────────────────
// Lucas: „kannst du mir ganz oben ne Zusammenfassung von Cards / Betfair aus dem Public-Push /
// Poly aus den Public-Kandidaten — und das wechselt mit, wenn ich Monat/Woche umstell."
//
// Drei Stellen, an denen so eine Kopfzeile lügt, und genau die werden hier festgehalten:
//   1. Sie zeigt die LAUFENDE Periode als Schlagzeile (am Montag ein Spiel groß).
//   2. Sie zeigt eine Rendite auf n=8, ohne dass man das sieht.
//   3. Sie geht beim Umschalten NICHT mit und zeigt weiter Wochen, während Monate ausgewählt sind.
const kopfBloecke = () => [
  { id: 'cards', label: 'Cards · laufender Betrieb', emoji: '🎯', gruppe: 'Eigene Engine',
    abdeckung: { von: '2026-07-01', bis: '2026-09-10' },
    reihen: [
      reihe({ periode: '2026-W35', n: 40, hitPct: 60.0, roi: 12.0 }),
      reihe({ periode: '2026-W36', n: 44, hitPct: 70.5, roi: 18.3 }),
      reihe({ periode: '2026-W37', n: 5, hitPct: 60.0, roi: 99.9, vollstaendig: false, grund: 'läuft noch' }),
      reihe({ periode: '2026-08', art: 'monat', n: 88, hitPct: 66.0, roi: 5.5 }),
      reihe({ periode: 'gesamt', art: 'gesamt', n: 166, roi: 8.1 }),
    ] },
  { id: 'push-bf-public', label: 'Betfair · Public-Channel', emoji: '🟣', gruppe: 'Push-Kanäle',
    abdeckung: { von: '2026-08-26', bis: '2026-09-10' },
    reihen: [reihe({ periode: '2026-W36', n: 71, hitPct: 60.6, roi: 1.4 }),
             reihe({ periode: 'gesamt', art: 'gesamt', n: 220, roi: -0.8 })] },
  { id: 'poly-public', label: 'Polymarket · Public-Kandidaten', emoji: '◆', gruppe: 'Marktdaten',
    abdeckung: { von: '2026-08-05', bis: '2026-09-10' },
    reihen: [reihe({ periode: '2026-W36', n: 22, hitPct: 68.2, roi: 3.1 }),
             reihe({ periode: 'gesamt', art: 'gesamt', n: 183, roi: 6.0 })] },
];

const kopfTeil = (h) => h.split('st-kks')[1].split('st-kk-f')[0];

test('die Kopfzeile führt genau die drei Flächen, nach denen Lucas gefragt hat', () => {
  const w = laden();
  const k = kopfTeil(seite(w, kopfBloecke()));
  for (const name of ['Cards', 'Betfair', 'Poly']) assert.match(k, new RegExp(name));
  assert.match(k, /Public-Channel/);       // Betfair kommt aus dem Push, nicht aus allen Signalen
  assert.match(k, /Public-Kandidaten/);    // Poly kommt aus den Kandidaten, nicht aus der Shortlist
  assert.match(k, /Liga \+ MLS/);          // Cards ist der laufende Betrieb, ohne WM
});

test('die Kopfzeile zeigt die letzte ABGESCHLOSSENE Periode, nie die laufende', () => {
  // KW 37 läuft noch und stünde mit +99,9 % als Schlagzeile da — auf fünf Plays.
  const w = laden();
  const k = kopfTeil(seite(w, kopfBloecke()));
  assert.match(k, /KW 36/);
  assert.doesNotMatch(k, /KW 37/);
  assert.doesNotMatch(k, /99\.9|99,9/);
});

test('die Kopfzeile geht beim Umschalten auf Monate mit', () => {
  const w = laden();
  seite(w, kopfBloecke());
  w._stSetMode('monat');
  const k = kopfTeil(w.document.getElementById('statsPanel').innerHTML);
  assert.match(k, /Aug 2026/);
  assert.doesNotMatch(k, /KW 3/, 'nach dem Umschalten darf keine Kalenderwoche mehr dastehen');
  w._stSetMode('woche');
  assert.match(kopfTeil(w.document.getElementById('statsPanel').innerHTML), /KW 36/);
});

test('eine dünne Stichprobe wird als Punktschätzer gekennzeichnet', () => {
  // n=22 bei Poly liegt unter ugMinN=30 — die Zahl darf nicht als Urteil dastehen.
  const w = laden();
  const k = kopfTeil(seite(w, kopfBloecke()));
  assert.match(k, /Punktschätzer/);
  // Und die Stichprobe steht IMMER daneben, nicht nur bei den dünnen.
  assert.match(k, /71 Plays/);
  assert.match(k, /44 Plays/);
});

test('der Vergleich zur Vorperiode ist in Prozentpunkten und nennt die Periode', () => {
  const w = laden();
  const k = kopfTeil(seite(w, kopfBloecke()));
  assert.match(k, /\+6\.3 pp/);            // Cards: 18.3 − 12.0
  assert.match(k, /ggü. KW 35/);
  // Betfair und Poly haben keine Vorwoche — das muss dastehen, statt „+0.0 pp" zu behaupten.
  assert.match(k, /keine Vorperiode/);
  assert.doesNotMatch(k, /\+0\.0 pp/);
});

test('fehlt ein Bereich ganz, steht dort ein Wort statt einer Null', () => {
  const w = laden();
  const k = kopfTeil(seite(w, [kopfBloecke()[0]]));
  assert.match(k, /noch keine Daten/);
  assert.doesNotMatch(k, /0\.0%/);
});
