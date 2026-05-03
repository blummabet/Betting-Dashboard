// ═══════════════════════════════════════════════════════
//  validator.js — CocoBet Logik-Validator
//  Extracted from season-finish.html (Apr 2026)
//
//  Contains:
//    · buildValidatorDates()  — Datumsdropdown befüllen
//    · runPicksValidator()    — Picks validieren (alle Leagues)
//    · renderValidatorOutput()— HTML-Ausgabe rendern
//    · copyValidatorOutput()  — Ausgabe in Clipboard kopieren
//
//  Runtime dependencies (provided by the page):
//    · LEAGUES                — injected by update_dashboard.py
//    · window._teamStats      — injected by refresh_stats.py
//    · window._preMatchData   — loaded by prematch-server.js
//    · getBettingPicks()      — from pick-engine.js
//    · _poissonOver()         — from pick-engine.js
//    · GATE                   — from pick-engine.js
//    · findOdds()             — from season-finish.html (main script)
//    · DOM: document, navigator.clipboard
// ═══════════════════════════════════════════════════════

// ═══════════════════════════════════════════════════════
//  LOGIK-VALIDATOR
// ═══════════════════════════════════════════════════════

function buildValidatorDates() {
  const sel = document.getElementById('validatorDateSelect');
  if (!sel || typeof LEAGUES === 'undefined') return;

  // Parse "DD.MM.YYYY" → Date
  const parseDate = s => {
    const [d, m, y] = s.split('.');
    return new Date(`${y}-${m}-${d}T12:00:00`);
  };

  const today = new Date(); today.setHours(0,0,0,0);
  const limit = new Date(today); limit.setDate(limit.getDate() + 21);

  const dateSet = new Set();
  for (const lk of Object.keys(LEAGUES)) {
    for (const fx of (LEAGUES[lk].fixtures || [])) {
      if (!fx.date) continue;
      const d = parseDate(fx.date);
      if (d >= today && d <= limit) dateSet.add(fx.date);
    }
  }

  // Sort DD.MM.YYYY by converting to comparable string
  const sorted = [...dateSet].sort((a, b) => {
    const [ad,am,ay] = a.split('.');
    const [bd,bm,by] = b.split('.');
    return new Date(`${ay}-${am}-${ad}`) - new Date(`${by}-${bm}-${bd}`);
  });

  const weekdays = ['So','Mo','Di','Mi','Do','Fr','Sa'];
  sel.innerHTML = '<option value="">— Spieltag wählen —</option>' + sorted.map(dateStr => {
    const [d,m,y] = dateStr.split('.');
    const dt = new Date(`${y}-${m}-${d}T12:00:00`);
    const wd = weekdays[dt.getDay()];
    return `<option value="${dateStr}">${wd} ${d}.${m}.</option>`;
  }).join('');
}

