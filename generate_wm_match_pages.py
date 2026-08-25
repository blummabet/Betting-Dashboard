#!/usr/bin/env python3
"""
generate_wm_match_pages.py
Reads wm2026-data.json and writes one JSON per fixture to matches/data/wm-{slug}.json.

Slug format: wm-{home_lower}-vs-{away_lower}-{date}
e.g.  wm-mex-vs-zaf-2026-06-11

Run: python3 generate_wm_match_pages.py
"""

import json
import os
from datetime import datetime, timedelta, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "matches", "data")
os.makedirs(DATA_DIR, exist_ok=True)

# Dataset-Modus (Single Source: cocobet_dataset): Liga → Liga-Match-Pages (liga-{slug}.json +
# liga-index.json), gleiches Template. WM-only Quellen (poly/props/smartmoney) für Liga =
# nicht-existente Pfade → load_json gibt {} → leer.
import cocobet_dataset as D
_IS_LIGA     = D.is_liga()
# 13.07.2026 (MLS-Audit) — 🔴 D.is_liga() ist auch für MLS True → der MLS-Lauf schrieb
# matches/liga-*.json und ÜBERSCHRIEB matches/liga-index.json mit MLS-Inhalten. Ergebnis:
# 0 MLS-Match-Pages (171 wm-, 65 liga-, 0 mls-) UND beschädigte Liga-Seiten.
_PFX         = D.active_dataset()
WM_FILE      = str(D.data_file())
HISTORY_FILE = str(D.file("wm2026-odds-history.json", "liga-odds-history.json"))
POLY_FILE    = str(D.file("wm_poly_prices.json", "liga_poly_prices.json"))
PROPS_FILE   = str(D.file("wm2026-player-props.json", "liga_player_props.json"))
SMARTMONEY_FILE = str(D.file("wm_poly_smartmoney.json", "liga_poly_smartmoney.json"))

CO_HOSTS = {"MEX", "USA", "CAN"}

# ── Helpers ────────────────────────────────────────────────────────────────────

def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)

# 21.08.2026 (Lucas): Polymarket-Geld fuer die Event-Page aus money_map.json (matcht Betfair<->Poly
# je Spiel, breite Abdeckung inkl. Liga). liga_poly_smartmoney.json existiert nicht → smartMoney war
# immer None → Poly-Block versteckt. money_map liefert zumindest den Poly-Geld-Favoriten zuverlaessig.
_MONEY_MAP_CACHE = {}
def _money_map_rows():
    if "r" not in _MONEY_MAP_CACHE:
        d = load_json(os.path.join(BASE, "money_map.json")) or {}
        _MONEY_MAP_CACHE["r"] = d.get("rows") or []
    return _MONEY_MAP_CACHE["r"]

def _mm_norm(x):
    import re as _re
    return _re.sub(r"[^a-z0-9]+", "", str(x or "").lower())

def _mm_like(a, b):
    a, b = _mm_norm(a), _mm_norm(b)
    return bool(a and b and (a == b or a in b or b in a))

def poly_money_from_map(home_name, away_name):
    """Poly-Geld-Favorit fuer dieses Spiel aus money_map (oder None)."""
    for r in _money_map_rows():
        if not isinstance(r, dict):
            continue
        if _mm_like(home_name, r.get("home")) and _mm_like(away_name, r.get("away")):
            poly = r.get("poly") or {}
            bf = r.get("betfair") or {}
            if not poly.get("sharePct"):
                return None
            # Seite (home/away/draw) → welches Team
            side = poly.get("side")
            favTeam = (home_name if side == "home" else away_name if side == "away"
                       else poly.get("name") or "—")
            return {
                "favSide": side, "favTeam": favTeam,
                "sharePct": poly.get("sharePct"), "usd": poly.get("usd"),
                "srcTag": poly.get("src") or "",
                # Cross-Check: sieht Betfair dieselbe Seite vorne?
                "betfairAgree": (bf.get("side") == side) if bf.get("side") else None,
                "betfairPct": bf.get("sharePct"),
                "verdict": r.get("verdict"),
            }
    return None



def upset_score(home_elo, away_elo):
    gap = abs(home_elo - away_elo)
    if gap < 50:   return 9
    if gap < 100:  return 7
    if gap < 150:  return 6
    if gap < 200:  return 4
    if gap < 300:  return 2
    return 1


def devig(h, d, a):
    """De-vig 1X2 odds to implied win probabilities (%). None bei Platzhalter-Quoten.

    19.07.2026 — Platzhalter-Quoten-Gate (Lucas: „Fehler mehrfach"). Ohne den Filter landeten
    Fake-Wahrscheinlichkeiten (Remis 1.01 → „99 %") auf den Match-Pages. odds_plausibility ist
    die EINE Quelle."""
    from odds_plausibility import plausible_1x2
    if not plausible_1x2(h, d, a):
        return None, None, None
    try:
        margin = 1/h + 1/d + 1/a
        return (
            round(1/h / margin * 100, 1),
            round(1/d / margin * 100, 1),
            round(1/a / margin * 100, 1),
        )
    except (ZeroDivisionError, TypeError):
        return None, None, None


def model_probs_from_elo(home_elo: float, away_elo: float, home_is_cohost: bool = False):
    """
    Modell-Wahrscheinlichkeiten aus Elo. EINZIGE Quelle ist generate_wm_picks.
    elo_probabilities() — kein eigener Kopie der Formel mehr (21.06.2026, Lucas:
    „nicht das wir was doppelt machen"). Lazy-Import wegen Zirkularität
    (generate_wm_picks ruft diesen Builder auf). Returns (pHome%, pDraw%, pAway%).
    """
    from generate_wm_picks import elo_probabilities   # lazy: vermeidet Zirkel-Import
    p = elo_probabilities(home_elo, away_elo, home_is_cohost)
    return (
        round(p["pH"] * 100, 1),
        round(p["pD"] * 100, 1),
        round(p["pA"] * 100, 1),
    )


def fmt_rate(v):
    """Convert 0-1 float to percentage float, or leave as-is if already ≥1."""
    if v is None:
        return None
    return round(v * 100, 1) if v <= 1.0 else round(v, 1)


# ── Build one JSON payload ─────────────────────────────────────────────────────

def _match_player_spotlights(wm: dict, home_id: str, away_id: str) -> list[dict]:
    """
    Gibt Player Spotlights zurück die zu diesem Spiel gehören.
    Schaut in wm["playerSpotlights"] nach Spielern beider Teams.
    """
    all_spots = wm.get("playerSpotlights", {})
    result = []
    for week_spots in all_spots.values():
        for spot in week_spots:
            if spot.get("teamId") in (home_id, away_id):
                # Vollständige Spotlight-Daten aus wm["squads"] anreichern
                player = wm.get("squads", {}).get(spot["teamId"])
                if player:
                    spot = dict(spot)
                    spot["player"] = player
                    # Flag + Name aus Gruppe
                    for gdata in wm.get("groups", {}).values():
                        for t in gdata.get("teams", []):
                            if t["id"] == spot["teamId"]:
                                spot["teamFlag"] = t.get("flag", "🏳")
                                spot["teamName"] = t.get("name", spot["teamId"])
                    result.append(spot)
    return result


