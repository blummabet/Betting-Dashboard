// ═══════════════════════════════════════════════════════
//  pick-engine.js — CocoBet Pick Engine
//  Extracted from season-finish.html (Apr 2026)
//
//  Contains:
//    · _pickBestLine()       — beste Handicap-Linie wählen
//    · deriveOdds()          — DNB/DC von 1X2 ableiten
//    · _poissonOver()        — Poisson Cumulative P(X > threshold)
//    · _poissonOdds()        — Poisson Odds mit Margin
//    · estimateCornersOdds() — Ecken-FV schätzen
//    · estimateCardsOdds()   — Karten-FV schätzen
//    · estimateBttsOdds()    — BTTS-FV schätzen
//    · estimateTeamGoalOdds()— Team-Tor-FV schätzen
//    · computeLineMovement() — Line Movement berechnen
//    · renderLineMovement()  — Line Movement HTML rendern
//    · const GATE            — Zentrale Negative-Edge-Schwellenwerte
//    · _hasNegEdge()         — Gate-Helper
//    · getBettingPicks()     — Haupt-Pick-Engine
//    · parseGermanDate()     — Datumsparsing (DD.MM.YYYY)
//    · getRestDays()         — Ruhetage berechnen
//
//  NO DOM dependencies except renderLineMovement().
//  All other functions run cleanly in Node.js.
//  Test: node test-pick-engine.js
// ═══════════════════════════════════════════════════════

function _pickBestLine(lines, targetOdds, minPt, maxPt) {
  if (!Array.isArray(lines) || !lines.length) return null;
  targetOdds = targetOdds || 1.62;
  const pool = (minPt != null || maxPt != null)
    ? lines.filter(l => (minPt == null || l.pt >= minPt) && (maxPt == null || l.pt <= maxPt))
    : lines;
  if (!pool.length) return null;
  return pool.reduce((best, l) =>
    !best || Math.abs(l.price - targetOdds) < Math.abs(best.price - targetOdds) ? l : best, null);
}

// ═══════════════════════════════════════════════════════
//  DERIVED ODDS HELPER (DNB + Doppelte Chance from 1X2)
// ═══════════════════════════════════════════════════════
// DNB Home fair odds: neutral on draw → 1 + P(away)/P(home)  [de-vigged, ~3% Pinnacle margin applied]
// DC 1X fair odds: covers home win + draw → 1 / (P(home) + P(draw))
function deriveOdds(raw) {
  if (!raw || !raw.hw || !raw.dr || !raw.aw) return raw || {};
  let ph, pd, pa;
  if (raw.hw_fair && raw.dr_fair && raw.aw_fair) {
    // Consensus fair odds available — no further devig needed, already margin-free.
    // Convert back to probabilities, re-normalise for floating-point safety.
    const _tot = 1/raw.hw_fair + 1/raw.dr_fair + 1/raw.aw_fair;
    ph = (1/raw.hw_fair) / _tot;
    pd = (1/raw.dr_fair) / _tot;
    pa = (1/raw.aw_fair) / _tot;
  } else {
    // Fallback: single-source devig from best available 1X2 odds.
    const tot = 1/raw.hw + 1/raw.dr + 1/raw.aw;  // total implied (>1 = overround)
    ph = (1/raw.hw) / tot;                         // de-vigged home win probability
    pd = (1/raw.dr) / tot;                         // de-vigged draw probability
    pa = (1/raw.aw) / tot;                         // de-vigged away win probability
  }
  const m  = 0.97;                              // ~3% Pinnacle-style margin applied to derived markets
  const r  = (x) => Math.round(x * 100) / 100;
  return {
    ...raw,
    dnbH: r((1 + pa/ph) * m),   // DNB Heimteam
    dnbA: r((1 + ph/pa) * m),   // DNB Auswärtsteam
    dc1X: r((1/(ph+pd)) * m),   // Doppelte Chance 1X
    dcX2: r((1/(pd+pa)) * m),   // Doppelte Chance X2
  };
}

// ═══════════════════════════════════════════════════════
//  POISSON MODEL — corners & cards fair value estimation
// ═══════════════════════════════════════════════════════
// Cumulative Poisson P(X > threshold) using Poisson(λ).
// threshold is the .5 line (e.g. 9.5 → pass 9, returns P(X>=10))
function _poissonOver(lambda, threshold) {
  if (lambda <= 0) return 0.5;
  const k = Math.floor(threshold); // P(X > k+0.5) = P(X >= k+1) = 1 - CDF(k)
  let cdf = 0, term = Math.exp(-lambda);
  for (let i = 0; i <= k; i++) {
    cdf += term;
    term *= lambda / (i + 1);
  }
  return Math.max(0.02, Math.min(0.98, 1 - cdf));
}
// Convert fair prob → bookmaker odds with given margin (default 6%).
function _poissonOdds(prob, margin) {
  margin = margin || 0.06;
  return Math.round((1 / prob) * (1 - margin) * 100) / 100;
}
// Estimate corners odds from expected corners total (Poisson model, 6% margin).
// Returns { co85, co95, co105, co115, cu85, cu95, oddsIsEst: true } — same keys as _parseOddsBets.
function estimateCornersOdds(lambda) {
  if (!lambda || lambda <= 0) return {};
  const r = { oddsIsEst: true };
  ['8.5','9.5','10.5','11.5'].forEach(line => {
    const l = parseFloat(line);
    const pOver = _poissonOver(lambda, l);
    const key = 'co' + line.replace('.','');
    r[key] = _poissonOdds(pOver);
    const ku = 'cu' + line.replace('.','');
    r[ku] = _poissonOdds(1 - pOver);
  });
  return r;
}
// Estimate cards odds from expected total cards (Poisson model, 7% margin — wider cards market).
// Returns { cards_o35, cards_o45, oddsIsEst: true }
function estimateCardsOdds(expectedCards) {
  if (!expectedCards || expectedCards <= 0) return {};
  const r = { oddsIsEst: true };
  const p35 = _poissonOver(expectedCards, 3.5);
  const p45 = _poissonOver(expectedCards, 4.5);
  r.cards_o35 = _poissonOdds(p35, 0.07);
  r.cards_o45 = _poissonOdds(p45, 0.07);
  return r;
}

// Estimate BTTS Yes/No odds from expected goals per team (Poisson, 7% margin).
// P(BTTS Yes) = P(home scores ≥ 1) × P(away scores ≥ 1) — independent Poisson events.
// lambdaH/lambdaA: adjusted expected goals (after fatigue + injury + motivation).
function estimateBttsOdds(lambdaH, lambdaA) {
  if (!lambdaH || !lambdaA || lambdaH <= 0 || lambdaA <= 0) return {};
  const pH = _poissonOver(lambdaH, 0.5);  // P(home scores ≥ 1)
  const pA = _poissonOver(lambdaA, 0.5);  // P(away scores ≥ 1)
  const pYes = Math.max(0.05, Math.min(0.92, pH * pA));
  return {
    bttsY: _poissonOdds(pYes,      0.07),
    bttsN: _poissonOdds(1 - pYes,  0.07),
    oddsIsEst: true,
  };
}
// Estimate Team Goals Over 1.5 odds from expected goals for one team (Poisson, 7% margin).
// P(team over 1.5) = P(team scores ≥ 2), clipped to sensible odds range.
function estimateTeamGoalOdds(lambdaTeam) {
  if (!lambdaTeam || lambdaTeam <= 0) return {};
  const pOver = _poissonOver(lambdaTeam, 1.5);  // P(X ≥ 2)
  return {
    over: _poissonOdds(Math.max(0.04, Math.min(0.94, pOver)),  0.07),
    under: _poissonOdds(Math.max(0.04, Math.min(0.94, 1 - pOver)), 0.07),
    oddsIsEst: true,
  };
}

// ═══════════════════════════════════════════════════════
//  LINE MOVEMENT — opening vs. current odds analysis
// ═══════════════════════════════════════════════════════

// Returns an array of movement rows (1X2 + O/U 2.5) or null if no meaningful move.
// ppShift > 0 = probability increased = odds shortened = money came in on this side.
// ppShift < 0 = probability decreased = odds drifted = money left / weak side.
// Returns null if max movement across all outcomes < 3pp (noise threshold).
// O/U rows carry label 'O25' / 'U25' and are appended after 1X2 rows.
function computeLineMovement(oddsOpen, oddsCurrent) {
  if (!oddsOpen || !oddsCurrent) return null;
  // 1X2 always shown (if data exists); O/U markets only shown when ≥3pp movement.
  // O3.5/U3.5 tracked in addition to O2.5/U2.5 — large moves on the 3.5 line
  // (e.g. known high-scoring teams) are informative and were previously invisible.
  const markets = [
    { label: '1',   key: 'hw',  ou: false },
    { label: 'X',   key: 'dr',  ou: false },
    { label: '2',   key: 'aw',  ou: false },
    { label: 'O25', key: 'o25', ou: true  },
    { label: 'U25', key: 'u25', ou: true  },
    { label: 'O35', key: 'o35', ou: true  },
    { label: 'U35', key: 'u35', ou: true  },
  ];
  const rows = [];
  for (const m of markets) {
    const o = parseFloat(oddsOpen[m.key]);
    const c = parseFloat(oddsCurrent[m.key]);
    if (!o || !c || isNaN(o) || isNaN(c) || o <= 1 || c <= 1) continue;
    const ppShift = Math.round(((1 / c) - (1 / o)) * 100);
    // O/U lines only shown when movement is meaningful (≥3pp) — static prices shown via pills
    if (m.ou && Math.abs(ppShift) < 3) continue;
    rows.push({ label: m.label, oddOpen: o, oddCurr: c, ppShift });
  }
  if (!rows.length) return null;
  const maxAbs = Math.max(...rows.map(r => Math.abs(r.ppShift)));
  if (maxAbs < 3) return null;  // below noise floor — skip rendering entirely
  return rows;
}

// Renders the LINE MOVEMENT strip HTML.
// picks: array from getBettingPicks() — used to colour-code confirming vs. contra moves.
function renderLineMovement(rows, picks, oddsD, isEstimated) {
  if (!rows || !rows.length) return '';

  // Determine which outcomes our picks align with (1X2 + O/U)
  const pickLabels = new Set();
  for (const p of (picks || [])) {
    const mkt = (p.market || '').toLowerCase();
    if (mkt.includes('heimsieg') || mkt.startsWith('1 ') || mkt === '1') pickLabels.add('1');
    else if (mkt.includes('auswärtssieg') || mkt.startsWith('2 ') || mkt === '2') pickLabels.add('2');
    else if (mkt.includes('unentschieden') || mkt.includes('remis')) pickLabels.add('X');
    // DNB/DC picks: treat as aligned with the primary outcome they protect
    else if (mkt.includes('dnb') && mkt.includes('heim')) pickLabels.add('1');
    else if (mkt.includes('dnb') && mkt.includes('auswärts')) pickLabels.add('2');
    else if (mkt.includes('doppelte chance') && (mkt.includes('1x') || mkt.includes('1/'))) { pickLabels.add('1'); pickLabels.add('X'); }
    else if (mkt.includes('doppelte chance') && (mkt.includes('x2') || mkt.includes('/2'))) { pickLabels.add('2'); pickLabels.add('X'); }
    // O/U picks: align with Over or Under row
    else if (mkt.includes('over') || mkt.includes('o2.5') || mkt === 'over 2.5' || mkt.includes('btts')) pickLabels.add('O25');
    else if (mkt.includes('under') || mkt.includes('u2.5') || mkt === 'under 2.5') pickLabels.add('U25');
  }

  // Human-readable labels for display
  const _lmDisplayLabel = { '1': '1', 'X': 'X', '2': '2', 'O25': 'O2.5', 'U25': 'U2.5', 'O35': 'O3.5', 'U35': 'U3.5' };

  const rowsHtml = rows.map(r => {
    const abs = Math.abs(r.ppShift);
    const dispLbl = _lmDisplayLabel[r.label] || r.label;
    if (abs < 3) {
      // Flat — show current odds, no arrow
      return `<div class="lm-row">
        <span class="lm-label">${dispLbl}</span>
        <span class="lm-arrow lm-flat">──</span>
        <span class="lm-open">${r.oddOpen.toFixed(2)}</span>
        <span class="lm-sep">→</span>
        <span class="lm-curr lm-flat">${r.oddCurr.toFixed(2)}</span>
        <span class="lm-pp lm-flat"></span>
      </div>`;
    }

    const shortened = r.ppShift > 0;  // prob up = odds down = money came in
    const arrowStr  = abs >= 8 ? (shortened ? '⬇⬇' : '⬆⬆')
                    : abs >= 5 ? (shortened ? '⬇'  : '⬆')
                    :            (shortened ? '↘'  : '↗');

    // Colour logic:
    // - move aligns with a pick we have → green (confirming)
    // - move contradicts a pick direction → red (contra)
    // - move on a side with no pick → blue (neutral, informational)
    // - drift (drifting) → muted gray
    let cls;
    if (pickLabels.has(r.label)) {
      cls = shortened ? 'lm-confirm' : 'lm-contra';
    } else {
      cls = shortened ? 'lm-neutral-short' : 'lm-neutral-drift';
    }

    const sharpBadge = (abs >= 8 && shortened)
      ? `<span class="lm-sharp">SHARP</span>` : '';
    const sign = r.ppShift > 0 ? '+' : '';

    return `<div class="lm-row">
      <span class="lm-label">${dispLbl}</span>
      <span class="lm-arrow ${cls}">${arrowStr}</span>
      <span class="lm-open">${r.oddOpen.toFixed(2)}</span>
      <span class="lm-sep">→</span>
      <span class="lm-curr ${cls}">${r.oddCurr.toFixed(2)}</span>
      <span class="lm-pp ${cls}">(${sign}${r.ppShift}pp)${sharpBadge}</span>
    </div>`;
  }).join('');

  const hasSharp = rows.some(r => Math.abs(r.ppShift) >= 8 && r.ppShift > 0);
  const stripClass = hasSharp ? 'lm-strip lm-strip-sharp' : 'lm-strip';
  const titleIcon  = hasSharp ? '📈' : '📊';

  // O2.5 / U2.5 pills — only from real bookmaker quotes, not estimated
  let ouHtml = '';
  if (oddsD && !isEstimated) {
    const _pill = (lbl, val) =>
      `<div class="lm-ou-pill"><span class="lm-ou-pill-lbl">${lbl}</span><span class="lm-ou-pill-val">${val.toFixed(2)}</span></div>`;
    if (oddsD.o25) ouHtml += _pill('O2.5', oddsD.o25);
    if (oddsD.u25) ouHtml += _pill('U2.5', oddsD.u25);
  }
  const ouBlock = ouHtml ? `<div class="lm-ou-pills">${ouHtml}</div>` : '';

  return `<div class="${stripClass}">
    <div class="lm-header">
      <div style="display:flex;align-items:center;gap:8px">
        <span class="lm-title">${titleIcon} LINE MOVEMENT</span>
        <span class="lm-sub">Opening → Aktuell</span>
      </div>
      ${ouBlock}
    </div>
    <div class="lm-rows">${rowsHtml}</div>
  </div>`;
}

// ═══════════════════════════════════════════════════════
//  BETTING PICKS ENGINE — NEGATIVE-EDGE GATE THRESHOLDS
// ═══════════════════════════════════════════════════════
// Single source of truth for all FV gate thresholds.
// Referenced in getBettingPicks() pick blocks AND in the
// renderFixtureCard() inline validator.
// SYNC: when changing any value here also update check_picks_logic.py
// (Python validator uses same thresholds in comments — search "SYNC:GATE").
const GATE = {
  GOALS_REAL: 0.12,   // Over 2.5 / Over 3.5 / BTTS  (real bookie odds)
  TEAM_REAL:  0.12,   // Heim/Ausw über 1.5  (real bookie odds)
  TEAM_EST:   0.15,   // Heim/Ausw über 1.5  (estimated odds — wider, model uncertainty)
  AH_REAL:    0.14,   // Asian Handicap  (real only; AH model less precise than goals)
  CORN_REAL:  0.10,   // Ecken Over  (real bookie odds)
  CORN_EST:   0.15,   // Ecken Over  (estimated odds)
};

// ─────────────────────────────────────────────────────
//  _hasNegEdge — negative-edge guard helper
// ─────────────────────────────────────────────────────
// Returns true when the implied probability exceeds the
// model fair probability by more than the gate threshold,
// meaning the bet has negative expected value and should
// be suppressed.
//
// fairProb  — model fair probability (0–1), or null
// odds      — decimal bookie odds, or null
// isEst     — true when odds are model-estimated (not real bookie feed)
// realGate  — GATE.* key to use for real bookie odds  (e.g. GATE.GOALS_REAL)
// estGate   — GATE.* key to use for estimated odds    (e.g. GATE.TEAM_EST),
//             or null to suppress the pick entirely when isEst is true
//
// Usage example (replacing inline pattern):
//   if (!_hasNegEdge(_o25FairProb, _o25Odds, false, GATE.GOALS_REAL, null)) { … }
function _hasNegEdge(fairProb, odds, isEst, realGate, estGate) {
  if (fairProb == null || odds == null) return false;
  if (isEst && estGate == null) return true;          // no est-odds variant → always suppress
  const thresh = isEst ? estGate : realGate;
  return (1 / odds) - fairProb > thresh;
}

