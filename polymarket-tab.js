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
// 25.07.2026 (Lucas: „Betting-Tab startet erst 31.7, aber dieses WE ist MLS-Runde"). MLS fehlte in
// der Poly-Liga-Whitelist → MLS-Fixtures fielen aus den Datums-Chips (_getAvailableDates) und dem
// Render. MLS hat echte Poly-Märkte und laufende Saison → gehört rein.
const POLY_LEAGUES = new Set(['GER','ENG','ITA','ESP','FRA','NED','POR','TUR','GER2','ENG2','SCO','MLS']);

// Markets we can map to Polymarket outcomes.
// Over/Under goals: 1.5, 2.5, 3.5 (Polymarket standard lines).
// Corners: all lines from pick engine (shown when Polymarket offers them; "kein Markt" otherwise).
// DNB, DC, Asian Handicap, HT, Cards, Team Goals: not on Polymarket → excluded.
const POLY_MARKETS = new Set([
  // ── Match result ────────────────────────────────────────
  'Heimsieg', 'Auswärtssieg', 'Unentschieden',
  // ── Goals Over/Under ────────────────────────────────────
  'Over 1.5 Tore', 'Over 2.5 Tore', 'Over 3.5 Tore',
  'Under 1.5 Tore', 'Under 2.5 Tore', 'Under 3.5 Tore',
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
  const dateSet = new Set();
  const todayStr = _todayStr();
  const [td, tm, ty] = todayStr.split('.');
  const todayDate = new Date(`${ty}-${tm}-${td}`);

  // ── 1. Liga-Fixtures (DD.MM.YYYY-Format) ────────────────────────
  if (typeof LEAGUES !== 'undefined') {
    for (const [lk, lg] of Object.entries(LEAGUES)) {
      if (!POLY_LEAGUES.has(lk)) continue;
      for (const fx of (lg.fixtures || [])) {
        if (!fx.date) continue;
        const [d, m, y] = fx.date.split('.');
        if (new Date(`${y}-${m}-${d}`) < todayDate) continue;
        dateSet.add(fx.date);
      }
    }
  }

  // ── 2. WM 2026 Fixtures (YYYY-MM-DD-Format → DD.MM.YYYY konvertieren) ──
  // Wichtig: ohne diesen Block würde während Sommerpause das Datum-Dropdown verschwinden,
  // weil LEAGUES leer ist. WM-Tage müssen mit rein.
  const wmSrc = (typeof window !== 'undefined')
    ? (window.WM2026_DATA || window._wmDataCache)
    : null;
  if (wmSrc && wmSrc.groups) {
    for (const gdata of Object.values(wmSrc.groups)) {
      for (const fx of (gdata.fixtures || [])) {
        if (!fx.date) continue;   // ISO YYYY-MM-DD
        const [y, m, d] = fx.date.split('-');
        if (!d) continue;
        const ddmm = `${d}.${m}.${y}`;
        if (new Date(`${y}-${m}-${d}`) < todayDate) continue;
        dateSet.add(ddmm);
      }
    }
  }

  // ── 3. Polymarket-Lookup (für Liga-Spiele die nicht in LEAGUES sind) ──
  if (typeof _polyLookup === 'object' && _polyLookup) {
    for (const fx of Object.values(_polyLookup)) {
      const d = fx && fx.date;
      if (!d) continue;
      // Akzeptiere beide Formate
      if (d.includes('-')) {
        const [yy, mm, dd] = d.split('-');
        if (!dd) continue;
        if (new Date(`${yy}-${mm}-${dd}`) < todayDate) continue;
        dateSet.add(`${dd}.${mm}.${yy}`);
      } else if (d.includes('.')) {
        const [dd, mm, yy] = d.split('.');
        if (!yy) continue;
        if (new Date(`${yy}-${mm}-${dd}`) < todayDate) continue;
        dateSet.add(d);
      }
    }
  }

  return [...dateSet].sort((a, b) => {
    const [ad, am, ay] = a.split('.');
    const [bd, bm, by] = b.split('.');
    return new Date(`${ay}-${am}-${ad}`) - new Date(`${by}-${bm}-${bd}`);
  });
}

// ── TAGES-FILTER als Chips (18.07.2026) ─────────────────────────────────────────
// Vorher ein <select>, das genau EINEN Tag zeigte — man sah nie, ob an anderen Tagen
// überhaupt Picks liegen, und musste blind durchklicken. Jetzt: eine Chip-Reihe mit
// Pick-Anzahl pro Tag plus „Alle" (dateStr='' → beide Extraktoren überspringen den
// Datumsfilter). Tage ohne Picks bleiben sichtbar, aber gedimmt.
function _polyPickCountForDate(d) {
  try {
    return _collectAllPolyPicks(d).length;
  } catch (_e) { return 0; }
}

function _renderPolyDateChips(activeDate) {
  // _getAvailableDates() speist sich aus LEAGUES/_polyLookup — WM-Picks kommen aus einer
  // eigenen Quelle und tauchen dort nicht auf. Ohne Union verschwindet ein Tag aus der Leiste,
  // obwohl Picks darauf liegen: der Pick wäre unerreichbar. Deshalb Union über die Pick-Tage.
  const set = new Set(_getAvailableDates());
  // WM + Liga/MLS-Pick-Tage dazu — deren Quellen tauchen in _getAvailableDates nicht auf,
  // sonst wäre der Pick-Tag unerreichbar (genau der MLS-Fall, 25.07.2026).
  for (const p of [...(getWmPolyPicks('') || []), ...(getMlsLigaPolyPicks('') || [])]) {
    const [y, m, d] = String(p.date || '').split('-');
    if (y && m && d) set.add(`${d}.${m}.${y}`);
    else if (p.date && p.date.includes('.')) set.add(p.date);
  }
  const dates = [...set].sort((a, b) => {
    const [ad, am, ay] = a.split('.'), [bd, bm, by] = b.split('.');
    return new Date(`${ay}-${am}-${ad}`) - new Date(`${by}-${bm}-${bd}`);
  }).slice(0, WM_POLY_DAYS_AHEAD);
  if (!dates.length) return '';

  const weekdays = ['So','Mo','Di','Mi','Do','Fr','Sa'];
  const chip = (val, label, count, isActive) => {
    const dim = count === 0 && !isActive;
    const bg     = isActive ? 'rgba(167,139,250,.18)' : 'transparent';
    const border = isActive ? '#a78bfa' : '#30363d';
    const col    = isActive ? '#a78bfa' : (dim ? '#6e7681' : '#c9d1d9');
    const badge  = count > 0
      ? `<span style="margin-left:5px;background:${isActive ? '#a78bfa' : '#30363d'};color:${isActive ? '#0d1117' : '#8b949e'};border-radius:7px;padding:0 5px;font-size:10px;font-weight:800">${count}</span>`
      : '';
    return `<button onclick="polyChangeDate('${val}')" data-polydate="${val}"
      style="background:${bg};border:1px solid ${border};border-radius:8px;color:${col};
             font-size:11px;font-weight:700;padding:6px 10px;cursor:pointer;font-family:inherit;
             transition:border-color .15s,color .15s;white-space:nowrap"
      onmouseover="this.style.borderColor='#a78bfa'" onmouseout="this.style.borderColor='${border}'"
      >${label}${badge}</button>`;
  };

  const total = _polyPickCountForDate('');
  const out = [chip('', 'Alle', total, !activeDate)];
  for (const d of dates) {
    const [dd, mm, yy] = d.split('.');
    const wd = weekdays[new Date(`${yy}-${mm}-${dd}`).getDay()];
    out.push(chip(d, `${wd} ${dd}.${mm}.`, _polyPickCountForDate(d), d === activeDate));
  }
  return `<div id="polyDateChips" style="display:flex;gap:6px;flex-wrap:wrap;align-items:center">${out.join('')}</div>`;
}

function polyChangeDate(dateStr) {
  _polyState.dateStr  = dateStr;
  // Alle Quellen: WM + Liga/MLS + Club-Ligen (eine Sammelstelle, damit keine vergessen wird)
  _polyState.picks = _collectAllPolyPicks(dateStr);
  _polyState.prices   = {};
  _polyState.selected = new Set(_polyState.picks.map(p => p.id));
  _polyRefreshStickyBar();

  // Aktiven Chip umsetzen (der Chip-Block rendert sich komplett neu — Zähler inklusive)
  const chips = document.getElementById('polyDateChips');
  if (chips) chips.outerHTML = _renderPolyDateChips(dateStr);

  // Update subtitle
  const sub = document.getElementById('polyDateSub');
  if (sub) sub.textContent = `${dateStr || 'Alle Tage'} · ${_polyState.picks.length} eligible pick${_polyState.picks.length !== 1 ? 's' : ''}`;

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
      if (dateStr && fx.date !== dateStr) continue;   // 18.07.: null = alle Tage

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

  // ── WM 2026 BET-Picks für dieses Datum dazu ──────────────────────────────
  // Filter: nur verdict=BET (Card-Edge-Floor 17.06.2026 entfernt — bestätigte
  // Steam-BETs haben edge ~0 by design; Betting-Tab zeigt sie wie die Cards).
  // Quelle: window.WM2026_DATA (von wm2026-renderer.js gesetzt) oder _wmDataCache
  // (eigener async Fetch in initPolymarket falls noch nicht geladen).
  const wmSrc = window.WM2026_DATA || window._wmDataCache;
  if (wmSrc) {
    const wmPicks = _extractWmPicksForDate(wmSrc, dateStr);
    for (const p of wmPicks) results.push(p);
  }

  // Sort: WM-Picks oben (per `isWm` Flag), dann high conf first, dann sc desc
  results.sort((a, b) => {
    if (!!a.isWm !== !!b.isWm) return a.isWm ? -1 : 1;
    if (a.conf !== b.conf) return a.conf === 'high' ? -1 : 1;
    return b.sc - a.sc;
  });
  return results;
}


// ── WM 2026 Pick-Loader ────────────────────────────────────────────────────────
// Cache: nach erstem Async-Load steht es auch für synchrone getPolyPicks() bereit.
let _wmDataLoading = false;
async function _loadWmDataAsync() {
  if (window.WM2026_DATA || window._wmDataCache || _wmDataLoading) return;
  _wmDataLoading = true;
  try {
    const r = await fetch('wm2026-data.json?t=' + Date.now(), { cache: 'no-store' });
    if (r.ok) window._wmDataCache = await r.json();
  } catch {}
  _wmDataLoading = false;
}

// Filter-Schwellen für WM BET-Picks im MANUELLEN Betting-Tab (NICHT Trading-Cockpit).
// 17.06.2026 (Lucas, Zwei-Flächen-Konzept): Card-Edge-Floor ENTFERNT. Ein bestätigter
// Steam-BET hat am Spieltag edgePP ~0 BY DESIGN — der Wert steckt in der Signal-
// Bestätigung, nicht im Preis. Betting-Tab zeigt jetzt ALLE verdict==BET (wie die Cards).
// (Der Auto-Trader/Trading-Cockpit ist davon UNBERÜHRT — der bleibt voll edge-getrieben.)
// 18.07.2026 (Lucas: „kann bei BET bleiben und ABWÄGEN mit hoher Conviction").
// Vorher: NUR verdict=BET. Bei dünnen Märkten (MLS) entstehen aber oft ausschließlich
// ABWÄGEN-Picks — der Tab zeigte dann nichts, obwohl Picks da waren.
// Jetzt: BET immer, ABWÄGEN nur ab hoher Conviction. Schwach begründete ABWÄGEN bleiben draußen
// (die gehören auf die Card zum Beobachten, nicht ins Wett-Interface). NOBET/SKIP nie.
//
// SCHWELLE 5 — empirisch, nicht aus verdict_thresholds abgeleitet. Naheliegend wäre die
// „abwaegen"-Schwelle 6 aus cocobet_config gewesen; die wäre aber wirkungslos: `verdict` kommt
// aus computeVerdict() (Modell/Markt/Story), NICHT aus dem Conviction-Score — und über alle
// 248 gestempelten Picks (WM+Liga+MLS) erreicht KEIN einziges ABWÄGEN jemals 6.
// Verteilung ABWÄGEN: 0:7 1:17 2:16 3:42 4:50 5:34 — Maximum 5. Mit 6 hätte der Filter exakt
// dasselbe getan wie das alte BET-only und der Tab wäre weiter leer geblieben.
// 5 = oberstes Fünftel der ABWÄGEN-Picks (34/166 ≈ 20 %). Wenn die Verteilung wandert, hier
// nachziehen — der Test `poly-betting-filter` schlägt an, wenn die Schwelle wieder zum No-Op wird.
const WM_POLY_BET_ONLY          = false;
const WM_POLY_ABWAEGEN_MIN_CONV = 5;
const WM_POLY_DAYS_AHEAD        = 14;   // Sichtfenster für die Tages-Chips

// Gehört der Pick ins manuelle Wett-Interface?
function _polyPickEligible(verdict, conviction) {
  if (verdict === 'BET') return true;
  if (verdict !== 'ABWÄGEN') return false;
  return typeof conviction === 'number' && conviction >= WM_POLY_ABWAEGEN_MIN_CONV;
}

// Anpfiff bereits vorbei?  Primär: echte UTC-Kickoff-Zeit fx.kickoff (von
// Polymarket-Gamma, z.B. "2026-06-12T02:00:00Z"). Fallback: fx.date + fx.time.
// So werden Spätspiele (z.B. KOR-CZE 02:00 UTC = 20:00 Guadalajara) korrekt als
// "heute Abend, noch bettbar" behandelt statt über den 00:00-Platzhalter
// fälschlich versteckt. Erst NACH Anpfiff verschwindet das Spiel.
function _wmKickoffPassed(fx) {
  if (!fx) return false;
  if (fx.kickoff) {
    const k = new Date(fx.kickoff);
    if (!isNaN(k.getTime())) return k.getTime() <= Date.now();
  }
  if (!fx.date) return false;
  const t = (fx.time && /^\d{2}:\d{2}/.test(fx.time)) ? fx.time : '23:59';
  const ko = new Date(`${fx.date}T${t}:00Z`);
  if (isNaN(ko.getTime())) return false;
  return ko.getTime() <= Date.now();
}

function _extractWmPicksForDate(wm, dateStr) {
  const results = [];
  const picks = wm.picks || {};
  const groups = wm.groups || {};

  // BUG-FIX 06.06.2026: dateStr kommt vom Datepicker im Format DD.MM.YYYY
  // (z.B. "11.06.2026"). fx.date ist aber ISO YYYY-MM-DD ("2026-06-11").
  // String-Vergleich war NIE wahr → 0 Picks für WM angezeigt.
  // Lösung: dateStr in ISO konvertieren falls nötig.
  let dateStrIso = dateStr;
  if (dateStr && dateStr.includes('.')) {
    const [dd, mm, yyyy] = dateStr.split('.');
    if (dd && mm && yyyy) dateStrIso = `${yyyy}-${mm}-${dd}`;
  }

  // Build group/team Lookup für Flag + Name
  const teamLookup = {};
  for (const [gKey, gData] of Object.entries(groups)) {
    for (const t of (gData.teams || [])) {
      teamLookup[t.id] = { name: t.name || t.id, flag: t.flag || '🏳' };
    }
  }

  for (const [pickKey, pickList] of Object.entries(picks)) {
    if (!Array.isArray(pickList) || pickList.length === 0) continue;
    // pickKey = "GRP-MD-HOME-AWAY"
    const parts = pickKey.split('-');
    if (parts.length < 4) continue;
    const gKey = parts[0], md = parseInt(parts[1]), hId = parts[2], aId = parts[3];
    const g = groups[gKey];
    if (!g) continue;
    const fx = (g.fixtures || []).find(f => f.home === hId && f.away === aId && f.matchday === md);
    // fx.date ist ISO YYYY-MM-DD — gegen konvertiertes dateStrIso vergleichen
    if (!fx) continue;
    if (dateStrIso && fx.date !== dateStrIso) continue;   // 18.07.: null = alle Tage
    // FIX 11.06.2026: Spiele mit bereits vergangenem Anpfiff NICHT mehr als Wette
    // anbieten. Betrifft v.a. die 00:00-Platzhalter-Zeiten (8 Fixtures): ein Spiel
    // mit Anpfiff "heute 00:00" ist schon vorbei/läuft → darf nicht als frische
    // Wette gelistet werden (Lucas: KOR-CZE erschien fälschlich als "heute").
    if (_wmKickoffPassed(fx)) continue;

    const hInfo = teamLookup[hId] || { name: hId, flag: '🏳' };
    const aInfo = teamLookup[aId] || { name: aId, flag: '🏳' };

    for (const p of pickList) {
      // Refactor 2026-06-06: trackingExcluded-Check via shared Helper.
      // _pick_helpers.js isLegitimatePick spiegelt pick_helpers.is_legitimate_pick.
      const isLegit = (window.CocoBetPicks && window.CocoBetPicks.isLegitimatePick)
        ? window.CocoBetPicks.isLegitimatePick(p)
        : !p.trackingExcluded;   // Fallback wenn Helper fehlt
      if (!isLegit) continue;

      const edge = parseFloat(p.edgePP) || 0;
      const verdict = p.verdict;

      // BET immer, ABWÄGEN nur mit hoher Conviction (siehe _polyPickEligible).
      if (!_polyPickEligible(verdict, p.convictionScore)) continue;
      // FIX 1 (09.06.2026): synthetische saferAlt-Picks sind Card-Insurance,
      // keine Trade-Kandidaten — werden im Polymarket-Tab nicht gelistet.
      if (p.synthetic) continue;

      // Nur Märkte die Polymarket auch listet (POLY_MARKETS Set)
      // — generate_wm_picks.py schreibt deutsche Labels, müssen ggf. gemappt werden
      // BUG-FIX 06.06.2026: Über 1.5 und Über 3.5 fehlten im Mapping
      const market = p.market;
      const mappedMarket =
        market === 'Über 1.5 Tore'      ? 'Over 1.5 Tore' :
        market === 'Über 2.5 Tore'      ? 'Over 2.5 Tore' :
        market === 'Über 3.5 Tore'      ? 'Over 3.5 Tore' :
        market === 'Unter 1.5 Tore'     ? 'Under 1.5 Tore' :
        market === 'Unter 2.5 Tore'     ? 'Under 2.5 Tore' :
        market === 'Unter 3.5 Tore'     ? 'Under 3.5 Tore' :
        market === 'Beide Teams treffen — Ja' ? 'Beide Teams treffen' :
        market;
      if (!POLY_MARKETS.has(mappedMarket)) continue;

      // Confidence-Score (sc) — leihen wir aus edgePP für Sortierung
      const sc = Math.min(99, 50 + Math.round(edge));

      results.push({
        id: `WM|${pickKey}|${market}`,
        league: 'WM2026',
        leagueFlag: '🌍',
        leagueName: 'WM 2026',
        home: hInfo.name,
        away: aInfo.name,
        homeFlag: hInfo.flag,    // for badge enhancement
        awayFlag: aInfo.flag,
        homeId: hId, awayId: aId,
        market: mappedMarket,
        conf: p.conf || 'medium',
        sc: sc,
        odds: p.odds,
        modelOdds: p.modelOdds,
        oddsIsEst: false,
        date: fx.date,
        edgePP: edge,
        dataQuality: p.dataQuality || 'elo_only',
        mods: [],
        saferAlt: null,
        boldAlt: null,
        oddsOpen: null,
        h2h: null,
        // ── WM-spezifische Felder für Card-Rendering ──
        isWm: true,
        wmGroup: gKey,
        wmMatchday: md,
        wmInfo: p.info || '',
        wmVenue: fx.venue || '',
        // FIX 2 (09.06.2026): Conviction + Engine-Felder durchreichen
        // damit Manual-Trade-Confirm Conviction sehen + warnen kann.
        convictionScore:      typeof p.convictionScore === 'number' ? p.convictionScore : null,
        convictionLabel:      p.convictionLabel || null,
        signalAdjustmentPP:   typeof p.signalAdjustmentPP === 'number' ? p.signalAdjustmentPP : null,
        effectiveEdgePP:      typeof p.effectiveEdgePP === 'number' ? p.effectiveEdgePP : null,
        synthetic:            !!p.synthetic,
      });
    }
  }
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

    // BET immer, ABWÄGEN nur mit hoher Conviction (siehe _polyPickEligible).
    if (!_polyPickEligible(entry.verdict, entry.convictionScore)) continue;
    // FIX 1 (09.06.2026): synthetische saferAlt-Picks raus — Insurance, kein Trade
    if (entry.synthetic) continue;

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
      // FIX 2 (09.06.2026): Conviction + Engine-Felder durchreichen
      convictionScore:      typeof entry.convictionScore === 'number' ? entry.convictionScore : null,
      convictionLabel:      entry.convictionLabel || null,
      signalAdjustmentPP:   typeof entry.signalAdjustmentPP === 'number' ? entry.signalAdjustmentPP : null,
      effectiveEdgePP:      typeof entry.effectiveEdgePP === 'number' ? entry.effectiveEdgePP : null,
      synthetic:            !!entry.synthetic,
    });
  }

  // Sort: höchste Conviction zuerst (wenn vorhanden), dann edge (sc).
  results.sort((a, b) => {
    if (a.verdict !== b.verdict) return a.verdict === 'BET' ? -1 : 1;
    const ca = typeof a.convictionScore === 'number' ? a.convictionScore : -1;
    const cb = typeof b.convictionScore === 'number' ? b.convictionScore : -1;
    if (ca !== cb) return cb - ca;
    return b.sc - a.sc;
  });
  return results;
}

