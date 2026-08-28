"""28.08.2026 — das 2-Stunden-Fenster des Auto-Traders hat nie existiert.

Aus Lucas' Runner-Log, fuenf verschiedene Spiele, alle mit derselben Zahl:

    ⏰ Zu nah am Anpfiff (-17.6h): Racing Santander vs Elche — übersprungen
    ⏰ Zu nah am Anpfiff (-17.6h): Crystal Palace vs Manchester City — übersprungen
    ⏰ Zu nah am Anpfiff (-17.6h): Bayern München vs VfB Stuttgart — übersprungen

-17,6 h ist nicht der Abstand zum Anpfiff, sondern der des Laufs (17:34 UTC) zu MITTERNACHT.
Der Gate bekam `fix["date"]` ("2026-08-28"), also ein Datum ohne Uhrzeit, und das parst als
00:00. Damit galt jedes Spiel ab 02:00 Uhr frueh an seinem eigenen Spieltag als laengst
angepfiffen — obwohl `min_days_until_game = 0` und `min_hours_before_match = 2` genau
erlauben sollten, bis zwei Stunden vor Anpfiff zu handeln.

Die Schwellen bleiben unveraendert. Nur gemessen wird jetzt das Richtige.
"""
import os
import sys
import pytest
from datetime import datetime, timezone, timedelta

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import auto_wm_poly_trigger as A


class TestAnpfiffFeld:
    def test_kickoff_schlaegt_datum(self):
        fix = {"date": "2026-08-28", "kickoff": "2026-08-28T18:30:00Z"}
        assert A._anpfiff_feld(fix) == "2026-08-28T18:30:00Z"

    def test_datum_als_rueckfall(self):
        """Fixtures ohne Uhrzeit gibt es weiterhin — die duerfen nicht durchfallen."""
        assert A._anpfiff_feld({"date": "2026-08-28"}) == "2026-08-28"

    def test_leerer_kickoff_faellt_auf_datum(self):
        assert A._anpfiff_feld({"date": "2026-08-28", "kickoff": ""}) == "2026-08-28"
        assert A._anpfiff_feld({"date": "2026-08-28", "kickoff": None}) == "2026-08-28"

    def test_muell_gibt_leerstring(self):
        for x in (None, "kein dict", 42, {}):
            assert A._anpfiff_feld(x) == ""


class TestDerFehlerAusDemLog:
    def _jetzt_setzen(self, monkeypatch, iso):
        """Laufzeit einfrieren, damit die Stundenrechnung pruefbar ist."""
        fest = datetime.fromisoformat(iso)

        class _DT(datetime):
            @classmethod
            def now(cls, tz=None):
                return fest if tz else fest.replace(tzinfo=None)

        monkeypatch.setattr(A, "datetime", _DT)

    def test_datum_allein_liefert_die_beruechtigten_minus_17_6h(self, monkeypatch):
        """Der Beweis, dass -17,6 h die Mitternachts-Differenz war, nicht der Anpfiff."""
        self._jetzt_setzen(monkeypatch, "2026-08-28T17:34:00+00:00")
        assert A.hours_until("2026-08-28") == pytest.approx(-17.57, abs=0.05)

    def test_echter_anpfiff_liefert_die_wahrheit(self, monkeypatch):
        """Bayern–Stuttgart stiess um 18:30 an, der Lauf war um 17:34 — also +0,9 h."""
        self._jetzt_setzen(monkeypatch, "2026-08-28T17:34:00+00:00")
        assert A.hours_until("2026-08-28T18:30:00Z") == pytest.approx(0.93, abs=0.05)

    def test_am_vormittag_ist_ein_abendspiel_handelbar(self, monkeypatch):
        """Der Fall, der bisher NIE eintrat: 09:00 Uhr, Anpfiff 20:00 → 11 h Vorlauf.

        Vorher meldete derselbe Aufruf -9 h und das Spiel fiel raus.
        """
        self._jetzt_setzen(monkeypatch, "2026-08-28T09:00:00+00:00")
        fix = {"date": "2026-08-28", "kickoff": "2026-08-28T20:00:00Z"}
        h = A.hours_until(A._anpfiff_feld(fix))
        assert h == pytest.approx(11.0, abs=0.05)
        assert h >= A.MIN_HOURS_BEFORE_MATCH, "Spieltags-Abendspiel muss handelbar sein"
        assert A.hours_until(fix["date"]) < 0, "so sah es vorher aus"

    def test_kurz_vor_anpfiff_bleibt_gesperrt(self, monkeypatch):
        """Das Fenster soll oeffnen, nicht verschwinden."""
        self._jetzt_setzen(monkeypatch, "2026-08-28T19:45:00+00:00")
        fix = {"date": "2026-08-28", "kickoff": "2026-08-28T20:00:00Z"}
        assert A.hours_until(A._anpfiff_feld(fix)) < A.MIN_HOURS_BEFORE_MATCH

    def test_nach_anpfiff_bleibt_gesperrt(self, monkeypatch):
        self._jetzt_setzen(monkeypatch, "2026-08-28T21:00:00+00:00")
        fix = {"date": "2026-08-28", "kickoff": "2026-08-28T20:00:00Z"}
        assert A.hours_until(A._anpfiff_feld(fix)) < 0


class TestSchwellenUnveraendert:
    """Die Werte sind Lucas' Entscheidung — dieser Fix darf sie nicht anfassen."""

    def test_stundenfenster_kommt_aus_der_config(self):
        assert A.MIN_HOURS_BEFORE_MATCH == A._cfg("trade", "min_hours_before_match", 4)

    def test_tagesfenster_kommt_aus_der_config(self):
        assert A.MIN_DAYS_UNTIL_GAME == A._cfg("trade", "min_days_until_game", 1)


class TestDerGateBenutztDenAnpfiff:
    def test_gate_ruft_anpfiff_feld_auf(self):
        """Ein Helfer, der nicht aufgerufen wird, heilt nichts."""
        with open(os.path.join(REPO, "auto_wm_poly_trigger.py"), encoding="utf-8") as f:
            src = f.read()
        assert "hours_until(_anpfiff_feld(fix))" in src
        assert 'hours_until(fix.get("date", ""))' not in src, \
            "der alte, datums-basierte Aufruf steht noch da"
