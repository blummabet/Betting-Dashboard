"""
sharp_signals/venue_form.py — Heim/Auswärts-Split + dichte Zuletzt-Raten (25.07.2026, Lucas)

Der Datensatz trägt pro Team `form.venueSeq` (H/A je Spiel) + ausgerichtete Bool-Sequenzen
`scoredSeq` (getroffen), `csSeq` (zu Null) und `o25Seq` (über 2.5) — 30/30 befüllt, aber bisher
NUR von der Streaks-Content-Pipeline gelesen, von KEINEM Pick-Signal. Das Tor-Modell poolt heute
nur `avgScored`/`avgConceded` über alle Spiele.

Dieses Signal holt den orthogonalen Teil heraus:
  · 1X2/DC → venue-KONDITIONIERTE Stärke: Heim-Team NUR in seinen Heimspielen (trifft/kassiert)
    gegen Auswärts-Team NUR in seinen Auswärtsspielen. Fängt „Festung daheim / schwacher Reisender"
    — gerade in der reise-lastigen MLS größer als der Gesamtschnitt zeigt.
  · O/U 2.5 → kombinierte Zuletzt-Über-Rate beider Teams (dichter/aktueller als die dünne h2h-Rate).

form-Familie (Anti-Korr-Discount gegen form_trend/xg_strength — dieselbe Angriffs-/Form-Info nicht
doppelt zählen). BTTS bewusst NICHT (noch keine BTTS-Quoten; kommt mit dem O/U+BTTS-Fetch).
"""
from __future__ import annotations
from typing import Optional
from sharp_signals.base import Signal, SignalResult, market_side


DEFAULT_THRESHOLDS = {
    "min_venue_games":  3,     # min Spiele am jeweiligen Ort in der Sequenz
    "scale_1x2_pp":     4.0,   # pp pro Venue-Netto-Differenz (Bereich ±2 → ±8, gedeckelt)
    "ou_scale_pp":      4.0,   # pp pro (Über-Rate − 0.5)
    "ou_min_games":     5,
    "min_signal_pp":    0.8,
    "max_signal_pp":    4.0,
    "base_conf":        0.5,
    "max_conf":         0.7,
}


def _load_thresholds() -> dict:
    try:
        import json, os
        from pathlib import Path
        raw = json.loads((Path(__file__).parent.parent / "cocobet_config.json")
                         .read_text(encoding="utf-8"))
        active = os.environ.get("COCOBET_PROFILE") or raw["profiles"].get("active", "wm2026")
        cfg = raw["profiles"].get(active, {}).get("venue_form") or {}
        return {**DEFAULT_THRESHOLDS, **cfg}
    except Exception:
        return DEFAULT_THRESHOLDS


def _rate(seq, idx):
    return sum(1 for i in idx if seq[i]) / len(idx) if idx else None


def _ou_market(market: str):
    """(+1 Über / −1 Unter, Linie) oder (None, None). Nur 2.5 (einzige verlässlich geholte Linie)."""
    m = (market or "").lower()
    if "ecken" in m or "corner" in m:
        return (None, None)
    is_over = "über" in m or "uber" in m or "over" in m
    is_under = "unter" in m or "under" in m
    if not (is_over or is_under):
        return (None, None)
    if "1.5" in m or "1,5" in m or "3.5" in m or "3,5" in m:
        return (None, None)   # nur 2.5 — für 1.5/3.5 fehlen die Sequenz-Daten sauber
    return (+1 if is_over else -1, 2.5)


