#!/usr/bin/env node
/**
 * generate_picks.js
 *
 * Runs the ACTUAL getBettingPicks() + computeMatchScore() from season-finish.html
 * in a Node.js vm context — picks are identical to what the browser renders.
 *
 * Output: picks_output.json   (read by save_picks.py)
 * Usage:  node generate_picks.js
 */

'use strict';
const fs   = require('fs');
const path = require('path');
const vm   = require('vm');

// ── Window shim — pick-engine.js was written for browser context; ─────────────
// it references window._oddsData, window._teamStats, window._oddsReady etc.
// A global shim prevents "window is not defined" in Node.js.
// _teamStats is updated after stats_cache.json loads (see engine.setTeamStats below).
if (typeof window === 'undefined') {
  global.window = {
    _oddsData: {}, _preMatchData: {}, _oddsReady: false,
    _teamStats: {},
    _igDataUrl: '', _igFileName: '',
  };
}

// ── Pick engine (canonical Node.js path — no VM extraction needed) ────────────
const engine = require('./pick-engine.js');
const { getBettingPicks, computeMatchScore, deriveOdds } = engine;

const BASE           = __dirname;
const HTML_PATH      = path.join(BASE, 'season-finish.html');
const PREMATCH_PATH  = path.join(BASE, 'prematch-data.json');
const STATS_PATH     = path.join(BASE, 'stats_cache.json');
const OUTPUT_PATH    = path.join(BASE, 'picks_output.json');

// ── 1. Read HTML and extract <script> block ───────────────────────────────────
const html = fs.readFileSync(HTML_PATH, 'utf8');
const sStart = html.indexOf('<script>');
const sEnd   = html.indexOf('</script>', sStart);
if (sStart === -1 || sEnd === -1) { console.error('No <script> found'); process.exit(1); }
let script = html.substring(sStart + 8, sEnd);
console.log(`Extracted ${script.length} chars of JS`);

// ── 2. Remove the IIFE that calls window.fetch.bind (CORS proxy — not needed) ─
// Replace the self-invoking CORS proxy function with a no-op before eval
script = script.replace(
  '(function _installCorsProxy() {',
  '(function _installCorsProxy_DISABLED_IN_NODE() { return; // '
);

// ── 3. Remove DOM-manipulation code that runs at module level ─────────────────
// Cut script at first top-level querySelectorAll call
const domIdx = script.indexOf('\ndocument.querySelector');
if (domIdx > -1) {
  const cut = script.lastIndexOf('\n}\n', domIdx);
  script = script.substring(0, cut > 0 ? cut + 2 : domIdx);
  console.log(`Trimmed to ${script.length} chars`);
}

// ── 4. Load prematch odds (prematch-data.json) ────────────────────────────────
let pmFixtures = [];
try {
  const pm = JSON.parse(fs.readFileSync(PREMATCH_PATH, 'utf8'));
  pmFixtures = pm.fixtures || [];
} catch (_) {}
console.log(`Prematch fixtures loaded: ${pmFixtures.length}`);

// Build lookup: normalized "home|away" → odds object
function normTeam(s) {
  return s.toLowerCase()
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')  // strip diacritics
    .replace(/\b(fc|sv|sc|ac|as|us|cd|sk|rb)\b/g, ' ')
    .replace(/[^a-z0-9 ]/g, ' ')
    .replace(/\s+/g, ' ').trim();
}
const pmOddsMap = {};
const pmH2hMap  = {};
for (const fx of pmFixtures) {
  const h = normTeam(fx.homeTeamName || fx.home || '');
  const a = normTeam(fx.awayTeamName || fx.away || '');
  if (h && a) {
    pmOddsMap[`${h}|${a}`] = fx.odds || {};
    if (fx.h2h && fx.h2h.games > 0) pmH2hMap[`${h}|${a}`] = fx.h2h;
  }
}
console.log(`H2H fixtures loaded: ${Object.keys(pmH2hMap).length}`);

