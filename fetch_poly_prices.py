#!/usr/bin/env python3
"""
fetch_poly_prices.py — Server-side Polymarket price fetcher
Runs in GitHub Actions (no CORS restrictions).

API used: Gamma API  https://gamma-api.polymarket.com
  GET /sports           → tag IDs per sport (no need to scan 6,125 tags)
  GET /events/keyset    → cursor-based pagination, 500/page, with:
                            tag_id=<id>
                            closed=false       (skip settled markets)
                            end_date_min=<ISO> (skip old past matches)
                            limit=500

Reads  : picks_output.json
Writes : polymarket_prices.json
"""

import json
import re
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone, timedelta

# ── Markets we extract ────────────────────────────────────
POLY_MARKETS = {'Heimsieg', 'Auswärtssieg', 'Unentschieden', 'Over 2.5 Tore', 'Under 2.5 Tore'}

# ── Leagues covered on Polymarket ────────────────────────
POLY_LEAGUES = {'GER', 'ENG', 'ITA', 'ESP', 'FRA', 'NED', 'POR', 'TUR', 'GER2', 'SCO', 'ENG2'}

# ── German / local → English team name map ───────────────
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
    'Levante':                  'Levante',
    'Paris Saint-Germain':      'Paris Saint-Germain',
    'Paris Saint Germain':      'Paris Saint-Germain',
    'PSG':                      'Paris Saint-Germain',
    'Marseille':                'Marseille',
    'Monaco':                   'Monaco',
    'RC Lens':                  'Lens',
    'Lille':                    'Lille',
    'Lyon':                     'Lyon',
    'OGC Nice':                 'Nice',
    'Stade Rennais':            'Rennes',
    'Rennes':                   'Rennes',
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
    'Paris FC':                 'Paris FC',
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
    'Başakşehir':               'Basaksehir',
    'Basaksehir':               'Basaksehir',
    'Gaziantep FK':             'Gaziantep',
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


# ── HTTP helper ───────────────────────────────────────────

def api_get(url: str, retries: int = 3) -> list | dict | None:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
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
                print(f"  ❌ API error: {e}  url={url}")
    return None


def _extract_list(data) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ('events', 'data', 'markets', 'results', 'items'):
            if key in data and isinstance(data[key], list):
                return data[key]
    return []


def _parse_list_field(val) -> list:
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            r = json.loads(val)
            return r if isinstance(r, list) else []
        except (json.JSONDecodeError, ValueError):
            return []
    return []


def _safe_float(val) -> float | None:
    try:
        f = float(val)
        return f if 0 < f < 1 else None  # exclude exactly 0 and 1 (settled)
    except (TypeError, ValueError):
        return None


# ── Step 1: get soccer tag IDs via /sports ────────────────

SOCCER_SPORT_KEYWORDS = {
    'soccer', 'football', 'epl', 'bundesliga', 'serie a', 'la liga', 'laliga',
    'ligue', 'premier league', 'eredivisie', 'primeira', 'scottish',
    'championship', 'calcio', 'süper lig', 'super lig',
}
SOCCER_EXCLUDE_KEYWORDS = {
    'rugby', 'cricket', 'american football', 'nfl', 'nba', 'mlb', 'nhl',
    'tennis', 'golf', 'mma', 'boxing', 'college football', 'formula',
    'cycling', 'motor', 'flag football', 'poker', 'chess',
}


def get_soccer_tag_ids_from_sports() -> list[str]:
    """
    Call GET /sports — returns sport objects with tag IDs per sport.
    Much faster than scanning all 6,125 tags.
    """
    data = api_get('https://gamma-api.polymarket.com/sports')
    sports = _extract_list(data) if data else []
    if not sports:
        print("  ⚠️  /sports returned nothing — falling back to tag scan")
        return []

    tag_ids = []
    for sp in sports:
        sport_name = (sp.get('sport') or '').lower()
        tags_str   = sp.get('tags') or ''  # comma-separated tag IDs

        # Exclude non-soccer sports
        if any(kw in sport_name for kw in SOCCER_EXCLUDE_KEYWORDS):
            continue
        if not any(kw in sport_name for kw in SOCCER_SPORT_KEYWORDS):
            continue

        for tid in str(tags_str).split(','):
            tid = tid.strip()
            if tid and tid not in tag_ids:
                tag_ids.append(tid)
                print(f"  [sport] {sport_name!r} → tag_id={tid}")

    return tag_ids


