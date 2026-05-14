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
//  VIEW SWITCHER
// ═══════════════════════════════════════════════════════
function showView(view) {
  const isSeason      = view === 'season';
  const isResults     = view === 'results';
  const isHeart       = view === 'heart';
  const isStatus      = view === 'status';
  const isPolymarket  = view === 'polymarket';
  const isTracking    = view === 'tracking';
  const isPolyTrader  = view === 'polytrader';

  document.getElementById('mainContent').style.display        = isSeason      ? '' : 'none';
  document.getElementById('resultsPanel').style.display       = isResults     ? '' : 'none';
  document.getElementById('heartPanel').style.display         = isHeart       ? '' : 'none';
  document.getElementById('statusPanel').style.display        = isStatus      ? '' : 'none';
  document.getElementById('polymarketPanel').style.display    = isPolymarket  ? '' : 'none';
  document.getElementById('trackingV2Panel').style.display    = isTracking    ? '' : 'none';
  const _ptPanel = document.getElementById('polyTraderPanel');
  if (_ptPanel) _ptPanel.style.display = isPolyTrader ? '' : 'none';

  document.querySelector('.league-nav').style.display         = isSeason      ? '' : 'none';
  const legend = document.querySelector('.legend-section');
  if (legend) legend.style.display = isSeason ? '' : 'none';

  document.getElementById('navSeason').classList.toggle('active',      isSeason);
  document.getElementById('navResults').classList.toggle('active',     isResults);
  document.getElementById('navHeart').classList.toggle('active',       isHeart);
  document.getElementById('navStatus').classList.toggle('active',      isStatus);
  document.getElementById('navPolymarket').classList.toggle('active',  isPolymarket);
  document.getElementById('navTracking').classList.toggle('active',    isTracking);
  const _navPT = document.getElementById('navPolyTrader');
  if (_navPT) _navPT.classList.toggle('active', isPolyTrader);
  // Sharp Radar uses the season panel — clear its active when another view is picked
  const _navSharp = document.getElementById('navSharp');
  if (_navSharp) _navSharp.classList.remove('active');

  if (isResults)     initResults();
  if (isStatus)      { initStatus(); buildValidatorDates(); }
  if (isPolymarket)  initPolymarket();
  if (isTracking && typeof initResultsV2 === 'function') initResultsV2();
  if (isPolyTrader)  initPolyTrader();
}

