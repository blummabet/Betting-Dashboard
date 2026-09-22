// tests/frontend/uebersicht-refresh-takt.test.mjs — 22.09.2026
//
// 🔴 Lucas: „Was ist da jetzt mit diesen 12 Megabyte, liga-data.json — was kann man da machen,
// oder wo führt das zu Problemen? Ich brauche immer Lösungsvorschläge."
//
// Gemessen wurden drei Kosten, die vorher als eine gezählt wurden:
//   · über die Leitung gehen 1,2 MB (gzip) — das Netz ist NICHT das Problem
//   · zu parsen und im Speicher: 12,7 MB — das ist es, und zwar am Handy
//   · und das alle ZWEI MINUTEN erneut, mit `no-store` und Cache-Buster
//
// Der 2-Minuten-Takt kam am 19.08.2026 aus einem echten Fund (Betfair-HT-Kasten zeigte alte
// Spiele). Für die Betfair-Dateien ist er richtig — sie wechseln alle 14-15 Minuten. Die
// schwerste Datei der Seite wechselt alle 110 Minuten und wird 30x pro Stunde geladen:
// 59 von 60 Ladungen sind umsonst.
//
// Fehlerklasse: ein Takt, der für die schnellste Quelle gesetzt ist und für alle gilt.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync, statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
import { JSDOM } from 'jsdom';

const ROOT = new URL('../../', import.meta.url);
const JS = readFileSync(new URL('main-dashboard.js', ROOT), 'utf8');

function fenster() {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="mainDashPanel"></div></body>',
    { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w._mdNoAutoRefresh = true;
  w.fetch = () => Promise.resolve({ ok: false });
  w.eval(JS);
  return w;
}

test('die schweren Dateien haben ein Mindest-Alter, die schnellen nicht', () => {
  const w = fenster();
  const tab = w.MD_CACHE_MIN;
  for (const f of ['liga-data.json', 'mls-data.json', 'liga_streaks.json', 'mls_streaks.json']) {
    assert.ok(tab[f] > 0, f + ' müsste ein Mindest-Alter haben');
  }
  for (const f of ['betfair_prices.json', 'stake_highroller.json', 'killer.json',
                   'dashboard_pulse.json', 'freigabe.json', 'betfair_overview.json']) {
    assert.ok(!tab[f], f + ' wechselt alle 14-15 Min und darf NICHT gecacht werden');
  }
});

test('⭐ die Tabelle stimmt mit der ECHTEN Änderungsrate überein', () => {
  // Der eigentliche Wächter. Eine Behauptung über einen Takt, die niemand nachmisst, veraltet
  // still — genau so ist der 2-Minuten-Takt zu einem Problem geworden. Gemessen wird gegen
  // `git log`, nicht gegen eine zweite Tabelle.
  const w = fenster();
  // 🔴 Beim Bau zuerst falsch: `new URL('.', ROOT).pathname` liefert den Pfad URL-KODIERT
  // („Betting%20Dashboard"), git fand das Verzeichnis nicht, `rate()` gab überall null zurück
  // und der Wächter übersprang stillschweigend ALLES. Eine Mutation (`liga-data.json: 999`)
  // überlebte ihn deshalb. Fehlerklasse: ein Guard, der nichts findet, weil er nichts ansieht —
  // und dessen Stille wie ein Freispruch aussieht. Deshalb unten auch `geprueft > 0`.
  const CWD = fileURLToPath(new URL('.', ROOT));
  const rate = (datei) => {
    try {
      const out = execFileSync('git', ['log', '--since=7 days ago', '--oneline', '--', datei],
        { cwd: CWD, encoding: 'utf8' });
      const n = out.split('\n').filter(Boolean).length;
      return n ? (7 * 24 * 60) / n : Infinity;      // Ø Abstand in Minuten
    } catch (_e) { return null; }
  };
  let geprueft = 0;
  for (const [datei, min] of Object.entries(w.MD_CACHE_MIN)) {
    const abstand = rate(datei);
    if (abstand == null) continue;                  // kein git — dann sagt der Test nichts
    geprueft++;
    assert.ok(abstand >= 2 * min,
      `${datei} wechselt im Schnitt alle ${Math.round(abstand)} Min, wird aber ${min} Min `
      + `gecacht. Das Mindest-Alter muss klar unter dem Änderungsabstand liegen, sonst kostet `
      + `es Frische statt Ladungen.`);
  }
  assert.ok(geprueft >= 4,
    `der Wächter hat nur ${geprueft} Dateien geprüft — wenn git hier nicht läuft, ist seine `
    + `Stille kein Freispruch. Genau daran ist er beim Bau einmal vorbeigelaufen.`);
  // Und die Gegenrichtung: was NICHT in der Tabelle steht und trotzdem gross und traege ist,
  // gehoert hinein. Sonst waechst die Seite wieder zu, ohne dass es auffaellt.
  const q = JS.match(/return Promise\.all\(\[([\s\S]*?)\]\);/)[1]
    .split('\n').filter(z => !z.trim().startsWith('//')).join('\n');
  const namen = [...q.matchAll(/jfSchlank\('([^']+)',\s*'[^']+'\)|jf\('([^']+)'\)/g)]
    .map(m => m[1] || m[2]);
  for (const n of namen) {
    if (w.MD_CACHE_MIN[n]) continue;
    let mb = 0;
    try { mb = statSync(new URL(n, ROOT)).size / 1e6; } catch (_e) { continue; }
    const abstand = rate(n);
    if (abstand == null) continue;
    assert.ok(!(mb > 0.25 && abstand >= 60),
      `${n} ist ${mb.toFixed(2)} MB gross und wechselt nur alle ${Math.round(abstand)} Min — `
      + `es gehört in MD_CACHE_MIN.`);
  }
});

test('der erste Aufruf holt alles — der Cache ist dann leer', async () => {
  // Das ist der Fall, über den Lucas sich am 12.09. beschwert hat („am iPhone lädt die
  // Übersicht beim ersten Aufruf langsam"). Er darf durch diese Änderung nicht schlechter
  // werden, und er wird es nicht: gespart wird erst ab dem ZWEITEN Laden.
  const w = fenster();
  assert.deepStrictEqual(Object.keys(w._mdFileCache), []);
  let geholt = [];
  w.fetch = (u) => { geholt.push(String(u).split('?')[0].split('/').pop());
                     return Promise.resolve({ ok: true, json: () => Promise.resolve({ a: 1 }) }); };
  await w._mdFetch();
  assert.ok(geholt.includes('liga-data.json'));
  assert.ok(geholt.includes('betfair_prices.json'));
});

test('⭐ der zweite Lauf spart genau die schweren Dateien', async () => {
  const w = fenster();
  w.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({ a: 1 }) });
  await w._mdFetch();
  const gecacht = Object.keys(w._mdFileCache);
  assert.ok(gecacht.includes('liga-data.json'), 'nach dem ersten Lauf liegt sie im Cache');
  assert.ok(!gecacht.includes('betfair_prices.json'), 'die schnellen werden nie gecacht');

  let geholt = [];
  w.fetch = (u) => { geholt.push(String(u).split('?')[0].split('/').pop());
                     return Promise.resolve({ ok: true, json: () => Promise.resolve({ a: 1 }) }); };
  await w._mdFetch();
  assert.ok(!geholt.includes('liga-data.json'), 'liga-data darf im zweiten Lauf nicht kommen');
  assert.ok(!geholt.includes('mls-data.json'));
  assert.ok(geholt.includes('betfair_prices.json'), 'die schnellen kommen weiter bei jedem Lauf');
  assert.ok(geholt.includes('killer.json'));
});

