"""17.07.2026 — market_drift darf nicht durch Platzhalter-Quoten vergiftet werden.

BEFUND (Lucas: „MLS-Cards morgens da, dann weg — Sharp Radar hat aber Moves"): Der markt-weite
Median-Drift (in detect_steam vom Move abgezogen, um spielspezifisches Sharp-Money zu isolieren)
wurde von vier fernen MLS-Spieltagen verzerrt, deren AKTUELLES 1X2 noch ein Platzhalter war
(aw=1.04, Opening plausibel 4.75) → 67–81pp Geister-Moves. Median aw sprang von echten 1.24 auf
1.80. Dadurch fiel ein legitimer 4.5pp-Steam-Pick (New England) nach Drift-Abzug unter die
3pp-Schwelle → NOBET → Card verschwand.

Ein einziges Fixture mit Platzhalter-Quote vergiftet also die Pick-Auswahl ALLER Spiele. Dritte
Inkarnation des Platzhalter-Problems (nach Radar-Geistern und Geister-Picks).
"""
import steam_engine as S


ECHT = {
    "A": {"odds_open": {"hw": 1.8, "dr": 3.6, "aw": 4.5}, "hw": 1.9, "dr": 3.5, "aw": 4.2},
    "B": {"odds_open": {"hw": 2.1, "dr": 3.4, "aw": 3.4}, "hw": 2.0, "dr": 3.4, "aw": 3.6},
    "C": {"odds_open": {"hw": 1.5, "dr": 4.0, "aw": 6.0}, "hw": 1.55, "dr": 4.0, "aw": 5.6},
    "D": {"odds_open": {"hw": 2.5, "dr": 3.3, "aw": 2.7}, "hw": 2.6, "dr": 3.3, "aw": 2.6},
    "E": {"odds_open": {"hw": 1.9, "dr": 3.5, "aw": 3.9}, "hw": 1.95, "dr": 3.5, "aw": 3.8},
}
# Platzhalter im AKTUELLEN Wert (aw=1.04, Overround absurd) — der reale MLS-Fall.
GEIST_AKTUELL = {"odds_open": {"hw": 1.65, "dr": 3.7, "aw": 4.75}, "hw": 1.04, "dr": 1.01, "aw": 1.04}
# Platzhalter im OPENING.
GEIST_OPENING = {"odds_open": {"hw": 1.04, "dr": 1.01, "aw": 1.04}, "hw": 1.8, "dr": 3.6, "aw": 4.5}


class TestDriftIgnoriertPlatzhalter:
    def test_geister_aktuell_verzerren_den_drift_nicht(self):
        rein = S.market_drift(ECHT)
        vergiftet = S.market_drift({**ECHT, "G1": GEIST_AKTUELL, "G2": GEIST_AKTUELL})
        # Der Drift darf sich durch die Geister praktisch nicht verschieben.
        assert abs(rein["aw"] - vergiftet["aw"]) < 0.5, \
            f"Platzhalter-aktuell verzerrt den aw-Drift: {rein['aw']} → {vergiftet['aw']}"

    def test_geister_opening_verzerren_den_drift_nicht(self):
        rein = S.market_drift(ECHT)
        vergiftet = S.market_drift({**ECHT, "G": GEIST_OPENING})
        assert abs(rein["aw"] - vergiftet["aw"]) < 0.5

    def test_echte_spiele_zaehlen_weiter(self):
        # Der Filter darf nicht ALLES wegwerfen — echte Fixtures müssen den Drift noch bilden.
        dr = S.market_drift({**ECHT, "G": GEIST_AKTUELL})
        assert "aw" in dr and "hw" in dr, "Drift ganz verloren — Filter zu aggressiv"

    def test_legitimer_pick_ueberlebt_nach_fix(self):
        """Der konkrete Fall: ein 4.5pp-Auswärts-Move muss nach Drift-Abzug ein Trigger bleiben,
        wenn der Drift nicht durch Geister aufgebläht ist."""
        odds = {**ECHT, "G": GEIST_AKTUELL,
                "PICK": {"odds_open": {"hw": 1.9, "dr": 3.6, "aw": 4.33},
                         "hw": 2.0, "dr": 3.6, "aw": 3.62}}   # aw: 4.33→3.62 ≈ 4.5pp
        dr = S.market_drift(odds)
        trigs = S.detect_steam(odds["PICK"], drift=dr)
        assert any(t.get("side") == "away" for t in trigs), \
            f"legitimer 4.5pp-Move wird durch aufgeblähten Drift ({dr.get('aw')}) weggefiltert"
