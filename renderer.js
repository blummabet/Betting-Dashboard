// ═══════════════════════════════════════════════════════
//  renderer.js — CocoBet Fixture & League Renderer
//  Extracted from season-finish.html (Apr 2026)
//
//  Contains:
//    · scoreClass()               — CSS-Klasse für Score-Badge
//    · cardType()                 — Card-Typ (title/relegation/…)
//    · pillClass()                — CSS-Klasse für Stake-Pill
//    · renderFormDots()           — Form-Punkte als HTML
//    · renderFormSparkline()      — Sparkline-SVG aus Form-String
//    · computeRemainingDifficulty()— Remaining Fixture Difficulty
//    · renderStakeRow()           — Stake-Zeile (Heim/Auswärts)
//    · renderH2H()                — H2H-Sektion HTML
//    · buildPickOfDayHtml()       — Pick-of-the-Day Widget
//    · buildTopCardsHtml()        — Top-Cards Widget
//    · getPressureLabel()         — Pressure-Label Text
//    · getNextFixtures()          — Nächste Fixtures für ein Team
//    · getOpponentQuality()       — Gegner-Qualität (ELO-basiert)
//    · getTacticalBookingSignals()— Taktische Karten-Signale
//    · renderSquadBlock()         — Squad-Block HTML
//    · isDoOrDie()                — Do-or-Die Flag
//    · buildDoOrDieSection()      — Do-or-Die Sektion HTML
//    · renderFixtureCard()        — Haupt-Fixture-Card HTML
//    · renderLeague()             — Liga-View rendern
//    · renderOverview()           — Übersichts-Tab rendern
//    · isWithin7Days()            — Datums-Helfer
//    · weekLabel()                — Wochentag-Label
//    · getDayLabel()              — Tag-Label (Heute/Morgen/…)
//    · buildDayFilterHtml()       — Tag-Filter-Buttons HTML
//    · selectDay()                — Tag auswählen (filtert View)
//    · applyDayFilter()           — Matches auf gewählten Tag filtern
//
//  Runtime dependencies (provided by the page):
//    · LEAGUES                    — injected by update_dashboard.py
//    · window._teamStats          — injected by refresh_stats.py
//    · window._preMatchData       — loaded by prematch-server.js
//    · window._oddsData           — loaded by loadAllOdds()
//    · getBettingPicks()          — from pick-engine.js
//    · computeLineMovement()      — from pick-engine.js
//    · renderLineMovement()       — from pick-engine.js
//    · deriveOdds()               — from pick-engine.js
//    · findOdds()                 — from season-finish.html (main script)
//    · generateScript()           — from season-finish.html (main script)
//    · DOM: document, window
// ═══════════════════════════════════════════════════════


// ═══════════════════════════════════════════════════════
//  RENDER
// ═══════════════════════════════════════════════════════
function scoreClass(s) {
  if (s >= 11) return 'score-hi';
  if (s >= 8.5) return 'score-md';
  return 'score-lo';
}

function cardType(match) {
  const hc = (match.homeStake?.labels||[]).map(l=>l.c);
  const ac = (match.awayStake?.labels||[]).map(l=>l.c);
  const bothRed = hc.includes('red') && ac.includes('red');
  const bothGold = hc.includes('gold') && ac.includes('gold');
  if (bothRed) return 'both-rel';
  if (bothGold) return 'title';
  if ((hc.includes('gold')||ac.includes('gold')) && (hc.includes('red')||ac.includes('red'))) return 'top-vs-rel';
  if (hc.includes('blue') && ac.includes('blue')) return 'ucl-battle';
  if (hc.includes('red') || ac.includes('red')) return 'single-rel';
  return 'european';
}

function pillClass(c) {
  return {red:'sp-red',gold:'sp-gold',blue:'sp-blue',orange:'sp-orange',yellow:'sp-yellow',green:'sp-green'}[c]||'sp-green';
}

function renderFormDots(formStr) {
  if (!formStr) return '';
  const dots = formStr.split('').map(r => {
    const cls = r==='W' ? 'fd-w' : (r==='D' ? 'fd-d' : 'fd-l');
    return `<span class="fd ${cls}" title="${r==='W'?'Sieg':r==='D'?'Unentschieden':'Niederlage'}">${r}</span>`;
  }).join('');
  return `<span class="form-dots">${dots}</span>`;
}

function renderFormSparkline(formStr) {
  if (!formStr || formStr.length < 2) {
    // No form: return placeholder with same dimensions
    return `<div class="sparkline-wrap"><span class="sparkline-label">Keine Daten</span><svg width="96" height="34" viewBox="0 0 96 34" class="form-sparkline"><line x1="4" y1="17" x2="92" y2="17" stroke="#30363d" stroke-width="1.5" stroke-dasharray="4,3"/></svg></div>`;
  }
  const results = formStr.split('').slice(-6);
  const pts = results.map(r => r === 'W' ? 3 : r === 'D' ? 1 : 0);
  const n = pts.length;
  const W = 96, H = 34, padX = 5, padY = 5;
  const xStep = (W - padX * 2) / Math.max(n - 1, 1);

  // Trend: last half vs first half
  const half = Math.max(1, Math.floor(n / 2));
  const firstAvg = pts.slice(0, half).reduce((a,b) => a+b, 0) / half;
  const lastAvg  = pts.slice(-half).reduce((a,b) => a+b, 0) / half;
  const trendCol = lastAvg > firstAvg ? '#3fb950' : lastAvg < firstAvg ? '#f85149' : '#8b949e';
  const trendArrow = lastAvg > firstAvg ? '↑' : lastAvg < firstAvg ? '↓' : '→';

  const coords = pts.map((p, i) => {
    const x = (padX + i * xStep).toFixed(1);
    const y = (padY + (1 - p / 3) * (H - padY * 2)).toFixed(1);
    return `${x},${y}`;
  });
  const lastX = (padX + (n - 1) * xStep).toFixed(1);
  const lastY = (padY + (1 - pts[n - 1] / 3) * (H - padY * 2)).toFixed(1);
  const title = results.map((r,i) => `${r}(${pts[i]}P)`).join(' · ');

  // Area fill under the line
  const firstX = padX.toFixed(1);
  const bottom = (H - padY + 2).toFixed(1);
  const areaPoints = `${firstX},${bottom} ${coords.join(' ')} ${lastX},${bottom}`;

  // Individual result dots along the bottom
  const dotRow = pts.map((p, i) => {
    const x = (padX + i * xStep).toFixed(1);
    const col = p === 3 ? '#3fb950' : p === 1 ? '#8b949e' : '#f85149';
    const lbl = results[i];
    return `<circle cx="${x}" cy="${(H - 3).toFixed(1)}" r="2.2" fill="${col}" opacity=".7" title="${lbl}"/>`;
  }).join('');

  const labelText = `Form ${trendArrow}`;

  return `<div class="sparkline-wrap" title="${title}">
    <span class="sparkline-label">${labelText}</span>
    <svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" class="form-sparkline">
      <polygon points="${areaPoints}" fill="${trendCol}" opacity=".10"/>
      <polyline points="${coords.join(' ')}" fill="none" stroke="${trendCol}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" opacity=".90"/>
      <circle cx="${lastX}" cy="${lastY}" r="3" fill="${trendCol}" opacity=".95"/>
      ${dotRow}
    </svg>
  </div>`;
}

function computeRemainingDifficulty(leagueKey, teamName) {
  const L = LEAGUES[leagueKey];
  if (!L || !L.fixtures || !L.stakeTeams) return null;
  // Score lookup — teams NOT in stakeTeams are not at stake, treat as avg (score 5)
  const scoreMap = {};
  L.stakeTeams.forEach(t => { scoreMap[t.team] = t.score; });
  const remaining = L.fixtures.filter(f => f.home === teamName || f.away === teamName);
  if (remaining.length === 0) return null;
  const oppScores = remaining.map(f => {
    const opp = f.home === teamName ? f.away : f.home;
    return scoreMap[opp] ?? 5;
  });
  const avg = oppScores.reduce((a,b) => a+b, 0) / oppScores.length;
  let label, cls;
  if (avg >= 7.5)      { label = '⬛ Schwer'; cls = 'rest-hard'; }
  else if (avg >= 5.5) { label = '🟡 Mittel';  cls = 'rest-mid';  }
  else                 { label = '🟢 Leicht';  cls = 'rest-easy'; }
  return { avg: avg.toFixed(1), n: remaining.length, label, cls };
}

function renderStakeRow(name, stakeInfo, formData, leagueKey) {
  const sparkline = renderFormSparkline(formData?.form);

  // Table position lookup — prefer stake object, fall back to stakeTeams
  let pos        = stakeInfo?.pos        ?? null;
  let pts        = stakeInfo?.pts        ?? null;
  let gapToLine  = stakeInfo?.gapToLine  ?? null;
  let lineName   = stakeInfo?.lineName   ?? null;
  if ((pos == null || pts == null) && leagueKey && LEAGUES[leagueKey]?.stakeTeams) {
    const st = LEAGUES[leagueKey].stakeTeams.find(t => t.team === name);
    if (st) {
      if (pos      == null) pos      = st.pos;
      if (pts      == null) pts      = st.pts;
      if (gapToLine == null && st.gapToLine != null) { gapToLine = st.gapToLine; lineName = st.lineName; }
    }
  }
  const totalTeams = leagueKey && LEAGUES[leagueKey]?.stakeTeams ? LEAGUES[leagueKey].stakeTeams.length : 18;
  const posClass = pos != null ? (pos <= 3 ? 'pos-top' : pos >= totalTeams - 2 ? 'pos-bot' : '') : '';
  // pos-tag now includes pts: "#18 19Pts"
  const posTag = pos != null
    ? `<span class="pos-tag ${posClass}">#${pos}${pts != null ? ' ' + pts + 'Pts' : ''}</span>`
    : '';

  // ── Gap badge only (pos + pts are already in the posTag) ──────────────────
  let standingsCtxHtml = '';
  if (gapToLine != null && lineName) {
    let gapHtml = '';
    if (gapToLine > 0) {
      gapHtml = `<span class="stctx-gap stctx-ahead">+${gapToLine}P vor ${lineName}</span>`;
    } else if (gapToLine < 0) {
      gapHtml = `<span class="stctx-gap stctx-behind">${Math.abs(gapToLine)}P hinter ${lineName}</span>`;
    } else {
      gapHtml = `<span class="stctx-gap stctx-level">Gleichstand ${lineName}</span>`;
    }
    standingsCtxHtml = `<div class="standings-ctx">${gapHtml}</div>`;
  }

  if (!stakeInfo) {
    return `<div class="team-row">
      <div class="tr-left"><span class="team-name">${name}</span>${posTag}<span class="sp-none">kein direkter Stake</span>${standingsCtxHtml}</div>
      <div class="tr-right">${sparkline}</div>
    </div>`;
  }

  const pills = stakeInfo.labels.length
    ? stakeInfo.labels.map(l=>`<span class="stake-pill ${pillClass(l.c)}">${l.l}</span>`).join('')
    : `<span class="sp-none">gesichert / keine Agenda</span>`;

  return `<div class="team-row">
    <div class="tr-left"><span class="team-name">${name}</span>${posTag}${pills}${standingsCtxHtml}</div>
    <div class="tr-right">${sparkline}</div>
  </div>`;
}

function renderH2H(h2h) {
  if (!h2h || h2h.games < 3) return '';
  const n  = h2h.games;
  const hw = h2h.homeWins, dw = h2h.draws, aw = h2h.awayWins;

  // Result mini-chips (H/X/A)
  const hasApiStats = h2h.over25Rate != null;
  let extHtml = '';
  if (hasApiStats) {
    const o25Pct  = Math.round(h2h.over25Rate * 100);
    const bttsPct = Math.round(h2h.bttsRate   * 100);
    const avgG    = h2h.avgGoals;
    const o25Col  = o25Pct >= 60 ? '#3fb950' : o25Pct >= 40 ? '#e3b341' : '#8b949e';
    const bttsCol = bttsPct >= 60 ? '#3fb950' : bttsPct >= 40 ? '#e3b341' : '#8b949e';

    const chips = (h2h.lastResults || []).map(r => {
      const lbl = r.homeWon ? 'H' : r.awayWon ? 'A' : 'X';
      const col = r.homeWon ? '#3fb950' : r.awayWon ? '#f85149' : '#8b949e';
      const tip = `${r.homeGoals}:${r.awayGoals} (${r.year})`;
      return `<span title="${tip}" style="display:inline-flex;align-items:center;justify-content:center;
        width:16px;height:16px;border-radius:3px;font-size:9px;font-weight:800;
        background:${col}22;color:${col};border:1px solid ${col}55">${lbl}</span>`;
    }).join('');

    extHtml = `
      <span class="h2h-div">·</span>
      <span class="h2h-stat">Ø <strong>${avgG}</strong> Tore</span>
      <span class="h2h-div">·</span>
      <span class="h2h-stat">+2.5: <strong style="color:${o25Col}">${o25Pct}%</strong></span>
      <span class="h2h-div">·</span>
      <span class="h2h-stat">BTTS: <strong style="color:${bttsCol}">${bttsPct}%</strong></span>
      ${chips ? `<span class="h2h-div">·</span><span style="display:flex;gap:2px;align-items:center">${chips}</span>` : ''}
    `;
  }

  // Win-rate mini-bar (compact, 54px total)
  const hwP = hw/n, dwP = dw/n, awP = aw/n;
  const BAR = 54;
  const hwW = Math.max(3, Math.round(hwP*BAR));
  const dwW = Math.max(3, Math.round(dwP*BAR));
  const awW = Math.max(3, Math.round(awP*BAR));

  return `<div class="h2h-strip">
    <span class="h2h-label">H2H</span>
    <span class="h2h-record">
      <strong style="color:#3fb950">${hw}</strong>H
      <strong style="color:#8b949e">${dw}</strong>X
      <strong style="color:#f85149">${aw}</strong>A
    </span>
    <div class="h2h-bar" title="${hw} Heim · ${dw} Unentschieden · ${aw} Auswärts">
      <div class="h2h-seg h2h-home" style="width:${hwW}px"></div>
      <div class="h2h-seg h2h-draw" style="width:${dwW}px"></div>
      <div class="h2h-seg h2h-away" style="width:${awW}px"></div>
    </div>
    <span class="h2h-ngames">${n} Sp.</span>
    ${extHtml}
  </div>`;
}

// ═══════════════════════════════════════════════════════
//  PICK OF THE DAY BUILDER
//  Finds the single strongest pick across all matches.
//  Ranked by: hot(3)>value(2)>inj-edge(1)>plain(0), then match score.
// ═══════════════════════════════════════════════════════
function buildPickOfDayHtml(matchList) {
  const candidates = [];
  for (const m of matchList) {
    const sc = computeMatchScore(m, m.leagueKey);
    if (sc < 7) continue;
    const odds = m.leagueKey ? findOdds(m.leagueKey, m.home, m.away) : null;
    const picks = getBettingPicks(m, odds, m.leagueKey);
    for (const p of picks) {
      if (p.conf === 'high' || p.conf === 'medium') candidates.push({p, sc, m});
    }
  }
  if (candidates.length === 0) return '';

  candidates.sort((a, b) => {
    const vScore = x => x === 'hot' ? 3 : x === 'value' ? 2 : x === 'inj-edge' ? 1 : 0;
    const av = vScore(a.p.value) * 10 + a.sc;
    const bv = vScore(b.p.value) * 10 + b.sc;
    return bv - av;
  });

  const {p, sc, m} = candidates[0];
  const flag  = m.leagueFlag || '';
  const date  = m.date || '';
  const time  = m.time  ? ` · ${m.time}` : '';
  const _potdInjTeam = (() => {
    const hi = m.homeForm?.injuries?.impactScore || 0;
    const ai = m.awayForm?.injuries?.impactScore || 0;
    if (hi >= 2.0 && ai >= 2.0) return '';
    if (hi >= 2.0) return ` · ${m.home.split(' ').slice(-1)[0]}`;
    if (ai >= 2.0) return ` · ${m.away.split(' ').slice(-1)[0]}`;
    return '';
  })();
  const vTag  = p.value === 'hot'       ? '<span class="value-tag hot">🔥 VALUE</span>'
              : p.value === 'value'     ? '<span class="value-tag val">💰 Value</span>'
              : p.value === 'inj-edge'  ? `<span class="value-tag inj">🏥 Inj. Edge${_potdInjTeam}</span>` : '';
  const oddsStr = p.odds ? `@ ${p.odds.toFixed(2)}` : '';
  const confStr = p.conf === 'high' ? '★★★' : '★★☆';

  // Fair value display
  let fvStr = '';
  if (p.modelOdds && p.odds) {
    const edgePp = Math.round((1/p.modelOdds - (1/p.odds)*1.03) * 100);
    const edgeTxt = edgePp > 0 ? `+${edgePp}pp Edge` : edgePp === 0 ? '≈ Fair' : `${edgePp}pp`;
    fvStr = `<span class="potd-fv">FV ${p.modelOdds} → Bookie ${p.odds.toFixed(2)} <span style="color:${edgePp>=10?'#3fb950':edgePp>=5?'#e3b341':'#8b949e'}">${edgeTxt}</span></span>`;
  } else if (p.modelOdds) {
    fvStr = `<span class="potd-fv">FV ${p.modelOdds} (Modell-Näherung)</span>`;
  }

  // Safer alt line
  let altStr = '';
  if (p.saferAlt) {
    altStr = `<div class="potd-alt safer"><span class="safer-label">✓ Main Pick</span> <span class="safer-market">${p.saferAlt.market}</span> <span class="safer-odds">@ ~${p.saferAlt.estOdds.toFixed(2)}</span> <span style="opacity:.5;font-size:10px">(est.)</span></div>`;
  } else if (p.boldAlt) {
    altStr = `<div class="potd-alt bold">📈 <strong>Mehr Value:</strong> ${p.boldAlt.market} @ ~${p.boldAlt.estOdds.toFixed(2)} <span style="opacity:.6;font-size:10px">(Modell-Näherung)</span></div>`;
  }

  // Short reason (first sentence only)
  const shortReason = (p.reason || '').replace(/<[^>]+>/g,'').split('·')[0].split('📊')[0].trim();

  return `<div class="potd-section">
    <div class="potd-label">⭐ PICK OF THE DAY</div>
    <div class="potd-matchline">${flag} ${m.home} <span class="potd-vs">vs</span> ${m.away} <span class="potd-meta">${date}${time} · Score ${sc}/12</span></div>
    <div class="potd-pick-line">
      <span class="potd-icon">${p.icon}</span>
      <span class="potd-market">${p.market}</span>
      <span class="potd-odds">${oddsStr}</span>
      ${vTag}
      <span class="potd-conf">${confStr}</span>
    </div>
    ${fvStr}
    ${altStr}
    <div class="potd-reason">${shortReason}</div>
  </div>`;
}

// ═══════════════════════════════════════════════════════
//  CARDS DES TAGES
//  Top 7 matches for the day, each with their single best pick.
//  Selection: real bookie odds + pick model score + conf level.
//  One card per match, sorted by composite rank score.
// ═══════════════════════════════════════════════════════
// ── Match expiry helper ───────────────────────────────────────────────────────
// Returns true when a match is definitively over: kickoff time + 100 minutes.
// 100 min covers 90 min play + typical stoppage/extra time.
// If no time is set, only the date is checked (never hidden on the same day).
function isMatchOver(dateStr, timeStr) {
  if (!dateStr) return false;
  const [d, mo, y] = dateStr.split('.');
  if (!timeStr) return false;          // no kickoff time → never auto-hide
  const [h, min] = timeStr.split(':');
  const kickoff = new Date(+y, +mo - 1, +d, +h, +min, 0);
  const cutoff  = new Date(kickoff.getTime() + 100 * 60 * 1000);
  return Date.now() > cutoff.getTime();
}

// TAGES-PICKS ÜBERSICHT — alle wettierbaren Picks des Tages
// Zeigt ALLE BET + ABWÄGEN Picks (kein SKIP, kein Low-Conf).
// Keine künstliche Begrenzung auf 7 Picks — alles was sich lohnt, kommt rein.
// 📨 markiert Telegram-Picks (BET + conf=high + echte Odds + Edge ≥ 4pp).
// ═══════════════════════════════════════════════════════
function buildTopCardsHtml(matchList) {
  // Edge in Prozentpunkten (wie telegram_bot.py: 1/modelOdds - 1/odds)
  const _edgePp = (modelOdds, odds) => {
    if (!modelOdds || !odds || modelOdds <= 0 || odds <= 0) return 0;
    return Math.round((1 / modelOdds - 1 / odds) * 100 * 10) / 10;
  };
  const _TG_MIN_EDGE = 4.0;

  const bets      = [];  // verdict = BET
  const considers = [];  // verdict = ABWÄGEN

  for (const m of matchList) {
    if (isMatchOver(m.date, m.time)) continue;

    const odds = m.leagueKey ? findOdds(m.leagueKey, m.home, m.away) : null;
    const picks = getBettingPicks(m, odds, m.leagueKey)
      .filter(p => p.conf === 'high' || p.conf === 'medium');
    if (!picks.length) continue;

    // Fixture snapshot for oddsOpen and h2h (fed into computeVerdict)
    const _fix = m.leagueKey
      ? (LEAGUES[m.leagueKey]?.fixtures || []).find(f => f.home === m.home && f.away === m.away)
      : null;
    const _oddsOpen = _fix?.odds_open || null;
    const _h2h      = m.h2h || null;

    // _noRealOdds guard: same logic as renderFixtureCard
    const _noRealOdds = !odds || odds._isEstimated;

    for (const p of picks) {
      const oddsNum = (typeof p.odds === 'number') ? p.odds : null;
      const _vd = computeVerdict({
        modelOdds: p.modelOdds,
        odds:      (_noRealOdds && p.oddsIsEst) ? null : oddsNum,
        oddsIsEst: p.oddsIsEst,
        market:    p.market,
        oddsOpen:  _oddsOpen,
        h2h:       _h2h,
      });
      if (_vd.verdict === 'SKIP') continue;

      const ep      = _edgePp(p.modelOdds, oddsNum);
      // TG criteria (mirrors telegram_bot.py best_pick logic):
      //   Primary:   conf=high + real odds + edge ≥ 4pp
      //   Exception: conf=medium + real odds + edge ≥ 12pp (exceptional value plays)
      const _tgHighConf   = p.conf === 'high'   && ep >= _TG_MIN_EDGE;
      const _tgMediumConf = p.conf === 'medium' && ep >= 12.0;
      const isTg    = _vd.verdict === 'BET'
                   && !p.oddsIsEst
                   && oddsNum != null
                   && (_tgHighConf || _tgMediumConf);

      const entry = { p, m, vd: _vd, ep, isTg };

      if (_vd.verdict === 'BET') bets.push(entry);
      else                       considers.push(entry);
    }
  }

  // Sort BET by edge desc (best value first), ABWÄGEN by pick-score desc
  bets.sort((a, b) => b.ep - a.ep);
  considers.sort((a, b) => (b.p.sc || 0) - (a.p.sc || 0));

  const allPicks = [...bets, ...considers];
  if (!allPicks.length) return '';

  // ── 📨 TG badge: only the ONE pick per match Telegram actually sends ─────
  // Mirrors telegram_bot.py best_pick(): highest edge among conf=high, real odds, ep≥4pp.
  // Multiple picks from same match may qualify, but Telegram sends exactly one.
  // Without this guard, two picks from the same match could both show 📨 — misleading.
  const _tgBestPerMatch = new Map();
  for (const entry of bets) {
    if (!entry.isTg) continue;
    const mk = `${entry.m.home}|${entry.m.away}`;
    const prev = _tgBestPerMatch.get(mk);
    if (!prev || entry.ep > prev.ep) _tgBestPerMatch.set(mk, entry);
  }
  // Clear isTg on all entries, then re-set only on the winner per match
  for (const entry of bets) entry.isTg = false;
  for (const entry of _tgBestPerMatch.values()) entry.isTg = true;

  // ── Expose BET + high-conf picks globally so renderFixtureCard can mark ⭐ ──
  window._topPickSet = new Set(
    bets.filter(e => e.p.conf === 'high').map(e => `${e.m.home}|${e.m.away}|${e.p.market}`)
  );

  // ── Helpers ───────────────────────────────────────────────────────────────
  const confStr   = c => c === 'high' ? '★★★' : '★★☆';
  const oddsClass = (p) => {
    if (!p.odds || p.oddsIsEst) return 'tc-odds-est';
    return (p.odds >= 1.40 && p.odds <= 1.95) ? 'tc-odds-sweet' : 'tc-odds-ok';
  };
  const _sqCircle = (stake) => {
    const sq = stake?.squadStrength ?? null;
    if (sq == null) return '';
    const cls = sq >= 8.5 ? 'sqc-full' : sq >= 7.0 ? 'sqc-ok' : 'sqc-low';
    return `<span class="sqc ${cls}" title="Squad-Stärke: ${sq}/10">${Math.round(sq)}</span>`;
  };

  const renderRow = ({ p, m, vd, ep, isTg }) => {
    const time      = m.time ? ` · ${m.time}` : '';
    const oddsLbl   = p.odds
      ? `<span class="tc-odds-pill ${oddsClass(p)}">@ ${p.odds.toFixed(2)}${p.oddsIsEst ? ' ~est' : ''}</span>`
      : '';
    const vTag      = p.value === 'hot'      ? '<span class="value-tag hot" style="font-size:10px">🔥 VALUE</span>'
                    : p.value === 'value'    ? '<span class="value-tag val" style="font-size:10px">💰 Value</span>'
                    : p.value === 'inj-edge' ? '<span class="value-tag inj" style="font-size:10px">🏥 Edge</span>' : '';
    const tgBadge   = isTg ? '<span class="tc-tg-badge">📨 TG</span>' : '';
    const epLabel   = ep > 0 ? `<span class="tc-ep-pill">+${ep.toFixed(1)}pp</span>` : '';
    // Verdict badge — reuse colours from computeVerdict
    const vBadge    = `<span class="pick-verdict-mini" style="background:${vd.vBg};color:${vd.vColor};border:1px solid ${vd.vBorder};border-radius:4px;padding:1px 6px;font-size:10px;font-weight:700">${vd.verdict}</span>`;
    // Short reason (strip HTML, first ~100 chars)
    const _rawReason = (p.reason || '').replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim();
    const _short     = _rawReason.length > 100 ? _rawReason.slice(0, 97) + '…' : _rawReason;
    const _hCircle   = _sqCircle(m.homeStake);
    const _aCircle   = _sqCircle(m.awayStake);

    return `<div class="topcards-row">
      <div class="tc-top">
        <div class="tc-matchline">${m.leagueFlag || ''} ${m.home}${_hCircle} vs ${m.away}${_aCircle} · ${m.date}${time}</div>
        ${vBadge}${tgBadge}
      </div>
      <div class="tc-pick-row">
        <span class="tc-icon">${p.icon}</span>
        <span class="tc-market">${p.market}</span>
        ${oddsLbl}${epLabel}${vTag}
        <span class="tc-conf">${confStr(p.conf)}</span>
      </div>
      ${_short ? `<div class="tc-reason">${_short}</div>` : ''}
    </div>`;
  };

  const tgCount   = bets.filter(e => e.isTg).length;
  const betCount  = bets.length;
  const abwCount  = considers.length;

  // ── Persist to localStorage for Results tracking ──────────────────────────
  try {
    const _tcHistory = JSON.parse(localStorage.getItem('tc_history') || '[]');
    const _todayDate = allPicks[0]?.m?.date || '';
    const _newEntries = allPicks.map(({ p, m, vd }) => ({
      date: m.date || '',
      dateIso: m.dateIso || '',
      home: m.home,
      away: m.away,
      market: p.market,
      odds: p.odds || null,
      conf: p.conf,
      verdict: vd.verdict,
    }));
    const _kept   = _todayDate ? _tcHistory.filter(e => e.date !== _todayDate) : _tcHistory;
    const _pruned = _kept.slice(-2700); // ~30 picks × 90 days
    localStorage.setItem('tc_history', JSON.stringify([..._pruned, ..._newEntries]));
  } catch(_e) { /* localStorage unavailable */ }

  // ── Render two sections ───────────────────────────────────────────────────
  const betSection = bets.length ? `
    <div class="tc-section-header tc-bet-header">🟢 BET (${betCount})</div>
    <div class="topcards-grid">${bets.map(renderRow).join('')}</div>` : '';

  const abwSection = considers.length ? `
    <div class="tc-section-header tc-abw-header">🟡 ABWÄGEN (${abwCount})</div>
    <div class="topcards-grid">${considers.map(renderRow).join('')}</div>` : '';

  return `<div class="topcards-section">
    <div class="topcards-header">
      <span>📋 Tages-Picks · ${betCount} BET · ${abwCount} ABWÄGEN</span>
      <span class="topcards-header-right">${tgCount > 0 ? `${tgCount}× 📨 TG` : 'Kein TG heute'}</span>
    </div>
    ${betSection}${abwSection}
  </div>`;
}

