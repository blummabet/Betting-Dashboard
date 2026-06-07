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
  let _wmData         = null;
  let _polyLookup     = {};   // key: "HOME-AWAY" → poly fixture object
  let _travelLookup   = {};   // key: TEAM_ID → travel burden object
  let _confidenceStats = null;  // pick_confidence_stats.json
  let _oddsHistoryLookup = {};  // key: "HOME-AWAY" → [ {ts, hw, dr, aw, o25, ...}, ... ]
  let _wmMatchPages = {};       // slug → match-page-data (aus matches/data/wm-{slug}.json)
  let _wmPagesLoaded = false;
  let _wmPagesLastTs  = 0;      // wann wm-match-pages zuletzt geladen wurden
  const _expandedPreviews = new Set();  // Set of match-keys mit ausgeklapptem AI-Preview
  let _whyModalKey = null;              // wenn !== null: Modal ist offen für diesen matchKey
  let _activeGroup    = 'all';
  let _activeMd       = 'all';   // matchday filter: 'all' | 1 | 2 | 3
  let _activeSort     = 'date';  // 'date' | 'edge' | 'upset'
  let _loaded         = false;
  let _lastLoadTs     = 0;       // Timestamp des letzten erfolgreichen Loads (ms)

  // TTL für In-Memory-Cache. Tab-Wechsel innerhalb dieses Fensters → kein Re-Fetch
  // (schnell). Danach: silent re-fetch im Hintergrund mit alten Karten sichtbar,
  // damit Picks nach jedem 4h-Cron-Update spätestens 5 Min später frisch sind.
  // Picks werden nur 5×/Tag (alle 4h) im Workflow neu generiert, ein 5-Min-TTL
  // ist also conservatively kurz und liefert ein gutes Verhältnis aus Frische
  // und Bandbreiten-Sparsamkeit.
  const CARDS_CACHE_TTL_MS = 5 * 60 * 1000;

  const CO_HOSTS = new Set(['MEX', 'USA', 'CAN']);

  // ─────────────────────────────────────────────────────
  //  ENTRY POINT
  // ─────────────────────────────────────────────────────
  window.initIntlCards = async function () {
    const panel = document.getElementById('intlCardsPanel');
    if (!panel) return;

    // ── Cache-Strategie ──────────────────────────────────────────────────
    // Warm hit (TTL nicht abgelaufen): nur re-rendern, kein Netzwerk.
    // Warm miss (TTL abgelaufen, aber Daten vorhanden): alte Karten weiter
    //   sichtbar lassen + im Hintergrund silent re-fetch → kein Flicker.
    // Cold (noch nie geladen): Spinner zeigen, dann fetch.
    const isWarm    = _loaded && _wmData;
    const ttlValid  = (Date.now() - _lastLoadTs) < CARDS_CACHE_TTL_MS;
    if (isWarm && ttlValid) {
      _render();
      return;
    }
    if (!isWarm) {
      panel.innerHTML = `
        <div style="text-align:center;padding:60px 16px;color:var(--muted);">
          <div style="font-size:36px;margin-bottom:14px;animation:spin 1.2s linear infinite;display:inline-block;">⚙️</div>
          <div style="font-size:13px;font-weight:600;">Lade WM 2026 Daten…</div>
        </div>`;
    }
    // Bei warmem Miss: Karten bleiben sichtbar, fetch läuft silent unten weiter

    try {
      const [wmResp, polyResp, travelResp, confResp, ppResp, chgResp, histResp] = await Promise.all([
        fetch('wm2026-data.json?t=' + Date.now()),
        fetch('wm_poly_prices.json?t=' + Date.now()).catch(() => null),
        fetch('wm_travel_burden.json?t=' + Date.now()).catch(() => null),
        fetch('pick_confidence_stats.json?t=' + Date.now()).catch(() => null),
        fetch('wm2026-player-picks.json?t=' + Date.now()).catch(() => null),
        fetch('pick_changes_log.json?t=' + Date.now()).catch(() => null),
        fetch('wm2026-odds-history.json?t=' + Date.now()).catch(() => null),
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

      if (travelResp && travelResp.ok) {
        const travelRaw = await travelResp.json();
        // travelRaw ist {TEAM_ID: {...}} — direkt als Lookup nutzbar
        _travelLookup = travelRaw || {};
        window._wmTravelBurden = _travelLookup;   // backward compat mit altem Code
      }

      if (confResp && confResp.ok) {
        _confidenceStats = await confResp.json();
      }

      // Odds-History (Sparkline-Quelle für Pick-Cards)
      if (histResp && histResp.ok) {
        try {
          _oddsHistoryLookup = await histResp.json();
        } catch (e) { _oddsHistoryLookup = {}; }
      }

      // Pick-Änderungen (Rolling-Log, max 200 Einträge / 7 Tage)
      if (chgResp && chgResp.ok) {
        try {
          const chgRaw = await chgResp.json();
          _wmData.pickChanges = chgRaw.changes || [];
        } catch (e) { _wmData.pickChanges = []; }
      } else {
        _wmData.pickChanges = [];
      }

      // Spieler-Picks (separates File — kommt erst T-3 vor Anpfiff)
      // Format: { lastUpdate, picks: { "MEX-ZAF": [...] } }
      // Renderer erwartet aber Key-Format "GROUP-MD-HOME-AWAY" → mappen via Fixture-Liste
      if (ppResp && ppResp.ok) {
        try {
          const ppRaw = await ppResp.json();
          const ppByHa = ppRaw.picks || {};
          // Map ha-keys auf fixture-keys
          const mapped = {};
          for (const gkey of Object.keys(_wmData.groups || {})) {
            const gdata = _wmData.groups[gkey];
            for (const fx of (gdata.fixtures || [])) {
              const haKey = `${fx.home}-${fx.away}`;
              const list = ppByHa[haKey];
              if (list && list.length) {
                const fixKey = `${gkey}-${fx.matchday}-${fx.home}-${fx.away}`;
                mapped[fixKey] = list;
              }
            }
          }
          _wmData.playerPicks = mapped;
        } catch (e) { console.warn('player-picks parse failed', e); }
      }

      _loaded = true;
      _lastLoadTs = Date.now();
      _render();

      // Stage 2: WM-Match-Pages im Hintergrund laden (für Probability-Bar, Squad-Pills, AI-Preview)
      // Erstes Render zeigt Cards schon, zweites Render hat dann die Extra-Daten
      _loadWmMatchPages();
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

  // Banner: Toggle expand/collapse
  let _bannerExpanded = false;
  window.wmToggleChangesBanner = function () {
    _bannerExpanded = !_bannerExpanded;
    _render();
  };

  // Pick "Warum?" Modal — Open/Close
  window.wmOpenWhy = function (matchKey) {
    _whyModalKey = matchKey;
    _render();
    document.body.style.overflow = 'hidden';
    // ESC + Backdrop binden
    if (!window._wmEscBound) {
      document.addEventListener('keydown', e => {
        if (e.key === 'Escape' && _whyModalKey) window.wmCloseWhy();
      });
      window._wmEscBound = true;
    }
  };
  window.wmCloseWhy = function () {
    _whyModalKey = null;
    document.body.style.overflow = '';
    _render();
  };

  // AI-Preview expand toggle
  window.wmTogglePreview = function (matchKey) {
    if (_expandedPreviews.has(matchKey)) _expandedPreviews.delete(matchKey);
    else _expandedPreviews.add(matchKey);
    _render();
  };

  // Scroll zu einer Match-Card und kurz highlighten
  window.wmJumpToCard = function (matchKey) {
    const el = document.querySelector(`[data-match-key="${matchKey}"]`);
    if (!el) return;
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    el.classList.add('cc-card-pulse');
    setTimeout(() => el.classList.remove('cc-card-pulse'), 2500);
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

    // ─── Pick-Changes Banner (last 24h, only relevant ones) ──
    html += _buildChangesBanner();

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

    // ─── PICK "WARUM?" Modal-Overlay (über allem) ──────
    if (_whyModalKey) {
      html += _renderWhyModalOverlay();
    }

    panel.innerHTML = html;
  }

  // Rendert das Modal-Overlay basierend auf _whyModalKey
  function _renderWhyModalOverlay() {
    const mk = _whyModalKey;
    if (!mk) return '';
    const parts = mk.split('-');
    if (parts.length < 4) return '';
    const [gKey, mdStr, homeId, awayId] = parts;
    const gData = (_wmData.groups || {})[gKey];
    if (!gData) return '';
    const md = +mdStr;
    const fx = (gData.fixtures || []).find(f => f.matchday === md && f.home === homeId && f.away === awayId);
    if (!fx) return '';
    fx.groupKey = gKey;
    const teamsMap = Object.fromEntries((gData.teams || []).map(t => [t.id, t]));
    const home = teamsMap[homeId] || { id: homeId, name: homeId, flag: '🏳️' };
    const away = teamsMap[awayId] || { id: awayId, name: awayId, flag: '🏳️' };
    const fxOdds = (_wmData.odds || {})[`${homeId}-${awayId}`] || null;
    const fxPicks = (_wmData.picks || {})[mk] || [];
    // Audit-Fix 06.06.2026: trackingExcluded Picks komplett raus aus der Card.
    // Diese werden vom Tracker (resolve_wm_picks.py) als VOID markiert wenn sie
    // direktional widersprüchlich sind — wir wollen sie nirgends anzeigen.
    const livePicks = fxPicks.filter(p =>
      !p.trackingExcluded && (p.verdict === 'BET' || p.verdict === 'ABWÄGEN')
    );
    const sortedPicks = [...livePicks].sort((a, b) => {
      if (a.verdict === 'BET' && b.verdict !== 'BET') return -1;
      if (b.verdict === 'BET' && a.verdict !== 'BET') return 1;
      return (b.edgePP || 0) - (a.edgePP || 0);
    });
    const heroPick = sortedPicks[0];
    if (!heroPick) return '';

    const homeForm = (_wmData.form || {})[homeId];
    const awayForm = (_wmData.form || {})[awayId];
    const eloDiff = (home.elo && away.elo) ? (home.elo - away.elo) : null;
    const matchPage = _findMatchPage(fx);

    const body = _buildPickWhyModal(heroPick, fx, home, away, homeForm, awayForm, eloDiff, fxOdds, matchPage);
    return `
      <div class="wm-why-backdrop" onclick="wmCloseWhy()"></div>
      <div class="wm-why-modal" role="dialog" aria-modal="true">
        <button class="wm-why-close" onclick="wmCloseWhy()" aria-label="Schließen">✕</button>
        ${body}
      </div>
    `;
  }

  // ─────────────────────────────────────────────────────
  //  CARD BUILDER — Community-First Layout (Pick/Story/Confidence)
  // ─────────────────────────────────────────────────────
  function _buildCard(fx, gData, home, away, fxOdds, fxPicks, fxPPicks, standing, homeSquad, awaySquad, homeForm, awayForm, polyFix, todayIso) {
    const eloDiff   = (home.elo && away.elo) ? (home.elo - away.elo) : null;
    const isPlayed  = fx.date < todayIso;
    const isToday   = fx.date === todayIso;

    // Pick selection: pick BET/ABWÄGEN with highest edge as hero
    // WATCH-Picks (z.B. Corner-Picks ohne Markt-Quote) sind keine Hero-Kandidaten
    // Smart-Substitution: saferAlt-Picks (Doppelte Chance / AH-Alternative für riskante Picks)
    //   werden bei gleicher Verdict-Klasse bevorzugt — niedrigere Quote = höhere Hit-Rate
    // Audit-Fix 06.06.2026: trackingExcluded Picks komplett raus aus der Card.
    // Diese werden vom Tracker (resolve_wm_picks.py) als VOID markiert wenn sie
    // direktional widersprüchlich sind — wir wollen sie nirgends anzeigen.
    const livePicks = fxPicks.filter(p =>
      !p.trackingExcluded && (p.verdict === 'BET' || p.verdict === 'ABWÄGEN')
    );
    const sortedPicks = [...livePicks].sort((a, b) => {
      // Audit-Fix 06.06.2026: SAFER-ALT vor allem.
      // Smart-Substitution markiert AH Aus +0.5 als saferAltFor='DNB Aus' wenn
      // das Original eine riskante Quote >2.30 hat. Vorher wurde der safer-Alt
      // benachteiligt weil ABWÄGEN nach BET sortiert wurde → DNB @3.14 blieb Hero
      // statt AH +0.5 @1.88 mit höherer Edge zu nehmen. Jetzt: safer-Alt
      // dominiert die Verdict-Hierarchie, weil die Smart-Sub-Engine den Pick
      // explizit als "bessere Wahl" markiert hat.
      const aSafer = !!a.saferAltFor;
      const bSafer = !!b.saferAltFor;
      if (aSafer && !bSafer) return -1;
      if (bSafer && !aSafer) return 1;
      // Innerhalb safer/non-safer: BET vor ABWÄGEN
      if (a.verdict === 'BET' && b.verdict !== 'BET') return -1;
      if (b.verdict === 'BET' && a.verdict !== 'BET') return 1;
      // Dann Edge desc
      return (b.edgePP || 0) - (a.edgePP || 0);
    });
    let heroPick   = sortedPicks[0] || null;
    let otherPicks = sortedPicks.slice(1);

    // ── UI-Convention-Fix 05.06.2026 ──────────────────────────────────────
    // Bei dataQuality=elo+form_asym (ein Team hat keine Form-Daten):
    //   - Kein BET kann durchkommen (B4-Fix bereits aktiv)
    //   - ABER auch ABWÄGEN-Picks mit hohen Quoten (>3.0) oder ohne
    //     andere unterstützende Daten sind irreführend als "Main Pick".
    // Regel: Wenn ALLE Live-Picks dataQuality=elo+form_asym haben UND
    //   der beste Pick eine Quote >3.0 hat → Card als Beobachtungs-Spiel
    //   rendern statt "Vorsichtiger Pick" zu zeigen.
    if (heroPick) {
      const allAsym = livePicks.every(p =>
        p.dataQuality === 'elo+form_asym' || p.dataQuality === 'elo_only'
      );
      const heroIsRisky = (heroPick.odds || 0) > 3.0;
      const heroIsAsym = heroPick.dataQuality === 'elo+form_asym' || heroPick.dataQuality === 'elo_only';
      if (allAsym && heroIsRisky && heroIsAsym) {
        // Card als Beobachtungs-Spiel rendern (kein Main-Pick)
        heroPick = null;
        otherPicks = []; // andere Picks ausblenden — Datenbasis fehlt
      }
    }

    // ── Cross-Market-Konsistenz im UI 06.06.2026 ───────────────────────────
    // Bug: Generator-Check greift nur bei BET-Pairs. Wenn Hero ABWÄGEN ist
    // (z.B. CAN-BIH X2 @2.05), aber "Weitere Picks" enthalten AH Heim −0.5
    // (homeStrong) → User sieht logisch widersprüchliche Empfehlungen
    // nebeneinander. Hier in UI ausfiltern.
    // Refactor 2026-06-06: DIRECTION_MAP + INCOMPATIBLE jetzt aus _pick_helpers.js
    // (window.CocoBetPicks). Spiegelt pick_constants.json (Python-Master).
    if (heroPick && window.CocoBetPicks) {
      otherPicks = otherPicks.filter(p =>
        !window.CocoBetPicks.arePicksConflicting(heroPick, p)
      );
    } else if (heroPick) {
      // Fallback: wenn _pick_helpers.js noch nicht geladen, keine UI-Filterung.
      // Server-seitiges trackingExcluded fängt 99% der Fälle ab.
      console.warn('CocoBetPicks helpers nicht geladen — UI-Konflikt-Filter inaktiv');
    }

    // Hot badge: high poly edge OR steam lag — only when relevant
    const showHotBadge = !!polyFix && (
      (polyFix.bestEdge != null && polyFix.bestEdge >= 10) ||
      polyFix.steamLag === true
    );

    // Card tier class
    let cardCls = 'cc-card';
    if (isPlayed)                              cardCls += ' cc-played';
    else if (heroPick && heroPick.verdict === 'BET')      cardCls += ' cc-tier-bet';
    else if (heroPick && heroPick.verdict === 'ABWÄGEN')  cardCls += ' cc-tier-abw';
    else                                       cardCls += ' cc-tier-watch';
    if (isToday) cardCls += ' cc-today';

    const matchKey = `${fx.groupKey}-${fx.matchday}-${fx.home}-${fx.away}`;
    let html = `<div class="${cardCls}" data-match-key="${matchKey}">`;

    // ─── Hot Edge Badge (only when massive edge / steam) ──
    if (showHotBadge && polyFix.bestEdge != null) {
      html += `<div class="cc-hot-badge">🔥 +${Math.round(polyFix.bestEdge)}pp Edge</div>`;
    } else if (polyFix && polyFix.steamLag) {
      html += `<div class="cc-hot-badge">🔥 Steam Lag</div>`;
    }

    // ─── TOP — Angle + Teams + Meta ───────────────────
    const angle = _deriveAngle(heroPick, fx, eloDiff, polyFix, homeForm, awayForm, standing);
    html += `<div class="cc-top">`;
    if (angle) {
      html += `<div class="cc-angle ${angle.cls}">${angle.icon} ${angle.label}</div>`;
    }
    html += `<div class="cc-teams">
      <div class="cc-team"><span class="cc-flag">${home.flag}</span>${home.name}</div>
      <div class="cc-vs">VS</div>
      <div class="cc-team"><span class="cc-flag">${away.flag}</span>${away.name}</div>
    </div>`;
    const groupLabel = (gData.name || ('Gruppe ' + fx.groupKey));
    const dateMain   = _fmtDate(fx.date, fx.time);   // "Fr 12. Jun · 18:00 Uhr"
    const localTime  = _venueLocalTime(fx.venue, fx.time);  // " · 12:00 NY" oder ""
    html += `<div class="cc-meta">
      <span>${groupLabel} · ST ${fx.matchday}</span>
      <span class="cc-dot"></span>
      <span>${dateMain}${localTime ? `<span class="cc-local-tz">${localTime}</span>` : ''}</span>
      ${fx.venue ? `<span class="cc-dot"></span><span class="cc-venue">📍 ${fx.venue}</span>` : ''}
      ${_venueEnvPill(fx.venue)}
      ${_weatherPill(fx)}
    </div></div>`;

    // ── Lade Match-Page (für Probability-Bar, Squad-Pills, AI-Preview) ──
    const matchPage = _findMatchPage(fx);

    // ── PROBABILITY-BAR (1X2 visuell) ──
    if (matchPage && !isPlayed) {
      const pb = _buildProbBar(matchPage, home, away);
      if (pb) html += pb;
    }

    // ─── PICK HERO ─────────────────────────────────────
    if (!isPlayed && heroPick) {
      const isAbw = heroPick.verdict === 'ABWÄGEN';
      const stars = heroPick.conf === 'high' ? 3 : heroPick.conf === 'medium' ? 2 : 1;
      const oddsStr = heroPick.odds != null ? heroPick.odds.toFixed(2) : '—';
      html += `<div class="cc-pick${isAbw ? ' cc-pick-abw' : ''}">
        <div class="cc-pick-label">${isAbw ? 'Vorsichtiger Pick' : 'Unser Pick'}</div>
        <div class="cc-pick-market">${heroPick.market}</div>
        <div class="cc-pick-odds"><span class="cc-at">@</span><span class="cc-num">${oddsStr}</span></div>
        <div class="cc-pick-conf">
          ${[1,2,3].map(n => `<span class="cc-star${isAbw ? ' cc-star-abw' : ''} ${n <= stars ? 'cc-star-full' : 'cc-star-empty'}">★</span>`).join('')}
        </div>
        <button class="cc-why-btn" onclick="wmOpenWhy('${matchKey.replace(/['"\\\\]/g,'')}')" title="Modell-Rechnung, Insights, CLV, Risiko, Stake-Empfehlung">
          🔍 Warum?
        </button>
      </div>`;

      // Odds-Strip: Opening → Now Drift + Mini-Sparkline (zwischen Pick und Story)
      const stripHtml = _buildOddsStrip(heroPick, fxOdds, fx);
      if (stripHtml) html += stripHtml;
    } else if (isPlayed && fx.result) {
      html += `<div class="cc-pick cc-pick-result">
        <div class="cc-pick-label">Endstand</div>
        <div class="cc-pick-market">${fx.result.home}:${fx.result.away}</div>
      </div>`;
    } else if (!isPlayed && !heroPick) {
      // Check ob die Picks wegen asymmetrischer Datenbasis ausgeblendet wurden
      const hasAsymPicks = livePicks.length > 0;
      const watchMsg = hasAsymPicks
        ? 'Datenbasis unvollständig — Form-Daten eines Teams fehlen'
        : 'Kein Pick mit Edge — Spielverlauf abwarten';
      html += `<div class="cc-pick cc-pick-watch">
        <div class="cc-pick-label">Beobachtungs-Spiel</div>
        <div class="cc-pick-watch-text">${watchMsg}</div>
      </div>`;
    }

    // ─── STORY block ──────────────────────────────────
    if (!isPlayed && heroPick) {
      const story = _buildStory(heroPick, fx, home, away, homeForm, awayForm, polyFix, eloDiff, standing);
      if (story) {
        html += `<div class="cc-story${heroPick.verdict === 'ABWÄGEN' ? ' cc-story-abw' : ''}">${story}</div>`;
      }
    }

    // ─── EVIDENCE — Form + Key Signals ────────────────
    html += `<div class="cc-evidence">`;
    // Block A: Form last 5 with goals avg
    html += `<div class="cc-ev-block">
      <div class="cc-ev-label">Form letzten 5</div>`;
    if (homeForm && homeForm.last5) {
      html += `<div class="cc-form">${(homeForm.last5||[]).slice(0,5).map(r =>
        `<div class="cc-form-dot cc-fd-${(r||'').toLowerCase()}">${r}</div>`).join('')}</div>`;
      const homeAvg = homeForm.avgScored != null ? `${homeForm.avgScored.toFixed(1)} Tore Ø` : '';
      html += `<div class="cc-form-team"><span><span class="cc-flag-sm">${home.flag}</span> ${home.name}</span><span>${homeAvg}</span></div>`;
    }
    if (awayForm && awayForm.last5) {
      html += `<div class="cc-form" style="margin-top:8px;">${(awayForm.last5||[]).slice(0,5).map(r =>
        `<div class="cc-form-dot cc-fd-${(r||'').toLowerCase()}">${r}</div>`).join('')}</div>`;
      const awayAvg = awayForm.avgScored != null ? `${awayForm.avgScored.toFixed(1)} Tore Ø` : '';
      html += `<div class="cc-form-team"><span><span class="cc-flag-sm">${away.flag}</span> ${away.name}</span><span>${awayAvg}</span></div>`;
    }
    if (!homeForm && !awayForm) {
      html += `<div style="font-size:11px;color:var(--muted);font-style:italic;">Form-Daten ab Tournament-Start</div>`;
    }
    html += `</div>`;
    // Block B: Key signals based on pick angle
    html += `<div class="cc-ev-block">
      <div class="cc-ev-label">Schlüssel-Signale</div>`;
    const signals = _buildSignals(heroPick, fx, home, away, homeForm, awayForm, polyFix, eloDiff);
    if (signals.length) {
      signals.forEach(s => {
        html += `<div class="cc-headstat"><span class="cc-key">${s.label}</span><span class="cc-val ${s.cls || ''}">${s.value}</span></div>`;
      });
    } else {
      html += `<div style="font-size:11px;color:var(--muted);font-style:italic;">Weitere Signale nach Daten-Vervollständigung</div>`;
    }
    html += `</div>`;
    html += `</div>`; // cc-evidence

    // ─── Other picks compact (if more than hero) ─────────
    if (otherPicks.length) {
      html += `<div class="cc-otherpicks">
        <div class="cc-ev-label" style="padding:0 0 6px 0;">Weitere Picks</div>`;
      for (const op of otherPicks.slice(0, 3)) {
        const cls = op.verdict === 'BET' ? 'cc-op-bet' : 'cc-op-abw';
        const oddsStr = op.odds != null ? op.odds.toFixed(2) : '—';
        const epp = op.edgePP != null ? ` <span class="cc-op-edge">+${op.edgePP}pp</span>` : '';
        html += `<div class="cc-op-row ${cls}">
          <span class="cc-op-verdict">${op.verdict}</span>
          <span class="cc-op-market">${op.market}</span>
          <span class="cc-op-odds">@${oddsStr}</span>${epp}
        </div>`;
      }
      html += `</div>`;
    }

    // ─── SQUAD PILLS (Top-Spieler je Team mit G/A) ──
    if (matchPage && !isPlayed) {
      const sp = _buildSquadPills(matchPage, home, away);
      if (sp) html += sp;
    }

    // ─── AI-PREVIEW (collapsible) ──
    if (matchPage && !isPlayed) {
      const aip = _buildAiPreview(matchPage, matchKey);
      if (aip) html += aip;
    }

    // ─── CORNER-PICKS (Eckball-Erwartung + Pick wenn Quote vorhanden) ──
    if (!isPlayed && fxPicks && fxPicks.length) {
      const cornerPicks = fxPicks.filter(p => {
        const m = (p.market || '').toLowerCase();
        return m.includes('ecken') || m.includes('corner');
      });
      if (cornerPicks.length) {
        // Zeige erst aktive Picks (BET/ABWÄGEN), sonst WATCH-Eintrag
        const active = cornerPicks.filter(p => p.verdict === 'BET' || p.verdict === 'ABWÄGEN');
        const watch  = cornerPicks.filter(p => p.verdict === 'WATCH');
        const display = active.length ? active.slice(0, 2) : watch.slice(0, 1);
        if (display.length) {
          html += `<div class="cc-otherpicks">
            <div class="cc-ev-label" style="padding:0 0 6px 0;">🚩 Eckball-Markt</div>`;
          for (const cp of display) {
            const ce = cp.cornersExpected;
            const isBet = cp.verdict === 'BET';
            const isAbw = cp.verdict === 'ABWÄGEN';
            const isWatch = cp.verdict === 'WATCH';
            const cls = isBet ? 'cc-op-bet' : isAbw ? 'cc-op-abw' : 'cc-op-watch';
            const verdictLabel = isWatch ? '🚩 Erwartung' : cp.verdict;
            const oddsStr = cp.odds != null ? `@${(+cp.odds).toFixed(2)}` : '<span style="color:var(--muted);">Quote folgt</span>';
            const eppStr = cp.edgePP ? ` <span class="cc-op-edge">+${cp.edgePP}pp</span>` : '';
            const expStr = ce ? ` <span style="font-size:10px;color:var(--muted);">· Ø ${ce.total} Total</span>` : '';
            html += `<div class="cc-op-row ${cls}">
              <span class="cc-op-verdict" style="${isWatch ? 'background:rgba(245,197,24,.10);color:#f5c518;' : ''}">${verdictLabel}</span>
              <span class="cc-op-market">${cp.market}${expStr}</span>
              <span class="cc-op-odds">${oddsStr}</span>${eppStr}
            </div>`;
          }
          html += `</div>`;
        }
      }
    }

    // ─── PLAYER PICKS (Spieler-Märkte aus TheOddsAPI, T-3 vor Anpfiff) ──
    if (!isPlayed && fxPPicks && fxPPicks.length) {
      const ppActive = fxPPicks.filter(p => p.verdict === 'PICK').slice(0, 3);
      if (ppActive.length) {
        const teamFlag = (tid) => tid === fx.home ? home.flag : tid === fx.away ? away.flag : '🏳️';
        const kindIcon = { HERO: '⭐', STAT: '📊', VALUE: '💎', FIRST: '🎲' };
        const kindLabel = { HERO: 'Star-Pick', STAT: 'Schuss-Volumen', VALUE: 'Geheimtipp', FIRST: 'Viral-Quote' };
        html += `<div class="cc-otherpicks">
          <div class="cc-ev-label" style="padding:0 0 6px 0;">🎯 Spieler-Picks</div>`;
        for (const pp of ppActive) {
          const icon = kindIcon[pp.kind] || '🎯';
          const label = kindLabel[pp.kind] || 'Pick';
          const oddsStr = pp.odds != null ? (+pp.odds).toFixed(2) : '—';
          html += `<div class="cc-op-row cc-op-bet">
            <span class="cc-op-verdict" style="background:rgba(0,212,161,0.12);color:#00d4a1;">${icon} ${label}</span>
            <span class="cc-op-market">${teamFlag(pp.teamId)} <strong>${pp.player}</strong> · ${pp.market}</span>
            <span class="cc-op-odds">@${oddsStr}</span>
          </div>`;
        }
        html += `</div>`;
      }
    }

    // ─── ACTIONS row ──────────────────────────────────
    const slug = `wm-${fx.home.toLowerCase()}-vs-${fx.away.toLowerCase()}-${fx.date}`;
    if (!isPlayed && heroPick) {
      const dq    = heroPick.dataQuality || 'elo';
      const dqCls = dq === 'full' ? 'cc-tier-full' : '';
      // Confidence-Backtest: zeige Hit-Rate vergleichbarer Picks
      const conf = _confidenceFor(heroPick);
      let confHtml = '';
      if (conf && conf.n >= 3) {
        const scopeLabel = {
          cluster: 'identische Picks',
          market:  `auf ${heroPick.market}`,
          angle:   `auf ${_angleKeyFromMarket(heroPick.market)}-Picks`,
          global:  'WM-Picks gesamt',
        }[conf.scope] || 'Vergleich';
        const cls = conf.rate >= 60 ? 'cc-val-hot' : conf.rate < 40 ? 'cc-val-cool' : '';
        confHtml = `<span class="cc-conf-backtest"><span class="cc-conf-rate ${cls}">${conf.rate}%</span> · n=${conf.n} ${scopeLabel}</span>`;
      }
      html += `<div class="cc-actions">
        <div class="cc-data-tier">
          <span class="cc-tier-pill ${dqCls}">${dq}</span>
          <span class="cc-conf-text">· conf ${heroPick.conf || 'medium'}</span>
          ${confHtml}
        </div>
        <a class="cc-detail-btn" href="matches/wm-match.html?m=${slug}" target="_blank">↗ Analyse</a>
        <button class="cc-share-btn" onclick="window.wmSharePick && window.wmSharePick('${fx.groupKey}-${fx.matchday}-${fx.home}-${fx.away}')">📤 Posten</button>
      </div>`;
    } else {
      html += `<div class="cc-actions">
        <div class="cc-data-tier">
          ${isPlayed ? '<span class="cc-tier-pill">gespielt</span>' : '<span class="cc-tier-pill">beobachten</span>'}
        </div>
        <a class="cc-detail-btn" href="matches/wm-match.html?m=${slug}" target="_blank">↗ Analyse</a>
        <span></span>
      </div>`;
    }

    html += `</div>`; // cc-card
    return html;
  }

  // ─────────────────────────────────────────────────────
  //  CHANGES BANNER — Pick-Updates der letzten 24h
  //  Nicht-blockierend: Banner verschwindet wenn keine Changes
  // ─────────────────────────────────────────────────────
  function _buildChangesBanner() {
    const all = (_wmData && _wmData.pickChanges) || [];
    if (!all.length) return '';

    // Nur Changes der letzten 24h zeigen
    const cutoffMs = Date.now() - 24 * 3600 * 1000;
    const recent = all.filter(c => {
      try { return new Date(c.ts).getTime() >= cutoffMs; }
      catch (e) { return false; }
    });
    if (!recent.length) return '';

    // Deduplizieren auf neueste Version pro (matchKey + market)
    const byKey = {};
    for (const c of recent) {
      const k = `${c.matchKey}::${c.market}`;
      if (!byKey[k] || c.ts > byKey[k].ts) byKey[k] = c;
    }
    const list = Object.values(byKey).sort((a, b) => (b.ts || '').localeCompare(a.ts || ''));
    if (!list.length) return '';

    // Counts nach Typ
    const counts = { upgrade: 0, downgrade: 0, new_pick: 0, removed: 0, edge_up: 0, edge_down: 0 };
    for (const c of list) counts[c.deltaKind] = (counts[c.deltaKind] || 0) + 1;
    const totalLabel = `${list.length} Pick-Update${list.length === 1 ? '' : 's'} heute`;

    const chips = [];
    if (counts.upgrade)    chips.push(`<span class="pcb-chip pcb-up">▲ ${counts.upgrade} aufgewertet</span>`);
    if (counts.new_pick)   chips.push(`<span class="pcb-chip pcb-new">🆕 ${counts.new_pick} neu</span>`);
    if (counts.downgrade)  chips.push(`<span class="pcb-chip pcb-down">▼ ${counts.downgrade} zurückgestuft</span>`);
    if (counts.removed)    chips.push(`<span class="pcb-chip pcb-rem">✕ ${counts.removed} entfernt</span>`);
    if (counts.edge_up)    chips.push(`<span class="pcb-chip pcb-up">↑ ${counts.edge_up} Edge gestiegen</span>`);
    if (counts.edge_down)  chips.push(`<span class="pcb-chip pcb-down">↓ ${counts.edge_down} Edge gefallen</span>`);

    const head = `
      <div class="pcb-head" onclick="wmToggleChangesBanner()">
        <div class="pcb-head-left">
          <span class="pcb-icon">🔄</span>
          <span class="pcb-title">${totalLabel}</span>
          <span class="pcb-chips">${chips.join(' ')}</span>
        </div>
        <div class="pcb-toggle">${_bannerExpanded ? '▲ Schließen' : '▼ Details'}</div>
      </div>`;

    if (!_bannerExpanded) {
      return `<div class="pick-changes-banner">${head}</div>`;
    }

    const items = list.slice(0, 12).map(c => {
      const kindCls = {
        upgrade:   'pcb-row-up',
        new_pick:  'pcb-row-new',
        downgrade: 'pcb-row-down',
        removed:   'pcb-row-rem',
        edge_up:   'pcb-row-up',
        edge_down: 'pcb-row-down',
      }[c.deltaKind] || '';
      const kindIcon = {
        upgrade:   '▲',
        new_pick:  '🆕',
        downgrade: '▼',
        removed:   '✕',
        edge_up:   '↑',
        edge_down: '↓',
      }[c.deltaKind] || '·';
      const timeAgo = _timeAgo(c.ts);
      const safeKey = c.matchKey.replace(/['"\\]/g, '');
      return `
        <div class="pcb-row ${kindCls}" onclick="wmJumpToCard('${safeKey}')" title="Klick: springt zur Card">
          <span class="pcb-row-icon">${kindIcon}</span>
          <span class="pcb-row-fixture">${c.fixture || c.matchKey}</span>
          <span class="pcb-row-market">${c.market}</span>
          <span class="pcb-row-reason">${c.reason}</span>
          <span class="pcb-row-time">${timeAgo}</span>
        </div>`;
    }).join('');

    return `<div class="pick-changes-banner">
      ${head}
      <div class="pcb-list">${items}</div>
    </div>`;
  }

  function _timeAgo(iso) {
    if (!iso) return '';
    try {
      const diffMin = (Date.now() - new Date(iso).getTime()) / 60000;
      if (diffMin < 1) return 'gerade';
      if (diffMin < 60) return `vor ${Math.floor(diffMin)}m`;
      const h = Math.floor(diffMin / 60);
      if (h < 24) return `vor ${h}h`;
      return `vor ${Math.floor(h / 24)}d`;
    } catch (e) { return ''; }
  }

  // ─────────────────────────────────────────────────────
  //  ANGLE DERIVATION — übersetzt Pick + Daten in eine
  //  semantische "Angle"-Kategorie (wie National-Labels)
  // ─────────────────────────────────────────────────────
  function _deriveAngle(pick, fx, eloDiff, polyFix, homeForm, awayForm, standing) {
    // Special: WM-Eröffnungsspiel (BRA vs MAR, Gruppe C, ST 1, 12.06.2026)
    if (fx.groupKey === 'C' && fx.matchday === 1 && fx.home === 'BRA' && fx.away === 'MAR') {
      return { cls: 'cc-a-eroeff', icon: '🎬', label: 'WM-Eröffnungsspiel' };
    }
    // Special: standings-based scenarios (ST 2/3)
    if (standing && standing.length && fx.matchday >= 3) {
      const homePos = standing.findIndex(s => s.id === fx.home) + 1;
      const awayPos = standing.findIndex(s => s.id === fx.away) + 1;
      if (homePos > 3 && awayPos > 3) return { cls: 'cc-a-dead', icon: '❌', label: 'Beide ausgeschieden' };
      if ((homePos > 3 || awayPos > 3) && fx.matchday === 3) {
        return { cls: 'cc-a-druck', icon: '🔥', label: 'Aufstiegs-Druck' };
      }
      if (homePos <= 2 && awayPos <= 2 && fx.matchday === 3) {
        return { cls: 'cc-a-titel', icon: '🏆', label: 'Spiel um Gruppensieg' };
      }
    }

    if (!pick) {
      if (eloDiff != null && Math.abs(eloDiff) >= 250) return { cls: 'cc-a-pflicht', icon: '🏆', label: 'Klassen-Unterschied' };
      return { cls: 'cc-a-duell', icon: '⚖️', label: 'Gruppenspiel' };
    }

    const m = (pick.market || '').toLowerCase();

    // Über X.5 Tore → Tor-Fest
    if ((m.includes('über') || m.includes('over')) && (m.includes('2.5') || m.includes('1.5') || m.includes('3.5'))) {
      return { cls: 'cc-a-torfest', icon: '⚽', label: 'Tor-Fest erwartet' };
    }
    // Unter X.5 Tore → Defensiv-Schlacht
    if ((m.includes('unter') || m.includes('under')) && (m.includes('2.5') || m.includes('1.5') || m.includes('3.5'))) {
      return { cls: 'cc-a-defshow', icon: '🛡', label: 'Defensiv-Schlacht' };
    }
    // BTTS
    if (m.includes('beide teams') || m.includes('btts') || m.includes('both teams')) {
      if (m.includes('nein') || m.includes('no')) return { cls: 'cc-a-defshow', icon: '🛡', label: 'Zu Null möglich' };
      return { cls: 'cc-a-torfest', icon: '⚽', label: 'Beide treffen' };
    }
    // Heimsieg / Auswärtssieg
    const isHomeWin = m.includes('heim') || m.includes('home') || /^1$/.test(m);
    const isAwayWin = m.includes('auswärt') || m.includes('away') || /^2$/.test(m);
    if (isHomeWin || isAwayWin) {
      const favoringDiff = isHomeWin ? (eloDiff || 0) : -(eloDiff || 0);
      if (favoringDiff >= 200) return { cls: 'cc-a-pflicht', icon: '🏆', label: 'Pflichtsieg-Favorit' };
      // Pick against Elo + good form = Underdog
      if (favoringDiff < 0) {
        const checkForm = isHomeWin ? homeForm : awayForm;
        const wins = checkForm?.last5 ? checkForm.last5.filter(r => r === 'W').length : 0;
        if (wins >= 3) return { cls: 'cc-a-underdog', icon: '⚡', label: 'Underdog mit Form' };
      }
      return { cls: 'cc-a-pflicht', icon: '🎯', label: 'Sieg-Pick mit Edge' };
    }
    // Unentschieden / DNB
    if (m.includes('unentsch') || m.includes('draw')) {
      if (eloDiff != null && Math.abs(eloDiff) < 80) return { cls: 'cc-a-duell', icon: '⚖️', label: 'Ausgeglichenes Duell' };
      return { cls: 'cc-a-duell', icon: '⚖️', label: 'Punkteteilung wahrscheinlich' };
    }
    if (m.includes('dnb')) return { cls: 'cc-a-pflicht', icon: '🛡', label: 'Draw-No-Bet Sicherung' };

    return { cls: 'cc-a-duell', icon: '🎯', label: 'Pick mit Edge' };
  }

  // ─────────────────────────────────────────────────────
  //  STORY BUILDER — 2 Sätze aus Daten
  //  Satz 1: Hauptbehauptung (Form/xG/Defense/Elo)
  //  Satz 2: Modell-vs-Markt-Argument
  // ─────────────────────────────────────────────────────
  function _buildStory(pick, fx, home, away, homeForm, awayForm, polyFix, eloDiff, standing) {
    const m = (pick.market || '').toLowerCase();
    const h2hRaw = (_wmData.h2h || {});
    const h2h = h2hRaw[`${fx.home}-${fx.away}`] || h2hRaw[`${fx.away}-${fx.home}`] || null;
    // Bezugsgröße: wie viele Spiele die Form umfasst — gibt der Story Tiefe
    // ("in letzten 15") statt nur "pro Spiel"
    const refN = Math.max(homeForm?.games || 0, awayForm?.games || 0) || 10;
    const refStr = `in letzten ${refN}`;

    let sentence1 = '';

    if ((m.includes('über') || m.includes('over')) && m.includes('2.5')) {
      const parts = [];
      // Primary: stärkster Angriff — vermeidet doppelte Team-Erwähnung
      let primaryTeamId = null;
      const homeScored = (homeForm && homeForm.avgScored) || 0;
      const awayScored = (awayForm && awayForm.avgScored) || 0;
      if (awayScored >= 2.0 && awayScored >= homeScored) {
        parts.push(`<strong>${away.name} trifft ${awayScored.toFixed(1)} Tore ${refStr}</strong>`);
        primaryTeamId = fx.away;
      } else if (homeScored >= 2.0) {
        parts.push(`<strong>${home.name} trifft ${homeScored.toFixed(1)} Tore ${refStr}</strong>`);
        primaryTeamId = fx.home;
      }
      // Secondary: der ANDERE Team
      if (homeForm && homeForm.over25Rate != null && homeForm.over25Rate >= 0.55 && primaryTeamId !== fx.home) {
        parts.push(`${home.name} ${Math.round(homeForm.over25Rate*100)}% Ü2.5`);
      } else if (awayForm && awayForm.over25Rate != null && awayForm.over25Rate >= 0.55 && primaryTeamId !== fx.away) {
        parts.push(`${away.name} ${Math.round(awayForm.over25Rate*100)}% Ü2.5`);
      }
      // H2H-Trend
      if (h2h && h2h.over25Rate != null && h2h.over25Rate >= 0.6 && parts.length < 2) {
        parts.push(`H2H ${Math.round(h2h.over25Rate*100)}% Ü2.5`);
      }
      sentence1 = parts.length
        ? parts.slice(0, 2).join(', ') + '. Beide Defensiven offen.'
        : 'Beide Offensiv-Reihen produktiv genug für 3+ Tore.';
    }
    else if ((m.includes('unter') || m.includes('under')) && m.includes('2.5')) {
      const parts = [];
      let primaryTeamId = null;
      const homeConc = (homeForm && homeForm.avgConceded) != null ? homeForm.avgConceded : 99;
      const awayConc = (awayForm && awayForm.avgConceded) != null ? awayForm.avgConceded : 99;
      if (awayConc < 0.7 && awayConc <= homeConc) {
        parts.push(`<strong>${away.name} kassiert nur ${awayConc.toFixed(1)} Gegentore ${refStr}</strong>`);
        primaryTeamId = fx.away;
      } else if (homeConc < 0.7) {
        parts.push(`<strong>${home.name} kassiert nur ${homeConc.toFixed(1)} Gegentore ${refStr}</strong>`);
        primaryTeamId = fx.home;
      }
      // Sekundär: anderer Team — entweder schwache Offensive oder eigener Defense-Wert
      const otherScored = primaryTeamId === fx.away ? homeForm?.avgScored : awayForm?.avgScored;
      const otherName   = primaryTeamId === fx.away ? home.name : away.name;
      if (otherScored != null && otherScored < 1.2) {
        parts.push(`<strong>${otherName} nur ${otherScored.toFixed(1)} Tore Ø</strong>`);
      } else if (homeForm && homeConc < 1.0 && primaryTeamId !== fx.home) {
        parts.push(`${home.name} ${homeConc.toFixed(1)} Gegen Ø`);
      } else if (awayForm && awayConc < 1.0 && primaryTeamId !== fx.away) {
        parts.push(`${away.name} ${awayConc.toFixed(1)} Gegen Ø`);
      }
      if (h2h && h2h.over25Rate != null && h2h.over25Rate < 0.5 && parts.length < 2) {
        parts.push(`H2H ${Math.round((1-h2h.over25Rate)*100)}% Unter 2.5`);
      }
      sentence1 = parts.length
        ? parts.slice(0, 2).join(' · ') + '. Wenig Offensiv-Druck erwartet.'
        : 'Tor-armes Spiel zu erwarten — beide Teams kontrolliert.';
    }
    else if (m.includes('beide teams') || m.includes('btts')) {
      const wantYes = !(m.includes('nein') || m.includes('no'));
      if (wantYes) {
        sentence1 = (homeForm && awayForm)
          ? `<strong>${home.name} bttsRate ${Math.round((homeForm.bttsRate||0)*100)}%</strong> · ${away.name} ${Math.round((awayForm.bttsRate||0)*100)}%. Beide trafen zuletzt regelmäßig.`
          : 'Beide Teams trafen in Form-Spielen regelmäßig.';
      } else {
        sentence1 = 'Eines der Teams defensiv überlegen — Clean Sheet realistisch.';
      }
    }
    else if (m.includes('heim') || m.includes('home') || /^1$/.test(m)) {
      const favDiff = eloDiff || 0;
      // Sieg-/Niederlage-Serien zuerst — narrative Schärfe
      const homeStreak = _winStreak(homeForm);
      const homeLossSt = _lossStreak(awayForm);
      if (homeStreak >= 4) {
        sentence1 = `<strong>${home.name} ${homeStreak} Siege in Folge</strong> — Form heißer als Quoten zeigen.`;
      } else if (homeLossSt >= 3) {
        sentence1 = `<strong>${away.name} ${homeLossSt} Niederlagen in Folge</strong> — Krise wird vom Markt unterschätzt.`;
      } else if (favDiff >= 200) {
        sentence1 = `<strong>${home.name} Elo +${favDiff}</strong> über ${away.name} — klassische Heim-Pflichtaufgabe.`;
      } else if (favDiff >= 80) {
        sentence1 = `<strong>${home.name}</strong> favorisiert${homeForm && homeForm.last5 ? ` (Form ${homeForm.last5.join('')})` : ''}.`;
      } else {
        const wins = homeForm?.last5 ? homeForm.last5.filter(r => r === 'W').length : 0;
        sentence1 = wins >= 3
          ? `<strong>${home.name} ${wins} Siege in 5</strong> — Form schlägt Elo.`
          : `<strong>${home.name}</strong> Heim-Bonus + Quoten-Edge.`;
      }
    }
    else if (m.includes('auswärt') || m.includes('away') || /^2$/.test(m)) {
      const favDiff = -(eloDiff || 0);
      const awayStreak = _winStreak(awayForm);
      const homeLossSt = _lossStreak(homeForm);
      if (awayStreak >= 4) {
        sentence1 = `<strong>${away.name} ${awayStreak} Siege in Folge</strong> — Quoten haben Form-Lauf nicht eingepreist.`;
      } else if (homeLossSt >= 3) {
        sentence1 = `<strong>${home.name} ${homeLossSt} Niederlagen in Folge</strong> — Markt traut der Krise nicht.`;
      } else if (favDiff >= 200) {
        sentence1 = `<strong>${away.name} Elo +${favDiff}</strong> über ${home.name} — Pflichtsieg-Favorit auswärts.`;
      } else {
        const wins = awayForm?.last5 ? awayForm.last5.filter(r => r === 'W').length : 0;
        sentence1 = wins >= 3
          ? `<strong>${away.name} ${wins} Siege in 5</strong> — Form besser als Quoten suggerieren.`
          : `<strong>${away.name}</strong> Auswärts-Form unterschätzt vom Markt.`;
      }
    }
    else if (m.includes('unentsch') || m.includes('draw')) {
      const absD = Math.abs(eloDiff || 0);
      sentence1 = absD < 80
        ? `<strong>Elo-Differenz nur ${absD}</strong> — beide Teams auf Augenhöhe, Remis realistisch.`
        : 'Quoten-Edge auf Unentschieden — Modell sieht engeres Spiel als Markt.';
    }
    else if (m.includes('dnb')) {
      sentence1 = 'Draw-No-Bet als Absicherung — Einsatz zurück bei Unentschieden.';
    }
    else {
      sentence1 = pick.info ? `<strong>${pick.info.split('·')[0].trim()}</strong>.` : 'Edge in der Quote erkannt.';
    }

    // ── Zusatz-Sätze: Travel, Verletzung, Standings-Druck ─────────────────
    const sentences = [sentence1];

    // 1) Travel Burden — kritische Anreise als Pick-Verstärker
    const homeLeg = _teamLegForMatch(fx.home, fx.matchday);
    const awayLeg = _teamLegForMatch(fx.away, fx.matchday);
    const burdenSentence = (leg, teamName, teamFlag) => {
      if (!leg || leg.same_venue || (leg.km || 0) < 2500) return null;
      const km = Math.round(leg.km).toLocaleString('de');
      const rest = leg.rest_days || 0;
      const altShift = leg.alt_shift || 0;
      if ((leg.burden || '').toLowerCase() === 'critical') {
        return `<strong>${teamFlag} ${teamName} fliegt ${km} km</strong> mit nur ${rest} Ruhetagen` + (altShift >= 1500 ? ` und ${altShift}m Höhenwechsel` : '');
      }
      if ((leg.burden || '').toLowerCase() === 'high' || (leg.km || 0) >= 3000) {
        return `${teamFlag} ${teamName} mit ${km} km Anreise (${rest} Ruhetage)`;
      }
      return null;
    };
    const homeBurd = burdenSentence(homeLeg, home.name, home.flag);
    const awayBurd = burdenSentence(awayLeg, away.name, away.flag);
    // Nur der/die kritischere(n) — meist nur 1, max beide
    const burdens = [homeBurd, awayBurd].filter(Boolean);
    if (burdens.length) {
      sentences.push(burdens.join(' · ') + '.');
    }

    // 2) Verletzungen — Top-Stürmer raus als Markt-Edge-Verstärker
    const homeOut = _topInjuredScorer(fx.home);
    const awayOut = _topInjuredScorer(fx.away);
    const injSentences = [];
    if (homeOut) injSentences.push(`<strong>${home.flag} ${home.name} ohne ${homeOut.name}</strong> (${homeOut.position || '?'}, ${homeOut.status})`);
    if (awayOut) injSentences.push(`<strong>${away.flag} ${away.name} ohne ${awayOut.name}</strong> (${awayOut.position || '?'}, ${awayOut.status})`);
    if (injSentences.length) {
      sentences.push(injSentences.join(' · ') + '.');
    }

    // 2b) Public-vs-Sharp Bias — wenn das Massenpublikum eine Seite stark anders preist als Pinnacle
    if (pick.publicBias && pick.publicBias.pp >= 4) {
      const pb = pick.publicBias;
      const ocName = { hw: 'Heimsieg', dr: 'Unentschieden', aw: 'Auswärtssieg' }[pb.outcome] || pb.outcome;
      const ocTeam = pb.outcome === 'hw' ? home.name : pb.outcome === 'aw' ? away.name : null;
      const verb = pb.direction === 'over' ? '<strong>über-bettet</strong>' : '<strong>unter-bettet</strong>';
      const target = ocTeam ? `${ocTeam} (${ocName})` : ocName;
      sentences.push(`💸 <strong>${pb.bookmaker}</strong> ${verb} ${target} um <strong>${pb.pp}pp</strong> vs Pinnacle — Sharps sehen das Public-Money gegenläufig.`);
    }

    // 3) ST3 Standings-Druck (Aufstiegs-Kontext)
    if (fx.matchday >= 3 && standing && standing.length) {
      const hRow = standing.find(s => s.id === fx.home);
      const aRow = standing.find(s => s.id === fx.away);
      const hPos = standing.findIndex(s => s.id === fx.home) + 1;
      const aPos = standing.findIndex(s => s.id === fx.away) + 1;
      if (hRow && aRow) {
        const hSafe = hPos <= 2;
        const aSafe = aPos <= 2;
        const hOut  = hPos > 3;
        const aOut  = aPos > 3;
        if (hSafe && aSafe) {
          sentences.push(`<strong>Beide schon Achtelfinale</strong> — Rotation + Schonung wahrscheinlich.`);
        } else if (hOut && aOut) {
          sentences.push(`<strong>Beide ausgeschieden</strong> — Friendly-Charakter, beide ohne Druck.`);
        } else if (hOut && aSafe) {
          sentences.push(`<strong>${home.flag} ${home.name} braucht zwingend Sieg + Schützenhilfe</strong>, ${away.name} bereits sicher.`);
        } else if (aOut && hSafe) {
          sentences.push(`<strong>${away.flag} ${away.name} muss alles riskieren</strong>, ${home.name} bereits sicher.`);
        } else if (hOut) {
          sentences.push(`<strong>${home.flag} ${home.name} im Aufstiegs-Modus</strong> — Sieg Pflicht.`);
        } else if (aOut) {
          sentences.push(`<strong>${away.flag} ${away.name} im Aufstiegs-Modus</strong> — Sieg Pflicht.`);
        }
      }
    }

    // Sentence 2 — Modell vs Markt
    let modelSentence = '';
    if (pick.modelOdds != null && pick.odds != null) {
      const epp = pick.edgePP != null ? pick.edgePP : 0;
      const tier = epp >= 12 ? 'massiv' : epp >= 6 ? 'solide' : epp >= 3 ? 'dünn' : 'minimal';
      modelSentence = `<em>Modell sagt ${pick.modelOdds.toFixed(2)}, Markt ${pick.odds.toFixed(2)} — Edge ${tier} (+${epp}pp).</em>`;
    } else if (pick.info) {
      modelSentence = `<em>${pick.info}</em>`;
    }

    return sentences.join(' ') + (modelSentence ? '<br>' + modelSentence : '');
  }

  // ─────────────────────────────────────────────────────
  //  WM-MATCH-PAGES — lazy load (Probability-Bar, Squad-Pills, AI-Preview)
  // ─────────────────────────────────────────────────────
  async function _loadWmMatchPages() {
    // Gleiches Cache-Konzept wie initIntlCards: TTL-Check, silent re-fetch.
    // Squad-Daten ändern sich selten, Probability-Bar abhängig vom Form-Fetch
    // (alle 4h) — gleicher TTL macht Sinn damit alles synchron frisch ist.
    if (_wmPagesLoaded && (Date.now() - _wmPagesLastTs) < CARDS_CACHE_TTL_MS) {
      return;
    }
    try {
      const bust = '?t=' + Date.now();
      const idxResp = await fetch('matches/wm-index.json' + bust);
      if (!idxResp.ok) return;
      const idx = await idxResp.json();
      const slugs = idx.slugs || [];
      if (!slugs.length) return;
      // Cache-Buster auch auf die individuellen Pages — sonst served der Browser
      // beim zweiten Tab-Wechsel die alten Squad-/Form-Daten aus dem disk-cache.
      const results = await Promise.all(slugs.map(slug =>
        fetch(`matches/data/${slug}.json` + bust).then(r => r.ok ? r.json() : null).catch(() => null)
      ));
      for (const d of results) {
        if (d && d.slug) _wmMatchPages[d.slug] = d;
      }
      _wmPagesLoaded = true;
      _wmPagesLastTs = Date.now();
      _render();   // Re-render mit den neuen Daten
    } catch (e) { console.warn('wm-match-pages load failed', e); }
  }

  function _findMatchPage(fx) {
    if (!_wmPagesLoaded) return null;
    // Slug-Format wie in generate_wm_match_pages.py: wm-{home_lower}-vs-{away_lower}-{date}
    const slug = `wm-${(fx.home||'').toLowerCase()}-vs-${(fx.away||'').toLowerCase()}-${fx.date}`;
    return _wmMatchPages[slug] || null;
  }

  // ── Probability-Bar (1X2 als 3-Farb-Balken) ─────────────────
  function _buildProbBar(page, home, away) {
    if (!page) return '';
    const ph = page.probHome, pd = page.probDraw, pa = page.probAway;
    if (ph == null || pd == null || pa == null) return '';
    return `<div class="cc-probbar-wrap" title="Modell-Wahrscheinlichkeit (Elo + Form + Travel)">
      <div class="cc-probbar">
        <div class="cc-pb-h" style="flex:${ph};" title="${home.name} ${ph}%"></div>
        <div class="cc-pb-d" style="flex:${pd};" title="Unentschieden ${pd}%"></div>
        <div class="cc-pb-a" style="flex:${pa};" title="${away.name} ${pa}%"></div>
      </div>
      <div class="cc-probbar-lbl">
        <span>${home.flag} ${ph}%</span>
        <span>X ${pd}%</span>
        <span>${pa}% ${away.flag}</span>
      </div>
    </div>`;
  }

  // ── Squad-Pills (Top-Spieler beider Teams mit G/A/Min) ──────
  function _buildSquadPills(page, home, away) {
    if (!page) return '';
    const sq = page.squads || {};
    const h = sq[home.id || ''] || sq[page.homeId];
    const a = sq[away.id || ''] || sq[page.awayId];
    if (!h && !a) return '';
    const pill = (player, flag) => {
      if (!player || !player.name) return '';
      const goals = player.goals != null ? `${player.goals}G` : '';
      const ast   = player.assists != null ? ` ${player.assists}A` : '';
      const pos   = player.position ? `<span class="cc-sq-pos">${player.position}</span>` : '';
      return `<span class="cc-sq-pill" title="Top-Spieler aus WMQ + letzten Klubspielen">
        <span class="cc-sq-flag">${flag}</span>
        <strong>${player.name}</strong>
        ${pos}
        <span class="cc-sq-stats">${goals}${ast}</span>
      </span>`;
    };
    const hp = pill(h, home.flag);
    const ap = pill(a, away.flag);
    if (!hp && !ap) return '';
    return `<div class="cc-squad-row">${hp}${ap}</div>`;
  }

  // ── AI-Preview (collapsible) ────────────────────────────────
  function _buildAiPreview(page, matchKey) {
    if (!page || !page.aiPreview) return '';
    const expanded = _expandedPreviews.has(matchKey);
    const safeKey = matchKey.replace(/['"\\]/g, '');
    if (!expanded) {
      return `<div class="cc-ai-collapsed" onclick="wmTogglePreview('${safeKey}')">
        🤖 <span>AI-Analyse</span> <span class="cc-ai-toggle">▼ aufklappen</span>
      </div>`;
    }
    return `<div class="cc-ai-expanded">
      <div class="cc-ai-head" onclick="wmTogglePreview('${safeKey}')">
        🤖 <span>AI-Analyse</span> <span class="cc-ai-toggle">▲ einklappen</span>
      </div>
      <div class="cc-ai-body">${page.aiPreview}</div>
    </div>`;
  }

  // ─────────────────────────────────────────────────────
  //  ODDS-STRIP — Opening → Aktuell Drift + Mini-Sparkline
  //  Gleiches Markt-Key-Mapping wie in National-Cards (renderer.js).
  //  Versteckt sich automatisch bei <2pp Delta = kein Lärm.
  // ─────────────────────────────────────────────────────
  function _pickToOddsKey(market) {
    const m = (market || '').toLowerCase();
    // DNB-Picks ausschließen: opening dnbH/dnbA wird nicht gespeichert,
    // hw/aw als Fallback wäre apples-to-oranges → Strip falsch.
    if (m.includes('dnb')) return null;
    if (m.includes('heimsieg'))                                return 'hw';
    if (m.includes('auswärtssieg'))                            return 'aw';
    if (m.includes('unentschieden') || m.includes('remis'))    return 'dr';
    if (m.includes('über 2.5')   || m.includes('over 2.5'))    return 'o25';
    if (m.includes('unter 2.5')  || m.includes('under 2.5'))   return 'u25';
    if (m.includes('beide teams treffen') || m.includes('btts')) return 'bttsY';
    return null;
  }

  function _buildOddsStrip(pick, fxOdds, fx) {
    if (!pick || !fxOdds || pick.odds == null) return '';
    const key = _pickToOddsKey(pick.market);
    if (!key) return '';   // Markt nicht mappbar (DC, AH, etc.) — kein Strip

    const openSnap = fxOdds.odds_open || {};
    const openOdds = parseFloat(openSnap[key]);
    const nowOdds  = parseFloat(pick.odds);
    if (!openOdds || !nowOdds || openOdds <= 1 || nowOdds <= 1) return '';

    // pp-Drift: positive Delta = implied prob gestiegen = Quote gefallen
    const openImpl = 1 / openOdds;
    const nowImpl  = 1 / nowOdds;
    const ppDrift  = Math.round((nowImpl - openImpl) * 100);
    if (Math.abs(ppDrift) < 2) return '';   // Kein nennenswerter Move → kein Strip

    // Quote gefallen = Markt confirmt unseren Pick = CLV+ für uns
    const clvPositive = nowOdds < openOdds;
    const cls         = clvPositive ? 'up' : 'down';
    const arrow       = clvPositive ? '↘' : '↗';
    const ppLabel     = (ppDrift > 0 ? '+' : '') + ppDrift + 'pp';
    const clvLabel    = clvPositive ? 'CLV+' : 'CLV−';

    // Sparkline aus History (window._oddsHistoryLookup[matchKey])
    const matchKey = `${fx.home}-${fx.away}`;
    const hist     = (_oddsHistoryLookup[matchKey] || [])
      .filter(s => typeof s[key] === 'number' && s[key] > 1);

    let sparkSvg = '';
    if (hist.length >= 3) {
      sparkSvg = _renderSparkline(hist.map(s => s[key]), clvPositive);
    } else if (openOdds && nowOdds) {
      // Fallback: 2-Punkt-Linie zwischen Opening + Aktuell
      sparkSvg = _renderSparkline([openOdds, nowOdds], clvPositive);
    }

    return `<div class="cc-odds-strip">
      <div class="cc-os-drift">
        <span class="cc-os-label">Quote</span>
        <span class="cc-os-open">${openOdds.toFixed(2)}</span>
        <span class="cc-os-arrow">→</span>
        <span class="cc-os-now ${cls}">${nowOdds.toFixed(2)} ${arrow}</span>
        <span class="cc-os-pp ${cls}">${ppLabel}</span>
        <span class="cc-os-clv cc-clv-${cls}">${clvLabel}</span>
      </div>
      <div class="cc-os-spark">${sparkSvg}</div>
    </div>`;
  }

  function _renderSparkline(values, clvPositive) {
    if (!values || values.length < 2) return '';
    const W = 120, H = 24, pad = 2;
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = (max - min) || 1;
    const dx = (W - pad * 2) / (values.length - 1);

    const pts = values.map((v, i) => {
      const x = pad + i * dx;
      // höhere Quote = oben → 1 - normalized
      const y = pad + (1 - (v - min) / range) * (H - pad * 2);
      return `${x.toFixed(1)} ${y.toFixed(1)}`;
    });
    const linePath = `M ${pts.join(' L ')}`;
    const areaPath = `${linePath} L ${pad + (values.length - 1) * dx} ${H} L ${pad} ${H} Z`;
    const lastX = pad + (values.length - 1) * dx;
    const lastY = pad + (1 - (values[values.length - 1] - min) / range) * (H - pad * 2);
    const firstY = pad + (1 - (values[0] - min) / range) * (H - pad * 2);
    const color = clvPositive ? '#00d4a1' : '#f85149';
    const gradId = `cc-os-g-${Math.random().toString(36).slice(2,8)}`;

    return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
      <defs><linearGradient id="${gradId}" x1="0" x2="0" y1="0" y2="1">
        <stop offset="0%" stop-color="${color}" stop-opacity="0.30"/>
        <stop offset="100%" stop-color="${color}" stop-opacity="0"/>
      </linearGradient></defs>
      <path d="${areaPath}" fill="url(#${gradId})"/>
      <path d="${linePath}" stroke="${color}" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
      <circle cx="${pad}" cy="${firstY.toFixed(1)}" r="1.8" fill="rgba(255,255,255,0.25)"/>
      <circle cx="${lastX.toFixed(1)}" cy="${lastY.toFixed(1)}" r="2.5" fill="${color}"/>
    </svg>`;
  }

  // ═══════════════════════════════════════════════════════
  //  PICK "WARUM?" MODAL — Transparente Begründung pro Pick
  //  (Differenzierungs-Feature: zeigt Modell-Mathematik statt
  //   AI-Phantasie wie die Konkurrenz-Tools)
  // ═══════════════════════════════════════════════════════

  // ── Konfidenz-Score 0-10 aus Verdict + Edge ableiten ─────
  function _confidenceScore(pick) {
    if (!pick) return 0;
    const v = pick.verdict;
    const e = pick.edgePP || 0;
    const conf = pick.conf || 'medium';
    if (v === 'BET') {
      if (conf === 'high' || e >= 12) return Math.min(10, 7 + Math.floor(e / 6));
      if (conf === 'medium' || e >= 6) return 7;
      return 6;
    }
    if (v === 'ABWÄGEN') {
      if (e >= 5) return 5;
      return 4;
    }
    return 3;
  }

  function _confidenceLabel(score, pick) {
    const v = (pick && pick.verdict) || '?';
    const c = (pick && pick.conf) || '?';
    return `${score}/10 · ${v} ${c}`;
  }

  // ── Kelly-Criterion Stake-Range ──────────────────────────
  // Standard: ½ Kelly für konservative Risiko-Management
  function _kellyStake(odds, modelOdds) {
    if (!odds || !modelOdds || odds <= 1 || modelOdds <= 1) return null;
    const p = 1 / modelOdds;           // Modell-Wahrscheinlichkeit
    const q = 1 - p;
    const b = odds - 1;                // Net-Payout-Ratio
    const f = (b * p - q) / b;         // Vollkelly
    if (f <= 0) return null;           // Kein positiver Edge → kein Stake
    const halfKelly = f * 0.5;         // Konservativ
    return {
      full:    +(f * 100).toFixed(1),       // % Bankroll
      half:    +(halfKelly * 100).toFixed(1),
      // Empfohlene Range = ¼ Kelly bis ½ Kelly
      lowPct:  +(halfKelly * 50).toFixed(1),
      highPct: +(halfKelly * 100).toFixed(1),
    };
  }

  function _stakeRange(pick) {
    // Hybrid: Konvention (1-5% Cap mit Verdict-Stufung) + ½-Kelly als Untergrenze-Sanity
    // Profi-Range: BET high=3-5%, BET medium=2-3%, BET low/ABWÄGEN=1-2%
    const k = _kellyStake(pick.odds, pick.modelOdds);
    if (!k) return { label: '0.5–1%', sub: 'minimal · kein klarer Edge' };

    const v = pick.verdict;
    const e = pick.edgePP || 0;
    const c = pick.conf || 'medium';

    let lo, hi;
    if (v === 'BET' && (c === 'high' || e >= 12)) {
      lo = 3.0; hi = 5.0;
    } else if (v === 'BET' && (c === 'medium' || e >= 6)) {
      lo = 2.0; hi = 3.0;
    } else if (v === 'BET') {
      lo = 1.5; hi = 2.5;
    } else if (v === 'ABWÄGEN') {
      lo = 1.0; hi = 2.0;
    } else {
      lo = 0.5; hi = 1.0;
    }
    // Sanity-Override: wenn ½ Kelly unter Lo liegt, runter (zb sehr knapper Edge)
    if (k.half < lo) {
      const half = Math.max(0.5, k.half);
      lo = Math.max(0.5, half * 0.7);
      hi = Math.min(hi, half * 1.3);
    }
    return {
      label: `${lo.toFixed(1)}–${hi.toFixed(1)}%`,
      sub:   `½ Kelly ${k.half.toFixed(1)}% · Edge ${e}pp`,
    };
  }

  // ── Risk-Assessment auto ─────────────────────────────────
  function _riskAssessment(pick, fx, eloDiff, homeForm, awayForm) {
    const dq = (pick && pick.dataQuality) || 'elo_only';
    const factors = [];

    // 1. Data-Quality
    if (dq === 'elo_only') {
      factors.push({ severity: 2, txt: 'Nur Elo-Daten verfügbar — keine Form/H2H-Bestätigung' });
    } else if (dq === 'elo+form') {
      factors.push({ severity: 1, txt: 'Form vorhanden aber H2H-Daten fehlen' });
    }

    // 2. Underdog-Gap
    if (eloDiff != null) {
      const m = (pick.market || '').toLowerCase();
      const pickedHome = m.includes('heim');
      const pickedAway = m.includes('ausw');
      let gap = 0;
      if (pickedHome && eloDiff < 0) gap = -eloDiff;
      else if (pickedAway && eloDiff > 0) gap = eloDiff;
      if (gap > 150) factors.push({ severity: 2, txt: `Pick auf Underdog mit Elo-Gap ${gap.toFixed(0)}` });
      else if (gap > 75) factors.push({ severity: 1, txt: `Schwächeres Team (Elo-Gap ${gap.toFixed(0)})` });
    }

    // 3. Form-Volatilität
    const allForms = [homeForm, awayForm].filter(f => f && f.last5);
    for (const f of allForms) {
      const wld = (f.last5 || []).join('');
      // Hochvolatil wenn W und L in last5
      if (wld.includes('W') && wld.includes('L') && f.games >= 5) {
        // Volatil ist Risk-Note für BTTS/Over picks
        const m = (pick.market || '').toLowerCase();
        if (m.includes('beide') || m.includes('über') || m.includes('over')) {
          factors.push({ severity: 1, txt: 'Form-Volatilität in einem Team (W/L-Mix)' });
          break;
        }
      }
    }

    // 4. Hohe Edge → wirkt suspekt
    if ((pick.edgePP || 0) > 20) {
      factors.push({ severity: 2, txt: `Sehr hoher Edge (${pick.edgePP}pp) — sanity-prüfen` });
    }

    // 5. ABWÄGEN-Status
    if (pick.verdict === 'ABWÄGEN') {
      factors.push({ severity: 1, txt: 'ABWÄGEN-Status — kleinerer Stake empfohlen' });
    }

    const totalSev = factors.reduce((s, f) => s + f.severity, 0);
    const level = totalSev >= 3 ? 'high'
                : totalSev >= 1 ? 'med'
                : 'low';
    const label = level === 'high' ? 'Hoch' : level === 'med' ? 'Mittel' : 'Niedrig';
    const text = factors.length
      ? factors.slice(0, 2).map(f => f.txt).join('. ') + '.'
      : 'Keine erkennbaren zusätzlichen Risiken über Standard-Spielunsicherheit hinaus.';
    return { level, label, text };
  }

  // ── Insights auto-extrahieren (3 stärkste Signale) ───────
  function _extractInsights(pick, fx, home, away, homeForm, awayForm, eloDiff, fxOdds) {
    const m = (pick.market || '').toLowerCase();
    const isOver  = m.includes('über') || m.includes('over');
    const isUnder = m.includes('unter') || m.includes('under');
    const isBtts  = m.includes('beide') || m.includes('btts');
    const isHome  = m.includes('heim') || m.includes('dnb: heim');
    const isAway  = m.includes('ausw') || m.includes('dnb: ausw');

    const candidates = [];

    // ── Form-basierte Insights ──
    if (homeForm && homeForm.games >= 3) {
      if (isHome) {
        candidates.push({
          score: (homeForm.avgScored || 0) * 10,
          txt: `${home.name} erzielte in letzten ${homeForm.games} Spielen <strong>${(homeForm.avgScored||0).toFixed(1)} Tore/Spiel</strong> bei <strong>${(homeForm.avgConceded||0).toFixed(1)} Gegentoren</strong>.`,
          tag: `Form n=${homeForm.games}`, tagCls: 'wm-tag-data',
        });
      }
      if (isOver || isBtts) {
        candidates.push({
          score: (homeForm.over25Rate || 0) * 30,
          txt: `${home.name} traf in <strong>${Math.round((homeForm.bttsRate||0)*100)}% der Spiele BTTS</strong> und scored Ø ${(homeForm.avgScored||0).toFixed(1)}.`,
          tag: `Form n=${homeForm.games}`, tagCls: 'wm-tag-data',
        });
      }
      if (isUnder) {
        candidates.push({
          score: 30 - (homeForm.over25Rate || 0) * 30,
          txt: `${home.name} hatte in <strong>${Math.round((1-(homeForm.over25Rate||0))*100)}% der Spiele unter 2.5 Tore</strong> — defensiv-getrieben.`,
          tag: `Form n=${homeForm.games}`, tagCls: 'wm-tag-data',
        });
      }
    }
    if (awayForm && awayForm.games >= 3) {
      if (isAway) {
        candidates.push({
          score: (awayForm.avgScored || 0) * 10,
          txt: `${away.name} kommt mit <strong>${(awayForm.avgScored||0).toFixed(1)} Tore/Spiel</strong> in der Form, ${(awayForm.avgConceded||0).toFixed(1)} hinten.`,
          tag: `Form n=${awayForm.games}`, tagCls: 'wm-tag-data',
        });
      }
      if (isOver || isBtts) {
        candidates.push({
          score: (awayForm.bttsRate || 0) * 30,
          txt: `${away.name} traf in <strong>${Math.round((awayForm.bttsRate||0)*100)}% BTTS</strong> und kassiert Ø ${(awayForm.avgConceded||0).toFixed(1)} Tore.`,
          tag: `Form n=${awayForm.games}`, tagCls: 'wm-tag-data',
        });
      }
    }

    // ── Elo-Diff Insight ──
    if (eloDiff != null && Math.abs(eloDiff) >= 100 && (isHome || isAway)) {
      const stronger = eloDiff > 0 ? home : away;
      candidates.push({
        score: Math.abs(eloDiff) / 5,
        txt: `Elo-Differenz <strong>${eloDiff > 0 ? '+' : ''}${eloDiff.toFixed(0)}</strong> zugunsten ${stronger.name} — historisch klares Klassenmerkmal.`,
        tag: 'Elo', tagCls: 'wm-tag-data',
      });
    }

    // ── CLV Insight (Sharps) ──
    if (typeof pick.clvPP === 'number' && Math.abs(pick.clvPP) >= 2) {
      const positive = pick.clvPP > 0;
      candidates.push({
        score: Math.abs(pick.clvPP) * 4 + 20,
        txt: positive
          ? `Pinnacle hat die Quote seit Eröffnung um <strong>${Math.abs(pick.clvPP).toFixed(1)}pp Richtung unser Pick</strong> bewegt — <strong style="color:var(--accent);">CLV+</strong>.`
          : `Pinnacle bewegte die Quote um <strong>${Math.abs(pick.clvPP).toFixed(1)}pp gegen uns</strong> seit Eröffnung — <strong style="color:var(--red);">CLV-</strong>, Markt sieht es anders.`,
        tag: 'Pinnacle', tagCls: positive ? 'wm-tag-sharp' : 'wm-tag-warn',
      });
    }

    // ── Public-Bias Insight ──
    if (pick.publicBias && pick.publicBias.pp >= 4) {
      const dir = pick.publicBias.direction === 'over' ? 'überschätzt' : 'unterschätzt';
      candidates.push({
        score: pick.publicBias.pp * 3,
        txt: `Public-Bookies <strong>${dir}</strong> dieses Outcome um <strong>${pick.publicBias.pp}pp</strong> — Sharps vs. Square-Money divergiert.`,
        tag: 'Public-Bias', tagCls: 'wm-tag-edge',
      });
    }

    // ── Corner-Insight (wenn das Match Corner-Picks hat oder Hero-Pick BTTS/OU ist) ──
    // Pulls Eckenerwartung aus dem cornersExpected-Feld der Corner-Picks im Match
    const allMatchPicks = ((_wmData && _wmData.picks) || {})[`${fx.groupKey}-${fx.matchday}-${fx.home}-${fx.away}`] || [];
    const cornerPick = allMatchPicks.find(p => p.cornersExpected);
    if (cornerPick && cornerPick.cornersExpected) {
      const ce = cornerPick.cornersExpected;
      const isCornerHero = (pick.market || '').toLowerCase().includes('ecken');
      if (isCornerHero) {
        candidates.push({
          score: 50,
          txt: `Modell-Erwartung: <strong>${ce.total} Ecken Total</strong> (${ce.home} ${home.flag} / ${ce.away} ${away.flag}). Basis: Form-Ø (forAvg + Gegner againstAvg).`,
          tag: 'Ecken-Modell', tagCls: 'wm-tag-data',
        });
      } else if (isOver || isBtts || isUnder) {
        // Bonus-Insight für Tor-Picks: hohe Eckenzahl korreliert oft mit Tor-Aktivität
        candidates.push({
          score: 15,
          txt: `Eckenerwartung des Modells: <strong>${ce.total} Total</strong> — ${ce.total >= 9.5 ? 'offene Partie mit viel Volumen vor dem Tor' : 'kontrollierter Spielfluss'}.`,
          tag: 'Ecken', tagCls: 'wm-tag-data',
        });
      }
    }

    // ── Edge-Magnitude Insight (Fallback wenn nichts anderes) ──
    if (candidates.length < 3 && pick.edgePP) {
      candidates.push({
        score: 5,
        txt: `Unser Modell sieht <strong>${pick.edgePP}pp Edge</strong> ggü. dem Bookie-Preis — Modell-Wahrscheinlichkeit ${Math.round(100/(pick.modelOdds||1))}% vs. Markt ${Math.round(100/(pick.odds||1))}%.`,
        tag: 'Edge', tagCls: 'wm-tag-edge',
      });
    }

    // Top-3 nach Score auswählen + dedup
    candidates.sort((a, b) => b.score - a.score);
    const seen = new Set();
    const top = [];
    for (const c of candidates) {
      const key = c.txt.substring(0, 40);
      if (seen.has(key)) continue;
      seen.add(key);
      top.push(c);
      if (top.length >= 3) break;
    }
    return top;
  }

  // ── Modal-Body bauen ─────────────────────────────────────
  function _buildPickWhyModal(pick, fx, home, away, homeForm, awayForm, eloDiff, fxOdds, matchPage) {
    if (!pick) return '';
    const score      = _confidenceScore(pick);
    const scoreLabel = _confidenceLabel(score, pick);
    const scorePct   = score * 10;
    const isAbw      = pick.verdict === 'ABWÄGEN';
    const accent     = isAbw ? '#f5c518' : '#00d4a1';
    const oddsStr    = pick.odds != null ? pick.odds.toFixed(2) : '—';

    // Time-Label
    let timeLabel = '';
    try {
      const dt = new Date(`${fx.date}T${fx.time || '19:00'}:00`);
      const wd = ['So','Mo','Di','Mi','Do','Fr','Sa'][dt.getDay()];
      timeLabel = `${wd} ${dt.getDate().toString().padStart(2,'0')}.${(dt.getMonth()+1).toString().padStart(2,'0')}. · ${fx.time || ''}`;
    } catch (e) {}

    // ── 1. MODELL-RECHNUNG ──
    const elo_h = matchPage?.homeElo || home.elo;
    const elo_a = matchPage?.awayElo || away.elo;
    const xg_h  = matchPage?.xgHome;
    const xg_a  = matchPage?.xgAway;
    const probMarket  = pick.odds      ? Math.round(100 / pick.odds)      : null;
    const probModel   = pick.modelOdds ? Math.round(100 / pick.modelOdds) : null;
    let calcRows = '';
    if (elo_h && elo_a) {
      calcRows += `<div class="wm-calc-row"><span class="wm-calc-label">Elo (${home.name} / ${away.name})</span><span class="wm-calc-val">${elo_h} / ${elo_a} (${eloDiff > 0 ? '+' : ''}${eloDiff})</span></div>`;
    }
    if (xg_h != null && xg_a != null) {
      calcRows += `<div class="wm-calc-row"><span class="wm-calc-label">xG Erwartung (H / A)</span><span class="wm-calc-val">${xg_h.toFixed(2)} / ${xg_a.toFixed(2)}</span></div>`;
    }
    // Travel-Mod
    const travel_h = _teamLegForMatch && _teamLegForMatch(fx.home, fx.matchday);
    if (travel_h && travel_h.discount != null && travel_h.discount < 1.0) {
      const pp = Math.round((1 - travel_h.discount) * 100);
      calcRows += `<div class="wm-calc-row"><span class="wm-calc-label">Travel-Mod ${home.flag}</span><span class="wm-calc-val">−${pp}% xG</span></div>`;
    }
    if (probModel != null) {
      calcRows += `<div class="wm-calc-row"><span class="wm-calc-label">P(${pick.market}) Modell</span><span class="wm-calc-val">${probModel}%</span></div>`;
    }
    if (probModel != null && probMarket != null) {
      calcRows += `<div class="wm-calc-row"><span class="wm-calc-label">Modell-Quote → Markt-Quote</span><span class="wm-calc-val acc">${(pick.modelOdds||0).toFixed(2)} → ${oddsStr} = +${pick.edgePP}pp Edge</span></div>`;
    }

    // ── 2. KEY INSIGHTS ──
    const insights = _extractInsights(pick, fx, home, away, homeForm, awayForm, eloDiff, fxOdds);
    const insightHtml = insights.map((i, idx) => `
      <div class="wm-insight">
        <div class="wm-insight-num">${(idx+1).toString().padStart(2,'0')}</div>
        <div class="wm-insight-txt">${i.txt}<span class="wm-insight-tag ${i.tagCls}">${i.tag}</span></div>
      </div>`).join('');

    // ── 3. CLV-Block ──
    let clvBlock = '';
    if (typeof pick.clvPP === 'number' && Math.abs(pick.clvPP) >= 1) {
      const pos = pick.clvPP > 0;
      const sign = pos ? '+' : '';
      // Opening-Quote aus Markt-Open ableiten
      let openOdds = null;
      const oddsKey = _pickToOddsKey(pick.market);
      if (oddsKey && fxOdds?.odds_open?.[oddsKey]) openOdds = fxOdds.odds_open[oddsKey];
      const driftStr = openOdds ? `${openOdds.toFixed(2)} → ${oddsStr}` : `${sign}${pick.clvPP.toFixed(1)}pp`;
      clvBlock = `<div class="wm-section">
        <div class="wm-section-label">💎 Closing-Line-Value</div>
        <div class="wm-clv ${pos ? '' : 'wm-clv-neg'}">
          <div class="wm-clv-head">
            <span class="wm-clv-title">Quote-Bewegung seit Eröffnung</span>
            <span class="wm-clv-pp">${driftStr} · ${pos ? 'CLV+' : 'CLV-'} (${sign}${pick.clvPP.toFixed(1)}pp)</span>
          </div>
          <div class="wm-clv-explanation">
            ${pos
              ? `Sharps verteuern unsere Seite — <strong style="color:var(--accent);">Markt bestätigt unsere Sicht</strong>.`
              : `Sharps bewegen die Quote gegen uns — Markt sieht es anders. Pick mit Vorsicht behandeln.`}
          </div>
        </div>
      </div>`;
    }

    // ── 4. Backtest aus _confidenceStats ──
    let backtestBlock = '';
    if (_confidenceFor) {
      const conf = _confidenceFor(pick);
      if (conf && conf.n >= 3) {
        const scopeLabel = {
          cluster: 'identischen Picks',
          market:  `${pick.market}-Picks`,
          angle:   'ähnlichen Picks',
          global:  'allen WM-Picks',
        }[conf.scope] || 'vergleichbaren Picks';
        backtestBlock = `<div class="wm-section">
          <div class="wm-section-label">📊 Historischer Backtest</div>
          <div class="wm-backtest">
            <div class="wm-bt-num">${conf.rate}%</div>
            <div class="wm-bt-text">
              Trefferquote bei <strong>${scopeLabel}</strong> (n=${conf.n}).
              ${conf.rate >= 55 ? 'Solide Validierung des Modells.' : conf.rate >= 45 ? 'Mittlere Validierung — Edge nicht garantiert.' : 'Underperformance — Pick mit Vorsicht.'}
            </div>
          </div>
        </div>`;
      }
    }

    // ── 5. Risk + Stake ──
    const risk  = _riskAssessment(pick, fx, eloDiff, homeForm, awayForm);
    const stake = _stakeRange(pick);
    const dq    = pick.dataQuality || 'elo';

    // ── 6. Data-Footer ──
    const formN = (homeForm?.games || 0) + (awayForm?.games || 0);
    const updatedAt = matchPage?.generatedAt
      ? `vor ${Math.max(1, Math.round((Date.now() - new Date(matchPage.generatedAt).getTime()) / 60000))}m`
      : 'kürzlich';

    return `
      <div class="wm-header">
        <div class="wm-confidence-label">
          <span>KONFIDENZ</span>
          <span class="wm-confidence-score" style="color:${accent};">${scoreLabel}</span>
        </div>
        <div class="wm-confidence-bar">
          <div class="wm-confidence-fill" style="width:${scorePct}%;background:${accent};"></div>
        </div>
        <div class="wm-match-row">
          <div class="wm-team">
            <span class="wm-team-flag">${home.flag}</span>
            <div class="wm-team-name">${home.name}</div>
          </div>
          <div class="wm-pick-col">
            <div class="wm-time">${timeLabel}</div>
            <div class="wm-pick-odds" style="color:${accent};">${oddsStr}</div>
            <div class="wm-pick-market">${isAbw ? 'Vorsichtiger Pick' : 'Unser Pick'}<strong>${pick.market}</strong></div>
          </div>
          <div class="wm-team">
            <span class="wm-team-flag">${away.flag}</span>
            <div class="wm-team-name">${away.name}</div>
          </div>
        </div>
      </div>

      ${calcRows ? `<div class="wm-section">
        <div class="wm-section-label">📐 Modell-Rechnung — woher kommt die Quote</div>
        <div class="wm-calc">${calcRows}</div>
      </div>` : ''}

      ${insights.length ? `<div class="wm-section">
        <div class="wm-section-label">🎯 Schlüssel-Signale</div>
        ${insightHtml}
      </div>` : ''}

      ${clvBlock}
      ${backtestBlock}

      <div class="wm-section">
        <div class="wm-section-label">⚖️ Risiko & Stake-Empfehlung</div>
        <div class="wm-risk-stake">
          <div class="wm-risk">
            <div class="wm-risk-val ${risk.level}">${risk.label}</div>
            <div class="wm-risk-txt">${risk.text} Daten-Tier: <strong style="color:var(--text);">${dq}</strong>.</div>
          </div>
          <div class="wm-stake">
            <div class="wm-stake-val">${stake.label}</div>
            <div class="wm-stake-lbl">Bankroll</div>
            <div class="wm-stake-sub">${stake.sub}</div>
          </div>
        </div>
      </div>

      <div class="wm-data-footer">
        <span><strong>Bookie:</strong> Pinnacle</span>
        <span><strong>Form:</strong> ${formN} Spiele${homeForm || awayForm ? '' : ' (fehlt)'}</span>
        <span><strong>Aktualisiert:</strong> ${updatedAt}</span>
      </div>
    `;
  }

  // ─────────────────────────────────────────────────────
  //  SIGNALS — bis zu 4 KPIs passend zum Pick
  // ─────────────────────────────────────────────────────
  function _buildSignals(pick, fx, home, away, homeForm, awayForm, polyFix, eloDiff) {
    const signals = [];
    const m = (pick?.market || '').toLowerCase();
    const h2hRaw = (_wmData.h2h || {});
    const h2h = h2hRaw[`${fx.home}-${fx.away}`] || h2hRaw[`${fx.away}-${fx.home}`] || null;
    const cornersForm = _wmData.cornersForm || {};

    // Hilfs-Schätzungen aus Form-Daten
    const cleanSheets = (form) => {
      // bttsRate = "beide trafen" → Clean Sheet ≈ Anteil ohne BTTS + Spiele zu 0:x
      // Approx: cleanSheets ≈ (1 - bttsRate) * games — konservative Schätzung
      if (!form || form.bttsRate == null || !form.games) return null;
      return Math.round((1 - form.bttsRate) * form.games);
    };
    // _winStreak / _lossStreak sind module-scoped (oben definiert)
    const winsInLast = (form, n) => {
      const arr = (form?.last10 || form?.last5 || []).slice(-n);
      return arr.filter(r => r === 'W').length;
    };

    // Pick-specific signals
    if ((m.includes('über') || m.includes('over')) && m.includes('2.5')) {
      // Stärkste Offensive zuerst
      if (homeForm?.avgScored != null && homeForm.avgScored >= 2.0) {
        signals.push({ label: `${home.flag} Tor-Schnitt`, value: homeForm.avgScored.toFixed(1), cls: 'cc-val-hot' });
      }
      if (awayForm?.avgScored != null && awayForm.avgScored >= 2.0) {
        signals.push({ label: `${away.flag} Tor-Schnitt`, value: awayForm.avgScored.toFixed(1), cls: 'cc-val-hot' });
      }
      if (homeForm?.over25Rate != null && signals.length < 3) {
        const v = Math.round(homeForm.over25Rate * 100);
        signals.push({ label: `Ü2.5 ${home.flag}`, value: v + '%', cls: v >= 55 ? 'cc-val-hot' : '' });
      }
      if (awayForm?.over25Rate != null && signals.length < 3) {
        const v = Math.round(awayForm.over25Rate * 100);
        signals.push({ label: `Ü2.5 ${away.flag}`, value: v + '%', cls: v >= 55 ? 'cc-val-hot' : '' });
      }
      if (h2h?.over25Rate != null && signals.length < 4) {
        const v = Math.round(h2h.over25Rate * 100);
        signals.push({ label: `Ü2.5 H2H (${h2h.games || '?'})`, value: v + '%', cls: v >= 50 ? 'cc-val-hot' : '' });
      }
      if (homeForm?.bttsRate != null && awayForm?.bttsRate != null && signals.length < 4) {
        const v = Math.round(((homeForm.bttsRate + awayForm.bttsRate) / 2) * 100);
        signals.push({ label: 'BTTS-Trend', value: v + '%', cls: v >= 55 ? 'cc-val-hot' : '' });
      }
    }
    else if ((m.includes('unter') || m.includes('under')) && m.includes('2.5')) {
      // Clean Sheets — viel narrativer als "Gegen 0.3"
      const homeCS = cleanSheets(homeForm);
      const awayCS = cleanSheets(awayForm);
      if (awayCS != null && homeForm?.games) {
        signals.push({ label: `${away.flag} Clean Sheets`, value: `${awayCS}/${awayForm.games}`, cls: awayCS / awayForm.games >= 0.5 ? 'cc-val-cool' : '' });
      }
      if (homeCS != null && homeForm?.games) {
        signals.push({ label: `${home.flag} Clean Sheets`, value: `${homeCS}/${homeForm.games}`, cls: homeCS / homeForm.games >= 0.5 ? 'cc-val-cool' : '' });
      }
      if (homeForm?.avgConceded != null && signals.length < 3) {
        signals.push({ label: `${home.flag} Gegen Ø`, value: homeForm.avgConceded.toFixed(1), cls: homeForm.avgConceded < 0.7 ? 'cc-val-cool' : '' });
      }
      if (awayForm?.avgConceded != null && signals.length < 3) {
        signals.push({ label: `${away.flag} Gegen Ø`, value: awayForm.avgConceded.toFixed(1), cls: awayForm.avgConceded < 0.7 ? 'cc-val-cool' : '' });
      }
      if (h2h?.avgGoals != null && signals.length < 4) {
        signals.push({ label: `H2H Ø Tore (${h2h.games})`, value: h2h.avgGoals.toFixed(1), cls: h2h.avgGoals < 2.5 ? 'cc-val-cool' : '' });
      }
    }
    else if (m.includes('heim') || m.includes('home') || m.includes('auswärt') || m.includes('away')) {
      if (eloDiff != null) signals.push({ label: 'Elo-Diff', value: (eloDiff > 0 ? '+' : '') + eloDiff, cls: Math.abs(eloDiff) >= 200 ? 'cc-val-hot' : '' });
      // Sieg-Serie zuerst (narrative Schärfe)
      const homeStreak = _winStreak(homeForm);
      const awayStreak = _winStreak(awayForm);
      if (homeStreak >= 3) {
        signals.push({ label: `${home.flag} Sieg-Serie`, value: `${homeStreak} in Folge`, cls: 'cc-val-hot' });
      }
      if (awayStreak >= 3) {
        signals.push({ label: `${away.flag} Sieg-Serie`, value: `${awayStreak} in Folge`, cls: 'cc-val-hot' });
      }
      if (signals.length < 3 && homeForm?.last5) {
        const w = homeForm.last5.filter(r => r === 'W').length;
        signals.push({ label: `${home.flag} Siege /5`, value: w, cls: w >= 4 ? 'cc-val-hot' : '' });
      }
      if (signals.length < 3 && awayForm?.last5) {
        const w = awayForm.last5.filter(r => r === 'W').length;
        signals.push({ label: `${away.flag} Siege /5`, value: w, cls: w >= 4 ? 'cc-val-hot' : '' });
      }
      if (signals.length < 4 && h2h && h2h.games > 0) {
        signals.push({ label: `H2H (${h2h.games})`, value: `${h2h.homeWins}-${h2h.draws}-${h2h.awayWins}` });
      }
    }
    else {
      if (eloDiff != null) signals.push({ label: 'Elo-Diff', value: (eloDiff > 0 ? '+' : '') + eloDiff });
      if (homeForm?.last5) {
        const w = homeForm.last5.filter(r => r === 'W').length;
        signals.push({ label: `${home.flag} Siege /5`, value: w });
      }
      if (awayForm?.last5) {
        const w = awayForm.last5.filter(r => r === 'W').length;
        signals.push({ label: `${away.flag} Siege /5`, value: w });
      }
      if (h2h && h2h.games > 0) {
        signals.push({ label: 'H2H Spiele', value: h2h.games });
      }
    }

    // Poly-Edge als Bonus (nur wenn substantiell)
    if (polyFix?.bestEdge != null && Math.abs(polyFix.bestEdge) >= 3) {
      const cls = polyFix.bestEdge >= 5 ? 'cc-val-hot' : '';
      signals.push({ label: 'Poly-Edge', value: '+' + polyFix.bestEdge.toFixed(1) + 'pp', cls });
    }

    // Travel-Burden — wenn signifikant (>= 3000km oder critical/high) als Signal mit aufnehmen
    const homeLeg = _teamLegForMatch(fx.home, fx.matchday);
    const awayLeg = _teamLegForMatch(fx.away, fx.matchday);
    const relLeg = (leg) => leg && !leg.same_venue && ((leg.km || 0) >= 3000 || ['critical','high'].includes((leg.burden||'').toLowerCase()));
    if (relLeg(homeLeg) && signals.length < 4) {
      signals.push({ label: `${home.flag} Anreise`, value: `${Math.round(homeLeg.km).toLocaleString('de')} km`, cls: 'cc-val-hot' });
    }
    if (relLeg(awayLeg) && signals.length < 4) {
      signals.push({ label: `${away.flag} Anreise`, value: `${Math.round(awayLeg.km).toLocaleString('de')} km`, cls: 'cc-val-hot' });
    }

    // Top-Stürmer-Verletzung — sobald injuries-Daten kommen
    const homeOut = _topInjuredScorer(fx.home);
    const awayOut = _topInjuredScorer(fx.away);
    if (homeOut && signals.length < 4) {
      signals.push({ label: `${home.flag} ohne ${homeOut.position || 'Star'}`, value: homeOut.name.split(' ').pop(), cls: 'cc-val-cool' });
    }
    if (awayOut && signals.length < 4) {
      signals.push({ label: `${away.flag} ohne ${awayOut.position || 'Star'}`, value: awayOut.name.split(' ').pop(), cls: 'cc-val-cool' });
    }

    // Public-vs-Sharp Bias als prominentes Signal (knallt — zeigt wo das Volumen-Geld irrt)
    if (pick?.publicBias && pick.publicBias.pp >= 4) {
      const pb = pick.publicBias;
      const ocShort = { hw: 'HW', dr: 'X', aw: 'AW' }[pb.outcome] || pb.outcome;
      const sign = pb.direction === 'over' ? '+' : '-';
      signals.unshift({ label: `💸 Public-Bias ${ocShort}`, value: `${sign}${pb.pp}pp`, cls: 'cc-val-hot' });
    }

    return signals.slice(0, 4);
  }

  // ─────────────────────────────────────────────────────
  //  VENUE ENV — gibt eine kompakte Pille (Höhe/Hitze/Dome)
  //  nur wenn relevant (>1500m, >30°C, Dome). Sonst nichts.
  // ─────────────────────────────────────────────────────
  function _venueEnvPill(venue) {
    if (!venue) return '';
    const v = venue.toLowerCase();
    // High altitude
    if (v.includes('azteca') || v.includes('mexico city')) return `<span class="cc-dot"></span><span class="cc-env-pill cc-env-alt">🏔 2200m</span>`;
    if (v.includes('akron') || v.includes('guadalajara')) return `<span class="cc-dot"></span><span class="cc-env-pill cc-env-alt">🏔 1566m</span>`;
    // Dome
    if (v.includes("at&t") || v.includes('att stadium') || v.includes('dallas')) return `<span class="cc-dot"></span><span class="cc-env-pill cc-env-dome">🏛 Dome</span>`;
    if (v.includes('nrg') || v.includes('houston')) return `<span class="cc-dot"></span><span class="cc-env-pill cc-env-dome">🏛 Dome</span>`;
    if (v.includes('bc place') || v.includes('vancouver')) return `<span class="cc-dot"></span><span class="cc-env-pill cc-env-dome">🏛 Dome</span>`;
    // Heat
    if (v.includes('miami') || v.includes('monterrey') || v.includes('bbva')) return `<span class="cc-dot"></span><span class="cc-env-pill cc-env-heat">🌡 30°C+</span>`;
    return '';
  }

  // ─────────────────────────────────────────────────────
  //  VENUE TZ — Anstoßzeit am Spielort (UTC-Offset für die
  //  16 Host-Cities). "21:00 Berlin · 15:00 NY" Format.
  // ─────────────────────────────────────────────────────
  // CEST = UTC+2 (Sommer) — fix für WM-Zeitraum Juni/Juli.
  // Liefert Offset in Stunden gegenüber UTC für jede Stadt.
  function _venueTz(venue) {
    if (!venue) return null;
    const v = venue.toLowerCase();
    // EST/EDT = UTC-4 im Sommer (Boston, NY, Philly, Miami, Atlanta, Toronto)
    if (v.includes('metlife') || v.includes('new york') || v.includes('east rutherford')) return { off: -4, city: 'NY', tzShort: 'EDT' };
    if (v.includes('gillette') || v.includes('foxborough') || v.includes('boston'))    return { off: -4, city: 'Boston', tzShort: 'EDT' };
    if (v.includes('hard rock') || v.includes('miami'))                                 return { off: -4, city: 'Miami', tzShort: 'EDT' };
    if (v.includes('mercedes-benz') || v.includes('atlanta'))                           return { off: -4, city: 'Atlanta', tzShort: 'EDT' };
    if (v.includes('bmo field') || v.includes('toronto'))                               return { off: -4, city: 'Toronto', tzShort: 'EDT' };
    if (v.includes('philly') || v.includes('philadelphia') || v.includes('lincoln'))   return { off: -4, city: 'Philly', tzShort: 'EDT' };
    // CST/CDT = UTC-5 (Dallas, Houston, KC, Mexiko-City, Guadalajara, Monterrey)
    if (v.includes("at&t") || v.includes('dallas'))                                     return { off: -5, city: 'Dallas', tzShort: 'CDT' };
    if (v.includes('nrg') || v.includes('houston'))                                     return { off: -5, city: 'Houston', tzShort: 'CDT' };
    if (v.includes('arrowhead') || v.includes('kansas'))                                return { off: -5, city: 'KC', tzShort: 'CDT' };
    if (v.includes('azteca') || v.includes('mexico city'))                              return { off: -6, city: 'Mexico City', tzShort: 'CST' }; // Mexico nicht DST
    if (v.includes('akron') || v.includes('guadalajara'))                               return { off: -6, city: 'Guadalajara', tzShort: 'CST' };
    if (v.includes('bbva') || v.includes('monterrey'))                                  return { off: -6, city: 'Monterrey', tzShort: 'CST' };
    // PST/PDT = UTC-7 (Vancouver, LA, Seattle, SF)
    if (v.includes('bc place') || v.includes('vancouver'))                              return { off: -7, city: 'Vancouver', tzShort: 'PDT' };
    if (v.includes('sofi') || v.includes('los angeles') || v.includes('inglewood'))    return { off: -7, city: 'LA', tzShort: 'PDT' };
    if (v.includes('seattle') || v.includes('lumen'))                                   return { off: -7, city: 'Seattle', tzShort: 'PDT' };
    if (v.includes("levi's") || v.includes('santa clara') || v.includes('san francisco')) return { off: -7, city: 'SF', tzShort: 'PDT' };
    return null;
  }

  // ─────────────────────────────────────────────────────
  //  Pick-Confidence Lookup — historische Hit-Rate für einen Pick
  //  Versucht zuerst engsten Cluster, fällt dann auf Markt/Angle zurück.
  // ─────────────────────────────────────────────────────
  function _confidenceFor(pick) {
    if (!_confidenceStats || !pick) return null;
    const angleKey = _angleKeyFromMarket(pick.market);
    const edgeBkt  = (pick.edgePP == null) ? 'n/a'
                   : pick.edgePP < 5  ? '0-5pp'
                   : pick.edgePP < 10 ? '5-10pp'
                   : '10pp+';
    const dq       = pick.dataQuality || '?';
    const clusterKey = `${pick.market}|${angleKey}|${edgeBkt}|${dq}`;
    // 1. Exakter 4-dim Cluster
    const cluster = (_confidenceStats.byCluster || {})[clusterKey];
    if (cluster && cluster.n >= 3) return { ...cluster, scope: 'cluster' };
    // 2. byMarket
    const m = (_confidenceStats.byMarket || {})[pick.market];
    if (m && m.n >= 5) return { ...m, scope: 'market' };
    // 3. byAngle
    const a = (_confidenceStats.byAngle || {})[angleKey];
    if (a && a.n >= 8) return { ...a, scope: 'angle' };
    // 4. Global
    const g = _confidenceStats.global || {};
    if (g.n >= 15) return { ...g, scope: 'global' };
    return null;
  }
  function _angleKeyFromMarket(market) {
    const m = (market || '').toLowerCase();
    if (m.includes('über') || m.includes('over')) return m.includes('2.5') ? 'torfest' : 'other';
    if (m.includes('unter') || m.includes('under')) return m.includes('2.5') ? 'defshow' : 'other';
    if (m.includes('beide teams treffen') || m.includes('btts')) {
      return (m.includes('nein') || m.includes('no')) ? 'defshow' : 'torfest';
    }
    if (m.includes('heim') || m.includes('home') || m === '1') return 'pflicht';
    if (m.includes('auswärt') || m.includes('away') || m === '2') return 'pflicht';
    if (m.includes('unentsch') || m.includes('draw')) return 'duell';
    if (m.includes('dnb')) return 'pflicht';
    return 'other';
  }

  // ─────────────────────────────────────────────────────
  //  Form-Helpers — Streaks aus last10/last5 ableiten
  // ─────────────────────────────────────────────────────
  function _winStreak(form) {
    const arr = form?.last10 || form?.last5;
    if (!arr) return 0;
    let s = 0;
    for (let i = arr.length - 1; i >= 0; i--) {
      if (arr[i] === 'W') s++; else break;
    }
    return s;
  }
  function _lossStreak(form) {
    const arr = form?.last10 || form?.last5;
    if (!arr) return 0;
    let s = 0;
    for (let i = arr.length - 1; i >= 0; i--) {
      if (arr[i] === 'L') s++; else break;
    }
    return s;
  }

  // ─────────────────────────────────────────────────────
  //  Travel-Burden für ein Team beim Anflug auf diesen Spieltag
  //  Liefert das passende `leg` (matchday_from = matchday-1)
  //  oder null wenn kein Anflug nötig (Spieltag 1 oder gleiche Stadt)
  // ─────────────────────────────────────────────────────
  function _teamLegForMatch(teamId, matchday) {
    const tb = _travelLookup[teamId];
    if (!tb || !tb.legs) return null;
    return tb.legs.find(l => l.matchday_to === matchday) || null;
  }

  // Liefert die Burden-Pille für ein Team — knapp, nur wenn relevant
  function _travelPill(teamFlag, leg) {
    if (!leg || leg.same_venue || (leg.km || 0) < 1500) return '';
    const burden = (leg.burden || '').toLowerCase();
    if (burden === 'none' || burden === 'low') return '';
    const km = Math.round(leg.km).toLocaleString('de');
    const cls = burden === 'critical' ? 'cc-env-heat'
              : burden === 'high'     ? 'cc-env-alt'
              :                          'cc-env-pill';
    const icon = burden === 'critical' ? '⚠️' : '✈️';
    return `<span class="cc-env-pill ${cls}">${icon} ${teamFlag} ${km} km</span>`;
  }

  // ─────────────────────────────────────────────────────
  //  Verletzungs-Info für ein Team — nutzt `injuries`-Feld
  //  Schema (sobald fetch_wm_injuries.py voll läuft):
  //    injuries[teamId] = { players: [{name, position, status, severity, missMatch}] }
  //  status = "out" | "doubtful" | "back"
  //  severity = 1-3 (3 = Top-Star, 1 = Reservist)
  //  Aktuell: nur _meta gefüllt → graceful return
  // ─────────────────────────────────────────────────────
  function _topInjuredScorer(teamId) {
    const inj = (_wmData.injuries || {})[teamId];
    if (!inj || !inj.players) return null;
    // Top-Star raus: severity 3 OR Position ST/CAM/RW/LW + status "out"
    const outAttackers = (inj.players || []).filter(p =>
      p.status === 'out' &&
      (p.severity >= 3 || ['ST','CF','CAM','RW','LW','LM','RM'].includes(p.position))
    );
    if (!outAttackers.length) return null;
    // Severity-sortiert
    outAttackers.sort((a, b) => (b.severity || 0) - (a.severity || 0));
    return outAttackers[0];
  }

  // ─────────────────────────────────────────────────────
  //  Wetter-Pille — liest fx.weather wenn vorhanden.
  //  Schema (sobald fetch_wm_weather.py Daten schreibt):
  //    fx.weather = { temp: 22, condition: "rain" | "sun" | "cloud" | "snow", windKph: 18, humidity: 70 }
  //  Aktuell graceful: zeigt nichts wenn keine Daten.
  // ─────────────────────────────────────────────────────
  function _weatherPill(fx) {
    const w = fx && fx.weather;
    if (!w || w.temp == null) return '';
    const cond = (w.condition || '').toLowerCase();
    let icon = '🌤';
    if (cond.includes('rain') || cond.includes('shower')) icon = '🌧';
    else if (cond.includes('storm') || cond.includes('thunder')) icon = '⛈';
    else if (cond.includes('snow')) icon = '❄️';
    else if (cond.includes('clear') || cond.includes('sun')) icon = '☀️';
    else if (cond.includes('cloud') || cond.includes('overcast')) icon = '☁️';
    const wind = w.windKph && w.windKph >= 30 ? ` · 💨 ${Math.round(w.windKph)}` : '';
    const cls = w.temp >= 32 ? 'cc-env-heat' : 'cc-env-pill';
    return `<span class="cc-dot"></span><span class="cc-env-pill ${cls === 'cc-env-heat' ? 'cc-env-heat' : ''}">${icon} ${Math.round(w.temp)}°C${wind}</span>`;
  }

  // ─────────────────────────────────────────────────────
  //  Lokale Spielort-Zeit aus fx.time (HH:MM, Berlin/CEST)
  //  Wenn Venue in US/MX/CA: liefert ", 15:00 NY" (oder ähnlich).
  //  Sonst leer (z.B. wenn Berlin-Lokal sowieso passt).
  // ─────────────────────────────────────────────────────
  function _venueLocalTime(venue, berlinTime) {
    if (!venue || !berlinTime) return '';
    const tz = _venueTz(venue);
    if (!tz) return '';
    // berlinTime ist "HH:MM" — CEST = UTC+2
    const m = /^(\d{1,2}):(\d{2})$/.exec(berlinTime.trim());
    if (!m) return '';
    let totalMin = parseInt(m[1], 10) * 60 + parseInt(m[2], 10);
    // Berlin → UTC: -2h. UTC → Venue: + tz.off (negativ).
    totalMin += (-2 + tz.off) * 60;
    // Normalisieren (0-1439)
    totalMin = ((totalMin % 1440) + 1440) % 1440;
    const h = String(Math.floor(totalMin / 60)).padStart(2, '0');
    const min = String(totalMin % 60).padStart(2, '0');
    return ` · ${h}:${min} ${tz.city}`;
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
