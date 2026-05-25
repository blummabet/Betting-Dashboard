// ═══════════════════════════════════════════════════════
//  polymarket-tab.js — CocoBet Polymarket Tab
//  (Apr 2026)
//
//  Sections:
//    1. Constants — team name map, league/market filters, stake
//    2. State
//    3. Pick collection — getPolyPicks(dateStr)
//    4. Gamma API — fetchGammaPrice(pick)
//    5. UI rendering — pick cards, price blocks, edge display
//    6. Stats — localStorage-based P&L tracker
//    7. Confirmation flow — JSON download, save-as-pending
//    8. Entry point — initPolymarket()
//
//  Runtime deps (provided by the page):
//    · LEAGUES          — injected by update_dashboard.py
//    · getBettingPicks() — from pick-engine.js
//    · findOdds()        — from season-finish-v2.html main script
// ═══════════════════════════════════════════════════════

// ── 1. CONSTANTS ────────────────────────────────────────

const POLY_STAKE = 5; // EUR flat stake per pick

// Leagues covered on Polymarket (skip AUT, HUN, CRO, POL)
const POLY_LEAGUES = new Set(['GER','ENG','ITA','ESP','FRA','NED','POR','TUR','GER2','ENG2','SCO']);

// Markets we can map to Polymarket outcomes.
// Over/Under goals: 1.5, 2.5, 3.5 (Polymarket standard lines).
// Corners: all lines from pick engine (shown when Polymarket offers them; "kein Markt" otherwise).
// DNB, DC, Asian Handicap, HT, Cards, Team Goals: not on Polymarket → excluded.
const POLY_MARKETS = new Set([
  // ── Match result ────────────────────────────────────────
  'Heimsieg', 'Auswärtssieg', 'Unentschieden',
  // ── Goals Over/Under ────────────────────────────────────
  'Over 1.5 Tore', 'Over 2.5 Tore', 'Over 3.5 Tore',
  'Under 1.5 Tore', 'Under 2.5 Tore',
  // ── Both Teams to Score ─────────────────────────────────
  'Beide Teams treffen',
  // ── Corners Over/Under (all pick-engine lines) ──────────
  'Über 6.5 Ecken', 'Über 7.5 Ecken', 'Über 8.5 Ecken',
  'Über 9.5 Ecken', 'Über 10.5 Ecken', 'Über 11.5 Ecken',
  'Unter 6.5 Ecken', 'Unter 7.5 Ecken', 'Unter 8.5 Ecken', 'Unter 9.5 Ecken',
]);

// German dashboard names → English Polymarket names
const TEAM_NAME_MAP = {
  // ── Bundesliga ──────────────────────────────────────
  'Bayern München':           'Bayern Munich',
  'Borussia Dortmund':        'Borussia Dortmund',
  'Bayer Leverkusen':         'Bayer Leverkusen',
  'RB Leipzig':               'RB Leipzig',
  'Eintracht Frankfurt':      'Eintracht Frankfurt',
  'VfB Stuttgart':            'VfB Stuttgart',
  'Borussia Mönchengladbach': "Borussia M'gladbach",
  'SC Freiburg':              'Freiburg',
  '1. FC Union Berlin':       'Union Berlin',
  'VfL Wolfsburg':            'Wolfsburg',
  'TSG Hoffenheim':           'Hoffenheim',
  'Werder Bremen':            'Werder Bremen',
  'FC Augsburg':              'Augsburg',
  '1. FSV Mainz 05':          'Mainz',
  'Mainz 05':                 'Mainz',
  'VfL Bochum':               'Bochum',
  '1. FC Heidenheim':         'Heidenheim',
  'Holstein Kiel':            'Holstein Kiel',
  'FC St. Pauli':             'St. Pauli',
  // ── 2. Bundesliga ───────────────────────────────────
  'Hamburger SV':             'Hamburger SV',
  'Fortuna Düsseldorf':       'Fortuna Dusseldorf',
  '1. FC Köln':               'FC Koln',
  'Hannover 96':              'Hannover 96',
  'Karlsruher SC':            'Karlsruhe',
  'Hertha BSC':               'Hertha Berlin',
  'SpVgg Greuther Fürth':     'Greuther Furth',
  'SC Paderborn':             'Paderborn',
  '1. FC Nürnberg':           'Nuremberg',
  'FC Schalke 04':            'Schalke 04',
  'Darmstadt 98':             'Darmstadt',
  // ── Premier League ──────────────────────────────────
  'Manchester City':          'Manchester City',
  'Arsenal':                  'Arsenal',
  'Liverpool':                'Liverpool',
  'Manchester United':        'Manchester United',
  'Chelsea':                  'Chelsea',
  'Tottenham Hotspur':        'Tottenham Hotspur',
  'Newcastle United':         'Newcastle United',
  'Aston Villa':              'Aston Villa',
  'Brighton & Hove Albion':   'Brighton',
  'Brighton':                 'Brighton',
  'West Ham United':          'West Ham United',
  'Wolverhampton Wanderers':  'Wolverhampton',
  'Crystal Palace':           'Crystal Palace',
  'Nottingham Forest':        'Nottingham Forest',
  'Brentford':                'Brentford',
  'Fulham':                   'Fulham',
  'Everton':                  'Everton',
  'AFC Bournemouth':          'Bournemouth',
  'Bournemouth':              'Bournemouth',
  'Leicester City':           'Leicester City',
  'Ipswich Town':             'Ipswich Town',
  'Southampton':              'Southampton',
  // ── Serie A ─────────────────────────────────────────
  'Inter Mailand':            'Inter Milan',
  'Inter Milan':              'Inter Milan',
  'AC Mailand':               'AC Milan',
  'AC Milan':                 'AC Milan',
  'Juventus':                 'Juventus',
  'Napoli':                   'Napoli',
  'AS Roma':                  'AS Roma',
  'Lazio':                    'Lazio',
  'Atalanta':                 'Atalanta',
  'Fiorentina':               'Fiorentina',
  'Bologna':                  'Bologna',
  'Torino':                   'Torino',
  'Hellas Verona':            'Verona',
  'Genoa':                    'Genoa',
  'Udinese':                  'Udinese',
  'Cagliari':                 'Cagliari',
  'Lecce':                    'Lecce',
  'Empoli':                   'Empoli',
  'Monza':                    'Monza',
  'Como':                     'Como',
  'Venezia':                  'Venezia',
  'Parma':                    'Parma',
  // ── La Liga ─────────────────────────────────────────
  'Real Madrid':              'Real Madrid',
  'FC Barcelona':             'FC Barcelona',
  'Barcelona':                'FC Barcelona',
  'Atletico Madrid':          'Atletico Madrid',
  'Villarreal':               'Villarreal',
  'Athletic Club':            'Athletic Club',
  'Real Sociedad':            'Real Sociedad',
  'Sevilla':                  'Sevilla',
  'Valencia':                 'Valencia',
  'Real Betis':               'Real Betis',
  'Osasuna':                  'Osasuna',
  'Getafe':                   'Getafe',
  'Girona':                   'Girona',
  'Celta Vigo':               'Celta Vigo',
  'RCD Mallorca':             'Mallorca',
  'Mallorca':                 'Mallorca',
  'UD Las Palmas':            'Las Palmas',
  'Las Palmas':               'Las Palmas',
  'Deportivo Alavés':         'Alaves',
  'Rayo Vallecano':           'Rayo Vallecano',
  'Real Valladolid':          'Valladolid',
  'CD Leganés':               'Leganes',
  'Espanyol':                 'Espanyol',
  // ── Ligue 1 ─────────────────────────────────────────
  'Paris Saint-Germain':      'Paris Saint-Germain',
  'PSG':                      'Paris Saint-Germain',
  'Marseille':                'Marseille',
  'Monaco':                   'Monaco',
  'RC Lens':                  'Lens',
  'Lille':                    'Lille',
  'Lyon':                     'Lyon',
  'OGC Nice':                 'Nice',
  'Stade Rennais':            'Rennes',
  'Nantes':                   'Nantes',
  'Strasbourg':               'Strasbourg',
  'Stade de Reims':           'Reims',
  'Montpellier':              'Montpellier',
  'Brest':                    'Brest',
  'Toulouse':                 'Toulouse',
  'Le Havre':                 'Le Havre',
  'Auxerre':                  'Auxerre',
  'Angers':                   'Angers',
  'Saint-Étienne':            'Saint-Etienne',
  // ── Eredivisie ──────────────────────────────────────
  'Ajax':                     'Ajax',
  'PSV Eindhoven':            'PSV Eindhoven',
  'Feyenoord':                'Feyenoord',
  'AZ Alkmaar':               'AZ Alkmaar',
  'FC Utrecht':               'FC Utrecht',
  'FC Twente':                'FC Twente',
  'NEC Nijmegen':             'NEC Nijmegen',
  'Heerenveen':               'Heerenveen',
  'Go Ahead Eagles':          'Go Ahead Eagles',
  'Almere City':              'Almere City',
  'Fortuna Sittard':          'Fortuna Sittard',
  // ── Primeira Liga ───────────────────────────────────
  'Benfica':                  'Benfica',
  'FC Porto':                 'Porto',
  'Porto':                    'Porto',
  'Sporting CP':              'Sporting CP',
  'Braga':                    'Braga',
  'Vitória de Guimarães':     'Guimaraes',
  'Guimarães':                'Guimaraes',
  'Famalicão':                'Famalicao',
  // ── Süper Lig ───────────────────────────────────────
  'Galatasaray':              'Galatasaray',
  'Fenerbahçe':               'Fenerbahce',
  'Fenerbahce':               'Fenerbahce',
  'Beşiktaş':                 'Besiktas',
  'Besiktas':                 'Besiktas',
  'Trabzonspor':              'Trabzonspor',
  'Başakşehir':               'Istanbul Basaksehir',
  'Kasımpaşa':                'Kasimpasa',
  'Antalyaspor':              'Antalyaspor',
  'Sivasspor':                'Sivasspor',
  'Rizespor':                 'Rizespor',
  // ── Scottish Premiership ────────────────────────────
  'Celtic':                   'Celtic',
  'Rangers':                  'Rangers',
  'Hearts':                   'Heart of Midlothian',
  'Hibernian':                'Hibernian',
  'Aberdeen':                 'Aberdeen',
  'Motherwell':               'Motherwell',
  'Dundee United':            'Dundee United',
  'Ross County':              'Ross County',
  'Kilmarnock':               'Kilmarnock',
  'St Mirren':                'St Mirren',
  // ── Championship (ENG2) ─────────────────────────────
  'Leeds':                    'Leeds United',
  'Leeds United':             'Leeds United',
  'Burnley':                  'Burnley',
  'Burnley FC':               'Burnley',
  'Sheffield United':         'Sheffield United',
  'West Brom':                'West Bromwich Albion',
  'West Bromwich Albion':     'West Bromwich Albion',
  'Sunderland':               'Sunderland',
  'Middlesbrough':            'Middlesbrough',
  'Watford':                  'Watford',
  'Blackburn Rovers':         'Blackburn',
  'Blackburn':                'Blackburn',
  'Coventry City':            'Coventry City',
  'Stoke City':               'Stoke City',
  'Cardiff City':             'Cardiff City',
  'Bristol City':             'Bristol City',
  'Norwich City':             'Norwich City',
  'Preston North End':        'Preston',
  'Hull City':                'Hull City',
  'Millwall':                 'Millwall',
  'Luton Town':               'Luton Town',
  'Luton':                    'Luton Town',
  'Derby County':             'Derby County',
  'Portsmouth':               'Portsmouth',
  'Plymouth Argyle':          'Plymouth',
  'Oxford United':            'Oxford United',
  'Swansea City':             'Swansea City',
  'Queens Park Rangers':      'Queens Park Rangers',
  'QPR':                      'Queens Park Rangers',
  'Sheffield Wednesday':      'Sheffield Wednesday',
};

function toEnglishName(name) {
  if (!name) return name;
  return TEAM_NAME_MAP[name] || name; // fallback: pass through unchanged
}

// ── 2. STATE ────────────────────────────────────────────

let _polyState = {
  dateStr:  null,
  picks:    [],
  prices:   {},   // pickId → { found:bool, price:float|null, eventTitle:str }
  selected: new Set(),
};

// ── 3. PICK COLLECTION ──────────────────────────────────

function _todayStr() {
  const n = new Date();
  const d = String(n.getDate()).padStart(2, '0');
  const m = String(n.getMonth() + 1).padStart(2, '0');
  return `${d}.${m}.${n.getFullYear()}`;
}

// Returns all fixture dates that have at least one eligible Polymarket pick, sorted ascending
function _getAvailableDates() {
  if (typeof LEAGUES === 'undefined') return [];
  const dateSet = new Set();
  const today = _todayStr();

  for (const [lk, lg] of Object.entries(LEAGUES)) {
    if (!POLY_LEAGUES.has(lk)) continue;
    for (const fx of (lg.fixtures || [])) {
      if (!fx.date) continue;
      // Only future / today dates
      const [d, m, y] = fx.date.split('.');
      if (new Date(`${y}-${m}-${d}`) < new Date(_todayStr().split('.').reverse().join('-'))) continue;
      dateSet.add(fx.date);
    }
  }

  // Sort DD.MM.YYYY chronologically
  return [...dateSet].sort((a, b) => {
    const [ad, am, ay] = a.split('.');
    const [bd, bm, by] = b.split('.');
    return new Date(`${ay}-${am}-${ad}`) - new Date(`${by}-${bm}-${bd}`);
  });
}

function polyChangeDate(dateStr) {
  _polyState.dateStr  = dateStr;
  // Merge club league picks + WM 2026 picks
  const clubPicks = getPolyPicks(dateStr);
  const wmPicks   = getWmPolyPicks(dateStr);
  _polyState.picks = [...wmPicks, ...clubPicks];  // WM first
  _polyState.prices   = {};
  _polyState.selected = new Set(_polyState.picks.map(p => p.id));
  _polyRefreshStickyBar();

  // Update subtitle
  const sub = document.getElementById('polyDateSub');
  if (sub) sub.textContent = `${dateStr} · ${_polyState.picks.length} eligible pick${_polyState.picks.length !== 1 ? 's' : ''}`;

  // Update status label
  const status = document.getElementById('polyPriceStatus');
  if (status) { status.textContent = '⏳ Polymarket-Preise werden geladen…'; status.style.color = ''; }

  const pickSection = document.getElementById('polyPicksLabel');
  if (pickSection) pickSection.textContent = `Picks — ${_polyState.picks.length} verfügbar`;

  document.getElementById('polyPickGrid').innerHTML = renderPolyPickCards();
  _fetchAllPricesAsync();
}

function getPolyPicks(dateStr) {
  if (typeof LEAGUES === 'undefined') return [];
  const results = [];

  for (const [lk, lg] of Object.entries(LEAGUES)) {
    if (!POLY_LEAGUES.has(lk)) continue;
    for (const fx of (lg.fixtures || [])) {
      if (fx.date !== dateStr) continue;

      const rawOdds = (typeof findOdds === 'function')
        ? findOdds(fx.leagueKey || lk, fx.home, fx.away)
        : null;
      // MUST pass through deriveOdds() before getBettingPicks() — same as renderer.js and generate_picks.js.
      // Without this, pick-engine receives raw {hw,dr,aw} without de-vigged probabilities or
      // derived markets (DC/DNB/AH) → completely wrong picks (wrong markets, wrong lines).
      const odds = (typeof deriveOdds === 'function' && rawOdds)
        ? deriveOdds(rawOdds)
        : rawOdds;

      let picks = [];
      try { picks = getBettingPicks(fx, odds, lk) || []; } catch (e) { /* skip broken fixture */ }

      for (const p of picks) {
        if (!POLY_MARKETS.has(p.market))          continue;
        if (p.conf === 'low')                     continue;

        // For 1X2 and O/U: require real bookie odds (skip estimated — model vs model).
        // For BTTS: allow estimated odds — modelOdds comes from independent Poisson and is
        // valid for comparison against Poly price even when no real bookie quote is available.
        const isBtts = p.market === 'Beide Teams treffen';
        if (!isBtts && (p.oddsIsEst || p.odds == null)) continue;
        if (isBtts && p.modelOdds == null)               continue; // need at least modelOdds

        // ── Negative-edge guard (mirrors renderFixtureCard() belt-and-suspenders) ──
        // Picks where the vig-adjusted edge is < -5pp are suppressed in the card renderer.
        // Apply the SAME check here so Polymarket never shows picks the card doesn't show.
        if (p.modelOdds != null && p.odds != null) {
          const _ep = Math.round(((1 / p.modelOdds) - (1 / p.odds) * 1.03) * 100);
          if (_ep < -5) continue;
        }

        const id = `${lk}|${fx.home}|${fx.away}|${p.market}`;
        results.push({
          id,
          league:      lk,
          leagueFlag:  lg.flag || '🏆',
          leagueName:  lg.name || lk,
          home:        fx.home,
          away:        fx.away,
          market:      p.market,
          conf:        p.conf,
          sc:          p.sc,
          odds:        p.odds,        // null/estimated for BTTS — use modelOdds for edge
          modelOdds:   p.modelOdds,
          oddsIsEst:   p.oddsIsEst || false,
          date:        fx.date,
          // ── Verdict & context fields (mirrors renderer.js pick cards) ──────────
          mods:        p.mods        || [],
          saferAlt:    p.saferAlt    || null,
          boldAlt:     p.boldAlt     || null,
          oddsOpen:    fx.odds_open  || null,   // for market-movement signal
          h2h:         fx.h2h        || null,   // for H2H story signal
        });
      }
    }
  }

  // Sort: high conf first, then by sc descending
  results.sort((a, b) => {
    if (a.conf !== b.conf) return a.conf === 'high' ? -1 : 1;
    return b.sc - a.sc;
  });
  return results;
}

// ── WM 2026 PICKS für Polymarket ────────────────────────────────────────────────
// Liest WM Picks aus window.WM2026_PICKS_FOR_POLY (von season-finish-v2.html befüllt)
// Format pro Entry: { pickKey, home, away, homeFlag, awayFlag, date, market, odds,
//                    modelOdds, verdict, edgePP, clvPP, dataQuality, conf }

const WM_MARKET_TO_POLY = {
  'Heimsieg':                 'Heimsieg',
  'Auswärtssieg':             'Auswärtssieg',
  'Unentschieden':            'Unentschieden',
  'Über 2.5 Tore':            'Over 2.5 Tore',
  'Unter 2.5 Tore':           'Under 2.5 Tore',
  'Beide Teams treffen — Ja': 'Beide Teams treffen',
};

function getWmPolyPicks(dateStr) {
  const raw = (typeof window !== 'undefined' && window.WM2026_PICKS_FOR_POLY) || [];
  if (!raw.length) return [];

  const results = [];

  for (const entry of raw) {
    // Date filter (WM dates are YYYY-MM-DD, Poly tab uses DD.MM.YYYY)
    const [y, m, d] = (entry.date || '').split('-');
    const entryDateFmt = (y && m && d) ? `${d}.${m}.${y}` : null;
    if (dateStr && entryDateFmt && entryDateFmt !== dateStr) continue;

    // Only BET and ABWÄGEN
    if (!['BET', 'ABWÄGEN'].includes(entry.verdict)) continue;

    // Map market name to Polymarket equivalent
    const polyMarket = WM_MARKET_TO_POLY[entry.market];
    if (!polyMarket) continue;   // DNB, etc. — not on Polymarket

    // Edge vs Pinnacle (not model): (1/pinnacleOdds) - polyPrice
    // Shown in _edgeBlock() using pick.odds (Pinnacle quote from TheOddsAPI)
    const id = `WM2026|${entry.home}|${entry.away}|${polyMarket}`;

    // CLV badge text
    const clvPP = entry.clvPP || 0;
    const clvBadge = clvPP >= 3
      ? `<span title="Pinnacle Line Movement: Sharp Money bestätigt" style="background:#3fb95022;border:1px solid #3fb95044;color:#3fb950;font-size:9px;padding:1px 5px;border-radius:8px;font-weight:700">CLV +${clvPP}pp ↑</span>`
      : clvPP <= -3
        ? `<span title="Linie gegen Pick-Richtung bewegt" style="background:#f8514922;border:1px solid #f8514944;color:#f85149;font-size:9px;padding:1px 5px;border-radius:8px;font-weight:700">CLV ${clvPP}pp ↓</span>`
        : '';

    const dataWarning = entry.dataQuality === 'elo_only'
      ? `<span title="Nur Elo-Daten — Form/H2H fehlen" style="background:#e3b34122;border:1px solid #e3b34144;color:#e3b341;font-size:9px;padding:1px 5px;border-radius:8px">⚠️ Elo only</span>`
      : '';

    results.push({
      id,
      league:      'WM2026',
      leagueFlag:  '🏆',
      leagueName:  'WM 2026',
      home:        entry.home,
      away:        entry.away,
      homeId:      entry.homeId || null,
      awayId:      entry.awayId || null,
      homeFlag:    entry.homeFlag || '',
      awayFlag:    entry.awayFlag || '',
      market:      polyMarket,
      conf:        entry.verdict === 'BET' ? 'high' : 'medium',
      sc:          entry.edgePP || 0,
      odds:        entry.odds,          // Pinnacle/bookmaker odds — edge reference
      modelOdds:   entry.modelOdds,
      oddsIsEst:   false,
      date:        entry.date,
      dateFmt:     entryDateFmt,
      clvPP:       clvPP,
      dataQuality: entry.dataQuality || 'elo_only',
      verdict:     entry.verdict,
      edgePP:      entry.edgePP || 0,
      mods:        [clvBadge, dataWarning].filter(Boolean),
      saferAlt:    null,
      boldAlt:     null,
      oddsOpen:    null,
      h2h:         null,
      isWm:        true,
    });
  }

  results.sort((a, b) => {
    if (a.verdict !== b.verdict) return a.verdict === 'BET' ? -1 : 1;
    return b.sc - a.sc;
  });
  return results;
}

// ── 4. POLYMARKET PRICES (from server-cached JSON) ──────
//
// Prices are fetched server-side by fetch_poly_prices.py (GitHub Actions)
// and stored in polymarket_prices.json — no CORS proxy needed.
//
// Cache shape:
// {
//   fetched: "2026-05-01T06:00:00Z",
//   matches: {
//     "Leeds|Burnley": {
//       found: true, eventTitle: "...", eventUrl: "...",
//       markets: { "Heimsieg": 0.62, "Over 2.5 Tore": 0.55, ... }
//     }
//   }
// }

