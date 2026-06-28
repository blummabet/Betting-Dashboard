// tests/frontend/pwa-nav.test.mjs — PWA-Tags + mobile Bottom-Nav (28.06.2026, Lucas).
// (1) Statisch: season-finish-v2.html hat Manifest/Apple-Tags + Bottom-Nav-/Sheet-Markup + SW-Reg.
// (2) Verhalten: showView() spiegelt den aktiven Tab in die Bottom-Nav; toggleMoreSheet() öffnet/schließt.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const HTML = new URL('../../season-finish-v2.html', import.meta.url);
const UI   = new URL('../../ui.js', import.meta.url);

test('PWA-Tags + Bottom-Nav-Markup sind im HTML vorhanden', () => {
  const dom = new JSDOM(readFileSync(HTML, 'utf8'));   // runScripts NICHT gesetzt → kein JS-Lauf
  const d = dom.window.document;
  // PWA
  assert.ok(d.querySelector('link[rel="manifest"]'), 'manifest-Link fehlt');
  assert.ok(d.querySelector('link[rel="apple-touch-icon"]'), 'apple-touch-icon fehlt');
  assert.ok(d.querySelector('meta[name="apple-mobile-web-app-capable"]'), 'apple-mobile-web-app-capable fehlt');
  assert.ok(d.querySelector('meta[name="theme-color"]'), 'theme-color fehlt');
  assert.match(readFileSync(HTML, 'utf8'), /serviceWorker\.register/, 'SW-Registrierung fehlt');
  // Bottom-Nav
  assert.equal(d.querySelectorAll('.bottom-nav .bn-btn').length, 5, '5 Bottom-Tabs erwartet');
  assert.ok(d.getElementById('bnMore'), 'Mehr-Button fehlt');
  assert.equal(d.querySelectorAll('.more-sheet .ms-btn').length, 4, '4 Einträge im Mehr-Sheet erwartet');
});

test('showView spiegelt aktiven Tab in Bottom-Nav + toggleMoreSheet öffnet/schließt', () => {
  const dom = new JSDOM(`<!DOCTYPE html><body>
    <div id="mainContent"></div><div id="polymarketPanel"></div><div id="heartPanel"></div>
    <nav class="bottom-nav">
      <button class="bn-btn" data-sec="national" id="bnNat"></button>
      <button class="bn-btn" data-sec="sharp" id="bnSharp"></button>
      <button class="bn-btn" id="bnMore"></button>
    </nav>
    <div class="more-sheet" id="moreSheet">
      <button class="ms-btn" data-sec="polybetting" id="msPb"></button>
      <button class="ms-btn" data-sec="heart" id="msHeart"></button>
    </div>
  </body>`, { runScripts: 'outside-only' });
  const w = dom.window;
  // Init-Callbacks stubben (showView ruft sie am Ende auf)
  for (const fn of ['initStatus','initPolymarket','initPolyTrader','initPolyWallets',
    'initNationalCards','initNationalTracking','initIntlCards','initIntlTracking','initWm2026',
    'initTelegramPanel','initTiktokStudio','renderSharpRadar','logDashboardAction','buildValidatorDates']) {
    w[fn] = () => {};
  }
  w.eval(readFileSync(UI, 'utf8'));

  // „Mehr"-Sektion (polybetting) → Mehr-Button aktiv, Sheet-Eintrag aktiv
  try { w.showView('polybetting'); } catch (_) {}
  assert.ok(w.document.getElementById('bnMore').classList.contains('active'), 'Mehr-Button muss bei polybetting aktiv sein');
  assert.ok(w.document.getElementById('msPb').classList.contains('active'), 'Sheet-Eintrag polybetting aktiv');
  assert.ok(!w.document.getElementById('bnNat').classList.contains('active'), 'National darf nicht aktiv sein');

  // Direkter Tab (sharp) → bnSharp aktiv, Mehr nicht
  try { w.showView('sharp'); } catch (_) {}
  assert.ok(w.document.getElementById('bnSharp').classList.contains('active'));
  assert.ok(!w.document.getElementById('bnMore').classList.contains('active'));

  // Sheet-Toggle
  const sheet = w.document.getElementById('moreSheet');
  assert.ok(!sheet.classList.contains('open'));
  w.toggleMoreSheet();
  assert.ok(sheet.classList.contains('open'), 'Sheet muss offen sein');
  w.toggleMoreSheet();
  assert.ok(!sheet.classList.contains('open'), 'Sheet muss wieder zu sein');
});