def generate_bet_insights(home_id, away_id, home_form, away_form, h2h, home_team, away_team) -> list[dict]:
    """
    Generiert kontextuelle Wett-Insights aus Form/H2H-Daten.
    Returns list of {icon, text, type} — max 6 Insights.
    form fields already normalised: over25Rate/bttsRate in %, avgScored/avgConceded as per-game floats.
    """
    insights = []

    def add(icon, text, kind):
        insights.append({"icon": icon, "text": text, "type": kind})

    for team_id, form, team in [(home_id, home_form, home_team), (away_id, away_form, away_team)]:
        if not form:
            continue
        name = team.get("name", team_id)
        last5  = form.get("last5",  [])
        last10 = form.get("last10", [])

        # Unbeaten streak (W or D in a row from most recent)
        unbeaten = 0
        for r in reversed(last10):
            if r in ("W", "D"):
                unbeaten += 1
            else:
                break
        if unbeaten >= 5:
            add("🔥", f"{name} seit {unbeaten} Spielen ungeschlagen", "streak")
        elif unbeaten >= 3:
            add("📈", f"{name} seit {unbeaten} Spielen ohne Niederlage", "streak")

        # Win streak
        wins = 0
        for r in reversed(last5):
            if r == "W":
                wins += 1
            else:
                break
        if wins >= 3:
            add("⚡", f"{name} – {wins} Siege in Folge", "streak")

        # Loss streak (red flag)
        losses = 0
        for r in reversed(last5):
            if r == "L":
                losses += 1
            else:
                break
        if losses >= 3:
            add("⚠️", f"{name} zuletzt {losses} Niederlagen in Folge", "warning")

        # Over 2.5 rate
        o25 = form.get("over25Rate")
        if o25 is not None and o25 >= 65:
            add("⚽", f"{name}: Over 2.5 in {round(o25)}% der letzten Spiele", "goals")
        elif o25 is not None and o25 <= 30:
            add("🛡️", f"{name}: Nur {round(o25)}% der Spiele über 2.5 Tore", "defense")

        # BTTS rate
        btts = form.get("bttsRate")
        if btts is not None and btts >= 65:
            add("🔄", f"{name}: Beide Teams trafen in {round(btts)}% der Spiele", "btts")

        # Scoring average — high or low
        avg_s = form.get("avgScored")
        avg_c = form.get("avgConceded")
        if avg_s is not None and avg_s >= 2.2:
            add("🎯", f"{name}: Ø {avg_s:.1f} Tore/Spiel — starke Offensive", "goals")
        elif avg_s is not None and avg_s < 0.9:
            add("😴", f"{name}: Nur Ø {avg_s:.1f} Tore/Spiel — schwache Offensive", "warning")
        if avg_c is not None and avg_c <= 0.6:
            add("🏰", f"{name}: Ø nur {avg_c:.1f} Gegentore — defensive Mauer", "defense")

    # H2H insights
    if h2h:
        games = h2h.get("games", 0)
        hn    = home_team.get("name", home_id)
        an    = away_team.get("name", away_id)
        if games >= 3:
            hw = h2h.get("homeWins", 0)
            dr = h2h.get("draws",    0)
            aw = h2h.get("awayWins", 0)

            if hw >= round(games * 0.6):
                add("📊", f"H2H: {hn} gewann {hw}/{games} Direktbegegnungen", "h2h")
            elif aw >= round(games * 0.6):
                add("📊", f"H2H: {an} dominiert – {aw} von {games} Siegen", "h2h")
            elif dr >= round(games * 0.4):
                add("🤝", f"H2H: {dr} Unentschieden in {games} Direktbegegnungen — Remis-Tendenz", "h2h")

            avg_g = h2h.get("avgGoals")
            if avg_g:
                if float(avg_g) >= 3.2:
                    add("🔥", f"H2H: Ø {float(avg_g):.1f} Tore/Spiel — torhungrige Partien", "goals")
                elif float(avg_g) < 1.8:
                    add("🛡️", f"H2H: Ø {float(avg_g):.1f} Tore/Spiel — taktische Duelle", "defense")

            o25_h = h2h.get("over25Rate")
            if o25_h is not None and float(o25_h) >= 70:
                add("⚽", f"H2H: Over 2.5 in {round(float(o25_h))}% der Direktbegegnungen", "goals")

    return insights[:6]


def build_odds_history(history: dict, odds_key: str) -> list[dict]:
    """
    Gibt die letzten 20 Snapshots für ein Fixture zurück.
    Format: [{ts, hw, dr, aw, hwShift, awShift}]
    hwShift/awShift = implied prob shift vs vorheriger Snapshot.
    """
    snaps = history.get(odds_key, [])
    if not snaps:
        return []

    # Maximale 20 Einträge (letzte zuerst für Chart)
    subset = snaps[-20:]
    result = []
    for i, s in enumerate(subset):
        entry = {
            "ts":  s.get("ts", ""),
            "hw":  s.get("hw"),
            "dr":  s.get("dr"),
            "aw":  s.get("aw"),
        }
        # Shift zum vorherigen Snapshot
        if i > 0:
            prev = subset[i - 1]
            def _pp(o):
                return round(100 / o, 2) if o and o > 0 else None
            ph, nh = _pp(prev.get("hw")), _pp(s.get("hw"))
            pa, na = _pp(prev.get("aw")), _pp(s.get("aw"))
            entry["hwShift"] = round(nh - ph, 2) if ph and nh else 0
            entry["awShift"] = round(na - pa, 2) if pa and na else 0
        else:
            entry["hwShift"] = 0
            entry["awShift"] = 0
        result.append(entry)
    return result


def poisson_xg(home_form, away_form, home_elo: float, away_elo: float, home_is_cohost: bool = False):
    """
    Schätzt Expected Goals (xG) via Poisson-Modell aus Form-Daten.
    Fallback auf Elo-basierte Schätzung wenn Form-Daten fehlen.
    Returns (xg_home, xg_away) als float.
    """
    WM_AVG = 2.3  # historischer WM-Schnitt: ~2.3 Tore/Spiel

    h_scored = h_conceded = a_scored = a_conceded = None

    if home_form and home_form.get('games', 0) >= 3:
        h_scored   = home_form.get('avgScored',   0)
        h_conceded = home_form.get('avgConceded', 0)

    if away_form and away_form.get('games', 0) >= 3:
        a_scored   = away_form.get('avgScored',   0)
        a_conceded = away_form.get('avgConceded', 0)

    import math
    p_home = 1.0 / (1.0 + 10.0 ** (-(home_elo - away_elo) / 400.0))
    if home_is_cohost:
        p_home = min(0.90, p_home + 0.04)
    p_away = 1.0 - p_home

    if h_scored is not None and a_conceded is not None:
        xg_home = round((h_scored + a_conceded) / 2, 2)
    else:
        xg_home = round(WM_AVG * p_home * 0.95, 2)

    if a_scored is not None and h_conceded is not None:
        xg_away = round((a_scored + h_conceded) / 2, 2)
    else:
        xg_away = round(WM_AVG * p_away * 1.05, 2)

    return xg_home, xg_away


def _smartmoney_all(_cache={}):
    """Smart-Money (wm_poly_smartmoney.json) einmal laden + memoizen. {} wenn fehlt."""
    if "d" not in _cache:
        raw = load_json(SMARTMONEY_FILE) or {}
        d = raw.get("matches", raw)
        _cache["d"] = d if isinstance(d, dict) else {}
    return _cache["d"]


# 13.07.2026 (MLS-Audit): war hart wm_lineups → MLS-Match-Pages zeigten NIE eine Aufstellung,
# obwohl fetch_wm_lineups mls_lineups.json schreibt.
LINEUPS_FILE = str(D.file("wm_lineups.json", "liga_lineups.json"))