let _polyPriceCache = null;   // null = not loaded, {} = loaded (may be empty)
let _polyPriceFetched = null; // ISO timestamp of last server fetch
let _polyPriceMissing = false;// true when polymarket_prices.json returned 404

async function _loadPolyPriceCache() {
  if (_polyPriceCache !== null) return;
  try {
    // Cache-buster prevents CDN (GitHub Pages) from serving stale JSON.
    // Date-rounded to the hour so the CDN doesn't get hammered on every second.
    const _cbv = Math.floor(Date.now() / 3600000);
    const res = await fetch(`polymarket_prices.json?v=${_cbv}`, { cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    _polyPriceCache  = data.matches || {};
    _polyPriceFetched = data.fetched || null;
    console.log(`[Poly] Cache loaded: ${Object.keys(_polyPriceCache).length} matches, fetched ${_polyPriceFetched}`);
  } catch (e) {
    console.warn('[Poly] polymarket_prices.json not available:', e.message);
    _polyPriceCache = {};
    _polyPriceMissing = true;
  }
}

// ── WM 2026 Polymarket Prices (from fetch_wm_poly_prices.py → wm_poly_prices.json) ──
// Keyed by "{HOME_ID}-{AWAY_ID}" e.g. "GER-CUW"
// hw/dr/aw are probabilities (0-1), convert to odds with 1/p
let _wmPolyPriceCache   = null;  // null = not loaded; keyed by "HOME-AWAY"
let _wmPolyPriceMissing = false;
let _wmClvRadar         = [];    // filtered ≥5pp — kept for legacy position logger
let _wmAllFixtures      = [];    // all 72 games with Pinnacle + Poly + edge
let _wmGeneratedAt      = '';    // timestamp from wm_poly_prices.json
let _wmTableFilter      = 'edge3'; // default filter: show edge ≥ 3pp

async function _loadWmPolyPriceCache() {
  if (_wmPolyPriceCache !== null) return;
  try {
    const _cbv = Math.floor(Date.now() / 3600000);
    const res = await fetch(`wm_poly_prices.json?v=${_cbv}`, { cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    _wmPolyPriceCache = data.prices       || {};
    _wmClvRadar       = data.clvRadar     || [];
    _wmAllFixtures    = data.allFixtures  || [];
    _wmGeneratedAt    = data.generatedAt  || '';
    console.log(`[Poly] WM prices loaded: ${_wmAllFixtures.length} fixtures, ` +
      `${_wmAllFixtures.filter(f=>f.hasPinnacle).length} with Pinnacle, ` +
      `${data.generatedAt || ''}`);
  } catch (e) {
    console.warn('[Poly] wm_poly_prices.json not available:', e.message);
    _wmPolyPriceCache = {};
    _wmPolyPriceMissing = true;
  }
}

function _setWmFilter(f) {
  _wmTableFilter = f;
  // WM table lives in the Trading tab — re-render the WM section there
  const wmSection = document.getElementById('wmMarketSection');
  if (wmSection) {
    wmSection.innerHTML = _renderWmMarketTable();
  }
}

// Maps our WM market label → which price field in wm_poly_prices.json
const WM_MARKET_TO_PRICE_KEY = {
  'Heimsieg':              'hw',
  'Auswärtssieg':          'aw',
  'Unentschieden':         'dr',
  'Over 2.5 Tore':         'poly_o25',
  'Under 2.5 Tore':        'poly_u25',
  'Over 1.5 Tore':         'poly_o15',
  'Over 3.5 Tore':         'poly_o35',
  'Beide Teams treffen':   'poly_btts',
};

function _getWmPolyPrice(pick) {
  // pick.homeId, pick.awayId, pick.market must be set
  if (!_wmPolyPriceCache || !pick.homeId || !pick.awayId) return null;
  const key    = `${pick.homeId}-${pick.awayId}`;
  const entry  = _wmPolyPriceCache[key];
  if (!entry) return { found: false, stale: true };

  const mkey   = WM_MARKET_TO_PRICE_KEY[pick.market];
  if (!mkey) return { found: false };  // unmapped market

  const price  = entry[mkey];
  if (price == null || price <= 0) return { found: false };

  // O/U and BTTS markets live in the -more-markets slug
  const isOuBtts = ['poly_o25','poly_u25','poly_o15','poly_o35','poly_btts'].includes(mkey);
  const slug = isOuBtts && entry.moreMktSlug ? entry.moreMktSlug : entry.slug;

  return {
    found:      true,
    price,                           // probability 0-1
    eventUrl:   `https://polymarket.com/de/sports/fifa-world-cup/${slug}`,
    eventTitle: entry.title || `${pick.home} vs ${pick.away}`,
    vol:        entry.vol,
  };
}

// Polymarket price sanity check + normalisation.
//
// Background: Polymarket structures soccer 1X2 as THREE separate binary markets
// ("Will Home win?", "Draw?", "Will Away win?"). The YES-prices from three
// independent binary markets don't necessarily sum to 1.0 — they can be up to
// ~1.30 when markets are lightly traded or not yet arbitraged.
// This is NOT a data error; the prices are real and tradeable. We normalise them
// so the displayed implied probability and edge are correct.
//
// Truly corrupted data (sum > 1.40 or sum < 0.80) is still rejected.
//
// Returns { clean: bool, normalised: object } where normalised is a copy of
// entry.markets with 1X2 prices divided by their sum (when sum ≠ 1.0).
function _sanitisePolyEntry(entry) {
  const m = Object.assign({}, entry.markets || {});
  const h = m['Heimsieg'], x = m['Unentschieden'], a = m['Auswärtssieg'];
  const o = m['Over 2.5 Tore'], u = m['Under 2.5 Tore'];

  // O/U binary markets: must sum exactly to ~1.0 (no normalisation needed/possible)
  if (o != null && u != null) {
    const sumOU = o + u;
    if (sumOU < 0.90 || sumOU > 1.10) return { clean: false };
  }

  // 1X2: normalise if sum is between 0.80 and 1.40 (typical for separate binary markets)
  if (h != null && x != null && a != null) {
    const sum1x2 = h + x + a;
    if (sum1x2 < 0.80 || sum1x2 > 1.40) return { clean: false };  // truly corrupt
    if (sum1x2 < 0.95 || sum1x2 > 1.05) {
      // Normalise — prices are from separate binary markets, not arbitraged yet
      m['Heimsieg']      = h / sum1x2;
      m['Unentschieden'] = x / sum1x2;
      m['Auswärtssieg']  = a / sum1x2;
      return { clean: true, normalised: m, wasNormalised: true };
    }
  }
  return { clean: true, normalised: m, wasNormalised: false };
}

// Retrieve price for a single pick from the cached JSON.
// Returns { found, price, eventTitle, eventUrl } or null.
// Returns { found: false, corrupted: true } when the match prices fail the sanity check.
// Returns { found: false, gameFound: true, eventUrl } when the game exists on Poly but
//   the specific market line isn't available (e.g. pick is Over 2.5 but Poly only has 4.5).
function _getPriceFromCache(pick) {
  if (!_polyPriceCache) return null;
  const key = `${pick.home}|${pick.away}`;
  const entry = _polyPriceCache[key];
  // Key not in cache at all → cache is stale/incomplete, NOT confirmed "kein Markt"
  if (entry === undefined) return { found: false, stale: true };
  if (!entry.found) return { found: false };

  // Sanity check + normalisation: Poly stores 1X2 as 3 separate binary markets → prices
  // can sum to 1.20+ when not yet arbitraged. Normalise rather than reject.
  // Skip sanity check for corners/cards (separate Poly markets, 1X2 sum irrelevant).
  const isCornerOrCard = pick.market && (
    pick.market.startsWith('Über ') || pick.market.startsWith('Unter ') ||
    pick.market.includes('Ecken')   || pick.market.includes('Karten') ||
    pick.market.includes('Corner')
  );
  let _markets = entry.markets || {};
  if (!isCornerOrCard) {
    const _san = _sanitisePolyEntry(entry);
    if (!_san.clean) return { found: false, corrupted: true };
    _markets = _san.normalised || _markets;
  }

  const price = _markets[pick.market];
  // Game is on Polymarket but this specific market line isn't available
  // (e.g. pick = Over 2.5 but Poly only offers O/U 4.5).
  // Don't treat as "kein Markt" — show a link so the user can still open the game.
  if (price == null) {
    return { found: false, gameFound: true, eventUrl: entry.eventUrl || 'https://polymarket.com/' };
  }
  return {
    found:      true,
    price:      price,
    eventTitle: entry.eventTitle || '',
    eventUrl:   entry.eventUrl   || 'https://polymarket.com/',
  };
}

// ── 5. UI RENDERING ─────────────────────────────────────

function _confBadge(conf) {
  const map = {
    high:   { bg: '#3fb95022', border: '#3fb95044', color: '#3fb950', label: 'HIGH' },
    medium: { bg: '#f5c51822', border: '#f5c51844', color: '#f5c518', label: 'MED'  },
    low:    { bg: '#8b949e22', border: '#8b949e44', color: '#8b949e', label: 'LOW'  },
  };
  const c = map[conf] || map.low;
  return `<span style="font-size:10px;font-weight:700;padding:2px 8px;border-radius:10px;background:${c.bg};color:${c.color};border:1px solid ${c.border};letter-spacing:.3px">${c.label}</span>`;
}

function _marketIcon(market) {
  if (!market) return '📊';
  if (market === 'Heimsieg')             return '🏠';
  if (market === 'Auswärtssieg')         return '✈️';
  if (market === 'Unentschieden')        return '🤝';
  if (market === 'Beide Teams treffen')  return '⚽';
  if (market.startsWith('Over'))         return '⚽';
  if (market.startsWith('Under'))        return '🔒';
  if (market.startsWith('Über'))         return '🚩';  // corners over
  if (market.startsWith('Unter'))        return '🛡️'; // corners under
  return '📊';
}

function _marketColor(market) {
  if (!market) return '#8b949e';
  if (market === 'Heimsieg')          return '#58a6ff';
  if (market === 'Auswärtssieg')      return '#f5c518';
  if (market === 'Unentschieden')     return '#a78bfa';
  if (market === 'Beide Teams treffen') return '#a78bfa';
  if (market.startsWith('Over'))      return '#3fb950';  // goals over
  if (market.startsWith('Under'))     return '#f85149';  // goals under
  if (market.startsWith('Über'))      return '#3fb950';  // corners over
  if (market.startsWith('Unter'))     return '#f85149';  // corners under
  return '#8b949e';
}

function _priceBlock(pickId) {
  const p = _polyState.prices[pickId];
  if (p === undefined)        return `<span style="color:#8b949e;font-size:12px">—</span>`;
  if (p.loading)              return `<span style="color:#8b949e;font-size:12px">⏳</span>`;
  if (!p.found && p.stale)      return `<span style="color:#e3b341;font-size:12px">⟳ neu laden</span>`;
  if (!p.found && p.corrupted) return `<span style="color:#f85149;font-size:11px" title="Poly-Preise für dieses Spiel summieren nicht auf 100% — AMM-Fehler, nicht handelbar">⚠️ Preise ungültig</span>`;
  if (!p.found && p.gameFound) return `<span style="color:#8b949e;font-size:12px" title="Spiel auf Polymarket, aber diese spezifische Linie nicht verfügbar">andere Linie</span>`;
  if (!p.found)                return `<span style="color:#8b949e;font-size:12px">kein Markt</span>`;
  const pct      = Math.round(p.price * 100);
  const polyOdds = (1 / p.price).toFixed(2);
  return `<span style="color:#a78bfa;font-weight:700;font-size:15px">${pct}¢</span> <span style="color:#8b949e;font-size:11px">(${polyOdds})</span>`;
}

function _edgeBlock(pick, pickId) {
  const p = _polyState.prices[pickId];
  const refOdds = pick.oddsIsEst ? pick.modelOdds : pick.odds;
  // Stale = match exists in our picks but wasn't in the price cache → cache not yet refreshed
  if (p && p.stale) return `<span style="color:#8b949e;font-size:11px" title="Polymarket-Preis noch nicht gecheckt — läuft 4x täglich via GitHub Action">⏳ n.v.</span>`;
  if (!p || !p.found || !refOdds) return `<span style="color:#8b949e;font-size:12px">—</span>`;
  const ourImplied = 1 / refOdds;
  // Positive = Poly gibt bessere Odds als der Bookie (niedrigere implizite Wahrsch. = höhere Quoten)
  const edgePp = Math.round((ourImplied - p.price) * 100);
  if (Math.abs(edgePp) < 1) return `<span style="color:#8b949e;font-size:12px">≈ 0%</span>`;
  const col  = edgePp > 0 ? '#3fb950' : '#f85149';
  const sign = edgePp > 0 ? '+' : '';
  // Distinguish: real bookie edge vs model-only edge (no independent bookie confirmation)
  if (pick.oddsIsEst) {
    return `<span style="color:${col};font-size:13px;font-weight:700">${sign}${edgePp}pp</span>`
         + `<span style="color:#8b949e;font-size:10px;margin-left:3px" title="Edge basiert auf Poisson-Modell, nicht auf Bookie-Quote">~Modell</span>`;
  }
  return `<span style="color:${col};font-size:13px;font-weight:700">${sign}${edgePp}pp</span>`;
}

function _openButtonHtml(pickId) {
  const pd = _polyState.prices[pickId];
  if (!pd || pd.loading) {
    return `<div style="height:32px"></div>`;
  }
  if (!pd.found && pd.stale) {
    return `<div style="text-align:center;font-size:11px;color:#e3b34188;padding:6px 0">⟳ Cache veraltet — Preise neu laden</div>`;
  }
  if (!pd.found && pd.corrupted) {
    return `<div style="text-align:center;font-size:11px;color:#f8514988;padding:6px 0">⚠️ AMM-Preisfehler — Markt nicht handelbar</div>`;
  }
  if (!pd.found && pd.gameFound && pd.eventUrl) {
    return `<a href="${pd.eventUrl}" target="_blank" rel="noopener"
      onclick="event.stopPropagation()"
      style="display:flex;align-items:center;justify-content:center;gap:6px;
             background:#8b949e11;border:1px solid #8b949e33;border-radius:8px;
             color:#8b949e;font-size:12px;font-weight:700;padding:8px;
             text-decoration:none;transition:background .15s"
      onmouseover="this.style.background='#8b949e22'"
      onmouseout="this.style.background='#8b949e11'">
      🔗 Auf Polymarket öffnen (andere Linie)
    </a>`;
  }
  if (!pd.found || !pd.eventUrl) {
    return `<div style="text-align:center;font-size:11px;color:#8b949e44;padding:6px 0">kein Polymarket-Markt gefunden</div>`;
  }
  return `<a href="${pd.eventUrl}" target="_blank" rel="noopener"
    onclick="event.stopPropagation()"
    style="display:flex;align-items:center;justify-content:center;gap:6px;
           background:#a78bfa22;border:1px solid #a78bfa55;border-radius:8px;
           color:#a78bfa;font-size:12px;font-weight:700;padding:8px;
           text-decoration:none;transition:background .15s"
    onmouseover="this.style.background='#a78bfa33'"
    onmouseout="this.style.background='#a78bfa22'">
    🔗 Auf Polymarket öffnen
  </a>`;
}

// ── Verdict block (BET / ABWÄGEN / SKIP) ────────────────────────────────────
// Delegates to pick-verdict.js › computeVerdict() — single source of truth.
function _verdictBlock(pick) {
  const _eff = (pick.oddsIsEst || !pick.odds) ? pick.modelOdds : pick.odds;
  const _vd = computeVerdict({
    modelOdds: pick.modelOdds,
    odds:      _eff,
    oddsIsEst: pick.oddsIsEst,
    market:    pick.market,
    oddsOpen:  pick.oddsOpen,
    h2h:       pick.h2h,
  });
  const { modEmoji, modTxt, mktEmoji, mktTxt, storyEmoji, storyTxt, verdict, vColor, vBg, vBorder } = _vd;
  return `<div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:10px;font-size:11px;line-height:1.4">
    <span>${modEmoji} <span style="color:#8b949e">Modell</span> <strong style="color:#c9d1d9">${modTxt}</strong></span>
    <span style="color:#30363d">·</span>
    <span>${mktEmoji} <span style="color:#8b949e">Markt</span> <strong style="color:#c9d1d9">${mktTxt}</strong></span>
    <span style="color:#30363d">·</span>
    <span>${storyEmoji} <span style="color:#8b949e">H2H</span> <strong style="color:#c9d1d9">${storyTxt}</strong></span>
    <span style="margin-left:auto;background:${vBg};color:${vColor};border:1px solid ${vBorder};border-radius:6px;padding:2px 9px;font-weight:800;letter-spacing:.4px">${verdict}</span>
  </div>`;
}

// SaferAlt / BoldAlt — only show when the alternative market exists on Polymarket
function _altBlock(pick) {
  if (pick.saferAlt && POLY_MARKETS.has(pick.saferAlt.market)) {
    return `<div style="background:rgba(63,185,80,0.06);border:1px solid rgba(63,185,80,0.25);border-radius:6px;padding:6px 10px;margin-bottom:8px;font-size:11px">
      <span style="color:#3fb950;font-weight:700">✓ Sicherer:</span>
      <span style="color:#e6edf3;margin-left:4px">${pick.saferAlt.market}</span>
      <span style="color:#8b949e;margin-left:4px">@ ~${pick.saferAlt.estOdds.toFixed(2)}</span>
      <span style="color:#8b949e;font-size:10px;margin-left:2px">(Modell-Näherung)</span>
    </div>`;
  }
  if (pick.boldAlt && POLY_MARKETS.has(pick.boldAlt.market)) {
    return `<div style="background:rgba(227,179,65,0.06);border:1px solid rgba(227,179,65,0.25);border-radius:6px;padding:6px 10px;margin-bottom:8px;font-size:11px">
      <span style="color:#e3b341;font-weight:700">📈 Mehr Value:</span>
      <span style="color:#e6edf3;margin-left:4px">${pick.boldAlt.market}</span>
      <span style="color:#8b949e;margin-left:4px">@ ~${pick.boldAlt.estOdds.toFixed(2)}</span>
      <span style="color:#8b949e;font-size:10px;margin-left:2px">(Modell-Näherung)</span>
    </div>`;
  }
  return '';
}

function _renderPickCard(pick) {
  const isSel      = _polyState.selected.has(pick.id);
  const priceData  = _polyState.prices[pick.id];
  // noMarket = Poly hat dieses Spiel explizit nicht; stale = Cache war veraltet, kein Urteil möglich
  // corrupted = AMM-Preisfehler (1X2-Summe weit von 1.0) → ebenfalls ausgegraut
  // gameFound = Spiel auf Poly, aber spezifische Linie fehlt → NICHT ausgegraut (Link zeigen)
  const noMarket   = priceData && !priceData.loading && !priceData.found && !priceData.stale && !priceData.gameFound;
  const mktColor   = _marketColor(pick.market);

  // ── Already-placed check ─────────────────────────────────────────────────────
  // Check by ID, then by home|away|market (IDs may differ between save sources),
  // then session memory fallback.
  const _norm = s => (s || '').toLowerCase().replace(/[^a-z0-9]/g, '');
  const _allBets = _getPolyBets();
  const _placedBet = _allBets.find(b => b.id === pick.id)
    || _allBets.find(b => _norm(b.home) === _norm(pick.home)
                       && _norm(b.away) === _norm(pick.away)
                       && _norm(b.market) === _norm(pick.market))
    || (window._polyPlacedThisSession?.[pick.id] || null);
  const isPlaced   = !!_placedBet;
  const _placedResult = _placedBet?.result; // null = pending, 'won'/'lost' etc = resolved

  if (isPlaced) {
    const resIcon  = _placedResult === 'won'  ? '✅ Gewonnen'
                   : _placedResult === 'lost' ? '❌ Verloren'
                   : _placedResult === 'void' ? '〇 Void'
                   : '⏳ Ausstehend';
    const resCol   = _placedResult === 'won'  ? '#3fb950'
                   : _placedResult === 'lost' ? '#f85149'
                   : '#8b949e';
    const polyPriceStr = _placedBet.polyPrice
      ? `${Math.round(_placedBet.polyPrice * 100)}¢ · ${(1 / _placedBet.polyPrice).toFixed(2)}`
      : '—';
    return `<div class="poly-pick-card poly-no-market"
         data-id="${pick.id}"
         style="opacity:.75;cursor:default;position:relative">
      <!-- Placed banner -->
      <div style="position:absolute;top:10px;right:10px;background:${_placedResult ? (_placedResult==='won'?'#1a3a24':'#3a1a1a') : '#1a2340'};border:1px solid ${_placedResult ? resCol+'55' : '#a78bfa55'};border-radius:6px;padding:3px 8px;font-size:11px;font-weight:700;color:${_placedResult ? resCol : '#a78bfa'}">
        ${_placedResult ? resIcon : '🟣 Platziert'}
      </div>
      <!-- League -->
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
        <span style="font-size:16px">${pick.leagueFlag}</span>
        <span style="font-size:10px;color:#8b949e;font-weight:700;text-transform:uppercase;letter-spacing:.5px">${pick.leagueName}</span>
      </div>
      <!-- Match -->
      <div style="font-size:14px;font-weight:700;margin-bottom:8px;line-height:1.3;color:#e6edf3">
        ${pick.home} <span style="color:#8b949e;font-weight:400;font-size:12px">vs</span> ${pick.away}
      </div>
      <!-- Market + conf -->
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px">
        <span style="font-size:13px">${_marketIcon(pick.market)}</span>
        <span style="font-size:13px;font-weight:600;color:${mktColor}">${pick.market}</span>
        ${_confBadge(pick.conf)}
      </div>
      <!-- Bet summary row -->
      <div style="background:#0d1117;border-radius:8px;padding:10px 12px;font-size:12px;color:#8b949e;display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
        <span>€${_placedBet.stake ?? POLY_STAKE} gesetzt · Poly: ${polyPriceStr}</span>
        <span style="color:${resCol};font-weight:700">${_placedResult ? resIcon : '⏳'}</span>
      </div>
      ${_openButtonHtml(pick.id)}
    </div>`;
  }

  return `<div class="poly-pick-card${isSel ? ' poly-selected' : ''}${noMarket ? ' poly-no-market' : ''}"
       data-id="${pick.id}"
       onclick="polyTogglePick('${pick.id.replace(/'/g, "\\'")}')">
    <!-- League + checkbox -->
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
      <span style="font-size:16px">${pick.leagueFlag}</span>
      <span style="font-size:10px;color:#8b949e;font-weight:700;text-transform:uppercase;letter-spacing:.5px">${pick.leagueName}</span>
      <span style="margin-left:auto;font-size:16px;opacity:${noMarket ? '.3' : '1'}">${isSel ? '☑️' : '⬜'}</span>
    </div>
    <!-- Match -->
    <div style="font-size:14px;font-weight:700;margin-bottom:8px;line-height:1.3;color:#e6edf3">
      ${pick.home} <span style="color:#8b949e;font-weight:400;font-size:12px">vs</span> ${pick.away}
    </div>
    <!-- Market + conf -->
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
      <span style="font-size:13px">${_marketIcon(pick.market)}</span>
      <span style="font-size:13px;font-weight:600;color:${mktColor}">${pick.market}</span>
      ${_confBadge(pick.conf)}
    </div>
    <!-- Verdict (BET / ABWÄGEN / SKIP) — mirrors renderer.js 3-signal logic -->
    ${_verdictBlock(pick)}
    <!-- Mods chips -->
    ${(pick.mods?.length) ? `<div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:8px">${pick.mods.join('')}</div>` : ''}
    <!-- SaferAlt / BoldAlt (only if market is on Polymarket) -->
    ${_altBlock(pick)}
    <!-- Price grid -->
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:0;background:#0d1117;border-radius:8px;overflow:hidden;margin-bottom:10px">
      <div style="padding:10px;text-align:center">
        <div style="font-size:9px;color:#8b949e;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Bookie</div>
        <div style="font-size:15px;font-weight:700;color:#e6edf3">${pick.odds ?? '—'}</div>
      </div>
      <div style="padding:10px;text-align:center;border-left:1px solid #1c2128;border-right:1px solid #1c2128">
        <div style="font-size:9px;color:#8b949e;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Polymarket</div>
        <div>${_priceBlock(pick.id)}</div>
      </div>
      <div style="padding:10px;text-align:center">
        <div style="font-size:9px;color:#8b949e;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Edge</div>
        <div>${_edgeBlock(pick, pick.id)}</div>
      </div>
    </div>
    <!-- Open on Polymarket button -->
    ${_openButtonHtml(pick.id)}
  </div>`;
}

// ── WM 2026 Position Logger (localStorage-backed) ─────────────────────────
// Positions survive page reloads. Export to JSON for the GitHub Action to pick up.
const _WM_POS_KEY = 'wmPolyPositions_v2';
function _loadWmPos()    { try { return JSON.parse(localStorage.getItem(_WM_POS_KEY)||'[]'); } catch(_){ return []; } }
function _saveWmPos(arr) { localStorage.setItem(_WM_POS_KEY, JSON.stringify(arr)); }
function _addWmPos(pos)  {
  const a = _loadWmPos();
  a.push({ ...pos, id: Date.now(), status: 'open', openedAt: new Date().toISOString() });
  _saveWmPos(a);
}
function _closeWmPos(id) {
  _saveWmPos(_loadWmPos().map(p => p.id === id
    ? { ...p, status: 'closed', closedAt: new Date().toISOString() }
    : p));
}

function _openLogPositionModal(data) {
  // data: { home, away, market, priceKey, polyPrice, pinnFair, slug }
  let overlay = document.getElementById('wmPosModal');
  if (!overlay) return;
  overlay._posData = data;
  document.getElementById('wmPosTitle').textContent = `${data.home} vs ${data.away} — ${data.market}`;
  document.getElementById('wmPosEntry').value   = data.polyPrice.toFixed(4);
  document.getElementById('wmPosStake').value   = String(_getStakeForEdge(data.edge ?? 0));
  document.getElementById('wmPosPinnFair').value = data.pinnFair.toFixed(4);
  document.getElementById('wmPosSlug').value    = data.slug;
  document.getElementById('wmPosPriceKey').value = data.priceKey;
  overlay.style.display = 'flex';
  document.getElementById('wmPosStake').focus();
}

function _closeWmPosModal() {
  const o = document.getElementById('wmPosModal');
  if (o) o.style.display = 'none';
}

function _confirmWmPosition() {
  const overlay = document.getElementById('wmPosModal');
  if (!overlay || !overlay._posData) return;
  const data       = overlay._posData;
  const entryPrice = parseFloat(document.getElementById('wmPosEntry').value);
  const stake      = parseFloat(document.getElementById('wmPosStake').value);
  const pinnFair   = parseFloat(document.getElementById('wmPosPinnFair').value);
  if (!entryPrice || entryPrice <= 0 || !stake || stake <= 0) {
    alert('Bitte Einstiegspreis und Einsatz eingeben.'); return;
  }
  _addWmPos({
    home: data.home, away: data.away, market: data.market,
    slug:       document.getElementById('wmPosSlug').value,
    priceKey:   document.getElementById('wmPosPriceKey').value,
    entryPrice, pinnFair, stake,
  });
  _closeWmPosModal();
  // Refresh WM section in Trading tab
  const wmSection = document.getElementById('wmMarketSection');
  if (wmSection) wmSection.innerHTML = _renderWmMarketTable();
}

function _wmExportJson() {
  const positions = _loadWmPos().filter(p => p.status === 'open');
  const out = JSON.stringify({
    positions: positions.map(p => ({
      home: p.home, away: p.away, market: p.market,
      slug: p.slug, priceKey: p.priceKey,
      entryPrice: p.entryPrice, pinnFair: p.pinnFair,
      stake: p.stake, status: 'open', openedAt: p.openedAt,
    })),
    updatedAt: '',
  }, null, 2);
  try {
    navigator.clipboard.writeText(out).catch(() => {});
  } catch (_) {}
  const btn = document.getElementById('wmExportBtn');
  if (btn) { const orig = btn.textContent; btn.textContent = '✅ Kopiert!'; setTimeout(() => { btn.textContent = orig; }, 2200); }
}

function _renderWmOpenPositions() {
  const positions = _loadWmPos().filter(p => p.status === 'open');
  if (positions.length === 0) return '';

  const rows = positions.map(pos => {
    let currentPrice = null;
    let pnlPct = null;
    if (_wmPolyPriceCache) {
      const entry = Object.values(_wmPolyPriceCache).find(e => e.slug === pos.slug);
      if (entry && pos.priceKey && entry[pos.priceKey]) {
        currentPrice = entry[pos.priceKey];
        if (pos.entryPrice > 0) pnlPct = ((currentPrice - pos.entryPrice) / pos.entryPrice * 100).toFixed(1);
      }
    }
    const isProfit  = pnlPct !== null && parseFloat(pnlPct) >= 0;
    const pnlColor  = pnlPct === null ? '#8b949e' : isProfit ? '#3fb950' : '#f85149';
    const pnlStr    = pnlPct !== null
      ? `<strong style="color:${pnlColor}">${parseFloat(pnlPct)>=0?'+':''}${pnlPct}%</strong>`
      : `<span style="color:#8b949e">—</span>`;
    const currStr   = currentPrice
      ? `<span style="color:#a78bfa">${(currentPrice*100).toFixed(1)}¢</span> (${(1/currentPrice).toFixed(2)}x)`
      : '<span style="color:#8b949e">—</span>';
    const polyUrl   = pos.slug ? `https://polymarket.com/de/sports/fifa-world-cup/${pos.slug}` : '#';
    return `<div style="display:flex;align-items:center;gap:8px;padding:6px 10px;
                        background:#161b22;border-radius:6px;margin-bottom:4px;font-size:12px;flex-wrap:wrap">
      <span style="color:#e6edf3;min-width:180px">${pos.home} vs ${pos.away} — ${pos.market}</span>
      <span style="color:#8b949e">Entry <strong style="color:#c9d1d9">${(pos.entryPrice*100).toFixed(1)}¢</strong></span>
      <span style="color:#8b949e">Aktuell ${currStr}</span>
      <span>${pnlStr}</span>
      <span style="color:#8b949e">€${pos.stake}</span>
      <a href="${polyUrl}" target="_blank" rel="noopener"
         style="margin-left:auto;background:#a78bfa22;border:1px solid #a78bfa44;border-radius:5px;
                color:#a78bfa;font-size:10px;font-weight:700;padding:2px 8px;text-decoration:none;white-space:nowrap">
        🔗 Verkaufen
      </a>
      <button onclick="_closeWmPos(${pos.id});const s=document.getElementById('wmMarketSection');if(s)s.innerHTML=_renderWmMarketTable();"
              style="background:#f8514912;border:1px solid #f8514933;border-radius:5px;
                     color:#f85149;font-size:10px;padding:2px 6px;cursor:pointer">✕</button>
    </div>`;
  }).join('');

  return `<div style="background:#0d1117;border:1px solid #3fb95044;border-radius:10px;
                      padding:12px 14px;margin-bottom:14px">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
      <span style="font-size:13px;font-weight:700;color:#3fb950">📊 Offene Positionen (${positions.length})</span>
      <button id="wmExportBtn" onclick="_wmExportJson()"
              style="margin-left:auto;background:#21262d;border:1px solid #30363d;border-radius:6px;
                     color:#c9d1d9;font-size:11px;padding:3px 10px;cursor:pointer">
        📋 JSON kopieren
      </button>
    </div>
    <div style="font-size:10px;color:#8b949e;margin-bottom:8px">
      JSON in <code>wm_poly_positions.json</code> einfügen &amp; committen → GitHub Action übernimmt das Monitoring
    </div>
    ${rows}
  </div>`;
}

function _ensureWmPosModal() {
  if (document.getElementById('wmPosModal')) return;
  const m = document.createElement('div');
  m.id = 'wmPosModal';
  m.style.cssText = 'display:none;position:fixed;inset:0;background:#00000099;z-index:9999;' +
    'align-items:center;justify-content:center';
  m.innerHTML = `
    <div style="background:#161b22;border:1px solid #30363d;border-radius:12px;padding:24px 28px;
                min-width:340px;max-width:480px;width:90%">
      <div style="font-size:14px;font-weight:700;color:#e6edf3;margin-bottom:4px">✏️ Position loggen</div>
      <div id="wmPosTitle" style="font-size:12px;color:#a78bfa;margin-bottom:16px"></div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px">
        <label style="font-size:11px;color:#8b949e">
          Einstiegspreis (Wahrsch.)
          <input id="wmPosEntry" type="number" step="0.0001" min="0.01" max="1"
                 style="display:block;width:100%;margin-top:4px;background:#0d1117;border:1px solid #30363d;
                        border-radius:6px;color:#e6edf3;padding:6px 8px;font-size:13px"/>
        </label>
        <label style="font-size:11px;color:#8b949e">
          Einsatz (€)
          <input id="wmPosStake" type="number" step="1" min="1"
                 style="display:block;width:100%;margin-top:4px;background:#0d1117;border:1px solid #30363d;
                        border-radius:6px;color:#e6edf3;padding:6px 8px;font-size:13px"/>
        </label>
        <label style="font-size:11px;color:#8b949e">
          Pinnacle Fair (devigged)
          <input id="wmPosPinnFair" type="number" step="0.0001" min="0" max="1" readonly
                 style="display:block;width:100%;margin-top:4px;background:#0d1117;border:1px solid #30363d;
                        border-radius:6px;color:#8b949e;padding:6px 8px;font-size:13px"/>
        </label>
        <div></div>
      </div>
      <input type="hidden" id="wmPosSlug"/>
      <input type="hidden" id="wmPosPriceKey"/>
      <div style="display:flex;gap:10px;justify-content:flex-end">
        <button onclick="_closeWmPosModal()"
                style="background:#21262d;border:1px solid #30363d;border-radius:6px;
                       color:#8b949e;font-size:13px;padding:7px 16px;cursor:pointer">
          Abbrechen
        </button>
        <button onclick="_confirmWmPosition()"
                style="background:#3fb95022;border:1px solid #3fb95066;border-radius:6px;
                       color:#3fb950;font-size:13px;font-weight:700;padding:7px 16px;cursor:pointer">
          ✅ Position speichern
        </button>
      </div>
    </div>`;
  m.addEventListener('click', e => { if (e.target === m) _closeWmPosModal(); });
  document.body.appendChild(m);
}

// ── WM 2026 Manual Bet via GitHub Action ─────────────────────────────────
// Same mechanism as Polymarket Betting tab — triggers place-poly-bets dispatch
// Order fields understood by polymarket_bet.py:
//   market: "Heimsieg"|"Auswärtssieg"|"Unentschieden"|"Over 2.5 Tore"|"Under 2.5 Tore"|"Beide Teams treffen"
//   slug:   moneyline slug for 1X2, more-markets slug for O/U

function _wmBetConfirm(orderJson) {
  // orderJson is a JSON string passed via onclick to avoid closure issues
  let order;
  try {
    order = typeof orderJson === 'string' ? JSON.parse(decodeURIComponent(orderJson)) : orderJson;
  } catch (e) {
    console.error('[WMBet] Failed to parse order JSON:', e);
    alert('Fehler: Bet-Order konnte nicht gelesen werden. Bitte Seite neu laden.');
    return;
  }
  const pat = _getGithubPAT();

  const polyOddsStr = order.polyPrice ? (1 / order.polyPrice).toFixed(2) : '—';
  const edgeStr     = order.edge != null && order.edge > 0 ? `+${order.edge}pp vs Pinnacle fair` : '';
  const stakeEur    = _getStakeForEdge(order.edge ?? 0);
  const potentialWin = order.polyPrice > 0
    ? ((stakeEur / order.polyPrice) - stakeEur).toFixed(2)
    : '?';

  // Reuse polyModal if it exists, otherwise create one inline
  let modal = document.getElementById('polyModal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'polyModal';
    modal.style.cssText = `position:fixed;inset:0;background:#000000cc;z-index:9999;display:flex;align-items:center;justify-content:center;padding:16px`;
    modal.innerHTML = '<div id="polyModalBody" style="background:#0d1117;border:1px solid #30363d;border-radius:14px;padding:24px;max-width:480px;width:100%"></div>';
    modal.addEventListener('click', e => { if (e.target === modal) modal.style.display = 'none'; });
    document.body.appendChild(modal);
  }
  // Store order in modal dataset to avoid conflicts from rapid multi-clicks
  modal.dataset.pendingOrder = JSON.stringify(order);
  modal.style.display = 'flex';

  document.getElementById('polyModalBody').innerHTML = `
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:18px">
      <span style="font-size:24px">🏆</span>
      <div>
        <div style="font-size:16px;font-weight:800;color:#e6edf3">WM 2026 Bet bestätigen</div>
        <div style="font-size:12px;color:#8b949e">${order.home} vs ${order.away}</div>
      </div>
      <button onclick="document.getElementById('polyModal').style.display='none'"
        style="margin-left:auto;background:none;border:none;color:#6e7681;font-size:18px;cursor:pointer">✕</button>
    </div>

    <div style="background:#161b22;border-radius:10px;padding:16px;margin-bottom:16px">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
        <div>
          <div style="font-size:10px;color:#6e7681;margin-bottom:3px;text-transform:uppercase;letter-spacing:.5px">Markt</div>
          <div style="font-size:14px;font-weight:700;color:#e6edf3">${order.market}</div>
        </div>
        <div>
          <div style="font-size:10px;color:#6e7681;margin-bottom:3px;text-transform:uppercase;letter-spacing:.5px">Poly Odds</div>
          <div style="font-size:14px;font-weight:700;color:#a78bfa">${polyOddsStr}</div>
        </div>
        <div>
          <div style="font-size:10px;color:#6e7681;margin-bottom:3px;text-transform:uppercase;letter-spacing:.5px">Edge</div>
          <div style="font-size:13px;font-weight:700;color:#e3b341">${edgeStr || '—'}</div>
        </div>
        <div>
          <div style="font-size:10px;color:#6e7681;margin-bottom:3px;text-transform:uppercase;letter-spacing:.5px">Einsatz</div>
          <div style="font-size:13px;font-weight:700;color:#3fb950">€${stakeEur} → win ~€${potentialWin}</div>
        </div>
      </div>
    </div>

    ${!pat ? `<div style="background:#f8514911;border:1px solid #f8514933;border-radius:8px;padding:10px 14px;margin-bottom:14px;font-size:12px;color:#f85149">
      ⚠️ Kein GitHub Token — <button onclick="polyOpenSettings()" style="background:none;border:none;color:#f85149;cursor:pointer;font-size:12px;font-weight:700;text-decoration:underline;font-family:inherit">Jetzt einrichten →</button>
    </div>` : ''}

    <button id="wmBetDispatchBtn" onclick="_wmBetDispatch()"
      style="width:100%;background:linear-gradient(135deg,#e3b341,#a07820);border:none;border-radius:10px;
             color:#fff;font-size:15px;font-weight:800;padding:14px;cursor:pointer;font-family:inherit;
             letter-spacing:.02em;box-shadow:0 2px 16px #e3b34144;margin-bottom:8px;${!pat?'opacity:.5;':''}">
      🟣 Bet via GitHub auslösen
    </button>
    <div style="text-align:center;font-size:11px;color:#484f58">
      €${stakeEur} USDC · Polygon · Private Key in GitHub Secrets
    </div>`;
}

async function _wmBetDispatch() {
  const modal = document.getElementById('polyModal');
  let order;
  try {
    order = modal && modal.dataset.pendingOrder ? JSON.parse(modal.dataset.pendingOrder) : null;
  } catch (e) {
    console.error('[WMBet] Failed to read pending order from modal:', e);
    order = null;
  }
  if (!order) return;

  const btn = document.getElementById('wmBetDispatchBtn');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Wird ausgelöst…'; btn.style.opacity = '.6'; }

  const orders = [{
    home:      order.home,
    away:      order.away,
    market:    order.market,
    league:    'WM2026',
    stake:     _getStakeForEdge(order.edge ?? 0),
    polyPrice: order.polyPrice,
    slug:      order.slug,
    eventUrl:  order.slug ? `https://polymarket.com/sports/fifa-world-cup/${order.slug}` : null,
    edgePP:    order.edge,
    pinnFair:  order.pinnFair,
  }];

  let ok = false;
  try {
    ok = await _callGitHubDispatch(orders);
  } catch(e) {
    console.error('[WMBet] dispatch error:', e);
    ok = true; // action may have triggered despite error
  }

  const body  = document.getElementById('polyModalBody');

  if (ok) {
    body.innerHTML = `
      <div style="text-align:center;padding:30px 20px">
        <div style="font-size:48px;margin-bottom:16px">✅</div>
        <div style="font-size:17px;font-weight:800;color:#3fb950;margin-bottom:8px">GitHub Action ausgelöst</div>
        <div style="font-size:13px;color:#8b949e;margin-bottom:6px">${order.home} vs ${order.away} — ${order.market}</div>
        <div style="font-size:12px;color:#484f58">polymarket_bet.py läuft jetzt auf deinem Runner.<br>Ergebnis erscheint in picks_history.json.</div>
        <button onclick="document.getElementById('polyModal').style.display='none'"
          style="margin-top:20px;background:#21262d;border:1px solid #30363d;border-radius:8px;
                 color:#e6edf3;font-size:13px;font-weight:600;padding:8px 20px;cursor:pointer;font-family:inherit">
          Schließen
        </button>
      </div>`;
  } else {
    if (btn) { btn.disabled = false; btn.textContent = '🟣 Nochmal versuchen'; btn.style.opacity = '1'; }
    _polyToast('❌ GitHub Dispatch fehlgeschlagen — PAT prüfen');
  }
}

// ── WM 2026 Market Table ───────────────────────────────────────────────────
const ALERT_EDGE_PP = 3;   // ≥ this pp → show in Alert Zone (manual review week)
                            // raise to 5 when auto-trigger is live

// ── Stake config per edge threshold (stored in localStorage) ──────────────
// Tiers: [{minEdge: 3, stake: 5}, {minEdge: 5, stake: 10}, {minEdge: 7, stake: 15}]
// _getStakeForEdge picks the highest matching tier.
const _WM_STAKE_CONFIG_KEY = 'wmStakeConfig';
const _WM_STAKE_DEFAULTS = [
  { minEdge: 3, stake: 5  },
  { minEdge: 5, stake: 10 },
  { minEdge: 7, stake: 15 },
];

function _getWmStakeConfig() {
  try {
    const raw = localStorage.getItem(_WM_STAKE_CONFIG_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed) && parsed.length) return parsed;
    }
  } catch(e) {}
  return _WM_STAKE_DEFAULTS.map(t => ({...t})); // return copies
}