function findPrematchOdds(home, away) {
  const hn = normTeam(home), an = normTeam(away);
  const key = `${hn}|${an}`;
  if (pmOddsMap[key]) return pmOddsMap[key];
  // Fuzzy: partial containment
  for (const [k, v] of Object.entries(pmOddsMap)) {
    const [kh, ka] = k.split('|');
    if ((kh.includes(hn) || hn.includes(kh)) &&
        (ka.includes(an) || an.includes(ka))) return v;
  }
  return {};
}

function findPrematchH2h(home, away) {
  const hn = normTeam(home), an = normTeam(away);
  const key = `${hn}|${an}`;
  if (pmH2hMap[key]) return pmH2hMap[key];
  // Fuzzy: partial containment
  for (const [k, v] of Object.entries(pmH2hMap)) {
    const [kh, ka] = k.split('|');
    if ((kh.includes(hn) || hn.includes(kh)) &&
        (ka.includes(an) || an.includes(ka))) return v;
  }
  return null;
}

// ── 5. Load stats_cache.json (xG, Elo, corner rates — mirrors window._teamStats) ──
let teamStats = {};
try {
  teamStats = JSON.parse(fs.readFileSync(STATS_PATH, 'utf8'));
  const leagues = Object.keys(teamStats).length;
  const teams   = Object.values(teamStats).reduce((n, l) => n + Object.keys(l).length, 0);
  console.log(`Team stats loaded: ${leagues} leagues, ${teams} teams`);
} catch (_) {
  console.warn('stats_cache.json not found — xG/Elo stats unavailable');
}
engine.setTeamStats(teamStats);
if (typeof global.window !== 'undefined') global.window._teamStats = teamStats;

// ── 6. Build vm sandbox with browser API stubs ────────────────────────────────
const mockFetch = () => Promise.resolve({
  json: () => Promise.resolve({}),
  blob: () => Promise.resolve({}),
  ok: true, status: 200,
});

const sandbox = {
  // window — must have fetch so _installCorsProxy can reference it even disabled
  window: {
    fetch: mockFetch,
    _oddsData: {}, _preMatchData: {}, _oddsReady: false,
    _teamStats: teamStats,   // ← real xG/Elo data from stats_cache.json
    _igDataUrl: '', _igFileName: '',
  },
  // Browser globals
  document: {
    getElementById:     () => ({ innerHTML:'', style:{}, classList:{ add:()=>{}, remove:()=>{} }, addEventListener:()=>{} }),
    querySelector:      () => null,
    querySelectorAll:   () => [],
    addEventListener:   () => {},
    createElement:      () => ({ getContext:()=>null, width:0, height:0 }),
  },
  localStorage:  { getItem:()=>null, setItem:()=>{}, removeItem:()=>{} },
  sessionStorage:{ getItem:()=>null, setItem:()=>{}, removeItem:()=>{} },
  navigator:     { clipboard:{ write:()=>Promise.resolve() }, canShare:()=>false },
  fetch:         mockFetch,
  Blob:          function Blob(){},
  ClipboardItem: function ClipboardItem(){},
  URL:           { createObjectURL:()=>'', revokeObjectURL:()=>{} },
  Image:         function Image(){},
  setTimeout:    ()=>{}, clearTimeout:()=>{},
  setInterval:   ()=>{}, clearInterval:()=>{},
  requestAnimationFrame: ()=>{},
  alert:         ()=>{}, confirm:()=>false,
  console,
  // Export capture
  exports: {},
};

// ── 7. Append LEAGUES export and evaluate ────────────────────────────────────
// Pick functions come from pick-engine.js (require above). VM only needed for LEAGUES data.
script += `\ntry { exports.LEAGUES = LEAGUES; } catch(_e) {}`;

try {
  vm.runInNewContext(script, sandbox);
} catch (e) {
  console.error('VM error:', e.message);
  // Show which line caused the issue
  const lines = e.stack.split('\n');
  lines.slice(0, 8).forEach(l => console.error(l));
  process.exit(1);
}

