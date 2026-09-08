// tests/frontend/uebersicht-stroeme.test.mjs — Ebene 1 als Leistungstafel (08.09.2026)
//
// Lucas: „ich kapier es einfach nicht — was wird da besonders freigegeben? … mein Ansatz wäre:
// ich seh dort die Schubladen die Sinn machen, mit etwas Stats — ROI, P/L, CLV. Und dann weiß
// ich für mich auch was ich besser folgen kann: eher Poly, eher Betfair, eher Cards."
//
// Die alte Frage („darf ich blind spielen?") wurde seit Wochen jeden Tag mit „nein" beantwortet.
// Sie bleibt — als Satz weiter unten. Zuerst steht jetzt seine Frage.
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

function schublade(over) {
  return Object.assign({ schublade: 'Liga · ABWÄGEN', strom: 'cards', art: 'verdict',
    n: 91, status: 'geprueft', roi: 0.152, roiLb: 0.008, pl: 13.8, clv: -1.52, clvLb: -2.0,
    fehltN: 0 }, over || {});
}

const FG = (over) => Object.assign({
  regeln: { minN: 30 },
  zusammenfassung: { schubladen: 3, freigegeben: 0, kandidaten: 0, ruhend: 0 },
  freigegeben: [], kandidaten: [],
  stroeme: [
    { strom: 'cards', zerlegung: 'nach Verdikt', gruppen: 4, n: 156, pl: 14.9, roi: 0.0954, clv: -2.01, belegte: 1 },
    { strom: 'betfair', zerlegung: 'nach Markt', gruppen: 7, n: 16656, pl: -26.1, roi: -0.0016, clv: null, belegte: 0 },
    { strom: 'poly', zerlegung: 'nach Conviction', gruppen: 5, n: 234, pl: -17.0, roi: -0.0726, clv: -1.28, belegte: 1 },
  ],
  alle: [schublade()],
}, over || {});

function ebene1(w, f) {
  w._mdState.data = { freigabe: f };
  w._renderMainDash();
  return w.document.querySelectorAll('section.md-sp .md-eb')[0].innerHTML;
}

test('die drei Ströme stehen mit ROI, P/L, Plays und CLV nebeneinander', () => {
  const html = ebene1(load(), FG());
  ['Cards', 'Betfair', 'Polymarket'].forEach((s) => assert.match(html, new RegExp(s), s + ' fehlt'));
  assert.match(html, /\+9\.5%/, 'Cards-ROI fehlt');
  assert.match(html, /\+14\.9/, 'Cards-P\/L fehlt');
  assert.match(html, /-2\.0pp/, 'Cards-CLV fehlt');
  assert.match(html, /16\.656/, 'die Betfair-Stichprobe fehlt');
});

test('jede Strom-Kachel nennt ihre Zerlegung — sonst liest man sie als „alles von Poly"', () => {
  // Die Schubladen eines Stroms überlappen sich; summiert wird über EINE disjunkte Zerlegung.
  const html = ebene1(load(), FG());
  assert.match(html, /nach Verdikt/);
  assert.match(html, /nach Conviction/);
  assert.match(html, /nach Markt/);
  assert.match(html, /überschneidungsfreie Zerlegung/);
});

test('der Badge sagt, wer vorn liegt — nicht „nichts freigegeben"', () => {
  const html = ebene1(load(), FG());
  assert.match(html, /Cards vorn/);
  assert.doesNotMatch(html.split('md-eb-s')[0], /nichts freigegeben/);
});

test('ist etwas freigegeben, sagt der Badge das — die strenge Aussage schlägt die Rangliste', () => {
  const f = FG({ freigegeben: [schublade({ status: 'freigegeben' })] });
  const html = ebene1(load(), f);
  assert.match(html, /1 freigegeben/);
});

test('die stärksten Schubladen stehen nach Untergrenze, nicht nach Punktschätzer', () => {
  const f = FG({ alle: [
    schublade({ schublade: 'Wenig belegt', roi: 0.36, roiLb: -0.001, pl: 11.9, n: 33 }),
    schublade({ schublade: 'Gut belegt', roi: 0.152, roiLb: 0.008, pl: 13.8, n: 91 }),
  ] });
  const html = ebene1(load(), f);
  // Nur die Bestenliste betrachten: die Namen tauchen auch im Begründungssatz darüber auf,
  // und ein indexOf über das ganze Markup würde dort hängenbleiben statt die Reihenfolge zu prüfen.
  const liste = html.split('stärksten Schubladen')[1].split('md-kl-det')[0];
  assert.ok(liste.indexOf('Gut belegt') < liste.indexOf('Wenig belegt'),
    'die höhere Untergrenze gehört nach oben, auch wenn der rohe ROI kleiner ist');
  assert.match(html, /Rendite-<b>Untergrenze<\/b>/);
});

test('jede Schubladen-Zeile trägt ROI mit UG, P/L und CLV', () => {
  const html = ebene1(load(), FG());
  assert.match(html, /ROI \+15\.2%/);
  assert.match(html, /UG \+0\.8%/);
  assert.match(html, /P\/L \+13\.8/);
  assert.match(html, /CLV -1\.5pp/);
});

test('ruhende Schubladen stehen nicht in der Bestenliste', () => {
  const f = FG({ alle: [schublade({ schublade: 'WM · ABWÄGEN', status: 'ruht', roiLb: 0.5 })] });
  const html = ebene1(load(), f);
  // Das Register unten zeigt weiterhin ALLE Schubladen — nur die Bestenliste nicht.
  const oben = html.split('md-kl-det')[0];
  assert.doesNotMatch(oben.split('stärksten Schubladen')[1] || '', /WM · ABWÄGEN/,
    'eine Schublade, die nichts mehr liefert, gehört nicht in „die stärksten"');
});

test('ohne Ströme im Artefakt wird keine Tafel erfunden', () => {
  const html = ebene1(load(), FG({ stroeme: [] }));
  assert.doesNotMatch(html, /überschneidungsfreie Zerlegung/);
  assert.match(html, /nichts freigegeben/, 'dann fällt der Badge auf die alte Aussage zurück');
});

test('die Frage der Ebene ist Lucas’ Frage, die strenge steht darunter', () => {
  const html = ebene1(load(), FG());
  assert.match(html, /Wem kann ich am ehesten folgen\?/);
  assert.match(html, /blind<\/b> folgen/);
});
