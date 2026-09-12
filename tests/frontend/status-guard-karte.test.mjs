// tests/frontend/status-guard-karte.test.mjs — 12.09.2026 (Plattform-Audit, Block B)
//
// 🔴 `uebersicht_integrity.py` laeuft bei jedem Liga- und MLS-Update, prueft 19
// Ausgabe-Eigenschaften der Uebersicht und wird committet. Gelesen hat das Ergebnis **keine
// einzige Frontend-Datei**. Beim Fund standen drei Checks auf rot, zwei davon mit Schweregrad
// `error`, und einer war erst an diesem Vormittag dazugekommen:
//
//   · Stake-Spielklasse: 1 Fussball-Liga ohne Eintrag — faellt aus jeder Zeile der Ansicht
//   · Poly-Deckung: 2 Maerkte, die der Liga-Fetcher hat und der Money-Scan nie
//   · Stumme Signale: 3 Signale ohne eine einzige Feuerung
//
// Dieselbe Fehlerklasse wie beim Pick-Validator: ein Waechter, der laeuft und ins Leere meldet.
// Diese Tests halten die Regel fest, an der alles haengt: **ein alter oder fehlender Stand darf
// nie wie „nichts gefunden" aussehen.**
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const ROOT = new URL('../../', import.meta.url);
const JS = readFileSync(new URL('status-checks.js', ROOT), 'utf8');

function fenster() {
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'https://x.com/', runScripts: 'outside-only' });
  dom.window.fetch = () => Promise.resolve({ ok: false, json: () => Promise.resolve(null) });
  dom.window.eval(JS);
  return dom.window;
}
const W = fenster();
const ROT = '#f85149';

const stempel = (hAlt) => new Date(Date.now() - hAlt * 3600000).toISOString();
const check = (ok, sev, label, failures = []) => ({ ok, severity: sev, label, failures, nFail: failures.length });
const gi = (checks, hAlt = 1) => ({ generatedAt: stempel(hAlt), nFail: checks.filter(c => !c.ok).length, checks });

test('⭐ fehlende Datei ist ROT und sagt, dass das kein „keine Befunde" ist', () => {
  const k = W._stGuardKarte(null);
  assert.strictEqual(k.col, ROT);
  assert.match(k.html, /<b>nicht<\/b>/);
});

test('⭐ alter Stand ist ROT — die Batterie laeuft bei jedem Update', () => {
  const k = W._stGuardKarte(gi([check(true, 'error', 'X')], 24 * 5));
  assert.strictEqual(k.col, ROT);
  assert.match(k.html, /laeuft nicht/);
  assert.doesNotMatch(k.html, /✅/, 'eine tote Batterie darf kein Haekchen zeigen');
});

test('ein error-Check faerbt rot, ein warn-Check nur gelb', () => {
  const rot = W._stGuardKarte(gi([check(false, 'error', 'Poly-Deckung', ['x']), check(true, 'warn', 'Y')]));
  assert.strictEqual(rot.col, ROT);
  const gelb = W._stGuardKarte(gi([check(false, 'warn', 'Stumme Signale', ['x']), check(true, 'error', 'Y')]));
  assert.notStrictEqual(gelb.col, ROT);
  assert.match(gelb.html, /Warnung/);
});

test('alles gruen bleibt gruen — und nennt die Zahl der Checks', () => {
  const k = W._stGuardKarte(gi([check(true, 'error', 'A'), check(true, 'warn', 'B')]));
  assert.notStrictEqual(k.col, ROT);
  assert.match(k.html, /alle 2 Checks gruen/);
});

test('die Befunde stehen mit Text da, Fehler vor Warnungen', () => {
  const k = W._stGuardKarte(gi([
    check(false, 'warn', 'Stumme Signale', ['polymarket_sharp: 0 Feuerungen']),
    check(false, 'error', 'Poly-Deckung', ['sea-gen-fro: der Liga-Fetcher hat den Markt, der Money-Scan nie']),
  ]));
  assert.match(k.html, /Poly-Deckung/);
  assert.match(k.html, /Money-Scan nie/);
  assert.ok(k.html.indexOf('Poly-Deckung') < k.html.indexOf('Stumme Signale'),
    'ein error gehoert ueber eine Warnung');
});

test('lange Befundlisten werden gekappt, aber die Zahl bleibt sichtbar', () => {
  const viele = ['a', 'b', 'c', 'd', 'e'];
  const k = W._stGuardKarte(gi([check(false, 'error', 'Viele', viele)]));
  assert.match(k.html, /2 weitere/, 'der Rest darf nicht still verschwinden');
});

test('Gegenprobe: Befundtext wird escaped', () => {
  const k = W._stGuardKarte(gi([check(false, 'error', '<script>x</script>', ['<img src=x>'])]));
  assert.doesNotMatch(k.html, /<script>/);
  assert.doesNotMatch(k.html, /<img /);
});

// ── Die Karte muss auch wirklich auf der Seite stehen und ins Urteil eingehen ────────────────
async function uebersicht(gInput) {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="statusPage"></div></body>',
    { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: false, json: () => Promise.resolve(null) });
  w.eval(JS);
  let gerendert = '';
  w._stDynEl = () => ({ set innerHTML(v) { gerendert = v; }, get innerHTML() { return gerendert; } });
  w._stGet = async (f) => (f === 'uebersicht_integrity.json' ? gInput : null);
  w._stFreshGrid = async () => '';
  w._stThresholdsCard = () => '';
  await w._stRenderOverview();
  return gerendert;
}

test('⭐ die Guard-Karte steht auf der Seite und faerbt das Urteil oben mit', async () => {
  const html = await uebersicht(gi([check(false, 'error', 'Poly-Deckung', ['fehlender Markt'])]));
  const trenn = html.indexOf('🧭');
  assert.ok(trenn > 0, 'die Guard-Karte wird gar nicht gerendert');
  assert.match(html, /Poly-Deckung/);
  const kopf = html.slice(0, trenn);
  assert.match(kopf, /Guard-Batterie/,
    'sonst steht oben gruen, waehrend unten rot steht');
  assert.ok(kopf.includes(ROT));
});

test('⭐ zwei rote Waechter loeschen sich nicht gegenseitig aus dem Urteil', async () => {
  // Beim Bauen des zweiten Waechters passiert: als zwei if-Bloecke hat der spaetere die Meldung
  // des frueheren ueberschrieben. Oben stand dann nur noch einer von zweien.
  const dom = new JSDOM('<!DOCTYPE html><body><div id="statusPage"></div></body>',
    { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: false, json: () => Promise.resolve(null) });
  w.eval(JS);
  let gerendert = '';
  w._stDynEl = () => ({ set innerHTML(v) { gerendert = v; }, get innerHTML() { return gerendert; } });
  w._stGet = async () => null;          // BEIDE Waechter ohne Ergebnis -> beide rot
  w._stFreshGrid = async () => '';
  w._stThresholdsCard = () => '';
  await w._stRenderOverview();
  const kopf = gerendert.slice(0, gerendert.indexOf('🧭'));
  assert.match(kopf, /Guard-Batterie/, 'die Guard-Batterie fehlt im Urteil');
  assert.match(kopf, /Pick-Validator/, 'der Pick-Validator fehlt im Urteil');
});
