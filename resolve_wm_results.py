#!/usr/bin/env python3
"""
resolve_wm_results.py — WM 2026 Bet-Resolver: P&L + CLV Tracking
==================================================================

Liest:
  · wm_auto_bets_placed.json  — automatisch platzierte Bets
  · picks_history.json        — manuell platzierte Bets (league='WM2026')
  · wm2026-data.json          — Spielergebnisse + Pinnacle-Closing-Odds

Schreibt wm_results.json:
  {
    "bets": [
      {
        "betKey":      "GER-CIV-heimsieg",
        "home":        "Deutschland",
        "away":        "Elfenbeinküste",
        "market":      "Heimsieg",
        "stake":       10.0,
        "polyPrice":   0.52,          ← Entry-Wahrscheinlichkeit (Polymarket)
        "polyOdds":    1.923,         ← 1/polyPrice = Dezimal-Quotient
        "pinnFair":    0.556,         ← Pinnacle fair probability bei Entry
        "pinnClose":   0.58,          ← Pinnacle fair probability beim Anpfiff (CLV-Basis)
        "clvPP":       +2.8,          ← (pinnClose - polyPrice) * 100 → positiv = gut
        "result":      "WIN",         ← WIN | LOSS | VOID | PENDING
        "pnl":         +9.23,         ← profit bei WIN, -stake bei LOSS, 0 bei VOID
        "score":       "2-1",
        "placedAt":    "2026-06-12T...",
        "resolvedAt":  "2026-06-12T..."
      }
    ],
    "summary": {
      "totalBets":    5,
      "resolved":     3,
      "pending":      2,
      "wins":         2,
      "losses":       1,
      "voids":        0,
      "totalStaked":  35.0,
      "totalPnl":     +8.46,
      "roi":          +24.2,           ← totalPnl / totalStaked * 100
      "avgCLV":       +2.1,            ← Durchschnittlicher CLV aller resolved Bets
      "sharpeEst":    null             ← wird befüllt sobald ≥5 Bets resolved
    },
    "updatedAt": "..."
  }

CLV (Closing Line Value):
  Entry-Poly-Preis (Wahrscheinlichkeit) mit Pinnacle Closing Linie vergleichen.
  CLV > 0 bedeutet: wir haben zum richtigen Zeitpunkt zu besseren Odds gewettet
  als der Markt beim Anpfiff bewertet hat → zeigt Edge-Qualität an.
  Formula: clvPP = (pinnClose - polyPrice) * 100

Märkte → Gewinn-Bedingung:
  Heimsieg        → winner == home_id
  Auswärtssieg    → winner == away_id
  Unentschieden   → winner == "draw"
  Over 2.5 Tore   → total_goals > 2
  Under 2.5 Tore  → total_goals <= 2
  Over 1.5 Tore   → total_goals > 1
  Under 1.5 Tore  → total_goals <= 1
  Over 3.5 Tore   → total_goals > 3
  Beide Teams treffen → both_scored (home_score ≥ 1 AND away_score ≥ 1)

Run: python resolve_wm_results.py
Triggered: manage-wm-poly.yml (nach Preis-Fetch)
"""

import json
import math
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE          = Path(__file__).parent
PLACED_FILE   = BASE / "wm_auto_bets_placed.json"
HISTORY_FILE  = BASE / "picks_history.json"
WM_FILE       = BASE / "wm2026-data.json"
RESULTS_FILE  = BASE / "wm_results.json"
POLY_HIST_FILE = BASE / "wm2026-poly-history.json"

# Mapping zwischen Pick-Market-Label und Poly-Snapshot-Key
# (Polymarket-Snapshots haben Keys wie poly_hw / poly_dr / poly_aw / poly_o25 / poly_u25)
POLY_MARKET_KEY_MAP = {
    "Heimsieg":         "hw",
    "Auswärtssieg":     "aw",
    "Unentschieden":    "dr",
    "Over 2.5 Tore":    "o25",
    "Under 2.5 Tore":   "u25",
    "Über 2.5 Tore":    "o25",
    "Unter 2.5 Tore":   "u25",
    # BTTS / DC / AH / Corners: noch nicht in poly-history-Snapshot — bleiben None,
    # CLV gegen Pinn-Closing (existing clvPP) deckt das weiterhin ab.
}