function _saveWmStakeConfig(tiers) {
  try { localStorage.setItem(_WM_STAKE_CONFIG_KEY, JSON.stringify(tiers)); } catch(e) {}
}

function _getStakeForEdge(edgePP) {
  const tiers = _getWmStakeConfig();
  // Sort highest minEdge first, pick first tier where edgePP qualifies
  const sorted = [...tiers].sort((a, b) => b.minEdge - a.minEdge);
  for (const t of sorted) {
    if (edgePP >= t.minEdge) return t.stake;
  }
  return POLY_STAKE; // fallback to flat constant
}

function _renderWmStakeConfig() {
  const tiers = _getWmStakeConfig();
  const rows = tiers.map((t, i) => `
    <div style="display:grid;grid-template-columns:auto 1fr auto 1fr auto;gap:4px 8px;align-items:center;margin-bottom:6px">
      <span style="font-size:11px;color:#6e7681">ab</span>
      <input type="number" min="1" max="20" step="0.5" value="${t.minEdge}"
        id="wmStakeTierEdge${i}"
        style="background:#0d1117;border:1px solid #30363d;border-radius:5px;color:#e6edf3;font-size:12px;padding:4px 8px;width:60px;font-family:inherit">
      <span style="font-size:11px;color:#6e7681">pp → €</span>
      <input type="number" min="1" max="500" step="1" value="${t.stake}"
        id="wmStakeTierStake${i}"
        style="background:#0d1117;border:1px solid #30363d;border-radius:5px;color:#3fb950;font-size:12px;padding:4px 8px;width:60px;font-family:inherit;font-weight:700">
      <button onclick="_wmRemoveStakeTier(${i})"
        style="background:none;border:none;color:#484f58;cursor:pointer;font-size:13px;padding:2px 4px" title="Entfernen">×</button>
    </div>`).join('');

  return `
    <div id="wmStakeConfigPanel" style="background:#0d1117;border:1px solid #21262d;border-radius:8px;padding:12px 14px;margin-top:10px">
      <div style="font-size:10px;font-weight:700;color:#484f58;text-transform:uppercase;letter-spacing:.5px;margin-bottom:10px">💰 Stake-Konfiguration</div>
      <div id="wmStakeTierRows">${rows}</div>
      <div style="display:flex;gap:8px;margin-top:6px">
        <button onclick="_wmAddStakeTier()"
          style="background:#161b22;border:1px solid #30363d;border-radius:6px;color:#8b949e;font-size:11px;padding:4px 10px;cursor:pointer;font-family:inherit">
          + Tier
        </button>
        <button onclick="_wmSaveStakeConfig()"
          style="background:#3fb95022;border:1px solid #3fb95055;border-radius:6px;color:#3fb950;font-size:11px;font-weight:700;padding:4px 12px;cursor:pointer;font-family:inherit">
          ✓ Speichern
        </button>
        <button onclick="_wmResetStakeConfig()"
          style="background:none;border:none;color:#484f58;font-size:11px;padding:4px 6px;cursor:pointer;font-family:inherit">
          Reset
        </button>
      </div>
      <div id="wmStakeConfigMsg" style="font-size:10px;color:#3fb950;margin-top:5px;min-height:14px"></div>
    </div>`;
}

