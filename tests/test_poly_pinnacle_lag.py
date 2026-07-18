"""18.07.2026 — Lead-Lag zwischen Polymarket und Pinnacle.

Das Ergebnis auf echten Daten ist ein NEGATIVBEFUND: kein messbarer Vorlauf in eine der beiden
Richtungen, Peak sitzt bei Lag 0 — stabil über Raster 15/30/60/120min.

Ein Negativbefund ist aber nur so viel wert wie die Fähigkeit der Methode, das Gegenteil zu
finden. Deshalb sind die wichtigsten Tests hier die mit KÜNSTLICH eingebautem Vorlauf: würde
das Skript einen echten Lead übersehen, hieße „kein Vorlauf" schlicht „mein Code ist kaputt" —
und wir würden eine reale Edge wegwerfen, weil ein Test grün war.
"""
from datetime import datetime, timedelta, timezone

import pytest

import analyze_poly_pinnacle_lag as A

KO = datetime(2026, 7, 20, 18, 0, tzinfo=timezone.utc)


def _iso(dt):
    return dt.isoformat()


def _reihe(werte, start_h_vor_ko, schritt_h=1):
    """[(ts, wert)] rückwärts vom Anpfiff."""
    return [(KO - timedelta(hours=start_h_vor_ko - i * schritt_h), v)
            for i, v in enumerate(werte)]


VIG = 1.05   # Overround. MUSS > 1.0 sein, sonst wirft odds_plausibility die Snaps als
             # Platzhalter raus — und der Test misst dann versehentlich gar nichts.


def _odds_snaps(probs, start_h):
    """Wahrscheinlichkeit für Heim → plausible 1X2-Quoten."""
    out = []
    for ts, p in _reihe(probs, start_h):
        p = max(0.10, min(0.80, p))
        rest = (1.0 - p) / 2
        out.append({"ts": _iso(ts), "hw": round(1 / (p * VIG), 3),
                    "dr": round(1 / (rest * VIG), 3), "aw": round(1 / (rest * VIG), 3)})
    return out


def _poly_snaps(probs, start_h):
    out = []
    for ts, p in _reihe(probs, start_h):
        rest = (1.0 - p) / 2
        out.append({"ts": _iso(ts), "poly_hw": p, "poly_dr": rest, "poly_aw": rest})
    return out


def _lauf(pinn_probs, poly_probs, start_h=30, n_matches=12):
    """Mehrere Matches mit demselben Muster — sonst reicht n nicht für MIN_PAIRS."""
    odds, poly, fixtures = {}, {}, {}
    for i in range(n_matches):
        k = f"M{i}"
        odds[k] = _odds_snaps(pinn_probs, start_h)
        poly[k] = _poly_snaps(poly_probs, start_h)
        fixtures[k] = {"kickoff": _iso(KO)}
    return A.analyze(odds, poly, fixtures)


def _peak(rep):
    g = [l for l in rep["lags"] if l["korrelation"] is not None]
    return max(g, key=lambda l: l["korrelation"]) if g else None


# Ein Zickzack-Muster: genug echte Bewegung in beide Richtungen, damit Korrelation definiert ist.
MUSTER = [0.40, 0.44, 0.41, 0.47, 0.43, 0.50, 0.46, 0.53, 0.49, 0.56, 0.52, 0.58]


class TestMethodeFindetEchtenVorlauf:
    """Der entscheidende Nachweis. Ohne diese Tests ist der Negativbefund wertlos."""

    def test_poly_fuehrt_wird_erkannt(self):
        """Poly macht dieselbe Bewegung 2h FRÜHER → Peak muss bei +2h liegen."""
        rep = _lauf(pinn_probs=MUSTER, poly_probs=MUSTER[2:] + MUSTER[:2])
        p = _peak(rep)
        assert p["lagStunden"] == pytest.approx(2.0), \
            f"eingebauter Poly-Vorlauf nicht gefunden (Peak bei {p['lagStunden']}h) — " \
            f"ein echter Lead in den Live-Daten würde genauso übersehen"
        assert "Polymarket führt" in rep["befund"]

    def test_pinnacle_fuehrt_wird_erkannt(self):
        rep = _lauf(pinn_probs=MUSTER[2:] + MUSTER[:2], poly_probs=MUSTER)
        p = _peak(rep)
        assert p["lagStunden"] == pytest.approx(-2.0)
        assert "Pinnacle führt" in rep["befund"]

    def test_gleichlauf_wird_als_gleichlauf_erkannt(self):
        rep = _lauf(pinn_probs=MUSTER, poly_probs=MUSTER)
        assert _peak(rep)["lagStunden"] == pytest.approx(0.0)
        assert "kein messbarer Vorlauf" in rep["befund"]


