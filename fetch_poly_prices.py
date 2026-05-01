#!/usr/bin/env python3
"""
fetch_poly_prices.py — Server-side Polymarket price fetcher
Runs in GitHub Actions (no CORS restrictions).

Strategy: bulk-fetch ALL active soccer/football events from Polymarket
(keyword search is broken — returns irrelevant results regardless of query).
Then match fixtures by team name in event title.

Reads  : picks_output.json
Writes : polymarket_prices.json
"""

import json
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone

# ── Markets we extract ────────────────────────────────────
POLY_MARKETS = {'Heimsieg', 'Auswärtssieg', 'Unentschieden', 'Over 2.5 Tore', 'Under 2.5 Tore'}

# ── Leagues covered on Polymarket ────────────────────────
POLY_LEAGUES = {'GER', 'ENG', 'ITA', 'ESP', 'FRA', 'NED', 'POR', 'TUR', 'GER2', 'SCO', 'ENG2'}

# ── German → English team name map ───────────────────────
TEAM_NAME_MAP = {
    'Bayern München':           'Bayern Munich',
    'Bayern':                   'Bayern Munich',
    'Borussia Dortmund':        'Dortmund',
    'Bayer Leverkusen':         'Leverkusen',
    'RB Leipzig':               'Leipzig',
    'Eintracht Frankfurt':      'Frankfurt',
    'VfB Stuttgart':            'Stuttgart',
    'Borussia Mönchengladbach': 'Gladbach',
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
    'Holstein Kiel':            'Kiel',
    'FC St. Pauli':             'St. Pauli',
    'Hamburger SV':             'Hamburger SV',
    'Fortuna Düsseldorf':       'Dusseldorf',
    '1. FC Köln':               'Koln',
    'Hannover 96':              'Hannover',
    'Karlsruher SC':            'Karlsruhe',
    'Hertha BSC':               'Hertha',
    'SpVgg Greuther Fürth':     'Furth',
    'SC Paderborn':             'Paderborn',
    '1. FC Nürnberg':           'Nuremberg',
    'FC Schalke 04':            'Schalke',
    'Darmstadt 98':             'Darmstadt',
    'Manchester City':          'Manchester City',
    'Arsenal':                  'Arsenal',
    'Liverpool':                'Liverpool',
    'Manchester United':        'Manchester United',
    'Chelsea':                  'Chelsea',
    'Tottenham Hotspur':        'Tottenham',
    'Tottenham':                'Tottenham',
    'Newcastle United':         'Newcastle',
    'Newcastle':                'Newcastle',
    'Aston Villa':              'Aston Villa',
    'Brighton & Hove Albion':   'Brighton',
    'Brighton':                 'Brighton',
    'West Ham United':          'West Ham',
    'West Ham':                 'West Ham',
    'Wolverhampton Wanderers':  'Wolves',
    'Wolves':                   'Wolves',
    'Crystal Palace':           'Crystal Palace',
    'Nottingham Forest':        'Nottingham Forest',
    'Brentford':                'Brentford',
    'Fulham':                   'Fulham',
    'Everton':                  'Everton',
    'AFC Bournemouth':          'Bournemouth',
    'Bournemouth':              'Bournemouth',
    'Leicester City':           'Leicester',
    'Ipswich Town':             'Ipswich',
    'Southampton':              'Southampton',
    'Inter Mailand':            'Inter Milan',
    'Inter Milan':              'Inter Milan',
    'AC Mailand':               'AC Milan',
    'AC Milan':                 'AC Milan',
    'Juventus':                 'Juventus',
    'Napoli':                   'Napoli',
    'AS Roma':                  'Roma',
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
    'Levante':                  'Levante',
    'Paris Saint-Germain':      'PSG',
    'PSG':                      'PSG',
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
    'Ajax':                     'Ajax',
    'PSV Eindhoven':            'PSV',
    'Feyenoord':                'Feyenoord',
    'AZ Alkmaar':               'AZ',
    'FC Utrecht':               'Utrecht',
    'FC Twente':                'Twente',
    'Benfica':                  'Benfica',
    'FC Porto':                 'Porto',
    'Porto':                    'Porto',
    'Sporting CP':              'Sporting',
    'Braga':                    'Braga',
    'Galatasaray':              'Galatasaray',
    'Fenerbahçe':               'Fenerbahce',
    'Fenerbahce':               'Fenerbahce',
    'Beşiktaş':                 'Besiktas',
    'Trabzonspor':              'Trabzonspor',
    'Celtic':                   'Celtic',
    'Rangers':                  'Rangers',
    'Leeds':                    'Leeds',
    'Leeds United':             'Leeds',
    'Burnley':                  'Burnley',
    'Sheffield United':         'Sheffield United',
    'West Brom':                'West Brom',
    'West Bromwich Albion':     'West Brom',
    'Sunderland':               'Sunderland',
    'Middlesbrough':            'Middlesbrough',
    'Watford':                  'Watford',
    'Blackburn Rovers':         'Blackburn',
    'Blackburn':                'Blackburn',
    'Coventry City':            'Coventry',
    'Stoke City':               'Stoke',
    'Cardiff City':             'Cardiff',
    'Bristol City':             'Bristol City',
    'Norwich City':             'Norwich',
    'Preston North End':        'Preston',
    'Hull City':                'Hull',
    'Millwall':                 'Millwall',
    'Luton Town':               'Luton',
    'Luton':                    'Luton',
    'Derby County':             'Derby',
    'Portsmouth':               'Portsmouth',
    'Plymouth Argyle':          'Plymouth',
    'Oxford United':            'Oxford',
    'Swansea City':             'Swansea',
    'QPR':                      'QPR',
    'Queens Park Rangers':      'QPR',
    'Sheffield Wednesday':      'Sheffield Wednesday',
}