# ── Step 2: fetch events via /events/keyset ───────────────

def fetch_events_for_tag(tag_id: str, end_date_min: str) -> list[dict]:
    """
    Cursor-based pagination via /events/keyset.
    Uses correct snake_case param names (end_date_min, closed).
    Returns up to a few hundred events per tag — much faster than offset.
    """
    base = 'https://gamma-api.polymarket.com/events/keyset'
    params = {
        'tag_id':       tag_id,
        'closed':       'false',     # skip settled/resolved markets
        'end_date_min': end_date_min,
        'limit':        '500',
        'order':        'endDate',
        'ascending':    'true',      # soonest games first
    }

    events: list[dict] = []
    after_cursor = None

    while True:
        if after_cursor:
            params['after_cursor'] = after_cursor
        elif 'after_cursor' in params:
            del params['after_cursor']

        url = base + '?' + urllib.parse.urlencode(params)
        data = api_get(url)
        if not data or not isinstance(data, dict):
            break

        batch = data.get('events') or []
        next_cursor = data.get('next_cursor')

        events.extend(batch)
        print(f"  [tag={tag_id}] +{len(batch)} events (cursor={'...' if after_cursor else 'start'})")

        if not next_cursor or len(batch) == 0:
            break

        after_cursor = next_cursor
        time.sleep(0.1)

    return events


def fetch_all_soccer_events(tag_ids: list[str], end_date_min: str) -> list[dict]:
    """Fetch and deduplicate all soccer events across all tags."""
    seen: dict[str, dict] = {}  # id/slug → event

    for tid in tag_ids:
        evs = fetch_events_for_tag(tid, end_date_min)
        new = 0
        for ev in evs:
            key = str(ev.get('id') or ev.get('slug') or id(ev))
            if key not in seen:
                seen[key] = ev
                new += 1
        if new:
            sample = [ev.get('title', '')[:50] for ev in evs[:2]]
            print(f"  [tag={tid}] +{new} new (total={len(seen)}) — e.g. {sample}")
        else:
            print(f"  [tag={tid}] 0 new events in date window")

    return list(seen.values())


# ── Step 3: match fixtures to events ─────────────────────

def name_tokens(name: str) -> list[str]:
    """
    Full name first (highest priority), then individual tokens.
    'city' and 'united' are kept (NOT stopwords) so Manchester City ≠ Manchester United.
    """
    stopwords = {'fc', 'sc', 'ac', 'the', 'afc', 'bv', 'sk', 'cf', 'de', 'rcd'}
    tokens = [t for t in name.lower().split() if len(t) >= 3 and t not in stopwords]
    result = [name.lower()] + [t for t in tokens if t != name.lower()]
    return list(dict.fromkeys(result))


def _token_conflict(full_name: str, title: str) -> bool:
    """
    Returns True if a token-only match is likely the WRONG team.
    Handles 2-word teams that share a first word:
      "Manchester United" vs "Manchester City"
      "Real Madrid" vs "Real Sociedad" vs "Real Betis"
    """
    if full_name in title:
        return False
    words = full_name.split()
    if len(words) == 2:
        first, second = words
        if first in title and second not in title:
            return True
    return False


