"""
sharp_signals/h2h_pattern.py — Head-to-Head Pattern als Pick-Adjustment

Konzept:
  Direkte Vergleiche zeigen oft persistente Spielstil-Konflikte (Tiki-Taka vs
  Konter, Höhe-Vorteile, mentaler Bonus). Wenn ein Team in ≥5 H2H-Spielen
  dominiert hat (≥60% Win-Rate inkl. Draws), ist das ein Indikator.

  Sample-Size-Anforderung: ≥5 Spiele. Darunter Signal zu rauschig.
"""
from __future__ import annotations
from typing import Optional
from sharp_signals.base import Signal, SignalResult


DEFAULT_THRESHOLDS = {
    # FIX 09.06.2026: Schwelle von 5 → 2 (WM-Realität: NTs spielen sich selten
    # 5x gegeneinander; bei 5 würden 95% der Picks ohne H2H-Signal laufen).
    # Score-Scale entsprechend reduziert weil 2-Spiele-Stichprobe rauschiger ist.
    "min_h2h_games":      2,
    "dominance_threshold": 0.55,
    "score_scale_pp":     4.0,     # halbiert wg kleinerer Stichproben
    "min_signal_pp":      0.6,
    # Soft-Penalty wenn Stichprobe sehr klein (2-3 Spiele)
    "small_sample_dampening": 0.6,
    "small_sample_threshold": 4,
}


def _load_thresholds() -> dict:
    try:
        import json, os
        from pathlib import Path
        raw = json.loads((Path(__file__).parent.parent / "cocobet_config.json")
                         .read_text(encoding="utf-8"))
        active = os.environ.get("COCOBET_PROFILE") or raw["profiles"].get("active", "wm2026")
        cfg = raw["profiles"].get(active, {}).get("h2h_pattern") or {}
        return {**DEFAULT_THRESHOLDS, **cfg}
    except Exception:
        return DEFAULT_THRESHOLDS


def _pick_side(market: str) -> int:
    m = (market or "").lower()
    if "heimsieg" in m: return +1
    if "dnb" in m and ("heim" in m or "home" in m): return +1
    if "ah heim" in m: return +1
    if "doppelte chance" in m and "— 1x" in m: return +1
    if "auswärtssieg" in m or "auswartssieg" in m: return -1
    if "dnb" in m and ("ausw" in m or "away" in m): return -1
    if "ah auswärts" in m or "ah auswarts" in m: return -1
    if "doppelte chance" in m and "— x2" in m: return -1
    return 0


def _ou_market(market: str):
    """Returns (direction, line) — siehe form_trend._ou_market."""
    m = (market or "").lower()
    is_over = "über" in m or "uber" in m or "over" in m
    is_under = "unter" in m or "under" in m
    if not (is_over or is_under): return (None, None)
    if "ecken" in m or "corner" in m: return (None, None)
    line = 2.5
    if "1.5" in m or "1,5" in m: line = 1.5
    elif "3.5" in m or "3,5" in m: line = 3.5
    return (+1 if is_over else -1, line)


def _btts_market(market: str):
    m = (market or "").lower()
    if not ("beide" in m or "btts" in m): return None
    return -1 if ("nein" in m or "no" in m) else +1


