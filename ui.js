// ═══════════════════════════════════════════════════════
//  ui.js — CocoBet View Switcher & Status Tab
//  Extracted from season-finish.html (Apr 2026)
//
//  Contains:
//    · showView()              — Tab / View switching
//    · logDashboardAction()    — Action logger
//    · _timeAgo()              — ISO → "vor X Min" helper
//    · _freshnessColor()       — Freshness color indicator
//    · _statusCard()           — Status card HTML builder
//    · _quickLink()            — Quick link HTML builder
//    · toggleValidatorDetails()— Validator detail toggle
//    · initStatus()            — Status tab data loader & renderer
//
//  Runtime dependencies (provided by the page):
//    · window._preMatchData    — loaded by prematch-server.js
//    · window._oddsData        — loaded by loadAllOdds()
//    · window._teamStats       — injected by refresh_stats.py
//    · buildValidatorDates()   — from validator.js
//    · DOM: document, window
// ═══════════════════════════════════════════════════════

// ═══════════════════════════════════════════════════════
//  VIEW SWITCHER — Two-level navigation
//  Top level:  national | intl | sharp | polytrading | polybetting | heart | status
//  Sub level:  cards | tracking  (only for national + intl)
// ═══════════════════════════════════════════════════════

// Track current top-level section so showSubView() knows where to navigate
let _activeSection = 'national';
// Track the full active view (28.06.2026) — nötig fürs „Mehr"-Menü (Heart/Status/Telegram/TikTok),
// weil intl-telegram/intl-studio dieselbe Section 'intl' haben.
let _activeView = 'home';

// All panel IDs — hidden when switching views
const _ALL_PANELS = [
  'mainDashPanel', 'mainContent', 'trackingV2Panel', 'resultsPanel',
  'intlCardsPanel', 'intlTrackingPanel', 'intlWm2026Panel', 'intlTelegramPanel',
  'tiktokStudioPanel', 'streaksPanel',
  'polymarketPanel', 'polyTraderPanel', 'polyWalletsPanel', 'betfairRadarPanel', 'moneyMapPanel',
  'heartPanel', 'statusPanel', 'signalCheckPanel', 'stakeRadarPanel',
];

// Top-nav button IDs (Heart/Status seit 28.06.2026 im „Mehr"-Dropdown, nicht mehr hier)
const _TOP_NAV_IDS = [
  // 14.08.2026 (Lucas): Primär-Nav = Übersicht/National/Poly-Betting/Poly-Wallets/Betfair/Money-Map.
  // Intl/Sharp/Poly-Trading sind ins „Mehr"-Menü gewandert (dort als tm-item via data-view aktiv).
  'navHome', 'navNational', 'navPolymarket', 'navPolyWallets', 'navBetfair', 'navMoneyMap',
];

function showView(view) {
  // ── Determine section ────────────────────────────────
  _activeView = view;
  _activeSection = view.startsWith('national') ? 'national'
                 : view.startsWith('intl')     ? 'intl'
                 : view;  // sharp | polytrading | polybetting | heart | status

  // ── Hide all panels ──────────────────────────────────
  _ALL_PANELS.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.display = 'none';
  });

  // ── Show correct panel ───────────────────────────────
  const panelMap = {
    'home':              'mainDashPanel',
    'national-cards':    'mainContent',
    'national-tracking': 'trackingV2Panel',
    'national-streaks':  'streaksPanel',
    'intl-streaks':      'streaksPanel',
    'intl-cards':        'intlCardsPanel',
    'intl-tracking':     'intlTrackingPanel',
    'intl-wm2026':       'intlWm2026Panel',
    'intl-studio':       'tiktokStudioPanel',
    'sharp':             'mainContent',
    'polytrading':       'polyTraderPanel',
    'polybetting':       'polymarketPanel',
    'polywallets':       'polyWalletsPanel',
    'betfair':           'betfairRadarPanel',
    'moneymap':          'moneyMapPanel',
    'analyse':           'signalCheckPanel',
    'stakeradar':        'stakeRadarPanel',
    'heart':             'heartPanel',
    'status':            'statusPanel',
  };
  const panelId = panelMap[view];
  if (panelId) {
    const panel = document.getElementById(panelId);
    if (panel) panel.style.display = '';
  }

  // ── Alte statische League-Nav + Legende: komplett raus ───────────────
  // (25.06.2026, Lucas) National nutzt den Flaggen-Gruppenfilter des WM-Renderers; für Sharp
  // Radar braucht die alte League-Nav auch niemand → überall ausblenden (keine doppelte Navi).
  const leagueNav = document.querySelector('.league-nav');
  const legend    = document.querySelector('.legend-section');
  if (leagueNav) leagueNav.style.display = 'none';
  if (legend)    legend.style.display    = 'none';

  // ── Sub-nav: visible for National + International ────
  const subNav = document.getElementById('subNav');
  // (28.06.2026, Lucas) Sub-Navi nur noch für die Daten-Ansichten Cards/Tracking.
  // Telegram + TikTok Studio sind in das „Mehr"-Menü gewandert (Desktop-Dropdown + Mobile-Sheet).
  const hasSubNav = ['national-cards', 'national-tracking', 'national-streaks',
                     'intl-cards', 'intl-tracking', 'intl-streaks'].includes(view);
  if (subNav) subNav.style.display = hasSubNav ? '' : 'none';

  // Sub-nav active buttons
  const isCards    = view.endsWith('-cards');
  const isTracking = view.endsWith('-tracking');
  const isStreaks  = view.endsWith('-streaks');
  const subCards    = document.getElementById('subCards');
  const subTracking = document.getElementById('subTracking');
  const subStreaks  = document.getElementById('subStreaks');
  if (subCards)    subCards.classList.toggle('active',    isCards);
  if (subTracking) subTracking.classList.toggle('active', isTracking);
  if (subStreaks)  subStreaks.classList.toggle('active',  isStreaks);

  // ── Top-nav active state ─────────────────────────────
  _TOP_NAV_IDS.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.remove('active');
  });
  const topNavMap = {
    'home':        'navHome',
    'national':    'navNational',
    'polybetting': 'navPolymarket',
    'polywallets': 'navPolyWallets',
    'betfair':     'navBetfair',
    'moneymap':    'navMoneyMap',
  };
  const activeNavId = topNavMap[_activeSection];
  if (activeNavId) {
    const el = document.getElementById(activeNavId);
    if (el) el.classList.add('active');
  }

  // ── „Mehr"-Menü (28.06.2026, Lucas): Heart/Status/Telegram/TikTok gebündelt ──
  // Desktop = Dropdown (#navMore + .top-more-menu), Mobile = Bottom-Sheet (.more-sheet).
  // Telegram/TikTok haben Section 'intl' → über die volle View (_activeView) matchen.
  const MORE_SECS  = ['intl', 'polytrading', 'sharp', 'heart', 'status', 'analyse'];   // 14.08.2026 (Lucas): Intl/Sharp/Poly-Trading ins Mehr
  const MORE_VIEWS = ['intl-studio'];   // Telegram lebt jetzt im Status-Tab (28.06.2026)
  const isMore = MORE_SECS.includes(_activeSection) || MORE_VIEWS.includes(_activeView);

  // Desktop: „Mehr"-Button aktiv nur für seine eigenen Einträge (Poly bleibt eigene Top-Buttons).
  const navMore = document.getElementById('navMore');
  if (navMore) navMore.classList.toggle('active', isMore);   // 14.08.2026 (Lucas): alle Mehr-Einträge markieren
  document.querySelectorAll('.top-more-menu .tm-item').forEach(b => {
    b.classList.toggle('active', b.getAttribute('data-view') === _activeView);
  });

  // Mobile: Bottom-Tabs — „Mehr" aktiv bei jeder „more"-View, sonst die passende Section.
  document.querySelectorAll('.bottom-nav .bn-btn').forEach(b => {
    const on = b.id === 'bnMore'
      ? isMore
      : (!isMore && b.getAttribute('data-sec') === _activeSection);
    b.classList.toggle('active', on);
  });
  // Sheet-Einträge per data-sec ODER data-view markieren.
  document.querySelectorAll('.more-sheet .ms-btn').forEach(b => {
    const sec = b.getAttribute('data-sec'), vw = b.getAttribute('data-view');
    b.classList.toggle('active', (!!sec && sec === _activeSection) || (!!vw && vw === _activeView));
  });

  // ── Sharp Radar: activate sharp league button ────────
  if (view === 'sharp') {
    document.querySelectorAll('.league-btn').forEach(b => b.classList.remove('active'));
    const sharpBtn = document.querySelector('.league-btn[data-league="sharp"]');
    if (sharpBtn) sharpBtn.classList.add('active');
    window._currentLeague = 'sharp';
    if (typeof renderSharpRadar === 'function') renderSharpRadar();
  }

  // ── Callbacks ────────────────────────────────────────
  if (view === 'status')            { initStatus(); if (typeof initTelegramPanel === 'function') initTelegramPanel(); }
  if (view === 'polybetting')       initPolymarket();
  if (view === 'polytrading')       initPolyTrader();
  if (view === 'polywallets'  && typeof initPolyWallets === 'function') initPolyWallets();
  if (view === 'betfair') {
    if (typeof window._bfLoad === 'function') window._bfLoad();
    const p = document.getElementById('betfairRadarPanel');
    if (p && typeof window._renderBetfairRadar === 'function') p.innerHTML = window._renderBetfairRadar();
  }
  if (view === 'moneymap'     && typeof initMoneyMap === 'function') initMoneyMap();
  if (view === 'analyse'      && typeof initSignalCheck === 'function') initSignalCheck();
  if (view === 'stakeradar'   && typeof initStakeRadar === 'function') initStakeRadar();
  // (25.06.2026, Lucas: Liga auf WM-Stack) National-Views laufen jetzt auf dem
  // bewährten WM-Renderer/Tracking (liest liga-data.json) statt statischem
  // renderer.js-Output bzw. initResultsV2.
  if ((view === 'national-streaks' || view === 'intl-streaks') && typeof initStreaks === 'function') initStreaks(_activeSection);
  if (view === 'home'              && typeof window._mdLoad        === 'function') window._mdLoad();
  if (view === 'national-cards'    && typeof initNationalCards    === 'function') initNationalCards();
  if (view === 'national-tracking' && typeof initNationalTracking === 'function') initNationalTracking();
  if (view === 'intl-cards'        && typeof initIntlCards     === 'function') initIntlCards();
  if (view === 'intl-tracking'     && typeof initIntlTracking  === 'function') initIntlTracking();
  if (view === 'intl-wm2026'       && typeof initWm2026        === 'function') initWm2026();
  if (view === 'intl-studio'       && typeof initTiktokStudio  === 'function') initTiktokStudio();
}

