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

async function runStatusPage(force) {
  if (_stRunning) return;
  _stRunning = true;
  try {
    const [data, poly, oddsHist, bal, ks, autobets, status, valRep] = await Promise.all([
      _stGet('wm2026-data.json'), _stGet('wm_poly_prices.json'), _stGet('wm2026-odds-history.json'),
      _stGet('wm_poly_balance.json'), _stGet('wm_kill_switch.json'), _stGet('wm_auto_bets_placed.json'),
      _stGet('wm_status.json'), _stGet('pick_validation_report.json'),
    ]);

    const problems = [];
    const add = (sev, title, detail) => problems.push({ sev, title, detail });

    // ── Live-Check 1: Stale Edges (edge_X ≠ fair_X − poly_X) ──────────────
    if (poly && Array.isArray(poly.allFixtures)) {
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

    // ── Live-Check 5: Pinnacle-Odds-Alter (Stale-Odds-Breaker) ──────────
    if (oddsHist && typeof oddsHist === 'object') {
      let newest = null;
      for (const arr of Object.values(oddsHist)) {
        if (!Array.isArray(arr) || !arr.length) continue;
        const t = _stParseTs(arr[arr.length - 1].ts);
        if (t && (!newest || t > newest)) newest = t;
      }
      const age = _stAgeH(newest);
      if (age === null) add('warn', 'Keine Odds-Snapshots', 'wm2026-odds-history.json leer/unlesbar.');
      else if (age > 24) add('error', `Pinnacle-Odds ${age.toFixed(0)}h alt`,
        `> 24h → Auto-Trader-Stale-Odds-Breaker greift, KEINE Trades. fetch_wm_odds / GitHub Actions prüfen.`);
      else if (age > 12) add('warn', `Pinnacle-Odds ${age.toFixed(0)}h alt`, 'Älter als ein halber Tag — Fetch beobachten.');
    }

    // ── Live-Check 6: Poly-Preise-Alter ──────────────────────────────────
    if (poly) {
      const age = _stAgeH(_stParseTs(poly.generatedAt));
      if (age !== null && age > 24) add('error', `Poly-Preise ${age.toFixed(0)}h alt`, 'manage-wm-poly / fetch_wm_poly_prices prüfen.');
      else if (age !== null && age > 12) add('warn', `Poly-Preise ${age.toFixed(0)}h alt`, 'Älter als erwartet (5×/Tag).');
    }

    // ── Live-Check 7: Balance-Alter ──────────────────────────────────────
    if (bal) {
      const age = _stAgeH(_stParseTs(bal.updatedAt));
      if (age !== null && age > 30) add('warn', `Balance ${age.toFixed(0)}h alt`, 'wm_poly_balance veraltet → Bankroll-Caps auf altem Stand.');
    }

    // ── Live-Check 8: Daily-Bet-Cap ──────────────────────────────────────
    if (autobets && Array.isArray(autobets.bets)) {
      const today = new Date().toISOString().slice(0, 10);
      const n = autobets.bets.filter(b => (b.placedAt || '').slice(0, 10) === today).length;
      if (n >= 8) add('info', `Daily-Bet-Cap erreicht (${n}/8)`, 'Heute werden keine weiteren Auto-Trades ausgelöst.');
    }

    _stRenderProblems(problems);
    _stRenderIntegrity(status);
    _stRenderServer(status);
    _stRenderSignals(data, status);
    _stRenderVerdict(problems, status, valRep);
    _stRenderFeeds();   // eigene Fetches (inkl. Files die oben nicht geladen wurden)
  } finally {
    _stRunning = false;
  }
}

function _stRenderVerdict(problems, status, valRep) {
  const el = document.getElementById('st_verdict'); if (!el) return;
  const errs = problems.filter(p => p.sev === 'error').length;
  const warns = problems.filter(p => p.sev === 'warn').length;
  const srvRank = _SEV_RANK[(status && status.verdict) || 'ok'] || 0;
  const liveRank = errs ? 3 : warns ? 2 : 0;
  const worst = Math.max(srvRank, liveRank);
  const sev = worst >= 3 ? 'error' : worst >= 2 ? 'warn' : 'ok';
  const m = _SEV_META[sev];
  const srvErr = status ? (status.errors || []).length : 0;
  const srvWarn = status ? (status.warns || []).length : 0;
  const valErr = valRep && valRep.stats ? (valRep.stats.errors || 0) : 0;

  document.getElementById('st_verdictIcon').textContent = m.icon;
  const title = sev === 'error' ? 'Es gibt Probleme — bitte prüfen'
    : sev === 'warn' ? 'Läuft, mit Hinweisen' : 'Alles läuft sauber';
  document.getElementById('st_verdictTitle').textContent = title;
  document.getElementById('st_verdictTitle').style.color = m.col;
  document.getElementById('st_verdictSub').innerHTML =
    `Live: <b>${errs}</b> Fehler · <b>${warns}</b> Warnungen &nbsp;|&nbsp; Server-Readiness: <b>${srvErr}</b> Fehler · <b>${srvWarn}</b> Hinweise &nbsp;|&nbsp; Pick-Validator: <b>${valErr}</b> Fehler`;
  el.style.borderColor = m.col;
  el.style.background = m.bg;
  const badge = (n, s) => n > 0 ? `<div style="background:rgba(0,0,0,.25);border:1px solid ${_SEV_META[s].col};border-radius:8px;padding:6px 12px;text-align:center;min-width:54px;"><div style="font-size:18px;font-weight:800;color:${_SEV_META[s].col};">${n}</div><div style="font-size:9px;opacity:.7;text-transform:uppercase;">${_SEV_META[s].lbl}</div></div>` : '';
  document.getElementById('st_verdictCounts').innerHTML =
    badge(errs + srvErr + valErr, 'error') + badge(warns + srvWarn, 'warn');

  // Roter/gelber Punkt am Status-Tab in der Hauptnavi — sichtbar ohne reinzuklicken
  const dot = document.getElementById('navStatusDot');
  if (dot) {
    if (sev === 'ok') { dot.style.display = 'none'; }
    else {
      dot.style.display = 'inline-block';
      dot.style.background = m.col;
      dot.style.boxShadow = `0 0 6px ${m.col}`;
      dot.title = title;
    }
  }
}

function _stRenderProblems(problems) {
  const el = document.getElementById('st_problems'); if (!el) return;
  if (!problems.length) {
    el.innerHTML = `<div style="text-align:center;padding:20px;color:#3fb950;font-weight:700;">🟢 Keine Live-Probleme — alle Browser-Checks grün</div>`;
    return;
  }
  problems.sort((a, b) => _SEV_RANK[b.sev] - _SEV_RANK[a.sev]);
  el.innerHTML = problems.map(p => {
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

const _ST_SIG_ALL = ['lead_lag_bias', 'public_static_bias', 'travel_burden', 'injury', 'form_trend',
  'h2h_pattern', 'xg_strength', 'polymarket_sharp', 'steam_lag', 'pressure_index',
  'lineup_signal', 'apif_predictions', 'weather_signal', 'incentive_signal', 'altitude_signal'];
const _ST_SIG_CORE = new Set(['form_trend', 'xg_strength', 'travel_burden', 'pressure_index']);
const _ST_SIG_COND = {
  lead_lag_bias: 'nur bei Quotenbewegung', injury: 'nur bei Ausfällen',
  polymarket_sharp: 'nur bei Poly↔Pinn-Divergenz', steam_lag: 'nur bei Steam-Move',
  lineup_signal: 'feuert T-1h', incentive_signal: 'ab MD2',
  public_static_bias: 'nur bei Public-Divergenz', h2h_pattern: 'nur ≥3 H2H',
  weather_signal: 'nur ≥30°C', apif_predictions: 'wenn APIF-Daten da',
  altitude_signal: 'nur Höhen-Venues',
};

function _stRenderSignals(data, status) {
  const el = document.getElementById('st_signals'); if (!el) return;
  const fire = {}; _ST_SIG_ALL.forEach(n => fire[n] = 0);
  if (data && data.picks) {
    for (const plist of Object.values(data.picks)) {
      if (!Array.isArray(plist)) continue;
      for (const p of plist) for (const s of (p.signals || [])) if (s.name in fire) fire[s.name]++;
    }
  } else if (status && Array.isArray(status.signalsFired)) {
    status.signalsFired.forEach(n => { if (n in fire) fire[n] = 1; });
  }
  const fired = _ST_SIG_ALL.filter(n => fire[n] > 0).length;
  const cnt = document.getElementById('st_signalsCount');
  if (cnt) cnt.textContent = `${fired}/15 feuern`;

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
