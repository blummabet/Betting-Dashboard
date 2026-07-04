"""
streak_momentum.py — Serien als Pick-Signal (29.06.2026, Lucas: Umkehrschluss zu „Signale
stärken den Streak"). Hat ein Team eine lange, von der EIGEN-Grundrate gestützte Serie in der
Markt-Richtung (z.B. 7× Über), ist das ein Zusatz-Hinweis für den Pick.

04.07.2026 (Lucas: „Streaks zu starken Zahlen machen") — Experten-Review umgesetzt:
  · MIN_LENGTH 4→3: das Signal feuerte 1× in 153 Picks → konnte nie gelernt werden. Lockerer.
  · Markt-Persistenz (Backtest-Evidenz): Ecken-Serien persistieren (+4% ROI n=97), Tor-/BTTS-
    Ergebnis-Serien bluten (btts −15%, over25 −11%, noBtts −26%). Pro Markt ein Multiplikator →
    stil-persistente Serien zählen mehr, varianzlastige weniger.
  · xG-Deckung (compute_streaks.xgBacked): eine Über-Serie aus Glückstoren (xG unter der Linie)
    wird stark gedämpft, eine xG-gestützte voll (leicht geboostet). Kern gegen Gambler's Fallacy.
  · Gegner-Normalisierung: eine Serie gegen einen Gegner, der die Richtung mitträgt, ist mehr wert.

BEWUSST DISZIPLINIERT (unverändert):
  · KLEIN gedeckelt (±max_pp) — eine Serie ≠ Edge (Pinnacle preist Form ein).
  · form-Familie (registry SIGNAL_GROUPS) → Anti-Korr-Discount gegen form_trend/xg/h2h.
  · Nutzt EIGEN-Tendenz (length + ratePct + rohe Gegner-Grundrate), NICHT den matchup/signal-
    adjustierten Status → kein Zirkel.
  · Der Bayesian-Loop kalibriert das Gesamt-Gewicht; die Markt-/xG-Differenzierung passiert hier
    im Score (sichere „Segmentierung" ohne den Lern-Kern zu splitten). Prior via signal_priors.
Tunebar: cocobet_config.json → profiles.<profil>.streak_momentum.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from sharp_signals.base import Signal, SignalResult

# ── Defaults (via cocobet_config.json überschreibbar) ──────────────────────────
DEFAULTS = {
    "min_length":    3,      # kürzere Serien = Rauschen (vorher 4 → feuerte fast nie)
    "min_rate_pct":  55,     # Serie muss von der eigenen Grundrate gestützt sein
    "per_streak":    0.15,   # pp pro gestützter Serie (× Länge × Stärke × Persistenz × xG × Gegner)
    "max_pp":        2.5,    # harter Deckel (klein!)
    "min_fire_abs":  0.25,   # darunter nicht feuern
    "backed_factor": 1.15,   # xgBacked == True → leichter Boost
    "unbacked_factor": 0.35, # xgBacked == False → stark dämpfen (Glückstore)
    "opp_scale_min": 0.80,   # Gegner-Normalisierung untere Grenze
    "opp_scale_max": 1.25,   # … obere Grenze
    # Markt-Persistenz aus dem Backtest (by_market ROI). 1.0 = voll vertrauen.
    "market_persistence": {
        "over25": 0.5, "under25": 0.5,       # Tor-Ergebnis-Serien: varianzlastig
        "bttsYes": 0.45, "bttsNo": 0.4,      # BTTS: laut Backtest klar negativ
        "cornersOver": 1.0, "cornersUnder": 0.4,  # Ecken über persistiert, unter nicht
    },
}

# (Markt-Familie, Richtung) → (stützender Streak-Typ, gegenläufiger Streak-Typ)
_SUPPORT = {
    ("ou", +1):      ("over25", "under25"),
    ("ou", -1):      ("under25", "over25"),
    ("btts", +1):    ("bttsYes", "bttsNo"),
    ("btts", -1):    ("bttsNo", "bttsYes"),
    ("corners", +1): ("cornersOver", "cornersUnder"),
    ("corners", -1): ("cornersUnder", "cornersOver"),
}

# Streak-Typen, deren „Over/Ja"-Seite von einer HOHEN rohen Gegner-Rate gestützt wird.
# (_opp_rate_pct liefert immer die Over/Ja-Rate → für Under/Nein invertieren.)
_OVER_SIDE = {"over25", "bttsYes", "cornersOver", "scored", "cards"}


def _load_cfg() -> dict:
    try:
        raw = json.loads((Path(__file__).parent.parent / "cocobet_config.json")
                         .read_text(encoding="utf-8"))
        active = os.environ.get("COCOBET_PROFILE") or raw["profiles"].get("active", "wm2026")
        cfg = raw["profiles"].get(active, {}).get("streak_momentum") or {}
        merged = {**DEFAULTS, **cfg}
        merged["market_persistence"] = {**DEFAULTS["market_persistence"],
                                        **(cfg.get("market_persistence") or {})}
        return merged
    except Exception:
        return DEFAULTS


def _market_family_dir(market: str):
    m = (market or "").lower()
    if "ecken" in m or "corner" in m:
        return ("corners", -1 if ("unter" in m or "under" in m) else +1)
    if "karten" in m or "card" in m:
        return (None, None)   # Karten laut Backtest negativ → nicht bepicken
    if "über" in m or "uber" in m or "over" in m or "unter" in m or "under" in m:
        if "tore" not in m and "goal" not in m and not any(x in m for x in ["1.5", "2.5", "3.5", "1,5", "2,5", "3,5"]):
            return (None, None)
        is_under = "unter" in m or "under" in m
        return ("ou", -1 if is_under else +1)
    if "beide" in m or "btts" in m:
        return ("btts", -1 if ("nein" in m or " no" in m or m.endswith("no")) else +1)
    return (None, None)


def _pick_team_streak(streaks_for_team, stype, pref_venue):
    """Beste Serie eines Teams für einen Typ — venue-passend (Heim/Auswärts), sonst Gesamt."""
    best, best_score = None, -1
    for s in (streaks_for_team or []):
        if s.get("type") != stype:
            continue
        v = s.get("venue")
        score = 2 if v == pref_venue else (1 if v == "all" else 0)
        if score > best_score:
            best, best_score = s, score
    return best


def _opp_factor(s: dict, stype: str, cfg: dict) -> float:
    """Gegner-Normalisierung: trägt der nächste Gegner die Serien-Richtung mit? (roh, kein Zirkel)."""
    opp = (s.get("next") or {}).get("oppRatePct")
    if not isinstance(opp, (int, float)):
        return 1.0
    support = opp if stype in _OVER_SIDE else (100 - opp)   # richtungs-normalisiert
    # support 50% → 1.0 (neutral); 100% → max; 0% → min
    lo, hi = cfg["opp_scale_min"], cfg["opp_scale_max"]
    frac = max(0.0, min(1.0, support / 100.0))
    return lo + (hi - lo) * frac


def _xg_factor(s: dict, cfg: dict) -> float:
    """xG-Deckung → Multiplikator. None (n/a) = neutral, True = Boost, False = stark dämpfen."""
    xgb = s.get("xgBacked")
    if xgb is True:
        return cfg["backed_factor"]
    if xgb is False:
        return cfg["unbacked_factor"]
    return 1.0


class StreakMomentumSignal(Signal):
    """Lange, gestützte Serien beider Teams in der Markt-Richtung → kleiner Pick-Nudge,
    differenziert nach Markt-Persistenz + xG-Deckung + Gegner-Kontext."""

    def name(self) -> str:
        return "streak_momentum"

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        cfg = _load_cfg()
        fam, direction = _market_family_dir(pick.get("market", ""))
        if fam is None:
            return None
        idx = context.get("streaks") or {}
        if not idx:
            return None
        home_id, away_id = context.get("home_id"), context.get("away_id")
        sup_type, opp_type = _SUPPORT[(fam, direction)]
        persist = cfg["market_persistence"]

        score, parts, n_backed, n_unbacked = 0.0, [], 0, 0
        for tid, pref in ((str(home_id), "H"), (str(away_id), "A")):
            team_streaks = idx.get(tid) or []
            for stype, sign in ((sup_type, +1), (opp_type, -1)):
                s = _pick_team_streak(team_streaks, stype, pref)
                if not s:
                    continue
                length = s.get("length") or 0
                rate = s.get("ratePct")
                if length < cfg["min_length"] or rate is None or rate < cfg["min_rate_pct"]:
                    continue
                rate_strength = max(0.0, min(1.0, (rate - 50) / 50.0))   # 50%→0, 100%→1
                xgf = _xg_factor(s, cfg)
                oppf = _opp_factor(s, stype, cfg)
                pmul = persist.get(stype, 0.5)
                contrib = (sign * min(length, 8) * cfg["per_streak"]
                           * rate_strength * pmul * xgf * oppf)
                score += contrib
                if s.get("xgBacked") is True:
                    n_backed += 1
                elif s.get("xgBacked") is False:
                    n_unbacked += 1
                if sign > 0:
                    tag = "✓xG" if s.get("xgBacked") is True else ("⚠️Glück" if s.get("xgBacked") is False else "")
                    parts.append(f"{s.get('team', tid)} {length}× {s.get('market', stype)}{(' '+tag) if tag else ''}")

        if abs(score) < cfg["min_fire_abs"]:
            return None
        score = max(-cfg["max_pp"], min(cfg["max_pp"], round(score, 2)))
        confidence = round(min(0.55, 0.35 + 0.05 * len(parts)), 2)
        if score > 0 and parts:
            ev = "🔥 Serien stützen: " + " · ".join(parts[:2])
        elif score < 0:
            ev = "🔥 Serien laufen gegen den Pick"
        else:
            ev = "🔥 Serien-Momentum neutral"
        return SignalResult(score=score, confidence=confidence, evidence=ev,
                            metadata={"family": fam, "direction": direction,
                                      "n_supporting": len(parts),
                                      "n_xg_backed": n_backed, "n_unbacked": n_unbacked,
                                      "market_type": sup_type})
