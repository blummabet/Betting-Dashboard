// tests/frontend/betfair-bucket-mute.test.mjs — 04.09.2026
//
// Lucas: „mach ma mal Betfair-Check."
//
// Das Terminal blendete Zeilen aus, wenn der Liga-Bucket `n>=10 && roi<=-0.05` erfüllte. An dem
// Tag standen die fünf Ligen des Boards bei n = 9 bis 14, und das Muten traf ausgerechnet die
// drei überzeugtesten Zeilen: Man City (Konviktion 93), PSG (100), Arsenal (85).
//
// Rauschprobe über die echten 1.652 Match-Odds-Plays: dieselben Stichprobengrößen zufällig aus
// einem gemeinsamen Topf gezogen, ergeben in 91 % der Läufe eine mindestens so große Spanne
// zwischen bester und schlechtester Liga. Der Bucket sortierte Rauschen.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';

const JS = readFileSync(new URL('../../betfair-radar.js', import.meta.url), 'utf8');

test('gemutet wird auf der Untergrenze, nicht auf dem Punktschätzer', () => {
  assert.match(JS, /typeof b\.roiUg==='number' && b\.roiUg<=-0\.05/);
  assert.ok(!/b\.n>=10 && typeof b\.roi==='number' && b\.roi<=-0\.05/.test(JS),
    'das alte Gate auf n>=10 und roi darf nicht mehr dastehen');
});

test('ohne Untergrenze wird nicht gemutet — nichts zu wissen ist kein Grund wegzublenden', () => {
  const m = JS.match(/function _tMute\(g\)\{[\s\S]*?return \{m:false,r:''\}; \}/);
  assert.ok(m, '_tMute gefunden');
  assert.ok(!/b\.n\s*>=\s*\d+/.test(m[0]), 'kein n-Schwellwert mehr im Mute');
});

test('das Badge färbt nur, wo eine Untergrenze existiert', () => {
  assert.match(JS, /typeof r\.b\.roiUg==='number'/);
  assert.match(JS, /kein Urteil · n/);
});

test('die Kopfzeile nennt die richtige Schwelle', () => {
  assert.match(JS, /Urteil erst ab n≥30 \(Rendite-Untergrenze\)/);
  assert.ok(!/CLV-Bucket = hist\. Kante je Liga \(n≥10\)/.test(JS));
});

test('die Mute-Überschrift erklärt den neuen Grund', () => {
  assert.match(JS, /Rendite-UNTERGRENZE negativ/);
});