// Returns a short "why under pressure" label for a team.
// stakeObj is the full stake object: {score, labels:[{l, c}]} or null.
function getPressureLabel(stakeObj, teamName) {
  if (!stakeObj || !stakeObj.labels || !stakeObj.labels.length) return '';
  const colors = stakeObj.labels.map(l => l.c);
  const motiv  = stakeObj.motivationLevel || 'full';
  // Teams with confirmed/secured season outcome — show as demotivated, not as fighters
  if (motiv === 'none') {
    if (colors.includes('red'))    return `<span style="opacity:.65">⬜ ${teamName} bereits abgestiegen (keine Motivation)</span>`;
    if (colors.includes('gold'))   return `<span style="opacity:.65">⬜ ${teamName} bereits Meister (Rotation möglich)</span>`;
    if (colors.includes('blue'))   return `<span style="opacity:.65">⬜ ${teamName} UCL bereits gesichert</span>`;
    if (colors.includes('orange')) return `<span style="opacity:.65">⬜ ${teamName} EL bereits gesichert</span>`;
    return `<span style="opacity:.65">⬜ ${teamName} Saison-Ziel gesichert</span>`;
  }
  if (motiv === 'low') {
    if (colors.includes('red'))    return `${teamName} kämpft gegen den Abstieg (nahezu bestätigt)`;
    if (colors.includes('gold'))   return `${teamName} kämpft um den Titel (nahezu gesichert)`;
  }
  // Standard pressure labels — team is still actively fighting
  if (colors.includes('red'))    return `${teamName} kämpft gegen den Abstieg`;
  if (colors.includes('gold'))   return `${teamName} kämpft um den Titel`;
  if (colors.includes('blue'))   return `${teamName} kämpft um die Champions League`;
  if (colors.includes('orange')) return `${teamName} kämpft um die Europa League`;
  if (colors.includes('yellow')) return `${teamName} kämpft um Europa`;
  if (colors.includes('purple')) return `${teamName} kämpft um die Conference League`;
  return '';
}

// ═══════════════════════════════════════════════════════════════════
//  TACTICAL BOOKING HELPERS
// ═══════════════════════════════════════════════════════════════════

// Returns next N upcoming fixtures for a team from the league's fixture list
function getNextFixtures(teamName, afterDate, allFixtures, n = 2) {
  const d0 = parseGermanDate(afterDate);
  return allFixtures
    .filter(f => (f.home === teamName || f.away === teamName)
              && parseGermanDate(f.date) > d0)
    .sort((a, b) => parseGermanDate(a.date) - parseGermanDate(b.date))
    .slice(0, n);
}

// Opponent quality score for a fixture, from the perspective of teamName.
// Higher = more important / harder opponent → less likely to "waste" a suspension here.
function getOpponentQuality(fixture, teamName) {
  if (!fixture) return 5;
  const isHome   = fixture.home === teamName;
  const oppStake = isHome ? fixture.awayStake : fixture.homeStake;
  if (!oppStake) return 5;
  const colors = (oppStake.labels || []).map(l => l.c);
  let q = (oppStake.score || 5);
  if (colors.includes('gold'))   q += 3.0;   // title contender — big game
  if (colors.includes('blue'))   q += 2.0;   // UCL chaser
  if (colors.includes('orange')) q += 1.0;   // EL chaser
  if (colors.includes('red'))    q += 1.5;   // relegation battle — intense game
  if (oppStake.mustWin)          q += 2.0;   // must-win for opponent → extra pressure
  if ((oppStake.pressureRatio || 0) > 0) q += oppStake.pressureRatio * 1.5;
  return Math.round(q * 10) / 10;
}

// Analyses a team's bookings for tactical booking risk.
// Returns array of {player, yellows, threshold, signal} or []
function getTacticalBookingSignals(bookingsSide, teamName, matchDate, allFixtures) {
  if (!bookingsSide?.length) return [];
  const signals = [];
  const next2 = getNextFixtures(teamName, matchDate, allFixtures, 2);
  const nextFx    = next2[0] || null;   // game they'd MISS if booked now
  const overNextFx = next2[1] || null;  // game they'd RETURN for

  const q1 = nextFx     ? getOpponentQuality(nextFx, teamName)     : null;
  const q2 = overNextFx ? getOpponentQuality(overNextFx, teamName) : null;

  // Tactical booking makes sense when:
  //   suspension game (q1) is against a weaker opponent than the return game (q2)
  const isTactical = q1 !== null && q2 !== null && q2 > q1 + 1.0;
  // Suspension is "worth it" — miss a easier game, come back fresh for the harder one
  const isTacticalStrong = q1 !== null && q2 !== null && q2 > q1 + 2.5;

  for (const p of bookingsSide) {
    if (!p.oneAway) continue;  // only players ONE yellow away from ban
    const lastName = (p.name || '').split(' ').slice(-1)[0];
    const posLabel = p.position === 'G' ? 'TW'
                   : p.position === 'D' ? 'Abwehr'
                   : p.position === 'F' ? 'Sturm'
                   : p.position === 'M' ? 'Mittelfeld' : '';
    const posStr = posLabel ? ` (${posLabel})` : '';
    signals.push({
      name:      p.name,
      lastName,
      yellows:   p.yellows,
      threshold: p.threshold,
      posStr,
      isTactical,
      isTacticalStrong,
      nextOpponent:     nextFx
        ? (nextFx.home === teamName ? nextFx.away : nextFx.home)
        : null,
      overNextOpponent: overNextFx
        ? (overNextFx.home === teamName ? overNextFx.away : overNextFx.home)
        : null,
      q1, q2,
    });
  }
  return signals;
}

function renderSquadBlock(match) {
  const hSt = match.homeStake;
  const aSt = match.awayStake;

  // Read squad data from top-level homeSquad/awaySquad (all teams) with
  // fallback to homeStake/awayStake (legacy path for cached data)
  const hSq   = match.homeSquad?.squadStrength ?? hSt?.squadStrength ?? null;
  const aSq   = match.awaySquad?.squadStrength ?? aSt?.squadStrength ?? null;
  const hMiss = match.homeSquad?.missingStarters ?? hSt?.missingStarters;
  const aMiss = match.awaySquad?.missingStarters ?? aSt?.missingStarters;

  // Fallback: if squad cache has no missingStarters, use confirmed missing from form injury data.
  // This prevents "Vollbesetzt" when the cache is stale but injury API has current data.
  const _hFormInj = (match.homeForm?.injuries?._raw || [])
    .filter(p => p.type === 'Missing Fixture')
    .map(p => ({ name: p.player, pos: (p.position || [''])[0] }));
  const _aFormInj = (match.awayForm?.injuries?._raw || [])
    .filter(p => p.type === 'Missing Fixture')
    .map(p => ({ name: p.player, pos: (p.position || [''])[0] }));
  const hMissEff = (hMiss?.length) ? hMiss : _hFormInj;
  const aMissEff = (aMiss?.length) ? aMiss : _aFormInj;

  const hHasMiss = (hMissEff || []).some(p => p && p.name);
  const aHasMiss = (aMissEff || []).some(p => p && p.name);
  // Skip block only when there is literally nothing to show for either team
  if (hSq == null && aSq == null && !hHasMiss && !aHasMiss) return '';

  // injuryDataFetched: did we actually receive injury data from the API?
  // false = no data → show "Keine Daten" instead of misleading "Vollbesetzt"
  const hInjFetched = match.homeSquad?.injuryDataFetched ?? (hSt != null);
  const aInjFetched = match.awaySquad?.injuryDataFetched ?? (aSt != null);

  const POS = {F:'ST', M:'MF', D:'VER', G:'TW'};
  const barColor  = s => s >= 8.5 ? '#3fb950' : s >= 7.0 ? '#e3b341' : '#f85149';
  const scoreIcon = s => s >= 8.5 ? '⚡' : s >= 7.0 ? '⚠️' : '🏥';
  const scoreCls  = s => s >= 8.5 ? 'sqstr-full' : s >= 7.0 ? 'sqstr-ok' : 'sqstr-low';

  const renderTeam = (name, sq, missing, injFetched) => {
    const missingList = (missing || []).filter(p => p && p.name);
    // Skip only when there is truly nothing to show: no score AND no injury data
    if (sq == null && !missingList.length && !injFetched) return '';
    const pct = sq != null ? Math.round(sq / 10 * 100) : 0;
    const missingHtml = missingList.length
      ? `<div class="squad-missing">↳ ${
          missingList.map(p => {
            const posStr = POS[p.pos] || p.pos || '';
            const eta    = p.eta ? ` · ${p.eta}` : '';
            return `${p.name}${posStr ? ` (${posStr}${eta})` : eta ? ` (${eta})` : ''}`;
          }).join(', ')
        } fehlt${missingList.length > 1 ? 'en' : ''}</div>`
      : injFetched
        ? `<div class="squad-missing" style="color:var(--muted);opacity:.6">Vollbesetzt</div>`
        : `<div class="squad-missing" style="color:var(--muted);opacity:.45;font-style:italic">Keine Ausfalls-Daten</div>`;

    // Strength bar: only when sq is known (team in squad_cache) AND injury data was fetched.
    // When sq == null (team not yet in cache), show missing players but no bar.
    const metaHtml = (sq != null && injFetched)
      ? `<div class="squad-bar-wrap"><div class="squad-bar-fill" style="width:${pct}%;background:${barColor(sq)}"></div></div>
         <span class="squad-score ${scoreCls(sq)}">${scoreIcon(sq)} ${sq.toFixed(1)}/10</span>`
      : sq != null
        ? `<span class="squad-score" style="color:var(--muted);opacity:.5">–/10</span>`
        : `<span class="squad-score" style="color:var(--muted);opacity:.45;font-size:10px;font-style:italic">kein Cache</span>`;

    const shortName = name.split(' ').slice(-1)[0];
    return `<div class="squad-row">
      <div class="squad-meta">
        <span class="squad-name" title="${name}">${shortName}</span>
        ${metaHtml}
      </div>
      ${missingHtml}
    </div>`;
  };

  const hHtml = renderTeam(match.home, hSq, hMissEff, hInjFetched);
  const aHtml = renderTeam(match.away, aSq, aMissEff, aInjFetched);
  if (!hHtml && !aHtml) return '';

  // Divider between teams only when both shown
  const divider = (hHtml && aHtml) ? '<div class="squad-divider"></div>' : '';

  return `<div class="squad-block">
    <div class="squad-label">🧬 Squad-Status</div>
    ${hHtml}${divider}${aHtml}
  </div>`;
}

// ── Do-or-Die detection ───────────────────────────────────────────────────────
// Returns null or { isGold, teams:[{name,label}], rl } when ≥1 team has no room for error.
// Criteria: mustWin=true AND rl ≤ 4 AND red/gold label AND motivationLevel !== 'none'
function isDoOrDie(match) {
  const rl = match.roundsLeft ?? match._roundsLeft ?? 99;
  if (rl > 4) return null;
  const hs = match.homeStake || null;
  const as = match.awayStake || null;
  const _check = (stake, name) => {
    if (!stake || stake.motivationLevel === 'none') return null;
    if (!stake.mustWin) return null;
    const cols = (stake.labels || []).map(l => l.c || '');
    const isRel    = cols.includes('red');
    const isGold   = cols.includes('gold');
    const isBlue   = cols.includes('blue');    // UCL qualification fight
    const isOrange = cols.includes('orange');  // Europa League fight
    const isYellow = cols.includes('yellow');  // Relegation playoff
    if (!isRel && !isGold && !isBlue && !isOrange && !isYellow) return null;
    const label = isRel
      ? (rl <= 2 ? 'Abstieg steht vor der Tür' : 'Abstiegskampf — Punkte oder Absturz')
      : isGold
        ? (rl <= 2 ? 'Titelchance jetzt oder nie' : 'Titelkampf — Vorsprung sichern')
        : isBlue
          ? (rl <= 2 ? 'UCL-Ticket jetzt oder nie' : 'UCL-Kampf — kein Ausrutschen')
          : isOrange
            ? (rl <= 2 ? 'Europa League jetzt oder nie' : 'EL-Kampf — Punkte sind Pflicht')
            : (rl <= 2 ? 'Playoff droht — alles auf dem Spiel' : 'Rel.-Playoff — Punkte jetzt holen');
    return { name, isGold, label };
  };
  const hDod = _check(hs, match.home);
  const aDod = _check(as, match.away);
  if (!hDod && !aDod) return null;
  const teams = [hDod, aDod].filter(Boolean);
  const isGold = teams.every(t => t.isGold); // pure gold only if both/all are title
  return { isGold, teams, rl };
}

// ── Do-or-Die section for Best-of-All tab ────────────────────────────────────
function buildDoOrDieSection(matchList) {
  // Only show games in the next 3 days
  const _today = new Date(); _today.setHours(0,0,0,0);
  const _cutoff = new Date(_today); _cutoff.setDate(_cutoff.getDate() + 3);
  const next3 = matchList.filter(m => {
    const d = parseGermanDate(m.date);
    return d >= _today && d <= _cutoff;
  });

  // Sort: fewest roundsLeft first, then earliest date (nearest game first)
  const raw = next3
    .map(m => ({ m, dod: isDoOrDie(m) }))
    .filter(x => x.dod !== null)
    .sort((a, b) => {
      if (a.dod.rl !== b.dod.rl) return a.dod.rl - b.dod.rl;
      return parseGermanDate(a.m.date) - parseGermanDate(b.m.date);
    });

  // Deduplicate: each team appears at most once (their nearest/most urgent game)
  const seenTeams = new Set();
  const candidates = [];
  for (const entry of raw) {
    const dodTeamNames = entry.dod.teams.map(t => t.name);
    if (dodTeamNames.some(n => seenTeams.has(n))) continue; // team already shown
    candidates.push(entry);
    dodTeamNames.forEach(n => seenTeams.add(n));
  }

  if (!candidates.length) return '';

  const cards = candidates.map(({ m, dod }) => {
    const leagueStr = `${m.leagueFlag || ''} ${m.leagueName || ''}`.trim();
    const heroClass = dod.isGold ? 'gold' : '';
    const teamHtml  = dod.teams.map(t =>
      `<span class="dod-hero">${t.name}</span>`
    ).join(' & ');
    // build vs line: hero teams in colour, other team normal
    const heroNames = new Set(dod.teams.map(t => t.name));
    const hSpan = heroNames.has(m.home)
      ? `<span class="dod-hero">${m.home}</span>` : m.home;
    const aSpan = heroNames.has(m.away)
      ? `<span class="dod-hero">${m.away}</span>` : m.away;
    const stakes = dod.teams.map(t => t.label).join(' · ');
    const rlLabel = dod.rl <= 1 ? 'LETZTES SPIEL' : `${dod.rl} SPIELE NOCH`;
    return `<div class="dod-mini-card ${heroClass}" onclick="
      document.querySelectorAll('.league-btn').forEach(b=>b.classList.remove('active'));
      const lbtn=document.querySelector('[data-league=\\'${m.leagueKey}\\']');
      if(lbtn){lbtn.classList.add('active');renderLeague('${m.leagueKey}');}
    ">
      <div class="dod-mc-league">${leagueStr}</div>
      <div class="dod-mc-teams ${heroClass}">${hSpan} <span style="opacity:.5">vs</span> ${aSpan}</div>
      <div class="dod-mc-stake">${stakes}</div>
      <div class="dod-mc-meta">
        <span class="dod-mc-date">${m.date || ''}</span>
        <span class="dod-mc-rl">${rlLabel}</span>
      </div>
    </div>`;
  }).join('');

  return `<div class="dod-section">
    <div class="dod-section-header">
      <span>🚨</span><span>Jetzt oder Nie — Letzte-Chance Spiele</span>
      <span style="font-size:10px;font-weight:500;color:var(--muted);text-transform:none;letter-spacing:0">${candidates.length} Spiele</span>
    </div>
    <div class="dod-mini-grid">${cards}</div>
  </div>`;
}

