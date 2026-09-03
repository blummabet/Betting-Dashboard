// tests/frontend/pwa-nav.test.mjs — PWA-Tags + Navigation (Bottom-Nav mobil, „Mehr"-Dropdown web).
// (1) Statisch: season-finish-v2.html hat Manifest/Apple-Tags + Bottom-Nav/Sheet + Web-Dropdown + SW.
// (2) Verhalten: showView() spiegelt aktiven Tab in Bottom-Nav UND „Mehr"-Dropdown; Toggles auf/zu.
// 14.08.2026 (Lucas): Navi-Umbau — PRIMÄR = Übersicht/National/Poly-Betting/Poly-Wallets/Betfair/Money-Map;
// MEHR = International/Poly-Trading/Sharp/Heart/Status/TikTok/Analyse. Tests entsprechend nachgezogen.
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
  // Web „Mehr"-Dropdown (International/Poly-Trading/Sharp/Heart/Status/TikTok/Analyse/Stake, 03.09.2026)
  assert.ok(d.getElementById('navMore'), 'Web-Mehr-Button fehlt');
  // 03.09.2026: vorher zaehlte das hier nur. Eine Zahl sagt nicht, WAS fehlt — und beim
  // Stake-Radar fiel genau deshalb auf, dass der Eintrag im Web-Dropdown stand, im mobilen
  // Sheet aber nicht: mobil war der Tab unerreichbar. Jetzt werden die MENGEN verglichen,
  // damit ein neuer Eintrag nie nur auf einer der beiden Flaechen landet.
  // Die beiden Flaechen benennen ihre Ziele historisch unterschiedlich (das Sheet trug frueher
  // data-sec, das Dropdown data-view), ein Namensvergleich ginge also am Zustand vorbei. Was
  // zaehlt, ist: gleich viele Eintraege, und der neue auf BEIDEN.
  const ziele = (sel, b) => [...d.querySelectorAll(sel)].map(x => x.dataset.view || x.dataset.sec);
  const drop = ziele('#topMoreMenu .tm-item');
  const sheet = ziele('.more-sheet .ms-btn');
  assert.equal(drop.length, 8, '8 Dropdown-Eintraege erwartet');
  assert.equal(sheet.length, drop.length,
    'Web-Dropdown und mobiles Sheet aus dem Takt — ein Tab waere auf einer Flaeche unerreichbar');
  assert.ok(drop.includes('stakeradar'), 'Stake Radar fehlt im Web-Dropdown');
  assert.ok(sheet.includes('stakeradar'), 'Stake Radar fehlt im mobilen Sheet');
  // Mobile Bottom-Nav (7 Tabs: Übersicht/National/Betting/Wallets/Betfair/Money/Mehr)
  assert.equal(d.querySelectorAll('.bottom-nav .bn-btn').length, 7, '7 Bottom-Tabs erwartet');
  // Telegram Control liegt jetzt als ausklappbarer Abschnitt im Status-Tab, nicht mehr im Menü
  assert.ok(d.getElementById('st_telegram'), 'Telegram-Details im Status-Tab fehlt');
  assert.equal(d.querySelectorAll('[data-view="intl-telegram"]').length, 0, 'Kein Telegram-Menüeintrag mehr');
});

test('showView spiegelt aktiven Tab in Bottom-Nav + Web-Dropdown; Toggles auf/zu', () => {
  // 14.08.2026 (Lucas): International/Sharp/Poly-Trading sind ins „Mehr" gewandert; Poly-Betting ist
  // jetzt ein Primär-Tab. DOM + Erwartungen entsprechend neu.
  const dom = new JSDOM(`<!DOCTYPE html><body>
    <div id="mainContent"></div><div id="intlCardsPanel"></div><div id="tiktokStudioPanel"></div>
    <div id="polymarketPanel"></div><div id="heartPanel"></div><div id="statusPanel"></div>
    <button id="navPolymarket"></button>
    <div class="top-nav-more" id="topNavMore">
      <button id="navMore"></button>
      <div class="top-more-menu" id="topMoreMenu">
        <button class="tm-item" data-view="intl-cards" id="tmIntl"></button>
        <button class="tm-item" data-view="sharp"></button>
        <button class="tm-item" data-view="heart"></button>
        <button class="tm-item" data-view="status"></button>
        <button class="tm-item" data-view="intl-studio" id="tmTik"></button>
      </div>
    </div>
    <div class="sub-nav" id="subNav"><button id="subCards"></button><button id="subTracking"></button></div>
    <nav class="bottom-nav">
      <button class="bn-btn" data-sec="polybetting" id="bnPolyBet"></button>
      <button class="bn-btn" id="bnMore"></button>
    </nav>
    <div class="more-sheet" id="moreSheet">
      <button class="ms-btn" data-sec="intl" id="msIntl"></button>
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

  // TikTok Studio (intl-Section, „Mehr"-View) → Mehr aktiv, Sub-Navi versteckt
  try { w.showView('intl-studio'); } catch (_) {}
  assert.ok($('navMore').classList.contains('active'), 'Web-Mehr aktiv bei TikTok');
  assert.ok($('tmTik').classList.contains('active'), 'Dropdown-TikTok aktiv');
  assert.ok($('bnMore').classList.contains('active'), 'Bottom-Mehr aktiv bei TikTok');
  assert.ok(!$('bnPolyBet').classList.contains('active'), 'Primär-Tab darf bei TikTok nicht aktiv sein');
  assert.ok($('msTik').classList.contains('active'), 'Sheet-TikTok (data-view) aktiv');
  assert.equal($('subNav').style.display, 'none', 'Sub-Navi bei TikTok versteckt');

  // Status → Mehr aktiv
  try { w.showView('status'); } catch (_) {}
  assert.ok($('navMore').classList.contains('active'), 'Web-Mehr aktiv bei Status');

  // International-Cards ist jetzt ein „Mehr"-Eintrag → Mehr aktiv, Sub-Navi sichtbar + Cards aktiv
  try { w.showView('intl-cards'); } catch (_) {}
  assert.ok($('navMore').classList.contains('active'), 'Web-Mehr aktiv bei International');
  assert.ok($('bnMore').classList.contains('active'), 'Bottom-Mehr aktiv bei International');
  assert.ok($('tmIntl').classList.contains('active'), 'Dropdown-International aktiv');
  assert.ok($('msIntl').classList.contains('active'), 'Sheet-International (data-sec) aktiv');
  assert.notEqual($('subNav').style.display, 'none', 'Sub-Navi bei Cards sichtbar');
  assert.ok($('subCards').classList.contains('active'), 'Cards-Sub-Tab aktiv');

  // Polymarket Betting ist jetzt ein PRIMÄR-Tab → eigener Bottom-Tab aktiv, Mehr NICHT
  try { w.showView('polybetting'); } catch (_) {}
  assert.ok($('bnPolyBet').classList.contains('active'), 'Poly-Betting-Bottom-Tab aktiv');
  assert.ok($('navPolymarket').classList.contains('active'), 'Poly-Betting-Web-Tab aktiv');
  assert.ok(!$('navMore').classList.contains('active'), 'Mehr nicht aktiv bei Poly-Betting');

  // Dropdown-Toggle
  try { w.showView('home'); } catch (_) {}
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
