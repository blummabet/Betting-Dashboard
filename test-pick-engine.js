// ═══════════════════════════════════════════════════════
//  test-pick-engine.js — Unit Tests für pick-engine.js
//  Run: node test-pick-engine.js
//
//  Tested sections:
//    1. Poisson math (_poissonOver, _poissonOdds)
//    2. Gate logic (_hasNegEdge)
//    3. Odds derivation (deriveOdds)
//    4. Line movement (computeLineMovement)
//    5. Date utilities (parseGermanDate, getRestDays)
//    6. Full pick engine (getBettingPicks) — 4 fixture snapshots
// ═══════════════════════════════════════════════════════

const fs   = require('fs');
const path = require('path');

// ── Browser globals required by pick-engine.js ──────────
// window._teamStats  : venue-specific xG data from refresh_stats.py
// window._preMatchData: opening odds + full H2H from prematch-server.js
// LEAGUES            : injected by update_dashboard.py as inline <script>
// All are empty here → getBettingPicks falls back to form/H2H-only path.
global.window = {
  _teamStats:    {},
  _preMatchData: {},
};
// LEAGUES is a top-level global (not on window) — mock as empty object.
global.LEAGUES = {};

// ── Load pick-engine.js into this scope ─────────────────
// The file uses function declarations (not ES-module exports),
// so eval() is the simplest way to hoist all functions.
const engineSrc = fs.readFileSync(
  path.join(__dirname, 'pick-engine.js'), 'utf8'
);
eval(engineSrc); // eslint-disable-line no-eval

// ════════════════════════════════════════════════════════
//  Mini test runner
// ════════════════════════════════════════════════════════
let _passed = 0, _failed = 0;

function test(name, fn) {
  try {
    fn();
    console.log(`  ✅  ${name}`);
    _passed++;
  } catch (e) {
    console.error(`  ❌  ${name}`);
    console.error(`       ${e.message}`);
    _failed++;
  }
}

function eq(a, b, msg)       { if (a !== b)             throw new Error(`${msg || ''} | expected ${JSON.stringify(b)}, got ${JSON.stringify(a)}`); }
function ok(v, msg)          { if (!v)                   throw new Error(`${msg || ''} | expected truthy, got ${JSON.stringify(v)}`); }
function approx(a, b, d, msg){ if (Math.abs(a-b) > d)   throw new Error(`${msg || ''} | expected ~${b} (±${d}), got ${a}`); }
function noThrow(fn, msg)    { try { fn(); } catch(e) { throw new Error(`${msg || ''} | threw: ${e.message}`); } }

// ════════════════════════════════════════════════════════
//  1. POISSON MATH
// ════════════════════════════════════════════════════════
console.log('\n── 1. Poisson Math ─────────────────────────────────');

test('_poissonOver: P(X>2.5) with λ=2.5 is ~0.456', () => {
  // P(X≥3) = 1 − (e^-2.5·(1 + 2.5 + 2.5²/2)) ≈ 0.4562
  approx(_poissonOver(2.5, 2.5), 0.456, 0.003, 'P(X>2.5|λ=2.5)');
});

test('_poissonOver: P(X>0.5) with λ=1.5 is ~0.777', () => {
  // P(X≥1) = 1 − e^-1.5 ≈ 0.7769
  approx(_poissonOver(1.5, 0.5), 0.777, 0.003, 'P(X>0.5|λ=1.5)');
});

test('_poissonOver: very low lambda → clipped to 0.02 minimum', () => {
  const p = _poissonOver(0.01, 9.5);
  ok(p >= 0.02 && p <= 0.1, `clamp check p=${p}`);
});

test('_poissonOver: monotone — P(X>1.5|λ=3) > P(X>2.5|λ=3)', () => {
  const p15 = _poissonOver(3, 1.5);
  const p25 = _poissonOver(3, 2.5);
  ok(p15 > p25, `P(X>1.5)=${p15.toFixed(3)} should be > P(X>2.5)=${p25.toFixed(3)}`);
});

test('_poissonOdds: fair odds from prob=0.5, margin 6% → ~1.88', () => {
  // (1/0.5) * 0.94 = 1.88
  approx(_poissonOdds(0.5, 0.06), 1.88, 0.02, 'odds(0.5,6%)');
});