function _wmSaveStakeConfig() {
  const tiers = _getWmStakeConfig();
  const saved = tiers.map((_, i) => ({
    minEdge: parseFloat(document.getElementById(`wmStakeTierEdge${i}`)?.value ?? _.minEdge),
    stake:   parseFloat(document.getElementById(`wmStakeTierStake${i}`)?.value ?? _.stake),
  })).filter(t => !isNaN(t.minEdge) && !isNaN(t.stake) && t.stake > 0);
  _saveWmStakeConfig(saved);
  const msg = document.getElementById('wmStakeConfigMsg');
  if (msg) { msg.textContent = '✓ Gespeichert'; setTimeout(() => { if(msg) msg.textContent = ''; }, 2000); }
}

function _wmRemoveStakeTier(i) {
  const tiers = _getWmStakeConfig();
  tiers.splice(i, 1);
  _saveWmStakeConfig(tiers);
  const panel = document.getElementById('wmStakeConfigPanel');
  if (panel) panel.outerHTML = _renderWmStakeConfig();
}

function _wmAddStakeTier() {
  const tiers = _getWmStakeConfig();
  const maxEdge = tiers.reduce((m, t) => Math.max(m, t.minEdge), 5);
  tiers.push({ minEdge: maxEdge + 2, stake: 20 });
  _saveWmStakeConfig(tiers);
  const panel = document.getElementById('wmStakeConfigPanel');
  if (panel) panel.outerHTML = _renderWmStakeConfig();
}

function _wmResetStakeConfig() {
  _saveWmStakeConfig(_WM_STAKE_DEFAULTS.map(t => ({...t})));
  const panel = document.getElementById('wmStakeConfigPanel');
  if (panel) panel.outerHTML = _renderWmStakeConfig();
}

function _renderWmMarketTable() {
  _ensureWmPosModal();
  const openPosHtml = _renderWmOpenPositions();

  if (!_wmAllFixtures || _wmAllFixtures.length === 0) {
    return openPosHtml
      ? `<div style="margin-bottom:20px">${openPosHtml}</div>`
      : `<div style="text-align:center;padding:60px 20px;color:#484f58">
           <div style="font-size:32px;margin-bottom:10px">⏳</div>
           <div style="font-weight:600">WM-Daten werden geladen…</div>
           <div style="font-size:12px;margin-top:6px">wm_poly_prices.json nicht gefunden oder leer</div>
         </div>`;
  }

  // ── helpers ──────────────────────────────────────────────────────────────
  const ec  = pp => pp >= 5 ? '#3fb950' : pp >= 3 ? '#e3b341' : pp > 0 ? '#8b949e' : '#484f58';
  const eb  = pp => pp >= 5 ? '#3fb95018' : pp >= 3 ? '#e3b34112' : 'transparent';
  const fmt = odds => odds ? odds.toFixed(2) : '—';
  const p2o = p  => (p && p > 0) ? (1/p).toFixed(2) : '—';  // probability → decimal odds

  // Days until match
  const daysUntil = dateStr => {
    if (!dateStr) return null;
    const diff = Math.ceil((new Date(dateStr) - new Date()) / 86400000);
    return diff;
  };
  const daysBadge = dateStr => {
    const d = daysUntil(dateStr);
    if (d === null) return '';
    if (d <= 0)  return `<span style="color:#f85149;font-size:10px;font-weight:700">HEUTE</span>`;
    if (d === 1) return `<span style="color:#e3b341;font-size:10px;font-weight:700">MORGEN</span>`;
    if (d <= 7)  return `<span style="color:#e3b341;font-size:10px">in ${d}d</span>`;
    return `<span style="color:#484f58;font-size:10px">in ${d}d</span>`;
  };

  // ── filter ────────────────────────────────────────────────────────────────
  const f = _wmTableFilter;
  const allFix = _wmAllFixtures;
  const steamFix  = allFix.filter(x => x.steamLag === true);
  const growFix   = allFix.filter(x => x.edgeTrend === 'growing' && (x.bestEdge||0) >= 2);
  const counts = {
    steam: steamFix.length,
    grow:  growFix.length,
    alert: allFix.filter(x => (x.bestEdge||0) >= ALERT_EDGE_PP).length,
    pinn:  allFix.filter(x => x.hasPinnacle).length,
    all:   allFix.length,
  };

  const alertFix = allFix.filter(x => (x.bestEdge||0) >= ALERT_EDGE_PP)
                         .sort((a,b) => (b.momentumScore||0) - (a.momentumScore||0));

  const tableFix = (() => {
    if (f === 'steam')  return steamFix;
    if (f === 'grow')   return growFix;
    if (f === 'alert')  return alertFix;
    if (f === 'pinn')   return allFix.filter(x => x.hasPinnacle);
    // Default 'all': sorted by momentum score (already sorted from Python)
    return allFix;
  })();

  // ── filter bar ────────────────────────────────────────────────────────────
  const filterBtn = (key, label, count, color) => {
    const active = _wmTableFilter === key;
    const baseCol = color || '#a78bfa';
    return `<button onclick="_setWmFilter('${key}')"
      style="background:${active ? baseCol+'28' : '#161b22'};
             border:1px solid ${active ? baseCol+'99' : '#30363d'};
             border-radius:20px;color:${active ? baseCol : '#8b949e'};
             font-size:11px;font-weight:${active ? '700' : '500'};
             padding:5px 14px;cursor:pointer;transition:all .15s;white-space:nowrap">
      ${label}${count !== undefined ? ` <span style="opacity:.7;font-size:10px">${count}</span>` : ''}
    </button>`;
  };

  // ── log-position button ────────────────────────────────────────────────────
  const logBtn = (data, minEdge = 1) => {
    if (!data || !data.polyPrice || !data.pinnFair || (data.edge||0) < minEdge) return '';
    return `<button title="Position loggen" onclick="event.stopPropagation();_openLogPositionModal(JSON.parse(decodeURIComponent('${
      encodeURIComponent(JSON.stringify(data))
    }')))"
      style="background:#a78bfa18;border:1px solid #a78bfa44;border-radius:5px;
             color:#a78bfa;font-size:10px;font-weight:700;padding:2px 7px;
             cursor:pointer;white-space:nowrap;transition:opacity .15s"
      onmouseover="this.style.opacity='.7'" onmouseout="this.style.opacity='1'">✏️ loggen</button>`;
  };

  // ── outcome chip ─────────────────────────────────────────────────────────
  // betOrder: full order object for _wmBetConfirm; null = no bet button
  const outcomeChip = (label, pinn, poly, edge, logData, betOrder) => {
    const col = ec(edge);
    const bg  = eb(edge);
    const isAlert = edge !== null && edge >= ALERT_EDGE_PP;

    const betBtn = (betOrder && poly && edge !== null && edge >= ALERT_EDGE_PP)
      ? `<button onclick="event.stopPropagation();_wmBetConfirm(decodeURIComponent('${
          encodeURIComponent(JSON.stringify(betOrder))
        }'))"
          style="margin-left:4px;background:linear-gradient(135deg,#e3b34122,#a0782212);
                 border:1px solid #e3b34155;border-radius:5px;color:#e3b341;
                 font-size:10px;font-weight:700;padding:2px 8px;cursor:pointer;
                 white-space:nowrap;transition:opacity .15s"
          onmouseover="this.style.opacity='.75'" onmouseout="this.style.opacity='1'">🟣 Setzen</button>`
      : '';

    return `<div style="display:flex;align-items:center;gap:8px;padding:6px 10px;
                        background:${bg};border-radius:7px;
                        border:1px solid ${isAlert ? col+'44' : '#21262d'}">
      <span style="font-size:11px;color:#6e7681;font-weight:700;min-width:14px">${label}</span>
      ${pinn ? `<span style="font-size:12px;color:#8b949e">${fmt(pinn)}</span><span style="font-size:10px;color:#484f58">→</span>` : ''}
      <span style="font-size:12px;color:#a78bfa;font-weight:700">${p2o(poly)}</span>
      ${edge !== null && edge > 0
        ? `<span style="font-size:11px;font-weight:800;color:${col};margin-left:2px">+${edge}pp${isAlert ? ' ▲' : ''}</span>`
        : (edge !== null ? `<span style="font-size:10px;color:#484f58">${edge}pp</span>` : '')
      }
      ${logBtn(logData)}${betBtn}
    </div>`;
  };

  // ── single fixture card ───────────────────────────────────────────────────
  const fixtureCard = (fix, compact=false) => {
    const [fy, fm, fd] = (fix.date || '').split('-');
    const dateFmt = fy ? `${fd}.${fm}.${fy.slice(2)}` : '—';
    const polyUrl = fix.slug ? `https://polymarket.com/de/sports/fifa-world-cup/${fix.slug}` : '#';
    const be = fix.bestEdge || 0;

    const borderCol = be >= 5 ? '#3fb95066' : be >= ALERT_EDGE_PP ? '#e3b34166' : '#21262d';
    const bgCol     = be >= 5 ? '#0d1a0d'   : be >= ALERT_EDGE_PP ? '#1a160a'   : '#0d1117';

    // ── Edge momentum badges ──────────────────────────────────────────────────
    const trend      = fix.edgeTrend || '';
    const bestDeltaKey = fix.bestEdgeKey ? `edgeDelta_${fix.bestEdgeKey}` : null;
    const bestDelta  = bestDeltaKey ? (fix[bestDeltaKey] ?? null) : null;
    const steamLag   = fix.steamLag === true;

    const trendBadge = (() => {
      if (steamLag)
        return `<span title="Steam Lag: Pinnacle hat sich bewegt, Poly hat noch nicht reagiert — höchste Priorität!"
                      style="background:#f8514922;border:1px solid #f8514966;border-radius:8px;
                             color:#f85149;font-size:10px;font-weight:800;padding:2px 9px;white-space:nowrap;
                             cursor:default">🔥 Steam Lag</span>`;
      if (trend === 'growing')
        return `<span title="Edge wächst seit 24h — Poly hinkt Pinnacle hinterher. Jetzt handeln."
                      style="background:#3fb95018;border:1px solid #3fb95055;border-radius:8px;
                             color:#3fb950;font-size:10px;font-weight:700;padding:2px 9px;white-space:nowrap">
                  📈 ${bestDelta !== null ? '+' + bestDelta + 'pp ↑' : 'wächst'}</span>`;
      if (trend === 'closing')
        return `<span title="Edge schrumpft — Poly holt auf. Kritisch prüfen ob noch Wert vorhanden."
                      style="background:#e3b34112;border:1px solid #e3b34144;border-radius:8px;
                             color:#e3b341;font-size:10px;font-weight:700;padding:2px 9px;white-space:nowrap">
                  📉 ${bestDelta !== null ? bestDelta + 'pp ↓' : 'schließt'}</span>`;
      if (trend === 'new' && be > 0)
        return `<span title="Neue Edge — erstmals in diesem Run aufgetaucht."
                      style="background:#60a5fa18;border:1px solid #60a5fa44;border-radius:8px;
                             color:#60a5fa;font-size:10px;font-weight:700;padding:2px 9px;white-space:nowrap">
                  🆕 neu</span>`;
      return '';
    })();

    // Header row
    const header = `<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap">
      <span style="font-size:13px;font-weight:700;color:#e6edf3">${fix.home} <span style="color:#484f58;font-weight:400">vs</span> ${fix.away}</span>
      <span style="font-size:11px;color:#6e7681">${dateFmt}</span>
      ${daysBadge(fix.date)}
      ${be > 0 ? `<span style="font-size:11px;font-weight:800;color:${ec(be)};background:${eb(be)};
                               padding:2px 8px;border-radius:8px;border:1px solid ${ec(be)}44">
                    +${be}pp</span>` : ''}
      ${trendBadge}
      <span style="margin-left:auto;display:flex;align-items:center;gap:8px">
        <span style="font-size:10px;color:#484f58">Vol $${(fix.vol||0).toLocaleString('de-DE',{maximumFractionDigits:0})}</span>
        <a href="${polyUrl}" target="_blank" rel="noopener"
           style="background:#a78bfa22;border:1px solid #a78bfa55;border-radius:5px;
                  color:#a78bfa;font-size:10px;font-weight:700;padding:3px 10px;
                  text-decoration:none;white-space:nowrap">🔗 Poly</a>
      </span>
    </div>`;

    // Outcomes
    let outcomesHtml;
    if (fix.hasPinnacle) {
      outcomesHtml = `<div style="display:flex;flex-direction:column;gap:4px">
        ${outcomeChip('H', fix.pinn_hw, fix.poly_hw, fix.edge_hw,
          {home:fix.home,away:fix.away,market:'Heimsieg',priceKey:'hw',polyPrice:fix.poly_hw,pinnFair:fix.fair_hw,slug:fix.slug,edge:fix.edge_hw},
          {home:fix.home,away:fix.away,market:'Heimsieg',polyPrice:fix.poly_hw,pinnFair:fix.fair_hw,slug:fix.slug,edge:fix.edge_hw})}
        ${outcomeChip('X', fix.pinn_dr, fix.poly_dr, fix.edge_dr,
          {home:fix.home,away:fix.away,market:'Unentschieden',priceKey:'dr',polyPrice:fix.poly_dr,pinnFair:fix.fair_dr,slug:fix.slug,edge:fix.edge_dr},
          {home:fix.home,away:fix.away,market:'Unentschieden',polyPrice:fix.poly_dr,pinnFair:fix.fair_dr,slug:fix.slug,edge:fix.edge_dr})}
        ${outcomeChip('A', fix.pinn_aw, fix.poly_aw, fix.edge_aw,
          {home:fix.home,away:fix.away,market:'Auswärtssieg',priceKey:'aw',polyPrice:fix.poly_aw,pinnFair:fix.fair_aw,slug:fix.slug,edge:fix.edge_aw},
          {home:fix.home,away:fix.away,market:'Auswärtssieg',polyPrice:fix.poly_aw,pinnFair:fix.fair_aw,slug:fix.slug,edge:fix.edge_aw})}
      </div>`;
    } else {
      // No Pinnacle yet — compact single line
      outcomesHtml = `<div style="font-size:11px;color:#484f58;padding:2px 0;display:flex;gap:12px;flex-wrap:wrap">
        <span>⏳ Pinnacle noch nicht gelistet</span>
        <span style="color:#6e7681">H <strong style="color:#a78bfa">${p2o(fix.poly_hw)}</strong></span>
        <span style="color:#6e7681">X <strong style="color:#a78bfa">${p2o(fix.poly_dr)}</strong></span>
        <span style="color:#6e7681">A <strong style="color:#a78bfa">${p2o(fix.poly_aw)}</strong></span>
        ${fix.poly_o25 ? `<span style="color:#6e7681">Ü2.5 <strong style="color:#a78bfa">${p2o(fix.poly_o25)}</strong></span>` : ''}
        ${fix.poly_btts ? `<span style="color:#6e7681">BTTS <strong style="color:#a78bfa">${p2o(fix.poly_btts)}</strong></span>` : ''}
      </div>`;
    }

    // O/U + BTTS — shown as chips with bet buttons (same as 1X2)
    let ouHtml = '';
    if (fix.poly_o25 || fix.poly_btts) {
      const moreMktUrl = fix.moreMktSlug
        ? `https://polymarket.com/de/sports/fifa-world-cup/${fix.moreMktSlug}` : polyUrl;
      const ouSlug = fix.moreMktSlug || fix.slug;

      ouHtml = `<div style="margin-top:8px;padding-top:8px;border-top:1px solid #21262d">
        <div style="font-size:10px;color:#484f58;font-weight:600;margin-bottom:5px;text-transform:uppercase;letter-spacing:.5px">Over / Under + BTTS</div>
        <div style="display:flex;flex-direction:column;gap:4px">
          ${fix.poly_o25 ? outcomeChip('Ü2.5', fix.pinn_o25||null, fix.poly_o25, fix.edge_o25 ?? null,
              {home:fix.home,away:fix.away,market:'Over 2.5',priceKey:'o25',polyPrice:fix.poly_o25,pinnFair:fix.fair_o25,slug:ouSlug,edge:fix.edge_o25},
              {home:fix.home,away:fix.away,market:'Over 2.5 Tore',polyPrice:fix.poly_o25,pinnFair:fix.fair_o25,slug:ouSlug,edge:fix.edge_o25}) : ''}
          ${fix.poly_u25 ? outcomeChip('U2.5', fix.pinn_u25||null, fix.poly_u25, fix.edge_u25 ?? null,
              {home:fix.home,away:fix.away,market:'Under 2.5',priceKey:'u25',polyPrice:fix.poly_u25,pinnFair:fix.fair_u25,slug:ouSlug,edge:fix.edge_u25},
              {home:fix.home,away:fix.away,market:'Under 2.5 Tore',polyPrice:fix.poly_u25,pinnFair:fix.fair_u25,slug:ouSlug,edge:fix.edge_u25}) : ''}
          ${fix.poly_o15 ? outcomeChip('Ü1.5', null, fix.poly_o15, null, null,
              {home:fix.home,away:fix.away,market:'Over 1.5 Tore',polyPrice:fix.poly_o15,slug:ouSlug,edge:null}) : ''}
          ${fix.poly_o35 ? outcomeChip('Ü3.5', null, fix.poly_o35, null, null,
              {home:fix.home,away:fix.away,market:'Over 3.5 Tore',polyPrice:fix.poly_o35,slug:ouSlug,edge:null}) : ''}
          ${fix.poly_btts ? outcomeChip('BTTS', null, fix.poly_btts, null,
              {home:fix.home,away:fix.away,market:'BTTS',priceKey:'btts',polyPrice:fix.poly_btts,slug:ouSlug,edge:null},
              {home:fix.home,away:fix.away,market:'Beide Teams treffen',polyPrice:fix.poly_btts,slug:ouSlug,edge:null}) : ''}
        </div>
        <a href="${moreMktUrl}" target="_blank" rel="noopener"
           style="display:inline-block;margin-top:6px;font-size:10px;color:#a78bfa55;text-decoration:none;transition:color .15s"
           onmouseover="this.style.color='#a78bfa'" onmouseout="this.style.color='#a78bfa55'">+Alle Märkte auf Polymarket →</a>
      </div>`;
    }

    return `<div style="background:${bgCol};border:1px solid ${borderCol};border-radius:10px;
                        padding:10px 14px;margin-bottom:6px">
      ${header}${outcomesHtml}${ouHtml}
    </div>`;
  };

  // ── Alert Zone ────────────────────────────────────────────────────────────
  let alertZoneHtml = '';
  if (alertFix.length > 0) {
    alertZoneHtml = `
    <div style="background:linear-gradient(135deg,#1a1600,#12180a);
                border:1px solid #e3b34144;border-radius:12px;
                padding:14px 16px;margin-bottom:20px">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px">
        <span style="font-size:15px">🎯</span>
        <span style="font-size:13px;font-weight:700;color:#e3b341">Alert Zone — Edge ≥${ALERT_EDGE_PP}pp</span>
        <span style="font-size:11px;color:#6e7681;margin-left:4px">${alertFix.length} Spiel${alertFix.length!==1?'e':''} · manuell prüfen</span>
        <span style="margin-left:auto;font-size:10px;color:#484f58">Pinnacle fair vs Poly-Preis</span>
      </div>
      ${alertFix.map(fix => fixtureCard(fix)).join('')}
    </div>`;
  }

  // ── Full table ─────────────────────────────────────────────────────────────
  // Compact table view for all fixtures
  const tableRows = tableFix.map(fix => {
    const [fy, fm, fd] = (fix.date || '').split('-');
    const dateFmt = fy ? `${fd}.${fm}.` : '—';
    const d = daysUntil(fix.date);
    const dStr = d === null ? '' : d <= 0 ? '🔴' : d <= 7 ? `<span style="color:#e3b341">${d}d</span>` : `<span style="color:#484f58">${d}d</span>`;
    const be = fix.bestEdge || 0;
    const polyUrl = fix.slug ? `https://polymarket.com/de/sports/fifa-world-cup/${fix.slug}` : '#';

    const pinnStr = fix.hasPinnacle
      ? `${fmt(fix.pinn_hw)} / ${fmt(fix.pinn_dr)} / ${fmt(fix.pinn_aw)}`
      : `<span style="color:#484f58;font-style:italic">—</span>`;
    const polyStr = `<span style="color:#a78bfa">${p2o(fix.poly_hw)}</span> / <span style="color:#a78bfa">${p2o(fix.poly_dr)}</span> / <span style="color:#a78bfa">${p2o(fix.poly_aw)}</span>`;

    const edgeTd = be > 0
      ? `<span style="color:${ec(be)};font-weight:700">+${be}pp</span>`
      : (fix.hasPinnacle ? `<span style="color:#484f58">—</span>` : `<span style="color:#21262d">n/a</span>`);

    // Edge momentum indicator for compact table
    const trendTd = (() => {
      if (fix.steamLag)              return `<span title="Steam Lag" style="color:#f85149;font-weight:800">🔥</span>`;
      if (fix.edgeTrend==='growing') return `<span title="Edge wächst" style="color:#3fb950;font-weight:700">↑</span>`;
      if (fix.edgeTrend==='closing') return `<span title="Edge schließt" style="color:#e3b341;font-weight:700">↓</span>`;
      if (fix.edgeTrend==='new')     return `<span title="Neue Edge" style="color:#60a5fa;font-weight:700">★</span>`;
      return `<span style="color:#21262d">—</span>`;
    })();

    let ouStr;
    if (fix.pinn_o25 && fix.poly_o25) {
      const eo  = fix.edge_o25 ?? 0;
      const eoc = eo >= 3 ? '#3fb950' : eo >= 1.5 ? '#d29922' : eo > 0 ? '#6e9e6e' : '#484f58';
      const eos = eo > 0 ? '+' : '';
      ouStr = `<div style="line-height:1.4">
        <div style="font-size:11px;color:#8b949e">${fix.pinn_o25.toFixed(2)} <span style="color:#484f58">/</span> ${(fix.pinn_u25||0).toFixed(2)}</div>
        <div style="font-size:11px;font-weight:700;color:${eoc}">${eos}${eo}pp</div>
      </div>`;
    } else if (fix.poly_o25) {
      ouStr = `<span style="color:#6e7681">${p2o(fix.poly_o25)}/${p2o(fix.poly_u25)}</span>`;
    } else {
      ouStr = `<span style="color:#21262d">—</span>`;
    }

    const rowBg = be >= 5 ? 'background:#0d1a0d' : be >= ALERT_EDGE_PP ? 'background:#1a160a' : '';

    return `<tr style="border-bottom:1px solid #161b22;${rowBg}">
      <td style="padding:7px 10px;white-space:nowrap">
        <div style="font-size:12px;font-weight:600;color:#c9d1d9">${fix.home} vs ${fix.away}</div>
      </td>
      <td style="padding:7px 8px;white-space:nowrap;font-size:11px;color:#6e7681">${dateFmt} ${dStr}</td>
      <td style="padding:7px 8px;font-size:11px;color:#8b949e">${pinnStr}</td>
      <td style="padding:7px 8px;font-size:11px">${polyStr}</td>
      <td style="padding:7px 8px;text-align:center">${edgeTd}</td>
      <td style="padding:7px 8px;text-align:center">${trendTd}</td>
      <td style="padding:7px 8px;font-size:11px;text-align:center">${ouStr}</td>
      <td style="padding:7px 8px;text-align:center">
        <a href="${polyUrl}" target="_blank" rel="noopener"
           style="color:#a78bfa55;font-size:11px;text-decoration:none;transition:color .15s"
           onmouseover="this.style.color='#a78bfa'" onmouseout="this.style.color='#a78bfa55'">🔗</a>
      </td>
    </tr>`;
  }).join('');

  const noPinnCount = allFix.filter(x => !x.hasPinnacle).length;
  const standStr = _wmGeneratedAt ? _wmGeneratedAt : '';
  // Next update times (UTC → CEST +2h): 06,10,14,18,22 UTC
  const nextUpdate = (() => {
    const now = new Date();
    const hrs = [8,12,16,20,24]; // CEST
    const nowH = now.getHours() + now.getMinutes()/60;
    const next = hrs.find(h => h > nowH) || 8;
    const diff = next > nowH ? next - nowH : (24 - nowH + 8);
    return diff < 1 ? `in ${Math.round(diff*60)}min` : `in ~${Math.floor(diff)}h`;
  })();

  const _html = `<div>

    <!-- Header -->
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:16px;flex-wrap:wrap">
      <span style="font-size:16px;font-weight:800;color:#e6edf3">🏆 WM 2026 — Polymarket</span>
      <div style="display:flex;flex-direction:column;margin-left:auto;text-align:right">
        <span style="font-size:10px;color:#484f58">Stand: ${standStr}</span>
        <span style="font-size:10px;color:#484f58">Nächstes Update: ${nextUpdate}</span>
      </div>
    </div>

    <!-- Info bar -->
    <div style="font-size:11px;color:#6e7681;margin-bottom:12px;line-height:1.6">
      Pinnacle devigged fair-Prob. vs Polymarket — positiver Edge = Poly unterbewertet.
      5× täglich aktualisiert (08/12/16/20/00 Uhr CEST).
      ${noPinnCount > 0 ? `<span style="color:#484f58">${noPinnCount} Spiele noch ohne Pinnacle.</span>` : ''}
    </div>

    <!-- Performance / P&L / CLV Section (async-filled) -->
    <div id="wmPerformanceSection"></div>

    <!-- Alert Zone (always visible when alerts exist) -->
    ${alertZoneHtml}

    <!-- Filter bar -->
    <div style="display:flex;gap:6px;margin-bottom:14px;flex-wrap:wrap;align-items:center">
      <span style="font-size:11px;color:#484f58;margin-right:4px">Tabelle:</span>
      ${counts.steam > 0 ? filterBtn('steam', '🔥 Steam Lag', counts.steam, '#f85149') : ''}
      ${counts.grow  > 0 ? filterBtn('grow',  '📈 Wächst', counts.grow, '#3fb950') : ''}
      ${filterBtn('alert', `🎯 Alert ≥${ALERT_EDGE_PP}pp`, counts.alert, '#e3b341')}
      ${filterBtn('pinn',  '🔷 Mit Pinnacle', counts.pinn)}
      ${filterBtn('all',   '📋 Alle 72', counts.all)}
    </div>
    ${(counts.steam > 0 || counts.grow > 0) ? `
    <div style="background:rgba(63,185,80,0.06);border:1px solid #3fb95030;border-radius:8px;
                padding:8px 12px;margin-bottom:12px;font-size:11px;color:#6e7681;line-height:1.6">
      <span style="color:#3fb950;font-weight:700">Momentum-Ranking aktiv:</span>
      Spiele sind sortiert nach Handlungsdringlichkeit —
      ${counts.steam > 0 ? `<strong style="color:#f85149">${counts.steam}× 🔥 Steam Lag</strong> (höchste Priorität) · ` : ''}
      ${counts.grow > 0  ? `<strong style="color:#3fb950">${counts.grow}× 📈 wachsende Edge</strong> ·` : ''}
      je früher desto besser.
    </div>` : ''}

    <!-- Open positions -->
    ${openPosHtml}

    <!-- Compact table -->
    ${tableFix.length === 0
      ? `<div style="text-align:center;padding:30px;color:#484f58;font-size:13px">Keine Fixtures für diesen Filter.</div>`
      : `<div style="overflow-x:auto;border-radius:10px;border:1px solid #21262d">
           <table style="width:100%;border-collapse:collapse;font-family:inherit">
             <thead>
               <tr style="background:#161b22;border-bottom:1px solid #21262d">
                 <th style="padding:8px 10px;text-align:left;font-size:10px;color:#6e7681;font-weight:700;text-transform:uppercase;letter-spacing:.5px">Spiel</th>
                 <th style="padding:8px 8px;text-align:left;font-size:10px;color:#6e7681;font-weight:700;text-transform:uppercase;letter-spacing:.5px">Datum</th>
                 <th style="padding:8px 8px;text-align:left;font-size:10px;color:#6e7681;font-weight:700;text-transform:uppercase;letter-spacing:.5px">Pinnacle H/X/A</th>
                 <th style="padding:8px 8px;text-align:left;font-size:10px;color:#a78bfa;font-weight:700;text-transform:uppercase;letter-spacing:.5px">Poly H/X/A</th>
                 <th style="padding:8px 8px;text-align:center;font-size:10px;color:#6e7681;font-weight:700;text-transform:uppercase;letter-spacing:.5px">Edge</th>
                 <th style="padding:8px 8px;text-align:center;font-size:10px;color:#6e7681;font-weight:700;text-transform:uppercase;letter-spacing:.5px" title="🔥 Steam Lag · ↑ wächst · ↓ schließt">Trend</th>
                 <th style="padding:8px 8px;text-align:center;font-size:10px;color:#6e7681;font-weight:700;text-transform:uppercase;letter-spacing:.5px">Ü/U 2.5</th>
                 <th style="padding:8px 8px;text-align:center;font-size:10px;color:#6e7681;font-weight:700;text-transform:uppercase;letter-spacing:.5px"></th>
               </tr>
             </thead>
             <tbody>${tableRows}</tbody>
           </table>
         </div>`
    }

    <!-- System Info -->
    <div id="wmSystemInfo" style="margin-top:18px;padding:12px 16px;background:#161b22;border:1px solid #21262d;border-radius:10px;font-size:11px;color:#6e7681;line-height:1.7">
      <div style="font-size:10px;font-weight:700;color:#484f58;text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px">🤖 System Info</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px 16px">
        <div>
          <span style="color:#484f58">Auto-Trigger:</span>
          <span style="color:#f85149;font-weight:700">DEAKTIVIERT</span>
          <span style="color:#484f58"> (ENABLED=False)</span>
        </div>
        <div>
          <span style="color:#484f58">Edge-Schwelle:</span>
          <span style="color:#e3b341;font-weight:700">${ALERT_EDGE_PP}pp</span>
          <span style="color:#484f58"> → ${counts.alert} Kandidat${counts.alert !== 1 ? 'en' : ''} jetzt</span>
        </div>
        <div>
          <span style="color:#484f58">Platziert:</span>
          <span id="wmAutoBetsCount" style="color:#8b949e;font-weight:700">…</span>
        </div>
        <div>
          <span style="color:#484f58">Poly Balance:</span>
          <span id="wmPolyBalance" style="color:#a78bfa;font-weight:700">…</span>
        </div>
      </div>
      ${_renderWmStakeConfig()}
    </div>
  </div>`;

  // Async: fetch stats for System Info (deferred so DOM is ready)
  setTimeout(() => {
    // Placed bet count
    fetch('wm_auto_bets_placed.json?' + Date.now())
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        const el = document.getElementById('wmAutoBetsCount');
        if (!el) return;
        const bets  = d && Array.isArray(d.bets) ? d.bets : [];
        const count = bets.length;
        const total = bets.reduce((s, b) => s + (b.stake ?? 0), 0);
        el.textContent = `${count} Bet${count !== 1 ? 's' : ''} · €${total.toFixed(0)} gesamt`;
      })
      .catch(() => {
        const el = document.getElementById('wmAutoBetsCount');
        if (el) el.textContent = '—';
      });

    // Polymarket USDC balance
    fetch('wm_poly_balance.json?' + Date.now())
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        const el = document.getElementById('wmPolyBalance');
        if (!el) return;
        const total = d?.total ?? d?.usdc;
        if (total == null) { el.textContent = '—'; return; }
        const updStr = d.updatedAt
          ? ` <span style="color:#484f58;font-size:10px;font-weight:400">(${new Date(d.updatedAt).toLocaleTimeString('de-AT', {hour:'2-digit',minute:'2-digit'})})</span>`
          : '';
        const breakdown = (d.usdc_e > 0.01)
          ? ` <span style="color:#484f58;font-size:10px">(+$${d.usdc_e.toFixed(2)} USDC.e)</span>`
          : '';
        el.innerHTML = `$${total.toFixed(2)} USDC${breakdown}${updStr}`;
      })
      .catch(() => {
        const el = document.getElementById('wmPolyBalance');
        if (el) el.textContent = '—';
      });

    // P&L / CLV Performance section
    fetch('wm_results.json?' + Date.now())
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        const el = document.getElementById('wmPerformanceSection');
        if (!el) return;
        if (!d) { el.innerHTML = ''; return; }
        el.innerHTML = _buildPerformanceHtml(d);
      })
      .catch(() => {});
  }, 0);

  return _html;
}