// Navigate directly to Sharp Radar from the top nav
function showSharpRadar() {
  // Show the season panel (same container as league views)
  showView('season');
  // Activate the sharp sub-tab in league nav
  document.querySelectorAll('.league-btn').forEach(b => b.classList.remove('active'));
  const _sharpBtn = document.querySelector('.league-btn[data-league="sharp"]');
  if (_sharpBtn) _sharpBtn.classList.add('active');
  window._currentLeague = 'sharp';
  // Render the radar
  if (typeof renderSharpRadar === 'function') renderSharpRadar();
  // Mark Sharp Radar active in top nav (showView de-activated navSeason)
  const _navSharp = document.getElementById('navSharp');
  if (_navSharp) _navSharp.classList.add('active');
  document.getElementById('navSeason').classList.remove('active');
}

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
let _polyTraderFilter = { signal: 'all', market: 'all', minDays: 0, maxDays: 10 };
let _polyTraderSort = { col: 'signal_strength', dir: -1 };

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
  const allSignals  = candidates.filter(c => c.signal);
  const sharpCount  = candidates.filter(c => c.signal === 'SHARP' || c.signal === 'BOTH').length;
  const clvCount    = candidates.filter(c => c.signal === 'CLV+' || c.signal === 'BOTH').length;
  const bothCount   = candidates.filter(c => c.signal === 'BOTH').length;
  const posDeltas   = candidates.filter(c => c.poly_delta_pp > 0);
  const avgPosDelta = posDeltas.length ? (posDeltas.reduce((s,c) => s+c.poly_delta_pp,0)/posDeltas.length).toFixed(1) : '—';

  // ── Filter + sort candidates ─────────────────────────────────────────────
  let rows = candidates.filter(c => {
    if (_polyTraderFilter.signal !== 'all' && c.signal !== _polyTraderFilter.signal) return false;
    if (_polyTraderFilter.market !== 'all' && c.market !== _polyTraderFilter.market) return false;
    if (c.daysOut < _polyTraderFilter.minDays || c.daysOut > _polyTraderFilter.maxDays) return false;
    return true;
  });
  const { col, dir } = _polyTraderSort;
  rows.sort((a, b) => {
    let va = a[col] ?? -999, vb = b[col] ?? -999;
    if (typeof va === 'string') va = va.toLowerCase(), vb = vb.toLowerCase();
    return va < vb ? dir : va > vb ? -dir : 0;
  });

  // ── Unique markets for filter ────────────────────────────────────────────
  const allMarkets = [...new Set(candidates.map(c => c.market))].sort();

  function _signalBadge(sig) {
    if (!sig) return '<span style="font-size:10px;color:#6b7a8d">—</span>';
    const cfg = {
      'BOTH':  { bg:'#00d4a118', bc:'#00d4a135', col:'#00d4a1', lbl:'★ BOTH'  },
      'SHARP': { bg:'#58a6ff12', bc:'#58a6ff35', col:'#58a6ff', lbl:'⚡ SHARP' },
      'CLV+':  { bg:'#a78bfa12', bc:'#a78bfa35', col:'#a78bfa', lbl:'📐 CLV+'  },
    }[sig] || { bg:'#ffffff08', bc:'#ffffff15', col:'#8b9ab0', lbl: sig };
    return `<span style="background:${cfg.bg};border:1px solid ${cfg.bc};color:${cfg.col};font-size:10px;font-weight:700;padding:2px 7px;border-radius:6px;white-space:nowrap">${cfg.lbl}</span>`;
  }

  function _deltaCell(pp) {
    if (pp == null) return '—';
    const col = pp > 1 ? '#3fb950' : pp < -1 ? '#f85149' : '#8b9ab0';
    const ico = pp > 0 ? '▲' : pp < 0 ? '▼' : '→';
    return `<span style="color:${col};font-weight:700">${ico} ${pp > 0?'+':''}${pp.toFixed(1)}pp</span>`;
  }

  function _bookieMoveCell(pp) {
    if (pp == null) return '—';
    const col = Math.abs(pp) >= 8 ? '#58a6ff' : Math.abs(pp) >= 5 ? '#e3b341' : '#8b9ab0';
    return `<span style="color:${col};font-weight:600">${pp > 0?'+':''}${pp.toFixed(1)}pp</span>`;
  }

  function _sortTh(label, colKey) {
    const active = _polyTraderSort.col === colKey;
    const arrow = active ? (_polyTraderSort.dir === -1 ? ' ↓' : ' ↑') : '';
    return `<th style="cursor:pointer;user-select:none;${active?'color:#00d4a1':''}" onclick="ptSort('${colKey}')">${label}${arrow}</th>`;
  }

  const tableRows = rows.map(c => {
    const kickofFmt = c.kickoffDate ? c.kickoffDate.slice(5).replace('-','.') : '—';
    const daysLabel = c.daysOut <= 1 ? `<span style="color:#e3b341">Heute/Mor.</span>` : `${c.daysOut}d`;
    const obsSimPnl = c.obs_pnl_pp != null
      ? `<span style="color:${c.obs_pnl_pp > 0 ? '#3fb950' : c.obs_pnl_pp < 0 ? '#f85149' : '#8b9ab0'};font-weight:700">${c.obs_pnl_pp > 0?'+':''}${c.obs_pnl_pp.toFixed(1)}pp</span>`
      : '—';
    const polyOpenFmt = c.poly_open != null ? `${c.poly_open.toFixed(1)}%` : '—';
    const polyCurFmt  = c.poly_cur  != null ? `${c.poly_cur.toFixed(1)}%`  : '—';
    const polyUrl = c.eventUrl
      ? `<a href="${c.eventUrl}" target="_blank" style="color:#58a6ff;font-size:10px">🔗</a>`
      : '';

    return `<tr style="border-bottom:1px solid #1e2d3d">
      <td style="padding:9px 8px;font-weight:600;white-space:nowrap">${c.home} vs ${c.away} ${polyUrl}</td>
      <td style="padding:9px 8px;color:#8b9ab0;white-space:nowrap">${kickofFmt} <span style="font-size:10px">(${daysLabel})</span></td>
      <td style="padding:9px 8px;font-size:11px;color:#8b9ab0">${c.market}</td>
      <td style="padding:9px 8px;text-align:center">${_bookieMoveCell(c.bookie_move_pp)}</td>
      <td style="padding:9px 8px;text-align:center;color:#8b9ab0">${polyOpenFmt}</td>
      <td style="padding:9px 8px;text-align:center;font-weight:700">${polyCurFmt}</td>
      <td style="padding:9px 8px;text-align:center">${_deltaCell(c.poly_delta_pp)}</td>
      <td style="padding:9px 8px;text-align:center">${_signalBadge(c.signal)}</td>
      <td style="padding:9px 8px;text-align:center">${obsSimPnl}</td>
    </tr>`;
  }).join('');

  const noRows = rows.length === 0
    ? `<tr><td colspan="9" style="text-align:center;padding:40px;color:#6b7a8d">Keine Kandidaten für aktuelle Filter</td></tr>`
    : '';

  const marketOptions = allMarkets.map(m =>
    `<option value="${m}" ${_polyTraderFilter.market===m?'selected':''}>${m}</option>`
  ).join('');

  panel.innerHTML = `
<!-- ── Observer Mode Banner ─────────────────────────────────── -->
<div style="background:linear-gradient(135deg,#0a1f18,#0a1428);border:1px solid #00d4a125;border-radius:14px;padding:16px 20px;margin-bottom:20px;display:flex;align-items:center;gap:14px">
  <div style="font-size:28px;flex-shrink:0">👁</div>
  <div>
    <div style="font-size:13px;font-weight:700;color:#00d4a1;margin-bottom:3px">Observer Mode — Kein echtes Geld</div>
    <div style="font-size:12px;color:#6b7a8d;line-height:1.5">
      Alle P&amp;L-Werte sind simuliert. Das System beobachtet Poly-Preis-Bewegungen vs. Bookie-Line-Bewegungen.
      Nach 2–3 Wochen Daten → Auto-Trade mit €1/Signal.
    </div>
  </div>
  <div style="margin-left:auto;text-align:right;flex-shrink:0">
    <div style="font-size:10px;color:#6b7a8d">Stand</div>
    <div style="font-size:12px;color:#8b9ab0;font-weight:600">${updated ? new Date(updated).toLocaleString('de-AT',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}) : '—'}</div>
  </div>
</div>

<!-- ── Summary Stats ─────────────────────────────────────────── -->
<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:20px">
  <div style="background:#0f1419;border:1px solid #1e2d3d;border-radius:12px;padding:14px;text-align:center">
    <div style="font-size:24px;font-weight:800;color:#00d4a1">${allSignals.length}</div>
    <div style="font-size:11px;color:#6b7a8d;margin-top:3px">Aktive Signale</div>
  </div>
  <div style="background:#0f1419;border:1px solid #58a6ff30;border-radius:12px;padding:14px;text-align:center">
    <div style="font-size:24px;font-weight:800;color:#58a6ff">${sharpCount}</div>
    <div style="font-size:11px;color:#6b7a8d;margin-top:3px">⚡ SHARP</div>
  </div>
  <div style="background:#0f1419;border:1px solid #a78bfa30;border-radius:12px;padding:14px;text-align:center">
    <div style="font-size:24px;font-weight:800;color:#a78bfa">${clvCount}</div>
    <div style="font-size:11px;color:#6b7a8d;margin-top:3px">📐 CLV+</div>
  </div>
  <div style="background:#0f1419;border:1px solid #3fb95030;border-radius:12px;padding:14px;text-align:center">
    <div style="font-size:24px;font-weight:800;color:#3fb950">${avgPosDelta > 0 ? '+' : ''}${avgPosDelta}pp</div>
    <div style="font-size:11px;color:#6b7a8d;margin-top:3px">∅ Poly-Delta (pos.)</div>
  </div>
</div>

<!-- ── Filters ───────────────────────────────────────────────── -->
<div style="background:#0f1419;border:1px solid #1e2d3d;border-radius:12px;padding:14px 16px;margin-bottom:16px;display:flex;flex-wrap:wrap;gap:12px;align-items:center">
  <span style="font-size:11px;color:#6b7a8d;text-transform:uppercase;letter-spacing:.5px">Filter</span>
  <select onchange="ptFilterSignal(this.value)" style="background:#141b22;border:1px solid #243040;color:#e8edf3;border-radius:7px;padding:5px 8px;font-size:12px">
    <option value="all" ${_polyTraderFilter.signal==='all'?'selected':''}>Alle Signale</option>
    <option value="BOTH"  ${_polyTraderFilter.signal==='BOTH' ?'selected':''}>★ BOTH</option>
    <option value="SHARP" ${_polyTraderFilter.signal==='SHARP'?'selected':''}>⚡ SHARP</option>
    <option value="CLV+"  ${_polyTraderFilter.signal==='CLV+' ?'selected':''}>📐 CLV+</option>
  </select>
  <select onchange="ptFilterMarket(this.value)" style="background:#141b22;border:1px solid #243040;color:#e8edf3;border-radius:7px;padding:5px 8px;font-size:12px">
    <option value="all">Alle Märkte</option>
    ${marketOptions}
  </select>
  <label style="font-size:12px;color:#8b9ab0;display:flex;align-items:center;gap:6px">
    Kickoff ≤
    <input type="range" min="1" max="10" value="${_polyTraderFilter.maxDays}" oninput="ptFilterDays(this.value);document.getElementById('ptDaysLbl').textContent=this.value" style="width:80px">
    <span id="ptDaysLbl" style="color:#00d4a1;font-weight:700;min-width:16px">${_polyTraderFilter.maxDays}</span>d
  </label>
  <span style="margin-left:auto;font-size:11px;color:#6b7a8d">${rows.length} / ${candidates.length} Kandidaten</span>
</div>

<!-- ── Table ─────────────────────────────────────────────────── -->
<div style="background:#0f1419;border:1px solid #1e2d3d;border-radius:12px;overflow:hidden;margin-bottom:20px">
  <div style="overflow-x:auto">
    <table style="width:100%;border-collapse:collapse;font-size:12px">
      <thead>
        <tr style="border-bottom:1px solid #1e2d3d;background:#141b22">
          ${_sortTh('Match', 'home')}
          ${_sortTh('Kickoff', 'kickoffDate')}
          ${_sortTh('Markt', 'market')}
          ${_sortTh('Bookie Move', 'bookie_move_pp')}
          ${_sortTh('Poly Open', 'poly_open')}
          ${_sortTh('Poly Aktuell', 'poly_cur')}
          ${_sortTh('Poly Δ', 'poly_delta_pp')}
          ${_sortTh('Signal', 'signal')}
          ${_sortTh('Obs. P&L', 'obs_pnl_pp')}
        </tr>
      </thead>
      <tbody>
        ${tableRows || noRows}
      </tbody>
    </table>
  </div>
</div>

<!-- ── Legend ────────────────────────────────────────────────── -->
<div style="background:#0f1419;border:1px solid #1e2d3d;border-radius:12px;padding:16px 20px;font-size:11px;color:#6b7a8d;line-height:1.8">
  <div style="font-weight:700;color:#8b9ab0;margin-bottom:8px;text-transform:uppercase;letter-spacing:.5px">Legende</div>
  <div><span style="color:#58a6ff;font-weight:700">⚡ SHARP</span> — Pinnacle-Linie bewegt sich ≥5pp → Profis haben Geld gesetzt. Poly hinkt typisch 6–36h nach.</div>
  <div><span style="color:#a78bfa;font-weight:700">📐 CLV+</span> — Aktuelle Pinnacle-Implied &gt; Poly-Preis um ≥4pp → Poly ist noch nicht auf Bookie-Niveau repriced.</div>
  <div><span style="color:#00d4a1;font-weight:700">★ BOTH</span> — Beide Signale gleichzeitig → Stärkster Entry-Kandidat.</div>
  <div style="margin-top:6px"><strong style="color:#8b9ab0">Obs. P&L</strong> — Simulierter Gewinn wenn Opening-Entry bei <em>poly_open</em> und aktueller Preis als Exit. Rein beobachtend, kein echtes Trade.</div>
  <div><strong style="color:#8b9ab0">Bookie Move</strong> — Pinnacle implied probability: Opening → Aktuell (Differenz in Prozentpunkten).</div>
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