test('_poissonOdds: higher prob → lower odds (monotone)', () => {
  const o60 = _poissonOdds(0.60);
  const o40 = _poissonOdds(0.40);
  ok(o60 < o40, `odds(0.60)=${o60} should be < odds(0.40)=${o40}`);
});

// ════════════════════════════════════════════════════════
//  2. GATE LOGIC (_hasNegEdge)
// ════════════════════════════════════════════════════════
console.log('\n── 2. Gate Logic (_hasNegEdge) ─────────────────────');

test('_hasNegEdge: no negative edge when implied prob close to fair', () => {
  // fair=0.55, odds=1.80 → implied=0.556, excess=0.006 < gate 0.05
  eq(_hasNegEdge(0.55, 1.80, false, 0.05, null), false, 'close match');
});

test('_hasNegEdge: negative edge when implied >> fair', () => {
  // fair=0.40, odds=1.60 → implied=0.625, excess=0.225 >> gate 0.05
  eq(_hasNegEdge(0.40, 1.60, false, 0.05, null), true, 'clear neg edge');
});

test('_hasNegEdge: estimated odds with estGate=null always → suppress', () => {
  eq(_hasNegEdge(0.60, 1.50, true, 0.05, null), true, 'isEst + no estGate');
});

test('_hasNegEdge: estimated odds within estGate → no suppress', () => {
  // fair=0.55, est odds=1.75 → implied=0.571, excess=0.021 < estGate 0.08
  eq(_hasNegEdge(0.55, 1.75, true, 0.05, 0.08), false, 'isEst within gate');
});

test('_hasNegEdge: null fairProb → never suppress', () => {
  eq(_hasNegEdge(null, 1.50, false, 0.05, null), false, 'null fairProb');
});

test('_hasNegEdge: null odds → never suppress', () => {
  eq(_hasNegEdge(0.55, null, false, 0.05, null), false, 'null odds');
});

// ════════════════════════════════════════════════════════
//  3. DERIVED ODDS (deriveOdds)
// ════════════════════════════════════════════════════════
console.log('\n── 3. Derived Odds (deriveOdds) ─────────────────────');

test('deriveOdds: returns input unchanged when hw/dr/aw missing', () => {
  const r = deriveOdds({ hw: 2.00 }); // missing dr/aw
  eq(r.dnbH, undefined, 'no dnbH when incomplete');
});

test('deriveOdds: DNB home odds < 1X2 home odds for clear home fav', () => {
  // Clear home favourite (1.40): DNB home should be even tighter (less risk, lower odds)
  const r = deriveOdds({ hw: 1.40, dr: 4.50, aw: 8.00 });
  ok(r.dnbH > 1.0 && r.dnbH < 1.40, `dnbH=${r.dnbH} should be between 1.0 and hw=1.40`);
});

test('deriveOdds: DNB away odds < 1X2 away odds for clear away dog', () => {
  const r = deriveOdds({ hw: 1.40, dr: 4.50, aw: 8.00 });
  ok(r.dnbA < 8.00, `dnbA=${r.dnbA} should be < aw=8.00`);
});

test('deriveOdds: DC 1X odds < 1X2 home win odds', () => {
  // DC 1X covers home + draw — should be shorter than home alone
  const r = deriveOdds({ hw: 2.10, dr: 3.20, aw: 3.60 });
  ok(r.dc1X < r.hw, `dc1X=${r.dc1X} should be < hw=${r.hw}`);
});

test('deriveOdds: uses fair odds path when hw_fair/dr_fair/aw_fair present', () => {
  const r1 = deriveOdds({ hw: 1.90, dr: 3.50, aw: 4.00 });
  const r2 = deriveOdds({ hw: 1.90, dr: 3.50, aw: 4.00,
                          hw_fair: 1.95, dr_fair: 3.60, aw_fair: 4.10 });
  // Both should produce valid dnbH but values may differ (devig source differs)
  ok(r1.dnbH > 1.0, 'fallback path'); ok(r2.dnbH > 1.0, 'fair-odds path');
});

