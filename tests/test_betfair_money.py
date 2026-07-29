import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sharp_signals.betfair_money import BetfairMoneySignal

BF = {
    "home": "Barcelona SC", "away": "Emelec", "league": "Ecuador Serie A",
    "markets": {
        "Match Odds": {"runners": [
            {"name": "Barcelona SC", "odd": 2.0, "vol": 8000},
            {"name": "The Draw", "odd": 3.5, "vol": 1000},
            {"name": "Emelec", "odd": 4.0, "vol": 1000}]},
        "Over/Under 2.5 Goals": {"runners": [
            {"name": "Over 2.5 Goals", "odd": 1.9, "vol": 3000},
            {"name": "Under 2.5 Goals", "odd": 2.0, "vol": 1000}]},
        "Both teams to Score?": {"runners": [
            {"name": "Yes", "odd": 1.8, "vol": 2500},
            {"name": "No", "odd": 2.1, "vol": 1500}]},
    },
}
def ctx(bf=BF): return {"betfair_snapshot": bf}


def test_kein_snapshot_kein_signal():
    assert BetfairMoneySignal().evaluate({"market": "Heimsieg"}, {}) is None


def test_1x2_geld_auf_heim_stuetzt():
    r = BetfairMoneySignal().evaluate({"market": "Heimsieg"}, ctx())
    assert r is not None and r.score > 0
    assert "Betfair-Geld stützt Heim" in r.evidence
    assert r.metadata["token"] == "H" and r.metadata["market"] == "Match Odds"


def test_under_ohne_geld_warnt():
    # Geld liegt auf Over → Under-Pick wird gewarnt (negativer score)
    r = BetfairMoneySignal().evaluate({"market": "Unter 2.5"}, ctx())
    assert r is not None and r.score < 0
    assert r.metadata["token"] == "UNDER"


def test_over_und_line_35():
    r = BetfairMoneySignal().evaluate({"market": "Über 2.5 Tore"}, ctx())
    assert r.metadata["market"] == "Over/Under 2.5 Goals" and r.metadata["token"] == "OVER"
    assert r.score > 0


def test_btts_mapping():
    r = BetfairMoneySignal().evaluate({"market": "BTTS Ja"}, ctx())
    assert r.metadata["market"] == "Both teams to Score?" and r.metadata["token"] == "YES"


def test_zu_wenig_geld_kein_signal():
    thin = {**BF, "markets": {"Match Odds": {"runners": [
        {"name": "Barcelona SC", "odd": 2.0, "vol": 10},
        {"name": "The Draw", "odd": 3.5, "vol": 5},
        {"name": "Emelec", "odd": 4.0, "vol": 5}]}}}
    assert BetfairMoneySignal().evaluate({"market": "Heimsieg"}, ctx(thin)) is None


def test_track_record_boost():
    sig = BetfairMoneySignal()
    sig._track = {"byLeagueMarket": {"Ecuador Serie A|Match Odds": {"n": 30, "roi": 0.2}}}
    sig._loaded = True
    r = sig.evaluate({"market": "Heimsieg"}, ctx())
    assert r.score > 0 and "solide" in r.evidence
    # Boost hebt Confidence über den Basiswert
    base = BetfairMoneySignal(); base._track = {"byLeagueMarket": {}}; base._loaded = True
    rb = base.evaluate({"market": "Heimsieg"}, ctx())
    assert r.confidence > rb.confidence


def test_track_record_fade_dreht_um():
    sig = BetfairMoneySignal()
    sig._track = {"byLeagueMarket": {"Ecuador Serie A|Match Odds": {"n": 40, "roi": -0.18}}}
    sig._loaded = True
    r = sig.evaluate({"market": "Heimsieg"}, ctx())
    # Geld auf Heim, aber Liga×Markt verliert historisch → Signal dreht auf NEGATIV (Fade)
    assert r.score < 0 and "gefadet" in r.evidence


if __name__ == "__main__":
    import types
    fns = [v for k, v in dict(globals()).items() if k.startswith("test_") and isinstance(v, types.FunctionType)]
    for f in fns: f(); print("ok", f.__name__)
    print("\n%d tests passed" % len(fns))