// Alias — kept so old references still work
function _renderWmClvRadar() { return _renderWmMarketTable(); }

// ── WM 2026 Performance / P&L / CLV Section ───────────────────────────────
// Gebaut aus wm_results.json, wird async nach dem Rendern injiziert.

function _buildPerformanceHtml(data) {
  const s     = data.summary || {};
  const bets  = data.bets    || [];

  // Noch keine Bets → nichts anzeigen
  if (!s.totalBets || s.totalBets === 0) return '';

  const pnlColor  = s.totalPnl >= 0 ? '#3fb950' : '#f85149';
  const roiColor  = s.roi       >= 0 ? '#3fb950' : '#f85149';
  const clvColor  = (s.avgCLV  ?? 0) >= 0 ? '#3fb950' : '#f85149';

  const fmtPct  = v  => v != null  ? `${v >= 0 ? '+' : ''}${v.toFixed(1)}%` : '—';
  const fmtPP   = v  => v != null  ? `${v >= 0 ? '+' : ''}${v.toFixed(1)}pp` : '—';
  const fmtEur  = v  => v != null  ? `${v >= 0 ? '+' : ''}€${Math.abs(v).toFixed(2)}` : '—';
  const fmtSign = (v, fmt) => v != null ? (v >= 0 ? `+${fmt(Math.abs(v))}` : `-${fmt(Math.abs(v))}`) : '—';

  // Stat-Karten
  const statCard = (label, value, color, sub = '') => `
    <div style="background:#0d1117;border:1px solid #21262d;border-radius:10px;padding:14px 16px;text-align:center">
      <div style="font-size:10px;color:#484f58;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">${label}</div>
      <div style="font-size:20px;font-weight:800;color:${color}">${value}</div>
      ${sub ? `<div style="font-size:10px;color:#6e7681;margin-top:3px">${sub}</div>` : ''}
    </div>`;

  const winRate   = s.winRate != null ? `${s.winRate.toFixed(0)}%` : '—';
  const clvStr    = fmtPP(s.avgCLV);
  const roiStr    = fmtPct(s.roi);
  const pnlStr    = s.totalPnl >= 0
    ? `+€${s.totalPnl.toFixed(2)}`
    : `-€${Math.abs(s.totalPnl).toFixed(2)}`;

  const statsHtml = `
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:16px">
      ${statCard('Bets', `${s.wins ?? 0}W / ${s.losses ?? 0}L`, '#e6edf3',
        `${s.resolved ?? 0} resolved · ${s.pending ?? 0} offen`)}
      ${statCard('Win Rate', winRate, s.winRate >= 50 ? '#3fb950' : '#f85149',
        `${s.totalBets} Bets gesamt`)}
      ${statCard('P&L', pnlStr, pnlColor,
        `€${(s.totalStaked ?? 0).toFixed(0)} gesetzt`)}
      ${statCard('ROI', roiStr, roiColor,
        `Ø CLV: ${clvStr}`)}
    </div>`;

  // Bet-Tabelle
  const resolved = bets.filter(b => b.result !== 'PENDING');
  const pending  = bets.filter(b => b.result === 'PENDING');
  const sorted   = [...resolved, ...pending];

  if (!sorted.length) return `
    <div style="margin:16px 0;padding:16px;background:#0d1117;border:1px solid #21262d;border-radius:12px">
      <div style="font-size:11px;font-weight:700;color:#484f58;text-transform:uppercase;letter-spacing:.5px;margin-bottom:12px">📈 Performance</div>
      ${statsHtml}
    </div>`;

  const rows = sorted.map(b => {
    const resultIcon = {WIN:'✅',LOSS:'❌',VOID:'⬜',PENDING:'⏳'}[b.result] ?? '?';
    const resultCol  = {WIN:'#3fb950',LOSS:'#f85149',VOID:'#8b949e',PENDING:'#e3b341'}[b.result] ?? '#8b949e';
    const pnlStr2    = b.result === 'WIN'  ? `+€${b.pnl.toFixed(2)}`
                     : b.result === 'LOSS' ? `-€${Math.abs(b.pnl).toFixed(2)}`
                     : b.result === 'VOID' ? '—'
                     : '⏳';
    const pnlCol     = b.pnl > 0 ? '#3fb950' : b.pnl < 0 ? '#f85149' : '#8b949e';
    const clvCell    = b.clvPP != null
      ? `<span style="color:${b.clvPP >= 0 ? '#3fb950' : '#f85149'}">${b.clvPP >= 0 ? '+' : ''}${b.clvPP.toFixed(1)}pp</span>`
      : '<span style="color:#484f58">—</span>';
    const scoreCell  = b.score
      ? `<span style="color:#8b949e;font-size:11px">${b.score}</span>`
      : '<span style="color:#484f58">—</span>';
    const polyOddsStr = b.polyOdds ? b.polyOdds.toFixed(2) : '—';
    const edgeStr     = b.pinnFair && b.polyPrice
      ? `${((b.pinnFair - b.polyPrice) * 100).toFixed(1)}pp`
      : '—';
    const slug        = b.slug;
    const polyLink    = slug
      ? `<a href="https://polymarket.com/sports/fifa-world-cup/${slug}" target="_blank"
           style="color:#a78bfa;font-size:10px;text-decoration:none">↗</a>`
      : '';

    return `<tr style="border-top:1px solid #161b22">
      <td style="padding:8px 10px;font-size:12px;color:${resultCol};font-weight:700;white-space:nowrap">
        ${resultIcon} ${b.result}
      </td>
      <td style="padding:8px 10px;font-size:12px;color:#e6edf3;white-space:nowrap">
        ${b.home} vs ${b.away}
      </td>
      <td style="padding:8px 10px;font-size:11px;color:#8b949e">${b.market}</td>
      <td style="padding:8px 10px;font-size:12px;color:#a78bfa;text-align:center">${polyOddsStr}</td>
      <td style="padding:8px 10px;font-size:11px;color:#e3b341;text-align:center">${edgeStr}</td>
      <td style="padding:8px 10px;font-size:11px;text-align:center">${clvCell}</td>
      <td style="padding:8px 10px;font-size:12px;font-weight:700;color:${pnlCol};text-align:right">${pnlStr2}</td>
      <td style="padding:8px 10px;font-size:11px;text-align:center">${scoreCell}</td>
      <td style="padding:8px 10px;text-align:center">${polyLink}</td>
    </tr>`;
  }).join('');

  return `
    <div style="margin:16px 0;padding:16px;background:#0d1117;border:1px solid #21262d;border-radius:12px">
      <div style="font-size:11px;font-weight:700;color:#484f58;text-transform:uppercase;letter-spacing:.5px;margin-bottom:12px">
        📈 Performance — WM 2026
        ${s.sharpeEst != null ? `<span style="color:#6e7681;font-size:10px;margin-left:8px;font-weight:400">Sharpe ~${s.sharpeEst.toFixed(2)}</span>` : ''}
      </div>
      ${statsHtml}

      <!-- Bet-Tabelle -->
      <div style="overflow-x:auto;border-radius:8px;border:1px solid #21262d">
        <table style="width:100%;border-collapse:collapse;font-family:inherit">
          <thead>
            <tr style="background:#161b22">
              <th style="padding:8px 10px;font-size:10px;color:#484f58;text-transform:uppercase;letter-spacing:.5px;text-align:left;font-weight:600">Result</th>
              <th style="padding:8px 10px;font-size:10px;color:#484f58;text-transform:uppercase;letter-spacing:.5px;text-align:left;font-weight:600">Spiel</th>
              <th style="padding:8px 10px;font-size:10px;color:#484f58;text-transform:uppercase;letter-spacing:.5px;text-align:left;font-weight:600">Markt</th>
              <th style="padding:8px 10px;font-size:10px;color:#484f58;text-transform:uppercase;letter-spacing:.5px;text-align:center;font-weight:600">Odds</th>
              <th style="padding:8px 10px;font-size:10px;color:#484f58;text-transform:uppercase;letter-spacing:.5px;text-align:center;font-weight:600">Edge</th>
              <th style="padding:8px 10px;font-size:10px;color:#3fb950;text-transform:uppercase;letter-spacing:.5px;text-align:center;font-weight:600">CLV</th>
              <th style="padding:8px 10px;font-size:10px;color:#484f58;text-transform:uppercase;letter-spacing:.5px;text-align:right;font-weight:600">P&L</th>
              <th style="padding:8px 10px;font-size:10px;color:#484f58;text-transform:uppercase;letter-spacing:.5px;text-align:center;font-weight:600">Score</th>
              <th style="padding:8px 10px;font-size:10px;color:#484f58;text-transform:uppercase;letter-spacing:.5px;text-align:center;font-weight:600">Link</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>

      <!-- CLV Erklärung -->
      <div style="margin-top:10px;font-size:10px;color:#484f58;line-height:1.6">
        <strong style="color:#3fb950">CLV</strong> (Closing Line Value) = Pinnacle-Fair-Prob beim Anpfiff minus Entry-Preis auf Polymarket.
        Positiv = wir haben zum richtigen Zeitpunkt besser als der Marktschluss gewettet → zeigt echten Edge.
      </div>
    </div>`;
}

function renderPolyPickCards() {
  const picks = _polyState.picks;

  if (picks.length === 0) {
    return `<div style="grid-column:1/-1;text-align:center;padding:60px 24px;color:#8b949e">
      <div style="font-size:40px;margin-bottom:14px">🟣</div>
      <div style="font-size:16px;font-weight:600;margin-bottom:6px;color:#e6edf3">Keine Picks verfügbar</div>
      <div style="font-size:13px;line-height:1.6">Für <strong>${_polyState.dateStr}</strong> gibt es keine Picks.</div>
    </div>`;
  }

  const clubPicks = picks.filter(p => !p.isWm);
  const wmPicks   = picks.filter(p => p.isWm);

  const wmPickHtml = wmPicks.length > 0
    ? `<div style="grid-column:1/-1;font-size:11px;color:#6e7681;margin-bottom:8px;padding-top:4px">
         WM System-Picks (${wmPicks.length}):
       </div>` + wmPicks.map(_renderPickCard).join('')
    : '';

  const clubHtml = clubPicks.length > 0
    ? `<div style="grid-column:1/-1;font-size:11px;color:#6e7681;margin:12px 0 8px">
         Club-Liga Picks (${clubPicks.length}):
       </div>` + clubPicks.map(_renderPickCard).join('')
    : '';

  return wmPickHtml + clubHtml;
}

// ── 6. STATS ────────────────────────────────────────────

function _getPolyBets() {
  try   { return JSON.parse(localStorage.getItem('betedge_poly_bets') || '[]'); }
  catch { return []; }
}

function _savePolyBets(bets) {
  try {
    localStorage.setItem('betedge_poly_bets', JSON.stringify(bets));
  } catch(e) {
    if (e.name === 'QuotaExceededError') {
      // Try to free space by trimming old V2 tracking entries, then retry
      _trimLocalStorageQuota();
      try {
        localStorage.setItem('betedge_poly_bets', JSON.stringify(bets));
        console.log('[PolyBets] ✅ Gespeichert nach Quota-Bereinigung');
        return;
      } catch(e2) { /* still full — fall through to error */ }
    }
    console.error('[PolyBets] localStorage error:', e.name, e.message);
    _polyShowStorageError(e);
  }
}

