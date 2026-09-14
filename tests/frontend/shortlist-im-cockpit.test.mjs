// tests/frontend/shortlist-im-cockpit.test.mjs
//
// 14.09.2026 (Lucas: „wo zeigen wir die Bets an die automatisch gemacht werden … wuerde fast
// polymarket trading sagen weil dort sollte ja auch automatisch getraded werden").
//
// Genau so ist es gebaut: der „Heute spielenswert"-Auto-Play erscheint im TRADING-Cockpit,
// nicht auf der Betting-Seite. Die Betting-Seite ist bewusst das MANUELLE Interface — sie
// filtert Auto-Quellen heraus. Diese Tests halten beide Haelften fest, denn die zweite ist
// die stille: eine neue Auto-Quelle, die dort nicht erkannt wird, laeuft als „manuelle
// Wette" mit und verfaelscht die Bilanz, ohne dass irgendwo ein Fehler erscheint.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';

const CODE = readFileSync(new URL('../../polymarket-tab.js', import.meta.url), 'utf8');

test('das Cockpit laedt das Wett-Buch des Auto-Plays', () => {
  assert.match(CODE, /jf\('shortlist_auto_bets_placed\.json'\)/,
    'ohne diese Zeile taucht keine einzige automatische Shortlist-Wette im Trading-Tab auf');
});

test('der Auto-Play ist KEIN vierter Datensatz', () => {
  // Ein Eintrag in POLY_DATASETS wuerde vier Dateien suchen, die es nie geben wird
  // (Fixtures, Balance, Kill-Switch, Prices) — der Auto-Play hat nur ein Wett-Buch.
  const m = CODE.match(/const POLY_DATASETS\s*=\s*\[([^\]]*)\]/);
  assert.ok(m, 'POLY_DATASETS nicht gefunden');
  assert.ok(!/shortlist/.test(m[1]), 'shortlist gehoert nicht in POLY_DATASETS');
});

test('⭐ jede auto_*-Quelle gilt auf der Betting-Seite als Auto — auch die naechste', () => {
  // Die Aufzaehlung (`=== 'auto' || === 'auto_steam'`) war der Fehler: auto_shortlist waere
  // als dritte Variante still als manuelle Wette in die Betting-Statistik gelaufen.
  const m = CODE.match(/const _isAutoSrc\s*=\s*b\s*=>\s*([^;]+);/);
  assert.ok(m, '_isAutoSrc nicht gefunden');
  assert.match(m[1], /startsWith\('auto'\)/,
    'eine Liste vergisst die naechste Auto-Quelle — Praefix-Pruefung, wie in telegram_trades.is_auto_source');
  const _isAutoSrc = new Function('b', `return ${m[1]};`);
  for (const src of ['auto', 'auto_steam', 'auto_shortlist']) {
    assert.strictEqual(_isAutoSrc({ source: src }), true, `${src} muss als Auto gelten`);
  }
  assert.strictEqual(_isAutoSrc({ source: 'manual' }), false);
  assert.strictEqual(_isAutoSrc({}), true, 'ohne Quelle gilt weiter der Default auto');
});

test('die Positions-Tabelle sagt, WELCHES System die Position aufgemacht hat', () => {
  assert.match(CODE, /_istShortlist\(b\)\s*\n?\s*\?\s*`<span title="Heute spielenswert/,
    'zwei Systeme auf einer Wallet — ohne Kennzeichen ist die Zeile nicht zuzuordnen');
  assert.match(CODE, /const quelle = /);
});

test('der Poly-Link einer Shortlist-Position zeigt nicht auf den WM-Pfad', () => {
  // Shortlist-Slugs sind Events (E-Sport, Tennis, alle Ligen) — /sports/fifa-world-cup/
  // haette bei JEDER dieser Zeilen ins Leere gefuehrt.
  assert.match(CODE, /_istShortlist\(b\)\s*\?\s*`https:\/\/polymarket\.com\/event\/\$\{slug\}`/);
});

test('⭐ die Exposure-Leiste behauptet keine gemeinsame Zahl fuer zwei Deckel', () => {
  // Pinnacle stoppt bei $80, der Auto-Play bei $100, beide zaehlen denselben Topf. Eine
  // Leiste gegen „80" waere bei $95 offener Exposure schlicht falsch.
  assert.match(CODE, /const SHORTLIST_MAX_OPEN = 100;/);
  assert.match(CODE, /max: Math\.max\(MAX_OPEN_EXP, SHORTLIST_MAX_OPEN\)/);
  assert.match(CODE, /🤖 Pinnacle \$\{?/, 'die Aufteilung muss dranstehen');
  assert.match(CODE, /Stopp \$\$\{MAX_OPEN_EXP\}/);
});

test('die Aufteilung rechnet Pinnacle als Rest, nicht als zweite Liste', () => {
  // Zwei unabhaengige Filter wuerden bei einer unbekannten Quelle beide danebengreifen und
  // die Summe waere kleiner als die Exposure. Rest = Gesamt − Shortlist kann nicht driften.
  assert.match(CODE, /const expPinnacle\s*=\s*openExposure - expShortlist;/);
});
