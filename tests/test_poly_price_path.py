# -*- coding: utf-8 -*-
"""tests/test_poly_price_path.py — 29.08.2026 (Lucas: „mach den Preispfad").

Der Pfad beantwortet die Frage, an der die Wallet-These haengt: bewegt sich der Preis, NACHDEM
jemand eingestiegen ist? Vorher ging das nicht — Poly hatte median 2 Punkte je Markt (Betfair
zum Vergleich: 51). Mit zwei Punkten misst man keinen Nachlauf.

Die Tests sichern vor allem die Stellen, an denen ein Pfad still falsch wird: doppelte Punkte aus
ueberlappenden Laeufen, aufgeloeste Maerkte als „Preis", und Luecken, die als „keine Bewegung"
durchgehen.
"""
from datetime import datetime, timedelta, timezone

import poly_price_path as P

T0 = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)


def _markt(hw=0.60, aw=0.40, vol=50000, league="EPL", resolved=None, htk=5.0):
    return {"league": league, "prices": {"Heim": hw, "Ausw": aw},
            "totalUsd": vol, "hoursToKickoff": htk, "resolved": resolved}


class TestFortschreiben:
    def test_erster_lauf_legt_den_punkt_an(self):
        d = P.update({}, [{"k1": _markt()}], now=T0)
        assert list(d) == ["k1"]
        pt = d["k1"]["points"][0]
        assert pt["p"] == {"Heim": 0.6, "Ausw": 0.4} and pt["vol"] == 50000 and pt["htk"] == 5.0

    def test_zweiter_lauf_haengt_an(self):
        d = P.update({}, [{"k1": _markt()}], now=T0)
        d = P.update(d, [{"k1": _markt(hw=0.66, aw=0.34)}], now=T0 + timedelta(minutes=30))
        assert [p["p"]["Heim"] for p in d["k1"]["points"]] == [0.6, 0.66]

    def test_ueberlappende_laeufe_verdoppeln_den_pfad_nicht(self):
        # Zwei Laeufe koennen sich ueberschneiden (Cron + Dispatch). Ohne Mindestabstand haette
        # derselbe Preis zwei Punkte — und jede Bewegungsmessung waere verwaessert.
        d = P.update({}, [{"k1": _markt()}], now=T0)
        d = P.update(d, [{"k1": _markt(hw=0.61)}], now=T0 + timedelta(minutes=2))
        assert len(d["k1"]["points"]) == 1

    def test_spaetere_quelle_gewinnt(self):
        # Close-Feed ist frischer als der Upcoming-Sweep -> steht in der Liste hinten.
        d = P.update({}, [{"k1": _markt(hw=0.60)}, {"k1": _markt(hw=0.70)}], now=T0)
        assert d["k1"]["points"][0]["p"]["Heim"] == 0.7

    def test_deckel_wirft_die_aeltesten_punkte(self):
        d = {}
        for i in range(6):
            d = P.update(d, [{"k1": _markt(hw=0.50 + i / 100)}],
                         now=T0 + timedelta(minutes=30 * i), max_points=4)
        pts = [p["p"]["Heim"] for p in d["k1"]["points"]]
        assert len(pts) == 4 and pts[0] == 0.52 and pts[-1] == 0.55

    def test_aufgeloeste_maerkte_kommen_nicht_in_den_pfad(self):
        assert P.update({}, [{"k1": _markt(resolved=True)}], now=T0) == {}

    def test_settle_preise_sind_kein_preis(self):
        # 1.0 / 0.0 ist ein Ergebnis, keine Bewertung — sonst endet jeder Pfad mit einem Sprung
        # auf 100 %, der wie ein gewaltiger Move aussieht.
        assert P.update({}, [{"k1": {"prices": {"Heim": 1.0, "Ausw": 0.0}}}], now=T0) == {}

    def test_alte_maerkte_fallen_raus(self):
        d = P.update({}, [{"k1": _markt()}], now=T0)
        d = P.update(d, [{"k2": _markt()}], now=T0 + timedelta(hours=40))
        assert list(d) == ["k2"]


class TestMarkout:
    def _pfad(self):
        d = {}
        for i, pr in enumerate([0.50, 0.52, 0.55, 0.58]):
            d = P.update(d, [{"k1": _markt(hw=pr, aw=round(1 - pr, 2))}],
                         now=T0 + timedelta(minutes=15 * i))
        return d

    def test_bewegung_zu_uns_ist_positiv(self):
        # Einstieg bei 0.50, 30 Minuten spaeter 0.55 -> +5pp, der Markt kam zu uns.
        assert P.markout(self._pfad(), "k1", "Heim", T0.isoformat(), minuten=30) == 5.0

    def test_bewegung_gegen_uns_ist_negativ(self):
        assert P.markout(self._pfad(), "k1", "Ausw", T0.isoformat(), minuten=30) == -5.0

    def test_ohne_abdeckung_kommt_None_und_nicht_null(self):
        # Eine Luecke als 0 zu buchen hiesse „keine Bewegung" — das waere eine erfundene
        # Beobachtung, die jeden Schnitt Richtung null zieht.
        assert P.markout(self._pfad(), "k1", "Heim", T0.isoformat(), minuten=600) is None
        assert P.markout(self._pfad(), "k2", "Heim", T0.isoformat()) is None
        assert P.markout(self._pfad(), "k1", "Gibtsnicht", T0.isoformat()) is None

    def test_es_wird_nicht_interpoliert(self):
        # Zwischen zwei Messpunkten wird kein Wert erfunden: das Ziel nimmt den ERSTEN Punkt
        # danach, der Start den letzten davor.
        p = self._pfad()
        assert P.markout(p, "k1", "Heim", T0.isoformat(), minuten=20) == 5.0   # -> Punkt bei +30
