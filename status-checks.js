// ═══════════════════════════════════════════════════════════════════════
//  status-checks.js — WM Status-Seite: Live-Health-Engine
//
//  Single Source of Truth für "läuft alles / was ist gefailt".
//  Rechnet WM-native Checks live im Browser aus den committeten JSONs und
//  kombiniert sie mit der Server-Readiness (wm_status.json, vom Cron).
//
//  Entry: runStatusPage(force)  — aufgerufen von initStatus() (ui.js)
//  Rendert: #st_verdict #st_problems #st_server #st_feeds #st_signals
// ═══════════════════════════════════════════════════════════════════════

const _SEV_RANK = { error: 3, warn: 2, info: 1, ok: 0 };
const _SEV_META = {
  error: { icon: '🔴', col: '#f85149', bg: 'rgba(248,81,73,.08)',  bd: 'rgba(248,81,73,.30)',  lbl: 'FEHLER' },
  warn:  { icon: '🟡', col: '#e3b341', bg: 'rgba(227,179,65,.07)', bd: 'rgba(227,179,65,.25)',  lbl: 'WARNUNG' },
  info:  { icon: '🔵', col: '#58a6ff', bg: 'rgba(88,166,255,.06)', bd: 'rgba(88,166,255,.20)',  lbl: 'HINWEIS' },
  ok:    { icon: '🟢', col: '#3fb950', bg: 'rgba(63,185,80,.07)',  bd: 'rgba(63,185,80,.25)',   lbl: 'OK' },
};

// Feed-Frische: Erwartete Aktualisierungs-Kadenz pro Datei.
const _ST_FEEDS = [
  { file: 'wm_poly_prices.json',        icon: '💹', label: 'Polymarket Preise + Edges', ts: 'generatedAt',     warnH: 8,  errH: 24, crit: true },
  { file: 'wm2026-odds-history.json',   icon: '📈', label: 'Pinnacle Odds-Snapshots',   ts: '_newestSnap',     warnH: 8,  errH: 24, crit: true },
  { file: 'wm_poly_balance.json',       icon: '💰', label: 'Polymarket Balance',        ts: 'updatedAt',       warnH: 8,  errH: 30, crit: false },
  { file: 'pick_validation_report.json',icon: '🔍', label: 'Validator-Report',          ts: 'lastRun',         warnH: 8,  errH: 24, crit: true },
  { file: 'wm_status.json',             icon: '🩺', label: 'Readiness-Report',          ts: 'generatedAt',     warnH: 8,  errH: 24, crit: false },
  { file: 'steam_lag_log.json',         icon: '🔥', label: 'Steam-Lag Monitor',         ts: 'updatedAt',       warnH: 8,  errH: 24, crit: false },
  { file: 'wm_weather.json',            icon: '🌡️', label: 'Wetter-Feed',               ts: 'generatedAt',     warnH: 30, errH: 60, crit: false },
  { file: 'wm_nt_xg.json',              icon: '📊', label: 'NT-xG (Coverage)',          ts: null,              warnH: 0,  errH: 0,  crit: false },
  { file: 'wm_apif_predictions.json',   icon: '🤝', label: 'APIF-Predictions',        ts: null,              warnH: 0,  errH: 0,  crit: false },
  { file: 'wm_lineups.json',            icon: '📋', label: 'Aufstellungen (T-1h)',      ts: 'generatedAt',     warnH: 0,  errH: 0,  crit: false },
];

function _stParseTs(v) {
  if (!v) return null;
  if (typeof v === 'string' && /^\d{2}\.\d{2}\.\d{4}/.test(v)) {
    const m = v.match(/(\d{2})\.(\d{2})\.(\d{4})[ T](\d{2}):(\d{2})/);
    if (m) return new Date(Date.UTC(+m[3], +m[2] - 1, +m[1], +m[4], +m[5]));
  }
  const d = new Date(v);
  return isNaN(d.getTime()) ? null : d;
}
function _stAgeH(d) { return d ? (Date.now() - d.getTime()) / 3600000 : null; }
// 20.07.2026 WM-Winterisierung — Turnier beendet? (spiegelt cocobet_dataset.tournament_is_over).
// Alle Fixtures (Gruppen + koFixtures) aufgelöst UND letzter Anpfiff in der Vergangenheit → dann sind
// die Odds/Poly-Frische-Checks ERWARTET veraltet (TheOddsAPI droppt beendete Turniere), kein Fehler.
// Universell: laufende Liga/MLS hat immer kommende Spiele → false.
function _stTournamentOver(data) {
  if (!data) return false;
  const FINAL = new Set(['FT', 'AET', 'PEN', 'FINISHED']);
  const fx = [];
  for (const g of Object.values(data.groups || {})) for (const f of (g.fixtures || [])) fx.push(f);
  const ko = data.koFixtures;
  if (Array.isArray(ko)) fx.push(...ko);
  else if (ko && typeof ko === 'object') for (const v of Object.values(ko)) Array.isArray(v) ? fx.push(...v) : fx.push(v);
  if (!fx.length) return false;
  const resolved = f => FINAL.has(String((f.result || {}).status || '').toUpperCase());
  if (!fx.every(resolved)) return false;
  let latest = '';
  for (const f of fx) { const k = f.kickoff || f.date || ''; if (k > latest) latest = k; }
  if (!latest) return true;
  const t = _stParseTs(latest);
  return t ? t.getTime() < Date.now() : true;
}
function _stAgo(d) {
  const h = _stAgeH(d);
  if (h === null) return '—';
  if (h < 1) return `vor ${Math.max(1, Math.round(h * 60))} Min`;
  if (h < 48) return `vor ${h.toFixed(1)} Std`;
  return `vor ${Math.floor(h / 24)} Tagen`;
}
async function _stGet(f) {
  try { const r = await fetch(f + '?t=' + Date.now()); return r.ok ? await r.json() : null; }
  catch (e) { return null; }
}

let _stRunning = false;

// (26.06.2026, Lucas: Status Liga/Intl-Toggle) — Modul-State: welcher Datensatz
// wird im Status-Tab gezeigt. 'intl' = bestehendes WM/CL-Verhalten (Default),
// 'liga' = schlanke Liga-Ops-Health aus liga_status.json + liga-data.json.
let _stDataset = 'intl';

// 13.07.2026 (MLS-Audit) — Status-Tab war zweigeteilt (International/Liga). mls_status.json wurde
// erzeugt und committet, war im UI aber nicht erreichbar: der MLS-Gesundheitszustand (60 Guards,
// Lern-Loop) war unsichtbar. Neue Liga = EINE Zeile hier.
const ST_DATASETS = [
  { id: 'intl', label: '🌍 International' },
  { id: 'liga', label: '⚽ Top-5' },
  { id: 'mls',  label: '🇺🇸 MLS' },
];
// Dateien je Datensatz. 'intl' läuft über den eigenen WM-Pfad (Poly/Kill-Switch/Auto-Bets).
function ST_FILES(ds) {
  const p = ds === 'mls' ? 'mls' : 'liga';
  return {
    data:    p === 'mls' ? 'mls-data.json' : 'liga-data.json',
    status:  `${p}_status.json`,
    ledger:  `${p}_signal_ledger.json`,
    weights: `${p}_signal_weights.json`,
  };
}
// „Liga-artig" = alles außer dem WM-Pfad.
function _stIsLigaLike(ds) { return ds === 'liga' || ds === 'mls'; }