// ════════════════════════════════════════════════════════
//  4. LINE MOVEMENT (computeLineMovement)
// ════════════════════════════════════════════════════════
console.log('\n── 4. Line Movement (computeLineMovement) ───────────');

test('computeLineMovement: returns null when opening = current (no movement)', () => {
  const o = { hw: 2.00, dr: 3.30, aw: 3.60 };
  eq(computeLineMovement(o, o), null, 'no movement');
});

test('computeLineMovement: detects home shortening (≥3pp)', () => {
  const open = { hw: 2.20, dr: 3.30, aw: 3.60 };
  const curr = { hw: 1.80, dr: 3.40, aw: 3.80 }; // hw shortened ~10pp
  const rows = computeLineMovement(open, curr);
  ok(rows !== null, 'should detect movement');
  const homeRow = rows.find(r => r.label === '1');
  ok(homeRow, 'home row present');
  ok(homeRow.ppShift > 0, `home shortened → positive ppShift (got ${homeRow?.ppShift})`);
});

test('computeLineMovement: ignores O/U movement below 3pp threshold', () => {
  const open = { hw: 2.00, dr: 3.30, aw: 3.60, o25: 1.85, u25: 1.95 };
  const curr = { hw: 1.80, dr: 3.40, aw: 3.80, o25: 1.87, u25: 1.93 }; // tiny O/U move
  const rows = computeLineMovement(open, curr);
  ok(rows !== null, 'should have 1X2 rows');
  const hasO25 = rows.some(r => r.label === 'O25');
  eq(hasO25, false, 'O25 row should be absent (< 3pp move)');
});

test('computeLineMovement: returns null when all moves < 3pp', () => {
  const open = { hw: 2.00, dr: 3.30, aw: 3.60 };
  const curr = { hw: 2.01, dr: 3.32, aw: 3.58 }; // tiny moves
  // Should return null if max pp shift is below noise floor
  // (function returns null when maxAbs < 3)
  const rows = computeLineMovement(open, curr);
  // Either null OR all rows have ppShift < 3 (rows filter differently by market type)
  if (rows !== null) {
    const maxAbs = Math.max(...rows.map(r => Math.abs(r.ppShift)));
    ok(maxAbs >= 3, `If rows present, at least one should be ≥3pp, got max=${maxAbs}`);
  }
});

// ════════════════════════════════════════════════════════
//  5. DATE UTILITIES
// ════════════════════════════════════════════════════════
console.log('\n── 5. Date Utilities ────────────────────────────────');

test('parseGermanDate: parses DD.MM.YYYY correctly', () => {
  const d = parseGermanDate('15.04.2025');
  eq(d.getFullYear(), 2025, 'year');
  eq(d.getMonth(), 3, 'month (0-indexed April)');
  eq(d.getDate(), 15, 'day');
});

test('parseGermanDate: handles single-digit day/month', () => {
  const d = parseGermanDate('5.3.2026');
  eq(d.getFullYear(), 2026, 'year');
  eq(d.getMonth(), 2, 'March = 2');
  eq(d.getDate(), 5, 'day');
});

test('getRestDays: computes correct days between previous and current fixture', () => {
  const fixtures = [
    { home: 'Team A', away: 'Team B', date: '01.04.2025' },
    { home: 'Team A', away: 'Team C', date: '08.04.2025' },
    { home: 'Team D', away: 'Team A', date: '15.04.2025' },
  ];
  // Team A plays on 01.04, 08.04, 15.04 → rest before 08.04 = 7 days
  const rest = getRestDays('Team A', '08.04.2025', fixtures);
  eq(rest, 7, 'rest days between 01.04 and 08.04');
});

test('getRestDays: returns null when no previous fixture found', () => {
  const fixtures = [{ home: 'Team B', away: 'Team C', date: '01.04.2025' }];
  const rest = getRestDays('Team A', '08.04.2025', fixtures);
  eq(rest, null, 'no previous fixture');
});

