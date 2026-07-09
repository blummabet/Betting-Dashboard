"""
sharp_signals/public_static_bias.py — Konsens-Bookmaker vs Pinnacle

Konzept:
  Wenn Pinnacle (sharp) und ein Konsens-Soft-Book (bet365, William Hill, …)
  unterschiedliche implied probabilities für denselben Outcome haben, ist
  das ein direkter Bias-Indikator.

  Public überbettet hw (z.B. +5pp) → die Masse glaubt Heim wahrscheinlicher
  als Pinnacle's sharp Schätzung. Historisch verlieren Public-Konsens-Picks
  → ein Pick AUF hw bei Pinnacle reitet GEGEN den Public-Bias und gewinnt
  meistens (Pinnacle hat häufiger recht).

  Score-Direction:
    Pick auf X mit Public-Bias_X > 0  →  positiver Score (wir contrarian zu Public)
    Pick auf X mit Public-Bias_X < 0  →  negativer Score (wir mit Public → no edge)

Migration von generate_wm_picks.compute_public_bias() ins neue Signal-Interface.
"""
from __future__ import annotations
from typing import Optional
from sharp_signals.base import Signal, SignalResult


DEFAULT_THRESHOLDS = {
    # FIX 09.06.2026: min_bias 3 → 2 (Audit zeigte 92% der WM-Diffs in <3pp Range,
    # 1% im sweet-spot). Pinnacle und Soft-Books alignen pre-WM zu stark, daher
    # sensibleren Trigger nötig. Erste echte Sharp-Bewegung wird ab 2pp sichtbar.
    "min_bias_pp":      2.0,
    "max_credible_pp": 15.0,
    "base_score_pp":    1.2,
    "magnitude_scale":  0.5,
}


def _load_thresholds() -> dict:
    try:
        import json, os
        from pathlib import Path
        raw = json.loads((Path(__file__).parent.parent / "cocobet_config.json")
                         .read_text(encoding="utf-8"))
        active = os.environ.get("COCOBET_PROFILE") or raw["profiles"].get("active", "wm2026")
        cfg = raw["profiles"].get(active, {}).get("public_bias") or {}
        return {**DEFAULT_THRESHOLDS, **cfg}
    except Exception:
        return DEFAULT_THRESHOLDS


def _devig_1x2(hw: float, dr: float, aw: float) -> tuple[float, float, float] | tuple[None, None, None]:
    if not (hw and dr and aw):
        return (None, None, None)
    p_hw, p_dr, p_aw = 1.0/hw, 1.0/dr, 1.0/aw
    s = p_hw + p_dr + p_aw
    if s <= 0:
        return (None, None, None)
    return (p_hw/s, p_dr/s, p_aw/s)


def _outcome_key_from_market(market: str) -> Optional[str]:
    """Map freier Market-String auf hw/dr/aw — gleiches Pattern wie LeadLag."""
    m = (market or "").lower()
    if "heimsieg" in m: return "hw"
    if "auswärtssieg" in m or "auswartssieg" in m: return "aw"
    if "unentsch" in m: return "dr"
    if "dnb" in m and ("heim" in m or "home" in m): return "hw"
    if "dnb" in m and ("ausw" in m or "away" in m): return "aw"
    return None


def _ou_btts_key(market: str) -> Optional[str]:
    """Map O/U (1.5/2.5/3.5) + BTTS auf entsprechende Snapshot-Keys.
    09.07.2026: 1.5 + 3.5 ergänzt — Softbook covert jetzt die komplette Tor-Leiter."""
    m = (market or "").lower()
    if "ecken" in m or "corner" in m: return None
    # O/U-Linien (Public-side jetzt für 1.5/2.5/3.5 verfügbar)
    if "tore" in m:
        over = "über" in m or "uber" in m or "over" in m
        under = "unter" in m or "under" in m
        if over or under:
            for lbl, suf in (("1.5", "15"), ("1,5", "15"),
                             ("2.5", "25"), ("2,5", "25"),
                             ("3.5", "35"), ("3,5", "35")):
                if lbl in m:
                    return ("o" if over else "u") + suf
    # BTTS
    if "beide" in m or "btts" in m:
        return "bttsN" if ("nein" in m or "no" in m) else "bttsY"
    return None


