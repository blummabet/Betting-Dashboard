// tests/frontend/poly-public-push-record.test.mjs — 04.09.2026
//
// Lucas: „in diesem Track-Record haben wir ja die Public-Kandidaten, die aktuell vielversprechend
// aussehen … aktuell schicken wir aber schon Polymarket-Push in den Public-Channel, aber ich weiss
// nicht wie gut das abschneidet, würde mich interessieren, lässt sich das rausfinden?"
//
// In der Frage steckt eine Verwechslung, und sie ist nicht Lucas' Schuld — bis heute hiessen zwei
// verschiedene Dinge gleich:
//
//   ◆ Public-Kandidaten   Shortlist-Plays, die das harte Gate bestehen WÜRDEN. Reine Vorschau.
//                         poly-wallets.js:2200 sagt es selbst: „NUR Vorschau (sendet nicht)".
//   🐋 Public-Pushs       was poly_whale_watch.py wirklich in den Channel schickt.
//
// Die Bilanz der einen sagt nichts über die andere. Diese Tests halten die Trennung fest — und
// die Regel, unter der beide gemessen werden: die RENDITE mit Untergrenze urteilt, nie die
// Trefferquote. Der reale Stand am 04.09. ist n=3 mit ROI +58%, und genau daran zeigt sich, ob
// das Board ehrlich ist: +58% aus drei Plays ist ein Punktschätzer, kein Beleg.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const ROOT = new URL('../../', import.meta.url);
const JS = readFileSync(new URL('poly-wallets.js', ROOT), 'utf8');

function fenster() {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="polyWalletsPanel"></div></body>',
    { url: 'https://test.local/', runScripts: 'outside-only', pretendToBeVisual: true });
  dom.window.fetch = () => Promise.resolve({ ok: false, json: () => Promise.resolve(null) });
  dom.window.eval(JS);
  return dom.window;
}
const W = fenster();

// Der echte Stand aus poly_public_record.json am 04.09.2026, 05:57 UTC.
const ECHT = {
  updatedAt: '2026-09-04T05:57:44.127045+00:00',
  startAb: '2026-09-03T05:26:50Z', gesamt: 3, offen: 0, unaufloesbar: 0,
  agg: { n: 3, wins: 3, hit: 1.0, hitUg: 0.5258, nOhnePreis: 0, pnl: 17.51, stake: 30.0,
         roi: 0.5837, roiUg: null, belegt: false, geldurteil: true, clvAvg: 1.0, clvUg: null },
  byCat: { 'E-Sport': { n: 3, wins: 3, hit: 1.0, hitUg: 0.5258, nOhnePreis: 0, pnl: 17.51,
                        stake: 30.0, roi: 0.5837, roiUg: null, belegt: false, geldurteil: true,
                        clvAvg: 1.0, clvUg: null } },
  retro: { n: 34, unaufloesbar: 23,
           agg: { n: 11, wins: 10, hit: 0.9091, hitUg: 0.6772, nOhnePreis: 11, pnl: 0, stake: 0,
                  roi: null, roiUg: null, belegt: false, geldurteil: false,
                  clvAvg: null, clvUg: null } },
};

