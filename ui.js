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

// All panel IDs — hidden when switching views
const _ALL_PANELS = [
  'mainContent', 'trackingV2Panel', 'resultsPanel',
  'intlCardsPanel', 'intlTrackingPanel', 'intlWm2026Panel', 'intlTelegramPanel',
  'polymarketPanel', 'polyTraderPanel',
  'heartPanel', 'statusPanel',
];

// Top-nav button IDs
const _TOP_NAV_IDS = [
  'navNational', 'navIntl', 'navSharp',
  'navPolyTrader', 'navPolymarket', 'navHeart', 'navStatus',
];

function showView(view) {
  // ── Determine section ────────────────────────────────
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
    'national-cards':    'mainContent',
    'national-tracking': 'trackingV2Panel',
    'intl-cards':        'intlCardsPanel',
    'intl-tracking':     'intlTrackingPanel',
    'intl-wm2026':       'intlWm2026Panel',
    'intl-telegram':     'intlTelegramPanel',
    'sharp':             'mainContent',
    'polytrading':       'polyTraderPanel',
    'polybetting':       'polymarketPanel',
    'heart':             'heartPanel',
    'status':            'statusPanel',
  };
  const panelId = panelMap[view];
  if (panelId) {
    const panel = document.getElementById(panelId);
    if (panel) panel.style.display = '';
  }

  // ── League nav: visible for National Cards + Sharp ───
  const leagueNav = document.querySelector('.league-nav');
  const legend    = document.querySelector('.legend-section');
  const showLeague = view === 'national-cards' || view === 'sharp';
  if (leagueNav) leagueNav.style.display = showLeague ? '' : 'none';
  if (legend)    legend.style.display    = view === 'national-cards' ? '' : 'none';

  // ── Sub-nav: visible for National + International ────
  const subNav = document.getElementById('subNav');
  const hasSubNav = _activeSection === 'national' || _activeSection === 'intl';
  if (subNav) subNav.style.display = hasSubNav ? '' : 'none';

  // Sub-nav active buttons
  const isCards    = view.endsWith('-cards');
  const isTracking = view.endsWith('-tracking');
  const isWm2026   = view === 'intl-wm2026';
  const isTelegram = view === 'intl-telegram';
  const subCards    = document.getElementById('subCards');
  const subTracking = document.getElementById('subTracking');
  const subWm2026   = document.getElementById('subWm2026');
  const subTelegram = document.getElementById('subTelegram');
  if (subCards)    subCards.classList.toggle('active',    isCards);
  if (subTracking) subTracking.classList.toggle('active', isTracking);
  if (subWm2026)   subWm2026.classList.toggle('active',   isWm2026);
  if (subTelegram) subTelegram.classList.toggle('active', isTelegram);
  // WM2026 + Telegram sub-nav only visible under International
  const intlOnly = _activeSection === 'intl';
  if (subWm2026)   subWm2026.style.display   = intlOnly ? '' : 'none';
  if (subTelegram) subTelegram.style.display  = intlOnly ? '' : 'none';

  // ── Top-nav active state ─────────────────────────────
  _TOP_NAV_IDS.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.remove('active');
  });
  const topNavMap = {
    'national':    'navNational',
    'intl':        'navIntl',
    'sharp':       'navSharp',
    'polytrading': 'navPolyTrader',
    'polybetting': 'navPolymarket',
    'heart':       'navHeart',
    'status':      'navStatus',
  };
  const activeNavId = topNavMap[_activeSection];
  if (activeNavId) {
    const el = document.getElementById(activeNavId);
    if (el) el.classList.add('active');
  }

  // ── Sharp Radar: activate sharp league button ────────
  if (view === 'sharp') {
    document.querySelectorAll('.league-btn').forEach(b => b.classList.remove('active'));
    const sharpBtn = document.querySelector('.league-btn[data-league="sharp"]');
    if (sharpBtn) sharpBtn.classList.add('active');
    window._currentLeague = 'sharp';
    if (typeof renderSharpRadar === 'function') renderSharpRadar();
  }

  // ── Callbacks ────────────────────────────────────────
  if (view === 'status')            { initStatus(); buildValidatorDates(); }
  if (view === 'polybetting')       initPolymarket();
  if (view === 'polytrading')       initPolyTrader();
  if (view === 'national-tracking' && typeof initResultsV2      === 'function') initResultsV2();
  if (view === 'intl-cards'        && typeof initIntlCards     === 'function') initIntlCards();
  if (view === 'intl-tracking'     && typeof initIntlTracking  === 'function') initIntlTracking();
  if (view === 'intl-wm2026'       && typeof initWm2026        === 'function') initWm2026();
  if (view === 'intl-telegram'     && typeof initTelegramPanel === 'function') initTelegramPanel();
}

