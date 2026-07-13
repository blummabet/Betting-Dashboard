#!/usr/bin/env python3
"""
liga_backtest.py — Signal-Backtest auf Liga-Historie (26.06.2026, Lucas: „damit wir gute Wetten
kriegen"). PILOT: Premier League, letzte abgeschlossene Saison, Trefferquote OHNE Quoten.

Idee: Jedes vergangene Spiel chronologisch durchgehen, den Pre-Match-Zustand (Form/Tabelle/H2H zum
Spielzeitpunkt) rekonstruieren, durch die ECHTE Signal-Engine (evaluate_signals) schicken und
messen, wie oft jedes Signal richtig liegt. Validiert die Daten-Signale (form_trend, h2h_pattern,
league_pressure) gegen die Realität → primt später die Liga-Gewichte.

NICHT im Pilot: xG-Signale (brauchen pro Spiel /fixtures/statistics → schwer, Phase 2) und Steam
(historische Linienbewegung existiert nicht → nur vorwärts paper-tradebar). Quoten/ROI = Phase 2.

Reine Funktionen (Rekonstruktion + Aggregation) sind testbar; main() holt via API-Football.
"""
from __future__ import annotations

import http.client
import json
import os
from collections import defaultdict
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
APIF_HOST = "v3.football.api-sports.io"
APIF_KEY = os.environ.get("APISPORTS_KEY", "")
import cocobet_dataset as D
# 13.07.2026: datensatz-eigen — sonst überschriebe ein MLS-Lauf den Liga-Report (und umgekehrt).
REPORT_FILE = str(D.file("wm_backtest_report.json", "liga_backtest_report.json"))

# Liga-Code → (API-Football league_id, football-data CSV-Code oder None)
# 13.07.2026 (Lucas: „Backtest VOR dem Lineup-Watcher — wir starten in Runde 16, wir können nicht
# 10 Runden lang lernen"). MLS aufgenommen. football-data.co.uk führt die MLS nicht in der
# Standard-Liste → fd_code None → KEINE historischen Closing-Quoten.
# Das ist verkraftbar: prime_liga_priors baut die Priors ausschließlich aus TREFFERQUOTE und
# Anzahl der Calls (build_priors liest hitRate/calls) — Quoten liefern nur ROI/CLV als Beiwerk.
# Für MLS bleiben diese Felder im Report also leer, die Priors entstehen trotzdem.
LEAGUES = {"ENG": (39, "E0"), "ESP": (140, "SP1"), "GER": (78, "D1"),
           "ITA": (135, "I1"), "FRA": (61, "F1"),
           "MLS": (253, None)}
VALUE_THRESHOLDS = [0.0, 2.0, 4.0]   # Conviction-Schwellen (combined_score_pp) für den Value-Filter
WARMUP_GAMES = 4          # erst werten, wenn beide Teams ≥4 Spiele Historie haben
FORM_N = 5                # Form über die letzten N Spiele
CANDIDATE_MARKETS = ["Heimsieg", "Auswärtssieg", "Über 2.5 Tore", "Unter 2.5 Tore"]


# ───────────────────────── Reine Rekonstruktion ─────────────────────────

def market_won(market: str, hs: int, as_: int) -> bool:
    total = hs + as_
    if market == "Heimsieg":        return hs > as_
    if market == "Auswärtssieg":    return as_ > hs
    if market == "Über 2.5 Tore":   return total > 2.5
    if market == "Unter 2.5 Tore":  return total < 2.5
    return False


def form_entry(results: list) -> dict:
    """results = Liste der letzten Spiele eines Teams als (gf, ga) → {games, avgScored, avgConceded}."""
    last = results[-FORM_N:]
    n = len(last)
    if n == 0:
        return {"games": 0, "avgScored": 0.0, "avgConceded": 0.0}
    return {"games": n,
            "avgScored": round(sum(g for g, _ in last) / n, 3),
            "avgConceded": round(sum(a for _, a in last) / n, 3)}


def xg_entry(results: list) -> dict:
    """results = [(xgFor, xgAgainst)] eines Teams (bis VOR dem Spiel) → xg_strength-Format.
    source='apif_real' ab 3 Spielen → xg_strength nutzt ECHTES xG (sonst Form-Fallback, Phase 1)."""
    last = results[-10:]
    n = len(last)
    if n < 3:
        return {"games": n, "xgForAvg": None, "xgAgainstAvg": None, "xgGames": n, "source": "none"}
    return {"games": n, "xgGames": n, "source": "apif_real",
            "xgForAvg": round(sum(f for f, _ in last) / n, 3),
            "xgAgainstAvg": round(sum(a for _, a in last) / n, 3)}