// Sub-nav click: navigate within current section
function showSubView(sub) {
  showView(_activeSection + '-' + sub);
}

// Mobile „Mehr"-Sheet auf/zu (28.06.2026, Lucas: Bottom-Nav)
function toggleMoreSheet() {
  const s = document.getElementById('moreSheet');
  if (s) s.classList.toggle('open');
}

// Desktop „Mehr ▾"-Dropdown auf/zu (28.06.2026, Lucas)
function toggleTopMore(ev) {
  if (ev) ev.stopPropagation();
  const m = document.getElementById('topMoreMenu');
  if (m) m.classList.toggle('open');
}
function closeTopMore() {
  const m = document.getElementById('topMoreMenu');
  if (m) m.classList.remove('open');
}
// Klick außerhalb schließt das Dropdown
if (typeof document !== 'undefined') {
  document.addEventListener('click', function (e) {
    const wrap = document.getElementById('topNavMore');
    const menu = document.getElementById('topMoreMenu');
    if (menu && menu.classList.contains('open') && wrap && !wrap.contains(e.target)) {
      menu.classList.remove('open');
    }
  });
}

// Backward compat (called from some league-btn click handlers)
function showSharpRadar() { showView('sharp'); }

// ═══════════════════════════════════════════════════════
//  STATUS / DATA TAB
// ═══════════════════════════════════════════════════════

// ── Action logger (called by toolbar buttons) ──────────
function logDashboardAction(key) {
  try {
    const log = JSON.parse(localStorage.getItem('betedge_action_log') || '{}');
    log[key] = new Date().toISOString();
    localStorage.setItem('betedge_action_log', JSON.stringify(log));
  } catch(e) {}
}

// ── Helpers ─────────────────────────────────────────────
function _timeAgo(isoStr) {
  if (!isoStr) return '—';
  const diff = Date.now() - new Date(isoStr).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 2)   return 'gerade eben';
  if (m < 60)  return `vor ${m} Min`;
  const h = Math.floor(m / 60);
  if (h < 24)  return `vor ${h} Std`;
  return `vor ${Math.floor(h / 24)} Tagen`;
}

function _freshnessColor(isoStr) {
  if (!isoStr) return '#8b949e';
  const h = (Date.now() - new Date(isoStr).getTime()) / 3600000;
  if (h < 6)   return '#3fb950';   // green: fresh
  if (h < 24)  return '#f0c040';   // yellow: getting old
  return '#f85149';                 // red: stale
}

function _statusCard(icon, title, value, sub, color) {
  return `<div style="background:var(--card2);border:1px solid var(--border);border-radius:10px;padding:14px 16px;">
    <div style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px;">${icon} ${title}</div>
    <div style="font-size:15px;font-weight:700;color:${color || 'var(--text)'};margin-bottom:3px;">${value}</div>
    ${sub ? `<div style="font-size:11px;color:var(--muted);">${sub}</div>` : ''}
  </div>`;
}

function _quickLink(icon, label, url, color) {
  return `<a href="${url}" target="_blank" style="display:flex;align-items:center;gap:8px;background:var(--card2);border:1px solid var(--border);border-radius:10px;padding:12px 14px;text-decoration:none;color:${color || 'var(--text)'};font-size:13px;font-weight:600;transition:border-color .15s;" onmouseover="this.style.borderColor='${color || '#58a6ff'}'" onmouseout="this.style.borderColor='var(--border)'">
    <span style="font-size:18px;">${icon}</span>
    <div>
      <div>${label}</div>
      <div style="font-size:10px;color:var(--muted);font-weight:400;">GitHub Actions →</div>
    </div>
  </a>`;
}

// ── Status workflows section ─────────────────────────────
// Update 06.06.2026: WM-Pipeline komplett ergänzt, Liga-Workflows pausiert markiert
const _STATUS_WORKFLOWS = [
  // ── WM 2026 (aktiv) ─────────────────────────────────────
  { id: 'fetch-wm-data',     icon: '🌍', label: 'WM Daten',              color: '#00d4a1', desc: '5×/Tag · Picks + Form + Odds + Sharp Moves' },
  { id: 'manage-wm-poly',    icon: '💹', label: 'WM Poly Trading',       color: '#a78bfa', desc: '5×/Tag · Auto-Trigger + Sell + Health' },
  { id: 'poly-bets',         icon: '🟣', label: 'Polymarket Manual',     color: '#a78bfa', desc: 'On-Demand bei UI-Klick "Jetzt platzieren"' },
  { id: 'daily-wm-story',    icon: '🎬', label: 'WM Live-Story Engine',  color: '#4cc9f0', desc: 'Täglich 06:00 UTC · TikTok Hook+Info' },
  { id: 'daily-tiktok',      icon: '📱', label: 'Daily TikTok Cards',    color: '#4cc9f0', desc: 'Täglich 04:00 UTC · Hidden-Gem / Killer-Stat' },
  { id: 'daily-heartbeat',   icon: '🤖', label: 'Daily Heartbeat',       color: '#3fb950', desc: 'Täglich 06:00 UTC · System-Status an Trades' },
  { id: 'track-record-card', icon: '🏆', label: 'Track-Record-Card',     color: '#3fb950', desc: 'Täglich 19:00 UTC · ROI an Trades' },
  { id: 'telegram-wm-recap', icon: '📺', label: 'WM Tages-Recap',        color: '#f0c040', desc: 'Täglich 21:30 UTC · Recap an Public' },
  { id: 'kill-switch',       icon: '🛑', label: 'Kill-Switch (Mobile)',  color: '#f85149', desc: 'On-Demand · Trading sofort pausieren' },
  // ── Liga (pausiert während WM) ──────────────────────────
  { id: 'update-dashboard',  icon: '⏸️', label: 'Liga Dashboard',         color: '#8b949e', desc: 'PAUSIERT während WM · Liga-Picks' },
  { id: 'fetch-prematch',    icon: '⏸️', label: 'Liga Pre-Match',         color: '#8b949e', desc: 'PAUSIERT während WM' },
  { id: 'fetch-results',     icon: '⏸️', label: 'Liga Ergebnisse',        color: '#8b949e', desc: 'PAUSIERT während WM' },
];

const _STATUS_FILES = [
  // ── WM Pick-Generierung ─────────────────────────────────
  { file: 'wm2026-data.json',       icon: '🌍', label: 'WM Picks + Form + H2H',  desc: 'via fetch-wm-data.yml · 5×/Tag' },
  { file: 'wm2026-odds-history.json', icon: '📈', label: 'Pinnacle Odds-History', desc: 'Opening vs Closing Tracking' },
  { file: 'wm_poly_prices.json',    icon: '💹', label: 'Polymarket Prices+Edges', desc: 'Pinnacle vs Polymarket Drift' },
  { file: 'pick_validation_report.json', icon: '🔍', label: 'Validator Report',     desc: 'via validate_wm_picks.py' },
  { file: 'pick_changes_log.json',  icon: '🔄', label: 'Pick-Changes Log',       desc: 'Daily diff vs previous run' },
  // ── WM Trading ──────────────────────────────────────────
  { file: 'wm_poly_balance.json',   icon: '💰', label: 'Polymarket Balance',     desc: 'USDC verfügbar' },
  { file: 'wm_auto_bets_placed.json', icon: '🤖', label: 'Auto-Bets platziert',  desc: 'Alle automatisch ausgelösten Trades' },
  { file: 'wm_results.json',        icon: '📊', label: 'P&L + CLV Tracking',     desc: 'via resolve_wm_results.py' },
  { file: 'position_health.json',   icon: '🩺', label: 'Position-Health-Score',  desc: '4-Faktor Health pro offenem Trade' },
  { file: 'wm_kill_switch.json',    icon: '🛑', label: 'Kill-Switch State',      desc: 'enabled: true/false' },
  // ── WM Content ──────────────────────────────────────────
  { file: 'wm_story_proposals.json', icon: '🎬', label: 'Story-Engine Vorschläge', desc: 'Tägliche Story-Angle-Scores' },
  { file: 'wm_live_story_state.json', icon: '📝', label: 'Story Dedup-State',     desc: 'Welche Entities zuletzt gepostet' },
  { file: 'telegram-log.json',      icon: '📨', label: 'Telegram-Send-Log',       desc: 'Alle versendeten Nachrichten' },
  { file: 'wm_sharp_dedup.json',    icon: '📡', label: 'Sharp-Move Dedup',        desc: 'Anti-Spam für Sharp-Alerts' },
  { file: 'steam_lag_log.json',     icon: '🔥', label: 'Steam-Lag Log',           desc: 'Pinnacle-vs-Polymarket Edges' },
];