function renderFixtureCard(match, leagueName, leagueFlag, leagueKey) {
  // Enrich match fields from prematch-data.json when not already set
  const _pm = window._preMatchData?.[`${match.home}|${match.away}`];
  if (!match.time && _pm?.time) match.time = _pm.time;
  // Referee stats live in prematch-data.json → copy to match object so
  // getBettingPicks() can read match.refereeStats (was always null before)
  if (!match.refereeStats && _pm?.refereeStats) match.refereeStats = _pm.refereeStats;

  const angle = getBettingAngle(match);
  const ct = cardType(match);
  // Use precision computed score, fall back to hardcoded while odds load
  const sc = computeMatchScore(match, leagueKey);
  const odds  = leagueKey ? findOdds(leagueKey, match.home, match.away) : null;
  const oddsD = deriveOdds(odds || {});
  const picks = getBettingPicks(match, oddsD, leagueKey);

  // ── Line movement strip ────────────────────────────────────────────────────
  const _oddsOpen = _pm?.odds_open || null;
  const _lmRows   = computeLineMovement(_oddsOpen, odds);
  const lineMovementHtml = renderLineMovement(_lmRows, picks, oddsD, odds?._isEstimated);

  // Show all high/medium confidence picks — user decides what's worth betting.
  // Low-odds picks get ⚠ label instead of being hidden.
  // Also apply the same negative-edge safety cut here (belt-and-suspenders),
  // so _v2PickBuffer and Polymarket never see picks the card actually suppresses.
  const visiblePicks = picks.filter(p => {
    if (p.conf !== 'high' && p.conf !== 'medium') return false;
    // Same -5pp edge threshold as the picksHtml map's `return ''` guard below
    if (p.modelOdds != null && p.odds != null) {
      const _ep = Math.round(((1 / p.modelOdds) - (1 / p.odds) * 1.03) * 100);
      if (_ep < -5) return false;
    }
    return true;
  });

  // ── No valid picks → suppress card entirely ───────────────────────────────
  // Negative-edge picks are already removed inside getBettingPicks().
  // If nothing survives, there's no value here — don't render a card at all.
  if (visiblePicks.length === 0) return '';

  // ── Buffer picks for V2 Tracking (avoids recomputing with missing match data) ─
  // savePicksV2() reads from this buffer instead of re-running getBettingPicks().
  if (!window._v2PickBuffer) window._v2PickBuffer = {};
  const _bufKey = `${match.date||''}|${leagueKey||''}|${match.home}|${match.away}`;
  window._v2PickBuffer[_bufKey] = {
    date: match.date, leagueKey, leagueName, leagueFlag,
    home: match.home, away: match.away, matchScore: sc,
    picks: visiblePicks,
  };
  const picksHtml = visiblePicks.map(p => {
    const oddsNum  = p.odds ?? null;

    // Note: negative-edge picks (-5pp) are already removed from visiblePicks above
    // (the filter block before the buffer assignment). Nothing reaches here with edge < -5pp.

    // When the whole fixture has no real market odds (_isEstimated), suppress
    // all pick-level estimated quotes too — they're model output, not bookmaker prices.
    const _noRealOdds = !!(odds?._isEstimated);
    const oddsTag  = (oddsNum != null && !(_noRealOdds && p.oddsIsEst))
      ? p.oddsIsEst
        ? `<span class="pick-odds-tag" style="opacity:.85">@ ~${oddsNum.toFixed(2)}<span style="font-size:9px;opacity:.6;margin-left:2px">(est.)</span></span>`
        : `<span class="pick-odds-tag" style="${oddsNum < 1.40 ? 'opacity:.6' : ''}">@ ${oddsNum.toFixed(2)}</span>`
      : _noRealOdds
        ? `<span style="font-size:10px;color:#8b949e;margin-left:4px;padding:1px 5px;border:1px solid #30363d;border-radius:4px" title="Für diese Liga gibt es keinen Bookie-Feed — Fair Value ist Modellschätzung">kein Bookie-Feed</span>`
        : `<span style="font-size:10px;color:var(--muted);margin-left:4px;font-style:italic">keine Quote</span>`;
    const lowWarn  = oddsNum != null && !p.oddsIsEst && oddsNum < 1.40
      ? `<span style="font-size:11px;color:#e3b341;margin-left:4px;font-weight:600" title="Quote unter 1.40 — wenig Wert">⚠ niedrig</span>` : '';
    const _injEdgeTeam = (() => {
      const hi = match.homeForm?.injuries?.impactScore || 0;
      const ai = match.awayForm?.injuries?.impactScore || 0;
      if (hi >= 2.0 && ai >= 2.0) return '';
      if (hi >= 2.0) return ` · ${match.home.split(' ').slice(-1)[0]}`;
      if (ai >= 2.0) return ` · ${match.away.split(' ').slice(-1)[0]}`;
      return '';
    })();
    const valueTag = p.value === 'hot'       ? '<span class="value-tag hot">🔥 VALUE</span>'
                   : p.value === 'value'    ? '<span class="value-tag val">💰 Value</span>'
                   : p.value === 'inj-edge' ? `<span class="value-tag inj">🏥 Inj. Edge${_injEdgeTeam}</span>` : '';
    const confClass = {high:'conf-high',medium:'conf-medium',low:'conf-low'}[p.conf]||'conf-medium';
    const confLabel = {high:'★★★',medium:'★★☆',low:'★☆☆'}[p.conf]||'★★☆';

    // ── Fair Odds comparison row ──────────────────────────────────────────────
    // modelOdds = 1/mp for main markets (calibrated probability model)
    //           = sc-based proxy for specialty markets (corners, cards, HZ etc.)
    // When bookie > modelOdds: their price exceeds our fair value → VALUE territory
    // _pickNegEdge: set true when neg edge is confirmed → dims the pick card visually
    let fairOddsHtml = '';
    let _pickNegEdge = false;
    if (p.modelOdds != null) {
      const mo = p.modelOdds.toFixed(2);
      // isScBased: markets where FV is an sc-signal proxy, not a calibrated model probability.
      // HT markets removed (now use Poisson for goals, de-vigged bookie for 1X2).
      const isScBased = ['Über 8.5 Ecken','Über 9.5 Ecken','Über 11.5 Ecken',
        'Über 3.5 Karten','Über 4.5 Karten'].includes(p.market)
        || p.market.startsWith('Handicap Heim') || p.market.startsWith('Handicap Auswärts')
        || p.market.includes(' über 1.5 Tore') || p.market.includes('Karten');
      const srcLabel = isScBased
        ? '<span style="font-size:9px;color:#444d56;font-style:italic"> (Modell-Näherung)</span>'
        : '';
      // When the fixture has no real market feed AND pick odds are estimated,
      // skip the "Bookie: X.XX" comparison — it would compare model to itself (meaningless edge).
      if (oddsNum != null && !(_noRealOdds && p.oddsIsEst)) {
        // Edge = model probability minus implied (bookie) probability — consistent with p.value thresholds
        // edgePp: positive = we have edge (bookie odds too high), negative = no edge
        const _modelProb = p.modelOdds ? 1 / p.modelOdds : null;
        const _impliedProb = (1 / oddsNum) * 1.03;  // ×1.03 strips bookmaker margin, consistent with p.value calc
        const edgePp = _modelProb != null ? Math.round((_modelProb - _impliedProb) * 100) : null;
        let edgeCls, edgeTxt, bookieCls;
        // _negWarn: true when bookie is notably overpriced vs our model — visual alarm
        let _negWarn = false;
        if (edgePp != null && edgePp >= 13) {
          edgeCls = 'fov-hot'; bookieCls = 'fov-hot';
          edgeTxt = `↑ +${edgePp}pp Edge`;
        } else if (edgePp != null && edgePp >= 7) {
          edgeCls = 'fov-value'; bookieCls = 'fov-value';
          edgeTxt = `↑ +${edgePp}pp Edge`;
        } else if (edgePp == null || (edgePp >= -2 && edgePp < 7)) {
          edgeCls = ''; bookieCls = 'fov-fair';
          edgeTxt = edgePp != null && edgePp > 0 ? `+${edgePp}pp` : '≈ Fair';
        } else if (edgePp < -2 && edgePp >= -5) {
          // Mildly negative: show in orange as caution
          edgeCls = 'fov-below'; bookieCls = 'fov-below';
          edgeTxt = `⚠ ${edgePp}pp`;
          _negWarn = true;
          _pickNegEdge = true;
        } else {
          // Strongly negative (< -5pp): bright red alarm
          edgeCls = 'fov-below'; bookieCls = 'fov-below';
          edgeTxt = `❌ ${edgePp}pp Negativ`;
          _negWarn = true;
          _pickNegEdge = true;
        }
        const _negWarnBanner = _negWarn
          ? `<div style="font-size:10px;color:#f85149;font-weight:600;margin-top:2px;padding:1px 4px;border-radius:3px;background:rgba(248,81,73,0.1);">⚠ Neg. Edge — Bookie billiger als Model-FV</div>`
          : '';
        fairOddsHtml = `<div class="pick-fair-odds">
          <span class="fov-label">Fair Value</span>
          <span class="fov-our">${mo}</span>
          <span style="color:#444d56">→</span>
          <span>Bookie: <span class="fov-bookie-val ${bookieCls}">${oddsNum.toFixed(2)}</span></span>
          <span class="fov-edge ${edgeCls}">${edgeTxt}</span>${srcLabel}
        </div>${_negWarnBanner}`;
      } else {
        // No bookie odds — distinguish between no-feed league vs temporarily missing
        const _noFeedNote = _noRealOdds
          ? `<span style="font-size:10px;color:#8b949e" title="Liga ohne Bookie-Feed (z.B. CRO/HUN) — Modellschätzung als Referenz">— kein Bookie-Feed (Modell-Referenz)</span>`
          : `<span style="color:#444d56;font-size:10px">— kein Bookie-Vergleich verfügbar</span>`;
        fairOddsHtml = `<div class="pick-fair-odds">
          <span class="fov-label">Fair Value</span>
          <span class="fov-our">${mo}</span>
          ${_noFeedNote}${srcLabel}
        </div>`;
      }
    }

    const modsHtml = (p.mods?.length) ? `<div class="pick-mods">${p.mods.join('')}</div>` : '';

    // ── Kelly Criterion stake sizing ──────────────────────────────────────────
    // Formula: f* = (b·p − q) / b  where b = oddsNum−1, p = 1/modelOdds, q = 1−p
    // Show ½ Kelly (conservative, capped at 25%) + Full Kelly (capped at 50%)
    // Only when: real bookie odds present, modelOdds is a calibrated probability (not sc-based proxy)
    let kellyHtml = '';
    if (p.modelOdds != null && oddsNum != null && !(_noRealOdds && p.oddsIsEst) && !p.oddsIsEst && oddsNum > 1.01) {
      const _kB = oddsNum - 1;
      const _kP = 1 / p.modelOdds;
      const _kQ = 1 - _kP;
      const _kFull = (_kB * _kP - _kQ) / _kB;
      if (_kFull > 0.005) {   // only show when Kelly suggests at least 0.5% stake
        const _kHalf    = Math.min(_kFull / 2, 0.25);
        const _kFullCap = Math.min(_kFull, 0.50);
        const _kHPct    = (_kHalf    * 100).toFixed(1);
        const _kFPct    = (_kFullCap * 100).toFixed(1);
        // Colour hint: grey = tiny edge, amber = modest, green = strong
        const _kColor   = _kHalf < 0.025 ? '#8b949e' : _kHalf < 0.07 ? '#e3b341' : '#00d4a1';
        const _kCap     = _kFullCap < _kFull ? ' (cap)' : '';
        kellyHtml = `<div class="pick-kelly">
          <span class="pk-label">Kelly</span>
          <span style="color:${_kColor};font-weight:700;font-size:11px;" title="½ Kelly (empfohlen): ${_kHPct}% des Bankrolls setzen">½K: ${_kHPct}%</span>
          <span class="pk-dot">·</span>
          <span class="pk-full" title="Full Kelly${_kCap}: ${_kFPct}%">Full: ${_kFPct}%${_kCap}</span>
          <span class="pk-hint" title="Kelly Criterion: mathematisch optimale Einsatzgröße basierend auf Model-Edge. ½ Kelly ist die konservative Empfehlung (halbes Risiko, ~75% des Erwartungswerts).">ℹ</span>
        </div>`;
      }
    }

    // ── Opening → Current odds drift per pick ─────────────────────────────────
    // Maps pick market → odds key in odds_open / current odds object.
    // Only shows when odds_open exists AND the relevant key is present in both snapshots.
    // Green = line shortened (market moved our way = positive CLV signal).
    // Red   = line lengthened (market moved against us = negative CLV signal).
    let driftHtml = '';
    if (_oddsOpen && oddsNum != null && !p.oddsIsEst) {
      const mktL = (p.market || '').toLowerCase();
      // DC picks use dc1X_bkr / dcX2_bkr — NOT the raw Away/Home Win odds.
      // Using 'aw' for X2 or 'hw' for 1X caused apples-to-oranges drift comparisons.
      // Guard: 1HZ / 2HZ picks must NOT use FT opening odds (different markets).
      // If market contains 'hz:' or 'halbzeit', there's no half-specific opening to compare.
      const _isHzPick = mktL.includes('hz:') || mktL.includes('halbzeit');
      const _oddsKey = _isHzPick                                                                          ? null
        : mktL.includes('doppelte chance') && mktL.includes('x2')                                        ? 'dcX2_bkr'
        : mktL.includes('doppelte chance') && mktL.includes('1x')                                        ? 'dc1X_bkr'
        : mktL.includes('heimsieg') || mktL.includes('dnb: heim')                                        ? 'hw'
        : mktL.includes('auswärtssieg') || mktL.includes('dnb: ausw')                                    ? 'aw'
        : mktL.includes('unentschieden') || mktL.includes('remis')                                       ? 'dr'
        : mktL.includes('over 2.5') || mktL.includes('über 2.5')                                         ? 'o25'
        : mktL.includes('under 2.5') || mktL.includes('unter 2.5')                                       ? 'u25'
        : mktL.includes('over 3.5') || mktL.includes('über 3.5')                                         ? 'o35'
        : mktL.includes('btts') || mktL.includes('beide teams treffen')                                  ? 'bttsY'
        : mktL.startsWith('ah heim')                                                                      ? 'ah_h'
        : mktL.startsWith('ah ausw')                                                                      ? 'ah_a'
        : null;
      // For DC picks: if bookmaker DC snapshot not in odds_open, derive from 1X2 opening
      let _openOdds = _oddsKey ? parseFloat(_oddsOpen[_oddsKey]) : null;
      if ((!_openOdds || _openOdds <= 1) && _oddsOpen.hw && _oddsOpen.dr && _oddsOpen.aw) {
        if (_oddsKey === 'dcX2_bkr') {
          const tot = 1/_oddsOpen.hw + 1/_oddsOpen.dr + 1/_oddsOpen.aw;
          const pd = (1/_oddsOpen.dr)/tot, pa = (1/_oddsOpen.aw)/tot;
          _openOdds = Math.round((1/(pd+pa)) * 0.97 * 100) / 100;
        } else if (_oddsKey === 'dc1X_bkr') {
          const tot = 1/_oddsOpen.hw + 1/_oddsOpen.dr + 1/_oddsOpen.aw;
          const ph = (1/_oddsOpen.hw)/tot, pd = (1/_oddsOpen.dr)/tot;
          _openOdds = Math.round((1/(ph+pd)) * 0.97 * 100) / 100;
        }
      }
      if (_openOdds && _openOdds > 1 && oddsNum > 1 && Math.abs(_openOdds - oddsNum) > 0.01) {
        const _openImpl = 1 / _openOdds;
        const _currImpl = 1 / oddsNum;
        const _ppDrift  = Math.round((_currImpl - _openImpl) * 100);  // +pp = line shortened (bookie raised prob)
        if (Math.abs(_ppDrift) >= 2) {
          // Positive ppDrift = implied prob went UP = odds shortened = market moved AGAINST our pick (bad CLV signal)
          // But for our pick odds: if our odds > opening odds → line shortened → bad. if our odds < opening → good.
          // CLV: we want OUR odds > closing odds. Here: _openOdds is opening, oddsNum is current (proxy for closing).
          // If oddsNum > _openOdds → odds LENGTHENED = market disagrees more → BAD for us
          // If oddsNum < _openOdds → odds SHORTENED = market moved our way → GOOD for us (positive CLV signal)
          const _clvPositive = oddsNum < _openOdds;  // line shortened = market confirmed our view
          const _driftColor  = _clvPositive ? '#3fb950' : '#f85149';
          const _driftArrow  = _clvPositive ? '↘' : '↗';
          const _ppLabel     = (_ppDrift > 0 ? '+' : '') + _ppDrift + 'pp';
          const _clvNote     = _clvPositive ? ' CLV+' : '';
          const _openTs      = _pm?.odds_open_ts ? new Date(_pm.odds_open_ts).toLocaleDateString('de-AT', {day:'2-digit', month:'2-digit'}) : null;
          const _tsNote      = _openTs ? ` (seit ${_openTs})` : '';
          driftHtml = `<div class="pick-odds-drift">
            <span style="color:#8b949e;font-size:10px;">Opening${_tsNote}:</span>
            <span style="font-size:10px;color:#8b949e;">${_openOdds.toFixed(2)}</span>
            <span style="color:#444d56;font-size:10px;">→ Aktuell:</span>
            <span style="font-size:10px;font-weight:600;color:${_driftColor};">${oddsNum.toFixed(2)} ${_driftArrow} <span title="${_ppLabel} Verschiebung seit Opening">${_ppLabel}${_clvNote}</span></span>
          </div>`;
        }
      }
    }

    // ── Tactical booking hint (card picks only) ───────────────────────────────
    // When players are one yellow from suspension, they may play more aggressively
    // in this match — relevant signal for card market picks.
    let _tacBookHint = '';
    if (p.market.includes('Karten')) {
      const _tbFix  = leagueKey ? (LEAGUES[leagueKey]?.fixtures || []) : [];
      const _tbSigs = [
        ...getTacticalBookingSignals(match.bookings?.home || [], match.home, match.date, _tbFix),
        ...getTacticalBookingSignals(match.bookings?.away || [], match.away, match.date, _tbFix),
      ];
      if (_tbSigs.length) {
        const _tbNames = _tbSigs.slice(0, 2).map(s => `${s.lastName}${s.posStr}`).join(', ');
        const _tbExtra = _tbSigs.length > 2 ? ` +${_tbSigs.length - 2} weitere` : '';
        _tacBookHint = `<br>🟨 Gelb-Risiko: ${_tbNames}${_tbExtra} nahe Sperre — könnte(n) aggressiver auftreten.`;
      }
    }

    // ── Safer / Bolder alternative lines ─────────────────────────────────────
    // saferAlt: pick has odds > 2.0 → safer version is the primary recommendation
    // boldAlt:  pick has odds 1.4–2.0 → bolder version shown as secondary option
    let altHtml = '';
    if (p.saferAlt) {
      altHtml = `<div class="pick-alt safer">
        <div style="margin-bottom:3px;">
          <span class="safer-label">✓ Main Pick</span>
          <span class="safer-market">${p.saferAlt.market}</span>
          <span class="safer-odds">@ ~${p.saferAlt.estOdds.toFixed(2)}</span>
          <span class="alt-note" style="margin-left:4px;">(est.)</span>
        </div>
        <div style="font-size:10px;opacity:.55;">Value alt: ${p.market} @ ${oddsNum ? oddsNum.toFixed(2) : '?'}</div>
      </div>`;
    } else if (p.boldAlt) {
      altHtml = `<div class="pick-alt bold">
        📈 <strong>Mehr Value:</strong> ${p.boldAlt.market} <span class="alt-odds">@ ~${p.boldAlt.estOdds.toFixed(2)}</span>
        <span class="alt-note">(Modell-Näherung)</span>
      </div>`;
    }

    const _ciCls = p.conf === 'high' ? ' ci-high' : p.conf === 'medium' ? ' ci-medium' : '';
    const _isTopPick = window._topPickSet?.has(`${match.home}|${match.away}|${p.market}`);
    const _topCls  = _isTopPick ? ' is-top-pick' : '';
    const _topBadge = _isTopPick ? `<span class="top-pick-badge">⭐ Top Pick</span>` : '';
    // Negative-edge picks get a left red border + reduced opacity as visual warning.
    const _negEdgeStyle = _pickNegEdge
      ? ' style="opacity:0.72;border-left:3px solid #f85149;"'
      : '';

    // ── 3-Signal Bet Verdict ──────────────────────────────────────────────────
    // Delegated to pick-verdict.js › computeVerdict() — single source of truth.
    // Pass null for odds when no real bookie feed exists (estimated leagues).
    let verdictHtml = '';
    {
      const _vd = computeVerdict({
        modelOdds: p.modelOdds,
        odds:      (_noRealOdds && p.oddsIsEst) ? null : oddsNum,
        oddsIsEst: p.oddsIsEst,
        market:    p.market,
        oddsOpen:  _oddsOpen,
        h2h:       match.h2h,
      });
      const { modEmoji, modTxt, mktEmoji, mktTxt, storyEmoji, storyTxt,
              verdict: _vTxt, vColor: _vColor, vBg: _vBg, vBorder: _vBorder } = _vd;
      verdictHtml = `<div class="pick-verdict">
        <span class="pv-sig">${modEmoji} <span class="pv-lbl">Modell</span> <span class="pv-val">${modTxt}</span></span>
        <span class="pv-dot">·</span>
        <span class="pv-sig">${mktEmoji} <span class="pv-lbl">Markt</span> <span class="pv-val">${mktTxt}</span></span>
        <span class="pv-dot">·</span>
        <span class="pv-sig">${storyEmoji} <span class="pv-lbl">H2H</span> <span class="pv-val">${storyTxt}</span></span>
        <span class="pv-badge" style="background:${_vBg};color:${_vColor};border:1px solid ${_vBorder};">${_vTxt}</span>
      </div>`;
    }

    return `<div class="pick-item${_ciCls}${_topCls}"${_negEdgeStyle}>
      <span class="pick-icon">${p.icon}</span>
      <div class="pick-body">
        <div class="pick-market">${_topBadge}<span class="pick-conf ${confClass}">${confLabel}</span><span>${p.market}</span>${oddsTag}${lowWarn}${valueTag}</div>
        ${verdictHtml}
        ${altHtml}
        ${fairOddsHtml}
        ${kellyHtml}
        ${driftHtml}
        ${modsHtml}
        <div class="pick-reason">${p.reason}${_tacBookHint}</div>
      </div>
    </div>`;
  }).join('');

  // Telegram share payload (JSON-encoded match data)
  const shareData = encodeURIComponent(JSON.stringify(match)).replace(/'/g,'%27');

  // ── Do-or-Die banner — shown above pressure strip when truly no room for error ──
  const _dod = isDoOrDie(match);
  let dodHtml = '';
  if (_dod) {
    const dodClass = _dod.isGold ? 'dod-banner gold-dod' : 'dod-banner';
    const dodIcon  = _dod.rl <= 2 ? '🚨' : '⚡';
    const dodTitle = _dod.rl <= 1 ? 'LETZTES SPIEL DER SAISON'
                   : _dod.rl <= 2 ? 'JETZT ODER NIE'
                   : 'LETZTE CHANCE';
    const dodSub   = _dod.teams.map(t => `${t.name}: ${t.label}`).join(' · ');
    dodHtml = `<div class="${dodClass}">
      <span class="dod-icon">${dodIcon}</span>
      <div class="dod-body">
        <span class="dod-title">${dodTitle} · NOCH ${_dod.rl} SPIEL${_dod.rl === 1 ? '' : 'E'}</span>
        <span class="dod-sub">${dodSub}</span>
      </div>
    </div>`;
  }

  // ── Pressure banner ───────────────────────────────────────────────────
  // Shown when ≥1 team has a stake AND there are ≤6 rounds left.
  // Intensity and language scale with how close to the end of season we are.
  const _rlC = match.roundsLeft ?? 99;
  const _hSC = match.homeStake || null;   // full stake object {score, labels:[]} or null
  const _aSC = match.awayStake || null;
  const _anyStake = (_hSC?.labels?.length > 0) || (_aSC?.labels?.length > 0);
  let pressureHtml = '';
  if (_rlC <= 6 && _anyStake) {
    const _hMotivBanner = _hSC?.motivationLevel || 'full';
    const _aMotivBanner = _aSC?.motivationLevel || 'full';
    const _allSecured = (!_hSC || _hMotivBanner === 'none') && (!_aSC || _aMotivBanner === 'none');
    // If all staked teams are already confirmed, show neutral "secured" strip instead of alarm
    const _pInt   = _allSecured ? 'secured'
                  : _rlC <= 1 ? 'extreme' : _rlC <= 2 ? 'critical' : _rlC <= 3 ? 'high' : 'medium';
    const _pIcon  = _allSecured ? '⬜'
                  : _rlC <= 1 ? '🚨' : _rlC <= 2 ? '🔥' : _rlC <= 3 ? '⚠️' : '📍';
    const _pRounds = _allSecured ? 'SAISONZIEL GESICHERT'
                   : _rlC <= 1 ? 'LETZTE RUNDE DER SAISON' : `NOCH ${_rlC} RUNDEN`;
    const _hLabel = getPressureLabel(_hSC, match.home);
    const _aLabel = getPressureLabel(_aSC, match.away);
    pressureHtml = `<div class="pressure-strip ${_pInt}">
      <span class="ps-icon">${_pIcon}</span>
      <div class="ps-content">
        <span class="ps-rounds">${_pRounds}</span>
        ${_hLabel ? `<span class="ps-team">${_hLabel}</span>` : ''}
        ${_aLabel ? `<span class="ps-team">${_aLabel}</span>` : ''}
      </div>
    </div>`;
  }

  // ── Context strip: rest days + injuries + referee ───────────────────────
  const _ctxFix  = leagueKey ? (LEAGUES[leagueKey]?.fixtures || []) : [];
  const _ctxHRest = getRestDays(match.home, match.date, _ctxFix);
  const _ctxARest = getRestDays(match.away, match.date, _ctxFix);
  const _ctxHInj  = match.homeForm?.injuries || null;
  const _ctxAInj  = match.awayForm?.injuries || null;
  const ctxBadges = [];

  // Fatigue — show in plain language, spell out Tage
  if (_ctxHRest != null && _ctxHRest <= 5) {
    const cls = _ctxHRest <= 3 ? 'ctx-fatigue-high' : 'ctx-fatigue-med';
    ctxBadges.push(`<span class="ctx-badge ${cls}">😴 Kurze Pause: ${match.home} (${_ctxHRest} Tage)</span>`);
  }
  if (_ctxARest != null && _ctxARest <= 5) {
    const cls = _ctxARest <= 3 ? 'ctx-fatigue-high' : 'ctx-fatigue-med';
    ctxBadges.push(`<span class="ctx-badge ${cls}">😴 Kurze Pause: ${match.away} (${_ctxARest} Tage)</span>`);
  }

  // Injuries — focus on names, not technical impact score
  const _buildInjBadge = (inj, teamName) => {
    if (!inj || (inj.total||0) === 0) return '';
    const imp = inj.impactScore || 0;
    if (imp < 0.3 && (inj.confirmed||0) === 0) return '';
    const cls = imp >= 3.5 ? 'ctx-injury-high' : imp >= 2.0 ? 'ctx-injury-atk' : 'ctx-injury-def';
    // Player names (last name only, max 2)
    const confirmed = (inj._raw || []).filter(p => p.type === 'Missing Fixture');
    const names = confirmed.slice(0, 2).map(p => p.player.split(' ').slice(-1)[0]);
    const nameStr = names.length ? names.join(', ') + (confirmed.length > 2 ? ` +${confirmed.length - 2}` : '') : '';
    // Position area (most affected)
    const areaMap = [];
    if ((inj.goalkeeper||0) > 0) areaMap.push('TW');
    if ((inj.attack||0)     > 0) areaMap.push(`${inj.attack} Ang`);
    if ((inj.defense||0)    > 0) areaMap.push(`${inj.defense} Abw`);
    if ((inj.midfield||0)   > 0) areaMap.push(`${inj.midfield} MF`);
    const areaStr = areaMap.length ? ` · ${areaMap.slice(0,3).join('/')}${inj.posEstimated ? ' ~' : ''}` : '';
    const label = nameStr ? `${nameStr} fehlt${confirmed.length > 1 ? 'en' : ''}${areaStr}` : `${inj.total} Ausfälle${areaStr}`;
    return `<span class="ctx-badge ${cls}">🏥 ${teamName}: ${label}</span>`;
  };
  const hInjHtml = _buildInjBadge(_ctxHInj, match.home);
  const aInjHtml = _buildInjBadge(_ctxAInj, match.away);
  if (hInjHtml) ctxBadges.push(hInjHtml);
  if (aInjHtml) ctxBadges.push(aInjHtml);

  // ── Karten-Pick guard (used by both yellow-card badges and referee stats below) ──
  const _hasKartenPick = visiblePicks.some(p => p.market.includes('Karten'));

  // ── Yellow card accumulation / tactical booking ──────────────────────────────
  // Only shown when the system generated a Karten pick — avoids orphaned info.
  if (_hasKartenPick) {
    const _allFix = leagueKey ? (LEAGUES[leagueKey]?.fixtures || []) : [];
    const _bkHome = match.bookings?.home || [];
    const _bkAway = match.bookings?.away || [];
    const _homeTacSigs = getTacticalBookingSignals(_bkHome, match.home, match.date, _allFix);
    const _awayTacSigs = getTacticalBookingSignals(_bkAway, match.away, match.date, _allFix);

    for (const sig of [..._homeTacSigs, ..._awayTacSigs]) {
      const teamLabel = [..._homeTacSigs].includes(sig) ? match.home : match.away;
      let badgeCls, badgeText;
      if (sig.isTacticalStrong) {
        // Clear case: miss a weak game, return for a big one
        badgeCls  = 'ctx-booking-tactical';
        badgeText = `🟨 ${sig.lastName}${sig.posStr}: ${sig.yellows}/${sig.threshold} Gelbe`
          + ` — Sperre vs ${sig.nextOpponent} (schwächer) denkbar`;
      } else if (sig.isTactical) {
        // Mild case: slight quality difference
        badgeCls  = 'ctx-booking-warn';
        badgeText = `🟨 ${sig.lastName}${sig.posStr}: ${sig.yellows}/${sig.threshold} Gelbe`
          + ` — eine Karte = gesperrt vs ${sig.nextOpponent}`;
      } else {
        // Suspension risk only — no tactical angle visible
        badgeCls  = 'ctx-booking-risk';
        badgeText = `🟨 ${sig.lastName}${sig.posStr}: ${sig.yellows}/${sig.threshold} Gelbe — Sperren-Risiko`;
      }
      ctxBadges.push(`<span class="ctx-badge ${badgeCls}">${badgeText}</span>`);
    }
  }

  // Referee — only shown alongside a Karten pick (card tendency only matters for that market)
  const _ref = match.refereeStats || null;
  if (_hasKartenPick && _ref?.name) {
    const avg = _ref.avgCards;
    const refCls = avg == null    ? 'ctx-ref-neutral'
                 : avg >= 4.5    ? 'ctx-ref-high'
                 : avg >= 3.5    ? 'ctx-ref-med'
                 : avg >= 0      ? 'ctx-ref-low'
                 : 'ctx-ref-neutral';
    const avgNote = avg != null ? ` · Ø ${avg} Karten/Sp` : '';
    ctxBadges.push(`<span class="ctx-badge ${refCls}">👨‍⚖️ Schiri: ${_ref.name}${avgNote}</span>`);
  }

  const contextHtml = ctxBadges.length
    ? `<div class="context-strip"><span class="ctx-label">Kontext</span>${ctxBadges.join('')}</div>`
    : '';

  // ── Signal Bar: at-a-glance indicators (why is this match special?) ──────────
  // Shows up to 4 prioritised signals between match title and context strip.
  // Priority: 1) Value  2) Injuries  3) Pressure  4) Fatigue  5) H2H  6) LineMove
  const _signals = [];

  // 1 — Value signals (most actionable)
  const _sigHasHot   = visiblePicks.some(p => p.value === 'hot');
  const _sigHasValue = visiblePicks.some(p => p.value === 'value' || p.value === 'inj-edge');
  if (_sigHasHot)        _signals.push({cls:'sig-value-hot',   txt:'🔥 HOT VALUE'});
  else if (_sigHasValue) _signals.push({cls:'sig-value',       txt:'💰 Value Edge'});

  // 2 — Injury signals
  const _sigMaxInj = Math.max(_ctxHInj?.impactScore||0, _ctxAInj?.impactScore||0);
  const _sigInjTeam = (_ctxAInj?.impactScore||0) >= (_ctxHInj?.impactScore||0) ? match.away : match.home;
  const _sigInjShort = _sigInjTeam.split(' ').slice(-1)[0];
  if (_sigMaxInj >= 3.5)       _signals.push({cls:'sig-inj-crit', txt:`🏥 Schwer: ${_sigInjShort}`});
  else if (_sigMaxInj >= 2.0)  _signals.push({cls:'sig-inj-warn', txt:`🏥 Ausfälle: ${_sigInjShort}`});

  // 3 — Pressure / Tabellenkontext signals
  const _sigHColors = (match.homeStake?.labels||[]).map(l=>l.c);
  const _sigAColors = (match.awayStake?.labels||[]).map(l=>l.c);
  const _sigBothRed  = _sigHColors.includes('red')  && _sigAColors.includes('red');
  const _sigBothGold = _sigHColors.includes('gold') && _sigAColors.includes('gold');
  const _sigMustWin  = match.homeStake?.mustWin || match.awayStake?.mustWin;
  const _sigRedVsGold = (_sigHColors.includes('red') && _sigAColors.includes('gold'))
                     || (_sigHColors.includes('gold') && _sigAColors.includes('red'));
  if (_sigBothGold)        _signals.push({cls:'sig-pressure-gold', txt:'🏆 Titelduell'});
  else if (_sigBothRed)    _signals.push({cls:'sig-pressure-red',  txt:'🆘 Kellerduell'});
  else if (_sigRedVsGold)  _signals.push({cls:'sig-pressure-warn', txt:'⚡ Spitze vs Keller'});
  else if (_sigMustWin)    _signals.push({cls:'sig-pressure-warn', txt:'⚡ Muss-Sieg'});

  // 4 — Fatigue signal
  const _sigMinRest = Math.min(_ctxHRest ?? 99, _ctxARest ?? 99);
  if (_sigMinRest !== 99 && _sigMinRest <= 3) {
    const _sigFatTeam = (_ctxHRest||99) <= (_ctxARest||99) ? match.home : match.away;
    _signals.push({cls:'sig-fatigue', txt:`😴 ${_sigFatTeam.split(' ').slice(-1)[0]}: nur ${_sigMinRest}T`});
  }

  // 5 — H2H signal (strong pattern over ≥5 games)
  const _sigH2h = match.h2h;
  if (_sigH2h?.games >= 5) {
    const _g  = _sigH2h.games;
    const _br = (_sigH2h.btts  ||0) / _g;
    const _or = (_sigH2h.over25||0) / _g;
    const _hw = (_sigH2h.homeWins||0) / _g;
    const _aw = (_sigH2h.awayWins||0) / _g;
    if      (_br >= 0.70) _signals.push({cls:'sig-h2h', txt:`⚽ H2H ${Math.round(_br*100)}% BTTS`});
    else if (_or >= 0.70) _signals.push({cls:'sig-h2h', txt:`⚽ H2H ${Math.round(_or*100)}% Over 2.5`});
    else if (_hw >= 0.75) _signals.push({cls:'sig-h2h', txt:`📊 H2H: ${match.home.split(' ').slice(-1)[0]} dom.`});
    else if (_aw >= 0.75) _signals.push({cls:'sig-h2h', txt:`📊 H2H: ${match.away.split(' ').slice(-1)[0]} dom.`});
  }

  // 6 — Line movement signal
  if (_lmRows?.length) _signals.push({cls:'sig-movement', txt:'📈 Linie bewegt'});

  // 7 — Tactical booking signal
  const _allFixSig = leagueKey ? (LEAGUES[leagueKey]?.fixtures || []) : [];
  const _tacHome = getTacticalBookingSignals(match.bookings?.home || [], match.home, match.date, _allFixSig);
  const _tacAway = getTacticalBookingSignals(match.bookings?.away || [], match.away, match.date, _allFixSig);
  const _tacStrong = [..._tacHome, ..._tacAway].filter(s => s.isTacticalStrong);
  const _tacAny    = [..._tacHome, ..._tacAway].filter(s => s.isTactical);
  // Only show booking signal when the system actually generated a Karten pick —
  // (_hasKartenPick already computed above, before the context section)
  if (_hasKartenPick) {
    if (_tacStrong.length) {
      _signals.push({cls:'sig-booking', txt:`🟨 Takt. Sperre: ${_tacStrong[0].lastName}`});
    } else if (_tacAny.length) {
      _signals.push({cls:'sig-booking', txt:`🟨 Sperren-Risiko: ${_tacAny[0].lastName}`});
    }
  }

  const signalBarHtml = _signals.length
    ? `<div class="signal-bar">${_signals.slice(0,4).map(s=>`<span class="signal-pill ${s.cls}">${s.txt}</span>`).join('')}</div>`
    : '';

  // ── Event Page Link ───────────────────────────────────────────────────────
  const _slugify = t => (t||'').toLowerCase()
    .replace(/ä/g,'ae').replace(/ö/g,'oe').replace(/ü/g,'ue').replace(/ß/g,'ss')
    .replace(/á/g,'a').replace(/é/g,'e').replace(/í/g,'i').replace(/ó/g,'o').replace(/ú/g,'u')
    .replace(/ñ/g,'n').replace(/ç/g,'c')
    .replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'');
  const _dateIso = (() => {
    try { const [d,mo,y]=(match.date||'').split('.'); return `${y}-${mo.padStart(2,'0')}-${d.padStart(2,'0')}`; } catch(_){return '';}
  })();
  const _eventSlug = `${_slugify(match.home)}-vs-${_slugify(match.away)}-${_dateIso}`;
  const _matchPageLink = _eventSlug
    ? `<a href="matches/match.html?m=${_eventSlug}" target="_blank"
         style="display:flex;align-items:center;justify-content:center;gap:7px;
                padding:10px 14px;border-radius:8px;width:100%;
                border:1px solid #00d4a133;background:#00d4a108;
                color:var(--accent);font-size:12px;font-weight:700;
                text-decoration:none;transition:all .15s;margin-bottom:8px;"
         onmouseover="this.style.background='#00d4a118';this.style.borderColor='#00d4a166'"
         onmouseout="this.style.background='#00d4a108';this.style.borderColor='#00d4a133'">
         🔍 Spiel-Analyse öffnen
       </a>`
    : '';

  return `
  <div class="stake-card ${ct}">
    <div class="card-watermark"><img src="cocobet-logo.png" alt="" onerror="this.parentElement.style.display='none'"></div>
    <div class="score-badge ${scoreClass(sc)}"><span class="sb-val">${sc}</span><span class="sb-sub">/12</span></div>
    <div class="card-top">
      <div class="card-meta">${leagueFlag} <span class="card-league-name">${leagueName}</span><span class="card-meta-sep">·</span><span class="card-date-inline">📅 ${match.date}${match.time ? ' · ' + match.time : ''}</span></div>
      <div class="card-match"><span class="card-home">${match.home}</span><span class="card-vs">vs</span><span class="card-away">${match.away}</span></div>
    </div>
    ${dodHtml}${signalBarHtml}${pressureHtml}${contextHtml}${renderSquadBlock(match)}${lineMovementHtml}
    <div class="teams-stakes">
      ${renderStakeRow(match.home, match.homeStake, match.homeForm, leagueKey)}
      ${renderStakeRow(match.away, match.awayStake, match.awayForm, leagueKey)}
    </div>
    ${renderH2H(match.h2h)}
    <div class="bet-angle">
      <div class="ba-header"><span class="ba-label">Wett-Winkel</span><span class="ba-badge ${angle.cls}">${angle.badge}</span></div>
      <div class="ba-text">${angle.text}</div>
    </div>
    <div class="picks-section">
      <div class="picks-label">🎲 Top Wetten für diese Partie</div>
      ${picksHtml || '<div style="font-size:11px;color:var(--muted);padding:6px 0;font-style:italic">Kein Pick mit ausreichender Konfidenz (★★☆+) für dieses Spiel.</div>'}
      ${!window._oddsReady ? '<div style="font-size:10px;color:var(--muted);padding:3px 0;font-style:italic">⏳ Quoten werden geladen…</div>' : ''}
    </div>
    <div style="margin-top:8px">${_matchPageLink}</div>
    <div style="display:flex;flex-wrap:wrap;gap:7px;margin-top:4px">
      <button class="infographic-btn" title="Infografik erstellen" onclick="generateInfographic('${shareData}','${leagueName.replace(/'/g,"\\'")}','${leagueFlag}','${leagueKey||''}')">
        📸 Info
      </button>
      <button class="infographic-btn" title="Sportschau-Skript für CapCut/ElevenLabs" onclick="generateScript('${shareData}','${leagueName.replace(/'/g,"\\'")}','${leagueFlag}','${leagueKey||''}')" style="color:#a78bfa;border-color:#a78bfa55;">
        🎙 Skript
      </button>
      <button class="share-btn" style="flex:1;min-width:60px" onclick="shareTelegram('${shareData}','${leagueName.replace(/'/g,"\\'")}','${leagueFlag}','${leagueKey||''}')">
        📤 TG
      </button>
      <button class="share-btn" style="flex:0 0 auto;width:auto;padding:9px 10px" title="Text kopieren (DE)" onclick="copyCard('${shareData}','${leagueName.replace(/'/g,"\\'")}','${leagueFlag}','${leagueKey||''}',this,'de')">
        📋
      </button>
      <button class="share-btn" style="flex:0 0 auto;width:auto;padding:9px 10px;color:#58a6ff;border-color:#58a6ff55;" title="Copy text (EN)" onclick="copyCard('${shareData}','${leagueName.replace(/'/g,"\\'")}','${leagueFlag}','${leagueKey||''}',this,'en')">
        🇬🇧
      </button>
      <button class="share-btn" style="flex:0 0 auto;width:auto;padding:9px 10px;color:#a78bfa;border-color:#a78bfa55;" title="Card als Bild kopieren (DE)" onclick="copyCardImage(this,'de')">
        🖼️
      </button>
      <button class="share-btn" style="flex:0 0 auto;width:auto;padding:9px 10px;color:#58a6ff;border-color:#58a6ff55;" title="Copy card as image (EN)" onclick="copyCardImage(this,'en')">
        🇬🇧🖼️
      </button>
    </div>
  </div>`;
}