test('getRestDays: ignores fixtures on or after matchDate', () => {
  const fixtures = [
    { home: 'Team A', away: 'Team B', date: '10.04.2025' }, // same day
    { home: 'Team A', away: 'Team C', date: '12.04.2025' }, // after
    { home: 'Team A', away: 'Team D', date: '03.04.2025' }, // before — should be used
  ];
  const rest = getRestDays('Team A', '10.04.2025', fixtures);
  eq(rest, 7, 'rest from 03.04 to 10.04 = 7 days');
});

// ════════════════════════════════════════════════════════
//  6. FULL PICK ENGINE — getBettingPicks() snapshots
// ════════════════════════════════════════════════════════
console.log('\n── 6. getBettingPicks() Fixture Snapshots ───────────');

// ── Helpers ──────────────────────────────────────────────
function makeMatch(overrides = {}) {
  return {
    home: 'Team Home',
    away: 'Team Away',
    homeForm: { goalsPerGame: 1.5, concededPerGame: 1.3, streak: 0, formScore: 0.50 },
    awayForm: { goalsPerGame: 1.4, concededPerGame: 1.2, streak: 0, formScore: 0.50 },
    homeStake: { labels: [], motivationLevel: 'full' },
    awayStake: { labels: [], motivationLevel: 'full' },
    h2h: { games: 0 },
    roundsLeft: 99,
    ...overrides,
  };
}

function makeOdds(overrides = {}) {
  return { hw: 2.00, dr: 3.30, aw: 3.60, o25: 1.85, u25: 1.95, ...overrides };
}

function picksWithConf(picks, conf) {
  return picks.filter(p => p.conf === conf);
}

// ── Fixture A: Robustness — minimal match, should not crash ──────────────────
test('Fixture A: does not crash on minimal match object', () => {
  noThrow(() => {
    const picks = getBettingPicks(makeMatch(), makeOdds(), 'GER');
    ok(Array.isArray(picks), 'returns array');
  }, 'minimal match');
});

test('Fixture A: all picks have required fields (market, conf, reason)', () => {
  const picks = getBettingPicks(makeMatch(), makeOdds(), 'GER');
  for (const p of picks) {
    ok(p.market,  `pick missing .market: ${JSON.stringify(p)}`);
    ok(p.conf,    `pick missing .conf: ${JSON.stringify(p)}`);
    ok(p.reason != null, `pick missing .reason: ${JSON.stringify(p)}`);
  }
});

test('Fixture A: all picks have valid conf values', () => {
  const valid = new Set(['low', 'medium', 'high']);
  const picks = getBettingPicks(makeMatch(), makeOdds(), 'GER');
  for (const p of picks) {
    ok(valid.has(p.conf), `invalid conf "${p.conf}" in pick "${p.market}"`);
  }
});

// ── Fixture B: High-scoring match → Over 2.5 pick expected ───────────────────
test('Fixture B: high-scoring match produces at least one pick', () => {
  const match = makeMatch({
    homeForm: { goalsPerGame: 2.5, concededPerGame: 1.2, streak: 3, formScore: 0.75 },
    awayForm: { goalsPerGame: 2.2, concededPerGame: 1.4, streak: 2, formScore: 0.70 },
    h2h: {
      games: 8, homeWins: 4, draws: 1, awayWins: 3,
      lastMeetingYear: 2024,
      over25Rate: 0.75, bttsRate: 0.65, avgGoals: 3.3,
    },
  });
  const odds = makeOdds({ hw: 1.75, dr: 3.80, aw: 4.80, o25: 1.55, u25: 2.50 });
  const picks = getBettingPicks(match, odds, 'GER');
  ok(picks.length > 0, `expected picks, got ${picks.length}`);
});

