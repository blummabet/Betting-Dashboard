// ═══════════════════════════════════════════════════════
//  wm2026-renderer.js — WM 2026 International Cards
//  Renders the International > Cards section (intlCardsPanel)
//
//  Entry point: window.initIntlCards()
//    Called from ui.js showView('intl-cards')
//
//  Data sources:
//    wm2026-data.json      — groups, fixtures, picks, squads, form, odds
//    wm_poly_prices.json   — polymarket prices + edge per fixture
// ═══════════════════════════════════════════════════════

(function () {
  'use strict';

  // ── Module state ──────────────────────────────────────
  let _wmData      = null;
  let _polyLookup  = {};   // key: "HOME-AWAY" → poly fixture object
  let _activeGroup = 'all';
  let _activeMd    = 'all';   // matchday filter: 'all' | 1 | 2 | 3
  let _activeSort  = 'date';  // 'date' | 'edge' | 'upset'
  let _loaded      = false;

  const CO_HOSTS = new Set(['MEX', 'USA', 'CAN']);

  // ─────────────────────────────────────────────────────
  //  ENTRY POINT
  // ─────────────────────────────────────────────────────
  window.initIntlCards = async function () {
    const panel = document.getElementById('intlCardsPanel');
    if (!panel) return;

    if (_loaded && _wmData) {
      _render();
      return;
    }

    panel.innerHTML = `
      <div style="text-align:center;padding:60px 16px;color:var(--muted);">
        <div style="font-size:36px;margin-bottom:14px;animation:spin 1.2s linear infinite;display:inline-block;">⚙️</div>
        <div style="font-size:13px;font-weight:600;">Lade WM 2026 Daten…</div>
      </div>`;

    try {
      const [wmResp, polyResp] = await Promise.all([
        fetch('wm2026-data.json?t=' + Date.now()),
        fetch('wm_poly_prices.json?t=' + Date.now()).catch(() => null),
      ]);
      if (!wmResp.ok) throw new Error('HTTP ' + wmResp.status);
      _wmData = await wmResp.json();
      window.WM2026_DATA = _wmData;   // expose for Sharp Radar + other modules

      if (polyResp && polyResp.ok) {
        const polyRaw = await polyResp.json();
        _polyLookup = {};
        for (const f of (polyRaw.allFixtures || [])) {
          _polyLookup[f.key] = f;
        }
      }

      _loaded = true;
      _render();
    } catch (e) {
      panel.innerHTML = `
        <div style="text-align:center;padding:60px 16px;color:var(--muted);">
          <div style="font-size:40px;margin-bottom:16px;">⚠️</div>
          <div style="font-size:15px;font-weight:700;color:var(--red);">Daten konnten nicht geladen werden</div>
          <div style="font-size:12px;margin-top:8px;">${e.message}</div>
          <button onclick="window.initIntlCards()" style="margin-top:18px;background:var(--accent);color:#000;border:none;border-radius:8px;padding:8px 20px;font-size:13px;font-weight:700;cursor:pointer;">Erneut versuchen</button>
        </div>`;
    }
  };

  // ── Group / Matchday filters (called from inline onclick) ─
  window.wmSetGroup = function (gKey) {
    _activeGroup = gKey;
    _render();
  };
  window.wmSetMd = function (md) {
    _activeMd = md;
    _render();
  };
  window.wmSetSort = function (s) {
    _activeSort = s;
    _render();
  };

  // ─────────────────────────────────────────────────────
  //  MAIN RENDER
  // ─────────────────────────────────────────────────────
  function _render() {
    const panel = document.getElementById('intlCardsPanel');
    if (!panel || !_wmData) return;

    const groups    = _wmData.groups || {};
    const groupKeys = Object.keys(groups).sort();

    // ── Collect + sort all fixtures ───────────────────
    let allFx = [];
    for (const [gKey, gData] of Object.entries(groups)) {
      for (const fx of (gData.fixtures || [])) {
        allFx.push({ ...fx, groupKey: gKey, groupData: gData });
      }
    }
    allFx.sort((a, b) => {
      if (a.date !== b.date)         return a.date.localeCompare(b.date);
      if (a.time && b.time)          return a.time.localeCompare(b.time);
      if (a.matchday !== b.matchday) return a.matchday - b.matchday;
      return a.groupKey.localeCompare(b.groupKey);
    });

    // ── Apply filters ─────────────────────────────────
    let filtered = _activeGroup === 'all' ? allFx : allFx.filter(fx => fx.groupKey === _activeGroup);
    if (_activeMd !== 'all') filtered = filtered.filter(fx => fx.matchday === +_activeMd);

    // ── Shared data maps ──────────────────────────────
    const picks       = _wmData.picks       || {};
    const playerPicks = _wmData.playerPicks || {};
    const standings   = _wmData.standings   || {};
    const squads      = _wmData.squads      || {};
    const odds        = _wmData.odds        || {};
    const form        = _wmData.form        || {};

    const todayIso = new Date().toISOString().slice(0, 10);

    // ─────────────────────────────────────────────────
    //  HTML BUILD
    // ─────────────────────────────────────────────────
    let html = '';

    // ─── Tournament Header ────────────────────────────
    const daysUntil = Math.ceil((new Date('2026-06-11') - new Date(todayIso)) / 86400000);
    const countdownStr = daysUntil > 0
      ? `<span class="wm-countdown">⏳ ${daysUntil} Tage bis zum Anpfiff</span>`
      : daysUntil === 0
        ? `<span class="wm-countdown wm-countdown-live">🔴 Heute startet die WM!</span>`
        : `<span class="wm-countdown wm-countdown-live">🔴 WM läuft</span>`;

    // Quick stats for header
    const totalPicks = Object.values(picks).flat().filter(p => p.verdict === 'BET' || p.verdict === 'ABWÄGEN').length;
    const polyCount  = Object.keys(_polyLookup).length;

    html += `
    <div class="wm-header">
      <div class="wm-header-left">
        <div class="wm-title">🌍 FIFA WM 2026</div>
        <div class="wm-subtitle">USA · Canada · Mexico · 48 Teams · 104 Spiele · 11. Jun – 19. Jul</div>
      </div>
      <div class="wm-header-right">
        ${countdownStr}
        ${totalPicks > 0 ? `<span style="font-size:10px;font-weight:700;color:var(--accent);">${totalPicks} Picks</span>` : ''}
        ${polyCount > 0 ? `<span style="font-size:10px;font-weight:700;color:#a78bfa;">${polyCount} Poly-Märkte</span>` : ''}
      </div>
    </div>`;

    // ─── Group Filter ─────────────────────────────────
    html += `<div class="wm-group-filter">`;
    html += `<button class="wm-gf-btn${_activeGroup === 'all' ? ' active' : ''}" onclick="wmSetGroup('all')">⭐ Alle</button>`;
    for (const gKey of groupKeys) {
      const gLabel = groups[gKey].name.replace('Gruppe ', '');
      // Count picks in this group
      const gPicks = Object.entries(picks)
        .filter(([k]) => k.startsWith(gKey + '-'))
        .flatMap(([, v]) => v)
        .filter(p => p.verdict === 'BET').length;
      html += `<button class="wm-gf-btn${_activeGroup === gKey ? ' active' : ''}" onclick="wmSetGroup('${gKey}')">Gr. ${gLabel}${gPicks ? ` <span style="font-size:8px;background:rgba(63,185,80,.2);color:#3fb950;border-radius:4px;padding:0 4px;">${gPicks}</span>` : ''}</button>`;
    }
    html += `</div>`;

    // ─── Matchday Filter ─────────────────────────────
    html += `<div class="wm-md-filter">`;
    html += `<button class="wm-md-btn${_activeMd === 'all' ? ' active' : ''}" onclick="wmSetMd('all')">Alle Spieltage</button>`;
    html += `<button class="wm-md-btn${_activeMd === 1 ? ' active' : ''}" onclick="wmSetMd(1)">Spieltag 1</button>`;
    html += `<button class="wm-md-btn${_activeMd === 2 ? ' active' : ''}" onclick="wmSetMd(2)">Spieltag 2</button>`;
    html += `<button class="wm-md-btn${_activeMd === 3 ? ' active' : ''}" onclick="wmSetMd(3)">Spieltag 3</button>`;
    html += `</div>`;

    // ─── Sort control ────────────────────────────────
    html += `
    <div class="wm-sort-bar">
      <span class="wm-sort-lbl">Sortierung:</span>
      <button class="wm-sort-btn${_activeSort==='date'?' active':''}" onclick="wmSetSort('date')">📅 Datum</button>
      <button class="wm-sort-btn${_activeSort==='edge'?' active':''}" onclick="wmSetSort('edge')">⚡ Edge</button>
      <button class="wm-sort-btn${_activeSort==='upset'?' active':''}" onclick="wmSetSort('upset')">💥 Upset</button>
    </div>`;

    // Apply sort
    if (_activeSort === 'edge') {
      filtered = [...filtered].sort((a, b) => {
        const pa = picks[`${a.groupKey}-${a.matchday}-${a.home}-${a.away}`] || [];
        const pb = picks[`${b.groupKey}-${b.matchday}-${b.home}-${b.away}`] || [];
        const ea = Math.max(...pa.map(p => p.edgePP || 0), 0);
        const eb = Math.max(...pb.map(p => p.edgePP || 0), 0);
        return eb - ea;
      });
    } else if (_activeSort === 'upset') {
      const us = _wmData.upsetScores || {};
      filtered = [...filtered].sort((a, b) => {
        const ua = us[`${a.groupKey}-${a.matchday}-${a.home}-${a.away}`] || 0;
        const ub = us[`${b.groupKey}-${b.matchday}-${b.home}-${b.away}`] || 0;
        return ub - ua;
      });
    }

    // ─── Cards ───────────────────────────────────────
    if (!filtered.length) {
      html += `<div style="text-align:center;padding:48px 16px;color:var(--muted);">Keine Spiele gefunden.</div>`;
    } else {
      let lastDate = null;
      html += `<div class="wm-cards-wrap">`;
      for (const fx of filtered) {
        // Date divider
        if (fx.date !== lastDate) {
          const isFuture  = fx.date > todayIso;
          const isToday   = fx.date === todayIso;
          const dateLabel = _fmtDate(fx.date, null);
          const dateBadge = isToday
            ? `<span class="wm-date-today">HEUTE</span>`
            : isFuture
              ? `<span class="wm-date-upcoming">${_daysFrom(fx.date, todayIso)}</span>`
              : '';
          html += `
          <div class="wm-date-divider">
            <span class="wm-date-divider-text">${dateLabel}</span>
            ${dateBadge}
            <span class="wm-date-divider-line"></span>
          </div>`;
          lastDate = fx.date;
        }

        const fxOdds   = odds[`${fx.home}-${fx.away}`]    || null;
        const fxPicks  = picks[`${fx.groupKey}-${fx.matchday}-${fx.home}-${fx.away}`]       || [];
        const fxPPicks = playerPicks[`${fx.groupKey}-${fx.matchday}-${fx.home}-${fx.away}`] || [];
        const fxStand  = standings[fx.groupKey]  || null;
        const gData    = fx.groupData;
        const teams    = gData.teams || [];
        const homeTeam = teams.find(t => t.id === fx.home) || { id: fx.home, name: fx.home, flag: '🏳', elo: null };
        const awayTeam = teams.find(t => t.id === fx.away) || { id: fx.away, name: fx.away, flag: '🏳', elo: null };
        const homeSquad = squads[fx.home] || null;
        const awaySquad = squads[fx.away] || null;
        const homeForm  = form[fx.home]   || null;
        const awayForm  = form[fx.away]   || null;
        const polyFix   = _polyLookup[`${fx.home}-${fx.away}`] || null;

        html += _buildCard(fx, gData, homeTeam, awayTeam, fxOdds, fxPicks, fxPPicks, fxStand, homeSquad, awaySquad, homeForm, awayForm, polyFix, todayIso);
      }
      html += `</div>`;
    }

    panel.innerHTML = html;
  }

  // ─────────────────────────────────────────────────────
  //  CARD BUILDER
  // ─────────────────────────────────────────────────────
  function _buildCard(fx, gData, home, away, fxOdds, fxPicks, fxPPicks, standing, homeSquad, awaySquad, homeForm, awayForm, polyFix, todayIso) {
    const eloDiff  = (home.elo && away.elo) ? (home.elo - away.elo) : null;
    const isPlayed = fx.date < todayIso;
    const isToday  = fx.date === todayIso;

    // Sort picks: BET first, then by edgePP desc
    const sortedPicks = [...fxPicks].sort((a, b) => {
      if (a.verdict === 'BET' && b.verdict !== 'BET') return -1;
      if (b.verdict === 'BET' && a.verdict !== 'BET') return 1;
      return (b.edgePP || 0) - (a.edgePP || 0);
    });
    const hasBet    = fxPicks.some(p => p.verdict === 'BET');
    const hasPicks  = fxPicks.length > 0;
    const hasPlayer = fxPPicks.length > 0;

    // Card accent — green only for BET, yellow for ABWÄGEN, purple for player, amber for today
    const accentColor = hasBet ? '#3fb950'
                      : hasPicks ? '#e3b341'
                      : hasPlayer ? '#a78bfa'
                      : isToday ? '#e3b341'
                      : 'transparent';

    const xgStats = _wmData.xgStats || {};
    const homeXg  = xgStats[fx.home] || null;
    const awayXg  = xgStats[fx.away] || null;
    const upsetScores = _wmData.upsetScores || {};
    const upsetScore  = upsetScores[`${fx.groupKey}-${fx.matchday}-${fx.home}-${fx.away}`] || 0;
    const aiPreviews  = _wmData.aiPreviews || {};
    const aiSnippet   = (aiPreviews[`${fx.groupKey}-${fx.matchday}-${fx.home}-${fx.away}`] || {}).tgSnippet || null;

    let html = `<div class="wm-card${isPlayed ? ' wm-card-played' : ''}" style="--card-accent:${accentColor}">`;

    // ─── Group bar ────────────────────────────────────
    html += `
    <div class="wm-card-groupbar">
      <span class="wm-group-tag">🌍 ${gData.name || ('Gruppe ' + fx.groupKey)}</span>
      <span class="wm-matchday-tag">ST ${fx.matchday}</span>
      <span class="wm-groupbar-sep">·</span>
      <span class="wm-date-tag">${_fmtDate(fx.date, fx.time)}</span>
      ${isToday ? '<span class="wm-live-badge">● HEUTE</span>' : ''}
      ${polyFix && polyFix.steamLag ? '<span class="wm-steam-mini">🔥 STEAM</span>' : ''}
    </div>`;

    // ─── Teams + Form + Odds ──────────────────────────
    html += `<div class="wm-card-body">`;
    html += `<div class="wm-teams">`;
    // eloDiff > 0 means home stronger; show delta for the stronger side, negative for weaker
    const homeEloDelta = eloDiff != null ? eloDiff : null;
    const awayEloDelta = eloDiff != null ? -eloDiff : null;
    html += _teamRow(home, standing, fx.home, 'home', homeForm, homeEloDelta);
    html += `<div class="wm-draw-separator"><span>— vs —</span></div>`;
    html += _teamRow(away, standing, fx.away, 'away', awayForm, awayEloDelta);
    html += `</div>`;

    // Odds column
    html += `<div class="wm-odds-col">`;
    if (fxOdds && (fxOdds.hw || fxOdds.dr || fxOdds.aw)) {
      // Highlight odds matching BET picks
      const betMarkets = fxPicks.filter(p => p.verdict === 'BET').map(p => (p.market||'').toLowerCase());
      const hlHome = betMarkets.some(m => m.includes('heim') || m.includes('home') || m === '1');
      const hlDraw = betMarkets.some(m => m.includes('unentsch') || m.includes('draw') || m === 'x');
      const hlAway = betMarkets.some(m => m.includes('auswärts') || m.includes('away') || m === '2');
      html += _oddsCell(fxOdds.hw, 'H', hlHome);
      html += _oddsCell(fxOdds.dr, 'X', hlDraw);
      html += _oddsCell(fxOdds.aw, 'A', hlAway);
    } else {
      html += `<div class="wm-odds-empty">
        <div class="wm-odds-na">—</div>
        <div class="wm-odds-na">—</div>
        <div class="wm-odds-na">—</div>
        <div class="wm-odds-hint">Odds ab Jun</div>
      </div>`;
    }
    html += `</div>`; // wm-odds-col
    html += `</div>`; // wm-card-body

    // ─── Match Picks — Zone 2 (immediately after teams) ──
    if (hasPicks) {
      html += `<div class="wm-picks-section">`;
      html += `<div class="wm-section-header">🎯 PICKS</div>`;
      for (const pick of sortedPicks) {
        html += _buildPickRow(pick, false);
      }
      html += `</div>`;
    }

    // ─── Player Picks ─────────────────────────────────
    if (hasPlayer) {
      html += `<div class="wm-picks-section wm-player-section">`;
      html += `<div class="wm-section-header" style="color:#a78bfa;">⚽ SPIELER-WETTEN</div>`;
      for (const pp of fxPPicks) {
        html += _buildPickRow(pp, true);
      }
      html += `</div>`;
    }

    // ─── Model Probability Bar ────────────────────────
    if (home.elo && away.elo) {
      const prob = _eloProbs(home.elo, away.elo, CO_HOSTS.has(fx.home));
      html += `
      <div class="wm-prob-bar">
        <div class="wm-prob-h">
          <span class="wm-prob-pct">${prob.h}%</span>
          <span class="wm-prob-lbl">${home.flag}</span>
        </div>
        <div class="wm-prob-d">
          <span class="wm-prob-lbl-center">ELO-MODELL</span>
          <span class="wm-prob-pct">${prob.d}%</span>
        </div>
        <div class="wm-prob-a">
          <span class="wm-prob-lbl">${away.flag}</span>
          <span class="wm-prob-pct">${prob.a}%</span>
        </div>
      </div>`;
    }

    // ─── Odds strip — sharpest pp move across all markets ──
    if (fxOdds && fxOdds.odds_open) {
      const open = fxOdds.odds_open;
      const moves = [];
      if (fxOdds.hw  != null && open.hw  != null) moves.push({ pp: (100/fxOdds.hw)  - (100/open.hw),  label: 'Heimsieg',  cur: fxOdds.hw.toFixed(2) });
      if (fxOdds.dr  != null && open.dr  != null) moves.push({ pp: (100/fxOdds.dr)  - (100/open.dr),  label: 'Unentsch.', cur: fxOdds.dr.toFixed(2) });
      if (fxOdds.aw  != null && open.aw  != null) moves.push({ pp: (100/fxOdds.aw)  - (100/open.aw),  label: 'Auswärts',  cur: fxOdds.aw.toFixed(2) });
      if (fxOdds.o25 != null && open.o25 != null) moves.push({ pp: (100/fxOdds.o25) - (100/open.o25), label: 'Über 2.5',  cur: fxOdds.o25.toFixed(2) });
      if (fxOdds.u25 != null && open.u25 != null) moves.push({ pp: (100/fxOdds.u25) - (100/open.u25), label: 'Unter 2.5', cur: fxOdds.u25.toFixed(2) });
      // Find sharpest move
      moves.sort((a, b) => Math.abs(b.pp) - Math.abs(a.pp));
      const best = moves[0];
      if (best && Math.abs(best.pp) >= 1.0) {
        const dir = best.pp > 0 ? '▲' : '▼';
        const clr = best.pp > 0 ? 'var(--green)' : 'var(--red)';
        html += `
        <div class="wm-odds-strip">
          <span class="wm-strip-label">LINIE</span>
          <span style="color:${clr};font-weight:700;">${dir} ${Math.abs(best.pp).toFixed(1)}pp ${best.label}</span>
          <span class="wm-strip-sep">·</span>
          <span class="wm-strip-open">Kurs ${best.cur}</span>
        </div>`;
      }
    }

    // ─── Venue + Climate pills ───────────────────────
    if (fx.venue) {
      // quick inline venue lookup for cards
      const _vk = (fx.venue || '').toLowerCase().trim();
      const _vmap = {
        'estadio azteca':2200,'mexico city':2200,'azteca':2200,
        'estadio akron':1566,'guadalajara':1566,'akron':1566,
        'estadio bbva':540,'monterrey':540,'bbva':540,
        'hard rock stadium':2,'miami':2,'hard rock':2,
        "at&t stadium":170,'att stadium':170,'dallas':170,
        'nrg stadium':15,'nrg':15,'houston':15,
        'arrowhead stadium':320,'arrowhead':320,'kansas city':320,
        'bc place':5,'vancouver':5,'bmo field':76,'toronto':76,
      };
      const _vtmap = {
        'estadio azteca':'outdoor','mexico city':'outdoor','azteca':'outdoor',
        'estadio akron':'outdoor','guadalajara':'outdoor','akron':'outdoor',
        'estadio bbva':'outdoor','monterrey':'outdoor','bbva':'outdoor',
        'hard rock stadium':'outdoor','miami':'outdoor','hard rock':'outdoor',
        "at&t stadium":'dome','att stadium':'dome','dallas':'dome',
        'nrg stadium':'dome','nrg':'dome','houston':'dome',
        'bc place':'dome','vancouver':'dome',
        'sofi stadium':'open-roof','sofi':'open-roof',
      };
      const _vtempmap = {
        'estadio azteca':18,'mexico city':18,'azteca':18,
        'estadio akron':25,'guadalajara':25,'akron':25,
        'estadio bbva':36,'monterrey':36,'bbva':36,
        'hard rock stadium':33,'miami':33,'hard rock':33,
        'arrowhead stadium':33,'arrowhead':33,'kansas city':33,
      };
      // find matching key
      let _matchKey = null;
      for (const k of Object.keys(_vmap)) { if (_vk.includes(k)||k.includes(_vk)){_matchKey=k;break;} }
      const _alt  = _matchKey ? _vmap[_matchKey]  : null;
      const _vtyp = _matchKey ? (_vtmap[_matchKey]||'outdoor') : 'outdoor';
      const _temp = _matchKey ? (_vtempmap[_matchKey]||null) : null;

      let _envPills = '';
      if (_alt != null) {
        if      (_alt >= 2000) _envPills += `<span class="wm-env-pill wm-env-alt-high">🏔️ ${_alt}m</span>`;
        else if (_alt >= 1000) _envPills += `<span class="wm-env-pill wm-env-alt-mid">🏔️ ${_alt}m</span>`;
        else if (_alt >= 300)  _envPills += `<span class="wm-env-pill wm-env-alt-low">⛰️ ${_alt}m</span>`;
      }
      if (_vtyp === 'dome')      _envPills += `<span class="wm-env-pill wm-env-dome">🏛️ Dome</span>`;
      else if (_vtyp==='open-roof') _envPills += `<span class="wm-env-pill wm-env-dome">🌤️ Offen</span>`;
      if (_temp != null && _vtyp !== 'dome') {
        if      (_temp >= 33) _envPills += `<span class="wm-env-pill wm-env-heat">🌡️ ${_temp}°C</span>`;
        else if (_temp >= 28) _envPills += `<span class="wm-env-pill wm-env-warm">🌡️ ${_temp}°C</span>`;
      }
      html += `<div class="wm-venue">📍 ${fx.venue}${_envPills ? '<span class="wm-env-pills">' + _envPills + '</span>' : ''}</div>`;
    }

    // ─── Upset Score badge ────────────────────────────
    if (upsetScore >= 6) {
      html += `<div class="wm-upset-badge">💥 Upset-Potential ${upsetScore}/10</div>`;
    }

    // ─── Scenario banner ──────────────────────────────
    const scenario = _buildScenario(home, away, eloDiff, fx.matchday, standing, fx, isPlayed);
    if (scenario) {
      html += `<div class="wm-scenario">${scenario}</div>`;
    }

    // ─── xG + Form Stats strip ────────────────────────
    const hasXg   = homeXg || awayXg;
    const hasForm = homeForm || awayForm;
    if (hasXg || hasForm) {
      html += `<div class="wm-stats-strip">`;
      // Threshold-colored pill helper: over25Rate/bttsRate > 60% → green, < 40% → red
      const ouPillCls = r => r > 0.60 ? 'wm-stat-pill wm-stat-ou-high' : r < 0.40 ? 'wm-stat-pill wm-stat-ou-low' : 'wm-stat-pill wm-stat-ou';
      const bttsPillCls = r => r > 0.55 ? 'wm-stat-pill wm-stat-btts-high' : r < 0.35 ? 'wm-stat-pill wm-stat-btts-low' : 'wm-stat-pill wm-stat-btts';
      // Home side
      html += `<div class="wm-stats-team">`;
      if (homeXg) html += `<span class="wm-stat-pill wm-stat-xg" title="xG Attack / Defense">⚽ ${homeXg.xgForAvg.toFixed(1)} · 🛡 ${homeXg.xgAgainstAvg.toFixed(1)}</span>`;
      if (homeForm) {
        if (homeForm.over25Rate != null) html += `<span class="${ouPillCls(homeForm.over25Rate)}">O2.5 ${Math.round(homeForm.over25Rate * 100)}%</span>`;
        if (homeForm.bttsRate != null)   html += `<span class="${bttsPillCls(homeForm.bttsRate)}">BTTS ${Math.round(homeForm.bttsRate * 100)}%</span>`;
      }
      html += `</div>`;
      // Away side
      html += `<div class="wm-stats-team wm-stats-team-away">`;
      if (awayXg) html += `<span class="wm-stat-pill wm-stat-xg" title="xG Attack / Defense">⚽ ${awayXg.xgForAvg.toFixed(1)} · 🛡 ${awayXg.xgAgainstAvg.toFixed(1)}</span>`;
      if (awayForm) {
        if (awayForm.over25Rate != null) html += `<span class="${ouPillCls(awayForm.over25Rate)}">O2.5 ${Math.round(awayForm.over25Rate * 100)}%</span>`;
        if (awayForm.bttsRate != null)   html += `<span class="${bttsPillCls(awayForm.bttsRate)}">BTTS ${Math.round(awayForm.bttsRate * 100)}%</span>`;
      }
      html += `</div>`;
      html += `</div>`; // wm-stats-strip
    }

    // ─── O2.5 / BTTS Odds row ────────────────────────
    if (fxOdds && (fxOdds.o25 || fxOdds.bttsY)) {
      html += `<div class="wm-ou-row">`;
      if (fxOdds.o25)   html += `<div class="wm-ou-cell"><span class="wm-ou-lbl">O2.5</span><span class="wm-ou-val">${fxOdds.o25.toFixed(2)}</span></div>`;
      if (fxOdds.u25)   html += `<div class="wm-ou-cell"><span class="wm-ou-lbl">U2.5</span><span class="wm-ou-val">${fxOdds.u25.toFixed(2)}</span></div>`;
      if (fxOdds.bttsY) html += `<div class="wm-ou-cell"><span class="wm-ou-lbl">BTTS J</span><span class="wm-ou-val">${fxOdds.bttsY.toFixed(2)}</span></div>`;
      if (fxOdds.bttsN) html += `<div class="wm-ou-cell"><span class="wm-ou-lbl">BTTS N</span><span class="wm-ou-val">${fxOdds.bttsN.toFixed(2)}</span></div>`;
      html += `</div>`;
    }

    // ─── AI Snippet ───────────────────────────────────
    if (aiSnippet && !isPlayed) {
      html += `<div class="wm-ai-snippet">🤖 ${aiSnippet}</div>`;
    }

    // ─── Polymarket mini row ──────────────────────────
    if (polyFix) {
      html += _buildPolyRow(polyFix);
    }

    // ─── Squad Spotlight ──────────────────────────────
    if (homeSquad || awaySquad) {
      html += `<div class="wm-squad-spotlight">`;
      html += `<div class="wm-section-header" style="color:var(--blue);font-size:9px;">👥 SCHLÜSSELSPIELER</div>`;
      html += `<div class="wm-squad-row">`;
      if (homeSquad) html += _squadPlayer(home, homeSquad);
      if (awaySquad) html += _squadPlayer(away, awaySquad);
      html += `</div></div>`;
    }

    // ─── Event Page Link ──────────────────────────────
    const slug = `wm-${fx.home.toLowerCase()}-vs-${fx.away.toLowerCase()}-${fx.date}`;
    html += `<a class="wm-event-link wm-event-link-btn" href="matches/wm-match.html?m=${slug}" target="_blank">↗ Vollanalyse · Elo · xG · AI-Preview · Polymarket</a>`;

    html += `</div>`; // wm-card
    return html;
  }

  // ── Team row with form dots ───────────────────────────
  function _teamRow(team, standing, teamId, side, form, eloDelta) {
    const pos    = standing ? standing.findIndex(s => s.id === teamId) + 1 : 0;
    const posStr = pos > 0 ? `<span class="wm-standing-pos">${pos}.</span>` : '';
    // Show Elo as delta (advantage over opponent), not raw number
    let eloStr = '';
    if (eloDelta != null) {
      const sign   = eloDelta > 0 ? '+' : '';
      const clr    = eloDelta > 0 ? '#3fb950' : eloDelta < 0 ? '#f85149' : 'var(--muted)';
      eloStr = `<span class="wm-elo-badge" style="color:${clr};border-color:${clr}44">${sign}${eloDelta} Elo</span>`;
    } else if (team.elo) {
      eloStr = `<span class="wm-elo-badge">${team.elo}</span>`;
    }
    const formDots = form && form.last5 ? _formDots(form.last5) : '';
    return `
    <div class="wm-team-row wm-team-${side}">
      ${posStr}
      <span class="wm-flag">${team.flag}</span>
      <span class="wm-name">${team.name}</span>
      ${eloStr}
      ${formDots ? `<div class="wm-form-dots">${formDots}</div>` : ''}
    </div>`;
  }

  // ── Odds cell ─────────────────────────────────────────
  function _oddsCell(val, label, highlight) {
    const display = val != null ? val.toFixed(2) : '—';
    const cls = highlight ? ' wm-odds-hl' : '';
    return `<div class="wm-odds-cell${cls}">
      <span class="wm-odds-lbl">${label}</span>
      <span class="wm-odds-val">${display}</span>
    </div>`;
  }

  // ── Pick row with edgePP ──────────────────────────────
  function _buildPickRow(pick, isPlayer) {
    const conf    = pick.conf || 'medium';
    const stars   = conf === 'high' ? '★★★' : conf === 'medium' ? '★★☆' : '★☆☆';
    const starsClr = conf === 'high' ? '#3fb950' : conf === 'medium' ? '#e3b341' : '#8b949e';
    const verdict  = pick.verdict || 'ABWÄGEN';
    const vClr     = verdict === 'BET' ? '#3fb950' : verdict === 'SKIP' ? '#f85149' : '#e3b341';
    const vBg      = verdict === 'BET' ? 'rgba(63,185,80,.12)' : verdict === 'SKIP' ? 'rgba(248,81,73,.10)' : 'rgba(227,179,65,.10)';
    const vBorder  = verdict === 'BET' ? 'rgba(63,185,80,.35)' : verdict === 'SKIP' ? 'rgba(248,81,73,.30)' : 'rgba(227,179,65,.30)';
    const oddsStr  = pick.odds != null ? '@' + pick.odds.toFixed(2) : '—';
    const market   = isPlayer && pick.playerName ? `${pick.playerName} — ${pick.market}` : pick.market;
    const icon     = pick.icon || (isPlayer ? '⚽' : '🎯');

    // Edge badge
    let edgeHtml = '';
    if (pick.edgePP != null) {
      const ep = parseFloat(pick.edgePP);
      const epStr = (ep >= 0 ? '+' : '') + ep.toFixed(0) + 'pp';
      edgeHtml = `<span class="wm-pick-edge ${ep >= 3 ? 'pos' : 'neu'}">${epStr}</span>`;
    }

    // Model odds comparison
    let modelHtml = '';
    if (pick.modelOdds != null && pick.odds != null) {
      modelHtml = `<div class="wm-pick-model">Modell: ${pick.modelOdds.toFixed(2)}</div>`;
    }

    // dataQuality badge
    const dqBadge = pick.dataQuality && pick.dataQuality !== 'elo+form'
      ? `<span class="wm-dq-badge">${pick.dataQuality}</span>` : '';

    return `
    <div class="wm-pick-row">
      <span class="wm-verdict" style="color:${vClr};background:${vBg};border-color:${vBorder};">${verdict}</span>
      <span class="wm-pick-icon">${icon}</span>
      <div class="wm-pick-main">
        <div class="wm-pick-market">${market}${dqBadge}</div>
        ${modelHtml}
        ${pick.info ? `<div class="wm-pick-info">${pick.info}</div>` : ''}
      </div>
      <span class="wm-pick-stars" style="color:${starsClr}">${stars}</span>
      ${edgeHtml}
      <span class="wm-pick-odds">${oddsStr}</span>
    </div>`;
  }

  // ── Polymarket mini row ───────────────────────────────
  function _buildPolyRow(pf) {
    const pct = v => v != null ? Math.round(v * 100) + '%' : null;
    const edge = (e, key) => {
      if (e == null || Math.abs(e) < 0.5) return '';
      const cls = e > 0 ? 'pos' : 'neg';
      const s   = (e > 0 ? '+' : '') + e.toFixed(1) + 'pp';
      return `<span class="wm-poly-edge ${cls}">${s}</span>`;
    };

    const parts = [];
    if (pf.poly_hw  != null) parts.push(`<span>HW <span class="wm-poly-val">${pct(pf.poly_hw)}</span>${edge(pf.edge_hw)}</span>`);
    if (pf.poly_dr  != null) parts.push(`<span>X <span class="wm-poly-val">${pct(pf.poly_dr)}</span>${edge(pf.edge_dr)}</span>`);
    if (pf.poly_o25 != null) parts.push(`<span>O2.5 <span class="wm-poly-val">${pct(pf.poly_o25)}</span>${edge(pf.edge_o25)}</span>`);
    if (pf.poly_u25 != null) parts.push(`<span>U2.5 <span class="wm-poly-val">${pct(pf.poly_u25)}</span>${edge(pf.edge_u25)}</span>`);

    if (!parts.length) return '';

    const vol = pf.vol ? '<span style="margin-left:auto;color:#666;">$' + (pf.vol / 1000).toFixed(0) + 'K Vol.</span>' : '';
    return `
    <div class="wm-poly-row">
      <span class="wm-poly-tag">POLY</span>
      ${parts.join('<span style="color:var(--border)">·</span>')}
      ${vol}
    </div>`;
  }

  // ── Squad player with real stats ──────────────────────
  function _squadPlayer(team, squad) {
    const goals   = squad.goals   != null ? squad.goals   : null;
    const assists = squad.assists != null ? squad.assists : null;
    const per90   = squad.minutes && goals != null && squad.minutes > 0
      ? (goals / (squad.minutes / 90)).toFixed(2) : null;

    const statsHtml = (goals != null || assists != null) ? `
      <div class="wm-squad-stats">
        ${goals   != null ? `<div class="wm-squad-stat"><div class="wm-squad-stat-val" style="color:#3fb950;">${goals}</div><div class="wm-squad-stat-lbl">Tore</div></div>` : ''}
        ${assists != null ? `<div class="wm-squad-stat"><div class="wm-squad-stat-val" style="color:#60a5fa;">${assists}</div><div class="wm-squad-stat-lbl">Assists</div></div>` : ''}
        ${per90 != null   ? `<div class="wm-squad-stat"><div class="wm-squad-stat-val" style="color:#f0c040;">${per90}</div><div class="wm-squad-stat-lbl">T/90</div></div>` : ''}
      </div>` : '';

    return `
    <div class="wm-squad-player">
      <span class="wm-squad-flag">${team.flag}</span>
      <div>
        <div class="wm-squad-name">${squad.name}</div>
        <div class="wm-squad-meta">${squad.position}</div>
        ${statsHtml}
      </div>
    </div>`;
  }

  // ─────────────────────────────────────────────────────
  //  HELPERS
  // ─────────────────────────────────────────────────────

  function _formDots(last5) {
    return last5.slice(0, 5).map(r => {
      const cls = r === 'W' ? 'wm-fd-w' : r === 'D' ? 'wm-fd-d' : 'wm-fd-l';
      return `<span class="wm-fd ${cls}">${r}</span>`;
    }).join('');
  }

  function _eloProbs(homeElo, awayElo, isCoHost) {
    const diff  = homeElo - awayElo;
    let pExp    = 1 / (1 + Math.pow(10, -diff / 400));
    if (isCoHost) pExp = Math.min(0.93, pExp + 0.03);
    const absD  = Math.abs(diff);
    let pDraw   = 0.24 * Math.max(0.35, 1 - absD / 600);
    pDraw = Math.max(0.10, Math.min(0.30, pDraw));
    const pHome = pExp * (1 - pDraw);
    const pAway = (1 - pExp) * (1 - pDraw);
    const tot   = pHome + pDraw + pAway;
    return {
      h: Math.round(pHome / tot * 100),
      d: Math.round(pDraw / tot * 100),
      a: Math.round(pAway / tot * 100),
    };
  }

  // ─────────────────────────────────────────────────────
  //  SCENARIO TEXT
  // ─────────────────────────────────────────────────────
  function _buildScenario(home, away, eloDiff, matchday, standing, fx, isPlayed) {
    if (isPlayed) return null;

    if (standing && standing.length > 0) {
      return _standingScenario(home, away, standing, matchday);
    }

    if (eloDiff === null) return null;
    const absElo  = Math.abs(eloDiff);
    const favTeam = eloDiff > 0 ? home : away;
    const undTeam = eloDiff > 0 ? away : home;
    const coHost  = CO_HOSTS.has(fx.home) ? ` · 🏠 Co-Host-Bonus` : '';

    if (matchday > 1) {
      return `⚡ <strong>${favTeam.flag} ${favTeam.name}</strong> Favorit (Elo +${absElo}) — jeder Punkt im Gruppenrennen wichtig${coHost}`;
    }
    if (absElo >= 250) {
      return `🏆 <strong>${favTeam.flag} ${favTeam.name}</strong> Topfavorit (Elo +${absElo}) — Pflichtauftakt für Gruppenführung${coHost}`;
    } else if (absElo >= 120) {
      return `⚡ <strong>${favTeam.flag} ${favTeam.name}</strong> Favorit (Elo +${absElo}) — <strong>${undTeam.flag} ${undTeam.name}</strong> für Überraschung gut${coHost}`;
    } else if (absElo >= 40) {
      return `⚖️ Ausgeglichenes Duell — <strong>${favTeam.flag} ${favTeam.name}</strong> leicht vorne (Elo +${absElo})${coHost}`;
    } else {
      return `🔥 Sehr ausgeglichenes Spiel — Elo-Differenz nur ${absElo} Punkte, alles offen${coHost}`;
    }
  }

  function _standingScenario(home, away, standing, matchday) {
    const homeRow = standing.find(s => s.id === home.id);
    const awayRow = standing.find(s => s.id === away.id);
    if (!homeRow || !awayRow) return null;

    const homePts = homeRow.pts || 0;
    const awayPts = awayRow.pts || 0;
    const homePos = standing.findIndex(s => s.id === home.id) + 1;
    const awayPos = standing.findIndex(s => s.id === away.id) + 1;

    if (homePos > 3 && awayPos > 3) return `❌ Beide Teams bereits ausgeschieden`;
    if (homePos <= 2 && awayPos <= 2 && matchday === 3) return `🏆 Beide qualifiziert — Kampf um <strong>Gruppenführung</strong>`;
    if ((homePos > 3 || awayPos > 3) && matchday === 3) {
      const desperate = homePos > 3 ? home : away;
      return `🔥 <strong>${desperate.flag} ${desperate.name}</strong> braucht zwingend einen Sieg — Ausscheiden droht`;
    }
    if (homePos === 1 && awayPos === 2) return `⭐ Spitzenpaarung: <strong>${home.flag} Platz 1</strong> vs <strong>${away.flag} Platz 2</strong>`;
    return `📊 <strong>${home.flag} ${home.name}</strong> ${homePts} Pkt (${homePos}.) vs <strong>${away.flag} ${away.name}</strong> ${awayPts} Pkt (${awayPos}.)`;
  }

  const _DAYS   = ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa'];
  const _MONTHS = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez'];

  function _fmtDate(iso, time) {
    if (!iso) return '';
    const d   = new Date(iso + 'T12:00:00');
    const tStr = time ? ` · ${time} Uhr` : '';
    return `${_DAYS[d.getDay()]}, ${d.getDate()}. ${_MONTHS[d.getMonth()]}${tStr}`;
  }

  function _daysFrom(iso, todayIso) {
    const diff = Math.ceil((new Date(iso) - new Date(todayIso)) / 86400000);
    if (diff === 1) return 'Morgen';
    if (diff <= 7) return `in ${diff} Tagen`;
    return `in ${Math.ceil(diff / 7)} Wo.`;
  }

})();