const LEAGUES = sandbox.exports.LEAGUES;
if (!LEAGUES) {
  console.error('Failed to extract LEAGUES from season-finish.html');
  process.exit(1);
}
// pick-engine.js references the global LEAGUES for rest-day calculations (line 954).
// Expose it so getBettingPicks() can find it regardless of require() scope.
global.LEAGUES = LEAGUES;
// getBettingPicks, computeMatchScore, deriveOdds come from pick-engine.js (required above)
console.log(`pick-engine.js: ${typeof getBettingPicks}, ${typeof computeMatchScore}, ${typeof deriveOdds}`);
console.log(`Leagues found: ${Object.keys(LEAGUES).length}`);

// ── 7b. Market name → marketKey mapping ──────────────────────────────────────
// Must match resolve_picks.py evaluate_pick() exactly.
function marketToKey(market) {
  const m = market.trim();
  const ml = m.toLowerCase();

  // Result
  if (ml === 'heimsieg')      return 'homeWin';
  if (ml === 'auswärtssieg')  return 'awayWin';
  if (ml === 'unentschieden') return 'draw';

  // Goals
  if (/^über 2\.5 tore$/i.test(ml) || /^over 2\.5 tore$/i.test(ml)) return 'over25';
  if (/^unter 2\.5 tore$/i.test(ml) || /^under 2\.5 tore$/i.test(ml)) return 'under25';
  if (/^über 3\.5 tore$/i.test(ml) || /^over 3\.5 tore$/i.test(ml)) return 'over35';
  if (/^unter 3\.5 tore$/i.test(ml) || /^under 3\.5 tore$/i.test(ml)) return 'under35';

  // BTTS
  if (/^beide teams treffen$/.test(ml))        return 'btts';
  if (/^beide teams treffen: nein$/.test(ml))  return 'noBtts';

  // Cards
  if (/^über 3\.5 karten$/i.test(ml)) return 'cards35';
  if (/^über 4\.5 karten$/i.test(ml)) return 'cards45';

  // Asian Handicap — "AH Heim -2.25" / "AH Ausw. -1.5" / "AH Auswärts +2"
  let ahM = m.match(/^ah\s+heim\s+([-+]?\d+\.?\d*)/i);
  if (ahM) return `ah_home:${ahM[1]}`;
  // Away AH: capture the trailing number (handles "AH Ausw. -1.5", "AH Auswärts +2")
  ahM = m.match(/^ah\s+ausw[^\s\d+-]*\.?\s+([-+]?\d+\.?\d*)/i);
  if (ahM) return `ah_away:${ahM[1]}`;

  // Handicap Heim / Handicap Auswärts (PICK 3 model-estimated AH)
  // e.g. "Handicap Heim -0.5", "Handicap Heim -0.75", "Handicap Heim -1.0"
  // Same resolution logic as ah_home / ah_away — map to same key format.
  let hcM = m.match(/^handicap\s+heim\s+([-+]?\d+\.?\d*)/i);
  if (hcM) return `ah_home:${hcM[1]}`;
  hcM = m.match(/^handicap\s+ausw[äa][^\s\d+-]*\.?\s*([-+]?\d+\.?\d*)/i);
  if (hcM) return `ah_away:${hcM[1]}`;

  // Double Chance
  if (/doppelte chance.*1x/i.test(ml)) return 'dc1X';
  if (/doppelte chance.*x2/i.test(ml)) return 'dcX2';
  if (/doppelte chance.*12/i.test(ml)) return 'dc12';

  // Corners  (e.g. "Über 9.5 Ecken" / "Unter 8.5 Ecken")
  let cM = m.match(/[üU]ber\s+(\d+\.?\d*)\s+Ecken/i);
  if (cM) return `corners_over:${cM[1]}`;
  cM = m.match(/[uU]nter\s+(\d+\.?\d*)\s+Ecken/i);
  if (cM) return `corners_under:${cM[1]}`;

  // Half-time goals
  if (/1\.\s*hz.*over 0\.5/i.test(ml) || /1\.\s*hz.*über 0\.5/i.test(ml)) return 'ht_over05';
  if (/1\.\s*hz.*beide teams treffen: nein/i.test(ml)) return 'ht_noBtts';
  if (/1\.\s*hz.*beide teams treffen/i.test(ml)) return 'ht_btts';
  if (/1\.\s*hz.*over 1\.5/i.test(ml)) return 'ht_over15';

  // Team-specific goals — "PSG über 1.5 Tore"
  // Note: this function is now called as marketToKey(market, home, away) to encode home/away context
  const tgM = m.match(/über\s+(\d+\.?\d*)\s+Tore$/i);
  if (tgM) {
    const thr = tgM[1];
    const _home = (marketToKey._home || '').toLowerCase();
    const _away = (marketToKey._away || '').toLowerCase();
    if (_home && m.toLowerCase().includes(_home)) return `team_goals_home_over:${thr}`;
    if (_away && m.toLowerCase().includes(_away)) return `team_goals_away_over:${thr}`;
    return `team_goals_over:${thr}`;  // fallback (legacy, will void)
  }

  // Fallback slug
  return ml.replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '') || 'unknown';
}