class VenueFormSignal(Signal):
    """Heim/Auswärts-konditionierte Form + Zuletzt-Über-Rate."""

    def __init__(self):
        self._t = _load_thresholds()

    def name(self) -> str:
        return "venue_form"

    def _venue_net(self, form: dict, venue: str):
        """Getroffen-Rate − Kassiert-Rate NUR in Heim- bzw. Auswärtsspielen. None bei zu wenig."""
        vs, ss, cs = form.get("venueSeq"), form.get("scoredSeq"), form.get("csSeq")
        if not (isinstance(vs, list) and isinstance(ss, list) and isinstance(cs, list)):
            return None
        n = min(len(vs), len(ss), len(cs))
        idx = [i for i in range(n) if vs[i] == venue]
        if len(idx) < self._t["min_venue_games"]:
            return None
        scored = _rate(ss, idx)
        clean = _rate(cs, idx)
        if scored is None or clean is None:
            return None
        return scored - (1.0 - clean), len(idx)   # netto, + Sample-Größe

    def _over_rate(self, form: dict):
        seq = form.get("o25Seq")
        if not isinstance(seq, list) or len(seq) < self._t["ou_min_games"]:
            return None
        return sum(1 for x in seq if x) / len(seq)

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        side = market_side(pick.get("market", ""))
        if side not in ("home", "away", "over", "under"):
            return None
        forms = context.get("form") or {}
        hid, aid = context.get("home_id"), context.get("away_id")
        fh, fa = forms.get(hid) or {}, forms.get(aid) or {}
        if not fh or not fa:
            return None

        cap = self._t["max_signal_pp"]

        # ── 1X2 / DC (home/away): venue-konditionierte Stärke ──
        if side in ("home", "away"):
            nh = self._venue_net(fh, "H")
            na = self._venue_net(fa, "A")
            if nh is None or na is None:
                return None
            net_home, gh = nh
            net_away, ga = na
            relative = net_home - net_away          # >0 = Heim venue-stärker
            signed = relative if side == "home" else -relative
            score = signed * self._t["scale_1x2_pp"]
            if abs(score) < self._t["min_signal_pp"]:
                return None
            score = max(-cap, min(cap, score))
            conf = min(self._t["max_conf"], self._t["base_conf"] + 0.02 * min(gh, ga))
            oc = "Heim" if side == "home" else "Auswärts"
            ev = (f"⚡ Ortsform: Heim trifft in {round(net_home*100+0)}-Netto daheim, Auswärts "
                  f"{round(net_away*100+0)}-Netto auf Reisen (getroffen − kassiert) — "
                  f"{relative:+.2f} Unterschied zugunsten {'Heim' if relative>0 else 'Auswärts'}. "
                  f"Der Heim/Auswärts-Split ist hier aussagekräftiger als der Gesamtschnitt.")
            return SignalResult(round(score, 2), round(conf, 2), ev,
                                metadata={"venue_net_home": round(net_home, 3),
                                          "venue_net_away": round(net_away, 3),
                                          "relative": round(relative, 3),
                                          "home_venue_games": gh, "away_venue_games": ga,
                                          "pick_side": side})

        # ── O/U 2.5: kombinierte Zuletzt-Über-Rate ──
        ou_dir, _line = _ou_market(pick.get("market", ""))
        if ou_dir is None:
            return None
        oh, oa = self._over_rate(fh), self._over_rate(fa)
        if oh is None or oa is None:
            return None
        combined = (oh + oa) / 2.0
        lean = combined - 0.5
        score = ou_dir * lean * self._t["ou_scale_pp"]
        if abs(score) < self._t["min_signal_pp"]:
            return None
        score = max(-cap, min(cap, score))
        conf = min(self._t["max_conf"], self._t["base_conf"] + 0.02 * min(len(fh.get("o25Seq", [])),
                                                                          len(fa.get("o25Seq", []))))
        side_str = "Über" if ou_dir == +1 else "Unter"
        ev = (f"⚡ Zuletzt gingen {round(oh*100)}% der Heim- und {round(oa*100)}% der Auswärts-Spiele "
              f"über 2.5 (Schnitt {round(combined*100)}%) — spricht für {side_str} 2.5.")
        return SignalResult(round(score, 2), round(conf, 2), ev,
                            metadata={"over_rate_home": round(oh, 3), "over_rate_away": round(oa, 3),
                                      "combined": round(combined, 3), "pick_side": f"{side_str} 2.5"})