# Märkte und ihre Win-Bedingungen
# tuple: (market_label, check_function(result) → bool | None (None=VOID wenn kein Ergebnis))
MARKET_WIN_CONDITIONS = {
    "Heimsieg":           lambda r: r.get("winner") == r.get("_home_id"),
    "Auswärtssieg":       lambda r: r.get("winner") == r.get("_away_id"),
    "Unentschieden":      lambda r: r.get("winner") == "draw",
    "Over 2.5 Tore":      lambda r: _total_goals(r) is not None and _total_goals(r) > 2.5,
    "Under 2.5 Tore":     lambda r: _total_goals(r) is not None and _total_goals(r) < 2.5,
    "Over 1.5 Tore":      lambda r: _total_goals(r) is not None and _total_goals(r) > 1.5,
    "Under 1.5 Tore":     lambda r: _total_goals(r) is not None and _total_goals(r) < 1.5,
    "Over 3.5 Tore":      lambda r: _total_goals(r) is not None and _total_goals(r) > 3.5,
    "Under 3.5 Tore":     lambda r: _total_goals(r) is not None and _total_goals(r) < 3.5,
    "Beide Teams treffen": lambda r: (
        r.get("home_score") is not None and r.get("away_score") is not None
        and r["home_score"] >= 1 and r["away_score"] >= 1
    ),
    "Beide Teams treffen - Nein": lambda r: (
        r.get("home_score") is not None and r.get("away_score") is not None
        and not (r["home_score"] >= 1 and r["away_score"] >= 1)
    ),
}

FINISHED_STATUSES = {"FT", "AET", "PEN"}


def _total_goals(result: dict) -> float | None:
    h = result.get("home_score")
    a = result.get("away_score")
    if h is None or a is None:
        return None
    return float(h + a)


# H2 Fix 05.06.2026 — Power-Devig statt Proportional-Devig:
# Proportional teilt Margin gleichmäßig auf alle Outcomes → systematisch
# Underdog-bias (Underdogs bekommen zu viel Wahrscheinlichkeit zugewiesen).
# Power-Devig findet k mit sum((1/odd)^k) = 1 — die Standard-Methode für
# Pinnacle-CLV in Sharp-Betting-Literatur (Joseph Buchdahl, Bet Bind).
# Bei niedriger Margin (<3%) ist Unterschied minimal; bei 5%+ Margin
# unterscheiden sich Power vs Proportional um 0.5-1.5pp je Outcome.
def power_devig(*decimal_odds: float, iterations: int = 50) -> tuple[float, ...]:
    """Bisection-Power-Devig.

    Findet k sodass sum((1/odd)^k) ≈ 1, gibt fair_probs zurück.
    Funktioniert für 2-, 3- und mehr Outcomes.
    """
    odds = [float(o) for o in decimal_odds if o and o > 1]
    if len(odds) < 2:
        return tuple()
    inv = [1.0 / o for o in odds]
    raw_sum = sum(inv)
    # Falls quasi keine Margin (raw_sum ≈ 1), proportional reicht völlig
    if abs(raw_sum - 1.0) < 0.005:
        return tuple(v / raw_sum for v in inv)
    # Bisection auf k ∈ [0.5, 1.5]
    lo, hi = 0.5, 1.5
    for _ in range(iterations):
        k = (lo + hi) / 2
        s = sum(v ** k for v in inv)
        if s > 1.0:
            lo = k   # k zu klein → Summe zu groß → k erhöhen
        else:
            hi = k
        if abs(s - 1.0) < 1e-6:
            break
    k_final = (lo + hi) / 2
    return tuple(v ** k_final for v in inv)


def fair_prob_single_pinnacle(odd: float, assumed_vig: float = 0.025) -> float | None:
    """H2 Fix: Single-Outcome Fair-Prob mit Pinnacle-Standardvig (~2.5%).

    Wird verwendet wenn die Gegenseite eines 2-way Marktes fehlt (z.B. nur bttsY
    ohne bttsN). Vorher: rohes 1/odd (overestimates probability, ignoriert Vig).
    Jetzt: konservative Pinnacle-Vig-Annahme abziehen.
    """
    if not odd or odd <= 1:
        return None
    return round((1.0 / odd) / (1.0 + assumed_vig), 4)


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"  ⚠️  Fehler beim Laden von {path.name}: {e}")
        return default


