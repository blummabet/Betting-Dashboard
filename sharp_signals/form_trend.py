"""
sharp_signals/form_trend.py — Form-Trend der letzten 5 Spiele

Konzept:
  Die letzten 5 Spiele eines Teams sind ein direkter Form-Indikator. Wir nutzen:
    · avgScored / avgConceded (Tore-Avg über die Form-Spiele)
    · games (wie viele Spiele in der Form-Datei — Sample-Size-Check)

  Wenn Team A klar bessere Form hat als Team B → Pick auf A erhält positiven
  Score. Bei xG-Übergap (Team über-performt vs Tor-Erwartung) → Mean-Reversion
  als negativer Modifier.

  Im Gegensatz zum Modell-internen xG: hier ist Form direkt erlebbar und
  nachvollziehbar für die Card-Story.
"""
from __future__ import annotations
from typing import Optional
from sharp_signals.base import Signal, SignalResult


DEFAULT_THRESHOLDS = {
    "min_games":          3,
    "scoring_score_scale": 3.0,    # pp pro Tor-Diff im avgScored
    "conceding_score_scale": 2.5,  # pp pro Tor-Diff im avgConceded (umgekehrtes Vorzeichen)
    "min_signal_pp":      0.8,
    "max_signal_pp":      6.0,
    # O/U + BTTS Erweiterung (NEU 09.06.2026):
    # Total-Goals-Avg pro Spiel der letzten Form. Vergleich gegen O/U-Linie:
    # avg_total > line + threshold → Über stützt · avg_total < line − threshold → Unter stützt
    "ou_total_threshold": 0.3,     # Tore Diff zur Linie damit Signal feuert
    "ou_score_scale":     4.0,     # pp pro Tor-Diff
    # BTTS: avg bttsRate über beide Teams → > 0.55 stützt BTTS Ja, < 0.40 stützt Nein
    "btts_score_scale":   5.0,     # pp pro Rate-Diff
}


def _load_thresholds() -> dict:
    try:
        import json, os
        from pathlib import Path
        raw = json.loads((Path(__file__).parent.parent / "cocobet_config.json")
                         .read_text(encoding="utf-8"))
        active = os.environ.get("COCOBET_PROFILE") or raw["profiles"].get("active", "wm2026")
        cfg = raw["profiles"].get(active, {}).get("form_trend") or {}
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
    """Erkennt O/U-Markt. Returns (direction, line) oder (None, None).
    direction: +1 = Über (mehr Tore stützen), -1 = Unter (weniger stützen)."""
    m = (market or "").lower()
    is_over = "über" in m or "uber" in m or "over" in m
    is_under = "unter" in m or "under" in m
    if not (is_over or is_under): return (None, None)
    if "ecken" in m or "corner" in m: return (None, None)  # Ecken-Märkte ausklammern
    if "tore" not in m and "goal" not in m and not any(x in m for x in ["1.5","2.5","3.5"]):
        return (None, None)
    line = 2.5  # Default
    if "1.5" in m or "1,5" in m: line = 1.5
    elif "3.5" in m or "3,5" in m: line = 3.5
    return (+1 if is_over else -1, line)


def _btts_market(market: str):
    """Erkennt BTTS-Markt. Returns +1 (Ja) / -1 (Nein) / None."""
    m = (market or "").lower()
    if not ("beide" in m or "btts" in m): return None
    if "nein" in m or "no" in m: return -1
    return +1


