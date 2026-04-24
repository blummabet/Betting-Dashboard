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

const BASE         = __dirname;
const HTML_PATH    = path.join(BASE, 'season-finish.html');
const PREMATCH_PATH= path.join(BASE, 'prematch-data.json');
const OUTPUT_PATH  = path.join(BASE, 'picks_output.json');

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
for (const fx of pmFixtures) {
  const h = normTeam(fx.homeTeamName || fx.home || '');
  const a = normTeam(fx.awayTeamName || fx.away || '');
  if (h && a) pmOddsMap[`${h}|${a}`] = fx.odds || {};
}

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

// ── 5. Build vm sandbox with browser API stubs ────────────────────────────────
const mockFetch = () => Promise.resolve({
  json: () => Promise.resolve({}),
  blob: () => Promise.resolve({}),
  ok: true, status: 200,
});

const sandbox = {
  // window — must have fetch so _installCorsProxy can reference it even disabled
  window: {
    fetch: mockFetch,
    _oddsData: {}, _preMatchData: {}, _oddsReady: false, _teamStats: {},
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

// ── 6. Append export line and evaluate ───────────────────────────────────────
script += `\n
// ── Node.js export shim ──
try {
  exports.getBettingPicks  = getBettingPicks;
  exports.computeMatchScore= computeMatchScore;
  exports.deriveOdds       = deriveOdds;
  exports.LEAGUES          = LEAGUES;
} catch(_e) {}
`;

try {
  vm.runInNewContext(script, sandbox);
} catch (e) {
  console.error('VM error:', e.message);
  // Show which line caused the issue
  const lines = e.stack.split('\n');
  lines.slice(0, 8).forEach(l => console.error(l));
  process.exit(1);
}

const { getBettingPicks, computeMatchScore, LEAGUES } = sandbox.exports;
if (!getBettingPicks || !LEAGUES) {
  console.error('Failed to extract getBettingPicks / LEAGUES');
  process.exit(1);
}
console.log(`Leagues found: ${Object.keys(LEAGUES).length}`);

// ── 6b. Market name → marketKey mapping ──────────────────────────────────────
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
  const tgM = m.match(/über\s+(\d+\.?\d*)\s+Tore$/i);
  if (tgM) return `team_goals_over:${tgM[1]}`;

  // Fallback slug
  return ml.replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '') || 'unknown';
}

// ── 7. Run picks for every fixture ───────────────────────────────────────────
const output = [];
let total = 0, errors = 0;

for (const [leagueKey, league] of Object.entries(LEAGUES)) {
  const fixtures = league.fixtures || [];
  for (const match of fixtures) {
    if (!match.home || !match.away) continue;
    total++;

    // Build odds object from prematch-data.json
    const odds = findPrematchOdds(match.home, match.away);

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
        marketKey: marketToKey(p.market || ''),
        icon:      p.icon      || '',
        conf:      p.conf      || 'medium',
        sc:        typeof p.sc === 'number' ? Math.round(p.sc * 1000) / 1000 : 0,
        odds:      p.odds != null ? p.odds : null,
        modelOdds: p.modelOdds != null ? p.modelOdds : null,
        value:     p.value     || null,
        oddsIsEst: p.oddsIsEst || false,
      })),
    });
  }
}

fs.writeFileSync(OUTPUT_PATH, JSON.stringify(output, null, 2));
console.log(`\nDone: ${total} fixtures → ${output.length} entries, ${errors} errors`);
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