def build_result_lookup(wm: dict) -> dict:
    """
    Erstellt ein Lookup: "HOME_ID-AWAY_ID" → result-dict.
    result-dict enthält auch home_id + away_id für Lambda-Zugriff.
    """
    lookup = {}
    odds_map = wm.get("odds", {})
    # Phase 3 (16.06.2026): minutengenaue Closing-Linien aus eigener Datei bevorzugen
    # (vom 15min-Manage-Fetch nahe Anpfiff committet). Fallback = odds_closing in
    # wm2026-data.json (bis-4h-frühe Closing). Macht CLV präziser.
    closing_lines = {}
    try:
        _clf = BASE / "wm_closing_lines.json"
        if _clf.exists():
            closing_lines = json.loads(_clf.read_text(encoding="utf-8")) or {}
    except Exception:
        closing_lines = {}

    for gdata in wm.get("groups", {}).values():
        for fx in gdata.get("fixtures", []):
            home_id = fx["home"]
            away_id = fx["away"]
            key     = f"{home_id}-{away_id}"
            result  = fx.get("result", {})

            if not result:
                continue

            # Pinnacle Closing Odds — minutengenaue Datei bevorzugen, sonst odds_map
            odds_entry = odds_map.get(key, {})
            closing    = closing_lines.get(key) or odds_entry.get("odds_closing", {})

            # Fair probability aus Closing Odds berechnen — H2: Power-Devig
            pinn_close_hw = pinn_close_dr = pinn_close_aw = None
            if closing.get("hw") and closing.get("dr") and closing.get("aw"):
                probs = power_devig(closing["hw"], closing["dr"], closing["aw"])
                if len(probs) == 3:
                    pinn_close_hw = round(probs[0], 4)
                    pinn_close_dr = round(probs[1], 4)
                    pinn_close_aw = round(probs[2], 4)

            # Devigg O/U 2.5 closing odds (Power-Devig)
            pinn_close_o25 = pinn_close_u25 = None
            c_o25 = closing.get("o25"); c_u25 = closing.get("u25")
            if c_o25 and c_u25 and c_o25 > 1 and c_u25 > 1:
                probs = power_devig(c_o25, c_u25)
                if len(probs) == 2:
                    pinn_close_o25, pinn_close_u25 = round(probs[0], 4), round(probs[1], 4)

            # Devigg BTTS closing odds (Power-Devig + Pinnacle-Vig-Fallback)
            pinn_close_btts   = None
            pinn_close_bttsN  = None
            c_bttsY = closing.get("bttsY"); c_bttsN = closing.get("bttsN")
            if c_bttsY and c_bttsN and c_bttsY > 1 and c_bttsN > 1:
                probs = power_devig(c_bttsY, c_bttsN)
                if len(probs) == 2:
                    pinn_close_btts, pinn_close_bttsN = round(probs[0], 4), round(probs[1], 4)
            elif c_bttsY and c_bttsY > 1:
                # H2 Fix: nicht rohes 1/odd (overestimates) — Pinnacle-Vig-Annahme abziehen
                pinn_close_btts = fair_prob_single_pinnacle(c_bttsY)

            # H1 Fix 05.06.2026 — CLV-Backfill für DC/AH/DNB/O15/O35/Corners:
            # Vorher wurden CLV-Werte nur für 1X2/O25/U25/BTTS berechnet,
            # alle anderen Picks (DC/DNB/Corners/AH) bekamen clvPP=None →
            # Avg-CLV-Statistik war systematisch zu klein und für diese
            # Marktarten gar nicht trackbar. Jetzt: vollständige Devig-Pipeline.

            # O/U 1.5 (Power-Devig)
            pinn_close_o15 = pinn_close_u15 = None
            c_o15 = closing.get("o15"); c_u15 = closing.get("u15")
            if c_o15 and c_u15 and c_o15 > 1 and c_u15 > 1:
                probs = power_devig(c_o15, c_u15)
                if len(probs) == 2:
                    pinn_close_o15, pinn_close_u15 = round(probs[0], 4), round(probs[1], 4)

            # O/U 3.5 (Power-Devig)
            pinn_close_o35 = pinn_close_u35 = None
            c_o35 = closing.get("o35"); c_u35 = closing.get("u35")
            if c_o35 and c_u35 and c_o35 > 1 and c_u35 > 1:
                probs = power_devig(c_o35, c_u35)
                if len(probs) == 2:
                    pinn_close_o35, pinn_close_u35 = round(probs[0], 4), round(probs[1], 4)

            # DC: aus deviggten 1X2-Wahrscheinlichkeiten ableiten
            # (akkurater als c_dc1X/c_dc12/c_dcX2 deviggen, weil 1X2-Closing
            # tighter ist — Pinnacle macht 1X2 als Hauptmarkt)
            pinn_close_dc1X = pinn_close_dc12 = pinn_close_dcX2 = None
            if pinn_close_hw is not None and pinn_close_dr is not None and pinn_close_aw is not None:
                pinn_close_dc1X = round(pinn_close_hw + pinn_close_dr, 4)
                pinn_close_dc12 = round(pinn_close_hw + pinn_close_aw, 4)
                pinn_close_dcX2 = round(pinn_close_dr + pinn_close_aw, 4)

            # DNB: aus deviggten 1X2-Wahrscheinlichkeiten ableiten
            # (Draw No Bet = Sieg-Wahrscheinlichkeit / nicht-draw-Wahrscheinlichkeit)
            pinn_close_dnbH = pinn_close_dnbA = None
            if pinn_close_hw is not None and pinn_close_aw is not None:
                nondraw = pinn_close_hw + pinn_close_aw
                if nondraw > 0:
                    pinn_close_dnbH = round(pinn_close_hw / nondraw, 4)
                    pinn_close_dnbA = round(pinn_close_aw / nondraw, 4)

            # Asian Handicap -0.5 (Power-Devig)
            pinn_close_ahH_n050 = pinn_close_ahA_p050 = None
            c_ahHn050 = closing.get("ahH_n050"); c_ahAp050 = closing.get("ahA_p050")
            if c_ahHn050 and c_ahAp050 and c_ahHn050 > 1 and c_ahAp050 > 1:
                probs = power_devig(c_ahHn050, c_ahAp050)
                if len(probs) == 2:
                    pinn_close_ahH_n050, pinn_close_ahA_p050 = round(probs[0], 4), round(probs[1], 4)

            # Corners (Power-Devig) — cornerLine gibt die Linie an
            pinn_close_cOver = pinn_close_cUnder = None
            corner_line      = closing.get("cornerLine")
            c_cOver          = closing.get("cOver"); c_cUnder = closing.get("cUnder")
            if c_cOver and c_cUnder and c_cOver > 1 and c_cUnder > 1:
                probs = power_devig(c_cOver, c_cUnder)
                if len(probs) == 2:
                    pinn_close_cOver, pinn_close_cUnder = round(probs[0], 4), round(probs[1], 4)

            lookup[key] = {
                **result,
                "_home_id":            home_id,
                "_away_id":            away_id,
                "_pinn_close_hw":      pinn_close_hw,
                "_pinn_close_dr":      pinn_close_dr,
                "_pinn_close_aw":      pinn_close_aw,
                "_pinn_close_o15":     pinn_close_o15,
                "_pinn_close_u15":     pinn_close_u15,
                "_pinn_close_o25":     pinn_close_o25,
                "_pinn_close_u25":     pinn_close_u25,
                "_pinn_close_o35":     pinn_close_o35,
                "_pinn_close_u35":     pinn_close_u35,
                "_pinn_close_btts":    pinn_close_btts,
                "_pinn_close_bttsN":   pinn_close_bttsN,
                "_pinn_close_dc1X":    pinn_close_dc1X,
                "_pinn_close_dc12":    pinn_close_dc12,
                "_pinn_close_dcX2":    pinn_close_dcX2,
                "_pinn_close_dnbH":    pinn_close_dnbH,
                "_pinn_close_dnbA":    pinn_close_dnbA,
                "_pinn_close_ahH_n050": pinn_close_ahH_n050,
                "_pinn_close_ahA_p050": pinn_close_ahA_p050,
                "_pinn_close_cOver":   pinn_close_cOver,
                "_pinn_close_cUnder":  pinn_close_cUnder,
                "_pinn_corner_line":   corner_line,
            }
    return lookup