const _STATUS_ACTIONS = [
  { key: 'picks_saved',        icon: '💾', label: 'Picks speichern',    color: '#3fb950' },
  { key: 'wm_picks_refresh',   icon: '🔄', label: 'WM Picks reload',    color: '#00d4a1' },
  { key: 'poly_trader_open',   icon: '💹', label: 'Trade-Cockpit',      color: '#a78bfa' },
  { key: 'story_preview',      icon: '🎬', label: 'Story-Vorschau',     color: '#4cc9f0' },
];

const _REPO = 'blummabet/Betting-Dashboard';

let _statusLoaded = false;

function toggleValidatorDetails() {
  const box = document.getElementById('validatorBannerIssues');
  const btn = document.getElementById('validatorBannerToggle');
  const open = box.style.display !== 'none';
  box.style.display = open ? 'none' : 'block';
  btn.textContent   = open ? 'Details anzeigen' : 'Details ausblenden';
}

async function initStatus() {
  if (_statusLoaded) return;
  _statusLoaded = true;

  // ── Section 0: WM Live-Health-Engine (ersetzt alten Liga-Validator-Banner) ──
  // Der frühere VALIDATOR_SUMMARY-Banner kam aus der Liga-Pipeline und war für
  // die WM unbrauchbar. Jetzt: runStatusPage() (status-checks.js) rendert Verdict,
  // Live-Probleme, Server-Readiness, Feed-Frische und Signal-Matrix.
  if (typeof runStatusPage === 'function') runStatusPage();

  const vs = null;
  if (vs) {
    const banner  = document.getElementById('validatorBanner');
    const icon    = document.getElementById('validatorBannerIcon');
    const title   = document.getElementById('validatorBannerTitle');
    const sub     = document.getElementById('validatorBannerSub');
    const counts  = document.getElementById('validatorBannerCounts');
    const list    = document.getElementById('validatorBannerList');
    const issBox  = document.getElementById('validatorBannerIssues');
    const ts      = document.getElementById('validatorBannerTs');

    const hasErr  = vs.errors > 0;
    const hasWarn = vs.warnings > 0;

    // Background & icon based on severity
    if (hasErr) {
      banner.style.background = 'linear-gradient(135deg,#2d1a1a,#3a1f1f)';
      banner.style.border     = '1px solid #f85149';
      banner.style.color      = '#f8f8f2';
      icon.textContent        = '🔴';
      title.textContent       = `${vs.errors} kritische Fehler gefunden`;
    } else if (hasWarn) {
      banner.style.background = 'linear-gradient(135deg,#2a2010,#332815)';
      banner.style.border     = '1px solid #d29922';
      banner.style.color      = '#f8f8f2';
      icon.textContent        = '🟡';
      title.textContent       = `${vs.warnings} Warnungen — manuelle Prüfung empfohlen`;
    } else {
      banner.style.background = 'linear-gradient(135deg,#0d2318,#112b1e)';
      banner.style.border     = '1px solid #3fb950';
      banner.style.color      = '#f8f8f2';
      icon.textContent        = '✅';
      title.textContent       = 'Alle Picks logisch konsistent';
    }

    sub.textContent = `${vs.checked} Spiele geprüft (nächste 3 Tage)`;
    ts.textContent  = `Letzter Check: ${vs.timestamp}`;

    // Count badges
    const badge = (n, col, lbl) => n > 0
      ? `<div style="background:rgba(0,0,0,.3);border:1px solid ${col};border-radius:8px;padding:5px 12px;text-align:center;min-width:52px;">
           <div style="font-size:16px;font-weight:700;color:${col};">${n}</div>
           <div style="font-size:10px;opacity:.7;">${lbl}</div>
         </div>` : '';
    counts.innerHTML = badge(vs.errors,'#f85149','Fehler') + badge(vs.warnings,'#d29922','Warn.') + badge(vs.infos,'#58a6ff','Hinw.');

    // Issue list (only errors + warnings for the banner)
    const relevant = (vs.issues || []).filter(i => i.severity === 'ERROR' || i.severity === 'WARN');
    const SEV_ICON = { ERROR: '🔴', WARN: '🟡', INFO: '🔵' };
    if (relevant.length > 0) {
      list.innerHTML = relevant.map(i =>
        `<div style="display:flex;gap:10px;font-size:12px;align-items:flex-start;padding:6px 0;border-bottom:1px solid rgba(255,255,255,.07);">
           <span style="flex-shrink:0;">${SEV_ICON[i.severity]||'⚪'}</span>
           <div>
             <span style="font-weight:600;">${i.home} vs ${i.away}</span>
             <span style="opacity:.6;margin-left:6px;">${i.date} · ${i.league}</span><br>
             <span style="opacity:.8;">[${i.code}] ${i.msg}</span>
           </div>
         </div>`
      ).join('');
      issBox.style.display = 'none'; // collapsed by default
    }

    banner.style.display = 'block';
  }

  // ── Section 1: Workflow badges ────────────────────────
  const wfEl = document.getElementById('statusWorkflows');
  wfEl.innerHTML = _STATUS_WORKFLOWS.map(w => {
    const badgeUrl = `https://github.com/${_REPO}/actions/workflows/${w.id}.yml/badge.svg`;
    const runUrl   = `https://github.com/${_REPO}/actions/workflows/${w.id}.yml`;
    return `<a href="${runUrl}" target="_blank" style="display:block;background:var(--card2);border:1px solid var(--border);border-radius:10px;padding:14px 16px;text-decoration:none;">
      <div style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px;">${w.icon} ${w.label}</div>
      <div style="margin-bottom:6px;"><img src="${badgeUrl}" alt="${w.label}" style="height:20px;border-radius:4px;" onerror="this.style.display='none';this.nextElementSibling.style.display='inline'"><span style="display:none;font-size:11px;color:#f85149;">Badge nicht verfügbar</span></div>
      <div style="font-size:11px;color:var(--muted);">${w.desc}</div>
    </a>`;
  }).join('');

  // ── Section 2 (Feed-Frische) + Signal-Matrix + Verdict + Probleme ──────
  // → komplett in runStatusPage() (status-checks.js), oben aufgerufen.
  //   Nutzt eingebettete Daten-Timestamps statt GitHub-API (kein Rate-Limit,
  //   spiegelt echte Daten-Frische statt Commit-Zeit).

  // ── Section 4: Quick links to trigger workflows ───────
  document.getElementById('statusQuickLinks').innerHTML = _STATUS_WORKFLOWS.map(w =>
    _quickLink(w.icon, w.label,
      `https://github.com/${_REPO}/actions/workflows/${w.id}.yml`,
      w.color)
  ).join('');

  // ── Section A: WM Health-Dashboard (Live-Kennzahlen) ──
  loadWmControlCenter();
  // Auto-Refresh every 60s while on Status-Tab
  if (!window._ccInterval) {
    window._ccInterval = setInterval(() => {
      if (document.getElementById('statusPanel')?.style.display !== 'none') {
        loadWmControlCenter();
        if (typeof runStatusPage === 'function') runStatusPage(true);
      }
    }, 60000);
  }

  // ── Section B: Telegram-Log (letzte 15 Sends) ─────────
  loadTelegramLog();
}


  // [validator functions] → validator.js
  // buildValidatorDates(), runPicksValidator(), renderValidatorOutput(), copyValidatorOutput()


