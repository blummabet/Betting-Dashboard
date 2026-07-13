// ═══════════════════════════════════════════════════════════════════════════
//  test_poly_wallets_dataset_switch.js — Guard gegen den „Tab bleibt leer"-Bug
//
//  12.07.2026 (Lucas: „im Whale-Wallets-Tab erscheint nichts, wenn ich auf MLS klicke").
//
//  URSACHE: Der aktive Datensatz lag in `window._pwDataset` — demselben Namen wie die
//  Funktion `_pwDataset()`. Top-Level-Funktionen hängen im Browser an `window`, also hat
//  `window._pwDataset = 'mls'` die Funktion mit einem String überschrieben. Der nächste
//  Aufruf warf „TypeError: _pwDataset is not a function", _pwRender starb, das Panel blieb
//  leer — ohne jede Fehlermeldung. WM lief, weil dort nie umgeschaltet wurde.
//
//  Dieser Test schaltet WIRKLICH um (nicht nur „die Funktion existiert") und prüft, dass
//  danach noch gerendert werden kann. Ein Namensclash dieser Art fällt hier sofort auf.
//
//  Lauf: node tests/test_poly_wallets_dataset_switch.js
// ═══════════════════════════════════════════════════════════════════════════
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');

let failed = 0;
function ok(name, cond, detail) {
  if (cond) { console.log('  ✅ ' + name); }
  else { failed++; console.log('  ❌ ' + name + (detail ? '  → ' + detail : '')); }
}

// ── Browser-nahe Umgebung: window IST der globale Scope, Funktionsdeklarationen landen dort.
const panel = { innerHTML: '', style: {} };
const sandbox = {
  document: {
    getElementById: (id) => (id === 'polyWalletsPanel' ? panel : null),
    createElement: () => ({ getContext: () => ({}), style: {}, setAttribute() {} }),
    head: { appendChild() {} },
  },
  Chart: function () { return { destroy() {} }; },
  _timeAgo: () => 'jetzt',
  console,
  fetch: () => Promise.resolve({ ok: false, json: () => Promise.resolve(null) }),
  setTimeout,
};
const vm = require('vm');
const ctx = vm.createContext(sandbox);
sandbox.window = ctx;   // ← genau wie im Browser: window === globalThis
vm.runInContext(fs.readFileSync(path.join(ROOT, 'poly-wallets.js'), 'utf8'), ctx);

console.log('\n🐋 poly-wallets — Datensatz-Umschalter\n');

ok('_pwDataset() ist eine Funktion', typeof ctx._pwDataset === 'function');
ok('Default-Datensatz = wm', ctx._pwDataset() === 'wm');

// ── DER eigentliche Guard: umschalten und danach WEITER benutzen können.
ctx._pwSwitchDataset('mls');
ok('nach Wechsel: _pwDataset() ist IMMER NOCH eine Funktion (kein Namensclash)',
   typeof ctx._pwDataset === 'function',
   'überschrieben mit: ' + typeof ctx._pwDataset);
ok('nach Wechsel: aktiver Datensatz = mls',
   typeof ctx._pwDataset === 'function' && ctx._pwDataset() === 'mls');

let threw = null;
try { ctx._pwFiles(); ctx._pwDatasetTabs(); } catch (e) { threw = e.message; }
ok('_pwFiles()/_pwDatasetTabs() laufen nach dem Wechsel ohne Exception', !threw, threw);

// Zurück + unbekannter Datensatz → Fallback statt Absturz
ctx._pwSwitchDataset('wm');
ok('Rückwechsel auf wm funktioniert', ctx._pwDataset() === 'wm');
ctx._pwSwitchDataset('gibtsnicht');
ok('unbekannter Datensatz wird ignoriert (bleibt wm)', ctx._pwDataset() === 'wm');

// Jeder Datensatz muss die 4 Dateien deklarieren (sonst fetcht der Tab ins Leere).
// (`const` landet nicht auf dem Global-Objekt → im Kontext auswerten statt ctx.PW_DATASETS.)
const DS = vm.runInContext('PW_DATASETS', ctx);
const need = ['id', 'icon', 'label', 'prices', 'wallets', 'data', 'hist'];
let cfgOk = Array.isArray(DS) && DS.length >= 2;
for (const d of (DS || [])) for (const k of need) if (!d[k]) cfgOk = false;
ok('PW_DATASETS: jeder Eintrag hat id/icon/label + 4 Dateinamen', cfgOk,
   'gefunden: ' + (Array.isArray(DS) ? DS.map(d => d.id).join(',') : typeof DS));

// Kein Rückfall in das alte Muster: der Zustand darf NIE window.<Funktionsname> heißen.
// Kommentare vorher entfernen — die BESCHREIBEN den alten Bug und dürfen nicht anschlagen.
const src = fs.readFileSync(path.join(ROOT, 'poly-wallets.js'), 'utf8')
  .replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
ok('kein `window.<Funktionsname> =` mehr im Code (Namensclash-Rückfall)',
   !/window\.\s*_pwDataset\s*=/.test(src));

console.log(failed ? `\n❌ ${failed} Fehler\n` : '\n✅ alle Checks grün\n');
process.exit(failed ? 1 : 0);
