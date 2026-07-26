#!/usr/bin/env python3
"""Tests für sharp_signals/venue_form.py (25.07.2026) — Heim/Auswärts-Split + Zuletzt-Über-Rate."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sharp_signals.venue_form import VenueFormSignal

SIG = VenueFormSignal()

# 8 Spiele, abwechselnd H/A → je 4 Heim-/4 Auswärts-Spiele
VEN = ["H", "A", "H", "A", "H", "A", "H", "A"]


def _team(scored_at_H, clean_at_H, scored_at_A, clean_at_A, o25=None):
    ss, cs = [], []
    for v in VEN:
        if v == "H":
            ss.append(scored_at_H); cs.append(clean_at_H)
        else:
            ss.append(scored_at_A); cs.append(clean_at_A)
    f = {"venueSeq": VEN, "scoredSeq": ss, "csSeq": cs}
    if o25 is not None:
        f["o25Seq"] = o25
    return f


def _ctx(home, away):
    return {"home_id": "H", "away_id": "A", "form": {"H": home, "A": away}}


# Heim daheim stark (trifft+zu Null), Auswärts auf Reisen schwach (trifft nicht, kassiert)
HOME_STRONG = _team(True, True, True, False, o25=[True, True, True, True, True, False])
AWAY_WEAK = _team(False, False, False, False, o25=[True, True, True, False, True, False])


def test_home_pick_positive_when_home_venue_stronger():
    r = SIG.evaluate({"market": "Heimsieg"}, _ctx(HOME_STRONG, AWAY_WEAK))
    assert r is not None and r.score > 0 and r.metadata["pick_side"] == "home"


def test_away_pick_negative_when_home_venue_stronger():
    # Auswärts-Pick, aber Heim ist venue-stärker → Signal warnt (negativ)
    r = SIG.evaluate({"market": "Auswärtssieg"}, _ctx(HOME_STRONG, AWAY_WEAK))
    assert r is not None and r.score < 0 and r.metadata["pick_side"] == "away"


def test_insufficient_venue_games_none():
    short = {"venueSeq": ["H", "A"], "scoredSeq": [True, False], "csSeq": [True, False]}
    assert SIG.evaluate({"market": "Heimsieg"}, _ctx(short, short)) is None


def test_over_pick_positive_high_over_rate():
    r = SIG.evaluate({"market": "Über 2.5 Tore"}, _ctx(HOME_STRONG, AWAY_WEAK))
    assert r is not None and r.score > 0 and "Über" in r.metadata["pick_side"]


def test_under_pick_negative_high_over_rate():
    r = SIG.evaluate({"market": "Unter 2.5 Tore"}, _ctx(HOME_STRONG, AWAY_WEAK))
    assert r is not None and r.score < 0


def test_ou_35_line_skipped_none():
    # 3.5 hat keine sauberen Sequenz-Daten → kein Signal
    assert SIG.evaluate({"market": "Über 3.5 Tore"}, _ctx(HOME_STRONG, AWAY_WEAK)) is None


def test_btts_market_none():
    assert SIG.evaluate({"market": "Beide treffen — Ja"}, _ctx(HOME_STRONG, AWAY_WEAK)) is None


def test_missing_form_none():
    assert SIG.evaluate({"market": "Heimsieg"}, {"home_id": "H", "away_id": "A", "form": {}}) is None


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  ok   {name}")
            except AssertionError as e:
                fails += 1; print(f"  FAIL {name}: {e}")
    print("ALLE GRUEN" if not fails else f"{fails} FEHLER")
    sys.exit(1 if fails else 0)