class H2HPatternSignal(Signal):
    """
    H2H Win-Rate-basiertes Signal.

    Context erwartet:
      h2h: { games, homeWins, draws, awayWins }
    """

    def __init__(self):
        self._t = _load_thresholds()

    def name(self) -> str:
        return "h2h_pattern"

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        h2h = context.get("h2h") or {}
        games = h2h.get("games", 0)
        if games < self._t["min_h2h_games"]:
            return None
        market = pick.get("market", "")

        # Dampening für kleine Stichproben — auch für O/U+BTTS
        small_sample = games < self._t["small_sample_threshold"]
        small_factor = self._t["small_sample_dampening"] if small_sample else 1.0

        # ── 1. 1X2 / DC / DNB / AH ────────────────────────────────────
        side = _pick_side(market)
        if side != 0:
            home_wins = h2h.get("homeWins", 0)
            draws     = h2h.get("draws", 0)
            away_wins = h2h.get("awayWins", 0)
            if side == +1:
                picked_rate = (home_wins + 0.5 * draws) / games
            else:
                picked_rate = (away_wins + 0.5 * draws) / games
            score = (picked_rate - 0.5) * self._t["score_scale_pp"] * small_factor
            if abs(score) < self._t["min_signal_pp"]:
                return None
            confidence = min(0.85, 0.35 + 0.05 * min(games, 10))
            oc_label = "Heim" if side == +1 else "Auswärts"
            ev = (f"⚔️ Direkte Duelle ({games}): {home_wins} Heimsiege, {draws} Remis, "
                  f"{away_wins} Auswärtssiege — {oc_label} holt davon {picked_rate*100:.0f}%.")
            return SignalResult(
                score=round(score, 2), confidence=round(confidence, 2), evidence=ev,
                metadata={"games": games, "home_wins": home_wins, "draws": draws,
                          "away_wins": away_wins, "picked_rate": round(picked_rate, 3),
                          "pick_side": "home" if side == 1 else "away"},
            )

        # ── 2. O/U (NEU 09.06.2026) — h2h.over25Rate + avgGoals ───────
        ou_dir, ou_line = _ou_market(market)
        if ou_dir is not None:
            avg_goals = h2h.get("avgGoals")
            over25_rate = h2h.get("over25Rate")
            if avg_goals is None and over25_rate is None:
                return None
            # Wenn avgGoals da: vergleiche gegen die Linie
            # Wenn nur over25Rate: bewerte nur O/U 2.5 sinnvoll
            score = 0.0
            ev_parts = []
            if avg_goals is not None:
                diff_to_line = avg_goals - ou_line
                signed_diff = diff_to_line * ou_dir
                score += signed_diff * (self._t["score_scale_pp"] / 2) * small_factor
                ev_parts.append(f"im Schnitt {avg_goals:.1f} Tore (Linie {ou_line})")
            if over25_rate is not None and ou_line == 2.5:
                # Direktes Maß: Rate über 2.5
                if ou_dir == +1:   # Über-Pick
                    score += (over25_rate - 0.5) * self._t["score_scale_pp"] * small_factor
                else:              # Unter-Pick
                    score += (0.5 - over25_rate) * self._t["score_scale_pp"] * small_factor
                ev_parts.append(f"in {over25_rate*100:.0f}% fielen über 2.5 Tore")
            if abs(score) < self._t["min_signal_pp"]:
                return None
            confidence = min(0.75, 0.35 + 0.05 * min(games, 10))
            side_str = "Über" if ou_dir == +1 else "Unter"
            # 🔴 04.09.2026 (Lucas-Cards-Check). Der Schluss-Satz kam aus der PICK-Richtung, nicht
            # aus dem Ergebnis. Auf der Venezia-Card stand deshalb woertlich:
            #
            #     „im Schnitt 1.2 Tore (Linie 2.5) · in 25% fielen ueber 2.5 Tore
            #      → spricht fuer Ueber 2.5."   —  daneben der Wert -3,5pp
            #
            # Die Zahlen waren richtig, der Satz sagte das Gegenteil. Wer nur die Begruendung
            # liest — und dafuer ist sie da — bekam ein Argument FUER den Pick, wo das Signal
            # dagegen sprach. Die Richtung kommt jetzt aus dem VORZEICHEN.
            richtung = "spricht für" if score > 0 else "spricht gegen"
            ev = (f"⚔️ Aus den letzten {games} Duellen: " + " · ".join(ev_parts)
                  + f" → {richtung} {side_str} {ou_line}.")
            return SignalResult(
                score=round(score, 2), confidence=round(confidence, 2), evidence=ev,
                metadata={"games": games, "h2h_avg_goals": avg_goals,
                          "h2h_over25_rate": over25_rate, "pick_side": f"{side_str} {ou_line}"},
            )

        # ── 3. BTTS (NEU 09.06.2026) — h2h.bttsRate ───────────────────
        btts_dir = _btts_market(market)
        if btts_dir is not None:
            btts_rate = h2h.get("bttsRate")
            if btts_rate is None:
                return None
            diff_from_neutral = btts_rate - 0.5
            signed_diff = diff_from_neutral * btts_dir
            if abs(signed_diff) < 0.08:
                return None
            score = signed_diff * self._t["score_scale_pp"] * 2 * small_factor
            if abs(score) < self._t["min_signal_pp"]:
                return None
            confidence = min(0.70, 0.30 + 0.05 * min(games, 10))
            side_str = "Ja" if btts_dir == +1 else "Nein"
            # Dieselbe Korrektur: „passt zu" galt auch dort, wo das Signal dagegen lief.
            passung = "passt zu" if score > 0 else "spricht gegen"
            ev = (f"⚔️ In den {games} direkten Duellen trafen beide zu {btts_rate*100:.0f}% "
                  f"— {passung} „Beide treffen {side_str}\".")
            return SignalResult(
                score=round(score, 2), confidence=round(confidence, 2), evidence=ev,
                metadata={"games": games, "h2h_btts_rate": btts_rate, "pick_side": f"BTTS-{side_str}"},
            )

        return None
