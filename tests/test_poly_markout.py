"""19.07.2026 — Markout-Test: trägt Making, oder frisst Adverse Selection die Spread-Ersparnis?

Angestoßen von Lucas' Krypto-Befund (Maker-Markout −4.18pp, „echt-toxisch"). Bevor wir für
Fußball `maker_enabled` je anfassen, misst das Skript aus echter Preishistorie, ob eine ruhende
Bid genau bei Abwärtsdruck füllt und der Preis danach WEITER fällt.

Die Tests fixieren die Kern-Mechanik — vor allem: dass ein sinkender Preis nach Fill als NEGATIVER
Markout erkannt wird (sonst würde das Tor eine toxische Strategie durchwinken).
"""
from datetime import datetime, timedelta, timezone

import poly_markout as MO


def _hist(prices, minutes=30):
    """Eine Preisreihe auf poly_hw, gleichmäßig getaktet."""
    t0 = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)
    return {"K": [{"ts": (t0 + timedelta(minutes=minutes * i)).isoformat(), "poly_hw": p}
                  for i, p in enumerate(prices)]}


def _many(prices, n=20, minutes=30):
    """Dasselbe Muster über viele Märkte, damit MIN_FILLS erreicht wird."""
    out = {}
    base = _hist(prices, minutes=minutes)["K"]
    for i in range(n):
        out[f"M{i}"] = [dict(s) for s in base]
    return out


class TestMechanik:
    def test_abwaerts_dann_weiter_runter_ist_negativer_markout(self):
        # jeder Down-Tick wird von weiterem Fall gefolgt → Adverse Selection
        rep = MO.compute_markout(_many([0.60, 0.55, 0.50, 0.45, 0.40, 0.35]))
        head = rep["horizons"]["2.0h"]
        assert head["meanPP"] is not None and head["meanPP"] < 0, "sinkender Preis = negativer Markout"

    def test_abwaerts_dann_erholung_ist_positiver_markout(self):
        # Down-Tick, dann bounct der Preis binnen 2h ÜBER den Fill zurück → Making trägt.
        # 60-min-Takt, damit das +2h-Fenster (2 Snapshots) die Erholung wirklich erfasst.
        rep = MO.compute_markout(_many([0.60, 0.50, 0.62, 0.52, 0.64, 0.54, 0.66], minutes=60))
        head = rep["horizons"]["2.0h"]
        assert head["meanPP"] is not None and head["meanPP"] > 0

    def test_nur_abwaerts_ticks_zaehlen_als_fills(self):
        # rein steigender Preis → keine Bid-Füllung → keine Fills
        rep = MO.compute_markout(_many([0.30, 0.35, 0.40, 0.45, 0.50]))
        assert rep["fills"] == 0


class TestVerdikt:
    def test_toxisch_wird_als_traegt_nicht_markiert(self):
        rep = MO.compute_markout(_many([0.70, 0.60, 0.50, 0.40, 0.30, 0.20], n=30))
        # steiler Dauerfall: Markout deutlich unter −Spread-Ersparnis
        assert rep["verdict"] == "traegt_nicht", f"toxische Serie nicht erkannt ({rep['netMakerPP']})"

    def test_zu_wenig_daten_kein_urteil(self):
        rep = MO.compute_markout(_hist([0.6, 0.5, 0.55]))   # 1 Markt, < MIN_FILLS
        assert rep["verdict"] == "zu wenig Daten" and rep["netMakerPP"] is None

    def test_netto_ist_markout_plus_spread(self):
        rep = MO.compute_markout(_many([0.60, 0.50, 0.58, 0.49, 0.57, 0.48, 0.56], n=30))
        head = rep["horizons"]["2.0h"]["meanPP"]
        assert rep["netMakerPP"] == round(head + rep["spreadSavedPP"], 3)


class TestRobustheit:
    def test_platzhalter_preise_raus(self):
        # 0.0/1.0 sind Platzhalter, kein Markt → dürfen keine Fills erzeugen
        rep = MO.compute_markout(_many([1.0, 0.0, 1.0, 0.0]))
        assert rep["fills"] == 0

    def test_leere_historie(self):
        rep = MO.compute_markout({})
        assert rep["fills"] == 0 and rep["verdict"] == "zu wenig Daten"

    def test_alle_outcome_felder_werden_gelesen(self):
        t0 = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)
        h = {"K": [{"ts": (t0 + timedelta(minutes=30 * i)).isoformat(),
                    "poly_o25": p, "poly_u25": 1 - p} for i, p in enumerate([0.6, 0.5, 0.55])]}
        rep = MO.compute_markout(h)
        assert rep["fills"] >= 1, "O/U-Felder werden übersehen"


def test_gegen_echte_daten_lauffaehig():
    """Smoke: läuft das Skript über die echte WM-Historie ohne Absturz und liefert ein Urteil?"""
    import json
    from pathlib import Path
    p = Path(__file__).resolve().parent.parent / "wm2026-poly-history.json"
    if not p.exists():
        return
    rep = MO.compute_markout(json.loads(p.read_text("utf-8")))
    assert rep["verdict"] in ("traegt", "traegt_nicht", "grenzwertig", "zu wenig Daten")
    assert rep["fills"] > 0