def standings_rows(table: dict) -> list:
    """table = {teamId: {points, gf, ga}} → sortierte Tabellen-Zeilen mit pos (FIFA-Tiebreaker)."""
    rows = [{"team": t, "points": d["points"], "gd": d["gf"] - d["ga"], "gf": d["gf"]}
            for t, d in table.items()]
    rows.sort(key=lambda r: (-r["points"], -r["gd"], -r["gf"], r["team"]))
    for i, r in enumerate(rows):
        r["pos"] = i + 1
    return rows


def _pnl(won: bool, odds) -> float | None:
    """1u-Einsatz auf die Pick-Seite zur Einstiegs-Quote → P&L. None wenn keine Quote."""
    if not odds or odds <= 1.0:
        return None
    return round((odds - 1.0) if won else -1.0, 3)


def clv_pct(entry, close) -> float | None:
    """Closing Line Value: Einstiegs- vs Closing-Quote derselben Pick-Seite. >0 = wir haben einen
    BESSEREN Preis bekommen als der Markt schloss (Linie lief zu uns hin → Signal lief dem Markt
    voraus). Der wahre Steam-Test: positiver CLV = grün, auch wenn der reine ROI negativ ist."""
    if not entry or not close or entry <= 1.0 or close <= 1.0:
        return None
    return round((entry / close - 1.0) * 100, 2)


def aggregate(ledger: list) -> dict:
    """ledger = [{signal, market, score, won, odds?}] → Richtungs-Trefferquote + ROI (Phase 2) pro
    Signal/Markt. ROI: jeder positive Richtungs-Call = 1u auf den Markt zur Closing-Quote."""
    def _mk():
        return {"calls": 0, "correct": 0, "bets": 0, "pnl": 0.0, "stake": 0.0,
                "clvSum": 0.0, "clvN": 0, "clvPos": 0}
    per_sig = defaultdict(_mk)
    per_sig_mkt = defaultdict(_mk)
    for e in ledger:
        if abs(e["score"]) < 0.3:        # nur echte Richtungs-Calls
            continue
        correct = (e["score"] > 0 and e["won"]) or (e["score"] < 0 and not e["won"])
        # ROI + CLV nur bei POSITIVEM Call (= „wir würden den Markt spielen") + vorhandener Quote.
        pnl = _pnl(e["won"], e.get("odds")) if e["score"] > 0 else None
        clv = clv_pct(e.get("odds"), e.get("oddsClose")) if e["score"] > 0 else None
        for key, bucket in ((e["signal"], per_sig), ((e["signal"], e["market"]), per_sig_mkt)):
            b = bucket[key]
            b["calls"] += 1
            b["correct"] += 1 if correct else 0
            if pnl is not None:
                b["bets"] += 1
                b["pnl"] += pnl
                b["stake"] += 1.0
            if clv is not None:
                b["clvSum"] += clv
                b["clvN"] += 1
                b["clvPos"] += 1 if clv > 0 else 0
    def _row(v):
        roi = round(v["pnl"] / v["stake"] * 100, 1) if v["stake"] else None
        return {"calls": v["calls"], "correct": v["correct"],
                "hitRate": round(v["correct"] / v["calls"], 3) if v["calls"] else None,
                "bets": v["bets"], "roiPct": roi, "pnl": round(v["pnl"], 2),
                "avgClvPct": round(v["clvSum"] / v["clvN"], 2) if v["clvN"] else None,
                "beatCloseRate": round(v["clvPos"] / v["clvN"], 3) if v["clvN"] else None,
                "clvN": v["clvN"]}
    return {
        "perSignal": {k: _row(v) for k, v in sorted(per_sig.items(), key=lambda kv: -kv[1]["calls"])},
        "perSignalMarket": {f"{k[0]}|{k[1]}": _row(v)
                            for k, v in sorted(per_sig_mkt.items(), key=lambda kv: -kv[1]["calls"])},
    }


