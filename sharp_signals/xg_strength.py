"""
sharp_signals/xg_strength.py — Expected-Goals als Team-Stärke-Modifier

Konzept:
  Understat liefert pro Team xgForAvg (erwartete eigene Tore) und
  xgAgainstAvg (erwartete Gegentore). Das ist schärfer als reine Tor-Statistik
  weil es Chancen-Qualität misst — nicht Glück/Pech bei Abschlüssen.

  xG-Diff eines Teams = xgFor - xgAgainst
  → hohe Diff = dominant, niedrige = schwach

  Wenn Heim deutlich höhere xG-Diff hat als Auswärts → positiver Score auf
  Heim-Pick. Verfügbar primär für UEFA-Teams (Understat-Coverage).

Mean-Reversion-Notiz:
  Wenn avgScored > xgForAvg → Team über-performt (mehr Tore als Modell erwartet)
  → mean reversion-Risiko. Aktuell nicht eingebaut, könnte als Sub-Signal kommen.
"""
from __future__ import annotations
from typing import Optional
from sharp_signals.base import Signal, SignalResult


DEFAULT_THRESHOLDS = {
    "min_games":          5,    # mind. 5 xG-Spiele pro Team (echtes xG)
    "min_games_proxy":    5,    # für Form-Proxy
    "score_scale_pp":     2.0,  # pp pro xG-Diff-pp Differenz
    "score_scale_proxy":  1.2,  # Form-Proxy wird gedämpft (kein echtes xG)
    "min_signal_pp":      0.8,
    "max_signal_pp":      6.0,
    "proxy_confidence_max": 0.65,
    # O/U + BTTS Erweiterung (NEU 09.06.2026):
    # Expected total = h_xgFor + a_xgFor + (defensive Korrektur). Direkter Vergleich zur Linie.
    "ou_threshold":       0.35,  # xG-Diff zur Linie damit Signal feuert
    "ou_score_scale":     3.5,
    "btts_score_scale":   4.5,
    # Dünne-xG-Abdeckung-Dämpfer (15.06.2026, Lucas — ESP-CPV 0:0): hat ein Team
    # GAR KEINE echten xG-Spiele (nur Schuss-/Form-Proxy, z.B. Kap Verde, viele
    # CONMEBOL/AFC/Afrika-Teams), ist die Tor-Markt-Schätzung messbar unsicherer.
    # SANFT: nur die Confidence runter (Richtung/Score bleiben) → kleinerer
    # gewichteter Beitrag + sichtbar in der Evidence. Kein Überreagieren.
    "thin_xg_confidence_mult": 0.80,
}


def _load_thresholds() -> dict:
    try:
        import json, os
        from pathlib import Path
        raw = json.loads((Path(__file__).parent.parent / "cocobet_config.json")
                         .read_text(encoding="utf-8"))
        active = os.environ.get("COCOBET_PROFILE") or raw["profiles"].get("active", "wm2026")
        cfg = raw["profiles"].get(active, {}).get("xg_strength") or {}
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


