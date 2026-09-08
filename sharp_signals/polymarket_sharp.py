"""
sharp_signals/polymarket_sharp.py — Polymarket als zweiter Sharp-Anker

Konzept:
  Polymarket ist ein dezentraler Prognose-Markt mit hohem Crypto-Volumen.
  Im Gegensatz zu Soft-Books (Public-Bias) sind Polymarket-Trader oft selbst
  scharf — manche Crypto-Funds machen dort 6-stellige Positions.

  Wenn Polymarket UND Pinnacle in derselben Richtung zeigen → 2 Sharp-Quellen
  bestätigen sich → höhere Confidence für den Pick.
  Wenn Polymarket gegen Pinnacle steht → eine Quelle liegt daneben →
  konservatives Signal (kein BET).

Volume-Gating: nur signifikant wenn polymarket_vol ≥ MIN_VOL_USDC.
Pre-Tournament-Märkte haben oft niedriges Volume → Signal überspringt sie.
"""
from __future__ import annotations
from typing import Optional
from sharp_signals.base import Signal, SignalResult, poly_volumen


DEFAULT_THRESHOLDS = {
    "min_volume_usdc":   5000,
    "min_diff_pp":       2.5,   # Polymarket vs Pinnacle implied
    "score_scale_pp":    0.6,   # pp pro pp Diff
    "max_signal_pp":     4.0,
}


def _load_thresholds() -> dict:
    try:
        import json, os
        from pathlib import Path
        raw = json.loads((Path(__file__).parent.parent / "cocobet_config.json")
                         .read_text(encoding="utf-8"))
        active = os.environ.get("COCOBET_PROFILE") or raw["profiles"].get("active", "wm2026")
        cfg = raw["profiles"].get(active, {}).get("polymarket_sharp") or {}
        return {**DEFAULT_THRESHOLDS, **cfg}
    except Exception:
        return DEFAULT_THRESHOLDS


def _devig_1x2(hw, dr, aw):
    if not (hw and dr and aw):
        return (None, None, None)
    p_hw, p_dr, p_aw = 1.0/hw, 1.0/dr, 1.0/aw
    s = p_hw + p_dr + p_aw
    if s <= 0:
        return (None, None, None)
    return (p_hw/s, p_dr/s, p_aw/s)


# ── Welche Ausgaenge dieses Signal lesen kann (07.09.2026) ──────────────────────────────────
# Ein Ausgang ist hier eine SUMME von 1X2-Beinen. Fuer Heimsieg ist das die Summe aus einem
# Bein, fuer „Doppelte Chance — 1X" die aus zweien. Beides rechnet sich aus denselben drei
# Poly-Preisen, die schon dastehen; es fehlte nur die Zuordnung.
#
# Warum das mehr als Kosmetik ist, gemessen am 07.09. ueber die 300 Liga-Picks:
#
#     Heimsieg + Auswaertssieg      80 Picks  → 22 mit Pinnacle → 15 mit Poly → **0 ueber $5k**
#     Doppelte Chance (1X / X2)     95 Picks  ← die groesste Marktgruppe ueberhaupt
#
# Und die Spiele mit echtem Poly-Geld ($404.746, $345.895, $186.831, $86.761) tragen
# ausschliesslich Doppelte-Chance- und Ueber/Unter-Picks. Das Signal schaute also genau dort
# NICHT hin, wo das Geld lag — nicht wegen eines Fehlers in der Rechnung, sondern weil eine
# Marktbezeichnung fehlte.
#
# DNB bleibt bewusst ein Ein-Bein-Ausgang: „Draw no bet" ist keine Summe, sondern eine
# Rueckzahlung beim Remis. Es hier als hw+dr zu fuehren waere eine andere Wette.
_AUSGANG_BEINE = {
    "hw":  ("hw",),
    "dr":  ("dr",),
    "aw":  ("aw",),
    "1x":  ("hw", "dr"),
    "x2":  ("dr", "aw"),
    "12":  ("hw", "aw"),
}

_LABEL = {"hw": "Heim", "dr": "X", "aw": "Auswärts",
          "1x": "1X", "x2": "X2", "12": "12"}