class TestFallenSindAbgefangen:
    def test_platzhalter_quoten_fliegen_raus(self):
        """1.04/1.01/1.04 = 291 % Overround. Ungefiltert erzeugen sie eine gewaltige
        Scheinbewegung — dieselbe Quelle, die schon 80pp-Fake-Steam ausgelöst hat."""
        odds = {"M0": [{"ts": _iso(KO - timedelta(hours=h)), "hw": 1.04, "dr": 1.01, "aw": 1.04}
                       for h in range(20, 0, -1)]}
        poly = {"M0": _poly_snaps(MUSTER, 20)}
        rep = A.analyze(odds, poly, {"M0": {"kickoff": _iso(KO)}})
        assert rep["stats"]["verworfenPlatzhalter"] == 20
        assert rep["stats"]["matches"] == 0, "Platzhalter-Match ging in die Auswertung ein"

    def test_in_play_snaps_zaehlen_nicht(self):
        """Nach Anpfiff bewegen sich beide Reihen wegen der TORE — trivial korreliert und
        für unsere Frage bedeutungslos."""
        nach_ko = [(KO + timedelta(hours=1), 0.9), (KO + timedelta(hours=2), 0.95)]
        g = A._grid(nach_ko, KO, "hw")
        assert g == {}, "In-Play-Snapshots landen im Raster"

    def test_ohne_kickoff_kein_raten(self):
        """Ohne Anpfiff ist kein Zeitbezug herstellbar — Match verwerfen statt schätzen."""
        rep = A.analyze({"M0": _odds_snaps(MUSTER, 20)}, {"M0": _poly_snaps(MUSTER, 20)}, {})
        assert rep["stats"]["verworfenKeinKickoff"] == 1
        assert rep["stats"]["matches"] == 0

    def test_beidseitiger_stillstand_zaehlt_nicht(self):
        """Zwei Nullen korrelieren perfekt. Würden wir sie mitzählen, sähe jede ruhige Phase
        wie Gleichlauf aus und würde einen echten Lead überdecken."""
        flach = [0.5] * 12
        rep = _lauf(pinn_probs=flach, poly_probs=flach)
        assert all(l["n"] == 0 for l in rep["lags"]), "Stillstand wird als Beobachtung gezählt"
        assert rep["befund"] == "zu wenig Daten"


class TestDeVig:
    def test_wahrscheinlichkeiten_summieren_auf_eins(self):
        f = A._devig(2.0, 3.5, 4.0)
        assert sum(f.values()) == pytest.approx(1.0)

    def test_kaputte_quoten_geben_none(self):
        assert A._devig(0, 3.5, 4.0) is None
        assert A._devig(None, 3.5, 4.0) is None
        assert A._devig("x", 3.5, 4.0) is None


class TestKOSpieleGehenNichtVerloren:
    def test_ko_fixtures_landen_in_der_map(self):
        """Wiederkehrender Fehler im Projekt: KO-Spiele liegen in koFixtures, NICHT in groups.
        Wer nur groups iteriert, verliert die halbe Endrunde."""
        data = {"groups": {"A": {"fixtures": [{"key": "G1", "home": "a", "away": "b"}]}},
                "koFixtures": [{"key": "K1", "home": "c", "away": "d"}]}
        m = A._fixtures_map(data)
        assert "G1" in m and "K1" in m, "koFixtures fehlen in der Fixture-Map"