// (26.06.2026, Lucas: Status Liga/Intl-Toggle) — Toggle-Buttons oben im
// statusPanel per JS injizieren (idempotent), damit alles in status-checks.js
// bleibt und season-finish-v2.html unangetastet ist.
function _stRenderToggle() {
  const panel = document.getElementById('statusPanel'); if (!panel) return;
  let bar = document.getElementById('st_datasetToggle');
  if (!bar) {
    bar = document.createElement('div');
    bar.id = 'st_datasetToggle';
    bar.style.cssText = 'display:flex;gap:8px;margin-bottom:16px;';
    panel.insertBefore(bar, panel.firstChild);  // ganz oben
  }
  const btn = (ds, label) => {
    const on = _stDataset === ds;
    const col = on ? 'var(--text)' : 'var(--muted)';
    const bg = on ? 'var(--card2)' : 'transparent';
    const bd = on ? 'var(--text)' : 'var(--border)';
    return `<button data-ds="${ds}" style="background:${bg};border:1px solid ${bd};color:${col};border-radius:8px;padding:8px 16px;font-size:13px;font-weight:${on ? 700 : 600};cursor:pointer;font-family:inherit;${on ? 'box-shadow:0 0 0 1px var(--text) inset;' : ''}">${label}</button>`;
  };
  // 13.07.2026 (MLS-Audit): mls_status.json wird erzeugt UND committet, war im UI aber nicht
  // erreichbar — der MLS-Gesundheitszustand (Guards, Lern-Loop) war schlicht unsichtbar.
  // Neue Liga = ein Eintrag in ST_DATASETS.
  bar.innerHTML = ST_DATASETS.map(d => btn(d.id, d.label)).join('');
  bar.querySelectorAll('button').forEach(b => {
    b.onclick = () => {
      const ds = b.getAttribute('data-ds');
      if (ds === _stDataset) return;
      _stDataset = ds;
      runStatusPage(true);
    };
  });
}

// ── LERN-STATUS (04.07.2026, Lucas: „merk nirgends ob der Loop klappt") ──────
// Drei Stufen sichtbar: (1) xG nach dem Spiel geholt? (2) Picks als verdient/Glück/Pech
// bewertet? (3) Signal-Gewichte nachjustiert? — live aus Ledger + Gewichten + Daten.
const _PV_META = {
  JUSTIFIED:     { lbl: 'verdient',            col: '#3fb950' },
  LUCKY:         { lbl: 'Glück',               col: '#58a6ff' },
  UNLUCKY:       { lbl: 'Pech',                col: '#e3b341' },
  DESERVED_LOSS: { lbl: 'verdiente Niederlage', col: '#f85149' },
};

// Signal-Klartext-Namen (identisch zur Sharp-Radar-Nomenklatur) für die Lern-Tabelle.
const _SIG_LABEL = {
  form_trend: 'Form-Trend', xg_strength: 'xG-Stärke', travel_burden: 'Reise-Last',
  smart_money: 'Smart Money', chance_creation: 'Chancen-Qualität', incentive_signal: 'Anreiz',
  public_static_bias: 'Public-Bias', lineup_signal: 'Aufstellung (T-1h)',
  lead_lag_bias: 'Sharp-Move (Pinn vs Soft)', weather_signal: 'Wetter/Hitze',
  pressure_index: 'Druck-Index', league_pressure: 'Liga-Druck', form_rating: 'Form-Rating', h2h_pattern: 'H2H-Muster',
  apif_predictions: 'APIF-Prognose', freshness_leg: 'Frische', fixture_congestion: 'Terminstress',
  altitude_signal: 'Höhe', injury: 'Verletzungen', streak_momentum: 'Serien-Momentum',
  polymarket_sharp: 'Polymarket-Sharp', steam_lag: 'Steam-Lag',
};
// Nur im Trade-Pfad — feuern per Design NIE auf Cards → lernen hier nicht (kein Fehler).
const _SIG_TRADE_ONLY = new Set(['polymarket_sharp', 'steam_lag']);
const _SIG_MIN_LEARN = 10;   // ab so vielen Beobachtungen gilt ein Signal als „gelernt"