def get_pinn_close_for_market(res: dict, market: str) -> float | None:
    """
    Gibt die Pinnacle-Closing-Fair-Probability für den gegebenen Markt zurück.
    Wird für CLV-Berechnung verwendet.

    H1 Fix 05.06.2026 — vollständige Marktabdeckung:
    1X2, O/U 1.5+2.5+3.5, BTTS Ja/Nein, DC (1X/X2/12), DNB, Corners, AH -0.5
    """
    m = market.lower()

    # 1X2
    if "heimsieg" in m:
        return res.get("_pinn_close_hw")
    if "auswärtssieg" in m or "auswartssieg" in m:
        return res.get("_pinn_close_aw")
    if "unentschieden" in m:
        return res.get("_pinn_close_dr")

    # Doppelte Chance (vor O/U prüfen wegen "1X"/"X2"/"12" Substrings)
    if "doppelte chance" in m or m.endswith(" 1x") or m.endswith(" x2") or m.endswith(" 12"):
        if "1x" in m:
            return res.get("_pinn_close_dc1X")
        if "x2" in m:
            return res.get("_pinn_close_dcX2")
        if "12" in m:
            return res.get("_pinn_close_dc12")

    # DNB
    if "dnb" in m or "draw no bet" in m:
        if "heim" in m:
            return res.get("_pinn_close_dnbH")
        if "auswärt" in m or "auswart" in m:
            return res.get("_pinn_close_dnbA")

    # Over/Under Tore — alle Linien
    if "über 1.5" in m or "over 1.5" in m:
        return res.get("_pinn_close_o15")
    if "unter 1.5" in m or "under 1.5" in m:
        return res.get("_pinn_close_u15")
    if "über 2.5" in m or "over 2.5" in m:
        return res.get("_pinn_close_o25")
    if "unter 2.5" in m or "under 2.5" in m:
        return res.get("_pinn_close_u25")
    if "über 3.5" in m or "over 3.5" in m:
        return res.get("_pinn_close_o35")
    if "unter 3.5" in m or "under 3.5" in m:
        return res.get("_pinn_close_u35")

    # BTTS
    if "beide teams" in m or "btts" in m:
        if "nein" in m or "no" in m:
            return res.get("_pinn_close_bttsN")
        return res.get("_pinn_close_btts")

    # Asian Handicap -0.5 (Heimteam -0.5 entspricht effektiv Heimsieg ohne Draw)
    if "handicap" in m or "ah " in m or m.startswith("ah"):
        if "heim" in m and ("-0.5" in m or "-0,5" in m):
            return res.get("_pinn_close_ahH_n050")
        if ("auswärt" in m or "auswart" in m) and ("+0.5" in m or "+0,5" in m):
            return res.get("_pinn_close_ahA_p050")

    # Corners
    if "corner" in m or "eck" in m:
        if "über" in m or "over" in m:
            return res.get("_pinn_close_cOver")
        if "unter" in m or "under" in m:
            return res.get("_pinn_close_cUnder")

    return None


