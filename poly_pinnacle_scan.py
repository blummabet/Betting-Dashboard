#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""poly_pinnacle_scan.py — Broad Pinnacle×Poly Lag-Scanner (04.08.2026, Lucas).

MESSMODUL, keine Picks/Trades. Paart je aktiver Liga das Polymarket-1X2 mit Pinnacle (via The Odds
API) und schreibt Zeit-Snapshots (pinn-fair vs poly-prob je Ausgang) mit. Das Sheet
(poly_pinnacle_stats.py, Phase 2) rechnet daraus den Round-Trip-Backtest: Einstieg auf Polys
nachhinkendem Preis, sobald Pinnacle sich bewegt; Ausstieg, sobald Poly konvergiert.

Roster-frei: Poly-Event ↔ Pinnacle-Event werden direkt über Teamname+Datum gepaart (kein Rückgriff
auf unsere Team-IDs). Poly-1X2 kommt aus groupItemThreshold (0=Heim,1=Remis,2=Auswärts).

Laufkosten schonend: pro Liga zuerst Poly holen; nur wenn Poly Spiele hat, wird die (kostende)
Odds-API für Pinnacle gefragt. h2h-only, regions=eu,uk.
"""
import json
import os
import re
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

# ── Liga-Register: Poly-series_id ↔ The-Odds-API sport_key. Poly-IDs im Browser gegen gamma /sports
#    verifiziert (04.08.2026). Top-5 sind vorsaisonal leer → schaden nicht (Poly-Call liefert 0, dann skip).
LEAGUES = [
    {"name": "Champions League",  "poly": "10204", "odds": ["soccer_uefa_champs_league", "soccer_uefa_champs_league_qualification"]},
    {"name": "Europa League",     "poly": "10209", "odds": ["soccer_uefa_europa_league", "soccer_uefa_europa_league_qualification"]},
    {"name": "La Liga",           "poly": "10193", "odds": "soccer_spain_la_liga"},
    {"name": "Eredivisie",        "poly": "10286", "odds": "soccer_netherlands_eredivisie"},
    {"name": "Primeira Liga",     "poly": "10330", "odds": "soccer_portugal_primeira_liga"},
    {"name": "Championship",      "poly": "10355", "odds": "soccer_efl_champ"},
    {"name": "Brasileirão",       "poly": "10359", "odds": "soccer_brazil_campeonato"},
    {"name": "Belgien Pro League","poly": "12351", "odds": "soccer_belgium_first_div"},
    {"name": "Eliteserien (NOR)", "poly": "10362", "odds": "soccer_norway_eliteserien"},
    {"name": "Superliga (DEN)",   "poly": "10363", "odds": "soccer_denmark_superliga"},
    {"name": "J-League",          "poly": "10360", "odds": "soccer_japan_j_league"},
    {"name": "K-League",          "poly": "10444", "odds": "soccer_korea_kleague1"},
    {"name": "MLS",               "poly": "10189", "odds": "soccer_usa_mls"},
    {"name": "Liga MX",           "poly": "10290", "odds": "soccer_mexico_ligamx"},
    {"name": "Süper Lig (TUR)",   "poly": "10292", "odds": "soccer_turkey_super_league"},
    {"name": "Premier League",    "poly": "10188", "odds": "soccer_epl"},
    {"name": "Bundesliga",        "poly": "10194", "odds": "soccer_germany_bundesliga"},
    {"name": "Serie A",           "poly": "10203", "odds": "soccer_italy_serie_a"},
    {"name": "Ligue 1",           "poly": "10195", "odds": "soccer_france_ligue_one"},
]

STORE_FILE   = "pinnacle_poly_scan.json"
GAMMA_TMPL   = ("https://gamma-api.polymarket.com/events?series_id={sid}"
                "&limit=100&offset={off}&active=true&closed=false&order=startDate&ascending=false")
GAMMA_PAGES  = 4          # 400 Events Headroom je Liga
PRUNE_AFTER_H = 6.0       # Spiele >6h nach Anpfiff aus dem Store werfen
MAX_SNAPS    = 300        # Snapshots je Spiel deckeln (~10 Tage @ 2/h)
_DERIV_RE    = re.compile(r"-(halftime|second-half|first-half|exact-score|first-to-score|"
                          r"corners?|odd-even|winner|top-\d|to-score)")
UA = {"User-Agent": "BetEdge/1.0 (+https://github.com/blummabet)", "Accept": "application/json"}


def _http_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read())


def _devig_1x2(hw, dr, aw):
    """Decimal 1X2 → faire Wkt (Vig raus). Implausible/fehlende Quoten → None."""
    try:
        hw, dr, aw = float(hw), float(dr), float(aw)
    except (TypeError, ValueError):
        return None
    if min(hw, dr, aw) <= 1.0 or max(hw, dr, aw) > 100:
        return None
    ih, idr, ia = 1.0 / hw, 1.0 / dr, 1.0 / aw
    m = ih + idr + ia
    if m <= 0:
        return None
    return (round(ih / m, 4), round(idr / m, 4), round(ia / m, 4))


# ── Polymarket: Basis-Moneyline je Liga (roster-frei) ───────────────────────────────────────────
def fetch_poly_games(series_id, http=_http_json):
    out, seen = [], set()
    for page in range(GAMMA_PAGES):
        try:
            evs = http(GAMMA_TMPL.format(sid=series_id, off=page * 100))
        except Exception as e:
            print(f"    ⚠️  Poly {series_id} Seite {page}: {e}")
            break
        if not isinstance(evs, list) or not evs:
            break
        for e in evs:
            slug = e.get("slug", "")
            if not slug or _DERIV_RE.search(slug) or slug in seen:
                continue
            teams = e.get("teams") or []
            if len(teams) < 2:
                continue
            hw = dr = aw = None
            for m in (e.get("markets") or []):
                try:
                    pr = json.loads(m.get("outcomePrices", "[]") or "[]")
                except (ValueError, TypeError):
                    pr = []
                if not pr:
                    continue
                yes = float(pr[0])
                thr = str(m.get("groupItemThreshold", ""))
                gt = str(m.get("groupItemTitle", "")).lower()
                if thr == "0":
                    hw = yes
                elif thr == "1" or "draw" in gt or "remis" in gt:
                    dr = yes
                elif thr == "2":
                    aw = yes
            if hw is None or dr is None or aw is None:
                continue
            seen.add(slug)
            out.append({
                "slug": slug,
                "home": teams[0].get("name", ""),
                "away": teams[1].get("name", ""),
                "kickoff": e.get("startTime") or e.get("startDate") or e.get("gameStartTime"),
                "poly": [round(hw, 4), round(dr, 4), round(aw, 4)],
                "vol": round(float(e.get("volume") or 0), 0),
            })
        if len(evs) < 100:
            break
    return out


# ── Pinnacle (über The Odds API), h2h-only, sharp-priorisiert ─────────────────────────────────────
def fetch_pinn_games(sport_key, odds_get=None):
    """Gibt [{home,away,commence,pinn:[hw,dr,aw]faire Wkt, book, decimals:[..]}]. odds_get injizierbar."""
    if odds_get is None:
        from fetch_wm_odds import odds_get as _og, ODDS_KEY
        odds_get = lambda p: _og(p)  # noqa: E731
        key = ODDS_KEY
    else:
        key = os.environ.get("ODDS_API_KEY", "TESTKEY")
    from fetch_liga_odds import _best_book, _map_1x2, BOOK_PRIORITY
    keys = sport_key if isinstance(sport_key, list) else [sport_key]
    evs = []
    for sk in keys:
        path = (f"/v4/sports/{sk}/odds?apiKey={key}"
                f"&regions=eu,uk&markets=h2h&oddsFormat=decimal")
        d = odds_get(path)
        if isinstance(d, list):
            evs.extend(d)
    if not evs:
        return []
    out = []
    for e in evs:
        bk, outs = _best_book(e.get("bookmakers") or [], "h2h", BOOK_PRIORITY)
        if not outs:
            continue
        hw, dr, aw = _map_1x2(outs, e.get("home_team", ""), e.get("away_team", ""))
        fair = _devig_1x2(hw, dr, aw)
        if not fair:
            continue
        out.append({
            "home": e.get("home_team", ""), "away": e.get("away_team", ""),
            "commence": e.get("commence_time"), "book": bk,
            "pinn": list(fair), "dec": [hw, dr, aw],
        })
    return out


# ── Paaren (orientierungs-bewusst) + Snapshot bauen ──────────────────────────────────────────────
def pair_games(poly_games, pinn_games):
    """Je Poly-Spiel das passende Pinnacle-Spiel; Pinnacle-Wkt in Polys Heim/Auswärts-Rahmen gedreht."""
    from fetch_liga_odds import match_event_to_fixture
    pairs = []
    used = set()
    for pg in poly_games:
        for i, xg in enumerate(pinn_games):
            if i in used:
                continue
            ori = match_event_to_fixture(
                {"home_team": xg["home"], "away_team": xg["away"]}, pg["home"], pg["away"])
            if not ori:
                continue
            used.add(i)
            ph = xg["pinn"]
            pinn = ph if ori == "direct" else [ph[2], ph[1], ph[0]]   # swapped → hw/aw tauschen
            pairs.append({"poly": pg, "pinn_frame": pinn, "book": xg["book"], "ori": ori})
            break
    return pairs


def _kick_age_h(kickoff, now):
    if not kickoff:
        return None
    try:
        k = datetime.fromisoformat(str(kickoff).replace("Z", "+00:00"))
    except ValueError:
        return None
    if k.tzinfo is None:
        k = k.replace(tzinfo=timezone.utc)
    return (now - k).total_seconds() / 3600.0


def scan(leagues=None, poly_fetch=fetch_poly_games, pinn_fetch=fetch_pinn_games, now=None):
    """Ein Durchlauf: liefert {gameKey: snap-row}. now/Fetcher injizierbar für Tests."""
    now = now or datetime.now(timezone.utc)
    ts = now.isoformat()
    rows, n_leagues_active, n_pairs = {}, 0, 0
    for lg in (leagues or LEAGUES):
        pg = poly_fetch(lg["poly"])
        if not pg:
            continue
        n_leagues_active += 1
        xg = pinn_fetch(lg["odds"])
        if not xg:
            print(f"    · {lg['name']}: {len(pg)} Poly-Spiele, aber 0 Pinnacle (keine Paarung)")
            continue
        for pr in pair_games(pg, xg):
            g = pr["poly"]
            key = f"{lg['name']}|{g['home']}|{g['away']}|{str(g['kickoff'])[:10]}"
            rows[key] = {
                "league": lg["name"], "home": g["home"], "away": g["away"],
                "kickoff": g["kickoff"],
                "snap": {"ts": ts, "pinn": pr["pinn_frame"], "poly": g["poly"],
                         "vol": g["vol"], "book": pr["book"]},
            }
            n_pairs += 1
        print(f"    · {lg['name']}: {len(pg)} Poly · {len(xg)} Pinnacle · "
              f"{sum(1 for k in rows if rows[k]['league']==lg['name'])} gepaart")
    return rows, n_leagues_active, n_pairs, ts, now


def merge_store(store, rows, now):
    """Neue Snapshots an den Store hängen; alte Spiele prunen; Snaps deckeln."""
    games = store.setdefault("games", {})
    for key, r in rows.items():
        g = games.get(key)
        if not g:
            g = {k: r[k] for k in ("league", "home", "away", "kickoff")}
            g["snaps"] = []
            games[key] = g
        g["kickoff"] = r["kickoff"] or g.get("kickoff")
        g["snaps"].append(r["snap"])
        if len(g["snaps"]) > MAX_SNAPS:
            g["snaps"] = g["snaps"][-MAX_SNAPS:]
    # Prune: Spiele deutlich nach Anpfiff raus (Serie abgeschlossen; Backtest liest sie vorher aus)
    for key in list(games.keys()):
        age = _kick_age_h(games[key].get("kickoff"), now)
        if age is not None and age > PRUNE_AFTER_H:
            del games[key]
    return store


def main():
    print("=== poly_pinnacle_scan.py ===")
    try:
        with open(STORE_FILE, encoding="utf-8") as f:
            store = json.load(f)
    except (FileNotFoundError, ValueError):
        store = {}
    rows, n_active, n_pairs, ts, now = scan()
    store = merge_store(store, rows, now)
    store["_meta"] = {"generatedAt": ts, "leaguesActive": n_active, "pairsThisRun": n_pairs,
                      "gamesTracked": len(store.get("games", {}))}
    with open(STORE_FILE, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, separators=(",", ":"))
    print(f"  → {n_active} aktive Ligen · {n_pairs} Paarungen · "
          f"{len(store.get('games', {}))} Spiele im Store → {STORE_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