// ── 8. Run picks for every fixture ───────────────────────────────────────────
const output = [];
let total = 0, errors = 0;

for (const [leagueKey, league] of Object.entries(LEAGUES)) {
  const fixtures = league.fixtures || [];
  for (const match of fixtures) {
    if (!match.home || !match.away) continue;
    total++;

    // Build odds object from prematch-data.json — MUST pass through deriveOdds() first.
    // The browser calls deriveOdds() before getBettingPicks(); skipping this step causes
    // completely different picks (no de-vigged probabilities, no DC/DNB/AH derived markets).
    const odds = deriveOdds ? deriveOdds(findPrematchOdds(match.home, match.away)) : findPrematchOdds(match.home, match.away);

    // Inject league-level roundsLeft into match — getBettingPicks() reads match.roundsLeft
    // to compute urgencyMed, awayNeedsWin, homeNeedsWin, and all pressure boosts.
    // Without this, _rl=99 → urgencyMed=false → zero pressure signals for ALL matches.
    if (match.roundsLeft == null) match.roundsLeft = league.roundsLeft ?? 99;

    // Enrich match with FULL H2H data from prematch-data.json.
    // LEAGUES already has a simplified h2h (from update_dashboard.py) that lacks
    // bttsRate, over25Rate, over35Rate, lastResults — the fields that drive BTTS picks.
    // prematch-server.js fetches the full h2h (identical to what the browser fetches live),
    // so we always prefer it. This fixes browser↔history pick divergence.
    const h2h = findPrematchH2h(match.home, match.away);
    if (h2h) match.h2h = h2h;  // override simplified LEAGUES h2h with full prematch h2h

    let picks = [], matchScore = 0;
    try {
      picks = getBettingPicks(match, odds, leagueKey) || [];
    } catch (e) {
      errors++;
      if (errors <= 3) console.warn(`  pick error ${match.home} vs ${match.away}: ${e.message}`);
    }
    try {
      matchScore = computeMatchScore(match, leagueKey) || 0;
    } catch (_) {}

    // Format date for picks_history compatibility
    const dateStr  = match.date || '';
    const dateIso  = (() => {
      try {
        const [d,m,y] = dateStr.split('.');
        return `${y}-${m.padStart(2,'0')}-${d.padStart(2,'0')}`;
      } catch(_) { return ''; }
    })();

    output.push({
      league:     leagueKey,
      leagueName: league.name  || leagueKey,
      leagueFlag: league.flag  || '',
      roundsLeft: league.roundsLeft ?? 99,
      home:       match.home,
      away:       match.away,
      date:       dateStr,
      dateIso,
      eventId:    match.eventId || null,
      matchScore: Math.round(matchScore * 10) / 10,
      picks: (picks || []).map(p => ({
        market:    p.market    || '',
        marketKey: (marketToKey._home = match.home, marketToKey._away = match.away, marketToKey(p.market || '')),
        icon:      p.icon      || '',
        conf:      p.conf      || 'medium',
        sc:        typeof p.sc === 'number' ? Math.round(p.sc * 1000) / 1000 : 0,
        odds:      p.odds != null ? p.odds : null,
        modelOdds: p.modelOdds != null ? p.modelOdds : null,
        value:     p.value     || null,
        oddsIsEst: p.oddsIsEst || false,
        reason:    p.reason    || '',
        mods:      Array.isArray(p.mods) ? p.mods : [],
        saferAlt:  p.saferAlt  || null,
        boldAlt:   p.boldAlt   || null,
      })),
    });
  }
}

