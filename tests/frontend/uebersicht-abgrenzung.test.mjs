// tests/frontend/uebersicht-abgrenzung.test.mjs — 30.08.2026
//
// Lucas: „wir müssen halt hier noch irgendwie rausarbeiten was der unterschied [ist]".
//
// „Mehrfach gedeckt" und „Top-Wetten jetzt" stehen untereinander, sind beide geldgetrieben und
// sahen aus wie zweimal dasselbe. Gebaut sind sie gegensätzlich:
//   · Mehrfach gedeckt = KONJUNKTION. Alle Bedingungen gleichzeitig, sonst fällt die Zeile raus.
//     Kann leer sein — und leer ist dort eine Aussage.
//   · Top-Wetten jetzt = DISJUNKTION. Das stärkste Einzelsignal über alle Flächen; EINE Quelle
//     genügt. Ist praktisch nie leer, also steht dort auch an einem schwachen Tag etwas.
// Diese Tests halten die Abgrenzung fest — und die Brücke: ein Spiel, das in BEIDEN steht,
// wird als solches markiert, statt wie eine Doppelung auszusehen.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const MOD = new URL('../../main-dashboard.js', import.meta.url);
const ko = (h = 2) => new Date(Date.now() + h * 3600e3).toISOString();
const jetzt = new Date().toISOString();

const klZeile = (id, home, away, extra = {}) => ({
  matchId: id, home, away, league: 'English Premier League', kickoff: ko(),
  markt: 'Match Odds', seite: 'home', name: home, odd: 1.8, haltePreis: 1.8, anteilPct: 74,
  stufe: 2, verstaerker: [], rang: 55, track: null, streak: null, poly: null,
  gehaltenSeit: jetzt, zuletztAktiv: jetzt, aktiv: true, ...extra,
});
// Eine Betfair-Zufluss-Zeile — die Fläche, auf der sich beide Sektionen überhaupt treffen können.
const flow = (id, home, away) => ({
  matchId: id, home, away, league: 'English Premier League', market: 'Match Odds',
  sideName: home, deltaEur: 41000, nowEur: 260000, odd: 1.8, dir: 'in', kickoff: ko(),
});

function render({ killer = null, flowRows = [] } = {}) {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="mainDashPanel"></div></body>',
    { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve(null) });
  w.eval(readFileSync(MOD, 'utf8'));
  w._mdState.data = {
    liga: null, mls: null, ligaStreaks: null, mlsStreaks: null, betfair: null, whales: null,
    killer, freigabe: { alle: [{ schublade: 'Konjunktion · Betfair-Kern', n: 70,
      status: 'geprueft', roi: 0.117, roiLb: -0.058, clv: 3.51, clvLb: 2.72 }] },
    bfOverview: { steam: [], flow: flowRows },
  };
  w._renderMainDash();
  const html = w.document.getElementById('mainDashPanel').innerHTML;
  const box = w.document.getElementById('mdJetztBox');
  // 01.09.2026: beide sind jetzt Ebenen EINER Sektion — per DOM greifbar, nicht per Textstelle.
  const ebene = (nr) => {
    const n = w.document.querySelector('.md-eb-n.e' + nr);
    return n ? n.closest('.md-eb').outerHTML : '';
  };
  return { html, jetzt: box ? box.innerHTML : '', ebene };
}