test('der Cache liefert dieselben Daten, nicht null', async () => {
  const w = fenster();
  w.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({ marke: 'echt' }) });
  const a = await w._mdFetch();
  w.fetch = () => Promise.resolve({ ok: false });   // ab jetzt würde jeder Abruf null liefern
  const b = await w._mdFetch();
  assert.deepStrictEqual(b[0], a[0], 'liga-data muss aus dem Cache kommen, nicht als null');
  assert.strictEqual(b[0].marke, 'echt');
});

test('⭐ ein fehlgeschlagener Abruf wird NICHT gecacht', async () => {
  // Sonst bliebe eine Kachel 20 Minuten leer, weil ein einzelner Abruf danebenging —
  // „fehlende Information rendert als harmloser Default", nur mit Verfallsdatum.
  const w = fenster();
  w.fetch = () => Promise.resolve({ ok: false });
  await w._mdFetch();
  assert.deepStrictEqual(Object.keys(w._mdFileCache), [],
    'null darf nie in den Cache — der nächste Lauf muss es erneut versuchen');
});

test('ein harter Refresh umgeht den Cache', async () => {
  const w = fenster();
  w.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({ a: 1 }) });
  await w._mdFetch();
  let geholt = [];
  w.fetch = (u) => { geholt.push(String(u).split('?')[0].split('/').pop());
                     return Promise.resolve({ ok: true, json: () => Promise.resolve({ a: 2 }) }); };
  await w._mdFetch(true);
  assert.ok(geholt.includes('liga-data.json'), 'bei _md.hart muss alles frisch kommen');
});

test('der automatische Refresh setzt NICHT hart — sonst wäre nichts gewonnen', () => {
  const quelle = JS.split('function _mdRefresh')[1].split('\n  }')[0];
  assert.match(quelle, /_mdLoad\(true\)/);
  assert.doesNotMatch(quelle, /_mdLoad\(true,\s*true\)/,
    'der Timer darf den Cache nicht umgehen — er ist der Grund, warum es ihn gibt');
});

test('⭐ _mdLoad reicht das Flag durch, statt es zu setzen', async () => {
  // Ohne diesen Fall überlebt `_mdFetch(true)` in _mdLoad: der Timer ruft brav ohne `hart`,
  // und trotzdem wird jedes Mal alles geholt. Der Test oben liest nur _mdRefresh und hätte
  // das nie gesehen — eine Regel an zwei Stellen, geprüft an einer.
  // Geprüft wird die WIRKUNG, nicht der Aufruf: `_mdFetch` liegt in der IIFE, ein
  // Monkey-Patch auf `window` erreicht den internen Aufruf nicht — ein Test, der das
  // versucht, prüft seine eigene Attrappe.
  const w = fenster();
  w.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({ a: 1 }) });
  await w._mdFetch();                       // erster Lauf füllt den Cache
  let geholt = [];
  w.fetch = (u) => { geholt.push(String(u).split('?')[0].split('/').pop());
                     return Promise.resolve({ ok: true, json: () => Promise.resolve({ a: 1 }) }); };
  w.eval('_mdLoad(true)');
  await new Promise(r => setTimeout(r, 30));
  assert.ok(geholt.length, '_mdLoad(true) muss überhaupt laden');
  assert.ok(!geholt.includes('liga-data.json'),
    '_mdLoad(true) ist ein normaler Refresh — nur _mdLoad(true, true) ist hart');

  geholt = [];
  w._mdLoad(true, true);
  await new Promise(r => setTimeout(r, 30));
  assert.ok(geholt.includes('liga-data.json'), '_mdLoad(true, true) muss alles frisch holen');
});
