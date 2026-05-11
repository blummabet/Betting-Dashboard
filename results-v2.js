/**
 * results-v2.js — BetEdge Results Tracking V2
 *
 * Architecture:
 *  - Picks saved to localStorage['betedge_picks_v2'] when cards render
 *  - Auto-resolve reads results-cache.json (updated 3× daily by GitHub Action)
 *  - Legacy import migrates usable data from picks_history.json
 *  - Zero server dependency — works on GitHub Pages and offline
 */

'use strict';

// ── Constants ─────────────────────────────────────────────────────────────────
const V2_KEY        = 'betedge_picks_v2';
const V2_RESULTS_URLS = [
  'http://localhost:3001/results-cache',
  'https://blummabet.github.io/Betting-Dashboard/results-cache.json',
];

// Markets where we need corners data
const CORNERS_MARKETS = /Ecken/i;
// Markets where we need cards data
const CARDS_MARKETS   = /Karten/i;
// Half-time markets
const HT_MARKETS      = /1\.\s*HZ/i;

// ── Storage ───────────────────────────────────────────────────────────────────
function _v2Load() {
  try { return JSON.parse(localStorage.getItem(V2_KEY) || '[]'); }
  catch { return []; }
}
function _v2Save(data) {
  try { localStorage.setItem(V2_KEY, JSON.stringify(data)); } catch(e) {}
}

// ── Pick saving (called by renderer.js after renderOverview) ──────────────────
// matchList: array of match objects from LEAGUES, already filtered to visible range
function savePicksV2(matchList) {
  if (!matchList || !matchList.length) return;
  if (typeof getBettingPicks !== 'function' || typeof deriveOdds !== 'function') return;

  const now   = new Date().toISOString();
  const store = _v2Load();
  const idx   = {};
  store.forEach((e, i) => { idx[_v2Id(e)] = i; });

  let added = 0, updated = 0;

  for (const match of matchList) {
    const lk    = match.leagueKey;
    const odds  = (typeof findOdds === 'function' && lk)
                    ? findOdds(lk, match.home, match.away)
                    : null;
    const oddsD = deriveOdds(odds || {});
    const picks = getBettingPicks(match, oddsD, lk) || [];
    const vis   = picks.filter(p => p.conf === 'high' || p.conf === 'medium');
    if (!vis.length) continue;

    const dateIso = _toIso(match.date || '');
    const id      = `${dateIso}-${lk}-${match.home}-${match.away}`;

    const entry = {
      id,
      date:       match.date || '',
      dateIso,
      league:     lk || '',
      leagueName: match.leagueName || lk || '',
      leagueFlag: match.leagueFlag || '',
      home:       match.home,
      away:       match.away,
      matchScore: Math.round((typeof computeMatchScore === 'function'
                    ? computeMatchScore(match, lk) : 0) * 10) / 10,
      source:     'v2',
      savedAt:    now,
      picks: vis.map(p => ({
        market:    p.market    || '',
        marketKey: _mKey(p.market || ''),
        icon:      p.icon      || '',
        conf:      p.conf      || 'medium',
        sc:        typeof p.sc === 'number' ? Math.round(p.sc * 1000) / 1000 : 0,
        odds:      p.odds      != null ? p.odds      : null,
        modelOdds: p.modelOdds != null ? p.modelOdds : null,
        value:     p.value     || null,
        oddsIsEst: p.oddsIsEst || false,
        result:    null,
        resolvedAt:null,
      })),
    };

    const existing = idx[id];
    if (existing !== undefined) {
      const old = store[existing];
      // Don't overwrite resolved results
      const hasResolved = (old.picks || []).some(p => p.result);
      if (!hasResolved) {
        store[existing] = entry;
        updated++;
      } else {
        // Merge: keep resolved picks' results but update everything else
        entry.picks = entry.picks.map(ep => {
          const op = (old.picks || []).find(p => p.market === ep.market);
          if (op && op.result) { ep.result = op.result; ep.resolvedAt = op.resolvedAt; }
          return ep;
        });
        store[existing] = entry;
        updated++;
      }
    } else {
      store.push(entry);
      idx[id] = store.length - 1;
      added++;
    }
  }

  if (added || updated) {
    _v2Save(store);
    console.log(`[V2] picks saved: +${added} new, ${updated} updated`);
  }
}

