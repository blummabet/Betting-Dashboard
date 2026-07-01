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

  // Conviction-gewichteter Stake (12.06.2026): BET höher als ABWÄGEN, weil BET =
  // Edge + Signal-Bestätigung (höhere Konfidenz). Flat würde die ~vielen ABWÄGEN
  // gleich gewichten → Bilanz weniger repräsentativ. Poly-Auto-Trading bleibt flat.
  // 28.06.2026 (Lucas: Edge-Staking): primär pick.stake (fraktionales Kelly, pick_staking.py).
  // Fallback auf das alte getierte Flat nur für Alt-Picks ohne stake (Freeze-geschützte/historische).
  const STAKE_BET = 10, STAKE_ABW = 5; // €, Fallback
  const _stakeOf = (p) => (p && typeof p.stake === 'number')
    ? p.stake
    : ((p && p.verdict === 'BET') ? STAKE_BET : STAKE_ABW);

  // (25.06.2026, Lucas: KO-Runden) Reihenfolge + deutsche Labels der K.O.-Phase.
  const KO_ROUND_ORDER  = ['R32', 'R16', 'QF', 'SF', '3RD', 'F'];
  const KO_ROUND_LABELS = { R32: 'Sechzehntelfinale', R16: 'Achtelfinale', QF: 'Viertelfinale', SF: 'Halbfinale', '3RD': 'Spiel um Platz 3', F: 'Finale' };

  // ── Modus-Parametrisierung (25.06.2026, Lucas: Liga auf WM-Stack) ──────
  // Gleiches Tracking bedient WM (intlTrackingPanel/wm2026-data.json) UND Liga
  // (trackingV2Panel/liga-data.json). Defaults = WM → initIntlTracking() unverändert.
  let _dataFile = 'wm2026-data.json';
  let _panelId  = 'intlTrackingPanel';
  let _mode     = 'wm';   // 'wm' | 'liga'

  // ── Module state ───────────────────────────────────────
  let _data      = null;
  let _loaded    = false;
  let _loadedFile = null;   // zuletzt geladenes Dataset (25.06.2026, Lucas: Cache-Invalidierung WM↔Liga)
  let _grpFilter = 'all';
  let _mdFilter  = 'all';    // 'all' | 1 | 2 | 3
  let _vrdFilter = 'all';    // 'all' | 'BET' | 'ABWÄGEN' | 'SKIP'
  let _trkSort   = 'chrono'; // 'chrono' (Standard, nach Anpfiff) | 'bet' (nach Pick-Stärke)
  let _showTop   = false;    // toggle for Top Picks section
  let _validationReport = null;
  let _showValidation   = false;
  let _auditReport      = null;
  let _showAudit        = false;

  // ─────────────────────────────────────────────────────
  //  ENTRY POINT
  // ─────────────────────────────────────────────────────
  window.initIntlTracking = async function () {
    // WM-Defaults (25.06.2026, Lucas: Liga auf WM-Stack) — Verhalten unverändert.
    _dataFile = 'wm2026-data.json';
    _panelId  = 'intlTrackingPanel';
    _mode     = 'wm';
    return _loadTracking();
  };

  // (25.06.2026, Lucas: Liga auf WM-Stack) National-Tracking auf dem WM-Tracking.
  // Liest liga-data.json (WM-Format) ins Panel trackingV2Panel. Gleiche
  // BET/ABWÄGEN/NOBET-Logik; KO-Zeilen feuern nur bei koFixtures (Liga: keine).
  window.initNationalTracking = async function () {
    _dataFile = 'liga-data.json';
    _panelId  = 'trackingV2Panel';
    _mode     = 'liga';
    return _loadTracking();
  };

  async function _loadTracking() {
    const panel = document.getElementById(_panelId);
    if (!panel) return;

    if (_loaded && _data && _loadedFile === _dataFile) {   // nur warm bei gleichem Dataset
      _render();
      return;
    }

    panel.innerHTML = `
      <div style="text-align:center;padding:60px 16px;color:var(--muted);">
        <div style="font-size:36px;margin-bottom:14px;animation:spin 1.2s linear infinite;display:inline-block;">⚙️</div>
        <div style="font-size:13px;font-weight:600;">${_mode === 'liga' ? 'Lade Liga-Picks…' : 'Lade WM 2026 Picks…'}</div>
      </div>`;

    try {
      // (25.06.2026, Lucas: Liga auf WM-Stack) Im liga-Modus kein WM-Validator-Report.
      const _isLiga = _mode === 'liga';
      const [resp, valResp] = await Promise.all([
        fetch(_dataFile + '?t=' + Date.now()),
        _isLiga ? Promise.resolve(null) : fetch('pick_validation_report.json?t=' + Date.now()).catch(() => null),
      ]);
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      _data   = await resp.json();
      // 29.06.2026 (Lucas: MLS „wie die anderen Ligen"): MLS-Datensatz mit-laden + mergen
      // (Gruppe „MLS"/Picks „MLS-…" kollisionsfrei) → MLS-Picks erscheinen im Tracking.
      if (_isLiga) {
        try {
          const mlsResp = await fetch('mls-data.json?t=' + Date.now());
          if (mlsResp && mlsResp.ok) {
            const mls = await mlsResp.json();
            if (mls && mls.groups) {
              _data.groups = Object.assign({}, _data.groups || {}, mls.groups);
              _data.picks  = Object.assign({}, _data.picks  || {}, mls.picks  || {});
            }
          }
        } catch (e) { /* MLS optional */ }
      }
      if (valResp && valResp.ok) {
        try { _validationReport = await valResp.json(); } catch (e) {}
      }
      _loaded = true;
      _loadedFile = _dataFile;   // Dataset merken (Cache-Invalidierung WM↔Liga, 25.06.2026)
      _render();
    } catch (e) {
      const _retryFn = _mode === 'liga' ? 'window.initNationalTracking()' : 'window.initIntlTracking()';
      panel.innerHTML = `
        <div style="text-align:center;padding:60px 16px;color:var(--muted);">
          <div style="font-size:40px;margin-bottom:16px;">⚠️</div>
          <div style="font-size:15px;font-weight:700;color:var(--red);">Daten konnten nicht geladen werden</div>
          <div style="font-size:12px;margin-top:8px;">${e.message}</div>
          <button onclick="${_retryFn}" style="margin-top:18px;background:var(--accent);color:#000;border:none;border-radius:8px;padding:8px 20px;font-size:13px;font-weight:700;cursor:pointer;">Erneut versuchen</button>
        </div>`;
    }
  }

  // Filter callbacks (called from inline onclick)
  window.wmTrkSetGroup   = g  => { _grpFilter = g;  _render(); };
  window.wmTrkSetMd      = md => { _mdFilter  = md; _render(); };
  window.wmTrkSetVerdict = v  => { _vrdFilter = v;  _render(); };
  window.wmTrkSetSort    = s  => { _trkSort = s;   _render(); };
  window.wmTrkToggleTop  = () => { _showTop = !_showTop; _render(); };
  // (25.06.2026, Lucas: Liga auf WM-Stack) Refresh ruft den modus-passenden Entry-Point.
  window.wmTrkRefresh    = () => { _loaded = false; _data = null; _validationReport = null; _auditReport = null; (_mode === 'liga' ? window.initNationalTracking : window.initIntlTracking)(); };
  window.wmTrkToggleVal  = () => { _showValidation = !_showValidation; _showAudit = false; _render(); };
  window.wmTrkRunAudit   = () => { _auditReport = _runCardTrackingAudit(); _showAudit = true; _showValidation = false; _render(); };
  window.wmTrkCloseAudit = () => { _showAudit = false; _render(); };

  // ─────────────────────────────────────────────────────
  //  MAIN RENDER
  // ─────────────────────────────────────────────────────
  function _render() {
    const panel = document.getElementById(_panelId);
    if (!panel || !_data) return;
    const _isLiga = _mode === 'liga';   // (25.06.2026, Lucas: Liga auf WM-Stack)

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
        // FIX 12.06.2026: resolve_wm_picks schreibt UPPERCASE WIN/LOSS/VOID,
        // dieser Tab vergleicht aber 'won'/'lost'/'push' → nichts wurde als
        // aufgelöst gezählt. Hier einmalig normalisieren (case-robust, beide
        // Schreibweisen). VOID→push (neutral).
        const _normRes = (r) => {
          if (!r) return r;
          const u = String(r).toUpperCase();
          return u === 'WIN' ? 'won' : u === 'LOSS' ? 'lost'
               : (u === 'VOID' || u === 'PUSH') ? 'push' : String(r).toLowerCase();
        };
        const combined = [
          ...fxPicks.map(p  => ({ ...p, result: _normRes(p.result), _stake: _stakeOf(p), _isPlayer: false })),
          ...fxPPicks.map(p => ({ ...p, result: _normRes(p.result), _stake: _stakeOf(p), _isPlayer: true  })),
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

    // (25.06.2026, Lucas: KO-Runden) KO-Zeilen einbinden. Nur bothResolved (Teams
    // stehen fest). Picks unter "KO-{round}-{home}-{away}" — gleiche BET/ABWÄGEN/NOBET-
    // Behandlung wie Gruppenspiele. Team-Namen aus globaler Team-Union, da KO-Teams
    // aus beliebigen Gruppen kommen. Picks zählen normal mit, sobald WIN/LOSS.
    {
      const koFixtures = Array.isArray(_data.koFixtures) ? _data.koFixtures : [];
      if (koFixtures.length) {
        const teamUnion = {};
        for (const gData of Object.values(groups)) {
          for (const t of (gData.teams || [])) {
            if (!teamUnion[t.id]) teamUnion[t.id] = t;
          }
        }
        const _koGData = { name: 'K.O.-Runde', teams: Object.values(teamUnion) };
        const _normResKo = (r) => {
          if (!r) return r;
          const u = String(r).toUpperCase();
          return u === 'WIN' ? 'won' : u === 'LOSS' ? 'lost'
               : (u === 'VOID' || u === 'PUSH') ? 'push' : String(r).toLowerCase();
        };
        for (const kf of koFixtures) {
          if (!kf.bothResolved) continue;
          const pickKey = `KO-${kf.round}-${kf.home}-${kf.away}`;
          const fxPicks = allPicks[pickKey] || [];
          if (!fxPicks.length) continue;   // ohne Picks keine Tracking-Zeile
          const combined = fxPicks.map(p => ({
            ...p, result: _normResKo(p.result), _stake: _stakeOf(p), _isPlayer: false,
          }));
          const koDate = kf.date || (kf.kickoff ? String(kf.kickoff).slice(0, 10) : '');
          const isPast = koDate && koDate < todayIso;
          rows.push({
            fx: {
              home: kf.home, away: kf.away, round: kf.round,
              matchday: kf.round, kickoff: kf.kickoff, date: koDate,
              time: (kf.kickoff ? new Date(kf.kickoff).toTimeString().slice(0, 5) : ''),
              groupKey: 'KO', isKO: true,
            },
            gData: _koGData,
            homeTeam: teamUnion[kf.home] || { id: kf.home, name: kf.home, flag: '🏳' },
            awayTeam: teamUnion[kf.away] || { id: kf.away, name: kf.away, flag: '🏳' },
            picks:    combined,
            isLocked: isPast,
          });
        }
      }
    }

    // Sort by date → time → matchday (FIX 11.06.2026: Mitternachts-Umbruch,
    // 00:00 = spätes Nacht-Spiel, < 06:00 als +24h → nicht fälschlich zuerst)
    const _koKey = (t) => {
      if (!t || !/^\d{1,2}:\d{2}$/.test(t)) return 9999;
      const [h, m] = t.split(":").map(Number); const mins = h * 60 + m;
      return mins < 360 ? mins + 1440 : mins;
    };
    rows.sort((a, b) => {
      if (a.fx.date !== b.fx.date) return a.fx.date.localeCompare(b.fx.date);
      const ta = _koKey(a.fx.time), tb = _koKey(b.fx.time);
      if (ta !== tb)               return ta - tb;
      return a.fx.matchday - b.fx.matchday;
    });

    // ── Apply filters ─────────────────────────────────
    let filtered = rows;
    // (25.06.2026, Lucas: KO-Runden) Gruppen-Filter: KO-Zeilen haben keine Gruppe
    // → nur bei „alle Gruppen" zeigen, sonst rausfiltern (kein falsches Auftauchen).
    if (_grpFilter !== 'all') filtered = filtered.filter(r => !r.fx.isKO && r.fx.groupKey === _grpFilter);
    // (25.06.2026, Lucas: KO-Runden) String-Vergleich: numerische Spieltage UND
    // Runden-Codes (R32/R16/QF/SF) als _mdFilter.
    if (_mdFilter  !== 'all') filtered = filtered.filter(r => String(r.fx.matchday) === String(_mdFilter));

    // Flatten picks for filtered set (apply verdict filter)
    // FIX 11.06.2026: trackingExcluded raus (Cross-Market-Konflikte wie
    // CAN-BIH "AH Heim" neben "Auswärtssieg"). Das Tracking filterte nur nach
    // Verdict → der Konflikt-Pick blieb sichtbar.
    // FIX 21.06.2026 (Lucas, Single-Source): KEINE eigene Risky-Hero-Demotion mehr hier.
    // Die „riskante Variante → Beobachtungs-Spiel"-Entscheidung trifft AUSSCHLIESSLICH der
    // Engine (generate_wm_picks.py: stempelt trackingExcluded + demotedRiskyGame, INKL. der
    // Steam-Ausnahme bei sicher abgeleiteten Quoten). Cards (renderer.js) + Telegram vertrauen
    // exakt diesen Flags. Das Tracking re-derivte die Demotion vorher selbst — aber OHNE die
    // Steam-Ausnahme — und verbarg dadurch legitime Steam-Picks (z.B. ECU-CUW „AH Heim −1.5 @1.5"),
    // die in Telegram + Card sichtbar waren → Divergenz. trackingExcluded (unten) ist die
    // einzige Quelle. Tracking == Card == Telegram == Engine.
    const _ahGrp = (m) => { const x = /^(AH (?:Heim|Auswärts) [+−])/.exec(m || ''); return x ? x[1] : null; };
    const flatPicks = [];
    const nobetRows = [];   // 23.06.2026 (Lucas): NOBET separat — NIE in flatPicks/KPIs/P&L
    for (const row of filtered) {
      // AH-Linien-Dedup pro Spiel (14.06.2026): je Seite+Vorzeichen nur die beste Linie
      // (höchste Edge). „AH Auswärts +0.5" UND „+0.75" sind redundant — eine reicht.
      const _vr = (v) => v === 'BET' ? 0 : v === 'ABWÄGEN' ? 1 : v === 'BEOBACHTEN' ? 2 : 3;
      const ahBest = {};
      for (const p of row.picks) {
        if (p.trackingExcluded || p.boldAlt || p.verdict === 'SKIP') continue;
        const g = _ahGrp(p.market);
        if (!g) continue;
        const cur = ahBest[g];
        const better = !cur
          || _vr(p.verdict) < _vr(cur.verdict)
          || (_vr(p.verdict) === _vr(cur.verdict) && (p.edgePP || 0) > (cur.edgePP || 0));
        if (better) ahBest[g] = p;
      }
      for (const p of row.picks) {
        if (p.trackingExcluded) continue;
        if (p.boldAlt) continue;   // FIX 14.06.2026: durch sichere Variante ersetzt → nicht tracken
        if (p.verdict === 'NOBET') {   // kein Bet → eigener Abschnitt, NIE in KPIs/P&L/Win-Rate
          nobetRows.push({ ...p, _row: row });
          continue;
        }
        const g = _ahGrp(p.market);
        if (g && ahBest[g] && ahBest[g] !== p) continue;   // redundante AH-Linie
        if (_vrdFilter === 'all' || p.verdict === _vrdFilter) {
          flatPicks.push({ ...p, _row: row });
        }
      }
    }

    // Sortierung (11.06.2026): 'chrono' = nach Anpfiff (filtered ist schon
    // chronologisch sortiert → flatPicks-Reihenfolge passt). 'bet' = nach
    // Pick-Stärke (BET zuerst, dann Edge absteigend).
    if (_trkSort === 'bet') {
      const _vrank = v => (v === 'BET' ? 0 : v === 'ABWÄGEN' ? 1 : 2);
      flatPicks.sort((a, b) => {
        if (_vrank(a.verdict) !== _vrank(b.verdict)) return _vrank(a.verdict) - _vrank(b.verdict);
        return (b.edgePP || 0) - (a.edgePP || 0);
      });
    }

    // Top Picks = BET verdict
    const topPicks = flatPicks.filter(p => p.verdict === 'BET');

    // ─── Build HTML ────────────────────────────────────
    let html = '';

    // ─── Header ───────────────────────────────────────
    // (25.06.2026, Lucas: Liga auf WM-Stack) Neutraler Liga-Titel im liga-Modus.
    const _trkTitle = _isLiga ? '📊 Liga Tracking' : '📊 WM 2026 Tracking';
    html += `
    <div class="wm-header">
      <div class="wm-header-left">
        <div class="wm-title">${_trkTitle}</div>
        <div class="wm-subtitle">Alle Picks aus den Cards · Eingefroren bei Kickoff · BET €${STAKE_BET} · ABWÄGEN €${STAKE_ABW}</div>
      </div>
      <div class="wm-header-right">
        <button onclick="wmTrkRefresh()" style="background:var(--surface2);border:1px solid var(--border);color:var(--text);border-radius:6px;padding:5px 12px;font-size:11px;font-weight:600;cursor:pointer;">🔄 Aktualisieren</button>
      </div>
    </div>`;

    // ─── VALIDATION + AUDIT PILL ROW ──────────────────────
    html += _buildValidationRow();
    if (_showValidation) html += _buildValidationDetail();
    if (_showAudit)      html += _buildAuditDetail();

    // ─── HERO BLOCK — die EINE Zahl die alles erzählt ────
    html += _buildHeroBlock(flatPicks);

    // ─── EQUITY CURVE — Bankroll-Verlauf seit Start ───────
    html += _buildEquityCurve(flatPicks);

    // ─── Global KPI strip ─────────────────────────────
    html += _buildKpiStrip(flatPicks, 'Alle Picks');

    // ─── Filters ──────────────────────────────────────
    // Group filter
    html += `<div class="wm-group-filter" style="margin-top:12px;">`;
    html += _fBtn('⭐ Alle', 'all', _grpFilter, `wmTrkSetGroup('all')`);
    for (const gKey of groupKeys) {
      // (25.06.2026, Lucas: Liga auf WM-Stack) WM: „Gr. A"; Liga: Liga-FLAGGE + Kürzel (🏴 ENG).
      const label = (groups[gKey].name || 'Gruppe ?').replace('Gruppe ', '');
      const ligaLabel = `${groups[gKey].flag ? groups[gKey].flag + ' ' : ''}${gKey}`;
      html += _fBtn(_isLiga ? ligaLabel : `Gr. ${label}`, gKey, _grpFilter, `wmTrkSetGroup('${gKey}')`);
    }
    html += `</div>`;

    // Matchday filter
    html += `<div class="wm-md-filter">`;
    html += _fBtn('Alle Spieltage', 'all', _mdFilter, `wmTrkSetMd('all')`);
    if (_isLiga) {
      // (25.06.2026, Lucas: Liga auf WM-Stack) Spieltag-Buttons DYNAMISCH aus den
      // vorhandenen fixtures[].matchday-Werten (distinct, sortiert). Bei vielen Runden
      // auf die nächsten ~3 anstehenden begrenzen (analog Renderer). _fBtn vergleicht
      // strikt (=== val) → val als String + onclick wmTrkSetMd('<md>') (String-Filter).
      const _mdSet = new Set();
      for (const gData of Object.values(groups)) {
        for (const fx of (gData.fixtures || [])) {
          if (fx.matchday != null && fx.matchday !== '') _mdSet.add(fx.matchday);
        }
      }
      const _allMds = [..._mdSet].sort((a, b) =>
        (parseFloat(a) || 0) - (parseFloat(b) || 0) || String(a).localeCompare(String(b)));
      // (26.06.2026, Lucas) Spieltag freigeschaltet wenn Quoten da ODER innerhalb 2 Wochen
      // (analog Renderer) — sonst Navi mit allen ~38 Runden zugemüllt.
      const _odds = _data.odds || {};
      const _twoWeeks = new Date(Date.now() + 14 * 86400000).toISOString().slice(0, 10);
      const _liveMd = (md) => {
        for (const gData of Object.values(groups)) {
          for (const fx of (gData.fixtures || [])) {
            if (String(fx.matchday) !== String(md)) continue;
            if (_odds[`${fx.home}-${fx.away}`] || (fx.date >= todayIso && fx.date <= _twoWeeks)) return true;
          }
        }
        return false;
      };
      let _shownMds = _allMds.filter(_liveMd);
      if (!_shownMds.length) {
        const _next = _allMds.filter(md => {
          for (const gData of Object.values(groups))
            for (const fx of (gData.fixtures || []))
              if (String(fx.matchday) === String(md) && fx.date >= todayIso) return true;
          return false;
        });
        _shownMds = _next.slice(0, 1);
      }
      if (_mdFilter !== 'all' && !_shownMds.some(md => String(md) === String(_mdFilter))
          && _allMds.some(md => String(md) === String(_mdFilter))) {
        _shownMds = [..._shownMds, _mdFilter];
      }
      for (const md of _shownMds) {
        const _mdStr = String(md).replace(/['"\\]/g, '');
        html += _fBtn(`Spieltag ${md}`, _mdStr, String(_mdFilter), `wmTrkSetMd('${_mdStr}')`);
      }
    } else {
    html += _fBtn('Spieltag 1', 1,     _mdFilter, `wmTrkSetMd(1)`);
    html += _fBtn('Spieltag 2', 2,     _mdFilter, `wmTrkSetMd(2)`);
    html += _fBtn('Spieltag 3', 3,     _mdFilter, `wmTrkSetMd(3)`);
    // (25.06.2026, Lucas: KO-Runden) Runden-Buttons NUR für vorhandene Runden.
    {
      const _koRounds = new Set((Array.isArray(_data.koFixtures) ? _data.koFixtures : [])
        .filter(k => k.bothResolved).map(k => k.round));
      for (const r of KO_ROUND_ORDER) {
        if (!_koRounds.has(r)) continue;
        html += _fBtn(KO_ROUND_LABELS[r], r, _mdFilter, `wmTrkSetMd('${r}')`);
      }
    }
    }
    html += `</div>`;

    // Verdict filter
    html += `<div class="wm-trk-vrd-filter">`;
    const vrdOpts = [['all','Alle Verdicts','⭐'],['BET','BET','🟢'],['ABWÄGEN','ABWÄGEN','🟡'],['SKIP','SKIP','🔴']];
    for (const [val, lbl, ico] of vrdOpts) {
      const active = _vrdFilter === val;
      html += `<button class="wm-md-btn${active ? ' active' : ''}" onclick="wmTrkSetVerdict('${val}')">${ico} ${lbl}</button>`;
    }
    html += `</div>`;

    // Sortierung: chronologisch (Standard) vs nach Pick-Stärke (BET) — NEU 11.06.2026
    html += `<div class="wm-trk-vrd-filter" style="margin-top:6px;">`;
    html += `<span style="font-size:11px;color:var(--muted);align-self:center;margin-right:4px;">Sortierung:</span>`;
    for (const [val, lbl, ico] of [['chrono','Chronologisch','📅'],['bet','Nach Pick-Stärke','🟢']]) {
      const active = _trkSort === val;
      html += `<button class="wm-md-btn${active ? ' active' : ''}" onclick="wmTrkSetSort('${val}')">${ico} ${lbl}</button>`;
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

    // ─── NOBET — gesehen, aber kein Bet (kein KPI/P&L-Einfluss) ───────────
    html += _buildNobetSection(nobetRows);

    panel.innerHTML = html;
  }

  // NOBET-Abschnitt (23.06.2026, Lucas): Picks die mal BET/ABWÄGEN waren und deren Value gekippt
  // ist. Rein informativ mit Grund + grauem Schatten-Resultat — NICHT in KPIs/Win-Rate/P&L.
  function _buildNobetSection(rows) {
    if (!rows || !rows.length) return '';
    const _shadow = (r) => {
      const s = String(r.shadowResult || '').toUpperCase();
      if (s === 'WIN')  return '<span style="color:#3fb950">✅ hätte gewonnen</span>';
      if (s === 'LOSS') return '<span style="color:#f85149">❌ hätte verloren</span>';
      if (s === 'VOID') return '<span style="color:#8b949e">➖ Push</span>';
      return '<span style="color:#76819c">offen</span>';
    };
    let html = `
      <div class="wm-trk-section-title" style="margin-top:18px;color:#76819c;">
        🚫 Kein Bet — gesehen, aber kein Value
        <span class="wm-trk-count">${rows.length}</span>
      </div>
      <div style="font-size:11px;color:#76819c;margin:0 0 8px;">War mal BET/ABWÄGEN, Edge dann gekippt. Schatten-Ergebnis rein informativ — zählt nicht in Quote/P&L.</div>
      <div style="display:flex;flex-direction:column;gap:6px;opacity:.85">`;
    for (const r of rows) {
      const fx = r._row && r._row.fx ? r._row.fx : {};
      const match = `${fx.home || ''}–${fx.away || ''}`;
      const _o = r.origOdds != null ? `@${(+r.origOdds).toFixed(2)}` : (r.odds != null ? `@${(+r.odds).toFixed(2)}` : '');
      html += `
        <div style="display:grid;grid-template-columns:1fr auto;gap:10px;align-items:center;background:rgba(118,129,156,.08);border:1px solid rgba(118,129,156,.2);border-radius:10px;padding:9px 12px">
          <div style="min-width:0">
            <div style="font-size:13px;color:#c9d2e3"><span style="color:#76819c;font-weight:700">NOBET</span> · ${r.market || ''} ${_o ? `<span style="color:#76819c">${_o}</span>` : ''}</div>
            <div style="font-size:11px;color:#76819c;margin-top:2px;overflow:hidden;text-overflow:ellipsis">${match}${r.nobetReason ? ' · ' + r.nobetReason : ''}</div>
          </div>
          <div style="font-size:12px;white-space:nowrap">${_shadow(r)}</div>
        </div>`;
    }
    html += `</div>`;
    return html;
  }

  // ─────────────────────────────────────────────────────
  //  VALIDATION-ROW — Pill mit Validator + Audit-Button
  // ─────────────────────────────────────────────────────
  function _buildValidationRow() {
    const rep = _validationReport;
    let valPill;
    if (!rep) {
      valPill = `<div class="wm-trk-pill wm-trk-pill-muted">🔍 Validation läuft noch nicht — nach nächstem Pipeline-Run verfügbar</div>`;
    } else {
      const s = rep.stats || {};
      if (s.errors > 0) {
        valPill = `<div class="wm-trk-pill wm-trk-pill-err" onclick="wmTrkToggleVal()">
          ❌ <b>${s.errors} Fehler</b> in ${s.total} Picks · klick für Details</div>`;
      } else if (s.warnings > 0) {
        valPill = `<div class="wm-trk-pill wm-trk-pill-warn" onclick="wmTrkToggleVal()">
          ⚠️ ${s.total} Picks geprüft · <b>${s.warnings} Warnungen</b> · klick für Details</div>`;
      } else {
        valPill = `<div class="wm-trk-pill wm-trk-pill-ok" onclick="wmTrkToggleVal()">
          ✅ <b>${s.total} Picks geprüft · 0 Fehler</b> · klick für Details</div>`;
      }
    }
    return `<div class="wm-trk-val-row">
      ${valPill}
      <button class="wm-trk-audit-btn" onclick="wmTrkRunAudit()" title="Vergleicht Tracking-Picks mit dem was in den WM-Cards angezeigt wird">
        🔎 Card-Audit ausführen
      </button>
    </div>`;
  }

  function _buildValidationDetail() {
    const rep = _validationReport;
    if (!rep) return '';
    const issues = rep.issues || [];
    if (!issues.length) {
      return `<div class="wm-trk-val-detail">
        <div style="text-align:center;padding:16px;color:var(--muted);font-size:12px;">
          ✅ Alle ${rep.stats.total} Picks bestehen alle Sanity-Checks.
        </div>
        <button onclick="wmTrkToggleVal()" class="wm-trk-close">▲ Schließen</button>
      </div>`;
    }
    // Gruppiere nach Severity
    const byLvl = { error: [], warning: [], info: [] };
    for (const i of issues) (byLvl[i.level] || byLvl.warning).push(i);

    let html = `<div class="wm-trk-val-detail">`;
    for (const lvl of ['error', 'warning', 'info']) {
      if (!byLvl[lvl].length) continue;
      const icon = lvl === 'error' ? '❌' : lvl === 'warning' ? '⚠️' : 'ℹ️';
      const label = lvl === 'error' ? 'Fehler' : lvl === 'warning' ? 'Warnungen' : 'Hinweise';
      html += `<div class="wm-trk-val-group wm-trk-val-${lvl}">
        <div class="wm-trk-val-group-head">${icon} ${byLvl[lvl].length} ${label}</div>`;
      for (const i of byLvl[lvl]) {
        html += `<div class="wm-trk-val-issue">
          <div class="wm-trk-val-issue-head">
            <span class="wm-trk-val-code">${i.code}</span>
            <span class="wm-trk-val-mk">${i.matchKey}</span>
            <span class="wm-trk-val-market">${i.market}</span>
          </div>
          <div class="wm-trk-val-msg">${i.message}</div>
        </div>`;
      }
      html += `</div>`;
    }
    html += `<button onclick="wmTrkToggleVal()" class="wm-trk-close">▲ Schließen</button>`;
    html += `</div>`;
    return html;
  }

  function _buildAuditDetail() {
    const r = _auditReport;
    if (!r) return '';
    const status = r.mismatches.length === 0
      ? `<div class="wm-trk-pill wm-trk-pill-ok" style="cursor:default;">✅ Alle ${r.checked} Card-Hero-Picks 1:1 im Tracking gefunden</div>`
      : `<div class="wm-trk-pill wm-trk-pill-err" style="cursor:default;">❌ ${r.mismatches.length} Abweichungen von ${r.checked} geprüften Match-Cards</div>`;
    let html = `<div class="wm-trk-val-detail">
      <div style="margin-bottom:10px;">${status}</div>`;
    if (r.mismatches.length) {
      html += `<div class="wm-trk-val-group wm-trk-val-error">
        <div class="wm-trk-val-group-head">❌ Abweichungen Cards vs Tracking</div>`;
      for (const m of r.mismatches) {
        html += `<div class="wm-trk-val-issue">
          <div class="wm-trk-val-issue-head">
            <span class="wm-trk-val-mk">${m.matchKey}</span>
            <span class="wm-trk-val-market">${m.market || '—'}</span>
          </div>
          <div class="wm-trk-val-msg">${m.reason}</div>
        </div>`;
      }
      html += `</div>`;
    } else {
      html += `<div style="text-align:center;padding:14px;color:var(--muted);font-size:11.5px;">
        Jeder Card-Hero-Pick (BET/ABWÄGEN) wurde im Tracking-Listing gefunden.
        Es gibt KEINEN Render-Drift — Tracking und Cards lesen aus derselben Source.
      </div>`;
    }
    html += `<button onclick="wmTrkCloseAudit()" class="wm-trk-close">▲ Schließen</button>`;
    html += `</div>`;
    return html;
  }

  // ─────────────────────────────────────────────────────
  //  AUDIT — Card-Hero-Picks 1:1 im Tracking?
  //  Repliziert exakt die Filter-Logik aus wm2026-renderer.js
  // ─────────────────────────────────────────────────────
  function _runCardTrackingAudit() {
    const allPicks = _data.picks || {};
    const groups   = _data.groups || {};
    let checked = 0;
    const mismatches = [];

    for (const [gKey, gData] of Object.entries(groups)) {
      for (const fx of (gData.fixtures || [])) {
        const mk = `${gKey}-${fx.matchday}-${fx.home}-${fx.away}`;
        const all = allPicks[mk] || [];
        // Card-Logik replizieren: BET/ABWÄGEN, sortiert (trackingExcluded raus — FIX 11.06.2026)
        const live = all.filter(p => (p.verdict === 'BET' || p.verdict === 'ABWÄGEN') && !p.trackingExcluded);
        const sorted = [...live].sort((a, b) => {
          if (a.verdict === 'BET' && b.verdict !== 'BET') return -1;
          if (b.verdict === 'BET' && a.verdict !== 'BET') return 1;
          return (b.edgePP || 0) - (a.edgePP || 0);
        });
        const heroPick = sorted[0] || null;
        if (!heroPick) continue;   // Match ohne Hero — kein Audit nötig
        checked++;
        // Identitäts-Match: gleicher Pick im Tracking-Listing (allPicks)?
        const found = all.find(p =>
          p.market === heroPick.market &&
          p.verdict === heroPick.verdict &&
          Math.abs((p.odds || 0) - (heroPick.odds || 0)) < 0.005
        );
        if (!found) {
          mismatches.push({
            matchKey: mk,
            market: heroPick.market,
            reason: `Hero-Pick aus Card nicht im Tracking-Listing gefunden (Market: ${heroPick.market} @${heroPick.odds})`,
          });
        }
      }
    }
    return { checked, mismatches, runAt: new Date().toISOString() };
  }

  // ─────────────────────────────────────────────────────
  //  KPI-Math als Shared-Helper (Hero + Strip + Card teilen ihn)
  // ─────────────────────────────────────────────────────
  function _computeKpis(picks) {
    const resolved = picks.filter(p => p.result != null);
    const won      = resolved.filter(p => p.result === 'won');
    const lost     = resolved.filter(p => p.result === 'lost');
    const push     = resolved.filter(p => p.result === 'push');
    const decided  = resolved.length - push.length;

    const winRate = decided > 0 ? Math.round(won.length / decided * 100) : null;
    const avgOdds = resolved.length > 0
      ? +(resolved.reduce((s, p) => s + (p.odds || 1), 0) / resolved.length).toFixed(2)
      : null;

    let pnl = null, roi = null;
    if (resolved.length > 0) {
      // resultStakeFactor (13.06.2026): 0.5 bei AH-Viertel-Linien-Halb-Ergebnis
      // (halber Stake gewinnt/verliert, Rest Push). Wirkt nur auf die P&L-Beiträge,
      // NICHT auf den staked-Nenner (voller Einsatz wurde riskiert).
      pnl = +(won.reduce((s, p) => s + ((p.odds || 1) - 1) * p._stake * (p.resultStakeFactor || 1), 0)
            - lost.reduce((s, p) => s + p._stake * (p.resultStakeFactor || 1), 0)).toFixed(2);
      const _staked = resolved.reduce((s, p) => s + p._stake, 0);
      roi = _staked > 0 ? +(pnl / _staked * 100).toFixed(1) : null;
    }

    // Avg CLV — pro-Pick CLV in pp, gewichtet nur über resolved (sonst statistisch zappelig)
    const clvPicks = resolved.filter(p => typeof p.clvPP === 'number');
    const avgClv = clvPicks.length > 0
      ? +(clvPicks.reduce((s, p) => s + p.clvPP, 0) / clvPicks.length).toFixed(1)
      : null;

    return {
      total: picks.length,
      bet:   picks.filter(p => p.verdict === 'BET').length,
      pending: picks.length - resolved.length,
      resolved: resolved.length,
      won:   won.length,
      lost:  lost.length,
      push:  push.length,
      winRate, avgOdds, pnl, roi, avgClv,
    };
  }

  // ─────────────────────────────────────────────────────
  //  HERO BLOCK — die EINE Zahl die Vertrauen erzeugt
  // ─────────────────────────────────────────────────────
  function _buildHeroBlock(picks) {
    const k = _computeKpis(picks);
    const isLive = k.resolved > 0;

    if (!isLive) {
      // Pre-WM-State: zeige "Bereit für ST1" statt leere KPIs
      return `<div class="wm-trk-hero wm-trk-hero-pending">
        <div class="wm-trk-hero-row">
          <div class="wm-trk-hero-side">
            <div class="wm-trk-hero-mini-num">${k.total}</div>
            <div class="wm-trk-hero-mini-lbl">Picks bereit</div>
          </div>
          <div class="wm-trk-hero-center">
            <div class="wm-trk-hero-pending-icon">⏳</div>
            <div class="wm-trk-hero-pending-txt">Track-Record startet mit Spieltag 1</div>
            <div class="wm-trk-hero-pending-sub">${k.bet} BET · ${k.total - k.bet} ABWÄGEN — eingefroren bei Kickoff</div>
          </div>
          <div class="wm-trk-hero-side">
            <div class="wm-trk-hero-mini-num">11.06.</div>
            <div class="wm-trk-hero-mini-lbl">Anpfiff</div>
          </div>
        </div>
      </div>`;
    }

    const roiSign  = k.roi >= 0 ? '+' : '';
    const roiCls   = k.roi >= 0 ? 'wm-trk-hero-pos' : 'wm-trk-hero-neg';
    const clvSign  = k.avgClv != null && k.avgClv >= 0 ? '+' : '';
    const clvVal   = k.avgClv != null ? `${clvSign}${k.avgClv}pp` : '—';
    const clvCls   = k.avgClv != null ? (k.avgClv >= 0 ? 'wm-trk-hero-pos' : 'wm-trk-hero-neg') : '';
    const hitRate  = k.winRate != null ? `${k.winRate}%` : '—';

    return `<div class="wm-trk-hero ${roiCls}">
      <div class="wm-trk-hero-row">
        <div class="wm-trk-hero-side">
          <div class="wm-trk-hero-mini-num">${hitRate}</div>
          <div class="wm-trk-hero-mini-lbl">Trefferquote · ${k.won}/${k.resolved - k.push}</div>
        </div>
        <div class="wm-trk-hero-center">
          <div class="wm-trk-hero-label">Return on Investment</div>
          <div class="wm-trk-hero-num">${roiSign}${k.roi}%</div>
          <div class="wm-trk-hero-sub">${k.pnl >= 0 ? '+' : '−'}€${Math.abs(k.pnl).toFixed(2)} · BET €${STAKE_BET}/ABWÄGEN €${STAKE_ABW} · ${k.resolved} resolvierte</div>
        </div>
        <div class="wm-trk-hero-side">
          <div class="wm-trk-hero-mini-num ${clvCls}">${clvVal}</div>
          <div class="wm-trk-hero-mini-lbl">Ø CLV · n=${k.resolved}</div>
        </div>
      </div>
    </div>`;
  }

  // ─────────────────────────────────────────────────────
  //  EQUITY CURVE — kumulatives P&L pro resolvierten Pick
  // ─────────────────────────────────────────────────────
  function _buildEquityCurve(picks) {
    const resolved = picks.filter(p => p.result != null);
    if (resolved.length === 0) {
      return `<div class="wm-trk-curve wm-trk-curve-empty">
        <span style="color:var(--muted);font-size:11px;letter-spacing:.5px;">📈 Bankroll-Verlauf — Erste Resultate ab 11. Juni</span>
      </div>`;
    }

    // Sortiere chronologisch nach kickoff (fx date + time)
    const sortable = resolved.map(p => ({
      pick: p,
      ts: `${p._row?.fx?.date || '9999-99-99'}T${p._row?.fx?.time || '23:59'}`,
    })).sort((a, b) => a.ts.localeCompare(b.ts));

    // Kumuliere PnL Pick für Pick
    let cum = 0;
    const points = [{ x: 0, y: 0, pnl: 0 }];   // Startpunkt
    sortable.forEach((s, i) => {
      const p = s.pick;
      let delta = 0;
      if (p.result === 'won')  delta = ((p.odds || 1) - 1) * p._stake;
      else if (p.result === 'lost') delta = -p._stake;
      cum += delta;
      points.push({ x: i + 1, y: cum, pnl: cum, market: p.market, result: p.result, odds: p.odds });
    });

    const n = points.length;
    const W = 800, H = 140, padL = 40, padR = 30, padT = 12, padB = 24;
    const minY = Math.min(0, ...points.map(p => p.y));
    const maxY = Math.max(0, ...points.map(p => p.y));
    const rangeY = (maxY - minY) || 1;

    const xPos = i => padL + (i / Math.max(1, n - 1)) * (W - padL - padR);
    const yPos = v => padT + (1 - (v - minY) / rangeY) * (H - padT - padB);

    const linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${xPos(i).toFixed(1)} ${yPos(p.y).toFixed(1)}`).join(' ');
    const areaPath = `${linePath} L ${xPos(n - 1).toFixed(1)} ${yPos(0).toFixed(1)} L ${xPos(0).toFixed(1)} ${yPos(0).toFixed(1)} Z`;
    const isPositive = cum >= 0;
    const color = isPositive ? '#3fb950' : '#f85149';

    // Zero-Line nur wenn 0 im Range
    const zeroY = yPos(0);
    const zeroLine = (minY <= 0 && maxY >= 0)
      ? `<line x1="${padL}" y1="${zeroY.toFixed(1)}" x2="${W - padR}" y2="${zeroY.toFixed(1)}" stroke="rgba(255,255,255,0.12)" stroke-dasharray="3,3" stroke-width="1"/>`
      : '';

    // Last point + label
    const lastX = xPos(n - 1);
    const lastY = yPos(cum);
    const sign = cum >= 0 ? '+' : '−';
    const labelTxt = `${sign}€${Math.abs(cum).toFixed(2)}`;

    return `<div class="wm-trk-curve">
      <div class="wm-trk-curve-head">
        <span class="wm-trk-curve-title">📈 Bankroll-Verlauf · BET €${STAKE_BET}/ABWÄGEN €${STAKE_ABW}</span>
        <span class="wm-trk-curve-sub">${resolved.length} resolvierte Picks</span>
      </div>
      <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" class="wm-trk-curve-svg">
        <defs>
          <linearGradient id="trkCurveGrad" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stop-color="${color}" stop-opacity="0.30"/>
            <stop offset="100%" stop-color="${color}" stop-opacity="0"/>
          </linearGradient>
        </defs>
        ${zeroLine}
        <path d="${areaPath}" fill="url(#trkCurveGrad)"/>
        <path d="${linePath}" stroke="${color}" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
        <circle cx="${lastX.toFixed(1)}" cy="${lastY.toFixed(1)}" r="4" fill="${color}"/>
        <text x="${lastX.toFixed(1)}" y="${(lastY - 8).toFixed(1)}" text-anchor="end" fill="${color}" font-size="13" font-weight="800" font-family="-apple-system,sans-serif">${labelTxt}</text>
      </svg>
    </div>`;
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
      pnl = won.reduce((s, p) => s + ((p.odds || 1) - 1) * p._stake, 0)
          - lost.reduce((s, p) => s + p._stake, 0);
      pnl = Math.round(pnl * 100) / 100;
    }

    // ROI = P&L / (Summe gestakter € auf resolved) * 100
    let roi = null;
    const _staked = resolved.reduce((s, p) => s + p._stake, 0);
    if (_staked > 0) {
      roi = Math.round(pnl / _staked * 100);
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
      ${(() => {
        const clvPicks = resolved.filter(p => typeof p.clvPP === 'number');
        if (!clvPicks.length) return _kpi('Ø CLV', '—', 'var(--muted)');
        const avg = +(clvPicks.reduce((s, p) => s + p.clvPP, 0) / clvPicks.length).toFixed(1);
        const sign = avg >= 0 ? '+' : '';
        const col = avg >= 0 ? '#3fb950' : '#f85149';
        return _kpi('Ø CLV', `${sign}${avg}pp`, col);
      })()}
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

    // FIX 14.06.2026: Sterne aus dem VERDICT (nicht aus conf/Datenqualität) — sonst stand
    // ein ★★★-ABWÄGEN über einem ★★☆-BET (Lucas). Jetzt: BET ★★★ ≥ ABWÄGEN ★★☆ > Rest.
    const stars    = verdict === 'BET' ? '★★★' : verdict === 'ABWÄGEN' ? '★★☆' : '★☆☆';
    const starsClr = verdict === 'BET' ? '#3fb950' : verdict === 'ABWÄGEN' ? '#e3b341' : '#8b949e';

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
    if (p.result === 'won')  pnlStr = `<span style="color:#3fb950;font-size:10px;font-weight:700;">+€${(((p.odds||1)-1)*p._stake).toFixed(2)}</span>`;
    if (p.result === 'lost') pnlStr = `<span style="color:#f85149;font-size:10px;font-weight:700;">-€${p._stake.toFixed(2)}</span>`;
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