class PublicStaticBiasSignal(Signal):
    """
    Vergleicht Pinnacle vs Konsens-Bookmaker für den gepickten Outcome.

    Context erwartet:
      odds_snapshot: { "hw": float, "dr": float, "aw": float,
                       "public_hw": float, "public_dr": float, "public_aw": float,
                       "public_bookmaker": str }
    """

    def __init__(self):
        self._t = _load_thresholds()

    def name(self) -> str:
        return "public_static_bias"

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        snap = context.get("odds_snapshot") or {}
        market = pick.get("market", "")

        # ── 1. 1X2 / DC / DNB / AH (alte Logik) ──────────────────────────
        outcome = _outcome_key_from_market(market)
        if outcome:
            return self._eval_1x2(snap, outcome)

        # ── 2. O/U 2.5 + BTTS (NEU 09.06.2026) ───────────────────────────
        ou_key = _ou_btts_key(market)
        if ou_key:
            return self._eval_ou_btts(snap, ou_key)

        return None

    def _eval_ou_btts(self, snap: dict, key: str) -> Optional[SignalResult]:
        """Public-vs-Pinnacle Bias für O/U 2.5 oder BTTS Ja/Nein.
        Bei 2-way Märkten ist devig anders als bei 1X2 — wir nutzen einfaches
        complementary-pair devig (vig gleichmäßig verteilt)."""
        sharp_odds  = snap.get(key)
        public_odds = snap.get(f"public_{key}")
        if not sharp_odds or not public_odds: return None
        if sharp_odds <= 1.0 or public_odds <= 1.0: return None

        # Komplementärer Markt-Key für devig (z.B. o25 ↔ u25)
        pairs = {"o15": "u15", "u15": "o15",
                 "o25": "u25", "u25": "o25",
                 "o35": "u35", "u35": "o35",
                 "bttsY": "bttsN", "bttsN": "bttsY"}
        opp = pairs.get(key)
        sharp_opp  = snap.get(opp) if opp else None
        public_opp = snap.get(f"public_{opp}") if opp else None

        # Devig wenn opp-Quote da ist; sonst raw implied
        if sharp_opp and public_opp:
            s_main = 1.0 / sharp_odds
            s_opp  = 1.0 / sharp_opp
            sharp_p = s_main / (s_main + s_opp)
            p_main = 1.0 / public_odds
            p_opp  = 1.0 / public_opp
            public_p = p_main / (p_main + p_opp)
        else:
            sharp_p  = 1.0 / sharp_odds
            public_p = 1.0 / public_odds

        diff_pp = (public_p - sharp_p) * 100.0
        abs_diff = abs(diff_pp)
        if abs_diff < self._t["min_bias_pp"]: return None
        if abs_diff > self._t["max_credible_pp"]: return None

        # Direction: Public überbettet (diff > 0) → contrarian Pick = positiv
        direction = 1.0 if diff_pp > 0 else -1.0
        extra = (abs_diff - self._t["min_bias_pp"]) * self._t["magnitude_scale"]
        score = direction * (self._t["base_score_pp"] + extra)
        confidence = min(0.80, 0.40 + abs_diff * 0.04)

        oc_label = {"o15": "Über 1.5", "u15": "Unter 1.5",
                    "o25": "Über 2.5", "u25": "Unter 2.5",
                    "o35": "Über 3.5", "u35": "Unter 3.5",
                    "bttsY": "BTTS Ja", "bttsN": "BTTS Nein"}[key]
        public_bk = snap.get("public_ou_bookmaker", "Public")
        direction_str = "über-bettet" if diff_pp > 0 else "unter-bettet"
        if diff_pp > 0:
            evidence = (f"Die breite Masse ({public_bk}) hat {oc_label} um {abs_diff:.1f}pp "
                        f"überbewertet (vs Pinnacle) — wir halten bewusst dagegen.")
        else:
            evidence = (f"Die breite Masse ({public_bk}) lässt {oc_label} um {abs_diff:.1f}pp "
                        f"links liegen (vs Pinnacle) — kein Publikums-Hebel hier.")

        return SignalResult(
            score=round(score, 2), confidence=round(confidence, 2), evidence=evidence,
            metadata={"market_key": key, "diff_pp": round(diff_pp, 2),
                      "sharp_p": round(sharp_p, 4), "public_p": round(public_p, 4),
                      "public_bk": public_bk},
        )

    def _eval_1x2(self, snap: dict, outcome: str) -> Optional[SignalResult]:
        s_hw, s_dr, s_aw = snap.get("hw"), snap.get("dr"), snap.get("aw")
        p_hw, p_dr, p_aw = snap.get("public_hw"), snap.get("public_dr"), snap.get("public_aw")
        if not all([s_hw, s_dr, s_aw, p_hw, p_dr, p_aw]):
            return None

        sharp  = _devig_1x2(s_hw, s_dr, s_aw)
        public = _devig_1x2(p_hw, p_dr, p_aw)
        if sharp[0] is None or public[0] is None:
            return None

        idx = {"hw": 0, "dr": 1, "aw": 2}[outcome]
        diff_pp = (public[idx] - sharp[idx]) * 100.0   # positiv = Public überbettet

        abs_diff = abs(diff_pp)
        if abs_diff < self._t["min_bias_pp"]:
            return None  # zu rauschig
        if abs_diff > self._t["max_credible_pp"]:
            return None  # wahrscheinlich Daten-Anomalie

        # Direction: wenn Public überbettet (diff > 0), reitet ein Pick auf
        # diesem Outcome GEGEN den Public-Konsens → positives Signal
        direction = 1.0 if diff_pp > 0 else -1.0

        # Magnitude: Base + linear über min_bias_pp
        extra = (abs_diff - self._t["min_bias_pp"]) * self._t["magnitude_scale"]
        score = direction * (self._t["base_score_pp"] + extra)

        # Confidence steigt mit Bias-Größe (bis Cap)
        confidence = min(0.85, 0.45 + abs_diff * 0.04)

        oc_label = {"hw": "Heim", "dr": "X", "aw": "Auswärts"}[outcome]
        public_bk = snap.get("public_bookmaker", "Public")
        direction_str = "über-bettet" if diff_pp > 0 else "unter-bettet"
        if diff_pp > 0:
            evidence = (f"Die breite Masse ({public_bk}) hat {oc_label} um {abs_diff:.1f}pp "
                        f"überbewertet (vs Pinnacle) — wir halten bewusst dagegen.")
        else:
            evidence = (f"Die breite Masse ({public_bk}) lässt {oc_label} um {abs_diff:.1f}pp "
                        f"links liegen (vs Pinnacle) — kein Publikums-Hebel hier.")

        return SignalResult(
            score=round(score, 2),
            confidence=round(confidence, 2),
            evidence=evidence,
            metadata={
                "outcome":   outcome,
                "diff_pp":   round(diff_pp, 2),
                "sharp_p":   round(sharp[idx], 4),
                "public_p":  round(public[idx], 4),
                "public_bk": public_bk,
            },
        )
