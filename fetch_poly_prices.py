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
import os
import re
import time
import unicodedata
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone, timedelta

# ── Markets we extract ────────────────────────────────────
POLY_MARKETS = {
    # Match result
    'Heimsieg', 'Auswärtssieg', 'Unentschieden',
    # Goals Over/Under (standard Polymarket lines)
    'Over 1.5 Tore', 'Over 2.5 Tore', 'Over 3.5 Tore',
    'Under 1.5 Tore', 'Under 2.5 Tore',
    # Both Teams to Score — Yes and No both available on Polymarket
    'Beide Teams treffen',
    'Beide Teams treffen: Nein',
    # Corners Over/Under (all pick-engine lines; extracted when Polymarket offers them)
    'Über 6.5 Ecken', 'Über 7.5 Ecken', 'Über 8.5 Ecken',
    'Über 9.5 Ecken', 'Über 10.5 Ecken', 'Über 11.5 Ecken',
    'Unter 6.5 Ecken', 'Unter 7.5 Ecken', 'Unter 8.5 Ecken', 'Unter 9.5 Ecken',
}

# ── Leagues covered on Polymarket ────────────────────────
POLY_LEAGUES = {'GER', 'ENG', 'ITA', 'ESP', 'FRA', 'NED', 'POR', 'TUR', 'GER2', 'SCO', 'ENG2'}

# ── WM 2026 team ID → English name (for Polymarket matching) ─────────────────
WM_TEAM_EN = {
    "ARG": "Argentina",   "AUS": "Australia",    "AUT": "Austria",
    "BEL": "Belgium",     "BIH": "Bosnia",        "BRA": "Brazil",
    "CAN": "Canada",      "CIV": "Ivory Coast",   "COD": "DR Congo",
    "COL": "Colombia",    "CPV": "Cape Verde",    "CRO": "Croatia",
    "CUW": "Curacao",     "CZE": "Czech Republic","DZA": "Algeria",
    "ECU": "Ecuador",     "EGY": "Egypt",         "ENG": "England",
    "ESP": "Spain",       "FRA": "France",        "GER": "Germany",
    "GHA": "Ghana",       "HTI": "Haiti",         "IRN": "Iran",
    "IRQ": "Iraq",        "JOR": "Jordan",        "JPN": "Japan",
    "KOR": "South Korea", "MAR": "Morocco",       "MEX": "Mexico",
    "NED": "Netherlands", "NOR": "Norway",        "NZL": "New Zealand",
    "PAN": "Panama",      "POR": "Portugal",      "PRY": "Paraguay",
    "QAT": "Qatar",       "SAU": "Saudi Arabia",  "SCO": "Scotland",
    "SEN": "Senegal",     "SUI": "Switzerland",   "SWE": "Sweden",
    "TUN": "Tunisia",     "TUR": "Turkey",        "URU": "Uruguay",
    "USA": "United States","UZB": "Uzbekistan",   "ZAF": "South Africa",
}

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

def api_get(url: str, retries: int = 3, silent_404: bool = False) -> list | dict | None:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
        'Accept': 'application/json',
    }
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                if not silent_404:
                    pass  # 404 = not found, normal for slug probes
                return None  # no point retrying a 404
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                print(f"  ❌ API error: {e}  url={url}")
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
        # Exclude settled/near-settled markets: < 2¢ or > 98¢ means outcome
        # is essentially resolved — showing stale prices would mislead the edge calc.
        return f if 0.02 <= f <= 0.98 else None
    except (TypeError, ValueError):
        return None


# ── Polymarket league slugs (frontend URL pattern) ───────
# URL: polymarket.com/sports/<league-slug>/<home3>-<away3>-<date>
LEAGUE_POLY_SLUG: dict[str, str] = {
    'ENG':  'epl',
    'ENG2': 'championship',
    'GER':  'bundesliga',
    'GER2': 'bundesliga-2',
    'ESP':  'laliga',
    'ITA':  'serie-a',
    'FRA':  'ligue-1',
    'NED':  'eredivisie',
    'POR':  'primeira-liga',
    'TUR':  'super-lig',
    'SCO':  'scottish-premiership',
}

_SLUG_DROP = re.compile(r'\b(fc|sc|ac|as|rc|bv|sk|cf|cd|ud|ss|us|sv|if|ik|vfl|vfb|tsv|tsg|bvb|rb|fk|nk|gd|gil|afc|fca|1\.|og|af|sbo)\b')

def _team_abbrev(name: str) -> str:
    """3-letter slug abbreviation matching Polymarket's pattern (vil, ars, bay …)."""
    s = name.lower()
    s = re.sub(r"[''ʼ]", '', s)                           # remove apostrophes
    s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')  # strip diacritics
    s = _SLUG_DROP.sub(' ', s).strip()                     # remove common FC/SC prefixes
    # Split, keep words that are NOT pure numbers (skip "1899", "05" etc.)
    parts = [p for p in re.split(r'[^a-z0-9]+', s)
             if len(p) >= 2 and not re.fullmatch(r'\d+', p)]
    return (parts[0][:3] if parts else re.sub(r'[^a-z]', '', name.lower())[:3])


def _normalize_date(raw: str) -> str:
    """Return ISO YYYY-MM-DD from any common date format (DD.MM.YYYY or YYYY-MM-DD)."""
    s = str(raw).strip()
    # Already ISO
    if re.match(r'^\d{4}-\d{2}-\d{2}', s):
        return s[:10]
    # German format DD.MM.YYYY or DD.MM.YY
    m = re.match(r'^(\d{1,2})\.(\d{1,2})\.(\d{4})', s)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    return s[:10]