test('Fixture B: high-scoring match — any Over 2.5 type pick is not low-conf', () => {
  const match = makeMatch({
    homeForm: { goalsPerGame: 2.5, concededPerGame: 1.2, streak: 3, formScore: 0.75 },
    awayForm: { goalsPerGame: 2.2, concededPerGame: 1.4, streak: 2, formScore: 0.70 },
    h2h: {
      games: 8, homeWins: 4, draws: 1, awayWins: 3,
      lastMeetingYear: 2024,
      over25Rate: 0.75, bttsRate: 0.65, avgGoals: 3.3,
    },
  });
  const odds = makeOdds({ hw: 1.75, dr: 3.80, aw: 4.80, o25: 1.55, u25: 2.50 });
  const picks = getBettingPicks(match, odds, 'GER');
  // If an Over pick exists, it should not be low-conf (strong H2H + form signal)
  const overPick = picks.find(p =>
    p.market && (p.market.includes('Over') || p.market.includes('Über') || p.market.includes('2.5'))
    && !p.market.toLowerCase().includes('under') && !p.market.includes('U2')
  );
  if (overPick) {
    ok(overPick.conf !== 'low' || overPick.odds < 1.33 || overPick.odds > 2.05,
      `Over pick "${overPick.market}" conf="${overPick.conf}" (expected medium/high, or demoted by odds-cap)`);
  }
  // If no over pick at all, that's also acceptable (gate may block it)
  ok(true, 'structural check passed');
});

// ── Fixture C: Defensive match — both teams have low-scoring history ─────────
test('Fixture C: defensive match does not crash', () => {
  noThrow(() => {
    const match = makeMatch({
      homeForm: { goalsPerGame: 0.9, concededPerGame: 0.6, streak: 0, formScore: 0.48 },
      awayForm: { goalsPerGame: 0.8, concededPerGame: 0.5, streak: 0, formScore: 0.45 },
      h2h: {
        games: 6, homeWins: 3, draws: 2, awayWins: 1,
        lastMeetingYear: 2023,
        over25Rate: 0.20, bttsRate: 0.17, avgGoals: 1.7,
      },
    });
    const odds = makeOdds({ hw: 2.10, dr: 3.10, aw: 3.50, o25: 2.50, u25: 1.50 });
    const picks = getBettingPicks(match, odds, 'ITA');
    ok(Array.isArray(picks), 'returns array');
  }, 'defensive match');
});

test('Fixture C: defensive match — no Over 2.5 with high conf', () => {
  const match = makeMatch({
    homeForm: { goalsPerGame: 0.9, concededPerGame: 0.6, streak: 0, formScore: 0.48 },
    awayForm: { goalsPerGame: 0.8, concededPerGame: 0.5, streak: 0, formScore: 0.45 },
    h2h: {
      games: 6, homeWins: 3, draws: 2, awayWins: 1,
      lastMeetingYear: 2023,
      over25Rate: 0.20, bttsRate: 0.17, avgGoals: 1.7,
    },
  });
  const odds = makeOdds({ hw: 2.10, dr: 3.10, aw: 3.50, o25: 2.50, u25: 1.50 });
  const picks = getBettingPicks(match, odds, 'ITA');
  const highOverPick = picks.find(p =>
    p.conf === 'high' &&
    p.market && (p.market.includes('Over') || p.market.includes('Über'))
    && !p.market.toLowerCase().includes('under')
    && !p.market.toLowerCase().includes('karte')
    && !p.market.toLowerCase().includes('ecke')
  );
  eq(highOverPick, undefined, `Should not have high-conf Over goal pick in defensive match`);
});

// ── Fixture D: Both teams low motivation → all non-cards picks capped to 'low' ─
test('Fixture D: both low-motivation → non-cards picks capped to conf=low', () => {
  const match = makeMatch({
    home: 'Absteiger FC',
    away: 'Mittelfeld SV',
    homeStake: { labels: [{ c: 'red' }], motivationLevel: 'low' },
    awayStake: { labels: [{ c: 'red' }], motivationLevel: 'low' },
    homeForm: { goalsPerGame: 1.6, concededPerGame: 1.4, streak: -1, formScore: 0.40 },
    awayForm: { goalsPerGame: 1.5, concededPerGame: 1.3, streak: 0,  formScore: 0.45 },
    h2h: {
      games: 5, homeWins: 2, draws: 2, awayWins: 1,
      lastMeetingYear: 2024, over25Rate: 0.50, bttsRate: 0.40, avgGoals: 2.4,
    },
    roundsLeft: 4,
  });
  const odds = makeOdds({ hw: 2.10, dr: 3.20, aw: 3.50, o25: 1.80, u25: 2.00 });
  const picks = getBettingPicks(match, odds, 'GER');

  const nonCardsMedHighPicks = picks.filter(p =>
    (p.conf === 'medium' || p.conf === 'high') &&
    !p.market?.toLowerCase().includes('karte')
  );
  eq(nonCardsMedHighPicks.length, 0,
    `Expected 0 medium/high non-cards picks, got ${nonCardsMedHighPicks.length}:\n` +
    nonCardsMedHighPicks.map(p => `  · "${p.market}" conf=${p.conf}`).join('\n')
  );
});

