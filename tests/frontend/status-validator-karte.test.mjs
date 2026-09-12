// tests/frontend/status-validator-karte.test.mjs — 12.09.2026 (Plattform-Audit)
//
// Der Pick-Validator (`check_picks_logic.py`) hatte sein Ergebnis viereinhalb Monate ins Leere
// geschrieben: der Banner in ui.js stand auf `const vs = null`, die Summary war in keiner
// git-add-Zeile, und der Lauf starb seit dem 26.04.2026 an jeder Partie ohne H2H-Schnitt. Die
// committete Datei sagte „46 geprueft, 3 Fehler" — echt sind 107 Spiele mit 26 Fehlern.
//
// Jetzt sitzt der Befund in der Status-Uebersicht. Diese Tests halten die eine Regel fest, an der
// alles haengt: **ein alter oder fehlender Stand darf nie wie „nichts gefunden" aussehen.** Der
// Rest (Zaehlen, Gruppieren) ist Komfort; das hier ist der Grund.
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
const ROT = '#f85149', GELB = '#e3b341';

const stempel = (stundenAlt) => {
  const d = new Date(Date.now() - stundenAlt * 3600000);
  const z = (n) => String(n).padStart(2, '0');
  // Format wie check_picks_logic es schreibt: "%d.%m.%Y %H:%M", in UTC gelesen.
  return `${z(d.getUTCDate())}.${z(d.getUTCMonth() + 1)}.${d.getUTCFullYear()} ${z(d.getUTCHours())}:${z(d.getUTCMinutes())}`;
};
const summary = (over) => Object.assign({
  timestamp: stempel(1), checked: 107, errors: 0, warnings: 0, infos: 244, issues: [],
}, over || {});

test('⭐ fehlende Datei ist ROT und sagt ausdruecklich, dass das kein „keine Fehler" ist', () => {
  const k = W._stValidatorKarte(null);
  assert.strictEqual(k.col, ROT);
  assert.match(k.html, /nicht.*„keine Fehler gefunden"|<b>nicht<\/b>/);
});

test('⭐ alter Stand ist ROT — genau der Zustand seit 26.04.2026', () => {
  const k = W._stValidatorKarte(summary({ timestamp: stempel(24 * 137), checked: 46, errors: 3 }));
  assert.strictEqual(k.col, ROT);
  assert.match(k.html, /liefert nicht/);
  assert.doesNotMatch(k.html, /✅/, 'ein toter Validator darf nirgends ein Haekchen zeigen');
});

test('unlesbarer Zeitstempel ist ROT, nicht gruen', () => {
  const k = W._stValidatorKarte(summary({ timestamp: 'gestern irgendwann' }));
  assert.strictEqual(k.col, ROT);
  assert.match(k.html, /Stand unbekannt/);
});

test('frisch und sauber ist gruen', () => {
  const k = W._stValidatorKarte(summary());
  assert.notStrictEqual(k.col, ROT);
  assert.match(k.html, /107 Spiele geprueft/);
});

test('Fehler faerben rot und werden nach Code gruppiert, nicht Zeile fuer Zeile', () => {
  const issues = [];
  for (let i = 0; i < 26; i++) {
    issues.push({ severity: 'ERROR', code: 'PRESSURE_MUSTWINFLAG_MISMATCH', home: 'Wolfsberger AC',
                  away: 'Rapid Vienna', msg: 'pressureRatio=0.85 > 0.65 aber mustWin=False.' });
  }
  issues.push({ severity: 'WARN', code: 'CARDS35_LOW_FV', home: 'A', away: 'B', msg: 'FV zu niedrig' });
  const k = W._stValidatorKarte(summary({ errors: 26, warnings: 1, issues }));
  assert.strictEqual(k.col, ROT);
  assert.match(k.html, /26×/, '26 gleiche Befunde sind EIN Problem, keine 26 Zeilen');
  assert.match(k.html, /PRESSURE_MUSTWINFLAG_MISMATCH/);
  assert.match(k.html, /CARDS35_LOW_FV/);
  const zeilen = (k.html.match(/<tr>/g) || []).length;
  assert.strictEqual(zeilen, 2, `gruppiert waeren es 2 Zeilen, gerendert wurden ${zeilen}`);
});

test('Hinweise (INFO) blaehen die Liste nicht auf', () => {
  const issues = Array.from({ length: 50 }, () => ({ severity: 'INFO', code: 'LOW_SCORING_PROFILE', msg: 'x' }));
  const k = W._stValidatorKarte(summary({ infos: 50, issues }));
  assert.doesNotMatch(k.html, /LOW_SCORING_PROFILE/);
  assert.notStrictEqual(k.col, ROT);
});

test('Gegenprobe: Meldungstext wird escaped, eine Karte darf nicht zerbrechen', () => {
  const k = W._stValidatorKarte(summary({ errors: 1, issues: [
    { severity: 'ERROR', code: 'X<script>', home: 'A', away: 'B', msg: '<img src=x onerror=1>' }] }));
  assert.doesNotMatch(k.html, /<script>/);
  assert.doesNotMatch(k.html, /<img /);
  assert.match(k.html, /&lt;/);
});

// ⭐ Der wichtigste Test der Datei, und bewusst NICHT als Textsuche im Quelltext: ein
// `assert.match(JS, /val.col === _ST_R/)` bleibt gruen, wenn jemand `if (false && …)` davor
// schreibt. Beim Bauen dieser Datei ist mir genau das passiert — die Mutation lief durch.
// Also die Uebersicht wirklich rendern und nachsehen, was oben steht.
async function uebersicht(vs) {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="statusPage"></div></body>',
    { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: false, json: () => Promise.resolve(null) });
  w.eval(JS);
  let gerendert = '';
  // Funktions-Deklarationen liegen im globalen Scope — ueberschreibbar, und der Rest des
  // Moduls sieht die Ersatzfassung.
  w._stDynEl = () => ({ set innerHTML(v) { gerendert = v; }, get innerHTML() { return gerendert; } });
  w._stGet = async (f) => (f === 'validator_summary.json' ? vs : null);
  w._stFreshGrid = async () => '';
  w._stThresholdsCard = () => '';
  await w._stRenderOverview();
  return gerendert;
}

