#!/usr/bin/env node
// ═══════════════════════════════════════════════════════════════════════════
//  Betting Dashboard — Pre-Match Data Server
//  Läuft lokal, holt Daten von api-football (kein CORS-Problem)
//  und stellt sie dem Dashboard auf localhost:3001 zur Verfügung.
//
//  Start:    node prematch-server.js
//  Dashboard: http://localhost:3001
//
//  API-Quota-Schätzung pro Lauf (~9 Ligen, ~8 Tage):
//    • Fixtures/Date:   8 Calls
//    • Injuries:        ~80 Calls (1 pro Spiel)
//    • H2H:             ~80 Calls (1 pro Paar)
//    • Referee Stats:   ~50 Calls (5 pro Schiri, ~10 Schiris)
//    • Odds:            ~80 Calls (1 pro Spiel)
//    Gesamt: ~300 Calls · Pro Plan: 7500/Tag → kein Problem
// ═══════════════════════════════════════════════════════════════════════════

const http  = require('http');
const https = require('https');
const fs    = require('fs');
const path  = require('path');

// ── Modi ─────────────────────────────────────────────────────────────────────
//   node prematch-server.js          → lokaler HTTP-Server (Development)
//   node prematch-server.js --write  → JSON-Datei schreiben (GitHub Actions)
const WRITE_MODE = process.argv.includes('--write');

// ── Config ──────────────────────────────────────────────────────────────────
// API Key: zuerst Environment Variable (GitHub Secret), dann Fallback für lokalen Dev
const API_KEY   = process.env.APISPORTS_KEY || '9f36726c1bdc9957b4a49f89277b80db';
const API_HOST  = 'v3.football.api-sports.io';

// Nur diese Ligen fetchen — verhindert 7000+ Spiele pro Tag weltweit
// api-football League IDs: https://www.api-football.com/documentation-v3#tag/Leagues
const LEAGUE_IDS = {
  39:  'Premier League',
  78:  'Bundesliga',
  135: 'Serie A',
  140: 'La Liga',
  61:  'Ligue 1',
  218: 'Austrian Bundesliga',
  88:  'Eredivisie',
  94:  'Primeira Liga',
  179: 'Scottish Premiership',
  203: 'Süper Lig',
  // Neue Ligen (Saison-Ende April/Mai)
  144: 'Jupiler Pro League',
  106: 'Ekstraklasa',
  271: 'NB I',
  210: 'HNL',
};
const PORT      = 3001;
const CACHE_TTL = 6 * 3600 * 1000;  // 6 Stunden
const BATCH_DELAY = 600;             // ms zwischen Batches (Pro Plan: ~300req/min safe margin)
const CALL_DELAY  = 200;             // ms zwischen einzelnen Calls

// ── In-Memory Cache ──────────────────────────────────────────────────────────
let _cache = { ts: 0, data: null, fetching: false };