function _stRenderLearning(data, ledger, weights) {
  const el = document.getElementById('st_learning');
  if (!el) return;

  // ── Stufe 1: xG-Abdeckung fertiger Spiele (Gruppe + KO) ──
  let finished = 0, withXg = 0;
  const _scan = fx => {
    const r = (fx && fx.result) || {};
    const fin = ['FT', 'AET', 'PEN'].includes(String(r.status || '').toUpperCase());
    if (!fin) return;
    finished++;
    if (r.stats && typeof r.stats.homeXg === 'number') withXg++;
  };
  if (data && data.groups) for (const g of Object.values(data.groups)) for (const fx of (g.fixtures || [])) _scan(fx);
  if (data && Array.isArray(data.koFixtures)) for (const fx of data.koFixtures) _scan(fx);

  // ── Stufe 2: Prozess-Verdict-Abdeckung im Ledger ──
  const recs = (ledger && Array.isArray(ledger.records)) ? ledger.records : [];
  const pvCounts = {};
  let judged = 0;
  for (const r of recs) {
    const pv = r.processVerdict;
    if (pv && _PV_META[pv]) { pvCounts[pv] = (pvCounts[pv] || 0) + 1; judged++; }
  }

  // ── Stufe 3: Gewichte — jüngstes last_updated + stärkste Bewegungen ──
  let newestW = null, movers = [];
  if (weights && typeof weights === 'object') {
    for (const [name, w] of Object.entries(weights)) {
      if (name === '_meta' || !w || typeof w.weight !== 'number') continue;
      const t = _stParseTs(w.last_updated);
      if (t && (!newestW || t > newestW)) newestW = t;
      movers.push({ name, weight: w.weight, n: w.n_observations || 0, drift: Math.abs(w.weight - 1) });
    }
    movers.sort((a, b) => b.drift - a.drift);
  }

  const tsEl = document.getElementById('st_learnTs');
  if (tsEl) tsEl.textContent = newestW ? 'Gewichte: ' + _stAgo(newestW) : '';

  // Stufen-Pills (grün wenn Stufe greift)
  const pill = (ok, icon, label, sub) => {
    const col = ok ? '#3fb950' : '#e3b341';
    return `<div style="flex:1;min-width:150px;background:${col}14;border:1px solid ${col}44;border-radius:10px;padding:11px 13px;">
      <div style="font-size:11px;color:var(--muted);letter-spacing:.5px;">${icon} ${label}</div>
      <div style="font-size:15px;font-weight:800;color:${col};margin-top:3px;">${sub}</div></div>`;
  };
  const xgPct = finished ? Math.round(withXg / finished * 100) : 0;
  const jPct  = recs.length ? Math.round(judged / recs.length * 100) : 0;
  const pills = `<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px;">
    ${pill(finished && withXg === finished, '📊', 'xG nach Spiel geholt', finished ? `${withXg}/${finished} Spiele` : '—')}
    ${pill(judged > 0, '⚖️', 'Picks bewertet', recs.length ? `${judged}/${recs.length} (${jPct}%)` : '—')}
    ${pill(!!newestW, '🎚️', 'Gewichte justiert', newestW ? _stAgo(newestW) : 'nie')}</div>`;

  // Verdict-Verteilung als Balken
  let bar = '';
  if (judged > 0) {
    const seg = Object.entries(_PV_META).map(([k, m]) => {
      const n = pvCounts[k] || 0; if (!n) return '';
      const p = Math.round(n / judged * 100);
      return `<div style="flex:${n};background:${m.col};min-width:2px;" title="${m.lbl}: ${n} (${p}%)"></div>`;
    }).join('');
    const legend = Object.entries(_PV_META).map(([k, m]) => {
      const n = pvCounts[k] || 0; if (!n) return '';
      return `<span style="white-space:nowrap;"><span style="display:inline-block;width:9px;height:9px;border-radius:2px;background:${m.col};margin-right:4px;"></span>${m.lbl} ${n}</span>`;
    }).filter(Boolean).join('<span style="color:var(--muted);margin:0 4px;">·</span>');
    bar = `<div style="font-size:11px;color:var(--muted);margin-bottom:5px;">Rückblick-Urteil pro Pick (aus echtem Match-xG) — verlorene-aber-verdiente Picks werden milder gelernt:</div>
      <div style="display:flex;height:14px;border-radius:7px;overflow:hidden;margin-bottom:7px;">${seg}</div>
      <div style="display:flex;flex-wrap:wrap;gap:6px 4px;font-size:11px;">${legend}</div>`;
  }

  // ── Feuer-Häufigkeit je Signal auf der AKTUELLEN Slate (für den Netto-Einfluss) ──
  const fireCount = {};
  if (data && data.picks) {
    for (const plist of Object.values(data.picks)) {
      if (!Array.isArray(plist)) continue;
      for (const p of plist) {
        for (const sg of (p.signals || [])) {
          if (sg && sg.name && sg.score !== 0 && sg.score != null) {
            fireCount[sg.name] = (fireCount[sg.name] || 0) + 1;
          }
        }
      }
    }
  }

  // ── Signal-Lerntabelle: gelernt + Netto-Einfluss (Feuer × Vertrauens-Abweichung) ──
  const sigRows = [];
  if (weights && typeof weights === 'object') {
    for (const [name, w] of Object.entries(weights)) {
      if (name === '_meta' || !w || typeof w.weight !== 'number') continue;
      const wins = +w.wins_when_triggered || 0, loss = +w.losses_when_triggered || 0;
      const dec = wins + loss;
      const fire = fireCount[name] || 0;
      sigRows.push({
        name, label: _SIG_LABEL[name] || name, weight: w.weight,
        n: w.n_observations || 0, hit: dec > 0 ? Math.round(wins / dec * 100) : null,
        fire, infl: Math.round((w.weight - 1) * fire * 10) / 10,   // Vol × Δ = Netto-Einfluss
        tradeOnly: _SIG_TRADE_ONLY.has(name),
      });
    }
  }
  // Träger oben, Drags unten (nach Netto-Einfluss); dünne nach n.
  const learned  = sigRows.filter(s => !s.tradeOnly && s.n >= _SIG_MIN_LEARN).sort((a, b) => b.infl - a.infl);
  const thin     = sigRows.filter(s => !s.tradeOnly && s.n < _SIG_MIN_LEARN).sort((a, b) => b.n - a.n);
  const tradeSig = sigRows.filter(s => s.tradeOnly);
  const maxInfl  = Math.max(1, ...sigRows.map(s => Math.abs(s.infl)));

  const sigRow = s => {
    const up = s.weight > 1.02, dn = s.weight < 0.98;
    const col = up ? '#3fb950' : (dn ? '#f85149' : 'var(--muted)');
    const arr = up ? '↑' : (dn ? '↓' : '–');
    const hit = s.hit === null ? '<span style="color:var(--muted);">—</span>'
      : `<span style="color:${s.hit >= 55 ? '#3fb950' : (s.hit <= 45 ? '#e3b341' : 'var(--fg)')};">${s.hit}%</span>`;
    // Netto-Einfluss als signierte, farbige Zahl + diverging Balken (Mitte = 0).
    const icol = s.infl > 0.5 ? '#3fb950' : (s.infl < -0.5 ? '#f85149' : 'var(--muted)');
    const iw = Math.abs(s.infl) / maxInfl * 50;
    const ibar = s.infl >= 0
      ? `<span style="position:absolute;left:50%;width:${iw}%;height:100%;background:#3fb950;"></span>`
      : `<span style="position:absolute;right:50%;width:${iw}%;height:100%;background:#f85149;"></span>`;
    const isign = s.infl > 0 ? '+' : '';
    return `<div style="display:flex;align-items:center;gap:9px;font-size:12px;padding:3px 0;">
      <span style="flex:1;min-width:104px;">${s.label}</span>
      <span style="width:40px;text-align:right;color:var(--muted);font-size:10.5px;font-variant-numeric:tabular-nums;">${s.fire}×</span>
      <span style="width:30px;text-align:right;font-variant-numeric:tabular-nums;">${hit}</span>
      <span style="width:42px;text-align:right;font-weight:800;color:${col};font-variant-numeric:tabular-nums;">${arr}${s.weight.toFixed(2)}</span>
      <span style="position:relative;width:54px;height:7px;background:rgba(255,255,255,.06);border-radius:4px;overflow:hidden;flex-shrink:0;"><span style="position:absolute;left:50%;top:0;width:1px;height:100%;background:rgba(255,255,255,.25);"></span>${ibar}</span>
      <span style="width:42px;text-align:right;font-weight:800;color:${icol};font-variant-numeric:tabular-nums;">${isign}${s.infl}</span></div>`;
  };

  const subHead = t => `<div style="font-size:10.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.8px;font-weight:700;margin:12px 0 4px;">${t}</div>`;
  let tbl = subHead(`Gelernt · genug Masse (n ≥ ${_SIG_MIN_LEARN}) · nach Netto-Einfluss`) + learned.map(sigRow).join('');
  if (thin.length)     tbl += subHead('Lernt noch · dünne Stichprobe') + thin.map(sigRow).join('');
  if (tradeSig.length) tbl += subHead('Nur Trading · feuert nicht auf Cards') +
    tradeSig.map(s => `<div style="display:flex;align-items:center;gap:9px;font-size:12px;padding:3px 0;opacity:.55;">
      <span style="flex:1;">${s.label}</span><span style="color:var(--muted);font-size:10.5px;">lernt hier nicht (Trade-Pfad)</span></div>`).join('');

  // Health-Verdict-Kopf
  const loopOk = judged > 0 && !!newestW;
  const vcol = loopOk ? '#3fb950' : '#e3b341';
  const verdict = `<div style="display:flex;align-items:center;gap:8px;margin-bottom:14px;padding:9px 12px;background:${vcol}12;border:1px solid ${vcol}40;border-radius:10px;">
    <span style="font-size:16px;">${loopOk ? '✓' : '⏳'}</span>
    <span style="font-size:12.5px;font-weight:700;color:${vcol};">${loopOk
      ? `Lern-Loop aktiv · ${judged} Picks bewertet · ${learned.length} Signale mit Masse`
      : 'Lern-Loop wartet auf erste Ergebnisse'}</span></div>`;

  // ── Ledger-Kopfzeile (22.07.2026, Lucas: „sehe ich auf einen Blick, ob/wann zuletzt gelernt
  // wurde"). N Einträge · letzter Eintrag vor X (jüngstes resolvedAt) · Loop grün/wartet.
  // Steht IMMER oben — auch bevor der erste Pick auflöst (dann 0 Einträge · wartet). ──
  let _lastRecTs = null;
  for (const r of recs) {
    const t = _stParseTs(r.resolvedAt);
    if (t && (!_lastRecTs || t > _lastRecTs)) _lastRecTs = t;
  }
  const _lcol = loopOk ? '#3fb950' : '#e3b341';
  const ledgerHead = `<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:12px;padding:9px 12px;background:${_lcol}12;border:1px solid ${_lcol}40;border-radius:10px;font-size:12.5px;">
    <span style="font-weight:800;color:${_lcol};">🧾 Ledger: ${recs.length} ${recs.length === 1 ? 'Eintrag' : 'Einträge'}</span>
    <span style="color:var(--muted);">·</span>
    <span style="color:var(--fg);">letzter Eintrag ${_lastRecTs ? _stAgo(_lastRecTs) : '—'}</span>
    <span style="color:var(--muted);">·</span>
    <span style="font-weight:700;color:${_lcol};">${loopOk ? '✓ Lern-Loop grün' : '⏳ Lern-Loop wartet'}</span></div>`;

  if (!recs.length && !finished) {
    el.innerHTML = ledgerHead +
      '<div style="color:var(--muted);text-align:center;padding:14px;">Noch keine aufgelösten Picks — Lern-Status füllt sich nach den ersten Ergebnissen.</div>';
    return;
  }
  el.innerHTML = ledgerHead + verdict + pills + bar +
    `<div style="margin-top:16px;">
      <div style="font-size:11px;color:var(--muted);margin-bottom:2px;"><b style="color:var(--fg);">Feuer</b>=wie oft auf der aktuellen Slate · <b style="color:var(--fg);">Hit</b>=Trefferquote · <b style="color:var(--fg);">Gewicht</b> 1.00=neutral · <b style="color:var(--fg);">Einfluss</b>=Feuer×(Gewicht−1): <span style="color:#3fb950;">grün trägt</span>, <span style="color:#f85149;">rot zieht runter</span></div>
      ${tbl}
    </div>`;
}