// ── Die Verwechslung, die in der Frage steckte ──────────────────────────────
test('die Vorschau steht als Vorschau da — „sendet nichts" gehört aufs Board, nicht in einen Kommentar', () => {
  assert.match(JS, /◆ Public-Kandidaten', '\(nur Vorschau — sendet nichts/);
});

test('der Push-Block sagt im Kopf, dass er NICHT die Public-Kandidaten sind', () => {
  const h = W._pwPublicPush(ECHT);
  assert.match(h, /Nicht zu verwechseln mit ◆ Public-Kandidaten/);
  assert.match(h, /poly_whale_watch\.py/);
});

// ── Das Urteil hängt an der Rendite ─────────────────────────────────────────
test('ROI +58% aus drei Plays wird NICHT als Beleg verkauft', () => {
  const h = W._pwPublicPush(ECHT);
  assert.match(h, /\+58\.4%/, 'der Punktschätzer wird gezeigt');
  assert.match(h, /zu klein für eine Untergrenze/, 'aber ausdrücklich nicht als Urteil');
  assert.ok(!/belegt: Rendite/.test(h), 'nichts darf hier „belegt" heißen');
});

test('eine glänzende Trefferquote macht keinen Beleg', () => {
  // 90% Treffer, und trotzdem Geld weg — die Quote steht da, das Urteil kommt woanders her.
  const a = { n: 40, wins: 36, hit: 0.9, hitUg: 0.78, nOhnePreis: 0, pnl: -13.0, stake: 400.0,
              roi: -0.0325, roiUg: -0.09, belegt: false, geldurteil: true, clvAvg: -0.4 };
  const h = W._pwPubBlock(a, 'Test', '');
  assert.match(h, /nicht belegt/);
  assert.match(h, /schließt Verlust nicht aus/);
});

test('erst eine Untergrenze über null heißt belegt', () => {
  const a = { n: 60, wins: 40, hit: 0.667, hitUg: 0.57, nOhnePreis: 0, pnl: 90.0, stake: 600.0,
              roi: 0.15, roiUg: 0.04, belegt: true, geldurteil: true, clvAvg: 1.2 };
  assert.match(W._pwPubBlock(a, 'Test', ''), /belegt: Rendite-Untergrenze \+4%/);
});

// ── Fehlende Preise: die Lücke wird benannt, nicht gefüllt ──────────────────
test('wo kein Einstiegspreis steht, gibt es kein Geldurteil — und das steht auch da', () => {
  const h = W._pwPublicPush(ECHT);
  assert.match(h, /bei allen 11 fehlt der Einstiegspreis/);
  assert.match(h, /Eine Trefferquote ohne die Preise ist keine Zahl/);
});

test('91% Retro-Treffer werden nicht als Ergebnis der Pushs ausgegeben', () => {
  const h = W._pwPublicPush(ECHT);
  assert.match(h, /Kontext, kein Beleg/);
  assert.match(h, /23 davon nie aufgelöst/);
});

test('das Urteil bei fehlenden Preisen nennt beim Namen, was fehlt', () => {
  const [, txt] = W._pwPubUrteil({ n: 11, wins: 10, hit: 0.9091, geldurteil: false, belegt: false,
                                   roiUg: null, roi: null });
  assert.match(txt, /kein Geldurteil möglich/);
});

// ── Leerstände lügen nicht ──────────────────────────────────────────────────
test('ohne gesendeten Push steht da, dass das Buch am Einführungstag beginnt', () => {
  const h = W._pwPublicPush({ gesamt: 0 });
  assert.match(h, /noch keinen gesendeten Push/);
  assert.match(h, /wäre kein Beleg, sondern eine Auswahl/);
});

test('eine fehlende Datei kippt den Block nicht', () => {
  assert.doesNotThrow(() => W._pwPublicPush(null));
  assert.doesNotThrow(() => W._pwPublicPush(undefined));
});

test('offene und unauflösbare Pushs senken den Nenner sichtbar', () => {
  const h = W._pwPublicPush(Object.assign({}, ECHT, { offen: 2, unaufloesbar: 4 }));
  assert.match(h, /2 noch offen/);
  assert.match(h, /4 unauflösbar/);
});

// ── Je Sportart ─────────────────────────────────────────────────────────────
test('die Sportart-Tabelle zeigt die Untergrenze als eigene Spalte', () => {
  const h = W._pwPubCats(ECHT.byCat);
  assert.match(h, /<th>UG<\/th>/);
  assert.match(h, /E-Sport/);
  assert.match(h, /ein ROI ohne Untergrenze ist ein Punktschätzer/);
});

test('ohne Kategorien gibt es keine leere Tabelle', () => {
  assert.strictEqual(W._pwPubCats({}), '');
  assert.strictEqual(W._pwPubCats(null), '');
});

// ── Der Block hängt in der Track-Ansicht ────────────────────────────────────
test('der Push-Block wird in der Track-Record-Ansicht gerendert', () => {
  assert.match(JS, /\+_pwPublicPush\(_pwCache && _pwCache\.publicRec\)/);
});

test('poly_public_record.json wird überhaupt geladen', () => {
  assert.match(JS, /jf\('poly_public_record\.json'\)/);
  assert.match(JS, /publicRec\]\)=>/);
});