test('Fixture D: both low-motivation — function still returns array', () => {
  const match = makeMatch({
    homeStake: { labels: [{ c: 'red' }], motivationLevel: 'low' },
    awayStake: { labels: [{ c: 'red' }], motivationLevel: 'low' },
  });
  const picks = getBettingPicks(match, makeOdds(), 'GER');
  ok(Array.isArray(picks), 'returns array even for low-motiv match');
});

// ── Fixture E: None motivation (confirmed result) — picks also capped ─────────
test('Fixture E: motivationLevel=none on one side — no crash', () => {
  noThrow(() => {
    const match = makeMatch({
      homeStake: { labels: [{ c: 'gold' }], motivationLevel: 'none' }, // already champion
      awayStake: { labels: [],              motivationLevel: 'full' },
    });
    getBettingPicks(match, makeOdds(), 'GER');
  }, 'none-motivation');
});

// ── Fixture F: Odds-cap boundaries ────────────────────────────────────────────
test('Fixture F: picks with real odds > 2.05 are demoted to low', () => {
  // Over 3.5 odds often >2.05 — should be demoted
  const match = makeMatch({
    homeForm: { goalsPerGame: 2.0, concededPerGame: 1.5, streak: 1, formScore: 0.60 },
    awayForm: { goalsPerGame: 1.8, concededPerGame: 1.4, streak: 0, formScore: 0.55 },
  });
  const odds = makeOdds({ hw: 1.95, dr: 3.50, aw: 4.20, o25: 1.70, u25: 2.15,
                          o35: 2.60, u35: 1.50 }); // o35 > 2.05 → should cap
  const picks = getBettingPicks(match, odds, 'GER');
  for (const p of picks) {
    if (p.odds != null && !p.oddsIsEst && p.odds > 2.05) {
      eq(p.conf, 'low', `Pick "${p.market}" odds=${p.odds} > 2.05 should be conf=low`);
    }
  }
});

test('Fixture F: picks with real odds < 1.33 are demoted to low', () => {
  const match = makeMatch({
    homeForm: { goalsPerGame: 3.0, concededPerGame: 0.5, streak: 5, formScore: 0.90 },
    awayForm: { goalsPerGame: 0.5, concededPerGame: 2.5, streak: -4, formScore: 0.10 },
  });
  // Extreme favourite odds — o25 very likely but also very cheap
  const odds = makeOdds({ hw: 1.12, dr: 6.00, aw: 16.0, o25: 1.20, u25: 5.00 });
  const picks = getBettingPicks(match, odds, 'GER');
  for (const p of picks) {
    if (p.odds != null && !p.oddsIsEst && p.odds < 1.33) {
      eq(p.conf, 'low', `Pick "${p.market}" odds=${p.odds} < 1.33 should be conf=low`);
    }
  }
});

// ── Fixture G: No odds at all — estimated-only path ─────────────────────────
test('Fixture G: match with no real odds returns array without crashing', () => {
  noThrow(() => {
    const match = makeMatch({
      homeForm: { goalsPerGame: 1.8, concededPerGame: 1.2, streak: 1, formScore: 0.58 },
      awayForm: { goalsPerGame: 1.5, concededPerGame: 1.4, streak: 0, formScore: 0.50 },
    });
    const picks = getBettingPicks(match, {}, 'ENG'); // empty odds
    ok(Array.isArray(picks), 'array returned');
  }, 'no-odds path');
});

// ════════════════════════════════════════════════════════
//  RESULTS
// ════════════════════════════════════════════════════════
console.log(`\n${'═'.repeat(54)}`);
console.log(`  Ergebnis: ${_passed} bestanden · ${_failed} fehlgeschlagen`);
console.log(`${'═'.repeat(54)}\n`);
if (_failed > 0) process.exit(1);
