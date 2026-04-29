#!/usr/bin/env python3
"""
fetch_poly_prices.py — Server-side Polymarket price fetcher
Runs in GitHub Actions (no CORS restrictions).

Reads  : picks_output.json
Writes : polymarket_prices.json

Output format:
{
  "fetched": "2026-05-01T06:00:00Z",
  "matches": {
    "Leeds|Burnley": {
      "found": true,
      "eventTitle": "Leeds United vs Burnley",
      "eventUrl": "https://polymarket.com/event/...",
      "markets": {
        "Heimsieg":       0.62,
        "Auswärtssieg":   0.21,
        "Unentschieden":  0.17,
        "Over 2.5 Tore":  0.55,
        "Under 2.5 Tore": 0.45
      }
    },
    ...
  }
}
"""

import json
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone

# ── Leagues covered on Polymarket ────────────────────────
POLY_LEAGUES = {'GER', 'ENG', 'ITA', 'ESP', 'FRA', 'NED', 'POR', 'TUR', 'GER2', 'SCO'}

# ── Markets we extract ────────────────────────────────────
POLY_MARKETS = {'Heimsieg', 'Auswärtssieg', 'Unentschieden', 'Over 2.5 Tore', 'Under 2.5 Tore'}

# ── German → English team name map ───────────────────────
TEAM_NAME_MAP = {
    # Bundesliga
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
    # 2. Bundesliga
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
    # Premier League
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
    # Serie A
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
    # La Liga
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
    # Ligue 1
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
    # Eredivisie
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
    # Primeira Liga
    'Benfica':                  'Benfica',
    'FC Porto':                 'Porto',
    'Porto':                    'Porto',
    'Sporting CP':              'Sporting CP',
    'Braga':                    'Braga',
    'Vitória de Guimarães':     'Guimaraes',
    'Guimarães':                'Guimaraes',
    'Famalicão':                'Famalicao',
    # Süper Lig
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
    # Scottish Premiership
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
    # Championship (ENG2)
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
    # Newcastle (common alias)
    'Newcastle':                'Newcastle United',
}


def to_english(name: str) -> str:
    return TEAM_NAME_MAP.get(name, name)


def team_tokens(name: str) -> list[str]:
    """Extract meaningful tokens (≥ 3 chars) from a team name."""
    return [t for t in name.lower().split() if len(t) >= 3]


def any_token_in(tokens: list[str], text: str) -> bool:
    return any(t in text for t in tokens)


def gamma_search(keyword: str, active_only: bool = True, retries: int = 3) -> list:
    """Call Gamma API and return list of events. Returns [] on error."""
    params = f"keyword={urllib.parse.quote(keyword)}&limit=15"
    if active_only:
        params += "&active=true"
    url = f"https://gamma-api.polymarket.com/events?{params}"

    headers = {
        'User-Agent': 'BetEdge-Dashboard/1.0 (GitHub Actions)',
        'Accept': 'application/json',
    }

    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                result = data if isinstance(data, list) else []
                if result:
                    print(f"  [gamma] '{keyword}' → {len(result)} events: {[e.get('title','?') for e in result[:3]]}")
                else:
                    print(f"  [gamma] '{keyword}' → 0 events (leere Antwort)")
                return result
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)  # exponential backoff
            else:
                print(f"  [gamma] ❌ {keyword!r}: {e}")
    return []


def extract_outcome_price(market: str, question: str, outcomes: list, prices: list,
                          home_en: str, away_en: str) -> float | None:
    """
    Mirror of JS _extractOutcomePrice().
    Returns probability as float (0–1) or None if no match.
    """
    q = question.lower()
    is_goals = '2.5' in market and 'Tore' in market

    if is_goals:
        if '2.5' not in q and 'goal' not in q:
            return None
        # Yes/No style outcomes
        y_idx = next((i for i, o in enumerate(outcomes) if o.lower() == 'yes'), -1)
        n_idx = next((i for i, o in enumerate(outcomes) if o.lower() == 'no'), -1)
        if market.startswith('Over') and y_idx >= 0:
            return _safe_float(prices[y_idx])
        if market.startswith('Under') and n_idx >= 0:
            return _safe_float(prices[n_idx])
        # Over/Under labelled outcomes
        o_idx = next((i for i, o in enumerate(outcomes) if 'over' in o.lower()), -1)
        u_idx = next((i for i, o in enumerate(outcomes) if 'under' in o.lower()), -1)
        if market.startswith('Over') and o_idx >= 0:
            return _safe_float(prices[o_idx])
        if market.startswith('Under') and u_idx >= 0:
            return _safe_float(prices[u_idx])
        return None

    # 1X2 / Match Winner
    if 'win' not in q and 'winner' not in q and 'match' not in q:
        return None

    h_first = home_en.lower().split()[0]
    a_first = away_en.lower().split()[0]

    if market == 'Heimsieg':
        idx = next((i for i, o in enumerate(outcomes) if h_first in o.lower()), -1)
        return _safe_float(prices[idx]) if idx >= 0 else None
    if market == 'Auswärtssieg':
        idx = next((i for i, o in enumerate(outcomes) if a_first in o.lower()), -1)
        return _safe_float(prices[idx]) if idx >= 0 else None
    if market == 'Unentschieden':
        idx = next((i for i, o in enumerate(outcomes) if 'draw' in o.lower()), -1)
        return _safe_float(prices[idx]) if idx >= 0 else None
    return None