// Sub-nav click: navigate within current section
function showSubView(sub) {
  showView(_activeSection + '-' + sub);
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
const _STATUS_WORKFLOWS = [
  { id: 'update-dashboard',  icon: '🏁', label: 'Dashboard Update',     color: '#3fb950', desc: 'Täglich 06:00 + 14:00 UTC' },
  { id: 'fetch-prematch',    icon: '📋', label: 'Pre-Match Daten',       color: '#f0c040', desc: 'Täglich 04:45 + 12:45 UTC' },
  { id: 'fetch-results',     icon: '📊', label: 'Ergebnisse holen',      color: '#58a6ff', desc: 'Täglich 3× täglich' },
  { id: 'refresh-xg',        icon: '📐', label: 'xG Statistiken',        color: '#a78bfa', desc: 'Wöchentlich Mo 05:00 UTC' },
];

const _STATUS_FILES = [
  { file: 'season-finish.html', icon: '🏁', label: 'Dashboard HTML',     desc: 'via update-dashboard.yml' },
  { file: 'prematch-data.json', icon: '📋', label: 'Pre-Match Daten',    desc: 'via fetch-prematch.yml' },
  { file: 'results-cache.json', icon: '📊', label: 'Ergebnisse Cache',   desc: 'via fetch-results.yml' },
  { file: 'stats_cache.json',   icon: '📐', label: 'xG / Stats Cache',   desc: 'via refresh-xg.yml + refresh_stats.py' },
];

const _STATUS_ACTIONS = [
  { key: 'picks_saved',        icon: '💾', label: 'Picks speichern',    color: '#3fb950' },
  { key: 'results_fetched',    icon: '🔄', label: 'Ergebnisse holen',   color: '#58a6ff' },
  { key: 'prematch_reloaded',  icon: '🔃', label: 'Pre-Match reload',   color: '#f0c040' },
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

  // ── Section 0: Validator Summary Banner ──────────────
  const vs = (typeof VALIDATOR_SUMMARY !== 'undefined') ? VALIDATOR_SUMMARY : null;
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

  // ── Section 2: File freshness via GitHub API ──────────
  const filesEl   = document.getElementById('statusFiles');
  const filesNote = document.getElementById('statusFilesNote');
  filesEl.innerHTML = _STATUS_FILES.map(() =>
    `<div style="background:var(--card2);border:1px solid var(--border);border-radius:10px;padding:14px 16px;">
      <div style="height:48px;display:flex;align-items:center;justify-content:center;color:var(--muted);font-size:12px;">Lädt…</div>
    </div>`
  ).join('');

  const fileMeta = await Promise.all(_STATUS_FILES.map(async f => {
    try {
      const r = await fetch(`https://api.github.com/repos/${_REPO}/commits?path=${encodeURIComponent(f.file)}&per_page=1`);
      if (!r.ok) return null;
      const data = await r.json();
      if (!data.length) return null;
      const commit = data[0];
      return {
        date:    commit.commit?.committer?.date || commit.commit?.author?.date,
        sha:     commit.sha?.slice(0, 7),
        message: commit.commit?.message?.split('\n')[0] || '',
      };
    } catch(e) { return null; }
  }));

  filesEl.innerHTML = _STATUS_FILES.map((f, i) => {
    const meta  = fileMeta[i];
    const ago   = meta ? _timeAgo(meta.date) : '—';
    const color = meta ? _freshnessColor(meta.date) : '#8b949e';
    const sha   = meta?.sha ? `<span style="font-family:monospace;font-size:10px;opacity:.6;">${meta.sha}</span>` : '';
    const msg   = meta?.message ? `<span title="${meta.message}">${meta.message.length > 40 ? meta.message.slice(0, 40) + '…' : meta.message}</span>` : '';
    return `<div style="background:var(--card2);border:1px solid var(--border);border-radius:10px;padding:14px 16px;">
      <div style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px;">${f.icon} ${f.label}</div>
      <div style="font-size:15px;font-weight:700;color:${color};margin-bottom:4px;">${ago}</div>
      <div style="font-size:11px;color:var(--muted);">${f.file}</div>
      ${meta ? `<div style="font-size:10px;color:var(--muted);margin-top:3px;">${sha} ${msg}</div>` : ''}
    </div>`;
  }).join('');

  filesNote.textContent = 'Stand: via GitHub API  · Grün < 6h  ·  Gelb < 24h  ·  Rot ≥ 24h';

  // ── Section 3: Dashboard action log ──────────────────
  const actEl = document.getElementById('statusActions');
  let log = {};
  try { log = JSON.parse(localStorage.getItem('betedge_action_log') || '{}'); } catch(e) {}

  actEl.innerHTML = _STATUS_ACTIONS.map(a => {
    const ts    = log[a.key] || null;
    const ago   = ts ? _timeAgo(ts) : 'Noch nie';
    const color = ts ? _freshnessColor(ts) : '#8b949e';
    const isoFmt = ts ? new Date(ts).toLocaleString('de-AT', { day:'2-digit', month:'2-digit', hour:'2-digit', minute:'2-digit' }) : null;
    return _statusCard(a.icon, a.label, ago, isoFmt || 'Noch kein Klick in diesem Browser', color);
  }).join('');

  // ── Section 4: Quick links to trigger workflows ───────
  document.getElementById('statusQuickLinks').innerHTML = _STATUS_WORKFLOWS.map(w =>
    _quickLink(w.icon, w.label,
      `https://github.com/${_REPO}/actions/workflows/${w.id}.yml`,
      w.color)
  ).join('');
}


  // [validator functions] → validator.js
  // buildValidatorDates(), runPicksValidator(), renderValidatorOutput(), copyValidatorOutput()


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

  try {
    const res = await fetch('poly_trader_data.json?_=' + Date.now());
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    _polyTraderData = await res.json();
  } catch(e) {
    panel.innerHTML = `<div style="text-align:center;padding:60px 20px;color:#f85149">
      <div style="font-size:32px;margin-bottom:12px">⚠️</div>
      <div style="font-weight:700;margin-bottom:6px">Daten nicht gefunden</div>
      <div style="font-size:12px;color:#6b7a8d">poly_trader_data.json fehlt — läuft nach dem nächsten GitHub Actions Workflow</div>
    </div>`;
    return;
  }
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

  panel.innerHTML = `
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


