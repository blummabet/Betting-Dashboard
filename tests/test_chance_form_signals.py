"""Tests: chance_creation + form_rating Signale (xG/Stats-Build 12.06.2026)."""
from sharp_signals.chance_creation import ChanceCreationSignal
from sharp_signals.form_rating import FormRatingSignal


def _ctx(home, away):
    return {"home_id": "ARG", "away_id": "BRA",
            "xg_stats": {"ARG": home, "BRA": away}}


# ── chance_creation ──────────────────────────────────────────────────────────

def test_chance_creation_home_pick_more_creation_positive():
    sig = ChanceCreationSignal()
    ctx = _ctx({"games": 5, "keyPassesForAvg": 9.0, "shotsInsideForAvg": 8.0},
               {"games": 5, "keyPassesForAvg": 4.0, "shotsInsideForAvg": 3.0})
    r = sig.evaluate({"market": "Heimsieg"}, ctx)
    assert r is not None and r.score > 0


def test_chance_creation_away_pick_flips_sign():
    sig = ChanceCreationSignal()
    ctx = _ctx({"games": 5, "keyPassesForAvg": 9.0, "shotsInsideForAvg": 8.0},
               {"games": 5, "keyPassesForAvg": 4.0, "shotsInsideForAvg": 3.0})
    r = sig.evaluate({"market": "Auswärtssieg"}, ctx)
    assert r is not None and r.score < 0   # Heim kreiert mehr → Auswärts-Pick negativ


def test_chance_creation_none_without_data():
    sig = ChanceCreationSignal()
    ctx = _ctx({"games": 5}, {"games": 5})   # keine keyPasses/shots
    assert sig.evaluate({"market": "Heimsieg"}, ctx) is None


def test_chance_creation_none_too_few_games():
    sig = ChanceCreationSignal()
    ctx = _ctx({"games": 1, "keyPassesForAvg": 9.0}, {"games": 5, "keyPassesForAvg": 4.0})
    assert sig.evaluate({"market": "Heimsieg"}, ctx) is None


def test_chance_creation_over_high_volume():
    sig = ChanceCreationSignal()
    ctx = _ctx({"games": 5, "keyPassesForAvg": 14.0, "shotsInsideForAvg": 12.0},
               {"games": 5, "keyPassesForAvg": 13.0, "shotsInsideForAvg": 11.0})
    r = sig.evaluate({"market": "Über 2.5 Tore"}, ctx)
    assert r is not None and r.score > 0   # viel Chancen-Volumen → Over


# ── form_rating ──────────────────────────────────────────────────────────────

def test_form_rating_better_home_positive():
    sig = FormRatingSignal()
    ctx = _ctx({"games": 5, "ratingAvg": 7.4, "xgSimAgainstAvg": 0.6},
               {"games": 5, "ratingAvg": 6.6, "xgSimAgainstAvg": 1.3})
    r = sig.evaluate({"market": "Heimsieg"}, ctx)
    assert r is not None and r.score > 0


def test_form_rating_only_outcome_markets():
    sig = FormRatingSignal()
    ctx = _ctx({"games": 5, "ratingAvg": 7.4}, {"games": 5, "ratingAvg": 6.6})
    assert sig.evaluate({"market": "Über 2.5 Tore"}, ctx) is None


def test_form_rating_none_without_rating():
    sig = FormRatingSignal()
    ctx = _ctx({"games": 5}, {"games": 5})
    assert sig.evaluate({"market": "Heimsieg"}, ctx) is None
