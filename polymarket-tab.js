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
  'FC Barcelona':             'Barcelona',
  'Barcelona':                'Barcelona',
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

// ── 4. GAMMA API ────────────────────────────────────────

async function fetchGammaPrice(pick) {
  const homeEn = toEnglishName(pick.home);
  const awayEn = toEnglishName(pick.away);

  // Build search keyword — try full names first, fall back to first word of each
  const keyword = `${homeEn} ${awayEn}`;

  let events = [];
  try {
    const res = await fetch(
      `https://gamma-api.polymarket.com/events?keyword=${encodeURIComponent(keyword)}&active=true&limit=12`,
      { signal: AbortSignal.timeout(8000) }
    );
    if (!res.ok) return null;
    events = await res.json();
  } catch (e) { return null; }

  // Find best matching event (title contains at least one team name token)
  const homeTokens = homeEn.toLowerCase().split(/\s+/).filter(t => t.length > 3);
  const awayTokens = awayEn.toLowerCase().split(/\s+/).filter(t => t.length > 3);

  for (const ev of events) {
    const title = (ev.title || '').toLowerCase();
    const homeMatch = homeTokens.some(t => title.includes(t));
    const awayMatch = awayTokens.some(t => title.includes(t));
    if (!homeMatch || !awayMatch) continue;

    // Search markets within this event
    for (const mkt of (ev.markets || [])) {
      const q = (mkt.question || '').toLowerCase();
      let outcomes, prices;
      try {
        outcomes = JSON.parse(mkt.outcomes || '[]');
        prices   = JSON.parse(mkt.outcomePrices || '[]');
      } catch (e) { continue; }
      if (!outcomes.length || outcomes.length !== prices.length) continue;

      const price = _extractOutcomePrice(pick.market, q, outcomes, prices, homeEn, awayEn);
      if (price !== null) {
        return { found: true, price, eventTitle: ev.title, marketQ: mkt.question };
      }
    }
  }
  return null;
}

function _extractOutcomePrice(market, question, outcomes, prices, homeEn, awayEn) {
  const isGoals = market.includes('2.5 Tore');

  // ── Over/Under 2.5 ──────────────────────────────────
  if (isGoals) {
    if (!question.includes('2.5') && !question.includes('goal')) return null;
    const yIdx = outcomes.findIndex(o => o.toLowerCase() === 'yes');
    const nIdx = outcomes.findIndex(o => o.toLowerCase() === 'no');
    if (market.startsWith('Over')  && yIdx >= 0) return parseFloat(prices[yIdx]) || null;
    if (market.startsWith('Under') && nIdx >= 0) return parseFloat(prices[nIdx]) || null;
    // Some markets have "Over" / "Under" as outcomes
    const oIdx = outcomes.findIndex(o => o.toLowerCase().includes('over'));
    const uIdx = outcomes.findIndex(o => o.toLowerCase().includes('under'));
    if (market.startsWith('Over')  && oIdx >= 0) return parseFloat(prices[oIdx]) || null;
    if (market.startsWith('Under') && uIdx >= 0) return parseFloat(prices[uIdx]) || null;
    return null;
  }

  // ── 1X2 / Match Winner ──────────────────────────────
  if (!question.includes('win') && !question.includes('winner') && !question.includes('match')) return null;

  const hFirst = homeEn.toLowerCase().split(' ')[0];
  const aFirst = awayEn.toLowerCase().split(' ')[0];

  if (market === 'Heimsieg') {
    const idx = outcomes.findIndex(o => o.toLowerCase().includes(hFirst));
    return idx >= 0 ? (parseFloat(prices[idx]) || null) : null;
  }
  if (market === 'Auswärtssieg') {
    const idx = outcomes.findIndex(o => o.toLowerCase().includes(aFirst));
    return idx >= 0 ? (parseFloat(prices[idx]) || null) : null;
  }
  if (market === 'Unentschieden') {
    const idx = outcomes.findIndex(o => o.toLowerCase().includes('draw'));
    return idx >= 0 ? (parseFloat(prices[idx]) || null) : null;
  }
  return null;
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
  if (!p.found)               return `<span style="color:#8b949e;font-size:12px">kein Markt</span>`;
  const pct      = Math.round(p.price * 100);
  const polyOdds = (1 / p.price).toFixed(2);
  return `<span style="color:#a78bfa;font-weight:700;font-size:15px">${pct}¢</span> <span style="color:#8b949e;font-size:11px">(${polyOdds})</span>`;
}