def _lineups_all(_cache={}):
    """Aufstellungen (wm_lineups.json) einmal laden + memoizen. {} wenn fehlt."""
    if "d" not in _cache:
        d = load_json(LINEUPS_FILE) or {}
        _cache["d"] = d if isinstance(d, dict) else {}
    return _cache["d"]


def _lineup_for(home_id, away_id):
    """Schlanke Aufstellung (Formation/Trainer/Start-XI mit grid/Bank) fürs Payload.
    None wenn (noch) keine veröffentlicht — Aufstellungen kommen ~1h vor Anpfiff."""
    lu = _lineups_all().get(f"{home_id}-{away_id}") or {}
    def _slim(side):
        if not isinstance(side, dict) or not side.get("starting"):
            return None
        return {
            "formation": side.get("formation"),
            "coach":     side.get("coach"),
            "starting":  [{"name": p.get("name"), "pos": p.get("pos"),
                           "grid": p.get("grid"), "num": p.get("num")}
                          for p in (side.get("starting") or [])],
            "subs":      [{"name": p.get("name"), "pos": p.get("pos"), "num": p.get("num")}
                          for p in (side.get("subs") or [])],
        }
    h, a = _slim(lu.get("home")), _slim(lu.get("away"))
    if not h and not a:
        return None
    return {"home": h, "away": a, "kickoff": lu.get("kickoff")}


# ── Serien (compute_streaks) fürs Match-Payload (29.06.2026, Lucas: Serien auf die Event-Page) ──
def _streaks_index(_cache={}):
    """{wm_,liga_,mls_}streaks.json einmal laden + nach teamId indizieren (dataset-aware)."""
    if "d" not in _cache:
        data = load_json(str(D.file("wm_streaks.json", "liga_streaks.json"))) or {}
        idx = {}
        for s in (data.get("streaks") or []):
            idx.setdefault(str(s.get("teamId")), []).append(s)
        _cache["d"] = idx
    return _cache["d"]


def _streaks_for_match(home_id, away_id):
    """Heim-Team bevorzugt Heim-Serie, Auswärts-Team Auswärts-Serie, sonst Gesamt (Venue-Dedup wie
    die Card). Schlankes Payload für die Event-Page. None wenn keine Serien."""
    def _pick(team_id, pref):
        by_type, score = {}, (lambda v: 2 if v == pref else (1 if v == "all" else 0))
        for s in _streaks_index().get(str(team_id), []):
            cur = by_type.get(s.get("type"))
            if cur is None or score(s.get("venue")) > score(cur.get("venue")):
                by_type[s.get("type")] = s
        return list(by_type.values())
    ms = _pick(home_id, "H") + _pick(away_id, "A")
    ms.sort(key=lambda s: -(s.get("length") or 0))
    out = [{
        "team": s.get("team"), "teamId": s.get("teamId"), "type": s.get("type"),
        "market": s.get("market"), "length": s.get("length"), "venue": s.get("venue"),
        "ratePct": s.get("ratePct"), "oppSupportPct": s.get("oppSupportPct"),
        "seq": s.get("seq"), "continuation": s.get("continuation"),
        "next": s.get("next"), "signalInfo": s.get("signalInfo"),
    } for s in ms[:6]]
    return out or None


# ── Betfair-Exchange-Geld + Markt-Konsens (31.07.2026, Lucas: „Event-Pages mit Betfair/Poly füllen") ──
# Gebacken zur Generierzeit (wie Pinnacle/Soft/Poly auf der Page), per event_key gematcht — dieselbe
# Normalisierung wie das betfair_money-Signal in generate_wm_picks. „Nur zeitnahe Spiele": der Block
# entsteht NUR, wenn betfair_prices.json ein Match liefert (→ bei Vorsaison-Spielen ohne Börse = None).
BF_NORM_AMBER, BF_NORM_RED = 1.6, 2.6        # ×-Norm-Schwellen — identisch zum Radar
BF_NORM_MIN_PEERS, BF_NORM_MIN_EUR = 4, 3000

def _bf_event_key(a, b):
    try:
        from poly_cross_sport import event_key
        return event_key(a, b)
    except Exception:
        return "-".join(sorted([(a or "").strip().lower(), (b or "").strip().lower()]))

# Woerter, die zu viele Vereine teilen — als Bruecke wertlos und gefaehrlich.
# Woerter, die zu viele Vereine teilen — als Bruecke wertlos. Vor allem STADT-Namen sind
# gefaehrlich: „Manchester United" und „Manchester City" wuerden sonst als dasselbe Team gelten,
# und der Paar-Test rettet das nicht, wenn beide am selben Tag gegen dieselbe Mannschaft spielen.
_BF_STOPWORDS = {"united", "sporting", "national", "internacional", "juniors", "wanderers",
                 "rangers", "rovers", "albion", "county", "manchester", "london", "madrid",
                 "milano", "milan", "roma", "torino", "sevilla", "bristol", "sheffield",
                 "nottingham", "newcastle", "birmingham", "istanbul", "moskva", "beograd"}


def _bf_compatible(a, b):
    """Zwei Team-Schreibweisen, dasselbe Team? REIN/testbar.

    25.08.2026 (Lucas): der exakte `event_key` verlor „Real Betis"/„Betis" und
    „Athletic Club"/„Athletic Bilbao". Enthaltensein reicht — aber nur ab 4 Zeichen, sonst wuerde
    „FC" auf alles passen.
    """
    from poly_cross_sport import norm as _n
    na, nb = _n(a), _n(b)
    if not na or not nb:
        return False
    if na == nb or (len(na) >= 4 and len(nb) >= 4 and (na in nb or nb in na)):
        return True
    # „Athletic Club" und „Athletic Bilbao" enthalten einander NICHT — sie teilen ein markantes Wort.
    # Mindestlaenge 5 haelt „Real"/„Real" (Madrid vs Sociedad) und „FC"/„United" bewusst draussen;
    # genau die waeren die gefaehrlichen Fehltreffer.
    wa = {w for w in (_n(x) for x in str(a).split()) if len(w) >= 5 and w not in _BF_STOPWORDS}
    wb = {w for w in (_n(x) for x in str(b).split()) if len(w) >= 5 and w not in _BF_STOPWORDS}
    return bool(wa & wb)


def _bf_find(snaps, fuzzy, home, away, date=None):
    """Betfair-Snapshot zum Spiel. Erst exakt, dann Namens-Bruecke am selben Spieltag. REIN.

    Die Bruecke ist bewusst eng: gleicher Tag (±1 wegen Zeitzone), BEIDE Seiten kompatibel, und der
    Treffer muss EINDEUTIG sein. Zwei Kandidaten heisst lieber kein Block als der falsche.
    """
    m = (snaps or {}).get(_bf_event_key(home, away))
    if m:
        return m
    if not fuzzy or not date:
        return None
    from datetime import date as _date, timedelta as _td
    try:
        d0 = _date.fromisoformat(str(date)[:10])
        days = [str(d0 + _td(days=k)) for k in (0, -1, 1)]
    except Exception:
        days = [str(date)[:10]]
    hits = []
    for day in days:
        for cand in (fuzzy.get(day) or []):
            if ((_bf_compatible(home, cand.get("home")) and _bf_compatible(away, cand.get("away")))
                    or (_bf_compatible(home, cand.get("away")) and _bf_compatible(away, cand.get("home")))):
                hits.append(cand)
    return hits[0] if len(hits) == 1 else None


