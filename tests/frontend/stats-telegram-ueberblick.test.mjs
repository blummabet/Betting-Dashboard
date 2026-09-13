/* 13.09.2026 (Lucas: „wär cool, wenn auf der Startseite noch ganz oben ein Block ist, der
 * Telegram komplett zusammenfasst … damit ich schau, ob das auch wirklich hinhaut")
 *
 * Und der Fund, der beim Pruefen dazukam: die drei Kacheln eines Push-Blocks haben DREI
 * verschiedene Nenner. Poly-Whales stand auf „69 Plays · 69,0 % Treffer · +24,6 % Rendite" —
 * die Quote kam aus 42 abgerechneten, die Rendite aus 31 mit Preis. Auf einem Screenshot liest
 * das jeder als 69 von 69.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const SRC = readFileSync(new URL('../../stats.js', import.meta.url), 'utf8');

function welt(data) {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="statsPanel"></div></body>',
    { url: 'https://x.test/', runScripts: 'outside-only' });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve(null) });
  w.eval(SRC);
  w._stData = data;
  return w;
}

const BLOCK = (id, label, kanal, n, ab, hit, roi) => ({
  id, label, emoji: '🎯', gruppe: 'Push-Kanäle', kanal,
  abdeckung: { von: '2026-09-01', bis: '2026-09-13' },
  reihen: [
    { periode: '2026-W37', art: 'woche', n, nAufgeloest: ab, treffer: Math.round(ab * hit / 100),
      hitPct: hit, hitUg: null, roi, roiUg: null, pl: 1.2, clv: null, mitQuote: ab,
      von: '2026-09-07', bis: '2026-09-13', vollstaendig: true },
    { periode: 'gesamt', art: 'gesamt', n, nAufgeloest: ab, treffer: Math.round(ab * hit / 100),
      hitPct: hit, hitUg: null, roi, roiUg: null, pl: 1.2, clv: null, mitQuote: ab,
      von: '2026-09-01', bis: '2026-09-13', vollstaendig: true },
  ],
});

const DATEN = {
  generatedAt: '2026-09-13T12:00:00Z', heute: '2026-09-13', ugMinN: 30,
  bloecke: [
    BLOCK('push-whale', 'Poly-Whales · Public-Channel', 'Public', 69, 42, 69.0, 24.6),
    BLOCK('push-killer', 'Konjunktion · Trades', 'Trades', 70, 64, 57.8, 2.8),
    { id: 'cards', label: 'Cards', emoji: '🎯', gruppe: 'Eigene Engine',
      abdeckung: { von: '2026-09-01', bis: '2026-09-13' },
      reihen: [{ periode: 'gesamt', art: 'gesamt', n: 10, nAufgeloest: 10, treffer: 6,
                 hitPct: 60, hitUg: null, roi: 5, roiUg: null, pl: 0.5, clv: null,
                 mitQuote: 10, von: '2026-09-01', bis: '2026-09-13', vollstaendig: true }],
    },
  ],
};

test('der Ueberblick listet jeden Push-Kanal — und nur die', () => {
  const w = welt(DATEN);
  const html = w._stTelegram(DATEN.bloecke);
  assert.match(html, /Poly-Whales/);
  assert.match(html, /Konjunktion/);
  assert.ok(!/>.{0,40}Cards</.test(html), 'die eigene Engine ist kein Telegram-Kanal');
});

test('jede Zeile sagt, in welchen Kanal sie geht', () => {
  const html = welt(DATEN)._stTelegram(DATEN.bloecke);
  assert.match(html, /Public/);
  assert.match(html, /Trades/);
});

test('der Nenner steht neben der Zahl, die er traegt', () => {
  const html = welt(DATEN)._stTelegram(DATEN.bloecke);
  // 69 Pushes, aber 42 abgerechnet — beide muessen dastehen
  assert.match(html, /69/);
  assert.match(html, /42/);
});

test('es gibt KEINE Gesamt-Rendite ueber alle Kanaele', () => {
  /* Die Kanaele rechnen mit verschiedenen Einsaetzen und Preisen (Whale $10 fix, Betfair zur
   * Quote in der Nachricht, Konjunktion zum Haltepreis). Ein Mittel darueber saehe ueberzeugend
   * aus und bedeutete nichts — genau die Sorte Zahl, die auf einem geposteten Screenshot
   * Schaden anrichtet. */
  const w = welt(DATEN);
  const html = w._stTelegram(DATEN.bloecke);
  const summe = html.slice(html.indexOf('Zusammen'));
  assert.ok(!/[+-]\d+[.,]\d%/.test(summe), 'in der Summenzeile steht eine Rendite');
  assert.match(summe, /139/, 'die Pushes werden sehr wohl summiert (69 + 70)');
});

test('die Summe zaehlt Pushes UND abgerechnete getrennt', () => {
  const html = welt(DATEN)._stTelegram(DATEN.bloecke);
  const summe = html.slice(html.indexOf('Zusammen'));
  assert.match(summe, /139/);          // 69 + 70 Pushes
  assert.match(summe, /106/);          // 42 + 64 abgerechnet
});

test('die Perioden-Wahl bietet nur an, was es wirklich gibt', () => {
  const w = welt(DATEN);
  w._stMode = 'woche';
  const html = w._stTelegram(DATEN.bloecke);
  assert.match(html, /W37/);
  assert.ok(!/W35/.test(html), 'eine Periode ohne Daten darf nicht angeboten werden');
});

test('der Block folgt der gewaehlten Periode', () => {
  const w = welt(DATEN);
  w._stMode = 'woche';
  w._stTgPeriode = '2026-W37';
  assert.match(w._stTelegram(DATEN.bloecke), /2026-W37/);
});

test('die Kachel nennt den Nenner der Trefferquote', () => {
  const w = welt(DATEN);
  w._stPost = false;
  const html = w._stBlock(DATEN.bloecke[0]);
  assert.match(html, /aus 42 abgerechneten/);
});

test('bei vollstaendig abgerechneten Bloecken steht kein ueberfluessiger Nenner', () => {
  const w = welt(DATEN);
  const html = w._stBlock(DATEN.bloecke[2]);
  assert.ok(!/aus 10 abgerechneten/.test(html),
    'wenn alle abgerechnet sind, ist der Nenner keine Information, sondern Rauschen');
});