def match_score(title_lower: str, home_tokens: list, away_tokens: list) -> int:
    """
    2 = both teams found, 1 = one team, 0 = none.
    home_tokens[0] / away_tokens[0] = full lowercased name.
    """
    home_full = home_tokens[0]
    away_full = away_tokens[0]

    def team_hit(full: str, tokens: list) -> bool:
        if full in title_lower:
            return True
        if _token_conflict(full, title_lower):
            return False
        return any(t in title_lower for t in tokens[1:])

    home_hit = team_hit(home_full, home_tokens)
    away_hit = team_hit(away_full, away_tokens)
    return 2 if home_hit and away_hit else 1 if home_hit or away_hit else 0


# ── Step 4: extract prices from matched event ─────────────

def _parse_list_field(val) -> list:
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            r = json.loads(val)
            return r if isinstance(r, list) else []
        except (json.JSONDecodeError, ValueError):
            return []
    return []


def extract_outcome_price(market: str, question: str, outcomes: list,
                          prices: list, home_en: str, away_en: str) -> float | None:
    q = question.lower()
    is_goals = '2.5' in market

    if is_goals:
        if '2.5' not in q and 'goal' not in q:
            return None
        y_idx = next((i for i, o in enumerate(outcomes) if str(o).lower() == 'yes'), -1)
        n_idx = next((i for i, o in enumerate(outcomes) if str(o).lower() == 'no'),  -1)
        o_idx = next((i for i, o in enumerate(outcomes) if 'over'  in str(o).lower()), -1)
        u_idx = next((i for i, o in enumerate(outcomes) if 'under' in str(o).lower()), -1)
        if market.startswith('Over'):
            idx = y_idx if y_idx >= 0 else o_idx
        else:
            idx = n_idx if n_idx >= 0 else u_idx
        return _safe_float(prices[idx]) if idx >= 0 else None

    # 1X2 match winner
    if not any(kw in q for kw in ('win', 'winner', 'match', 'beat', 'vs', 'v ', 'draw')):
        return None

    home_tokens = [t for t in home_en.lower().split() if len(t) >= 3]
    away_tokens = [t for t in away_en.lower().split() if len(t) >= 3]

    # Helper: index of Yes outcome (binary markets use Yes/No instead of team names)
    yes_idx = next((i for i, o in enumerate(outcomes) if str(o).lower() == 'yes'), -1)

    if market == 'Heimsieg':
        # Try named outcome first ("Leeds United FC", "Home", etc.)
        idx = next((i for i, o in enumerate(outcomes)
                    if any(t in str(o).lower() for t in home_tokens)), -1)
        # Fallback: binary "Will [HomeTeam] win?" → Yes = home win
        if idx < 0 and yes_idx >= 0 and any(t in q for t in home_tokens):
            idx = yes_idx
        return _safe_float(prices[idx]) if idx >= 0 else None

    if market == 'Auswärtssieg':
        idx = next((i for i, o in enumerate(outcomes)
                    if any(t in str(o).lower() for t in away_tokens)), -1)
        if idx < 0 and yes_idx >= 0 and any(t in q for t in away_tokens):
            idx = yes_idx
        return _safe_float(prices[idx]) if idx >= 0 else None

    if market == 'Unentschieden':
        idx = next((i for i, o in enumerate(outcomes)
                    if 'draw' in str(o).lower()), -1)
        if idx < 0 and yes_idx >= 0 and 'draw' in q:
            idx = yes_idx
        return _safe_float(prices[idx]) if idx >= 0 else None

    return None


def event_prices(ev: dict, home_en: str, away_en: str) -> dict:
    """Extract market prices — checks nested markets AND event-level outcomes."""
    found: dict = {}

    def _try(question: str, outcomes: list, prices: list):
        for market in POLY_MARKETS:
            if market in found:
                continue
            p = extract_outcome_price(market, question, outcomes, prices, home_en, away_en)
            if p is not None:
                found[market] = p

    # 1. Nested sub-markets (e.g. "More Markets" events)
    for mkt in (ev.get('markets') or []):
        q        = (mkt.get('question') or '').lower()
        outcomes = _parse_list_field(mkt.get('outcomes'))
        prices   = _parse_list_field(mkt.get('outcomePrices'))
        if outcomes and len(outcomes) == len(prices):
            _try(q, outcomes, prices)

    # 2. Event-level outcomes (simple single-market events)
    if not found:
        ev_outcomes = _parse_list_field(ev.get('outcomes'))
        ev_prices   = _parse_list_field(ev.get('outcomePrices'))
        ev_q        = (ev.get('title') or ev.get('question') or '').lower()
        if ev_outcomes and len(ev_outcomes) == len(ev_prices):
            _try(ev_q, ev_outcomes, ev_prices)

    return found


