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
let _polyTraderFilter = { signal: 'all', market: 'all', maxDays: 10, actionableOnly: false };
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
  const allSignals   = candidates.filter(c => c.signal);
  const actionable   = candidates.filter(c => c.is_actionable);
  const sharpCount   = candidates.filter(c => c.signal === 'SHARP' || c.signal === 'BOTH').length;
  const clvCount     = candidates.filter(c => c.signal === 'CLV+' || c.signal === 'BOTH').length;
  const posDeltas    = candidates.filter(c => (c.poly_delta_pp||0) > 0);
  const avgPosDelta  = posDeltas.length ? (posDeltas.reduce((s,c) => s+(c.poly_delta_pp||0),0)/posDeltas.length).toFixed(1) : '—';

  // ── Filter + sort ────────────────────────────────────────────────────────
  let rows = candidates.filter(c => {
    if (_polyTraderFilter.actionableOnly && !c.is_actionable) return false;
    if (_polyTraderFilter.signal !== 'all' && c.signal !== _polyTraderFilter.signal) return false;
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
  function _signalBadge(sig, actionable) {
    if (!sig) return '<span style="font-size:10px;color:#6b7a8d">—</span>';
    const cfg = {
      'BOTH':  { bg:'#00d4a118', bc:'#00d4a140', col:'#00d4a1', lbl:'★ BOTH'  },
      'SHARP': { bg:'#58a6ff12', bc:'#58a6ff40', col:'#58a6ff', lbl:'⚡ SHARP' },
      'CLV+':  { bg:'#a78bfa12', bc:'#a78bfa40', col:'#a78bfa', lbl:'📐 CLV+'  },
    }[sig] || { bg:'#ffffff08', bc:'#ffffff15', col:'#8b9ab0', lbl: sig };
    const actTag = actionable ? `<span style="color:#3fb950;font-size:9px;margin-left:4px">✓ ACT</span>` : '';
    return `<span style="background:${cfg.bg};border:1px solid ${cfg.bc};color:${cfg.col};font-size:10px;font-weight:700;padding:2px 7px;border-radius:6px;white-space:nowrap">${cfg.lbl}${actTag}</span>`;
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

  const tableRows = rows.map(c => {
    const kDate = c.kickoffDate ? c.kickoffDate.slice(5).replace('-','.') : '—';
    const dLbl  = (c.daysOut||0) <= 1 ? `<span style="color:#e3b341;font-size:10px">Heute/Mor.</span>` : `<span style="font-size:10px;color:#6b7a8d">${c.daysOut}d</span>`;
    const rowBg = c.is_actionable ? 'background:rgba(0,212,161,.03);border-left:2px solid #00d4a130' : '';
    const polyLink = c.eventUrl ? `<a href="${c.eventUrl}" target="_blank" style="color:#58a6ff;font-size:10px;margin-left:4px;opacity:.7">🔗</a>` : '';
    const gapCol = (c.gap_pp||0) > 4 ? '#00d4a1' : (c.gap_pp||0) > 2 ? '#e3b341' : '#6b7a8d';
    const obsCol = (c.obs_pnl_pp||0) > 0 ? '#3fb950' : (c.obs_pnl_pp||0) < 0 ? '#f85149' : '#6b7a8d';

    return `<tr style="border-bottom:1px solid #1a2535;${rowBg}">
      <td style="padding:9px 8px;font-weight:600;white-space:nowrap;font-size:12px">${_tierBadge(c.liq_tier)} ${c.home} vs ${c.away}${polyLink}</td>
      <td style="padding:9px 8px;white-space:nowrap">${kDate} ${dLbl}</td>
      <td style="padding:9px 8px;font-size:11px;color:#8b9ab0">${c.market}</td>
      <td style="padding:9px 8px;text-align:center">${_pp(c.bookie_move_pp, 5)}</td>
      <td style="padding:9px 8px;text-align:center;color:#6b7a8d">${c.poly_open != null ? c.poly_open.toFixed(1)+'%' : '—'}</td>
      <td style="padding:9px 8px;text-align:center;font-weight:700">${c.poly_cur != null ? c.poly_cur.toFixed(1)+'%' : '—'}</td>
      <td style="padding:9px 8px;text-align:center"><span style="color:${gapCol};font-weight:700">${c.gap_pp != null ? (c.gap_pp>0?'+':'')+c.gap_pp.toFixed(1)+'pp' : '—'}</span></td>
      <td style="padding:9px 8px;text-align:center">${_dirBadge(c.trade_direction)}</td>
      <td style="padding:9px 8px;text-align:center">${_signalBadge(c.signal, c.is_actionable)}</td>
      <td style="padding:9px 8px;text-align:center"><span style="color:${obsCol};font-weight:700">${c.obs_pnl_pp != null ? (c.obs_pnl_pp>0?'+':'')+c.obs_pnl_pp.toFixed(1)+'pp' : '—'}</span></td>
    </tr>`;
  }).join('');

  const noRows = rows.length === 0
    ? `<tr><td colspan="10" style="text-align:center;padding:40px;color:#6b7a8d">Keine Kandidaten für aktuelle Filter</td></tr>` : '';

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
  <div style="background:#0f1419;border:1px solid #00d4a130;border-radius:12px;padding:14px;text-align:center">
    <div style="font-size:26px;font-weight:800;color:#00d4a1">${actionable.length}</div>
    <div style="font-size:11px;color:#6b7a8d;margin-top:3px">✓ Actionable</div>
  </div>
  <div style="background:#0f1419;border:1px solid #58a6ff25;border-radius:12px;padding:14px;text-align:center">
    <div style="font-size:26px;font-weight:800;color:#58a6ff">${sharpCount}</div>
    <div style="font-size:11px;color:#6b7a8d;margin-top:3px">⚡ SHARP</div>
  </div>
  <div style="background:#0f1419;border:1px solid #a78bfa25;border-radius:12px;padding:14px;text-align:center">
    <div style="font-size:26px;font-weight:800;color:#a78bfa">${clvCount}</div>
    <div style="font-size:11px;color:#6b7a8d;margin-top:3px">📐 CLV+</div>
  </div>
  <div style="background:#0f1419;border:1px solid #3fb95025;border-radius:12px;padding:14px;text-align:center">
    <div style="font-size:26px;font-weight:800;color:#3fb950">${typeof avgPosDelta === 'string' && avgPosDelta !== '—' && parseFloat(avgPosDelta) > 0 ? '+' : ''}${avgPosDelta}pp</div>
    <div style="font-size:11px;color:#6b7a8d;margin-top:3px">∅ Poly-Delta</div>
  </div>
</div>

<!-- ── Filters ────────────────────────────────────────────── -->
<div style="background:#0f1419;border:1px solid #1e2d3d;border-radius:12px;padding:12px 16px;margin-bottom:14px;display:flex;flex-wrap:wrap;gap:10px;align-items:center">
  <span style="font-size:11px;color:#6b7a8d;text-transform:uppercase;letter-spacing:.5px">Filter</span>
  <label style="display:flex;align-items:center;gap:6px;font-size:12px;color:${_polyTraderFilter.actionableOnly?'#00d4a1':'#8b9ab0'};cursor:pointer;padding:4px 10px;border-radius:7px;border:1px solid ${_polyTraderFilter.actionableOnly?'#00d4a140':'#243040'};background:${_polyTraderFilter.actionableOnly?'#00d4a110':'transparent'}">
    <input type="checkbox" ${_polyTraderFilter.actionableOnly?'checked':''} onchange="ptFilterActionable(this.checked)" style="accent-color:#00d4a1"> Nur Actionable
  </label>
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
    Max. Tage bis Kickoff:
    <input type="range" min="1" max="10" value="${_polyTraderFilter.maxDays}" oninput="ptFilterDays(this.value);document.getElementById('ptDaysLbl').textContent=this.value" style="width:70px">
    <span id="ptDaysLbl" style="color:#00d4a1;font-weight:700;min-width:16px">${_polyTraderFilter.maxDays}</span>
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
          ${_sortTh('Bookie Δ', 'bookie_move_pp', true)}
          ${_sortTh('Poly Open', 'poly_open', true)}
          ${_sortTh('Poly Aktuell', 'poly_cur', true)}
          ${_sortTh('Gap', 'gap_pp', true)}
          ${_sortTh('Trade', 'trade_direction', true)}
          ${_sortTh('Signal', 'signal', true)}
          ${_sortTh('Obs. P&L', 'obs_pnl_pp', true)}
        </tr>
      </thead>
      <tbody>${tableRows || noRows}</tbody>
    </table>
  </div>
</div>

<!-- ══════════════════════════════════════════════════════════
     LOGIK & KRITERIEN DOKUMENTATION
     ════════════════════════════════════════════════════════ -->
<div style="background:#0f1419;border:1px solid #1e2d3d;border-radius:14px;padding:20px 24px;margin-bottom:14px">
  <div style="font-size:13px;font-weight:700;color:#e8edf3;margin-bottom:18px;display:flex;align-items:center;gap:8px">
    <span style="background:#00d4a115;border:1px solid #00d4a130;border-radius:8px;padding:4px 8px;font-size:16px">📋</span>
    Logik & Kriterien — Wie Signale entstehen
  </div>

  <!-- Das Konzept -->
  <div style="margin-bottom:20px">
    <div style="font-size:11px;font-weight:700;color:#00d4a1;text-transform:uppercase;letter-spacing:.6px;margin-bottom:10px">Das Konzept</div>
    <div style="font-size:12px;color:#8b9ab0;line-height:1.8;background:#141b22;border-radius:10px;padding:14px 16px;border:1px solid #1e2d3d">
      Polymarket ist ein dezentraler Vorhersagemarkt — Preise bewegen sich nur wenn jemand tradet.
      Pinnacle (scharfer Buchmacher) repriced sofort durch institutionelles Kapital.
      Dieses <strong style="color:#e8edf3">Timing-Gap von 6–36 Stunden</strong> ist die Edge: Wir kaufen auf Poly bevor Poly den Pinnacle-Preis widerspiegelt,
      und verkaufen wenn Poly nachgezogen hat — <strong style="color:#e8edf3">unabhängig vom Spielausgang</strong>.
    </div>
  </div>

  <!-- Signal-Typen -->
  <div style="margin-bottom:20px">
    <div style="font-size:11px;font-weight:700;color:#00d4a1;text-transform:uppercase;letter-spacing:.6px;margin-bottom:10px">Signal-Typen</div>
    <div style="display:grid;gap:8px">
      <div style="background:#141b22;border:1px solid #58a6ff25;border-radius:10px;padding:12px 14px">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
          <span style="background:#58a6ff15;border:1px solid #58a6ff35;color:#58a6ff;font-size:10px;font-weight:700;padding:2px 8px;border-radius:5px">⚡ SHARP</span>
          <span style="font-size:11px;color:#6b7a8d">Mindest-Bookie-Bewegung: <strong style="color:#e8edf3">≥5pp</strong> · Poly-Gap noch offen: <strong style="color:#e8edf3">≥2pp</strong></span>
        </div>
        <div style="font-size:11px;color:#8b9ab0;line-height:1.6">Pinnacle hat die Linie seit Opening um ≥5pp bewegt. Das bedeutet Sharp Money (Profi-Kapital) hat die Seite gekauft. Poly hinkt nach. <em>Nur wenn der Gap noch ≥2pp offen ist — sonst hat Poly schon repriced und das Fenster ist zu.</em></div>
      </div>
      <div style="background:#141b22;border:1px solid #a78bfa25;border-radius:10px;padding:12px 14px">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
          <span style="background:#a78bfa15;border:1px solid #a78bfa35;color:#a78bfa;font-size:10px;font-weight:700;padding:2px 8px;border-radius:5px">📐 CLV+</span>
          <span style="font-size:11px;color:#6b7a8d">Gap Pinnacle-Implied vs. Poly-Preis: <strong style="color:#e8edf3">≥4pp</strong></span>
        </div>
        <div style="font-size:11px;color:#8b9ab0;line-height:1.6">Die aktuelle Pinnacle-Fair-Quote impliziert eine höhere Wahrscheinlichkeit als der Poly-Preis zeigt. Poly ist gegenüber Pinnacle underpriced. <em>Kein Bookie-Move nötig — der Gap kann auch strukturell seit Opening bestehen.</em></div>
      </div>
      <div style="background:#141b22;border:1px solid #00d4a125;border-radius:10px;padding:12px 14px">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
          <span style="background:#00d4a115;border:1px solid #00d4a135;color:#00d4a1;font-size:10px;font-weight:700;padding:2px 8px;border-radius:5px">★ BOTH</span>
          <span style="font-size:11px;color:#6b7a8d">SHARP + CLV+ gleichzeitig → stärkster Entry</span>
        </div>
        <div style="font-size:11px;color:#8b9ab0;line-height:1.6">Bookie hat sich bewegt UND der Gap ist noch offen. Höchste Priorität — Poly hat noch nicht nachgezogen obwohl der Markt sich bereits bewegt hat.</div>
      </div>
    </div>
  </div>

  <!-- Actionability-Kriterien -->
  <div style="margin-bottom:20px">
    <div style="font-size:11px;font-weight:700;color:#00d4a1;text-transform:uppercase;letter-spacing:.6px;margin-bottom:10px">✓ Actionable — alle 3 müssen zutreffen</div>
    <div style="background:#141b22;border:1px solid #3fb95020;border-radius:10px;padding:12px 16px">
      <div style="display:grid;grid-template-columns:auto 1fr;gap:6px 12px;font-size:11px;color:#8b9ab0;line-height:1.7">
        <span style="color:#3fb950;font-weight:700">① Gap ≥2pp</span><span>Der Abstand zwischen Pinnacle-Implied und Poly-Preis ist noch offen. Wenn Gap &lt;2pp: Poly hat repriced, Fenster zu.</span>
        <span style="color:#3fb950;font-weight:700">② Preis 15–85%</span><span>Poly-Preis im liquiden Bereich. Preise &lt;15% oder &gt;85% haben hohen Bid-Ask-Spread relativ zur Bewegung und dünne Liquidität.</span>
        <span style="color:#3fb950;font-weight:700">③ Kickoff ≥0d</span><span>Spiel hat noch nicht stattgefunden. Vergangene Spiele werden automatisch nach 2 Tagen aus dem System entfernt.</span>
      </div>
    </div>
  </div>

  <!-- Trade Direction -->
  <div style="margin-bottom:20px">
    <div style="font-size:11px;font-weight:700;color:#00d4a1;text-transform:uppercase;letter-spacing:.6px;margin-bottom:10px">Trade Direction</div>
    <div style="background:#141b22;border:1px solid #1e2d3d;border-radius:10px;padding:12px 16px;display:grid;grid-template-columns:1fr 1fr;gap:12px;font-size:11px">
      <div>
        <span style="color:#3fb950;font-weight:700">BUY YES ▲</span>
        <div style="color:#8b9ab0;margin-top:4px;line-height:1.6">Bookie-Quote kürzer geworden (Implied gestiegen) = Profis haben das Outcome gekauft. Outcome ist jetzt wahrscheinlicher. → Kaufe den Yes-Token auf Poly.</div>
      </div>
      <div>
        <span style="color:#f85149;font-weight:700">BUY NO ▼</span>
        <div style="color:#8b9ab0;margin-top:4px;line-height:1.6">Bookie-Quote länger geworden (Implied gefallen) = Profis haben die Gegenseite gekauft. Outcome ist jetzt unwahrscheinlicher. → Kaufe den No-Token (oder fade die Position).</div>
      </div>
    </div>
  </div>

  <!-- Ligen & Liquiditäts-Tier -->
  <div style="margin-bottom:20px">
    <div style="font-size:11px;font-weight:700;color:#00d4a1;text-transform:uppercase;letter-spacing:.6px;margin-bottom:10px">Ligen & Liquiditäts-Tier</div>
    <div style="background:#141b22;border:1px solid #1e2d3d;border-radius:10px;padding:12px 16px;font-size:11px;color:#8b9ab0;line-height:1.8">
      <div style="display:grid;grid-template-columns:auto 1fr;gap:4px 16px">
        <span style="color:#3fb950;font-weight:700">T1 — Liquid</span><span>Premier League, Bundesliga, Serie A, La Liga, Ligue 1 — Größte Poly-Märkte, engster Spread, schnellste Repricing.</span>
        <span style="color:#e3b341;font-weight:700">T2 — Mittel</span><span>Eredivisie, Primeira Liga, 2. Bundesliga, Championship — Mittelgroße Märkte, 1–3pp Spread normal.</span>
        <span style="color:#f85149;font-weight:700">T3 — Dünn</span><span>Süper Lig, Scottish Premiership — Kleinste Märkte, höchster Slippage-Risiko bei &gt;100 USDC.</span>
      </div>
    </div>
  </div>

  <!-- Kostenstruktur & Break-Even -->
  <div style="margin-bottom:20px">
    <div style="font-size:11px;font-weight:700;color:#00d4a1;text-transform:uppercase;letter-spacing:.6px;margin-bottom:10px">Kosten & Break-Even</div>
    <div style="background:#141b22;border:1px solid #1e2d3d;border-radius:10px;padding:12px 16px;font-size:11px;color:#8b9ab0;line-height:1.8">
      <div style="display:grid;grid-template-columns:auto 1fr;gap:4px 16px">
        <span style="color:#e8edf3;font-weight:600">Bid-Ask Spread</span><span>1–3pp auf Poly (je nach Markt). Größter Kostenfaktor.</span>
        <span style="color:#e8edf3;font-weight:600">Slippage</span><span>~0.5pp bei Market-Orders. Limit-Orders auf Best-Bid verwenden.</span>
        <span style="color:#e8edf3;font-weight:600">Gas-Kosten</span><span>~0.01–0.05 USDC/Trade auf Polygon. Vernachlässigbar.</span>
        <span style="color:#00d4a1;font-weight:700">Break-Even</span><span><strong style="color:#00d4a1">≥5pp Poly-Bewegung</strong> nötig für Profit nach allen Kosten. Unsere Signale (≥4pp Gap) sind knapp im profitablen Bereich. SHARP ≥8pp klar profitabel.</span>
      </div>
    </div>
  </div>

  <!-- Was wir noch verbessern können -->
  <div>
    <div style="font-size:11px;font-weight:700;color:#e3b341;text-transform:uppercase;letter-spacing:.6px;margin-bottom:10px">⚠ Bekannte Limitierungen & nächste Verbesserungen</div>
    <div style="background:#141b22;border:1px solid #e3b34120;border-radius:10px;padding:12px 16px;font-size:11px;color:#8b9ab0;line-height:1.8">
      <div style="display:grid;gap:6px">
        <div><span style="color:#e3b341;font-weight:600">Poly-Delta = 0</span> — Solange nur 1 Snapshot existiert ist Open = Current. Delta baut sich über Zeit auf. Erst ab ~3 Tagen aussagekräftig.</div>
        <div><span style="color:#e3b341;font-weight:600">Keine Zeitstempel für Bookie-Move</span> — Wir wissen nicht wann sich Pinnacle bewegt hat (nur um wie viel). Ideal: Bookie-Move-Zeitpunkt erfassen um Entry-Fenster präziser zu bestimmen.</div>
        <div><span style="color:#e3b341;font-weight:600">Over/Under und BTTS ohne Pinnacle-Fair-Key</span> — CLV+ Signal nur für 1X2 + Over 2.5 möglich (haben pinn_fair). Andere Märkte: nur Poly-Tracking ohne Bookie-Vergleich.</div>
        <div><span style="color:#e3b341;font-weight:600">Kein Exit-Signal</span> — Aktuell kein automatischer "Jetzt verkaufen"-Trigger. Geplant: Exit wenn Gap &lt;1pp oder Poly-Delta ≥ 80% der Bookie-Bewegung.</div>
        <div><span style="color:#e3b341;font-weight:600">Liquiditäts-Tier ist statisch</span> — T1/T2/T3 nach Liga hardcodiert. Besser wäre live Poly-Volume pro Markt. Folgt in Phase 2.</div>
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