// Free up localStorage space by trimming old/large entries
function _trimLocalStorageQuota() {
  // 1. Trim betedge_picks_v2 — keep last 60 days (date-based, not count-based)
  // ~30–50 fixtures/day × 60 days = up to 3000 entries, but localStorage has ~5MB.
  // Date-based trim avoids data loss when many fixtures are tracked in a day.
  try {
    const v2Raw = localStorage.getItem('betedge_picks_v2');
    if (v2Raw) {
      const v2 = JSON.parse(v2Raw);
      if (v2.length > 500) {
        // Keep last 60 days of data
        const cutoff = new Date();
        cutoff.setDate(cutoff.getDate() - 60);
        const cutoffIso = cutoff.toISOString().slice(0, 10);
        const trimmed = v2.filter(e => (e.dateIso || '') >= cutoffIso);
        if (trimmed.length < v2.length) {
          localStorage.setItem('betedge_picks_v2', JSON.stringify(trimmed));
          console.log(`[Storage] Trimmed betedge_picks_v2: ${v2.length} → ${trimmed.length} entries (kept ≥${cutoffIso})`);
        }
      }
    }
  } catch(_) {}

  // 2. Remove any stale large keys we don't recognise
  try {
    const keysToCheck = Object.keys(localStorage)
      .filter(k => !['betedge_picks_v2','betedge_poly_bets','betedge_github_pat'].includes(k));
    for (const k of keysToCheck) {
      const size = (localStorage.getItem(k) || '').length;
      if (size > 50000) {
        console.log(`[Storage] Removing large stale key: ${k} (${Math.round(size/1024)}KB)`);
        localStorage.removeItem(k);
      }
    }
  } catch(_) {}
}

function _polyShowStorageError(e) {
  const existing = document.getElementById('polyStorageErrBanner');
  if (existing) return; // already showing
  const banner = document.createElement('div');
  banner.id = 'polyStorageErrBanner';
  Object.assign(banner.style, {
    position: 'fixed', top: '60px', right: '16px', zIndex: '9999',
    background: '#2d1a1a', border: '1px solid #f85149',
    borderRadius: '10px', padding: '12px 16px', maxWidth: '340px',
    color: '#f85149', fontSize: '12px', fontWeight: '600',
    boxShadow: '0 4px 20px rgba(0,0,0,.6)', lineHeight: '1.5',
  });
  // Compute what's using space
  let storageInfo = '';
  try {
    const keys = Object.keys(localStorage);
    const sizes = keys.map(k => ({ k, kb: Math.round((localStorage.getItem(k)||'').length / 1024) }));
    sizes.sort((a,b) => b.kb - a.kb);
    storageInfo = sizes.slice(0,5).map(x => `${x.k}: ${x.kb}KB`).join(' · ');
  } catch(_) {}

  banner.innerHTML = `
    <div style="font-size:13px;font-weight:800;margin-bottom:4px">⚠️ localStorage voll (QuotaExceededError)</div>
    <div style="color:#8b949e;font-size:11px;margin-top:4px">${storageInfo}</div>
    <div style="color:#8b949e;font-size:11px;margin-top:4px">Bets werden via picks_history.json (Repo) getrackt — kein Datenverlust.</div>
    <div style="display:flex;gap:6px;margin-top:8px;flex-wrap:wrap">
      <button onclick="_trimLocalStorageQuota();_savePolyBets(_getPolyBets());this.textContent='✅ Bereinigt';this.disabled=true" style="background:#f8514922;border:1px solid #f8514955;border-radius:6px;color:#f85149;font-size:11px;padding:3px 10px;cursor:pointer;font-family:inherit">🧹 Bereinigen</button>
      <button onclick="this.parentElement.parentElement.remove()" style="background:none;border:1px solid #30363d;border-radius:6px;color:#8b949e;font-size:11px;padding:3px 10px;cursor:pointer;font-family:inherit">✕ Schließen</button>
    </div>
  `;
  document.body.appendChild(banner);
  setTimeout(() => banner?.remove(), 12000);
}

// ── Import placed bets from picks_history.json ───────────────────────────────
// picks_history.json is written by polymarket_bet.py (GitHub Action) and contains
// polyBets arrays embedded in fixture entries. This is the reliable source of truth
// since it lives in the repo and survives page reloads / localStorage failures.
const POLY_HISTORY_URLS = [
  'http://localhost:3001/picks_history',
  'https://blummabet.github.io/Betting-Dashboard/picks_history.json',
];

async function _syncBetsFromHistory(silent = true) {
  let history = null;
  for (const url of POLY_HISTORY_URLS) {
    try {
      const r = await fetch(url, { cache: 'no-store' });
      if (r.ok) { history = await r.json(); break; }
    } catch(_) {}
  }
  if (!Array.isArray(history)) return 0;

  const existing  = _getPolyBets();
  // Build dedup index: "home|away|market" (case-insensitive normalised)
  const _norm = s => (s || '').toLowerCase().replace(/[^a-z0-9]/g, '');
  const _key  = (home, away, market) => `${_norm(home)}|${_norm(away)}|${_norm(market)}`;
  const idx   = new Set(existing.map(b => _key(b.home, b.away, b.market)));

  let imported = 0;
  for (const fx of history) {
    if (!Array.isArray(fx.polyBets)) continue;
    for (const pb of fx.polyBets) {
      if (pb.status === 'failed') continue; // skip failed orders
      const k = _key(fx.home, fx.away, pb.market);
      if (idx.has(k)) continue; // already tracked

      existing.push({
        id:        `${fx.league || ''}|${fx.home}|${fx.away}|${pb.market}`,
        date:      fx.date || '',
        home:      fx.home || '',
        away:      fx.away || '',
        market:    pb.market || '',
        league:    fx.league || '',
        stake:     pb.stake  || 5,
        polyPrice: pb.polyPrice || null,
        placed:    pb.placedAt || fx.date || '',
        method:    'auto',
        result:    pb.result  || null,
      });
      idx.add(k);
      imported++;
    }
  }

  if (imported > 0) {
    _savePolyBets(existing);
    console.log(`[PolyBets] ✅ ${imported} Bet(s) aus picks_history.json importiert`);
    if (!silent) _polyToast(`📥 ${imported} Bet${imported !== 1 ? 's' : ''} aus Repo importiert`);
  }
  return imported;
}

function renderPolyStats() {
  // Merge localStorage bets with session-memory fallback (deduped by id)
  const lsBets  = _getPolyBets();
  const lsIds   = new Set(lsBets.map(b => b.id));
  const sessBets = Object.values(window._polyPlacedThisSession || {})
                    .filter(b => !lsIds.has(b.id));
  const bets    = [...lsBets, ...sessBets];
  const total   = bets.length;
  const resolved = bets.filter(b => b.result && b.result !== 'void');
  const won      = bets.filter(b => b.result === 'won').length;
  const lost     = bets.filter(b => b.result === 'lost').length;
  const winRate  = resolved.length > 0 ? Math.round(won / resolved.length * 100) : null;
  const staked   = bets.reduce((s, b) => s + (b.stake || 0), 0);
  const returned = bets.filter(b => b.result === 'won')
    .reduce((s, b) => s + (b.polyPrice > 0 ? b.stake / b.polyPrice : 0), 0);
  const pnl      = returned - staked;
  const roi      = staked > 0 ? Math.round(pnl / staked * 100) : null;

  const statCards = [
    {
      label: 'Total Bets',
      value: total,
      sub:   `${won}W · ${lost}L · ${total - won - lost} open`,
      color: '#e6edf3',
    },
    {
      label: 'Win Rate',
      value: winRate !== null ? `${winRate}%` : '—',
      sub:   `${resolved.length} abgeschlossen`,
      color: winRate !== null ? (winRate >= 50 ? '#3fb950' : '#f85149') : '#8b949e',
    },
    {
      label: 'Einsatz',
      value: `€${staked.toFixed(2)}`,
      sub:   `Ø €${total > 0 ? (staked / total).toFixed(2) : '—'} / Bet`,
      color: '#e6edf3',
    },
    {
      label: 'P&L',
      value: `€${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}`,
      sub:   roi !== null ? `ROI: ${roi > 0 ? '+' : ''}${roi}%` : 'ROI: —',
      color: pnl > 0 ? '#3fb950' : pnl < 0 ? '#f85149' : '#8b949e',
    },
  ];

  const _toTs = s => { const [d,m,y] = (s||'00.00.0000').split('.'); return new Date(`${y}-${m}-${d}`); };
  const recent = [...bets].sort((a,b) => _toTs(b.date) - _toTs(a.date)).slice(0, 15);
  const rows   = recent.length === 0
    ? `<tr><td colspan="6" style="text-align:center;color:#8b949e;padding:28px;font-size:13px">Noch keine Bets gespeichert</td></tr>`
    : recent.map((b, i) => {
        const resIcon   = b.result === 'won'  ? '✅' : b.result === 'lost' ? '❌' : b.result === 'void' ? '—' : '⏳';
        const resColor  = b.result === 'won'  ? '#3fb950' : b.result === 'lost' ? '#f85149' : '#8b949e';
        const pricePct  = b.polyPrice ? `${Math.round(b.polyPrice * 100)}¢` : '—';
        const methIcon  = b.method === 'auto' ? '<span title="Auto via GitHub Action">🤖</span>' : '<span title="Manuell platziert">✋</span>';
        return `<tr style="border-bottom:1px solid #30363d">
          <td style="padding:9px 12px;font-size:11px;color:#8b949e">${b.date}</td>
          <td style="padding:9px 12px;font-size:12px">${b.home} vs ${b.away}</td>
          <td style="padding:9px 12px;font-size:12px;color:${_marketColor(b.market)}">${b.market}</td>
          <td style="padding:9px 12px;font-size:12px;color:#a78bfa">${pricePct}</td>
          <td style="padding:9px 12px;font-size:14px;text-align:center">${methIcon}</td>
          <td style="padding:9px 12px;color:${resColor};font-weight:700">${resIcon}</td>
        </tr>`;
      }).join('');

  return `
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:16px">
      ${statCards.map(c => `
        <div style="background:#161b22;border:1px solid #30363d;border-radius:10px;padding:14px 16px">
          <div style="font-size:10px;color:#8b949e;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px;font-weight:700">${c.label}</div>
          <div style="font-size:24px;font-weight:800;color:${c.color};line-height:1.1">${c.value}</div>
          <div style="font-size:11px;color:#8b949e;margin-top:4px">${c.sub}</div>
        </div>`).join('')}
    </div>
    ${sessBets.length > 0 ? `
    <div style="background:#1a2340;border:1px solid #a78bfa44;border-radius:8px;padding:10px 14px;margin-bottom:10px;font-size:12px;display:flex;align-items:center;gap:10px;flex-wrap:wrap">
      <span style="color:#a78bfa;font-weight:700">⚡ ${sessBets.length} Bet${sessBets.length!==1?'s':''} nur im Session-Memory (localStorage leer)</span>
      <button onclick="
        const sess=Object.values(window._polyPlacedThisSession||{});
        const bets=_getPolyBets();
        const ids=new Set(bets.map(b=>b.id));
        sess.filter(b=>!ids.has(b.id)).forEach(b=>bets.push(b));
        _savePolyBets(bets);
        const n=_getPolyBets().length;
        if(n>0){_polyToast('✅ '+sess.length+' Bet(s) in localStorage gespeichert');}
        else{_polyToast('❌ localStorage-Save fehlgeschlagen — prüf Browser-Konsole');}
        document.getElementById('polyStatsSection').innerHTML=renderPolyStats();
      " style="background:#a78bfa22;border:1px solid #a78bfa55;border-radius:6px;color:#a78bfa;font-size:11px;font-weight:700;padding:4px 12px;cursor:pointer;font-family:inherit">
        💾 Jetzt in localStorage speichern
      </button>
    </div>` : ''}
    <div style="background:#161b22;border:1px solid #30363d;border-radius:10px;overflow:hidden">
      <div style="padding:12px 16px;border-bottom:1px solid #30363d;display:flex;align-items:center;justify-content:space-between">
        <span style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:#8b949e">Letzte Bets</span>
        <div style="display:flex;gap:6px">
          <button onclick="_syncBetsFromHistory(false).then(()=>{document.getElementById('polyStatsSection').innerHTML=renderPolyStats();const g=document.getElementById('polyPickGrid');if(g)g.innerHTML=renderPolyPickCards();})" style="background:none;border:1px solid #a78bfa55;border-radius:6px;color:#a78bfa;font-size:11px;font-weight:600;padding:4px 10px;cursor:pointer;font-family:inherit">📥 Sync Repo</button>
          <button onclick="polyAutoResolve()" style="background:none;border:1px solid #3fb95055;border-radius:6px;color:#3fb950;font-size:11px;font-weight:600;padding:4px 10px;cursor:pointer;font-family:inherit">🔄 Auto-auswerten</button>
          <button onclick="polyManualResolve()" style="background:none;border:1px solid #30363d;border-radius:6px;color:#8b949e;font-size:11px;font-weight:600;padding:4px 10px;cursor:pointer;font-family:inherit">✏️ Manuell</button>
          <button onclick="if(confirm('Alle Poly-Bets komplett löschen? (Neustart)')){localStorage.removeItem('betedge_poly_bets');window._polyPlacedThisSession={};document.getElementById('polyStatsSection').innerHTML=renderPolyStats();const g=document.getElementById('polyPickGrid');if(g)g.innerHTML=renderPolyPickCards();_polyToast('🗑️ Poly-Bets zurückgesetzt');}" style="background:none;border:1px solid #f8514933;border-radius:6px;color:#f85149;font-size:11px;font-weight:600;padding:4px 10px;cursor:pointer;font-family:inherit">🗑️ Reset</button>
        </div>
      </div>
      <table style="width:100%;border-collapse:collapse">
        <thead style="background:#1c2128">
          <tr>
            <th style="padding:8px 12px;text-align:left;font-size:9px;color:#8b949e;font-weight:700;text-transform:uppercase;letter-spacing:.5px">Datum</th>
            <th style="padding:8px 12px;text-align:left;font-size:9px;color:#8b949e;font-weight:700;text-transform:uppercase;letter-spacing:.5px">Spiel</th>
            <th style="padding:8px 12px;text-align:left;font-size:9px;color:#8b949e;font-weight:700;text-transform:uppercase;letter-spacing:.5px">Markt</th>
            <th style="padding:8px 12px;text-align:left;font-size:9px;color:#8b949e;font-weight:700;text-transform:uppercase;letter-spacing:.5px">Preis</th>
            <th style="padding:8px 12px;text-align:center;font-size:9px;color:#8b949e;font-weight:700;text-transform:uppercase;letter-spacing:.5px">Via</th>
            <th style="padding:8px 12px;text-align:left;font-size:9px;color:#8b949e;font-weight:700;text-transform:uppercase;letter-spacing:.5px">Result</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

// ── 6b. AUTO-RESOLVE ────────────────────────────────────
// Fetches picks_history.json from the local server (or GitHub Pages as fallback),
// matches each pending Polymarket bet to a resolved match entry, and sets result.

function _normTeamResolve(n) {
  return (n || '').toLowerCase()
    .replace(/[àáâãäå]/g, 'a').replace(/[èéêë]/g, 'e')
    .replace(/[ìíîï]/g, 'i').replace(/[òóôõöø]/g, 'o').replace(/[ùúûü]/g, 'u')
    .replace(/[ß]/g, 'ss').replace(/[şș]/g, 's').replace(/[ğ]/g, 'g').replace(/[ı]/g, 'i')
    .replace(/\b(fc|sv|sc|ac|ss|rc|sk|vfb|vfl|rb|tsv|as|us|cd|cf|nk|hnk|1\.fc)\b/g, '')
    .replace(/[^a-z0-9]/g, '').trim();
}

function _matchHistoryEntry(bet, history) {
  // bet.date is "DD.MM.YYYY"; history entries have .date "DD.MM.YYYY"
  const hN = _normTeamResolve(bet.home);
  const aN = _normTeamResolve(bet.away);
  for (const entry of history) {
    if (entry.date !== bet.date) continue;
    const eH = _normTeamResolve(entry.home);
    const eA = _normTeamResolve(entry.away);
    const homeOk = eH === hN || eH.includes(hN) || hN.includes(eH);
    const awayOk = eA === aN || eA.includes(aN) || aN.includes(eA);
    if (homeOk && awayOk) return entry;
  }
  return null;
}

function _resolveBetFromEntry(bet, entry) {
  // 1. Try to find exact match by market name in history picks
  const pick = (entry.picks || []).find(p => p.market === bet.market);
  if (pick?.result === 'win')  return 'won';
  if (pick?.result === 'loss') return 'lost';

  // 2. Fallback: compute from finalScore for basic markets
  const fs = entry.finalScore;
  if (!fs) return null;
  const [h, a] = fs.split(':').map(Number);
  if (isNaN(h) || isNaN(a)) return null;

  const m = bet.market;
  if (m === 'Heimsieg')                return h > a  ? 'won' : 'lost';
  if (m === 'Auswärtssieg')            return a > h  ? 'won' : 'lost';
  if (m === 'Unentschieden')           return h === a ? 'won' : 'lost';
  if (m === 'Beide Teams treffen')     return (h > 0 && a > 0) ? 'won' : 'lost';
  if (m === 'Over 2.5 Tore')          return (h + a) > 2.5 ? 'won' : 'lost';
  if (m === 'Under 2.5 Tore')         return (h + a) < 2.5 ? 'won' : 'lost';
  if (m === 'Over 3.5 Tore')          return (h + a) > 3.5 ? 'won' : 'lost';
  if (m === 'Under 3.5 Tore')         return (h + a) < 3.5 ? 'won' : 'lost';
  if (m === 'Doppelte Chance: 1X')    return h >= a ? 'won' : 'lost';
  if (m === 'Doppelte Chance: X2')    return a >= h ? 'won' : 'lost';
  if (m === 'Doppelte Chance: 12')    return h !== a ? 'won' : 'lost';

  return null; // specialty market not found in history picks
}

async function polyAutoResolve(silent = false) {
  const bets    = _getPolyBets();
  const pending = bets.filter(b => !b.result);
  if (!pending.length) {
    if (!silent) _polyToast('Keine offenen Bets');
    return;
  }

  // ── 1. Load picks_history.json (primary resolve source) ─────────────────
  let history = null;
  for (const url of ['http://localhost:3001/picks_history', 'https://blummabet.github.io/Betting-Dashboard/picks_history.json']) {
    try {
      const r = await fetch(url);
      if (r.ok) { history = await r.json(); break; }
    } catch (e) { /* try next */ }
  }

  // ── 2. Load results-cache.json (fallback — resolves directly from score) ──
  let resultsCache = null;
  for (const url of ['http://localhost:3001/results-cache', 'https://blummabet.github.io/Betting-Dashboard/results-cache.json']) {
    try {
      const r = await fetch(url, { cache: 'no-store' });
      if (r.ok) { const d = await r.json(); resultsCache = d.fixtures || d; break; }
    } catch (e) { /* try next */ }
  }

  if (!history && !resultsCache) {
    if (!silent) _polyToast('❌ Spielergebnisse nicht erreichbar');
    return;
  }

  // Build results-cache lookup: "norm_home|norm_away" → fixture
  const _cNorm = s => (s||'').toLowerCase().replace(/\b(fc|sv|sc|ac|as|us|cd|sk|rb|bv|vv|nk|fk|cf|ss|if|kf|pfc)\b/g,' ').replace(/[^a-z0-9 ]/g,' ').replace(/\s+/g,' ').trim();
  const cacheLookup = {};
  if (Array.isArray(resultsCache)) {
    for (const fx of resultsCache) {
      if (fx.goalsHome == null) continue;
      cacheLookup[`${_cNorm(fx.home)}|${_cNorm(fx.away)}`] = fx;
    }
  }

  let resolvedCount = 0;
  for (const bet of bets) {
    if (bet.result) continue;

    // Try picks_history first (most detailed — has per-market results)
    if (Array.isArray(history)) {
      const entry = _matchHistoryEntry(bet, history);
      if (entry?.resolved) {
        const result = _resolveBetFromEntry(bet, entry);
        if (result) { bet.result = result; resolvedCount++; continue; }
      }
    }

    // Fallback: resolve directly from results-cache.json score
    if (Object.keys(cacheLookup).length) {
      const hN = _cNorm(bet.home);
      const aN = _cNorm(bet.away);
      const fx = cacheLookup[`${hN}|${aN}`]
              || Object.entries(cacheLookup).find(([k]) => {
                   const [kh, ka] = k.split('|');
                   return (kh.includes(hN) || hN.includes(kh)) && (ka.includes(aN) || aN.includes(ka));
                 })?.[1];
      if (fx) {
        // Check date match (bet.date is "DD.MM.YYYY", fx.date is "YYYY-MM-DD")
        const [bd, bm, by] = (bet.date || '').split('.');
        const betIso = by && bm && bd ? `${by}-${bm}-${bd}` : '';
        const dateDiff = betIso && fx.date ? Math.abs(new Date(betIso) - new Date(fx.date)) / 86400000 : 99;
        if (dateDiff <= 1) {
          const h = fx.goalsHome, a = fx.goalsAway;
          const score = `${h}:${a}`;
          const fakeEntry = { resolved: true, finalScore: score, picks: [] };
          const result = _resolveBetFromEntry(bet, fakeEntry);
          if (result) { bet.result = result; resolvedCount++; }
        }
      }
    }
  }

  _savePolyBets(bets);

  const stats = document.getElementById('polyStatsSection');
  if (stats) stats.innerHTML = renderPolyStats();

  if (!silent) {
    _polyToast(resolvedCount > 0
      ? `✅ ${resolvedCount} Bet${resolvedCount !== 1 ? 's' : ''} automatisch ausgewertet`
      : '⏳ Noch keine neuen Ergebnisse verfügbar');
  } else if (resolvedCount > 0) {
    _polyToast(`✅ ${resolvedCount} Bet${resolvedCount !== 1 ? 's' : ''} automatisch ausgewertet`);
  }
}

// ── 7. CONFIRMATION FLOW ────────────────────────────────

function polyMarkPlaced() {
  // Save all selected picks as "pending" in localStorage — user has placed them manually on Polymarket
  const sel = _polyState.picks.filter(p => _polyState.selected.has(p.id));
  if (sel.length === 0) return;

  if (!window._polyPlacedThisSession) window._polyPlacedThisSession = {};
  const bets = _getPolyBets();
  for (const p of sel) {
    const pd = _polyState.prices[p.id];
    const entry = {
      id:        p.id,
      date:      p.date || _polyState.dateStr,
      home:      p.home,
      away:      p.away,
      market:    p.market,
      league:    p.league,
      stake:     POLY_STAKE,
      polyPrice: pd?.found ? pd.price : null,
      placed:    new Date().toISOString(),
      method:    'manual',
      result:    null,
    };
    bets.push(entry);
    window._polyPlacedThisSession[p.id] = entry;
  }
  _savePolyBets(bets);
  _polyState.selected.clear();
  _polyRefreshStickyBar();
  document.getElementById('polyPickGrid').innerHTML = renderPolyPickCards();
  document.getElementById('polyStatsSection').innerHTML = renderPolyStats();
  _polyToast(`✅ ${sel.length} Bet${sel.length !== 1 ? 's' : ''} als platziert gespeichert`);
}

function polyTogglePick(id) {
  if (_polyState.selected.has(id)) _polyState.selected.delete(id);
  else _polyState.selected.add(id);
  _polyRefreshStickyBar();
  const grid = document.getElementById('polyPickGrid');
  if (grid) grid.innerHTML = renderPolyPickCards();
}

function polySelectAll() {
  _polyState.picks.forEach(p => {
    // Only select picks where a market was found (or still loading)
    const pd = _polyState.prices[p.id];
    if (!pd || pd.loading || pd.found) _polyState.selected.add(p.id);
  });
  _polyRefreshStickyBar();
  const grid = document.getElementById('polyPickGrid');
  if (grid) grid.innerHTML = renderPolyPickCards();
}

function polySelectNone() {
  _polyState.selected.clear();
  _polyRefreshStickyBar();
  const grid = document.getElementById('polyPickGrid');
  if (grid) grid.innerHTML = renderPolyPickCards();
}

function _polyRefreshStickyBar() {
  const bar  = document.getElementById('polyStickyBar');
  const lbl  = document.getElementById('polyStickyCount');
  if (!bar) return;
  const n     = _polyState.selected.size;
  const stake = (n * POLY_STAKE).toFixed(2);
  bar.style.display = n > 0 ? 'flex' : 'none';
  if (lbl) lbl.textContent = `${n} Pick${n !== 1 ? 's'  : ''} ausgewählt · €${stake} Einsatz`;
}

// ── GitHub PAT helpers ──────────────────────────────────

const POLY_GITHUB_REPO = 'blummabet/Betting-Dashboard';

function _getGithubPAT() {
  try { return localStorage.getItem('betedge_github_pat') || ''; } catch { return ''; }
}
function _saveGithubPAT(token) {
  try { localStorage.setItem('betedge_github_pat', token.trim()); } catch (e) {}
}

function polyOpenSettings() {
  const current = _getGithubPAT();
  const masked  = current ? '•'.repeat(Math.min(current.length, 20)) : '';
  document.getElementById('polyModalBody').innerHTML = `
    <div style="font-size:17px;font-weight:800;margin-bottom:6px;color:#e6edf3">⚙️ Einstellungen</div>
    <div style="font-size:12px;color:#8b949e;margin-bottom:20px">Einmalig — Token bleibt nur in deinem Browser</div>

    <label style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:#8b949e;display:block;margin-bottom:6px">
      GitHub Personal Access Token
    </label>
    <div style="display:flex;gap:8px;margin-bottom:6px">
      <input id="polyPatInput" type="password" placeholder="${masked || 'ghp_...'}"
        style="flex:1;background:#0d1117;border:1px solid #30363d;border-radius:8px;color:#e6edf3;font-size:13px;padding:10px 12px;font-family:monospace;outline:none"
        oninput="this.style.borderColor='#a78bfa'" />
      <button onclick="polySavePAT()"
        style="background:#a78bfa;border:none;border-radius:8px;color:#000;font-size:13px;font-weight:700;padding:10px 16px;cursor:pointer;font-family:inherit">
        Speichern
      </button>
    </div>
    <div style="font-size:11px;color:#8b949e;margin-bottom:20px;line-height:1.5">
      Scope: <code style="color:#00d4a1;background:#00d4a110;padding:1px 5px;border-radius:3px">repo</code>
      · Erstellen unter github.com → Settings → Developer settings → Tokens (classic)
    </div>

    <div style="background:#0d1117;border:1px solid #30363d;border-radius:8px;padding:12px 14px">
      <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:#8b949e;margin-bottom:8px">Status</div>
      <div style="font-size:13px;color:${current ? '#3fb950' : '#f85149'}">
        ${current ? '✅ Token gespeichert' : '❌ Kein Token — Bets können nicht ausgelöst werden'}
      </div>
      <div style="font-size:11px;color:#8b949e;margin-top:4px">Repo: ${POLY_GITHUB_REPO}</div>
    </div>`;
  document.getElementById('polyModal').style.display = 'flex';
}

function polySavePAT() {
  const val = document.getElementById('polyPatInput')?.value?.trim();
  if (!val) { _polyToast('❌ Kein Token eingegeben'); return; }
  if (!val.startsWith('ghp_') && !val.startsWith('github_pat_')) {
    _polyToast('⚠️ Sieht nicht wie ein GitHub Token aus');
  }
  _saveGithubPAT(val);
  document.getElementById('polyModal').style.display = 'none';
  _polyToast('✅ GitHub Token gespeichert');
  // Refresh settings button color
  const btn = document.getElementById('polySettingsBtn');
  if (btn) { btn.style.color = '#3fb950'; btn.style.borderColor = '#3fb95055'; }
}

// ── GitHub dispatch ─────────────────────────────────────

async function _callGitHubDispatch(orders) {
  const pat = _getGithubPAT();
  if (!pat) {
    polyOpenSettings();
    return false;
  }

  const resp = await fetch(`https://api.github.com/repos/${POLY_GITHUB_REPO}/dispatches`, {
    method:  'POST',
    headers: {
      'Authorization': `Bearer ${pat}`,
      'Accept':        'application/vnd.github+json',
      'Content-Type':  'application/json',
      'X-GitHub-Api-Version': '2022-11-28',
    },
    body: JSON.stringify({
      event_type:     'place-poly-bets',
      client_payload: { orders },
    }),
  });

  return resp.ok || resp.status === 204; // GitHub returns 204 No Content on success
}