// ═══════════════════════════════════════════════════════
//  WM CONTROL CENTER — Status-Tab Live-Health-Dashboard
// ═══════════════════════════════════════════════════════
async function loadWmControlCenter() {
  const grid = document.getElementById('cc_grid');
  const tsEl = document.getElementById('cc_lastRefresh');
  if (!grid) return;

  // Parallel fetch aller Health-relevanten Files
  const [wmData, balance, autoBets, ks, health, results] = await Promise.all([
    fetch('wm2026-data.json?t=' + Date.now()).then(r => r.ok ? r.json() : null).catch(() => null),
    fetch('wm_poly_balance.json?t=' + Date.now()).then(r => r.ok ? r.json() : null).catch(() => null),
    fetch('wm_auto_bets_placed.json?t=' + Date.now()).then(r => r.ok ? r.json() : null).catch(() => null),
    fetch('wm_kill_switch.json?t=' + Date.now()).then(r => r.ok ? r.json() : null).catch(() => null),
    fetch('position_health.json?t=' + Date.now()).then(r => r.ok ? r.json() : null).catch(() => null),
    fetch('wm_results.json?t=' + Date.now()).then(r => r.ok ? r.json() : null).catch(() => null),
  ]);

  // ── Stats berechnen ──
  let betCount = 0, abwCount = 0, watchCount = 0;
  if (wmData?.picks) {
    for (const plist of Object.values(wmData.picks)) {
      if (!Array.isArray(plist)) continue;
      for (const p of plist) {
        if (p.verdict === 'BET') betCount++;
        else if (p.verdict === 'ABWÄGEN') abwCount++;
        else if (p.verdict === 'WATCH') watchCount++;
      }
    }
  }

  const balanceUsdc = balance?.total ?? balance?.usdc ?? null;
  const balanceColor = balanceUsdc === null ? '#8b949e'
    : balanceUsdc >= 100 ? '#3fb950'
    : balanceUsdc >= 20 ? '#e3b341'
    : '#f85149';

  // Bets heute / total
  const bets = autoBets?.bets || [];
  const today = new Date().toISOString().slice(0, 10);
  const betsToday = bets.filter(b => (b.placedAt || '').slice(0, 10) === today).length;
  const stakeToday = bets.filter(b => (b.placedAt || '').slice(0, 10) === today)
    .reduce((s, b) => s + (parseFloat(b.stake) || 0), 0);

  // Kill-Switch
  // 25.08.2026 (Audit-Befund 15): `ks` ist null, wenn die Datei nicht geladen werden konnte —
  // vorher ergab das 🟢 LIVE. Die Python-Seite ist an derselben Stelle fail-closed (Korruption =
  // Stop); das Dashboard behauptete das Gegenteil. Unbekannt ist jetzt ein eigener Zustand.
  const ksUnknown = !ks;
  const ksOn = ks?.enabled !== false;   // default true (active), sobald die Datei da ist
  const ksLabel = ksUnknown ? '❔ UNBEKANNT' : ksOn ? '🟢 LIVE' : '🔴 PAUSE';
  const ksColor = ksUnknown ? '#e3b341' : ksOn ? '#3fb950' : '#f85149';

  // Position-Health
  // Dasselbe hier: der Monitor schreibt seit 25.08. ein `error`-Feld, wenn er die Wett-Datei nicht
  // lesen konnte. „Keine offenen" und „ich weiss es nicht" sind zwei verschiedene Aussagen.
  const healthUnknown = !health || !!health.error;
  const positions = health?.positions || [];
  const critical = positions.filter(p => (p.status === 'critical' || p.status === 'warning')).length;
  const healthColor = healthUnknown ? '#e3b341'
                    : positions.length === 0 ? '#8b949e' : critical > 0 ? '#f85149' : '#3fb950';

  // P&L
  const totalPnl = results?.summary?.totalPnl ?? 0;
  const roi = results?.summary?.roi ?? 0;
  const pnlColor = totalPnl > 0 ? '#3fb950' : totalPnl < 0 ? '#f85149' : '#8b949e';

  const stat = (icon, lbl, val, color, sub) => `
    <div style="background:rgba(0,0,0,0.30);border:1px solid var(--border);border-radius:10px;padding:12px 14px;">
      <div style="font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px;">${icon} ${lbl}</div>
      <div style="font-size:20px;font-weight:800;color:${color};line-height:1.1;">${val}</div>
      <div style="font-size:10px;color:var(--muted);margin-top:3px;">${sub || ''}</div>
    </div>`;

  grid.innerHTML = [
    stat('🎯', 'Aktive Picks', `${betCount}`, '#00d4a1', `BET · ${abwCount} ABWÄGEN · ${watchCount} WATCH`),
    stat('🛑', 'Kill-Switch', ksLabel, ksColor, ks?.reason ? ks.reason.slice(0, 28) : 'Trading-Status'),
    stat('💰', 'Polymarket Balance',
         balanceUsdc !== null ? `$${balanceUsdc.toFixed(2)}` : '—',
         balanceColor,
         balance?.address ? balance.address.slice(0, 10) + '…' : 'USDC verfügbar'),
    stat('🤖', 'Bets heute', `${betsToday}/8`, betsToday >= 7 ? '#f85149' : '#3fb950',
         `$${stakeToday.toFixed(2)} / $50 max`),
    stat('🩺', 'Position-Health',
         healthUnknown ? '❔' : positions.length > 0 ? `${positions.length - critical}/${positions.length}` : '—',
         healthColor,
         healthUnknown ? 'Wett-Datei nicht lesbar — Positionen unbekannt'
           : positions.length === 0 ? 'Keine offenen' : `${critical} kritisch`),
    stat('📊', 'P&L (resolved)',
         results?.summary ? `${totalPnl >= 0 ? '+' : ''}$${totalPnl.toFixed(2)}` : '—',
         pnlColor,
         results?.summary ? `ROI ${roi >= 0 ? '+' : ''}${roi.toFixed(1)}%` : 'noch keine'),
  ].join('');

  if (tsEl) {
    const now = new Date();
    tsEl.textContent = `Aktualisiert ${now.toLocaleTimeString('de-AT', {hour:'2-digit',minute:'2-digit'})}`;
  }
}

async function loadTelegramLog() {
  const el = document.getElementById('cc_tgLog');
  const cnt = document.getElementById('tg_log_count');
  if (!el) return;

  try {
    const r = await fetch('telegram-log.json?t=' + Date.now());
    if (!r.ok) { el.innerHTML = '<div style="color:#f85149;padding:14px;text-align:center;">telegram-log.json nicht erreichbar</div>'; return; }
    const log = await r.json();
    if (!Array.isArray(log) || log.length === 0) {
      el.innerHTML = '<div style="color:var(--muted);padding:14px;text-align:center;">Keine Logs</div>';
      return;
    }

    if (cnt) cnt.textContent = `${log.length} total`;

    // Letzte 15, neueste zuerst
    const PUB_ID = '-1003819239615';
    const last15 = [...log].reverse().slice(0, 15);

    const TYPE_ICON = {
      morning_card: '🌅', recap: '📊', sharp_alert: '📡', steam_alert: '🔥',
      player_spotlight: '🌟', wm_live_story: '🎬', cumul_alert: '📈',
      pick_changes_digest: '🔄', track_record: '🏆', auto_bet: '🤖', sell_alert: '💰',
      heartbeat: '💓',
    };
    const TYPE_COLOR = {
      morning_card: '#00d4a1', recap: '#f0c040', sharp_alert: '#ff8c00',
      steam_alert: '#f85149', player_spotlight: '#a78bfa', wm_live_story: '#4cc9f0',
      cumul_alert: '#ff8c00', pick_changes_digest: '#a78bfa', track_record: '#3fb950',
      auto_bet: '#3fb950', sell_alert: '#e3b341',
    };

    el.innerHTML = last15.map(e => {
      const icon = TYPE_ICON[e.type] || '📱';
      const color = TYPE_COLOR[e.type] || '#8b949e';
      const dt = e.sentAt ? new Date(e.sentAt).toLocaleString('de-AT',
        { day:'2-digit', month:'2-digit', hour:'2-digit', minute:'2-digit' }) : '?';
      const isPublic = String(e.chatId || '') === PUB_ID;
      const chanBadge = isPublic
        ? '<span style="background:rgba(248,81,73,0.10);border:1px solid rgba(248,81,73,0.30);color:#f85149;font-size:9px;font-weight:700;padding:2px 6px;border-radius:4px;">🌐 PUBLIC</span>'
        : '<span style="background:rgba(63,185,80,0.10);border:1px solid rgba(63,185,80,0.30);color:#3fb950;font-size:9px;font-weight:700;padding:2px 6px;border-radius:4px;">🔒 PRIVAT</span>';
      const preview = (e.preview || '').replace(/<[^>]+>/g, '').slice(0, 80);
      return `<div style="display:flex;gap:10px;align-items:center;padding:8px 12px;background:var(--card2);border:1px solid var(--border);border-radius:8px;">
        <span style="font-size:16px;flex-shrink:0;">${icon}</span>
        <span style="color:${color};font-weight:700;font-size:11px;min-width:120px;text-transform:uppercase;letter-spacing:.3px;">${(e.type||'?').replace(/_/g,' ')}</span>
        ${chanBadge}
        <span style="color:var(--muted);font-size:11px;font-family:monospace;flex-shrink:0;">${dt}</span>
        <span style="color:var(--text);font-size:11px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${preview}">${preview}</span>
      </div>`;
    }).join('');
  } catch(e) {
    el.innerHTML = `<div style="color:#f85149;padding:14px;text-align:center;">Fehler: ${e.message}</div>`;
  }
}

// ═══════════════════════════════════════════════════════
//  POLY TRADER TAB
// ═══════════════════════════════════════════════════════

let _polyTraderData = null;
let _polyTraderFilter = { signal: 'all', market: 'all', maxDays: 10, actionableOnly: false, hideSuspicious: true };
let _polyTraderSort = { col: 'signal_score', dir: -1 };

async function initPolyTrader() {
  const panel = document.getElementById('polyTraderPanel');
  if (!panel) return;
  panel.innerHTML = `<div style="text-align:center;padding:60px 20px;color:#6b7a8d">
    <div style="width:28px;height:28px;border:3px solid #ffffff10;border-top-color:#00d4a1;border-radius:50%;animation:spin .8s linear infinite;margin:0 auto 14px"></div>
    Lade Poly-Trader-Daten…
  </div>`;

  // Load WM prices in parallel with poly_trader_data.json
  const wmPromise = (typeof _loadWmPolyPriceCache === 'function')
    ? _loadWmPolyPriceCache()
    : Promise.resolve();

  try {
    const res = await fetch('poly_trader_data.json?_=' + Date.now());
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    _polyTraderData = await res.json();
  } catch(e) {
    // Still show WM table even if poly_trader_data.json fails
    await wmPromise;
    panel.innerHTML = `<div style="text-align:center;padding:40px 20px;color:#f85149">
      <div style="font-size:32px;margin-bottom:12px">⚠️</div>
      <div style="font-weight:700;margin-bottom:6px">Club-Daten nicht gefunden</div>
      <div style="font-size:12px;color:#6b7a8d">poly_trader_data.json fehlt — läuft nach dem nächsten GitHub Actions Workflow</div>
    </div>`;
    return;
  }

  await wmPromise;
  renderPolyTrader(panel);
}