def replay(matches: list, evaluate_fn, league: str = "ENG"):
    """matches = chronologisch sortierte [{home, away, hs, as_, matchday}]. evaluate_fn(pick, ctx)
    = registry.evaluate_signals (injizierbar → testbar). Gibt (ledger, system_ledger) zurück:
    ledger = pro-Signal-Calls; system_ledger = combined_score_pp pro (Spiel,Markt) für Value-Filter."""
    # 13.07.2026: Spielplan je Team → fixture_congestion (Ruhetage) kann im Backtest überhaupt
    # erst feuern. Vorher fehlte team_schedule im Replay-Kontext, das Signal bekam also nie einen
    # Call und damit auch nie einen Prior — obwohl es live regelmäßig anschlägt (MLS spielt viel
    # unter der Woche). Gilt für Liga genauso.
    schedule: dict = defaultdict(list)             # teamId → [Datums-Strings]
    for _m in matches:
        for _t in (_m.get("home"), _m.get("away")):
            if _t and _m.get("date"):
                schedule[_t].append(str(_m["date"])[:10])
    for _t in schedule:
        schedule[_t] = sorted(set(schedule[_t]))

    team_results: dict = defaultdict(list)         # teamId → [(gf, ga)]
    team_xg: dict = defaultdict(list)              # teamId → [(xgFor, xgAgainst)]  (Phase 2)
    table: dict = defaultdict(lambda: {"points": 0, "gf": 0, "ga": 0})
    h2h: dict = defaultdict(lambda: {"games": 0, "homeWins": 0, "draws": 0, "awayWins": 0})
    ledger, system = [], []
    for m in matches:
        h, a, hs, as_, md = m["home"], m["away"], m["hs"], m["as_"], m.get("matchday")
        m_odds = m.get("odds") or {}
        m_close = m.get("oddsClose") or {}
        # ── Pre-Match-Zustand (VOR diesem Spiel) ──
        if len(team_results[h]) >= WARMUP_GAMES and len(team_results[a]) >= WARMUP_GAMES:
            pair = h2h[tuple(sorted((h, a)))]
            ctx = {
                "home_id": h, "away_id": a, "group_id": league, "matchday": md,
                "form": {h: form_entry(team_results[h]), a: form_entry(team_results[a])},
                "h2h": dict(pair),
                "standings": {league: standings_rows(table)},
                # Phase 2: echtes xG point-in-time (xg_strength nutzt es statt Form-Fallback).
                "xg_stats": {h: xg_entry(team_xg[h]), a: xg_entry(team_xg[a])},
                # 13.07.2026: Erschöpfung/Spielstau — rest_days rechnet gegen das Spieldatum.
                "team_schedule": dict(schedule),
                "current_match_date": str(m.get("date") or "")[:10],
            }
            for market in CANDIDATE_MARKETS:
                res = evaluate_fn({"market": market, "odds": m_odds.get(market, 2.0)}, ctx)
                won = market_won(market, hs, as_)
                for sig in (res.get("signals") or []):
                    ledger.append({"signal": sig["name"], "market": market,
                                   "score": sig.get("score", 0), "won": won,
                                   "odds": m_odds.get(market), "oddsClose": m_close.get(market)})
                system.append({"market": market, "combined": res.get("combined_score_pp", 0),
                               "won": won, "odds": m_odds.get(market),
                               "oddsClose": m_close.get(market)})
        # ── Zustand NACH dem Spiel fortschreiben ──
        team_results[h].append((hs, as_))
        team_results[a].append((as_, hs))
        _xg = m.get("xg") or {}
        if _xg.get("home") is not None and _xg.get("away") is not None:
            team_xg[h].append((_xg["home"], _xg["away"]))
            team_xg[a].append((_xg["away"], _xg["home"]))
        table[h]["gf"] += hs; table[h]["ga"] += as_
        table[a]["gf"] += as_; table[a]["ga"] += hs
        if hs > as_:   table[h]["points"] += 3
        elif as_ > hs: table[a]["points"] += 3
        else:          table[h]["points"] += 1; table[a]["points"] += 1
        pr = h2h[tuple(sorted((h, a)))]
        pr["games"] += 1
        if hs > as_:   pr["homeWins" if h < a else "awayWins"] += 1
        elif as_ > hs: pr["awayWins" if h < a else "homeWins"] += 1
        else:          pr["draws"] += 1
    return ledger, system


