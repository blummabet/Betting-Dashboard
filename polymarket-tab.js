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
const POLY_LEAGUES = new Set(['GER','ENG','ITA','ESP','FRA','NED','POR','TUR','GER2','SCO']);

// Markets we can map to Polymarket outcomes
const POLY_MARKETS = new Set([
  'Heimsieg', 'Auswärtssieg', 'Unentschieden',
  'Over 2.5 Tore', 'Under 2.5 Tore',
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
  _polyState.picks    = getPolyPicks(dateStr);
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

      const odds = (typeof findOdds === 'function')
        ? findOdds(fx.leagueKey || lk, fx.home, fx.away)
        : null;

      let picks = [];
      try { picks = getBettingPicks(fx, odds, lk) || []; } catch (e) { /* skip broken fixture */ }

      for (const p of picks) {
        if (!POLY_MARKETS.has(p.market))          continue;
        if (p.conf === 'low')                     continue;
        if (p.oddsIsEst || p.odds == null)        continue;

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
          odds:        p.odds,
          date:        fx.date,
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
    const res = await fetch('polymarket_prices.json', { cache: 'no-store' });
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

// Retrieve price for a single pick from the cached JSON.
// Returns { found, price, eventTitle, eventUrl } or null.
function _getPriceFromCache(pick) {
  if (!_polyPriceCache) return null;
  const key = `${pick.home}|${pick.away}`;
  const entry = _polyPriceCache[key];
  // Key not in cache at all → cache is stale/incomplete, NOT confirmed "kein Markt"
  if (entry === undefined) return { found: false, stale: true };
  if (!entry.found) return { found: false };
  const price = (entry.markets || {})[pick.market];
  if (price == null) return { found: false };
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
  const icons = {
    'Heimsieg':       '🏠',
    'Auswärtssieg':   '✈️',
    'Unentschieden':  '🤝',
    'Over 2.5 Tore':  '⚽',
    'Under 2.5 Tore': '🔒',
  };
  return icons[market] || '📊';
}

function _marketColor(market) {
  if (!market) return '#8b949e';
  if (market === 'Heimsieg')          return '#58a6ff';
  if (market === 'Auswärtssieg')      return '#f5c518';
  if (market === 'Unentschieden')     return '#a78bfa';
  if (market.startsWith('Over'))      return '#3fb950';
  if (market.startsWith('Under'))     return '#f85149';
  return '#8b949e';
}

function _priceBlock(pickId) {
  const p = _polyState.prices[pickId];
  if (p === undefined)        return `<span style="color:#8b949e;font-size:12px">—</span>`;
  if (p.loading)              return `<span style="color:#8b949e;font-size:12px">⏳</span>`;
  if (!p.found && p.stale)    return `<span style="color:#e3b341;font-size:12px">⟳ neu laden</span>`;
  if (!p.found)               return `<span style="color:#8b949e;font-size:12px">kein Markt</span>`;
  const pct      = Math.round(p.price * 100);
  const polyOdds = (1 / p.price).toFixed(2);
  return `<span style="color:#a78bfa;font-weight:700;font-size:15px">${pct}¢</span> <span style="color:#8b949e;font-size:11px">(${polyOdds})</span>`;
}

function _edgeBlock(pick, pickId) {
  const p = _polyState.prices[pickId];
  if (!p || !p.found || !pick.odds) return `<span style="color:#8b949e;font-size:12px">—</span>`;
  const ourImplied = 1 / pick.odds;
  // Positive = Poly gibt bessere Odds als der Bookie (niedrigere implizite Wahrsch. = höhere Quoten)
  const edgePp     = Math.round((ourImplied - p.price) * 100);
  if (Math.abs(edgePp) < 1) return `<span style="color:#8b949e;font-size:12px">≈ 0%</span>`;
  const col  = edgePp > 0 ? '#3fb950' : '#f85149';
  const sign = edgePp > 0 ? '+' : '';
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

function _renderPickCard(pick) {
  const isSel      = _polyState.selected.has(pick.id);
  const priceData  = _polyState.prices[pick.id];
  // noMarket = Poly hat dieses Spiel explizit nicht; stale = Cache war veraltet, kein Urteil möglich
  const noMarket   = priceData && !priceData.loading && !priceData.found && !priceData.stale;
  const mktColor   = _marketColor(pick.market);

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
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px">
      <span style="font-size:13px">${_marketIcon(pick.market)}</span>
      <span style="font-size:13px;font-weight:600;color:${mktColor}">${pick.market}</span>
      ${_confBadge(pick.conf)}
    </div>
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

function renderPolyPickCards() {
  const picks = _polyState.picks;
  if (picks.length === 0) {
    return `<div style="grid-column:1/-1;text-align:center;padding:60px 24px;color:#8b949e">
      <div style="font-size:40px;margin-bottom:14px">🟣</div>
      <div style="font-size:16px;font-weight:600;margin-bottom:6px;color:#e6edf3">Keine Picks verfügbar</div>
      <div style="font-size:13px;line-height:1.6">Für <strong>${_polyState.dateStr}</strong> gibt es keine high/medium Picks
        mit echten Quoten in Polymarket-Ligen.<br>
        Versuche einen anderen Tag oder prüfe ob Quoten geladen sind.</div>
    </div>`;
  }
  return picks.map(_renderPickCard).join('');
}

// ── 6. STATS ────────────────────────────────────────────

function _getPolyBets() {
  try   { return JSON.parse(localStorage.getItem('betedge_poly_bets') || '[]'); }
  catch { return []; }
}

function _savePolyBets(bets) {
  try { localStorage.setItem('betedge_poly_bets', JSON.stringify(bets)); } catch (e) {}
}

function renderPolyStats() {
  const bets     = _getPolyBets();
  const total    = bets.length;
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

  const recent = [...bets].reverse().slice(0, 15);
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
    <div style="background:#161b22;border:1px solid #30363d;border-radius:10px;overflow:hidden">
      <div style="padding:12px 16px;border-bottom:1px solid #30363d;display:flex;align-items:center;justify-content:space-between">
        <span style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:#8b949e">Letzte Bets</span>
        <div style="display:flex;gap:6px">
          <button onclick="polyAutoResolve()" style="background:none;border:1px solid #3fb95055;border-radius:6px;color:#3fb950;font-size:11px;font-weight:600;padding:4px 10px;cursor:pointer;font-family:inherit">🔄 Auto-auswerten</button>
          <button onclick="polyManualResolve()" style="background:none;border:1px solid #30363d;border-radius:6px;color:#8b949e;font-size:11px;font-weight:600;padding:4px 10px;cursor:pointer;font-family:inherit">✏️ Manuell</button>
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

  // Try local server first, then GitHub Pages
  let history = null;
  const urls = [
    'http://localhost:3001/picks_history',
    'https://blummabet.github.io/Betting-Dashboard/picks_history.json',
  ];
  for (const url of urls) {
    try {
      const r = await fetch(url);
      if (r.ok) { history = await r.json(); break; }
    } catch (e) { /* try next */ }
  }

  if (!history || !Array.isArray(history)) {
    if (!silent) _polyToast('❌ Spielergebnisse nicht erreichbar');
    return;
  }

  let resolvedCount = 0;
  for (const bet of bets) {
    if (bet.result) continue;
    const entry  = _matchHistoryEntry(bet, history);
    if (!entry?.resolved) continue;   // match not yet finished
    const result = _resolveBetFromEntry(bet, entry);
    if (result) { bet.result = result; resolvedCount++; }
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

  const bets = _getPolyBets();
  for (const p of sel) {
    const pd = _polyState.prices[p.id];
    bets.push({
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
    });
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

  const ok = await _callGitHubDispatch(orders);

  if (ok) {
    // Save as pending in localStorage
    const bets = _getPolyBets();
    for (const p of sel) {
      const pd = _polyState.prices[p.id];
      bets.push({
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
      });
    }
    _savePolyBets(bets);
    _polyState.selected.clear();
    _polyRefreshStickyBar();
    document.getElementById('polyModal').style.display = 'none';
    document.getElementById('polyPickGrid').innerHTML = renderPolyPickCards();
    document.getElementById('polyStatsSection').innerHTML = renderPolyStats();
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
  const dateStr = _todayStr();
  _polyState.dateStr  = dateStr;
  _polyState.picks    = getPolyPicks(dateStr);
  _polyState.prices   = {};
  _polyState.selected = new Set(_polyState.picks.map(p => p.id)); // start: all selected

  const panel = document.getElementById('polymarketPanel');
  if (!panel) return;

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
      const result = _getPriceFromCache(pick);
      _polyState.prices[pick.id] = result || { found: false };
    }
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