function renderPolyTrader(panel) {
  if (!_polyTraderData) return;
  const candidates = Object.values(_polyTraderData.candidates || {});
  const updated = _polyTraderData.updated || '';

  // ── Summary stats ────────────────────────────────────────────────────────
  const buyCount     = candidates.filter(c => c.buy_signal === 'BUY').length;
  const watchCount   = candidates.filter(c => c.buy_signal === 'WATCH').length;
  const suspCount    = candidates.filter(c => c.suspicious_gap).length;
  const withPnl      = candidates.filter(c => c.obs_pnl_eur != null);
  const totalPnlEur  = withPnl.length ? withPnl.reduce((s,c) => s+(c.obs_pnl_eur||0), 0) : null;

  // ── Filter + sort ────────────────────────────────────────────────────────
  let rows = candidates.filter(c => {
    if (_polyTraderFilter.hideSuspicious && c.suspicious_gap) return false;
    if (_polyTraderFilter.actionableOnly && !c.is_actionable) return false;
    if (_polyTraderFilter.signal !== 'all') {
      // 'signal' filter now maps to buy_signal values too
      if (_polyTraderFilter.signal === 'BUY'   && c.buy_signal !== 'BUY')   return false;
      if (_polyTraderFilter.signal === 'WATCH' && c.buy_signal !== 'WATCH') return false;
      if (_polyTraderFilter.signal === 'BOTH'  && c.signal !== 'BOTH')      return false;
      if (_polyTraderFilter.signal === 'SHARP' && c.signal !== 'SHARP' && c.signal !== 'BOTH') return false;
      if (_polyTraderFilter.signal === 'CLV+'  && c.signal !== 'CLV+'  && c.signal !== 'BOTH') return false;
      if (_polyTraderFilter.signal === 'SUSP'  && !c.suspicious_gap)        return false;
    }
    if (_polyTraderFilter.market !== 'all' && c.market !== _polyTraderFilter.market) return false;
    if ((c.daysOut||0) > _polyTraderFilter.maxDays) return false;
    return true;
  });
  const { col, dir } = _polyTraderSort;
  rows.sort((a, b) => {
    let va = a[col] ?? -999, vb = b[col] ?? -999;
    if (typeof va === 'string') va = va.toLowerCase(), vb = (b[col]||'').toLowerCase();
    return va < vb ? dir : va > vb ? -dir : 0;
  });

  const allMarkets = [...new Set(candidates.map(c => c.market))].sort();

  // ── Helpers ──────────────────────────────────────────────────────────────
  function _buyBadge(buySig, suspicious) {
    if (suspicious) return `<span style="background:#2d1e0015;border:1px solid #e3b34150;color:#e3b341;font-size:10px;font-weight:700;padding:2px 7px;border-radius:6px;white-space:nowrap">⚠ PRÜFEN</span>`;
    if (!buySig) return '<span style="font-size:10px;color:#6b7a8d">—</span>';
    const cfg = {
      'BUY':   { bg:'#3fb95015', bc:'#3fb95040', col:'#3fb950', lbl:'▲ BUY' },
      'WATCH': { bg:'#e3b34115', bc:'#e3b34140', col:'#e3b341', lbl:'👁 WATCH' },
      'SKIP':  { bg:'#f8514915', bc:'#f8514940', col:'#f85149', lbl:'▽ SKIP' },
    }[buySig] || { bg:'#ffffff08', bc:'#ffffff15', col:'#8b9ab0', lbl: buySig };
    return `<span style="background:${cfg.bg};border:1px solid ${cfg.bc};color:${cfg.col};font-size:10px;font-weight:700;padding:2px 7px;border-radius:6px;white-space:nowrap">${cfg.lbl}</span>`;
  }
  function _signalBadge(sig, actionable) {
    if (!sig) return '<span style="font-size:10px;color:#6b7a8d">—</span>';
    const cfg = {
      'BOTH':  { bg:'#00d4a118', bc:'#00d4a140', col:'#00d4a1', lbl:'★ BOTH'  },
      'SHARP': { bg:'#58a6ff12', bc:'#58a6ff40', col:'#58a6ff', lbl:'⚡ SHARP' },
      'CLV+':  { bg:'#a78bfa12', bc:'#a78bfa40', col:'#a78bfa', lbl:'📐 CLV+'  },
    }[sig] || { bg:'#ffffff08', bc:'#ffffff15', col:'#8b9ab0', lbl: sig };
    return `<span style="background:${cfg.bg};border:1px solid ${cfg.bc};color:${cfg.col};font-size:10px;font-weight:700;padding:2px 7px;border-radius:6px;white-space:nowrap">${cfg.lbl}</span>`;
  }
  function _pp(pp, threshold=1) {
    if (pp == null) return '—';
    const col = pp > threshold ? '#3fb950' : pp < -threshold ? '#f85149' : '#8b9ab0';
    return `<span style="color:${col};font-weight:700">${pp > 0?'+':''}${pp.toFixed(1)}pp</span>`;
  }
  function _dirBadge(dir) {
    if (!dir) return '—';
    return dir === 'BUY_YES'
      ? `<span style="color:#3fb950;font-size:10px;font-weight:700;background:#3fb95015;border:1px solid #3fb95030;padding:2px 6px;border-radius:5px">BUY YES ▲</span>`
      : `<span style="color:#f85149;font-size:10px;font-weight:700;background:#f8514915;border:1px solid #f8514930;padding:2px 6px;border-radius:5px">BUY NO ▼</span>`;
  }
  function _tierBadge(tier) {
    const cfg = { 1: { col:'#3fb950', lbl:'T1' }, 2: { col:'#e3b341', lbl:'T2' }, 3: { col:'#f85149', lbl:'T3' } };
    const c = cfg[tier] || { col:'#8b9ab0', lbl:'?' };
    return `<span title="Liquiditäts-Tier" style="color:${c.col};font-size:10px;font-weight:700;opacity:.8">${c.lbl}</span>`;
  }
  function _sortTh(label, colKey, center=false) {
    const active = _polyTraderSort.col === colKey;
    const arrow = active ? (_polyTraderSort.dir === -1 ? ' ↓' : ' ↑') : '';
    return `<th style="padding:10px 8px;cursor:pointer;user-select:none;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.4px;color:${active?'#00d4a1':'#6b7a8d'};text-align:${center?'center':'left'}" onclick="ptSort('${colKey}')">${label}${arrow}</th>`;
  }

  // ── Price cell helpers ───────────────────────────────────
  function _priceRow(label, val, bold=false) {
    if (val == null) return '';
    return `<div style="display:flex;gap:4px;align-items:baseline"><span style="color:#4a5568;font-size:10px;min-width:30px">${label}</span><span style="color:${bold?'#e8edf3':'#8b9ab0'};font-weight:${bold?'700':'400'}">${val.toFixed(1)}%</span></div>`;
  }
  function _priceDelta(val, threshold=0) {
    if (val == null) return '';
    const col = val > threshold ? '#3fb950' : val < -threshold ? '#f85149' : '#6b7a8d';
    return `<div style="color:${col};font-size:10px;margin-top:1px">${val>0?'+':''}${val.toFixed(1)}pp</div>`;
  }
  function _closedBadge() {
    return `<span style="font-size:9px;background:#1e2d3d;color:#6b7a8d;border-radius:4px;padding:1px 5px;margin-left:2px">CLOSED</span>`;
  }

  const tableRows = rows.map(c => {
    const kDate = c.kickoffDate ? c.kickoffDate.slice(5).replace('-','.') : '—';
    const dLbl  = (c.daysOut||0) <= 0
      ? `<span style="color:#f85149;font-size:10px">PAST</span>`
      : (c.daysOut||0) === 1
        ? `<span style="color:#e3b341;font-size:10px">Morgen</span>`
        : `<span style="font-size:10px;color:#6b7a8d">${c.daysOut}d</span>`;

    // Row highlighting: BUY = subtle green, suspicious = orange border
    let rowBg = '';
    if (c.suspicious_gap) rowBg = 'border-left:2px solid #e3b34150;opacity:.7';
    else if (c.buy_signal === 'BUY') rowBg = 'background:rgba(63,185,80,.04);border-left:2px solid #3fb95040';
    else if (c.buy_signal === 'WATCH') rowBg = 'background:rgba(227,179,65,.02);border-left:2px solid #e3b34125';

    const polyLink = c.eventUrl ? `<a href="${c.eventUrl}" target="_blank" style="color:#58a6ff;font-size:10px;margin-left:4px;opacity:.7">🔗</a>` : '';

    // Gap color: green = Poly underpriced (positive gap = BUY), red = overpriced
    const gapVal = c.gap_pp;
    const gapCol = gapVal == null ? '#6b7a8d'
      : c.suspicious_gap ? '#e3b341'
      : gapVal >= 5  ? '#3fb950'
      : gapVal >= 2  ? '#a8d48a'
      : gapVal <= -2 ? '#f85149'
      : '#6b7a8d';

    const obsCol = (c.obs_pnl_pp||0) > 0 ? '#3fb950' : (c.obs_pnl_pp||0) < 0 ? '#f85149' : '#6b7a8d';
    const eurCol = (c.obs_pnl_eur||0) > 0 ? '#3fb950' : (c.obs_pnl_eur||0) < 0 ? '#f85149' : '#6b7a8d';

    // Bookie cell: Open → Cur [→ Close] + Δ
    const bookieCell = `<div style="font-size:11px;line-height:1.5">
      ${_priceRow('Open', c.bookie_open_impl)}
      ${_priceRow('Cur', c.bookie_cur_impl, true)}
      ${c.bookie_close != null ? _priceRow('Close', c.bookie_close) + _closedBadge() : ''}
      ${_priceDelta(c.bookie_move_pp, 5)}
    </div>`;

    // Poly cell: Open → Cur [→ Close] + Δ
    const polyCell = `<div style="font-size:11px;line-height:1.5">
      ${_priceRow('Open', c.poly_open)}
      ${_priceRow('Cur', c.poly_cur, true)}
      ${c.poly_close != null ? _priceRow('Close', c.poly_close) + _closedBadge() : ''}
      ${_priceDelta(c.poly_delta_pp)}
    </div>`;

    // Obs P&L: pp + € stacked
    const obsCell = `<div style="text-align:center;line-height:1.6">
      <div style="color:${obsCol};font-weight:700;font-size:12px">${c.obs_pnl_pp != null ? (c.obs_pnl_pp>0?'+':'')+c.obs_pnl_pp.toFixed(1)+'pp' : '—'}</div>
      ${c.obs_pnl_eur != null ? `<div style="color:${eurCol};font-size:11px">${c.obs_pnl_eur>0?'+':''}€${c.obs_pnl_eur.toFixed(2)}</div>` : ''}
      ${c.obs_closed ? `<div style="font-size:9px;color:#6b7a8d;margin-top:1px">geschlossen</div>` : ''}
    </div>`;

    return `<tr style="border-bottom:1px solid #1a2535;${rowBg}">
      <td style="padding:9px 8px;font-weight:600;white-space:nowrap;font-size:12px">${_tierBadge(c.liq_tier)} ${c.home} vs ${c.away}${polyLink}</td>
      <td style="padding:9px 8px;white-space:nowrap">${kDate} ${dLbl}</td>
      <td style="padding:9px 8px;font-size:11px;color:#8b9ab0">${c.market}</td>
      <td style="padding:9px 8px">${bookieCell}</td>
      <td style="padding:9px 8px">${polyCell}</td>
      <td style="padding:9px 8px;text-align:center"><span style="color:${gapCol};font-weight:700">${gapVal != null ? (gapVal>0?'+':'')+gapVal.toFixed(1)+'pp' : '—'}${c.suspicious_gap ? ' ⚠' : ''}</span></td>
      <td style="padding:9px 8px;text-align:center">${_buyBadge(c.buy_signal, c.suspicious_gap)}</td>
      <td style="padding:9px 8px;text-align:center">${_signalBadge(c.signal, c.is_actionable)}</td>
      <td style="padding:9px 8px">${obsCell}</td>
    </tr>`;
  }).join('');

  const noRows = rows.length === 0
    ? `<tr><td colspan="9" style="text-align:center;padding:40px;color:#6b7a8d">Keine Kandidaten für aktuelle Filter</td></tr>` : '';

  const marketOptions = allMarkets.map(m =>
    `<option value="${m}" ${_polyTraderFilter.market===m?'selected':''}>${m}</option>`
  ).join('');

  // ── WM 2026 Market Table — Trading tab shows ONLY WM during WM season ──
  const wmTableHtml = (typeof _renderWmMarketTable === 'function')
    ? `<div id="wmMarketSection">${_renderWmMarketTable()}</div>`
    : '';

  // During WM season: show only WM table, skip club candidates
  // ─────────────────────────────────────────────────────────────
  // Trading-Cockpit + Auto-Trader-Config OBEN ANZEIGEN (kommt aus polymarket-tab.js
  // — die Funktionen renderTradingCockpit/renderAutoTraderConfig sind global verfügbar
  // weil polymarket-tab.js vor ui.js geladen wird). Cockpit lädt sich async via
  // SVG-onload-Trigger sobald HTML im DOM ist.
  const cockpitBlock = (typeof renderAutoTraderConfig === 'function')
    ? `
    <div id="tradingCockpit">
      <div style="background:#161b22;border:1px solid #30363d;border-radius:14px;padding:30px;margin-bottom:16px;text-align:center;color:#8b949e;font-size:13px">
        ⚙️ Cockpit lädt Live-Daten…
      </div>
    </div>
    <svg xmlns="http://www.w3.org/2000/svg" width="1" height="1" style="display:none" onload="if(window.refreshCockpit && !window._cockpitLoading){window._cockpitLoading=true;refreshCockpit().finally(()=>{window._cockpitLoading=false;});}"></svg>
    ${renderAutoTraderConfig()}
    `
    : '';

  // Position-Health-Block (lädt async, rendert oben über Cockpit)
  const healthBlock = `
    <div id="positionHealthBlock">
      <div style="background:#161b22;border:1px solid #30363d;border-radius:14px;padding:14px;margin-bottom:14px;color:#8b949e;font-size:12px;text-align:center;">
        🩺 Position-Health-Monitor lädt…
      </div>
    </div>
    <svg xmlns="http://www.w3.org/2000/svg" width="1" height="1" style="display:none" onload="if(window.loadPositionHealth && !window._healthLoading){window._healthLoading=true;loadPositionHealth().finally(()=>{window._healthLoading=false;});}"></svg>
  `;

  panel.innerHTML = healthBlock + cockpitBlock;   // 22.08.2026 (Lucas): WM-Markttabelle raus — Liga-Cockpit ist der Live-Stand

  // Fix 08.06.2026: SVG-onload-Trigger feuern in modernen Browsern nicht
  // mehr zuverlässig wenn via innerHTML eingefügt (Security-Hardening).
  // Direkter Aufruf via setTimeout ist robuster. Plus Retry-Loop falls
  // polymarket-tab.js asynchron lädt und window.refreshCockpit zum ersten
  // Tick noch undefined ist. Max 20 Retries × 100ms = 2s.
  // Idempotent dank _cockpitLoading/_healthLoading-Flag.
  (function bootCockpitLoaders(attempt = 0) {
    const cockpitReady = typeof window.refreshCockpit === 'function';
    const healthReady  = typeof window.loadPositionHealth === 'function';
    if (cockpitReady && !window._cockpitLoading) {
      window._cockpitLoading = true;
      console.log('[Cockpit-Boot] refreshCockpit() wird gerufen (attempt ' + attempt + ')');
      window.refreshCockpit().finally(() => { window._cockpitLoading = false; });
    }
    if (healthReady && !window._healthLoading) {
      window._healthLoading = true;
      console.log('[Cockpit-Boot] loadPositionHealth() wird gerufen (attempt ' + attempt + ')');
      window.loadPositionHealth().finally(() => { window._healthLoading = false; });
    }
    if ((!cockpitReady || !healthReady) && attempt < 20) {
      setTimeout(() => bootCockpitLoaders(attempt + 1), 100);
    } else if (!cockpitReady || !healthReady) {
      console.warn('[Cockpit-Boot] Loader-Funktionen nicht gefunden nach 2s — Frontend-Code unvollständig?',
        { cockpitReady, healthReady });
    }
  })();

  return; // ← remove this line after WM season to restore club table

  panel.innerHTML = wmTableHtml + `
<!-- ── Observer Mode Banner ─────────────────────────────── -->
<div style="background:linear-gradient(135deg,#0a1f18,#0a1428);border:1px solid #00d4a125;border-radius:14px;padding:16px 20px;margin-bottom:20px;display:flex;align-items:center;gap:14px;flex-wrap:wrap">
  <div style="font-size:28px;flex-shrink:0">👁</div>
  <div style="flex:1;min-width:200px">
    <div style="font-size:13px;font-weight:700;color:#00d4a1;margin-bottom:3px">Observer Mode — Simuliert, kein echtes Geld</div>
    <div style="font-size:12px;color:#6b7a8d;line-height:1.5">Poly-Preise werden stündlich gespeichert. Nach 2–3 Wochen Daten → Auto-Trade mit €1/Signal aktiviert.</div>
  </div>
  <div style="text-align:right;flex-shrink:0">
    <div style="font-size:10px;color:#6b7a8d">Letztes Update</div>
    <div style="font-size:12px;color:#8b9ab0;font-weight:600">${updated ? new Date(updated).toLocaleString('de-AT',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}) : '—'}</div>
  </div>
</div>

<!-- ── Summary Stats ──────────────────────────────────────── -->
<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:20px">
  <div style="background:#0a1a0a;border:1px solid #3fb95040;border-radius:12px;padding:14px;text-align:center;cursor:pointer" onclick="ptFilterBuy('BUY')">
    <div style="font-size:26px;font-weight:800;color:#3fb950">${buyCount}</div>
    <div style="font-size:11px;color:#6b7a8d;margin-top:3px">▲ BUY Signale</div>
  </div>
  <div style="background:#0f1419;border:1px solid #e3b34125;border-radius:12px;padding:14px;text-align:center;cursor:pointer" onclick="ptFilterBuy('WATCH')">
    <div style="font-size:26px;font-weight:800;color:#e3b341">${watchCount}</div>
    <div style="font-size:11px;color:#6b7a8d;margin-top:3px">👁 WATCH</div>
  </div>
  <div style="background:#0f1419;border:1px solid #e3b34115;border-radius:12px;padding:14px;text-align:center;cursor:pointer" onclick="ptFilterBuy('SUSP')" title="Verdächtige Gaps (>20pp) — wahrscheinlich falsches Mapping">
    <div style="font-size:26px;font-weight:800;color:#e3b34180">${suspCount}</div>
    <div style="font-size:11px;color:#6b7a8d;margin-top:3px">⚠ Verdächtig</div>
  </div>
  <div style="background:#0f1419;border:1px solid #3fb95025;border-radius:12px;padding:14px;text-align:center">
    ${totalPnlEur != null
      ? `<div style="font-size:26px;font-weight:800;color:${totalPnlEur>=0?'#3fb950':'#f85149'}">${totalPnlEur>=0?'+':''}€${totalPnlEur.toFixed(2)}</div>`
      : `<div style="font-size:26px;font-weight:800;color:#6b7a8d">—</div>`
    }
    <div style="font-size:11px;color:#6b7a8d;margin-top:3px">Sim. P&L (€5/Trade)</div>
  </div>
</div>

<!-- ── Filters ────────────────────────────────────────────── -->
<div style="background:#0f1419;border:1px solid #1e2d3d;border-radius:12px;padding:12px 16px;margin-bottom:14px;display:flex;flex-wrap:wrap;gap:10px;align-items:center">
  <span style="font-size:11px;color:#6b7a8d;text-transform:uppercase;letter-spacing:.5px">Filter</span>
  <select onchange="ptFilterSignal(this.value)" style="background:#141b22;border:1px solid #243040;color:#e8edf3;border-radius:7px;padding:5px 8px;font-size:12px">
    <option value="all"   ${_polyTraderFilter.signal==='all'  ?'selected':''}>Alle</option>
    <option value="BUY"   ${_polyTraderFilter.signal==='BUY'  ?'selected':''}>▲ BUY</option>
    <option value="WATCH" ${_polyTraderFilter.signal==='WATCH'?'selected':''}>👁 WATCH</option>
    <option value="BOTH"  ${_polyTraderFilter.signal==='BOTH' ?'selected':''}>★ BOTH</option>
    <option value="SHARP" ${_polyTraderFilter.signal==='SHARP'?'selected':''}>⚡ SHARP</option>
    <option value="CLV+"  ${_polyTraderFilter.signal==='CLV+' ?'selected':''}>📐 CLV+</option>
    <option value="SUSP"  ${_polyTraderFilter.signal==='SUSP' ?'selected':''}>⚠ Verdächtig</option>
  </select>
  <select onchange="ptFilterMarket(this.value)" style="background:#141b22;border:1px solid #243040;color:#e8edf3;border-radius:7px;padding:5px 8px;font-size:12px">
    <option value="all">Alle Märkte</option>
    ${marketOptions}
  </select>
  <label style="font-size:12px;color:#8b9ab0;display:flex;align-items:center;gap:6px">
    Max. Tage:
    <input type="range" min="1" max="10" value="${_polyTraderFilter.maxDays}" oninput="ptFilterDays(this.value);document.getElementById('ptDaysLbl').textContent=this.value" style="width:70px">
    <span id="ptDaysLbl" style="color:#00d4a1;font-weight:700;min-width:16px">${_polyTraderFilter.maxDays}</span>
  </label>
  <label style="display:flex;align-items:center;gap:6px;font-size:12px;color:${_polyTraderFilter.hideSuspicious?'#e3b341':'#8b9ab0'};cursor:pointer;padding:4px 10px;border-radius:7px;border:1px solid ${_polyTraderFilter.hideSuspicious?'#e3b34140':'#243040'};background:${_polyTraderFilter.hideSuspicious?'#e3b34110':'transparent'}">
    <input type="checkbox" ${_polyTraderFilter.hideSuspicious?'checked':''} onchange="ptFilterSuspicious(!this.checked)" style="accent-color:#e3b341"> Verdächtige ausblenden
  </label>
  <span style="margin-left:auto;font-size:11px;color:#6b7a8d">${rows.length} / ${candidates.length} Einträge</span>
</div>

<!-- ── Signal Table ───────────────────────────────────────── -->
<div style="background:#0f1419;border:1px solid #1e2d3d;border-radius:12px;overflow:hidden;margin-bottom:20px">
  <div style="overflow-x:auto;-webkit-overflow-scrolling:touch">
    <table style="width:100%;border-collapse:collapse;font-size:12px">
      <thead>
        <tr style="border-bottom:2px solid #1e2d3d;background:#141b22">
          ${_sortTh('Match', 'home')}
          ${_sortTh('Kickoff', 'kickoffDate')}
          ${_sortTh('Markt', 'market')}
          ${_sortTh('Pini Open→Cur', 'bookie_move_pp')}
          ${_sortTh('Poly Open→Cur', 'poly_delta_pp')}
          ${_sortTh('Gap', 'gap_pp', true)}
          ${_sortTh('Aktion', 'buy_signal', true)}
          ${_sortTh('Signal', 'signal', true)}
          ${_sortTh('Obs. P&L', 'obs_pnl_pp', true)}
        </tr>
      </thead>
      <tbody>${tableRows || noRows}</tbody>
    </table>
  </div>
</div>

<!-- ══════════════════════════════════════════════════════════
     WAS WIR HIER GENAU MACHEN
     ════════════════════════════════════════════════════════ -->
<div style="background:#0f1419;border:1px solid #1e2d3d;border-radius:14px;padding:20px 24px;margin-bottom:14px">
  <div style="font-size:13px;font-weight:700;color:#e8edf3;margin-bottom:18px;display:flex;align-items:center;gap:8px">
    <span style="background:#00d4a115;border:1px solid #00d4a130;border-radius:8px;padding:4px 8px;font-size:16px">📋</span>
    Was wir hier genau machen
  </div>

  <!-- Die Idee in einem Satz -->
  <div style="background:linear-gradient(135deg,#0a1f18,#0a1428);border:1px solid #00d4a130;border-radius:12px;padding:16px 18px;margin-bottom:20px;font-size:13px;color:#e8edf3;line-height:1.8">
    Wir suchen Momente wo <strong style="color:#3fb950">Polymarket ein Spiel günstiger bewertet als Pinnacle</strong> — kaufen den unterbewerteten Token, und verkaufen wenn Poly den Preis nachzieht. <span style="color:#8b9ab0">Kein klassisches Wetten auf den Ausgang — nur Preiskonvergenz zwischen zwei Märkten.</span>
  </div>

  <!-- Schritt für Schritt -->
  <div style="margin-bottom:20px">
    <div style="font-size:11px;font-weight:700;color:#00d4a1;text-transform:uppercase;letter-spacing:.6px;margin-bottom:12px">So funktioniert es — Schritt für Schritt</div>
    <div style="display:grid;gap:8px">

      <div style="background:#141b22;border-radius:10px;padding:12px 14px;display:flex;gap:12px;align-items:flex-start">
        <span style="background:#00d4a120;color:#00d4a1;font-size:11px;font-weight:800;padding:3px 8px;border-radius:6px;flex-shrink:0;margin-top:1px">1</span>
        <div style="font-size:12px;color:#8b9ab0;line-height:1.7">
          <strong style="color:#e8edf3">Pinnacle setzt einen fairen Preis.</strong> Pinnacle ist der schärfste Buchmacher der Welt — Profis und Algorithmen handeln dort sofort wenn neue Informationen auftauchen. Sein Preis gilt als "wahrer Marktwert".
        </div>
      </div>

      <div style="background:#141b22;border-radius:10px;padding:12px 14px;display:flex;gap:12px;align-items:flex-start">
        <span style="background:#00d4a120;color:#00d4a1;font-size:11px;font-weight:800;padding:3px 8px;border-radius:6px;flex-shrink:0;margin-top:1px">2</span>
        <div style="font-size:12px;color:#8b9ab0;line-height:1.7">
          <strong style="color:#e8edf3">Polymarket hinkt nach.</strong> Polymarket ist ein dezentraler Markt — Preise ändern sich nur wenn jemand aktiv tradet. Bei wenig Volumen bleibt der Preis stehen, auch wenn sich der "echte Wert" schon verändert hat. Dieses Timing-Gap ist 6–36 Stunden.
        </div>
      </div>

      <div style="background:#0a1a0a;border:1px solid #3fb95025;border-radius:10px;padding:12px 14px;display:flex;gap:12px;align-items:flex-start">
        <span style="background:#3fb95020;color:#3fb950;font-size:11px;font-weight:800;padding:3px 8px;border-radius:6px;flex-shrink:0;margin-top:1px">3</span>
        <div style="font-size:12px;color:#8b9ab0;line-height:1.7">
          <strong style="color:#3fb950">Gap erkannt → BUY Signal.</strong> Wenn Pinnacle 56% impliziert aber Poly noch bei 48% steht: Gap = +8pp. Das bedeutet Poly ist um 8pp "zu billig". Wir kaufen den YES-Token bei 48¢.
          <div style="background:#0f1419;border-radius:7px;padding:8px 10px;margin-top:8px;font-size:11px">
            Poly-Quote (1/0.48 = <strong style="color:#e8edf3">2.08</strong>) ist höher als Pinnacle (1/0.56 = <strong style="color:#e8edf3">1.79</strong>) → Poly bietet das bessere Geschäft → <strong style="color:#3fb950">BUY</strong>
          </div>
        </div>
      </div>

      <div style="background:#141b22;border-radius:10px;padding:12px 14px;display:flex;gap:12px;align-items:flex-start">
        <span style="background:#00d4a120;color:#00d4a1;font-size:11px;font-weight:800;padding:3px 8px;border-radius:6px;flex-shrink:0;margin-top:1px">4</span>
        <div style="font-size:12px;color:#8b9ab0;line-height:1.7">
          <strong style="color:#e8edf3">Poly zieht nach → wir verkaufen.</strong> Sobald andere Trader den Gap erkennen (oder der Markt sich dem Spieltag nähert), steigt der Poly-Preis von 48% auf ~55%. Wir verkaufen bei 55¢ — <strong style="color:#3fb950">+7pp Gewinn unabhängig davon ob Bayern gewinnt oder nicht.</strong>
        </div>
      </div>

    </div>
  </div>

  <!-- Was wir jetzt gerade machen -->
  <div style="margin-bottom:20px">
    <div style="font-size:11px;font-weight:700;color:#00d4a1;text-transform:uppercase;letter-spacing:.6px;margin-bottom:10px">Aktueller Status — Observer Mode</div>
    <div style="background:#141b22;border:1px solid #1e2d3d;border-radius:10px;padding:14px 16px;font-size:12px;color:#8b9ab0;line-height:1.8">
      <div style="display:grid;grid-template-columns:auto 1fr;gap:8px 14px;align-items:start">
        <span style="color:#3fb950;font-weight:700;white-space:nowrap">✓ Aktiv</span>
        <span>Poly-Preise werden 5–6× täglich gespeichert. BUY/WATCH Signale werden berechnet. Simulated P&L läuft mit.</span>
        <span style="color:#e3b341;font-weight:700;white-space:nowrap">⏳ Noch nicht</span>
        <span>Kein automatisches Trading. Wenn du ein <strong style="color:#3fb950">▲ BUY</strong> Signal siehst: geh manuell auf polymarket.com (🔗 Link in der Zeile), kauf den YES-Token, und verkauf wenn der Gap sich schließt.</span>
        <span style="color:#6b7a8d;font-weight:700;white-space:nowrap">Ziel</span>
        <span>Nach 2–3 Wochen Observer-Daten: sehen ob Signale wirklich zu Preisbewegung führen → dann Auto-Trade mit kleinem Betrag einschalten.</span>
      </div>
    </div>
  </div>

  <!-- BUY / WATCH / SKIP erklärt -->
  <div style="margin-bottom:20px">
    <div style="font-size:11px;font-weight:700;color:#00d4a1;text-transform:uppercase;letter-spacing:.6px;margin-bottom:10px">Aktions-Badges erklärt</div>
    <div style="display:grid;gap:8px">
      <div style="background:#0a1a0a;border:1px solid #3fb95030;border-radius:10px;padding:11px 14px;display:grid;grid-template-columns:90px 1fr;gap:8px;align-items:center">
        <span style="background:#3fb95015;border:1px solid #3fb95040;color:#3fb950;font-size:10px;font-weight:700;padding:3px 8px;border-radius:6px;text-align:center">▲ BUY</span>
        <span style="font-size:11px;color:#8b9ab0;line-height:1.6">Gap ≥5pp · T1/T2 Liga · Poly-Preis 15–85% · Spiel noch offen. <strong style="color:#e8edf3">Kaufen auf polymarket.com (🔗).</strong></span>
      </div>
      <div style="background:#141b22;border:1px solid #e3b34125;border-radius:10px;padding:11px 14px;display:grid;grid-template-columns:90px 1fr;gap:8px;align-items:center">
        <span style="background:#e3b34115;border:1px solid #e3b34140;color:#e3b341;font-size:10px;font-weight:700;padding:3px 8px;border-radius:6px;text-align:center">👁 WATCH</span>
        <span style="font-size:11px;color:#8b9ab0;line-height:1.6">Gap 2–4pp. Etwas da — im Auge behalten. Wenn Gap wächst → wird zu BUY.</span>
      </div>
      <div style="background:#141b22;border:1px solid #f8514920;border-radius:10px;padding:11px 14px;display:grid;grid-template-columns:90px 1fr;gap:8px;align-items:center">
        <span style="background:#f8514915;border:1px solid #f8514935;color:#f85149;font-size:10px;font-weight:700;padding:3px 8px;border-radius:6px;text-align:center">▽ SKIP</span>
        <span style="font-size:11px;color:#8b9ab0;line-height:1.6">Poly ist teurer als Pinnacle. Kein Vorteil — eher short gehen (NO Token) oder nichts tun.</span>
      </div>
      <div style="background:#141b22;border:1px solid #e3b34120;border-radius:10px;padding:11px 14px;display:grid;grid-template-columns:90px 1fr;gap:8px;align-items:center">
        <span style="background:#e3b34110;border:1px solid #e3b34140;color:#e3b341;font-size:10px;font-weight:700;padding:3px 8px;border-radius:6px;text-align:center">⚠ PRÜFEN</span>
        <span style="font-size:11px;color:#8b9ab0;line-height:1.6">Gap &gt;20pp. Wahrscheinlich falsches Contract-Matching — kein echter Trade. Standardmäßig ausgeblendet.</span>
      </div>
    </div>
  </div>

  <!-- Kosten & Break-Even kompakt -->
  <div style="margin-bottom:20px">
    <div style="font-size:11px;font-weight:700;color:#00d4a1;text-transform:uppercase;letter-spacing:.6px;margin-bottom:10px">Kosten & Break-Even</div>
    <div style="background:#141b22;border:1px solid #1e2d3d;border-radius:10px;padding:12px 16px;font-size:11px;color:#8b9ab0;line-height:1.8">
      <div style="display:grid;grid-template-columns:auto 1fr;gap:4px 16px">
        <span style="color:#e8edf3;font-weight:600">Bid-Ask Spread</span><span>1–3pp auf Poly. Größter Kostenfaktor — deshalb erst ab Gap ≥5pp kaufen.</span>
        <span style="color:#e8edf3;font-weight:600">Slippage</span><span>~0.5pp bei Market-Orders. Limit-Orders auf Best-Bid verwenden.</span>
        <span style="color:#e8edf3;font-weight:600">Gas-Kosten</span><span>~0.01–0.05 USDC/Trade auf Polygon. Vernachlässigbar.</span>
        <span style="color:#00d4a1;font-weight:700">Break-Even</span><span>Poly muss sich um <strong style="color:#00d4a1">≥5pp</strong> bewegen für Profit nach Kosten. Gap ≥5pp → BUY Schwelle passt genau.</span>
      </div>
    </div>
  </div>

  <!-- Limitierungen -->
  <div>
    <div style="font-size:11px;font-weight:700;color:#e3b341;text-transform:uppercase;letter-spacing:.6px;margin-bottom:10px">⚠ Aktuelle Einschränkungen</div>
    <div style="background:#141b22;border:1px solid #e3b34120;border-radius:10px;padding:12px 16px;font-size:11px;color:#8b9ab0;line-height:1.8">
      <div style="display:grid;gap:6px">
        <div><span style="color:#e3b341;font-weight:600">Pinnacle-Vergleich nur für 1X2 + Over 2.5</span> — Andere Märkte (BTTS, Over 1.5, Corners) haben keinen pinn_fair Key → kein BUY Signal möglich, nur Poly-Tracking.</div>
        <div><span style="color:#e3b341;font-weight:600">Kein Exit-Signal</span> — Aktuell kein automatischer "Jetzt verkaufen"-Trigger. Manuell: verkaufen wenn Gap &lt;1pp oder Poly-Delta ≥80% der initialen Bookie-Bewegung.</div>
        <div><span style="color:#e3b341;font-weight:600">Liquidity Tier ist statisch</span> — T1/T2/T3 nach Liga, kein live Volume-Check. T3 Ligen (TUR, SCO) bekommen kein BUY Signal da zu dünn.</div>
        <div><span style="color:#e3b341;font-weight:600">P&L erst ab 3+ Tagen aussagekräftig</span> — Open = Current solange nur 1 Snapshot. Delta und Sim. P&L bauen sich über Zeit auf.</div>
      </div>
    </div>
  </div>
</div>`;
}