// ═══════════════════════════════════════════════════════
//  SHARP MONEY RADAR
//  Aggregates line movement across ALL leagues for today's fixtures.
//  Four sections:
//    1. Overview KPIs  — fixtures tracked, avg vig, biggest mover
//    2. Biggest Movers — top-15 fixtures by max movement magnitude
//    3. Our Picks      — today's picks enriched with sharp context
//    4. Market Heatmap — movement by market type across all fixtures
// ═══════════════════════════════════════════════════════
// ──────────────────────────────────────────────────────────────────────────
//  SHARP-RADAR ADD-ONS (NEU 09.06.2026) — Sharp-Move-getriebene Engine
//  Block A: Sharp-Move + Conviction Watchlist
//  Block B: Bayesian-Weights Live-Status (was hat das System gelernt)
//  Block C: CLV-Aggregation pro Signal-Familie (welche tragen langfristig)
// ──────────────────────────────────────────────────────────────────────────

// Finde den besten Conviction-Pick für ein Match (homeId-awayId).
// Liefert {score, label, sharpMoveActive, pickKey, market} oder null.
function _findBestConvictionForMatch(homeId, awayId) {
  const wm = window.WM2026_DATA;
  if (!wm || !wm.picks) return null;
  let best = null;
  for (const [pk, plist] of Object.entries(wm.picks)) {
    if (!pk.endsWith(`-${homeId}-${awayId}`)) continue;
    for (const p of plist) {
      const score = typeof p.convictionScore === 'number' ? p.convictionScore : null;
      if (score === null) continue;
      if (!best || score > best.score) {
        best = {
          score, label: p.convictionLabel,
          sharpMoveActive: !!p.sharpMoveActive,
          pickKey: pk, market: p.market,
          verdict: p.verdict,
        };
      }
    }
  }
  return best;
}

// (28.06.2026) Pre-Match-gefilterte History, von renderSharpRadar gesetzt. Sparkline + „letzte
// Bewegung" lesen daraus → kein In-Play-Cliff. Fallback auf das Roh-Global wenn (noch) nicht gesetzt.
let _sharpActiveHist = null;
function _sharpHistFor(key) {
  return (_sharpActiveHist && _sharpActiveHist[key]) || window.WM2026_ODDS_HISTORY?.[key];
}

// Mini-Sparkline aus odds-history für ein WM-Match-Markt (Pinnacle).
// Returns SVG-String oder ''. width/height konfigurierbar.
function _wmMiniSparkline(homeId, awayId, marketKey, w = 70, h = 18) {
  const hist = _sharpHistFor(`${homeId}-${awayId}`);
  if (!Array.isArray(hist) || hist.length < 2) return '';
  const series = hist.map(s => s[marketKey]).filter(v => typeof v === 'number' && v > 1);
  if (series.length < 2) return '';
  const min = Math.min(...series), max = Math.max(...series);
  if (max === min) return '';
  const stepX = w / (series.length - 1);
  const pts = series.map((v, i) => `${(i * stepX).toFixed(1)},${(h - ((v - min) / (max - min)) * h).toFixed(1)}`).join(' ');
  const last = series[series.length - 1], first = series[0];
  const col = last < first ? '#3fb950' : last > first ? '#f85149' : '#8b949e';
  return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" style="vertical-align:middle;"><polyline points="${pts}" fill="none" stroke="${col}" stroke-width="1.5"/></svg>`;
}

// "Letzte Bewegung" aus History — wann hat sich der Wert zuletzt geändert?
function _lastChangeAgo(homeId, awayId, marketKey) {
  const hist = _sharpHistFor(`${homeId}-${awayId}`);
  if (!Array.isArray(hist) || hist.length < 2) return null;
  // Find most recent change going from end backwards
  let lastVal = hist[hist.length - 1]?.[marketKey];
  if (typeof lastVal !== 'number') return null;
  for (let i = hist.length - 2; i >= 0; i--) {
    const v = hist[i][marketKey];
    if (typeof v === 'number' && Math.abs(v - lastVal) > 0.01) {
      const ts = hist[i + 1]?.ts;
      if (!ts) return null;
      const diffH = (Date.now() - new Date(ts).getTime()) / 3600000;
      if (diffH < 1) return { mins: Math.round(diffH * 60), label: 'vor <1h' };
      if (diffH < 24) return { mins: Math.round(diffH * 60), label: `vor ${Math.round(diffH)}h` };
      const diffD = Math.floor(diffH / 24);
      return { mins: Math.round(diffH * 60), label: `vor ${diffD}d` };
    }
  }
  return { mins: 9999, label: 'stabil' };
}

// Sammle alle aktiven WM-Picks aus wm2026-data
function _collectActiveWmPicks() {
  const wm = window.WM2026_DATA;
  if (!wm || !wm.picks || !wm.groups) return [];
  const teamLookup = {};
  for (const grp of Object.values(wm.groups || {})) {
    for (const t of (grp.teams || [])) teamLookup[t.id] = t;
  }
  const fxLookup = {};
  for (const [gk, grp] of Object.entries(wm.groups || {})) {
    for (const fx of (grp.fixtures || [])) {
      fxLookup[`${gk}-${fx.matchday}-${fx.home}-${fx.away}`] = { ...fx, groupKey: gk };
    }
  }
  const result = [];
  for (const [pk, plist] of Object.entries(wm.picks)) {
    const fx = fxLookup[pk];
    if (!fx) continue;
    // Nur künftige Fixtures
    try {
      const fxDate = new Date(`${fx.date}T${fx.time || '20:00'}:00`);
      if (fxDate < new Date(Date.now() - 6 * 3600 * 1000)) continue;
    } catch(e) {}
    for (const p of plist) {
      const verdict = p.verdict;
      if (verdict === 'SKIP' || verdict === 'BEOBACHTEN') continue;
      result.push({
        pickKey:  pk,
        fixture:  fx,
        home:     teamLookup[fx.home] || { id: fx.home, name: fx.home, flag: '🏳' },
        away:     teamLookup[fx.away] || { id: fx.away, name: fx.away, flag: '🏳' },
        pick:     p,
      });
    }
  }
  return result;
}

// Block A — Watchlist: Sharp-Move ODER Conviction ≥7
function _renderSharpWatchlist() {
  const picks = _collectActiveWmPicks();
  const watch = picks.filter(item => {
    const p = item.pick;
    return p.sharpMoveActive
        || (typeof p.convictionScore === 'number' && p.convictionScore >= 7);
  });
  if (watch.length === 0) {
    return `<div class="section-label" style="margin-bottom:10px;">🎯 Sharp-Money Watchlist</div>
      <div style="background:var(--card);border:1px solid var(--border);border-radius:12px;padding:20px;margin-bottom:24px;color:var(--muted);font-size:12px;font-style:italic;text-align:center;">
        Noch keine Picks mit Sharp-Move-Trigger oder hoher Conviction. Wird sichtbar sobald Pinnacle bewegt oder Signal-Setup ≥7/10 erreicht.
      </div>`;
  }
  watch.sort((a, b) => (b.pick.convictionScore || 0) - (a.pick.convictionScore || 0));
  const rows = watch.slice(0, 12).map(item => {
    const p = item.pick;
    const conv = typeof p.convictionScore === 'number' ? p.convictionScore : null;
    const convBadge = conv !== null
      ? `<span style="font-family:ui-monospace,monospace;font-size:11px;padding:2px 8px;border-radius:5px;font-weight:700;background:${conv >= 8 ? 'rgba(0,212,161,0.20)' : 'rgba(125,211,252,0.20)'};color:${conv >= 8 ? '#00d4a1' : '#7dd3fc'};">${conv}/10</span>`
      : '';
    const sharpBadge = p.sharpMoveActive
      ? `<span style="font-size:10px;padding:2px 6px;border-radius:4px;background:rgba(248,81,73,0.20);color:#f85149;font-weight:700;">🔥 Sharp-Move</span>`
      : '';
    const sm = p.sharpMoveDetails;
    const smDetails = sm
      ? `<div style="font-size:11px;color:var(--muted);margin-top:2px;">Pinnacle ${sm.open_pinn_odds ? sm.open_pinn_odds.toFixed(2) : '?'} → ${sm.current_pinn_odds ? sm.current_pinn_odds.toFixed(2) : '?'} · ${sm.soft_lag_pp ? `Soft +${sm.soft_lag_pp.toFixed(1)}pp dahinter` : 'Bewegt'}</div>`
      : '';
    return `<a href="matches/wm-match-v2.html?m=wm-${item.fixture.home.toLowerCase()}-vs-${item.fixture.away.toLowerCase()}-${item.fixture.date}" style="display:block;padding:10px 14px;border-bottom:1px solid var(--border);text-decoration:none;color:var(--text);">
      <div style="display:flex;align-items:center;gap:10px;justify-content:space-between;flex-wrap:wrap;">
        <div style="display:flex;align-items:center;gap:8px;font-size:13px;">
          <span>${item.home.flag} ${item.home.name}</span>
          <span style="color:var(--muted);">vs</span>
          <span>${item.away.flag} ${item.away.name}</span>
        </div>
        <div style="display:flex;align-items:center;gap:6px;">${sharpBadge}${convBadge}</div>
      </div>
      <div style="font-size:12px;color:var(--accent);font-weight:700;margin-top:4px;">${p.market} @${p.odds ? parseFloat(p.odds).toFixed(2) : '?'} <span style="color:var(--muted);font-weight:400;">· ${p.verdict}${p.edgePP != null ? ` · Edge +${p.edgePP}pp` : ''}</span></div>
      ${smDetails}
    </a>`;
  }).join('');
  return `<div class="section-label" style="margin-bottom:10px;">🎯 Sharp-Money Watchlist · ${watch.length} Picks aktiv</div>
    <div style="background:var(--card);border:1px solid var(--border);border-radius:12px;overflow:hidden;margin-bottom:24px;">
      ${rows}
    </div>`;
}

// Block B — Bayesian-Weights aus signal_weights.json
function _renderBayesianWeights() {
  // Dataset-bewusst (26.06.2026, Lucas): im Liga-Tab die LIGA-Gewichte + nur die liga-aktiven
  // Signale zeigen — sonst standen WM-Signale (Travel/Wetter/Anreiz) fälschlich im Liga-Panel.
  // 13.07.2026: MLS zählt zu den Liga-Signalen (keine WM-Signale wie Travel/Wetter/Anreiz) und
  // hat EIGENE Gewichte (mls_signal_weights.json) — vorher fiel es still auf die WM-Gewichte zurück.
  const _isLiga = (typeof _sharpDataset !== 'undefined') && _sharpIsLigaLike(_sharpDataset);
  const weights = (typeof _sharpDataset !== 'undefined'
    ? window[_sharpMeta(_sharpDataset).weightsGlobal] : null) || {};
  const signalNames = _isLiga ? [
    "lead_lag_bias", "public_static_bias", "injury", "form_trend", "h2h_pattern",
    "xg_strength", "chance_creation", "form_rating", "freshness_leg", "lineup_signal",
    "apif_predictions", "league_pressure", "fixture_congestion", "topscorer_momentum",
    "coach_change", "transfer_shift",
  ] : [
    "lead_lag_bias", "public_static_bias", "travel_burden", "injury",
    "form_trend", "h2h_pattern", "xg_strength", "polymarket_sharp",
    "steam_lag", "pressure_index", "lineup_signal", "apif_predictions",
    "weather_signal", "incentive_signal",
  ];
  const labels = {
    lead_lag_bias: "Sharp-Move (Pinn vs Soft)",
    public_static_bias: "Public-Bias",
    travel_burden: "Travel-Burden",
    injury: "Verletzungen",
    form_trend: "Form-Trend",
    h2h_pattern: "H2H-Pattern",
    xg_strength: "xG-Stärke",
    polymarket_sharp: "Polymarket-Sharp",
    steam_lag: "Steam-Lag (Pinn vs Poly)",
    pressure_index: "Pressure-Index",
    lineup_signal: "Lineup T-1h",
    apif_predictions: "APIF Predictions",
    weather_signal: "Weather/Hitze",
    incentive_signal: "Anreiz-Signal",
    chance_creation: "Chancen-Kreation",
    form_rating: "Form-Rating",
    freshness_leg: "Frische (Pulse)",
    league_pressure: "Liga-Druck",
    fixture_congestion: "Erschöpfung/Spielstau",
    topscorer_momentum: "Top-Torjäger",
    coach_change: "Neuer Trainer",
    transfer_shift: "Schlüssel-Abgang",
  };
  const rows = signalNames.map(name => {
    const w = weights[name] || {};
    const weight = typeof w.weight === 'number' ? w.weight : 1.0;
    const n = w.n_observations || 0;
    const wins = w.wins_when_triggered || 0;
    const hitRate = n > 0 ? Math.round((wins / n) * 100) : null;
    const wCol = weight > 1.1 ? '#3fb950' : weight < 0.9 ? '#f85149' : '#8b949e';
    const wLabel = weight.toFixed(2);
    const hrCell = hitRate !== null
      ? `<span style="color:${hitRate >= 55 ? '#3fb950' : hitRate >= 45 ? '#e3b341' : '#f85149'};font-weight:700;">${hitRate}%</span>`
      : `<span style="color:var(--muted);font-style:italic;">—</span>`;
    return `<tr style="border-top:1px solid var(--border);">
      <td style="padding:8px 12px;font-size:13px;">${labels[name] || name}</td>
      <td style="padding:8px 12px;text-align:right;font-family:ui-monospace,monospace;color:${wCol};font-weight:700;">${wLabel}</td>
      <td style="padding:8px 12px;text-align:right;font-size:12px;color:var(--muted);">${n}</td>
      <td style="padding:8px 12px;text-align:right;font-size:12px;">${hrCell}</td>
    </tr>`;
  }).join('');
  const totalN = signalNames.reduce((sum, name) => sum + ((weights[name] || {}).n_observations || 0), 0);
  const waitMsg = _isLiga
    ? `⏳ Liga-Lern-Loop startet mit Backtest-Prior (Vorsaison) — die Gewichte sind schon vorgewärmt und verschieben sich mit den ersten aufgelösten Liga-Picks.`
    : `⏳ Lern-Loop wartet auf erste resolved WM-Picks. Erst nach ~30 Beobachtungen verschieben sich die Weights spürbar.`;
  const learnState = totalN < 10
    ? `<div style="padding:10px 14px;background:rgba(245,194,90,0.06);border-left:3px solid #f5c25a;font-size:12px;color:#f5c25a;">${waitMsg}</div>`
    : `<div style="padding:10px 14px;background:rgba(0,212,161,0.06);border-left:3px solid #00d4a1;font-size:12px;color:#00d4a1;">✓ Lern-Loop aktiv · ${totalN} Beobachtungen verteilt über alle Signale${_isLiga ? ' (Liga)' : ''}</div>`;
  return `<div class="section-label" style="margin-bottom:10px;">🧠 Bayesian-Lern-Status · was das System gelernt hat</div>
    <div style="background:var(--card);border:1px solid var(--border);border-radius:12px;overflow:hidden;margin-bottom:24px;">
      ${learnState}
      <table style="width:100%;border-collapse:collapse;">
        <thead><tr style="background:rgba(255,255,255,0.02);">
          <th style="padding:10px 12px;text-align:left;font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:0.5px;">Signal</th>
          <th style="padding:10px 12px;text-align:right;font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:0.5px;">Weight</th>
          <th style="padding:10px 12px;text-align:right;font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:0.5px;">n</th>
          <th style="padding:10px 12px;text-align:right;font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:0.5px;">Hit-Rate</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

// ── CLV-Bilanz (28.06.2026, Lucas: „CLV als Nordstern") ──────────────────────
// Lädt {wm_,liga_}clv_summary.json (compute_clv_summary.py) lazy, dataset-aware, re-rendert.
let _clvLoading = { intl: false, liga: false, mls: false };
function _loadClvSummary() {
  // 13.07.2026: datensatz-generisch (vorher `=== 'liga'` → MLS zeigte still die WM-CLV-Bilanz).
  const meta = _sharpMeta(_sharpDataset);
  const gkey = meta.clvGlobal;
  if (window[gkey] !== undefined) return;            // schon geladen (auch {} zählt)
  const lk = _sharpDataset;
  if (_clvLoading[lk]) return;
  _clvLoading[lk] = true;
  const f = meta.clvFile;
  fetch(f + '?t=' + Date.now()).then(r => r.ok ? r.json() : null).catch(() => null)
    .then(j => { window[gkey] = j || {}; })
    .finally(() => { _clvLoading[lk] = false; renderSharpRadar(); });
}

// Scoreboard: Ø CLV + % schlägt Schluss + Abdeckung, dann Schnitt nach Markt/Liga/Zeit.
function _renderClvScoreboard() {
  const s = window[_sharpMeta(_sharpDataset).clvGlobal] || null;
  const head = `<div class="section-label" style="margin-bottom:10px;">🎯 CLV-Bilanz · schlagen wir die Closing-Linie?</div>`;
  const wrap = (inner) => head + `<div style="background:var(--card);border:1px solid var(--border);border-radius:12px;padding:16px;margin-bottom:24px;">${inner}</div>`;

  if (!s || !s.overall) {
    return wrap(`<div style="color:var(--muted);font-size:12px;text-align:center;">CLV-Bilanz wird geladen …</div>`);
  }
  const ov = s.overall;
  const cov = ov.coverage || {};
  if (!ov.n) {
    const hint = cov.resolved
      ? `${cov.resolved} Spiele aufgelöst, aber noch keine Closing-Linie erfasst — Closing-Capture prüfen.`
      : `Noch keine aufgelösten Steam-Picks. Die Bilanz füllt sich, sobald Spiele gelaufen sind.`;
    return wrap(`<div style="color:var(--muted);font-size:12px;text-align:center;line-height:1.6;">${hint}</div>`);
  }

  const clvCol = (v) => v == null ? 'var(--muted)' : v >= 1 ? '#3fb950' : v >= 0 ? '#a8d48a' : '#f85149';
  const beatCol = (v) => v == null ? 'var(--muted)' : v >= 52 ? '#3fb950' : v >= 48 ? '#e3b341' : '#f85149';
  const covCol = (v) => v == null ? 'var(--muted)' : v >= 80 ? '#3fb950' : v >= 50 ? '#e3b341' : '#f85149';
  // BET-Quote: niedrig = scharf selektiert (gut), hoch = zu viele BET (Verwässerungs-Risiko).
  const betCol = (v) => v == null ? 'var(--muted)' : v <= 20 ? '#3fb950' : v <= 35 ? '#e3b341' : '#f85149';
  const pp = (v) => v == null ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(1)}pp`;
  const pct = (v) => v == null ? '—' : `${v.toFixed(0)}%`;
  const br = s.betRate || {};

  const tile = (lbl, val, col, sub) => `<div style="flex:1;min-width:120px;background:var(--bg);border:1px solid var(--border);border-left:3px solid ${col};border-radius:10px;padding:12px 14px;">
    <div style="font-size:20px;font-weight:900;color:${col};line-height:1.1;">${val}</div>
    <div style="font-size:10px;color:var(--muted);margin-top:5px;text-transform:uppercase;letter-spacing:.4px;">${lbl}</div>
    ${sub ? `<div style="font-size:10px;color:var(--muted);margin-top:3px;">${sub}</div>` : ''}</div>`;

  let html = `<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:6px;">
    ${tile('Ø CLV', pp(ov.avgClvPP), clvCol(ov.avgClvPP), 'pro Pick vs Schluss')}
    ${tile('schlägt Schluss', pct(ov.pctBeatClose), beatCol(ov.pctBeatClose), `${ov.n} Picks`)}
    ${tile('Closing-Abdeckung', pct(cov.pct), covCol(cov.pct), `${cov.withClosing}/${cov.resolved}`)}
    ${br.overall != null ? tile('BET-Quote', pct(br.overall), betCol(br.overall), br.counts ? `${br.counts.BET}/${(br.counts.BET + br.counts['ABWÄGEN'])} Picks` : 'Anteil BET') : ''}
  </div>`;
  html += `<div style="font-size:10.5px;color:var(--muted);margin:8px 2px 14px;line-height:1.5;">Positiver Ø CLV = die Linie lief nach unserem Einstieg weiter in Pick-Richtung → wir schlagen den Schluss (zahlt langfristig, unabhängig vom Einzel-Ergebnis).</div>`;

  // Mini-Tabelle pro Schnitt
  const miniTable = (title, entries) => {
    if (!entries.length) return '';
    const rows = entries.map(([k, a]) => `<tr style="border-top:1px solid var(--border);">
      <td style="padding:6px 10px;font-size:12px;">${k}</td>
      <td style="padding:6px 10px;text-align:right;font-family:ui-monospace,monospace;font-weight:700;color:${clvCol(a.avgClvPP)};">${pp(a.avgClvPP)}</td>
      <td style="padding:6px 10px;text-align:right;font-weight:700;color:${beatCol(a.pctBeatClose)};">${pct(a.pctBeatClose)}</td>
      <td style="padding:6px 10px;text-align:right;color:var(--muted);font-size:11px;">${a.n}</td>
    </tr>`).join('');
    return `<div style="margin-top:14px;">
      <div style="font-size:11px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.4px;margin-bottom:4px;">${title}</div>
      <table style="width:100%;border-collapse:collapse;">
        <tr style="font-size:9px;color:var(--muted);text-transform:uppercase;"><td style="padding:2px 10px;"></td><td style="padding:2px 10px;text-align:right;">Ø CLV</td><td style="padding:2px 10px;text-align:right;">schlägt Schluss</td><td style="padding:2px 10px;text-align:right;">n</td></tr>
        ${rows}
      </table></div>`;
  };
  // Pick-Typ-Split (28.06.2026, Lucas): zeigt, dass der Edge im BET-Tier sitzt (ABWÄGEN verwässert).
  const _vOrder = { BET: 0, 'ABWÄGEN': 1 };
  html += miniTable('Nach Pick-Typ', Object.entries(s.byVerdict || {})
    .sort((a, b) => (_vOrder[a[0]] ?? 9) - (_vOrder[b[0]] ?? 9)));
  html += miniTable('Nach Markt', Object.entries(s.byMarket || {}).sort((a, b) => (b[1].n || 0) - (a[1].n || 0)));
  html += miniTable(_sharpIsLigaLike(_sharpDataset) ? 'Nach Liga' : 'Nach Gruppe', Object.entries(s.byLeague || {}).sort((a, b) => (b[1].n || 0) - (a[1].n || 0)));
  html += miniTable('Nach Spieltag', (s.byTime || []).map(b => [b.bucket, b]));

  // BET-Quote pro Liga (Steuerungs-Hebel: nicht zu viele BET bei ~50 Spielen/Runde).
  const _brl = br.byLeague || {};
  const _brEntries = Object.entries(_brl).filter(([, v]) => v != null).sort((a, b) => b[1] - a[1]);
  if (_brEntries.length) {
    html += `<div style="margin-top:14px;font-size:11px;color:var(--muted);">
      <span style="font-weight:700;text-transform:uppercase;letter-spacing:.4px;">BET-Quote pro Liga</span>&nbsp;&nbsp;`
      + _brEntries.map(([k, v]) => `<span style="color:${betCol(v)};font-weight:700;">${k} ${v.toFixed(0)}%</span>`).join(' · ')
      + `</div>`;
  }

  return wrap(html);
}

