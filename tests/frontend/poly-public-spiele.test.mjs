// tests/frontend/poly-public-spiele.test.mjs — 09.09.2026
//
// Lucas: „was mir fehlt vor allem beim Public-Kandidaten ist, welche Spiele da überhaupt dabei
// sind. … und ich will auch immer kontrollieren, ob für die ‚Heute spielenswert' auch wirklich in
// Trades-Channel eine Push kommt."
//
// Der Block darüber zeigte seit Wochen n, Trefferquote, ROI und CLV — also wie gut die Auswahl
// war, aber nie WAS drin war. Eine Kennzahl ohne ihre Zeilen kann man nicht nachprüfen.
//
// ⭐ Die eigentliche Falle steckt in der Push-Spalte: „wir wissen es nicht" und „es wurde nicht
// gepusht" sind zwei verschiedene Aussagen. Ohne geladenes Push-Buch darf nie „kein Push"
// dastehen — das wäre eine Behauptung über etwas, das gar nicht nachgesehen wurde.
//
// 🔴 12.09.2026 (Plattform-Audit): diese Datei hat die Regel nur zur HÄLFTE festgehalten. Geprüft
// war „Datei fehlt ganz"; nicht geprüft war „Datei da, reicht aber nicht weit genug zurück". Und
// genau das war der reale Zustand: die Spalte las `shortlist_push_seen.json`, einen Dedup-Stand
// mit drei Tagen TTL, und schrieb für alles Ältere „kein Push" — 179 von 193 Zeilen falsch. Seit
// dem Fix liest sie `shortlist_push_ledger.json` und kennt drei Zustände statt zwei. Die neuen
// Fälle stehen in `poly-push-spalte.test.mjs`; hier wird die Ansicht drumherum nachgezogen.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

function laden(cache) {
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve(null) });
  w.eval(readFileSync(new URL('../../poly-wallets.js', import.meta.url), 'utf8'));
  w._pwTestSetCache(cache || {});
  return w;
}

const play = (over) => Object.assign({
  key: 'atp-tiafoe-michels-2026-09-08', side: 'Frances Tiafoe', league: 'TENNIS',
  verdict: 'BET', conv: 8, entryPrice: 0.72, public: true, result: 'win',
  firstTs: '2026-09-08T09:00:00Z',
}, over || {});

const track = (over) => Object.assign({
  open: {}, settled: [play()],
}, over || {});

// Zeilenform wie `push_shortlist_trades._buche_pushes` sie schreibt.
const PUSH = [{ k: 'atp-tiafoe-michels-2026-09-08|Frances Tiafoe',
                key: 'atp-tiafoe-michels-2026-09-08', side: 'Frances Tiafoe',
                conv: 8, sentAt: '2026-09-08T10:03:53Z', pushPreis: 0.72 }];
// Ein Buch, das den Play-Zeitraum abdeckt, ihn selbst aber nicht enthält — nur so ist
// „kein Push" eine Aussage und keine Gedächtnislücke.
const PUSH_ANDERES = [{ k: 'irgendwas-anderes|Y', key: 'irgendwas-anderes', side: 'Y',
                        conv: 7, sentAt: '2026-09-07T08:00:00Z', pushPreis: 0.5 }];

test('die Spiele der Public-Kandidaten stehen ausklappbar da', () => {
  const w = laden({ pushLed: PUSH });
  const h = w._pwPublicSpiele(track());
  assert.match(h, /Welche Spiele sind das/);
  assert.match(h, /atp-tiafoe-michels/);
  assert.match(h, /Frances Tiafoe/);
  assert.match(h, /<details/, 'zugeklappt — die Kennzahlen sind die Antwort, die Zeilen die Kontrolle');
});

test('gepushte Plays sind als solche erkennbar', () => {
  const w = laden({ pushLed: PUSH });
  assert.match(w._pwPublicSpiele(track()), /gepusht/);
});

test('⭐ ohne Push-Buch steht NICHT „kein Push"', () => {
  // Der teure Fehler: aus einer fehlenden Datei eine Aussage über den Channel machen.
  const w = laden({});
  const h = w._pwPublicSpiele(track());
  assert.doesNotMatch(h, /kein Push/,
    'ohne geladenes Buch ist unbekannt, ob gepusht wurde — das ist nicht „nicht gepusht"');
  assert.match(h, /—/);
});

test('ein Play ohne Push-Eintrag heißt „kein Push" — mit Erklärung warum das normal ist', () => {
  const w = laden({ pushLed: PUSH_ANDERES });
  const h = w._pwPublicSpiele(track());
  assert.match(h, /kein Push/);
  assert.match(h, /Deckel|92¢|Dedup/, 'der Tooltip muss den echten Grund nennen, nicht die seit '
                                    + '07.09. überholte „zwei verschiedene Tore"-Erklärung');
});

test('⭐ ein Play ÄLTER als das Buch heißt NICHT „kein Push"', () => {
  // Die zweite Hälfte derselben Regel, und der reale Fund vom 12.09.: ein Buch kann da sein und
  // trotzdem nichts über diesen Play wissen.
  const w = laden({ pushLed: PUSH_ANDERES });
  const h = w._pwPublicSpiele(track({ settled: [play({ firstTs: '2026-08-01T09:00:00Z' })] }));
  assert.doesNotMatch(h, /kein Push/,
    'das Buch beginnt am 07.09. — über den 01.08. kann es nichts sagen');
  assert.match(h, /vor dem Buch/);
});

test('offene und abgerechnete Kandidaten stehen beide drin', () => {
  const w = laden({ pushLed: PUSH });
  const h = w._pwPublicSpiele(track({
    open: { k1: play({ key: 'cs2-gl1-furia-2026-09-09', side: 'FURIA', result: null }) },
  }));
  assert.match(h, /1 offen/);
  assert.match(h, /FURIA/);
  assert.match(h, /läuft/, 'ein laufendes Spiel hat kein Ergebnis und behauptet auch keines');
});

test('nicht-öffentliche Plays gehören nicht in diese Liste', () => {
  const w = laden({ pushLed: PUSH });
  const h = w._pwPublicSpiele(track({ settled: [play({ public: false, side: 'Nicht Public' })] }));
  assert.strictEqual(h, '', 'ohne Public-Kandidaten gar kein Block statt eines leeren Rahmens');
});

test('der Kopf zählt, wie viele davon im Trades-Channel gelandet sind', () => {
  const w = laden({ pushLed: PUSH });
  const h = w._pwPublicSpiele(track({
    settled: [play(), play({ key: 'ohne-push', side: 'X' })],
  }));
  assert.match(h, /1 von 2 im Zeitraum des Push-Buchs/,
    'der Nenner darf nur zählen, was das Buch überhaupt beantworten kann');
});
