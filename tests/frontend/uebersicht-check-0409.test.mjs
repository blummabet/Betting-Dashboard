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
  // (seit 04.09.) der Liga-Schnitt. Zwei verschiedene Dinge unter einem Namen.
  assert.match(MD, /Liga-Schnitt '/);
  assert.ok(!/s\.basis === 'pure'/.test(MD), "basis „pure\" gibt es nicht mehr");
});

test('die Seltenheit rechnet mit der EIGENEN Rate, nicht mit dem Liga-Schnitt', () => {
  // 05.09.2026 hielt dieser Test fest, dass die Seltenheit „Liga-Basis" als Nenner NENNT.
  // 08.09.2026, externes Feedback: das Nennen war nie das Problem — der Nenner war falsch.
  // „Parma · Unter 2,5, 10er: 1 von 11.990 (Liga-Basis 39 %)" neben „Eigenrate 80 %";
  // 0,8^10 sind 1 von 9. Faktor 1.290.
  //
  // ⭐ Damit hat der Test von damals die falsche Zahl ZEMENTIERT — genau die Klasse, vor der
  // sein eigener Kommentar warnte („ein Test, der den Defekt festhält"). Die Regel heißt jetzt:
  // das Frontend rechnet gar nichts mehr, es liest `seltenheit` aus dem Produzenten.
  assert.match(MD, /1 von '/, 'die Seltenheit steht auf dem Board');
  assert.match(MD, /s\.seltenheit/, 'sie kommt fertig aus compute_streaks');
  assert.match(MD, /eigene Rate '/, 'und nennt die Rate, aus der sie folgt');
  assert.match(MD, /Seltenheit nicht belegbar/,
    'ohne eigene Vorgeschichte gibt es kein Urteil — „unauffällig" und „nicht gemessen" sind '
    + 'nicht dasselbe');
  assert.match(MD, /im Feld erwartbar/,
    'der Erwartungswert im Suchfeld gehört daneben — sonst liest man jede Seltenheit als Befund');
  assert.ok(!/\(Liga-Basis ' \+ s\.ligaBasisPct/.test(MD),
    'der Liga-Schnitt darf nicht mehr als Nenner der Seltenheit erscheinen');
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

// ── 08.09.2026: der Nachfolge-Fund zum 04.09. ───────────────────────────────
// Die Kachel heißt seit dem 04.09. richtig — sie trug ihre Zahl aber weiter ohne Fehlerbalken.
// `poly_shortlist_track.agg.public` liefert `roiUg: −0,0283` und `belegt: false` gleich mit;
// angezeigt wurde nur das obere Ende des Bereichs (+6,3 %). Dieselbe Klasse, eine Ebene tiefer.
test('die Poly-Kachel zeigt ihre Untergrenze, nicht nur den Punktschätzer', () => {
  assert.match(MD, /pl\.roiUgPct/, 'die Untergrenze wird nicht gelesen');
  assert.match(MD, /'ROI · UG —'/, 'ohne Untergrenze muss „UG —" dastehen, nicht nichts');
  assert.match(MD, /pl\.belegt \? 'belegt' : 'nicht belegt'/,
    'ob die Untergrenze über null liegt, ist die eigentliche Aussage');
});