_LNORM_CACHE = {}


def _bf_learned_norm():
    """Gelernte Liga-Basis aus betfair_league_norm.json ({} wenn es sie noch nicht gibt).

    Ueber einen Cache-Dict, damit Tests eine Basis setzen koennen statt gegen die Live-Datei zu
    laufen — Schwellen gegen Bot-Daten zu pruefen ist die Klasse Test, die eines Tages ohne
    Code-Aenderung rot wird ([[feedback_tests_no_live_data_thresholds]]).
    """
    if "b" not in _LNORM_CACHE:
        import os as _os
        f = _os.path.join(BASE, "betfair_league_norm.json")
        got = {}
        if _os.path.exists(f):
            try:
                got = (json.load(open(f, encoding="utf-8")) or {}).get("byLeagueStage") or {}
            except Exception:
                got = {}
        _LNORM_CACHE["b"] = got
    return _LNORM_CACHE["b"]


def _bf_market_total(m):
    """Summe der Runner-Volumina über ALLE Märkte — identisch zu totalG() im Radar."""
    s = 0.0
    for mk in (m.get("markets") or {}).values():
        for r in (mk.get("runners") or []):
            s += float(r.get("vol") or 0)
    return s

def _bf_stage(m, now_ms):
    """Pre-Match-Bucket wie _stageOf im Radar: p1 = letzte 3h vor Anpfiff, p0 = früher. Live/fertig → None."""
    li = m.get("liveInfo") or {}
    if li.get("finished"):
        return None
    ko = m.get("kickoff")
    try:
        from datetime import datetime as _dt
        k = _dt.fromisoformat(str(ko).replace("Z", "+00:00")).timestamp() * 1000 if ko else None
    except Exception:
        k = None
    if k is None:
        return "p0"
    if k <= now_ms:                       # Anpfiff vorbei → live, nicht bepagen
        return None
    return "p1" if (k - now_ms) <= 3 * 3.6e6 else "p0"

def load_betfair():
    """{event_key: match} + ×-Norm-Basis {stage: sortierte Totals}. Einmal in main() laden."""
    import os as _os
    f = _os.path.join(BASE, "matches", "..", "betfair_prices.json") if False else _os.path.join(BASE, "betfair_prices.json")
    if not _os.path.exists(f):
        return {}, {}
    try:
        raw = json.load(open(f, encoding="utf-8"))
    except Exception as e:
        print(f"  ⚠️  Betfair-Preise nicht ladbar: {e}")
        return {}, {}
    now_ms = (datetime.utcnow() - datetime(1970, 1, 1)).total_seconds() * 1000
    snaps, base, fuzzy = {}, {}, {}
    for m in (raw.get("matches") or []):
        h, a = m.get("home"), m.get("away")
        if h and a:
            snaps[_bf_event_key(h, a)] = m
            _day = str(m.get("kickoff") or "")[:10]
            if _day:
                fuzzy.setdefault(_day, []).append(m)
        st = _bf_stage(m, now_ms)
        tot = _bf_market_total(m)
        if st and tot >= BF_NORM_MIN_EUR:
            base.setdefault(st, []).append(tot)
    for st in base:
        base[st].sort()
    print(f"  Betfair-Geld: {len(snaps)} Matches geladen (×-Norm-Basis: {{ {', '.join(f'{k}:{len(v)}' for k,v in base.items())} }})")
    return snaps, base, fuzzy