class FormTrendSignal(Signal):
    """
    Form-Differenz der letzten ~5 Spiele für 1X2/DNB/AH/DC-Picks.

    Context erwartet:
      home_id, away_id
      form: { teamId: { games, avgScored, avgConceded } }
    """

    def __init__(self):
        self._t = _load_thresholds()

    def name(self) -> str:
        return "form_trend"

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        form = context.get("form") or {}
        home_id, away_id = context.get("home_id"), context.get("away_id")
        if not (home_id and away_id):
            return None

        fh = form.get(home_id) or {}
        fa = form.get(away_id) or {}
        if (fh.get("games", 0) < self._t["min_games"]
                or fa.get("games", 0) < self._t["min_games"]):
            return None

        h_scored = fh.get("avgScored", 0) or 0
        h_conced = fh.get("avgConceded", 0) or 0
        a_scored = fa.get("avgScored", 0) or 0
        a_conced = fa.get("avgConceded", 0) or 0
        market = pick.get("market", "")

        # ── 1. 1X2 / DC / DNB / AH (alte Logik) ─────────────────────────
        side = _pick_side(market)
        if side != 0:
            if side == +1:
                scoring_diff = h_scored - a_scored
                conceding_diff = a_conced - h_conced
            else:
                scoring_diff = a_scored - h_scored
                conceding_diff = h_conced - a_conced

            score = (scoring_diff * self._t["scoring_score_scale"]
                     + conceding_diff * self._t["conceding_score_scale"])
            if abs(score) < self._t["min_signal_pp"]:
                return None
            score = max(-self._t["max_signal_pp"], min(self._t["max_signal_pp"], score))

            confidence = min(0.85,
                0.50 + 0.04 * min(fh.get("games", 0), fa.get("games", 0))
                + 0.05 * (abs(scoring_diff) + abs(conceding_diff))
            )
            ev = (f"📈 Form letzte {min(fh['games'], fa['games'])}: "
                  f"Heim {h_scored:.1f}:{h_conced:.1f} vs "
                  f"Auswärts {a_scored:.1f}:{a_conced:.1f}")
            return SignalResult(
                score=round(score, 2), confidence=round(confidence, 2), evidence=ev,
                metadata={
                    "home_scored": round(h_scored, 2), "home_conceded": round(h_conced, 2),
                    "away_scored": round(a_scored, 2), "away_conceded": round(a_conced, 2),
                    "home_games": fh.get("games"), "away_games": fa.get("games"),
                    "pick_side": "home" if side == 1 else "away",
                },
            )

        # ── 2. O/U-Markt (NEU 09.06.2026) ────────────────────────────────
        ou_dir, ou_line = _ou_market(market)
        if ou_dir is not None:
            # Erwartete Total-Tore aus Form: (h_scored + h_conced + a_scored + a_conced) / 2
            # Das ist der Durchschnitt der Tore pro Spiel beider Teams.
            expected_total = (h_scored + h_conced + a_scored + a_conced) / 2.0
            diff_to_line = expected_total - ou_line
            # Über-Pick: Vorteil wenn diff > 0, Unter-Pick: Vorteil wenn diff < 0
            signed_diff = diff_to_line * ou_dir
            threshold = self._t["ou_total_threshold"]
            if abs(signed_diff) < threshold:
                return None
            score = signed_diff * self._t["ou_score_scale"]
            score = max(-self._t["max_signal_pp"], min(self._t["max_signal_pp"], score))
            if abs(score) < self._t["min_signal_pp"]:
                return None
            confidence = min(0.80, 0.45 + 0.04 * min(fh.get("games", 0), fa.get("games", 0))
                             + 0.08 * abs(signed_diff))
            side_str = "Über" if ou_dir == +1 else "Unter"
            ev = (f"📈 Form-Tor-Schnitt {expected_total:.1f}/Spiel "
                  f"vs Linie {ou_line} → {side_str} {ou_dir*signed_diff:+.1f} Tore Vorteil")
            return SignalResult(
                score=round(score, 2), confidence=round(confidence, 2), evidence=ev,
                metadata={
                    "expected_total": round(expected_total, 2), "ou_line": ou_line,
                    "diff_to_line": round(diff_to_line, 2), "pick_side": f"{side_str} {ou_line}",
                },
            )

        # ── 3. BTTS-Markt (NEU 09.06.2026) ───────────────────────────────
        btts_dir = _btts_market(market)
        if btts_dir is not None:
            # bttsRate Durchschnitt beider Teams. Falls fehlend → Proxy aus avgScored
            # Beide Teams treffen typisch wenn beide >0.9 scored UND <1.6 conceded
            h_btts = fh.get("bttsRate")
            a_btts = fa.get("bttsRate")
            if h_btts is not None and a_btts is not None:
                avg_btts = (h_btts + a_btts) / 2.0
            else:
                # Proxy: beide Teams scored >= 1.0 → ~60% BTTS-Wahrscheinlichkeit
                h_scoring_strength = min(1.0, h_scored / 1.5)
                a_scoring_strength = min(1.0, a_scored / 1.5)
                avg_btts = (h_scoring_strength + a_scoring_strength) / 2.0 * 0.7
            # Neutral = 0.5, jeder Punkt darüber stützt BTTS Ja
            diff_from_neutral = avg_btts - 0.5
            signed_diff = diff_from_neutral * btts_dir
            if abs(signed_diff) < 0.05:
                return None
            score = signed_diff * self._t["btts_score_scale"] * 2  # *2 weil Rate ja 0-1
            score = max(-self._t["max_signal_pp"], min(self._t["max_signal_pp"], score))
            if abs(score) < self._t["min_signal_pp"]:
                return None
            confidence = min(0.75, 0.45 + 0.05 * min(fh.get("games", 0), fa.get("games", 0))
                             + 0.5 * abs(signed_diff))
            side_str = "Ja" if btts_dir == +1 else "Nein"
            ev = (f"📈 BTTS-Schnitt Form {avg_btts*100:.0f}% "
                  f"(Heim {h_scored:.1f}:{h_conced:.1f}, Auswärts {a_scored:.1f}:{a_conced:.1f}) "
                  f"→ Beide treffen {side_str}")
            return SignalResult(
                score=round(score, 2), confidence=round(confidence, 2), evidence=ev,
                metadata={"avg_btts_rate": round(avg_btts, 3), "pick_side": f"BTTS-{side_str}"},
            )

        return None
