"""
sharp_signals/chance_creation.py — Chancen-Kreation als Stärke-Modifier

Quelle: fetch_wm_nt_xg.py aggregiert pro Team aus /fixtures/players + /fixtures/
statistics:
  · keyPassesForAvg   — Ø Schlüsselpässe/Spiel (chancen-kreierende Pässe)
  · shotsInsideForAvg — Ø Schüsse im 16er/Spiel (hochwertige Abschlüsse)

Beides ist orthogonal zum reinen xG-Ergebnis: ein Team kann viele Chancen
kreieren ohne sie zu nutzen (→ positive Regression erwartbar) oder umgekehrt.
Verfügbar auch für Teams OHNE echtes API-xG (Schlüsselpässe/Schüsse sind in
Freundschaftsspielen gefüllt) → schließt dieselbe Coverage-Lücke wie xGsim.

Score-Logik (pp gegen Pinnacle-implied):
  · 1X2/DC/DNB/AH  → side · (heim_threat − ausw_threat) · scale
  · O/U            → (heim_threat + ausw_threat − liga_avg) · dir · scale
  threat = keyPasses + w·shotsInside  (kombinierter Angriffs-Druck)
"""
from __future__ import annotations
import os
import json
from pathlib import Path
from typing import Optional
from sharp_signals.base import Signal, SignalResult

BASE = Path(__file__).resolve().parent.parent

DEFAULT_T = {
    "min_games":          3,
    "shots_inside_weight": 0.4,   # shotsInside fließt gedämpft neben keyPasses ein
    "result_scale":       0.45,   # pp pro threat-Differenz-Einheit
    "ou_scale":           0.40,
    "ou_baseline":        22.0,   # Liga-Ø threat-Summe (key+0.4·inside beider Teams)
    "min_signal_pp":      0.8,
    "max_signal_pp":      6.0,
}


def _load_t() -> dict:
    try:
        raw = json.loads((BASE / "cocobet_config.json").read_text(encoding="utf-8"))
        active = os.environ.get("COCOBET_PROFILE") or raw["profiles"].get("active", "wm2026")
        cfg = (raw["profiles"].get(active, {}).get("chance_creation")) or {}
        return {**DEFAULT_T, **cfg}
    except Exception:
        return dict(DEFAULT_T)


def _pick_side(market: str) -> int:
    """+1 = Pick auf Heim, -1 = auf Auswärts, 0 = kein Outcome-Markt."""
    m = (market or "").lower()
    if "doppelte chance" in m or "double chance" in m:
        if "1x" in m or "— 1" in m: return +1
        if "x2" in m or "— 2" in m: return -1
    if "heim" in m or "home" in m: return +1
    if "auswärt" in m or "auswarts" in m or "away" in m: return -1
    return 0


def _ou_market(market: str):
    """(dir, line) für O/U-Märkte: dir +1=Over, -1=Under. Sonst (None, None)."""
    m = (market or "").lower()
    is_ou = ("über" in m or "uber" in m or "over" in m or "unter" in m or "under" in m)
    if not is_ou:
        return (None, None)
    direction = +1 if ("über" in m or "uber" in m or "over" in m) else -1
    line = 2.5
    for tok in m.replace(",", ".").split():
        try:
            line = float(tok); break
        except ValueError:
            continue
    return (direction, line)


class ChanceCreationSignal(Signal):
    def __init__(self):
        self._t = _load_t()

    def name(self) -> str:
        return "chance_creation"

    def _threat(self, rec: dict):
        kp = rec.get("keyPassesForAvg")
        si = rec.get("shotsInsideForAvg")
        if kp is None and si is None:
            return None
        return (kp or 0.0) + self._t["shots_inside_weight"] * (si or 0.0)

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        home_id, away_id = context.get("home_id"), context.get("away_id")
        if not (home_id and away_id):
            return None
        xg = context.get("xg_stats") or {}
        rh, ra = xg.get(home_id) or {}, xg.get(away_id) or {}
        if (rh.get("games", 0) or 0) < self._t["min_games"] or (ra.get("games", 0) or 0) < self._t["min_games"]:
            return None
        th, ta = self._threat(rh), self._threat(ra)
        if th is None or ta is None:
            return None
        market = pick.get("market", "")

        side = _pick_side(market)
        if side != 0:
            relative = th - ta
            score = side * relative * self._t["result_scale"]
            if abs(score) < self._t["min_signal_pp"]:
                return None
            score = max(-self._t["max_signal_pp"], min(self._t["max_signal_pp"], score))
            conf = min(0.80, 0.50 + 0.04 * abs(relative))
            ev = (f"🎨 Chancen-Kreation: Heim {th:.1f} vs Auswärts {ta:.1f} "
                  f"(Schlüsselpässe+Abschlüsse, Δ {relative:+.1f})")
            return SignalResult(round(score, 2), round(conf, 2), ev,
                                {"home_threat": round(th, 2), "away_threat": round(ta, 2),
                                 "relative": round(relative, 2)})

        ou_dir, _line = _ou_market(market)
        if ou_dir is not None:
            total = th + ta
            signed = (total - self._t["ou_baseline"]) * ou_dir
            score = signed * self._t["ou_scale"]
            if abs(score) < self._t["min_signal_pp"]:
                return None
            score = max(-self._t["max_signal_pp"], min(self._t["max_signal_pp"], score))
            conf = min(0.72, 0.42 + 0.02 * abs(total - self._t["ou_baseline"]))
            ev = (f"🎨 Chancen-Volumen: Σ {total:.1f} (Schlüsselpässe+Abschlüsse beider Teams) "
                  f"{'hoch→Over' if ou_dir>0 else 'niedrig→Under'}")
            return SignalResult(round(score, 2), round(conf, 2), ev,
                                {"total_threat": round(total, 2)})
        return None