// ── Auto-resolve ──────────────────────────────────────────────────────────────
async function autoResolveV2(silent = false) {
  // Load results-cache.json
  let results = null;
  for (const url of V2_RESULTS_URLS) {
    try {
      const r = await fetch(url, { cache: 'no-store' });
      if (r.ok) { const d = await r.json(); results = d.fixtures || d; break; }
    } catch(_) {}
  }
  if (!Array.isArray(results) || !results.length) {
    if (!silent) _v2Toast('❌ results-cache.json nicht erreichbar');
    return 0;
  }

  // Build lookup: normalized "home|away" → fixture
  const lookup = {};
  for (const fx of results) {
    if (fx.goalsHome == null && fx.goalsAway == null) continue; // not resolved yet
    const key = _normPair(fx.home, fx.away);
    lookup[key] = fx;
  }

  const store = _v2Load();
  let resolved = 0;

  for (const entry of store) {
    const openPicks = entry.picks.filter(p => !p.result);
    if (!openPicks.length) continue;

    const fx = lookup[_normPair(entry.home, entry.away)];
    if (!fx) continue;
    // Only resolve if the match date matches (within 1 day tolerance)
    if (!_dateClose(entry.dateIso, fx.date)) continue;

    const now = new Date().toISOString();
    for (const p of openPicks) {
      const res = _resolveMarket(p.market, fx);
      if (res !== null) {
        p.result     = res;
        p.resolvedAt = now;
        resolved++;
      }
    }
  }

  _v2Save(store);
  if (!silent && resolved > 0) _v2Toast(`✅ ${resolved} Picks ausgewertet`);
  else if (!silent)            _v2Toast('⏳ Keine neuen Ergebnisse');
  return resolved;
}

// Resolve a single pick market against a finished fixture
function _resolveMarket(market, fx) {
  const m  = (market || '').trim();
  const ml = m.toLowerCase();
  const gH = fx.goalsHome ?? null;
  const gA = fx.goalsAway ?? null;
  const cH = fx.cornersHome ?? null;
  const cA = fx.cornersAway ?? null;
  const yH = fx.yellowHome  ?? 0;
  const yA = fx.yellowAway  ?? 0;
  const rH = fx.redHome     ?? 0;
  const rA = fx.redAway     ?? 0;
  const hH = fx.htHome      ?? null;
  const hA = fx.htAway      ?? null;

  if (gH == null || gA == null) return null; // no score data

  const diff   = gH - gA;
  const total  = gH + gA;
  const cards  = yH + yA + rH + rA;
  const corners = (cH != null && cA != null) ? cH + cA : null;

  // ── Result markets ───────────────────────────────────────────────────────
  if (ml === 'heimsieg')       return diff > 0  ? 'won' : 'lost';
  if (ml === 'auswärtssieg')   return diff < 0  ? 'won' : 'lost';
  if (ml === 'unentschieden')  return diff === 0 ? 'won' : 'lost';

  // ── Double Chance ────────────────────────────────────────────────────────
  if (/doppelte chance.*1x/i.test(ml))  return diff >= 0 ? 'won' : 'lost';
  if (/doppelte chance.*x2/i.test(ml))  return diff <= 0 ? 'won' : 'lost';
  if (/doppelte chance.*12/i.test(ml))  return diff !== 0 ? 'won' : 'lost';

  // ── BTTS ─────────────────────────────────────────────────────────────────
  if (/beide teams treffen: nein/i.test(ml)) return (gH === 0 || gA === 0) ? 'won' : 'lost';
  if (/beide teams treffen/i.test(ml))       return (gH > 0 && gA > 0)     ? 'won' : 'lost';

  // ── Goals over/under (Asian quarter lines) ───────────────────────────────
  const overMatch = m.match(/[Oo]ver\s+(\d+\.?\d*)\s+[Tt]ore/i) ||
                    m.match(/[Üü]ber\s+(\d+\.?\d*)\s+[Tt]ore/i);
  const underMatch = m.match(/[Uu]nder\s+(\d+\.?\d*)\s+[Tt]ore/i) ||
                     m.match(/[Uu]nter\s+(\d+\.?\d*)\s+[Tt]ore/i);

  if (overMatch) {
    const line = parseFloat(overMatch[1]);
    return _resolveAsian(total, line, 'over');
  }
  if (underMatch) {
    const line = parseFloat(underMatch[1]);
    return _resolveAsian(total, line, 'under');
  }

  // ── Asian Handicap ───────────────────────────────────────────────────────
  const ahH = m.match(/^ah\s+heim\s+([-+]?\d+\.?\d*)/i);
  const ahA = m.match(/^ah\s+ausw[^\s\d+-]*\.?\s+([-+]?\d+\.?\d*)/i);
  if (ahH) {
    const h = parseFloat(ahH[1]);
    return _resolveAsian(diff, -h, 'over'); // home wins by more than |h|
  }
  if (ahA) {
    const h = parseFloat(ahA[1]);
    return _resolveAsian(-diff, -h, 'over'); // away wins by more than |h|
  }

  // ── Corners ──────────────────────────────────────────────────────────────
  if (corners !== null) {
    const coM = m.match(/[Üü]ber\s+(\d+\.?\d*)\s+Ecken/i);
    const cuM = m.match(/[Uu]nter\s+(\d+\.?\d*)\s+Ecken/i);
    if (coM) return _resolveAsian(corners, parseFloat(coM[1]), 'over');
    if (cuM) return _resolveAsian(corners, parseFloat(cuM[1]), 'under');
  }

  // ── Cards ─────────────────────────────────────────────────────────────────
  if (/karten/i.test(ml)) {
    const ckM = m.match(/[Üü]ber\s+(\d+\.?\d*)\s+Karten/i);
    const ckU = m.match(/[Uu]nter\s+(\d+\.?\d*)\s+Karten/i);
    if (ckM) return _resolveAsian(cards, parseFloat(ckM[1]), 'over');
    if (ckU) return _resolveAsian(cards, parseFloat(ckU[1]), 'under');
  }

  // ── Half-time markets ─────────────────────────────────────────────────────
  if (/1\.\s*hz/i.test(ml) && hH != null && hA != null) {
    const htTotal = hH + hA;
    const htDiff  = hH - hA;
    if (/hz.*over 0\.5|hz.*über 0\.5/i.test(ml))  return htTotal >= 1 ? 'won' : 'lost';
    if (/hz.*over 1\.5/i.test(ml))                return htTotal >= 2 ? 'won' : 'lost';
    if (/hz.*under 0\.5/i.test(ml))               return htTotal === 0 ? 'won' : 'lost';
    if (/hz.*under 1\.5/i.test(ml))               return htTotal <= 1 ? 'won' : 'lost';
    if (/hz.*beide teams treffen: nein/i.test(ml))return (hH === 0 || hA === 0) ? 'won' : 'lost';
    if (/hz.*beide teams treffen/i.test(ml))       return (hH > 0 && hA > 0) ? 'won' : 'lost';
    if (/hz.*heimsieg/i.test(ml))                  return htDiff > 0 ? 'won' : 'lost';
    if (/hz.*auswärtssieg/i.test(ml))              return htDiff < 0 ? 'won' : 'lost';
    if (/hz.*unentschieden/i.test(ml))             return htDiff === 0 ? 'won' : 'lost';
  }

  return null; // unknown market
}

