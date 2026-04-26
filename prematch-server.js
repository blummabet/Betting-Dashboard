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
// API-Football key (injuries, H2H, referee stats, fixtures, bookings)
const API_KEY   = process.env.APISPORTS_KEY || '9f36726c1bdc9957b4a49f89277b80db';
const API_HOST  = 'v3.football.api-sports.io';
// The Odds API key (all pre-match odds incl. same-day — replaces API-Football /odds)
const ODDS_API_KEY  = process.env.ODDS_API_KEY || 'e33cee8d4ce8d646476115c7d1e3f3e4';
const ODDS_API_HOST = 'api.the-odds-api.com';

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
  207: 'Super League (Switzerland)',
};

// The Odds API sport keys — one call per key fetches ALL upcoming fixtures for that league.
// Far more efficient than API-Football (15 calls vs 136 per run) + covers same-day games.
const LEAGUE_ODDS_KEYS = {
  39:  'soccer_epl',
  78:  'soccer_germany_bundesliga',
  135: 'soccer_italy_serie_a',
  140: 'soccer_spain_la_liga',
  61:  'soccer_france_ligue_one',
  218: 'soccer_austria_bundesliga',
  88:  'soccer_netherlands_eredivisie',
  94:  'soccer_portugal_primeira_liga',
  203: 'soccer_turkey_super_league',
  106: 'soccer_poland_ekstraklasa',
  179: 'soccer_scotland_premiership',    // SCO — added; server has safe error handling if 404
  144: 'soccer_belgium_first_div_a',     // BEL Jupiler Pro League
  207: 'soccer_switzerland_superleague', // SUI Super League
  // 271 (HUN), 210 (CRO): not covered by The Odds API — no bookmaker odds available.
  // Fair Value for these leagues is derived from API prediction percentages (_isEstimated:true).
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

// ── The Odds API helper ──────────────────────────────────────────────────────
// Fetches ALL upcoming odds for a given sport in one call.
// Regions: eu,uk — UK bookmakers (Bet365, W.Hill etc.) are essential for SCO/BEL/SUI
// which have limited EU bookie coverage. EU-only returned empty arrays for those leagues.
// Returns { data: [...events], remaining: '19950' }
function oddsApiFetch(sportKey) {
  return new Promise((resolve, reject) => {
    const path = `/v4/sports/${sportKey}/odds/?apiKey=${ODDS_API_KEY}`
      + `&regions=eu,uk&markets=h2h,spreads,totals&oddsFormat=decimal`;
    const options = { hostname: ODDS_API_HOST, path, method: 'GET',
      headers: { 'User-Agent': 'CocoBet/1.0' } };
    const req = https.request(options, res => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => {
        try {
          const data = JSON.parse(body);
          const remaining = res.headers['x-requests-remaining'] || null;
          resolve({ data, remaining });
        } catch(e) { reject(new Error(`JSON parse: ${e.message}`)); }
      });
    });
    req.on('error', reject);
    req.setTimeout(15000, () => { req.destroy(); reject(new Error(`Timeout: ${sportKey}`)); });
    req.end();
  });
}

// Fetch alternate soccer markets (corners + cards + Asian lines + double chance).
// Uses regions=eu,uk — EU for spreads/DC, UK for corners/cards (Bet365, W.Hill etc.).
// EU-only returns 0 corner quotes; UK bookmakers have full alternate_totals_corners coverage.
// Returns { data: [...events] } or { data: [] } on error.
function oddsApiFetchAlt(sportKey) {
  return new Promise((resolve) => {
    const path = `/v4/sports/${sportKey}/odds/?apiKey=${ODDS_API_KEY}`
      + `&regions=eu,uk&markets=alternate_totals_corners,alternate_totals_cards,alternate_totals,alternate_spreads,double_chance&oddsFormat=decimal`;
    const options = { hostname: ODDS_API_HOST, path, method: 'GET',
      headers: { 'User-Agent': 'CocoBet/1.0' } };
    const req = https.request(options, res => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => {
        try {
          if (res.statusCode !== 200) { resolve({ data: [] }); return; }
          const data = JSON.parse(body);
          resolve({ data: Array.isArray(data) ? data : [] });
        } catch(e) { resolve({ data: [] }); }
      });
    });
    req.on('error', () => resolve({ data: [] }));
    req.setTimeout(15000, () => { req.destroy(); resolve({ data: [] }); });
    req.end();
  });
}

// Fetch 1st-half markets via eu,uk regions (h2h_h1 = HT 1X2, totals_h1 = HT over/under).
// UK region (Bet365, W.Hill) is required for Eredivisie, Scottish, Belgian etc. — EU-only misses them.
// Returns array of events, or [] on any error/non-200.
function oddsApiFetchHT(sportKey) {
  return new Promise((resolve) => {
    const path = `/v4/sports/${sportKey}/odds/?apiKey=${ODDS_API_KEY}`
      + `&regions=eu,uk&markets=h2h_h1,totals_h1&oddsFormat=decimal`;
    const options = { hostname: ODDS_API_HOST, path, method: 'GET',
      headers: { 'User-Agent': 'CocoBet/1.0' } };
    const req = https.request(options, res => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => {
        try {
          if (res.statusCode !== 200) { resolve([]); return; }
          const data = JSON.parse(body);
          resolve(Array.isArray(data) ? data : []);
        } catch(e) { resolve([]); }
      });
    });
    req.on('error', () => resolve([]));
    req.setTimeout(15000, () => { req.destroy(); resolve([]); });
    req.end();
  });
}

// Fetch 1st-half BTTS via UK region (btts_h1 not available in EU — follows same pattern as btts).
// Returns array of events, or [] on any error/non-200.
function oddsApiFetchHTBtts(sportKey) {
  return new Promise((resolve) => {
    const path = `/v4/sports/${sportKey}/odds/?apiKey=${ODDS_API_KEY}`
      + `&regions=uk&markets=btts_h1&oddsFormat=decimal`;
    const options = { hostname: ODDS_API_HOST, path, method: 'GET',
      headers: { 'User-Agent': 'CocoBet/1.0' } };
    const req = https.request(options, res => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => {
        try {
          if (res.statusCode !== 200) { resolve([]); return; }
          const data = JSON.parse(body);
          resolve(Array.isArray(data) ? data : []);
        } catch(e) { resolve([]); }
      });
    });
    req.on('error', () => resolve([]));
    req.setTimeout(15000, () => { req.destroy(); resolve([]); });
    req.end();
  });
}

