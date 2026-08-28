// tests/frontend/verdict-flip-badge.test.mjs — 28.08.2026 (Lucas, Barcelona–Athletic)
// Der Über-2.5-Pick war morgens NOBET und stand 14 Minuten vor Anpfiff wieder auf ABWÄGEN.
// Logik bleibt (Aufstellung T-1h soll wirken dürfen) — aber es muss dranstehen.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';

const ROOT = new URL('../../', import.meta.url);
const SRC = readFileSync(new URL('wm2026-renderer.js', ROOT), 'utf8');

function loadBadge() {
  const m = SRC.match(/function _verdictFlipBadge\(p\) \{[\s\S]*?\n  \}/);
  assert.ok(m, '_verdictFlipBadge nicht gefunden');
  // eslint-disable-next-line no-new-func
  return new Function(m[0].replace(/^  /, '') + '; return _verdictFlipBadge;')();
}
const badge = loadBadge();

test('ohne Wechsel kein Badge — kein Lärm auf stabilen Picks', () => {
  assert.equal(badge({ market: 'X' }), '');
  assert.equal(badge({ market: 'X', verdictFlips: [] }), '');
  assert.equal(badge(null), '');
  assert.equal(badge({ market: 'X', verdictFlips: 'kaputt' }), '');
});

test('der echte Fall wird benannt: NOBET → ABWÄGEN', () => {
  const h = badge({ market: 'Über 2.5 Tore', verdictFlips: [
    { ts: '2026-08-27T18:46:00+00:00', von: 'NOBET', auf: 'ABWÄGEN' }] });
  assert.match(h, /NOBET/);
  assert.match(h, /ABWÄGEN/);
  assert.match(h, /↻/);
});

test('bei mehreren Wechseln zeigt das Badge den letzten, der Tooltip alle', () => {
  const h = badge({ market: 'X', verdictFlips: [
    { ts: '2026-08-27T06:49:00+00:00', von: 'ABWÄGEN', auf: 'NOBET' },
    { ts: '2026-08-27T18:46:00+00:00', von: 'NOBET', auf: 'ABWÄGEN' }] });
  assert.match(h, /↻ NOBET→ABWÄGEN/, 'sichtbar ist der letzte Wechsel');
  assert.match(h, /title="[^"]*ABWÄGEN → NOBET[^"]*NOBET → ABWÄGEN/, 'Tooltip hat den ganzen Verlauf');
});

test('kaputter Zeitstempel kippt das Badge nicht', () => {
  const h = badge({ market: 'X', verdictFlips: [{ ts: 'kaputt', von: 'BET', auf: 'NOBET' }] });
  assert.match(h, /BET→NOBET/);
  assert.doesNotMatch(h, /NaN|Invalid/);
});

test('Anführungszeichen im Tooltip werden entschärft (kein Attribut-Ausbruch)', () => {
  const h = badge({ market: 'X', verdictFlips: [{ ts: 'x', von: 'A"B', auf: 'C' }] });
  const title = h.match(/title="([^"]*)"/);
  assert.ok(title, 'title-Attribut bleibt intakt');
  assert.doesNotMatch(title[1], /"/);
});

test('Badge hängt an beiden Render-Stellen (Hero und Nebenpicks)', () => {
  // Fehlt es an einer, sieht man den Wechsel je nach Pick-Rang mal ja, mal nein.
  const treffer = SRC.match(/_verdictFlipBadge\(/g) || [];
  assert.ok(treffer.length >= 3, `nur ${treffer.length} Vorkommen — eine Render-Stelle vergessen?`);
});