// Asian handicap resolver with quarter-line support
function _resolveAsian(actual, line, direction) {
  // Full-number lines: straightforward
  if (line % 0.5 === 0) {
    if (direction === 'over')  return actual > line ? 'won' : actual === line ? 'void' : 'lost';
    if (direction === 'under') return actual < line ? 'won' : actual === line ? 'void' : 'lost';
  }
  // Quarter lines (x.25 or x.75): split bet
  const lower = Math.floor(line * 2) / 2;   // e.g. 2.25 → 2.0
  const upper = lower + 0.5;                 // e.g. 2.25 → 2.5
  const resLower = _resolveAsian(actual, lower, direction);
  const resUpper = _resolveAsian(actual, upper, direction);
  if (resLower === 'won'  && resUpper === 'won')  return 'won';
  if (resLower === 'lost' && resUpper === 'lost') return 'lost';
  if (resLower === 'void' && resUpper === 'void') return 'void';
  // Half-win: one won, one void
  if ((resLower === 'won' && resUpper === 'void') ||
      (resLower === 'void' && resUpper === 'won')) return 'halfwon';
  // Half-loss: one lost, one void
  if ((resLower === 'lost' && resUpper === 'void') ||
      (resLower === 'void' && resUpper === 'lost')) return 'halflost';
  // Win + Loss = push effectively
  return 'void';
}

// ── Legacy import ─────────────────────────────────────────────────────────────
function importLegacyPicks() {
  fetch('http://localhost:3001/picks_history')
    .catch(() => fetch('https://blummabet.github.io/Betting-Dashboard/picks_history.json'))
    .then(r => r.ok ? r.json() : Promise.reject())
    .then(legacy => {
      if (!Array.isArray(legacy)) return;
      // Filter out duplicates / bad leagues
      const BAD_LEAGUES = new Set(['NED2', 'AUT2']);
      const store = _v2Load();
      const idx   = new Set(store.map(e => _v2Id(e)));
      let added   = 0;

      for (const e of legacy) {
        if (BAD_LEAGUES.has(e.league)) continue;
        const picks = (e.picks || []).filter(p => p.conf !== 'low');
        if (!picks.length) continue;

        const dateIso = e.dateIso || _toIso(e.date || '');
        const id = `${dateIso}-${e.league}-${e.home}-${e.away}`;
        if (idx.has(id)) continue;

        store.push({
          id,
          date:       e.date || '',
          dateIso,
          league:     e.league,
          leagueName: e.leagueName || e.league,
          leagueFlag: e.leagueFlag || '',
          home:       e.home,
          away:       e.away,
          matchScore: e.matchScore || 0,
          source:     'legacy',
          savedAt:    e.savedAt || dateIso,
          picks: picks.map(p => ({
            market:    p.market || '',
            marketKey: _mKey(p.market || ''),
            icon:      p.icon || '',
            conf:      p.conf || 'medium',
            sc:        p.sc || 0,
            odds:      p.odds != null ? p.odds : null,
            modelOdds: p.modelOdds != null ? p.modelOdds : null,
            value:     p.value || null,
            oddsIsEst: p.oddsIsEst || false,
            result:    p.result === 'win' ? 'won' : p.result === 'loss' ? 'lost' : p.result || null,
            resolvedAt:p.result ? (dateIso + 'T23:59:00Z') : null,
          })),
        });
        idx.add(id);
        added++;
      }

      _v2Save(store);
      _v2Toast(`✅ ${added} Spiele aus Legacy importiert`);
      _renderV2Tab();
    })
    .catch(() => _v2Toast('❌ Legacy-Daten nicht erreichbar'));
}