// ── Confirm modal ───────────────────────────────────────

function polyConfirm() {
  const sel = _polyState.picks.filter(p => _polyState.selected.has(p.id));
  if (sel.length === 0) return;

  const pat = _getGithubPAT();

  const rows = sel.map(p => {
    const pd       = _polyState.prices[p.id];
    const priceStr = pd?.found ? `${Math.round(pd.price * 100)}¢` : '—';
    const oddsStr  = pd?.found ? (1 / pd.price).toFixed(2) : '—';
    return `<tr style="border-bottom:1px solid #1c2128">
      <td style="padding:9px 12px;font-size:13px">${p.leagueFlag} ${p.home} vs ${p.away}</td>
      <td style="padding:9px 12px;font-size:13px;color:${_marketColor(p.market)}">${_marketIcon(p.market)} ${p.market}</td>
      <td style="padding:9px 12px;font-size:13px;color:#a78bfa;font-weight:700">${priceStr}</td>
      <td style="padding:9px 12px;font-size:13px;color:#8b949e">${oddsStr}</td>
      <td style="padding:9px 12px;font-size:13px;color:#3fb950;font-weight:700">€${POLY_STAKE}</td>
    </tr>`;
  }).join('');

  const ordersObj = sel.map(p => ({
    home:      p.home,
    away:      p.away,
    market:    p.market,
    league:    p.league,
    bookyOdds: p.odds,
    stake:     POLY_STAKE,
    polyPrice: _polyState.prices[p.id]?.found ? _polyState.prices[p.id].price : null,
    eventUrl:  _polyState.prices[p.id]?.eventUrl  || null,
    eventTitle: _polyState.prices[p.id]?.eventTitle || null,
  }));

  window._polyOrdersSel = sel;
  window._polyOrdersObj = ordersObj;

  document.getElementById('polyModalBody').innerHTML = `
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:18px">
      <span style="font-size:24px">🟣</span>
      <div>
        <div style="font-size:17px;font-weight:800;color:#e6edf3">Bestellübersicht</div>
        <div style="font-size:12px;color:#8b949e">${sel.length} Pick${sel.length !== 1 ? 's' : ''} · €${(sel.length * POLY_STAKE).toFixed(2)} Total</div>
      </div>
    </div>

    <div style="background:#0d1117;border-radius:8px;overflow:hidden;margin-bottom:16px">
      <table style="width:100%;border-collapse:collapse">
        <thead style="background:#1c2128">
          <tr>
            <th style="padding:8px 12px;text-align:left;font-size:9px;color:#8b949e;font-weight:700;text-transform:uppercase">Spiel</th>
            <th style="padding:8px 12px;text-align:left;font-size:9px;color:#8b949e;font-weight:700;text-transform:uppercase">Markt</th>
            <th style="padding:8px 12px;text-align:left;font-size:9px;color:#8b949e;font-weight:700;text-transform:uppercase">Preis</th>
            <th style="padding:8px 12px;text-align:left;font-size:9px;color:#8b949e;font-weight:700;text-transform:uppercase">Odds</th>
            <th style="padding:8px 12px;text-align:left;font-size:9px;color:#8b949e;font-weight:700;text-transform:uppercase">Einsatz</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>

    ${!pat ? `<div style="background:#f8514911;border:1px solid #f8514933;border-radius:8px;padding:10px 14px;margin-bottom:14px;font-size:12px;color:#f85149">
      ⚠️ Kein GitHub Token gesetzt.
      <button onclick="polyOpenSettings()" style="background:none;border:none;color:#f85149;cursor:pointer;font-size:12px;font-weight:700;padding:0;margin-left:6px;text-decoration:underline;font-family:inherit">Jetzt einrichten →</button>
    </div>` : ''}

    <button id="polyDispatchBtn" onclick="polyDispatch()"
      style="width:100%;background:linear-gradient(135deg,#a78bfa,#7c3aed);border:none;border-radius:10px;color:#fff;font-size:15px;font-weight:800;padding:14px;cursor:pointer;font-family:inherit;letter-spacing:.02em;box-shadow:0 2px 16px #a78bfa44;margin-bottom:10px;${!pat ? 'opacity:.5;' : ''}">
      🟣 Bets via GitHub auslösen
    </button>
    <div style="text-align:center;font-size:11px;color:#8b949e">
      Wallet: Polygon USDC · Private Key bleibt in GitHub Secrets
    </div>`;

  document.getElementById('polyModal').style.display = 'flex';
}

async function polyDispatch() {
  const orders = window._polyOrdersObj;
  const sel    = window._polyOrdersSel;
  if (!orders?.length) return;

  const btn = document.getElementById('polyDispatchBtn');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Wird ausgelöst…'; }

  // ── Save bets to localStorage BEFORE dispatch ──────────────────────────────
  // Also track in window._polyPlacedThisSession (session memory) as fallback
  // in case localStorage fails — picks still show as "placed" within this session.
  if (!window._polyPlacedThisSession) window._polyPlacedThisSession = {};

  const savedBets = [];
  try {
    const bets = _getPolyBets();
    const countBefore = bets.length;
    for (const p of sel) {
      const pd = _polyState.prices[p.id];
      const entry = {
        id:        p.id,
        date:      p.date || _polyState.dateStr,
        home:      p.home,
        away:      p.away,
        market:    p.market,
        league:    p.league,
        stake:     POLY_STAKE,
        polyPrice: pd?.found ? pd.price : null,
        placed:    new Date().toISOString(),
        method:    'auto',
        result:    null,
      };
      bets.push(entry);
      savedBets.push(entry);
      // Session memory fallback — always works, survives localStorage failure
      window._polyPlacedThisSession[p.id] = entry;
    }
    _savePolyBets(bets);
    // Verify save actually worked
    const countAfter = _getPolyBets().length;
    if (countAfter > countBefore) {
      console.log(`[PolyDispatch] ✅ ${sel.length} bet(s) in localStorage (total: ${countAfter})`);
    } else {
      console.warn('[PolyDispatch] ⚠️ localStorage nicht erhöht — Fallback auf Session-Memory aktiv');
    }
  } catch(saveErr) {
    console.error('[PolyDispatch] save error:', saveErr);
    // Still track in session memory even if localStorage failed
    for (const p of sel) {
      window._polyPlacedThisSession[p.id] = { id: p.id, result: null };
    }
  }

  // ── Refresh stats immediately so bets appear ───────────────────────────────
  const statsEl = document.getElementById('polyStatsSection');
  if (statsEl) statsEl.innerHTML = renderPolyStats();

  // ── Dispatch to GitHub ─────────────────────────────────────────────────────
  let ok = false;
  try {
    ok = await _callGitHubDispatch(orders);
  } catch(dispatchErr) {
    console.error('[PolyDispatch] GitHub dispatch threw:', dispatchErr);
    // Bets already saved above — treat as unknown (action may have triggered)
    ok = true;
  }

  if (ok) {
    _polyState.selected.clear();
    _polyRefreshStickyBar();
    const modal = document.getElementById('polyModal');
    if (modal) modal.style.display = 'none';
    const grid = document.getElementById('polyPickGrid');
    if (grid) grid.innerHTML = renderPolyPickCards();
    if (statsEl) statsEl.innerHTML = renderPolyStats();
    _polyToast(`🟣 ${sel.length} Bet${sel.length !== 1 ? 's' : ''} ausgelöst via GitHub Action!`);
  } else {
    if (btn) { btn.disabled = false; btn.textContent = '🟣 Bets via GitHub auslösen'; }
    _polyToast('❌ GitHub API Fehler — Token prüfen');
    polyOpenSettings();
  }
}

function polySavePending() {
  const sel  = window._polyOrdersSel || [];
  const bets = _getPolyBets();
  for (const p of sel) {
    const pd = _polyState.prices[p.id];
    bets.push({
      id:         p.id,
      date:       p.date || _polyState.dateStr,
      home:       p.home,
      away:       p.away,
      market:     p.market,
      league:     p.league,
      stake:      POLY_STAKE,
      polyPrice:  pd?.found ? pd.price : null,
      placed:     new Date().toISOString(),
      method:     'manual',
      result:     null,
    });
  }
  _savePolyBets(bets);
  document.getElementById('polyModal').style.display = 'none';
  _polyState.selected.clear();
  _polyRefreshStickyBar();
  const grid = document.getElementById('polyPickGrid');
  if (grid) grid.innerHTML = renderPolyPickCards();
  const stats = document.getElementById('polyStatsSection');
  if (stats) stats.innerHTML = renderPolyStats();
  _polyToast(`✅ ${sel.length} Bet${sel.length !== 1 ? 's' : ''} als platziert gespeichert`);
}

function polyManualResolve() {
  const bets = _getPolyBets();
  const open = bets.filter(b => !b.result);
  if (open.length === 0) { _polyToast('Keine offenen Bets'); return; }

  const rows = open.map((b, i) => `
    <div style="background:#0d1117;border-radius:8px;padding:12px 14px;margin-bottom:8px">
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
        <div style="flex:1;min-width:160px">
          <div style="font-size:13px;font-weight:600;color:#e6edf3">${b.home} vs ${b.away}</div>
          <div style="font-size:11px;color:${_marketColor(b.market)};margin-top:2px">${b.market} · ${b.polyPrice ? Math.round(b.polyPrice*100)+'¢' : '—'} · ${b.date}</div>
        </div>
        <div style="display:flex;gap:6px;flex-shrink:0">
          <button onclick="polySetResult(${i},'won')"  style="background:#3fb95022;border:1px solid #3fb95055;border-radius:6px;color:#3fb950;font-size:12px;font-weight:600;padding:6px 10px;cursor:pointer;font-family:inherit">✅ Gewonnen</button>
          <button onclick="polySetResult(${i},'lost')" style="background:#f8514922;border:1px solid #f8514955;border-radius:6px;color:#f85149;font-size:12px;font-weight:600;padding:6px 10px;cursor:pointer;font-family:inherit">❌ Verloren</button>
          <button onclick="polySetResult(${i},'void')" style="background:#8b949e22;border:1px solid #8b949e44;border-radius:6px;color:#8b949e;font-size:12px;font-weight:600;padding:6px 10px;cursor:pointer;font-family:inherit">— Void</button>
          <button onclick="polyDeleteBet(${i})"        style="background:#f8514911;border:1px solid #f8514933;border-radius:6px;color:#f85149;font-size:12px;font-weight:600;padding:6px 10px;cursor:pointer;font-family:inherit">🗑️</button>
        </div>
      </div>
    </div>`).join('');

  window._polyOpenBets = open;

  document.getElementById('polyModalBody').innerHTML = `
    <div style="font-size:17px;font-weight:800;margin-bottom:16px;color:#e6edf3">✏️ Ergebnisse einpflegen</div>
    <div style="font-size:12px;color:#8b949e;margin-bottom:16px">${open.length} offene Bet${open.length !== 1 ? 's' : ''}</div>
    ${rows}`;
  document.getElementById('polyModal').style.display = 'flex';
}

function polySetResult(idx, result) {
  const open = window._polyOpenBets;
  if (!open?.[idx]) return;
  const bets    = _getPolyBets();
  const target  = open[idx];
  const betIdx  = bets.findIndex(b => b.id === target.id && b.placed === target.placed);
  if (betIdx >= 0) {
    bets[betIdx].result = result;
    _savePolyBets(bets);
    const icon = result === 'won' ? '✅ Gewonnen!' : result === 'lost' ? '❌ Verloren' : '— Void';
    _polyToast(icon);
    setTimeout(() => {
      document.getElementById('polyModal').style.display = 'none';
      const stats = document.getElementById('polyStatsSection');
      if (stats) stats.innerHTML = renderPolyStats();
    }, 600);
  }
}

function polyDeleteBet(idx) {
  const open = window._polyOpenBets;
  if (!open?.[idx]) return;
  const bets   = _getPolyBets();
  const target = open[idx];
  const betIdx = bets.findIndex(b => b.id === target.id && b.placed === target.placed);
  if (betIdx >= 0) {
    bets.splice(betIdx, 1);
    _savePolyBets(bets);
    open.splice(idx, 1);
    window._polyOpenBets = open;
    _polyToast('🗑️ Bet gelöscht');
    setTimeout(() => {
      if (open.length === 0) {
        document.getElementById('polyModal').style.display = 'none';
      } else {
        polyManualResolve();
      }
      const stats = document.getElementById('polyStatsSection');
      if (stats) stats.innerHTML = renderPolyStats();
    }, 400);
  }
}

function _polyToast(msg) {
  const t = document.createElement('div');
  t.style.cssText = 'position:fixed;bottom:90px;left:50%;transform:translateX(-50%);'
    + 'background:#3fb950;color:#000;font-weight:700;font-size:13px;'
    + 'padding:10px 22px;border-radius:20px;z-index:9999;pointer-events:none;'
    + 'box-shadow:0 4px 20px rgba(0,0,0,.4)';
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 2800);
}

// ── 8. ENTRY POINT ──────────────────────────────────────