def determine_result(bet: dict, res: dict) -> str:
    """WIN | LOSS | VOID | PENDING"""
    status = res.get("status", "NS")
    if status not in FINISHED_STATUSES:
        return "PENDING"

    market  = bet.get("market", "")
    checker = MARKET_WIN_CONDITIONS.get(market)
    if not checker:
        return "VOID"

    try:
        win = checker(res)
    except Exception:
        win = None

    if win is None:
        return "VOID"
    return "WIN" if win else "LOSS"


def compute_pnl(bet: dict, result: str) -> float:
    stake      = float(bet.get("stake", 0))
    poly_price = float(bet.get("polyPrice", 0))

    if result == "WIN":
        # Gewinn = (1/polyPrice - 1) * stake (Dezimal-Odds Umrechnung)
        if poly_price > 0:
            odds = 1.0 / poly_price
            return round((odds - 1.0) * stake, 4)
        return 0.0
    elif result == "LOSS":
        return round(-stake, 4)
    return 0.0  # VOID oder PENDING


def normalize_bet(bet: dict) -> dict:
    """Normalisiert einen Bet-Eintrag (auto oder manuell) auf ein einheitliches Format."""
    # Manuell platzierte WM-Bets aus picks_history.json haben andere Struktur
    if "picks" in bet:
        # picks_history Format
        for pick in bet.get("picks", []):
            yield {
                "betKey":    f"{bet.get('home','')}-{bet.get('away','')}-{pick.get('market','')}",
                "home":      bet.get("home", ""),
                "away":      bet.get("away", ""),
                "homeId":    bet.get("homeId", ""),
                "awayId":    bet.get("awayId", ""),
                "market":    pick.get("market", ""),
                "stake":     float(pick.get("stake", bet.get("stake", 5))),
                "polyPrice": float(pick.get("polyPrice", 0)),
                "pinnFair":  float(pick.get("pinnFair", 0)) if pick.get("pinnFair") else None,
                "slug":      pick.get("slug", ""),
                "placedAt":  bet.get("savedAt", ""),
                "source":    "manual",
            }
    else:
        yield {**bet, "source": bet.get("source", "auto")}


# ─────────────────────────────────────────────────────────────────────────────
# Polymarket-Closing-Snapshot Helper (Audit-Erweiterung 07.06.2026)
# ─────────────────────────────────────────────────────────────────────────────
def find_poly_close_price(
    poly_hist: dict,
    home_id: str,
    away_id: str,
    market_label: str,
    match_date: str
) -> float | None:
    """Liefert Polymarket-Preis ~1h vor Match-Start für CLV-Vergleich.

    Strategie: aus wm2026-poly-history.json den Snapshot finden dessen ts
    am nächsten an `match_date + 18:00 UTC` (typische WM-Anpfiff-Zeit)
    aber NICHT danach liegt. Wenn kein Snapshot in [-12h, 0] vor Anpfiff →
    nimm den jüngsten Snapshot insgesamt (besser als None).
    """
    if not poly_hist or not match_date:
        return None
    key       = f"{home_id}-{away_id}"
    snapshots = poly_hist.get(key) or []
    if not snapshots:
        return None

    poly_key = POLY_MARKET_KEY_MAP.get(market_label.strip())
    if not poly_key:
        return None
    poly_field = f"poly_{poly_key}"

    # Match-Anpfiff schätzen (WM-Standard: 19:00 UTC für Hauptspiele).
    # Falls Datum bekannt, suchen wir Snapshot ≤ Anpfiff aber innerhalb 12h davor.
    try:
        # Bug-Fix 08.06.2026: lokalen datetime-Import entfernt (siehe fetch_wm_poly_prices)
        # — globaler Import oben enthält jetzt timedelta. Sonst gleicher
        # UnboundLocalError-Trap wie bei fetch_wm_poly_prices Line 625.
        if "T" in match_date:
            anpfiff = datetime.fromisoformat(match_date.replace("Z", "+00:00"))
        else:
            anpfiff = datetime.fromisoformat(f"{match_date}T18:00:00+00:00")
    except Exception:
        anpfiff = None

    best = None
    best_dist = None
    for snap in snapshots:
        price = snap.get(poly_field)
        if price is None:
            continue
        ts_str = snap.get("ts", "")
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except Exception:
            continue

        if anpfiff:
            delta = (anpfiff - ts).total_seconds()
            if delta < 0:
                continue  # nach Anpfiff = uninteressant
            if delta > 12 * 3600:
                continue  # zu weit weg
            if best_dist is None or delta < best_dist:
                best = price
                best_dist = delta
        else:
            # Fallback: jüngster Snapshot
            best = price

    return best