// Fetch BTTS market via UK region (btts is not available in EU region — causes 422).
// Returns array of events with btts bookmakers, or [] on any error/404.
function oddsApiFetchBtts(sportKey) {
  return new Promise((resolve) => {
    const path = `/v4/sports/${sportKey}/odds/?apiKey=${ODDS_API_KEY}`
      + `&regions=uk&markets=btts&oddsFormat=decimal`;
    const options = { hostname: ODDS_API_HOST, path, method: 'GET',
      headers: { 'User-Agent': 'CocoBet/1.0' } };
    const req = https.request(options, res => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => {
        try {
          if (res.statusCode !== 200) { resolve([]); return; }
          const data = JSON.parse(body);
          resolve(Array.isArray(data) ? data : []);
        } catch(e) { resolve([]); }
      });
    });
    req.on('error', () => resolve([]));
    req.setTimeout(15000, () => { req.destroy(); resolve([]); });
    req.end();
  });
}

// Normalize team names for fuzzy matching across APIs (API-Football vs The Odds API)
// Examples: "Inter" ↔ "Inter Milan", "HNK Hajduk Split" ↔ "Hajduk Split"
function normTeam(n) {
  return (n || '').toLowerCase()
    .replace(/[àáâãäå]/g, 'a').replace(/[èéêë]/g, 'e').replace(/[ìíîï]/g, 'i')
    .replace(/[òóôõöø]/g, 'o').replace(/[ùúûü]/g, 'u').replace(/[ß]/g, 'ss')
    .replace(/\b(fc|sv|sc|ac|ss|rc|sk|bsc|rb|vfb|vfl|1\.fc|tsv|spvgg|as|us|cd|cf|hnk|nk|gks|rsca|rsc)\b/g, ' ')
    .replace(/[^a-z0-9 ]/g, ' ').replace(/\s+/g, ' ').trim();
}

// Find the matching Odds API event for a fixture by team names + date
function matchOddsEvent(fixtureHome, fixtureAway, fixtureDate, oddsEvents) {
  const hN = normTeam(fixtureHome), aN = normTeam(fixtureAway);
  for (const e of oddsEvents) {
    // compare YYYY-MM-DD (UTC) — Odds API uses ISO8601 commence_time
    const eDate = (e.commence_time || '').slice(0, 10);
    if (eDate !== fixtureDate) continue;
    const ehN = normTeam(e.home_team), eaN = normTeam(e.away_team);
    // Bidirectional contains-check + word-level match (handles "Inter" ↔ "Inter Milan")
    const homeOk = ehN.includes(hN) || hN.includes(ehN)
                 || hN.split(' ').some(w => w.length > 3 && ehN.includes(w));
    const awayOk = eaN.includes(aN) || aN.includes(eaN)
                 || aN.split(' ').some(w => w.length > 3 && eaN.includes(w));
    if (homeOk && awayOk) return e;
  }
  return null;
}