def aggregate_system(system: list, thresholds=None) -> dict:
    """Value-Filter: setze 1u auf einen Markt nur, wenn combined_score_pp ≥ Schwelle. Pro Schwelle
    Trefferquote + ROI — zeigt, ob HÖHERE Conviction = bessere Wetten (statt jeden Favoriten)."""
    thresholds = thresholds if thresholds is not None else VALUE_THRESHOLDS
    out = {}
    for thr in thresholds:
        bets = wins = 0
        pnl = stake = 0.0
        clv_sum = 0.0; clv_n = clv_pos = 0
        for e in system:
            if e["combined"] < thr or thr <= 0 and e["combined"] <= 0:
                continue
            c = clv_pct(e.get("odds"), e.get("oddsClose"))
            if c is not None:
                clv_sum += c; clv_n += 1; clv_pos += 1 if c > 0 else 0
            p = _pnl(e["won"], e.get("odds"))
            if p is None:
                continue
            bets += 1; wins += 1 if e["won"] else 0
            pnl += p; stake += 1.0
        out[f">={thr}pp"] = {"bets": bets, "wins": wins,
                             "hitRate": round(wins / bets, 3) if bets else None,
                             "roiPct": round(pnl / stake * 100, 1) if stake else None,
                             "pnl": round(pnl, 2),
                             "avgClvPct": round(clv_sum / clv_n, 2) if clv_n else None,
                             "beatCloseRate": round(clv_pos / clv_n, 3) if clv_n else None}
    return out


# ───────────────────────── Live-Fetch (API-Football) ─────────────────────────

def _api_get(path: str) -> dict | None:
    if not APIF_KEY:
        return None
    try:
        conn = http.client.HTTPSConnection(APIF_HOST, timeout=20)
        conn.request("GET", path, headers={"x-apisports-key": APIF_KEY})
        resp = conn.getresponse(); raw = resp.read().decode("utf-8", "replace"); conn.close()
        return json.loads(raw) if resp.status == 200 else None
    except Exception as e:
        print(f"  ⚠️  API {path}: {e}")
        return None


def _parse_round(s: str):
    import re
    m = re.search(r"(\d+)\s*$", str(s or ""))
    return int(m.group(1)) if m else None


def fetch_league_matches(league_id: int, season: int) -> list:
    """Abgeschlossene Liga-Spiele der Saison → chronologische Match-Liste für replay()."""
    data = _api_get(f"/fixtures?league={league_id}&season={season}") or {}
    out = []
    for it in (data.get("response") or []):
        st = (((it.get("fixture") or {}).get("status") or {}).get("short")) or ""
        if st not in ("FT", "AET", "PEN"):
            continue
        tm, gl, lg, fx = it.get("teams") or {}, it.get("goals") or {}, it.get("league") or {}, it.get("fixture") or {}
        h, a = (tm.get("home") or {}), (tm.get("away") or {})
        if gl.get("home") is None or gl.get("away") is None:
            continue
        out.append({"home": str(h.get("id")), "away": str(a.get("id")),
                    "homeName": h.get("name"), "awayName": a.get("name"),
                    "fid": (fx.get("id")),
                    "hs": int(gl["home"]), "as_": int(gl["away"]),
                    "matchday": _parse_round(lg.get("round")), "date": (fx.get("date") or "")})
    out.sort(key=lambda m: m["date"])
    return out


def fetch_fixture_xg(fid, cache: dict) -> dict | None:
    """Echtes xG pro Team aus /fixtures/statistics (gecacht je fixture-id). {home: xg, away: xg}
    bezogen auf die Heim/Auswärts-Seiten des Fixtures (per Team-ID gemappt im Aufrufer)."""
    key = str(fid)
    if key in cache:
        return cache[key]
    data = _api_get(f"/fixtures/statistics?fixture={fid}")
    out = {}
    for blk in ((data or {}).get("response") or []):
        tid = str(((blk.get("team") or {}).get("id")))
        xg = None
        for s in (blk.get("statistics") or []):
            if str(s.get("type", "")).lower() == "expected_goals" and s.get("value") not in (None, ""):
                try:
                    xg = float(str(s["value"]).replace(",", "."))
                except Exception:
                    xg = None
        if xg is not None:
            out[tid] = xg
    cache[key] = out
    return out


# ── Historische Closing-Quoten: football-data.co.uk (gratis CSV pro Liga/Saison) ──
FD_LEAGUE = {"ENG": "E0", "ESP": "SP1", "GER": "D1", "ITA": "I1", "FRA": "F1"}


def _fd_season_code(season: int) -> str:
    """2025 → '2526' (football-data Saison-Code Startjahr+Folgejahr, 2-stellig)."""
    return f"{season % 100:02d}{(season + 1) % 100:02d}"


