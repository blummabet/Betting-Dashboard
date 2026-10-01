// tests/frontend/serien-wetten.test.mjs — 01.10.2026
//
// Lucas: „output soll unter ‚national' in den Serien-Bereich und in der Übersicht in so eine Card".
// compute_streaks schreibt `wettliste` (Markt, Quote, Trefferchance je Serie). Beide Stellen lesen
// nur — gerechnet wird im Erzeuger. Geprüft: vergangene Spiele raus, nach Chance sortiert,
// Modell-Chancen als solche beschriftet, Team-Namen escaped.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';

const ROOT = new URL('../../', import.meta.url);

function holen(code, name) {
  const a = code.indexOf('function ' + name + '(');
  assert.ok(a >= 0, 'Funktion weg: ' + name);
  let tiefe = 0;
  for (let j = code.indexOf('{', a); j < code.length; j++) {
    if (code[j] === '{') tiefe++;
    else if (code[j] === '}') { tiefe--; if (!tiefe) return code.slice(a, j + 1); }
  }
  throw new Error('Klammern offen: ' + name);
}

const bald = h => new Date(Date.now() + h * 3600e3).toISOString();
const ROWS = [
  { team: 'Seattle', serie: 'Ungeschlagen', length: 9, gegner: 'Portland', heim: true, kickoff: bald(30),
    markt: 'Doppelte Chance (ungeschlagen)', chanceAus: 'markt', quote: 1.20, fairQuote: 1.22, quelle: 'pinnacle', trefferPct: 82.1 },
  { team: 'Vancouver<b>', serie: 'Über 2,5', length: 5, gegner: 'LA', heim: false, kickoff: bald(50),
    markt: 'Über 2,5 Tore', chanceAus: 'markt', quote: 1.44, fairQuote: 1.51, trefferPct: 66.3 },
  { team: 'Austin', serie: 'Trifft', length: 7, gegner: 'Dallas', heim: true, kickoff: bald(20),
    markt: 'Team trifft', chanceAus: 'modell', quote: null, trefferPct: 74 },
  { team: 'Alt', serie: 'Sieg', length: 4, gegner: 'X', heim: true, kickoff: bald(-3),
    markt: 'Sieg', chanceAus: 'markt', quote: 1.5, trefferPct: 99 },
];

test('Übersicht: Kachel heißt Serien-Wetten und liest die wettliste', () => {
  const JS = readFileSync(new URL('main-dashboard.js', ROOT), 'utf8');
  assert.match(JS, /tile\('🔥', 'Serien-Wetten'/);
  const _md = { data: { ligaStreaks: { wettliste: ROWS.slice(0, 2) }, mlsStreaks: { wettliste: ROWS.slice(2) } } };
  const f = new Function('_md', holen(JS, 'serienWetten') + '\nreturn serienWetten;')(_md);
  const r = f(5);
  assert.deepStrictEqual(r.map(x => x.team), ['Seattle', 'Austin', 'Vancouver<b>'], 'vergangenes Spiel raus, nach Chance');
  assert.strictEqual(f(1).length, 1);

  const zeile = new Function('esc', 'team', 'fl', '_flagFrom', 'A', '_mdDonutRow',
    holen(JS, '_mdSerienWetteZeile') + '\nreturn _mdSerienWetteZeile;')(
    s => String(s).replace(/</g, '&lt;'), x => x, () => '', () => '', { good: 'g', red: 'r' },
    (titel, sub, wert) => titel + '|' + sub + '|' + wert);
  const modell = zeile(ROWS[2]);
  assert.match(modell, /Chance laut Modell/);
  assert.doesNotMatch(modell, /@<b>/, 'ohne Quote keine Quote erfinden');
  const markt = zeile(ROWS[1]);
  assert.match(markt, /@<b>1\.44<\/b>/);
  assert.match(markt, /Chance laut Markt/);
  assert.doesNotMatch(markt, /Vancouver<b>/, 'Team-Name escaped');
});

test('National-Serien-Tab: Block steht vor den Serien und ist für die Liga verdrahtet', () => {
  const JS = readFileSync(new URL('wm2026-renderer.js', ROOT), 'utf8');
  assert.match(JS, /if \(isLiga\) html \+= _streakWettenHtml\(data && data\.wettliste, data && data\.buecher\)/);
  const f = new Function(holen(JS, '_esc') + '\n' + holen(JS, '_wettBuchText') + '\n' + holen(JS, '_streakWettenHtml') + '\nreturn _streakWettenHtml;')();
  const html = f(ROWS);
  assert.match(html, /3 spielbar/);
  assert.ok(html.indexOf('Seattle') < html.indexOf('Austin') && html.indexOf('Austin') < html.indexOf('Vancouver'));
  assert.doesNotMatch(html, />Alt</);
  assert.match(html, /faire Quote 1\.22 \(pinnacle\)/);
  assert.match(html, /Vancouver&lt;b&gt;/);
  assert.match(f([]), /Keine aktive Serie/);
});

// Punkt 5 (01.10.2026): das Buch zur Tafel. Das Urteil kommt fertig aus serien_wetten_buch.py.
const BUCH_LIGA = { gesamt: { n: 40, offen: 6, trefferPct: 71.5, erwartetPct: 70.2, urteil: 'stimmt · Geld sammelt' },
                    markt: { roiPct: -3.1, mitQuote: 31 } };
const BUCH_MLS = { gesamt: { n: 0, offen: 7 } };

test('Buch-Fuß im Serien-Tab: abgerechnet, getroffen gegen angezeigt, ROI, Urteil', () => {
  const JS = readFileSync(new URL('wm2026-renderer.js', ROOT), 'utf8');
  const f = new Function(holen(JS, '_esc') + '\n' + holen(JS, '_wettBuchText') + '\n'
    + holen(JS, '_streakWettenHtml') + '\nreturn _streakWettenHtml;')();
  const html = f(ROWS, [['Liga', BUCH_LIGA], ['MLS', BUCH_MLS], ['X', null]]);
  assert.match(html, /Liga: 40 abgerechnet · getroffen 71\.5 % bei angezeigt 70\.2 % · ROI zur gezeigten Quote -3\.1 % \(n=31\) · stimmt/);
  assert.match(html, /MLS: 7 vorgemerkt, noch keine abgerechnet/);
  assert.match(f([], [['Liga', BUCH_LIGA]]), /📒 Buch/, 'auch in der Länderspielpause sichtbar');
  assert.doesNotMatch(f(ROWS, []), /📒/);
  assert.match(JS, /buecher = \[\['Liga', j && j\.wettBuch\], \['MLS', m && m\.wettBuch\]\]/);
});

test('Buch-Zeilen in der Übersicht-Kachel', () => {
  const JS = readFileSync(new URL('main-dashboard.js', ROOT), 'utf8');
  const _md = { data: { ligaStreaks: { wettBuch: BUCH_LIGA }, mlsStreaks: { wettBuch: BUCH_MLS } } };
  const z = new Function('_md', holen(JS, 'serienBuchZeilen') + '\nreturn serienBuchZeilen;')(_md)();
  assert.deepStrictEqual(z, ['Liga: 40 abgerechnet · getroffen 71.5 % bei angezeigt 70.2 % · ROI -3.1 % (n=31) · stimmt · Geld sammelt',
                             'MLS: 7 vorgemerkt, noch keine abgerechnet']);
  assert.match(JS, /_swBuch = serienBuchZeilen\(\)/);
});