def _outcome_key_from_market(market: str) -> Optional[str]:
    m = (market or "").lower()
    # Doppelte Chance zuerst: „Doppelte Chance — 1X" enthaelt kein „heimsieg", aber die
    # Reihenfolge macht die Absicht sichtbar.
    if "doppelte chance" in m or "double chance" in m:
        if "1x" in m: return "1x"
        if "x2" in m: return "x2"
        if "12" in m: return "12"
        return None
    if "heimsieg" in m: return "hw"
    if "auswärtssieg" in m or "auswartssieg" in m: return "aw"
    if "unentsch" in m: return "dr"
    if "dnb" in m and ("heim" in m or "home" in m): return "hw"
    if "dnb" in m and ("ausw" in m or "away" in m): return "aw"
    return None


class PolymarketSharpSignal(Signal):
    """
    Polymarket-implied vs Pinnacle-implied für 1X2-/DNB-Picks.

    Context erwartet:
      odds_snapshot: { hw, dr, aw }  # Pinnacle
      poly_snapshot: { poly_hw, poly_dr, poly_aw, poly_vol }
    """

    def __init__(self):
        self._t = _load_thresholds()

    def name(self) -> str:
        return "polymarket_sharp"

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        outcome = _outcome_key_from_market(pick.get("market", ""))
        if not outcome:
            return None

        # Pinnacle-Snap (devigt) als Anker
        snap = context.get("odds_snapshot") or {}
        pinn_p = _devig_1x2(snap.get("hw"), snap.get("dr"), snap.get("aw"))
        if pinn_p[0] is None:
            return None

        # Polymarket implied probs (rohe Markt-Preise, schon prob-like)
        poly = context.get("poly_snapshot") or {}
        p_hw, p_dr, p_aw = poly.get("poly_hw"), poly.get("poly_dr"), poly.get("poly_aw")
        # 06.09.2026: liest jetzt `vol` UND `poly_vol` (s. base.poly_volumen). Vorher stand hier
        # `poly.get("poly_vol", 0)` — ein Feld, das die Produktion nie schreibt. Dieses Signal
        # hat deswegen nie gefeuert.
        vol = poly_volumen(poly)
        if None in (p_hw, p_dr, p_aw):
            return None
        if vol is None or vol < self._t["min_volume_usdc"]:
            return None  # kein bekanntes Volumen oder zu wenig Geld dahinter

        # Normalisieren (Polymarket-Implied sum ≈ 1.0 - 1.05)
        s = p_hw + p_dr + p_aw
        if s <= 0:
            return None
        poly_p = (p_hw/s, p_dr/s, p_aw/s)

        # Summe der Beine — bei 1X2 ein Bein, bei Doppelter Chance zwei. Beide Seiten
        # werden GLEICH summiert, sonst vergliche man zwei verschiedene Wetten.
        idx = {"hw": 0, "dr": 1, "aw": 2}
        beine = _AUSGANG_BEINE[outcome]
        poly_w = sum(poly_p[idx[b]] for b in beine)
        pinn_w = sum(pinn_p[idx[b]] for b in beine)
        diff_pp = (poly_w - pinn_w) * 100.0

        if abs(diff_pp) < self._t["min_diff_pp"]:
            return None

        # Positive Diff = Polymarket sieht Outcome wahrscheinlicher → bestätigt Pick
        # Negative Diff = Polymarket sieht weniger wahrscheinlich → warnt
        score = diff_pp * self._t["score_scale_pp"]
        score = max(-self._t["max_signal_pp"], min(self._t["max_signal_pp"], score))

        # Confidence steigt mit Volume + Diff-Größe
        vol_factor = min(1.0, vol / 50000.0)
        confidence = min(0.90, 0.50 + 0.15 * vol_factor + abs(diff_pp) * 0.03)

        oc_label = _LABEL[outcome]
        direction = "bestätigt" if diff_pp > 0 else "widerspricht"
        ev = (f"🟣 Polymarket ({oc_label}) {direction} Pinnacle: "
              f"Poly {poly_w*100:.0f}% vs Pinn {pinn_w*100:.0f}% "
              f"· Vol ${vol/1000:.0f}k")

        return SignalResult(
            score=round(score, 2),
            confidence=round(confidence, 2),
            evidence=ev,
            metadata={
                "outcome":       outcome,
                "beine":         list(beine),
                "diff_pp":       round(diff_pp, 2),
                "poly_implied":  round(poly_w, 4),
                "pinn_implied":  round(pinn_w, 4),
                "volume_usdc":   vol,
            },
        )