def _parse_ah_line(market_lower: str):
    """Signierte AH-Linie aus Markt-String ('AH Heim −1.5' → -1.5, 'AH Auswärts +0.5'
    → +0.5). Unicode-Minus (−) wird normalisiert."""
    mm = re.search(r"([+\-]?\s*\d+(?:\.\d+)?)", market_lower.replace("−", "-"))
    if not mm:
        return None
    try:
        return float(mm.group(1).replace(" ", ""))
    except Exception:
        return None


def process_verdict(market: str, result_str: str, stats: dict | None) -> dict:
    """Prozess-Urteil aus den ECHTEN Match-xG (14.06.2026): hat der Pick es per xG
    „verdient"? Trennt Können von Varianz. Liefert {processVerdict, processCovered,
    xgTotal, xgHome, xgAway} oder {} wenn nicht beurteilbar.

    processVerdict:
      JUSTIFIED     — gewonnen & per xG verdient (sauberer Win)
      LUCKY         — gewonnen, aber per xG NICHT verdient (Glück)
      UNLUCKY       — verloren, aber per xG verdient (Pech — z.B. QAT-SUI Over)
      DESERVED_LOSS — verloren & per xG auch verdient verloren (echter Fehl-Read)
    """
    if result_str not in ("WIN", "LOSS") or not stats:
        return {}
    xg_t = stats.get("xgTotal")
    xg_h = stats.get("homeXg")
    xg_a = stats.get("awayXg")
    if xg_t is None:
        return {}
    m = (market or "").lower()
    covered = None
    mt = re.search(r"(\d+\.5)", m)
    is_goals = "tore" in m or "goals" in m
    if is_goals and ("über" in m or "uber" in m or "over" in m) and mt:
        covered = xg_t >= float(mt.group(1))
    elif is_goals and ("unter" in m or "under" in m) and mt:
        covered = xg_t < float(mt.group(1))
    elif xg_h is not None and xg_a is not None:
        diff = xg_h - xg_a   # >0 = Heim per xG besser
        if "ah heim" in m or "ah home" in m:
            ln = _parse_ah_line(m)
            covered = (diff + ln) > 0 if ln is not None else None
        elif "ah auswärt" in m or "ah auswaert" in m or "ah away" in m:
            ln = _parse_ah_line(m)
            covered = (-diff + ln) > 0 if ln is not None else None
        elif "heimsieg" in m:                         covered = diff > 0
        elif "auswärtssieg" in m or "auswaertssieg" in m: covered = diff < 0
        elif "1x" in m or "dnb: heim" in m:           covered = diff >= -0.3
        elif "x2" in m or "dnb: auswärt" in m:        covered = diff <= 0.3
        elif "unentschieden" in m:                    covered = abs(diff) < 0.4
        elif "beide teams" in m or "btts" in m:
            # FIX 14.06.2026: BTTS prozess-bewerten. Beide Teams mit ≥0.8 xG haben ein
            # Tor „verdient" → Finishing-Varianz von Können trennen. Gelernt aus AUS-TUR
            # (Türkei away-xG ~1.8, traf 0 → BTTS-Ja-Loss = UNLUCKY, nicht voll bestrafen).
            BTTS_XG = 0.8
            both_deserved = (xg_h >= BTTS_XG and xg_a >= BTTS_XG)
            is_no = "nein" in m or "no" in m
            covered = (not both_deserved) if is_no else both_deserved
    if covered is None:
        return {}
    won = (result_str == "WIN")
    verdict = ("JUSTIFIED" if (won and covered) else
               "LUCKY"     if (won and not covered) else
               "UNLUCKY"   if (not won and covered) else
               "DESERVED_LOSS")
    return {"processVerdict": verdict, "processCovered": covered,
            "xgTotal": xg_t, "xgHome": xg_h, "xgAway": xg_a}