def gamma_fetch_by_slug(slug: str) -> dict | None:
    """Fetch a single Gamma event by slug (GET /events/{slug}). 404 = silently None."""
    url = f'https://gamma-api.polymarket.com/events/{urllib.parse.quote(slug, safe="/-")}'
    data = api_get(url, silent_404=True)
    if not data:
        return None
    if isinstance(data, list):
        return data[0] if data else None
    if isinstance(data, dict) and data.get('id'):
        return data
    return None


def slug_fetch_event(home: str, away: str, date_str: str, league: str) -> dict | None:
    """
    Construct Polymarket event slug from league + team abbreviations + date.
    Tries both 'home-away' and 'away-home' orders, and 'more-markets' suffix.
    Pattern from: polymarket.com/sports/<leagueslug>/<h3>-<a3>-<date>
    """
    lg = LEAGUE_POLY_SLUG.get(league, '')
    if not lg:
        return None
    home_en = to_english(home)
    away_en = to_english(away)
    h3 = _team_abbrev(home_en)
    a3 = _team_abbrev(away_en)
    for slug in [
        f"{lg}/{h3}-{a3}-{date_str}",
        f"{lg}/{a3}-{h3}-{date_str}",                     # reversed order
        f"{lg}/{h3}-{a3}-{date_str}-more-markets",
    ]:
        ev = gamma_fetch_by_slug(slug)
        if ev:
            print(f"    ✅ slug hit: '{slug}' → '{ev.get('title')}'")
            return ev
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

# Extra tokens for teams whose names differ between our system and Polymarket titles.
# Key = our canonical English name (lowercase).
# Value = list of tokens that appear in Polymarket event titles for that team.
_POLY_EXTRA_TOKENS: dict[str, list[str]] = {
    'rennes':          ['rennais', 'stade rennais'],   # "Stade Rennais FC"
    'lyon':            ['lyonnais', 'olympique lyonnais'],  # "Olympique Lyonnais"
    'marseille':       ['olympique de marseille'],
    'nice':            ['ogc nice'],
    'monaco':          ['as monaco'],
    'paris fc':        ['paris'],
    'psg':             ['paris saint-germain', 'paris saint germain'],
    'atletico madrid': ['atletico de madrid', 'club atletico'],
    'barcelona':       ['fc barcelona', 'futbol club barcelona'],
    'real madrid':     ['real madrid cf'],
    'wolves':          ['wolverhampton', 'wolverhampton wanderers'],
    'gladbach':        ['monchengladbach', 'borussia monchengladbach', 'borussia m'],
    'koln':            ['cologne', '1. fc koln', 'fc koln'],
}


def name_tokens(name: str) -> list[str]:
    """
    Full name first (highest priority), then individual tokens, then Polymarket extras.
    'city' and 'united' are kept (NOT stopwords) so Manchester City ≠ Manchester United.
    """
    stopwords = {'fc', 'sc', 'ac', 'the', 'afc', 'bv', 'sk', 'cf', 'de', 'rcd'}
    tokens = [t for t in name.lower().split() if len(t) >= 3 and t not in stopwords]
    result = [name.lower()] + [t for t in tokens if t != name.lower()]
    # Add known alternative spellings used in Polymarket event titles
    extras = _POLY_EXTRA_TOKENS.get(name.lower(), [])
    result.extend(e for e in extras if e not in result)
    return list(dict.fromkeys(result))


# First words that are SHARED across multiple teams → matching on them alone is ambiguous.
# e.g. "Manchester United" vs "Manchester City" — "Manchester" alone isn't enough.
# Words NOT in this set are treated as unique identifiers (e.g. "Bayern", "Liverpool").
_AMBIGUOUS_FIRST_WORDS = {
    'real', 'manchester', 'inter', 'atletico', 'atletico', 'sporting',
    'dynamo', 'dinamo', 'lokomotiv', 'west', 'borussia', 'red', 'paris',
    'union', 'fortuna', 'olympique', 'olympiakos', 'olympiacos',
}


def _token_conflict(full_name: str, title: str) -> bool:
    """
    Returns True if a token-only match is likely the WRONG team.
    Handles 2-word teams that share a first word:
      "Manchester United" vs "Manchester City"
      "Real Madrid" vs "Real Sociedad" vs "Real Betis"
    DOES NOT fire for unique first-word teams like "Bayern Munich"
    where "Bayern" alone unambiguously identifies the team — even
    when the title uses "München" instead of "Munich".
    """
    if full_name in title:
        return False
    words = full_name.split()
    if len(words) == 2:
        first, second = words
        if first in title and second not in title:
            # Only block when the first word is known-ambiguous.
            # Unique identifiers (Bayern, Liverpool, Chelsea …) are safe alone.
            return first.lower() in _AMBIGUOUS_FIRST_WORDS
    return False


def _ascii_fold(s: str) -> str:
    """Strip diacritics: 'beşiktaş' → 'besiktas', 'fenerbahçe' → 'fenerbahce'."""
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')