class XGStrengthSignal(Signal):
    """
    xG-basierter Team-Stärke-Vergleich.

    Context erwartet:
      home_id, away_id
      xg_stats: { teamId: { xgForAvg, xgAgainstAvg, games } }
    """

    def __init__(self):
        self._t = _load_thresholds()

    def name(self) -> str:
        return "xg_strength"

    @staticmethod
    def _real_xg_games(entry: dict) -> int:
        """Echte xG-Spiele eines Teams (nicht Schuss-/Form-Proxy). 0 = gar keine
        echte xG-Abdeckung (Kap Verde & viele CONMEBOL/AFC/Afrika-Teams).

        FIX 29.06.2026 (Lucas): Der Rich-Aggregator (fetch_wm_nt_xg) schreibt echtes xG nach
        `xgForAvg` (= None wenn keins, separat vom xGsim), setzt aber WEDER `xgGames` NOCH
        `source in (understat,apif_real)`. Die alte Prüfung las das als 0 → thin_cov war auf
        JEDEM Spiel True → xg_strength dauerhaft gedämpft + „dünne Abdeckung" fälschlich gelabelt.
        Jetzt: echtes xG = `xgForAvg` vorhanden (egal welcher source-Tag)."""
        # shot_proxy: generate_wm_picks setzt bei FEHLENDEM echtem xG xgForAvg = xgSimForAvg und
        # taggt source="shot_proxy" → das ist KEIN echtes xG (sonst zählten wir Proxy als echt).
        if entry.get("source") == "shot_proxy":
            return 0
        g = entry.get("xgGames")
        if g is not None:
            return g
        if entry.get("xgForAvg") is not None:   # echtes API-xG steckt in xgForAvg (None = nur Proxy)
            return entry.get("games", 0) or 0
        return 0

    def _resolve_xg(self, context: dict):
        """Resolve xG-Werte oder Form-Proxy. Returns (h_for, h_ag, a_for, a_ag,
        h_games, a_games, is_proxy, thin_cov) oder None wenn unvollständig.
        thin_cov = mind. ein Team hat 0 echte xG-Spiele (nur Proxy)."""
        home_id, away_id = context.get("home_id"), context.get("away_id")
        if not (home_id and away_id): return None
        xg = context.get("xg_stats") or {}
        xh = xg.get(home_id) or {}
        xa = xg.get(away_id) or {}
        thin_cov = min(self._real_xg_games(xh), self._real_xg_games(xa)) == 0
        h_for, h_ag = xh.get("xgForAvg"), xh.get("xgAgainstAvg")
        a_for, a_ag = xa.get("xgForAvg"), xa.get("xgAgainstAvg")
        h_games = xh.get("games", 0) or 0
        a_games = xa.get("games", 0) or 0
        is_proxy = False
        if (None in (h_for, h_ag, a_for, a_ag) or
                h_games < self._t["min_games"] or a_games < self._t["min_games"]):
            form = context.get("form") or {}
            fh, fa = form.get(home_id) or {}, form.get(away_id) or {}
            min_proxy = self._t["min_games_proxy"]
            if (fh.get("games", 0) < min_proxy or fa.get("games", 0) < min_proxy):
                return None
            for v in (fh.get("avgScored"), fh.get("avgConceded"),
                      fa.get("avgScored"), fa.get("avgConceded")):
                if v is None: return None
            h_for, h_ag = fh["avgScored"], fh["avgConceded"]
            a_for, a_ag = fa["avgScored"], fa["avgConceded"]
            h_games, a_games = fh["games"], fa["games"]
            is_proxy = True
        return (h_for, h_ag, a_for, a_ag, h_games, a_games, is_proxy, thin_cov)

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        resolved = self._resolve_xg(context)
        if not resolved: return None
        h_for, h_ag, a_for, a_ag, h_games, a_games, is_proxy, thin_cov = resolved
        market = pick.get("market", "")
        label = "Form-xG (Proxy)" if is_proxy else "xG-Stärke"
        n_min = min(h_games, a_games)
        # Sanfter Dämpfer (Confidence) wenn ein Team gar kein echtes xG hat.
        _thin_mult = self._t.get("thin_xg_confidence_mult", 1.0) if thin_cov else 1.0
        _thin_ev = " · dünne xG-Abdeckung" if thin_cov else ""

        # ── 1. 1X2 / DC / DNB / AH (Outcome-Differenz) ───────────────────
        side = _pick_side(market)
        if side != 0:
            home_diff = h_for - h_ag
            away_diff = a_for - a_ag
            relative = home_diff - away_diff
            scale = self._t["score_scale_proxy"] if is_proxy else self._t["score_scale_pp"]
            score = side * relative * scale
            if abs(score) < self._t["min_signal_pp"]:
                return None
            score = max(-self._t["max_signal_pp"], min(self._t["max_signal_pp"], score))
            confidence = min(0.90, 0.55 + 0.03 * n_min + 0.04 * abs(relative))
            if is_proxy: confidence = min(self._t["proxy_confidence_max"], confidence)
            confidence *= _thin_mult
            ev = (f"⚡ {label}: Heim erspielt sich {h_for:.2f} Tor-Chancen (xG) und gibt {h_ag:.2f} "
                  f"her, Auswärts {a_for:.2f} und {a_ag:.2f} — macht {relative:+.2f} Unterschied.{_thin_ev}")
            return SignalResult(
                score=round(score, 2), confidence=round(confidence, 2), evidence=ev,
                metadata={"home_xg_for": round(h_for, 2), "home_xg_against": round(h_ag, 2),
                          "away_xg_for": round(a_for, 2), "away_xg_against": round(a_ag, 2),
                          "relative_diff": round(relative, 2), "is_proxy": is_proxy,
                          "pick_side": "home" if side == 1 else "away"},
            )

        # ── 2. O/U (NEU 09.06.2026) — Expected total ─────────────────────
        ou_dir, ou_line = _ou_market(market)
        if ou_dir is not None:
            # Erwartete Gesamt-Tore = (heim_xgFor + heim_xgAg + ausw_xgFor + ausw_xgAg) / 2
            # heuristisch — entspricht avg goals/match wenn beide Teams gegen Avg-Stärke spielen
            expected_total = (h_for + h_ag + a_for + a_ag) / 2.0
            diff_to_line = expected_total - ou_line
            signed_diff = diff_to_line * ou_dir
            if abs(signed_diff) < self._t["ou_threshold"]:
                return None
            scale = self._t["ou_score_scale"]
            if is_proxy: scale *= 0.7
            score = signed_diff * scale
            score = max(-self._t["max_signal_pp"], min(self._t["max_signal_pp"], score))
            if abs(score) < self._t["min_signal_pp"]:
                return None
            confidence = min(0.80, 0.45 + 0.03 * n_min + 0.05 * abs(signed_diff))
            if is_proxy: confidence = min(self._t["proxy_confidence_max"], confidence)
            confidence *= _thin_mult
            side_str = "Über" if ou_dir == +1 else "Unter"
            ev = (f"⚡ Die xG-Werte deuten auf ~{expected_total:.2f} Tore pro Spiel hin, die Linie "
                  f"steht bei {ou_line} — Tendenz {side_str} ({ou_dir*signed_diff:+.2f}).{_thin_ev}")
            return SignalResult(
                score=round(score, 2), confidence=round(confidence, 2), evidence=ev,
                metadata={"expected_total": round(expected_total, 2), "ou_line": ou_line,
                          "diff_to_line": round(diff_to_line, 2), "is_proxy": is_proxy,
                          "pick_side": f"{side_str} {ou_line}"},
            )

        # ── 3. BTTS (NEU 09.06.2026) — beide Teams scoring strong? ──────
        btts_dir = _btts_market(market)
        if btts_dir is not None:
            # Beide xgFor hoch → beide Teams treffen wahrscheinlich
            # h_score_potential = heim_xgFor relativ zu ausw_xgAg → hoch wenn heim_xgFor > ausw_xgAg
            h_score_strength = h_for / max(a_ag, 0.5)  # >1 = heim wahrscheinlich trifft
            a_score_strength = a_for / max(h_ag, 0.5)
            # BTTS wahrscheinlich wenn beide >= 0.85
            min_strength = min(h_score_strength, a_score_strength)
            # Normiere: 0.5 = neutral, 1.5+ = klar BTTS
            score = (min_strength - 1.0) * self._t["btts_score_scale"] * btts_dir
            scale = self._t["btts_score_scale"]
            if is_proxy: scale *= 0.7
            score = (min_strength - 1.0) * scale * btts_dir
            score = max(-self._t["max_signal_pp"], min(self._t["max_signal_pp"], score))
            if abs(score) < self._t["min_signal_pp"]:
                return None
            confidence = min(0.75, 0.40 + 0.03 * n_min)
            if is_proxy: confidence = min(self._t["proxy_confidence_max"], confidence)
            confidence *= _thin_mult
            side_str = "Ja" if btts_dir == +1 else "Nein"
            ev = (f"⚡ {label}: Heims Angriff ({h_for:.2f}) trifft auf Auswärts' Abwehr ({a_ag:.2f}), "
                  f"umgekehrt {a_for:.2f} gegen {h_ag:.2f} — spricht für „Beide treffen {side_str}\".{_thin_ev}")
            return SignalResult(
                score=round(score, 2), confidence=round(confidence, 2), evidence=ev,
                metadata={"h_score_strength": round(h_score_strength, 2),
                          "a_score_strength": round(a_score_strength, 2),
                          "is_proxy": is_proxy, "pick_side": f"BTTS-{side_str}"},
            )

        return None
