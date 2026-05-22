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
from datetime import datetime, timezone
from pathlib import Path

BASE          = Path(__file__).parent
PLACED_FILE   = BASE / "wm_auto_bets_placed.json"
HISTORY_FILE  = BASE / "picks_history.json"
WM_FILE       = BASE / "wm2026-data.json"
RESULTS_FILE  = BASE / "wm_results.json"

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

    for gdata in wm.get("groups", {}).values():
        for fx in gdata.get("fixtures", []):
            home_id = fx["home"]
            away_id = fx["away"]
            key     = f"{home_id}-{away_id}"
            result  = fx.get("result", {})

            if not result:
                continue

            # Pinnacle Closing Odds aus odds_map
            odds_entry = odds_map.get(key, {})
            closing    = odds_entry.get("odds_closing", {})

            # Fair probability aus Closing Odds berechnen
            pinn_close_hw = pinn_close_dr = pinn_close_aw = None
            if closing.get("hw") and closing.get("dr") and closing.get("aw"):
                c_hw = closing["hw"]; c_dr = closing["dr"]; c_aw = closing["aw"]
                margin = 1/c_hw + 1/c_dr + 1/c_aw
                pinn_close_hw = round((1/c_hw) / margin, 4)
                pinn_close_dr = round((1/c_dr) / margin, 4)
                pinn_close_aw = round((1/c_aw) / margin, 4)

            lookup[key] = {
                **result,
                "_home_id":         home_id,
                "_away_id":         away_id,
                "_pinn_close_hw":   pinn_close_hw,
                "_pinn_close_dr":   pinn_close_dr,
                "_pinn_close_aw":   pinn_close_aw,
                "_pinn_close_o25":  closing.get("o25"),
                "_pinn_close_u25":  closing.get("u25"),
                "_pinn_close_btts": closing.get("bttsY"),
            }
    return lookup


def get_pinn_close_for_market(res: dict, market: str) -> float | None:
    """
    Gibt die Pinnacle-Closing-Fair-Probability für den gegebenen Markt zurück.
    Wird für CLV-Berechnung verwendet.
    """
    m = market.lower()
    if "heimsieg" in m:
        return res.get("_pinn_close_hw")
    if "auswärtssieg" in m or "auswartssieg" in m:
        return res.get("_pinn_close_aw")
    if "unentschieden" in m:
        return res.get("_pinn_close_dr")
    if "over 2.5" in m or "über 2.5" in m:
        p = res.get("_pinn_close_o25")
        return round(1/p, 4) if p and p > 1 else None   # o25 ist Dezimalquotient → umrechnen
    if "under 2.5" in m:
        p = res.get("_pinn_close_u25")
        return round(1/p, 4) if p and p > 1 else None
    if "beide teams" in m and "nein" not in m:
        p = res.get("_pinn_close_btts")
        return round(1/p, 4) if p and p > 1 else None
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


def main():
    now_iso = datetime.now(timezone.utc).isoformat()
    print(f"📊  resolve_wm_results.py — P&L + CLV Tracking")
    print(f"    Zeit: {now_iso[:19]} UTC\n")

    # Daten laden
    placed_data = load_json(PLACED_FILE, {"bets": []})
    history     = load_json(HISTORY_FILE, [])
    wm          = load_json(WM_FILE, {})

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
            "clvPP":       clv_pp,
            "result":      result_str,
            "pnl":         pnl,
            "score":       score,
            "slug":        bet.get("slug", ""),
            "source":      bet.get("source", "auto"),
            "placedAt":    bet.get("placedAt", ""),
            "resolvedAt":  res.get("resolvedAt") if result_str in ("WIN", "LOSS", "VOID") else None,
        }

        resolved_bets.append(resolved_bet)
        status_icon = {"WIN": "✅", "LOSS": "❌", "VOID": "⬜", "PENDING": "⏳"}.get(result_str, "?")
        clv_str = f" CLV={clv_pp:+.1f}pp" if clv_pp is not None else ""
        print(f"  {status_icon} {bet.get('home','')} vs {bet.get('away','')} "
              f"— {bet.get('market','')} | P&L: {pnl:+.2f}€{clv_str}")

    _write_results(resolved_bets, now_iso)


def _write_results(bets: list[dict], now_iso: str) -> None:
    finished = [b for b in bets if b.get("result") in ("WIN", "LOSS", "VOID")]
    wins     = [b for b in finished if b.get("result") == "WIN"]
    losses   = [b for b in finished if b.get("result") == "LOSS"]
    voids    = [b for b in finished if b.get("result") == "VOID"]
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
        "resolved":    len(finished),
        "pending":     len(pending),
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