def to_english(name: str) -> str:
    return TEAM_NAME_MAP.get(name, name)


def _parse_list_field(val) -> list:
    """Parse a field that might be a JSON string or already a list."""
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            result = json.loads(val)
            return result if isinstance(result, list) else []
        except (json.JSONDecodeError, ValueError):
            return []
    return []


def _safe_float(val) -> float | None:
    try:
        f = float(val)
        return f if 0 < f <= 1 else None
    except (TypeError, ValueError):
        return None


def api_get(url: str, retries: int = 3) -> list | dict | None:
    """Make a GET request and return parsed JSON."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'application/json',
    }
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                print(f"  ❌ API error {url}: {e}")
    return None


def _extract_list(data) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ('data', 'events', 'markets', 'results', 'items'):
            if key in data and isinstance(data[key], list):
                return data[key]
    return []


# ── Fetch all soccer events ───────────────────────────────

# Known soccer-related tag IDs on Polymarket (discovered empirically)
# Add more here as they're found
KNOWN_SOCCER_TAG_IDS: list[str] = []  # populated at runtime from tag discovery

# Soccer keywords for title-based filtering
SOCCER_TITLE_SIGNALS = {
    'epl', 'premier league', 'bundesliga', 'serie a', 'la liga', 'ligue 1',
    'champions league', 'europa league', 'eredivisie', 'primeira liga',
    'süper lig', 'super lig', 'scottish', 'soccer', 'football',
    # Common team names that appear in match titles
    'arsenal', 'liverpool', 'chelsea', 'manchester', 'tottenham', 'newcastle',
    'brentford', 'fulham', 'everton', 'brighton', 'west ham', 'villa',
    'barcelona', 'real madrid', 'atletico', 'sevilla', 'villarreal',
    'juventus', 'milan', 'inter', 'napoli', 'roma', 'atalanta',
    'bayern', 'dortmund', 'leverkusen', 'leipzig', 'frankfurt', 'stuttgart',
    'psg', 'paris', 'marseille', 'monaco', 'lille', 'lyon',
    'ajax', 'psv', 'feyenoord', 'porto', 'benfica', 'sporting',
    'celtic', 'rangers', 'galatasaray', 'fenerbahce', 'besiktas',
    'leeds', 'burnley', 'sunderland', 'sheffield',
}


def _looks_like_soccer(event: dict) -> bool:
    """Heuristic: does this event look like a soccer/football event?"""
    title = (event.get('title') or '').lower()
    tags  = event.get('tags') or []
    tag_labels = ' '.join(
        (t.get('label') or t.get('name') or t.get('slug') or '') for t in tags
    ).lower()
    combined = title + ' ' + tag_labels
    return any(s in combined for s in SOCCER_TITLE_SIGNALS)


def discover_all_tags() -> list[dict]:
    """Paginate through ALL tags from Gamma API."""
    all_tags = []
    offset = 0
    while True:
        data = api_get(f"https://gamma-api.polymarket.com/tags?limit=200&offset={offset}")
        batch = _extract_list(data)
        if not batch:
            break
        all_tags.extend(batch)
        if len(batch) < 200:
            break
        offset += 200
        time.sleep(0.2)
    return all_tags


def get_soccer_tag_ids() -> list[str]:
    """Return tag IDs for soccer/football leagues."""
    soccer_keywords = {
        'soccer', 'football', 'epl', 'bundesliga', 'serie a', 'la liga', 'laliga',
        'ligue', 'premier league', 'premier-league', 'eredivisie', 'primeira',
        'scottish', 'championship', 'liga', 'calcio', 'fussball',
    }
    # Exclude non-soccer sports that also match
    exclude_keywords = {
        'rugby', 'cricket', 'poker', 'golf', 'college', 'american', 'nfl',
        'nba', 'mlb', 'nhl', 'tennis', 'mma', 'boxing', 'college football',
        'motor', 'formula', 'cycling', 'swimming', 'athletics',
    }

    all_tags = discover_all_tags()
    print(f"  [tags] Total tags found: {len(all_tags)}")

    soccer_ids = []
    for tag in all_tags:
        label = (tag.get('label') or tag.get('name') or tag.get('slug') or '').lower()
        if any(kw in label for kw in exclude_keywords):
            continue
        if any(kw in label for kw in soccer_keywords):
            tid = tag.get('id') or tag.get('tag_id')
            if tid:
                soccer_ids.append(str(tid))
                print(f"  [tag] {label!r} → id={tid}")
    return soccer_ids


def fetch_events_by_tag(tag_id: str) -> list[dict]:
    """Fetch all active events for a given tag ID."""
    events = []
    offset = 0
    while True:
        url = (f"https://gamma-api.polymarket.com/events"
               f"?tag_id={tag_id}&active=true&limit=100&offset={offset}")
        data = api_get(url)
        batch = _extract_list(data)
        if not batch:
            break
        events.extend(batch)
        print(f"  [tag={tag_id}] +{len(batch)} events (offset={offset})")
        if len(batch) < 100:
            break
        offset += 100
        time.sleep(0.25)
    return events


def fetch_via_games_category() -> list[dict]:
    """
    Try Polymarket's gamesCategory parameter — used internally for the Sports section.
    Tries multiple likely parameter names.
    """
    attempts = [
        "https://gamma-api.polymarket.com/events?gamesCategory=soccer&active=true&limit=100",
        "https://gamma-api.polymarket.com/events?gamesCategory=football&active=true&limit=100",
        "https://gamma-api.polymarket.com/events?sport=soccer&active=true&limit=100",
        "https://gamma-api.polymarket.com/events?category=soccer&active=true&limit=100",
        "https://gamma-api.polymarket.com/events?sports=soccer&active=true&limit=100",
    ]
    for url in attempts:
        data = api_get(url)
        batch = _extract_list(data)
        if batch and _looks_like_soccer(batch[0]):
            param = url.split('?')[1].split('&')[0]
            print(f"  [gamesCategory] ✅ '{param}' returned {len(batch)} events")
            # Paginate remaining pages
            events = list(batch)
            if len(batch) == 100:
                offset = 100
                while True:
                    data2 = api_get(url.replace('limit=100', f'limit=100&offset={offset}'))
                    b2 = _extract_list(data2)
                    if not b2:
                        break
                    events.extend(b2)
                    print(f"  [gamesCategory] +{len(b2)} (offset={offset})")
                    if len(b2) < 100:
                        break
                    offset += 100
                    time.sleep(0.25)
            return events
    print("  [gamesCategory] No sport-category endpoint worked")
    return []


def fetch_all_events_paginated(max_pages: int = 60) -> list[dict]:
    """
    Paginate ALL active Polymarket events, collect ones that look like soccer.
    Stops after max_pages pages to avoid timeout.
    """
    soccer_events = []
    offset = 0
    consecutive_empty_soccer = 0

    for page in range(max_pages):
        url = (f"https://gamma-api.polymarket.com/events"
               f"?active=true&limit=100&order=volume&ascending=false&offset={offset}")
        data = api_get(url)
        batch = _extract_list(data)
        if not batch:
            break

        soccer_batch = [e for e in batch if _looks_like_soccer(e)]
        soccer_events.extend(soccer_batch)

        if soccer_batch:
            consecutive_empty_soccer = 0
            titles = [e.get('title', '')[:40] for e in soccer_batch[:2]]
            print(f"  [page {page+1}] {len(batch)} total, {len(soccer_batch)} soccer — e.g. {titles}")
        else:
            consecutive_empty_soccer += 1
            print(f"  [page {page+1}] {len(batch)} total, 0 soccer")

        if len(batch) < 100:
            break
        # Stop early if many pages with no soccer (sorted by volume, soccer events are high-volume)
        if consecutive_empty_soccer >= 5 and len(soccer_events) >= 20:
            print(f"  [page {page+1}] Stopping — 5 consecutive pages without soccer")
            break
        offset += 100
        time.sleep(0.25)

    return soccer_events


def fetch_all_soccer_events(tag_ids: list[str]) -> list[dict]:
    """
    Fetch all active soccer events from Polymarket using multiple strategies.
    Returns deduplicated list of event dicts.
    """
    all_events: dict[str, dict] = {}  # id → event (for deduplication)

    def add_events(evs: list[dict], source: str):
        n_new = 0
        for ev in evs:
            eid = str(ev.get('id') or ev.get('slug') or id(ev))
            if eid not in all_events:
                all_events[eid] = ev
                n_new += 1
        print(f"  [{source}] +{n_new} new events (total: {len(all_events)})")

    # Strategy 1: gamesCategory parameter (most targeted)
    print("\n  Strategy 1: gamesCategory endpoint...")
    gc_events = fetch_via_games_category()
    if gc_events:
        add_events(gc_events, 'gamesCategory')

    # Strategy 2: fetch by soccer tag IDs
    if tag_ids:
        print(f"\n  Strategy 2: fetching {len(tag_ids)} tag(s)...")
        for tid in tag_ids:
            evs = fetch_events_by_tag(tid)
            soccer_evs = [e for e in evs if _looks_like_soccer(e)]
            if soccer_evs:
                # Show sample titles so we know what we're getting
                sample = [e.get('title', '')[:50] for e in soccer_evs[:3]]
                print(f"  [tag={tid}] sample: {sample}")
                add_events(soccer_evs, f'tag={tid}')
            else:
                print(f"  [tag={tid}] {len(evs)} events but none look like soccer — skipped")

    # Strategy 3: paginate all events sorted by volume (soccer is popular = high volume)
    if len(all_events) < 30:
        print(f"\n  Strategy 3: paginating all events (have only {len(all_events)} so far)...")
        paginated = fetch_all_events_paginated(max_pages=60)
        add_events(paginated, 'pagination')

    return list(all_events.values())


# ── Price extraction from events ─────────────────────────

def extract_outcome_price(market: str, question: str, outcomes: list,
                          prices: list, home_en: str, away_en: str) -> float | None:
    q = question.lower()
    is_goals = '2.5' in market

    if is_goals:
        if '2.5' not in q and 'goal' not in q:
            return None
        y_idx = next((i for i, o in enumerate(outcomes) if str(o).lower() == 'yes'), -1)
        n_idx = next((i for i, o in enumerate(outcomes) if str(o).lower() == 'no'), -1)
        o_idx = next((i for i, o in enumerate(outcomes) if 'over' in str(o).lower()), -1)
        u_idx = next((i for i, o in enumerate(outcomes) if 'under' in str(o).lower()), -1)
        if market.startswith('Over'):
            idx = y_idx if y_idx >= 0 else o_idx
            return _safe_float(prices[idx]) if idx >= 0 else None
        else:
            idx = n_idx if n_idx >= 0 else u_idx
            return _safe_float(prices[idx]) if idx >= 0 else None

    # 1X2 match winner
    win_keywords = ('win', 'winner', 'match', 'beat', 'vs', 'v ')
    if not any(kw in q for kw in win_keywords):
        return None

    home_tokens = [t for t in home_en.lower().split() if len(t) >= 3]
    away_tokens = [t for t in away_en.lower().split() if len(t) >= 3]

    if market == 'Heimsieg':
        idx = next((i for i, o in enumerate(outcomes)
                    if any(t in str(o).lower() for t in home_tokens)), -1)
        return _safe_float(prices[idx]) if idx >= 0 else None
    if market == 'Auswärtssieg':
        idx = next((i for i, o in enumerate(outcomes)
                    if any(t in str(o).lower() for t in away_tokens)), -1)
        return _safe_float(prices[idx]) if idx >= 0 else None
    if market == 'Unentschieden':
        idx = next((i for i, o in enumerate(outcomes)
                    if 'draw' in str(o).lower()), -1)
        return _safe_float(prices[idx]) if idx >= 0 else None
    return None


def event_prices(ev: dict, home_en: str, away_en: str) -> dict:
    """Extract all available market prices from a single event."""
    found = {}
    for mkt in (ev.get('markets') or []):
        q = (mkt.get('question') or '').lower()
        outcomes = _parse_list_field(mkt.get('outcomes'))
        prices   = _parse_list_field(mkt.get('outcomePrices'))
        if not outcomes or len(outcomes) != len(prices):
            continue
        for market in POLY_MARKETS:
            if market in found:
                continue
            p = extract_outcome_price(market, q, outcomes, prices, home_en, away_en)
            if p is not None:
                found[market] = p
    return found


# ── Match fixtures against bulk events ───────────────────

def name_tokens(name: str) -> list[str]:
    """Return meaningful lowercase tokens from a team name."""
    stopwords = {'fc', 'sc', 'ac', 'united', 'city', 'the', 'afc', 'bv'}
    tokens = [t for t in name.lower().split() if len(t) >= 3 and t not in stopwords]
    # Always include the full lowercased name too
    tokens.append(name.lower())
    return list(dict.fromkeys(tokens))  # deduplicated


def match_score(title_lower: str, home_tokens: list, away_tokens: list) -> int:
    """Return match quality: 2=both teams found, 1=one team, 0=none."""
    home_hit = any(t in title_lower for t in home_tokens)
    away_hit = any(t in title_lower for t in away_tokens)
    return (2 if home_hit and away_hit else
            1 if home_hit or away_hit else 0)


def find_match_in_events(events: list, home: str, away: str) -> dict | None:
    """
    Find the best matching event for a home vs away fixture and extract prices.
    Returns structured result or None.
    """
    home_en = to_english(home)
    away_en = to_english(away)
    h_tokens = name_tokens(home_en)
    a_tokens = name_tokens(away_en)

    best_ev   = None
    best_score = 0

    for ev in events:
        title = (ev.get('title') or '').lower()
        sc = match_score(title, h_tokens, a_tokens)
        if sc > best_score:
            best_score = sc
            best_ev = ev

    if best_score < 2 or best_ev is None:
        return None  # need both teams in title

    prices = event_prices(best_ev, home_en, away_en)
    if not prices:
        return None

    slug = best_ev.get('slug') or ''
    url  = f"https://polymarket.com/event/{slug}" if slug else "https://polymarket.com/"
    return {
        'found':      True,
        'eventTitle': best_ev.get('title', ''),
        'eventUrl':   url,
        'markets':    prices,
    }


# ── Main ─────────────────────────────────────────────────

def main():
    # Load picks
    try:
        with open('picks_output.json', 'r', encoding='utf-8') as f:
            picks_list = json.load(f)
    except FileNotFoundError:
        print("⚠️  picks_output.json not found")
        out = {'fetched': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'matches': {}}
        with open('polymarket_prices.json', 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        return
    except json.JSONDecodeError as e:
        print(f"❌ picks_output.json parse error: {e}")
        return

    # Collect unique matches
    unique_matches: dict[str, tuple[str, str]] = {}
    for fx in picks_list:
        league = fx.get('league', '')
        if league not in POLY_LEAGUES:
            continue
        home = fx.get('home', '')
        away = fx.get('away', '')
        if not home or not away:
            continue
        has_poly_market = any(p.get('market') in POLY_MARKETS for p in (fx.get('picks') or []))
        if not has_poly_market:
            continue
        unique_matches[f"{home}|{away}"] = (home, away)

    print(f"🔍 {len(unique_matches)} fixtures to match")

    # Step 1: discover soccer tag IDs (paginate all tags)
    print("\n📌 Discovering soccer tags (all pages)...")
    tag_ids = get_soccer_tag_ids()
    print(f"  Found {len(tag_ids)} soccer tag(s)")

    # Step 2: bulk-fetch all soccer events via multiple strategies
    print("\n📥 Fetching soccer events from Polymarket...")
    all_events = fetch_all_soccer_events(tag_ids)
    print(f"  Total soccer events fetched: {len(all_events)}")

    if not all_events:
        print("⚠️  No events fetched — check API access")
        out = {
            'fetched': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'matches': {k: {'found': False, 'eventTitle': '', 'eventUrl': '', 'markets': {}}
                        for k in unique_matches}
        }
        with open('polymarket_prices.json', 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        return

    # Step 3: match fixtures against fetched events
    print(f"\n🔗 Matching {len(unique_matches)} fixtures against {len(all_events)} events...")
    results: dict[str, dict] = {}
    found_count = 0

    for key, (home, away) in unique_matches.items():
        result = find_match_in_events(all_events, home, away)
        if result:
            found_count += 1
            print(f"  ✅ {home} vs {away} → {result['eventTitle']}")
            results[key] = result
        else:
            results[key] = {'found': False, 'eventTitle': '', 'eventUrl': '', 'markets': {}}

    print(f"\n{'─'*60}")
    print(f"✅ {found_count}/{len(unique_matches)} matches found on Polymarket")

    out = {
        'fetched': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'matches': results,
    }
    with open('polymarket_prices.json', 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("💾 polymarket_prices.json saved")


if __name__ == '__main__':
    main()
