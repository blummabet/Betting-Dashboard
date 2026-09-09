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