def match_score(title_lower: str, home_tokens: list, away_tokens: list) -> int:
    """
    2 = both teams found, 1 = one team, 0 = none.
    home_tokens[0] / away_tokens[0] = full lowercased name.
    Also checks an ASCII-folded version of the title so that e.g.
    'besiktas' matches a title containing 'beşiktaş'.
    """
    home_full = home_tokens[0]
    away_full = away_tokens[0]
    title_ascii = _ascii_fold(title_lower)  # 'beşiktaş vs trabzonspor' → 'besiktas vs trabzonspor'

    def team_hit(full: str, tokens: list) -> bool:
        if full in title_lower or full in title_ascii:
            return True
        if _token_conflict(full, title_lower) and _token_conflict(full, title_ascii):
            return False
        return any(t in title_lower or t in title_ascii for t in tokens[1:])

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

    # ── BTTS: "Will both teams score?" / "Both Teams to Score?" ─────────────
    if market in ('Beide Teams treffen', 'Beide Teams treffen: Nein'):
        btts_kw = ('both teams', 'both score', 'btts', 'both team to score',
                   'both teams to score', 'will both')
        if not any(kw in q for kw in btts_kw):
            return None
        want_no = (market == 'Beide Teams treffen: Nein')
        y_idx = next((i for i, o in enumerate(outcomes) if str(o).lower() == 'yes'), -1)
        n_idx = next((i for i, o in enumerate(outcomes) if str(o).lower() == 'no'),  -1)
        idx = n_idx if want_no else y_idx
        return _safe_float(prices[idx]) if idx >= 0 else None

    # ── Goals Over/Under (1.5 / 2.5 / 3.5) ─────────────────────────────────
    # Market names: "Over 1.5 Tore", "Under 2.5 Tore", "Over 3.5 Tore", etc.
    goals_m = re.match(r'^(Over|Under)\s+(\d+\.5)\s+Tore$', market)
    if goals_m:
        direction = goals_m.group(1)   # 'Over' or 'Under'
        line      = goals_m.group(2)   # '1.5', '2.5', '3.5'
        # Question must reference the line or mention goals/goal
        if line not in q and 'goal' not in q:
            return None
        # For multi-line O/U questions the line itself must appear to avoid cross-market pollution
        if 'goal' in q and line not in q:
            return None
        y_idx = next((i for i, o in enumerate(outcomes) if str(o).lower() == 'yes'),   -1)
        n_idx = next((i for i, o in enumerate(outcomes) if str(o).lower() == 'no'),    -1)
        o_idx = next((i for i, o in enumerate(outcomes) if 'over'  in str(o).lower()), -1)
        u_idx = next((i for i, o in enumerate(outcomes) if 'under' in str(o).lower()), -1)
        idx = (y_idx if y_idx >= 0 else o_idx) if direction == 'Over' else (n_idx if n_idx >= 0 else u_idx)
        return _safe_float(prices[idx]) if idx >= 0 else None

    # ── Corners Over/Under ───────────────────────────────────────────────────
    # Market names: "Über 9.5 Ecken", "Unter 8.5 Ecken", etc.
    corners_m = re.match(r'^(Über|Unter)\s+(\d+\.5)\s+Ecken$', market)
    if corners_m:
        direction = corners_m.group(1)   # 'Über' or 'Unter'
        line      = corners_m.group(2)   # '6.5' … '11.5'
        # Question must mention corners and the specific line
        if 'corner' not in q or line not in q:
            return None
        y_idx = next((i for i, o in enumerate(outcomes) if str(o).lower() == 'yes'),   -1)
        n_idx = next((i for i, o in enumerate(outcomes) if str(o).lower() == 'no'),    -1)
        o_idx = next((i for i, o in enumerate(outcomes) if 'over'  in str(o).lower()), -1)
        u_idx = next((i for i, o in enumerate(outcomes) if 'under' in str(o).lower()), -1)
        idx = (y_idx if y_idx >= 0 else o_idx) if direction == 'Über' else (n_idx if n_idx >= 0 else u_idx)
        return _safe_float(prices[idx]) if idx >= 0 else None

    # 1X2 match winner — pass if question has relevant keywords OR outcomes contain team/draw
    # Relaxed check: some Polymarket markets use "Moneyline" or just the match title as question
    has_draw_outcome = any('draw' in str(o).lower() for o in outcomes)
    has_keywords = any(kw in q for kw in ('win', 'winner', 'match', 'beat', 'vs', 'v ', 'draw', 'moneyline'))
    if not has_keywords and not has_draw_outcome:
        return None

    home_tokens = [t for t in home_en.lower().split() if len(t) >= 3]
    away_tokens = [t for t in away_en.lower().split() if len(t) >= 3]

    # Helper: index of Yes outcome (binary markets use Yes/No instead of team names)
    yes_idx = next((i for i, o in enumerate(outcomes) if str(o).lower() == 'yes'), -1)

    def _binary_winner(q_str: str) -> str | None:
        """For 'Will X beat/win/defeat Y?' questions return 'home', 'away', or None."""
        import re
        m = re.search(r'\bwill\s+(.{2,40}?)\s+(?:beat|win\b|defeat)', q_str)
        if m:
            subject = m.group(1)
            if any(t in subject for t in home_tokens):
                return 'home'
            if any(t in subject for t in away_tokens):
                return 'away'
        return None

    if market == 'Heimsieg':
        # Try named outcome first ("Leeds United FC", "Home", etc.)
        idx = next((i for i, o in enumerate(outcomes)
                    if any(t in str(o).lower() for t in home_tokens)), -1)
        # Fallback: binary "Will [HomeTeam] beat/win?" → Yes = home win
        # Use subject-detection so "Will Barcelona beat Osasuna?" matches home only
        if idx < 0 and yes_idx >= 0 and _binary_winner(q) == 'home':
            idx = yes_idx
        return _safe_float(prices[idx]) if idx >= 0 else None

    if market == 'Auswärtssieg':
        idx = next((i for i, o in enumerate(outcomes)
                    if any(t in str(o).lower() for t in away_tokens)), -1)
        # Fallback: binary "Will [AwayTeam] beat/win?" → Yes = away win
        if idx < 0 and yes_idx >= 0 and _binary_winner(q) == 'away':
            idx = yes_idx
        return _safe_float(prices[idx]) if idx >= 0 else None

    if market == 'Unentschieden':
        # First try explicit "Draw" / "DRAW" outcome label (3-way moneyline markets)
        idx = next((i for i, o in enumerate(outcomes)
                    if 'draw' in str(o).lower()), -1)
        # Fallback: binary "Will [X] end in a draw?" → Yes
        # Don't require team tokens to be absent — draw questions often include both teams
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
                if os.environ.get('POLY_DEBUG'):
                    print(f"    [debug] {market} ← q='{question[:80]}' outcomes={outcomes} → {p:.2f}")

    # 1. Nested sub-markets (e.g. "More Markets" events)
    for mkt in (ev.get('markets') or []):
        q        = (mkt.get('question') or '').lower()
        outcomes = _parse_list_field(mkt.get('outcomes'))
        prices   = _parse_list_field(mkt.get('outcomePrices'))
        if outcomes and len(outcomes) == len(prices):
            _try(q, outcomes, prices)

    # 2. Event-level outcomes (simple single-market events or 1X2 winner events)
    # Always try event-level — "More Markets" events may not have 1X2 but a sibling event does
    ev_outcomes = _parse_list_field(ev.get('outcomes'))
    ev_prices   = _parse_list_field(ev.get('outcomePrices'))
    ev_q        = (ev.get('title') or ev.get('question') or '').lower()
    if ev_outcomes and len(ev_outcomes) == len(ev_prices):
        _try(ev_q, ev_outcomes, ev_prices)

    return found


