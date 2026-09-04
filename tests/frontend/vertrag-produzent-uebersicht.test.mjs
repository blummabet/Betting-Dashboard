// tests/frontend/vertrag-produzent-uebersicht.test.mjs — 04.09.2026
//
// Lucas: „Bin gespannt, wann wir die Übersicht mal fehlerfrei haben."
//
// Berechtigt — und die drei Funde von heute waren nicht zufällig, sie waren dreimal dieselbe
// Bauart. ZWEI davon waren Korrekturen, die ich am selben Tag woanders schon gemacht hatte:
//
//   · Die Serien-Sortierung wurde morgens in compute_streaks.py + wm2026-renderer.js auf
//     Seltenheit umgestellt. Die Übersicht hat ihre EIGENE `allStreaks()` — und sortierte
//     weiter nach Länge, während sie die Grundrate danebenschrieb.
//   · Die Verwechslung „Public-Kandidaten (Vorschau) ≠ gesendete Pushs" wurde morgens im
//     Track-Record aufgelöst. Die Übersicht hat ihre EIGENE Kachel — und hieß weiter
//     „Poly Public".
//   · `basis === 'pure'` stand noch im Code, obwohl der Produzent diesen Wert nicht mehr
//     kennt. Ein toter Zweig, der still das falsche Label wählte.
//
// Die Übersicht ist eine Zusammenfassung von elf Engines, und sie baut Logik nach, statt sie zu
// lesen. Jede Korrektur woanders muss von Hand gespiegelt werden — und wird es nicht.
//
// Dieser Test schließt nicht die einzelnen Fehler, sondern die KLASSE: kein Frontend darf auf
// einen Feldwert prüfen, den sein Produzent gar nicht (mehr) erzeugen kann. Genau das hätte
// `basis === 'pure'` sofort gefangen — und fängt den nächsten toten Zweig.
//
// Vorbild ist der bestehende Test „die Schwellen stehen an drei Stellen — und überall gleich"
// (uebersicht-bftrack.test.mjs). Der hat heute funktioniert: er hat angeschlagen, als ich die
// Betfair-Schwellen geändert habe. Diese Idee gehört auf die anderen Duplikate ausgeweitet.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';

const ROOT = new URL('../../', import.meta.url);
const lies = (f) => readFileSync(new URL(f, ROOT), 'utf8');

const MD = lies('main-dashboard.js');
const WM = lies('wm2026-renderer.js');
const CS = lies('compute_streaks.py');

/** Alle Zeichenketten, auf die ein Frontend für `feld` vergleicht. */
function frontendWerte(js, feld) {
  const re = new RegExp(`\\.${feld}\\s*===\\s*['"]([a-zA-Z_]+)['"]`, 'g');
  const out = new Set();
  let m;
  while ((m = re.exec(js))) out.add(m[1]);
  return out;
}
/** Alle Zeichenketten, die der Produzent für `feld` schreiben kann. */
function produzentWerte(py, muster) {
  const out = new Set();
  for (const re of muster) {
    let m;
    const r = new RegExp(re, 'g');
    while ((m = r.exec(py))) out.add(m[1]);
  }
  return out;
}

test('kein Frontend prüft auf ein `basis`, das compute_streaks nicht erzeugt', () => {
  // Die basis-Werte stehen als letzte Zeichenkette auf den `basis_art = …`-Zeilen.
  const kann = new Set();
  for (const zeile of CS.split('\n')) {
    if (!zeile.includes('basis_art')) continue;
    const treffer = zeile.match(/"([a-z]+)"/g) || [];
    if (treffer.length) kann.add(treffer[treffer.length - 1].replace(/"/g, ''));
  }
  assert.ok(kann.size >= 2, 'die basis-Werte im Produzenten sind nicht mehr auffindbar');
  for (const [name, js] of [['main-dashboard.js', MD], ['wm2026-renderer.js', WM]]) {
    for (const w of frontendWerte(js, 'basis')) {
      // „gelernt" gehört zur Liga-Norm (betfair/stake), nicht zu den Serien — anderes Feld,
      // gleicher Name. Nur die Serien-Vokabeln werden hier geprüft.
      if (w === 'gelernt' || w === 'zu' || w === 'duenn') continue;
      assert.ok(kann.has(w),
        `${name} prüft auf basis === '${w}', aber compute_streaks.py kann nur ${[...kann].join('/')} schreiben — toter Zweig`);
    }
  }
});

test('kein Frontend prüft auf einen `state`, den compute_streaks nicht erzeugt', () => {
  const kann = produzentWerte(CS, ['return\\s+"(intakt|neutral|wackelt|unbelegt)"', '"state":\\s*"([a-z]+)"']);
  assert.ok(kann.size >= 3);
  for (const [name, js] of [['main-dashboard.js', MD], ['wm2026-renderer.js', WM]]) {
    for (const w of frontendWerte(js, 'state')) {
      if (w === 'contradict') continue;   // Signal-Zustand, kommt aus _next_match_signal
      assert.ok(kann.has(w), `${name} prüft auf state === '${w}' — den gibt es im Produzenten nicht`);
    }
  }
});

// ── Die zweite Bauart: die Übersicht sortiert selbst, was der Produzent schon entschieden hat ──
test('die Übersicht rankt Serien nach demselben Kriterium wie der Produzent', () => {
  // compute_streaks.py sortiert nach zufallPct und schreibt das ins _meta. Wenn die Übersicht
  // nach etwas anderem rankt, stehen zwei Wahrheiten nebeneinander — genau der Fund von heute.
  assert.match(CS, /"sortiert":\s*"zufallPct"/, 'der Produzent nennt sein Sortierkriterium nicht mehr');
  const von = MD.indexOf('  function allStreaks(');
  const bis = MD.indexOf('  function bestStreaks(');
  const fn = MD.slice(von, bis);
  assert.ok(von > 0 && bis > von, 'allStreaks nicht gefunden');
  assert.match(fn, /zufallPct|_mdStreakSelten/, 'die Übersicht sortiert wieder nach etwas Eigenem');
  assert.ok(!/\(\+b\.length \|\| 0\) - \(\+a\.length \|\| 0\)\) \|\| \(rb - ra\)/.test(fn),
    'die alte Längen-Sortierung ist zurück');
});

test('der Serien-Tab und die Übersicht benutzen dasselbe Seltenheitsmaß', () => {
  assert.match(WM, /s\.zufallPct/, 'der Serien-Tab liest zufallPct nicht mehr');
  assert.match(MD, /x\.zufallPct|s\.zufallPct/, 'die Übersicht liest zufallPct nicht mehr');
});

// ── Die dritte Bauart: fest getippte Sätze, die eine Zahl behaupten ──────────
test('Ebene 1 behauptet den Blockierungsgrund nicht mehr, sondern rechnet ihn', () => {
  // „keine Schublade hat ihre Untergrenze über null" war an dem Tag schlicht falsch:
  // Liga · ABWÄGEN stand bei n46 / ROI +24,4 % / ROI-UG +3,7 % — blockiert hat die CLV-Bedingung.
  assert.ok(!/keine Schublade hat ihre Untergrenze über null/.test(MD));
  assert.match(MD, /_roiOk\s*=\s*_reif\.filter/, 'der Grund wird nicht mehr aus den Daten bestimmt');
});

test('die Poly-Kachel benennt sich nach dem, was sie misst', () => {
  assert.ok(!/🎮 Poly Public/.test(MD), '„Poly Public" las sich wie die Bilanz des Kanals');
  assert.match(MD, /Vorschau, sendet nicht/);
});