// ── 9. Second pass: prematch-only fixtures (POL, CRO, SUI, BEL, TUR …) ──────────
// generate_picks.js iterates LEAGUES from season-finish.html, which only includes
// leagues fetched by update_dashboard.py. prematch-server.js fetches additional leagues
// (e.g. Ekstraklasa, HNL, Super Lig, Swiss SL) that are NOT in LEAGUES.
// This pass processes those extra fixtures so they also get picks.

// Build set of already-processed home|away pairs
const processed = new Set(output.map(e => `${normTeam(e.home)}|${normTeam(e.away)}`));

// League metadata from prematch-data.json fixtures
const PM_LEAGUE_META = {
  // leagueId → { key, name, flag }
  // NOTE: leagueId 88 = Eredivisie (NED top flight) — already processed via LEAGUES pass 1. DO NOT add here.
  // NOTE: leagueId 218 = Österreichische BL (AUT top flight) — already processed via LEAGUES pass 1. DO NOT add here.
  // Adding these caused duplicate results entries (score 1.0/12) because team names in prematch-data.json
  // differ slightly from LEAGUES names (e.g. "Feyenoord Rotterdam" vs "Feyenoord") → dedup check fails.
  203: { key:'TUR', name:'Süper Lig',        flag:'🇹🇷' },
  106: { key:'POL', name:'Ekstraklasa',      flag:'🇵🇱' },
  207: { key:'SUI', name:'Super League',     flag:'🇨🇭' },
  144: { key:'BEL', name:'First Division A', flag:'🇧🇪' },
  210: { key:'CRO', name:'HNL',              flag:'🇭🇷' },
  104: { key:'RUS', name:'Premier Liga',     flag:'🇷🇺' },
  // NED2 (Eerste Divisie, leagueId 89) and AUT2 (2.Liga) intentionally omitted —
  // no stake/standings data available → would generate 1.0/12 noise entries.
};

// Pick the best LEAGUES key to borrow context from (for getBettingPicks league config)
// Falls back to a neutral similar league key so pick logic still runs.
const FALLBACK_LEAGUE_KEY = {
  TUR:  'GER',   // Similar league profile
  POL:  'GER',
  SUI:  'GER',
  BEL:  'GER',
  CRO:  'NED',
  NED2: 'NED',
  AUT2: 'AUT',
};

let extraTotal = 0, extraErrors = 0;