def parse_fd_csv(text: str) -> list[dict]:
    """football-data-CSV → [{date, home, away, oddsH, oddsD, oddsA, o25, u25}] (reine Funktion)."""
    import csv
    import io
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        try:
            home, away = r.get("HomeTeam"), r.get("AwayTeam")
            if not home or not away:
                continue
            def _f(*keys):
                for k in keys:
                    v = r.get(k)
                    if v not in (None, ""):
                        try:
                            return float(v)
                        except Exception:
                            pass
                return None
            rows.append({"date": r.get("Date"), "home": home, "away": away,
                         # Einstieg = Vor-Match-Quote (Tage vor Anpfiff).
                         "oddsH": _f("AvgH", "B365H", "PSH"), "oddsD": _f("AvgD", "B365D", "PSD"),
                         "oddsA": _f("AvgA", "B365A", "PSA"),
                         "o25": _f("Avg>2.5", "B365>2.5", "P>2.5"),
                         "u25": _f("Avg<2.5", "B365<2.5", "P<2.5"),
                         # Closing = C-Spalten (kurz vor Anpfiff) → für CLV (26.06.2026, Lucas).
                         "oddsHc": _f("AvgCH", "B365CH", "PSCH"), "oddsAc": _f("AvgCA", "B365CA", "PSCA"),
                         "o25c": _f("AvgC>2.5", "B365C>2.5", "PC>2.5"),
                         "u25c": _f("AvgC<2.5", "B365C<2.5", "PC<2.5")})
        except Exception:
            continue
    return rows


def _http_get(url: str) -> str | None:
    import urllib.request
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CocoBet/1.0"})
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.read().decode("utf-8", "replace")
    except Exception as e:
        print(f"  ⚠️  football-data {url}: {e}")
        return None


def _fd_date_iso(d: str) -> str:
    """football-data Datum DD/MM/YY(YY) → YYYY-MM-DD."""
    parts = (d or "").split("/")
    if len(parts) != 3:
        return ""
    dd, mm, yy = parts
    yy = ("20" + yy) if len(yy) == 2 else yy
    return f"{yy}-{int(mm):02d}-{int(dd):02d}"


def attach_odds(matches: list, fd_rows: list) -> int:
    """football-data-Zeilen per Datum + Teamname an die Matches hängen (m['odds']). Anzahl gematcht."""
    from fetch_liga_odds import _names_match
    n = 0
    for m in matches:
        md = (m.get("date") or "")[:10]
        hn, an = m.get("homeName"), m.get("awayName")
        for r in fd_rows:
            if _fd_date_iso(r["date"]) == md and _names_match(r["home"], hn) and _names_match(r["away"], an):
                m["odds"] = {"Heimsieg": r["oddsH"], "Auswärtssieg": r["oddsA"],
                             "Über 2.5 Tore": r["o25"], "Unter 2.5 Tore": r["u25"]}
                m["oddsClose"] = {"Heimsieg": r.get("oddsHc"), "Auswärtssieg": r.get("oddsAc"),
                                  "Über 2.5 Tore": r.get("o25c"), "Unter 2.5 Tore": r.get("u25c")}
                n += 1
                break
    return n


def _default_leagues() -> list:
    """Welche Ligen backtesten? Im MLS-Datensatz NUR MLS (sonst primen wir die MLS-Gewichte mit
    europäischen Ergebnissen — genau die Cross-Dataset-Kontamination, die wir überall entfernen)."""
    if D.active_dataset() == "mls":
        return ["MLS"]
    return [c for c in LEAGUES if c != "MLS"]          # Top-5 = Liga-Datensatz


def _default_seasons() -> list:
    """13.07.2026 (Lucas: „wir starten in Runde 16, wir können nicht 10 Runden lang lernen").

    Europa-Ligen: die abgeschlossene Vorsaison (year-1).
    MLS: Kalenderjahr-Saison → die abgeschlossene VORSAISON **plus die laufende**. Die laufende
    liefert 218 gespielte Spiele (Runde 15/34) — wertvoll, weil aktueller Kader/Trainer; die
    Vorsaison liefert die Masse (~510 Spiele) für belastbare Trefferquoten. Zusammen ist die
    Stichprobe groß genug für MIN_CALLS=50 je Signal.
    """
    jetzt = datetime.utcnow().year
    if D.active_dataset() == "mls":
        return [jetzt - 1, jetzt]
    return [jetzt - 1]