RESULT_MARKETS = {'Heimsieg', 'Auswärtssieg', 'Unentschieden'}


def keyword_fetch_winner_events(home_en: str, away_en: str, home: str = '', away: str = '') -> list[dict]:
    """
    Targeted API call for a single fixture to find its 1X2 winner event.
    Used as fallback when the bulk tag-based fetch didn't include the plain
    winner event (they're often tagged differently from 'More Markets' events).
    Excludes 'More Markets' events from results.
    """
    keyword = f"{home_en} {away_en}"
    url = ('https://gamma-api.polymarket.com/events'
           + '?' + urllib.parse.urlencode({'keyword': keyword, 'active': 'true', 'limit': '20'}))
    data = api_get(url)
    events = data if isinstance(data, list) else (data or {}).get('events', []) if data else []

    # If the English name differs from the original (e.g. 'Besiktas' ≠ 'Beşiktaş'),
    # also try a keyword search with the original names — Polymarket may index by native spelling.
    if not events and (home_en != home or away_en != away):
        keyword2 = f"{home} {away}"
        url2 = ('https://gamma-api.polymarket.com/events'
                + '?' + urllib.parse.urlencode({'keyword': keyword2, 'active': 'true', 'limit': '20'}))
        data2 = api_get(url2)
        events = data2 if isinstance(data2, list) else (data2 or {}).get('events', []) if data2 else []

    # Exclude 'More Markets' events — we want the plain winner/moneyline event
    return [ev for ev in events if 'more market' not in (ev.get('title') or '').lower()]


