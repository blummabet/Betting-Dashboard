// tests/frontend/cockpit-positionsstand.test.mjs — 18.09.2026
//
// Lucas: „Schalke – Elversberg ist aber noch offen / Brentford Chelsea auch".
//
// Bei der Aufarbeitung fiel eine zweite Sache auf, die zu meiner eigenen Fehldiagnose vom 16.09.
// gefuehrt hatte: `liga_poly_balance.json` meldete $10,12 an Positionen — ueber fuenf Laeufe und
// zwei Tage exakt denselben Betrag, waehrend die Kurse liefen. Der Positions-Fetch faellt bei
// einem API-Fehler auf den alten Wert zurueck, und die Kachel zeigte ihn wie eine frische Zahl.
//
// Der Produzent schreibt jetzt `positionsStand`. Diese Datei prueft nur, dass die Flaeche ihn
// ZEIGT — und die Schwelle nicht selbst nachbaut, sondern den Stand nennt.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const SRC = readFileSync(new URL('../../polymarket-tab.js', import.meta.url), 'utf8');
const RAW = readFileSync(new URL('../../raw-json.js', import.meta.url), 'utf8');

function laden() {
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: false });
  w.eval(RAW);
  w.eval(SRC);
  return w;
}

const vorStunden = (h) => new Date(Date.now() - h * 3600000).toISOString();

function cockpit(w, bal) {
  return w.renderTradingCockpit({
    placed: { bets: [] }, balance: bal, kill: {}, poly: { allFixtures: [] }, data: {},
  });
}

test('ein eingefrorener Positionswert wird als alt ausgewiesen', () => {
  const w = laden();
  const html = cockpit(w, { usdc: 184.85, positions: 9.28, total: 194.13,
                            positionsStand: vorStunden(40) });
  assert.match(html, /Positionswert vor 40 h gemessen/,
    'ohne diesen Hinweis liest sich ein Wert aus vorgestern wie der von jetzt');
});

test('ein frischer Stand wird nicht kommentiert', () => {
  const w = laden();
  const html = cockpit(w, { usdc: 184.85, positions: 9.28, total: 194.13,
                            positionsStand: vorStunden(0.2) });
  assert.ok(!/Positionswert vor/.test(html));
  assert.match(html, /\$9\.28 in Pos\./);
});

test('fehlt das Feld, wird nichts behauptet', () => {
  // Altbestand: Dateien ohne `positionsStand` duerfen nicht als „frisch" durchgehen und auch
  // nicht als „alt" — die Flaeche weiss es schlicht nicht. Den Fund macht der Guard.
  const w = laden();
  const html = cockpit(w, { usdc: 184.85, positions: 9.28, total: 194.13 });
  assert.ok(!/Positionswert vor/.test(html));
});
