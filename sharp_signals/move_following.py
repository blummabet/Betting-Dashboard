"""
sharp_signals/move_following.py — Move-Following + Zustands-Bestaetigung (25.07.2026, Lucas)

Kalibriert auf 7154 Top-5-Spielen mit historischen Pinnacle-Closing-Odds
(backtest_move_following.py + tests). Kernbefund (out-of-sample, idealisierter Opening-
Einstieg = OBERGRENZE): dem Pinnacle-Move zu folgen traegt Edge, aber STARK abhaengig von
der Move-GROESSE — und bei schwachen Moves nur, wenn der Team-Zustand (xG-Proxy + Form) den
Move stuetzt:
  · Move >=5pp → starker Edge, Zustand egal   (OOS +29,9%)
  · 3-5pp      → moderat
  · <3pp       → NUR wenn Zustand BESTAETIGT; widerspricht der Zustand → Warnung (OOS -19%)

CONVICTION-MODIFIKATOR, kein Origin-Signal: der Move ist ohnehin der Steam-Trigger, dieses
Signal bewertet WIE SEHR man ihm glauben soll. sharp_money-Familie (Anti-Korr gegen
opener_move/lead_lag verhindert Doppelzaehlung desselben Moves). Nur `liga_default` (Top-5) —
dort historisch validiert; fuer WM/MLS in disabled_signals bis eigene Historie da ist.

Live-Move = Opening→juengster Pinnacle-Snap (Proxy fuers Closing, das pre-match noch fehlt).
Zustand nur fuer 1X2/DC/DNB/AH (home/away); O/U nur nach Move-Groesse (kein sauberer Zustand).
"""
from __future__ import annotations
from typing import Optional
from sharp_signals.base import Signal, SignalResult, market_side


DEFAULT_THRESHOLDS = {
    "gate_pp":              2.0,   # darunter kein bewertbarer Move
    "mid_pp":               3.0,   # Grenze schwach/mittel
    "strong_pp":            5.0,   # ab hier starker Move (Zustand egal)
    "max_signal_pp":        2.0,   # Modifikator, klein gedeckelt
    "score_strong":         2.0,
    "score_mid":            1.2,
    "score_weak_confirm":   0.6,
    "score_weak_contradict": -1.2,  # schwacher Move gegen den Zustand = Warnung
    "form_w":               0.15,  # Gewicht Form-Diff relativ zur xG-Netto-Diff
    "min_state_games":      3,     # darunter Zustand undefiniert
}


def _load_thresholds() -> dict:
    try:
        import json, os
        from pathlib import Path
        raw = json.loads((Path(__file__).parent.parent / "cocobet_config.json")
                         .read_text(encoding="utf-8"))
        active = os.environ.get("COCOBET_PROFILE") or raw["profiles"].get("active", "wm2026")
        cfg = raw["profiles"].get(active, {}).get("move_following") or {}
        return {**DEFAULT_THRESHOLDS, **cfg}
    except Exception:
        return DEFAULT_THRESHOLDS


def _imp(o):
    return (1.0 / o) if (isinstance(o, (int, float)) and o > 1.0) else None


def _parse_ts(ts):
    if not ts:
        return None
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except Exception:
        return None


def _devig_1x2(s, key):
    a, b, c = _imp(s.get("hw")), _imp(s.get("dr")), _imp(s.get("aw"))
    if None in (a, b, c):
        return None
    tot = a + b + c
    return {"home": a / tot, "away": c / tot}.get(key)


def _devig_ou(s, key):
    a, b = _imp(s.get("o25")), _imp(s.get("u25"))
    if None in (a, b):
        return None
    tot = a + b
    return {"over": a / tot, "under": b / tot}.get(key)


def _pinnacle_move_pp(context: dict, side: str):
    """Opening→juengster Pinnacle-Snap: Wkt-Zunahme der Pick-Seite in pp. None wenn <2 Snaps."""
    hist = context.get("odds_history") or []
    pinn = [s for s in hist if isinstance(s, dict) and s.get("bk") == "pinnacle" and _parse_ts(s.get("ts"))]
    pinn.sort(key=lambda s: s["ts"])
    if len(pinn) < 2:
        return None
    implied = _devig_1x2 if side in ("home", "away") else _devig_ou
    p_open = implied(pinn[0], side)
    p_now = implied(pinn[-1], side)
    if p_open is None or p_now is None:
        return None
    return (p_now - p_open) * 100.0