// ── Poly Trader event handlers (global, called from inline HTML) ────────────
window.ptSort = function(col) {
  if (_polyTraderSort.col === col) _polyTraderSort.dir *= -1;
  else { _polyTraderSort.col = col; _polyTraderSort.dir = -1; }
  renderPolyTrader(document.getElementById('polyTraderPanel'));
};
window.ptFilterSignal = function(val) {
  _polyTraderFilter.signal = val;
  renderPolyTrader(document.getElementById('polyTraderPanel'));
};
window.ptFilterMarket = function(val) {
  _polyTraderFilter.market = val;
  renderPolyTrader(document.getElementById('polyTraderPanel'));
};
window.ptFilterDays = function(val) {
  _polyTraderFilter.maxDays = parseInt(val);
  renderPolyTrader(document.getElementById('polyTraderPanel'));
};
window.ptFilterActionable = function(val) {
  _polyTraderFilter.actionableOnly = val;
  renderPolyTrader(document.getElementById('polyTraderPanel'));
};
window.ptFilterSuspicious = function(val) {
  _polyTraderFilter.hideSuspicious = val;
  renderPolyTrader(document.getElementById('polyTraderPanel'));
};
// Quick-filter by clicking on summary stats tiles
window.ptFilterBuy = function(val) {
  _polyTraderFilter.signal = val;
  if (val === 'SUSP') _polyTraderFilter.hideSuspicious = false;
  renderPolyTrader(document.getElementById('polyTraderPanel'));
};