def main():
    now_iso = datetime.now(timezone.utc).isoformat()
    print(f"📊  resolve_wm_results.py — P&L + CLV Tracking")
    print(f"    Zeit: {now_iso[:19]} UTC\n")

    # Daten laden
    placed_data = load_json(PLACED_FILE, {"bets": []})
    history     = load_json(HISTORY_FILE, [])
    wm          = load_json(WM_FILE, {})
    poly_hist   = load_json(POLY_HIST_FILE, {})

    # Alle WM-Bets sammeln (auto + manuell)
    raw_bets: list[dict] = list(placed_data.get("bets", []))

    # Manuell platzierte WM2026-Bets aus picks_history
    for entry in history:
        if entry.get("league") == "WM2026":
            raw_bets.append(entry)

    if not raw_bets:
        print("  ℹ️   Keine WM-Bets gefunden — noch keine Bets platziert")
        # Leere Struktur schreiben
        _write_results([], now_iso)
        return

    print(f"  Bets gesamt: {len(raw_bets)}")

    # Normalisieren
    bets: list[dict] = []
    for rb in raw_bets:
        for b in normalize_bet(rb):
            bets.append(b)

    # Ergebnis-Lookup aufbauen
    result_lookup = build_result_lookup(wm)
    if not result_lookup:
        print("  ⚠️   Noch keine Spielergebnisse in wm2026-data.json — alle Bets PENDING")

    # Bets resolven
    resolved_bets = []
    for bet in bets:
        home_id = bet.get("homeId") or bet.get("home", "")
        away_id = bet.get("awayId") or bet.get("away", "")
        key     = f"{home_id}-{away_id}"
        res     = result_lookup.get(key, {})

        # FIX 13.06.2026: Früh per Auto-Sell/Konvergenz verkaufte Trades sind
        # TERMINAL — nicht übers Spielergebnis auflösen (wir sind ja schon raus).
        # Realisierter P&L = sharesEstimate × (sellPrice − Entry). Sonst blieben sie
        # ewig PENDING und die Performance-Sektion zeigte den Verkauf nie.
        bet_status = (bet.get("status") or "").lower()
        if bet_status == "sold":
            result_str = "SOLD"
            _entry  = float(bet.get("polyPrice", 0) or 0)
            _exit   = bet.get("sellPrice")
            _shares = float(bet.get("sharesEstimate", 0) or 0)
            pnl = (round(_shares * (float(_exit) - _entry), 2)
                   if (_exit is not None and _entry > 0) else 0.0)
        else:
            result_str  = determine_result(bet, res) if res else "PENDING"
            pnl         = compute_pnl(bet, result_str)
        poly_price  = float(bet.get("polyPrice", 0) or 0)
        poly_odds   = round(1.0 / poly_price, 3) if poly_price > 0 else None
        pinn_fair   = float(bet.get("pinnFair", 0) or 0) or None

        # CLV: Pinnacle Closing vs Entry Poly Price (beide als Wahrscheinlichkeit)
        pinn_close = get_pinn_close_for_market(res, bet.get("market", "")) if res else None
        clv_pp     = None
        if pinn_close and poly_price:
            clv_pp = round((pinn_close - poly_price) * 100, 2)

        # Polymarket-CLV (Audit-Erweiterung 07.06.2026):
        # Vergleich Entry-Polymarket-Preis vs Polymarket-Preis ~1h vor Anpfiff.
        # Sagt aus ob wir Polymarket-seitig gut getimed haben (komplementär zu Pinn-CLV).
        poly_close = find_poly_close_price(
            poly_hist,
            home_id, away_id,
            bet.get("market", ""),
            bet.get("matchDate") or res.get("matchDate") or ""
        )
        poly_clv_pp = None
        if poly_close and poly_price:
            poly_clv_pp = round((poly_close - poly_price) * 100, 2)

        # Score-String
        score = None
        if res.get("home_score") is not None and res.get("away_score") is not None:
            score = f"{res['home_score']}-{res['away_score']}"

        resolved_bet = {
            "betKey":      bet.get("betKey") or key + "-" + bet.get("market", ""),
            "home":        bet.get("home", ""),
            "away":        bet.get("away", ""),
            "homeId":      home_id,
            "awayId":      away_id,
            "market":      bet.get("market", ""),
            "stake":       float(bet.get("stake", 5)),
            "polyPrice":   round(poly_price, 4) if poly_price else None,
            "polyOdds":    poly_odds,
            "pinnFair":    round(pinn_fair, 4) if pinn_fair else None,
            "pinnClose":   round(pinn_close, 4) if pinn_close else None,
            "clvPP":       clv_pp,           # CLV gegen Pinnacle (Industrie-Standard)
            "polyClose":   round(poly_close, 4) if poly_close else None,
            "polyClvPP":   poly_clv_pp,      # CLV gegen Polymarket-Close (Exchange-Timing)
            "isSteamLag":  bool(bet.get("isSteamLag", False)),
            "result":      result_str,
            "pnl":         pnl,
            "score":       score,
            "slug":        bet.get("slug", ""),
            "source":      bet.get("source", "auto"),
            "placedAt":    bet.get("placedAt", ""),
            "resolvedAt":  (res.get("resolvedAt") if result_str in ("WIN", "LOSS", "VOID")
                            else bet.get("soldAt") if result_str == "SOLD" else None),
            # Early-Sell-Details (für die Performance-Anzeige)
            "sellPrice":   round(float(bet["sellPrice"]), 4) if bet.get("sellPrice") is not None else None,
            "sellReason":  bet.get("sellReason"),
        }

        # Prozess-Urteil aus echten Match-xG (14.06.2026): verdient/Pech/Glück.
        pv = process_verdict(bet.get("market", ""), result_str, res.get("stats"))
        if pv:
            resolved_bet.update(pv)

        resolved_bets.append(resolved_bet)
        status_icon = {"WIN": "✅", "LOSS": "❌", "VOID": "⬜", "PENDING": "⏳", "SOLD": "💸"}.get(result_str, "?")
        clv_str = f" CLV={clv_pp:+.1f}pp" if clv_pp is not None else ""
        print(f"  {status_icon} {bet.get('home','')} vs {bet.get('away','')} "
              f"— {bet.get('market','')} | P&L: {pnl:+.2f}€{clv_str}")

    _write_results(resolved_bets, now_iso)
    _write_back_status_to_placed(resolved_bets, now_iso)