// Parse a The Odds API event into the same odds object format as parseBets().
// Produces: hw, dr, aw, hw_fair, dr_fair, aw_fair, _cn, bttsY, bttsN,
//           o25, u25, o35, u35, o15, dc1X_bkr, dcX2_bkr, dc12_bkr,
//           ah_h, ah_h_point, ah_a, ah_a_point,
//           o25_fair, u25_fair, o25_cn (O/U 2.5 bookmaker consensus)
function parseTheOddsEvent(oddsEvent) {
  const r = {};
  const books = oddsEvent.bookmakers || [];
  if (!books.length) return r;
  const hTeam = normTeam(oddsEvent.home_team);
  const aTeam = normTeam(oddsEvent.away_team);
  // Pinnacle first for primary-market values
  const sorted = [...books].sort((a, b) => (a.key === 'pinnacle' ? 0 : 1) - (b.key === 'pinnacle' ? 0 : 1));

  // ── Pass 1: consensus fair 1X2 (Pinnacle 2×, others 1×) ───────────────────
  const _samples = [];
  for (const bkr of books) {
    const h2h = (bkr.markets || []).find(m => m.key === 'h2h');
    if (!h2h) continue;
    let hw = null, dr = null, aw = null;
    for (const o of (h2h.outcomes || [])) {
      const nm = normTeam(o.name);
      if (nm === hTeam || hTeam.includes(nm) || nm.includes(hTeam)) hw = o.price;
      else if (nm === aTeam || aTeam.includes(nm) || nm.includes(aTeam)) aw = o.price;
      else dr = o.price;
    }
    if (!hw || !dr || !aw || isNaN(hw) || isNaN(dr) || isNaN(aw)) continue;
    const tot = 1/hw + 1/dr + 1/aw, margin = tot - 1;
    if (margin > 0.15 || margin < -0.02) continue;
    _samples.push({ ph: (1/hw)/tot, pd: (1/dr)/tot, pa: (1/aw)/tot,
                    weight: bkr.key === 'pinnacle' ? 2.0 : 1.0 });
  }
  if (_samples.length) {
    const tw = _samples.reduce((s, d) => s + d.weight, 0);
    const ph = _samples.reduce((s, d) => s + d.ph * d.weight, 0) / tw;
    const pd = _samples.reduce((s, d) => s + d.pd * d.weight, 0) / tw;
    const pa = _samples.reduce((s, d) => s + d.pa * d.weight, 0) / tw;
    const n  = ph + pd + pa;
    const r2 = x => Math.round(x * 100) / 100;
    r.hw_fair  = r2(n / ph);
    r.dr_fair  = r2(n / pd);
    r.aw_fair  = r2(n / pa);
    r._cn      = _samples.length;
    // Derived DC from fair probs — used as fallback if real double_chance market unavailable
    r.dc1X_bkr = r2(1 / (ph + pd));
    r.dcX2_bkr = r2(1 / (pd + pa));
    r.dc12_bkr = r2(1 / (ph + pa));
  }

  // ── Pass 1b: consensus fair O/U 2.5 (same Pinnacle-2× weighting) ──────────
  const _ouSamples = [];
  for (const bkr of books) {
    const totMkt = (bkr.markets || []).find(m => m.key === 'totals');
    if (!totMkt) continue;
    let _o25 = null, _u25 = null;
    for (const o of (totMkt.outcomes || [])) {
      if (o.name === 'Over'  && Math.abs(o.point - 2.5) < 0.01) _o25 = o.price;
      else if (o.name === 'Under' && Math.abs(o.point - 2.5) < 0.01) _u25 = o.price;
    }
    if (!_o25 || !_u25 || isNaN(_o25) || isNaN(_u25)) continue;
    const _tot = 1/_o25 + 1/_u25, _margin = _tot - 1;
    if (_margin > 0.12 || _margin < -0.02) continue;
    _ouSamples.push({
      po: (1/_o25)/_tot, pu: (1/_u25)/_tot,
      weight: bkr.key === 'pinnacle' ? 2.0 : 1.0
    });
  }
  if (_ouSamples.length >= 1) {
    const _tw = _ouSamples.reduce((s, d) => s + d.weight, 0);
    const _po = _ouSamples.reduce((s, d) => s + d.po * d.weight, 0) / _tw;
    const _pu = _ouSamples.reduce((s, d) => s + d.pu * d.weight, 0) / _tw;
    const _n  = _po + _pu;
    const _r2 = x => Math.round(x * 100) / 100;
    r.o25_fair = _r2(_n / _po);
    r.u25_fair = _r2(_n / _pu);
    r.o25_cn   = _ouSamples.length;
  }

  // ── Pass 2: primary market values ─────────────────────────────────────────
  for (const bkr of sorted) {
    for (const mkt of (bkr.markets || [])) {
      const mk = mkt.key;
      if (mk === 'h2h') {
        for (const o of (mkt.outcomes || [])) {
          const nm = normTeam(o.name);
          if (!r.hw && (nm === hTeam || hTeam.includes(nm) || nm.includes(hTeam))) r.hw = o.price;
          else if (!r.aw && (nm === aTeam || aTeam.includes(nm) || nm.includes(aTeam))) r.aw = o.price;
          else if (!r.dr && o.price > 1.01) r.dr = o.price;
        }
      } else if (mk === 'totals') {
        for (const o of (mkt.outcomes || [])) {
          if      (o.name === 'Over'  && Math.abs(o.point - 2.5) < 0.01 && !r.o25) r.o25 = o.price;
          else if (o.name === 'Under' && Math.abs(o.point - 2.5) < 0.01 && !r.u25) r.u25 = o.price;
          else if (o.name === 'Over'  && Math.abs(o.point - 3.5) < 0.01 && !r.o35) r.o35 = o.price;
          else if (o.name === 'Under' && Math.abs(o.point - 3.5) < 0.01 && !r.u35) r.u35 = o.price;
          else if (o.name === 'Over'  && Math.abs(o.point - 1.5) < 0.01 && !r.o15) r.o15 = o.price;
          else if (o.name === 'Under' && Math.abs(o.point - 1.5) < 0.01 && !r.u15) r.u15 = o.price;
        }
      } else if (mk === 'btts') {
        for (const o of (mkt.outcomes || [])) {
          if      (o.name === 'Yes' && !r.bttsY) r.bttsY = o.price;
          else if (o.name === 'No'  && !r.bttsN) r.bttsN = o.price;
        }
      } else if (mk === 'spreads') {
        for (const o of (mkt.outcomes || [])) {
          const nm = normTeam(o.name);
          const isH = nm === hTeam || hTeam.includes(nm) || nm.includes(hTeam);
          if (isH) {
            if (!r.ah_h_point) { r.ah_h_point = o.point; r.ah_h = o.price; }
            // Collect ALL bookmaker spread lines → _pickBestLine can find closest-to-1.62
            if (!r.ah_home_lines) r.ah_home_lines = [];
            if (!r.ah_home_lines.find(l => Math.abs(l.pt - o.point) < 0.01)) r.ah_home_lines.push({ pt: o.point, price: o.price });
          } else {
            if (!r.ah_a_point) { r.ah_a_point = o.point; r.ah_a = o.price; }
            if (!r.ah_away_lines) r.ah_away_lines = [];
            if (!r.ah_away_lines.find(l => Math.abs(l.pt - o.point) < 0.01)) r.ah_away_lines.push({ pt: o.point, price: o.price });
          }
        }
      } else if (mk === 'alternate_totals_corners') {
        for (const o of (mkt.outcomes || [])) {
          const pt = o.point; const p = o.price;
          if (o.name === 'Over') {
            if (Math.abs(pt - 8.5)  < 0.01 && !r.co85)  r.co85  = p;
            else if (Math.abs(pt - 9.5)  < 0.01 && !r.co95)  r.co95  = p;
            else if (Math.abs(pt - 10.5) < 0.01 && !r.co105) r.co105 = p;
            else if (Math.abs(pt - 11.5) < 0.01 && !r.co115) r.co115 = p;
          } else if (o.name === 'Under') {
            if (Math.abs(pt - 8.5)  < 0.01 && !r.cu85)  r.cu85  = p;
            else if (Math.abs(pt - 9.5)  < 0.01 && !r.cu95)  r.cu95  = p;
            else if (Math.abs(pt - 10.5) < 0.01 && !r.cu105) r.cu105 = p;
            else if (Math.abs(pt - 11.5) < 0.01 && !r.cu115) r.cu115 = p;
          }
        }
      } else if (mk === 'alternate_totals_cards') {
        for (const o of (mkt.outcomes || [])) {
          const pt = o.point; const p = o.price;
          if (o.name === 'Over') {
            if (Math.abs(pt - 3.5) < 0.01 && !r.cards_o35) r.cards_o35 = p;
            else if (Math.abs(pt - 4.5) < 0.01 && !r.cards_o45) r.cards_o45 = p;
            else if (Math.abs(pt - 5.5) < 0.01 && !r.cards_o55) r.cards_o55 = p;
          } else if (o.name === 'Under') {
            if (Math.abs(pt - 3.5) < 0.01 && !r.cards_u35) r.cards_u35 = p;
            else if (Math.abs(pt - 4.5) < 0.01 && !r.cards_u45) r.cards_u45 = p;
          }
        }
      } else if (mk === 'double_chance') {
        // Real bookmaker DC quotes override derived values
        for (const o of (mkt.outcomes || [])) {
          const nm = (o.name || '').toLowerCase();
          if ((nm === '1x' || nm === 'home/draw') && o.price > 1.01) r.dc1X_bkr = o.price;
          else if ((nm === 'x2' || nm === 'draw/away') && o.price > 1.01) r.dcX2_bkr = o.price;
          else if ((nm === '12' || nm === 'home/away' || nm === '1 & 2') && o.price > 1.01) r.dc12_bkr = o.price;
        }
      } else if (mk === 'h2h_h1') {
        // 1st half 1X2 — halftime winner market
        for (const o of (mkt.outcomes || [])) {
          const nm = norm(o.name);
          if (!r.ht_hw && o.price > 1.01 && (nm === hTeam || hTeam.includes(nm) || nm.includes(hTeam))) r.ht_hw = o.price;
          else if (!r.ht_aw && o.price > 1.01 && (nm === aTeam || aTeam.includes(nm) || nm.includes(aTeam))) r.ht_aw = o.price;
          else if (!r.ht_dr && o.price > 1.01) r.ht_dr = o.price;
        }
      } else if (mk === 'totals_h1') {
        // 1st half over/under totals (0.5 and 1.5 lines)
        for (const o of (mkt.outcomes || [])) {
          if      (o.name === 'Over'  && Math.abs(o.point - 0.5) < 0.01 && !r.ht_o05) r.ht_o05 = o.price;
          else if (o.name === 'Under' && Math.abs(o.point - 0.5) < 0.01 && !r.ht_u05) r.ht_u05 = o.price;
          else if (o.name === 'Over'  && Math.abs(o.point - 1.5) < 0.01 && !r.ht_o15) r.ht_o15 = o.price;
          else if (o.name === 'Under' && Math.abs(o.point - 1.5) < 0.01 && !r.ht_u15) r.ht_u15 = o.price;
        }
      } else if (mk === 'btts_h1') {
        // Both teams to score in 1st half (UK bookmakers)
        for (const o of (mkt.outcomes || [])) {
          if (o.name === 'Yes' && !r.ht_bttsY) r.ht_bttsY = o.price;
          if (o.name === 'No'  && !r.ht_bttsN) r.ht_bttsN = o.price;
        }
      } else if (mk === 'alternate_totals') {
        // Asian Over/Under lines (quarter-ball: 1.75, 2.0, 2.25, 2.75, 3.25, etc.)
        // Collected as arrays sorted by pt — picker selects line closest to target odds (~1.62).
        // Also extracts standard lines (1.5, 2.5, 3.5) as fallback when main totals market omits them.
        // Many bookmakers (e.g. Unibet, Bet365) only list Under 1.5 in alternate_totals, not totals.
        for (const o of (mkt.outcomes || [])) {
          const pt = o.point; const p = o.price;
          if (pt < 1.0 || pt > 6.0) continue;
          if (o.name === 'Over') {
            if (!r.ao_lines) r.ao_lines = [];
            if (!r.ao_lines.find(l => Math.abs(l.pt - pt) < 0.01)) r.ao_lines.push({ pt, price: p });
            // Backfill standard keys if not yet set from totals market
            if (Math.abs(pt - 1.5) < 0.01 && !r.o15) r.o15 = p;
            if (Math.abs(pt - 2.5) < 0.01 && !r.o25) r.o25 = p;
            if (Math.abs(pt - 3.5) < 0.01 && !r.o35) r.o35 = p;
          } else if (o.name === 'Under') {
            if (!r.au_lines) r.au_lines = [];
            if (!r.au_lines.find(l => Math.abs(l.pt - pt) < 0.01)) r.au_lines.push({ pt, price: p });
            // Backfill standard keys if not yet set from totals market
            if (Math.abs(pt - 1.5) < 0.01 && !r.u15) r.u15 = p;
            if (Math.abs(pt - 2.5) < 0.01 && !r.u25) r.u25 = p;
            if (Math.abs(pt - 3.5) < 0.01 && !r.u35) r.u35 = p;
          }
        }
      } else if (mk === 'alternate_spreads') {
        // All available Asian Handicap lines per team — enables target-odds selection (~1.62)
        for (const o of (mkt.outcomes || [])) {
          const nm = normTeam(o.name);
          const pt = o.point; const p = o.price;
          if (nm === hTeam || hTeam.includes(nm) || nm.includes(hTeam)) {
            if (!r.ah_home_lines) r.ah_home_lines = [];
            if (!r.ah_home_lines.find(l => Math.abs(l.pt - pt) < 0.01)) r.ah_home_lines.push({ pt, price: p });
          } else if (nm === aTeam || aTeam.includes(nm) || nm.includes(aTeam)) {
            if (!r.ah_away_lines) r.ah_away_lines = [];
            if (!r.ah_away_lines.find(l => Math.abs(l.pt - pt) < 0.01)) r.ah_away_lines.push({ pt, price: p });
          }
        }
      }
    }
  }
  return r;
}

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