// Block C — CLV-Aggregation pro Signal-Familie aus wm_results.json
function _renderClvAggregation() {
  const results = window.WM_RESULTS_DATA || null;
  if (!results || !Array.isArray(results.picks) || results.picks.length === 0) {
    return `<div class="section-label" style="margin-bottom:10px;">📈 CLV-Aggregation pro Signal-Familie</div>
      <div style="background:var(--card);border:1px solid var(--border);border-radius:12px;padding:20px;margin-bottom:24px;color:var(--muted);font-size:12px;text-align:center;">
        Aussagekräftig ab ~30 resolved Picks. Voller Inhalt erscheint Mitte/Ende WM. Tracked pro Familie: Avg CLV, Hit-Rate, ROI.
      </div>`;
  }
  const families = {
    sharp_money: { signals: ["lead_lag_bias", "steam_lag", "polymarket_sharp"], picks: [] },
    form:        { signals: ["form_trend", "xg_strength", "h2h_pattern"], picks: [] },
    context:     { signals: ["travel_burden", "injury", "weather_signal", "pressure_index", "incentive_signal"], picks: [] },
    realtime:    { signals: ["lineup_signal"], picks: [] },
    market:      { signals: ["public_static_bias", "apif_predictions"], picks: [] },
  };
  for (const p of results.picks) {
    if (!Array.isArray(p.signals) || p.result == null) continue;
    for (const [famKey, fam] of Object.entries(families)) {
      if (p.signals.some(s => fam.signals.includes(s.name) && (s.score || 0) > 0)) {
        fam.picks.push(p);
      }
    }
  }
  const rows = Object.entries(families).map(([famKey, fam]) => {
    const n = fam.picks.length;
    if (n === 0) {
      return `<tr style="border-top:1px solid var(--border);">
        <td style="padding:8px 12px;font-size:13px;text-transform:capitalize;">${famKey.replace('_', ' ')}</td>
        <td style="padding:8px 12px;text-align:right;color:var(--muted);font-style:italic;">—</td>
        <td style="padding:8px 12px;text-align:right;color:var(--muted);font-style:italic;">—</td>
        <td style="padding:8px 12px;text-align:right;color:var(--muted);font-style:italic;">—</td>
        <td style="padding:8px 12px;text-align:right;color:var(--muted);">0</td>
      </tr>`;
    }
    const wins = fam.picks.filter(p => p.result === 'won').length;
    const hitRate = Math.round((wins / n) * 100);
    const avgClv = fam.picks.reduce((s, p) => s + (p.clvPP || 0), 0) / n;
    const roiSum = fam.picks.reduce((s, p) => {
      const stake = 1;
      const ret = p.result === 'won' ? (parseFloat(p.odds || 1) - 1) * stake : -stake;
      return s + ret;
    }, 0);
    const roi = Math.round((roiSum / n) * 100);
    return `<tr style="border-top:1px solid var(--border);">
      <td style="padding:8px 12px;font-size:13px;text-transform:capitalize;">${famKey.replace('_', ' ')}</td>
      <td style="padding:8px 12px;text-align:right;font-family:ui-monospace,monospace;color:${avgClv >= 1 ? '#3fb950' : avgClv >= 0 ? '#a8d48a' : '#f85149'};font-weight:700;">${avgClv >= 0 ? '+' : ''}${avgClv.toFixed(1)}pp</td>
      <td style="padding:8px 12px;text-align:right;font-weight:700;color:${hitRate >= 55 ? '#3fb950' : hitRate >= 45 ? '#e3b341' : '#f85149'};">${hitRate}%</td>
      <td style="padding:8px 12px;text-align:right;font-weight:700;color:${roi >= 0 ? '#3fb950' : '#f85149'};">${roi >= 0 ? '+' : ''}${roi}%</td>
      <td style="padding:8px 12px;text-align:right;color:var(--muted);font-size:12px;">${n}</td>
    </tr>`;
  }).join('');
  return `<div class="section-label" style="margin-bottom:10px;">📈 CLV-Aggregation pro Signal-Familie</div>
    <div style="background:var(--card);border:1px solid var(--border);border-radius:12px;overflow:hidden;margin-bottom:24px;">
      <table style="width:100%;border-collapse:collapse;">
        <thead><tr style="background:rgba(255,255,255,0.02);">
          <th style="padding:10px 12px;text-align:left;font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:0.5px;">Familie</th>
          <th style="padding:10px 12px;text-align:right;font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:0.5px;">Avg CLV</th>
          <th style="padding:10px 12px;text-align:right;font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:0.5px;">Hit-Rate</th>
          <th style="padding:10px 12px;text-align:right;font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:0.5px;">ROI</th>
          <th style="padding:10px 12px;text-align:right;font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:0.5px;">n</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

// (26.06.2026, Lucas: Sharp Radar Liga-Toggle) — Modul-State: welcher Datensatz
// wird im Sharp-Radar-Tab gezeigt. 'intl' = WM (window.WM2026_DATA/_ODDS_HISTORY),
// 'liga'/'mls' = derselbe Radar auf Liga-/MLS-Daten (identisches Format).
//
// 18.07.2026 (Lucas): Einstieg ist jetzt LIGA statt WM. Die WM endet mit dem Finale am
// 19.07. — danach wäre der Default eine Fläche ohne kommende Spiele, und der aktive
// Datensatz läge immer einen Klick entfernt. WM bleibt über den Toggle erreichbar.
// ⚠️ Liga-Daten werden LAZY geladen: der Default-Wechsel allein reicht nicht, der
// Erstaufruf muss den Ladevorgang selbst anstoßen (siehe renderSharpRadar) — sonst
// hängt der Tab dauerhaft im „kommt mit dem nächsten Liga-Lauf"-Zustand fest.
let _sharpDataset = 'liga';

// (26.06.2026, Lucas: Sharp Radar Liga-Toggle) — Liga-Daten EINMALIG lazy laden
// und in window.LIGA_DATA / window.LIGA_ODDS_HISTORY cachen. Danach re-render.
// Schlägt ein Fetch fehl (Datei noch nicht da → kommt mit dem nächsten Liga-Lauf),
// bleibt der Wert leer; renderSharpRadar zeigt dann einen freundlichen Hinweis.
let _sharpLigaLoading = false;
function _loadLigaSharpData() {
  if (_sharpLigaLoading) return;
  if (window.LIGA_DATA && window.LIGA_ODDS_HISTORY) return;  // schon geladen
  _sharpLigaLoading = true;
  Promise.all([
    (window.LIGA_DATA ? Promise.resolve(window.LIGA_DATA)
      : fetch('liga-data.json?t=' + Date.now()).then(r => r.ok ? r.json() : null).catch(() => null)),
    (window.LIGA_ODDS_HISTORY ? Promise.resolve(window.LIGA_ODDS_HISTORY)
      : fetch('liga-odds-history.json?t=' + Date.now()).then(r => r.ok ? r.json() : null).catch(() => null)),
    (window.LIGA_SIGNAL_WEIGHTS ? Promise.resolve(window.LIGA_SIGNAL_WEIGHTS)
      : fetch('liga_signal_weights.json?t=' + Date.now()).then(r => r.ok ? r.json() : null).catch(() => null)),
    // 29.06.2026 (Lucas: MLS „wie die anderen Ligen") — MLS-Moves in den Liga-Radar mit-mergen.
    fetch('mls-data.json?t=' + Date.now()).then(r => r.ok ? r.json() : null).catch(() => null),
    fetch('mls-odds-history.json?t=' + Date.now()).then(r => r.ok ? r.json() : null).catch(() => null),
    // 13.07.2026: MLS hat EIGENE Signal-Gewichte — ohne die zeigte der MLS-Radar die WM-Gewichte.
    fetch('mls_signal_weights.json?t=' + Date.now()).then(r => r.ok ? r.json() : null).catch(() => null),
  ]).then(([ld, lh, lw, md, mh, mw]) => {
    window.LIGA_DATA           = ld || {};
    window.LIGA_ODDS_HISTORY   = lh || {};
    window.LIGA_SIGNAL_WEIGHTS = lw || {};
    window.MLS_SIGNAL_WEIGHTS  = mw || {};
    // MLS-Gruppen/Odds dazumischen (kollisionsfrei: Gruppe „MLS", Fixture-Keys „MLS-…").
    if (md && md.groups) {
      window.LIGA_DATA.groups = Object.assign({}, window.LIGA_DATA.groups || {}, md.groups);
      if (md.odds) window.LIGA_DATA.odds = Object.assign({}, window.LIGA_DATA.odds || {}, md.odds);
    }
    if (mh) window.LIGA_ODDS_HISTORY = Object.assign({}, window.LIGA_ODDS_HISTORY || {}, mh);
  }).catch(() => {
    window.LIGA_DATA         = window.LIGA_DATA || {};
    window.LIGA_ODDS_HISTORY = window.LIGA_ODDS_HISTORY || {};
  }).finally(() => {
    _sharpLigaLoading = false;
    // 13.07.2026 BUG: hier stand nur `=== 'liga'`. Beim neuen MLS-Toggle lud der Fetch zwar sauber,
    // löste danach aber KEIN Re-Render aus → das Panel blieb ewig auf „⚽ Liga-Sharp-Daten werden
    // geladen …" stehen (Lucas: „MLS-Daten werden im Sharp Radar nicht geladen" — sie WAREN geladen,
    // nur nie gezeichnet). Jeder Liga-artige Datensatz muss hier neu zeichnen.
    if (_sharpIsLigaLike(_sharpDataset)) renderSharpRadar();
  });
}

// (26.06.2026, Lucas: Sharp Radar Liga-Toggle) — Toggle-Leiste „🌍 International" /
// „⚽ Liga" als HTML-String, der oben in den Radar-Output eingehängt wird. Aktiver
// Button hervorgehoben (Muster wie der Status-Tab-Toggle in status-checks.js).
function _sharpRenderToggleHtml() {
  const btn = (ds, label) => {
    const on = _sharpDataset === ds;
    const col = on ? 'var(--text)' : 'var(--muted)';
    const bg  = on ? 'var(--card2, rgba(255,255,255,0.06))' : 'transparent';
    const bd  = on ? 'var(--text)' : 'var(--border)';
    return `<button onclick="_sharpSetDataset('${ds}')" style="background:${bg};border:1px solid ${bd};color:${col};border-radius:8px;padding:8px 16px;font-size:13px;font-weight:${on ? 700 : 600};cursor:pointer;font-family:inherit;${on ? 'box-shadow:0 0 0 1px var(--text) inset;' : ''}">${label}</button>`;
  };
  // 13.07.2026 (Lucas: „der Sharp Radar hat noch kein MLS, nur Liga"). MLS war zwar drin —
  // aber in den Liga-Toggle GEMERGT und damit unsichtbar. Eigener Button. Neue Liga später:
  // Eintrag in SHARP_SUBSETS + ein btn(...) hier.
  // 18.07.2026: Reihenfolge folgt dem Einstieg — Top-5 zuerst, WM ans Ende (nach dem Finale
  // am 19.07. Archiv). Der Datensatz mit laufenden Spielen steht vorn.
  return `<div id="sharp_datasetToggle" style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap;">`
    + btn('liga', '⚽ Top-5') + btn('mls', '🇺🇸 MLS') + btn('intl', '🌍 International')
    + `</div>`;
}

// Welche Gruppen gehören zu welchem Radar-Datensatz? MLS und die Top-5 liegen gemeinsam in
// window.LIGA_DATA (ein Fetch), werden hier aber sauber getrennt angezeigt.
//   liga → alles AUSSER MLS · mls → nur MLS
const SHARP_SUBSETS = { liga: g => g !== 'MLS', mls: g => g === 'MLS' };

// „Liga-artig" = liest window.LIGA_DATA (Top-5 UND MLS liegen dort gemeinsam), im Gegensatz zu
// 'intl' (WM-Globals). 13.07.2026: Vorher stand `=== 'liga'` an DREI Stellen verstreut — beim
// Einbau des MLS-Toggles habe ich eine davon übersehen (den Re-Render nach dem Lazy-Load), und
// der MLS-Radar hing für immer im Lade-Zustand. Eine Funktion, ein Ort, kein Vergessen mehr.
// Neuer Datensatz = Eintrag in SHARP_SUBSETS, sonst nichts.
function _sharpIsLigaLike(ds) { return Object.prototype.hasOwnProperty.call(SHARP_SUBSETS, ds); }

// Pro Radar-Datensatz: wo liegen Signal-Gewichte und CLV-Bilanz? MLS hat EIGENE Dateien
// (mls_signal_weights.json / mls_clv_summary.json) — vorher fiel der MLS-Tab still auf die
// WM-Gewichte und die WM-CLV-Bilanz zurück, weil überall `=== 'liga'` geprüft wurde.
// Neuer Datensatz = eine Zeile hier.
const SHARP_DS_META = {
  intl: { clvFile: 'wm_clv_summary.json',   clvGlobal: 'WM_CLV_SUMMARY',   weightsGlobal: 'SIGNAL_WEIGHTS'      },
  liga: { clvFile: 'liga_clv_summary.json', clvGlobal: 'LIGA_CLV_SUMMARY', weightsGlobal: 'LIGA_SIGNAL_WEIGHTS' },
  mls:  { clvFile: 'mls_clv_summary.json',  clvGlobal: 'MLS_CLV_SUMMARY',  weightsGlobal: 'MLS_SIGNAL_WEIGHTS'  },
};
function _sharpMeta(ds) { return SHARP_DS_META[ds] || SHARP_DS_META.intl; }

// Datensatz auf die gewünschten Gruppen zuschneiden — inkl. passender History (nur die Fixture-
// Keys der behaltenen Gruppen), sonst rechnet der Radar Mover aus Spielen, die gar nicht sichtbar sind.
function _sharpSliceData(data, hist, ds) {
  const keep = SHARP_SUBSETS[ds];
  if (!keep || !data || !data.groups) return { data, hist };
  const groups = {};
  const keys = new Set();
  for (const [gid, grp] of Object.entries(data.groups)) {
    if (!keep(gid)) continue;
    groups[gid] = grp;
    for (const fx of (grp.fixtures || [])) keys.add(`${fx.home}-${fx.away}`);
  }
  const odds = {};
  for (const [k, v] of Object.entries(data.odds || {})) if (keys.has(k)) odds[k] = v;
  const h = {};
  for (const [k, v] of Object.entries(hist || {})) if (k === '_meta' || keys.has(k)) h[k] = v;
  return { data: Object.assign({}, data, { groups, odds }), hist: h };
}

// (26.06.2026, Lucas: Sharp Radar Liga-Toggle) — Klick-Handler (global, da via inline
// onclick aufgerufen). Setzt den Datensatz, triggert ggf. den Liga-Lazy-Load und
// rendert neu. WM/Intl-Pfad bleibt davon unberührt.
function _sharpSetDataset(ds) {
  if (ds === _sharpDataset) return;
  _sharpDataset = ds;
  // 13.07.2026: 'mls' liest dieselben Liga-Globals (MLS ist dort mit-gemergt) → gleicher Lazy-Load.
  if (_sharpIsLigaLike(ds)) _loadLigaSharpData();
  renderSharpRadar();
}
if (typeof window !== 'undefined') window._sharpSetDataset = _sharpSetDataset;

// (26.06.2026, Lucas: „Sharp Radar soll aktuelle Liga-Linien auch OHNE Bewegung zeigen")
// Solange keine Linie über ≥2 Snapshots wandert (6 Wochen vor Saison = statisch), gibt es keine
// Steam-Moves zu zeigen. Statt „kommt bald" rendern wir die aktuellen Pinnacle-/Soft-1X2-Linien
// der bepreisten, anstehenden Spiele als Tabelle. Reiner View aus data.odds + data.groups.
function _renderLigaCurrentLinesHtml(data) {
  const odds = (data && data.odds) || {};
  const groups = (data && data.groups) || {};
  const meta = {};
  for (const g of Object.values(groups)) {
    const names = {};
    for (const t of (g.teams || [])) names[String(t.id)] = t.name || t.id;
    for (const fx of (g.fixtures || [])) {
      const played = ['FT', 'AET', 'PEN'].includes(String((fx.result || {}).status || '').toUpperCase());
      meta[`${fx.home}-${fx.away}`] = {
        home: names[String(fx.home)] || fx.homeName || fx.home,
        away: names[String(fx.away)] || fx.awayName || fx.away,
        date: fx.date, md: fx.matchday, played,
      };
    }
  }
  const rows = [];
  for (const [k, o] of Object.entries(odds)) {
    const m = meta[k];
    if (!m || m.played || !o || !o.hw) continue;
    rows.push({ ...m, o });
  }
  rows.sort((a, b) => String(a.date || '').localeCompare(String(b.date || '')));
  if (!rows.length) return '';
  // Nur die nächsten ~3 Wochen zeigen (sonst wird die Seite bei 5 Ligen × ~10 Spielen/Runde × 38
  // Runden endlos — 26.06.2026, Lucas). Nach Datum sortiert, gedeckelt, Rest als Hinweis.
  const _today = new Date().toISOString().slice(0, 10);
  const _horizon = new Date(Date.now() + 21 * 86400000).toISOString().slice(0, 10);
  const _totalPriced = rows.length;
  let inWindow = rows.filter(r => r.date && r.date >= _today && r.date <= _horizon);
  if (!inWindow.length) inWindow = rows.filter(r => r.date && r.date >= _today).slice(0, 20);
  const CAP = 40;
  const shown = inWindow.slice(0, CAP);
  if (!shown.length) return '';
  const cell = (o, k) => (o[k] != null ? o[k] : '–');
  let h = `<div style="max-width:960px;margin:0 auto;">`;
  h += `<div style="color:var(--muted);font-size:12px;line-height:1.6;margin:6px 0 16px;text-align:center;">📡 Aktuelle Liga-Linien (Pinnacle + Soft-Konsens), nächste 3 Wochen. Noch keine Steam-Bewegung — sobald sich Linien über mehrere Snapshots bewegen, erscheinen hier die Moves.</div>`;
  h += `<table style="width:100%;border-collapse:collapse;font-size:12px;">`
     + `<tr style="color:var(--muted);text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:.4px;">`
     + `<th style="padding:7px 8px;">Spiel</th><th>Datum</th><th>Pinnacle 1 / X / 2</th><th>Soft 1 / X / 2</th></tr>`;
  for (const r of shown) {
    const p = `${cell(r.o, 'hw')} / ${cell(r.o, 'dr')} / ${cell(r.o, 'aw')}`;
    const hasSoft = r.o.public_hw || r.o.public_dr || r.o.public_aw;
    const s = hasSoft ? `${cell(r.o, 'public_hw')} / ${cell(r.o, 'public_dr')} / ${cell(r.o, 'public_aw')}` : '–';
    const dStr = (r.date && /^\d{4}-\d{2}-\d{2}$/.test(r.date))
      ? `${r.date.slice(8,10)}.${r.date.slice(5,7)}.` : (r.md != null ? `ST ${r.md}` : '');
    h += `<tr style="border-top:1px solid var(--border);">`
       + `<td style="padding:7px 8px;color:var(--text);">${r.home} – ${r.away}</td>`
       + `<td style="color:var(--muted);white-space:nowrap;">${dStr}</td>`
       + `<td style="color:var(--text);">${p}</td>`
       + `<td style="color:var(--muted);">${s}</td></tr>`;
  }
  h += `</table>`;
  if (_totalPriced > shown.length) {
    h += `<div style="color:var(--muted);font-size:11px;text-align:center;margin-top:10px;">+ ${_totalPriced - shown.length} weitere bepreiste Spiele außerhalb der nächsten 3 Wochen (erscheinen, sobald sie näher rücken).</div>`;
  }
  h += `</div>`;
  return h;
}

// ── Platzhalter-Quoten erkennen (13.07.2026) ────────────────────────────────
// Spiegelbild von odds_plausibility.py — die Regel muss auf BEIDEN Seiten gleich sein, sonst
// zeigt das Frontend Mover, die das Backend längst verworfen hat (oder umgekehrt).
// Ein echter 1X2-Markt: keine Quote < 1.05, Remis ≥ 1.50, Overround 100–130 %.
// Platzhalter der Quellen-API beim Opening (1.04/1.01/1.04 → 291 %) erzeugen sonst Geister-Moves.
function _sharpPlausible1x2(hw, dr, aw) {
  if (!hw || !dr || !aw) return false;
  if (hw < 1.05 || aw < 1.05 || dr < 1.5) return false;
  const orr = 1 / hw + 1 / dr + 1 / aw;
  return orr >= 1.0 && orr <= 1.30;
}
// Teil-Snapshots (kein volles 1X2) bleiben drin — dort ist die Marge nicht prüfbar.
function _sharpSnapOk(s) {
  if (!s || typeof s !== 'object') return false;
  if (!(s.hw && s.dr && s.aw)) return true;
  return _sharpPlausible1x2(s.hw, s.dr, s.aw);
}
function _sharpCleanSnaps(snaps) {
  return Array.isArray(snaps) ? snaps.filter(_sharpSnapOk) : [];
}

