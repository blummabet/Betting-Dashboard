// tests/frontend/pwa-nav.test.mjs — PWA-Tags + Navigation (Bottom-Nav mobil, „Mehr"-Dropdown web).
// (1) Statisch: season-finish-v2.html hat Manifest/Apple-Tags + Bottom-Nav/Sheet + Web-Dropdown + SW.
// (2) Verhalten: showView() spiegelt aktiven Tab in Bottom-Nav UND „Mehr"-Dropdown; Toggles auf/zu.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const HTML = new URL('../../season-finish-v2.html', import.meta.url);
const UI   = new URL('../../ui.js', import.meta.url);

test('PWA-Tags + Navi-Markup (Bottom-Nav, Sheet, Web-Dropdown) im HTML vorhanden', () => {
  const raw = readFileSync(HTML, 'utf8');
  const d = new JSDOM(raw).window.document;        // runScripts NICHT gesetzt → kein JS-Lauf
  // PWA
  assert.ok(d.querySelector('link[rel="manifest"]'), 'manifest-Link fehlt');
  assert.ok(d.querySelector('link[rel="apple-touch-icon"]'), 'apple-touch-icon fehlt');
  assert.ok(d.querySelector('meta[name="apple-mobile-web-app-capable"]'), 'apple-mobile-web-app-capable fehlt');
  assert.match(raw, /serviceWorker\.register/, 'SW-Registrierung fehlt');
  // Sub-Navi: Cards + Serien + Tracking (Serien zwischen Cards und Tracking, 28.06.2026)
  assert.equal(d.querySelectorAll('#subNav .sub-nav-btn').length, 3, 'Sub-Navi: Cards, Serien, Tracking');
  assert.ok(d.getElementById('subStreaks'), 'Serien-Sub-Tab fehlt');
  // Web „Mehr"-Dropdown mit 3 Einträgen (Heart/Status/TikTok) — Telegram wanderte in den Status
  assert.ok(d.getElementById('navMore'), 'Web-Mehr-Button fehlt');
  assert.equal(d.querySelectorAll('#topMoreMenu .tm-item').length, 3, '3 Dropdown-Einträge erwartet');
  // Mobile Bottom-Nav (5 Tabs) + Sheet (jetzt 5: Poly×2, TikTok, Heart, Status)
  assert.equal(d.querySelectorAll('.bottom-nav .bn-btn').length, 5, '5 Bottom-Tabs erwartet');
  assert.equal(d.querySelectorAll('.more-sheet .ms-btn').length, 5, '5 Sheet-Einträge erwartet');
  // Telegram Control liegt jetzt als ausklappbarer Abschnitt im Status-Tab, nicht mehr im Menü
  assert.ok(d.getElementById('st_telegram'), 'Telegram-Details im Status-Tab fehlt');
  assert.equal(d.querySelectorAll('[data-view="intl-telegram"]').length, 0, 'Kein Telegram-Menüeintrag mehr');
});

test('showView spiegelt aktiven Tab in Bottom-Nav + Web-Dropdown; Toggles auf/zu', () => {
  const dom = new JSDOM(`<!DOCTYPE html><body>
    <div id="mainContent"></div><div id="intlCardsPanel"></div><div id="tiktokStudioPanel"></div>
    <div id="polymarketPanel"></div><div id="heartPanel"></div><div id="statusPanel"></div>
    <button id="navIntl"></button>
    <div class="top-nav-more" id="topNavMore">
      <button id="navMore"></button>
      <div class="top-more-menu" id="topMoreMenu">
        <button class="tm-item" data-view="heart"></button>
        <button class="tm-item" data-view="status"></button>
        <button class="tm-item" data-view="intl-studio" id="tmTik"></button>
      </div>
    </div>
    <div class="sub-nav" id="subNav"><button id="subCards"></button><button id="subTracking"></button></div>
    <nav class="bottom-nav">
      <button class="bn-btn" data-sec="intl" id="bnIntl"></button>
      <button class="bn-btn" id="bnMore"></button>
    </nav>
    <div class="more-sheet" id="moreSheet">
      <button class="ms-btn" data-view="intl-studio" id="msTik"></button>
      <button class="ms-btn" data-sec="heart" id="msHeart"></button>
    </div>
  </body>`, { runScripts: 'outside-only' });
  const w = dom.window;
  w.eval(readFileSync(UI, 'utf8'));
  // Stubs NACH dem eval — initStatus o.ä. sind in ui.js selbst deklariert und würden Stubs
  // davor überschreiben (echter initStatus macht async fetch → innerHTML auf fehlendem Element).
  for (const fn of ['initStatus','initPolymarket','initPolyTrader','initPolyWallets',
    'initNationalCards','initNationalTracking','initIntlCards','initIntlTracking','initWm2026',
    'initTelegramPanel','initTiktokStudio','renderSharpRadar','logDashboardAction','buildValidatorDates']) {
    w[fn] = () => {};
  }
  const $ = (id) => w.document.getElementById(id);

  // TikTok Studio (intl-Section, aber „Mehr"-View) → Mehr aktiv, Intl-Tab NICHT, Sub-Navi versteckt
  try { w.showView('intl-studio'); } catch (_) {}
  assert.ok($('navMore').classList.contains('active'), 'Web-Mehr aktiv bei TikTok');
  assert.ok($('tmTik').classList.contains('active'), 'Dropdown-TikTok aktiv');
  assert.ok($('bnMore').classList.contains('active'), 'Bottom-Mehr aktiv bei TikTok');
  assert.ok(!$('bnIntl').classList.contains('active'), 'Intl-Tab darf bei TikTok nicht aktiv sein');
  assert.ok($('msTik').classList.contains('active'), 'Sheet-TikTok (data-view) aktiv');
  assert.equal($('subNav').style.display, 'none', 'Sub-Navi bei TikTok versteckt');

  // Status → Mehr aktiv
  try { w.showView('status'); } catch (_) {}
  assert.ok($('navMore').classList.contains('active'), 'Web-Mehr aktiv bei Status');

  // Intl-Cards → Intl-Tab aktiv, Mehr NICHT, Sub-Navi sichtbar + Cards aktiv
  try { w.showView('intl-cards'); } catch (_) {}
  assert.ok($('bnIntl').classList.contains('active'), 'Intl-Bottom-Tab aktiv');
  assert.ok(!$('navMore').classList.contains('active'), 'Mehr nicht aktiv bei Intl-Cards');
  assert.notEqual($('subNav').style.display, 'none', 'Sub-Navi bei Cards sichtbar');
  assert.ok($('subCards').classList.contains('active'), 'Cards-Sub-Tab aktiv');

  // Dropdown-Toggle
  try { w.showView('national-cards'); } catch (_) {}
  assert.ok(!$('topMoreMenu').classList.contains('open'));
  w.toggleTopMore();
  assert.ok($('topMoreMenu').classList.contains('open'), 'Dropdown offen');
  w.closeTopMore();
  assert.ok(!$('topMoreMenu').classList.contains('open'), 'Dropdown zu');

  // Mobile-Sheet-Toggle
  w.toggleMoreSheet();
  assert.ok($('moreSheet').classList.contains('open'), 'Sheet offen');
  w.toggleMoreSheet();
  assert.ok(!$('moreSheet').classList.contains('open'), 'Sheet zu');
});