def _safe_float(val) -> float | None:
    try:
        f = float(val)
        return f if 0 < f <= 1 else None
    except (TypeError, ValueError):
        return None


def match_event_prices(ev: dict, home_en: str, away_en: str) -> dict | None:
    """
    Try to extract prices for all POLY_MARKETS from a Gamma event.
    Returns dict of {market: price} or None if nothing matched.
    """
    found_markets = {}

    for mkt in (ev.get('markets') or []):
        q = (mkt.get('question') or '').lower()
        try:
            outcomes = json.loads(mkt.get('outcomes') or '[]')
            prices   = json.loads(mkt.get('outcomePrices') or '[]')
        except (json.JSONDecodeError, TypeError):
            continue
        if not outcomes or len(outcomes) != len(prices):
            continue

        for market in POLY_MARKETS:
            if market in found_markets:
                continue
            price = extract_outcome_price(market, q, outcomes, prices, home_en, away_en)
            if price is not None:
                found_markets[market] = price

    return found_markets if found_markets else None


def fetch_match_prices(home: str, away: str) -> dict:
    """
    Try multiple search strategies to find Polymarket prices for a match.
    Returns structured result dict.
    """
    home_en = to_english(home)
    away_en = to_english(away)
    home_tokens = team_tokens(home_en)
    away_tokens = team_tokens(away_en)

    def try_events(events: list, label: str) -> dict | None:
        for ev in events:
            title = (ev.get('title') or '').lower()
            if not any_token_in(home_tokens, title):
                continue
            if not any_token_in(away_tokens, title):
                continue
            markets = match_event_prices(ev, home_en, away_en)
            if markets:
                slug = ev.get('slug') or ''
                url = f"https://polymarket.com/event/{slug}" if slug else "https://polymarket.com/"
                print(f"  ✅ [{label}] {ev.get('title')}")
                return {
                    'found': True,
                    'eventTitle': ev.get('title', ''),
                    'eventUrl': url,
                    'markets': markets,
                }
        return None

    strategies = [
        (f"{home_en} {away_en}", True,  'S1:combined'),
        (home_en,                True,  'S2:home-only'),
        (away_en,                True,  'S3:away-only'),
        (f"{home_en} {away_en}", False, 'S4:combined-no-active'),
        (home_en,                False, 'S5:home-no-active'),
    ]

    for keyword, active_only, label in strategies:
        events = gamma_search(keyword, active_only=active_only)
        result = try_events(events, label)
        if result:
            return result
        time.sleep(0.3)  # gentle throttle between API calls

    print(f"  ❌ No market found: {home_en} vs {away_en}")
    return {'found': False, 'eventTitle': '', 'eventUrl': '', 'markets': {}}


def main():
    # Load picks
    try:
        with open('picks_output.json', 'r', encoding='utf-8') as f:
            picks_list = json.load(f)
    except FileNotFoundError:
        print("⚠️  picks_output.json not found — writing empty polymarket_prices.json")
        out = {'fetched': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'matches': {}}
        with open('polymarket_prices.json', 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        return
    except json.JSONDecodeError as e:
        print(f"❌ picks_output.json parse error: {e}")
        return

    # Collect unique matches that have at least one POLY_MARKETS pick
    unique_matches: dict[str, tuple[str, str]] = {}  # key → (home, away)
    for fx in picks_list:
        league = fx.get('league', '')
        if league not in POLY_LEAGUES:
            continue
        home = fx.get('home', '')
        away = fx.get('away', '')
        if not home or not away:
            continue

        has_poly_market = any(
            p.get('market') in POLY_MARKETS
            for p in (fx.get('picks') or [])
        )
        if not has_poly_market:
            continue

        key = f"{home}|{away}"
        unique_matches[key] = (home, away)

    print(f"🔍 {len(unique_matches)} matches to fetch from Polymarket Gamma API")

    results: dict[str, dict] = {}
    for i, (key, (home, away)) in enumerate(unique_matches.items(), 1):
        print(f"[{i}/{len(unique_matches)}] {home} vs {away}")
        results[key] = fetch_match_prices(home, away)
        # Small pause between matches to be polite to the API
        if i < len(unique_matches):
            time.sleep(0.5)

    found_count = sum(1 for v in results.values() if v.get('found'))
    print(f"\n✅ Done: {found_count}/{len(unique_matches)} matches found on Polymarket")

    out = {
        'fetched': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'matches': results,
    }
    with open('polymarket_prices.json', 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("💾 polymarket_prices.json saved")


if __name__ == '__main__':
    main()
