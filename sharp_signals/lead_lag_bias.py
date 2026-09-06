"""
sharp_signals/lead_lag_bias.py — Pinnacle Lead-Lag gegenüber Soft-Books

Konzept (Lucas 07.06.2026):
  Pinnacle ist der schärfste Buchmacher. Wenn Pinnacle eine Quote ändert
  (z.B. Heim von 2.10 → 1.85), reagiert sharp money als erstes. Soft-Books
  (William Hill, Bet365, Unibet, …) ziehen mit Verzögerung von Minuten bis
  Stunden nach.

  In dem Lag-Fenster ist die Pinnacle-Quote bereits "korrekt" (scharfer Preis),
  und die Soft-Book-Quoten noch "alt". Wenn wir auf Pinnacle-Niveau wetten,
  haben wir die scharfe Quote — bevor Konsens-Bookies sie korrigieren.

Zwei Stufen des Signals:

  EARLY (Pinnacle moved, Soft-Books NOT yet):
    → starkes Signal in Pinnacle's Bewegungsrichtung
    → Bewertung: bis zu +score je nach Pinnacle-Move-Größe

  CONFIRMED (Pinnacle moved, Soft-Books followed):
    → die These ist bestätigt — Sharp-Pressure war echt
    → noch stärkeres Signal weil mehrere Bookies "einig" sind
    → Bewertung: höherer score als EARLY

Implied Probabilities (devigt) werden verglichen, NICHT rohe Quoten —
weil verschiedene Bookies unterschiedliche Margins haben.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from sharp_signals.base import Signal, SignalResult, snapshot_am_fensteranfang


# Schwellen — alle via cocobet_config.json profiles.<active>.lead_lag.* überschreibbar
DEFAULT_THRESHOLDS = {
    # Min. Pinnacle-Move (in pp implied prob) damit das Signal triggert
    "pinn_min_move_pp":    1.5,
    # Lookback-Fenster für Pinnacle-Move (Stunden)
    "pinn_lookback_h":     24,
    # Soft-Book Lag-Schwelle: wenn Soft-Move < lag_ratio × Pinn-Move → EARLY
    "soft_lag_ratio":      0.5,
    # Score-Beiträge in pp gegen den Markt — werden vom combiner gewichtet
    "early_base_score_pp":     2.5,
    "confirmed_base_score_pp": 4.0,
    # Confidence-Boost wenn mehrere Soft-Books bestätigen
    "multi_soft_bonus":    0.15,
}


def _load_thresholds() -> dict:
    """Lädt Schwellen aus cocobet_config.json mit Defaults als Fallback."""
    try:
        import json, os
        from pathlib import Path
        raw_path = Path(__file__).parent.parent / "cocobet_config.json"
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        active = os.environ.get("COCOBET_PROFILE") or raw["profiles"].get("active", "wm2026")
        cfg = raw["profiles"].get(active, {}).get("lead_lag") or {}
        return {**DEFAULT_THRESHOLDS, **cfg}
    except Exception:
        return DEFAULT_THRESHOLDS


def _devig_implied(hw: float, dr: float, aw: float) -> tuple[float, float, float]:
    """
    Devigt eine 1X2-Quote (verhältnismäßige Proportional-Devigging).
    Returns implied probabilities ohne Margin.
    """
    if not (hw and dr and aw):
        return (None, None, None)
    p_hw, p_dr, p_aw = 1.0/hw, 1.0/dr, 1.0/aw
    s = p_hw + p_dr + p_aw
    if s <= 0:
        return (None, None, None)
    return (p_hw/s, p_dr/s, p_aw/s)


def _parse_ts(ts: str) -> Optional[datetime]:
    if not ts:
        return None
    try:
        # ISO 8601 mit oder ohne Z
        s = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _select_outcome_key_from_market(market: str) -> Optional[str]:
    """
    Welches Outcome wird vom Pick bewettet? Mappt freie Market-Strings auf
    Snapshot-Keys: 1X2 → hw/dr/aw, O/U → o15/o25/o35/u15/u25/u35.
    09.07.2026 (Lucas): O/U ergänzt — Softbook-Lag jetzt auch auf Tor-Linien.
    AH/BTTS → None (Signal nicht anwendbar).
    """
    m = (market or "").lower()
    if "heimsieg" in m or m == "1":
        return "hw"
    if "auswärtssieg" in m or "auswartssieg" in m or m == "2":
        return "aw"
    if "unentsch" in m or m == "x":
        return "dr"
    # DNB Heim/Auswärts ist verwandt mit hw/aw (Draw = Push)
    if "dnb" in m and ("heim" in m or "home" in m):
        return "hw"
    if "dnb" in m and ("ausw" in m or "away" in m):
        return "aw"
    # O/U-Tor-Linien (2-way): über/unter × 1.5/2.5/3.5
    if "tore" in m:
        over = "über" in m or "uber" in m or "over" in m
        under = "unter" in m or "under" in m
        if over or under:
            for lbl, suf in (("1.5", "15"), ("1,5", "15"),
                             ("2.5", "25"), ("2,5", "25"),
                             ("3.5", "35"), ("3,5", "35")):
                if lbl in m:
                    return ("o" if over else "u") + suf
    return None


# Komplementär-Keys für O/U-2-way-Devig
_OU_COMPLEMENT = {"o15": "u15", "u15": "o15", "o25": "u25",
                  "u25": "o25", "o35": "u35", "u35": "o35"}


def _implied_for_outcome(snap: dict, outcome: str) -> Optional[float]:
    """De-viggte implied Wkt eines Outcomes aus einem Snapshot.
    1X2 (hw/dr/aw) → proportionales 3-way-Devig; O/U (oNN/uNN) → 2-way complementary-devig.
    Fallback (Gegenquote fehlt) → rohe implied 1/odds."""
    if outcome in ("hw", "dr", "aw"):
        p = _devig_implied(snap.get("hw"), snap.get("dr"), snap.get("aw"))
        return p[{"hw": 0, "dr": 1, "aw": 2}[outcome]]
    if outcome in _OU_COMPLEMENT:
        o = snap.get(outcome)
        if not o or o <= 1.0:
            return None
        opp = snap.get(_OU_COMPLEMENT[outcome])
        if opp and opp > 1.0:
            a, b = 1.0 / o, 1.0 / opp
            return a / (a + b)
        return 1.0 / o
    return None


class LeadLagBiasSignal(Signal):
    """
    Pinnacle Lead-Lag vs Soft-Books für 1X2-/DNB-Picks.

    Nutzt context["odds_history"] (eine Liste {ts, hw, dr, aw, bk}).
    Für die gepickte Outcome-Seite (hw/dr/aw):
      1) Berechne Pinnacle-Move in den letzten lookback_h Stunden
      2) Berechne Soft-Book-Move im gleichen Fenster (William Hill, Unibet, …)
      3) Wenn Pinn-Move ≥ Schwelle UND Soft-Move signifikant kleiner → EARLY
      4) Wenn Pinn-Move ≥ Schwelle UND Soft-Move ähnlich groß → CONFIRMED
    """

    def __init__(self):
        self._t = _load_thresholds()

    def name(self) -> str:
        return "lead_lag_bias"

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        # Nur für 1X2-/DNB-Märkte sinnvoll
        outcome = _select_outcome_key_from_market(pick.get("market", ""))
        if not outcome:
            return None

        history = context.get("odds_history") or []
        if len(history) < 2:
            return None

        snap_ts = _parse_ts(context.get("snapshot_ts") or "") or datetime.now(timezone.utc)
        lookback_seconds = self._t["pinn_lookback_h"] * 3600

        # Partitioniere History nach Bookmaker
        by_bk: dict[str, list[dict]] = {}
        for e in history:
            bk = (e.get("bk") or "?").lower()
            by_bk.setdefault(bk, []).append(e)

        # Sortiere chronologisch
        for bk in by_bk:
            by_bk[bk].sort(key=lambda x: x.get("ts", ""))

        # Pinnacle-Move berechnen
        pinn = by_bk.get("pinnacle") or []
        if len(pinn) < 2:
            return None  # ohne Pinn-History kein Signal

        pinn_move = self._compute_move_pp(pinn, outcome, snap_ts, lookback_seconds)
        if pinn_move is None or abs(pinn_move) < self._t["pinn_min_move_pp"]:
            return None  # keine relevante Pinn-Bewegung

        # Soft-Book-Moves berechnen
        soft_bks = [bk for bk in by_bk.keys() if bk != "pinnacle" and bk != "?"]
        soft_moves = []
        for bk in soft_bks:
            mv = self._compute_move_pp(by_bk[bk], outcome, snap_ts, lookback_seconds)
            if mv is not None:
                soft_moves.append((bk, mv))

        if not soft_moves:
            # Wir haben Pinnacle-Move aber keine Soft-Book-Vergleichsdaten →
            # Vorsicht: kein Signal feuern (wir wüssten nicht ob EARLY oder CONFIRMED)
            return None

        # Welcher Anteil der Soft-Books ist Pinnacle gefolgt?
        # "Gefolgt" = Move in selber Richtung UND Magnitude ≥ lag_ratio × Pinn-Move
        threshold = abs(pinn_move) * self._t["soft_lag_ratio"]
        followed = []
        lagging  = []
        for bk, mv in soft_moves:
            if mv * pinn_move > 0 and abs(mv) >= threshold:
                followed.append((bk, mv))
            else:
                lagging.append((bk, mv))

        # Score-Richtung: positiv = Pinnacle macht Outcome wahrscheinlicher
        # (Quote fällt → implied prob steigt → Signal sagt "BET das Outcome")
        # Für den picker-side bedeutet positives pinn_move auf hw, dass Heim
        # wahrscheinlicher wird — wenn der Pick auf Heim ist, ist das gut.
        direction = 1.0 if pinn_move > 0 else -1.0

        # EARLY: mehrheitlich Soft-Books haben nicht nachgezogen
        # CONFIRMED: mehrheitlich haben nachgezogen
        is_confirmed = len(followed) >= len(lagging) and len(followed) > 0
        is_early     = not is_confirmed and len(lagging) > 0

        base_score = (self._t["confirmed_base_score_pp"] if is_confirmed
                      else self._t["early_base_score_pp"])

        # Magnituden-Skalierung: größerer Pinn-Move → stärkeres Signal
        # (linear bis 5pp Pinn-Move = volle Stärke)
        mag_scale = min(1.5, abs(pinn_move) / 3.0)
        score = direction * base_score * mag_scale

        # Confidence: Anzahl Soft-Books × Bonus + Basis
        confidence = 0.55 + self._t["multi_soft_bonus"] * len(soft_moves)
        confidence = min(0.95, confidence)

        # Evidence-Text für die Card
        oc_label = {"hw": "Heim", "dr": "X", "aw": "Auswärts",
                    "o15": "Über 1.5", "u15": "Unter 1.5",
                    "o25": "Über 2.5", "u25": "Unter 2.5",
                    "o35": "Über 3.5", "u35": "Unter 3.5"}.get(outcome, outcome)
        if is_confirmed:
            soft_str = ", ".join(bk for bk, _ in followed[:2])
            evidence = (f"Pinnacle hat {oc_label} um {pinn_move:+.1f}pp bewegt, und {soft_str} "
                        f"ziehen schon nach ({len(followed)}) — der Move ist bestätigt.")
        else:
            soft_str = ", ".join(bk for bk, _ in lagging[:2])
            evidence = (f"Pinnacle hat {oc_label} um {pinn_move:+.1f}pp bewegt, {soft_str} "
                        f"hängen noch hinterher ({len(lagging)}) — wir sind früh dran.")

        return SignalResult(
            score=round(score, 2),
            confidence=round(confidence, 2),
            evidence=evidence,
            metadata={
                "stage":       "confirmed" if is_confirmed else "early",
                "pinn_move_pp": round(pinn_move, 2),
                "soft_moves":   [{"bk": bk, "move_pp": round(mv, 2)}
                                 for bk, mv in soft_moves],
                "outcome":      outcome,
            },
        )

    @staticmethod
    def _compute_move_pp(snaps: list[dict], outcome: str,
                         snap_ts: datetime, lookback_seconds: float) -> Optional[float]:
        """
        Berechnet implied-prob-Bewegung von start_of_lookback bis jetzt
        in Prozentpunkten. Positiv = Outcome wahrscheinlicher geworden.
        """
        if len(snaps) < 2:
            return None

        # Jüngster Snap = "nach"
        last = snaps[-1]
        # 06.09.2026: der Preis, wie er am FENSTERANFANG stand — nicht der erste Snapshot
        # im Fenster. Unsere Zeitreihe schreibt nur bei Preisaenderung fort; ein ruhiger
        # Markt, der dann kippt, hatte im Fenster genau einen Eintrag und war unsichtbar.
        # Ueber die ganze Liga-History: +288 sichtbare Moves >= 2 pp (+28 %).
        # Siehe base.snapshot_am_fensteranfang.
        first_in_window = snapshot_am_fensteranfang(snaps, snap_ts, lookback_seconds)

        if first_in_window is None:
            return None
        if first_in_window is last:
            return None  # zu wenig Auflösung im Fenster

        p_before = _implied_for_outcome(first_in_window, outcome)
        p_after  = _implied_for_outcome(last, outcome)

        if p_before is None or p_after is None:
            return None
        return (p_after - p_before) * 100.0