function runPicksValidator() {
  const sel = document.getElementById('validatorDateSelect');
  const date = sel?.value;
  const out = document.getElementById('validatorOutput');
  const copyBtn = document.getElementById('validatorCopyBtn');
  if (!out) return;
  if (!date) { out.innerHTML = ''; if (copyBtn) copyBtn.style.display='none'; return; }

  const results = [];
  let checked = 0;

  for (const lk of Object.keys(LEAGUES)) {
    const lg = LEAGUES[lk];
    const rl = lg.roundsLeft || 99;
    const ceiling = rl<=1?12.0:rl<=2?11.5:rl<=3?11.0:rl<=4?10.5:rl<=5?10.0:rl<=6?9.5:rl<=7?9.0:rl<=8?8.5:rl<=9?8.0:7.5;

    for (const fx of (lg.fixtures || [])) {
      if (fx.date !== date) continue;
      if (!fx.homeStake && !fx.awayStake) continue; // no stakes = not in scope
      checked++;

      const hs = fx.homeStake || {};
      const as = fx.awayStake || {};
      const hf = fx.homeForm  || {};
      const af = fx.awayForm  || {};
      const ms = fx.matchScore || 0;
      const h2h = fx.h2h || {};
      const label = `${lg.flag || ''} ${fx.home} vs ${fx.away}`;

      const hMotiv = hs.motivationLevel || '';
      const aMotiv = as.motivationLevel || '';
      const hPR = hs.pressureRatio || 0;
      const aPR = as.pressureRatio || 0;
      const hPN = hs.pointsNeeded || 0;
      const aPN = as.pointsNeeded || 0;
      const hMW = hs.mustWin || false;
      const aMW = as.mustWin || false;
      const hGPG = hf.goalsPerGame || hs.goalsPerGame || 0;
      const aGPG = af.goalsPerGame || as.goalsPerGame || 0;
      const hScore = hs.score || 0;
      const aScore = as.score || 0;

      // Label-based color
      const hColor = (hs.labels||[]).map(x=>x.c||'').join(' ');
      const aColor = (as.labels||[]).map(x=>x.c||'').join(' ');
      const hRed  = hColor.includes('red');
      const aRed  = aColor.includes('red');
      const hGold = hColor.includes('gold');
      const aGold = aColor.includes('gold');
      const anyRed  = hRed || aRed;
      const bothRed = hRed && aRed;
      const anyGold = hGold || aGold;
      const bothGold = hGold && aGold;

      const hRedSafe = hRed && hMotiv !== 'none' && hPR === 0 && hPN === 0;
      const aRedSafe = aRed && aMotiv !== 'none' && aPR === 0 && aPN === 0;
      const bothRedSafe = hRedSafe && aRedSafe;
      const bothNone = hMotiv === 'none' && aMotiv === 'none';
      const bothLow  = hMotiv === 'low'  && aMotiv === 'low';

      const h2hGames    = h2h.games    || 0;
      const h2hHW       = h2h.homeWins || 0;
      const h2hAW       = h2h.awayWins || 0;
      const h2hAvgGoals = h2h.avgGoals || 0;
      const h2hDom = h2hGames >= 5 && (h2hHW/h2hGames >= 0.75 || h2hAW/h2hGames >= 0.75);

      const flag = (sev, code, msg) => results.push({sev, code, label, league: lg.name, msg});

      // ── 🔴 FEHLER ──────────────────────────────────────────────
      if ((hMW && hMotiv === 'none') || (aMW && aMotiv === 'none')) {
        const who = (hMW && hMotiv==='none') ? fx.home : fx.away;
        flag('error', 'MW_ON_CONFIRMED_REL', `${who}: mustWin=true aber motiv='none' — abgestiegenes/gesichertes Team wird falsch bewertet`);
      }
      if (ms > ceiling + 0.05) {
        flag('error', 'SCORE_EXCEEDS_CEILING', `Score ${ms} überschreitet Ceiling ${ceiling} für roundsLeft=${rl} — Python-Daten vor dem Fix generiert`);
      }
      if (bothNone && ms > 6) {
        flag('error', 'DEAD_RUBBER_HIGH_SCORE', `Beide motiv='none' (Dead Rubber) — Score ${ms} > 6, Dead-Rubber-Penalty nicht angewendet`);
      }

      // ── 🟡 WARNUNGEN ───────────────────────────────────────────
      if (anyRed && (hRedSafe || aRedSafe) && ms >= 7.5) {
        const who = bothRedSafe ? 'Beide' : (hRedSafe ? fx.home : fx.away);
        flag('warn', 'RED_SAFE_HIGH_SCORE', `${who}: rot-Label aber pressure=0, ptNeeded=0, Score ${ms} ≥7.5 — Angle-Text könnte falsche Dringlichkeit ausstrahlen`);
      }
      if (hMW && hGPG < 0.8 && hGPG > 0) {
        flag('warn', 'MUSTWIN_LOW_GPG', `${fx.home}: mustWin=true aber goalsPerGame=${hGPG.toFixed(2)} — Team kann realistisch kaum gewinnen`);
      }
      if (aMW && aGPG < 0.8 && aGPG > 0) {
        flag('warn', 'MUSTWIN_LOW_GPG', `${fx.away}: mustWin=true aber goalsPerGame=${aGPG.toFixed(2)} — Team kann realistisch kaum gewinnen`);
      }
      if (h2hDom && ms >= 8) {
        const domTeam = h2hHW/h2hGames >= 0.75 ? fx.home : fx.away;
        const domPct  = Math.round(Math.max(h2hHW,h2hAW)/h2hGames*100);
        flag('warn', 'H2H_DOMINATED_HIGH_SCORE', `${domTeam} dominiert H2H (${domPct}% / ${h2hGames} Sp.) — Underdog-Alarm-Text könnte irreführend sein`);
      }
      if (bothRed && bothRedSafe) {
        flag('warn', 'BOTH_RED_SAFE', `Beide Teams rot aber beide mathematisch gerettet (pressure=0) — Kellerduell-Narrative ist falsch`);
      }
      if (bothLow && ms >= 9) {
        flag('warn', 'BOTH_LOW_MOTIV_HIGH_SCORE', `Beide motiv='low', Score trotzdem ${ms} ≥9 — ungewöhnlich hoher Score bei niedrigem Antrieb`);
      }
      const avgGPG = (hGPG + aGPG) / 2;
      // LOW_SCORING_PROFILE — nur als 🔵 Hinweis, unabhängig vom tatsächlichen Pick.
      // LOW_SCORING_OVER_RISK (🟡) wird weiter unten in der Picks-Sektion geprüft,
      // dort haben wir Zugriff auf _genPicks und feuern nur wenn wirklich ein Over-Pick vorhanden ist.
      if (avgGPG > 0 && avgGPG < 0.9 && h2hAvgGoals < 2.0 && h2hGames >= 3) {
        flag('info', 'LOW_SCORING_PROFILE', `Ø gpg=${avgGPG.toFixed(2)}, H2H Ø=${h2hAvgGoals.toFixed(1)} Tore — Niedrig-Scoring-Profil`);
      }

      // ── 🔵 HINWEISE (Stake-Daten) ──────────────────────────────
      if (h2hDom && anyGold && anyRed) {
        flag('info', 'H2H_DOM_GOLD_RED', `Gold+Rot Duell mit H2H-Dominanz — Pick-Richtung sollte durch Angle bestätigt werden`);
      }
      if (h2hGames < 5 && ms >= 8) {
        flag('info', 'LOW_H2H_SAMPLE', `Nur ${h2hGames} H2H-Spiele bei Score ${ms} — Quoten stärker gewichten als H2H-Statistiken`);
      }
      if (bothGold && hPR === 0 && aPR === 0) {
        flag('info', 'BOTH_GOLD_NO_PRESSURE', `bothGold aber beide pressure=0 — "Titelduell"-Text übertreibt Dringlichkeit`);
      }
      const scoreDiff = Math.abs(hScore - aScore);
      if (scoreDiff >= 4 && hScore > 0 && aScore > 0) {
        flag('info', 'ASYMMETRIC_STAKE_SCORES', `Score-Differenz ${scoreDiff.toFixed(1)} Punkte (${fx.home}: ${hScore} vs ${fx.away}: ${aScore}) — sehr klarer Favorit`);
      }

      // ── PICKS-BASIERTE CHECKS ─────────────────────────────────────────────────
      // getBettingPicks() und findOdds() sind synchron — direkt aufrufbar.
      // Fixture-State vorbereiten: roundsLeft muss am Match stehen (wie generate_picks.js).
      let _genPicks = [], _picksOk = false;
      let _fxCopy = null; // hoisted so _fxCopy._expGoals is readable after the try/catch
      try {
        _fxCopy = Object.assign({}, fx);
        if (_fxCopy.roundsLeft == null) _fxCopy.roundsLeft = rl;
        const _odds = findOdds(lk, fx.home, fx.away) || {};
        _genPicks = getBettingPicks(_fxCopy, _odds, lk) || [];
        _picksOk  = true;
      } catch(_e) { /* getBettingPicks fehlt oder Odds-Lookup failed */ }

      if (_picksOk && _genPicks.length > 0) {
        const _p1 = _genPicks[0];
        const _hc = (fx.homeStake?.labels||[]).map(l=>l.c||'');
        const _ac = (fx.awayStake?.labels||[]).map(l=>l.c||'');
        const _hNone = (fx.homeStake?.motivationLevel || 'full') === 'none';
        const _aNone = (fx.awayStake?.motivationLevel || 'full') === 'none';

        // ── 🔴 FEHLER (Picks) — direkte Pick-Validierung ─────────
        // Diese Checks prüfen die tatsächlich generierten Picks gegen bekannte Fehler-Muster.
        // Findet was der Nutzer bisher täglich manuell gefunden hat.

        // 🔴 Under 1.5 Pick aber H2H widerlegt ihn (Heracles/Volendam-Typ)
        const _under15Pick = _genPicks.find(p => p.market === 'Under 1.5 Tore');
        if (_under15Pick && h2hGames >= 4) {
          if (h2hAvgGoals >= 2.0) {
            flag('error', 'U15_H2H_CONTRADICT',
              `Under 1.5 Pick [${_under15Pick.conf}] aber H2H Ø=${h2hAvgGoals.toFixed(1)} Tore (${h2hGames} Sp.) — H2H widerlegt den Pick direkt. H2H-Guard greift nicht oder reicht nicht.`);
          }
        }

        // 🔴 Under 2.5 Pick aber H2H widerlegt ihn mit Hard Block (≥ 3.5 Ø sollte geblockt haben)
        const _under25PickH2h = _genPicks.find(p => p.market === 'Under 2.5 Tore');
        if (_under25PickH2h && h2hGames >= 4) {
          if (h2hAvgGoals >= 3.5) {
            flag('error', 'U25_H2H_HARD_BLOCK_MISS',
              `Under 2.5 Pick [${_under25PickH2h.conf}] aber H2H Ø=${h2hAvgGoals.toFixed(1)} Tore (${h2hGames} Sp.) — HARD BLOCK (≥3.5) hat nicht gegriffen.`);
          } else if (h2hAvgGoals >= 3.0) {
            flag('warn', 'U25_H2H_CONTRADICT',
              `Under 2.5 Pick [${_under25PickH2h.conf}] aber H2H Ø=${h2hAvgGoals.toFixed(1)} Tore (${h2hGames} Sp.) — starke Dämpfung aktiv, Pick prüfen.`);
          }
        }

        // 🔴 Karten-Pick für bestätigt abgestiegenes Team ohne Schiri-Evidenz
        const _cardsPick = _genPicks.find(p =>
          p.market?.toLowerCase().includes('karten') || p.market?.toLowerCase().includes('cards'));
        if (_cardsPick) {
          const _anyConfRel = (_hNone && _hc.includes('red')) || (_aNone && _ac.includes('red'));
          if (_anyConfRel) {
            const relTeam = (_hNone && _hc.includes('red')) ? fx.home : fx.away;
            flag('error', 'CARDS_PICK_RELEGATED',
              `${_cardsPick.market} Pick [${_cardsPick.conf}] aber ${relTeam} ist bestätigt abgestiegen (motiv='none'). cardSc-Suppression greift nicht — Schiri-Threshold prüfen.`);
          }
        }

        // 🔴 Pick ohne Quote UND kein "keine Quote"-Label (wird trotzdem als Pick angezeigt)
        _genPicks.forEach((p, i) => {
          if (p.odds === null && !p.oddsIsEst && p.conf !== 'low') {
            flag('error', 'PICK_NO_ODDS_MEDIUM',
              `Pick ${i+1} "${p.market}" [${p.conf}] hat keine Quote und ist nicht [low] — wird als relevanter Pick angezeigt ohne Wettmöglichkeit.`);
          }
        });

        // Abgestiegenes Heimteam bekommt Heimsieg/AH Heim als Pick 1
        if (_hNone && _hc.includes('red')) {
          if (_p1.market === 'Heimsieg' || _p1.market.startsWith('AH Heim') || _p1.market.startsWith('Handicap Heim')) {
            flag('error', 'RELEGATED_HOME_RESULT_PICK', `${fx.home} motiv=none (abgestiegen) aber Pick 1 = "${_p1.market}" [${_p1.conf}] — System setzt auf ein motivationsloses Team`);
          }
        }
        // Abgestiegenes Auswärtsteam bekommt Auswärtssieg/AH Ausw als Pick 1
        if (_aNone && _ac.includes('red')) {
          if (_p1.market === 'Auswärtssieg' || _p1.market.startsWith('AH Ausw') || _p1.market.startsWith('Handicap Ausw')) {
            flag('error', 'RELEGATED_AWAY_RESULT_PICK', `${fx.away} motiv=none (abgestiegen) aber Pick 1 = "${_p1.market}" [${_p1.conf}] — System setzt auf ein motivationsloses Team`);
          }
        }
        // Negativer sc — darf nie gezeigt werden
        _genPicks.forEach((p, i) => {
          if (typeof p.sc === 'number' && p.sc < 0) {
            flag('error', 'NEGATIVE_SC_PICK', `Pick ${i+1} "${p.market}" hat sc=${p.sc.toFixed(3)} (negativ) — wurde trotzdem angezeigt`);
          }
        });
        // Unentschieden als Fallback bei sehr hoher Quote (> 3.50)
        if (_p1.market === 'Unentschieden' && _p1.conf === 'medium' && _p1.odds !== null && _p1.odds > 3.50) {
          flag('error', 'DRAW_FALLBACK_HIGH_ODDS', `Unentschieden [medium] als Fallback-Pick bei Quote ${_p1.odds} — reine Rauschen-Promotion, kein echter Signal`);
        }

        // 🔴 LOW_SCORING_OVER_RISK — nur wenn tatsächlich ein Over-Pick generiert wurde
        // (vorher war der Check im Stake-Abschnitt ohne Zugriff auf _genPicks → Fehlalarm bei Under-Picks)
        const _hasOverPick = _genPicks.some(p => p.market?.startsWith('Over ') && p.market?.includes('Tore'));
        if (_hasOverPick && avgGPG > 0 && avgGPG < 0.7 && h2hAvgGoals < 2.0 && h2hGames >= 5) {
          flag('warn', 'LOW_SCORING_OVER_RISK',
            `Ø gpg=${avgGPG.toFixed(2)}, H2H Ø=${h2hAvgGoals.toFixed(1)} Tore (${h2hGames} Sp.) — Over-Pick trotz schwachem Scoring-Profil. Hard Gate sollte greifen.`);
        }

        // ── 🟡 WARNUNGEN (Picks) ─────────────────────────────────
        // Medium-Pick mit sehr niedrigem sc (Fallback-Promotion)
        _genPicks.forEach((p, i) => {
          if (p.conf === 'medium' && typeof p.sc === 'number' && p.sc < 0.15 && p.sc > 0) {
            flag('warn', 'LOW_SC_MEDIUM_PICK', `Pick ${i+1} "${p.market}" ist [medium] aber sc=${p.sc.toFixed(3)} — Fallback-Promotion mit schwachem Signal`);
          }
        });
        // Under 2.5 für starkes Auswärtsteam (xG_away > 1.8 + AWR > 0.60)
        const _ts = window._teamStats || {};
        const _aStatV = _ts[lk]?.[fx.away] || {};
        const _hStatV = _ts[lk]?.[fx.home] || {};
        const _under25Pick = _genPicks.find(p => p.market === 'Under 2.5 Tore' || p.market === 'Unter 2.5 Tore');
        if (_under25Pick && _aStatV.xG_away > 1.8 && _aStatV.awayWinRate > 0.60) {
          flag('warn', 'UNDER_DOMINANT_AWAY', `Under 2.5 Pick für ${fx.away} (xG=${_aStatV.xG_away?.toFixed(1)} auswärts, ${Math.round(_aStatV.awayWinRate*100)}% AWR) — kontraindiziert für ein dominant torstarkes Auswärtsteam`);
        }
        // Sehr kurze Ergebnis-Quote ohne Handicap-Nutzung
        if ((_p1.market === 'Heimsieg' || _p1.market === 'Auswärtssieg') && _p1.odds !== null && _p1.odds < 1.25) {
          flag('warn', 'RESULT_VERY_SHORT_NO_AH', `${_p1.market} bei Quote ${_p1.odds} — so kurze Quoten sollten als AH-Pick gezeigt werden (besser Risk/Reward)`);
        }
        // Alle 3 Picks sind [low]
        if (_genPicks.length >= 3 && _genPicks.every(p => p.conf === 'low')) {
          flag('warn', 'ALL_PICKS_LOW', `Alle ${_genPicks.length} Picks sind [low] — kaum verwertbares Signal, Spiel lieber überspringen`);
        }

        // 🟡 Beide Teams motiv='low' aber trotzdem Medium/High Pick vorhanden
        if (bothLow) {
          const _highPick = _genPicks.find(p => p.conf === 'medium' || p.conf === 'high');
          if (_highPick) {
            flag('warn', 'BOTH_LOW_MOTIV_MEDIUM_PICK',
              `Beide Teams motiv='low' aber Pick "${_highPick.market}" ist [${_highPick.conf}] — bei niedrigem Antrieb beider Teams sollten keine Medium/High-Picks erscheinen.`);
          }
        }

        // 🟡 Over 2.5 Pick aber beide Teams historisch torarm
        const _over25Pick = _genPicks.find(p => p.market?.startsWith('Over 2.5') || p.market?.startsWith('Über 2.5'));
        if (_over25Pick && hGPG > 0 && aGPG > 0 && (hGPG + aGPG) < 1.8 && h2hAvgGoals > 0 && h2hAvgGoals < 2.0) {
          flag('warn', 'OVER25_LOW_SCORING',
            `Over 2.5 Pick [${_over25Pick.conf}] aber komb. ${(hGPG+aGPG).toFixed(1)} Tore/Sp und H2H Ø=${h2hAvgGoals.toFixed(1)} — Hard Gate sollte geblockt haben.`);
        }
        // Motivation-Asymmetrie erkannt aber Ergebnis-Pick schwach (< 0.45)
        if (_hNone && _hc.includes('red') && !_aNone) {
          const _awaySc = _genPicks.find(p => p.market === 'Auswärtssieg' || p.market.startsWith('AH Ausw'))?.sc ?? null;
          if (_awaySc !== null && _awaySc < 0.45) {
            flag('warn', 'ASYMMETRY_WEAK_AWAY_SC', `${fx.home} abgestiegen (none) + ${fx.away} kompetitiv — aber Auswärtssieg sc=${_awaySc.toFixed(2)} noch unter Medium. Stake-Label für ${fx.away} fehlt?`);
          }
        }
        if (_aNone && _ac.includes('red') && !_hNone) {
          const _homeSc = _genPicks.find(p => p.market === 'Heimsieg' || p.market.startsWith('AH Heim'))?.sc ?? null;
          if (_homeSc !== null && _homeSc < 0.45) {
            flag('warn', 'ASYMMETRY_WEAK_HOME_SC', `${fx.away} abgestiegen (none) + ${fx.home} kompetitiv — aber Heimsieg sc=${_homeSc.toFixed(2)} noch unter Medium. Stake-Label für ${fx.home} fehlt?`);
          }
        }

        // 🔴 Goals FV Negative Edge — Over 2.5 / Over 3.5 mit negativem Poisson-Edge
        // Prüft ob FV-Gate (neu Apr 2026) Pick korrekt geblockt hätte
        // NOTE: _fxCopy._expGoals is written by getBettingPicks() after expGoals is finalised.
        // Do NOT fall back to (hGPG + aGPG) — that uses static config values that are ~10× too small
        // and cause false positives.  Skip the check entirely if _expGoals wasn't written.
        { const _o25p = _genPicks.find(p => p.market?.startsWith('Over 2.5') || p.market?.startsWith('Über 2.5'));
          if (_o25p && _o25p.odds != null && !_o25p.oddsIsEst && _fxCopy._expGoals != null) {
            const _fv25 = _poissonOver(_fxCopy._expGoals, 2.5);
            const _gap25 = (1 / _o25p.odds) - _fv25;
            if (_gap25 > GATE.GOALS_REAL) flag('error', 'OVER25_NEG_EDGE',
              `Over 2.5 Pick [${_o25p.conf}] @ ${_o25p.odds} aber Poisson FV=${(_fv25*100).toFixed(1)}% (Implied=${(100/_o25p.odds).toFixed(1)}%, Gap=${(_gap25*100).toFixed(1)}pp) — FV-Gate sollte geblockt haben.`);
          }
          const _o35p = _genPicks.find(p => p.market?.startsWith('Over 3.5') || p.market?.startsWith('Über 3.5'));
          if (_o35p && _o35p.odds != null && !_o35p.oddsIsEst && _fxCopy._expGoals != null) {
            const _fv35 = _poissonOver(_fxCopy._expGoals, 3.5);
            const _gap35 = (1 / _o35p.odds) - _fv35;
            if (_gap35 > GATE.GOALS_REAL) flag('error', 'OVER35_NEG_EDGE',
              `Over 3.5 Pick [${_o35p.conf}] @ ${_o35p.odds} aber Poisson FV=${(_fv35*100).toFixed(1)}% (Implied=${(100/_o35p.odds).toFixed(1)}%, Gap=${(_gap35*100).toFixed(1)}pp) — FV-Gate sollte geblockt haben.`);
          }
        }
        // 🔴 BTTS FV Negative Edge
        // Uses _fxCopy._muH / _fxCopy._muA (same Poisson params as pick-engine's BTTS gate).
        // Do NOT fall back to the rough (hGPG+aGPG)*0.65 proxy — gives false positives when
        // goalsPerGame is missing (defaults to 0 here but 1.4 in pick-engine). Skip if muH/muA unavailable.
        { const _bttsp = _genPicks.find(p => p.market === 'Beide Teams treffen');
          if (_bttsp && _bttsp.odds != null && !_bttsp.oddsIsEst &&
              _fxCopy._muH != null && _fxCopy._muA != null) {
            const _expH = Math.max(0.1, _fxCopy._muH);
            const _expA = Math.max(0.1, _fxCopy._muA);
            const _bttsFV = (1 - Math.exp(-_expH)) * (1 - Math.exp(-_expA));
            const _bttsGap = (1 / _bttsp.odds) - _bttsFV;
            if (_bttsGap > GATE.BTTS_REAL) flag('error', 'BTTS_NEG_EDGE',
              `BTTS Pick [${_bttsp.conf}] @ ${_bttsp.odds} aber Poisson FV≈${(_bttsFV*100).toFixed(1)}% (Implied=${(100/_bttsp.odds).toFixed(1)}%, Gap=${(_bttsGap*100).toFixed(1)}pp) — FV-Gate sollte geblockt haben.`);
          }
        }
        // 🔴 1X2 Result FV Negative Edge — Heimsieg / Auswärtssieg mit negativem Poisson-Edge
        // Uses _fxCopy._muH / _fxCopy._muA written by getBettingPicks() (Apr 2026 Poisson model).
        // Gate: GATE.RESULT_REAL = 0.15 — independent Poisson model, not bookie-derived.
        { const _heimp = _genPicks.find(p => p.market === 'Heimsieg');
          if (_heimp && _heimp.odds != null && !_heimp.oddsIsEst &&
              _fxCopy._muH != null && _fxCopy._muA != null) {
            const _pp = _poisson1x2(_fxCopy._muH, _fxCopy._muA);
            if (_pp) {
              const _heimGap = (1 / _heimp.odds) - _pp.pH;
              if (_heimGap > GATE.RESULT_REAL) flag('error', 'HEIMSIEG_NEG_EDGE',
                `Heimsieg Pick [${_heimp.conf}] @ ${_heimp.odds} aber Poisson FV=${(_pp.pH*100).toFixed(1)}% (Implied=${(100/_heimp.odds).toFixed(1)}%, Gap=${(_heimGap*100).toFixed(1)}pp) — RESULT_REAL Gate sollte geblockt haben.`);
            }
          }
          const _auswp = _genPicks.find(p => p.market === 'Auswärtssieg');
          if (_auswp && _auswp.odds != null && !_auswp.oddsIsEst &&
              _fxCopy._muH != null && _fxCopy._muA != null) {
            const _pp = _poisson1x2(_fxCopy._muH, _fxCopy._muA);
            if (_pp) {
              const _auswGap = (1 / _auswp.odds) - _pp.pA;
              if (_auswGap > GATE.RESULT_REAL) flag('error', 'AUSWÄRTSSIEG_NEG_EDGE',
                `Auswärtssieg Pick [${_auswp.conf}] @ ${_auswp.odds} aber Poisson FV=${(_pp.pA*100).toFixed(1)}% (Implied=${(100/_auswp.odds).toFixed(1)}%, Gap=${(_auswGap*100).toFixed(1)}pp) — RESULT_REAL Gate sollte geblockt haben.`);
            }
          }
        }
        // 🟡 Karten-Pick aber Schiri-Daten fehlen (Ref=null → Fallback auf Liga-Baserate)
        { const _cp2 = _genPicks.find(p => p.market?.toLowerCase().includes('karten'));
          const _anyRedConf2 = (_hNone && _hc.includes('red')) || (_aNone && _ac.includes('red'));
          if (_cp2 && _anyRedConf2) {
            const _ts2 = window._teamStats || {};
            const _refStats = window._preMatchData?.[`${fx.home}|${fx.away}`];
            const _refAvg2 = _refStats?.refereeStats?.cardsPerGame ?? null;
            if (_refAvg2 === null) {
              flag('warn', 'CARDS_REL_NO_REF_DATA',
                `${_cp2.market} Pick [${_cp2.conf}] bei abgestiegenem Team aber keine Schiri-Daten — Fallback auf Liga-Baserate (3.5) aktiv. Pick manuell prüfen.`);
            }
          }
        }

        // ── 🔵 HINWEISE (Picks) ───────────────────────────────────
        // Kein einziger echter Bookie-Quotenfeed
        if (_genPicks.length > 0 && _genPicks.every(p => p.oddsIsEst || p.odds === null)) {
          flag('info', 'NO_REAL_ODDS', `Alle ${_genPicks.length} Picks haben geschätzte oder keine Quoten (~) — kein echter Bookmaker-Feed vorhanden`);
        }
        // Corner-Pick mit verdächtigen Stats-Daten
        const _cornerPick = _genPicks.find(p => p.market?.includes('Ecken'));
        if (_cornerPick) {
          const _hCornH = _hStatV.cornersHome ?? null;
          const _aCornA = _aStatV.cornersAway ?? null;
          if ((_hCornH !== null && _hCornH < 2.0) || (_aCornA !== null && _aCornA < 2.0)) {
            const who = (_hCornH !== null && _hCornH < 2.0) ? `${fx.home} cornH=${_hCornH}` : `${fx.away} cornA=${_aCornA}`;
            flag('info', 'CORNER_BAD_DATA', `${_cornerPick.market} Pick aber ${who} <2 (vermutlich <2 gespeicherte Spiele) — Formel-Fallback aktiv, Pick auf Plausibilität prüfen`);
          }
        }
        // Fehlende Stake-Labels bei 0 Picks
        if (_genPicks.length === 0 && (fx.homeStake || fx.awayStake)) {
          flag('info', 'NO_PICKS_GENERATED', `Kein einziger Pick generiert — Score=${ms}, roundsLeft=${rl}. Alle Signale unter Schwellwert?`);
        }
      } // end _picksOk
    }
  }

  renderValidatorOutput(results, checked, date);
}