async function runStatusPage(force) {
  if (_stRunning) return;
  _stRunning = true;
  try {
    _stRenderToggle();   // (26.06.2026, Lucas: Status Liga/Intl-Toggle)

    // (26.06.2026, Lucas: Status Liga/Intl-Toggle) — früher Liga-Abzweig.
    // WM/Intl-Flow darunter bleibt komplett unverändert.
    if (_stIsLigaLike(_stDataset)) { await _runLigaStatus(); return; }

    const [data, poly, oddsHist, bal, ks, autobets, status, valRep, ledger, weights] = await Promise.all([
      _stGet('wm2026-data.json'), _stGet('wm_poly_prices.json'), _stGet('wm2026-odds-history.json'),
      _stGet('wm_poly_balance.json'), _stGet('wm_kill_switch.json'), _stGet('wm_auto_bets_placed.json'),
      _stGet('wm_status.json'), _stGet('pick_validation_report.json'),
      _stGet('wm_signal_ledger.json'), _stGet('signal_weights.json'),
    ]);

    const problems = [];
    const add = (sev, title, detail) => problems.push({ sev, title, detail });

    // ── WM-Winterisierung (20.07.2026): Turnier beendet → die Frische-Checks (Odds/Poly/Balance/
    // Stale-Edges) sind ERWARTET veraltet, TheOddsAPI droppt die WM. Ein grüner Hinweis statt roter
    // Fehlalarme; die betroffenen Live-Checks werden übersprungen. Pick-/Konsistenz-Checks bleiben. ──
    const wmOver = _stTournamentOver(data);
    if (wmOver) add('info', '🏁 WM 2026 beendet — winterisiert',
      'Alle Spiele aufgelöst (Finale 19.07.). Odds/Poly/Balance werden erwartungsgemäß nicht mehr aktualisiert und die WM-Workflows sind pausiert — die Frische-Warnungen unten entfallen daher. Kein Ausfall.');

    // ── Live-Check 1: Stale Edges (edge_X ≠ fair_X − poly_X) ──────────────
    if (!wmOver && poly && Array.isArray(poly.allFixtures)) {
      const stale = [];
      for (const fx of poly.allFixtures) {
        for (const m of ['hw', 'dr', 'aw', 'o25', 'u25']) {
          const fair = fx['fair_' + m], pol = fx['poly_' + m], ed = fx['edge_' + m];
          if ([fair, pol, ed].some(v => typeof v !== 'number')) continue;
          const live = Math.round((fair - pol) * 1000) / 10;
          if (Math.abs(live - ed) > 0.5) stale.push(`${fx.homeId}-${fx.awayId} ${m}: ${ed >= 0 ? '+' : ''}${ed} ≠ live ${live >= 0 ? '+' : ''}${live}pp`);
        }
      }
      if (stale.length) add('error', `${stale.length} Stale Edge(s) in wm_poly_prices.json`,
        `Gespeichertes edge_X weicht von fair−poly ab → Auto-Trader rechnet evtl. falsch (rechnet live nach, aber Datei sollte stimmen). ${stale.slice(0, 4).join(' · ')}${stale.length > 4 ? ' …' : ''}`);
    }

    // ── Live-Check 2: Home/Away-Konflikt (beide Seiten empfohlen) ────────
    if (data && data.picks) {
      const conflicts = [];
      for (const [key, plist] of Object.entries(data.picks)) {
        if (!Array.isArray(plist)) continue;
        const act = p => (p.verdict === 'BET' || p.verdict === 'ABWÄGEN') && !p.trackingExcluded && !p.synthetic;
        const hasHome = plist.some(p => p.market === 'Heimsieg' && act(p));
        const hasAway = plist.some(p => p.market === 'Auswärtssieg' && act(p));
        if (hasHome && hasAway) conflicts.push(key.replace(/^[A-L]-\d+-/, ''));
      }
      if (conflicts.length) add('error', `${conflicts.length} Home+Away-Widerspruch`,
        `Beide Siegrichtungen gleichzeitig empfohlen: ${conflicts.join(', ')} — Cross-Market-Filter prüfen.`);
    }

    // ── Live-Check 3: Spielplan-Konsistenz (Seed vs Polymarket-Datum) ────
    if (data && data.groups && poly && poly.prices) {
      const seed = {};
      for (const g of Object.values(data.groups)) for (const fx of (g.fixtures || [])) seed[`${fx.home}-${fx.away}`] = (fx.date || '').slice(0, 10);
      const mism = [];
      for (const [k, od] of Object.entries(poly.prices)) {
        const pd = (od.date || '').slice(0, 10), sd = seed[k];
        if (pd && sd && pd !== sd) mism.push(`${k}: Seed ${sd} ≠ real ${pd}`);
      }
      if (mism.length) add('error', `${mism.length} Fixture(s) falsch datiert`,
        `Spielplan weicht vom echten Polymarket-Datum ab → Picks am falschen Tag. ${mism.slice(0, 3).join(' · ')}`);
    }

    // ── Live-Check 4: Kill-Switch ────────────────────────────────────────
    if (ks && ks.enabled === false) add('warn', 'Auto-Trading pausiert (Kill-Switch)',
      `Trading ist manuell gestoppt${ks.reason ? ': ' + ks.reason : ''}. Resume via GitHub Action "Kill-Switch".`);

    // ── Live-Check 5: Trading-Odds frisch GEHOLT? (16.06.2026) ──────────
    // Pinnacle-Odds treiben jeden Trade-Edge. Quelle der Frische = _meta.oddsFetchedAt
    // (von fetch_wm_odds bei JEDEM Lauf gesetzt, auch ohne Bewegung — nicht der letzte
    // Snapshot, der bei flachen Linien ewig alt aussieht). manage holt alle 30min,
    // also ist >2h schon verdächtig, >4h = Feed/Runner hängt → KEINE frischen Trades.
    if (!wmOver && oddsHist && typeof oddsHist === 'object') {
      const fetchedAt = oddsHist._meta && oddsHist._meta.oddsFetchedAt;
      let ts = _stParseTs(fetchedAt);
      if (!ts) {   // Fallback (alte Daten ohne _meta): jüngster Snapshot
        for (const arr of Object.values(oddsHist)) {
          if (!Array.isArray(arr) || !arr.length) continue;
          const t = _stParseTs(arr[arr.length - 1].ts);
          if (t && (!ts || t > ts)) ts = t;
        }
      }
      const age = _stAgeH(ts);
      if (age === null) add('error', 'Keine Trading-Odds', 'wm2026-odds-history.json leer/ohne Fetch-Zeitstempel — fetch_wm_odds prüfen.');
      else if (age > 4) add('error', `Trading-Odds ${age.toFixed(1)}h nicht geholt`,
        `fetch_wm_odds liefert nicht (API-Limit / Runner offline / Workflow). Edges laufen gegen veraltete Pinnacle → bei >24h stoppt der Auto-Trader ganz.`);
      else if (age > 2) add('warn', `Trading-Odds ${age.toFixed(1)}h nicht geholt`, 'manage-wm-poly sollte alle 30min holen — Lauf beobachten.');
    }

    // ── Live-Check 6: Poly-Preise-Alter (manage-Zyklus-Heartbeat) ────────
    if (!wmOver && poly) {
      const age = _stAgeH(_stParseTs(poly.generatedAt));
      if (age !== null && age > 4) add('error', `Poly-Preise ${age.toFixed(1)}h alt`, 'manage-wm-poly hängt (alle 30min erwartet) → kein Auto-Trading. Runner/Workflow prüfen.');
      else if (age !== null && age > 2) add('warn', `Poly-Preise ${age.toFixed(1)}h alt`, 'Älter als der 30min-Trading-Takt — manage-wm-poly beobachten.');
    }

    // ── Live-Check 7: Balance-Alter ──────────────────────────────────────
    if (!wmOver && bal) {
      const age = _stAgeH(_stParseTs(bal.updatedAt));
      if (age !== null && age > 30) add('warn', `Balance ${age.toFixed(0)}h alt`, 'wm_poly_balance veraltet → Bankroll-Caps auf altem Stand.');
    }

    // ── Live-Check 8: Daily-Bet-Cap ──────────────────────────────────────
    if (autobets && Array.isArray(autobets.bets)) {
      const today = new Date().toISOString().slice(0, 10);
      const n = autobets.bets.filter(b => (b.placedAt || '').slice(0, 10) === today).length;
      if (n >= 8) add('info', `Daily-Bet-Cap erreicht (${n}/8)`, 'Heute werden keine weiteren Auto-Trades ausgelöst.');
    }

    _stRenderProblems(problems, valRep);
    _stRenderIntegrity(status);
    _stRenderServer(status);
    _stRenderLearning(data, ledger, weights);
    _stRenderSignals(data, status);
    _stRenderVerdict(problems, status, valRep, wmOver);
    _stRenderFeeds();   // eigene Fetches (inkl. Files die oben nicht geladen wurden)
  } finally {
    _stRunning = false;
  }
}