function renderSharpRadar() {
  const mc = document.getElementById('mainContent');

  // (26.06.2026, Lucas: Sharp Radar Liga-Toggle) — Datensatz-Aliase. Im Default
  // ('intl') exakt das bisherige WM-Verhalten (_data=window.WM2026_DATA). Im Liga-
  // Modus aus den separat geladenen Liga-Globals (identisches JSON-Format).
  // 13.07.2026: 'mls' verhält sich wie 'liga' (gleiche Globals), zeigt aber NUR die MLS-Gruppe.
  const _isLiga = _sharpIsLigaLike(_sharpDataset);
  const _raw  = _isLiga ? (window.LIGA_DATA || {}) : window.WM2026_DATA;
  const _rawH = _isLiga ? (window.LIGA_ODDS_HISTORY || {}) : window.WM2026_ODDS_HISTORY;
  const _sliced = _isLiga ? _sharpSliceData(_raw, _rawH, _sharpDataset) : { data: _raw, hist: _rawH };
  const _data = _sliced.data;
  const _hist = _sliced.hist;

  // (26.06.2026, Lucas: Sharp Radar Liga-Toggle) — Liga-Daten noch nicht da/leer?
  // Freundlicher Hinweis statt leerem/kaputtem Radar. liga-odds-history.json kommt
  // erst mit dem nächsten Liga-Lauf; liga-data.json ohne History ergibt keine Moves.
  if (_isLiga) {
    // 18.07.2026 — Liga ist jetzt der EINSTIEG, nicht mehr nur ein Toggle-Ziel. Vorher stieß
    // nur _sharpSwitchDataset() den Lazy-Load an; beim Erstaufruf gab es keinen Switch, also
    // wären die Globals leer geblieben und der Tab hätte für immer „kommt mit dem nächsten
    // Liga-Lauf" gezeigt, obwohl die Daten längst da sind. Deshalb hier selbst anstoßen.
    if (!window.LIGA_DATA || !window.LIGA_ODDS_HISTORY) {
      _loadLigaSharpData();     // re-rendert selbst, sobald geladen (setzt _sharpLigaLoading)
    }
    const _histKeys = _hist && typeof _hist === 'object'
      ? Object.keys(_hist).filter(k => k !== '_meta') : [];
    if (_sharpLigaLoading) {
      if (mc) mc.innerHTML = _sharpRenderToggleHtml() +
        `<div style="max-width:960px;margin:0 auto;padding:40px 0;text-align:center;color:var(--muted);font-size:13px;">⚽ Liga-Sharp-Daten werden geladen …</div>`;
      return;
    }
    // Bewegung = irgendein Match mit ≥2 Snapshots. Solange keine da ist (auch wenn History schon
    // Einzel-Snapshots hat), aktuelle Linien zeigen statt leerem Radar / „kommt bald".
    const _hasMoves = _histKeys.some(k => Array.isArray(_hist[k]) && _hist[k].length >= 2);
    if (!_hasMoves) {
      const _cur = _renderLigaCurrentLinesHtml(_data);
      if (mc) mc.innerHTML = _sharpRenderToggleHtml() + (_cur ||
        `<div style="max-width:960px;margin:0 auto;padding:40px 24px;text-align:center;color:var(--muted);font-size:13px;line-height:1.6;">⚽ Liga-Linien kommen mit dem nächsten Liga-Lauf.<br><span style="font-size:11px;color:var(--muted);opacity:.8;">Sobald Quoten geholt sind, zeigt der Radar hier die aktuellen Pinnacle-/Soft-Linien und später die Bewegungen.</span></div>`);
      return;
    }
  }

  // ── Helpers ───────────────────────────────────────────────────────────────
  const todayMidnight = new Date(); todayMidnight.setHours(0,0,0,0);
  const _isToday = ds => {
    try { const d = parseGermanDate(ds); d.setHours(0,0,0,0); return d.getTime() === todayMidnight.getTime(); }
    catch { return false; }
  };
  // Format date string "DD.MM.YYYY" → short weekday label "Di 13.5."
  const _fmtDate = ds => {
    try {
      const d = parseGermanDate(ds);
      const days = ['So','Mo','Di','Mi','Do','Fr','Sa'];
      return `${days[d.getDay()]} ${d.getDate()}.${d.getMonth()+1}.`;
    } catch { return ds || ''; }
  };
  const _mvColor = pp => pp >= 8 ? '#f85149' : pp >= 5 ? '#e3b341' : '#3fb950';

  // ── Helpers ──────────────────────────────────────────────────────────────
  // Whether the match has started (kickoff time reached, regardless of 100-min over check)
  const _isKickedOff = (m) => {
    if (!m.date || !m.time) return false;
    try {
      const [d, mo, y] = m.date.split('.');
      const [h, min]   = m.time.split(':');
      return Date.now() >= new Date(+y, +mo - 1, +d, +h, +min, 0).getTime();
    } catch { return false; }
  };
  // Radar-Relevanz (15.06.2026, Lucas): nur handelbare/aktuelle Spiele zeigen.
  // Verstecke definitiv beendete Spiele + alles, was mehr als 1 Tag in der
  // Vergangenheit liegt. Heute + anstehend + gestern (kurzer Rückblick) bleiben.
  // Das Lernen läuft unabhängig über den Bayesian-Loop, nicht über diese Anzeige.
  const _radarRelevant = (m) => {
    if (!m || !m.date) return true;
    if (isMatchOver(m.date, m.time)) return false;
    try {
      const d = parseGermanDate(m.date); d.setHours(0, 0, 0, 0);
      return d.getTime() >= (todayMidnight.getTime() - 24 * 3600 * 1000);
    } catch { return true; }
  };
  // Age of opening snapshot in human-readable form
  const _openAge = (ts) => {
    if (!ts) return null;
    const diffH = Math.round((Date.now() - new Date(ts).getTime()) / 3600000);
    if (diffH < 2)  return '<2h alt';
    if (diffH < 24) return `${diffH}h alt`;
    const diffD = Math.floor(diffH / 24);
    return `${diffD}d alt`;
  };

  // ── Collect ALL fixtures within 7 days across all leagues ─────────────────
  // (26.06.2026, Lucas: Sharp Radar Liga-Toggle) — Diese Schleife zieht die alten
  // LEAGUES-Fixtures + WM-only-Globals (window._preMatchData/findOdds). Im Liga-Modus
  // überspringen: Liga-Moves kommen unten ausschließlich aus _hist (liga-odds-history).
  const allFixtures = [];
  for (const [lk, L] of (_isLiga ? [] : Object.entries(LEAGUES))) {
    for (const m of (L.fixtures || [])) {
      if (!isWithin7Days(m.date)) continue;
      const pmKey        = `${m.home}|${m.away}`;
      const pm           = window._preMatchData?.[pmKey];
      const oddsOpen     = pm?.odds_open    || null;
      const oddsClosing  = pm?.odds_closing || null;
      const openTs       = pm?.odds_open_ts || null;
      const kicked       = _isKickedOff(m);
      // For kicked-off games use closing snapshot; for upcoming games use live odds
      const oddsRef      = kicked ? oddsClosing : ((typeof findOdds === 'function') ? findOdds(lk, m.home, m.away) : null);
      const oddsCurrent  = kicked ? ((typeof findOdds === 'function') ? findOdds(lk, m.home, m.away) : null) : oddsRef;
      const mvRows       = (oddsOpen && oddsRef) ? computeLineMovement(oddsOpen, oddsRef) : null;
      const maxMov       = mvRows ? Math.max(...mvRows.map(r => Math.abs(r.ppShift))) : 0;
      allFixtures.push({ m, lk, L, pm, oddsOpen, oddsClosing, oddsCurrent, oddsRef, openTs, kicked, mvRows, maxMov });
    }
  }

  // ── WM 2026 / Liga: Add fixtures from odds-history ────────────────────────
  // (26.06.2026, Lucas: Sharp Radar Liga-Toggle) — _data/_hist statt der WM-Globals
  // direkt; im Default ('intl') 1:1 wie bisher (window.WM2026_DATA/_ODDS_HISTORY).
  const _wmSharpData = _data;
  // (28.06.2026, Lucas: „riesige Drops, die es so nicht gab") — In-Play-Snapshots wurden in die
  // History geschrieben (Tor → Quote schießt Richtung Spielstand) und verfälschten als „Closing"
  // ALLE Sharp-Radar-Sektionen (Mover/Heatmap/KPI/Verlauf/Gesamtbewegung). ZENTRAL filtern: pro
  // Match nur Snapshots bis zum Anpfiff. Fallback: alle (falls kickoff fehlt/alle post-ko).
  const _hist0 = _hist || {};
  const _koByKey = {};
  for (const grp of Object.values((_wmSharpData && _wmSharpData.groups) || {})) {
    for (const fx of (grp.fixtures || [])) {
      if (fx.kickoff) _koByKey[`${fx.home}-${fx.away}`] = new Date(String(fx.kickoff).replace('Z', '+00:00')).getTime();
    }
  }
  for (const kf of ((_wmSharpData && _wmSharpData.koFixtures) || [])) {
    if (kf.kickoff && kf.home && kf.away) _koByKey[`${kf.home}-${kf.away}`] = new Date(String(kf.kickoff).replace('Z', '+00:00')).getTime();
  }
  const _preHist = {};
  for (const [k, snaps] of Object.entries(_hist0)) {
    if (k === '_meta' || !Array.isArray(snaps)) { _preHist[k] = snaps; continue; }
    // 13.07.2026 (Lucas: „schau dir den Sharp Radar nochmal an"): Platzhalter-Snapshots raus,
    // BEVOR irgendetwas gerechnet wird. Die MLS-History eröffnete mit 1.04/1.01/1.04 (Overround
    // 291 %) — daraus wurden Geister-Mover („PSG 1.02 → 1.40, +37pp") und 80pp-„Steam".
    // Ein echter 1X2-Markt hat 102–110 % Marge. Spiegelt odds_plausibility.py (Python-Seite).
    const clean = _sharpCleanSnaps(snaps);
    const base  = clean.length ? clean : [];
    const ko = _koByKey[k];
    if (!ko) { _preHist[k] = base; continue; }
    const pre = base.filter(s => s && s.ts && new Date(s.ts).getTime() <= ko);
    _preHist[k] = pre.length ? pre : base;   // Fallback: nie leer machen
  }
  _sharpActiveHist = _preHist;   // Mini-Sparkline + Letzte-Bewegung lesen daraus
  const _wmOddsHist  = _preHist;
  if (_wmSharpData && _wmOddsHist) {
    // Build team lookup table
    const _wmTeams = {};
    for (const grp of Object.values(_wmSharpData.groups || {})) {
      for (const t of (grp.teams || [])) _wmTeams[t.id] = t;
    }
    const now = Date.now();
    const WM_WINDOW_MS = 60 * 24 * 3600 * 1000;  // show up to 60 days ahead
    for (const grp of Object.values(_wmSharpData.groups || {})) {
      for (const fx of (grp.fixtures || [])) {
        const matchKey  = `${fx.home}-${fx.away}`;
        const snapshots = _wmOddsHist[matchKey];
        if (!snapshots || snapshots.length < 1) continue;
        // Date filter: -7 days to +60 days (covers full tournament)
        const fxDate = new Date(`${fx.date}T00:00:00`);
        if (fxDate < new Date(now - 7 * 86400000) || fxDate > new Date(now + WM_WINDOW_MS)) continue;
        const oddsOpen    = snapshots[0];                          // _wmOddsHist ist bereits pre-match-gefiltert
        const oddsCurrent = snapshots[snapshots.length - 1];       // (zentral, s. _preHist oben) → kein In-Play
        const openTs      = snapshots[0].ts;
        // Convert ISO date (YYYY-MM-DD) → DD.MM.YYYY for existing helpers
        const [yr, mo, dy] = fx.date.split('-');
        const dateDE = `${dy}.${mo}.${yr}`;
        const homeT  = _wmTeams[fx.home] || { name: fx.home, flag: '🏳' };
        const awayT  = _wmTeams[fx.away] || { name: fx.away, flag: '🏳' };
        const mFake  = { date: dateDE, time: fx.time || '', home: `${homeT.flag} ${homeT.name}`, away: `${awayT.flag} ${awayT.name}` };
        const kicked = _isKickedOff(mFake);
        const mvRows = snapshots.length >= 2 ? computeLineMovement(oddsOpen, oddsCurrent) : null;
        const maxMov = mvRows ? Math.max(...mvRows.map(r => Math.abs(r.ppShift))) : 0;
        allFixtures.push({
          m: mFake, lk: 'WM2026', L: { name: '🌍 WM 2026', flag: '🌍' },
          pm: null, oddsOpen, oddsClosing: null, oddsCurrent,
          oddsRef: oddsCurrent, openTs, kicked, mvRows, maxMov,
          snaps: snapshots   // (28.06.2026) für Snapshot-Dichte-KPI (Datenfrische sichtbar machen)
        });
      }
    }
  }

  // ── Section 1: KPIs (full week) ───────────────────────────────────────────
  const upcoming      = allFixtures.filter(f => !f.kicked);
  const withOdds      = allFixtures.filter(f => f.oddsCurrent != null);
  const withMovement  = allFixtures.filter(f => f.mvRows != null);
  const closedWithMv  = allFixtures.filter(f => f.kicked && f.mvRows != null);
  const biggestMover  = [...allFixtures].sort((a,b) => b.maxMov - a.maxMov)[0];

  let vigSum = 0, vigCount = 0;
  for (const {oddsCurrent: o} of withOdds) {
    if (o?.hw && o?.dr && o?.aw && o.hw > 1 && o.dr > 1 && o.aw > 1) {
      vigSum += (1/o.hw + 1/o.dr + 1/o.aw - 1) * 100;
      vigCount++;
    }
  }
  const avgVig = vigCount ? (vigSum / vigCount).toFixed(1) : '—';

  // Snapshot-Dichte (28.06.2026, abgeschaut bei SteamWatch): wie viele Pinnacle-Snapshots haben
  // wir erfasst? Macht sichtbar, dass die 15-min-Erfassung wirklich live ist. Heute + Fenster gesamt.
  let snapTotal = 0, snapToday = 0;
  const _todayStr = new Date().toISOString().slice(0, 10);
  for (const f of allFixtures) {
    if (!Array.isArray(f.snaps)) continue;
    snapTotal += f.snaps.length;
    for (const s of f.snaps) {
      if (s && typeof s.ts === 'string' && s.ts.slice(0, 10) === _todayStr) snapToday++;
    }
  }

  const bigMoverLabel = biggestMover && biggestMover.maxMov > 0
    ? `${biggestMover.m.home.split(' ').slice(-1)[0]} – ${biggestMover.m.away.split(' ').slice(-1)[0]}: ${biggestMover.maxMov}pp`
    : '—';

  // KPI semantic left-border colors
  const mvRate      = allFixtures.length > 0 ? (withMovement.length / allFixtures.length * 100) : 0;
  const mvRateCol   = mvRate >= 5 ? '#f85149' : mvRate >= 2 ? '#e3b341' : '#3fb950';
  const bigMoverPP  = biggestMover?.maxMov || 0;
  const bigMoverCol = bigMoverPP >= 4 ? '#f85149' : bigMoverPP >= 2 ? '#e3b341' : '#3fb950';
  const kpiCards = [
    { ic: '📅', lbl: 'Spiele gesamt',    val: allFixtures.length + ' (7 Tage)', col: '#484f58', sub: '' },
    { ic: '⏳', lbl: 'Bevorstehend',     val: upcoming.length + ' offen',       col: '#484f58', sub: '' },
    { ic: '📡', lbl: 'Mit Linienbeweg.', val: withMovement.length + ' Spiele',  col: mvRateCol, sub: mvRate.toFixed(1) + '% aller Spiele' },
    { ic: '🔒', lbl: 'Closing-Daten',    val: closedWithMv.length + ' gespielt',col: '#484f58', sub: '' },
    { ic: '⚡', lbl: 'Größter Mover',    val: bigMoverLabel,                     col: bigMoverCol, sub: bigMoverPP >= 4 ? '→ ACT' : bigMoverPP >= 2 ? '→ WATCH' : '' },
    { ic: '📸', lbl: 'Snapshots',        val: snapTotal.toLocaleString('de-AT'), col: snapToday > 0 ? '#3fb950' : '#484f58', sub: snapToday > 0 ? snapToday.toLocaleString('de-AT') + ' heute · live' : 'Erfassung alle 15 Min' },
  ];
  const kpiHtml = `<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:20px;">
    ${kpiCards.map(({ic, lbl, val, col, sub}) => `<div style="background:var(--card);border:1px solid var(--border);border-left:3px solid ${col};border-radius:10px;padding:13px 15px;">
      <div style="font-size:20px;margin-bottom:5px;">${ic}</div>
      <div style="font-size:16px;font-weight:900;color:var(--text);line-height:1.2;">${val}</div>
      <div style="font-size:10px;color:var(--muted);margin-top:4px;text-transform:uppercase;letter-spacing:.4px;">${lbl}</div>
      ${sub ? `<div style="font-size:10px;font-weight:700;color:${col};margin-top:4px;">${sub}</div>` : ''}
    </div>`).join('')}
  </div>`;

  // ── Section 2: Biggest Movers (all week, with date + movement type label) ──
  // Anti-Drift-Fix 09.06.2026:
  //  · Conviction-Picks zuerst (höhere Conviction zuerst), dann nach maxMov
  //  · Conviction-Badge + Sharp-Move-Indikator + Klickbar zur Event-Page
  //  · Sparkline + "Letzte Bewegung"-Indikator für Aktualitäts-Signal
  const movers = allFixtures
    .filter(f => f.mvRows && f.maxMov >= 3 && _radarRelevant(f.m))
    .map(f => {
      // Add Conviction info for WM-fixtures (m.home / m.away sind IDs bei WM)
      const conv = _findBestConvictionForMatch(f.m.home, f.m.away);
      return { ...f, conviction: conv };
    })
    .sort((a, b) => {
      // 1) Picks mit Conviction ≥6 zuerst (nach Score absteigend)
      const aC = a.conviction?.score || 0;
      const bC = b.conviction?.score || 0;
      const aRelevant = aC >= 6 ? 1 : 0;
      const bRelevant = bC >= 6 ? 1 : 0;
      if (aRelevant !== bRelevant) return bRelevant - aRelevant;
      if (aRelevant && bRelevant && aC !== bC) return bC - aC;
      // 2) Sharp-Move-Picks zuerst innerhalb gleichem Conviction-Bucket
      const aS = a.conviction?.sharpMoveActive ? 1 : 0;
      const bS = b.conviction?.sharpMoveActive ? 1 : 0;
      if (aS !== bS) return bS - aS;
      // 3) Tie-break nach maxMov
      return b.maxMov - a.maxMov;
    })
    .slice(0, 20);

  const moversHtml = movers.length ? movers.map(({m, lk, L, mvRows, maxMov, kicked, openTs, oddsClosing, conviction}) => {
    const maxColor  = _mvColor(maxMov);
    const dateLabel = _fmtDate(m.date);
    const timeLabel = m.time ? ` · ${m.time}` : '';
    const isT       = _isToday(m.date);

    // Label: show if we're comparing to closing or live odds, and opening age
    const ageLabel  = _openAge(openTs);
    const snapLabel = kicked
      ? `<span style="font-size:9px;padding:1px 5px;border-radius:4px;background:rgba(88,166,255,0.12);color:#58a6ff;border:1px solid #58a6ff30;">Opening→Closing</span>`
      : `<span style="font-size:9px;padding:1px 5px;border-radius:4px;background:rgba(255,255,255,0.05);color:#8b949e;border:1px solid #30363d;">Opening→Aktuell</span>`;
    const ageBadge  = ageLabel
      ? `<span style="font-size:9px;color:${ageLabel.includes('<2h') ? '#f85149' : ageLabel.includes('1d') || ageLabel.includes('2d') ? '#e3b341' : '#6b7a8d'};padding:1px 5px;" title="Opening-Snapshot Alter">⏱ ${ageLabel}</span>`
      : '';

    // ── WM-Check: ist das ein WM-Match? (→ Sparkline + Event-Page-Link) ──
    // (26.06.2026, Lucas: Sharp Radar Liga-Toggle) — _hist statt WM-Global; im
    // Liga-Modus zeigt das die Liga-History, im Intl-Modus exakt wie bisher.
    const isWm = lk === 'wm2026' || (_hist && _hist[`${m.home}-${m.away}`]);

    const rowHtml = mvRows.map(row => {
      const backed     = row.ppShift > 0;
      const color      = backed ? '#3fb950' : '#f85149';
      const arrow      = row.oddCurr < row.oddOpen ? '↘' : '↗';
      const movBadge   = Math.abs(row.ppShift) >= 3
        ? `<span style="font-size:9px;font-weight:800;padding:1px 5px;border-radius:4px;background:${backed ? 'rgba(63,185,80,0.15)' : 'rgba(248,81,73,0.12)'};color:${color};border:1px solid ${color}40;">${backed ? '↑ Markt' : '↓ Markt'}</span>`
        : '';
      // Mini-Sparkline für WM-Matches (zeigt visuell die Bewegung über Zeit)
      const spark = isWm && row.key ? _wmMiniSparkline(m.home, m.away, row.key, 55, 14) : '';
      // "Letzte Bewegung vor X" — Aktualitäts-Signal
      const last = isWm && row.key ? _lastChangeAgo(m.home, m.away, row.key) : null;
      const lastBadge = last
        ? `<span style="font-size:9px;color:${last.mins < 360 ? '#3fb950' : last.mins < 1440 ? '#e3b341' : '#6b7a8d'};" title="Letzte Bewegung dieses Marktes">${last.label}</span>`
        : '';
      return `<span style="display:inline-flex;align-items:center;gap:5px;background:rgba(255,255,255,0.04);border:1px solid #30363d;border-radius:5px;padding:2px 7px;font-size:11px;white-space:nowrap;">
        <span style="color:#8b949e;font-weight:700;">${row.label}</span>
        <span style="color:#8b949e;font-size:10px;">${row.oddOpen.toFixed(2)}→</span>
        <span style="color:${color};font-weight:700;">${row.oddCurr.toFixed(2)} ${arrow}</span>
        ${spark}
        <span style="color:${color};font-size:10px;">${row.ppShift > 0 ? '+' : ''}${row.ppShift}pp</span>
        ${movBadge}
        ${lastBadge}
      </span>`;
    }).join('');

    // Conviction-Badge (rechts neben maxMov-Pille)
    const convBadge = conviction && conviction.score >= 6
      ? `<span style="font-family:ui-monospace,monospace;font-size:11px;font-weight:700;padding:2px 8px;border-radius:5px;background:${conviction.score >= 8 ? 'rgba(0,212,161,0.20)' : 'rgba(125,211,252,0.20)'};color:${conviction.score >= 8 ? '#00d4a1' : '#7dd3fc'};" title="${conviction.label || ''} · ${conviction.market || ''}">${conviction.score >= 8 ? '🎯' : '⭐'} ${conviction.score}/10</span>`
      : '';
    const sharpBadge = conviction && conviction.sharpMoveActive
      ? `<span style="font-size:10px;padding:2px 6px;border-radius:4px;background:rgba(248,81,73,0.15);color:#f85149;font-weight:700;">🔥</span>`
      : '';

    // Klickbar wenn WM-Match → Event-Page
    const wrapStart = isWm
      ? `<a href="matches/wm-match-v2.html?m=wm-${m.home.toLowerCase()}-vs-${m.away.toLowerCase()}-${m.date.split('.').reverse().join('-')}" style="display:block;text-decoration:none;color:inherit;background:var(--card);border:1px solid var(--border);border-radius:10px;padding:12px 14px;margin-bottom:8px;transition:border-color .15s;" onmouseover="this.style.borderColor='rgba(0,212,161,0.45)'" onmouseout="this.style.borderColor='var(--border)'">`
      : `<div style="background:var(--card);border:1px solid var(--border);border-radius:10px;padding:12px 14px;margin-bottom:8px;">`;
    const wrapEnd = isWm ? `</a>` : `</div>`;

    return `${wrapStart}
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap;">
        <span style="font-size:15px;">${L.flag}</span>
        <span style="font-weight:700;font-size:13px;">${m.home} <span style="color:var(--muted)">vs</span> ${m.away}</span>
        <span style="font-size:10px;font-weight:600;padding:1px 7px;border-radius:8px;background:${isT ? 'rgba(0,212,161,0.12)' : 'rgba(255,255,255,0.05)'};color:${isT ? '#00d4a1' : '#8b949e'};border:1px solid ${isT ? 'rgba(0,212,161,0.3)' : '#30363d'};">${isT ? '📅 Heute' : (kicked ? '🔒 ' : '') + dateLabel}${timeLabel}</span>
        ${snapLabel}${ageBadge}
        ${sharpBadge}${convBadge}
        <span style="margin-left:auto;background:rgba(255,255,255,0.05);border:1px solid ${maxColor}40;border-radius:12px;padding:2px 10px;font-size:11px;font-weight:800;color:${maxColor};">⚡ ${maxMov}pp</span>
      </div>
      <div style="display:flex;gap:5px;flex-wrap:wrap;">${rowHtml}</div>
    ${wrapEnd}`;
  }).join('') : `<div style="padding:24px;text-align:center;color:var(--muted);font-size:13px;">Noch keine signifikante Linienbewegung diese Woche (≥3pp) — Opening-Snapshots werden täglich geladen.</div>`;

  // ── Hero: „Größte Mover" Top-5 (28.06.2026, abgeschaut bei SteamWatch) ────
  // Scanbare Headline ganz oben: gebackte Seite + Quoten-Move % + Open→Jetzt. Rein nach
  // Magnitude (keine Conviction-Sortierung) — der schnelle Überblick vor der Detail-Liste.
  // Sauberer Teamname: <img>-Logos (Liga) UND führende Flag-Emojis (WM) raus → reiner Name.
  // (28.06.2026 Fix: Liga-Namen sind "<img src=...> Chelsea" → alte Variante zerlegte das HTML.)
  const _cleanName = (s) => String(s || '')
    .replace(/<[^>]*>/g, '')                                                    // HTML (Logo-img) raus
    .replace(/^(?:[\u{1F1E6}-\u{1F1FF}\u{2600}-\u{27BF}\u{1F000}-\u{1FAFF}️‍\s]+)/u, '')  // führende Flag/Emoji
    .trim();
  const _sideLabel = (lbl, hn, an) => {
    if (lbl === '1') return hn;
    if (lbl === '2') return an;
    if (lbl === 'X') return 'Remis';
    const num = String(lbl).replace(/\D/g, '').replace('25', '2.5').replace('35', '3.5').replace('15', '1.5');
    if (/^o/i.test(lbl)) return 'Über ' + num;
    if (/^u/i.test(lbl)) return 'Unter ' + num;
    return lbl;
  };
  const heroMovers = allFixtures
    .filter(f => f.mvRows && f.maxMov >= 3 && _radarRelevant(f.m))
    .sort((a, b) => b.maxMov - a.maxMov)
    .slice(0, 5);
  const moversHeroHtml = heroMovers.length ? `
    <div style="background:var(--card);border:1px solid var(--border);border-radius:14px;padding:14px 16px;margin-bottom:22px;">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;flex-wrap:wrap;gap:6px;">
        <span style="font-size:13px;font-weight:900;color:var(--text);">🔥 Größte Mover · Top ${heroMovers.length}</span>
        <span style="font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.4px;">gebackte Seite · Quoten-Move · Open→Jetzt</span>
      </div>
      ${heroMovers.map((f, i) => {
        const hn = _cleanName(f.m.home), an = _cleanName(f.m.away);
        const head = [...f.mvRows].sort((x, y) => y.ppShift - x.ppShift)[0];  // stärkste positive Bewegung = gebackt
        const side = _sideLabel(head.label, hn, an);
        const oddPct = head.oddOpen > 1 ? ((head.oddCurr - head.oddOpen) / head.oddOpen * 100) : 0;
        const dropped = head.oddCurr < head.oddOpen;            // Quote gefallen = Geld auf diese Seite
        const col = dropped ? '#3fb950' : '#f85149';
        const arrow = dropped ? '↓' : '↑';
        const isT = _isToday(f.m.date);
        const dateChip = isT ? '📅 Heute' : (f.kicked ? '🔒 ' : '') + _fmtDate(f.m.date);
        return `<div style="display:flex;align-items:center;gap:10px;padding:8px 4px;${i < heroMovers.length - 1 ? 'border-bottom:1px solid var(--border);' : ''}">
            <span style="font-size:11px;font-weight:900;color:var(--muted);width:18px;flex-shrink:0;">${i + 1}</span>
            <span style="flex:1;min-width:0;font-size:12px;font-weight:700;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${hn} <span style="color:var(--muted);font-weight:400;">vs</span> ${an}</span>
            <span style="font-size:11px;font-weight:800;color:${col};background:rgba(255,255,255,0.04);border:1px solid ${col}40;border-radius:6px;padding:2px 8px;white-space:nowrap;">${side} ${arrow}${Math.abs(oddPct).toFixed(1)}%</span>
            <span style="font-size:11px;color:var(--muted);white-space:nowrap;font-family:ui-monospace,monospace;">${head.oddOpen.toFixed(2)}→<span style="color:${col};font-weight:700;">${head.oddCurr.toFixed(2)}</span></span>
            <span style="font-size:9px;color:${isT ? '#00d4a1' : 'var(--muted)'};white-space:nowrap;min-width:54px;text-align:right;">${dateChip}</span>
          </div>`;
      }).join('')}
    </div>` : '';

  // ── Section 3: Our Picks in Sharp Context (today's picks) ─────────────────
  const bufEntries = window._v2PickBuffer ? Object.values(window._v2PickBuffer) : [];
  const todayPicks = bufEntries.filter(b => _isToday(b.date) && b.picks?.length);

  let picksContextHtml = '';
  if (!todayPicks.length) {
    picksContextHtml = `<div style="padding:20px;text-align:center;color:var(--muted);font-size:13px;">Noch keine Picks für heute — kurz warten bis Daten geladen sind.</div>`;
  } else {
    const pickRows = [];
    for (const buf of todayPicks) {
      const pmKey        = `${buf.home}|${buf.away}`;
      const pm           = window._preMatchData?.[pmKey];
      const oddsOpen     = pm?.odds_open    || null;
      const oddsClosing  = pm?.odds_closing || null;
      const oddsCurrent  = (typeof findOdds === 'function') ? findOdds(buf.league, buf.home, buf.away) : null;
      const openTs       = pm?.odds_open_ts || null;
      // For movement: use closing if game kicked off, live odds otherwise
      // buf.date is German "DD.MM.YYYY", buf.time is "HH:MM" → use isMatchOver()
      const matchKicked  = buf.date && buf.time ? isMatchOver(buf.date, buf.time) : false;
      const oddsRef      = matchKicked ? oddsClosing : oddsCurrent;
      const mvRows       = (oddsOpen && oddsRef) ? computeLineMovement(oddsOpen, oddsRef) : null;

      for (const pick of buf.picks) {
        const mktL      = (pick.market || '').toLowerCase();
        const oddsNum   = pick.odds ?? null;

        // Map pick market to line-movement label
        const pickMktKey = mktL.includes('heimsieg')||mktL.includes('dnb: heim') ? '1'
          : mktL.includes('auswärtssieg')||mktL.includes('dnb: ausw') ? '2'
          : mktL.includes('unentschieden')||mktL.includes('remis') ? 'X'
          : mktL.includes('over 2.5')||mktL.includes('über 2.5') ? 'O25'
          : mktL.includes('under 2.5')||mktL.includes('unter 2.5') ? 'U25'
          : mktL.includes('doppelte chance')&&mktL.includes('1x') ? '1X_DC'
          : mktL.includes('doppelte chance')&&mktL.includes('x2') ? 'X2_DC'
          : null;

        let pickMv = null;
        if (mvRows && pickMktKey) {
          pickMv = mvRows.find(r =>
            r.label === pickMktKey ||
            (pickMktKey === '1X_DC' && (r.label === '1' || r.label === 'X')) ||
            (pickMktKey === 'X2_DC' && (r.label === 'X' || r.label === '2'))
          );
        }

        // ── CLV / Opening-Drift ─────────────────────────────────────────────
        // Before kickoff: "Opening-Drift" — how much did the market move since opening?
        //   Positive (↘ shortened) = sharp money confirms our pick direction = GREEN
        //   Negative (↗ drifted)   = market moved against us = RED
        // After kickoff: "CLV" — our bet odds vs. the actual closing line
        //   Positive = we got BETTER odds than closing = CLV+ = GREEN
        //   Negative = closing was better = we paid too much = RED
        // Formula for both: (1/closingOrOpening - 1/ourOdds) * 100
        //   Positive when the market probability INCREASED after our snapshot/bet — i.e. we beat it.
        let clvLabel = '—', clvColor = '#8b949e', clvTitle = '';
        // Market key lookup — expanded to cover all pick types
        const _okey = mktL.includes('heimsieg') || mktL.startsWith('ah heim') || mktL.includes('dnb: heim') ? 'hw'
          : mktL.includes('auswärtssieg') || mktL.startsWith('ah ausw') || mktL.includes('dnb: ausw') ? 'aw'
          : mktL.includes('unentschieden') || mktL.includes('remis') ? 'dr'
          : (mktL.includes('over 2.5') || mktL.includes('über 2.5') || mktL.includes('o2.5')) ? 'o25'
          : (mktL.includes('under 2.5') || mktL.includes('unter 2.5') || mktL.includes('u2.5')) ? 'u25'
          : (mktL.includes('over 3.5') || mktL.includes('über 3.5')) ? 'o35'
          : (mktL.includes('under 3.5') || mktL.includes('unter 3.5')) ? 'u35'
          : (mktL.includes('beide teams treffen') || mktL.includes('btts') || mktL.includes('gg')) ? 'bttsY'
          : (mktL.includes('doppelte chance') && (mktL.includes('1x') || mktL.includes('heim'))) ? 'hw'  // DC 1X: proxy via home
          : (mktL.includes('doppelte chance') && (mktL.includes('x2') || mktL.includes('ausw'))) ? 'aw'  // DC X2: proxy via away
          : null;

        if (matchKicked && oddsClosing && oddsNum && _okey) {
          // Real CLV: (1/closingOdds - 1/ourOdds) * 100
          // Positive = closing shorter than our bet = we beat the closing line = CLV+
          const _closingOdds = parseFloat(oddsClosing[_okey]);
          if (_closingOdds && _closingOdds > 1) {
            const ppCLV = Math.round(((1/_closingOdds) - (1/oddsNum)) * 100);
            clvLabel = ppCLV >= 3 ? `CLV +${ppCLV}pp ✓` : ppCLV > 0 ? `CLV +${ppCLV}pp` : `CLV ${ppCLV}pp`;
            clvColor = ppCLV >= 3 ? '#3fb950' : ppCLV >= 0 ? '#a8d48a' : '#f85149';
            clvTitle = `Unsere Quote: ${oddsNum.toFixed(2)} | Closing-Quote: ${_closingOdds.toFixed(2)}`;
          }
        } else if (oddsOpen && oddsNum && _okey) {
          // Pre-kickoff Opening-Drift: (1/openingOdds - 1/currentOdds) * 100
          // Positive = market shortened since opening (steam toward our pick) = GREEN
          // Negative = market drifted against us since opening = RED
          const _oo = parseFloat(oddsOpen[_okey]);
          const ageLabel = _openAge(openTs);
          if (_oo && _oo > 1 && Math.abs(_oo - oddsNum) > 0.01) {
            const ppDrift = Math.round(((1/_oo) - (1/oddsNum)) * 100);
            // Positive: opening was lower implied prob → market now shorter → sharp confirms
            clvLabel = ppDrift >= 3 ? `↘ bestätigt +${ppDrift}pp` : ppDrift <= -3 ? `↗ driftet ${ppDrift}pp` : 'Stabil';
            clvColor = ppDrift >= 3 ? '#3fb950' : ppDrift <= -3 ? '#f85149' : '#8b949e';
            clvTitle = ageLabel ? `Opening-Snapshot: ${ageLabel}` : '';
          } else if (_oo) {
            clvLabel = 'Stabil'; clvColor = '#8b949e';
            clvTitle = 'Keine Linienbewegung seit Opening';
          }
        }
        const clvSectionLabel = matchKicked ? 'CLV' : 'Opening-Drift';

        // Model edge
        let edgeLabel = '—', edgeColor = '#8b949e';
        if (pick.modelOdds && oddsNum) {
          const ep = Math.round((1/pick.modelOdds - (1/oddsNum)*1.03) * 100);
          edgeLabel = ep >= 0 ? `+${ep}pp` : `${ep}pp`;
          edgeColor = ep >= 7 ? '#3fb950' : ep >= 0 ? '#e3b341' : '#f85149';
        }

        // Sharp alignment: did the market move our way?
        let sharpLabel = '—', sharpColor = '#8b949e', sharpBg = 'rgba(255,255,255,0.03)';
        if (pickMv) {
          const pp  = Math.abs(pickMv.ppShift);
          const pos = pickMv.ppShift > 0;  // positive = implied prob went up = market backed this outcome
          const closedSuffix = matchKicked ? ' (Closing)' : '';
          if (pos && pp >= 5)   { sharpLabel = `✅ Bestätigt ${pp}pp${closedSuffix}`;  sharpColor = '#3fb950'; sharpBg = 'rgba(63,185,80,0.07)'; }
          else if (pos)          { sharpLabel = `↗ Tendenz ${pp}pp${closedSuffix}`;    sharpColor = '#3fb950'; }
          else if (pp >= 8)      { sharpLabel = `⚠ Contra ${pp}pp${closedSuffix}`;    sharpColor = '#f85149'; sharpBg = 'rgba(248,81,73,0.07)'; }
          else                   { sharpLabel = `↘ Gegen ${pp}pp${closedSuffix}`;     sharpColor = '#e3b341'; }
        } else if (!mvRows) {
          sharpLabel = 'Kein Opening';
        } else {
          sharpLabel = 'Kein Signal';
        }

        pickRows.push(`<div style="background:${sharpBg};border:1px solid var(--border);border-radius:10px;padding:11px 14px;margin-bottom:7px;">
          <div style="display:flex;align-items:center;gap:7px;margin-bottom:7px;flex-wrap:wrap;">
            <span>${buf.leagueFlag || ''}</span>
            <span style="font-size:11px;color:var(--muted);">${buf.home} vs ${buf.away}</span>
            <span style="font-weight:700;font-size:13px;">${pick.market}</span>
            ${oddsNum ? `<span style="color:#58a6ff;font-weight:700;font-size:12px;">@ ${oddsNum.toFixed(2)}</span>` : ''}
            ${matchKicked ? `<span style="font-size:10px;padding:1px 5px;border-radius:4px;background:rgba(88,166,255,0.12);color:#58a6ff;border:1px solid #58a6ff30;">🔒 gespielt</span>` : ''}
          </div>
          <div style="display:flex;gap:6px;flex-wrap:wrap;font-size:11px;">
            <span style="padding:2px 8px;border-radius:5px;background:rgba(255,255,255,0.05);border:1px solid #30363d;">
              <span style="color:#8b949e;">Model Edge:</span> <span style="color:${edgeColor};font-weight:700;">${edgeLabel}</span>
            </span>
            <span style="padding:2px 8px;border-radius:5px;background:rgba(255,255,255,0.05);border:1px solid #30363d;" title="${clvTitle}">
              <span style="color:#8b949e;">${clvSectionLabel}:</span> <span style="color:${clvColor};font-weight:700;">${clvLabel}</span>
            </span>
            <span style="padding:2px 8px;border-radius:5px;background:rgba(255,255,255,0.04);border:1px solid ${sharpColor}40;">
              <span style="color:#8b949e;">Markt:</span> <span style="color:${sharpColor};font-weight:700;">${sharpLabel}</span>
            </span>
          </div>
        </div>`);
      }
    }
    picksContextHtml = pickRows.length ? pickRows.join('') :
      `<div style="padding:20px;text-align:center;color:var(--muted);">Keine Picks für heutige Spiele.</div>`;
  }

  // ── Section 4: Market Flow Heatmap (full week) ────────────────────────────
  const MARKET_DEFS = [
    { key: 'hw', label: 'Heimsieg (1)' }, { key: 'dr', label: 'Remis (X)' },
    { key: 'aw', label: 'Auswärtssieg (2)' }, { key: 'o25', label: 'Over 2.5' },
    { key: 'u25', label: 'Under 2.5' }, { key: 'o35', label: 'Over 3.5' },
  ];
  const labelMap = { hw:'1', dr:'X', aw:'2', o25:'O25', u25:'U25', o35:'O35' };

  const heatData = MARKET_DEFS.map(({key, label}) => {
    let totalPp = 0, count = 0, posCount = 0, negCount = 0;
    for (const {mvRows} of allFixtures) {
      if (!mvRows) continue;
      const row = mvRows.find(r => r.label === labelMap[key]);
      if (row) {
        totalPp += Math.abs(row.ppShift); count++;
        if (row.ppShift > 0) posCount++; else negCount++;
      }
    }
    return { label, avgPp: count ? (totalPp/count).toFixed(1) : null, count, posCount, negCount };
  });

  const heatmapHtml = `<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:8px;margin-bottom:12px;">
    ${heatData.map(({label, avgPp, count, posCount, negCount}) => {
      const v    = avgPp ? parseFloat(avgPp) : 0;
      const bg   = !avgPp ? 'rgba(255,255,255,0.02)' : v>=7 ? 'rgba(248,81,73,0.13)' : v>=4 ? 'rgba(227,179,65,0.10)' : 'rgba(63,185,80,0.07)';
      const col  = !avgPp ? '#484f58' : v>=7 ? '#f85149' : v>=4 ? '#e3b341' : '#3fb950';
      const tier = !avgPp ? '' : v>=4 ? 'SHARP' : v>=1 ? 'WATCH' : 'FLAT';
      const dir  = count ? (posCount > negCount ? `↗ ${posCount}/${count}` : `↘ ${negCount}/${count}`) : '';
      return `<div style="background:${bg};border:1px solid ${col}30;border-radius:8px;padding:11px 13px;text-align:center;">
        <div style="font-size:14px;font-weight:900;color:${col};">${avgPp != null ? avgPp+'pp' : '—'}</div>
        <div style="font-size:10px;color:var(--muted);margin-top:3px;">${label}</div>
        <div style="display:flex;align-items:center;justify-content:center;gap:4px;margin-top:4px;">
          ${count ? `<span style="font-size:9px;color:${col};opacity:.75">${count} Spiele · ${dir}</span>` : `<span style="font-size:9px;color:#484f58">kein Opening</span>`}
          ${tier ? `<span style="font-size:8px;font-weight:800;color:${col};background:${col}20;border-radius:4px;padding:0 4px">${tier}</span>` : ''}
        </div>
      </div>`;
    }).join('')}
  </div>
  <div style="padding-top:10px;border-top:1px solid #21262d;">
    <div style="font-size:9px;font-weight:700;color:#484f58;text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px">Schwellenwerte &amp; Handlungsregeln</div>
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <div style="flex:1;min-width:150px;display:flex;align-items:flex-start;gap:8px;padding:8px 10px;background:rgba(63,185,80,.06);border:1px solid rgba(63,185,80,.18);border-radius:8px">
        <span style="font-size:14px;flex-shrink:0">🟢</span>
        <div><div style="font-size:10px;font-weight:800;color:#3fb950">0–0.9pp — Kein Signal</div>
        <div style="font-size:10px;color:#484f58;margin-top:2px;line-height:1.4">Markt effizient. Kein Handlungsbedarf — blind vertrauen.</div></div>
      </div>
      <div style="flex:1;min-width:150px;display:flex;align-items:flex-start;gap:8px;padding:8px 10px;background:rgba(227,179,65,.06);border:1px solid rgba(227,179,65,.18);border-radius:8px">
        <span style="font-size:14px;flex-shrink:0">🟡</span>
        <div><div style="font-size:10px;font-weight:800;color:#e3b341">1–3.9pp — Beobachten</div>
        <div style="font-size:10px;color:#484f58;margin-top:2px;line-height:1.4">CLV-Alignment prüfen. Pick-Richtung validieren bevor Einsatz erhöht wird.</div></div>
      </div>
      <div style="flex:1;min-width:150px;display:flex;align-items:flex-start;gap:8px;padding:8px 10px;background:rgba(248,81,73,.06);border:1px solid rgba(248,81,73,.18);border-radius:8px">
        <span style="font-size:14px;flex-shrink:0">🔴</span>
        <div><div style="font-size:10px;font-weight:800;color:#f85149">≥4pp — Sharp Signal</div>
        <div style="font-size:10px;color:#484f58;margin-top:2px;line-height:1.4">Pick-Richtung bestätigen. Gegen Sharp-Richtung: meiden oder Stake reduzieren.</div></div>
      </div>
    </div>
  </div>`;

  // ── Section WM: Pinnacle Line Movement Sparklines + Total Movement Table ──
  let wmSparklineHtml = '';
  let wmTotalMoveHtml = '';
  if (_wmSharpData && _wmOddsHist) {
    // Build team lookup
    const _wmT = {};
    for (const grp of Object.values(_wmSharpData.groups || {}))
      for (const t of (grp.teams || [])) _wmT[t.id] = t;

    // Helper: implied probability
    const _ip = o => (o && o > 0) ? Math.round(100 / o * 10) / 10 : null;
    const _ppShift = (o1, o2) => {
      const p1 = _ip(o1), p2 = _ip(o2);
      return (p1 != null && p2 != null) ? Math.round((p2 - p1) * 10) / 10 : null;
    };
    const _shiftCol = pp => pp == null ? '#484f58' : Math.abs(pp) >= 8 ? '#f85149' : Math.abs(pp) >= 4 ? '#e3b341' : Math.abs(pp) >= 2 ? '#3fb950' : '#484f58';
    const _sign = pp => pp > 0 ? '+' : '';

    // ── Sparkline SVG builder ───────────────────────────────────────────────
    const _drawPinnSparkline = (snaps, matchKey) => {
      if (!snaps || snaps.length < 2) return '';
      const W = 320, H = 56, PAD = 6;
      const last = Math.min(snaps.length, 20); // max 20 points
      const pts  = snaps.slice(-last);

      // Collect all implied probs
      const lines = [
        { key: 'hw',  col: '#3fb950', label: 'H' },
        { key: 'dr',  col: '#8b949e', label: 'X' },
        { key: 'aw',  col: '#f85149', label: 'A' },
      ];
      // Only include a line if first AND last snapshot have data
      const activeLines = lines.filter(l => pts[0][l.key] && pts[pts.length-1][l.key]);
      if (!activeLines.length) return '';

      // All valid ip values for y-scale
      const allVals = activeLines.flatMap(l => pts.map(s => _ip(s[l.key])).filter(v => v != null));
      if (!allVals.length) return '';
      const yMin = Math.max(0, Math.min(...allVals) - 4);
      const yMax = Math.min(100, Math.max(...allVals) + 4);
      const yRange = yMax - yMin || 1;

      const xScale = i  => PAD + (i / (pts.length - 1)) * (W - PAD * 2);
      const yScale = ip => H - PAD - ((ip - yMin) / yRange) * (H - PAD * 2);

      let svgParts = [`<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:${H}px;overflow:visible">`];

      // Grid line at 50%
      if (yMin < 50 && yMax > 50) {
        const y50 = yScale(50);
        svgParts.push(`<line x1="${PAD}" y1="${y50}" x2="${W-PAD}" y2="${y50}" stroke="#30363d" stroke-width="1" stroke-dasharray="3,3"/>`);
        svgParts.push(`<text x="${PAD}" y="${y50-2}" font-size="7" fill="#484f58">50%</text>`);
      }

      // Draw lines
      for (const {key, col} of activeLines) {
        const coords = pts.map((s, i) => {
          const ip = _ip(s[key]);
          return ip != null ? `${xScale(i).toFixed(1)},${yScale(ip).toFixed(1)}` : null;
        }).filter(Boolean);
        if (coords.length < 2) continue;

        // Gradient fill under line for biggest mover
        const fillId = `fill_${matchKey}_${key}`;
        svgParts.push(`<defs>
          <linearGradient id="${fillId}" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="${col}" stop-opacity="0.18"/>
            <stop offset="100%" stop-color="${col}" stop-opacity="0.02"/>
          </linearGradient>
        </defs>`);

        // Fill area
        const firstX = xScale(pts.findIndex(s => _ip(s[key]) != null));
        const lastX  = xScale(pts.length - 1);
        const fillPoints = `${firstX},${H-PAD} ${coords.join(' ')} ${lastX},${H-PAD}`;
        svgParts.push(`<polygon points="${fillPoints}" fill="url(#${fillId})"/>`);

        // Line
        svgParts.push(`<polyline points="${coords.join(' ')}" fill="none" stroke="${col}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>`);

        // Last point dot + probability label
        const lastCoord = coords[coords.length - 1].split(',');
        const lastPt    = pts[pts.length - 1];
        const lastIp    = _ip(lastPt[key]);
        svgParts.push(`<circle cx="${lastCoord[0]}" cy="${lastCoord[1]}" r="3" fill="${col}" stroke="#0d1117" stroke-width="1.5"/>`);
        if (lastIp != null) {
          const lx = parseFloat(lastCoord[0]);
          const ly = parseFloat(lastCoord[1]);
          const anchor = lx > W * 0.75 ? 'end' : 'start';
          const dx = anchor === 'end' ? -5 : 5;
          const dy = ly < H * 0.35 ? 10 : -4;
          svgParts.push(`<text x="${(lx+dx).toFixed(1)}" y="${(ly+dy).toFixed(1)}" font-size="9" font-weight="700" fill="${col}" text-anchor="${anchor}" opacity="0.9">${lastIp}%</text>`);
        }
      }

      svgParts.push('</svg>');
      return svgParts.join('');
    };

    // ── Build fixture data with total movement ──────────────────────────────
    const wmFxData = [];
    for (const grp of Object.values(_wmSharpData.groups || {})) {
      for (const fx of (grp.fixtures || [])) {
        const key   = `${fx.home}-${fx.away}`;
        const snaps = _wmOddsHist[key];
        if (!snaps || snaps.length < 1) continue;
        const homeT = _wmT[fx.home] || { name: fx.home, flag: '🏳' };
        const awayT = _wmT[fx.away] || { name: fx.away, flag: '🏳' };
        const first = snaps[0];
        const last  = snaps[snaps.length - 1];
        const fields = [
          { key: 'hw',    label: 'H'    },
          { key: 'dr',    label: 'X'    },
          { key: 'aw',    label: 'A'    },
          { key: 'o25',   label: 'Ü2.5' },
          { key: 'u25',   label: 'U2.5' },
          { key: 'bttsY', label: 'BTTS' },
        ];
        const shifts = {};
        let maxAbsShift = 0;
        for (const {key: fk, label} of fields) {
          const s = _ppShift(first[fk], last[fk]);
          shifts[fk] = s;
          if (s != null && Math.abs(s) > maxAbsShift) maxAbsShift = Math.abs(s);
        }
        wmFxData.push({
          key, fx, homeT, awayT, snaps, first, last, shifts, maxAbsShift,
          snapCount: snaps.length,
        });
      }
    }

    // Sort by max cumulative shift (biggest movers first)
    wmFxData.sort((a, b) => b.maxAbsShift - a.maxAbsShift);

    // ── Section A: Sparkline Cards (top movers + all fixtures with ≥2 snaps) ──
    const sparkFx = wmFxData.filter(d => d.snapCount >= 2);
    if (sparkFx.length > 0) {
      // Count ACT/WATCH fixtures for section header badges
      const actCount  = sparkFx.filter(d => d.maxAbsShift >= 4).length;
      const watchCount = sparkFx.filter(d => d.maxAbsShift >= 2).length;

      // Filter state (default ≥2pp — only show meaningful signals)
      window._wmSparkFilter = window._wmSparkFilter ?? 2;
      const filteredSparkFx = sparkFx.filter(d => d.maxAbsShift >= window._wmSparkFilter);

      const sparkFilterBar = `<div style="display:flex;align-items:center;gap:6px;margin-bottom:10px;flex-wrap:wrap">
        ${actCount  > 0 ? `<span style="background:rgba(248,81,73,.12);border:1px solid rgba(248,81,73,.3);border-radius:10px;padding:1px 8px;font-size:10px;font-weight:800;color:#f85149">🚨 ${actCount} ACT ≥4pp</span>` : ''}
        ${watchCount > 0 ? `<span style="background:rgba(227,179,65,.10);border:1px solid rgba(227,179,65,.25);border-radius:10px;padding:1px 8px;font-size:10px;font-weight:700;color:#e3b341">👁 ${watchCount} WATCH ≥2pp</span>` : ''}
        <span style="font-size:10px;color:#484f58;margin-left:auto">Filter:</span>
        ${[['Alle', 0], ['≥2pp', 2], ['≥4pp', 4]].map(([lbl, thr]) => {
          const active = window._wmSparkFilter === thr;
          return `<button onclick="window._wmSparkFilter=${thr};renderSharpRadar()"
            style="background:${active ? 'rgba(0,212,161,.12)' : 'rgba(255,255,255,.03)'};border:1px solid ${active ? 'rgba(0,212,161,.4)' : '#30363d'};
                   border-radius:10px;color:${active ? '#00d4a1' : '#6e7681'};font-size:10px;font-weight:${active ? '800' : '500'};
                   padding:3px 10px;cursor:pointer;font-family:inherit;transition:all .12s">${lbl}</button>`;
        }).join('')}
      </div>`;

      const sparkCardsHtml = filteredSparkFx.length === 0
        ? `<div style="padding:20px;text-align:center;color:#484f58;font-size:12px">Keine Bewegung über ${window._wmSparkFilter}pp — Filter ändern um alle Spiele zu sehen</div>`
        : filteredSparkFx.map(({key, fx, homeT, awayT, snaps, shifts, maxAbsShift, snapCount}) => {
        const [yr, mo, dy] = fx.date.split('-');
        const dateFmt = `${dy}.${mo}.${yr.slice(2)}`;
        const moveCol = _shiftCol(maxAbsShift);
        const sparkSvg = _drawPinnSparkline(snaps, key.replace('-','_'));

        // Shift chips for each market
        const chipFields = [
          { fk: 'hw', label: 'H' }, { fk: 'dr', label: 'X' }, { fk: 'aw', label: 'A' },
          { fk: 'o25', label: 'Ü2.5' }, { fk: 'u25', label: 'U2.5' }, { fk: 'bttsY', label: 'BTTS' },
        ];
        const chips = chipFields.map(({fk, label}) => {
          const s = shifts[fk];
          if (s == null) return '';
          if (Math.abs(s) < 0.5) return `<span style="padding:2px 7px;border-radius:5px;background:#161b22;border:1px solid #21262d;font-size:10px;color:#484f58">${label} —</span>`;
          const col = _shiftCol(s);
          const sign = _sign(s);
          return `<span style="padding:2px 7px;border-radius:5px;background:${col}18;border:1px solid ${col}44;font-size:10px;font-weight:700;color:${col}">${label} ${sign}${s}pp</span>`;
        }).join('');

        const bk = snaps[snaps.length-1].bk || '?';
        const bgCard    = maxAbsShift >= 8 ? '#1a0d0d' : maxAbsShift >= 5 ? '#1a160a' : maxAbsShift >= 2 ? '#0d1117' : '#0d1117';
        const borderCard = maxAbsShift >= 8 ? '#f8514933' : maxAbsShift >= 5 ? '#e3b34133' : maxAbsShift >= 2 ? '#30363d' : '#21262d';
        const accentBorder = maxAbsShift >= 4 ? '#f85149' : maxAbsShift >= 2 ? '#e3b341' : 'transparent';

        // Actionable badge: ACT / WATCH / flat
        const moveBadge = maxAbsShift >= 4
          ? `<span style="font-size:11px;font-weight:800;color:#f85149;background:rgba(248,81,73,.15);border:1px solid rgba(248,81,73,.4);border-radius:8px;padding:2px 10px">🚨 ACT ${maxAbsShift}pp</span>`
          : maxAbsShift >= 2
          ? `<span style="font-size:11px;font-weight:800;color:#e3b341;background:rgba(227,179,65,.12);border:1px solid rgba(227,179,65,.35);border-radius:8px;padding:2px 10px">👁 WATCH ${maxAbsShift}pp</span>`
          : `<span style="font-size:11px;font-weight:700;color:#484f58;background:rgba(255,255,255,.03);border:1px solid #21262d;border-radius:8px;padding:2px 10px">${maxAbsShift}pp</span>`;

        // Action bar — plain-language guidance for user
        const actionBar = (() => {
          if (maxAbsShift < 2) return '';
          // Find biggest mover market
          const entries = Object.entries(shifts).filter(([,v]) => v != null && Math.abs(v) >= 0.5);
          if (!entries.length) return '';
          entries.sort(([,a],[,b]) => Math.abs(b) - Math.abs(a));
          const [fk, fpp] = entries[0];
          const mktNames = { hw: 'Heimsieg (H)', dr: 'Remis (X)', aw: 'Auswärtssieg (A)', o25: 'Über 2.5 Tore', u25: 'Unter 2.5 Tore', bttsY: 'BTTS Ja' };
          const mktName = mktNames[fk] || fk;
          const dir = fpp > 0 ? 'gewinnt Wahrscheinlichkeit' : 'verliert Wahrscheinlichkeit';
          const sign = fpp > 0 ? '+' : '';
          const barCol = maxAbsShift >= 4 ? '#f85149' : '#e3b341';
          const actionText = maxAbsShift >= 4
            ? `🚨 Sharp-Signal: <strong>${mktName}</strong> ${dir} (${sign}${fpp}pp) — Pick in diese Richtung bestätigen, gegen diese Richtung meiden`
            : `👁 Beobachten: <strong>${mktName}</strong> ${dir} (${sign}${fpp}pp) — Entwicklung verfolgen, kein sofortiger Handlungsbedarf`;
          return `<div style="margin-top:8px;padding:7px 10px;border-radius:7px;background:${barCol}10;border-left:3px solid ${barCol};font-size:11px;color:${barCol};line-height:1.5">${actionText}</div>`;
        })();

        return `<div style="background:${bgCard};border:1px solid ${borderCard};border-left:3px solid ${accentBorder};border-radius:10px;padding:12px 14px;margin-bottom:8px;">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap;">
            <span style="font-size:13px;font-weight:700;color:#e6edf3">${homeT.flag} ${homeT.name} <span style="color:#484f58;font-weight:400">vs</span> ${awayT.flag} ${awayT.name}</span>
            <span style="font-size:10px;color:#6e7681">${dateFmt}</span>
            <span style="margin-left:auto">${moveBadge}</span>
          </div>
          <div style="margin-bottom:8px;border-radius:6px;overflow:hidden;background:#0a0d10;padding:4px 6px">
            ${sparkSvg}
            <div style="display:flex;gap:12px;font-size:9px;color:#6e7681;margin-top:2px;padding-left:2px">
              <span style="display:flex;align-items:center;gap:3px"><span style="display:inline-block;width:14px;height:2px;background:#3fb950"></span> H</span>
              <span style="display:flex;align-items:center;gap:3px"><span style="display:inline-block;width:14px;height:2px;background:#8b949e"></span> X</span>
              <span style="display:flex;align-items:center;gap:3px"><span style="display:inline-block;width:14px;height:2px;background:#f85149"></span> A</span>
              <span style="color:#484f58">${snapCount} Snapshots · ${bk}</span>
            </div>
          </div>
          <div style="display:flex;gap:5px;flex-wrap:wrap">${chips}</div>
          ${actionBar}
        </div>`;
        }).join('');

      wmSparklineHtml = sparkFilterBar + sparkCardsHtml;
    }

    // ── Section B: Gesamtbewegung Tabelle (alle WM Fixtures) ───────────────
    const allFxSorted = [...wmFxData].sort((a, b) => b.maxAbsShift - a.maxAbsShift);
    if (allFxSorted.length > 0) {
      const tRows = allFxSorted.map(({fx, homeT, awayT, shifts, maxAbsShift, snapCount}) => {
        const [yr, mo, dy] = fx.date.split('-');
        const dateFmt = `${dy}.${mo}.`;
        const maxCol = _shiftCol(maxAbsShift);

        const tdShift = (fk) => {
          const s = shifts[fk];
          if (s == null) return '<td style="padding:5px 6px;text-align:center;font-size:10px;color:#30363d;">—</td>';
          if (Math.abs(s) < 0.5) return '<td style="padding:5px 6px;text-align:center;font-size:10px;color:#484f58;">±0</td>';
          const col = _shiftCol(s);
          const sign = _sign(s);
          return `<td style="padding:5px 6px;text-align:center;font-size:10px;font-weight:700;color:${col}">${sign}${s}</td>`;
        };

        return `<tr style="border-bottom:1px solid #21262d">
          <td style="padding:5px 8px;font-size:11px;white-space:nowrap;color:#e6edf3">${homeT.flag} ${homeT.name.split(' ').slice(-1)[0]} – ${awayT.flag} ${awayT.name.split(' ').slice(-1)[0]}</td>
          <td style="padding:5px 6px;font-size:10px;color:#6e7681">${dateFmt}</td>
          ${tdShift('hw')}${tdShift('dr')}${tdShift('aw')}
          ${tdShift('o25')}${tdShift('u25')}${tdShift('bttsY')}
          <td style="padding:5px 8px;text-align:center;font-size:11px;font-weight:800;color:${maxCol}">${maxAbsShift > 0 ? maxAbsShift+'pp' : '—'}</td>
          <td style="padding:5px 8px;font-size:10px;color:#484f58;text-align:center">${snapCount}</td>
        </tr>`;
      }).join('');

      wmTotalMoveHtml = `<div style="overflow-x:auto;border-radius:10px;border:1px solid #21262d">
        <table style="width:100%;border-collapse:collapse;font-family:inherit">
          <thead>
            <tr style="background:#161b22;border-bottom:1px solid #21262d">
              <th style="padding:8px 8px;text-align:left;font-size:10px;color:#6e7681;font-weight:700;text-transform:uppercase;letter-spacing:.5px">Spiel</th>
              <th style="padding:8px 6px;font-size:10px;color:#6e7681;font-weight:700;text-transform:uppercase;letter-spacing:.5px">Datum</th>
              <th style="padding:8px 6px;text-align:center;font-size:10px;color:#3fb950;font-weight:700">H Δpp</th>
              <th style="padding:8px 6px;text-align:center;font-size:10px;color:#8b949e;font-weight:700">X Δpp</th>
              <th style="padding:8px 6px;text-align:center;font-size:10px;color:#f85149;font-weight:700">A Δpp</th>
              <th style="padding:8px 6px;text-align:center;font-size:10px;color:#a78bfa;font-weight:700">Ü2.5</th>
              <th style="padding:8px 6px;text-align:center;font-size:10px;color:#60a5fa;font-weight:700">U2.5</th>
              <th style="padding:8px 6px;text-align:center;font-size:10px;color:#f0c040;font-weight:700">BTTS</th>
              <th style="padding:8px 8px;text-align:center;font-size:10px;color:#e6edf3;font-weight:700">Max Δ</th>
              <th style="padding:8px 8px;text-align:center;font-size:10px;color:#484f58;font-weight:700;letter-spacing:.3px">Snaps</th>
            </tr>
          </thead>
          <tbody>${tRows}</tbody>
        </table>
      </div>`;
    }
  }

  // ── Assemble ──────────────────────────────────────────────────────────────
  _loadClvSummary();   // 28.06.2026: CLV-Bilanz lazy laden (dataset-aware), re-rendert wenn da
  mc.innerHTML = `<div style="max-width:960px;margin:0 auto;padding:0 0 60px;">

    ${_sharpRenderToggleHtml()}

    <div style="margin-bottom:22px;padding:18px 20px 14px;background:linear-gradient(135deg,rgba(0,212,161,0.07),rgba(88,166,255,0.04));border:1px solid rgba(0,212,161,0.18);border-radius:14px;">
      <div style="font-size:18px;font-weight:900;margin-bottom:5px;">📡 Sharp Money Radar</div>
      <div style="font-size:12px;color:var(--muted);line-height:1.55;display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
        <span>Linienbewegungen im Markt · alle 7 Tage · CLV-Orientierung für unsere Picks</span>
        ${(() => {
          // FIX 16.06.2026: Frische = letzter FETCH (hist._meta.oddsFetchedAt), nicht nur
          // die letzte Bewegung. Grund (Lucas): bei flachen Pre-Match-Linien gab es lange
          // keinen neuen Snapshot → Badge hing auf „vor 17 Std" und meldete fälschlich
          // STALE, obwohl der Manage-Zyklus alle 15-30min frisch holt. fetch_wm_odds
          // schreibt jetzt oddsFetchedAt bei JEDEM Lauf. Stale erst wenn der FETCH hängt.
          const hist = _hist || {};  // (26.06.2026, Lucas: Sharp Radar Liga-Toggle) — dataset-bewusst
          let moveTs = 0;
          for (const snaps of Object.values(hist)) {
            if (Array.isArray(snaps) && snaps.length) {
              const t = new Date(snaps[snaps.length - 1].ts).getTime();
              if (!isNaN(t) && t > moveTs) moveTs = t;
            }
          }
          const fetchIso = (hist._meta && hist._meta.oddsFetchedAt) || null;
          const fetchTs  = fetchIso ? new Date(fetchIso).getTime() : 0;
          const baseTs   = fetchTs || moveTs;   // Fallback auf Bewegung (alte Daten ohne _meta)
          if (baseTs) {
            const diffM = Math.round((Date.now() - baseTs) / 60000);
            const ago = diffM < 2 ? 'gerade eben'
                      : diffM < 60 ? `vor ${diffM} Min`
                      : diffM < 1440 ? `vor ${Math.floor(diffM/60)} Std`
                      : `vor ${Math.floor(diffM/1440)} Tg`;
            const stale = diffM >= 240;             // > 4h ohne Fetch = Feed hängt (Lauf alle 15-30min)
            const col = diffM < 90 ? '#3fb950' : diffM < 240 ? '#e3b341' : '#f85149';
            const moveTxt = moveTs ? new Date(moveTs).toLocaleString('de-AT',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}) : '—';
            return `<span style="font-size:11px;font-weight:800;color:${col};background:rgba(0,0,0,0.25);border:1px solid ${col}66;border-radius:5px;padding:2px 8px;" title="Letzte Pinnacle-Bewegung: ${moveTxt}">📊 Odds ${ago} geholt${stale ? ' · ⚠️ STALE — Feed prüfen' : ''}</span>`;
          }
          // Kein Snapshot geladen → ehrlich rot statt "wird geladen…"
          const _ts = window._pmTs;
          if (_ts) {
            const diffM = Math.round((Date.now() - _ts) / 60000);
            const ago = diffM < 60 ? `vor ${diffM} Min` : `vor ${Math.floor(diffM/60)} Std`;
            return `<span style="font-size:11px;font-weight:700;color:#8b949e;background:rgba(0,0,0,0.25);border:1px solid #30363d;border-radius:5px;padding:2px 8px;">⏱ Liga-Prematch ${ago}</span>`;
          }
          return '<span style="color:#f85149;font-size:11px;font-weight:800;">⚠️ Keine Odds-Snapshots geladen — Feed prüfen</span>';
        })()}
      </div>
    </div>

    ${moversHeroHtml}

    ${_renderSharpWatchlist()}
    ${_renderClvScoreboard()}
    ${_renderBayesianWeights()}
    ${_renderClvAggregation()}

    <div class="section-label" style="margin-bottom:10px;">📊 Marktübersicht · diese Woche</div>
    ${kpiHtml}

    <div class="section-label" style="margin-bottom:10px;">🔥 Markt-Flow Heatmap · Ø Bewegung pro Market (7 Tage)</div>
    <div style="background:var(--card);border:1px solid var(--border);border-radius:12px;padding:16px;margin-bottom:20px;">
      ${heatmapHtml}
    </div>

    <div class="section-label" style="margin-bottom:6px;">⚡ Größte Marktbewegungen · sortiert nach Magnitude</div>
    <div style="font-size:11px;color:var(--muted);margin-bottom:10px;padding:0 2px;">
      <strong style="color:var(--text)">Opening→Aktuell</strong> für Spiele vor Anpfiff · <strong style="color:#58a6ff">Opening→Closing</strong> für bereits gespielte Spiele.
      Opening-Snapshots entstehen beim ersten Prematch-Fetch — das Alter wird in jeder Zeile angezeigt. <span style="color:#f85149">⏱ &lt;2h alt</span> = Opening zu frisch für echte Signale.
    </div>
    <div style="margin-bottom:20px;">${moversHtml}</div>

    ${wmSparklineHtml ? `
    <div class="section-label" style="margin-bottom:10px;">📈 WM 2026 — Pinnacle Quoten-Verlauf (Opening → Aktuell)</div>
    <div style="font-size:11px;color:var(--muted);margin-bottom:10px;padding:0 2px;">
      Grün = Heimsieg · Grau = Remis · Rot = Auswärtssieg · Implied Probability aus Pinnacle-Snapshots.
      Starke Bewegung = Sharp Money oder neue Information im Markt.
    </div>
    <div style="margin-bottom:20px;">${wmSparklineHtml}</div>
    ` : ''}

    ${wmTotalMoveHtml ? `
    <div class="section-label" style="margin-bottom:8px;">📋 WM 2026 — Gesamtbewegung seit Erstnotiz (alle Fixtures)</div>
    <div style="font-size:11px;color:var(--muted);margin-bottom:10px;padding:0 2px;">
      Δpp = Veränderung der Implied Probability von Opening-Snapshot bis aktuell.
      Positiv = Markt sieht Ergebnis wahrscheinlicher · Sortiert nach stärkster Gesamtbewegung.
    </div>
    <div style="margin-bottom:20px;">${wmTotalMoveHtml}</div>
    ` : ''}

    <div class="section-label" style="margin-bottom:4px;">🎯 Unsere heutigen Picks im Sharp-Kontext</div>
    <div style="font-size:11px;color:var(--muted);margin-bottom:10px;padding:0 2px;">
      <strong style="color:var(--text)">Opening-Drift</strong> = Marktbewegung seit unserem ersten Snapshot (vor Kickoff).
      <strong style="color:#58a6ff">CLV</strong> = Closing Line Value nach Kickoff: unsere Quote vs. Closing-Quote. CLV+ bedeutet wir haben besser als der Markt geschlossen.
    </div>
    ${picksContextHtml}

  </div>`;
}

function renderLeague(key) {
  // (25.06.2026, Lucas: National auf WM-Stack) Die alte Liga-/Overview-Anzeige ist abgelöst — das
  // National-Menü rendert jetzt der WM-Renderer (initNationalCards) ins selbe Panel mainContent.
  // Sonst überschreiben die alten Boot-/Async-Re-Renders (stats_cache, loadAllOdds) die neuen Cards
  // → „Cards kurz da, dann weg". Sharp Radar nutzt renderLeague weiter, daher nur key≠'sharp' blocken.
  if (window.NATIONAL_USES_NEW_RENDERER && key !== 'sharp') return;
  const mc = document.getElementById('mainContent');
  if (key === 'overview') { renderOverview(); return; }
  if (key === 'sharp')    { renderSharpRadar(); return; }
  const L = LEAGUES[key];
  if (!L) { mc.innerHTML = '<p style="color:var(--muted);padding:20px">Keine Daten verfügbar.</p>'; return; }

  // Standings context
  const top3 = L.stakeTeams.filter(t=>t.pos<=3).slice(0,3);
  const bottom3 = L.stakeTeams.filter(t=>t.score>=7&&(t.labels||[]).some(l=>l.c==='red')).slice(0,3);

  const topChips = top3.map(t=>`<div class="pos-chip ucl-zone"><span class="pn">#${t.pos}</span><span class="pt">${t.team}</span><span class="pp">${t.pts}pts</span></div>`).join('');
  const botChips = bottom3.map(t=>`<div class="pos-chip rel-zone"><span class="pn">#${t.pos}</span><span class="pt">${t.team}</span><span class="pp">${t.pts}pts</span></div>`).join('');

  // All games this week (for day chip counts)
  const week = [...L.fixtures].filter(m => isWithin7Days(m.date));
  // Apply active day filter for actual card display, hide finished matches (kickoff + 100 min)
  const filtered = applyDayFilter(week)
    .filter(m => !isMatchOver(m.date, m.time))
    // Skip dead-rubber fixtures: both teams confirmed out of everything (motivationLevel='none')
    // BUT only when there are also no valid picks — a model might still find value in dead rubbers
    // (e.g. heavy favorite, line movement, etc.) and we shouldn't suppress those cards.
    .filter(m => {
      const hm = m.homeStake?.motivationLevel;
      const am = m.awayStake?.motivationLevel;
      if (!(hm === 'none' && am === 'none')) return true;  // at least one team has stakes → show
      // Both 'none': only hide if the pick engine also finds nothing
      const _odds = findOdds(leagueKey || key, m.home, m.away);
      const _oddsD = deriveOdds(_odds || {});
      const _picks = getBettingPicks(m, _oddsD, leagueKey || key);
      const _visible = _picks.filter(p => {
        if (p.conf !== 'high' && p.conf !== 'medium') return false;
        if (p.modelOdds != null && p.odds != null) {
          const _ep = Math.round(((1 / p.modelOdds) - (1 / p.odds) * 1.03) * 100);
          if (_ep < -5) return false;
        }
        return true;
      });
      return _visible.length > 0;  // keep card if picks exist despite dead rubber
    })
    .sort((a,b)=>computeMatchScore(b,key)-computeMatchScore(a,key));
  const cards = filtered.map(m=>renderFixtureCard(m, L.name, L.flag, key)).join('');
  const potdHtml = buildPickOfDayHtml(filtered.map(m=>({...m, leagueKey:key, leagueFlag:L.flag})));

  const dayLabel = window._selectedDay === 'all'
    ? weekLabel()
    : (() => { const d = parseGermanDate(window._selectedDay); return d.toLocaleDateString('de-DE',{weekday:'long',day:'numeric',month:'long'}); })();

  const emptyState = `
    <div style="grid-column:1/-1;text-align:center;padding:40px 20px;color:var(--muted)">
      <div style="font-size:32px;margin-bottom:12px">📅</div>
      <div style="font-weight:600;margin-bottom:6px">${window._selectedDay !== 'all' ? 'Keine Spiele an diesem Tag in ' + L.name : 'Keine Spiele diese Woche'}</div>
      <div style="font-size:12px">${window._selectedDay !== 'all' ? 'Anderen Tag wählen oder auf "Alle" klicken' : 'Nächste High-Stakes Partie kommt nach dem ' + weekLabel().split('–')[1].trim()}</div>
    </div>`;

  mc.innerHTML = `
    <div class="league-info-bar">
      <div class="lib-item accent"><div class="lib-val">${L.flag} ${L.name}</div><div class="lib-key">Liga</div></div>
      <div class="lib-sep"></div>
      <div class="lib-item warn"><div class="lib-val">${L.roundsLeft}</div><div class="lib-key">Runden verbleibend</div></div>
      <div class="lib-sep"></div>
      <div class="lib-item"><div class="lib-val">${L.leader}</div><div class="lib-key">Tabellenführer</div></div>
      <div class="lib-sep"></div>
      <div class="lib-item"><div class="lib-val">${L.leaderPts}</div><div class="lib-key">Punkte</div></div>
      <div class="lib-sep"></div>
      <div class="lib-item"><div class="lib-val">${filtered.length}${filtered.length!==week.length?' / '+week.length:''}</div><div class="lib-key">Spiele${filtered.length!==week.length?' angezeigt':' diese Woche'}</div></div>
    </div>

    ${topChips||botChips ? `<div class="standings-strip">${topChips}${botChips}</div>` : ''}

    ${buildDayFilterHtml(week)}

    ${potdHtml}

    <div class="section-label">🎯 High-Stakes Spiele · ${L.name} · 📅 ${dayLabel}</div>
    <div class="stake-grid">${cards || emptyState}</div>
  `;
}