function renderValidatorOutput(results, checked, date) {
  const out = document.getElementById('validatorOutput');
  const copyBtn = document.getElementById('validatorCopyBtn');
  if (!out) return;

  const errors = results.filter(r => r.sev === 'error');
  const warns  = results.filter(r => r.sev === 'warn');
  const infos  = results.filter(r => r.sev === 'info');

  const sevStyle = {
    error: {bg:'rgba(248,81,73,.08)', border:'rgba(248,81,73,.3)', badge:'background:#f85149;color:#fff', icon:'🔴', label:'FEHLER'},
    warn:  {bg:'rgba(227,179,65,.06)', border:'rgba(227,179,65,.25)', badge:'background:#e3b341;color:#000', icon:'🟡', label:'WARNUNG'},
    info:  {bg:'rgba(88,166,255,.06)', border:'rgba(88,166,255,.2)', badge:'background:#58a6ff;color:#000', icon:'🔵', label:'HINWEIS'},
  };

  // Summary bar
  let html = `<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:10px 14px;background:var(--card2);border-radius:8px;margin-bottom:14px;font-size:12px;">
    <span style="color:var(--muted);">Geprüft: <strong style="color:var(--text)">${checked} Spiele</strong></span>
    <span style="color:#f85149;font-weight:700;">🔴 ${errors.length} Fehler</span>
    <span style="color:#e3b341;font-weight:700;">🟡 ${warns.length} Warnungen</span>
    <span style="color:#58a6ff;font-weight:700;">🔵 ${infos.length} Hinweise</span>
  </div>`;

  if (results.length === 0) {
    html += `<div style="text-align:center;padding:24px;color:var(--green);font-weight:700;font-size:14px;">✅ Keine Logik-Fehler gefunden — alle Picks sind konsistent</div>`;
  } else {
    for (const sev of ['error','warn','info']) {
      const items = results.filter(r => r.sev === sev);
      if (!items.length) continue;
      const s = sevStyle[sev];
      for (const item of items) {
        html += `<div style="background:${s.bg};border:1px solid ${s.border};border-radius:8px;padding:10px 14px;margin-bottom:8px;display:flex;gap:10px;align-items:flex-start;">
          <span style="display:inline-flex;align-items:center;gap:4px;padding:2px 7px;border-radius:5px;font-size:10px;font-weight:700;white-space:nowrap;${s.badge}">${s.icon} ${s.label}</span>
          <div style="flex:1;min-width:0;">
            <div style="font-weight:700;color:var(--text);margin-bottom:2px;">${item.label}</div>
            <div style="color:var(--muted);font-size:11.5px;"><code style="background:rgba(255,255,255,.06);padding:1px 5px;border-radius:3px;font-size:10.5px;">${item.code}</code> — ${item.msg}</div>
          </div>
        </div>`;
      }
    }
  }

  out.innerHTML = html;
  if (copyBtn) copyBtn.style.display = checked > 0 ? '' : 'none';

  // Store plain-text version for copy
  out._plainText = `Logik-Validator — ${date}\nGeprüft: ${checked} Spiele | 🔴 ${errors.length} Fehler | 🟡 ${warns.length} Warnungen | 🔵 ${infos.length} Hinweise\n${'─'.repeat(60)}\n` +
    (results.length === 0 ? '✅ Keine Logik-Fehler gefunden\n' :
      results.map(r => {
        const icon = r.sev==='error'?'🔴':r.sev==='warn'?'🟡':'🔵';
        return `${icon} [${r.code}]\n   ${r.label}\n   ${r.msg}`;
      }).join('\n\n'));
}

function copyValidatorOutput() {
  const out = document.getElementById('validatorOutput');
  const btn = document.getElementById('validatorCopyBtn');
  const text = out?._plainText;
  if (!text) return;
  navigator.clipboard.writeText(text).then(() => {
    if (btn) { btn.textContent = '✅ Kopiert!'; setTimeout(() => { btn.textContent = '📋 Kopieren'; }, 2000); }
  });
}