def find_match_in_events(events: list, home: str, away: str,
                         date_str: str = '', league: str = '') -> dict | None:
    home_en  = to_english(home)
    away_en  = to_english(away)
    h_tokens = name_tokens(home_en)
    a_tokens = name_tokens(away_en)

    candidates = [ev for ev in events
                  if match_score((ev.get('title') or '').lower(), h_tokens, a_tokens) >= 2]

    # Prefer "More Markets" events (richer sub-market data) over simple events.
    # Tie-break: home team's full name must appear BEFORE "vs" in the title
    # (prevents e.g. "RCD Espanyol de Barcelona" matching when looking for "FC Barcelona").
    def _home_not_in_prefix(title: str, home_full: str) -> bool:
        vs_pos = title.find(' vs')
        prefix = title[:vs_pos] if vs_pos > 0 else title
        return home_full not in prefix

    if candidates:
        candidates.sort(key=lambda e: (
            'more market' not in (e.get('title') or '').lower(),
            len(e.get('markets') or []) == 0,
            _home_not_in_prefix((e.get('title') or '').lower(), h_tokens[0]),
        ))

    # Merge prices from ALL candidate events — different events may hold different markets
    # (e.g. "More Markets" events have goals markets, separate events have 1X2 winner markets)
    merged_prices: dict = {}
    first_ev = None
    for ev in candidates:
        prices = event_prices(ev, home_en, away_en)
        if prices:
            if first_ev is None:
                first_ev = ev
            for k, v in prices.items():
                if k not in merged_prices:  # first candidate wins per market
                    merged_prices[k] = v

    # Fallback: if 1X2 result markets still missing, do a targeted keyword search
    # for the winner event — bulk tag-fetch may have missed it (different tag assignment)
    missing_result = RESULT_MARKETS - set(merged_prices.keys())
    if missing_result:
        print(f"    [{home_en} vs {away_en}] 1X2 missing ({missing_result}) — keyword fallback …")
        extra_events = keyword_fetch_winner_events(home_en, away_en, home, away)
        for ev in extra_events:
            title = (ev.get('title') or '').lower()
            if match_score(title, h_tokens, a_tokens) < 2:
                continue
            prices = event_prices(ev, home_en, away_en)
            for k, v in prices.items():
                if k not in merged_prices:
                    merged_prices[k] = v
                    print(f"    [{home_en} vs {away_en}] ✅ keyword fallback found {k} from '{ev.get('title')}'")
            if first_ev is None and prices:
                first_ev = ev

    # Last-resort: slug-based fetch using Polymarket URL pattern
    # polymarket.com/sports/<leagueslug>/<h3>-<a3>-<date>
    if not merged_prices and date_str and league:
        print(f"    [{home_en} vs {away_en}] — slug fallback ({league}) …")
        slug_ev = slug_fetch_event(home, away, date_str, league)
        if slug_ev:
            prices = event_prices(slug_ev, home_en, away_en)
            for k, v in prices.items():
                merged_prices[k] = v
            if first_ev is None:
                first_ev = slug_ev

    print(f"    [{home_en} vs {away_en}] → merged markets: {list(merged_prices.keys())}")

    if not merged_prices:
        return None

    slug = first_ev.get('slug') or ''
    url  = f"https://polymarket.com/event/{slug}" if slug else "https://polymarket.com/"
    return {
        'found':      True,
        'eventTitle': first_ev.get('title', ''),
        'eventUrl':   url,
        'markets':    merged_prices,
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

    # Collect unique fixtures that need Polymarket pricing
    # Store (home, away, date_str, league) so we can use slug fallback
    unique_matches: dict[str, tuple[str, str, str, str]] = {}
    for fx in picks_list:
        league = fx.get('league', '')
        if league not in POLY_LEAGUES:
            continue
        home = fx.get('home', '')
        away = fx.get('away', '')
        if not home or not away:
            continue
        # Process ALL supported-league games regardless of current pick markets.
        # Picks are recomputed live by the browser engine and can differ from picks_output.json
        # (e.g. new odds unlock an Under 2.5 pick that wasn't there when picks_output was generated).
        # Filtering by pick-market causes stale "not found" cache entries for those games.
        # date_str: normalize to YYYY-MM-DD regardless of source format (DD.MM.YYYY or ISO)
        raw_date = fx.get('date') or fx.get('fixture_date') or fx.get('kickoff') or ''
        date_str = _normalize_date(raw_date) if raw_date else ''
        unique_matches[f"{home}|{away}"] = (home, away, date_str, league)

    # ── WM 2026: add fixtures with picks to unique_matches ───────────────────
    wm_added = 0
    try:
        with open('wm2026-data.json', 'r', encoding='utf-8') as f:
            wm_data = json.load(f)

        wm_picks = wm_data.get('picks', {})
        wm_groups = wm_data.get('groups', {})

        # Build fixture date lookup: "homeId-awayId" → "YYYY-MM-DD"
        fx_dates: dict[str, str] = {}
        for gdata in wm_groups.values():
            for fx in gdata.get('fixtures', []):
                h, a = fx.get('home', ''), fx.get('away', '')
                if h and a:
                    fx_dates[f"{h}-{a}"] = fx.get('date', '')

        for pick_key, picks in wm_picks.items():
            if not picks:
                continue
            # pick_key format: "A-1-MEX-ZAF" (group-matchday-homeId-awayId)
            parts = pick_key.split('-')
            if len(parts) < 4:
                continue
            home_id = parts[-2]
            away_id = parts[-1]
            home_en = WM_TEAM_EN.get(home_id, home_id)
            away_en = WM_TEAM_EN.get(away_id, away_id)
            date_str = fx_dates.get(f"{home_id}-{away_id}", '')
            match_key = f"{home_en}|{away_en}"
            if match_key not in unique_matches:
                unique_matches[match_key] = (home_en, away_en, date_str, 'WM2026')
                wm_added += 1

        print(f"  [WM2026] +{wm_added} fixtures mit Picks hinzugefügt")
    except FileNotFoundError:
        print("  [WM2026] wm2026-data.json nicht gefunden — übersprungen")
    except Exception as e:
        print(f"  [WM2026] Fehler beim Laden: {e}")

    print(f"🔍 {len(unique_matches)} fixtures to match (inkl. WM)")

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

    for key, (home, away, date_str, league) in unique_matches.items():
        result = find_match_in_events(all_events, home, away, date_str=date_str, league=league)
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

    # ── Poly Trader: update signal tracking ───────────────────────────────────
    try:
        update_trader_data(results, unique_matches)
    except Exception as e:
        import traceback
        print(f"⚠️  poly_trader_data update failed: {e}")
        traceback.print_exc()


# ═══════════════════════════════════════════════════════════════════════════════
# POLY TRADER — Signal Tracking
# Writes poly_trader_data.json with:
#   - Opening Poly price (first ever recorded per match-market)
#   - Price history (snapshot per run)
#   - Bookie line movement vs. Poly movement → signal detection
# ═══════════════════════════════════════════════════════════════════════════════

# Markets where we can compare Poly price to Pinnacle fair odds
# Maps Poly market name → (odds_open key, odds_current key)
TRADER_MARKET_MAP = {
    'Heimsieg':       ('pinn_hw_fair', 'pinn_hw_fair'),
    'Auswärtssieg':   ('pinn_aw_fair', 'pinn_aw_fair'),
    'Unentschieden':  ('pinn_dr_fair', 'pinn_dr_fair'),
    'Over 2.5 Tore':  ('o25_fair',     'o25_fair'),
    'Over 1.5 Tore':  (None,           None),   # no Pinnacle fair key → Poly-only tracking
    'Over 3.5 Tore':  (None,           None),
    'Beide Teams treffen': (None,       None),
}

# Minimum bookie move (pp) to flag as SHARP signal
SHARP_THRESHOLD_PP      = 5.0   # Min bookie line move (pp) to flag SHARP
CLV_THRESHOLD_PP        = 4.0   # Min gap Pinnacle-implied vs. Poly (pp) for CLV+
MIN_GAP_ACTIONABLE      = 2.0   # Gap must still be open ≥2pp for signal to be "actionable"
MIN_POLY_PRICE          = 15.0  # Filter ultra-low prices (thin liquidity, high spread)
MAX_POLY_PRICE          = 85.0  # Filter near-certainty prices (same reason)
MAX_DAYS_OUT            = 10    # Ignore matches >10 days out

# ── Buy-signal thresholds ────────────────────────────────────────────────────
# BUY_THRESHOLD_PP: gap ≥ this → Poly significantly underpriced vs Pinnacle → BUY
# WATCH_THRESHOLD_PP: gap ≥ this → Poly slightly underpriced / worth monitoring
# SKIP_THRESHOLD_PP: gap ≤ negative this → Poly overpriced → SKIP (or sell)
# MAX_PLAUSIBLE_GAP: gaps above this almost certainly indicate a bad contract mapping
# MIN_LIQ_TIER: only leagues with liq_tier ≤ this get BUY/WATCH signals (T1+T2 = top leagues)
BUY_THRESHOLD_PP        = 5.0   # Poly "Quote" clearly better than Pinnacle → BUY
WATCH_THRESHOLD_PP      = 2.0   # Poly close to fair → WATCH
SKIP_THRESHOLD_PP       = 2.0   # Poly overpriced → SKIP
MAX_PLAUSIBLE_GAP       = 20.0  # >20pp gap = almost certainly bad contract mapping → suspicious
MIN_LIQ_TIER_SIGNAL     = 2     # Only T1 (top-5 leagues) + T2 get buy signals; T3 = monitor only


def _implied(fair_odds: float | None) -> float | None:
    """Convert decimal fair odds to implied probability %."""
    if fair_odds and fair_odds > 1:
        return round(100.0 / fair_odds, 2)
    return None


def update_trader_data(poly_results: dict, unique_matches: dict):
    """
    Load poly_trader_data.json (or start fresh), then for every match-market
    that has a Poly price update the signal tracking and save back.
    """
    now_ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    # Load existing trader data
    try:
        with open('poly_trader_data.json', 'r', encoding='utf-8') as f:
            trader = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        trader = {'updated': now_ts, 'candidates': {}}

    # Load prematch data for bookie odds (club leagues)
    try:
        with open('prematch-data.json', 'r', encoding='utf-8') as f:
            raw_pm = json.load(f)
        pm_fixtures = raw_pm if isinstance(raw_pm, list) else raw_pm.get('fixtures', [])
    except Exception:
        pm_fixtures = []

    # Build prematch lookup: "home|away" → fixture
    pm_idx: dict[str, dict] = {}
    for fx in pm_fixtures:
        h = fx.get('homeTeamName') or fx.get('home', '')
        a = fx.get('awayTeamName') or fx.get('away', '')
        if h and a:
            pm_idx[f"{h}|{a}"] = fx

    # Load WM 2026 odds for Pinnacle-implied probabilities
    wm_odds_idx: dict[str, dict] = {}   # "HomeEN|AwayEN" → {pinn_hw_fair, pinn_dr_fair, pinn_aw_fair}
    try:
        with open('wm2026-data.json', 'r', encoding='utf-8') as f:
            _wmd = json.load(f)
        for odds_key, odds in _wmd.get('odds', {}).items():
            parts = odds_key.split('-')
            if len(parts) != 2:
                continue
            h_en = WM_TEAM_EN.get(parts[0], parts[0])
            a_en = WM_TEAM_EN.get(parts[1], parts[1])
            hw, dr, aw = odds.get('hw'), odds.get('dr'), odds.get('aw')
            # 19.07.2026 — Platzhalter-Quoten-Gate (Legacy-Match-Pages): NUR echte Märkte de-viggen,
            # sonst landet eine Fake-Fair in pick-engine.js / generate_match_pages. Eine Quelle:
            # odds_plausibility (Remis ≥1.50, Overround 1.00-1.30). Dieselbe Bug-Klasse wie 13.07.
            from odds_plausibility import plausible_1x2 as _plausible_1x2
            if hw and dr and aw and _plausible_1x2(hw, dr, aw):
                # Devig: compute Pinnacle fair odds (remove ~3-4% margin)
                margin = 1/hw + 1/dr + 1/aw
                wm_odds_idx[f"{h_en}|{a_en}"] = {
                    "pinn_hw_fair": round(hw * margin, 3),
                    "pinn_dr_fair": round(dr * margin, 3),
                    "pinn_aw_fair": round(aw * margin, 3),
                }
    except Exception:
        pass

    candidates = trader.get('candidates', {})
    today = datetime.now(timezone.utc).date()
    updated_count = 0

    for match_key, poly_data in poly_results.items():
        if not poly_data.get('found'):
            continue
        markets = poly_data.get('markets', {})
        if not markets:
            continue

        meta = unique_matches.get(match_key, ())
        if len(meta) < 4:
            continue
        home, away, date_str, league = meta

        # Parse kickoff date
        kickoff_date = None
        try:
            kickoff_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except Exception:
            pass

        days_out = (kickoff_date - today).days if kickoff_date else 999
        # Allow yesterday (-1) to freeze close prices; filter out further past & far future
        if days_out < -1 or days_out > MAX_DAYS_OUT:
            continue

        # Get prematch fixture for bookie odds
        pm_fx = pm_idx.get(match_key) or pm_idx.get(f"{home}|{away}")
        odds_open = (pm_fx.get('odds_open') or {}) if pm_fx else {}
        odds_cur  = (pm_fx.get('odds')      or {}) if pm_fx else {}

        # WM 2026: inject Pinnacle fair odds when no prematch-data.json entry
        if league == 'WM2026' and not pm_fx:
            wm_fair = wm_odds_idx.get(match_key) or wm_odds_idx.get(f"{home}|{away}")
            if wm_fair:
                # Use current Pinnacle odds as both open and current (no open history yet)
                odds_open = wm_fair
                odds_cur  = wm_fair

        for market_name, poly_price in markets.items():
            if market_name not in TRADER_MARKET_MAP:
                continue
            if not isinstance(poly_price, (int, float)):
                continue

            open_key, cur_key = TRADER_MARKET_MAP[market_name]
            candidate_key = f"{match_key}|{market_name}"

            # Bookie implied probabilities
            bookie_open_impl = _implied(odds_open.get(open_key)) if open_key else None
            bookie_cur_impl  = _implied(odds_cur.get(cur_key))   if cur_key  else None
            bookie_move_pp   = None
            if bookie_open_impl is not None and bookie_cur_impl is not None:
                bookie_move_pp = round(bookie_cur_impl - bookie_open_impl, 2)

            poly_pct = round(poly_price * 100, 2)  # convert 0-1 → 0-100

            # Existing candidate or new?
            existing = candidates.get(candidate_key, {})
            if existing:
                # Preserve opening price
                poly_open     = existing['poly_open']
                poly_open_ts  = existing['poly_open_ts']
                # Append to price history (keep last 48 snapshots ≈ 2 days at hourly)
                history = existing.get('price_history', [])
                history.append({'ts': now_ts, 'pct': poly_pct})
                if len(history) > 48:
                    history = history[-48:]
            else:
                # First time seeing this match-market
                poly_open    = poly_pct
                poly_open_ts = now_ts
                history      = [{'ts': now_ts, 'pct': poly_pct}]

            poly_delta_pp = round(poly_pct - poly_open, 2)

            # ── Close prices: freeze on kickoff day (days_out ≤ 0) ──────────────
            poly_close    = existing.get('poly_close')
            bookie_close  = existing.get('bookie_close')
            if days_out <= 0:
                if poly_close is None:
                    poly_close = poly_pct          # freeze last known Poly price
                if bookie_close is None:
                    bookie_close = bookie_cur_impl  # freeze last known Bookie price

            # ── Remaining gap: Pinnacle current implied vs. Poly current price ──
            # Positive gap = Pinnacle thinks outcome MORE likely than Poly → Poly underpriced → BUY
            # Negative gap = Poly thinks outcome MORE likely than Pinnacle → Poly overpriced → SKIP
            gap_pp = None
            if bookie_cur_impl is not None:
                gap_pp = round(bookie_cur_impl - poly_pct, 2)

            # ── League liquidity tier ─────────────────────────────────────────
            # Tier 1 = most liquid on Poly, Tier 3 = thinnest
            LIQ_TIER = {'ENG': 1, 'ESP': 1, 'GER': 1, 'ITA': 1, 'FRA': 1,
                        'NED': 2, 'POR': 2, 'GER2': 2, 'ENG2': 2,
                        'TUR': 3, 'SCO': 3}
            liq_tier = LIQ_TIER.get(league, 2)

            # ── Suspicious gap check ──────────────────────────────────────────
            # Gaps > MAX_PLAUSIBLE_GAP pp almost certainly indicate a bad Polymarket
            # contract mapping (wrong game matched) — not a real arbitrage opportunity.
            # These are flagged but NOT blocked from storage (useful for debugging mapping).
            suspicious_gap = gap_pp is not None and abs(gap_pp) > MAX_PLAUSIBLE_GAP

            # ── Buy signal (primary action label) ────────────────────────────
            # Strategy: compare Poly implied probability vs Pinnacle fair price.
            # When Poly "Quote" (implied odds) is HIGHER than Pinnacle (= Poly price lower),
            # it means Poly is underpriced relative to sharp money → BUY.
            # Prerequisite: enough liquidity (liq_tier ≤ MIN_LIQ_TIER_SIGNAL) AND
            #   plausible gap (not suspicious) AND Poly price in liquid range AND future match.
            in_liquid_range = MIN_POLY_PRICE <= poly_pct <= MAX_POLY_PRICE
            buy_prereq = (
                bookie_cur_impl is not None   # need Pinnacle comparison
                and not suspicious_gap         # gap must be plausible
                and liq_tier <= MIN_LIQ_TIER_SIGNAL  # T1 or T2 league only
                and in_liquid_range            # Poly price in 15–85% range
                and days_out >= 0              # match is still upcoming
            )
            buy_signal = None
            if buy_prereq:
                if gap_pp >= BUY_THRESHOLD_PP:
                    buy_signal = 'BUY'    # Poly clearly underpriced → buy now
                elif gap_pp >= WATCH_THRESHOLD_PP:
                    buy_signal = 'WATCH'  # Poly slightly underpriced → monitor
                elif gap_pp <= -SKIP_THRESHOLD_PP:
                    buy_signal = 'SKIP'   # Poly overpriced → don't buy / consider NO

            # ── Trade direction ───────────────────────────────────────────────
            # bookie_move_pp = bookie_cur_impl - bookie_open_impl
            # Positive = implied prob rose = odds shortened = outcome more likely = BUY_YES
            # Negative = implied prob fell = odds lengthened = outcome less likely = BUY_NO
            trade_direction = None
            if bookie_move_pp is not None and abs(bookie_move_pp) >= SHARP_THRESHOLD_PP:
                trade_direction = 'BUY_YES' if bookie_move_pp > 0 else 'BUY_NO'

            # ── Legacy signal detection (kept for SHARP/CLV+ badges) ─────────
            signal = None
            signal_strength = 0.0
            signal_detail   = []

            gap_still_open = gap_pp is not None and abs(gap_pp) >= MIN_GAP_ACTIONABLE
            is_sharp = (bookie_move_pp is not None
                        and abs(bookie_move_pp) >= SHARP_THRESHOLD_PP
                        and gap_still_open
                        and not suspicious_gap)
            if is_sharp:
                signal_strength = max(signal_strength, abs(bookie_move_pp))
                signal_detail.append(f"Bookie {bookie_move_pp:+.1f}pp, Gap {gap_pp:+.1f}pp offen")
                signal = 'SHARP'

            is_clv = (gap_pp is not None and gap_pp >= CLV_THRESHOLD_PP and not suspicious_gap)
            if is_clv:
                signal_strength = max(signal_strength, abs(gap_pp))
                signal_detail.append(f"CLV gap {gap_pp:+.1f}pp")
                signal = 'BOTH' if is_sharp else 'CLV+'

            # ── Actionability: aligned with buy_signal ─────────────────────────
            is_actionable = (buy_signal == 'BUY')

            # ── Composite score (for ranking) ─────────────────────────────────
            bm_abs = abs(bookie_move_pp) if bookie_move_pp is not None else 0.0
            gap_abs = abs(gap_pp) if gap_pp is not None else 0.0
            signal_score = round(bm_abs * 0.6 + gap_abs * 0.4, 2)

            # ── Simulated P&L (€5 stake, sell at kickoff / mark-to-market) ────
            OBS_STAKE    = 5.0
            obs_entry    = existing.get('obs_entry', poly_open)
            eff_dir      = trade_direction
            if eff_dir is None and gap_pp is not None:
                eff_dir = 'BUY_YES' if gap_pp > 0 else 'BUY_NO'
            exit_pct     = (poly_close if poly_close is not None else poly_pct) / 100.0
            entry_pct_f  = obs_entry / 100.0 if obs_entry is not None else None

            obs_pnl_eur = None
            obs_pnl_pp  = round(poly_pct - obs_entry, 2) if obs_entry is not None else poly_delta_pp
            if entry_pct_f and eff_dir:
                if eff_dir == 'BUY_YES' and entry_pct_f > 0:
                    obs_pnl_eur = round(OBS_STAKE * (exit_pct - entry_pct_f) / entry_pct_f, 2)
                elif eff_dir == 'BUY_NO':
                    denom = 1.0 - entry_pct_f
                    if denom > 0:
                        obs_pnl_eur = round(OBS_STAKE * (entry_pct_f - exit_pct) / denom, 2)

            candidates[candidate_key] = {
                'home':             home,
                'away':             away,
                'league':           league,
                'liq_tier':         liq_tier,
                'kickoffDate':      date_str,
                'daysOut':          days_out,
                'market':           market_name,
                'eventUrl':         poly_data.get('eventUrl', ''),
                # Bookie
                'bookie_open_impl': bookie_open_impl,
                'bookie_cur_impl':  bookie_cur_impl,
                'bookie_close':     bookie_close,
                'bookie_move_pp':   bookie_move_pp,
                # Poly
                'poly_open':        poly_open,
                'poly_open_ts':     poly_open_ts,
                'poly_cur':         poly_pct,
                'poly_cur_ts':      now_ts,
                'poly_close':       poly_close,
                'poly_delta_pp':    poly_delta_pp,
                # Gap & direction
                'gap_pp':           gap_pp,
                'trade_direction':  trade_direction,
                # ── Primary action signal ────────────────────────────────────
                # buy_signal: 'BUY' | 'WATCH' | 'SKIP' | None
                #   BUY  = Poly quote > Pinnacle (underpriced ≥ BUY_THRESHOLD_PP), liquid league
                #   WATCH = gap ≥ WATCH_THRESHOLD_PP but < BUY_THRESHOLD_PP
                #   SKIP = Poly overpriced vs Pinnacle (gap ≤ −SKIP_THRESHOLD_PP)
                #   None = no Pinnacle comparison, T3 league, or outside Poly liquid range
                'buy_signal':       buy_signal,
                'suspicious_gap':   suspicious_gap,  # True = gap >20pp = likely bad mapping
                # ── Legacy signals (SHARP / CLV+ / BOTH) ────────────────────
                'signal':           signal,
                'signal_strength':  signal_strength,
                'signal_score':     signal_score,
                'signal_detail':    ', '.join(signal_detail),
                'is_actionable':    is_actionable,
                # Tracking
                'first_seen_ts':    existing.get('first_seen_ts', now_ts),
                'price_history':    history,
                # Observer P&L (€5 stake, sell at kickoff / mark-to-market)
                'obs_entry':        obs_entry,
                'obs_pnl_pp':       obs_pnl_pp,
                'obs_pnl_eur':      obs_pnl_eur,
                'obs_closed':       poly_close is not None,  # True = position closed at kickoff
            }
            updated_count += 1

    # Clean up candidates for past matches (>2 days after kickoff)
    cutoff = today - timedelta(days=2)
    to_remove = []
    for k, c in candidates.items():
        try:
            kd = datetime.strptime(c.get('kickoffDate', ''), '%Y-%m-%d').date()
            if kd < cutoff:
                to_remove.append(k)
        except Exception:
            pass
    for k in to_remove:
        del candidates[k]

    trader['updated']    = now_ts
    trader['candidates'] = candidates

    with open('poly_trader_data.json', 'w', encoding='utf-8') as f:
        json.dump(trader, f, ensure_ascii=False, indent=2)

    print(f"📊 poly_trader_data.json — {updated_count} candidate-markets updated, "
          f"{len(to_remove)} expired entries removed")


if __name__ == '__main__':
    main()