class MoveFollowingSignal(Signal):
    """Move-Groessen-gestaffeltes Confirm mit Zustands-Gate auf schwache Moves."""

    def __init__(self):
        self._t = _load_thresholds()

    def name(self) -> str:
        return "move_following"

    def _team_strength(self, tid, context):
        """xG-Proxy-Netto (+ Form) eines Teams, leakage-frei aus der Saison-Historie. None wenn
        zu duenn. xgSim = kalibrierter Schuss-Proxy (immer da), Fallback Tor-Form."""
        if not tid:
            return None
        xg = (context.get("xg_stats") or {}).get(tid) or {}
        form = (context.get("form") or {}).get(tid) or {}
        mg = self._t["min_state_games"]
        xf, xa = xg.get("xgSimForAvg"), xg.get("xgSimAgainstAvg")
        if xf is not None and xa is not None and (xg.get("games", 0) or 0) >= mg:
            net = xf - xa
        else:
            af, ac = form.get("avgScored"), form.get("avgConceded")
            if af is None or ac is None or (form.get("games", 0) or 0) < mg:
                return None
            net = af - ac
        fpts = 0.0
        last5 = form.get("last5")
        if isinstance(last5, list) and last5:
            fpts = sum(3 if r == "W" else 1 if r == "D" else 0 for r in last5) / len(last5)
        return net + self._t["form_w"] * fpts

    def _state_edge(self, side, context):
        """Zustands-Vorteil der Pick-Seite (nur home/away). >0 stuetzt, <0 widerspricht, None unklar."""
        if side not in ("home", "away"):
            return None
        sh = self._team_strength(context.get("home_id"), context)
        sa = self._team_strength(context.get("away_id"), context)
        if sh is None or sa is None:
            return None
        return (sh - sa) if side == "home" else (sa - sh)

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        side = market_side(pick.get("market", ""))
        if side not in ("home", "away", "over", "under"):
            return None
        move = _pinnacle_move_pp(context, side)
        if move is None or move < self._t["gate_pp"]:
            return None   # kein bewertbarer Move zu unserer Seite

        cap = self._t["max_signal_pp"]
        oc = {"home": "Heim", "away": "Auswärts", "over": "Über", "under": "Unter"}[side]

        # ── starker Move: Zustand egal ──
        if move >= self._t["strong_pp"]:
            score = min(cap, self._t["score_strong"])
            ev = (f"Pinnacle hat {oc} seit der Eröffnung um {move:+.1f}pp verkürzt — ein großer, "
                  f"klarer Sharp-Move. Historisch (Top-5) trägt genau diese Größenklasse den "
                  f"stärksten Edge, unabhängig von der Team-Form.")
            return SignalResult(round(score, 2), 0.7, ev,
                                metadata={"move_pp": round(move, 2), "bucket": "strong",
                                          "outcome": side})

        # ── mittlerer Move (3-5pp): moderat ──
        if move >= self._t["mid_pp"]:
            score = min(cap, self._t["score_mid"])
            ev = (f"Pinnacle zog {oc} um {move:+.1f}pp an — ein solider Sharp-Move mittlerer Größe, "
                  f"der dem schärfsten Geld folgt.")
            return SignalResult(round(score, 2), 0.6, ev,
                                metadata={"move_pp": round(move, 2), "bucket": "mid",
                                          "outcome": side})

        # ── schwacher Move (<3pp): NUR mit Zustands-Bestätigung ──
        edge = self._state_edge(side, context)
        if edge is None:
            return None   # O/U oder Zustand unbekannt → schwacher Move nicht bewertbar
        if edge > 0:
            score = min(cap, self._t["score_weak_confirm"])
            ev = (f"Kleiner {oc}-Move ({move:+.1f}pp) — für sich genommen schwach, aber die "
                  f"Team-Daten (xG/Form) stützen die Richtung, was solche Moves historisch erst "
                  f"tragfähig macht.")
            conf = 0.5
            bucket = "weak_confirm"
        else:
            score = max(-cap, self._t["score_weak_contradict"])
            ev = (f"Vorsicht: nur ein kleiner {oc}-Move ({move:+.1f}pp), und die Team-Daten "
                  f"(xG/Form) sprechen dagegen — genau diese Konstellation verlor historisch "
                  f"deutlich (Top-5).")
            conf = 0.55
            bucket = "weak_contradict"
        return SignalResult(round(score, 2), conf, ev,
                            metadata={"move_pp": round(move, 2), "bucket": bucket,
                                      "state_edge": round(edge, 3), "outcome": side})
