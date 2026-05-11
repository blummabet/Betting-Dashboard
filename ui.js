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

  document.getElementById('mainContent').style.display        = isSeason     ? '' : 'none';
  document.getElementById('resultsPanel').style.display       = isResults    ? '' : 'none';
  document.getElementById('heartPanel').style.display         = isHeart      ? '' : 'none';
  document.getElementById('statusPanel').style.display        = isStatus     ? '' : 'none';
  document.getElementById('polymarketPanel').style.display    = isPolymarket ? '' : 'none';
  document.getElementById('trackingV2Panel').style.display    = isTracking   ? '' : 'none';

  document.querySelector('.league-nav').style.display         = isSeason     ? '' : 'none';
  const legend = document.querySelector('.legend-section');
  if (legend) legend.style.display = isSeason ? '' : 'none';

  document.getElementById('navSeason').classList.toggle('active',     isSeason);
  document.getElementById('navResults').classList.toggle('active',    isResults);
  document.getElementById('navHeart').classList.toggle('active',      isHeart);
  document.getElementById('navStatus').classList.toggle('active',     isStatus);
  document.getElementById('navPolymarket').classList.toggle('active', isPolymarket);
  document.getElementById('navTracking').classList.toggle('active',   isTracking);

  if (isResults)    initResults();
  if (isStatus)     { initStatus(); buildValidatorDates(); }
  if (isPolymarket) initPolymarket();
  if (isTracking && typeof initResultsV2 === 'function') initResultsV2();
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


