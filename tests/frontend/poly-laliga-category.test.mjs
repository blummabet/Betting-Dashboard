// tests/frontend/poly-laliga-category.test.mjs — 03.08.2026 (Lucas: „Poly hat nun La Liga"): die
// Top-5-Fußball-Ligen werden in BEIDEN Sport-Klassifikatoren als Fußball erkannt (nicht „Sonstige"),
// damit La-Liga-Poly-Märkte in den Money/Whale-Views korrekt unter ⚽ Fußball erscheinen.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const PW = new URL('../../poly-wallets.js', import.meta.url);
function boot() {
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window; w.eval(readFileSync(PW, 'utf8')); return w;
}

test('_pwCatOf: La Liga & die anderen Top-Ligen → Fußball ⚽ (Regex-Fallback)', () => {
  const w = boot();
  for (const lg of ['laliga', 'LALIGA', 'bundesliga', 'serie', 'ligue', 'epl', 'soccer', 'lal-ala-get-2026-08-15', 'LAL']) {
    assert.deepEqual(w._pwCatOf(lg), ['Fußball', '⚽'], lg + ' → Fußball');
  }
});

test('_pwCatOf: bekannte exakte Keys bleiben unverändert; Politik bleibt Sonstige', () => {
  const w = boot();
  assert.deepEqual(w._pwCatOf('lol'), ['E-Sport', '🎮']);
  assert.deepEqual(w._pwCatOf('nba'), ['US-Sport', '🇺🇸']);
  assert.equal(w._pwCatOf('greater-manchester')[0], 'Sonstige');
});

test('_pwSportCategory kennt laliga (Sport-Filter greift)', () => {
  const w = boot();
  assert.equal(w._pwSportCategory('laliga-rma-bar-2026-08-16'), 'Fußball');
  assert.equal(w._pwSportPass ? (w._pwSetSportFilter && w._pwSetSportFilter('all'), w._pwSportPass('laliga')) : true, true);
});