def main():
    import time
    _env_season = os.environ.get("BACKTEST_SEASON")    # "2025" oder "2025,2026"
    seasons = ([int(x) for x in _env_season.split(",") if x.strip()]
               if _env_season else _default_seasons())
    only = os.environ.get("BACKTEST_LEAGUES")          # optional "ENG,ESP"
    leagues = [c for c in (only.split(",") if only else _default_leagues()) if c in LEAGUES]
    print(f"=== liga_backtest.py — {','.join(leagues)} · Saison(s) {','.join(map(str,seasons))} "
          f"· Datensatz {D.active_dataset()} ===")
    if not APIF_KEY:
        print("  ❌  APISPORTS_KEY nicht gesetzt — übersprungen.")
        return

    CACHE = str(D.file("wm_backtest_cache.json", "liga_backtest_cache.json"))
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    import sharp_signals.registry as R
    weights = R.load_signal_weights()

    all_ledger, all_system = [], []
    per_league_meta = {}
    for code, season in [(c, s_) for c in leagues for s_ in seasons]:
        lid, fd_code = LEAGUES[code]
        matches = fetch_league_matches(lid, season)
        if not matches:
            print(f"  {code} {season}: 0 Spiele — übersprungen")
            continue
        # Echtes xG je Spiel (gecacht).
        xg_n = 0
        for m in matches:
            if not m.get("fid"):
                continue
            stats = fetch_fixture_xg(m["fid"], cache)
            if stats and m["home"] in stats and m["away"] in stats:
                m["xg"] = {"home": stats[m["home"]], "away": stats[m["away"]]}
                xg_n += 1
            time.sleep(0.2)
        # Historische Closing-Quoten (football-data.co.uk, pro Liga). Ohne CSV-Quelle (MLS) → 0:
        # Trefferquoten-Priors funktionieren trotzdem, nur ROI/CLV bleiben leer.
        odds_n = 0
        if fd_code:
            fd_text = _http_get(f"https://www.football-data.co.uk/mmz4281/{_fd_season_code(season)}/{fd_code}.csv")
            odds_n = attach_odds(matches, parse_fd_csv(fd_text)) if fd_text else 0
        led, sysd = replay(matches, lambda pick, ctx: R.evaluate_signals(pick, ctx, weights), league=code)
        all_ledger += led; all_system += sysd
        per_league_meta[f"{code}-{season}"] = {"matches": len(matches), "xg": xg_n, "odds": odds_n}
        print(f"  {code} {season}: {len(matches)} Spiele · xG {xg_n} · Quoten {odds_n}")
    json.dump(cache, open(CACHE, "w"), ensure_ascii=False)

    report = aggregate(all_ledger)
    report["valueFilter"] = aggregate_system(all_system)
    report["_meta"] = {"leagues": leagues, "season": season, "perLeague": per_league_meta,
                       "ledgerEntries": len(all_ledger), "generatedAt": datetime.utcnow().isoformat()}
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n  Signal: Trefferquote | ROI (Einstieg) | CLV (Einstieg vs Closing):")
    for sig, d in report["perSignal"].items():
        roi = f"{d['roiPct']:+.1f}%" if d.get("roiPct") is not None else "—"
        clv = f"{d['avgClvPct']:+.2f}%" if d.get("avgClvPct") is not None else "—"
        beat = f"{d['beatCloseRate']*100:.0f}%" if d.get("beatCloseRate") is not None else "—"
        print(f"    {sig:18} {d['hitRate']}  ({d['correct']}/{d['calls']})   ROI {roi}   "
              f"CLV {clv} (schlägt Closing {beat})")
    print(f"\n  Value-Filter (ab Conviction-Schwelle, combined_score_pp):")
    for thr, d in report["valueFilter"].items():
        roi = f"{d['roiPct']:+.1f}%" if d.get("roiPct") is not None else "—"
        clv = f"{d['avgClvPct']:+.2f}%" if d.get("avgClvPct") is not None else "—"
        beat = f"{d['beatCloseRate']*100:.0f}%" if d.get("beatCloseRate") is not None else "—"
        print(f"    {thr:8} Treffer {d['hitRate']}  ROI {roi}  CLV {clv} (schlägt Closing {beat})  ({d['bets']} Wetten)")
    print(f"\n  ✅ Report → {os.path.basename(REPORT_FILE)}")


if __name__ == "__main__":
    main()
