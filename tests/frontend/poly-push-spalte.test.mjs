// tests/frontend/poly-push-spalte.test.mjs — 12.09.2026 (Plattform-Audit)
//
// 🔴 Der Fund: die Push-Spalte im Public-Kandidaten-Aufklapper las `shortlist_push_seen.json` und
// schrieb bei jedem Fehltreffer „kein Push". Diese Datei ist aber ein DEDUP-Stand mit drei Tagen
// TTL (`SEEN_TTL_DAYS = 3`) und stand beim Fund auf 23 Zeilen — alles Aeltere bekam ein
// definitives Negativ aus einer Quelle, die es nicht wissen kann. 179 von 193 Zeilen sagten
// faelschlich „kein Push".
//
// Fehlerklasse, nicht Instanz: **fehlende Information darf nicht als harmloser Default rendern.**
// Der Fix gibt der Spalte einen dritten Zustand, und diese Tests halten alle drei fest — inklusive
// der Gegenprobe, dass „kein Push" NICHT verschwindet, wo es wirklich stimmt. Ein Waechter, der
// nur die neue Freundlichkeit prueft, wuerde eine Spalte durchlassen, die nie mehr Nein sagt.
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

// Zeilenform wie sie push_shortlist_trades._buche_pushes schreibt.
const BUCH = [
  { k: 'nba-lal-2026-09-10|Lakers', key: 'nba-lal-2026-09-10', side: 'Lakers',
    sentAt: '2026-09-10T18:02:11Z', conv: 7, pushPreis: 0.61, league: 'NBA' },
  { k: 'epl-ars-2026-09-11|Arsenal', key: 'epl-ars-2026-09-11', side: 'Arsenal',
    sentAt: '2026-09-11T12:40:00Z', conv: 6, pushPreis: 0.48, league: 'EPL' },
];
function mitBuch(led) { W._pwCache = { pushLed: led }; }

test('gepusht: steht im Buch → ✅ mit Zeitpunkt und Push-Preis', () => {
  mitBuch(BUCH);
  const p = W._pwPushInfo({ key: 'nba-lal-2026-09-10', side: 'Lakers',
                            firstTs: '2026-09-10T17:00:00Z' });
  assert.match(p.txt, /gepusht/);
  assert.match(p.tip, /2026-09-10/);
  assert.match(p.tip, /61¢/, 'der Push-Preis gehoert in den Tooltip — er ist der Preis, den ein '
                           + 'Leser in dem Moment bekommen haette');
});

test('kein Push: liegt IM Zeitraum des Buchs und fehlt → echtes Nein', () => {
  mitBuch(BUCH);
  const p = W._pwPushInfo({ key: 'seriea-int-2026-09-11', side: 'Inter',
                            firstTs: '2026-09-11T09:00:00Z' });
  assert.strictEqual(p.txt, 'kein Push');
});

test('vor dem Buch: aelter als die aelteste Buchzeile → unbekannt, nicht Nein', () => {
  mitBuch(BUCH);
  const p = W._pwPushInfo({ key: 'bl-bvb-2026-08-20', side: 'Dortmund',
                            firstTs: '2026-08-20T15:00:00Z' });
  assert.strictEqual(p.txt, 'vor dem Buch',
    'Der urspruengliche Fehler: genau diese Zeile stand auf „kein Push".');
  assert.match(p.tip, /Luecke im Ged/);
});

test('kein Buch geladen: „—", nicht „kein Push"', () => {
  mitBuch(null);
  assert.strictEqual(W._pwPushInfo({ key: 'x', side: 'y' }).txt, '—');
  mitBuch([]);
  assert.strictEqual(W._pwPushInfo({ key: 'x', side: 'y' }).txt, '—',
    'Ein leeres Buch ist kein Beleg fuer ausgebliebene Pushs.');
});

test('Gegenprobe: das TTL-Dedup-Buch wird nirgends mehr als Push-Beleg gelesen', () => {
  assert.ok(!/_pwCache\s*&&\s*_pwCache\.pushSeen/.test(JS),
    'shortlist_push_seen.json ist ein Dedup-Stand mit 3 Tagen TTL — als Quelle fuer '
  + '„wurde gepusht?" ist sie strukturell ungeeignet.');
  assert.ok(/shortlist_push_ledger\.json/.test(JS), 'das echte Push-Buch wird nicht geladen');
});

test('Gegenprobe: ohne Zeitstempel am Play wird NICHT auf „vor dem Buch" geraten', () => {
  mitBuch(BUCH);
  const p = W._pwPushInfo({ key: 'ohne-ts', side: 'Team' });
  assert.strictEqual(p.txt, 'kein Push',
    'Ohne eigenen Zeitstempel ist „vor dem Buch" eine Vermutung. Dann lieber die Aussage, die '
  + 'das Buch fuer seinen Zeitraum wirklich tragen kann.');
});