// 25.07.2026 (Lucas: „seh nichts im Betting-Tab" → MLS war nie angeschlossen). Liest die von
// wm2026-renderer.js exponierten Liga/MLS-Picks (window.NATIONAL_PICKS_FOR_POLY) und wendet
// EXAKT denselben Eligibilitäts-Filter an wie WM (BET immer, ABWÄGEN ab Conviction 5). Gleiches
// Entry-Format wie getWmPolyPicks, damit Render/Edge-Block unverändert funktionieren.
const _POLY_LEAGUE_META = {
  MLS: { flag: '🇺🇸', name: 'MLS' }, GER: { flag: '🇩🇪', name: 'Bundesliga' },
  ENG: { flag: '🏴', name: 'Premier League' }, ESP: { flag: '🇪🇸', name: 'La Liga' },
  ITA: { flag: '🇮🇹', name: 'Serie A' }, FRA: { flag: '🇫🇷', name: 'Ligue 1' },
};
function getMlsLigaPolyPicks(dateStr) {
  const raw = (typeof window !== 'undefined' && window.NATIONAL_PICKS_FOR_POLY) || [];
  if (!raw.length) return [];
  const results = [];
  for (const e of raw) {
    const [y, m, d] = String(e.date || '').split('-');
    const dateFmt = (y && m && d) ? `${d}.${m}.${y}` : null;
    if (dateStr && dateFmt && dateFmt !== dateStr) continue;
    if (!_polyPickEligible(e.verdict, e.convictionScore)) continue;
    const polyMarket = WM_MARKET_TO_POLY[e.market];
    if (!polyMarket) continue;
    const meta = _POLY_LEAGUE_META[e.league] || { flag: '🏆', name: e.league || 'Liga' };
    const clvPP = e.clvPP || 0;
    results.push({
      id: `${e.league}|${e.home}|${e.away}|${polyMarket}`,
      league: e.league || 'MLS', leagueFlag: meta.flag, leagueName: meta.name,
      home: e.home, away: e.away, homeId: e.homeId || null, awayId: e.awayId || null,
      homeFlag: '', awayFlag: '',
      market: polyMarket, conf: e.verdict === 'BET' ? 'high' : 'medium',
      sc: e.edgePP || 0, odds: e.odds, modelOdds: e.modelOdds, oddsIsEst: false,
      date: e.date, dateFmt, clvPP, dataQuality: e.dataQuality || 'elo_only',
      verdict: e.verdict, edgePP: e.edgePP || 0, mods: [], saferAlt: null, boldAlt: null,
      oddsOpen: null, h2h: null, isWm: false,
      convictionScore: typeof e.convictionScore === 'number' ? e.convictionScore : null,
    });
  }
  results.sort((a, b) => {
    if (a.verdict !== b.verdict) return a.verdict === 'BET' ? -1 : 1;
    const ca = a.convictionScore ?? -1, cb = b.convictionScore ?? -1;
    return cb !== ca ? cb - ca : b.sc - a.sc;
  });
  return results;
}

// Baut NATIONAL_PICKS_FOR_POLY direkt aus mls-data.json (+ liga-data.json), unabhängig davon, ob
// der National-Tab schon geöffnet wurde. Gleiche flache Form wie wm2026-renderer.js sie exponiert.
async function _loadNationalPolyPicksAsync() {
  const _build = (d, out) => {
    if (!d || !d.groups || !d.picks) return;
    const fxByHa = {};
    for (const g of Object.values(d.groups)) {
      for (const fx of (g.fixtures || [])) fxByHa[`${fx.home}-${fx.away}`] = fx;
    }
    for (const [pk, plist] of Object.entries(d.picks)) {
      if (!Array.isArray(plist)) continue;
      const fx = fxByHa[pk.split('-').slice(2).join('-')];
      if (!fx) continue;
      const league = pk.split('-')[0] || 'MLS';
      for (const p of plist) {
        if (!['BET', 'ABWÄGEN'].includes(p.verdict)) continue;
        out.push({
          league, home: fx.homeName || String(fx.home), away: fx.awayName || String(fx.away),
          homeId: fx.home, awayId: fx.away, date: fx.date,
          market: p.market, odds: p.odds, modelOdds: p.modelOdds,
          verdict: p.verdict, convictionScore: p.convictionScore,
          edgePP: p.edgePP || 0, clvPP: p.clvPP || 0, dataQuality: p.dataQuality || 'elo_only',
        });
      }
    }
  };
  const out = [];
  for (const f of ['mls-data.json', 'liga-data.json']) {
    try {
      const r = await fetch(f + '?t=' + Date.now());
      if (r.ok) _build(await r.json(), out);
    } catch (_e) { /* Datensatz optional */ }
  }
  window.NATIONAL_PICKS_FOR_POLY = out;
  return out;
}