def _median(xs):
    n = len(xs)
    if not n:
        return None
    xs = sorted(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2

def _bf_market_shares(m, market_name, runner_map):
    """runner_map: {token: [mögliche Runner-Namen]} → {token: {vol, share, odd}} + total."""
    mk = (m.get("markets") or {}).get(market_name) or {}
    runners = mk.get("runners") or []
    tot = sum(float(r.get("vol") or 0) for r in runners) or 0.0
    out = {}
    for tok, names in runner_map.items():
        rr = next((r for r in runners if r.get("name") in names), None)
        if rr:
            v = float(rr.get("vol") or 0)
            out[tok] = {"vol": round(v), "share": round(v / tot, 4) if tot else None, "odd": rr.get("odd")}
    return (out or None), round(tot)

_BROAD_CACHE = {}


def _broad_rows():
    """poly_money_broad_close.json — dieselbe Quelle, aus der Radar, Wallets und Whales leben."""
    if "r" not in _BROAD_CACHE:
        d = load_json(os.path.join(BASE, "poly_money_broad_close.json")) or {}
        _BROAD_CACHE["r"] = d if isinstance(d, dict) else {}
    return _BROAD_CACHE["r"]


def _broad_outcome_slot(label, home, away):
    """Ausgangs-Label → 'home' | 'draw' | 'away' | None. REIN."""
    from poly_cross_sport import norm as _n
    lab = _n(label)
    if not lab:
        return None
    if lab.startswith("draw") or "draw" in lab[:6]:
        return "draw"
    h, a = _n(home), _n(away)
    if h and (lab == h or (len(lab) >= 4 and len(h) >= 4 and (lab in h or h in lab))):
        return "home"
    if a and (lab == a or (len(lab) >= 4 and len(a) >= 4 and (lab in a or a in lab))):
        return "away"
    return None


def poly_broad_smartmoney(home_name, away_name, date=None):
    """Polymarket-Geld je Ausgang aus dem Broad-Feed — im Format, das die Seite schon rendert.

    25.08.2026 (Lucas: „seh immer noch keinen Poly-Block"): Quelle war money_map.json, die einen
    Betfair<->Poly-Doppeltreffer verlangt und deshalb aktuell 2 Zeilen fuehrt. Der Broad-Feed hat
    380+ Fussball-Maerkte MIT Wallet-Aufschluesselung — genau das, was `renderPoly` erwartet
    (outcomes.{home,draw,away}.{share,holders,topHolderShare}).

    Nur der 1X2-Basismarkt: die Zusatzmaerkte (-exact-score, -more-markets, -halftime-result) tragen
    dieselben Teamnamen und wuerden sonst als Kandidat mitzaehlen.
    """
    best = None
    for key, m in (_broad_rows() or {}).items():
        if not isinstance(m, dict) or m.get("resolved") is not None:
            continue
        if any(key.endswith(sfx) for sfx in ("-exact-score", "-more-markets", "-halftime-result")):
            continue
        shares = m.get("shares") or {}
        if len(shares) < 2:
            continue
        slots = {}
        for lab, usd in shares.items():
            slot = _broad_outcome_slot(lab, home_name, away_name)
            if slot:
                slots.setdefault(slot, []).append((lab, float(usd or 0)))
        if "home" not in slots or "away" not in slots:
            continue                                  # beide Teams muessen vorkommen
        tot = sum(v for lst in slots.values() for _, v in lst)
        if tot <= 0:
            continue
        if best is None or tot > best[0]:
            best = (tot, m, slots)
    if not best:
        return None
    tot, m, slots = best
    whales = [w for w in (m.get("whales") or []) if isinstance(w, dict)]
    out = {}
    for slot in ("home", "draw", "away"):
        lst = slots.get(slot) or []
        if not lst:
            continue
        usd = sum(v for _, v in lst)
        labels = {lab for lab, _ in lst}
        mine = sorted((float(w.get("usd") or 0) for w in whales if w.get("side") in labels), reverse=True)
        out[slot] = {"share": round(usd / tot, 4), "usd": round(usd),
                     "holders": len(mine) or None,
                     "topHolderShare": (round(mine[0] / usd, 4) if mine and usd > 0 else None)}
    if "home" not in out or "away" not in out:
        return None
    return {"outcomes": out, "totalUsd": round(tot),
            "topTraders": len([w for w in whales if float(w.get("usd") or 0) >= 1000]),
            "src": "broad"}


_UPCOMING_CACHE = {}


def _upcoming_rows():
    """poly_money_upcoming.json — Poly-Preise + Volumen bis 48h vor Anpfiff.

    25.08.2026 (Lucas): der Close-Feed friert erst ~3h vor Anpfiff ein und enthaelt fuer eine Seite,
    die Tage vorher erzeugt wird, GAR NICHTS (0 Eintraege ab dem 25.08.). Diese Datei gibt es seit
    dem 12.08. fuer die Money Map und sie hat genau das Fehlende: Valencia–Betis, Real Madrid–Real
    Sociedad & Co. schon am Vortag. Keine Wallet-Aufschluesselung (kein Holder-Call) — dafuer
    rendert die Seite den kompakten Block.
    """
    if "r" not in _UPCOMING_CACHE:
        d = load_json(os.path.join(BASE, "poly_money_upcoming.json")) or {}
        _UPCOMING_CACHE["r"] = d if isinstance(d, dict) else {}
    return _UPCOMING_CACHE["r"]


def poly_upcoming_money(home_name, away_name, betfair_block=None):
    """Kompakter Poly-Geld-Block (Favorit + Anteil + Volumen) fuer Spiele vor dem Close-Fenster.

    Auf Polymarket IST der Preis die Geldverteilung — deshalb ist `sharePct` hier der de-viggte
    Preis-Anteil der fuehrenden Seite, nicht ein Shares-Anteil. Das steht so im Tooltip der Seite.
    """
    best = None
    for key, m in (_upcoming_rows() or {}).items():
        if not isinstance(m, dict):
            continue
        if any(key.endswith(sfx) for sfx in ("-exact-score", "-more-markets", "-halftime-result")):
            continue
        prices = m.get("prices") or {}
        if len(prices) < 2:
            continue
        slots = {}
        for lab, pr in prices.items():
            slot = _broad_outcome_slot(lab, home_name, away_name)
            if slot and isinstance(pr, (int, float)):
                slots[slot] = max(slots.get(slot, 0.0), float(pr))
        if "home" not in slots or "away" not in slots:
            continue
        vol = float(m.get("totalUsd") or 0)
        if best is None or vol > best[0]:
            best = (vol, slots)
    if not best:
        return None
    vol, slots = best
    tot = sum(slots.values())
    if tot <= 0:
        return None
    side = max(slots, key=lambda k: slots[k])
    share = slots[side] / tot                       # de-viggt: Summe der Ausgangs-Preise = 1
    fav = home_name if side == "home" else away_name if side == "away" else "Unentschieden"
    # Cross-Check gegen den Betfair-FAVORITEN (niedrigste Quote), nicht gegen die groesste
    # Geld-Saeule: bei Valencia–Betis liegen 60% des Geldes auf dem Remis, Favorit ist es deshalb
    # nicht. „Die Boersen sind uneinig" darf nur stehen, wenn sie wirklich verschiedene Seiten
    # vorne sehen.
    bf_side, bf_pct = None, None
    if isinstance(betfair_block, dict):
        mo = betfair_block.get("mo") or {}
        od = mo.get("odds") or {}
        bf_side = _fav_token(od.get("home"), od.get("draw"), od.get("away"))
        if bf_side:
            _sh = ((mo.get("shares") or {}).get(bf_side) or {}).get("share")
            bf_pct = round(_sh * 100) if isinstance(_sh, (int, float)) else None
    return {
        "favSide": side, "favTeam": fav,
        "sharePct": round(share * 100), "usd": round(vol),
        "srcTag": "upcoming",
        "betfairAgree": (bf_side == side) if bf_side else None,
        "betfairPct": bf_pct,
        "verdict": None,
    }


def build_betfair_block(home_name, away_name, snaps, norm_base, fuzzy=None, date=None):
    if not snaps:
        return None
    m = _bf_find(snaps, fuzzy, home_name, away_name, date)
    if not m:
        return None
    now_ms = (datetime.utcnow() - datetime(1970, 1, 1)).total_seconds() * 1000
    total = _bf_market_total(m)
    if total < 5000:          # Kleckervolumen → Verteilung ist Rauschen, kein Block
        return None
    # 1X2-Geld (Match Odds) — Runner heißen wie die Betfair-Teams bzw. „The Draw".
    mo_market = "Match Odds"
    mo_runmap = {"home": [m.get("home")], "draw": ["The Draw", "Draw"], "away": [m.get("away")]}
    mo_shares, mo_total = _bf_market_shares(m, mo_market, mo_runmap)
    mo = m.get("mo") or {}
    fair = mo.get("fair") or {}
    # O/U 2.5
    ou = m.get("markets", {}).get("Over/Under 2.5 Goals")
    ou_out, ou_total = (None, 0)
    if ou:
        ou_out, ou_total = _bf_market_shares(m, "Over/Under 2.5 Goals",
                                             {"over": ["Over 2.5 Goals"], "under": ["Under 2.5 Goals"]})
    # ×-Norm
    st = _bf_stage(m, now_ms)
    ratio, lvl = None, 0
    # 25.08.2026: gelernte Liga-Basis statt Schnappschuss — identisch zum Radar seit 24.08.
    # Der alte Weg mass ein EPL-Spiel gegen einen Pool voller Mini-Ligen und kam auf x80,
    # wo x0.6 richtig war. Ohne belastbare Liga-Basis gibt es hier gar keinen Wert.
    if st and total >= BF_NORM_MIN_EUR:
        _lb = (_bf_learned_norm() or {}).get('%s|%s' % (m.get('league'), st))
        if isinstance(_lb, dict) and (_lb.get('n') or 0) >= BF_NORM_MIN_PEERS and _lb.get('med'):
            ratio = round(total / float(_lb['med']), 2)
            lvl = 2 if ratio >= BF_NORM_RED else (1 if ratio >= BF_NORM_AMBER else 0)
    # „Heavy money" Seite: wo Geld-Anteil den fairen Anteil am stärksten übersteigt
    heavy = None
    if mo_shares and fair and (mo_total or 0) >= 3000:
        best_pp = 0
        for tok in ("home", "draw", "away"):
            sh = (mo_shares.get(tok) or {}).get("share")
            fr = fair.get(tok)
            if sh is not None and fr is not None:
                pp = (sh - fr) * 100
                if pp > best_pp:
                    best_pp, heavy = pp, {"token": tok, "moneyPct": round(sh * 100), "fairPct": round(fr * 100), "edgePP": round(pp)}
    return {
        "totalEur": round(total),
        "kickoff": m.get("kickoff"),
        "capturedAt": m.get("capturedAt") or (m.get("_meta") or {}).get("generatedAt"),
        "normRatio": ratio, "normLvl": lvl,
        "mo": {"shares": mo_shares, "fair": {k: (round(v, 4) if isinstance(v, (int, float)) else v) for k, v in fair.items()},
               "odds": {"home": mo.get("hw"), "draw": mo.get("dr"), "away": mo.get("aw")}, "totalEur": mo_total},
        "ou25": ({"shares": ou_out, "totalEur": ou_total} if ou_out else None),
        "heavy": heavy,
    }

def _fav_token(oh, od, oa):
    """Favorit = niedrigste Dezimalquote. Gibt 'home'|'draw'|'away' oder None."""
    cand = [(oh, "home"), (od, "draw"), (oa, "away")]
    cand = [(o, t) for o, t in cand if isinstance(o, (int, float)) and o > 1]
    if not cand:
        return None
    return min(cand)[1]

def build_consensus(pinn, soft, smart, betfair):
    """Ein Streifen: welche Seite sehen Pinnacle / Soft / Betfair / Polymarket? Konsens = alle einig."""
    src = []
    if pinn:
        t = _fav_token(pinn.get("nowH"), pinn.get("nowD"), pinn.get("nowA"))
        if t: src.append({"name": "Pinnacle", "token": t})
    if soft:
        t = _fav_token(soft.get("nowH"), soft.get("nowD"), soft.get("nowA"))
        if t: src.append({"name": "Soft-Books", "token": t})
    if betfair and betfair.get("mo", {}).get("odds"):
        o = betfair["mo"]["odds"]
        t = _fav_token(o.get("home"), o.get("draw"), o.get("away"))
        if t: src.append({"name": "Betfair", "token": t})
    if smart and smart.get("outcomes"):
        oc = smart["outcomes"]
        best = max(((k, (v or {}).get("share") or 0) for k, v in oc.items()), key=lambda x: x[1], default=(None, 0))
        if best[0] and best[1] > 0:
            src.append({"name": "Polymarket", "token": best[0]})
    if len(src) < 2:
        return None
    toks = [s["token"] for s in src]
    modal = max(set(toks), key=toks.count)
    agree = len(set(toks)) == 1
    return {"sources": src, "modal": modal, "agree": agree, "n": len(src), "nAgree": toks.count(modal)}


def build_payload(group_id, group_data, fixture, team_lookup, wm, history=None, ai_previews=None, poly_lookup=None, betfair_snaps=None, betfair_norm=None, betfair_fuzzy=None):
    home_id = fixture["home"]
    away_id = fixture["away"]
    home_team = team_lookup[home_id]
    away_team = team_lookup[away_id]

    date = fixture["date"]
    slug = f"{_PFX}-{home_id.lower()}-vs-{away_id.lower()}-{date}"
    # KO-Spiele haben 'round' (R32/R16/…) statt 'matchday' → pick_key "KO-R32-…" wie generate_wm_picks.
    _md = fixture.get("matchday") or fixture.get("round") or "KO"
    pick_key = f"{group_id}-{_md}-{home_id}-{away_id}"
    odds_key = f"{home_id}-{away_id}"
    h2h_key  = f"{home_id}-{away_id}"

    home_elo = home_team.get("elo") or 1500
    away_elo = away_team.get("elo") or 1500
    elo_diff = home_elo - away_elo  # signed (positive = home stronger)

    # Picks
    picks_raw = wm.get("picks", {}).get(pick_key, [])

    # Odds
    odds_raw = wm.get("odds", {}).get(odds_key)
    odds_out = None
    if odds_raw:
        odds_out = {
            "home":    odds_raw.get("hw"),
            "draw":    odds_raw.get("dr"),
            "away":    odds_raw.get("aw"),
            "over25":  odds_raw.get("o25"),
            "under25": odds_raw.get("u25"),
            "btts":    odds_raw.get("btts"),
            "noBtts":  odds_raw.get("no_btts"),
        }

    # Win probabilities (de-vigged market)
    prob_home = prob_draw = prob_away = None
    if odds_raw and odds_raw.get("hw") and odds_raw.get("dr") and odds_raw.get("aw"):
        prob_home, prob_draw, prob_away = devig(odds_raw["hw"], odds_raw["dr"], odds_raw["aw"])

    # Model probabilities — direkt aus Elo-Modell (konsistent und vollständig)
    co_host = home_id in CO_HOSTS
    mod_home, mod_draw, mod_away = model_probs_from_elo(home_elo, away_elo, co_host)

    # Form
    form = wm.get("form", {})
    home_form = form.get(home_id)
    away_form = form.get(away_id)

    # Normalise rate fields (some sources store as 0-1, want as 0-100 for display)
    def normalise_form(f):
        if not f:
            return None
        out = dict(f)
        for k in ("over25Rate", "bttsRate"):
            if k in out and out[k] is not None:
                out[k] = fmt_rate(out[k])
        return out

    home_form = normalise_form(home_form)
    away_form = normalise_form(away_form)

    # xG: echte API-Football Werte wenn vorhanden, sonst Poisson-Fallback
    xg_stats   = wm.get("xgStats", {})
    home_xg_d  = xg_stats.get(home_id)
    away_xg_d  = xg_stats.get(away_id)

    # (31.07.2026) games>=3 reicht nicht: ein Vorsaison-Team kann Spiele UND xgForAvg=None haben
    # (kein API-xG erhoben) → None-Arithmetik crashte build_payload. Erst jetzt sichtbar, weil die
    # Vorsaison-Fixtures neu bepaged werden. _xg_ok verlangt numerische Mittelwerte.
    def _xg_ok(d):
        return bool(d) and (d.get("games", 0) or 0) >= 3 \
               and isinstance(d.get("xgForAvg"), (int, float)) \
               and isinstance(d.get("xgAgainstAvg"), (int, float))

    if _xg_ok(home_xg_d) and _xg_ok(away_xg_d):
        # Blend: (home_attack + away_defence) / 2 — same logic as Poisson but with real xG rates
        xg_home = round((home_xg_d["xgForAvg"] + away_xg_d["xgAgainstAvg"]) / 2, 2)
        xg_away = round((away_xg_d["xgForAvg"] + home_xg_d["xgAgainstAvg"]) / 2, 2)
        xg_source = "api_football"
    elif _xg_ok(home_xg_d):
        # Only home xG available — mix with Poisson for away
        _, xg_away_fb = poisson_xg(home_form, away_form, home_elo, away_elo, home_id in CO_HOSTS)
        xg_home = round(home_xg_d["xgForAvg"], 2)
        xg_away = xg_away_fb
        xg_source = "partial"
    elif _xg_ok(away_xg_d):
        # Only away xG available — mix with Poisson for home
        xg_home_fb, _ = poisson_xg(home_form, away_form, home_elo, away_elo, home_id in CO_HOSTS)
        xg_home = xg_home_fb
        xg_away = round(away_xg_d["xgForAvg"], 2)
        xg_source = "partial"
    else:
        xg_home, xg_away = poisson_xg(home_form, away_form, home_elo, away_elo, home_id in CO_HOSTS)
        xg_source = "poisson"

    # Polymarket data (from wm_poly_prices.json)
    poly_fix = (poly_lookup or {}).get(odds_key)
    poly_out = None
    if poly_fix:
        poly_out = {
            "hw":          poly_fix.get("poly_hw"),
            "dr":          poly_fix.get("poly_dr"),
            "aw":          poly_fix.get("poly_aw"),
            "o25":         poly_fix.get("poly_o25"),
            "u25":         poly_fix.get("poly_u25"),
            "btts":        poly_fix.get("poly_btts"),
            "vol":         poly_fix.get("vol"),
            "edge_hw":     poly_fix.get("edge_hw"),
            "edge_dr":     poly_fix.get("edge_dr"),
            "edge_aw":     poly_fix.get("edge_aw"),
            "edge_o25":    poly_fix.get("edge_o25"),
            "edge_u25":    poly_fix.get("edge_u25"),
            "bestEdge":    poly_fix.get("bestEdge"),
            "bestEdgeKey": poly_fix.get("bestEdgeKey"),
            "steamLag":    poly_fix.get("steamLag"),
            "hasPinnacle": poly_fix.get("hasPinnacle"),
            "slug":        poly_fix.get("slug"),
            "moreMktSlug": poly_fix.get("moreMktSlug"),
        }

    # Player props (anytime scorer) — aus wm2026-player-props.json (keyed by matchKey)
    # fetch_wm_player_props.py schreibt: { "MEX-ZAF": { "players": [{name, teamId, odds}, ...] } }
    # Wir transformieren zu { "MEX": {"anytime": 2.50}, "ZAF": {"anytime": 3.50} }
    player_props_out = {home_id: None, away_id: None}
    props_file_data = load_json(PROPS_FILE) or {}
    match_props = props_file_data.get(h2h_key)  # h2h_key = "MEX-ZAF"
    if match_props and isinstance(match_props.get("players"), list):
        team_best: dict[str, float] = {}
        for p in match_props["players"]:
            tid  = p.get("teamId")
            odds = p.get("odds")
            if tid and odds:
                # Beste (niedrigste) Quote pro Team behalten
                if tid not in team_best or odds < team_best[tid]:
                    team_best[tid] = float(odds)
        for tid, best_odds in team_best.items():
            player_props_out[tid] = {"anytime": best_odds}

    # H2H
    h2h_raw = wm.get("h2h", {}).get(h2h_key)
    h2h_out = None
    if h2h_raw:
        g = h2h_raw.get("games") or 1
        h2h_out = {
            "games":      h2h_raw.get("games", 0),
            "homeWins":   h2h_raw.get("homeWins", 0),
            "draws":      h2h_raw.get("draws", 0),
            "awayWins":   h2h_raw.get("awayWins", 0),
            "avgGoals":   h2h_raw.get("avgGoals"),
            "over25Rate": fmt_rate(h2h_raw.get("over25Rate")),
            "bttsRate":   fmt_rate(h2h_raw.get("bttsRate")),
            "homeBar":    round(h2h_raw.get("homeWins", 0) / g * 100),
            "drawBar":    round(h2h_raw.get("draws", 0) / g * 100),
            "awayBar":    round(h2h_raw.get("awayWins", 0) / g * 100),
        }

    # Bet Insights (rule-based, from form + H2H — must be after h2h_out is set)
    bet_insights = generate_bet_insights(
        home_id, away_id,
        home_form, away_form,
        h2h_out,
        home_team, away_team,
    )

    # Pinnacle- + Soft-Bookie-Odds-Strips (Opening → jetzt) für die Match-Page-Strips
    _oo = (odds_raw or {}).get("odds_open") or {}
    pinn_odds = None
    if odds_raw and odds_raw.get("hw"):
        pinn_odds = {
            "openH": _oo.get("hw"), "openD": _oo.get("dr"), "openA": _oo.get("aw"),
            "nowH": odds_raw.get("hw"), "nowD": odds_raw.get("dr"), "nowA": odds_raw.get("aw"),
            "book": odds_raw.get("bookmaker") or "Pinnacle",
        }
    soft_odds = None
    if odds_raw and odds_raw.get("public_hw"):
        soft_odds = {
            "openH": odds_raw.get("public_hw_open"), "openD": odds_raw.get("public_dr_open"),
            "openA": odds_raw.get("public_aw_open"),
            "nowH": odds_raw.get("public_hw"), "nowD": odds_raw.get("public_dr"),
            "nowA": odds_raw.get("public_aw"),
            "book": odds_raw.get("public_bookmaker") or "Soft-Books",
        }

    # Smart-Money (Polymarket-Wallet-Verteilung) für dieses Spiel
    smart_money = _smartmoney_all().get(odds_key)
    if not (smart_money and smart_money.get("outcomes")):
        # liga_poly_smartmoney.json existiert nicht — der Broad-Feed liefert dasselbe Format.
        smart_money = poly_broad_smartmoney(home_team["name"], away_team["name"], date) or smart_money
    # Betfair-Exchange-Geld + Markt-Konsens (31.07.2026) — nur wenn die Börse das Spiel führt.
    # Steht VOR dem Poly-Block, weil der kompakte Poly-Block den Betfair-Cross-Check mitnimmt.
    betfair_block = build_betfair_block(home_team["name"], away_team["name"], betfair_snaps or {},
                                        betfair_norm or {}, fuzzy=betfair_fuzzy, date=date)

    # Reihenfolge nach Reichhaltigkeit: money_map (selten, hat aber den fertigen Cross-Check) →
    # poly_money_upcoming (bis 48h vorher — der Normalfall einer Vorschau-Seite).
    poly_money = (poly_money_from_map(home_team["name"], away_team["name"])
                  or poly_upcoming_money(home_team["name"], away_team["name"], betfair_block))
    consensus_block = build_consensus(pinn_odds, soft_odds, smart_money, betfair_block)

    # Group teams + fixtures (for group table / context)
    group_teams = group_data.get("teams", [])
    group_fixtures = group_data.get("fixtures", [])

    payload = {
        "slug":       slug,
        "home":       home_team["name"],
        "homeId":     home_id,
        "homeFlag":   home_team.get("flag", ""),
        "away":       away_team["name"],
        "awayId":     away_id,
        "awayFlag":   away_team.get("flag", ""),
        "date":       date,
        "time":       fixture.get("time", ""),
        "venue":      fixture.get("venue", ""),
        "group":      group_id,
        "groupName":  group_data.get("name", f"Gruppe {group_id}"),
        "matchday":   _md,
        "round":      fixture.get("round"),
        "roundLabel": fixture.get("roundLabel"),
        "pickKey":    pick_key,
        "homeElo":    home_elo,
        "awayElo":    away_elo,
        "eloDiff":    elo_diff,
        "xgHome":     xg_home,
        "xgAway":     xg_away,
        "xgSource":   xg_source,  # "api_football" | "partial" | "poisson"
        "upsetScore": upset_score(home_elo, away_elo),
        "homeConf":   home_team.get("confederation", ""),
        "awayConf":   away_team.get("confederation", ""),
        "coHostBonus": home_id in CO_HOSTS,
        "coHostTeam":  home_team["name"] if home_id in CO_HOSTS else None,
        # Probabilities
        "probHome":  prob_home,
        "probDraw":  prob_draw,
        "probAway":  prob_away,
        "modHome":   mod_home,
        "modDraw":   mod_draw,
        "modAway":   mod_away,
        # AI Preview
        "aiPreview":     (ai_previews or {}).get(pick_key, {}).get("text"),
        "aiTgSnippet":   (ai_previews or {}).get(pick_key, {}).get("tgSnippet"),
        # Player Spotlights
        "playerSpotlights": _match_player_spotlights(wm, home_id, away_id),
        # Aufstellung (wm_lineups.json, ~T-1h) — Formation/Trainer/Start-XI/Bank
        "lineups": _lineup_for(home_id, away_id),
        # Serien (compute_streaks) — Heim/Auswärts-passend, lebendig (Matchup + Signale + seqViz)
        "streaks": _streaks_for_match(home_id, away_id),
        # Squad key players (with extended stats: shots, cards, rating, etc.)
        "squads": {
            home_id: wm.get("squads", {}).get(home_id),
            away_id: wm.get("squads", {}).get(away_id),
        },
        # Corner averages per team (from fetch_wm_corners.py)
        "cornersHome": wm.get("cornersForm", {}).get(home_id),
        "cornersAway": wm.get("cornersForm", {}).get(away_id),
        # Injuries & Suspensions (from fetch_wm_injuries.py, ab WM-Start)
        "injuriesHome": wm.get("injuries", {}).get(home_id, {}).get("players"),
        "injuriesAway": wm.get("injuries", {}).get(away_id, {}).get("players"),
        # Bet Insights + Polymarket + Player Props
        "betInsights":   bet_insights,
        "polyData":      poly_out,
        "pinnOdds":      pinn_odds,
        "softOdds":      soft_odds,
        "smartMoney":    smart_money,
        "polyMoney":     poly_money,
        "betfair":       betfair_block,
        "consensus":     consensus_block,
        "playerProps":   player_props_out,
        # Data sections
        "picks":         picks_raw,
        "odds":          odds_out,
        "oddsOpen":      odds_raw.get("odds_open") if odds_raw else None,
        "oddsHistory":   build_odds_history(history or {}, odds_key),
        "homeForm":      home_form,
        "awayForm":      away_form,
        "h2h":           h2h_out,
        "homeTeams":     group_teams,
        "groupFixtures": group_fixtures,
        # Meta — ISO 8601 für browser-kompatibles Parsing (Safari/Firefox sind strikt).
        # Vorher "06.06.2026 06:57 UTC" → Safari gab Invalid Date → "Aktualisiert vor 43866m" Bug.
        "generatedAt":      datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generatedAtHuman": datetime.utcnow().strftime("%d.%m.%Y %H:%M UTC"),  # für Anzeige falls gebraucht
    }
    return slug, payload


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    wm = load_json(WM_FILE)
    if not wm:
        print(f"ERROR: {WM_FILE} not found.")
        return

    history     = load_json(HISTORY_FILE) or {}
    ai_previews = wm.get("aiPreviews", {})
    poly_raw    = load_json(POLY_FILE) or {}
    poly_lookup = {f["key"]: f for f in poly_raw.get("allFixtures", [])}
    print(f"  Odds history: {len(history)} Fixtures mit Snapshots")
    print(f"  AI Previews: {len(ai_previews)} gecacht")
    print(f"  Polymarket:  {len(poly_lookup)} Fixtures geladen")

    # Build flat team lookup {id -> team_dict}
    team_lookup = {}
    for group_data in wm["groups"].values():
        for t in group_data.get("teams", []):
            team_lookup[t["id"]] = t

    generated = 0
    slugs = []

    # Betfair-Exchange-Snapshot (31.07.2026): einmal laden → Event-Pages backen Geld-Verteilung + ×-Norm.
    _bf_snaps, _bf_norm, _bf_fuzzy = load_betfair()

    # Liga: nur „live" Spiele bepagen — sonst 1066 statt ~40 Seiten. „Live" =
    #   Quoten da  ODER  ≤2 Wochen  ODER  in den nächsten MATCH_PAGE_MDS Spieltagen der
    #   eigenen Gruppe. Die Matchday-Klausel deckt die Vorsaison ab: Top-5 startet >14 Tage
    #   entfernt, die Karten zeigen aber schon MD1–2 → ohne sie 404 auf jeder Vorsaison-
    #   Event-Page (31.07.2026, Lucas: „Event-Pages der Cards funktionieren nicht mehr").
    MATCH_PAGE_MDS = 3
    _odds = wm.get("odds") or {}
    _two_weeks = (datetime.utcnow().date() + timedelta(days=14)).isoformat()
    _today = datetime.utcnow().date().isoformat()

    def _mdnum(m):
        try:
            return float(m)
        except Exception:
            return 9999.0

    # {(home,away,date)} der Fixtures in den nächsten MATCH_PAGE_MDS Spieltagen JE Gruppe —
    # exakt das, was die Karten verlinken. Bounded (~Ligen × MDs × Spiele), keine 1000+-Explosion.
    _card_keys = set()
    for _g in wm["groups"].values():
        _up = [f for f in _g.get("fixtures", [])
               if (f.get("date") or "")[:10] >= _today and f.get("matchday") not in (None, "")]
        _mds = sorted({f.get("matchday") for f in _up}, key=_mdnum)[:MATCH_PAGE_MDS]
        for f in _up:
            if f.get("matchday") in _mds:
                _card_keys.add((f.get("home"), f.get("away"), (f.get("date") or "")[:10]))

    for group_id, group_data in wm["groups"].items():
        for fixture in group_data.get("fixtures", []):
            home_id = fixture.get("home")
            away_id = fixture.get("away")
            if not home_id or not away_id:
                continue
            if _IS_LIGA:
                _d = (fixture.get("date") or "")[:10]
                _live = ((f"{home_id}-{away_id}" in _odds)
                         or (_today <= _d <= _two_weeks)
                         or ((home_id, away_id, _d) in _card_keys))
                if not _live:
                    continue
            if home_id not in team_lookup or away_id not in team_lookup:
                print(f"  SKIP: unknown team {home_id} or {away_id}")
                continue

            slug, payload = build_payload(group_id, group_data, fixture, team_lookup, wm, history, ai_previews, poly_lookup, _bf_snaps, _bf_norm, _bf_fuzzy)
            out_path = os.path.join(DATA_DIR, f"{slug}.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
            slugs.append(slug)
            generated += 1
            print(f"  ✓ {payload['home']} vs {payload['away']}  [{slug}.json]")

    # KO-Spiele (30.06.2026, Lucas: „Event-Pages komplett leer in der KO-Phase"): liegen in koFixtures,
    # nicht groups → wurden nie bepaged. Synthetische „KO"-Gruppe mit globaler Team-Union; der Slug
    # (wm-{h}-vs-{a}-{date}) matcht exakt den [↗ Analyse]-Link der KO-Card. Nur bothResolved Paarungen.
    if not _IS_LIGA:
        _ko_group = {"name": "K.-o.-Runde", "teams": list(team_lookup.values()), "fixtures": []}
        for fixture in (wm.get("koFixtures") or []):
            home_id, away_id = fixture.get("home"), fixture.get("away")
            if not home_id or not away_id:
                continue
            if home_id not in team_lookup or away_id not in team_lookup:
                print(f"  SKIP KO: unknown team {home_id} or {away_id}")
                continue
            slug, payload = build_payload("KO", _ko_group, fixture, team_lookup, wm,
                                          history, ai_previews, poly_lookup, _bf_snaps, _bf_norm, _bf_fuzzy)
            out_path = os.path.join(DATA_DIR, f"{slug}.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
            slugs.append(slug)
            generated += 1
            print(f"  ✓ {payload['home']} vs {payload['away']}  [KO {slug}.json]")

    # Index (dataset-bewusst: wm-index.json bzw. liga-index.json)
    index_path = os.path.join(BASE, "matches", f"{_PFX}-index.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump({
            "slugs": slugs,
            "generated": datetime.utcnow().isoformat(),
            "count": generated,
        }, f, ensure_ascii=False, separators=(",", ":"))

    print(f"\n✅ Generated {generated} {_PFX.upper()} match pages → matches/data/{_PFX}-*.json")
    print(f"   Index: matches/{_PFX}-index.json")
    print(f"   Template: matches/wm-match.html")


if __name__ == "__main__":
    main()