// ── API Helper ───────────────────────────────────────────────────────────────
function apiFetch(urlPath) {
  return new Promise((resolve, reject) => {
    const options = {
      hostname: API_HOST,
      path:     urlPath,
      method:   'GET',
      headers:  { 'x-apisports-key': API_KEY }
    };
    const req = https.request(options, res => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => {
        try { resolve(JSON.parse(body)); }
        catch(e) { reject(new Error(`JSON parse error for ${urlPath}: ${e.message}`)); }
      });
    });
    req.on('error', reject);
    req.setTimeout(15000, () => { req.destroy(); reject(new Error(`Timeout: ${urlPath}`)); });
    req.end();
  });
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// ── Date helper ──────────────────────────────────────────────────────────────
function localIso(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

// ── Fuzzy team name matching (mirrors HTML's _fuzzyTeam) ────────────────────
function norm(s) {
  return (s || '').toLowerCase()
    // Umlaut normalization: ö→o, ü→u, ä→a, etc. so "Köln" matches "Koln"
    .replace(/[àáâãäå]/g,'a').replace(/[èéêë]/g,'e').replace(/[ìíîï]/g,'i')
    .replace(/[òóôõöø]/g,'o').replace(/[ùúûü]/g,'u').replace(/[ýÿ]/g,'y')
    .replace(/[ñ]/g,'n').replace(/[ç]/g,'c').replace(/[ß]/g,'ss')
    .replace(/[şș]/g,'s').replace(/[ğ]/g,'g').replace(/[ı]/g,'i')
    .replace(/\bfc\b|\bafc\b|\bcf\b|\bsc\b|\bsv\b|\bac\b|\bbc\b|\bfk\b|\bsk\b/g, '')
    .replace(/[^a-z0-9]/g, '');
}
function fuzzy(apiName, localName) {
  const a = norm(apiName), b = norm(localName);
  if (!a || !b) return false;
  if (a === b) return true;
  if (a.length >= 4 && b.length >= 4) {
    if (a.includes(b) || b.includes(a)) return true;
    if (a.slice(0, 5) === b.slice(0, 5)) return true;
  }
  return false;
}

// ── Squad position cache (7-day TTL, persisted to squad-cache.json) ─────────
const SQUAD_CACHE_FILE = path.join(__dirname, 'squad-cache.json');
const SQUAD_TTL = 7 * 24 * 3600 * 1000;
// Load persisted cache from disk (survives GitHub Actions runs)
let _squadCache = {};
try {
  const _raw = fs.readFileSync(SQUAD_CACHE_FILE, 'utf8');
  _squadCache = JSON.parse(_raw);
  const _alive = Object.keys(_squadCache).filter(id => Date.now() - (_squadCache[id]?.ts||0) < SQUAD_TTL).length;
  console.log(`[Squad] Cache geladen: ${Object.keys(_squadCache).length} Teams (${_alive} noch gültig)`);
} catch(e) { /* first run — cache file doesn't exist yet */ }

async function fetchSquadPositions(teamId) {
  if (!teamId) return {};
  const cached = _squadCache[teamId];
  if (cached && Date.now() - cached.ts < SQUAD_TTL) return cached.data;
  try {
    const data = await apiFetch(`/players/squads?team=${teamId}`);
    const players = (data.response || [])[0]?.players || [];
    const posMap = {};
    for (const p of players) {
      const pos = p.position || '';
      const code = pos.startsWith('Goal') ? 'G'
                 : pos.startsWith('Def')  ? 'D'
                 : pos.startsWith('Mid')  ? 'M'
                 : pos.startsWith('For')  ? 'F'
                 : 'M';  // default midfield
      // Store by normalized name (lowercase, trim)
      posMap[(p.name || '').toLowerCase().trim()] = code;
      if (p.id) posMap[`id_${p.id}`] = code;
    }
    _squadCache[teamId] = { ts: Date.now(), data: posMap };
    return posMap;
  } catch(e) { return {}; }
}
function _saveSquadCache() {
  try { fs.writeFileSync(SQUAD_CACHE_FILE, JSON.stringify(_squadCache)); }
  catch(e) { console.warn('[Squad] Cache speichern fehlgeschlagen:', e.message); }
}

// ── Compute injury impact score (0–6 scale) ──────────────────────────────────
function computeInjuryImpact(inj) {
  // Weights per position: based on how replaceable each role is
  let sc = 0;
  sc += (inj.goalkeeper || 0) * 1.1;          // GK: hardest to replace truly
  sc += Math.min(inj.attack || 0, 4) * 0.95;  // each striker directly reduces xG
  if ((inj.attack || 0) >= 3) sc += 0.7;      // compound: no real striker crisis
  sc += Math.min(inj.defense || 0, 4) * 0.60; // each CB/fullback: leaky defence
  if ((inj.defense || 0) >= 3) sc += 0.5;     // compound: exposed backline
  sc += Math.min(inj.midfield || 0, 5) * 0.30;// midfielders: less critical individually
  sc += (inj.goalkeeper || 0) >= 2 ? 1.0 : 0; // 2nd GK missing = crisis
  sc += (inj.questionable || 0) * 0.25;        // questionable at half-weight
  return Math.min(6.0, Math.round(sc * 10) / 10);
}

// ── Parse bookmakers array → odds object (same format as HTML) ───────────────
// Accepts full bookmakers array; Pinnacle takes priority for 1X2/Goals.
// Merges BTTS, Double Chance, and Cards from any available bookmaker.
// Computes consensus fair value (hw_fair/dr_fair/aw_fair) from all bookmakers:
//   Pinnacle (margin <2.5%) gets 2× weight, others 1×.
//   Averaging multiple de-vigged sources cancels individual bookmaker biases.
// Case-insensitive matching — mirrors browser _parseOddsBets logic.
function parseBets(bookmakers) {
  if (!Array.isArray(bookmakers) || !bookmakers.length) return {};
  const r = {};
  const sorted = [...bookmakers].sort((a, b) => {
    const aP = (a.name?.toLowerCase().includes('pinnacle') || a.id === 8) ? 0 : 1;
    const bP = (b.name?.toLowerCase().includes('pinnacle') || b.id === 8) ? 0 : 1;
    return aP - bP;
  });

  // ── Pass 1: collect consensus 1X2 data from all bookmakers ──────────────────
  const _cSamples = [];
  for (const bkr of bookmakers) {
    let _hw = null, _dr = null, _aw = null;
    for (const bet of (bkr.bets || [])) {
      const bn = (bet.name || '').toLowerCase().trim();
      if (bn === 'match winner' || bn === '1x2' || bn === 'result' || bn === 'fulltime result' || bn === 'winner' || bn === 'match result') {
        for (const v of (bet.values || [])) {
          const vl = (v.value || '').toLowerCase();
          if (vl === 'home') _hw = parseFloat(v.odd);
          else if (vl === 'away') _aw = parseFloat(v.odd);
          else if (vl === 'draw') _dr = parseFloat(v.odd);
        }
        break;
      }
    }
    if (!_hw || !_dr || !_aw || isNaN(_hw) || isNaN(_dr) || isNaN(_aw)) continue;
    const _tot = 1/_hw + 1/_dr + 1/_aw;
    const _margin = _tot - 1;
    if (_margin > 0.15 || _margin < -0.02) continue; // skip corrupt/exchange outliers
    const _isPinn = bkr.name?.toLowerCase().includes('pinnacle') || bkr.id === 8;
    _cSamples.push({
      ph: (1/_hw) / _tot, pd: (1/_dr) / _tot, pa: (1/_aw) / _tot,
      weight: _isPinn ? 2.0 : 1.0,  // Pinnacle: 2× weight (sharper, no bias)
      name: bkr.name || `id${bkr.id}`
    });
  }
  if (_cSamples.length >= 1) {
    const _tw  = _cSamples.reduce((s, d) => s + d.weight, 0);
    const _ph  = _cSamples.reduce((s, d) => s + d.ph * d.weight, 0) / _tw;
    const _pd  = _cSamples.reduce((s, d) => s + d.pd * d.weight, 0) / _tw;
    const _pa  = _cSamples.reduce((s, d) => s + d.pa * d.weight, 0) / _tw;
    const _n   = _ph + _pd + _pa;  // normalize floating point
    const _r2  = (x) => Math.round(x * 100) / 100;
    r.hw_fair  = _r2(_n / _ph);    // true fair odds = 1/prob, no margin
    r.dr_fair  = _r2(_n / _pd);
    r.aw_fair  = _r2(_n / _pa);
    r._cn      = _cSamples.length; // how many books contributed
  }

  // ── Pass 2: primary markets (Pinnacle-first for actual betting odds) ─────────
  for (const bkr of sorted) {
    for (const bet of (bkr.bets || [])) {
      const bn = (bet.name || '').toLowerCase().trim();
      if (bn === 'match winner' || bn === '1x2' || bn === 'result' || bn === 'fulltime result' || bn === 'winner' || bn === 'match result') {
        for (const v of (bet.values || [])) {
          const vl = (v.value || '').toLowerCase();
          if      (vl === 'home' && !r.hw) r.hw = parseFloat(v.odd);
          else if (vl === 'away' && !r.aw) r.aw = parseFloat(v.odd);
          else if (vl === 'draw' && !r.dr) r.dr = parseFloat(v.odd);
        }
      } else if (bn === 'goals over/under' || bn === 'total goals' || bn === 'over/under' || bn === 'total - goals' || bn.includes('goals o/u') || (bn.includes('over') && bn.includes('under') && bn.includes('goal'))) {
        for (const v of (bet.values || [])) {
          const vl = (v.value || '').toLowerCase();
          if      (vl === 'over 2.5'  && !r.o25) r.o25 = parseFloat(v.odd);
          else if (vl === 'under 2.5' && !r.u25) r.u25 = parseFloat(v.odd);
          else if (vl === 'over 3.5'  && !r.o35) r.o35 = parseFloat(v.odd);
          else if (vl === 'under 3.5' && !r.u35) r.u35 = parseFloat(v.odd);
          else if (vl === 'over 1.5'  && !r.o15) r.o15 = parseFloat(v.odd);
        }
      } else if (bn.includes('both teams') || bn === 'btts' || bn === 'gg/ng') {
        for (const v of (bet.values || [])) {
          const vl = (v.value || '').toLowerCase();
          if      ((vl === 'yes' || vl === 'gg') && !r.bttsY) r.bttsY = parseFloat(v.odd);
          else if ((vl === 'no'  || vl === 'ng') && !r.bttsN) r.bttsN = parseFloat(v.odd);
        }
      } else if (bn === 'double chance' || bn.includes('double chance')) {
        for (const v of (bet.values || [])) {
          const vl = (v.value || '').toLowerCase();
          if      ((vl === 'home/draw' || vl === '1x' || vl === 'home or draw') && !r.dc1X_bkr) r.dc1X_bkr = parseFloat(v.odd);
          else if ((vl === 'draw/away' || vl === 'x2' || vl === 'draw or away') && !r.dcX2_bkr) r.dcX2_bkr = parseFloat(v.odd);
        }
      } else if (bn === 'asian handicap' || bn === 'draw no bet' || bn === 'dnb') {
        for (const v of (bet.values || [])) {
          const vl = (v.value || '').toLowerCase();
          if      (vl === 'home' && !r.dnbH) r.dnbH = parseFloat(v.odd);
          else if (vl === 'away' && !r.dnbA) r.dnbA = parseFloat(v.odd);
        }
      } else if (bn === 'total - corners' || bn === 'corners' || bn === 'corner kicks' || bn.includes('total corners') || (bn.includes('corner') && (bn.includes('over') || bn.includes('under') || bn.includes('total')))) {
        for (const v of (bet.values || [])) {
          const vl = (v.value || '').toLowerCase();
          if      (vl === 'over 9.5'  && !r.co95)  r.co95  = parseFloat(v.odd);
          else if (vl === 'under 9.5' && !r.cu95)  r.cu95  = parseFloat(v.odd);
          else if (vl === 'over 8.5'  && !r.co85)  r.co85  = parseFloat(v.odd);
          else if (vl === 'under 8.5' && !r.cu85)  r.cu85  = parseFloat(v.odd);
          else if (vl === 'over 10.5' && !r.co105) r.co105 = parseFloat(v.odd);
          else if (vl === 'under 10.5'&& !r.cu105) r.cu105 = parseFloat(v.odd);
          else if (vl === 'over 11.5' && !r.co115) r.co115 = parseFloat(v.odd);
        }
      } else if (bn.includes('card') || bn.includes('booking') || bn === 'total - cards') {
        for (const v of (bet.values || [])) {
          const vl = (v.value || '').toLowerCase();
          if      (vl === 'over 3.5'  && !r.cards_o35) r.cards_o35 = parseFloat(v.odd);
          else if (vl === 'under 3.5' && !r.cards_u35) r.cards_u35 = parseFloat(v.odd);
          else if (vl === 'over 4.5'  && !r.cards_o45) r.cards_o45 = parseFloat(v.odd);
          else if (vl === 'under 4.5' && !r.cards_u45) r.cards_u45 = parseFloat(v.odd);
          else if (vl === 'over 5.5'  && !r.cards_o55) r.cards_o55 = parseFloat(v.odd);
        }
      }
    }
  }
  return r;
}

// ── FINISHED STATUS ──────────────────────────────────────────────────────────
const FINISHED = new Set(['FT','AET','PEN','AWD','WO','CANC','ABD']);

// ════════════════════════════════════════════════════════════════════════════
//  MAIN FETCH FUNCTION
// ════════════════════════════════════════════════════════════════════════════
async function fetchAllPrematchData() {
  // ── Account quota check ──────────────────────────────────────────────────
  try {
    const _st = await apiFetch('/status');
    const _sub = (_st.response || {}).subscription || {};
    const _req = (_st.response || {}).requests || {};
    console.log(`[Server] API-Account: Plan="${_sub.plan||'?'}" | Heute: ${_req.current??'?'}/${_req.limit_day??'?'} Requests | Verbleibend: ${(_req.limit_day??0)-(_req.current??0)}`);
    if (_st.errors && Object.keys(_st.errors).length) {
      console.warn(`[Server] API-Status Fehler:`, JSON.stringify(_st.errors));
    }
  } catch(e) { console.warn('[Server] API-Status nicht abrufbar:', e.message); }

  const today = new Date();
  const dates = [];
  for (let i = -1; i <= 7; i++) {
    dates.push(localIso(new Date(today.getFullYear(), today.getMonth(), today.getDate() + i)));
  }

  const dateFrom = dates[0];
  const dateTo   = dates[dates.length - 1];
  console.log(`\n[Server] Fetching ${Object.keys(LEAGUE_IDS).length} Ligen von ${dateFrom} bis ${dateTo}`);

  // ── Step 1: Fixtures pro Liga mit Datumsbereich (statt alle Spiele weltweit) ─
  // Pro Liga 1 API-Call statt pro Datum alle Ligen → ~9 Calls statt 7000+ Spiele
  const fixtureMap = {};
  for (const [leagueId, leagueName] of Object.entries(LEAGUE_IDS)) {
    try {
      const data = await apiFetch(
        `/fixtures?league=${leagueId}&season=2025&from=${dateFrom}&to=${dateTo}&timezone=Europe%2FVienna`
      );
      const fxs = data.response || [];
      console.log(`  [Step1] ${leagueName} (${leagueId}): ${fxs.length} Spiele`);
      for (const fx of fxs) {
        const id = fx.fixture?.id;
        if (!id) continue;
        // Datum + Uhrzeit aus API-Antwort extrahieren
        const fxRaw    = fx.fixture?.date || '';
        const fxDate   = fxRaw.slice(0, 10);
        const fxTime   = fxRaw.length >= 16 ? fxRaw.slice(11, 16) : null; // "HH:MM" local time
        const fxStatus = fx.fixture?.status?.short || 'NS';
        fixtureMap[id] = {
          fixtureId:    id,
          homeTeamName: fx.teams?.home?.name || '',
          awayTeamName: fx.teams?.away?.name || '',
          homeTeamId:   fx.teams?.home?.id   || null,
          awayTeamId:   fx.teams?.away?.id   || null,
          referee:      fx.fixture?.referee  || null,
          refereeStats: null,
          date:         fxDate,
          time:         fxTime,
          injuries:     { home: [], away: [] },
          injurySummary: { home: null, away: null },
          h2h:          null,
          isFinished:    FINISHED.has(fxStatus),
          odds:          null,
          apiPrediction: null
        };
      }
      await sleep(CALL_DELAY);
    } catch(e) {
      console.warn(`  [Step1] Liga ${leagueId} Fehler:`, e.message);
    }
  }

  const fixtures = Object.values(fixtureMap);
  console.log(`[Server] Step1 fertig: ${fixtures.length} Spiele total`);
  if (!fixtures.length) return [];

  // ── Step 1.5: Squad positions for all teams (7-day disk cache) ──────────────
  // Cache persists across runs — only fetch teams whose data is expired/missing.
  // Batched 5-at-a-time with 800ms delay to avoid rate-limit bursts.
  const uniqueTeamIds = [...new Set(
    fixtures.flatMap(d => [d.homeTeamId, d.awayTeamId].filter(Boolean))
  )];
  const staleTeams = uniqueTeamIds.filter(id => {
    const c = _squadCache[id];
    return !c || Date.now() - c.ts >= SQUAD_TTL;
  });
  console.log(`[Server] Step1.5: ${staleTeams.length} Teams brauchen Squad-Fetch (${uniqueTeamIds.length - staleTeams.length} gecacht)`);
  for (let i = 0; i < staleTeams.length; i += 5) {
    await Promise.allSettled(staleTeams.slice(i, i + 5).map(id => fetchSquadPositions(id)));
    if (i + 5 < staleTeams.length) await sleep(800);
  }
  if (staleTeams.length) _saveSquadCache();
  console.log(`  Step1.5 fertig: ${uniqueTeamIds.length} Teams gesamt, ${staleTeams.length} neu geladen`);

  // ── Step 2: Injuries with position data (parallel batches of 10) ────────────
  console.log(`[Server] Step2: Verletzungen für ${fixtures.length} Spiele...`);
  let injOk = 0;
  for (let i = 0; i < fixtures.length; i += 10) {
    const batch = fixtures.slice(i, i + 10);
    await Promise.allSettled(batch.map(async d => {
      try {
        const data = await apiFetch(`/injuries?fixture=${d.fixtureId}`);
        const injuries = data.response || [];
        const seen = new Set();
        const homePosMap = _squadCache[d.homeTeamId]?.data || {};
        const awayPosMap = _squadCache[d.awayTeamId]?.data || {};

        for (const inj of injuries) {
          const pName = inj.player?.name || '?';
          if (seen.has(pName)) continue;
          seen.add(pName);
          const injType = inj.player?.type || 'Injured';  // "Missing Fixture" | "Questionable"
          const isHome = fuzzy(inj.team?.name || '', d.homeTeamName);
          const posMap = isHome ? homePosMap : awayPosMap;
          // Look up position: try by ID first, then normalized name
          const pId = inj.player?.id;
          const pPos = (pId && posMap[`id_${pId}`])
            || posMap[(pName).toLowerCase().trim()]
            || 'M';  // default midfield if unknown
          const entry = {
            player:   pName,
            position: pPos,          // 'G' | 'D' | 'M' | 'F'
            type:     injType,       // 'Missing Fixture' | 'Questionable'
            reason:   inj.player?.reason || null
          };
          if (isHome) d.injuries.home.push(entry);
          else        d.injuries.away.push(entry);
        }

        // Compute structured injury summary for each side
        const _buildInjSummary = (list) => {
          const confirmed   = list.filter(i => i.type === 'Missing Fixture');
          const questionable = list.filter(i => i.type !== 'Missing Fixture');
          const count = (arr, pos) => arr.filter(i => i.position === pos).length;
          const inj = {
            goalkeeper:   count(confirmed, 'G'),
            defense:      count(confirmed, 'D'),
            midfield:     count(confirmed, 'M'),
            attack:       count(confirmed, 'F'),
            confirmed:    confirmed.length,
            questionable: questionable.length,
            total:        list.length,
            notes:        list.map(i =>
              `${i.player} (${i.type === 'Missing Fixture' ? 'Gesperrt/Verletzt' : 'Fraglich'}${i.reason ? ' — ' + i.reason : ''})`
            ),
            _raw: list
          };
          inj.impactScore = computeInjuryImpact(inj);
          return inj;
        };

        d.injurySummary = {
          home: _buildInjSummary(d.injuries.home),
          away: _buildInjSummary(d.injuries.away)
        };

        if (injuries.length) injOk++;
      } catch(e) {}
    }));
    if (i + 10 < fixtures.length) await sleep(BATCH_DELAY);
  }
  console.log(`  Step2 fertig: ${injOk} Spiele mit Verletzungsdaten (inkl. Positionen)`);

  // ── Step 3: H2H (parallel batches of 10) ─────────────────────────────────
  const h2hable = fixtures.filter(d => d.homeTeamId && d.awayTeamId);
  console.log(`[Server] Step3: H2H für ${h2hable.length} Paarungen...`);
  let h2hOk = 0;
  let _firstH2hErr = null;
  for (let i = 0; i < h2hable.length; i += 10) {
    const batch = h2hable.slice(i, i + 10);
    await Promise.allSettled(batch.map(async d => {
      try {
        const data = await apiFetch(`/fixtures/headtohead?h2h=${d.homeTeamId}-${d.awayTeamId}&last=10`);
        if (data.errors && Object.keys(data.errors).length && !_firstH2hErr) {
          _firstH2hErr = { type: 'api_error', errors: data.errors, h2h: `${d.homeTeamId}-${d.awayTeamId}` };
          console.warn(`  [H2H] API-Error:`, JSON.stringify(data.errors));
        }
        const fxs = data.response || [];
        if (!fxs.length) {
          if (!_firstH2hErr) _firstH2hErr = { type: 'empty', results: data.results, h2h: `${d.homeTeamId}-${d.awayTeamId}` };
          return;
        }
        let totalGoals = 0, over25 = 0, over35 = 0, btts = 0, homeWins = 0, draws = 0, awayWins = 0;
        let lastYear = null;
        const lastResults = [];
        for (const f of fxs) {
          const hg = f.goals?.home ?? 0, ag = f.goals?.away ?? 0;
          totalGoals += hg + ag;
          if (hg + ag > 2.5) over25++;
          if (hg + ag > 3.5) over35++;
          if (hg > 0 && ag > 0) btts++;
          const isHome = f.teams?.home?.id === d.homeTeamId;
          if (isHome ? hg > ag : ag > hg) homeWins++;
          else if (hg === ag) draws++;
          else awayWins++;
          const yr = new Date(f.fixture?.date || '').getFullYear();
          if (!isNaN(yr) && (!lastYear || yr > lastYear)) lastYear = yr;
          lastResults.push(isHome ? (hg > ag ? 'W' : hg === ag ? 'D' : 'L') : (ag > hg ? 'W' : hg === ag ? 'D' : 'L'));
        }
        const n = fxs.length;
        d.h2h = {
          games:        n,
          homeWins,
          draws,
          awayWins,
          lastMeetingYear: lastYear,
          avgGoals:     Math.round(totalGoals / n * 10) / 10,
          over25Rate:   Math.round(over25 / n * 100) / 100,
          over35Rate:   Math.round(over35 / n * 100) / 100,
          bttsRate:     Math.round(btts   / n * 100) / 100,
          lastResults:  lastResults.slice(0, 5)
        };
        h2hOk++;
      } catch(e) {
        if (!_firstH2hErr) _firstH2hErr = { type: 'exception', message: e.message, h2h: `${d.homeTeamId}-${d.awayTeamId}` };
      }
    }));
    if (i + 10 < h2hable.length) await sleep(BATCH_DELAY);
  }
  if (_firstH2hErr) console.warn(`  [H2H] Erstes Problem:`, JSON.stringify(_firstH2hErr));
  console.log(`  Step3 fertig: ${h2hOk} Paarungen mit H2H`);

  // ── Step 4: Referee stats — ÜBERSPRUNGEN in GitHub Actions ──────────────
  // Schiri-Stats brauchen pro Schiri 3+ sequentielle API-Calls (zu langsam für CI).
  // Sie werden stattdessen im Browser via _enrichMissingData geladen (48h Cache).
  // Die referee-Namen sind im JSON enthalten → Browser kann sie direkt nachladen.
  const uniqueRefs = [...new Set(fixtures.map(d => d.referee).filter(Boolean))];
  console.log(`[Server] Step4: ${uniqueRefs.length} Schiris in JSON (Stats werden im Browser geladen)`);
  // refereeStats bleibt null — Browser füllt sie via refStats_v5 Cache

  // ── Step 5: Odds (upcoming games only) ───────────────────────────────────
  // No bookmaker filter — fetch all bookmakers, parseBets() merges BTTS/DC/Cards from any.
  const upcoming = fixtures.filter(d => !d.isFinished && d.fixtureId);
  console.log(`[Server] Step5: Quoten für ${upcoming.length} bevorstehende Spiele (alle Bookmaker)...`);
  let oddsOk = 0, oddsFail = 0;
  let _firstOddsErr = null;  // capture first error/empty for diagnostics

  for (const d of upcoming) {
    await sleep(1200);
    try {
      const data = await apiFetch(`/odds?fixture=${d.fixtureId}`);
      // Capture API-level errors (plan restriction, quota, etc.)
      if (data.errors && Object.keys(data.errors).length && !_firstOddsErr) {
        _firstOddsErr = { type: 'api_error', errors: data.errors, fixture: d.fixtureId };
        console.warn(`  [Odds] API-Error für Fixture ${d.fixtureId}:`, JSON.stringify(data.errors));
      }
      const bookmakers = (data.response || [])[0]?.bookmakers || [];
      if (bookmakers.length) {
        // Log bookmaker/bet names for first successful fetch (once)
        if (oddsOk === 0) {
          const bkrNames = bookmakers.map(b => b.name).join(', ');
          const betNames = [...new Set(bookmakers.flatMap(b => (b.bets||[]).map(bt => bt.name)))].join(', ');
          console.log(`  [Odds] Sample bkrs: ${bkrNames}`);
          console.log(`  [Odds] Sample bets: ${betNames}`);
        }
        const r = parseBets(bookmakers);
        if (Object.keys(r).length) { d.odds = r; oddsOk++; }
        else { oddsFail++; }
      } else {
        // No bookmakers in response — log once for diagnostics
        if (!_firstOddsErr) {
          _firstOddsErr = { type: 'no_bookmakers', results: data.results, fixture: d.fixtureId };
          console.warn(`  [Odds] Keine Bookmaker für Fixture ${d.fixtureId}: results=${data.results}, errors=${JSON.stringify(data.errors||{})}`);
        }
        oddsFail++;
      }
    } catch(e) {
      if (!_firstOddsErr) _firstOddsErr = { type: 'exception', message: e.message, fixture: d.fixtureId };
      oddsFail++;
    }
  }
  if (_firstOddsErr) console.warn(`  [Odds] Erstes Problem:`, JSON.stringify(_firstOddsErr));
  console.log(`  Step5 fertig: ${oddsOk} OK · ${oddsFail} leer/Fehler (von ${upcoming.length} Spielen)`);

  // ── Step 5b: Late-fetch cards odds for fixtures ≤48h away ────────────────
  // Card markets open later than 1X2/O2.5 — only worth re-fetching close to kickoff.
  // Only targets fixtures that already have main odds (BTTS/DC present) but no cards.
  const _d0 = new Date().toISOString().slice(0, 10);
  const _d1 = new Date(Date.now() + 24 * 3600 * 1000).toISOString().slice(0, 10);
  const _d2 = new Date(Date.now() + 48 * 3600 * 1000).toISOString().slice(0, 10);
  const needCards = upcoming.filter(d =>
    d.odds &&                                               // main odds exist (Step 5 succeeded)
    !d.odds.cards_o35 && !d.odds.cards_o45 &&              // cards still missing
    (d.date === _d0 || d.date === _d1 || d.date === _d2)   // kickoff within ~48h
  );
  if (needCards.length) {
    console.log(`[Server] Step5b: Karten-Quoten Late-Fetch für ${needCards.length} Spiele ≤48h...`);
    let cardsOk = 0;
    for (const d of needCards) {
      await sleep(1200);
      try {
        const data = await apiFetch(`/odds?fixture=${d.fixtureId}`);
        const bookmakers = (data.response || [])[0]?.bookmakers || [];
        if (bookmakers.length) {
          const r = parseBets(bookmakers);
          // Merge only card fields — don't overwrite existing 1X2/BTTS/DC/Goals odds
          if (r.cards_o35 || r.cards_o45) {
            if (r.cards_o35)  d.odds.cards_o35  = r.cards_o35;
            if (r.cards_u35)  d.odds.cards_u35  = r.cards_u35;
            if (r.cards_o45)  d.odds.cards_o45  = r.cards_o45;
            if (r.cards_u45)  d.odds.cards_u45  = r.cards_u45;
            if (r.cards_o55)  d.odds.cards_o55  = r.cards_o55;
            cardsOk++;
            console.log(`  [Step5b] ✅ ${d.homeTeamName} vs ${d.awayTeamName}: cards o35=${r.cards_o35||'-'} o45=${r.cards_o45||'-'}`);
          }
        }
      } catch(e) { /* silent — cards are bonus data, never block the run */ }
    }
    console.log(`  Step5b fertig: ${cardsOk}/${needCards.length} Spiele mit Karten-Quoten gefunden`);
  }

  // ── Step 5.5: API Predictions ─────────────────────────────────────────────
  // /predictions returns the API-Football model's expected goals, result percentages
  // and Poisson-distribution win/draw/loss probabilities — used as independent signal.
  console.log(`[Server] Step5.5: Predictions für ${upcoming.length} Spiele...`);
  let predOk = 0;
  for (const d of upcoming) {
    await sleep(1200);
    try {
      const data = await apiFetch(`/predictions?fixture=${d.fixtureId}`);
      const pred = (data.response || [])[0];
      if (pred) {
        const p  = pred.predictions || {};
        const cp = pred.comparison  || {};
        // Percent fields come as "70%" strings — parse to int
        const _pct = (s) => { const n = parseInt(s); return isNaN(n) ? null : n; };
        // Helper: extract {home, away} int pair from comparison sub-object
        const _comp = (key) => {
          const h = parseInt(cp[key]?.home); const a = parseInt(cp[key]?.away);
          return (!isNaN(h) && !isNaN(a)) ? { home: h, away: a } : null;
        };
        d.apiPrediction = {
          goalsHome:   parseFloat(p.goals?.home)               || null,  // e.g. 1.8
          goalsAway:   parseFloat(p.goals?.away)               || null,  // e.g. 1.2
          underOver:   p.under_over                            || null,  // "Over 2.5" | "Under 2.5"
          pctHome:     _pct(p.percent?.home),  // 0–100 (percentage string without %)
          pctDraw:     _pct(p.percent?.draw),
          pctAway:     _pct(p.percent?.away),
          // Poisson distribution — API's own model result probabilities (0–100)
          poissonHome: _pct(cp.poisson_distribution?.home),
          poissonDraw: _pct(cp.poisson_distribution?.draws),
          poissonAway: _pct(cp.poisson_distribution?.away),
          // Comparison signals (0–100 each side, higher = better)
          compForm:    _comp('form'),    // recent form score
          compAtt:     _comp('att'),     // attack strength
          compDef:     _comp('def'),     // defensive strength
          compGoals:   _comp('goals'),   // goals comparison
        };
        predOk++;
      }
    } catch(e) {
      // Silently skip — predictions are optional enrichment
    }
  }
  console.log(`  Step5.5 fertig: ${predOk} Predictions geladen (von ${upcoming.length} Spielen)`);

  const refNote = uniqueRefs.length ? `, ${uniqueRefs.length} Schiri-Namen (Stats im Browser)` : '';
  console.log(`\n[Server] ✅ Fertig: ${fixtures.length} Spiele, ${h2hOk} H2H, ${injOk} Verletzungen${refNote}, ${oddsOk} Quoten, ${predOk} Predictions\n`);
  return fixtures;
}

// ════════════════════════════════════════════════════════════════════════════
//  HTTP SERVER
// ════════════════════════════════════════════════════════════════════════════
const server = http.createServer(async (req, res) => {
  // CORS headers (allows the HTML at file:// or localhost to call us)
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Headers', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');

  if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }

  const url = req.url.split('?')[0];

  // ── GET /prematch — main data endpoint ────────────────────────────────────
  if (url === '/prematch') {
    const forceRefresh = req.url.includes('refresh=1');

    // If already fetching, wait up to 60s
    if (_cache.fetching) {
      let waited = 0;
      while (_cache.fetching && waited < 60000) {
        await sleep(500); waited += 500;
      }
    }

    // Serve cache if fresh
    if (!forceRefresh && _cache.data && Date.now() - _cache.ts < CACHE_TTL) {
      console.log(`[Server] Cache-Hit: ${_cache.data.length} Spiele (Alter: ${Math.round((Date.now()-_cache.ts)/60000)}min)`);
      res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
      res.end(JSON.stringify({ ts: _cache.ts, fixtures: _cache.data }));
      return;
    }

    // Fetch fresh data
    _cache.fetching = true;
    try {
      _cache.data = await fetchAllPrematchData();
      _cache.ts   = Date.now();
      res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
      res.end(JSON.stringify({ ts: _cache.ts, fixtures: _cache.data }));
    } catch(e) {
      console.error('[Server] Fetch-Fehler:', e.message);
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: e.message }));
    } finally {
      _cache.fetching = false;
    }
    return;
  }

  // ── GET /status — quota check ─────────────────────────────────────────────
  if (url === '/status') {
    try {
      const data = await apiFetch('/status');
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(data));
    } catch(e) {
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: e.message }));
    }
    return;
  }

  // ── GET / or /season-finish.html — serve the dashboard ───────────────────
  if (url === '/' || url === '/season-finish.html') {
    const htmlPath = path.join(__dirname, 'season-finish.html');
    if (fs.existsSync(htmlPath)) {
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      fs.createReadStream(htmlPath).pipe(res);
    } else {
      res.writeHead(404); res.end('season-finish.html nicht gefunden');
    }
    return;
  }

  res.writeHead(404); res.end('Not found');
});