// (26.06.2026, Lucas: Status Liga/Intl-Toggle) — schlanker Liga-Pfad.
// Nutzt dieselben Render-Helfer wie WM (Verdict/Problems/Integrity), aber
// KEINE Poly/Kill-Switch/Auto-Bet/Signal-Live-Checks (die sind WM-spezifisch).
// 13.07.2026: generisch über ST_DATASETS — vorher hart auf liga-*.json, damit war der
// MLS-Status unerreichbar, obwohl mls_status.json existiert und committet wird.
async function _runLigaStatus() {
  const f = ST_FILES(_stDataset);
  const [ligaData, ligaStatus, ligaLedger, ligaWeights] = await Promise.all([
    _stGet(f.data), _stGet(f.status), _stGet(f.ledger), _stGet(f.weights),
  ]);
  // Lern-Status auch im Liga-Tab (dataset-eigene Dateien) — greift der Loop dort?
  _stRenderLearning(ligaData, ligaLedger, ligaWeights);

  // WM-only Sektionen leeren, damit kein stale WM-Inhalt unter dem Liga-Tab hängt.
  const clear = (id, msg) => { const e = document.getElementById(id); if (e) e.innerHTML = msg || ''; };
  clear('st_server', '<div style="color:var(--muted);text-align:center;padding:14px;">Liga-Ansicht — Server-Readiness ist WM-spezifisch.</div>');
  clear('st_signals', '<div style="color:var(--muted);text-align:center;padding:14px;">Liga-Ansicht — Signal-Matrix ist WM-spezifisch.</div>');
  clear('st_feeds', '<div style="color:var(--muted);text-align:center;padding:14px;">Liga-Ansicht — WM-Feeds ausgeblendet.</div>');
  const sigCnt = document.getElementById('st_signalsCount'); if (sigCnt) sigCnt.textContent = '';
  const srvTs = document.getElementById('st_serverTs'); if (srvTs) srvTs.textContent = '';

  // Noch kein Liga-Lauf: freundlicher Hinweis statt Crash.
  if (!ligaStatus || !Array.isArray(ligaStatus.checks)) {
    _stRenderVerdict([], null, null);
    const pe = document.getElementById('st_problems');
    if (pe) pe.innerHTML = '<div style="text-align:center;padding:20px;color:var(--muted);font-weight:600;">⚽ Liga-Status kommt mit dem nächsten Liga-Lauf.</div>';
    const ie = document.getElementById('st_integrity');
    if (ie) ie.innerHTML = '<div style="color:var(--muted);text-align:center;padding:14px;">liga_status.json noch nicht vorhanden.</div>';
    const ic = document.getElementById('st_integrityCount'); if (ic) ic.textContent = '';
    return;
  }

  // Probleme aus den nicht-ok Checks bauen.
  const problems = [];
  for (const c of ligaStatus.checks) {
    if (c.ok) continue;
    const detail = ((c.failures || []).slice(0, 4).join(' · ')) + (c.hint ? (' — ' + c.hint) : '');
    problems.push({ sev: c.severity === 'error' ? 'error' : 'warn', title: c.label, detail });
  }

  // Feed-Frische: liga-data.json läuft 2×/Tag → >14h alt = Warnung.
  const meta = (ligaData && ligaData._meta) || {};
  const dataTs = _stParseTs(meta.dataUpdatedAt);
  const dataAge = _stAgeH(dataTs);
  if (dataAge === null) problems.push({ sev: 'warn', title: 'Liga-Daten ohne Frische-Stempel', detail: 'liga-data.json fehlt oder _meta.dataUpdatedAt nicht gesetzt — Liga-Lauf prüfen.' });
  else if (dataAge > 14) problems.push({ sev: 'warn', title: `Liga-Daten ${dataAge.toFixed(1)}h alt`, detail: 'Liga-Pipeline sollte 2×/Tag laufen (< 14h). update-liga-Workflow beobachten.' });

  // Verdict / Problems / Integrity über die bestehenden Helfer rendern.
  _stRenderVerdict(problems, ligaStatus, null);
  _stRenderProblems(problems, null);
  _stRenderIntegrity(ligaStatus);

  // Kompakte Liga-Zähler-/Frische-Zeile über die Integritäts-Liste setzen.
  const ie = document.getElementById('st_integrity');
  if (ie) {
    const groups = ligaData && ligaData.groups ? Object.values(ligaData.groups) : [];
    let nTeams = 0, nFx = 0;
    for (const g of groups) {
      nTeams += (g.teams || []).length;
      nFx += (g.fixtures || []).length;
    }
    // odds/xgStats/picks liegen TOP-LEVEL in liga-data.json (nicht je Gruppe). 26.06.2026.
    const nOdds = Object.keys((ligaData && ligaData.odds) || {}).length;
    const nXg = Object.keys((ligaData && ligaData.xgStats) || {}).length;
    const nPicks = Object.values((ligaData && ligaData.picks) || {})
      .reduce((s, v) => s + (Array.isArray(v) ? v.length : 0), 0);
    const when = _stAgo(dataTs || _stParseTs(ligaStatus.generatedAt));
    const row = document.createElement('div');
    row.id = 'st_ligaSummary';
    row.style.cssText = 'background:var(--card2);border:1px solid var(--border);border-radius:9px;padding:10px 13px;margin-bottom:6px;font-size:11.5px;color:var(--text);';
    row.innerHTML = `${groups.length} Ligen · ${nTeams} Teams · ${nFx} Fixtures · ${nOdds} Quoten · ${nXg} xG-Teams · ${nPicks} Picks &nbsp;·&nbsp; <span style="color:var(--muted);">zuletzt aktualisiert ${when}</span>`;
    const old = document.getElementById('st_ligaSummary'); if (old) old.remove();
    ie.insertBefore(row, ie.firstChild);
  }
}

