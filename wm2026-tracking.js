// ═══════════════════════════════════════════════════════
//  wm2026-tracking.js — WM 2026 Pick Tracking
//
//  Entry point: window.initIntlTracking()
//    Called from ui.js showView('intl-tracking')
//
//  Single source of truth: wm2026-data.json
//    Same file as the cards tab — no localStorage, no buffer.
//    Picks are frozen at kickoff by the data layer (Python scripts
//    do not update picks for games that have already kicked off).
//
//  Result fields (added by Python scripts when games finish):
//    pick.result  → 'won' | 'lost' | 'push' | null
//
//  KPIs (per filter set):
//    Total picks · BET% · Win rate · Avg odds · ROI · P&L (€10/pick)
// ═══════════════════════════════════════════════════════

(function () {
  'use strict';

  const STAKE = 10; // € per pick for P&L calculation

  // ── Module state ───────────────────────────────────────
  let _data      = null;
  let _loaded    = false;
  let _grpFilter = 'all';
  let _mdFilter  = 'all';    // 'all' | 1 | 2 | 3
  let _vrdFilter = 'all';    // 'all' | 'BET' | 'ABWÄGEN' | 'SKIP'
  let _showTop   = false;    // toggle for Top Picks section

  // ─────────────────────────────────────────────────────
  //  ENTRY POINT
  // ─────────────────────────────────────────────────────
  window.initIntlTracking = async function () {
    const panel = document.getElementById('intlTrackingPanel');
    if (!panel) return;

    if (_loaded && _data) {
      _render();
      return;
    }

    panel.innerHTML = `
      <div style="text-align:center;padding:60px 16px;color:var(--muted);">
        <div style="font-size:36px;margin-bottom:14px;animation:spin 1.2s linear infinite;display:inline-block;">⚙️</div>
        <div style="font-size:13px;font-weight:600;">Lade WM 2026 Picks…</div>
      </div>`;

    try {
      const resp = await fetch('wm2026-data.json?t=' + Date.now());
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      _data   = await resp.json();
      _loaded = true;
      _render();
    } catch (e) {
      panel.innerHTML = `
        <div style="text-align:center;padding:60px 16px;color:var(--muted);">
          <div style="font-size:40px;margin-bottom:16px;">⚠️</div>
          <div style="font-size:15px;font-weight:700;color:var(--red);">Daten konnten nicht geladen werden</div>
          <div style="font-size:12px;margin-top:8px;">${e.message}</div>
          <button onclick="window.initIntlTracking()" style="margin-top:18px;background:var(--accent);color:#000;border:none;border-radius:8px;padding:8px 20px;font-size:13px;font-weight:700;cursor:pointer;">Erneut versuchen</button>
        </div>`;
    }
  };

  // Filter callbacks (called from inline onclick)
  window.wmTrkSetGroup   = g  => { _grpFilter = g;  _render(); };
  window.wmTrkSetMd      = md => { _mdFilter  = md; _render(); };
  window.wmTrkSetVerdict = v  => { _vrdFilter = v;  _render(); };
  window.wmTrkToggleTop  = () => { _showTop = !_showTop; _render(); };
  window.wmTrkRefresh    = () => { _loaded = false; _data = null; window.initIntlTracking(); };

  // ─────────────────────────────────────────────────────
  //  MAIN RENDER
  // ─────────────────────────────────────────────────────
  function _render() {
    const panel = document.getElementById('intlTrackingPanel');
    if (!panel || !_data) return;

    const groups      = _data.groups      || {};
    const allPicks    = _data.picks        || {};
    const playerPicks = _data.playerPicks  || {};
    const groupKeys   = Object.keys(groups).sort();
    const todayIso    = new Date().toISOString().slice(0, 10);
    const nowTime     = new Date().toTimeString().slice(0, 5); // HH:MM

    // ── Collect all fixture-pick rows ─────────────────
    // Each row = { fx, groupKey, home, away, homeTeam, awayTeam, picks[], isLocked }
    // isLocked = kickoff has passed → picks frozen (no editing in data layer)
    const rows = [];

    for (const [gKey, gData] of Object.entries(groups)) {
      const teams = gData.teams || [];
      const teamMap = Object.fromEntries(teams.map(t => [t.id, t]));

      for (const fx of (gData.fixtures || [])) {
        const pickKey  = `${gKey}-${fx.matchday}-${fx.home}-${fx.away}`;
        const fxPicks  = allPicks[pickKey]    || [];
        const fxPPicks = playerPicks[pickKey] || [];
        const combined = [
          ...fxPicks.map(p  => ({ ...p, _isPlayer: false })),
          ...fxPPicks.map(p => ({ ...p, _isPlayer: true  })),
        ];

        if (!combined.length) continue; // no picks → skip

        const isToday  = fx.date === todayIso;
        const isPast   = fx.date < todayIso;
        // Frozen = kickoff has passed (date is today and time ≤ now, or date is in the past)
        const isLocked = isPast || (isToday && fx.time && fx.time <= nowTime);

        rows.push({
          fx:       { ...fx, groupKey: gKey },
          gData,
          homeTeam: teamMap[fx.home] || { id: fx.home, name: fx.home, flag: '🏳' },
          awayTeam: teamMap[fx.away] || { id: fx.away, name: fx.away, flag: '🏳' },
          picks:    combined,
          isLocked,
        });
      }
    }

    // Sort by date → time → matchday
    rows.sort((a, b) => {
      if (a.fx.date !== b.fx.date) return a.fx.date.localeCompare(b.fx.date);
      if (a.fx.time && b.fx.time)  return a.fx.time.localeCompare(b.fx.time);
      return a.fx.matchday - b.fx.matchday;
    });

    // ── Apply filters ─────────────────────────────────
    let filtered = rows;
    if (_grpFilter !== 'all') filtered = filtered.filter(r => r.fx.groupKey === _grpFilter);
    if (_mdFilter  !== 'all') filtered = filtered.filter(r => r.fx.matchday === +_mdFilter);

    // Flatten picks for filtered set (apply verdict filter)
    const flatPicks = [];
    for (const row of filtered) {
      for (const p of row.picks) {
        if (_vrdFilter === 'all' || p.verdict === _vrdFilter) {
          flatPicks.push({ ...p, _row: row });
        }
      }
    }

    // Top Picks = BET verdict
    const topPicks = flatPicks.filter(p => p.verdict === 'BET');

    // ─── Build HTML ────────────────────────────────────
    let html = '';

    // ─── Header ───────────────────────────────────────
    html += `
    <div class="wm-header">
      <div class="wm-header-left">
        <div class="wm-title">📊 WM 2026 Tracking</div>
        <div class="wm-subtitle">Alle Picks aus den Cards · Eingefroren bei Kickoff · €${STAKE}/Pick</div>
      </div>
      <div class="wm-header-right">
        <button onclick="wmTrkRefresh()" style="background:var(--surface2);border:1px solid var(--border);color:var(--text);border-radius:6px;padding:5px 12px;font-size:11px;font-weight:600;cursor:pointer;">🔄 Aktualisieren</button>
      </div>
    </div>`;

    // ─── Global KPI strip ─────────────────────────────
    html += _buildKpiStrip(flatPicks, 'Alle Picks');

    // ─── Filters ──────────────────────────────────────
    // Group filter
    html += `<div class="wm-group-filter" style="margin-top:12px;">`;
    html += _fBtn('⭐ Alle', 'all', _grpFilter, `wmTrkSetGroup('all')`);
    for (const gKey of groupKeys) {
      const label = (groups[gKey].name || 'Gruppe ?').replace('Gruppe ', '');
      html += _fBtn(`Gr. ${label}`, gKey, _grpFilter, `wmTrkSetGroup('${gKey}')`);
    }
    html += `</div>`;

    // Matchday filter
    html += `<div class="wm-md-filter">`;
    html += _fBtn('Alle Spieltage', 'all', _mdFilter, `wmTrkSetMd('all')`);
    html += _fBtn('Spieltag 1', 1,     _mdFilter, `wmTrkSetMd(1)`);
    html += _fBtn('Spieltag 2', 2,     _mdFilter, `wmTrkSetMd(2)`);
    html += _fBtn('Spieltag 3', 3,     _mdFilter, `wmTrkSetMd(3)`);
    html += `</div>`;

    // Verdict filter
    html += `<div class="wm-trk-vrd-filter">`;
    const vrdOpts = [['all','Alle Verdicts','⭐'],['BET','BET','🟢'],['ABWÄGEN','ABWÄGEN','🟡'],['SKIP','SKIP','🔴']];
    for (const [val, lbl, ico] of vrdOpts) {
      const active = _vrdFilter === val;
      html += `<button class="wm-md-btn${active ? ' active' : ''}" onclick="wmTrkSetVerdict('${val}')">${ico} ${lbl}</button>`;
    }
    html += `</div>`;

    // ─── Top Picks section ────────────────────────────
    if (topPicks.length > 0) {
      const isOpen = _showTop;
      html += `
      <div class="wm-trk-top-section">
        <div class="wm-trk-top-header" onclick="wmTrkToggleTop()" style="cursor:pointer;display:flex;align-items:center;gap:8px;padding:10px 14px;background:rgba(63,185,80,0.08);border:1px solid rgba(63,185,80,0.25);border-radius:10px;margin-bottom:${isOpen ? '10px' : '0'};">
          <span style="font-size:13px;font-weight:700;color:#3fb950;">🏆 Top Picks (BET)</span>
          <span style="background:rgba(63,185,80,0.2);color:#3fb950;border-radius:10px;padding:2px 8px;font-size:11px;font-weight:700;">${topPicks.length} Pick${topPicks.length !== 1 ? 's' : ''}</span>
          <span style="margin-left:auto;font-size:10px;color:var(--muted);">${isOpen ? '▲ Einklappen' : '▼ Ausklappen'}</span>
        </div>`;
      if (isOpen) {
        html += _buildKpiStrip(topPicks, 'Top Picks (BET)');
        html += `<div style="margin-top:10px;">`;
        html += _buildPicksTable(topPicks, todayIso);
        html += `</div>`;
      }
      html += `</div>`;
    }

    // ─── All Picks Table ──────────────────────────────
    if (!flatPicks.length) {
      html += `
      <div style="text-align:center;padding:60px 16px;color:var(--muted);">
        <div style="font-size:36px;margin-bottom:12px;">🔍</div>
        <div style="font-size:14px;font-weight:600;">Keine Picks gefunden</div>
        <div style="font-size:12px;margin-top:6px;">
          ${rows.length === 0 ? 'Es wurden noch keine Picks für die WM 2026 erfasst.' : 'Kein Pick entspricht dem aktuellen Filter.'}
        </div>
      </div>`;
    } else {
      html += `
      <div class="wm-trk-section-title" style="margin-top:18px;">
        📋 Alle Picks
        <span class="wm-trk-count">${flatPicks.length}</span>
      </div>`;
      html += _buildPicksTable(flatPicks, todayIso);
    }

    panel.innerHTML = html;
  }

  // ─────────────────────────────────────────────────────
  //  KPI STRIP
  // ─────────────────────────────────────────────────────
  function _buildKpiStrip(picks, label) {
    const total     = picks.length;
    const resolved  = picks.filter(p => p.result != null);
    const won       = picks.filter(p => p.result === 'won');
    const lost      = picks.filter(p => p.result === 'lost');
    const push      = picks.filter(p => p.result === 'push');
    const pending   = picks.filter(p => p.result == null);

    const nBet      = picks.filter(p => p.verdict === 'BET').length;
    const betPct    = total > 0 ? Math.round(nBet / total * 100) : 0;

    const winRate   = resolved.length > 0 ? Math.round(won.length / (resolved.length - push.length || 1) * 100) : null;
    const avgOdds   = resolved.length > 0
      ? (resolved.reduce((s, p) => s + (p.odds || 1), 0) / resolved.length).toFixed(2)
      : null;

    // P&L: won = profit of (odds-1)*STAKE; lost = -STAKE; push = 0
    let pnl = null;
    if (resolved.length > 0) {
      pnl = won.reduce((s, p) => s + ((p.odds || 1) - 1) * STAKE, 0)
          - lost.length * STAKE;
      pnl = Math.round(pnl * 100) / 100;
    }

    // ROI = P&L / (resolved * STAKE) * 100
    let roi = null;
    if (resolved.length > 0) {
      roi = Math.round(pnl / (resolved.length * STAKE) * 100);
    }

    const pnlColor  = pnl == null ? 'var(--muted)' : pnl >= 0 ? '#3fb950' : '#f85149';
    const roiColor  = roi == null ? 'var(--muted)' : roi >= 0 ? '#3fb950' : '#f85149';

    return `
    <div class="wm-trk-kpi-strip">
      ${_kpi('Picks gesamt', total, 'var(--text)')}
      ${_kpi('BET-Quote', betPct + '%', '#3fb950')}
      ${_kpi('Ausstehend', pending.length, 'var(--muted)')}
      ${_kpi('Gewonnen', won.length, '#3fb950')}
      ${_kpi('Verloren', lost.length, '#f85149')}
      ${_kpi('Push', push.length, '#8b949e')}
      ${_kpi('Trefferquote', winRate != null ? winRate + '%' : '—', winRate != null ? (winRate >= 55 ? '#3fb950' : winRate >= 45 ? '#e3b341' : '#f85149') : 'var(--muted)')}
      ${_kpi('Ø Quoten', avgOdds || '—', 'var(--text)')}
      ${_kpi('ROI', roi != null ? (roi >= 0 ? '+' : '') + roi + '%' : '—', roiColor)}
      ${_kpi('P&L', pnl != null ? (pnl >= 0 ? '+' : '') + '€' + Math.abs(pnl).toFixed(2) : '—', pnlColor)}
    </div>`;
  }

  function _kpi(label, value, color) {
    return `
    <div class="wm-trk-kpi">
      <div class="wm-trk-kpi-val" style="color:${color};">${value}</div>
      <div class="wm-trk-kpi-lbl">${label}</div>
    </div>`;
  }

  // ─────────────────────────────────────────────────────
  //  PICKS TABLE
  //  Groups picks by date, shows match context per row
  // ─────────────────────────────────────────────────────
  function _buildPicksTable(picks, todayIso) {
    // Group by date
    const byDate = {};
    for (const p of picks) {
      const d = p._row.fx.date;
      if (!byDate[d]) byDate[d] = [];
      byDate[d].push(p);
    }

    let html = `<div class="wm-trk-table">`;

    for (const date of Object.keys(byDate).sort()) {
      const isToday   = date === todayIso;
      const isPast    = date < todayIso;
      const isFuture  = date > todayIso;
      const dateLabel = _fmtDate(date);
      const statusBadge = isToday
        ? `<span class="wm-date-today">HEUTE</span>`
        : isPast
          ? `<span style="font-size:9px;background:var(--surface2);color:var(--muted);border-radius:4px;padding:2px 6px;">GESPIELT</span>`
          : `<span style="font-size:9px;background:rgba(63,185,80,0.12);color:#3fb950;border-radius:4px;padding:2px 6px;">AUSSTEHEND</span>`;

      html += `
      <div class="wm-trk-date-block">
        <div class="wm-date-divider">
          <span class="wm-date-divider-text">${dateLabel}</span>
          ${statusBadge}
          <span class="wm-date-divider-line"></span>
        </div>`;

      // Group by fixture within date
      const byFx = {};
      for (const p of byDate[date]) {
        const key = `${p._row.fx.groupKey}-${p._row.fx.matchday}-${p._row.fx.home}-${p._row.fx.away}`;
        if (!byFx[key]) byFx[key] = { row: p._row, picks: [] };
        byFx[key].picks.push(p);
      }

      for (const fxKey of Object.keys(byFx).sort()) {
        const { row, picks: fxPicks } = byFx[fxKey];
        const { fx, homeTeam, awayTeam, isLocked } = row;

        // Fixture header
        const groupStr  = (row.gData.name || `Gruppe ${fx.groupKey}`);
        const timeStr   = fx.time ? fx.time + ' Uhr' : '';
        const lockIcon  = isLocked ? '🔒' : '📋';
        const lockTip   = isLocked ? 'Eingefroren' : 'Ausstehend';

        html += `
        <div class="wm-trk-fx-block">
          <div class="wm-trk-fx-header">
            <span class="wm-trk-fx-teams">${homeTeam.flag} ${homeTeam.name} vs ${awayTeam.flag} ${awayTeam.name}</span>
            <span class="wm-trk-fx-meta">${lockIcon} ${groupStr} · ST${fx.matchday}${timeStr ? ' · ' + timeStr : ''}</span>
          </div>`;

        // Score row (if available)
        if (fx.scoreHome != null && fx.scoreAway != null) {
          html += `<div class="wm-trk-score">${fx.scoreHome} : ${fx.scoreAway}</div>`;
        }

        // Pick rows
        for (const p of fxPicks) {
          html += _buildTrackingRow(p);
        }

        html += `</div>`;
      }

      html += `</div>`; // wm-trk-date-block
    }

    html += `</div>`; // wm-trk-table
    return html;
  }

  // ─────────────────────────────────────────────────────
  //  SINGLE TRACKING ROW
  // ─────────────────────────────────────────────────────
  function _buildTrackingRow(p) {
    const verdict  = p.verdict || 'ABWÄGEN';
    const vClr     = verdict === 'BET' ? '#3fb950' : verdict === 'SKIP' ? '#f85149' : '#e3b341';
    const vBg      = verdict === 'BET' ? 'rgba(63,185,80,.08)' : verdict === 'SKIP' ? 'rgba(248,81,73,.08)' : 'rgba(227,179,65,.08)';

    const conf     = p.conf || 'medium';
    const stars    = conf === 'high' ? '★★★' : conf === 'medium' ? '★★☆' : '★☆☆';
    const starsClr = conf === 'high' ? '#3fb950' : conf === 'medium' ? '#e3b341' : '#8b949e';

    const oddsStr  = p.odds != null ? p.odds.toFixed(2) : '—';

    // Result badge
    let resultBadge = '';
    let rowBorder   = 'var(--border)';
    if (p.result === 'won') {
      resultBadge = `<span class="wm-trk-result won">✅ Gewonnen</span>`;
      rowBorder   = 'rgba(63,185,80,0.35)';
    } else if (p.result === 'lost') {
      resultBadge = `<span class="wm-trk-result lost">❌ Verloren</span>`;
      rowBorder   = 'rgba(248,81,73,0.35)';
    } else if (p.result === 'push') {
      resultBadge = `<span class="wm-trk-result push">🔄 Push</span>`;
      rowBorder   = 'rgba(139,148,158,0.35)';
    } else {
      resultBadge = `<span class="wm-trk-result pending">⏳</span>`;
    }

    // P&L for this pick
    let pnlStr = '';
    if (p.result === 'won')  pnlStr = `<span style="color:#3fb950;font-size:10px;font-weight:700;">+€${(((p.odds||1)-1)*STAKE).toFixed(2)}</span>`;
    if (p.result === 'lost') pnlStr = `<span style="color:#f85149;font-size:10px;font-weight:700;">-€${STAKE.toFixed(2)}</span>`;
    if (p.result === 'push') pnlStr = `<span style="color:var(--muted);font-size:10px;">€0.00</span>`;

    const marketStr = p._isPlayer && p.playerName ? `${p.playerName} — ${p.market}` : p.market;
    const icon      = p.icon || (p._isPlayer ? '⚽' : '🎯');

    return `
    <div class="wm-trk-row" style="border-left:2px solid ${rowBorder};">
      <span class="wm-verdict" style="color:${vClr};background:${vBg};border-color:${vClr}26;font-size:9px;padding:2px 6px;">${verdict}</span>
      <span class="wm-pick-icon" style="font-size:14px;">${icon}</span>
      <div class="wm-trk-row-main">
        <div class="wm-trk-row-market">${marketStr}</div>
        ${p.info ? `<div class="wm-trk-row-info">${p.info}</div>` : ''}
      </div>
      <span class="wm-pick-stars" style="color:${starsClr};font-size:10px;">${stars}</span>
      <span class="wm-trk-row-odds">@ ${oddsStr}</span>
      ${resultBadge}
      ${pnlStr}
    </div>`;
  }

  // ─────────────────────────────────────────────────────
  //  HELPERS
  // ─────────────────────────────────────────────────────
  function _fBtn(label, val, active, onclick) {
    const isActive = active === val || (val === 'all' && active === 'all');
    return `<button class="wm-gf-btn${isActive ? ' active' : ''}" onclick="${onclick}">${label}</button>`;
  }

  const _DAYS   = ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa'];
  const _MONTHS = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez'];

  function _fmtDate(iso) {
    if (!iso) return '';
    const d = new Date(iso + 'T12:00:00');
    return `${_DAYS[d.getDay()]}, ${d.getDate()}. ${_MONTHS[d.getMonth()]}`;
  }

})();