function renderOverview() {
  const mc = document.getElementById('mainContent');

  // Gather ALL fixtures across all leagues, filter to next 7 days
  const all = [];
  for (const [key, L] of Object.entries(LEAGUES)) {
    for (const f of L.fixtures) {
      all.push({...f, leagueKey:key, leagueName:L.name, leagueFlag:L.flag, roundsLeft:L.roundsLeft});
    }
  }
  const week = all.filter(f => isWithin7Days(f.date));
  week.sort((a,b)=>computeMatchScore(b,b.leagueKey)-computeMatchScore(a,a.leagueKey));

  // Apply active day filter, hide finished matches (kickoff + 100 min)
  const filtered = applyDayFilter(week).filter(f => !isMatchOver(f.date, f.time));

  // Stats on filtered set
  const score11 = filtered.filter(f=>computeMatchScore(f,f.leagueKey)>=11).length;
  const score9  = filtered.filter(f=>computeMatchScore(f,f.leagueKey)>=9).length;

  const dayLabel = window._selectedDay === 'all'
    ? weekLabel()
    : (() => { const d = parseGermanDate(window._selectedDay); return d.toLocaleDateString('de-DE',{weekday:'long',day:'numeric',month:'long'}); })();

  const emptyAll = `
    <div style="grid-column:1/-1;text-align:center;padding:60px 20px;color:var(--muted)">
      <div style="font-size:40px;margin-bottom:14px">${window._selectedDay !== 'all' ? '📅' : '🎉'}</div>
      <div style="font-weight:600;font-size:16px;margin-bottom:8px">${window._selectedDay !== 'all' ? 'Keine High-Stakes Spiele an diesem Tag' : 'Keine High-Stakes Spiele diese Woche'}</div>
      <div style="font-size:12px">${window._selectedDay !== 'all' ? 'Anderen Tag wählen oder auf "Alle" klicken' : 'Schau nächste Woche wieder rein — die Lage spitzt sich zu!'}</div>
    </div>`;

  // Cards des Tages + POTD use only the filtered (day-selected) matches
  // buildTopCardsHtml MUST run before renderFixtureCard so _topPickSet is populated
  const dodSectionHtml = buildDoOrDieSection(week); // internally limited to next 3 days + deduped per team
  const potdHtml      = buildPickOfDayHtml(filtered);
  const topCardsHtml  = buildTopCardsHtml(filtered);
  const cards = filtered.map(m=>renderFixtureCard(m, m.leagueName, m.leagueFlag, m.leagueKey)).join('');

  mc.innerHTML = `
    <div class="overview-header">
      🏁 <strong>Season Finish · ${window._selectedDay === 'all' ? 'Nächste 7 Tage' : dayLabel}</strong><br>
      📅 <strong>${dayLabel}</strong> &nbsp;·&nbsp;
      <strong style="color:var(--orange)">${score11}</strong> Spiele Score ≥11 &nbsp;·&nbsp;
      <strong style="color:var(--green)">${score9}</strong> Spiele Score ≥9
    </div>

    ${buildDayFilterHtml(week)}

    ${dodSectionHtml}

    ${potdHtml}

    ${topCardsHtml}

    <div class="section-label" style="margin-top:4px">⭐ Alle High-Stakes Spiele${window._selectedDay !== 'all' ? ' · '+dayLabel : ' dieser Woche'} · sortiert nach Score</div>
    <div class="stake-grid">${cards || emptyAll}</div>
  `;

  // ── Save browser-computed picks to localStorage (Results V2 tracking) ────────
  // Uses the SAME odds + deriveOdds + getBettingPicks chain as the cards above,
  // so tracked picks ALWAYS match what's shown on screen.
  window._v2LastMatchList = filtered;  // expose globally so Tracking tab can trigger manually
  if (typeof savePicksV2 === 'function') {
    try { savePicksV2(filtered); } catch(e) { console.warn('[savePicksV2]', e); }
  }
  // Legacy: also try to push to local server (fire-and-forget, no blocking)
  _pushPicksToServer(filtered).catch(() => {});
}

