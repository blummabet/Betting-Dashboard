// ═══════════════════════════════════════════════════════
//  pick-verdict.js — Shared 3-Signal Verdict Engine
//  BET / ABWÄGEN / SKIP
//
//  Single source of truth consumed by:
//    · renderer.js        (pick cards in fixture view)
//    · polymarket-tab.js  (Polymarket betting tab)
//
//  Exported global: computeVerdict(pick) → data object
// ═══════════════════════════════════════════════════════

/**
 * computeVerdict(pick)
 *
 * Computes the 3-signal BET / ABWÄGEN / SKIP verdict for a single pick.
 *
 * Required pick fields:
 *   .modelOdds   — calibrated model price (null → Signal 1 skipped)
 *   .odds        — effective bookie odds to compare against;
 *                  pass null when no real market odds are available
 *                  (e.g. estimated-odds leagues without a bookie feed)
 *   .oddsIsEst   — true when odds are model estimates (suppresses Signal 2)
 *   .market      — market label string (German)
 *   .oddsOpen    — opening odds snapshot object { hw, aw, dr, o25, u25, bttsY, … }
 *                  or null when not available
 *   .h2h         — { games, homeWins, draws, awayWins, avgGoals, over25Rate, bttsRate }
 *                  or null when not available
 *
 * Returns:
 *   {
 *     modSig, modEmoji, modTxt,       // Signal 1 – Model Edge
 *     mktSig, mktEmoji, mktTxt,       // Signal 2 – Line Movement
 *     storySig, storyEmoji, storyTxt, // Signal 3 – H2H Story
 *     verdict,                        // 'BET' | 'ABWÄGEN' | 'SKIP'
 *     vColor, vBg, vBorder            // CSS badge colours
 *   }
 */