for (const fx of pmFixtures) {
  const hn = normTeam(fx.homeTeamName || '');
  const an = normTeam(fx.awayTeamName || '');
  if (!hn || !an) continue;
  if (processed.has(`${hn}|${an}`)) continue;  // already in output

  const meta = PM_LEAGUE_META[fx.leagueId];
  if (!meta) continue;  // only process known extra leagues

  processed.add(`${hn}|${an}`);
  extraTotal++;

  const leagueKey = FALLBACK_LEAGUE_KEY[meta.key] || 'GER';
  const odds  = deriveOdds ? deriveOdds(findPrematchOdds(fx.homeTeamName, fx.awayTeamName)) : findPrematchOdds(fx.homeTeamName, fx.awayTeamName);
  const h2h   = findPrematchH2h(fx.homeTeamName, fx.awayTeamName);

  // Build a match object compatible with getBettingPicks
  const match = {
    home:       fx.homeTeamName,
    away:       fx.awayTeamName,
    date:       fx.date ? (fx.date.includes('-') ? fx.date.split('-').reverse().join('.') : fx.date) : '',
    roundsLeft: fx.roundsLeft ?? 99,
    h2h:        h2h || fx.h2h || null,
    homeStake:  fx.homeStake  || null,
    awayStake:  fx.awayStake  || null,
    homeForm:   fx.homeForm   || null,
    awayForm:   fx.awayForm   || null,
    homeSquad:  fx.homeSquad  || null,
    awaySquad:  fx.awaySquad  || null,
    refereeStats: fx.refereeStats || null,
    expGoals:   fx.expGoals   || null,
    matchScore: fx.matchScore  || null,
    eventId:    fx.eventId    || null,
  };

  let picks = [], matchScore = 0;
  try {
    picks = getBettingPicks(match, odds, leagueKey) || [];
  } catch (e) {
    extraErrors++;
    if (extraErrors <= 3) console.warn(`  [extra] pick error ${match.home} vs ${match.away}: ${e.message}`);
  }
  try {
    matchScore = computeMatchScore(match, leagueKey) || 0;
  } catch (_) {}

  const dateStr = match.date || '';
  const dateIso = (() => {
    if (!dateStr) return fx.date || '';
    try {
      const [d,m,y] = dateStr.split('.');
      return `${y}-${m.padStart(2,'0')}-${d.padStart(2,'0')}`;
    } catch(_) { return fx.date || ''; }
  })();

  output.push({
    league:     meta.key,
    leagueName: meta.name,
    leagueFlag: meta.flag,
    roundsLeft: fx.roundsLeft ?? 99,
    home:       fx.homeTeamName,
    away:       fx.awayTeamName,
    date:       dateStr,
    dateIso,
    eventId:    fx.eventId || null,
    matchScore: Math.round(matchScore * 10) / 10,
    picks: (picks || []).map(p => ({
      market:    p.market    || '',
      marketKey: (marketToKey._home = fx.homeTeamName, marketToKey._away = fx.awayTeamName, marketToKey(p.market || '')),
      icon:      p.icon      || '',
      conf:      p.conf      || 'medium',
      sc:        typeof p.sc === 'number' ? Math.round(p.sc * 1000) / 1000 : 0,
      odds:      p.odds != null ? p.odds : null,
      modelOdds: p.modelOdds != null ? p.modelOdds : null,
      value:     p.value     || null,
      oddsIsEst: p.oddsIsEst || false,
      reason:    p.reason    || '',
      mods:      Array.isArray(p.mods) ? p.mods : [],
      saferAlt:  p.saferAlt  || null,
      boldAlt:   p.boldAlt   || null,
    })),
  });
}

if (extraTotal > 0) {
  console.log(`Extra leagues: +${extraTotal} fixtures (POL/CRO/SUI/BEL/TUR…), ${extraErrors} errors`);
}

fs.writeFileSync(OUTPUT_PATH, JSON.stringify(output, null, 2));
console.log(`\nDone: ${total + extraTotal} fixtures → ${output.length} entries, ${errors + extraErrors} errors`);
console.log(`Output: ${OUTPUT_PATH}`);

// Summary of picks
const withPicks = output.filter(e => e.picks.length > 0);
console.log(`Matches with picks: ${withPicks.length}`);
if (withPicks.length > 0) {
  console.log('Sample (first 3):');
  withPicks.slice(0, 3).forEach(e => {
    console.log(`  ${e.leagueFlag} ${e.home} vs ${e.away} (${e.date})`);
    e.picks.forEach(p => console.log(`    → ${p.market}  [${p.conf}]  odds=${p.odds}`));
  });
}