// ── Tab rendering ─────────────────────────────────────────────────────────────
let _v2Filters = { league: 'all', market: 'all', source: 'all', days: '90' };

function initResultsV2() {
  const panel = document.getElementById('trackingV2Panel');
  if (!panel) return;

  // If localStorage is empty AND we have live match data → auto-save now
  const existing = _v2Load();
  if (!existing.length && window._v2LastMatchList?.length) {
    try { savePicksV2(window._v2LastMatchList); } catch(e) {}
  }

  _renderV2Tab();
  // Auto-resolve silently on tab open
  autoResolveV2(true).then(n => { if (n > 0) _renderV2Tab(); });
}

function _renderV2Tab() {
  const panel = document.getElementById('trackingV2Panel');
  if (!panel) return;

  const all = _v2Load();
  const filtered = _applyFilters(all);
  const allPicks = filtered.flatMap(e => e.picks.map(p => ({...p, _entry: e})));

  // Empty state with action buttons
  if (!all.length) {
    const hasLive = window._v2LastMatchList?.length > 0;
    panel.innerHTML = `
      <div style="max-width:520px;margin:60px auto;text-align:center;padding:0 20px">
        <div style="font-size:48px;margin-bottom:16px">📈</div>
        <div style="font-size:18px;font-weight:700;margin-bottom:8px">Tracking V2 — noch keine Daten</div>
        <div style="font-size:13px;color:var(--muted);line-height:1.7;margin-bottom:24px">
          Picks werden automatisch gespeichert wenn die Cards geladen werden.<br>
          ${hasLive
            ? 'Live-Daten sind bereit — klick zum Laden:'
            : 'Gehe zuerst auf <strong>⭐ Best of All</strong> damit die Cards rendern, dann komm hier zurück.'}
        </div>
        <div style="display:flex;flex-direction:column;gap:10px;align-items:center">
          ${hasLive ? `
          <button onclick="savePicksV2(window._v2LastMatchList);_renderV2Tab()"
            style="background:var(--accent);color:#000;border:none;border-radius:8px;padding:10px 24px;font-size:13px;font-weight:700;cursor:pointer">
            📡 Picks aus Live-Daten laden (${window._v2LastMatchList.length} Spiele)
          </button>` : ''}
          <button onclick="importLegacyPicks();_renderV2Tab()"
            style="background:var(--card2);color:var(--text);border:1px solid var(--border);border-radius:8px;padding:10px 24px;font-size:13px;font-weight:600;cursor:pointer">
            📂 Historische Daten importieren (picks_history.json)
          </button>
        </div>
      </div>`;
    return;
  }

  panel.innerHTML = `
    <div style="padding:16px 0">
      ${_kpiHtml(allPicks)}
      ${_breakdownHtml(filtered)}
      ${_filtersHtml(all)}
      ${_tableHtml(filtered)}
      ${_actionsHtml(all)}
    </div>
  `;
}

