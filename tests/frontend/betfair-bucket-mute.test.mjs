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

test('gemutet wird auf dem Urteil des Produzenten, nicht auf einer eigenen Schwelle', () => {
  // 04.09.2026 (Lucas: „geh die verbleibenden Duplikate durch"): das Mute hatte SEINE EIGENE
  // Schwelle (-0,05), während der Rest des Systems bei -0,10 fadete — eine vierte Zahl neben
  // den drei, die ein Test gleichhielt. Jetzt fällt betfair_track_record.py das Urteil einmal.
  assert.match(JS, /b\.urteil==='verliert'/);
  assert.ok(!/b\.roiUg<=-0\.05/.test(JS), 'die eigene Schwelle darf nicht zurückkommen');
  assert.ok(!/b\.n>=10 && typeof b\.roi==='number'/.test(JS), 'und der Punktschätzer erst recht nicht');
});

test('ohne Urteil wird nicht gemutet — nichts zu wissen ist kein Grund wegzublenden', () => {
  const m = JS.match(/function _tMute\(g\)\{[\s\S]*?return \{m:false,r:''\}; \}/);
  assert.ok(m, '_tMute gefunden');
  assert.ok(!/b\.n\s*>=\s*\d+/.test(m[0]), 'kein n-Schwellwert mehr im Mute');
  // Kommentarzeilen dürfen die Zahlen nennen (sie erklären ja, was früher falsch war) —
  // im ausführbaren Teil darf keine Schwelle mehr stehen.
  const code = m[0].split('\n').filter(z => !z.trim().startsWith('//')).join('\n');
  assert.ok(!/-0\.\d+/.test(code), 'und keine Schwelle — die steht beim Produzenten');
});

test('das Badge färbt nur, wo ein Urteil existiert', () => {
  // 04.09.2026: auch die Farbe folgt jetzt dem Urteil des Produzenten. Vorher prüfte das Badge
  // das Vorzeichen von roiUg selbst — dann kann es grün stehen, während das Mute rot urteilt.
  assert.match(JS, /if\(r\.b && r\.b\.urteil\)\{/);
  assert.match(JS, /_pos=r\.b\.urteil==='traegt'/);
  assert.match(JS, /kein Urteil · n/);
});

test('die Kopfzeile nennt die richtige Schwelle', () => {
  assert.match(JS, /Urteil erst ab n≥30 \(Rendite-Untergrenze\)/);
  assert.ok(!/CLV-Bucket = hist\. Kante je Liga \(n≥10\)/.test(JS));
});

test('die Mute-Überschrift erklärt den neuen Grund', () => {
  assert.match(JS, /Rendite-UNTERGRENZE negativ/);
});