// ── Yellow card suspension thresholds per league ────────────────────────────
// Threshold = number of yellows that triggers 1-match ban in that competition
const YELLOW_THRESHOLDS = {
  39:  5,   // Premier League (5, 10, 15)
  78:  5,   // Bundesliga
  135: 5,   // Serie A
  140: 5,   // La Liga
  61:  5,   // Ligue 1
  218: 4,   // Austrian Bundesliga
  88:  5,   // Eredivisie
  94:  5,   // Primeira Liga
  179: 5,   // Scottish Premiership
  203: 5,   // Süper Lig
  144: 5,   // Jupiler Pro League
  106: 5,   // Ekstraklasa
  271: 5,   // NB I
  210: 4,   // HNL
};

// ── Bookings cache (24h TTL, persisted to bookings-cache.json) ──────────────
// Stores yellow card counts per player per team — refreshed daily
const BOOKINGS_CACHE_FILE = path.join(__dirname, 'bookings-cache.json');
const BOOKINGS_TTL = 24 * 3600 * 1000;
let _bookingsCache = {};
try {
  _bookingsCache = JSON.parse(fs.readFileSync(BOOKINGS_CACHE_FILE, 'utf8'));
  const _alive = Object.keys(_bookingsCache).filter(id => Date.now() - (_bookingsCache[id]?.ts||0) < BOOKINGS_TTL).length;
  console.log(`[Bookings] Cache geladen: ${Object.keys(_bookingsCache).length} Teams (${_alive} noch gültig)`);
} catch(e) { /* first run */ }

