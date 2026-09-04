"""
sharp_signals/betfair_money.py — Betfair-Exchange-GELD als Sharp-Signal (29.07.2026, Lucas).

Anders als `multi_book_steam` (nutzt Betfair-QUOTEN als Steam-Anker), bewertet dieses Signal das
tatsächlich gematchte GELD pro Ausgang (aus Betwatch, betfair_prices.json): liegt auf der Pick-Seite
MEHR Geld, als ihr Preis impliziert? „Edge" = Geld-Anteil − fairer Anteil (aus den Betfair-Quoten
de-viggt). Deckt 1X2, Über/Unter 2.5/3.5 und BTTS ab (keine Asian, keine HT).

Zwei Lern-Ebenen:
  · GLOBAL   — das Signalgewicht in signal_weights.json justiert die CLV-Lernschleife (wie jedes Signal).
  · LIGA×MARKT — die confidence wird mit dem Track-Record (betfair_track_record.json) moduliert:
                 guter ROI verstärkt; wo dem Geld-folgen historisch VERLIERT, dreht das Signal um
                 (Geld dort = Fade). Braucht Mindest-Stichprobe (MIN_TR_N), sonst neutral.

Context erwartet:
  betfair_snapshot: der rohe Betwatch-Match-Dict {home, away, league, markets:{name:{runners:[{name,odd,vol}]}}}
                    — von generate_wm_picks per Namens-Matching gesetzt. Fehlt es → None (kein Fehlsignal).
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Optional
from sharp_signals.base import Signal, SignalResult, market_side

_ROOT = Path(__file__).resolve().parent.parent
_TRACK_FILE = _ROOT / "betfair_track_record.json"

MIN_MONEY_EUR = 3000.0    # Markt-Gesamtgeld mind. so hoch, sonst nicht handelbar
MIN_EDGE      = 0.06      # |Geld-Anteil − fairer Anteil| mind. so groß
SCORE_SCALE   = 20.0      # Edge 0.10 → 2.0pp
MAX_SIGNAL_PP = 4.0
# 04.09.2026: Die Schwellen gelten seit dem Betfair-Checkup auf der RENDITE-UNTERGRENZE (roiUg),
# nicht auf dem Punktschaetzer. Ein eigenes n-Gate braucht es damit nicht mehr — die Untergrenze
# existiert erst ab n=30 (freigabe.UG_MIN_N) und ist unterhalb schlicht None. MIN_TR_N ist nur
# noch Anzeige: „ab so vielen Spielen KANN es ein Urteil geben".
MIN_TR_N      = 30        # = freigabe.UG_MIN_N; ab hier kann es ueberhaupt eine Untergrenze geben
TR_FADE_ROI   = -0.10     # ROI-UG ≤ das → dem Geld zu folgen verliert belegt → Signal umdrehen (Fade)
TR_BOOST_ROI  = 0.0       # ROI-UG > das → verstärken (eine Untergrenze ueber null ist der Beleg)


def _tok(market_name: str, runner_name: str, home, away) -> Optional[str]:
    """Betwatch-Runner → Token (H/D/A · OVER/UNDER · YES/NO)."""
    if market_name == "Match Odds":
        if runner_name == home:
            return "H"
        if runner_name == away:
            return "A"
        if runner_name == "The Draw":
            return "D"
        return None
    if market_name in ("Over/Under 2.5 Goals", "Over/Under 3.5 Goals"):
        n = str(runner_name or "").lower()
        return "OVER" if n.startswith("over") else "UNDER" if n.startswith("under") else None
    if market_name == "Both teams to Score?":
        n = str(runner_name or "").strip().lower()
        return "YES" if n == "yes" else "NO" if n == "no" else None
    return None


def _pick_target(market: str):
    """Pick-Markt → (Betwatch-Marktname, Token) für 1X2 / Ü-U 2.5-3.5 / BTTS. Sonst None."""
    m = (market or "").lower()
    if "bts" in m or "btts" in m or "beide" in m:
        return ("Both teams to Score?", "NO" if ("nein" in m or " no" in m) else "YES")
    side = market_side(market)   # home/away/over/under/None (eine Quelle, base.py)
    if side in ("home", "away"):
        return ("Match Odds", "H" if side == "home" else "A")
    if side in ("over", "under"):
        line = "3.5" if ("3.5" in m or "3,5" in m) else "2.5"
        return ("Over/Under %s Goals" % line, "OVER" if side == "over" else "UNDER")
    return None


def _devig(odds: dict) -> dict:
    """{token: odd} → {token: faire prob} (Overround raus). Leere/ungültige raus."""
    inv = {t: (1.0 / o) for t, o in odds.items() if isinstance(o, (int, float)) and o > 1}
    s = sum(inv.values())
    return {t: v / s for t, v in inv.items()} if s > 0 else {}


class BetfairMoneySignal(Signal):
    def __init__(self):
        self._track = None
        self._loaded = False

    def name(self) -> str:
        return "betfair_money"

    def _track_for(self, league, market_name):
        if not self._loaded:
            try:
                self._track = json.loads(_TRACK_FILE.read_text(encoding="utf-8"))
            except Exception:
                self._track = None
            self._loaded = True
        blm = (self._track or {}).get("byLeagueMarket") or {}
        return blm.get("%s|%s" % (league, market_name))

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        bf = context.get("betfair_snapshot")
        if not bf:
            return None
        target = _pick_target(pick.get("market", ""))
        if not target:
            return None
        market_name, tok = target
        mk = (bf.get("markets") or {}).get(market_name)
        if not mk:
            return None
        home, away = bf.get("home"), bf.get("away")

        # Geld je Token + Quoten je Token
        vol_by, odd_by = {}, {}
        for r in (mk.get("runners") or []):
            t = _tok(market_name, r.get("name"), home, away)
            if t is None:
                continue
            vol_by[t] = (vol_by.get(t, 0.0) + (r.get("vol") or 0.0))
            if isinstance(r.get("odd"), (int, float)):
                odd_by[t] = r["odd"]
        total = sum(vol_by.values())
        if total < MIN_MONEY_EUR or tok not in vol_by:
            return None

        money_share = vol_by[tok] / total
        fair = _devig(odd_by)
        fair_share = fair.get(tok)
        if fair_share is None:
            return None
        edge = money_share - fair_share            # + = mehr Geld als der Preis impliziert
        if abs(edge) < MIN_EDGE:
            return None

        score = max(-MAX_SIGNAL_PP, min(MAX_SIGNAL_PP, edge * SCORE_SCALE))
        vol_factor = min(1.0, total / 30000.0)
        confidence = min(0.85, 0.45 + 0.20 * vol_factor + abs(edge) * 0.8)

        # ── Track-Record-Modulation (Liga×Markt) ──
        tr = self._track_for(bf.get("league"), market_name)
        tr_note = ""
        # 04.09.2026: Urteil an der Rendite-UNTERGRENZE, nicht am Punktschaetzer. Median-n je
        # Bucket ist 5; von 1.641 Buckets tragen 3 ueberhaupt eine Untergrenze. Was keine hat,
        # verschiebt hier nichts mehr — weder nach oben noch nach unten.
        if tr and isinstance(tr.get("roiUg"), (int, float)):
            roi = tr["roiUg"]
            if roi <= TR_FADE_ROI:
                score = -score                      # dem Geld folgen verliert hier → Fade
                confidence = min(0.8, 0.5 + abs(roi))
                tr_note = " · ⚠️ Liga×Markt verliert (ROI-UG %+.0f%%, n%d) → gefadet" % (roi * 100, tr["n"])
            elif roi > TR_BOOST_ROI:
                confidence = min(0.92, confidence * (1.0 + min(0.3, roi)))
                tr_note = " · ✅ Liga×Markt solide (ROI-UG %+.0f%%, n%d)" % (roi * 100, tr["n"])
        else:
            confidence *= 0.85                       # noch keine belastbare Historie → etwas vorsichtiger

        lbl = {"H": "Heim", "D": "X", "A": "Ausw", "OVER": "Über", "UNDER": "Unter",
               "YES": "BTTS Ja", "NO": "BTTS Nein"}.get(tok, tok)
        stance = "stützt" if score > 0 else "warnt gegen"
        ev = ("💷 Betfair-Geld %s %s: %.0f%% des Geldes (fair %.0f%%) auf €%.0fk%s"
              % (stance, lbl, money_share * 100, fair_share * 100, total / 1000.0, tr_note))

        return SignalResult(
            score=round(score, 2),
            confidence=round(confidence, 2),
            evidence=ev,
            metadata={"market": market_name, "token": tok,
                      "money_share": round(money_share, 3), "fair_share": round(fair_share, 3),
                      "edge_pp": round(edge * 100, 2), "total_eur": round(total),
                      "track_roi": (tr or {}).get("roi"), "track_n": (tr or {}).get("n")},
        )