function computeVerdict(pick) {
  const oddsNum = pick.odds; // caller resolves oddsIsEst → modelOdds before passing

  // ── Signal 1: Model Edge ──────────────────────────────────────────────────
  // Positive edge (pp) = model thinks outcome is MORE likely than bookie implies.
  // ≥7pp → green (BET signal); 0–6pp → yellow (neutral); <0pp → orange/red (fade).
  let modSig = 0, modEmoji = '⬜', modTxt = '—';
  if (pick.modelOdds != null && oddsNum != null) {
    const _ep = Math.round((1 / pick.modelOdds - (1 / oddsNum) / 1.05) * 100);   // 31.07.2026 Lucas-Audit: Devig teilt (Ueberrunde ~1.05), vorher *1.03 = falschrum (wie schon im Steam-Pfad korrigiert)
    if      (_ep >= 7)  { modSig =  1; modEmoji = '🟢'; modTxt = `+${_ep}pp`; }
    else if (_ep >= 0)  { modSig =  0; modEmoji = '🟡'; modTxt = `+${_ep}pp`; }
    else if (_ep >= -4) { modSig = -1; modEmoji = '🟠'; modTxt = `${_ep}pp`;  }
    else                { modSig = -1; modEmoji = '🔴'; modTxt = `${_ep}pp`;  }
  }

  // ── Signal 2: Market (Line Movement / CLV) ───────────────────────────────
  // Compares opening odds to current odds. Odds shortening = sharp money in.
  // Suppressed for estimated-odds picks (no real bookie feed).
  let mktSig = 0, mktEmoji = '⬜', mktTxt = '—';
  if (pick.oddsOpen && oddsNum != null && !pick.oddsIsEst) {
    const _ml = (pick.market || '').toLowerCase();

    // Map market label → odds_open key
    const _ok = _ml.includes('hz:') || _ml.includes('halbzeit')               ? null
      : _ml.includes('doppelte chance') && _ml.includes('x2')                 ? 'dcX2_bkr'
      : _ml.includes('doppelte chance') && _ml.includes('1x')                 ? 'dc1X_bkr'
      : _ml.includes('heimsieg')      || _ml.includes('dnb: heim')            ? 'hw'
      : _ml.includes('auswärtssieg')  || _ml.includes('dnb: ausw')            ? 'aw'
      : _ml.includes('unentschieden') || _ml.includes('remis')                ? 'dr'
      : _ml.includes('over 2.5')      || _ml.includes('über 2.5')             ? 'o25'
      : _ml.includes('under 2.5')     || _ml.includes('unter 2.5')            ? 'u25'
      : _ml.includes('btts')          || _ml.includes('beide teams')          ? 'bttsY'
      : null;

    let _oo = _ok ? parseFloat(pick.oddsOpen[_ok]) : null;

    // Derive DC opening from 1X2 if DC snapshot not stored directly
    if ((!_oo || _oo <= 1) && pick.oddsOpen.hw && pick.oddsOpen.dr && pick.oddsOpen.aw) {
      const _t = 1 / pick.oddsOpen.hw + 1 / pick.oddsOpen.dr + 1 / pick.oddsOpen.aw;
      if (_ok === 'dcX2_bkr') _oo = Math.round((1 / ((1 / pick.oddsOpen.dr) / _t + (1 / pick.oddsOpen.aw) / _t)) * 0.97 * 100) / 100;
      if (_ok === 'dc1X_bkr') _oo = Math.round((1 / ((1 / pick.oddsOpen.hw) / _t + (1 / pick.oddsOpen.dr) / _t)) * 0.97 * 100) / 100;
    }

    if (_oo && _oo > 1 && Math.abs(_oo - oddsNum) > 0.01) {
      const _ppD = Math.round(((1 / oddsNum) - (1 / _oo)) * 100);
      if (Math.abs(_ppD) >= 2) {
        if (oddsNum < _oo) { mktSig =  1; mktEmoji = '🟢'; mktTxt = `↘ ${Math.abs(_ppD)}pp CLV`; }
        else               { mktSig = -1; mktEmoji = '🔴'; mktTxt = `↗ ${Math.abs(_ppD)}pp`;     }
      } else { mktEmoji = '⬜'; mktTxt = 'stabil'; }
    } else if (_oo) { mktEmoji = '⬜'; mktTxt = 'stabil'; }
  }

  // ── Signal 3: H2H Story ───────────────────────────────────────────────────
  // Does head-to-head history support the pick? Rate vs threshold determines signal.
  let storySig = 0, storyEmoji = '⬜', storyTxt = '—';
  const _h = pick.h2h;
  if (_h && _h.games >= 3) {
    const _n   = _h.games;
    const _hw2 = _h.homeWins || 0, _dw2 = _h.draws || 0, _aw2 = _h.awayWins || 0;
    const _ml2 = (pick.market || '').toLowerCase();
    let _rate = null, _thresh = 0.5, _lbl = '';

    if      (_ml2.includes('heimsieg')      || _ml2.includes('dnb: heim') || _ml2.startsWith('ah heim')) {
      _rate = _hw2 / _n; _thresh = 0.45; _lbl = `${Math.round(_rate * 100)}% H`;
    } else if (_ml2.includes('auswärtssieg') || _ml2.includes('dnb: ausw') || _ml2.startsWith('ah ausw')) {
      _rate = _aw2 / _n; _thresh = 0.40; _lbl = `${Math.round(_rate * 100)}% A`;
    } else if (_ml2.includes('unentschieden') || _ml2.includes('remis')) {
      _rate = _dw2 / _n; _thresh = 0.28; _lbl = `${Math.round(_rate * 100)}% X`;
    } else if (_ml2.includes('doppelte chance') && _ml2.includes('x2')) {
      _rate = (_dw2 + _aw2) / _n; _thresh = 0.50; _lbl = `${Math.round(_rate * 100)}% X2`;
    } else if (_ml2.includes('doppelte chance') && _ml2.includes('1x')) {
      _rate = (_hw2 + _dw2) / _n; _thresh = 0.50; _lbl = `${Math.round(_rate * 100)}% 1X`;
    } else if ((_ml2.includes('under') || _ml2.includes('unter')) && !_ml2.includes('ecken') && !_ml2.includes('karten') && _h.avgGoals != null) {
      // Goals-Under (NOT corners/cards — those have no H2H equivalent)
      const _ag = parseFloat(_h.avgGoals);
      const _ul = parseFloat((_ml2.match(/[\d.]+/) || ['2.5'])[0]);
      if (!isNaN(_ag) && !isNaN(_ul)) {
        _rate = _ag < _ul ? 0.70 : _ag < _ul + 0.5 ? 0.40 : 0.15;
        _thresh = 0.5; _lbl = `Ø ${_ag} Tore`;
      }
    } else if ((_ml2.includes('over') || _ml2.includes('über')) && !_ml2.includes('ecken') && !_ml2.includes('karten') && _h.over25Rate != null) {
      // Goals-Over (NOT corners/cards)
      _rate = _h.over25Rate; _thresh = 0.50; _lbl = `${Math.round(_rate * 100)}% +2.5`;
    } else if ((_ml2.includes('btts') || _ml2.includes('beide teams')) && _h.bttsRate != null) {
      _rate = _h.bttsRate; _thresh = 0.45; _lbl = `BTTS ${Math.round(_rate * 100)}%`;
    }

    if (_rate !== null && _lbl) {
      storyTxt = _lbl;
      if      (_rate >= _thresh + 0.10) { storySig =  1; storyEmoji = '🟢'; }
      else if (_rate >= _thresh - 0.10) { storySig =  0; storyEmoji = '🟡'; }
      else                              { storySig = -1; storyEmoji = '🔴'; }
    }
  }

  // ── Final Verdict ─────────────────────────────────────────────────────────
  // Score = sum of three signals (-3 to +3).
  // Hard SKIP: model AND market both negative (two sharps agree: fade).
  // BET: score ≥2, or score=1 with model signal confirming (avoids noise bets).
  const _score    = modSig + mktSig + storySig;
  const _hardSkip = modSig === -1 && mktSig === -1;
  let verdict, vColor, vBg, vBorder;

  if (_hardSkip || _score <= -1) {
    verdict = 'SKIP';    vColor = '#f85149'; vBg = 'rgba(248,81,73,0.12)';  vBorder = 'rgba(248,81,73,0.32)';
  } else if (_score >= 2 || (_score === 1 && modSig === 1)) {
    verdict = 'BET';     vColor = '#3fb950'; vBg = 'rgba(63,185,80,0.12)';  vBorder = 'rgba(63,185,80,0.32)';
  } else {
    verdict = 'ABWÄGEN'; vColor = '#e3b341'; vBg = 'rgba(227,179,65,0.10)'; vBorder = 'rgba(227,179,65,0.28)';
  }

  return { modSig, modEmoji, modTxt, mktSig, mktEmoji, mktTxt, storySig, storyEmoji, storyTxt, verdict, vColor, vBg, vBorder };
}