// 01.09.2026 (Lucas: „das wirkt jetzt schon sehr oft quasi redundant, oder?"): die beiden stehen
// seither als Ebene 2 und 3 EINER Sektion untereinander. Damit wiegt die Abgrenzung noch schwerer
// als vorher — untereinander in einem Rahmen muss jede Ebene sagen, warum sie nicht die andere ist.
// 01.09.2026, zweite Fassung: aus dem harten Filter wurde ein PUNKTESTAND (Lucas: „die Bücher alle
// im Vergleich … mit einer Punkteanzeige"). Die Abgrenzung zur Rangliste bleibt damit bestehen und
// wird sogar schärfer — Ebene 2 wiegt BÜCHER, Ebene 3 sortiert Einzelsignale.
test('beide Ebenen sagen, wie sie gebaut sind — Punktestand gegen Rangliste', () => {
  const { ebene } = render({ killer: { stufe1: [], stufe2: [klZeile('1', 'Arsenal', 'Gegner')] } });
  assert.match(ebene(2), /class="md-mech"[^>]*>Punktestand</, 'die Bücher-Ebene heißt Punktestand');
  assert.match(ebene(3), /class="md-mech"[^>]*>Rangliste</, 'die Disjunktion heißt Rangliste');
  assert.doesNotMatch(ebene(2), />Rangliste</, 'die Bauarten dürfen sich nicht vermischen');
});

test('die Köpfe nennen die Folge, nicht nur den Namen', () => {
  // Das ist der Unterschied, der beim Nachspielen zählt: oben muss ALLES zusammenkommen und
  // eine leere Sektion ist dort eine Aussage — unten genügt EINE Quelle.
  const { html } = render({ killer: { stufe1: [], stufe2: [klZeile('1', 'Arsenal', 'Gegner')] },
    flowRows: [flow('99', 'Everton', 'Fulham')] });
  // Ebene 2 sagt jetzt, WIE gewichtet wird (Buch schlägt Kriterium) und dass ein nicht erhobenes
  // Buch den Nenner senkt statt Punkte zu kosten — das ist die Aussage, die beim Nachspielen zählt.
  assert.match(html, /senken den Nenner/);
  assert.match(html, /leer heißt leer/);
  assert.match(html, /eine Quelle genügt, kein UND/);
});

test('ein Spiel in BEIDEN Sektionen wird als gedeckt markiert, nicht doppelt gezeigt', () => {
  const { jetzt: jz } = render({
    killer: { stufe1: [], stufe2: [klZeile('42', 'Arsenal', 'Chelsea')] },
    flowRows: [flow('42', 'Arsenal', 'Chelsea')],
  });
  assert.match(jz, /🔒 gedeckt/, 'die Brücke zwischen den Sektionen');
  assert.match(jz, /Stufe 2/, 'und sie sagt, welche Stufe');
});

test('ohne Deckung bleibt die Top-Wette unmarkiert', () => {
  const { jetzt: jz } = render({
    killer: { stufe1: [], stufe2: [klZeile('42', 'Arsenal', 'Chelsea')] },
    flowRows: [flow('99', 'Everton', 'Fulham')],
  });
  assert.match(jz, /Everton/);
  assert.doesNotMatch(jz, /🔒 gedeckt/, 'ein anderes Spiel ist nicht gedeckt');
});

test('ohne Killer-Daten markiert die Rangliste gar nichts', () => {
  const { jetzt: jz } = render({ killer: null, flowRows: [flow('42', 'Arsenal', 'Chelsea')] });
  assert.match(jz, /Arsenal/);
  assert.doesNotMatch(jz, /🔒 gedeckt/, 'fehlende Information ist keine Deckung — fail-closed');
});

test('die Markierung verändert den Rang NICHT', () => {
  // Bewusst: den Score anzuheben wäre eine Auswahl-Entscheidung (Lucas' Sache), keine Anzeige.
  const a = render({ killer: { stufe1: [], stufe2: [klZeile('42', 'Arsenal', 'Chelsea')] },
    flowRows: [flow('42', 'Arsenal', 'Chelsea'), flow('99', 'Everton', 'Fulham')] });
  const b = render({ killer: null,
    flowRows: [flow('42', 'Arsenal', 'Chelsea'), flow('99', 'Everton', 'Fulham')] });
  const reihe = (h) => [...h.matchAll(/class="md-jz-nm">([^<]+)</g)].map(m => m[1]);
  assert.deepEqual(reihe(a.jetzt), reihe(b.jetzt), 'dieselbe Reihenfolge mit und ohne Deckung');
});