// EINE Sammelstelle für alle Betting-Tab-Pick-Quellen — verhindert, dass eine Quelle an einem
// Aggregations-Punkt vergessen wird (genau so fiel MLS raus). WM + Liga/MLS + Club-Ligen.
function _collectAllPolyPicks(dateStr) {
  let wm = [], mls = [], club = [];
  try { wm   = getWmPolyPicks(dateStr)     || []; } catch (_e) {}
  try { mls  = getMlsLigaPolyPicks(dateStr) || []; } catch (_e) {}
  try { club = getPolyPicks(dateStr)       || []; } catch (_e) {}
  return [...wm, ...mls, ...club];
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
let _wmAllFixtures      = [];    // all 72 games with Pinnacle + Poly + edge
let _wmGeneratedAt      = '';    // timestamp from wm_poly_prices.json
let _wmTableFilter      = 'all'; // default: alle Fixtures, sorted by momentum
let _wmPolyHistoryData  = null;  // wm2026-poly-history.json — {matchKey: [{ts, poly_hw, edge_hw, ...}]}

async function _loadWmPolyPriceCache() {
  if (_wmPolyPriceCache !== null) return;
  try {
    const _cbv = Math.floor(Date.now() / 3600000);
    const res = await fetch(`wm_poly_prices.json?v=${_cbv}`, { cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    _wmPolyPriceCache = data.prices      || {};
    _wmAllFixtures    = data.allFixtures || [];
    _wmGeneratedAt    = data.generatedAt || '';
    console.log(`[Poly] WM prices loaded: ${_wmAllFixtures.length} fixtures, ` +
      `${_wmAllFixtures.filter(f=>f.hasPinnacle).length} with Pinnacle`);
  } catch (e) {
    console.warn('[Poly] wm_poly_prices.json not available:', e.message);
    _wmPolyPriceCache = {};
    _wmPolyPriceMissing = true;
  }
  // Load poly price history in parallel (needed for sparklines + action badges)
  if (_wmPolyHistoryData === null) {
    try {
      const hr = await fetch('wm2026-poly-history.json?t=' + Date.now(), { cache: 'no-store' });
      if (hr.ok) {
        _wmPolyHistoryData = await hr.json();
        console.log(`[Poly] History loaded: ${Object.keys(_wmPolyHistoryData).length} fixtures`);
      }
    } catch(e) { _wmPolyHistoryData = {}; }
  }
}

// ── Fixture Sparkline ─────────────────────────────────────────────────────
// Zeichnet Pinn fair prob (blau/solid) vs Poly price (lila/gestrichelt).
// Rec 01-06 implemented: market label, start/end labels, line styles,
// edge badge, timestamp axis, direction annotation.
function _drawFixtureSparkline(matchKey, edgeKey) {
  if (!_wmPolyHistoryData || !edgeKey) return '';
  const snaps = (_wmPolyHistoryData[matchKey] || []).slice(-18);
  if (snaps.length < 3) return '<div style="font-size:10px;color:#484f58;padding:4px 0">📊 Noch zu wenig Verlauf — ab morgen sichtbar</div>';

  const edgeField = `edge_${edgeKey}`;
  const polyField = `poly_${edgeKey}`;

  const polyVals = snaps.map(s => (s[polyField] != null && s[polyField] > 0) ? s[polyField] : null);
  const edgeVals = snaps.map(s => s[edgeField] ?? null);
  const pinnVals = snaps.map((s, i) => {
    const p = polyVals[i], e = edgeVals[i];
    if (p == null || e == null) return null;
    return Math.min(Math.max(p + e / 100, 0.01), 0.99);
  });

  const allProbs = [...polyVals, ...pinnVals].filter(x => x !== null);
  if (allProbs.length < 3) return '';

  // SVG dimensions: data area 0-56, axis band 58-74
  const W = 500, H = 76, dataH = 54;
  const axisY = 64;
  const minP = Math.min(...allProbs) - 0.018;
  const maxP = Math.max(...allProbs) + 0.018;
  const toX = i => 28 + (i / (snaps.length - 1)) * (W - 56); // left/right margin 28px for labels
  const toY = p => 4 + dataH - 4 - ((p - minP) / (maxP - minP)) * (dataH - 8);

  const pinnPts = pinnVals.map((p, i) => p !== null ? [toX(i), toY(p)] : null).filter(Boolean);
  const polyPts = polyVals.map((p, i) => p !== null ? [toX(i), toY(p)] : null).filter(Boolean);
  if (pinnPts.length < 2 || polyPts.length < 2) return '';

  const fillPoly = [...pinnPts, ...[...polyPts].reverse()]
    .map(([x,y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const pinnLine = pinnPts.map(([x,y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const polyLine = polyPts.map(([x,y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');

  // Steam marker
  let steamX = null;
  for (let i = Math.max(1, snaps.length - 6); i < snaps.length; i++) {
    const p1 = pinnVals[i], p0 = pinnVals[i-1];
    if (p1 !== null && p0 !== null && Math.abs(p1 - p0) >= 0.015) {
      steamX = ((toX(i-1) + toX(i)) / 2).toFixed(1);
      break;
    }
  }

  // ── Rec 02: Start + end value labels ───────────────────────────────────
  const [sxP, syP] = pinnPts[0];
  const [sxO, syO] = polyPts[0];
  const [lxP, lyP] = pinnPts[pinnPts.length - 1];
  const [lxO, lyO] = polyPts[polyPts.length - 1];
  const startPinnPct = Math.round((pinnVals.find(v=>v!==null)||0)*100);
  const startPolyPct = Math.round((polyVals.find(v=>v!==null)||0)*100);
  const endPinnPct   = Math.round((pinnVals.filter(v=>v!==null).at(-1)||0)*100);
  const endPolyPct   = Math.round((polyVals.filter(v=>v!==null).at(-1)||0)*100);

  // ── Rec 06: Edge direction annotation ──────────────────────────────────
  const edgeStart = (pinnVals.find(v=>v!==null)||0) - (polyVals.find(v=>v!==null)||0);
  const edgeEnd   = (pinnVals.filter(v=>v!==null).at(-1)||0) - (polyVals.filter(v=>v!==null).at(-1)||0);
  const edgeDeltaPP = (edgeEnd - edgeStart) * 100;
  let dirLabel, dirCol, dirArrow;
  if (edgeDeltaPP > 0.8) {
    dirLabel = 'Edge wächst'; dirCol = '#3fb950'; dirArrow = '↑';
  } else if (edgeDeltaPP < -0.8) {
    dirLabel = 'Edge schrumpft'; dirCol = '#f85149'; dirArrow = '↓';
  } else {
    dirLabel = 'Edge stabil'; dirCol = '#e3b341'; dirArrow = '→';
  }
  const annotText = `${dirArrow} ${dirLabel}`;
  const annotW = annotText.length * 5.8 + 16;

  // ── Rec 05: Timestamp axis ──────────────────────────────────────────────
  // ~8h per snap interval
  const hoursAgo = Math.round((snaps.length - 1) * 8);
  const timeLabel = hoursAgo >= 48 ? `vor ${Math.round(hoursAgo/24)}T` : `vor ${hoursAgo}h`;
  const firstX = toX(0).toFixed(1);
  const lastX  = toX(snaps.length - 1).toFixed(1);

  return `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:${H}px;display:block;overflow:visible">

    <!-- edge fill -->
    <polygon points="${fillPoly}" fill="#3fb950" opacity="0.10"/>

    <!-- steam marker -->
    ${steamX ? `<line x1="${steamX}" y1="2" x2="${steamX}" y2="${dataH+2}" stroke="#f85149" stroke-width="1" stroke-dasharray="3,2" opacity="0.6"/>
      <text x="${parseFloat(steamX)+4}" y="12" fill="#f85149" font-size="8" font-family="monospace" font-weight="700">🔥</text>` : ''}

    <!-- Rec 03: Pinnacle — solid blue -->
    <polyline points="${pinnLine}" stroke="#58a6ff" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
    <!-- Rec 03: Polymarket — dashed purple -->
    <polyline points="${polyLine}" stroke="#a78bfa" stroke-width="1.5" stroke-dasharray="5 3" fill="none" stroke-linecap="round" stroke-linejoin="round"/>

    <!-- Rec 02: Start dots (faded) -->
    <circle cx="${sxP.toFixed(1)}" cy="${syP.toFixed(1)}" r="2.5" fill="#58a6ff" opacity="0.35"/>
    <circle cx="${sxO.toFixed(1)}" cy="${syO.toFixed(1)}" r="2.5" fill="#a78bfa" opacity="0.35"/>

    <!-- Rec 02: Start value labels (left, faded) -->
    <text x="${(sxP - 4).toFixed(1)}" y="${(syP + 3.5).toFixed(1)}" font-size="9" font-family="monospace" fill="#58a6ff" text-anchor="end" opacity="0.45">${startPinnPct}%</text>
    <text x="${(sxO - 4).toFixed(1)}" y="${(syO + 3.5).toFixed(1)}" font-size="9" font-family="monospace" fill="#a78bfa" text-anchor="end" opacity="0.45">${startPolyPct}%</text>

    <!-- Rec 02: End dots (solid) -->
    <circle cx="${lxP.toFixed(1)}" cy="${lyP.toFixed(1)}" r="3" fill="#58a6ff" stroke="#0d1117" stroke-width="1.5"/>
    <circle cx="${lxO.toFixed(1)}" cy="${lyO.toFixed(1)}" r="3" fill="#a78bfa" stroke="#0d1117" stroke-width="1.5"/>

    <!-- Rec 02: End value labels (right, full opacity) -->
    <text x="${(lxP + 5).toFixed(1)}" y="${(lyP + 3.5).toFixed(1)}" font-size="9" font-weight="700" font-family="monospace" fill="#58a6ff" text-anchor="start">${endPinnPct}%</text>
    <text x="${(lxO + 5).toFixed(1)}" y="${(lyO + 3.5).toFixed(1)}" font-size="9" font-weight="700" font-family="monospace" fill="#a78bfa" text-anchor="start">${endPolyPct}%</text>

    <!-- Rec 06: Edge-direction annotation pill -->
    <rect x="${((W - annotW) / 2).toFixed(1)}" y="6" width="${annotW.toFixed(1)}" height="16" rx="3" fill="#161b22" stroke="#30363d" stroke-width="0.5"/>
    <text x="${(W/2).toFixed(1)}" y="17.5" font-size="9" font-family="monospace" fill="${dirCol}" text-anchor="middle" font-weight="700">${annotText}</text>

    <!-- Rec 05: Timestamp axis -->
    <line x1="${firstX}" y1="${axisY}" x2="${lastX}" y2="${axisY}" stroke="#21262d" stroke-width="0.5"/>
    <line x1="${firstX}" y1="${axisY - 3}" x2="${firstX}" y2="${axisY + 3}" stroke="#30363d" stroke-width="1"/>
    <line x1="${lastX}" y1="${axisY - 3}" x2="${lastX}" y2="${axisY + 3}" stroke="#30363d" stroke-width="1"/>
    <text x="${firstX}" y="${H - 2}" font-size="8.5" font-family="monospace" fill="#484f58" text-anchor="middle">${timeLabel}</text>
    <text x="${lastX}" y="${H - 2}" font-size="8.5" font-family="monospace" fill="#484f58" text-anchor="middle">jetzt</text>

  </svg>`;
}

// ── Action Badge ──────────────────────────────────────────────────────────
// Analysiert Edge, Volume, Trend, Steam und History → klare Handlungsempfehlung.
// Beide Szenarien (stabiler Gap / frischer Steam) sind valide Trades — der
// Unterschied ist nur die Dringlichkeit und Stake-Größe.
function _computeActionBadge(fix) {
  const edge  = fix.bestEdge || 0;
  const vol   = fix.vol || 0;
  const steam = fix.steamLag === true;
  const trend = fix.edgeTrend || 'stable';
  const key   = fix.key;

  // Wie lange existiert dieser Edge schon? (aus History)
  let edgeDays = 0;
  if (_wmPolyHistoryData && key && fix.bestEdgeKey) {
    const field = `edge_${fix.bestEdgeKey}`;
    const snaps = _wmPolyHistoryData[key] || [];
    edgeDays = snaps.filter(s => (s[field] || 0) >= 3).length;
    // @ 3 runs/day: 3 snaps = 1 Tag, 9 snaps = 3 Tage
    edgeDays = Math.round(edgeDays / 3);
  }
  const edgeIsEstablished = edgeDays >= 3;

  // ── Entscheidungsbaum ────────────────────────────────────────────────────
  if (edge < 2 || !fix.hasPinnacle) {
    return {
      icon: '—', label: 'Kein Signal', col: '#484f58', bg: '#161b22',
      reason: fix.hasPinnacle
        ? 'Edge unter 2pp — zu gering für einen Trade.'
        : 'Kein Pinnacle-Kurs verfügbar. Abwarten bis Pinnacle das Spiel listet.',
    };
  }

  if (trend === 'closing' && edge < 5) {
    return {
      icon: '⏸', label: 'Edge schließt', col: '#e3b341', bg: '#1a160a',
      reason: `Edge schrumpft auf ${edge.toFixed(1)}pp — Poly holt auf. Kein günstiger Einstieg mehr, außer du glaubst der Edge stabilisiert sich.`,
    };
  }

  // Steam-Lag: höchste Priorität — Poly hat Pinnacle-Move noch nicht eingepreist
  if (steam && edge >= 5) {
    const volNote = vol >= 5000 ? 'Volume gut' : vol >= 1500 ? `Vol $${vol.toLocaleString()} (ok)` : `Vol $${vol.toLocaleString()} — kleine Position`;
    return {
      icon: '🔥', label: 'Jetzt handeln', col: '#f85149', bg: '#200a0a',
      reason: `Pinnacle hat sich bewegt, Poly hat noch nicht reagiert → frischer Edge. ${volNote}. Je früher desto besser — Poly wird aufholen.`,
    };
  }

  // Hoher Edge + gutes Volume
  if (edge >= 7 && vol >= 5000) {
    return {
      icon: '✅', label: 'Starker Trade', col: '#3fb950', bg: '#091409',
      reason: `Edge +${edge.toFixed(1)}pp — deutlich über Conviction-Schwelle. Volume ausreichend. Volle Stake-Größe.${edgeIsEstablished ? ` Etabliert seit ~${edgeDays} Tagen.` : ''}`,
    };
  }

  if (edge >= 5 && vol >= 5000) {
    const stability = edgeIsEstablished
      ? `Edge stabil seit ~${edgeDays} Tagen — strukturelle Unterbewertung.`
      : `Neuer Edge — beobachte ob er sich hält.`;
    return {
      icon: '✅', label: 'Handeln', col: '#3fb950', bg: '#0d1a0d',
      reason: `Edge +${edge.toFixed(1)}pp, Volume $${vol.toLocaleString()}. ${stability} Stake gemäß Tier-Konfiguration.`,
    };
  }

  // Gut aber Liquidität begrenzt
  if (edge >= 5 && vol >= 1000) {
    return {
      icon: '🟡', label: 'Handeln (klein)', col: '#e3b341', bg: '#1a160a',
      reason: `Edge solide (+${edge.toFixed(1)}pp), aber Vol $${vol.toLocaleString()} begrenzt Liquidität. Kleine Position oder Limit-Order setzen.`,
    };
  }

  // Edge da aber zu wenig Volume
  if (edge >= 5 && vol < 1000) {
    return {
      icon: '👁', label: 'Beobachten', col: '#e3b341', bg: '#1a160a',
      reason: `Edge +${edge.toFixed(1)}pp ist gut, aber Vol $${vol.toLocaleString()} zu gering für sinnvollen Einstieg. Warten bis Volume steigt (Spiel näher rückt).`,
    };
  }

  // Edge 3-5pp: unter Conviction-Schwelle, aber im Auge behalten
  if (edge >= 3) {
    const growNote = trend === 'growing' ? ' Edge wächst — könnte bald über 5pp.' : '';
    return {
      icon: '👁', label: 'Beobachten', col: '#6e7681', bg: '#161b22',
      reason: `Edge +${edge.toFixed(1)}pp liegt unter der 5pp-Conviction-Schwelle.${growNote} Warten bis Edge ≥5pp oder Volume steigt.`,
    };
  }

  return {
    icon: '—', label: 'Abwarten', col: '#484f58', bg: '#161b22',
    reason: 'Kein klares Signal. Edge-Entwicklung abwarten.',
  };
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
  'Under 1.5 Tore':        'poly_u15',   // FIX 14.06.2026: fehlte → "kein Markt" trotz Daten
  'Over 3.5 Tore':         'poly_o35',
  'Under 3.5 Tore':        'poly_u35',   // FIX 14.06.2026: DEU-CUW Under 3.5 nicht handelbar weil unmapped
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

  // FIX 3 (09.06.2026): Conviction-Badge + Engine-Warnungen.
  // Spiegelt die drei Auto-Trigger-Gates (Raw-Edge ≥2pp, Conviction ≥3/10,
  // synthetic excluded). Manueller Trade kann override-en, aber muss informiert sein.
  const conv = typeof order.conviction === 'number' ? order.conviction : null;
  const convLabel = conv == null ? null
    : conv >= 8 ? { txt: '🎯 Top-Pick', col: '#3fb950', bg: 'rgba(63,185,80,.18)' }
    : conv >= 6 ? { txt: '⭐ Main-Pick', col: '#e3b341', bg: 'rgba(227,179,65,.18)' }
    : conv >= 3 ? { txt: '👁 Beobachten', col: '#8b949e', bg: 'rgba(139,148,158,.15)' }
                : { txt: '⚠ Schwache Bestätigung', col: '#f85149', bg: 'rgba(248,81,73,.15)' };

  const warnings = [];
  if (order.edge != null && order.edge < 2) {
    warnings.push(`Raw-Edge nur ${order.edge > 0 ? '+' : ''}${order.edge}pp — Auto-Trigger-Mindest ist 2pp`);
  }
  if (conv != null && conv < 3) {
    warnings.push(`Conviction ${conv}/10 — Auto-Trigger-Mindest ist 3/10`);
  }
  if (order.synthetic) {
    warnings.push(`Synthetischer saferAlt-Pick — als Insurance gedacht, nicht als Trade`);
  }
  if (typeof order.effectiveEdge === 'number' && typeof order.edge === 'number'
      && Math.abs(order.effectiveEdge - order.edge) > 1) {
    const sign = order.signalAdj > 0 ? '+' : '';
    warnings.push(`Engine pumpt Edge um ${sign}${(order.effectiveEdge - order.edge).toFixed(1)}pp (raw ${order.edge}pp → effektiv ${order.effectiveEdge}pp)`);
  }

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

    ${convLabel ? `
    <div style="display:flex;align-items:center;justify-content:space-between;gap:10px;
                background:${convLabel.bg};border:1px solid ${convLabel.col}55;border-radius:10px;
                padding:10px 14px;margin-bottom:12px">
      <div>
        <div style="font-size:10px;color:#6e7681;text-transform:uppercase;letter-spacing:.5px">Conviction-Score</div>
        <div style="font-size:14px;font-weight:800;color:${convLabel.col};margin-top:2px">${convLabel.txt}</div>
      </div>
      <div style="font-size:20px;font-weight:900;color:${convLabel.col}">${conv}/10</div>
    </div>` : ''}

    ${warnings.length ? `
    <div style="background:#f8514911;border:1px solid #f8514944;border-radius:10px;padding:10px 14px;margin-bottom:14px">
      <div style="font-size:11px;font-weight:800;color:#f85149;margin-bottom:6px;text-transform:uppercase;letter-spacing:.5px">⚠ Auto-Trigger hätte das geblockt</div>
      ${warnings.map(w => `<div style="font-size:12px;color:#f85149;margin-top:2px">• ${w}</div>`).join('')}
      <div style="font-size:10px;color:#8b949e;margin-top:6px;font-style:italic">Du kannst manuell überschreiben — der Auto-Trigger ist defensiver geworden weil die Engine Edges teils ungerechtfertigt pumpt.</div>
    </div>` : ''}

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

// ── System Guide — Pipeline-Anleitung oben im WM Tab ──────────────────────
function _renderWmSystemGuide() {
  // FIX 14.06.2026 (Lucas): Trading-System-Erklärung + Roadmap aus dem Polymarket-
  // Trading-Tab entfernt — gehört dort nicht hin. Funktion gibt nichts mehr zurück.
  return '';
  // eslint-disable-next-line no-unreachable
  // Status: auto-trigger active? (check local config)
  const autoEnabled = localStorage.getItem('wmAutoTriggerLive') === 'true';
  const manualPhase = !autoEnabled;

  const phase = (num, icon, title, status, statusCol, statusBg, lines) => `
    <div style="flex:1;min-width:180px;background:${statusBg};border:1px solid ${statusCol}33;
                border-radius:10px;padding:14px 16px;position:relative;overflow:hidden">
      <div style="position:absolute;top:10px;right:12px;font-size:9px;font-weight:800;
                  color:${statusCol};background:${statusCol}22;border:1px solid ${statusCol}44;
                  border-radius:10px;padding:2px 7px;letter-spacing:.5px">${status}</div>
      <div style="font-size:22px;margin-bottom:6px">${icon}</div>
      <div style="font-size:10px;font-weight:800;color:#484f58;letter-spacing:.8px;
                  text-transform:uppercase;margin-bottom:3px">Phase ${num}</div>
      <div style="font-size:13px;font-weight:800;color:#e6edf3;margin-bottom:10px">${title}</div>
      <div style="display:flex;flex-direction:column;gap:6px">
        ${lines.map(l => `<div style="font-size:11px;color:#8b949e;line-height:1.4;
                                      display:flex;gap:7px;align-items:flex-start">
          <span style="color:${statusCol};margin-top:1px;flex-shrink:0">▸</span>
          <span>${l}</span>
        </div>`).join('')}
      </div>
    </div>`;

  const arrow = `<div style="color:#30363d;font-size:18px;font-weight:300;
                              align-self:center;flex-shrink:0;padding:0 4px">→</div>`;

  const criteriaRow = (icon, label, value, col) =>
    `<div style="display:flex;align-items:center;gap:6px;padding:5px 10px;
                 background:#0d1117;border-radius:6px;border:1px solid #21262d">
      <span style="font-size:13px">${icon}</span>
      <span style="font-size:10px;color:#6e7681;flex:1">${label}</span>
      <span style="font-size:11px;font-weight:700;color:${col||'#e6edf3'}">${value}</span>
    </div>`;

  return `
  <div style="margin-bottom:20px">

    <!-- Header -->
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px">
      <span style="font-size:15px">⚙️</span>
      <span style="font-size:13px;font-weight:800;color:#e6edf3">Trading System — Wie es funktioniert</span>
      <span style="font-size:10px;color:#484f58;margin-left:auto">
        ${autoEnabled
          ? `<span style="color:#3fb950;font-weight:700">🤖 Auto-Modus AKTIV</span>`
          : `<span style="color:#e3b341;font-weight:700">✋ Manueller Modus</span>`}
      </span>
    </div>

    <!-- 3-Phase Pipeline -->
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px;align-items:stretch">
      ${phase(1, '📡', 'Signal erkennen', 'LIVE · 3×/Tag', '#60a5fa', '#0a0f1a', [
        'Gamma API holt Polymarket-Preise',
        'Pinnacle devigged → fairer Wert berechnet',
        'Edge = Pinn fair − Poly · in %p',
        'steamLag wenn Pinnacle zieht, Poly schläft',
        'Telegram-Alert bei Edge ≥ 4pp (neu/steam)',
      ])}
      ${arrow}
      ${phase(2, manualPhase ? '✋' : '🤖', manualPhase ? 'Manuell setzen' : 'Auto-Bet', manualPhase ? 'JETZT' : 'AKTIV', manualPhase ? '#e3b341' : '#3fb950', manualPhase ? '#1a160a' : '#0d1a0d', manualPhase ? [
        'Badge zeigt: Jetzt handeln / Handeln / Beobachten',
        'Auf Polymarket öffnen → Bet platzieren',
        '<strong style="color:#a78bfa">✏️ loggen</strong> klicken → Position in Dashboard erfassen',
        'JSON exportieren → in wm_poly_positions.json einfügen → GitHub Desktop commiten',
        'GitHub Action übernimmt ab da das Monitoring',
      ] : [
        'Echte Ask-Edge ≥ 4pp (nach Spread) + Vol ≥ $1.500 + Pinnacle gelistet',
        'Verdict BET oder ABWÄGEN erforderlich',
        'Nicht am Spieltag selbst (mind. 1 Tag vorher)',
        'Stake: $5.50 flat (keine Edge-Tiers, 01.06. bestätigt)',
        'Telegram-Benachrichtigung im Trades-Channel',
      ])}
      ${arrow}
      ${phase(3, '📊', 'Position schließen', 'alle 30 Min', '#a78bfa', '#0f0d1a', [
        'manage_wm_poly_positions.py überwacht den echten Bid',
        '<strong style="color:#3fb950">Profit-Ziel</strong>: realer Bid-Gewinn ≥ +8% über Entry',
        '<strong style="color:#e3b341">Konvergenz</strong>: Poly innerhalb 1.5pp von Pinn fair',
        '<strong style="color:#f85149">Stop-Loss</strong>: ≥15% im Minus (bis 2h vor KO) → raus',
        'Hard-Close ~40 Min vor Anpfiff · danach CLV + P&L',
      ])}
    </div>

    <!-- Trigger-Kriterien Box -->
    <div style="background:#0d1117;border:1px solid #21262d;border-radius:10px;padding:14px 16px;margin-bottom:10px">
      <div style="font-size:10px;font-weight:800;color:#484f58;letter-spacing:.8px;
                  text-transform:uppercase;margin-bottom:10px">Auto-Trigger Kriterien (ab 1. Juni)</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:6px">
        ${criteriaRow('🎯', 'Mindest-Edge', '≥ 4pp Ask-Edge (nach Spread)', '#3fb950')}
        ${criteriaRow('💧', 'Liquidität', '≥ $1.500 Vol + Buch ≥ $50', '#3fb950')}
        ${criteriaRow('📅', 'Timing', '1 Tag bis ~40 Min vor Anpfiff', '#e3b341')}
        ${criteriaRow('✅', 'Verdict', 'BET oder ABWÄGEN', '#3fb950')}
        ${criteriaRow('📊', 'Datenqualität', 'Form + H2H (≥4pp) oder ELO-only (≥8pp)', '#e3b341')}
        ${criteriaRow('💰', 'Max. Stake', '€5–€15 je nach Edge-Tier', '#a78bfa')}
      </div>
    </div>

    <!-- Was fehlt noch / Roadmap -->
    <details style="background:#0d1117;border:1px solid #21262d;border-radius:10px;
                    padding:12px 16px;cursor:pointer">
      <summary style="font-size:11px;font-weight:700;color:#6e7681;user-select:none;list-style:none;
                      display:flex;align-items:center;gap:6px">
        <span>🗺️</span>
        <span>Roadmap — was noch kommt</span>
        <span style="margin-left:auto;color:#484f58;font-size:10px">▼ ausklappen</span>
      </summary>
      <div style="margin-top:12px;display:flex;flex-direction:column;gap:6px">
        ${[
          ['🔴', 'offen',     'Position-Sync: localStorage → GitHub direkt, ohne manuellen Commit-Schritt'],
          ['🔴', 'offen',     'Bankroll-Tracker: Gesamtexposure + freies Kapital live im Tab'],
          ['🔴', 'offen',     'Multi-Market-Guard: max. 1 Bet pro Spiel (korreliertes Risiko)'],
          ['🟡', 'Jun 11+',   'CLV-Live: Closing-Odds-Freeze aktiviert sobald WM startet'],
          ['🟡', 'Jun 11+',   'Live P&L: nach jedem Spielergebnis auto-updated'],
          ['🟡', 'Jun 11+',   'Auto-Schließen: Position nach Spielende automatisch resolved'],
          ['🟢', 'bereit',    'Telegram Edge Alert (≥5pp neue/steam Edges) → Trades-Channel'],
          ['🟢', 'bereit',    'Sparkline + Action Badge pro Fixture'],
          ['🟢', 'bereit',    'CLOB Orderbook Bid/Ask/Spread/Liquidität'],
          ['🟢', 'bereit',    'Sharp Radar in Fixture integriert (steamLag-Badge)'],
        ].map(([dot, status, text]) =>
          `<div style="display:flex;align-items:flex-start;gap:8px;font-size:11px">
            <span style="flex-shrink:0;margin-top:1px">${dot}</span>
            <span style="color:#484f58;font-weight:700;min-width:48px;flex-shrink:0">${status}</span>
            <span style="color:#8b949e">${text}</span>
          </div>`
        ).join('')}
      </div>
    </details>

  </div>`;
}

function _renderWmMarketTable() {
  _ensureWmPosModal();
  const openPosHtml = _renderWmOpenPositions();

  if (!_wmAllFixtures || _wmAllFixtures.length === 0) {
    return _renderWmSystemGuide() + (openPosHtml
      ? `<div style="margin-bottom:20px">${openPosHtml}</div>`
      : `<div style="text-align:center;padding:60px 20px;color:#484f58">
           <div style="font-size:32px;margin-bottom:10px">⏳</div>
           <div style="font-weight:600">WM-Daten werden geladen…</div>
           <div style="font-size:12px;margin-top:6px">wm_poly_prices.json nicht gefunden oder leer</div>
         </div>`);
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
  // FIX 14.06.2026: beendete Spiele (Anpfiff vorbei) raus aus den HANDLUNGS-Buckets.
  // Settled Poly-Preise (→1.00 / →0 nach Spielende) erzeugten Phantom-Edges in der
  // Alert Zone (z.B. KOR-CZE +31.9pp, USA-PRY +24.6pp — beide längst gespielt, „Poly
  // bietet —"). Kein Trade möglich → es wurde auch nie einer ausgelöst. Filter via
  // _wmKickoffPassed (fx.kickoff aus Polymarket-Gamma). 'all'/'pinn' bleiben (Browse).
  const _live = x => !_wmKickoffPassed(x);
  // liveFix = nur noch ANSTEHENDE Spiele. Beendete Spiele (Anpfiff vorbei) gehören
  // NICHT in die Opportunity-Tabelle: settled Poly-Preise (→1.00/0) erzeugen Phantom-
  // Edges (+43pp etc.) und ein „BET"/„Position loggen" auf ein gelaufenes Spiel ist
  // irreführend — es kann eh kein Trade mehr ausgelöst werden. Sie bleiben oben in der
  // Performance/Verlauf-Sektion sichtbar. Gilt jetzt für ALLE Buckets inkl. Default 'all'.
  const liveFix = allFix.filter(_live);
  const finishedCount = allFix.length - liveFix.length;
  const steamFix  = liveFix.filter(x => x.steamLag === true);
  const growFix   = liveFix.filter(x => x.edgeTrend === 'growing' && (x.bestEdge||0) >= 2);
  const alertFix  = liveFix.filter(x => (x.bestEdge||0) >= ALERT_EDGE_PP)
                          .sort((a,b) => (b.momentumScore||0) - (a.momentumScore||0));
  const counts = {
    steam: steamFix.length,
    grow:  growFix.length,
    alert: alertFix.length,
    pinn:  liveFix.filter(x => x.hasPinnacle).length,
    all:   liveFix.length,
  };

  const tableFix = (() => {
    if (f === 'steam')  return steamFix;
    if (f === 'grow')   return growFix;
    if (f === 'alert')  return alertFix;
    if (f === 'pinn')   return liveFix.filter(x => x.hasPinnacle);
    // Default 'all': nur noch anstehende Spiele, sortiert nach Momentum (aus Python)
    return liveFix;
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

  // ── Fixture card ─────────────────────────────────────────────────────────
  const fixtureCard = (fix, compact=false) => {
    const [fy, fm, fd] = (fix.date || '').split('-');
    const dateFmt = fy ? `${fd}.${fm}.${fy.slice(2)}` : '—';
    const polyUrl    = fix.slug ? `https://polymarket.com/de/sports/fifa-world-cup/${fix.slug}` : '#';
    const moreMktUrl = fix.moreMktSlug ? `https://polymarket.com/de/sports/fifa-world-cup/${fix.moreMktSlug}` : polyUrl;
    const be  = fix.bestEdge || 0;
    const bk  = fix.bestEdgeKey || '';
    const mktNames = { hw:'Heimsieg', dr:'Unentschieden', aw:'Auswärtssieg', o25:'Über 2.5 Tore', u25:'Unter 2.5 Tore' };
    const mktLabel  = mktNames[bk] || '';
    const fairProb  = fix[`fair_${bk}`];
    const polyProb  = fix[`poly_${bk}`];
    const fairOdds  = fairProb && fairProb > 0 ? (1/fairProb).toFixed(2) : '—';
    const polyOdds  = polyProb && polyProb > 0 ? (1/polyProb).toFixed(2) : '—';

    const trend      = fix.edgeTrend || '';
    const steamLag   = fix.steamLag === true;
    const bestDelta  = fix.bestEdgeKey ? (fix[`edgeDelta_${fix.bestEdgeKey}`] ?? null) : null;

    const borderCol = steamLag ? '#f8514966' : be >= 5 ? '#3fb95066' : be >= ALERT_EDGE_PP ? '#e3b34155' : '#21262d';
    const bgCol     = steamLag ? 'rgba(248,81,73,.025)' : be >= 5 ? 'rgba(8,20,8,.7)' : be >= ALERT_EDGE_PP ? 'rgba(20,16,0,.7)' : '#0d1117';

    // ── Zone 1: 2-row header ─────────────────────────────────────────────────
    const header = `
    <div style="margin-bottom:12px">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:5px">
        <span style="font-size:15px;font-weight:700;color:#e6edf3">${fix.home} <span style="color:#484f58;font-weight:400;font-size:13px">vs</span> ${fix.away}</span>
        <a href="${polyUrl}" target="_blank" rel="noopener"
           style="background:#a78bfa22;border:1px solid #a78bfa55;border-radius:7px;
                  color:#a78bfa;font-size:11px;font-weight:700;padding:4px 12px;
                  text-decoration:none;white-space:nowrap;flex-shrink:0">🔗 Polymarket</a>
      </div>
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
        <span style="font-size:12px;color:#6e7681">${dateFmt}</span>
        ${daysBadge(fix.date)}
        ${be > 0 ? `<span style="font-size:11px;font-weight:800;color:${ec(be)};background:${eb(be)};padding:2px 8px;border-radius:8px;border:1px solid ${ec(be)}44">+${be}pp Edge</span>` : ''}
        <span style="margin-left:auto;font-size:10px;color:#484f58">Vol $${(fix.vol||0).toLocaleString('de-DE',{maximumFractionDigits:0})}</span>
      </div>
    </div>`;

    // ── Zone 2: Hero Bet ─────────────────────────────────────────────────────
    // Loudest element — left-bordered, big edge number, filled CTA
    const heroHtml = (bk && be > 0) ? (() => {
      const heroBorderCol = be >= 5 ? '#3fb950' : be >= 3 ? '#e3b341' : '#6e7681';
      const heroBg        = be >= 5 ? 'rgba(63,185,80,.06)'   : be >= 3 ? 'rgba(227,179,65,.05)'  : 'rgba(28,33,40,.5)';
      const verdictLabel  = be >= 5 ? 'BET'       : be >= 3 ? 'ABWÄGEN'  : 'BEOBACHTEN';
      const verdictBg     = be >= 5 ? 'rgba(63,185,80,.18)'  : be >= 3 ? 'rgba(227,179,65,.15)' : 'rgba(110,118,129,.12)';
      const verdictBorder = be >= 5 ? '#3fb95055' : be >= 3 ? '#e3b34155'  : '#6e768155';
      const betBtnHtml = be >= ALERT_EDGE_PP ? `
        <button onclick="event.stopPropagation();_wmBetConfirm(decodeURIComponent('${
          encodeURIComponent(JSON.stringify({home:fix.home,away:fix.away,market:mktLabel,polyPrice:polyProb,pinnFair:fairProb,slug:(bk==='o25'||bk==='u25')?(fix.moreMktSlug||fix.slug):fix.slug,edge:be}))
        }'))"
          style="background:${heroBorderCol};color:#000;border:none;border-radius:7px;
                 font-size:12px;font-weight:800;padding:7px 18px;cursor:pointer;
                 letter-spacing:.3px;font-family:inherit;transition:opacity .15s;white-space:nowrap"
          onmouseover="this.style.opacity='.8'" onmouseout="this.style.opacity='1'">🟣 Position loggen</button>` : `
        <button onclick="event.stopPropagation();_wmBetConfirm(decodeURIComponent('${
          encodeURIComponent(JSON.stringify({home:fix.home,away:fix.away,market:mktLabel,polyPrice:polyProb,pinnFair:fairProb,slug:(bk==='o25'||bk==='u25')?(fix.moreMktSlug||fix.slug):fix.slug,edge:be}))
        }'))"
          style="background:transparent;border:1px solid ${heroBorderCol}44;border-radius:7px;
                 color:${heroBorderCol};font-size:11px;font-weight:700;padding:5px 14px;cursor:pointer;
                 font-family:inherit;transition:opacity .15s;white-space:nowrap"
          onmouseover="this.style.opacity='.7'" onmouseout="this.style.opacity='1'">Loggen</button>`;

      return `<div style="border-left:3px solid ${heroBorderCol};background:${heroBg};
                          border-radius:0 10px 10px 0;padding:12px 16px;margin-bottom:10px">
        <div style="font-size:8px;font-weight:800;color:${heroBorderCol};text-transform:uppercase;
                    letter-spacing:.8px;margin-bottom:6px">🎯 Bester Markt — jetzt handeln</div>
        <div style="font-size:13px;color:#8b949e;margin-bottom:4px">${mktLabel}</div>
        <div style="display:flex;align-items:flex-end;gap:10px;margin-bottom:10px;flex-wrap:wrap">
          <div>
            <span style="font-size:28px;font-weight:900;color:${heroBorderCol};line-height:1">+${be}pp</span>
          </div>
          <div style="font-size:11px;color:#6e7681;line-height:1.7;padding-bottom:2px">
            Pinnacle fair <strong style="color:#8b949e">${fairOdds}</strong><br>
            Poly bietet <strong style="color:#a78bfa">${polyOdds}</strong>
          </div>
          <span style="font-size:11px;font-weight:800;background:${verdictBg};color:${heroBorderCol};
                       border:1px solid ${verdictBorder};border-radius:7px;padding:4px 10px;
                       align-self:flex-end;letter-spacing:.3px">${verdictLabel}</span>
        </div>
        ${betBtnHtml}
      </div>`;
    })() : '';

    // ── Zone 3: Signal strip ─────────────────────────────────────────────────
    const badge = _computeActionBadge(fix);
    const signalHtml = (badge.label !== 'Kein Signal') ? `
    <div style="display:flex;align-items:flex-start;gap:8px;margin-bottom:10px;padding:7px 10px;
                background:rgba(0,0,0,.2);border-radius:7px">
      <span style="font-size:14px;flex-shrink:0;margin-top:1px">${badge.icon}</span>
      <div>
        <span style="font-size:11px;font-weight:800;color:${badge.col}">${badge.label}</span>
        <div style="font-size:11px;color:#6e7681;margin-top:1px;line-height:1.45">${badge.reason}</div>
      </div>
    </div>` : '';

    // ── Zone 3b: Steam Lag Explainer ─────────────────────────────────────────
    // Shown whenever steamLag is true — explains what happened and what to do.
    const steamExplainerHtml = steamLag ? (() => {
      const moveStr  = fix.pinnSteamMove ? `+${fix.pinnSteamMove}pp` : 'signifikant';
      const mktLabel = ({ hw:'Heimsieg', aw:'Auswärtssieg', dr:'Unentschieden',
                          o25:'Over 2.5 Tore', u25:'Under 2.5 Tore', btts:'BTTS' })[fix.bestEdgeKey] || fix.bestEdgeKey || 'diesen Markt';
      const be = fix.bestEdge || 0;

      // Action recommendation based on edge size
      let actionLine = '';
      if (be >= 5) {
        actionLine = `<div style="margin-top:8px;padding:7px 10px;border-radius:6px;background:rgba(248,81,73,.12);border:1px solid rgba(248,81,73,.3);font-size:11px;font-weight:700;color:#f85149">
          ⚡ Zeitkritisch — jetzt auf <strong>${mktLabel}</strong> bei Polymarket wetten, bevor der Kurs aufholt. Edge schliesst sich in Minuten bis Stunden.
        </div>`;
      } else if (be >= 2) {
        actionLine = `<div style="margin-top:8px;padding:7px 10px;border-radius:6px;background:rgba(227,179,65,.08);border:1px solid rgba(227,179,65,.25);font-size:11px;color:#e3b341">
          👁 Edge aktuell +${be.toFixed(1)}pp — noch unter Conviction-Schwelle (5pp). Beobachten: wenn Pinnacle weiter zieht und Poly nicht folgt, steigt die Edge auf handelbar. Kurs im Auge behalten.
        </div>`;
      } else {
        actionLine = `<div style="margin-top:8px;font-size:11px;color:#6e7681">
          Edge noch zu klein (+${be.toFixed(1)}pp). Steam-Signal im Auge behalten — wenn Poly weiter schläft, wird diese Situation interessant.
        </div>`;
      }

      return `<div style="margin-bottom:10px;padding:10px 12px;border-radius:8px;
                           background:rgba(248,81,73,.06);border:1px solid rgba(248,81,73,.25);
                           border-left:3px solid #f85149">
        <div style="display:flex;align-items:center;gap:7px;margin-bottom:6px">
          <span style="font-size:14px">🔥</span>
          <span style="font-size:11px;font-weight:800;color:#f85149;letter-spacing:.02em">STEAM LAG — Was ist passiert?</span>
        </div>
        <div style="font-size:11px;color:#c9d1d9;line-height:1.6">
          <strong>Pinnacle</strong> hat den Kurs für <strong>${mktLabel}</strong> gerade um <strong style="color:#f85149">${moveStr}</strong> bewegt.
          Das bedeutet: informierte Wetter (Sharps) haben massiv auf diese Seite gesetzt —
          Pinnacle hat das sofort eingepreist. <strong>Polymarket reagiert verzögert</strong>,
          weil der Preis dort dezentral durch Liquidity Provider angepasst wird.
          Dieses Zeitfenster ist die Opportunity.
        </div>
        ${actionLine}
      </div>`;
    })() : '';

    // ── Zone 4: Sparkline ────────────────────────────────────────────────────
    const sparklineSvg = _drawFixtureSparkline(fix.key, fix.bestEdgeKey);

    // Rec 01: Market label pill
    const _edgeKeyToLabel = { hw:'🏠 Heimsieg', aw:'✈️ Auswärtssieg', dr:'⚖️ Unentschieden',
      draw:'⚖️ Unentschieden', o25:'📈 Over 2.5 Tore', u25:'📉 Under 2.5 Tore',
      o15:'📈 Over 1.5 Tore', o35:'📈 Over 3.5 Tore', btts:'⚽ BTTS' };
    const _mktLabel = _edgeKeyToLabel[fix.bestEdgeKey] || fix.bestEdgeKey || '';

    // Rec 04: Edge badge + trend icon
    const _edgePP = fix.bestEdge || 0;
    const _trend  = fix.edgeTrend || 'stable';
    const _trendIcon  = _trend === 'widening' ? '↑' : _trend === 'narrowing' ? '↓' : '→';
    const _trendCol   = _trend === 'widening' ? '#3fb950' : _trend === 'narrowing' ? '#f85149' : '#e3b341';
    const _edgeSign   = _edgePP >= 0 ? '+' : '';

    const chartHtml = sparklineSvg ? `<div style="margin-bottom:10px">
      <!-- Rec 01+04: Header row — market label left, edge badge right -->
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
        <span style="display:inline-flex;align-items:center;gap:5px;
                     background:#21262d;border:0.5px solid #30363d;border-radius:5px;
                     padding:3px 9px;font-size:11px;font-weight:700;color:#c9d1d9">
          📊 ${_mktLabel}
        </span>
        <span style="display:inline-flex;align-items:center;gap:5px;
                     background:${_trend==='widening'?'#0d2818':_trend==='narrowing'?'#2d0f0f':'#1c1a0e'};
                     border:0.5px solid ${_trendCol}44;border-radius:5px;
                     padding:3px 9px;font-size:11px;font-weight:800;color:${_trendCol}">
          ${_edgeSign}${_edgePP.toFixed(1)}pp ${_trendIcon}
        </span>
      </div>
      ${sparklineSvg}
      <!-- Rec 03: Updated legend with line styles -->
      <div style="display:flex;align-items:center;gap:16px;font-size:10px;color:#6e7681;margin-top:4px;padding-left:2px">
        <span style="display:flex;align-items:center;gap:5px">
          <svg width="20" height="10" style="flex-shrink:0"><line x1="0" y1="5" x2="20" y2="5" stroke="#58a6ff" stroke-width="2"/></svg>
          Pinnacle fair
        </span>
        <span style="display:flex;align-items:center;gap:5px">
          <svg width="20" height="10" style="flex-shrink:0"><line x1="0" y1="5" x2="20" y2="5" stroke="#a78bfa" stroke-width="1.5" stroke-dasharray="4 3"/></svg>
          Polymarket
        </span>
        ${steamLag ? '<span style="color:#f85149;font-weight:700;margin-left:4px">🔥 Steam-Move</span>' : ''}
      </div>
    </div>` : '';

    // ── Zone 5: Outcomes — hierarchy-aware ──────────────────────────────────
    // Best row: hero highlight. SKIP rows: 45% opacity. Log buttons differentiated.
    const outcomeRow = (label, pinnOdds, polyProbVal, edge, betOrder, isHero) => {
      if (!polyProbVal) return '';
      const pOdds = polyProbVal > 0 ? (1/polyProbVal).toFixed(2) : '—';
      const col   = ec(edge);
      const isSkip = edge !== null && edge < 0;
      const opacity = isSkip ? 'opacity:.45;' : '';
      const hlBg  = isHero ? `background:${eb(edge)};border:1px solid ${col}44;` : 'background:#161b22;border:1px solid #21262d;';

      const btnHtml = (betOrder && polyProbVal && edge !== null && edge >= ALERT_EDGE_PP)
        ? `<button onclick="event.stopPropagation();_wmBetConfirm(decodeURIComponent('${encodeURIComponent(JSON.stringify(betOrder))}'))"
            style="background:${col};color:#000;border:none;border-radius:5px;
                   font-size:10px;font-weight:800;padding:3px 10px;cursor:pointer;white-space:nowrap;font-family:inherit"
            onmouseover="this.style.opacity='.8'" onmouseout="this.style.opacity='1'">🟣 Loggen</button>`
        : (betOrder ? `<button onclick="event.stopPropagation();_wmBetConfirm(decodeURIComponent('${encodeURIComponent(JSON.stringify(betOrder))}'))"
            style="background:transparent;border:1px solid #484f58;border-radius:5px;
                   color:#484f58;font-size:10px;font-weight:600;padding:2px 8px;cursor:pointer;white-space:nowrap;font-family:inherit"
            onmouseover="this.style.opacity='.7'" onmouseout="this.style.opacity='1'">Loggen</button>` : '');

      return `<div style="display:flex;align-items:center;gap:8px;padding:7px 10px;
                          border-radius:8px;${hlBg}${opacity}margin-bottom:4px">
        <span style="font-size:11px;color:#6e7681;font-weight:700;min-width:14px">${label}</span>
        ${pinnOdds ? `<span style="font-size:12px;color:#6e7681">${fmt(pinnOdds)}</span>
                      <span style="font-size:10px;color:#484f58">→</span>` : ''}
        <span style="font-size:13px;color:#a78bfa;font-weight:800">${pOdds}</span>
        ${edge !== null ? `<span style="font-size:11px;font-weight:800;color:${col}">
          ${edge > 0 ? '+' + edge : edge}pp${edge >= ALERT_EDGE_PP ? ' ▲' : ''}
        </span>` : ''}
        <span style="margin-left:auto">${btnHtml}</span>
      </div>`;
    };

    let outcomesHtml = '';
    if (fix.hasPinnacle) {
      const bestMktForH   = bk === 'hw';
      const bestMktForX   = bk === 'dr';
      const bestMktForA   = bk === 'aw';
      outcomesHtml = `<div style="margin-bottom:8px">
        <div style="font-size:9px;font-weight:700;color:#484f58;text-transform:uppercase;letter-spacing:.5px;margin-bottom:5px">1X2</div>
        ${outcomeRow('H', fix.pinn_hw, fix.poly_hw, fix.edge_hw,
          {home:fix.home,away:fix.away,market:'Heimsieg',polyPrice:fix.poly_hw,pinnFair:fix.fair_hw,slug:fix.slug,edge:fix.edge_hw,
           conviction:fix.conviction_hw,signalAdj:fix.signalAdj_hw,effectiveEdge:fix.effectiveEdge_hw,synthetic:fix.synthetic_hw}, bestMktForH)}
        ${outcomeRow('X', fix.pinn_dr, fix.poly_dr, fix.edge_dr,
          {home:fix.home,away:fix.away,market:'Unentschieden',polyPrice:fix.poly_dr,pinnFair:fix.fair_dr,slug:fix.slug,edge:fix.edge_dr,
           conviction:fix.conviction_dr,signalAdj:fix.signalAdj_dr,effectiveEdge:fix.effectiveEdge_dr,synthetic:fix.synthetic_dr}, bestMktForX)}
        ${outcomeRow('A', fix.pinn_aw, fix.poly_aw, fix.edge_aw,
          {home:fix.home,away:fix.away,market:'Auswärtssieg',polyPrice:fix.poly_aw,pinnFair:fix.fair_aw,slug:fix.slug,edge:fix.edge_aw,
           conviction:fix.conviction_aw,signalAdj:fix.signalAdj_aw,effectiveEdge:fix.effectiveEdge_aw,synthetic:fix.synthetic_aw}, bestMktForA)}
      </div>`;
    } else {
      outcomesHtml = `<div style="font-size:11px;color:#484f58;padding:4px 0;display:flex;gap:12px;flex-wrap:wrap;margin-bottom:8px">
        <span>⏳ Pinnacle noch nicht gelistet</span>
        ${fix.poly_hw ? `<span style="color:#6e7681">H <strong style="color:#a78bfa">${p2o(fix.poly_hw)}</strong></span>` : ''}
        ${fix.poly_dr ? `<span style="color:#6e7681">X <strong style="color:#a78bfa">${p2o(fix.poly_dr)}</strong></span>` : ''}
        ${fix.poly_aw ? `<span style="color:#6e7681">A <strong style="color:#a78bfa">${p2o(fix.poly_aw)}</strong></span>` : ''}
        ${fix.poly_o25 ? `<span style="color:#6e7681">O2.5 <strong style="color:#a78bfa">${p2o(fix.poly_o25)}</strong></span>` : ''}
        ${fix.poly_btts ? `<span style="color:#6e7681">BTTS <strong style="color:#a78bfa">${p2o(fix.poly_btts)}</strong></span>` : ''}
      </div>`;
    }

    // ── Zone 6: O/U + BTTS chips ────────────────────────────────────────────
    let ouHtml = '';
    if (fix.poly_o25 || fix.poly_btts) {
      const ouSlug = fix.moreMktSlug || fix.slug;
      const bestMktO25 = bk === 'o25';
      const bestMktU25 = bk === 'u25';
      ouHtml = `<div style="border-top:1px solid #21262d;padding-top:8px;margin-top:4px">
        <div style="font-size:9px;font-weight:700;color:#484f58;text-transform:uppercase;letter-spacing:.5px;margin-bottom:5px">Over / Under + BTTS</div>
        ${fix.poly_o25 ? outcomeRow('O2.5', fix.pinn_o25||null, fix.poly_o25, fix.edge_o25??null,
          {home:fix.home,away:fix.away,market:'Über 2.5 Tore',polyPrice:fix.poly_o25,pinnFair:fix.fair_o25,slug:ouSlug,edge:fix.edge_o25,
           conviction:fix.conviction_o25,signalAdj:fix.signalAdj_o25,effectiveEdge:fix.effectiveEdge_o25,synthetic:fix.synthetic_o25}, bestMktO25) : ''}
        ${fix.poly_u25 ? outcomeRow('U2.5', fix.pinn_u25||null, fix.poly_u25, fix.edge_u25??null,
          {home:fix.home,away:fix.away,market:'Unter 2.5 Tore',polyPrice:fix.poly_u25,pinnFair:fix.fair_u25,slug:ouSlug,edge:fix.edge_u25,
           conviction:fix.conviction_u25,signalAdj:fix.signalAdj_u25,effectiveEdge:fix.effectiveEdge_u25,synthetic:fix.synthetic_u25}, bestMktU25) : ''}
        ${fix.poly_o15 ? outcomeRow('O1.5', null, fix.poly_o15, null,
          {home:fix.home,away:fix.away,market:'Über 1.5 Tore',polyPrice:fix.poly_o15,slug:ouSlug,edge:null}, false) : ''}
        ${fix.poly_o35 ? outcomeRow('O3.5', null, fix.poly_o35, null,
          {home:fix.home,away:fix.away,market:'Über 3.5 Tore',polyPrice:fix.poly_o35,slug:ouSlug,edge:null}, false) : ''}
        ${fix.poly_btts ? outcomeRow('BTTS', null, fix.poly_btts, null,
          {home:fix.home,away:fix.away,market:'Beide Teams treffen',polyPrice:fix.poly_btts,slug:ouSlug,edge:null}, false) : ''}
        <a href="${moreMktUrl}" target="_blank" rel="noopener"
           style="display:inline-block;margin-top:5px;font-size:10px;color:#a78bfa44;text-decoration:none;transition:color .15s"
           onmouseover="this.style.color='#a78bfa'" onmouseout="this.style.color='#a78bfa44'">+ Alle Märkte auf Polymarket →</a>
      </div>`;
    }

    // ── Zone 7: Orderbook — minimal/tertiary ─────────────────────────────────
    let depthHtml = '';
    if (fix.clobBid != null && fix.clobAsk != null) {
      const mktLbl    = {hw:'H',dr:'X',aw:'A',o25:'O2.5',u25:'U2.5'}[fix.clobMarket||''] || '';
      const spreadCol = fix.clobSpreadPP <= 2 ? '#3fb950' : fix.clobSpreadPP <= 4 ? '#e3b341' : '#f85149';
      const liqCol    = (fix.clobTopLiq||0) >= 1000 ? '#3fb950' : (fix.clobTopLiq||0) >= 300 ? '#e3b341' : '#6e7681';
      depthHtml = `<div style="margin-top:8px;padding-top:6px;border-top:1px solid #21262d;
                               display:flex;gap:14px;flex-wrap:wrap;font-size:10px;color:#484f58;align-items:center">
        <span style="font-weight:600">${mktLbl} Orderbook:</span>
        <span>Bid <strong style="color:#3fb950">${Math.round(fix.clobBid*100)}¢</strong></span>
        <span>Ask <strong style="color:#f85149">${Math.round(fix.clobAsk*100)}¢</strong></span>
        <span>Spread <strong style="color:${spreadCol}">${fix.clobSpreadPP}pp</strong></span>
        <span>Liq <strong style="color:${liqCol}">$${(fix.clobTopLiq||0).toLocaleString('de-DE',{maximumFractionDigits:0})}</strong></span>
      </div>`;
    }

    return `<div style="background:${bgCol};border:1px solid ${borderCol};border-left:3px solid ${borderCol};
                        border-radius:10px;padding:12px 16px;margin-bottom:8px">
      ${header}${heroHtml}${steamExplainerHtml}${signalHtml}${chartHtml}${outcomesHtml}${ouHtml}${depthHtml}
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

  // ── Trade Brief Cards (replaces compact table) ────────────────────────────
  const mktNames = { hw:'Heimsieg', dr:'Unentschieden', aw:'Auswärtssieg', o25:'Über 2.5 Tore', u25:'Unter 2.5 Tore' };

  const tradeBriefCard = fix => {
    const [fy, fm, fd] = (fix.date || '').split('-');
    const dateFmt = fy ? `${fd}.${fm}.` : '—';
    const d = daysUntil(fix.date);
    const dStr = d === null ? ''
      : d <= 0  ? `<span style="background:#f8514922;border:1px solid #f8514944;border-radius:5px;color:#f85149;font-size:9px;font-weight:800;padding:2px 6px">HEUTE</span>`
      : d === 1 ? `<span style="background:#e3b34115;border:1px solid #e3b34133;border-radius:5px;color:#e3b341;font-size:9px;font-weight:800;padding:2px 6px">MORGEN</span>`
      : d <= 7  ? `<span style="font-size:10px;color:#e3b341;font-weight:700">${d}d</span>`
      : `<span style="font-size:10px;color:#484f58">${d}d</span>`;

    const be  = fix.bestEdge || 0;
    const bk  = fix.bestEdgeKey || '';
    const polyUrl    = fix.slug ? `https://polymarket.com/de/sports/fifa-world-cup/${fix.slug}` : '#';
    const moreMktUrl = fix.moreMktSlug ? `https://polymarket.com/de/sports/fifa-world-cup/${fix.moreMktSlug}` : polyUrl;

    // Decision panel colours
    const panelCol    = be >= 5 ? '#3fb950' : be >= 3 ? '#e3b341' : be >= 1 ? '#6e7681' : '#484f58';
    const panelBg     = be >= 5 ? 'rgba(63,185,80,.06)'    : be >= 3 ? 'rgba(227,179,65,.05)' : 'rgba(22,27,34,.5)';
    const panelBorder = be >= 5 ? 'rgba(63,185,80,.22)'    : be >= 3 ? 'rgba(227,179,65,.18)' : '#21262d';
    const verdict     = be >= 5 ? { label:'BET',        col:'#3fb950', bg:'rgba(63,185,80,.15)'  }
                      : be >= 3 ? { label:'ABWÄGEN',    col:'#e3b341', bg:'rgba(227,179,65,.12)' }
                      : be > 0  ? { label:'BEOBACHTEN', col:'#6e7681', bg:'rgba(110,118,129,.1)' }
                      :           { label:'KEIN SIGNAL',col:'#484f58', bg:'transparent'          };

    const fairProb = fix[`fair_${bk}`];
    const polyProb = fix[`poly_${bk}`];
    const fairOdds = fairProb && fairProb > 0 ? (1/fairProb).toFixed(2) : '—';
    const polyOdds = polyProb && polyProb > 0 ? (1/polyProb).toFixed(2) : '—';
    const fairPct  = fairProb ? Math.round(fairProb * 100) + '%' : '—';
    const polyPct  = polyProb ? Math.round(polyProb * 100) + '%' : '—';

    // Best-market bet order for log button
    const bestBetOrder = bk && be >= ALERT_EDGE_PP ? JSON.stringify({
      home:fix.home, away:fix.away, market:mktNames[bk]||bk,
      polyPrice:polyProb, pinnFair:fairProb,
      slug:(bk==='o25'||bk==='u25')?(fix.moreMktSlug||fix.slug):fix.slug,
      edge:be
    }) : null;

    // ── Left: Decision Panel ────────────────────────────────────────────────
    const decisionPanel = bk && be > 0 ? `
      <div style="flex-shrink:0;width:195px;background:${panelBg};border:1px solid ${panelBorder};
                  border-radius:8px;padding:11px 13px;display:flex;flex-direction:column;gap:5px">
        <div style="font-size:8px;font-weight:800;color:${panelCol};text-transform:uppercase;letter-spacing:.7px">🎯 Bester Markt</div>
        <div style="font-size:12px;font-weight:800;color:#e6edf3;line-height:1.2">${mktNames[bk]||bk}</div>
        <div style="display:flex;align-items:baseline;gap:5px">
          <span style="font-size:22px;font-weight:900;color:${panelCol};line-height:1">+${be}pp</span>
          <span style="font-size:9px;color:#6e7681">Edge</span>
        </div>
        <div style="font-size:10px;color:#6e7681;line-height:1.7">
          Pinn fair: <strong style="color:#8b949e">${fairPct}</strong> (${fairOdds})<br>
          Poly: <strong style="color:#a78bfa">${polyPct}</strong> (${polyOdds})
        </div>
        <span style="font-size:10px;font-weight:800;background:${verdict.bg};color:${verdict.col};
                     border:1px solid ${verdict.col}44;border-radius:6px;padding:3px 9px;
                     display:inline-block;align-self:flex-start;letter-spacing:.3px">${verdict.label}</span>
        ${bestBetOrder ? `<button onclick="event.stopPropagation();_wmBetConfirm(decodeURIComponent('${
          encodeURIComponent(bestBetOrder)}'))"
          style="margin-top:2px;background:linear-gradient(135deg,#e3b34120,#8b7a1218);
                 border:1px solid #e3b34155;border-radius:6px;color:#e3b341;
                 font-size:10px;font-weight:700;padding:4px 10px;cursor:pointer;
                 transition:opacity .15s;font-family:inherit"
          onmouseover="this.style.opacity='.7'" onmouseout="this.style.opacity='1'">🟣 Position loggen</button>` : ''}
      </div>` : `
      <div style="flex-shrink:0;width:195px;background:rgba(22,27,34,.4);border:1px solid #21262d;
                  border-radius:8px;padding:11px 13px;display:flex;flex-direction:column;
                  align-items:center;justify-content:center;gap:6px;text-align:center">
        <span style="font-size:20px;opacity:.25">📊</span>
        <span style="font-size:10px;color:#484f58;line-height:1.5">Noch kein<br>Pinnacle-Signal</span>
      </div>`;

    // ── Right: Markets grid ─────────────────────────────────────────────────
    const mktRow = (label, pinnOdds, polyProbVal, edgePP, isKey) => {
      if (!polyProbVal && !pinnOdds) return '';
      const pOdds = polyProbVal && polyProbVal > 0 ? (1/polyProbVal).toFixed(2) : '—';
      const pPct  = polyProbVal ? Math.round(polyProbVal * 100) + '%' : '';
      const eCol  = edgePP >= 3 ? '#3fb950' : edgePP >= 1 ? '#e3b341' : edgePP > 0 ? '#6e7681' : '#484f58';
      const eStr  = edgePP != null ? (edgePP > 0 ? `+${edgePP}pp` : `${edgePP}pp`) : '—';
      const hlBg  = isKey ? 'rgba(0,212,161,.05)' : 'transparent';
      const hlBrd = isKey
        ? (be >= 5 ? '1px solid rgba(63,185,80,.25)' : '1px solid rgba(0,212,161,.18)')
        : '1px solid transparent';
      const lblCol = isKey ? panelCol : '#6e7681';
      return `<div style="display:grid;grid-template-columns:36px 68px 80px 54px;align-items:center;
                          gap:0;padding:4px 8px;border-radius:6px;
                          background:${hlBg};border:${hlBrd};margin-bottom:2px">
        <span style="font-size:10px;font-weight:800;color:${lblCol}">${label}${isKey ? ' ◀' : ''}</span>
        <span style="font-size:11px;color:#6e7681">${pinnOdds ? fmt(pinnOdds) : '<span style="color:#21262d">—</span>'}</span>
        <span style="font-size:11px;color:#a78bfa;font-weight:${isKey ? '800' : '600'}">${pOdds} <span style="font-size:9px;color:#6e768166">${pPct}</span></span>
        <span style="font-size:10px;font-weight:700;color:${eCol};text-align:right">${eStr}</span>
      </div>`;
    };

    const marketsHtml = `
      <div style="flex:1;min-width:0">
        <div style="display:grid;grid-template-columns:36px 68px 80px 54px;gap:0;padding:2px 8px 5px;margin-bottom:1px">
          <span style="font-size:8px;color:#484f58;font-weight:700;text-transform:uppercase;letter-spacing:.3px">MARKT</span>
          <span style="font-size:8px;color:#484f58;font-weight:700;text-transform:uppercase;letter-spacing:.3px">PINNACLE</span>
          <span style="font-size:8px;color:#6e40c9aa;font-weight:700;text-transform:uppercase;letter-spacing:.3px">POLYMARKET</span>
          <span style="font-size:8px;color:#484f58;font-weight:700;text-align:right;text-transform:uppercase;letter-spacing:.3px">EDGE</span>
        </div>
        ${mktRow('H',    fix.pinn_hw,  fix.poly_hw,  fix.edge_hw  ?? null, bk==='hw')}
        ${mktRow('X',    fix.pinn_dr,  fix.poly_dr,  fix.edge_dr  ?? null, bk==='dr')}
        ${mktRow('A',    fix.pinn_aw,  fix.poly_aw,  fix.edge_aw  ?? null, bk==='aw')}
        ${(fix.poly_o25||fix.pinn_o25) ? `<div style="border-top:1px solid #21262d;margin:3px 0 4px"></div>` : ''}
        ${(fix.poly_o25||fix.pinn_o25) ? mktRow('O2.5', fix.pinn_o25, fix.poly_o25, fix.edge_o25??null, bk==='o25') : ''}
        ${(fix.poly_u25||fix.pinn_u25) ? mktRow('U2.5', fix.pinn_u25, fix.poly_u25, fix.edge_u25??null, bk==='u25') : ''}
        ${fix.poly_btts ? mktRow('BTTS', null, fix.poly_btts, null, false) : ''}
        ${fix.hasMoreMarkets ? `<a href="${moreMktUrl}" target="_blank" rel="noopener"
           style="display:block;margin-top:5px;padding:2px 8px;font-size:9px;color:#a78bfa44;
                  text-decoration:none;transition:color .15s"
           onmouseover="this.style.color='#a78bfa'" onmouseout="this.style.color='#a78bfa44'">+ Alle Märkte auf Polymarket →</a>` : ''}
      </div>`;

    // ── Signal strip ─────────────────────────────────────────────────────────
    const sigs = [];
    if (fix.steamLag)
      sigs.push(`<span style="background:#f8514918;border:1px solid #f8514944;border-radius:6px;padding:2px 8px;font-size:9px;font-weight:800;color:#f85149">🔥 Steam Lag${fix.pinnSteamMove?' · Pinn +'+fix.pinnSteamMove+'pp':''}</span>`);
    if (fix.edgeTrend==='growing')
      sigs.push(`<span style="background:#3fb95012;border:1px solid #3fb95030;border-radius:6px;padding:2px 8px;font-size:9px;font-weight:700;color:#3fb950">📈 Edge wächst</span>`);
    if (fix.edgeTrend==='closing')
      sigs.push(`<span style="background:#e3b34110;border:1px solid #e3b34130;border-radius:6px;padding:2px 8px;font-size:9px;font-weight:700;color:#e3b341">📉 Edge schließt</span>`);
    if (fix.edgeTrend==='new' && be > 0)
      sigs.push(`<span style="background:#60a5fa12;border:1px solid #60a5fa30;border-radius:6px;padding:2px 8px;font-size:9px;font-weight:700;color:#60a5fa">🆕 Neu</span>`);
    if ((fix.momentumScore||0) >= 7)
      sigs.push(`<span style="font-size:9px;font-weight:700;color:#f85149">⚡ Momentum ${fix.momentumScore}/10</span>`);
    else if ((fix.momentumScore||0) >= 5)
      sigs.push(`<span style="font-size:9px;font-weight:700;color:#e3b341">Momentum ${fix.momentumScore}/10</span>`);
    if (fix.vol)
      sigs.push(`<span style="font-size:9px;color:#484f58">Vol $${fix.vol.toLocaleString('de-DE',{maximumFractionDigits:0})}</span>`);

    const cardBorderCol = fix.steamLag ? 'rgba(248,81,73,.40)' : be >= 5 ? 'rgba(63,185,80,.30)' : be >= 3 ? 'rgba(227,179,65,.20)' : '#21262d';
    const cardBg        = fix.steamLag ? 'rgba(248,81,73,.025)' : be >= 5 ? 'rgba(8,20,8,.6)' : 'transparent';

    return `<div style="background:${cardBg};border:1px solid ${cardBorderCol};border-radius:10px;margin-bottom:6px;overflow:hidden">
      <div style="display:flex;align-items:center;gap:8px;padding:7px 12px;background:rgba(22,27,34,.8);border-bottom:1px solid #21262d;flex-wrap:wrap">
        <span style="font-size:13px;font-weight:700;color:#c9d1d9">${fix.home} <span style="color:#484f58;font-weight:400">vs</span> ${fix.away}</span>
        <span style="font-size:11px;color:#6e7681">${dateFmt}</span>
        ${dStr}
        <span style="margin-left:auto">
          <a href="${polyUrl}" target="_blank" rel="noopener"
             style="background:#a78bfa18;border:1px solid #a78bfa44;border-radius:5px;
                    color:#a78bfa;font-size:10px;font-weight:700;padding:2px 9px;text-decoration:none">🔗 Poly</a>
        </span>
      </div>
      <div style="display:flex;gap:10px;padding:10px 12px;align-items:flex-start;flex-wrap:wrap">
        ${decisionPanel}
        ${marketsHtml}
      </div>
      ${sigs.length ? `<div style="display:flex;align-items:center;gap:6px;padding:4px 12px 8px;flex-wrap:wrap;border-top:1px solid #21262d">${sigs.join('')}</div>` : ''}
    </div>`;
  };

  const tableRows = tableFix.map(tradeBriefCard).join('');

  const noPinnCount = liveFix.filter(x => !x.hasPinnacle).length;
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
      <a href="steam-lag-log.html" target="_blank"
         style="display:inline-flex;align-items:center;gap:6px;
                background:rgba(248,81,73,.1);border:1px solid rgba(248,81,73,.35);
                border-radius:8px;padding:6px 12px;text-decoration:none;
                font-size:11px;font-weight:700;color:#f85149;
                transition:background .15s;white-space:nowrap"
         onmouseover="this.style.background='rgba(248,81,73,.18)'"
         onmouseout="this.style.background='rgba(248,81,73,.1)'">
        🔥 Steam Lag Log
      </a>
    </div>

    <!-- Info bar -->
    <div style="font-size:11px;color:#6e7681;margin-bottom:12px;line-height:1.6">
      Pinnacle devigged fair-Prob. vs Polymarket — positiver Edge = Poly unterbewertet.
      5× täglich aktualisiert (08/12/16/20/00 Uhr CEST).
      ${noPinnCount > 0 ? `<span style="color:#484f58">${noPinnCount} Spiele noch ohne Pinnacle.</span>` : ''}
    </div>

    <!-- System Guide -->
    ${_renderWmSystemGuide()}

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
      ${filterBtn('all',   `📋 Alle ${counts.all}`, counts.all)}
      ${finishedCount > 0 ? `<span style="font-size:10px;color:#484f58;margin-left:2px">· ${finishedCount} beendet (in Performance)</span>` : ''}
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

    <!-- Trade Brief Cards -->
    ${tableFix.length === 0
      ? `<div style="text-align:center;padding:30px;color:#484f58;font-size:13px">Keine Fixtures für diesen Filter.</div>`
      : `<div>${tableRows}</div>`
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

    // Polymarket USDC balance — 25.07.2026 (Lucas: „falsche balance"): der Betting-Tab las FEST
    // wm_poly_balance.json (stale seit WM-Ende 19.07.). Es ist EINE Wallet — also die FRISCHESTE
    // der Balance-Dateien nehmen (MLS-Pipeline schreibt mls_poly_balance.json). Fehler-Dateien
    // (error-Feld) nur, wenn keine echte existiert.
    Promise.all([
      fetch('mls_poly_balance.json?' + Date.now()).then(r => r.ok ? r.json() : null).catch(() => null),
      fetch('wm_poly_balance.json?'  + Date.now()).then(r => r.ok ? r.json() : null).catch(() => null),
    ])
      .then(([mls, wm]) => {
        const el = document.getElementById('wmPolyBalance');
        if (!el) return;
        const ts = x => (x && x.updatedAt) ? Date.parse(x.updatedAt) : -1;
        const cand = [mls, wm].filter(x => x && (x.total != null || x.usdc != null));
        const good = cand.filter(x => !x.error);
        const d = (good.length ? good : cand).sort((a, b) => ts(b) - ts(a))[0];   // frischeste echte gewinnt
        if (!d) { el.textContent = '—'; return; }
        const total = d.total ?? d.usdc;
        if (total == null) { el.textContent = '—'; return; }
        const updStr = d.updatedAt
          ? ` <span style="color:#484f58;font-size:10px;font-weight:400">(${new Date(d.updatedAt).toLocaleTimeString('de-AT', {hour:'2-digit',minute:'2-digit'})})</span>`
          : '';
        // total = Wallet-Equity (frei + Positionen). Aufschlüsselung zeigen, damit klar ist,
        // warum die Zahl über dem freien, setzbaren Guthaben liegt (Lucas 22.07.2026).
        const pos = Number(d.positions) || 0;
        let breakdown = '';
        if (pos > 0.01) {
          breakdown = ` <span style="color:#484f58;font-size:10px">($${(Number(d.usdc)||0).toFixed(2)} frei + $${pos.toFixed(2)} in Positionen)</span>`;
        } else if (d.usdc_e > 0.01) {
          breakdown = ` <span style="color:#484f58;font-size:10px">(+$${d.usdc_e.toFixed(2)} USDC.e)</span>`;
        }
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

// ── Trade Post-Mortem (21.06.2026, Lucas) — rückblickend „was wäre besser gewesen".
// Quelle: summary.postmortem (resolve_wm_results._write_results). CLV = Entry vs
// Pinnacle-Closing, der Frühindikator für +EV. Markiert lückenhafte CLV-Abdeckung.
function _buildPostmortemHtml(pm) {
  if (!pm || !pm.closedN) return '';
  const eur    = v => v == null ? '—' : `${v >= 0 ? '+' : '-'}€${Math.abs(v).toFixed(2)}`;
  const eurCol = v => (v || 0) >= 0 ? '#3fb950' : '#f85149';
  const clv    = v => v == null ? '<span style="color:#484f58">—</span>'
    : `<span style="color:${v >= 0 ? '#3fb950' : '#f85149'}">${v >= 0 ? '+' : ''}${v.toFixed(1)}pp</span>`;
  const cov = (pm.clvCoverage || '0/0').split('/').map(Number);
  const covLow = cov[1] > 0 && cov[0] / cov[1] < 0.5;
  const covNote = covLow
    ? `<div style="margin-top:8px;padding:8px 10px;background:rgba(227,179,65,.08);border:1px solid rgba(227,179,65,.25);border-radius:8px;font-size:10px;color:#e3b341;line-height:1.5">⚠ CLV nur bei ${pm.clvCoverage} Trades erfasst — Closing-Snapshot noch lückenhaft, Auswertung teilblind. CLV (Entry vs Pinnacle-Closing) ist der Frühindikator für echten Wert.</div>`
    : '';
  const row = (k, v) => `<tr style="border-top:1px solid #161b22">
      <td style="padding:6px 10px;font-size:11px;color:#e6edf3">${k}</td>
      <td style="padding:6px 10px;font-size:11px;text-align:center;color:#8b949e">${v.n}</td>
      <td style="padding:6px 10px;font-size:11px;text-align:right;font-weight:700;color:${eurCol(v.pnl)}">${eur(v.pnl)}</td>
      <td style="padding:6px 10px;font-size:11px;text-align:center">${clv(v.avgClv)} <span style="color:#484f58;font-size:9px">${v.clvCoverage}</span></td>
    </tr>`;
  const mkRows = Object.entries(pm.byMarket || {}).map(([k, v]) => row(k, v)).join('');
  const exRows = Object.entries(pm.byExit   || {}).map(([k, v]) => row(k, v)).join('');
  const htc = pm.heldToClose || {};
  const htcLine = (htc.n || 0) > 0
    ? `🔁 Halten bis Closing: ${htc.exitBetter}× früher-raus besser · ${htc.holdBetter}× halten besser (Ø ${eur(htc.avgDeltaEur)}/Trade)`
    : '🔁 Halten-bis-Closing-Gegenrechnung: noch keine Daten (Poly-Closing-Snapshot fehlt)';
  const tbl = (title, rows) => `
    <div style="margin-top:10px">
      <div style="font-size:10px;color:#6e7681;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">${title}</div>
      <table style="width:100%;border-collapse:collapse;border:1px solid #21262d;border-radius:6px;overflow:hidden">
        <thead><tr style="background:#161b22">
          <th style="padding:5px 10px;font-size:9px;color:#484f58;text-align:left;text-transform:uppercase;letter-spacing:.5px">Segment</th>
          <th style="padding:5px 10px;font-size:9px;color:#484f58;text-align:center;text-transform:uppercase">n</th>
          <th style="padding:5px 10px;font-size:9px;color:#484f58;text-align:right;text-transform:uppercase">P&L</th>
          <th style="padding:5px 10px;font-size:9px;color:#3fb950;text-align:center;text-transform:uppercase">ØCLV</th>
        </tr></thead><tbody>${rows}</tbody>
      </table>
    </div>`;
  return `
    <div style="margin:14px 0;padding:14px 16px;background:#0d1117;border:1px solid #21262d;border-radius:12px">
      <div style="font-size:11px;font-weight:700;color:#484f58;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">🔬 Trade Post-Mortem — was trägt, was nicht</div>
      <div style="font-size:11px;color:#8b949e">${pm.closedN} geschlossen · realisiert <b style="color:${eurCol(pm.realizedPnl)}">${eur(pm.realizedPnl)}</b> · ØCLV ${clv(pm.avgClv)} <span style="color:#484f58">(${pm.clvCoverage})</span></div>
      ${covNote}
      ${tbl('Nach Markt-Typ', mkRows)}
      ${tbl('Nach Exit-Grund', exRows)}
      <div style="margin-top:10px;font-size:10px;color:#8b949e;line-height:1.5">${htcLine}</div>
    </div>`;
}

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
    const resultIcon = {WIN:'✅',LOSS:'❌',VOID:'⬜',PENDING:'⏳',SOLD:'💸'}[b.result] ?? '?';
    const resultCol  = {WIN:'#3fb950',LOSS:'#f85149',VOID:'#8b949e',PENDING:'#e3b341',SOLD:'#a78bfa'}[b.result] ?? '#8b949e';
    const resultLabel = b.result === 'SOLD' ? 'VERKAUFT' : b.result;   // früh verkauft (FIX 13.06.2026)
    const pnlStr2    = b.result === 'WIN'  ? `+€${b.pnl.toFixed(2)}`
                     : b.result === 'LOSS' ? `-€${Math.abs(b.pnl).toFixed(2)}`
                     : b.result === 'SOLD' ? `${b.pnl >= 0 ? '+' : '-'}€${Math.abs(b.pnl || 0).toFixed(2)}`
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
    // Prozess-Urteil aus echten Match-xG (14.06.2026): verdient/Pech/Glück
    const PROC = {
      UNLUCKY:       { t: '😤 unverdient', c: '#e3b341' },
      LUCKY:         { t: '🍀 Glück',      c: '#e3b341' },
      JUSTIFIED:     { t: '✓ verdient',    c: '#3fb950' },
      DESERVED_LOSS: { t: '✓ verd. Niederl.', c: '#8b949e' },
    };
    const _pv = PROC[b.processVerdict];
    const procTag = _pv
      ? `<div style="font-size:9px;color:${_pv.c};font-weight:600;margin-top:2px"
             title="echte Match-xG ${b.xgHome ?? '?'}:${b.xgAway ?? '?'} (Σ ${b.xgTotal ?? '?'})">${_pv.t}</div>`
      : '';

    return `<tr style="border-top:1px solid #161b22">
      <td style="padding:8px 10px;font-size:12px;color:${resultCol};font-weight:700;white-space:nowrap"
          ${b.result === 'SOLD' && b.sellReason ? `title="${b.sellReason.replace(/"/g,'')}"` : ''}>
        ${resultIcon} ${resultLabel}${procTag}
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
      ${_buildPostmortemHtml(s.postmortem)}

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
      <div style="font-size:13px;line-height:1.6">${_polyState.dateStr
        ? `Für <strong>${_polyState.dateStr}</strong> gibt es keine Picks.`
        : `Aktuell steht kein Pick zum Wetten an.`}</div>
      <div style="font-size:12px;line-height:1.6;color:#6e7681;margin-top:8px">
        Hier landen Picks mit Verdict <strong>BET</strong> sowie <strong>ABWÄGEN ab Conviction ${WM_POLY_ABWAEGEN_MIN_CONV}</strong>.
        Schwächere ABWÄGEN-Picks stehen bewusst nur auf den Cards.
      </div>
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

// ═══════════════════════════════════════════════════════════════
// Auto-Trader Config & Live-Status — alles auf einen Blick
// Spiegelt die Werte in auto_wm_poly_trigger.py + manage_wm_poly_positions.py
// (bei Code-Änderungen auch hier nachziehen!)
// ═══════════════════════════════════════════════════════════════
const AUTO_TRADER_CONFIG = {
  trigger: {
    title:    'Auto-Trigger (auto_wm_poly_trigger.py)',
    enabled:  'via GitHub Secret AUTO_TRIGGER_ENABLED',
    rows: [
      { lbl: 'Edge-Schwelle Normal',         val: '≥ 4.0pp',          note: '01.06.26: von 5.0 auf 4.0 gesenkt (Sweet Spot 3-5pp)' },
      { lbl: 'Edge-Schwelle Steam Lag',      val: '≥ 3.0pp',          note: 'Bonus bei Pinn-Move ohne Poly-Reaktion' },
      { lbl: 'Edge-Schwelle elo_only',       val: '≥ 8.0pp',          note: 'Strenger bei dünner Datenbasis' },
      { lbl: 'Pre-Tournament-Schwelle',      val: '≥ 6.0pp',          note: 'Wenn Match > 5 Tage entfernt — frühe Linien sind unsicher' },
      { lbl: 'Min Liquidität (Vol)',         val: '≥ $1.500',         note: 'Schützt vor dünnen Märkten (min_vol_usdc)' },
      { lbl: 'Min Stunden bis Anpfiff',      val: '≥ 4h',             note: 'Kein Kauf zu nah am Spiel' },
      { lbl: 'Min Tage bis Spiel',           val: '≥ 1 Tag',          note: 'Kein Kauf am Spieltag selbst' },
      { lbl: 'Eintritt am echten Ask',       val: 'Spread-Gate',      note: '17.06.26: echte Edge = fair − Ask (nicht Mid). Eintritt zum Ask, nicht zum Mittelpreis.' },
      { lbl: 'Echte Ask-Edge-Floor',         val: '≥ 4.0pp',          note: '17.06.26: der ENTSCHEIDENDE Floor — 4pp nach Spread (alte 5pp waren Mid = ~3pp real)' },
      { lbl: 'Max Eintritts-Spread',         val: '≤ 6.0pp',          note: '17.06.26: zu breiter Spread frisst die Edge → kein Kauf' },
      { lbl: 'Min Orderbuch-Liquidität',     val: '≥ $50',            note: '17.06.26: Top-of-Book Bid+Ask — dünnes Buch = kein Kauf' },
      { lbl: 'Kein Buch → kein Trade',       val: 'require_book',     note: '17.06.26: kein beidseitiges Orderbuch (dünner Markt) → übersprungen statt blind zum Mid' },
    ],
  },
  stake: {
    title: 'Stake & Bankroll',
    rows: [
      { lbl: 'Stake pro Bet',                val: '$5.50 USDC',        note: '€5 flat — keine Edge-Tiers (01.06.26 bestätigt)' },
      { lbl: 'Max Bets / UTC-Tag',           val: '8',                 note: 'Harte Obergrenze' },
      { lbl: 'Max Stake / UTC-Tag',          val: '$50',               note: 'Statisch — siehe Adaptive Cap unten' },
      { lbl: 'Adaptive Daily-Cap',           val: '40% × Balance',     note: 'Bei $40 Balance → $16/Tag · bei $200 → volle $50' },
      { lbl: 'Max Open Exposure',            val: '$80 USDC',          note: 'NEU: Cap auf kumulierter Stake in offenen Positionen' },
      { lbl: 'Min Restbalance nach Bet',     val: '$1',                note: 'Sicherheitspuffer' },
      { lbl: 'Max Positionen / Match',       val: '2',                 note: 'z.B. Über 2.5 + Heimsieg auf gleiches Spiel ok' },
    ],
  },
  sell: {
    title: 'Auto-Sell (manage_wm_poly_positions.py)',
    enabled:  'via GitHub Secret AUTO_SELL_ENABLED',
    rows: [
      { lbl: 'Bewertung am echten Bid',      val: 'realisierbar',      note: '17.06.26: Position am Orderbuch-Bid bewertet (was wir beim Verkauf bekommen), NICHT am Mittelpreis. Killt Spread-Phantom-Gewinne.' },
      { lbl: 'Profit-Target',                val: '+8%',               note: '17.06.26: +10% → +8% — auf REALEM Bid-Gewinn (nicht Mid)' },
      { lbl: 'Profit-Sell-Veto',             val: 'Bid > Entry',       note: '17.06.26: Profit-Mitnahme nur wenn Bid wirklich über Einstieg + Spread eng' },
      { lbl: 'Max Sell-Spread',              val: '≤ 15pp',            note: '17.06.26: nicht in absurd breites Buch verkaufen' },
      { lbl: 'Pinn-Konvergenz-Gap',          val: '≤ 1.5pp',           note: '01.06.26: von 2.0 strenger gemacht' },
      { lbl: 'Min Profit vor Konvergenz',    val: '+3pp',              note: 'Sekundär-Schwelle nicht-bei-0 schließen' },
      { lbl: 'Age-Decay-Schwelle',           val: '+5% nach 36h',      note: 'Alte Positionen mit kleinem Profit schließen (age_decay_profit_target)' },
      { lbl: '🔴 Stop-Loss (früh)',          val: '−15% bis 2h vor KO', note: '16.06.26: ab 2h vor Anpfiff jede Position ≥15% im Minus sofort raus — VOR dem volatilen Aufstellungs-Fenster (early_stoploss_pct 0.15 / early_stoploss_hours 2.0)' },
      { lbl: '🔴 Deep-Loss',                 val: '−40% + ≥12h',       note: 'Tief im Minus UND noch ≥12h bis Anpfiff → Bankroll re-allokieren (loss_deep_pct 0.40)' },
      { lbl: '🔴 Sharps gegen uns',          val: 'Pinn ≥7pp < Entry', note: 'Pinnacle-Fair liegt ≥7pp UNTER unserem Entry-Preis → Sharps haben die Erwartung gesenkt, raus (sharp_against_gap_pp 7)' },
      { lbl: '🔴 Age-Loss',                  val: '−10% nach 36h',     note: 'Alte Verlustposition → Spread frisst sonst den Buchwert (age_loss_threshold_pct 0.10)' },
      { lbl: 'Pre-Match-Close (Hard)',       val: '≤ 0.67h (~40 Min)', note: '16.06.26 enger gestellt: kurz vor Anpfiff alle offenen Positionen schließen — vorher 6h, jetzt ~40 Min (pre_match_close_hours 0.67). NICHT in-play halten.' },
    ],
  },
};

function renderConfigSection(section) {
  const cfg = AUTO_TRADER_CONFIG[section];
  if (!cfg) return '';
  return `
    <div style="background:#0d1117;border:1px solid #30363d;border-radius:10px;padding:14px 16px;margin-bottom:10px">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
        <div style="font-size:11px;font-weight:700;color:#a78bfa;text-transform:uppercase;letter-spacing:.6px">${cfg.title}</div>
        ${cfg.enabled ? `<span style="font-size:9px;color:#8b949e;font-style:italic">${cfg.enabled}</span>` : ''}
      </div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:6px">
        ${cfg.rows.map(r => `
          <div style="display:flex;align-items:flex-start;gap:10px;padding:6px 0;border-bottom:1px dashed #21262d">
            <div style="flex:1;min-width:0">
              <div style="font-size:12px;color:#e6edf3;font-weight:600">${r.lbl}</div>
              <div style="font-size:10px;color:#8b949e;margin-top:2px;line-height:1.4">${r.note}</div>
            </div>
            <div style="font-size:13px;font-weight:800;color:#00d4a1;font-family:'SF Mono',Menlo,monospace;white-space:nowrap">${r.val}</div>
          </div>`).join('')}
      </div>
    </div>`;
}

function renderAutoTraderLiveStatus() {
  // Berechnungen aus localStorage / window-State
  const bets = (typeof _getPolyBets === 'function') ? _getPolyBets() : [];
  const today = new Date().toISOString().slice(0, 10);

  const todayBets    = bets.filter(b => (b.placedAt || '').slice(0, 10) === today);
  const todayStake   = todayBets.reduce((s, b) => s + (parseFloat(b.stake) || 0), 0);
  const openBets     = bets.filter(b => !b.resolved && b.result == null && !b.soldAt);
  const openExposure = openBets.reduce((s, b) => s + (parseFloat(b.stake) || 0), 0);
  const balance      = (typeof window._wmPolyBalance === 'object' && window._wmPolyBalance)
                       ? (parseFloat(window._wmPolyBalance.usdc) || 0)
                       : null;
  const adaptiveCap  = balance != null ? Math.min(50, balance * 0.40) : null;

  const fmtUsd = (v) => v == null ? '—' : '$' + v.toFixed(2);
  const ratio  = (cur, cap) => cap ? Math.min(100, Math.round(cur / cap * 100)) : 0;

  const status = [
    {
      lbl: 'Bets heute',
      val: `${todayBets.length} / 8`,
      bar: ratio(todayBets.length, 8),
      cls: todayBets.length >= 8 ? 'hot' : todayBets.length >= 6 ? 'warm' : 'ok',
    },
    {
      lbl: 'Stake heute',
      val: `${fmtUsd(todayStake)} / ${fmtUsd(adaptiveCap)}`,
      bar: ratio(todayStake, adaptiveCap),
      cls: adaptiveCap && todayStake >= adaptiveCap ? 'hot' : adaptiveCap && todayStake / adaptiveCap >= 0.75 ? 'warm' : 'ok',
    },
    {
      lbl: 'Open Exposure',
      val: `${fmtUsd(openExposure)} / $80`,
      bar: ratio(openExposure, 80),
      cls: openExposure >= 80 ? 'hot' : openExposure >= 60 ? 'warm' : 'ok',
    },
    {
      lbl: 'Verfügbare Balance',
      val: fmtUsd(balance),
      bar: balance != null ? Math.min(100, Math.round(balance / 200 * 100)) : 0,
      cls: balance == null || balance < 10 ? 'hot' : balance < 50 ? 'warm' : 'ok',
    },
  ];
  const clrMap = { hot: '#f85149', warm: '#e3b341', ok: '#3fb950' };

  return `
    <div style="background:#0d1117;border:1px solid #30363d;border-radius:10px;padding:14px 16px;margin-bottom:10px">
      <div style="font-size:11px;font-weight:700;color:#a78bfa;text-transform:uppercase;letter-spacing:.6px;margin-bottom:10px">Live-Status (aus localStorage)</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px">
        ${status.map(s => `
          <div>
            <div style="display:flex;justify-content:space-between;align-items:baseline;font-size:11px;margin-bottom:4px">
              <span style="color:#8b949e;font-weight:600;text-transform:uppercase;letter-spacing:.4px">${s.lbl}</span>
              <span style="color:${clrMap[s.cls]};font-weight:800;font-family:'SF Mono',Menlo,monospace">${s.val}</span>
            </div>
            <div style="height:5px;background:#21262d;border-radius:3px;overflow:hidden">
              <div style="height:100%;width:${s.bar}%;background:${clrMap[s.cls]};transition:width .3s"></div>
            </div>
          </div>`).join('')}
      </div>
    </div>`;
}

// ═══════════════════════════════════════════════════════════════
// Trading Cockpit — Live-Übersicht für Polymarket Auto-Trader
// ═══════════════════════════════════════════════════════════════
async function loadCockpitData() {
  // Holt vier JSON-Files parallel via raw.githubusercontent (kein CDN-Cache)
  const base = 'https://raw.githubusercontent.com/blummabet/Betting-Dashboard/main';
  const t = Date.now();
  const urls = [
    `${base}/wm_auto_bets_placed.json?t=${t}`,
    `${base}/wm_poly_balance.json?t=${t}`,
    `${base}/wm_kill_switch.json?t=${t}`,
    `${base}/wm_poly_prices.json?t=${t}`,
    `${base}/wm2026-data.json?t=${t}`,   // für Pinnacle-Odds-Frische (Edge-Basis)
    // 19.07.2026 — Maker-Register beider Live-Datensätze (WM läuft aus, MLS ist die Zukunft).
    `${base}/wm_poly_resting_orders.json?t=${t}`,
    `${base}/mls_poly_resting_orders.json?t=${t}`,
    // Markout: trägt Making, oder frisst Adverse Selection die Spread-Ersparnis?
    `${base}/wm_poly_markout.json?t=${t}`,
    `${base}/mls_poly_markout.json?t=${t}`,
  ];
  const fallbacks = [
    'wm_auto_bets_placed.json',
    'wm_poly_balance.json',
    'wm_kill_switch.json',
    'wm_poly_prices.json',
    'wm2026-data.json',
    'wm_poly_resting_orders.json',
    'mls_poly_resting_orders.json',
    'wm_poly_markout.json',
    'mls_poly_markout.json',
  ];
  const results = await Promise.all(urls.map(async (u, i) => {
    try {
      const r = await fetch(u, { cache: 'no-store' });
      if (r.ok) return r.json();
    } catch {}
    try {
      const r = await fetch(fallbacks[i] + '?t=' + t, { cache: 'no-store' });
      if (r.ok) return r.json();
    } catch {}
    return null;
  }));
  // Ruhende Maker-Orders beider Datensätze zusammenführen (nur die noch offenen interessieren).
  const _resting = [];
  for (const idx of [5, 6]) {
    const ro = (results[idx] && results[idx].orders) || [];
    for (const o of ro) if (o && o.status === 'resting') _resting.push(o);
  }
  return { placed: results[0], balance: results[1], kill: results[2], poly: results[3],
           data: results[4], resting: _resting,
           markout: { wm: results[7], mls: results[8] } };
}

// ── Maker-Register (19.07.2026) ──────────────────────────────────────────────
// Zeigt ruhende Limit-Orders, die auf einen Fill warten. Solange maker_enabled aus ist, gibt es
// keine → dann eine ruhige Erklärzeile statt eines leeren Kastens. Sobald aktiv, sieht Lucas hier
// live, was im Buch liegt und was der Lebenszyklus-Monitor kurz vor Anpfiff zu Taker eskaliert.
// Markout-Verdict-Zeile (19.07.2026, angestoßen von Lucas' Krypto-Markout): trägt Making, oder
// frisst Adverse Selection die Spread-Ersparnis? Das ist das ehrliche Tor für maker_enabled.
function _ptMarkoutLine(markout) {
  const m = markout || {};
  const parts = [];
  for (const [ds, rep] of [['MLS', m.mls], ['WM', m.wm]]) {
    if (!rep || rep.verdict == null) continue;
    const v = rep.verdict, net = rep.netMakerPP;
    const face = v === 'traegt' ? ['🟢', '#3fb950', 'trägt']
      : v === 'traegt_nicht' ? ['🔴', '#f85149', 'trägt NICHT']
      : v === 'grenzwertig' ? ['⚪', '#8b949e', 'grenzwertig']
      : ['⏳', '#8b949e', 'zu wenig Daten'];
    const netTxt = (net == null) ? '' : ` (netto ${net > 0 ? '+' : ''}${net}pp)`;
    parts.push(`<span style="color:${face[1]}">${face[0]} ${ds}: ${face[2]}${netTxt}</span>`);
  }
  if (!parts.length) return '';
  return `<div style="padding:8px 16px;background:rgba(167,139,250,.05);border-top:1px solid #21262d;font-size:11px;color:#8b949e;line-height:1.5">
    <b style="color:#a78bfa">Kann Making funktionieren?</b> Markout-Test (Adverse Selection vs. Spread-Ersparnis): ${parts.join(' · ')}.
    <span style="color:#6e7681"> Maker erst scharfschalten, wenn das dauerhaft 🟢 ist.</span></div>`;
}

function _ptRestingBlock(resting, markout) {
  const list = resting || [];
  const markoutLine = _ptMarkoutLine(markout);
  if (!list.length) {
    return `<div style="background:#0d1117;border:1px solid #30363d;border-radius:10px;overflow:hidden;margin-bottom:14px">
      <div style="padding:12px 16px">
        <div style="font-size:10px;font-weight:700;letter-spacing:.8px;color:#8b949e;text-transform:uppercase;margin-bottom:6px">🅼 Maker-Orders · ruhend</div>
        <div style="font-size:12px;color:#8b949e;line-height:1.5">Keine ruhenden Limit-Orders. Maker-Modus spart den Spread, indem Orders im Buch warten statt zu crossen — aktiv erst mit <code style="color:#a78bfa">maker_enabled</code>. Unerfüllte Orders werden kurz vor Anpfiff automatisch zu Taker eskaliert.</div>
      </div>${markoutLine}
    </div>`;
  }
  const fmtKo = iso => { const h = _polyHoursUntil(iso); return h == null ? '—' : (h < 0 ? 'angepfiffen' : h.toFixed(1) + 'h'); };
  const rows = list.slice(0, 12).map(o => {
    const h = _polyHoursUntil(o.kickoff);
    const near = (h != null && h <= 1.5);   // Eskalations-Fenster
    return `<tr style="border-top:1px solid #21262d">
      <td style="padding:7px 12px;font-size:12px;color:#e6edf3">${(o.matchKey || '—')}</td>
      <td style="padding:7px 12px;font-size:12px;color:#8b949e">${(o.market || '—')}</td>
      <td style="padding:7px 12px;text-align:right;font-size:12px;color:#a78bfa;font-weight:700">${o.price != null ? Math.round(o.price * 100) + '¢' : '—'}</td>
      <td style="padding:7px 12px;text-align:right;font-size:12px;color:${near ? '#e3b341' : '#8b949e'}">${fmtKo(o.kickoff)}${near ? ' ⚠️' : ''}</td>
    </tr>`;
  }).join('');
  return `<div style="background:#0d1117;border:1px solid #30363d;border-radius:10px;overflow:hidden;margin-bottom:14px">
    <div style="padding:10px 16px;border-bottom:1px solid #30363d;display:flex;justify-content:space-between;align-items:center">
      <span style="font-size:10px;font-weight:700;letter-spacing:.8px;color:#8b949e;text-transform:uppercase">🅼 Maker-Orders · ruhend</span>
      <span style="font-size:11px;color:#a78bfa;font-weight:800">${list.length} im Buch</span>
    </div>
    <table style="width:100%;border-collapse:collapse">
      <thead><tr style="background:rgba(255,255,255,.02)">
        <th style="padding:8px 12px;text-align:left;font-size:10px;color:#8b949e;text-transform:uppercase">Spiel</th>
        <th style="padding:8px 12px;text-align:left;font-size:10px;color:#8b949e;text-transform:uppercase">Markt</th>
        <th style="padding:8px 12px;text-align:right;font-size:10px;color:#8b949e;text-transform:uppercase">Preis</th>
        <th style="padding:8px 12px;text-align:right;font-size:10px;color:#8b949e;text-transform:uppercase">bis Anpfiff</th>
      </tr></thead><tbody>${rows}</tbody>
    </table>
  </div>`;
}

function _polyCurrentPrice(bet, polyData) {
  if (!polyData?.allFixtures) return null;
  const key = `${bet.homeId || ''}-${bet.awayId || ''}`;
  const fx = polyData.allFixtures.find(f => f.key === key);
  if (!fx) return null;
  // FIX 10.06.2026: Auto-Trader schreibt ENGLISCHE O/U-Labels ("Over/Under 2.5 Tore",
  // siehe EDGE_MARKET_MAP in auto_wm_poly_trigger.py). Die Map kannte nur die deutschen
  // ("Über/Unter") → O/U-Positionen fanden nie einen Live-Preis → P&L blieb $0.
  // Beide Varianten gemappt für Robustheit.
  const map = {
    'Heimsieg':'hw', 'Auswärtssieg':'aw', 'Unentschieden':'dr',
    'Over 2.5 Tore':'o25', 'Under 2.5 Tore':'u25',
    'Über 2.5 Tore':'o25', 'Unter 2.5 Tore':'u25',
  };
  const fld = map[bet.market];
  return fld ? fx[`poly_${fld}`] : null;
}

function _polyHoursSince(iso) {
  if (!iso) return null;
  try { return (Date.now() - new Date(iso).getTime()) / 3600000; } catch { return null; }
}

function _polyHoursUntil(iso) {
  if (!iso) return null;
  try { return (new Date(iso).getTime() - Date.now()) / 3600000; } catch { return null; }
}

function renderTradingCockpit(data) {
  const { placed, balance: bal, kill, poly, data: wmData } = (data || {});
  const bets = (placed?.bets) || [];
  const balanceUsd = parseFloat(bal?.usdc || 0);
  const killEnabled = (kill?.enabled !== false);
  const killReason = kill?.reason || '';

  const today = new Date().toISOString().slice(0, 10);

  // Heute
  const betsToday = bets.filter(b => (b.placedAt || '').slice(0, 10) === today);
  const stakeToday = betsToday.reduce((s, b) => s + (parseFloat(b.stake) || 0), 0);

  // Open Positions
  const openBets = bets.filter(b => !b.resolved && b.result == null && !b.soldAt);
  const openExposure = openBets.reduce((s, b) => s + (parseFloat(b.stake) || 0), 0);

  // Live P&L offene Positionen
  let openPnl = 0, openPnlCount = 0;
  for (const b of openBets) {
    const entry = parseFloat(b.polyPrice || 0);
    if (entry <= 0) continue;
    const cur = _polyCurrentPrice(b, poly);
    if (cur == null) continue;
    const stake = parseFloat(b.stake || 0);
    openPnl += (stake / entry) * cur - stake;
    openPnlCount++;
  }

  // 7-Tage Stats
  const cutoff7d = Date.now() - 7 * 86400000;
  const resolved7d = bets.filter(b => {
    if (!['WIN','LOSS','VOID'].includes(b.result)) return false;
    const ts = b.resolvedAt || b.placedAt || '';
    return ts && new Date(ts).getTime() > cutoff7d;
  });
  const wins7d = resolved7d.filter(b => b.result === 'WIN').length;
  const losses7d = resolved7d.filter(b => b.result === 'LOSS').length;
  const winRate7d = (wins7d + losses7d) > 0 ? Math.round(wins7d / (wins7d + losses7d) * 100) : null;
  const pnl7d = resolved7d.reduce((s, b) => s + (parseFloat(b.pnl) || 0), 0);
  const stake7d = resolved7d.reduce((s, b) => s + (parseFloat(b.stake) || 0), 0);
  const roi7d = stake7d > 0 ? (pnl7d / stake7d * 100) : null;

  // Caps
  const DAILY_BET_CAP = 8, MAX_OPEN_EXP = 80, ADAPTIVE_FRAC = 0.40, DAILY_STAKE_HARD = 50;
  const adaptiveCap = Math.min(DAILY_STAKE_HARD, balanceUsd * ADAPTIVE_FRAC);

  const fmtUsd = v => '$' + (v ?? 0).toFixed(2);
  const fmtPct = v => (v == null ? '—' : (v > 0 ? '+' : '') + v.toFixed(1) + '%');
  const pctOf = (cur, cap) => Math.min(100, cap > 0 ? Math.round(cur / cap * 100) : 0);

  // Last Trade
  const lastTrade = bets.length ? bets.slice().sort((a,b) => (b.placedAt || '').localeCompare(a.placedAt || ''))[0] : null;
  const lastTradeHrs = lastTrade ? _polyHoursSince(lastTrade.placedAt) : null;

  // ── Hero KPI Cards ──────────────────────────────────────────
  const heroKpis = [
    {
      label: 'Balance',
      value: fmtUsd(balanceUsd),
      sub: balanceUsd < 50 ? 'auflаden empfohlen' : `${(balanceUsd / 200 * 100).toFixed(0)}% von Ziel-Bankroll`,
      color: balanceUsd < 10 ? '#f85149' : balanceUsd < 50 ? '#e3b341' : '#00d4a1',
      icon: '💼',
    },
    {
      label: 'Open Exposure',
      value: fmtUsd(openExposure),
      sub: `${openBets.length} Pos. · ${openPnlCount > 0 ? `Live ${fmtPct(openExposure > 0 ? openPnl / openExposure * 100 : 0)}` : 'keine Live-Daten'}`,
      color: openExposure > MAX_OPEN_EXP * 0.85 ? '#f85149' : openExposure > MAX_OPEN_EXP * 0.5 ? '#e3b341' : '#a371f7',
      icon: '📈',
    },
    {
      label: 'P&L Heute',
      value: fmtUsd(openPnl),
      sub: openPnlCount > 0 ? `aus ${openPnlCount} live getrackten Positionen` : 'noch keine Live-Preise',
      color: openPnl > 0 ? '#00d4a1' : openPnl < 0 ? '#f85149' : '#8b949e',
      icon: openPnl >= 0 ? '🟢' : '🔴',
    },
    {
      label: 'Win-Rate 7d',
      value: winRate7d != null ? winRate7d + '%' : '—',
      sub: resolved7d.length > 0 ? `${wins7d}W / ${losses7d}L · ROI ${fmtPct(roi7d)}` : 'noch keine aufgelösten Bets',
      color: winRate7d == null ? '#8b949e' : winRate7d >= 60 ? '#00d4a1' : winRate7d >= 50 ? '#e3b341' : '#f85149',
      icon: '🎯',
    },
  ];

  const heroHtml = heroKpis.map(k => `
    <div style="background:#0d1117;border:1px solid #30363d;border-radius:12px;padding:16px 18px;display:flex;flex-direction:column;gap:8px">
      <div style="display:flex;align-items:center;justify-content:space-between">
        <span style="font-size:10px;color:#8b949e;text-transform:uppercase;letter-spacing:.8px;font-weight:700">${k.label}</span>
        <span style="font-size:14px">${k.icon}</span>
      </div>
      <div style="font-size:28px;font-weight:900;color:${k.color};line-height:1;font-family:'SF Mono',Menlo,monospace">${k.value}</div>
      <div style="font-size:11px;color:#8b949e">${k.sub}</div>
    </div>`).join('');

  // ── Cap-Bars (heutiger Stand) ──────────────────────────────
  const capBars = [
    { label: 'Bets heute', cur: betsToday.length, max: DAILY_BET_CAP, display: `${betsToday.length} / ${DAILY_BET_CAP}` },
    { label: 'Stake heute', cur: stakeToday, max: adaptiveCap, display: `${fmtUsd(stakeToday)} / ${fmtUsd(adaptiveCap)}` },
    { label: 'Open Exposure', cur: openExposure, max: MAX_OPEN_EXP, display: `${fmtUsd(openExposure)} / $${MAX_OPEN_EXP}` },
  ];

  const capHtml = capBars.map(b => {
    const pct = pctOf(b.cur, b.max);
    const clr = pct >= 90 ? '#f85149' : pct >= 70 ? '#e3b341' : '#00d4a1';
    return `
    <div>
      <div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:5px">
        <span style="color:#8b949e;font-weight:600;text-transform:uppercase;letter-spacing:.4px">${b.label}</span>
        <span style="color:${clr};font-weight:800;font-family:'SF Mono',Menlo,monospace">${b.display}</span>
      </div>
      <div style="height:6px;background:#21262d;border-radius:3px;overflow:hidden">
        <div style="height:100%;width:${pct}%;background:${clr};transition:width .3s"></div>
      </div>
    </div>`;
  }).join('');

  // ── Live Open Positions Tabelle ────────────────────────────
  let positionsHtml = `<div style="font-size:12px;color:#8b949e;font-style:italic;text-align:center;padding:14px">Keine offenen Positionen</div>`;
  if (openBets.length > 0) {
    const rows = openBets.slice().sort((a,b) => (b.placedAt || '').localeCompare(a.placedAt || '')).map(b => {
      const entry = parseFloat(b.polyPrice || 0);
      // 19.06.2026: echten Bid-Preis von manage_wm_poly_positions bevorzugen (b.currentPrice),
      // der deckt AH/BTTS ab (vorher „—", weil client-seitig kein Preis-Feld). Fallback =
      // gecachter Markt-Preis für Totals/1X2.
      const cur = (b.currentPrice != null) ? b.currentPrice : _polyCurrentPrice(b, poly);
      const stake = parseFloat(b.stake || 0);
      let pnl = null, pnlPct = null;
      if (cur != null && entry > 0) {
        pnl = (stake / entry) * cur - stake;
        pnlPct = pnl / stake * 100;
      }
      // FIX 19.06.2026 (Lucas): Anpfiff IMMER aus der echten UTC-Kickoff-Zeit, NICHT aus
      // b.matchDate (nur Datum → 00:00Z; bei Spätspielen einen Tag daneben → ECU-CUW „in 3.5h"
      // statt 27.5h, TUR-PRY „läuft" statt in 6.5h). Priorität: Record-kickoff → Fixture-Lookup
      // (_wmAllFixtures, autoritativ aus Gamma) → matchDate als letzter Fallback.
      const _fxKo = (_wmAllFixtures.find(f => f.key === `${b.homeId}-${b.awayId}`) || {}).kickoff;
      const hrsUntil = _polyHoursUntil(b.kickoff || _fxKo || b.matchDate);
      const matchStatus = hrsUntil != null ? (hrsUntil < 0 ? '🔴 läuft' : hrsUntil < 6 ? `⚠️ in ${hrsUntil.toFixed(1)}h` : `${hrsUntil.toFixed(1)}h`) : '—';
      const pnlColor = pnl == null ? '#8b949e' : pnl > 0.05 ? '#00d4a1' : pnl < -0.05 ? '#f85149' : '#e3b341';
      const slug = b.slug || '';
      const polyLink = slug ? `https://polymarket.com/sports/fifa-world-cup/${slug}` : '#';
      return `
      <tr style="border-bottom:1px solid #30363d">
        <td style="padding:8px 12px;font-size:12px;color:#e6edf3">${b.home || b.homeId} <span style="color:#8b949e">vs</span> ${b.away || b.awayId}</td>
        <td style="padding:8px 12px;font-size:11px;color:#8b949e">${b.market || '?'}</td>
        <td style="padding:8px 12px;font-size:11px;color:#e6edf3;font-family:'SF Mono',Menlo,monospace">${(entry * 100).toFixed(1)}¢</td>
        <td style="padding:8px 12px;font-size:11px;color:#e6edf3;font-family:'SF Mono',Menlo,monospace">${cur != null ? (cur * 100).toFixed(1) + '¢' : '—'}</td>
        <td style="padding:8px 12px;font-size:11px;color:${pnlColor};font-weight:700;font-family:'SF Mono',Menlo,monospace;text-align:right">${pnl != null ? fmtPct(pnlPct) : '—'}</td>
        <td style="padding:8px 12px;font-size:10px;color:#8b949e">${matchStatus}</td>
        <td style="padding:8px 12px;font-size:10px;white-space:nowrap">
          <a href="${polyLink}" target="_blank" style="color:#a371f7;text-decoration:none">🔗</a>
          <button onclick="_wmClosePosition('${(b.betKey || '').replace(/'/g, '')}','${((b.home||b.homeId)+' '+(b.market||'')).replace(/'/g,'')}')"
            title="Hab ich manuell auf Polymarket verkauft → als geschlossen markieren"
            style="margin-left:6px;background:#21262d;border:1px solid #30363d;border-radius:5px;color:#8b949e;font-size:10px;padding:2px 7px;cursor:pointer;font-family:inherit">🔒 geschl.</button>
        </td>
      </tr>`;
    }).join('');
    positionsHtml = `
    <table style="width:100%;border-collapse:collapse">
      <thead><tr style="background:#1c2128">
        <th style="padding:8px 12px;text-align:left;font-size:9px;color:#8b949e;font-weight:700;text-transform:uppercase;letter-spacing:.5px">Match</th>
        <th style="padding:8px 12px;text-align:left;font-size:9px;color:#8b949e;font-weight:700;text-transform:uppercase;letter-spacing:.5px">Markt</th>
        <th style="padding:8px 12px;text-align:left;font-size:9px;color:#8b949e;font-weight:700;text-transform:uppercase;letter-spacing:.5px">Entry</th>
        <th style="padding:8px 12px;text-align:left;font-size:9px;color:#8b949e;font-weight:700;text-transform:uppercase;letter-spacing:.5px">Aktuell</th>
        <th style="padding:8px 12px;text-align:right;font-size:9px;color:#8b949e;font-weight:700;text-transform:uppercase;letter-spacing:.5px">P&amp;L</th>
        <th style="padding:8px 12px;text-align:left;font-size:9px;color:#8b949e;font-weight:700;text-transform:uppercase;letter-spacing:.5px">Anpfiff</th>
        <th style="padding:8px 12px;font-size:9px"></th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
  }

  // ── System-Health ──────────────────────────────────────────
  const killHtml = killEnabled
    ? `<span style="color:#00d4a1;font-weight:800">🟢 ACTIVE</span>`
    : `<span style="color:#f85149;font-weight:800">🛑 PAUSED</span><div style="font-size:10px;color:#8b949e;margin-top:2px">${killReason}</div>`;
  const balanceTs = bal?.updatedAt || bal?.ts || '—';
  const balanceFresh = balanceTs !== '—' ? (() => { try { const h = _polyHoursSince(balanceTs); return h != null ? h.toFixed(1) + 'h alt' : balanceTs; } catch { return balanceTs; } })() : '—';
  const lastTradeHtml = lastTrade ? `${lastTrade.home || lastTrade.homeId} vs ${lastTrade.away || lastTrade.awayId} · vor ${lastTradeHrs != null ? lastTradeHrs.toFixed(1) + 'h' : '—'}` : 'noch keine Trades';

  // ── Final Cockpit-Layout ───────────────────────────────────
  return `
  <div style="background:linear-gradient(135deg,#161b22 0%,#161b22 50%,#1c2128 100%);border:1px solid rgba(0,212,161,.18);border-radius:14px;padding:18px 20px;margin-bottom:16px">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
      <div>
        <div style="font-size:11px;font-weight:800;letter-spacing:1.5px;color:#00d4a1;text-transform:uppercase">🎮 Trading Cockpit</div>
        <div style="font-size:10px;color:#8b949e;margin-top:2px">Live aus GitHub</div>
        ${(() => {
          // FIX 11.06.2026: ECHTE Daten-Frische statt "zuletzt geladen" (= nur Ladezeit).
          // Poly-Trade-Edge = Pinnacle-fair vs Poly-Preis → BEIDE müssen frisch sein.
          // Rot + STALE ab 24h = exakt die Schwelle, ab der der Stale-Odds-Breaker
          // den Auto-Trade stoppt. So sieht man sofort ob "nichts zu traden" =
          // "ok, kein Edge" oder "Achtung, alte Daten".
          const _parseDe = s => {
            const m = (s || '').match(/(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}):(\d{2})/);
            return m ? Date.UTC(+m[3], +m[2]-1, +m[1], +m[4], +m[5]) : null;
          };
          const now = Date.now();
          const polyTs = _parseDe(poly && poly.generatedAt);
          const polyH = polyTs ? (now - polyTs) / 3600000 : null;
          let pinnTs = 0;
          for (const v of Object.values((wmData && wmData.odds) || {})) {
            if (v && v.updatedAt) { const t = new Date(v.updatedAt).getTime(); if (!isNaN(t) && t > pinnTs) pinnTs = t; }
          }
          const pinnH = pinnTs ? (now - pinnTs) / 3600000 : null;
          const fmt = h => h == null ? '?' : h < 1 ? '<1h' : h < 24 ? Math.round(h) + 'h' : Math.floor(h/24) + 'd';
          const worst = Math.max(polyH || 0, pinnH || 0);
          const col = worst < 6 ? '#00d4a1' : worst < 24 ? '#e3b341' : '#f85149';
          const stale = (pinnH != null && pinnH >= 24) || (polyH != null && polyH >= 24);
          return `<div style="margin-top:6px;font-size:11px;font-weight:700;display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
            <span style="color:${col};background:rgba(0,0,0,0.25);border:1px solid ${col}66;border-radius:5px;padding:2px 8px;">📊 Poly-Preise: ${fmt(polyH)} alt</span>
            <span style="color:${col};background:rgba(0,0,0,0.25);border:1px solid ${col}66;border-radius:5px;padding:2px 8px;">🎲 Pinnacle-Odds: ${fmt(pinnH)} alt</span>
            ${stale ? '<span style="color:#f85149;font-weight:800;">⚠️ STALE — Auto-Trade pausiert (Breaker greift)</span>' : '<span style="color:#00d4a1;">✓ Daten frisch</span>'}
          </div>`;
        })()}
      </div>
      <button onclick="refreshCockpit()" style="background:rgba(0,212,161,.1);border:1px solid rgba(0,212,161,.3);color:#00d4a1;border-radius:8px;padding:6px 14px;font-size:11px;font-weight:700;cursor:pointer;font-family:inherit">↻ Refresh</button>
    </div>

    <!-- Hero KPI 4-Grid -->
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-bottom:18px">
      ${heroHtml}
    </div>

    <!-- Cap-Status Bars -->
    <div style="background:#0d1117;border:1px solid #30363d;border-radius:10px;padding:14px 16px;margin-bottom:14px">
      <div style="font-size:10px;font-weight:700;letter-spacing:.8px;color:#8b949e;text-transform:uppercase;margin-bottom:12px">Live Cap-Status</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px">
        ${capHtml}
      </div>
    </div>

    <!-- Open Positions Tabelle -->
    <div style="background:#0d1117;border:1px solid #30363d;border-radius:10px;overflow:hidden;margin-bottom:14px">
      <div style="padding:10px 16px;border-bottom:1px solid #30363d;display:flex;align-items:center;justify-content:space-between">
        <span style="font-size:10px;font-weight:700;letter-spacing:.8px;color:#8b949e;text-transform:uppercase">📊 Offene Positionen · Live</span>
        <span style="font-size:11px;color:${openPnl >= 0 ? '#00d4a1' : '#f85149'};font-weight:800;font-family:'SF Mono',Menlo,monospace">${openBets.length > 0 ? `${openBets.length} · ${fmtUsd(openPnl)}` : '0'}</span>
      </div>
      ${positionsHtml}
    </div>

    ${_ptRestingBlock(data && data.resting, data && data.markout)}

    <!-- System-Health Footer -->
    <div style="background:#0d1117;border:1px solid #30363d;border-radius:10px;padding:12px 16px;display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:14px;font-size:11px">
      <div>
        <div style="font-size:9px;color:#8b949e;font-weight:700;letter-spacing:.8px;text-transform:uppercase;margin-bottom:4px">Trading Status</div>
        ${killHtml}
      </div>
      <div>
        <div style="font-size:9px;color:#8b949e;font-weight:700;letter-spacing:.8px;text-transform:uppercase;margin-bottom:4px">Balance gefetcht</div>
        <div style="color:#e6edf3">${balanceFresh}</div>
      </div>
      <div>
        <div style="font-size:9px;color:#8b949e;font-weight:700;letter-spacing:.8px;text-transform:uppercase;margin-bottom:4px">Letzter Trade</div>
        <div style="color:#e6edf3">${lastTradeHtml}</div>
      </div>
      <div>
        <div style="font-size:9px;color:#8b949e;font-weight:700;letter-spacing:.8px;text-transform:uppercase;margin-bottom:4px">Aktionen</div>
        <a href="https://github.com/blummabet/Betting-Dashboard/actions/workflows/kill-switch.yml" target="_blank" style="color:#f85149;text-decoration:none;font-weight:700">🛑 Kill-Switch</a>
        &nbsp;·&nbsp;
        <a href="https://github.com/blummabet/Betting-Dashboard/actions/workflows/daily-heartbeat.yml" target="_blank" style="color:#a371f7;text-decoration:none;font-weight:700">🤖 Heartbeat</a>
      </div>
    </div>
  </div>`;
}

async function refreshCockpit() {
  const el = document.getElementById('tradingCockpit');
  if (!el) return;
  el.innerHTML = `<div style="text-align:center;padding:30px;color:#8b949e">⚙️ Lade Cockpit-Daten…</div>`;
  const data = await loadCockpitData();
  el.innerHTML = renderTradingCockpit(data);
}

function renderAutoTraderConfig() {
  return `
    <details style="background:#161b22;border:1px solid #30363d;border-radius:12px;padding:14px 18px;margin-bottom:16px" open>
      <summary style="cursor:pointer;font-size:14px;font-weight:800;color:#e6edf3;outline:none;list-style:none;display:flex;align-items:center;justify-content:space-between">
        <span>🤖 Auto-Trader · Config &amp; Live-Status</span>
        <span style="font-size:11px;color:#8b949e;font-weight:600">▾ ein-/ausklappen</span>
      </summary>
      <div style="margin-top:14px">
        ${renderAutoTraderLiveStatus()}
        ${renderConfigSection('trigger')}
        ${renderConfigSection('stake')}
        ${renderConfigSection('sell')}
        <div style="font-size:10px;color:#8b949e;font-style:italic;margin-top:10px;text-align:right">
          Stand 01.06.2026 · bei Code-Änderung in auto_wm_poly_trigger.py / manage_wm_poly_positions.py auch hier nachziehen
        </div>
      </div>
    </details>`;
}

// ── Performance-Sektion (Server-Daten, 11.06.2026 neu gebaut) ───────────────
// Vorher: localStorage 'betedge_poly_bets' + picks_history.json (frühe Manual-
// Tracking-Version, Resultate 'won'/'lost', €). Jetzt autoritativ aus
// wm_results.json (P&L/CLV/WIN-LOSS, resolve_wm_results.py) + wm_auto_bets_
// placed.json (Auto-Trader) + wm_poly_balance.json — dieselbe Quelle wie
// Status-Tab & Trading-Cockpit. Keine Karteileiche mehr.
let _polyStatsCache = null;
let _polyStatsLoading = false;

// 12.07.2026 (Lucas: „MLS ist auf Polymarket da" — MLS-Bets müssen hier auftauchen).
// Die Betting-Seite bleibt bewusst TAGESWEISE mit ALLEN Ligen gemeinsam (kein Umschalter,
// Lucas: „das stört mich nicht") → wir MERGEN die Datensätze statt zu wechseln.
// Neue Liga dazu = eine Zeile in dieser Liste.
const _POLY_BET_DATASETS = [
  { results: 'wm_results.json',   placed: 'wm_auto_bets_placed.json',   bal: 'wm_poly_balance.json'   },
  { results: 'mls_results.json',  placed: 'mls_auto_bets_placed.json',  bal: 'mls_poly_balance.json'  },
  { results: 'liga_results.json', placed: 'liga_auto_bets_placed.json', bal: 'liga_poly_balance.json' },
];

const _pbFetch = (f) => fetch(f + '?t=' + Date.now())
  .then(r => r.ok ? r.json() : null).catch(() => null);

async function _loadPolyStatsData() {
  if (_polyStatsLoading) return;
  _polyStatsLoading = true;
  try {
    const per = await Promise.all(_POLY_BET_DATASETS.map(async d => ({
      res:    await _pbFetch(d.results),
      placed: await _pbFetch(d.placed),
      bal:    await _pbFetch(d.bal),
    })));
    // Bets aller Datensätze zusammenführen. Die KPIs (Trefferquote/P&L/Einsatz) werden in
    // _polyStatsHtml lokal aus res.bets gerechnet → simples Concat reicht, keine Summary-Mathe.
    const bets = [], placedBets = [];
    let bal = null, summary = null;
    for (const p of per) {
      if (p.res && Array.isArray(p.res.bets)) bets.push(...p.res.bets);
      if (p.res && p.res.summary && !summary) summary = p.res.summary;
      if (p.placed && Array.isArray(p.placed.bets)) placedBets.push(...p.placed.bets);
      // Balance = dieselbe Polymarket-Wallet über alle Datensätze → erste vorhandene nehmen.
      if (!bal && p.bal) bal = p.bal;
    }
    _polyStatsCache = { res: { bets, summary }, placed: { bets: placedBets }, bal };
    const el = document.getElementById('polyStatsSection');
    if (el) el.innerHTML = _polyStatsHtml(_polyStatsCache);
  } finally { _polyStatsLoading = false; }
}

function renderPolyStats() {
  _loadPolyStatsData();   // Hintergrund-Refresh; füllt #polyStatsSection wenn fertig
  return _polyStatsCache
    ? _polyStatsHtml(_polyStatsCache)
    : `<div style="background:#161b22;border:1px solid #30363d;border-radius:10px;padding:30px;text-align:center;color:#8b949e">⏳ Performance lädt…</div>`;
}

function _polyStatsHtml(c) {
  const res = c.res || {};
  const s = res.summary || {};
  const allRows = Array.isArray(res.bets) ? res.bets : [];
  // FIX 14.06.2026: Die Betting-Seite zeigt NUR manuell getriggerte Wetten
  // (polymarket_bet.py-Terminal / ✏️ Position loggen → source='manual'). Auto-Trader-
  // Trades (source='auto'/'auto_steam', inkl. Legacy-Einträge ohne source → default auto)
  // gehören aufs Trading-Cockpit, nicht hierher. Kennzahlen werden lokal aus dem manuellen
  // Subset gerechnet — die Server-summary aggregiert auto+manuell und wäre sonst falsch.
  const _isAutoSrc = b => { const sc = b.source || 'auto'; return sc === 'auto' || sc === 'auto_steam'; };
  const allBets   = allRows.filter(b => !_isAutoSrc(b));
  const autoCount = allRows.length - allBets.length;
  const placedArr = (c.placed && Array.isArray(c.placed.bets)) ? c.placed.bets.filter(b => !_isAutoSrc(b)) : [];
  const balUsdc = c.bal ? (c.bal.total != null ? c.bal.total : (c.bal.usdc != null ? c.bal.usdc : null)) : null;

  const resolved = allBets.filter(b => ['WIN','LOSS','VOID'].includes(b.result)).length;
  const wins   = allBets.filter(b => b.result === 'WIN').length;
  const losses = allBets.filter(b => b.result === 'LOSS').length;
  const pending= allBets.filter(b => !b.result || b.result === 'PENDING').length;
  const decided = wins + losses;
  const winRate = decided > 0 ? (wins / decided) * 100 : null;
  const totalPnl = allBets.reduce((a, b) => a + (+b.pnl || 0), 0);
  const staked = allBets.reduce((a, b) => a + (+b.stake || 0), 0);
  const roi = staked > 0 ? (totalPnl / staked) * 100 : null;
  const total = allBets.length;
  const _clvs = allBets.map(b => (typeof b.clv === 'number' ? b.clv : (typeof b.clvPp === 'number' ? b.clvPp : null))).filter(v => v != null);
  const avgClv = _clvs.length ? _clvs.reduce((a, v) => a + v, 0) / _clvs.length : null;

  const card = (label, value, sub, color) => `
    <div style="background:#161b22;border:1px solid #30363d;border-radius:10px;padding:14px 16px">
      <div style="font-size:10px;color:#8b949e;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px;font-weight:700">${label}</div>
      <div style="font-size:24px;font-weight:800;color:${color};line-height:1.1">${value}</div>
      <div style="font-size:11px;color:#8b949e;margin-top:4px">${sub}</div>
    </div>`;

  const pnlColor = totalPnl > 0 ? '#3fb950' : totalPnl < 0 ? '#f85149' : '#8b949e';
  const wrColor = winRate == null ? '#8b949e' : winRate >= 50 ? '#3fb950' : '#f85149';
  const cards = [
    card('Bilanz', resolved > 0 ? `${wins}W / ${losses}L` : '—',
         winRate != null ? `Trefferquote ${Math.round(winRate)}%` : `${pending} offen · 0 aufgelöst`, wrColor),
    card('P&L', `${totalPnl >= 0 ? '+' : ''}$${totalPnl.toFixed(2)}`,
         roi != null ? `ROI ${roi >= 0 ? '+' : ''}${roi.toFixed(1)}%` : 'noch offen', pnlColor),
    card('Einsatz', `$${staked.toFixed(2)}`,
         `${total} Bets · Ø $${total > 0 ? (staked / total).toFixed(2) : '0.00'}`, '#e6edf3'),
    card('Ø CLV', avgClv != null ? `${avgClv >= 0 ? '+' : ''}${avgClv.toFixed(1)}pp` : '—',
         'Closing Line Value', avgClv == null ? '#8b949e' : avgClv >= 0 ? '#3fb950' : '#f85149'),
    card('Balance', balUsdc != null ? `$${balUsdc.toFixed(2)}` : '—', 'USDC im Wallet',
         balUsdc == null ? '#8b949e' : balUsdc >= 50 ? '#3fb950' : '#e3b341'),
  ];

  const recent = [...allBets].sort((a, b) => (b.placedAt || '').localeCompare(a.placedAt || '')).slice(0, 15);
  const rows = recent.length === 0
    ? `<tr><td colspan="6" style="text-align:center;color:#8b949e;padding:28px;font-size:13px">Noch keine manuell getriggerten Wetten — platziere über „✏️ Position loggen" oder <code style="color:#a78bfa">polymarket_bet.py</code></td></tr>`
    : recent.map(b => {
        const r = b.result;
        const resIcon = r === 'WIN' ? '✅' : r === 'LOSS' ? '❌' : r === 'VOID' ? '➖' : '⏳';
        const resColor = r === 'WIN' ? '#3fb950' : r === 'LOSS' ? '#f85149' : '#8b949e';
        const dt = (b.placedAt || '').slice(0, 10).split('-').reverse().join('.');
        const pricePct = b.polyPrice ? `${Math.round(b.polyPrice * 100)}¢` : '—';
        const isAuto = b.source === 'auto';
        const src = isAuto
          ? '<span style="background:rgba(63,185,80,.12);border:1px solid rgba(63,185,80,.4);color:#3fb950;font-size:10px;font-weight:700;padding:2px 8px;border-radius:5px;white-space:nowrap" title="Vom Auto-Trader gesetzt">🤖 Auto</span>'
          : '<span style="background:rgba(227,179,65,.12);border:1px solid rgba(227,179,65,.4);color:#e3b341;font-size:10px;font-weight:700;padding:2px 8px;border-radius:5px;white-space:nowrap" title="Manuell gesetzt">✋ Manuell</span>';
        const pnlStr = (r && r !== 'PENDING') ? ` <span style="color:${resColor};font-size:11px">${(+b.pnl >= 0 ? '+' : '')}$${(+b.pnl || 0).toFixed(2)}</span>` : '';
        return `<tr style="border-bottom:1px solid #30363d">
          <td style="padding:9px 12px;font-size:11px;color:#8b949e">${dt}</td>
          <td style="padding:9px 12px;font-size:12px">${b.home} vs ${b.away}</td>
          <td style="padding:9px 12px;font-size:12px;color:${_marketColor(b.market)}">${b.market}</td>
          <td style="padding:9px 12px;font-size:12px;color:#a78bfa">${pricePct}</td>
          <td style="padding:9px 12px;font-size:14px;text-align:center">${src}</td>
          <td style="padding:9px 12px;color:${resColor};font-weight:700;white-space:nowrap">${resIcon}${pnlStr}</td>
        </tr>`;
      }).join('');

  const upd = res.updatedAt ? new Date(res.updatedAt).toLocaleString('de-AT', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—';

  return `
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;flex-wrap:wrap">
      <span style="font-size:11px;color:#8b949e">Nur <strong style="color:#e3b341">manuell getriggerte</strong> Wetten · Server-getrackt (resolve_wm_results) · Stand ${upd}</span>
      <span style="margin-left:auto;font-size:11px;color:#8b949e">✋ ${total} Manuell · ${pending} offen${autoCount > 0 ? ` · <span title="Auto-Trader-Trades — sichtbar im Trading-Cockpit, hier ausgeblendet">🤖 ${autoCount} Auto ausgeblendet</span>` : ''}</span>
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:16px">
      ${cards.join('')}
    </div>
    <div style="background:#161b22;border:1px solid #30363d;border-radius:10px;overflow:hidden">
      <div style="padding:12px 16px;border-bottom:1px solid #30363d;display:flex;align-items:center;justify-content:space-between">
        <span style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:#8b949e">Letzte Bets</span>
        <div style="display:flex;gap:6px;align-items:center">
          <span style="font-size:10px;color:#8b949e">Auflösung automatisch per Cron</span>
          <button onclick="_polyStatsCache=null;document.getElementById('polyStatsSection').innerHTML=renderPolyStats()" style="background:none;border:1px solid #30363d;border-radius:6px;color:#8b949e;font-size:11px;font-weight:600;padding:4px 10px;cursor:pointer;font-family:inherit">🔄 Aktualisieren</button>
        </div>
      </div>
      <table style="width:100%;border-collapse:collapse">
        <thead style="background:#1c2128">
          <tr>
            <th style="padding:8px 12px;text-align:left;font-size:9px;color:#8b949e;font-weight:700;text-transform:uppercase;letter-spacing:.5px">Datum</th>
            <th style="padding:8px 12px;text-align:left;font-size:9px;color:#8b949e;font-weight:700;text-transform:uppercase;letter-spacing:.5px">Spiel</th>
            <th style="padding:8px 12px;text-align:left;font-size:9px;color:#8b949e;font-weight:700;text-transform:uppercase;letter-spacing:.5px">Markt</th>
            <th style="padding:8px 12px;text-align:left;font-size:9px;color:#8b949e;font-weight:700;text-transform:uppercase;letter-spacing:.5px">Preis</th>
            <th style="padding:8px 12px;text-align:center;font-size:9px;color:#8b949e;font-weight:700;text-transform:uppercase;letter-spacing:.5px">Typ</th>
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

// ── Datensatz aus der Liga ableiten (18.07.2026) ────────────────────────────────────────────
// 🔴 GELD-BUG: Der Dispatch sendete nur `{ orders }`. poly-bets.yml liest aber
// `client_payload.dataset` und fällt OHNE Angabe auf 'wm' zurück — eine MLS- oder Liga-Wette
// wäre also als WM-Wette platziert und in wm_auto_bets_placed.json geschrieben worden
// (falscher Datensatz in P&L, CLV und Lern-Loop). Seit der Betting-Tab alle Datensätze mergt,
// ist das der Normalfall, nicht der Sonderfall.
const _POLY_LIGA_CODES = ['ENG', 'ESP', 'GER', 'ITA', 'FRA'];

function _polyDatasetForLeague(league) {
  const L = String(league || '').toUpperCase();
  if (L === 'MLS') return { dataset: 'mls', profile: 'mls_default' };
  if (_POLY_LIGA_CODES.includes(L)) return { dataset: 'liga', profile: 'liga_default' };
  return { dataset: 'wm', profile: 'wm2026' };   // WM-Gruppen (A–L) + KO
}

async function _callGitHubDispatch(orders) {
  const pat = _getGithubPAT();
  if (!pat) {
    polyOpenSettings();
    return false;
  }

  // Nach Datensatz gruppieren: ein gemischter Batch (z.B. MLS + Liga) darf NICHT in einem
  // einzigen Lauf landen — sonst schreibt der Workflow alles in dieselbe Datei.
  const gruppen = {};
  for (const o of (orders || [])) {
    const { dataset, profile } = _polyDatasetForLeague(o.league);
    (gruppen[dataset] = gruppen[dataset] || { profile, orders: [] }).orders.push(o);
  }

  let alleOk = true;
  for (const [dataset, grp] of Object.entries(gruppen)) {
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
        client_payload: { orders: grp.orders, dataset, profile: grp.profile },
      }),
    });
    if (!(resp.ok || resp.status === 204)) alleOk = false;
  }
  return alleOk;
}

// 23.06.2026 (Lucas): Position manuell als geschlossen markieren (hab direkt auf Polymarket
// verkauft). Löst close-poly-position aus → reconcile_poly_positions.py --close=<betKey> liest
// den echten Sell-Trade, setzt status=closed_manual + realisierten P&L, stoppt die Sell-Alerts.
async function _wmClosePosition(betKey, label) {
  if (!betKey) { _polyToast('❌ Kein betKey — Position nicht identifizierbar'); return; }
  const pat = _getGithubPAT();
  if (!pat) { polyOpenSettings(); return; }
  if (!window.confirm(`Position als manuell geschlossen markieren?\n\n${label || betKey}\n\n` +
      `Das System liest deinen echten Verkaufs-Trade von Polymarket, bucht den realisierten ` +
      `P&L und stoppt die Sell-Alerts. (Du hast bereits auf Polymarket verkauft.)`)) return;
  try {
    const resp = await fetch(`https://api.github.com/repos/${POLY_GITHUB_REPO}/dispatches`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${pat}`,
        'Accept': 'application/vnd.github+json',
        'Content-Type': 'application/json',
        'X-GitHub-Api-Version': '2022-11-28',
      },
      body: JSON.stringify({ event_type: 'close-poly-position', client_payload: { betKey } }),
    });
    if (resp.ok || resp.status === 204) {
      _polyToast('🔒 Schließung ausgelöst — Runner bucht den Verkauf in ~1 Min');
    } else {
      _polyToast('❌ Dispatch fehlgeschlagen — PAT prüfen');
    }
  } catch (e) {
    _polyToast('🔒 Schließung ausgelöst (Antwort unklar — in 1 Min prüfen)');
  }
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
    _polyState.dateStr = '';              // '' = alle Tage (Default seit 18.07.2026)
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

  // 18.07.2026: Default ist ALLE Tage ('') statt heute. Der Tab zeigte sonst an einem
  // spielfreien Tag „keine Picks", obwohl für übermorgen welche dastanden. null = noch
  // nie gewählt → '' ; ein bewusst gewähltes '' bleibt '' (deshalb kein `||`).
  const dateStr = _polyState.dateStr == null ? '' : _polyState.dateStr;
  _polyState.dateStr  = dateStr;
  _polyState.picks    = _collectAllPolyPicks(dateStr);   // WM + Liga/MLS + Club (nicht nur Club)
  _polyState.prices   = {};
  _polyState.selected = new Set(_polyState.picks.map(p => p.id)); // start: all selected

  // ── WM 2026 Picks async dazuladen ───────────────────────────────────────
  // Falls window.WM2026_DATA noch nicht gesetzt (User hat WM-Tab noch nie geöffnet),
  // fetchen wir wm2026-data.json einmalig in den Background-Cache. Sobald geladen
  // re-rendert das Grid mit den WM-Picks zusätzlich zu den National-Picks.
  if (!window.WM2026_DATA && !window._wmDataCache) {
    _loadWmDataAsync().then(() => {
      if (window._wmDataCache) {
        _polyState.picks = _collectAllPolyPicks(_polyState.dateStr || dateStr);
        _polyState.selected = new Set(_polyState.picks.map(p => p.id));
        const grid = document.getElementById('polyPickGrid');
        if (grid) grid.innerHTML = renderPolyPickCards();
        const stats = document.getElementById('polyStatsSection');
        if (stats) stats.innerHTML = renderPolyStats();
      }
    });
  }

  // ── Liga/MLS-Picks async dazuladen (25.07.2026, Lucas: „seh nichts im Betting-Tab") ──────
  // Der Tab war nie an den Liga/MLS-Datensatz angeschlossen. Damit er nicht davon abhängt, dass
  // der National-Tab vorher geöffnet wurde, holen wir mls-data.json (+ liga-data.json) selbst und
  // bauen NATIONAL_PICKS_FOR_POLY im selben Format wie wm2026-renderer.js.
  if (!window.NATIONAL_PICKS_FOR_POLY) {
    _loadNationalPolyPicksAsync().then(() => {
      _polyState.picks = _collectAllPolyPicks(_polyState.dateStr || dateStr);
      _polyState.selected = new Set(_polyState.picks.map(p => p.id));
      const grid = document.getElementById('polyPickGrid');
      if (grid) grid.innerHTML = renderPolyPickCards();
      const chips = document.getElementById('polyDateChips');
      if (chips) chips.outerHTML = _renderPolyDateChips(_polyState.dateStr || '');
    });
  }

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
        <div id="polyDateSub" style="font-size:12px;color:#8b949e;margin-top:3px">${dateStr || 'Alle Tage'} &nbsp;·&nbsp; ${n} eligible pick${n !== 1 ? 's' : ''}</div>
      </div>
      <div style="margin-left:auto;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        ${_renderPolyDateChips(dateStr)}
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

    <!-- ── Trading-Konzept-Block entfernt 09.06.2026 ───────────────────── -->

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

// ═══════════════════════════════════════════════════════════════════
//  POSITION-HEALTH-MONITOR
//  Lädt position_health.json und rendert Status-Cards für offene Trades
// ═══════════════════════════════════════════════════════════════════
window.loadPositionHealth = async function () {
  const block = document.getElementById('positionHealthBlock');
  if (!block) return;
  try {
    const ts = Date.now();
    // M2 Fix 05.06.2026 — POLY_GITHUB_REPO statt hardcoded blummabet-URL
    // (verhindert kaputten Fetch wenn Repo umbenannt oder Fork verwendet wird)
    const repo = (typeof POLY_GITHUB_REPO !== 'undefined' && POLY_GITHUB_REPO)
      ? POLY_GITHUB_REPO
      : 'blummabet/Betting-Dashboard';
    let raw = `https://raw.githubusercontent.com/${repo}/main/position_health.json?t=${ts}`;
    let res = await fetch(raw).catch(() => null);
    if (!res || !res.ok) {
      res = await fetch(`position_health.json?t=${ts}`, { cache: 'no-store' }).catch(() => null);
    }
    if (!res || !res.ok) {
      block.innerHTML = renderHealthPlaceholder('Position-Health-Daten nicht verfügbar');
      return;
    }
    const data = await res.json();
    block.innerHTML = renderPositionHealth(data);
  } catch (e) {
    block.innerHTML = renderHealthPlaceholder('Fehler beim Laden: ' + e.message);
  }
};

function renderHealthPlaceholder(msg) {
  return `<div style="background:#161b22;border:1px solid #30363d;border-radius:14px;padding:14px;margin-bottom:14px;color:#8b949e;font-size:12px;text-align:center;">🩺 ${msg}</div>`;
}

function renderPositionHealth(data) {
  const positions = (data && data.positions) || [];
  const lastRun = data && data.lastRun;
  if (!positions.length) {
    return `<div class="ph-empty">
      <div class="ph-empty-icon">🩺</div>
      <div class="ph-empty-title">Position-Health-Monitor</div>
      <div class="ph-empty-text">Aktuell keine offenen Polymarket-Positionen. Bei ersten Trades zeigt dieser Block je Position einen Health-Score (0-100) basierend auf Edge-Persistenz, Pinnacle-Drift, CLV und Time-Pressure.</div>
      ${lastRun ? `<div class="ph-empty-time">Letzter Check: ${_phFmtTime(lastRun)}</div>` : ''}
    </div>`;
  }

  // Sort by score asc (kritischste zuerst)
  positions.sort((a, b) => (a.score || 0) - (b.score || 0));

  // Summary-Stats
  const counts = { ok: 0, watch: 0, warning: 0, critical: 0 };
  for (const p of positions) counts[p.status] = (counts[p.status] || 0) + 1;

  const cards = positions.map(p => _phCard(p)).join('');

  return `
    <div class="ph-wrap">
      <div class="ph-header">
        <div class="ph-header-left">
          <span class="ph-header-icon">🩺</span>
          <span class="ph-header-title">Position-Health-Monitor</span>
          <span class="ph-header-count">${positions.length} offene Position${positions.length === 1 ? '' : 'en'}</span>
        </div>
        <div class="ph-header-right">
          ${counts.critical ? `<span class="ph-chip ph-chip-critical">🔴 ${counts.critical}</span>` : ''}
          ${counts.warning  ? `<span class="ph-chip ph-chip-warning">🟠 ${counts.warning}</span>` : ''}
          ${counts.watch    ? `<span class="ph-chip ph-chip-watch">🟡 ${counts.watch}</span>` : ''}
          ${counts.ok       ? `<span class="ph-chip ph-chip-ok">🟢 ${counts.ok}</span>` : ''}
          <span class="ph-header-time">${lastRun ? _phFmtTime(lastRun) : ''}</span>
        </div>
      </div>
      <div class="ph-cards">${cards}</div>
    </div>
  `;
}

function _phCard(p) {
  const statusClass = `ph-status-${p.status}`;
  const score = Math.round(p.score || 0);
  const factors = (p.factors || []).map(f => {
    const fScore = Math.round(f.score || 0);
    const fEmoji = fScore >= 80 ? '✅' : fScore >= 60 ? '🟡' : fScore >= 40 ? '🟠' : '🔴';
    return `<div class="ph-factor"><span class="ph-factor-emoji">${fEmoji}</span><span class="ph-factor-name">${f.name}</span><span class="ph-factor-score">${fScore}</span><span class="ph-factor-note">${f.note || ''}</span></div>`;
  }).join('');
  const hoursLeft = p.hoursLeft != null ? `${p.hoursLeft.toFixed(1)}h bis Anpfiff` : 'Anpfiff-Zeit unbekannt';
  const safeKey = (p.key || '').replace(/['"\\]/g, '');
  return `
    <details class="ph-card ${statusClass}">
      <summary class="ph-card-head">
        <div class="ph-card-left">
          <span class="ph-card-flags">${p.homeFlag || '🏳'} ${p.awayFlag || '🏳'}</span>
          <div class="ph-card-match">
            <div class="ph-card-teams">${p.home || '?'} vs ${p.away || '?'}</div>
            <div class="ph-card-market">${p.market || '?'} · ${hoursLeft}</div>
          </div>
        </div>
        <div class="ph-card-score-block">
          <div class="ph-card-score-num">${score}</div>
          <div class="ph-card-score-lbl">/100</div>
        </div>
      </summary>
      <div class="ph-card-body">
        <div class="ph-card-factors">${factors}</div>
        <div class="ph-card-reco">💡 ${p.recommendation || ''}</div>
      </div>
    </details>
  `;
}

function _phFmtTime(iso) {
  try {
    const d = new Date(iso);
    const mins = Math.round((Date.now() - d.getTime()) / 60000);
    if (mins < 60) return `vor ${mins}m`;
    if (mins < 1440) return `vor ${Math.round(mins/60)}h`;
    return d.toLocaleString('de-AT', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
  } catch (e) { return ''; }
}