function _stRenderVerdict(problems, status, valRep, wmOver) {
  const el = document.getElementById('st_verdict'); if (!el) return;
  const errs = problems.filter(p => p.sev === 'error').length;
  const warns = problems.filter(p => p.sev === 'warn').length;
  const srvRank = _SEV_RANK[(status && status.verdict) || 'ok'] || 0;
  const liveRank = errs ? 3 : warns ? 2 : 0;
  // 20.07.2026 WM-Winterisierung: bei beendetem Turnier sind Server-Readiness + Pick-Validator
  // eingefroren (Pipeline pausiert) → ihre Warnungen sind ERWARTET, nicht aktiv. Gesamtstatus daher
  // nicht rot/gelb ziehen; die Zählungen bleiben informativ sichtbar, aber der Verdict ist „beendet".
  const worst = wmOver ? 0 : Math.max(srvRank, liveRank);
  const sev = worst >= 3 ? 'error' : worst >= 2 ? 'warn' : 'ok';
  const m = _SEV_META[sev];
  const srvErr = status ? (status.errors || []).length : 0;
  const srvWarn = status ? (status.warns || []).length : 0;
  const valErr = valRep && valRep.stats ? (valRep.stats.errors || 0) : 0;

  document.getElementById('st_verdictIcon').textContent = wmOver ? '🏁' : m.icon;
  const title = wmOver ? 'WM 2026 beendet — winterisiert'
    : sev === 'error' ? 'Es gibt Probleme — bitte prüfen'
    : sev === 'warn' ? 'Läuft, mit Hinweisen' : 'Alles läuft sauber';
  document.getElementById('st_verdictTitle').textContent = title;
  document.getElementById('st_verdictTitle').style.color = m.col;
  document.getElementById('st_verdictSub').innerHTML = wmOver
    ? `🏁 Turnier beendet — Server-Readiness (<b>${srvErr}</b>) &amp; Pick-Validator (<b>${valErr}</b>) sind eingefrorene WM-Historie, erwartbar. Live-Checks pausiert.`
    : `Live: <b>${errs}</b> Fehler · <b>${warns}</b> Warnungen &nbsp;|&nbsp; Server-Readiness: <b>${srvErr}</b> Fehler · <b>${srvWarn}</b> Hinweise &nbsp;|&nbsp; Pick-Validator: <b>${valErr}</b> Fehler`;
  el.style.borderColor = m.col;
  el.style.background = m.bg;
  const badge = (n, s) => n > 0 ? `<div style="background:rgba(0,0,0,.25);border:1px solid ${_SEV_META[s].col};border-radius:8px;padding:6px 12px;text-align:center;min-width:54px;"><div style="font-size:18px;font-weight:800;color:${_SEV_META[s].col};">${n}</div><div style="font-size:9px;opacity:.7;text-transform:uppercase;">${_SEV_META[s].lbl}</div></div>` : '';
  document.getElementById('st_verdictCounts').innerHTML = wmOver ? ''
    : badge(errs + srvErr + valErr, 'error') + badge(warns + srvWarn, 'warn');

  // Roter/gelber Punkt am Status-Tab in der Hauptnavi — sichtbar ohne reinzuklicken
  // navStatusDot sitzt im „Mehr"-Dropdown (Status-Eintrag); navMoreDot spiegelt ihn auf den
  // „Mehr ▾"-Button, damit ein Alarm auch ohne Aufklappen sichtbar ist (28.06.2026).
  [document.getElementById('navStatusDot'), document.getElementById('navMoreDot')].forEach(dot => {
    if (!dot) return;
    if (sev === 'ok') { dot.style.display = 'none'; }
    else {
      dot.style.display = 'inline-block';
      dot.style.background = m.col;
      dot.style.boxShadow = `0 0 6px ${m.col}`;
      dot.title = title;
    }
  });
}

function _stRenderProblems(problems, valRep) {
  const el = document.getElementById('st_problems'); if (!el) return;
  let html;
  if (!problems.length) {
    html = `<div style="text-align:center;padding:20px;color:#3fb950;font-weight:700;">🟢 Keine Live-Probleme — alle Browser-Checks grün</div>`;
  } else {
    problems.sort((a, b) => _SEV_RANK[b.sev] - _SEV_RANK[a.sev]);
    html = problems.map(p => {
      const m = _SEV_META[p.sev];
      return `<div style="background:${m.bg};border:1px solid ${m.bd};border-radius:9px;padding:11px 14px;display:flex;gap:11px;align-items:flex-start;">
        <span style="flex-shrink:0;font-size:15px;">${m.icon}</span>
        <div style="flex:1;min-width:0;">
          <div style="font-weight:700;color:var(--text);font-size:13px;">${p.title}</div>
          <div style="color:var(--muted);font-size:11.5px;margin-top:2px;">${p.detail}</div>
        </div>
      </div>`;
    }).join('');
  }

  // ── Pick-Validator-Issues auflisten (16.06.2026) ──────────────────────
  // Vorher stand im Header nur „Pick-Validator: 3 Fehler", aber die 3 wurden
  // NIRGENDS gelistet. Jetzt mit Code + Spiel + Markt + Begründung sichtbar.
  const issues = (valRep && Array.isArray(valRep.issues)) ? valRep.issues : [];
  if (issues.length) {
    const rank = { error: 3, warning: 2, warn: 2 };
    issues.sort((a, b) => (rank[b.level] || 0) - (rank[a.level] || 0));
    html += `<div style="margin-top:16px;font-weight:700;font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.6px;">🔍 Pick-Validator · ${issues.length} Hinweis(e)</div>`;
    html += issues.map(i => {
      const m = _SEV_META[i.level === 'error' ? 'error' : 'warn'];
      const head = [i.code, i.matchKey, i.market].filter(Boolean).join(' · ');
      return `<div style="background:${m.bg};border:1px solid ${m.bd};border-radius:9px;padding:11px 14px;display:flex;gap:11px;align-items:flex-start;margin-top:7px;">
        <span style="flex-shrink:0;font-size:15px;">${m.icon}</span>
        <div style="flex:1;min-width:0;">
          <div style="font-weight:700;color:var(--text);font-size:13px;">${head}</div>
          <div style="color:var(--muted);font-size:11.5px;margin-top:2px;">${i.message || ''}</div>
        </div>
      </div>`;
    }).join('');
  }
  el.innerHTML = html;
}