function _edgeBlock(pick, pickId) {
  const p = _polyState.prices[pickId];
  if (!p || !p.found || !pick.odds) return `<span style="color:#8b949e;font-size:12px">—</span>`;
  const ourImplied = 1 / pick.odds;
  const edgePp     = Math.round((p.price - ourImplied) * 100);
  if (Math.abs(edgePp) < 1) return `<span style="color:#8b949e;font-size:12px">≈ 0%</span>`;
  const col  = edgePp > 0 ? '#3fb950' : '#f85149';
  const sign = edgePp > 0 ? '+' : '';
  return `<span style="color:${col};font-size:13px;font-weight:700">${sign}${edgePp}pp</span>`;
}

function _renderPickCard(pick) {
  const isSel      = _polyState.selected.has(pick.id);
  const priceData  = _polyState.prices[pick.id];
  const noMarket   = priceData && !priceData.loading && !priceData.found;
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
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:0;background:#0d1117;border-radius:8px;overflow:hidden">
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
    ? `<tr><td colspan="5" style="text-align:center;color:#8b949e;padding:28px;font-size:13px">Noch keine Bets gespeichert</td></tr>`
    : recent.map((b, i) => {
        const resIcon  = b.result === 'won'  ? '✅' : b.result === 'lost' ? '❌' : b.result === 'void' ? '—' : '⏳';
        const resColor = b.result === 'won'  ? '#3fb950' : b.result === 'lost' ? '#f85149' : '#8b949e';
        const pricePct = b.polyPrice ? `${Math.round(b.polyPrice * 100)}¢` : '—';
        return `<tr style="border-bottom:1px solid #30363d">
          <td style="padding:9px 12px;font-size:11px;color:#8b949e">${b.date}</td>
          <td style="padding:9px 12px;font-size:12px">${b.home} vs ${b.away}</td>
          <td style="padding:9px 12px;font-size:12px;color:${_marketColor(b.market)}">${b.market}</td>
          <td style="padding:9px 12px;font-size:12px;color:#a78bfa">${pricePct}</td>
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
        <button onclick="polyManualResolve()" style="background:none;border:1px solid #30363d;border-radius:6px;color:#8b949e;font-size:11px;font-weight:600;padding:4px 10px;cursor:pointer;font-family:inherit">✏️ Ergebnisse einpflegen</button>
      </div>
      <table style="width:100%;border-collapse:collapse">
        <thead style="background:#1c2128">
          <tr>
            <th style="padding:8px 12px;text-align:left;font-size:9px;color:#8b949e;font-weight:700;text-transform:uppercase;letter-spacing:.5px">Datum</th>
            <th style="padding:8px 12px;text-align:left;font-size:9px;color:#8b949e;font-weight:700;text-transform:uppercase;letter-spacing:.5px">Spiel</th>
            <th style="padding:8px 12px;text-align:left;font-size:9px;color:#8b949e;font-weight:700;text-transform:uppercase;letter-spacing:.5px">Markt</th>
            <th style="padding:8px 12px;text-align:left;font-size:9px;color:#8b949e;font-weight:700;text-transform:uppercase;letter-spacing:.5px">Preis</th>
            <th style="padding:8px 12px;text-align:left;font-size:9px;color:#8b949e;font-weight:700;text-transform:uppercase;letter-spacing:.5px">Result</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

// ── 7. CONFIRMATION FLOW ────────────────────────────────

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
    home:      toEnglishName(p.home),
    away:      toEnglishName(p.away),
    market:    p.market,
    league:    p.league,
    bookyOdds: p.odds,
    stake:     POLY_STAKE,
    polyPrice: _polyState.prices[p.id]?.found ? _polyState.prices[p.id].price : null,
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
        <div style="font-size:12px;color:#8b949e;margin-top:3px">${dateStr} &nbsp;·&nbsp; ${n} eligible pick${n !== 1 ? 's' : ''}</div>
      </div>
      <div style="margin-left:auto;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <button onclick="polySelectAll()"  style="background:none;border:1px solid #30363d;border-radius:8px;color:#8b949e;font-size:11px;font-weight:600;padding:7px 13px;cursor:pointer;font-family:inherit;transition:border-color .15s" onmouseover="this.style.borderColor='#a78bfa'" onmouseout="this.style.borderColor='#30363d'">☑️ Alle</button>
        <button onclick="polySelectNone()" style="background:none;border:1px solid #30363d;border-radius:8px;color:#8b949e;font-size:11px;font-weight:600;padding:7px 13px;cursor:pointer;font-family:inherit;transition:border-color .15s" onmouseover="this.style.borderColor='#a78bfa'" onmouseout="this.style.borderColor='#30363d'">⬜ Keine</button>
        <button onclick="initPolymarket()" style="background:none;border:1px solid #30363d;border-radius:8px;color:#8b949e;font-size:11px;font-weight:600;padding:7px 13px;cursor:pointer;font-family:inherit;transition:border-color .15s" onmouseover="this.style.borderColor='#00d4a1'" onmouseout="this.style.borderColor='#30363d'">🔄 Refresh</button>
        <button id="polySettingsBtn" onclick="polyOpenSettings()" style="background:none;border:1px solid ${_getGithubPAT() ? '#3fb95055' : '#f8514933'};border-radius:8px;color:${_getGithubPAT() ? '#3fb950' : '#f85149'};font-size:11px;font-weight:600;padding:7px 13px;cursor:pointer;font-family:inherit">⚙️ Setup</button>
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
      <span style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.8px;color:#8b949e">
        Picks — ${n} verfügbar
      </span>
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
      <button onclick="polyConfirm()"
              style="background:linear-gradient(135deg,#a78bfa,#7c3aed);border:none;border-radius:10px;color:#fff;font-size:14px;font-weight:800;padding:11px 26px;cursor:pointer;font-family:inherit;letter-spacing:.02em;box-shadow:0 2px 12px #a78bfa44">
        🟣 Jetzt platzieren
      </button>
    </div>`;

  // Init sticky bar
  _polyRefreshStickyBar();

  // Fetch prices asynchronously
  _fetchAllPricesAsync();
}

async function _fetchAllPricesAsync() {
  const picks        = _polyState.picks;
  const statusEl     = document.getElementById('polyPriceStatus');
  let   fetchedCount = 0;

  for (const pick of picks) {
    _polyState.prices[pick.id] = { loading: true, found: false };

    try {
      const result = await fetchGammaPrice(pick);
      _polyState.prices[pick.id] = result
        ? { found: true, price: result.price, eventTitle: result.eventTitle }
        : { found: false };
    } catch (e) {
      _polyState.prices[pick.id] = { found: false };
    }

    fetchedCount++;

    // Update pick cards after each fetch
    const grid = document.getElementById('polyPickGrid');
    if (grid) grid.innerHTML = renderPolyPickCards();

    // Update status label
    if (statusEl) {
      if (fetchedCount < picks.length) {
        statusEl.textContent = `⏳ ${fetchedCount}/${picks.length} Preise geladen…`;
      } else {
        const found = Object.values(_polyState.prices).filter(p => p.found).length;
        statusEl.textContent = `✅ ${found}/${picks.length} Märkte gefunden`;
        statusEl.style.color = '#3fb950';
      }
    }

    // Brief pause to avoid hammering the API
    await new Promise(r => setTimeout(r, 350));
  }

  if (picks.length === 0 && statusEl) {
    statusEl.textContent = '';
  }
}