test('⭐ ein roter Validator faerbt das Urteil OBEN mit', async () => {
  // Sonst steht der Banner auf gruen und die Karte darunter auf rot — ein Widerspruch auf einem
  // Board ist schlimmer als beide Zustaende einzeln.
  const html = await uebersicht(summary({ errors: 26, issues: [
    { severity: 'ERROR', code: 'PRESSURE_MUSTWINFLAG_MISMATCH', home: 'A', away: 'B', msg: 'x' }] }));
  // Erst: steht die Karte ueberhaupt auf der Seite? `indexOf` auf -1 laufen zu lassen und dann
  // weiterzuschneiden wuerde ein fehlendes Rendern gruen durchgehen lassen.
  const trenn = html.indexOf('🐕');
  assert.ok(trenn > 0, 'die Validator-Karte wird gar nicht gerendert');
  assert.match(html, /PRESSURE_MUSTWINFLAG_MISMATCH/, 'der Befund steht nicht auf der Seite');
  const kopf = html.slice(0, trenn);   // alles vor der Validator-Karte
  assert.match(kopf, /Pick-Validator/,
    'Das Urteil oben erwaehnt den Validator nicht — dann steht dort gruen, waehrend unten rot steht.');
  assert.ok(kopf.includes(ROT), 'das Urteil oben ist nicht rot eingefaerbt');
});

test('⭐ ein toter Validator faerbt das Urteil ebenfalls', async () => {
  const html = await uebersicht(null);
  const trenn = html.indexOf('🐕');
  assert.ok(trenn > 0, 'die Validator-Karte wird gar nicht gerendert');
  const kopf = html.slice(0, trenn);
  assert.ok(kopf.includes(ROT),
    'Kein Ergebnis ist kein gruener Zustand — genau so sah der 26.04. viereinhalb Monate lang aus.');
});

test('frischer sauberer Validator laesst ein gruenes Urteil gruen', async () => {
  const html = await uebersicht(summary());
  const trenn = html.indexOf('🐕');
  assert.ok(trenn > 0, 'die Validator-Karte wird gar nicht gerendert');
  const kopf = html.slice(0, trenn);
  assert.doesNotMatch(kopf, /Pick-Validator meldet Fehler|Pick-Validator mit Warnungen/);
});