function initPolymarket() {
  const panel = document.getElementById('polymarketPanel');
  if (!panel) return;

  // ── Wait for live odds before computing picks ─────────────────────────────
  // loadAllOdds() runs async after page load. If it hasn't finished yet,
  // show a loading state and let the loadAllOdds callback trigger us again.
  // This prevents a two-phase render (stale picks → live picks) that causes
  // a jarring flash and may show wrong picks (e.g. ITA instead of ENG).
  if (!window._oddsLoaded) {
    _polyState.dateStr = _todayStr();     // remember chosen date for deferred render
    window._pendingPolyInit = true;       // signal: call initPolymarket() when odds ready
    panel.innerHTML = `
      <div style="text-align:center;padding:80px 24px;color:#8b949e">
        <div style="font-size:36px;margin-bottom:14px">⏳</div>
        <div style="font-weight:700;font-size:15px;margin-bottom:6px;color:#e6edf3">Live-Quoten werden geladen…</div>
        <div style="font-size:12px">Picks werden berechnet sobald Marktdaten verfügbar sind</div>
      </div>`;
    return;
  }

  // Proactively free localStorage quota before any saves
  _trimLocalStorageQuota();

  const dateStr = _polyState.dateStr || _todayStr();
  _polyState.dateStr  = dateStr;
  _polyState.picks    = getPolyPicks(dateStr);
  _polyState.prices   = {};
  _polyState.selected = new Set(_polyState.picks.map(p => p.id)); // start: all selected

  // Sync placed bets from picks_history.json (repo-based, survives localStorage failures)
  _syncBetsFromHistory(true).then(n => {
    if (n > 0) {
      // Re-render pick cards to show placed indicator
      const grid = document.getElementById('polyPickGrid');
      if (grid) grid.innerHTML = renderPolyPickCards();
      const stats = document.getElementById('polyStatsSection');
      if (stats) stats.innerHTML = renderPolyStats();
    }
  });

  const n = _polyState.picks.length;

  panel.innerHTML = `
    <!-- ── HEADER ────────────────────────────────────── -->
    <div style="display:flex;align-items:flex-start;gap:12px;margin-bottom:20px;flex-wrap:wrap">
      <div>
        <h2 style="margin:0;font-size:22px;font-weight:900;color:#a78bfa;letter-spacing:-.01em">🟣 Polymarket</h2>
        <div id="polyDateSub" style="font-size:12px;color:#8b949e;margin-top:3px">${dateStr} &nbsp;·&nbsp; ${n} eligible pick${n !== 1 ? 's' : ''}</div>
      </div>
      <div style="margin-left:auto;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        ${(() => {
          const dates = _getAvailableDates();
          const weekdays = ['So','Mo','Di','Mi','Do','Fr','Sa'];
          const opts = dates.map(d => {
            const [dd,mm,yy] = d.split('.');
            const wd = weekdays[new Date(`${yy}-${mm}-${dd}`).getDay()];
            return `<option value="${d}" ${d === dateStr ? 'selected' : ''}>${wd} ${dd}.${mm}.</option>`;
          }).join('');
          return dates.length > 1
            ? `<select onchange="polyChangeDate(this.value)" style="background:#161b22;border:1px solid #30363d;border-radius:8px;color:#e6edf3;font-size:12px;padding:7px 10px;cursor:pointer;font-family:inherit;outline:none">${opts}</select>`
            : '';
        })()}
        <button onclick="polySelectAll()"  style="background:none;border:1px solid #30363d;border-radius:8px;color:#8b949e;font-size:11px;font-weight:600;padding:7px 13px;cursor:pointer;font-family:inherit;transition:border-color .15s" onmouseover="this.style.borderColor='#a78bfa'" onmouseout="this.style.borderColor='#30363d'">☑️ Alle</button>
        <button onclick="polySelectNone()" style="background:none;border:1px solid #30363d;border-radius:8px;color:#8b949e;font-size:11px;font-weight:600;padding:7px 13px;cursor:pointer;font-family:inherit;transition:border-color .15s" onmouseover="this.style.borderColor='#a78bfa'" onmouseout="this.style.borderColor='#30363d'">⬜ Keine</button>
        <button onclick="initPolymarket()" style="background:none;border:1px solid #30363d;border-radius:8px;color:#8b949e;font-size:11px;font-weight:600;padding:7px 13px;cursor:pointer;font-family:inherit;transition:border-color .15s" onmouseover="this.style.borderColor='#00d4a1'" onmouseout="this.style.borderColor='#30363d'">🔄 Refresh</button>
        <button id="polySettingsBtn" onclick="polyOpenSettings()" style="background:none;border:1px solid #30363d;border-radius:8px;color:#8b949e;font-size:11px;font-weight:600;padding:7px 13px;cursor:pointer;font-family:inherit;transition:border-color .15s" onmouseover="this.style.borderColor='#f5c518'" onmouseout="this.style.borderColor='#30363d'">⚙️ PAT</button>
      </div>
    </div>

    <!-- ── SETUP HINT ─────────────────────────────────── -->
    <div id="polySetupHint" style="background:#a78bfa0d;border:1px solid #a78bfa33;border-radius:10px;padding:12px 16px;margin-bottom:20px;display:flex;align-items:flex-start;gap:10px">
      <span style="font-size:18px;margin-top:1px">💡</span>
      <div style="font-size:12px;color:#8b949e;line-height:1.6;flex:1">
        <strong style="color:#a78bfa">Einmalig:</strong> USDC-Allowance im Polymarket UI setzen.
        Dann Private Key in <code style="font-size:11px;color:#00d4a1;background:#00d4a110;padding:1px 5px;border-radius:4px">.env</code> hinterlegen
        und <code style="font-size:11px;color:#00d4a1;background:#00d4a110;padding:1px 5px;border-radius:4px">polymarket_bet.py --setup</code> ausführen.
      </div>
      <button onclick="document.getElementById('polySetupHint').style.display='none'" style="background:none;border:none;color:#8b949e;cursor:pointer;font-size:16px;padding:0;line-height:1;flex-shrink:0">✕</button>
    </div>

    <!-- ── PICKS SECTION ──────────────────────────────── -->
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
      <span id="polyPicksLabel" style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.8px;color:#8b949e">Picks — ${n} verfügbar</span>
      <span style="font-size:11px;color:#8b949e" id="polyPriceStatus">⏳ Polymarket-Preise werden geladen…</span>
    </div>
    <div id="polyPickGrid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:12px;margin-bottom:40px">
      ${renderPolyPickCards()}
    </div>

    <!-- ── STATS SECTION ──────────────────────────────── -->
    <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.8px;color:#8b949e;margin-bottom:10px;margin-top:8px">
      📊 Performance
    </div>
    <div id="polyStatsSection">
      ${renderPolyStats()}
    </div>

    <!-- ── MODAL ──────────────────────────────────────── -->
    <div id="polyModal"
         style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.75);z-index:1000;align-items:center;justify-content:center;padding:16px"
         onclick="if(event.target===this)this.style.display='none'">
      <div style="background:#161b22;border:1px solid #30363d;border-radius:14px;padding:24px;max-width:580px;width:100%;max-height:85vh;overflow-y:auto"
           onclick="event.stopPropagation()">
        <div id="polyModalBody"></div>
        <button onclick="document.getElementById('polyModal').style.display='none'"
                style="width:100%;margin-top:14px;background:none;border:1px solid #30363d;border-radius:8px;color:#8b949e;font-size:13px;padding:10px;cursor:pointer;font-family:inherit">
          Schliessen
        </button>
      </div>
    </div>

    <!-- ── TRADING-KONZEPT: Opening & Closing Trades ─── -->
    <div style="margin-top:48px;border-top:1px solid #21262d;padding-top:32px;">
      <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.8px;color:#8b949e;margin-bottom:16px;">
        💡 Trading-Konzept: Opening &amp; Closing Trades
      </div>

      <!-- Kern-Idee -->
      <div style="background:#a78bfa0d;border:1px solid #a78bfa33;border-radius:12px;padding:20px 22px;margin-bottom:14px;">
        <div style="font-size:13px;font-weight:800;color:#a78bfa;margin-bottom:10px;">🎯 Die Kern-Idee — Gewinn ohne Spielausgang abzuwarten</div>
        <p style="font-size:13px;color:#c9d1d9;line-height:1.7;margin:0 0 10px;">
          Polymarket ist ein Vorhersagemarkt: Ja-Tokens kosten z.B. 0.62 USDC (= Markt sieht 62% Chance).
          Du musst <strong style="color:#e6edf3;">den Ausgang nicht abwarten</strong> — du kannst den Token jederzeit wieder verkaufen.
          Wenn der Marktpreis von 0.62 auf 0.70 steigt, hast du +8 Cent pro Token Gewinn gemacht, ohne dass das Spiel stattgefunden hat.
        </p>
        <p style="font-size:13px;color:#c9d1d9;line-height:1.7;margin:0;">
          Unser System erfasst bereits <strong style="color:#e6edf3;">Opening-Odds</strong> (erster Fetch, eingefroren) und
          <strong style="color:#e6edf3;">Closing-Odds</strong> (letzter Fetch vor Anstoß). Wenn die Bookie-Linie sich verkürzt
          (z.B. Over 2.5: 1.95→1.75), folgt der Poly-Preis fast immer nach — von 0.51 auf ~0.57+.
          Genau dieses Delta ist der Trade.
        </p>
      </div>

      <!-- Wie der Trade funktioniert -->
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
        <div style="background:#0d1117;border:1px solid #21262d;border-radius:10px;padding:16px;">
          <div style="font-size:12px;font-weight:700;color:#3fb950;margin-bottom:10px;">📈 OPENING TRADE — 5–7 Tage vor Anstoß</div>
          <ul style="font-size:12px;color:#8b949e;line-height:1.8;padding-left:16px;margin:0;">
            <li>Pinnacle öffnet Over 2.5 @ <strong style="color:#e6edf3;">1.95</strong> → impliziert <strong style="color:#e6edf3;">51%</strong></li>
            <li>Poly-Preis ist noch bei <strong style="color:#3fb950;">0.50–0.53</strong> (Markt langsamer als Bookie)</li>
            <li><strong style="color:#e6edf3;">Kaufe</strong> den Yes-Token auf Polymarket (z.B. 50 USDC = ~95 Tokens @ 0.525)</li>
            <li>Signal: <code style="font-size:11px;color:#00d4a1;background:#00d4a110;padding:1px 4px;border-radius:3px">pinn_o25_fair</code> vorhanden + unser Modell sieht Edge</li>
          </ul>
        </div>
        <div style="background:#0d1117;border:1px solid #21262d;border-radius:10px;padding:16px;">
          <div style="font-size:12px;font-weight:700;color:#f85149;margin-bottom:10px;">📉 CLOSING TRADE — 2–4 Stunden vor Anstoß</div>
          <ul style="font-size:12px;color:#8b949e;line-height:1.8;padding-left:16px;margin:0;">
            <li>Pinnacle schließt Over 2.5 @ <strong style="color:#e6edf3;">1.73</strong> → impliziert <strong style="color:#e6edf3;">58%</strong></li>
            <li>Poly-Preis ist nachgezogen auf <strong style="color:#e3b341;">0.57–0.60</strong></li>
            <li><strong style="color:#e6edf3;">Verkaufe</strong> den Yes-Token → 95 Tokens × 0.585 = <strong style="color:#3fb950;">55.6 USDC</strong></li>
            <li>Gewinn: <strong style="color:#3fb950;">+5.6 USDC (+11.2%)</strong> — unabhängig vom Spielausgang</li>
          </ul>
        </div>
      </div>

      <!-- Signal-Typen -->
      <div style="background:#0d1117;border:1px solid #21262d;border-radius:10px;padding:16px;margin-bottom:14px;">
        <div style="font-size:12px;font-weight:700;color:#58a6ff;margin-bottom:12px;">⚡ 3 Trade-Signal-Typen die wir bereits berechnen</div>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;">
          <div>
            <div style="font-size:11px;font-weight:700;color:#e3b341;margin-bottom:6px;">1. CLV+ Entry Signal</div>
            <p style="font-size:11px;color:#8b949e;line-height:1.6;margin:0;">
              Wenn <code style="color:#00d4a1;font-size:10px;">pinn_hw_fair</code> / <code style="color:#00d4a1;font-size:10px;">pinn_o25_fair</code>
              vorhanden UND unser Modell sieht Edge: Poly-Markt wurde noch nicht repriced.
              Kauffenster: erste 24–48h nach Opening. Ziel: Poly nachzieht auf Pinnacle-Niveau.
            </p>
          </div>
          <div>
            <div style="font-size:11px;font-weight:700;color:#f85149;margin-bottom:6px;">2. SHARP Money Follow</div>
            <p style="font-size:11px;color:#8b949e;line-height:1.6;margin:0;">
              Wenn <code style="color:#00d4a1;font-size:10px;">_ppO ≥ 8pp</code> oder <code style="color:#00d4a1;font-size:10px;">_ppH ≥ 8pp</code>:
              Sharp-Money hat die Bookie-Linie bereits bewegt. Poly hinkt typisch 6–18h nach.
              Sofort in Richtung des Sharp-Money kaufen bevor Poly repriced.
            </p>
          </div>
          <div>
            <div style="font-size:11px;font-weight:700;color:#3fb950;margin-bottom:6px;">3. Hedge / Teilverkauf</div>
            <p style="font-size:11px;color:#8b949e;line-height:1.6;margin:0;">
              Wir haben bereits eine Bookie-Wette platziert. Line läuft gegen uns (CLV−).
              Poly-Position aufbauen um Bookie-Verlust teilweise zu hedgen — effektiv Risiko
              reduzieren ohne die Bookie-Wette stornieren zu müssen.
            </p>
          </div>
        </div>
      </div>

      <!-- Warum Poly langsamer ist -->
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
        <div style="background:#0d1117;border:1px solid #21262d;border-radius:10px;padding:16px;">
          <div style="font-size:12px;font-weight:700;color:#e6edf3;margin-bottom:10px;">🐢 Warum Poly den Bookies hinterherhinkt</div>
          <ul style="font-size:12px;color:#8b949e;line-height:1.8;padding-left:16px;margin:0;">
            <li>Polymarket: dezentral, AMM-basiert — Preis bewegt sich nur wenn jemand tradet</li>
            <li>Pinnacle: zentralisiert, Sharp-Action fließt sofort in die Linie</li>
            <li>Liquid-Provider auf Poly reagieren auf Bookie-Bewegungen mit Verzögerung</li>
            <li>Gap = unser Arbitrage-Fenster: typisch <strong style="color:#e6edf3;">6–36 Stunden</strong></li>
            <li>Größte Gaps bei Spielen &gt;4 Tage weg (Markt noch dünn besetzt)</li>
          </ul>
        </div>
        <div style="background:#0d1117;border:1px solid #21262d;border-radius:10px;padding:16px;">
          <div style="font-size:12px;font-weight:700;color:#e6edf3;margin-bottom:10px;">⚠️ Risiken &amp; Grenzen</div>
          <ul style="font-size:12px;color:#8b949e;line-height:1.8;padding-left:16px;margin:0;">
            <li><strong style="color:#f5c518;">Spread/Slippage:</strong> Bid-Ask auf Poly 1–3pp → brauchen ≥5pp Bewegung für Profit</li>
            <li><strong style="color:#f5c518;">Liquidität:</strong> dünne Märkte = großer Slippage bei &gt;200 USDC</li>
            <li><strong style="color:#f5c518;">Poly-Resolution:</strong> Markt schliesst erst nach Spielende → kein sofortiger Exit</li>
            <li><strong style="color:#f5c518;">Linie bewegt sich nicht:</strong> wenn Pinnacle stabil bleibt, bleibt auch Poly stabil</li>
            <li><strong style="color:#f5c518;">Gas-Kosten:</strong> Polygon-Transaktionen ~0.01–0.05 USDC/Trade (vernachlässigbar)</li>
          </ul>
        </div>
      </div>

      <!-- Implementierungs-Roadmap -->
      <div style="background:#0d1117;border:1px solid #21262d;border-radius:10px;padding:16px;margin-bottom:14px;">
        <div style="font-size:12px;font-weight:700;color:#e6edf3;margin-bottom:12px;">🗺️ Implementierungs-Roadmap</div>
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;">
          <div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px;">
            <div style="font-size:10px;font-weight:700;color:#3fb950;margin-bottom:6px;">PHASE 1 — Beobachten</div>
            <p style="font-size:11px;color:#8b949e;line-height:1.6;margin:0;">
              Dashboard zeigt Opening-Poly-Preis vs. Closing-Poly-Preis für abgeschlossene Picks.
              Wie groß war das Delta? Wäre der Trade profitabel gewesen?
              <em>Datenbasis schaffen.</em>
            </p>
          </div>
          <div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px;">
            <div style="font-size:10px;font-weight:700;color:#e3b341;margin-bottom:6px;">PHASE 2 — Tracking</div>
            <p style="font-size:11px;color:#8b949e;line-height:1.6;margin:0;">
              <code style="font-size:10px;color:#00d4a1;">fetch_poly_prices.py</code> speichert Poly-Preis-Historie
              pro Pick (Opening + stündlich + Closing). Neues Feld <code style="font-size:10px;color:#00d4a1;">poly_price_open</code>
              in polymarket_prices.json.
            </p>
          </div>
          <div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px;">
            <div style="font-size:10px;font-weight:700;color:#f5c518;margin-bottom:6px;">PHASE 3 — Signal</div>
            <p style="font-size:11px;color:#8b949e;line-height:1.6;margin:0;">
              Dashboard zeigt pro Pick: "Entry @ 0.52 · Aktuell 0.61 · Delta +9pp ·
              <strong style="color:#3fb950;">Trade-Fenster offen</strong>".
              Filterbar nach Min-Delta, Liquidität, Tage bis Anstoß.
            </p>
          </div>
          <div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px;">
            <div style="font-size:10px;font-weight:700;color:#a78bfa;margin-bottom:6px;">PHASE 4 — Automation</div>
            <p style="font-size:11px;color:#8b949e;line-height:1.6;margin:0;">
              <code style="font-size:10px;color:#00d4a1;">polymarket_trade.py</code>: automatischer Opening-Buy wenn
              Signal feuert (Bookie-Edge + Poly underpriced), automatischer Closing-Sell
              X Stunden vor Anstoß.
            </p>
          </div>
        </div>
      </div>

      <!-- API-Möglichkeiten -->
      <div style="background:#0d1117;border:1px solid #21262d;border-radius:10px;padding:16px;margin-bottom:14px;">
        <div style="font-size:12px;font-weight:700;color:#58a6ff;margin-bottom:12px;">🔌 Was die Polymarket API heute bereits kann (<code style="font-size:11px;">py-clob-client</code>)</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
          <ul style="font-size:12px;color:#8b949e;line-height:1.8;padding-left:16px;margin:0;">
            <li>✅ <code style="font-size:11px;color:#00d4a1;">get_market()</code> — Orderbook + Best-Bid/Ask</li>
            <li>✅ <code style="font-size:11px;color:#00d4a1;">create_order()</code> — Limit &amp; Market Orders</li>
            <li>✅ <code style="font-size:11px;color:#00d4a1;">cancel_order()</code> — offene Order stornieren</li>
            <li>✅ <code style="font-size:11px;color:#00d4a1;">get_open_orders()</code> — aktive Positionen abrufen</li>
          </ul>
          <ul style="font-size:12px;color:#8b949e;line-height:1.8;padding-left:16px;margin:0;">
            <li>✅ <code style="font-size:11px;color:#00d4a1;">get_trades()</code> — Trade-Historie</li>
            <li>✅ Preise via REST: <code style="font-size:11px;color:#00d4a1;">/markets/{clobTokenId}</code></li>
            <li>⚠️ Kein natives "Sell-to-Close" — stattdessen Sell-Order auf Yes-Token</li>
            <li>⚠️ Slippage bei Market-Orders — Limit-Orders bevorzugen</li>
          </ul>
        </div>
        <div style="margin-top:12px;font-size:12px;color:#8b949e;line-height:1.7;">
          <strong style="color:#e6edf3;">Für den Closing-Trade:</strong> Da Poly keine nativen "Sell-to-Close"-Orders kennt,
          erstellt <code style="font-size:11px;color:#00d4a1;">polymarket_bet.py</code> eine <strong style="color:#e6edf3;">SELL-Order auf den Yes-Token</strong>
          (= verkauft die gehaltenen Tokens zurück in den Markt). Limit-Preis = Aktueller Best-Bid − 0.5pp
          (sofortiger Fill ohne zu viel Slippage).
        </div>
      </div>

      <!-- Mathematik -->
      <div style="background:#0d1117;border:1px solid #21262d;border-radius:10px;padding:16px;">
        <div style="font-size:12px;font-weight:700;color:#e6edf3;margin-bottom:12px;">🧮 Beispiel-Rechnung: Over 2.5, Leverkusen vs. Bayern</div>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;font-size:12px;">
          <div style="background:#161b22;border-radius:8px;padding:10px;">
            <div style="color:#8b949e;margin-bottom:4px;">Opening (Mo. 09:00)</div>
            <div style="color:#e6edf3;font-weight:700;">Pinnacle: 1.92 (52%)</div>
            <div style="color:#3fb950;">Poly Yes: 0.51 USDC</div>
            <div style="color:#8b949e;margin-top:6px;">→ Kaufe 100 USDC worth</div>
            <div style="color:#e6edf3;">= 196 Tokens @ 0.510</div>
          </div>
          <div style="background:#161b22;border-radius:8px;padding:10px;">
            <div style="color:#8b949e;margin-bottom:4px;">Closing (Do. 16:00 −3h)</div>
            <div style="color:#e6edf3;font-weight:700;">Pinnacle: 1.74 (57%)</div>
            <div style="color:#e3b341;">Poly Yes: 0.58 USDC</div>
            <div style="color:#8b949e;margin-top:6px;">→ Verkaufe alle Tokens</div>
            <div style="color:#e6edf3;">= 196 × 0.575 = 112.7</div>
          </div>
          <div style="background:#0a1a0a;border:1px solid #3fb95033;border-radius:8px;padding:10px;">
            <div style="color:#8b949e;margin-bottom:4px;">Ergebnis</div>
            <div style="color:#3fb950;font-size:16px;font-weight:800;">+12.7 USDC</div>
            <div style="color:#3fb950;font-size:13px;font-weight:700;">+12.7% auf 100 USDC</div>
            <div style="color:#8b949e;margin-top:6px;font-size:11px;">Spiel ist egal.</div>
            <div style="color:#8b949e;font-size:11px;">Kein Bookie-Limit.</div>
            <div style="color:#8b949e;font-size:11px;">Kein gubbin-Risiko.</div>
          </div>
        </div>
        <div style="margin-top:12px;font-size:11px;color:#8b949e;line-height:1.6;padding:10px 12px;background:#161b22;border-radius:8px;border:1px solid #30363d;">
          <strong style="color:#e3b341;">Break-Even:</strong> Bei 1.5pp Spread (Poly Bid-Ask) + 0.5pp Slippage = ~2pp Kosten.
          Bookie-Bewegung muss also ≥ <strong style="color:#e6edf3;">5pp</strong> sein damit der Trade profitabel ist.
          Unsere SHARP-Signale (≥8pp) sind damit automatisch im profitablen Bereich —
          der Poly-Markt muss nur noch nachziehen.
        </div>
      </div>

    </div>
    <!-- ── END TRADING-KONZEPT ─────────────────────────── -->

    <!-- ── STICKY CONFIRM BAR ─────────────────────────── -->
    <div id="polyStickyBar"
         style="display:none;position:fixed;bottom:0;left:0;right:0;background:#161b22;border-top:1px solid #30363d;padding:12px 20px;align-items:center;justify-content:space-between;z-index:100;gap:12px">
      <span id="polyStickyCount" style="font-size:13px;color:#e6edf3;font-weight:600"></span>
      <div style="display:flex;gap:8px">
        <button onclick="polyMarkPlaced()"
                style="background:none;border:1px solid #30363d;border-radius:10px;color:#8b949e;font-size:13px;font-weight:600;padding:11px 18px;cursor:pointer;font-family:inherit">
          ✅ Manuell
        </button>
        <button onclick="polyConfirm()"
                style="background:linear-gradient(135deg,#a78bfa,#7c3aed);border:none;border-radius:10px;color:#fff;font-size:14px;font-weight:800;padding:11px 26px;cursor:pointer;font-family:inherit;letter-spacing:.02em;box-shadow:0 2px 12px #a78bfa44">
          🟣 Bets auslösen
        </button>
      </div>
    </div>`;

  // Init sticky bar
  _polyRefreshStickyBar();

  // Auto-resolve pending bets silently (only shows toast if something changed)
  setTimeout(() => polyAutoResolve(true), 800);

  // Fetch prices asynchronously
  _fetchAllPricesAsync();
}

async function _fetchAllPricesAsync() {
  const picks    = _polyState.picks;
  const statusEl = document.getElementById('polyPriceStatus');

  // Load price cache from server-generated JSON (no CORS proxy needed)
  if (statusEl) { statusEl.textContent = '⏳ Polymarket-Preise werden geladen…'; statusEl.style.color = ''; }

  await _loadPolyPriceCache();
  await _loadWmPolyPriceCache();

  // Show fetched-at timestamp if available
  let statusSuffix = '';
  if (_polyPriceFetched) {
    try {
      const d = new Date(_polyPriceFetched);
      statusSuffix = ` (Stand: ${d.toLocaleString('de-DE', { dateStyle: 'short', timeStyle: 'short' })})`;
    } catch (_) {}
  }

  // Apply cached prices to all picks at once
  // If the JSON file doesn't exist yet, leave prices undefined (show '—') rather than graying out
  if (!_polyPriceMissing) {
    for (const pick of picks) {
      if (pick.isWm) {
        // WM 2026: use wm_poly_prices.json (Gamma API prices)
        const result = _getWmPolyPrice(pick);
        _polyState.prices[pick.id] = result || { found: false, stale: _wmPolyPriceMissing };
      } else {
        const result = _getPriceFromCache(pick);
        _polyState.prices[pick.id] = result || { found: false };
      }
    }
    // NOTE: We do NOT filter out picks here — all system picks are valid Polymarket bets.
    // Stale (⏳) or missing (—) prices just mean the price cache needs a refresh (git pull).
  }

  // Single re-render after all prices are set
  const grid = document.getElementById('polyPickGrid');
  if (grid) grid.innerHTML = renderPolyPickCards();

  // Update status label
  if (statusEl) {
    if (_polyPriceMissing) {
      statusEl.textContent = '⚠️ polymarket_prices.json fehlt — GitHub Action ausführen';
      statusEl.style.color = '#f5c518';
    } else if (picks.length === 0) {
      statusEl.textContent = '';
    } else {
      const found = Object.values(_polyState.prices).filter(p => p.found).length;
      statusEl.textContent = `✅ ${found}/${picks.length} Märkte gefunden${statusSuffix}`;
      statusEl.style.color = '#3fb950';
    }
  }
}