function _stRenderIntegrity(status) {
  const el = document.getElementById('st_integrity'); if (!el) return;
  const cntEl = document.getElementById('st_integrityCount');
  const checks = (status && Array.isArray(status.checks)) ? status.checks : null;
  if (!checks) {
    el.innerHTML = '<div style="color:var(--muted);text-align:center;padding:14px;">wm_status.json hat noch keine Integritäts-Checks — kommt mit dem nächsten Pipeline-Lauf.</div>';
    if (cntEl) cntEl.textContent = '';
    return;
  }
  const okN = checks.filter(c => c.ok).length;
  if (cntEl) cntEl.textContent = `${okN}/${checks.length} Checks sauber`;
  // Fehler zuerst (error > warn > ok), dann nach Fail-Anzahl
  const rank = c => c.ok ? 0 : (c.severity === 'error' ? 3 : 2);
  const sorted = [...checks].sort((a, b) => rank(b) - rank(a) || (b.nFail - a.nFail));
  el.innerHTML = sorted.map(c => {
    const m = c.ok ? _SEV_META.ok : (c.severity === 'error' ? _SEV_META.error : _SEV_META.warn);
    const fails = (c.failures || []);
    const body = c.ok
      ? `<span style="color:#3fb950;font-size:11px;">sauber</span>`
      : `<span style="color:${m.col};font-size:11px;font-weight:700;">${c.nFail} Fehler</span>`;
    const detail = (!c.ok && fails.length) ? `
      <details style="margin-top:6px;">
        <summary style="cursor:pointer;font-size:10px;color:var(--muted);">betroffene Spiele zeigen (${fails.length})</summary>
        <div style="margin-top:6px;display:flex;flex-direction:column;gap:3px;">
          ${fails.map(f => `<div style="font-size:11px;color:var(--text);font-family:monospace;">· ${f}</div>`).join('')}
        </div>
      </details>` : '';
    return `<div style="background:${m.bg};border:1px solid ${m.bd};border-radius:9px;padding:10px 13px;">
      <div style="display:flex;align-items:center;gap:9px;">
        <span style="font-size:14px;">${m.icon}</span>
        <div style="flex:1;min-width:0;">
          <div style="font-weight:700;font-size:12.5px;color:var(--text);">${c.label}</div>
          <div style="font-size:10.5px;color:var(--muted);">${c.note || ''}</div>
        </div>
        ${body}
      </div>${detail}
    </div>`;
  }).join('');
}

function _stRenderServer(status) {
  const el = document.getElementById('st_server'); if (!el) return;
  const tsEl = document.getElementById('st_serverTs');
  if (!status) {
    el.innerHTML = `<div style="color:var(--muted);text-align:center;padding:14px;">wm_status.json noch nicht vorhanden — wird beim nächsten Pipeline-Lauf erzeugt.</div>`;
    return;
  }
  const age = _stAgo(_stParseTs(status.generatedAt));
  if (tsEl) tsEl.textContent = `Stand: ${age}`;
  const errs = status.errors || [], warns = status.warns || [], oks = status.oks || [];
  const line = (txt, sev) => {
    const m = _SEV_META[sev];
    return `<div style="display:flex;gap:9px;align-items:flex-start;font-size:12px;padding:6px 0;border-bottom:1px solid var(--border);">
      <span style="flex-shrink:0;">${m.icon}</span><span style="color:var(--text);">${txt}</span></div>`;
  };
  let html = '';
  errs.forEach(e => html += line(e, 'error'));
  warns.forEach(w => html += line(w, 'warn'));
  if (!errs.length && !warns.length) html += `<div style="color:#3fb950;font-weight:700;padding:8px 0;">🟢 Letzter Lauf ohne Lücken — ${oks.length} Checks OK</div>`;
  else html += `<div style="font-size:11px;color:var(--muted);padding-top:8px;">+ ${oks.length} Checks OK</div>`;
  el.innerHTML = html;
}

let _stSignalChart = null;

// FIX 14.06.2026: chance_creation + form_rating ergänzt (waren seit ihrer Einführung
// nicht in der Matrix → „X/15" statt 17, zwei stark feuernde Signale unsichtbar).
const _ST_SIG_ALL = ['lead_lag_bias', 'public_static_bias', 'travel_burden', 'injury', 'form_trend',
  'h2h_pattern', 'xg_strength', 'polymarket_sharp', 'steam_lag', 'pressure_index',
  'lineup_signal', 'apif_predictions', 'weather_signal', 'incentive_signal', 'altitude_signal',
  'chance_creation', 'form_rating'];
const _ST_SIG_CORE = new Set(['form_trend', 'xg_strength', 'travel_burden', 'pressure_index']);
const _ST_SIG_COND = {
  lead_lag_bias: 'nur bei Quotenbewegung', injury: 'nur bei Ausfällen',
  polymarket_sharp: 'nur bei Poly↔Pinn-Divergenz', steam_lag: 'nur bei Steam-Move',
  lineup_signal: 'feuert T-1h', incentive_signal: 'ab MD2',
  public_static_bias: 'nur bei Public-Divergenz', h2h_pattern: 'nur ≥3 H2H',
  weather_signal: 'nur ≥30°C', apif_predictions: 'wenn APIF-Daten da',
  altitude_signal: 'nur Höhen-Venues',
  chance_creation: 'wenn Team-Stats da', form_rating: 'wenn Team-Stats da',
};

