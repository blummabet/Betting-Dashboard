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

  // ── Modus-Parametrisierung (25.06.2026, Lucas: Liga auf WM-Stack) ──────
  // Gleicher Renderer bedient WM (International-Cards) UND Liga (National-Cards).
  // Defaults = WM, damit initIntlCards() exakt wie bisher läuft. initNationalCards()
  // überschreibt _dataFile/_cardsPanelId/_mode → liest liga-data.json ins Panel
  // mainContent und blendet WM-only-UI (Countdown/Spieltag-1-3/KO/Quali) aus.
  let _dataFile     = 'wm2026-data.json';
  let _cardsPanelId = 'intlCardsPanel';
  let _mode         = 'wm';   // 'wm' | 'liga'

  // 19.07.2026 (Lucas: „MLS-Event-Pages komplett leer") — die Match-Page-JSONs schreibt
  // generate_wm_match_pages mit dem DATENSATZ-Prefix (mls-{id}-vs-{id}-{date}). MLS rendert aber
  // unter _mode='liga', also baute das Frontend `liga-…` → 404 → leere Event-Page. Fixture-Gruppe
  // 'MLS' unterscheidet MLS von den Top-5-Ligen. Top-5 unverändert (liga-), WM unverändert (wm-).
  function _mpPrefix(fx) {
    if (fx && (fx.groupKey === 'MLS' || fx.group === 'MLS')) return 'mls';
    return _mode === 'liga' ? 'liga' : 'wm';
  }

  // (20.07.2026) Anstehende Spieltage EINER Gruppe — Kern des „MLS zeigt Spieltag 1"-Bugs:
  // die Filterleiste darf nur Fixtures der aktiven Gruppe sehen, sonst erbt die MLS die Top-5-
  // Spieltage (deren Saison noch nicht läuft → md 1), obwohl die MLS längst bei md 18 steht.
  // Rein/testbar. activeGroup==='all' → gemischt (bewusst, „Alle Ligen"-Ansicht).
  function _upcomingMdsForScope(allFx, activeGroup, todayIso) {
    const scope = activeGroup === 'all' ? allFx : allFx.filter(fx => fx.groupKey === activeGroup);
    const mds = [...new Set(scope
      .filter(fx => fx.matchday != null && fx.matchday !== '')
      .map(fx => fx.matchday))]
      .sort((a, b) => (parseFloat(a) || 0) - (parseFloat(b) || 0) || String(a).localeCompare(String(b)));
    return mds.filter(md => scope.some(fx => String(fx.matchday) === String(md) && fx.date >= todayIso));
  }

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
  let _activeSort     = 'date';  // 'date' | 'conviction' | 'signals'
  let _curatedExpanded = false;  // 28.06.2026 (Lucas): in der kuratierten Liga-Ansicht „mehr" aufgeklappt?
  let _showPast       = false;   // 17.06.2026: vergangene/gespielte Spiele default ausgeblendet (weniger Scrollen)
  let _loaded         = false;
  let _lastLoadTs     = 0;       // Timestamp des letzten erfolgreichen Loads (ms)
  let _loadedFile     = null;    // welches Dataset zuletzt geladen wurde (25.06.2026, Lucas:
                                 // Cache-Invalidierung bei Wechsel WM↔Liga, sonst zeigt National
                                 // die noch geladenen WM-Daten unter dem Liga-Header)

  // TTL für In-Memory-Cache. Tab-Wechsel innerhalb dieses Fensters → kein Re-Fetch
  // (schnell). Danach: silent re-fetch im Hintergrund mit alten Karten sichtbar,
  // damit Picks nach jedem 4h-Cron-Update spätestens 5 Min später frisch sind.
  // Picks werden nur 5×/Tag (alle 4h) im Workflow neu generiert, ein 5-Min-TTL
  // ist also conservatively kurz und liefert ein gutes Verhältnis aus Frische
  // und Bandbreiten-Sparsamkeit.
  const CARDS_CACHE_TTL_MS = 5 * 60 * 1000;

  const CO_HOSTS = new Set(['MEX', 'USA', 'CAN']);

  // (25.06.2026, Lucas: KO-Runden) Reihenfolge + deutsche Labels für die KO-Phase.
  // Quelle bleibt wm["koFixtures"] (Backend-Resolver) — hier nur Anzeige.
  const KO_ROUND_ORDER  = ['R32', 'R16', 'QF', 'SF', '3RD', 'F'];
  const KO_ROUND_LABELS = { R32: 'Sechzehntelfinale', R16: 'Achtelfinale', QF: 'Viertelfinale', SF: 'Halbfinale', '3RD': 'Spiel um Platz 3', F: 'Finale' };

  // ─────────────────────────────────────────────────────
  //  ENTRY POINT
  // ─────────────────────────────────────────────────────
  window.initIntlCards = async function () {
    // WM-Defaults (25.06.2026, Lucas: Liga auf WM-Stack) — Verhalten unverändert.
    _dataFile     = 'wm2026-data.json';
    _cardsPanelId = 'intlCardsPanel';
    _mode         = 'wm';
    return _loadCards();
  };

  // (25.06.2026, Lucas: Liga auf WM-Stack) National-Cards auf dem WM-Renderer.
  // Liest liga-data.json (WM-Format, Liga=„Gruppe") ins Panel mainContent.
  // Im liga-Modus werden die WM-Sibling-Fetches (poly/travel/confidence/player-picks/
  // odds-history/match-pages) NICHT geladen — nur liga-data.json. Die WM-only-UI
  // (Countdown, Spieltag-1-3-Buttons, KO/Quali) wird in _render() ausgeblendet.
  window.initNationalCards = async function () {
    _dataFile     = 'liga-data.json';
    _cardsPanelId = 'mainContent';
    _mode         = 'liga';
    return _loadCards();
  };

  // 29.08.2026 (Lucas: „wenn es verbessert, zieh's nach"): Die Daten kamen bisher relativ, also
  // aus dem GitHub-Pages-Snapshot. Der wird seit der Umstellung stuendlich neu veroeffentlicht —
  // die Fetcher committen aber alle paar Minuten. Folge: die Cards zeigten bis zu eine Stunde
  // alte Picks und Ergebnisse, waehrend die Uebersicht daneben (main-dashboard.js) auf EXAKT
  // denselben Dateien (liga-data.json, mls-data.json) schon raw-frisch war. Ein Datensatz, zwei
  // Staende, je nachdem welchen Tab man offen hatte.
  // Reihenfolge wie in main-dashboard.js / status-checks.js: raw/main zuerst (commit-frisch),
  // Pages-Snapshot nur als Rueckfall — sonst waere eine raw-Stoerung ein Totalausfall statt
  // einer Verzoegerung, und offline (PWA/Service-Worker) ginge gar nichts mehr.
  const _RAW_BASE = 'https://raw.githubusercontent.com/blummabet/Betting-Dashboard/main';
  async function _rawFirst(datei) {
    const t = Date.now();
    try {
      const r = await fetch(`${_RAW_BASE}/${datei}?t=${t}`, { cache: 'no-store' });
      if (r.ok) return await r.json();
    } catch (e) { /* raw nicht erreichbar -> Snapshot */ }
    try {
      const r = await fetch(`${datei}?t=${t}`, { cache: 'no-store' });
      if (r.ok) return await r.json();
    } catch (e) { /* offline oder kaputtes JSON -> null */ }
    return null;
  }

  // ─────────────────────────────────────────────────────
  //  SERIEN / STREAKS (28.06.2026, Lucas) — Content-Schicht, KEINE Quoten/€ (TikTok-safe).
  //  Liest {wm_,liga_}streaks.json (compute_streaks.py). Eigener Tab + Top-Sektion in den Cards.
  // ─────────────────────────────────────────────────────
  const _streaksCache   = {};   // 'liga'|'wm' → data
  const _streaksLoading = {};
  function _loadStreaks(isLiga) {
    const ds = isLiga ? 'liga' : 'wm';
    if (_streaksCache[ds]) return Promise.resolve(_streaksCache[ds]);
    const f = isLiga ? 'liga_streaks.json' : 'wm_streaks.json';
    const main = _rawFirst(f);
    // 29.06.2026 (Lucas: MLS): im National-Modus MLS-Serien mit-laden + zusammenführen.
    const extra = isLiga ? _rawFirst('mls_streaks.json') : Promise.resolve(null);
    return Promise.all([main, extra]).then(([j, m]) => {
      const streaks = ((j && j.streaks) || []).concat((m && m.streaks) || []);
      _streaksCache[ds] = { streaks };
      return _streaksCache[ds];
    });
  }
  // Beim Cards-Render einmalig nachladen, dann genau einmal neu zeichnen (Top-Serien-Sektion).
  function _ensureStreaks(isLiga, rerender) {
    const ds = isLiga ? 'liga' : 'wm';
    if (_streaksCache[ds] || _streaksLoading[ds]) return;
    _streaksLoading[ds] = true;
    _loadStreaks(isLiga).finally(() => { _streaksLoading[ds] = false; if (rerender) rerender(); });
  }

  const _STREAK_ICON = { over25: '⚽', under25: '🧱', bttsYes: '🤝', bttsNo: '🚫',
                         cornersOver: '🚩', cornersUnder: '🚩', scored: '🎯', cleanSheet: '🛡️', cards: '🟨' };
  const _STREAK_CONT = {
    intakt:  { col: '#3fb950', label: 'Serie intakt' },
    neutral: { col: '#8b949e', label: 'offen' },
    wackelt: { col: '#e3b341', label: 'wackelt' },
  };
  // venue-Suffix + komplementäre Gegner-Metrik (für nächstes Spiel).
  const _VENUE_LABEL = { H: 'Heim', A: 'Auswärts' };
  const _OPP_METRIC = { over25: 'Über', under25: 'Über', bttsYes: 'BTTS', bttsNo: 'BTTS',
                        cornersOver: 'Ecken', cornersUnder: 'Ecken', cards: 'Karten',
                        scored: 'kassiert', cleanSheet: 'trifft' };
  function _streakShortDate(iso) {
    if (!iso) return '';
    const p = String(iso).slice(0, 10).split('-');
    return p.length === 3 ? `${p[2]}.${p[1]}.` : '';
  }
  // Nächstes-Spiel-Block (adamchoi-Paarung): Gegner prominent (Wappen + Name) + Datum + Gegner-Rate-Chip.
  function _streakNextHtml(s) {
    const nx = s.next;
    if (!nx) return '';
    const vs = nx.atHome ? 'vs' : '@';
    const opp = nx.oppName || nx.oppId || '?';
    const dt = _streakShortDate(nx.date);
    const crest = nx.oppId ? `https://media.api-sports.io/football/teams/${nx.oppId}.png` : '';
    let oppChip = '';
    if (nx.oppRatePct != null) {
      oppChip = `<span style="display:inline-block;background:var(--border);color:var(--muted);border-radius:6px;padding:1px 7px;font-size:10px;font-weight:700;white-space:nowrap;">Gegner ${nx.oppRatePct}% ${_OPP_METRIC[s.type] || ''}</span>`;
    }
    return `<div style="display:flex;align-items:center;flex-wrap:wrap;gap:6px;margin-top:7px;padding-top:7px;border-top:1px dashed var(--border);">
      <span style="font-size:11px;color:var(--muted);font-weight:600;">⏭ Nächstes ${vs}</span>
      ${crest ? `<img src="${crest}" style="width:18px;height:18px;object-fit:contain;" loading="lazy" alt="">` : ''}
      <span style="font-size:13.5px;font-weight:800;color:var(--text);">${opp}</span>
      ${dt ? `<span style="font-size:11px;color:var(--muted);">· ${dt}</span>` : ''}
      ${oppChip}
    </div>`;
  }
  // Farbe nach Stütz-Stärke (gleiche Schwellen wie der Status): ≥60 grün, ≤45 amber, sonst grau.
  function _rateColor(pct) {
    if (pct == null) return _STREAK_CONT.neutral.col;
    if (pct >= 60) return _STREAK_CONT.intakt.col;
    if (pct <= 45) return _STREAK_CONT.wackelt.col;
    return _STREAK_CONT.neutral.col;
  }
  // Beschrifteter Mini-%-Balken (Eigentendenz bzw. Gegner).
  function _miniBar(label, pct, col) {
    return `<div style="margin-bottom:7px;">
      <div style="display:flex;justify-content:space-between;align-items:baseline;font-size:10px;line-height:1;">
        <span style="color:var(--muted);">${label}</span>
        <span style="font-weight:800;color:${col};">${pct}%</span>
      </div>
      <div style="height:5px;background:var(--border);border-radius:99px;margin-top:3px;overflow:hidden;">
        <div style="height:100%;width:${Math.max(0, Math.min(100, pct))}%;background:${col};border-radius:99px;"></div>
      </div>
    </div>`;
  }
  // Sequenz-Punkte: macht den Lauf sichtbar (●●●●○ = Treffer/kein Treffer). seq ist most-recent-first;
  // wir zeigen chronologisch (alt→neu, links→rechts), damit die aktuelle Serie rechts „andockt".
  function _streakDotsHtml(seq, col) {
    if (!seq || !seq.length) return '';
    const dots = seq.slice().reverse().map(hit =>
      `<span style="color:${hit ? col : 'var(--border)'};">●</span>`).join('');
    return `<span style="font-size:9px;letter-spacing:1.5px;white-space:nowrap;vertical-align:middle;">${dots}</span>`;
  }
  // Signal-Indikator fürs nächste Spiel (Stufe 2): zeigt, ob die Engine-Signale die Serie
  // bestätigen oder ihr widersprechen (29.06.2026, Lucas: „sehen ob wirklich was feuert").
  function _streakSignalHtml(s) {
    const si = s.signalInfo;
    if (!si) return '';
    const confirm = si.state === 'confirm';
    const col = confirm ? _STREAK_CONT.intakt.col : _STREAK_CONT.wackelt.col;
    const ic = confirm ? '📡' : '⚠️';
    const verb = confirm ? 'bestätigen' : 'dagegen';
    const meta = (typeof _SIG_META !== 'undefined') ? _SIG_META : {};
    const chips = (si.names || []).slice(0, 4).map(n => {
      const m = meta[n] || ['•', n];
      return `<span style="font-size:10px;color:var(--muted);white-space:nowrap;">${m[0]} ${m[1]}</span>`;
    }).join(' ');
    return `<div style="display:flex;align-items:center;flex-wrap:wrap;gap:7px;margin-top:6px;">
      <span style="background:${col}1f;color:${col};border:1px solid ${col}66;border-radius:6px;padding:1px 7px;font-size:10px;font-weight:800;white-space:nowrap;">${ic} ${si.count} Signal${si.count === 1 ? '' : 'e'} ${verb}</span>
      ${chips}
    </div>`;
  }
  function _streakRowHtml(s) {
    const ic = _STREAK_ICON[s.type] || '🔥';
    const c = _STREAK_CONT[(s.continuation || {}).state] || _STREAK_CONT.neutral;
    const logo = s.teamId ? `https://media.api-sports.io/football/teams/${s.teamId}.png` : '';
    const venue = _VENUE_LABEL[s.venue] ? ` · <span style="color:var(--accent);font-weight:700;">${_VENUE_LABEL[s.venue]}</span>` : '';
    // Zwei getrennte Balken: Eigentendenz + nächster Gegner (29.06.2026, Lucas: lebendige Serien).
    const ownPct = (s.ratePct != null) ? s.ratePct : null;
    const oppPct = (s.next && s.next.oppRatePct != null) ? s.next.oppRatePct : null;
    const oppSup = (s.oppSupportPct != null) ? s.oppSupportPct : oppPct;   // färbt nach Stütze FÜR die Serie
    let bars = '';
    if (ownPct != null) bars += _miniBar('Eigen', ownPct, _rateColor(ownPct));
    if (oppPct != null) bars += _miniBar('Gegner', oppPct, _rateColor(oppSup));
    return `<div style="display:flex;align-items:flex-start;gap:11px;padding:14px 6px;border-bottom:1px solid var(--border);">
      ${logo ? `<img src="${logo}" style="width:30px;height:30px;object-fit:contain;flex-shrink:0;margin-top:2px;" loading="lazy" alt="">` : ''}
      <div style="flex:1;min-width:0;">
        <div style="font-size:15px;font-weight:800;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${s.team} <span style="font-size:11px;color:var(--muted);font-weight:600;">${s.leagueName || s.league || ''}</span></div>
        <div style="font-size:12.5px;color:var(--text);margin-top:3px;">${ic} ${s.market}${venue} · <strong style="color:${c.col};">${s.length} in Folge</strong> ${_streakDotsHtml(s.seq, c.col)}</div>
        ${_streakNextHtml(s)}
        ${_streakSignalHtml(s)}
      </div>
      <div style="flex-shrink:0;width:110px;" title="${(s.continuation || {}).label || ''}">
        ${bars}
        <div style="font-size:10px;font-weight:800;color:${c.col};text-align:right;text-transform:uppercase;letter-spacing:.4px;">${c.label}</div>
      </div>
    </div>`;
  }

  // Streak-Typ → Filter-Gruppe (28.06.2026, Lucas: nach Streak-Art filtern).
  const _STREAK_GROUP = { over25: 'tore', under25: 'tore', bttsYes: 'btts', bttsNo: 'btts',
                          cornersOver: 'ecken', cornersUnder: 'ecken',
                          scored: 'team', cleanSheet: 'team', cards: 'karten' };
  const _STREAK_GROUP_LABEL = { tore: '⚽ Tore O/U', btts: '🤝 BTTS', ecken: '🚩 Ecken',
                                team: '🎯 Team (trifft/zu null)', karten: '🟨 Karten' };
  const _streakGroup = (t) => _STREAK_GROUP[t] || 'sonst';
  const _VENUE_FILTERS = [['all', 'Gesamt'], ['H', '🏠 Heim'], ['A', '✈️ Auswärts']];
  let _streakSection = 'national';   // welcher Datensatz im Tab
  let _streakLeagueF = 'all';
  let _streakTypeF   = 'all';
  let _streakVenueF  = 'all';        // Gesamt / Heim / Auswärts (adamchoi-Split)
  let _streakHotOnly = false;        // nur „heiße" Serien (intakt + Signale bestätigen)
  window.wmSetStreakLeague = (l) => { _streakLeagueF = l; _renderStreaksInto(); };
  window.wmSetStreakType   = (t) => { _streakTypeF = t; _renderStreaksInto(); };
  window.wmSetStreakVenue  = (v) => { _streakVenueF = v; _renderStreaksInto(); };
  window.wmSetStreakHot    = () => { _streakHotOnly = !_streakHotOnly; _renderStreaksInto(); };

  // Heat-Score: Länge + Status (intakt/wackelt) + Signal-Bestätigung. Treibt Hero + „Heiß"-Filter.
  function _streakHeat(s) {
    let h = s.length || 0;
    const st = (s.continuation || {}).state;
    if (st === 'intakt') h += 2; else if (st === 'wackelt') h -= 3;
    const si = s.signalInfo;
    if (si) h += (si.state === 'confirm' ? (si.count || 0) : -(si.count || 0));
    return h;
  }
  const _streakIsHot = (s) => (s.continuation || {}).state === 'intakt' && _streakHeat(s) >= 6;

  // Große Hero-Kachel für eine Top-Serie.
  function _streakHeroHtml(s) {
    const c = _STREAK_CONT[(s.continuation || {}).state] || _STREAK_CONT.neutral;
    const ic = _STREAK_ICON[s.type] || '🔥';
    const logo = s.teamId ? `https://media.api-sports.io/football/teams/${s.teamId}.png` : '';
    const venue = _VENUE_LABEL[s.venue] ? ` · ${_VENUE_LABEL[s.venue]}` : '';
    const si = s.signalInfo;
    const sigBadge = si ? `<div style="margin-top:6px;font-size:10px;font-weight:800;color:${si.state === 'confirm' ? _STREAK_CONT.intakt.col : _STREAK_CONT.wackelt.col};">${si.state === 'confirm' ? '📡 ' + si.count + ' Signale dafür' : '⚠️ ' + si.count + ' dagegen'}</div>` : '';
    return `<div style="flex:1 1 200px;min-width:0;background:linear-gradient(135deg,${c.col}22,transparent);border:1px solid ${c.col}55;border-radius:12px;padding:12px 14px;">
      <div style="display:flex;align-items:center;gap:8px;">
        ${logo ? `<img src="${logo}" style="width:26px;height:26px;object-fit:contain;flex-shrink:0;" loading="lazy" alt="">` : ''}
        <div style="font-size:14px;font-weight:800;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${s.team}</div>
      </div>
      <div style="display:flex;align-items:baseline;gap:8px;margin-top:8px;">
        <span style="font-size:32px;font-weight:900;color:${c.col};line-height:1;">${s.length}</span>
        <span style="font-size:12px;color:var(--muted);">${ic} ${s.market}${venue}</span>
      </div>
      <div style="margin-top:8px;">${_streakDotsHtml(s.seq, c.col)}</div>
      <div style="margin-top:6px;font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.4px;color:${c.col};">${c.label}</div>
      ${sigBadge}
    </div>`;
  }

  // Voller Serien-Tab. section: 'national'→Liga, sonst WM.
  window.initStreaks = async function (section) {
    _streakSection = section;
    const panel = document.getElementById('streaksPanel');
    if (!panel) return;
    panel.innerHTML = `<div style="text-align:center;padding:40px;color:var(--muted);">🔥 Serien werden geladen…</div>`;
    await _loadStreaks(section === 'national');
    _renderStreaksInto();
  };

  // Rendert den Serien-Tab aus dem Cache + wendet Liga-/Typ-Filter an (kein Re-Fetch).
  function _renderStreaksInto() {
    const isLiga = _streakSection === 'national';
    const panel = document.getElementById('streaksPanel');
    if (!panel) return;
    const data = _streaksCache[isLiga ? 'liga' : 'wm'];
    const full = (data && data.streaks) || [];
    let html = `<div style="max-width:900px;margin:0 auto;">
      <div class="wm-header"><div class="wm-header-left">
        <div class="wm-title">🔥 Serien</div>
        <div class="wm-subtitle">Aktive Team-Serien — Tore Über/Unter, Beide treffen, Ecken, Karten &amp; Team (trifft/zu null). Mit Heim/Auswärts-Split und nächstem Spiel.</div>
      </div></div>`;
    if (!full.length) {
      html += `<div style="text-align:center;padding:40px 16px;color:var(--muted);font-size:13px;line-height:1.6;">Noch keine aktiven Serien (ab 3 in Folge). Füllt sich, sobald genug Spiele gelaufen sind.</div></div>`;
      panel.innerHTML = html; return;
    }
    // Filter anwenden — venue: 'all' zeigt nur Gesamt-Serien (keine H/A-Duplikate)
    let list = full.slice();
    list = list.filter(s => (s.venue || 'all') === _streakVenueF);
    if (_streakLeagueF !== 'all') list = list.filter(s => s.league === _streakLeagueF);
    if (_streakTypeF !== 'all') list = list.filter(s => _streakGroup(s.type) === _streakTypeF);
    // Hero: die heißesten 3 (vor dem Heiß-Filter, als Spotlight). Liste schließt sie aus (kein Doppel).
    const _hk = s => `${s.teamId}|${s.type}|${s.venue}`;
    const hero = list.slice().sort((a, b) => _streakHeat(b) - _streakHeat(a)).filter(s => _streakHeat(s) >= 5).slice(0, 3);
    const heroKeys = new Set(hero.map(_hk));
    if (_streakHotOnly) list = list.filter(_streakIsHot);
    const listRows = list.filter(s => !heroKeys.has(_hk(s)));

    // Filter-Leisten (Optionen aus dem vollen Satz)
    const _fbtn = (active, label, fn) => `<button onclick="${fn}" style="background:${active ? 'var(--accent)' : 'transparent'};color:${active ? '#000' : 'var(--muted)'};border:1px solid ${active ? 'var(--accent)' : 'var(--border)'};border-radius:8px;padding:5px 11px;font-size:12px;font-weight:700;cursor:pointer;margin:0 4px 6px 0;">${label}</button>`;
    const leagues = [...new Set(full.map(s => s.league))].sort();
    const groups = [...new Set(full.map(s => _streakGroup(s.type)))].filter(g => _STREAK_GROUP_LABEL[g]);
    // Heim/Auswärts-Split (nur zeigen, wenn überhaupt venue-getaggte Serien da sind)
    const hasVenue = full.some(s => s.venue === 'H' || s.venue === 'A');
    if (hasVenue) {
      html += `<div style="margin-bottom:4px;">` + _VENUE_FILTERS.map(([v, lab]) =>
        _fbtn(_streakVenueF === v, lab, `wmSetStreakVenue('${v}')`)).join('') + `</div>`;
    }
    if (leagues.length > 1) {
      html += `<div style="margin-bottom:4px;">` + _fbtn(_streakLeagueF === 'all', 'Alle Ligen', "wmSetStreakLeague('all')")
        + leagues.map(l => _fbtn(_streakLeagueF === l, l, `wmSetStreakLeague('${l}')`)).join('') + `</div>`;
    }
    html += `<div style="margin-bottom:6px;">` + _fbtn(_streakTypeF === 'all', 'Alle Arten', "wmSetStreakType('all')")
      + groups.map(g => _fbtn(_streakTypeF === g, _STREAK_GROUP_LABEL[g], `wmSetStreakType('${g}')`)).join('')
      + `<button onclick="wmSetStreakHot()" style="background:${_streakHotOnly ? '#f0883e' : 'transparent'};color:${_streakHotOnly ? '#000' : '#f0883e'};border:1px solid #f0883e;border-radius:8px;padding:5px 11px;font-size:12px;font-weight:800;cursor:pointer;margin:0 4px 6px 0;">🔥 Nur heiße</button></div>`;

    html += `<div style="font-size:11px;color:var(--muted);margin:0 2px 12px;line-height:1.5;">🟢 „Serie intakt" = Tendenz + Gegner + Signale stützen die Strähne · 🟡 „wackelt" = läuft gegen die Stütze (eher Zufall). Reiner Content — keine Wett-Garantie.</div>`;

    // Hero-Spotlight: die heißesten Serien groß oben.
    if (hero.length) {
      html += `<div style="font-size:12px;font-weight:900;margin:0 2px 8px;color:#f0883e;">🔥 Heißeste Serien</div>
        <div style="display:flex;flex-wrap:wrap;gap:10px;margin-bottom:16px;">${hero.map(_streakHeroHtml).join('')}</div>`;
    }
    if (!hero.length && !listRows.length) {
      html += `<div style="text-align:center;padding:24px;color:var(--muted);font-size:12px;">Keine Serien für diesen Filter.</div></div>`;
      panel.innerHTML = html; return;
    }
    if (listRows.length) {
      html += `<div style="background:var(--card);border:1px solid var(--border);border-radius:12px;padding:4px 14px;">`;
      for (const s of listRows) html += _streakRowHtml(s);
      html += `</div>`;
    }
    html += `</div>`;
    panel.innerHTML = html;
  }

  // Kompakte Top-Serien-Sektion für die Cards (nur starke Serien, max 4).
  function _strongStreaksSectionHtml(isLiga) {
    const data = _streaksCache[isLiga ? 'liga' : 'wm'];
    if (!data) return '';
    const strong = (data.streaks || []).filter(s => s.strong && (s.venue || 'all') === 'all').slice(0, 4);
    if (!strong.length) return '';
    let h = `<div style="background:var(--card);border:1px solid var(--border);border-radius:12px;padding:12px 14px;margin-bottom:16px;">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;">
        <span style="font-size:13px;font-weight:900;">🔥 Starke Serien</span>
        <span onclick="showSubView('streaks')" style="font-size:11px;color:var(--accent);font-weight:700;cursor:pointer;">alle Serien →</span>
      </div>`;
    for (const s of strong) h += _streakRowHtml(s);
    h += `</div>`;
    return h;
  }

  // Per-Match-Serien-Box für eine Card (28.06.2026, Lucas): Serien von Heim/Auswärts dieses Spiels.
  // Pro (Team,Markt) genau EINE Serie wählen: bevorzugt die venue-passende (Heim-Serie fürs
  // Heimteam, Auswärts fürs Auswärtsteam), sonst die Gesamt-Serie. Verhindert H/A/Gesamt-Duplikate.
  // 🔴 04.09.2026 (Lucas-Cards-Check). `score` gab der GEGENTEILIGEN Hälfte eine 0 — und 0 hat
  // gereicht, weil es keine Untergrenze gab. Auf Werder Bremen (Heim) v RB Leipzig (Auswärts)
  // standen deshalb beide Zeilen falschherum:
  //
  //     RB Leipzig · Ungeschlagen HEIM 6×        → Leipzig spielt hier auswärts
  //     Werder Bremen · Über 9,5 Ecken AUSWÄRTS 5× → Werder spielt hier daheim
  //
  // In den Daten hat Werder ausschließlich Auswärts-Serien, Leipzig fast nur Heim-Serien. Die
  // Box heißt „Serien in diesem Spiel"; eine Serie aus der anderen Hälfte gehört dort nicht
  // hinein — sie wird auf dieses Spiel bezogen, obwohl sie darüber nichts sagt.
  function _streaksForTeam(list, teamId, prefVenue) {
    const byType = {};
    const score = (v) => (v === prefVenue ? 2 : (v === 'all' || !v) ? 1 : 0);
    for (const s of list) {
      if (s.teamId !== String(teamId)) continue;
      if (!score(s.venue)) continue;            // andere Hälfte → gar nicht erst aufnehmen
      const cur = byType[s.type];
      if (!cur || score(s.venue) > score(cur.venue)) byType[s.type] = s;
    }
    return Object.values(byType);
  }
  function _matchStreaksHtml(homeId, awayId) {
    const data = _streaksCache[_mode === 'liga' ? 'liga' : 'wm'];
    if (!data) return '';
    const all = data.streaks || [];
    const ms = _streaksForTeam(all, homeId, 'H')
      .concat(_streaksForTeam(all, awayId, 'A'))
      .sort((a, b) => b.length - a.length);
    if (!ms.length) return '';
    let h = `<div style="background:linear-gradient(135deg,rgba(240,136,62,0.10),rgba(240,136,62,0.03));border:1px solid rgba(240,136,62,0.25);border-radius:10px;padding:10px 12px;margin:10px 0;">
      <div style="font-size:11px;font-weight:800;color:#f0883e;text-transform:uppercase;letter-spacing:.4px;margin-bottom:6px;">🔥 Serien in diesem Spiel</div>`;
    for (const s of ms.slice(0, 4)) {
      const ic = _STREAK_ICON[s.type] || '🔥';
      const c = _STREAK_CONT[(s.continuation || {}).state] || _STREAK_CONT.neutral;
      const venue = _VENUE_LABEL[s.venue] ? ` <span style="color:#f0883e;font-weight:700;">${_VENUE_LABEL[s.venue]}</span>` : '';
      h += `<div style="display:flex;align-items:center;gap:6px;font-size:12px;margin:4px 0;">
        <span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"><strong>${s.team}</strong> · ${ic} ${s.market}${venue}</span>
        ${_streakDotsHtml(s.seq, c.col)}
        <span style="font-weight:800;white-space:nowrap;">${s.length}×</span>
        <span style="font-size:10px;font-weight:700;color:${c.col};white-space:nowrap;">${c.label}</span>
      </div>`;
    }
    h += `</div>`;
    return h;
  }

  async function _loadCards() {
    const panel = document.getElementById(_cardsPanelId);
    if (!panel) return;

    // ── Cache-Strategie ──────────────────────────────────────────────────
    // Warm hit (TTL nicht abgelaufen): nur re-rendern, kein Netzwerk.
    // Warm miss (TTL abgelaufen, aber Daten vorhanden): alte Karten weiter
    //   sichtbar lassen + im Hintergrund silent re-fetch → kein Flicker.
    // Cold (noch nie geladen): Spinner zeigen, dann fetch.
    // Cache nur warm, wenn DASSELBE Dataset geladen ist (sonst WM-Daten im Liga-Tab, 25.06.2026).
    const isWarm    = _loaded && _wmData && _loadedFile === _dataFile;
    const ttlValid  = (Date.now() - _lastLoadTs) < CARDS_CACHE_TTL_MS;
    if (isWarm && ttlValid) {
      _render();
      return;
    }
    if (!isWarm) {
      panel.innerHTML = `
        <div style="text-align:center;padding:60px 16px;color:var(--muted);">
          <div style="font-size:36px;margin-bottom:14px;animation:spin 1.2s linear infinite;display:inline-block;">⚙️</div>
          <div style="font-size:13px;font-weight:600;">${_mode === 'liga' ? 'Lade Liga-Daten…' : 'Lade WM 2026 Daten…'}</div>
        </div>`;
    }
    // Bei warmem Miss: Karten bleiben sichtbar, fetch läuft silent unten weiter

    try {
      // (25.06.2026, Lucas: Liga auf WM-Stack) Im liga-Modus NUR liga-data.json laden —
      // WM-Sibling-JSONs (poly/travel/confidence/player-picks/odds-history) bleiben null/leer.
      const _isLiga = _mode === 'liga';
      const [wmDaten, polyRaw, travelRaw, confRaw, ppRaw, chgRaw, histRaw] = await Promise.all([
        _rawFirst(_dataFile),
        _isLiga ? Promise.resolve(null) : _rawFirst('wm_poly_prices.json'),
        _isLiga ? Promise.resolve(null) : _rawFirst('wm_travel_burden.json'),
        _isLiga ? Promise.resolve(null) : _rawFirst('pick_confidence_stats.json'),
        _isLiga ? Promise.resolve(null) : _rawFirst('wm2026-player-picks.json'),
        _isLiga ? Promise.resolve(null) : _rawFirst('pick_changes_log.json'),
        _isLiga ? Promise.resolve(null) : _rawFirst('wm2026-odds-history.json'),
      ]);
      if (!wmDaten) throw new Error(_dataFile + ' war weder ueber raw/main noch im Pages-Snapshot lesbar');
      _wmData = wmDaten;
      // 29.06.2026 (Lucas: MLS „wie die anderen Ligen"): im National-Modus zusätzlich den
      // MLS-Datensatz (eigenes File + Profil + Lernen) laden und für die Anzeige mergen. Keys
      // kollidieren nicht (Gruppe „MLS", Picks „MLS-…", Odds nach Fixture-Key) → MLS taucht
      // automatisch als weitere Liga in der kuratierten Cards-Ansicht auf.
      if (_isLiga) {
        try {
          const mls = await _rawFirst('mls-data.json');
          // 12.07.2026 (Lucas: „Liga-Cards kaputt"): NUR mergen, wenn der MLS-Datensatz auch
          // wirklich Fixtures hat. Als der API-Zugang ablief, schrieb build_liga_data leere
          // groups (0 Teams/0 Fixtures), die picks-Leichen (292 Keys) blieben aber drin → der
          // Merge zog verwaiste Picks auf nicht-existente Fixtures/Teams in die Liga-Ansicht
          // und der Card-Bau kippte. Leerer/kaputter MLS-Stand wird jetzt schlicht ignoriert.
          const mlsHasFixtures = !!(mls && mls.groups && Object.keys(mls.groups).length
            && Object.values(mls.groups).some(g => ((g && g.fixtures) || []).length > 0));
          if (mlsHasFixtures) {
            _wmData.groups  = Object.assign({}, _wmData.groups  || {}, mls.groups);
            _wmData.picks   = Object.assign({}, _wmData.picks   || {}, mls.picks   || {});
            _wmData.odds    = Object.assign({}, _wmData.odds    || {}, mls.odds    || {});
            _wmData.teamIds = Object.assign({}, _wmData.teamIds || {}, mls.teamIds || {});
          } else if (mls && mls.groups) {
            console.warn('MLS-Datensatz ohne Fixtures — Merge übersprungen (Liga-Cards bleiben intakt).');
          }
        } catch (e) { /* MLS optional — National läuft auch ohne */ }
      }
      // (25.06.2026, Lucas: Liga auf WM-Stack) WM2026_DATA NUR im WM-Modus exposen —
      // sonst würde der Liga-Tab die WM-Daten für Sharp Radar überschreiben.
      if (_mode !== 'liga') window.WM2026_DATA = _wmData;   // expose for Sharp Radar + other modules

      // 25.07.2026 (Lucas: „seh nichts im Betting-Tab"): der Polymarket-Betting-Tab las bisher NUR
      // die WM-Match-JSONs + das statische LEAGUES-Objekt — Liga/MLS (dieser Datensatz) war nie
      // angeschlossen. Hier die gemergten Liga/MLS-Picks als flache Liste exposen, im selben Format
      // wie WM2026_PICKS_FOR_POLY, damit der Tab sie 1:1 mit demselben Eligibilitäts-Filter zeigt.
      if (_isLiga) {
        try {
          const _fxByHa = {};
          for (const g of Object.values(_wmData.groups || {})) {
            for (const fx of (g.fixtures || [])) _fxByHa[`${fx.home}-${fx.away}`] = fx;
          }
          const _nat = [];
          for (const [pk, plist] of Object.entries(_wmData.picks || {})) {
            if (!Array.isArray(plist)) continue;
            const fx = _fxByHa[pk.split('-').slice(2).join('-')];   // pk = "GROUP-MD-home-away"
            if (!fx) continue;
            const _league = pk.split('-')[0] || 'MLS';   // Gruppe = Liga-Label (MLS, GER, …)
            for (const p of plist) {
              if (!['BET', 'ABWÄGEN'].includes(p.verdict)) continue;   // Feinfilter (Conviction) im Tab
              _nat.push({
                league: _league,
                home: fx.homeName || String(fx.home), away: fx.awayName || String(fx.away),
                homeId: fx.home, awayId: fx.away, date: fx.date,
                market: p.market, odds: p.odds, modelOdds: p.modelOdds,
                verdict: p.verdict, convictionScore: p.convictionScore,
                edgePP: p.edgePP || 0, clvPP: p.clvPP || 0,
                dataQuality: p.dataQuality || 'elo_only',
              });
            }
          }
          window.NATIONAL_PICKS_FOR_POLY = _nat;
        } catch (_e) { window.NATIONAL_PICKS_FOR_POLY = []; }
      }

      if (polyRaw) {
        _polyLookup = {};
        for (const f of (polyRaw.allFixtures || [])) {
          _polyLookup[f.key] = f;
        }
      }

      if (travelRaw) {
        // travelRaw ist {TEAM_ID: {...}} — direkt als Lookup nutzbar
        _travelLookup = travelRaw || {};
        window._wmTravelBurden = _travelLookup;   // backward compat mit altem Code
      }

      if (confRaw) {
        _confidenceStats = confRaw;
      }

      // Odds-History (Sparkline-Quelle für Pick-Cards)
      if (histRaw) {
        _oddsHistoryLookup = histRaw;
      }

      // Pick-Änderungen (Rolling-Log, max 200 Einträge / 7 Tage)
      _wmData.pickChanges = (chgRaw && chgRaw.changes) || [];

      // Spieler-Picks (separates File — kommt erst T-3 vor Anpfiff)
      // Format: { lastUpdate, picks: { "MEX-ZAF": [...] } }
      // Renderer erwartet aber Key-Format "GROUP-MD-HOME-AWAY" → mappen via Fixture-Liste
      if (ppRaw) {
        try {
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
      _loadedFile = _dataFile;   // Dataset merken (Cache-Invalidierung bei WM↔Liga, 25.06.2026)
      _lastLoadTs = Date.now();
      _render();

      // Stage 2: WM-Match-Pages im Hintergrund laden (für Probability-Bar, Squad-Pills, AI-Preview)
      // Erstes Render zeigt Cards schon, zweites Render hat dann die Extra-Daten
      // (26.06.2026, Lucas: Event Pages liga-tauglich) Match-Pages auch für Liga laden
      // (liga-index.json / liga-{slug}.json). _loadWmMatchPages ist dataset-bewusst.
      _loadWmMatchPages();
    } catch (e) {
      // (25.06.2026, Lucas: Liga auf WM-Stack) Retry ruft den modus-passenden Entry-Point.
      const _retryFn = _mode === 'liga' ? 'window.initNationalCards()' : 'window.initIntlCards()';
      panel.innerHTML = `
        <div style="text-align:center;padding:60px 16px;color:var(--muted);">
          <div style="font-size:40px;margin-bottom:16px;">⚠️</div>
          <div style="font-size:15px;font-weight:700;color:var(--red);">Daten konnten nicht geladen werden</div>
          <div style="font-size:12px;margin-top:8px;">${e.message}</div>
          <button onclick="${_retryFn}" style="margin-top:18px;background:var(--accent);color:#000;border:none;border-radius:8px;padding:8px 20px;font-size:13px;font-weight:700;cursor:pointer;">Erneut versuchen</button>
        </div>`;
    }
  }

  // ── Group / Matchday filters (called from inline onclick) ─
  window.wmSetGroup = function (gKey) {
    _activeGroup = gKey;
    _activeMd = 'all';          // 26.07.2026 (Lucas): Spieltag ist pro-Liga → bei Liga-Wechsel/„Alle" zuruecksetzen
    _curatedExpanded = false;   // 28.06.2026: Liga-Wechsel → kuratierte Liste wieder eingeklappt
    _render();
  };
  window.wmSetMd = function (md) {
    _activeMd = md;
    _curatedExpanded = false;
    _render();
  };
  window.wmSetSort = function (s) {
    _activeSort = s;
    _render();
  };
  window.wmToggleCurated = function () {   // 28.06.2026: „mehr/weniger" in der Beste-der-Liga-Ansicht
    _curatedExpanded = !_curatedExpanded;
    _render();
  };
  window.wmTogglePast = function () {
    _showPast = !_showPast;
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
    const panel = document.getElementById(_cardsPanelId);
    if (!panel || !_wmData) return;
    const _isLiga = _mode === 'liga';   // (25.06.2026, Lucas: Liga auf WM-Stack)

    const groups    = _wmData.groups || {};
    const groupKeys = Object.keys(groups).sort();

    // ── Collect + sort all fixtures ───────────────────
    let allFx = [];
    for (const [gKey, gData] of Object.entries(groups)) {
      for (const fx of (gData.fixtures || [])) {
        allFx.push({ ...fx, groupKey: gKey, groupData: gData });
      }
    }

    // (25.06.2026, Lucas: KO-Runden) KO-Paarungen aus wm["koFixtures"] einreihen.
    // EINMAL eine globale Team-Union bauen (für Flaggen/Elo), weil KO-Teams aus
    // beliebigen Gruppen kommen. In der „Alle"-Ansicht nur bothResolved zeigen
    // (sonst Lärm); nicht-aufgelöste nur in der Runden-gefilterten Ansicht.
    const koFixtures = Array.isArray(_wmData.koFixtures) ? _wmData.koFixtures : [];
    if (koFixtures.length) {
      const _allTeams = [];
      const _seenTeam = new Set();
      for (const gData of Object.values(groups)) {
        for (const t of (gData.teams || [])) {
          if (!_seenTeam.has(t.id)) { _seenTeam.add(t.id); _allTeams.push(t); }
        }
      }
      const _koGroupData = { teams: _allTeams, name: 'K.O.-Runde' };
      const _mdIsRound = KO_ROUND_ORDER.includes(_activeMd);
      for (const kf of koFixtures) {
        // In „Alle"-Ansicht nur aufgelöste; in Runden-Ansicht auch Platzhalter.
        if (!kf.bothResolved && !_mdIsRound) continue;
        allFx.push({
          home: kf.home, away: kf.away,
          date: kf.date, kickoff: kf.kickoff, venue: kf.venue,
          matchday: kf.round, groupKey: 'KO', isKO: true, koData: kf,
          groupData: _koGroupData,
        });
      }
    }
    // FIX 11.06.2026: Mitternachts-Umbruch. Ein 00:00-Anpfiff ist das SPÄTE
    // Nacht-Spiel des Tages (nach den 18:00/21:00-Spielen), nicht das erste.
    // Vorher sortierte "00:00" < "21:00" → KOR-CZE stand fälschlich VOR dem
    // Opener MEX-ZAF. Frühe Uhrzeiten (< 06:00) als +24h behandeln.
    // Sortierung rein nach echtem Kickoff (UTC ms) — deckt Datum+Uhrzeit korrekt
    // ab, auch Nach-Mitternacht-UTC-Spiele (KOR-CZE). fx.time-Heuristik nur Fallback.
    allFx.sort((a, b) => {
      const ka = _kickoffSortMs(a), kb = _kickoffSortMs(b);
      if (ka !== kb)                 return ka - kb;
      if (a.matchday !== b.matchday) return a.matchday - b.matchday;
      return a.groupKey.localeCompare(b.groupKey);
    });

    // ── Apply filters ─────────────────────────────────
    let filtered = _activeGroup === 'all' ? allFx : allFx.filter(fx => fx.groupKey === _activeGroup);
    // (25.06.2026, Lucas: KO-Runden) String-Vergleich, damit numerische Spieltage
    // UND Runden-Codes (R32/R16/QF/SF) als _activeMd funktionieren.
    if (_activeMd !== 'all') filtered = filtered.filter(fx => String(fx.matchday) === String(_activeMd));

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
    // (20.07.2026 Winterisierung) Nach dem Finale nicht mehr „WM läuft" zeigen. Turnier beendet =
    // alle Fixtures (Gruppen + koFixtures) aufgelöst. Sonst hing der Header ewig auf „läuft".
    const _wmOver = daysUntil < 0 && (() => {
      const _all = [];
      for (const g of Object.values(_wmData.groups || {})) for (const f of (g.fixtures || [])) _all.push(f);
      if (Array.isArray(_wmData.koFixtures)) _all.push(..._wmData.koFixtures);
      const FINAL = new Set(['FT', 'AET', 'PEN', 'FINISHED']);
      return _all.length > 0 && _all.every(f => FINAL.has(String((f.result || {}).status || '').toUpperCase()));
    })();
    const countdownStr = daysUntil > 0
      ? `<span class="wm-countdown">⏳ ${daysUntil} Tage bis zum Anpfiff</span>`
      : daysUntil === 0
        ? `<span class="wm-countdown wm-countdown-live">🔴 Heute startet die WM!</span>`
        : _wmOver
          ? `<span class="wm-countdown">🏁 WM 2026 beendet</span>`
          : `<span class="wm-countdown wm-countdown-live">🔴 WM läuft</span>`;

    // Quick stats for header
    const totalPicks = Object.values(picks).flat().filter(p => p.verdict === 'BET' || p.verdict === 'ABWÄGEN').length;
    const polyCount  = Object.keys(_polyLookup).length;

    if (_isLiga) {
      // (25.06.2026, Lucas: Liga auf WM-Stack) Neutraler Liga-Header — kein WM-Countdown,
      // keine WM-Turnier-Subline, kein Poly-Märkte-Zähler (Liga hat keine Poly-Siblings).
      html += `
      <div class="wm-header">
        <div class="wm-header-left">
          <div class="wm-title">⚽ Top-Ligen</div>
          <div class="wm-subtitle">Premier League · La Liga · Bundesliga · Serie A · Ligue 1</div>
        </div>
        <div class="wm-header-right">
          ${totalPicks > 0 ? `<span style="font-size:10px;font-weight:700;color:var(--accent);">${totalPicks} Picks</span>` : ''}
        </div>
      </div>`;
    } else {
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
    }

    // ─── Pick-Changes Banner (last 24h, only relevant ones) ──
    html += _buildChangesBanner();

    // ─── Starke Serien (28.06.2026, Lucas) — kompakte Content-Sektion bei starken Streaks ──
    _ensureStreaks(_isLiga, _render);
    html += _strongStreaksSectionHtml(_isLiga);

    // ─── Group Filter ─────────────────────────────────
    html += `<div class="wm-group-filter">`;
    html += `<button class="wm-gf-btn${_activeGroup === 'all' ? ' active' : ''}" onclick="wmSetGroup('all')">⭐ Alle</button>`;
    for (const gKey of groupKeys) {
      // (25.06.2026, Lucas: Liga auf WM-Stack) WM: „Gr. A" (Strip „Gruppe "); Liga: Liga-FLAGGE
      // + Kürzel (🏴 ENG), wie die alte National-Nav. Fallback auf Namen wenn keine Flagge.
      const gLabel = (groups[gKey].name || gKey).replace('Gruppe ', '');
      const gBtnLabel = _isLiga
        ? `${groups[gKey].flag ? groups[gKey].flag + ' ' : ''}${gKey}`
        : `Gr. ${gLabel}`;
      // Count picks in this group
      const gPicks = Object.entries(picks)
        .filter(([k]) => k.startsWith(gKey + '-'))
        .flatMap(([, v]) => v)
        .filter(p => p.verdict === 'BET').length;
      html += `<button class="wm-gf-btn${_activeGroup === gKey ? ' active' : ''}" onclick="wmSetGroup('${gKey}')">${gBtnLabel}${gPicks ? ` <span style="font-size:8px;background:rgba(63,185,80,.2);color:#3fb950;border-radius:4px;padding:0 4px;">${gPicks}</span>` : ''}</button>`;
    }
    html += `</div>`;

    // ─── Matchday Filter ─────────────────────────────
    // (26.07.2026, Lucas) In der „Alle Ligen"-Ansicht KEINE Spieltags-Navi: „Spieltag" ist eine
    // pro-Liga-Zahl und ergibt über Ligen an unterschiedlichen Saison-Punkten (Top-5 md1 vs MLS
    // md18) keine gemeinsame Achse. Chips erst bei gewählter Liga. WM-Modus (else-Zweig) unverändert.
    const _showMdFilter = !(_isLiga && _activeGroup === 'all');
    if (_showMdFilter) {
    html += `<div class="wm-md-filter">`;
    html += `<button class="wm-md-btn${_activeMd === 'all' ? ' active' : ''}" onclick="wmSetMd('all')">Alle Spieltage</button>`;
    if (_isLiga) {
      // (25.06.2026, Lucas: Liga auf WM-Stack) Spieltag-Buttons DYNAMISCH aus den
      // vorhandenen fixtures[].matchday-Werten (distinct, sortiert). Bei vielen Runden
      // (Liga = bis zu 38 Spieltage) auf die nächsten ~3 anstehenden begrenzen +
      // „Alle Spieltage" oben. „Anstehend" = kleinste Spieltage mit Spielen ab heute;
      // gibt es keine Zukunfts-Spiele mehr, fallen wir auf die letzten 3 zurück.
      // (20.07.2026) Spieltag-Chips NUR aus der aktiven Liga ableiten. Sonst erbt die MLS die
      // Spieltage der Top-5 (deren Saison 2026/27 noch nicht läuft → „nächster" Spieltag = 1),
      // obwohl die MLS längst bei md 18 steht. `allFx` ist Top-5 + MLS gemerged; bei gewählter
      // Gruppe muss die Filterleiste auf genau diese Gruppe scopen. „Alle" bleibt gemischt.
      const _scopeFx = _activeGroup === 'all' ? allFx : allFx.filter(fx => fx.groupKey === _activeGroup);
      const _mdSet = new Set();
      for (const fx of _scopeFx) {
        if (fx.matchday != null && fx.matchday !== '') _mdSet.add(fx.matchday);
      }
      const _allMds = [..._mdSet].sort((a, b) =>
        (parseFloat(a) || 0) - (parseFloat(b) || 0) || String(a).localeCompare(String(b)));
      // (26.06.2026, Lucas) Spieltag „freigeschaltet" wenn er Quoten hat ODER innerhalb der
      // nächsten 2 Wochen liegt — Quoten kommen eh nur Tage vorher, also Navi nicht mit allen
      // ~38 Runden zumüllen. Nichts live (z.B. 6 Wochen vor Saisonstart) → nur nächster Spieltag.
      const _twoWeeks = new Date(Date.now() + 14 * 86400000).toISOString().slice(0, 10);
      const _liveMd = (md) => _scopeFx.some(fx => String(fx.matchday) === String(md) && (
        odds[`${fx.home}-${fx.away}`] || (fx.date >= todayIso && fx.date <= _twoWeeks)));
      // (26.06.2026 Fix „Spieltag 1 dann 20"): nur ANSTEHENDE Spieltage ab dem nächsten zeigen und
      // nie weiter als +4 — sonst reißen evtl. fehl-gematchte Odds verstreute Runden auf. Greift
      // zusätzlich zum Daten-Fix in fetch_liga_odds (pick_event_for_fixture) als Sicherheitsnetz.
      const _upcoming = _upcomingMdsForScope(allFx, _activeGroup, todayIso);
      const _firstUp = _upcoming.length ? parseFloat(_upcoming[0]) : null;
      let _shownMds = _allMds.filter(md => _liveMd(md) && (_firstUp === null
        || (parseFloat(md) >= _firstUp && parseFloat(md) - _firstUp <= 4)));
      if (!_shownMds.length) _shownMds = _upcoming.slice(0, 1);
      // aktiven Spieltag immer sichtbar lassen
      if (_activeMd !== 'all' && !_shownMds.some(md => String(md) === String(_activeMd))
          && _allMds.some(md => String(md) === String(_activeMd))) {
        _shownMds = [..._shownMds, _activeMd];
      }
      for (const md of _shownMds) {
        const _active = String(_activeMd) === String(md);
        html += `<button class="wm-md-btn${_active ? ' active' : ''}" onclick="wmSetMd('${String(md).replace(/['"\\]/g, '')}')">Spieltag ${md}</button>`;
      }
    } else {
    html += `<button class="wm-md-btn${_activeMd === 1 ? ' active' : ''}" onclick="wmSetMd(1)">Spieltag 1</button>`;
    html += `<button class="wm-md-btn${_activeMd === 2 ? ' active' : ''}" onclick="wmSetMd(2)">Spieltag 2</button>`;
    html += `<button class="wm-md-btn${_activeMd === 3 ? ' active' : ''}" onclick="wmSetMd(3)">Spieltag 3</button>`;
    // (25.06.2026, Lucas: KO-Runden) Runden-Buttons NUR für Runden mit koFixtures.
    {
      const _koRounds = new Set((Array.isArray(_wmData.koFixtures) ? _wmData.koFixtures : []).map(k => k.round));
      for (const r of KO_ROUND_ORDER) {
        if (!_koRounds.has(r)) continue;
        html += `<button class="wm-md-btn${_activeMd === r ? ' active' : ''}" onclick="wmSetMd('${r}')">${KO_ROUND_LABELS[r]}</button>`;
      }
    }
    }
    html += `</div>`;
    }

    // ─── Sort control ────────────────────────────────
    // (28.06.2026, Lucas) In der kuratierten Liga-Ansicht (Alle Spieltage) ist die Reihenfolge
    // fix „beste zuerst" → Sort-Bar nur in der Voll-Liste (konkreter Spieltag / WM) zeigen.
    const _curated = _isLiga && _activeMd === 'all';
    if (!_curated) {
    html += `
    <div class="wm-sort-bar">
      <span class="wm-sort-lbl">Sortierung:</span>
      <button class="wm-sort-btn${_activeSort==='date'?' active':''}" onclick="wmSetSort('date')">📅 Datum</button>
      <button class="wm-sort-btn${_activeSort==='conviction'?' active':''}" onclick="wmSetSort('conviction')" title="Höchste Conviction (x/10) zuerst">🏅 Conviction</button>
      <button class="wm-sort-btn${_activeSort==='signals'?' active':''}" onclick="wmSetSort('signals')" title="Meiste feuernde Signale zuerst">🧠 Signale</button>
    </div>`;
    }

    // ── Vergangene Spiele ausblenden (17.06.2026) ─────
    // Default: gespielte Spiele (Datum < heute ODER Endstatus) raus → weniger Scrollen.
    // Toggle-Button blendet sie bei Bedarf wieder ein.
    const _isPlayed = (fx) => _fxIsPast(fx, todayIso);   // kickoff-basiert (27.06.2026)
    const _pastCount = filtered.filter(_isPlayed).length;
    if (!_showPast && _pastCount > 0) {
      filtered = filtered.filter(fx => !_isPlayed(fx));
    }
    if (_pastCount > 0) {
      html += `
      <div class="wm-past-toggle-bar" style="display:flex;justify-content:center;margin:8px 0 4px;">
        <button class="wm-sort-btn" onclick="wmTogglePast()" style="font-size:12px;">
          ${_showPast ? `🙈 ${_pastCount} vergangene Spiele ausblenden` : `👁 ${_pastCount} vergangene Spiele einblenden`}
        </button>
      </div>`;
    }

    // Helper: nur legitime (nicht-excluded, nicht-synth) Picks
    const _livePicks = (fx) => {
      const arr = picks[`${fx.groupKey}-${fx.matchday}-${fx.home}-${fx.away}`] || [];
      return arr.filter(p =>
        !p.trackingExcluded
        && (p.verdict === 'BET' || p.verdict === 'ABWÄGEN')
      );
    };

    // Apply sort
    if (_activeSort === 'conviction') {
      // Max Conviction-Score über alle Picks des Matches
      filtered = [...filtered].sort((a, b) => {
        const ca = Math.max(0, ..._livePicks(a).map(p => p.convictionScore || 0));
        const cb = Math.max(0, ..._livePicks(b).map(p => p.convictionScore || 0));
        return cb - ca;
      });
    } else if (_activeSort === 'signals') {
      // Anzahl feuernde Signale (Summe über alle live Picks, Dedup nach Name)
      filtered = [...filtered].sort((a, b) => {
        const sigCount = fx => {
          const names = new Set();
          for (const p of _livePicks(fx)) {
            for (const s of (p.signals || [])) names.add(s.name);
          }
          return names.size;
        };
        return sigCount(b) - sigCount(a);
      });
    }

    // ─── Card-Builder (gekapselt, von allen Render-Pfaden genutzt) ──────────
    // (25.06.2026, Lucas) Pro-Fixture gekapselt: eine fehlerhafte (z.B. Liga-)Card darf nicht
    // die GESAMTE Liste blanken — fehlerhafte überspringen, Rest rendert.
    const _cardHtml = (fx) => {
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
      try {
        // (28.06.2026, Lucas) Ausgeloste + bepickte KO-Spiele laufen 1:1 durch den vollen
        // _buildCard (Quoten-Stripes, Polymarket-Box, Story — wie Gruppenspiele). Nur offene
        // Paarungen / noch quotenlose KO-Spiele behalten die schlanke Vorschau-Card.
        const _koRich = fx.isKO && fx.koData && fx.koData.bothResolved && _wmLivePicks(fxPicks).length > 0;
        if (fx.isKO && !_koRich) {
          return _buildKoCard(fx, homeTeam, awayTeam, fxOdds, fxPicks, polyFix, todayIso);
        }
        return _buildCard(fx, gData, homeTeam, awayTeam, fxOdds, fxPicks, fxPPicks, fxStand, homeSquad, awaySquad, homeForm, awayForm, polyFix, todayIso);
      } catch (err) {
        console.warn('Card-Build fehlgeschlagen', fx && (fx.home + '-' + fx.away), err);
        return '';
      }
    };

    // Pick-Qualität eines Fixtures (best-first): BET > ABWÄGEN > kein Pick, dann Conviction, dann Steam.
    // (28.06.2026, Lucas) Treibt die kuratierte „Beste zuerst"-Ansicht. Ohne Pick → 0 (sortiert hinter
    // alle Picks, fällt aber als Füller für die Top-3 zurück, damit jede Liga sichtbar bleibt).
    const _fixtureRank = (fx) => {
      const lp = _livePicks(fx);
      if (!lp.length) return 0;
      const hasBet   = lp.some(p => p.verdict === 'BET');
      const bestConv = Math.max(0, ...lp.map(p => p.convictionScore || 0));
      const steam    = lp.some(p => p.steamActive || p.sharpMoveActive);
      return (hasBet ? 1000 : 100) + bestConv * 10 + (steam ? 5 : 0);
    };

    // ─── Cards ───────────────────────────────────────
    if (!filtered.length) {
      html += `<div style="text-align:center;padding:48px 16px;color:var(--muted);">Keine Spiele gefunden.</div>`;
    } else if (_curated && _activeGroup === 'all') {
      // (A) Alle Ligen + Alle Spieltage → pro Liga die Top 3 (best-first). Liga-Mini-Header,
      //     anklickbar → ganze Liga. So bleibt keine Liga „verschüttet" und kein Endlos-Scroll.
      const byLeague = {};
      for (const fx of filtered) (byLeague[fx.groupKey] = byLeague[fx.groupKey] || []).push(fx);
      const leaguesOrdered = Object.keys(byLeague).sort((a, b) => {
        const ra = Math.max(0, ...byLeague[a].map(_fixtureRank));
        const rb = Math.max(0, ...byLeague[b].map(_fixtureRank));
        return rb - ra || groupKeys.indexOf(a) - groupKeys.indexOf(b);
      });
      html += `<div style="font-size:11px;color:var(--muted);text-align:center;margin:2px 0 10px;">🏅 Beste Picks pro Liga · Liga antippen für die ganze Liste</div>`;
      html += `<div class="wm-cards-wrap">`;
      for (const gKey of leaguesOrdered) {
        const top3 = [...byLeague[gKey]]
          .sort((a, b) => _fixtureRank(b) - _fixtureRank(a) || _kickoffSortMs(a) - _kickoffSortMs(b))
          .slice(0, 3);
        if (!top3.length) continue;
        const gName = groups[gKey].name || gKey;
        const gFlag = groups[gKey].flag ? groups[gKey].flag + ' ' : '';
        html += `<div onclick="wmSetGroup('${gKey}')" style="display:flex;align-items:center;gap:8px;cursor:pointer;margin:18px 0 8px;padding-bottom:6px;border-bottom:1px solid var(--border);">
          <span style="font-size:14px;font-weight:800;">${gFlag}${gName}</span>
          <span style="margin-left:auto;font-size:11px;color:var(--accent);font-weight:700;">alle ${byLeague[gKey].length} Spiele →</span>
        </div>`;
        for (const fx of top3) html += _cardHtml(fx);
      }
      html += `</div>`;
    } else if (_curated) {
      // (B) Einzelne Liga + Alle Spieltage → beste dieser Liga zuerst, gekappt + „mehr".
      const ranked = [...filtered].sort((a, b) =>
        _fixtureRank(b) - _fixtureRank(a) || _kickoffSortMs(a) - _kickoffSortMs(b));
      const CAP  = 12;
      const show = _curatedExpanded ? ranked : ranked.slice(0, CAP);
      html += `<div style="font-size:11px;color:var(--muted);text-align:center;margin:2px 0 10px;">🏅 Beste zuerst · oben einen Spieltag wählen für die komplette Runde</div>`;
      html += `<div class="wm-cards-wrap">`;
      for (const fx of show) html += _cardHtml(fx);
      html += `</div>`;
      if (ranked.length > CAP) {
        html += `<div style="display:flex;justify-content:center;margin:12px 0;">
          <button class="wm-sort-btn" onclick="wmToggleCurated()" style="font-size:12px;">
            ${_curatedExpanded ? `🙈 Weniger anzeigen` : `▾ Alle ${ranked.length} Spiele dieser Liga`}
          </button></div>`;
      }
    } else {
      // (C) Konkreter Spieltag (oder WM) → volle Liste nach Datum, mit Datums-Trennern.
      let lastDate = null;
      html += `<div class="wm-cards-wrap">`;
      for (const fx of filtered) {
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
        html += _cardHtml(fx);
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
    const livePicks = _wmLivePicks(fxPicks);
    const sortedPicks = [...livePicks].sort((a, b) => {
      if (a.verdict === 'BET' && b.verdict !== 'BET') return -1;
      if (b.verdict === 'BET' && a.verdict !== 'BET') return 1;
      // FIX 13.06.2026: Conviction vor Edge (gleicher Hero wie in der Karte).
      const _ca = a.convictionScore || 0, _cb = b.convictionScore || 0;
      if (_cb !== _ca) return _cb - _ca;
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

  // Live-Picks (BET/ABWÄGEN, ohne ausgeschlossene/ersetzte) + AH-Linien-Dedup.
  // FIX 14.06.2026: je Seite+Vorzeichen nur die beste AH-Linie (höchste Edge) —
  // „AH Auswärts +0.5" UND „+0.75" sind redundant, eine Cover-Linie reicht (Lucas).
  // ── Verdict-Wechsel sichtbar machen (28.08.2026, Lucas) ────────────────────
  // Barcelona-Athletic: der Über-2.5-Pick war morgens NOBET (also nicht auf der Karte und
  // nicht im Public-Post), und 14 Minuten VOR Anpfiff hob die neu gerechnete Conviction ihn
  // zurück auf ABWÄGEN — da stand er wieder da, ohne je gepostet worden zu sein.
  //
  // Die Logik bleibt wie sie ist (die Aufstellung kommt T-1h und soll noch wirken dürfen).
  // Aber es muss DRANSTEHEN, sonst wundert man sich zu Recht. generate_wm_picks schreibt die
  // Wechsel in p.verdictFlips mit.
  function _verdictFlipBadge(p) {
    const flips = (p && Array.isArray(p.verdictFlips)) ? p.verdictFlips : [];
    if (!flips.length) return '';
    const last = flips[flips.length - 1];
    let uhr = '';
    try {
      const d = new Date(last.ts);
      if (isFinite(d.getTime())) {
        uhr = d.toLocaleTimeString('de-AT', { hour: '2-digit', minute: '2-digit' });
      }
    } catch (e) { /* ohne Uhrzeit weiter */ }
    const verlauf = flips.map(f => {
      let t = '';
      try { const d = new Date(f.ts); if (isFinite(d.getTime())) t = d.toLocaleString('de-AT', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) + ' '; } catch (e) {}
      return `${t}${f.von} \u2192 ${f.auf}`;
    }).join(' \u00b7 ');
    const titel = `Verdict nach der Veröffentlichung gedreht: ${verlauf}`.replace(/"/g, '&quot;');
    return ` <span class="cc-verdict-flip" title="${titel}" style="font-size:9.5px;color:#e3b341;white-space:nowrap">\u21bb ${last.von}\u2192${last.auf}${uhr ? ' ' + uhr : ''}</span>`;
  }

  function _wmLivePicks(fxPicks) {
    const base = (fxPicks || []).filter(p =>
      !p.trackingExcluded && !p.boldAlt && (p.verdict === 'BET' || p.verdict === 'ABWÄGEN'));
    const _vr = (v) => v === 'BET' ? 0 : v === 'ABWÄGEN' ? 1 : v === 'BEOBACHTEN' ? 2 : 3;
    const best = {};
    for (const p of base) {
      const m = /^(AH (?:Heim|Auswärts) [+−])/.exec(p.market || '');
      if (!m) continue;
      const cur = best[m[1]];
      const better = !cur || _vr(p.verdict) < _vr(cur.verdict)
        || (_vr(p.verdict) === _vr(cur.verdict) && (p.edgePP || 0) > (cur.edgePP || 0));
      if (better) best[m[1]] = p;
    }
    return base.filter(p => {
      const m = /^(AH (?:Heim|Auswärts) [+−])/.exec(p.market || '');
      return !(m && best[m[1]] && best[m[1]] !== p);
    });
  }

  // Icon + Display-Name je Signal — EINE Quelle (26.06.2026), genutzt von Gruppen- UND KO-Cards.
  const _SIG_META = {
    weather_signal:      ['🌡', 'Wetter'],
    travel_burden:       ['✈', 'Travel'],
    pressure_index:      ['🎯', 'Druck'],
    form_trend:          ['📈', 'Form-Trend'],
    xg_strength:         ['🥅', 'xG-Stärke'],
    h2h_pattern:         ['🤝', 'H2H'],
    injury:              ['🩹', 'Verletzungen'],
    apif_predictions:    ['📊', 'APIF-Modell'],
    lead_lag_bias:       ['📡', 'Sharp-Lag'],
    public_static_bias:  ['🎲', 'Public-Bias'],
    incentive_signal:    ['🏆', 'Anreiz'],
    lineup_signal:       ['📋', 'Lineup T-1h'],
    polymarket_sharp:    ['⚡', 'Poly (Trade)'],
    steam_lag:           ['🌊', 'Steam-Lag (Trade)'],
    chance_creation:     ['🎨', 'Chancen'],
    form_rating:         ['⭐', 'Form-Rating'],
    freshness_leg:       ['💨', 'Frische'],
    smart_money:         ['🐋', 'Smart-Money'],
    streak_momentum:     ['🔥', 'Serien-Momentum'],
    league_pressure:     ['⚡', 'Liga-Druck'],
    fixture_congestion:  ['🥵', 'Erschöpfung'],
    topscorer_momentum:  ['🎯', 'Top-Torjäger'],
    coach_change:        ['🔁', 'Neuer Trainer'],
    transfer_shift:      ['🔄', 'Transfer-Abgang'],
    betfair_money:       ['💷', 'Betfair-Geld'],
    betfair_coherence:   ['🧩', 'Kohärenz'],
  };

  // Engine-Signal-Grid (pos/neg/silent Kacheln) — gemeinsamer Renderer für Gruppen- + KO-Cards.
  //
  // 04.09.2026 (Lucas-Cards-Check, Nacharbeit). Auf der Elche-Card standen sechs Kacheln —
  // Verletzungen −6,8 · Form +2,1 · H2H −1,0 · xG +1,3 · Chancen +1,1 · Frische +1,6 — und
  // gar kein Netto. Drei Dinge liefen da zusammen, alle gleich verwirrend:
  //
  //   1. Das Netto war versteckt, weil |+0,17| < 0,5 galt als „nicht nennenswert". Damit fehlte
  //      dem Leser der einzige Anker, und die Kacheln wirkten wie das ganze Ergebnis.
  //   2. Die Kacheln summieren NICHT auf das Netto und sollen es auch nicht: `combined_score_pp`
  //      ist ein mit Konfidenz und Gewicht gemittelter Wert (registry.py), die Kacheln zeigen
  //      die rohen Scores. Sichtbar addiert Elche zu −0,44, das Netto steht bei +0,17. Beides
  //      ist richtig — nebeneinander ohne Erklärung sieht es nach Rechenfehler aus.
  //   3. `slice(0, 6)` schnitt in Registry-Reihenfolge ab, ohne Hinweis. Auf Elche fiel damit
  //      `move_following +1,2` heraus — nicht weil es klein war, sondern weil es hinten stand.
  //
  // Deshalb: Netto immer zeigen (auch nahe null), als „Ø gewichtet" benennen statt als Summe,
  // die stärksten Signale zuerst, und Abgeschnittenes ausweisen statt verschweigen.
  function _engineSignalGridHtml(heroPick) {
    const sigList = Array.isArray(heroPick.signals) ? heroPick.signals : [];
    if (!sigList.length) return '';
    const adj = heroPick.signalAdjustmentPP;
    const roh = sigList.reduce((a, s) => a + (s.score || 0), 0);
    const adjLabel = (typeof adj === 'number')
      ? `<span class="cc-sig-adj ${adj > 0.05 ? 'pos' : adj < -0.05 ? 'neg' : ''}" title="Ø gewichtet nach Konfidenz und Signal-Gewicht — bewusst KEINE Summe der Kacheln (die ergäben ${roh > 0 ? '+' : ''}${roh.toFixed(1)}pp). Ein sicheres Signal zählt mehr als ein unsicheres.">${adj > 0 ? '+' : ''}${adj.toFixed(1)}pp Netto <span style="font-weight:600;opacity:.75">Ø gew.</span></span>`
      : '';
    // Nach Betrag sortiert: die Kacheln, die das Ergebnis tragen, stehen vorn. Die
    // Registry-Reihenfolge sagt dem Leser nichts.
    const sortiert = sigList.slice().sort((a, b) => Math.abs(b.score || 0) - Math.abs(a.score || 0));
    const MAX = 6;
    const rest = sortiert.slice(MAX);
    const tiles = sortiert.slice(0, MAX).map(s => {
      const [ico, name] = _SIG_META[s.name] || ['•', (s.name || '').replace(/_/g, ' ')];
      const score = s.score || 0;
      const cls = score > 0.3 ? 'cc-sig-tile-pos' : score < -0.3 ? 'cc-sig-tile-neg' : 'cc-sig-tile-silent';
      const val = Math.abs(score) >= 0.1 ? `${score > 0 ? '+' : ''}${score.toFixed(1)}pp` : '—';
      return `<div class="cc-sig-tile ${cls}">
        <div class="cc-sig-tile-head"><span class="cc-sig-tile-ico">${ico}</span><span class="cc-sig-tile-name">${name}</span></div>
        <div class="cc-sig-tile-val">${val}</div>
        <div class="cc-sig-tile-desc">${s.evidence || ''}</div>
      </div>`;
    }).join('');
    // Abgeschnittenes benennen — mit Namen und Werten, damit „+2 weitere" nicht selbst
    // wieder eine Lücke ist.
    const restLabel = rest.length
      ? `<div class="cc-sig-rest" style="font-size:10.5px;color:var(--muted);margin-top:6px;" title="${rest.map(s => `${(_SIG_META[s.name] || ['', s.name])[1]} ${(s.score || 0) > 0 ? '+' : ''}${(s.score || 0).toFixed(1)}pp`).join(' · ')}">+${rest.length} weitere${rest.length === 1 ? 's' : ''} Signal${rest.length === 1 ? '' : 'e'} — zählen mit, aber nicht abgebildet</div>`
      : '';
    return `<div class="cc-signals">
      <div class="cc-signals-head">🧠 Engine-Signale ${adjLabel}</div>
      <div class="cc-sig-grid">${tiles}</div>
      ${restLabel}
    </div>`;
  }

  // Spiel „vergangen/gespielt"? — IMMER über den Anpfiff (kickoff) entscheiden, nicht über das
  // Spieltag-Datum (27.06.2026, Lucas). Spät-Anpfiff-Spiele (z.B. 04:00 Wien = nächster UTC-Tag)
  // haben date=Vortag, kickoff=Folgetag → `date < heute` markierte sie fälschlich „GESPIELT",
  // obwohl noch nicht angepfiffen. Endstatus (FT/AET/…) zählt immer als gespielt.
  const _PAST_FINAL = ['FT', 'AET', 'PEN', 'AWD', 'WO'];
  function _fxIsPast(fx, todayIso) {
    const status = String((fx.result || {}).status || '').toUpperCase();
    if (_PAST_FINAL.includes(status)) return true;
    const ko = fx && fx.kickoff ? new Date(String(fx.kickoff).replace('Z', '+00:00')) : null;
    if (ko && !isNaN(ko.getTime())) return ko.getTime() <= Date.now();
    return (fx && fx.date || '') < todayIso;   // Fallback ohne kickoff
  }

  // Sharp-Konsens (28.06.2026, Lucas): Pinnacle vs Betfair Exchange als 2. Sharp-Anker.
  // De-viggt beide 1X2 und vergleicht den Favoriten. Nur Cross-Check/Confidence — NICHT in der
  // Pick-Engine. Liefert null wenn Betfair (bf_*) fehlt (z.B. WM / keine Börsen-Abdeckung).
  function _sharpConsensus(o) {
    if (!o || !(o.hw > 1 && o.dr > 1 && o.aw > 1) || !(o.bf_hw > 1 && o.bf_dr > 1 && o.bf_aw > 1)) return null;
    const devig = (a, b, c) => { const ia = 1 / a, ib = 1 / b, ic = 1 / c, t = ia + ib + ic; return [ia / t, ib / t, ic / t]; };
    const [ph, pd, pa] = devig(o.hw, o.dr, o.aw);
    const [bh, bd, ba] = devig(o.bf_hw, o.bf_dr, o.bf_aw);
    const pinn = [['Heim', ph], ['Remis', pd], ['Auswärts', pa]].sort((x, y) => y[1] - x[1]);
    const bf = { Heim: bh, Remis: bd, 'Auswärts': ba };
    const fav = pinn[0][0];
    const bfFav = [['Heim', bh], ['Remis', bd], ['Auswärts', ba]].sort((x, y) => y[1] - x[1])[0][0];
    const diffPP = Math.abs(pinn[0][1] - bf[fav]) * 100;
    if (bfFav !== fav) return { label: `⚠ Sharp uneinig · Pinnacle ${fav} / Betfair ${bfFav}`, col: '#f85149' };
    if (diffPP <= 2) return { label: '🤝 Sharp-Konsens · Pinnacle & Betfair einig', col: '#3fb950' };
    if (diffPP >= 4) return { label: `⚠ Betfair weicht ${diffPP.toFixed(0)}pp ab`, col: '#e3b341' };
    return null;
  }
  function _sharpConsensusChip(o) {
    const c = _sharpConsensus(o);
    return c ? `<div class="cc-sharp-consensus" style="font-size:11px;font-weight:700;color:${c.col};margin:6px 0 2px;">${c.label}</div>` : '';
  }

  // ─────────────────────────────────────────────────────
  //  CARD BUILDER — Community-First Layout (Pick/Story/Confidence)
  // ─────────────────────────────────────────────────────
  // Mini-🔥-Badge im Card-Header: zeigt beim Scrollen, dass das Match heiße/starke Serien hat.
  function _matchHotBadge(homeId, awayId) {
    const data = _streaksCache[_mode === 'liga' ? 'liga' : 'wm'];
    if (!data) return '';
    const all = data.streaks || [];
    const ms = _streaksForTeam(all, homeId, 'H').concat(_streaksForTeam(all, awayId, 'A'));
    const hot = ms.filter(s => _streakIsHot(s) || s.strong);
    if (!hot.length) return '';
    const max = Math.max(...hot.map(s => s.length || 0));
    return `<span class="cc-dot"></span><span style="color:#f0883e;font-weight:800;font-size:11px;white-space:nowrap;">🔥 ${hot.length} Serie${hot.length === 1 ? '' : 'n'}${max ? ` · bis ${max}×` : ''}</span>`;
  }
  function _buildCard(fx, gData, home, away, fxOdds, fxPicks, fxPPicks, standing, homeSquad, awaySquad, homeForm, awayForm, polyFix, todayIso) {
    const eloDiff   = (home.elo && away.elo) ? (home.elo - away.elo) : null;
    // FIX 14.06.2026: nicht nur Datum < heute — auch HEUTE bereits beendete Spiele
    // (AUS-TUR 06:00 angepfiffen, FT, aber fx.date == todayIso) gelten als gespielt,
    // sonst rendert die Card sie weiter als offenen Pick statt als Endstand (Lucas).
    const _finalStatus = ['FT', 'AET', 'PEN', 'AWD', 'WO'].includes(
      ((fx.result && fx.result.status) || '').toUpperCase());
    const isPlayed  = _fxIsPast(fx, todayIso);   // kickoff-basiert (27.06.2026)
    const isToday   = fx.date === todayIso;

    // Pick selection: pick BET/ABWÄGEN with highest edge as hero
    // WATCH-Picks (z.B. Corner-Picks ohne Markt-Quote) sind keine Hero-Kandidaten
    // Smart-Substitution: saferAlt-Picks (Doppelte Chance / AH-Alternative für riskante Picks)
    //   werden bei gleicher Verdict-Klasse bevorzugt — niedrigere Quote = höhere Hit-Rate
    // Audit-Fix 06.06.2026: trackingExcluded Picks komplett raus aus der Card.
    // Diese werden vom Tracker (resolve_wm_picks.py) als VOID markiert wenn sie
    // direktional widersprüchlich sind — wir wollen sie nirgends anzeigen.
    const livePicks = _wmLivePicks(fxPicks);
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
      // FIX 13.06.2026: Conviction VOR roher Edge. Vorher entschied bei gleichem
      // Verdict allein die Edge → ein conv-0-Longshot mit hoher Edge wurde zum Hero
      // (z.B. BEL-EGY „Über 3.5" conv0/edge9 schlug „AH Heim −1.5" conv3/edge6).
      // Qualität (signal-gestützte Conviction) schlägt jetzt rohe Edge bei der Hero-Wahl.
      const _ca = a.convictionScore || 0, _cb = b.convictionScore || 0;
      if (_cb !== _ca) return _cb - _ca;
      // Dann Edge desc
      return (b.edgePP || 0) - (a.edgePP || 0);
    });
    let heroPick   = sortedPicks[0] || null;
    let otherPicks = sortedPicks.slice(1);
    // Einsatz pro Pick (28.06.2026, Lucas: „in den Cards muss klar sein welcher Stake — egal welches Label").
    // Quelle: pick.stake (pick_staking.py, Edge-Staking). Fallback null → nichts anzeigen.
    const _stakeStr = (p) => (p && typeof p.stake === 'number')
      ? (p.stake % 1 === 0 ? String(p.stake) : p.stake.toFixed(1)) : null;
    let watchReason = null;   // warum ein Spiel zur Beobachtung demotet wurde (für Text)

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
        watchReason = 'asymData';
      }
    }

    // ── FIX 14.06.2026: Riskanter Longshot-Hero ohne sichere Alternative ──────
    // Lucas: bei vielen Spielen war der Haupt-Pick die riskante Variante (AH −1.5/−2.5,
    // Quote >3). Die Engine bietet jetzt eine sichere Variante an (saferAltFor/boldAlt) —
    // WO ES SIE GIBT. Für echte Mismatch-Longshots (z.B. AH Auswärts −2 @6.4, Unter 1.5
    // @3.15) ist die sichere Variante −EV → die Engine bietet (korrekt) keine an. Dann
    // soll auch KEIN riskanter Pick als Headline stehen: lieber „Beobachtungs-Spiel".
    // Greift NUR wenn keine sichere Alternative existiert (kein boldAlt UND kein saferAltFor).
    const RISKY_HERO_MAX = 3.0;
    const _ahFavLine = (m) => { const x = /AH (?:Heim|Auswärts) −([\d.]+)/.exec(m || ''); return x ? parseFloat(x[1]) : 0; };
    // Steam-Picks leiten die AH-Linie bewusst auf eine sichere Quote ab (1,4-1,95) →
    // die Linien-Höhe ist kein Risiko, nur eine Quote > 3,0 wäre eins (analog Engine/Guard).
    const _heroIsRiskyVariant = heroPick &&
      ((heroPick.odds || 0) > RISKY_HERO_MAX ||
       (heroPick.source !== 'steam' && _ahFavLine(heroPick.market) >= 1.5));
    if (heroPick && _heroIsRiskyVariant && !heroPick.boldAlt && !heroPick.saferAltFor) {
      heroPick = null;
      otherPicks = [];
      watchReason = 'riskyNoSafe';
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
      html += `<div class="cc-hot-badge" title="Pinnacle hat die Quote bereits bewegt — Polymarket hinkt hinterher. Klassisches Sharp-Signal.">🔥 Sharp-Move erkannt</div>`;
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
    // (28.06.2026, Lucas) KO-Spiele laufen jetzt durch den vollen _buildCard → Header KO-bewusst:
    // Runden-Label statt „Gruppe X · ST Y" (KO hat keine Gruppe/Spieltag-Nummer).
    const _ko = fx.isKO ? (fx.koData || {}) : null;
    const groupLabel = _ko
      ? `🏆 ${_ko.roundLabel || KO_ROUND_LABELS[_ko.round] || 'K.O.-Runde'}${_ko.matchNo ? ` · Spiel ${_ko.matchNo}` : ''}`
      : `${gData.name || ('Gruppe ' + fx.groupKey)} · ST ${fx.matchday}`;
    const dateMain   = _fmtKickoffMain(fx);          // "So, 14. Jun · 00:00 Uhr" (Wien, aus kickoff)
    const localTime  = _venueLocalFromKickoff(fx);   // " · 18:00 NY" (Venue-Local, aus kickoff)
    html += `<div class="cc-meta">
      <span>${groupLabel}</span>
      <span class="cc-dot"></span>
      <span>${dateMain}${localTime ? `<span class="cc-local-tz">${localTime}</span>` : ''}</span>
      ${fx.venue ? `<span class="cc-dot"></span><span class="cc-venue">📍 ${fx.venue}</span>` : ''}
      ${_venueEnvPill(fx.venue)}
      ${_weatherPill(fx)}
      ${_matchHotBadge(fx.home, fx.away)}
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
      // FIX 13.06.2026 (Mittelweg) — Haupt-Pick behält Sterne aus Modell-Confidence,
      // wird aber NUR runtergestuft, wenn die Signale aktiv WIDERSPRECHEN (Netto ≤ −2pp)
      // oder quasi keine Bestätigung da ist (Conviction ≤ 1). So bleiben solide Picks
      // klare Heroes (★★/★★★), nur echte Oversell-Fälle (Edge da, aber alle Signale
      // dagegen — z.B. CIV-ECU) fallen auf ★. Nicht generell wegen früher dünner Daten.
      // FIX 14.06.2026: Sterne aus dem VERDICT (nicht conf/Datenqualität) — sonst stand
      // ein ★★★-ABWÄGEN über einem ★★☆-BET. BET 3 ≥ ABWÄGEN 2; bei klar widersprechenden
      // Signalen (Netto ≤ −2pp) eine Stufe runter (BET→2, ABWÄGEN→1).
      // Sterne = DER EINE schnelle Pick-Indikator (Lucas 20.06.): BET bleibt ★★★ (Konsistenz
      // zum Label), ABWÄGEN wird nach Conviction abgestuft (★/★★/★★★) — so tragen die Sterne
      // echte Stärke statt nur das Verdict zu spiegeln und stimmen mit dem Conviction-Block
      // darunter überein (Glance hier, Detail dort), statt zwei konkurrierende Indikatoren.
      const _cs = (typeof heroPick.convictionScore === 'number') ? heroPick.convictionScore : null;
      let stars;
      if (heroPick.verdict === 'BET') stars = 3;
      else if (heroPick.verdict === 'ABWÄGEN') stars = (_cs != null) ? (_cs >= 7 ? 3 : _cs >= 4 ? 2 : 1) : 2;
      else stars = 1;
      const _net = heroPick.signalAdjustmentPP;
      if (typeof _net === 'number' && _net <= -2) stars = Math.max(1, stars - 1);
      const oddsStr = heroPick.odds != null ? heroPick.odds.toFixed(2) : '—';
      html += `<div class="cc-pick${isAbw ? ' cc-pick-abw' : ''}">
        <div class="cc-pick-label">${isAbw ? 'Vorsichtiger Pick' : 'Unser Pick'}</div>
        <div class="cc-pick-market">${heroPick.market}</div>
        <div class="cc-pick-odds"><span class="cc-at">@</span><span class="cc-num">${oddsStr}</span></div>
        ${_stakeStr(heroPick) ? `<div class="cc-pick-stake" style="font-size:12.5px;font-weight:800;color:#5eead4;margin-top:3px;">💶 Einsatz €${_stakeStr(heroPick)}</div>` : ''}
        <div class="cc-pick-conf">
          ${[1,2,3].map(n => `<span class="cc-star${isAbw ? ' cc-star-abw' : ''} ${n <= stars ? 'cc-star-full' : 'cc-star-empty'}">★</span>`).join('')}
        </div>
        <button class="cc-why-btn" onclick="wmOpenWhy('${matchKey.replace(/['"\\\\]/g,'')}')" title="Modell-Rechnung, Insights, CLV, Risiko, Stake-Empfehlung">
          🔍 Warum?
        </button>
      </div>`;

      // Sharp-Konsens (Pinnacle vs Betfair Exchange) — nur Liga (bf_* vorhanden), reiner Cross-Check.
      html += _sharpConsensusChip(fxOdds);

      // Odds-Verlauf zwischen Pick und Story. Steam-Picks: eigener Move-Graph (geht für
      // ALLE Märkte inkl. AH, nutzt steamOpen/steamCur direkt). Sonst der klassische
      // Odds-Strip (nur mappbare Märkte mit ≥2pp Drift).
      if (heroPick.source === 'steam') {
        html += _steamMoveGraph(heroPick);
      } else {
        const stripHtml = _buildOddsStrip(heroPick, fxOdds, fx);
        if (stripHtml) html += stripHtml;
      }
      // 💷 Betfair-Geld-Verteilung (unter Pinnacle/Soft-Block), sobald das Signal feuert.
      html += _betfairMoneyBlock(heroPick);
    } else if (isPlayed && fx.result && fx.result.home_score != null && fx.result.away_score != null
               && ['FT','AET','PEN'].includes((fx.result.status || 'FT').toUpperCase())) {
      // FIX 12.06.2026: Felder heißen home_score/away_score (nicht .home/.away).
      // FIX 13.06.2026: NUR bei finished (FT/AET/PEN) als „Endstand" zeigen — sonst
      // wurde ein Live-Zwischenstand (1H 2:0) fälschlich als Endstand gerendert,
      // obwohl das Spiel 4:1 endete. (Default 'FT' für Altdaten ohne status-Feld.)
      html += `<div class="cc-pick cc-pick-result">
        <div class="cc-pick-label">Endstand</div>
        <div class="cc-pick-market">${fx.result.home_score}:${fx.result.away_score}</div>
      </div>`;
    } else if (isPlayed) {
      // Entweder live (Spiel läuft) oder gespielt aber Ergebnis-Lag.
      const _st = (fx.result && fx.result.status || '').toUpperCase();
      const _liveSet = ['1H','HT','2H','ET','BT','P','LIVE','INT','SUSP'];
      if (_liveSet.includes(_st)) {
        const _el = fx.result && fx.result.elapsed;
        html += `<div class="cc-pick cc-pick-result">
          <div class="cc-pick-label">🔴 Läuft${_el ? ` · ${_el}'` : ''}</div>
          <div class="cc-pick-market cc-pick-pending">Endstand abwarten</div>
        </div>`;
      } else {
        // Gespielt (laut Datum), aber Ergebnis noch nicht da (API-Football-Lag).
        html += `<div class="cc-pick cc-pick-result">
          <div class="cc-pick-label">Endstand</div>
          <div class="cc-pick-market cc-pick-pending">–:–</div>
        </div>`;
      }
    } else if (!isPlayed && !heroPick) {
      // FIX 14.06.2026: korrekte Begründung je nach Demotion-Grund (vorher zeigte JEDE
      // Demotion mit Live-Picks fälschlich „Form-Daten fehlen", auch der Risiko-Fall).
      const watchMsg =
        watchReason === 'riskyNoSafe' ? 'Nur riskante Varianten (hohe Quote) — keine sichere Wette'
        : watchReason === 'asymData'  ? 'Datenbasis unvollständig — Form-Daten eines Teams fehlen'
        : (livePicks.length > 0)      ? 'Datenbasis unvollständig — Form-Daten eines Teams fehlen'
        :                               'Kein Pick mit Edge — Spielverlauf abwarten';
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

      // SHARP-MOVE-BOX entfernt 17.06.2026: war ein ZWEITER Pinnacle-Streifen aus der
      // (löchrigen) odds_history → erschien nur auf manchen Cards. Der Pinnacle-Streifen
      // kommt jetzt IMMER aus dem Steam-Trigger via _steamMoveGraph (Z.699). Doppelung weg.

      // ─── CONVICTION-BADGE (NEU 09.06.2026) ────────────
      // Wett-Qualitäts-Bewertung 0-10 aus conviction_score.py.
      // Bar-Visualisierung mit 8+-Zielmarker. Wird IMMER angezeigt wenn
      // Score gesetzt — auch bei niedrigem Score (transparente Warnung).
      if (typeof heroPick.convictionScore === 'number') {
        const score = heroPick.convictionScore;
        const label = heroPick.convictionLabel
          || (score >= 8 ? '🎯 Top-Wette' : score >= 6 ? '⭐ Gute Wette'
            : score >= 4 ? '👁 Beobachten' : score >= 2 ? '⚠ Schwache Bestätigung'
            : '⚠ Keine Bestätigung');
        const cls = score >= 8 ? 'cc-conv-top'
                  : score >= 6 ? 'cc-conv-good'
                  : score >= 4 ? 'cc-conv-watch' : 'cc-conv-low';
        const pct = (score / 10) * 100;
        const fams = heroPick.convictionFamilies || {};
        const famRows = [
          ['💸', 'Sharp-Money', fams.sharp_money || 0, 3],
          ['📊', 'Modell-Stack', fams.model_stack || 0, 3],   // Form+xG+H2H+Chancen+Rating
          ['🧭', 'Kontext', fams.context || 0, 3],            // Travel+Lineup+Wetter+Druck+Höhe
          ['🌐', 'Markt-Konsens', fams.market || 0, 1],
        ].filter(([, , v, max]) => v > 0 || max >= 2)
         .map(([icon, n, v, max]) => {
           const segs = Array.from({length: max}, (_, i) =>
             `<span class="cc-fam-seg${i < v ? ' on' : ''}"></span>`).join('');
           return `<div class="cc-fam-row ${v > 0 ? 'pos' : ''}">
             <span class="cc-fam-name">${icon} ${n}</span>
             <span class="cc-fam-segs">${segs}</span>
             <span class="cc-fam-val">${v}/${max}</span>
           </div>`;
         }).join('');
        html += `<div class="cc-conviction ${cls}">
          <div class="cc-conv-head">${label} <span class="cc-conv-score">${score}/10</span></div>
          ${famRows ? `<div class="cc-fam-grid">${famRows}</div>` : ''}
          <div class="cc-conv-bar"><div class="cc-conv-fill" style="width:${pct}%"></div><div class="cc-conv-target" title="8+ = Top-Wette"></div></div>
          <div class="cc-conv-bar-labels"><span>Conviction ${score}/10</span><span>für Top-Wette: 8+</span></div>
        </div>`;
      } else if (typeof heroPick.convictionScore === 'number'
                 && heroPick.modelHallucinationWarning
                 && heroPick.convictionScore < 4) {
        html += `<div class="cc-conviction cc-conv-warn">
          <div class="cc-conv-head">⚠ Edge vorhanden, aber dünne Begründung</div>
          <div class="cc-conv-extra">Conviction nur ${heroPick.convictionScore}/10 — Pick mit Vorsicht</div>
        </div>`;
      }

      // ─── ENGINE-SIGNAL-GRID (NEU 09.06.2026) ──────────
      // Signal-Engine (sharp_signals/) hat pro Pick signals[] mit evidence
      // und signalAdjustmentPP. Grid mit pos/neg/silent Tiles statt Text-Liste.
      html += _engineSignalGridHtml(heroPick);
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

    // ─── Synthetische saferAlt-Box (NEU 09.06.2026) ───────
    // Wenn HeroPick einen boldAlt referenziert (Smart-Sub-Insurance), zeigen
    // wir die Alternative prominent als gestrichelte Box VOR den anderen Picks.
    if (heroPick && heroPick.boldAlt) {
      const ba = heroPick.boldAlt;
      const altOdds = ba.odds != null ? ba.odds.toFixed(2) : '—';
      const altEdge = ba.edgePP != null ? `${ba.edgePP > 0 ? '+' : ''}${ba.edgePP}pp` : '';
      const heroOdds = heroPick.odds != null ? heroPick.odds.toFixed(2) : '—';
      html += `<div class="cc-safer-alt">
        <div class="cc-safer-alt-head">
          <span>🛡 Sicherere Alternative</span>
          <span style="font-family:'JetBrains Mono','SF Mono',Menlo,monospace;font-size:13px;">${ba.market} @${altOdds} · ${altEdge}</span>
        </div>
        <div class="cc-safer-alt-body">
          Weniger Edge, aber deutlich risikoärmer als <strong>${heroPick.market} @${heroOdds}</strong>.
        </div>
        <div class="cc-safer-alt-synth">
          ${ba.edgePP != null && ba.edgePP < 4 ? 'Synthetische Alternative — wurde nicht als eigener Pick generiert weil Edge unter Schwelle, aber als Insurance angeboten.' : 'Eigene Edge-Berechnung — auch als alleinstehender Pick valide.'}
        </div>
      </div>`;
    }

    // ─── Other picks compact (if more than hero) ─────────
    // Exclude bereits gezeigtes boldAlt-Market damit nicht doppelt
    const heroBoldAltMarket = heroPick && heroPick.boldAlt ? heroPick.boldAlt.market : null;
    const otherPicksFiltered = heroBoldAltMarket
      ? otherPicks.filter(op => op.market !== heroBoldAltMarket)
      : otherPicks;
    if (otherPicksFiltered.length) {
      html += `<div class="cc-otherpicks">
        <div class="cc-ev-label" style="padding:0 0 6px 0;">Weitere Picks</div>`;
      for (const op of otherPicksFiltered.slice(0, 3)) {
        const cls = op.verdict === 'BET' ? 'cc-op-bet' : 'cc-op-abw';
        const oddsStr = op.odds != null ? op.odds.toFixed(2) : '—';
        const epp = op.edgePP != null ? ` <span class="cc-op-edge">${op.edgePP > 0 ? '+' : ''}${op.edgePP}pp</span>` : '';
        const synthBadge = op.synthetic ? ' <span class="cc-op-synth">🛡</span>' : '';
        const opStake = _stakeStr(op) ? ` <span class="cc-op-stake" style="color:#5eead4;font-weight:700;">💶 €${_stakeStr(op)}</span>` : '';
        html += `<div class="cc-op-row ${cls}">
          <span class="cc-op-verdict">${op.verdict}</span>
          <span class="cc-op-market">${op.market}${synthBadge}${_verdictFlipBadge(op)}</span>
          <span class="cc-op-odds">@${oddsStr}</span>${epp}${opStake}
        </div>`;
      }
      html += `</div>`;
    }

    // ─── NOBET (war BET/ABWÄGEN, Value inzwischen weg) — transparent, KEIN Bet ──
    // 23.06.2026 (Lucas): nicht lautlos verschwinden lassen, sondern „gesehen, aber kein Bet, weil…"
    // zeigen. Schatten-Resultat rein informativ (zählt NICHT in P&L/Win-Rate/Lernen).
    const _nobets = (fxPicks || []).filter(p => p && p.verdict === 'NOBET');
    if (_nobets.length) {
      html += `<div class="cc-otherpicks" style="opacity:.8">
        <div class="cc-ev-label" style="padding:0 0 6px 0;color:#76819c;">Kein Bet — gesehen, aber kein Value</div>`;
      for (const nb of _nobets.slice(0, 3)) {
        const _o = nb.odds != null ? nb.odds.toFixed(2) : (nb.origOdds != null ? nb.origOdds.toFixed(2) : '—');
        const _sh = nb.shadowResult === 'WIN'  ? '<span style="color:#3fb950">✅ hätte gewonnen</span>'
                  : nb.shadowResult === 'LOSS' ? '<span style="color:#f85149">❌ hätte verloren</span>'
                  : nb.shadowResult === 'VOID' ? '<span style="color:#8b949e">➖ Push</span>'
                  : `@${_o}`;
        const _reason = nb.nobetReason
          ? `<br><span style="font-size:.7rem;color:#76819c">${nb.nobetReason}</span>` : '';
        html += `<div class="cc-op-row" style="background:rgba(118,129,156,.08);border-color:rgba(118,129,156,.22)">
          <span class="cc-op-verdict" style="color:#76819c">NOBET</span>
          <span class="cc-op-market">${nb.market}${_reason}</span>
          <span class="cc-op-odds" style="color:#76819c;white-space:nowrap">${_sh}</span>
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

    // ─── Serien in diesem Spiel (28.06.2026, Lucas) — wenn Heim/Auswärts eine aktive Serie hat ──
    html += _matchStreaksHtml(fx.home, fx.away);

    // ─── ACTIONS row ──────────────────────────────────
    // (26.06.2026, Lucas) Slug dataset-bewusst: wm- bzw. liga- (Analyse-Link → matches/wm-match-v2.html).
    const slug = `${_mpPrefix(fx)}-${fx.home.toLowerCase()}-vs-${fx.away.toLowerCase()}-${fx.date}`;
    if (!isPlayed && heroPick) {
      // Fußzeile (20.06.2026): Datenqualitäts-Tier (steam/full/elo) + conf RAUS — die Engine ist
      // signal-getrieben, das Tier interessiert niemanden mehr. Stattdessen drei aussagekräftige
      // Chips: Pulse (Frische des Moves) · Lineup (Ausfälle T-1h) · Track-Record (ehrliche Zählung).

      // Track-Record: ehrliche „X von N" statt nacktem Prozent (n ist klein → % wirkt zu präzise).
      const conf = _confidenceFor(heroPick);
      let trackStr = '';
      if (conf && conf.n >= 3) {
        const won = Math.round(conf.rate / 100 * conf.n);
        const cls = conf.rate >= 60 ? 'cc-val-hot' : conf.rate < 40 ? 'cc-val-cool' : '';
        const scopeLabel = {
          cluster: 'praktisch identischen',
          market:  heroPick.market,
          angle:   'ähnlichen',
          global:  'allen WM-',
        }[conf.scope] || 'vergleichbaren';
        trackStr = `<span class="cc-conf-backtest" title="Trefferquote vergleichbarer Picks aus dem Backtest — kleine Stichprobe, nur grobe Orientierung."><span class="cc-conf-rate ${cls}">${won}/${conf.n}</span> ${scopeLabel} Wetten getroffen</span>`;
      }
      // Pulse — nur Steam-Picks mit Frische-Status (GESTÄRKT / BASIS / DREHT)
      let pulseStr = '';
      const _pmap = { confirm: ['GESTÄRKT', '#3fb950'], drift: ['BASIS', '#8b949e'], reverse: ['DREHT', '#f85149'] };
      if (heroPick.source === 'steam' && _pmap[heroPick.freshnessState]) {
        const pm = _pmap[heroPick.freshnessState];
        pulseStr = `<span style="font-size:.74rem;color:#8b949e" title="Pulse — Frische des Sharp-Money-Moves">⚡ Pulse <strong style="color:${pm[1]}">${pm[0]}</strong></span>`;
      }
      // Lineup — wenn die Aufstellung raus ist (T-1h) und jemand fehlt/zurück ist
      let lineupStr = '';
      const _lsig = (heroPick.signals || []).find(s => s && s.name === 'lineup_signal');
      const _aff  = (_lsig && _lsig.metadata && _lsig.metadata.affected) || [];
      if (_aff.length) {
        const _nm = a => a.name || a.scorer || 'Schlüsselspieler';   // key_players: name · top_scorer: scorer
        const _miss = _aff.find(a => a.status === 'missing');
        const _ben  = _aff.find(a => a.status === 'benched');
        const _ret  = _aff.find(a => a.status === 'returning');
        let _lt = '', _lc = '#8b949e';
        if (_miss)      { _lt = `${_nm(_miss)} fehlt`;      _lc = '#f85149'; }
        else if (_ben)  { _lt = `${_nm(_ben)} nur Bank`;    _lc = '#e3b341'; }
        else if (_ret)  { _lt = `${_nm(_ret)} zurück`;      _lc = '#3fb950'; }
        if (_lt) {
          const _more = _aff.length > 1 ? ` +${_aff.length - 1}` : '';
          lineupStr = `<span style="font-size:.74rem;color:${_lc}" title="Aufstellung (T-1h)">📋 ${_lt}${_more}</span>`;
        }
      }
      const _chips = [pulseStr, lineupStr, trackStr].filter(Boolean)
        .join('<span style="color:#30363d;margin:0 6px">·</span>');
      html += `<div class="cc-actions">
        <div class="cc-data-tier">${_chips}</div>
        <a class="cc-detail-btn" href="matches/wm-match-v2.html?m=${slug}" target="_blank">↗ Analyse</a>
        <button class="cc-share-btn" onclick="window.wmSharePick && window.wmSharePick('${fx.groupKey}-${fx.matchday}-${fx.home}-${fx.away}')">📤 Posten</button>
      </div>`;
    } else {
      html += `<div class="cc-actions">
        <div class="cc-data-tier">
          ${isPlayed ? '<span class="cc-tier-pill">gespielt</span>' : '<span class="cc-tier-pill">beobachten</span>'}
        </div>
        <a class="cc-detail-btn" href="matches/wm-match-v2.html?m=${slug}" target="_blank">↗ Analyse</a>
        <span></span>
      </div>`;
    }

    html += `</div>`; // cc-card
    return html;
  }

  // ─────────────────────────────────────────────────────
  //  KO-CARD BUILDER (25.06.2026, Lucas: KO-Runden)
  //  Kompakte Card für die K.O.-Phase. Zweistufig:
  //   1. bothResolved + Live-Picks → volle (schlanke) Pick-Card.
  //   2. bothResolved, KEINE Picks → Vorschau („Quoten folgen").
  //   3. nicht bothResolved        → Platzhalter (homeRef vs awayRef).
  //  KEINE Gruppen-Standings/Quali-Logik (gibt's für KO nicht).
  // ─────────────────────────────────────────────────────
  function _buildKoCard(fx, home, away, fxOdds, fxPicks, polyFix, todayIso) {
    const kf = fx.koData || {};
    const roundLabel = kf.roundLabel || KO_ROUND_LABELS[kf.round] || 'K.O.-Runde';
    const eloDiff = (home.elo && away.elo) ? (home.elo - away.elo) : null;

    const _finalStatus = ['FT', 'AET', 'PEN', 'AWD', 'WO'].includes(
      ((fx.result && fx.result.status) || '').toUpperCase());
    const isPlayed = _fxIsPast(fx, todayIso);   // kickoff-basiert (27.06.2026)
    const isToday  = fx.date === todayIso;

    // Live-Picks (BET/ABWÄGEN, ohne ausgeschlossene/redundante AH-Linien) —
    // identische Quelle wie Gruppenspiele (_wmLivePicks liest fxPicks).
    const livePicks = _wmLivePicks(fxPicks);
    const sortedPicks = [...livePicks].sort((a, b) => {
      if (a.verdict === 'BET' && b.verdict !== 'BET') return -1;
      if (b.verdict === 'BET' && a.verdict !== 'BET') return 1;
      const _ca = a.convictionScore || 0, _cb = b.convictionScore || 0;
      if (_cb !== _ca) return _cb - _ca;
      return (b.edgePP || 0) - (a.edgePP || 0);
    });

    // ── Card-Klasse / Tier ──
    let cardCls = 'cc-card cc-ko-card';
    if (isPlayed)                                            cardCls += ' cc-played';
    else if (sortedPicks[0] && sortedPicks[0].verdict === 'BET')      cardCls += ' cc-tier-bet';
    else if (sortedPicks[0] && sortedPicks[0].verdict === 'ABWÄGEN')  cardCls += ' cc-tier-abw';
    else                                                    cardCls += ' cc-tier-watch';
    if (isToday) cardCls += ' cc-today';

    const matchKey = `KO-${kf.round || ''}-${fx.home || 'TBD'}-${fx.away || 'TBD'}`;
    let html = `<div class="${cardCls}" data-match-key="${matchKey}">`;

    // ── TOP — Runden-Badge + Teams + Meta ──
    html += `<div class="cc-top">`;
    html += `<div class="cc-angle cc-angle-neutral">🏆 ${roundLabel}${kf.matchNo ? ` · Spiel ${kf.matchNo}` : ''}</div>`;

    if (kf.bothResolved) {
      html += `<div class="cc-teams">
        <div class="cc-team"><span class="cc-flag">${home.flag}</span>${home.name}</div>
        <div class="cc-vs">VS</div>
        <div class="cc-team"><span class="cc-flag">${away.flag}</span>${away.name}</div>
      </div>`;
    } else {
      // Platzhalter: menschenlesbare Referenzen (immer vorhanden).
      html += `<div class="cc-teams cc-teams-tbd">
        <div class="cc-team cc-team-tbd">${kf.homeRef || 'noch offen'}</div>
        <div class="cc-vs">VS</div>
        <div class="cc-team cc-team-tbd">${kf.awayRef || 'noch offen'}</div>
      </div>`;
    }

    const dateMain  = _fmtKickoffMain(fx);          // "So, 28. Jun · 21:00 Uhr" (Wien)
    const localTime = _venueLocalFromKickoff(fx);   // " · 14:00 LA"
    html += `<div class="cc-meta">
      <span>${roundLabel}</span>
      <span class="cc-dot"></span>
      <span>${dateMain}${localTime ? `<span class="cc-local-tz">${localTime}</span>` : ''}</span>
      ${fx.venue ? `<span class="cc-dot"></span><span class="cc-venue">📍 ${fx.venue}</span>` : ''}
    </div></div>`;

    // ── Body: 3 Zustände ──
    if (isPlayed && fx.result && fx.result.home_score != null && fx.result.away_score != null
        && ['FT','AET','PEN'].includes((fx.result.status || 'FT').toUpperCase())) {
      html += `<div class="cc-pick cc-pick-result">
        <div class="cc-pick-label">Endstand</div>
        <div class="cc-pick-market">${fx.result.home_score}:${fx.result.away_score}</div>
      </div>`;
    } else if (!kf.bothResolved) {
      // Zustand 3: Teams stehen noch nicht fest.
      html += `<div class="cc-pick cc-pick-watch">
        <div class="cc-pick-label">Paarung offen</div>
        <div class="cc-pick-watch-text">Teams stehen noch nicht fest</div>
      </div>`;
    } else if (sortedPicks.length) {
      // Zustand 1: bothResolved + Live-Picks → schlanke Pick-Darstellung.
      const hero = sortedPicks[0];
      const isAbw = hero.verdict === 'ABWÄGEN';
      const _cs = (typeof hero.convictionScore === 'number') ? hero.convictionScore : null;
      let stars;
      if (hero.verdict === 'BET') stars = 3;
      else if (isAbw) stars = (_cs != null) ? (_cs >= 7 ? 3 : _cs >= 4 ? 2 : 1) : 2;
      else stars = 1;
      const _net = hero.signalAdjustmentPP;
      if (typeof _net === 'number' && _net <= -2) stars = Math.max(1, stars - 1);
      const oddsStr = hero.odds != null ? hero.odds.toFixed(2) : '—';
      html += `<div class="cc-pick${isAbw ? ' cc-pick-abw' : ''}">
        <div class="cc-pick-label">${isAbw ? 'Vorsichtiger Pick' : 'Unser Pick'}</div>
        <div class="cc-pick-market">${hero.market}${_verdictFlipBadge(hero)}</div>
        <div class="cc-pick-odds"><span class="cc-at">@</span><span class="cc-num">${oddsStr}</span></div>
        <div class="cc-pick-conf">
          ${[1,2,3].map(n => `<span class="cc-star${isAbw ? ' cc-star-abw' : ''} ${n <= stars ? 'cc-star-full' : 'cc-star-empty'}">★</span>`).join('')}
        </div>
        <button class="cc-why-btn" onclick="wmOpenWhy('${matchKey.replace(/['"\\]/g,'')}')" title="Modell-Rechnung, Insights, CLV, Risiko, Stake-Empfehlung">🔍 Warum?</button>
      </div>`;
      // Weitere Picks kompakt darunter.
      for (const p of sortedPicks.slice(1)) {
        const pAbw = p.verdict === 'ABWÄGEN';
        const pOdds = p.odds != null ? p.odds.toFixed(2) : '—';
        html += `<div class="cc-ko-extra-pick">
          <span class="cc-verdict ${pAbw ? 'cc-verdict-abw' : 'cc-verdict-bet'}">${p.verdict}</span>
          <span class="cc-ko-extra-market">${p.market}</span>
          <span class="cc-ko-extra-odds">@ ${pOdds}</span>
        </div>`;
      }
      // Engine-Signale (gleicher Renderer wie Gruppen-Cards) + Form-Block — damit die KO-Card
      // genauso reich ist wie eine normale Card (26.06.2026, Lucas: „steht ja viel mehr drin").
      html += _engineSignalGridHtml(hero);
      const _kf = _wmData.form || {};
      const fH = _kf[fx.home], fA = _kf[fx.away];
      if ((fH && fH.last5) || (fA && fA.last5)) {
        html += `<div class="cc-evidence"><div class="cc-ev-block"><div class="cc-ev-label">Form letzten 5</div>`;
        if (fH && fH.last5) {
          html += `<div class="cc-form">${fH.last5.slice(0,5).map(r => `<div class="cc-form-dot cc-fd-${(r||'').toLowerCase()}">${r}</div>`).join('')}</div>`
            + `<div class="cc-form-team"><span><span class="cc-flag-sm">${home.flag}</span> ${home.name}</span><span>${fH.avgScored != null ? fH.avgScored.toFixed(1)+' Tore Ø' : ''}</span></div>`;
        }
        if (fA && fA.last5) {
          html += `<div class="cc-form" style="margin-top:8px;">${fA.last5.slice(0,5).map(r => `<div class="cc-form-dot cc-fd-${(r||'').toLowerCase()}">${r}</div>`).join('')}</div>`
            + `<div class="cc-form-team"><span><span class="cc-flag-sm">${away.flag}</span> ${away.name}</span><span>${fA.avgScored != null ? fA.avgScored.toFixed(1)+' Tore Ø' : ''}</span></div>`;
        }
        html += `</div></div>`;
      }
    } else {
      // Zustand 2: bothResolved, aber (noch) keine Picks/Quoten. Statt leerem „Quoten folgen"
      // eine echte VORSCHAU aus vorhandenen Daten (Form/Elo/Ø-Tore) — die R32-Quoten von Pinnacle
      // kommen oft erst nah am Anpfiff, die Card soll bis dahin nicht leer wirken (26.06.2026, Lucas).
      const _f = _wmData.form || {};
      const fH = _f[fx.home], fA = _f[fx.away];
      let prev = '';
      if (eloDiff != null && Math.abs(eloDiff) >= 15) {
        const favName = eloDiff > 0 ? home.name : away.name;
        prev += `<div style="font-size:12px;color:var(--muted);margin-bottom:6px;">Elo-Favorit: <b style="color:var(--text);">${favName}</b> (${eloDiff > 0 ? '+' : ''}${eloDiff})</div>`;
      }
      if (fH && fH.last5 && fA && fA.last5) {
        prev += `<div style="display:flex;justify-content:center;gap:16px;align-items:center;margin-bottom:6px;">
          <span style="display:inline-flex;gap:3px;align-items:center;">${home.flag} ${_formDots(fH.last5)}</span>
          <span style="display:inline-flex;gap:3px;align-items:center;">${away.flag} ${_formDots(fA.last5)}</span>
        </div>`;
      }
      if (fH && fA && fH.avgGoals != null && fA.avgGoals != null) {
        prev += `<div style="font-size:11px;color:var(--muted);">Ø Tore/Spiel: ${fH.avgGoals.toFixed(1)} · ${fA.avgGoals.toFixed(1)}</div>`;
      }
      html += `<div class="cc-pick cc-pick-watch">
        <div class="cc-pick-label">Vorschau</div>
        ${prev}
        <div class="cc-pick-watch-text" style="margin-top:8px;">⏳ Quoten folgen</div>
      </div>`;
    }

    // ── Serien + Analyse-Link auch ohne Pick (30.06.2026, Lucas: „Vorschau-Cards zeigen fast nichts —
    //    Serien + Event-Page könnte man zeigen"). Nur wenn beide Teams feststehen — Serien brauchen
    //    echte Teams, und die Event-Page existiert erst dann. Bei TBD bleibt die Card schlank.
    if (kf.bothResolved && fx.home && fx.away) {
      html += _matchStreaksHtml(fx.home, fx.away);
      const _slug = `${_mpPrefix(fx)}-${fx.home.toLowerCase()}-vs-${fx.away.toLowerCase()}-${fx.date}`;
      html += `<div class="cc-actions">
        <div class="cc-data-tier"><span class="cc-tier-pill">${isPlayed ? 'gespielt' : 'beobachten'}</span></div>
        <a class="cc-detail-btn" href="matches/wm-match-v2.html?m=${_slug}" target="_blank">↗ Analyse</a>
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
  // ═══════════════════════════════════════════════════════════════════════════
  //  🔴 04.09.2026 (Lucas-Cards-Check) — WM-GRUPPENLOGIK AUF LIGA-TABELLEN
  //
  //  Auf den Liga-Cards stand als BEGRÜNDUNG eines Picks:
  //
  //      ❌ Beide ausgeschieden — Friendly-Charakter, beide ohne Druck.      (Ipswich–Liverpool, ST 3)
  //      Real Betis braucht zwingend Sieg + Schützenhilfe, Real Madrid bereits sicher.  (La Liga ST 4)
  //      🔥 Aufstiegs-Druck                                                  (PSG–Monaco, Ligue 1 ST 3)
  //
  //  An Spieltag 3 einer Liga ist niemand ausgeschieden und niemand sicher. Die Ursache ist
  //  eine WM-Gruppenregel, die auf eine Liga-Tabelle losgelassen wurde:
  //
  //      const hSafe = hPos <= 2, hOut = hPos > 3;
  //
  //  In einer Vierergruppe heißt das „durch" und „raus". In `standings['ESP']` stehen aber
  //  ZWANZIG Teams (ENG 20, GER 18) — dort ist jedes Team ab Platz 4 „ausgeschieden" und jedes
  //  auf Platz 1–2 „bereits sicher". Damit trug praktisch jede Liga-Card ab ST 3 einen
  //  frei erfundenen Tabellen-Kontext.
  //
  //  Das ist nicht kosmetisch: der Satz steht im „Warum?" und begründet einen Einsatz. Bei
  //  Ipswich–Liverpool stützte „beide ohne Druck" einen Über-2.5-Pick.
  //
  //  Ein WM-Gruppentisch hat vier Teams. Genau daran hängt die Logik ab jetzt — und wo es keine
  //  Gruppe gibt, wird kein Ersatz-Kontext erzählt, sondern gar keiner.
  const _GRUPPE_MAX = 4;
  function _istGruppentabelle(standing) {
    return Array.isArray(standing) && standing.length > 0 && standing.length <= _GRUPPE_MAX;
  }

  function _deriveAngle(pick, fx, eloDiff, polyFix, homeForm, awayForm, standing) {
    // Special: WM-Eröffnungsspiel (BRA vs MAR, Gruppe C, ST 1, 12.06.2026)
    if (fx.groupKey === 'C' && fx.matchday === 1 && fx.home === 'BRA' && fx.away === 'MAR') {
      return { cls: 'cc-a-eroeff', icon: '🎬', label: 'WM-Eröffnungsspiel' };
    }
    // Special: standings-based scenarios (ST 3) — aus dem mathematisch korrekten Qual-Status
    // (incentive_signal, am Fixture als qualHome/qualAway), NICHT aus der Tabellenposition.
    // Bug 23.06.2026: pos<=2 galt als „sicher" → Iran/Uruguay mit 2 Pkt fälschlich „Gruppensieg".
    if (fx.matchday >= 3 && (fx.qualHome || fx.qualAway)) {
      const hL = (fx.qualHome && fx.qualHome.label) || null;
      const aL = (fx.qualAway && fx.qualAway.label) || null;
      const SAFE  = ['qualified', 'can_draw', 'leader_can_draw'];   // faktisch durch (Remis reicht)
      const DRUCK = ['must_win_top2', 'win_secures_top2', 'third_chase', 'eliminated', 'must_win'];
      if (hL === 'eliminated' && aL === 'eliminated')  return { cls: 'cc-a-dead', icon: '❌', label: 'Beide ausgeschieden' };
      if (SAFE.includes(hL) && SAFE.includes(aL))      return { cls: 'cc-a-titel', icon: '🏆', label: 'Spiel um Gruppensieg' };
      if (DRUCK.includes(hL) || DRUCK.includes(aL))    return { cls: 'cc-a-druck', icon: '🔥', label: 'Aufstiegs-Druck' };
    } else if (_istGruppentabelle(standing) && fx.matchday >= 3) {
      // Fallback (alte Positions-Heuristik) bis qualHome/qualAway im Payload sind — NUR in einer
      // echten Vierergruppe, siehe _istGruppentabelle.
      const homePos = standing.findIndex(s => s.team === fx.home) + 1;
      const awayPos = standing.findIndex(s => s.team === fx.away) + 1;
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

    // Anti-Drift-Fix 09.06.2026 — Klassen-Unterschied schlägt Tor-/Defensiv-Label.
    // Bei großem Elo-Vorsprung (>= 250) ist "Defensiv-Schlacht" bei Unter X.5
    // oder "Tor-Fest" bei Über X.5 inhaltlich falsch — es ist eine kontrollierte
    // Dominanz, kein Duell. Vorher: ESP-CPV (Elo +370) als "Defensiv-Schlacht"
    // getitelt, obwohl 88% ESP-Sieg-Wahrscheinlichkeit.
    const isLopsided = (eloDiff != null && Math.abs(eloDiff) >= 250);
    if (isLopsided) {
      return { cls: 'cc-a-pflicht', icon: '🏆', label: 'Klassen-Unterschied' };
    }
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
      // H2H-Trend — Anti-Drift-Fix: erst ab n=3 Spielen sinnvoll, sonst "100%"-Artefakt bei n=1
      if (h2h && h2h.over25Rate != null && h2h.over25Rate >= 0.6 && (h2h.games || 0) >= 3 && parts.length < 2) {
        parts.push(`H2H ${Math.round(h2h.over25Rate*100)}% Ü2.5 (${h2h.games} Spiele)`);
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
      // Anti-Drift-Fix 09.06.2026: H2H-Rate erst ab n=3 vertrauenswürdig (n=1 gibt 0% oder 100% Artefakte).
      if (h2h && h2h.over25Rate != null && h2h.over25Rate < 0.5 && (h2h.games || 0) >= 3 && parts.length < 2) {
        parts.push(`H2H ${Math.round((1-h2h.over25Rate)*100)}% Unter 2.5 (${h2h.games} Spiele)`);
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
      // Anti-Drift-Fix 09.06.2026 — "Form schlägt Elo" darf nur greifen wenn
      // UNSER Team auch wirklich BESSER ist als der Gegner. Vorher: bei KOR
      // (3W) vs CZE (4W) wurde "Korea Form schlägt Elo" gepickt, obwohl CZE
      // bessere Form hatte. Jetzt: nur wenn home.wins > away.wins UND home.wins >= 3.
      const homeWins = _formWins(homeForm);
      const awayWins = _formWins(awayForm);
      if (homeStreak >= 4) {
        sentence1 = `<strong>${home.name} ${homeStreak} Siege in Folge</strong> — Form heißer als Quoten zeigen.`;
      } else if (homeLossSt >= 3) {
        sentence1 = `<strong>${away.name} ${homeLossSt} Niederlagen in Folge</strong> — Krise wird vom Markt unterschätzt.`;
      } else if (favDiff >= 200) {
        sentence1 = `<strong>${home.name} Elo +${favDiff}</strong> über ${away.name} — klassische Heim-Pflichtaufgabe.`;
      } else if (favDiff >= 80) {
        sentence1 = `<strong>${home.name}</strong> favorisiert${homeForm && homeForm.last5 ? ` (Form ${homeForm.last5.join('')})` : ''}.`;
      } else if (homeWins >= 3 && homeWins > awayWins) {
        // Nur wenn unser Team echt bessere Form als Gegner hat
        sentence1 = `<strong>${home.name} ${homeWins} Siege in 5</strong> — Form besser als ${away.name} (${awayWins}/5).`;
      } else {
        sentence1 = `<strong>${home.name}</strong> Heim-Bonus + Quoten-Edge.`;
      }
    }
    else if (m.includes('auswärt') || m.includes('away') || /^2$/.test(m)) {
      const favDiff = -(eloDiff || 0);
      const awayStreak = _winStreak(awayForm);
      const homeLossSt = _lossStreak(homeForm);
      const homeWins = _formWins(homeForm);
      const awayWins = _formWins(awayForm);
      if (awayStreak >= 4) {
        sentence1 = `<strong>${away.name} ${awayStreak} Siege in Folge</strong> — Quoten haben Form-Lauf nicht eingepreist.`;
      } else if (homeLossSt >= 3) {
        sentence1 = `<strong>${home.name} ${homeLossSt} Niederlagen in Folge</strong> — Markt traut der Krise nicht.`;
      } else if (favDiff >= 200) {
        sentence1 = `<strong>${away.name} Elo +${favDiff}</strong> über ${home.name} — Pflichtsieg-Favorit auswärts.`;
      } else if (awayWins >= 3 && awayWins > homeWins) {
        sentence1 = `<strong>${away.name} ${awayWins} Siege in 5</strong> — Form besser als ${home.name} (${homeWins}/5).`;
      } else {
        sentence1 = `<strong>${away.name}</strong> Auswärts-Form mit Edge.`;
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
      if ((leg.burden || '').toLowerCase() === 'significant' || (leg.km || 0) >= 3000) {
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
      const verb = pb.direction === 'over' ? 'pumpt' : 'lässt links liegen';
      const target = ocTeam ? `${ocTeam} (${ocName})` : ocName;
      sentences.push(`💸 Die Masse bei <strong>${pb.bookmaker}</strong> ${verb} ${target} um <strong>${pb.pp}pp</strong> gegenüber Pinnacle — die Sharps sehen's andersrum.`);
    }

    // 3) ST3 Standings-Druck (Aufstiegs-Kontext) — aus dem mathematisch korrekten Qual-Status
    //    (incentive_signal, fx.qualHome/qualAway). Bug 23.06.2026: vorher Tabellen-POSITION
    //    (pos<=2='sicher', pos>3='muss') → Iran/Uruguay (2 Pkt, Platz 2) fälschlich „schon
    //    Achtelfinale", Platz-3-Teams (müssen meist gewinnen) gar nicht erwähnt.
    if (fx.matchday >= 3 && (fx.qualHome || fx.qualAway)) {
      const _phrase = (team, q) => {
        if (!q || !q.label) return null;
        const t = `${team.flag} ${team.name}`;
        switch (q.label) {
          case 'qualified':       return `${t} ist schon durch`;
          case 'leader_can_draw': return `${t} führt — ein Remis reicht fürs Achtelfinale, ein Sieg für Platz 1`;
          case 'can_draw':        return `${t} reicht schon ein Remis fürs Achtelfinale`;
          case 'win_secures_top2':return `${t} ist mit einem Sieg sicher unter den Top 2`;
          case 'must_win_top2':   return `${t} braucht einen Sieg für die Top 2`;
          case 'third_chase':     return `${t} kann nur noch über den besten Dritten weiter — ein Sieg muss her`;
          case 'eliminated':      return `${t} ist ausgeschieden`;
          case 'must_win':        return `${t} muss gewinnen, um weiterzukommen`;  // Legacy-Fallback
          default:                return null;
        }
      };
      const hq = fx.qualHome, aq = fx.qualAway;
      if (hq && aq && hq.label === 'qualified' && aq.label === 'qualified') {
        sentences.push(`<strong>Beide schon durch</strong> — Rotation + Schonung möglich.`);
      } else if (hq && aq && hq.label === 'eliminated' && aq.label === 'eliminated') {
        sentences.push(`<strong>Beide ausgeschieden</strong> — Friendly-Charakter, beide ohne Druck.`);
      } else {
        const hp = _phrase(home, hq), ap = _phrase(away, aq);
        if (hp) sentences.push(`<strong>${hp}</strong>.`);
        if (ap) sentences.push(`<strong>${ap}</strong>.`);
      }
    } else if (fx.matchday >= 3 && _istGruppentabelle(standing)) {
      // Fallback (alte Positions-Heuristik) bis qualHome/qualAway im Payload sind — NUR in einer
      // echten Vierergruppe. Auf einer 20er-Liga-Tabelle war „Platz > 3" = ausgeschieden.
      const hPos = standing.findIndex(s => s.team === fx.home) + 1;
      const aPos = standing.findIndex(s => s.team === fx.away) + 1;
      if (standing.find(s => s.team === fx.home) && standing.find(s => s.team === fx.away)) {
        const hSafe = hPos <= 2, aSafe = aPos <= 2, hOut = hPos > 3, aOut = aPos > 3;
        if (hSafe && aSafe) sentences.push(`<strong>Beide schon Achtelfinale</strong> — Rotation + Schonung wahrscheinlich.`);
        else if (hOut && aOut) sentences.push(`<strong>Beide ausgeschieden</strong> — Friendly-Charakter, beide ohne Druck.`);
        else if (hOut && aSafe) sentences.push(`<strong>${home.flag} ${home.name} braucht zwingend Sieg + Schützenhilfe</strong>, ${away.name} bereits sicher.`);
        else if (aOut && hSafe) sentences.push(`<strong>${away.flag} ${away.name} muss alles riskieren</strong>, ${home.name} bereits sicher.`);
        else if (hOut) sentences.push(`<strong>${home.flag} ${home.name} im Aufstiegs-Modus</strong> — Sieg Pflicht.`);
        else if (aOut) sentences.push(`<strong>${away.flag} ${away.name} im Aufstiegs-Modus</strong> — Sieg Pflicht.`);
      }
    }

    // Sentence 2 — Modell vs Markt
    // 17.06.2026: Steam-Picks NICHT als „Edge minimal" framen — bei einem bestätigten Move
    // ist der Rest-Edge bauartbedingt ~0; der Wert steckt im Drop, nicht im Restpreis.
    let modelSentence = '';
    if (pick.reverserCounter) {
      modelSentence = `<em>Hier dreht das frische Pinnacle-Geld auf die Gegenseite. Wir nehmen lieber die sichere Linie als blind auf den Gegen-Sieg zu gehen — die wird erst mit mehr Bestätigung zur echten Wette.</em>`;
    } else if (pick.source === 'steam' && pick.reverser) {
      modelSentence = `<em>Pinnacle ist von ${(+pick.steamOpen).toFixed(2)} auf ${(+pick.steamCur).toFixed(2)} gelaufen, aber das frische Geld dreht jetzt gegen den Pick — der Move ist überholt, wir stufen zurück.</em>`;
    } else if (pick.source === 'steam' && pick.steamMovePP) {
      // Drift-Halten (Roh-Quote steht, Signal ist markt-relativ) ehrlich vom echten Quotensturz trennen.
      // Roh-pp aus den Quoten rechnen, falls das Feld auf alten Picks fehlt.
      let _mvRaw = pick.steamMoveRawPP;
      if (_mvRaw == null && pick.steamOpen > 1 && pick.steamCur > 1)
        _mvRaw = (1 / (+pick.steamCur) - 1 / (+pick.steamOpen)) * 100;
      const _dh = (_mvRaw != null && Math.abs(pick.steamMovePP - _mvRaw) >= 1.5);
      modelSentence = _dh
        ? `<em>Pinnacle hielt die Quote bei ${(+pick.steamCur).toFixed(2)}, während der restliche Markt wegdriftete — relativ zum Markt ein +${pick.steamMovePP}pp-Sharp-Signal. Der Wert steckt im Halten, nicht im Restpreis.</em>`
        : `<em>Pinnacle ist von ${(+pick.steamOpen).toFixed(2)} auf ${(+pick.steamCur).toFixed(2)} gefallen (+${pick.steamMovePP}pp) — der Wert steckt im Move selbst, nicht mehr im Restpreis.</em>`;
    } else if (pick.modelOdds != null && pick.odds != null) {
      const epp = pick.edgePP != null ? pick.edgePP : 0;
      const tier = epp >= 12 ? 'einen massiven' : epp >= 6 ? 'einen soliden' : epp >= 3 ? 'einen kleinen' : 'kaum';
      modelSentence = `<em>Unser Modell sieht ${pick.modelOdds.toFixed(2)}, der Markt bietet ${pick.odds.toFixed(2)} — macht ${tier} Vorsprung (+${epp}pp).</em>`;
    } else if (pick.info) {
      modelSentence = `<em>${pick.info}</em>`;
    }

    // BET-Lebenszyklus: seit wann BET + „hält trotz ruhendem Move" (18.06.2026)
    let betLifeSentence = '';
    if (pick.verdict === 'BET' && pick.firstBetAt) {
      const since = new Date(pick.firstBetAt);
      if (!isNaN(since)) {
        const hrs = Math.max(0, (Date.now() - since.getTime()) / 3600000);
        const ago = hrs < 24 ? `${Math.round(hrs)}h` : `${Math.round(hrs / 24)} Tg`;
        betLifeSentence = pick.betHeld
          ? `<em style="color:#3fb950;">✅ BET seit ${ago} — hält: Move ruht, aber kein Gegen-Geld.</em>`
          : `<em style="color:#8b949e;">BET seit ${ago}.</em>`;
      }
    }

    return sentences.join(' ')
      + (modelSentence ? '<br>' + modelSentence : '')
      + (betLifeSentence ? '<br>' + betLifeSentence : '')
      + _smartMoneyBox(pick);
  }

  // 💰 Smart-Money-Box (violett, 19.06.2026): Poly-Geldverteilung + Top-Trader. Reine Anzeige.
  function _smartMoneyBox(pick) {
    const sm = pick && pick.smartMoney;
    if (!sm || !sm.outcomes) return '';
    const o = sm.outcomes;
    const pct = v => (v && v.share != null) ? Math.round(v.share * 100) : null;
    const h = pct(o.home), d = pct(o.draw), a = pct(o.away);
    if (h == null && a == null) return '';
    const usd = sm.totalUsd ? (sm.totalUsd >= 1e6 ? `$${(sm.totalUsd/1e6).toFixed(1)}M` : `$${Math.round(sm.totalUsd/1e3)}k`) : '';
    const parts = [];
    if (h != null) parts.push(`Heim ${h}%`);
    if (d != null) parts.push(`Unent. ${d}%`);
    if (a != null) parts.push(`Ausw. ${a}%`);
    // Der eigentliche „Smart"-Teil (20.06.2026): hat das Geld auf UNSERER Pick-Seite den fairen
    // Pinnacle-Preis übertroffen? Kommt aus dem smart_money-Signal am Pick (nur wenn es gefeuert
    // hat — 1X2/DC/AH). Roher Split allein spiegelt nur den Favoriten; erst der Überschuss ist Signal.
    let edgeLine = '';
    let clusterLine = '';
    const sig = (pick.signals || []).find(s => s && s.name === 'smart_money');
    if (sig && sig.metadata && sig.metadata.excessPP != null) {
      const m = sig.metadata;
      const sideLbl = { home: 'Heim', draw: 'Unent.', away: 'Ausw.' }[m.outcome] || m.outcome;
      const moneyPct = Math.round((m.share || 0) * 100);
      const fairPct  = Math.round((m.fairShare || 0) * 100);
      const exc = m.excessPP;
      edgeLine = `<br><span style="color:${exc > 0 ? '#3fb950' : '#8b949e'};">→ auf ${sideLbl} `
        + `${moneyPct}% Geld vs. ${fairPct}% fair (${exc > 0 ? '+' : ''}${exc}pp ${exc > 0 ? 'mehr als der Markt rechtfertigt' : 'darunter'})</span>`;
      // Konsens-Cluster (22.06.2026): ≥N unabhängige Wale sammeln dieselbe Seite ein → Verstärkung;
      // Whale-Exit nah am Anpfiff → Warnung (Conviction kippt). Kommt aus sig.metadata.
      if (m.clustered && m.cluster) {
        clusterLine = `<br><span style="color:#5eead4;">🐋 ${m.cluster} große Wallets sammeln gerade dieselbe Seite ein</span>`;
      }
      if (m.exitFlag) {
        const net = Math.abs(m.netFlowUsd || 0);
        const netLbl = net >= 1000 ? `$${Math.round(net/1000)}k` : `$${Math.round(net)}`;
        clusterLine += `<br><span style="color:#ff7b5d;">⚠️ Wale verkaufen kurz vor Anpfiff netto ${netLbl} hier — Überzeugung kippt</span>`;
      }
    }
    const tip = `Verfolgt wird das offene Interesse der größten Wallets je Ausgang auf Polymarket — `
      + `NICHT das Gesamtvolumen des Marktes (das ist höher). ${usd} = Summe dieser Top-Positionen`
      + (sm.topTraders != null ? `, davon ${sm.topTraders} Wallets über $1.000.` : '.');
    return `<div style="margin-top:6px;padding:6px 9px;border-radius:8px;background:rgba(167,139,250,.10);border:1px solid rgba(167,139,250,.35);font-size:.76rem;color:#c4b5fd;" title="${tip}">
      💰 <strong>Smart Money</strong> — wo die großen Wallets liegen<br>
      <span style="color:#8b949e;">${usd} verfolgt${sm.topTraders != null ? ` · ${sm.topTraders} Wallets &gt;$1k` : ''}</span><br>
      <span style="color:#a78bfa;">${parts.join(' · ')}</span>${edgeLine}${clusterLine}
    </div>`;
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
      // (26.06.2026, Lucas) dataset-bewusst: wm-index.json bzw. liga-index.json
      const _idxPfx = _mode === 'liga' ? 'liga' : 'wm';
      const idxResp = await fetch(`matches/${_idxPfx}-index.json` + bust);
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
    // Slug-Format wie in generate_wm_match_pages.py: {wm|liga|mls}-{home_lower}-vs-{away_lower}-{date}
    const slug = `${_mpPrefix(fx)}-${(fx.home||'').toLowerCase()}-vs-${(fx.away||'').toLowerCase()}-${fx.date}`;
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

    const _clvTooltip = clvPositive
      ? 'Closing Line Value positiv: der Markt hat sich seit Eröffnung in Richtung unseres Picks bewegt — typisches Sharp-Signal.'
      : 'Closing Line Value negativ: der Markt hat sich gegen unseren Pick bewegt.';
    return `<div class="cc-odds-strip">
      <div class="cc-os-drift">
        <span class="cc-os-label">Quote</span>
        <span class="cc-os-open">${openOdds.toFixed(2)}</span>
        <span class="cc-os-arrow">→</span>
        <span class="cc-os-now ${cls}">${nowOdds.toFixed(2)} ${arrow}</span>
        <span class="cc-os-pp ${cls}">${ppLabel}</span>
        <span class="cc-os-clv cc-clv-${cls}" title="${_clvTooltip}">${clvLabel}</span>
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

    // ── Incentive-Signal Insight (Bracket-Anreiz / Venue / Dead-Rubber / Rotation) ──
    // Liest pro Pick die signals[] Liste und extrahiert incentive_signal,
    // wenn es signifikant gefeuert hat (|score| >= 1.0pp). Übersetzt die
    // Komponenten-Outputs in eine narrativ verständliche Erklärung mit
    // Team-Namen — kein Engineer-Speak.
    if (Array.isArray(pick.signals)) {
      const inc = pick.signals.find(s => s && s.name === 'incentive_signal');
      if (inc && typeof inc.score === 'number' && Math.abs(inc.score) >= 1.0) {
        const positive = inc.score > 0;
        const ev = (inc.evidence || '').replace(/^🎯\s*/, '');

        // Welches Team steht im Fokus des Anreizes?
        // Bei Heim-Pick → home, bei Auswärts-Pick → away, sonst neutral
        const _m = (pick.market || '').toLowerCase();
        const focusTeam = _m.includes('heim') ? home
                       : (_m.includes('ausw') ? away : null);
        const focusName = focusTeam ? focusTeam.name : 'das Team';

        // Headline je nach Komponenten in evidence-String
        let intro = positive
          ? `${focusName} hat einen klaren sportlichen Anreiz, dieses Spiel zu gewinnen`
          : `${focusName} hat strukturellen Gegenwind in diesem Spiel`;
        if (ev.toLowerCase().includes('dead') || ev.toLowerCase().includes('beide teams bereits')) {
          intro = `Spiel ohne sportlichen Druck — beide Teams stehen schon im Achtelfinale`;
        } else if (ev.toLowerCase().includes('rotation') || ev.toLowerCase().includes('pause')) {
          intro = positive
            ? `Kurze Pause zur nächsten Runde — Favorit rotiert wahrscheinlich, Tor-Erwartung sinkt`
            : `Nur kurze Pause zur nächsten Runde — Favorit schont Stammspieler`;
        } else if (ev.toLowerCase().includes('muss gewinnen')) {
          intro = `Klare Anreiz-Asymmetrie zwischen den Teams`;
        }

        candidates.push({
          score: Math.abs(inc.score) * 15 + 25,   // priorisiert über Form-Signale
          txt: `<strong>${intro}.</strong> ${ev.charAt(0).toUpperCase() + ev.slice(1)}. ` +
               `Engine-Bewertung: <strong style="color:var(${positive ? '--accent' : '--red'});">` +
               `${inc.score > 0 ? '+' : ''}${inc.score.toFixed(1)}pp</strong>.`,
          tag: 'Anreiz', tagCls: positive ? 'wm-tag-sharp' : 'wm-tag-warn',
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
    // Steam-Confirmed-Badge (17.06.2026): Linie stark in unsere Richtung gelaufen →
    // bestätigter Move (auf Poly geritten), auch wenn die Karten-Edge konvergiert ist.
    const steamBadge = pick.steamConfirmed
      ? `<div class="wm-steam-confirmed" title="Pinnacle-Move ist eingetreten und von Soft-Quoten bestätigt. Der Wert am Buch ist abgeschmolzen — auf Polymarket wird der Move geritten. Kein frischer Value-Einstieg mehr.">🔥 Move bestätigt${pick.steamFollowPP ? ` +${pick.steamFollowPP.toFixed(0)}pp` : ''} · geritten auf Poly</div>`
      : '';

    // Safer-Line-Ableitung (17.06.2026): der Sharp-Move lief auf einer riskanten Linie,
    // gewettet wird die sichere Linie. Move = These, sichere Linie = Wette.
    const safeBadge = pick.safeDerived
      ? `<div class="wm-safe-derived" title="Der Sharp-Money-Move lief auf der riskanten Linie. Zum Wetten leiten wir die nächst-sichere Linie ab (höhere Trefferquote), solange ihre Quote ≥ 1,35 bleibt. Der Move bleibt die These.">🎯 Move auf <strong>${pick.safeThesisMarket}</strong>${pick.safeThesisOdds ? ` @${(+pick.safeThesisOdds).toFixed(2)}` : ''} → sichere Wette: <strong>${pick.market}</strong></div>`
      : '';

    // Time-Label
    let timeLabel = '';
    try {
      // Aus echtem kickoff (UTC) → Wien (CEST UTC+2); Fallback alte date+time-Felder.
      const _ko = fx.kickoff ? new Date(fx.kickoff) : new Date(`${fx.date}T${fx.time || '19:00'}:00Z`);
      const _v  = new Date(_ko.getTime() + 2 * 3600 * 1000);
      const wd  = ['So','Mo','Di','Mi','Do','Fr','Sa'][_v.getUTCDay()];
      timeLabel = `${wd} ${String(_v.getUTCDate()).padStart(2,'0')}.${String(_v.getUTCMonth()+1).padStart(2,'0')}. · ${String(_v.getUTCHours()).padStart(2,'0')}:${String(_v.getUTCMinutes()).padStart(2,'0')}`;
    } catch (e) {}

    // ── 1. MODELL-RECHNUNG ──
    const elo_h = matchPage?.homeElo || home.elo;
    const elo_a = matchPage?.awayElo || away.elo;
    // FIX 12.06.2026: Modell-Tor-Erwartung (λ aus dem Pick) bevorzugen vor der
    // matchPage-xG — sonst stand eine FREMDE xG (z.B. 2.87) neben der Modell-Prob
    // (z.B. 85%), die auf einem anderen λ (~3.3) beruht → wirkte unstimmig.
    const lamH = (typeof pick.lamH === 'number') ? pick.lamH : null;
    const lamA = (typeof pick.lamA === 'number') ? pick.lamA : null;
    const goalH = lamH != null ? lamH : matchPage?.xgHome;
    const goalA = lamA != null ? lamA : matchPage?.xgAway;
    const goalLabel = lamH != null ? 'Modell-Tor-Erwartung (H / A)' : 'xG Erwartung (H / A)';
    const probMarket  = pick.odds      ? Math.round(100 / pick.odds)      : null;
    const probModel   = pick.modelOdds ? Math.round(100 / pick.modelOdds) : null;
    let calcRows = '';
    if (elo_h && elo_a) {
      calcRows += `<div class="wm-calc-row"><span class="wm-calc-label">Elo (${home.name} / ${away.name})</span><span class="wm-calc-val">${elo_h} / ${elo_a} (${eloDiff > 0 ? '+' : ''}${eloDiff})</span></div>`;
    }
    if (goalH != null && goalA != null) {
      calcRows += `<div class="wm-calc-row"><span class="wm-calc-label">${goalLabel}</span><span class="wm-calc-val">${goalH.toFixed(2)} / ${goalA.toFixed(2)} <em style="opacity:.6">(Σ ${(goalH + goalA).toFixed(2)})</em></span></div>`;
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
      calcRows += `<div class="wm-calc-row"><span class="wm-calc-label">Modell-Quote → Markt-Quote</span><span class="wm-calc-val acc">${(pick.modelOdds||0).toFixed(2)} → ${oddsStr} = +${pick.edgePP}pp Edge (roh)</span></div>`;
    }
    if (typeof pick.effectiveEdgePP === 'number' && pick.effectiveEdgePP !== pick.edgePP) {
      const eff = pick.effectiveEdgePP;
      const effCls = eff >= pick.edgePP ? 'acc' : 'neg';
      calcRows += `<div class="wm-calc-row"><span class="wm-calc-label">Edge nach Engine-Adjustment</span><span class="wm-calc-val ${effCls}">${eff > 0 ? '+' : ''}${eff}pp <em style="opacity:0.7;">(${eff > pick.edgePP ? 'verstärkt' : 'gedämpft'})</em></span></div>`;
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
        const won = Math.round(conf.rate / 100 * conf.n);
        const scopeLabel = {
          cluster: 'praktisch identischen',
          market:  `${pick.market}-`,
          angle:   'ähnlichen',
          global:  'allen WM-',
        }[conf.scope] || 'vergleichbaren';
        backtestBlock = `<div class="wm-section">
          <div class="wm-section-label">📊 Historischer Backtest</div>
          <div class="wm-backtest">
            <div class="wm-bt-num">${won}/${conf.n}</div>
            <div class="wm-bt-text">
              Von <strong>${conf.n} ${scopeLabel}Wetten</strong> haben <strong>${won}</strong> getroffen (${conf.rate}%).
              ${conf.n < 5 ? 'Noch kleine Stichprobe — nur grobe Orientierung.' : conf.rate >= 55 ? 'Solide Validierung des Modells.' : conf.rate >= 45 ? 'Mittlere Validierung — Edge nicht garantiert.' : 'Underperformance — Pick mit Vorsicht.'}
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
            ${safeBadge}
            ${steamBadge}
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

      ${(() => {
        // ── Engine-Signale (sharp_signals/) — pro-Signal Breakdown ──
        const sigs = Array.isArray(pick.signals) ? pick.signals : [];
        if (!sigs.length) return '';
        const adj = pick.signalAdjustmentPP;
        const adjStr = (typeof adj === 'number')
          ? `<span class="wm-sig-adj ${adj > 0 ? 'pos' : (adj < 0 ? 'neg' : '')}">Netto ${adj > 0 ? '+' : ''}${adj.toFixed(1)}pp</span>`
          : '';
        // Signal-Vorzeichen = Richtung zur WETTE: score > 0 stützt den Pick (bestätigt
        // den Move), score < 0 spricht dagegen. 17.06.2026: klar in Dafür/Dagegen gruppiert
        // (Lucas) — der Public sieht sofort, welche Signale den Drop bestätigen.
        const _row = (s) => `
          <div class="wm-sig-row">
            <div class="wm-sig-name">${s.name.replace(/_/g, ' ')}</div>
            <div class="wm-sig-evidence">${s.evidence}</div>
            <div class="wm-sig-score ${s.score > 0 ? 'pos' : 'neg'}">${s.score > 0 ? '+' : ''}${s.score.toFixed(1)}pp</div>
            <div class="wm-sig-conf">conf ${(s.confidence * 100).toFixed(0)}%</div>
            <div class="wm-sig-weight">w ${(s.weight || 1).toFixed(2)}</div>
          </div>`;
        const _byMag = (a, b) => Math.abs(b.score) - Math.abs(a.score);
        const pro     = sigs.filter(s => s.score > 0).sort(_byMag);
        const contra  = sigs.filter(s => s.score < 0).sort(_byMag);
        const neutral = sigs.filter(s => s.score === 0).length;
        const _group = (title, cls, arr) => arr.length
          ? `<div class="wm-sig-group-head ${cls}">${title} · ${arr.length}</div>
             <div class="wm-sig-table">${arr.map(_row).join('')}</div>`
          : '';
        return `<div class="wm-section">
          <div class="wm-section-label">🧠 Engine-Signale — was bestätigt den Move ${adjStr}</div>
          ${_group('✅ Dafür — stützen den Pick', 'pro', pro)}
          ${_group('⚠️ Dagegen — sprechen dagegen', 'contra', contra)}
          <div class="wm-sig-note">
            Vorzeichen = Richtung zur Wette: <strong>+pp dafür</strong>, <strong>−pp dagegen</strong>.
            ${neutral ? `${neutral} Signal${neutral !== 1 ? 'e' : ''} neutral (nicht gezeigt). ` : ''}
            Nur getriggerte Signale; die volle Liste inkl. nicht-feuernder steht auf der Event-Page.
            Gewichte (w) lernen nach jedem aufgelösten Pick via Bayesian-Update.
          </div>
        </div>`;
      })()}

      ${(() => {
        // ── Conviction-Familien-Tabelle (Modal-Block, NEU 09.06.2026) ──
        // Zeigt im Modal welche Familien zur Conviction beigetragen haben.
        if (typeof pick.convictionScore !== 'number') return '';
        const score = pick.convictionScore;
        if (score < 1) return '';
        const fams = pick.convictionFamilies || {};
        const rows = [
          ['Sharp-Money (Pinnacle-Move + Softbook-Konsens-Lag)',      fams.sharp_money || 0, 3],
          ['Modell-Stack (Form + xG + H2H + Injury + Modell-Sanity)', fams.model_stack || 0, 3],
          ['Kontext (Travel + Lineup-T1h + Wetter + Druck + Anreiz)', fams.context     || 0, 3],
          ['Markt-Konsens (Public-Bias + APIF-Predictions)',          fams.market      || 0, 1],
        ];
        const famHtml = rows.map(([n, v, max]) => {
          const cls = v > 0 ? 'pos' : '';
          return `<div class="wm-fam-row ${cls}">
            <span class="wm-fam-name">${n}</span>
            <span class="wm-fam-val">+${v} / max ${max}</span>
          </div>`;
        }).join('');
        const pct = (score / 10) * 100;
        const label = pick.convictionLabel
          || (score >= 8 ? '🎯 Top-Wette' : score >= 6 ? '⭐ Gute Wette' : score >= 4 ? '👁 Beobachten' : '');
        return `<div class="wm-section">
          <div class="wm-section-label">🏅 Conviction-Score — wie überzeugt ist das System</div>
          <div class="wm-conv-modal">
            <div class="wm-conv-modal-head">
              <span>${label}</span>
              <span class="wm-conv-modal-score">${score}/10</span>
            </div>
            <div class="wm-conv-modal-bar">
              <div class="wm-conv-modal-fill" style="width:${pct}%;"></div>
              <div class="wm-conv-modal-target" title="8+ = Top-Wette"></div>
            </div>
            <div class="wm-conv-modal-fams">${famHtml}</div>
            <div class="wm-conv-modal-explain">
              Conviction zählt unabhängige Bestätigungs-Quellen. Bei 8+/10 darf ein ABWÄGEN auf BET hochgestuft werden.
              Bayesian-Loop kalibriert die Gewichte nach jedem resolved Pick.
              <br><br>
              <strong>Polymarket-Signale (polymarket_sharp, steam_lag) zählen hier NICHT</strong> —
              Polymarket ist Trade-Gegenseite (siehe Polytrade-Tab), kein Sharp-Anker.
            </div>
          </div>
        </div>`;
      })()}

      ${clvBlock}
      ${backtestBlock}

      <div class="wm-section">
        <div class="wm-section-label">⚙️ Pick-Pipeline — wie der Pick entstanden ist</div>
        <div class="wm-pipe">
          <div class="wm-pipe-step"><strong>1. Elo + xG-Modell</strong> → fair-Quote pro Markt</div>
          <div class="wm-pipe-step"><strong>2. Edge-Filter</strong> → nur Märkte mit Edge ≥ Mindestschwelle (1X2: 5pp, AH/O/U: 4pp)</div>
          <div class="wm-pipe-step"><strong>3. Modell-Bias-Schutz</strong> → O/U-Edge >10pp bzw. AH-Edge >12pp wird auf ABWÄGEN downgegradet (Stress-Indikator)</div>
          <div class="wm-pipe-step"><strong>4. Cross-Model-Check</strong> → DNB ↔ AH +0.5 vergleicht Elo- gegen Skellam-Implied. Bei Divergenz ≥ 8pp → BET wird ABWÄGEN${(pick.downgradedReason || '').includes('Modell-Inkonsistenz') ? ' <em style="color:var(--yellow);">← griff hier</em>' : ''}</div>
          <div class="wm-pipe-step"><strong>5. Cross-Market-Konflikt</strong> → unvereinbare Direction-Picks (z.B. Heim + AH Auswärts) → schwächerer aus Card/Tracking gefiltert (auch BET-vs-ABWÄGEN, neu 09.06.)${(pick.downgradedReason || '').includes('Konflikt') ? ' <em style="color:var(--yellow);">← griff hier</em>' : ''}</div>
          <div class="wm-pipe-step"><strong>6. Smart-Substitution</strong> → bei hoher Quote (>2.30): sicherere Alternative gesucht. Wenn zwei Originale auf dieselbe Alt zeigen, wird sie nur einmal als Insurance angeboten (Dedup neu 09.06.)</div>
          <div class="wm-pipe-step"><strong>7. Verlust-Markt-Filter</strong> → Corner-Linien für WM deaktiviert. BTTS am 09.06. reaktiviert mit Conviction-Gate, weil alter Skellam-Loss vor der Signal-Engine entstand</div>
          <div class="wm-pipe-step"><strong>8. Signal-Engine (14 Signale)</strong> → Sharp: lead_lag, polymarket_sharp, steam_lag · Modell: form_trend, h2h_pattern, xg_strength, injury · Kontext: travel_burden, weather, pressure_index, incentive, lineup · Markt: public_static_bias, apif_predictions. Seit 09.06. mit O/U+BTTS-Coverage in form_trend/h2h/xg/travel/public_bias.</div>
        </div>
      </div>

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
      if (h2h?.over25Rate != null && (h2h.games || 0) >= 3 && signals.length < 4) {
        const v = Math.round(h2h.over25Rate * 100);
        signals.push({ label: `Ü2.5 H2H (${h2h.games})`, value: v + '%', cls: v >= 50 ? 'cc-val-hot' : '' });
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
    const relLeg = (leg) => leg && !leg.same_venue && ((leg.km || 0) >= 3000 || ['critical','significant'].includes((leg.burden||'').toLowerCase()));
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
  // Anti-Drift-Fix 09.06.2026: Streak NUR aus last5 (was die Card auch anzeigt).
  // Vorher: Fallback auf last10 → "3 Siege in Folge" Claim aus last10 [..W,W,W],
  // während Card-Pille die last5 [L,W,D,W,L] zeigt und User keine Serie sieht.
  // Konsistenz: was die Card behauptet muss in der angezeigten Form sichtbar sein.
  function _winStreak(form) {
    const arr = form?.last5;
    if (!Array.isArray(arr)) return 0;
    let s = 0;
    for (let i = arr.length - 1; i >= 0; i--) {
      if (arr[i] === 'W') s++; else break;
    }
    return s;
  }
  function _lossStreak(form) {
    const arr = form?.last5;
    if (!Array.isArray(arr)) return 0;
    let s = 0;
    for (let i = arr.length - 1; i >= 0; i--) {
      if (arr[i] === 'L') s++; else break;
    }
    return s;
  }
  // Anzahl Siege in last5 (NICHT consecutive) — für Form-Vergleichs-Logik
  function _formWins(form) {
    const arr = form?.last5;
    if (!Array.isArray(arr)) return 0;
    return arr.filter(r => r === 'W').length;
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
    const cls = burden === 'critical'    ? 'cc-env-heat'
              : burden === 'significant' ? 'cc-env-alt'
              :                            'cc-env-pill';
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

  // ── Authoritative Zeit-Anzeige aus fx.kickoff (UTC ISO) ───────────────────
  // fx.time ist ein UNZUVERLÄSSIGES Seed-Feld: mal Wien-Zeit (MEX-ZAF "21:00"),
  // mal Venue-Local (BRA-MAR "18:00" = NY statt Wien), mal 00:00-Platzhalter
  // (KOR-CZE). Einzige verlässliche Quelle ist fx.kickoff (Polymarket gamma
  // startTime, echtes UTC). WM-Fenster Juni/Juli → Wien durchgehend CEST (UTC+2).
  function _koDate(fx) {
    const ko = fx && fx.kickoff;
    if (!ko) return null;
    const d = new Date(ko);
    return isNaN(d.getTime()) ? null : d;
  }

  // Hauptlabel in Wiener Zeit: "So, 14. Jun · 00:00 Uhr". Fallback alte Felder.
  function _fmtKickoffMain(fx) {
    const d = _koDate(fx);
    if (!d) return _fmtDate(fx.date, fx.time);
    const v  = new Date(d.getTime() + 2 * 3600 * 1000);   // UTC+2 (CEST)
    const h  = String(v.getUTCHours()).padStart(2, '0');
    const mi = String(v.getUTCMinutes()).padStart(2, '0');
    return `${_DAYS[v.getUTCDay()]}, ${v.getUTCDate()}. ${_MONTHS[v.getUTCMonth()]} · ${h}:${mi} Uhr`;
  }

  // Venue-Local aus kickoff: " · 18:00 NY". Fallback alte Felder.
  function _venueLocalFromKickoff(fx) {
    const d = _koDate(fx);
    if (!d) return _venueLocalTime(fx.venue, fx.time);
    const tz = _venueTz(fx.venue);
    if (!tz) return '';
    const loc = new Date(d.getTime() + tz.off * 3600 * 1000);
    const h   = String(loc.getUTCHours()).padStart(2, '0');
    const mi  = String(loc.getUTCMinutes()).padStart(2, '0');
    return ` · ${h}:${mi} ${tz.city}`;
  }

  // Sort-Key (ms) aus kickoff; Fallback date+time-Heuristik (< 06:00 = späte Session).
  function _kickoffSortMs(fx) {
    const d = _koDate(fx);
    if (d) return d.getTime();
    if (!fx || !fx.date) return Infinity;
    const m = /^(\d{1,2}):(\d{2})$/.exec(((fx.time || '')).trim());
    let mins = m ? (parseInt(m[1], 10) * 60 + parseInt(m[2], 10)) : 0;
    if (mins < 360) mins += 1440;
    const base = new Date(fx.date + 'T00:00:00Z').getTime();
    return (isNaN(base) ? 0 : base) + mins * 60000;
  }

  // ── Team row with form dots ───────────────────────────
  function _teamRow(team, standing, teamId, side, form, eloDelta) {
    const pos    = standing ? standing.findIndex(s => s.team === teamId) + 1 : 0;
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

  // ── Odds-Move-Balken: Pinnacle (immer) + Soft (wenn da) ──────────────────────
  // 17.06.2026 (Lucas): EIN Balken-Bauteil, zwei korrekt benannte Quellen.
  //   Pinnacle (rot) = steamOpen/steamCur (der Trigger — IMMER, deshalb jede Card).
  //   Soft (grün)    = softOpen/softNow (echte Softbook-Bewegung — wenn vorhanden).
  // Vorher war der grüne Streifen fälschlich „Soft", zeigte aber Pinnacle-Daten.
  function _moveBar(opts) {
    const { icon, label, o, c, mvText, meta, cls } = opts;
    if (o == null || c == null || o <= 1 || c <= 1) return '';
    const mvPP = ((1 / +c) - (1 / +o)) * 100;            // implizite Bewegung in pp
    const barWidth = Math.min(100, 30 + Math.abs(mvPP) * 7);
    return `<div class="cc-sharp-box ${cls}">
      <div class="cc-sm-head">${icon} <strong>${label}</strong> ${mvText}</div>
      <div class="cc-sm-bar-row">
        <span class="cc-sm-open">Opening: ${(+o).toFixed(2)}</span>
        <div class="cc-sm-bar"><div class="cc-sm-bar-fill" style="width:${barWidth}%"></div></div>
        <span class="cc-sm-now">Jetzt: ${(+c).toFixed(2)}</span>
      </div>
      ${meta ? `<div class="cc-sm-meta">${meta}</div>` : ''}
    </div>`;
  }

  // Frische-Status auf einen Blick (18.06.2026): BASIS (Move ruht) / GESTÄRKT (frisches
  // Geld weiter für uns) / DREHT (frisches Geld gegen uns). Soll Lucas sofort sehen lassen,
  // ob sich was geändert oder verstärkt hat.
  function _freshnessStatusBadge(pick) {
    if (!pick || pick.source !== 'steam' || !pick.freshnessState) return '';
    const map = {
      confirm: { label: 'GESTÄRKT', arrow: '↑', color: '#3fb950', bg: 'rgba(63,185,80,.12)', sub: 'frisches Geld läuft weiter für uns' },
      drift:   { label: 'BASIS',    arrow: '•', color: '#8b949e', bg: 'rgba(139,148,158,.12)', sub: 'der Move ist die Grundlage — ruht aktuell' },
      reverse: { label: 'DREHT',    arrow: '↓', color: '#f85149', bg: 'rgba(248,81,73,.12)', sub: 'frisches Geld dreht gegen uns' },
    };
    const m = map[pick.freshnessState];
    if (!m) return '';
    const rmv = pick.recentMovePP;
    const rmvStr = (rmv != null) ? `${rmv > 0 ? '+' : ''}${(+rmv).toFixed(1)}pp frisch` : '';
    const legStr = pick.legHours != null
      ? (pick.legHours >= 48 ? ` · seit ~${Math.round(pick.legHours / 24)} Tg` : ` · seit ~${Math.round(pick.legHours)}h`) : '';
    return `<div style="display:flex;align-items:center;gap:8px;margin:2px 0 6px;padding:5px 9px;border-radius:8px;background:${m.bg};border:1px solid ${m.color}55;">
      <span style="font-weight:700;color:${m.color};font-size:.8rem;letter-spacing:.04em;white-space:nowrap;">${m.arrow} ${m.label}</span>
      <span style="color:#8b949e;font-size:.74rem;line-height:1.2;">${m.sub}${rmvStr ? ` · <strong style="color:${m.color}">${rmvStr}</strong>` : ''}${legStr}</span>
    </div>`;
  }

  // 💷 Betfair-Geld-Block (29.07.2026, Lucas) — die GELD-VERTEILUNG aus dem betfair_money-Signal:
  // wieviel % des gematchten Geldes auf der Pick-Seite liegt vs. fairer Anteil (Betfair-Quoten
  // de-viggt), + €-Volumen + Track-Record-Hinweis (Liga×Markt solide/fadet). Liest heroPick.signals
  // (die Engine-Signalliste, mit metadata) — kein separates Pick-Feld nötig. Rendert für ALLE Picks
  // (Steam wie Modell), sobald das Signal gefeuert hat (Top-5 + MLS mit Namens-Match).
  const _BF_TOK_LABEL = { H:'Heim', D:'Remis', A:'Auswärts', OVER:'Über', UNDER:'Unter', YES:'BTTS Ja', NO:'BTTS Nein' };
  function _betfairMoneyBlock(pick) {
    const sig = (pick && Array.isArray(pick.signals))
      ? pick.signals.find(s => s && s.name === 'betfair_money') : null;
    const md = sig && sig.metadata;
    if (!md || md.money_share == null || md.fair_share == null) return '';
    const moneyPct = Math.round(md.money_share * 100);
    const fairPct  = Math.round(md.fair_share  * 100);
    const label    = _BF_TOK_LABEL[md.token] || md.token || '';
    const score    = +sig.score || 0;
    const edgePp   = (md.edge_pp != null) ? +md.edge_pp : (moneyPct - fairPct);
    const kEur     = (md.total_eur != null) ? Math.round(md.total_eur / 1000) : null;

    // Haltung: stützt (grün) / gefadet trotz Geld (rot) / dünn = Geld gegen Pick (gelb).
    let word, color;
    if (edgePp > 0 && score < 0) { word = 'warnt trotz Geld auf'; color = '#f85149'; }
    else if (score > 0)          { word = 'stützt';               color = '#3fb950'; }
    else                         { word = 'dünn auf';             color = '#e3b341'; }

    // Track-Record-Hinweis (Liga×Markt) aus der Signal-Metadata (nur ab n≥15 belastbar).
    let track = '';
    const roi = md.track_roi, trN = md.track_n;
    if (roi != null && trN != null && trN >= 15) {
      const roiPct = (roi >= 0 ? '+' : '') + Math.round(roi * 100) + '%';
      if (roi <= -0.10)     track = ` · <span style="color:#f85149">⚠️ Liga×Markt fadet (ROI ${roiPct}, n${trN})</span>`;
      else if (roi >= 0.05) track = ` · <span style="color:#3fb950">✅ Liga×Markt solide (ROI ${roiPct}, n${trN})</span>`;
    }

    const edgeStr = `${edgePp >= 0 ? '+' : ''}${Math.round(edgePp)}pp ggü. fair`;
    const meta    = `${kEur != null ? `€${kEur}k gematcht im Markt` : 'im Markt gematcht'}${track}`;
    const wMoney  = Math.max(0, Math.min(100, moneyPct));
    const wFair   = Math.max(0, Math.min(100, fairPct));
    return `<div class="cc-sharp-box cc-betfair">
      <div class="cc-sm-head">💷 <strong>Betfair-Geld ${word} ${label}</strong> <span style="color:${color};font-weight:600">${edgeStr}</span></div>
      <div class="cc-bf-bar-row">
        <span class="cc-bf-pct" style="color:${color}">${moneyPct}%</span>
        <div class="cc-bf-bar">
          <div class="cc-bf-fill" style="width:${wMoney}%;background:${color}"></div>
          <div class="cc-bf-fair" style="left:${wFair}%" title="fairer Anteil ${fairPct}%"></div>
        </div>
        <span class="cc-bf-fairlbl">fair ${fairPct}%</span>
      </div>
      <div class="cc-sm-meta">${meta}</div>
    </div>`;
  }

  function _steamMoveGraph(pick) {
    if (!pick || pick.source !== 'steam') return '';
    let html = _freshnessStatusBadge(pick);
    // 1) Pinnacle — der Trigger, immer da. Alters-/Lag-Kontext aus sharpMoveDetails wenn vorhanden.
    const mv = pick.steamMovePP;
    // 21.07.2026 (Lucas, MLS): steamMovePP ist DRIFT-BEREINIGT. Steht die Roh-Quote fast still
    // (steamMoveRawPP ≈ 0), war es ein „Halten gegen den Markt", kein Quotensturz — dann ehrlich
    // beschriften, sonst las sich „2.10→2.09 · +3.5pp" wie ein 3.5pp-Fall.
    // steamMoveRawPP fehlt auf ALTEN (vor dem Fix gebauten) Picks → dann die Roh-Bewegung aus den
    // angezeigten Quoten selbst rechnen, damit der ehrliche „Drift-Halten"-Text auch dort greift.
    let mvRaw = pick.steamMoveRawPP;
    if (mvRaw == null && pick.steamOpen > 1 && pick.steamCur > 1)
      mvRaw = (1 / (+pick.steamCur) - 1 / (+pick.steamOpen)) * 100;
    const _driftHold = (mvRaw != null && Math.abs(mv - mvRaw) >= 1.5);
    const sm = pick.sharpMoveDetails || {};
    let pinnMeta = _driftHold
      ? 'die Quote hielt, während der restliche Markt wegdriftete — relatives Sharp-Signal'
      : 'Hier ist scharfes Geld reingelaufen — das war der Auslöser';
    if (sm.move_age_days != null) {
      const d = sm.move_age_decay, ageD = Math.round(sm.move_age_days);
      // Altersbewusst: ein Move, der ≥4 Tage her ist, ist NICHT mehr „frisch" (auch wenn der
      // Decay-Faktor hoch ist) — er ist ausgereift. Sonst stand „vor 9 Tagen losgelaufen · noch frisch".
      pinnMeta = (ageD >= 4 ? `vor ${ageD} Tagen losgelaufen · ausgereift`
                : d >= 1 ? `vor ${ageD} Tagen losgelaufen · noch frisch`
                : d >= 0.5 ? `vor ${ageD} Tagen losgelaufen · schon etwas abgekühlt`
                : `vor ${ageD} Tagen losgelaufen · nicht mehr taufrisch`);
    }
    // Frische-Split (18.06.2026): der „Move seit Eröffnung" wird ehrlich in seinen
    // LETZTEN Bewegungs-Abschnitt aufgeteilt. confirm = frisches Geld läuft weiter für uns,
    // drift = Move ruht (nur alte Drift), reverse = frisches Geld dreht GEGEN uns.
    if (pick.recentMovePP != null && pick.freshnessState) {
      const rmv = +pick.recentMovePP;
      const legTxt = pick.legHours != null
        ? (pick.legHours >= 48 ? `~${Math.round(pick.legHours / 24)} Tage`
           : `~${Math.round(pick.legHours)}h`) : '';
      const rmvStr = `${rmv > 0 ? '+' : ''}${rmv.toFixed(1)}pp`;
      if (pick.freshnessState === 'confirm') {
        pinnMeta += ` · <span style="color:#3fb950;">✅ läuft frisch weiter: ${rmvStr} im letzten Abschnitt (${legTxt})</span>`;
      } else if (pick.freshnessState === 'reverse') {
        const revWord = pick.reverserFresh === false ? 'die Linie steht inzwischen gegen den Move' : 'frisches Geld dreht gegen uns';
        pinnMeta += ` · <span style="color:#f85149;font-weight:600;">⚠️ Achtung, dreht: ${rmvStr} — ${revWord}</span>`;
      } else {
        pinnMeta += ` · <span style="color:#8b949e;">⏸ der Move macht gerade Pause (zuletzt nur ${rmvStr})</span>`;
      }
    }
    html += _moveBar({
      icon: '🔥', label: 'Pinnacle bewegt', cls: 'cc-pinn',
      o: pick.steamOpen, c: pick.steamCur,
      // Bei Drift-Halten: die Roh-Quote (passt zum Balken) + der drift-relative Wert getrennt zeigen.
      mvText: _driftHold
        ? `${mvRaw > 0 ? '+' : ''}${(+mvRaw).toFixed(1)}pp Quote · +${mv}pp ggü. Markt`
        : `${mv > 0 ? '+' : ''}${mv}pp seit Eröffnung`,
      meta: pinnMeta,
    });
    // Prominente Reverser-Warnung (frisches Geld läuft gegen unseren Pick)
    if (pick.reverser) {
      const fresh = pick.reverserFresh !== false;
      const headline = fresh ? 'Frisches Geld dreht gegen uns' : 'Linie steht gegen den Move';
      const sub = fresh
        ? 'der Move seit Eröffnung ist überholt'
        : `der Gegen-Move ist älter${pick.reverserLastMoveH != null ? ` (~${Math.round(pick.reverserLastMoveH / 24)} Tage)` : ''}, aber der Pick sitzt auf der falschen Seite`;
      html += `<div class="cc-reverser-warn" style="margin-top:6px;padding:8px 10px;border-radius:8px;
        background:rgba(248,81,73,.10);border:1px solid rgba(248,81,73,.35);color:#f85149;font-size:.82rem;">
        ⚠️ <strong>${headline}</strong> — ${sub}. Pick zurückgestuft.${pick.reverserPP != null ? ` (letzter Abschnitt ${(+pick.reverserPP).toFixed(1)}pp)` : ''}
      </div>`;
    }
    // 2) Soft-Quote — die echte Softbook-Bewegung (nur wenn Soft-Daten da)
    if (pick.softOpen != null && pick.softNow != null) {
      const ff = pick.softFollowPP;
      // FIX 19.06.2026 (Lucas): „hinken nach" war der Catch-all-Fallback — stand auch da, wenn
      // die Soft-Quote 0pp bewegt hat und gar nicht hinterherhinkt. Echtes Lag = Soft-Quote
      // noch LÄNGER als die aktuelle Pinnacle-Quote (steamCur), d.h. Soft hat noch nicht
      // aufgeschlossen → Resthebel. Ist Soft schon ≤ Pinnacle, gibt's keinen Lag mehr.
      // FIX 20.06.2026 (Lucas): „da ist noch Luft" war vage — jetzt zeigen wir GEGENÜBER WEM
      // (Pinnacle) und WIE VIEL. Lag in pp = 1/Pinnacle − 1/Soft (positiv = Soft länger als
      // Pinnacle = noch nicht aufgeschlossen). Unter ~1pp: praktisch gleichauf, kein „hinterher".
      const _pinn = pick.steamCur;
      const _lagPp = (_pinn && pick.softNow) ? (1 / _pinn - 1 / pick.softNow) * 100 : null;
      const softMeta = pick.softConfirmed
        ? '✅ Soft-Books bestätigen den Move'
        : (ff != null && ff > 0 ? `Soft-Books ziehen nach (+${ff}pp)`
           : (_lagPp != null && _lagPp >= 1.0)
              ? `Soft ${(+pick.softNow).toFixed(2)} hängt noch ~${_lagPp.toFixed(1)}pp hinter Pinnacle ${(+_pinn).toFixed(2)}`
              : 'Soft-Quote ist praktisch auf Pinnacle-Höhe');
      html += _moveBar({
        icon: '💶', label: 'Soft-Quote bewegt', cls: 'cc-soft',
        o: pick.softOpen, c: pick.softNow,
        mvText: (ff != null ? `${ff > 0 ? '+' : ''}${ff}pp seit Eröffnung` : ''),
        meta: softMeta,
      });
    }
    return html;
  }

  // ── Pick row with edgePP ──────────────────────────────
  function _buildPickRow(pick, isPlayer) {
    const verdict  = pick.verdict || 'ABWÄGEN';
    // FIX 14.06.2026: Sterne aus dem Verdict, nicht aus conf (Datenqualität) — Konsistenz
    // mit dem Label (BET ★★★ ≥ ABWÄGEN ★★☆ > Rest), wie im Tracking + Hero.
    const stars   = verdict === 'BET' ? '★★★' : verdict === 'ABWÄGEN' ? '★★☆' : '★☆☆';
    const starsClr = verdict === 'BET' ? '#3fb950' : verdict === 'ABWÄGEN' ? '#e3b341' : '#8b949e';
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

    const counterCls = pick.reverserCounter ? ' wm-pick-row--counter' : '';
    const counterTag = pick.reverserCounter
      ? `<span class="wm-counter-tag" title="Frisches Geld dreht auf diese Seite — datengetriebene Gegen-Linie zum zurückgestuften Pick. Reift nur via Conviction zu BET." style="display:inline-block;font-size:.7rem;color:#58a6ff;border:1px solid rgba(88,166,255,.4);border-radius:6px;padding:1px 6px;margin-bottom:3px;">↩️ Reverser-Konter${pick.counterOf ? ` zu ${pick.counterOf}` : ''}</span>` : '';
    return `
    <div class="wm-pick-row${counterCls}"${pick.reverserCounter ? ' style="border-left:3px solid rgba(88,166,255,.5);padding-left:8px;"' : ''}>
      ${counterTag ? `<div style="width:100%;">${counterTag}</div>` : ''}
      <span class="wm-verdict" style="color:${vClr};background:${vBg};border-color:${vBorder};">${verdict}</span>
      <span class="wm-pick-icon">${icon}</span>
      <div class="wm-pick-main">
        <div class="wm-pick-market">${market}${dqBadge}</div>
        ${modelHtml}
        ${pick.info ? `<div class="wm-pick-info">${pick.info}</div>` : ''}
        ${_steamMoveGraph(pick)}
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

    // 04.09.2026: _standingScenario rechnet in Vierergruppen („Platz > 3 = ausgeschieden").
    // Auf einer Liga-Tabelle mit 18–20 Zeilen ergibt das nur Unsinn — dann lieber der
    // Elo-Satz darunter, der ohne Tabellenkontext auskommt.
    if (_istGruppentabelle(standing)) {
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
    const homeRow = standing.find(s => s.team === home.id);
    const awayRow = standing.find(s => s.team === away.id);
    if (!homeRow || !awayRow) return null;

    const homePts = homeRow.pts || 0;
    const awayPts = awayRow.pts || 0;
    const homePos = standing.findIndex(s => s.team === home.id) + 1;
    const awayPos = standing.findIndex(s => s.team === away.id) + 1;

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

  // Test-Hook (27.06.2026): Card-Renderer für den jsdom-Render-Harness zugänglich machen.
  // Reines Test-Interface — die Produktion nutzt die internen Aufrufe; ändert kein Verhalten.
  if (typeof window !== 'undefined') {
    window.__wmCardTest = {
      engineSignalGridHtml: _engineSignalGridHtml,
      betfairMoneyBlock: _betfairMoneyBlock,      // 29.07.2026: 💷 Betfair-Geld-Verteilungsblock
      buildKoCard: _buildKoCard,
      buildCard: _buildCard,
      sharpConsensus: _sharpConsensus,
      streakRowHtml: _streakRowHtml,
      matchStreaksHtml: _matchStreaksHtml,
      setStreaksCache: (ds, d) => { _streaksCache[ds] = d; },
      fxIsPast: _fxIsPast,
      setWmData: (d) => { _wmData = d; },
      mpPrefix: _mpPrefix,                       // 19.07.2026: MLS-Event-Page-Slug-Prefix
      setMode: (m) => { _mode = m; },
      upcomingMdsForScope: _upcomingMdsForScope, // 20.07.2026: Spieltag-Chip-Scope (MLS-Bug)
    };
  }

})();