// ═══════════════════════════════════════════════════════
//  PICKS → SERVER PUSH
//  Sends browser-computed picks to prematch-server.js (localhost:3001/save_picks)
//  so picks_history.json is always in sync with what the cards show.
// ═══════════════════════════════════════════════════════
function _marketToKey(market) {
  const m = (market || '').trim();
  const ml = m.toLowerCase();
  if (ml === 'heimsieg')                       return 'homeWin';
  if (ml === 'auswärtssieg')                   return 'awayWin';
  if (ml === 'unentschieden')                  return 'draw';
  if (/over 2\.5 tore|über 2\.5 tore/i.test(ml))  return 'over25';
  if (/under 2\.5 tore|unter 2\.5 tore/i.test(ml))return 'under25';
  if (/over 3\.5 tore|über 3\.5 tore/i.test(ml))  return 'over35';
  if (/under 3\.5 tore|unter 3\.5 tore/i.test(ml))return 'under35';
  if (/over 2\.25 tore/i.test(ml))            return 'over225';
  if (/over 2 tore/i.test(ml))                return 'over2';
  if (/beide teams treffen: nein/i.test(ml))  return 'noBtts';
  if (/beide teams treffen/i.test(ml))        return 'btts';
  if (/über 4\.5 karten/i.test(ml))           return 'cards45';
  if (/über 3\.5 karten/i.test(ml))           return 'cards35';
  if (/doppelte chance.*1x/i.test(ml))        return 'dc1X';
  if (/doppelte chance.*x2/i.test(ml))        return 'dcX2';
  if (/doppelte chance.*12/i.test(ml))        return 'dc12';
  const ahH = m.match(/^ah\s+heim\s+([-+]?\d+\.?\d*)/i);
  if (ahH) return `ah_home:${ahH[1]}`;
  const ahA = m.match(/^ah\s+ausw[^\s\d+-]*\.?\s+([-+]?\d+\.?\d*)/i);
  if (ahA) return `ah_away:${ahA[1]}`;
  const co = m.match(/[üü]ber\s+(\d+\.?\d*)\s+Ecken/i);
  if (co) return `corners_over:${co[1]}`;
  const cu = m.match(/[uu]nter\s+(\d+\.?\d*)\s+Ecken/i);
  if (cu) return `corners_under:${cu[1]}`;
  if (/1\.\s*hz.*over 0\.5/i.test(ml) || /1\.\s*hz.*über 0\.5/i.test(ml)) return 'ht_over05';
  if (/1\.\s*hz.*beide teams treffen: nein/i.test(ml)) return 'ht_noBtts';
  if (/1\.\s*hz.*beide teams treffen/i.test(ml))       return 'ht_btts';
  return ml.replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '') || 'unknown';
}

async function _pushPicksToServer(matchList) {
  const SERVER = 'http://localhost:3001/save_picks';

  // Build payload: one entry per fixture with picks (same logic as renderFixtureCard)
  const payload = [];
  for (const match of matchList) {
    const lk   = match.leagueKey;
    const odds  = lk ? findOdds(lk, match.home, match.away) : null;
    const oddsD = deriveOdds(odds || {});
    const picks = getBettingPicks(match, oddsD, lk) || [];
    const visible = picks.filter(p => p.conf === 'high' || p.conf === 'medium');
    if (visible.length === 0) continue;  // no picks → not tracked

    // dateIso from "DD.MM.YYYY"
    const dateIso = (() => {
      try {
        const [d, mo, y] = (match.date || '').split('.');
        return `${y}-${mo.padStart(2,'0')}-${d.padStart(2,'0')}`;
      } catch(_) { return ''; }
    })();

    payload.push({
      id:         `${dateIso}-${lk}-${match.home}-${match.away}`,
      date:       match.date || '',
      dateIso,
      league:     lk,
      leagueName: match.leagueName || lk,
      leagueFlag: match.leagueFlag || '',
      home:       match.home,
      away:       match.away,
      eventId:    match.eventId || null,
      matchScore: Math.round(computeMatchScore(match, lk) * 10) / 10,
      picks: visible.map(p => ({
        market:    p.market    || '',
        marketKey: _marketToKey(p.market || ''),
        icon:      p.icon      || '',
        conf:      p.conf      || 'medium',
        sc:        typeof p.sc === 'number' ? Math.round(p.sc * 1000) / 1000 : 0,
        odds:      p.odds      != null ? p.odds      : null,
        modelOdds: p.modelOdds != null ? p.modelOdds : null,
        value:     p.value     || null,
        oddsIsEst: p.oddsIsEst || false,
        result:    null,
      })),
    });
  }

  if (payload.length === 0) return;

  try {
    const r = await fetch(SERVER, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(payload),
    });
    if (r.ok) {
      const res = await r.json();
      console.log(`[PicksSync] ✅ ${res.added} new, ${res.updated} updated → picks_history.json`);
    }
  } catch (_) {
    // Local server not running — silently ignore (GitHub Pages / offline mode)
  }
}

// ═══════════════════════════════════════════════════════
//  DATE FILTER — next 7 days only
// ═══════════════════════════════════════════════════════
// parseGermanDate + getRestDays → pick-engine.js

function isWithin7Days(dateStr) {
  const today = new Date(); today.setHours(0,0,0,0);
  const end   = new Date(today); end.setDate(end.getDate() + 7);
  const d = parseGermanDate(dateStr);
  return d >= today && d <= end;
}

function weekLabel() {
  const today = new Date();
  const end   = new Date(today); end.setDate(end.getDate() + 7);
  const fmt = (dt) => dt.toLocaleDateString('de-DE', {day:'numeric', month:'short'});
  return `${fmt(today)} – ${fmt(end)} ${end.getFullYear()}`;
}

// ═══════════════════════════════════════════════════════
//  DAY FILTER — global state + helpers
// ═══════════════════════════════════════════════════════
window._selectedDay  = 'all';   // 'all' or a date string like '05.04.2026'
window._currentLeague = 'overview';

function getDayLabel(dateStr) {
  const d = parseGermanDate(dateStr);
  const days = ['So','Mo','Di','Mi','Do','Fr','Sa'];
  return `<span class="day-name">${days[d.getDay()]}</span> ${d.getDate()}.${d.getMonth()+1}.`;
}

function buildDayFilterHtml(allWeekMatches) {
  // allWeekMatches = full unfiltered week for THIS view (used for chip counts)
  const todayMidnight = new Date(); todayMidnight.setHours(0,0,0,0);
  const isToday = ds => { const d = parseGermanDate(ds); d.setHours(0,0,0,0); return d.getTime() === todayMidnight.getTime(); };

  const dateSet = new Set(allWeekMatches.map(m => m.date));
  const dates = [...dateSet].sort((a,b) => parseGermanDate(a) - parseGermanDate(b));

  const allActive = window._selectedDay === 'all';
  const chips = [`<button class="day-chip${allActive?' active':''}" onclick="selectDay('all')">
    📅 <span class="day-name">Alle</span> <span class="day-count">${allWeekMatches.length}</span>
  </button>`];

  for (const date of dates) {
    const count   = allWeekMatches.filter(m => m.date === date).length;
    const active  = window._selectedDay === date;
    const todayCls = isToday(date) ? ' today-chip' : '';
    chips.push(`<button class="day-chip${active?' active':''}${todayCls}" onclick="selectDay('${date}')">
      ${getDayLabel(date)} <span class="day-count">${count}</span>
    </button>`);
  }

  return `<div class="day-filter">${chips.join('')}</div>`;
}

function selectDay(day) {
  window._selectedDay = day;
  renderLeague(window._currentLeague);
}

function applyDayFilter(matches) {
  if (window._selectedDay === 'all') return matches;
  return matches.filter(m => m.date === window._selectedDay);
}

