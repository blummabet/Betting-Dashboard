// tests/frontend/uebersicht-check-0409.test.mjs — 04.09.2026
//
// Lucas: „Übersicht check". Drei Funde, alle in main-dashboard.js.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';

const MD = readFileSync(new URL('../../main-dashboard.js', import.meta.url), 'utf8');

// ── 1. Die Serien-Kachel sortierte weiter nach Länge ────────────────────────
// Der Serien-Umbau vom selben Tag (zufallPct statt Länge) lief an der Übersicht vorbei: die
// hat ihre eigene Sortierung. Ergebnis auf dem Board — fünfmal derselbe Markt:
//   „Chicago Fire · Team trifft 15× · Grundrate 82 %"
//   „Inter Miami   · Team trifft 15× · Grundrate 82 %"  …
// Die Kachel schrieb die Grundrate selbst dazu und rankte trotzdem danach, dass sie hoch ist.
function streakSort() {
  const von = MD.indexOf('  function _mdStreakSelten(');
  const bis = MD.indexOf('  function bestStreaks(');
  assert.ok(von > 0 && bis > von, 'allStreaks/_mdStreakSelten nicht gefunden');
  const g = {};
  // eslint-disable-next-line no-new-func
  new Function('exp', '_md', MD.slice(von, bis) + '\nexp.f=allStreaks;')(
    g, { data: { ligaStreaks: { streaks: g.__ }, mlsStreaks: null } });
  return g;
}

function sortiere(streaks) {
  const von = MD.indexOf('  function _mdStreakSelten(');
  const bis = MD.indexOf('  function bestStreaks(');
  const g = {};
  // eslint-disable-next-line no-new-func
  new Function('exp', '_md', MD.slice(von, bis) + '\nexp.f=allStreaks;')(
    g, { data: { ligaStreaks: { streaks }, mlsStreaks: null } });
  return g.f();
}

test('die seltenste Serie steht oben, nicht die längste', () => {
  const out = sortiere([
    { length: 15, type: 'scored', market: 'Team trifft', zufallPct: 3.87 },
    { length: 5, type: 'cleanSheet', market: 'Zu null', zufallPct: 0.027 },
  ]);
  assert.strictEqual(out[0].market, 'Zu null', '1 zu 3.700 schlägt 1 zu 26');
});

test('ohne Maßstab bleibt es bei der alten Ordnung', () => {
  const out = sortiere([{ length: 6, market: 'A' }, { length: 9, market: 'B' }]);
  assert.strictEqual(out[0].market, 'B', 'kein zufallPct → längste zuerst, wie bisher');
});

test('Serien mit Maßstab stehen vor denen ohne', () => {
  const out = sortiere([
    { length: 12, market: 'ohne' },
    { length: 4, market: 'mit', zufallPct: 0.5 },
  ]);
  assert.strictEqual(out[0].market, 'mit');
});

test('logisch eingeschlossene Serien fallen aus der Fünfer-Kachel', () => {
  const out = sortiere([
    { length: 7, market: 'Sieg-Serie', zufallPct: 0.49 },
    { length: 7, market: 'Ungeschlagen', zufallPct: 0.49, impliziertVon: 'win' },
  ]);
  assert.strictEqual(out.length, 1);
  assert.strictEqual(out[0].market, 'Sieg-Serie');
});

test('das Label nennt, woher die Grundrate kommt', () => {
  // Vorher stand überall „Grundrate X%" — je nach Fall war das die Team-Historie ODER
  // (seit heute) der Liga-Schnitt. Zwei verschiedene Dinge unter einem Namen.
  assert.match(MD, /Liga-Schnitt '/);
  assert.match(MD, /' · vorher '/);
  assert.ok(!/s\.basis === 'pure'/.test(MD), "basis „pure\" gibt es nicht mehr");
});

// ── 2. Ebene 1 nannte den falschen Grund ────────────────────────────────────
// „keine Schublade hat ihre Untergrenze über null" — an dem Tag falsch:
//     Liga · ABWÄGEN   n46   ROI +24,4 %   ROI-UG +3,7 %   CLV-UG −2,16
// Die ROI-Untergrenze lag über null; blockiert hat die CLV-Bedingung.
test('der Grund wird aus den Zahlen bestimmt, nicht behauptet', () => {
  assert.ok(!/keine Schublade hat ihre Untergrenze über null/.test(MD),
    'die pauschale Behauptung darf nicht mehr dastehen');
  assert.match(MD, /scheiter' \+ \(_roiOk\.length === 1 \? 't' : 'n'\) \+ ' an der <b>CLV-Bedingung<\/b>/);
  assert.match(MD, /_roiLb|roiLb > 0/);
});

test('strukturell unerfüllbare Schubladen werden benannt', () => {
  // 7 der 18 reifen Schubladen tragen gar keinen CLV-Wert (Over/Under 2.5 mit n=1668,
  // Match Odds n=1654 …). „CLV-UG ≥ 0" ist mit einem fehlenden Wert nie erfüllbar.
  assert.match(MD, /tragen gar keinen CLV-Wert/);
  assert.match(MD, /nie erfüllen, unabhängig vom ROI/);
});

// ── 3. „Poly Public" war die Vorschau, die nichts sendet ────────────────────
test('die Kachel heißt nach dem, was sie misst', () => {
  assert.ok(!/🎮 Poly Public/.test(MD), '„Poly Public" las sich wie die Bilanz des Kanals');
  assert.match(MD, /🎮 Poly-Kandidaten/);
  assert.match(MD, /Vorschau, sendet nicht/);
});

test('die Zahl der echt gesendeten Pushs steht daneben', () => {
  assert.match(MD, /pl\.gesendetN != null/);
  assert.match(MD, /'echt gesendet'/);
});