def _write_back_status_to_placed(resolved_bets: list[dict], now_iso: str) -> None:
    """FIX 13.06.2026: Aufgelösten Status (won/lost/void) in wm_auto_bets_placed.json
    zurückschreiben — symmetrisch zum „sold" das der Auto-Sell setzt. SONST blieben
    aufgelöste Wetten auf status=`placed` ohne `result` → klebten ewig im „Offene
    Positionen · Live"-Panel (Filter: result==null && !soldAt) als „🔴 läuft / −100%"
    (QAT-SUI nach LOSS). Und manage_wm_poly_positions (lädt nur status==`placed`)
    würde sie weiter zu managen versuchen. Sold-Bets werden NICHT überschrieben."""
    if not os.path.exists(PLACED_FILE):
        return
    try:
        data = json.loads(PLACED_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  ⚠️  Status-Rückschreiben übersprungen (Lesefehler): {e}")
        return
    _STATUS = {"WIN": "won", "LOSS": "lost", "VOID": "void"}
    by_key = {rb.get("betKey"): rb for rb in resolved_bets
              if rb.get("result") in _STATUS}
    changed = 0
    for bet in data.get("bets", []):
        if (bet.get("status") or "").lower() == "sold":
            continue   # früh verkauft = terminal, nie übers Ergebnis überschreiben
        rb = by_key.get(bet.get("betKey"))
        if not rb:
            continue
        new_status = _STATUS[rb["result"]]
        if bet.get("status") != new_status or bet.get("result") != rb["result"]:
            bet["status"]     = new_status
            bet["result"]     = rb["result"]
            bet["pnl"]        = rb.get("pnl")
            bet["resolvedAt"] = rb.get("resolvedAt") or now_iso
            changed += 1
    if changed:
        data["updatedAt"] = now_iso
        PLACED_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  ↩️  {changed} aufgelöste Wette(n) in wm_auto_bets_placed.json markiert (won/lost/void)")


def _write_results(bets: list[dict], now_iso: str) -> None:
    finished = [b for b in bets if b.get("result") in ("WIN", "LOSS", "VOID")]
    wins     = [b for b in finished if b.get("result") == "WIN"]
    losses   = [b for b in finished if b.get("result") == "LOSS"]
    voids    = [b for b in finished if b.get("result") == "VOID"]
    sold     = [b for b in bets if b.get("result") == "SOLD"]   # früh verkauft (FIX 13.06.2026)
    pending  = [b for b in bets if b.get("result") == "PENDING"]

    total_staked = sum(b.get("stake", 0) for b in bets if b.get("result") != "VOID")
    total_pnl    = sum(b.get("pnl", 0) for b in bets)
    roi          = round(total_pnl / total_staked * 100, 2) if total_staked > 0 else 0.0

    clv_values = [b["clvPP"] for b in finished if b.get("clvPP") is not None]
    avg_clv    = round(sum(clv_values) / len(clv_values), 2) if clv_values else None

    # Einfache Sharpe-Schätzung (benötigt ≥5 resolved Bets)
    sharpe = None
    pnls = [b.get("pnl", 0) for b in finished]
    if len(pnls) >= 5:
        mean = sum(pnls) / len(pnls)
        std  = math.sqrt(sum((p - mean) ** 2 for p in pnls) / len(pnls))
        sharpe = round(mean / std, 2) if std > 0 else None

    summary = {
        "totalBets":   len(bets),
        "resolved":    len(finished) + len(sold),   # geschlossen = aufgelöst + früh verkauft
        "pending":     len(pending),
        "sold":        len(sold),
        "wins":        len(wins),
        "losses":      len(losses),
        "voids":       len(voids),
        "winRate":     round(len(wins) / len(finished) * 100, 1) if finished else None,
        "totalStaked": round(total_staked, 2),
        "totalPnl":    round(total_pnl, 4),
        "roi":         roi,
        "avgCLV":      avg_clv,
        "sharpeEst":   sharpe,
    }

    out = {
        "bets":      bets,
        "summary":   summary,
        "updatedAt": now_iso,
    }

    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"\n✅  wm_results.json geschrieben")
    print(f"    Bets: {summary['totalBets']} gesamt | {summary['resolved']} resolved | {summary['pending']} pending")
    print(f"    P&L:  €{total_pnl:+.2f} | ROI: {roi:+.1f}% | Ø CLV: {avg_clv:+.1f}pp" if avg_clv else
          f"    P&L:  €{total_pnl:+.2f} | ROI: {roi:+.1f}% | CLV: noch keine Daten")


if __name__ == "__main__":
    main()
