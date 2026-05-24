// ═══════════════════════════════════════════════════════
//  wm2026-renderer.js — WM 2026 International Cards
//  Renders the International > Cards section (intlCardsPanel)
//
//  Entry point: window.initIntlCards()
//    Called from ui.js showView('intl-cards')
//
//  Data sources:
//    wm2026-data.json  — groups, fixtures, standings, picks,
//                        playerPicks, squads, odds
//
//  Card design (approved):
//    Group bar · Teams + Odds column · Odds strip (if ≥0.05 shift)
//    Venue · Scenario banner (Elo-based until group play begins)
//    Picks section (verdict + market + conf + odds + one info line)
//    Player Picks section (always rendered, empty = hidden)
//    Squad Spotlight footer
// ═══════════════════════════════════════════════════════

(function () {
  'use strict';

  // ── Module state ──────────────────────────────────────
  let _wmData      = null;
  let _activeGroup = 'all';
  let _activeMd    = 'all';   // matchday filter: 'all' | 1 | 2 | 3
  let _loaded      = false;

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
      const resp = await fetch('wm2026-data.json?t=' + Date.now());
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      _wmData = await resp.json();
      window.WM2026_DATA = _wmData;   // expose for Sharp Radar + other modules
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

    // Get distinct matchdays in filtered set
    const matchdays = [...new Set(filtered.map(fx => fx.matchday))].sort((a, b) => a - b);

    // ── Count picks + upcoming per group ─────────────
    const picks       = _wmData.picks       || {};
    const playerPicks = _wmData.playerPicks || {};
    const standings   = _wmData.standings   || {};
    const squads      = _wmData.squads      || {};
    const odds        = _wmData.odds        || {};

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

    html += `
    <div class="wm-header">
      <div class="wm-header-left">
        <div class="wm-title">🌍 FIFA WM 2026</div>
        <div class="wm-subtitle">USA · Canada · Mexico · 48 Teams · 104 Spiele · 11. Jun – 19. Jul</div>
      </div>
      <div class="wm-header-right">
        ${countdownStr}
      </div>
    </div>`;

    // ─── Group Filter ─────────────────────────────────
    html += `<div class="wm-group-filter">`;
    html += `<button class="wm-gf-btn${_activeGroup === 'all' ? ' active' : ''}" onclick="wmSetGroup('all')">⭐ Alle</button>`;
    for (const gKey of groupKeys) {
      const gLabel = groups[gKey].name.replace('Gruppe ', '');
      html += `<button class="wm-gf-btn${_activeGroup === gKey ? ' active' : ''}" onclick="wmSetGroup('${gKey}')">Gr. ${gLabel}</button>`;
    }
    html += `</div>`;

    // ─── Matchday Filter (only when a group is selected) ──
    if (_activeGroup !== 'all') {
      html += `<div class="wm-md-filter">`;
      html += `<button class="wm-md-btn${_activeMd === 'all' ? ' active' : ''}" onclick="wmSetMd('all')">Alle Spieltage</button>`;
      html += `<button class="wm-md-btn${_activeMd === 1 ? ' active' : ''}" onclick="wmSetMd(1)">Spieltag 1</button>`;
      html += `<button class="wm-md-btn${_activeMd === 2 ? ' active' : ''}" onclick="wmSetMd(2)">Spieltag 2</button>`;
      html += `<button class="wm-md-btn${_activeMd === 3 ? ' active' : ''}" onclick="wmSetMd(3)">Spieltag 3</button>`;
      html += `</div>`;
    }

    // ─── Cards ───────────────────────────────────────
    if (!filtered.length) {
      html += `<div style="text-align:center;padding:48px 16px;color:var(--muted);">Keine Spiele gefunden.</div>`;
    } else {
      // Group by date for visual separation
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

        // Card
        const fxOdds    = odds[`${fx.home}-${fx.away}`]    || null;
        const fxPicks   = picks[`${fx.groupKey}-${fx.matchday}-${fx.home}-${fx.away}`]       || [];
        const fxPPicks  = playerPicks[`${fx.groupKey}-${fx.matchday}-${fx.home}-${fx.away}`] || [];
        const fxStand   = standings[fx.groupKey]  || null;
        const gData     = fx.groupData;
        const teams     = gData.teams || [];
        const homeTeam  = teams.find(t => t.id === fx.home) || { id: fx.home, name: fx.home, flag: '🏳', elo: null };
        const awayTeam  = teams.find(t => t.id === fx.away) || { id: fx.away, name: fx.away, flag: '🏳', elo: null };
        const homeSquad = squads[fx.home] || null;
        const awaySquad = squads[fx.away] || null;

        html += _buildCard(fx, gData, homeTeam, awayTeam, fxOdds, fxPicks, fxPPicks, fxStand, homeSquad, awaySquad, todayIso);
      }
      html += `</div>`;
    }

    panel.innerHTML = html;
  }

  // ─────────────────────────────────────────────────────
  //  CARD BUILDER
  // ─────────────────────────────────────────────────────
  function _buildCard(fx, gData, home, away, fxOdds, fxPicks, fxPPicks, standing, homeSquad, awaySquad, todayIso) {
    const eloDiff   = (home.elo && away.elo) ? (home.elo - away.elo) : null;
    const isPlayed  = fx.date < todayIso;
    const isToday   = fx.date === todayIso;
    const hasPicks  = fxPicks.length > 0;
    const hasPlayer = fxPPicks.length > 0;

    // Card accent color
    const accentColor = hasPicks ? '#3fb950'
                      : hasPlayer ? '#a78bfa'
                      : isToday ? '#e3b341'
                      : 'transparent';

    let html = `<div class="wm-card" style="--card-accent:${accentColor}">`;

    // ─── Group bar ────────────────────────────────────
    const groupName = gData.name || ('Gruppe ' + fx.groupKey);
    const timeStr   = fx.time ? ` · ${fx.time} Uhr` : '';
    html += `
    <div class="wm-card-groupbar">
      <span class="wm-group-tag">🌍 ${groupName}</span>
      <span class="wm-matchday-tag">ST ${fx.matchday}</span>
      <span class="wm-groupbar-sep">·</span>
      <span class="wm-date-tag">${_fmtDate(fx.date, fx.time)}</span>
      ${isToday ? '<span class="wm-live-badge">● HEUTE</span>' : ''}
    </div>`;

    // ─── Teams + Odds ─────────────────────────────────
    html += `<div class="wm-card-body">`;

    // Teams column
    const homePos = standing ? standing.findIndex(s => s.id === fx.home) + 1 : 0;
    const awayPos = standing ? standing.findIndex(s => s.id === fx.away) + 1 : 0;

    html += `<div class="wm-teams">`;
    html += _teamRow(home, homePos, 'home');
    html += `<div class="wm-draw-separator"><span>— vs —</span></div>`;
    html += _teamRow(away, awayPos, 'away');
    html += `</div>`;

    // Odds column
    html += `<div class="wm-odds-col">`;
    if (fxOdds && (fxOdds.hw || fxOdds.dr || fxOdds.aw)) {
      html += _oddsCell(fxOdds.hw, 'H', false);
      html += _oddsCell(fxOdds.dr, 'X', false);
      html += _oddsCell(fxOdds.aw, 'A', false);
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

    // ─── Odds strip (line movement) ───────────────────
    if (fxOdds && fxOdds.odds_open && fxOdds.hw != null) {
      const openHw = fxOdds.odds_open.hw;
      if (openHw != null) {
        const shift = fxOdds.hw - openHw;
        if (Math.abs(shift) >= 0.05) {
          const dir      = shift < 0 ? '▼' : '▲';
          const clr      = shift < 0 ? 'var(--green)' : 'var(--red)';
          const shiftAbs = Math.abs(shift).toFixed(2);
          html += `
          <div class="wm-odds-strip">
            <span class="wm-strip-label">LINIE</span>
            <span style="color:${clr};font-weight:700;">${dir} ${shiftAbs}</span>
            <span class="wm-strip-sep">·</span>
            <span class="wm-strip-open">Eröffnung ${openHw.toFixed(2)}</span>
          </div>`;
        }
      }
    }

    // ─── Venue ───────────────────────────────────────
    if (fx.venue) {
      html += `<div class="wm-venue">📍 ${fx.venue}</div>`;
    }

    // ─── Scenario banner ──────────────────────────────
    const scenario = _buildScenario(home, away, eloDiff, fx.matchday, standing, fx, isPlayed);
    if (scenario) {
      html += `<div class="wm-scenario">${scenario}</div>`;
    }

    // ─── Match Picks ──────────────────────────────────
    if (hasPicks) {
      html += `<div class="wm-picks-section">`;
      html += `<div class="wm-section-header">🎯 PICKS</div>`;
      for (const pick of fxPicks) {
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

    // ─── Squad Spotlight ──────────────────────────────
    if (homeSquad || awaySquad) {
      html += `<div class="wm-squad-spotlight">`;
      html += `<div class="wm-section-header" style="color:var(--blue);font-size:9px;">👥 KADER-SPOTLIGHT</div>`;
      html += `<div class="wm-squad-row">`;
      if (homeSquad) {
        html += _squadPlayer(home, homeSquad);
      }
      if (awaySquad) {
        html += _squadPlayer(away, awaySquad);
      }
      html += `</div></div>`;
    }

    html += `</div>`; // wm-card
    return html;
  }

  // ── Team row inside card ──────────────────────────────
  function _teamRow(team, pos, side) {
    const posStr = pos > 0 ? `<span class="wm-standing-pos">${pos}.</span>` : '';
    const eloStr = team.elo ? `<span class="wm-elo-badge">${team.elo}</span>` : '';
    return `
    <div class="wm-team-row wm-team-${side}">
      ${posStr}
      <span class="wm-flag">${team.flag}</span>
      <span class="wm-name">${team.name}</span>
      ${eloStr}
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

  // ── Pick row (match pick or player pick) ──────────────
  function _buildPickRow(pick, isPlayer) {
    const conf      = pick.conf || 'medium';
    const stars     = conf === 'high' ? '★★★' : conf === 'medium' ? '★★☆' : '★☆☆';
    const starsClr  = conf === 'high' ? '#3fb950' : conf === 'medium' ? '#e3b341' : '#8b949e';
    const verdict   = pick.verdict || 'ABWÄGEN';
    const vClr      = verdict === 'BET' ? '#3fb950' : verdict === 'SKIP' ? '#f85149' : '#e3b341';
    const vBg       = verdict === 'BET' ? 'rgba(63,185,80,.12)' : verdict === 'SKIP' ? 'rgba(248,81,73,.10)' : 'rgba(227,179,65,.10)';
    const vBorder   = verdict === 'BET' ? 'rgba(63,185,80,.35)' : verdict === 'SKIP' ? 'rgba(248,81,73,.30)' : 'rgba(227,179,65,.30)';
    const oddsStr   = pick.odds != null ? pick.odds.toFixed(2) : '—';
    const marketStr = isPlayer && pick.playerName ? `${pick.playerName} — ${pick.market}` : pick.market;
    const icon      = pick.icon || (isPlayer ? '⚽' : '🎯');

    return `
    <div class="wm-pick-row">
      <span class="wm-verdict" style="color:${vClr};background:${vBg};border-color:${vBorder};">${verdict}</span>
      <span class="wm-pick-icon">${icon}</span>
      <div class="wm-pick-main">
        <div class="wm-pick-market">${marketStr}</div>
        ${pick.info ? `<div class="wm-pick-info">${pick.info}</div>` : ''}
      </div>
      <span class="wm-pick-stars" style="color:${starsClr}">${stars}</span>
      <span class="wm-pick-odds">${oddsStr}</span>
    </div>`;
  }

  // ── Squad player block ────────────────────────────────
  function _squadPlayer(team, squad) {
    const statsStr = squad.wmGoals != null
      ? `${squad.wmGoals}G ${squad.wmAssists != null ? squad.wmAssists + 'A' : ''}`
      : (squad.caps != null ? `${squad.caps} Caps` : '');
    return `
    <div class="wm-squad-player">
      <span class="wm-squad-flag">${team.flag}</span>
      <div>
        <div class="wm-squad-name">${squad.name}</div>
        <div class="wm-squad-meta">${squad.position}${statsStr ? ' · ' + statsStr : ''}</div>
      </div>
    </div>`;
  }

  // ─────────────────────────────────────────────────────
  //  SCENARIO TEXT (Elo-based until group play begins)
  // ─────────────────────────────────────────────────────
  function _buildScenario(home, away, eloDiff, matchday, standing, fx, isPlayed) {
    if (isPlayed) return null; // No scenario for already-played games

    // If we have standing data, generate table-based scenario
    if (standing && standing.length > 0) {
      return _standingScenario(home, away, standing, matchday);
    }

    // Pre-tournament: Elo-based scenario
    if (eloDiff === null) return null;
    const absElo  = Math.abs(eloDiff);
    const favTeam = eloDiff > 0 ? home : away;
    const undTeam = eloDiff > 0 ? away : home;

    if (matchday > 1) {
      return `⚡ <strong>${favTeam.flag} ${favTeam.name}</strong> als Favorit (Elo +${absElo}) — jeder Punkt im Gruppenrennen wichtig`;
    }
    if (absElo >= 250) {
      return `🏆 <strong>${favTeam.flag} ${favTeam.name}</strong> Topfavorit (Elo +${absElo}) — Pflichtauftakt für die Gruppenführung`;
    } else if (absElo >= 120) {
      return `⚡ <strong>${favTeam.flag} ${favTeam.name}</strong> Favorit (Elo +${absElo}) — <strong>${undTeam.flag} ${undTeam.name}</strong> für Überraschung gut`;
    } else if (absElo >= 40) {
      return `⚖️ Ausgeglichenes Duell — <strong>${favTeam.flag} ${favTeam.name}</strong> leicht vorne (Elo +${absElo})`;
    } else {
      return `🔥 Sehr ausgeglichenes Spiel — Elo-Differenz nur ${absElo} Punkte, alles offen`;
    }
  }

  function _standingScenario(home, away, standing, matchday) {
    const homeRow = standing.find(s => s.id === home.id);
    const awayRow = standing.find(s => s.id === away.id);
    if (!homeRow || !awayRow) return null;

    const homePts  = homeRow.pts  || 0;
    const awayPts  = awayRow.pts  || 0;
    const homePos  = standing.findIndex(s => s.id === home.id) + 1;
    const awayPos  = standing.findIndex(s => s.id === away.id) + 1;

    if (homePos > 3 && awayPos > 3) {
      return `❌ Beide Teams bereits ausgeschieden — Spiel ohne Gruppenrelevanz`;
    }
    if (homePos <= 2 && awayPos <= 2 && matchday === 3) {
      return `🏆 Beide schon qualifiziert — Kampf um <strong>Gruppenführung</strong> und die bessere K.O.-Auslosung`;
    }
    if ((homePos > 3 || awayPos > 3) && matchday === 3) {
      const desperate = homePos > 3 ? home : away;
      const safe      = homePos > 3 ? away : home;
      return `🔥 <strong>${desperate.flag} ${desperate.name}</strong> braucht zwingend einen Sieg — Ausscheiden droht`;
    }
    if (homePos === 1 && awayPos === 2) {
      return `⭐ Spitzenpaarung: <strong>${home.flag} Platz 1</strong> vs <strong>${away.flag} Platz 2</strong> — Kampf um Gruppenführung`;
    }
    return `📊 <strong>${home.flag} ${home.name}</strong> ${homePts} Pkt (${homePos}.) vs <strong>${away.flag} ${away.name}</strong> ${awayPts} Pkt (${awayPos}.)`;
  }

  // ─────────────────────────────────────────────────────
  //  HELPERS
  // ─────────────────────────────────────────────────────
  const _DAYS  = ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa'];
  const _MONTHS = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez'];

  function _fmtDate(iso, time) {
    if (!iso) return '';
    const d   = new Date(iso + 'T12:00:00');
    const day = _DAYS[d.getDay()];
    const mon = _MONTHS[d.getMonth()];
    const tStr = time ? ` · ${time} Uhr` : '';
    return `${day}, ${d.getDate()}. ${mon}${tStr}`;
  }

  function _daysFrom(iso, todayIso) {
    const diff = Math.ceil((new Date(iso) - new Date(todayIso)) / 86400000);
    if (diff === 1) return 'Morgen';
    if (diff <= 7) return `in ${diff} Tagen`;
    return `in ${Math.ceil(diff / 7)} Wo.`;
  }

})();
