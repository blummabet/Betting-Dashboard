"""
conviction_score.py — Wett-Qualitäts-Bewertung 0-10

Trennt Edge-Verdict (für Polymarket-Trading) von Conviction-Verdict
(für direkte Sportsbook-Wetten / Cards). Lucas-Insight 09.06.2026:
Edge gegen Pinnacle ist Phantom wenn Elo halluziniert. Echte Wett-Qualität
kommt aus mehreren UNABHÄNGIGEN Signal-Familien die in dieselbe Richtung
zeigen + Sharp-Money-Bestätigung.

Architektur — Sharp-Move als Trigger, Signale untermauern:

  AUSLÖSER (einer reicht damit Conviction überhaupt berechnet wird):
    1. Sharp-Move bei Pinnacle (≥5pp implied since open, Softs noch hinterher)
    2. Klassischer Edge ≥4pp (für Trading-Pipeline)
    3. Strong Setup: ≥3 Signal-Familien einig

  CONVICTION-SCORE (max 10):
    Sharp-Money-Konsens   max 3pt  (höher gewichtet — echter Edge-Beweis)
      · Pinnacle-Move in Pick-Richtung           +1
      · Soft-Books folgen Pinnacle nach          +1
      · Polymarket-implied in Pick-Richtung      +1
      · Opening→Current Movement in Pick-Richtung +1 (gecapped auf 3 total)
    Form-Konsens          max 2pt
      · Form-Trend, H2H (n≥3), xG-Stärke — stärkste 2 zählen
    Kontext               max 2pt
      · Travel, Injury, Weather, Pressure, Incentive — stärkste 2
    Realtime              max 2pt
      · Lineup-Signal (T-1h Aufstellung) — höher gewichtet
    Markt-Konsens         max 1pt
      · Public-Bias ODER APIF-Predictions
    Modell-Sanity         max 1pt
      · Modell ≤10pp vom Markt-Konsens (kein Halluzinations-Edge)

  VERDICT (Cards):
    ≥8/10 → 🎯 Top-Wette
    ≥6/10 → ⭐ ABWÄGEN
    <6   → nicht in Cards (für Polymarket-Trigger trotzdem aktiv)

  BAYESIAN-LERNEN:
    Signal-Weights aus signal_weights.json justieren die Scores datengetrieben.
    Nach 30+ resolved Picks sind Weights kalibriert. Lineup-Signal kriegt z.B.
    weight=1.3 wenn historisch öfter gewinnt, Pressure-Index weight=0.8 wenn
    schlechter.

  KONFIGURATION:
    Alle Schwellwerte in cocobet_config.json → profiles.<profile>.conviction_score.
    Liga-Profile haben moderatere Defaults.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Optional


# ──────────────────────────────────────────────────────────────────────────
#  Config-Loader (Profile-aware, mit Defaults für Robustheit)
# ──────────────────────────────────────────────────────────────────────────
def _load_config() -> dict:
    """Lädt conviction_score-Section aus cocobet_config.json, Profile-aware."""
    DEFAULTS = {
        "sharp_move": {
            "min_pinn_move_pp": 5.0,
            "min_soft_lag_pp": 3.0,
            "min_hours_since_open": 6,
        },
        "verdict_thresholds": {"top": 8, "abwaegen": 6, "skip": 4},
        "family_caps": {
            "sharp_money": 3, "form": 2, "context": 2,
            "realtime": 2, "market": 1, "model": 1,
        },
        "opening_movement": {
            "enabled": True, "min_pp_in_pick_direction": 3.0,
        },
        "signal_weights_init": 1.0,
        "card_quote_display": {
            "show_soft_book_quote": True,
            "show_pinn_in_modal": True,
            "show_movement_in_modal": True,
        },
    }
    try:
        raw = json.loads((Path(__file__).parent / "cocobet_config.json")
                         .read_text(encoding="utf-8"))
        active = os.environ.get("COCOBET_PROFILE") or raw["profiles"].get("active", "wm2026")
        cfg = raw["profiles"].get(active, {}).get("conviction_score") or {}
        # Merge mit Defaults (für fehlende Sub-Keys)
        def _merge(d, defaults):
            out = dict(defaults)
            for k, v in d.items():
                if isinstance(v, dict) and isinstance(defaults.get(k), dict):
                    out[k] = _merge(v, defaults[k])
                else:
                    out[k] = v
            return out
        return _merge(cfg, DEFAULTS)
    except Exception:
        return DEFAULTS


def _load_signal_weights() -> dict:
    """
    Lädt Bayesian-gelernte Signal-Weights aus signal_weights.json.
    Default 1.0 wenn nicht vorhanden oder Signal nicht gelistet.
    """
    try:
        from sharp_signals.registry import load_signal_weights, get_weight
        weights = load_signal_weights()
        return {name: get_weight(weights, name) for name in [
            "lead_lag_bias", "public_static_bias", "travel_burden", "injury",
            "form_trend", "h2h_pattern", "xg_strength", "polymarket_sharp",
            "steam_lag", "pressure_index", "lineup_signal", "apif_predictions",
            "weather_signal", "incentive_signal",
        ]}
    except Exception:
        return {}


# ──────────────────────────────────────────────────────────────────────────
#  Pick-Direction-Helper
# ──────────────────────────────────────────────────────────────────────────
def _pick_direction(market: str) -> str:
    """Welche Richtung zeigt der Pick? Für Movement-Analyse."""
    m = (market or "").lower()
    if "heim" in m or "home" in m: return "home"
    if "auswärt" in m or "auswarts" in m or "away" in m: return "away"
    if "unter" in m or "under" in m: return "under"
    if "über" in m or "uber" in m or "over" in m: return "over"
    if "unentsch" in m or "draw" in m: return "draw"
    return "neutral"


def _pick_odds_key(market: str) -> Optional[str]:
    """
    Maps Pick-Market-String auf das Feld im Odds-Snapshot (hw/dr/aw/o25/u25/...).
    Granularer als _pick_direction — unterscheidet O1.5 vs O2.5 vs O3.5,
    BTTS Ja vs Nein, Corner-Linien.

    Returns None wenn kein bekannter Markt → Sharp-Move-Detection skip.
    """
    m = (market or "").lower()

    # Doppelte Chance (vor 1X2-Check) — approximiert die nähere Seite
    if "doppelte chance" in m or "double chance" in m:
        if "1x" in m: return "hw"   # Heim oder X — Heim-Bias als Proxy
        if "x2" in m: return "aw"
        if "12" in m: return "hw"   # Beide-Mannschaften: Heim-Seite als Default
    # 1X2 + DNB/AH (alle hängen am gleichen Outcome-Implied)
    if "heim" in m or "home" in m: return "hw"
    if "auswärt" in m or "auswarts" in m or "away" in m: return "aw"
    if "unentsch" in m or "remis" in m or "draw" in m: return "dr"

    # Corners (vor Tore-Check — "Ecken" enthält auch "über"/"unter")
    if "ecken" in m or "corner" in m:
        if "8.5" in m or "85" in m: return "cOver85" if ("über" in m or "over" in m) else "cUnder85"
        if "9.5" in m or "95" in m: return "cOver95" if ("über" in m or "over" in m) else "cUnder95"
        if "10.5" in m or "105" in m: return "cOver105" if ("über" in m or "over" in m) else "cUnder105"
        # Fallback: keine Linie erkannt → generisches cOver
        return "cOver"

    # BTTS
    if "beide" in m or "btts" in m:
        if "nein" in m or "no" in m: return "bttsN"
        return "bttsY"

    # Tor-Linien (granularer als nur "over"/"under")
    if "über" in m or "uber" in m or "over" in m:
        if "1.5" in m or "1,5" in m: return "o15"
        if "3.5" in m or "3,5" in m: return "o35"
        return "o25"  # Default
    if "unter" in m or "under" in m:
        if "1.5" in m or "1,5" in m: return "u15"
        if "3.5" in m or "3,5" in m: return "u35"
        return "u25"  # Default

    return None


# ──────────────────────────────────────────────────────────────────────────
#  Sharp-Move-Trigger Detection
# ──────────────────────────────────────────────────────────────────────────
def detect_sharp_move(pick: dict, context: dict, cfg: dict) -> Optional[dict]:
    """
    Erkennt klassischen Sharp-Move: Pinnacle hat sich seit Eröffnung ≥X pp
    bewegt UND mind. 1 Soft-Book ist noch ≥Y pp dahinter UND ≥Z Stunden
    seit Eröffnung vergangen.

    Returns: {triggered: bool, pinn_move_pp, soft_lag_pp, hours_since_open}
    oder None wenn Daten unzureichend.
    """
    history = context.get("odds_history") or []
    if not history or len(history) < 2:
        return None

    sm_cfg = cfg["sharp_move"]
    # Opening = ältester Snapshot, Current = neuester
    opening = history[0]
    current = history[-1]

    # Granularer Odds-Key direkt aus Market-String (deckt O15/O25/O35/BTTS/Corner ab).
    # Fallback auf alten _pick_direction-Pfad für Backward-Compat.
    key = _pick_odds_key(pick.get("market", ""))
    if not key:
        # Backward-Compat: alte pick_direction-Logik nur 1X2/O25/U25
        pick_key_map = {"home": "hw", "draw": "dr", "away": "aw",
                        "over": "o25", "under": "u25"}
        direction = _pick_direction(pick.get("market", ""))
        key = pick_key_map.get(direction)
    if not key:
        return None

    open_pinn = opening.get(f"pinn_{key}") or opening.get(key)
    curr_pinn = current.get(f"pinn_{key}") or current.get(key)
    if not isinstance(open_pinn, (int, float)) or not isinstance(curr_pinn, (int, float)):
        return None
    if open_pinn <= 1.0 or curr_pinn <= 1.0:
        return None

    open_implied = (1.0 / open_pinn) * 100
    curr_implied = (1.0 / curr_pinn) * 100
    pinn_move_pp = curr_implied - open_implied   # positiv = Pinnacle sieht es jetzt wahrscheinlicher

    # Zeit seit Eröffnung
    from datetime import datetime, timezone
    hours_since_open = None
    try:
        ts_open = opening.get("ts")
        if ts_open:
            ts_dt = datetime.fromisoformat(str(ts_open).replace("Z", "+00:00"))
            hours_since_open = (datetime.now(timezone.utc) - ts_dt).total_seconds() / 3600
    except Exception:
        pass

    # Soft-Book-Lag prüfen (irgendein Soft-Book das ≥X pp hinter Pinnacle ist)
    soft_lag_pp = 0.0
    for bk in ("bet365", "williamhill", "betfair_ex"):
        soft_odds = current.get(f"{bk}_{key}")
        if isinstance(soft_odds, (int, float)) and soft_odds > 1.0:
            soft_implied = (1.0 / soft_odds) * 100
            lag = curr_implied - soft_implied
            soft_lag_pp = max(soft_lag_pp, lag)

    # Trigger-Logik 09.06.2026: Soft-Lag von Hard-Requirement → Bonus.
    # Begründung (Lucas): Wenn Pinnacle vor X Tagen klar Position bezogen hat
    # und Soft-Books seither aufgeholt haben, ist der MOVE als Modell-Signal
    # trotzdem wertvoll (Pinnacle = Wahrheits-Anker). Trading-Pfad nutzt
    # Soft-Lag separat über fetch_wm_poly_prices/auto-trigger.
    triggered = (
        pinn_move_pp >= sm_cfg["min_pinn_move_pp"]
        and (hours_since_open is None or hours_since_open >= sm_cfg["min_hours_since_open"])
    )
    # Soft-Lag-Bonus: wenn weiterhin Soft-Book-Lag besteht, ist es ein "frischer"
    # Sharp-Move → Conviction-Score gibt extra Punkt
    soft_lag_bonus = soft_lag_pp >= sm_cfg["min_soft_lag_pp"]

    return {
        "triggered": triggered,
        "pinn_move_pp": round(pinn_move_pp, 2),
        "soft_lag_pp": round(soft_lag_pp, 2),
        "soft_lag_bonus": soft_lag_bonus,
        "hours_since_open": round(hours_since_open, 1) if hours_since_open is not None else None,
        "open_pinn_odds": open_pinn,
        "current_pinn_odds": curr_pinn,
    }


def detect_opening_movement(pick: dict, context: dict, cfg: dict) -> Optional[dict]:
    """
    Markiert ob Pinnacle sich seit Opening IN Pick-Richtung bewegt hat.
    Schwächere Schwelle als Sharp-Move (für Conviction-Sub-Punkt).
    """
    om_cfg = cfg.get("opening_movement", {})
    if not om_cfg.get("enabled", True):
        return None
    history = context.get("odds_history") or []
    if not history or len(history) < 2:
        return None

    pick_key_map = {"home": "hw", "draw": "dr", "away": "aw",
                    "over": "o25", "under": "u25"}
    # Granularer Key first (deckt O15/O35/BTTS/Corner), fallback auf alt
    key = _pick_odds_key(pick.get("market", ""))
    if not key:
        direction = _pick_direction(pick.get("market", ""))
        key = pick_key_map.get(direction)
    if not key:
        return None

    opening = history[0]
    current = history[-1]
    open_q = opening.get(f"pinn_{key}") or opening.get(key)
    curr_q = current.get(f"pinn_{key}") or current.get(key)
    if not isinstance(open_q, (int, float)) or not isinstance(curr_q, (int, float)):
        return None
    if open_q <= 1.0 or curr_q <= 1.0:
        return None

    move_pp = (1.0 / curr_q - 1.0 / open_q) * 100   # positiv = Pinn glaubt Pick mehr
    threshold = om_cfg.get("min_pp_in_pick_direction", 3.0)
    return {
        "in_pick_direction": move_pp >= threshold,
        "move_pp": round(move_pp, 2),
    }


# ──────────────────────────────────────────────────────────────────────────
#  Conviction-Score Berechnung
# ──────────────────────────────────────────────────────────────────────────
def compute_conviction_score(pick: dict, signal_output: dict,
                             context: dict) -> dict:
    """
    Berechnet 0-10 Conviction-Score basierend auf Signal-Output + Markt-Daten.

    Args:
      pick:          aus generate_wm_picks (market, edgePP, odds, modelOdds, ...)
      signal_output: aus sharp_signals.registry.evaluate_signals()
                     {signals: [...], combined_score_pp, n_positive_signals}
      context:       {odds_history, odds_snapshot, ...}

    Returns:
      {
        "score":         int 0-10,
        "verdict":       "top" | "abwaegen" | "skip",
        "label":         "🎯 Top-Wette" | "⭐ Gute Wette" | None,
        "family_scores": {family: points},
        "evidence":      [str, ...] — was zu welchen Punkten geführt hat
        "sharp_move":    sharp_move-dict oder None,
        "opening_movement": opening-movement-dict oder None,
      }
    """
    cfg = _load_config()
    weights = _load_signal_weights()
    caps = cfg["family_caps"]
    signals = signal_output.get("signals") or []

    # Pro Signal: Direction-Vorzeichen × bayesian weight × confidence
    # Wir betrachten nur Signale mit positive contribution (score>0) als "Conviction-Punkt"
    # Negative Signale dämpfen aber nicht direkt — sie stehen schon im signalAdjustment.
    def _signal_contributes(name: str) -> float:
        for s in signals:
            if s.get("name") == name and (s.get("score") or 0) > 0:
                return float(s.get("confidence", 0.5)) * weights.get(name, 1.0)
        return 0.0

    family_scores = {"sharp_money": 0, "form": 0, "context": 0,
                     "realtime": 0, "market": 0, "model": 0}
    evidence = []

    # ── Familie 1: Sharp-Money-Konsens (max 3) ────────────────────────────
    sharp_signals_active = []
    for name in ("lead_lag_bias", "steam_lag", "polymarket_sharp"):
        if _signal_contributes(name) > 0:
            sharp_signals_active.append(name)
            evidence.append(f"Sharp: {name}")

    sharp_count = min(len(sharp_signals_active), 2)   # max 2 von Sharp-Signalen

    # Opening-Movement zusätzlicher Punkt
    om = detect_opening_movement(pick, context, cfg)
    if om and om.get("in_pick_direction"):
        sharp_count += 1
        evidence.append(f"Pinnacle bewegt {om['move_pp']:+.1f}pp seit Eröffnung in Pick-Richtung")

    # Sharp-Move-Trigger (Pinnacle ≥X pp Move + Zeit) extra Punkt — unabhängig
    # vom Soft-Lag jetzt (Lockerung 09.06.2026). Soft-Lag-Bonus gibt nochmal +1.
    # Move-Age-Decay: ≤7d=100%, ≤14d=80%, ≤21d=50%, >21d=20%, >30d=0% (Safety
    # gegen ewig nachhängende historische Moves).
    sm = detect_sharp_move(pick, context, cfg)
    if sm and sm.get("triggered"):
        hours = sm.get("hours_since_open") or 0
        days = hours / 24
        if days > 30:
            decay = 0.0
        elif days > 21:
            decay = 0.2
        elif days > 14:
            decay = 0.5
        elif days > 7:
            decay = 0.8
        else:
            decay = 1.0
        sm["move_age_decay"] = decay
        sm["move_age_days"] = round(days, 1)
        if decay >= 1.0:
            sharp_count += 1
            evidence.append(f"Sharp-Move: Pinnacle {sm['pinn_move_pp']:+.1f}pp seit Eröffnung")
        elif decay >= 0.5:
            sharp_count += 1  # ganzer Punkt aber Evidence flaggt Alter
            evidence.append(f"Sharp-Move älter ({days:.0f}d): Pinnacle {sm['pinn_move_pp']:+.1f}pp — Punkt teil-gedämpft")
        elif decay > 0:
            # Bruchteil-Punkt nicht im Cap-System darstellbar → kein Punkt, nur Evidence
            evidence.append(f"Sharp-Move sehr alt ({days:.0f}d): Pinnacle {sm['pinn_move_pp']:+.1f}pp — kein Conviction-Punkt")
        # decay==0: nichts, evidence still leer
        if sm.get("soft_lag_bonus") and decay >= 0.5:
            sharp_count += 1
            evidence.append(f"Bonus: Soft-Books {sm['soft_lag_pp']:.1f}pp hinter Pinnacle")

    family_scores["sharp_money"] = min(sharp_count, caps["sharp_money"])

    # ── Familie 2: Form-Konsens (max 2) ───────────────────────────────────
    form_signals_active = []
    for name in ("form_trend", "xg_strength", "h2h_pattern"):
        if _signal_contributes(name) > 0:
            form_signals_active.append(name)
            evidence.append(f"Form: {name}")
    family_scores["form"] = min(len(form_signals_active), caps["form"])

    # ── Familie 3: Kontext (max 2) ────────────────────────────────────────
    ctx_signals_active = []
    for name in ("travel_burden", "injury", "weather_signal",
                 "pressure_index", "incentive_signal"):
        if _signal_contributes(name) > 0:
            ctx_signals_active.append(name)
            evidence.append(f"Kontext: {name}")
    family_scores["context"] = min(len(ctx_signals_active), caps["context"])

    # ── Familie 4: Realtime — Lineup höher gewichtet (max 2) ──────────────
    if _signal_contributes("lineup_signal") > 0:
        family_scores["realtime"] = caps["realtime"]   # voll
        evidence.append("Realtime: Lineup T-1h stützt Pick")

    # ── Familie 5: Markt-Konsens (max 1) ──────────────────────────────────
    market_signals_active = []
    for name in ("public_static_bias", "apif_predictions"):
        if _signal_contributes(name) > 0:
            market_signals_active.append(name)
            evidence.append(f"Markt-Konsens: {name}")
    family_scores["market"] = min(len(market_signals_active), caps["market"])

    # ── Familie 6: Modell-Sanity (max 1) ──────────────────────────────────
    # Modell darf nicht halluzinieren — model_odds darf nicht > 10pp vom Markt sein
    model_odds = pick.get("modelOdds")
    market_odds = pick.get("odds")
    if isinstance(model_odds, (int, float)) and isinstance(market_odds, (int, float)):
        if model_odds > 1.0 and market_odds > 1.0:
            model_implied = 100.0 / model_odds
            market_implied = 100.0 / market_odds
            if abs(model_implied - market_implied) <= 10.0:
                family_scores["model"] = caps["model"]
                evidence.append("Modell ≤10pp vom Markt — keine Halluzination")

    # ── Total Score ───────────────────────────────────────────────────────
    total = sum(family_scores.values())
    total = min(total, 10)

    # ── Verdict ───────────────────────────────────────────────────────────
    thresholds = cfg["verdict_thresholds"]
    if total >= thresholds["top"]:
        verdict, label = "top", "🎯 Top-Wette"
    elif total >= thresholds["abwaegen"]:
        verdict, label = "abwaegen", "⭐ Gute Wette"
    elif total >= thresholds["skip"]:
        verdict, label = "watch", "👁 Beobachten"
    else:
        verdict, label = "skip", None

    return {
        "score": int(total),
        "verdict": verdict,
        "label": label,
        "family_scores": family_scores,
        "evidence": evidence,
        "sharp_move": sm,        # bereits oben berechnet
        "opening_movement": om,
    }