function _stRenderSignals(data, status) {
  const el = document.getElementById('st_signals'); if (!el) return;
  const fire = {}; _ST_SIG_ALL.forEach(n => fire[n] = 0);
  if (data && data.picks) {
    // Primär: echte Zähler aus den aktuellen Picks (frischeste Wahrheit).
    for (const plist of Object.values(data.picks)) {
      if (!Array.isArray(plist)) continue;
      for (const p of plist) for (const s of (p.signals || [])) if (s.name in fire) fire[s.name]++;
    }
  } else if (status && status.perSignal) {
    // Fallback 1 (14.06.2026): autoritative Zähler aus dem letzten Pipeline-Lauf.
    for (const n of _ST_SIG_ALL) if (n in status.perSignal) fire[n] = status.perSignal[n];
  } else if (status && Array.isArray(status.signalsFired)) {
    // Fallback 2: nur binär (feuert/feuert nicht).
    status.signalsFired.forEach(n => { if (n in fire) fire[n] = 1; });
  }
  const fired = _ST_SIG_ALL.filter(n => fire[n] > 0).length;
  const cnt = document.getElementById('st_signalsCount');
  if (cnt) cnt.textContent = `${fired}/${_ST_SIG_ALL.length} feuern`;

  const maxC = Math.max(1, ..._ST_SIG_ALL.map(n => fire[n]));
  const sorted = [..._ST_SIG_ALL].sort((a, b) => fire[b] - fire[a]);
  el.innerHTML = sorted.map(n => {
    const c = fire[n], on = c > 0, core = _ST_SIG_CORE.has(n);
    const col = on ? '#3fb950' : core ? '#f85149' : '#6e7681';
    const pct = Math.round(c / maxC * 100);
    const right = on ? `${c}×` : (core ? 'KERN still' : (_ST_SIG_COND[n] || 'kontextabh.'));
    return `<div style="display:flex;align-items:center;gap:8px;">
      <div style="width:128px;flex-shrink:0;font-size:11px;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${n}">${n}</div>
      <div style="flex:1;background:var(--card2);border-radius:4px;height:15px;overflow:hidden;">
        <div style="height:100%;width:${pct}%;background:${col};opacity:${on ? 0.9 : 0.25};border-radius:4px;"></div>
      </div>
      <div style="width:118px;flex-shrink:0;font-size:10px;color:${col};text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${right}</div>
    </div>`;
  }).join('');

  _stRenderSignalTrend();
  _stRenderSignalWeights(fire);
}

async function _stRenderSignalTrend() {
  const cv = document.getElementById('st_signalTrend');
  const note = document.getElementById('st_signalTrendNote');
  if (!cv || typeof Chart === 'undefined') return;
  const hist = await _stGet('wm_signal_history.json');
  if (!Array.isArray(hist) || hist.length === 0) {
    if (note) note.textContent = 'Noch keine History — baut sich ab dem nächsten Pipeline-Lauf täglich auf.';
    return;
  }
  const labels = hist.map(h => (h.date || '').slice(5));
  const fired = hist.map(h => h.fired);
  const pws = hist.map(h => h.picksWithSignal);
  if (_stSignalChart) { try { _stSignalChart.destroy(); } catch (e) {} }
  _stSignalChart = new Chart(cv.getContext('2d'), {
    type: 'line',
    data: { labels, datasets: [
      { label: 'Signale feuern (/15)', data: fired, borderColor: '#00d4a1', backgroundColor: 'rgba(0,212,161,.12)', tension: .3, fill: true, yAxisID: 'y', pointRadius: 3 },
      { label: 'Picks mit Signal', data: pws, borderColor: '#a78bfa', tension: .3, yAxisID: 'y1', pointRadius: 2 },
    ] },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#8b949e', font: { size: 10 }, boxWidth: 12 } } },
      scales: {
        y:  { position: 'left',  min: 0, max: 15, title: { display: true, text: 'Signale', color: '#8b949e', font: { size: 9 } }, ticks: { color: '#8b949e', font: { size: 9 } }, grid: { color: 'rgba(255,255,255,.05)' } },
        y1: { position: 'right', min: 0, ticks: { color: '#8b949e', font: { size: 9 } }, grid: { display: false } },
        x:  { ticks: { color: '#8b949e', font: { size: 9 } }, grid: { display: false } },
      },
    },
  });
  if (note) note.textContent = `${hist.length} Tag(e) erfasst · aktuell ${fired[fired.length - 1]}/15 Signale · ${pws[pws.length - 1]} Picks mit Signal`;
}

async function _stRenderSignalWeights(fire) {
  const el = document.getElementById('st_signalWeights'); if (!el) return;
  const w = await _stGet('signal_weights.json');
  const hist = await _stGet('wm_signal_history.json');
  const first = (Array.isArray(hist) && hist.length) ? (hist[0].weights || {}) : {};
  if (!w) { el.innerHTML = '<div style="color:var(--muted);font-size:11px;">signal_weights.json nicht gefunden</div>'; return; }
  const rows = _ST_SIG_ALL.filter(n => w[n] && typeof w[n].weight === 'number');
  if (!rows.length) { el.innerHTML = '<div style="color:var(--muted);font-size:11px;">Noch keine Gewichte.</div>'; return; }
  // nach Gewicht sortiert (auffälligste zuerst)
  rows.sort((a, b) => Math.abs((w[b].weight || 1) - 1) - Math.abs((w[a].weight || 1) - 1));
  el.innerHTML = rows.map(n => {
    const wt = w[n].weight, nobs = w[n].n_observations || 0;
    const f0 = first[n];
    const delta = (typeof f0 === 'number') ? wt - f0 : 0;
    const dCol = delta > 0.001 ? '#3fb950' : delta < -0.001 ? '#f85149' : '#6e7681';
    const dStr = Math.abs(delta) < 0.001 ? '±0' : (delta > 0 ? '+' : '') + delta.toFixed(2);
    const wCol = wt > 1.02 ? '#3fb950' : wt < 0.98 ? '#f85149' : 'var(--text)';
    return `<div style="background:var(--card2);border:1px solid var(--border);border-radius:8px;padding:8px 10px;">
      <div style="font-size:11px;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${n}">${n}</div>
      <div style="display:flex;align-items:baseline;gap:6px;margin-top:2px;">
        <span style="font-size:15px;font-weight:700;color:${wCol};">${wt.toFixed(2)}</span>
        <span style="font-size:10px;color:${dCol};">Δ ${dStr}</span>
        <span style="font-size:9px;color:var(--muted);margin-left:auto;">${nobs} obs</span>
      </div>
    </div>`;
  }).join('');
}

async function _stRenderFeeds() {
  const el = document.getElementById('st_feeds'); if (!el) return;
  const metas = await Promise.all(_ST_FEEDS.map(async f => {
    const d = await _stGet(f.file);
    if (d === null) return { f, missing: true };
    let ts = null;
    if (f.ts === '_newestSnap' && typeof d === 'object') {
      for (const arr of Object.values(d)) if (Array.isArray(arr) && arr.length) { const t = _stParseTs(arr[arr.length - 1].ts); if (t && (!ts || t > ts)) ts = t; }
    } else if (f.ts && typeof d === 'object') ts = _stParseTs(d[f.ts]);
    return { f, missing: false, ts };
  }));
  el.innerHTML = metas.map(({ f, missing, ts }) => {
    let col, val, sub;
    if (missing) {
      col = f.crit ? '#f85149' : '#6e7681';
      val = f.crit ? 'FEHLT' : 'nicht vorhanden';
      sub = f.crit ? 'kritisch — Fetch prüfen' : 'optional / kontextabhängig';
    } else if (!f.ts) {
      col = '#3fb950'; val = 'vorhanden'; sub = 'kein Zeitstempel';
    } else {
      const age = _stAgeH(ts);
      if (age === null) { col = '#6e7681'; val = '—'; sub = 'kein Zeitstempel'; }
      else { col = age > f.errH ? '#f85149' : age > f.warnH ? '#e3b341' : '#3fb950'; val = _stAgo(ts); sub = `Soll < ${f.warnH}h`; }
    }
    return `<div style="background:var(--card2);border:1px solid var(--border);border-radius:10px;padding:13px 15px;">
      <div style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.4px;margin-bottom:6px;">${f.icon} ${f.label}</div>
      <div style="font-size:15px;font-weight:700;color:${col};margin-bottom:3px;">${val}</div>
      <div style="font-size:10px;color:var(--muted);">${f.file} · ${sub}</div>
    </div>`;
  }).join('');
}