def find_match_in_events(events: list, home: str, away: str) -> dict | None:
    home_en  = to_english(home)
    away_en  = to_english(away)
    h_tokens = name_tokens(home_en)
    a_tokens = name_tokens(away_en)

    candidates = [ev for ev in events
                  if match_score((ev.get('title') or '').lower(), h_tokens, a_tokens) >= 2]

    if not candidates:
        return None

    # Prefer "More Markets" events (richer sub-market data) over simple events.
    # Tie-break: home team's full name must appear BEFORE "vs" in the title
    # (prevents e.g. "RCD Espanyol de Barcelona" matching when looking for "FC Barcelona").
    def _home_not_in_prefix(title: str, home_full: str) -> bool:
        vs_pos = title.find(' vs')
        prefix = title[:vs_pos] if vs_pos > 0 else title
        return home_full not in prefix

    candidates.sort(key=lambda e: (
        'more market' not in (e.get('title') or '').lower(),
        len(e.get('markets') or []) == 0,
        _home_not_in_prefix((e.get('title') or '').lower(), h_tokens[0]),
    ))

    for ev in candidates:
        prices = event_prices(ev, home_en, away_en)
        if prices:
            slug = ev.get('slug') or ''
            url  = f"https://polymarket.com/event/{slug}" if slug else "https://polymarket.com/"
            return {
                'found':      True,
                'eventTitle': ev.get('title', ''),
                'eventUrl':   url,
                'markets':    prices,
            }

    return None


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

    # Collect unique fixtures that need Polymarket pricing
    unique_matches: dict[str, tuple[str, str]] = {}
    for fx in picks_list:
        league = fx.get('league', '')
        if league not in POLY_LEAGUES:
            continue
        home = fx.get('home', '')
        away = fx.get('away', '')
        if not home or not away:
            continue
        has_poly = any(p.get('market') in POLY_MARKETS for p in (fx.get('picks') or []))
        if not has_poly:
            continue
        unique_matches[f"{home}|{away}"] = (home, away)

    print(f"🔍 {len(unique_matches)} fixtures to match")

    # end_date_min: only events that haven't ended yet (allow 1 day grace)
    today = datetime.now(timezone.utc).date()
    end_date_min = (today - timedelta(days=1)).strftime('%Y-%m-%dT00:00:00Z')
    print(f"📅 end_date_min = {end_date_min}")

    # Step 1: get soccer tag IDs from /sports
    print("\n📌 Fetching soccer tag IDs from /sports...")
    tag_ids = get_soccer_tag_ids_from_sports()
    if not tag_ids:
        print("  ⚠️  No tag IDs from /sports — aborting")
        return
    print(f"  Found {len(tag_ids)} soccer tag(s)")

    # Step 2: fetch events
    print(f"\n📥 Fetching events (closed=false, end_date_min={end_date_min})...")
    all_events = fetch_all_soccer_events(tag_ids, end_date_min)
    print(f"  Total unique soccer events: {len(all_events)}")

    if not all_events:
        print("⚠️  No events — check API or date window")
        out = {
            'fetched': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'matches': {k: {'found': False, 'eventTitle': '', 'eventUrl': '', 'markets': {}}
                        for k in unique_matches}
        }
        with open('polymarket_prices.json', 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        return

    # Step 3: match fixtures
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
