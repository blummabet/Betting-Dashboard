// 29.09.2026 (Lucas' Übersicht-Check): „🏀 Atlanta Braves" bei den Top-5 Live-Whales. Derselbe Fall
// wie am 02.09. („MLB bekam 🏀") — damals in _pwSportIcon behoben, aber die Übersicht hatte eine
// eigene Kopie (_mdSportIco), die direkt über die Kategorie US-Sport → 🏀 ging.
// Dazu: der Countdown liest den absoluten Anpfiff (koTs), nicht capturedAt+hoursToKickoff.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const PW = new URL('../../poly-wallets.js', import.meta.url);
const MD = new URL('../../main-dashboard.js', import.meta.url);
function load() {
  const dom = new JSDOM('<!DOCTYPE html><body></body>',
    { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  dom.window.fetch = () => Promise.resolve({ ok: false, json: () => Promise.resolve(null) });
  dom.window.eval(readFileSync(PW, 'utf8'));
  return dom.window;
}

test('MLB mit gestempelter Kategorie US-Sport bekommt ⚾, nicht 🏀', () => {
  const w = load();
  assert.strictEqual(w.eval("_pwSportIcon('MLB', 'US-Sport')"), '⚾');
  assert.strictEqual(w.eval("_pwSportIcon('NBA', 'US-Sport')"), '🏀');
  assert.strictEqual(w.eval("_pwSportIcon('Serie A')"), '⚽');
});

test('Gegentest: die Übersicht baut die Icon-Logik nicht nach', () => {
  const src = readFileSync(MD, 'utf8');
  assert.ok(!src.includes('_PW_CAT_ICON[_pwSportCategory('),
    'main-dashboard.js leitet das Zeilen-Icon wieder selbst aus der Kategorie ab — so kam 🏀 für MLB zurück');
  assert.ok(src.includes('_pwSportIcon(lg, sp)'));
});

test('Anpfiff aus koTs schlägt capturedAt + hoursToKickoff', () => {
  const w = load();
  const ko = new Date(Date.now() + 9 * 60000).toISOString();
  // alter Weg: Stempel 5 Min nach der Messung -> 5 Min zu spät
  const cap = new Date(Date.now() - 13 * 60000).toISOString();
  const m = { hoursToKickoff: 27 / 60, capturedAt: cap, koTs: ko };
  const h = w.eval('_pwRealHtk(' + JSON.stringify(m) + ')');
  assert.ok(Math.abs(h * 60 - 9) < 0.5, 'erwartet ~9 Min, bekam ' + (h * 60).toFixed(1));
  delete m.koTs;
  const alt = w.eval('_pwRealHtk(' + JSON.stringify(m) + ')');
  assert.ok(alt * 60 > 13, 'ohne koTs bleibt der alte (versetzte) Wert — Rückfall');
});