// ── Analytics Breakdown: Match Score + Konfidenz + CLV ───────────────────────
function _breakdownHtml(entries) {
  const allPicks = entries.flatMap(e => e.picks.map(p => ({...p, _sc: e.matchScore || 0})));
  if (!allPicks.length) return '';

  // helper: win/loss/open + winRate from a pick subset
  function _stats(picks) {
    const w = picks.filter(p => p.result === 'won' || p.result === 'halfwon').length;
    const l = picks.filter(p => p.result === 'lost' || p.result === 'halflost').length;
    const o = picks.filter(p => !p.result).length;
    const res = picks.filter(p => p.result && p.result !== 'void');
    const wr = res.length >= 3 ? Math.round(w / res.length * 100) : null;
    return { w, l, o, wr, res: res.length };
  }

  // ── 1. Match Score Breakdown ─────────────────────────────────────────────
  const scoreBrackets = [
    { label: '9/12',  min: 9,  max: 9.9  },
    { label: '10/12', min: 10, max: 10.9 },
    { label: '11/12', min: 11, max: 11.9 },
    { label: '12/12', min: 12, max: 12   },
  ];
  const scoreRows = scoreBrackets.map(b => {
    const picks = allPicks.filter(p => p._sc >= b.min && p._sc <= b.max);
    if (!picks.length) return null;
    const s = _stats(picks);
    const wrCol = s.wr == null ? '#8b949e' : s.wr >= 60 ? '#3fb950' : s.wr >= 45 ? '#f0c040' : '#f85149';
    return `<tr>
      <td style="font-weight:700;color:var(--accent)">${b.label}</td>
      <td style="color:#3fb950">✅ ${s.w}</td>
      <td style="color:#f85149">❌ ${s.l}</td>
      <td style="color:#8b949e">⏳ ${s.o}</td>
      <td style="font-weight:800;color:${wrCol}">${s.wr != null ? s.wr + '%' : '—'}</td>
    </tr>`;
  }).filter(Boolean).join('');

  // ── 2. Konfidenz Breakdown ───────────────────────────────────────────────
  const confGroups = [
    { label: '★★★', key: 'high'   },
    { label: '★★☆', key: 'medium' },
    { label: '★☆☆', key: 'low'    },
  ];
  const confRows = confGroups.map(g => {
    const picks = allPicks.filter(p => p.conf === g.key);
    if (!picks.length) return null;
    const s = _stats(picks);
    const wrCol = s.wr == null ? '#8b949e' : s.wr >= 60 ? '#3fb950' : s.wr >= 45 ? '#f0c040' : '#f85149';
    return `<tr>
      <td style="font-weight:700;color:var(--yellow)">${g.label}</td>
      <td style="color:#3fb950">✅ ${s.w}</td>
      <td style="color:#f85149">❌ ${s.l}</td>
      <td style="color:#8b949e">⏳ ${s.o}</td>
      <td style="font-weight:800;color:${wrCol}">${s.wr != null ? s.wr + '%' : '—'}</td>
    </tr>`;
  }).filter(Boolean).join('');

  // ── 3. CLV Split ─────────────────────────────────────────────────────────
  const withOdds    = allPicks.filter(p => p.odds && !p.oddsIsEst);
  const withoutOdds = allPicks.filter(p => !p.odds || p.oddsIsEst);
  const sWO  = _stats(withOdds);
  const sWOO = _stats(withoutOdds);

  const _mkTable = (title, rows) => `
    <div style="background:var(--card2);border:1px solid var(--border);border-radius:10px;padding:14px 16px">
      <div style="font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.6px;font-weight:700;margin-bottom:10px">${title}</div>
      <table style="width:100%;border-collapse:collapse;font-size:12px">
        <thead><tr style="color:var(--muted);font-size:10px">
          <th style="text-align:left;padding-bottom:6px">Gruppe</th>
          <th style="padding-bottom:6px">Gew.</th>
          <th style="padding-bottom:6px">Verl.</th>
          <th style="padding-bottom:6px">Offen</th>
          <th style="padding-bottom:6px">Win%</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;

  const clvWrCol  = sWO.wr  == null ? '#8b949e' : sWO.wr  >= 55 ? '#3fb950' : '#f0c040';
  const clvWrCol2 = sWOO.wr == null ? '#8b949e' : sWOO.wr >= 55 ? '#3fb950' : '#f0c040';
  const clvHtml = `
    <div style="background:var(--card2);border:1px solid var(--border);border-radius:10px;padding:14px 16px">
      <div style="font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.6px;font-weight:700;margin-bottom:12px">📈 CLV — Closing Line Value</div>
      <div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:10px">
        <div style="flex:1;min-width:100px;text-align:center">
          <div style="font-size:22px;font-weight:800;color:${clvWrCol}">${sWO.wr != null ? sWO.wr + '%' : '—'}</div>
          <div style="font-size:11px;color:var(--muted);margin-top:3px">Win Rate<br><span style="color:var(--accent)">mit Bookie-Quote</span></div>
        </div>
        <div style="width:1px;background:var(--border)"></div>
        <div style="flex:1;min-width:100px;text-align:center">
          <div style="font-size:22px;font-weight:800;color:${clvWrCol2}">${sWOO.wr != null ? sWOO.wr + '%' : '—'}</div>
          <div style="font-size:11px;color:var(--muted);margin-top:3px">Win Rate<br><span style="color:var(--muted)">keine Quote</span></div>
        </div>
      </div>
      <div style="font-size:10px;color:#484f58;padding:6px 8px;background:rgba(0,0,0,.2);border-radius:5px;line-height:1.5">
        ℹ️ CLV-Tracking aktiv sobald Opening-Odds erfasst sind. Picks mit Bookie-Quote zeigen Marktvalidierung — höhere Win Rate = Modell erkennt echten Edge.
      </div>
    </div>`;

  return `
    <div style="margin-bottom:20px">
      <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.8px;color:var(--muted);margin-bottom:10px;display:flex;align-items:center;gap:8px">
        Analytics
        <span style="flex:1;height:1px;background:var(--border)"></span>
      </div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px">
        ${scoreRows ? _mkTable('📊 Match Score Breakdown', scoreRows) : ''}
        ${confRows  ? _mkTable('⭐ Konfidenz Breakdown', confRows)    : ''}
        ${clvHtml}
      </div>
    </div>`;
}

function _applyFilters(entries) {
  const { league, market, source, days } = _v2Filters;
  const cutoff = days === 'all' ? null : new Date(Date.now() - parseInt(days) * 86400000);

  return entries.filter(e => {
    if (league !== 'all' && e.league !== league) return false;
    if (source !== 'all' && e.source !== source) return false;
    if (cutoff) {
      const d = new Date(e.dateIso || e.date);
      if (d < cutoff) return false;
    }
    if (market !== 'all') {
      const cats = _marketCat(market);
      if (!e.picks.some(p => cats.includes(_mKey(p.market)))) return false;
    }
    return true;
  });
}

function _kpiHtml(picks) {
  const resolved   = picks.filter(p => p.result && p.result !== 'void' && p.result !== 'halfwon' && p.result !== 'halflost');
  const won        = picks.filter(p => p.result === 'won' || p.result === 'halfwon').length;
  const lost       = picks.filter(p => p.result === 'lost' || p.result === 'halflost').length;
  const open       = picks.filter(p => !p.result).length;
  const winRate    = resolved.length ? Math.round(won / resolved.length * 100) : null;

  // P&L calculation
  let pnl = 0, staked = 0;
  for (const p of picks) {
    if (!p.result || !p.odds) continue;
    const stake = 5; // flat €5
    staked += stake;
    if (p.result === 'won')      pnl += stake * (p.odds - 1);
    else if (p.result === 'lost')pnl -= stake;
    else if (p.result === 'halfwon')  pnl += stake * (p.odds - 1) / 2;
    else if (p.result === 'halflost') pnl -= stake / 2;
    // void: 0
  }
  const roi = staked > 0 ? Math.round(pnl / staked * 100) : null;

  const kpis = [
    { label: 'Total Picks', val: picks.length, sub: `${won}W · ${lost}L · ${open} offen`, color: 'var(--text)' },
    { label: 'Win Rate',    val: winRate != null ? `${winRate}%` : '—',
      sub: `${resolved.length} ausgewertet`,
      color: winRate == null ? 'var(--muted)' : winRate >= 55 ? '#3fb950' : winRate >= 45 ? '#f0c040' : '#f85149' },
    { label: 'Einsatz',     val: staked > 0 ? `€${staked.toFixed(0)}` : '—', sub: '@ €5 flat', color: 'var(--text)' },
    { label: 'P&L',         val: staked > 0 ? `€${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}` : '—',
      sub: roi != null ? `ROI ${roi > 0 ? '+' : ''}${roi}%` : 'ROI —',
      color: pnl > 0 ? '#3fb950' : pnl < 0 ? '#f85149' : 'var(--muted)' },
  ];

  return `
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:16px">
      ${kpis.map(k => `
        <div style="background:var(--card2);border:1px solid var(--border);border-radius:10px;padding:14px 16px">
          <div style="font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;font-weight:700;margin-bottom:6px">${k.label}</div>
          <div style="font-size:22px;font-weight:800;color:${k.color};line-height:1.1">${k.val}</div>
          <div style="font-size:11px;color:var(--muted);margin-top:4px">${k.sub}</div>
        </div>`).join('')}
    </div>`;
}

function _filtersHtml(all) {
  const leagues = [...new Set(all.map(e => e.league))].sort();
  const { league, market, source, days } = _v2Filters;

  const sel = (id, val, opts) => `
    <select id="v2f_${id}" onchange="_v2SetFilter('${id}', this.value)"
      style="background:var(--card2);border:1px solid var(--border);border-radius:6px;color:var(--text);padding:6px 10px;font-size:12px;cursor:pointer">
      ${opts.map(([v,l]) => `<option value="${v}" ${val===v?'selected':''}>${l}</option>`).join('')}
    </select>`;

  return `
    <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:14px">
      <span style="font-size:11px;color:var(--muted);font-weight:700">Filter:</span>
      ${sel('league', league, [['all','Alle Ligen'], ...leagues.map(l => [l, l])])}
      ${sel('market', market, [
        ['all','Alle Märkte'],['result','1X2'],['dc','Double Chance'],['goals','Tore O/U'],
        ['btts','BTTS'],['corners','Ecken'],['cards','Karten'],['ah','Asian HCP'],['ht','Halbzeit'],
      ])}
      ${sel('source', source, [['all','Alle Quellen'],['v2','Neu (V2)'],['legacy','Legacy']])}
      ${sel('days', days, [['7','7 Tage'],['14','14 Tage'],['30','30 Tage'],['90','90 Tage'],['all','Alle']])}
    </div>`;
}

function _v2SetFilter(key, val) {
  _v2Filters[key] = val;
  _renderV2Tab();
}

function _tableHtml(entries) {
  // Sort by date desc
  const sorted = [...entries].sort((a, b) => (b.dateIso || b.date).localeCompare(a.dateIso || a.date));

  if (!sorted.length) {
    return `<div style="text-align:center;padding:48px;color:var(--muted);font-size:14px">
      Keine Daten für diesen Filter.<br>
      <span style="font-size:12px">Öffne die Cards-Ansicht um Picks zu speichern.</span>
    </div>`;
  }

  const rows = sorted.flatMap(e => e.picks.map(p => {
    const res     = p.result;
    const resIcon = res === 'won'      ? '✅'
                  : res === 'lost'     ? '❌'
                  : res === 'void'     ? '〇'
                  : res === 'halfwon'  ? '½✅'
                  : res === 'halflost' ? '½❌'
                  : '⏳';
    const resCol  = res === 'won' || res === 'halfwon' ? '#3fb950'
                  : res === 'lost' || res === 'halflost' ? '#f85149'
                  : res === 'void' ? '#8b949e' : '#8b949e';
    const conf    = p.conf === 'high' ? '★★★' : '★★☆';
    const oddsStr = p.odds ? p.odds.toFixed(2) : (p.oddsIsEst ? '~est' : '—');
    const pnl     = _pickPnl(p);
    const pnlStr  = pnl != null ? `€${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}` : '—';
    const srcBadge = e.source === 'legacy'
      ? '<span style="font-size:9px;background:#2d2216;color:#f0c040;border-radius:3px;padding:1px 4px">legacy</span>'
      : '';

    return `<tr style="border-bottom:1px solid var(--border)">
      <td style="padding:7px 10px;font-size:11px;color:var(--muted);white-space:nowrap">${e.date} ${srcBadge}</td>
      <td style="padding:7px 10px;font-size:11px">${e.leagueFlag} ${e.league}</td>
      <td style="padding:7px 10px;font-size:12px;font-weight:600;white-space:nowrap">${e.home} vs ${e.away}</td>
      <td style="padding:7px 10px;font-size:12px;color:#a78bfa">${p.icon || ''} ${p.market}</td>
      <td style="padding:7px 10px;font-size:12px;font-weight:700;color:var(--green)">${oddsStr}</td>
      <td style="padding:7px 10px;font-size:11px;color:var(--muted)">${conf}</td>
      <td style="padding:7px 10px;font-size:14px;color:${resCol};font-weight:700;text-align:center">${resIcon}</td>
      <td style="padding:7px 10px;font-size:12px;font-weight:700;color:${pnl != null ? (pnl >= 0 ? '#3fb950' : '#f85149') : 'var(--muted)'}">${pnlStr}</td>
    </tr>`;
  })).join('');

  return `
    <div style="background:var(--card2);border:1px solid var(--border);border-radius:10px;overflow:hidden;margin-bottom:16px">
      <div style="overflow-x:auto">
        <table style="width:100%;border-collapse:collapse;min-width:600px">
          <thead style="background:var(--bg)">
            <tr>
              ${['Datum','Liga','Spiel','Markt','Kurs','Konf.','Erg.','P&L'].map(h =>
                `<th style="padding:8px 10px;text-align:left;font-size:9px;color:var(--muted);font-weight:700;text-transform:uppercase;letter-spacing:.5px;white-space:nowrap">${h}</th>`
              ).join('')}
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </div>`;
}

function _actionsHtml(all) {
  const hasLegacy = all.some(e => e.source === 'legacy');
  const total = all.length;
  const lastSaved = all.reduce((m, e) => e.savedAt > m ? e.savedAt : m, '');

  return `
    <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:8px">
      <button onclick="autoResolveV2().then(()=>_renderV2Tab())"
        style="background:none;border:1px solid #3fb95055;border-radius:6px;color:#3fb950;font-size:12px;font-weight:700;padding:7px 14px;cursor:pointer">
        🔄 Auto-auswerten
      </button>
      ${!hasLegacy ? `
      <button onclick="importLegacyPicks()"
        style="background:none;border:1px solid var(--border);border-radius:6px;color:var(--muted);font-size:12px;font-weight:700;padding:7px 14px;cursor:pointer">
        📥 Legacy importieren (ab 13. Apr)
      </button>` : ''}
      <button onclick="_v2Export()"
        style="background:none;border:1px solid var(--border);border-radius:6px;color:var(--muted);font-size:12px;font-weight:700;padding:7px 14px;cursor:pointer">
        💾 Export JSON
      </button>
      <button onclick="_v2ClearConfirm()"
        style="background:none;border:1px solid #f8514933;border-radius:6px;color:#f85149;font-size:12px;font-weight:700;padding:7px 14px;cursor:pointer">
        🗑️ Reset
      </button>
    </div>
    <div style="font-size:11px;color:var(--muted)">
      ${total} Spiele gespeichert · Zuletzt: ${lastSaved ? _timeAgo(lastSaved) : '—'}
    </div>`;
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function _v2Id(e) {
  return `${e.dateIso || _toIso(e.date || '')}-${e.league}-${e.home}-${e.away}`;
}

function _toIso(dateStr) {
  // "DD.MM.YYYY" → "YYYY-MM-DD"
  try { const [d,m,y] = dateStr.split('.'); return `${y}-${m.padStart(2,'0')}-${d.padStart(2,'0')}`; }
  catch { return dateStr || ''; }
}

function _normPair(h, a) {
  const n = s => (s||'').toLowerCase().replace(/[^a-z0-9]/g,' ').replace(/\s+/g,' ').trim();
  return `${n(h)}|${n(a)}`;
}

function _dateClose(iso1, iso2) {
  if (!iso1 || !iso2) return false;
  return Math.abs(new Date(iso1) - new Date(iso2)) < 86400000 * 2; // 2 day tolerance
}

function _pickPnl(p) {
  if (!p.result || !p.odds) return null;
  const stake = 5;
  if (p.result === 'won')      return +(stake * (p.odds - 1)).toFixed(2);
  if (p.result === 'lost')     return -stake;
  if (p.result === 'halfwon')  return +(stake * (p.odds - 1) / 2).toFixed(2);
  if (p.result === 'halflost') return -(stake / 2);
  return 0; // void
}

function _mKey(market) {
  const m = (market||'').trim(); const ml = m.toLowerCase();
  if (ml === 'heimsieg')                      return 'homeWin';
  if (ml === 'auswärtssieg')                  return 'awayWin';
  if (ml === 'unentschieden')                 return 'draw';
  if (/doppelte chance.*1x/i.test(ml))        return 'dc1X';
  if (/doppelte chance.*x2/i.test(ml))        return 'dcX2';
  if (/doppelte chance.*12/i.test(ml))        return 'dc12';
  if (/beide teams treffen: nein/i.test(ml))  return 'noBtts';
  if (/beide teams treffen/i.test(ml))        return 'btts';
  if (/ecken/i.test(ml))  { const n=m.match(/(\d+\.?\d*)/); return n?`corners:${n[1]}`:'corners'; }
  if (/karten/i.test(ml)) { const n=m.match(/(\d+\.?\d*)/); return n?`cards:${n[1]}`:'cards'; }
  if (/1\.\s*hz/i.test(ml))                  return 'ht';
  if (/^over|^über|^under|^unter/i.test(ml)) return 'goals';
  if (/^ah\s/i.test(ml) || /^handicap/i.test(ml)) return 'ah';
  return ml.replace(/[^a-z0-9]+/g,'_').replace(/^_|_$/g,'') || 'other';
}

function _marketCat(cat) {
  const MAP = {
    result:  ['homeWin','awayWin','draw'],
    dc:      ['dc1X','dcX2','dc12'],
    btts:    ['btts','noBtts'],
    goals:   ['goals','over25','under25','over225','over2'],
    corners: ['corners'],
    cards:   ['cards'],
    ah:      ['ah'],
    ht:      ['ht'],
  };
  return MAP[cat] || [];
}

function _marketCatMatch(marketKey, cat) {
  if (cat === 'all') return true;
  const cats = _marketCat(cat);
  return cats.some(c => marketKey.startsWith(c));
}

function _v2Export() {
  const data = _v2Load();
  const blob = new Blob([JSON.stringify(data, null, 2)], {type:'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `betedge_picks_v2_${new Date().toISOString().slice(0,10)}.json`;
  a.click();
}

function _v2ClearConfirm() {
  if (confirm('Alle V2 Tracking-Daten löschen? Dies kann nicht rückgängig gemacht werden.')) {
    localStorage.removeItem(V2_KEY);
    _renderV2Tab();
    _v2Toast('🗑️ Tracking-Daten gelöscht');
  }
}

function _v2Toast(msg) {
  const t = document.createElement('div');
  t.textContent = msg;
  Object.assign(t.style, {
    position:'fixed', bottom:'80px', right:'20px', zIndex:'9999',
    background:'#1c2128', border:'1px solid #30363d', borderRadius:'8px',
    padding:'10px 16px', color:'#e6edf3', fontSize:'13px', fontWeight:'600',
    boxShadow:'0 4px 16px rgba(0,0,0,.5)',
  });
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3000);
}

function _timeAgo(isoStr) {
  if (!isoStr) return '—';
  const m = Math.floor((Date.now() - new Date(isoStr)) / 60000);
  if (m < 2)  return 'gerade eben';
  if (m < 60) return `vor ${m} Min`;
  const h = Math.floor(m / 60);
  if (h < 24) return `vor ${h} Std`;
  return `vor ${Math.floor(h/24)} Tagen`;
}