async function fetchTeamBookings(teamId) {
  if (!teamId) return [];
  const cached = _bookingsCache[teamId];
  if (cached && Date.now() - cached.ts < BOOKINGS_TTL) return cached.data;
  try {
    // Fetch page 1 (and page 2 if needed) of player stats for this team
    const data = await apiFetch(`/players?team=${teamId}&season=2025`);
    const total = data.paging?.total || 1;
    let entries = data.response || [];
    if (total >= 2) {
      await sleep(200);
      const data2 = await apiFetch(`/players?team=${teamId}&season=2025&page=2`);
      entries = entries.concat(data2.response || []);
    }
    const players = entries
      .map(e => ({
        id:      e.player?.id || null,
        name:    e.player?.name || '?',
        yellows: e.statistics?.[0]?.cards?.yellow || 0,
      }))
      .filter(p => p.yellows > 0);
    _bookingsCache[teamId] = { ts: Date.now(), data: players };
    return players;
  } catch(e) { return []; }
}
function _saveBookingsCache() {
  try { fs.writeFileSync(BOOKINGS_CACHE_FILE, JSON.stringify(_bookingsCache)); }
  catch(e) { console.warn('[Bookings] Cache speichern fehlgeschlagen:', e.message); }
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

// ── Referee cache (48h TTL, persisted to referee-cache.json) ────────────────
// Stores avgCards/avgYellow/games per referee name — refreshed every 48h.
// One API call per unique referee name (typically ~10–15 per run).
const REFEREE_CACHE_FILE = path.join(__dirname, 'referee-cache.json');
const REFEREE_TTL = 48 * 3600 * 1000;
let _refereeCache = {};
try {
  _refereeCache = JSON.parse(fs.readFileSync(REFEREE_CACHE_FILE, 'utf8'));
  const _alive = Object.keys(_refereeCache).filter(k => Date.now() - (_refereeCache[k]?.ts||0) < REFEREE_TTL).length;
  console.log(`[Referee] Cache geladen: ${Object.keys(_refereeCache).length} Schiris (${_alive} noch gültig)`);
} catch(e) { /* first run */ }

async function fetchRefereeStats(refName) {
  if (!refName) return null;
  const key = refName.toLowerCase().trim();
  const cached = _refereeCache[key];
  if (cached && Date.now() - cached.ts < REFEREE_TTL) return cached.data;

  try {
    const encodedName = encodeURIComponent(refName);
    const data = await apiFetch(`/referees?name=${encodedName}`);
    let refs = data.response || [];

    // Fallback: try last name only (handles abbreviated "M. Oliver" → "Oliver")
    if (!refs.length) {
      const parts = refName.trim().split(/\s+/);
      const lastName = parts[parts.length - 1];
      if (lastName && lastName.length > 3 && lastName !== refName) {
        await sleep(CALL_DELAY);
        const data2 = await apiFetch(`/referees?name=${encodeURIComponent(lastName)}`);
        refs = data2.response || [];
      }
    }

    if (!refs.length) {
      _refereeCache[key] = { ts: Date.now(), data: null };
      return null;
    }

    // Aggregate across seasons 2024 + 2025 (covers current + previous season)
    let totalCards = 0, totalYellow = 0, totalGames = 0;
    for (const ref of refs) {
      for (const stat of (ref.statistics || [])) {
        const season = stat.league?.season;
        if (season !== 2024 && season !== 2025) continue;
        const games   = stat.games?.played || 0;
        const yellows = stat.cards?.yellow || 0;
        const reds    = (stat.cards?.red || 0) + (stat.cards?.yellowred || 0);
        totalGames  += games;
        totalYellow += yellows;
        totalCards  += yellows + reds;
      }
    }

    if (!totalGames) {
      _refereeCache[key] = { ts: Date.now(), data: null };
      return null;
    }

    const result = {
      name:      refs[0]?.referee?.name || refName,
      avgCards:  Math.round((totalCards  / totalGames) * 100) / 100,
      avgYellow: Math.round((totalYellow / totalGames) * 100) / 100,
      games:     totalGames,
    };
    _refereeCache[key] = { ts: Date.now(), data: result };
    return result;
  } catch(e) {
    return null;
  }
}

function _saveRefereeCache() {
  try { fs.writeFileSync(REFEREE_CACHE_FILE, JSON.stringify(_refereeCache)); }
  catch(e) { console.warn('[Referee] Cache speichern fehlgeschlagen:', e.message); }
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
// Also computes O/U 2.5 consensus: o25_fair, u25_fair, o25_cn.
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

  // ── Pass 1b: consensus fair O/U 2.5 (same weighting as 1X2) ────────────────
  const _ouSamples = [];
  for (const bkr of bookmakers) {
    let _o25 = null, _u25 = null;
    for (const bet of (bkr.bets || [])) {
      const bn = (bet.name || '').toLowerCase().trim();
      if (bn === 'goals over/under' || bn === 'total goals' || bn === 'over/under' || bn === 'total - goals' || bn.includes('goals o/u') || (bn.includes('over') && bn.includes('under') && bn.includes('goal'))) {
        for (const v of (bet.values || [])) {
          const vl = (v.value || '').toLowerCase();
          if (vl === 'over 2.5')  _o25 = parseFloat(v.odd);
          else if (vl === 'under 2.5') _u25 = parseFloat(v.odd);
        }
        break;
      }
    }
    if (!_o25 || !_u25 || isNaN(_o25) || isNaN(_u25)) continue;
    const _tot = 1/_o25 + 1/_u25;
    const _margin = _tot - 1;
    if (_margin > 0.12 || _margin < -0.02) continue; // skip corrupt/exchange outliers
    const _isPinn = bkr.name?.toLowerCase().includes('pinnacle') || bkr.id === 8;
    _ouSamples.push({
      po: (1/_o25) / _tot, pu: (1/_u25) / _tot,
      weight: _isPinn ? 2.0 : 1.0,
      name: bkr.name || `id${bkr.id}`
    });
  }
  if (_ouSamples.length >= 1) {
    const _tw  = _ouSamples.reduce((s, d) => s + d.weight, 0);
    const _po  = _ouSamples.reduce((s, d) => s + d.po * d.weight, 0) / _tw;
    const _pu  = _ouSamples.reduce((s, d) => s + d.pu * d.weight, 0) / _tw;
    const _n   = _po + _pu;
    const _r2  = (x) => Math.round(x * 100) / 100;
    r.o25_fair = _r2(_n / _po); // fair odds Over 2.5 (no margin)
    r.u25_fair = _r2(_n / _pu); // fair odds Under 2.5
    r.o25_cn   = _ouSamples.length; // bookmaker count for O/U consensus
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
          else if (vl === 'over 11.5'  && !r.co115) r.co115 = parseFloat(v.odd);
          else if (vl === 'under 11.5' && !r.cu115) r.cu115 = parseFloat(v.odd);
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
      } else if (
        // API-Football First Half goals market — various bet names observed in the wild:
        // "First Half - Goals - Over/Under", "Goals - 1st Half", "First Half Goals",
        // "1st Half Total Goals", "Half Time - Over/Under Goals", "HT Total Goals"
        (bn.includes('first half') && (bn.includes('goal') || bn.includes('over') || bn.includes('under'))) ||
        (bn.includes('1st half') && (bn.includes('goal') || bn.includes('over') || bn.includes('under'))) ||
        bn === 'ht goals over/under' || bn === 'half time goals' || bn === 'first half - goals'
      ) {
        for (const v of (bet.values || [])) {
          const vl = (v.value || '').toLowerCase();
          if      (vl === 'over 0.5'  && !r.ht_o05) r.ht_o05 = parseFloat(v.odd);
          else if (vl === 'under 0.5' && !r.ht_u05) r.ht_u05 = parseFloat(v.odd);
          else if (vl === 'over 1.5'  && !r.ht_o15) r.ht_o15 = parseFloat(v.odd);
          else if (vl === 'under 1.5' && !r.ht_u15) r.ht_u15 = parseFloat(v.odd);
          else if (vl === 'over 2.5'  && !r.ht_o25) r.ht_o25 = parseFloat(v.odd);
          else if (vl === 'under 2.5' && !r.ht_u25) r.ht_u25 = parseFloat(v.odd);
        }
      } else if (
        (bn.includes('first half') || bn.includes('1st half') || bn.includes('half time')) &&
        bn.includes('both teams')
      ) {
        for (const v of (bet.values || [])) {
          const vl = (v.value || '').toLowerCase();
          if      ((vl === 'yes' || vl === 'gg') && !r.ht_bttsY) r.ht_bttsY = parseFloat(v.odd);
          else if ((vl === 'no'  || vl === 'ng') && !r.ht_bttsN) r.ht_bttsN = parseFloat(v.odd);
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
  let _apiRemaining = 9999; // assume plenty unless we can check
  try {
    const _st = await apiFetch('/status');
    const _sub = (_st.response || {}).subscription || {};
    const _req = (_st.response || {}).requests || {};
    _apiRemaining = (_req.limit_day ?? 9999) - (_req.current ?? 0);
    console.log(`[Server] API-Account: Plan="${_sub.plan||'?'}" | Heute: ${_req.current??'?'}/${_req.limit_day??'?'} Requests | Verbleibend: ${_apiRemaining}`);
    if (_apiRemaining < 200) {
      console.warn(`[Server] ⚠ Quota knapp (${_apiRemaining} verbleibend) — Step1.6 (Bookings) wird übersprungen um Odds-Fetch zu sichern`);
    }
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
          leagueId:     parseInt(leagueId, 10),
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
          bookings:     { threshold: YELLOW_THRESHOLDS[parseInt(leagueId,10)] || 5, home: [], away: [] },
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

  // ── Step 1.6: Yellow card counts (24h cache, 1–2 calls per team) ────────────
  // Finds players with yellows >= threshold-1 (one away from suspension)
  // Cached 24h — bookings change once per matchday, not intra-day
  const staleBookingTeams = uniqueTeamIds.filter(id => {
    const c = _bookingsCache[id];
    return !c || Date.now() - c.ts >= BOOKINGS_TTL;
  });
  // Guard: skip booking re-fetch if quota is too low — odds (Step 5) must have priority.
  // Each team needs 1-2 calls; with 272 teams that's up to 544 calls. Keep 400+ for odds/injuries.
  const _needBookingCalls = staleBookingTeams.length * 1.5; // estimate 1.5 calls/team average
  if (_apiRemaining < 200 && staleBookingTeams.length > 0) {
    console.warn(`[Server] Step1.6: ÜBERSPRUNGEN — nur ${_apiRemaining} API-Calls verbleibend, Odds-Fetch hat Vorrang`);
  } else {
    console.log(`[Server] Step1.6: Gelbkarten — ${staleBookingTeams.length} Teams neu laden (~${Math.round(_needBookingCalls)} Calls), ${uniqueTeamIds.length - staleBookingTeams.length} gecacht`);
    for (let i = 0; i < staleBookingTeams.length; i += 5) {
      await Promise.allSettled(staleBookingTeams.slice(i, i + 5).map(id => fetchTeamBookings(id)));
      if (i + 5 < staleBookingTeams.length) await sleep(800);
    }
    if (staleBookingTeams.length) _saveBookingsCache();
  }

  // Enrich each fixture with near-suspension players
  for (const d of fixtures) {
    const threshold = YELLOW_THRESHOLDS[d.leagueId] || 5;
    const enrichSide = (teamId) => {
      const raw  = _bookingsCache[teamId]?.data || [];
      const posMap = _squadCache[teamId]?.data || {};
      return raw
        .filter(p => p.yellows >= threshold - 1)
        .map(p => {
          const pos = (p.id && posMap[`id_${p.id}`])
            || posMap[(p.name || '').toLowerCase().trim()]
            || null;
          return {
            id:         p.id,
            name:       p.name,
            yellows:    p.yellows,
            threshold,
            position:   pos,
            atThreshold: p.yellows >= threshold,  // already AT threshold — suspended if not reset
            oneAway:    p.yellows === threshold - 1,  // one yellow away from ban
          };
        })
        .sort((a, b) => b.yellows - a.yellows);
    };
    d.bookings = {
      threshold,
      home: enrichSide(d.homeTeamId),
      away: enrichSide(d.awayTeamId),
    };
  }
  console.log(`  Step1.6 fertig`);

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

  // ── Step 4: Referee stats (48h disk cache, ~1 call per unique referee) ────
  // Fetches /referees?name=X for each unique referee name, aggregates cards/game
  // across seasons 2024+2025. Results are stored in referee-cache.json (48h TTL).
  // With ~10–15 unique refs per run this costs ≤15 API calls — well within quota.
  const uniqueRefs = [...new Set(fixtures.map(d => d.referee).filter(Boolean))];
  const staleRefs  = uniqueRefs.filter(name => {
    const c = _refereeCache[name.toLowerCase().trim()];
    return !c || Date.now() - c.ts >= REFEREE_TTL;
  });
  console.log(`[Server] Step4: ${uniqueRefs.length} Schiris (${staleRefs.length} neu laden, ${uniqueRefs.length - staleRefs.length} gecacht)...`);

  // Sequential fetch — small set, each may need 1–2 API calls (last-name fallback)
  for (const refName of staleRefs) {
    await fetchRefereeStats(refName);
    await sleep(CALL_DELAY);
  }
  if (staleRefs.length) _saveRefereeCache();

  // Enrich fixtures with referee stats
  for (const d of fixtures) {
    if (!d.referee) continue;
    d.refereeStats = _refereeCache[d.referee.toLowerCase().trim()]?.data || null;
  }
  const refOk = fixtures.filter(d => d.refereeStats).length;
  console.log(`  Step4 fertig: ${refOk}/${uniqueRefs.length} Schiris mit Stats`);

  // ── Step 5: The Odds API — Pre-Match Odds ────────────────────────────────
  // One API call per league fetches ALL upcoming fixtures' odds at once.
  // Covers same-day games (unlike API-Football which stops ~4 days before kickoff).
  // Regions: eu,uk — UK bookmakers required for SCO/BEL/SUI (EU-only returns empty array).
  // Markets: h2h (1X2), spreads (AH), totals (O/U).
  // DC odds (dc1X/X2/12) are derived from fair h2h probabilities.
  // Note: Cards/corners via Step 5c (alternate markets, eu,uk). BTTS via Step 5b (uk).
  const upcoming = fixtures.filter(d => !d.isFinished && d.fixtureId);
  const _uniqueSportKeys = [...new Set(
    fixtures.filter(d => !d.isFinished && d.leagueId && LEAGUE_ODDS_KEYS[d.leagueId])
            .map(d => LEAGUE_ODDS_KEYS[d.leagueId])
  )];
  console.log(`[Server] Step5 (TheOddsAPI): ${_uniqueSportKeys.length} Ligen, ~${upcoming.length} Spiele...`);

  const _sportKeyEvents = {};   // sportKey → events[]
  let _oddsApiRemaining = null;
  for (const sk of _uniqueSportKeys) {
    await sleep(600);
    try {
      const { data, remaining } = await oddsApiFetch(sk);
      if (remaining !== null) _oddsApiRemaining = remaining;
      if (Array.isArray(data) && data.length > 0) {
        _sportKeyEvents[sk] = data;
        console.log(`  [OddsAPI] ${sk}: ${data.length} Events`);
      } else if (Array.isArray(data)) {
        _sportKeyEvents[sk] = [];
        console.log(`  [OddsAPI] ${sk}: 0 Events (kein Spieltag oder Liga nicht verfügbar)`);
      } else {
        _sportKeyEvents[sk] = [];
        const errMsg = data?.message || JSON.stringify(data).slice(0, 80);
        console.warn(`  [OddsAPI] ${sk}: Fehler — ${errMsg}`);
      }
    } catch(e) {
      _sportKeyEvents[sk] = [];
      console.warn(`  [OddsAPI] ${sk}: Exception — ${e.message}`);
    }
  }
  if (_oddsApiRemaining !== null)
    console.log(`[OddsAPI] Verbleibende Requests diesen Monat: ${_oddsApiRemaining}`);

  // ── Step 5b: BTTS enrichment via UK region ────────────────────────────────
  // btts market causes 422 with regions=eu — UK bookmakers (Bet365 etc.) carry it.
  // Merge into existing _sportKeyEvents by event ID so parseTheOddsEvent gets btts data.
  let bttsEnriched = 0;
  for (const sk of _uniqueSportKeys) {
    if (!_sportKeyEvents[sk]?.length) continue;
    await sleep(400);
    const bttsEvents = await oddsApiFetchBtts(sk);
    for (const be of bttsEvents) {
      const main = _sportKeyEvents[sk].find(e => e.id === be.id);
      if (!main) continue;
      for (const bkr of (be.bookmakers || [])) {
        const existing = main.bookmakers.find(b => b.key === bkr.key);
        if (existing) {
          for (const mkt of (bkr.markets || [])) {
            if (!existing.markets.find(m => m.key === mkt.key)) existing.markets.push(mkt);
          }
        } else {
          main.bookmakers.push(bkr);
        }
      }
      bttsEnriched++;
    }
  }
  if (bttsEnriched > 0) console.log(`  [OddsAPI] BTTS enriched: ${bttsEnriched} Events`);

  // ── Step 5c: Alternate markets — Corners + Cards + Double Chance ─────────
  let altEnriched = 0;
  for (const sk of _uniqueSportKeys) {
    if (!_sportKeyEvents[sk]?.length) continue;
    await sleep(400);
    const { data: altEvents } = await oddsApiFetchAlt(sk);
    for (const ae of altEvents) {
      const main = _sportKeyEvents[sk].find(e => e.id === ae.id);
      if (!main) continue;
      for (const bkr of (ae.bookmakers || [])) {
        const existing = main.bookmakers.find(b => b.key === bkr.key);
        if (existing) {
          for (const mkt of (bkr.markets || [])) {
            if (!existing.markets.find(m => m.key === mkt.key)) existing.markets.push(mkt);
          }
        } else {
          main.bookmakers.push(bkr);
        }
      }
      altEnriched++;
    }
  }
  if (altEnriched > 0) console.log(`  [OddsAPI] Corners/Cards/DC enriched: ${altEnriched} Events`);

  // ── Step 5d: 1st half markets — h2h_h1 + totals_h1 (EU) + btts_h1 (UK) ───
  // Pass 4a: EU region — halftime 1X2 and halftime over/under totals
  let htEnriched = 0;
  for (const sk of _uniqueSportKeys) {
    if (!_sportKeyEvents[sk]?.length) continue;
    await sleep(400);
    const htEvents = await oddsApiFetchHT(sk);
    for (const he of htEvents) {
      const main = _sportKeyEvents[sk].find(e => e.id === he.id);
      if (!main) continue;
      for (const bkr of (he.bookmakers || [])) {
        const existing = main.bookmakers.find(b => b.key === bkr.key);
        if (existing) {
          for (const mkt of (bkr.markets || [])) {
            if (!existing.markets.find(m => m.key === mkt.key)) existing.markets.push(mkt);
          }
        } else {
          main.bookmakers.push(bkr);
        }
      }
      htEnriched++;
    }
  }
  // Pass 4b: UK region — 1st half BTTS (btts_h1 not in EU region)
  let htBttsEnriched = 0;
  for (const sk of _uniqueSportKeys) {
    if (!_sportKeyEvents[sk]?.length) continue;
    await sleep(400);
    const htBttsEvents = await oddsApiFetchHTBtts(sk);
    for (const hbe of htBttsEvents) {
      const main = _sportKeyEvents[sk].find(e => e.id === hbe.id);
      if (!main) continue;
      for (const bkr of (hbe.bookmakers || [])) {
        const existing = main.bookmakers.find(b => b.key === bkr.key);
        if (existing) {
          for (const mkt of (bkr.markets || [])) {
            if (!existing.markets.find(m => m.key === mkt.key)) existing.markets.push(mkt);
          }
        } else {
          main.bookmakers.push(bkr);
        }
      }
      htBttsEnriched++;
    }
  }
  if (htEnriched > 0 || htBttsEnriched > 0)
    console.log(`  [OddsAPI] HZ-Märkte enriched: h2h_h1/totals_h1 ${htEnriched} · btts_h1 ${htBttsEnriched} Events`);

  let oddsOk = 0, oddsMiss = 0;
  for (const d of upcoming) {
    const sk = d.leagueId ? LEAGUE_ODDS_KEYS[d.leagueId] : null;
    const events = sk ? (_sportKeyEvents[sk] || []) : [];
    const matched = matchOddsEvent(d.homeTeamName, d.awayTeamName, d.date, events);
    if (matched) {
      const parsed = parseTheOddsEvent(matched);
      if (Object.keys(parsed).length > 0) {
        d.odds = parsed;
        // Log first successful parse for diagnostics
        if (oddsOk === 0) {
          const bkrNames = matched.bookmakers.map(b => b.title || b.key).join(', ');
          console.log(`  [OddsAPI] Sample Bookies: ${bkrNames}`);
          console.log(`  [OddsAPI] Sample Parsed: hw=${parsed.hw} dr=${parsed.dr} aw=${parsed.aw} bttsY=${parsed.bttsY||'-'} o25=${parsed.o25||'-'} ah_h=${parsed.ah_h||'-'}@${parsed.ah_h_point}`);
        }
        oddsOk++;
      } else { oddsMiss++; }
    } else { oddsMiss++; }
  }
  console.log(`  Step5 fertig: ${oddsOk} OK · ${oddsMiss} kein Match (von ${upcoming.length} Spielen)`);

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

  console.log(`\n[Server] ✅ Fertig: ${fixtures.length} Spiele, ${h2hOk} H2H, ${injOk} Verletzungen, ${refOk}/${uniqueRefs.length} Schiri-Stats, ${oddsOk} Quoten, ${predOk} Predictions\n`);
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

      // ── Preserve odds_open from previous run ──────────────────────────────
      // odds_open is set once (first time we see a fixture with odds) and never overwritten.
      // This creates a permanent opening-line snapshot for line movement detection.
      const prevOddsOpen = {};
      try {
        const prev = JSON.parse(fs.readFileSync(outPath, 'utf8'));
        for (const fx of (prev.fixtures || [])) {
          if (fx.fixtureId && fx.odds_open) prevOddsOpen[fx.fixtureId] = fx.odds_open;
        }
        console.log(`[GitHub Actions] odds_open: ${Object.keys(prevOddsOpen).length} Opening-Snapshots aus vorherigem Run geladen`);
      } catch(e) {
        console.log('[GitHub Actions] odds_open: Kein vorheriger Run gefunden (erster Lauf oder Datei fehlt)');
      }
      for (const fx of fixtures) {
        if (fx.odds && Object.keys(fx.odds).length > 0) {
          // Keep existing opening snapshot, or set current odds as baseline (first time)
          fx.odds_open = prevOddsOpen[fx.fixtureId] || { ...fx.odds };
        }
      }
      // ─────────────────────────────────────────────────────────────────────

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
