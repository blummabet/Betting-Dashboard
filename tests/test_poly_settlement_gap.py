"""19.07.2026 — Auflösungs-Lücke: nach Abpfiff handelt der feststehende Gewinner noch < 1.00.

Der wichtigste Test hier ist NICHT, dass eine Lücke gefunden wird — sondern dass ein VORSPIEL-
Preis NIEMALS als Lücke durchgeht. Ohne diesen Schutz würde das Skript jede vergangene Wette als
„garantierten Gewinn" ausweisen und echtes Geld auf ein längst gelaufenes Spiel schicken.
"""
from datetime import datetime, timedelta, timezone

import pytest

import poly_settlement_gap as S

KO = datetime(2026, 7, 19, 18, 0, tzinfo=timezone.utc)


def _prices(gen_offset_h, **outcome_over):
    e = {"homeId": "H", "awayId": "A", "title": "Heim vs Gast",
         "kickoff": KO.isoformat(), "vol": 20_000,
         "hw": 0.90, "dr": 0.05, "aw": 0.05,
         "poly_o15": 0.90, "poly_u15": 0.10,
         "poly_o25": 0.20, "poly_u25": 0.80,
         "poly_o35": 0.05, "poly_u35": 0.95,
         "poly_btts": 0.10, "poly_btts_no": 0.90}
    e.update(outcome_over)
    return {"generatedAt": (KO + timedelta(hours=gen_offset_h)).isoformat(),
            "prices": {"H-A": e}}


def _data(hs, as_):
    return {"groups": {"MLS": {"fixtures": [
        {"home": "H", "away": "A", "result": {"status": "FT", "home_score": hs, "away_score": as_}}]}}}


class TestLueckeWirdGefunden:
    def test_heimsieg_steht_fest_aber_unter_1(self):
        # 2:0 → Heim gewann, Über 1.5 gewann, Unter 2.5 verlor... hw noch 0.90 → 10pp Lücke
        rep = S.analyze(_prices(3, hw=0.90), _data(2, 0))
        hw = [g for g in rep["gaps"] if g["markt"] == "1X2"]
        assert hw and hw[0]["gapPP"] == pytest.approx(10.0)

    def test_alle_gewinner_maerkte(self):
        """2:1 → Heim, Über 1.5+2.5, BTTS. Alle unterbepreist → mehrere Lücken."""
        rep = S.analyze(_prices(3, hw=0.92, poly_o15=0.94, poly_o25=0.93, poly_btts=0.90),
                        _data(2, 1))
        märkte = {g["markt"] for g in rep["gaps"]}
        assert {"1X2", "Ü/U 1.5", "Ü/U 2.5", "BTTS"} <= märkte

    def test_gewinner_bei_1_ist_keine_luecke(self):
        """Schon aufgelöst (1.00) → nichts zu holen."""
        rep = S.analyze(_prices(3, hw=1.0), _data(2, 0))
        assert not any(g["markt"] == "1X2" for g in rep["gaps"])

    def test_winzige_luecke_unter_der_gebuehr(self):
        rep = S.analyze(_prices(3, hw=0.99), _data(2, 0))   # nur 1pp < MIN_GAP_PP
        assert not any(g["markt"] == "1X2" for g in rep["gaps"])


class TestStaleSchutz:
    def test_vorspiel_preis_ist_keine_luecke(self):
        """DER kritische Test: Snapshot VOR Anpfiff → 0.90 ist die damalige Quote, kein Settlement."""
        rep = S.analyze(_prices(-1, hw=0.90), _data(2, 0))   # generatedAt 1h VOR KO
        assert rep["gaps"] == [], "Vorspiel-Preis als garantierter Gewinn ausgewiesen"
        assert rep["skippedStale"] == 1

    def test_kurz_nach_anpfiff_noch_in_play(self):
        """30min nach Anpfiff läuft das Spiel noch — Preis ist In-Play, nicht Settlement."""
        rep = S.analyze(_prices(0.5, hw=0.90), _data(2, 0))
        assert rep["gaps"] == [] and rep["skippedStale"] == 1

    def test_deutlich_nach_abpfiff_zaehlt(self):
        rep = S.analyze(_prices(3, hw=0.90), _data(2, 0))
        assert rep["gapCount"] >= 1


class TestRobustheit:
    def test_kein_ergebnis_keine_luecke(self):
        rep = S.analyze(_prices(3), {"groups": {"MLS": {"fixtures": [
            {"home": "H", "away": "A", "result": {"status": "NS"}}]}}})
        assert rep["gaps"] == []

    def test_duenner_markt_raus(self):
        rep = S.analyze(_prices(3, vol=200, hw=0.85), _data(2, 0))
        assert rep["gaps"] == []

    def test_ko_fixtures_werden_erfasst(self):
        data = {"koFixtures": [
            {"home": "H", "away": "A", "result": {"status": "AET", "home_score": 3, "away_score": 0}}]}
        rep = S.analyze(_prices(3, hw=0.90), data)
        assert rep["gapCount"] >= 1, "KO-Spiele (koFixtures) werden übersehen"

    def test_leere_eingaben(self):
        assert S.analyze({}, {})["gapCount"] == 0