// ═══════════════════════════════════════════════════════
//  BETTING PICKS ENGINE
// ═══════════════════════════════════════════════════════
function getBettingPicks(match, odds, leagueKey) {
  const hc = (match.homeStake?.labels||[]).map(l=>l.c);
  const ac = (match.awayStake?.labels||[]).map(l=>l.c);
  const bothRed  = hc.includes('red')  && ac.includes('red');
  const bothGold = hc.includes('gold') && ac.includes('gold');
  const bothBlue = hc.includes('blue') && ac.includes('blue');
  const anyRed   = hc.includes('red')  || ac.includes('red');
  const anyGold  = hc.includes('gold') || ac.includes('gold');
  const anyBlue  = hc.includes('blue') || ac.includes('blue');
  const o = deriveOdds(odds || {});

  // ── Inject Poisson-estimated corners/cards odds when real bookmaker quotes missing ──
  // The Odds API has no corners/cards markets — we derive fair value via Poisson model.
  // Marked oddsIsEst=true → rendered with "~" prefix so user knows it's model-estimated.
  // cornersEst is computed below, so we populate lazily inside the pick blocks instead.
  // Cards: expected ≈ referee average if known, else league-calibrated base × pressure
  // (populated in Specialist Pick block where _refAvg is available)

  // ── League-specific Over/Under probability offset ─────────────────────────
  // High-scoring leagues (ENG, GER, AUT, TUR, SCO) get a positive cap offset.
  // Defensive leagues (ITA, FRA) get a negative offset.
  // This corrects the single-cap model that was tuned on mid-scoring leagues.
  const _lgCap = ({ENG:0.05, GER:0.05, AUT:0.04, TUR:0.03, SCO:0.03, NED:0.03, BEL:0.02, POR:0.01, POL:0, CRO:0, HUN:0, ESP:0, ITA:-0.04, FRA:-0.04})[leagueKey] || 0;

  // De-vig base probabilities — prefer Konsens-Devig (hw_fair) when available;
  // fall back to single-source Pinnacle de-vig if consensus is missing.
  const _cn     = odds?._cn || 0;                                // number of contributing bookmakers
  const _hasFair = odds?.hw_fair && odds?.dr_fair && odds?.aw_fair;
  let _bkrPH, _bkrPD, _bkrPA;
  if (_hasFair) {
    // hw_fair/dr_fair/aw_fair are fair ODDS (e.g. 2.13), NOT probabilities.
    // Convert: prob = 1/odds, then normalise (sum should be ~1.0 since already margin-free).
    const _fairTot = 1/odds.hw_fair + 1/odds.dr_fair + 1/odds.aw_fair;
    _bkrPH = (1/odds.hw_fair) / _fairTot;
    _bkrPD = (1/odds.dr_fair) / _fairTot;
    _bkrPA = (1/odds.aw_fair) / _fairTot;
  } else {
    const _bkrTot = (odds?.hw && odds?.dr && odds?.aw) ? (1/odds.hw + 1/odds.dr + 1/odds.aw) : 0;
    _bkrPH = _bkrTot > 0 ? (1/odds.hw) / _bkrTot : null;  // de-vigged home win prob
    _bkrPD = _bkrTot > 0 ? (1/odds.dr) / _bkrTot : null;  // de-vigged draw prob
    _bkrPA = _bkrTot > 0 ? (1/odds.aw) / _bkrTot : null;  // de-vigged away win prob
  }

  // ── Form signals ──────────────────────────────────────
  const hF = match.homeForm || {}, aF = match.awayForm || {};
  const hGoals  = hF.goalsPerGame    ?? 1.4;
  const aGoals  = aF.goalsPerGame    ?? 1.4;
  const hConc   = hF.concededPerGame ?? 1.3;
  const aConc   = aF.concededPerGame ?? 1.3;
  const hStreak = hF.streak ?? 0;
  const aStreak = aF.streak ?? 0;
  const hFS     = hF.formScore ?? 0.5;
  const aFS     = aF.formScore ?? 0.5;

  // ── Player context snippets (from squad_cache via update_dashboard.py) ──────
  // topAttacker/keyDefender are null when squad data unavailable or stats too low.
  // Injected into goal- and result-pick reason texts to make them concrete.
  // Primary: homeStake (stake teams) — Fallback: homeSquad (all teams incl. non-stake opponents like Real Madrid)
  const _hTop = match.homeStake?.topAttacker ?? match.homeSquad?.topAttacker ?? null;
  const _aTop = match.awayStake?.topAttacker ?? match.awaySquad?.topAttacker ?? null;
  const _hDef = match.homeStake?.keyDefender ?? match.homeSquad?.keyDefender ?? null;
  const _aDef = match.awayStake?.keyDefender ?? match.awaySquad?.keyDefender ?? null;

  const _posDE = {G:'TW', D:'VER', M:'MF', F:'ST'};
  // "Saka 11G+8A" or "Haaland 26G"
  const _fmtAtt = (p) => {
    if (!p) return '';
    const ga = p.assists > 0 ? `${p.goals}G+${p.assists}A` : `${p.goals}G`;
    return `${p.name} ${ga}`;
  };
  // "Saliba (VER)" — rating only shown when ≥7.0
  const _fmtDef = (p) => {
    if (!p) return '';
    const rtg = p.rating >= 7.0 ? ` · ${p.rating.toFixed(1)} Rtg` : '';
    return `${p.name} (${_posDE[p.pos]||p.pos}${rtg})`;
  };
  // Short last word of team name ("Manchester City" → "City")
  const _teamShort = (name) => (name||'').split(' ').slice(-1)[0];

  // Pre-built lines — appended inside pick reason strings below
  const _attLineHome = _hTop ? `${_teamShort(match.home)}: ${_fmtAtt(_hTop)}` : '';
  const _attLineAway = _aTop ? `${_teamShort(match.away)}: ${_fmtAtt(_aTop)}` : '';
  // Combined attacker line for goal picks (both teams)
  const _bothAttLine = (_attLineHome && _attLineAway) ? `<br>⚽ ${_attLineHome} · ${_attLineAway}`
    : (_attLineHome || _attLineAway) ? `<br>⚽ ${_attLineHome || _attLineAway}` : '';
  // Defender lines for under/clean-sheet picks
  const _defLineHome = _hDef ? `${_teamShort(match.home)}: ${_fmtDef(_hDef)}` : '';
  const _defLineAway = _aDef ? `${_teamShort(match.away)}: ${_fmtDef(_aDef)}` : '';
  const _bothDefLine = (_defLineHome && _defLineAway) ? `<br>🛡️ ${_defLineHome} · ${_defLineAway}`
    : (_defLineHome || _defLineAway) ? `<br>🛡️ ${_defLineHome || _defLineAway}` : '';

  // ── H2H signals (recency-weighted) ───────────────────
  // If h2h.lastMeetingYear is set, duel data older than ~3y gets discounted:
  // 1y ago → weight 0.88  |  3y → 0.64  |  5y → 0.40  |  7y+ → 0.25
  const h2h      = match.h2h || {};
  const h2hN     = h2h.games || 0;
  const h2hAge   = h2h.lastMeetingYear ? (new Date().getFullYear() - h2h.lastMeetingYear) : 1;
  const h2hW     = Math.max(0.25, 1 - h2hAge * 0.12);
  const drawRate    = h2hN >= 3 ? (h2h.draws||0)/h2hN * h2hW + 0.26*(1-h2hW) : 0.25;
  const homeWinRate = h2hN >= 3 ? (h2h.homeWins||0)/h2hN * h2hW + 0.46*(1-h2hW) : 0.45;
  const awayWinRate = h2hN >= 3 ? (h2h.awayWins||0)/h2hN * h2hW + 0.30*(1-h2hW) : 0.30;

  // ── H2H goals patterns (from API, Pro plan) ───────────────────────────────
  // over25Rate / bttsRate from real historical goals data — weighted by recency
  // If API H2H not available, these modifiers are neutral (0).
  // Supplement with prematch-data.json H2H when match config lacks over25Rate/bttsRate:
  // update_dashboard.py writes simplified H2H to HTML (no over25Rate/bttsRate),
  // while prematch-server.js fetches the full H2H into window._preMatchData.
  const _pmH2h      = (window._preMatchData?.[`${match.home}|${match.away}`] || null)?.h2h || null;
  const _h2hOver25  = h2h.over25Rate ?? _pmH2h?.over25Rate ?? null;   // 0.0–1.0 or null
  const _h2hBtts    = h2h.bttsRate   ?? _pmH2h?.bttsRate   ?? null;
  const _h2hAvgG    = h2h.avgGoals   ?? _pmH2h?.avgGoals   ?? null;
  const _h2hSample  = h2hN >= 5;  // only apply when ≥5 games for reliability

  // Over 2.5 H2H modifier: +0.12 if ≥70%, +0.06 if ≥60%, -0.04 if ≤40%, -0.08 if ≤30%, -0.14 if ≤20%
  // Extended downside: 40-50% now gets -0.04 (was 0) — e.g. 40% H2H is a real warning signal.
  const _h2hO25Mod  = (!_h2hSample || _h2hOver25 == null) ? 0
    : _h2hOver25 >= 0.70 ?  0.12
    : _h2hOver25 >= 0.60 ?  0.06
    : _h2hOver25 <= 0.20 ? -0.14
    : _h2hOver25 <= 0.30 ? -0.08
    : _h2hOver25 <= 0.40 ? -0.04   // below neutral zone → small negative signal
    : 0;

  // BTTS H2H modifier: +0.10 if ≥70%, +0.05 if ≥60%, -0.06 if ≤35%, -0.10 if ≤25%, -0.16 if ≤15%
  // Extended downside: 26-35% now gets -0.06 (was 0). 30% BTTS in 10 games is a real negative signal
  // (mirrors the ≤40% fix in _h2hO25Mod). Symmetric: suppresses BTTS Ja, boosts BTTS Nein.
  const _h2hBttsMod = (!_h2hSample || _h2hBtts == null) ? 0
    : _h2hBtts >= 0.70 ?  0.10
    : _h2hBtts >= 0.60 ?  0.05
    : _h2hBtts <= 0.15 ? -0.16
    : _h2hBtts <= 0.25 ? -0.10
    : _h2hBtts <= 0.35 ? -0.06   // below neutral zone → negative signal (e.g. Galatasaray/Fenerbahçe 30%)
    : 0;

  // ── H2H lastResults recency modifier ────────────────────────────────────────
  // lastResults = ['W','D','L','W','W'] (W = home team won that meeting, oldest→newest)
  // Weighted average: most recent game counts most. Applied to result picks only (±0.07 max).
  // This captures TREND: home team dominating recent H2H meetings → real signal beyond overall rate.
  const _h2hLastResults = Array.isArray(h2h.lastResults) ? h2h.lastResults : [];
  let _h2hRecencyMod = 0; // positive = home wins recent H2H, negative = away wins recent H2H
  if (_h2hLastResults.length >= 3) {
    const _wr = [0.10, 0.15, 0.25, 0.25, 0.25]; // weight: oldest→newest (last slot = most recent)
    const _offset = Math.max(0, _wr.length - _h2hLastResults.length);
    let _wScore = 0, _wTotal = 0;
    for (let _ri = 0; _ri < _h2hLastResults.length; _ri++) {
      const _w = _wr[_offset + _ri] ?? 0.20;
      _wScore += (_h2hLastResults[_ri] === 'W' ? 1.0 : _h2hLastResults[_ri] === 'D' ? 0.5 : 0.0) * _w;
      _wTotal += _w;
    }
    const _recScore = _wTotal > 0 ? _wScore / _wTotal : 0.5; // 0.0–1.0, 0.5 = neutral
    _h2hRecencyMod = (_recScore - 0.5) * 0.14; // maps 0..1 → −0.07..+0.07
  }

  // ── H2H avgGoals secondary Over/Under modifier ───────────────────────────────
  // Applied IN ADDITION to _h2hO25Mod (which is based on over25Rate).
  // avgGoals provides an independent confirmation: high Ø tore → stronger Over signal.
  // Only applied when _h2hSample (≥5 games) and avgGoals available.
  // H2H avgGoals modifier — symmetric: positive boosts Over 2.5 / suppresses Under 2.5; negative does the inverse.
  // Extended downside: 2.0–2.5 range now gets -0.04 (was 0). avgG of 2.1 below the 2.5 line is a real warning.
  const _h2hAvgGMod = (_h2hSample && _h2hAvgG != null)
    ? _h2hAvgG >= 3.5 ?  0.05
    : _h2hAvgG >= 3.0 ?  0.03
    : _h2hAvgG >= 2.8 ?  0.01
    : _h2hAvgG <= 1.6 ? -0.08   // very low scoring H2H
    : _h2hAvgG <= 2.0 ? -0.06   // clearly below line
    : _h2hAvgG <= 2.5 ? -0.04   // borderline — below the 2.5 threshold
    : 0
    : 0;

  // Avg goals H2H note for pick reasons
  // With API data: full goals stats. With static config only: win rate summary.
  const _h2hGoalNote = (_h2hSample && _h2hAvgG != null)
    ? `<br>📊 H2H (${h2hN} Duelle): Ø ${_h2hAvgG} Tore/Spiel · ${Math.round((_h2hOver25||0)*100)}% Über 2.5 · ${Math.round((_h2hBtts||0)*100)}% BTTS`
    : (_h2hSample && h2hN >= 5)
    ? `<br>📊 H2H (${h2hN} Duelle): ${h2h.homeWins||0}H / ${h2h.draws||0}U / ${h2h.awayWins||0}A — Heimsieg-Rate ${Math.round((h2h.homeWins||0)/h2hN*100)}%`
    : '';

  // ── Real xG & venue stats from understat cache (injected by refresh_stats.py) ───
  const _ts    = window._teamStats || {};
  const hStat  = _ts[leagueKey]?.[match.home] || {};
  const aStat  = _ts[leagueKey]?.[match.away] || {};
  const _hXG   = hStat.xG_home  || null;   // home team avg xG at home
  const _hXGA  = hStat.xGA_home || null;   // home team avg xGA at home
  const _aXG   = aStat.xG_away  || null;   // away team avg xG away
  const _aXGA  = aStat.xGA_away || null;   // away team avg xGA away
  const _hHWR  = hStat.homeWinRate ?? null; // home team actual home win rate
  const _aAWR  = aStat.awayWinRate ?? null; // away team actual away win rate
  // ── Clean sheet & failed-to-score rates (from refresh_stats.py) ──────────────
  // cleanSheetHome  = % of home games where home team kept a clean sheet
  // failedToScoreAway = % of away games where away team scored 0 goals
  // These directly drive BTTS No + Under calibration (venue-specific, full-season basis)
  const _hCSHome  = hStat.cleanSheetHome   ?? null;
  const _aCSAway  = aStat.cleanSheetAway   ?? null;
  const _hFTSHome = hStat.failedToScoreHome ?? null;
  const _aFTSAway = aStat.failedToScoreAway ?? null;
  // ── Corner stats (from refresh_stats.py fixture-level batch fetch) ────────────
  // cornersHome = avg corners when team plays at home  |  cornersAway = avg corners away
  // Used to replace the formula-based cornersEst when real data is available.
  const _hCornersHome = hStat.cornersHome ?? null;  // home team: corners per home game
  const _aCornersHome = aStat.cornersHome ?? null;  // away team: corners when they play at home (not relevant for this match, but cross-ref)
  const _hCornersAway = hStat.cornersAway ?? null;  // home team: corners per away game
  const _aCornersAway = aStat.cornersAway ?? null;  // away team: corners per away game
  // xGSource — "shots" if upgraded by teams/statistics, "goals" otherwise
  const _hXGSource = hStat.xgSource ?? 'goals';
  const _aXGSource = aStat.xgSource ?? 'goals';
  // ── API Prediction (from prematch-server.js /predictions endpoint) ───────────
  // Independent model signal: expected goals, result %, Poisson distribution
  const _apiPred    = match.apiPrediction   || null;
  const _apiGoalsH  = _apiPred?.goalsHome   ?? null;  // API-expected goals for home team
  const _apiGoalsA  = _apiPred?.goalsAway   ?? null;  // API-expected goals for away team
  const _apiUO      = _apiPred?.underOver   ?? null;  // "Over 2.5" | "Under 2.5" | null
  const _apiPctH    = _apiPred?.pctHome     ?? null;  // 0–100
  const _apiPctD    = _apiPred?.pctDraw     ?? null;
  const _apiPctA    = _apiPred?.pctAway     ?? null;
  const _apiPoiH    = _apiPred?.poissonHome ?? null;  // Poisson win% (0–100)
  const _apiPoiD    = _apiPred?.poissonDraw ?? null;
  const _apiPoiA    = _apiPred?.poissonAway ?? null;
  // Blended API expected goals — used when xGBased=false (non-Big5 or no refresh_stats run)
  const _apiExpG = (_apiGoalsH !== null && _apiGoalsA !== null) ? (_apiGoalsH + _apiGoalsA) : null;

  // ── Dynamic blend ratio: more bookmakers → trust consensus more ──
  // _cn is the number of contributing bookmakers from Konsens-Devig.
  // ≥5 books: 90% market / 10% API | ≥3: 87% | ≥2: 83% | <2: 80%
  const _wBkr = _hasFair ? (_cn >= 5 ? 0.90 : _cn >= 3 ? 0.87 : _cn >= 2 ? 0.83 : 0.80) : 0.80;
  const _wApi = 1 - _wBkr;

  // ── Blended fair probabilities: dynamic market weight + API prediction pct ──
  // When both signals available: blend for sharpest estimate.
  // When only one: use that one. When neither: null (pure formula fallback).
  const _fairPH = (_bkrPH !== null && _apiPctH !== null)
    ? _bkrPH * _wBkr + (_apiPctH / 100) * _wApi
    : (_bkrPH ?? (_apiPctH !== null ? _apiPctH / 100 : null));
  const _fairPD = (_bkrPD !== null && _apiPctD !== null)
    ? _bkrPD * _wBkr + (_apiPctD / 100) * _wApi
    : (_bkrPD ?? (_apiPctD !== null ? _apiPctD / 100 : null));
  const _fairPA = (_bkrPA !== null && _apiPctA !== null)
    ? _bkrPA * _wBkr + (_apiPctA / 100) * _wApi
    : (_bkrPA ?? (_apiPctA !== null ? _apiPctA / 100 : null));

  // ── Line movement nudge ─────────────────────────────────────────────────────
  // ppShift = (1/current − 1/open) × 100 → positive means market moved toward that outcome.
  // We apply a small nudge to mp: +0.015 per full pp of steam toward home/away/draw.
  // Cap at ±3pp to avoid overweighting noisy openers.
  const _pmEntry = window._preMatchData?.[`${match.home}|${match.away}`] || null;
  const _oOpen   = _pmEntry?.odds_open || null;
  let _lmH = 0, _lmD = 0, _lmA = 0, _lmO = 0, _lmU = 0;
  if (_oOpen && odds?.hw && odds?.dr && odds?.aw) {
    const _ppH = Math.round(((1/odds.hw)  - (1/(_oOpen.hw  || odds.hw)))  * 100);
    const _ppD = Math.round(((1/odds.dr)  - (1/(_oOpen.dr  || odds.dr)))  * 100);
    const _ppA = Math.round(((1/odds.aw)  - (1/(_oOpen.aw  || odds.aw)))  * 100);
    _lmH = Math.max(-0.045, Math.min(0.045, _ppH * 0.015));
    _lmD = Math.max(-0.045, Math.min(0.045, _ppD * 0.015));
    _lmA = Math.max(-0.045, Math.min(0.045, _ppA * 0.015));
  }
  // O/U 2.5 line movement nudge — used in goals pick mp adjustments
  if (_oOpen && odds?.o25 && odds?.u25 && _oOpen.o25 && _oOpen.u25) {
    const _ppO = Math.round(((1/odds.o25) - (1/_oOpen.o25)) * 100);
    const _ppU = Math.round(((1/odds.u25) - (1/_oOpen.u25)) * 100);
    _lmO = Math.max(-0.045, Math.min(0.045, _ppO * 0.015));
    _lmU = Math.max(-0.045, Math.min(0.045, _ppU * 0.015));
  }

  // ── Comparison signals from API /predictions endpoint ─────────────────────────
  // Each field: {home: 0–100, away: 0–100} (higher = better for that side)
  const _compForm  = _apiPred?.compForm  ?? null;  // recent form comparison
  const _compAtt   = _apiPred?.compAtt   ?? null;  // attack strength comparison
  const _compDef   = _apiPred?.compDef   ?? null;  // defensive strength comparison
  const _compGoals = _apiPred?.compGoals ?? null;  // goals comparison
  // Compute differentials: positive = home has edge, negative = away has edge
  const _compFormDiff  = _compForm  ? _compForm.home  - _compForm.away  : null;  // +30 → home clearly better form
  const _compAttDiff   = _compAtt   ? _compAtt.home   - _compAtt.away   : null;
  const _compDefDiff   = _compDef   ? _compDef.home   - _compDef.away   : null;  // positive = home defends better
  const _compGoalsDiff = _compGoals ? _compGoals.home - _compGoals.away : null;

  // ── Season-level stats from refresh_stats.py (formation, streaks) ─────────────
  const _hFormation  = hStat.formation       ?? null;  // e.g. "4-3-3"
  const _aFormation  = aStat.formation       ?? null;
  const _hBigWinStr  = hStat.biggestWinStreak  ?? null;
  const _hBigLoseStr = hStat.biggestLoseStreak ?? null;
  const _aBigWinStr  = aStat.biggestWinStreak  ?? null;
  const _aBigLoseStr = aStat.biggestLoseStreak ?? null;
  const _hCurStreak  = hStat.currentStreak   ?? null;  // +N=win, -N=loss, 0=neutral
  const _aCurStreak  = aStat.currentStreak   ?? null;
  // Parse formation → last digit = number of forwards (offensive indicator)
  // 4-3-3 → 3 fwd (offensive), 4-5-1 → 1 fwd (defensive), 4-4-2 → neutral
  const _fwds = (f) => { if (!f) return null; const p = f.split('-'); return p.length >= 2 ? parseInt(p[p.length-1]) : null; };
  const _hFwds = _fwds(_hFormation);  // null if unknown
  const _aFwds = _fwds(_aFormation);
  // Formation modifier: 3+ fwd = offensive (+0.07 xG modifier), 1 fwd = defensive (-0.07)
  const _hFormMod = _hFwds === null ? 0 : _hFwds >= 3 ? 0.07 : _hFwds <= 1 ? -0.07 : 0;
  const _aFormMod = _aFwds === null ? 0 : _aFwds >= 3 ? 0.07 : _aFwds <= 1 ? -0.07 : 0;
  const _hElo  = hStat.elo || null;         // ClubElo rating home team
  const _aElo  = aStat.elo || null;         // ClubElo rating away team
  // eloDiff > 0 = home stronger; <0 = away stronger
  const eloDiff    = (_hElo && _aElo) ? Math.round(_hElo - _aElo) : null;
  const eloHomeFav = eloDiff !== null && eloDiff >  150;  // clear home Elo edge
  const eloAwayFav = eloDiff !== null && eloDiff < -150;  // clear away Elo edge
  const eloClose   = eloDiff !== null && Math.abs(eloDiff) <  30;  // Elo-balanced
  // Human-readable Elo label for reason texts (only when both available)
  const eloLabel   = (_hElo && _aElo)
    ? `Elo ${Math.round(_hElo)} vs ${Math.round(_aElo)} (Δ${eloDiff >= 0 ? '+' : ''}${eloDiff})`
    : null;
  const xGBased = !!(_hXG && _hXGA && _aXG && _aXGA);

  // ── xG Fairness (from refresh_stats.py — actual goals ÷ expected goals) ──
  // > 1.15 = overperforming xG → likely to regress downward (lucky)
  // < 0.85 = underperforming xG → likely to regress upward (unlucky)
  const _hFair  = hStat.xg_fairness_home ?? null;  // home team at home
  const _aFair  = aStat.xg_fairness_away ?? null;  // away team away
  // How much to nudge result pick confidence based on fairness
  // Overperforming home team → expect fewer goals → home win less likely → mild penalty
  // Underperforming home team → regression due → mild boost
  const _hFairMod = _hFair == null ? 0
                  : _hFair > 1.25  ? -0.07   // home is very lucky, regression likely
                  : _hFair > 1.12  ? -0.04
                  : _hFair < 0.75  ?  0.07   // home badly unlucky, positive regression due
                  : _hFair < 0.88  ?  0.04
                  : 0;
  const _aFairMod = _aFair == null ? 0
                  : _aFair > 1.25  ? -0.07   // away is very lucky
                  : _aFair > 1.12  ? -0.04
                  : _aFair < 0.75  ?  0.07   // away badly unlucky
                  : _aFair < 0.88  ?  0.04
                  : 0;
  // Human-readable fairness note for pick reasons (only shown when meaningful)
  const _hFairNote = _hFair == null ? ''
    : _hFair > 1.12 ? ` (Achtung: ${match.home} überperformt xG um ${Math.round((_hFair-1)*100)}% — Regression möglich)`
    : _hFair < 0.88 ? ` (${match.home} unterperformt xG um ${Math.round((1-_hFair)*100)}% — positiver Trend erwartet)`
    : '';
  const _aFairNote = _aFair == null ? ''
    : _aFair > 1.12 ? ` (Achtung: ${match.away} überperformt xG um ${Math.round((_aFair-1)*100)}% — Regression möglich)`
    : _aFair < 0.88 ? ` (${match.away} unterperformt xG um ${Math.round((1-_aFair)*100)}% — positiver Trend erwartet)`
    : '';

  // ── Season urgency ────────────────────────────────────
  // roundsLeft is auto-calculated by update_dashboard.py from real standings.
  // The closer to season end, the more every point matters — teams can't afford draws.
  const _rl           = match.roundsLeft ?? 99;
  const urgencyHigh   = _rl <= 3;   // 3 or fewer rounds: critical, no margin left
  const urgencyMed    = _rl <= 6;   // 6 or fewer: decisive phase, pressure elevated
  // Granular pressure boost — scales continuously with rounds left.
  // A team needing a win at round 1 faces catastrophically higher stakes than at round 6.
  // 1 round → +0.28, 2 → +0.22, 3 → +0.16, 4 → +0.11, 5 → +0.08, 6 → +0.06, 7+ → 0
  const _pressureBoost = _rl <= 1 ? 0.28 : _rl <= 2 ? 0.22 : _rl <= 3 ? 0.16
                       : _rl <= 4 ? 0.11 : _rl <= 5 ? 0.08 : _rl <= 6 ? 0.06 : 0;
  // "Must-win" flag: ANY team with a stake (gold/red/blue/orange/yellow/purple) has pressure
  // in the decisive phase — not just relegation or title teams.
  // hc/ac are arrays like ['red'] or ['gold','blue'] — use .length
  const homeHasStake  = hc.length > 0;
  const awayHasStake  = ac.length > 0;

  // ── Motivation Tracker ────────────────────────────────────────────────────
  // Teams whose season outcome is already mathematically confirmed have reduced motivation:
  // 'none' = confirmed champion/relegated/qualified → expect rotation, zero-pressure play
  // 'low'  = nearly confirmed (miracle needed to change outcome) → partial reduction
  // 'full' = actively fighting (default)
  // Computed in update_dashboard.py → calc_motivation() based on points gap vs. rounds left.
  const hMotiv = match.homeStake?.motivationLevel || 'full';
  const aMotiv = match.awayStake?.motivationLevel || 'full';
  const hMotivNone = hMotiv === 'none';
  const aMotivNone = aMotiv === 'none';
  const hMotivLow  = hMotiv === 'low';
  const aMotivLow  = aMotiv === 'low';

  // Must-win only applies when the team is STILL fighting with full motivation.
  // 'low' teams (mathematically unlikely) and 'none' (confirmed) don't play with real urgency.
  // Matches Python: mustWin = pressure.mustWin AND motiv == 'full'
  const homeNeedsWin  = urgencyMed && homeHasStake && hMotiv === 'full';
  const awayNeedsWin  = urgencyMed && awayHasStake && aMotiv === 'full';
  const bothNeedWin   = homeNeedsWin && awayNeedsWin;
  // Urgency label for pick reason texts — graduated language based on severity
  const urgencyLabel  = _rl <= 1 ? `🚨 LETZTE RUNDE — dieser Sieg kann alles entscheiden`
                      : _rl <= 2 ? `🔥 Nur noch ${_rl} Runden — kein Spielraum mehr`
                      : _rl <= 3 ? `⚠️ Noch ${_rl} Runden — jetzt wird Meister und Absteiger entschieden`
                      : urgencyMed ? `📍 ${_rl} Runden verbleibend — entscheidende Phase`
                      : null;

  // ── Pressure context helpers — used across PICK 1, 2 and 3 ──────────────
  // Defined here so all pick blocks can reference them without re-calculation.
  const _anyNeedsWin = homeNeedsWin || awayNeedsWin;
  // Human-readable team labels (color-aware, motivation-aware)
  const _pHLabel = hMotivNone
    ? (hc.includes('gold') ? `${match.home} bereits Meister` : hc.includes('red') ? `${match.home} bereits abgestiegen` : `${match.home} gesichert`)
    : homeNeedsWin
    ? (hc.includes('gold') ? `${match.home} im Titelkampf` : hc.includes('red') ? `${match.home} im Abstiegskampf` : `${match.home} unter Druck`)
    : '';
  const _pALabel = aMotivNone
    ? (ac.includes('gold') ? `${match.away} bereits Meister` : ac.includes('red') ? `${match.away} bereits abgestiegen` : `${match.away} gesichert`)
    : awayNeedsWin
    ? (ac.includes('gold') ? `${match.away} im Titelkampf` : ac.includes('red') ? `${match.away} im Abstiegskampf` : `${match.away} unter Druck`)
    : '';
  const _rlSfx = _rl < 99 ? `, noch ${_rl} Spieltag${_rl === 1 ? '' : 'e'}` : '';
  // Generic pressure note for goals/specialist reason texts
  // Confirmed teams: warn that opponent gets tactical free-ride vs. low-intensity lineup
  const _motivWarnH = hMotivNone
    ? `<br><strong>⬜ ${_pHLabel} — mögliche Rotation, reduzierte Intensität. Vorteil für Gegner.</strong>`
    : hMotivLow
    ? hc.includes('red')
      ? `<br><em>⚠️ ${match.home} Abstieg quasi sicher — Motivation könnte nachlassen, Gegner profitiert.</em>`
      : `<br><em>⚠️ ${match.home} nahezu gesichert — leicht reduzierte Motivation erwartet.</em>`
    : '';
  const _motivWarnA = aMotivNone
    ? `<br><strong>⬜ ${_pALabel} — mögliche Rotation, reduzierte Intensität. Vorteil für Gegner.</strong>`
    : aMotivLow
    ? ac.includes('red')
      ? `<br><em>⚠️ ${match.away} Abstieg quasi sicher — Motivation könnte nachlassen, Gegner profitiert.</em>`
      : `<br><em>⚠️ ${match.away} nahezu gesichert — leicht reduzierte Motivation erwartet.</em>`
    : '';
  const _pressNote = bothNeedWin
    ? `<br><strong>⚡ Beide Teams müssen gewinnen${_rlSfx} — maximaler Angriffsdruck, taktische Sicherung Nebensache.</strong>`
    : homeNeedsWin
    ? `<br><strong>⚡ ${_pHLabel}${_rlSfx} — Heimteam geht volles Risiko, öffnet Räume für Konter.</strong>`
    : awayNeedsWin
    ? `<br><strong>⚡ ${_pALabel}${_rlSfx} — Auswärtsteam agiert mit Vollgas-Mentalität.</strong>`
    : (hMotivNone || aMotivNone)
    ? `${_motivWarnH}${_motivWarnA}`
    : '';

  // ── Derived ───────────────────────────────────────────
  // Expected goals: prefer real xG model (home xG + away xGA, away xG + home xGA)
  const _expGoalsModel = xGBased
    ? (_hXG + _aXGA + _aXG + _hXGA) / 2
    : (hGoals + aConc + aGoals + hConc) / 2;
  // API Prediction blend: when xGBased=false and API goals available, blend 70/30.
  // Only blend for non-xG path — when Understat xG is available it's already strong.
  let expGoals = (!xGBased && _apiExpG !== null)
    ? Math.round((_expGoalsModel * 0.70 + _apiExpG * 0.30) * 10) / 10
    : _expGoalsModel;
  // Label shown in pick reasons — distinguishes data source for expected goals estimate
  // Priority: shots-based xG (teams/statistics) > API expGoals blend > goals proxy
  const _shotsBased = (_hXGSource === 'shots' || _aXGSource === 'shots');
  const egPfx = xGBased && _shotsBased
    ? `🎯 ${expGoals.toFixed(1)} xG (Schüsse)`    // shots-based xG from teams/statistics
    : xGBased
      ? `📐 ${expGoals.toFixed(1)} xG (Understat)` // real Understat xG (legacy)
      : (_apiExpG !== null)
        ? `🤖 ${expGoals.toFixed(1)} EG (Modell + API)`
        : `Ø ${expGoals.toFixed(1)} EG`;
  // Venue form: blend real home/away win rate (55%) with overall formScore (45%) when available
  // Fallback: proxy formula (home +15%, away -13%)
  const hFS_home = _hHWR != null
    ? Math.min(0.93, _hHWR * 0.55 + hFS * 0.45)
    : Math.min(0.93, hFS * 1.15 + 0.03);
  const aFS_away = _aAWR != null
    ? Math.max(0.07, _aAWR * 0.55 + aFS * 0.45)
    : Math.max(0.07, aFS * 0.87 - 0.03);
  const homeInForm = hStreak >= 2 && hFS_home > 0.62;
  const awayInForm = aStreak >= 2 && aFS_away > 0.56;
  const homePoor   = hStreak <= -3 || hFS_home < 0.25;
  const awayPoor   = aStreak <= -3 || aFS_away < 0.22;
  const drawLikely = drawRate > 0.36;

  // ── Rest-Tage / Fixture Congestion ──────────────────────────────────────────
  // getRestDays looks up previous fixture in the league calendar → days between games.
  // Away travel amplifies fatigue → slightly stronger penalty on awayAttStr.
  const _allFix    = leagueKey ? (LEAGUES[leagueKey]?.fixtures || []) : [];
  const _hRest     = getRestDays(match.home, match.date, _allFix);
  const _aRest     = getRestDays(match.away, match.date, _allFix);
  // Attack mult: tired team creates fewer chances (≤3d: -18%, ≤4d: -10%, ≤5d: -4%)
  const _hFatigAtt = _hRest == null ? 1.0 : _hRest <= 3 ? 0.82 : _hRest <= 4 ? 0.90 : _hRest <= 5 ? 0.96 : 1.0;
  const _aFatigAtt = _aRest == null ? 1.0 : _aRest <= 3 ? 0.78 : _aRest <= 4 ? 0.87 : _aRest <= 5 ? 0.94 : 1.0;
  // Defense mult: tired team concedes more (≤3d: +10%, ≤4d: +6%, ≤5d: +2%)
  const _hFatigDef = _hRest == null ? 1.0 : _hRest <= 3 ? 1.10 : _hRest <= 4 ? 1.06 : _hRest <= 5 ? 1.02 : 1.0;
  const _aFatigDef = _aRest == null ? 1.0 : _aRest <= 3 ? 1.12 : _aRest <= 4 ? 1.07 : _aRest <= 5 ? 1.02 : 1.0;

  // ── Injuries: position-specific xG modifiers ──────────────────────────────
  // New format: { goalkeeper, defense, midfield, attack, confirmed, questionable, impactScore }
  // Build injury object from missingStarters array (squad data) → correct player counts per position
  const _buildInjObj = (missing) => {
    if (!missing || !missing.length) return null;
    const o = { goalkeeper: 0, defense: 0, midfield: 0, attack: 0 };
    for (const p of missing) {
      if      (p.pos === 'G') o.goalkeeper++;
      else if (p.pos === 'D') o.defense++;
      else if (p.pos === 'M') o.midfield++;
      else if (p.pos === 'F') o.attack++;
    }
    const total = o.goalkeeper + o.defense + o.midfield + o.attack;
    if (total === 0) return null;
    // Derive impactScore: GK counts 2.5, F=1.6, D=1.2, M=1.0 (matches squad strength weights)
    o.impactScore = Math.min(10, o.goalkeeper * 2.5 + o.attack * 1.6 + o.defense * 1.2 + o.midfield * 1.0);
    o.confirmed = total;
    return o;
  };
  const _hMissing = match.homeSquad?.missingStarters ?? match.homeStake?.missingStarters;
  const _aMissing = match.awaySquad?.missingStarters ?? match.awayStake?.missingStarters;
  const _hInj      = _buildInjObj(_hMissing) || hF.injuries || null;
  const _aInj      = _buildInjObj(_aMissing) || aF.injuries || null;
  const _hImpact   = _hInj?.impactScore ?? 0;
  const _aImpact   = _aInj?.impactScore ?? 0;
  // xG attack multiplier: strikers (0.10/player) + midfielders (0.04/player) + compound bonus
  const _hInjAtt = _hInj ? Math.max(0.68,
    1 - (_hInj.attack   || 0) * 0.10
      - (_hInj.midfield || 0) * 0.04
      - ((_hInj.attack  || 0) >= 2 ? 0.05 : 0)   // compound: 2+ strikers missing
      - ((_hInj.attack  || 0) >= 3 ? 0.07 : 0)   // compound: no real striker
  ) : 1.0;
  const _aInjAtt = _aInj ? Math.max(0.68,
    1 - (_aInj.attack   || 0) * 0.10
      - (_aInj.midfield || 0) * 0.04
      - ((_aInj.attack  || 0) >= 2 ? 0.05 : 0)
      - ((_aInj.attack  || 0) >= 3 ? 0.07 : 0)
  ) : 1.0;
  // xGA defense multiplier: GK (9%) + each CB/fullback (7%)
  const _hInjDef = _hInj ? Math.min(1.30,
    1 + (_hInj.goalkeeper || 0) * 0.09
      + (_hInj.defense    || 0) * 0.07
      + ((_hInj.defense   || 0) >= 3 ? 0.06 : 0) // compound: exposed backline
  ) : 1.0;
  const _aInjDef = _aInj ? Math.min(1.30,
    1 + (_aInj.goalkeeper || 0) * 0.09
      + (_aInj.defense    || 0) * 0.07
      + ((_aInj.defense   || 0) >= 3 ? 0.06 : 0)
  ) : 1.0;
  // Net xG deltas for edge display (positive = team scored more/less)
  const _hInjxGDelta = -(1 - _hInjAtt);   // e.g. -0.22 means team scores 22% less
  const _aInjxGDelta = -(1 - _aInjAtt);

  // ── xG-based profiles (xG preferred, goals as fallback) ─────────────────
  // Fatigue + injury multipliers applied at source → flow through ALL pick computations.
  let homeAttStr = (xGBased ? _hXG  : hGoals) * _hFatigAtt * _hInjAtt;
  let homeDefStr = (xGBased ? _hXGA : hConc)  * _hFatigDef * _hInjDef;
  let awayAttStr = (xGBased ? _aXG  : aGoals) * _aFatigAtt * _aInjAtt;
  let awayDefStr = (xGBased ? _aXGA : aConc)  * _aFatigDef * _aInjDef;

  // ── Motivation penalty (applied after fatigue + injury) ───────────────────
  // Confirmed teams (motivationLevel='none') rotate key players and lower intensity:
  //   Attack:  -18% xG (rotated strikers, tactical shape abandoned)
  //   Defense: +12% xGA (second-string defenders, less pressing)
  // Near-confirmed (motivationLevel='low'):
  //   Attack:  -8% xG
  //   Defense: +6% xGA
  if (hMotivNone) { homeAttStr *= 0.82; homeDefStr *= 1.12; }
  else if (hMotivLow) { homeAttStr *= 0.92; homeDefStr *= 1.06; }
  if (aMotivNone) { awayAttStr *= 0.82; awayDefStr *= 1.12; }
  else if (aMotivLow) { awayAttStr *= 0.92; awayDefStr *= 1.06; }

  // ── Formation modifier (applied after fatigue + injury + motivation) ───────────
  // Offensive formation (3+ forwards): +7% attack. Defensive (1 forward): −7% attack.
  // Max ±7% so it enhances but never dominates the fatigue/injury signals.
  if (_hFormMod !== 0) { homeAttStr *= (1 + _hFormMod); homeDefStr *= (1 - _hFormMod * 0.5); }
  if (_aFormMod !== 0) { awayAttStr *= (1 + _aFormMod); awayDefStr *= (1 - _aFormMod * 0.5); }

  // ── expGoals sanity floor ────────────────────────────────────────────────
  // expGoals is computed before fatigue/injury/motivation multipliers are applied
  // to homeAttStr/awayAttStr. For xG-based paths with sparse Understat data this
  // can yield physically impossible values (e.g. expGoals=0.1 while homeAttStr=2.3).
  // Floor: expGoals must be at least 35% of the combined adjusted attack strength.
  // 35% is conservative — calibrated so it doesn't override real low-scoring games
  // but catches clearly corrupted xG inputs.
  {
    const _expGoalsAttFloor = Math.round((homeAttStr + awayAttStr) * 0.35 * 10) / 10;
    if (expGoals < _expGoalsAttFloor) expGoals = _expGoalsAttFloor;
  }
  // Write finalised expGoals back to match so the inline validator can read it.
  // The validator passes _fxCopy = Object.assign({}, fx) to getBettingPicks(), so
  // writing to `match` here sets _fxCopy._expGoals which the validator then reads.
  match._expGoals = expGoals;

  // BTTS signals (refined by xG)
  const bttsXGStrong = homeAttStr > 1.30 && awayAttStr > 1.10 && homeDefStr > 0.90 && awayDefStr > 0.90;
  const bttsLikely   = homeAttStr > 1.15 && awayAttStr > 0.95 && homeDefStr > 0.85 && awayDefStr > 0.85;
  const bttsBad      = homeAttStr < 0.90 || awayAttStr < 0.80;
  const bttsNoSignal = homeAttStr < 1.00 || awayAttStr < 0.90;
  // Corners estimate — prefer real stats-cache data over xG formula
  // cornersEst formula: ~3.4 corners/home-xG-unit + ~3.0/away-xG-unit (calibrated on Big5)
  // Defensive leakiness bonus: porous defences invite more pressure → more corners
  const _defBonus = Math.min(1.2, Math.max(0, (homeDefStr + awayDefStr - 2.0) * 0.5));
  const _cornersFormula = homeAttStr * 3.4 + awayAttStr * 3.0 + _defBonus;
  // Real corner data from fixtures/statistics batch fetch: home avg at home + away avg away
  // Sanity-cap individual team averages before combining (API data can be noisy for smaller leagues)
  // Quality gate: < 2.0 means the average comes from 0–1 games only → unreliable, fall back to formula.
  const _hCH = (_hCornersHome !== null && _hCornersHome >= 2.0) ? Math.min(_hCornersHome, 9.5) : null;
  const _aCA = (_aCornersAway !== null && _aCornersAway >= 2.0) ? Math.min(_aCornersAway, 8.5) : null;
  const _cornersReal = (_hCH !== null && _aCA !== null)
    ? Math.round((_hCH + _aCA) * 10) / 10
    : null;
  // Hard cap on total estimate: 13 corners max — keeps Over 11.5 FV above 1.25 even for high-pressing games.
  // Anything beyond 13 expected corners is likely a data artefact (API noise / small sample).
  const cornersEst     = _cornersReal !== null ? Math.min(_cornersReal, 13.0) : Math.min(_cornersFormula, 13.0);
  const cornersDataReal = _cornersReal !== null;
  const cornersOver8   = cornersEst >= 8.0;
  const cornersOver9   = cornersEst >= 9.5;
  const cornersOver11  = cornersEst >= 11.0;
  // ── Poisson-estimated corners odds (injected into o when real quotes absent) ──
  if (!o.co95 || !o.co85) {
    const _cEst = estimateCornersOdds(cornersEst);
    if (!o.co85)  { o.co85  = _cEst.co85;  o.cu85  = _cEst.cu85;  }
    if (!o.co95)  { o.co95  = _cEst.co95;  o.cu95  = _cEst.cu95;  }
    if (!o.co105) { o.co105 = _cEst.co105; o.cu105 = _cEst.cu105; }
    if (!o.co115) { o.co115 = _cEst.co115; o.cu115 = _cEst.cu115; }
    if (_cEst.oddsIsEst) o._cornersOddsEst = true;  // flag for render
  }
  // Cards — helper flags (anyGold already declared above; anyOrange added here)
  const anyOrange = hc.includes('orange') || ac.includes('orange');
  const cardsVeryHigh = bothRed && hStreak <= -2 && aStreak <= -2;
  // cardsHigh: relegation vs any high-stakes team (title, UCL, Europa, or both red)
  const cardsHigh     = bothRed || (anyRed && (anyBlue || anyGold || anyOrange));
  const cardsMed      = (anyRed && (hStreak <= -2 || aStreak <= -2)) || (!anyRed && hStreak <= -2 && aStreak <= -2);
  // Cards motivation guards — confirmed-out teams don't play under "maximalem Druck"
  // motivNone = confirmed relegated/champion → reckless play possible but NOT desperation pressure
  const _hRedConf   = hc.includes('red') && hMotivNone;  // home is confirmed relegated
  const _aRedConf   = ac.includes('red') && aMotivNone;  // away is confirmed relegated
  const _anyRedConf = _hRedConf || _aRedConf;
  const _bothRedConf = _hRedConf && _aRedConf;
  // Effective pressure boost for cards: confirmed-relegated teams add no desperation energy
  const _cardPressBoost = _anyRedConf ? _pressureBoost * 0.20 : _pressureBoost;

  // ── Referee card influence (Pro plan) ───────────────────────────────────────
  // avgCards from real referee history shifts base confidence for card picks.
  // High-card referee: meaningful boost. Lenient ref: suppresses card picks.
  const _refStats    = match.refereeStats || null;
  const _refAvg      = _refStats?.avgCards ?? null;
  const _refCardMod  = _refAvg == null  ? 0        // no data — neutral
                     : _refAvg >= 5.5   ?  0.18    // very card-heavy ref
                     : _refAvg >= 4.5   ?  0.10    // above average
                     : _refAvg >= 3.5   ?  0.04    // slightly above
                     : _refAvg < 2.0    ? -0.20    // very lenient — suppress strongly
                     : _refAvg < 2.8    ? -0.12    // lenient
                     : _refAvg < 3.2    ? -0.05    // slightly below
                     : 0;
  // Human-readable note for pick reasons
  const _refCardNote = _refAvg == null ? ''
    : _refAvg >= 4.5 ? `<br>👨‍⚖️ Schiedsrichter ${_refStats.name}: Ø ${_refAvg} Karten/Spiel — hohe Kartentendenz bestätigt.`
    : _refAvg < 3.0  ? `<br>👨‍⚖️ Schiedsrichter ${_refStats.name}: Ø ${_refAvg} Karten/Spiel — ruhiger Pfeifer, Markt kritisch prüfen.`
    : `<br>👨‍⚖️ Schiedsrichter ${_refStats.name}: Ø ${_refAvg} Karten/Spiel.`;
  // ── Poisson-estimated cards odds (injected into o when real quotes absent) ──
  // Expected total cards: blended from referee avg (primary) + team card profiles (secondary).
  // Team profiles (homeCardProfile.avgCards + awayCardProfile.avgCards) give per-team
  // seasonal discipline data — Atlético-style vs. Man City-style tendencies captured.
  // Fallback chain: refAvg only → blend ref+team → team only → league base + pressure.
  if (!o.cards_o35) {
    const _leagueCardBase = ({ENG:3.8, GER:3.6, ITA:3.5, ESP:3.4, FRA:3.6, AUT:3.7,
                              NED:3.5, POR:3.8, TUR:4.2, SCO:4.0, POL:3.6, SUI:3.4})[leagueKey] || 3.5;
    // Team card sum: sum of each team's seasonal avg cards (home + away cards received)
    const _hCP = match.homeCardProfile?.avgCards ?? null;
    const _aCP = match.awayCardProfile?.avgCards  ?? null;
    const _teamCardSum = (_hCP !== null && _aCP !== null) ? (_hCP + _aCP) : null;
    // Blending: ref avg captures referee's control style; team sum captures team discipline.
    // When both available: 60% ref weight (better predictor) + 40% team profile.
    const _expCards = _refAvg !== null && _teamCardSum !== null
      ? _refAvg * 0.60 + _teamCardSum * 0.40          // blend: ref is primary, team secondary
      : _refAvg !== null
        ? _refAvg                                      // ref only — single best predictor
        : _teamCardSum !== null
          ? _teamCardSum + (bothNeedWin ? 0.3 : _anyNeedsWin ? 0.15 : 0) // team + pressure
          : _leagueCardBase + (bothRed ? 0.8 : anyRed ? 0.4 : 0)         // pure fallback
               + (bothNeedWin ? 0.5 : _anyNeedsWin ? 0.25 : 0);
    const _cOdds = estimateCardsOdds(_expCards);
    if (!o.cards_o35) { o.cards_o35 = _cOdds.cards_o35; }
    if (!o.cards_o45) { o.cards_o45 = _cOdds.cards_o45; }
    if (_cOdds.oddsIsEst) o._cardsOddsEst = true;  // flag for render
  }
  // ── Poisson-estimated BTTS odds (injected when real quotes absent) ─────────
  // P(BTTS Yes) = P(home scores ≥ 1) × P(away scores ≥ 1) via independent Poisson.
  // lambdaH/A: adjusted attack strength already incorporates fatigue + injury + motivation.
  if (!o.bttsY) {
    const _bEst = estimateBttsOdds(homeAttStr, awayAttStr);
    if (_bEst.bttsY) {
      o.bttsY = _bEst.bttsY;
      o.bttsN = _bEst.bttsN;
      o._bttsOddsEst = true;
    }
  }
  // ── Poisson-estimated Team Goals Over 1.5 odds (injected when real quotes absent) ──
  // expH/A: blended expected goals (homeAttStr + awayDefStr / 2, same formula as PICK 2 block).
  if (!o.hto15 || !o.ato15) {
    const _expHteam = (homeAttStr + awayDefStr) / 2;
    const _expAteam = (awayAttStr + homeDefStr) / 2;
    if (!o.hto15) {
      const _htEst = estimateTeamGoalOdds(_expHteam);
      if (_htEst.over) { o.hto15 = _htEst.over; o.htu15 = _htEst.under; o._hto15Est = true; }
    }
    if (!o.ato15) {
      const _atEst = estimateTeamGoalOdds(_expAteam);
      if (_atEst.over) { o.ato15 = _atEst.over; o.atu15 = _atEst.under; o._ato15Est = true; }
    }
  }
  // Handicap: dominant team vs clearly inferior opposition
  const homeHandicap  = hFS_home > 0.66 && (_hHWR ?? homeWinRate) > 0.54 && (awayPoor || aFS_away < 0.35);
  const awayHandicap  = aFS_away > 0.60 && (_aAWR ?? awayWinRate) > 0.46 && (homePoor || hFS_home < 0.35);
  // Tempo
  const firstHalfOpen  = expGoals > 3.0 || homeAttStr > 1.6 || awayAttStr > 1.5;
  const firstHalfTight = expGoals < 2.3 && drawLikely;

  // ── Pick pool with strict category deduplication ──────────────────────────
  // 3 picks selected: 1 result, 1 goals/tempo, 1 specialist
  const picks = [];
  const _used  = new Set();
  // _push(p, sc) — attach sc to pick so infographic & results tracking can use it
  // When the underlying odds came from API prediction (not real bookmakers), automatically
  // mark all picks that have real odds values as estimates — mirrors corners/cards Poisson logic.
  const _odds1x2IsEst = !!(odds?._isEstimated || o?._isEstimated);
  const _push = (p, sc) => {
    if (!p || _used.has(p.market)) return false;
    _used.add(p.market);
    if (sc !== undefined) p.sc = sc;
    // Auto-flag estimated odds on picks from API prediction fallback (not Poisson — those set it themselves)
    if (_odds1x2IsEst && p.odds != null && !p.oddsIsEst) p.oddsIsEst = true;
    // Invariant: a pick with no real odds and no estimate flag must be 'low' confidence.
    // Without this a pick displayed as [medium] or [high] would appear with no bettable quote.
    if (p.odds == null && !p.oddsIsEst && p.conf !== 'low') p.conf = 'low';
    picks.push(p);
    return true;
  };
  let _topResultMkt = ''; // hoisted: set by PICK 1, read by PICK 2 for consistency guard

  // ╔══════════════════════════════════════════════════════════════════════╗
  // ║  PICK 1 — RESULT MARKET                                            ║
  // ║  Score all result candidates; match-type context applied as boost  ║
  // ╚══════════════════════════════════════════════════════════════════════╝
  {
    const rC = [];
    // ── Heimsieg ──────────────────────────────────────────────────────────
    {
      // BACKTEST FINDING: base of 0.40 made model pick home win for almost every match.
      // Fix: start at 0.0 — positive signals must actively push score above thresholds.
      let sc = 0.0 + (hFS_home - 0.5)*1.20 + Math.max(0,hStreak)*0.09 + homeWinRate*0.35;
      if (hc.includes('gold')) sc += 0.16; if (hc.includes('blue')) sc += 0.10;
      // Red away team boosts home win — BUT only if that away team is NOT under must-win pressure.
      // When awayNeedsWin, desperation overrides demoralisation: they fight hard away, not collapse.
      if (ac.includes('red') && !awayNeedsWin) sc += 0.14;
      // 🔑 RELEGATED AWAY + FIGHTING HOME: motivation asymmetry boost.
      // Full boost when home explicitly needs a win; partial when merely competitive (not relegated).
      // Fires even without a stake label — any non-relegated home team benefits from facing
      // a confirmed-relegated away side with no rotation pressure.
      if (aMotivNone && ac.includes('red') && !hMotivNone) {
        sc += homeNeedsWin ? 0.30 : 0.18;
      }
      if (homeInForm && !awayInForm) sc += 0.28;
      if (homePoor) sc -= 0.48;            if (awayInForm && !homeInForm) sc -= 0.20;
      if (eloDiff !== null) sc += Math.min(0.22, Math.max(-0.22, eloDiff / 700));
      if (homeNeedsWin && !awayNeedsWin) sc += _pressureBoost;
      if (bothNeedWin) sc += _pressureBoost * 0.50;
      // xG Fairness adjustment: lucky home team → regression risk → mild penalty
      // unlucky away team → regression risk → further softens home win case
      sc += _hFairMod;   // home overperforming xG at home → reduce confidence
      sc -= _aFairMod;   // away underperforming → they're due, hurts home win case
      // 🔑 H2H RECENCY: last 5 direct meetings, recency-weighted. Positive = home has been winning recently.
      // Max ±0.07 — small but meaningful for borderline picks.
      sc += _h2hRecencyMod;
      // 🔑 API POISSON — fair value supplement (only when Pinnacle odds absent; max ±0.10)
      // Poisson from /predictions is an independent model — use as mild confirmatory signal.
      if (_apiPoiH !== null && !_bkrPH) {
        const _ph = _apiPoiH / 100;
        if (_ph >= 0.60) sc += 0.10;
        else if (_ph >= 0.50) sc += 0.05;
        else if (_ph <= 0.25) sc -= 0.08;
        else if (_ph <= 0.35) sc -= 0.04;
      }
      // 🔑 COMPARISON SIGNALS — API-Football model: form/att/def/goals differentials
      // Each capped at ±0.10 total to prevent single signal from dominating.
      if (_compFormDiff !== null)  sc += Math.min(0.07, Math.max(-0.07, _compFormDiff / 100 * 0.70));
      if (_compAttDiff !== null)   sc += Math.min(0.06, Math.max(-0.06, _compAttDiff  / 100 * 0.60));
      if (_compDefDiff !== null)   sc += Math.min(0.05, Math.max(-0.05, _compDefDiff  / 100 * 0.50));
      if (_compGoalsDiff !== null) sc += Math.min(0.05, Math.max(-0.05, _compGoalsDiff/ 100 * 0.50));
      // 🔑 STREAK MOMENTUM — biggest win/loss streak this season + current streak
      // Biggest win streak ≥5 = dominant team this season → small boost
      if (_hBigWinStr  !== null && _hBigWinStr  >= 5) sc += Math.min(0.08, (_hBigWinStr  - 4) * 0.02);
      if (_aBigLoseStr !== null && _aBigLoseStr >= 4) sc += Math.min(0.06, (_aBigLoseStr - 3) * 0.02);
      // Current streak (from refresh_stats.py): positive = recent wins, negative = recent losses
      if (_hCurStreak !== null && _hCurStreak >= 3)  sc += Math.min(0.08, (_hCurStreak - 2) * 0.025);
      if (_hCurStreak !== null && _hCurStreak <= -3) sc -= Math.min(0.08, (-_hCurStreak - 2) * 0.025);
      if (_aCurStreak !== null && _aCurStreak >= 3)  sc -= Math.min(0.08, (_aCurStreak - 2) * 0.025);
      if (_aCurStreak !== null && _aCurStreak <= -3) sc += Math.min(0.06, (-_aCurStreak - 2) * 0.020);
      // 🔑 MUSTWIN_LOW_GPG: home team must win but structurally can't score
      // AVS (0.20 gpg), Konyaspor etc. — urgency ≠ firepower
      if (homeNeedsWin && homeAttStr < 0.50) sc = Math.max(0, sc - 0.40); // very low scorer + must win
      else if (homeNeedsWin && homeAttStr < 0.70) sc = Math.max(0, sc - 0.20); // low scorer + must win
      // 🔑 RELEGATED HOME: confirmed-relegated home team has no motivation — heavy penalty.
      // Historical home win rate is meaningless when the squad will rotate and intensity drops.
      // "Abstieg bestätigt" cards should never recommend betting on that team to win at home.
      if (hMotivNone && hc.includes('red')) sc = Math.max(0, sc - 0.55);
      // ★★★ threshold 1.50 (multi-signal). ★★☆ lowered 0.72→0.50 so normal home favorites
      // without pressure still show (backtest showed too many good picks hidden at 0.72).
      const conf = sc > 1.50 ? 'high' : sc > 0.50 ? 'medium' : 'low';
      const _xgLbl = xGBased ? 'xG' : 'Tore';
      // Build reason: lead with the primary signal, support with attack vs defence matchup, add H2H context
      const _hH2hSnippet = h2hN >= 3
        ? ` · H2H: ${h2h.homeWins||0}H/${h2h.draws||0}U/${h2h.awayWins||0}A (${h2hN} Duelle)`
        : '';
      // Venue-specific season stat note — shown only when meaningful
      const _hVenueNote = (_hHWR !== null || _hCSHome !== null)
        ? `<br>📊 Heimstatistik (Saison): ${_hHWR !== null ? `${Math.round(_hHWR*100)}% Siege` : ''}${_hHWR !== null && _hCSHome !== null ? ' · ' : ''}${_hCSHome !== null ? `${Math.round(_hCSHome*100)}% Clean Sheets` : ''}.`
        : '';
      // Streak note
      const _hStreakNote = (_hCurStreak !== null && Math.abs(_hCurStreak) >= 3)
        ? `<br>🔥 Aktueller Lauf: ${match.home} ${_hCurStreak > 0 ? `${_hCurStreak}× ungeschlagen` : `${-_hCurStreak}× ohne Sieg`}.`
        : '';
      // Comparison note
      const _hCompNote = (_compFormDiff !== null && _compFormDiff >= 20)
        ? `<br>📡 API-Signale bestätigen den Heimvorteil: ${match.home} zeigt aktuell klar die bessere Form.`
        : (_compFormDiff !== null && _compFormDiff <= -20)
          ? `<br>⚠️ API-Signale: ${match.away} hat aktuell die bessere Formkurve — Vorsicht.`
          : '';
      let reason = homeInForm
        ? `${match.home} ist in Topform (zuletzt ${hStreak} Siege) und gewinnt ${Math.round(hFS_home*100)}% seiner Heimspiele. Das Angriffsspiel (Ø ${homeAttStr.toFixed(1)} Tore/Spiel) trifft auf eine anfällige ${match.away}-Abwehr (kassiert Ø ${awayDefStr.toFixed(1)} Tore/Spiel).${_hH2hSnippet}`
        : hc.includes('gold') && !hMotivNone
          ? `${match.home} kämpft um den Titel — ein Heimsieg ist Pflicht. Gewinnt ${Math.round(hFS_home*100)}% der Heimspiele und erzielt Ø ${homeAttStr.toFixed(1)} Tore/Spiel. Der Druck erhöht die Intensität.${_hH2hSnippet}`
          : hc.includes('gold') && hMotivNone
            ? `${match.home} ist bereits Meister — Pflichtspiel ohne Saisondruck. Gewinnt ${Math.round(hFS_home*100)}% der Heimspiele, Rotation möglich. Qualität bleibt strukturell hoch.${_hH2hSnippet}`
          : hc.includes('red') && homeNeedsWin
            ? `${match.home} kämpft gegen den Abstieg und braucht jeden Punkt zu Hause — das steigert die Intensität und Entschlossenheit. ${match.away} kommt mit nur ${Math.round(aFS_away*100)}% Auswärtssieg-Rate.${_hH2hSnippet}`
            : ac.includes('red') && !awayNeedsWin
              ? `${match.away} ist auswärts unter Abstiegsdruck — das wirkt sich oft negativ auf die Leistung aus. ${match.home} gewinnt ${Math.round(hFS_home*100)}% seiner Heimspiele und kann diesen Vorteil nutzen.${_hH2hSnippet}`
              : `${match.home} gewinnt ${Math.round(hFS_home*100)}% seiner Heimspiele und erzielt dabei Ø ${homeAttStr.toFixed(1)} Tore/Spiel. Der Gegner kassiert Ø ${awayDefStr.toFixed(1)} Tore/Spiel.${_hH2hSnippet}`;
      if (eloAwayFav && eloLabel) reason += `<br>⚠️ Elo-Warnung: ${eloLabel}`;
      else if (eloHomeFav && eloLabel) reason += `<br>📊 Elo bestätigt: ${eloLabel}`;
      reason += _hVenueNote;
      reason += _hStreakNote;
      reason += _hCompNote;
      if (_apiPoiH !== null) {
        if (_apiPoiH >= 50) reason += `<br>🤖 Statistisches Modell sieht ${match.home} mit ${_apiPoiH}% als Favorit — bestätigt die Analyse.`;
        else if (_apiPoiH <= 32) reason += `<br>⚠️ Statistisches Modell: ${match.home} nur bei ${_apiPoiH}% Siegchance — Modell ist skeptischer.`;
      }
      rC.push({sc, p:{icon:'🏠', market:'Heimsieg', odds:o.hw, conf, reason}});
      // AH-Kandidat: wenn Heimsieg-Quote zu günstig (< 1.35), beste AH-Line via Ziel-Quote ~1.62
      if (o.hw != null && o.hw < 1.35) {
        // ah_home_lines now contains ALL bookmaker spread lines (from spreads market, Pass 1)
        // + alternate_spreads lines (Pass 6, if available) — _pickBestLine picks closest to 1.62
        const _ahBest  = _pickBestLine(o.ah_home_lines, 1.62);
        const _ahOdds  = _ahBest ? _ahBest.price : (o.ah_h && o.ah_h >= 1.35 && o.ah_h <= 2.05 ? o.ah_h : null);
        const _ahPoint = _ahBest ? _ahBest.pt    : o.ah_h_point;
        if (_ahOdds != null && _ahOdds >= 1.35 && _ahOdds <= 2.05) {
          const _ahPt = _ahPoint != null ? (_ahPoint >= 0 ? `+${_ahPoint}` : `${_ahPoint}`) : '';
          const _ahMkt = `AH Heim${_ahPt ? ' ' + _ahPt : ''}`;
          const _ahConf = sc > 1.50 ? 'high' : sc > 0.50 ? 'medium' : 'low';
          const _ahReason = `${match.home} ist klarer Favorit (1X2-Quote ${o.hw.toFixed(2)} — kein Wert). Asian Handicap${_ahPt ? ' ' + _ahPt : ''} @ ${_ahOdds.toFixed(2)} bietet deutlich besseres Value. ` + reason;
          // FV gate: replicate the margin-factor formula used in computeFairValue (AH section).
          // Suppress if implied prob exceeds model fair prob by >14pp (wider than goals 12pp — AH
          // calc is less precise and the line choice adds uncertainty).
          const _ahPtN   = _ahPoint != null ? Math.abs(_ahPoint) : 0;
          const _ahMfH   = _ahPtN >= 3.0 ? 0.27 : _ahPtN >= 2.75 ? 0.32 : _ahPtN >= 2.5 ? 0.37
                         : _ahPtN >= 2.25 ? 0.44 : _ahPtN >= 2.0 ? 0.51 : _ahPtN >= 1.75 ? 0.58
                         : _ahPtN >= 1.5 ? 0.64 : _ahPtN >= 1.25 ? 0.72 : _ahPtN >= 1.0 ? 0.80
                         : _ahPtN >= 0.75 ? 0.87 : _ahPtN >= 0.5 ? 0.93 : 0.97;
          const _ahBoostH  = (_bkrPH ?? 0) > 0.85 ? 1.35 : (_bkrPH ?? 0) > 0.80 ? 1.20 : 1.0;
          const _ahFairPH  = _bkrPH != null ? Math.min(0.90, _bkrPH * Math.min(0.97, _ahMfH * _ahBoostH)) : null;
          const _ahNegEdgeH = !o._isEstimated && _hasNegEdge(_ahFairPH, _ahOdds, false, GATE.AH_REAL, null);
          if (!_ahNegEdgeH) {
            rC.push({sc, p:{icon:'🏠', market:_ahMkt, odds:_ahOdds, conf:_ahConf, reason:_ahReason}});
          }
        }
      }
    }
    // ── Auswärtssieg ──────────────────────────────────────────────────────
    {
      // BACKTEST FINDING: ★★★ Auswärtssieg had +2.7% ROI — our best signal. Keep selective.
      // Base 0.26 → 0.0 (same fix as Heimsieg — require active positive signals)
      let sc = 0.0 + (aFS_away - 0.5)*1.20 + Math.max(0,aStreak)*0.09 + awayWinRate*0.35;
      if (ac.includes('gold')) sc += 0.16; if (ac.includes('blue')) sc += 0.10;
      // Red home team boosts away win — BUT only if that home team is NOT under must-win pressure.
      // When homeNeedsWin, desperation at home overrides demoralisation: they fight, not collapse.
      if (hc.includes('red') && !homeNeedsWin) sc += 0.14;
      // 🔑 RELEGATED HOME + COMPETITIVE AWAY: motivation asymmetry boost.
      // Full boost when away explicitly needs a win; partial when merely competitive (not relegated).
      // Fires even without a stake label — any non-relegated away team benefits from playing
      // a confirmed-relegated home side that has nothing to play for.
      if (hMotivNone && hc.includes('red') && !aMotivNone) {
        sc += awayNeedsWin ? 0.30 : 0.18;
      }
      if (awayInForm && !homeInForm) sc += 0.28;
      if (awayPoor) sc -= 0.48;            if (homeInForm && !awayInForm) sc -= 0.20;
      if (eloDiff !== null) sc += Math.min(0.22, Math.max(-0.22, -eloDiff / 700));
      if (awayNeedsWin && !homeNeedsWin) sc += _pressureBoost;
      if (bothNeedWin) sc += _pressureBoost * 0.50;
      // xG Fairness adjustment: lucky away team → regression risk → mild penalty
      // unlucky home team → they're due → hurts away win case
      sc += _aFairMod;   // away overperforming → reduce confidence
      sc -= _hFairMod;   // home underperforming → they'll improve, hurts away win
      // 🔑 H2H RECENCY: inverted — negative _h2hRecencyMod means away has been winning recently
      sc -= _h2hRecencyMod;
      // 🔑 API POISSON — fair value supplement when Pinnacle odds absent
      if (_apiPoiA !== null && !_bkrPA) {
        const _pa = _apiPoiA / 100;
        if (_pa >= 0.55) sc += 0.10;
        else if (_pa >= 0.45) sc += 0.05;
        else if (_pa <= 0.20) sc -= 0.08;
        else if (_pa <= 0.30) sc -= 0.04;
      }
      // 🔑 COMPARISON SIGNALS (inverted for away team: negative diff = away has edge)
      if (_compFormDiff  !== null) sc += Math.min(0.07, Math.max(-0.07, -_compFormDiff  / 100 * 0.70));
      if (_compAttDiff   !== null) sc += Math.min(0.06, Math.max(-0.06, -_compAttDiff   / 100 * 0.60));
      if (_compDefDiff   !== null) sc += Math.min(0.05, Math.max(-0.05, -_compDefDiff   / 100 * 0.50));
      if (_compGoalsDiff !== null) sc += Math.min(0.05, Math.max(-0.05, -_compGoalsDiff / 100 * 0.50));
      // 🔑 STREAK MOMENTUM — away team version
      if (_aBigWinStr  !== null && _aBigWinStr  >= 5) sc += Math.min(0.08, (_aBigWinStr  - 4) * 0.02);
      if (_hBigLoseStr !== null && _hBigLoseStr >= 4) sc += Math.min(0.06, (_hBigLoseStr - 3) * 0.02);
      if (_aCurStreak !== null && _aCurStreak >= 3)  sc += Math.min(0.08, (_aCurStreak - 2) * 0.025);
      if (_aCurStreak !== null && _aCurStreak <= -3) sc -= Math.min(0.08, (-_aCurStreak - 2) * 0.025);
      if (_hCurStreak !== null && _hCurStreak >= 3)  sc -= Math.min(0.08, (_hCurStreak - 2) * 0.025);
      if (_hCurStreak !== null && _hCurStreak <= -3) sc += Math.min(0.06, (-_hCurStreak - 2) * 0.020);
      // 🔑 MUSTWIN_LOW_GPG: away team must win but structurally can't score
      if (awayNeedsWin && awayAttStr < 0.50) sc = Math.max(0, sc - 0.40);
      else if (awayNeedsWin && awayAttStr < 0.70) sc = Math.max(0, sc - 0.20);
      // 🔑 RELEGATED AWAY: confirmed-relegated away team has no motivation — heavy penalty.
      // Auswärts ohne Druck + Abstieg bestätigt = maximale Rotation und Gleichgültigkeit.
      if (aMotivNone && ac.includes('red')) sc = Math.max(0, sc - 0.55);
      // Threshold: ★★★ at 1.30 (slightly lower than Heimsieg since away wins are rarer/more selective)
      const conf = sc > 1.30 ? 'high' : sc > 0.45 ? 'medium' : 'low';
      const _xgLblA = xGBased ? 'xG' : 'Tore';
      const _aH2hSnippet = h2hN >= 3
        ? ` · H2H: ${h2h.homeWins||0}H/${h2h.draws||0}U/${h2h.awayWins||0}A (${h2hN} Duelle)`
        : '';
      const _aVenueNote = (_aAWR !== null || _aCSAway !== null)
        ? `<br>📊 Auswärtsstatistik (Saison): ${_aAWR !== null ? `${Math.round(_aAWR*100)}% Siege` : ''}${_aAWR !== null && _aCSAway !== null ? ' · ' : ''}${_aCSAway !== null ? `${Math.round(_aCSAway*100)}% Clean Sheets` : ''}.`
        : '';
      // Formation + streak notes (away perspective)
      const _aStreakNote = (_aCurStreak !== null && Math.abs(_aCurStreak) >= 3)
        ? `<br>🔥 Aktueller Lauf: ${match.away} ${_aCurStreak > 0 ? `${_aCurStreak}× ungeschlagen` : `${-_aCurStreak}× ohne Sieg`}.`
        : '';
      const _aCompNote = (_compFormDiff !== null && _compFormDiff <= -20)
        ? `<br>📡 API-Signale bestätigen: ${match.away} zeigt aktuell klar die bessere Form.`
        : (_compFormDiff !== null && _compFormDiff >= 20)
          ? `<br>⚠️ API-Signale: ${match.home} liegt in der aktuellen Form vorn — Vorsicht.`
          : '';
      let reason = awayInForm
        ? `${match.away} ist in Topform (zuletzt ${aStreak} Siege) und gewinnt ${Math.round(aFS_away*100)}% seiner Auswärtsspiele. Das Angriffsspiel (Ø ${awayAttStr.toFixed(1)} Tore/Spiel) trifft auf eine anfällige ${match.home}-Abwehr (kassiert Ø ${homeDefStr.toFixed(1)} Tore/Spiel).${_aH2hSnippet}`
        : ac.includes('gold') && !aMotivNone
          ? `${match.away} kämpft im Titelkampf um Punkte auswärts. Gewinnt ${Math.round(aFS_away*100)}% der Auswärtsspiele und erzielt Ø ${awayAttStr.toFixed(1)} Tore/Spiel. Titeldruck treibt die Leistung.${_aH2hSnippet}`
          : ac.includes('gold') && aMotivNone
            ? `${match.away} ist bereits Meister — Auswärtsspiel ohne Saisondruck. Gewinnt ${Math.round(aFS_away*100)}% der Auswärtsspiele, Rotation möglich. Qualität bleibt strukturell hoch.${_aH2hSnippet}`
          : hc.includes('red') && !homeNeedsWin
            ? `${match.home} steckt im Abstiegskampf und ist defensiv anfällig (kassiert Ø ${homeDefStr.toFixed(1)} Tore/Spiel). ${match.away} mit ${Math.round(aFS_away*100)}% Auswärtssieg-Rate kann diesen Vorteil nutzen.${_aH2hSnippet}`
            : `${match.away} gewinnt ${Math.round(aFS_away*100)}% seiner Auswärtsspiele und erzielt dabei Ø ${awayAttStr.toFixed(1)} Tore/Spiel. Der Gegner kassiert Ø ${homeDefStr.toFixed(1)} Tore/Spiel.${_aH2hSnippet}`;
      if (eloHomeFav && eloLabel) reason += `<br>⚠️ Elo-Warnung: ${eloLabel}`;
      else if (eloAwayFav && eloLabel) reason += `<br>📊 Elo bestätigt: ${eloLabel}`;
      reason += _aVenueNote;
      reason += _aStreakNote;
      reason += _aCompNote;
      if (_apiPoiA !== null) {
        if (_apiPoiA >= 50) reason += `<br>🤖 Statistisches Modell sieht ${match.away} mit ${_apiPoiA}% als Favorit — bestätigt die Analyse.`;
        else if (_apiPoiA <= 32) reason += `<br>⚠️ Statistisches Modell: ${match.away} nur bei ${_apiPoiA}% Siegchance — Modell ist skeptischer.`;
      }
      rC.push({sc, p:{icon:'✈️', market:'Auswärtssieg', odds:o.aw, conf, reason}});
      // AH-Kandidat: wenn Auswärtssieg-Quote zu günstig (< 1.35), beste AH-Line via Ziel-Quote ~1.62
      if (o.aw != null && o.aw < 1.35) {
        // ah_away_lines contains all bookmaker spread lines + alternate_spreads (Pass 6)
        const _ahBest  = _pickBestLine(o.ah_away_lines, 1.62);
        const _ahOdds  = _ahBest ? _ahBest.price : (o.ah_a && o.ah_a >= 1.35 && o.ah_a <= 2.05 ? o.ah_a : null);
        const _ahPoint = _ahBest ? _ahBest.pt    : o.ah_a_point;
        if (_ahOdds != null && _ahOdds >= 1.35 && _ahOdds <= 2.05) {
          const _ahPt = _ahPoint != null ? (_ahPoint >= 0 ? `+${_ahPoint}` : `${_ahPoint}`) : '';
          const _ahMkt = `AH Ausw.${_ahPt ? ' ' + _ahPt : ''}`;
          const _ahConf = sc > 1.30 ? 'high' : sc > 0.45 ? 'medium' : 'low';
          const _ahReason = `${match.away} ist klarer Favorit (1X2-Quote ${o.aw.toFixed(2)} — kein Wert). Asian Handicap${_ahPt ? ' ' + _ahPt : ''} @ ${_ahOdds.toFixed(2)} bietet deutlich besseres Value. ` + reason;
          // FV gate: same margin-factor formula as computeFairValue (AH section).
          // Suppress if implied prob exceeds model fair prob by >14pp.
          const _ahPtN   = _ahPoint != null ? Math.abs(_ahPoint) : 0;
          const _ahMfA   = _ahPtN >= 3.0 ? 0.27 : _ahPtN >= 2.75 ? 0.32 : _ahPtN >= 2.5 ? 0.37
                         : _ahPtN >= 2.25 ? 0.44 : _ahPtN >= 2.0 ? 0.51 : _ahPtN >= 1.75 ? 0.58
                         : _ahPtN >= 1.5 ? 0.64 : _ahPtN >= 1.25 ? 0.72 : _ahPtN >= 1.0 ? 0.80
                         : _ahPtN >= 0.75 ? 0.87 : _ahPtN >= 0.5 ? 0.93 : 0.97;
          const _ahBoostA  = (_bkrPA ?? 0) > 0.85 ? 1.35 : (_bkrPA ?? 0) > 0.80 ? 1.20 : 1.0;
          const _ahFairPA  = _bkrPA != null ? Math.min(0.90, _bkrPA * Math.min(0.97, _ahMfA * _ahBoostA)) : null;
          const _ahNegEdgeA = !o._isEstimated && _hasNegEdge(_ahFairPA, _ahOdds, false, GATE.AH_REAL, null);
          if (!_ahNegEdgeA) {
            rC.push({sc, p:{icon:'✈️', market:_ahMkt, odds:_ahOdds, conf:_ahConf, reason:_ahReason}});
          }
        }
      }
    }
    // ── Unentschieden ─────────────────────────────────────────────────────
    {
      let sc = drawRate * 0.85 + (drawLikely ? 0.22 : 0);
      if (bothGold) sc += 0.26; if (Math.abs(hFS_home - aFS_away) < 0.10) sc += 0.12;
      if (h2hN >= 5 && drawRate > 0.35) sc += 0.10;
      // Elo: balanced ratings reinforce draw signal; strong gap suppresses it
      if (eloClose) sc += 0.09;
      else if (eloDiff !== null && Math.abs(eloDiff) > 200) sc = Math.max(0, sc - 0.12);
      // Season urgency: when teams MUST win, draw is the worst outcome → suppress it.
      // Graduated: single team needs win → moderate suppress; both need win → strong suppress.
      // Exception: bothGold in a true Titelduell where a draw might still suit the leader.
      if (homeNeedsWin || awayNeedsWin) {
        const drawSuppress = bothNeedWin
          ? _pressureBoost * 1.10   // both teams must win: Remis hilft keinem
          : _pressureBoost * 0.75;  // one team must win: still bad for them
        // Exception: title leader might accept a draw to protect lead → only partially suppress
        const bothGoldLeader = bothGold && !urgencyHigh;
        if (!bothGoldLeader) sc = Math.max(0, sc - drawSuppress);
      }
      // Extra suppression 1: red-zone teams rarely helped by a draw (even if not technically mustWin)
      if ((hc.includes('red') || ac.includes('red')) && !bothNeedWin) sc = Math.max(0, sc - 0.18);
      // Extra suppression 2: heavy market favorite → draw probability is low regardless of form signals
      // _fairPH/PA = blended Pinnacle (80%) + API pct (20%) — most reliable signal of true win prob
      if (_fairPH != null && _fairPH > 0.55) sc = Math.max(0, sc - (_fairPH - 0.55) * 2.2);
      else if (_fairPA != null && _fairPA > 0.55) sc = Math.max(0, sc - (_fairPA - 0.55) * 2.2);
      const _drH2h = h2hN >= 3 ? ` In ${h2hN} Duellen: ${h2h.draws||0}× Remis (${Math.round(drawRate*100)}%).` : ` H2H-Remisquote: ${Math.round(drawRate*100)}%.`;
      let reason = bothGold
        ? `Titelduell zweier gleichwertiger Teams — keiner will verlieren.${_drH2h} Form: ${Math.round(hFS_home*100)}% vs ${Math.round(aFS_away*100)}%${eloClose&&eloLabel?' · '+eloLabel:''}.`
        : `Ausgeglichene Kräfteverhältnisse: Heim ${Math.round(hFS_home*100)}% vs Ausw. ${Math.round(aFS_away*100)}%.${_drH2h}${eloClose&&eloLabel?' '+eloLabel:''}`;
      rC.push({sc, p:{icon:'🤝', market:'Unentschieden', odds:o.dr, conf: sc > 0.62 ? 'medium' : 'low', reason}});
    }
    // ── Draw No Bet (DNB) — Heim ─────────────────────────────────────────
    // Fires when home lean is real but not overwhelming, and draw-rate is non-trivial.
    // DNB removes draw risk: effective prob = homeWinProb / (homeWinProb + awayWinProb).
    // Scoring is deliberately scaled below outright Heimsieg so it only wins in rC when
    // the outright win signal is medium-strength (high outright → DNB odds too low anyway).
    {
      const heimsiegSc = rC.find(r => r.p.market === 'Heimsieg')?.sc ?? 0;
      const sc = heimsiegSc * 0.62 + drawRate * 0.28;
      if (sc > 0.38 && drawRate > 0.20) {
        const conf = sc > 0.50 ? 'medium' : 'low';
        rC.push({sc, p:{icon:'🏠', market:'DNB: Heimteam', odds: o.dnbH||null, conf,
          reason:`${match.home} ist Favorit, aber ein Remis ist zu ${Math.round(drawRate*100)}% möglich. DNB (Draw No Bet) ist eine Absicherung: bei einem Unentschieden bekommst du den Einsatz zurück — nur bei einer Niederlage verlierst du.`}});
      }
    }
    // ── Draw No Bet (DNB) — Auswärts ─────────────────────────────────────
    {
      const auswSc = rC.find(r => r.p.market === 'Auswärtssieg')?.sc ?? 0;
      const sc = auswSc * 0.62 + drawRate * 0.28;
      if (sc > 0.38 && drawRate > 0.20) {
        const conf = sc > 0.50 ? 'medium' : 'low';
        rC.push({sc, p:{icon:'✈️', market:'DNB: Auswärtsteam', odds: o.dnbA||null, conf,
          reason:`${match.away} ist klarer Favorit, aber ein Remis ist zu ${Math.round(drawRate*100)}% möglich. DNB (Draw No Bet) ist eine Absicherung: bei einem Unentschieden bekommst du den Einsatz zurück — nur bei einer Niederlage verlierst du.`}});
      }
    }
    // ── Doppelte Chance ───────────────────────────────────────────────────
    // DC is the right pick when: lean exists, draw is possible, but not strong enough for outright.
    // IMPORTANT: When a team MUST WIN (pressure), the draw component is worth much less —
    // they attack hard (draw less likely) and a draw would be a bad sporting result for them.
    // In that case, the outright win should score higher than DC, so we reduce the draw weight.
    {
      const heimsiegSc = rC.find(r => r.p.market === 'Heimsieg')?.sc ?? 0;
      const auswSc     = rC.find(r => r.p.market === 'Auswärtssieg')?.sc ?? 0;
      const dcHome = heimsiegSc >= auswSc;
      const dcMkt  = dcHome ? 'Doppelte Chance: 1X' : 'Doppelte Chance: X2';
      // When a team must win, the draw option is unlikely AND unhelpful → reduce weight.
      // bothNeedWin: draws are even less likely than when only one team needs a win → lowest weight.
      const _dcDrawW = bothNeedWin ? 0.10 : (dcHome && homeNeedsWin) || (!dcHome && awayNeedsWin) ? 0.25 : 1.0;
      let sc = dcHome
        ? Math.min(0.72, hFS_home * 0.48 + drawRate * 0.40 * _dcDrawW + (hc.includes('gold')||ac.includes('red') ? 0.08 : 0))
        : Math.min(0.68, aFS_away * 0.48 + drawRate * 0.40 * _dcDrawW + (ac.includes('gold')||hc.includes('red') ? 0.08 : 0));
      // 🔑 RELEGATED team in DC: suppress entirely — backing a relegated team (even with draw)
      // is wrong when the opponent is fighting for survival (asymmetric motivation).
      if (dcHome  && hMotivNone && hc.includes('red')) sc = 0;
      if (!dcHome && aMotivNone && ac.includes('red')) sc = 0;
      const conf = sc > 0.55 ? 'medium' : 'low';
      // Pressure note for DC reason when team needs to win (draw doesn't help them)
      const _dcPressNote = !bothNeedWin && ((dcHome && homeNeedsWin) || (!dcHome && awayNeedsWin))
        ? `<br><strong>⚠️ ${dcHome ? match.home : match.away} kämpft um die Meisterschaft und braucht einen Sieg — ein Remis wäre sportlich wertlos. DC sichert trotzdem beide Ergebnisse ab.</strong>`
        : '';
      const reason = dcHome
        ? `${match.home} ist Favorit (${Math.round(hFS_home*100)}% Heimsieg-Rate) — diese Wette gewinnt sowohl bei einem Sieg als auch bei einem Unentschieden. Nur bei einer Niederlage von ${match.home} geht der Einsatz verloren.${_dcPressNote}`
        : `${match.away} zeigt starke Auswärtsform (${Math.round(aFS_away*100)}% Auswärtssieg-Rate) — diese Wette gewinnt sowohl bei einem Sieg als auch bei einem Unentschieden. Nur bei einer Niederlage von ${match.away} geht der Einsatz verloren.${_dcPressNote}`;
      // Prefer real bookmaker DC odds; fall back to 1X2-derived estimate
      const dcOdds = dcHome ? (o.dc1X_bkr||o.dc1X||null) : (o.dcX2_bkr||o.dcX2||null);
      // Skip DC if odds known and < 1.25 — heavy favourite, DC adds no value
      // Edge check: calculate fair DC probability from de-vigged 1X2 odds.
      // If bookmaker offers WORSE price than fair value (negative edge), suppress the pick.
      // This prevents showing DC picks where the bookmaker margin exceeds any model advantage.
      let _dcHasEdge = true;
      if (dcOdds && o.hw && o.dr && o.aw) {
        const _dTot = 1/o.hw + 1/o.dr + 1/o.aw;
        const _fH = (1/o.hw)/_dTot, _fD = (1/o.dr)/_dTot, _fA = (1/o.aw)/_dTot;
        const _dcFairProb = dcHome ? _fH + _fD : _fA + _fD;
        const _dcFairOdds = 1 / _dcFairProb;
        // Allow 2% tolerance — suppress if offered odds are more than 2% below fair value
        if (dcOdds < _dcFairOdds * 0.98) _dcHasEdge = false;
      }
      if (sc > 0 && !(dcOdds !== null && dcOdds < 1.25) && _dcHasEdge) {
        rC.push({sc, p:{icon:'🎯', market:dcMkt, odds:dcOdds, conf, reason}});
      }
    }
    rC.sort((a,b) => b.sc - a.sc);
    // Draw filter: never surface a pure Unentschieden pick.
    // Pure draws are high-variance, odds typically 3.0+ (well above the 1.4–2.0 target range).
    // When a draw situation is present, the DC pick (1X or X2) covers both win and draw
    // with odds in the right range — strictly better risk profile. Demoting to 'low' here
    // lets the existing fallback logic naturally promote DC/DNB instead.
    rC.forEach(r => { if (r.p.market === 'Unentschieden') r.p.conf = 'low'; });
    // Cheap ML filter: Heimsieg/Auswärtssieg mit Quote < 1.35 auf 'low' setzen.
    // Threshold matched to AH trigger (o.hw < 1.35) so that whenever an AH candidate
    // was pushed into rC, the plain Heimsieg/Auswärtssieg gets demoted and AH wins.
    // Previously 1.33 caused a gap (1.33–1.34): browser live odds drifted below 1.33
    // → AH shown in card, but generate_picks.js had stored odds just above 1.33
    // → "Heimsieg" saved in history instead of "AH Heim". Aligning to 1.35 closes the gap.
    rC.forEach(r => {
      if ((r.p.market === 'Heimsieg' || r.p.market === 'Auswärtssieg')
          && r.p.odds != null && r.p.odds < 1.35) r.p.conf = 'low';
    });
    // _topResultMkt is used by PICK 2 consistency guard (awayWinWeak / homeWinWeak).
    // Map DNB/DC/AH back to the underlying directional lean so PICK 2 still works correctly.
    { const _raw = rC[0].p.market;
      _topResultMkt = _raw === 'DNB: Heimteam'      || _raw === 'Doppelte Chance: 1X' || _raw.startsWith('AH Heim') ? 'Heimsieg'
                    : _raw === 'DNB: Auswärtsteam'  || _raw === 'Doppelte Chance: X2' || _raw.startsWith('AH Ausw') ? 'Auswärtssieg'
                    : _raw;
    }
    // Push PICK 1: prefer medium/high result pick.
    // Fallback: if all result picks are low-conf (e.g. both-red evenly matched games),
    // promote the best DC/DNB to medium — these are inherently safer than a raw outright
    // and give the user something actionable when no clear winner exists.
    { const best = rC.find(r => r.p.conf !== 'low');
      if (best) {
        _push(best.p, best.sc);
      } else {
        // No confident result — take safest available (DC preferred, then DNB, then best)
        // 🔑 Never promote a relegated team's side as fallback: if home is relegated,
        //    skip Heimsieg / DC 1X / AH Heim; if away is relegated, skip Auswärtssieg / DC X2 / AH Ausw.
        const _skipHome = hMotivNone && hc.includes('red');
        const _skipAway = aMotivNone && ac.includes('red');
        const _keepable = r => {
          const mkt = r.p.market;
          if (_skipHome && (mkt === 'Heimsieg' || mkt === 'Doppelte Chance: 1X' || mkt.startsWith('AH Heim') || mkt.startsWith('DNB: Heimteam'))) return false;
          if (_skipAway && (mkt === 'Auswärtssieg' || mkt === 'Doppelte Chance: X2' || mkt.startsWith('AH Ausw') || mkt.startsWith('DNB: Auswärtsteam'))) return false;
          // Skip Draw as fallback when: odds > 3.50 (market says it's unlikely) or sc < 0.45.
          // A draw at 3.50+ with no confident result pick = noise, not a tip.
          if (mkt === 'Unentschieden' && ((r.p.odds !== null && r.p.odds > 3.50) || r.sc < 0.45)) return false;
          return true;
        };
        const fallback = rC.find(r => _keepable(r) && r.p.market.startsWith('Doppelte Chance'))
                      || rC.find(r => _keepable(r) && r.p.market.startsWith('DNB'))
                      || rC.find(r => _keepable(r))
                      || null; // if every candidate is a relegated side, emit nothing
        // Only promote if sc is meaningfully positive — never surface sc ≤ 0 or near-zero picks.
        if (fallback && fallback.sc > 0.10) {
          fallback.p.conf = 'medium'; // promote: DC/DNB always safer than a raw outright
          _push(fallback.p, fallback.sc);
        }
      }
    }
  }

  // ╔══════════════════════════════════════════════════════════════════════╗
  // ║  PICK 2 — GOALS / TEMPO MARKET                                     ║
  // ║  xG-based scoring, context boosts per match type                   ║
  // ╚══════════════════════════════════════════════════════════════════════╝
  {
    const gC = [];
    // Consistency guard: if the result pick is won by a low-scoring team (< 1.0/Sp),
    // suppress Over markets and un-suppress Under — avoids e.g. Auswärtssieg + Over 2.5
    // for a defensive away team that only scores 0.8/Sp.
    // Graduated dampening: how defensive is the predicted winner?
    // 0 = no dampening; 1 = full suppression of Over / boost of Under
    // Formula: 0 if attStr ≥ 1.05 (softened from 1.15), linear ramp to 1.0 at attStr ≤ 0.55
    // Rationale: guard was too aggressive — teams scoring 0.9/Sp still produce goals
    // via opponent attack. Only truly defensive teams (≤ 0.55) get full suppression.
    const _awayWinWeak = _topResultMkt === 'Auswärtssieg'
      ? Math.max(0, Math.min(1, (1.05 - awayAttStr) / 0.50)) : 0;
    const _homeWinWeak = _topResultMkt === 'Heimsieg'
      ? Math.max(0, Math.min(1, (1.05 - homeAttStr) / 0.50)) : 0;
    const _favWeak  = Math.max(_awayWinWeak, _homeWinWeak); // 0–1 gradient
    const _favWeak1 = _favWeak > 0;                          // any dampening at all
    // When _favWeak, bothRed boosts/penalties in goals market are bypassed
    const _eBothRed = bothRed && !_favWeak1;

    // Over 3.5
    { let sc = expGoals>3.8?0.82:expGoals>3.4?0.65:expGoals>3.1?0.44:expGoals>2.7?0.20:0.06;
      if (_eBothRed) sc = Math.min(0.88, sc + 0.12);
      if (_favWeak1) sc = Math.max(0, sc - 0.40 * _favWeak);
      // 🔑 PRESSURE/RUNDEN: Druck erhöht Toranzahl leicht, aber Over 3.5 braucht primär hohe xG (Backtest: 37% HR).
      // Boost moderat — reales Edge nur bei genuinen Hochscore-Spielen (expGoals > 3.4 / 3.8).
      if (bothNeedWin)       sc = Math.min(0.90, sc + _pressureBoost * 0.80);
      else if (_anyNeedsWin) sc = Math.min(0.88, sc + _pressureBoost * 0.45);
      // Low-scoring suppression (same logic as Over 2.5)
      { const _bvl = homeAttStr < 0.65 && awayAttStr < 0.65;
        if (_bvl) sc = Math.max(0, sc - 0.40); }
      const _o35H2hNote = (_h2hSample && _h2hAvgG != null) ? ` Historisch Ø ${_h2hAvgG} Tore/Duell.` : '';
      // Low-attack context: when attack stats are modest, the Over signal comes from defensive weakness
      const _o35DefDriven = homeAttStr < 0.85 || awayAttStr < 0.85;
      const _o35BaseNote = _o35DefDriven
        ? `${match.home} erzielt Ø ${homeAttStr.toFixed(1)}, ${match.away} Ø ${awayAttStr.toFixed(1)} Tore/Spiel — die Torerwartung kommt vor allem aus defensiver Anfälligkeit (Gegentore: ${match.home} Ø ${homeDefStr.toFixed(1)}, ${match.away} Ø ${awayDefStr.toFixed(1)}). Das Modell erwartet ${expGoals.toFixed(1)} Tore insgesamt: ein Ergebnis mit 4+ Treffern ist trotz moderater Angriffe möglich.`
        : `${match.home} erzielt Ø ${homeAttStr.toFixed(1)} Tore/Spiel, ${match.away} Ø ${awayAttStr.toFixed(1)} — beide Defensiven sind anfällig und lassen viele Gegentore zu. Das Modell erwartet ${expGoals.toFixed(1)} Tore insgesamt: ein Torfestival mit 4+ Treffern ist klar möglich.`;
      // Asian O/U: pick line ≤ 3.5 closest to ~1.62 (lower threshold = safer bet, similar odds)
      const _ao35Best = _pickBestLine(o.ao_lines, 1.62, 2.75, 3.5);
      const _o35Odds  = _ao35Best ? _ao35Best.price : o.o35;
      const _o35Pt    = _ao35Best ? _ao35Best.pt    : 3.5;
      // 🔑 NEGATIVE EDGE GATE: Poisson-FV-Check — nur bei echten Bookie-Quoten (nicht estimated).
      // Threshold 12pp: wenn Bookie-Wahrscheinlichkeit unsere FV um >12pp überschreitet → kein Edge.
      // Schützt vor strukturell negativen Picks (z.B. Over 3.5 @ 1.65 mit expGoals=3.2 → FV=2.50).
      const _o35FairProb = (!odds?._isEstimated && _o35Odds != null)
        ? _poissonOver(expGoals, 3.5) : null;
      const _o35NegEdge = _hasNegEdge(_o35FairProb, _o35Odds, false, GATE.GOALS_REAL, null);
      if (!_o35NegEdge) gC.push({sc, p:{icon:'🔥', market:`Over ${_o35Pt} Tore`, odds:_o35Odds,
        conf: sc>0.68?'high':sc>0.44?'medium':'low',
        reason:`${_o35BaseNote}${_o35H2hNote}${_bothAttLine}`}}); }

    // Over 2.5
    { let sc = expGoals>3.2?0.78:expGoals>2.8?0.66:expGoals>2.5?0.52:expGoals>2.2?0.30:0.10;
      if (_eBothRed) sc = Math.min(0.88, sc + 0.16);
      if (bothGold && !anyRed) sc = Math.max(0, sc - 0.10);
      if (_favWeak1) sc = Math.max(0, sc - 0.40 * _favWeak);
      // 🔑 PRESSURE/RUNDEN: Over 2.5 profitiert weniger von Druck als BTTS (Backtest: 54% Hit-Rate in MustWin,
      // unterhalb Breakeven bei ~1.80er Quoten). Boost reduziert um Borderline-Picks in Medium-Conf zu vermeiden.
      if (bothNeedWin)       sc = Math.min(0.90, sc + _pressureBoost * 0.70);
      else if (_anyNeedsWin) sc = Math.min(0.88, sc + _pressureBoost * 0.45);
      // Titelduell in Crunch-Zeit: kontrolliertes Spiel → leichte Over-Suppression
      if (anyGold && !anyRed && urgencyHigh) sc = Math.max(0, sc - 0.07);
      // 🔑 H2H GOALS HISTORY: over25Rate + avgGoals as independent confirmation
      sc = Math.min(0.92, Math.max(0, sc + _h2hO25Mod + _h2hAvgGMod));
      // 🔑 CLEAN SHEET / FAILED TO SCORE: both teams rarely shut out → Over supported
      if (_hCSHome !== null && _aCSAway !== null) {
        const _csAvg = (_hCSHome + _aCSAway) / 2;
        if (_csAvg <= 0.12) sc = Math.min(0.92, sc + 0.06);   // rarely shut out → both attack well
        else if (_csAvg >= 0.45) sc = Math.max(0, sc - 0.10); // very defensive → Over less likely
      }
      // 🔑 API PREDICTION CONSENSUS: independent model agrees → amplify signal
      if (_apiUO === 'Over 2.5') sc = Math.min(0.92, sc + 0.07);
      else if (_apiUO === 'Under 2.5') sc = Math.max(0, sc - 0.06);
      // 🔑 LOW-SCORING SUPPRESSION: both teams structurally can't score enough for Over 2.5
      // Antalyaspor/Konyaspor (Ø 0.5 gpg), Osijek/Varazdin (Ø 0.4 gpg) etc.
      // attStr < 0.65 ≈ teams averaging under ~0.7 goals/game after adjustments
      { const _bothVeryLow = homeAttStr < 0.65 && awayAttStr < 0.65;
        const _h2hLowG = _h2hSample && _h2hAvgG !== null && _h2hAvgG < 2.0;
        if (_bothVeryLow && _h2hLowG) sc = Math.max(0, sc - 0.50);      // both low + H2H confirms → strong
        else if (_bothVeryLow)         sc = Math.max(0, sc - 0.30);      // both low → moderate
        else if ((homeAttStr < 0.65 || awayAttStr < 0.65) && _h2hLowG)
                                       sc = Math.max(0, sc - 0.18); }    // one side + H2H → mild
      const _o25H2hNote = (_h2hSample && _h2hOver25 != null)
        ? ` Historisch ${Math.round(_h2hOver25*100)}% der ${h2hN} Duelle über 2.5 Tore${_h2hAvgG!=null?' (Ø '+_h2hAvgG+' Tore/Spiel)':''}.`
        : '';
      const _o25ApiTotal = (_apiGoalsH !== null && _apiGoalsA !== null && _apiGoalsH > 0 && _apiGoalsA > 0)
        ? _apiGoalsH + _apiGoalsA : null;
      const _o25ApiNote = _o25ApiTotal !== null
        ? (_o25ApiTotal >= 2.5
            ? `<br>🤖 API-Modell erwartet ${_o25ApiTotal.toFixed(1)} Tore — bestätigt die Over-Prognose.`
            : `<br>⚠️ API-Modell erwartet nur ${_o25ApiTotal.toFixed(1)} Tore — geht von weniger Toren aus.`)
        : '';
      // Hard gate: Kein Over 2.5-Pick wenn Modell selbst < 2.5 Tore erwartet (verhindert Widersprüche)
      const _o25GoalText = expGoals > 2.8
        ? `mindestens 3 Treffer sind gut möglich`
        : `mit ${expGoals.toFixed(1)} erwarteten Toren ist die Marke von 2.5 Toren erreichbar`;
      // Low-attack context: when one or both teams barely score, explain the Over via defensive weakness
      const _o25DefDriven = homeAttStr < 0.85 || awayAttStr < 0.85;
      const _o25BaseNote = _o25DefDriven
        ? `${match.home} erzielt Ø ${homeAttStr.toFixed(1)}, ${match.away} Ø ${awayAttStr.toFixed(1)} Tore/Spiel — die Torerwartung kommt vor allem aus anfälligen Defensiven (Gegentore: ${match.home} Ø ${homeDefStr.toFixed(1)}, ${match.away} Ø ${awayDefStr.toFixed(1)}). Das Modell erwartet ${expGoals.toFixed(1)} Tore: ${_o25GoalText}.`
        : `${match.home} erzielt Ø ${homeAttStr.toFixed(1)} Tore/Spiel, ${match.away} Ø ${awayAttStr.toFixed(1)} — beide Defensiven lassen regelmäßig Gegentore zu (Gegentore: ${match.home} Ø ${homeDefStr.toFixed(1)}, ${match.away} Ø ${awayDefStr.toFixed(1)}). Das Modell erwartet ${expGoals.toFixed(1)} Tore: ${_o25GoalText}.`;
      if (expGoals >= 2.5) {
        // Asian O/U: pick line ≤ 2.5 closest to ~1.62 (lower threshold = safer, same or better odds)
        const _ao25Best = _pickBestLine(o.ao_lines, 1.62, 2.0, 2.5);
        const _o25Odds  = _ao25Best ? _ao25Best.price : o.o25;
        const _o25Pt    = _ao25Best ? _ao25Best.pt    : 2.5;
        // 🔑 NEGATIVE EDGE GATE: Poisson-FV-Check (identisch Corners-Logik).
        // Bei echter Bookie-Quote: wenn implizierte Wahrscheinlichkeit FV um >12pp überschreitet → kein Edge.
        // (Frühere Annahme "Hard Gate reicht" war falsch: expGoals=2.5 mit Odds 1.65 hat -15pp Edge)
        const _o25FairProb = (!odds?._isEstimated && _o25Odds != null)
          ? _poissonOver(expGoals, 2.5) : null;
        const _o25NegEdge = _hasNegEdge(_o25FairProb, _o25Odds, false, GATE.GOALS_REAL, null);
        if (!_o25NegEdge) gC.push({sc, p:{icon:'⚽', market:`Over ${_o25Pt} Tore`, odds:_o25Odds,
          conf: sc>0.66?'high':sc>0.46?'medium':'low',
          reason:`${_o25BaseNote}${_o25H2hNote}${_o25ApiNote}${_bothAttLine}`}}); } }

    // Under 2.5
    { let sc = expGoals<1.7?0.85:expGoals<2.0?0.72:expGoals<2.3?0.57:expGoals<2.6?0.34:0.12;
      if (bothGold && !anyRed && expGoals < 2.5) sc = Math.min(0.90, sc + 0.12);
      if (_eBothRed) sc = Math.max(0, sc - 0.28);
      if (_favWeak1) sc = Math.min(0.90, sc + 0.40 * _favWeak);
      // 🔑 PRESSURE/RUNDEN: Muss-gewinnen → Angriffsdrang killt Under-Signal
      // Note: bothNeedWin already fully handled below — no separate _favWeak1 penalty needed
      if (bothNeedWin)       sc = Math.max(0, sc - _pressureBoost * 1.10);
      else if (_anyNeedsWin) sc = Math.max(0, sc - _pressureBoost * 0.65);
      // 🔑 H2H: under 2.5 is inverse of both H2H modifiers
      sc = Math.min(0.92, Math.max(0, sc - _h2hO25Mod - _h2hAvgGMod));
      // 🔑 H2H HARD GATE: wenn H2H-Durchschnitt deutlich über der Under-2.5-Linie liegt,
      // ist der Pick strukturell widerlegbar — die Paarung produziert historisch mehr Tore.
      // Analog zu Under 1.5 (HARD BLOCK bei ≥ 2.5 Ø): Under 2.5 HARD BLOCK bei ≥ 3.5 Ø.
      // Unter diesem Niveau: starke Dämpfung statt Hard Block (da Under 2.5 mehr Spielraum hat).
      if (_h2hSample && _h2hAvgG != null) {
        if      (_h2hAvgG >= 3.5) sc = 0;                        // HARD BLOCK — H2H widerlegt eindeutig (Ø ≥ 3.5 Tore)
        else if (_h2hAvgG >= 3.0) sc = Math.max(0, sc - 0.35);  // starke Dämpfung
        else if (_h2hAvgG >= 2.8) sc = Math.max(0, sc - 0.18);  // moderate Dämpfung
      }
      if (_h2hSample && _h2hBtts != null) {
        if      (_h2hBtts >= 0.75) sc = 0;                        // HARD BLOCK — BTTS 75%+ widerlegt Under 2.5
        else if (_h2hBtts >= 0.65) sc = Math.max(0, sc - 0.22); // beide treffen sehr häufig → starke Dämpfung
        else if (_h2hBtts >= 0.55) sc = Math.max(0, sc - 0.12); // beide treffen häufig → leichte Dämpfung
      }
      // 🔑 CLEAN SHEET / FAILED TO SCORE: defensive teams at home + struggling away attackers → Under
      if (_hCSHome !== null && _aCSAway !== null) {
        const _csAvg = (_hCSHome + _aCSAway) / 2;
        if (_csAvg >= 0.40) sc = Math.min(0.92, sc + 0.10);   // both very defensive → Under likely
        else if (_csAvg >= 0.30) sc = Math.min(0.92, sc + 0.05);
      }
      if (_aFTSAway !== null && _aFTSAway >= 0.35) sc = Math.min(0.92, sc + 0.07);  // away often fails to score
      if (_hFTSHome !== null && _hFTSHome >= 0.30) sc = Math.min(0.92, sc + 0.05);  // home also struggles to score
      // 🔑 API PREDICTION CONSENSUS
      if (_apiUO === 'Under 2.5') sc = Math.min(0.92, sc + 0.07);
      else if (_apiUO === 'Over 2.5') sc = Math.max(0, sc - 0.06);
      const _u25DefTeam = _topResultMkt==='Heimsieg'?match.home:_topResultMkt==='Auswärtssieg'?match.away:null;
      const _pressWarn = _anyNeedsWin
        ? `<br><strong>⚠️ ${bothNeedWin ? 'Beide Teams' : homeNeedsWin ? match.home : match.away} unter Druck${_rlSfx} — Angriffsdrang erhöht Torrisiko, Under-Signal geschwächt.</strong>` : '';
      const _u25H2hNote = (_h2hSample && _h2hOver25 != null)
        ? ` Historisch ${100-Math.round(_h2hOver25*100)}% der ${h2hN} Duelle unter 2.5 Tore${_h2hAvgG!=null?' (Ø '+_h2hAvgG+' Tore/Spiel)':''}.`
        : '';
      const _u25CSNote = (_hCSHome !== null || _aFTSAway !== null)
        ? `<br>📊 Saison-Statistiken: ${_hCSHome !== null ? `${match.home} ${Math.round(_hCSHome*100)}% Clean Sheets zuhause` : ''}${_hCSHome !== null && _aFTSAway !== null ? ' · ' : ''}${_aFTSAway !== null ? `${match.away} trifft in ${Math.round(_aFTSAway*100)}% der Auswärtsspiele nicht` : ''}.`
        : '';
      const _u25Reason = _favWeak > 0.4 && _u25DefTeam
        ? `${_u25DefTeam} dominiert dieses Spiel — der schwächere Angriff (Ø ${Math.min(homeAttStr,awayAttStr).toFixed(1)} Tore/Spiel) kommt kaum zu Chancen. Weniger als 3 Tore sind zu erwarten.${_u25H2hNote}${_u25CSNote}${_pressWarn}${_bothDefLine}`
        : `Das Modell erwartet nur ${expGoals.toFixed(1)} Tore insgesamt — ${match.home} (Ø ${homeAttStr.toFixed(1)} Tore/Spiel) und ${match.away} (Ø ${awayAttStr.toFixed(1)}) sind beide offensiv zu schwach für viele Treffer.${_u25H2hNote}${_u25CSNote}${_pressWarn}${_bothDefLine}`;
      // 🔑 MINIMUM THRESHOLD: Under 2.5 nur pushen wenn sc ≥ 0.38
      // Verhindert schwache Restpicks (nach H2H-Dämpfung) im Low-Conf-Bereich
      if (sc >= 0.38) gC.push({sc, p:{icon:'🛡️', market:'Under 2.5 Tore', odds:o.u25,
        conf: sc>0.68?'high':sc>0.48?'medium':'low',
        reason: _u25Reason}}); }

    // Under 1.5
    { let sc = expGoals<1.4?0.76:expGoals<1.7?0.54:0.08;
      // 🔑 PRESSURE/RUNDEN: jedes Muss-gewinnen zerstört Under 1.5 komplett
      if (_anyNeedsWin) sc = Math.max(0, sc - _pressureBoost * 1.50);
      // 🔑 H2H HARD GATE: wenn H2H Ø ≥ 2.5 Tore → Under 1.5 ist klar widerlegt → sc = 0
      // (vorher: sc - 0.55 ließ sc=0.21 übrig → Pick erschien trotzdem. Heracles/Volendam-Bug Apr 2026)
      // H2H ≥ 2.5 Ø: beide Teams treffen historisch → Under 1.5 macht keinen Sinn
      // H2H 2.0–2.5: moderate Widerlegung (-0.35, statt -0.28)
      // BTTS ≥ 60%: beide Teams treffen häufig → Under 1.5 benötigt 0+0 oder 1+0
      if (_h2hSample && _h2hAvgG != null) {
        if      (_h2hAvgG >= 2.5) sc = 0;                        // HARD BLOCK — H2H widerlegt eindeutig
        else if (_h2hAvgG >= 2.0) sc = Math.max(0, sc - 0.35);  // starke Dämpfung
      }
      if (_h2hSample && _h2hBtts != null && _h2hBtts >= 0.60) {
        sc = 0; // HARD BLOCK — BTTS 60%+ macht Under 1.5 unvertretbar
      }
      // 🔑 MINIMUM THRESHOLD: Under 1.5 nur pushen wenn sc ≥ 0.42
      // Verhindert dass sehr schwache Picks (nach H2H-Reduktion) trotzdem erscheinen
      if (sc >= 0.42) gC.push({sc, p:{icon:'🔒', market:'Under 1.5 Tore', odds:o.u15||null,
        conf: sc>0.65?'medium':'low',
        reason:`Das Modell erwartet nur ${expGoals.toFixed(1)} Tore — beide Teams sind offensiv extrem schwach. Ein einziger Treffer in diesem Spiel wäre schon viel.`}}); }

    // BTTS Ja
    { let sc = 0.14;
      sc += Math.min(0.22, Math.max(0, (homeAttStr - 0.95) * 0.38));
      sc += Math.min(0.20, Math.max(0, (awayAttStr - 0.80) * 0.44));
      sc += Math.min(0.14, Math.max(0, (homeDefStr - 0.80) * 0.30));
      sc += Math.min(0.12, Math.max(0, (awayDefStr - 0.80) * 0.30));
      if (_eBothRed) sc = Math.min(0.88, sc + 0.22);
      if (anyGold && !anyRed) sc = Math.max(0, sc - 0.08);
      if (bttsBad) sc *= 0.35;
      if (_favWeak1) sc *= (1 - _favWeak * 0.65);
      // 🔑 PRESSURE/RUNDEN: BTTS ist der stärkste MustWin-Markt (Backtest: 67–68% Hit-Rate).
      // Druckteam öffnet sich → Gegner nutzt Räume → beide treffen fast zwangsläufig.
      // Boost deutlich erhöht gegenüber Over 2.5 (was: 1.10/0.55).
      if (bothNeedWin)       sc = Math.min(0.90, sc + _pressureBoost * 1.30);
      else if (_anyNeedsWin) sc = Math.min(0.86, sc + _pressureBoost * 0.80);
      // 🔑 H2H BTTS HISTORY: real historical BTTS rate from direct meetings
      sc = Math.min(0.92, Math.max(0, sc + _h2hBttsMod));
      sc = Math.min(0.92, sc);
      // Suppress BTTS when either team is a massive underdog (odds > 5.0):
      // very weak teams rarely score regardless of motivation → BTTS is unrealistic.
      // In these cases BTTS Nein or a goals pick without that team's contribution is more accurate.
      if ((o.hw && o.hw > 5.0) || (o.aw && o.aw > 5.0)) sc = Math.max(0, sc - 0.30);
      else if ((o.hw && o.hw > 3.5) || (o.aw && o.aw > 3.5)) sc = Math.max(0, sc - 0.10);
      // 🔑 CLEAN SHEET / FAILED TO SCORE: direct evidence against BTTS
      // If away team often fails to score away AND home team often keeps clean sheets → BTTS very unlikely
      if (_hCSHome !== null && _hCSHome >= 0.40) sc = Math.max(0, sc - 0.10);
      if (_aFTSAway !== null && _aFTSAway >= 0.35) sc = Math.max(0, sc - 0.10);
      if (_hCSHome !== null && _aFTSAway !== null && _hCSHome >= 0.35 && _aFTSAway >= 0.30) sc = Math.max(0, sc - 0.08); // compound: both signals confirm
      const _bttsPressNote = bothNeedWin
        ? `<br><strong>⚡ Beide Teams müssen gewinnen${_rlSfx} — beide greifen an, beide riskieren Kontertore.</strong>`
        : _anyNeedsWin ? `<br><strong>⚡ ${homeNeedsWin ? _pHLabel : _pALabel}${_rlSfx} — öffnet hinten Räume, Kontertreffer für Gegner wahrscheinlich.</strong>` : '';
      const _bttsH2hNote = (_h2hSample && _h2hBtts != null)
        ? ` Historisch ${Math.round(_h2hBtts*100)}% der ${h2hN} Duelle mit Toren auf beiden Seiten.`
        : '';
      // 🔑 BTTS NEGATIVE EDGE GATE: Poisson-basiert, getrennte Heim/Auswärts-Erwartungen.
      // P(BTTS) = P(home≥1) × P(away≥1) = (1 - e^-expH) × (1 - e^-expA)
      // Nur bei echten BTTS-Quoten (nicht estimated) prüfen.
      { const _expH = Math.max(0.1, (homeAttStr + awayDefStr) / 2);
        const _expA = Math.max(0.1, (awayAttStr + homeDefStr) / 2);
        const _bttsFairProb = (!o._bttsOddsEst && o.bttsY != null)
          ? (1 - Math.exp(-_expH)) * (1 - Math.exp(-_expA)) : null;
        const _bttsNegEdge = _hasNegEdge(_bttsFairProb, o.bttsY, false, GATE.GOALS_REAL, null);
        if (!_bttsNegEdge) gC.push({sc, p:{icon:'⚽', market:'Beide Teams treffen', odds:o.bttsY||null, oddsIsEst: o._bttsOddsEst||false,
          conf: sc>0.65?'high':sc>0.44?'medium':'low',
          reason:`${match.home} (Ø ${homeAttStr.toFixed(1)} Tore/Spiel) und ${match.away} (Ø ${awayAttStr.toFixed(1)}) treffen beide regelmäßig — beide Defensiven sind anfällig und lassen Gegentore zu. Beide Teams werden voraussichtlich treffen.${_bttsH2hNote}${_bttsPressNote}${_bothAttLine}`}}); }
      }

    // BTTS Nein
    { const bothAttWeak = homeAttStr < 0.88 && awayAttStr < 0.82;
      const oneAttWeak  = !bothAttWeak && bttsBad;
      let sc = bothAttWeak ? 0.70 : oneAttWeak ? 0.38 : bttsNoSignal ? 0.22 : 0.08;
      if (anyGold && anyRed) sc = Math.min(0.80, sc + 0.15);
      if (_eBothRed) sc = Math.max(0, sc - 0.35);
      if (_favWeak1) sc = Math.min(0.80, sc + 0.20 * _favWeak);
      // 🔑 PRESSURE/RUNDEN: Druck-Team greift an → Kontertore entstehen → BTTS Nein sehr unwahrscheinlich
      if (bothNeedWin)       sc = Math.max(0, sc - _pressureBoost * 1.20);
      else if (_anyNeedsWin) sc = Math.max(0, sc - _pressureBoost * 0.70);
      // 🔑 H2H BTTS HISTORY: inverse of BTTS Ja modifier — high historical BTTS rate suppresses Nein
      sc = Math.min(0.80, Math.max(0, sc - _h2hBttsMod));
      // 🔑 CLEAN SHEET / FAILED TO SCORE: season-long evidence for BTTS No
      if (_hCSHome !== null && _hCSHome >= 0.45) sc = Math.min(0.88, sc + 0.14); // home rarely concedes at home
      else if (_hCSHome !== null && _hCSHome >= 0.32) sc = Math.min(0.88, sc + 0.07);
      if (_aFTSAway !== null && _aFTSAway >= 0.40) sc = Math.min(0.88, sc + 0.12); // away rarely scores away
      else if (_aFTSAway !== null && _aFTSAway >= 0.28) sc = Math.min(0.88, sc + 0.06);
      const weakAtt = homeAttStr<awayAttStr?match.home:match.away;
      const _bttsNoH2h = (_h2hSample && _h2hBtts != null)
        ? ` Historisch ${100-Math.round(_h2hBtts*100)}% der ${h2hN} Duelle blieb ein Team torlos.`
        : '';
      // Build clean sheet / FTS note for reason text
      const _bttsNoStatNote = (_hCSHome !== null || _aFTSAway !== null)
        ? `<br>📊 Saison-Stats: ${_hCSHome !== null ? `${match.home} hält ${Math.round(_hCSHome*100)}% Clean Sheets zuhause` : ''}${_hCSHome !== null && _aFTSAway !== null ? ' · ' : ''}${_aFTSAway !== null ? `${match.away} trifft in ${Math.round(_aFTSAway*100)}% der Auswärtsspiele nicht` : ''}.`
        : '';
      gC.push({sc, p:{icon:'🔒', market:'Beide Teams treffen: Nein', odds:o.bttsN||null, oddsIsEst: o._bttsOddsEst||false,
        conf: sc>0.58?'medium':'low',
        reason:`${weakAtt} ist offensiv sehr schwach (Ø ${Math.min(homeAttStr,awayAttStr).toFixed(1)} Tore/Spiel) — ein Treffer ist für dieses Team schon eine Herausforderung. Wahrscheinlich bleibt eines der beiden Teams ohne Tor.${_bttsNoH2h}${_bttsNoStatNote}${_bothDefLine}`}}); }

    // ── Heimteam Over 1.5 Tore — BACKTEST VALIDATED: 69% bei expHome > 1.85 ──────
    { const expH = (homeAttStr + awayDefStr) / 2;
      let sc     = expH > 2.10 ? 0.78 : expH > 1.95 ? 0.66 : expH > 1.85 ? 0.56 : 0;
      // 🔑 PRESSURE: Heimteam muss gewinnen → All-in-Angriff → Over 1.5 noch wahrscheinlicher
      if (sc > 0 && homeNeedsWin) sc = Math.min(0.88, sc + _pressureBoost * 0.90);
      if (sc > 0) {
        const _xL = xGBased ? 'xG' : 'Tore';
        const _hPN = homeNeedsWin ? `<br><strong>⚡ ${_pHLabel}${_rlSfx} — Heimteam greift voll an, Over 1.5 durch Druckspiel klar verstärkt.</strong>` : '';
        // FV gate: Poisson P(H≥2) vs implied odds probability.
        // Real odds: suppress at >12pp gap. Estimated odds: suppress at >15pp (wider, model uncertainty).
        const _hto15Odds = o.hto15 || null;
        const _hto15FV   = _hto15Odds != null ? _poissonOver(expH, 1.5) : null;
        const _hto15NegEdge = _hasNegEdge(_hto15FV, _hto15Odds, o._hto15Est, GATE.TEAM_REAL, GATE.TEAM_EST);
        if (!_hto15NegEdge) {
          gC.push({sc, p:{icon:'🏠', market:`${match.home} über 1.5 Tore`, odds: _hto15Odds, oddsIsEst: o._hto15Est||false,
            conf: sc > 0.68 ? 'high' : 'medium',
            reason:`${match.home} trifft im Schnitt ${homeAttStr.toFixed(1)} Mal pro Spiel — der Gegner lässt ${awayDefStr.toFixed(1)} Tore zu. Das Modell erwartet ${expH.toFixed(1)} Heimtore: mindestens 2 Treffer für ${match.home} sind gut möglich.${_attLineHome ? '<br>⚽ ' + _attLineHome : ''}`}});
        }
      }
    }

    // ── Auswärtsteam Over 1.5 Tore — BACKTEST VALIDATED: 65%+ bei expAway > 1.90 ─
    { const expA = (awayAttStr + homeDefStr) / 2;
      let sc     = expA > 2.10 ? 0.68 : expA > 1.95 ? 0.56 : 0;
      // 🔑 PRESSURE: Auswärtsteam muss gewinnen → volles Risiko → mehr Auswärtstore
      if (sc > 0 && awayNeedsWin) sc = Math.min(0.82, sc + _pressureBoost * 0.85);
      if (sc > 0) {
        const _xL = xGBased ? 'xG' : 'Tore';
        const _aPN = awayNeedsWin ? `<br><strong>⚡ ${_pALabel}${_rlSfx} — Auswärtsteam geht volles Risiko, Over 1.5 durch Druckspiel verstärkt.</strong>` : '';
        // FV gate: Poisson P(A≥2) vs implied odds probability.
        const _ato15Odds = o.ato15 || null;
        const _ato15FV   = _ato15Odds != null ? _poissonOver(expA, 1.5) : null;
        const _ato15NegEdge = _hasNegEdge(_ato15FV, _ato15Odds, o._ato15Est, GATE.TEAM_REAL, GATE.TEAM_EST);
        if (!_ato15NegEdge) {
          gC.push({sc, p:{icon:'✈️', market:`${match.away} über 1.5 Tore`, odds: _ato15Odds, oddsIsEst: o._ato15Est||false,
            conf: sc > 0.65 ? 'medium' : 'low',
            reason:`${match.away} trifft im Schnitt ${awayAttStr.toFixed(1)} Mal pro Spiel — der Gegner lässt ${homeDefStr.toFixed(1)} Tore zu. Das Modell erwartet ${expA.toFixed(1)} Auswärtstore: mindestens 2 Treffer für ${match.away} sind gut möglich.${_attLineAway ? '<br>⚽ ' + _attLineAway : ''}`}});
        }
      }
    }

    // 1HZ Under 0.5 (tactical opener — suppressed when any team is under pressure)
    { let sc = (bothGold && expGoals < 2.5) ? 0.55 : firstHalfTight ? 0.44 : 0.12;
      // 🔑 PRESSURE/RUNDEN: Druckteam presst von Minute 1 → kein langsamer Start
      if (_anyNeedsWin) sc = Math.max(0, sc - _pressureBoost * 1.20);
      gC.push({sc, p:{icon:'⏱️', market:'1. HZ: Under 0.5 Tore', odds:o.ht_u05||null,
        conf: sc>0.50?'medium':'low',
        reason:`Taktisch vorsichtiger Spielbeginn erwartet — beide Teams tasten sich ab. Das Modell erwartet insgesamt nur ${expGoals.toFixed(1)} Tore: ein torloser Start in die erste Halbzeit ist gut möglich.`}}); }

    gC.sort((a,b) => b.sc - a.sc);
    for (const c of gC) { if (_push(c.p, c.sc)) break; }
  }

  // ╔══════════════════════════════════════════════════════════════════════╗
  // ║  PICK 3 — SPECIALIST MARKET                                        ║
  // ║  Corners / Cards / Handicap / HZ / Shots — diverse from picks 1+2 ║
  // ╚══════════════════════════════════════════════════════════════════════╝
  {
    const sC = [];

    // ── Corners Over / Under ────────────────────────────────────────────────────
    // Over: high corners expected. Under: defensively-oriented match with low corners.
    // When cornersDataReal: estimate from real stats_cache averages → slight confidence boost.
    // Odds from parseBets corners market (co95/cu95/co85/cu85/co105/cu105/co115).
    {
      // ── Over ─────────────────────────────────────────────────────────────────
      let scO = cornersOver11 ? 0.74 : cornersOver9 ? 0.58 : cornersOver8 ? 0.40 : 0.18;
      if (bothBlue) scO = Math.min(scO + 0.06, 0.82);
      // 🔑 PRESSURE: Druckteam presst aggressiv → erzwingt mehr Ecken
      if (bothNeedWin)       scO = Math.min(0.88, scO + _pressureBoost * 1.00);
      else if (_anyNeedsWin) scO = Math.min(0.82, scO + _pressureBoost * 0.55);
      // Real corner data → slight confidence boost (better estimate than formula)
      if (cornersDataReal) scO = Math.min(0.92, scO + 0.05);
      // Choose market line closest to estimate from below.
      // MIN_ODD escalation: if the chosen Over line is too cheap (< 1.35) because
      // cornersEst greatly exceeds the threshold, step up to a higher line.
      // Higher Over line = harder to hit = better odds.  Keep stepping until >= 1.35
      // or until no higher line is available (then keep current regardless).
      const _OVER_MIN_ODD = 1.35;
      const _overLines = [
        { mkt:'Über 8.5 Ecken',  odds: o.co85  || null },
        { mkt:'Über 9.5 Ecken',  odds: o.co95  || null },
        { mkt:'Über 10.5 Ecken', odds: o.co105 || null },
        { mkt:'Über 11.5 Ecken', odds: o.co115 || null },
      ];
      // Starting line: based on cornersEst
      let _overStartIdx = cornersEst >= 11.5 ? 3 : cornersEst >= 10.5 ? 2 : cornersEst >= 9.5 ? 1 : 0;
      // Escalate if odds too cheap
      let _overIdx = _overStartIdx;
      while (_overIdx < _overLines.length - 1) {
        const _chk = _overLines[_overIdx].odds;
        if (_chk !== null && _chk < _OVER_MIN_ODD) _overIdx++;
        else break;
      }
      const _cOMkt  = _overLines[_overIdx].mkt;
      const _cOOdds = _overLines[_overIdx].odds;
      const _cornPressNote = _anyNeedsWin
        ? ` ${bothNeedWin ? 'Beide Teams' : homeNeedsWin ? match.home : match.away} unter Druck${_rlSfx} — intensives Pressing erzwingt mehr Ecken.` : '';
      const _cornDataNote = cornersDataReal
        ? `<br>📊 Echte Ecken-Daten (Saison): ${match.home} Ø ${_hCornersHome} Heim · ${match.away} Ø ${_aCornersAway} Ausw. → Ø ${cornersEst.toFixed(1)} erwartet.`
        : ``;
      // Estimated corner odds below 1.55 offer no real value — skip pick entirely.
      // Real bookmaker odds (oddsIsEst=false) always pass regardless of level.
      const _EST_CORNER_MIN_ODDS = 1.55;
      const _cornSkip = o._cornersOddsEst && _cOOdds != null && _cOOdds < _EST_CORNER_MIN_ODDS;
      // Max odds guard: skip if odds > 3.20 (real or estimated).
      // Odds above 3.20 mean the expected corners are well below the line —
      // the model has no edge and the pick is low-value noise.
      const _OVER_MAX_ODD = 3.20;
      const _cornSkipHigh = _cOOdds != null && _cOOdds > _OVER_MAX_ODD;
      // Minimum signal guard: sc < 0.25 = too weak to show regardless of odds.
      const _cornSkipLowSc = scO < 0.25;
      // Negative edge gate: Poisson fair value vs bookie/estimated implied probability.
      // Real bookie odds: suppress if implied prob exceeds FV by >10pp (tight gate, real data).
      // Estimated odds: suppress if implied prob exceeds FV by >15pp (wider gate, model uncertainty).
      // This catches cases like Estrela/Porto -21pp or Osasuna/Sevilla -23pp on estimated lines.
      const _cornLineNums = [8.5, 9.5, 10.5, 11.5];
      const _cornFairProbO = _cOOdds != null
        ? _poissonOver(cornersEst, _cornLineNums[_overIdx])
        : null;
      const _cornNegEdge = _hasNegEdge(_cornFairProbO, _cOOdds, o._cornersOddsEst, GATE.CORN_REAL, GATE.CORN_EST);
      if (!_cornSkip && !_cornSkipHigh && !_cornSkipLowSc && !_cornNegEdge)
      sC.push({sc: scO, p:{icon:'🚩', market:_cOMkt, odds:_cOOdds, oddsIsEst: o._cornersOddsEst||false,
        conf: scO>0.65?'high':scO>0.38?'medium':'low',
        reason:`${cornersDataReal
          ? `Saisonstatistik: ${cornersEst.toFixed(1)} Ecken erwartet (${match.home} Ø ${_hCornersHome} Heim + ${match.away} Ø ${_aCornersAway} Ausw.).`
          : `Beide Teams spielen offensiv — ca. ${cornersEst.toFixed(0)} Ecken werden in diesem Spiel erwartet.${_defBonus > 0.5 ? ' Beide Defensiven sind anfällig, was viele Angriffe und damit mehr Ecken begünstigt.' : ''}`
        }${_cornPressNote}${_cornDataNote}`}});

      // ── Under ────────────────────────────────────────────────────────────────
      // Only meaningful when estimate clearly below the chosen threshold.
      // MIN_ODD guard: Under-Ecken odds fall as the line rises (higher Under = even more
      // certain = even cheaper). So if the chosen line has odds < 1.35 there is no
      // meaningful value on ANY Under line — drop the pick entirely rather than
      // suggesting a higher line that would be even shorter.
      if (cornersEst < 9.0 && !_anyNeedsWin) {
        let scU = cornersEst < 7.0 ? 0.72 : cornersEst < 7.5 ? 0.60 : cornersEst < 8.0 ? 0.47 : 0.34;
        if (cornersDataReal) scU = Math.min(0.88, scU + 0.06);
        if (scU >= 0.32) {
          const _cUMkt  = cornersEst < 7.5 ? 'Unter 8.5 Ecken' : 'Unter 9.5 Ecken';
          const _cUOdds = _cUMkt === 'Unter 8.5 Ecken' ? (o.cu85 || null) : (o.cu95 || null);
          // Drop pick when odds are known but below the minimum threshold (1.35).
          // A 1.11 "Unter 8.5" is not a recommendation — it's noise.
          const _UNDER_MIN_ODD = 1.35;
          const _underOddsOk = _cUOdds == null || _cUOdds >= _UNDER_MIN_ODD;
          if (_underOddsOk) {
            const _uDataNote = cornersDataReal
              ? `<br>📊 Echte Ecken-Daten (Saison): ${match.home} Ø ${_hCornersHome} Heim · ${match.away} Ø ${_aCornersAway} Ausw. → nur Ø ${cornersEst.toFixed(1)} erwartet.`
              : ``;
            sC.push({sc: scU, p:{icon:'🚩', market:_cUMkt, odds:_cUOdds, oddsIsEst: o._cornersOddsEst||false,
              conf: scU>0.60?'high':scU>0.38?'medium':'low',
              reason:`${cornersDataReal
                ? `Defensives Spiel — Saisonschnitt ergibt nur ${cornersEst.toFixed(1)} Ecken gesamt.`
                : `Taktisch defensives Spiel mit erwarteten ~${cornersEst.toFixed(0)} Ecken.`
              }${_uDataNote}`}});
          }
        }
      }
    }

    // ── Cards — granular mit Runden-Faktor ────────────────────────────────────
    // 🔑 PRESSURE/RUNDEN: Karten-Signal ist Druck × Intensität — beide Faktoren eingerechnet
    { let cardSc = 0;
      let cardMkt = 'Über 3.5 Karten';
      let cardReason = '';
      if (cardsVeryHigh) {
        // Beide im Abstieg + schlechte Form: 4.5er realistisch
        cardSc  = Math.min(0.96, 0.90 + _cardPressBoost * 0.30 + _refCardMod);
        cardMkt = 'Über 4.5 Karten';
        cardReason = _bothRedConf
          ? `Duell bestätigter Absteiger${_rlSfx} — kein Abstiegsdruck mehr, aber Frust und schlechte Form können Aggressivität antreiben. Karten möglich.`
          : _anyRedConf
            ? `Schlechte Form, ein Team bereits abgestiegen${_rlSfx} — ungleiche Intensitäten, Frustrationsspiel, taktische Fouls erwartet.`
            : `6-Punkte-Kellerduell${_rlSfx} — Verzweiflung, taktische Fouls, emotionale Zweikämpfe. Historisch >4.5 Karten.`;
      } else if (cardsHigh) {
        cardSc  = Math.min(0.88, 0.66 + _cardPressBoost * 0.50 + _refCardMod);
        cardMkt = urgencyHigh ? 'Über 4.5 Karten' : 'Über 3.5 Karten';
        const _relVsElite = anyRed && !bothRed;
        cardReason = _relVsElite
          ? `Abstieg trifft Titelkampf${_rlSfx} — Relegations-Team spielt aggressiv, Elite-Team diktiert Tempo. Intensives Pressing auf beiden Seiten.`
          : _bothRedConf
            ? `Duell bestätigter Absteiger${_rlSfx} — Saison bereits entschieden, aber physisches Spiel und Frustration können Karten provozieren.`
            : _anyRedConf
              ? `Abstiegskampf trifft bestätigten Absteiger${_rlSfx} — ein Team kämpft noch, das andere spielt ohne Druck. Ungleiche Intensität kann Fouls und Frustration erzeugen.`
              : `Abstiegsduell${_rlSfx} — beide Teams unter maximalem Druck. Taktische Fouls und physisches Spiel erwartet.`;
      } else if (cardsMed) {
        cardSc  = Math.min(0.72, 0.40 + _cardPressBoost * 0.40 + _refCardMod);
        const _noRedMed = !anyRed;
        cardReason = _noRedMed
          ? `Beide Teams in schlechter Form — frustriertes Spiel mit erhöhtem Foulspiel erwartet.`
          : `Abstiegsdruck${_rlSfx} — mindestens ein Team kämpft um den Klassenerhalt. Physisches Spiel wahrscheinlich.`;
      } else if (_refAvg != null && _refAvg >= 5.0 && _anyNeedsWin) {
        // Even without red-zone teams: very card-heavy ref + pressure → still a pick
        cardSc  = Math.min(0.60, 0.35 + _pressureBoost * 0.30 + _refCardMod);
        cardMkt = 'Über 3.5 Karten';
        cardReason = `Druckspiel${_rlSfx} kombiniert mit kartenlastigem Schiedsrichter — erhöhte Karten-Wahrscheinlichkeit.`;
      }
      // Suppress card pick if referee is very lenient and situation isn't extreme
      if (cardSc > 0 && _refAvg != null && _refAvg < 2.5 && !cardsVeryHigh) cardSc = 0;
      // Confirmed-relegated teams play with reduced intensity → "Frustration" alone is not enough.
      // Rule: if ANY confirmed-relegated team is involved, require referee evidence (≥3.5 avg cards)
      // to justify a cards pick. Without ref data the base rate is unknown — suppress.
      // If BOTH teams are confirmed relegated (both motiv='none'), kill the pick entirely:
      // two teams rotating and coasting = no real desperation = fewer cards, not more.
      // 🔑 CONFIRMED RELEGATED SUPPRESSION (Fix Apr 2026, verfeinert Apr 2026)
      // Abgestiegene Teams haben keinen Abstiegsdruck mehr → Karten-Pick reduziert oder geblockt.
      // Logik: _refAvg == null → kein Cache-Eintrag für diesen Schiri (≠ "kein kartenlastiger Schiri").
      // Statt Null-Komplett-Suppression: Liga-Baserate (3.5) als konservativer Default.
      //   < 3.0 Karten/Spiel (leonischer Schiri) → ganz supprimieren
      //   3.0–4.5 Karten/Spiel (Durchschnitt + kein Ref-Datum) → stark reduzieren (×0.60)
      //   ≥ 4.5 Karten/Spiel (kartenlastiger Schiri) → nur leicht reduzieren (×0.85)
      if (cardSc > 0 && _bothRedConf) {
        cardSc = 0; // beide abgestiegen → kein Druck, kein Pick
      } else if (cardSc > 0 && _anyRedConf) {
        const _refForCards = _refAvg ?? 3.5; // null → konservativer Ligadurchschnitt
        if      (_refForCards < 3.0) cardSc = 0;          // leonischer Schiri → kein Pick
        else if (_refForCards < 4.5) cardSc *= 0.60;      // Durchschnitt/kein Datum → stark reduzieren
        // ≥ 4.5: kartenlastiger Schiri → kein Extra-Penalty (Standardreduzierung durch Ligadurchschnitt reicht)
      }
      const _cardOdds = cardMkt.includes('4.5') ? (o.cards_o45||null) : (o.cards_o35||null);
      // Max odds guard: cards > 3.20 means low card probability — not worth recommending.
      if (cardSc > 0 && _cardOdds != null && _cardOdds > 3.20) cardSc = 0;
      // FV-Gate for cards: suppress if bookie implied prob exceeds Poisson fair prob by > GATE.GOALS_REAL.
      // Uses same blended expected-cards formula as estimateCardsOdds() injection above.
      // SYNC:GATE — threshold === GATE_GOALS_REAL in check_picks_logic.py
      if (cardSc > 0 && _cardOdds != null) {
        const _lcbG = ({ENG:3.8,GER:3.6,ITA:3.5,ESP:3.4,FRA:3.6,AUT:3.7,
                        NED:3.5,POR:3.8,TUR:4.2,SCO:4.0,POL:3.6,SUI:3.4})[leagueKey] || 3.5;
        const _hCPg = match.homeCardProfile?.avgCards ?? null;
        const _aCPg = match.awayCardProfile?.avgCards  ?? null;
        const _tcSumG = (_hCPg !== null && _aCPg !== null) ? (_hCPg + _aCPg) : null;
        const _expCardsG = _refAvg !== null && _tcSumG !== null
          ? _refAvg * 0.60 + _tcSumG * 0.40
          : _refAvg !== null
            ? _refAvg
            : _tcSumG !== null
              ? _tcSumG + (bothNeedWin?0.3:_anyNeedsWin?0.15:0)
              : _lcbG + (bothRed?0.8:anyRed?0.4:0) + (bothNeedWin?0.5:_anyNeedsWin?0.25:0);
        const _cardThresh = cardMkt.includes('4.5') ? 4.5 : 3.5;
        const _fairCardP  = _poissonOver(_expCardsG, _cardThresh);
        if (_hasNegEdge(_fairCardP, _cardOdds, o._cardsOddsEst||false, GATE.GOALS_REAL, GATE.GOALS_REAL))
          cardSc = 0;
      }
      if (cardSc > 0) sC.push({sc: cardSc, p:{icon: cardMkt.includes('4.5') ? '🟥' : '🟨',
        market: cardMkt, odds: _cardOdds, oddsIsEst: o._cardsOddsEst||false,
        // Cap at 'medium' when no referee data — cardsVeryHigh alone (pure team labels)
        // is not enough to justify ★★★. Referee history is the single best predictor.
        conf: cardSc>0.65 && _refAvg != null ? 'high' : cardSc>0.45?'medium':'low',
        reason: cardReason}});
    }

    // ── Handicap — tiered AH level based on favorite strength ────────────────
    // When a team is a very heavy favorite, plain Heimsieg is underpriced (e.g. 1.20).
    // A higher AH level (-0.75 / -1.0) gives more meaningful odds with potential edge.
    //
    // AH level selection by de-vigged win probability:
    //   _bkrPH >= 0.78  →  AH -1.0  (needs 2+ goal margin; ~65-75% of wins)  est. odds ÷ 0.75
    //   _bkrPH >= 0.68  →  AH -0.75 (quarter ball: half on -0.5, half on -1.0) est. odds ÷ 0.875
    //   else            →  AH -0.5  (plain home win, no draw)
    //
    // Estimated AH odds = 1 / (_bkrPH × ahFactor). Shown as model estimate, not bookie.
    if (homeHandicap) {
      const _ahP    = _bkrPH ?? 0;
      const _ahFac  = _ahP >= 0.78 ? 0.75 : _ahP >= 0.68 ? 0.875 : 1.00;
      const _ahMkt  = _ahP >= 0.78 ? 'Handicap Heim -1.0'
                    : _ahP >= 0.68 ? 'Handicap Heim -0.75'
                    :                'Handicap Heim -0.5';
      // Estimated AH odds from de-vigged probability (clearly a model estimate)
      const _ahEstO = (_ahP > 0) ? +Math.max(1.12, 1 / (_ahP * _ahFac)).toFixed(2) : null;

      let hcSc = Math.min(0.84, 0.56 + hFS_home*0.30 + Math.max(0,hStreak)*0.04 + Math.max(0,((_hHWR??homeWinRate)-0.54)*0.60));
      // 🔑 PRESSURE: Heimteam muss gewinnen → Vollgas-Angriff → Handicap noch stärker
      if (homeNeedsWin) hcSc = Math.min(0.90, hcSc + _pressureBoost * 0.70);

      const _ahReasonLevel = _ahMkt.includes('-1.0')
        ? `Der Heimsieg ist mit ~${Math.round(_ahP*100)}% so klar eingepreist (@ ${odds?.hw?.toFixed(2)||'?'}), dass ein -1.0 Handicap besser quotiert ist. ${match.home} erzielt Ø ${hGoals.toFixed(1)} Heimtore/Spiel — Siege mit ≥2 Toren Vorsprung sind realistisch.`
        : _ahMkt.includes('-0.75')
        ? `${match.home} ist mit ~${Math.round(_ahP*100)}% Siegwahrscheinlichkeit klarer Favorit (Heimsieg @ ${odds?.hw?.toFixed(2)||'?'}). Das -0.75 Handicap bietet mehr Wert als der unterquotierte Heimsieg. Ø ${hGoals.toFixed(1)} Tore/Spiel bestätigen die Überlegenheit.`
        : `${match.home} gewinnt ${Math.round(hFS_home*100)}% seiner Heimspiele und erzielt dabei im Schnitt ${hGoals.toFixed(1)} Tore — ein klarer Heimsieg (Handicap -0.5) ist gut möglich.`;

      sC.push({sc: hcSc, p:{icon:'🏠', market: _ahMkt, odds: _ahEstO, oddsIsEst: !!_ahEstO,
        conf: hcSc>0.70?'high':'medium', reason: _ahReasonLevel}});

    } else if (awayHandicap) {
      const _ahP    = _bkrPA ?? 0;
      const _ahFac  = _ahP >= 0.72 ? 0.75 : _ahP >= 0.62 ? 0.875 : 1.00;
      const _ahMkt  = _ahP >= 0.72 ? 'Handicap Auswärts -1.0'
                    : _ahP >= 0.62 ? 'Handicap Auswärts -0.75'
                    :                'Handicap Auswärts -0.5';
      const _ahEstO = (_ahP > 0) ? +Math.max(1.12, 1 / (_ahP * _ahFac)).toFixed(2) : null;

      let hcSc = Math.min(0.78, 0.50 + aFS_away*0.30 + Math.max(0,aStreak)*0.04 + Math.max(0,((_aAWR??awayWinRate)-0.46)*0.60));
      // 🔑 PRESSURE: Auswärtsteam muss gewinnen → All-in auch auswärts
      if (awayNeedsWin) hcSc = Math.min(0.86, hcSc + _pressureBoost * 0.65);

      const _ahReasonAway = _ahMkt.includes('-1.0') || _ahMkt.includes('-0.75')
        ? `${match.away} ist mit ~${Math.round(_ahP*100)}% Siegwahrscheinlichkeit klarer Favorit (@ ${odds?.aw?.toFixed(2)||'?'}). Das ${_ahMkt.replace('Handicap Auswärts ','')} Handicap bietet mehr Wert. Ø ${aGoals.toFixed(1)} Tore/Spiel auswärts bestätigen die Klasse.`
        : `${match.away} gewinnt ${Math.round(aFS_away*100)}% seiner Auswärtsspiele und trifft dabei im Schnitt ${aGoals.toFixed(1)} Mal — ein klarer Auswärtssieg (Handicap -0.5) ist gut möglich.`;

      sC.push({sc: hcSc, p:{icon:'✈️', market: _ahMkt, odds: _ahEstO, oddsIsEst: !!_ahEstO,
        conf: hcSc>0.65?'high':'medium', reason: _ahReasonAway}});
    }

    // ── 1. HZ: Over 0.5 Tore ────────────────────────────────────────────────
    // Base threshold: expGoals > 3.4 (85% model prob, odds likely ≥ 1.30).
    // 🔑 PRESSURE EXCEPTION: when any team must win, they press hard from kickoff →
    //   lower threshold to 3.1 (still value range) because early goal probability spikes.
    { const _htThresh = _anyNeedsWin ? 3.1 : 3.4;
      const htSc = expGoals > 3.4 ? 0.85
                 : expGoals > _htThresh && _anyNeedsWin ? 0.74
                 : 0;
      if (htSc > 0) {
        const _htPN = _anyNeedsWin && expGoals <= 3.4
          ? `<br><strong>⚡ ${bothNeedWin ? 'Beide Teams' : homeNeedsWin ? _pHLabel : _pALabel}${_rlSfx} — presst von Minute 1, erhöht früh-Tor-Wahrscheinlichkeit deutlich.</strong>` : '';
        sC.push({sc: htSc, p:{icon:'⏱️', market:'1. HZ: Over 0.5 Tore', odds: o.ht_o05||null,
          conf: htSc > 0.78 ? 'high' : 'medium',
          reason:`${match.home} (Ø ${homeAttStr.toFixed(1)} Tore/Spiel) und ${match.away} (Ø ${awayAttStr.toFixed(1)}) spielen beide offensiv — ein Treffer schon in der ersten Halbzeit ist sehr wahrscheinlich.`}});
      }
    }

    // ── Heimteam trifft / Auswärtsteam trifft REMOVED ───────────────────────
    // Backtest: 92%/84% probability → implied market odds ~1.08/~1.19 → below minimum 1.30 threshold.
    // No value for punter even with high hit-rate. Omitted entirely.

    // 1HZ Beide Teams treffen — boosted when any team is under pressure
    { let btts1sc = (firstHalfOpen && expGoals > 3.2 && !_used.has('1. HZ: Over 0.5 Tore')) ? 0.54 : 0;
      // 🔑 PRESSURE: Druckteam presst → Gegner kontert → Tore auf beiden Seiten bereits in HZ1
      if (btts1sc > 0 && _anyNeedsWin) btts1sc = Math.min(0.70, btts1sc + _pressureBoost * 0.80);
      if (btts1sc > 0) {
        const _b1PN = _anyNeedsWin ? `<br><strong>⚡ ${bothNeedWin ? 'Beide Teams' : homeNeedsWin ? _pHLabel : _pALabel}${_rlSfx} — Pressingspiel von Beginn an erhöht frühe BTTS-Wahrscheinlichkeit.</strong>` : '';
        sC.push({sc: btts1sc, p:{icon:'⏱️', market:'1. HZ: Beide Teams treffen', odds:o.ht_bttsY||null, conf: btts1sc>0.50?'medium':'low',
          reason:`${match.home} (Ø ${homeAttStr.toFixed(1)} Tore/Spiel) und ${match.away} (Ø ${awayAttStr.toFixed(1)}) starten offensiv — beide Teams könnten schon in der ersten Halbzeit getroffen haben.`}});
      }
    }

    // 1HZ Under 1.5 (slow tight opener — suppressed when any team under pressure)
    { let u15sc = firstHalfTight ? 0.50 : 0;
      if (u15sc > 0 && _anyNeedsWin) u15sc = Math.max(0, u15sc - _pressureBoost * 1.10);
      if (u15sc > 0) sC.push({sc: u15sc, p:{icon:'⏱️', market:'1. HZ: Under 1.5 Tore', odds:o.ht_u15||null, conf:'medium',
        reason:`Vorsichtiger Spielbeginn erwartet — beide Teams tasten sich erst ab. Das Modell erwartet ${expGoals.toFixed(1)} Tore insgesamt: in der ersten Halbzeit ist maximal 1 Treffer wahrscheinlich.`}});
    }

    // DC fallback removed from PICK 3 — DC is already handled in PICK 1.
    // Having DC in both PICK 1 + PICK 3 creates contradictory picks (DC X2 + DC 1X same game).
    // If no PICK 3 specialty market qualifies, the card simply shows no third pick.

    // ── 1. HZ: Heimsieg / Auswärtssieg (+ AH -0.25 Substitution) ───────────
    // Primary window: odds 1.40–2.05 → straight HT result pick.
    // Substitution: odds 1.33–1.39 → too cheap; estimate HT AH -0.25 from de-vigged
    //   HT 1X2 probs (needs ht_hw + ht_dr + ht_aw). Formula:
    //   AH -0.25 fair = (1 − pD/2) / pH — full win on HT result, half loss on HT draw.
    //   Applied 4% margin (oddsIsEst: true). Range gate 1.35–2.00.
    // Scaled down ~55%/48% of FT confidence (HT results more volatile than FT).
    {
      // ── HT Home Win helper: build htHSc and push ─────────────────────────
      const _tryHtHome = (htOdds, isEstimated, mktLabel, oddsLabel) => {
        let htHSc = hFS_home * 0.55;
        if (homeNeedsWin) htHSc = Math.min(0.82, htHSc + _pressureBoost * 0.45);
        if (eloHomeFav)   htHSc = Math.min(0.82, htHSc + 0.07);
        if (homeAttStr > 1.4) htHSc = Math.min(0.82, htHSc + 0.05);
        if (htHSc < 0.38) return;
        const _reason = isEstimated
          ? `${match.home} ist klar favorisiert für HZ1 (1X2-Quote ${o.ht_hw.toFixed(2)} — kein Wert). AH -0.25 @ ~${oddsLabel} bietet bessere Rendite: volles Win bei HZ-Heimsieg, nur Halbverlust bei Unentschieden.`
          : `${match.home} dominiert ${Math.round(hFS_home*100)}% seiner Heimspiele und erzielt Ø ${homeAttStr.toFixed(1)} Tore/Spiel — ein Führungstreffer bereits in Halbzeit 1 ist realistisch. HZ-Quote ${oddsLabel} bietet Wert.`;
        sC.push({sc: htHSc, p:{icon:'⏱️', market: mktLabel, odds: htOdds, oddsIsEst: isEstimated,
          conf: htHSc > 0.65 ? 'high' : 'medium', reason: _reason}});
      };

      if (o.ht_hw != null && o.ht_hw >= 1.40 && o.ht_hw <= 2.05) {
        // Value range — straight HT Home Win
        _tryHtHome(o.ht_hw, false, '1. HZ: Heimsieg', o.ht_hw.toFixed(2));
      } else if (o.ht_hw != null && o.ht_hw >= 1.33 && o.ht_hw < 1.40
                 && o.ht_dr != null && o.ht_aw != null) {
        // Too cheap — substitute with estimated HT AH -0.25
        const _htTot = 1/o.ht_hw + 1/o.ht_dr + 1/o.ht_aw;
        const _htPH  = (1/o.ht_hw) / _htTot;
        const _htPD  = (1/o.ht_dr) / _htTot;
        const _htAHe = Math.round((1 - _htPD * 0.5) / _htPH * 0.96 * 100) / 100;
        if (_htAHe >= 1.35 && _htAHe <= 2.00)
          _tryHtHome(_htAHe, true, '1. HZ: AH Heim -0.25', `~${_htAHe.toFixed(2)}`);
      }

      // ── HT Away Win helper: build htASc and push ─────────────────────────
      const _tryHtAway = (htOdds, isEstimated, mktLabel, oddsLabel) => {
        let htASc = aFS_away * 0.48;
        if (awayNeedsWin) htASc = Math.min(0.78, htASc + _pressureBoost * 0.40);
        if (eloAwayFav)   htASc = Math.min(0.78, htASc + 0.07);
        if (awayAttStr > 1.4) htASc = Math.min(0.78, htASc + 0.05);
        if (htASc < 0.36) return;
        const _reason = isEstimated
          ? `${match.away} ist klar favorisiert für HZ1 (1X2-Quote ${o.ht_aw.toFixed(2)} — kein Wert). AH -0.25 @ ~${oddsLabel} bietet bessere Rendite: volles Win bei HZ-Auswärtssieg, nur Halbverlust bei Unentschieden.`
          : `${match.away} gewinnt ${Math.round(aFS_away*100)}% seiner Auswärtsspiele und trifft dabei Ø ${awayAttStr.toFixed(1)} Mal/Spiel — auch in Halbzeit 1 realistisch führend. HZ-Quote ${oddsLabel} bietet Wert.`;
        sC.push({sc: htASc, p:{icon:'⏱️', market: mktLabel, odds: htOdds, oddsIsEst: isEstimated,
          conf: htASc > 0.60 ? 'high' : 'medium', reason: _reason}});
      };

      if (o.ht_aw != null && o.ht_aw >= 1.40 && o.ht_aw <= 2.05) {
        // Value range — straight HT Away Win
        _tryHtAway(o.ht_aw, false, '1. HZ: Auswärtssieg', o.ht_aw.toFixed(2));
      } else if (o.ht_aw != null && o.ht_aw >= 1.33 && o.ht_aw < 1.40
                 && o.ht_dr != null && o.ht_hw != null) {
        // Too cheap — substitute with estimated HT AH -0.25
        const _htTot = 1/o.ht_hw + 1/o.ht_dr + 1/o.ht_aw;
        const _htPA  = (1/o.ht_aw) / _htTot;
        const _htPD  = (1/o.ht_dr) / _htTot;
        const _htAHe = Math.round((1 - _htPD * 0.5) / _htPA * 0.96 * 100) / 100;
        if (_htAHe >= 1.35 && _htAHe <= 2.00)
          _tryHtAway(_htAHe, true, '1. HZ: AH Ausw. -0.25', `~${_htAHe.toFixed(2)}`);
      }
    }

    sC.sort((a,b) => b.sc - a.sc);
    // Redundant pick guard: skip Handicap picks if PICK 1 already covers the same direction.
    // Both 'Handicap Heim *' (PICK 3 model-estimated) and the 'AH Heim *' (PICK 1 AH substitution)
    // represent the same underlying bet — showing both on one card confuses the user.
    { const _p1Mkt = picks.length > 0 ? picks[0].market : null;
      const _p1Home = ['Heimsieg','DNB: Heimteam','Doppelte Chance: 1X'].includes(_p1Mkt)
                    || (_p1Mkt?.startsWith('AH Heim'));   // AH substitution counts as home direction
      const _p1Away = ['Auswärtssieg','DNB: Auswärtsteam','Doppelte Chance: X2'].includes(_p1Mkt)
                    || (_p1Mkt?.startsWith('AH Ausw'));   // AH Ausw. substitution = away direction
      const _isHomeHC = m => m?.startsWith('Handicap Heim');
      const _isAwayHC = m => m?.startsWith('Handicap Auswärts');
      for (const c of sC) {
        if (_isHomeHC(c.p.market) && _p1Home) continue;
        if (_isAwayHC(c.p.market) && _p1Away) continue;
        if (_push(c.p, c.sc)) break;
      }
    }
  }
  // ── Value estimation ─────────────────────────────────────────────────────
  // Compare our model probability (derived from signals) vs Pinnacle implied prob.
  // Edge ≥ 10% → 🔥 hot value  |  Edge ≥ 5% → 💰 value  |  else → null
  // Only applies to picks with Pinnacle odds (hw/dr/aw/o25/u25/o35).
  // Specialty markets (BTTS, cards, corners, DC, 1st half) stay untagged — no odds to compare.
  picks.forEach(p => {
    // oddsIsEst = true means p.odds is a model estimate, not a real bookie price.
    // Comparing model vs. model would produce meaningless "edge" — skip value tag for those.
    const ip = (p.odds && !p.oddsIsEst) ? (1 / p.odds) * 1.03 : null;  // ×1.03 strips ~3% bookmaker margin
    let mp = null;           // our model probability estimate
    // Injury impact reduces expected corners (injured wingers/fullbacks mean less attacking width)
    const _cInjAdj = Math.max(0, ((_hImpact||0) + (_aImpact||0)) * 0.08);
    const cornersEstAdj = Math.max(4.0, cornersEst - _cInjAdj);
    switch (p.market) {
      case 'Heimsieg':
        if (_fairPH !== null) {
          // Market-anchored: blended fair prob (dynamic weight consensus + API pct) as base
          // + line movement nudge: steam toward home shifts mp up
          let _adj = homeNeedsWin ? _pressureBoost * 0.18 : 0;
          mp = Math.min(0.97, Math.max(0.02, _fairPH + Math.min(0.06, Math.max(-0.06, _adj)) + _lmH));
        } else {
          mp = Math.min(0.82, 0.34 + (hFS_home - 0.5) * 0.65 + Math.max(0, hStreak) * 0.03 + homeWinRate * 0.16);
          if (xGBased) mp = Math.min(0.82, mp + Math.max(0, homeAttStr - 1.2) * 0.08 - Math.max(0, awayAttStr - 1.4) * 0.06);
          if (eloHomeFav) mp = Math.min(0.82, mp + 0.04);
          if (homeNeedsWin) mp = Math.min(0.82, mp + _pressureBoost * 0.18);
        }
        break;
      case 'Auswärtssieg':
        if (_fairPA !== null) {
          let _adj = awayNeedsWin ? _pressureBoost * 0.18 : 0;
          mp = Math.min(0.97, Math.max(0.02, _fairPA + Math.min(0.06, Math.max(-0.06, _adj)) + _lmA));
        } else {
          mp = Math.min(0.76, 0.26 + (aFS_away - 0.5) * 0.65 + Math.max(0, aStreak) * 0.03 + awayWinRate * 0.16);
          if (xGBased) mp = Math.min(0.76, mp + Math.max(0, awayAttStr - 1.1) * 0.08 - Math.max(0, homeAttStr - 1.4) * 0.06);
          if (eloAwayFav) mp = Math.min(0.76, mp + 0.04);
          if (awayNeedsWin) mp = Math.min(0.76, mp + _pressureBoost * 0.18);
        }
        break;
      // ── DC / DNB: derived markets — computed from de-vigged 1X2 probs ─────────
      // DC/DNB fair value = sum of underlying outcome probabilities.
      // Using bookmaker's own 1X2 odds (most liquid, most efficient market) to de-vig
      // gives the most accurate fair price. Comparing THAT against the DC/DNB quote
      // reveals whether the bookmaker has priced those markets with extra margin.
      // If no 1X2 odds available, fall back to normalized 3-way model probs.
      case 'DNB: Heimteam':
      case 'DNB: Auswärtsteam':
      case 'Doppelte Chance: 1X':
      case 'Doppelte Chance: X2': {
        let _pH, _pD, _pA;
        if (o.hw && o.dr && o.aw) {
          // De-vig Pinnacle 1X2 odds → true probabilities
          const _tot = 1/o.hw + 1/o.dr + 1/o.aw;
          _pH = (1/o.hw) / _tot;
          _pD = (1/o.dr) / _tot;
          _pA = (1/o.aw) / _tot;
        } else {
          // No 1X2 odds — use normalized 3-way model estimate
          // IMPORTANT: caps are applied AFTER normalization so relative probabilities are correct
          const _mH = Math.max(0.01, 0.34+(hFS_home-0.5)*0.65+Math.max(0,hStreak)*0.03+homeWinRate*0.16+(xGBased?Math.max(0,homeAttStr-1.2)*0.08-Math.max(0,awayAttStr-1.4)*0.06:0)+(eloHomeFav?0.04:0)+(homeNeedsWin?_pressureBoost*0.18:0));
          const _mA = Math.max(0.01, 0.26+(aFS_away-0.5)*0.65+Math.max(0,aStreak)*0.03+awayWinRate*0.16+(xGBased?Math.max(0,awayAttStr-1.1)*0.08-Math.max(0,homeAttStr-1.4)*0.06:0)+(eloAwayFav?0.04:0)+(awayNeedsWin?_pressureBoost*0.18:0));
          const _mD = Math.max(0.05, drawRate*0.72+0.10-((homeNeedsWin||awayNeedsWin)?_pressureBoost*0.30:0));
          const _mTot = Math.max(0.01, _mH + _mA + _mD);
          _pH = Math.min(0.82, _mH/_mTot); _pA = Math.min(0.76, _mA/_mTot); _pD = Math.min(0.40, _mD/_mTot);
        }
        if      (p.market === 'Doppelte Chance: 1X') mp = Math.min(0.97, _pH + _pD);
        else if (p.market === 'Doppelte Chance: X2') mp = Math.min(0.97, _pA + _pD);
        else if (p.market === 'DNB: Heimteam')       mp = Math.min(0.95, _pH / (_pH + _pA));
        else if (p.market === 'DNB: Auswärtsteam')   mp = Math.min(0.95, _pA / (_pH + _pA));
        break;
      }
      case 'Unentschieden':
        if (_fairPD !== null) {
          let _adj = (homeNeedsWin || awayNeedsWin) ? -Math.min(0.10, _pressureBoost * 0.30) : 0;
          mp = Math.max(0.03, Math.min(0.65, _fairPD + _adj + _lmD));
        } else {
          mp = Math.min(0.40, drawRate * 0.72 + 0.10);
          if (homeNeedsWin || awayNeedsWin) mp = Math.max(0.05, mp - _pressureBoost * 0.30);
        }
        break;
      case 'Over 2.5 Tore':
        mp = expGoals > 3.2 ? 0.72 + _lgCap : expGoals > 2.8 ? 0.60 + _lgCap : expGoals > 2.4 ? 0.48 + _lgCap * 0.7 : 0.36 + _lgCap * 0.5;
        mp = Math.min(0.92, Math.max(0.12, mp));  // hard floor/ceiling after league adjustment
        if (bothNeedWin)       mp = Math.min(0.88 + _lgCap, mp + _pressureBoost * 0.55);
        else if (_anyNeedsWin) mp = Math.min(0.82 + _lgCap, mp + _pressureBoost * 0.30);
        // H2H goals history: both rate (over25Rate) and average (avgGoals) as signals
        if (_h2hSample && _h2hOver25 != null) mp = Math.min(0.92, mp + _h2hO25Mod * 0.7);
        if (_h2hSample && _h2hAvgG   != null) mp = Math.min(0.92, mp + _h2hAvgGMod * 0.7); // was missing from FV
        // API prediction consensus: independent model agrees → small FV boost
        if (_apiUO === 'Over 2.5')  mp = Math.min(0.92, mp + 0.05); // was missing from FV
        else if (_apiUO === 'Under 2.5') mp = Math.max(0.12, mp - 0.04);
        // Line movement nudge: steam toward Over = money coming in on goals → boost mp
        mp = Math.min(0.92, Math.max(0.12, mp + _lmO));
        // Market anchor: Pinnacle O2.5/U2.5 already prices in relegation pressure.
        // Allow at most +10pp above de-vigged market probability to prevent double-counting.
        if (o.o25 && o.u25) { const _mktO = (1/o.o25)/((1/o.o25)+(1/o.u25)); mp = Math.min(_mktO + 0.10, mp); }
        break;
      case 'Under 2.5 Tore':
        mp = expGoals < 1.8 ? 0.72 - _lgCap : expGoals < 2.2 ? 0.60 - _lgCap : expGoals < 2.6 ? 0.49 - _lgCap * 0.7 : 0.37 - _lgCap * 0.5;
        mp = Math.min(0.92, Math.max(0.08, mp));  // hard floor/ceiling after league adjustment
        if (bothNeedWin)       mp = Math.max(0.10 - _lgCap, mp - _pressureBoost * 0.55);
        else if (_anyNeedsWin) mp = Math.max(0.15 - _lgCap, mp - _pressureBoost * 0.30);
        if (_h2hSample && _h2hOver25 != null) mp = Math.min(0.92, Math.max(0.05, mp - _h2hO25Mod * 0.7));
        if (_h2hSample && _h2hAvgG   != null) mp = Math.min(0.92, Math.max(0.05, mp - _h2hAvgGMod * 0.7)); // was missing from FV
        if (_apiUO === 'Under 2.5') mp = Math.min(0.92, mp + 0.05);  // was missing from FV
        else if (_apiUO === 'Over 2.5') mp = Math.max(0.08, mp - 0.04);
        // Line movement nudge: steam toward Under = money on fewer goals → boost mp
        mp = Math.min(0.92, Math.max(0.08, mp + _lmU));
        // Market anchor: cap Under mp at de-vigged market Under prob + 10pp
        if (o.o25 && o.u25) { const _mktU = (1/o.u25)/((1/o.o25)+(1/o.u25)); mp = Math.min(_mktU + 0.10, mp); }
        break;
      case 'Over 3.5 Tore':
        mp = expGoals > 3.6 ? 0.60 + _lgCap : expGoals > 3.1 ? 0.42 + _lgCap * 0.8 : expGoals > 2.7 ? 0.28 + _lgCap * 0.5 : 0.18 + _lgCap * 0.3;
        mp = Math.min(0.88, Math.max(0.05, mp));
        if (bothNeedWin)       mp = Math.min(0.78 + _lgCap, mp + _pressureBoost * 0.50);
        else if (_anyNeedsWin) mp = Math.min(0.70 + _lgCap, mp + _pressureBoost * 0.28);
        // H2H modifiers at ×0.35 (half weight vs O2.5 — same direction, less precision at 3.5 line)
        if (_h2hSample && _h2hOver25 != null) mp = Math.min(0.88, mp + _h2hO25Mod * 0.35);
        if (_h2hSample && _h2hAvgG   != null) mp = Math.min(0.88, mp + _h2hAvgGMod * 0.35);
        // API prediction: halved vs O2.5 signal (API model targets 2.5 line, less precise for 3.5)
        if (_apiUO === 'Over 2.5')  mp = Math.min(0.88, mp + 0.025);
        else if (_apiUO === 'Under 2.5') mp = Math.max(0.05, mp - 0.020);
        // Line movement — same direction as O/U 2.5
        mp = Math.min(0.88, Math.max(0.05, mp + _lmO));
        // Market anchor: use real O3.5 odds if available, otherwise derive from O2.5 (less accurate)
        if (o.o35) { const _mktO35 = 1 / o.o35 / (1/o.o35 + (o.u35 ? 1/o.u35 : (1 - 1/o.o35))); mp = Math.min(_mktO35 + 0.12, mp); }
        else if (o.o25 && o.u25) { const _mktO35 = (1/o.o25)/((1/o.o25)+(1/o.u25)) * 0.55; mp = Math.min(_mktO35 + 0.12, mp); }
        break;
      case 'Beide Teams treffen':
        // BTTS Yes: Poisson P(home ≥ 1) × P(away ≥ 1) — independent events
        { const _pH1 = Math.max(0.05, 1 - Math.exp(-homeAttStr));  // P(home scores ≥ 1)
          const _pA1 = Math.max(0.05, 1 - Math.exp(-awayAttStr));  // P(away scores ≥ 1)
          let _bttsMp = Math.min(0.86, Math.max(0.14, _pH1 * _pA1));
          // Pressure: both need to win → both attack → BTTS more likely
          if (bothNeedWin)       _bttsMp = Math.min(0.86, _bttsMp + _pressureBoost * 0.45);
          else if (_anyNeedsWin) _bttsMp = Math.min(0.82, _bttsMp + _pressureBoost * 0.22);
          // H2H history
          if (_h2hSample && _h2hBtts != null) _bttsMp = Math.min(0.86, _bttsMp + _h2hBttsMod * 0.7);
          // Clean sheet / failed-to-score: high home CS rate or high away FTS rate suppresses BTTS
          if (_hCSHome !== null && _hCSHome >= 0.35) _bttsMp = Math.max(0.12, _bttsMp - 0.06);
          if (_aFTSAway !== null && _aFTSAway >= 0.35) _bttsMp = Math.max(0.12, _bttsMp - 0.06);
          mp = _bttsMp;
        } break;
      case 'Beide Teams treffen: Nein':
        { const _pH0 = Math.max(0.05, Math.exp(-homeAttStr));  // P(home scores 0)
          const _pA0 = Math.max(0.05, Math.exp(-awayAttStr));  // P(away scores 0)
          // P(BTTS No) = 1 - P(both score): cleaner than lookup table
          let _bttsNMp = Math.min(0.82, Math.max(0.08, 1 - (1-_pH0)*(1-_pA0)));
          if (bothNeedWin)       _bttsNMp = Math.max(0.08, _bttsNMp - _pressureBoost * 0.45);
          else if (_anyNeedsWin) _bttsNMp = Math.max(0.10, _bttsNMp - _pressureBoost * 0.22);
          if (_h2hSample && _h2hBtts != null) _bttsNMp = Math.min(0.82, _bttsNMp - _h2hBttsMod * 0.7);
          if (_hCSHome !== null && _hCSHome >= 0.35) _bttsNMp = Math.min(0.82, _bttsNMp + 0.05);
          if (_aFTSAway !== null && _aFTSAway >= 0.35) _bttsNMp = Math.min(0.82, _bttsNMp + 0.05);
          mp = _bttsNMp;
        } break;
      // ── Cards — Poisson-derived fair probability from estimateCardsOdds() ────────
      // estimateCardsOdds returns odds with 7% margin: o.cards_o35 = 0.93/P(cards>3.5)
      // → P(cards>3.5) = 0.93/o.cards_o35  (strips the built-in margin back out)
      case 'Über 3.5 Karten':
        if (o.cards_o35) mp = Math.min(0.93, Math.max(0.04, 0.93 / o.cards_o35));
        break;
      case 'Über 4.5 Karten':
        if (o.cards_o45) mp = Math.min(0.90, Math.max(0.02, 0.93 / o.cards_o45));
        break;
      // ── Corners — model probability from expected corner estimate (injury-adjusted) ──
      case 'Über 11.5 Ecken': mp = Math.min(0.88, Math.max(0.08, 0.35 + (cornersEstAdj - 11.5) * 0.12)); break;
      case 'Über 10.5 Ecken': mp = Math.min(0.88, Math.max(0.10, 0.40 + (cornersEstAdj - 10.5) * 0.12)); break;
      case 'Über 9.5 Ecken':  mp = Math.min(0.88, Math.max(0.12, 0.50 + (cornersEstAdj - 9.5)  * 0.10)); break;
      case 'Über 8.5 Ecken':  mp = Math.min(0.88, Math.max(0.14, 0.60 + (cornersEstAdj - 8.5)  * 0.10)); break;
      case 'Unter 9.5 Ecken': mp = Math.min(0.85, Math.max(0.08, 0.50 + (9.5 - cornersEstAdj)  * 0.10)); break;
      case 'Unter 8.5 Ecken': mp = Math.min(0.85, Math.max(0.08, 0.55 + (8.5 - cornersEstAdj)  * 0.12)); break;
    }
    // ── Asian Handicap FV — win-margin probability instead of raw 1X2 ────────────
    // Raw win probability (e.g. 0.88 for Man City) is WRONG for AH -2.25:
    // what matters is P(win by 3+ goals). Win-margin factor converts 1X2 prob → AH coverage prob.
    // Factors empirically derived: AH -2.25 ≈ 44% of straight-win prob, AH -1.5 ≈ 64%, etc.
    if (mp === null && p.market && (p.market.startsWith('AH ') || p.market.startsWith('Handicap '))) {
      const _ahM  = p.market.match(/[-\u2212](\d+\.?\d*)/);
      const _ahPt = _ahM ? parseFloat(_ahM[1]) : 1.0;
      const _isH  = p.market.toLowerCase().includes('heim');
      const _ahBP = (_isH ? (_bkrPH ?? 0) : (_bkrPA ?? 0));
      const _mf   = _ahPt >= 3.0  ? 0.27 : _ahPt >= 2.75 ? 0.32 : _ahPt >= 2.5  ? 0.37
                  : _ahPt >= 2.25 ? 0.44 : _ahPt >= 2.0  ? 0.51 : _ahPt >= 1.75 ? 0.58
                  : _ahPt >= 1.5  ? 0.64 : _ahPt >= 1.25 ? 0.72 : _ahPt >= 1.0  ? 0.80
                  : _ahPt >= 0.75 ? 0.87 : _ahPt >= 0.5  ? 0.93 : 0.97;
      // Strong-favourite boost: teams with >80% win prob win by larger margins more often
      // than the flat factor assumes. Calibrated: >85% → ×1.35, >80% → ×1.20.
      const _mfBoost = _ahBP > 0.85 ? 1.35 : _ahBP > 0.80 ? 1.20 : 1.0;
      const _mfAdj   = Math.min(0.97, _mf * _mfBoost);
      if (_ahBP > 0.05) mp = Math.min(0.90, Math.max(0.05, _ahBP * _mfAdj));
    }
    // For markets with a proper mp, compute model odds + edge
    if (mp !== null) {
      p.modelOdds = Math.round((1 / mp) * 100) / 100;
      if (ip !== null) {
        const edge = mp - ip;
        p.value = edge >= 0.10 ? 'hot' : edge >= 0.05 ? 'value' : null;
        // Injury edge amplifier: when injury impact is high AND market is affected,
        // our model captures it more precisely than the bookmaker → lower edge threshold
        const _hImpactHigh = _hImpact >= 2.0;
        const _aImpactHigh = _aImpact >= 2.0;
        const _injAffectsGoals = ['Over 2.5 Tore','Under 2.5 Tore','Beide Teams treffen','Beide Teams treffen: Nein'].includes(p.market);
        const _injAffectsResult = ['Heimsieg','Auswärtssieg','DNB: Heimteam','DNB: Auswärtsteam'].includes(p.market);
        if (p.value === null && (_hImpactHigh || _aImpactHigh)) {
          // Injury-adjusted: lower threshold to 0.05 for affected markets
          if ((_injAffectsGoals || _injAffectsResult) && edge >= 0.05) {
            p.value = 'inj-edge';  // special: injury-created edge
          }
        }
      } else {
        p.value = null;
      }
    } else {
      p.value = null;
      // Specialty markets (corners, cards, HZ, team-over-1.5, handicap): sc-based model odds
      // sc is a raw signal score, not a calibrated prob. Scaling factor 0.86 converts it
      // to a plausible probability range: sc=0.85→p≈0.73, sc=0.65→p≈0.56, sc=0.45→p≈0.39
      if (p.sc != null) {
        const scProb = Math.min(0.88, Math.max(0.12, p.sc < 1 ? p.sc * 0.86 : 0.88));
        p.modelOdds = Math.round((1 / scProb) * 100) / 100;
      }
    }
  });

  // Note: picks are NOT filtered by negative edge here.
  // The Fair Value comparison on each pick card is informational — the pick itself
  // is driven by pressure, form, H2H and the scoring system. A pick can be valid
  // even if the bookie has a slightly tighter price than our model (FV > bookie).
  // The Value/Hot tags already communicate when we have genuine positive edge.

  // ── Mod-chips: compact context badges attached to each pick ─────────────────
  // Injury, fatigue, pressure, H2H goals, ref info shown as scannable chips
  // instead of long appended text — keeps reason text concise.
  picks.forEach(p => {
    const hHome = ['Heimsieg','DNB: Heimteam','Doppelte Chance: 1X'].includes(p.market) || p.market.startsWith('Handicap Heim');
    const hAway = ['Auswärtssieg','DNB: Auswärtsteam','Doppelte Chance: X2'].includes(p.market) || p.market.startsWith('Handicap Auswärts');
    const hGoal = ['Over 2.5 Tore','Over 3.5 Tore','Under 2.5 Tore','Beide Teams treffen','Beide Teams treffen: Nein'].includes(p.market);
    const hCard = p.market.includes('Karten');
    const chips = [];
    // Pressure chip intentionally omitted here — shown once in the event's pressure-strip banner above.
    // Injury chips (relevant markets)
    if ((hHome || hGoal) && _hImpact >= 0.5) {
      const _hInjIcon = _hImpact >= 3.5 ? '🔴' : _hImpact >= 2.0 ? '🟠' : '🟡';
      const _hAreas = [];
      if ((_hInj?.goalkeeper||0)>0) _hAreas.push(`TW${_hInj.goalkeeper}`);
      if ((_hInj?.attack||0)>0)     _hAreas.push(`Ang${_hInj.attack}`);
      if ((_hInj?.defense||0)>0)    _hAreas.push(`Abw${_hInj.defense}`);
      if ((_hInj?.midfield||0)>0)   _hAreas.push(`MF${_hInj.midfield}`);
      chips.push(`<span class="mod-chip mod-inj">${_hInjIcon} ${match.home} ${_hImpact.toFixed(1)}${_hAreas.length?' ('+_hAreas.join('/')+')':''}</span>`);
    }
    if ((hAway || hGoal) && _aImpact >= 0.5) {
      const _aInjIcon = _aImpact >= 3.5 ? '🔴' : _aImpact >= 2.0 ? '🟠' : '🟡';
      const _aAreas = [];
      if ((_aInj?.goalkeeper||0)>0) _aAreas.push(`TW${_aInj.goalkeeper}`);
      if ((_aInj?.attack||0)>0)     _aAreas.push(`Ang${_aInj.attack}`);
      if ((_aInj?.defense||0)>0)    _aAreas.push(`Abw${_aInj.defense}`);
      if ((_aInj?.midfield||0)>0)   _aAreas.push(`MF${_aInj.midfield}`);
      chips.push(`<span class="mod-chip mod-inj">${_aInjIcon} ${match.away} ${_aImpact.toFixed(1)}${_aAreas.length?' ('+_aAreas.join('/')+')':''}</span>`);
    }
    // xG impact summary for goals markets
    if (hGoal && (_hImpact >= 1.0 || _aImpact >= 1.0)) {
      const _xgParts = [];
      if (Math.round((1-_hInjAtt)*100) >= 8) _xgParts.push(`${match.home} -${Math.round((1-_hInjAtt)*100)}% xG`);
      if (Math.round((1-_aInjAtt)*100) >= 8) _xgParts.push(`${match.away} -${Math.round((1-_aInjAtt)*100)}% xG`);
      if (Math.round((_hInjDef-1)*100) >= 6) _xgParts.push(`${match.home} +${Math.round((_hInjDef-1)*100)}% xGA`);
      if (Math.round((_aInjDef-1)*100) >= 6) _xgParts.push(`${match.away} +${Math.round((_aInjDef-1)*100)}% xGA`);
      if (_xgParts.length) chips.push(`<span class="mod-chip" style="background:#0d1a2d;color:#79c0ff;border:1px solid #1d4e7a">📉 ${_xgParts.join(' · ')}</span>`);
    }
    // Fatigue chips
    if ((hHome || hGoal) && _hFatigAtt < 1.0)
      chips.push(`<span class="mod-chip mod-fat">😴 ${match.home} ${_hRest}T Pause (-${Math.round((1-_hFatigAtt)*100)}% xG)</span>`);
    if ((hAway || hGoal) && _aFatigAtt < 1.0)
      chips.push(`<span class="mod-chip mod-fat">😴 ${match.away} ${_aRest}T Pause (-${Math.round((1-_aFatigAtt)*100)}% xG)</span>`);
    // Ref chip for card picks
    if (hCard && _refAvg != null)
      chips.push(`<span class="mod-chip mod-ref">👨‍⚖️ ${(_refStats?.name||'SR').split(' ').slice(-1)[0]}: Ø ${_refAvg} K/Sp</span>`);
    // xG fairness chip (regression warning)
    if ((hHome || hAway) && (_hFair != null || _aFair != null)) {
      if (_hFair > 1.12 && hHome) chips.push(`<span class="mod-chip mod-neutral">⚠️ ${match.home} überperformt xG (${Math.round(_hFair*100)}%)</span>`);
      if (_aFair > 1.12 && hAway) chips.push(`<span class="mod-chip mod-neutral">⚠️ ${match.away} überperformt xG (${Math.round(_aFair*100)}%)</span>`);
    }
    // Motivation chips — shown when a team's season fate is already confirmed
    // Signals to bettor: expect rotation, reduced effort, underperformance vs. xG baseline
    if (hMotivNone && (hHome || hGoal))
      chips.push(`<span class="mod-chip" style="background:#1a1a1a;color:#aaa;border:1px solid #444">⬜ ${match.home} ${hc.includes('red') ? 'abgestiegen' : 'gesichert'} (-18% xG)</span>`);
    else if (hMotivLow && (hHome || hGoal))
      chips.push(`<span class="mod-chip" style="background:#1a1a1a;color:#aaa;border:1px solid #444">⬜ ${match.home} ${hc.includes('red') ? 'Abstieg quasi sicher' : 'nahezu gesichert'} (-8% xG)</span>`);
    if (aMotivNone && (hAway || hGoal))
      chips.push(`<span class="mod-chip" style="background:#1a1a1a;color:#aaa;border:1px solid #444">⬜ ${match.away} ${ac.includes('red') ? 'abgestiegen' : 'gesichert'} (-18% xG)</span>`);
    else if (aMotivLow && (hAway || hGoal))
      chips.push(`<span class="mod-chip" style="background:#1a1a1a;color:#aaa;border:1px solid #444">⬜ ${match.away} ${ac.includes('red') ? 'Abstieg quasi sicher' : 'nahezu gesichert'} (-8% xG)</span>`);
    p.mods = chips;
  });

  // ── Safer Alternative / Bold Alternative computation ────────────────────────
  // For picks with odds > 2.0: compute one step DOWN (safer line, ~1.7–2.0 range).
  //   → saferAlt becomes the PRIMARY recommended bet on the card.
  //   → original high-odds pick becomes the "Value Alternative".
  // For picks with odds 1.4–2.0: optionally compute one step UP (bolder version).
  //   → boldAlt is shown as secondary "Mehr Value" suggestion.
  // All estimated odds are model-derived (no extra API call needed).
  const _r2 = x => Math.round(x * 100) / 100;

  // ── Odds step helper: anchors on bookie ip + empirical line step ─────────────
  // More reliable than pure model formula (avoids ceiling artefacts).
  // ip = implied prob of the current pick (stripped of ~3% margin).
  // stepUp = additional probability gained by dropping one line (empirical calibration).
  // Returns model-estimated odds for the safer/bolder alternative, or null if out of range.
  const _stepOdds = (baseOdds, stepUp, minO, maxO) => {
    const ip = baseOdds ? (1 / baseOdds) * 1.03 : null;
    if (!ip) return null;
    const newProb = Math.min(0.87, ip + stepUp);
    const est = Math.round((1 / newProb) * 100) / 100;
    return (est >= minO && est <= maxO) ? est : null;
  };
  const _stepOddsDown = (baseOdds, stepUp, minO = 1.30, maxO = 2.60) =>
    _stepOdds(baseOdds, stepUp, minO, maxO);
  const _stepOddsUp = (baseOdds, stepDown, minO = 1.80, maxO = 6.50) => {
    const ip = baseOdds ? (1 / baseOdds) * 1.03 : null;
    if (!ip) return null;
    const newProb = Math.max(0.13, ip - stepDown);
    const est = Math.round((1 / newProb) * 100) / 100;
    return (est >= minO && est <= maxO) ? est : null;
  };

  picks.forEach(p => {
    const o = p.odds;
    // ── Step-DOWN (safer): for risky odds > 2.0 ─────────────────────────
    if (o && o > 2.00) {
      switch (p.market) {
        case 'Heimsieg': {
          // Use blended prob if available, else fall back to bookie odds directly
          const _pH = _bkrPH || (o ? (1/o) * 1.03 : null);
          const _pD = _bkrPD || null;
          if (_pH && _pD) {
            const dnb = (_pH + _pD) / _pH;
            const raw = 1 / _pH;
            const ah  = _r2((dnb + raw) / 2);
            if (ah >= 1.35 && ah <= 2.90) p.saferAlt = { market: 'AH -0.25 Heim', estOdds: ah };
          } else if (_pH) {
            // No draw prob — approximate AH via DNB only
            const dnbOnly = _r2(1 / _pH);
            if (dnbOnly >= 1.35 && dnbOnly <= 2.90) p.saferAlt = { market: 'DNB: Heimteam', estOdds: dnbOnly };
          }
          break;
        }
        case 'Auswärtssieg': {
          const _pA = _bkrPA || (o ? (1/o) * 1.03 : null);
          const _pD = _bkrPD || null;
          if (_pA && _pD) {
            const dnb = (_pA + _pD) / _pA;
            const raw = 1 / _pA;
            const ah  = _r2((dnb + raw) / 2);
            if (ah >= 1.35 && ah <= 2.90) p.saferAlt = { market: 'AH -0.25 Auswärts', estOdds: ah };
          } else if (_pA) {
            const dnbOnly = _r2(1 / _pA);
            if (dnbOnly >= 1.35 && dnbOnly <= 2.90) p.saferAlt = { market: 'DNB: Auswärtsteam', estOdds: dnbOnly };
          }
          break;
        }
        // Corners: +22pp probability per 2-line step (empirically calibrated)
        case 'Über 11.5 Ecken': {
          const est = _stepOddsDown(o, 0.22);
          if (est) p.saferAlt = { market: 'Über 9.5 Ecken', estOdds: est };
          break;
        }
        case 'Über 9.5 Ecken': {
          const est = _stepOddsDown(o, 0.22);
          if (est) p.saferAlt = { market: 'Über 7.5 Ecken', estOdds: est };
          break;
        }
        case 'Über 8.5 Ecken': {
          const est = _stepOddsDown(o, 0.20);
          if (est) p.saferAlt = { market: 'Über 7.5 Ecken', estOdds: est };
          break;
        }
        // Goals: +20pp per 1-goal step
        case 'Over 3.5 Tore': {
          const est = _stepOddsDown(o, 0.20);
          if (est) p.saferAlt = { market: 'Over 2.5 Tore', estOdds: est };
          break;
        }
        case 'Over 2.5 Tore': {
          const est = _stepOddsDown(o, 0.22, 1.20, 2.20);
          if (est) p.saferAlt = { market: 'Over 1.5 Tore', estOdds: est };
          break;
        }
        case 'Beide Teams treffen': {
          const est = _stepOddsDown(o, 0.22, 1.20, 2.00);
          if (est) p.saferAlt = { market: 'Over 1.5 Tore', estOdds: est };
          break;
        }
        // Cards: +17pp per 1-card step
        case 'Über 5.5 Karten': {
          const est = _stepOddsDown(o, 0.17);
          if (est) p.saferAlt = { market: 'Über 4.5 Karten', estOdds: est };
          break;
        }
        case 'Über 4.5 Karten': {
          const est = _stepOddsDown(o, 0.17);
          if (est) p.saferAlt = { market: 'Über 3.5 Karten', estOdds: est };
          break;
        }
        case 'Über 3.5 Karten': {
          const est = _stepOddsDown(o, 0.17, 1.20, 2.00);
          if (est) p.saferAlt = { market: 'Über 2.5 Karten', estOdds: est };
          break;
        }
      }
    }
    // ── Step-UP (bold): for safer odds 1.40–2.00 show a bolder option ────
    else if (o && o >= 1.40 && o <= 2.00) {
      switch (p.market) {
        case 'Über 9.5 Ecken': {
          const est = _stepOddsUp(o, 0.22);
          if (est) p.boldAlt = { market: 'Über 11.5 Ecken', estOdds: est };
          break;
        }
        case 'Over 2.5 Tore': {
          const est = _stepOddsUp(o, 0.20);
          if (est) p.boldAlt = { market: 'Over 3.5 Tore', estOdds: est };
          break;
        }
        case 'Over 1.5 Tore': {
          const est = _stepOddsUp(o, 0.22, 1.70, 4.50);
          if (est) p.boldAlt = { market: 'Over 2.5 Tore', estOdds: est };
          break;
        }
        case 'Über 4.5 Karten': {
          const est = _stepOddsUp(o, 0.17);
          if (est) p.boldAlt = { market: 'Über 5.5 Karten', estOdds: est };
          break;
        }
        case 'Über 3.5 Karten': {
          const est = _stepOddsUp(o, 0.17, 1.80, 5.00);
          if (est) p.boldAlt = { market: 'Über 4.5 Karten', estOdds: est };
          break;
        }
      }
    }
  });

  // ── Odds cap: hide picks outside the value range ─────────────────────────────
  // Upper cap 2.05: high-odds picks introduce unnecessary variance.
  // Lower cap 1.33: too-cheap picks (huge favorites) offer no value — the tiny return
  // doesn't justify the risk. Picks with real odds < 1.33 are demoted to 'low' globally.
  // Exception: null odds (no market data yet) and estimated (~) odds are left alone —
  // those can't be judged by the same standard.
  for (const p of picks) {
    if (p.odds != null && !p.oddsIsEst && p.odds > 2.05) p.conf = 'low';
    if (p.odds != null && !p.oddsIsEst && p.odds < 1.33) p.conf = 'low';
  }

  // ── Both-teams-low-motivation cap ─────────────────────────────────────────
  // When neither side has a meaningful stake in the result, picks should never
  // reach medium/high confidence — a garbage-time match offers no predictive edge.
  // Exception: cards markets are allowed to stay at their computed level because
  // low-motivation late-season matches often still produce cards from cynical play.
  if (hMotivLow && aMotivLow) {
    for (const p of picks) {
      if (p.conf === 'medium' || p.conf === 'high') {
        if (!p.market?.toLowerCase().includes('karte')) p.conf = 'low';
      }
    }
  }

  return picks;
}

// ═══════════════════════════════════════════════════════
//  PRECISION SCORE ENGINE
//  Replaces coarse integer scores with continuous 1–12 scale
//  that differentiates matches much more granularly,
//  with optional market-validation bonus from live odds.
// ═══════════════════════════════════════════════════════

function parseGermanDate(str) {
  const [d, m, y] = (str||'').split('.');
  return new Date(+y, +m - 1, +d);
}

// Returns days of rest a team had before matchDate, based on their previous fixture in allFixtures.
// null = no previous fixture found in our data (e.g. first game of tracked window).
function getRestDays(teamName, matchDate, allFixtures) {
  if (!allFixtures || !allFixtures.length || !matchDate) return null;
  const matchDt = parseGermanDate(matchDate);
  const prev = allFixtures
    .filter(f => f.home === teamName || f.away === teamName)
    .map(f => parseGermanDate(f.date))
    .filter(d => d.getTime() < matchDt.getTime());
  if (!prev.length) return null;
  prev.sort((a, b) => b - a);
  return Math.round((matchDt.getTime() - prev[0].getTime()) / 864e5);
}
