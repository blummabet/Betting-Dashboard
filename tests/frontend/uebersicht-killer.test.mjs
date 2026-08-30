// tests/frontend/uebersicht-killer.test.mjs — 29.08.2026
//
// Lucas: „das könnte man irgendwie noch spezielle bauen oder? Also dort kommst halt nur rein
// wenn / Pini move da / Betfair geld oben und quoten mitziehen / Poly geld oben."
//
// Entschieden hat er sich für ZWEI Stufen sichtbar. Die Auswahl trifft killer.py; hier wird
// nur geprüft, dass die Übersicht sie ehrlich zeigt — vor allem die zwei Stellen, an denen
// eine solche Sektion sonst lügt:
//   · sie darf nicht „spielbar" behaupten, solange die ROI-Untergrenze unter null liegt,
//   · Stufe 2 darf nicht aussehen wie Stufe 1 (fehlendes Poly muss sichtbar fehlen).
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const MOD = new URL('../../main-dashboard.js', import.meta.url);

function render(killer, freigabe) {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="mainDashPanel"></div></body>',
    { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve(null) });
  w.eval(readFileSync(MOD, 'utf8'));
  w._mdState.data = {
    liga: null, mls: null, ligaStreaks: null, mlsStreaks: null, betfair: null, whales: null,
    killer, freigabe,
  };
  w._renderMainDash();
  const html = w.document.getElementById('mainDashPanel').innerHTML;
  const von = html.indexOf('Mehrfach gedeckt');
  return html.slice(Math.max(0, von - 400), html.indexOf('md-kl-foot') + 900);
}

const ko = () => new Date(Date.now() + 2 * 3600e3).toISOString();
const jetzt = new Date().toISOString();
const zeile = (home, extra = {}) => ({
  matchId: 'm' + home, home, away: 'Gegner', league: 'English Premier League', kickoff: ko(),
  markt: 'Match Odds', seite: 'home', name: home, odd: 1.8, haltePreis: 1.8, anteilPct: 74,
  stufe: 2, verstaerker: [], rang: 55, track: null, streak: null, poly: null,
  pinnMovePP: null, wertVsPinn: null,
  gehaltenSeit: jetzt, zuletztAktiv: jetzt, aktiv: true, ...extra,
});

const REG = (status, extra = {}) => ({
  alle: [{ schublade: 'Konjunktion · Betfair-Kern', strom: 'betfair', n: 70, status,
           roi: 0.117, roiLb: -0.058, clv: 3.51, clvLb: 2.72, ...extra }],
});

test('solange die Untergrenze unter null liegt, sagt die Sektion „beobachten"', () => {
  const html = render({ stufe1: [], stufe2: [zeile('Arsenal')] }, REG('geprueft'));
  assert.match(html, /beobachten/);
  assert.doesNotMatch(html, /freigegeben/i, 'nichts darf hier nach Freigabe aussehen');
  assert.match(html, /Untergrenze/, 'die Untergrenze gehört sichtbar dazu, nicht nur der ROI');
  assert.match(html, /Beobachtungsliste, keine Freigabe/);
});

test('freigegeben wird auch so benannt', () => {
  const html = render({ stufe1: [], stufe2: [zeile('Arsenal')] },
    REG('freigegeben', { roiLb: 0.04 }));
  assert.match(html, /freigegeben · n70/);
  assert.doesNotMatch(html, /Beobachtungsliste/);
});

test('ohne Freigabe-Datei wird nichts behauptet', () => {
  const html = render({ stufe1: [], stufe2: [zeile('Arsenal')] }, null);
  assert.match(html, /sammelt noch/);
});

test('die drei Kern-Bedingungen stehen als Beleg an der Zeile', () => {
  const html = render({ stufe1: [], stufe2: [zeile('Arsenal')] }, REG('geprueft'));
  assert.match(html, /Geld 74%/);
  assert.match(html, /frischer Zufluss/);
  assert.match(html, /Quote zieht mit/);
});

test('Stufe 2 zeigt, was ihr fehlt — sonst sieht sie aus wie Stufe 1', () => {
  const voll = zeile('Chelsea', { stufe: 1, poly: { anteilPct: 71, usd: 40000, odd: 1.75 },
    verstaerker: [{ art: 'poly', text: 'Poly 71%', gewicht: 12 },
                  { art: 'pinn', text: 'Pinnacle stimmt zu', gewicht: 10 }] });
  const html = render({ stufe1: [voll], stufe2: [zeile('Arsenal')] }, REG('geprueft'));
  assert.match(html, /Voll gedeckt/);
  assert.match(html, /Betfair-Kern/);
  assert.match(html, /Poly 71%/);
  assert.match(html, /kein Poly-Markt/, 'der Betfair-Kern muss seine Lücke zeigen');
});

test('leer heißt leer — keine erfundene Zeile, aber die Regel bleibt lesbar', () => {
  const html = render({ stufe1: [], stufe2: [],
    regeln: { text: 'Geldanteil ≥65% UND frischer Zufluss ≥€2000 UND Quote zieht mit.' } },
    REG('geprueft'));
  assert.match(html, /Gerade deckt sich nichts/);
  assert.match(html, /≥65%/);
});

// 30.08.2026 (Lucas: „das wechselt auch ohne dass ich die Seite aktualisiere"): der Treffer
// wird bis zum Anpfiff gehalten. Damit das nicht wie ein eingefrorener Fehler aussieht, muss
// die Zeile zeigen, seit wann sie steht und ob die Bedingungen gerade noch anliegen.
test('eine laufende Zeile ist von einer gehaltenen unterscheidbar', () => {
  const alt = new Date(Date.now() - 90 * 60000).toISOString();
  const html = render({ stufe1: [], stufe2: [
    zeile('Arsenal'),
    zeile('Chelsea', { aktiv: false, zuletztAktiv: alt, gehaltenSeit: alt }),
  ] }, REG('geprueft'));
  assert.match(html, /läuft gerade/);
  assert.match(html, /gehalten seit/);
  assert.match(html, /zuletzt aktiv/);
});

test('der Haltepreis bleibt stehen, die weggelaufene Quote steht daneben', () => {
  const html = render({ stufe1: [], stufe2: [zeile('Arsenal', { haltePreis: 1.80, odd: 2.40 })] },
    REG('geprueft'));
  assert.match(html, /@1\.80/, 'gezeigt wurde der Preis beim Treffer');
  assert.match(html, /jetzt 2\.40/, 'dass die Quote weggelaufen ist, darf nicht verschwiegen werden');
});

test('steht die Quote noch, wird kein Zweitpreis danebengeklebt', () => {
  const html = render({ stufe1: [], stufe2: [zeile('Arsenal', { haltePreis: 1.80, odd: 1.81 })] },
    REG('geprueft'));
  assert.doesNotMatch(html, /jetzt 1\.81/);
});