// ════════════════════════════════════════════════════════════════════════════
//  ENTRY POINT — je nach Modus HTTP-Server oder JSON-Datei schreiben
// ════════════════════════════════════════════════════════════════════════════
if (WRITE_MODE) {
  // GitHub Actions Modus: Daten holen, prematch-data.json schreiben, exit
  console.log('[GitHub Actions] Starte Daten-Fetch für prematch-data.json...');
  fetchAllPrematchData()
    .then(fixtures => {
      const outPath = path.join(__dirname, 'prematch-data.json');
      const output  = JSON.stringify({ ts: Date.now(), fixtures }, null, 2);
      fs.writeFileSync(outPath, output, 'utf8');
      const kb = Math.round(Buffer.byteLength(output) / 1024);
      console.log(`\n✅ prematch-data.json geschrieben: ${fixtures.length} Spiele (${kb} KB)`);
      process.exit(0);
    })
    .catch(e => {
      console.error('\n❌ Fehler:', e.message);
      process.exit(1);
    });
} else {
  // Lokaler Server Modus
  server.listen(PORT, '127.0.0.1', () => {
    console.log('');
    console.log('╔═══════════════════════════════════════════════════════╗');
    console.log('║         Betting Dashboard — Pre-Match Server           ║');
    console.log('╠═══════════════════════════════════════════════════════╣');
    console.log(`║  Dashboard:  http://localhost:${PORT}                   ║`);
    console.log(`║  API-Daten:  http://localhost:${PORT}/prematch           ║`);
    console.log(`║  Refresh:    http://localhost:${PORT}/prematch?refresh=1 ║`);
    console.log(`║  Quota:      http://localhost:${PORT}/status             ║`);
    console.log('╠═══════════════════════════════════════════════════════╣');
    console.log('║  Strg+C zum Beenden                                    ║');
    console.log('╚═══════════════════════════════════════════════════════╝');
    console.log('');
    console.log('[Server] Starte initialen Daten-Load im Hintergrund...');

    fetchAllPrematchData()
      .then(data => {
        _cache = { ts: Date.now(), data, fetching: false };
        console.log(`[Server] ✅ ${data.length} Spiele geladen und gecacht (6h TTL)`);
      })
      .catch(e => {
        _cache.fetching = false;
        console.error('[Server] ❌ Initialer Load fehlgeschlagen:', e.message);
      });
  });
}

server.on('error', e => {
  if (e.code === 'EADDRINUSE') {
    console.error(`\n❌ Port ${PORT} ist bereits belegt. Server läuft vielleicht schon?\n`);
  } else {
    console.error('\n❌ Server-Fehler:', e.message, '\n');
  }
  process.exit(1);
});
